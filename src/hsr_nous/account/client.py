"""HoYoLAB / 米游社 HSR API 客户端（thin wrapper）.

只做三件事：
1. 读取 ltuid/ltoken（keyring 优先，.env fallback）
2. 调取公开 API（角色列表、忘却之庭战绩、开拓力）
3. 把 JSON 转为 OwnedCharacter / MoCRecord / AccountSnapshot

**协议警告**：HoYoLAB API 是非官方协议，米哈游随时可能轮换端点。
代码应当能够容忍字段缺失——任何字段都可能是 None。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from hsr_nous.account.models import AccountSnapshot, MoCRecord, OwnedCharacter


class AccountError(Exception):
    """账号 API 调用错误（凭据缺失 / 端点轮换 / 网络）."""


# ----------------------------------------------------------------- token 读取


def _read_secret(env_key: str) -> Optional[str]:
    """优先从 keyring 读，回退到 .env（HSR_NOUS_ 前缀）."""
    try:
        import keyring

        v = keyring.get_password("hsr_nous", env_key)
        if v:
            return v
    except Exception:
        # keyring 在无 GUI / macOS keychain 锁定时可能失败
        pass
    return os.environ.get(env_key) or None


def _read_credentials() -> tuple[Optional[str], Optional[str]]:
    """返回 (ltuid, ltoken)，都为 None 表示未配置."""
    return (
        _read_secret("HSR_NOUS_HOYO_LTUID"),
        _read_secret("HSR_NOUS_HOYO_LTOKEN"),
    )


def is_configured() -> bool:
    """是否已配置 ltuid/ltoken."""
    ltuid, ltoken = _read_credentials()
    return bool(ltuid and ltoken)


# ----------------------------------------------------------------- DS 签名（简版）

_SALT = "xV8v4Qu54lUKrEYFZkJhB8cuOh9Asafs"  # 已知常量（部分公开逆向）


def _ds_sign(query: str = "", body: str = "") -> str:
    """生成 mihoyo DS 签名（极简版，不含 random body hash 校验）.

    完整签名算法：md5(salt + timestamp + str(rand) + query + body_hash)，
    其中 rand 是 6 位字母数字。本实现使用固定 'hsrnous' 串——可能被风控，
    但对只读端点足够（HoYoLAB 接口鉴权重在 cookie）。
    """
    t = str(int(time.time()))
    s = _SALT
    rand = "hsrnous"
    raw = f"{s}{t}{rand}{query}{body}"
    h = hashlib.md5(raw.encode()).hexdigest()
    return f"{t},{rand},{h}"


# ----------------------------------------------------------------- HTTP 客户端


_BASE_URLS = {
    # server_code → api base
    "cn_gf01": "https://api-takumi.mihoyo.com",
    "cn_qd01": "https://api-takumi-qingdao.mihoyo.com",
    "os_asia": "https://api-os.hoyolab.com",
    "os_euro": "https://api-os.hoyolab.com",
    "os_america": "https://api-os.hoyolab.com",
}


def _resolve_server() -> str:
    return os.environ.get("HSR_NOUS_HOYO_SERVER", "cn_gf01")


def _headers(ltuid: str, ltoken: str, ds: str) -> Dict[str, str]:
    return {
        "Cookie": f"ltuid={ltuid}; ltoken={ltoken};",
        "DS": ds,
        "x-rpc-app_version": "2.40.0",
        "x-rpc-client_type": "5",
        "x-rpc-language": "zh-cn",
        "x-rpc-device_id": "hsr-nous-device",
        "User-Agent": "hsr-nous/0.1",
    }


def _safe_get_json(url: str, headers: Dict[str, str], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """GET 请求，返回 JSON 或 None（任何异常都不抛）."""
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=headers)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ----------------------------------------------------------------- 公开 API


def get_owned_characters(*, lang: str = "cn") -> List[OwnedCharacter]:
    """拉取用户拥有的角色列表.

    Args:
        lang: 显示语言 "cn" / "en"

    Returns:
        List[OwnedCharacter]：空列表表示未配置/失败/账号无角色。
    """
    ltuid, ltoken = _read_credentials()
    if not (ltuid and ltoken):
        return []

    base = _BASE_URLS.get(_resolve_server(), _BASE_URLS["cn_gf01"])
    url = f"{base}/event/solstar/party/avatar/list"
    ds = _ds_sign()
    data = _safe_get_json(url, _headers(ltuid, ltoken, ds))
    if not data or data.get("retcode", -1) != 0:
        return []

    chars_raw = data.get("data", {}).get("list", [])
    result: List[OwnedCharacter] = []
    for ch in chars_raw:
        try:
            oc = OwnedCharacter(
                character_id=str(ch.get("avatar_id", "")),
                name=ch.get("name", ""),
                level=int(ch.get("level", 1)),
                ascension=int(ch.get("promotion", 0)),
                eidolon=int(ch.get("rank", 0)),
                light_cone_id=str(ch.get("equipment_id") or "") or None,
                light_cone_level=int(ch.get("equipment_level", 1)),
                relic_set_ids=[
                    str(r.get("set_id"))
                    for r in ch.get("relic_list", [])
                    if r.get("set_id")
                ],
                raw=ch,
            )
            result.append(oc)
        except Exception:
            continue
    return result


def get_trailblaze_power() -> int:
    """拉取当前开拓力（0 表示未配置或失败）."""
    ltuid, ltoken = _read_credentials()
    if not (ltuid and ltoken):
        return 0
    base = _BASE_URLS.get(_resolve_server(), _BASE_URLS["cn_gf01"])
    url = f"{base}/event/solstar/note/api/note"
    ds = _ds_sign()
    data = _safe_get_json(url, _headers(ltuid, ltoken, ds))
    if not data or data.get("retcode", -1) != 0:
        return 0
    return int(data.get("data", {}).get("current_stamina", 0))


def get_moc_records() -> List[MoCRecord]:
    """拉取忘却之庭战绩（最近若干期）."""
    ltuid, ltoken = _read_credentials()
    if not (ltuid and ltoken):
        return []
    base = _BASE_URLS.get(_resolve_server(), _BASE_URLS["cn_gf01"])
    url = f"{base}/event/solstar/party/index"
    ds = _ds_sign()
    data = _safe_get_json(url, _headers(ltuid, ltoken, ds))
    if not data or data.get("retcode", -1) != 0:
        return []

    moc_list = data.get("data", {}).get("challenge", [])
    result: List[MoCRecord] = []
    for m in moc_list:
        try:
            result.append(
                MoCRecord(
                    season=int(m.get("season", 0)),
                    name=m.get("name", ""),
                    stars=int(m.get("star_num", 0)),
                    max_floor=int(m.get("max_floor", 0)),
                    total_battles=int(m.get("battle_num", 0)),
                )
            )
        except Exception:
            continue
    return result


def get_account_snapshot() -> AccountSnapshot:
    """一次性拉取账号完整快照."""
    ltuid, _ = _read_credentials()
    return AccountSnapshot(
        uid=ltuid or "",
        trailblaze_power=get_trailblaze_power(),
        owned_characters=get_owned_characters(),
        moc_records=get_moc_records(),
    )


# ----------------------------------------------------------------- 类接口


class AccountClient:
    """面向对象客户端（与函数 API 等价）."""

    def __init__(self) -> None:
        self.configured = is_configured()

    def owned_characters(self) -> List[OwnedCharacter]:
        return get_owned_characters()

    def trailblaze_power(self) -> int:
        return get_trailblaze_power()

    def moc_records(self) -> List[MoCRecord]:
        return get_moc_records()

    def snapshot(self) -> AccountSnapshot:
        return get_account_snapshot()