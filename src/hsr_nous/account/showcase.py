"""角色展柜快照（api.mihomo.me 公共聚合）——记录接口风控降级替代源.

定位（docs/integrations.md §1.9）：`fetch_account_snapshot`（米游社记录接口）撞风控
（Geetest 10035——出口 IP 维度，§1.8 变量排除实证链）时的公开面替代。展柜数据是
玩家在游戏内**主动公开**的角色（含遗器/光锥/行迹全件），无需登录、不经米游社
风控——微信小程序（星铁工坊等）同源。

代价（与记录接口快照的差异，消费方须知情）：
- 仅展柜角色——游戏上限 8 个，且玩家可在游戏内关闭公开（is_display=False →
  本件返回 None，不脑补）；
- 无开拓力/忘却之庭（快照对应字段为 0/空）；
- 星魂只给已解锁数量（rank），无星魂名列表；忆灵标记恒 False；
- 第三方服务依赖（mihomo.me 可用性/口径漂移——词表映射见 _MIHOMO_PATHS，
  未知命途原样透传并告警）。

同一 AccountSnapshot 形状——上游消费方对来源无感（测试钉形状一致）。
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Dict, Mapping, Optional

from hsr_nous.account.client import _panel_value
from hsr_nous.account.models import (
    AccountCharacter,
    AccountLightCone,
    AccountRelic,
    AccountSnapshot,
    RelicStat,
)

logger = logging.getLogger(__name__)

_API = "https://api.mihomo.me/sr_info_parsed/{uid}?lang=cn"

#: mihomo path.id（游戏内部开发名）→ AccountCharacter.path 词表（= genshin 枚举串，
#: adapter 侧 lower 即 canonical key）。映射依据=mihomo 实读值（2026-10-17 实证
#: "Memory"→记忆）；未知命途不脑补，原样透传 + 告警（词表扩员时此处补行）。
_MIHOMO_PATHS = {
    "Warrior": "Destruction", "Knight": "Preservation", "Priest": "Abundance",
    "Hunt": "Hunt", "Mage": "Erudition", "Shaman": "Harmony",
    "Warlock": "Nihility", "Memory": "Remembrance",
    "Elation": "Elation",   # 欢愉实读值=id 即枚举串（非开发名，2026-10-17 实读在案）
}


def _get_showcase_json(uid: str, timeout: float = 20.0) -> Mapping[str, Any]:
    """拉取展柜原始 JSON（独立成函数=测试接缝；网络/解析失败抛，调用方降级）."""
    req = urllib.request.Request(
        _API.format(uid=uid), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _map_path(path_id: str) -> str:
    if path_id in _MIHOMO_PATHS:
        return _MIHOMO_PATHS[path_id]
    logger.warning("mihomo 未知命途 %r——词表透传，account_adapter 可能拒识", path_id)
    return path_id


def _relic_stat(a: Mapping[str, Any]) -> RelicStat:
    """affix → RelicStat（保留原始属性码 type 与原始 value，不用本地化 display）."""
    return RelicStat(name=str(a.get("type") or a.get("name", "")),
                     value=str(a.get("value", a.get("display", ""))),
                     times=int(a.get("count") or a.get("times") or 1))


def _to_relic(r: Mapping[str, Any]) -> AccountRelic:
    return AccountRelic(
        id=str(r.get("id", "")), name=str(r.get("name", "")),
        pos=int(r.get("type") or 0),          # mihomo 槽位键名=type（1-6，含位面）
        level=int(r.get("level") or 0),
        rarity=int(r.get("rarity") or 0),
        set_id=str(r.get("set_id") or ""),
        main=_relic_stat(r["main_affix"]) if r.get("main_affix") else None,
        subs=tuple(_relic_stat(a) for a in (r.get("sub_affix") or [])),
    )


def _to_light_cone(lc: Optional[Mapping[str, Any]]) -> Optional[AccountLightCone]:
    if not lc:
        return None
    return AccountLightCone(
        id=str(lc.get("id", "")), name=str(lc.get("name", "")),
        level=int(lc.get("level") or 0), superimposition=int(lc.get("rank") or 1),
        rarity=int(lc.get("rarity") or 0),
    )


def _to_character(c: Mapping[str, Any]) -> AccountCharacter:
    props = c.get("properties") or []
    panel: Dict[str, float] = {}
    for p in props:
        try:
            panel[str(p.get("name", ""))] = _panel_value(str(p.get("display", "")))
        except (ValueError, KeyError):
            continue
    return AccountCharacter(
        id=str(c.get("id", "")),
        name=str(c.get("name", "")),
        level=int(c.get("level") or 0),
        eidolon=int(c.get("rank") or 0),
        unlocked_eidolons=(),   # mihomo 只给已解锁数量，无星魂名列表（不脑补）
        path=_map_path(str((c.get("path") or {}).get("id", ""))),
        element=str((c.get("element") or {}).get("id", "")),
        skill_levels={str(s.get("id")): int(s.get("level") or 0)
                      for s in (c.get("skills") or []) if s.get("id")},
        light_cone=_to_light_cone(c.get("light_cone")),
        relics=tuple(_to_relic(r) for r in (c.get("relics") or [])),
        panel=panel,
        has_memosprite=False,   # 展柜数据无忆灵字段（不脑补——记忆命途亦恒 False）
    )


def fetch_showcase_snapshot(uid: str, timeout: float = 20.0) -> Optional[AccountSnapshot]:
    """按 UID 拉展柜快照。玩家未公开展柜/服务不可达 → None（不抛、不脑补）."""
    uid = str(uid).strip()
    try:
        data = _get_showcase_json(uid, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — 网络/JSON/第三方漂移降级 None
        logger.warning("展柜数据拉取失败（%s: %s）", type(e).__name__, e)
        return None
    player = data.get("player") or {}
    if player.get("is_display") is False:
        logger.info("UID %s 未公开角色展柜（游戏内设置）——展柜快照不可用", uid)
        return None
    characters = tuple(_to_character(c) for c in (data.get("characters") or []))
    return AccountSnapshot(
        uid=str(player.get("uid") or uid),
        nickname=str(player.get("nickname", "")),
        level=int(player.get("level") or 0),
        trailblaze_power=0,          # 展柜数据无实时体力（§1.9 差异表）
        characters=characters,
        moc_records=(),              # 无忘却之庭
    )
