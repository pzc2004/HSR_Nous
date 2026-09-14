"""灵砂 1222 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 浮元召唤/
行动次数账挂忆师/治疗 ATK 基数/BEFOG scoped/余烬回响/星魂全链 → 手算全等.

过堂勘正六件（fixture 头注同录）：BEFOG vulnerability+break scoped / E1 效率
翻案 / 治疗 ATK 基数表达式展开×4 / 浮元账挂忆师 / 白值动态化 / 余烬回响
血线近似在案。

口径常数：灵砂白值 atk 679.14、crit 0.05/0.5（期望暴击区 1.025）；假人
def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9。浮元继承灵砂白值
（伤害基数=stat_of($self.summoner_id, 'atk') 动态）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

LS_ATK = 679.14
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1222", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ls(eng):
    return eng.state.actors["1222"]


def _cast_skill(eng):
    ls = _ls(eng)
    a = next(x for x in eng.actions_by_actor["1222"] if x.action_id == "122202")
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(ls, a)
    eng.bus.emit("on_action", {
        "actor": "1222", "action_type": "skill", "action_id": "122202",
        "target_type": "aoe", "target": "e1",
        "actor_type": ls.actor.actor_type}, eng.state)


def _fuyuan_act(eng):
    fy = eng.state.actors["1222_fuyuan"]
    a = next(x for x in eng.actions_by_actor["1222_fuyuan"] if x.action_id == "122204")
    eng._execute_action(fy, a)
    eng.bus.emit("on_action", {
        "actor": "1222_fuyuan", "action_type": "follow_up", "action_id": "122204",
        "target_type": "aoe", "target": "e1",
        "actor_type": fy.actor.actor_type}, eng.state)


class TestLingshaCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1222"]
        assert {"_fy_count", "_fy_on_field", "_echo_cd"} <= set(decls)
        assert decls["_fy_count"]["max"] == 5


class TestSkill:
    def test_skill_summon_and_heal(self, compiled):
        """战技：全体 0.8 lv10 + 召唤浮元+3 次 + 全体治疗 0.14×atk+420（ATK 基数钉）."""
        eng = _make(compiled)
        ls = _ls(eng)
        ally = eng.state.actors["ally"]
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        ally.current_hp = 1000.0
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast_skill(eng)
        assert math.isclose(hp1 - e1.current_hp, 0.8 * LS_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.8 * LS_ATK * Z, rel_tol=1e-9)
        assert math.isclose(ally.current_hp, 1000 + 0.14 * LS_ATK + 420, rel_tol=1e-9), (
            "ATK 基数（表达式展开——非 hp_scaling）")
        assert "1222_fuyuan" in eng.state.actors
        assert math.isclose(ls.resources["_fy_count"], 3.0)


class TestFuyuan:
    def test_fuyuan_action_and_count(self, compiled):
        """浮元行动：全体+随机 2×0.75 lv10 + 驱散 + 治疗 + 次数-1 账挂忆师."""
        eng = _make(compiled)
        _cast_skill(eng)
        ls = _ls(eng)
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        ally.current_hp = 1000.0
        hp1 = e1.current_hp
        _fuyuan_act(eng)
        assert math.isclose(hp1 - e1.current_hp, 2 * 0.75 * LS_ATK * Z, rel_tol=1e-9), (
            "全体 0.75 + 随机单体 0.75（确定化同序首）")
        assert math.isclose(ally.current_hp, 1000 + 0.12 * LS_ATK + 360, rel_tol=1e-9)
        assert math.isclose(ls.resources["_fy_count"], 2.0), "次数扣在灵砂账（账挂忆师）"
        assert "_fy_count" not in eng.state.actors["1222_fuyuan"].resources, (
            "浮元自身无分账（draft 死挂已废）")

    def test_dismiss_at_zero(self, compiled):
        """行动次数归 0 即消失：alive=False + _fy_on_field=0 + dismiss（actor_exit）."""
        eng = _make(compiled)
        _cast_skill(eng)
        ls = _ls(eng)
        ls.resources["_fy_count"] = 1.0
        _fuyuan_act(eng)
        assert eng.state.actors["1222_fuyuan"].alive is False, "归 0 dismiss"
        assert math.isclose(ls.resources["_fy_on_field"], 0.0)
        assert math.isclose(ls.resources["_fy_count"], 0.0)


class TestUltimate:
    def test_ult_befog_heal(self, compiled):
        """大招：全体 1.5 lv10 + 全体治疗 + BEFOG（scoped break）+ 浮元立即行动."""
        eng = _make(compiled)
        _cast_skill(eng)
        ls = _ls(eng)
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        ally.current_hp = 1000.0
        ls.current_energy = 110.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1222"] if x.action_id == "122203")
        assert eng._fire_ultimate(ls, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 1.5 * LS_ATK * Z, rel_tol=1e-9)
        assert math.isclose(ally.current_hp, 1000 + 0.12 * LS_ATK + 360, rel_tol=1e-9)
        m = e1.modifiers["BEFOG"]
        assert m.hit_condition_expr is not None, "BEFOG 是 break scoped 件（类型限定）"
        assert math.isclose(m.stat_effects["vulnerability"], 0.25)


class TestEcho:
    def test_echo_trigger_and_cd(self, compiled):
        """余烬回响：受击者 ≤60% 触发浮元追击（全体+随机）不耗次数 + 冷却 2."""
        eng = _make(compiled)
        _cast_skill(eng)
        ls = _ls(eng)
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        ally.current_hp = 1000.0   # 33% ≤60%
        count0 = ls.resources["_fy_count"]
        hp1 = e1.current_hp
        eng.bus.emit("on_hp_decrease", {
            "amount": 300.0, "source": "e1", "reason": "hit", "target": "ally",
            "damage_type": "fire", "action_type": "basic"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 2 * 0.75 * LS_ATK * Z, rel_tol=1e-9), (
            "浮元追击全体+随机（不耗行动次数）")
        assert math.isclose(ls.resources["_fy_count"], count0), "不耗次数"
        assert math.isclose(ls.resources["_echo_cd"], 2.0)
        # 冷却中不触发
        hp1 = e1.current_hp
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit", "target": "ally",
            "damage_type": "fire", "action_type": "basic"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 0.0), "冷却中不触发"


class TestEidolons:
    def test_e1_efficiency(self):
        """E1：自身击破效率 +50%（永续件）."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        m = _ls(eng).modifiers["E1_SELF_EFFICIENCY"]
        assert math.isclose(m.stat_effects["break_efficiency_boost"], 0.5)

    def test_e2_team_be(self):
        """E2：终结技全队击破特攻 +40% 3 回合."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        ls = _ls(eng)
        ls.current_energy = 110.0
        ally = eng.state.actors["ally"]
        ult = next(x for x in eng.actions_by_actor["1222"] if x.action_id == "122203")
        eng._fire_ultimate(ls, ult)
        assert math.isclose(
            eng.pipeline.effective_stats(ally)["break_effect"], 0.4, rel_tol=1e-9)

    def test_e4_fuyuan_heal_lowest(self):
        """E4：浮元行动时奶当前 HP 最低队友 0.4×atk."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        ls = _ls(eng)
        ally = eng.state.actors["ally"]
        ls.current_hp = 300.0   # 灵砂血最少
        ally.current_hp = 2000.0
        _fuyuan_act(eng)
        # E3 联动：天赋 lv12（灵砂 E3=ultimate+2、talent+2——浮元奶 lv12 档
        # 0.128×atk+400.5=487.43）+ E4 奶 0.4×atk（星魂固定值不随档）
        assert math.isclose(
            ls.current_hp, 300 + (0.128 * LS_ATK + 400.5) + 0.4 * LS_ATK, rel_tol=1e-9), (
            "浮元全体奶 lv12 + E4 奶最低（order_by $it.hp take 1——$self.atk 动态）")


class TestTechnique:
    def test_tech_summon_befog(self):
        """秘技：进战召唤浮元+3 次 + 全体 BEFOG 2 回合."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1222", "technique": "122207"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        ls = _ls(eng)
        e1 = eng.state.actors["e1"]
        assert "1222_fuyuan" in eng.state.actors
        assert math.isclose(ls.resources["_fy_count"], 3.0)
        assert "BEFOG" in e1.modifiers
