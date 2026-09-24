"""trigger_action 跨 actor 代放（B40 P1a）端到端：caster/action_type 选择子 +
elation_skill 枚举/默认档 + 互斥/类型闸。

模子：tmp_path 自写微型模板（template_roots 注入——零锚集污染，9999xx 假人族不占
fixtures 目录）。口径常数：假人 def 1000 → 防御区 0.5、雷弱点 → 抗性区 1.0、
未击破 0.9、期望暴击区 1.025（crit 0.05/0.5）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

ATK = 1000.0
DEF_ZONE = 0.5
CRIT_EXP = 1.025

_CASTER = """\
actor_id: "900101"
name: "代放测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_ult"
    name: "代放号令"
    action_type: "ultimate"
    target_type: "ally_single"
    scaling: []
    energy_cost: 100
hooks:
  - event: "on_ultimate"
    condition: "$event.source == '900101' && $event.action == 't_ult'"
    effects:
      - effect_type: "trigger_action"
        caster: "$event.target"
        action_type: "elation_skill"
"""

_ELATION_MATE = """\
actor_id: "900102"
name: "欢愉测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100,
             crit_rate: 0.05, crit_dmg: 0.5}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "thunder"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
  - action_id: "t_elation"
    name: "测试欢愉技"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "thunder"
    scaling: [{atk: 0.1}, {atk: 0.2}, {atk: 0.3}, {atk: 0.4}, {atk: 0.5},
              {atk: 0.6}, {atk: 0.7}, {atk: 0.8}, {atk: 0.9}, {atk: 1.0}]
"""

_TWO_ELATION = """\
actor_id: "900103"
name: "双欢愉测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_e1"
    name: "欢愉技一"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "thunder"
    scaling: [{atk: 1.0}]
  - action_id: "t_e2"
    name: "欢愉技二"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "thunder"
    scaling: [{atk: 1.0}]
"""

_NO_ELATION = """\
actor_id: "900104"
name: "无欢愉测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
"""

_MUTEX = """\
actor_id: "900105"
name: "互斥测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_ult"
    name: "互斥号令"
    action_type: "ultimate"
    target_type: "ally_single"
    scaling: []
    energy_cost: 100
hooks:
  - event: "on_ultimate"
    condition: "$event.source == '900105'"
    effects:
      - effect_type: "trigger_action"
        caster: "$event.target"
        action_id: "t_elation"
        action_type: "elation_skill"
"""

_BAD_CASTER = """\
actor_id: "900106"
name: "坏 caster 测试员"
level: 80
base_stats: {atk: 500, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_ult"
    name: "坏 caster 号令"
    action_type: "ultimate"
    target_type: "ally_single"
    scaling: []
    energy_cost: 100
hooks:
  - event: "on_ultimate"
    condition: "$event.source == '900106'"
    effects:
      - effect_type: "trigger_action"
        caster: 123
        action_type: "elation_skill"
"""

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture()
def roots(tmp_path):
    d = tmp_path / "characters"
    d.mkdir()
    for fname, body in {
        "900101_代放者.yaml": _CASTER,
        "900102_欢愉队友.yaml": _ELATION_MATE,
        "900103_双欢愉.yaml": _TWO_ELATION,
        "900104_无欢愉.yaml": _NO_ELATION,
        "900105_互斥.yaml": _MUTEX,
        "900106_坏caster.yaml": _BAD_CASTER,
    }.items():
        (d / fname).write_text(body, encoding="utf-8")
    return [str(tmp_path)]


def _build(mate: str):
    return {"build": {"team": [
        {"character_template": "900101", "level": 80},
        {"character_template": mate, "level": 80}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _fire_ult_at(eng, target_id: str):
    st = eng.state.actors["900101"]
    st.current_energy = 100.0
    ult = eng.actions_by_actor["900101"][0]
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


class TestCrossActorTrigger:
    def test_trigger_by_type_executes_and_inserts(self, roots):
        """跨 actor 按类索引代放：A 终结技指 B → B 的欢愉技插入执行（代放者=B、
        insert 事件、伤害落账、默认档 10 实取 lv10=1.0 行）。"""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build("900102"), _STAGE, template_roots=roots),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        events = []
        eng.bus.subscribe("on_action",
                          lambda et, payload, state: events.append(payload))
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _fire_ult_at(eng, "900102")
        expect = ATK * 1.0 * DEF_ZONE * 0.9 * CRIT_EXP     # lv10=index9=1.0（默认档 10 实证）
        assert math.isclose(hp - e1.current_hp, expect, rel_tol=1e-9), (
            "欢愉技 lv10 档实取——默认档 10（非 ultimate 回落、非 lv9）")
        ins = [p for p in events if p.get("insert")]
        assert len(ins) == 1 and ins[0]["actor"] == "900102", (
            "代放执行者=欢愉测试员（caster=$event.target）")
        assert ins[0]["action_type"] == "elation_skill" and ins[0]["action_id"] == "t_elation"
        assert any("欢愉测试员 插入发动 测试欢愉技" in line for line in eng.state.log)

    def test_zero_match_loud(self, roots):
        """目标无欢愉技 → 恰取 1 件失败（0 件）大声炸，不许静默吞。"""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build("900104"), _STAGE, template_roots=roots),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        with pytest.raises(ValueError, match="恰取 1 件失败"):
            _fire_ult_at(eng, "900104")

    def test_multi_match_loud(self, roots):
        """目标有两件欢愉技 → 选择子歧义（>1 件）大声炸。"""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build("900103"), _STAGE, template_roots=roots),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        with pytest.raises(ValueError, match="恰取 1 件失败"):
            _fire_ult_at(eng, "900103")


class TestCompileGates:
    def test_mutex_action_id_and_type(self, roots):
        with pytest.raises(ValueError, match="互斥"):
            compile_encounter({"build": {"team": [
                {"character_template": "900105", "level": 80},
                {"character_template": "900102", "level": 80}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "true", "action": "basic", "priority": 0}]}}},
                _STAGE, template_roots=roots)

    def test_caster_type_gate(self, roots):
        with pytest.raises(ValueError, match="caster 须为选择器字符串"):
            compile_encounter({"build": {"team": [
                {"character_template": "900106", "level": 80},
                {"character_template": "900102", "level": 80}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "true", "action": "basic", "priority": 0}]}}},
                _STAGE, template_roots=roots)

    def test_elation_skill_enum_and_default_level(self, roots):
        """action_type elation_skill 入 ACTION_TYPES 闸（不炸）+ 编译期默认档 10 入表。"""
        c = compile_encounter(_build("900102"), _STAGE, template_roots=roots)
        acts = {a.action_id: a for a in c.actions_by_actor["900102"]}
        assert acts["t_elation"].action_type == "elation_skill"
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        lv = eng._skill_level_of(eng.state.actors["900102"].actor, acts["t_elation"])
        assert lv == 10, "elation_skill 默认档 10（E0；非 ultimate 回落语义但同值自洽）"
