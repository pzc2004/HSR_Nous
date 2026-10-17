"""记录类接口的 Chrome 指纹传输层（curl_cffi）——风控应对件，§1.8 在案.

为什么存在（2026-10-17 实证）：米游社风控按 TLS/HTTP2 指纹甄别脚本——aiohttp/
httpx 的 ClientHello 与 Chrome 是两种生物。变量排除实验：设备指纹（自动签发/
浏览器可信值）、cookie 完备度（2→10 个）、UA/Referer 伪装——全部仍 10035。
curl_cffi（curl-impersonate 绑定，impersonate="chrome"）在传输层复制 Chrome
的 TLS+H2 指纹，是社区标准解法。

职责边界（压缩原则）：只替代**传输**。端点路由、DS 签名、retcode→错误映射、
数据模型全部复用 genshin.py（单一来源——它漂移我们跟随）；本件只做：
  genshin 模型/签名/路由 + curl_cffi 的 Session(impersonate="chrome").

缺 curl_cffi（account extra 未装新依赖的旧环境）→ available()=False，
调用方回退 genshin.py 原生 aiohttp 路径（POSIX 低风控环境仍可用）。

风控错误语义不变：retcode 非 0 原样映射 genshin.errors（含 GeetestError——
client.py 的分类日志与静默 None 纪律零改动）。
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import genshin.errors as _errors
import genshin.types as _types
import genshin.utility as _utility
from genshin.client import routes as _routes
from genshin.models.starrail import chronicle as _chronicle

REGION = _types.Region.CHINESE  # 本项目账号集成为国服口径（client._resolve_region 同）
GAME = _types.Game.STARRAIL

#: impersonate 目标——curl-impersonate 的 Chrome 指纹档（选具体主版本收益甚微，
#: "chrome" 档随库更新保持现役指纹——跟随 curl_cffi 版本走即跟随 Chrome 大版本）
_IMPERSONATE = "chrome"


def available() -> bool:
    """curl_cffi 是否可用（account extra 装了即 True；旧环境回退 aiohttp 路径）."""
    try:
        import curl_cffi  # noqa: F401
        return True
    except ImportError:
        return False


def _record_url(endpoint: str) -> str:
    base = _routes.RECORD_URL.get_url(REGION, GAME)
    return f"{base}/{endpoint}"


def _get(session: Any, endpoint: str, uid: int, cookies: Mapping[str, str],
         device_headers: Dict[str, str], params_extra: Optional[Dict[str, Any]],
         timeout: float) -> Mapping[str, Any]:
    """单接口 GET：params/DS 用同一 dict（DS 签名与实发参数必须逐字一致）."""
    params: Dict[str, Any] = {"role_id": uid,
                              "server": _utility.recognize_starrail_server(uid)}
    params.update(params_extra or {})
    headers = {
        **_utility.ds.get_ds_headers(REGION, params=params),
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
        **device_headers,
    }
    resp = session.get(_record_url(endpoint), params=params, headers=headers,
                       timeout=timeout)
    data = resp.json()
    # genshin manager 两步语义照抄（managers.py:201）：先极验码直映射 GeetestError
    # （GEETEST_RETCODES=10035/5003/10041/1034），再通用 retcode 映射
    _errors.check_for_geetest(data)
    if data.get("retcode", 0) != 0:
        _errors.raise_for_retcode(data)
    return data["data"]


def fetch_starrail_records(
    uid: int,
    cookies: Mapping[str, str],
    *,
    device_id: Optional[str] = None,
    device_fp: Optional[str] = None,
    timeout: float = 30.0,
) -> Tuple[_chronicle.StarRailDetailCharacterResponse, _chronicle.StarRailNote,
           _chronicle.StarRailChallenge]:
    """三个记录类接口一次拉全（字符详情/开拓力/忘却之庭）。

    与 genshin.py 组件同参数口径（endpoint/payload 照抄其 starrail 组件）：
    avatar/info 带 need_wiki=true，challenge 带 schedule_type=1&need_all=true。
    retcode 非 0 → genshin.errors（GeetestError=10035 风控，由调用方分类）。
    """
    from curl_cffi import requests as _cffi

    device_headers = {}
    if device_id:
        device_headers["x-rpc-device_id"] = device_id
    if device_fp:
        device_headers["x-rpc-device_fp"] = device_fp

    with _cffi.Session(impersonate=_IMPERSONATE) as session:
        detail = _chronicle.StarRailDetailCharacterResponse(**_get(
            session, "avatar/info", uid, cookies, device_headers,
            {"need_wiki": "true"}, timeout))
        notes = _chronicle.StarRailNote(**_get(
            session, "note", uid, cookies, device_headers, None, timeout))
        challenge_raw = _get(session, "challenge", uid, cookies, device_headers,
                             {"schedule_type": 1, "need_all": "true"}, timeout)
        challenge = _chronicle.StarRailChallenge(**challenge_raw)
    return detail, notes, challenge
