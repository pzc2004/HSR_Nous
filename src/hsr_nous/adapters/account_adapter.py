"""账号 → sim_schema 桥（防腐层）：AccountCharacter → build.yaml 成员字典.

唯一认识两侧的层：account（领域事实）× build schema（`_MEMBER_KEYS` 作者面）。
词条名映射 = `template_generator._PROP_MAP`（pct/特殊族单一事实源）+ flat 四项补充；
产出形状由 tests/test_account_snapshot.py 对拍 `_MEMBER_KEYS`/`_AFFIX_FIELD` 钉死——
schema 改动当场红，不静默漂移。

纪律：模板不存在（`data/library/<kind>/<id>_*.yaml`）→ member=None；词表外词条/未知
技能槽 → 收进 dropped（响亮记账，不静默吞——静默吞=幻觉温床）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hsr_nous.account.models import AccountCharacter, RelicStat
from hsr_nous.adapters.template_generator import _PROP_MAP
from hsr_nous.pipeline import paths

#: API 词条名（property_name_relic）→ DSL 词条 id
_PROP_TO_AFFIX: Dict[str, str] = {
    **_PROP_MAP,
    "HPDelta": "hp", "AttackDelta": "atk", "DefenceDelta": "def_", "SpeedDelta": "spd",
}

#: API 槽位 pos（1-6）→ DSL 槽位词表（sim_schema/docs/06_relics.md）
_POS_TO_SLOT = ("head", "hands", "body", "feet", "sphere", "rope")

#: API 技能 point_id 尾两位 → DSL 技能槽词表（模板 level_key 同词表）
_POINT_SUFFIX_TO_SLOT = {
    "01": "basic", "02": "skill", "03": "ultimate", "04": "talent", "07": "technique",
}


def _affix_id(stat: RelicStat) -> Optional[str]:
    """API 词条名 → DSL 词条 id；词表外 → None（调用方记 dropped，不脑补）."""
    return _PROP_TO_AFFIX.get(stat.name)


def _relics_member(ch: AccountCharacter, dropped: List[str]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for relic in ch.relics:
        if not 1 <= relic.pos <= 6:
            dropped.append(f"relic pos={relic.pos} 越界")
            continue
        slot = _POS_TO_SLOT[relic.pos - 1]
        entry: Dict[str, Any] = {}
        if relic.main is not None:
            mid = _affix_id(relic.main)
            if mid is None:
                dropped.append(f"{slot} 主词条 {relic.main.name!r}")
            else:
                entry["main"] = mid
        subs: Dict[str, int] = {}
        for s in relic.subs:
            sid = _affix_id(s)
            if sid is None:
                dropped.append(f"{slot} 副词条 {s.name!r}")
                continue
            subs[sid] = subs.get(sid, 0) + s.times
        entry["subs"] = subs
        out[slot] = entry
    return out


def _skill_levels(ch: AccountCharacter, dropped: List[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for point_id, level in ch.skill_levels.items():
        slot = _POINT_SUFFIX_TO_SLOT.get(str(point_id)[-2:])
        if slot is None:
            dropped.append(f"技能点 {point_id}")
            continue
        out[slot] = level
    return out


def account_character_to_member(
    ch: AccountCharacter, *, library_root: Optional[Path] = None
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """账号角色 → (build.yaml 成员字典, dropped 响亮记账).

    角色模板不存在（`data/library/characters/<id>_*.yaml`）→ (None, dropped)——不脑补。
    """
    root = Path(library_root) if library_root is not None else paths.library_dir()
    dropped: List[str] = []
    if not list(root.glob(f"characters/{ch.id}_*.yaml")):
        return None, [f"角色模板缺失 {ch.id}"]

    member: Dict[str, Any] = {
        "character_template": ch.id,
        "level": ch.level,
        "eidolon": ch.eidolon,
    }
    levels = _skill_levels(ch, dropped)
    if levels:
        member["skill_levels"] = levels
    if ch.light_cone is not None:
        lc = ch.light_cone
        if not list(root.glob(f"light_cones/{lc.id}_*.yaml")):
            dropped.append(f"光锥模板缺失 {lc.id}")
        else:
            member["light_cone_template"] = lc.id
            member["light_cone"] = {"superimposition": lc.superimposition}
    relics = _relics_member(ch, dropped)
    if relics:
        member["relics"] = relics
    return member, dropped
