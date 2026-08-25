"""v0.7C 多段伤害测试：instances 逐段结算 / 弹射 bounce / 段间死亡鞭尸.

数值口径同 v0.7A：atk=2000 crit(0.5,1.0) 期望模式单发倍率 1.0 = 1350，0.5 段倍率 = 675。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid, hp=1e9, max_toughness=100):
    return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=hp, spd=100, max_toughness=max_toughness, weakness=["fire"]))


def _engine(actions, enemies, mode=MODE_EXPECTED, seed=None, av=70.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"atk": actions},
                       policy=ScriptedPolicy(rotation=["skill"]), mode=mode, seed=seed,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _multihit(**kw):
    base = dict(action_id="s", name="连击", action_type="skill", target_type="single",
                damage_type="fire", scaling=[{"atk": 0.5}], toughness_dmg=10,
                skill_point_cost=1, instances=3)
    base.update(kw)
    return Action(**base)


class TestInstances:
    def test_three_segments_damage_and_toughness(self):
        """3 段 × 0.5 倍率 = 1.5 倍总伤；削韧按段累加 10×3=30."""
        state = _engine([_multihit()], [_dummy("e1")]).run()
        assert math.isclose(state.total_damage, 3 * 675.0, rel_tol=1e-6)
        assert math.isclose(state.actors["e1"].toughness, 100 - 30.0)

    def test_single_segment_default_unchanged(self):
        """instances=1 行为与多段前一致."""
        one = _multihit(instances=1)
        state = _engine([one], [_dummy("e1")]).run()
        assert math.isclose(state.total_damage, 675.0, rel_tol=1e-6)
        assert math.isclose(state.actors["e1"].toughness, 90.0)

    def test_overkill_latter_segments_lost(self):
        """段间击杀：第 1 段打死目标后，后 2 段落空（鞭尸损失）."""
        state = _engine([_multihit()], [_dummy("e1", hp=600.0)]).run()
        assert math.isclose(state.total_damage, 675.0, rel_tol=1e-6)
        assert not state.actors["e1"].alive


class TestBounce:
    def test_bounce_expected_mode_hits_primary(self):
        """期望模式弹射全中主目标（与 optimizer 单体口径一致）."""
        bounce = _multihit(target_type="bounce")
        state = _engine([bounce], [_dummy("e1"), _dummy("e2"), _dummy("e3")]).run()
        assert math.isclose(state.total_damage, 3 * 675.0, rel_tol=1e-6)
        assert math.isclose(state.actors["e1"].current_hp, 1e9 - 3 * 675.0, rel_tol=1e-9)
        assert math.isclose(state.actors["e2"].current_hp, 1e9)

    def test_bounce_roll_mode_total_conserved(self):
        """掷骰模式弹射：目标随机、暴击真掷，同 seed 逐字段复现（B16）."""
        bounce = _multihit(target_type="bounce")
        enemies = [_dummy("e1"), _dummy("e2"), _dummy("e3")]
        s1 = _engine([bounce], enemies, mode=MODE_ROLL, seed=42).run()
        s2 = _engine([bounce], [_dummy("e1"), _dummy("e2"), _dummy("e3")],
                     mode=MODE_ROLL, seed=42).run()
        # 每段 450（不暴）或 900（暴）：总伤必为 450 的倍数且在三段区间内
        assert 3 * 450.0 <= s1.total_damage <= 3 * 900.0
        assert math.isclose(s1.total_damage % 450.0, 0.0, abs_tol=1e-6)
        assert math.isclose(s1.total_damage, s2.total_damage, rel_tol=1e-9)
        assert s1.log == s2.log  # 同 seed 日志逐行全等
        # 逐段事件发射了 3 次（段数触发型机制的计数基础）
        assert sum(1 for l in s1.log if "连击" in l) == 3

    def test_bounce_redirects_after_kill(self):
        """弹射段间击杀：后续段重选到存活目标，不落空."""
        bounce = _multihit(target_type="bounce")
        enemies = [_dummy("e1", hp=600.0), _dummy("e2")]
        state = _engine([bounce], enemies, mode=MODE_EXPECTED).run()
        # 期望模式第 1 段中 e1（致死），后 2 段重选——e1 已死，候选只剩 e2
        assert not state.actors["e1"].alive
        assert state.actors["e2"].current_hp < 1e9
        assert math.isclose(state.total_damage, 3 * 675.0, rel_tol=1e-6)
