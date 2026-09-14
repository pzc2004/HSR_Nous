"""不死途 1504 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 饲饵标记/减防/
天赋反追加/终结技强化 FUA 链/婪酣经济/罪途三件/影肢头狼/星魂全链 → 手算全等.

口径常数：不死途白值 atk 776.16（行迹 atk_pct +0.1 → 有效 853.776）、
crit 0.05/0.5（行迹暴伤 +0.373 + 头狼光环 +0.4 → 1.273，期望暴击区 1.06365）；
雷伤行迹 +0.144；影肢 FUA 桶 0.8+0.1×婪酣（现场）。假人 def 1000 → 防御区 0.5、
饲饵减防 40%（lv10）→ 600 → 0.625（E5 档 44% → 560 → 1000/1560）；雷弱点 →
抗性区 1.0（辅手火属性非弱点 → 0.8）；未击破 0.9（max_toughness 9999 恒不破）。
秘技跳伤结算早于模板光环挂载（装填序）→ 不吃头狼/减防：防御区 0.5、暴伤 0.873。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 776.16                       # 白值（管线 calc_character_stats lv80）
EFF_ATK = ATK * 1.1                # 行迹 atk_pct +0.1 → 853.776
CD = 0.5 + 0.373 + 0.4             # 行迹暴伤 + 头狼光环 = 1.273
CE = 1 + 0.05 * CD                 # 期望暴击区 1.06365
ALLY_CE = 1 + 0.05 * 0.9           # 辅手：仅头狼 +0.4 → 1.045
TECH_CE = 1 + 0.05 * (0.5 + 0.373)  # 秘技：头狼未挂载（装填序）→ 1.04365
TH = 0.144                         # 雷伤行迹
DEFZ = 0.625                       # 饲饵减防 40%：1000/(600+1000)
UNBROKEN = 0.9


def _dmg(mult, *, atk=EFF_ATK, boost=1 + TH, defz=DEFZ, ce=CE, vuln=1.0):
    """雷伤手算：atk × 倍率 × 增伤区 × 防御区 × 抗性 1.0 × 未击破 × 期望暴击 × 易伤区."""
    return atk * mult * boost * defz * UNBROKEN * ce * vuln


def _fua_boost(gld):
    """影肢在场时的 FUA 增伤区：1 + 雷伤 0.144 + (0.8 + 0.1×婪酣)."""
    return 1 + TH + 0.8 + 0.1 * gld


ALLY_HIT = 1500 * 0.8 * DEFZ * UNBROKEN * ALLY_CE          # 辅手火伤（非弱点 0.8）
ALLY_HIT_E5 = 1500 * 0.8 * (1000 / 1560) * UNBROKEN * ALLY_CE * 1.24


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1504", "level": 80}
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
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1504", "technique": "150407"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]}],
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


def _ash(eng):
    return eng.state.actors["1504"]


def _cast(eng, owner, aid, tid):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[tid]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, tid="e1"):
    st = _ash(eng)
    st.current_energy = 150.0
    ult = next(a for a in eng.actions_by_actor["1504"] if a.action_id == "150403")
    tgt = eng.state.actors[tid]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


class TestAshveilCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1504"]}
        assert acts == {"150401", "150402", "150403", "150404"}
        decls = compiled.resource_decls_by_actor["1504"]
        assert decls["charge"]["max"] == 3
        assert decls["charge"]["current"] == 2
        assert decls["gluttony"]["max"] == 12


class TestBattleStart:
    def test_init_state(self, compiled):
        """开战：充能 2（decl.current）；饲饵自动标 e1（同 HP 按站位序）；减防 40% 在载；
        头狼/影肢/行迹面板全对."""
        eng = _make(compiled)
        st = _ash(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        es = eng.pipeline.effective_stats
        assert math.isclose(st.resources["charge"], 2.0)
        assert math.isclose(st.resources["gluttony"], 0.0)
        assert "BAIT" in e1.modifiers and "BAIT" not in e2.modifiers, "饲饵自动标生命值最低（同值站位序）"
        assert math.isclose(es(e1)["def_"], 600.0), "饲饵存在性减防 40%（lv10）开战即在载"
        assert math.isclose(es(e2)["def_"], 600.0)
        assert math.isclose(es(st)["atk"], EFF_ATK, rel_tol=1e-9)
        assert math.isclose(es(st)["crit_dmg"], CD, rel_tol=1e-9), "0.5+行迹 0.373+头狼 0.4"
        assert math.isclose(es(eng.state.actors["ally"])["crit_dmg"], 0.9, rel_tol=1e-9)
        assert math.isclose(es(st)["dmg_bonus"]["thunder"], TH, rel_tol=1e-9)
        assert math.isclose(es(st)["dmg_bonus"]["follow_up_dmg_boost"], 0.8, rel_tol=1e-9), (
            "影肢 FUA 桶（婪酣 0 时 0.8）")


class TestBasicAndSkill:
    def test_basic(self, compiled):
        """普攻 lv6=1.0：853.776×1.0×1.144×0.625×0.9×1.06365；回能 20、产 1 点."""
        eng = _make(compiled)
        st = _ash(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1504", "150401", "e1")
        assert math.isclose(hp1 - e1.current_hp, _dmg(1.0), rel_tol=1e-9)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, 4.0)

    def test_skill_marks_bait_then_extra_and_refund(self, compiled):
        """战技 lv10=2.0：首击 e2 转标（无追加）；再击 e2 已是饲饵 → 追加 #3=1.0（伪
        行动类别 skill 不吃影肢桶）+ 返还 1 点（gain_skill_point）；罪途 +1/次."""
        eng = _make(compiled)
        st = _ash(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp2 = e2.current_hp
        _cast(eng, "1504", "150402", "e2")
        assert math.isclose(hp2 - e2.current_hp, _dmg(2.0), rel_tol=1e-9), "首击：主倍率 2.0 无追加"
        assert "BAIT" in e2.modifiers and "BAIT" not in e1.modifiers, "饲饵转移到战技目标"
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点（无返还——e2 施放前非饲饵）"
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.resources["gluttony"], 1.0), "罪途① 施放战技 +1"
        hp2 = e2.current_hp
        _cast(eng, "1504", "150402", "e2")
        assert math.isclose(hp2 - e2.current_hp, _dmg(2.0) + _dmg(1.0), rel_tol=1e-9), (
            "已是饲饵：主 2.0 + 额外 1.0（快照读施放前饲饵态）")
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 返 1"
        assert math.isclose(st.resources["gluttony"], 2.0)


class TestTalentFUA:
    def test_ally_hit_triggers_fua(self, compiled):
        """辅手攻击饲饵 → 天赋链：回 8+5 能、耗 1 充能、FUA（2.0 lv10，影肢桶现场
        0.8+0.1×2）+2 婪酣；充能耗尽后不再触发（门槛 res_charge >= 1）."""
        eng = _make(compiled)
        st = _ash(eng)
        e2 = eng.state.actors["e2"]
        _cast(eng, "1504", "150402", "e2")   # 转标 e2，婪酣 1
        _cast(eng, "1504", "150402", "e2")   # 追加+返还，婪酣 2
        hp2 = e2.current_hp
        en0 = st.current_energy
        _cast(eng, "ally", "ally_skill", "e2")
        want = ALLY_HIT + _dmg(2.0, boost=_fua_boost(2))
        assert math.isclose(hp2 - e2.current_hp, want, rel_tol=1e-9), "辅手命中 + FUA（婪酣 2 → 桶 1.0）"
        assert math.isclose(st.resources["charge"], 1.0), "耗 1 充能"
        assert math.isclose(st.current_energy - en0, 13.0), "固定 +8 + 天赋回能 5"
        assert math.isclose(st.resources["gluttony"], 4.0), "天赋后续 +2"
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_skill", "e2")
        want = ALLY_HIT + _dmg(2.0, boost=_fua_boost(4))
        assert math.isclose(hp2 - e2.current_hp, want, rel_tol=1e-9), "第二次：婪酣 4 → 桶 1.2"
        assert math.isclose(st.resources["charge"], 0.0)
        assert math.isclose(st.resources["gluttony"], 6.0)
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_basic", "e2")
        assert math.isclose(hp2 - e2.current_hp, ALLY_HIT, rel_tol=1e-9), (
            "充能 0 → 天赋链不触发（无 FUA）")
        assert math.isclose(st.resources["gluttony"], 6.0)


class TestUltimateChain:
    def test_ult_full_chain(self, compiled):
        """终结技 lv10：主 4.0 + 转标 + 充能 2+3→钳 3 + 强化 FUA 2.0（桶 0.8，婪酣 0）
        + 双份婪酣 +4 → 婪酣段耗 4 追加 2.0（桶 0.8）；能量仅行动回 5（无 phantom +8）."""
        eng = _make(compiled)
        st = _ash(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _ult(eng, "e1")
        want = _dmg(4.0) + _dmg(2.0, boost=_fua_boost(0)) + _dmg(2.0, boost=_fua_boost(0))
        assert math.isclose(hp1 - e1.current_hp, want, rel_tol=1e-9)
        assert math.isclose(st.resources["charge"], 3.0), "2+3 钳到上限 3（最多拥有）"
        assert math.isclose(st.resources["gluttony"], 0.0), "0+2+2−4=0（罪途②+天赋后续−婪酣段）"
        assert math.isclose(st.current_energy, 5.0), "仅终结技动作回能 5（tbgd）"
        assert "BAIT" in e1.modifiers and "BAIT" not in e2.modifiers, "终结技转标施放目标"

    def test_ult_segment_consumes_then_deals(self, compiled):
        """婪酣段：先耗 4 后结算——影肢按剩余层数现场读（官方「每有 1 层」持有口径）：
        预存婪酣 6 开大，段伤桶 = 0.8+0.1×(6+4−4)=1.4."""
        eng = _make(compiled)
        st = _ash(eng)
        st.resources["gluttony"] = 6.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng, "e1")
        want = (_dmg(4.0)
                + _dmg(2.0, boost=_fua_boost(6))    # 强化 FUA：婪酣 6 → 桶 1.4
                + _dmg(2.0, boost=_fua_boost(6)))   # 段：耗 4 后余 6 → 桶 1.4
        assert math.isclose(hp1 - e1.current_hp, want, rel_tol=1e-9)
        assert math.isclose(st.resources["gluttony"], 6.0), "6+2+2−4=6"


class TestBaitDeathAndKill:
    def test_fua_kill_gluttony_and_remark(self, compiled):
        """天赋 FUA 击杀饲饵 → 罪途③ +1（hook 致死 action_id 空串口径）+ 后续 +2 共 3；
        饲饵死亡立即转标存活最低 HP 敌人（e2）."""
        eng = _make(compiled)
        st = _ash(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        fua = _dmg(2.0, boost=_fua_boost(0))
        e1.current_hp = ALLY_HIT + fua * 0.5   # 辅手击打不死、FUA 补刀致死
        _cast(eng, "ally", "ally_basic", "e1")
        assert not e1.alive, "FUA 补刀致死"
        assert math.isclose(st.resources["gluttony"], 3.0), "击杀 +1（罪途③）+ 后续 +2"
        assert math.isclose(st.resources["charge"], 1.0)
        assert "BAIT" in e2.modifiers, "饲饵死亡立即转标"


class TestEidolons:
    def test_e1_vuln_threshold_switch(self):
        """E1：满血易伤 0.24；HP≤50% 切 0.36（enable_if 双件，阈值切换非叠加）."""
        eng = _make(_compiled(eidolon=1))
        e1 = eng.state.actors["e1"]
        es = eng.pipeline.effective_stats
        assert math.isclose(es(e1)["vulnerability"], 0.24, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1504", "150401", "e1")
        assert math.isclose(hp1 - e1.current_hp, _dmg(1.0, vuln=1.24), rel_tol=1e-9)
        e1.current_hp = 0.4 * es(e1)["hp"]
        assert math.isclose(es(e1)["vulnerability"], 0.36, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1504", "150401", "e1")
        assert math.isclose(hp1 - e1.current_hp, _dmg(1.0, vuln=1.36), rel_tol=1e-9)

    def test_e2_cap18_and_refund(self):
        """E2：婪酣上限 12→18（max_override）——预存 14 开大：14+2+2=18（不钳 12）
        −4+1（返还 round(4×0.35)=1）=15."""
        eng = _make(_compiled(eidolon=2))
        st = _ash(eng)
        st.resources["gluttony"] = 14.0
        _ult(eng, "e1")
        assert math.isclose(st.resources["gluttony"], 15.0), (
            "上限 18 生效（否则钳 12 → 9）+ 返还 1")

    def test_e3_ult12_basic7(self):
        """E3：终结技 lv12（主 4.4/段 2.2）、普攻 lv7=1.1；E1 易伤 1.24 联动."""
        eng = _make(_compiled(eidolon=3))
        st = _ash(eng)
        assert st.actor.skill_levels["ultimate"] == 12
        assert st.actor.skill_levels["basic"] == 7
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1504", "150401", "e1")
        assert math.isclose(hp1 - e1.current_hp, _dmg(1.1, vuln=1.24), rel_tol=1e-9)
        hp1 = e1.current_hp
        _ult(eng, "e1")
        want = (_dmg(4.4, vuln=1.24)
                + _dmg(2.0, boost=_fua_boost(0), vuln=1.24)   # 强化 FUA 按天赋 lv10（E5 未到）
                + _dmg(2.2, boost=_fua_boost(0), vuln=1.24))  # 婪酣段 lv12=2.2
        assert math.isclose(hp1 - e1.current_hp, want, rel_tol=1e-9)
        assert math.isclose(st.resources["gluttony"], 1.0), "0+4−4+E2 返还 1（联动）"

    def test_e4_atk_boost(self):
        """E4：施放终结技后 ATK +40%（atk_pct）3 回合——有效攻击 776.16×1.5=1164.24；
        随后普攻 lv7（E3 联动）吃新面板."""
        eng = _make(_compiled(eidolon=4))
        st = _ash(eng)
        es = eng.pipeline.effective_stats
        _ult(eng, "e1")
        assert math.isclose(es(st)["atk"], ATK * 1.5, rel_tol=1e-9), "1+行迹 0.1+E4 0.4"
        assert st.modifiers["E4_ATK_BOOST"].duration == 3
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1504", "150401", "e1")
        assert math.isclose(hp1 - e1.current_hp,
                            _dmg(1.1, atk=ATK * 1.5, vuln=1.24), rel_tol=1e-9)

    def test_e5_skill12_talent12(self):
        """E5：战技 lv12（减防 44% → 假人 560）+ 天赋 lv12（FUA 2.2）；E1 1.24 联动."""
        eng = _make(_compiled(eidolon=5))
        st = _ash(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        es = eng.pipeline.effective_stats
        assert math.isclose(es(e1)["def_"], 560.0, rel_tol=1e-9), "减防 lv12=44% 开战即在载"
        defz = 1000 / 1560
        _cast(eng, "1504", "150402", "e2")   # 转标 e2（主 2.2 lv12）
        hp2 = e2.current_hp
        _cast(eng, "1504", "150402", "e2")   # 已是饲饵：主 2.2 + 额外 1.1
        want = (_dmg(2.2, defz=defz, vuln=1.24) + _dmg(1.1, defz=defz, vuln=1.24))
        assert math.isclose(hp2 - e2.current_hp, want, rel_tol=1e-9)
        hp2 = e2.current_hp
        _cast(eng, "ally", "ally_skill", "e2")
        want = (ALLY_HIT_E5 + _dmg(2.2, boost=_fua_boost(2), defz=defz, vuln=1.24))
        assert math.isclose(hp2 - e2.current_hp, want, rel_tol=1e-9), "天赋 FUA lv12=2.2"
        assert math.isclose(st.resources["charge"], 1.0)

    def test_e6_respen_and_gluttony_counter(self):
        """E6：全队抗穿 0.2 光环；婪酣每获得 1 层计数 +1（按获得量——+2 记 2）、
        增伤 = 0.04×层（stat_exprs 现场）；消耗不计、E2 返还计."""
        eng = _make(_compiled(eidolon=6))
        st = _ash(eng)
        es = eng.pipeline.effective_stats
        assert math.isclose(es(st)["res_pen"], 0.2, rel_tol=1e-9)
        assert math.isclose(es(eng.state.actors["ally"])["res_pen"], 0.2, rel_tol=1e-9), (
            "team 光环辅手同吃")
        _ult(eng, "e1")   # +2+2=4（计数 4）−4（不计）+1 返还（计数 5）
        assert math.isclose(st.resources["gluttony"], 1.0)
        assert math.isclose(st.modifiers["E6_GLD_STACKS"].stacks, 5.0)
        assert math.isclose(es(st)["dmg_bonus"]["all"], 0.2, rel_tol=1e-9), "5 层 × 4%"
        _cast(eng, "ally", "ally_basic", "e1")   # 天赋链 +2 → 计数 7
        assert math.isclose(st.modifiers["E6_GLD_STACKS"].stacks, 7.0)
        assert math.isclose(es(st)["dmg_bonus"]["all"], 0.28, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：全体雷伤 100%×ATK（装填序早于光环挂载——防御区 0.5、暴伤 0.873）
        + 充能 2+1=3（decl.current 布场不被盖）."""
        eng = _make(_compiled(pre_battle=True))
        st = _ash(eng)
        assert math.isclose(st.resources["charge"], 3.0), "初始 2 + 秘技 1"
        want = EFF_ATK * 1.0 * (1 + TH) * 0.5 * UNBROKEN * TECH_CE
        for tid in ("e1", "e2"):
            dealt = 1e9 - eng.state.actors[tid].current_hp
            assert math.isclose(dealt, want, rel_tol=1e-6), f"{tid} 秘技跳伤"
