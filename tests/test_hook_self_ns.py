"""_HookSelfNS 惰性面板：不读面板键零 effective_stats 调用；读 max_hp 口径正确（effective）.

审计实测急切求值 54% 浪费且利用率 0——构造即算 effective_stats 的版本已回退为按需惰性。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine, _HookSelfNS
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine() -> CombatEngine:
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(hp=5000, atk=2000, spd=200, max_energy=100))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={"hero": [basic]},
                       policy=ScriptedPolicy(), mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _counting_pipeline(eng: CombatEngine):
    """插桩：包一层 effective_stats 计数（引擎内部调用先发生的不计——先装好再操作）."""
    calls = {"n": 0}
    orig = eng.pipeline.effective_stats

    def counting(st):
        calls["n"] += 1
        return orig(st)

    eng.pipeline.effective_stats = counting  # type: ignore[method-assign]
    return calls


class TestHookSelfNSLazy:
    def test_basic_fields_zero_effective_stats(self):
        """构造 + 读基础字段（hp/energy/state）：零 effective_stats 调用."""
        eng = _engine()
        st = eng.state.actors["hero"]
        calls = _counting_pipeline(eng)
        ns = _HookSelfNS(eng, st)
        assert ns.hp == st.current_hp and ns.energy == st.current_energy and ns.state == ""
        assert calls["n"] == 0

    def test_hook_condition_without_panel_keys_zero_effective_stats(self):
        """e2e 钉：不读面板键的 hook 条件（$self.energy 族）全程零 effective_stats 调用."""
        eng = _engine()
        st = eng.state.actors["hero"]
        calls = _counting_pipeline(eng)
        ctx = eng._hook_ctx(st, {})
        cond = eng._expr.compile("$self.energy >= 0 && $self.hp > 0", layer="effect")
        assert eng._expr.evaluate(cond, ctx) is True
        assert calls["n"] == 0

    def test_max_hp_effective_caliber_and_cached(self):
        """读 max_hp：effective 口径（吃 hp_pct）；面板键共享同一次求值缓存."""
        eng = _engine()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="HP_UP", name="生命提升", modifier_type="buff", duration=0,
            stat_effects={"hp_pct": 0.5}))
        calls = _counting_pipeline(eng)
        ns = _HookSelfNS(eng, st)
        assert math.isclose(ns.max_hp, 7500.0, rel_tol=1e-9), "effective 口径（5000×1.5）"
        assert calls["n"] == 1
        assert ns.atk == 2000.0, "面板键同一份缓存，不二次求值"
        assert calls["n"] == 1

    def test_unknown_panel_key_raises_attribute_error(self):
        ns = _HookSelfNS(_engine(), _engine().state.actors["hero"])
        try:
            _ = ns.no_such_stat
        except AttributeError:
            pass
        else:
            raise AssertionError("未知面板键应 AttributeError")
