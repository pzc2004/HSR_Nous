"""死星天裁（140811）端到端：净化 + 毁伤驱动段数（每点 4 段，上限 26）+ 消耗≥4 额外均分.

lv10 口径：每段 45%、每毁伤 4 段、总倍率上限 1170%（=26 段）、消耗≥4 额外均分 450%。
数值口径：atk=2000 crit(0.5,1.0) 期望模式 def×res=0.5 未击破 ×0.9。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

RUIN = "ruin"


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid):
    return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _verdict():
    return Action(action_id="140811", name="支柱•死星天裁", action_type="skill",
                  target_type="bounce", damage_type="physical",
                  scaling=[{"atk": 0.45}], toughness_dmg=5, skill_point_cost=1,
                  instances_from_resource=RUIN, instances_per_point=4,
                  instances_cap=26, consume_all_resource=RUIN, cleanse_self=True)


def _extra():
    return Action(action_id="verdict_extra", name="死星天裁·额外", action_type="follow_up",
                  target_type="aoe", damage_type="physical",
                  scaling=[{"atk": 4.5}], split="even", energy_gain=0)


def _engine(av=70.0):
    dummies = [_dummy(f"e{i}") for i in (1, 2, 3)]
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon()] + dummies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"1408": [_verdict()]},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()

    # 140811"消耗≥4 毁伤额外均分"hook：负值资源事件判定
    def on_consume(et, payload, ctx):
        if payload.get("resource_id") != RUIN or payload.get("actor") != "1408":
            return
        if float(payload.get("amount", 0)) <= -4.0:
            eng.trigger_action(eng.state.actors["1408"], _extra(), tag="counter")

    eng.bus.subscribe("on_resource_gain", on_consume)
    return eng


class TestStarVerdict:
    def test_full_verdict_chain(self):
        eng = _engine()
        st = eng.state.actors["1408"]
        st.resources[RUIN] = 6.0
        # 预挂可驱散 debuff（净化验证）
        eng._apply_modifier(st, Modifier(
            modifier_id="BURN", name="灼烧", modifier_type="debuff",
            duration=2, dispellable=True))
        state = eng.run()

        # 1. 净化：debuff 已解除
        assert "BURN" not in st.modifiers, "净化应解除可驱散负面"
        # 2. 毁伤已消耗清零
        assert math.isclose(st.resources[RUIN], 0.0)
        # 3. 段数：min(6×4, 26)=24 段 bounce（期望模式全中首怪）
        #    每段 2000×0.45×1.5×0.5×0.9 = 607.5 ×24 = 14580
        # 4. 消耗≥4 额外均分：每怪 2000×(4.5/3)×1.5×0.5×0.9 = 2025
        per_seg = 2000 * 0.45 * 1.5 * 0.5 * 0.9
        per_extra = 2000 * 1.5 * 1.5 * 0.5 * 0.9
        expected_e1 = 24 * per_seg + per_extra   # 首怪吃全部 24 段 + 均分
        expected_e23 = per_extra                  # 其余怪只吃均分
        assert math.isclose(1e9 - state.actors["e1"].current_hp, expected_e1, rel_tol=1e-6), (
            f"首怪：手算 {expected_e1:.1f} vs 实际 {1e9 - state.actors['e1'].current_hp:.1f}"
        )
        assert math.isclose(1e9 - state.actors["e2"].current_hp, expected_e23, rel_tol=1e-6)
        assert math.isclose(1e9 - state.actors["e3"].current_hp, expected_e23, rel_tol=1e-6)
        # 5. 额外均分确实插入发动
        assert any("插入发动 死星天裁·额外" in l for l in state.log)

    def test_insufficient_ruin_no_extra(self):
        """毁伤 1（<4）：段数 4，不触发额外均分."""
        eng = _engine()
        st = eng.state.actors["1408"]
        st.resources[RUIN] = 1.0
        state = eng.run()
        assert not any("死星天裁·额外" in l for l in state.log)
        per_seg = 2000 * 0.45 * 1.5 * 0.5 * 0.9
        assert math.isclose(1e9 - state.actors["e1"].current_hp, 4 * per_seg, rel_tol=1e-6)
