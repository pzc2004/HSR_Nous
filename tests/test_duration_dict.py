"""duration dict 糖（04_modifier §4.14）落地测试：{value, tick_on} 解析 + 编译闸 + 引擎兜底.

- 编译闸：duration dict 未知键 / tick_on 词表外 / until 未落地——编译期炸指路
- 运行语义：tick_on "$modifier.source" → source_turn_end 锚——施加者回合结束走字，
  携带者回合不走字；duration 耗尽到期移除
- 引擎兜底：绕过编译层手写 dict 时同口径炸（不运行期 TypeError 裸炸）
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _actor(aid, spd):
    return Actor(actor_id=aid, name=aid, level=80,
                 stats=StatBlock(atk=1000, spd=spd, hp=3000, max_energy=100))


def _dummy():
    return Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=10, max_toughness=9999, weakness=["fire"]))


def _engine(max_av):
    """h1（spd 60，AV 166.7：@166.7/@333.3）为施加者，h2（spd 100，AV 100：@100/@200/@300）
    为携带者——速度错开无同值；木桩 spd 10 不干扰."""
    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
    enc = Encounter(encounter_id="t", name="t",
                    actors=[_actor("h1", 60), _actor("h2", 100), _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=max_av))
    eng = CombatEngine(enc, actions_by_actor={"h1": [basic], "h2": [basic]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


_SPEC = {
    "modifier_id": "SRC_BUFF", "name": "源锚", "modifier_type": "buff",
    "duration": {"value": 2, "tick_on": "$modifier.source"},
}


def _apply_source_mod(eng):
    """h1 施加 dict-duration modifier 到 h2 身上."""
    h1, h2 = eng.state.actors["h1"], eng.state.actors["h2"]
    assert eng._apply_modifier_spec(h2, dict(_SPEC), h1) is True
    return h2.modifiers["SRC_BUFF"]


class TestDurationDictCompileGates:
    def test_dict_form_accepted(self):
        """{value, tick_on} 是 §4.14 设计形态——编译通过，不再当未知写法."""
        BuildCompiler()._validate_modifier_spec(dict(_SPEC), "模板 X modifier")

    def test_scalar_duration_unchanged(self):
        BuildCompiler()._validate_modifier_spec(
            {"modifier_id": "M", "duration": 2}, "模板 X modifier")

    def test_unknown_key_rejected(self):
        bad = dict(_SPEC)
        bad["duration"] = {"value": 2, "tick_onn": "$modifier.source"}
        with pytest.raises(ValueError, match="未知键 'tick_onn'"):
            BuildCompiler()._validate_modifier_spec(bad, "模板 X modifier")

    def test_tick_on_vocab_rejected(self):
        bad = dict(_SPEC)
        bad["duration"] = {"value": 2, "tick_on": "$modifier.moon"}
        with pytest.raises(ValueError, match="tick_on 非法值"):
            BuildCompiler()._validate_modifier_spec(bad, "模板 X modifier")

    def test_until_rejected_as_unwired(self):
        bad = dict(_SPEC)
        bad["duration"] = {"until": "summon_turn_end"}
        with pytest.raises(ValueError, match="until 事件到期形态未落地"):
            BuildCompiler()._validate_modifier_spec(bad, "模板 X modifier")


class TestDurationDictEngineBackstop:
    def test_until_backstop(self):
        eng = _engine(100)
        with pytest.raises(ValueError, match="until 事件到期形态未落地"):
            eng._modifier_from_spec({"modifier_id": "M", "duration": {"until": "owner_down"}})

    def test_tick_on_backstop(self):
        eng = _engine(100)
        with pytest.raises(ValueError, match="tick_on 非法值"):
            eng._modifier_from_spec({"modifier_id": "M", "duration": {"value": 1, "tick_on": "x"}})

    def test_parse_to_anchor(self):
        mod = CombatEngine._modifier_from_spec(dict(_SPEC))
        assert mod.duration == 2
        assert mod.tick_anchor == "source_turn_end"


class TestSourceTurnEndAnchor:
    def test_materialize_and_source_recorded(self):
        """dict 形态物化 + 施加者记账（source_id 是 source 锚走字依据）."""
        eng = _engine(100)
        mod = _apply_source_mod(eng)
        assert mod.duration == 2 and mod.tick_anchor == "source_turn_end"
        assert mod.source_id == "h1"

    def test_ticks_on_source_turn_not_carrier(self):
        """携带者 h2 首动（@100）不走字；施加者 h1 首动（@166.7）结束走字 2→1；
        h2 第二动（@200）仍不走字."""
        eng = _engine(120)  # 仅 h2@100：纯携带者回合
        _apply_source_mod(eng)
        eng.run()
        assert eng.state.actors["h2"].modifiers["SRC_BUFF"].duration == 2, \
            "携带者回合结束不该触发 source 锚"

        eng = _engine(250)  # h2@100 → h1@166.7（走字）→ h2@200（不走字）
        _apply_source_mod(eng)
        eng.run()
        assert eng.state.actors["h2"].modifiers["SRC_BUFF"].duration == 1

    def test_expires_on_second_source_turn(self):
        """h1 第二动（@333.3）结束再走字 1→0 → 到期移除."""
        eng = _engine(400)
        _apply_source_mod(eng)
        eng.run()
        assert "SRC_BUFF" not in eng.state.actors["h2"].modifiers

    def test_int_duration_still_owner_anchor(self):
        """int 直给形态不受 dict 落地影响：仍按携带者回合结束锚走字."""
        eng = _engine(120)
        h2 = eng.state.actors["h2"]
        eng._apply_modifier(h2, Modifier(
            modifier_id="PLAIN", name="普通", modifier_type="buff", duration=1))
        eng.run()  # h2@100 回合结束 → 到期
        assert "PLAIN" not in h2.modifiers
