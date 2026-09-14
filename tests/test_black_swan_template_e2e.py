"""黑天鹅 1307 模板端到端对轴（验收型批·加强版单轨）：真模板 YAML → 编译 →
奥迹 DoT/顿悟/行迹/星魂全链 → 手算全等.

口径常数：黑天鹅白值 atk 659.736、crit 0.05/0.5（期望暴击区 1.025）、EHR 0；
假人 def 1000 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9 → Z=0.46125。
奥迹 DoT lv10 倍率 = #1 2.4 + #3 0.12×(层数-1)（加法口径在案）——走 deal_damage
带期望暴击区（全库触电同族口径；官方 DoT 不暴击的偏差在案待裁）。
顿悟 lv10 承伤 +25%（vulnerability 在案键）；行迹 65% base 期望恒生效。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BS_ATK = 659.736
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1307", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1307", "technique": "1130707"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["wind"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _bs(eng):
    return eng.state.actors["1307"]


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


def _arcana(eng, aid, stacks):
    """直接挂奥迹（测试装填——绕过概率判定槽）."""
    eng._apply_modifier(eng.state.actors[aid], Modifier(
        modifier_id="ARCANA", name="奥迹", modifier_type="debuff",
        stacks=stacks, max_stack=50, stack_mode="refresh", duration=0, dispellable=True))


def _ult(eng):
    st = _bs(eng)
    st.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["1307"] if a.action_id == "1130703")
    assert eng._fire_ultimate(st, ult) is True


def _tick(stacks):
    return (2.4 + 0.12 * (stacks - 1)) * BS_ATK * Z


class TestBlackSwanCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1307"]}
        assert acts == {"1130701", "1130702", "1130703"}
        decls = compiled.resource_decls_by_actor["1307"]
        assert {"_epiphany_saved", "_e6_guard", "_ch_talent_dot", "_ch_trace1",
                "_ch_trace2_enter", "_ch_trace2_def", "_ch_e6_team"} <= set(decls)


class TestArcanaDot:
    def test_tick_stacks_talent_and_halve(self, compiled):
        """奥迹 3 层跳伤 = (2.4+0.12×2)×ATK×Z → 65% 天赋 +1（期望恒生效）→ 减半 round(4/2)."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _arcana(eng, "e1", 3)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, _tick(3), rel_tol=1e-9)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 2.0), (
            "3+1=4 → 减半 round(4/2)=2（结算后减半口径在案）")

    def test_epiphany_first_tick_no_halve(self, compiled):
        """顿悟首跳免减半（闩置 1）——次跳恢复减半；顿悟承伤 +25% 入跳伤；
        大招生效序在案：1130701 命中 +5 层、11307102 减防（def 792 区）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _arcana(eng, "e1", 3)
        _ult(eng)
        assert "EPIPHANY" in e1.modifiers
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 8.0), "大招命中 11307101 +5（期望恒生效）"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        tick = (2.4 + 0.12 * 7) * BS_ATK * (1000 / (1000 + 792)) * 0.9 * 1.025 * 1.25
        assert math.isclose(hp1 - e1.current_hp, tick, rel_tol=1e-9), (
            "8 层跳伤 ×（减防区 1000/1792）×（顿悟承伤 1.25）")
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 9.0), (
            "8+1=9——首跳免减半（闩置 1）")
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 5.0), (
            "次跳：9+1=10 → 减半 round(10/2)=5")


class TestSkillAndTraces:
    def test_skill_def_down_blast(self, compiled):
        """战技：主+相邻 DEF -20.8%（lv10 param #4；受击事件天然收敛 Blast 命中域）."""
        eng = _make(compiled)
        _cast(eng, "1307", "1130702")
        for aid in ("e1", "e2"):
            tgt = eng.state.actors[aid]
            assert "ARCANA_DEF_DOWN" in tgt.modifiers
            assert math.isclose(eng.pipeline.effective_stats(tgt)["def_"],
                                1000 * (1 - 0.208), rel_tol=1e-9)

    def test_trace1_attacked_stacks(self, compiled):
        """11307101：黑天鹅攻击命中 → 65%（期望恒生效）+5 层奥迹."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng.bus.emit("on_become_target", {
            "source": "1307", "target": "e1", "action_type": "basic"}, eng.state)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 5.0)

    def test_trace2_enter_and_basic_def_down(self, compiled):
        """11307102：进战 65% +1 层；普攻命中 100% 施战技 DEF 降低（#2=1 勘正）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 1.0)
        _cast(eng, "1307", "1130701")
        assert "ARCANA_DEF_DOWN" in e1.modifiers

    def test_trace3_team_dmg_by_ehr(self, compiled):
        """11307103：全队增伤 = 60%×EHR（封顶 72%）——EHR 0.5 → 30%；EHR 2.0 → 72% 封顶."""
        eng = _make(compiled)
        bs = _bs(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.0, abs_tol=1e-9), "EHR 0 → 无增伤"
        eng._apply_modifier(bs, Modifier(
            modifier_id="EHR_FIX", name="EHR", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"effect_hit": 0.5}))
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.6 * 0.5, rel_tol=1e-9)
        eng._apply_modifier(bs, Modifier(
            modifier_id="EHR_FIX2", name="EHR2", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"effect_hit": 1.5}))
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.72, rel_tol=1e-9), "60%×2.0=1.2 → 封顶 0.72"


class TestEidolons:
    def test_e2_enter_30_stacks(self):
        """E2（新版）：进战 100% 基础概率陷入 **30 层**奥迹（actor_enter）——
        与行迹 11307102 进战 +1 同 emit 两钩同发，合计 31."""
        eng = _make(_compiled(eidolon=2))
        e1 = eng.state.actors["e1"]
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 31.0), (
            "E2 30 + 11307102 1（同 actor_enter 两钩同发）")

    def test_e4_vuln_and_unlimited_energy(self):
        """E4（新版）：揭露中承伤额外 +20%（E4_VULN）+ 回能无每轮限制（两次回合开始 +16）."""
        eng = _make(_compiled(eidolon=4))
        e1 = eng.state.actors["e1"]
        bs = _bs(eng)
        _ult(eng)
        assert "E4_VULN" in e1.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"],
                            0.25 + 0.2, rel_tol=1e-9), "顿悟 25%+E4 20%（同 zone 加算）"
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(bs.current_energy, 5.0 + 8.0 + 8.0), (
            "新版回能无每轮 1 次限制（大招回 5 + 8×2）")

    def test_e6_team_stack_and_guaranteed_extra(self):
        """E6（新版）：队友攻击 65% 施加 → 同笔必发 +1（=2 层）；11307101 +5 →
        同笔必发 +1（=6 层）——「每当黑天鹅使敌方陷入奥迹」含 E6 机制 1 施加源."""
        eng = _make(_compiled(eidolon=6))
        e1 = eng.state.actors["e1"]
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 2.0), (
            "E6 机制 1 施加 1 + 机制 2 同笔必发 1")
        eng.bus.emit("on_become_target", {
            "source": "1307", "target": "e1", "action_type": "basic"}, eng.state)
        assert math.isclose(e1.modifiers["ARCANA"].stacks, 2.0 + 5.0 + 1.0), (
            "11307101 +5 + 机制 2 同笔必发 +1")


class TestTechnique:
    def test_pre_battle_arcana(self):
        """秘技：开战全体敌人 +1 层奥迹（首环 150% 直挂——链式递减待收）."""
        eng = _make(_compiled(pre_battle=True))
        for aid in ("e1", "e2"):
            assert math.isclose(eng.state.actors[aid].modifiers["ARCANA"].stacks, 1.0)
