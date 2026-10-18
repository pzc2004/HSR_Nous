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


def clear_data_cache() -> None:
    """数据缓存失效钩子（update 落盘后调用——同 build.loader 先例）."""
    _load_table.cache_clear()
    _instance_map.cache_clear()
    _template_map.cache_clear()
    _skill_map.cache_clear()
    _elite_map.cache_clear()
    _hard_map.cache_clear()


@lru_cache(maxsize=4)
def _instance_map(tbgd_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """MonsterConfig → {MonsterID: 行}（实例层：修正系数/弱点/抗性/技能表/AI 覆写）."""
    return {str(r["MonsterID"]): r for r in _load_table("MonsterConfig.json", tbgd_dir)}


@lru_cache(maxsize=4)
def _template_map(tbgd_dir: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """MonsterTemplateConfig → {MonsterTemplateID: 行}（模板层：base 值/Rank/默认 AI）."""
    return {str(r["MonsterTemplateID"]): r for r in _load_table("MonsterTemplateConfig.json", tbgd_dir)}


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


def list_monster_ids(*, tbgd_dir: Optional[str] = None) -> List[str]:
    """怪物模板花名册（MonsterTemplateConfig 顶层 id——与 hakushin monstervalue
    顶层 632 键一一对应，对拍表钉同集）."""
    return sorted(_template_map(tbgd_dir).keys())


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

    返回 {level, hp, atk, def_, spd, max_toughness, effect_res, weakness, resistance,
          _level_clamped, _missing_bases}——原面板键与 hakushin 版同构，
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
    data = json.loads(path.read_text(encoding="utf-8"))
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
    data = json.loads(path.read_text(encoding="utf-8"))
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
