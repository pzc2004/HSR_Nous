"""战斗模拟器：纯仿真核心，只依赖 sim_schema."""

from hsr_nous.sim.avtree import AVTree
from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import ScriptedPolicy, legal_action_set
from hsr_nous.sim.scheduler import Scheduler
from hsr_nous.sim.state import ActorState, BattleState

__all__ = [
    "AVTree",
    "CombatEngine",
    "EventBus",
    "SettlementPipeline",
    "ScriptedPolicy",
    "Scheduler",
    "ActorState",
    "BattleState",
    "legal_action_set",
    "MODE_EXPECTED",
    "MODE_ROLL",
]
