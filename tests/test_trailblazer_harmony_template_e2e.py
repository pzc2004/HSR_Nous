"""开拓者•同谐 8005 模板端到端对轴（staging→fixtures 验收型批）：真模板 YAML → 编译 →
伴舞超击破全链/卫我起舞阶梯/随波逐流段覆写/剧院之帽推条/天赋回能/E1-E6 → 手算全等.

口径常数：开拓者 atk 446.292、crit 0.05/0.5（期望暴击区 1.025）、行迹击破 +0.373 /
虚数增伤 +0.144 / 效抵 +0.10、max_energy 140；假人 def 1000 → 防御区 0.5、弱点匹配 →
抗性区 1.0、未击破虚弱区 0.9、已击破 1.0；超击破基数 376.75533×有效削韧；伴舞转化
敌数分档 ≤1/≤3/>3 → 1.6/1.4/1.2（双版本裁决采 8006 读法：docs/mechanics 02 §2.11 +
hsr-optimizer + 米游社实测三层对轴，本台 2 敌=1.4）、卫我起舞 2 敌 +0.5；
火击破自带推条 25%（+2500），剧院之帽 +30%（+3000）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 446.292              # 开拓者白值（管线实值）
DMG_IMG = 0.144            # 行迹虚数增伤聚合（0.032+0.048+0.064）
BE_TRACE = 0.373           # 行迹击破特攻聚合（0.053×2+0.08×2+0.107）
DEF_ZONE = 0.5             # 假人 def 1000：1000/(1000+200+10×80)
CRIT_EXP = 1.025           # 期望暴击区 1+0.05×0.5
SB_BASE = 3767.5533 / 10   # 超击破基数系数
DIRECT_LV6 = ATK * 1.0 * (1 + DMG_IMG) * DEF_ZONE * 0.9 * CRIT_EXP      # 普攻 lv6 未击破直伤
SKILL_HIT = ATK * 0.5 * (1 + DMG_IMG) * DEF_ZONE * 0.9 * CRIT_EXP       # 战技单段 lv10 未击破直伤
SKILL_HIT_BROKEN = ATK * 0.5 * (1 + DMG_IMG) * DEF_ZONE * 1.0 * CRIT_EXP  # 战技单段 lv10 已击破直伤


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8005", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8005", "technique": "800507"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary", "fire"]},
    {"actor_id": "e2", "name": "假人2", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary", "fire"]}],
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


def _tb(eng):
    return eng.state.actors["8005"]


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
    ult = next(a for a in eng.actions_by_actor["8005"] if a.action_id == "800503")
    assert eng._fire_ultimate(st, ult) is True


class TestTBCompile:
    def test_actions_resources_and_trace_panel(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["8005"]}
        assert acts == {"800501", "800502", "800503"}
        decls = compiled.resource_decls_by_actor["8005"]
        assert decls["_e1_used"]["max"] == 1
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_tb(eng))
        assert math.isclose(eff["break_effect"], BE_TRACE, rel_tol=1e-9), "行迹击破 +37.3%"
        assert math.isclose(eff["dmg_bonus"]["imaginary"], DMG_IMG, rel_tol=1e-9), "行迹虚数伤 +14.4%"
        assert math.isclose(eff["effect_res"], 0.10, rel_tol=1e-9), "行迹效抵 +10%"


class TestBasic:
    def test_basic_damage_sp_energy(self, compiled):
        """普攻 lv6=1.0×atk：直伤 235.4949；SP 3→4；回能 20；削韧 10."""
        eng = _make(compiled)
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8005", "800501")
        assert math.isclose(hp - tgt.current_hp, DIRECT_LV6, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点"
        assert math.isclose(st.current_energy, 20.0), "回能 20"
        assert math.isclose(tgt.toughness, 90.0), "削韧 10"


class TestSkill:
    def test_skill_five_hits_and_shuffle_toughness(self, compiled):
        """战技 lv10=0.5×atk：首段指定 + 4 段随机（期望模式全中 e1）共 5×117.747；
        削韧 = 首段 20（随波逐流 10×(1+100%) 段 0 覆写）+ 4×5 = 40；耗 1 点；回能 30."""
        eng = _make(compiled)
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8005", "800502")
        assert math.isclose(hp - tgt.current_hp, 5 * SKILL_HIT, rel_tol=1e-9), (
            "首段+4 弹射同倍率 0.5（param(800502,1) lv10）")
        assert math.isclose(tgt.toughness, 60.0), "100-20-4×5=40 削韧总量"
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点"
        assert math.isclose(st.current_energy, 30.0), "回能 30（6/段×5 合流）"


class TestTalentAndHatTrace:
    def test_break_energy_and_hat_delay(self, compiled):
        """辅手火击破 e1：天赋 lv10 → 开拓者回能 10；剧院之帽 → 延后 30%（+3000），
        与火击破自带 25%（+2500）独立相加 +5500."""
        eng = _make(compiled)
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        before = _remaining(eng, "e1")
        _cast(eng, "ally", "ally_basic")
        assert tgt.broken, "火击破落位"
        assert math.isclose(st.current_energy, 10.0), "天赋 lv10 回能 10"
        assert math.isclose(_remaining(eng, "e1") - before, 5500.0, rel_tol=1e-9), (
            "击破自带 25%（+2500）+ 剧院之帽 30%（+3000）——加算形式与官方同向，合并口径待实测")


class TestUltBackupDancer:
    def test_backup_dancer_team_panels(self, compiled):
        """伴舞 lv10：双方 BE +0.3（开拓者 0.673/辅手 0.3）+ 转化敌数分档（2 敌=1.4）全队 +
        卫我起舞 2 敌 +0.5；持续 3、锚 owner_turn_start；开大后能量 5."""
        eng = _make(compiled)
        _ult(eng)
        st = _tb(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(st.current_energy, 5.0), "140 扣尽 + 返还 5"
        mod = st.modifiers["BACKUP_DANCER"]
        assert mod.duration == 3 and mod.tick_anchor == "owner_turn_start"
        assert mod.effect_scope == "team"
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE + 0.3, rel_tol=1e-9), "开拓者 BE = 行迹 0.373 + 伴舞 0.3"
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.3, rel_tol=1e-9), "辅手 BE = 伴舞 0.3（team 光环辐射）"
        for aid in ("8005", "ally"):
            eff = eng.pipeline.effective_stats(eng.state.actors[aid])
            assert math.isclose(eff["super_break_modifier"], 1.4, rel_tol=1e-9), (
                "伴舞超击破转化敌数分档：2 敌 ≤3 → 1.4（双版本裁决采 8006 读法）")
            assert math.isclose(eff["super_break_dmg_boost"], 0.5, rel_tol=1e-9), (
                "卫我起舞 2 敌 +50%（stat_exprs 现场求值）")

    def test_dance_ladder_tracks_enemy_count(self, compiled):
        """卫我起舞阶梯随敌数现场变：e2 阵亡 → 1 敌 +60%."""
        eng = _make(compiled)
        _ult(eng)
        e2 = eng.state.actors["e2"]
        e2.current_hp = 1.0
        _cast(eng, "8005", "800501", target=e2)   # 收掉 e2 → 场上 1 敌
        assert not e2.alive
        for aid in ("8005", "ally"):
            eff = eng.pipeline.effective_stats(eng.state.actors[aid])
            assert math.isclose(eff["super_break_dmg_boost"], 0.6, rel_tol=1e-9), (
                "1 敌 +60%（0.7-0.1×min(1,5)）")


class TestSuperBreakChain:
    def test_skill_on_broken_triggers_super_break(self, compiled):
        """伴舞在位 + e1 已击破：战技 5 击各带超击破——首段削韧 20（随波逐流）、
        弹射各 5；SB = 基数×削韧×(1+BE 0.673)×转化 1.4（2 敌档）×卫我起舞 1.5×防御 0.5."""
        eng = _make(compiled)
        _ult(eng)
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")          # 辅手火击破（开拓者天赋回 10 能）
        assert tgt.broken
        hp = tgt.current_hp
        _cast(eng, "8005", "800502")
        be_multi = 1 + BE_TRACE + 0.3             # 1.673（伴舞 0.3 已挂）
        sb_first = SB_BASE * 20 * be_multi * 1.4 * 1.5 * DEF_ZONE
        sb_bounce = SB_BASE * 5 * be_multi * 1.4 * 1.5 * DEF_ZONE
        expect = 5 * SKILL_HIT_BROKEN + sb_first + 4 * sb_bounce
        assert math.isclose(hp - tgt.current_hp, expect, rel_tol=1e-9), (
            "5×直伤 130.83 + 首段 SB 13236.54 + 4×弹射 SB 3309.14（转化 1.4 敌数档）")


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：进战全体 BE +30% 持续 2 回合（开拓者 0.673 / 辅手 0.3）."""
        eng = _make(_compiled(pre_battle=True))
        for aid, expect in (("8005", BE_TRACE + 0.3), ("ally", 0.3)):
            st = eng.state.actors[aid]
            assert "INSTANT_CHORUS" in st.modifiers
            assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                                expect, rel_tol=1e-9)


class TestEidolons:
    def test_e1_first_skill_refund(self):
        """E1：首次战技返 1 点（耗 1 返 1 净 0）；闩一次性——第二次不再返."""
        eng = _make(_compiled(eidolon=1))
        _cast(eng, "8005", "800502")
        assert math.isclose(eng.state.skill_points, 3.0), "首次战技 3-1+1=3"
        assert math.isclose(_tb(eng).resources["_e1_used"], 1.0)
        _cast(eng, "8005", "800502")
        assert math.isclose(eng.state.skill_points, 2.0), "闩已落：3-1=2"

    def test_e2_err_three_turns(self):
        """E2：开战 ERR +25% 3 回合（基值 1.0 加算）——普攻回能 20×1.25=25."""
        eng = _make(_compiled(eidolon=2))
        st = _tb(eng)
        assert "E2_ERR" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["energy_regen"],
                            1.25, rel_tol=1e-9)
        _cast(eng, "8005", "800501")
        assert math.isclose(st.current_energy, 25.0), "20×1.25"

    def test_e3_skill_talent_lv12(self):
        """E3：战技/天赋 lv12——单段 0.55×atk（首段+4 弹射同档）；击破回能 11
        （eidolon=3 联动 E2 → ERR 1.25：能量 (30+11)×1.25=51.25）."""
        eng = _make(_compiled(eidolon=3))
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8005", "800502")
        hit_lv12 = ATK * 0.55 * (1 + DMG_IMG) * DEF_ZONE * 0.9 * CRIT_EXP
        assert math.isclose(hp - tgt.current_hp, 5 * hit_lv12, rel_tol=1e-9), (
            "lv12=0.55 首段与弹射 param() 同随档")
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(st.current_energy, (30 + 11.0) * 1.25), (
            "(战技 30 + 天赋 lv12=11) × E2 联动 ERR 1.25——幻视族谱⑱ 联动取档")

    def test_e4_dove_dynamic_be_share(self):
        """E4：辅手 BE += 开拓者 BE×15%（stat_of 现场读无条件件面板——含行迹/伴舞，
        排除自身；开拓者自身不吃）."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        ally = eng.state.actors["ally"]
        assert "E4_DOVE" in ally.modifiers and "E4_DOVE" not in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.15 * BE_TRACE, rel_tol=1e-9), "未开大：0.15×0.373"
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_TRACE, rel_tol=1e-9), "开拓者自身不吃 E4"
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.3 + 0.15 * (BE_TRACE + 0.3), rel_tol=1e-9), (
            "开大后：伴舞 0.3 + 0.15×0.673（stat_exprs 现场求值）")

    def test_e5_ult_lv12_and_basic_lv7(self):
        """E5：终结技 lv12 → 伴舞 BE +33%（开拓者 0.703）；普攻 lv7=1.1×atk."""
        eng = _make(_compiled(eidolon=5))
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(_tb(eng))["break_effect"],
                            BE_TRACE + 0.33, rel_tol=1e-9), "lv12 #3=0.33 随档"
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8005", "800501")
        basic_lv7 = ATK * 1.1 * (1 + DMG_IMG) * DEF_ZONE * 0.9 * CRIT_EXP
        assert math.isclose(hp - tgt.current_hp, basic_lv7, rel_tol=1e-9), "普攻 lv6+1=lv7 档 1.1"

    def test_e6_six_bounces_and_energy_42(self):
        """E6（联动 E1-E5：战技 lv12=0.55、ERR 1.25）：战技 7 击（首段+6 弹射）、
        削韧 20+6×5、能量 (30+12)×1.25=52.5."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "8005", "800502")
        hit_lv12 = ATK * 0.55 * (1 + DMG_IMG) * DEF_ZONE * 0.9 * CRIT_EXP
        assert math.isclose(hp - tgt.current_hp, 7 * hit_lv12, rel_tol=1e-9), (
            "首段+4+2 弹射共 7 击（E3 联动 lv12 档）")
        assert math.isclose(tgt.toughness, 50.0), "100-20-6×5=50"
        assert math.isclose(st.current_energy, 42 * 1.25, rel_tol=1e-9), (
            "(30+E6 补 12)×E2 ERR 1.25——fandom 30(E0)/42(E6) 双档在案")
