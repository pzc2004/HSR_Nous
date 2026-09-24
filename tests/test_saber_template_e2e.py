"""Saber 1014 模板端到端对轴（验收型批·组2 复杂件）：真模板 YAML → 编译 → 共鸣循环/
战技双分支/弹射/替换普攻/星魂全链 → 手算全等.

过堂四件（fixture 头注同录）：战技双分支收编（$self.energy 白名单证伪挡因）/
A2 开战回填收编（gain_energy 原生池）/ E1 dmg_ultimate_dmg_boost 收编 /
天赋 duration param→int 纪律。

口径常数：Saber 白值 atk 601.524；A1 常驻 crit_rate +0.20 → 有效暴击率 0.25，
期望暴击区 = 1 + 0.25×crit_dmg_eff；A3 计数 1 层开战（crit_dmg 0.54 → 区 1.135）。
假人 def 0 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6 口径。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SB_ATK = 601.524
DU = 0.45                        # 防御区×未击破
CRIT_RATE = 0.25                 # 0.05 白值 + 0.20 A1


def _cz(crit_dmg: float) -> float:
    return 1 + CRIT_RATE * crit_dmg


def _build(*, eidolon: int = 0):
    member = {"character_template": "1014", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "wind",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


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
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _sb(eng):
    return eng.state.actors["1014"]


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
    m7 = _sb(eng)
    m7.current_energy = 360.0
    ult = next(a for a in eng.actions_by_actor["1014"] if a.action_id == "101403")
    assert eng._fire_ultimate(m7, ult) is True


class TestSaberCompile:
    def test_resources_actions_and_a1(self, compiled):
        decls = compiled.resource_decls_by_actor["1014"]
        assert decls["core_resonance"]["max"] == 99 and decls["golden_scepter"]["max"] == 1
        assert decls["overflow_energy"]["max"] == 120
        acts = {a.action_id: a for a in compiled.actions_by_actor["1014"]}
        assert set(acts) == {"101401", "101402", "101403", "101408"}, "强化普攻同册互斥"
        assert acts["101403"].energy_cost == 360
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_sb(eng))["crit_rate"], 0.25), (
            "A1 常驻 +20% 暴击率（trace_stat_effects 通道）")


class TestBattleStart:
    def test_resonance_a3_and_a2_refill(self, compiled):
        """开战：+1 共鸣（天赋 #8）+ A3 计数 1（暴伤 0.54）+ A2 回填 216（过堂收编实证）."""
        eng = _make(compiled)
        s = _sb(eng)
        assert math.isclose(s.resources["core_resonance"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"], 0.54), "A3 1 层 +4%"
        assert math.isclose(s.current_energy, 216.0), "A2 开战回填 0.6×360（gain_energy 原生池）"


class TestSkillBranches:
    def test_normal_branch(self, compiled):
        """常规分支（216+8×1<360 未达强化）：主 1.5/邻 0.75 对轴 + 获 3 共鸣 + A3 计数 3
        + A3 战技暴伤 0.5 挂载."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1014", "101402")
        z = DU * _cz(0.54)          # 结算时 A3 计数 1（开战）
        assert math.isclose(hp1 - e1.current_hp, 1.5 * SB_ATK * z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.75 * SB_ATK * z, rel_tol=1e-9)
        s = _sb(eng)
        assert math.isclose(s.resources["core_resonance"], 4.0), "1+3（Otherwise 分支）"
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"],
                            0.5 + 0.16 + 0.5, rel_tol=1e-9), "A3 4 层 0.16 + 战技暴伤 0.5"
        assert math.isclose(s.current_energy, 216.0), "常规分支不回能不耗共鸣"

    def test_boost_branch(self, compiled):
        """强化分支（352+8×5=392≥360）：主 1.5 + 强化段 0.14×5 对轴（相邻不吃段——
        邻接待收在案）+ 按 8/点回填 clamp 360 + 清空共鸣 + 常规分支互斥不发."""
        eng = _make(compiled)
        s = _sb(eng)
        s.current_energy = 352.0
        s.resources["core_resonance"] = 5.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1014", "101402")
        z = DU * _cz(0.54)
        assert math.isclose(hp1 - e1.current_hp, (1.5 + 0.14 * 5) * SB_ATK * z, rel_tol=1e-9), (
            "主 = 基础 1.5 + 每点 0.14×5（倍率区等值段）")
        assert math.isclose(hp2 - e2.current_hp, 0.75 * SB_ATK * z, rel_tol=1e-9), (
            "相邻仅基础段（邻接追加通道缺在案）")
        assert math.isclose(s.current_energy, 360.0), "8×5 回填 clamp 上限"
        assert math.isclose(s.resources["core_resonance"], 0.0), "攻击后清空共鸣"
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"], 1.04, rel_tol=1e-9), (
            "A3 计数不变（0.54——常规 +3 未发）+ 战技暴伤 0.5 挂载（强化分支同为战技）")


class TestUltimate:
    def test_ult_bounces_scepter_and_talent(self, compiled):
        """大招：AoE 2.8 对轴 + 10 段弹射 1.1/段（expected 全落 e1）+ 替换态闩置 1
        + 天赋（含自身大招在案）：增伤 0.6 二回合 + 3 共鸣 + A3 计数 3."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        z = DU * _cz(0.54)
        assert math.isclose(hp1 - e1.current_hp, (2.8 + 10 * 1.1) * SB_ATK * z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 2.8 * SB_ATK * z, rel_tol=1e-9)
        s = _sb(eng)
        assert math.isclose(s.resources["golden_scepter"], 1.0), "替换态闩置位"
        assert math.isclose(s.resources["core_resonance"], 4.0), "1+3（天赋我方大招）"
        assert "DRAGON_CORE_DMG" in s.modifiers, "天赋增伤 0.6（param(101404,3) lv10）"
        assert math.isclose(s.current_energy, 5.0)


class TestEnhancedBasic:
    def test_enhanced_basic_full_chain(self, compiled):
        """强化普攻（大招后）：AoE lv6=1.5 对轴（吃天赋增伤 1.6 + A3 4 层暴击区）
        + 2 敌追加 1.5 + 闩消耗 + 获 2 共鸣 + 回能 30."""
        eng = _make(compiled)
        _ult(eng)
        s = _sb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1014", "101408")
        z = DU * _cz(0.66)          # A3 4 层 → 暴伤 0.66
        per = (1.5 + 1.5) * SB_ATK * z * 1.6   # 本体 + 2 敌追加（同乘区）
        assert math.isclose(hp1 - e1.current_hp, per, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, per, rel_tol=1e-9)
        assert math.isclose(s.resources["golden_scepter"], 0.0), "闩消耗回常规"
        assert math.isclose(s.resources["core_resonance"], 6.0), "4+2（#2 获 2 共鸣）"
        assert math.isclose(s.current_energy, 5.0 + 30.0)


class TestEidolons:
    def test_e1_ult_boost_bucket(self):
        """E1：终结技伤害 +60%（dmg_ultimate_dmg_boost 收编——AoE 主段吃 1.6 桶；
        弹射段伪 follow_up 不命中 ultimate 桶，口径在案）+ 普攻后 +1 共鸣."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1014", "101401")
        assert math.isclose(_sb(eng).resources["core_resonance"], 2.0), "1+1（E1 普攻/战技）"
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        z = DU * _cz(0.5 + 0.04 * 2)   # A3 2 层（开战 1 + E1 普攻 1）
        assert math.isclose(hp1 - e1.current_hp,
                            2.8 * SB_ATK * z * 1.6 + 10 * 1.1 * SB_ATK * z, rel_tol=1e-9), (
            "主段 1.6 桶（E1）+ 弹射段不吃桶（伪 follow_up 口径在案）")
        assert math.isclose(hp2 - e2.current_hp, 2.8 * SB_ATK * z * 1.6, rel_tol=1e-9)

    def test_e4_res_pen_stacks(self):
        """E4：常驻风抗穿 8% + 每次大招 +4%×3 层——大招后有效 0.12；E3 大招 lv12 随档."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        s = _sb(eng)
        assert math.isclose(eng.pipeline.effective_stats(s)["res_pen"], 0.08, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(s)["res_pen"], 0.12, rel_tol=1e-9), (
            "8% + 4%×1 层（counter+烘焙双件）")
