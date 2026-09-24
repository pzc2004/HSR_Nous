"""B4 策略层回放变体：mode: scripted/hybrid 逐回合脚本 + enemy_next_av 上下文（14_policy）.

语义钉：script turn 1 起（= state.turn_count + 1，决策时点 turn_count 尚未递增）；
scripted 严格模式未覆盖即报错；hybrid 未覆盖回合回退 action_rules；
actor 先 id 后名、action 先 id 后类型解析（合法集内）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED


def _build(policy, av=400.0, enemy_spd=130.0):
    return ({"build": {"team": [{
        "character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
        "base_stats": {"atk": 1000, "spd": 134, "hp": 3000, "max_energy": 100},
        "actions": [
            {"action_id": "b", "name": "普攻", "action_type": "basic", "target_type": "single",
             "damage_type": "physical", "scaling": [{"atk": 1.0}]},
            {"action_id": "s", "name": "战技", "action_type": "skill", "target_type": "single",
             "damage_type": "physical", "scaling": [{"atk": 1.5}], "skill_point_cost": 1}],
    }], "policy": policy}},
        {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": enemy_spd,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": av}}})


def _run(policy, av=400.0, enemy_spd=130.0):
    build, stage = _build(policy, av, enemy_spd)
    eng = CombatEngine.from_compiled(compile_encounter(build, stage),
                                     mode=MODE_EXPECTED, initial_sp=5,
                                     initial_energy_ratio=0.0)
    return eng.run()


class TestPolicyScriptGates:
    def _cp(self, policy):
        return BuildCompiler()._compile_policy(policy)

    def test_mode_enum(self):
        with pytest.raises(ValueError, match="非法值 'scripteddd'"):
            self._cp({"mode": "scripteddd", "script": [{"turn": 1, "actor": "h", "action": "s"}]})

    def test_rule_based_with_script_rejected(self):
        with pytest.raises(ValueError, match="rule_based 但写了 script"):
            self._cp({"mode": "rule_based", "script": [{"turn": 1, "actor": "h", "action": "s"}]})

    def test_scripted_requires_script(self):
        with pytest.raises(ValueError, match="必须配非空 script"):
            self._cp({"mode": "scripted"})

    def test_script_entry_gates(self):
        with pytest.raises(ValueError, match="未知键 'actorr'"):
            self._cp({"mode": "scripted",
                      "script": [{"turn": 1, "actorr": "h", "action": "s"}]})
        with pytest.raises(ValueError, match="turn 须为 ≥1 的整数"):
            self._cp({"mode": "scripted", "script": [{"turn": 0, "actor": "h", "action": "s"}]})
        with pytest.raises(ValueError, match="缺 actor/action"):
            self._cp({"mode": "scripted", "script": [{"turn": 1, "actor": "h"}]})

    def test_valid_scripted_compiles(self):
        p = self._cp({"mode": "scripted",
                      "script": [{"turn": 1, "actor": "hero", "action": "s"},
                                 {"turn": 2, "actor": "英雄", "action": "basic"}]})
        assert p.mode == "scripted" and len(p.script) == 2


class TestScriptedRuntime:
    def test_exact_replay(self):
        """脚本轴：turn1 战技 → 后续普攻（敌方空过也占 turn_count——hero 动在 1/3/5/7/9）."""
        state = _run({"mode": "scripted",
                      "script": [{"turn": 1, "actor": "hero", "action": "s"}]
                      + [{"turn": t, "actor": "hero", "action": "basic"}
                         for t in (3, 5, 7, 9)]})
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert "战技" in uses[0] and all("普攻" in l for l in uses[1:]), (
            f"首动必须是脚本指定的战技：{uses[:3]}")

    def test_scripted_strict_missing_raises(self):
        """严格模式：脚本只写 turn 1，hero 的 turn 3 决策未覆盖即报错（turn 2 是敌方空过）."""
        with pytest.raises(RuntimeError, match="未覆盖 turn 3"):
            _run({"mode": "scripted", "script": [{"turn": 1, "actor": "hero", "action": "s"}]})

    def test_hybrid_fallback_to_rules(self):
        """hybrid：turn 1 按脚本战技，后续回退 action_rules（恒普攻）."""
        state = _run({"mode": "hybrid",
                      "script": [{"turn": 1, "actor": "hero", "action": "s"}],
                      "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]})
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert "战技" in uses[0] and all("普攻" in l for l in uses[1:])


class TestEnemyNextAv:
    def test_context_key_wired(self):
        """enemy_next_av 进策略上下文（5a 敌人意图可见性）：小于阈值触发规则."""
        state = _run({
            "action_rules": [
                {"condition": "enemy_next_av < 100", "action": "s", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0}],
            "parameters": {}}, av=150.0)
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        # 假人 spd130 → 下一动 AV≈76.9 < 100：规则命中 → 首动战技
        assert uses and "战技" in uses[0], f"enemy_next_av 未进上下文：{uses[:2]}"

    def test_context_key_large_when_far(self):
        """阈值不满足时回退——enemy_next_av 是真实求值不是恒真（慢敌 spd20 → 下一动 ~425AV）."""
        state = _run({
            "action_rules": [
                {"condition": "enemy_next_av < 10", "action": "s", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0}],
            "parameters": {}}, av=150.0, enemy_spd=20.0)
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert uses and "普攻" in uses[0]
