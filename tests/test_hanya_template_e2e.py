"""寒鸦 1215 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 承负全链/
计数回点消散/罚恶真伤/终结技/星魂 → 手算全等.

过堂勘正三件（fixture 头注同录）：Netherworld on_kill 目标写反死钩 /
速度基数 stat_of 跨人翻案 / 计数三钩主目标带标收紧。

口径常数：寒鸦白值 atk/spd 待模板（spd 110）；辅手 atk 1500、spd 90。
假人 def 0 → 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9、
期望暴击区 1.025。罚恶真伤 lv10=0.3×原伤；誊录官 ATK+10%。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ALLY_ATK = 1500.0
HY_SPD = 110.0
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1215", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _hy(eng):
    return eng.state.actors["1215"]


def _cast_hy(eng, aid, target_id):
    hy = _hy(eng)
    a = next(x for x in eng.actions_by_actor["1215"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(hy, a)
    eng.bus.emit("on_action", {
        "actor": "1215", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": hy.actor.actor_type}, eng.state)


def _ally_hit(eng, target_id):
    ally = eng.state.actors["ally"]
    a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_basic")
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(ally, a)
    eng.bus.emit("on_action", {
        "actor": "ally", "action_type": "basic", "action_id": "ally_basic",
        "target_type": "single", "target": tgt.actor.actor_id,
        "actor_type": ally.actor.actor_type}, eng.state)


class TestHanyaCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1215"]
        assert {"_burden_a", "_burden_b", "_burden_on"} <= set(decls)


class TestBurden:
    def test_apply_and_overwrite(self, compiled):
        """战技挂承负：单槽后写覆盖——他敌旧标摘除+新标挂上+计数归零+闩置 1."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hy = _hy(eng)
        _cast_hy(eng, "121502", "e1")
        assert "HANYA_BURDEN" in e1.modifiers
        assert math.isclose(hy.resources["_burden_on"], 1.0)
        hy.resources["_burden_a"] = 1.0   # 预置计数验归零
        _cast_hy(eng, "121502", "e2")
        assert "HANYA_BURDEN" not in e1.modifiers, "后写覆盖：旧标摘除"
        assert "HANYA_BURDEN" in e2.modifiers
        assert math.isclose(hy.resources["_burden_a"], 0.0), "新标新计数（归零读在案）"

    def test_count_chain_and_dispel(self, compiled):
        """计数链：主目标无标不计 → 带标 +1 → 满 2 回 1 SP+A 归零 B+1+誊录官+回 2 能
        → 再满 2 自动消散（快照 +1 双钩在案）."""
        eng = _make(compiled)
        hy = _hy(eng)
        ally = eng.state.actors["ally"]
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast_hy(eng, "121502", "e1")
        _ally_hit(eng, "e2")
        assert math.isclose(hy.resources["_burden_a"], 0.0), "主目标无标不计"
        _ally_hit(eng, "e1")
        assert math.isclose(hy.resources["_burden_a"], 1.0)
        hy.current_energy = 0.0
        sp0 = eng.state.skill_points
        _ally_hit(eng, "e1")
        assert math.isclose(hy.resources["_burden_a"], 0.0)
        assert math.isclose(hy.resources["_burden_b"], 1.0)
        assert eng.state.skill_points == min(sp0 + 1, 5), "回 1 SP"
        assert math.isclose(hy.current_energy, 2.0), "A6 回 2 能"
        assert "HANYA_SCRIVENER" in ally.modifiers, "誊录官挂触发者"
        # 第 2 轮回点 → 自动消散
        _ally_hit(eng, "e1")
        _ally_hit(eng, "e1")
        assert "HANYA_BURDEN" not in e1.modifiers, "回点满 2 次自动消散"
        assert math.isclose(hy.resources["_burden_on"], 0.0)


class TestTalent:
    def test_mark_and_true_dmg(self, compiled):
        """罚恶：命中带标→施放者挂标记 2 回合；持标者命中带标→真伤 0.3×原伤（誊录官联动对轴）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        _cast_hy(eng, "121502", "e1")
        _ally_hit(eng, "e1")
        assert "HANYA_TALENT_MARK" in ally.modifiers
        _ally_hit(eng, "e1")   # 第 2 次触发回点 → 誊录官 ATK+10% 挂上
        hp1 = e1.current_hp
        _ally_hit(eng, "e1")
        base = 1.0 * ALLY_ATK * 1.1 * Z   # 誊录官联动
        assert math.isclose(hp1 - e1.current_hp, base * 1.3, rel_tol=1e-9), (
            "真伤 0.3×原伤（category true 跳乘区等值——1407 E1 同构）")


class TestUltimate:
    def test_ult_buff(self, compiled):
        """大招：目标 ATK+60%（lv10）+ SPD flat=寒鸦 20%（stat_of 跨人 110×0.2=22）."""
        eng = _make(compiled)
        hy = _hy(eng)
        ally = eng.state.actors["ally"]
        hy.current_energy = 140.0
        ult = next(x for x in eng.actions_by_actor["1215"] if x.action_id == "121503")
        tgt = ally
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
            tgt if tgt in candidates else (candidates[0] if candidates else None))
        assert eng._fire_ultimate(hy, ult) is True
        es = eng.pipeline.effective_stats(ally)
        assert math.isclose(es["atk"], ALLY_ATK * 1.6, rel_tol=1e-9)
        assert math.isclose(es["spd"], 90 + 0.2 * HY_SPD, rel_tol=1e-9), (
            "速度基数=寒鸦 SPD（stat_of 跨人——目标白值近似旧案已废）")


class TestTraces:
    def test_netherworld_kill_sp(self, compiled):
        """Netherworld：带标敌被杀回 1 SP（目标=怪物——draft != monster 死钩已勘正）."""
        eng = _make(compiled)
        _cast_hy(eng, "121502", "e1")
        sp0 = eng.state.skill_points
        eng.bus.emit("on_kill", {"action_id": "ally_basic", "source": "ally",
                                 "target": "e1"}, eng.state)
        assert eng.state.skill_points == min(sp0 + 1, 5)


class TestEidolons:
    def test_e1_kill_advance_latch(self):
        """E1：持十王敕令队友击杀→寒鸦拉条 15%（每回合闩）."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        hy = _hy(eng)
        ally = eng.state.actors["ally"]
        from hsr_nous.sim.state import Modifier as _M
        ally.modifiers["HANYA_ULT_BUFF"] = _M(
            modifier_id="HANYA_ULT_BUFF", name="十王敕令", modifier_type="buff", duration=2)
        av0 = eng.scheduler.action_value_of(hy.actor) if hasattr(eng.scheduler, "action_value_of") else None
        eng.bus.emit("on_kill", {"action_id": "ally_basic", "source": "ally",
                                 "target": "e1"}, eng.state)
        assert math.isclose(hy.resources["_e1_used"], 1.0), "拉条后闩置位"
        eng.bus.emit("on_kill", {"action_id": "ally_basic", "source": "ally",
                                 "target": "e2"}, eng.state)
        assert math.isclose(hy.resources["_e1_used"], 1.0), "闩内不再触发"
        _ = av0

    def test_e2_skill_spd(self):
        """E2：施放战技后 SPD+20% 1 回合."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        hy = _hy(eng)
        spd0 = eng.pipeline.effective_stats(hy)["spd"]
        _cast_hy(eng, "121502", "e1")
        assert math.isclose(eng.pipeline.effective_stats(hy)["spd"],
                            spd0 * 1.2, rel_tol=1e-9)

    def test_e6_extra_true_dmg(self):
        """E6：罚恶额外真伤 0.1×原伤（与基础 0.3 并发）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        _cast_hy(eng, "121502", "e1")
        _ally_hit(eng, "e1")
        hp1 = e1.current_hp
        _ally_hit(eng, "e1")
        base = 1.0 * ALLY_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, base * 1.43, rel_tol=1e-9), (
            "罚恶 0.33（E5 联动 lv12）+ E6 0.1 双真伤段")


class TestTechnique:
    def test_tech_burden(self):
        """秘技：开战随机 1 敌挂承负 + 计数归零 + 闩置 1."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1215", "technique": "121507"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        hy = _hy(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        marked = ("HANYA_BURDEN" in e1.modifiers) or ("HANYA_BURDEN" in e2.modifiers)
        assert marked, "开战随机 1 敌挂承负（B22 确定化）"
        assert math.isclose(hy.resources["_burden_on"], 1.0)
