"""模板生成器：pipeline 游戏数据 → per-entity DSL 模板（data/sim_templates/characters/）.

v0.5 范围：角色模板（面板 + 普攻/战技/终结技 atk 倍率 + 默认削韧/回能）。
天赋/行迹/星魂机制、HP/DEF 倍率角色特判后置（desc 含"生命/防御"时打 scaling_note 标人工）。
v0.7 起 target_type / 副目标倍率忠于原始数据：effect 字段定形态，
desc 的"相邻目标…#N[i]%"占位符定副倍率位置（决策卡 #18 补注）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# StarRailRes type → sim action_type
_TYPE_MAP = {"Normal": "basic", "BPSkill": "skill", "Ultra": "ultimate"}

# 原始数据 effect 字段 → target_type（忠于原始数据的形态声明）
_EFFECT_MAP = {
    "SingleAttack": "single",
    "Blast": "blast",
    "AoEAttack": "aoe",
    "Bounce": "bounce",
    "Enhance": "self",
    "Support": "ally_single",
    "Restore": "ally_single",
    "Defence": "ally_single",
    "Impair": "single",   # 妨害类无 scaling 不进伤害结算，形态占位
    "Summon": "self",
}

# 默认削韧（公式层打击方式默认值，mechanics 削韧表）
_TOUGHNESS_DEFAULT = {"basic": 10, "skill": 20, "ultimate": 30}

# 默认回能
_ENERGY_GAIN = {"basic": 20, "skill": 30, "ultimate": 5}

# desc 中"相邻目标…#N[i]%"占位符 → params[N-1] 即副目标倍率
_BLAST_RE = re.compile(r"相邻目标[^#]{0,30}?#(\d+)\[i\]")

# 原始数据 properties type → 面板 stat（结构化字段直映射，绕开 desc 正则）
_PROP_MAP = {
    "AttackAddedRatio": "atk_pct",
    "DefenceAddedRatio": "def_pct",
    "HPAddedRatio": "hp_pct",
    "SpeedAddedRatio": "spd_pct",
    "CriticalChanceBase": "crit_rate",
    "CriticalDamageBase": "crit_dmg",
    "StatusProbabilityBase": "effect_hit",
    "StatusResistanceBase": "effect_res",
    "BreakDamageAddedRatioBase": "break_effect",
    "SPRatioBase": "energy_regen",
    "HealRatioBase": "dmg_heal_bonus",
    "PhysicalAddedRatio": "dmg_physical",
    "FireAddedRatio": "dmg_fire",
    "IceAddedRatio": "dmg_ice",
    "ThunderAddedRatio": "dmg_thunder",
    "WindAddedRatio": "dmg_wind",
    "QuantumAddedRatio": "dmg_quantum",
    "ImaginaryAddedRatio": "dmg_imaginary",
    "ElationDamageAddedRatioBase": "dmg_elation",
}


def _internal_element(raw: str) -> str:
    return raw.lower() if raw else ""


def generate_character_template(
    char_id: str,
    *,
    level: int = 80,
    lang: str = "cn",
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 数据 → 角色模板 dict（build-compiler 认识的形式）.

    Raises: ValueError（角色不存在）; KeyError（技能数据缺失）.
    """
    from hsr_nous.pipeline import calc_character_stats, load_character_skills_merged, load_characters

    chars = load_characters(data_dir=data_dir, lang=lang)
    raw = chars.get(str(char_id)) if isinstance(chars, dict) else None
    if raw is None:
        raise ValueError(f"角色 {char_id} 不存在于本地数据（lang={lang}）")

    base = calc_character_stats(str(char_id), level=level, lang=lang)
    element = _internal_element(raw.get("element", ""))
    raw_sp = raw.get("max_sp")
    max_sp = float(raw_sp) if raw_sp is not None else 0.0
    sp_note = None
    if raw_sp is None:
        # 特殊充能角色（遐蝶类新蕊资源）：非常规能量，max_energy 置 0 + 标人工
        sp_note = "max_sp 为 null：特殊充能角色（新蕊类），能量机制待人工"

    merged = load_character_skills_merged(data_dir=data_dir, lang=lang)
    actions: List[Dict[str, Any]] = []
    scaling_notes: List[str] = []
    if sp_note:
        scaling_notes.append(sp_note)
    for sid, s in merged.items():
        if not sid.startswith(str(char_id)):
            continue
        atype = _TYPE_MAP.get(s.get("type", ""))
        if atype is None:
            continue  # Talent/Maze/MazeNormal 后置
        params = s.get("params") or []
        scaling: List[Dict[str, float]] = []
        for lvl_params in params:
            if not lvl_params:
                continue
            scaling.append({"atk": float(lvl_params[0])})
        desc = s.get("desc", "") or ""
        if "生命上限" in desc or "生命值" in desc:
            scaling_notes.append(f"{s.get('name')}：疑似 HP 倍率（desc 含生命），当前按 atk 生成，待人工")
        if "防御" in desc:
            scaling_notes.append(f"{s.get('name')}：疑似 DEF 倍率（desc 含防御），当前按 atk 生成，待人工")
        target_type = _EFFECT_MAP.get(s.get("effect", ""), "single")
        action: Dict[str, Any] = {
            "action_id": str(s.get("id")),
            "name": s.get("name", ""),
            "action_type": atype,
            "target_type": target_type,
            "damage_type": element,
            "scaling": scaling,
            "energy_cost": int(max_sp) if atype == "ultimate" else 0,
            "energy_gain": _ENERGY_GAIN[atype],
            "toughness_dmg": _TOUGHNESS_DEFAULT[atype],
        }
        if s.get("effect") in ("Enhance", "Support", "Restore", "Defence", "Summon"):
            # 非攻击类：params[0] 不是伤害倍率（是 buff 数值/持续等），清空防误进伤害结算
            action["scaling"] = []
            action["damage_type"] = None
            action["toughness_dmg"] = 0
        if target_type == "blast":
            # 副目标倍率：desc"相邻目标…#N[i]%"占位符 → params[N-1]，照抄按等级数组
            m = _BLAST_RE.search(desc)
            if m and int(m.group(1)) >= 2:
                idx = int(m.group(1)) - 1
                blast_scaling = [
                    {"atk": float(p[idx])} for p in params if len(p) > idx
                ]
                if blast_scaling:
                    action["scaling_blast"] = blast_scaling
            else:
                scaling_notes.append(
                    f"{s.get('name')}：Blast 但 desc 未解析到相邻目标倍率占位符，"
                    "副目标暂同主倍率，待人工"
                )
        actions.append(action)

    template: Dict[str, Any] = {
        "actor_id": str(char_id),
        "name": raw.get("name", str(char_id)),
        "level": level,
        "base_stats": {
            "hp": base.get("hp", 0.0),
            "atk": base.get("atk", 0.0),
            "def": base.get("def", 0.0),
            "spd": base.get("spd", 100.0),
            "crit_rate": base.get("crit_rate", 0.05),
            "crit_dmg": base.get("crit_dmg", 0.5),
            "max_energy": max_sp,
        },
        "actions": actions,
    }
    if scaling_notes:
        template["scaling_notes"] = scaling_notes
    return template


def write_character_template(
    char_id: str,
    *,
    out_dir: str = "data/sim_templates/characters",
    level: int = 80,
    lang: str = "cn",
) -> str:
    """生成并写盘，返回文件路径."""
    tpl = generate_character_template(char_id, level=level, lang=lang)
    safe_name = tpl["name"].replace("•", "_").replace("·", "_").replace("/", "_")
    path = Path(out_dir) / f"{char_id}_{safe_name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 角色模板：{tpl['name']}（{char_id}）——由 adapters/template_generator 生成，勿手改\n")
        yaml.safe_dump(tpl, f, allow_unicode=True, sort_keys=False)
    return str(path)


# ---------------------------------------------------------------------------
# 光锥模板（v1 骨架：白值 + 叠影 lookup 表 + bindings；机制 effects 待 stat 语义钉死后批量）
# ---------------------------------------------------------------------------

def generate_light_cone_template(
    lc_id: str,
    *,
    level: int = 80,
    lang: str = "cn",
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 数据 → 光锥模板 dict（07_examples §7.2 形状）.

    v1 范围：白值三围 + params_by_superimposition 原样转置为 lookup_tables + variable_bindings。
    机制 effects 不生成（modifier 百分比 stat 写法待钉死）——desc 原文留存 notes 待收编。
    """
    from hsr_nous.pipeline import calc_light_cone_stats, get_light_cone, get_light_cone_ranks

    raw = get_light_cone(lc_id, lang=lang)
    if raw is None:
        raise ValueError(f"光锥 {lc_id} 不存在于本地数据（lang={lang}）")
    base = calc_light_cone_stats(lc_id, level=level, lang=lang)
    ranks = get_light_cone_ranks(lc_id, lang=lang) or {}

    params = ranks.get("params") or []  # S1~S5 × N 参数
    n_params = max((len(p) for p in params), default=0)
    lookup_tables: Dict[str, List[float]] = {}
    notes: List[str] = []

    # properties（结构化面板加成，S1~S5 × [{type,value}]）→ 语义命名列
    prop_cols: Dict[str, List[float]] = {}
    for s_idx, s_props in enumerate(ranks.get("properties") or []):
        for p in s_props:
            stat = _PROP_MAP.get(p.get("type", ""))
            if stat is None:
                notes.append(f"未知 properties type：{p.get('type')}（S{s_idx + 1}），待人工")
                continue
            col = prop_cols.setdefault(stat, [0.0] * len(params))
            if s_idx < len(col):
                col[s_idx] = float(p.get("value", 0.0))

    # params 列与 properties 列同值对齐：同值列并成语义名（不重复入库）
    used_param_cols: set[int] = set()
    for stat, col in prop_cols.items():
        match = next(
            (i for i in range(n_params)
             if all(abs((float(p[i]) if i < len(p) else 0.0) - col[s]) < 1e-9
                    for s, p in enumerate(params))),
            None,
        )
        if match is not None:
            used_param_cols.add(match)
        lookup_tables[stat] = col

    for i in range(n_params):
        if i in used_param_cols:
            continue
        col = [float(p[i]) if i < len(p) else 0.0 for p in params]
        # 整列全 0 的占位参数不入库（如 23042 的 param_3）
        if all(v == 0.0 for v in col):
            continue
        lookup_tables[f"param_{i + 1}"] = col

    variable_bindings = [
        f"self.{name} = lookup_table(\"{name}\", index=$build.light_cone.superimposition - 1)"
        for name in lookup_tables
    ]

    template: Dict[str, Any] = {
        "light_cone_id": str(lc_id),
        "name": raw.get("name", str(lc_id)),
        "rarity": raw.get("rarity"),
        "path": raw.get("path", ""),
        "base_stats": {
            "hp": base.get("hp", 0.0),
            "atk": base.get("atk", 0.0),
            "def": base.get("def", 0.0),
        },
    }
    if lookup_tables:
        template["lookup_tables"] = lookup_tables
        template["variable_bindings"] = variable_bindings
    mech_desc = (ranks.get("desc") or "").strip()
    if mech_desc:
        notes.append(f"机制 effects 未生成，待收编。desc：{mech_desc}")
    if notes:
        template["notes"] = notes
    return template


def write_light_cone_template(
    lc_id: str,
    *,
    out_dir: str = "data/sim_templates/light_cones",
    level: int = 80,
    lang: str = "cn",
) -> str:
    """生成并写盘，返回文件路径."""
    tpl = generate_light_cone_template(lc_id, level=level, lang=lang)
    safe_name = tpl["name"].replace("•", "_").replace("·", "_").replace("/", "_")
    path = Path(out_dir) / f"{lc_id}_{safe_name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 光锥模板：{tpl['name']}（{lc_id}）——由 adapters/template_generator 生成，勿手改\n")
        yaml.safe_dump(tpl, f, allow_unicode=True, sort_keys=False)
    return str(path)


# ---------------------------------------------------------------------------
# 遗器套装模板（v1 骨架：套装信息 + 2pc/4pc desc 留存；数值效果待 stat 语义钉死后正则批量）
# ---------------------------------------------------------------------------

def generate_relic_set_template(
    set_id: str,
    *,
    lang: str = "cn",
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 数据 → 遗器套装模板 dict.

    v1 范围：套装元信息 + 2pc/4pc desc 原文留存 notes（数值效果正则批量待 stat 语义钉死）。
    """
    from hsr_nous.pipeline import get_relic_set

    raw = get_relic_set(set_id, lang=lang)
    if raw is None:
        raise ValueError(f"遗器套装 {set_id} 不存在于本地数据（lang={lang}）")
    desc = raw.get("desc") or []
    props = raw.get("properties") or []
    template: Dict[str, Any] = {
        "relic_set_id": str(set_id),
        "name": raw.get("name", str(set_id)),
    }
    notes: List[str] = []
    for idx, pc_name in ((0, "set_2pc"), (1, "set_4pc")):
        if idx >= len(desc) or not desc[idx]:
            continue
        pc: Dict[str, Any] = {"desc": desc[idx]}
        stat_effects: Dict[str, float] = {}
        if idx < len(props):
            for p in props[idx]:
                stat = _PROP_MAP.get(p.get("type", ""))
                if stat is None:
                    notes.append(f"{pc_name} 未知 properties type：{p.get('type')}，待人工")
                    continue
                stat_effects[stat] = stat_effects.get(stat, 0.0) + float(p.get("value", 0.0))
        if stat_effects:
            pc["stat_effects"] = stat_effects
        notes.append(f"{pc_name} desc 未覆盖部分待收编：{desc[idx]}")
        template[pc_name] = pc
    if notes:
        template["notes"] = notes
    return template


def write_relic_set_template(
    set_id: str,
    *,
    out_dir: str = "data/sim_templates/relics",
    lang: str = "cn",
) -> str:
    """生成并写盘，返回文件路径."""
    tpl = generate_relic_set_template(set_id, lang=lang)
    safe_name = tpl["name"].replace("•", "_").replace("·", "_").replace("/", "_")
    path = Path(out_dir) / f"{set_id}_{safe_name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 遗器套装模板：{tpl['name']}（{set_id}）——由 adapters/template_generator 生成，勿手改\n")
        yaml.safe_dump(tpl, f, allow_unicode=True, sort_keys=False)
    return str(path)


# ---------------------------------------------------------------------------
# 敌人模板（v1 最小骨架：面板公式链 + 弱点 + 占位普攻；技能机制待收编）
# ---------------------------------------------------------------------------

def generate_enemy_template(
    enemy_id: str,
    *,
    level: int = 80,
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 双源数据 → 敌人模板 dict.

    面板：calc_enemy_stats（hakushin 公式链 base×HardLevel×Elite×Modify）；
    名字：monster.json 官方英文名（无中文结构化源，命名两态——官方名为合法态）；
    技能：fandom_enemy_data 技能 desc 留存 notes（机制待收编），行动给占位普攻。
    """
    import json as _json

    from hsr_nous.pipeline.stages_loader import calc_enemy_stats

    stats = calc_enemy_stats(enemy_id, level)
    if stats is None:
        raise ValueError(f"敌人 {enemy_id} 无 hakushin 数值（不存在或仅遗留源）")

    root = Path(__file__).parent.parent.parent.parent / "data"
    monster = _json.loads((root / "stages" / "hakushin" / "monster.json").read_text(encoding="utf-8"))
    meta = monster.get(str(enemy_id)) or {}
    name_en = meta.get("en") or str(enemy_id)

    notes: List[str] = []
    fandom_path = root / "fandom_enemy_data.json"
    if fandom_path.exists():
        fandom = _json.loads(fandom_path.read_text(encoding="utf-8"))
        fdata = fandom.get(name_en)
        if fdata:
            for sk in fdata.get("skills") or []:
                notes.append(
                    f"技能「{sk.get('name')}」（{sk.get('type')}）机制待收编：{sk.get('desc', '')}"
                )
    if stats.pop("_level_clamped", False):
        notes.append(f"等级 {level} 超出 HardLevelGroup 表范围，已钳到表内最大级")
    missing = stats.pop("_missing_bases", [])
    if missing:
        notes.append(f"原始数据缺 base 字段（按 0 处理）：{', '.join(missing)}——"
                     "通常为无韧性条/不行动的特殊怪，需人工确认机制")
    notes.append("攻击属性缺结构化数据源（fandom attack_element 多为 null），"
                 "占位行动不进伤害结算，待人工按怪物本体属性补")

    return {
        "enemy_id": str(enemy_id),
        "name": name_en,
        "level": level,
        "base_stats": {
            "hp": stats["hp"], "atk": stats["atk"], "def": stats["def_"],
            "spd": stats["spd"], "max_toughness": stats["max_toughness"],
            "effect_res": stats["effect_res"],
        },
        "weakness": stats["weakness"],
        "actions": [{
            "action_id": f"{enemy_id}_basic",
            "name": "Attack",
            "action_type": "basic",
            "target_type": "single",
            "damage_type": "",
            "scaling": [{"atk": 1.0}],
            "toughness_dmg": 10,
        }],
        **({"notes": notes} if notes else {}),
    }


def write_enemy_template(
    enemy_id: str,
    *,
    out_dir: str = "data/sim_templates/enemies",
    level: int = 80,
) -> str:
    """生成并写盘，返回文件路径."""
    tpl = generate_enemy_template(enemy_id, level=level)
    safe_name = tpl["name"].replace("•", "_").replace("·", "_").replace("/", "_").replace(" ", "_")
    path = Path(out_dir) / f"{enemy_id}_{safe_name}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 敌人模板：{tpl['name']}（{enemy_id}）——由 adapters/template_generator 生成，勿手改\n")
        yaml.safe_dump(tpl, f, allow_unicode=True, sort_keys=False)
    return str(path)
