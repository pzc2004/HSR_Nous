"""banish 队友离场/回场（白厄境界"其他队友离场且无法行动"）端到端.

链：变身 → 队友 banish（AV 冻结、选择器排除、actor_exit）→ 倒计时期间队友不行动
→ 退出 → 队友回场（actor_enter、解冻、后续正常行动）。
"""
from __future__ import annotations

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ULT_AFTER_ACTION, ScriptedPolicy
from hsr_nous.sim.state import StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _actor(aid, name, spd, atk=2000):
    return Actor(actor_id=aid, name=name, level=80,
                 stats=StatBlock(atk=atk, spd=spd, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy():
    return Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _basic(aid="basic"):
    return Action(action_id=aid, name="普攻", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)


def _engine(av=260.0):
    k_ult = Action(action_id="khaslana_ult", name="永劫燔世", action_type="ultimate",
                   target_type="single", ult_cost_resource="fire_seed", ult_cost_amount=12)
    k_basic = Action(action_id="khaslana_basic", name="创生•血棘渡亡", action_type="basic",
                     target_type="single", damage_type="physical", scaling=[{"atk": 3.0}],
                     toughness_dmg=20, energy_gain=0)
    actors = [_actor("1408", "白厄", 150), _actor("ally", "队友A", 120), _dummy()]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={
        "1408": [_basic(), k_ult, k_basic], "ally": [_basic()]},
        policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
        initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    eng.register_state_config("1408", StateConfig(
        state="khaslana",
        replaces_actions={"basic": "khaslana_basic"},
        locked_actions=["skill"],
        exit_conditions=[{"trigger": "on_action_count", "value": 2}],
        banish_allies_on_enter=True,
    ), entry_action_id="khaslana_ult")
    eng.state.actors["1408"].resources["fire_seed"] = 12.0
    return eng


class TestBanish:
    def test_banish_and_return_lifecycle(self):
        eng = _engine()
        state = eng.run()
        log = state.log

        # 1. 离场/回场日志成对出现
        assert any("队友A 离场（境界）" in l for l in log), f"无离场日志：{log[:8]}"
        assert any("队友A 回场" in l for l in log), f"无回场日志：{log[:8]}"
        # 2. banish 期间（@83.3 队友原行动点）队友无行动；回场后（@166.6）恢复行动
        ally_actions = [l for l in log if "队友A 对" in l]
        assert ally_actions, "队友回场后应有行动"
        first_ally_av = float(ally_actions[0].split(":")[0].replace("AV", ""))
        assert first_ally_av > 100.0, f"队友首次行动应在回场后（>{100}）：{ally_actions[0]}"
        # 3. 终局队友已回场（非 banished）
        assert state.actors["ally"].banished is False
        assert state.actors["ally"].alive

    def test_banished_ally_not_targeted(self):
        """banish 期间敌方目标选择排除离场队友（怪只能打白厄）."""
        boss_atk = Action(action_id="boss_atk", name="重击", action_type="basic",
                          target_type="single", damage_type="physical",
                          scaling=[{"atk": 1.0}], toughness_dmg=10)
        eng = _engine()
        eng.actions_by_actor["e1"] = [boss_atk]
        state = eng.run()
        # 怪 @100 行动时队友正被 banish → 目标只能是白厄
        boss_hits = [l for l in state.log if "重击" in l]
        assert boss_hits and all("对 白厄" in l for l in boss_hits), (
            f"banish 期间怪不应选中队友：{boss_hits}"
        )

    def test_state_owner_death_returns_allies(self):
        """形态主死亡：形态随死亡解除（exit_state reason=death）——境界 banish 的队友回场（防孤儿化）."""
        eng = _engine()
        khas = eng.state.actors["1408"]
        ally = eng.state.actors["ally"]
        # 白厄变身（火种 12 特殊充能）→ 队友 banish 离场
        assert eng._try_ultimate(khas, ULT_AFTER_ACTION), "变身技应施放成功"
        assert khas.state_config is not None and ally.banished, "前置：形态已入、队友已离场"
        # 形态中主死亡 → 真死路径应解除形态、队友 unfreeze 回场
        khas.current_hp = 0.0
        eng._check_death(khas, "e1")
        assert not khas.alive
        assert khas.state_config is None, "死亡后形态必须解除"
        assert ally.banished is False, "队友必须回场（不得永久 banish 孤儿化）"
        assert any("队友A 回场" in l for l in eng.state.log), f"缺回场日志：{eng.state.log[-6:]}"
        assert any("退出形态" in l for l in eng.state.log), f"缺退出形态日志：{eng.state.log[-6:]}"
        # 回场后调度器解冻：队友重新出现在行动条预览里
        assert "ally" in dict(eng.scheduler.preview()), "队友 AV 必须解冻（可再行动）"
