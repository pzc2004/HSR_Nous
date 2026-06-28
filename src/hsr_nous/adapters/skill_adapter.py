"""技能适配器：将 StarRailRes 技能数据 + Fandom 机制数据 转换为 sim_schema.Action.

Phase 1 模拟器只读 scaling 字段（用于伤害公式），
其它字段（energy_cost/sp_cost/toughness_dmg）保留供未来 Phase 2/3 使用。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.action import Action


_TYPE_TO_SIM = {
    "Normal": "basic",
    "BPSkill": "skill",
    "Ultra": "ultimate",
    "Talent": "talent",
    "Maze": "technique",
    "FollowUp": "follow_up",
}


_DMG_TYPE_TO_INTERNAL = {
    "Physical": "physical",
    "Fire": "fire",
    "Ice": "ice",
    "Thunder": "thunder",
    "Wind": "wind",
    "Quantum": "quantum",
    "Imaginary": "imaginary",
}


def adapt_skill(
    skill_data: Dict[str, Any],
    *,
    character_element: str = "",
) -> Action:
    """把原始 skill_data 字典转为 sim_schema.Action.

    `skill_data` 通常来自 StarRailRes character_skills.json 的某条记录：
        {"id": "101", "name": "...", "type": "BPSkill", "effect": "...", "params": [...]}

    Args:
        skill_data: 技能原始数据
        character_element: 角色元素英文 ID（Fire/Ice/...），用于填充 damage_type
    """
    skill_id = str(skill_data.get("id", ""))
    name = skill_data.get("name", "")
    skill_type = _TYPE_TO_SIM.get(skill_data.get("type", ""), "basic")

    # damage_type: StarRailRes 不直接给，从 effect 或 character_element 推断
    effect = skill_data.get("effect", "")
    damage_type = _DMG_TYPE_TO_INTERNAL.get(character_element, character_element.lower())

    params = skill_data.get("params", [])
    # 取最高等级的 params 做默认 scaling
    # sim.resolver 期望的 key: "atk" / "hp" / "def"（或 "def_"）
    # StarRailRes 的 params 通常是 [atk_coef, hp_coef, def_coef, ...] 三元组
    scaling: List[Dict[str, float]] = []
    if params and isinstance(params[-1], list):
        # params 形如 [[0.5,0,0], [0.55,0,0], ...]，取末级
        last = params[-1]
        scaling.append(
            {
                "atk": float(last[0]) if len(last) > 0 else 0.0,
                "hp": float(last[1]) if len(last) > 1 else 0.0,
                "def_": float(last[2]) if len(last) > 2 else 0.0,
            }
        )
    elif params and isinstance(params[-1], (int, float)):
        # 单标量
        scaling.append({"atk": float(params[-1])})

    return Action(
        action_id=skill_id,
        name=name,
        action_type=skill_type,
        target_type="single",
        damage_type=damage_type or None,
        scaling=scaling,
        energy_cost=int(skill_data.get("energy_cost", 0) or 0),
        energy_gain=int(skill_data.get("energy_gen", 0) or 0),
        skill_point_cost=int(skill_data.get("sp_cost", 0) or 0),
        skill_point_gain=int(skill_data.get("sp_gain", 0) or 0),
        toughness_dmg=int(skill_data.get("toughness_dmg", 0) or 0),
    )


def adapt_skill_by_id(
    skill_id: str,
    *,
    skill_level: int = 7,
    lang: str = "en",
    character_element: str = "",
) -> Optional[Action]:
    """通过 skill_id 查询 raw data + 合并 Fandom 机制字段后转 Action.

    Fandom 数据存在时，会覆盖 energy_cost / sp_cost / toughness_dmg 等字段。
    """
    from hsr_nous.pipeline import get_skill, load_character_skills_merged

    merged = load_character_skills_merged(lang=lang)
    raw = merged.get(skill_id) or get_skill(skill_id, lang=lang)
    if raw is None:
        return None

    return adapt_skill(raw, character_element=character_element)