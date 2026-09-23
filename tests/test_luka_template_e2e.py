"""卢卡 1111 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 裂伤循环/
战意循环/强化普攻结构/引爆/行迹/星魂全链 → 手算全等.

过堂三件（fixture 头注同录）：111108 结构勘正（直冲 3 段 instances + 碎天 hook）/
chance→mechanic_chance / dmg_taken→vulnerability。

口径常数：卢卡 atk 745.1136（白值 582.12×1.28——行迹 atk_pct 0.28 B-TR① 回填）、
crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 → 防御区 0.5、物理弱点 →
抗性区 1.0、未击破 0.9。裂伤 lv10 上限 = min(24%×1e9, 3.38×745.1136)=2518.48；
引爆 lv10 = 0.85×上限。普攻 lv6=1.0；111108 lv6：直冲 0.20/碎天 0.80。
2026-09-23 裂伤迁声明式 dot 通道：跳伤走引擎 A 类结算（eng._tick_dots），
不暴击+施加时刻快照——跳伤期望 = 上限×0.5×0.9（旧事件承载 tick 含期望暴击
1.025 的偏差随迁移消灭，R-LK2 对拍差核销）；直伤钩（含引爆段）仍走期望暴击。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

LK_ATK = 582.12 * 1.28     # 745.1136（行迹 atk_pct 0.28 回填——B-TR①）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
BLEED_CAP = 3.38 * LK_ATK            # lv10 min(24%×1e9, 3.38×ATK)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1111", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _lk(eng):
    return eng.state.actors["1111"]


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


class TestLukaCompile:
    def test_structure_and_vuln(self, compiled):
        decls = compiled.resource_decls_by_actor["1111"]
        assert decls["fighting_will"]["max"] == 4
        acts = {a.action_id: a for a in compiled.actions_by_actor["1111"]}
        assert acts["111108"].instances == 3, "直冲 3 段（结构勘正实证）"
        vuln = [e for h in compiled.hooks
                for e in h.effects
                if e.get("effect_type") == "apply_modifier"
                and e["modifier"]["modifier_id"] == "LUKA_VULN"]
        assert vuln and math.isclose(vuln[0]["modifier"]["stat_effects"]["vulnerability"], 0.2), (
            "dmg_taken→vulnerability 勘正（hook 承载，编译期 param 求值 lv10=0.20）")

    def test_battle_start_will_and_energy(self, compiled):
        eng = _make(compiled)
        s = _lk(eng)
        assert math.isclose(s.resources["fighting_will"], 1.0)
        assert math.isclose(s.current_energy, 3.0), "循环制动：开战层 +3 能（on_resource_gain）"


class TestSkillBleed:
    def test_skill_bleed_dispel_will(self, compiled):
        """战技：1.2 对轴 + 裂伤 3 回合 + 驱散 1 增益（LIFO）+ 战意 +1（+3 能）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="B1", name="旧增益", modifier_type="buff", duration=2))
        eng._apply_modifier(e1, Modifier(
            modifier_id="B2", name="新增益", modifier_type="buff", duration=2))
        hp1 = e1.current_hp
        _cast(eng, "1111", "111102")
        assert math.isclose(hp1 - e1.current_hp, 1.2 * LK_ATK * Z, rel_tol=1e-9)
        assert "LUKA_BLEED" in e1.modifiers and e1.modifiers["LUKA_BLEED"].duration == 3
        assert "B2" not in e1.modifiers and "B1" in e1.modifiers
        s = _lk(eng)
        assert math.isclose(s.resources["fighting_will"], 2.0)
        assert math.isclose(s.current_energy, 30.0 + 3.0 + 3.0), (
            "战技 30 + 开战层 3 + 战技层 3（循环制动逐层）")

    def test_bleed_tick_cap(self, compiled):
        """裂伤 tick（声明式 dot 通道·引擎 A 类结算）：min(24%×1e9, 3.38×ATK)=2518.48
        上限档（角色专属公式，HP 帽形跳伤时求值）——不暴击：0.5(def)×0.9(未击破)."""
        eng = _make(compiled)
        _cast(eng, "1111", "111102")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng._tick_dots(e1)   # 声明式跳伤走引擎 A 类结算（非 on_turn_start 事件）
        assert math.isclose(hp1 - e1.current_hp, BLEED_CAP * 0.5 * 0.9, rel_tol=1e-9)

    def test_bleed_tick_snapshot_atk(self, compiled):
        """快照语义：施加后卢卡 ATK 变动（新挂 atk_pct buff 翻倍面板）——
        跳伤基数仍读施加时刻快照 atk（3.38×745.1136），不随现值重估."""
        eng = _make(compiled)
        _cast(eng, "1111", "111102")
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(_lk(eng), Modifier(
            modifier_id="ATK_UP", name="攻击提升", modifier_type="buff",
            duration=2, stat_effects={"atk_pct": 1.0}))   # 施加后面板 atk×2
        hp1 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp1 - e1.current_hp, BLEED_CAP * 0.5 * 0.9, rel_tol=1e-9), (
            "跳伤基数=$snapshot.atk（施加时刻锁定）×3.38，非跳伤时刻现值")


class TestUltimate:
    def test_ult_will_vuln_energy(self, compiled):
        """大招：3.3 对轴 + 战意 +2（循环制动 +6）+ 易伤 12%（下一发普攻 ×1.12）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        m7 = _lk(eng)
        m7.current_energy = 130.0
        ult = next(a for a in eng.actions_by_actor["1111"] if a.action_id == "111103")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 3.3 * LK_ATK * Z, rel_tol=1e-9)
        assert "LUKA_VULN" in e1.modifiers
        s = _lk(eng)
        assert math.isclose(s.resources["fighting_will"], 3.0)
        assert math.isclose(s.current_energy, 5.0 + 6.0), (
            "5 自身 + 大招 2 层×3（手动充能 130 覆盖开战层在案）")
        hp1 = e1.current_hp
        _cast(eng, "1111", "111101")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * LK_ATK * Z * 1.2, rel_tol=1e-9)


class TestEnhancedBasic:
    def test_enhanced_structure_and_detonate(self, compiled):
        """强化普攻（战意 2）：直冲 3 段 0.20 + 碎天 0.80 + 粉碎追加 3 段 0.20
        （mechanic_chance 恒中）+ 耗 2 战意 + 命中裂伤引爆 0.85×上限."""
        eng = _make(compiled)
        _cast(eng, "1111", "111102")   # 裂伤 + 战意 2
        s = _lk(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1111", "111108")
        hits = (3 * 0.20 + 0.80 + 3 * 0.20) * LK_ATK * Z
        detonate = 0.85 * BLEED_CAP * Z
        assert math.isclose(hp1 - e1.current_hp, hits + detonate, rel_tol=1e-9), (
            "直冲 3+碎天 1+追加 3（结构勘正全链）+ 天赋引爆")
        assert math.isclose(s.resources["fighting_will"], 0.0), "耗 2 战意"

    def test_detonate_reads_dot_value_snapshot(self, compiled):
        """引爆读 dot_value（原裂伤当跳基数）：施加后卢卡 ATK 翻倍（新挂 buff）——
        直伤段随现值 ×2，引爆段仍 0.85×施加时刻快照基数（不随现值重算）."""
        eng = _make(compiled)
        _cast(eng, "1111", "111102")   # 裂伤（快照 atk=745.1136）+ 战意 2
        eng._apply_modifier(_lk(eng), Modifier(
            modifier_id="ATK_UP", name="攻击提升", modifier_type="buff",
            duration=2, stat_effects={"atk_pct": 1.0}))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1111", "111108")
        buffed = 582.12 * (1 + 0.28 + 1.0)   # 行迹 0.28 + 新挂 buff 1.0 = 有效 atk 1327.2336
        hits = (3 * 0.20 + 0.80 + 3 * 0.20) * buffed * Z   # 直伤吃现值（×2.28）
        detonate = 0.85 * BLEED_CAP * Z                    # 引爆读快照（不随现值）
        assert math.isclose(hp1 - e1.current_hp, hits + detonate, rel_tol=1e-9), (
            "dot_value=施加时刻快照基数×0.85——旧式公式重算（$self.atk 现值）已退役")


class TestEidolons:
    def test_e1_bleed_target_dmg_up(self):
        """E1：命中裂伤目标 → 增伤 15% 二回合——快照语义：战技挂裂伤的当发不触发
        （Welt 同族），后续行动（普攻）触发."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1111", "111102")
        assert "E1_FIGHT_ON" not in _lk(eng).modifiers, "挂裂伤的当发快照无裂伤（不触发）"
        _cast(eng, "1111", "111101")
        assert "E1_FIGHT_ON" in _lk(eng).modifiers
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1111", "111101")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * LK_ATK * Z * 1.15, rel_tol=1e-9)
