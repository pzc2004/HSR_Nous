"""丹恒·饮月 1213 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 →
四档普攻/擎手喝破双件/逆鳞抵扣/终结技/星魂全链 → 手算全等.

过堂勘正四件+引擎补口两件（fixture 头注同录）：before_consume payload +reason
行动归属 / 逆鳞抵扣收录 / 1213101 开局回能翻案 / cc_res 死键删除 /
E6 replace 重烘 / 首次挂载 stacks clamp（击数>cap 唯一缺口）。

口径常数：饮月白值 atk 698.544、spd 102、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9。
擎手 lv10 每层 0.1 cap 6；喝破 lv10 每层 0.12 cap 4；逆鳞上限 3。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

IL_ATK = 698.544
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1213", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member],
         "policy": {"name": "p", "action_rules": [
             {"condition": "true", "action": "skill", "priority": 50},
             {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled, *, sp: int = 5):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=sp)
    eng.setup()
    return eng


def _il(eng):
    return eng.state.actors["1213"]


def _cast(eng, aid, target_id="e1"):
    il = _il(eng)
    a = next(x for x in eng.actions_by_actor["1213"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(il, a)
    eng.bus.emit("on_action", {
        "actor": "1213", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": il.actor.actor_type}, eng.state)


class TestImbibitorCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1213"]
        assert decls["squama"]["max"] == 3


class TestBasicChain:
    def test_zezhi_zero_cost_stacks(self, compiled):
        """泽芝：0 耗产 1 点 + 擎手 2 层（cap 6）+ 1.0 lv6 对轴."""
        eng = _make(compiled, sp=3)
        e1 = eng.state.actors["e1"]
        sp0 = eng.state.skill_points
        hp1 = e1.current_hp
        _cast(eng, "121301")
        assert eng.state.skill_points == sp0 + 1, "普攻产 1 点"
        assert math.isclose(hp1 - e1.current_hp, 1.0 * IL_ATK * Z, rel_tol=1e-9)
        assert _il(eng).modifiers["RH_STACKS"].stacks == 2
        assert math.isclose(
            eng.pipeline.effective_stats(_il(eng))["dmg_bonus"].get("all", 0.0),
            0.2, rel_tol=1e-9), "2 层 ×0.1 重烘"

    def test_panna_seven_hits_cap(self, compiled):
        """盘拏耀跃：3 耗 SP 5→2；擎手 7 击 clamp cap 6（首次挂载 clamp 引擎补口）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "121312")
        assert eng.state.skill_points == 2
        assert _il(eng).modifiers["RH_STACKS"].stacks == 6, "7 击 clamp cap 6"
        assert _il(eng).modifiers["OUTROAR_STACKS"].stacks == 4, "自第 4 击起 4 层"
        assert math.isclose(hp1 - e1.current_hp, 5.0 * IL_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.8 * IL_ATK * Z, rel_tol=1e-9)
        es = eng.pipeline.effective_stats(_il(eng))
        assert math.isclose(es["dmg_bonus"].get("all", 0.0), 0.6, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.5 + 0.12 * 4, rel_tol=1e-9)


class TestSquama:
    def test_ult_gain_and_deduct(self, compiled):
        """逆鳞：大招 +2 → 瞬华 1 耗全抵（SP 不动逆鳞 −1）→ 天矢阴 2 耗抵 1 扣 1."""
        eng = _make(compiled)
        il = _il(eng)
        il.current_energy = 140.0
        ult = next(x for x in eng.actions_by_actor["1213"] if x.action_id == "121303")
        assert eng._fire_ultimate(il, ult) is True
        assert math.isclose(il.resources["squama"], 2.0), "终结技 +2（param(121303,3) 恒定）"
        sp0 = eng.state.skill_points
        _cast(eng, "121308")
        assert eng.state.skill_points == sp0, "1 耗全抵 SP 不动"
        assert math.isclose(il.resources["squama"], 1.0)
        _cast(eng, "121310")
        assert eng.state.skill_points == sp0 - 1, "2 耗抵 1 扣 1"
        assert math.isclose(il.resources["squama"], 0.0)

    def test_no_deduct_without_squama(self, compiled):
        """无逆鳞不抵：天矢阴 2 耗全扣 SP."""
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        _cast(eng, "121310")
        assert eng.state.skill_points == sp0 - 2

    def test_technique_squama(self):
        """秘技：全体 120% ATK + 逆鳞 +1."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1213", "technique": "121307"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        assert math.isclose(1e9 - e1.current_hp, 1.2 * IL_ATK * Z, rel_tol=1e-9)
        assert math.isclose(_il(eng).resources["squama"], 1.0)


class TestUltimate:
    def test_ult_blast_full_axis(self, compiled):
        """大招：主 3.0 邻 1.4 lv10——吃擎手 0.6 + 喝破暴伤 0.48 全对轴."""
        eng = _make(compiled)
        _cast(eng, "121312")   # 先叠擎手 6 层+喝破 4 层
        il = _il(eng)
        il.current_energy = 140.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(x for x in eng.actions_by_actor["1213"] if x.action_id == "121303")
        assert eng._fire_ultimate(il, ult) is True
        crit_zone = 1 + 0.05 * 0.98
        assert math.isclose(hp1 - e1.current_hp,
                            3.0 * IL_ATK * 0.5 * 0.9 * crit_zone * 1.6, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp,
                            1.4 * IL_ATK * 0.5 * 0.9 * crit_zone * 1.6, rel_tol=1e-9)


class TestEidolons:
    def test_e1_parallel_stacks(self):
        """E1：擎手双件并行 6+4=10——泽芝 2 击 E1 件 2 层."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast(eng, "121301")
        il = _il(eng)
        assert il.modifiers["RH_STACKS"].stacks == 2
        assert il.modifiers["RH_STACKS_E1"].stacks == 2
        assert math.isclose(
            eng.pipeline.effective_stats(il)["dmg_bonus"].get("all", 0.0),
            0.1 * (2 + 2), rel_tol=1e-9)

    def test_e2_advance_and_squama(self):
        """E2：终结技后拉条 100% + 逆鳞 +1（与基础 +2 合计 3 cap）."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        il = _il(eng)
        il.current_energy = 140.0
        ult = next(x for x in eng.actions_by_actor["1213"] if x.action_id == "121303")
        assert eng._fire_ultimate(il, ult) is True
        assert math.isclose(il.resources["squama"], 3.0), "基础 +2 + E2 +1（cap 3）"

    def test_e6_res_pen_next_panna(self):
        """E6：队友终结技叠计数 → 下一次盘拏耀跃本发吃抗穿 20%/层 + 摘双件（消耗型）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        il = _il(eng)
        for _ in range(2):
            eng.bus.emit("on_ultimate", {"source": "ally", "action": "ally_ult",
                                         "target": "e1"}, eng.state)
        assert il.modifiers["S6_STACKS"].stacks == 2
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "121312")
        # 本发即吃（on_become_target 伤害前挂）；E3 联动：普攻 lv7 档 5.5（非 lv6 5.0）
        assert math.isclose(hp1 - e1.current_hp,
                            5.5 * IL_ATK * 0.5 * 0.9 * 1.025 * 1.4, rel_tol=1e-9)
        assert "S6_STACKS" not in il.modifiers, "消耗摘计数"
        assert "S6_RESPEN" not in il.modifiers, "该次结算后摘加成件（防二连动残留）"
        # 第二发：S6 抗穿已消耗（抗区回 1.0），但吃第一发叠的天赋满层——
        # 擎手 10 层（6+4 E1 并行，E5 lv12 每层 0.11→增伤区 2.1）+ 喝破 4 层
        #（E3 lv12 每层 0.132→crit_dmg 1.028，crit 区 1.0514）
        hp1 = e1.current_hp
        _cast(eng, "121312")
        assert math.isclose(hp1 - e1.current_hp,
                            5.5 * IL_ATK * 0.5 * 0.9 * 1.0514 * 2.1, rel_tol=1e-9), (
            "S6 已消耗无抗穿，天赋叠层照吃")
