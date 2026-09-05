"""距离制调度模型专项：主状态=剩余距离（守恒）；变速时纹丝不动；拉条纯距离运算."""
from __future__ import annotations

import math

from hsr_nous.sim.scheduler import DISTANCE, EXTRA_COUNTDOWN, Scheduler
from hsr_nous.sim_schema.actor import Actor, StatBlock
from tests.scheduler_debug import current_av


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
        assert math.isclose(current_av(eng, eng.actor_of(h)), before / 200.0, rel_tol=1e-9)

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


class TestCountdownSpeedKey:
    """倒计时回合的速度键（白厄变身族 0.6×）：收尾与变速两处修复."""

    def test_countdown_exhausted_next_turn_uses_entity_speed(self):
        """倒计时耗尽收尾：先摘倒计时再挂键——下一动 eta = clock + 10000/实体速度."""
        sch = Scheduler([_actor("a", 100)])
        actor = sch.actor_of(sch.handle_of("a"))
        sch.grant_countdown("a", 2, spd=60.0)  # 实体 100，倒计时固定 60
        _, kind1, now1 = sch.next_actor()
        assert kind1 == EXTRA_COUNTDOWN
        assert math.isclose(now1, DISTANCE / 60.0, rel_tol=1e-9)
        _, kind2, now2 = sch.next_actor()  # 最后一倒计时回合弹出（耗尽点）
        assert kind2 == EXTRA_COUNTDOWN
        assert math.isclose(now2, 2 * DISTANCE / 60.0, rel_tol=1e-9)
        # 耗尽后下一动是普通回合，按实体速度 100（修复前错挂倒计时速度 60 → 晚 ~66.7AV）
        _, kind3, now3 = sch.next_actor()
        assert kind3 == "normal"
        assert math.isclose(now3, now2 + DISTANCE / 100.0, rel_tol=1e-9)
        assert math.isclose(current_av(sch, actor), DISTANCE / 100.0, rel_tol=1e-9)

    def test_speed_change_during_countdown_uses_countdown_speed(self):
        """倒计时中减速：键按倒计时速度算（倒计时速度固定，实体变速期间键不动）."""
        sch = Scheduler([_actor("a", 100)])
        actor = sch.actor_of(sch.handle_of("a"))
        sch.grant_countdown("a", 3, spd=60.0)
        sch.next_actor()  # 进入倒计时第 1 动，clock = 10000/60
        clock = sch.clock
        sch.on_speed_change(actor, 100.0, 30.0)  # 倒计时中实体被减速
        h = sch.handle_of("a")
        # _spd_now 已更新（出倒计时后按新速度 30），但当前键纹丝不动（倒计时速度固定）
        assert math.isclose(sch._spd_now[h], 30.0)
        assert math.isclose(current_av(sch, actor), DISTANCE / 60.0, rel_tol=1e-9)
        _, kind, now = sch.next_actor()
        assert kind == EXTRA_COUNTDOWN
        assert math.isclose(now, clock + DISTANCE / 60.0, rel_tol=1e-9)


class TestFormExitEta:
    """退大倒计时终点（form_exit_eta）：最后一次倒计时回合的预计时刻——
    行动条「退」标记的数据源；终点在倒计时推进中应保持不变（派生读数自洽）."""

    def test_no_countdown_returns_none(self):
        sch = Scheduler([_actor("a", 100)])
        assert sch.form_exit_eta("a") is None
        assert sch.form_exit_eta("ghost") is None

    def test_exit_eta_formula_and_invariance(self):
        """终点 = clock + remaining/spd + (left-1)×10000/spd，且不随倒计时推进漂移."""
        sch = Scheduler([_actor("a", 100)])
        sch.grant_countdown("a", 3, spd=60.0, initial_ratio=0.5)
        expected = 0.5 * DISTANCE / 60.0 + 2 * DISTANCE / 60.0
        assert math.isclose(sch.form_exit_eta("a"), expected, rel_tol=1e-9)
        sch.next_actor()  # 倒计时第 1 动：left 3→2，remaining 回满——终点不变
        assert math.isclose(sch.form_exit_eta("a"), expected, rel_tol=1e-9)
        sch.next_actor()  # 第 2 动：left 2→1——终点 = 下一动点（最后一击回合）
        assert math.isclose(sch.form_exit_eta("a"), expected, rel_tol=1e-9)
        assert math.isclose(sch.form_exit_eta("a"), sch.clock + DISTANCE / 60.0, rel_tol=1e-9)
        sch.next_actor()  # 第 3 动耗尽 → 无倒计时
        assert sch.form_exit_eta("a") is None


class TestUndoGaugeResetGuard:
    """undo_gauge_reset 归零护栏：cancel 恢复必须配 delay（推条）或 act_now 语义——
    hook 未推条时余量归零会同时刻无限重弹（撞 MAX_TURNS 截断毒数据）；
    归零兜底按"本次行动被消耗"重置满条."""

    def test_undo_after_delay_keeps_remainder(self):
        """正常路径（残梅绽族）：弹出重置 10000 → hook 推条 30% → undo 撤回重置 → 余量 3000."""
        sch = Scheduler([_actor("a", 100), _actor("e", 80)])
        e = sch.actor_of(sch.handle_of("e"))
        sch.delay_action(e, 0.3)  # hook 推条：10000 + 3000
        sch.undo_gauge_reset(e)   # 撤回弹出处重置：-10000 → 只留推条余量
        assert math.isclose(sch._remaining[sch.handle_of("e")], DISTANCE * 0.3, rel_tol=1e-9)

    def test_undo_without_delay_floors_to_full_gauge(self):
        """护栏：cancel 未配 delay → 不归零（避免同时刻重弹），按行动被消耗重置满条."""
        sch = Scheduler([_actor("a", 100), _actor("e", 80)])
        e = sch.actor_of(sch.handle_of("e"))
        sch.undo_gauge_reset(e)  # 10000 - 10000 → 护栏兜底回 10000
        h = sch.handle_of("e")
        assert math.isclose(sch._remaining[h], DISTANCE, rel_tol=1e-9), (
            f"未配 delay 的 cancel 不得归零（会同时刻无限重弹）：{sch._remaining[h]}"
        )
        assert current_av(sch, e) > 0, "下次弹出必须有时钟流逝（不同时刻重弹）"

    def test_cancel_recovery_without_delay_not_truncated(self):
        """引擎级回归：韧性恢复被 cancel 且 hook 无推条——旧实现同一时刻无限重弹
        直撞 MAX_TURNS（truncated 毒数据）；护栏后按行动被消耗跳过，局正常终止."""
        from hsr_nous.sim.engine import CombatEngine
        from hsr_nous.sim.pipeline import MODE_EXPECTED
        from hsr_nous.sim.policy_api import ScriptedPolicy
        from hsr_nous.sim_schema.action import Action
        from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

        hero = _actor("h", 100)
        dummy = Actor(actor_id="e", name="e", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["fire"]))
        basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=250))
        eng = CombatEngine(enc, actions_by_actor={"h": [basic]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        eng.state.actors["e"].broken = True
        # 恒 cancel 且无推条的退化 hook（cancel 恢复未配 delay 的最小复现）
        eng.bus.subscribe_waterfall("toughness_recovered", lambda et, p, ctx: {"cancel": True})
        state = eng.run()
        assert any("韧性恢复被阻止" in l for l in state.log)
        assert not any("[敌] e 行动" in l for l in state.log), "恢复恒被阻 → 敌不行动"
        assert state.truncated is False, \
            "护栏前：同时刻无限重弹撞 MAX_TURNS 截断；护栏后按行动被消耗满条重排"
