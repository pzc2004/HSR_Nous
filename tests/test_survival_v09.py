"""复活 / 锁血 / 月茧（v0.9，受击链末段四层分工）.

四层各就各位（engine._check_death docstring 为分工锚点）：
- 免死：before_take_damage waterfall cancel 伤害本身（test_death_immunity 已覆盖，此处只对轴分工）
- 锁血（modifier.hp_lock）：伤害照算，HP 钳 1
- 月茧（modifier.moon_cocoon + state.moon_cocoon_used）：留 1 血进月茧态；下次回合开始前
  受治疗/获盾解除，否则到期真死。次数语义（owner 实战确认 2026-08-22）：**全队每场共用 1 次**
  （战斗级状态）；同一伤害事件多人同时致死 → 一次全部进茧；茧中全队无次数，
  任何人（含茧中人）再受致命击 → 直接真死（无"延迟倒下"）
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


def _ally(actor_id: str = "h", name: str = "实验员"):
    return Actor(actor_id=actor_id, name=name, level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))


def _enemy():
    return Actor(actor_id="e", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=100000, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk():
    return Action(action_id="e_atk", name="灭世一击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _enemy_aoe():
    return Action(action_id="e_aoe", name="灭世狂澜", action_type="basic", target_type="aoe",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _engine():
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _engine_pair():
    """双队友夹具：h / h2 同嘲讽（期望模式敌方单体恒打存活列表首位）."""
    enc = Encounter(encounter_id="t", name="t",
                    actors=[_ally(), _ally("h2", "实验员乙"), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk(), _enemy_aoe()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hit(eng):
    eng._execute_action(eng.state.actors["e"], _enemy_atk())


def _grant(eng, actor_id: str = "h"):
    st = eng.state.actors[actor_id]
    eng._apply_modifier(st, Modifier(
        modifier_id="COCOON_GRANT", name="月茧之庇", modifier_type="buff",
        duration=0, dispellable=False, moon_cocoon=True))
    return st


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
    def test_enter_cocoon_consumes_team_charge(self):
        """进月茧：留 1 血 + 授予件消耗 + 全队次数消耗（战斗级状态，进 snapshot）."""
        eng = _engine()
        st = _grant(eng)
        _hit(eng)
        assert st.alive and math.isclose(st.current_hp, 1.0)
        assert MOON_COCOON_ID in st.modifiers
        assert "COCOON_GRANT" not in st.modifiers, "授予件已消耗"
        assert eng.state.moon_cocoon_used is True, "全队每场 1 次的次数已消耗（战斗级状态）"
        assert eng.state.snapshot()["moon_cocoon_used"] is True, "次数进 snapshot（B16 纯净不变量载体）"

    def test_cocooned_target_takes_lethal_dies(self):
        """茧中补刀真死：月茧期间全队无次数，茧中人再受致命击 → 直接真死（无延迟倒下）."""
        eng = _engine()
        st = _grant(eng)
        exits = []
        eng.bus.subscribe("actor_exit", lambda et, p, ctx: exits.append(dict(p)))
        _hit(eng)
        assert MOON_COCOON_ID in st.modifiers
        _hit(eng)  # 茧中第二击：不再保 1 血
        assert not st.alive
        assert any(p.get("reason") == "death" for p in exits)

    def test_cocoon_expires_at_owner_turn_start(self):
        """到期真死：月茧在下次回合开始前未受治疗/未获护盾 → 倒下."""
        eng = _engine()
        st = _grant(eng)
        exits = []
        eng.bus.subscribe("actor_exit", lambda et, p, ctx: exits.append(dict(p)))
        _hit(eng)
        assert MOON_COCOON_ID in st.modifiers
        eng._tick_modifiers(st, "owner_turn_start")
        assert not st.alive and math.isclose(st.current_hp, 0.0)
        assert any(p.get("reason") == "death" for p in exits)
        assert any("月茧到期" in l for l in eng.state.log)

    def test_cocoon_released_by_heal(self):
        """月茧中受治疗 → 解除存活（到期不再倒下）；次数不返还，再受致命击 → 真死."""
        eng = _engine()
        st = _grant(eng)
        _hit(eng)
        assert MOON_COCOON_ID in st.modifiers
        eng._run_hook_effect(st, {"effect_type": "heal_self", "ratio": 0.4}, {}, {})
        assert MOON_COCOON_ID not in st.modifiers
        assert math.isclose(st.current_hp, 1.0 + 1200.0), "茧中留 1 血，治疗 40% 上限叠加"
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.alive
        _hit(eng)  # 全队每场 1 次不返还：解除后再受致命击 → 真死
        assert not st.alive

    def test_cocoon_released_by_shield(self):
        """月茧中获得护盾 → 解除存活."""
        eng = _engine()
        st = _grant(eng)
        _hit(eng)
        eng._apply_modifier_spec(st, {"modifier_id": "SH_A", "name": "盾", "duration": 3,
                                      "shield": {"flat": 500.0}}, st)
        assert MOON_COCOON_ID not in st.modifiers
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.alive

    def test_simultaneous_aoe_deaths_all_enter_cocoon(self):
        """同时死亡多人一起救：一次 AoE 同时致死 2 人 → 这 1 次机会把 2 个全部送进月茧."""
        eng = _engine_pair()
        h1 = _grant(eng, "h")
        h2 = _grant(eng, "h2")
        eng._execute_action(eng.state.actors["e"], _enemy_aoe())
        assert h1.alive and math.isclose(h1.current_hp, 1.0) and MOON_COCOON_ID in h1.modifiers
        assert h2.alive and math.isclose(h2.current_hp, 1.0) and MOON_COCOON_ID in h2.modifiers
        assert eng.state.moon_cocoon_used is True
        # 茧中全队无次数：任一茧中人再受致命击 → 真死；另一人受治疗解除 → 存活
        _hit(eng)  # 期望模式敌方单体打存活首位 h1
        assert not h1.alive
        eng._run_hook_effect(h2, {"effect_type": "heal_self", "ratio": 0.4}, {}, {})
        assert MOON_COCOON_ID not in h2.modifiers
        eng._tick_modifiers(h2, "owner_turn_start")
        assert h2.alive

    def test_sequential_deaths_only_first_saved(self):
        """先后死只救第一个：首次致死用掉次数后，之后任何人受致命击 → 直接真死."""
        eng = _engine_pair()
        h1 = _grant(eng, "h")
        h2 = _grant(eng, "h2")
        _hit(eng)  # 第 1 击：h1 进茧，次数消耗
        assert h1.alive and MOON_COCOON_ID in h1.modifiers
        assert eng.state.moon_cocoon_used is True
        _hit(eng)  # 第 2 击：茧中 h1 补刀 → 真死
        assert not h1.alive
        _hit(eng)  # 第 3 击：h2 有授予件但全队次数已耗 → 真死，不进茧
        assert not h2.alive
        assert MOON_COCOON_ID not in h2.modifiers

    def test_cocoon_before_revive_priority(self):
        """优先级（owner 记忆确认 2026-08-22）：先消耗月茧，再消耗复活——
        带月茧授予件+复活件：第一击进茧（复活件不动）；茧中第二击落复活层回拉；
        且复活后月茧态已结束（否则下次回合开始会被到期误杀）."""
        eng = _engine()
        st = _grant(eng)
        eng._apply_modifier(st, Modifier(
            modifier_id="REV", name="复活", modifier_type="buff", duration=0,
            revive_percent=0.5, source_id="h"))
        _hit(eng)  # 第一击：先月茧——进茧，复活件原封不动
        assert st.alive and math.isclose(st.current_hp, 1.0)
        assert MOON_COCOON_ID in st.modifiers
        assert "REV" in st.modifiers, "先消耗月茧：复活件未被触碰"
        assert eng.state.moon_cocoon_used is True
        _hit(eng)  # 茧中第二击：次数已耗 → 落复活层 → 回拉 50%，月茧态随之结束
        assert st.alive and math.isclose(st.current_hp, 1500.0)
        assert "REV" not in st.modifiers, "复活件已消费"
        assert MOON_COCOON_ID not in st.modifiers, "复活接住时月茧态结束"
        eng._tick_modifiers(st, anchor="owner_turn_start")  # 到期不再误杀
        assert st.alive and math.isclose(st.current_hp, 1500.0)


class TestSetHpToPercent:
    def test_set_hp_hook_effect(self):
        """B9 原语：set_hp_to_percent 0.5 → HP=上限一半；0 → 致死走四层."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._run_hook_effect(st, {"effect_type": "set_hp_to_percent", "percent": 0.5}, {}, {})
        assert math.isclose(st.current_hp, 1500.0)
        eng._run_hook_effect(st, {"effect_type": "set_hp_to_percent", "percent": 0.0}, {}, {})
        assert not st.alive
