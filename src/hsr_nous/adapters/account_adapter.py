"""账号适配器：将 OwnedCharacter 转成 sim_schema.Actor.

仅依赖 raw_schema + sim_schema + 自身 account/ 模块（不依赖 pipeline）。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from hsr_nous.account.models import OwnedCharacter
from hsr_nous.sim_schema.actor import Actor, StatBlock


def adapt_owned_character(oc: OwnedCharacter, *, level: Optional[int] = None) -> Optional[Actor]:
    """把 OwnedCharacter 转为 Actor：若账号未提供基础属性，回退用 pipeline.calc_character_stats."""
    if level is None:
        level = max(oc.level, 1)

    try:
        # pipeline 仅做"找不到属性时回退到标准值"
        from hsr_nous.pipeline import calc_character_stats

        try:
            stats_dict = calc_character_stats(oc.character_id, level=level, lang="en")
        except Exception:
            stats_dict = {}

        # 注：曾带 energy=120.0×0.5 死键——StatBlock 无 energy 字段，该 kwarg 使整个构造
        # TypeError 落 except（stats 永远退回默认白板）；初始能量由引擎 spawn 按
        # rulebook constants.initial_energy_ratio 布场（同源唯一路径），此处不重复声明
        stats = StatBlock(
            hp=stats_dict.get("hp", 1000.0),
            atk=stats_dict.get("atk", 500.0),
            def_=stats_dict.get("def", 400.0),
            spd=stats_dict.get("spd", 100.0),
            crit_rate=stats_dict.get("crit_rate", 0.05),
            crit_dmg=stats_dict.get("crit_dmg", 0.50),
            max_energy=120.0,
        )
    except Exception:
        # 完全没有数据：返回最简 Actor
        stats = StatBlock()

    return Actor(
        actor_id=oc.character_id,
        name=oc.name or oc.character_id,
        actor_type="character",
        level=level,
        stats=stats,
        actions=[],
    )