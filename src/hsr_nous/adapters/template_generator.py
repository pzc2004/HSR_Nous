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


def _enemy_direct_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """TBGD 技能 + Fandom 对齐条目 → 单段直接攻击；任一语义不确定则不收编."""
    skill_type = semantic.get("type")
    if skill_type not in {"Basic ATK", "Single Target", "Blast", "AoE ATK"}:
        return None
    sp_hit_base = raw.get("sp_hit_base")
    if (not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    params = raw.get("param_list") or []
    desc = semantic.get("desc") or ""
    ratios = [float(x) / 100.0 for x in _ENEMY_ATK_RATIO_RE.findall(desc)]
    if skill_type == "Blast" and ("," in desc or desc.count(".") != 1):
        return None  # 自爆/条件/附加效果不是纯 Blast 直伤，留给独立机制收编
    expected_params = 2 if skill_type == "Blast" and len(params) == len(ratios) == 2 else 1
    if len(params) != expected_params or len(ratios) != expected_params:
        return None
    if any(abs(float(param) - ratio) > 1e-9 for param, ratio in zip(params, ratios)):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    if f"{element} DMG" not in desc:
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
        "damage_type": raw["damage_type"].lower(),
        "scaling": [{"atk": ratios[0]}],
        "toughness_dmg": int(sp_hit_base),
        "energy_gain": 0,
        "energy_grant": float(semantic.get("energy") or 0.0),
    }
    if target_type == "blast" and len(ratios) == 2:
        # 主副倍率分开时显式写；单倍率 Blast 由引擎沿用主倍率。副削韧均按 rulebook 候选。
        action["scaling_blast"] = [{"atk": ratios[1]}]
    return action


def _enemy_bounce_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Bounce（固定次数、每段同倍率随机单体）→ 现有多段 bounce action."""
    if semantic.get("type") != "Bounce":
        return None
    match = re.fullmatch(
        r"Deals successive \(×(\d+)\) (\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to random targets\.", semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    count = int(match.group(1))
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    ratio = float(match.group(3)) / 100.0
    if (count <= 0 or match.group(2) != element or len(params) != 2
            or abs(float(params[0]) - ratio) > 1e-9 or float(params[1]) != count):
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


def _enemy_restore_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_name: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Restore（仅“按施放者 Max HP 比例治疗敌方全体”）→ 支援 action + heal hook."""
    if semantic.get("type") != "Restore":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        rf"Immediately recovers all friendly units' HP \((\d+(?:\.\d+)?)% "
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
    """单体火伤 + Burn → 直接攻击 + 非叠层 DoT hook."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Fire":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Fire DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), "
        r"with a high chance \((\d+(?:\.\d+)?)% (Base Chance|ATK)\) to Burn the target "
        r"\((\d+) Turns, (\d+(?:\.\d+)?)% ATK DoT\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    duration = int(match.group(4))
    dot_ratio = float(match.group(5)) / 100.0
    expected = [damage_ratio, base_chance, float(duration), dot_ratio]
    if (match.group(3) == "ATK" and base_chance != 1.0) or len(params) != 4:
        return None
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
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
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_BURN",
                "name": "Burn",
                "modifier_type": "dot",
                "dot_element": "fire",
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


def _enemy_wind_shear_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """单体风伤 + 可叠层 Wind Shear → 直接攻击 + DoT hook."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Wind":
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?Wind DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (?:a single target|one designated target), "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to inflict Wind Shear "
        r"(?:on the target )?\((\d+(?:\.\d+)?)% ATK DoT Per Stack, "
        r"(\d+) Turns, Max (\d+) Stacks\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    dot_ratio = float(match.group(3)) / 100.0
    duration = int(match.group(4))
    max_stack = int(match.group(5))
    if len(params) == 4:
        expected = [damage_ratio, base_chance, float(duration), dot_ratio]
    elif len(params) == 5:
        expected = [damage_ratio, base_chance, float(duration), dot_ratio, float(max_stack)]
    else:
        return None
    if any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected)):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "single",
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
            "target": "$event.target",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_WIND_SHEAR",
                "name": "Wind Shear",
                "modifier_type": "dot",
                "dot_element": "wind",
                "dot_ratio": dot_ratio,
                "dot_base_chance": base_chance,
                "duration": duration,
                "max_stack": max_stack,
                "stack_mode": "refresh",
                "dispellable": True,
            },
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
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
    dot_ratio = float(match.group(3)) / 100.0
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
                "dot_ratio_expr": f"{dot_ratio} * $self.max_hp",
                "dot_base_chance": base_chance,
                "duration": duration,
                "max_stack": 1,
                "stack_mode": "refresh",
                "dispellable": True,
            },
        }],
    }
    return action, hook


def _enemy_imprison_action(
    raw: Dict[str, Any], semantic: Dict[str, Any],
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """AoE 直伤 + Imprisonment → 攻击 action + 原子推条/减速控制 hook."""
    if semantic.get("type") != "AoE ATK":
        return None
    desc = semantic.get("desc") or ""
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
    per_hit_ratio = float(match.group(2)) / 100.0
    instances = int(match.group(3) or 1)
    base_chance = float(match.group(4)) / 100.0
    delay_ratio = float(match.group(5)) / 100.0
    spd_ratio = float(match.group(6)) / 100.0
    duration = int(match.group(7))
    expected = [per_hit_ratio * instances, base_chance, float(duration), delay_ratio, spd_ratio]
    if (match.group(1) != element or len(params) != 5
            or any(abs(float(param) - value) > 1e-9 for param, value in zip(params, expected))):
        return None
    action_id = str(raw["skill_id"])
    action = {
        "action_id": action_id,
        "name": semantic.get("name") or action_id,
        "action_type": "skill",
        "target_type": "aoe",
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
            "target": "all_allies",
            "apply_chance": base_chance,
            "modifier": {
                "modifier_id": f"ENEMY_{action_id}_IMPRISON",
                "name": "Imprisonment",
                "modifier_type": "debuff",
                "debuff_kind": "control",
                "control_kind": "imprison",
                "stat_effects": {"spd_pct": -spd_ratio},
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
    if skill_type not in {"Single Target", "AoE ATK"}:
        return None
    desc = semantic.get("desc") or ""
    match = re.fullmatch(
        r"Deals (?:minor |massive )?(\w+) DMG \((\d+(?:\.\d+)?)% ATK\) "
        r"to (a single target|one designated target|all targets), "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to reduce "
        r"(the target's|their) DEF \((\d+(?:\.\d+)?)%, (\d+) Turns\)\.", desc)
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    target_type = "single" if skill_type == "Single Target" else "aoe"
    expected_target = (("a single target", "one designated target")
                       if target_type == "single" else ("all targets",))
    expected_possessive = "the target's" if target_type == "single" else "their"
    if (match.group(1) != element or match.group(3) not in expected_target
            or match.group(5) != expected_possessive):
        return None
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(4)) / 100.0
    def_ratio = float(match.group(6)) / 100.0
    duration = int(match.group(7))
    if len(params) == 3:
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
    expected = [damage_ratio, base_chance, vulnerability, float(duration)]
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
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or not raw.get("damage_type") or sp_hit_base is None
            or sp_hit_base < 0 or not float(sp_hit_base).is_integer()):
        return None
    element = {"Thunder": "Lightning"}.get(raw["damage_type"], raw["damage_type"])
    damage_ratio = float(match.group(2)) / 100.0
    base_chance = float(match.group(3)) / 100.0
    duration = int(match.group(4))
    if match.group(1) != element or len(params) != 4:
        return None
    # mechanics 07 §7.4：Weaken=降低造成伤害；第三参数为降伤比例。
    weaken_ratio = float(params[2])
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
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_id: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """Nihility's Command → 随机单体 lock_on + vulnerability marker."""
    if semantic.get("type") != "Lock On":
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
                "modifier_id": f"ENEMY_{owner_id}_LOCK_ON",
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


def _enemy_end_of_bow_action(
    raw: Dict[str, Any], semantic: Dict[str, Any], owner_id: str,
) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
    """End of Bow → 单体量子伤害 + 纠缠延迟伤害/推条 + 解除锁定."""
    if semantic.get("type") != "Single Target" or raw.get("damage_type") != "Quantum":
        return None
    match = re.fullmatch(
        r"Deals massive Quantum DMG \((\d+(?:\.\d+)?)% ATK\) to a single target, "
        r"with a high chance \((\d+(?:\.\d+)?)% Base Chance\) to inflict Entanglement "
        r"\((\d+(?:\.\d+)?)% Action Delay, (\d+(?:\.\d+)?)% ATK Delayed DMG Per Stack\)\.",
        semantic.get("desc") or "")
    params = raw.get("param_list") or []
    sp_hit_base = raw.get("sp_hit_base")
    if (not match or sp_hit_base is None or sp_hit_base < 0
            or not float(sp_hit_base).is_integer()):
        return None
    damage_ratio = float(match.group(1)) / 100.0
    base_chance = float(match.group(2)) / 100.0
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
                "modifier_id": f"ENEMY_{action_id}_ENTANGLE",
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


def _enemy_timed_charge_action(raw: Dict[str, Any], semantic: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """无额外数值的定时蓄力 → self 支援 action，下一技能由原始序列推进."""
    if (semantic.get("type") != "Charge"
            or semantic.get("desc") != "The next action uses Self-Exploding Module."
            or (raw.get("param_list") or [])):
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
    if hp_cost and (len(params) != 1 or abs(float(params[0]) - hp_cost) > 1e-9):
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
        r"(?:DMG|ATK)?(?: Boost)?, (\d+) Turn\)\. "
        r"The next action (?:uses|casts) .+", desc)
    params = raw.get("param_list") or []
    if not match or len(params) != 1:
        return None
    ratio = float(match.group(1)) / 100.0
    duration = int(match.group(2))
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


def generate_enemy_template(
    enemy_id: str,
    *,
    level: int = 80,
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """pipeline 数据 → 敌人模板 dict（通用序列 AI 的直接攻击子集）.

    面板与技能数值来自 TBGD；Fandom 只提供技能名、目标范围、攻击类型与倍率文本
    交叉证据。只有主动技能表逐项对齐且序列非空时才生成 actions/policy：通用
    SequenceThree 允许部分覆盖，专属 AIPath 仅序列全部可表达时收编；不做空序列兜底。
    """
    from hsr_nous.pipeline.enemies.loader import (
        calc_enemy_stats, get_enemy_ai, get_enemy_ai_config, get_enemy_detail,
        get_enemy_mechanics, get_enemy_skills, get_monster_meta)
    from hsr_nous.sim_schema.config_ai import has_initial_decision, unsupported_config_nodes

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
    paired = list(zip(active_raw, semantic_skills)) if len(active_raw) == len(semantic_skills) else []
    if semantic_skills and not paired:
        notes.append("TBGD 主动技能与 Fandom 条目数量不一致，未做技能语义对齐")

    ai = get_enemy_ai(enemy_id, tbgd_dir=tbgd_dir) or {}
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir) or {}
    if ai.get("ai_path_override"):
        ai_path = ai["ai_path_override"]
        sequence = ai.get("skill_sequence_override") or []
    else:
        ai_path = ai.get("ai_path")
        sequence = ai.get("skill_sequence") or []
    policy: Optional[Dict[str, Any]] = None
    actions: List[Dict[str, Any]] = []
    enemy_hooks: List[Dict[str, Any]] = []
    enemy_summons: List[Dict[str, Any]] = []
    if sequence and paired:
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
            candidate_actions: List[Dict[str, Any]] = []
            candidate_hooks: List[Dict[str, Any]] = []
            candidate_summons: List[Dict[str, Any]] = []
            for raw, semantic in paired:
                if raw["skill_id"] not in sequence:
                    continue
                action = _enemy_direct_action(raw, semantic)
                if action is None:
                    action = _enemy_bounce_action(raw, semantic)
                hook = None
                if action is None:
                    support = _enemy_restore_action(raw, semantic, name_en)
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
                    support = _enemy_delay_action(raw, semantic)
                    if support is not None:
                        action, hook = support
                if action is None:
                    support = _enemy_nihility_command_action(raw, semantic, str(detail["MonsterID"]))
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
                    support = _enemy_self_destruct_action(raw, semantic)
                    if support is not None:
                        action, hook = support
                if action is None:
                    support = _enemy_trashcan_enhance_action(raw, semantic)
                    if support is not None:
                        action, hook = support
                if action is None:
                    support = _enemy_defense_action(raw, semantic)
                    if support is not None:
                        action, hook = support
                if action is None:
                    support = _enemy_summon_action(
                        raw, semantic, detail, get_monster_meta, level=level)
                    if support is not None:
                        action, hook, summon_specs = support
                        candidate_summons.extend(summon_specs)
                if action is None:
                    action = _enemy_timed_charge_action(raw, semantic)
                if action is None:
                    support = _enemy_charge_action(raw, semantic)
                    if support is not None:
                        action, hook = support
                if action is not None:
                    candidate_actions.append(action)
                    if action["target_type"] == "blast":
                        notes.append(
                            f"技能 {action['action_id']} 副目标削韧按 rulebook 比例候选，待真实 golden")
                    if hook is not None:
                        candidate_hooks.append(hook)
                        if any((eff.get("modifier") or {}).get("modifier_type") == "dot"
                               for eff in hook["effects"]):
                            notes.append(f"技能 {action['action_id']} Shock 重施加按 refresh 候选，待真实 golden")
            covered_ids = {a["action_id"] for a in candidate_actions}
            full_sequence = all(skill_id in covered_ids for skill_id in sequence)
            # 通用 SequenceThree 允许部分覆盖并显式跳过；专属 AIPath 只在序列
            # 全部可表达时收编，避免把未知专属状态机压成普通轮转。
            if ai_path == _ENEMY_SEQUENCE_AI or full_sequence:
                actions = candidate_actions
                enemy_hooks = candidate_hooks
                enemy_summons = candidate_summons
                policy = {
                    "sequence": [str(x) for x in sequence],
                    "cooldown": cooldown,
                    "initial_cooldown": initial_cooldown,
                    "skill_phases": {
                        str(sk["skill_id"]): list(sk["phase_list"])
                        for sk in raw_skills if sk.get("phase_list")
                    },
                }
                if ai_path:
                    raw_config = get_enemy_ai_config(ai_path, tbgd_dir=tbgd_dir)
                    if raw_config is not None:
                        available_skill_names = {
                            str(sk["trigger_key"]) for sk in raw_skills
                            if sk.get("trigger_key") and sk["skill_id"] in covered_ids
                        }
                        bad = unsupported_config_nodes(raw_config, available_skill_names)
                        if not bad and not has_initial_decision(raw_config, available_skill_names):
                            bad = {"initial:no-executable-decision"}
                        if not bad:
                            policy["skill_ids"] = {
                                str(sk["trigger_key"]): str(sk["skill_id"])
                                for sk in raw_skills if sk.get("trigger_key")
                            }
                            policy["config"] = raw_config
                        else:
                            notes.append(f"ConfigAI 未收编节点：{', '.join(sorted(bad))}")
                for skill_id in sequence:
                    if skill_id not in covered_ids:
                        notes.append(f"序列技能 {skill_id} 未收编，运行时显式跳过")
            else:
                notes.append(f"AIPath {ai_path!r} 含未收编技能，专属 AI 不生成 actions/policy")
    elif not sequence:
        notes.append("AISkillSequence 为空，不做表序兜底")
    elif not paired:
        notes.append("技能语义未对齐，actions/policy 不生成")

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
        **({"hooks": enemy_hooks} if enemy_hooks else {}),
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
