"""legal 为空（全部行动被锁）回合语义：空过≠蒸发——回合末结算照走.

修复前 `_run_turn` 在 legal 为空时 return，跳过阶段 4：modifier 不 tick、
on_turn_end 不发、turn_count 不增——回合静默蒸发、永续 modifier 白赚。
"""
from __future__ import annotations

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(max_av):
    """唯一行动是 1 费战技 + initial_sp=0 → legal 恒为空；木桩 spd 10 不干扰."""
    hero = Actor(actor_id="h", name="测试员", level=80,
                 stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100))
    dummy = Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=10, max_toughness=9999, weakness=["fire"]))
    skill = Action(action_id="s", name="战技", action_type="skill", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0,
                   skill_point_cost=1)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=max_av))
    eng = CombatEngine(enc, actions_by_actor={"h": [skill]},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                       initial_sp=0, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestEmptyLegalTurn:
    def test_turn_end_settlement_still_runs(self):
        """空过回合：modifier 照 tick、on_turn_end 照发、turn_count 照增."""
        eng = _engine(150)  # 恰好 1 个空过回合（h@100；木桩@1000 超出截断）
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="B", name="计时", modifier_type="buff", duration=2))
        turn_ends = []
        eng.bus.subscribe("on_turn_end", lambda _et, p, _s: turn_ends.append(p["actor"]))
        state = eng.run()
        assert st.modifiers["B"].duration == 1, "空过回合 modifier 必须照走字"
        assert turn_ends == ["h"], "空过回合 on_turn_end 必须照发"
        assert state.turn_count == 1, "空过回合 turn_count 必须照增"
        assert any("无可用行动" in line for line in state.log)

    def test_modifier_expires_across_empty_turns(self):
        """连续空过：duration 2 经两个空过回合到期移除（修复前永续白赚）."""
        eng = _engine(250)  # h@100、h@200 两个空过回合
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="B", name="计时", modifier_type="buff", duration=2))
        state = eng.run()
        assert "B" not in st.modifiers, "两个空过回合后 duration 2 应到期"
        assert state.turn_count == 2
