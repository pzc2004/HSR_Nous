"""Phase 1 仿真测试：行动值系统 + 标准直伤公式 + 主循环.

所有期望值均为手算结果，确保公式实现正确。
"""

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.resolver import DamageResolver
from hsr_nous.sim.timeline import Timeline
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


# ---------------------------------------------------------------------------
# Timeline 测试
# ---------------------------------------------------------------------------

def _make_actor(actor_id, name, spd, actor_type="character", **stats):
    return Actor(
        actor_id=actor_id,
        name=name,
        actor_type=actor_type,
        stats=StatBlock(spd=spd, **stats),
    )


class TestTimeline:
    def test_initial_av(self):
        """初始行动值 = 10000 / 速度."""
        a = _make_actor("1", "快", spd=160)
        tl = Timeline([a])
        # 10000 / 160 = 62.5
        assert math.isclose(tl.entries[0].action_value, 62.5)

    def test_faster_acts_first(self):
        """速度高者先行动."""
        slow = _make_actor("1", "慢", spd=100)
        fast = _make_actor("2", "快", spd=160)
        tl = Timeline([slow, fast])
        actor, _ = tl.next_actor()
        assert actor.name == "快"

    def test_tie_break_by_order(self):
        """速度相同按队伍编排顺序."""
        a = _make_actor("1", "甲", spd=120)
        b = _make_actor("2", "乙", spd=120)
        tl = Timeline([a, b])
        actor, _ = tl.next_actor()
        assert actor.name == "甲"

    def test_action_count_in_cycle(self):
        """速度 134 在 150 AV 内应能行动两次（首轮两动阈值 133.3）."""
        a = _make_actor("1", "黄泉", spd=134)
        tl = Timeline([a])
        count = 0
        # 统计完整落在 150 AV 预算内的行动次数 = floor(150 / 74.6) = 2
        for _ in range(10):
            tl.next_actor()
            if tl.total_elapsed_av > 150:
                break
            count += 1
        # 行动完成于 AV 74.6 与 149.2（均 ≤150），第 3 次在 223.8 超出
        assert count == 2

    def test_advance_action(self):
        """拉条 100% 应减去一个完整行动值."""
        a = _make_actor("1", "x", spd=100)  # AV=100
        tl = Timeline([a])
        tl.advance_action(a, 1.0)
        assert math.isclose(tl.entries[0].action_value, 0.0)

    def test_speed_change_scales_av(self):
        """速度变化按比例调整当前行动值."""
        a = _make_actor("1", "x", spd=100)  # AV=100
        tl = Timeline([a])
        tl.on_speed_change(a, old_spd=100, new_spd=200)
        # 100 × 100/200 = 50
        assert math.isclose(tl.entries[0].action_value, 50.0)


# ---------------------------------------------------------------------------
# DamageResolver 测试
# ---------------------------------------------------------------------------

class TestDamageResolver:
    def test_basic_damage_hand_calc(self):
        """手算验证标准直伤公式.

        攻击者：ATK=2000，暴击率50%，暴击伤害100%，等级80
        技能：100% ATK 倍率，雷属性
        目标：等级80，弱点雷（抗性0%），未击破

        abilityMulti = 1.0 × 2000 = 2000
        dmgBoostMulti = 1.0（无增伤）
        defMulti = (80×10+200) / (敌防 + 1000) = 1000 / (1000+1000) = 0.5
            敌防 = 200 + 10×80 = 1000
        resMulti = 1 - 0 = 1.0（弱点）
        baseUniversalMulti = 0.9（未击破）
        vulnMulti = 1.0
        critExpected = 0.5×(1+1.0) + 0.5 = 1.5

        伤害 = 2000 × 1.0 × 0.5 × 1.0 × 0.9 × 1.0 × 1.5 = 1350
        """
        attacker = Actor(
            actor_id="atk", name="攻", level=80,
            stats=StatBlock(atk=2000, crit_rate=0.5, crit_dmg=1.0),
        )
        target = Actor(
            actor_id="tgt", name="敌", actor_type="monster", level=80,
            stats=StatBlock(weakness=["thunder"]),
        )
        action = Action(
            action_id="a1", name="普攻", action_type="basic",
            target_type="single", damage_type="thunder",
            scaling=[{"atk": 1.0}],
        )
        result = DamageResolver().resolve(action, attacker, target)
        assert math.isclose(result.damage, 1350.0, rel_tol=1e-6)

    def test_non_weakness_resistance(self):
        """非弱点属性承受 20% 基础抗性."""
        attacker = Actor(
            actor_id="atk", name="攻", level=80,
            stats=StatBlock(atk=1000, crit_rate=0.0, crit_dmg=0.5),
        )
        target = Actor(
            actor_id="tgt", name="敌", actor_type="monster", level=80,
            stats=StatBlock(weakness=["fire"]),  # 攻击雷，非弱点
        )
        action = Action(
            action_id="a1", name="普攻", action_type="basic",
            target_type="single", damage_type="thunder",
            scaling=[{"atk": 1.0}],
        )
        result = DamageResolver().resolve(action, attacker, target)
        # abilityMulti=1000, def=0.5, res=1-0.2=0.8, baseUniv=0.9, crit=1.0(CR=0)
        # 1000 × 0.5 × 0.8 × 0.9 = 360
        assert math.isclose(result.damage, 360.0, rel_tol=1e-6)

    def test_broken_target_no_reduction(self):
        """已击破目标无 10% 韧性减伤."""
        attacker = Actor(
            actor_id="atk", name="攻", level=80,
            stats=StatBlock(atk=1000, crit_rate=0.0, crit_dmg=0.5),
        )
        target = Actor(
            actor_id="tgt", name="敌", actor_type="monster", level=80,
            stats=StatBlock(weakness=["thunder"]),
        )
        action = Action(
            action_id="a1", name="普攻", action_type="basic",
            target_type="single", damage_type="thunder",
            scaling=[{"atk": 1.0}],
        )
        normal = DamageResolver().resolve(action, attacker, target, target_broken=False)
        broken = DamageResolver().resolve(action, attacker, target, target_broken=True)
        # broken / normal = 1.0 / 0.9
        assert math.isclose(broken.damage / normal.damage, 1.0 / 0.9, rel_tol=1e-6)

    def test_def_pen_increases_damage(self):
        """减防/无视防御提高伤害."""
        base_stats = dict(atk=1000, crit_rate=0.0, crit_dmg=0.5)
        target = Actor(
            actor_id="tgt", name="敌", actor_type="monster", level=80,
            stats=StatBlock(weakness=["thunder"]),
        )
        action = Action(
            action_id="a1", name="普攻", action_type="basic",
            target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}],
        )
        no_pen = Actor(actor_id="a", name="攻", level=80, stats=StatBlock(**base_stats))
        with_pen = Actor(actor_id="a", name="攻", level=80, stats=StatBlock(def_pen=0.5, **base_stats))
        d1 = DamageResolver().resolve(action, no_pen, target).damage
        d2 = DamageResolver().resolve(action, with_pen, target).damage
        assert d2 > d1


# ---------------------------------------------------------------------------
# CombatEngine 主循环测试
# ---------------------------------------------------------------------------

class TestCombatEngine:
    def _setup(self):
        hero = Actor(
            actor_id="hero", name="黄泉", level=80,
            stats=StatBlock(atk=3000, spd=134, crit_rate=0.5, crit_dmg=1.0, hp=1200),
        )
        enemy = Actor(
            actor_id="enemy", name="假人", actor_type="monster", level=80,
            stats=StatBlock(hp=1_000_000_000, spd=100, weakness=["thunder"]),
        )
        basic = Action(
            action_id="hero_basic", name="普攻", action_type="basic",
            target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}],
        )
        enc = Encounter(
            encounter_id="test", name="单体假人",
            actors=[hero, enemy],
            termination=TerminationConfig(mode="fixed_av", max_action_value=150),
        )
        return enc, {"hero": [basic]}

    def test_engine_deals_damage(self):
        """引擎应正确累计伤害."""
        enc, actions = self._setup()
        engine = CombatEngine(enc, actions_by_actor=actions)
        state = engine.run()
        assert state.total_damage > 0
        assert state.damage_by_actor["hero"] > 0

    def test_engine_action_count(self):
        """150 AV 内速度 134 的角色应行动 2 次."""
        enc, actions = self._setup()
        engine = CombatEngine(enc, actions_by_actor=actions)
        state = engine.run()
        hero_actions = [h for h in state.action_history if "黄泉" in h and "伤害" in h]
        assert len(hero_actions) == 2

    def test_engine_terminates_on_av(self):
        """fixed_av 模式应在达到 AV 上限后停止."""
        enc, actions = self._setup()
        engine = CombatEngine(enc, actions_by_actor=actions)
        state = engine.run()
        assert state.total_av <= 150 + 100  # 不会无限循环
