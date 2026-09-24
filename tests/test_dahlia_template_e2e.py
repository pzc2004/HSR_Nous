"""大丽花 1321 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 共舞者绑定/超击破
转化窗口/FUA 闩与行迹计数/结界/Wilt/星魂全链 → 手算全等.

口径常数：大丽花 atk 679.14、break_effect 0.373（行迹平铺）、spd 101（96+5）、
crit 0.05/0.5 → 期望暴击区 1.025、max_energy 130；辅手 atk 1500 BE 1.0，辅手二
atk 1200 BE 0.5。假人 def 1000 → 防御区 0.5；火弱点 → 抗性区 1.0；未击破 0.9。
超击破基数 = 3767.5533/10 × 有效削韧（rulebook super_break_base_multi，火无另系）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 679.14
CRIT = 1.025            # 期望暴击区 1 + 0.05×0.5
DEF_HALF = 0.5          # 假人 def 1000、攻击方 lv80 → 1000/(1000+1000)
WILT_DEF = 1000 / 1820  # Wilt -18% 后 def 820 → 1000/(820+1000)
SB_BASE3 = 376.75533 * 3  # FUA 逐段削韧 3 → 超击破基数


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1321", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100,
                        "break_effect": 1.0},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]},
        {"actor_id": "ally2", "name": "辅手二", "inline": True,
         "base_stats": {"atk": 1200, "spd": 85, "hp": 3000, "max_energy": 100,
                        "break_effect": 0.5},
         "actions": [{"action_id": "ally2_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1321", "technique": "132107"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
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


def _dahlia(eng):
    return eng.state.actors["1321"]


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
    st = _dahlia(eng)
    st.current_energy = 130.0
    ult = next(a for a in eng.actions_by_actor["1321"] if a.action_id == "132103")
    assert eng._fire_ultimate(st, ult) is True


def _pool(eng, aid):
    return float(eng.pipeline.effective_stats(eng.state.actors[aid]).get(
        "super_break_modifier", 0.0) or 0.0)


class TestCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1321"]}
        assert set(acts) == {"132101", "132102", "132103", "132104"}
        assert acts["132104"].action_type == "follow_up"
        assert acts["132104"].instances == 5, "天赋 FUA 5 段（官方 params #2 全档恒 5）"
        assert acts["132103"].split == "even", "终结技均分（勘正⑦）"
        decls = compiled.resource_decls_by_actor["1321"]
        assert decls["_fua_turns"]["max"] == 1
        assert decls["_fua_sp_count"]["max"] == 2

    def test_e6_skill_levels(self):
        """E3 终结技+2/普攻+1、E5 战技/天赋+2 联动（eidolon=6 实取档）."""
        c = _compiled(eidolon=6)
        lv = next(a for a in c.build_team if a.actor_id == "1321").skill_levels
        assert lv["ultimate"] == 12 and lv["basic"] == 7
        assert lv["skill"] == 12 and lv["talent"] == 12


class TestBaseAndTraces:
    def test_panel_and_talent_energy(self, compiled):
        """行迹平铺并白值：spd 101 / BE 0.373 / effect_res 0.18；入战回能 #4=35."""
        eng = _make(compiled)
        st = _dahlia(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["spd"], 101.0, rel_tol=1e-9)
        assert math.isclose(eff["break_effect"], 0.373, rel_tol=1e-9)
        assert math.isclose(eff["effect_res"], 0.18, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 35.0), "天赋入战 +35 能（勘正⑤）"

    def test_partner_binding_and_conversion_pool(self, compiled):
        """共舞者 = 最高 BE 队友（order_by 降序勘正①）：ally 中、ally2 不中；
        转化池 #5=0.6 挂自身+共舞者."""
        eng = _make(compiled)
        assert "DANCE_PARTNER" in eng.state.actors["ally"].modifiers
        assert "DANCE_PARTNER" not in eng.state.actors["ally2"].modifiers
        assert "DANCE_PARTNER_SELF" in _dahlia(eng).modifiers
        assert math.isclose(_pool(eng, "1321"), 0.6, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally"), 0.6, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally2"), 0.0, rel_tol=1e-9)

    def test_funeral_be_share(self, compiled):
        """行迹1：队友 BE += 0.24×大丽花 BE + 0.5 = 0.24×0.373+0.5 = 0.58952."""
        eng = _make(compiled)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])["break_effect"],
            1.0 + 0.58952, rel_tol=1e-9)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally2"])["break_effect"],
            0.5 + 0.58952, rel_tol=1e-9)


class TestBasicSkill:
    def test_basic_damage_and_gain(self, compiled):
        """普攻 lv6（默认档）：679.14×1.0×0.5×0.9×1.025 = 313.253325；SP+1、回能 20."""
        eng = _make(compiled)
        st = _dahlia(eng)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1321", "132101")
        assert math.isclose(hp0 - e1.current_hp, 313.253325, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "普攻产 1 点（3→4）"
        assert math.isclose(st.current_energy, 35.0 + 20.0)

    def test_skill_blast_zone(self, compiled):
        """战技 lv10：主/相邻同倍率 1.6 → 各 679.14×1.6×0.5×0.9×1.025 = 501.20532；
        结界全队 WBE +0.5（tick_anchor 大丽花回合开始 -1）；SP-1、回能 30."""
        eng = _make(compiled)
        st = _dahlia(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1321", "132102")
        for e, hp0 in ((e1, hp1), (e2, hp2)):
            assert math.isclose(hp0 - e.current_hp, 501.20532, rel_tol=1e-9)
        assert "SKILL_ZONE" in st.modifiers
        for aid in ("1321", "ally", "ally2"):
            assert math.isclose(
                eng.pipeline.effective_stats(eng.state.actors[aid])[
                    "weakness_break_efficiency_boost"], 0.5, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0), "战技耗 1 点（3→2）"
        assert math.isclose(st.current_energy, 35.0 + 30.0)
        assert st.modifiers["SKILL_ZONE"].duration == 3
        eng._tick_modifiers(st, "owner_turn_start")   # tick 由引擎回合处理驱动（非裸事件）
        assert st.modifiers["SKILL_ZONE"].duration == 2, "大丽花回合开始 -1（tick 口径）"


class TestUltimate:
    def test_split_even_and_wilt(self, compiled):
        """终结技 lv10：先挂 Wilt（def 820 → 区 1000/1820）后结算，split even 双怪
        各吃 3.0/2=1.5 倍率 → 679.14×1.5×(1000/1820)×0.9×1.025 = 516.351635."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        for e, hp0 in ((e1, hp1), (e2, hp2)):
            assert math.isclose(hp0 - e.current_hp, 516.3516346153847, rel_tol=1e-9)
            assert "WILT" in e.modifiers
            assert math.isclose(eng.pipeline.effective_stats(e)["def_"], 820.0,
                                rel_tol=1e-9), "Wilt lv10 DEF -18%"
        assert math.isclose(_dahlia(eng).current_energy, 5.0), "终结技释放后回 5 能"


class TestTalentFUA:
    def test_fua_trigger_latch_counter(self, compiled):
        """共舞者攻击 → FUA 5 段（各 679.14×0.3×0.5×0.9×1.025=93.976，期望模式全落
        e1）；每回合 1 次闩；行迹2 每 2 次 FUA 产 1 点."""
        eng = _make(compiled, initial_sp=1)
        st = _dahlia(eng)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")   # 辅手普攻 691.875 + FUA 5×93.976
        assert math.isclose(hp0 - e1.current_hp,
                            691.875 + 5 * 93.9759975, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 35.0 + 2.0), "FUA 回能 2"
        assert math.isclose(st.resources["_fua_turns"], 1.0), "闩已落"
        assert math.isclose(st.resources["_fua_sp_count"], 1.0), "行迹2 计数 1"
        assert math.isclose(eng.state.skill_points, 2.0), "辅手普攻 +1（1→2），行迹2 未产"
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")   # 同回合闩挡：无 FUA
        assert math.isclose(hp0 - e1.current_hp, 691.875, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 3.0)
        eng.bus.emit("on_turn_start", {"actor": "1321"}, eng.state)   # 闩归零
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")   # 第 2 次 FUA → 行迹2 产 1 点 + 计数清零
        assert math.isclose(hp0 - e1.current_hp,
                            691.875 + 5 * 93.9759975, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 5.0), "4（辅手普攻后）+1（行迹2）"
        assert math.isclose(st.resources["_fua_sp_count"], 0.0)

    def test_non_partner_no_trigger(self, compiled):
        """非共舞者（ally2）攻击不触发 FUA."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "ally2", "ally2_basic")   # 1200×0.5×0.9×1.025 = 553.5
        assert math.isclose(hp0 - e1.current_hp, 553.5, rel_tol=1e-9)
        assert math.isclose(_dahlia(eng).resources["_fua_turns"], 0.0)


class TestSuperBreak:
    def test_fua_super_break_window(self, compiled):
        """已击破目标：FUA 窗口抬池 #5 0.6→#3 2.0（勘正③）——逐段超击破
        376.75533×3 ×1.373(BE) ×2.0 ×0.5 = 1551.855204；共舞者辅手同吃转化
        （池 0.6、BE 1.58952——普攻削韧 10）；窗后即摘（池回落 0.6）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.broken = True
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        ally_dmg = 1500 * 0.5 * 1.0 * CRIT                      # 已击破 1.0 区
        ally_sb = 376.75533 * 10 * (1 + 1.58952) * 0.6 * 0.5    # 共舞者转化 #5=0.6
        fua_seg = ATK * 0.3 * 0.5 * 1.0 * CRIT                  # 本体段
        sb_seg = SB_BASE3 * 1.373 * 2.0 * 0.5                   # 超击破段（窗口 2.0）
        assert math.isclose(hp0 - e1.current_hp,
                            ally_dmg + ally_sb + 5 * (fua_seg + sb_seg), rel_tol=1e-9)
        assert "_FUA_SB_WINDOW" not in _dahlia(eng).modifiers, "窗后即摘"
        assert math.isclose(_pool(eng, "1321"), 0.6, rel_tol=1e-9), "池回落常态 #5"

    def test_normal_attack_pool_60(self, compiled):
        """常态攻击按 #5=60% 转化（窗口只罩 FUA）：大丽花普攻已击破假人 → 超击破
        376.75533×10 ×1.373 ×0.6 ×0.5（普攻削韧 10）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.broken = True
        hp0 = e1.current_hp
        _cast(eng, "1321", "132101")
        basic = ATK * 1.0 * 0.5 * 1.0 * CRIT
        sb = 376.75533 * 10 * 1.373 * 0.6 * 0.5
        assert math.isclose(hp0 - e1.current_hp, basic + sb, rel_tol=1e-9)


class TestEidolons:
    def test_e1_team_conversion(self):
        """E1：转化全队化——ally2 0.6；共舞者（自身+ally）0.6+0.4=1.0（加算口径）."""
        eng = _make(_compiled(eidolon=1))
        assert math.isclose(_pool(eng, "1321"), 1.0, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally"), 1.0, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally2"), 0.6, rel_tol=1e-9)

    def test_e2_res_pen_and_entry_wilt(self):
        """E2：全队 res_pen +0.2（敌方抗性 -20% 等价承载）+ 入场 Wilt 3 回合（def 820）；
        辅手普攻 = 1500×(1000/1820)×0.9×1.025×1.2 = 912.362637."""
        eng = _make(_compiled(eidolon=2))
        for aid in ("1321", "ally", "ally2"):
            assert math.isclose(
                eng.pipeline.effective_stats(eng.state.actors[aid])["res_pen"],
                0.2, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        assert "WILT" in e1.modifiers
        assert e1.modifiers["WILT"].duration == 3
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 820.0, rel_tol=1e-9)
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        ally_dmg = 1500 * WILT_DEF * 0.9 * CRIT * 1.2
        # FUA 同吃：Wilt 减防 + res_pen（区 1.2）
        fua_seg = ATK * 0.3 * WILT_DEF * 0.9 * CRIT * 1.2
        assert math.isclose(hp0 - e1.current_hp, ally_dmg + 5 * fua_seg, rel_tol=1e-9)

    def test_e4_extra_segments_and_vuln(self):
        """E4：FUA 追加 5 段 + 敌方全体易伤 12% 持续 2 回合。eidolon=4 联动（族谱 18）：
        E2 入场 Wilt 按 ult lv12 取档 -20%（def 800 → 区 1000/1800）+ res_pen 0.2（区 1.2）；
        天赋仍 lv10（E5 未激活）0.3/段；E4 段吃易伤（事件序 artifact 在案）."""
        eng = _make(_compiled(eidolon=4))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 800.0,
                            rel_tol=1e-9), "E3 联动：Wilt 实取 lv12（-20%）"
        lv12_def = 1000 / 1800
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        ally_dmg = 1500 * lv12_def * 0.9 * CRIT * 1.2
        fua_seg = ATK * 0.3 * lv12_def * 0.9 * CRIT * 1.2
        e4_seg = fua_seg * 1.12
        assert math.isclose(hp0 - e1.current_hp,
                            ally_dmg + 5 * fua_seg + 5 * e4_seg, rel_tol=1e-9)
        for e in (e1, e2):
            assert "E4_VULN" in e.modifiers
            assert e.modifiers["E4_VULN"].duration == 2
            assert math.isclose(eng.pipeline.effective_stats(e)["vulnerability"],
                                0.12, rel_tol=1e-9)

    def test_e6_partner_be_and_double_advance(self):
        """E6：共舞者 BE +150%（ally 1.0+1.5+葬礼 0.58952=3.08952）；FUA 后自身与共舞者
        各提前 20%（2000 AV）。eidolon=6 联动 E5 → FUA 实取 lv12（0.33/段）."""
        eng = _make(_compiled(eidolon=6))
        st = _dahlia(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])["break_effect"],
            1.0 + 1.5 + 0.58952, rel_tol=1e-9)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally2"])["break_effect"],
            0.5 + 0.58952, rel_tol=1e-9), "E6 只挂共舞者（ally2 无 +150%）"
        # lv12 联动：E2 Wilt(lv12 -20% → def 800，区 1000/1800) + res_pen 0.2 + E4 易伤
        e1 = eng.state.actors["e1"]
        lv12_def = 1000 / 1800
        hp0 = e1.current_hp
        rem_self, rem_ally = _remaining(eng, "1321"), _remaining(eng, "ally")
        _cast(eng, "ally", "ally_basic")
        ally_dmg = 1500 * lv12_def * 0.9 * CRIT * 1.2
        fua_seg = ATK * 0.33 * lv12_def * 0.9 * CRIT * 1.2
        e4_seg = fua_seg * 1.12
        assert math.isclose(hp0 - e1.current_hp,
                            ally_dmg + 5 * fua_seg + 5 * e4_seg, rel_tol=1e-9)
        assert math.isclose(rem_self - _remaining(eng, "1321"), 2000.0, rel_tol=1e-9), (
            "E6 自身提前 20%（勘正⑪）")
        assert math.isclose(rem_ally - _remaining(eng, "ally"), 2000.0, rel_tol=1e-9), (
            "E6 共舞者提前 20%")


class TestTechnique:
    def test_pre_battle_zone(self):
        """秘技：进战立即部署战技结界本体（3 回合——勘正⑨），全队 WBE +0.5."""
        eng = _make(_compiled(pre_battle=True))
        st = _dahlia(eng)
        assert "SKILL_ZONE" in st.modifiers
        assert st.modifiers["SKILL_ZONE"].duration == 3
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])[
                "weakness_break_efficiency_boost"], 0.5, rel_tol=1e-9)
