"""艾丝妲 1009 模板端到端对轴（验收型批·组2 开批）：真模板 YAML → 编译 → 弹射/
充能烘焙/衰减/点燃元素粒度/星魂全链 → 手算全等.

过堂四件（fixture 头注同录）：点燃 dmg_fire 收编 / chance→mechanic_chance /
火花 DoT 目标 $event.actor / 火弱点 +2 支摘除（element_of≠弱点证伪）。

口径常数：艾丝妲白值 atk 511.56、crit 0.117/0.5（0.05+行迹 crit_rate 0.067
B-TR① 回填——期望暴击区 1.0585）；假人 def 0 → 防御区 0.5、火弱点 →
抗性区 1.0、未击破 0.9。火伤池：自身 1.404（点燃 dmg_fire 0.18 + 行迹
dmg_fire 0.224 同回填）；队友只吃点燃 1.18（元素粒度收编实证——非火攻击不吃）。

充能-烘焙递增链（e2e 按现写语义钉死，判重/火弱点待收在案）：每次命中 +1 层并
重烘焙 aura——同一次战技内主段吃 0 层、弹射第 N 段吃 N 层（effect 序 gain 先写、
bake 后读；多段递增官方口径待实测）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ASTA_ATK = 511.56
Z = 0.5 * 0.9 * (1 + 0.117 * 0.5)   # 自身暴击区 1.0585（行迹 crit_rate 0.067 回填——B-TR①）
Z_ALLY = 0.5 * 0.9 * (1 + 0.05 * 0.5)   # 队友暴击区（辅手无行迹）
FIRE = 1.404       # 自身火伤池：点燃 0.18 + 行迹 dmg_fire 0.224（B-TR① 回填）
FIRE_ALLY = 1.18   # 队友火伤池：点燃 dmg_fire 0.18 命中域（火伤专属——元素粒度收编）
SEG = 0.5          # 战技每段 lv10


def _build(*, eidolon: int = 0, phys_ally: bool = False):
    member = {"character_template": "1009", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}]
    if phys_ally:
        team.append(
            {"actor_id": "ally2", "name": "物理手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 85, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ally2_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "physical",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]})
    return {"build": {"team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _asta(eng):
    return eng.state.actors["1009"]


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


class TestAstaCompile:
    def test_resources_actions(self, compiled):
        decls = compiled.resource_decls_by_actor["1009"]
        assert decls["_charge"]["max"] == 5 and "_asta_turns" in decls
        acts = {a.action_id: a for a in compiled.actions_by_actor["1009"]}
        assert acts["100903"].energy_cost == 120 and acts["100903"].target_type == "self"
        assert acts["100902"].skill_point_cost == 1 and acts["100902"].energy_gain == 6


class TestIgniteElemental:
    def test_fire_boosted_physical_not(self):
        """点燃 dmg_fire（元素粒度收编实证）：火普攻吃 1.18；物理普攻不吃（非火零外溢）."""
        compiled = compile_encounter(_build(phys_ally=True), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * Z_ALLY * FIRE_ALLY, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "ally2", "ally2_basic")
        phys_z = 0.5 * 0.8 * 0.9 * (1 + 0.05 * 0.5)   # 物理非弱点 → 抗性区 0.8，无点燃
        assert math.isclose(hp1 - e1.current_hp, 1500 * phys_z, rel_tol=1e-9), (
            "all_dmg 承载会误增物理——dmg_fire 收编后非火零外溢")


class TestBasicBurnAndCharge:
    def test_basic_burn_and_dot(self, compiled):
        """普攻：lv6=1.0 对轴×点燃 1.18 + 命中 +1 层（天赋）+ 灼烧挂载（声明式 dot
        通道——施加恒挂、80% 基础概率以 ehr_multi 期望权重乘进跳伤）+ 灼烧跳伤
        $event.actor 单跳（目标勘正实证；施加时刻快照吃 1 层蓄能 aura）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "1009", "100901")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ASTA_ATK * Z * FIRE, rel_tol=1e-9)
        assert math.isclose(_asta(eng).resources["_charge"], 1.0)
        assert "ASTA_BURN" in e1.modifiers, "mechanic_chance 0.8≥0.5 恒中"
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 1500 * 1.14, rel_tol=1e-9), (
            "蓄能 1 层全队 atk_pct 0.14 烘焙（team 光环）")
        hp2 = e2.current_hp
        hp1 = e1.current_hp
        eng._tick_dots(e1)   # 声明式跳伤走引擎 A 类结算（非 on_turn_start 事件）
        burn = 0.5 * (ASTA_ATK * 1.14) * 0.45 * FIRE * 0.8   # 施加时刻快照吃 1 层蓄能 aura；不暴击×0.45（非 Z）；80% 期望权重 ehr_multi
        assert math.isclose(hp1 - e1.current_hp, burn, rel_tol=1e-9), (
            "灼烧跳 0.5×ATK 单跳（声明式 dot 通道——不暴击+施加时刻快照+80% 期望权重）")
        assert e1.modifiers["ASTA_BURN"].modifier_type == "dot", "声明式 DoT 通道承载"
        assert math.isclose(hp2 - e2.current_hp, 0.0), "e2 未灼烧不吃跳（draft 全体跳勘正）"


class TestSkillBounce:
    def test_skill_bounce_escalating_bake(self, compiled):
        """战技：主段+4 弹射全落 e1（expected 取首）；充能递增烘焙——主段 0 层、
        弹射第 N 段 N 层（effect 序 gain 先写 bake 后读）；回能 6+24=30."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1009", "100902")
        series = 1 + 1.14 + 1.28 + 1.42 + 1.56   # 主 0 层 + 弹射 1/2/3/4 层
        assert math.isclose(hp1 - e1.current_hp,
                            SEG * ASTA_ATK * Z * FIRE * series, rel_tol=1e-9)
        assert math.isclose(_asta(eng).resources["_charge"], 5.0), "5 命中满层（上限 5 截断）"
        assert math.isclose(_asta(eng).current_energy, 30.0)


class TestUltimate:
    def test_ult_team_spd(self, compiled):
        """大招：全队 SPD +50（lv10 param(100903,1)）team 光环 2 回合 + 回能 5."""
        eng = _make(compiled)
        a = _asta(eng)
        a.current_energy = 120.0
        ult = next(x for x in eng.actions_by_actor["1009"] if x.action_id == "100903")
        assert eng._fire_ultimate(a, ult) is True
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(a)["spd"], 106 + 50, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 90 + 50, rel_tol=1e-9)
        assert math.isclose(a.current_energy, 5.0)


class TestDecay:
    def test_decay_from_second_turn(self, compiled):
        """衰减：第 1 回合不衰减（计数 0）；第 2 回合起 −3（满 5 → 2）并重烘焙."""
        eng = _make(compiled)
        _asta(eng).resources["_charge"] = 5.0
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        assert math.isclose(_asta(eng).resources["_charge"], 5.0), "第 1 回合不衰减"
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        assert math.isclose(_asta(eng).resources["_charge"], 2.0), "第 2 回合 −3"


class TestEidolons:
    def test_e1_fifth_bounce(self):
        """E1：第 5 段弹射（第 5 段吃满 5 层 0.70）+ 回能 36."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1009", "100902")
        series = 1 + 1.14 + 1.28 + 1.42 + 1.56 + 1.70
        assert math.isclose(hp1 - e1.current_hp,
                            SEG * ASTA_ATK * Z * FIRE * series, rel_tol=1e-9)
        assert math.isclose(_asta(eng).current_energy, 36.0)

    def test_e2_no_decay_marker(self):
        """E2：大招后持【不衰减】标记——下回合开始跳过衰减."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _asta(eng)
        a.current_energy = 120.0
        ult = next(x for x in eng.actions_by_actor["1009"] if x.action_id == "100903")
        assert eng._fire_ultimate(a, ult) is True
        assert "ASTA_E2_NODECAY" in a.modifiers
        a.resources["_charge"] = 5.0
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        assert math.isclose(a.resources["_charge"], 5.0), "标记覆盖衰减判定点"

    def test_e6_decay_reduced(self):
        """E6：衰减 −1（5 → 3）；E3 天赋+2 → 每层 atk_pct lv12=0.154 一并钉."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        a = _asta(eng)
        a.resources["_charge"] = 5.0
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        eng.bus.emit("on_turn_start", {"actor": "1009"}, eng.state)
        assert math.isclose(a.resources["_charge"], 3.0), "衰减 3−1=2"
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"],
                            1500 * (1 + 0.154 * 3), rel_tol=1e-9), "E3 天赋 lv12=0.154×3 层"
