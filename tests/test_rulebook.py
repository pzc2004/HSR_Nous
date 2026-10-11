"""Rulebook 加载器健全性：预编译产物结构完整、路由闭合、消费面齐备."""
from __future__ import annotations

import ast as _ast
import random

import pytest

from hsr_nous.sim_schema.rulebook import get_rulebook
from tests.scheduler_debug import preview


def test_rulebook_loads_precompiled():
    rb = get_rulebook()
    # 公式族 + 削韧公式齐备（欢愉路由已接线——B40 P2a，路由闭合断言见 test_route_closed_and_mode_complete）
    for key in ("damage", "damage_expected", "true_damage", "break_damage",
                "super_break_damage", "dot_damage", "elation_damage", "heal",
                "shield", "toughness_damage"):
        assert key in rb.formulas, f"formula {key} 缺失"
    assert rb.zones and rb.break_effects


def test_route_closed_and_mode_complete():
    """route 表：每个伤害类别两种模式都指向已定义的公式键（新类别 = 加一行即生效）."""
    rb = get_rulebook()
    for category, by_mode in rb.route.items():
        # settle 子键 = 类别结算规格（决策卡 #23 P1——通用 settle 消费，非公式路由）
        modes = set(by_mode) - {"settle"}
        assert modes == {"roll", "expected"}, f"{category} 模式不全"
        for mode in modes:
            assert by_mode[mode] in rb.formulas, f"route[{category}][{mode}] → 未定义公式 {by_mode[mode]!r}"
    # 欢愉路由已接线（B40 P2a——实例垫底：通用 settle + route 表 + action 层 elation
    # 行键 + hook category "elation"；#23 P3 起 roll/expected 双公式——模式分发进 route 数据）
    assert rb.route.get("elation", {}).get("roll") == "elation_damage"
    assert rb.route["elation"]["expected"] == "elation_damage_expected"


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
    """原则 B 入簿键齐备：gain_energy 公式 + 3 个新区 + 3 个常数 + 裂伤标记槽 + DoT 双路由."""
    rb = get_rulebook()
    assert "gain_energy" in rb.formulas
    for z in ("ability_base", "stat_with_pct", "taunt_eff"):
        assert z in rb.zones, f"zone {z} 缺失"
    # DoT 全乘区接链（B27#3 收官）：双路由入簿；v0.2 简化式 dot_snapshot/bleed_tick 已退役
    assert rb.route["dot"]["expected"] == "dot_damage"
    assert rb.route["bleed"]["expected"] == "bleed_dot_damage"
    assert "dot_damage" in rb.formulas and "bleed_dot_damage" in rb.formulas
    assert "dot_snapshot" not in rb.zones and "bleed_tick" not in rb.zones
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


# ---------------------------------------------------------------------------
# A8：rulebook 路径注入（测试可替换 rulebook，缓存键带路径互不污染）
# ---------------------------------------------------------------------------

_MINI_RULEBOOK = """\
zones: {z1: "atk * 2"}
formulas: {f1: {expression: "z1 + 1"}}
route: {direct: {roll: f1, expected: f1}}
constants: {probe: 0.77}
relic_affixes: {main: {hp: 1.5}, sub: {spd: 0.5}}
"""


class TestRulebookPathInjection:
    def test_default_is_singleton(self):
        """缺省单例行为不变：get_rulebook() 多次调用返回同一对象."""
        assert get_rulebook() is get_rulebook()

    def test_injected_path_loads_separate_rulebook(self, tmp_path):
        """注入临时 rulebook 生效：内容与默认不同，且默认缓存不受污染."""
        p = tmp_path / "rb.yaml"
        p.write_text(_MINI_RULEBOOK, encoding="utf-8")
        default = get_rulebook()
        injected = get_rulebook(p)
        assert injected is not default
        assert injected.constants["probe"] == 0.77
        assert injected.relic_affixes["main"]["hp"] == 1.5
        assert get_rulebook(p) is injected          # 同路径命中同一缓存
        assert get_rulebook() is default            # 默认单例不被注入污染
        assert "probe" not in get_rulebook().constants

    def test_relic_affixes_present_in_default(self):
        """A3 消费面：默认 rulebook 带 relic_affixes（main/sub 两表齐备）."""
        rb = get_rulebook()
        assert set(rb.relic_affixes) == {"main", "sub"}
        assert rb.relic_affixes["sub"]["spd"] == 2.6


def test_ability_base_zone_bitwise():
    """技能基数区走 rulebook zones.ability_base 求值，与 Python 拼接逐比特一致（非 isclose）.

    取档/别名映射（scaling 行 def→def_）已随决策卡 #23 下沉 zones 声明
    （ability_base inputs action_scaling，通用 settle 消费）——此处直验乘区表达式本体。
    """
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    got = pipe._zone("ability_base", {
        "atk_scaling": 0.3456, "hp_scaling": 0.0789, "def_scaling": 0.1234,
        "atk": 1234.5, "hp": 5678.9, "def_": 987.6})
    assert got == 0.3456 * 1234.5 + 0.0789 * 5678.9 + 0.1234 * 987.6


def test_dot_tick_rulebook_formula_eval():
    """DoT 跳伤走 rulebook `dot_damage` 公式链（route["dot"]，B27#3 收官）.

    裸件兜底（无 dot_snapshot_ctx）：攻击侧全中性、基数 dot_source_atk×dot_ratio；
    目标侧现值——假人 def 0 无覆写 → 兜底 1000 → 0.5、无弱点 → 非弱点抗 0.8、未击破 0.9：
    5432.1×1.234 × 0.5×0.8×0.9。
    """
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    holder = ActorState(
        actor=Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, spd=100, max_toughness=120)),
        current_hp=1e9)
    mod = Modifier(modifier_id="DOT", name="灼烧", modifier_type="dot", debuff_kind="dot",
                   duration=2, dot_element="fire", dot_ratio=1.234, dot_source_atk=5432.1)
    r = pipe.settle_damage("dot", holder, holder, modifier=mod)
    assert math.isclose(r.value, 5432.1 * 1.234 * 0.5 * 0.8 * 0.9, rel_tol=1e-12)
    assert math.isclose(holder.current_hp, 1e9 - r.value, rel_tol=1e-9)


def test_bleed_tick_rulebook_formula_eval():
    """裂伤跳伤走 rulebook `bleed_dot_damage` 公式链（route["bleed"]，B27#3 收官）.

    基数区 bleed_base_multi 不变（elite 档 → 7000）；裸件 BE/最终伤害中性；
    目标侧链 0.5×0.8×0.9（口径同上）→ 7000×0.36 = 2520。
    """
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    holder = ActorState(
        actor=Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                    stats=StatBlock(hp=100000.0, spd=100, max_toughness=120)),
        current_hp=100000.0)
    mod = Modifier(modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot",
                   debuff_kind="dot", duration=2, dot_element="physical",
                   dot_ratio=1.0, dot_source_atk=0.0)
    r = pipe.settle_damage("bleed", holder, holder, modifier=mod)
    base = min(0.07 * 100000.0, 2 * 3767.5533 * (0.5 + 120 / 40))  # elite 档 → 7000
    assert math.isclose(r.node["bleedBaseMulti"], 7000.0, rel_tol=1e-12)
    assert math.isclose(r.value, base * 0.5 * 0.8 * 0.9, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# B16 冻结规则：乘区取值/公式求值严格按 **AST 求值序**（括号/优先级决定的求值器
# 递归序，不是源码书写位序的隐式约定）——formula_idents 绑定期预解析；多 random()
# 区场景的随机流消耗序由此逐比特钉死（rulebook.yaml 卷头 + 01_formula 顶部注）。
# ---------------------------------------------------------------------------

def test_expression_idents_ast_eval_order():
    """标识符顺序 = AST 求值序（与 expression.evaluate 递归消费子节点的顺序一致）."""
    from hsr_nous.sim_schema.expression import parse
    from hsr_nous.sim_schema.rulebook import _expression_idents

    def idents(src: str):
        return _expression_idents(parse(src, layer="formula").tree)

    assert idents("a * b * c") == ["a", "b", "c"]          # 左结合链 = 书写序
    assert idents("a * (b + c)") == ["a", "b", "c"]        # 括号不改变求值序
    assert idents("x * x") == ["x"]                        # 同名首见去重
    assert idents("min(x, y) * z") == ["x", "y", "z"]      # 调用参数左→右，函数名非数据槽
    assert idents("a && b || c") == ["a", "b", "c"]        # BoolOp 按操作数序
    assert idents("a < b < c") == ["a", "b", "c"]          # 链式比较按操作数序
    # 判别例（三元）：AST 求值序 = 条件先于分支；旧源码位序（预处理改写后）会给分支先
    assert idents("c ? a : b") == ["c", "a", "b"]
    assert idents("c1 ? (c2 ? a : b) : d") == ["c1", "c2", "a", "b", "d"]


def test_damage_formula_idents_pinned():
    """现役 damage 公式取值序钉死（11 乘区；换序/改括号 = 有意变更）."""
    assert list(get_rulebook().formula_idents["damage"]) == [
        "ability_multiplier", "dmg_boost_multi", "ind_dmg_boost_multi", "def_multi",
        "res_multi", "base_universal_multi", "vuln_multi", "final_dmg_multi",
        "crit_multi", "weaken_multi", "dmg_red_multi",
    ]


_RNG_RULEBOOK = """\
zones:
  c:  {expression: "random()", node: cMulti}
  r1: {expression: "random()", node: r1Multi}
  r2: {expression: "random()", node: r2Multi}
  r3: {expression: "random()", node: r3Multi}
formulas:
  fwd:  {expression: "r1 * r2 * r3"}
  rev:  {expression: "r3 * r2 * r1"}
  cond: {expression: "c > 0.5 ? r1 : r2"}
route:
  fwd:  {roll: fwd,  expected: fwd,  settle: {node_formula: fwd,  is_crit: literal_false, scoped: []}}
  rev:  {roll: rev,  expected: rev,  settle: {node_formula: rev,  is_crit: literal_false, scoped: []}}
  cond: {roll: cond, expected: cond, settle: {node_formula: cond, is_crit: literal_false, scoped: []}}
"""

_RNG_SEED = 42


class TestMultiRandomZoneOrder:
    """多 random() 区场景：settle 取值顺序 = 公式 AST 求值序 → 随机流消耗序确定."""

    @pytest.fixture()
    def custom_rb(self, tmp_path, monkeypatch):
        import yaml

        from hsr_nous.sim_schema import rulebook as rb_mod

        p = tmp_path / "rulebook_rng.yaml"
        p.write_text(_RNG_RULEBOOK, encoding="utf-8")
        custom = rb_mod.get_rulebook(p)
        monkeypatch.setattr("hsr_nous.sim.pipeline.get_rulebook", lambda *a, **k: custom)
        return custom

    @staticmethod
    def _holder() -> ActorState:
        return ActorState(
            actor=Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                        stats=StatBlock(hp=1e9, spd=100, max_toughness=120)),
            current_hp=1e9)

    @staticmethod
    def _draws(n: int) -> list:
        rng = random.Random(_RNG_SEED)
        return [rng.random() for _ in range(n)]

    def test_formula_idents_follow_ast_order(self, custom_rb):
        """预解析序：fwd/rev 镜像、cond 条件先于分支（旧源码位序 cond 会给 [r1, c, r2]）."""
        assert custom_rb.formula_idents["fwd"] == ["r1", "r2", "r3"]
        assert custom_rb.formula_idents["rev"] == ["r3", "r2", "r1"]
        assert custom_rb.formula_idents["cond"] == ["c", "r1", "r2"]

    def test_deterministic_same_formula(self, custom_rb):
        """同公式同种子两次结算：值/node/流状态完全一致（确定性）."""
        from hsr_nous.sim.pipeline import MODE_ROLL

        r1 = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED).settle_damage(
            "fwd", self._holder(), self._holder())
        r2 = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED).settle_damage(
            "fwd", self._holder(), self._holder())
        assert r1.value == r2.value and r1.node == r2.node

    def test_stream_consumed_in_formula_order(self, custom_rb):
        """书写序镜像 → 消耗序镜像：fwd 的 r1=第1抽；rev 的 r1=第3抽（顺序由公式定）."""
        from hsr_nous.sim.pipeline import MODE_ROLL

        d1, d2, d3 = self._draws(3)
        rf = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED).settle_damage(
            "fwd", self._holder(), self._holder())
        assert (rf.node["r1Multi"], rf.node["r2Multi"], rf.node["r3Multi"]) == (d1, d2, d3)
        rr = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED).settle_damage(
            "rev", self._holder(), self._holder())
        assert (rr.node["r3Multi"], rr.node["r2Multi"], rr.node["r1Multi"]) == (d1, d2, d3)
        assert rf.node["r1Multi"] != rr.node["r1Multi"], "换序即换消耗位（顺序敏感实证）"

    def test_ternary_condition_draws_first(self, custom_rb):
        """AST 求值序锚：三元条件区先抽（c=第1抽、r1=第2抽、r2=第3抽）——
        旧源码位序实现下 r1 会拿第1抽，本断言对"位序回退"即红."""
        from hsr_nous.sim.pipeline import MODE_ROLL

        d1, d2, d3 = self._draws(3)
        r = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED).settle_damage(
            "cond", self._holder(), self._holder())
        assert (r.node["cMulti"], r.node["r1Multi"], r.node["r2Multi"]) == (d1, d2, d3)
        assert list(r.node)[:4] == ["formula", "cMulti", "r1Multi", "r2Multi"]
        # 抽取数契约：cond 恰好 3 抽（c/r1/r2 三区各一），公式求值自身零消耗
        p = SettlementPipeline(mode=MODE_ROLL, seed=_RNG_SEED)
        p.settle_damage("cond", self._holder(), self._holder())
        fresh = random.Random(_RNG_SEED)
        for _ in range(3):
            fresh.random()
        assert p.rng.getstate() == fresh.getstate()
