"""免死（140805"受到致命攻击不死，回血并立即发动最后一击"）端到端.

伤害入口 before_take_damage waterfall：hook 致死判定 → cancel + 回血 + trigger 反击。
v1 假设：每次变身一次免死（次数语义待游戏内实测，B19 记账）。
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _phainon():
    return Actor(actor_id="1408", name="白厄", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _boss():
    return Actor(actor_id="boss", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _actions():
    basic = Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                   damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)
    boss_atk = Action(action_id="boss_atk", name="灭世一击", action_type="basic",
                      target_type="single", damage_type="physical",
                      scaling=[{"atk": 1.0}], toughness_dmg=10)
    final = Action(action_id="final_strike", name="最后一击", action_type="ultimate",
                   target_type="aoe", damage_type="physical",
                   scaling=[{"atk": 4.8}], split="even", energy_gain=0)
    return basic, boss_atk, final


def _engine(av=100.0):
    basic, boss_atk, final = _actions()
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _boss()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"1408": [basic], "boss": [boss_atk]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()

    # 140805 免死机制 hook：每变身一次（v1 假设次数）
    used = {"flag": False}

    def death_immunity(et, payload, ctx):
        st = eng.state.actors["1408"]
        if payload.get("target") != "1408" or used["flag"]:
            return None
        if float(payload.get("amount", 0)) < st.current_hp:
            return None
        used["flag"] = True
        # 回复生命上限 25%，立即发动最后一击（剩余倒计时 0 → 满倍率，非变身场景）
        st.current_hp = st.actor.stats.hp * 0.25
        eng.trigger_action(st, final, tag="counter")
        return {"cancel": True}

    eng.bus.subscribe_waterfall("before_take_damage", death_immunity)
    return eng, used


class TestDeathImmunity:
    def test_lethal_hit_survives_with_counter(self):
        eng, used = _engine()
        state = eng.run()
        st = state.actors["1408"]
        # 1. 免死触发： alive + hp = 生命上限 25% = 750
        assert used["flag"] is True
        assert st.alive
        assert math.isclose(st.current_hp, 750.0, rel_tol=1e-6)
        # 2. 立即反击发生（最后一击均分 1 怪 = 全倍率 4.8）
        assert any("插入发动 最后一击" in l for l in state.log)
        # 3. boss 掉血 = T1 普攻 1350 + 反击（均分 1 怪 = 全倍率 4.8）6480 = 7830
        assert math.isclose(1e9 - state.actors["boss"].current_hp, 1350.0 + 6480.0, rel_tol=1e-4)
        # 4. 致死伤害未入账（cancel）
        assert all("灭世一击" not in l or "造成" not in l for l in state.log), \
            "被 cancel 的伤害不应有伤害日志"

    def test_second_lethal_hit_kills(self):
        """次数耗尽后第二次致死攻击正常死亡（v1 一次假设）."""
        eng, used = _engine(av=210.0)  # 怪两动（@100、@200 均在 av 内）
        state = eng.run()
        st = state.actors["1408"]
        assert used["flag"] is True
        assert not st.alive, "第二次致死攻击应正常死亡"
