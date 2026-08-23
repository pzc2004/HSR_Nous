"""忘却之庭轮次系统（v1.1，mechanics 03 §3.1 + 15 章模式表）.

规则（owner 实战确认 2026-08-24）：
- 轮次 = 全局时钟纯函数：预算满（首轮 150/后续 100）进下一轮，与速度/推拉条无关
- 忘却之庭转波次：轮次计数不变、预算重置 150、全体行动值重置——倒计时实体除外（跨波续跑）
- 其他模式：转波次不重置，新怪在当前时刻进场
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Cycle, Encounter, TerminationConfig


def _ally(actor_id: str = "h", name: str = "实验员"):
    return Actor(actor_id=actor_id, name=name, level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))


def _enemy(actor_id: str = "e", name: str = "小怪"):
    return Actor(actor_id=actor_id, name=name, actor_type="monster", level=80,
                 stats=StatBlock(hp=100, atk=10, spd=50, max_toughness=30,
                                 weakness=["fire"]))


def _cycle(**kw) -> Cycle:
    kw.setdefault("first_cycle_av", 150)
    kw.setdefault("subsequent_cycle_av", 100)
    return Cycle(**kw)


def _engine(cycle=None, waves=None, seed=None):
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy("e1")],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=10000),
                    cycle=cycle)
    eng = CombatEngine(enc, policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_ROLL,
                       seed=seed, initial_sp=10, initial_energy_ratio=0.0,
                       wave_enemies=waves or {})
    eng.setup()
    return eng


class TestCycleTick:
    def test_budget_tick_advances_cycle(self):
        """预算满进下一轮：150 → 轮 2，250 → 轮 3（时钟纯函数，手动推进即触发）."""
        eng = _engine(cycle=_cycle())
        st = eng.state
        st.clock = 149.9
        eng._tick_cycle()
        assert st.cycle_index == 1
        st.clock = 150.0
        eng._tick_cycle()
        assert st.cycle_index == 2
        assert math.isclose(st.cycle_end_clock, 250.0)
        st.clock = 260.0
        eng._tick_cycle()
        assert st.cycle_index == 3
        assert math.isclose(st.cycle_end_clock, 350.0)

    def test_cycle_events_payload(self):
        """on_cycle_end / on_cycle_start 发射，载荷带轮次与预算."""
        eng = _engine(cycle=_cycle())
        events = []
        eng.bus.subscribe("on_cycle_start", lambda et, p, ctx: events.append(dict(p)))
        eng.state.clock = 150.0
        eng._tick_cycle()
        assert events == [{"cycle_index": 2, "budget": 100.0}]

    def test_no_cycle_config_no_tick(self):
        """encounter.cycle=None：tick 静默跳过，轮次恒 1."""
        eng = _engine(cycle=None)
        eng.state.clock = 500.0
        eng._tick_cycle()
        assert eng.state.cycle_index == 1


class TestWaveReset:
    def _trigger_transition(self, eng):
        eng.state.actors["e1"].alive = False
        eng._advance_wave_if_needed()

    def test_forgotten_hall_reset(self):
        """忘却之庭（reset_on_wave）：全体剩余距离重置 10000、预算重置 150、轮次计数不变."""
        wave2 = [_enemy("e2", "二波怪")]
        eng = _engine(cycle=_cycle(reset_on_wave=True), waves={1: wave2})
        sch = eng.scheduler
        h = sch.handle_of("h")
        sch._remaining[h] = 1234.0  # 哨兵：已跑了一段的距离
        eng.state.clock = 100.0
        eng.state.cycle_index = 3
        eng.state.cycle_end_clock = 130.0
        self._trigger_transition(eng)
        assert math.isclose(sch._remaining[h], 10000.0), "行动值整体重置"
        assert math.isclose(eng.state.cycle_end_clock, 250.0), "预算重置为首轮 150"
        assert eng.state.cycle_index == 3, "轮次数不重置（mechanics 03 §3.1）"

    def test_countdown_excluded(self):
        """倒计时实体除外：countdown 中的 handle 原距离续跑，其他人重置."""
        wave2 = [_enemy("e2", "二波怪")]
        eng = _engine(cycle=_cycle(reset_on_wave=True), waves={1: wave2})
        sch = eng.scheduler
        sch.grant_countdown("h", 3, 60.0)
        h_cd = sch.handle_of("h")
        sch._remaining[h_cd] = 1234.0
        self._trigger_transition(eng)
        assert math.isclose(sch._remaining[h_cd], 1234.0), "倒计时跨波按原行动值续跑"
        e2 = sch.handle_of("e2")
        assert math.isclose(sch._remaining[e2], 10000.0), "新怪照常满条进场"

    def test_other_mode_no_reset(self):
        """非 reset 模式：不重置距离与预算，新怪直接进场."""
        wave2 = [_enemy("e2", "二波怪")]
        eng = _engine(cycle=_cycle(reset_on_wave=False), waves={1: wave2})
        sch = eng.scheduler
        h = sch.handle_of("h")
        sch._remaining[h] = 1234.0
        eng.state.cycle_end_clock = 130.0
        self._trigger_transition(eng)
        assert math.isclose(sch._remaining[h], 1234.0), "其他模式行动条不动"
        assert math.isclose(eng.state.cycle_end_clock, 130.0), "预算不刷新"


class TestCycleTermination:
    def test_max_cycles_truncates(self):
        """cycle.max_cycles=1：进入轮 2 即截断."""
        eng = _engine(cycle=_cycle(max_cycles=1))
        eng.state.clock = 150.0
        eng._tick_cycle()
        assert eng.state.cycle_index == 2
        assert eng._should_terminate() is True

    def test_cycles_used_in_snapshot(self):
        """cycles_used 进 snapshot（轮次评分基础）."""
        eng = _engine(cycle=_cycle())
        eng.state.clock = 150.0
        eng._tick_cycle()
        snap = eng.state.snapshot()
        assert snap["cycles_used"] == 2 and snap["cycle_index"] == 2

    def test_b16_same_seed_identical(self):
        """B16：带轮次配置的完整对局，同种子两局 snapshot 逐字段全等."""
        def _snap():
            return _engine(cycle=_cycle(reset_on_wave=True), seed=7).run().snapshot()
        assert _snap() == _snap()
