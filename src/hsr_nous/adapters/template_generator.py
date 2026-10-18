"""模板生成器：pipeline 游戏数据 → per-entity DSL 模板（data/sim_templates/characters/）.

v0.5 范围：角色模板（面板 + 普攻/战技/终结技 atk 倍率 + 默认削韧/回能）。
天赋/行迹/星魂机制、HP/DEF 倍率角色特判后置（desc 含"生命/防御"时打 scaling_note 标人工）。
v0.7 起 target_type / 副目标倍率忠于原始数据：effect 字段定形态，
desc 的"相邻目标…#N[i]%"占位符定副倍率位置。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hsr_nous.sim_schema.actor import PATH_ALIASES
from hsr_nous.sim_schema.templates import DEFAULT_TEMPLATE_ROOTS

#: 各类模板/旁车缺省写出目录 = 模板根唯一事实源（sim_schema/templates.py）下的 {kind}/ 子目录；
#: 调用方可注入 out_dir 覆盖（测试写临时根）——各处 write_* 缺省统一引用本表
_OUT_DIRS = {kind: f"{DEFAULT_TEMPLATE_ROOTS[0]}/{kind}"
             for kind in ("characters", "light_cones", "relics", "enemies", "descriptions", "stages")}

#: pipeline 玩法别名 → sim_schema/rulebook.yaml modes 的 canonical key
_STAGE_MODE_MAP = {
    "moc": "forgotten_hall",
    "pf": "pure_fiction",
    "as": "apocalyptic_shadow",
}

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

# 原始数据 properties type → 面板 stat（结构化字段直映射，绕开 desc 正则）。
# 每个目标键必须有消费端（生成键↔消费键双向钉见 tests/test_template_gen.py 治疗全链钉）：
# dmg_ 前缀族落 dmg_bonus 桶（bucket_element 按 damage_type 消费——elation 非元素，
# dmg_elation/dmg_heal_bonus 是无消费端死键，2026-10-12 勘正）；HealRatioBase → 顶层
# heal_bonus（pipeline.heal 治疗公式槽）；ElationDamageAddedRatioBase → elation 面板
# （21_elation §21.1 终审——CN「欢愉度强化」，勿按 property 名映射 elation_dmg_boost）。
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
    "HealRatioBase": "heal_bonus",
    "PhysicalAddedRatio": "dmg_physical",
    "FireAddedRatio": "dmg_fire",
    "IceAddedRatio": "dmg_ice",
    "ThunderAddedRatio": "dmg_thunder",
    "WindAddedRatio": "dmg_wind",
    "QuantumAddedRatio": "dmg_quantum",
    "ImaginaryAddedRatio": "dmg_imaginary",
    "ElationDamageAddedRatioBase": "elation",
}

# 行迹属性节点 type → 面板 stat（= properties 映射 + SpeedDelta 直加速度）
_TRACE_PROP_MAP = {**_PROP_MAP, "SpeedDelta": "spd"}

#: 非攻击类 effect（无 scaling 不进伤害结算，形态占位）——生成器/校验器共用单一事实源
_NON_ATTACK_EFFECTS = frozenset({"Enhance", "Support", "Restore", "Defence", "Summon"})

#: 阵营名册（03_actor §3.1 groups 打标）：分组名 → actor_id 集合。
#: 黄金裔 = 官方献予诗系列（昔涟忆灵技 1141513-1141526 逐目标专用诗）权威推断：
#: 开拓者•记忆（1141513）/阿格莱雅（1141514）/缇宝（1141515）/万敌（1141516）/遐蝶（1141517）/
#: 那刻夏（1141518）/风堇（1141519）/赛飞儿（1141520）/白厄（1141521）/海瑟音（1141522）/
#: 刻律德菈（1141523）/长夜月（1141524）/丹恒•腾荒（1141525）+ 昔涟自身（1415102"除昔涟外
#: 的黄金裔"明示其在册）。版本追踪：新黄金裔随新献予诗入库时补录
_FACTION_ROSTERS: Dict[str, frozenset] = {
    "faction:chrysos_heir": frozenset({
        "1401", "1403", "1404", "1405", "1406", "1407", "1408", "1409",
        "1410", "1412", "1413", "1414", "1415", "8007", "8008",
    }),
}


def _internal_element(raw: str) -> str:
    return raw.lower() if raw else ""


#: StarRailRes 命途英文名 → canonical key（count_team/path_of 消费口径——03_actor §3.1
#: Actor.path）；唯一事实源已上提 sim_schema/actor.py PATH_ALIASES（build_compiler path
#: 闸报错指路同读——勿另立表），本地别名沿用
_PATH_CANONICAL = PATH_ALIASES


def _internal_path(raw: str) -> str:
    return _PATH_CANONICAL.get(raw.lower(), raw.lower()) if raw else ""


#: 特殊充能显示名（energy_name，03_actor/前端 charge 槽）——两源：① 机制库手写件同名键
# （1407/1408/1415——唯一事实源在 data/library/characters/<id>_*.yaml 的
# energy_name 行，改正典件须同步本表）；② 4573c86 钦定收录、无手写件的三名
# （1308 残梦/1220 飞黄/1014 炉心共鸣，官方文本在案）。教训：2026-09-10 重生成丢补丁——
# 骨架每次重生成都是纯产出，不入生成器的补丁必丢，新收特殊充能角色必须落本表
_ENERGY_NAME_BY_CHAR = {"1407": "新蕊", "1408": "火种", "1415": "追忆",
                        "1308": "残梦", "1220": "飞黄", "1014": "炉心共鸣"}


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
    if str(char_id) in _FACTION_ROSTERS["faction:chrysos_heir"]:
        # 黄金裔名册（03_actor §3.1 groups）：以官方献予诗系列（昔涟忆灵技 1141513-1141526
        # 逐目标专用诗）为权威推断源——开拓者•记忆/阿格莱雅/缇宝/万敌/遐蝶/那刻夏/风堇/
        # 赛飞儿/白厄/海瑟音/刻律德菈/长夜月/丹恒•腾荒 + 昔涟自身（1415102"除昔涟外的
        # 黄金裔"明示其在册）；版本追踪——新黄金裔随新献予诗入库时补录
        template_groups = ["faction:chrysos_heir"]
    else:
        template_groups = []
    raw_sp = raw.get("max_sp")
    max_sp = float(raw_sp) if raw_sp is not None else 0.0
    sp_note = None
    if raw_sp is None:
        # 特殊充能角色（遐蝶类新蕊资源）：非常规能量，max_energy 置 0 + 标人工
        sp_note = "max_sp 为 null：特殊充能角色（新蕊类），能量机制待人工"

    merged = load_character_skills_merged(data_dir=data_dir, lang=lang)
    # 技能归属按 characters.json 的 skills 清单，不按 ID 前缀——加强版技能
    # （4.x 老角色增强，ID 形如 1{charid}xx，如希儿加强版 11102xxx）前缀会错挂
    # 到前缀相同的其他角色（曾把希儿加强版 1110201-203 分进 1110_玲可.yaml）
    owned = {str(s) for s in (raw.get("skills") or [])}
    actions: List[Dict[str, Any]] = []
    scaling_notes: List[str] = []
    if sp_note:
        scaling_notes.append(sp_note)
    for sid, s in merged.items():
        if owned and sid not in owned:
            continue
        if not owned and not sid.startswith(str(char_id)):
            continue  # characters.json 无 skills 清单的兜底（理论上不该发生）
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
        if s.get("effect") in _NON_ATTACK_EFFECTS:
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
        "path": _internal_path(raw.get("path", "")),   # 命途（count_team/path_of 消费前提——曾缺发致生成队恒 0）
        "element": element,   # 元素（动态元素族 element_of 取数源——03_actor §3.1 Actor.element）
        **({"energy_name": _ENERGY_NAME_BY_CHAR[str(char_id)]}
           if str(char_id) in _ENERGY_NAME_BY_CHAR else {}),   # 特殊充能显示名（锚=fixture）
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
    if template_groups:
        template["groups"] = template_groups

    # 行迹（skill_tree）：属性节点结构化 properties 直映射进面板；大行迹（额外能力）留 notes
    trace_flat: Dict[str, float] = {}   # 直加类（crit_dmg/spd/effect_hit/dmg_* 等）
    trace_pct: Dict[str, float] = {}    # pct 类（atk_pct 等——白值百分比，保持 pct 形态供编译期归并）
    trace_notes: List[str] = []
    from hsr_nous.pipeline.build.loader import get_character_full
    full = get_character_full(str(char_id), lang=lang)
    for st in full.get("skill_trees_detail") or []:
        if st.get("name") and st.get("desc"):
            trace_notes.append(f"大行迹「{st['name']}」机制待收编：{st['desc']}")
        for lv in st.get("levels") or []:
            for p in lv.get("properties") or []:
                stat = _TRACE_PROP_MAP.get(p.get("type", ""))
                if stat is None:
                    trace_notes.append(f"行迹未知 properties type：{p.get('type')}（节点 {st.get('id')}）")
                    continue
                val = float(p.get("value", 0.0))
                if stat.endswith("_pct"):
                    trace_pct[stat] = trace_pct.get(stat, 0.0) + val
                elif stat.startswith("dmg_"):
                    trace_flat.setdefault("dmg_bonus", {})
                    trace_flat["dmg_bonus"][stat] = trace_flat["dmg_bonus"].get(stat, 0.0) + val
                else:
                    trace_flat[stat] = trace_flat.get(stat, 0.0) + val
    bs = template["base_stats"]
    for stat, val in trace_flat.items():
        if stat == "dmg_bonus":
            bs.setdefault("dmg_bonus", {})
            for k, v in val.items():
                bs["dmg_bonus"][k.removeprefix("dmg_")] = bs["dmg_bonus"].get(k.removeprefix("dmg_"), 0.0) + v
        else:
            bs[stat] = bs.get(stat, 0.0) + val
    if trace_pct:
        template["trace_stat_effects"] = trace_pct
    if trace_notes:
        template["trace_notes"] = trace_notes

    if scaling_notes:
        template["scaling_notes"] = scaling_notes
    return template


def write_character_template(
    char_id: str,
    *,
    out_dir: str = _OUT_DIRS["characters"],
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
    out_dir: str = _OUT_DIRS["light_cones"],
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
    out_dir: str = _OUT_DIRS["relics"],
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
# 敌人模板（v1：面板 + 有序列证据的单段直接攻击子集；其余技能显式跳过）
# ---------------------------------------------------------------------------

_ENEMY_SEQUENCE_AI = "Config/ConfigAI/Monster_Common_SequenceThree_AI.json"
_ENEMY_ATK_RATIO_RE = re.compile(r"(\d+(?:\.\d+)?)%\s*ATK")
_ENEMY_ELEMENTS = ("Physical", "Fire", "Ice", "Lightning", "Wind", "Quantum", "Imaginary")


def _enemy_pure_damage_description(skill_type: str, element: str, desc: str) -> bool:
    """只接受完整纯直伤句，防止把未收编的附加效果静默削成纯伤害."""
    ratio = r"\d+(?:\.\d+)?% ATK"
    prefix = rf"Deals (?:(?:minor|massive|Massive) )?{re.escape(element)} DMG"
    if skill_type in {"Basic ATK", "Single Target", "AoE ATK"}:
        targets = ["all targets"] if skill_type == "AoE ATK" else [
            "a single target", "one designated target", "one target"]
        if skill_type == "Basic ATK":
            targets.append("all targets")
        target = rf"(?:{'|'.join(targets)})"
        patterns = [
            rf"{prefix} \({ratio}\) to {target}\.?",
            rf"{prefix} to {target} \({ratio}\)\.?",
        ]
    else:
        main = r"(?:a single target|one designated target)"
        adjacent = (r"(?:units adjacent to the target|any adjacent targets|adjacent targets|"
                    r"adjacent units|their adjacent targets|its adjacent units)")
        patterns = [
            rf"{prefix} \({ratio}\) to {main} and {adjacent}\.?",
            rf"{prefix} to {main} \({ratio}\) and {adjacent} \({ratio}\)\.?",
            rf"{prefix} \({ratio}\) to {main} and {adjacent} \({ratio}\)\.?",
        ]
    return any(re.fullmatch(pattern, desc) for pattern in patterns)


def _enemy_direct_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """TBGD 技能 + Fandom 对齐条目 → 单段纯直接攻击；任一语义不确定则不收编."""
    skill_type = semantic.get("type")
    if skill_type not in {"Basic ATK", "Single Target", "Blast", "AoE ATK"}:
        return None
    sp_hit_base = raw.get("sp_hit_base")
    if sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer():
        return None
    desc = semantic.get("desc") or ""
    desc_element = next((element for element in _ENEMY_ELEMENTS if f"{element} DMG" in desc), "")
    if not desc_element:
        return None
    raw_element = raw.get("damage_type")
    if raw_element and {"Thunder": "Lightning"}.get(raw_element, raw_element) != desc_element:
        return None
    if not _enemy_pure_damage_description(skill_type, desc_element, desc):
        return None
    params = raw.get("param_list") or []
    ratios = [float(x) / 100.0 for x in _ENEMY_ATK_RATIO_RE.findall(desc)]
    if params:
        # Blast 文本只写一次倍率时，允许原始主/副两个参数槽同值；其余布局仍逐槽对账。
        shared_blast = skill_type == "Blast" and len(ratios) == 1 and len(params) == 2
        if shared_blast:
            valid = all(abs(float(param) - ratios[0]) <= 1e-9 for param in params)
        else:
            expected_params = 2 if skill_type == "Blast" and len(params) == len(ratios) == 2 else 1
            valid = (len(params) == expected_params and len(ratios) == expected_params
                     and all(abs(float(param) - ratio) <= 1e-9
                             for param, ratio in zip(params, ratios)))
        if not valid:
            return None
    if skill_type == "AoE ATK":
        target_type = "aoe"
    elif skill_type == "Single Target":
        target_type = "single"
    elif skill_type == "Blast":
        target_type = "blast"
    elif "to all targets" in desc:
        target_type = "aoe"
    elif "to a single target" in desc or "to one designated target" in desc:
        target_type = "single"
    else:
        return None
    action = {
        "action_id": str(raw["skill_id"]),
        "name": semantic.get("name") or str(raw["skill_id"]),
        # 非 Basic ATK 的主动攻击暂以 skill 作实现期候选；真实 golden 最终定稿。
        "action_type": "basic" if skill_type == "Basic ATK" else "skill",
        "target_type": target_type,
        "damage_type": {"Lightning": "thunder"}.get(desc_element, desc_element).lower(),
        "scaling": [{"atk": ratios[0]}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if target_type == "blast" and len(ratios) == 2:
        # 主副倍率分开时显式写；单倍率 Blast 由引擎沿用主倍率。副削韧均按 rulebook 候选。
        action["scaling_blast"] = [{"atk": ratios[1]}]
    return action


def _enemy_linked_param_direct_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """纯直伤句携带关联机制参数槽时，只取本击倍率槽并复用通用直伤转换."""
    layouts = {
        "Lupine Chase Calls Bloody Gleam": ([6.0, 2.0], [6.0]),
        "Pyrolysis Death Beam": ([4.5, 3.5, 0.5, 1.2, 1.0], [4.5, 3.5]),
        "Punishment of Endless Winter": ([5.0, 0.0], [5.0]),
    }
    layout = layouts.get(str(semantic.get("name") or ""))
    params = raw.get("param_list") or []
    if layout is None or len(params) != len(layout[0]):
        return None
    expected, damage_params = layout
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    trimmed = dict(raw)
    trimmed["param_list"] = damage_params
    return _enemy_direct_action(trimmed, semantic)


def _enemy_starfall_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Starfall, Mooncry：AoE 直伤并切换到 Abundance/Destruction 形态."""
    if semantic.get("type") != "AoE ATK":
        return None
    match = re.fullmatch(
        r"Deals (Wind|Lightning) DMG \((\d+(?:\.\d+)?)% ATK\) to all targets "
        r"and shifts to (Abundance|Destruction) Form\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    element = {"Thunder": "Lightning"}.get(raw.get("damage_type"), raw.get("damage_type"))
    form = match.group(3)
    if (element != match.group(1) or (element, form) not in {
            ("Wind", "Abundance"), ("Lightning", "Destruction")}):
        return None
    ratio = float(match.group(2)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{form.upper()}_FORM",
                "name": f"{form} Form",
                "modifier_type": "buff",
                "duration": 0,
                "max_stack": 1,
                "stack_mode": "refresh",
                "singleton_group": "ENEMY_OPPORTUNISTIC_FORM",
                "dispellable": False,
            },
        }],
    }
    return action, hook


def _enemy_saturation_cleaning_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Saturation Cleaning!：Quantum AoE + 队伍共享 Punchline 单次发放."""
    if semantic.get("type") != "AoE ATK" or raw.get("damage_type") != "Quantum":
        return None
    match = re.fullmatch(
        r"Deals massive Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to all targets "
        r"and grants the target team Punchline \((\d+(?:\.\d+)?)\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    ratio = float(match.group(1)) / 100.0
    punchline = float(match.group(2))
    if (abs(float(params[0]) - punchline) > 1e-9
            or abs(float(params[1]) - ratio) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe",
        "damage_type": "quantum",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "gain_resource", "resource_id": "punchline",
            # 队伍池只写一次；以主目标为事件持有者，不按 AoE 命中人数重复发放。
            "target": "$event.target", "amount": punchline,
        }],
    }
    return action, hook


def _enemy_bounce_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bounce（固定次数、每段同倍率随机单体）→ 现有多段 bounce action."""
    if semantic.get("type") != "Bounce":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals successive \((?:×)?(\d+)\) (?:minor )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to random (?:single )?targets\.", desc)
    if match:
        count_text, element_text, ratio_text = match.group(1), match.group(2), match.group(3)
    else:
        match = re.fullmatch(
            r"Deals successive minor (\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to random single targets \(x(\d+)\)\.", desc)
        if not match:
            return None
        element_text, ratio_text, count_text = match.group(1), match.group(2), match.group(3)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if not raw.get("damage_type") or sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer():
        return None
    count = int(count_text)
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    ratio = float(ratio_text) / 100.0
    if (count <= 0 or element_text != element or len(params) > 2
            or (params and abs(float(params[0]) - ratio) > 1e-9)
            or (len(params) == 2 and float(params[1]) != count)):
        return None
    return {
        "action_id": str(raw["skill_id"]),
        "name": semantic.get("name") or str(raw["skill_id"]),
        "action_type": "skill",
        "target_type": "bounce",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "instances": count,
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }


def _enemy_obscure_blaze_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Obscure Blaze：攻击/强化获得计数，Bonepiercing Odium 基础 1 击并按层追加."""
    desc = semantic.get("desc") or ""
    params = raw.get("param_list") or []
    action_id = str(raw["skill_id"])
    base = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if semantic.get("type") == "Enhance":
        if desc != "Gains 3 stacks of Obscure Blaze." or params:
            return None
        return {**base, "target_type": "self", "resource_gain": {"obscure_blaze": 3}}

    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK", "Bounce"}:
        return None
    sp_hit_base = raw.get("sp_hit_base")
    if (raw.get("damage_type") != "Quantum" or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    if skill_type == "Bounce":
        match = re.fullmatch(
            r"Deals minor successive Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to a random target\. "
            r"Each stack of Obscure Blaze additionally deals DMG 1 time\.", desc)
        if not match:
            return None
        ratio = float(match.group(1)) / 100.0
        if (len(params) != 2 or abs(float(params[0]) - ratio) > 1e-9
                or not float(params[1]).is_integer() or params[1] < 0):
            return None
        max_stacks = int(params[1])
        return {
            **base, "target_type": "bounce", "damage_type": "quantum",
            "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base),
            "instances_from_resource": "obscure_blaze", "instances_base": 1,
            "instances_per_point": 1, "instances_cap": max_stacks + 1,
            "consume_all_resource": "obscure_blaze",
        }

    target_text = "all targets" if skill_type == "AoE ATK" else "(?:a single target|one designated target)"
    match = re.fullmatch(
        rf"Deals (?:minor )?Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to {target_text} "
        rf"and gains 1 stack of Obscure Blaze\.", desc)
    if not match:
        return None
    ratio = float(match.group(1)) / 100.0
    if len(params) != 1 or abs(float(params[0]) - ratio) > 1e-9:
        return None
    return {
        **base, "target_type": "aoe" if skill_type == "AoE ATK" else "single",
        "damage_type": "quantum", "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base), "resource_gain": {"obscure_blaze": 1},
    }


def _enemy_scorchbone_inferno_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Scorchbone Inferno：Bug 版 Shell of Faded Rage 的叠层与弹射扩散."""
    desc = semantic.get("desc") or ""
    params = raw.get("param_list") or []
    action_id = str(raw["skill_id"])
    base = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if semantic.get("type") == "Enhance":
        if desc != 'Gain many "Scorchbone Inferno" stacks.' or len(params) != 1:
            return None
        count = float(params[0])
        if count <= 0 or not count.is_integer():
            return None
        return {**base, "target_type": "self",
                "resource_gain": {"scorchbone_inferno": int(count)}}

    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK", "Bounce"}:
        return None
    sp_hit_base = raw.get("sp_hit_base")
    if (raw.get("damage_type") != "Quantum" or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    if skill_type == "Bounce":
        match = re.fullmatch(
            r"Deals minor Quantum DMG \((\d+(?:\.\d+)?)% ATK\) continuously to one random target "
            r"and their adjacent targets\. Each \"Scorchbone Inferno\" stack deals 1 additional "
            r"instance of damage\.", desc)
        if not match:
            return None
        ratio = float(match.group(1)) / 100.0
        if (len(params) != 2 or abs(float(params[0]) - ratio) > 1e-9
                or not float(params[1]).is_integer() or params[1] < 0):
            return None
        max_stacks = int(params[1])
        return {
            **base, "target_type": "bounce_blast", "damage_type": "quantum",
            "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base),
            "instances_from_resource": "scorchbone_inferno", "instances_base": 1,
            "instances_per_point": 1, "instances_cap": max_stacks + 1,
            "consume_all_resource": "scorchbone_inferno",
        }

    target_text = "all targets" if skill_type == "AoE ATK" else "one designated target"
    match = re.fullmatch(
        rf"Deals (?:minor )?Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to {target_text} "
        rf"and gain 1 \"Scorchbone Inferno\" stack\.", desc)
    if not match:
        return None
    ratio = float(match.group(1)) / 100.0
    if len(params) != 1 or abs(float(params[0]) - ratio) > 1e-9:
        return None
    return {
        **base, "target_type": "aoe" if skill_type == "AoE ATK" else "single",
        "damage_type": "quantum", "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base), "resource_gain": {"scorchbone_inferno": 1},
    }


def _enemy_custom_resource_decls(actions: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """由最终敌人行动表收集资源声明；未登记资源直接拒绝生成."""
    used: set[str] = set()
    for action in actions:
        used.update((action.get("resource_gain") or {}).keys())
        used.update(action.get(key) for key in ("instances_from_resource", "consume_all_resource")
                    if action.get(key))
    declarations: Dict[str, Dict[str, Any]] = {}
    for rid, name in (("obscure_blaze", "Obscure Blaze"),
                      ("scorchbone_inferno", "Scorchbone Inferno")):
        if rid in used:
            declarations[rid] = {"name": name, "max": 3, "current": 0}
    if "gusto" in used:
        declarations["gusto"] = {"name": "Gusto", "max": "inf", "current": 0}
    missing = used - declarations.keys()
    if missing:
        raise ValueError(f"敌人行动引用未登记资源：{sorted(missing)}")
    return declarations


def _enemy_distribute_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Distribute（总倍率明确、全目标均分）→ AoE + split: even."""
    if semantic.get("type") != "Distribute":
        return None
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"(?:to all targets\. The DMG is distributed evenly among (?:the )?targets|"
        r"to one designated locked-on target, the DMG is evenly distributed across all targets)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    ratio = float(match.group(2)) / 100.0
    if match.group(1) != element or len(params) != 1 or abs(float(params[0]) - ratio) > 1e-9:
        return None
    return {
        "action_id": str(raw["skill_id"]),
        "name": semantic.get("name") or str(raw["skill_id"]),
        "action_type": "skill",
        "target_type": "aoe",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
        "split": "even",
    }


def _enemy_restore_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_name: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Restore（仅“按施放者 Max HP 比例治疗敌方全体”）→ 支援 action + heal hook."""
    if semantic.get("type") != "Restore":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        rf"Immediately (?:recovers|restores) all friendly units' HP \((\d+(?:\.\d+)?)% "
        rf"{re.escape(owner_name)} Max HP\)\.", desc)
    params = raw.get("param_list") or []
    if not match or len(params) != 1:
        return None
    ratio = float(match.group(1)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{"effect_type": "heal", "target": "all_enemies", "ratio": ratio, "amount": 0}],
    }
    return action, hook


def _enemy_combat_redeployment_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Combat Redeployment → 净化其他友方 + 可选增伤 + 立即行动."""
    if semantic.get("type") != "Support":
        return None
    match = re.fullmatch(
        r"Dispels all debuffs on a friendly unit except Bronya, (?:and )?causes them to take action "
        r"immediately(?:, and slightly increases their DMG dealt \((\d+(?:\.\d+)?)%, (\d+) Turn\))?\.",
        semantic.get("desc") or "")
    if not match:
        return None
    params = raw.get("param_list") or []
    boost_ratio = float(match.group(1)) / 100.0 if match.group(1) else None
    boost_duration = int(match.group(2) or 0)
    if boost_ratio is None and params:
        return None
    if boost_ratio is not None and (
            len(params) != 2 or abs(float(params[0]) - boost_ratio) > 1e-9
            or float(params[1]) != boost_duration):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    other_friendlies = {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}
    effects = [{
        "effect_type": "remove_modifier",
        "target": other_friendlies,
        "filter": "$mod.kind != 'buff'",
    }]
    if boost_ratio is not None:
        effects.append({
            "effect_type": "apply_modifier",
            "target": other_friendlies,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_REDEPLOYMENT",
                "name": "Combat Redeployment",
                "modifier_type": "buff",
                "stat_effects": {"all_dmg": boost_ratio},
                "duration": boost_duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        })
    effects.append({"effect_type": "immediate_action", "target": other_friendlies})
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": effects,
    }
    return action, hook


def _enemy_heavens_binds_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Heaven's Binds：自身强化并获得一个额外行动."""
    if semantic.get("type") != "Enhance" or semantic.get("desc") != (
            "Enhances self to gain additional action."):
        return None
    params = raw.get("param_list") or []
    if len(params) != 6 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [2.5, 5.0, 3.8, 0.25, 1.0, 1.0])):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{"effect_type": "immediate_action", "target": "self"}],
    }
    return action, hook


def _enemy_engine_boost_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Engine Boost / Void Fission / Calamity Strike：ATK 增益并恢复韧性."""
    if semantic.get("type") != "Support":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Grants the Enhanced status \(ATK \+(\d+(?:\.\d+)?)%, (\d+) Turns\) to all friendly "
        r"units except the user, restoring their Toughness\.", desc)
    target_name = ""
    if not match:
        match = re.fullmatch(
            r"Enhances (Disaster's Right Hand|Dawn's Left Hand) "
            r"\(ATK \+(\d+(?:\.\d+)?)%, (\d+) Turns\), restoring its Toughness\.", desc)
        target_name = match.group(1) if match else ""
    if not match:
        return None
    if target_name:
        ratio = float(match.group(2)) / 100.0
        duration = int(match.group(3))
    else:
        ratio = float(match.group(1)) / 100.0
        duration = int(match.group(2))
    params = raw.get("param_list") or []
    if params and (len(params) != 2 or abs(float(params[0]) - ratio) > 1e-9
                   or float(params[1]) != duration):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    targets = ({"pool": "enemies", "where": f'$it.name == "{target_name}"'} if target_name
               else {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"})
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": targets,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_ENHANCED",
                "name": "Enhanced",
                "modifier_type": "buff",
                "stat_effects": {"atk_pct": ratio},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }, {
            "effect_type": "restore_toughness",
            "target": targets,
        }],
    }
    return action, hook


def _enemy_primal_hunger_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], detail: Dict[str, Any], monster_meta: Any,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Primal Hunger → 自身召唤的 Juvenile Sting 固定速度增益."""
    if semantic.get("type") != "Support":
        return None
    match = re.fullmatch(
        r'Increases the SPD \((\d+(?:\.\d+)?), (\d+) Turns\) of "Juvenile Sting" '
        r'summoned by this unit\.', semantic.get("desc") or "")
    summon_ids = detail.get("SummonIDList") or []
    if not match or len(summon_ids) != 1:
        return None
    summon_meta = monster_meta(str(summon_ids[0]))
    if not summon_meta or summon_meta.get("en") != "Juvenile Sting":
        return None
    params = raw.get("param_list") or []
    if len(params) != 2:
        return None
    spd = float(match.group(1))
    duration = int(match.group(2))
    if abs(float(params[0]) - spd) > 1e-9 or float(params[1]) != duration:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": {"pool": "enemies", "where": "$it.summoner_id == $self.actor_id"},
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_PRIMAL_HUNGER",
                "name": "Primal Hunger",
                "modifier_type": "buff",
                "stat_effects": {"spd": spd},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_rapturous_wind_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], detail: Dict[str, Any], monster_meta: Any,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Rapturous Wind：单体冰伤，Yanqing 与其飞剑叠 Chilling Light 增伤."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Ice":
        return None
    match = re.fullmatch(
        r"Deals Ice DMG \((\d+(?:\.\d+)?)% ATK\) to a single target\. Yanqing and all "
        r"Flying Swords gain 1 stack of Chilling Light and slightly increases DMG dealt "
        r"\((\d+(?:\.\d+)?)%\)\.", semantic.get("desc") or "")
    summon_ids = detail.get("SummonIDList") or []
    summon_metas = [monster_meta(str(summon_id)) for summon_id in summon_ids]
    if (not match or not summon_metas
            or any(not meta or meta.get("en") != "Flying Sword" for meta in summon_metas)):
        return None
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer()
            or len(params) != 2):
        return None
    ratio = float(match.group(1)) / 100.0
    boost = float(match.group(2)) / 100.0
    if (abs(float(params[0]) - ratio) > 1e-9
            or abs(float(params[1]) - boost) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    modifier_id = "ENEMY_CHILLING_LIGHT"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "ice",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": {
                "pool": "enemies",
                "where": "$it.actor_id == $self.actor_id or $it.summoner_id == $self.actor_id",
            },
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Chilling Light",
                "modifier_type": "buff",
                "stat_exprs": {"all_dmg": f"{boost} * stacks($self, '{modifier_id}')"},
                "stacks": 1,
                "duration": 0,
                "max_stack": 99,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_frigid_waterfall_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Frigid Waterfall：AoE 冰伤并叠加自身 DMG Boost."""
    if semantic.get("type") != "AoE ATK" or raw.get("damage_type") != "Ice":
        return None
    match = re.fullmatch(
        r"Deals Ice DMG \((\d+(?:\.\d+)?)% ATK\) to all targets and slightly increases "
        r"the DMG dealt \((\d+(?:\.\d+)?)%\)\. This DMG boosting effect is stackable\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 3):
        return None
    ratio = float(match.group(1)) / 100.0
    boost = float(match.group(2)) / 100.0
    if (abs(float(params[0]) - ratio) > 1e-9
            or abs(float(params[1]) - boost) > 1e-9 or float(params[2]) != 1.0):
        return None
    action_id = str(raw["skill_id"])
    modifier_id = "ENEMY_FRIGID_WATERFALL"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe",
        "damage_type": "ice",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Frigid Waterfall",
                "modifier_type": "buff",
                "stat_exprs": {"all_dmg": f"{boost} * stacks($self, '{modifier_id}')"},
                "stacks": 1,
                "duration": 0,
                "max_stack": 99,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_molten_fusion_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Molten Fusion：自身 ATK 每层 +30%，持续 2 回合，最多 3 层."""
    if semantic.get("type") != "Enhance":
        return None
    match = re.fullmatch(
        r"Increases this unit's ATK \((\d+(?:\.\d+)?)% Per Stack, (\d+) Turns, Max (\d+) Stacks\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    if not match or len(params) != 1:
        return None
    ratio = float(match.group(1)) / 100.0
    duration = int(match.group(2))
    max_stack = int(match.group(3))
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    modifier_id = "ENEMY_MOLTEN_FUSION"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Molten Fusion",
                "modifier_type": "buff",
                "stat_exprs": {"atk_pct": f"{ratio} * stacks($self, '{modifier_id}')"},
                "stacks": 1,
                "duration": duration,
                "max_stack": max_stack,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_shock_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体雷伤 + Shock → 直接攻击 + DoT hook（常规/倒序参数逐值对账）."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Thunder":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Lightning DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to Shock the target "
        r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\)\.", desc)
    reversed_params = False
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Lightning DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), "
            r"with a high chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) to Shock the target "
            r"\((\d+(?:\.\d+)?)% ATK DoT, (\d+) Turns\)\.", desc)
        reversed_params = True
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Lightning DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), "
            r"with a chance \((\d+(?:\.\d+)?)% Base Chance\) to Shock "
            r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\) the target\.", desc)
        reversed_params = False
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    if reversed_params:
        # Fandom 概率单位误写 ATK 的条目只接受 100% 且省略原始概率槽的形态。
        if match.group(3) == "ATK" and base_chance != 1.0:
            return None
        dot_ratio = float(match.group(4)) / 100.0
        duration = int(match.group(5))
        expected = [damage_ratio, dot_ratio, float(duration)]
        if base_chance != 1.0:
            return None
    else:
        duration = int(match.group(3))
        dot_ratio = float(match.group(4)) / 100.0
        expected = [damage_ratio, base_chance, float(duration), dot_ratio]
    if (len(params) != len(expected)
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "thunder",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_SHOCK",
                "name": "Shock",
                "modifier_type": "dot",
                "dot_element": "thunder",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_burn_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体/AoE 火伤 + Burn → 直接攻击 + 非叠层 DoT hook."""
    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK"} or raw.get("damage_type") != "Fire":
        return None
    desc = semantic.get("desc") or ""
    aoe = skill_type == "AoE ATK"
    enkindle = False
    if aoe:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Fire DMG \((\d+(?:\.\d+)?)% ATK\) to all targets, "
            r"with a high chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) to Burn "
            r"\((\d+(?:\.\d+)?)% ATK Fire DoT, (\d+) Turns\) them\.", desc)
        alternate = True
    else:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Fire DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), "
            r"with a (?:high )?chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) to Burn the target "
            r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\)\.", desc)
        alternate = False
        if not match:
            match = re.fullmatch(
                r"Deals (?:minor |massive )?Fire DMG \((\d+(?:\.\d+)?)% ATK\) "
                r"to (?:a single target|one designated target), "
                r"with a (?:high )?chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) to Burn "
                r"\((\d+(?:\.\d+)?)% ATK DoT, (\d+) Turns\) the target\.", desc)
            alternate = True
        if not match:
            match = re.fullmatch(
                r"Deals (?:minor |massive )?Fire DMG \((\d+(?:\.\d+)?)% ATK\) "
                r"to (?:a single target|one designated target)"
                r"(?:, with| and has) a high chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) "
                r"to inflict Enkindle \((\d+(?:\.\d+)?)% ATK DoT Per Stack, "
                r"(\d+) Turns, Stackable\)\.", desc)
            alternate = True
            enkindle = True
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    duration = int(match.group(5)) if alternate else int(match.group(4))
    dot_ratio = float(match.group(4)) / 100.0 if alternate else float(match.group(5)) / 100.0
    if match.group(3) == "ATK" and base_chance != 1.0:
        return None
    if len(params) == 3 and base_chance == 1.0:
        expected = [damage_ratio, dot_ratio, float(duration)]
    elif len(params) == 4:
        expected = [damage_ratio, base_chance, float(duration), dot_ratio]
    else:
        return None
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe" if aoe else "single",
        "damage_type": "fire",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "all_allies" if aoe else "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_{'ENKINDLE' if enkindle else 'BURN'}",
                "name": "Enkindle" if enkindle else "Burn",
                "modifier_type": "dot",
                "dot_element": "fire",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "duration": duration,
                # Enkindle 文本只说 Stackable，不制造上限；沿用 Modifier 默认安全上限。
                **({"stacks": 1} if enkindle else {"max_stack": 1}),
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_wind_shear_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体/AoE 风伤 + 可叠层 Wind Shear → 直接攻击 + DoT hook（多种参数布局）."""
    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK"} or raw.get("damage_type") != "Wind":
        return None
    desc = semantic.get("desc") or ""
    aoe = skill_type == "AoE ATK"
    if aoe:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Wind DMG \((\d+(?:\.\d+)?)% ATK\) to all targets, "
            r"with a high chance(?: \((\d+(?:\.\d+)?)% Base Chance\))? to cause Wind Shear "
            r"\((?:Applies (\d+) Stacks, )?(\d+(?:\.\d+)?)% ATK DoT Per Stack, (\d+) Turns"
            r"(?:, Max (\d+) Stacks)?\)\.", desc)
    else:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Wind DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target)"
            r"(?:, with| and has) a high chance(?: \((\d+(?:\.\d+)?)% Base Chance\))? "
            r"to (?:inflict|cause) Wind Shear (?:on the target )?\((?:Applies (\d+) Stacks, )?"
            r"(\d+(?:\.\d+)?)% ATK DoT(?: Per Stack)?, (\d+) Turns"
            r"(?:, Max (\d+) Stacks)?\)\.", desc)
        if not match:
            match = re.fullmatch(
                r"Deals (?:minor |massive )?Wind DMG \((\d+(?:\.\d+)?)% ATK\) "
                r"to (?:a single target|one designated target), "
                r"with a high chance(?: \((\d+(?:\.\d+)?)% Base Chance\))? to inflict "
                r"(\d+) stacks of Wind Shear \((\d+(?:\.\d+)?)% ATK DoT Per Stack, "
                r"(\d+) Turns(?:, Max (\d+) Stacks)?\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0 if match.group(2) else 1.0
    initial_stacks = int(match.group(3) or 1)
    dot_ratio = float(match.group(4)) / 100.0
    duration = int(match.group(5))
    max_stack = int(match.group(6) or 5)
    max_suffix = [float(max_stack)] if match.group(6) and len(params) == 5 else []
    layouts = [
        (base_chance, 1, [damage_ratio, base_chance, float(duration), dot_ratio] + max_suffix),
        (base_chance, 1, [damage_ratio, base_chance, dot_ratio, float(duration)] + max_suffix),
        (base_chance, initial_stacks,
         [damage_ratio, float(initial_stacks), float(duration), dot_ratio, base_chance] + max_suffix),
        (base_chance, initial_stacks,
         [damage_ratio, float(initial_stacks), dot_ratio, float(duration)] + max_suffix),
        # 原始表只载伤害倍率时，状态数值以完整文本对账，不虚构额外参数槽。
        (base_chance, initial_stacks, [damage_ratio]),
    ]
    if aoe:
        aoe_max_suffix = [float(max_stack)] if match.group(6) and len(params) == 3 else []
        layouts.append((base_chance, initial_stacks,
                        [damage_ratio, base_chance] + aoe_max_suffix))
    matched = [(chance, stacks, expected) for chance, stacks, expected in layouts
               if len(expected) == len(params)
               and all(abs(float(param) - value) <= 1e-9
                       for param, value in zip(params, expected))]
    if len({tuple(expected) for _chance, _stacks, expected in matched}) != 1:
        return None
    base_chance, initial_stacks, _expected = matched[0]
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe" if aoe else "single",
        "damage_type": "wind",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "all_allies" if aoe else "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_WIND_SHEAR",
                "name": "Wind Shear",
                "modifier_type": "dot",
                "dot_element": "wind",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "stacks": initial_stacks,
                "duration": duration,
                "max_stack": max_stack,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_great_arbor_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """固定 Bounce/Blast 并逐命中施加 Wind Shear（Great Arbor / Guiding Vulturnus）."""
    skill_type = semantic.get("type")
    if skill_type not in {"Bounce", "Blast"} or raw.get("damage_type") != "Wind":
        return None
    desc = semantic.get("desc") or ""
    if skill_type == "Bounce":
        match = re.fullmatch(
            r"Continuously \(×(\d+)\) deal Wind DMG \((\d+(?:\.\d+)?)% ATK\) to a random target, "
            r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to cause Wind Shear "
            r"\((\d+(?:\.\d+)?)% ATK DoT, (\d+) Turns\)\.", desc)
    else:
        match = re.fullmatch(
            r"Deals Wind DMG \((\d+(?:\.\d+)?)% ATK\) to (?:the targeted and adjacent allies|"
            r"a target and its adjacent targets), with a high chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to cause Wind Shear "
            r"\((\d+(?:\.\d+)?)% ATK DoT(?: Per Stack)?, (\d+) Turns(?:, Max \d+ Stacks)?\)\.",
            desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 4):
        return None
    if skill_type == "Bounce":
        instances = int(match.group(1))
        ratio = float(match.group(2)) / 100.0
        base_chance = float(match.group(3)) / 100.0
        dot_ratio = float(match.group(4)) / 100.0
        duration = int(match.group(5))
    else:
        instances = 1
        ratio = float(match.group(1)) / 100.0
        base_chance = float(match.group(2)) / 100.0
        dot_ratio = float(match.group(3)) / 100.0
        duration = int(match.group(4))
    expected = [ratio, 1.0, float(duration), dot_ratio]
    if (instances <= 0
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": skill_type.lower(),
        "damage_type": "wind",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if instances > 1:
        action["instances"] = instances
    if skill_type == "Blast":
        action["scaling_blast"] = [{"atk": ratio}]
    hook = {
        "event": "after_being_hit",
        "condition": f"$event.source == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_WIND_SHEAR",
                "name": "Wind Shear",
                "modifier_type": "dot",
                "dot_element": "wind",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "stacks": 1,
                "duration": duration,
                "max_stack": 5,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_caressing_moonlight_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], semantic_catalog: Optional[List[Dict[str, Any]]],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Caressing Moonlight：Blast 主邻伤害；主目标 Shocked 时副目标也 Shock."""
    if semantic.get("type") != "Blast" or raw.get("damage_type") != "Thunder":
        return None
    match = re.fullmatch(
        r"Deals Lightning DMG to a single target \((\d+(?:\.\d+)?)% ATK\) and "
        r"(?:units adjacent to the target|any adjacent targets) \((\d+(?:\.\d+)?)% ATK\)\. "
        r"If the primary target is Shocked, inflicts Shock on the secondary (?:units|targets) as well\.",
        semantic.get("desc") or "")
    shock_semantic = next((s for s in semantic_catalog or [] if s.get("name") == "Midnight Tumult"), None)
    shock_match = re.search(r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\)",
                            (shock_semantic or {}).get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or shock_match is None or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    ratios = [float(match.group(1)) / 100.0, float(match.group(2)) / 100.0]
    if any(abs(float(param) - ratio) > 1e-9 for param, ratio in zip(params, ratios)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "blast",
        "damage_type": "thunder",
        "scaling": [{"atk": ratios[0]}],
        "scaling_blast": [{"atk": ratios[1]}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "after_being_hit",
        "condition": (
            f"$event.source == $self.actor_id and $event.action_id == '{action_id}' "
            "and dot_kind($event.primary_target, 'shock') "
            "and $event.target != $event.primary_target"),
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": 1.0,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_SHOCK",
                "name": "Shock",
                "modifier_type": "dot",
                "dot_element": "thunder",
                "dot_ratio": float(shock_match.group(2)) / 100.0,
                "dot_base_chance": 1.0,
                "duration": int(shock_match.group(1)),
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_seething_whisper_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], semantic_catalog: Optional[List[Dict[str, Any]]],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Seething Whisper：单体雷伤 + 主目标 Shock + 其他 Shocked 目标追加雷伤."""
    if semantic.get("type") not in {"Single Target", "AoE ATK"} or raw.get("damage_type") != "Thunder":
        return None
    match = re.fullmatch(
        r"Deals Lightning DMG \((\d+(?:\.\d+)?)% ATK\) to a single target, with a(?: high)? chance "
        r"to Shock the target\.(?: And at the same time,| At the same time,) deals Lightning DMG "
        r"\((\d+(?:\.\d+)?)% ATK\) to (?:any other Shocked targets|all other Shocked targets)\.",
        semantic.get("desc") or "")
    shock_semantic = next((s for s in semantic_catalog or [] if s.get("name") == "Midnight Tumult"), None)
    shock_desc = (shock_semantic or {}).get("desc") or ""
    shock_match = re.search(r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\)(?: the target)?", shock_desc)
    chance_match = re.search(r"(\d+(?:\.\d+)?)% Base Chance", shock_desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or shock_match is None or chance_match is None or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    ratio = float(match.group(1)) / 100.0
    extra_ratio = float(match.group(2)) / 100.0
    if (abs(float(params[0]) - ratio) > 1e-9
            or abs(float(params[1]) - extra_ratio) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "thunder",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    condition = f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'"
    apply_hook = {
        "event": "on_action",
        "condition": condition,
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": float(chance_match.group(1)) / 100.0,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_SHOCK",
                "name": "Shock",
                "modifier_type": "dot",
                "dot_element": "thunder",
                "dot_ratio": float(shock_match.group(2)) / 100.0,
                "dot_base_chance": float(chance_match.group(1)) / 100.0,
                "duration": int(shock_match.group(1)),
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    extra_hook = {
        "event": "on_action",
        "condition": condition,
        "effects": [{
            "effect_type": "deal_damage",
            "target": {
                "pool": "allies",
                "where": "dot_kind($it, 'shock') and $it.actor_id != $event.target",
            },
            "damage_type": "thunder",
            "scaling_atk": extra_ratio,
        }],
    }
    return action, [apply_hook, extra_hook]


def _enemy_to_mourn_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """To Mourn the Departing：随机 N 目标 Atrophy 固伤、穿盾、削韧与受击回能."""
    if semantic.get("type") != "AoE ATK" or raw.get("damage_type") != "Quantum":
        return None
    match = re.fullmatch(
        r"Deals Quantum \"Atrophy DMG\" \((\d+(?:\.\d+)?)% Target Max HP\) "
        r"to (\d+) random targets\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    count = int(match.group(2))
    if count <= 0 or abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "deal_damage",
            "target": {"pool": "allies", "take": count, "mode": "random"},
            "damage_type": "quantum",
            "category": "atrophy",
            "amount": f"{ratio} * $target.max_hp",
            "toughness_dmg": int(sp_hit_base),
            "ignore_shield": True,
            "energy_grant": float(semantic.get("energy") or 0.0),
        }],
    }
    return action, hook


def _enemy_war_gear_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """War Gear：风伤后对已受 Wind Shear 的主目标立即结算一次 DoT."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Wind":
        return None
    match = re.fullmatch(
        r"Deals minor Wind DMG \((\d+(?:\.\d+)?)% ATK\) to a single target\. "
        r"If the target is currently suffering from Wind Shear, Wind Shear immediately causes DMG 1 time\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": semantic.get("name") or action_id,
        "action_type": "skill", "target_type": "single", "damage_type": "wind",
        "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": (
            f"$event.actor == $self.actor_id and $event.action_id == '{action_id}' "
            "and dot_kind($event.target, 'wind_shear')"),
        "effects": [{
            "effect_type": "trigger_dot", "target": "$event.target", "dot_element": "wind",
        }],
    }
    return action, hook


def _enemy_bleed_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体物理伤害 + Target Max HP Bleed → 攻击 action + 跳伤表达式 DoT."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Physical":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Physical DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), with a (?:high )?chance "
        r"\((\d+(?:\.\d+)?)% Base Chance\) to (?:cause|inflict) Bleed "
        r"\((\d+(?:\.\d+)?)% Target Max HP DoT, (\d+) Turns\)(?: on them)?\.", desc)
    per_stack = False
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Physical DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), with a (?:high )?chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to inflict (\d+) stacks? of Bleed "
            r"\((\d+(?:\.\d+)?)% Max HP DoT Per Stack, Max (\d+) Stacks, (\d+) Turns\)\.", desc)
        per_stack = True
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    if per_stack:
        initial_stacks = int(match.group(3))
        dot_ratio = float(match.group(4)) / 100.0
        max_stack = int(match.group(5))
        duration = int(match.group(6))
        if len(params) != 1 or abs(float(params[0]) - damage_ratio) > 1e-9:
            return None
    else:
        initial_stacks = 1
        dot_ratio = float(match.group(3)) / 100.0
        max_stack = 1
        duration = int(match.group(4))
        expected = [damage_ratio, base_chance, dot_ratio, float(duration)]
        if (len(params) != 4
                or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
            return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "physical",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    dot_expr = f"{dot_ratio} * $self.max_hp"
    if per_stack:
        dot_expr += " * max(1, $modifier.stacks)"
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_BLEED",
                "name": "Bleed",
                "modifier_type": "dot",
                "dot_element": "physical",
                "dot_ratio_expr": dot_expr,
                "dot_base_chance": base_chance,
                "stacks": initial_stacks,
                "duration": duration,
                "max_stack": max_stack,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_imprison_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体/AoE 直伤 + Imprisonment → 攻击 action + 原子推条/可选减速控制 hook."""
    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK"}:
        return None
    desc = semantic.get("desc") or ""
    single = skill_type == "Single Target"
    if single:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), with a high chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) of inflicting Imprisonment "
            r"\((\d+(?:\.\d+)?)% Action Delay, (\d+) Turn\)\.", desc)
    else:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK"
            r"(?: × (\d+))?\) to all targets, with a small chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to (?:inflict|cause) Imprisonment "
            r"\((\d+(?:\.\d+)?)% Action Delay, (\d+(?:\.\d+)?)% SPD Down, "
            r"(\d+) Turn\)(?: on the target)?\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    if single:
        per_hit_ratio = float(match.group(2)) / 100.0
        instances = 1
        base_chance = float(match.group(3)) / 100.0
        delay_ratio = float(match.group(4)) / 100.0
        spd_ratio = 0.0
        duration = int(match.group(5))
        expected = [per_hit_ratio, base_chance, float(duration), delay_ratio]
    else:
        per_hit_ratio = float(match.group(2)) / 100.0
        instances = int(match.group(3) or 1)
        base_chance = float(match.group(4)) / 100.0
        delay_ratio = float(match.group(5)) / 100.0
        spd_ratio = float(match.group(6)) / 100.0
        duration = int(match.group(7))
        expected = [per_hit_ratio * instances, base_chance, float(duration), delay_ratio, spd_ratio]
    if (match.group(1) != element or len(params) != len(expected)
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single" if single else "aoe",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": per_hit_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if instances > 1:
        action["instances"] = instances
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target" if single else "all_allies",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_IMPRISON",
                "name": "Imprisonment",
                "modifier_type": "debuff",
                "debuff_kind": "control",
                "control_kind": "imprison",
                "stat_effects": {"spd_pct": -spd_ratio} if spd_ratio else {},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
                "on_apply": [{
                    "effect_type": "delay_action", "target": "self",
                    "amount": delay_ratio * 100.0,
                }],
            },
        }],
    }
    return action, hook


def _enemy_def_impair_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """直伤 + DEF 减益（单体/AoE）→ 攻击 action + 概率 debuff hook."""
    skill_type = semantic.get("type")
    if skill_type not in {"Single Target", "AoE ATK", "Impair"}:
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (a single target|one designated target|all targets), "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to reduce "
        r"(the target's|their|the attacked target's) DEF \((\d+(?:\.\d+)?)%, (\d+) Turns?\)\.", desc)
    alternate = False
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (a single target|one designated target) and reduces the attacked target's DEF "
            r"\((\d+(?:\.\d+)?)%, (\d+) Turns?\)\.", desc)
        alternate = True
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    target_type = "aoe" if skill_type == "AoE ATK" else "single"
    expected_target = (("a single target", "one designated target")
                       if target_type == "single" else ("all targets",))
    if match.group(1) != element or match.group(3) not in expected_target:
        return None
    damage_ratio = float(match.group(2)) / 100.0
    if alternate:
        base_chance = 1.0
        def_ratio = float(match.group(4)) / 100.0
        duration = int(match.group(5))
    else:
        expected_possessive = {"the target's", "the attacked target's"} if target_type == "single" else {"their"}
        if match.group(5) not in expected_possessive:
            return None
        base_chance = float(match.group(4)) / 100.0
        def_ratio = float(match.group(6)) / 100.0
        duration = int(match.group(7))
    if len(params) == 1:
        expected = [damage_ratio]
    elif len(params) == 3:
        expected = [damage_ratio, def_ratio, float(duration)]
        if base_chance != 1.0:
            return None
    elif len(params) == 4:
        expected = [damage_ratio, base_chance, def_ratio, float(duration)]
    else:
        return None
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": target_type,
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target" if target_type == "single" else "all_allies",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_DEF_DOWN",
                "name": "DEF Reduction",
                "modifier_type": "debuff",
                "stat_effects": {"def_pct": -def_ratio},
                "duration": duration,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_vulnerability_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体直伤 + 承伤提高 → 攻击 action + vulnerability debuff hook."""
    if semantic.get("type") != "Single Target":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), with a high chance "
        r"\((\d+(?:\.\d+)?)% Base Chance\) to increase the DMG taken by "
        r"the attacked target \((\d+(?:\.\d+)?)%, (\d+) Turns\)\.", desc)
    alternate = False
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target) with a high chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to slightly increase the DMG taken by "
            r"the target \((\d+(?:\.\d+)?)%, (\d+) Turns\)\.", desc)
        alternate = True
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(3)) / 100.0
    vulnerability = float(match.group(4)) / 100.0
    duration = int(match.group(5))
    expected = ([damage_ratio, base_chance, float(duration), vulnerability] if alternate
                else [damage_ratio, base_chance, vulnerability, float(duration)])
    if (match.group(1) != element or len(params) != 4
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_VULNERABILITY",
                "name": "Vulnerability",
                "modifier_type": "debuff",
                "stat_effects": {"vulnerability": vulnerability},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_weaken_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体直伤 + Weaken → 攻击 action + 降伤 debuff hook."""
    if semantic.get("type") != "Single Target":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), with a chance "
        r"\((\d+(?:\.\d+)?)% Base Chance\) to Weaken them \((\d+) Turns\)\.", desc)
    explicit_ratio = False
    if not match:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"to (?:a single target|one designated target), with a high chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to inflict Weaken "
            r"\(-(\d+(?:\.\d+)?)% DMG Dealt, (\d+) Turns\)\.", desc)
        explicit_ratio = True
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(3)) / 100.0
    if match.group(1) != element or len(params) != 4:
        return None
    if explicit_ratio:
        weaken_ratio = float(match.group(4)) / 100.0
        duration = int(match.group(5))
        expected = [damage_ratio, weaken_ratio, base_chance, float(duration)]
    else:
        # mechanics 07 §7.4：Weaken=降低造成伤害；第三参数为降伤比例。
        weaken_ratio = float(params[2])
        duration = int(match.group(4))
        expected = [damage_ratio, base_chance, weaken_ratio, float(duration)]
    if (not 0 < weaken_ratio <= 1
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_WEAKEN",
                "name": "Weaken",
                "modifier_type": "debuff",
                "stat_effects": {"all_dmg": -weaken_ratio},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_effect_res_down_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体直伤 + Effect RES 降低 → 攻击 action + effect_res debuff hook."""
    if semantic.get("type") != "Single Target":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), with a chance "
        r"\((\d+(?:\.\d+)?)% Base Chance\) to reduce the target's Effect RES "
        r"\((\d+(?:\.\d+)?)%\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(3)) / 100.0
    res_ratio = float(match.group(4)) / 100.0
    if match.group(1) != element or len(params) != 3:
        return None
    # 100% 概率省略原始概率槽；后两项为减抗比例与持续回合。
    duration = int(params[2])
    expected = [damage_ratio, res_ratio, float(duration)]
    if (base_chance != 1.0 or duration <= 0 or float(params[2]) != duration
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_EFFECT_RES_DOWN",
                "name": "Effect RES Reduction",
                "modifier_type": "debuff",
                "stat_effects": {"effect_res": -res_ratio},
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_reverberation_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Sawing Evil → 直伤/Reverberation + 受击后 Strong Reverberation 两段 hooks."""
    aoe = semantic.get("type") == "AoE ATK"
    if semantic.get("type") not in {"Single Target", "AoE ATK"} or raw.get("damage_type") != "Physical":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Physical DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"(?:to a single target|to all targets) and has a (?:high )?chance "
        r"\((\d+(?:\.\d+)?)% Base Chance\) to inflict Reverberation "
        r"\((\d+) Turns\)(?: (?:to|on) the target)?\. After targets afflicted with Reverberation receive "
        r"an attack, they enter (?:the )?Strong Reverberation(?: state)? "
        r"\((\d+(?:\.\d+)?)% Action Delay, (\d+) Turn\) and then have (?:the )?Reverberation"
        r"(?: state)? dispelled\. Targets with Strong Reverberation cannot take action\.", desc)
    strong = match is not None
    if not strong:
        match = re.fullmatch(
            r"Deals (?:minor |massive )?Physical DMG \((\d+(?:\.\d+)?)% ATK\) "
            r"(?:to a single target|to all targets) and has a (?:high )?chance "
            r"\((\d+(?:\.\d+)?)% Base Chance\) to inflict Reverberation \((\d+) Turns\)\.", desc)
        if not match:
            return None
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer():
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    duration = int(match.group(3))
    delay_ratio = float(match.group(4)) / 100.0 if strong else 0.0
    strong_duration = int(match.group(5)) if strong else 0
    expected = [damage_ratio, base_chance, float(duration)]
    if (len(params) != 3
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe" if aoe else "single",
        "damage_type": "physical",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    reverb_id = f"ENEMY_{action_id}_REVERB"
    strong_id = f"ENEMY_{action_id}_STRONG_REVERB"
    initial_condition = f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'"
    if strong and not aoe:
        initial_condition += f" and not has_modifier($event.target, '{strong_id}')"
    initial_target = ({"pool": "allies", "where": f"not has_modifier($it, '{strong_id}')"}
                      if strong and aoe else ("all_allies" if aoe else "$event.target"))
    initial_hook = {
        "event": "on_action",
        "condition": initial_condition,
        "effects": [{
            "effect_type": "apply_modifier",
            "target": initial_target,
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": reverb_id,
                "name": "Reverberation",
                "modifier_type": "debuff",
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    strong_hook = {
        "event": "after_being_hit",
        "condition": f"has_modifier($event.target, '{reverb_id}')",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "modifier": {
                "modifier_id": strong_id,
                "name": "Strong Reverberation",
                "modifier_type": "debuff",
                "debuff_kind": "control",
                "control_kind": "strong_reverberation",
                "prevent_action": True,
                "duration": strong_duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
                "on_apply": [{
                    "effect_type": "delay_action", "target": "self",
                    "amount": delay_ratio * 100.0,
                }],
            },
        }, {
            "effect_type": "remove_modifier",
            "target": "$event.target",
            "modifier_id": reverb_id,
        }],
    }
    return action, [initial_hook, strong_hook] if strong else [initial_hook]


def _enemy_delay_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体直伤 + 确定/概率行动延后 → 攻击 action + delay_action hook."""
    if semantic.get("type") != "Single Target":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target) and delays "
        r"(?:their|the attacked target's) action(?: slightly)? "
        r"\((?:(\d+(?:\.\d+)?)% Base Chance, )?(\d+(?:\.\d+)?)%\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(3)) / 100.0 if match.group(3) else 1.0
    delay_ratio = float(match.group(4)) / 100.0
    expected = ([damage_ratio, delay_ratio] if match.group(3) is None
                else [damage_ratio, delay_ratio, base_chance])
    if (match.group(1) != element or len(params) != len(expected)
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "delay_action",
            "target": "$event.target",
            "amount": delay_ratio * 100.0,
            "apply_chance": base_chance,
        }],
    }
    return action, hook


def _enemy_spiral_arrow_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_id: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Spiral Arrow → 单体锁定支援 action + 目标侧 lock_on marker."""
    if (semantic.get("type") != "Lock On"
            or semantic.get("desc") != "Locks on to a single target. Cast End of Bow to this target in the next action."
            or (raw.get("param_list") or [])):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "modifier": {
                "modifier_id": f"ENEMY_{owner_id}_LOCK_ON",
                "name": "Lock On",
                "modifier_type": "debuff",
                "duration": 0,
                "max_stack": 1,
                "stack_mode": "refresh",
                "lock_on": True,
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_nihility_command_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], config: Optional[Dict[str, Any]],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Nihility's Command → 随机单体 lock_on + vulnerability marker."""
    marker_id = "MMonster_AML_Minion03_00_Target"
    if semantic.get("type") != "Lock On" or marker_id not in _config_modifier_names(config):
        return None
    match = re.fullmatch(
        r"Locks Onto \(Vulnerability \+(\d+(?:\.\d+)?)%\) a random unit on your team, "
        r"making them the target for incoming attacks from all of their enemies\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    if not match or len(params) != 2:
        return None
    vulnerability = float(match.group(1)) / 100.0
    duration = int(params[0])
    if (duration <= 0 or float(params[0]) != duration
            or abs(float(params[1]) - vulnerability) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        # 非伤害支援技复用 bounce 的随机单体选择；后续攻击由 lock_on 接管。
        "target_type": "bounce",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "modifier": {
                "modifier_id": marker_id,
                "name": "Nihility's Command",
                "modifier_type": "debuff",
                "stat_effects": {"vulnerability": vulnerability},
                # on_action 后挂，需 +1 才能跨越目标自身回合并锁定下一次敌方攻击。
                "duration": duration + 1,
                "max_stack": 1,
                "stack_mode": "refresh",
                "lock_on": True,
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_horn_clash_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Horn Clash → 单体量子伤害 + 追加一层公共 Entanglement."""
    if (semantic.get("name") != "Horn Clash" or semantic.get("type") != "Single Target"
            or raw.get("damage_type") != "Quantum"
            or semantic.get("desc") != "Deals Quantum DMG (320% ATK) to a single target, "
            "prioritizing Entangled targets, and applies one extra stack of Entanglement."):
        return None
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (len(params) != 1 or abs(float(params[0]) - 3.2) > 1e-9
            or sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": "Horn Clash",
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "quantum",
        "scaling": [{"atk": 3.2}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": 1.0,
            "modifier": {
                "modifier_id": "MCommon_Entangle",
                "name": "Entanglement",
                "modifier_type": "dot",
                "debuff_kind": "control",
                "control_kind": "entangle",
                "dot_element": "quantum",
                "dot_ratio": 0.6,
                "dot_base_chance": 1.0,
                "duration": 1,
                "max_stack": 5,
                "stack_mode": "refresh",
                "dispellable": True,
                "on_apply": [{
                    "effect_type": "delay_action", "target": "self", "amount": 45.0,
                }],
            },
        }],
    }
    return action, hook


def _enemy_end_of_bow_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_id: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """End of Bow → 单体量子伤害 + 纠缠延迟伤害/推条 + 解除锁定."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Quantum":
        return None
    match = re.fullmatch(
        r"Deals massive Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to a single target, "
        r"with a high chance(?: \((\d+(?:\.\d+)?)% Base Chance\))? to inflict Entanglement "
        r"\((\d+(?:\.\d+)?)% Action Delay, (\d+(?:\.\d+)?)% ATK Delayed DMG Per Stack\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0 if match.group(2) is not None else 1.0
    delay_ratio = float(match.group(3)) / 100.0
    dot_ratio = float(match.group(4)) / 100.0
    expected = [damage_ratio, delay_ratio, dot_ratio]
    if (base_chance != 1.0 or len(params) != 3
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "quantum",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": "MCommon_Entangle",
                "name": "Entanglement",
                "modifier_type": "dot",
                "debuff_kind": "control",
                "control_kind": "entangle",
                "dot_element": "quantum",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "duration": 1,
                "max_stack": 5,
                "stack_mode": "refresh",
                "dispellable": True,
                "on_apply": [{
                    "effect_type": "delay_action", "target": "self",
                    "amount": delay_ratio * 100.0,
                }],
            },
        }, {
            "effect_type": "remove_modifier",
            "target": "$event.target",
            "modifier_id": f"ENEMY_{owner_id}_LOCK_ON",
        }],
    }
    return action, hook


def _enemy_trashcan_enhance_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """The Can's Tribulations → 每次使用 ATK 加成翻倍的永久 self modifier."""
    if semantic.get("type") != "Enhance":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Increases this unit's ATK\.?<ref group=\"Note\">(.+)</ref>\.? "
        r"This effect is stackable and unremovable\.", desc)
    params = raw.get("param_list") or []
    if not match or len(params) != 1:
        return None
    note = match.group(1)
    doubling = ("Every subsequent use of The Can's Tribulations will double the existing ATK bonus")
    if doubling not in note:
        return None
    initials = [float(x) / 100.0 for x in re.findall(
        r"initial ATK bonus is (\d+(?:\.\d+)?)%", note)]
    if not any(abs(float(params[0]) - initial) <= 1e-9 for initial in initials):
        return None
    initial = float(params[0])
    action_id = str(raw["skill_id"])
    modifier_id = f"ENEMY_{action_id}_ATK_UP"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "ATK Boost",
                "modifier_type": "buff",
                # replace 前烘焙旧层数：首次 1×，其后 2×/4×/8×，层数同步保留。
                "stacks": f"stacks($self, '{modifier_id}') + 1",
                "stat_effects": {
                    "atk_pct": f"{initial} * (2 ** stacks($self, '{modifier_id}'))",
                },
                "duration": 0,
                "stack_mode": "replace",
                "dispellable": False,
            },
        }],
    }
    return action, hook


def _enemy_wrathful_roar_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Wrathful Roar：获得 3 层 Gusto 并标记监视目标；战技会转移标记."""
    if (semantic.get("type") != "Lock On" or raw.get("trigger_key") != "Skill04"
            or (raw.get("param_list") or [])):
        return None
    if semantic.get("desc") != (
            "Gains 3 stacks of Gusto and marks a random target for Monitoring. Until Gusto is "
            "exhausted, any target that uses their Skill will become the new Monitored target."):
        return None
    action_id = str(raw["skill_id"])
    marker_id = f"ENEMY_{action_id}_MONITORED"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "bounce",
        "energy_gain": 0,
        "energy_grant": 0.0,
        "resource_gain": {"gusto": 3},
    }
    marker = {
        "modifier_id": marker_id, "name": "Monitored", "modifier_type": "debuff",
        "lock_on": True, "duration": 0, "max_stack": 1,
        "stack_mode": "replace", "dispellable": True,
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [
            {"effect_type": "remove_modifier", "target": "all_allies", "modifier_id": marker_id,
             "reason": "monitor_retarget"},
            {"effect_type": "apply_modifier", "target": "$event.target", "modifier": marker},
        ],
    }
    retarget_hook = {
        "event": "on_action",
        "condition": "$event.actor_type == 'character' and $event.action_type == 'skill' and res_gusto > 0",
        "effects": [
            {"effect_type": "remove_modifier", "target": "all_allies", "modifier_id": marker_id,
             "reason": "monitor_retarget"},
            {"effect_type": "apply_modifier", "target": "$event.actor", "modifier": marker},
        ],
    }
    return action, [apply_hook, retarget_hook]


def _enemy_simian_strike_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Simian Strike：消耗 1 层 Gusto 攻击监视目标，耗尽后移除标记."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Quantum":
        return None
    if semantic.get("desc") != (
            "Consumes 1 stack of Gusto and deals Quantum DMG (475% ATK) to a Monitored target."):
        return None
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (len(params) != 1 or abs(float(params[0]) - 4.75) > 1e-9
            or sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    action_id = str(raw["skill_id"])
    marker_id = f"ENEMY_{action_id[:-2]}04_MONITORED"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "quantum",
        "scaling": [{"atk": 4.75}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
        "resource_gain": {"gusto": -1},
        "available_if": "res_gusto > 0",
    }
    cleanup_hook = {
        "event": "on_action",
        "condition": (
            f"$event.actor == $self.actor_id and $event.action_id == '{action_id}' "
            "and res_gusto <= 0"),
        "effects": [{
            "effect_type": "remove_modifier", "target": "all_allies", "modifier_id": marker_id,
            "reason": "gusto_exhausted",
        }],
    }
    return action, cleanup_hook


def _enemy_fiery_majesty_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Fiery Majesty：每次施放叠一层 20% 增伤，持续 2 回合、最多 3 层."""
    if semantic.get("type") != "Enhance" or semantic.get("desc") != (
            "Increases DMG dealt (20%, 2 Turns). This DMG boosting effect is stackable "
            "(Max 3 Stacks)."):
        return None
    params = raw.get("param_list") or []
    if len(params) != 3 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [0.2, 2.0, 3.0])):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_FIERY_MAJESTY",
                "name": "Fiery Majesty", "modifier_type": "buff",
                "stat_exprs": {"all_dmg": f"0.2 * stacks($self, 'ENEMY_{action_id}_FIERY_MAJESTY')"},
                # on_action 后挂载，当回合末先走字；+1 保留声明的两回合。
                "duration": 3, "max_stack": 3, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_allargando_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Allargando → Max HP 护盾 + 增伤/减伤 + 韧性锁."""
    if (semantic.get("type") != "Enhance"
            or semantic.get("desc") != "Enters the \"If We Live In the Light\" state, gains a Shield "
            "(12.5% Max HP), increases the DMG dealt (30%), decreases the DMG taken (75%), "
            "and makes Toughness immune to reduction."):
        return None
    params = raw.get("param_list") or []
    expected = [0.125, 0.3, 0.75]
    if len(params) != 3 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_ALLARGANDO",
                "name": "If We Live In the Light",
                "modifier_type": "buff",
                "stat_effects": {"all_dmg": 0.3, "dmg_dmg_reduction": 0.75},
                "duration": 0,
                "max_stack": 1,
                "stack_mode": "refresh",
                "toughness_lock": True,
                "shield": {"scaling": {"hp": 0.125}},
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_defense_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Hardy Leaf Sheath → self 加防 + toughness_lock modifier."""
    if semantic.get("type") != "Defense":
        return None
    match = re.fullmatch(
        r"Increases DEF \((\d+(?:\.\d+)?)%, (\d+) Turn\)\. "
        r"Toughness cannot be reduced\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    if not match or len(params) != 2:
        return None
    ratio = float(match.group(1)) / 100.0
    duration = int(match.group(2))
    if abs(float(params[0]) - ratio) > 1e-9 or float(params[1]) != duration:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_HARDY_SHEATH",
                "name": "Hardy Leaf Sheath",
                "modifier_type": "buff",
                "stat_effects": {"def_pct": ratio},
                # on_action 后挂，当前回合末先走字；+1 才能覆盖声明的下一回合。
                "duration": duration + 1,
                "max_stack": 1,
                "stack_mode": "refresh",
                "toughness_lock": True,
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _config_modifier_names(config: Optional[Dict[str, Any]]) -> set[str]:
    """ConfigAI 引用的全部 modifier 名（TargetAlias/UseSkill 之外的静态证据）."""
    found: set[str] = set()
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            name = value.get("ModifierName")
            if isinstance(name, dict):
                name = name.get("Value")
            if isinstance(name, str):
                found.add(name)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    if config:
        walk(config)
    return found


def _escape_charge_ids(config: Optional[Dict[str, Any]]) -> Dict[int, str]:
    """从 ConfigAI 提取 EscapingCharge01/02 的实际 modifier id（不使用文件名猜名）."""
    found: Dict[int, str] = {}
    for name in _config_modifier_names(config):
        for index in (1, 2):
            if name.endswith(f"EscapingCharge0{index}"):
                found[index] = name
    return found


def _enemy_flee_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], config: Optional[Dict[str, Any]] = None,
) -> Optional[tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    """扑满倒计时/立即逃跑 → self 支援 action，立即项附 leave_battle."""
    if semantic.get("type") != "Others" or (raw.get("param_list") or []):
        return None
    desc = semantic.get("desc") or ""
    waiting = {
        "The Treasure Trotter got spooked and will flee in 2 turns.": 1,
        "The Trotter got spooked and will flee in 2 turns.": 1,
        "The Treasure Trotter is panicking and will flee in 1 turn.": 2,
    }
    immediate = {"The Trotter flees in an instant.", "When taking action, this unit leaves the battle."}
    if desc not in waiting and desc not in immediate:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    if desc in waiting:
        charge_ids = _escape_charge_ids(config)
        if not charge_ids:
            return action, None
        if len(charge_ids) != 2:
            return None
        modifier_id = charge_ids[waiting[desc]]
        hook = {
            "event": "on_action",
            "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
            "effects": [{
                "effect_type": "apply_modifier",
                "target": "self",
                "modifier": {
                    "modifier_id": modifier_id,
                    "name": modifier_id,
                    "modifier_type": "buff",
                    "duration": 0,
                    "singleton_group": "escape_charge",
                    "dispellable": False,
                },
            }],
        }
        return action, hook
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{"effect_type": "leave_battle", "target": "self"}],
    }
    return action, hook


def _enemy_timed_charge_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """无额外效果的定时蓄力 → self 支援 action，下一技能由原始序列/ConfigAI 推进."""
    if semantic.get("type") not in {"Charge", "Charging"} or (raw.get("param_list") or []):
        return None
    desc = semantic.get("desc") or ""
    entry = (
        r"(?:Enters (?:the )?(?:\"[^\"]+\"|[A-Za-z ]+) state"
        r"|Enters Japa|This unit enters the \"[^\"]+\" state)"
    )
    if not (re.fullmatch(r"The next action (?:uses|casts) .+\.", desc)
            or re.fullmatch(
                entry + r"\. (?:Uses|Casts|Cast) .+ (?:in|during|for) the next (?:action|turn)\.",
                desc)):
        return None
    action_id = str(raw["skill_id"])
    return {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }


def _enemy_outrage_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Outrage 单体/自爆扩散 → 直接攻击 + 暴怒控制；自爆件附加死亡链."""
    if semantic.get("type") != "Impair" or raw.get("damage_type") != "Wind":
        return None
    desc = semantic.get("desc") or ""
    params = raw.get("param_list") or []
    self_destruct = False
    if desc == ('Deals minor Wind DMG (200% ATK) to one target with a high chance '
                '(100% Base Chance) of inflicting "Outrage." Targets afflicted by "Outrage" '
                'cannot take action for a number of turns and will attack a random unit friendly to this unit.'):
        if len(params) != 2:
            return None
        damage_ratio = duration = 2.0
        adjacent_ratio = None
        target_type = "single"
    elif desc == ('Detonates self and deals Wind DMG (300% ATK) to a target and its adjacent targets, '
                  'with a high chance (100% Base Chance) to cause Outrage (2 Turns) to the target.'):
        if len(params) != 3:
            return None
        damage_ratio = adjacent_ratio = 3.0
        duration = 2.0
        target_type = "blast"
        self_destruct = True
    else:
        return None
    expected = [damage_ratio] + ([adjacent_ratio] if adjacent_ratio is not None else []) + [duration]
    sp_hit_base = raw.get("sp_hit_base")
    if (sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer()
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": target_type,
        "damage_type": "wind",
        "scaling": [{"atk": damage_ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if adjacent_ratio is not None:
        action["scaling_blast"] = [{"atk": adjacent_ratio}]
    effects = [{
        "effect_type": "apply_modifier",
        "target": "$event.target",
        "apply_chance": 1.0,
        "modifier": {
            "modifier_id": "ENEMY_OUTRAGE",
            "name": "Outrage",
            "modifier_type": "debuff",
            "debuff_kind": "control",
            "control_kind": "outrage",
            "duration": int(duration),
            "max_stack": 1,
            "stack_mode": "refresh",
            "dispellable": True,
        },
    }]
    if self_destruct:
        effects.append({"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0})
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": effects,
    }
    return action, hook


def _enemy_spirit_whisper_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Spirit Whisper：120% 基础概率支配三回合并立即触发强制普攻."""
    if semantic.get("type") != "Impair" or semantic.get("desc") != (
            "Has a high chance (120% Base Chance) of Dominating (3 Turns) a single target and "
            "Advancing their action forward to immediately use their Basic ATK on a random ally "
            "of theirs."):
        return None
    params = raw.get("param_list") or []
    if len(params) != 5 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [1.0, 2.5, 1.5, 0.5, 1.2])):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target", "apply_chance": 1.2,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_DOMINATE",
                "name": "Dominated", "modifier_type": "debuff",
                "debuff_kind": "control", "control_kind": "dominate",
                "duration": 3, "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
                "on_apply": [{"effect_type": "immediate_action", "target": "self"}],
            },
        }],
    }
    return action, hook


def _enemy_shield_reflect_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], config: Optional[Dict[str, Any]],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Silvermane Lieutenant 盾反：受击标记攻击者，立即行动并由 ConfigAI 施放穿刺."""
    marker_id = "MMonster_W1_Soldier03_00_ReturnAttackTarget"
    descriptions = {
        'Enters the Counter state. When attacked by a single character, acts immediately and casts "Pierce" on the attacker.',
        "Enters the Counter state: When attacked, acts immediately and uses Pierce on the attacker.",
    }
    if (str(raw.get("skill_id")) not in {"100301003", "100301203", "100301303"}
            or semantic.get("type") not in {"Others", None}
            or semantic.get("desc") not in descriptions
            or (raw.get("param_list") or []) or marker_id not in _config_modifier_names(config)):
        return None
    action_id = str(raw["skill_id"])
    pierce_action_id = f"{action_id[:-1]}2"
    counter_id = f"ENEMY_{action_id}_COUNTER"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": counter_id, "name": "Counter", "modifier_type": "buff",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    counter_hook = {
        "event": "after_being_hit",
        "condition": f"$event.target == $self.actor_id and has_modifier($self, '{counter_id}')",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.source",
            "modifier": {
                "modifier_id": marker_id, "name": marker_id, "modifier_type": "debuff",
                "duration": 0, "lock_on": True, "dispellable": False,
            },
        }, {
            "effect_type": "immediate_action", "target": "self",
        }, {
            "effect_type": "remove_modifier", "target": "self", "modifier_id": counter_id,
            "reason": "counter_resolved",
        }],
    }
    cleanup_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{pierce_action_id}'",
        "effects": [{
            "effect_type": "remove_modifier", "target": "$event.target", "modifier_id": marker_id,
            "reason": "counter_resolved",
        }],
    }
    return action, [apply_hook, counter_hook, cleanup_hook]


def _enemy_unstable_forcefield_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Automaton Beetle：伤害后获得一次性 Barrier，下一次受击伤害归零."""
    if semantic.get("name") != "Unstable Forcefield" or semantic.get("desc") != (
            "Deals Physical DMG (300% ATK) to a single target, and grants a Barrier to another "
            "friendly unit.<ref group=\"Note\">Contrary to this wording, the Barrier is always "
            "applied to the Automaton Beetle itself.</ref> The Barrier nullifies all DMG received "
            "except for DoT until after the friendly unit is attacked."):
        return None
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (raw.get("damage_type") != "Physical" or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1
            or abs(float(params[0]) - 3.0) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 3.0}],
        "toughness_dmg": int(sp_hit_base), "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    barrier_id = f"ENEMY_{action_id}_BARRIER"
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": barrier_id, "name": "Barrier", "modifier_type": "buff",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    block_hook = {
        "event": "before_take_damage",
        "condition": f"$event.target == $self.actor_id and has_modifier($self, '{barrier_id}')",
        "effects": [{
            "effect_type": "modify_amount", "amount": 0,
        }, {
            "effect_type": "remove_modifier", "target": "self", "modifier_id": barrier_id,
            "reason": "barrier_consumed",
        }],
    }
    return action, [apply_hook, block_hook]


def _enemy_garrison_barrier_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Garrison Aura Field：给另一友方一次性 Barrier，受击免伤并消耗."""
    if semantic.get("type") != "Defense" or (raw.get("param_list") or []):
        return None
    if semantic.get("desc") != (
            "Grants a Barrier to another friendly unit. The Barrier nullifies all DMG received "
            "except for DoT until after the friendly unit is attacked."):
        return None
    action_id = str(raw["skill_id"])
    barrier_id = f"ENEMY_{action_id}_BARRIER"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": {"pool": "enemies", "where": "$it.actor_id != $self.actor_id", "take": 1},
            "modifier": {
                "modifier_id": barrier_id, "name": "Barrier", "modifier_type": "buff",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    block_hook = {
        "event": "before_take_damage",
        "condition": f"has_modifier($event.target, '{barrier_id}')",
        "effects": [{
            "effect_type": "modify_amount", "amount": 0,
        }, {
            "effect_type": "remove_modifier", "target": "$event.target", "modifier_id": barrier_id,
            "reason": "barrier_consumed",
        }],
    }
    return action, [apply_hook, block_hook]


def _enemy_melt_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Searing Prowler Melt：攻击灼烧目标后叠增伤（每次行动 1 层）."""
    if (str(raw.get("skill_id")) != "102301003" or semantic.get("name") != "Melt"
            or semantic.get("desc") != "After attacking a Burned target, receives a DMG increase "
            "(6% Per Stack, 3 Turns, Max 5 Stacks)."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 2 or abs(float(params[0]) - 0.06) > 1e-9 or float(params[1]) != 3.0:
        return []
    modifier_id = "ENEMY_102301003_MELT"
    return [{
        "event": "on_action",
        "condition": "$event.actor == $self.actor_id and dot_kind($event.target, 'burn')",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Melt",
                "modifier_type": "buff",
                "stat_exprs": {"all_dmg": f"0.06 * stacks($self, '{modifier_id}')"},
                "stacks": f"min(stacks($self, '{modifier_id}') + 1, 5)",
                "max_stack": 5,
                # 自身 on_action 后挂载，当回合末先走字；+1 保留声明的三回合。
                "duration": 4,
                "stack_mode": "replace",
                "dispellable": True,
            },
        }],
    }]


def _enemy_living_eternal_flame_passive(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Living Eternal Flame：自身被击杀时，击杀者获得两回合 SPD/DMG 增益."""
    if semantic.get("name") != "Living Eternal Flame" or semantic.get("desc") != (
            "When receiving a killing blow, increases the attacker's SPD (30%, 2 Turns) "
            "and DMG dealt (30%, 2 Turns)."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 3 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [0.3, 0.3, 2.0])):
        return []
    return [{
        "event": "on_kill",
        "condition": "$event.target == $self.actor_id",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "$event.source",
            "modifier": {
                "modifier_id": "ENEMY_LIVING_ETERNAL_FLAME",
                "name": "Living Eternal Flame",
                "modifier_type": "buff",
                "stat_effects": {"spd_pct": 0.3, "all_dmg": 0.3},
                "duration": 2,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }]


def _enemy_energy_burst_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Energy Burst：自身被击杀时，全队恢复固定能量."""
    if semantic.get("name") != "Energy Burst" or semantic.get("desc") != (
            "All targets' Energy gets regenerated (15) after this unit suffers a killing blow."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 1 or abs(float(params[0]) - 15.0) > 1e-9:
        return []
    return [{
        "event": "on_kill",
        "condition": "$event.target == $self.actor_id",
        "effects": [{"effect_type": "gain_energy", "target": "all_allies", "amount": 15.0}],
    }]


def _enemy_fleeting_veil_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fleeting Veil：四类攻击减伤 10%，攻击后 20% 基础概率禁锢目标."""
    if semantic.get("name") != "Fleeting Veil" or semantic.get("desc") != (
            "Slightly reduces the Basic ATK, Skill, Ultimate, and Follow-up ATK DMG received by "
            "this unit (10%), with a small chance (20% Base Chance) to inflict Imprisonment "
            "(50% Action Delay, 1 Turn) on the target attacked by Decaying Shadow."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 3 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [0.1, 0.2, 0.5])):
        return []
    modifier_id = f"ENEMY_{raw['skill_id']}_FLEETING_VEIL"
    return [{
        "event": "before_take_damage",
        "condition": (
            "$event.target == $self.actor_id and "
            "$event.action_type in ['basic', 'skill', 'ultimate', 'follow_up']"),
        "effects": [{"effect_type": "modify_amount", "amount": "$event.amount * 0.9"}],
    }, {
        "event": "on_action",
        "condition": "$event.actor == $self.actor_id and $event.target != $self.actor_id",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target", "apply_chance": 0.2,
            "modifier": {
                "modifier_id": modifier_id, "name": "Imprisonment", "modifier_type": "debuff",
                "debuff_kind": "control", "control_kind": "imprison",
                "duration": 1, "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
                "on_apply": [{"effect_type": "delay_action", "target": "self", "amount": 50.0}],
            },
        }],
    }]


def _enemy_tremble_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Tremble：攻击 Shocked 主目标后立即结算一次 Shock，不消耗持续回合."""
    if (semantic.get("name") != "Tremble"
            or semantic.get("desc") != "If the target is currently Shocked, directly causes Shock DMG 1 time."
            or (raw.get("param_list") or [])):
        return []
    return [{
        "event": "on_action",
        "condition": "$event.actor == $self.actor_id and dot_kind($event.target, 'shock')",
        "effects": [{
            "effect_type": "trigger_dot", "target": "$event.target", "dot_element": "thunder",
        }],
    }]


def _enemy_cruelty_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Cruelty：友方或支配目标攻击 Shocked 目标时追加一次雷伤，禁止自递归."""
    if semantic.get("name") != "Cruelty" or semantic.get("desc") != (
            "When friendly units or Dominated targets attack the Shocked primary target, "
            "unleash an extra Lightning attack (100% ATK)."):
        return []
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (raw.get("damage_type") != "Thunder" or len(params) != 1
            or abs(float(params[0]) - 1.0) > 1e-9 or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return []
    return [{
        "event": "after_being_hit",
        "condition": (
            "$event.action_id != 'hook_cruelty' and dot_kind($event.target, 'shock') and "
            "(actor_type_of($event.source) == 'monster' or controlled($event.source, 'dominate'))"),
        "effects": [{
            "effect_type": "deal_damage", "name": "cruelty", "target": "$event.target",
            "damage_type": "thunder", "scaling_atk": 1.0,
            "toughness_dmg": int(sp_hit_base),
            "energy_grant": float(semantic.get("energy") or 0.0),
        }],
    }]


def _enemy_expedite_verdict_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Expedite Verdict：未击破减伤，击破时推条/自伤并在击破期承伤提高."""
    if semantic.get("name") != "Expedite Verdict" or semantic.get("desc") != (
            "Reduces DMG received (50%) when not Weakness Broken. When this unit is Weakness Broken, "
            "its action will be further delayed (200%), and deals massive Imaginary DMG (20% Max HP) "
            "to this unit. While Weakness Broken, this unit receives increased DMG (50%)."):
        return []
    params = raw.get("param_list") or []
    expected = [0.5, 2.0, 0.5, 0.2]
    if len(params) != 4 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, expected)):
        return []
    skill_id = str(raw["skill_id"])
    guard_id = f"ENEMY_{skill_id}_GUARD"
    exposed_id = f"ENEMY_{skill_id}_EXPOSED"
    return [{
        "event": "on_battle_start",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": guard_id, "name": "Expedite Verdict Guard", "modifier_type": "buff",
                "stat_effects": {"dmg_dmg_reduction": 0.5}, "enable_if": "broken_of($self) == 0",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }, {
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": exposed_id, "name": "Expedite Verdict Exposed", "modifier_type": "buff",
                "stat_effects": {"vulnerability": 0.5}, "enable_if": "broken_of($self) > 0",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }, {
        "event": "on_break",
        "condition": "$event.target == $self.actor_id",
        "effects": [{
            "effect_type": "delay_action", "target": "self", "amount": 200.0,
        }, {
            "effect_type": "deal_damage", "target": "self", "damage_type": "imaginary",
            "scaling_hp": 0.2,
        }],
    }]


def _enemy_disembodied_shell_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Disembodied Shell：Safeguard 未击破减伤，击破推条并转为承伤提高."""
    if semantic.get("name") != "Disembodied Shell" or semantic.get("desc") != (
            "Enters the Safeguard state. When not Weakness Broken, reduces DMG received (60%). "
            "Once Weakness is Broken, action will be additionally delayed (75%). "
            "After Weakness is Broken, increases DMG received (50%)."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 3 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, [0.6, 0.75, 0.5])):
        return []
    skill_id = str(raw["skill_id"])
    guard_id = f"ENEMY_{skill_id}_SAFEGUARD"
    exposed_id = f"ENEMY_{skill_id}_SAFEGUARD_BREACH"
    return [{
        "event": "on_battle_start",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": guard_id, "name": "Safeguard", "modifier_type": "buff",
                "stat_effects": {"dmg_dmg_reduction": 0.6}, "enable_if": "broken_of($self) == 0",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }, {
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": exposed_id, "name": "Safeguard Breach", "modifier_type": "buff",
                "stat_effects": {"vulnerability": 0.5}, "enable_if": "broken_of($self) > 0",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }, {
        "event": "on_break",
        "condition": "$event.target == $self.actor_id",
        "effects": [{"effect_type": "delay_action", "target": "self", "amount": 75.0}],
    }]


def _enemy_thick_skinned_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Thick-Skinned：开局 DEF +150%，被击破后解除 Enhance Defense."""
    if semantic.get("name") != "Thick-Skinned" or semantic.get("desc") != (
            "At the start of battle and upon entering a new phase, this unit enters the "
            "\"Enhance Defense\" state, greatly increasing this unit's DEF (150%). "
            "After being Weakness Broken, dispels the \"Enhanced Defense\" state."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 1 or abs(float(params[0]) - 1.5) > 1e-9:
        return []
    modifier_id = f"ENEMY_{raw['skill_id']}_ENHANCE_DEFENSE"
    return [{
        "event": "on_battle_start",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": modifier_id, "name": "Enhance Defense", "modifier_type": "buff",
                "stat_effects": {"def_pct": 1.5}, "duration": 0,
                "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }, {
        "event": "on_break",
        "condition": "$event.target == $self.actor_id",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self", "modifier_id": modifier_id,
            "reason": "weakness_broken",
        }],
    }]


def _enemy_seeding_core_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Seeding Core：给单体目标施加 Spur of Thunderwoe 标记."""
    if (semantic.get("name") != "Seeding Core"
            or semantic.get("desc") != "Inflicts a single target with Spur of Thunderwoe."
            or (raw.get("param_list") or [])):
        return None
    action_id = str(raw["skill_id"])
    marker_id = "ENEMY_202202001_SPUR"
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "single", "energy_gain": 0, "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target",
            "modifier": {
                "modifier_id": marker_id, "name": "Spur of Thunderwoe", "modifier_type": "debuff",
                # 同 id 只保留最新施加者，后续 Core Rupture 才能精确归因到该敌人。
                "duration": 0, "max_stack": 1, "stack_mode": "replace", "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_core_rupture_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Core Rupture：死亡时雷伤自己施加过 Spur 的目标，回能并清除标记."""
    if semantic.get("name") != "Core Rupture" or semantic.get("desc") != (
            "Upon receiving a killing blow, this unit deals Lightning DMG (450% ATK) to any targets "
            "that were inflicted with Spur of Thunderwoe by them. Afterward, Spur of Thunderwoe on "
            "these targets will be removed."):
        return []
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    energy = float(semantic.get("energy") or 0.0)
    if (raw.get("damage_type") != "Thunder" or len(params) != 1
            or abs(float(params[0]) - 4.5) > 1e-9 or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer() or energy != 15.0):
        return []
    marker_id = "ENEMY_202202001_SPUR"
    marked = {
        "pool": "allies",
        # 本怪唯一的 debuff 即 Spur；与 modifier 名联立即可锁定“由该敌人施加”。
        "where": f"has_modifier($it, '{marker_id}') and debuff_count($it, $self.actor_id) > 0",
    }
    marked_alive = {**marked, "where": marked["where"] + " and actor_alive($it)"}
    return [{
        "event": "on_kill",
        "condition": "$event.target == $self.actor_id",
        "effects": [{
            "effect_type": "deal_damage", "target": marked, "damage_type": "thunder",
            "scaling_atk": 4.5, "toughness_dmg": int(sp_hit_base),
        }, {
            "effect_type": "gain_energy", "target": marked_alive, "amount": energy,
        }, {
            "effect_type": "remove_modifier", "target": marked, "modifier_id": marker_id,
            "reason": "core_rupture",
        }],
    }]


def _enemy_respite_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Respite By The Waters：指定行动类攻击计数，达到阈值立即行动并清零."""
    if semantic.get("name") != "Respite By The Waters" or semantic.get("desc") != (
            "Advances action (100%) after taking a certain number of attacks (5) from Basic ATK, "
            "Skill, Ultimate, or Memosprite Skill. When in the \"405301001\" state, decreases the "
            "number of attacks required to advance action (1)."):
        return []
    params = raw.get("param_list") or []
    if len(params) != 1 or float(params[0]) != 5.0:
        return []
    rid = "_respite_count"
    threshold = "has_modifier($self, '405301001') ? 1 : 5"
    return [{
        "event": "on_battle_start",
        "effects": [{"effect_type": "set_resource", "target": "self", "resource_id": rid, "amount": 0}],
    }, {
        "event": "after_being_hit",
        "condition": (
            "$event.target == $self.actor_id and "
            "$event.action_type in ['basic', 'skill', 'ultimate', 'memosprite_skill']"),
        "effects": [{"effect_type": "gain_resource", "target": "self", "resource_id": rid, "amount": 1}],
    }, {
        "event": "on_resource_gain",
        "condition": (
            f"$event.actor == $self.actor_id and $event.resource_id == '{rid}' "
            f"and $event.current >= ({threshold})"),
        "effects": [{
            "effect_type": "immediate_action", "target": "self",
        }, {
            "effect_type": "set_resource", "target": "self", "resource_id": rid, "amount": 0,
        }],
    }]


def _enemy_polis_protector_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Polis Protector / War Armor：受击扣层、破甲自伤推条回能、回合末复原."""
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Possesses a number of \"War Armor\" stacks \((\d+)\), which decreases DMG taken "
        r"\((\d+(?:\.\d+)?)%\)\. Loses 1 stack of \"War Armor\" on this unit after being attacked\. "
        r"When at 0 stacks, \"War Armor\" will be destroyed, dealing massive Imaginary DMG "
        r"\((\d+(?:\.\d+)?)% Max HP\) to this unit and delaying their action "
        r"\((\d+(?:\.\d+)?)%\)\. The target that destroyed \"War Armor\" will regenerate Energy "
        r"\((\d+(?:\.\d+)?)% Max Energy\)\. After \"War Armor\" is destroyed, this unit will also "
        r"additionally take minor Imaginary DMG \((\d+(?:\.\d+)?)% Max HP\) when attacked\. "
        r"\"War Armor\" will be restored to maximum stacks at the end of this unit's turn\.", desc)
    if semantic.get("name") != "Polis Protector" or not match:
        return []
    stacks = int(match.group(1))
    reduction = float(match.group(2)) / 100.0
    self_damage = float(match.group(3)) / 100.0
    delay = float(match.group(4)) / 100.0
    energy = float(match.group(5)) / 100.0
    extra_damage = float(match.group(6)) / 100.0
    expected = [float(stacks), delay, reduction, extra_damage, energy, self_damage]
    params = raw.get("param_list") or []
    if (stacks <= 0 or len(params) != 6
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return []
    skill_id = str(raw["skill_id"])
    rid = "_war_armor"
    armor_id = f"ENEMY_{skill_id}_WAR_ARMOR"
    breaker_id = f"ENEMY_{skill_id}_WAR_ARMOR_BREAKER"
    breaker_pool = {"pool": "all", "where": f"has_modifier($it, '{breaker_id}')"}
    external_hit = "$event.target == $self.actor_id and $event.source != $self.actor_id"
    return [{
        "event": "on_battle_start",
        "effects": [{
            "effect_type": "set_resource", "target": "self", "resource_id": rid, "amount": stacks,
        }, {
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": armor_id, "name": "War Armor", "modifier_type": "buff",
                "stat_effects": {"dmg_dmg_reduction": reduction}, "enable_if": "res__war_armor > 0",
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }, {
        "event": "after_being_hit",
        "condition": f"{external_hit} and res__war_armor == 1",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.source",
            "modifier": {
                "modifier_id": breaker_id, "name": "War Armor Breaker", "modifier_type": "buff",
                "duration": 0, "max_stack": 1, "stack_mode": "replace", "dispellable": False,
            },
        }],
    }, {
        "event": "after_being_hit",
        "condition": f"{external_hit} and res__war_armor > 0",
        "effects": [{"effect_type": "gain_resource", "target": "self", "resource_id": rid, "amount": -1}],
    }, {
        "event": "on_resource_gain",
        "condition": (
            f"$event.actor == $self.actor_id and $event.resource_id == '{rid}' "
            "and $event.amount < 0 and $event.current <= 0"),
        "effects": [{
            "effect_type": "deal_damage", "target": "self", "damage_type": "imaginary",
            "scaling_hp": self_damage,
        }, {
            "effect_type": "delay_action", "target": "self", "amount": delay * 100.0,
        }, {
            "effect_type": "gain_energy", "target": breaker_pool,
            "amount": f"$target.max_energy * {energy}",
        }, {
            "effect_type": "remove_modifier", "target": breaker_pool, "modifier_id": breaker_id,
            "reason": "war_armor_destroyed",
        }],
    }, {
        "event": "after_being_hit",
        "condition": f"{external_hit} and res__war_armor <= 0",
        "effects": [{
            "effect_type": "deal_damage", "target": "self", "damage_type": "imaginary",
            "scaling_hp": extra_damage,
        }],
    }, {
        "event": "on_turn_end",
        "condition": "$event.actor == $self.actor_id",
        "effects": [{"effect_type": "set_resource", "target": "self", "resource_id": rid, "amount": stacks}],
    }]


def _enemy_inferno_stove_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Inferno Stove：攻击概率减速；受击或承受 DoT 时累积 Stove Heating."""
    if semantic.get("name") != "Inferno Stove" or semantic.get("desc") != (
            "When attacking, this unit has a chance (50% Base Chance) to Slow (SPD -20%, 2 Turns) "
            "the target. When this unit is attacked or takes DoT, gains 1 stack of Stove Heating."):
        return []
    params = raw.get("param_list") or []
    expected = [0.0, 0.5, 0.2, 2.0]
    if len(params) != 4 or any(abs(float(param) - value) > 1e-9
                               for param, value in zip(params, expected)):
        return []
    skill_id = str(raw["skill_id"])
    rid = "_stove_heating"
    return [{
        "event": "on_battle_start",
        "effects": [{"effect_type": "set_resource", "target": "self", "resource_id": rid, "amount": 0}],
    }, {
        "event": "on_action",
        "condition": "$event.actor == $self.actor_id and $event.target != $self.actor_id",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target", "apply_chance": 0.5,
            "modifier": {
                "modifier_id": f"ENEMY_{skill_id}_SLOW", "name": "Slow", "modifier_type": "debuff",
                "stat_effects": {"spd_pct": -0.2}, "duration": 2,
                "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }, {
        "event": "after_being_hit",
        "condition": "$event.target == $self.actor_id and $event.source != $self.actor_id",
        "effects": [{"effect_type": "gain_resource", "target": "self", "resource_id": rid, "amount": 1}],
    }, {
        "event": "on_hp_decrease",
        "condition": "$event.target == $self.actor_id and $event.reason == 'dot'",
        "effects": [{"effect_type": "gain_resource", "target": "self", "resource_id": rid, "amount": 1}],
    }]


def _enemy_corporeal_formula_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Corporeal Formula：每次模式切换叠加 50% 承伤提高."""
    if (semantic.get("name") != "Corporeal Formula"
            or semantic.get("desc") != "Each mode switch increases this unit's DMG received (50%, can stack)."):
        return []
    if 0.5 not in [float(x) for x in raw.get("param_list") or []]:
        return []
    modifier_id = f"ENEMY_{raw['skill_id']}_CORPOREAL"
    return [{
        "event": "on_state_change",
        "condition": "$event.actor == $self.actor_id",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Corporeal Formula", "modifier_type": "buff",
                "stat_exprs": {"vulnerability": f"0.5 * stacks($self, '{modifier_id}')"}, "stacks": 1,
                "duration": 0, "max_stack": 99, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }]


def _enemy_eternal_recurrence_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Eternal Recurrence：进入 Grave Wound 时回满 HP，下次行动解除."""
    if (semantic.get("name") != "Eternal Recurrence"
            or semantic.get("desc") != (
                "When this unit enters the \"Grave Wound\" state, restore all HP and dispel the "
                "\"Grave Wound\" state on next action.")):
        return []
    return [{
        "event": "after_apply_modifier",
        "condition": "$event.target == $self.actor_id and $event.modifier_id == 'GRAVE_WOUND'",
        "effects": [{"effect_type": "heal", "target": "self", "ratio": 1.0, "amount": 0}],
    }, {
        "event": "on_action",
        "condition": "$event.actor == $self.actor_id",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self", "modifier_id": "GRAVE_WOUND",
            "reason": "eternal_recurrence",
        }],
    }]


def _enemy_leviathan_valor_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Leviathan's Vestige Valor：三个部件均存活时取消对 Doomsday Beast 的伤害."""
    if semantic.get("name") != "Leviathan's Vestige Valor" or semantic.get("desc") != (
            "The Doomsday Beast cannot be attacked until the Antimatter Engine, "
            "Disaster's Right Hand, and Dawn's Left Hand have all been destroyed."):
        return []
    return [{
        "event": "before_take_damage",
        "condition": (
            "$event.target == $self.actor_id and (actor_alive('8013144') "
            "or actor_alive('8012143') or actor_alive('8012145'))"),
        "effects": [{"effect_type": "cancel_event"}],
    }]


def _enemy_convert_passive(raw: Dict[str, Any], semantic: Dict[str, Any]) -> List[Dict[str, Any]]:
    """被动技能 → hooks；无可靠语义证据时返回空列表."""
    hooks = _enemy_melt_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_living_eternal_flame_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_energy_burst_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_fleeting_veil_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_tremble_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_cruelty_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_expedite_verdict_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_disembodied_shell_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_thick_skinned_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_core_rupture_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_respite_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_polis_protector_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_inferno_stove_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_corporeal_formula_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_eternal_recurrence_passive(raw, semantic)
    if not hooks:
        hooks = _enemy_leviathan_valor_passive(raw, semantic)
    return hooks


def _enemy_self_destruct_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """自爆 Blast → 直接攻击 + set_hp_to_percent(self, 0) 死亡链 hook."""
    if semantic.get("type") != "Blast":
        return None
    match = re.fullmatch(
        r"Self-destructs, dealing (\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to a single target and units adjacent to the target\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    ratio = float(match.group(2)) / 100.0
    if (match.group(1) != element or len(params) != 1
            or abs(float(params[0]) - ratio) > 1e-9):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "blast",
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0}],
    }
    return action, hook


def _enemy_multi_summon_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], detail: Dict[str, Any],
    monster_meta: Any, *, level: int,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]]:
    """Twin Bond / Omen / Spear & Shield：按 SummonIDList 逐个落实召唤."""
    if semantic.get("type") != "Summon":
        return None
    desc = semantic.get("desc") or ""
    expected_names = {
        "Summons Abundance Lotus and Destruction Lotus.": {"Abundance Lotus", "Destruction Lotus"},
        "Summons Ice Edges.": {"Ice Edge"},
        'Randomly summons statues of "Speartip," "The Shield," and "The Honored."': {
            "Speartip", "The Shield", "The Honored"},
    }.get(desc)
    if expected_names is None:
        return None
    summon_ids = [str(summon_id) for summon_id in detail.get("SummonIDList") or []]
    params = raw.get("param_list") or []
    expected_count = 3 if desc.startswith("Randomly summons statues") else 2
    if len(summon_ids) != expected_count:
        return None
    if expected_count == 3:
        if (len(params) != 1 or not float(params[0]).is_integer()
                or int(params[0]) != len(summon_ids)):
            return None
    elif params:
        return None
    names = [((monster_meta(summon_id) or {}).get("en") or "").strip('"')
             for summon_id in summon_ids]
    if set(names) != expected_names:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    specs = [{
        "summon_id": f"{summon_id}__{detail['MonsterID']}_s1",
        "enemy_template": summon_id,
        "level": level,
    } for summon_id in summon_ids]
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [
            {"effect_type": "summon", "summon_id": spec["summon_id"]}
            for spec in specs
        ],
    }
    return action, hook, specs


def _enemy_summon_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], detail: Dict[str, Any],
    monster_meta: Any, *, level: int,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]]:
    """Summon（单一怪物模板、数量明确，可选 Max HP 消耗）→ 支援 action + hooks."""
    if semantic.get("type") != "Summon":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(r"Summons (.+) \((\d+)\)\.", desc)
    hp_cost = 0.0
    if match:
        summon_name, count_text = match.group(1), match.group(2)
    else:
        match = re.fullmatch(
            r"Consumes HP \((\d+(?:\.\d+)?)% Max HP\) to summon (.+) \((\d+)\)", desc)
        if match:
            hp_cost = float(match.group(1)) / 100.0
            summon_name, count_text = match.group(2), match.group(3)
    summon_ids = detail.get("SummonIDList") or []
    if not match or len(summon_ids) != 1:
        return None
    params = raw.get("param_list") or []
    if (not hp_cost and params) or (hp_cost and (
            len(params) != 1 or abs(float(params[0]) - hp_cost) > 1e-9)):
        return None
    summon_id = str(summon_ids[0])
    meta = monster_meta(summon_id)
    if not meta or meta.get("en") not in {summon_name, summon_name.removesuffix("s")}:
        return None
    count = int(count_text)
    if not 0 < count <= 4:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    specs = [{
        "summon_id": f"{summon_id}__{detail['MonsterID']}_s{index}",
        "enemy_template": summon_id,
        "level": level,
    } for index in range(1, count + 1)]
    effects = []
    if hp_cost:
        effects.append({
            "effect_type": "drain_hp", "target": "self",
            "amount": f"{hp_cost} * $self.max_hp", "drain_ratio": 0.0,
        })
    effects.extend({"effect_type": "summon", "summon_id": spec["summon_id"]}
                   for spec in specs)
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": effects,
    }
    return action, hook, specs


def _enemy_charge_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Charge（下一击且增伤比例明确）→ self 支援 action + 增伤 modifier."""
    if semantic.get("type") != "Charge":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Enters the Charging state \((?:(?:DMG|ATK) )?\+?(\d+(?:\.\d+)?)%\s*"
        r"(?:DMG|ATK)?(?: Boost)?(?:, (\d+) Turn)?\)\. "
        r"The next action (?:uses|casts) [^.]+\.", desc)
    params = raw.get("param_list") or []
    if not match or (params and len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    # 未写持续回合时，Charging 的语义就是保留下次行动；与显式 1 Turn 同构。
    duration = int(match.group(2) or 1)
    if params and abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_CHARGE",
                "name": "Charging",
                "modifier_type": "buff",
                "stat_effects": {"all_dmg": ratio},
                # on_action 后挂在当前回合末先走一次字，需 +1 才能覆盖下一击。
                "duration": duration + 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_focused_charge_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Focused Charge → 全体友方 ATK 增益（含施放者）."""
    if semantic.get("type") != "Enhance":
        return None
    match = re.fullmatch(
        r"Increases the ATK \((\d+(?:\.\d+)?)%, (\d+) Turns\) of all friendly units\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    if not match or len(params) != 2:
        return None
    ratio = float(match.group(1)) / 100.0
    duration = int(match.group(2))
    if abs(float(params[0]) - ratio) > 1e-9 or float(params[1]) != duration:
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "all_enemies",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_FOCUSED_CHARGE",
                "name": "Focused Charge",
                "modifier_type": "buff",
                "stat_effects": {"atk_pct": ratio},
                # 施放者 on_action 后挂载，当回合末先走字；+1 覆盖声明的持续回合。
                "duration": duration + 1,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_high_temperature_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Searing Prowler 高温运转 → 常驻 ATK/SPD 增益 + 自身击破时解除."""
    if (str(raw.get("skill_id")) != "102301004" or semantic.get("type") != "Enhance"
            or semantic.get("desc") != "Slightly increases ATK (20%) and greatly increases SPD (100). "
            "This buff is dispelled upon Weakness Break."):
        return None
    params = raw.get("param_list") or []
    if len(params) != 2 or abs(float(params[0]) - 0.2) > 1e-9 or float(params[1]) != 100.0:
        return None
    action_id = str(raw["skill_id"])
    modifier_id = "Monster_W1_Mecha_Fire_Burning"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "High-Temperature Operation",
                "modifier_type": "buff",
                "stat_effects": {"atk_pct": 0.2, "spd": 100.0},
                "duration": 0,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    break_hook = {
        "event": "on_break",
        "condition": f"$event.target == $self.actor_id and has_modifier($self, '{modifier_id}')",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": modifier_id, "reason": "weakness_break",
        }],
    }
    return action, [apply_hook, break_hook]


def _enemy_biting_obituary_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Biting Obituary → 一回合增伤 + 自身弱点击破时解除."""
    if (semantic.get("type") != "Enhance"
            or semantic.get("desc") != "Greatly increases DMG dealt (100%) for 1 turn. "
            "This effect is removed when this unit becomes Weakness Broken."):
        return None
    params = raw.get("param_list") or []
    if len(params) != 2 or any(abs(float(param) - 1.0) > 1e-9 for param in params):
        return None
    action_id = str(raw["skill_id"])
    modifier_id = f"ENEMY_{action_id}_BITING_OBITUARY"
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": "self",
            "modifier": {
                "modifier_id": modifier_id,
                "name": "Biting Obituary",
                "modifier_type": "buff",
                "stat_effects": {"all_dmg": 1.0},
                # 自身 on_action 后挂载，当回合末先走字；+1 覆盖声明的一回合。
                "duration": 2,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    break_hook = {
        "event": "on_break",
        "condition": f"$event.target == $self.actor_id and has_modifier($self, '{modifier_id}')",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": modifier_id, "reason": "weakness_break",
        }],
    }
    return action, [apply_hook, break_hook]


def _enemy_dancing_cinders_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """AoE 火伤 + 灼烧目标额外火伤并解除灼烧."""
    if semantic.get("type") != "AoE ATK" or raw.get("damage_type") != "Fire":
        return None
    match = re.fullmatch(
        r"Deals Fire DMG \((\d+(?:\.\d+)?)% ATK\) to all targets\. "
        r"Targets suffering from Burn are dealt an extra Fire DMG "
        r"\((\d+(?:\.\d+)?)% ATK\) and have Burn removed\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    ratios = [float(match.group(1)) / 100.0, float(match.group(2)) / 100.0]
    if any(abs(float(param) - ratio) > 1e-9 for param, ratio in zip(params, ratios)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe",
        "damage_type": "fire",
        "scaling": [{"atk": ratios[0]}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    burned_targets = {"pool": "allies", "where": "dot_kind($it, 'burn')"}
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "deal_damage",
            "target": burned_targets,
            "damage_type": "fire",
            "scaling_atk": ratios[1],
            "category": "additional",
        }, {
            "effect_type": "remove_modifier",
            "target": burned_targets,
            "filter": "$mod.modifier_type == 'dot' and $mod.dot_element == 'fire'",
            "reason": "dancing_cinders",
        }],
    }
    return action, hook


def _enemy_daybreak_dispersal_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Daybreak Dispersal：解除力场并自挂易伤与指定元素抗性降低."""
    if semantic.get("type") != "Others":
        return None
    match = re.fullmatch(
        r'D?Dispels "Daybreak Forcefield" and applies "Disheartened" \((\d+) Turns\) '
        r'to this unit, increasing DMG taken \((\d+(?:\.\d+)?)%\) and reducing '
        r"this unit's (Quantum|Fire|Imaginary|Physical) RES \((\d+(?:\.\d+)?)%\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    if not match or len(params) != 3:
        return None
    duration = int(match.group(1))
    vulnerability = float(match.group(2)) / 100.0
    res_reduction = float(match.group(4)) / 100.0
    expected = [vulnerability, res_reduction, float(duration)]
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "self",
        "energy_gain": 0,
        "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": "ENEMY_DAYBREAK_FORCEFIELD", "reason": "daybreak_dispersal",
        }, {
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_DISHEARTENED",
                "name": "Disheartened",
                "modifier_type": "debuff",
                "stat_effects": {
                    "vulnerability": vulnerability,
                    f"res_{match.group(3).lower()}": -res_reduction,
                },
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_insidious_agitation_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Insidious Agitation：仅在指定数字状态内可用，施放物伤后解除该状态."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Physical":
        return None
    match = re.fullmatch(
        r"Deals Physical DMG \((\d+(?:\.\d+)?)% ATK\) to one designated target, "
        r"then dispels the (\d+) state\. Can only be used while in the \2 state\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    state_id = match.group(2)
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "physical",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
        "available_if": f"has_modifier($self, '{state_id}')",
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": state_id, "reason": "insidious_agitation",
        }],
    }
    return action, hook


def _enemy_gnaw_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Gnaw：单体物伤；仅在指定数字状态下追加施放者 Max HP 自愈."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Physical":
        return None
    match = re.fullmatch(
        r"Deals Physical DMG \((\d+(?:\.\d+)?)% ATK\) to a single target\. "
        r"If this unit is under the (\d+) state, attacks the target and restores "
        r"this unit's HP \((\d+(?:\.\d+)?)% Max HP\)\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    state_id = match.group(2)
    heal_ratio = float(match.group(3)) / 100.0
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
        "damage_type": "physical",
        "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": (
            f"$event.actor == $self.actor_id and $event.action_id == '{action_id}' "
            f"and has_modifier($self, '{state_id}')"),
        "effects": [{"effect_type": "heal", "target": "self", "ratio": heal_ratio, "amount": 0}],
    }
    return action, hook


def _enemy_burn_priority_blast_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """火伤 Blast + 优先灼烧目标 → 带 dot:burn 目标偏好的直接攻击."""
    if semantic.get("type") != "Blast" or raw.get("damage_type") != "Fire":
        return None
    match = re.fullmatch(
        r"Deals Fire DMG to a single target \((\d+(?:\.\d+)?)% ATK\) "
        r"and units adjacent to the target \((\d+(?:\.\d+)?)% ATK\)\. "
        r"This attack prioritizes targets afflicted with Burn\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    ratios = [float(match.group(1)) / 100.0, float(match.group(2)) / 100.0]
    if any(abs(float(param) - ratio) > 1e-9 for param, ratio in zip(params, ratios)):
        return None
    action_id = str(raw["skill_id"])
    return {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "blast",
        "damage_type": "fire",
        "scaling": [{"atk": ratios[0]}],
        "scaling_blast": [{"atk": ratios[1]}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
        "prefer_target": "dot:burn",
    }


def _enemy_tyrant_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Tyrant of the Vanquished：该单位整场不行动."""
    if (semantic.get("name") != "Tyrant of the Vanquished"
            or semantic.get("desc") != '"Conquer or Be Conquered" will not take action.'):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "self", "energy_gain": 0, "energy_grant": 0.0,
    }
    hook = {
        "event": "on_battle_start",
        "effects": [{
            "effect_type": "apply_modifier", "target": "self",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_NO_ACTION", "name": "Tyrant of the Vanquished",
                "modifier_type": "buff", "prevent_action": True,
                "duration": 0, "max_stack": 1, "stack_mode": "refresh", "dispellable": False,
            },
        }],
    }
    return action, hook


def _enemy_sweeping_lance_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sweeping Lance：Speartip 雕像释放的 1000% 物理 AoE."""
    if (semantic.get("name") != "Sweeping Lance" or semantic.get("desc") != (
            "Releases the power in the Speartip statue and deals Physical DMG (1000% ATK) to all targets.")
            or raw.get("damage_type") != "Physical" or raw.get("sp_hit_base") != 40.0
            or [float(x) for x in raw.get("param_list") or []] != [10.0]
            or float(semantic.get("energy") or 0.0) != 40.0):
        return None
    action_id = str(raw["skill_id"])
    return {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "aoe", "damage_type": "physical", "scaling": [{"atk": 10.0}],
        "toughness_dmg": 40, "energy_gain": 0, "energy_grant": 40.0,
    }


def _enemy_controlled_blasting_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Controlled Blasting：机械臂自爆，造成 1500% 单体物伤后自身离场."""
    if (semantic.get("name") != "Controlled Blasting" or semantic.get("desc") != (
            "The Auxiliary Robot Arm explodes, dealing massive Physical DMG (1500% ATK) to a single target.")
            or raw.get("damage_type") != "Physical" or raw.get("sp_hit_base") != 25.0
            or [float(x) for x in raw.get("param_list") or []] != [15.0]
            or float(semantic.get("energy") or 0.0) != 25.0):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 15.0}],
        "toughness_dmg": 25, "energy_gain": 0, "energy_grant": 25.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0}],
    }
    return action, hook


def _enemy_sweep_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Sweep：从编队左/右起连续三目标的虚数伤害与逐目标受击回能."""
    if semantic.get("type") != "Sweep" or raw.get("damage_type") != "Imaginary":
        return None
    match = re.fullmatch(
        r"Starting from the (leftmost|rightmost) target, uses a sweeping attack on 3 consecutive "
        r"targets, dealing minor Imaginary DMG \((\d+(?:\.\d+)?)% ATK\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(2)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    order = "formation" if match.group(1) == "leftmost" else "-formation"
    targets = {"pool": "allies", "order_by": order, "take": 3}
    action = {
        "action_id": action_id, "name": semantic.get("name") or action_id,
        "action_type": "skill", "target_type": "self", "energy_gain": 0, "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "deal_damage", "target": targets, "damage_type": "imaginary",
            "scaling_atk": ratio, "toughness_dmg": int(sp_hit_base),
        }, {
            "effect_type": "gain_energy", "target": targets,
            "amount": float(semantic.get("energy") or 0.0),
        }],
    }
    return action, hook


def _enemy_ironthorn_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """冰伤后冻结并禁止下次行动，下次回合开始结算延迟冰伤（三种参数布局）."""
    if semantic.get("type") not in {"Single Target", "Impair"} or raw.get("damage_type") != "Ice":
        return None
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Ice DMG \((\d+(?:\.\d+)?)% ATK\) to a single target, "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to Freeze the target"
        r"(?: \((\d+(?:\.\d+)?)% ATK Delayed DMG(?:, (\d+) Turn)?\))?\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if not match or sp_hit_base is None or sp_hit_base < 0 or not float(sp_hit_base).is_integer():
        return None
    ratio = float(match.group(1)) / 100.0
    chance = float(match.group(2)) / 100.0
    if match.group(3) is None:
        # 原文省略延迟倍率：TBGD 仍给齐伤害、概率、持续、延迟四槽。
        if len(params) != 4:
            return None
        duration_raw = params[2]
        delayed = float(params[3])
        expected = [ratio, chance, float(duration_raw), delayed]
    elif len(params) == 4:
        delayed = float(match.group(3)) / 100.0
        duration_raw = match.group(4) or params[2]
        expected = [ratio, chance, float(duration_raw), delayed]
    elif len(params) == 3 and chance == 1.0:
        # 100% 基础概率省略原始概率槽：伤害、持续、延迟三槽。
        delayed = float(match.group(3)) / 100.0
        duration_raw = match.group(4) or params[1]
        expected = [ratio, float(duration_raw), delayed]
    else:
        return None
    if not float(duration_raw).is_integer():
        return None
    duration = int(duration_raw)
    if duration <= 0 or delayed <= 0 or any(
            abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    modifier_id = f"ENEMY_{action_id}_FREEZE"
    action = {
        "action_id": action_id, "name": semantic.get("name") or action_id,
        "action_type": "skill", "target_type": "single", "damage_type": "ice",
        "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
    }
    apply_hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target", "apply_chance": chance,
            "modifier": {
                "modifier_id": modifier_id, "name": "Freeze", "modifier_type": "control",
                "control_kind": "freeze", "prevent_action": True, "duration": duration,
                "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    delayed_hook = {
        "event": "on_turn_start",
        "condition": f"has_modifier($event.actor, '{modifier_id}')",
        "effects": [{
            "effect_type": "deal_damage", "target": "$event.actor", "damage_type": "ice",
            "scaling_atk": delayed,
        }],
    }
    return action, [apply_hook, delayed_hook]


def _enemy_heavens_fall_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Heaven's Fall：单体物伤，Strong 目标追加一次物伤并解除 Strong."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Physical":
        return None
    match = re.fullmatch(
        r"Deals (?:massive )?Physical DMG \((\d+(?:\.\d+)?)% ATK\) to a single target\. "
        r"If the target is afflicted with Strong Reverberation, they additionally take Physical DMG "
        r"\((\d+(?:\.\d+)?)% ATK\), and Strong Reverberation is then dispelled\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 1):
        return None
    ratio = float(match.group(1)) / 100.0
    extra = float(match.group(2)) / 100.0
    if abs(float(params[0]) - ratio) > 1e-9:
        return None
    action_id = str(raw["skill_id"])
    strong_id = f"ENEMY_{action_id[:-1]}2_STRONG_REVERB"
    action = {
        "action_id": action_id, "name": semantic.get("name") or action_id,
        "action_type": "skill", "target_type": "single", "damage_type": "physical",
        "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
    }
    hook = {
        "event": "on_action",
        "condition": (
            f"$event.actor == $self.actor_id and $event.action_id == '{action_id}' "
            f"and has_modifier($event.target, '{strong_id}')"),
        "effects": [{
            "effect_type": "deal_damage", "target": "$event.target", "damage_type": "physical",
            "scaling_atk": extra,
        }, {
            "effect_type": "remove_modifier", "target": "$event.target", "modifier_id": strong_id,
            "reason": "heavens_fall",
        }],
    }
    return action, hook


def _enemy_soul_warrant_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Soul Warrant：锁定 Strong 目标，供后续 Heaven's Fall 选择."""
    if semantic.get("name") != "Soul Warrant":
        return None
    desc = semantic.get("desc") or ""
    if not re.fullmatch(
            r"When there are targets afflicted with Strong Reverberation on the field, lock on to "
            r"those targets and during the next action, use Heaven's Fall on them\.?", desc):
        return None
    params = [float(x) for x in raw.get("param_list") or []]
    if params not in ([4.0, 2.0], [2.8, 2.8]):
        return None
    action_id = str(raw["skill_id"])
    strong_id = f"ENEMY_{action_id[:-1]}2_STRONG_REVERB"
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "aoe", "energy_gain": 0, "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier",
            "target": {"pool": "allies", "where": f"has_modifier($it, '{strong_id}')"},
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_LOCK_ON", "name": "Soul Warrant",
                "modifier_type": "debuff", "lock_on": True,
                "duration": 0, "max_stack": 1, "stack_mode": "replace", "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_sky_piercing_lance_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sky-Piercing Lance：固定次数、每段同倍率的 Imaginary Bounce."""
    if semantic.get("type") != "Bounce" or raw.get("damage_type") != "Imaginary":
        return None
    match = re.fullmatch(
        r"Deals successive \((\d+)\) minor Imaginary DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to random (?:single )?targets\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 2):
        return None
    count = int(match.group(1))
    ratio = float(match.group(2)) / 100.0
    if (count <= 0 or abs(float(params[0]) - ratio) > 1e-9 or float(params[1]) != count):
        return None
    action_id = str(raw["skill_id"])
    return {
        "action_id": action_id, "name": semantic.get("name") or action_id,
        "action_type": "skill", "target_type": "bounce", "damage_type": "imaginary",
        "scaling": [{"atk": ratio}], "toughness_dmg": int(sp_hit_base), "instances": count,
        "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
    }


def _enemy_channel_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """课堂/下课频道切换及其能量、战技点、拉条支援技能."""
    name = semantic.get("name")
    desc = semantic.get("desc") or ""
    off_id, class_id = "OFF_CLASS_CHANNEL", "CLASSROOM_CHANNEL"
    surprise_id, fright_id = "SURPRISE_CHANNEL", "FRIGHT_CHANNEL"
    if name == "Channel Switch":
        if desc != "Switches the Surprise Channel status to the Fright Channel status.":
            return None
        required, event, effects = surprise_id, "on_action", [
            {"effect_type": "remove_modifier", "target": "self", "modifier_id": surprise_id},
            {"effect_type": "apply_modifier", "target": "self", "modifier": {
                "modifier_id": fright_id, "name": "Fright Channel", "modifier_type": "buff",
                "singleton_group": "actor_state", "duration": 0, "dispellable": False,
            }},
        ]
    elif name == "Change Banasyllabus":
        if desc != 'Switches the "Off-Class Channel" state to the "Classroom Channel" state.':
            return None
        required, event, effects = off_id, "on_action", [
            {"effect_type": "remove_modifier", "target": "self", "modifier_id": off_id},
            {"effect_type": "apply_modifier", "target": "self", "modifier": {
                "modifier_id": class_id, "name": "Classroom Channel", "modifier_type": "buff",
                "singleton_group": "actor_state", "duration": 0, "dispellable": False,
            }},
        ]
    elif name == "Disrupt Banasyllabus":
        if desc != ('After being attacked, switches the "Classroom Channel" state to the '
                    '"Off-Class Channel" state. When in "Off-Class Channel" state, will not '
                    'switch channels after being attacked.'):
            return None
        required, event, effects = class_id, "after_being_hit", [
            {"effect_type": "remove_modifier", "target": "self", "modifier_id": class_id},
            {"effect_type": "apply_modifier", "target": "self", "modifier": {
                "modifier_id": off_id, "name": "Off-Class Channel", "modifier_type": "buff",
                "singleton_group": "actor_state", "duration": 0, "dispellable": False,
            }},
        ]
    else:
        specs = {
            "Good Monkeys Get Grades": (
                off_id, 2.0,
                'Regenerates Skill Points (2) for the team. This ability can only be used while under the "Off-Class Channel" state.',
                [{"effect_type": "gain_skill_point", "amount": 2}]),
            "Bad Monkeys Get Demerits": (
                class_id, 1.0,
                'Reduces Skill Points (1) for the team. This ability can only be used while under the "Classroom Channel" state.',
                [{"effect_type": "gain_skill_point", "amount": -1}]),
            "Break Time! Chaaarge!": (
                off_id, 0.5,
                'Advances all targets\' actions (50%). This ability can only be used while under the "Off-Class Channel" state.',
                [{"effect_type": "advance_action", "target": "all_allies", "amount": 50.0}]),
            "Class Time! Sit Down!": (
                class_id, 0.5,
                'Advances all friendly units\' actions (50%). This ability can only be used while under the "Classroom Channel" state.',
                [{"effect_type": "advance_action", "target": "all_enemies", "amount": 50.0}]),
            "Banappiness Holiday": (
                off_id, 0.5,
                'Regenerates Energy (50% Max Energy) for one designated target. This ability can only be used while under the "Off-Class Channel" state.',
                [{"effect_type": "gain_energy", "target": "$event.target",
                  "amount": "$target.max_energy * 0.5"}]),
            "Surprise Variety Show": (
                surprise_id, 0.5,
                "Regenerates Energy (50% Max Energy) for a target. This ability can only be used while under the Surprise Channel state.",
                [{"effect_type": "gain_energy", "target": "$event.target",
                  "amount": "$target.max_energy * 0.5"}]),
        }
        if name not in specs:
            return None
        required, expected_param, expected_desc, effects = specs[name]
        params = raw.get("param_list") or []
        if desc != expected_desc or len(params) != 1 or abs(float(params[0]) - expected_param) > 1e-9:
            return None
        event = "on_action"
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": name, "action_type": "skill",
        "target_type": "single" if name in {"Banappiness Holiday", "Surprise Variety Show"} else "self",
        "energy_gain": 0, "energy_grant": 0.0,
        "available_if": f"has_modifier($self, '{required}')",
    }
    condition = (f"$event.target == $self.actor_id and has_modifier($self, '{required}') "
                 "and $event.source != $self.actor_id" if event == "after_being_hit"
                 else f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'")
    return action, {"event": event, "condition": condition, "effects": effects}


def _enemy_shrewd_bombing_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """十二段物伤轰炸 + 减防；Oversaturated Bombardment 允许叠层."""
    name = semantic.get("name")
    if name not in {"Shrewd Bombing", "Oversaturated Bombardment"} or raw.get("damage_type") != "Physical":
        return None
    match = re.fullmatch(
        r"Deals massive Physical DMG \((\d+(?:\.\d+)?)% ATK × 12\) to all targets, "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to reduce their DEF "
        r"\((\d+(?:\.\d+)?)%, (\d+) Turns\)\.(?: This debuff can stack\.)?",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer() or len(params) != 3):
        return None
    ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    def_ratio = float(match.group(3)) / 100.0
    duration = int(match.group(4))
    expected = [ratio, def_ratio, float(duration)]
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": name, "action_type": "skill",
        "target_type": "aoe", "damage_type": "physical", "scaling": [{"atk": ratio}],
        "toughness_dmg": int(sp_hit_base), "instances": 12,
        "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
    }
    stackable = name == "Oversaturated Bombardment"
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "all_allies", "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_DEF_DOWN", "name": "DEF Reduction",
                "modifier_type": "debuff", "stat_effects": {"def_pct": -def_ratio}, "duration": duration,
                **({"stacks": 1} if stackable else {"max_stack": 1}),
                "stack_mode": "refresh", "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_lock_on_target_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Lock On Target：给单体目标施加 lock_on，后续单体攻击优先命中."""
    if (semantic.get("name") != "Lock On Target"
            or semantic.get("desc") != 'Locks Onto a single target. The next action on the target will cast "Felling Order."'
            or (raw.get("param_list") or [])):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id, "name": semantic["name"], "action_type": "skill",
        "target_type": "single", "energy_gain": 0, "energy_grant": 0.0,
    }
    hook = {
        "event": "on_action",
        "condition": f"$event.actor == $self.actor_id and $event.action_id == '{action_id}'",
        "effects": [{
            "effect_type": "apply_modifier", "target": "$event.target",
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_LOCK_ON", "name": "Lock On",
                "modifier_type": "debuff", "lock_on": True,
                "duration": 0, "max_stack": 1, "stack_mode": "replace", "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_convert_skill(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_name: str,
    detail: Dict[str, Any], monster_meta: Any, level: int,
    raw_config: Optional[Dict[str, Any]],
    semantic_catalog: Optional[List[Dict[str, Any]]] = None,
) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """单个 TBGD 技能 × 单个 Fandom 语义候选 → (action, hooks, summons) 或全空."""
    action = None
    hook = None
    hooks: List[Dict[str, Any]] = []
    summons: List[Dict[str, Any]] = []
    support = _enemy_horn_clash_action(raw, semantic)
    if support is not None:
        action, hook = support
    if action is None:
        action = _enemy_burn_priority_blast_action(raw, semantic)
    if action is None:
        support = _enemy_unstable_forcefield_action(raw, semantic)
        if support is not None:
            action, forcefield_hooks = support
            hooks.extend(forcefield_hooks)
    if action is None:
        support = _enemy_garrison_barrier_action(raw, semantic)
        if support is not None:
            action, garrison_hooks = support
            hooks.extend(garrison_hooks)
    if action is None:
        support = _enemy_war_gear_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_seeding_core_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_tyrant_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        action = _enemy_sweeping_lance_action(raw, semantic)
    if action is None:
        support = _enemy_controlled_blasting_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_sweep_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_ironthorn_action(raw, semantic)
        if support is not None:
            action, ironthorn_hooks = support
            hooks.extend(ironthorn_hooks)
    if action is None:
        support = _enemy_soul_warrant_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_heavens_fall_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_channel_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_shrewd_bombing_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_lock_on_target_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        action = _enemy_linked_param_direct_action(raw, semantic)
    if action is None:
        action = _enemy_direct_action(raw, semantic)
    if action is None:
        support = _enemy_starfall_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_saturation_cleaning_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        action = _enemy_sky_piercing_lance_action(raw, semantic)
    if action is None:
        action = _enemy_bounce_action(raw, semantic)
    if action is None:
        action = _enemy_obscure_blaze_action(raw, semantic)
    if action is None:
        action = _enemy_scorchbone_inferno_action(raw, semantic)
    if action is None:
        action = _enemy_distribute_action(raw, semantic)
    if action is None:
        support = _enemy_focused_charge_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_biting_obituary_action(raw, semantic)
        if support is not None:
            action, biting_obituary_hooks = support
            hooks.extend(biting_obituary_hooks)
    if action is None:
        support = _enemy_high_temperature_action(raw, semantic)
        if support is not None:
            action, high_temperature_hooks = support
            hooks.extend(high_temperature_hooks)
    if action is None:
        support = _enemy_dancing_cinders_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_daybreak_dispersal_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_insidious_agitation_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_gnaw_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_restore_action(raw, semantic, owner_name)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_combat_redeployment_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_heavens_binds_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_engine_boost_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_primal_hunger_action(raw, semantic, detail, monster_meta)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_rapturous_wind_action(raw, semantic, detail, monster_meta)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_frigid_waterfall_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_molten_fusion_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_shock_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_burn_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_wind_shear_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_great_arbor_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_caressing_moonlight_action(raw, semantic, semantic_catalog)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_seething_whisper_action(raw, semantic, semantic_catalog)
        if support is not None:
            action, seething_hooks = support
            hooks.extend(seething_hooks)
    if action is None:
        support = _enemy_to_mourn_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_bleed_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_imprison_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_def_impair_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_vulnerability_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_weaken_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_effect_res_down_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_reverberation_action(raw, semantic)
        if support is not None:
            action, reverb_hooks = support
            hooks.extend(reverb_hooks)
    if action is None:
        support = _enemy_delay_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_nihility_command_action(raw, semantic, raw_config)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_spiral_arrow_action(raw, semantic, str(detail["MonsterID"]))
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_end_of_bow_action(raw, semantic, str(detail["MonsterID"]))
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_outrage_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_spirit_whisper_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_shield_reflect_action(raw, semantic, raw_config)
        if support is not None:
            action, shield_reflect_hooks = support
            hooks.extend(shield_reflect_hooks)
    if action is None:
        support = _enemy_self_destruct_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_trashcan_enhance_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_wrathful_roar_action(raw, semantic)
        if support is not None:
            action, roar_hooks = support
            hooks.extend(roar_hooks)
    if action is None:
        support = _enemy_simian_strike_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_fiery_majesty_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_allargando_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_defense_action(raw, semantic)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_flee_action(raw, semantic, raw_config)
        if support is not None:
            action, hook = support
    if action is None:
        support = _enemy_multi_summon_action(raw, semantic, detail, monster_meta, level=level)
        if support is not None:
            action, hook, summon_specs = support
            summons.extend(summon_specs)
    if action is None:
        support = _enemy_summon_action(raw, semantic, detail, monster_meta, level=level)
        if support is not None:
            action, hook, summon_specs = support
            summons.extend(summon_specs)
    if action is None:
        action = _enemy_timed_charge_action(raw, semantic)
    if action is None:
        support = _enemy_charge_action(raw, semantic)
        if support is not None:
            action, hook = support
    if hook is not None:
        hooks.append(hook)
    return action, hooks, summons


def generate_enemy_template(
    enemy_id: str,
    *,
    level: int = 80,
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 数据 → 敌人模板 dict（有序列/ConfigAI 证据的可表达技能子集）.

    面板与技能数值来自 TBGD；Fandom 提供技能名、目标范围、攻击类型与倍率文本
    交叉证据。ParamList 非空时逐值对账；空表不视为反证，纯直伤可使用原文倍率。
    通用 SequenceThree 允许部分覆盖；专属 AIPath 可由完整原始序列或
    可执行 ConfigAI 独立成立。空序列只在存在可执行 ConfigAI 决策时生成 policy，
    不做表序兜底。
    """
    from hsr_nous.pipeline.enemies.loader import (
        calc_enemy_stats, get_enemy_ai, get_enemy_ai_config, get_enemy_detail,
        get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    from hsr_nous.sim_schema.config_ai import (
        has_initial_decision, unsupported_config_nodes, used_config_skill_names)

    root = Path(data_dir) if data_dir is not None else None

    def _p(rel: str) -> Optional[str]:
        return str(root / rel) if root is not None else None

    tbgd_dir = _p("turnbasedgamedata")
    stats = calc_enemy_stats(enemy_id, level, tbgd_dir=tbgd_dir)
    if stats is None:
        raise ValueError(f"敌人 {enemy_id} 无 tbgd 数值（不存在或仅遗留源）")

    meta = get_monster_meta(
        enemy_id, monster_path=_p("stages/hakushin/monster.json"), tbgd_dir=tbgd_dir) or {}
    name_en = meta.get("en") or str(enemy_id)
    notes: List[str] = []
    fdata = get_enemy_mechanics(
        name_en, fandom_enemy_path=_p("fandom_enemy_data.json"),
        weakness=stats["weakness"])
    semantic_skills = (fdata or {}).get("skills") or []
    for sk in semantic_skills:
        notes.append(
            f"技能「{sk.get('name')}」（{sk.get('type')}）语义来源：{sk.get('desc', '')}"
        )

    raw_skills = get_enemy_skills(enemy_id, tbgd_dir=tbgd_dir)
    active_raw = [
        sk for sk in raw_skills
        if sk.get("trigger_key") != "PassiveSkillInitiate"
        and not sk.get("_missing_in_skill_config")
    ]
    ai = get_enemy_ai(enemy_id, tbgd_dir=tbgd_dir) or {}
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir) or {}
    if ai.get("ai_path_override"):
        ai_path = ai["ai_path_override"]
        sequence = ai.get("skill_sequence_override") or []
    else:
        ai_path = ai.get("ai_path")
        sequence = ai.get("skill_sequence") or []
    raw_config = get_enemy_ai_config(ai_path, tbgd_dir=tbgd_dir) if ai_path else None
    policy: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = []
    enemy_hooks: List[Dict[str, Any]] = []
    standalone_passive_hooks: List[Dict[str, Any]] = []
    enemy_summons: List[Dict[str, Any]] = []
    if (sequence or raw_config) and semantic_skills:
        cooldown: Dict[str, int] = {}
        initial_cooldown: Dict[str, int] = {}
        valid_cooldowns = True
        for sk in raw_skills:
            for raw_key, target in (("ai_cd", cooldown), ("ai_icd", initial_cooldown)):
                value = sk.get(raw_key)
                if value is None:
                    continue
                if value < 0 or not float(value).is_integer():
                    notes.append(f"技能 {sk['skill_id']} 的 {raw_key}={value} 不是非负整数")
                    valid_cooldowns = False
                    continue
                target[str(sk["skill_id"])] = int(value)
        if valid_cooldowns:
            conversion_ids = {str(skill_id) for skill_id in sequence}
            if raw_config is not None:
                config_skill_names = used_config_skill_names(raw_config)
                conversion_ids.update(
                    str(sk["skill_id"]) for sk in active_raw
                    if str(sk.get("trigger_key")) in config_skill_names)
            candidate_actions: List[Dict[str, Any]] = []
            candidate_hooks: List[Dict[str, Any]] = []
            candidate_summons: List[Dict[str, Any]] = []
            candidates: Dict[str, List[tuple]] = {}
            raw_positions = {id(raw): index for index, raw in enumerate(raw_skills)}
            semantic_positions = {id(semantic): index for index, semantic in enumerate(semantic_skills)}
            for raw in active_raw:
                if str(raw["skill_id"]) not in conversion_ids:
                    continue
                matches = []
                for semantic in semantic_skills:
                    action, hooks, summons = _enemy_convert_skill(
                        raw, semantic, name_en, detail, get_monster_meta, level, raw_config,
                        semantic_catalog=semantic_skills)
                    if action is not None:
                        matches.append((semantic, action, hooks, summons))
                candidates[str(raw["skill_id"])] = matches
            # 一个语义不得服务多个原始技能；冲突时只保留原始顺序也能对齐的那一条。
            for semantic in semantic_skills:
                semantic_index = semantic_positions[id(semantic)]
                owners = [(raw, match) for raw in active_raw
                          for match in candidates.get(str(raw["skill_id"]), [])
                          if match[0] is semantic]
                if len(owners) <= 1:
                    continue
                if semantic.get("name") == "Simian Strike":
                    # theBowja 与 TBGD 双源确认：相邻两个原始 ID 是同名同文的猱击，
                    # 不是一语义对多技能的误配，保留各自 action_id 供 ConfigAI 调用。
                    continue
                ordered = [raw for raw, _match in owners
                           if raw_positions[id(raw)] == semantic_index]
                for raw, match in owners:
                    if len(ordered) == 1 and raw is ordered[0]:
                        continue
                    candidates[str(raw["skill_id"])].remove(match)
            for raw in active_raw:
                if str(raw["skill_id"]) not in conversion_ids:
                    continue
                matches = candidates.get(str(raw["skill_id"]), [])
                if len(matches) > 1:
                    # 反向冲突同样只接受原始位次唯一对齐者（被动转换本已使用同一位次证据）。
                    positional = [match for match in matches
                                  if semantic_positions[id(match[0])] == raw_positions[id(raw)]]
                    if len(positional) == 1:
                        matches = positional
                    else:
                        notes.append(f"技能 {raw['skill_id']} 有多个 Fandom 语义候选，拒绝收编")
                        continue
                if not matches:
                    continue
                _semantic, action, hooks, summons = matches[0]
                candidate_actions.append(action)
                candidate_hooks.extend(hooks)
                candidate_summons.extend(summons)
                if action["target_type"] in {"blast", "bounce_blast"}:
                    notes.append(
                        f"技能 {action['action_id']} 副目标削韧按 rulebook 比例候选，待真实 golden")
                if action["name"] == "Garrison Aura Field":
                    notes.append(
                        f"技能 {action['action_id']} Barrier 目标按编队序首个其他友方候选，待真实 golden")
                for hook in hooks:
                    if any((eff.get("modifier") or {}).get("modifier_type") == "dot"
                           for eff in hook["effects"]):
                        notes.append(f"技能 {action['action_id']} DoT 重施加按 refresh 候选，待真实 golden")
            covered_ids = {a["action_id"] for a in candidate_actions}
            full_sequence = all(skill_id in covered_ids for skill_id in sequence)
            bad: Optional[set[str]] = None
            if ai_path and raw_config is not None:
                available_skill_names = {
                    str(sk["trigger_key"]) for sk in raw_skills
                    if sk.get("trigger_key") and sk["skill_id"] in covered_ids
                }
                bad = unsupported_config_nodes(raw_config, available_skill_names)
                if not bad and not has_initial_decision(
                        raw_config, available_skill_names, monster_id=str(enemy_id),
                        monster_rank=str(meta.get("rank") or "")):
                    bad = {"initial:no-executable-decision"}
            config_usable = bool(ai_path and raw_config is not None and not bad)
            if bad:
                notes.append(f"ConfigAI 未收编节点：{', '.join(sorted(bad))}")
            # 通用 SequenceThree 允许部分覆盖；专属 AIPath 可由完整原始序列或
            # 可执行 ConfigAI 独立成立，实例技能 ID 与模板序列不一致时不误杀后者。
            if ai_path == _ENEMY_SEQUENCE_AI or full_sequence or config_usable:
                actions = candidate_actions
                enemy_hooks = candidate_hooks
                enemy_summons = candidate_summons
                policy = {
                    "sequence": [str(x) for x in sequence],
                    "cooldown": cooldown,
                    "initial_cooldown": initial_cooldown,
                    "monster_rank": str(meta.get("rank") or ""),
                    "skill_phases": {
                        str(sk["skill_id"]): list(sk["phase_list"])
                        for sk in raw_skills if sk.get("phase_list")
                    },
                }
                if config_usable:
                    policy["skill_ids"] = {
                        str(sk["trigger_key"]): str(sk["skill_id"])
                        for sk in raw_skills if sk.get("trigger_key")
                    }
                    policy["config"] = raw_config
                if not sequence and (not covered_ids or not policy.get("config")):
                    notes.append(f"AIPath {ai_path!r} 无可执行 ConfigAI 决策，不生成 actions/policy")
                    policy = None
                    actions = []
                    enemy_hooks = []
                    enemy_summons = []
                for skill_id in sequence:
                    if skill_id not in covered_ids and (ai_path == _ENEMY_SEQUENCE_AI or not config_usable):
                        notes.append(f"序列技能 {skill_id} 未收编，运行时显式跳过")
            else:
                notes.append(f"AIPath {ai_path!r} 含未收编技能，专属 AI 不生成 actions/policy")
    elif not sequence and raw_config is None:
        notes.append("AISkillSequence 为空，不做表序兜底")
    elif not semantic_skills:
        notes.append("技能语义未对齐，actions/policy 不生成")

    # 被动 hook 不依附主动技能/专属 AI 是否可执行：死亡触发等机制即使无 actions 也必须保留。
    # Fandom 与原始表可能错位（Furiae Philosopher 少一项主动技），故按精确转换结果全表匹配；
    # PassiveSkillInitiate 与 SkillPxx 是被动触发键；Talent 语义也允许非 Passive 原始 ID
    # （Cruelty 的 Skill06 实证）。优先原生被动 ID，Talent 只补尚未覆盖的语义，防止同一
    # 被动被多个原始 ID 重复挂载；逐技能仍须精确转换且唯一匹配。
    has_talent_semantics = any(semantic.get("type") == "Talent" for semantic in semantic_skills)
    passive_raw = [raw for raw in raw_skills
                   if str(raw.get("trigger_key") or "").startswith(("Passive", "SkillP"))]
    if has_talent_semantics:
        passive_raw.extend(raw for raw in raw_skills if raw not in passive_raw)
    covered_passive_semantics: set[int] = set()
    for raw in passive_raw:
        matches = [(semantic, hooks) for semantic in semantic_skills
                   if (hooks := _enemy_convert_passive(raw, semantic))]
        if len(matches) == 1:
            semantic, passive_hooks = matches[0]
            if id(semantic) in covered_passive_semantics:
                continue
            covered_passive_semantics.add(id(semantic))
            standalone_passive_hooks.extend(passive_hooks)
            if semantic.get("name") == "Melt":
                notes.append(
                    f"技能 {raw['skill_id']} Melt 按每次行动叠 1 层，"
                    "AoE 多目标是否重复叠层待真实 golden")
            elif semantic.get("name") == "Polis Protector":
                notes.append(
                    f"技能 {raw['skill_id']} War Armor 多段攻击按每命中段扣层，"
                    "破甲后追加自伤同口径，待真实 golden")
        elif len(matches) > 1:
            notes.append(f"被动技能 {raw['skill_id']} 有多个 Fandom 语义候选，拒绝收编")

    delayed = [f"{sk['skill_id']}={sk['delay_ratio']}" for sk in raw_skills
               if sk.get("delay_ratio") is not None]
    if delayed:
        notes.append(f"DelayRatio 未接入时序，待真实 golden 验证：{', '.join(delayed)}")
    if stats.pop("_level_clamped", False):
        notes.append(f"等级 {level} 超出 HardLevelGroup 表范围，已钳到表内最大级")
    missing = stats.pop("_missing_bases", [])
    if missing:
        notes.append(f"原始数据缺 base 字段（按 0 处理）：{', '.join(missing)}——"
                     "通常为无韧性条/不行动的特殊怪，需人工确认机制")
    custom_resources = _enemy_custom_resource_decls(actions)

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
        "resistance": stats["resistance"],
        "actions": actions,
        **({"custom_resources": custom_resources} if custom_resources else {}),
        **({"hooks": enemy_hooks + standalone_passive_hooks}
           if enemy_hooks or standalone_passive_hooks else {}),
        **({"summons": enemy_summons} if enemy_summons else {}),
        **({"policy": policy} if policy is not None else {}),
        **({"notes": notes} if notes else {}),
    }


def write_enemy_template(
    enemy_id: str,
    *,
    out_dir: str = _OUT_DIRS["enemies"],
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


# ---------------------------------------------------------------------------
# 关卡模板（stages）：Hakushin 期数详情 → stage_template（waves 与 actor_id 去重）
# ---------------------------------------------------------------------------


def generate_stage_template(
    mode: str,
    period_id: str,
    *,
    side: int = 0,
    floor_index: int = 0,
    stages_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Hakushin 期数详情 → stage 模板 dict（floor+side 为最小单元，两侧绝不合并）."""
    if mode not in _STAGE_MODE_MAP:
        raise ValueError(f"暂不支持 Hakushin 玩法 {mode!r}（合法 {sorted(_STAGE_MODE_MAP)}）")
    if side not in (0, 1):
        raise ValueError(f"side 只能是 0（上半）或 1（下半），得到 {side!r}")
    from hsr_nous.pipeline.stages.loader import get_stage_hakushin

    data = get_stage_hakushin(mode, period_id, stages_dir=stages_dir)
    floors = data.get("floors") or []
    if not 0 <= floor_index < len(floors):
        raise ValueError(f"floor_index {floor_index} 越界（共 {len(floors)} 层）")
    floor = floors[floor_index]
    if side >= len(floor.get("sides", [])):
        raise ValueError(f"floor {floor.get('id')} 没有 side={side}")
    stage_id = f"{mode}_{period_id}_{floor['id']}_s{side + 1}"
    waves: List[Dict[str, Any]] = []
    for event in floor["sides"][side]:
        for monster in event.get("monster_list") or []:
            # 同一 side 可有多 event；波次号必须跨 event 递增，不能各自从 1 重启。
            wave_index = len(waves) + 1
            enemies: List[Dict[str, Any]] = []
            for position, enemy_id in enumerate(monster.values(), start=1):
                if not enemy_id:
                    raise ValueError(f"stage {stage_id} 出现空 monster id")
                enemies.append({
                    "enemy_template": str(enemy_id),
                    "level": int(event.get("level", 80)),
                    "actor_id": f"{enemy_id}__{stage_id}_w{wave_index}_p{position}",
                })
            waves.append({"wave_index": wave_index, "enemies": enemies})
    return {
        "stage_id": stage_id,
        "name": floor.get("name") or floor.get("group_name") or stage_id,
        "mode": _STAGE_MODE_MAP[mode],
        "waves": waves,
    }


def write_stage_template(
    mode: str,
    period_id: str,
    *,
    side: int = 0,
    floor_index: int = 0,
    out_dir: str = _OUT_DIRS["stages"],
    stages_dir: Optional[str] = None,
) -> str:
    """生成并写盘（<stage_id>.yaml），返回文件路径."""
    tpl = generate_stage_template(
        mode, period_id, side=side, floor_index=floor_index, stages_dir=stages_dir)
    stage_id = tpl["stage_id"]
    path = Path(out_dir) / f"{stage_id}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 关卡模板：{stage_id}——由 adapters/template_generator 生成，勿手改\n")
        yaml.safe_dump(tpl, f, allow_unicode=True, sort_keys=False)
    return str(path)


def write_stage_templates_for_period(
    mode: str,
    period_id: str,
    *,
    out_dir: str = _OUT_DIRS["stages"],
    stages_dir: Optional[str] = None,
) -> List[str]:
    """生成一个期数下全部 floor/side 模板，异常由批量入口按 period 收集."""
    from hsr_nous.pipeline.stages.loader import get_stage_hakushin

    data = get_stage_hakushin(mode, period_id, stages_dir=stages_dir)
    paths: List[str] = []
    for floor_index, _floor in enumerate(data.get("floors") or []):
        for side in (0, 1):
            paths.append(write_stage_template(
                mode, period_id, side=side, floor_index=floor_index,
                out_dir=out_dir, stages_dir=stages_dir))
    return paths


# ---------------------------------------------------------------------------
# 呈现层旁车（descriptions）：官方中文技能/行迹/星魂 desc/params + 能量槽显示名 →
# data/sim_templates/descriptions/{char_id}.json。显示文本不进 DSL 词表（编译器零改动），
# web 调试台旁路消费（契约见 adapters README「呈现层旁车」节）
# ---------------------------------------------------------------------------


def generate_description_sidecar(
    char_id: str,
    *,
    lang: str = "cn",
    data_dir: Optional[str] = None,
    skeleton_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """starrailres 技能/行迹/星魂原文 → 呈现层旁车 dict.

    收录（F3 扩员，不按骨架裁剪——天赋/秘技/行迹也要供状态 tab 来源展开）：
    - actions：character_skills 里该角色（技能 id 前缀 = char_id）的全部条目
      （Normal/BPSkill/Ultra/Talent/Maze/MazeNormal 全收），原样抽 name/desc/params，
      附官方 type_text（普攻/战技/终结技/天赋/秘技）作来源展开卡的类型标签
    - traces：character_skill_trees 里该角色大行迹节点（name+desc 俱全者——
      属性小行迹与技能等级节点无 desc 不收），键 = 节点 id
    - ranks：character_ranks 里该角色全部星魂条目（rank id 前缀 = char_id），
      键 = rank id，值 {rank, name, desc, params} 原样抽（星魂 tab 官方 desc 取数；
      实测 cn 全表 params 为 null、desc 无占位符——代入规则仍与技能 desc 同管线）
    skeleton_dir：骨架模板查找目录（缺省 = 缺省模板根 characters/）；批量生成 --out
      注入时须同根透传，否则读到别的根的骨架。
    Raises: ValueError（无骨架——旁车仍按角色骨架一份一份发）。
    """
    from hsr_nous.pipeline import (
        load_character_ranks, load_character_skill_trees, load_character_skills_merged)

    skel_dir = skeleton_dir if skeleton_dir is not None else _OUT_DIRS["characters"]
    skeletons = sorted(Path(skel_dir).glob(f"{char_id}_*.yaml"))
    if not skeletons:
        raise ValueError(f"角色 {char_id} 无骨架模板（{skel_dir} 下无 {char_id}_*.yaml）")
    try:
        skeleton = yaml.safe_load(skeletons[0].read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        skeleton = {}
    energy_name = skeleton.get("energy_name") if isinstance(skeleton, dict) else None

    prefix = str(char_id)
    merged = load_character_skills_merged(data_dir=data_dir, lang=lang)
    actions: Dict[str, Any] = {}
    for sid in sorted(merged):
        if not sid.startswith(prefix):
            continue
        s = merged[sid]
        actions[sid] = {
            "name": s.get("name", ""),
            "desc": s.get("desc", "") or "",
            "params": s.get("params") or [],
            "type_text": s.get("type_text") or "",  # 官方类型标签（来源展开卡 badge 用）
        }
    trees = load_character_skill_trees(data_dir=data_dir, lang=lang)
    traces: Dict[str, Any] = {}
    for nid in sorted(trees):
        if not nid.startswith(prefix):
            continue
        n = trees[nid]
        if not (n.get("name") and n.get("desc")):
            continue  # 属性小行迹/技能等级节点：无机制 desc，不收
        traces[nid] = {
            "name": str(n["name"]),
            "desc": str(n["desc"]),
            "params": n.get("params") or [],
        }
    ranks_all = load_character_ranks(data_dir=data_dir, lang=lang)
    ranks: Dict[str, Any] = {}
    for rid in sorted(ranks_all):
        if not rid.startswith(prefix):
            continue
        r = ranks_all[rid]
        ranks[rid] = {
            "rank": int(r.get("rank") or 0),
            "name": str(r.get("name", "")),
            "desc": str(r.get("desc", "") or ""),
            "params": r.get("params") or [],
        }
    return {
        "actor_id": prefix,
        "energy_name": energy_name,
        "actions": actions,
        "traces": traces,
        "ranks": ranks,
    }


def write_description_sidecar(
    char_id: str,
    *,
    out_dir: str = _OUT_DIRS["descriptions"],
    lang: str = "cn",
    skeleton_dir: Optional[str] = None,
) -> str:
    """生成并写盘（{char_id}.json），返回文件路径."""
    sidecar = generate_description_sidecar(char_id, lang=lang, skeleton_dir=skeleton_dir)
    path = Path(out_dir) / f"{char_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return str(path)


def write_all_description_sidecars(*, lang: str = "cn") -> List[str]:
    """全量：characters/ 下每副角色骨架一份旁车，返回写出路径列表."""
    out: List[str] = []
    for f in sorted(Path(_OUT_DIRS["characters"]).glob("*_*.yaml")):
        out.append(write_description_sidecar(f.name.split("_", 1)[0], lang=lang))
    return out


# ---------------------------------------------------------------------------
# 批量生成入口（CI/本地数据环境初始化——五类全量，失败逐个收集报尾，任一失败 exit 1）
# ---------------------------------------------------------------------------

def main() -> int:
    """全量生成模板骨架（角色/光锥/遗器/敌人/呈现层旁车），返回退出码."""
    import argparse

    parser = argparse.ArgumentParser(description="全量生成 per-entity DSL 模板骨架")
    parser.add_argument("--out", default=DEFAULT_TEMPLATE_ROOTS[0],
                        help="模板根目录（缺省 = sim_schema/templates.py 唯一事实源）")
    parser.add_argument("--lang", default="cn", help="生成语言（缺省 cn）")
    parser.add_argument("--level", type=int, default=80, help="面板等级（缺省 80）")
    args = parser.parse_args()

    from hsr_nous.pipeline.build.loader import (
        list_characters,
        list_light_cones,
        list_relic_sets,
    )
    from hsr_nous.pipeline.enemies.loader import list_monster_ids
    from hsr_nous.pipeline.stages.loader import list_hakushin_monster_ids, list_stages

    out_root = args.out
    out_dirs = {kind: f"{out_root}/{kind}" for kind in _OUT_DIRS}

    # (kind, roster, writer)；descriptions 按角色花名册逐 id 生成（不走默认目录 glob，
    # --out 注入时保持同根）
    def _rosters() -> List[tuple]:
        stage_jobs: List[tuple] = []
        enemy_ids = set(list_monster_ids())
        for mode in ("moc", "pf", "as"):
            enemy_ids.update(list_hakushin_monster_ids(mode))
            for period in list_stages(mode):
                if period["source"] == "hakushin":
                    stage_jobs.append((mode, period["id"]))
        return [
            ("characters", [cid for cid, _ in list_characters(lang=args.lang)],
             lambda cid: write_character_template(
                 cid, out_dir=out_dirs["characters"], level=args.level, lang=args.lang)),
            ("light_cones", [lid for lid, _ in list_light_cones(lang=args.lang)],
             lambda lid: write_light_cone_template(
                 lid, out_dir=out_dirs["light_cones"], level=args.level, lang=args.lang)),
            ("relics", [sid for sid, _ in list_relic_sets(lang=args.lang)],
             lambda sid: write_relic_set_template(
                 sid, out_dir=out_dirs["relics"], lang=args.lang)),
            ("enemies", sorted(enemy_ids),
             lambda eid: write_enemy_template(
                 eid, out_dir=out_dirs["enemies"], level=args.level)),
            ("descriptions", [cid for cid, _ in list_characters(lang=args.lang)],
             lambda cid: write_description_sidecar(
                 cid, out_dir=out_dirs["descriptions"], lang=args.lang,
                 skeleton_dir=out_dirs["characters"])),
            ("stages", stage_jobs,
             lambda job: write_stage_templates_for_period(
                 job[0], job[1], out_dir=out_dirs["stages"])),
        ]

    failures: Dict[str, List[str]] = {}
    for kind, ids, writer in _rosters():
        bad: List[str] = []
        for entity_id in ids:
            try:
                writer(entity_id)
            except Exception as exc:  # 逐个收集，不中断全量
                bad.append(f"{entity_id}: {type(exc).__name__} {exc}")
        if bad:
            failures[kind] = bad
        print(f"[template_generator] {kind}: {len(ids) - len(bad)}/{len(ids)} 生成", flush=True)

    if failures:
        for kind, bad in failures.items():
            print(f"[template_generator] {kind} 失败 {len(bad)} 件：", flush=True)
            for line in bad[:10]:
                print(f"  {line}", flush=True)
        return 1
    print(f"[template_generator] 全量完成 → {out_root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
