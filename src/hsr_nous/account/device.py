"""设备身份（device_id + device_fp）的签发与持久化——风控信任链地基.

背景（docs/integrations.md §1.8）：米哈游对记录类接口按"设备可信度"收敛——新指纹
冷启动敏感（Geetest 10035 高发）、稳定指纹随使用收敛。所以设备身份必须
**一次签发、永久复用**：每次登录/拉取都换随机指纹正是风控诱因之一。

两个件：
- device_id：本项目自生成的 uuid4（大写），永久不变；
- device_fp：调米哈游官方 getFp 端点拿的**服务端签发值**（不是自己拼——
  只有签发值进得了信任链；payload 形状照抄 genshin.py 1.7.31 generate_fp
  的现行实现，见 .venv/.../genshin/client/components/auth/client.py）。

优先级：env 显式覆写（HSR_NOUS_HOYO_DEVICE_ID/FP——风控排查用，见 §1.8 第 2 条）
> 持久化文件。存储在 ~/.config/hsr_nous/device_identity.json（非密钥，无需
keyring；headless 下 keyring 常不可用）。任何失败不抛——没有身份只是风控
概率变差，不是功能缺失。
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
import uuid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_ENV_ID = "HSR_NOUS_HOYO_DEVICE_ID"
_ENV_FP = "HSR_NOUS_HOYO_DEVICE_FP"

#: 米哈游 getFp 端点（genshin.py routes.py 现行值——CN/OS 分列）
_GET_FP_URLS = {
    "cn": "https://public-data-api.mihoyo.com/device-fp/api/getFp",
    "os": "https://sg-public-data-api.hoyoverse.com/device-fp/api/getFp",
}


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hsr_nous"


def _identity_path() -> Path:
    return _config_dir() / "device_identity.json"


def _load_file() -> dict:
    try:
        p = _identity_path()
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("设备身份文件读取失败（%s）——按未签发处理", type(e).__name__)
    return {}


def _save_file(data: dict) -> None:
    try:
        d = _config_dir()
        d.mkdir(parents=True, exist_ok=True)
        _identity_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        logger.warning("设备身份持久化失败（%s）——本次进程内仍生效", type(e).__name__)


def _random_seed_fp() -> str:
    return "".join(random.choices("0123456789abcdef", k=13))


def _stable_oaid(device_id: str) -> str:
    """从 device_id 稳定派生 oaid（16 位 hex）。

    oaid=Android 匿名设备标识——端点对**空 oaid 拒签**（code 500「内部错误」，
    2026-10-17 五变体对照实验实证），所以桌面场景也必须给个非空值；派生而非
    随机：同设备同 oaid，身份故事一致。
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, f"hsr_nous:oaid:{device_id}").hex[:16]


def _sign_device_fp(device_id: str, timeout: float = 15.0) -> Optional[str]:
    """调米哈游 getFp 端点签发 device_fp（失败/超时 → None 不抛）."""
    import urllib.request

    server = os.environ.get("HSR_NOUS_HOYO_SERVER", "cn_gf01")
    cn = server.startswith("cn_")
    payload = {
        "device_id": device_id,
        "device_fp": _random_seed_fp(),
        "seed_id": str(uuid.uuid4()).lower(),
        "seed_time": str(int(time.time() * 1000)),
        "platform": "2",
        "app_name": "bbs_cn" if cn else "bbs_oversea",
        # ext_fields 形状照抄 genshin.py generate_fp（oaid 必填非空——空串实测
        # 被端点拒签；board 五变体对照实验证明非必要，不给）
        "ext_fields": json.dumps({"oaid": _stable_oaid(device_id)}),
        "bbs_device_id" if cn else "hoyolab_device_id": str(uuid.uuid4()).lower(),
    }
    req = urllib.request.Request(
        _GET_FP_URLS["cn" if cn else "os"],
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0 miHoYoBBS/2.102.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        # 成功契约照抄 genshin.py：data.data.code == 200，fp 在 data.data.device_fp
        if data.get("data", {}).get("code") == 200:
            return str(data["data"]["device_fp"])
        logger.warning("getFp 拒签（code=%s）：%s", data.get("data", {}).get("code"),
                       data.get("data", {}).get("msg") or data.get("message"))
    except Exception as e:  # noqa: BLE001 — 网络/JSON/端点漂移任何失败都降级
        logger.warning("getFp 签发失败（%s: %s）", type(e).__name__, e)
    return None


#: 写盘失败时的进程内兜底（不替代持久化文件；env 显式覆写仍最高优先级）。
_IDENTITY_CACHE: dict = {}


def load_device_identity() -> Tuple[Optional[str], Optional[str]]:
    """读设备身份（env 覆写 > 持久化文件 > 进程内缓存；纯本地，无网络）。"""
    env_id, env_fp = os.environ.get(_ENV_ID), os.environ.get(_ENV_FP)
    data = _load_file()
    return (env_id or data.get("device_id") or _IDENTITY_CACHE.get("device_id"),
            env_fp or data.get("device_fp") or _IDENTITY_CACHE.get("device_fp"))


def ensure_device_identity(timeout: float = 15.0) -> Tuple[Optional[str], Optional[str]]:
    """取设备身份；缺则签发并持久化（幂等——已有不重复签发）。

    任何一步失败都返回当前最好的结果（device_id 必有——本地生成；device_fp 可能
    None——拒签/离线时不阻塞调用方）。FP-only 覆写与持久化 ID 合并，写盘失败时
    通过进程内缓存避免每次重新生成。
    """
    device_id, device_fp = load_device_identity()
    if device_id and device_fp:
        return device_id, device_fp
    if device_id is None:
        device_id = str(uuid.uuid4()).upper()
        _save_file({"device_id": device_id, "device_fp": device_fp,
                    "fp_issued_at": None})
        logger.info("设备身份已生成并持久化：device_id=%s…（getFp 签发随后进行）",
                    device_id[:8])
    if device_fp is None:
        signed = _sign_device_fp(device_id, timeout=timeout)
        if signed:
            device_fp = signed
            _save_file({"device_id": device_id, "device_fp": device_fp,
                        "fp_issued_at": int(time.time())})
            logger.info("device_fp 已由 getFp 端点签发并持久化")
    _IDENTITY_CACHE.update(device_id=device_id, device_fp=device_fp)
    return device_id, device_fp
