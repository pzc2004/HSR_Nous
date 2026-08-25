"""Rulebook 加载器健全性：预编译产物结构完整、路由闭合、消费面齐备."""
from __future__ import annotations

import ast as _ast

from hsr_nous.sim_schema.rulebook import get_rulebook
from tests.scheduler_debug import preview


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


def test_break_dot_ratios_fandom():
    """击破 DoT 倍率钉死（Fandom Toughness 页 Debuff Base DMG 表，2026-08-24 裁决）：
    灼烧 1.0 / 触电 2.0 / 风化**每层** 1.0（Wind Shear = 1 × Stack Count × Level Multiplier——
    风 scaling 1.5 是击破瞬间倍率，与 dot_ratio 是两个字段，旧值 1.5 系混用已修正）；
    裂伤敌类型系数 elite 7% / normal 16%（cap 见 bleed_base_multi）."""
    rb = get_rulebook()
    assert rb.break_effects["fire"]["dot_ratio"] == 1.0
    assert rb.break_effects["thunder"]["dot_ratio"] == 2.0
    assert rb.break_effects["wind"]["dot_ratio"] == 1.0
    assert rb.break_effects["physical"]["bleed_coeff"] == {"elite": 0.07, "normal": 0.16}
    # 击破瞬间倍率（scaling）独立于 dot_ratio：风 1.5 保留在 scaling 字段
    assert rb.break_effects["wind"]["scaling"] == 1.5


# ---------------------------------------------------------------------------
# A1 引擎查表消费：改 rulebook 值，引擎行为跟着变（字面量零回流）
# ---------------------------------------------------------------------------

import math
from dataclasses import replace as _dc_replace

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, SettlementPipeline
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import ActorState, Modifier
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
        return dict(preview(eng.scheduler))["e1"]

    assert math.isclose(thaw_av(_mini_eng()), 50.0)  # 10000×(1-0.5)/100
    _patch_rulebook(monkeypatch, constants={**get_rulebook().constants, "freeze_advance": 0.25})
    assert math.isclose(thaw_av(_mini_eng()), 75.0)  # 10000×(1-0.25)/100


# ---------------------------------------------------------------------------
# 原则 B 批次：引擎零公式硬编码——一切公式住 rulebook，引擎只查表求值
# ---------------------------------------------------------------------------

def test_principle_b_keys_present():
    """原则 B 入簿键齐备：gain_energy 公式 + 5 个新区 + 3 个常数 + 裂伤标记槽."""
    rb = get_rulebook()
    assert "gain_energy" in rb.formulas
    for z in ("ability_base", "stat_with_pct", "taunt_eff", "dot_snapshot", "bleed_tick"):
        assert z in rb.zones, f"zone {z} 缺失"
    for c in ("initial_sp", "initial_energy_ratio", "blast_toughness_ratio"):
        assert c in rb.constants, f"constant {c} 缺失"
    assert rb.break_effects["physical"]["bleed_ratio"] == 1.0  # 裂伤标记兼击破裂伤 ratio


class TestGainEnergyErrBuff:
    """B1 修复实证：modifier ERR buff（stat_effects.energy_regen）此前读裸面板是死键."""

    def test_err_buff_amplifies_action_gain(self):
        """行动回能吃 modifier ERR buff：20 × (1+0.2) = 24（修复前为 20——buff 不生效）."""
        eng = _mini_eng()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="ERR_BUF", name="充能", modifier_type="buff",
            stat_effects={"energy_regen": 0.2}))
        eng._execute_action(st, _attack())
        assert math.isclose(st.current_energy, 24.0)

    def test_err_buff_amplifies_hit_energy(self):
        """受击回能同入口自愈：energy_grant 10 × ERR(1+0.2) = 12."""
        eng = _mini_eng()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, Modifier(
            modifier_id="ERR_BUF", name="充能", modifier_type="buff",
            stat_effects={"energy_regen": 0.2}))
        enemy_atk = Action(action_id="e_atk", name="爪击", action_type="basic",
                           target_type="single", damage_type="fire",
                           scaling=[{"atk": 1.0}], toughness_dmg=0, energy_grant=10)
        eng._execute_action(eng.state.actors["e1"], enemy_atk)
        assert math.isclose(st.current_energy, 12.0)

    def test_err_exempt_feeds_neutral_regen(self):
        """err_exempt 具名豁免（§5.3）：ERR buff 在场仍喂 1.0；对照组吃 buff."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        hero = Actor(actor_id="h", name="测试员", level=80,
                     stats=StatBlock(hp=3000, spd=100, max_energy=100))
        st = ActorState(actor=hero, current_hp=3000.0, current_energy=0.0,
                        modifiers={"m": Modifier(
                            modifier_id="m", name="m", modifier_type="buff",
                            stat_effects={"energy_regen": 0.2})})
        r = pipe.gain_energy(st, 25.0, err_exempt=True)
        assert r.value == 25.0 and r.node["regenMulti"] == 1.0
        r2 = pipe.gain_energy(st, 25.0)  # 对照组：吃 ERR buff → 30
        assert r2.value == 30.0 and math.isclose(r2.node["regenMulti"], 1.2)


def _mini_eng_default():
    """不显式传 initial_sp / initial_energy_ratio——缺省读簿探针."""
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=1000, spd=200, hp=5000, max_energy=100))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=120, weakness=["fire"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=1000))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(), mode=MODE_EXPECTED)
    eng.setup()
    return eng


def test_initial_sp_reads_rulebook(monkeypatch):
    """开局 SP 缺省读簿（默认 3，mechanics 06 §6.2；改表 → 跟着变）."""
    assert _mini_eng_default().state.skill_points == 3
    _patch_rulebook(monkeypatch, constants={**get_rulebook().constants, "initial_sp": 7})
    assert _mini_eng_default().state.skill_points == 7


def test_initial_energy_ratio_reads_rulebook(monkeypatch):
    """开局能量比例缺省读簿（默认 0.5；改表 → 跟着变）."""
    assert _mini_eng_default().state.actors["hero"].current_energy == 50.0  # 100 × 0.5
    _patch_rulebook(monkeypatch, constants={**get_rulebook().constants, "initial_energy_ratio": 0.25})
    assert _mini_eng_default().state.actors["hero"].current_energy == 25.0


def test_blast_toughness_ratio_reads_rulebook(monkeypatch):
    """扩散副目标缺省削韧读簿 + // 截断修复实证（奇数 5 → 2.5，旧整除得 2；改表 → 跟着变）."""
    def side_toughness_after_hit() -> float:
        hero = Actor(actor_id="hero", name="测试员", level=80,
                     stats=StatBlock(atk=1000, spd=200, hp=5000, max_energy=100))
        e1 = Actor(actor_id="e1", name="假人甲", actor_type="monster", level=80,
                   stats=StatBlock(hp=1e9, spd=100, max_toughness=120, weakness=["fire"]))
        e2 = Actor(actor_id="e2", name="假人乙", actor_type="monster", level=80,
                   stats=StatBlock(hp=1e9, spd=100, max_toughness=120, weakness=["fire"]))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, e1, e2],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=1000))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED, initial_sp=3, initial_energy_ratio=0.0)
        eng.setup()
        blast = Action(action_id="a_blast", name="扩散", action_type="basic", target_type="blast",
                       damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=5)  # 奇数钉死浮点口径
        eng._execute_action(eng.state.actors["hero"], blast)
        return eng.state.actors["e2"].toughness

    assert side_toughness_after_hit() == 117.5  # 120 − 5×0.5（// 截断修复：旧值为 118）
    _patch_rulebook(monkeypatch, constants={**get_rulebook().constants, "blast_toughness_ratio": 1.0})
    assert side_toughness_after_hit() == 115.0  # 改表 → 副削韧跟着变


def test_stat_with_pct_zone_bitwise():
    """面板 pct 合成走 rulebook zones.stat_with_pct 求值，与旧 Python 拼接逐比特一致（非 isclose）."""
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    hero = Actor(actor_id="h", name="测试员", level=80,
                 stats=StatBlock(atk=1234.5, spd=100, hp=5000, max_energy=100))
    st = ActorState(actor=hero, current_hp=5000.0, current_energy=0.0,
                    modifiers={"m": Modifier(modifier_id="m", name="m", modifier_type="buff",
                                             stat_effects={"atk_pct": 0.123456})})
    out = pipe.effective_stats(st)
    assert out["atk"] == 1234.5 + 1234.5 * 0.123456


def test_ability_base_zone_bitwise():
    """技能基数区走 rulebook zones.ability_base 求值，与旧 Python 拼接逐比特一致（非 isclose）."""
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    action = Action(action_id="a", name="a", action_type="skill", target_type="single",
                    damage_type="fire", scaling=[{"atk": 0.3456, "hp": 0.0789, "def": 0.1234}])
    se = {"atk": 1234.5, "hp": 5678.9, "def_": 987.6}
    got = pipe._ability_multi_eff(action, se, 1)
    assert got == 0.3456 * 1234.5 + 0.0789 * 5678.9 + 0.1234 * 987.6


def test_dot_snapshot_zone_eval():
    """DoT 跳伤走 rulebook zones.dot_snapshot 求值（值与旧拼接逐比特一致）."""
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    holder = ActorState(
        actor=Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, spd=100, max_toughness=120)),
        current_hp=1e9)
    mod = Modifier(modifier_id="DOT", name="灼烧", modifier_type="dot", debuff_kind="dot",
                   duration=2, dot_element="fire", dot_ratio=1.234, dot_source_atk=5432.1)
    r = pipe.dot_tick(holder, mod)
    assert r.value == 5432.1 * 1.234
    assert holder.current_hp == 1e9 - r.value


def test_bleed_tick_zone_eval():
    """裂伤跳伤走 rulebook zones.bleed_tick 求值（基数 × ratio，值与旧拼接一致）."""
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    holder = ActorState(
        actor=Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=100000.0, spd=100, max_toughness=120)),
        current_hp=100000.0)
    mod = Modifier(modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot",
                   debuff_kind="dot", duration=2, dot_element="physical",
                   dot_ratio=1.0, dot_source_atk=0.0)
    r = pipe.bleed_tick(holder, mod)
    base = min(0.07 * 100000.0, 2 * 3767.5533 * (0.5 + 120 / 40))  # elite 档 → 7000
    assert r.value == base * 1.0
    assert math.isclose(r.node["bleedBaseMulti"], 7000.0)
