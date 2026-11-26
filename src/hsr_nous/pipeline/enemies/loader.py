"""enemies 域统一查询（turnbasedgamedata 怪物五表 + 关卡目标表口径）.

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

数据加载：各表全量 lru_cache（表不大，整表驻留比按行查快；clear_data_cache 一并清）。
Ability 机制侧另按 `JsonConfig` 读 CharacterConfig，并以本地文件内的实际 Ability/Modifier
Name 建引用闭包（`get_enemy_ability_sources`）；缺失、歧义和坏文件显式返回，不按文件名猜实体。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
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
def _load_table(name: str, tbgd_dir: Optional[str] = None) -> Any:
    path = (Path(tbgd_dir) / name) if tbgd_dir is not None else _paths.tbgd_file(name)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def _load_json_path(path_str: str) -> Any:
    """按绝对路径缓存 JSON 整表（monster.json/fandom_enemy_data.json 等逐行查询源）."""
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def clear_data_cache() -> None:
    """数据缓存失效钩子（update 落盘后调用——同 build.loader 先例）."""
    _load_table.cache_clear()
    _load_json_path.cache_clear()
    _instance_map.cache_clear()
    _template_map.cache_clear()
    _custom_value_tags.cache_clear()
    _skill_map.cache_clear()
    _elite_map.cache_clear()
    _hard_map.cache_clear()
    _battle_target_map.cache_clear()
    _ability_index.cache_clear()
    get_body_part_values.cache_clear()
    get_monster_ids_by_config_alias.cache_clear()
    get_monster_id_by_config_alias.cache_clear()


@lru_cache(maxsize=4)
def _instance_map(tbgd_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """MonsterConfig → {MonsterID: 行}（实例层：修正系数/弱点/抗性/技能表/AI 覆写）."""
    return {str(r["MonsterID"]): r for r in _load_table("MonsterConfig.json", tbgd_dir)}


@lru_cache(maxsize=4)
def _template_map(tbgd_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """MonsterTemplateConfig → {MonsterTemplateID: 行}（模板层：base 值/Rank/默认 AI）."""
    return {str(r["MonsterTemplateID"]): r for r in _load_table("MonsterTemplateConfig.json", tbgd_dir)}


@lru_cache(maxsize=4)
def _custom_value_tags(tbgd_dir: Optional[str] = None) -> frozenset:
    """实例/模板 CustomValueTags 全集（ConfigAI 哈希反查只读名册）."""
    tags = set()
    for row in (*_instance_map(tbgd_dir).values(), *_template_map(tbgd_dir).values()):
        tags.update(str(tag) for tag in row.get("CustomValueTags") or [])
    return frozenset(tags)


@lru_cache(maxsize=4)
def _skill_map(tbgd_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    return {str(r["SkillID"]): r for r in _load_table("MonsterSkillConfig.json", tbgd_dir)}


@lru_cache(maxsize=4)
def _elite_map(tbgd_dir: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
    return {int(r["EliteGroup"]): r for r in _load_table("EliteGroup.json", tbgd_dir)}


@lru_cache(maxsize=4)
def _hard_map(tbgd_dir: Optional[str] = None) -> Dict[int, Dict[int, Dict[str, Any]]]:
    """HardLevelGroup → {group: {level: 行}}（等级钳级在消费侧）."""
    out: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for r in _load_table("HardLevelGroup.json", tbgd_dir):
        out.setdefault(int(r["HardLevelGroup"]), {})[int(r["Level"])] = r
    return out


@lru_cache(maxsize=4)
def _battle_target_map(tbgd_dir: Optional[str] = None) -> Dict[int, float]:
    return {int(row["ID"]): _v(row["TargetParam"])
            for row in _load_table("BattleTargetConfig.json", tbgd_dir)
            if row.get("TargetParam") is not None}


def get_battle_target_param(battle_target_id: int, *, tbgd_dir: Optional[str] = None) -> Optional[float]:
    """关卡目标的 TargetParam 静态阈值；未知 ID 返回 None，表缺失由调用方显式处理."""
    return _battle_target_map(tbgd_dir).get(int(battle_target_id))


@lru_cache(maxsize=32)
def get_body_part_values(enemy_id: str, *, tbgd_dir: Optional[str] = None) -> Dict[str, Any]:
    """主体及部位变体共享的 PartEntityN_MonsterID 配置；由部位 ID 反查所属主体."""
    direct = get_enemy_ability_sources(enemy_id, tbgd_dir=tbgd_dir).get("custom_values") or {}
    if any(str(key).startswith("PartEntity") and str(key).endswith("_MonsterID")
           for key in direct):
        return direct
    matches = []
    for candidate in list_monster_ids(tbgd_dir=tbgd_dir):
        values = get_enemy_ability_sources(candidate, tbgd_dir=tbgd_dir).get("custom_values") or {}
        if any(str(key).startswith("PartEntity") and str(key).endswith("_MonsterID")
               and _is_int_like(value) and int(value) == int(enemy_id)
               for key, value in values.items()):
            matches.append(values)
    return matches[0] if len(matches) == 1 else {}


def _is_int_like(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer()


def list_monster_ids(*, tbgd_dir: Optional[str] = None) -> List[str]:
    """怪物模板花名册（MonsterTemplateConfig 顶层 id——与 hakushin monstervalue
    顶层 632 键一一对应，对拍表钉同集）."""
    return sorted(_template_map(tbgd_dir).keys())


def list_custom_value_tags(*, tbgd_dir: Optional[str] = None) -> List[str]:
    """全部已知 CustomValueTags（排序输出供 ConfigAI 哈希归一化）."""
    return sorted(_custom_value_tags(tbgd_dir))


def get_enemy_detail(
    enemy_id: str,
    *,
    tbgd_dir: Optional[str] = None,
    enemies_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按 ID 查怪物实例 + 模板合并视图（{_source: "tbgd", ...实例行, "_template": 模板行}）.

    主源 tbgd 五表；tbgd 查无（或五表文件缺失——与旧 hakushin 主源缺失同语义）时
    回退 theBowja 遗留快照（断更于游戏 3.2，**冻结保留**——停更但保留可读作回退）：
    Id/ElementalResistance/SkillList 等技能与抗性表，返回标 ``_source: "bowja_legacy"``
    + ``_stale: True``。两源均无该 id 返回 None（不静默编造）。
    """
    try:
        inst = _instance_map(tbgd_dir).get(str(enemy_id))
        if inst is not None:
            tpl = _template_map(tbgd_dir).get(str(inst.get("MonsterTemplateID")))
            if tpl is not None:
                return {"_source": "tbgd", **inst, "_template": tpl}
    except FileNotFoundError:
        pass  # 主源五表缺失 → 按「主源缺失」走回退链（同旧 hakushin 缺失语义）

    bowja_path = (
        Path(enemies_path) if enemies_path is not None
        else _paths.enemies_dir() / "enemies.json"
    )
    if bowja_path.exists():
        legacy = json.loads(bowja_path.read_text(encoding="utf-8")).get(str(enemy_id))
        if legacy is not None:
            return {"_source": "bowja_legacy", "_stale": True, **legacy}
    return None


# 效果抗性等级加算（mechanics 01 §1.2：Lv.51-75 每级 +0.4%，上限 +10%）
#——与 stages/loader._effect_res_bonus 同式镜像（P3 切源后 stages 侧退役，此处为正典）
def _effect_res_bonus(level: int) -> float:
    return min(max(level - 50, 0) * 0.004, 0.10)


def calc_enemy_stats(
    enemy_id: str,
    level: int,
    *,
    tbgd_dir: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """计算怪物在指定等级下的面板（tbgd 五表口径，公式链与 hakushin 版逐键同构）.

    公式链（系数全在 tbgd 五表，无外部假设）：
        面板 = base(模板) × HardLevelGroup[group, level].XxxRatio
                   × EliteGroup[elite].XxxRatio × 实例.XxxModifyRatio
        spd/max_toughness 另加 实例+模板 的 Speed/StanceModifyValue 平加项（有意差异，
        见模块 docstring）；效果抗性 = StatusResistanceBase + 等级加算（Lv.51-75 上限 +10%）。
    等级超出 HardLevelGroup 表内范围时钳到表内最大级（同 hakushin 版语义）。

    返回 {level, hp, atk, def_, spd, max_toughness, max_special_sp, initial_special_sp,
          effect_res, weakness, resistance, _level_clamped, _missing_bases}——原面板键与 hakushin 版同构，
    resistance 为 TBGD DamageTypeResistance 结构化净增量；怪物不存在返回 None。
    """
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir)
    if detail is None or detail.get("_source") != "tbgd":
        return None
    tpl = detail["_template"]

    group = _hard_map(tbgd_dir).get(int(detail.get("HardLevelGroup") or 1))
    if not group:
        return None
    clamped_level = min(level, max(group))
    hard = group[clamped_level]
    elite = _elite_map(tbgd_dir).get(int(detail.get("EliteGroup") or 1), {})

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
    config = get_enemy_ability_sources(enemy_id, tbgd_dir=tbgd_dir).get("character_config") or {}
    return {
        "level": level,
        "max_special_sp": float(_v(config.get("MaxSpecialSP")) or 0.0),
        "initial_special_sp": float(_v(config.get("CurrentSpecialSP")) or 0.0),
        "hp": _chain(bases["HPBase"], "HPRatio", "HPModifyRatio"),
        "atk": _chain(bases["AttackBase"], "AttackRatio", "AttackModifyRatio"),
        "def_": _chain(bases["DefenceBase"], "DefenceRatio", "DefenceModifyRatio"),
        "spd": spd,
        "max_toughness": max_toughness,
        "effect_res": float(_v(tpl.get("StatusResistanceBase")) or 0.0)
        + _effect_res_bonus(level),
        "weakness": [w.lower() for w in (detail.get("StanceWeakList") or [])],
        "resistance": {
            str(r["DamageType"]).lower(): float(_v(r.get("Value")) or 0.0)
            for r in detail.get("DamageTypeResistance") or [] if r.get("DamageType")
        },
        "_level_clamped": clamped_level != level,
        "_missing_bases": missing,
    }


def get_enemy_skills(
    enemy_id: str, *, tbgd_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """怪物技能清单（MonsterConfig.SkillList join MonsterSkillConfig）——tbgd 净增量.

    每技能：{skill_id, trigger_key, type_desc, damage_type, attack_type,
             sp_hit_base(削韧), delay_ratio(行动延迟), ai_cd, ai_icd,
             param_list(倍率), phase_list, modifier_list}；
    名字/描述是 TextMap hash 不收录（命名口径见模块 docstring）。
    怪物不存在 → []；技能表空 → []。
    """
    inst = _instance_map(tbgd_dir).get(str(enemy_id))
    if inst is None:
        return []
    out: List[Dict[str, Any]] = []
    for sid in inst.get("SkillList") or []:
        sk = _skill_map(tbgd_dir).get(str(sid))
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


def get_enemy_ai(
    enemy_id: str, *, tbgd_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """怪物 AI 行为（模板默认 + 实例覆写）——tbgd 净增量.

    返回 {ai_path(模板默认), ai_path_override(实例覆写),
          skill_sequence(模板默认出招循环), skill_sequence_override(实例覆写)}；
    AISkillSequence 元素是 Unity 混淆键单键 dict（值=SkillID），解为裸 id 表；
    怪物不存在 → None。
    """
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir)
    if detail is None or detail.get("_source") != "tbgd":
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


def get_enemy_ai_config(ai_path: str, *, tbgd_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按 AIPath 读取 ConfigAI 原始行为树；文件缺失返回 None，路径穿越直接拒绝."""
    if not ai_path or ai_path.startswith(("/", "\\")) or ".." in Path(ai_path).parts:
        raise ValueError(f"非法 AIPath {ai_path!r}")
    root = Path(tbgd_dir) if tbgd_dir is not None else _paths.turnbasedgamedata_dir()
    path = root / ai_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_config(parent: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
    """Config 继承合并：dict 递归合并，列表/标量子级覆盖."""
    out = dict(parent)
    for key, value in child.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_config(out[key], value)
        else:
            out[key] = value
    return out


def _load_config_json(relative_path: str, tbgd_dir: Optional[str],
                      _seen: Optional[frozenset] = None) -> Optional[Dict[str, Any]]:
    """读取仓库根部 Config JSON；拒绝穿越，缺文件与 AI 配置一样返回 None.

    显式 ParentConfigPath 递归继承：父 Config 先加载，子级覆盖；父路径缺失或循环显式报错。
    """
    if (not relative_path or relative_path.startswith(("/", "\\"))
            or ".." in Path(relative_path).parts):
        raise ValueError(f"非法 Config 路径 {relative_path!r}")
    seen = _seen or frozenset()
    if relative_path in seen:
        raise ValueError(f"Config ParentConfigPath 循环：{relative_path}")
    try:
        value = _load_table(relative_path, tbgd_dir)
    except FileNotFoundError:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Config 须为 JSON object：{relative_path}")
    parent_path = str(value.get("ParentConfigPath") or "")
    if parent_path:
        parent = _load_config_json(parent_path, tbgd_dir, seen | {relative_path})
        if parent is None:
            raise ValueError(f"Config 父路径缺失：{relative_path} -> {parent_path}")
        value = _merge_config(parent, value)
    return value


@lru_cache(maxsize=None)
def get_monster_ids_by_config_alias(alias: str, *, tbgd_dir: Optional[str] = None) -> tuple[str, ...]:
    """将字面 Monster_* 配置别名解析为有序模板 ID 集；缺失返回空."""
    matches = set()
    for row in _load_table("MonsterTemplateConfig.json", tbgd_dir):
        config = str(row.get("JsonConfig") or "")
        if Path(config).name == f"{alias}_Config.json":
            monster_id = row.get("MonsterTemplateID")
            if isinstance(monster_id, int):
                matches.add(str(monster_id))
    return tuple(sorted(matches))


@lru_cache(maxsize=None)
def get_monster_id_by_config_alias(alias: str, *, tbgd_dir: Optional[str] = None) -> Optional[str]:
    """仅当配置别名对应唯一模板 ID 时返回该 ID."""
    matches = get_monster_ids_by_config_alias(alias, tbgd_dir=tbgd_dir)
    return matches[0] if len(matches) == 1 else None


def get_enemy_character_config(
    enemy_id: str, *, tbgd_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 MonsterTemplateConfig.JsonConfig 读取角色技能/Ability 入口配置."""
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir)
    if not detail or detail.get("_source") != "tbgd":
        return None
    relative = str((detail.get("_template") or {}).get("JsonConfig") or "")
    return _load_config_json(relative, tbgd_dir) if relative else None


@lru_cache(maxsize=4)
def _ability_index(tbgd_dir: Optional[str] = None) -> Dict[str, Any]:
    """本地 Ability 与公共 Modifier 内容索引；文件名只用于枚举，实体解析以文件内 Name 为准."""
    root = Path(tbgd_dir) if tbgd_dir is not None else _paths.turnbasedgamedata_dir()
    config_root = root / "Config" / "ConfigAbility"
    global_root = root / "Config" / "ConfigGlobalModifier"
    task_template_root = root / "Config" / "ConfigGlobalTaskListTemplate"
    abilities: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    modifiers: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    target_aliases: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    global_templates: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    invalid_files: List[str] = []
    if not any(path.exists() for path in (config_root, global_root, task_template_root)):
        return {"abilities": abilities, "modifiers": modifiers,
                "target_aliases": target_aliases, "global_templates": global_templates,
                "invalid_files": invalid_files}
    for path in sorted(config_root.rglob("*.json")):
        if path.name.endswith(".layout.json"):
            continue
        relative = path.relative_to(root).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid_files.append(relative)
            continue
        for ability in doc.get("AbilityList") or []:
            name = ability.get("Name")
            if name:
                abilities.setdefault(str(name), []).append((relative, ability))
                for modifier_name, modifier in (ability.get("Modifiers") or {}).items():
                    modifiers.setdefault(str(modifier_name), []).append((relative, modifier))
        for name, modifier in (doc.get("GlobalModifiers") or {}).items():
            modifiers.setdefault(str(name), []).append((relative, modifier))
        for name, alias in (doc.get("GlobalTargetAlias") or {}).items():
            target_aliases.setdefault(str(name), []).append((relative, alias))
        for template in doc.get("GlobalTemplates") or []:
            name = template.get("Name")
            if name:
                global_templates.setdefault(str(name), []).append((relative, template))
    for path in sorted(global_root.rglob("*.json")):
        if path.name.endswith(".layout.json"):
            continue
        relative = path.relative_to(root).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid_files.append(relative)
            continue
        for name, modifier in (doc.get("ModifierMap") or {}).items():
            modifiers.setdefault(str(name), []).append((relative, modifier))
    for path in sorted(task_template_root.rglob("*.json")):
        if path.name.endswith(".layout.json"):
            continue
        relative = path.relative_to(root).as_posix()
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid_files.append(relative)
            continue
        for template in doc.get("TaskListTemplate") or []:
            name = template.get("Name")
            if name:
                global_templates.setdefault(str(name), []).append((relative, template))
    return {"abilities": abilities, "modifiers": modifiers,
            "target_aliases": target_aliases, "global_templates": global_templates,
            "invalid_files": invalid_files}


def _is_camera_ability(name: Any) -> bool:
    text = str(name or "")
    return (text.endswith(("_Camera", "DeathSetCamera", "MuteHitFly")) or "_Camera_" in text
            or ("_Camera" in text and text.rsplit("_Camera", 1)[1].isdigit()))


def _config_refs(value: Any):
    """提取编译所需的嵌套 Ability / modifier 引用；Camera 是纯表现层，不入闭包."""
    if isinstance(value, dict):
        node_type = str(value.get("$type") or "")
        if node_type == "RPG.GameCore.TargetAlias" and value.get("Alias"):
            alias = str(value["Alias"])
            yield "alias", alias
            for part in (part.strip() for part in alias.split("+")):
                if part and part != alias:
                    yield "alias", part
            base_alias = alias
            while True:
                stripped = re.sub(
                    r"\.Select\d+$|\.(?:WithServant|RemoveUnselectable|GetAliveOnly|Shuffle)$",
                    "", base_alias)
                if stripped == base_alias:
                    break
                base_alias = stripped
            if base_alias != alias:
                yield "alias", base_alias
        if node_type == "RPG.GameCore.TriggerParallelAbility":
            for row in value.get("ParallelAbilityList") or []:
                raw = row.get("AbilityName") or {}
                name = raw.get("Value") if isinstance(raw, dict) else raw
                if name and not _is_camera_ability(name):
                    yield "ability", str(name)
        elif node_type in {"RPG.GameCore.TriggerAbility", "RPG.GameCore.TurnInsertAbility",
                         "RPG.GameCore.AddStageAbilityByName", "RPG.GameCore.OwnerEntityAddAbility"}:
            raw = value.get("StageAbilityName" if node_type == "RPG.GameCore.AddStageAbilityByName"
                            else "AbilityName")
            name = raw.get("Value") if isinstance(raw, dict) else raw
            if name and not _is_camera_ability(name):
                yield "ability", str(name)
        elif node_type in {"RPG.GameCore.IncludeTaskListTemplate",
                           "RPG.GameCore.IncludeGlobalTaskListTemplate"}:
            raw = value.get("Name")
            name = raw.get("Value") if isinstance(raw, dict) else raw
            if name:
                yield "template", str(name)
        elif node_type == "RPG.GameCore.AddModifier":
            for field in ("ModifierName", "ReferenceModifierName"):
                raw = value.get(field)
                name = raw.get("Value") if isinstance(raw, dict) else raw
                if name:
                    yield "modifier", str(name)
        for child in value.values():
            yield from _config_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _config_refs(child)


def _select_index_entry(
    entries: List[tuple[str, Dict[str, Any]]], source_hint: Optional[str]
) -> Optional[tuple[str, Dict[str, Any]]]:
    """同名定义优先取引用者同文件；其余只在内容唯一时接受，歧义不猜."""
    if source_hint:
        local = [entry for entry in entries if entry[0] == source_hint]
        if len(local) == 1:
            return local[0]
    distinct: List[tuple[str, Dict[str, Any]]] = []
    for entry in entries:
        if not any(entry[1] == old[1] for old in distinct):
            distinct.append(entry)
    return distinct[0] if len(distinct) == 1 else None


def get_enemy_ability_sources(
    enemy_id: str, *, tbgd_dir: Optional[str] = None
) -> Dict[str, Any]:
    """返回某敌人 EntryAbility 的本地引用闭包及显式缺失/歧义清单.

    解析链为 JsonConfig → SkillList.EntryAbility / AbilityList → TriggerAbility /
    TurnInsertAbility / IncludeTaskListTemplate / AddModifier（含 ReferenceModifierName）。不会按怪物名猜 Ability 文件名；只有已下载
    文件里的实际 Name 才能满足引用。TargetAlias 引用同样递归进入闭包，可从其他文件
    装载唯一定义；带 SelectN/WithServant 等后缀的引用同时登记基底别名，别名队列与
    Ability/modifier/template 队列一样完整排空。内建别名不因此误判缺失。modifier 优先取实际引用它的 Ability 局部定义；
    同一闭包引用多份不同局部定义时仍报歧义，其余再按来源文件与内容唯一性消歧。
    """
    config = get_enemy_character_config(enemy_id, tbgd_dir=tbgd_dir)
    if config is None:
        return {"character_config": None, "abilities": {}, "modifiers": {},
                "ability_sources": {}, "source_files": [],
                "missing_abilities": [], "missing_modifiers": [], "ambiguous": []}
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir) or {}
    instance_values = {
        str(item["BFLIFKBEOPJ"]): item.get("MNDFOPKBHKP")
        for item in [*(detail.get("CustomValues") or []), *(detail.get("DynamicValues") or [])]
        if item.get("BFLIFKBEOPJ") is not None
    }
    custom_values = dict(config.get("CustomValues") or {})
    custom_values.update(instance_values)
    monster_template_id = str(
        (detail.get("_template") or {}).get("MonsterTemplateID")
        or detail.get("MonsterTemplateID") or enemy_id)
    ai = get_enemy_ai(enemy_id, tbgd_dir=tbgd_dir) or {}
    ai_path = ai.get("ai_path_override") or ai.get("ai_path")
    config_ai = get_enemy_ai_config(ai_path, tbgd_dir=tbgd_dir) if ai_path else None
    required = {
        str(skill.get("EntryAbility")) for skill in config.get("SkillList") or []
        if skill.get("EntryAbility")
    }
    # 新格式把同一组实例键值放 DynamicValues；实例值仍覆盖 CharacterConfig 同名默认值。
    required.update(str(name) for name in config.get("AbilityList") or [])
    required = {name for name in required if not _is_camera_ability(name)}
    index = _ability_index(tbgd_dir)
    abilities: Dict[str, Any] = {}
    modifiers: Dict[str, Any] = {}
    ability_sources: Dict[str, str] = {}
    source_files: set[str] = set()
    missing_abilities: set[str] = set()
    missing_modifiers: set[str] = set()
    ambiguous: set[str] = set()
    ability_queue = [(name, None) for name in sorted(required)]
    modifier_queue: List[tuple[str, Optional[str]]] = []
    template_queue: List[tuple[str, Optional[str]]] = []
    target_alias_queue: List[tuple[str, Optional[str]]] = []
    global_templates: Dict[str, Any] = {}
    target_aliases: Dict[str, Any] = {}
    local_modifier_candidates: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}
    while ability_queue or modifier_queue or template_queue or target_alias_queue:
        while ability_queue:
            name, hint = ability_queue.pop(0)
            if name in abilities or name in missing_abilities or f"ability:{name}" in ambiguous:
                continue
            entry = _select_index_entry(index["abilities"].get(name, []), hint)
            if entry is None:
                if index["abilities"].get(name):
                    ambiguous.add(f"ability:{name}")
                else:
                    missing_abilities.add(name)
                continue
            source, raw = entry
            abilities[name] = raw
            ability_sources[name] = source
            source_files.add(source)
            for kind, ref in _config_refs(raw):
                if kind == "modifier":
                    local = (raw.get("Modifiers") or {}).get(ref)
                    if local is not None:
                        local_modifier_candidates.setdefault(ref, []).append((source, local))
                {"ability": ability_queue, "modifier": modifier_queue,
                 "template": template_queue, "alias": target_alias_queue}[kind].append((ref, source))
        while modifier_queue:
            name, hint = modifier_queue.pop(0)
            if name in modifiers or name in missing_modifiers or f"modifier:{name}" in ambiguous:
                continue
            candidates = local_modifier_candidates.get(name, [])
            entry = (_select_index_entry(candidates, None) if candidates
                     else _select_index_entry(index["modifiers"].get(name, []), hint))
            if entry is None:
                if candidates or index["modifiers"].get(name):
                    ambiguous.add(f"modifier:{name}")
                else:
                    missing_modifiers.add(name)
                continue
            source, raw = entry
            modifiers[name] = raw
            source_files.add(source)
            for kind, ref in _config_refs(raw):
                {"ability": ability_queue, "modifier": modifier_queue,
                 "template": template_queue, "alias": target_alias_queue}[kind].append((ref, source))
        while template_queue:
            name, hint = template_queue.pop(0)
            entries = index["global_templates"].get(name, [])
            if name in global_templates or f"global_template:{name}" in ambiguous:
                continue
            entry = _select_index_entry(entries, hint)
            if entry is None:
                if entries:
                    ambiguous.add(f"global_template:{name}")
                continue
            source, raw = entry
            global_templates[name] = raw
            source_files.add(source)
            for kind, ref in _config_refs(raw):
                {"ability": ability_queue, "modifier": modifier_queue,
                 "template": template_queue, "alias": target_alias_queue}[kind].append((ref, source))
        while target_alias_queue:
            name, hint = target_alias_queue.pop(0)
            if name in target_aliases or f"target_alias:{name}" in ambiguous:
                continue
            entries = index["target_aliases"].get(name, [])
            if not entries:
                continue
            entry = _select_index_entry(entries, hint)
            if entry is None:
                ambiguous.add(f"target_alias:{name}")
                continue
            source, raw = entry
            target_aliases[name] = raw
            source_files.add(source)
            for kind, ref in _config_refs(raw):
                {"ability": ability_queue, "modifier": modifier_queue,
                 "template": template_queue, "alias": target_alias_queue}[kind].append((ref, source))
    for name, entries in index["target_aliases"].items():
        if name in target_aliases or f"target_alias:{name}" in ambiguous:
            continue
        local = [entry for entry in entries if entry[0] in source_files]
        if len(local) == 1:
            target_aliases[name] = local[0][1]
        elif local:
            ambiguous.add(f"target_alias:{name}")
    return {
        "character_config": config,
        "abilities": abilities,
        "modifiers": modifiers,
        "ability_sources": ability_sources,
        "source_files": sorted(source_files),
        "missing_abilities": sorted(missing_abilities),
        "missing_modifiers": sorted(missing_modifiers),
        "ambiguous": sorted(ambiguous),
        "invalid_files": list(index["invalid_files"]),
        "target_aliases": target_aliases,
        "global_templates": global_templates,
        "custom_values": custom_values,
        "summon_ids": list(detail.get("SummonIDList") or []),
        "custom_value_tags": list_custom_value_tags(tbgd_dir=tbgd_dir),
        "monster_template_id": monster_template_id,
        "config_ai": config_ai,
    }


# ---------------------------------------------------------------------------
# 怪物元信息/语义（自 stages/loader 迁入——monster.json 元信息 + Fandom 语义补充）
# ---------------------------------------------------------------------------

def get_monster_meta(
    enemy_id: str, *, monster_path: Optional[str] = None,
    tbgd_dir: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按 ID 查询 monster.json 怪物元信息（Hakushin 源）.

    返回 {rank, camp, icon, child, weak, en, desc} 原条目（en/zh = 官方英中名——
    命名两态下官方名为合法态）；文件缺失或 id 不存在返回 None。
    monster.json 只按模板 ID 建索引；TBGD 实例 ID 经 MonsterTemplateID 回挂。
    """
    path = (
        Path(monster_path) if monster_path is not None
        else _paths.monster_meta_path()
    )
    if not path.exists():
        return None
    data = _load_json_path(str(path))
    exact = data.get(str(enemy_id))
    if exact is not None:
        return exact
    detail = get_enemy_detail(enemy_id, tbgd_dir=tbgd_dir)
    if detail and detail.get("_source") == "tbgd":
        template_id = detail.get("MonsterTemplateID")
        if template_id is not None:
            return data.get(str(template_id))
    return None


def get_enemy_mechanics(
    page_title: str, *, fandom_enemy_path: Optional[str] = None,
    weakness: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """按 Fandom 页面名查询敌人机制数据（来源 data/fandom_enemy_data.json）.

    **语义补充**——机制描述文本（notes/对拍参照），数值权威是 tbgd 五表。
    数据文件由 pipeline/enemies/semantic.py 生成——文件不存在时返回 None，
    需先跑提取脚本（如 --limit 5 验证后全量）。
    精确名未命中时先尝试 ``<名称> (Boss)`` 页面别名；同名编号变体
    （如 ``Ice Edge (1)``）只在提供 weakness 且能唯一消歧时返回。
    """
    path = (
        Path(fandom_enemy_path) if fandom_enemy_path is not None
        else _paths.fandom_enemy_path()
    )
    if not path.exists():
        return None
    data = _load_json_path(str(path))
    exact = data.get(page_title)
    if exact is None:
        exact = data.get(f"{page_title} (Boss)")
    if exact is not None or weakness is None:
        return exact

    def _weak_set(values: Any) -> set[str]:
        return {"thunder" if str(v).lower() == "lightning" else str(v).lower()
                for v in values or []}

    wanted = _weak_set(weakness)
    prefix = f"{page_title} ("
    candidates = []
    for title, entry in data.items():
        if not title.startswith(prefix) or not title.endswith(")"):
            continue
        if not title[len(prefix):-1].isdigit():
            continue
        if _weak_set(entry.get("weaknesses")) == wanted:
            candidates.append(entry)
    return candidates[0] if len(candidates) == 1 else None
