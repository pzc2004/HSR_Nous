"""开拓者•同谐 8006（星/playergirl3）模板端到端对轴（验收型批）：真模板 YAML → 编译 →
伴舞/超击破转化敌数档/随波逐流削韧/天赋回能/剧院之帽延后/行迹/星魂全链 → 手算全等.

口径常数：8006 atk 446.292、crit 0.05/0.5（期望暴击区 1.025）、spd 105、max_energy 140；
行迹 BE +0.373、虚数增伤 +0.144（增伤区 1.144）、效果抵抗 +0.10；
假人 def 1000 → 防御区 1000/(1000+200+10×80)=0.5、虚数弱点 → 抗性区 1.0、
未击破 base_universal 0.9 / 已击破 1.0、max_toughness 100 → 击破基数 (0.5+100/40)=3.0；
超击破基数 376.75533×有效削韧（=3767.5533/10）；虚数击破系数 0.5、禁锢推条 0.55。
伴舞 lv10：BE +0.30；超击破转化敌数档 1.6/1.4/1.2（≤1/≤3/>3 名——02_damage_formula
§2.11 + hsr-optimizer + 米游社 54367648 实测表三层对轴；2 敌 = 1.4，1 敌 = 1.6）；
卫我起舞官方 params 五档（2 敌 = +0.5，1 敌 = +0.6）。
（cid 8006=星；同人物另一实体 8005=穹——不得简称互替。）
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 446.292
DMG_ZONE = 1.144          # 行迹虚数增伤（0.032+0.048+0.064）
BE_TRACE = 0.373          # 行迹击破特攻（0.053×2+0.08×2+0.107）
DEF_ZONE = 0.5
CRIT_EXP = 1.025          # 0.05×1.5 + 0.95
SB_BASE = 3767.5533 / 10  # 超击破基数系数

SKILL_HIT = ATK * 0.5 * DMG_ZONE * DEF_ZONE * 0.9 * CRIT_EXP              # lv10 未击破单段
BOUNCE_HIT = ATK * 0.5 * DMG_ZONE * DEF_ZONE * 1.0 * CRIT_EXP             # 已击破单段（弹射）
SB_BOUNCE = SB_BASE * 5 * (1 + BE_TRACE + 0.3) * 1.4 * 1.5 * DEF_ZONE     # 弹射超击破（BE 0.673，2敌 1.4/+0.5）
BREAK_DMG = 3767.5533 * 0.5 * 3.0 * (1 + BE_TRACE + 0.3) * DEF_ZONE       # 虚数击破伤害
SKILL_HIT_LV12 = ATK * 0.55 * DMG_ZONE * DEF_ZONE * 0.9 * CRIT_EXP        # E3 lv12 档 0.55
BASIC_HIT_LV7 = ATK * 1.1 * DMG_ZONE * DEF_ZONE * 0.9 * CRIT_EXP          # E5 普攻 6+1=7 档 1.1
ALLY_SB = (1500 * DEF_ZONE * CRIT_EXP * 1.0
           + SB_BASE * 10 * (1 + 0.3) * 1.4 * 1.5 * DEF_ZONE)             # 辅手已击破直伤+光环超击破（BE 0.3）


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8006", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "imaginary",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8006", "technique": "800607"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人2", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

_STAGE_1 = {"stage": {"stage_id": "s1", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, stage=None):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle),
                             stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _tb(eng):
    return eng.state.actors["8006"]


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


def _ult(eng):
    st = _tb(eng)
    st.current_energy = 140.0
    ult = next(a for a in eng.actions_by_actor["8006"] if a.action_id == "800603")
    assert eng._fire_ultimate(st, ult) is True


class TestTrailblazerCompile:
    def test_actions_resources_path(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["8006"]}
        assert acts == {"800601", "800602", "800603"}, "800606 战斗外攻击不落 actions"
        decls = compiled.resource_decls_by_actor["8006"]
        assert decls["_e1_used"]["max"] == 1

    def test_trace_panels(self, compiled):
        """行迹百分比节点：BE +0.373 / 效果抵抗 +0.10 / 虚数增伤 +0.144（勘正⑨）."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_tb(eng))
        assert math.isclose(eff["break_effect"], BE_TRACE, rel_tol=1e-9)
        assert math.isclose(eff["effect_res"], 0.10, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("imaginary", 0.0), DMG_ZONE - 1, rel_tol=1e-9)
        assert math.isclose(eff["spd"], 105.0, rel_tol=1e-9)
        assert eff.get("super_break_modifier", 0.0) == 0.0, "无伴舞 = 无转化源（池 0 不出超击破）"


class TestUltBackupDancer:
    def test_backup_dancer_aura_and_pools(self, compiled):
        """伴舞：单实例挂 8006 + team 光环辐射（辅手吃 BE 不持实例）；2 敌档转化 1.4/增伤 +0.5."""
        eng = _make(compiled)
        st = _tb(eng)
        _ult(eng)
        assert math.isclose(st.current_energy, 5.0), "140 扣尽 + 返还 5（米游社）"
        assert "BACKUP_DANCER" in st.modifiers and "BACKUP_DANCER_SB" in st.modifiers
        bd = st.modifiers["BACKUP_DANCER"]
        assert (bd.duration, bd.tick_anchor, bd.effect_scope) == (3, "owner_turn_start", "team"), (
            "官方「持续 3 回合，开拓者每次回合开始 -1」= 持有者 8006 回合开始走字")
        ally = eng.state.actors["ally"]
        assert "BACKUP_DANCER" not in ally.modifiers, "team 光环辐射不落实例"
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE + 0.3, rel_tol=1e-9), "开拓者 BE = 行迹 0.373 + 伴舞 lv10 0.30"
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.30, rel_tol=1e-9), "辅手经光环吃 BE"
        for aid in ("8006", "ally"):
            eff = eng.pipeline.effective_stats(eng.state.actors[aid])
            assert math.isclose(eff["super_break_modifier"], 1.4, rel_tol=1e-9), "2 敌档转化 1.4"
            assert math.isclose(eff["super_break_dmg_boost"], 0.5, rel_tol=1e-9), "卫我起舞 2 敌档 +0.5"

    def test_single_enemy_tier(self):
        """敌数分档现场求值：1 敌档转化 1.6 / 卫我起舞 +0.6（stat_exprs enemies_alive）."""
        eng = _make(_compiled(stage=_STAGE_1))
        _ult(eng)
        eff = eng.pipeline.effective_stats(_tb(eng))
        assert math.isclose(eff["super_break_modifier"], 1.6, rel_tol=1e-9)
        assert math.isclose(eff["super_break_dmg_boost"], 0.6, rel_tol=1e-9)


class TestSkill:
    def test_skill_first_hit_efficiency_and_bounces(self, compiled):
        """战技：首段削韧 10×2（随波逐流 hit_condition skill scoped）+ 弹射 4×5 → 总削 40；
        5 段全打 e1（expected 确定化按序取首），单段 117.7474 = atk×0.5×1.144×0.5×0.9×1.025."""
        eng = _make(compiled)
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8006", "800602")
        assert math.isclose(hp - tgt.current_hp, 5 * SKILL_HIT, rel_tol=1e-6), (
            "首段 + 4 弹射同倍率（lv10 #1=0.5）")
        assert math.isclose(tgt.toughness, 60.0, rel_tol=1e-9), (
            "100 - (10×2 随波逐流 + 4×5 弹射) = 60——弹射伪行动 follow_up 自然出集")
        assert math.isclose(st.current_energy, 30.0), "战技回能 30（米游社 6×5 合计）"
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点（tbgd 权威）"


class TestBreakChain:
    def test_break_talent_delay_super_break(self, compiled):
        """击破全链：伴舞在身 + 韧性 15 → 战技首段击破 → 天赋回 10 / 禁锢 0.55 + 剧院之帽
        0.3 推条 / 击破伤害 4727.34 / 4 弹射逐段超击破 3309.14；辅手跟打吃光环超击破."""
        eng = _make(compiled)
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        _ult(eng)                                   # energy 5
        tgt.toughness = 15.0
        before = _remaining(eng, "e1")
        hp = tgt.current_hp
        _cast(eng, "8006", "800602")
        assert tgt.broken, "首段 20 削韧击破"
        assert math.isclose(_remaining(eng, "e1") - before, 8500.0, rel_tol=1e-9), (
            "虚数禁锢 0.55（+5500）+ 剧院之帽 0.3（+3000）独立相加")
        assert math.isclose(st.current_energy, 45.0, rel_tol=1e-9), (
            "5 + 30 战技 + 10 天赋（lv10 param(800604,1)）")
        chain = SKILL_HIT + BREAK_DMG + 4 * (BOUNCE_HIT + SB_BOUNCE)
        assert math.isclose(hp - tgt.current_hp, chain, rel_tol=1e-6), (
            "首段直伤 117.75 + 击破 4727.34 + 4×(弹射直伤 130.83 + 超击破 3309.14) = 18604.95")
        hp2 = tgt.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp2 - tgt.current_hp, ALLY_SB, rel_tol=1e-6), (
            "辅手直伤 768.75（已击破 1.0）+ 光环超击破 5142.71（BE 0.3×转化 1.4×增伤 1.5）= 5911.46")


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技 即刻！独奏团：进战我方全体 BE +30%、持续 2 回合（单档字面值）."""
        eng = _make(_compiled(pre_battle=True))
        st = _tb(eng)
        assert "TECH_SOLO_SPOTLIGHT" in st.modifiers
        assert st.modifiers["TECH_SOLO_SPOTLIGHT"].duration == 2
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE + 0.3, rel_tol=1e-9), "0.373 行迹 + 0.30 秘技"
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["break_effect"],
                            0.30, rel_tol=1e-9)


class TestEidolons:
    def test_e1_first_skill_refund(self):
        """E1 您的最佳观众席：首次战技净耗 0（耗 1 返 1，_e1_used 闩）；第二次不返."""
        eng = _make(_compiled(eidolon=1))
        _cast(eng, "8006", "800602")
        assert math.isclose(eng.state.skill_points, 3.0), "首次战技耗 1 + 返 1 = 净 0"
        assert math.isclose(_tb(eng).resources["_e1_used"], 1.0)
        _cast(eng, "8006", "800602")
        assert math.isclose(eng.state.skill_points, 2.0), "闩已落——第二次只耗不返"

    def test_e2_err(self):
        """E2 越狱的跨洋彩虹：开战 ERR +25%（energy_regen 1.0→1.25，勘正②键名）；
        普攻回能 20×1.25 = 25."""
        eng = _make(_compiled(eidolon=2))
        st = _tb(eng)
        assert "E2_ERR" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["energy_regen"],
                            1.25, rel_tol=1e-9)
        _cast(eng, "8006", "800601")
        assert math.isclose(st.current_energy, 25.0, rel_tol=1e-9)

    def test_e3_skill_lv12_and_talent_lv12(self):
        """E3 休止符的疗养院（E1..E3 联动——E2 ERR 1.25 同入算）：战技 lv12 档 0.55
        （5 段 ×129.522 = 647.611）；天赋 lv12 回 11 → 击破后 37.5+13.75 = 51.25."""
        eng = _make(_compiled(eidolon=3))
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8006", "800602")
        assert math.isclose(hp - tgt.current_hp, 5 * SKILL_HIT_LV12, rel_tol=1e-6)
        assert math.isclose(tgt.toughness, 60.0, rel_tol=1e-9)
        st.current_energy = 0.0
        tgt.toughness = 15.0
        _cast(eng, "8006", "800602")
        assert math.isclose(st.current_energy, 30 * 1.25 + 11 * 1.25, rel_tol=1e-9), (
            "战技 30×1.25 + 天赋 lv12 11×1.25 = 51.25——幻视族谱⑱ 联动取档")

    def test_e4_team_be_live_tracking(self):
        """E4 袒护白鸽的冠冕：队友 BE = 0.15×8006 现场 BE（stat_exprs + stat_of 动态——
        开大前 0.15×0.373 = 0.05595；开大后 0.3 伴舞 + 0.15×0.673 = 0.40095）；自身不吃."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.15 * BE_TRACE, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.30 + 0.15 * (BE_TRACE + 0.3), rel_tol=1e-9), (
            "伴舞 BE 实时入 8006 面板再折算（非条件件可读）")
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE + 0.3, rel_tol=1e-9), "官方「除自身以外」——8006 不受 E4"

    def test_e5_ult_lv12_and_basic_lv7(self):
        """E5 包庇旧节拍的诗：伴舞 BE 实取 lv12 档 0.33（开拓者 0.703）；
        普攻 6+1=7 档在表内（1.1——勘正⑪非钳表尾），单段 259.044."""
        eng = _make(_compiled(eidolon=5))
        st = _tb(eng)
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE + 0.33, rel_tol=1e-9), "param(800603,3) lv12 = 0.33"
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8006", "800601")
        assert math.isclose(hp - tgt.current_hp, BASIC_HIT_LV7, rel_tol=1e-6)

    def test_e6_six_bounces(self):
        """E6 明天，栖息聚光之下（联动 E3 lv12 档 0.55）：弹射 4→6 段——7 段全中 e1
        总伤 906.655，削韧 20+6×5 = 50."""
        eng = _make(_compiled(eidolon=6))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8006", "800602")
        assert math.isclose(hp - tgt.current_hp, 7 * SKILL_HIT_LV12, rel_tol=1e-6)
        assert math.isclose(tgt.toughness, 50.0, rel_tol=1e-9)
