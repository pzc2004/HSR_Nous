"""目标代数 $self/$event 语境接线（2026-09-16）端到端：运行时注入 + 编译期对账闸.

模子同 P1a 批（tmp_path 微型模板）。$self=hook 持有者（与 hook condition 同口径）；
编译期错拼/越界字段即炸，不再放到运行期 ExpressionError。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

_A = """\
actor_id: "900501"
name: "持有测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
hooks:
  - event: "on_action"
    condition: "$event.actor == '900501' && $event.action_id == 't_basic'"
    effects:
      - effect_type: "apply_modifier"
        target: {pool: "allies", where: "$it.atk > $self.atk"}
        modifier:
          modifier_id: "T_GT"
          name: "比我攻高"
          modifier_type: "buff"
          duration: 0
          stat_effects: {"crit_rate": 0.1}
      - effect_type: "apply_modifier"
        target: {pool: "allies", where: "$it.actor_id == $self.actor_id"}
        modifier:
          modifier_id: "T_SELF"
          name: "正是我"
          modifier_type: "buff"
          duration: 0
          stat_effects: {"crit_rate": 0.2}
      - effect_type: "apply_modifier"
        target: {pool: "allies", where: "$it.actor_id == $event.actor"}
        modifier:
          modifier_id: "T_EVENT"
          name: "行动者"
          modifier_type: "buff"
          duration: 0
          stat_effects: {"crit_rate": 0.3}
"""

_B = """\
actor_id: "900502"
name: "高攻队友"
level: 80
base_stats: {atk: 1500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
"""

_BAD_SELF = """\
actor_id: "900503"
name: "坏 $self 测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
hooks:
  - event: "on_action"
    condition: "$event.actor == '900503'"
    effects:
      - effect_type: "apply_modifier"
        target: {pool: "allies", where: "$it.atk > $self.atkk"}
        modifier:
          modifier_id: "T_X"
          name: "x"
          modifier_type: "buff"
          duration: 0
"""

_BAD_EVENT = """\
actor_id: "900504"
name: "坏 $event 测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
hooks:
  - event: "on_action"
    condition: "$event.actor == '900504'"
    effects:
      - effect_type: "apply_modifier"
        target: {pool: "allies", where: "$it.actor_id == $event.crit"}
        modifier:
          modifier_id: "T_Y"
          name: "y"
          modifier_type: "buff"
          duration: 0
"""

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture()
def roots(tmp_path):
    d = tmp_path / "characters"
    d.mkdir()
    for fname, body in {
        "900501_持有者.yaml": _A, "900502_高攻.yaml": _B,
        "900503_坏self.yaml": _BAD_SELF, "900504_坏event.yaml": _BAD_EVENT,
    }.items():
        (d / fname).write_text(body, encoding="utf-8")
    return [str(tmp_path)]


def _build(*members):
    return {"build": {"team": [
        {"character_template": m, "level": 80} for m in members],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _cast_basic(eng, aid="900501"):
    st = eng.state.actors[aid]
    a = next(x for x in eng.actions_by_actor[aid] if x.action_id == "t_basic")
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": aid, "action_type": a.action_type, "action_id": a.action_id,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


class TestAlgebraSelfNs:
    def test_self_and_event_injection(self, roots):
        """where 三式全生效：$it.atk > $self.atk（比我攻高=队友）/
        $it.actor_id == $self.actor_id（正是我=持有者）/
        $it.actor_id == $event.actor（行动者=持有者）。"""
        c = compile_encounter(_build("900501", "900502"), _STAGE, template_roots=roots)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        _cast_basic(eng)
        st_a, st_b = eng.state.actors["900501"], eng.state.actors["900502"]
        assert "T_GT" in st_b.modifiers and "T_GT" not in st_a.modifiers, (
            "$self.atk=持有者 500：只有 1500 的队友命中")
        assert "T_SELF" in st_a.modifiers and "T_SELF" not in st_b.modifiers, (
            "$self.actor_id=持有者自身命中")
        assert "T_EVENT" in st_a.modifiers and "T_EVENT" not in st_b.modifiers, (
            "$event.actor=行动者命中")


class TestCompileGates:
    def test_bad_self_field_loud(self, roots):
        with pytest.raises(ValueError, match="atkk"):
            compile_encounter(_build("900503"), _STAGE, template_roots=roots)

    def test_bad_event_field_loud(self, roots):
        with pytest.raises(ValueError, match="crit"):
            compile_encounter(_build("900504"), _STAGE, template_roots=roots)
