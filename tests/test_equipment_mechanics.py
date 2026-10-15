"""装备机制进仿真 v1：光锥叠影绑定求值（B1）+ 光锥/遗器套装机制 hooks 通道.

通道钉：variable_bindings 编译期求值 → `$self.<param>` 命名空间（_HookSelfNS 回落）；
光锥/套装 hooks 与角色模板同一编译闸（owner=装备者）；notes 态自由文本不结算。
"""
from __future__ import annotations

import math

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 绑定求值器（variable_bindings → $self.<param>）
# ---------------------------------------------------------------------------

class TestVariableBindings:
    def _eval(self, bindings, tables, s=1):
        return BuildCompiler()._eval_variable_bindings(
            bindings, tables, superimposition=s, where="测试光锥")

    _TABLES = {"crit_rate": [0.10, 0.125, 0.15, 0.175, 0.20]}

    def test_superimposition_indexing(self):
        for s, want in ((1, 0.10), (3, 0.15), (5, 0.20)):
            params = self._eval(
                ["self.p = lookup_table('crit_rate', index=$build.light_cone.superimposition - 1)"],
                self._TABLES, s=s)
            assert math.isclose(params["p"], want), f"叠影 {s} 应取第 {s} 档"

    def test_unknown_table_rejected(self):
        with pytest.raises(ValueError, match="未知表"):
            self._eval(["self.p = lookup_table('nope', index=0)"], self._TABLES)

    def test_index_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="越界"):
            self._eval(["self.p = lookup_table('crit_rate', index=9)"], self._TABLES)

    def test_bad_statement_shape_rejected(self):
        with pytest.raises(ValueError, match="语句形态非法"):
            self._eval(["other.p = 1"], self._TABLES)


# ---------------------------------------------------------------------------
# 模板键闸
# ---------------------------------------------------------------------------

class TestEquipmentTemplateGates:
    def _tmp_root(self, tmp_path, kind, name, doc):
        d = tmp_path / kind
        d.mkdir(parents=True)
        (d / name).write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        return [str(tmp_path)]

    def test_light_cone_unknown_key_rejected(self, tmp_path):
        roots = self._tmp_root(tmp_path, "light_cones", "99002_坏光锥.yaml", {
            "light_cone_id": "99002", "name": "坏", "rarity": 5, "path": "Destruction",
            "base_stats": {"hp": 1, "atk": 1, "def": 1}, "passive": {}})
        from hsr_nous.sim_schema.actor import StatBlock
        with pytest.raises(ValueError, match="未知键 'passive'"):
            BuildCompiler()._merge_light_cone(
                StatBlock(), {"light_cone_template": "99002"}, roots=roots, actor_id="hero")

    def test_relic_piece_unknown_key_rejected(self, tmp_path):
        roots = self._tmp_root(tmp_path, "relics", "991_坏套装.yaml", {
            "relic_set_id": "991", "name": "坏套装",
            "set_2pc": {"desc": "x", "stat_effects": {"atk_pct": 0.1}, "hook": []}})
        with pytest.raises(ValueError, match="未知键 'hook'"):
            BuildCompiler()._merge_relic_sets(
                {"relics": {"head": {"set_id": "991"}, "hands": {"set_id": "991"}}},
                roots=roots, actor_id="hero", hooks_out=[])


# ---------------------------------------------------------------------------
# 全链路：光锥叠影 buff + 套装 4pc 条件效果
# ---------------------------------------------------------------------------

def _member(**kw):
    m = {"character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 20},
         "actions": [
             {"action_id": "b", "name": "普攻", "action_type": "basic", "target_type": "single",
              "damage_type": "physical", "scaling": [{"atk": 1.0}]},
             {"action_id": "u", "name": "终结", "action_type": "ultimate", "target_type": "single",
              "damage_type": "physical", "scaling": [{"atk": 1.5}], "energy_cost": 20}]}
    m.update(kw)
    return m


def _ally():
    return {"character_template": "inline", "actor_id": "ally2", "name": "队友", "level": 80,
            "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 20},
            "actions": [
                {"action_id": "b2", "name": "普攻", "action_type": "basic", "target_type": "single",
                 "damage_type": "physical", "scaling": [{"atk": 1.0}]}]}


def _stage(av=400.0):
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": av}}}


def _run(member, extra_team=None, av=400.0):
    team = [member] + (extra_team or [])
    build = {"build": {"team": team, "policy": {
        "name": "p", "action_rules": [
            {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _stage(av), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    return eng, eng.run()


class TestLightConeMechanics:
    def test_superimposition_binding_and_hook(self):
        """叠影 3：白值并入 + 绑定参数查表 0.15 + 进战 buff 烘焙该值."""
        eng, state = _run(_member(
            light_cone_template="99001", light_cone={"level": 80, "superimposition": 3}))
        hero = state.actors["hero"]
        assert math.isclose(hero.actor.stats.hp, 3000 + 1000), "光锥白值并入"
        assert math.isclose(eng._binding_params["hero"]["crit_rate_param"], 0.15), "叠 3 取第 3 档"
        mod = hero.modifiers.get("TEST_LC_CRIT")
        assert mod is not None and math.isclose(mod.stat_effects["crit_rate"], 0.15), (
            "进战 buff 的 stat 值经 `$self.crit_rate_param` 现场求值烘焙")

    def test_no_light_cone_no_params(self):
        eng, _state = _run(_member())
        assert eng._binding_params.get("hero") is None


class TestRelicSetMechanics:
    def test_2pc_stat_and_4pc_hook(self):
        """2pc 纯数值照常；4pc 条件效果：装备者终结技后暴伤 +25%，队友终结技不触发."""
        relics = {slot: {"set_id": "990"} for slot in ("head", "hands", "body", "feet")}
        applied = []
        eng, state = _run(_member(relics=relics), extra_team=[_ally()])
        hero = state.actors["hero"]
        ally = state.actors["ally2"]
        assert any(m.modifier_id == "RELIC_990_2PC" for m in
                   eng._initial_modifiers.get("hero", [])), "2pc stat_effects 转初始 Modifier"
        assert math.isclose(hero.actor.stats.crit_dmg, 0.5), "4pc 是条件效果——开局面板不含"
        assert "TEST_SET_4PC_CRITDMG" in hero.modifiers, "装备者终结技触发 4pc"
        assert math.isclose(hero.modifiers["TEST_SET_4PC_CRITDMG"].stat_effects["crit_dmg"], 0.25)
        assert "TEST_SET_4PC_CRITDMG" not in ally.modifiers, (
            "hook owner=装备者——队友不享受；条件 $self.actor_id==$event.source 防蹭队友终结技")

    def test_2pc_only_below_4(self):
        """只穿 2 件：2pc 生效、4pc hook 不登记（计数闸）."""
        relics = {slot: {"set_id": "990"} for slot in ("head", "hands")}
        eng, state = _run(_member(relics=relics))
        hero = state.actors["hero"]
        assert "TEST_SET_4PC_CRITDMG" not in hero.modifiers
        assert any(m.modifier_id == "RELIC_990_2PC" for m in
                   eng._initial_modifiers.get("hero", []))
