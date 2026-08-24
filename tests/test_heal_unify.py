"""治疗归一（rulebook `heal` 公式单一路径）+ 效果抵抗穿透接线.

spec 锚点：mechanics 01 §1.3 治疗公式（(属性×倍率+固定)×(1+Outgoing+Incoming−Reduction)）
+ rulebook formulas.heal / zones.ehr_multi（可执行唯一来源）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, SettlementPipeline
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import ActorState, Modifier
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _mod(mid: str, **stats: float) -> Modifier:
    return Modifier(modifier_id=mid, name=mid, modifier_type="buff",
                    stat_effects={k: float(v) for k, v in stats.items()})


def _src(heal_bonus: float = 0.0) -> ActorState:
    hero = Actor(actor_id="h", name="医师", level=80,
                 stats=StatBlock(atk=2000, spd=100, hp=4000, max_energy=100,
                                 heal_bonus=heal_bonus))
    return ActorState(actor=hero, current_hp=hero.stats.hp)


def _tgt(*mods: Modifier) -> ActorState:
    ally = Actor(actor_id="a", name="伤员", level=80,
                 stats=StatBlock(hp=5000, spd=100, max_energy=100))
    return ActorState(actor=ally, current_hp=1000.0,
                      modifiers={m.modifier_id: m for m in mods})


class TestHealUnify:
    def test_caster_heal_bonus_applies(self):
        """施放者 heal_bonus（Outgoing_Healing_Boost）：固定治疗 1000 × 1.20."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        r = pipe.heal(_src(heal_bonus=0.20), _tgt(), 1000.0)
        assert math.isclose(r.value, 1200.0, rel_tol=1e-9)
        assert math.isclose(r.node["healBonusMulti"], 1.20, rel_tol=1e-9)

    def test_caster_heal_bonus_from_modifier(self):
        """施放者 heal_bonus 经 modifier（effective_stats 层）同样生效."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src()
        src.modifiers["m1"] = _mod("m1", heal_bonus=0.10)
        r = pipe.heal(src, _tgt(), 1000.0)
        assert math.isclose(r.value, 1100.0, rel_tol=1e-9)

    def test_target_incoming_heal_applies(self):
        """受疗者 incoming_heal（Incoming）：加成为正 ×1.30；降低为负 ×0.10（萨姆领域族）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        r = pipe.heal(_src(), _tgt(_mod("m1", incoming_heal=0.30)), 1000.0)
        assert math.isclose(r.value, 1300.0, rel_tol=1e-9)
        r2 = pipe.heal(_src(), _tgt(_mod("m2", incoming_heal=-0.90)), 1000.0)
        assert math.isclose(r2.value, 100.0, rel_tol=1e-9)

    def test_heal_bonus_not_read_from_dmg_bonus_bucket(self):
        """读桶修复：dmg_bonus 桶里的 'heal_bonus' 键不再被误读（旧 bug 路径）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        hero = Actor(actor_id="h", name="医师", level=80,
                     stats=StatBlock(atk=2000, spd=100, hp=4000, max_energy=100,
                                     dmg_bonus={"heal_bonus": 0.50}))
        r = pipe.heal(ActorState(actor=hero, current_hp=hero.stats.hp), _tgt(), 1000.0)
        assert math.isclose(r.value, 1000.0, rel_tol=1e-9), "增伤桶键不应误当治疗加成"

    def test_hp_scaling_path(self):
        """倍率路径：hp_scaling=0.5 × 施放者有效 HP 4000 = 2000（rulebook heal 式基数区）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        tgt = _tgt()
        r = pipe.heal(_src(), tgt, hp_scaling=0.5)
        assert math.isclose(r.value, 2000.0, rel_tol=1e-9)
        assert math.isclose(tgt.current_hp, 3000.0, rel_tol=1e-9)

    def test_engine_heal_self_routes_pipeline(self):
        """engine heal_self 收编走管线：吃施放者 heal_bonus（收编前不吃）."""
        ally = Actor(actor_id="h", name="医师", level=80,
                     stats=StatBlock(hp=4000, atk=1000, def_=1000, spd=100, max_energy=100,
                                     heal_bonus=0.20))
        enemy = Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=50, max_toughness=120.0))
        enc = Encounter(encounter_id="t", name="t", actors=[ally, enemy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=250))
        eng = CombatEngine(enc, policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["h"]
        st.current_hp = 1000.0
        inc: list = []
        eng.bus.subscribe("on_hp_increase", lambda t, p, c: inc.append(p))
        eng._run_hook_effect(st, {"effect_type": "heal_self", "ratio": 0.5}, {}, {})
        # 4000×0.5×(1+0.20) = 2400（旧孤儿口径为 2000）
        assert math.isclose(st.current_hp, 3400.0, rel_tol=1e-9)
        assert len(inc) == 1 and math.isclose(inc[0]["amount"], 2400.0, rel_tol=1e-9)


class TestHitChancePen:
    def test_effect_res_pen_raises_chance(self):
        """效果抵抗穿透接 ehr_multi：(1 − 0.4 + 0.3) = 0.9（无穿透为 0.6）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        chance = pipe.hit_chance({"effect_hit": 0.0}, {"effect_res": 0.4}, 1.0,
                                 effect_res_pen=0.3)
        assert math.isclose(chance, 0.9, rel_tol=1e-9)
        chance_no_pen = pipe.hit_chance({"effect_hit": 0.0}, {"effect_res": 0.4}, 1.0)
        assert math.isclose(chance_no_pen, 0.6, rel_tol=1e-9)

    def test_pen_via_panel_flows_at_engine_callsite(self):
        """引擎调用点：modifier 面板 effect_res_pen 经 se 喂入（debuff 施加判定）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = ActorState(
            actor=Actor(actor_id="h", name="测试员", level=80,
                        stats=StatBlock(hp=3000, spd=100, max_energy=100)),
            current_hp=3000.0,
            modifiers={"m1": _mod("m1", effect_res_pen=0.3)})
        se = pipe.effective_stats(src)
        chance = pipe.hit_chance(se, {"effect_res": 0.4}, 1.0,
                                 effect_res_pen=se.get("effect_res_pen", 0.0))
        assert math.isclose(chance, 0.9, rel_tol=1e-9)
