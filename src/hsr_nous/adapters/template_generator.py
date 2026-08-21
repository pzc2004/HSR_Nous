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
    max_sp = float(raw.get("max_sp", 120.0))

    merged = load_character_skills_merged(data_dir=data_dir, lang=lang)
    actions: List[Dict[str, Any]] = []
    scaling_notes: List[str] = []
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
