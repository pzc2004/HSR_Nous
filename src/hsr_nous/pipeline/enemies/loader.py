"""enemies 域统一查询（turnbasedgamedata 五表口径）.

替代关系（P2 对拍基准，tests/test_enemy_source_parity.py 钉）：
- `calc_enemy_stats`/`get_enemy_detail`/`list_monster_ids` 对齐 stages.loader 现 hakushin
  链的输出形态（键名/单位/语义逐键一致），消费方切源零改动；
- 两处**有意差异**（迁移即修复，对拍表显式登记）：tbgd 的实例级/模板级
  SpeedModifyValue/StanceModifyValue 平加项计入 spd/max_toughness——hakushin
  monstervalue 无此字段，现公式链漏算（474 件实例 + 16/12 件模板在案）。

tbgd 净增量（现源完全没有的）：技能倍率 ParamList/削韧 SPHitBase/AI_CD/AI_ICD
（`get_enemy_skills`）、模板默认 AI + 实例 AI 覆写（`get_enemy_ai`）、DebuffResist/
SummonIDList/CustomValueTags（行原样可查）。

命名口径：MonsterName/SkillName 是 TextMap hash（本地无 TextMap）——名字源维持
hakushin monster.json（en/zh 官方名，get_monster_meta 不变，P3 切源时重审）。

数据加载：五表全量 lru_cache（表不大，整表驻留比按行查快；clear_data_cache 一并清）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Dict, List, Optional

from hsr_nous.pipeline import paths as _paths

#: tbgd 数值包装形态（{"Value": x}）与裸值混在——统一解包；None/缺键 → None
def _v(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("Value")
        if raw is None:
            return None
    return float(raw)


@lru_cache(maxsize=None)
def _load_table(name: str) -> Any:
    return json.loads(_paths.tbgd_file(name).read_text(encoding="utf-8"))


def clear_data_cache() -> None:
    """数据缓存失效钩子（update 落盘后调用——同 build.loader 先例）."""
    _load_table.cache_clear()
    _instance_map.cache_clear()
    _template_map.cache_clear()
    _skill_map.cache_clear()
    _elite_map.cache_clear()
    _hard_map.cache_clear()


@lru_cache(maxsize=1)
def _instance_map() -> Dict[str, Dict[str, Any]]:
    """MonsterConfig → {MonsterID: 行}（实例层：修正系数/弱点/抗性/技能表/AI 覆写）."""
    return {str(r["MonsterID"]): r for r in _load_table("MonsterConfig.json")}


@lru_cache(maxsize=1)
def _template_map() -> Dict[str, Dict[str, Any]]:
    """MonsterTemplateConfig → {MonsterTemplateID: 行}（模板层：base 值/Rank/默认 AI）."""
    return {str(r["MonsterTemplateID"]): r for r in _load_table("MonsterTemplateConfig.json")}


@lru_cache(maxsize=1)
def _skill_map() -> Dict[str, Dict[str, Any]]:
    return {str(r["SkillID"]): r for r in _load_table("MonsterSkillConfig.json")}


@lru_cache(maxsize=1)
def _elite_map() -> Dict[int, Dict[str, Any]]:
    return {int(r["EliteGroup"]): r for r in _load_table("EliteGroup.json")}


@lru_cache(maxsize=1)
def _hard_map() -> Dict[int, Dict[int, Dict[str, Any]]]:
    """HardLevelGroup → {group: {level: 行}}（等级钳级在消费侧）."""
    out: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for r in _load_table("HardLevelGroup.json"):
        out.setdefault(int(r["HardLevelGroup"]), {})[int(r["Level"])] = r
    return out


def list_monster_ids() -> List[str]:
    """怪物模板花名册（MonsterTemplateConfig 顶层 id——与 hakushin monstervalue
    顶层 632 键一一对应，对拍表钉同集）."""
    return sorted(_template_map().keys())


def get_enemy_detail(enemy_id: str) -> Optional[Dict[str, Any]]:
    """按 ID 查怪物实例 + 模板合并视图（{_source: "tbgd", ...实例行, "_template": 模板行}）.

    实例或模板任缺 → None（不静默回退——缺数据即缺数据，见「严肃模拟器」原则）。
    """
    inst = _instance_map().get(str(enemy_id))
    if inst is None:
        return None
    tpl = _template_map().get(str(inst.get("MonsterTemplateID")))
    if tpl is None:
        return None
    return {"_source": "tbgd", **inst, "_template": tpl}


# 效果抗性等级加算（mechanics 01 §1.2：Lv.51-75 每级 +0.4%，上限 +10%）
#——与 stages/loader._effect_res_bonus 同式镜像（P3 切源后 stages 侧退役，此处为正典）
def _effect_res_bonus(level: int) -> float:
    return min(max(level - 50, 0) * 0.004, 0.10)


def calc_enemy_stats(
    enemy_id: str,
    level: int,
) -> Optional[Dict[str, Any]]:
    """计算怪物在指定等级下的面板（tbgd 五表口径，公式链与 hakushin 版逐键同构）.

    公式链（系数全在 tbgd 五表，无外部假设）：
        面板 = base(模板) × HardLevelGroup[group, level].XxxRatio
                   × EliteGroup[elite].XxxRatio × 实例.XxxModifyRatio
        spd/max_toughness 另加 实例+模板 的 Speed/StanceModifyValue 平加项（有意差异，
        见模块 docstring）；效果抗性 = StatusResistanceBase + 等级加算（Lv.51-75 上限 +10%）。
    等级超出 HardLevelGroup 表内范围时钳到表内最大级（同 hakushin 版语义）。

    返回 {level, hp, atk, def_, spd, max_toughness, effect_res, weakness,
          _level_clamped, _missing_bases}——键名与 hakushin 版逐键一致（消费方切源零改动）；
    怪物不存在返回 None。
    """
    detail = get_enemy_detail(enemy_id)
    if detail is None:
        return None
    tpl = detail["_template"]

    group = _hard_map().get(int(detail.get("HardLevelGroup") or 1))
    if not group:
        return None
    clamped_level = min(level, max(group))
    hard = group[clamped_level]
    elite = _elite_map().get(int(detail.get("EliteGroup") or 1), {})

    def _ratio(table: Dict[str, Any], key: str) -> float:
        return _v(table.get(key)) or 1.0

    def _chain(base: Optional[float], ratio_key: str, modify_key: str) -> float:
        return (float(base or 0.0)  # None base = 该属性不存在（如无韧性条怪）
                * _ratio(hard, ratio_key)
                * _ratio(elite, ratio_key)
                * (_v(detail.get(modify_key)) or 1.0))

    _BASE_KEYS = ("AttackBase", "DefenceBase", "HPBase", "SpeedBase", "StanceBase")
    bases = {k: _v(tpl.get(k)) for k in _BASE_KEYS}
    missing = [k for k in _BASE_KEYS if bases[k] is None]

    spd = _chain(bases["SpeedBase"], "SpeedRatio", "SpeedModifyRatio")
    spd += (_v(detail.get("SpeedModifyValue")) or 0.0) + (_v(tpl.get("SpeedModifyValue")) or 0.0)
    max_toughness = _chain(bases["StanceBase"], "StanceRatio", "StanceModifyRatio")
    max_toughness += (_v(detail.get("StanceModifyValue")) or 0.0) + (_v(tpl.get("StanceModifyValue")) or 0.0)
    return {
        "level": level,
        "hp": _chain(bases["HPBase"], "HPRatio", "HPModifyRatio"),
        "atk": _chain(bases["AttackBase"], "AttackRatio", "AttackModifyRatio"),
        "def_": _chain(bases["DefenceBase"], "DefenceRatio", "DefenceModifyRatio"),
        "spd": spd,
        "max_toughness": max_toughness,
        "effect_res": float(_v(tpl.get("StatusResistanceBase")) or 0.0)
        + _effect_res_bonus(level),
        "weakness": [w.lower() for w in (detail.get("StanceWeakList") or [])],
        "_level_clamped": clamped_level != level,
        "_missing_bases": missing,
    }


def get_enemy_skills(enemy_id: str) -> List[Dict[str, Any]]:
    """怪物技能清单（MonsterConfig.SkillList join MonsterSkillConfig）——tbgd 净增量.

    每技能：{skill_id, trigger_key, type_desc, damage_type, attack_type,
             sp_hit_base(削韧), delay_ratio(行动延迟), ai_cd, ai_icd,
             param_list(倍率), phase_list, modifier_list}；
    名字/描述是 TextMap hash 不收录（命名口径见模块 docstring）。
    怪物不存在 → []；技能表空 → []。
    """
    inst = _instance_map().get(str(enemy_id))
    if inst is None:
        return []
    out: List[Dict[str, Any]] = []
    for sid in inst.get("SkillList") or []:
        sk = _skill_map().get(str(sid))
        if sk is None:
            out.append({"skill_id": str(sid), "_missing_in_skill_config": True})
            continue
        out.append({
            "skill_id": str(sid),
            "trigger_key": sk.get("SkillTriggerKey"),
            "type_desc": sk.get("SkillTypeDesc"),
            "damage_type": (sk.get("DamageType") or None),
            "attack_type": sk.get("AttackType"),
            "sp_hit_base": _v(sk.get("SPHitBase")),
            "delay_ratio": _v(sk.get("DelayRatio")),
            "ai_cd": _v(sk.get("AI_CD")),
            "ai_icd": _v(sk.get("AI_ICD")),
            "param_list": [_v(p) for p in (sk.get("ParamList") or [])],
            "phase_list": sk.get("PhaseList") or [],
            "modifier_list": sk.get("ModifierList") or [],
        })
    return out


def get_enemy_ai(enemy_id: str) -> Optional[Dict[str, Any]]:
    """怪物 AI 行为（模板默认 + 实例覆写）——tbgd 净增量.

    返回 {ai_path(模板默认), ai_path_override(实例覆写),
          skill_sequence(模板默认出招循环), skill_sequence_override(实例覆写)}；
    AISkillSequence 元素是 Unity 混淆键单键 dict（值=SkillID），解为裸 id 表；
    怪物不存在 → None。
    """
    detail = get_enemy_detail(enemy_id)
    if detail is None:
        return None
    tpl = detail["_template"]

    def _seq(raw: Any) -> List[str]:
        out: List[str] = []
        for item in raw or []:
            if isinstance(item, dict):
                out.extend(str(v) for v in item.values())
            else:
                out.append(str(item))
        return out

    return {
        "ai_path": tpl.get("AIPath"),
        "ai_path_override": detail.get("OverrideAIPath") or None,
        "skill_sequence": _seq(tpl.get("AISkillSequence")),
        "skill_sequence_override": _seq(detail.get("OverrideAISkillSequence")),
    }
