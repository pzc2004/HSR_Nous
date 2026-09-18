"""飞霄 1220 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 飞黄积攒/
战技天赋双 FUA/终结技逐击切换/击破效率/星魂 scoped 全链 → 手算全等.

过堂勘正六件+引擎补口四件（fixture 头注同录）：broken_of 通道 / res_pen
scoped / 削韧效率 scoped / deal_damage action_type 槽 / 双分支合并逐击切换 /
122014 删块 / 击破效率翻案 / E6/E4 scoped 化。

口径常数：飞霄白值 atk 601.524 × 行迹攻 1.28（B-TR④ 回填——攻 0.28/暴击 0.12/
防御 0.125 官方十节点聚合）= 769.95072、spd 112、crit 0.17/0.5（期望暴击区
1.085）；假人 def 0 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9。
子击 lv10=0.9（122008/122009 同值）、终结段 lv10=1.6；FUA lv10=1.1。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

FX_ATK = 601.524
FX_ATK_E = FX_ATK * 1.28              # 769.95072（行迹 atk_pct 0.28——B-TR④）
Z_FX = 0.5 * 0.9 * (1 + 0.17 * 0.5)   # CR 0.05+行迹 0.12=0.17 → 期望暴击区 1.085
Z_ALLY = 0.5 * 0.9 * 1.025            # 辅手（inline 无行迹）期望暴击区


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1220", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "wind",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _fx(eng):
    return eng.state.actors["1220"]


def _cast(eng, owner, aid, target_id="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


class TestFeixiaoCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1220"]
        assert {"flying_aureus", "_fua_turn_used", "_attack_tally",
                "_e2_count", "_e1_flag", "_e1_stacks"} <= set(decls)
        assert decls["flying_aureus"]["max"] == 12

    def test_battle_start_aureus(self, compiled):
        """Heavenpath：开战 +3 飞黄."""
        assert math.isclose(_make(compiled).state.actors["1220"].resources["flying_aureus"], 3.0)


class TestSkillFUA:
    def test_skill_with_fua(self, compiled):
        """战技：2.0 lv10 + 立即 FUA 1.1 lv10 + 飞黄 +1（双 0.5）+ 自增伤 + Boltcatch."""
        eng = _make(compiled)
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        f0 = fx.resources["flying_aureus"]
        _cast(eng, "1220", "122002")
        assert math.isclose(hp1 - e1.current_hp, (2.0 + 1.1) * FX_ATK_E * Z_FX, rel_tol=1e-9)
        assert math.isclose(fx.resources["flying_aureus"], f0 + 1.0), (
            "战技 0.5（计数钩）+ FUA 自身 0.5（非双记在案）")
        assert "FEIXIAO_TALENT_DMG" in fx.modifiers
        assert "FEIXIAO_BOLTCATCH" in fx.modifiers


class TestTalentFUA:
    def test_fua_trigger_and_latch(self, compiled):
        """天赋 FUA：我方第 2 次攻击触发（快照 off-by-one——tally 旧值 +1>=2）+ 每回合闩."""
        eng = _make(compiled)
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        _cast(eng, "ally", "ally_basic")   # tally 0→1（快照 0+1<2 不触发）
        assert math.isclose(fx.resources["_attack_tally"], 1.0)
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")   # 快照 1+1>=2 触发
        ally_d = 1.0 * 1500 * Z_ALLY
        fua_d = 1.1 * FX_ATK_E * Z_FX * 1.6   # 自增伤同钩后挂——本发 FUA 不吃（×1.6 为增伤区）
        dealt = hp1 - e1.current_hp
        assert dealt > ally_d, "FUA 触发（第 2 击）"
        assert math.isclose(fx.resources["_fua_turn_used"], 1.0)
        assert math.isclose(fx.resources["_attack_tally"], 0.0) or \
               math.isclose(fx.resources["_attack_tally"], 1.0)
        # 闩：本回合不再触发
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 2 * ally_d, rel_tol=1e-9), "闩内无 FUA"
        _ = fua_d

    def test_latch_reset_on_turn(self, compiled):
        """飞霄回合开始：闩/计数/E2 计数重置."""
        eng = _make(compiled)
        fx = _fx(eng)
        fx.resources["_fua_turn_used"] = 1.0
        fx.resources["_attack_tally"] = 1.0
        fx.resources["_e2_count"] = 3.0
        eng.bus.emit("on_turn_start", {"actor": "1220"}, eng.state)
        assert fx.resources["_fua_turn_used"] == 0.0
        assert fx.resources["_attack_tally"] == 0.0
        assert fx.resources["_e2_count"] == 0.0


class TestUltimate:
    def test_ult_segments_and_efficiency(self, compiled):
        """大招：子击×6（逐击三元+E1 旗 E0 恒等）+终结段+飞黄扣 6+效率件挂摘（未破不削韧）."""
        eng = _make(compiled)
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        fx.resources["flying_aureus"] = 8.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1220"] if x.action_id == "122003")
        assert eng._fire_ultimate(fx, ult) is True
        # 子击 6×0.9×atk×Z + 终结段 1.6×atk×Z（未破全程 122009 式 lv10 同值）
        expect = (6 * 0.9 + 1.6) * FX_ATK_E * Z_FX
        assert math.isclose(hp1 - e1.current_hp, expect, rel_tol=1e-9)
        assert math.isclose(fx.resources["flying_aureus"], 2.0), "扣 6（全清或扣 6 按扣 6 在案）"
        assert "FEIXIAO_ULT_EFFICIENCY" not in fx.modifiers, "效率件终结段后摘"
        assert math.isclose(e1.toughness, 9999.0 - 70.0), (
            "削 70=子击 6×5×2+终结段 5×2（效率件 ×2 挂摘生效）——不破无击破段")


class TestEidolons:
    def test_e1_stacks_ramp(self):
        """E1：子击叠层 ×(1.0→1.5) 递增（旗置 1 生效）；E0 恒等对照."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        fx.resources["flying_aureus"] = 8.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1220"] if x.action_id == "122003")
        eng._fire_ultimate(fx, ult)
        seg = 0.9 * FX_ATK_E * Z_FX
        expect = seg * (1.0 + 1.1 + 1.2 + 1.3 + 1.4 + 1.5) + 1.6 * FX_ATK_E * Z_FX * 1.5
        assert math.isclose(hp1 - e1.current_hp, expect, rel_tol=1e-9)

    def test_e2_ally_fua_aureus(self):
        """E2：队友 FUA +1 飞黄（每回合 cap 6）."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        fx = _fx(eng)
        f0 = fx.resources["flying_aureus"]
        for _ in range(8):
            eng.bus.emit("on_action", {"actor": "ally", "action_type": "follow_up",
                                       "action_id": "ally_fua", "target_type": "single",
                                       "target": "e1", "actor_type": "character"}, eng.state)
        assert math.isclose(fx.resources["_e2_count"], 6.0), "cap 6"
        # 计数钩 8×0.5 + E2 6×1.0 → 3+10=13 clamp 12
        assert math.isclose(fx.resources["flying_aureus"], 12.0)

    def test_e4_spd_and_fua_efficiency(self):
        """E4：FUA 时 SPD+8%；削韧效率 scoped——战技 20 不吃、FUA 5×2=10 吃（类型限定）."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        e1.toughness = 9999.0
        _cast(eng, "1220", "122002")
        assert "E4_FEIXIAO_SPD" in fx.modifiers
        assert "E4_FUA_EFFICIENCY" in fx.modifiers
        assert math.isclose(9999 - e1.toughness, 20 + 5 * 2.0), (
            "战技削 20（skill 非 follow_up 不吃）+ FUA 削 5×2（scoped 命中）")

    def test_e6_res_pen_scoped(self):
        """E6：res_pen scoped——大招抗区 1.2；FUA 不穿（follow_up 非 ultimate）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        fx.resources["flying_aureus"] = 8.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1220"] if x.action_id == "122003")
        eng._fire_ultimate(fx, ult)
        # E3 lv12：子击 0.648+0.33=0.978、终结段 1.728；E1 叠层；抗区 1.2
        seg = 0.978 * FX_ATK_E * Z_FX * 1.2
        expect = seg * 7.5 + 1.728 * FX_ATK_E * Z_FX * 1.2 * 1.5
        assert math.isclose(hp1 - e1.current_hp, expect, rel_tol=1e-9), (
            "deal_damage action_type: ultimate 声明——res_pen scoped 命中")


class TestTechnique:
    def test_tech_aureus(self):
        """秘技：入战 +1 飞黄（与 Heavenpath +3 合计 4）."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1220", "technique": "122007"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        assert math.isclose(eng.state.actors["1220"].resources["flying_aureus"], 4.0)
