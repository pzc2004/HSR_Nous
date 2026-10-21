"""固定随机序列与严格行动/目标脚本的端到端回归。"""
from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.montecarlo import RunRecorder
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.scripted import ScriptedRandom, run_scripted
from hsr_nous.sim_schema.action import Action
from tests._worldline_builders import make_acheron_worldline_parts


def _build(policy, *, enemy_hp=1e9, second_enemy_hp=None, enemy_spd=130.0,
           enemy_atk=0.0, hero_hp=3000.0, hero_spd=134.0, av=80.0,
           termination="fixed_av"):
    enemies = [{"actor_id": "e1", "name": "假人甲", "hp": enemy_hp,
                "atk": enemy_atk, "spd": enemy_spd, "max_toughness": 9999,
                "weakness": ["physical"]}]
    if second_enemy_hp is not None:
        enemies.append({"actor_id": "e2", "name": "假人乙", "hp": second_enemy_hp,
                        "atk": enemy_atk, "spd": enemy_spd, "max_toughness": 9999,
                        "weakness": ["physical"]})
    return ({"build": {"team": [{
        "character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
        "base_stats": {"atk": 1000, "spd": hero_spd, "hp": hero_hp, "max_energy": 100},
        "actions": [
            {"action_id": "b", "name": "普攻", "action_type": "basic", "target_type": "single",
             "damage_type": "physical", "scaling": [{"atk": 1.0}]},
            {"action_id": "s", "name": "战技", "action_type": "skill", "target_type": "single",
             "damage_type": "physical", "scaling": [{"atk": 1.5}], "skill_point_cost": 1}],
    }], "policy": policy}},
        {"stage": {"stage_id": "scripted", "enemies": enemies,
                   "termination": {"mode": termination, "max_action_value": av}}})


def _compiled(policy, **kwargs):
    build, stage = _build(policy, **kwargs)
    return compile_encounter(build, stage)


def _policy(action="basic", target=None):
    entry = {"turn": 1, "actor": "hero", "action": action}
    if target is not None:
        entry["target"] = target
    return {"mode": "scripted", "script": [entry]}


def _ultimate_compiled(ultimate_script, *, script=None, **kwargs):
    policy = {
        "mode": "scripted", "ult_timing": "scripted",
        "script": script or [{"turn": 1, "actor": "hero", "action": "basic"}],
        "ultimate_script": ultimate_script,
    }
    build, stage = _build(policy, **kwargs)
    member = build["build"]["team"][0]
    member["base_stats"]["max_energy"] = 0
    member["actions"].append({
        "action_id": "u", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "physical",
        "scaling": [{"atk": 2.0}], "energy_cost": 0, "energy_gain": 0,
    })
    return compile_encounter(build, stage)


class TestScriptedRandom:
    def test_sequence_consumed_remaining_and_exhaustion(self):
        rng = ScriptedRandom([0.0, 0.75])
        assert rng.random() == 0.0
        assert rng.consumed == 1 and rng.remaining == (0.75,)
        assert rng.random() == 0.75
        assert rng.consumed == 2 and rng.remaining == ()
        with pytest.raises(RuntimeError, match="已耗尽"):
            rng.random()

    @pytest.mark.parametrize("value", [-0.01, 1.0, math.nan, math.inf])
    def test_out_of_range_rejected(self, value):
        with pytest.raises(ValueError, match="0 <= value < 1"):
            ScriptedRandom([value])

    @pytest.mark.parametrize("value", [True, "0.5", None])
    def test_non_numeric_rejected(self, value):
        with pytest.raises(TypeError, match="须为实数"):
            ScriptedRandom([value])

    def test_choice_uses_shared_sequence(self):
        rng = ScriptedRandom([0.9])
        assert rng.choice(["a", "b", "c"]) == "c"
        assert rng.remaining == ()
        with pytest.raises(IndexError):
            ScriptedRandom([]).choice([])

    def test_sample_uses_shared_sequence(self):
        rng = ScriptedRandom([0.5, 0.0])
        assert rng.sample(["a", "b", "c", "d"], 2) == ["c", "a"]
        assert rng.remaining == ()

    def test_shuffle_uses_shared_sequence(self):
        rng = ScriptedRandom([0.5, 0.0])
        values = [1, 2, 3]
        assert rng.shuffle(values) is None
        assert values == [3, 1, 2]
        assert rng.remaining == ()

    def test_randint_and_uniform_use_shared_sequence(self):
        rng = ScriptedRandom([0.75, 0.25])
        assert rng.randint(2, 5) == 5
        assert rng.uniform(10.0, 20.0) == 12.5
        assert rng.remaining == ()

    def test_probability_endpoints(self):
        pipeline = SettlementPipeline(mode=MODE_ROLL)
        pipeline.rng = ScriptedRandom([0.0, 0.999])
        assert pipeline.roll_debuff_apply(0.0) is False
        assert pipeline.mechanic_chance(1.0) is True
        expr = ExprCompiler()
        rng = ScriptedRandom([0.0, 0.999])
        assert expr.evaluate(expr.compile("chance(0)"), rng=rng) is False
        assert expr.evaluate(expr.compile("chance(100)"), rng=rng) is True


class TestScriptedWorldline:
    def test_complete_win_is_engine_result_and_seed_independent(self):
        compiled = _compiled(_policy(), enemy_hp=1, av=1000, termination="wipe")
        first = run_scripted(compiled, [0.99], seed=1, initial_sp=5, initial_energy_ratio=0.0)
        second = run_scripted(compiled, [0.99], seed=999, initial_sp=5, initial_energy_ratio=0.0)
        assert first.outcome == "win" and first.record.enemies_alive == 0
        assert first.action_value == first.state.clock
        assert first.state.snapshot() == second.state.snapshot()
        assert first.state.log == second.state.log

    def test_complete_loss(self):
        compiled = _compiled(_policy(), hero_hp=1, hero_spd=100, enemy_spd=200,
                             enemy_atk=10000, av=1000)
        enemy_action = Action(action_id="enemy_basic", name="敌普攻", action_type="basic",
                              target_type="single", damage_type="physical",
                              scaling=[{"atk": 1.0}])
        compiled = replace(compiled, actions_by_actor={
            **compiled.actions_by_actor, "e1": [enemy_action]})
        result = run_scripted(compiled, [0.0, 0.99], initial_sp=5, initial_energy_ratio=0.0)
        assert result.outcome == "loss"
        assert not result.state.actors["hero"].alive
        assert result.random_source.consumed == 2

    def test_complete_timeout(self):
        compiled = _compiled(_policy(), hero_spd=150, enemy_spd=100, av=70)
        result = run_scripted(compiled, [0.99], initial_sp=5, initial_energy_ratio=0.0)
        assert result.outcome == "timeout"
        assert result.record.allies_alive == 1 and result.record.enemies_alive == 1

    @pytest.mark.parametrize("target", ["e2", "假人乙"])
    def test_action_and_target_replay(self, target):
        compiled = _compiled(_policy(target=target), second_enemy_hp=1)
        result = run_scripted(compiled, [0.99], initial_sp=5, initial_energy_ratio=0.0)
        assert result.outcome == "timeout"
        assert not result.state.actors["e2"].alive
        assert result.state.actors["e1"].alive
        assert any("英雄 对 假人乙 使用 普攻" in line for line in result.state.log)

    def test_illegal_action_raises(self):
        compiled = _compiled(_policy(action="s"))
        with pytest.raises(RuntimeError, match="行动.*不在合法集"):
            run_scripted(compiled, [], initial_sp=0, initial_energy_ratio=0.0)

    def test_illegal_target_raises_before_random_finalization(self):
        compiled = _compiled(_policy(target="不存在的敌人"), second_enemy_hp=1)
        with pytest.raises(RuntimeError, match="目标.*不在合法候选集"):
            run_scripted(compiled, [0.99], initial_sp=5, initial_energy_ratio=0.0)

    def test_missing_random_value_raises(self):
        compiled = _compiled(_policy(), enemy_hp=1, av=1000, termination="wipe")
        with pytest.raises(RuntimeError, match="已耗尽"):
            run_scripted(compiled, [], initial_sp=5, initial_energy_ratio=0.0)

    def test_unconsumed_random_value_raises(self):
        compiled = _compiled(_policy(), enemy_hp=1, av=1000, termination="wipe")
        with pytest.raises(RuntimeError, match="未全部消费"):
            run_scripted(compiled, [0.99, 0.5], initial_sp=5, initial_energy_ratio=0.0)


class TestUltimateScript:
    def test_compile_gates(self):
        entry = {"turn": 1, "window": "before_action", "actor": "hero", "action": "skip"}
        policy = {"mode": "scripted", "ult_timing": "after_action",
                  "script": [{"turn": 1, "actor": "hero", "action": "basic"}],
                  "ultimate_script": [entry]}
        with pytest.raises(ValueError, match="ult_timing 不是 scripted"):
            BuildCompiler()._compile_policy(policy)
        policy["ult_timing"] = "scripted"
        policy["ultimate_script"] = [{**entry, "window": "mid_action"}]
        with pytest.raises(ValueError, match="非法值 'mid_action'"):
            BuildCompiler()._compile_policy(policy)
        policy["ultimate_script"] = [entry]
        compiled = BuildCompiler()._compile_policy(policy)
        assert compiled.ult_timing == "scripted" and len(compiled.ultimate_script) == 1

    def test_normal_action_cannot_bypass_ultimate_script(self):
        compiled = _ultimate_compiled([
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "skip"},
        ], script=[{"turn": 1, "actor": "hero", "action": "ultimate"}],
            hero_spd=150, enemy_spd=100, av=70)
        with pytest.raises(RuntimeError, match="普通行动不得选择 ultimate"):
            run_scripted(compiled, [], initial_sp=5)

    def test_skip_cast_and_target(self):
        compiled = _ultimate_compiled([
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "skip"},
            {"turn": 1, "window": "after_action", "actor": "hero", "action": "ultimate",
             "target": "e2"},
            {"turn": 1, "window": "after_action", "actor": "hero", "action": "skip"},
        ], hero_spd=150, enemy_spd=100, av=70, second_enemy_hp=1e9)
        result = run_scripted(compiled, [0.99, 0.99], initial_sp=5)
        assert result.outcome == "timeout"
        assert any("英雄 对 假人乙 使用 终结技" in line for line in result.state.log)
        assert result.random_source.consumed == 2

    def test_continuous_cast_in_same_window(self):
        compiled = _ultimate_compiled([
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "ultimate"},
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "skip"},
            {"turn": 1, "window": "after_action", "actor": "hero", "action": "skip"},
        ], hero_spd=150, enemy_spd=100, av=70)
        result = run_scripted(compiled, [0.99, 0.99], initial_sp=5)
        actions = [line for line in result.state.log if "使用" in line]
        assert "终结技" in actions[0] and "普攻" in actions[1]

    @pytest.mark.parametrize("entries,message", [
        ([], "已耗尽"),
        ([{"turn": 1, "window": "after_action", "actor": "hero", "action": "skip"}],
         "窗口失配"),
        ([{"turn": 1, "window": "before_action", "actor": "other", "action": "skip"}],
         "不在 ready 集"),
        ([{"turn": 1, "window": "before_action", "actor": "hero", "action": "missing"}],
         "不在 ready 集"),
    ])
    def test_decision_mismatch_raises(self, entries, message):
        compiled = _ultimate_compiled(entries, hero_spd=150, enemy_spd=100, av=70)
        with pytest.raises(RuntimeError, match=message):
            run_scripted(compiled, [], initial_sp=5)

    def test_ultimate_target_mismatch_raises(self):
        compiled = _ultimate_compiled([
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "ultimate",
             "target": "missing"},
        ], hero_spd=150, enemy_spd=100, av=70)
        with pytest.raises(RuntimeError, match="目标.*不在合法候选集"):
            run_scripted(compiled, [], initial_sp=5)

    def test_save_restore_preserves_random_and_ultimate_cursors(self):
        compiled = _ultimate_compiled([
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "ultimate"},
            {"turn": 1, "window": "before_action", "actor": "hero", "action": "skip"},
            {"turn": 1, "window": "after_action", "actor": "hero", "action": "skip"},
            {"turn": 2, "window": "after_action", "actor": "hero", "action": "skip"},
            {"turn": 3, "window": "before_action", "actor": "hero", "action": "skip"},
            {"turn": 3, "window": "after_action", "actor": "hero", "action": "skip"},
        ], script=[
            {"turn": 1, "actor": "hero", "action": "basic"},
            {"turn": 3, "actor": "hero", "action": "basic"},
        ], hero_spd=150, enemy_spd=100, av=150)
        engine = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, initial_sp=5)
        engine.pipeline.rng = ScriptedRandom([0.99, 0.99, 0.99])
        engine.setup()
        engine.step()
        saved = json.loads(json.dumps(engine.save_state()))
        engine.run()
        restored = CombatEngine.load_state(
            compiled, saved, mode=MODE_ROLL, rng=ScriptedRandom([]))
        restored.run()
        assert restored.decision.export_state() == {"ultimate_cursor": 6}
        assert restored.pipeline.rng.consumed == 3
        assert restored.save_state() == engine.save_state()


class TestRealTeamWorldline:
    def test_acheron_full_decision_axis(self):
        build, stage, values = make_acheron_worldline_parts()
        recorder = None

        def prepare(engine):
            nonlocal recorder
            engine.setup()
            recorder = RunRecorder(engine)

        result = run_scripted(
            compile_encounter(build, stage), values,
            initial_sp=5, initial_energy_ratio=1.0, prepare_engine=prepare,
        )
        assert result.outcome == "timeout" and result.state.turn_count == 16
        assert result.random_source.consumed == 92 and not result.random_source.remaining
        assert recorder is not None and recorder.ult_casts == 3
        assert math.isclose(result.state.total_damage, 13835.311721259002, rel_tol=1e-9)
        assert any("轮盘勋爵" in line for line in result.state.log)
        assert any("猜猜谁住在这里" in line for line in result.state.log)
        assert any("残梦尽染，一刀缭断" in line for line in result.state.log)
