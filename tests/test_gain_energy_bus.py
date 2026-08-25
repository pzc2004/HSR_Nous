"""能量获得统一接线 on_gain_energy（mechanics 05 §5.1/§5.3 + §23.4 对账表）.

一切"获得能量"路径（行动回能 / 受击回能 / hook 原语 gain_energy——秘技装填预置同通道）
都经 on_gain_energy waterfall 发射；初始能量布场不是事件，不发射。
- 行动回能：普攻 20 / 战技 30 / 终结技 5，整动作一次（非逐段/逐目标）
- 载荷：actor（获得者）/ amount / source / action_id / reason / err_exempt
- waterfall 可改写 amount / cancel 取消；改写发生在 ERR 乘算之前
- err_exempt（§5.3 具名豁免）：照发事件，amount 不乘 ERR
- B16：同配置同种子两局逐字段全等
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _ally(aid="h", err=1.0, spd=100.0):
    return Actor(actor_id=aid, name=aid, level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=spd, max_energy=100,
                                 energy_regen=err, taunt=100, atk=1000))


def _enemy(aid="e", atk=1000.0, spd=50.0):
    return Actor(actor_id=aid, name=aid, actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=atk, spd=spd, max_toughness=9999,
                                 weakness=["fire"]))


def _basic(**kw):
    return Action(action_id="a_basic", name="普攻", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10, **kw)


def _skill(**kw):
    return Action(action_id="a_skill", name="战技", action_type="skill", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=20,
                  skill_point_cost=1, **kw)


def _ult(**kw):
    # 模板惯例：终结技显式 energy_gain: 5（mechanics 05 §5.1）
    return Action(action_id="a_ult", name="终结技", action_type="ultimate", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=30,
                  energy_cost=100, energy_gain=5, **kw)


def _engine(allies, actions_by_actor=None, enemies=None, mode=MODE_EXPECTED, seed=None,
            rotation=None, av=250.0):
    enc = Encounter(encounter_id="t", name="t",
                    actors=list(allies) + list(enemies if enemies is not None else [_enemy()]),
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor=actions_by_actor or {},
                       policy=ScriptedPolicy(rotation=rotation or ["basic"]), mode=mode, seed=seed,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _tap(eng):
    """被动观察 on_gain_energy（返回 None，不改写）."""
    seen = []
    eng.bus.subscribe_waterfall(
        "on_gain_energy", lambda et, p, ctx: (seen.append(dict(p)), None)[1])
    return seen


class TestActionGainEmits:
    @pytest.mark.parametrize("factory,action_type,expected", [
        (_basic, "basic", 20), (_skill, "skill", 30), (_ult, "ultimate", 5),
    ])
    def test_payload_and_amount(self, factory, action_type, expected):
        """普攻 20 / 战技 30 / 终结技 5：发事件且载荷正确，整动作一次."""
        eng = _engine([_ally()])
        seen = _tap(eng)
        action = factory()
        eng._execute_action(eng.state.actors["h"], action)
        gains = [p for p in seen if p["actor"] == "h"]
        assert len(gains) == 1, "整动作一次，不双发"
        p = gains[0]
        assert p["amount"] == expected and p["source"] == "h"
        assert p["action_id"] == action.action_id and p["reason"] == action_type
        assert p["err_exempt"] is False
        assert math.isclose(eng.state.actors["h"].current_energy, float(expected))

    def test_err_amplifies_action_gain(self):
        """行动回能吃 ERR（不在 §5.3 豁免清单）：ERR 1.2 → 战技 30×1.2=36."""
        eng = _engine([_ally(err=1.2)])
        eng._execute_action(eng.state.actors["h"], _skill())
        assert math.isclose(eng.state.actors["h"].current_energy, 36.0)


class TestWaterfallModify:
    def test_modify_amount_before_err(self):
        """waterfall 改写 amount 发生在 ERR 乘算前：20→50，再 ×1.2 = 60."""
        eng = _engine([_ally(err=1.2)])
        eng.bus.subscribe_waterfall(
            "on_gain_energy", lambda et, p, ctx: {"amount": 50})
        eng._execute_action(eng.state.actors["h"], _basic())
        assert math.isclose(eng.state.actors["h"].current_energy, 60.0)

    def test_cancel_blocks_gain(self):
        """waterfall cancel：行动回能被取消（能量不动）."""
        eng = _engine([_ally()])
        eng.bus.subscribe_waterfall(
            "on_gain_energy", lambda et, p, ctx: {"cancel": True})
        eng._execute_action(eng.state.actors["h"], _skill())
        assert math.isclose(eng.state.actors["h"].current_energy, 0.0)


class TestNoDoubleEmission:
    def test_multi_instance_single_emission(self):
        """多段行动（3 段）：回能整动作一次，事件只发一条，能量只加一次."""
        eng = _engine([_ally()])
        seen = _tap(eng)
        eng._execute_action(eng.state.actors["h"], _skill(instances=3))
        gains = [p for p in seen if p["actor"] == "h" and p["reason"] == "skill"]
        assert len(gains) == 1
        assert math.isclose(eng.state.actors["h"].current_energy, 30.0), "30 一次，非逐段 ×3"

    def test_multi_target_single_emission(self):
        """多目标行动（AOE 中 2 敌）：回能按行动者一次，不按目标数."""
        eng = _engine([_ally()], enemies=[_enemy("e1"), _enemy("e2")])
        seen = _tap(eng)
        aoe = Action(action_id="a_aoe", name="群攻", action_type="skill", target_type="aoe",
                     damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=20,
                     skill_point_cost=1)
        eng._execute_action(eng.state.actors["h"], aoe)
        gains = [p for p in seen if p["actor"] == "h" and p["reason"] == "skill"]
        assert len(gains) == 1
        assert math.isclose(eng.state.actors["h"].current_energy, 30.0)


class TestErrExempt:
    def test_hook_effect_exempt_emits_unamplified(self):
        """豁免回能（hook 原语 err_exempt）：照发事件，amount 不乘 ERR（25 非 30）."""
        eng = _engine([_ally(err=1.2)])
        seen = _tap(eng)
        st = eng.state.actors["h"]
        eng._run_hook_effect(st, {
            "effect_type": "gain_energy", "target": "self", "amount": 25,
            "err_exempt": True}, {})
        assert math.isclose(st.current_energy, 25.0), "豁免不乘 ERR"
        assert len(seen) == 1
        p = seen[0]
        assert p["actor"] == "h" and p["amount"] == 25 and p["source"] == "h"
        assert p["reason"] == "effect" and p["action_id"] is None
        assert p["err_exempt"] is True

    def test_hook_effect_default_amplified(self):
        """对照组：hook 原语默认（无 err_exempt）吃 ERR：25×1.2=30."""
        eng = _engine([_ally(err=1.2)])
        seen = _tap(eng)
        st = eng.state.actors["h"]
        eng._run_hook_effect(st, {
            "effect_type": "gain_energy", "target": "self", "amount": 25}, {})
        assert math.isclose(st.current_energy, 30.0)
        assert seen[0]["err_exempt"] is False


class TestGainEnergyB16:
    def test_same_seed_identical(self):
        """B16：同配置同种子两局逐字段全等（行动/受击/effect 三路径全在发事件）."""
        def build():
            ally_acts = [_basic(), _skill(), _ult()]
            enemy_act = Action(action_id="e_atk", name="爪击", action_type="basic",
                               target_type="single", damage_type="physical",
                               scaling=[{"atk": 1.0}], toughness_dmg=0, energy_grant=10)
            enc = Encounter(encounter_id="t", name="t", actors=[_ally(err=1.2), _enemy()],
                            termination=TerminationConfig(mode="fixed_av", max_action_value=450.0))
            eng = CombatEngine(enc, actions_by_actor={"h": ally_acts, "e": [enemy_act]},
                               policy=ScriptedPolicy(rotation=["skill", "basic"]),
                               mode=MODE_ROLL, seed=11, initial_sp=10, initial_energy_ratio=0.0)
            # hook 原语路径也在局内发一次（装填预置式；on_battle_start 在 setup 内发射，先订阅）
            eng.bus.subscribe("on_battle_start", lambda et, p, ctx: eng._run_hook_effect(
                eng.state.actors["h"],
                {"effect_type": "gain_energy", "target": "self", "amount": 10}, {}))
            eng.setup()
            return eng

        s1 = build().run().snapshot()
        s2 = build().run().snapshot()
        assert s1 == s2
        st = s1["actors"]["h"]
        assert st["current_energy"] > 0, "行动/受击/effect 回能确实发生"
