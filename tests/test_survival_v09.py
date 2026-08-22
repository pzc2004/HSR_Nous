"""复活 / 锁血 / 月茧（v0.9，受击链末段四层分工）.

四层各就各位（engine._check_death docstring 为分工锚点）：
- 免死：before_take_damage waterfall cancel 伤害本身（test_death_immunity 已覆盖，此处只对轴分工）
- 锁血（modifier.hp_lock）：伤害照算，HP 钳 1
- 月茧（modifier.moon_cocoon）：留 1 血进月茧态；下次回合开始前受治疗/获盾解除，否则真死
- 复活（modifier.revive_percent）：HP 归零后消费复活件按百分比回拉（发 on_revive）
另：B9 原语 set_hp_to_percent（hook effect）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import MOON_COCOON_ID, CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _ally():
    return Actor(actor_id="h", name="实验员", level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))


def _enemy():
    return Actor(actor_id="e", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=100000, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk():
    return Action(action_id="e_atk", name="灭世一击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _engine():
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hit(eng):
    eng._execute_action(eng.state.actors["e"], _enemy_atk())


class TestHpLock:
    def test_lethal_hit_clamps_to_one(self):
        """锁血：致命伤害照算（有伤害日志），HP 留 1 不死."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        _hit(eng)
        assert st.alive and math.isclose(st.current_hp, 1.0)
        assert any("灭世一击" in l and "造成" in l for l in eng.state.log), \
            "锁血不取消伤害（与免死 cancel 的分工）"
        _hit(eng)  # 第二击仍钳 1
        assert st.alive and math.isclose(st.current_hp, 1.0)

    def test_lock_expires_then_dies(self):
        """锁血件被摘除后，致命击正常死亡."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        eng._remove_modifier(st, "LOCK", "expire")
        _hit(eng)
        assert not st.alive


class TestRevive:
    def test_revive_consumes_modifier_and_pulls_hp(self):
        """复活：HP 归零 → 消费复活件 → 按生命上限 50% 回拉 + on_revive 载荷."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="REV", name="复活", modifier_type="buff", duration=0,
            revive_percent=0.5, source_id="h"))
        events = []
        eng.bus.subscribe("on_revive", lambda et, p, ctx: events.append(dict(p)))
        _hit(eng)
        assert st.alive and math.isclose(st.current_hp, 1500.0)
        assert "REV" not in st.modifiers, "复活件已消费"
        assert events == [{"target": "h", "percent": 0.5, "hp": 1500.0, "source": "h"}]
        # 第二次致命击：无复活件 → 真死
        _hit(eng)
        assert not st.alive

    def test_no_revive_means_death(self):
        eng = _engine()
        st = eng.state.actors["h"]
        _hit(eng)
        assert not st.alive


class TestMoonCocoon:
    def _grant(self, eng):
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="COCOON_GRANT", name="月茧之庇", modifier_type="buff",
            duration=0, dispellable=False, moon_cocoon=True))
        return st

    def test_enter_cocoon_once_then_true_death(self):
        """进月茧：留 1 血 + 授予件消耗（每场 1 次）；月茧到期未解除 → 真死."""
        eng = _engine()
        st = self._grant(eng)
        exits = []
        eng.bus.subscribe("actor_exit", lambda et, p, ctx: exits.append(dict(p)))
        _hit(eng)
        assert st.alive and math.isclose(st.current_hp, 1.0)
        assert MOON_COCOON_ID in st.modifiers
        assert "COCOON_GRANT" not in st.modifiers, "授予件每场 1 次已消耗"
        # 月茧中再受致命击：不重复进茧（留 1 血等裁决）
        _hit(eng)
        assert st.alive and math.isclose(st.current_hp, 1.0)
        # 下次回合开始：未受治疗/未获护盾 → 到期倒下
        eng._tick_modifiers(st, "owner_turn_start")
        assert not st.alive
        assert any(p.get("reason") == "death" for p in exits)

    def test_cocoon_released_by_heal(self):
        """月茧中受治疗 → 解除存活（到期不再倒下）."""
        eng = _engine()
        st = self._grant(eng)
        _hit(eng)
        assert MOON_COCOON_ID in st.modifiers
        eng._run_hook_effect(st, {"effect_type": "heal_self", "ratio": 0.4}, {}, {})
        assert MOON_COCOON_ID not in st.modifiers
        assert math.isclose(st.current_hp, 1.0 + 1200.0), "茧中留 1 血，治疗 40% 上限叠加"
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.alive

    def test_cocoon_released_by_shield(self):
        """月茧中获得护盾 → 解除存活."""
        eng = _engine()
        st = self._grant(eng)
        _hit(eng)
        eng._apply_modifier_spec(st, {"modifier_id": "SH_A", "name": "盾", "duration": 3,
                                      "shield": {"flat": 500.0}}, st)
        assert MOON_COCOON_ID not in st.modifiers
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.alive


class TestSetHpToPercent:
    def test_set_hp_hook_effect(self):
        """B9 原语：set_hp_to_percent 0.5 → HP=上限一半；0 → 致死走四层."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._run_hook_effect(st, {"effect_type": "set_hp_to_percent", "percent": 0.5}, {}, {})
        assert math.isclose(st.current_hp, 1500.0)
        eng._run_hook_effect(st, {"effect_type": "set_hp_to_percent", "percent": 0.0}, {}, {})
        assert not st.alive
