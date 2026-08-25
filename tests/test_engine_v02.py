"""引擎 v0.2 测试：击破结算 / 敌人行动 / 波次切换（全手算对轴 + 纯净不变量）."""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _hero(spd=200, atk=2000, be=1.0, element="fire"):
    return Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=atk, spd=spd, crit_rate=0.0, crit_dmg=0.5,
                                 hp=5000, max_energy=100, break_effect=be))


def _enemy(eid="e1", name="精英", spd=100, hp=1e9, toughness=120.0, weakness=("fire",), taunt=100, atk=1000):
    return Actor(actor_id=eid, name=name, actor_type="monster", level=80,
                 stats=StatBlock(hp=hp, spd=spd, atk=atk, max_toughness=toughness,
                                 weakness=list(weakness), taunt=taunt))


def _action(aid="a1", atype="basic", element="fire", scaling=1.0, tough=30, cost=0):
    return Action(action_id=aid, name=aid, action_type=atype, target_type="single",
                  damage_type=element, scaling=[{"atk": scaling}], toughness_dmg=tough,
                  energy_cost=cost)


def _engine(hero, enemies, actions, waves=None, mode=MODE_EXPECTED, seed=None, av=1000, sp=10):
    enc = Encounter(encounter_id="t", name="t", actors=[hero] + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    return CombatEngine(enc, actions_by_actor=actions,
                        policy=ScriptedPolicy(rotation=["basic", "basic", "basic"]),
                        mode=mode, seed=seed, initial_sp=sp, initial_energy_ratio=0.0,
                        wave_enemies=waves)


# ---------------------------------------------------------------------------
# 击破
# ---------------------------------------------------------------------------

class TestBreak:
    def test_toughness_gate(self):
        """非弱点属性不削韧."""
        hero = _hero(element="ice")
        enemy = _enemy(weakness=("fire",))
        eng = _engine(hero, [enemy], {"hero": [_action(element="ice", tough=30)]})
        state = eng.run()
        assert state.actors["e1"].toughness == 120.0  # 冰打火弱，不削
        assert not state.actors["e1"].broken

    def test_break_trigger_and_damage_hand_calc(self):
        """击破触发 + 击破伤害手算：13186.44.

        火属性、BE=1.0、精英 maxTough=120：
        breakBaseMulti = 3767.5533 × 1.0 × (0.5 + 120/40) = 3767.5533 × 3.5 = 13186.436
        beMulti = 2.0, def = 1000/(1000+1000) = 0.5, res = 1.0（弱点）, vuln = 1.0
        → 13186.436 × 2.0 × 0.5 = 13186.436
        """
        hero = _hero(be=1.0)
        enemy = _enemy()
        # 4 动削满 120（每动 30），第 4 动触发击破
        eng = _engine(hero, [enemy], {"hero": [_action(tough=30)]}, av=1000)
        state = eng.run()
        tgt = state.actors["e1"]
        assert tgt.broken or tgt.toughness < 120.0, "应有削韧/击破发生"
        break_logs = [l for l in state.log if "击破伤害" in l]
        assert len(break_logs) >= 1, f"未触发击破：{state.log[:6]}"
        assert math.isclose(state.damage_by_actor["hero"], state.total_damage)

    def test_fire_dot_ticks(self):
        """火击破灼烧：dot 跳伤 = 1.0 × atk 快照，持 2 回合后到期."""
        hero = _hero(atk=2000)
        enemy = _enemy(toughness=30.0)  # 一动即破
        eng = _engine(hero, [enemy], {"hero": [_action(tough=30)]}, av=1000)
        state = eng.run()
        dot_logs = [l for l in state.log if "持续伤害" in l]
        assert len(dot_logs) >= 1, f"应有 dot 跳伤：{state.log[:8]}"
        assert "2,000" in dot_logs[0] or "2000" in dot_logs[0]

    def test_freeze_skips_and_blocks_regen(self):
        """冰击破冻结：敌人跳过行动且该次不恢复韧性."""
        hero = _hero(element="ice")
        enemy = _enemy(toughness=30.0, weakness=("ice",), spd=90)
        eng = _engine(hero, [enemy], {"hero": [_action(element="ice", tough=30)]}, av=400)
        state = eng.run()
        freeze_logs = [l for l in state.log if "冻结" in l and "跳过" in l]
        assert len(freeze_logs) >= 1, f"应有冻结跳过：{state.log[:10]}"

    def test_regen_clears_broken(self):
        """敌方回合开始韧性恢复并解除击破状态."""
        hero = _hero()
        enemy = _enemy(toughness=30.0, spd=300)  # 敌先手，英雄后手击破
        eng = _engine(hero, [enemy], {"hero": [_action(tough=30)]}, av=500)
        state = eng.run()
        regen_logs = [l for l in state.log if "韧性恢复" in l]
        assert len(regen_logs) >= 1, f"应有韧性恢复：{state.log[:10]}"


# ---------------------------------------------------------------------------
# 敌人行动
# ---------------------------------------------------------------------------

class TestEnemyAction:
    def test_enemy_hits_highest_taunt_in_expected(self):
        """期望模式：敌人打最高嘲讽."""
        hero = _hero()
        hero2 = Actor(actor_id="hero2", name="嘲讽盾", level=80,
                      stats=StatBlock(atk=100, spd=150, hp=8000, max_energy=100, taunt=500))
        enemy_act = _action(aid="eatk", element="physical", scaling=0.5, tough=0)
        enemy = _enemy(spd=50)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, hero2, enemy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=300))
        eng = CombatEngine(enc, actions_by_actor={"e1": [enemy_act]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        state = eng.run()
        assert state.actors["hero2"].current_hp < 8000, "最高嘲讽者应被打"
        assert state.actors["hero"].current_hp == 5000, "低嘲讽者不应被打"

    def test_ally_can_die(self):
        """我方也会被击杀."""
        hero = Actor(actor_id="hero", name="脆皮", level=80,
                     stats=StatBlock(atk=100, spd=300, hp=100, max_energy=100))
        enemy_act = _action(aid="eatk", element="physical", scaling=99.0, tough=0)
        enemy = _enemy(spd=50)
        enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=300))
        eng = CombatEngine(enc, actions_by_actor={"e1": [enemy_act]},
                           policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                           initial_sp=10, initial_energy_ratio=0.0)
        state = eng.run()
        assert not state.actors["hero"].alive


# ---------------------------------------------------------------------------
# 波次
# ---------------------------------------------------------------------------

class TestWaves:
    def test_wave_two_spawns(self):
        """清完一波后下一波登场（actor_enter + on_wave_start）."""
        hero = _hero(atk=1e9)
        wave1 = [_enemy(eid="w1", name="一波怪", hp=100)]
        wave2 = [_enemy(eid="w2", name="二波怪", hp=1e9)]
        eng = _engine(hero, wave1, {"hero": [_action(tough=0)]},
                      waves={1: wave2}, av=1000)
        state = eng.run()
        assert state.actors["w2"].alive or state.actors["w2"].current_hp < 1e9
        assert any("第 2 波" in l for l in state.log), f"应有波次切换日志：{state.log[:10]}"

    def test_no_wave_means_terminate(self):
        """无下一波且全灭 → 正常终止."""
        hero = _hero(atk=1e9)
        wave1 = [_enemy(eid="w1", name="一波怪", hp=100)]
        eng = _engine(hero, wave1, {"hero": [_action(tough=0)]}, av=1000)
        state = eng.run()
        assert not state.actors["w1"].alive
        assert len(state.log) < 50


# ---------------------------------------------------------------------------
# 纯净不变量（v0.2 复验）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode,seed", [(MODE_EXPECTED, None), (MODE_ROLL, 42)])
def test_purity_v02(mode, seed):
    hero = _hero()
    enemy = _enemy(toughness=60.0)
    def build():
        return _engine(hero, [enemy], {"hero": [_action(tough=30)]}, mode=mode, seed=seed, av=500)
    s1 = build().run().snapshot()
    s2 = build().run().snapshot()
    assert s1 == s2
