"""引擎 v0.1 golden case：手算对轴 + 两局全等（纯净不变量）.

golden 值全部手算（含迁移自 phase-1 的旧手算），v0.1 验收标准：
单角色白板打木桩，手算伤害对轴；同配置连跑两局，终局状态逐字段全等。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.scheduler import Scheduler
from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _make_actor(actor_id, name, spd, actor_type="character", **stats):
    return Actor(actor_id=actor_id, name=name, actor_type=actor_type,
                 stats=StatBlock(spd=spd, **stats))


# ---------------------------------------------------------------------------
# Scheduler（行动序：AV 规则对轴）
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_initial_av(self):
        """初始时刻 = 10000 / 速度."""
        a = _make_actor("1", "快", 160)
        sch = Scheduler([a])
        assert math.isclose(sch.preview()[0][1], 62.5)

    def test_faster_acts_first(self):
        slow = _make_actor("1", "慢", 100)
        fast = _make_actor("2", "快", 160)
        sch = Scheduler([slow, fast])
        actor, _, _ = sch.next_actor()
        assert actor.name == "快"

    def test_tie_break_by_order(self):
        a = _make_actor("1", "甲", 120)
        b = _make_actor("2", "乙", 120)
        sch = Scheduler([a, b])
        actor, _, _ = sch.next_actor()
        assert actor.name == "甲"

    def test_two_actions_in_150_av(self):
        """速度 134 在 150 AV 内两动（首轮两动阈值 133.3）."""
        a = _make_actor("1", "黄泉", 134)
        sch = Scheduler([a])
        count, _ = 0, None
        for _ in range(10):
            _, _, now = sch.next_actor()
            if now > 150:
                break
            count += 1
        assert count == 2  # 行动完成于 74.6 与 149.2，第 3 次在 223.8 超出

    def test_advance_full(self):
        """拉条 100% = 减一个完整行动值."""
        a = _make_actor("1", "x", 100)
        sch = Scheduler([a])
        sch.advance_action(a, 1.0)
        assert math.isclose(sch.preview()[0][1], 0.0)

    def test_advance_noop_at_zero(self):
        """AV=0 时拉条无效."""
        a = _make_actor("1", "x", 100)
        sch = Scheduler([a])
        sch.act_now(a)
        sch.advance_action(a, 0.5)
        assert math.isclose(sch.preview()[0][1], 0.0)

    def test_speed_change_scales_av(self):
        """速度变化：剩余 AV 等比缩放."""
        a = _make_actor("1", "x", 100)
        sch = Scheduler([a])
        sch.on_speed_change(a, old_spd=100, new_spd=200)
        assert math.isclose(sch.preview()[0][1], 50.0)


# ---------------------------------------------------------------------------
# Pipeline（伤害公式：手算对轴）
# ---------------------------------------------------------------------------

class TestPipeline:
    def test_basic_damage_hand_calc(self):
        """手算 1350：ATK2000 CR50% CD100% lvl80，100% 倍率雷，目标 lvl80 弱雷未击破.

        ability=2000, boost=1.0, def=0.5, res=1.0, baseUniv=0.9, vuln=1.0,
        critExpected=0.5×2+0.5=1.5 → 2000×0.5×0.9×1.5 = 1350
        """
        attacker = Actor(actor_id="atk", name="攻", level=80,
                         stats=StatBlock(atk=2000, crit_rate=0.5, crit_dmg=1.0))
        target = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                       stats=StatBlock(weakness=["thunder"]))
        action = Action(action_id="a1", name="普攻", action_type="basic",
                        target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
        r = SettlementPipeline(mode=MODE_EXPECTED).deal_damage(action, attacker, target)
        assert math.isclose(r.value, 1350.0, rel_tol=1e-6)
        assert r.node["defMulti"] == 0.5 and r.node["critMulti"] == 1.5

    def test_non_weakness_resistance(self):
        """非弱点 20% 基础抗性：1000×0.5×0.8×0.9 = 360."""
        attacker = Actor(actor_id="atk", name="攻", level=80,
                         stats=StatBlock(atk=1000, crit_rate=0.0, crit_dmg=0.5))
        target = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                       stats=StatBlock(weakness=["fire"]))
        action = Action(action_id="a1", name="普攻", action_type="basic",
                        target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
        r = SettlementPipeline(mode=MODE_EXPECTED).deal_damage(action, attacker, target)
        assert math.isclose(r.value, 360.0, rel_tol=1e-6)

    def test_broken_target_ratio(self):
        """已击破 / 未击破 = 1.0 / 0.9."""
        attacker = Actor(actor_id="atk", name="攻", level=80,
                         stats=StatBlock(atk=1000, crit_rate=0.0))
        target = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                       stats=StatBlock(weakness=["thunder"]))
        action = Action(action_id="a1", name="普攻", action_type="basic",
                        target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
        p = SettlementPipeline(mode=MODE_EXPECTED)
        normal = p.deal_damage(action, attacker, target, target_broken=False).value
        broken = p.deal_damage(action, attacker, target, target_broken=True).value
        assert math.isclose(broken / normal, 1.0 / 0.9, rel_tol=1e-6)

    def test_def_pen_increases_damage(self):
        target = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                       stats=StatBlock(weakness=["thunder"]))
        action = Action(action_id="a1", name="普攻", action_type="basic",
                        target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
        no_pen = Actor(actor_id="a", name="攻", level=80,
                       stats=StatBlock(atk=1000, crit_rate=0.0, crit_dmg=0.5))
        with_pen = Actor(actor_id="a", name="攻", level=80,
                         stats=StatBlock(atk=1000, crit_rate=0.0, crit_dmg=0.5, def_pen=0.5))
        p = SettlementPipeline(mode=MODE_EXPECTED)
        assert p.deal_damage(action, with_pen, target).value > p.deal_damage(action, no_pen, target).value


# ---------------------------------------------------------------------------
# EventBus（契约：waterfall 白名单 v0.1 = amount/cancel）
# ---------------------------------------------------------------------------

class TestBus:
    def test_waterfall_amount_rewrite(self):
        bus = EventBus()
        bus.subscribe_waterfall("before_take_damage",
                                lambda _e, p, _c: {"amount": p["amount"] * 0.5})
        out = bus.waterfall("before_take_damage", {"amount": 100})
        assert out["amount"] == 50

    def test_waterfall_whitelist_rejects_other_keys(self):
        bus = EventBus()
        bus.subscribe_waterfall("before_take_damage",
                                lambda _e, p, _c: {"damage_type": "fire"})
        with pytest.raises(ValueError):
            bus.waterfall("before_take_damage", {"amount": 100})

    def test_emit_cannot_be_modified(self):
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.waterfall("on_kill", {})

    def test_waterfall_event_cannot_emit(self):
        bus = EventBus()
        with pytest.raises(ValueError):
            bus.emit("before_take_damage", {})


# ---------------------------------------------------------------------------
# CombatEngine（直伤闭环 + 两局全等）
# ---------------------------------------------------------------------------

def _setup(mode=MODE_EXPECTED, seed=None):
    hero = Actor(actor_id="hero", name="黄泉", level=80,
                 stats=StatBlock(atk=3000, spd=134, crit_rate=0.5, crit_dmg=1.0,
                                 hp=1200, max_energy=110))
    enemy = Actor(actor_id="enemy", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1_000_000_000, spd=100, weakness=["thunder"]))
    basic = Action(action_id="hero_basic", name="普攻", action_type="basic",
                   target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
    enc = Encounter(encounter_id="test", name="单体假人", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=150))
    engine = CombatEngine(enc, actions_by_actor={"hero": [basic]},
                          policy=ScriptedPolicy(rotation=["basic"]),
                          mode=mode, seed=seed, initial_energy_ratio=0.0)
    return engine


class TestCombatEngine:
    def test_hand_calc_full_run(self):
        """整局手算对轴：134 速两动 × 每动 4050 = 8100 总伤.

        每动：ability=3000, boost=1.0, def=(800)/(800+800+? )
            敌 lvl80 无面板防御 → 200+10×80=1000 → 1000/(1000+1000)=0.5? 错——
            attacker_const = 80×10+200 = 1000，敌防 1000 → 1000/(1000+1000) = 0.5
        res=1.0（弱雷）, baseUniv=0.9, vuln=1.0, critExpected=0.5×2+0.5=1.5
        → 3000×1.0×0.5×1.0×0.9×1.5 = 2025？不对——3000×0.5=1500×0.9=1350×1.5=2025
        两动 × 2025 = 4050？再算：3000×0.5×0.9×1.5 = 2025。总伤 = 2×2025 = 4050。
        """
        engine = _setup()
        state = engine.run()
        hero_hits = [l for l in state.log if "黄泉" in l and "伤害" in l]
        assert len(hero_hits) == 2, f"134 速 150AV 应两动，日志：{hero_hits}"
        assert math.isclose(state.total_damage, 4050.0, rel_tol=1e-6), (
            f"手算 4050 vs 实际 {state.total_damage}"
        )

    def test_terminates_on_av(self):
        state = _setup().run()
        assert state.cycle_av <= 150 + 100

    @pytest.mark.parametrize("mode,seed", [(MODE_EXPECTED, None), (MODE_ROLL, 42), (MODE_ROLL, 7)])
    def test_purity_two_runs_identical(self, mode, seed):
        """纯净不变量：同配置+同模式+同种子，两局终局状态逐字段全等."""
        s1 = _setup(mode=mode, seed=seed).run().snapshot()
        s2 = _setup(mode=mode, seed=seed).run().snapshot()
        assert s1 == s2, "两局终局状态不全等（纯净不变量被破坏）"
