"""黑塔 1013 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → AoE 双技/
天赋跨线追击/E1-E6 星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：天赋回能 5 收编（gain_energy 原语——draft 误判无槽键）/
Icing 注记升级（target_controlled 不可分控制类型维持待收）。

口径常数：黑塔白值 atk 582.12、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 →
防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.0。天赋跨线判定 =
命中后 hp ≤50% 且 hp+amount（命中前快照）>50%。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

HT_ATK = 582.12
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1013", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

#: 低血舞台（天赋跨线判定场）：max 1000，便于手控 50% 线
_STAGE_LOW = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _ht(eng):
    return eng.state.actors["1013"]


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


class TestHertaCompile:
    def test_actions_no_talent_entry(self, compiled):
        """天赋不建 action（hook 承载——避免与政策层双记账）；终结技 AoE 能量 110."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1013"]}
        assert set(acts) == {"101301", "101302", "101303"}
        assert acts["101303"].target_type == "aoe" and acts["101303"].energy_cost == 110
        assert acts["101302"].target_type == "aoe" and acts["101302"].skill_point_cost == 1


class TestAoeActions:
    def test_skill_ult_aoe(self, compiled):
        """战技 AoE 1.0 / 终结技 AoE 2.0（lv10）双敌同吃——战技满血场吃 HP≥50%
        增伤件（20%+25%=1.45，2026-09-23 收编），终结技无冻结不吃 Icing."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1013", "101302")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * HT_ATK * Z * 1.45, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.0 * HT_ATK * Z * 1.45, rel_tol=1e-9)
        m7 = _ht(eng)
        m7.current_energy = 110.0
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(a for a in eng.actions_by_actor["1013"] if a.action_id == "101303")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.0 * HT_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 2.0 * HT_ATK * Z, rel_tol=1e-9)
        assert math.isclose(m7.current_energy, 5.0)


class TestTalentCrossLine:
    def test_cross_triggers_fua_and_energy(self):
        """跨线（命中前 >50% → 命中后 ≤50%）：全体追加 0.4×ATK + 回能 5（过堂收编实证）；
        已在 ≤50% 的目标再命中不重复触发."""
        compiled = compile_encounter(_build(), _STAGE_LOW, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 520.0   # >50%×1000
        hp2 = e2.current_hp
        _cast(eng, "1013", "101301")   # lv6=1.0×582.12×0.46125 ≈ 268 → 252 ≤ 500 跨线
        fua = 0.4 * HT_ATK * Z
        assert math.isclose(e1.current_hp, 520.0 - 1.0 * HT_ATK * Z - fua, rel_tol=1e-9), (
            "e1 = 普攻 + 天赋追加（全体含触发目标）")
        assert math.isclose(hp2 - e2.current_hp, fua, rel_tol=1e-9), "e2 吃追加（全体域）"
        assert math.isclose(_ht(eng).current_energy, 20.0 + 5.0), "普攻 20 + 追加回能 5 收编"
        hp2 = e2.current_hp
        _cast(eng, "1013", "101301")   # e1 已 ≤50%——跨线条件不成立
        assert math.isclose(hp2 - e2.current_hp, 0.0, rel_tol=1e-9), "非跨线不重复触发"


class TestEidolons:
    def test_e1_basic_low_hp_bonus(self):
        """E1：普攻命中已 ≤50% 目标追加 0.4×ATK（与天赋跨线分离——本发无跨线）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE_LOW, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 400.0   # 已 ≤50%（400+268<500？不——400+268=668>500 会跨线！取 200 隔离）
        e1.current_hp = 200.0   # 200+268=468 ≤ 500——不跨线，纯 E1 域
        hp2 = e2.current_hp
        _cast(eng, "1013", "101301")
        assert math.isclose(e1.current_hp, 200.0 - 1.0 * HT_ATK * Z - 0.4 * HT_ATK * Z,
                            rel_tol=1e-9), "e1 = 普攻 + E1 追加 0.4（无天赋跨线）"
        assert math.isclose(hp2 - e2.current_hp, 0.0, rel_tol=1e-9), "e2 无天赋追加（未跨线）"

    def test_e2_crit_stacks(self):
        """E2：跨线 → 暴击率 +3%/层（计数+烘焙双件）——有效暴击 0.05+0.03."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE_LOW, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 520.0
        _cast(eng, "1013", "101301")
        m7 = _ht(eng)
        assert "E2_CR_STACKS" in m7.modifiers
        assert math.isclose(eng.pipeline.effective_stats(m7)["crit_rate"], 0.08, rel_tol=1e-9)

    def test_e4_dmg_up_on_trigger(self):
        """E4：跨线 → 增伤 10% 1 回合——下一发普攻吃 1.1 桶（E3 普攻+1=lv7 1.1 倍、
        E2 跨线暴击 0.08 → 期望暴击区 1.04，eidolon=4 全联动在案）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE_LOW, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 520.0
        _cast(eng, "1013", "101301")
        assert "E4_DMG_UP" in _ht(eng).modifiers
        e2 = eng.state.actors["e2"]
        hp2 = e2.current_hp
        _cast(eng, "1013", "101301", target=e2)
        z_e2 = 0.5 * 0.9 * (1 + 0.08 * 0.5)   # E2 跨线后 crit 0.08
        assert math.isclose(hp2 - e2.current_hp, 1.1 * HT_ATK * z_e2 * 1.1, rel_tol=1e-9), (
            "lv7 普攻 1.1 × E4 增伤 1.1（E2 暴击区 0.468）")

    def test_e6_atk_up_after_ult(self):
        """E6：大招（E5 → lv12=2.16）后 ATK +25% 1 回合——下一发普攻（E5 普攻+1=lv7
        1.1 倍）按 1.25×白值面板."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _ht(eng)
        m7.current_energy = 110.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1013"] if a.action_id == "101303")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.16 * HT_ATK * Z, rel_tol=1e-9), "E5 大招 lv12=2.16"
        assert "E6_ATK_UP" in m7.modifiers
        assert math.isclose(eng.pipeline.effective_stats(m7)["atk"], HT_ATK * 1.25, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1013", "101301")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * HT_ATK * 1.25 * Z, rel_tol=1e-9), (
            "lv7 普攻 1.1 × E6 面板 1.25")
