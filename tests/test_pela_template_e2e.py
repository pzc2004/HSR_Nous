"""佩拉 1106 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 驱散/减防/
天赋回能/Bash 真伤/行迹光环/星魂全链 → 手算全等.

过堂三件（fixture 头注同录）：def_shred→def_pct 负值 / E4 死键摘除 /
天赋·E6·Bash 判据 kind 当 id 死钩勘正（佩拉自件两族近似）。

口径常数：佩拉 atk 645.2712（白值 546.84×1.18——行迹 atk_pct 0.18 B-TR① 回填）、
冰伤池 1.224（行迹 dmg_ice 0.224 同回填）、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9；def 200 假人用于
减防对轴（Exposed −40% → 120）。普攻 lv6=1.0。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

PE_ATK = 546.84 * 1.18     # 645.2712（行迹 atk_pct 0.18 回填——B-TR①）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
ICE = 1.224                # 冰伤池（行迹 dmg_ice 0.224 回填——B-TR①）


def _build(*, eidolon: int = 0):
    member = {"character_template": "1106", "level": 80}
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


def _stage(enemy_def=0.0):
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
         "def": enemy_def, "max_toughness": 9999, "weakness": ["ice"]},
        {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
         "def": enemy_def, "max_toughness": 9999, "weakness": ["ice"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _pe(eng):
    return eng.state.actors["1106"]


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
    m7 = _pe(eng)
    m7.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1106"] if a.action_id == "110603")
    assert eng._fire_ultimate(m7, ult) is True


def _exposed(eng, tid="e1"):
    eng._apply_modifier(eng.state.actors[tid], Modifier(
        modifier_id="PELA_EXPOSED", name="Exposed", modifier_type="debuff", duration=2))


class TestPelaCompile:
    def test_exposed_def_pct(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1106"]}
        mods = {m["modifier_id"]: m for m in acts["110603"].apply_modifiers}
        assert math.isclose(mods["PELA_EXPOSED"]["stat_effects"]["def_pct"], -0.4), (
            "def_shred→def_pct 负值勘正（lv10=−0.4，编译期 param 求值）")


class TestSkill:
    def test_skill_dispel_and_wipe_out(self, compiled):
        """战技：2.1 对轴 + 驱散 1 增益（LIFO 新先摘）+ Wipe Out 窗口（下一击 +20%）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="B1", name="旧增益", modifier_type="buff", duration=2))
        eng._apply_modifier(e1, Modifier(
            modifier_id="B2", name="新增益", modifier_type="buff", duration=2))
        hp1 = e1.current_hp
        _cast(eng, "1106", "110602")
        assert math.isclose(hp1 - e1.current_hp, 2.1 * PE_ATK * Z * ICE, rel_tol=1e-9)
        assert "B2" not in e1.modifiers and "B1" in e1.modifiers, "驱散 LIFO 新先摘"
        assert "PELA_WIPE_OUT" in _pe(eng).modifiers
        hp1 = e1.current_hp
        _cast(eng, "1106", "110601")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * PE_ATK * Z * (ICE + 0.2), rel_tol=1e-9), (
            "Wipe Out 下一击 +20%（增伤池 1.224+0.2=1.424）")


class TestUltimate:
    def test_ult_exposed_def_down(self):
        """大招：AoE 1.0 对轴 + Exposed 减防 40%（def 200→120）+ 天赋吃自身 Exposed
        （apply_modifiers 先挂后伤——on_action 判据成立 +10 能）."""
        compiled = compile_encounter(_build(), _stage(enemy_def=200.0),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        assert "PELA_EXPOSED" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 120.0, rel_tol=1e-9)
        assert math.isclose(_pe(eng).current_energy, 5.0 + 10.0), (
            "释放回能 5 + 天赋 10（lv10——终结技自身 Exposed 时序在案）")


class TestTalentAndBash:
    def test_talent_energy_and_bash_true(self, compiled):
        """天赋：攻击后目标带 Exposed +10 能（自件两族近似实证）；Bash：+20% 真伤段."""
        eng = _make(compiled)
        _exposed(eng, "e1")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1106", "110601")
        basic = 1.0 * PE_ATK * Z * ICE
        assert math.isclose(hp1 - e1.current_hp, basic * 1.2, rel_tol=1e-9), (
            "普攻 + Bash 真伤 0.2×原伤害（category true 跳乘区严格等价）")
        assert math.isclose(_pe(eng).current_energy, 20.0 + 10.0)


class TestEidolons:
    def test_e1_any_kill_energy(self):
        """E1：任一敌方被消灭 +5 能（不区分击杀者——辅手击杀同吃）."""
        compiled = compile_encounter(_build(eidolon=1), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e2 = eng.state.actors["e2"]
        e2.current_hp = 100.0
        _cast(eng, "ally", "ally_basic", target=e2)
        assert not e2.alive
        assert math.isclose(_pe(eng).current_energy, 5.0)

    def test_e2_spd_buff(self):
        """E2：战技后 SPD +10% 二回合."""
        compiled = compile_encounter(_build(eidolon=2), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1106", "110602")
        assert math.isclose(eng.pipeline.effective_stats(_pe(eng))["spd"],
                            105 * 1.1, rel_tol=1e-9)

    def test_e6_feeble_pursuit(self):
        """E6：攻击后 Exposed 目标附加 40% ATK（E3 普攻 lv7=1.1、E5 天赋 lv12=11
        全联动；E6 段同吃 Bash 真伤）."""
        compiled = compile_encounter(_build(eidolon=6), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _exposed(eng, "e1")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1106", "110601")
        hits = (1.1 + 0.4) * PE_ATK * Z * ICE    # 普攻 lv7 + E6 附加
        bash = 0.2 * hits                         # 两段各吃 Bash 真伤
        assert math.isclose(hp1 - e1.current_hp, hits + bash, rel_tol=1e-9)
        assert math.isclose(_pe(eng).current_energy, 20.0 + 11.0), ("E5 天赋+2 → lv12=11（draft 注记写 11.5=lv13 误档，过堂对轴）")
