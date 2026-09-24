"""三月七 1224 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → Charge
充能/强化普攻段链/Shifu 双分支/驭澜/星魂全链 → 手算全等.

过堂勘正八件（fixture 头注同录）：ally_single / mechanic_chance 平铺 /
E2 分支并入 / 命途枚举删脑补 / SUP 削韧翻案 / _hit_chance 初始化 /
追加段 amount 三元内联 / 摘除置尾+追加回无门控钩。

重审勘正一件（2026-09-24，fixture 头注⑨同录）：摘除再挪段链尾部独立钩
（快照语义下主钩末尾摘除先于武装段 4/5 钩执行=段 4/5 脱增伤/E6 暴伤）+
真路径（on_resource_gain 满 7）8 段全程 ×1.8 回归钉。

口径常数：三月七白值 atk 564.48、spd 102、crit 0.05/0.5（期望暴击区
1.025）；假人 def 0 → 防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9。
强化普攻 lv6 段倍率 0.8、DPS 分支附加 lv10 0.2、天赋增伤 lv10 0.8。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

M7_ATK = 564.48
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, path: str = "hunt", pre_battle: list | None = None):
    member = {"character_template": "1224", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "path": path,
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "imaginary",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _m7(eng):
    return eng.state.actors["1224"]


def _cast(eng, aid, target_id):
    m7 = _m7(eng)
    a = next(x for x in eng.actions_by_actor["1224"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(m7, a)
    eng.bus.emit("on_action", {
        "actor": "1224", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": m7.actor.actor_type}, eng.state)


def _grant_shifu(eng):
    _cast(eng, "122402", "ally")


def _basic_n(eng, n):
    for _ in range(n):
        _cast(eng, "122401", "e1")


class TestMarch7Compile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1224"]
        assert {"charge", "_hit_chance", "_extra_hits", "_e2_used"} <= set(decls)
        assert decls["charge"]["max"] == 10


class TestShifu:
    def test_grant_and_dps_branch(self, compiled):
        """战技：挂 Shifu+加速；hunt 命途 → DPS 分支."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        _grant_shifu(eng)
        assert "SHIFU" in ally.modifiers
        assert math.isclose(
            ally.modifiers["SHIFU_SPD"].stat_effects["spd_pct"], 0.1, rel_tol=1e-9)
        assert "SKILL_DPS_ARMED" in _m7(eng).modifiers

    def test_support_branch_efficiency(self):
        """辅助命途（harmony）→ SUP 分支+削韧效率 +100%（翻案收录）."""
        eng = _make(compile_encounter(_build(path="harmony"), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _grant_shifu(eng)
        m = _m7(eng).modifiers["SKILL_SUP_ARMED"]
        assert math.isclose(m.stat_effects["break_efficiency_boost"], 1.0)
        assert "SKILL_DPS_ARMED" not in _m7(eng).modifiers


class TestChargeEnhanced:
    def test_basic_charge_and_enhanced(self, compiled):
        """普攻×7：+1 Charge+DPS 分支附加 0.2（lv10）；满 7 挂增伤（0.8 lv10）."""
        eng = _make(compiled)
        _grant_shifu(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _basic_n(eng, 7)
        m7 = _m7(eng)
        assert math.isclose(m7.resources["charge"], 7.0)
        # 前 6 击无增伤；第 7 击分支吃增伤（同钩 gain→on_resource_gain 挂→后段
        # deal_damage 读现场——快照族①：满 7 即挂即效（官方「悟了」同步语义）
        assert math.isclose(
            hp1 - e1.current_hp,
            6 * (1.0 + 0.2) * M7_ATK * Z + (1.0 + 0.2 * 1.8) * M7_ATK * Z,
            rel_tol=1e-9)
        assert "ENHANCED_DMG" in m7.modifiers

    def test_enhanced_basic_full_chain(self, compiled):
        """强化普攻：段 1（lv6 0.8）+段 2/3（0.8+0.2）+追加 3 段全出——全程增伤 1.8
        （追加段 amount 三元内联快照免疫；expected 0.6 恒触发 cap 3）."""
        eng = _make(compiled)
        _grant_shifu(eng)
        _basic_n(eng, 7)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "122408", "e1")
        seg1 = 0.8 * M7_ATK * Z * 1.8
        seg_n = (0.8 + 0.2) * M7_ATK * Z * 1.8
        assert math.isclose(hp1 - e1.current_hp, seg1 + 5 * seg_n, rel_tol=1e-9)
        m7 = _m7(eng)
        assert math.isclose(m7.resources["charge"], 0.0), "耗 Charge 7"
        assert "ENHANCED_DMG" not in m7.modifiers, "施放后摘除（钩尾）"
        assert "TIDE_TAMER" in eng.state.actors["ally"].modifiers, "驭澜挂 Shifu"


class TestUltimateArmed:
    def test_ult_armed_enhanced(self, compiled):
        """大招 2.4 lv10 + ULT_ARMED：下次强化普攻段 +2（共 5 段）+追加概率 0.8."""
        eng = _make(compiled)
        _grant_shifu(eng)
        m7 = _m7(eng)
        m7.current_energy = 110.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1224"] if x.action_id == "122403")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.4 * M7_ATK * Z, rel_tol=1e-9)
        assert math.isclose(m7.resources["_hit_chance"], 0.8), "武装概率 0.8"
        # 再攒满 7 放强化：段 1-3+武装 4/5+追加 3=8 段（本场景无增伤——set 绕过触发）
        m7.resources["charge"] = 7.0
        hp1 = e1.current_hp
        _cast(eng, "122408", "e1")
        seg = (0.8 + 0.2) * M7_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, 0.8 * M7_ATK * Z + 7 * seg,
                            rel_tol=1e-9), "段 1（0.8）+7 段（1.0）：基础 3+武装 2+追加 3"
        assert "ULT_ARMED" not in m7.modifiers, "兑现后摘 ULT_ARMED"

    def test_ult_armed_enhanced_real_path_full_boost(self, compiled):
        """真路径回归钉（重审勘正⑨）：7 普攻经 on_resource_gain 挂增伤 → 大招
        武装 → 强化普攻 8 段全程 ×1.8——含武装段 4/5（快照语义下主钩末尾摘除
        先于段 4/5 钩执行=段 4/5 脱增伤；摘除挪尾部钩后全程保）."""
        eng = _make(compiled)
        _grant_shifu(eng)
        m7 = _m7(eng)
        _basic_n(eng, 7)   # 真路径：第 7 击 charge 满 7 → on_resource_gain 挂增伤
        assert "ENHANCED_DMG" in m7.modifiers, "真路径满 7 挂增伤"
        m7.current_energy = 110.0
        e1 = eng.state.actors["e1"]
        ult = next(x for x in eng.actions_by_actor["1224"] if x.action_id == "122403")
        assert eng._fire_ultimate(m7, ult) is True
        assert "ULT_ARMED" in m7.modifiers
        hp1 = e1.current_hp
        _cast(eng, "122408", "e1")
        seg1 = 0.8 * M7_ATK * Z * 1.8
        seg_n = (0.8 + 0.2) * M7_ATK * Z * 1.8
        assert math.isclose(hp1 - e1.current_hp, seg1 + 7 * seg_n, rel_tol=1e-9), (
            "段 1+基础 2/3+追加 3+武装 4/5=8 段全程 ×1.8——段 4/5 不再脱增伤")
        assert "ENHANCED_DMG" not in m7.modifiers, "结算后摘增伤（尾部钩）"
        assert "ULT_ARMED" not in m7.modifiers, "兑现后摘 ULT_ARMED"


class TestEidolons:
    def test_e1_shifu_spd(self):
        """E1：挂 Shifu 后三月七速度 +10%."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _grant_shifu(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(_m7(eng))["spd"], 102 * 1.1, rel_tol=1e-9)

    def test_e2_counter_and_charge(self):
        """E2：Shifu 普攻/战技后三月七追加 60%+1 Charge（闩 1 回合）+DPS 分支段."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _grant_shifu(eng)
        m7 = _m7(eng)
        e1 = eng.state.actors["e1"]
        c0 = m7.resources["charge"]
        hp1 = e1.current_hp
        ally = eng.state.actors["ally"]
        a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_basic")
        eng.decision.select_target = lambda s, t, cands, e: e1
        eng._execute_action(ally, a)
        eng.bus.emit("on_action", {"actor": "ally", "action_type": "basic",
                                   "action_id": "ally_basic", "target_type": "single",
                                   "target": "e1", "actor_type": "character"}, eng.state)
        dealt = hp1 - e1.current_hp
        ally_d = 1.0 * 1500 * Z
        e2_d = 0.6 * M7_ATK * Z + 0.2 * M7_ATK * Z   # 追加 60% + DPS 分支 0.2
        assert math.isclose(dealt, ally_d + e2_d, rel_tol=1e-9)
        assert math.isclose(m7.resources["charge"], c0 + 2.0), (
            "天赋 Shifu 攻击 +1 + E2「额外获得」+1（官方双份）")
        # 闩：本回合不再触发
        hp1 = e1.current_hp
        eng._execute_action(ally, a)
        eng.bus.emit("on_action", {"actor": "ally", "action_type": "basic",
                                   "action_id": "ally_basic", "target_type": "single",
                                   "target": "e1", "actor_type": "character"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, ally_d, rel_tol=1e-9), "闩内不追加"

    def test_e6_next_enhanced_crit(self):
        """E6：大招后下次强化普攻 crit_dmg+0.5（兑现并摘除）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _grant_shifu(eng)
        m7 = _m7(eng)
        m7.current_energy = 110.0
        ult = next(x for x in eng.actions_by_actor["1224"] if x.action_id == "122403")
        eng._fire_ultimate(m7, ult)
        assert "E6_NEXT_ENH_CRITDMG" in m7.modifiers
        m7.resources["charge"] = 7.0
        _cast(eng, "122408", "e1")
        assert "E6_NEXT_ENH_CRITDMG" not in m7.modifiers, "兑现后摘除"


class TestTechnique:
    def test_tech_charge_energy(self):
        """秘技：Charge+3+回 30 能."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1224", "technique": "122407"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        m7 = _m7(eng)
        assert math.isclose(m7.resources["charge"], 3.0)
        assert math.isclose(m7.current_energy, 30.0)
