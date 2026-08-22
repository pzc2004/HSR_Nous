"""受击结算链闭环端到端（v0.9）：

我方带盾角色 + 敌方多段攻击 + 复活场景，一条完整受击链：
waterfall(before_take_damage) → 乘区 → 盾吸收（并行，破盾级联）→ 溢出扣血 →
死亡检查（锁血/复活）→ 受击回能 → after_being_hit（链尾，钩子读终态）。
另：B16 —— 同配置同种子两局逐字段全等。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

# 期望模式单段伤害：4000 ×0.5防 ×0.8抗 ×0.9未击破 ×1.025期望暴击 = 1476
SEG = 1476.0


def _ally():
    return Actor(actor_id="h", name="盾兵", level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))


def _enemy():
    return Actor(actor_id="e", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=4000, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _ally_skill():
    return Action(action_id="sh", name="加盾", action_type="skill", target_type="self",
                  skill_point_cost=1,
                  apply_modifiers=[{"modifier_id": "SH_A", "name": "护盾", "duration": 3,
                                    "stat_effects": {"taunt": 500.0},
                                    "shield": {"flat": 500.0}}])


def _enemy_atk():
    return Action(action_id="e_atk", name="三连击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0,
                  energy_grant=10, instances=3)


def _engine(mode=MODE_EXPECTED, seed=None):
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"h": [_ally_skill()], "e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=mode, seed=seed,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    # 复活件预置（生命上限 50% 回拉，消费型）
    eng._apply_modifier(eng.state.actors["h"], Modifier(
        modifier_id="REV", name="复活", modifier_type="buff", duration=0,
        revive_percent=0.5, source_id="h"))
    return eng


class TestHitChainEndToEnd:
    def test_full_chain_event_order(self):
        eng = _engine()
        stream = []
        for ev in ("shield_absorbed", "shield_broken", "on_revive", "after_being_hit"):
            eng.bus.subscribe(ev, lambda et, p, ctx: stream.append((et, dict(p))))
        eng.bus.subscribe_waterfall(
            "before_take_damage",
            lambda et, p, ctx: (stream.append((et, dict(p))), None)[1])
        eng.bus.subscribe_waterfall(
            "on_gain_energy",
            lambda et, p, ctx: (stream.append((et, dict(p))), None)[1])

        state = eng.run()
        st = state.actors["h"]

        # ---- 终态：盾破级联 + 复活回拉 + 三段受击回能 ----
        assert st.alive
        assert not st.shields and "SH_A" not in st.modifiers, "盾破后关联 modifier（含嘲讽提升）连带消失"
        assert "REV" not in st.modifiers, "复活件已消费"
        assert math.isclose(st.current_hp, 1500.0), "复活回拉至生命上限 50%"
        # T1/T2 两次战技各 +30（@100/@200 两动），受击 3 段 ×10 = +30
        assert math.isclose(st.current_energy, 90.0), "战技回能 60 + 受击回能 30（打盾段照回）"

        # ---- 链时序：三段逐段展开 ----
        # 前导 3 条是行动回能（本任务统一接线后 on_gain_energy 覆盖行动路径）：
        # h@AV100 战技、h@AV200 战技、e@AV200 普攻（敌人能量上限 0，事件照发、实得 0）
        seq = [et for et, _ in stream]
        assert seq == [
            "on_gain_energy", "on_gain_energy", "on_gain_energy",
            # 段 1：waterfall → 盾吸收（500）→ 破盾 → 回能 → after_being_hit
            "before_take_damage", "shield_absorbed", "shield_broken",
            "on_gain_energy", "after_being_hit",
            # 段 2：无盾 → 直接扣血 → 回能 → after_being_hit
            "before_take_damage", "on_gain_energy", "after_being_hit",
            # 段 3：致死 → 复活回拉 → 回能（存活）→ after_being_hit
            "before_take_damage", "on_revive", "on_gain_energy", "after_being_hit",
        ], f"受击链时序：{seq}"
        action_gains = [p for et, p in stream[:3] if et == "on_gain_energy"]
        assert [p["reason"] for p in action_gains] == ["skill", "skill", "basic"]
        assert [p["actor"] for p in action_gains] == ["h", "h", "e"]
        # 载荷抽查
        ab = next(p for et, p in stream if et == "shield_absorbed")
        assert math.isclose(ab["amount"], 500.0) and ab["target"] == "h"
        rev = next(p for et, p in stream if et == "on_revive")
        assert rev["percent"] == 0.5 and math.isclose(rev["hp"], 1500.0)
        hits = [p for et, p in stream if et == "after_being_hit"]
        assert [p["seg_index"] for p in hits] == [0, 1, 2]
        assert math.isclose(hits[0]["absorbed"], 500.0)
        assert math.isclose(hits[1]["absorbed"], 0.0)

    def test_b16_same_seed_identical(self):
        """B16：同配置同种子两局逐字段全等（受击链全件在位）."""
        s1 = _engine(mode=MODE_ROLL, seed=7).run().snapshot()
        s2 = _engine(mode=MODE_ROLL, seed=7).run().snapshot()
        assert s1 == s2
        st = s1["actors"]["h"]
        assert st["alive"] and st["current_hp"] > 0
