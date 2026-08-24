"""编译期校验闸测试：错误模板 → 明确报错（不许静默吞）.

覆盖清单（对应 13_validator.md §13.2 闸表）：
- effect_type 白名单（编译器 + 引擎双闸）
- 未知键拒绝（member / base_stats / actions / apply_modifiers / hooks / policy / termination / stage / enemy）
- 枚举字段（ult_timing / mode / termination.mode / action_type / target_type / stack_mode / tick_anchor / effect_scope）
- hook effects 表达式槽预编译
- target 选择器严格化（编译器 + 引擎双闸）
- 糖键"已知但未落地"拒绝 / inline hooks 拒绝
- level_key 透传（回归：曾静默丢失）
- 契约表补登记（on_cycle_start/on_cycle_end）
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.bus import DEFAULT_CONTRACT, EventBus
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.stage_compiler import StageCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED


def _build(**over):
    """最小合法 build；over 深替换一层."""
    build = {
        "team": [{
            "inline": True, "actor_id": "hero", "name": "测试员", "level": 80,
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
            "actions": [{
                "action_id": "b", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "fire",
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }
    build.update(over)
    return {"build": build}


def _stage(**over):
    stage = {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e6, "spd": 100, "max_toughness": 30}],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }
    stage.update(over)
    return {"stage": stage}


def _engine():
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(), _stage()), mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


# ---------------------------------------------------------------------------
# effect_type 白名单
# ---------------------------------------------------------------------------

class TestEffectTypeWhitelist:
    def test_compiler_rejects_unknown_effect_type(self):
        with pytest.raises(ValueError, match="未知 effect_type 'gain_resourcce'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "gain_resourcce", "amount": 1}], "模板 X")

    def test_compiler_error_lists_legal_set(self):
        with pytest.raises(ValueError, match="gain_resource"):
            BuildCompiler()._validate_effects([{"effect_type": "heal"}], "模板 X")

    def test_compiler_rejects_effect_param_typo(self):
        with pytest.raises(ValueError, match="未知键 'scaling_atkk'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "scaling_atkk": 1.0}], "模板 X")

    def test_engine_backstop_rejects_unknown_effect_type(self):
        """绕过编译层手写 CompiledHook 时引擎同口径炸（不静默跳过）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        with pytest.raises(ValueError, match="未知 effect_type 'fly_to_moon'"):
            eng._run_hook_effect(st, {"effect_type": "fly_to_moon"}, {})

    def test_engine_implemented_set_matches_doc_source(self):
        """单一事实源：引擎分支集合 == effect_types.py 登记集合."""
        from hsr_nous.sim_schema.effect_types import ENGINE_EFFECT_TYPES
        assert "break_damage" in ENGINE_EFFECT_TYPES
        assert len(ENGINE_EFFECT_TYPES) >= 15


# ---------------------------------------------------------------------------
# 未知键拒绝
# ---------------------------------------------------------------------------

class TestUnknownKeyRejection:
    def test_member_typo(self):
        bad = _build()
        bad["build"]["team"][0]["levell"] = 80
        with pytest.raises(ValueError, match="未知键 'levell'"):
            compile_encounter(bad, _stage())

    def test_base_stats_typo(self):
        bad = _build()
        bad["build"]["team"][0]["base_stats"]["atkk"] = 1000
        with pytest.raises(ValueError, match="未知键 'atkk'"):
            compile_encounter(bad, _stage())

    def test_action_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["toughness_dmgg"] = 10
        with pytest.raises(ValueError, match="未知键 'toughness_dmgg'"):
            compile_encounter(bad, _stage())

    def test_apply_modifiers_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "durationd": 2}]
        with pytest.raises(ValueError, match="未知键 'durationd'"):
            compile_encounter(bad, _stage())

    def test_hook_dict_typo(self):
        with pytest.raises(ValueError, match="未知键 'condtion'"):
            BuildCompiler()._compile_hooks(
                [{"event": "on_battle_start", "condtion": "true"}], "模板 X", "hero", [])

    def test_hook_unknown_event(self):
        with pytest.raises(ValueError, match="未登记事件 'after_actoin'"):
            BuildCompiler()._compile_hooks(
                [{"event": "after_actoin"}], "模板 X", "hero", [])

    def test_policy_typo(self):
        bad = _build()
        bad["build"]["policy"]["ult_timingg"] = "never"
        with pytest.raises(ValueError, match="未知键 'ult_timingg'"):
            compile_encounter(bad, _stage())

    def test_termination_typo(self):
        with pytest.raises(ValueError, match="未知键 'max_action_valuee'"):
            StageCompiler().compile(_stage()["stage"] | {"termination": {"mode": "fixed_av", "max_action_valuee": 1}})

    def test_stage_top_typo(self):
        with pytest.raises(ValueError, match="未知键 'enemiess'"):
            StageCompiler().compile(_stage()["stage"] | {"enemiess": []})

    def test_enemy_typo(self):
        with pytest.raises(ValueError, match="未知键 'hpp'"):
            StageCompiler().compile(
                _stage()["stage"] | {"enemies": [{"actor_id": "e", "hpp": 1}]})

    def test_wave_typo(self):
        with pytest.raises(ValueError, match="未知键 'wave_indexx'"):
            StageCompiler().compile(
                _stage()["stage"] | {"waves": [{"wave_indexx": 2, "enemies": []}]})


# ---------------------------------------------------------------------------
# 枚举字段
# ---------------------------------------------------------------------------

class TestEnumGates:
    def test_ult_timing_typo(self):
        """历史案例：after_actoin 曾致终结技永远不开零提示."""
        bad = _build()
        bad["build"]["policy"]["ult_timing"] = "after_actoin"
        with pytest.raises(ValueError, match="ult_timing.*after_actoin"):
            compile_encounter(bad, _stage())

    def test_stage_mode_typo(self):
        """历史案例：mode 拼错曾静默关闭轮次系统."""
        with pytest.raises(ValueError, match="mode 非法值 'forgotten_halll'"):
            StageCompiler().compile(_stage()["stage"] | {"mode": "forgotten_halll"})

    def test_stage_mode_legal(self):
        st = StageCompiler().compile(_stage()["stage"] | {"mode": "forgotten_hall"})
        assert st.cycle is not None

    def test_termination_mode_typo(self):
        with pytest.raises(ValueError, match="mode 非法值 'fixed_avv'"):
            StageCompiler().compile(
                _stage()["stage"] | {"termination": {"mode": "fixed_avv"}})

    def test_action_type_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["action_type"] = "baisc"
        with pytest.raises(ValueError, match="action_type 非法值 'baisc'"):
            compile_encounter(bad, _stage())

    def test_target_type_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["target_type"] = "singel"
        with pytest.raises(ValueError, match="target_type 非法值 'singel'"):
            compile_encounter(bad, _stage())

    def test_target_type_unimplemented_alias_rejected(self):
        """enemy_aoe 引擎未实现（落入默认单体=静默错）——按词表冻结拒绝."""
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["target_type"] = "enemy_aoe"
        with pytest.raises(ValueError, match="target_type 非法值 'enemy_aoe'"):
            compile_encounter(bad, _stage())

    def test_stack_mode_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "stack_mode": "refres"}]
        with pytest.raises(ValueError, match="stack_mode 非法值 'refres'"):
            compile_encounter(bad, _stage())

    def test_tick_anchor_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "tick_anchor": "owner_turn_ennd"}]
        with pytest.raises(ValueError, match="tick_anchor 非法值 'owner_turn_ennd'"):
            compile_encounter(bad, _stage())

    def test_effect_scope_typo(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "effect_scope": "tem"}]
        with pytest.raises(ValueError, match="effect_scope 非法值 'tem'"):
            compile_encounter(bad, _stage())


# ---------------------------------------------------------------------------
# hook effects 表达式槽预编译（B8：非法表达式编译期炸）
# ---------------------------------------------------------------------------

class TestEffectExprPrecompile:
    def test_syntax_error_rejected(self):
        with pytest.raises(ValueError, match="amount 表达式非法"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "gain_resource", "resource_id": "x", "amount": "1 +"}],
                "模板 X")

    def test_non_whitelist_function_rejected(self):
        with pytest.raises(ValueError, match="scaling_atk 表达式非法"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "scaling_atk": "eval(1)"}], "模板 X")

    def test_all_expr_slots_checked(self):
        for slot, eff in (
            ("ratio", {"effect_type": "heal_self", "ratio": "?"}),
            ("scaling_hp", {"effect_type": "deal_damage", "scaling_hp": "?"}),
            ("delta", {"effect_type": "adjust_stacks", "modifier_id": "m", "delta": "?"}),
            ("percent", {"effect_type": "set_hp_to_percent", "percent": "?"}),
        ):
            with pytest.raises(ValueError, match="表达式非法"):
                BuildCompiler()._validate_effects([eff], "模板 X")

    def test_legal_expression_passes(self):
        BuildCompiler()._validate_effects(
            [{"effect_type": "trigger_action", "action_id": "a",
              "scaling_atk": "0.4 * (1 + 0.2 * stacks($self, 'SOUL_PYRE'))"}], "模板 X")


# ---------------------------------------------------------------------------
# target 选择器严格化
# ---------------------------------------------------------------------------

class TestTargetSelector:
    def test_compiler_rejects_unknown_selector(self):
        with pytest.raises(ValueError, match="未知 target 选择器 'enemy_firsst'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "target": "enemy_firsst", "scaling_atk": 1.0}],
                "模板 X")

    def test_engine_no_silent_fallback(self):
        """引擎侧同口径炸（曾静默退化 enemy_first）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        with pytest.raises(ValueError, match="未知 hook target 选择器 'enemy_firsst'"):
            eng._hook_target_states("enemy_firsst", st, {})

    def test_legal_selectors_pass(self):
        for sel in ("self", "all_allies", "other_allies", "all_enemies",
                    "enemy_first", "highest_hp", "highest_hp_hit", "$event.actor"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "remove_modifier", "modifier_id": "m", "target": sel}], "模板 X")


# ---------------------------------------------------------------------------
# 糖键 / inline hooks 拒绝
# ---------------------------------------------------------------------------

class TestUnwiredSugarAndInlineHooks:
    def test_sugar_key_in_hook_rejected(self):
        with pytest.raises(ValueError, match="糖键 'trigger_limit'.*未接线"):
            BuildCompiler()._compile_hooks(
                [{"event": "on_turn_start", "trigger_limit": {"per_turn": 1}}], "模板 X", "h", [])

    def test_sugar_key_in_modifier_spec_rejected(self):
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "trigger_limit": {"per_turn": 1}}]
        with pytest.raises(ValueError, match="糖键 'trigger_limit'"):
            compile_encounter(bad, _stage())

    def test_inline_hooks_rejected(self):
        bad = _build()
        bad["build"]["team"][0]["hooks"] = [{"event": "on_battle_start"}]
        with pytest.raises(ValueError, match="inline 角色不支持 hooks"):
            compile_encounter(bad, _stage())


# ---------------------------------------------------------------------------
# level_key 透传（回归：曾静默丢失）
# ---------------------------------------------------------------------------

class TestLevelKeyPassthrough:
    def test_level_key_compiled(self):
        bad = _build()
        bad["build"]["team"][0]["actions"].append({
            "action_id": "fu", "name": "追加", "action_type": "follow_up",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "level_key": "talent",
        })
        compiled = compile_encounter(bad, _stage())
        fu = next(a for a in compiled.actions_by_actor["hero"] if a.action_id == "fu")
        assert fu.level_key == "talent"


# ---------------------------------------------------------------------------
# 契约表补登记
# ---------------------------------------------------------------------------

class TestCycleContract:
    def test_cycle_events_registered(self):
        assert DEFAULT_CONTRACT["on_cycle_start"] == "emit"
        assert DEFAULT_CONTRACT["on_cycle_end"] == "emit"

    def test_cycle_events_emittable(self):
        bus = EventBus()
        seen = []
        bus.subscribe("on_cycle_start", lambda et, p, ctx: seen.append(et))
        bus.emit("on_cycle_start", {"cycle_index": 1}, None)
        assert seen == ["on_cycle_start"]

    def test_engine_emits_cycle_events(self):
        """发射已接线：轮次预算跨过边界时 on_cycle_end/on_cycle_start 可被 hook 收到."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(), _stage(mode="forgotten_hall")),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        seen = []
        eng.bus.subscribe("on_cycle_start", lambda et, p, ctx: seen.append(("start", p["cycle_index"])))
        eng.bus.subscribe("on_cycle_end", lambda et, p, ctx: seen.append(("end", p["cycle_index"])))
        eng.state.cycle_end_clock = 0.0  # 强制下一轮 tick 跨轮次边界
        eng._tick_cycle()
        assert ("start", 2) in seen and ("end", 1) in seen


# ---------------------------------------------------------------------------
# validator 退役
# ---------------------------------------------------------------------------

class TestValidatorRetired:
    def test_validate_encounter_not_exported(self):
        import hsr_nous.sim_schema as ss
        assert not hasattr(ss, "validate_encounter")

    def test_validator_module_gone(self):
        with pytest.raises(ModuleNotFoundError):
            __import__("hsr_nous.sim_schema.validator")
