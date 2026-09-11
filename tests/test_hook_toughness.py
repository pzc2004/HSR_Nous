"""hook 伤害通道削韧收编（2026-09-07）：deal_damage `toughness_dmg` 与 action 层同键同语义.

语义钉（05_effects §造成伤害 / 03_actor §3.4）：hook 段削韧同走 `_apply_toughness_damage`
单漏斗——own_element 默认闸（攻击属性 ∈ 目标有效弱点才削）/ 双效率池 / 击破判定 /
多韧性条全同口径；逐目标逐 effect 各削（多段 = 多个 deal_damage 各声明，mechanics 04
"削韧值按比例分布在每一段"同构）；`category: "true"` 互斥（真伤无属性不削韧，
mechanics 02 §2.8）编译期炸。
实例锚：风堇 1140901 忆灵技 10 / 遐蝶 140709 死龙半 10 + 1140706 每段 5 /
长夜月 141303·1141307 各 30（米游社在案，三模板已回填）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(enemy_weakness=("ice",), max_toughness=100.0) -> CombatEngine:
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100,
                                 crit_rate=0.0, crit_dmg=0.5))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=max_toughness,
                                  weakness=list(enemy_weakness)))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hook_hit(eng: CombatEngine, **eff) -> None:
    base = {"effect_type": "deal_damage", "target": "enemy_first",
            "damage_type": "ice", "amount": 100.0}
    base.update(eff)
    eng._hooks._run_hook_effect(eng.state.actors["hero"], base, {})


class TestHookDealDamageToughness:
    def test_weakness_match_reduces(self):
        """弱点匹配：削韧 10 生效 + on_toughness_damage 照发（载荷 source/target 同 action 层）."""
        eng = _engine(enemy_weakness=["ice"])
        st = eng.state.actors["e1"]
        seen = []
        eng.bus.subscribe("on_toughness_damage", lambda et, p, ctx: seen.append(p))
        hp0 = st.current_hp
        _hook_hit(eng, toughness_dmg=10)
        assert math.isclose(st.toughness, 90.0, rel_tol=1e-9)
        assert seen and math.isclose(seen[-1]["amount"], 10.0, rel_tol=1e-9)
        assert seen[-1]["source"] == "hero" and seen[-1]["target"] == "e1"
        assert st.current_hp < hp0, "削韧不顶替伤害——HP 照扣"

    def test_weakness_mismatch_no_reduce(self):
        """不匹配：火打冰弱点怪削韧 = 0（own_element 默认闸同 action 层），伤害照落."""
        eng = _engine(enemy_weakness=["ice"])
        st = eng.state.actors["e1"]
        seen = []
        eng.bus.subscribe("on_toughness_damage", lambda et, p, ctx: seen.append(p))
        hp0 = st.current_hp
        _hook_hit(eng, damage_type="fire", toughness_dmg=10)
        assert st.toughness == 100.0
        assert not seen, "闸门拦下不得发 on_toughness_damage"
        assert st.current_hp < hp0

    def test_default_zero_no_reduce(self):
        """缺省不写 = 不削（旧行为不变——回归闸）."""
        eng = _engine(enemy_weakness=["ice"])
        st = eng.state.actors["e1"]
        _hook_hit(eng)
        assert st.toughness == 100.0

    def test_break_triggers(self):
        """削到 0 触发击破：broken/bars_exhausted + on_break + 击破伤害入账（同一管线，非只扣韧性）."""
        eng = _engine(enemy_weakness=["ice"], max_toughness=30.0)
        st = eng.state.actors["e1"]
        breaks = []
        eng.bus.subscribe("on_break", lambda et, p, ctx: breaks.append(p))
        hp0 = st.current_hp
        _hook_hit(eng, toughness_dmg=30)
        assert st.toughness == 0.0
        assert st.broken and st.bars_exhausted
        assert breaks and breaks[-1]["element"] == "ice"
        assert breaks[-1]["source"] == "hero" and breaks[-1]["target"] == "e1"
        assert eng.state.total_damage > 100.0, "击破伤害应计入总账（直伤 100 之外还有击破份）"
        assert st.current_hp < hp0 - 100.0
        # 条尽不可再削（04_break_system §4.5）——第二发不再发 on_toughness_damage
        seen = []
        eng.bus.subscribe("on_toughness_damage", lambda et, p, ctx: seen.append(p))
        _hook_hit(eng, toughness_dmg=30)
        assert not seen

    def test_multihit_each_segment_reduces(self):
        """多段各削：两段各 5 → 合计 10（逐段分布同构——遐蝶 1140706 六段×5 族）."""
        eng = _engine(enemy_weakness=["ice"])
        st = eng.state.actors["e1"]
        seen = []
        eng.bus.subscribe("on_toughness_damage", lambda et, p, ctx: seen.append(p))
        for _ in range(2):
            _hook_hit(eng, toughness_dmg=5)
        assert math.isclose(st.toughness, 90.0, rel_tol=1e-9)
        assert len(seen) == 2 and all(math.isclose(p["amount"], 5.0) for p in seen)

    def test_efficiency_dual_pool_same_pipeline(self):
        """双效率池同口径：10 × (1+0.5)(1+0.5) = 22.5（与 action 层同一结算式单漏斗）."""
        eng = _engine(enemy_weakness=["ice"])
        hero_st = eng.state.actors["hero"]
        st = eng.state.actors["e1"]
        eng._apply_modifier(hero_st, Modifier(
            modifier_id="b1", name="b1", modifier_type="buff",
            stat_effects={"break_efficiency_boost": 0.5}))
        eng._apply_modifier(hero_st, Modifier(
            modifier_id="b2", name="b2", modifier_type="buff",
            stat_effects={"weakness_break_efficiency_boost": 0.5}))
        _hook_hit(eng, toughness_dmg=10)
        assert math.isclose(st.toughness, 100.0 - 22.5, rel_tol=1e-9)

    def test_expression_value(self):
        """toughness_dmg 支持表达式（_hook_amount 通道）：按来源面板现场求值."""
        eng = _engine(enemy_weakness=["ice"])
        st = eng.state.actors["e1"]
        _hook_hit(eng, toughness_dmg="$self.atk * 0.01")   # 1000×0.01 = 10
        assert math.isclose(st.toughness, 90.0, rel_tol=1e-9)


class TestHookToughnessCompileGates:
    def test_true_damage_mutex(self):
        """category 'true' × toughness_dmg 互斥——真伤无属性不削韧（mechanics 02 §2.8）."""
        with pytest.raises(ValueError, match="互斥"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "target": "enemy_first",
                  "damage_type": "ice", "amount": 100, "category": "true",
                  "toughness_dmg": 10}], "t")

    def test_param_key_and_expr_slot_accepted(self):
        """toughness_dmg 在 deal_damage 参数词表 + 表达式槽（正键/表达式不误炸）."""
        BuildCompiler()._validate_effects(
            [{"effect_type": "deal_damage", "target": "enemy_first",
              "damage_type": "ice", "amount": 100, "toughness_dmg": 10}], "t")
        BuildCompiler()._validate_effects(
            [{"effect_type": "deal_damage", "target": "enemy_first",
              "damage_type": "ice", "amount": 100,
              "toughness_dmg": "$self.atk * 0.01"}], "t")

    def test_bad_expr_rejected_at_compile(self):
        """表达式槽预编译闸：错拼 $self 字段编译期炸（B8 同口径——不静默到运行期）."""
        with pytest.raises(ValueError, match="atkk"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "target": "enemy_first",
                  "damage_type": "ice", "amount": 100,
                  "toughness_dmg": "$self.atkk * 0.01"}], "t")
