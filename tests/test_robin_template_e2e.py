"""知更鸟 1309 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 行迹面板/天赋光环/战技
增伤/终结技拉条/回能经济/秘技/星魂全链 → 手算全等.

口径常数：知更鸟白值 atk 640.332 / hp 1280.664 / spd 102（行迹 +5 → 107）/ crit 0.05/0.5 /
max_energy 160；行迹 atk_pct 0.28 / hp_pct 0.18 → 有效 atk 819.62496 / hp 1511.18352；
天赋暴伤光环 lv10 = 0.2 → 双方暴伤 0.7；辅手 atk 1500。
假人 def 1000 → 防御区 0.5；物理/火弱点匹配 → 抗性区 1.0；未击破 0.9；
期望暴击区 = 1 + 0.05×0.7 = 1.035（E5 后 1 + 0.05×0.73 = 1.0365）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK_BASE = 640.332
HP_BASE = 1280.664
ATK_EFF = ATK_BASE * 1.28          # 819.62496（行迹 atk_pct 0.28）
HP_EFF = HP_BASE * 1.18            # 1511.18352（行迹 hp_pct 0.18）
DEF_RES = 0.5                      # 假人 def 1000 → (80×10+200)/(1000+1000)
UNBROKEN = 0.9                     # 未击破减伤区
CD_LV10 = 0.5 + 0.2                # 天赋 lv10 暴伤光环
CRIT_EXP = 1 + 0.05 * CD_LV10      # 1.035
CD_LV12 = 0.5 + 0.23               # E5 天赋 lv12
CRIT_EXP_E5 = 1 + 0.05 * CD_LV12   # 1.0365


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1309", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "战技", "action_type": "skill",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "skill_point_cost": 1},
                     {"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1},
                     {"action_id": "ally_bless", "name": "祝福", "action_type": "skill",
                      "target_type": "ally_single", "damage_type": "none",
                      "skill_point_cost": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1309", "technique": "130907"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical", "fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical", "fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _robin(eng):
    return eng.state.actors["1309"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, *, eidolon_energy: float = 160.0):
    st = _robin(eng)
    st.current_energy = eidolon_energy
    ult = next(a for a in eng.actions_by_actor["1309"] if a.action_id == "130903")
    assert eng._fire_ultimate(st, ult) is True


class TestRobinCompile:
    def test_actions_and_defaults(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1309"]}
        assert acts == {"130901", "130902", "130903", "130906"}
        ult = next(a for a in compiled.actions_by_actor["1309"] if a.action_id == "130903")
        assert ult.energy_cost == 160
        basic = next(a for a in compiled.actions_by_actor["1309"] if a.action_id == "130901")
        assert len(basic.scaling) == 10 and basic.skill_point_gain == 1
        robin_actor = next(a for a in compiled.build_team if a.actor_id == "1309")
        assert robin_actor.skill_levels == {
            "basic": 6, "skill": 10, "ultimate": 10, "talent": 10}


class TestBattleStartAuras:
    def test_trace_panel_and_talent_aura(self, compiled):
        """行迹面板（atk×1.28/hp×1.18/spd 107）+ 天赋暴伤光环 lv10=0.2 双方同吃."""
        eng = _make(compiled)
        robin, ally = _robin(eng), eng.state.actors["ally"]
        st = eng.pipeline.effective_stats(robin)
        assert math.isclose(st["atk"], ATK_EFF, rel_tol=1e-9), "行迹 atk_pct 0.28"
        assert math.isclose(st["hp"], HP_EFF, rel_tol=1e-9), "行迹 hp_pct 0.18"
        assert math.isclose(st["spd"], 107.0, rel_tol=1e-9), "行迹速度节点 +5 烘焙"
        assert math.isclose(st["crit_dmg"], CD_LV10, rel_tol=1e-9), "天赋光环（自身持有）"
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"],
                            CD_LV10, rel_tol=1e-9), "天赋光环 team 辐射辅手"
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 1500.0), "辅手不吃行迹"
        assert "ROBIN_TALENT_CD" in robin.modifiers

    def test_a1_advance_25(self, compiled):
        """华彩花腔：进战自身行动提前 25%（剩余距离 10000-2500=7500；队友不动）."""
        eng = _make(compiled)
        assert math.isclose(_remaining(eng, "1309"), 7500.0, rel_tol=1e-9)
        assert math.isclose(_remaining(eng, "ally"), 10000.0, rel_tol=1e-9)


class TestSkillAria:
    def test_cost_energy_buff_and_tick(self, compiled):
        """战技：SP 3→2；回能 30+A3 行迹 5=35（目标自身——天赋回能不误触）；
        增伤 0.5 双方同吃；owner_turn_start 走 3 字到期."""
        eng = _make(compiled, initial_sp=3)
        robin, ally = _robin(eng), eng.state.actors["ally"]
        _cast(eng, "1309", "130902", target=robin)
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 SP"
        assert math.isclose(robin.current_energy, 35.0), "30+5——天赋 +2 不误触（勘正②）"
        mod = robin.modifiers["ROBIN_SKILL_DMG"]
        assert mod.duration == 3 and mod.tick_anchor == "owner_turn_start"
        assert mod.effect_scope == "team"
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"]["all"], 0.5, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(robin)["dmg_bonus"]["all"], 0.5, rel_tol=1e-9)
        for expect in (2, 1):
            eng._tick_modifiers(robin, "owner_turn_start")
            assert robin.modifiers["ROBIN_SKILL_DMG"].duration == expect
        eng._tick_modifiers(robin, "owner_turn_start")
        assert "ROBIN_SKILL_DMG" not in robin.modifiers, "3 字走完到期"
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0), 0.0)


class TestBasicWhiteNoise:
    def test_damage_sp_energy_toughness(self, compiled):
        """普攻 lv6=1.0：819.62496×1.0×0.5×1.0×0.9×1.035=381.74032512；产 1 SP；回能 20+2."""
        eng = _make(compiled, initial_sp=3)
        robin, e1 = _robin(eng), eng.state.actors["e1"]
        hp0, sp0 = e1.current_hp, eng.state.skill_points
        _cast(eng, "1309", "130901")
        expected = ATK_EFF * 1.0 * DEF_RES * 1.0 * UNBROKEN * CRIT_EXP
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-9), (
            "白值×倍率×防御区×抗性区×未击破×期望暴击 手算全等")
        assert math.isclose(e1.toughness, 90.0), "削韧 10（物理弱点匹配）"
        assert math.isclose(eng.state.skill_points, sp0 + 1.0), "产 1 SP"
        assert math.isclose(robin.current_energy, 22.0), "20 + 天赋 2（命中敌方触发）"

    def test_skill_dmg_zone_flows_into_basic(self, compiled):
        """战技增伤 0.5 并入增伤区：819.62496×1.5×0.5×1.0×0.9×1.035=572.61048768."""
        eng = _make(compiled)
        robin, e1 = _robin(eng), eng.state.actors["e1"]
        _cast(eng, "1309", "130902", target=robin)
        hp0 = e1.current_hp
        _cast(eng, "1309", "130901")
        expected = ATK_EFF * 1.0 * 1.5 * DEF_RES * 1.0 * UNBROKEN * CRIT_EXP
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-9)


class TestTalentEnergyTriggerDomain:
    def test_ally_attack_triggers_support_does_not(self, compiled):
        """触发域：我方攻击命中敌方 +2（含插入式 FUA）；对友方施放辅助不触发."""
        eng = _make(compiled)
        robin, ally = _robin(eng), eng.state.actors["ally"]
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(robin.current_energy, 2.0), "辅手普攻命中 → +2"
        _cast(eng, "ally", "ally_bless", target=ally)
        assert math.isclose(robin.current_energy, 2.0), "对友方施放 → 不触发（目标过滤）"
        ally_basic = next(a for a in eng.actions_by_actor["ally"] if a.action_id == "ally_basic")
        eng.decision.select_target = lambda s, t, c, e: eng.state.actors["e1"]
        eng.trigger_action(ally, ally_basic, tag="test")   # 插入式攻击（FUA 同通道）
        assert math.isclose(robin.current_energy, 4.0), "插入式攻击同触发（勘正②——去 insert 排除）"


class TestUltimateOpus:
    def test_energy_refund_and_team_advance(self, compiled):
        """终结技：160 全扣 + 返还 5；除 Robin 外全体立即行动（剩余距离→0）；自身/敌方不动."""
        eng = _make(compiled)
        robin = _robin(eng)
        assert math.isclose(_remaining(eng, "1309"), 7500.0)   # A1 已提前
        _ult(eng)
        assert math.isclose(robin.current_energy, 5.0), "160 扣尽返还 5——天赋不误触（target self）"
        assert math.isclose(_remaining(eng, "ally"), 0.0), "队友立即行动"
        assert math.isclose(_remaining(eng, "1309"), 7500.0), "Robin 自身不拉（官方排除）"
        assert _remaining(eng, "e1") > 0.0, "敌方不受影响"


class TestTechniqueOverture:
    def test_pre_battle_latch_and_wave_energy(self):
        """秘技：进战 latch TECH_DRUNK_OVERTURE；转波回能 5（单挂——勘正⑧ 双挂已拆）."""
        eng = _make(_compiled(pre_battle=True))
        robin = _robin(eng)
        assert "TECH_DRUNK_OVERTURE" in robin.modifiers
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(robin.current_energy, 5.0), "每波 +5——双挂则 +10 必炸"
        eng.bus.emit("on_wave_start", {"wave_index": 2}, eng.state)
        assert math.isclose(robin.current_energy, 10.0)

    def test_no_pre_battle_no_latch(self, compiled):
        """未用秘技：无 latch、转波不回能（钩未注册）."""
        eng = _make(compiled)
        robin = _robin(eng)
        assert "TECH_DRUNK_OVERTURE" not in robin.modifiers
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(robin.current_energy, 0.0)


class TestEidolons:
    def test_e2_talent_energy_plus1(self):
        """E2：天赋回能 2+1=3（辅手命中 → 3；Robin 自普攻 20+3=23）."""
        eng = _make(_compiled(eidolon=2))
        robin = _robin(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(robin.current_energy, 3.0), "天赋 2 + E2 1"
        _cast(eng, "1309", "130901")
        assert math.isclose(robin.current_energy, 3.0 + 23.0)

    def test_e3_skill_lv12(self):
        """E3 战技+2 → lv12 实取 param(130902,1)=0.55（族谱#18 联动）."""
        eng = _make(_compiled(eidolon=3))
        robin = _robin(eng)
        _cast(eng, "1309", "130902", target=robin)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["dmg_bonus"]["all"],
                            0.55, rel_tol=1e-9), "lv12 档 0.55"

    def test_e4_ult_dispels_cc_all_allies(self):
        """E4：终结技驱散双方全部控制类（无个数限制——勘正③）；普通 debuff 保留."""
        eng = _make(_compiled(eidolon=4))
        robin, ally = _robin(eng), eng.state.actors["ally"]
        for st in (robin, ally):
            eng._apply_modifier(st, Modifier(
                modifier_id="FRZ", name="冻结", modifier_type="control",
                control_kind="freeze", duration=2))
            eng._apply_modifier(st, Modifier(
                modifier_id="FRZ2", name="禁锢", modifier_type="control",
                control_kind="imprison", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="SHRED", name="减防", modifier_type="debuff", duration=2))
        _ult(eng)
        for st in (robin, ally):
            assert "FRZ" not in st.modifiers and "FRZ2" not in st.modifiers, (
                "控制类全摘（$mod.kind == 'control'，勘正④）")
        assert "SHRED" in ally.modifiers, "非控制类 debuff 不误摘"

    def test_e5_basic_lv7_talent_lv12(self):
        """E5：普攻+1 → lv7 实取 1.1（勘正⑥——非 lv10 表尾）；天赋+2 → 暴伤 0.23.
        普攻期望 = 819.62496×1.1×0.5×1.0×0.9×1.0365."""
        eng = _make(_compiled(eidolon=5))
        robin, e1 = _robin(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(robin)["crit_dmg"],
                            CD_LV12, rel_tol=1e-9), "天赋 lv12 光环 0.23"
        hp0 = e1.current_hp
        _cast(eng, "1309", "130901")
        expected = ATK_EFF * 1.1 * DEF_RES * 1.0 * UNBROKEN * CRIT_EXP_E5
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-9), (
            "lv7 档 1.1 + lv12 暴伤 0.73 期望暴击区 1.0365")

    def test_e6_full_linkage(self):
        """E6 全联动（E3+E5 同激活）：战技 0.55 / 暴伤 0.73 / 普攻 lv7——E6 本体待收不误件."""
        eng = _make(_compiled(eidolon=6))
        robin, e1 = _robin(eng), eng.state.actors["e1"]
        _cast(eng, "1309", "130902", target=robin)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["dmg_bonus"]["all"],
                            0.55, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(robin)["crit_dmg"],
                            CD_LV12, rel_tol=1e-9)
        hp0 = e1.current_hp
        _cast(eng, "1309", "130901")
        expected = ATK_EFF * 1.1 * 1.55 * DEF_RES * 1.0 * UNBROKEN * CRIT_EXP_E5
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-9), (
            "增伤 0.55 并入 + lv7 倍率 + lv12 暴伤 三段联动")
