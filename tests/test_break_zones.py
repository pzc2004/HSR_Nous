"""击破增伤池接线（任务 A）+ 削韧双池迁移（任务 B）行为测试.

spec 锚点：01_formula 击破式/超击破式/§1.5 削韧式 + mechanics 02 §2.10/§2.11。
超击破注记：引擎尚无超击破结算路径（rulebook 表达式入簿备镜、route 未接、
无转换倍率源实例）——超击破部分只钉可执行 spec（rulebook 公式层）的三池
两两乘算性质，不实测引擎结算。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, SettlementPipeline
from hsr_nous.sim.state import ActorState, Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
from hsr_nous.sim_schema.expression import evaluate
from hsr_nous.sim_schema.rulebook import get_rulebook

# 手算锚（与 test_crosscheck_optimizer 同基准）：冰 scaling=1.0、maxTough=120、BE=1.0、
# lvl80 vs 白板防 1000（defMulti 0.5）、弱点抗 0（resMulti 1.0）、易伤 0
# breakBase = 3767.5533 × (0.5+120/40) = 13186.43655；×beMulti 2.0 ×def 0.5 → 13186.43655
_BASE_BREAK = 3767.5533 * (0.5 + 120 / 40) * 2.0 * 0.5


def _mod(mid: str, **stats: float) -> Modifier:
    return Modifier(modifier_id=mid, name=mid, modifier_type="buff",
                    stat_effects={k: float(v) for k, v in stats.items()})


def _src_state(*mods: Modifier) -> ActorState:
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=2000, spd=200, hp=5000, max_energy=100,
                                 break_effect=1.0, crit_rate=0.0))
    return ActorState(actor=hero, current_hp=hero.stats.hp,
                      modifiers={m.modifier_id: m for m in mods})


def _break_target() -> ActorState:
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=120.0, weakness=["ice"]))
    return ActorState(actor=enemy, current_hp=1e9, broken=True)


class TestBreakDmgBoostPool:
    """任务 A：break_dmg_boost_multi 接真实面板池（dmg_bonus 桶键 break_dmg_boost）."""

    def test_no_buff_unchanged(self):
        """无 buff：与旧中性喂入逐值一致（golden 锚不动）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        r = pipe.break_damage(_src_state(), _break_target(), "ice")
        assert math.isclose(r.value, _BASE_BREAK, rel_tol=1e-9)
        assert math.isclose(r.node["breakDmgBoostMulti"], 1.0, rel_tol=1e-9)

    def test_single_buff_amplifies(self):
        """击破伤害提高 16%：击破伤害 ×1.16."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        st = _src_state(_mod("b1", dmg_break_dmg_boost=0.16))
        r = pipe.break_damage(st, _break_target(), "ice")
        assert math.isclose(r.node["breakDmgBoostMulti"], 1.16, rel_tol=1e-9)
        assert math.isclose(r.value, _BASE_BREAK * 1.16, rel_tol=1e-9)

    def test_pool_additive_two_sources(self):
        """双源池内加算：0.10+0.20 → ×1.30（非乘算 1.10×1.20=1.32）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        st = _src_state(_mod("b1", dmg_break_dmg_boost=0.10),
                        _mod("b2", dmg_break_dmg_boost=0.20))
        r = pipe.break_damage(st, _break_target(), "ice")
        assert math.isclose(r.node["breakDmgBoostMulti"], 1.30, rel_tol=1e-9)
        assert not math.isclose(r.node["breakDmgBoostMulti"], 1.32, rel_tol=1e-9)
        assert math.isclose(r.value, _BASE_BREAK * 1.30, rel_tol=1e-9)

    def test_super_break_boost_pool_in_bucket(self):
        """super_break_dmg_boost 桶键可用（多源加算收敛），供未来超击破结算路径读取."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        st = _src_state(_mod("b1", dmg_super_break_dmg_boost=0.20),
                        _mod("b2", dmg_super_break_dmg_boost=0.15))
        se = pipe.effective_stats(st)
        assert math.isclose(se["dmg_bonus"]["super_break_dmg_boost"], 0.35, rel_tol=1e-9)


class TestSuperBreakFormulaSpec:
    """任务 A（可执行 spec 层）：超击破三池两两乘算（社区实测口径，mechanics §2.11）.

    引擎无超击破结算路径，本类直接求值 rulebook 表达式钉 spec 性质。
    """

    _CTX = {
        "base_universal_multi": 1.0, "def_multi": 0.5, "res_multi": 1.0,
        "vuln_multi": 1.0, "final_dmg_multi": 1.0, "super_break_base_multi": 100.0,
        "be_multi": 2.0, "super_break_conversion_multi": 1.6,
        "break_dmg_boost_multi": 1.0, "super_break_dmg_boost_multi": 1.0,
        "dmg_red_multi": 1.0,
    }

    def _eval(self, **overrides: float) -> float:
        rb = get_rulebook()
        return evaluate(rb.formulas["super_break_damage"],
                        context={**self._CTX, **overrides}).value

    def test_break_boost_also_amplifies_super_break(self):
        """击破伤害提高池对超击破同样生效（共池）."""
        v0 = self._eval()
        v1 = self._eval(break_dmg_boost_multi=1.16)
        assert math.isclose(v1 / v0, 1.16, rel_tol=1e-9)

    def test_two_pools_multiply_not_add(self):
        """三池两两乘算：(1+0.16)×(1+0.20)，非 (1+0.16+0.20)."""
        v0 = self._eval()
        v = self._eval(break_dmg_boost_multi=1.16, super_break_dmg_boost_multi=1.20)
        assert math.isclose(v / v0, 1.16 * 1.20, rel_tol=1e-9)
        assert not math.isclose(v / v0, 1.36, rel_tol=1e-9)

    def test_pool_zones_additive_within(self):
        """池内加算由乘区表达式保证：1 + pool（pool 值在面板层加算收敛）."""
        rb = get_rulebook()
        z = evaluate(rb.zones["super_break_dmg_boost_multi"],
                     context={"super_break_dmg_boost": 0.35}).value
        assert math.isclose(z, 1.35, rel_tol=1e-9)


class TestToughnessDualPool:
    """任务 B：削韧迁 rulebook toughness_damage 式 + 双效率池乘算."""

    def test_amount_dual_pool_multiplicative(self):
        """双池乘算：10 × (1+0.5) × (1+0.5) = 22.5（非单加算池 10 × (1+1.0) = 20）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        st = _src_state(_mod("b1", break_efficiency_boost=0.5),
                        _mod("b2", weakness_break_efficiency_boost=0.5))
        amount = pipe.toughness_damage_amount(st, 10.0)
        assert math.isclose(amount, 22.5, rel_tol=1e-9)
        assert not math.isclose(amount, 20.0, rel_tol=1e-9)

    def test_amount_single_pool_unchanged(self):
        """单源不变：任一池单挂 0.5 → ×1.5（与旧单池语义同值；无 buff → 原值）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        pool1 = _src_state(_mod("b1", break_efficiency_boost=0.5))
        pool2 = _src_state(_mod("b2", weakness_break_efficiency_boost=0.5))
        assert math.isclose(pipe.toughness_damage_amount(pool1, 10.0), 15.0, rel_tol=1e-9)
        assert math.isclose(pipe.toughness_damage_amount(pool2, 10.0), 15.0, rel_tol=1e-9)
        assert math.isclose(pipe.toughness_damage_amount(_src_state(), 10.0), 10.0, rel_tol=1e-9)
        # source=None（非在册来源）双池取 0，不炸
        assert math.isclose(pipe.toughness_damage_amount(None, 10.0), 10.0, rel_tol=1e-9)

    def _engine(self) -> CombatEngine:
        hero = Actor(actor_id="hero", name="测试员", level=80,
                     stats=StatBlock(atk=2000, spd=200, hp=5000, max_energy=100))
        enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=100, max_toughness=120.0, weakness=["fire"]))
        action = Action(action_id="a1", name="a1", action_type="basic", target_type="single",
                        damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=30)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=1000))
        eng = CombatEngine(enc, actions_by_actor={"hero": [action]},
                           mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def test_engine_dual_pool_and_event_payload(self):
        """引擎集成：双池削韧 30×2.25=67.5，on_toughness_damage 载荷 amount 同步."""
        eng = self._engine()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(hero_st, _mod("b1", break_efficiency_boost=0.5))
        eng._apply_modifier(hero_st, _mod("b2", weakness_break_efficiency_boost=0.5))
        events = []
        eng.bus.subscribe("on_toughness_damage", lambda t, p, c: events.append(p))
        eng._apply_toughness_damage(hero_st.actor, eng.actions_by_actor["hero"][0], e1)
        assert math.isclose(120.0 - e1.toughness, 67.5, rel_tol=1e-9)
        assert math.isclose(events[-1]["amount"], 67.5, rel_tol=1e-9)
        assert events[-1]["source"] == "hero" and events[-1]["target"] == "e1"

    def test_engine_single_pool_unchanged(self):
        """引擎集成：阮梅族单 buff（池 2 挂 0.5）削韧 30×1.5=45，与归池前同值."""
        eng = self._engine()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(hero_st, _mod("b1", weakness_break_efficiency_boost=0.5))
        eng._apply_toughness_damage(hero_st.actor, eng.actions_by_actor["hero"][0], e1)
        assert math.isclose(120.0 - e1.toughness, 45.0, rel_tol=1e-9)
