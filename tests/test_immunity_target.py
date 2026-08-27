"""补 1+2：debuff_immune 免疫控制 + on_become_target（140804 获火种/队友暴伤）."""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier, StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=582, spd=94, hp=3000, max_energy=100))


def _ally():
    return Actor(actor_id="ally", name="队友", level=80,
                 stats=StatBlock(atk=2000, spd=120, hp=3000, max_energy=100))


def _monster():
    return Actor(actor_id="e1", name="怪", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=100, spd=100, max_toughness=9999, weakness=["physical"]))


class TestDebuffImmune:
    def test_control_immunity_in_state(self):
        """形态内（grants_immune=[control]）：freeze 硬拒；普通 debuff 照挂；退出后可挂."""
        enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _monster()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=50))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED)
        eng.setup()
        st = eng.state.actors["1408"]
        eng.enter_state(st, StateConfig(state="khaslana", grants_immune=["control"]))

        freeze = Modifier(modifier_id="FRZ", name="冻结", modifier_type="debuff",
                          duration=1, control_kind="freeze")
        assert eng._apply_modifier(st, freeze) is False, "形态内控制应被硬拒"
        assert "FRZ" not in st.modifiers

        shred = Modifier(modifier_id="DEF0", name="减防", modifier_type="debuff", duration=1)
        assert eng._apply_modifier(st, shred) is True, "非控制 debuff 不受影响"

        eng.exit_state(st)
        assert eng._apply_modifier(st, freeze) is True, "退出形态后免疫失效"


class TestBecomeTarget:
    def test_seed_gain_and_ally_critdmg(self):
        """140804：成为技能目标获 1 火种；施放者为队友时另加暴伤（lv10 30%，3 回合）."""
        buff = Action(action_id="cheer", name="鼓舞", action_type="skill", target_type="ally_single",
                  skill_point_cost=1)
        bite = Action(action_id="bite", name="撕咬", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 0.1}], toughness_dmg=0)
        from hsr_nous.sim.compile.compiled import CompiledPolicy, CompiledPolicyRule
        from hsr_nous.sim.engine import CompiledPolicyRuntime
        enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _ally(), _monster()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=130))
        eng = CombatEngine(enc, actions_by_actor={"ally": [buff], "e1": [bite]},
                           policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                           initial_sp=10)
        # 队友 buff 目标选攻击最低者（白厄 582 < 队友 2000）
        eng.decision = CompiledPolicyRuntime(CompiledPolicy(
            name="t", action_rules=(),
            target_rules=(CompiledPolicyRule(action="skill", priority=0, selector="lowest_atk"),),
            parameters={}))
        eng.setup()

        seeds = {"n": 0.0}
        crit = {"applied": False}

        def hook(et, payload, ctx):
            if payload.get("target") != "1408":
                return
            st = eng.state.actors["1408"]
            seeds["n"] += 1.0
            src = payload.get("source", "")
            if src and src != "1408" and not src.startswith("e"):
                eng._apply_modifier(st, Modifier(
                    modifier_id="TALENT_CD", name="此身为炬", modifier_type="buff",
                    duration=3, stat_effects={"crit_dmg": 0.30}))
                crit["applied"] = True

        eng.bus.subscribe("on_become_target", hook)
        eng.run()

        # 队友 buff 选中白厄（atk 582 最低）+ 怪攻击 —— 至少 2 次成为目标
        assert seeds["n"] >= 2.0, f"成为目标次数不足：{seeds}"
        assert crit["applied"] is True
        assert "TALENT_CD" in eng.state.actors["1408"].modifiers
