"""火种银行（#19 overflow_mode:bank 糖语义）端到端：溢出转移→银行满作废→变身结束返还.

140804：火种达 12 激活，上限后还可最多溢出 3 点，变身结束时基于溢出点数获得火种。
银行逻辑用代码 hook 表达（#19"主资源+银行资源+转移 hook+返还 hook"的展开式）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

SEED, BANK = "fire_seed", "fire_seed_bank"
THRESHOLD, BANK_MAX = 12.0, 3.0


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy():
    return Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _actions():
    return [
        Action(action_id="skill", name="黎明创世", action_type="skill", target_type="single",
               damage_type="physical", scaling=[{"atk": 1.5}], toughness_dmg=20,
               skill_point_cost=1, resource_gain={SEED: 2}),
        Action(action_id="khaslana_ult", name="永劫燔世", action_type="ultimate",
               target_type="single", ult_cost_resource=SEED, ult_cost_amount=12),
        Action(action_id="khaslana_basic", name="创生•血棘渡亡", action_type="basic",
               target_type="single", damage_type="physical", scaling=[{"atk": 3.0}],
               toughness_dmg=20, energy_gain=0),
    ]


def _bank_hooks(eng):
    """火种银行机制：溢出转移（满作废）+ 变身结束返还."""

    def on_gain(et, payload, ctx):
        if payload.get("resource_id") != SEED:
            return
        st = eng.state.actors["1408"]
        overflow = st.resources.get(SEED, 0.0) - THRESHOLD
        if overflow > 0:
            bank = st.resources.get(BANK, 0.0)
            moved = min(overflow, max(0.0, BANK_MAX - bank))  # 银行满二层溢出=作废
            st.resources[SEED] = THRESHOLD
            st.resources[BANK] = bank + moved

    def on_state_change(et, payload, ctx):
        if payload.get("actor") != "1408" or "from_state" not in payload:
            return
        st = eng.state.actors["1408"]
        st.resources[SEED] = st.resources.get(SEED, 0.0) + st.resources.get(BANK, 0.0)
        st.resources[BANK] = 0.0

    eng.bus.subscribe("on_resource_gain", on_gain)
    eng.bus.subscribe("on_state_change", on_state_change)


def _engine(av=600.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"1408": _actions()},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    eng.register_state_config("1408", StateConfig(
        state="khaslana",
        replaces_actions={"basic": "khaslana_basic"},
        locked_actions=["skill"],
        exit_conditions=[{"trigger": "on_action_count", "value": 1}],
    ), entry_action_id="khaslana_ult")
    _bank_hooks(eng)
    return eng


class TestFireSeedBank:
    def test_overflow_bank_and_refund(self):
        eng = _engine(av=150.0)
        st = eng.state.actors["1408"]
        st.resources[SEED] = 14.0  # 预置超阈：T1 战技 14+2=16 → 溢出 3 满，钳 12 → 变身
        state = eng.run()
        r = st.resources

        # 轨迹：14 →(战技+2)→ 16 → 银行移 3（满），火种钳 12
        #      → 变身扣 12 → 倒计时 1 动 → 退出 → 返还 3
        assert math.isclose(r[SEED], 3.0), f"变身结束应返还银行 3：{r}"
        assert math.isclose(r[BANK], 0.0), f"银行应已清空：{r}"
        # 变身确实发生（激活用的是阈值 12，不是上限 15）
        assert any("进入形态 khaslana" in l for l in state.log)

    def test_bank_overflow_discarded(self):
        """银行满后继续获得：二层溢出作废（#19 翻车点）."""
        eng = _engine(av=150.0)
        st = eng.state.actors["1408"]
        st.resources[SEED] = 14.5
        st.resources[BANK] = 2.5
        eng.run()
        # T1 战技：14.5+2=16.5 → 只移 0.5（银行满 3），其余作废
        # 变身扣 12 → 0；退出返还 3 → 3
        assert math.isclose(st.resources[SEED], 3.0)
