"""13_validator §13.3 静态校验批量：$self 字段存在性 / override 互斥·冲突 /
重复 actor_id / resource_id 存在性 / 形状（人数/等级/速度/暴击率建议档）."""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.stage_compiler import StageCompiler

from tests.template_materialize import TEST_TEMPLATE_ROOTS


def _member(**kw):
    m = {"character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 1.0}]}]}
    m.update(kw)
    return m


def _build(members):
    return {"build": {"team": members, "policy": {
        "name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 70}}}


def _compile(build, stage=None):
    return compile_encounter(build, stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


class TestSelfNsFields:
    def test_typo_rejected(self):
        out: list = []
        with pytest.raises(ValueError, match=r"不存在的 `\$self.atkk`"):
            BuildCompiler()._compile_hooks([{
                "event": "on_turn_start", "condition": "$self.atkk > 0",
                "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
            }], "模板 X", "h", out)

    def test_whitelist_and_prefix_pass(self):
        out: list = []
        BuildCompiler()._compile_hooks([{
            "event": "on_turn_start", "condition": "$self.max_hp > 0 and $self.dmg_fire > 0",
            "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
        }], "模板 X", "h", out)
        assert out, "白名单字段（max_hp）与 dmg_<元素> 前缀应放行"

    def test_binding_param_extra_pass(self):
        out: list = []
        BuildCompiler()._compile_hooks([{
            "event": "on_turn_start", "condition": "$self.crit_rate_param > 0",
            "effects": [{"effect_type": "apply_modifier", "modifier": {
                "modifier_id": "M", "stat_effects": {"crit_rate": "$self.crit_rate_param"}}}],
        }], "模板 X", "h", out, extra_self_fields=("crit_rate_param",))
        assert out, "owner 绑定参数经 extra 放行"

    def test_effect_slot_typo_rejected(self):
        with pytest.raises(ValueError, match=r"不存在的 `\$self.crit_ratee`"):
            BuildCompiler()._validate_effects([{
                "effect_type": "apply_modifier",
                "modifier": {"modifier_id": "M",
                             "stat_effects": {"crit_rate": "$self.crit_ratee"}}}], "模板 X")


class TestOverrideChecks:
    def test_mutex_same_modifier(self):
        with pytest.raises(ValueError, match="override 互斥"):
            BuildCompiler()._validate_modifier_spec({
                "modifier_id": "M",
                "stat_effects": {"atk": 100},
                "override_effects": {"atk": 200},
            }, "模板 X modifier")

    def test_conflict_initial_modifiers(self):
        from hsr_nous.sim.state import Modifier
        mods = [
            Modifier(modifier_id="A", name="a", modifier_type="buff", duration=0,
                     override_effects={"spd": 120.0}),
            Modifier(modifier_id="B", name="b", modifier_type="buff", duration=0,
                     override_effects={"spd": 130.0}),
        ]
        with pytest.raises(ValueError, match="override 冲突"):
            BuildCompiler()._final_cross_checks(
                [], {}, {"hero": mods}, [], {}, {})


class TestDuplicateActorId:
    def test_team_duplicate_rejected(self):
        m2 = _member(actor_id="hero", name="另一个英雄")
        with pytest.raises(ValueError, match="重复 actor_id"):
            _compile(_build([_member(), _member(actor_id="hero", name="另一个英雄")]))


class TestResourceCrossCheck:
    def test_unknown_resource_rejected(self):
        m = _member(actions=[{"action_id": "b", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "physical",
                              "scaling": [{"atk": 1.0}],
                              "resource_gain": {"ghost_seed": 1}}])
        with pytest.raises(ValueError, match="未声明资源 'ghost_seed'"):
            _compile(_build([m]))

    def test_internal_prefix_pass(self):
        m = _member(actions=[{"action_id": "b", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "physical",
                              "scaling": [{"atk": 1.0}],
                              "resource_gain": {"_state_actions_khaslana": 1}}])
        _compile(_build([m]))   # 内部 `_` 前缀（引擎计数器）放行


class TestShapeChecks:
    def test_team_size_over_4(self):
        with pytest.raises(ValueError, match="超过上限 4"):
            _compile(_build([_member(actor_id=f"h{i}", name=f"英雄{i}") for i in range(5)]))

    def test_level_out_of_range(self):
        with pytest.raises(ValueError, match="level 81 越界"):
            _compile(_build([_member(level=81)]))

    def test_spd_not_positive(self):
        with pytest.raises(ValueError, match="spd 必须 > 0"):
            _compile(_build([_member(base_stats={"atk": 1000, "spd": 0, "hp": 3000,
                                                 "max_energy": 100})]))

    def test_crit_rate_warns(self):
        with pytest.warns(UserWarning, match="crit_rate"):
            _compile(_build([_member(base_stats={"atk": 1000, "spd": 100, "hp": 3000,
                                                 "max_energy": 100, "crit_rate": 1.5})]))


class TestStageShapeChecks:
    def test_waves_over_10(self):
        stage = {"stage_id": "s",
                 "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50}],
                 "waves": [{"wave_index": i, "enemies": []} for i in range(1, 12)]}
        with pytest.raises(ValueError, match="波次数 11 超上限 10"):
            StageCompiler().compile(stage)

    def test_wave_enemies_over_10(self):
        stage = {"stage_id": "s",
                 "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50}],
                 "waves": [{"wave_index": 1,
                            "enemies": [{"actor_id": f"w{i}", "name": "怪", "hp": 1, "spd": 1}
                                        for i in range(11)]}]}
        with pytest.raises(ValueError, match="敌人数超上限 10"):
            StageCompiler().compile(stage)

    def test_enemy_level_and_spd(self):
        with pytest.raises(ValueError, match="level 121 越界"):
            StageCompiler().compile({"stage_id": "s", "enemies": [
                {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50, "level": 121}]})
        with pytest.raises(ValueError, match="spd 必须 > 0"):
            StageCompiler().compile({"stage_id": "s", "enemies": [
                {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 0}]})
