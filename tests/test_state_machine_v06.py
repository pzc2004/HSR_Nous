"""v0.6 状态机测试：白厄变身全链（火种→变身→锁 buff→倒计时回合→最后一击→回场）.

决策卡 #16 验收用例的引擎落地版。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _phainon(atk=2000):
    return Actor(actor_id="phainon", name="白厄", level=80,
                 stats=StatBlock(atk=atk, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy():
    return Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))


def _actions():
    return [
        Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
               damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10),
        Action(action_id="khaslana_ult", name="永劫燔世，其将背负", action_type="ultimate",
               target_type="single", damage_type="fire", energy_cost=40),
        Action(action_id="khaslana_basic", name="创生•血棘渡亡", action_type="basic",
               target_type="single", damage_type="fire", scaling=[{"atk": 3.0}],
               toughness_dmg=20, energy_gain=0),
    ]


def _engine():
    enc = Encounter(encounter_id="t", name="t", actors=[_phainon(), _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=140))
    eng = CombatEngine(enc, actions_by_actor={"phainon": _actions()},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    eng.register_state_config("phainon", StateConfig(
        state="khaslana",
        replaces_actions={"basic": "khaslana_basic"},
        locked_actions=["skill"],
        exit_conditions=[{"trigger": "on_action_count", "value": 2}],
    ), entry_action_id="khaslana_ult")
    return eng


class TestPhainonChain:
    def test_full_chain(self):
        eng = _engine()
        state = eng.run()
        log = state.log

        # 1. 变身与回场都发生了
        assert any("进入形态 khaslana" in l for l in log), f"未变身：{log[:8]}"
        assert any("退出形态 khaslana" in l for l in log), f"未回场：{log[:8]}"
        # 2. 结束当前回合（锁 buff 原语）发生了
        assert any("回合被结束" in l for l in log), "end_current_turn 未执行"
        # 3. 倒计时回合：恰好两次血棘渡亡
        k_hits = [l for l in log if "创生•血棘渡亡" in l]
        assert len(k_hits) == 2, f"应有 2 次倒计时强化攻击：{k_hits}"
        # 4. 伤害对轴：2 普攻(1350) + 2 血棘渡亡(4050) = 10800
        assert math.isclose(state.total_damage, 10800.0, rel_tol=1e-6), (
            f"手算 10800 vs 实际 {state.total_damage}"
        )
        # 5. 回场后形态已退出
        assert state.actors["phainon"].state_config is None
        # 6. 回场后恢复普攻（日志里 普攻 在 弑神一击 之后仍有出现或形态标记清除）
        assert state.actors["phainon"].modifiers.get("STATE_khaslana") is None

    def test_locked_action_excluded_in_state(self):
        """形态下 locked_actions=['skill'] 被排除（合法性注入）."""
        eng = _engine()
        state = eng.run()
        # 全程不应出现 skill 施放
        assert not any("战技" in l and "使用" in l for l in state.log)

    def test_enhanced_only_in_state(self):
        """血棘渡亡只在形态内出现（合法性注入：常态不可见）."""
        eng = _engine()
        state = eng.run()
        k_idx = [i for i, l in enumerate(state.log) if "创生•血棘渡亡" in l]
        exit_idx = [i for i, l in enumerate(state.log) if "退出形态" in l]
        assert k_idx and exit_idx and max(k_idx) < min(exit_idx), "血棘渡亡必须全部发生在退出形态之前"
