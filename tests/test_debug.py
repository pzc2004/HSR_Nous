"""DebugController 调试控制器：单步/断点/检视/快照 + step/run 等价性."""

from hsr_nous.sim import CombatEngine, DebugController, ScriptedPolicy, MODE_EXPECTED
from hsr_nous.sim_schema import Action, Actor, Encounter, StatBlock, TerminationConfig


def _build_engine(seed=42):
    hero = Actor(actor_id="hero", name="黄泉", level=80,
                 stats=StatBlock(atk=3000, spd=134, crit_rate=0.5, crit_dmg=1.0,
                                 hp=1200, max_energy=110))
    enemy = Actor(actor_id="enemy", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1_000_000_000, spd=100, weakness=["thunder"]))
    basic = Action(action_id="hero_basic", name="普攻", action_type="basic",
                   target_type="single", damage_type="thunder", scaling=[{"atk": 1.0}])
    enc = Encounter(encounter_id="test", name="单体假人", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=150))
    return CombatEngine(enc, actions_by_actor={"hero": [basic]},
                        policy=ScriptedPolicy(rotation=["basic"]),
                        mode=MODE_EXPECTED, seed=seed, initial_energy_ratio=0.0)


def _run_out(debug: DebugController) -> None:
    while not debug.step_turn()["done"]:
        pass


class TestStepRunEquivalence:
    def test_stepped_run_equals_full_run(self):
        """步进到底 vs run() 到底：终态快照逐字段全等（step 拆分的正确性铁证）."""
        debug = DebugController(_build_engine())
        _run_out(debug)
        final = _build_engine().run()
        assert debug.state.snapshot() == final.snapshot()

    def test_logs_streamed_without_loss(self):
        """步进时增量日志拼接 == 全量日志（调试器不漏行）."""
        debug = DebugController(_build_engine())
        streamed = []
        while True:
            rec = debug.step_turn()
            streamed.extend(rec["logs"])
            if rec["done"]:
                break
        assert streamed == debug.state.log


class TestBreakpoints:
    def test_break_on_turn(self):
        debug = DebugController(_build_engine())
        debug.break_on_turn(2)  # 此 fixture 全局约 3 动（150 AV 截断），断点必须够得着
        rec = debug.continue_()
        assert not rec["done"] and rec["turn_count"] == 2

    def test_break_on_actor(self):
        debug = DebugController(_build_engine())
        debug.break_on_actor("enemy")
        rec = debug.continue_()
        assert not rec["done"] and rec["actor_id"] == "enemy"

    def test_clear_breaks_runs_to_end(self):
        debug = DebugController(_build_engine())
        debug.break_on_turn(2)
        debug.continue_()
        debug.clear_breaks()
        rec = debug.continue_()
        assert rec["done"]


class TestInspection:
    def test_action_bar_order_and_readonly(self):
        debug = DebugController(_build_engine())
        bar1, bar2 = debug.action_bar(), debug.action_bar()
        assert bar1 == bar2  # 只读：两次预览一致（不推进任何状态）
        assert bar1[0]["actor_id"] == "hero"  # 134 速先于 100 速
        assert bar1[0]["eta"] <= bar1[1]["eta"]

    def test_inspect_and_snapshot_shape(self):
        debug = DebugController(_build_engine())
        debug.step_turn()
        hero = debug.inspect("hero")
        assert hero["actor_id"] == "hero" and "current_hp" in hero
        full = debug.snapshot()
        assert set(full["actors"]) == {"hero", "enemy"}
        assert full["turn_count"] == 1

    def test_field_overview(self):
        debug = DebugController(_build_engine())
        debug.step_turn()
        field = debug.field()
        assert field["turn_count"] == 1
        assert field["actors"]["enemy"]["alive"] is True


class TestManualMode:
    def test_action_hook_drives_decisions(self):
        seen = []

        def hook(legal):
            seen.append([a.action_id for a in legal])
            return legal[0]

        debug = DebugController(_build_engine())
        debug.set_action_hook(hook)
        rec = debug.continue_()
        assert rec["done"]
        assert seen  # 决策点确实上交了回调

    def test_from_compiled_manual_flag(self):
        """manual=True 时编译策略 runtime 退场、policy 被接管."""
        engine = _build_engine()
        debug = DebugController(engine)
        debug.set_action_hook(lambda legal: None)  # 放弃选择 → 默认轮转
        rec = debug.continue_()
        assert rec["done"]


# ---------------------------------------------------------------------------
# 回退（稀疏检查点 + 段内重放）
# ---------------------------------------------------------------------------

class TestRewind:
    def test_back_then_rerun_equals_original(self):
        """回退到第 1 动后原样重跑到底：终态与不回退的局逐字段全等（重放精确性铁证）."""
        debug = DebugController(_build_engine(), checkpoint_interval=2)
        debug.continue_()  # 跑完
        final_snapshot = debug.snapshot()
        debug.back(debug.state.turn_count - 1)  # 回到第 1 动
        assert debug.state.turn_count == 1
        debug.continue_()  # 原样重跑（自动段确定性一致）
        assert debug.snapshot() == final_snapshot

    def test_goto_forward_and_backward(self):
        debug = DebugController(_build_engine(), checkpoint_interval=1)
        debug.goto_turn(2)
        assert debug.state.turn_count == 2
        debug.goto_turn(1)
        assert debug.state.turn_count == 1
        snap_at_1 = debug.snapshot()
        debug.goto_turn(2)
        assert debug.state.turn_count == 2
        debug.goto_turn(1)
        assert debug.snapshot() == snap_at_1  # 同一检查点恢复，逐位全等

    def test_rewind_disabled(self):
        debug = DebugController(_build_engine(), enable_rewind=False)
        debug.continue_()
        import pytest
        with pytest.raises(RuntimeError, match="回放未启用"):
            debug.back(1)

    def test_decision_log_records_manual_choices(self):
        debug = DebugController(_build_engine())
        debug.set_action_hook(lambda legal: legal[0])
        debug.continue_()
        assert debug.decisions  # 每次手动选择都进了决策簿（可落盘最小轨迹）
        assert all(isinstance(v, str) for v in debug.decisions.values())

    def test_manual_decisions_replayed_from_log(self):
        """回退的重放段由决策簿供给选择（不再问用户）；重走到底与原局逐位全等."""
        calls = []

        def hook(legal):
            calls.append(1)
            return legal[0]

        debug = DebugController(_build_engine(), checkpoint_interval=5)
        debug.set_action_hook(hook)
        debug.goto_turn(3)
        snap_at_3 = debug.snapshot()
        assert debug.decisions  # 手动选择已入簿
        before = len(calls)
        debug.back(2)  # 回到 turn 1：检查点恢复 + 重放（决策簿供 turn 0 的选择）
        assert len(calls) == before, "重放段不应再问用户"
        debug.goto_turn(3)  # 重走：turn 2 的决策已截断会再问，选择相同 → 终态全等
        assert debug.snapshot() == snap_at_3

    def test_trace_grows_and_truncates(self):
        debug = DebugController(_build_engine(), checkpoint_interval=1)
        debug.goto_turn(2)
        n2 = len(debug.trace)
        assert n2 >= 2
        debug.goto_turn(1)
        assert all(e["turn_count"] <= 1 for e in debug.trace)  # 旧未来已截断
