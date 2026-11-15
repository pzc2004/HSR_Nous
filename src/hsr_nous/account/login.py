"""米游社扫码登录（QR login）——替代手动 Cookie 提取的凭证获取通道.

流程（协议参考 jiarui666/mihoyo_qr_login 与 UIGF mihoyo-api-collect，自实现不搬码）：
  1. hk4e-sdk 申请登录 ticket → 终端显示二维码
  2. 米游社 APP 扫码 + 确认 → 轮询拿到 game_token
  3. game_token → stoken（api-takumi，DS-K2 签名）
  4. stoken → ltoken / cookie_token（passport-api，DS-X4 签名）
  5. 凭证写入 keyring（HSR_NOUS_HOYO_LTUID/LTOKEN）——client._read_secret 自动接续

用法：uv run python -m hsr_nous.account.login
"""
from __future__ import annotations

import hashlib
import json
import random
import string
import sys
import time
import uuid
from typing import Any, Optional

import httpx
import qrcode

_QR_FETCH = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/fetch"
_QR_QUERY = "https://hk4e-sdk.mihoyo.com/hk4e_cn/combo/panda/qrcode/query"
_TOKEN_BY_GAME = "https://api-takumi.mihoyo.com/account/ma-cn-session/app/getTokenByGameToken"
_LTOKEN = "https://passport-api.mihoyo.com/account/auth/api/getLTokenBySToken"
_COOKIE_TOKEN = "https://passport-api.mihoyo.com/account/auth/api/getCookieAccountInfoBySToken"

_APP_ID_QR = "8"                 # 二维码登录 app_id（崩坏:星穹铁道;UIGF 词表——7 是崩坏学园2)
_APP_ID_PASSPORT = "bll8iq97cem8"
_DS_SALT_K2 = "OvOIsZRXrUbXoUlpQuhEx4tgAwNVUMmp"
_DS_SALT_X4 = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"
_BBS_VERSION = "2.102.1"
_BBS_UA = f"Mozilla/5.0 (Linux; Android 12) Mobile miHoYoBBS/{_BBS_VERSION}"


def _ds_k2(body: dict) -> str:
    t = str(int(time.time()))
    r = "".join(random.choices(string.ascii_letters, k=6))
    b = json.dumps(body)
    h = hashlib.md5(f"salt={_DS_SALT_K2}&t={t}&r={r}&b={b}&q=".encode()).hexdigest()
    return f"{t},{r},{h}"


def _ds_x4(query: str = "", body: str = "") -> str:
    t = str(int(time.time()))
    r = str(random.randint(100000, 200000))
    h = hashlib.md5(f"salt={_DS_SALT_X4}&t={t}&r={r}&b={body}&q={query}".encode()).hexdigest()
    return f"{t},{r},{h}"


def _print_qr(text: str) -> None:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=1)
    qr.add_data(text)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


class QRLogin:
    def __init__(self) -> None:
        # 与记录 API 共用同一设备身份（风控看的是"设备故事"一致性——旧实现每次
        # 登录现造随机身份，见 account/device.py 头注）；签发失败退回本地随机。
        from hsr_nous.account.device import ensure_device_identity
        did, dfp = ensure_device_identity()
        self.device_id = did or str(uuid.uuid4()).upper()
        self.device_fp = dfp or "".join(random.choices("0123456789abcdef", k=13))
        self._client = httpx.Client(timeout=30.0)

    # ---------------------------------------------------------- 1. ticket
    def fetch_ticket(self) -> Optional[dict[str, str]]:
        resp = self._client.post(_QR_FETCH, json={"app_id": _APP_ID_QR, "device": self.device_id})
        data = resp.json()
        if data.get("retcode") != 0:
            print(f"[error] 申请二维码失败: {data.get('message')}")
            return None
        url = data["data"]["url"]
        ticket = url.split("ticket=")[1].split("&")[0] if "ticket=" in url else ""
        return {"url": url, "ticket": ticket}

    # ---------------------------------------------------------- 2. 轮询
    def wait_confirm(self, ticket: str, timeout: float = 180.0) -> Optional[dict[str, str]]:
        print("请用米游社 APP → 我的 → 右上角扫一扫 扫描上方二维码")
        start, last = time.time(), ""
        while time.time() - start < timeout:
            resp = self._client.post(
                _QR_QUERY,
                json={"app_id": _APP_ID_QR, "device": self.device_id, "ticket": ticket},
            )
            data = resp.json()
            if data.get("retcode") != 0:
                print(f"[error] 查询失败: {data.get('message')}")
                return None
            stat = data["data"].get("stat", "")
            if stat != last:
                print({"Init": "等待扫码…", "Scanned": "已扫码,请在 APP 上确认登录",
                       "Confirmed": "已确认,正在换取凭证…"}.get(stat, stat))
                last = stat
            if stat == "Confirmed":
                raw = data["data"].get("payload", {}).get("raw", "{}")
                payload = json.loads(raw)
                return {"uid": str(payload.get("uid", "")), "game_token": payload.get("token", "")}
            time.sleep(2)
        print("[error] 扫码超时")
        return None

    # ---------------------------------------------------------- 3. game_token → stoken
    def exchange_stoken(self, uid: str, game_token: str) -> Optional[dict[str, str]]:
        body = {"account_id": int(uid), "game_token": game_token}
        headers = {
            "x-rpc-app_id": _APP_ID_PASSPORT,
            "x-rpc-client_type": "2",
            "x-rpc-game_biz": "bbs_cn",
            "x-rpc-device_id": self.device_id,
            "x-rpc-device_fp": self.device_fp,
            "ds": _ds_k2(body),
            "user-agent": _BBS_UA,
        }
        data = self._client.post(_TOKEN_BY_GAME, json=body, headers=headers).json()
        if data.get("retcode") != 0:
            print(f"[error] 换取 stoken 失败: {data.get('message')}")
            return None
        d = data["data"]
        return {
            "stoken": d["token"]["token"],
            "mid": d["user_info"]["mid"],
            "stuid": d["user_info"].get("aid") or uid,
        }

    # ---------------------------------------------------------- 4. stoken → ltoken/cookie_token
    def _exchange_headers(self, stoken: str, mid: str, query: str) -> dict[str, str]:
        return {
            "user-agent": _BBS_UA,
            "x-rpc-app_version": _BBS_VERSION,
            "x-rpc-client_type": "5",
            "x-requested-with": "com.mihoyo.hyperion",
            "referer": "https://webstatic.mihoyo.com",
            "x-rpc-device_id": self.device_id,
            "x-rpc-device_fp": self.device_fp,
            "ds": _ds_x4(query=query),
            "cookie": f"mid={mid};stoken={stoken}",
        }

    def exchange_ltoken(self, stoken: str, mid: str) -> Optional[str]:
        headers = self._exchange_headers(stoken, mid, f"stoken={stoken}")
        data = self._client.get(_LTOKEN, headers=headers, params={"stoken": stoken}).json()
        if data.get("retcode") != 0:
            print(f"[error] 换取 ltoken 失败: {data.get('message')}")
            return None
        return data["data"].get("ltoken")

    def exchange_cookie_token(self, stoken: str, mid: str) -> Optional[str]:
        headers = self._exchange_headers(stoken, mid, f"stoken={stoken}")
        data = self._client.get(_COOKIE_TOKEN, headers=headers, params={"stoken": stoken}).json()
        if data.get("retcode") != 0:
            print(f"[error] 换取 cookie_token 失败: {data.get('message')}")
            return None
        return data["data"].get("cookie_token")

    def close(self) -> None:
        self._client.close()


def qr_login(timeout: float = 180.0) -> Optional[dict[str, str]]:
    """完整扫码登录：终端出码 → 确认 → 换取全部凭证（ltuid/ltoken/cookie_token/stoken/mid）."""
    login = QRLogin()
    try:
        ticket = login.fetch_ticket()
        if not ticket:
            return None
        _print_qr(ticket["url"])
        confirmed = login.wait_confirm(ticket["ticket"], timeout=timeout)
        if not confirmed:
            return None
        stoken_info = login.exchange_stoken(confirmed["uid"], confirmed["game_token"])
        if not stoken_info:
            return None
        stoken, mid, stuid = stoken_info["stoken"], stoken_info["mid"], stoken_info["stuid"]
        ltoken = login.exchange_ltoken(stoken, mid)
        cookie_token = login.exchange_cookie_token(stoken, mid)
        if not (ltoken and cookie_token):
            return None
        return {
            "ltuid": stuid, "ltoken": ltoken, "cookie_token": cookie_token,
            "stoken": stoken, "mid": mid,
        }
    finally:
        login.close()


def _save_to_keyring(creds: dict[str, str]) -> bool:
    try:
        import keyring

        keyring.set_password("hsr_nous", "HSR_NOUS_HOYO_LTUID", creds["ltuid"])
        keyring.set_password("hsr_nous", "HSR_NOUS_HOYO_LTOKEN", creds["ltoken"])
        return True
    except Exception as e:  # noqa: BLE001
        try:
            keyring.delete_password("hsr_nous", "HSR_NOUS_HOYO_LTUID")
        except Exception:  # noqa: BLE001
            pass
        print(f"[warn] keyring 写入失败（{type(e).__name__}）——回退写入 .env", file=sys.stderr)
        return False


def _save_to_env(creds: dict[str, str]) -> None:
    """回退通道：直接写仓库根 .env（gitignored，权限 0600）。headless 无 keyring 后端时用."""
    from hsr_nous.common.paths import repo_root

    env_path = repo_root() / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    kv = {"HSR_NOUS_HOYO_LTUID": creds["ltuid"], "HSR_NOUS_HOYO_LTOKEN": creds["ltoken"]}
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in kv:
            out.append(f"{key}={kv[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in kv.items():
        if key not in seen:
            out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    env_path.chmod(0o600)
    print("凭证已写入 .env（keyring 不可用的回退通道）")


def main() -> int:
    print("=" * 56)
    print("  米游社扫码登录（凭证将写入 keyring，供 account 模块使用）")
    print("=" * 56)
    creds = qr_login()
    if not creds:
        print("登录失败")
        return 1
    print(f"登录成功：UID ***{creds['ltuid'][-4:]}")
    if _save_to_keyring(creds):
        print("凭证已写入 keyring（HSR_NOUS_HOYO_LTUID/LTOKEN）")
    else:
        _save_to_env(creds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
