"""米游社账号读取：genshin.py 传输层（https://github.com/seriaati/genshin.py）.

纪律：未配置/任何失败 → 静默返回 None，不抛异常、不主动重试、不脑补。
DS 签名/端点轮换/限流重试由 genshin.py 承担（旧手写极简签名已退役）。

配置（部署事实，见 docs/integrations.md）：
- HSR_NOUS_HOYO_LTUID / HSR_NOUS_HOYO_LTOKEN（keyring 优先，.env 兜底）
- HSR_NOUS_HOYO_SERVER（默认 cn_gf01 → Region.CHINESE；cn_* 国服，其余国际服）
- HSR_NOUS_HOYO_UID（可选；不给则从账号列表解析首个崩铁 UID）
- HSR_NOUS_HOYO_DEVICE_ID / HSR_NOUS_HOYO_DEVICE_FP（可选；缺省自动签发并
  永久复用——见 account/device.py；env 仅作风控排查覆写，见 §1.8 第 2 条）
- 仓库根 .env 自动加载（`hsr_nous.common.env.load_repo_env`；调用方无需先 load_dotenv）
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, Tuple

import genshin

from hsr_nous.account import transport
from hsr_nous.account.device import ensure_device_identity
from hsr_nous.account.models import (
    AccountCharacter,
    AccountLightCone,
    AccountRelic,
    AccountSnapshot,
    MoCRecord,
    RelicStat,
)
from hsr_nous.common.env import load_repo_env

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------- 凭证与构造


def _read_secret(env_key: str) -> Optional[str]:
    """keyring 优先，回退环境变量（headless 下 keyring 可能失败，静默回退）."""
    try:
        import keyring

        v = keyring.get_password("hsr_nous", env_key)
        if v:
            return v
    except Exception:  # noqa: BLE001 — keyring 在无 GUI/锁定时不可用,回退即可
        pass
    return os.environ.get(env_key) or None


def _resolve_region() -> genshin.Region:
    server = os.environ.get("HSR_NOUS_HOYO_SERVER", "cn_gf01")
    return genshin.Region.CHINESE if server.startswith("cn_") else genshin.Region.OVERSEAS


def _make_client() -> Optional[genshin.Client]:
    """构造客户端；未配置返回 None。独立工厂——测试注入点（monkeypatch 本函数）.

    设备身份（device_id/device_fp）由 account.device 自动签发/复用（风控信任链，
    见 device.py 头注）；env 显式值优先于持久化值。
    """
    load_repo_env()  # 仓库根 .env（common.env；不覆盖已有环境变量；keyring 仍优先）
    ltuid = _read_secret("HSR_NOUS_HOYO_LTUID")
    ltoken = _read_secret("HSR_NOUS_HOYO_LTOKEN")
    if not (ltuid and ltoken):
        logger.info("米游社未配置（keyring/.env 无 ltuid+ltoken）——账号快照跳过")
        return None
    uid_env = os.environ.get("HSR_NOUS_HOYO_UID")
    device_id, device_fp = ensure_device_identity()
    # 米游社现为 v2 凭证（浏览器里只有 ltuid_v2/ltoken_v2），但 genshin 的鉴权
    # 归一化走 v1 键名——实测(2026-10-16)裸 v2 键名被服务端拒(InvalidCookies)，
    # v1 键名+v2 值正常。设备指纹：缺省走自动签发（首次一次 getFp 调用，之后
    # 永久复用——频繁换指纹是风控诱因）；风控排查可 env 覆写可信旧值。
    return genshin.Client(
        {"ltuid": ltuid, "ltoken": ltoken},
        game=genshin.Game.STARRAIL,
        region=_resolve_region(),
        uid=int(uid_env) if uid_env else None,
        device_id=device_id,
        device_fp=device_fp,
    )


# ----------------------------------------------------------------- 模型映射


def _relic_stat(p) -> RelicStat:
    """RelicProperty/DetailRelicProperty → RelicStat（API 原始名与值串原样保留）."""
    info = getattr(p, "info", None)
    name = info.name if info is not None else getattr(p, "name", "")
    return RelicStat(name=name, value=str(p.value), times=int(getattr(p, "times", 1)))


def _to_relic(r) -> AccountRelic:
    return AccountRelic(
        id=str(r.id),
        name=r.name,
        pos=int(r.pos),
        level=int(r.level),
        rarity=int(r.rarity),
        main=_relic_stat(r.main_property) if r.main_property else None,
        subs=tuple(_relic_stat(p) for p in r.properties),
    )


def _to_light_cone(e) -> Optional[AccountLightCone]:
    if e is None:
        return None
    return AccountLightCone(
        id=str(e.id), name=e.name, level=int(e.level),
        superimposition=int(e.rank), rarity=int(e.rarity),
    )


def _panel_value(raw: str) -> float:
    """面板值串解析："1234.5"→1234.5；"10.5%"→0.105（百分号转小数）."""
    raw = raw.strip()
    if raw.endswith("%"):
        return float(raw[:-1]) / 100.0
    return float(raw)


def _to_character(c) -> AccountCharacter:
    panel = {}
    for p in c.properties:
        try:
            panel[p.info.name] = _panel_value(p.final)
        except (ValueError, AttributeError):
            continue
    return AccountCharacter(
        id=str(c.id),
        name=c.name,
        level=int(c.level),
        eidolon=int(c.rank),
        unlocked_eidolons=tuple(r.name for r in c.ranks if r.is_unlocked),
        path=str(c.path),
        element=c.element,
        skill_levels={s.point_id: int(s.level) for s in c.skills},
        light_cone=_to_light_cone(c.equip),
        relics=tuple(_to_relic(r) for r in (*c.relics, *c.ornaments)),
        panel=panel,
        has_memosprite=c.memosprite is not None,
    )


# ----------------------------------------------------------------- 拉取主流程


async def _fetch_snapshot(client: genshin.Client) -> AccountSnapshot:
    uid = client.uid
    nickname, level = "", 0
    if uid is None:
        # 账号列表首个崩铁号（顺带拿到昵称/开拓等级，省一次调用）
        accounts = await client.get_game_accounts()
        for acc in accounts:
            if "hkrpg" in acc.game_biz:
                uid, nickname, level = acc.uid, acc.nickname, acc.level
                break
    if uid is None:
        raise ValueError("账号下无崩铁角色（无法解析 UID）")

    if transport.available():
        # Chrome 指纹传输（风控应对件——TLS/H2 指纹维度，见 transport.py 头注）：
        # 端点/DS/模型仍归 genshin.py，只换传输层。凭证与设备头复用 _make_client
        # 的同一批读取（keyring 多读一次可忽略——拉取本就不是高频路径）。
        logger.info("记录接口传输：curl_cffi（Chrome 指纹）")
        ltuid = _read_secret("HSR_NOUS_HOYO_LTUID")
        ltoken = _read_secret("HSR_NOUS_HOYO_LTOKEN")
        detail, notes, challenge = transport.fetch_starrail_records(
            int(uid), {"ltuid": ltuid, "ltoken": ltoken},
            device_id=client.custom_headers.get("x-rpc-device_id"),
            device_fp=client.custom_headers.get("x-rpc-device_fp"),
            region=_resolve_region())
    else:
        logger.info("记录接口传输：genshin.py 原生 aiohttp（未装 curl-cffi 的回退）")
        detail = await client.get_starrail_characters(uid=uid)
        notes = await client.get_starrail_notes(uid=uid)
        challenge = await client.get_starrail_challenge(uid=uid)

    characters = tuple(_to_character(c) for c in detail.avatar_list)
    moc: Tuple[MoCRecord, ...] = ()
    if challenge.has_data:
        moc = (MoCRecord(
            season=int(challenge.season), name=challenge.name,
            stars=int(challenge.total_stars), max_floor=int(challenge.max_floor),
            total_battles=int(challenge.total_battles),
        ),)
    return AccountSnapshot(
        uid=str(uid), nickname=nickname, level=level,
        trailblaze_power=int(notes.current_stamina),
        characters=characters, moc_records=moc,
    )


def fetch_account_snapshot() -> Optional[AccountSnapshot]:
    """一次拉取账号完整快照。未配置或任何失败 → None（不抛、不重试、不脑补）。

    失败可观测（2026-10-17）：返回 None 前按原因记日志——静默降级对手是正确
    纪律，但人无感地永远退回手动 build.yaml；看到 warning 即知走 §1.8 哪步。
    """
    try:
        client = _make_client()
        if client is None:
            return None
        return asyncio.run(_fetch_snapshot(client))
    except genshin.errors.GeetestError:
        logger.warning(
            "米游社风控（Geetest 10035）：记录类接口暂不可用——处理顺序见 "
            "docs/integrations.md §1.8（自动设备身份已尽力，仍触发则换网络/时段）")
        return None
    except genshin.errors.InvalidCookies:
        logger.warning(
            "米游社凭证失效（ltoken 过期或被吊销）：重新获取——"
            "python -m hsr_nous.account.login（扫码）或按 docs/integrations.md §1.2 手动填 Cookie")
        return None
    except Exception as e:  # noqa: BLE001 — 静默纪律:端点漂移/网络任何失败都返回 None
        logger.warning("账号快照拉取失败（%s: %s）", type(e).__name__, e)
        return None
