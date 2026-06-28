"""角色适配器：将 raw_schema.Character 转换为 sim_schema.Actor.

提供两种使用方式：
1. `adapt_character(character, ...)` — 接收已加载的 raw_schema 对象
2. `adapt_character_by_name(name, level)` — 通过名字自动查找（pipeline.calc_character_stats）

通过 raw_schema + pipeline.calc_character_stats 输出真实 StatBlock。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from hsr_nous.raw_schema.character import Character
from hsr_nous.raw_schema.light_cone import LightCone
from hsr_nous.raw_schema.relic import Relic
from hsr_nous.sim_schema.actor import Actor, StatBlock


# 元素 ID → sim_schema 中使用的规范化名
_ELEMENT_TO_INTERNAL = {
    "Fire": "fire",
    "Ice": "ice",
    "Thunder": "thunder",
    "Wind": "wind",
    "Quantum": "quantum",
    "Imaginary": "imaginary",
    "Physical": "physical",
}


def _internal_element(raw: str) -> str:
    """把 StarRailRes 的元素英文 ID 转换为 sim_schema 内部名（小写）."""
    return _ELEMENT_TO_INTERNAL.get(raw, raw.lower())


def _empty_stats() -> StatBlock:
    return StatBlock()


def adapt_character(
    character: Character,
    light_cone: Optional[LightCone] = None,
    relics: Optional[list[Relic]] = None,
    level: int = 80,
) -> Actor:
    """把 raw_schema.Character 转换为 sim_schema.Actor.

    Args:
        character: 角色档案
        light_cone: 光锥（可选，目前仅占位）
        relics: 遗器列表（可选，目前仅占位）
        level: 目标等级

    Returns:
        Actor：默认属性 spd=100，其它属性为零。
        **注意**：此函数不会主动调用 pipeline.calc_character_stats；
        若要获得真实数值，请使用 `adapt_character_by_name`。
    """
    return Actor(
        actor_id=str(character.id),
        name=character.name,
        actor_type="character",
        level=level,
        stats=_empty_stats(),
    )


def adapt_character_by_name(
    name: str,
    *,
    level: int = 80,
    lang: str = "en",
) -> Optional[Actor]:
    """通过角色名自动查找 raw_schema 数据，调用 pipeline.calc_character_stats 输出真实属性.

    Args:
        name: 角色英文名/中文名（如 "Acheron" / "黄泉"）
        level: 目标等级（1-80）
        lang: 数据语言（"en" | "cn"）

    Returns:
        Actor：HP/ATK/DEF/SPD/CR/CD 为真实计算值，元素/弱点已填充。
        若角色名找不到，返回 None。
    """
    # 仅按 data_dir=None（默认走根目录 data/）调用 pipeline
    from hsr_nous.pipeline import get_character_by_name, calc_character_stats

    raw = get_character_by_name(name, lang=lang)
    if raw is None:
        return None

    char_id = raw.get("id", "")
    try:
        stats_dict = calc_character_stats(char_id, level=level, lang=lang)
    except (ValueError, KeyError):
        stats_dict = {}

    element = _internal_element(raw.get("element", ""))

    # 元数据：把元素存进 dmg_bonus / weakness（sim 公式需要）
    dmg_bonus: Dict[str, float] = {}
    if element:
        # 角色属性增伤默认为 0；这里只标记"该元素存在"
        dmg_bonus[element] = 0.0

    weakness = [element] if element else []

    stats = StatBlock(
        hp=stats_dict.get("hp", 0.0),
        atk=stats_dict.get("atk", 0.0),
        def_=stats_dict.get("def", 0.0),
        spd=stats_dict.get("spd", 100.0),
        crit_rate=stats_dict.get("crit_rate", 0.05),
        crit_dmg=stats_dict.get("crit_dmg", 0.50),
        dmg_bonus=dmg_bonus,
        weakness=weakness,
        max_energy=raw.get("max_sp", 120.0),
        energy=raw.get("max_sp", 120.0) * 0.5,  # 假设战开始时 50% 能量
    )

    return Actor(
        actor_id=str(char_id),
        name=raw.get("name", name),
        actor_type="character",
        level=level,
        stats=stats,
        actions=raw.get("skills", []),  # 字符串 ID 列表，sim_tools 会进一步解析
    )


def make_dummy_enemy(
    name: str = "DefaultEnemy",
    *,
    level: int = 80,
    element: str = "",
    hp: float = 100000.0,
    atk: float = 1000.0,
    def_: float = 800.0,
    toughness: float = 100.0,
    weaknesses: Optional[list[str]] = None,
    resistance: Optional[Dict[str, float]] = None,
) -> Actor:
    """构造一个仿真用的虚拟敌人 Actor.

    HSR 公开数据（theBowja）没有 HP/ATK/DEF，所以必须手动指定。
    阶段 5 接入 mihoyo API 后可从账号/榜单读取真实数值。
    """
    return Actor(
        actor_id=f"enemy_{name}",
        name=name,
        actor_type="monster",
        level=level,
        stats=StatBlock(
            hp=hp,
            atk=atk,
            def_=def_,
            spd=100.0,
            max_toughness=toughness,
            toughness=toughness,
            resistance=resistance or {},
            weakness=weaknesses or [],
        ),
    )