"""账号适配器：将 OwnedCharacter 转成 sim_schema.Actor.

仅依赖 raw_schema + sim_schema + 自身 account/ 模块（不依赖 pipeline）。
"""
from __future__ import annotations

from typing import Optional

from hsr_nous.account.models import OwnedCharacter
from hsr_nous.sim_schema.actor import Actor, StatBlock


def adapt_owned_character(oc: OwnedCharacter, *, level: Optional[int] = None) -> Optional[Actor]:
    """把 OwnedCharacter 转为 Actor；查无官方数据返回 None.

    命名两态纪律：查不到数据时**不**造"听起来像真的"兜底面板（旧版 hp=1000/atk=500/
    def=400/max_energy=120 硬编码系编造值，已清除）——调用方按 None 跳过该角色。
    """
    if level is None:
        level = max(oc.level, 1)

    # pipeline 提供官方面板；查不到（角色不存在/数据缺失）→ None，不脑补
    from hsr_nous.pipeline import calc_character_stats, get_character

    try:
        stats_dict = calc_character_stats(oc.character_id, level=level, lang="en")
    except Exception:
        return None
    raw = get_character(oc.character_id, lang="en") or {}

    # 注：曾带 energy=120.0×0.5 死键——StatBlock 无 energy 字段，该 kwarg 使整个构造
    # TypeError 落 except（stats 永远退回默认白板）；初始能量由引擎 spawn 按
    # rulebook constants.initial_energy_ratio 布场（同源唯一路径），此处不重复声明
    stats = StatBlock(
        hp=stats_dict["hp"],
        atk=stats_dict["atk"],
        def_=stats_dict["def"],
        spd=stats_dict["spd"],
        crit_rate=stats_dict["crit_rate"],
        crit_dmg=stats_dict["crit_dmg"],
        max_energy=float(raw.get("max_sp") or 0.0),
    )

    return Actor(
        actor_id=oc.character_id,
        name=oc.name or oc.character_id,
        actor_type="character",
        level=level,
        stats=stats,
        actions=[],
    )
