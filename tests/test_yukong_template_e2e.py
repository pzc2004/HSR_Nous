"""驭空 1207 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 号令循环/
终结技双增/天赋 rider/大行迹门控/星魂全链 → 手算全等.

过堂复核结论：本件干净（fixture 头注同录）——计数/重烘/门控/闩全在轨，无勘正项。

口径常数：驭空白值 atk 599.76、spd 107、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9。号令 lv10
ATK+80%/层（2 层 = 区 2.6）；终结技 lv10 双增 28%/65%。普攻 lv6=1.0。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

YK_ATK = 599.76
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1207", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "imaginary",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _yk(eng):
    return eng.state.actors["1207"]


def _ally_atk(eng):
    return eng.pipeline.effective_stats(eng.state.actors["ally"])["atk"]


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


class TestYukongCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1207"]
        assert decls["_bowstrings"]["max"] == 2
        assert {"_skill_turn", "_talent_cd", "_archerion_cd"} <= set(decls)


class TestBowstrings:
    def test_skill_two_stacks_rebake(self, compiled):
        """战技：号令 2 层 → 全队 ATK+160%（区 2.6——计数+重烘双件）."""
        eng = _make(compiled)
        assert math.isclose(_ally_atk(eng), 1500.0, rel_tol=1e-9), "开战 0 层"
        _cast(eng, "1207", "120702")
        s = _yk(eng)
        assert math.isclose(s.resources["_bowstrings"], 2.0)
        assert math.isclose(_ally_atk(eng), 1500.0 * 2.6, rel_tol=1e-9), "2 层重烘 1.6"

    def test_decay_and_self_turn_exempt(self, compiled):
        """号令衰减：他人回合结束 -1 层重烘（区 1.8）；驭空自身回合结束不耗层."""
        eng = _make(compiled)
        _cast(eng, "1207", "120702")
        eng.bus.emit("on_turn_end", {"actor": "1207"}, eng.state)
        assert math.isclose(_yk(eng).resources["_bowstrings"], 2.0), "自身回合不耗层"
        eng.bus.emit("on_turn_end", {"actor": "ally"}, eng.state)
        assert math.isclose(_yk(eng).resources["_bowstrings"], 1.0)
        assert math.isclose(_ally_atk(eng), 1500.0 * 1.8, rel_tol=1e-9), "1 层重烘 0.8"

    def test_majestas_energy(self, compiled):
        """Majestas：号令在场队友行动 → 驭空 +2 能量（不含驭空自身保守读）."""
        eng = _make(compiled)
        _cast(eng, "1207", "120702")
        s = _yk(eng)
        e0 = s.current_energy
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(s.current_energy, e0 + 2.0), "辅手行动 +2"
        _cast(eng, "1207", "120701")
        assert math.isclose(s.current_energy, e0 + 2.0 + 20.0), (
            "驭空自身普攻只回 20（不含自身在案）")


class TestUltimate:
    def test_ult_crit_burst(self, compiled):
        """大招：3.8 对轴 + 号令在场全队暴击 28%/暴伤 65% 1 回合（lv10 #2/#3）."""
        eng = _make(compiled)
        _cast(eng, "1207", "120702")
        m7 = _yk(eng)
        m7.current_energy = 130.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1207"] if a.action_id == "120703")
        assert eng._fire_ultimate(m7, ult) is True
        # 本发吃双增（on_become_target 伤害前挂——待实测在案）：crit 区 1+0.33×1.15；
        # atk 区 2.6（号令 2 层）；Bowmaster 1.12
        crit_zone = 1 + (0.05 + 0.28) * (0.5 + 0.65)
        assert math.isclose(hp1 - e1.current_hp,
                            3.8 * YK_ATK * 2.6 * 1.12 * 0.5 * 0.9 * crit_zone, rel_tol=1e-9)
        ally = eng.state.actors["ally"]
        assert "ROARING_ULT_BURST" in ally.modifiers
        eff = eng.pipeline.effective_stats(ally)
        assert math.isclose(eff["crit_rate"], 0.05 + 0.28, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], 0.5 + 0.65, rel_tol=1e-9)


class TestTraces:
    def test_talent_rider_and_cd(self, compiled):
        """天赋：普攻附加 80% 虚数伤（lv10 param(120704,1)；40% 系 lv1 档）+ 冷却闩."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1207", "120701")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.0 + 0.8) * YK_ATK * Z * 1.12, rel_tol=1e-9)
        assert math.isclose(_yk(eng).resources["_talent_cd"], 1.0)
        hp1 = e1.current_hp
        _cast(eng, "1207", "120701")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * YK_ATK * Z * 1.12, rel_tol=1e-9), (
            "冷却闩在场：本发无附加段")

    def test_bowmaster_and_archerion(self, compiled):
        """Bowmaster：驭空（虚数）普攻 ×1.12（元素门控）；青镞：免疫 debuff + 触发后闩."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1207", "120701")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.0 + 0.8) * YK_ATK * Z * 1.12, rel_tol=1e-9), (
            "Bowmaster 0.12（虚数角色等价承载）")
        from hsr_nous.sim.state import Modifier as _M
        applied = eng._apply_modifier(_yk(eng), _M(
            modifier_id="D1", name="负面", modifier_type="debuff", duration=2))
        assert applied is False, "青镞免疫 debuff（grants_immune 通道）"
        assert math.isclose(_yk(eng).resources["_archerion_cd"], 2.0), "触发后 2 回合闩"
        # 闩期间：条件件未启用 → 免疫不在场（pipeline.modifier_enabled 引擎补口）
        applied2 = eng._apply_modifier(_yk(eng), _M(
            modifier_id="D2", name="负面二", modifier_type="debuff", duration=2))
        assert applied2 is True, "闩期间免疫关闭（条件件未启用=不在场）"


class TestEidolons:
    def test_e4_dmg_up_with_stacks(self):
        """E4：号令在场增伤 +30%（enable_if res_ 平铺门控——0 层不吃）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(
            eng.pipeline.effective_stats(_yk(eng))["dmg_bonus"].get("all", 0.0), 0.12, rel_tol=1e-9), (
            "0 层仅 Bowmaster（E4 不起）")
        _cast(eng, "1207", "120702")
        assert math.isclose(
            eng.pipeline.effective_stats(_yk(eng))["dmg_bonus"].get("all", 0.0), 0.42, rel_tol=1e-9), (
            "2 层：Bowmaster 0.12 + E4 0.30")

    def test_e6_ult_grant_stack(self):
        """E6：终结技授 1 层（cap 2——0 层时 0→1 并重烘）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        m7 = _yk(eng)
        m7.current_energy = 130.0
        ult = next(a for a in eng.actions_by_actor["1207"] if a.action_id == "120703")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(m7.resources["_bowstrings"], 1.0)
        # E3 联动：战技 lv12 档 atk_pct=0.88——1 层区 1.88
        assert math.isclose(_ally_atk(eng), 1500.0 * 1.88, rel_tol=1e-9)
