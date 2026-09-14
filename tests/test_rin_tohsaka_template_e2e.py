"""远坂凛 1508 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
天赋 Gem 流/秉持优雅/淑女风范/终结技主+其余+易伤+产点/强化战技互斥/行迹/星魂全链 → 手算全等.

口径常数：远坂凛 atk 698.544、crit 0.05/0.5（行迹暴伤 +0.373→0.873）、spd 102、
max_energy 160；假人 def 1000 → 防御区 0.5；量子弱点匹配 → 抗性基数 0；
未击破 0.9；期望暴击区 = 1+0.05×0.873 = 1.04365。
秉持有雅 atk_pct 1.5 + 行迹 atk_pct 0.18 → 有效 atk = 698.544×2.68 = 1872.09792；
量子穿抗 15% → 抗性区 1.15（E6 后 1.35）；行迹量子增伤 8% → 增伤区 1.08。
Z = 0.5×1.15×1.08×0.9×1.04365（E0 全链公共乘区）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 698.544 * (1 + 0.18 + 1.5)          # 1872.09792（行迹 0.18 + 秉持优雅 1.5）
CRIT_EXP = 1 + 0.05 * (0.5 + 0.373)       # 1.04365（行迹暴伤 0.373 进期望暴击区）
Z = 0.5 * 1.15 * 1.08 * 0.9 * CRIT_EXP    # E0 公共乘区（防御/抗性/增伤/未击破/期望暴击）
Z_E2 = 0.5 * 1.15 * (1.08 + 0.3) * 0.9 * CRIT_EXP   # E2：战技增伤桶 +0.3 进增伤区
Z_E6 = 0.5 * 1.35 * 1.08 * 0.9 * CRIT_EXP           # E6：穿抗 0.15+0.2=0.35 → 抗性区 1.35


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1508", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1508", "technique": "150807"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["quantum"]},
    {"actor_id": "e2", "name": "假人2", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["quantum"]}],
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


def _rin(eng):
    return eng.state.actors["1508"]


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


def _ult(eng, *, target=None):
    st = _rin(eng)
    st.current_energy = 160.0
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    ult = next(a for a in eng.actions_by_actor["1508"] if a.action_id == "150803")
    assert eng._fire_ultimate(st, ult) is True   # B37 双发：on_action/on_ultimate 引擎自发，勿手动补


class TestCompile:
    def test_actions_resources_available_if(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1508"]}
        assert set(acts) == {"150801", "150802", "150803", "150809"}
        assert compiled.resource_decls_by_actor["1508"]["gem_energy"]["max"] == 99
        assert acts["150802"].available_if == "res_gem_energy < 15", (
            "过堂②：单下划线平铺键（双下划线=未声明死件）")
        assert acts["150809"].available_if == "res_gem_energy >= 15"
        assert acts["150803"].target_type == "single", "过堂③：主目标段 single，其余段走 hook"


class TestBattleStart:
    def test_traces_and_major_traces(self, compiled):
        """开战：天赋 +20 Gem；秉持优雅 SP 上限 7/ATK×2.68/穿抗 0.15；淑女风范 spd×1.2；
        minor 行迹（暴伤 0.373/攻击 0.18/量子 0.08）经 trace_stat_effects 进面板."""
        eng = _make(compiled)
        st = _rin(eng)
        assert eng.state.sp_max_override == 7, "秉持优雅：5+2=7（过堂⑨ set_sp_max）"
        assert math.isclose(st.resources["gem_energy"], 20.0), "天赋入场 +20 Gem"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], ATK, rel_tol=1e-9), "698.544×(1+0.18+1.5)"
        assert math.isclose(eff["spd"], 102 * 1.2, rel_tol=1e-9), "淑女风范 spd+20%"
        assert math.isclose(eff["res_pen"], 0.15, rel_tol=1e-9), "秉持优雅量子穿抗 15%"
        assert math.isclose(eff["crit_dmg"], 0.873, rel_tol=1e-9), "行迹暴伤 0.373（过堂⑭）"
        assert math.isclose(eff["dmg_bonus"]["quantum"], 0.08, rel_tol=1e-9), "行迹量子 0.08"


class TestAvailableIf:
    @pytest.mark.parametrize("gem,normal_ok,enhanced_ok", [(20, False, True), (10, True, False)])
    def test_skill_slot_mutex(self, compiled, gem, normal_ok, enhanced_ok):
        """同槽双技互斥（仅 Gem 半口径；SP≥7 半待收）：Gem=20 仅强化、Gem=10 仅普通."""
        eng = _make(compiled)
        st = _rin(eng)
        st.resources["gem_energy"] = float(gem)
        acts = {a.action_id: a for a in eng.actions_by_actor["1508"]}
        assert eng._available_if_ok(st, acts["150802"]) is normal_ok
        assert eng._available_if_ok(st, acts["150809"]) is enhanced_ok


class TestBasicAndSkill:
    def test_basic_chain(self, compiled):
        """普攻 lv6=1.0：dmg=ATK×1.0×Z；SP 3→4 + 天赋 +1 Gem；回能 20."""
        eng = _make(compiled)
        st, e1 = _rin(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1508", "150801")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.0 * Z, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "产点 +1"
        assert math.isclose(st.resources["gem_energy"], 21.0), "天赋：SP 实变动 +1 → +1 Gem"
        assert math.isclose(st.current_energy, 20.0)

    def test_skill_chain_and_talent_sp_flow(self, compiled):
        """战技 lv10=1.8（Gem<15 位）：dmg=ATK×1.8×Z；耗点 1 → +1 Gem；回能 30；
        天赋 SP 流双向：辅手耗 1 点 +1 Gem、辅手产 1 点 +1 Gem."""
        eng = _make(compiled)
        st, e1 = _rin(eng), eng.state.actors["e1"]
        st.resources["gem_energy"] = 0.0   # 压到 15 下解锁普通战技
        hp0 = e1.current_hp
        _cast(eng, "1508", "150802")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.8 * Z, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0), "耗点 1（3→2）"
        assert math.isclose(st.resources["gem_energy"], 1.0), "耗 1 点 → +1 Gem"
        assert math.isclose(st.current_energy, 30.0)
        _cast(eng, "ally", "ally_skill")   # 辅手耗 1 点
        assert math.isclose(st.resources["gem_energy"], 2.0), "天赋：队友耗点同计"
        _cast(eng, "ally", "ally_basic")   # 辅手产 1 点
        assert math.isclose(st.resources["gem_energy"], 3.0), "天赋：恢复方向同计"


class TestEnhancedSkill:
    def test_first_hit_aoe_and_ladylike_refresh(self, compiled):
        """强化战技首击 lv10=0.9 全体：双假人各吃 ATK×0.9×Z；耗点 0/回能 30/首击不耗 Gem；
        淑女风范再触发（150802 不触发——EN 层裁定）."""
        eng = _make(compiled)
        st = _rin(eng)
        assert math.isclose(st.resources["gem_energy"], 20.0), "开局 20≥15 即强化位"
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1508", "150809")
        for old, e in ((hp1, e1), (hp2, e2)):
            assert math.isclose(old - e.current_hp, ATK * 0.9 * Z, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 3.0), "耗点 0（tbgd BPNeed=-1）"
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.resources["gem_energy"], 20.0), "首击不耗 Gem（消耗在弹射循环段——待收）"
        assert "LADYLIKE_POISE" in st.modifiers, "强化战技后淑女风范再挂"


class TestUltimate:
    def test_full_chain(self, compiled):
        """终结技 lv10：主目标 ATK×6.0×Z；其余（e2）ATK×2.0×Z（ultimate 身份，主目标不被
        其余段重复命中——过堂④）；全体易伤 0.2×3；产点 +1 → 天赋 +1 Gem；财源广进 +12 Gem；
        回能 5；易伤后普攻吃 ×1.2 承伤区."""
        eng = _make(compiled)
        st, e1, e2 = _rin(eng), eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, ATK * 6.0 * Z, rel_tol=1e-9), "主目标 600%"
        assert math.isclose(hp2 - e2.current_hp, ATK * 2.0 * Z, rel_tol=1e-9), "其余 200%（hook）"
        assert math.isclose(eng.state.skill_points, 4.0), "过堂⑬：文本 #4=1 产点"
        assert math.isclose(st.resources["gem_energy"], 20 + 12 + 1, rel_tol=1e-9), (
            "财源广进 12 + 天赋 SP 流 1")
        assert math.isclose(st.current_energy, 5.0), "160 全扣后回 5"
        for e in (e1, e2):
            assert math.isclose(eng.pipeline.effective_stats(e)["vulnerability"],
                                0.2, rel_tol=1e-9), "过堂⑪：易伤 20%×3（vulnerability 在案键）"
        hp1 = e1.current_hp
        _cast(eng, "1508", "150801")
        assert math.isclose(hp1 - e1.current_hp, ATK * 1.0 * Z * 1.2, rel_tol=1e-9), (
            "易伤后承伤区 ×1.2")

    def test_gem_clamp_99(self, compiled):
        """Gem 上限 99（推定值在案）：95 + 财源广进 12 + 天赋 1 = 108 → clamp 99."""
        eng = _make(compiled)
        st = _rin(eng)
        st.resources["gem_energy"] = 95.0
        _ult(eng)
        assert math.isclose(st.resources["gem_energy"], 99.0)


class TestTechnique:
    def test_pre_battle_gem(self):
        """秘技 150807：进战 +10 Gem（与天赋 20 合计 30）."""
        eng = _make(_compiled(pre_battle=True))
        assert math.isclose(_rin(eng).resources["gem_energy"], 30.0)


class TestEidolons:
    def test_e2_skill_boost(self):
        """E2：凛自身战技增伤 +30%（dmg_skill_dmg_boost 桶——过堂⑫）；战技 lv10 不变."""
        eng = _make(_compiled(eidolon=2))
        st, e1 = _rin(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"]["skill_dmg_boost"],
                            0.3, rel_tol=1e-9)
        st.resources["gem_energy"] = 0.0
        hp0 = e1.current_hp
        _cast(eng, "1508", "150802")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.8 * Z_E2, rel_tol=1e-9), (
            "增伤区 1.08+0.3=1.38")

    def test_e3_skill_lv12_basic_lv7(self):
        """E3（过堂①勘正=战技+2/普攻+1）：战技实取 lv12=1.98、普攻实取 lv7=1.1；
        eidolon=3 联动 E2 → 战技增伤区 1.38（普攻非战技类不吃）."""
        eng = _make(_compiled(eidolon=3))
        st, e1 = _rin(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1508", "150801")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.1 * Z, rel_tol=1e-9), "普攻 lv7=1.1"
        st.resources["gem_energy"] = 0.0
        hp0 = e1.current_hp
        _cast(eng, "1508", "150802")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.98 * Z_E2, rel_tol=1e-9), (
            "战技 lv12=1.98 × E2 增伤区 1.38")

    def test_e5_ult_lv12(self):
        """E5（过堂①勘正=终结技+2/天赋+2）：主 6.6/其余 2.2/易伤 0.22（lv12 档）."""
        eng = _make(_compiled(eidolon=5))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, ATK * 6.6 * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, ATK * 2.2 * Z, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"],
                            0.22, rel_tol=1e-9), "易伤随档 lv12=0.22"

    def test_e6_respen_gem_extra_turn(self):
        """E6：穿抗 0.15+0.2=0.35（抗性区 1.35）；终结技 +24 Gem + 1 额外回合
        （grant_extra_turn——过堂⑩）；联动 E5 → 主目标 lv12=6.6."""
        eng = _make(_compiled(eidolon=6))
        st, e1 = _rin(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.35, rel_tol=1e-9)
        hp1 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, ATK * 6.6 * Z_E6, rel_tol=1e-9)
        assert math.isclose(st.resources["gem_energy"], 20 + 12 + 1 + 24, rel_tol=1e-9)
        assert len(eng.scheduler._extra_queue) == 1, "额外回合授予"
        assert eng.scheduler._extra_queue[0][0] == eng.scheduler._handles["1508"]
