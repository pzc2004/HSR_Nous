"""战斗引擎 v0.1：直伤闭环主循环（回合四段驱动）.

回合四段（决策卡 #16 / mechanics 03 §3.6）：
    回合开始(A 类结算) → 行动 → 行动后窗口(终结技/插入行动合法点) → 回合结束(B 类结算)
额外回合两类型：正常回合类（吃回合事件）/ 倒计时类（不广播，自身回合点存在）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import ULT_AFTER_ACTION, ULT_BEFORE_ACTION, ScriptedPolicy, legal_action_set
from hsr_nous.sim.resources import cast_cost, ultimate_available
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN, EXTRA_NORMAL, Scheduler
from hsr_nous.sim.state import ActorState, BattleState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter

MAX_TURNS_SAFETY = 200  # 兜底防死循环


class CombatEngine:
    """回合制战斗模拟器 v0.1（直伤闭环）."""

    MONSTER_TYPES = {"monster", "enemy"}

    def __init__(
        self,
        encounter: Encounter,
        actions_by_actor: Optional[Dict[str, List[Action]]] = None,
        policy: Optional[ScriptedPolicy] = None,
        mode: str = MODE_ROLL,
        seed: Optional[int] = None,
        initial_sp: int = 3,
        initial_energy_ratio: float = 0.5,
    ) -> None:
        self.encounter = encounter
        self.actions_by_actor = actions_by_actor or {}
        self.policy = policy or ScriptedPolicy()
        self.pipeline = SettlementPipeline(mode=mode, seed=seed)
        self.bus = EventBus()
        self.state = BattleState()
        self.scheduler: Optional[Scheduler] = None
        self.initial_sp = initial_sp
        self.skill_points = initial_sp
        self.initial_energy_ratio = initial_energy_ratio

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_state(self) -> None:
        for actor in self.encounter.actors:
            self.state.actors[actor.actor_id] = ActorState(
                actor=actor,
                current_hp=actor.stats.hp,
                current_energy=actor.stats.max_energy * self.initial_energy_ratio,
                alive=True,
            )
            self.state.damage_by_actor[actor.actor_id] = 0.0
        self.scheduler = Scheduler(list(self.encounter.actors))
        self.skill_points = self.initial_sp
        self.bus.emit("on_battle_start", {"encounter": self.encounter.encounter_id}, self.state)

    # ------------------------------------------------------------------
    # 终止判定
    # ------------------------------------------------------------------

    def _is_monster(self, actor: Actor) -> bool:
        return actor.actor_type in self.MONSTER_TYPES

    def _enemies_alive(self) -> List[ActorState]:
        return [s for s in self.state.actors.values() if self._is_monster(s.actor) and s.alive]

    def _should_terminate(self) -> bool:
        term = self.encounter.termination
        if term.mode == "fixed_av" and self.state.cycle_av >= term.max_action_value:
            return True
        if term.mode == "kill_target" and not self._enemies_alive():
            return True
        if not self._enemies_alive():
            return True
        return False

    # ------------------------------------------------------------------
    # 行动执行
    # ------------------------------------------------------------------

    def _first_enemy(self) -> Optional[ActorState]:
        alive = self._enemies_alive()
        return alive[0] if alive else None

    def _first_ally(self, actor: Actor) -> Optional[ActorState]:
        for s in self.state.actors.values():
            if not self._is_monster(s.actor) and s.alive:
                return s
        return None

    def _execute_action(self, actor_state: ActorState, action: Action) -> None:
        """执行一个 action 的伤害/效果结算（v0.1：deal_damage 单体主目标）."""
        actor = actor_state.actor
        target = self._first_enemy()
        if target is None:
            return

        # 战技点收支
        self.skill_points += action.skill_point_gain - action.skill_point_cost

        # 能量：行动回能（默认 basic 20 / skill 30 / 其他按 energy_gain）
        gain = action.energy_gain or (20 if action.action_type == "basic" else 30 if action.action_type == "skill" else 0)
        if gain:
            self.pipeline.gain_energy(actor_state, gain)

        # 直伤结算（v0.1：单体主目标；多目标后置）
        if action.damage_type and action.scaling:
            result = self.pipeline.deal_damage(action, actor, target.actor)
            target.current_hp -= result.value
            self.state.total_damage += result.value
            self.state.damage_by_actor[actor.actor_id] += result.value
            # 事件发射（发射点生成式：状态变更即事实）
            self.bus.emit("on_toughness_damage", {"amount": action.toughness_dmg, "source": actor.actor_id, "target": target.actor.actor_id}, self.state)
            self.bus.emit("after_being_hit", {"amount": result.value, "damage_type": action.damage_type, "source": actor.actor_id, "target": target.actor.actor_id, "is_critical": result.node.get("isCrit", False)}, self.state)
            self._log(actor, action, target, result.value, result.node.get("isCrit", False))
            if target.current_hp <= 0 and target.alive:
                target.alive = False
                self.bus.emit("actor_exit", {"actor": target.actor.actor_id, "reason": "death"}, self.state)
                self.bus.emit("on_kill", {"source": actor.actor_id, "target": target.actor.actor_id}, self.state)

    def _try_ultimate(self, actor_state: ActorState, timing: str) -> bool:
        """尝试插入终结技：可大则开（耗能→结算→发射 on_ultimate）."""
        if self.policy.ult_timing != timing:
            return False
        actions = self.actions_by_actor.get(actor_state.actor.actor_id, [])
        ult = next((a for a in actions if a.action_type == "ultimate"), None)
        if not ultimate_available(actor_state, ult):
            return False
        cost = cast_cost(ult, actor_state.actor.stats.max_energy)
        self.pipeline.consume_energy(actor_state, cost)
        self._execute_action(actor_state, ult)
        self.bus.emit("on_ultimate", {"source": actor_state.actor.actor_id, "action": ult.action_id}, self.state)
        return True

    def _log(self, actor: Actor, action: Action, target: ActorState, damage: float, is_crit: bool) -> None:
        crit_mark = "（暴击）" if is_crit else ""
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor.name} 对 {target.actor.name} "
            f"使用 {action.name} 造成 {damage:,.0f} 伤害{crit_mark}"
        )

    # ------------------------------------------------------------------
    # 回合四段
    # ------------------------------------------------------------------

    def _run_turn(self, actor_state: ActorState, kind: str) -> None:
        actor = actor_state.actor
        is_countdown = kind == EXTRA_COUNTDOWN

        # 阶段 1 · 回合开始（A 类结算：倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_start", {"actor": actor.actor_id}, self.state)

        # 阶段 2 · 行动（敌方 v0.1：有 action 也走管线，无则占位跳过）
        if self._is_monster(actor):
            actions = self.actions_by_actor.get(actor.actor_id, [])
            if not actions:
                self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 行动（占位）")
                return
            action = actions[0]
        else:
            # 行动准备期：可插入终结技（ULT_BEFORE_ACTION）
            self._try_ultimate(actor_state, ULT_BEFORE_ACTION)
            legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []), self.skill_points)
            if not legal:
                self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                return
            action = self.policy.select_action(legal)

        self._execute_action(actor_state, action)
        self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": action.action_type}, self.state)

        # 阶段 3 · 行动后窗口（合法插入点：此时开大吃"本回合"效果）
        if not self._is_monster(actor):
            self._try_ultimate(actor_state, ULT_AFTER_ACTION)

        # 阶段 4 · 回合结束（B 类结算：倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_end", {"actor": actor.actor_id}, self.state)
        self.state.turn_count += 1

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> BattleState:
        """运行战斗仿真（v0.1 直伤闭环）."""
        self._init_state()
        assert self.scheduler is not None

        for _ in range(MAX_TURNS_SAFETY):
            if self._should_terminate():
                break
            actor, kind, now = self.scheduler.next_actor()
            self.state.clock = now
            self.state.cycle_av = now
            actor_state = self.state.actors[actor.actor_id]
            if not actor_state.alive:
                continue
            self._run_turn(actor_state, kind)

        return self.state
