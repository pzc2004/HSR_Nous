"""加拉赫 1301 模板端到端对轴（验收型批·单轨）：真模板 YAML → 编译 →
行迹/崭新配方/天赋/酩酊/武装闩/拉条/敬请干杯/秘技/星魂全链 → 手算全等.

口径常数：加拉赫 atk 529.2、hp 1305.36、crit 0.05/0.5、spd 98、max_energy 110；
行迹小节点 effect_res +28%/break_effect +13.3%/hp_pct +18%；
A2 崭新配方 heal_bonus = min(0.5×BE, 0.75) —— E0 实得 min(0.5×0.133, 0.75) = 0.0665。
假人 def 1000 → 防御区 0.5；火弱点 → 抗性 1.0；未击破 0.9；期望暴击区 1+0.05×0.5=1.025。
默认档：basic lv6、skill/ultimate/talent lv10（E3/E5 联动实取 lv7/lv12——族谱 18）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 529.2
DEF_ZONE = 0.5
UNBROKEN = 0.9
CRIT_EXP = 1.025
HEAL_BONUS_E0 = min(0.5 * 0.133, 0.75)   # 0.0665（行迹击破 13.3% 喂 A2 转化）
HEAL_MULTI_E0 = 1 + HEAL_BONUS_E0         # 1.0665


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1301", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1301", "technique": "130107"}]
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


def _gal(eng):
    return eng.state.actors["1301"]


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
    st = _gal(eng)
    st.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1301"] if a.action_id == "130103")
    assert eng._fire_ultimate(st, ult) is True


class TestGallagherCompile:
    def test_actions_and_resource(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1301"]}
        assert acts == {"130101", "130102", "130103", "130108"}
        assert compiled.resource_decls_by_actor["1301"]["_enhanced_armed"]["max"] == 1

    def test_skill_targets_ally(self, compiled):
        """战技 target_type=ally_single（过堂勘正①——"single" 敌方池会打敌人）."""
        skill = next(a for a in compiled.actions_by_actor["1301"] if a.action_id == "130102")
        assert skill.target_type == "ally_single"
        assert not skill.damage_type and not skill.scaling, "固定治疗无伤害段"


class TestTracesNovelConcoction:
    def test_trace_stat_nodes(self, compiled):
        """行迹小节点：effect_res +28% / break_effect +13.3% / hp 1305.36×1.18."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_gal(eng))
        assert math.isclose(eff["effect_res"], 0.28, rel_tol=1e-9)
        assert math.isclose(eff["break_effect"], 0.133, rel_tol=1e-9)
        assert math.isclose(eff["hp"], 1305.36 * 1.18, rel_tol=1e-9)

    def test_novel_concoction_heal_bonus(self, compiled):
        """崭新配方：heal_bonus = min(0.5×0.133, 0.75) = 0.0665（stat_exprs 动态）."""
        eng = _make(compiled)
        assert "NOVEL_CONCOCTION" in _gal(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_gal(eng))["heal_bonus"],
                            HEAL_BONUS_E0, rel_tol=1e-9)


class TestBasic:
    def test_damage_energy_sp_toughness(self, compiled):
        """普攻 lv6：529.2×1.0×0.5×0.9×1.025=244.0935；+20 能/+1 点/削韧 10."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp0, sp0 = e1.current_hp, eng.state.skill_points
        _cast(eng, "1301", "130101")
        assert math.isclose(hp0 - e1.current_hp, 244.0935, rel_tol=1e-9)
        assert math.isclose(_gal(eng).current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, sp0 + 1)
        assert math.isclose(e1.toughness, 90.0), "削韧 10（tbgd 30/米游社 10）"


class TestSkill:
    def test_flat_heal_and_costs(self, compiled):
        """罐装特调 lv10：1600×1.0665=1706.4（flat×(1+heal_bonus)）；-1 点/+30 能."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 1000.0
        sp0 = eng.state.skill_points
        _cast(eng, "1301", "130102", target=ally)
        assert math.isclose(ally.current_hp, 1000.0 + 1706.4, rel_tol=1e-9)
        assert math.isclose(_gal(eng).current_energy, 30.0)
        assert math.isclose(eng.state.skill_points, sp0 - 1)


class TestUltimate:
    def test_full_chain(self, compiled):
        """终结技：双假人各 366.14025 + 酩酊 2 回合 + 天赋自疗 2×682.56（先挂后伤，
        两酩酊目标各触发一次）+ 武装闩置 1 + 拉条 100%（剩余归零）+ 回能 5."""
        eng = _make(compiled)
        st = _gal(eng)
        st.current_hp = 100.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        # AoE：529.2×1.5×0.5×0.9×1.025 = 366.14025（两假人同值）
        assert math.isclose(hp1 - e1.current_hp, 366.14025, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 366.14025, rel_tol=1e-9)
        # 酩酊：action apply_modifiers 先挂（At the same time 语序——勘正⑦）
        assert e1.modifiers["BESOTTED"].duration == 2
        assert e2.modifiers["BESOTTED"].duration == 2
        # 终结技自身伤害命中 2 个已酩酊目标 → 天赋自疗 2 次 640×1.0665=682.56
        #（KQM「Heals Gallagher himself by activating his Talent」+ Prydwen
        # 「multiple times when attacking multiple enemies affected by the debuff」）
        assert math.isclose(st.current_hp, 100.0 + 2 * 682.56, rel_tol=1e-9)
        # 武装闩 + 拉条 100%（spd 98 → 剩余 ~102 < 10000 → 归零）
        assert math.isclose(st.resources["_enhanced_armed"], 1.0)
        assert math.isclose(_remaining(eng, "1301"), 0.0)
        # 能耗 110 全扣后回 5
        assert math.isclose(st.current_energy, 5.0)
        # 削韧 20/目标
        assert math.isclose(e1.toughness, 80.0)
        assert math.isclose(e2.toughness, 80.0)


class TestNectarBlitz:
    def test_full_chain(self, compiled):
        """酒花奔涌 lv6：529.2×2.5×0.5×0.9×1.025=610.23375 + 闩清 0 + 减攻 15%（850）+
        天赋回血自身 682.56 + 敬请干杯只铺队友（辅手 682.56、自身不双份）+ 削韧 30."""
        eng = _make(compiled)
        st = _gal(eng)
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        _ult(eng)   # 挂酩酊 + 武装闩
        st.current_hp, ally.current_hp = 500.0, 500.0
        hp1, sp0 = e1.current_hp, eng.state.skill_points
        _cast(eng, "1301", "130108")
        assert math.isclose(hp1 - e1.current_hp, 610.23375, rel_tol=1e-9)
        assert math.isclose(st.resources["_enhanced_armed"], 0.0), "闩兑现清 0"
        assert math.isclose(eng.pipeline.effective_stats(e1)["atk"], 850.0, rel_tol=1e-9), (
            "减攻 lv6=15% → 1000×0.85")
        assert e1.modifiers["ENHANCED_BASIC_ATK_DOWN"].duration == 2
        # 天赋：攻击者（加拉赫）回血 640×1.0665=682.56
        assert math.isclose(st.current_hp, 500.0 + 682.56, rel_tol=1e-9)
        # 敬请干杯：other_allies——辅手同量、自身不双份（勘正⑤）
        assert math.isclose(ally.current_hp, 500.0 + 682.56, rel_tol=1e-9)
        # 产点/回能与普攻一致；削韧 30（100-20 终结技-30 强普=50）
        assert math.isclose(eng.state.skill_points, sp0 + 1)
        assert math.isclose(e1.toughness, 50.0, rel_tol=1e-9)

    def test_gated_by_latch(self, compiled):
        """未武装时酒花奔涌被 available_if 闸滤除；终结技武装后过闸（_legal_with_available_if）."""
        eng = _make(compiled)
        st = _gal(eng)
        nb = next(a for a in eng.actions_by_actor["1301"] if a.action_id == "130108")
        basic = next(a for a in eng.actions_by_actor["1301"] if a.action_id == "130101")
        legal = eng._legal_with_available_if(st, [basic, nb])
        assert nb not in legal and basic in legal, "闩 0 → 强普滤除"
        _ult(eng)
        legal = eng._legal_with_available_if(st, [basic, nb])
        assert nb in legal, "闩 1 → 强普过闸"


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：双假人酩酊 2 回合 + 各 122.04675（ATK 50%）+ 削韧 20."""
        eng = _make(_compiled(pre_battle=True))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        for e in (e1, e2):
            assert e.modifiers["BESOTTED"].duration == 2
            assert math.isclose(1e9 - e.current_hp, 122.04675, rel_tol=1e-9)
            assert math.isclose(e.toughness, 80.0)


class TestEidolons:
    def test_e1_energy_and_eff_res(self):
        """E1：入场回能 20（gain_energy 正通道——勘正②）+ 效果抵抗 0.28+0.5=0.78."""
        eng = _make(_compiled(eidolon=1))
        st = _gal(eng)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["effect_res"],
                            0.78, rel_tol=1e-9)

    def test_e2_cleanse_and_eff_res(self):
        """E2：战技净化目标 1 个 debuff（LIFO 摘最新）+ 目标效果抵抗 +30% 2 回合."""
        eng = _make(_compiled(eidolon=2))
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_DEBUFF_A", name="旧", modifier_type="debuff",
            duration=3, dispellable=True))
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_DEBUFF_B", name="新", modifier_type="debuff",
            duration=3, dispellable=True))
        _cast(eng, "1301", "130102", target=ally)
        assert "TEST_DEBUFF_B" not in ally.modifiers, "LIFO 摘最新（max_count 1）"
        assert "TEST_DEBUFF_A" in ally.modifiers
        assert ally.modifiers["E2_EFF_RES"].duration == 2
        assert math.isclose(eng.pipeline.effective_stats(ally)["effect_res"],
                            0.3, rel_tol=1e-9)

    def test_e3_level_linkage(self):
        """E3：战技 lv12 治疗 1768×1.0665=1885.572；普攻 lv7 伤害 529.2×1.1×…=268.50285."""
        eng = _make(_compiled(eidolon=3))
        ally = eng.state.actors["ally"]
        ally.current_hp = 1000.0
        _cast(eng, "1301", "130102", target=ally)
        assert math.isclose(ally.current_hp, 1000.0 + 1885.572, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1301", "130101")
        assert math.isclose(hp1 - e1.current_hp, 268.50285, rel_tol=1e-9)

    def test_e4_besotted_duration3(self):
        """E4：终结技酩酊 2→3 回合（refresh 覆写——duration max() 语义）."""
        eng = _make(_compiled(eidolon=4))
        _ult(eng)
        assert eng.state.actors["e1"].modifiers["BESOTTED"].duration == 3
        assert eng.state.actors["e2"].modifiers["BESOTTED"].duration == 3

    def test_e5_level_linkage(self):
        """E5：终结技 lv12 伤害 529.2×1.65×…=402.754275；天赋 lv12 自疗 2×754.2288
        （两酩酊目标各触发一次）."""
        eng = _make(_compiled(eidolon=5))
        st = _gal(eng)
        st.current_hp = 10.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, 402.754275, rel_tol=1e-9)
        assert math.isclose(st.current_hp, 10.0 + 2 * 754.2288, rel_tol=1e-9)

    def test_e6_break_effect_and_efficiency(self):
        """E6：击破 0.133+0.2=0.333 → heal_bonus 0.1665（A2 动态跟随）+
        弱点击破效率 +20% → 普攻削韧 10×1.2=12."""
        eng = _make(_compiled(eidolon=6))
        st = _gal(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["break_effect"], 0.333, rel_tol=1e-9)
        assert math.isclose(eff["heal_bonus"], min(0.5 * 0.333, 0.75), rel_tol=1e-9)
        assert math.isclose(eff["weakness_break_efficiency_boost"], 0.2, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1301", "130101")
        assert math.isclose(e1.toughness, 88.0), "10×1.2=12（双池乘算单件）"
