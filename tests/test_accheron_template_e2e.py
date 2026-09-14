"""黄泉 1308 模板端到端对轴（复杂型专项·大招段结构重锤）：真模板 YAML → 编译 →
残梦经济/绯红结/啼泽雨斩段链/溢出 QA/行迹/星魂全链 → 手算全等.

口径常数：黄泉白值 atk 698.544、crit 0.05/0.5（期望暴击区 1.025）；假人 def 1000 →
防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9 → Z=0.46125。
大招 lv10：啼泽雨斩 0.24 单体、结爆 min(0.15×(1+n), 0.6) 全体、黄泉返渡 1.2 全体、
Thunder Core 0.25×6 随机（expected 按序取首全落 e1）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 698.544
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0, pre_battle: bool = False, extra_nihility: int = 0):
    member = {"character_template": "1308", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member]
    for i in range(extra_nihility):
        team.append({"actor_id": f"nih{i}", "name": f"虚无{i}", "inline": True,
                     "path": "nihility",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": f"nih{i}_basic", "name": "普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "ice", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10}]})
    team.append({"actor_id": "ally", "name": "辅手", "inline": True,
                 "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
                 "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "fire",
                              "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]})
    build = {"build": {"team": team,
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1308", "technique": "130807"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, extra_nihility: int = 0):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle,
                                    extra_nihility=extra_nihility),
                             _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ach(eng):
    return eng.state.actors["1308"]


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


def _knots(eng, aid, stacks):
    eng._apply_modifier(eng.state.actors[aid], Modifier(
        modifier_id="CRIMSON_KNOT", name="绯红结", modifier_type="debuff",
        stacks=stacks, max_stack=9, duration=0, dispellable=False))


def _ult(eng):
    st = _ach(eng)
    st.resources["slashed_dream"] = 9.0
    ult = next(a for a in eng.actions_by_actor["1308"] if a.action_id == "130803")
    assert eng._fire_ultimate(st, ult) is True


class TestAcheronCompile:
    def test_actions_and_ult_structure(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1308"]}
        assert set(acts) == {"130801", "130802", "130803"}, (
            "130814-130817 散装零成本 action 已摘除（免费终结技后门）")
        ult = acts["130803"]
        assert ult.instances == 4 and ult.segment_confirm is True
        assert len(ult.instance_variants) == 4 and ult.instance_variants[3] is not None
        assert ult.ult_cost_resource == "slashed_dream" and ult.ult_cost_amount == 9


class TestSkillAndTalent:
    def test_skill_blast_dream_knot(self, compiled):
        """战技：主 2.0×ATK/邻 0.75×ATK×Z + 残梦 +2（技能自带 1 + 战技挂结触发天赋 1）+
        指定目标 +1 结（天赋追发 +1 结落结最多敌）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1308", "130802")
        assert math.isclose(hp1 - e1.current_hp, 1.6 * ATK * Z, rel_tol=1e-9), (
            "战技 lv10=1.6 主（15 档表 index 9——末行 2.0 是 lv15 幻视勘正）")
        assert math.isclose(hp2 - e2.current_hp, 0.6 * ATK * Z, rel_tol=1e-9), (
            "相邻 lv10=0.6（同档）")
        assert math.isclose(_ach(eng).resources["slashed_dream"], 8.0), (
            "开战 5 + 开战挂结触发天赋 1 + 战技 1 + 战技结触发天赋 1（宽口径在案）")
        assert math.isclose(e1.modifiers["CRIMSON_KNOT"].stacks, 8.0), (
            "开战 5 + 天赋 1 + 战技 1 + 天赋 1（落点结最多=e1）")

    def test_talent_debuff_engine(self, compiled):
        """天赋：任意 debuff 落敌 → +1 残梦 + 结最多敌 +1 结（ULT_KNOT_LOCK 不在场）."""
        eng = _make(compiled)
        st = _ach(eng)
        st.resources["slashed_dream"] = 0.0
        eng._apply_modifier(eng.state.actors["e1"], Modifier(
            modifier_id="TEST_DEBUFF", name="测", modifier_type="debuff", duration=1))
        assert math.isclose(st.resources["slashed_dream"], 1.0)
        assert math.isclose(eng.state.actors["e1"].modifiers["CRIMSON_KNOT"].stacks, 7.0), (
            "开战 5 + 开战天赋 1 + 本 debuff 天赋 1（落点=-stacks 降序取结最多=e1）")


class TestOverflowQA:
    def test_overflow_converts_to_qa(self, compiled):
        """残梦溢出 → 四相断我（on_resource_gain overflow 字段——cap 3 截断）；
        战技每次 +2 残梦（技能 1+天赋 1）：8 起手，战技 1→溢 1、战技 2→溢 2."""
        eng = _make(compiled)
        st = _ach(eng)
        st.resources["slashed_dream"] = 8.0
        _cast(eng, "1308", "130802")   # 8+2=10 → 钳 9 溢 1 → QA 1
        assert math.isclose(st.resources["slashed_dream"], 9.0)
        assert math.isclose(st.modifiers["QUADRIVALENT_ASCENDANCE"].stacks, 1.0)
        _cast(eng, "1308", "130802")   # 9+2=11 → 溢 2 → QA 3 截断
        assert math.isclose(st.modifiers["QUADRIVALENT_ASCENDANCE"].stacks, 3.0)
        _cast(eng, "1308", "130802")
        assert math.isclose(st.modifiers["QUADRIVALENT_ASCENDANCE"].stacks, 3.0)


class TestUltimate:
    def test_rainblade_chain_full_account(self, compiled):
        """大招全链：结 9 起手 → 3×啼泽雨斩（0.24 单体 + 各摘 3 结 + 结爆 0.6 全体）+
        黄泉返渡 1.2 全体 + 全摘 + Thunder Core 6×0.25（expected 全落 e1）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _knots(eng, "e1", 9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(
            hp1 - e1.current_hp,
            (3 * 0.24 + 3 * 0.6 + 1.2 + 6 * 0.25) * ATK * Z, rel_tol=1e-9), (
            "e1：3 雨斩 + 3 结爆 + 返渡 + 6 Core")
        assert math.isclose(
            hp2 - e2.current_hp,
            (3 * 0.6 + 1.2) * ATK * Z, rel_tol=1e-9), "e2：3 结爆 + 返渡"
        assert "ULT_KNOT_LOCK" in _ach(eng).modifiers
        assert math.isclose(_ach(eng).resources["_ult_seg"], 0.0), "段计数末位复位"
        assert "CRIMSON_KNOT" not in e1.modifiers, (
            "返渡+后处理全摘（无 QA 起手——on_wave_start 不首发、无溢出，QA 消耗链不成立）")
        assert math.isclose(_ach(eng).resources["slashed_dream"], 0.0), "9-9 成本归零"

    def test_no_knots_no_detonation(self, compiled):
        """无结起手（摘除开战结）：3 雨斩 + 返渡 + Core，结爆不发（n=0 官方歧义按不发）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        for tgt in (e1, e2):
            tgt.modifiers.pop("CRIMSON_KNOT", None)   # 摘除开战 5 结+天赋 1（纯无结场景）
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (3 * 0.24 + 1.2 + 6 * 0.25) * ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.2 * ATK * Z, rel_tol=1e-9)

    def test_battle_knots_chain(self, compiled):
        """开战结链（不动手）：开战 5 结+天赋 1=6 → 雨斩 1/2 段各摘 3 引爆 0.6、段 3 无结."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(
            hp1 - e1.current_hp,
            (3 * 0.24 + 2 * 0.6 + 1.2 + 6 * 0.25) * ATK * Z, rel_tol=1e-9), (
            "e1：3 雨斩 + 2 结爆（段1/2 各摘 3）+ 返渡 + 6 Core")
        assert math.isclose(
            hp2 - e2.current_hp,
            (2 * 0.6 + 1.2) * ATK * Z, rel_tol=1e-9), "e2：2 结爆 + 返渡"

    def test_qa_consume_benefit(self, compiled):
        """QA ≥ 1 开大：消耗 1 层 → +1 残梦 + 随机敌 +1 结（ULT_KNOT_LOCK 不挡 QA 结）."""
        eng = _make(compiled)
        st = _ach(eng)
        st.modifiers["QUADRIVALENT_ASCENDANCE"] = Modifier(
            modifier_id="QUADRIVALENT_ASCENDANCE", name="四相断我状态", modifier_type="buff",
            stacks=2, max_stack=3, duration=0, dispellable=False)
        _ult(eng)
        assert math.isclose(st.modifiers["QUADRIVALENT_ASCENDANCE"].stacks, 1.0)
        assert math.isclose(st.resources["slashed_dream"], 1.0), "9-9 成本 +QA 消耗返 1"
        assert math.isclose(
            eng.state.actors["e1"].modifiers.get("CRIMSON_KNOT") and
            eng.state.actors["e1"].modifiers["CRIMSON_KNOT"].stacks or 0.0, 1.0,
            ), "QA 消耗补 +1 结（返渡全摘后重新附上）"


class TestEidolons:
    def test_e2_delta_two_vs_three_nihility(self):
        """E2 门控勘正：2 虚无 → 0.15+0.45=0.60；3 虚无 → 基础 0.60 不加（draft
        enable_if >=2 在 3 虚无时 1.05 双重计算幻视）."""
        eng2 = _make(_compiled(eidolon=2, extra_nihility=1))
        assert math.isclose(
            eng2.pipeline.effective_stats(_ach(eng2))["dmg_bonus"].get("all", 0.0),
            0.60, rel_tol=1e-9), "2 虚无：基础 0.15 + E2 差额 0.45"
        eng3 = _make(_compiled(eidolon=2, extra_nihility=2))
        assert math.isclose(
            eng3.pipeline.effective_stats(_ach(eng3))["dmg_bonus"].get("all", 0.0),
            0.60, rel_tol=1e-9), "3 虚无：基础 0.60 独立成立（差额件 enable_if ==2 不加）"

    def test_e4_ult_scoped_vuln(self):
        """E4：进战敌人大招易伤 +8%（hit_condition ult 限定——普攻/战技不吃）."""
        eng = _make(_compiled(eidolon=4))
        e1 = eng.state.actors["e1"]
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert "E4_ULT_VULN" in e1.modifiers
        hp1 = e1.current_hp
        _cast(eng, "1308", "130801")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK * Z, rel_tol=1e-9), (
            "普攻不吃 ult 易伤（eidolon=4 含 E3 → 普攻 lv7=1.1 联动）")
        hp1b = e1.current_hp
        e2 = eng.state.actors["e2"]
        e1.modifiers.pop("CRIMSON_KNOT", None)
        e2.modifiers.pop("CRIMSON_KNOT", None)   # 摘除开战结（纯看 E4 链）
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        eng.bus.emit("actor_enter", {"actor": "e2", "actor_type": "monster"}, eng.state)
        # 两次 E4_VULN 落敌各触发天赋：+1 结×2 落结最多敌（并列按池序=e1）→ e1 结 2
        hp1b, hp2b = e1.current_hp, e2.current_hp
        _ult(eng)
        z_ult = Z * 1.08   # 全段标 ultimate → E4 scoped 全吃
        assert math.isclose(
            hp1b - e1.current_hp,
            (3 * 0.2592 + 0.486 + 1.296 + 6 * 0.25) * ATK * z_ult, rel_tol=1e-9), (
            "e1：3 雨斩（E3 lv12=0.2592）+ 结爆 0.486（结 2 全摘 min(0.162×3,0.648)）"
            "+ 返渡 1.296 + 6 Core，全 ×1.08")
        assert math.isclose(
            hp2b - e2.current_hp,
            (0.486 + 1.296) * ATK * z_ult, rel_tol=1e-9), "e2：结爆 + 返渡 ×1.08"

    def test_e6_res_pen(self):
        """E6：常驻抗性穿透 20%（全伤害皆属大招判据——单通道无观察差）."""
        eng = _make(_compiled(eidolon=6))
        assert math.isclose(eng.pipeline.effective_stats(_ach(eng))["res_pen"],
                            0.2, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：全体 2.0×ATK 雷伤 + 无视弱点削韧 20（tough_scope all——物理弱点也削）+
        四相断我 +1."""
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
             "max_toughness": 100, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
        c = compile_encounter(_build(pre_battle=True), stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(c)
        e1 = eng.state.actors["e1"]
        assert math.isclose(1e9 - e1.current_hp,
                            2.0 * ATK * 0.5 * 0.8 * 0.9 * 1.025,
                            rel_tol=1e-6), (
            "全体 2.0×ATK（物理弱点下雷伤：防御区 0.5×非弱点抗性 0.8×未击破 0.9×期望暴击 1.025）")
        assert e1.toughness == 100 - 20, "无视弱点削韧（toughness_scope: all）"
        assert math.isclose(_ach(eng).modifiers["QUADRIVALENT_ASCENDANCE"].stacks, 1.0)
