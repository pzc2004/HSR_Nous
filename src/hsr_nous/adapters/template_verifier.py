"""模板回读校验器：模板 YAML ↔ 原始数据 逐字段独立比对（正确性的确定性验证）.

与 template_generator 对称但**独立**：不 import 生成器的映射表/正则——
生成器写错时校验器不能跟着错。映射表双份维护是有意的互相盯梢。

每个 verify_* 返回不一致清单（List[str]），空 = 通过；异常（数据缺失）原样上抛。
"""
from __future__ import annotations

import glob
from typing import Any, Dict, List

import yaml

from hsr_nous.pipeline import calc_character_stats, load_character_skills_merged

# 独立映射表（与 generator 双份维护，互相盯梢；改一边必须同步另一边并说明理由）
_V_TYPE_MAP = {"Normal": "basic", "BPSkill": "skill", "Ultra": "ultimate"}
_V_EFFECT_MAP = {
    "SingleAttack": "single", "Blast": "blast", "AoEAttack": "aoe", "Bounce": "bounce",
    "Enhance": "self", "Support": "ally_single", "Restore": "ally_single",
    "Defence": "ally_single", "Impair": "single", "Summon": "self",
}
_V_PROP_MAP = {
    "AttackAddedRatio": "atk_pct", "DefenceAddedRatio": "def_pct", "HPAddedRatio": "hp_pct",
    "SpeedAddedRatio": "spd_pct", "CriticalChanceBase": "crit_rate",
    "CriticalDamageBase": "crit_dmg", "StatusProbabilityBase": "effect_hit",
    "StatusResistanceBase": "effect_res", "BreakDamageAddedRatioBase": "break_effect",
    "SPRatioBase": "energy_regen", "HealRatioBase": "dmg_heal_bonus",
    "PhysicalAddedRatio": "dmg_physical", "FireAddedRatio": "dmg_fire",
    "IceAddedRatio": "dmg_ice", "ThunderAddedRatio": "dmg_thunder",
    "WindAddedRatio": "dmg_wind", "QuantumAddedRatio": "dmg_quantum",
    "ImaginaryAddedRatio": "dmg_imaginary", "ElationDamageAddedRatioBase": "dmg_elation",
}
_NON_ATTACK_EFFECTS = {"Enhance", "Support", "Restore", "Defence", "Summon"}

_TEMPLATES_ROOT = "data/sim_templates"


def _load(kind: str, ref: str) -> Dict[str, Any]:
    hits = glob.glob(f"{_TEMPLATES_ROOT}/{kind}/{ref}_*.yaml") or glob.glob(
        f"{_TEMPLATES_ROOT}/{kind}/{ref}.yaml")
    if not hits:
        raise FileNotFoundError(f"模板缺失：{kind}/{ref}")
    with open(hits[0], encoding="utf-8") as f:
        return yaml.safe_load(f)


def _close(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------

def verify_character_template(char_id: str, *, level: int = 80, lang: str = "cn") -> List[str]:
    """角色模板校验：面板/倍率/形态/削韧/回能/能量消耗 逐字段对原始数据."""
    diffs: List[str] = []
    tpl = _load("characters", char_id)
    base = calc_character_stats(char_id, level=level, lang=lang)
    for stat in ("hp", "atk", "def", "spd", "crit_rate", "crit_dmg"):
        if not _close(tpl["base_stats"].get(stat, 0), base.get(stat, 0)):
            diffs.append(f"base_stats.{stat}: 模板 {tpl['base_stats'].get(stat)} != 原始 {base.get(stat)}")

    merged = load_character_skills_merged(lang=lang)
    expected: Dict[str, Dict[str, Any]] = {}
    for sid, s in merged.items():
        if not sid.startswith(str(char_id)):
            continue
        atype = _V_TYPE_MAP.get(s.get("type", ""))
        if atype is None:
            continue
        expected[str(s.get("id"))] = s

    got = {a["action_id"]: a for a in tpl.get("actions", [])}
    for sid, s in expected.items():
        a = got.get(sid)
        if a is None:
            diffs.append(f"技能 {sid}（{s.get('name')}）模板缺失")
            continue
        effect = s.get("effect", "")
        want_tt = _V_EFFECT_MAP.get(effect, "single")
        if a.get("target_type") != want_tt:
            diffs.append(f"技能 {sid} target_type: 模板 {a.get('target_type')} != 期望 {want_tt}（effect={effect}）")
        params = s.get("params") or []
        if effect in _NON_ATTACK_EFFECTS:
            if a.get("scaling"):
                diffs.append(f"技能 {sid} 非攻击类（{effect}）但模板带 scaling")
            continue
        want_scaling = [{"atk": float(p[0])} for p in params if p]
        got_scaling = a.get("scaling") or []
        if len(got_scaling) != len(want_scaling):
            diffs.append(f"技能 {sid} scaling 长度: 模板 {len(got_scaling)} != 原始 {len(want_scaling)}")
        else:
            for i, (g, w) in enumerate(zip(got_scaling, want_scaling)):
                if not _close(g.get("atk", 0), w["atk"]):
                    diffs.append(f"技能 {sid} scaling[{i}]: 模板 {g.get('atk')} != 原始 {w['atk']}")
                    break
    return diffs


# ---------------------------------------------------------------------------
# 光锥
# ---------------------------------------------------------------------------

def verify_light_cone_template(lc_id: str, *, level: int = 80, lang: str = "cn") -> List[str]:
    """光锥模板校验：白值 + lookup 表内容（properties 语义列与 params 占位列的并集 == 原始参数）."""
    from hsr_nous.pipeline import calc_light_cone_stats, get_light_cone_ranks

    diffs: List[str] = []
    tpl = _load("light_cones", lc_id)
    base = calc_light_cone_stats(lc_id, level=level, lang=lang)
    for stat in ("hp", "atk", "def"):
        if not _close(tpl["base_stats"].get(stat, 0), base.get(stat, 0)):
            diffs.append(f"base_stats.{stat}: 模板 {tpl['base_stats'].get(stat)} != 原始 {base.get(stat)}")

    ranks = get_light_cone_ranks(lc_id, lang=lang) or {}
    params = ranks.get("params") or []
    tables = tpl.get("lookup_tables") or {}

    # properties → 语义列逐档对轴
    prop_cols: Dict[str, List[float]] = {}
    for s_idx, s_props in enumerate(ranks.get("properties") or []):
        for p in s_props:
            stat = _V_PROP_MAP.get(p.get("type", ""))
            if stat is None:
                continue
            prop_cols.setdefault(stat, [0.0] * len(params))
            if s_idx < len(params):
                prop_cols[stat][s_idx] = float(p.get("value", 0.0))
    for stat, want in prop_cols.items():
        got = tables.get(stat)
        if got is None:
            diffs.append(f"lookup_tables 缺 properties 语义列 {stat}")
        elif len(got) != len(want) or any(not _close(g, w) for g, w in zip(got, want)):
            diffs.append(f"lookup_tables.{stat}: 模板 {got} != 原始 {want}")

    # params 占位列（properties 已覆盖列与全 0 列豁免）：并集完整性
    for i in range(max((len(p) for p in params), default=0)):
        col = [float(p[i]) if i < len(p) else 0.0 for p in params]
        if all(v == 0.0 for v in col):
            continue
        covered = any(
            all(_close(c, w) for c, w in zip(col, want)) for want in prop_cols.values()
        )
        if covered:
            continue
        name = f"param_{i + 1}"
        got = tables.get(name)
        if got is None:
            diffs.append(f"lookup_tables 缺占位列 {name}（params 第 {i + 1} 列）")
        elif any(not _close(g, w) for g, w in zip(got, col)):
            diffs.append(f"lookup_tables.{name}: 模板 {got} != 原始 {col}")
    return diffs


# ---------------------------------------------------------------------------
# 遗器
# ---------------------------------------------------------------------------

def verify_relic_set_template(set_id: str, *, lang: str = "cn") -> List[str]:
    """遗器模板校验：2pc/4pc stat_effects == 原始 properties 映射."""
    from hsr_nous.pipeline import get_relic_set

    diffs: List[str] = []
    tpl = _load("relics", set_id)
    raw = get_relic_set(set_id, lang=lang)
    props = raw.get("properties") or []
    for idx, pc_key in ((0, "set_2pc"), (1, "set_4pc")):
        want: Dict[str, float] = {}
        if idx < len(props):
            for p in props[idx]:
                stat = _V_PROP_MAP.get(p.get("type", ""))
                if stat:
                    want[stat] = want.get(stat, 0.0) + float(p.get("value", 0.0))
        got = (tpl.get(pc_key) or {}).get("stat_effects") or {}
        if set(got) != set(want):
            diffs.append(f"{pc_key} stat_effects 键集: 模板 {sorted(got)} != 原始 {sorted(want)}")
            continue
        for stat, w in want.items():
            if not _close(got[stat], w):
                diffs.append(f"{pc_key}.{stat}: 模板 {got[stat]} != 原始 {w}")
    return diffs


# ---------------------------------------------------------------------------
# 敌人
# ---------------------------------------------------------------------------

def verify_enemy_template(enemy_id: str, *, level: int = 80) -> List[str]:
    """敌人模板校验：面板 == calc_enemy_stats 重算（公式链在 pipeline 层，独立于此）."""
    from hsr_nous.pipeline.stages_loader import calc_enemy_stats

    diffs: List[str] = []
    tpl = _load("enemies", enemy_id)
    stats = calc_enemy_stats(enemy_id, level)
    if stats is None:
        return [f"calc_enemy_stats 返回 None（{enemy_id}）"]
    base = tpl.get("base_stats", {})
    for stat, key in (("hp", "hp"), ("atk", "atk"), ("def", "def_"), ("spd", "spd"),
                      ("max_toughness", "max_toughness"), ("effect_res", "effect_res")):
        if not _close(base.get(stat, 0), stats[key], tol=1e-6):
            diffs.append(f"base_stats.{stat}: 模板 {base.get(stat)} != 重算 {stats[key]}")
    if sorted(tpl.get("weakness") or []) != sorted(stats["weakness"]):
        diffs.append(f"weakness: 模板 {tpl.get('weakness')} != 重算 {stats['weakness']}")
    return diffs
