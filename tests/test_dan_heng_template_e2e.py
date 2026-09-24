"""丹恒 1002 全机制模板端到端对轴（打标 staging 过堂收编版）：真模板 YAML → 编译
→ 行迹/战技减速/天赋/终结技追加/大风/星魂 E2-E6 全链 → 手算全等.

过堂收编四件（打标稿误判通道缺，引擎现状可组出）：天赋 on_become_target（白厄 140804
同族）/ 战技暴击减速（is_critical 载荷——2026-09-12 通道落地首个角色级实例）/
终结技 Slowed 追加与大风（真伤压缩口径，遐蝶 E1 等值先例）。

口径常数：丹恒白值 atk 546.84、行迹 atk_pct 0.18 → 有效攻击 645.2712；行迹风伤 0.224
→ 风伤区 1.224；假人 def 0 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9；
暴击 0.05/0.5 → 期望暴击区 1.025。默认档：basic 6 / skill 10 / ult 10（index=等级-1）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK_EFF = 546.84 * 1.18               # 645.2712（行迹 atk_pct 0.18 同池）
WIND = 1.224                          # 行迹风伤节点
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.05 * 0.5             # 1.025
ZONES = DEF_RES * UNBROKEN * CRIT_EXP * WIND
SKILL_DMG = ATK_EFF * 2.6 * ZONES     # 战技 lv10 主倍率 2.6
ULT_DMG = ATK_EFF * 4.0 * ZONES       # 终结技 lv10 基础倍率 4.0
BASIC_DMG = ATK_EFF * 1.0 * ZONES     # 普攻 lv6 倍率 1.0
ULT_TRUE = ULT_DMG * (1.2 / 4.0)      # 终结技追加 = #2/#1×原伤害（lv10 0.3）
GALE_TRUE = BASIC_DMG * 0.4           # 大风 +40% 真伤压缩


def _build(*, eidolon: int = 0, pre_battle=None):
    member = {"character_template": "1002", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 4000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "辅助", "action_type": "skill",
                      "target_type": "ally_single", "damage_type": "fire",
                      "scaling": [], "toughness_dmg": 0}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled, *, mode=MODE_EXPECTED, seed=None):
    kw = {"seed": seed} if seed is not None else {}
    eng = CombatEngine.from_compiled(compiled, mode=mode, initial_energy_ratio=0.0, **kw)
    eng.setup()
    return eng


def _dh(eng):
    return eng.state.actors["1002"]


def _cast(eng, owner, aid, *, target=None):
    """手动施放（_execute_action 不发 on_action——由调用方补发，同 _run_turn 口径）；
    有指向目标时先钉 _pick_ally_target（ally_single 寻址通道）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng._pick_ally_target = lambda attacker=None: tgt
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


class TestDanHengCompile:
    def test_resources_actions_trace(self, compiled):
        assert "_talent_cd" in compiled.resource_decls_by_actor["1002"]
        acts = {a.action_id: a for a in compiled.actions_by_actor["1002"]}
        assert acts["100201"].skill_point_gain == 1 and acts["100201"].energy_gain == 20
        assert acts["100202"].skill_point_cost == 1 and acts["100202"].energy_gain == 30
        assert acts["100203"].energy_cost == 100
        assert [round(d["atk"], 2) for d in acts["100201"].scaling[:2]] == [0.5, 0.6]
        assert round(acts["100202"].scaling[9]["atk"], 2) == 2.6, "战技 lv10=2.6（index=9）"
        assert round(acts["100203"].scaling[9]["atk"], 1) == 4.0, "终结技 lv10=4.0"
        a = compiled.build_team[0]
        assert a.stats.dmg_bonus.get("wind") == 0.224, "行迹风伤节点入白值面板"


class TestSkillSlow:
    def test_crit_skill_applies_slow(self, compiled):
        """战技暴击 → 目标减速 -12% 2 回合（is_critical 载荷；roll 必暴用 crit 件拉满）."""
        eng = _make(compiled, mode=MODE_ROLL, seed=7)
        dh, e1 = _dh(eng), eng.state.actors["e1"]
        eng._apply_modifier(dh, Modifier(
            modifier_id="CRIT_SURE", name="必暴", modifier_type="buff", duration=0,
            stat_effects={"crit_rate": 1.0}))
        _cast(eng, "1002", "100202")
        slow = e1.modifiers.get("DANHENG_SLOW")
        assert slow is not None, "暴击战技未挂减速"
        assert math.isclose(slow.stat_effects["spd_pct"], -0.12), "lv10 #2：-12%"
        assert math.isclose(slow.duration, 2.0), "lv10 #3：2 回合"

    def test_non_crit_skill_no_slow(self, compiled):
        eng = _make(compiled, mode=MODE_EXPECTED)   # 期望模式无离散暴击
        _cast(eng, "1002", "100202")
        assert "DANHENG_SLOW" not in eng.state.actors["e1"].modifiers


class TestTalent:
    def test_become_target_arms_res_pen_and_cooldown(self, compiled):
        """被友方技能指向 → 下一次攻击风抗穿 +36% + 冷却 2 回合（on_become_target 收编）."""
        eng = _make(compiled)
        dh = _dh(eng)
        _cast(eng, "ally", "ally_skill", target=dh)
        assert "DH_RES_PEN_ARMED" in dh.modifiers, "被友方指向未武装"
        assert math.isclose(dh.modifiers["DH_RES_PEN_ARMED"].stat_effects["res_pen"], 0.36)
        assert math.isclose(dh.resources["_talent_cd"], 2.0), "冷却 #2=2 回合"
        # 下一次攻击消耗
        _cast(eng, "1002", "100201")
        assert "DH_RES_PEN_ARMED" not in dh.modifiers, "攻击后未消耗武装"
        # 冷却中（cd=2）再指不触发
        _cast(eng, "ally", "ally_skill", target=dh)
        assert "DH_RES_PEN_ARMED" not in dh.modifiers, "冷却中误触发"
        # 冷却递减两回合清零 → 可再触发
        for expect in (1.0, 0.0):
            eng.bus.emit("on_turn_start", {"actor": "1002"}, eng.state)
            assert math.isclose(dh.resources["_talent_cd"], expect)
        _cast(eng, "ally", "ally_skill", target=dh)
        assert "DH_RES_PEN_ARMED" in dh.modifiers, "冷却清零未再武装"

    def test_e2_cooldown_one(self):
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        dh = _dh(eng)
        _cast(eng, "ally", "ally_skill", target=dh)
        assert math.isclose(dh.resources["_talent_cd"], 1.0), "E2：冷却 2→1（后注册覆盖）"


class TestUltimateAndGale:
    def _slowed_eng(self, compiled):
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="DANHENG_SLOW", name="疾雨·减速", modifier_type="debuff",
            duration=2, stat_effects={"spd_pct": -0.12}))
        return eng, e1

    def test_ult_true_append_on_slowed(self, compiled):
        """终结技打 Slowed 目标：基础 4.0 全等对轴 + 真伤追加 0.3×原伤害."""
        eng, e1 = self._slowed_eng(compiled)
        dh = _dh(eng)
        dh.current_energy = 100.0
        hp0 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1002"] if a.action_id == "100203")
        assert eng._fire_ultimate(dh, ult) is True
        assert math.isclose(hp0 - e1.current_hp, ULT_DMG + ULT_TRUE, rel_tol=1e-9), (
            "基础段全等（atk_eff×4.0×乘区）+ 追加真伤 0.3×原伤害")

    def test_gale_true_append_on_slowed_basic(self, compiled):
        """大风：普攻对 Slowed 目标 +40% 真伤压缩."""
        eng, e1 = self._slowed_eng(compiled)
        hp0 = e1.current_hp
        _cast(eng, "1002", "100201")
        assert math.isclose(hp0 - e1.current_hp, BASIC_DMG + GALE_TRUE, rel_tol=1e-9)

    def test_no_append_without_slow(self, compiled):
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1002", "100201")
        assert math.isclose(hp0 - e1.current_hp, BASIC_DMG, rel_tol=1e-9), (
            "无 Slowed 不追加（大风/终结技同闸）")


class TestEidolon4And6:
    def test_e4_kill_acts_again(self, compiled):
        """E4：终结技击杀 → 立即再动（advance_action 100 承载——额外回合语义待实测在案）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        dh, e1 = _dh(eng), eng.state.actors["e1"]
        e1.current_hp = 1.0
        dh.current_energy = 100.0
        ult = next(a for a in eng.actions_by_actor["1002"] if a.action_id == "100203")
        assert eng._fire_ultimate(dh, ult) is True and not e1.alive
        rem = eng.scheduler._remaining[eng.scheduler._handles["1002"]]
        assert math.isclose(rem, 0.0), "E4 击杀后行动提前 100%（remaining 归零）"

    def test_e6_slow_stacks_to_minus_20(self, compiled):
        """E6：战技减速 -12%→-20%（加算双件同池）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled, mode=MODE_ROLL, seed=7)
        dh, e1 = _dh(eng), eng.state.actors["e1"]
        eng._apply_modifier(dh, Modifier(
            modifier_id="CRIT_SURE", name="必暴", modifier_type="buff", duration=0,
            stat_effects={"crit_rate": 1.0}))
        _cast(eng, "1002", "100202")
        eff = eng.pipeline.effective_stats(e1)
        assert math.isclose(eff["spd"], e1.actor.stats.spd * (1 - 0.20), rel_tol=1e-9)


class TestTechnique:
    def test_technique_atk_buff(self):
        b = _build(pre_battle=[{"actor_id": "1002", "technique": "100207"}])
        compiled = compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        dh = _dh(eng)
        eff = eng.pipeline.effective_stats(dh)
        assert math.isclose(eff["atk"], 546.84 * (1 + 0.18 + 0.4), rel_tol=1e-9), (
            "秘技 ATK+40% 与行迹 18% 同池加算（3 回合）")
