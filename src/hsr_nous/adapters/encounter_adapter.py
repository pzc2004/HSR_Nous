"""遭遇战适配器：把队伍名 + 敌人 + 遗器关键词 拼成 sim_schema.Encounter.

提供 build_encounter(...) 单一入口，sim_tools 调用此模块即可获得可跑的仿真输入。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Tuple

from hsr_nous.adapters.character_adapter import (
    adapt_character_by_name,
    make_dummy_enemy,
)
from hsr_nous.adapters.skill_adapter import adapt_skill_by_id
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
from hsr_nous.sim_schema.policy import Policy


# 敌人名 → (HP, ATK, DEF, 弱点) 启发式默认值（公开数据缺的字段）
# 来源：HSR 1.5+ 主流忘却之庭/虚构叙事/末日幻影 通用值
_ENEMY_PRESETS: Dict[str, Dict[str, Any]] = {
    "忘却之庭BOSS": {
        "hp": 600000.0,
        "atk": 1500.0,
        "def_": 1000.0,
        "toughness": 120.0,
        "weaknesses": ["thunder", "fire", "ice"],
        "resistance": {"physical": 0.20},
    },
    "末日幻影": {
        "hp": 800000.0,
        "atk": 2000.0,
        "def_": 1200.0,
        "toughness": 180.0,
        "weaknesses": ["ice", "imaginary"],
        "resistance": {"quantum": 0.40},
    },
    "虚构叙事": {
        "hp": 300000.0,
        "atk": 800.0,
        "def_": 600.0,
        "toughness": 60.0,
        "weaknesses": ["fire", "thunder"],
        "resistance": {},
    },
    "DefaultEnemy": {
        "hp": 100000.0,
        "atk": 1000.0,
        "def_": 800.0,
        "toughness": 100.0,
        "weaknesses": [],
        "resistance": {},
    },
}


def _preset_for(enemy_name: str) -> Dict[str, Any]:
    """根据敌人名匹配默认数值，未匹配则用 DefaultEnemy."""
    if enemy_name in _ENEMY_PRESETS:
        return _ENEMY_PRESETS[enemy_name]
    # 模糊匹配：含子串
    for key, preset in _ENEMY_PRESETS.items():
        if key in enemy_name or enemy_name in key:
            return preset
    return _ENEMY_PRESETS["DefaultEnemy"]


def _resolve_enemy(enemy_name: str) -> Actor:
    """解析敌人 Actor：先尝试 theBowja 数据查名字，否则用预设。"""
    try:
        from hsr_nous.pipeline import get_enemy, list_enemies

        # 模糊匹配 theBowja 数据
        for eid, name in list_enemies():
            if name and (enemy_name in name or name in enemy_name):
                data = get_enemy(eid)
                if data:
                    preset = _preset_for(enemy_name)
                    weaknesses = data.get("ElementalWeaknesses", [])
                    return make_dummy_enemy(
                        name=name or enemy_name,
                        weaknesses=[
                            w.lower() if isinstance(w, str) else ""
                            for w in weaknesses
                        ],
                        resistance=data.get("ElementalResistance", {}),
                        hp=preset["hp"],
                        atk=preset["atk"],
                        def_=preset["def_"],
                        toughness=preset["toughness"],
                    )
    except Exception:
        pass

    # 回退：纯预设
    preset = _preset_for(enemy_name)
    return make_dummy_enemy(
        name=enemy_name,
        hp=preset["hp"],
        atk=preset["atk"],
        def_=preset["def_"],
        toughness=preset["toughness"],
        weaknesses=preset["weaknesses"],
        resistance=preset["resistance"],
    )


# 遗器关键词 → 增伤 dmg_bonus 简易映射（数据驱动版待接入 RelicSet）
_RELIC_BONUS: Dict[str, Dict[str, float]] = {
    "雷4": {"thunder": 0.20},
    "雷2+2": {"thunder": 0.10},
    "量子4": {"quantum": 0.20},
    "量子2+2": {"quantum": 0.10},
    "火4": {"fire": 0.20},
    "冰4": {"ice": 0.20},
    "风4": {"wind": 0.20},
    "物理4": {"physical": 0.20},
    "虚数4": {"imaginary": 0.20},
    "快枪手4": {"all": 0.10},
    "快枪手2+2": {"all": 0.05},
    "击破4": {"break_effect_multi": 0.16},
    "默认": {},
}


def _apply_relic_bonus(actor: Actor, relic_set: str) -> Actor:
    """把遗器关键词映射到 dmg_bonus；返回修改后的新 Actor（保持不可变风格）。"""
    bonus = _RELIC_BONUS.get(relic_set, {})
    if not bonus:
        return actor

    if "break_effect_multi" in bonus:
        be_mult = bonus["break_effect_multi"]
        return replace(
            actor,
            stats=replace(actor.stats, break_effect=actor.stats.break_effect + be_mult * 100),
        )

    new_bonus = dict(actor.stats.dmg_bonus)
    for k, v in bonus.items():
        if k == "all":
            new_bonus["all"] = new_bonus.get("all", 0.0) + v
        else:
            new_bonus[k] = new_bonus.get(k, 0.0) + v

    return replace(actor, stats=replace(actor.stats, dmg_bonus=new_bonus))


def _default_policy() -> Policy:
    """默认策略：能量满放终结技，否则战技，否则普攻."""
    from hsr_nous.sim_schema.policy import PolicyRule, TargetRule

    return Policy(
        name="default",
        action_rules=[
            PolicyRule(
                condition="energy >= ULT_THRESHOLD",
                action="ultimate",
                priority=100,
                description="能量满 → 终结技",
            ),
            PolicyRule(condition="true", action="skill", priority=50, description="否则战技"),
            PolicyRule(condition="true", action="basic", priority=0, description="否则普攻"),
        ],
        parameters={"ULT_THRESHOLD": 100},
        target_rules=[TargetRule(condition="true", selector="primary_target", priority=0)],
    )


def build_encounter(
    team: List[str],
    *,
    relic_set: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
    level: int = 80,
    max_av: int = 1500,
    lang: str = "en",
) -> Tuple[Encounter, Dict[str, List[Action]]]:
    """组装一个 sim_schema.Encounter.

    Args:
        team: 4 个角色名（如 ["Acheron", "Sparkle", "Ruan Mei", "Fu Xuan"]）
        relic_set: 遗器关键词（如 "雷4" / "量子4"）
        enemy_name: 敌人名（用于查 theBowja 数据，否则用预设）
        level: 队伍等级
        max_av: 最大行动值（终止条件）
        lang: 数据语言

    Returns:
        (Encounter, actions_by_actor)：Encounter + 该 encounter 中每个 character
        actor_id 对应的 Action 列表（给 CombatEngine 用）。
    """
    char_actors: List[Actor] = []
    actions_by_actor: Dict[str, List[Action]] = {}

    for name in team:
        actor = adapt_character_by_name(name, level=level, lang=lang)
        if actor is None:
            # 未找到：插入占位角色，避免 Engine 报错
            actor = Actor(actor_id=name, name=name, actor_type="character", level=level)
        actor = _apply_relic_bonus(actor, relic_set)

        # 解析技能列表 → Action 对象
        actions: List[Action] = []
        # 用角色的元素填 damage_type（适配 sim.resolver）
        char_element = ""
        if actor.stats.weakness:
            char_element = actor.stats.weakness[0].capitalize()
        for sid in actor.actions:
            action = adapt_skill_by_id(sid, lang=lang, character_element=char_element)
            if action is not None:
                actions.append(action)
        # 若该角色没有可用 Action，添加一个 dummy basic 防止 Engine 跳过
        if not actions:
            actions.append(
                Action(
                    action_id=f"dummy_basic_{actor.actor_id}",
                    name="普攻",
                    action_type="basic",
                    target_type="single",
                    scaling=[{"atk": 0.5}],
                    toughness_dmg=10,
                    skill_point_gain=1,
                )
            )
        actions_by_actor[actor.actor_id] = actions

        # 清空 actor.actions（sim_schema 用字符串 id 占位）
        char_actors.append(replace(actor, actions=[]))

    enemy_actor = _resolve_enemy(enemy_name)
    policy = _default_policy()

    enc = Encounter(
        encounter_id=f"enc_{team[0] if team else 'empty'}_{enemy_name}",
        name=f"{'+'.join(team)} vs {enemy_name}",
        actors=char_actors + [enemy_actor],
        policy=policy,
        termination=TerminationConfig(
            mode="fixed_av",
            max_action_value=max_av,
            max_turns=200,
        ),
    )
    return enc, actions_by_actor


def adapt_encounter(monster_data: Dict[str, Any]) -> Encounter:
    """兼容旧 API：仅根据敌人数据返回空 Encounter（保留向后兼容）.

    推荐使用 `build_encounter(...)` 一步到位。
    """
    return Encounter(
        encounter_id=str(monster_data.get("_id", monster_data.get("Id", ""))),
        name=monster_data.get("name", monster_data.get("Name", "")),
    )