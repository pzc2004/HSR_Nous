"""距离制调度模型专项：主状态=剩余距离（守恒）；变速时纹丝不动；拉条纯距离运算."""
from __future__ import annotations

import math

from hsr_nous.sim.scheduler import DISTANCE, Scheduler
from hsr_nous.sim_schema.actor import Actor, StatBlock


def _actor(aid, spd):
    return Actor(actor_id=aid, name=aid, level=80,
                 stats=StatBlock(atk=1000, spd=spd, hp=3000, max_energy=100))


class TestDistanceModel:
    def test_speed_change_leaves_remaining_untouched(self):
        """变速：remaining 主状态纹丝不动（只有派生键重算）."""
        eng = Scheduler([_actor("a", 100), _actor("e", 80)])
        h = eng.handle_of("a")
        before = eng._remaining[h]
        eng.on_speed_change(eng.actor_of(h), 100.0, 200.0)
        assert math.isclose(eng._remaining[h], before), "变速不应改写剩余距离"
        # 派生键按新速重算（剩余 AV 减半）
        assert math.isclose(eng.current_av(eng.actor_of(h)), before / 200.0, rel_tol=1e-9)

    def test_advance_is_pure_distance_subtraction(self):
        """拉条 = remaining -= 10000×pct（纯距离，与速度无关）."""
        eng = Scheduler([_actor("a", 100), _actor("e", 80)])
        h = eng.handle_of("a")
        eng.advance_action(eng.actor_of(h), 0.3)
        assert math.isclose(eng._remaining[h], DISTANCE * 0.7, rel_tol=1e-9), (
            f"拉条 30% 应扣 3000 距离：{eng._remaining[h]}"
        )

    def test_advance_100pct_not_zero_when_pushed_beyond_base(self):
        """被推条超过基础距离后，100% 拉条不归零（KQM 通式/饮月实测语义）."""
        eng = Scheduler([_actor("a", 100), _actor("e", 80)])
        h = eng.handle_of("a")
        eng.delay_action(eng.actor_of(h), 1.0)   # 推到 20000（超过基础 10000）
        eng.advance_action(eng.actor_of(h), 1.0)  # 拉 100%：扣 10000 → 剩 10000，不归零
        assert math.isclose(eng._remaining[h], DISTANCE, rel_tol=1e-9), (
            f"超基础值时 100% 拉条应剩 {DISTANCE}：{eng._remaining[h]}"
        )

    def test_advance_noop_at_zero_remaining(self):
        """剩余距离 ≤ 0 时拉条无效."""
        eng = Scheduler([_actor("a", 100), _actor("e", 80)])
        h = eng.handle_of("a")
        eng.act_now(eng.actor_of(h))
        assert math.isclose(eng._remaining[h], 0.0)
        eng.advance_action(eng.actor_of(h), 0.5)
        assert math.isclose(eng._remaining[h], 0.0), "剩余为 0 时拉条应无效"


class TestSpeedBuffWiring:
    def test_speed_buff_actually_changes_action_order(self):
        """速度 buff（modifier）挂上后，行动序真实改变（接线验证，历史死代码修复）."""
        from hsr_nous.sim.engine import CombatEngine
        from hsr_nous.sim.pipeline import MODE_EXPECTED
        from hsr_nous.sim.policy_api import ScriptedPolicy
        from hsr_nous.sim.state import Modifier
        from hsr_nous.sim_schema.action import Action
        from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

        hero = _actor("h", 100)
        dummy = Actor(actor_id="e", name="e", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["fire"]))
        basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=400))
        eng = CombatEngine(enc, actions_by_actor={"h": [basic]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        eng._apply_modifier(eng.state.actors["h"], Modifier(
            modifier_id="SPD_UP", name="加速", modifier_type="buff", duration=0,
            stat_effects={"spd_pct": 0.5}))  # 100 → 150
        state = eng.run()
        hero_acts = [l for l in state.log if "h 对" in l and "普攻" in l]
        avs = [float(l.split(":")[0].replace("AV", "")) for l in hero_acts]
        # buff 在 setup 后即挂 → 全部行动按 150 速（66.7 间隔）；接线死时会是 100 间隔
        assert len(avs) >= 3 and all(
            math.isclose(avs[i + 1] - avs[i], 10000 / 150, rel_tol=0.01) for i in range(len(avs) - 1)
        ), f"挂速 buff 后应全程按 150 速（66.7 间隔）：{avs}"

        # 对照组：无 buff 按面板 100 速（100 间隔）
        enc2 = Encounter(encounter_id="t2", name="t2", actors=[_actor("h", 100), dummy],
                         termination=TerminationConfig(mode="fixed_av", max_action_value=400))
        eng2 = CombatEngine(enc2, actions_by_actor={"h": [basic]},
                            policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                            initial_sp=10, initial_energy_ratio=0.0)
        eng2.setup()
        state2 = eng2.run()
        avs2 = [float(l.split(":")[0].replace("AV", ""))
                for l in state2.log if "h 对" in l and "普攻" in l]
        assert all(math.isclose(avs2[i + 1] - avs2[i], 100.0, abs_tol=0.5)
                   for i in range(len(avs2) - 1)), f"无 buff 应按 100 速：{avs2}"
