"""护盾系统（v0.9，mechanics 01 §1.3 为唯一事实来源）.

- 并行吸收：所有护盾同时吸收全额伤害；本体只承 max(0, 伤害 − 最高盾剩余)
- 低值盾后台破裂 → 关联 modifier 级联消失（附带效果一并移除），高值盾保留
- 单次伤害超过最高盾剩余 → 溢出扣本体 HP
- 真伤同走护盾吸收层（mechanics 02 §2.13：护盾非乘区，是乘区结算后的吸收层）
- 发射点 shield_absorbed / shield_broken；B16 两局全等
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

# 期望模式下手算锚点：atk1000 ×1.0倍率 ×0.5防御 ×0.8非弱点抗性 ×0.9未击破 ×1.025期望暴击 = 369
HIT = 369.0


def _ally():
    return Actor(actor_id="h", name="盾兵", level=80,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))


def _enemy():
    return Actor(actor_id="e", name="敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=1000, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk():
    return Action(action_id="e_atk", name="爪击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _engine(av=250.0, mode=MODE_EXPECTED, seed=None):
    enc = Encounter(encounter_id="t", name="t", actors=[_ally(), _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=mode, seed=seed,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _shield_spec(mid, value, **extra):
    spec = {"modifier_id": mid, "name": mid, "modifier_type": "buff",
            "duration": 3, "shield": {"flat": value}}
    spec.update(extra)
    return spec


def _hit_ally(eng):
    """敌方一击（期望模式定值 369）."""
    eng._execute_action(eng.state.actors["e"], _enemy_atk())


class TestShieldAbsorb:
    def test_parallel_absorb_high_shield_survives(self):
        """两盾同时扣全额；低盾破高盾留，本体不掉血."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, _shield_spec("SH_A", 500.0), st)
        eng._apply_modifier_spec(st, _shield_spec(
            "SH_B", 100.0, stat_effects={"taunt": 500.0}), st)
        events = []
        eng.bus.subscribe("shield_absorbed", lambda et, p, ctx: events.append((et, dict(p))))
        eng.bus.subscribe("shield_broken", lambda et, p, ctx: events.append((et, dict(p))))

        _hit_ally(eng)

        a = next(s for s in st.shields if s.shield_id == "SH_A")
        assert math.isclose(a.remaining, 500.0 - HIT), "高盾各扣全额 369"
        assert all(s.shield_id != "SH_B" for s in st.shields), "低盾后台破裂离场"
        assert math.isclose(st.current_hp, 3000.0), "本体承伤 = max(0, 369 − 500) = 0"
        # 级联：低盾 modifier 连带消失（附带 taunt 提升一并移除），高盾 modifier 保留
        assert "SH_B" not in st.modifiers
        assert "SH_A" in st.modifiers
        # 发射点载荷：逐盾 absorbed（各扣 min(剩余, 全额)）+ 低盾 broken
        absorbed = [p for et, p in events if et == "shield_absorbed"]
        assert {(p["shield_id"], round(p["amount"], 1)) for p in absorbed} == {
            ("SH_A", 369.0), ("SH_B", 100.0)}
        assert all(p["source"] == "e" and p["target"] == "h" for p in absorbed)
        broken = [p for et, p in events if et == "shield_broken"]
        assert [p["shield_id"] for p in broken] == ["SH_B"]

    def test_overflow_to_hp(self):
        """伤害超过最高盾剩余：未吸收部分溢出扣本体，两盾俱碎."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, _shield_spec("SH_A", 300.0), st)
        eng._apply_modifier_spec(st, _shield_spec("SH_B", 200.0), st)
        _hit_ally(eng)
        assert math.isclose(st.current_hp, 3000.0 - (HIT - 300.0)), "溢出 = 369 − 最高盾 300 = 69"
        assert not st.shields, "两盾均被全额击穿"
        assert "SH_A" not in st.modifiers and "SH_B" not in st.modifiers

    def test_true_damage_blocked_by_shield(self):
        """真伤（无乘区固定伤害）经同一吸收层被护盾抵挡."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, _shield_spec("SH_A", 500.0), st)
        overflow = eng._absorb_with_shields(st, 250.0, "true_src")
        assert math.isclose(overflow, 0.0)
        assert math.isclose(st.shields[0].remaining, 250.0)
        assert math.isclose(st.current_hp, 3000.0)

    def test_dot_goes_through_shield_layer(self):
        """DoT 跳伤吃盾：盾吸收、溢出才扣本体."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, _shield_spec("SH_A", 300.0), st)
        eng._apply_modifier(st, Modifier(
            modifier_id="DOT", name="灼烧", modifier_type="dot", debuff_kind="dot",
            duration=2, source_id="e", dot_element="fire", dot_ratio=1.0, dot_source_atk=400.0))
        eng._tick_dots(st)
        assert not st.shields, "400 跳伤击穿 300 盾"
        assert math.isclose(st.current_hp, 2900.0), "本体只承溢出 100"

    def test_dispel_removes_linked_shield(self):
        """反向级联：modifier 被驱散 → 其护盾实例一并移除."""
        eng = _engine()
        st = eng.state.actors["h"]
        eng._apply_modifier_spec(st, _shield_spec("SH_A", 500.0), st)
        assert eng.dispel(st) == 1
        assert not st.shields and "SH_A" not in st.modifiers

    def test_shield_value_formula_and_refresh(self):
        """护盾值 = (属性×倍率 + 固定值) × (1 + Shield_Bonus%)；同 modifier 重挂整换刷新."""
        eng = _engine()
        st = eng.state.actors["h"]
        caster = eng.state.actors["h"]
        caster.actor.stats.def_ = 1000.0
        caster.actor.stats.shield_bonus = 0.1
        spec = {"modifier_id": "SH_M", "name": "三月盾", "duration": 3,
                "shield": {"scaling": {"def": 0.48}, "flat": 640.0}}
        eng._apply_modifier_spec(st, spec, caster)
        # (1000×0.48 + 640) × 1.1 = 1232
        assert math.isclose(st.shields[0].remaining, 1232.0)
        eng._absorb_with_shields(st, 232.0)
        assert math.isclose(st.shields[0].remaining, 1000.0)
        eng._apply_modifier_spec(st, spec, caster)  # 重挂 → 整换为新值，不叠加
        assert len(st.shields) == 1
        assert math.isclose(st.shields[0].remaining, 1232.0)


class TestShieldB16:
    def test_two_runs_identical_with_shields(self):
        """B16：同配置同种子两局逐字段全等（含护盾栈快照）."""
        def build():
            ally = Actor(actor_id="h", name="盾兵", level=80,
                         stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100))
            skill = Action(action_id="sh_skill", name="加盾", action_type="skill",
                           target_type="self", skill_point_cost=1,
                           apply_modifiers=[{"modifier_id": "SH_A", "name": "护盾",
                                             "duration": 3, "stat_effects": {"taunt": 500.0},
                                             "shield": {"flat": 400.0}}])
            basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                           damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)
            enc = Encounter(encounter_id="t", name="t", actors=[ally, _enemy()],
                            termination=TerminationConfig(mode="fixed_av", max_action_value=250))
            eng = CombatEngine(enc, actions_by_actor={"h": [skill, basic], "e": [_enemy_atk()]},
                               policy=ScriptedPolicy(rotation=["skill", "basic"]),
                               mode=MODE_ROLL, seed=42, initial_sp=10, initial_energy_ratio=0.0)
            return eng.run().snapshot()

        s1, s2 = build(), build()
        assert s1 == s2
        assert s1["actors"]["h"]["shields"], "战斗结束后护盾栈应进快照"


class TestShieldFormulaBook:
    """护盾值走 rulebook `shield` 公式求值（原则 B 迁移：pipeline.shield_value 唯一路径）."""

    def test_three_scalings_and_bonus_each_apply(self):
        """def/hp/atk 三缩放槽各生效 + flat + shield_bonus：(480+300+100+640)×1.1 = 1672."""
        eng = _engine()
        st = eng.state.actors["h"]
        caster = eng.state.actors["h"]
        caster.actor.stats.def_ = 1000.0
        caster.actor.stats.atk = 500.0  # hp 3000 为 _ally 自带
        caster.actor.stats.shield_bonus = 0.1
        spec = {"modifier_id": "SH_T", "name": "三槽盾", "duration": 3,
                "shield": {"scaling": {"def": 0.48, "hp": 0.1, "atk": 0.2}, "flat": 640.0}}
        eng._apply_modifier_spec(st, spec, caster)
        assert math.isclose(st.shields[0].remaining, 1672.0)

    def test_no_buff_bitwise_unchanged(self):
        """无 buff 场景与旧 Python 拼接逐比特一致（迁移零数值漂移，非 isclose）."""
        eng = _engine()
        st = eng.state.actors["h"]
        caster = eng.state.actors["h"]
        caster.actor.stats.def_ = 1000.5
        spec = {"modifier_id": "SH_B", "name": "锚点盾", "duration": 3,
                "shield": {"scaling": {"def": 0.3456}, "flat": 640.25}}
        eng._apply_modifier_spec(st, spec, caster)
        expected = (1000.5 * 0.3456 + 640.25) * (1.0 + 0.0)  # 迁移前 Python 拼接口径
        assert st.shields[0].remaining == expected

    def test_unknown_scaling_slot_raises(self):
        """公式外缩放槽位报错指路（rulebook shield 仅 def/hp/atk 三槽），不静默吞."""
        eng = _engine()
        st = eng.state.actors["h"]
        spec = {"modifier_id": "SH_X", "name": "异槽盾", "duration": 3,
                "shield": {"scaling": {"spd": 1.0}, "flat": 100.0}}
        with pytest.raises(ValueError, match="公式外槽位"):
            eng._apply_modifier_spec(st, spec, st)
