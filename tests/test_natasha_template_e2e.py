"""娜塔莎 1105 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 治疗链/
HoT/天赋门控/行迹/星魂全链 → 手算全等.

过堂五件（fixture 头注同录）：ally_single 勘正 / 指定目标 $event.target /
outgoing_heal→heal_bonus 死键 / 天赋 hit_condition 正主 / E6 同目标。

口径常数：娜塔莎 atk 476.28、hp 1490.2272（白值 1164.24×1.28——行迹 hp_pct 0.28
B-TR① 回填）、crit 0.05/0.5（期望暴击区 1.025）；假人 def 0 → 防御区 0.5、
物理弱点 → 抗性区 1.0、未击破 0.9。普攻 lv6=1.0。
治疗公式 = (ratio×施放者 HP + flat) × (1 + heal_bonus 0.10 医者 + 命中域天赋桶)。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

NA_ATK = 476.28
NA_HP = 1164.24 * 1.28     # 1490.2272（行迹 hp_pct 0.28 回填——B-TR①）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
HB = 1.10          # 医者 heal_bonus 0.10


def _build(*, eidolon: int = 0):
    member = {"character_template": "1105", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 4000, "max_energy": 100},
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


def _na(eng):
    return eng.state.actors["1105"]


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


class TestNatashaCompile:
    def test_ally_single_and_heal_bonus(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1105"]}
        assert acts["110502"].target_type == "ally_single", "治疗技目标池勘正实证"
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_na(eng))["heal_bonus"], 0.10), (
            "医者 heal_bonus（outgoing_heal 死键勘正）")


class TestSkillHeal:
    def test_heal_hot_cleanse_designated(self, compiled):
        """战技：指定目标（$event.target 勘正实证）治疗 (0.07×HP+280)×1.1 + HoT 3 回合
        + 驱散 LIFO 新先摘."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0
        eng._apply_modifier(ally, Modifier(
            modifier_id="D1", name="旧负面", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="D2", name="新负面", modifier_type="debuff", duration=2))
        _cast(eng, "1105", "110502", target=ally)
        heal = (0.105 * NA_HP + 280.0) * HB   # lv10 param(110502,1/4)=0.105/280
        assert math.isclose(ally.current_hp, 2000.0 + heal, rel_tol=1e-9)
        assert "NATASHA_HOT" in ally.modifiers and ally.modifiers["NATASHA_HOT"].duration == 3
        assert "D2" not in ally.modifiers and "D1" in ally.modifiers
        hp0 = ally.current_hp
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        tick = (0.072 * NA_HP + 192.0) * HB   # lv10 param(110502,2/5)=0.072/192
        assert math.isclose(ally.current_hp - hp0, tick, rel_tol=1e-9), "HoT 逐跳（param(110502,2/5)）"

    def test_talent_scoped_low_hp(self, compiled):
        """天赋命中域：受疗者 ≤30% → heal_bonus +50%（(0.07×HP+280)×(1+0.10+0.50)）；
        >30% 不吃（scoped 正主实证——非后授 buff）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 800.0   # 20% ≤ 30%
        _cast(eng, "1105", "110502", target=ally)
        heal = (0.105 * NA_HP + 280.0) * (HB + 0.5)
        assert math.isclose(ally.current_hp, 800.0 + heal, rel_tol=1e-9)


class TestUltimate:
    def test_ult_heal_all(self, compiled):
        """大招：全体 (0.092×HP+368)×1.1；能量 5."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 2000.0
        m7 = _na(eng)
        m7.current_hp = 500.0
        m7.current_energy = 90.0
        ult = next(a for a in eng.actions_by_actor["1105"] if a.action_id == "110503")
        assert eng._fire_ultimate(m7, ult) is True
        heal = (0.138 * NA_HP + 368.0) * HB   # lv10 param(110503,1/2)=0.138/368
        assert math.isclose(ally.current_hp, 2000.0 + heal, rel_tol=1e-9)
        assert math.isclose(m7.current_hp, 500.0 + heal, rel_tol=1e-9)
        assert math.isclose(m7.current_energy, 5.0)


class TestEidolons:
    def test_e1_self_heal_low_hp(self):
        """E1：受击且 HP≤30% → 自疗 (0.15×HP+400)×(1+0.1+0.5 天赋命中域)，单场 1 次.
        行迹 hp 回填后 30% 档不再超顶（372.6+997.7=1370.2<1490.2——定档量不变，
        clamp 分支本档离线）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _na(eng)
        a.current_hp = 0.25 * NA_HP
        eng.bus.emit("after_being_hit", {
            "target": "1105", "source": "e1", "amount": 100.0,
            "action_type": "basic", "damage_type": "physical"}, eng.state)
        heal = (0.15 * NA_HP + 400.0) * (HB + 0.5)   # 997.654528
        assert math.isclose(a.current_hp, 0.25 * NA_HP + heal, rel_tol=1e-9), (
            "623.5×1.6=997.7 定档自疗（天赋 scoped 自身低血同吃）")
        assert math.isclose(a.resources["_e1_used"], 1.0)
        hp0 = a.current_hp
        eng.bus.emit("after_being_hit", {
            "target": "1105", "source": "e1", "amount": 100.0,
            "action_type": "basic", "damage_type": "physical"}, eng.state)
        assert math.isclose(a.current_hp, hp0), "单场闩不再触发"

    def test_e2_ult_hot_and_e4_hit_energy(self):
        """E2：大招对 ≤30% 队友附加 HoT（同事件后位求值——治疗先落：本例 50→
        967.8/4000=24.2% 仍 ≤30% 挂得上；800→1717.8/4000=42.9% 抬过阈即不挂，
        官方未写时点双态在案）；E4：受击 +5 能."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 50.0   # 治疗 (0.138×HP+368)×1.6(天赋命中域)=917.8 → 967.8 仍 ≤30%
        m7 = _na(eng)
        m7.current_energy = 90.0
        ult = next(a for a in eng.actions_by_actor["1105"] if a.action_id == "110503")
        assert eng._fire_ultimate(m7, ult) is True
        assert "NATASHA_E2_HOT" in ally.modifiers, "治疗后仍 ≤30% → 挂 HoT"
        hp0 = ally.current_hp
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(ally.current_hp - hp0, (0.06 * NA_HP + 160.0) * (HB + 0.5), rel_tol=1e-9), (
            "HoT 逐跳吃天赋命中域 ×1.6（受疗者跳时仍 ≤30%——'continuous healing also works' 同向实证）")
        e0 = m7.current_energy
        eng.bus.emit("after_being_hit", {
            "target": "1105", "source": "e1", "amount": 50.0,
            "action_type": "basic", "damage_type": "physical"}, eng.state)
        assert math.isclose(m7.current_energy, e0 + 5.0), "E4 受击 +5 能"

    def test_e2_ordering_countercase(self):
        """E2 反例（时点钉死）：队友 800/4000=20% 开战低血，但同发治疗先抬到
        42.9% → 不挂（同事件后位求值——官方时点未写在案）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        ally.current_hp = 800.0
        m7 = _na(eng)
        m7.current_energy = 90.0
        ult = next(a for a in eng.actions_by_actor["1105"] if a.action_id == "110503")
        assert eng._fire_ultimate(m7, ult) is True
        assert "NATASHA_E2_HOT" not in ally.modifiers, "治疗后抬过 30% → 不挂（时点钉死）"

    def test_e6_same_target_bonus(self):
        """E6：普攻同目标追加 0.4×Max HP 物伤（$event.target 勘正实证——打 e1 不吃 e2；
        E3 普攻 lv7=1.1 联动）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1105", "110501")
        assert math.isclose(hp1 - e1.current_hp,
                            1.1 * NA_ATK * Z + 0.4 * NA_HP * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0), "同目标追加——e2 不吃"
