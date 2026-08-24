"""Rulebook 加载器健全性：预编译产物结构完整、路由闭合、消费面齐备."""
from __future__ import annotations

import ast as _ast

from hsr_nous.sim_schema.rulebook import get_rulebook


def test_rulebook_loads_precompiled():
    rb = get_rulebook()
    # 公式族 + 削韧公式齐备（欢愉表达式入簿备镜，但路由不接）
    for key in ("damage", "damage_expected", "true_damage", "break_damage",
                "super_break_damage", "dot_damage", "elation_damage", "heal",
                "shield", "toughness_damage"):
        assert key in rb.formulas, f"formula {key} 缺失"
    assert rb.zones and rb.break_effects


def test_route_closed_and_mode_complete():
    """route 表：每个伤害类别两种模式都指向已定义的公式键（新类别 = 加一行即生效）."""
    rb = get_rulebook()
    for category, by_mode in rb.route.items():
        assert set(by_mode) == {"roll", "expected"}, f"{category} 模式不全"
        for mode, key in by_mode.items():
            assert key in rb.formulas, f"route[{category}][{mode}] → 未定义公式 {key!r}"
    # 欢愉未实装：表达式在簿但不得有路由（实例垫底纪律）
    assert not any("elation" in key for by_mode in rb.route.values() for key in by_mode.values())


def test_consumed_zones_defined():
    """引擎消费的公式（direct/break 两路由）引用的乘区名全部在 zones 有定义."""
    rb = get_rulebook()
    consumed = {rb.route[c][m] for c in ("direct", "break") for m in ("roll", "expected")}
    for key in consumed:
        names = {n.id for n in _ast.walk(rb.formulas[key].tree) if isinstance(n, _ast.Name)}
        for name in names:
            assert name in rb.zones or name == "ability_multiplier", (
                f"公式 {key} 引用未定义乘区 {name!r}")


def test_constants_present():
    rb = get_rulebook()
    assert rb.constants["non_weakness_res"] == 0.20
    assert rb.constants["default_target_def"] == 1000.0
    assert rb.constants["freeze_advance"] == 0.5  # mechanics 03 §3.5 解冻提前 50%


def test_energy_and_break_durations_present():
    """A1：行动默认回能表 + 击破持续回合表（mechanics 05 §5.1 / 04 §4.8）."""
    rb = get_rulebook()
    assert rb.energy == {"basic": 20, "skill": 30, "ultimate": 5}
    for el in ("physical", "fire", "thunder", "wind", "quantum"):
        assert rb.break_effects[el]["dot_duration"] == 2, f"{el} DoT 持续应为 2 回合"
    for el in ("ice", "quantum", "imaginary"):
        assert rb.break_effects[el]["control_duration"] == 1, f"{el} 控制持续应为 1 回合"


# ---------------------------------------------------------------------------
# A1 引擎查表消费：改 rulebook 值，引擎行为跟着变（字面量零回流）
# ---------------------------------------------------------------------------

import math
from dataclasses import replace as _dc_replace

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _mini_eng():
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=1000, spd=200, hp=5000, max_energy=100))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=120,
                                  weakness=["fire", "ice"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=1000))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, initial_sp=3, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _patch_rulebook(monkeypatch, **kw):
    """构造改值 rulebook 并让新 pipeline 拿到（引擎查表消费的行为探针）."""
    rb = _dc_replace(get_rulebook(), **kw)
    monkeypatch.setattr("hsr_nous.sim.pipeline.get_rulebook", lambda: rb)


def _attack(element="fire", atype="basic"):
    return Action(action_id=f"a_{element}", name=element, action_type=atype,
                  target_type="single", damage_type=element,
                  scaling=[{"atk": 1.0}], toughness_dmg=200)


def test_energy_default_reads_rulebook(monkeypatch):
    """普攻默认回能：rulebook energy 表查得（默认 20；改表 → 行为跟着变）."""
    eng = _mini_eng()
    st = eng.state.actors["hero"]
    eng._execute_action(st, _attack())
    assert st.current_energy == 20.0
    _patch_rulebook(monkeypatch, energy={"basic": 37, "skill": 30, "ultimate": 5})
    eng2 = _mini_eng()
    st2 = eng2.state.actors["hero"]
    eng2._execute_action(st2, _attack())
    assert st2.current_energy == 37.0, "改 rulebook energy 表，默认回能必须跟着变"


def test_break_dot_duration_reads_rulebook(monkeypatch):
    """击破 DoT 持续回合：rulebook break_effects.dot_duration（默认 2；改表 → 跟着变）."""
    eng = _mini_eng()
    eng._execute_action(eng.state.actors["hero"], _attack("fire"))
    assert eng.state.actors["e1"].modifiers["BRK_DOT_fire"].duration == 2
    eff = dict(get_rulebook().break_effects["fire"], dot_duration=5)
    _patch_rulebook(monkeypatch, break_effects={**get_rulebook().break_effects, "fire": eff})
    eng2 = _mini_eng()
    eng2._execute_action(eng2.state.actors["hero"], _attack("fire"))
    assert eng2.state.actors["e1"].modifiers["BRK_DOT_fire"].duration == 5


def test_break_control_duration_reads_rulebook():
    """击破控制持续回合：rulebook break_effects.control_duration（冰冻结 1 回合）."""
    eng = _mini_eng()
    eng._execute_action(eng.state.actors["hero"], _attack("ice"))
    assert eng.state.actors["e1"].modifiers["BRK_FREEZE"].duration == 1


def test_freeze_advance_reads_rulebook(monkeypatch):
    """冻结解冻提前量：rulebook constants.freeze_advance（默认 0.5；改表 → 跟着变）."""
    def thaw_av(eng):
        tgt = eng.state.actors["e1"]
        eng._apply_modifier(tgt, Modifier(
            modifier_id="BRK_FREEZE", name="冻结", modifier_type="control",
            debuff_kind="control", duration=1, control_kind="freeze"))
        eng._enemy_turn(tgt)  # 冻结分支：跳过 + 解冻提前
        return dict(eng.scheduler.preview())["e1"]

    assert math.isclose(thaw_av(_mini_eng()), 50.0)  # 10000×(1-0.5)/100
    _patch_rulebook(monkeypatch, constants={**get_rulebook().constants, "freeze_advance": 0.25})
    assert math.isclose(thaw_av(_mini_eng()), 75.0)  # 10000×(1-0.25)/100
