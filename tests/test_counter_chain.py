"""弑魂之炽（140809）端到端：挂状态→敌方全体立即行动→逐怪叠层→行动完毕插入反击→解除.

机制逻辑（hook）以代码注册——代表"模板机制的语义"，DSL 化留给机制收编阶段。
数值口径：atk=2000 crit(0.5,1.0) 期望模式 def×res=0.5 未击破 ×0.9 → 倍率 1.0 = 1350。
"""
from __future__ import annotations

import math

from dataclasses import replace

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

PYRE = "SOUL_PYRE"


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _monster(eid):
    return Actor(actor_id=eid, name=f"怪{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=500, spd=100, max_toughness=9999, weakness=["physical"]))


def _monster_attack(eid):
    return [Action(action_id=f"{eid}_atk", name="撕咬", action_type="basic", target_type="single",
                   damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)]


def _soul_edict():
    """灾厄•弑魂焚诏：获得 1 层弑魂之炽（减伤 30%）+ 敌方全体立即行动."""
    return Action(action_id="140809", name="灾厄•弑魂焚诏", action_type="skill",
                  target_type="self", skill_point_cost=1,
                  act_now_targets="all_enemies",
                  apply_modifiers=[{
                      "modifier_id": PYRE, "name": "弑魂之炽", "modifier_type": "buff",
                      "stacks": 1, "max_stack": 99,
                      "stat_effects": {"dmg_dmg_reduction": 0.30}}])


def _counter_action(stacks: int):
    """反击（140809）：aoe 主反击（倍率 1.0 + 层数×0.05）+ 额外 3 段随机单体."""
    return (
        Action(action_id="pyre_counter", name="弑魂反击", action_type="follow_up",
               target_type="aoe", damage_type="physical",
               scaling=[{"atk": 1.0 + 0.05 * stacks}], toughness_dmg=10),
        Action(action_id="pyre_counter_bounce", name="弑魂反击·追击", action_type="follow_up",
               target_type="bounce", damage_type="physical",
               scaling=[{"atk": 0.5}], toughness_dmg=5, instances=3),
    )


def _engine():
    actions = {"1408": [_soul_edict()],
               "e1": _monster_attack("e1"), "e2": _monster_attack("e2")}
    enc = Encounter(encounter_id="t", name="t",
                    actors=[_phainon(), _monster("e1"), _monster("e2")],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=100.0))
    eng = CombatEngine(enc, actions_by_actor=actions,
                       policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()

    # 弑魂之炽机制 hook（代表模板机制语义）：敌方行动叠层，全体行动完毕 → 反击+解除
    track = {"m": 0, "n": 0}

    def hook(et, payload, ctx):
        st = eng.state.actors["1408"]
        mod = st.modifiers.get(PYRE)
        if mod is None:
            track["m"] = track["n"] = 0
            return
        if payload.get("insert") or payload.get("actor") == "1408":
            return  # 插入行动不递归；白厄自身行动不计
        if track["m"] == 0:
            track["m"] = len(eng._enemies_alive())  # 立即行动的敌方全体数量
        mod.stacks += 1
        track["n"] += 1
        if track["n"] >= track["m"]:
            main, bounce = _counter_action(mod.stacks)
            eng.trigger_action(st, main, tag="counter")
            eng.trigger_action(st, bounce, tag="counter")
            eng._remove_modifier(st, PYRE, "counter_done")
            track["m"] = track["n"] = 0

    eng.bus.subscribe("on_action", hook)
    return eng, track


class TestSoulPyreCounter:
    def test_full_counter_chain(self):
        eng, _track = _engine()
        state = eng.run()
        log = state.log

        # 1. 弑魂焚诏施放 + 敌方全体立即行动（2 怪均在白厄下一动前行动）
        assert any("灾厄•弑魂焚诏" in l for l in log)
        # 2. 插入反击发生（aoe + bounce 追击）
        assert any("插入发动 弑魂反击" in l for l in log)
        assert any("插入发动 弑魂反击·追击" in l for l in log)
        # 3. 弑魂之炽已解除
        assert PYRE not in state.actors["1408"].modifiers
        # 4. 反击伤害对轴：施放时 1 层 + 2 怪行动叠 2 层 = 3 层
        #    aoe 倍率 1.0+3×0.05=1.15 → 每怪 2000×1.15×1.5×0.5×0.9=1552.5
        #    bounce 3 段 × 0.5 → 期望模式全中首怪 3×675=2025
        #    反击合计 2×1552.5 + 2025 = 5130
        #    （怪物攻击造成的伤害与白厄行动无关，不计入本断言的触发方）
        counter_main_per_enemy = 2000 * 1.15 * 1.5 * 0.5 * 0.9
        expected_counter = 2 * counter_main_per_enemy + 3 * 675.0
        # 从日志无法直接拆反击分项——用怪 hp 反推反击伤害（怪只受反击伤害）
        e1_taken = 1e9 - state.actors["e1"].current_hp
        e2_taken = 1e9 - state.actors["e2"].current_hp
        assert math.isclose(e1_taken + e2_taken, expected_counter, rel_tol=1e-6), (
            f"反击总伤：手算 {expected_counter:.1f} vs 实际 {e1_taken + e2_taken:.1f}"
        )

    def test_act_now_pulls_all_enemies(self):
        """act_now_targets：施放后敌方全体立即行动（怪行动日志早于白厄下一动）."""
        eng, _track = _engine()
        state = eng.run()
        log = state.log
        edict_idx = next(i for i, l in enumerate(log) if "弑魂焚诏" in l)
        # 施放后紧跟的应是两只怪的行动（被拉到当前时刻）
        following = log[edict_idx + 1: edict_idx + 5]
        monster_moves = [l for l in following if "撕咬" in l]
        assert len(monster_moves) == 2, f"应有 2 怪立即行动：{following}"
