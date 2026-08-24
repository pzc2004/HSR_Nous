"""编译期校验闸测试：错误模板 → 明确报错（不许静默吞）.

覆盖清单（对应 13_validator.md §13.2 闸表）：
- effect_type 白名单（编译器 + 引擎双闸）
- 未知键拒绝（member / base_stats / actions / apply_modifiers / hooks / policy / termination / stage / enemy）
- 枚举字段（ult_timing / mode / termination.mode / action_type / target_type / stack_mode / tick_anchor / effect_scope）
- hook effects 表达式槽预编译
- target 选择器严格化（编译器 + 引擎双闸）
- 糖键"已知但未落地"拒绝 / termination.mode 未实现值拒绝 / inline hooks 拒绝
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
from tests.template_materialize import materialize_template


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

    def test_termination_mode_unimplemented_rejected(self):
        """词表内但未实现的 mode（kill_target/survival/wipe）：编译期炸"未实现"——
        曾编译通过但引擎不判停=静默吞."""
        for mode in ("kill_target", "survival", "wipe"):
            with pytest.raises(ValueError, match=f"mode '{mode}' 已登记但未实现"):
                StageCompiler().compile(
                    _stage()["stage"] | {"termination": {"mode": mode}})

    def test_termination_mode_fixed_av_still_compiles(self):
        st = StageCompiler().compile(
            _stage()["stage"] | {"termination": {"mode": "fixed_av", "max_action_value": 150}})
        assert st.termination_mode == "fixed_av"

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


class TestGainEnergyTargetVocab:
    """gain_energy target 收窄为二值（05_effects §回复能量；编译闸与运行时同词表）——
    全词表放行曾让 highest_hp 等静默落入"全体充能"else 分支."""

    def test_compiler_rejects_out_of_vocab_selector(self):
        with pytest.raises(ValueError, match=r"gain_energy 的 target 非法值 'lowest_hp_ally'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "gain_energy", "target": "lowest_hp_ally", "amount": 10}],
                "模板 X")

    def test_compiler_rejects_full_vocab_selector(self):
        """highest_hp 在 hook 全词表内，但对 gain_energy 非法（收窄闸先于通用闸）."""
        with pytest.raises(ValueError, match=r"gain_energy 的 target 非法值 'highest_hp'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "gain_energy", "target": "highest_hp", "amount": 10}],
                "模板 X")

    def test_compiler_accepts_self_and_all_allies(self):
        for sel in ("self", "all_allies"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "gain_energy", "target": sel, "amount": 10}], "模板 X")

    def test_engine_backstop_rejects(self):
        """绕过编译层手写 effect 时引擎同口径炸（不静默当全体）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        with pytest.raises(ValueError, match=r"gain_energy 的 target 非法值 'highest_hp'"):
            eng._run_hook_effect(st, {"effect_type": "gain_energy",
                                      "target": "highest_hp", "amount": 10}, {})


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


# ---------------------------------------------------------------------------
# 键闸覆盖补全（build 顶层 / 模板顶层 / state_config / techniques / team_modifiers / eidolons）
# ---------------------------------------------------------------------------

def _compile_with_tpl(monkeypatch, tpl_over):
    """以内存模板编译（monkeypatch _load_template）：tpl_over 注入待测块."""
    tpl = {
        "actor_id": "9999", "name": "测试员",
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
        "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "fire",
                     "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
        **tpl_over,
    }
    monkeypatch.setattr(BuildCompiler, "_load_template",
                        staticmethod(lambda kind, ref: tpl))
    build = _build()
    build["build"]["team"] = [{"character_template": "9999", "level": 80}]
    return compile_encounter(build, _stage())


class TestKeyGateCoverage:
    def test_build_top_typo(self):
        bad = _build()
        bad["build"]["teamm"] = []
        with pytest.raises(ValueError, match="build 含未知键 'teamm'"):
            compile_encounter(bad, _stage())

    def test_template_top_typo(self, monkeypatch):
        """teamm（team_modifiers 错拼）在模板顶层曾静默吞整块——顶层键闸补上."""
        with pytest.raises(ValueError, match="角色模板 9999 含未知键 'teamm'"):
            _compile_with_tpl(monkeypatch, {"teamm": {"technique_point_initial_bonus": 3}})

    def test_state_config_key_typo(self, monkeypatch):
        with pytest.raises(ValueError, match="state_config 含未知键 'exit_conditionss'"):
            _compile_with_tpl(monkeypatch, {"state_config": {
                "state": "s", "exit_conditionss": [{"trigger": "on_action_count", "value": 1}]}})

    def test_state_config_exit_condition_key_typo(self, monkeypatch):
        with pytest.raises(ValueError, match="exit_conditions 含未知键 'triggerr'"):
            _compile_with_tpl(monkeypatch, {"state_config": {
                "state": "s", "exit_conditions": [{"triggerr": "on_action_count", "value": 1}]}})

    def test_technique_point_cost_typo(self, monkeypatch):
        """point_costt 错拼→编译期炸（曾读到默认 0 = 点池闸被绕过）."""
        with pytest.raises(ValueError, match="techniques 含未知键 'point_costt'"):
            _compile_with_tpl(monkeypatch, {"techniques": [
                {"technique_id": "t1", "point_costt": 5,
                 "effects": [{"effect_type": "gain_skill_point", "amount": 1}]}]})

    def test_team_modifiers_key_typo(self, monkeypatch):
        with pytest.raises(ValueError, match="team_modifiers 含未知键 'technique_point_initial_bonuss'"):
            _compile_with_tpl(monkeypatch, {"team_modifiers": {"technique_point_initial_bonuss": 3}})

    def test_eidolon_rank_and_entry_key(self, monkeypatch):
        with pytest.raises(ValueError, match="eidolons 含未知键 'E7'"):
            _compile_with_tpl(monkeypatch, {"eidolons": {"E7": {"name": "不存在的星魂"}}})
        with pytest.raises(ValueError, match="星魂 E1 含未知键 'stat_effectss'"):
            _compile_with_tpl(monkeypatch, {"eidolons": {"E1": {"stat_effectss": {"atk": 1}}}})

    def test_pre_battle_use_key_typo(self, monkeypatch):
        tpl_use = {"techniques": [{"technique_id": "t1", "point_cost": 1,
                                   "effects": [{"effect_type": "gain_skill_point", "amount": 1}]}]}
        tpl = {
            "actor_id": "9999", "name": "测试员",
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "fire",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
            **tpl_use,
        }
        monkeypatch.setattr(BuildCompiler, "_load_template",
                            staticmethod(lambda kind, ref: tpl))
        bad = _build()
        bad["build"]["team"] = [{"character_template": "9999", "level": 80}]
        bad["build"]["pre_battle"] = [{"actor_id": "9999", "techniquee": "t1"}]
        with pytest.raises(ValueError, match="pre_battle 含未知键 'techniquee'"):
            compile_encounter(bad, _stage())


# ---------------------------------------------------------------------------
# apply_modifiers.target 词表（引擎现状二值：self / all_enemies）
# ---------------------------------------------------------------------------

class TestApplyModifiersTargetVocab:
    def test_all_allies_rejected_at_compile_time(self):
        """all_allies 族引擎未支持——编译期炸，不许静默落入 else 当 all_enemies."""
        bad = _build()
        bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
            {"modifier_id": "M", "target": "all_allies"}]
        with pytest.raises(ValueError, match="target 非法值 'all_allies'"):
            compile_encounter(bad, _stage())

    def test_legal_targets_pass(self):
        for tgt in ("self", "all_enemies"):
            bad = _build()
            bad["build"]["team"][0]["actions"][0]["apply_modifiers"] = [
                {"modifier_id": "M", "target": tgt}]
            compile_encounter(bad, _stage())


# ---------------------------------------------------------------------------
# stat_effects 键错拼告警（开放命名空间：warn 不拒绝）
# ---------------------------------------------------------------------------

class TestStatEffectsKeyWarning:
    def test_typo_key_warns(self):
        with pytest.warns(UserWarning, match="crit_dmgg.*疑似 'crit_dmg' 错拼"):
            BuildCompiler()._validate_modifier_spec(
                {"modifier_id": "M", "stat_effects": {"crit_dmgg": 0.5}}, "模板 X")

    def test_warning_carries_template_ref(self):
        with pytest.warns(UserWarning, match="模板 X"):
            BuildCompiler()._validate_modifier_spec(
                {"modifier_id": "M", "stat_effects": {"atkk": 1.0}}, "模板 X")

    def test_known_and_custom_keys_silent(self):
        """合法键（含 dmg_/res_ 前缀族）与自定义 stat 不触发告警——开放命名空间不拦."""
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("error")  # 任何 warning 都炸
            BuildCompiler()._validate_modifier_spec(
                {"modifier_id": "M", "stat_effects": {
                    "crit_dmg": 0.5, "dmg_fire": 0.2, "res_pen": 0.1, "atk_pct": 0.1,
                    "my_custom_stat": 1.0}}, "模板 X")


# ---------------------------------------------------------------------------
# YAML 重复键检测（加载层：重复即炸，报文件名+键名）
# ---------------------------------------------------------------------------

class TestYamlDuplicateKeyGate:
    def test_duplicate_key_template_rejected(self):
        """重复键模板→炸（PyYAML 默认静默后值盖前值——1408 模板事故防线）."""
        from pathlib import Path
        d = Path("data/sim_templates/characters")
        d.mkdir(parents=True, exist_ok=True)
        f = d / "9997_dupkey.yaml"
        f.write_text(
            'actor_id: "9997"\nname: "测试员"\n'
            "base_stats: {atk: 1000}\n"
            "actions: []\n"
            "hooks:\n"
            "  - event: \"on_battle_start\"\n"
            "    effects:\n"
            "      - effect_type: \"apply_modifier\"\n"
            "        modifier:\n"
            "          modifier_id: \"M\"\n"
            "          stack_mode: \"refresh\"\n"
            "          stack_mode: \"set\"\n",
            encoding="utf-8")
        try:
            with pytest.raises(ValueError, match=r"9997_dupkey\.yaml 存在重复键 'stack_mode'"):
                BuildCompiler()._load_character_template("9997")
        finally:
            f.unlink(missing_ok=True)

    def test_clean_template_loads(self):
        """无重复键模板正常加载（1408 fixture 去重后回归锚；先物化保同 ID 唯一）."""
        materialize_template("1408_phainon.yaml")
        tpl = BuildCompiler()._load_character_template("1408")
        assert tpl["actor_id"] == "1408"
