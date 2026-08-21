"""战斗引擎 v0.2：直伤闭环 + 击破 + 敌人行动 + 波次切换.

回合四段（决策卡 #16 / mechanics 03 §3.6）：
    回合开始(A 类结算：DOT 跳伤) → 行动 → 行动后窗口(终结技/插入合法点) → 回合结束(B 类结算：modifier tick)
击破（mechanics 04）：削韧闸 → 击破伤害 → 属性击破效果（DOT/控制/延后）→ 敌方回合开始韧性恢复（冻结顺延）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import ULT_AFTER_ACTION, ULT_BEFORE_ACTION, ScriptedPolicy, legal_action_set
from hsr_nous.sim.resources import cast_cost, ultimate_available
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN, Scheduler
from hsr_nous.sim.state import ActorState, BattleState, Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter

MAX_TURNS_SAFETY = 200  # 兜底防死循环


class CompiledPolicyRuntime:
    """CompiledPolicy 的运行时执行：按优先级降序评估条件，首个命中者生效."""

    def __init__(self, compiled_policy, expr_compiler=None) -> None:
        from hsr_nous.sim.compile.expr_compiler import ExprCompiler
        self.policy = compiled_policy
        self.expr = expr_compiler or ExprCompiler()

    def _context(self, actor_state: ActorState, engine: "CombatEngine") -> Dict[str, Any]:
        st = actor_state.actor.stats
        ctx: Dict[str, Any] = {
            "energy": actor_state.current_energy,
            "max_energy": st.max_energy,
            "skill_points": engine.skill_points,
            "hp": actor_state.current_hp,
            "max_hp": st.hp,
        }
        ctx.update(self.policy.parameters)
        return ctx

    def select_action_type(self, actor_state: ActorState, engine: "CombatEngine") -> str:
        ctx = self._context(actor_state, engine)
        for rule in self.policy.action_rules:
            if rule.condition_expr is None or self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                return rule.action
        return "basic"

    def select_target(self, actor_state: ActorState, action_type: str, candidates: List[ActorState], engine: "CombatEngine") -> Optional[ActorState]:
        if not candidates:
            return None
        ctx = self._context(actor_state, engine)
        ctx["action_type"] = action_type
        for rule in self.policy.target_rules:
            if rule.condition_expr is not None and not self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                continue
            sel = rule.selector
            if isinstance(sel, str):
                if sel == "primary_target" or sel == "enemy_single":
                    return candidates[0]
                if sel == "all_enemies":
                    return candidates[0]
                if sel == "lowest_hp_ally":
                    allies = [s for s in candidates]
                    return min(allies, key=lambda s: s.current_hp / max(s.actor.stats.hp, 1e-6))
            elif isinstance(sel, dict):
                t = sel.get("type")
                if t == "min" and sel.get("key") == "stats.hp":
                    return min(candidates, key=lambda s: s.current_hp)
                if t == "priority":
                    return candidates[0]
        return candidates[0]


class CombatEngine:
    """回合制战斗模拟器 v0.2."""

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
        wave_enemies: Optional[Dict[int, List[Actor]]] = None,
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
        self.wave_enemies = wave_enemies or {}
        self.current_wave = 0  # 0 = encounter.actors 初始阵容；1..N = waves
        self.compiled_runtime: Optional[CompiledPolicyRuntime] = None

    @classmethod
    def from_compiled(
        cls,
        compiled,
        *,
        mode: str = MODE_ROLL,
        seed: Optional[int] = None,
        initial_sp: int = 3,
        initial_energy_ratio: float = 0.5,
    ) -> "CombatEngine":
        """从 CompiledEncounter 直接构建引擎（DSL 模板 → 战斗的正式入口）."""
        engine = cls(
            compiled.to_encounter(),
            actions_by_actor=compiled.actions_by_actor,
            policy=ScriptedPolicy(),
            mode=mode,
            seed=seed,
            initial_sp=initial_sp,
            initial_energy_ratio=initial_energy_ratio,
            wave_enemies={i: list(w) for i, w in compiled.stage.waves.items()},
        )
        engine.compiled_runtime = CompiledPolicyRuntime(compiled.policy)
        engine.policy.ult_timing = compiled.policy.ult_timing
        return engine

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _init_state(self) -> None:
        for actor in self.encounter.actors:
            toughness = actor.stats.max_toughness if self._is_monster(actor) else 0.0
            self.state.actors[actor.actor_id] = ActorState(
                actor=actor,
                current_hp=actor.stats.hp,
                current_energy=actor.stats.max_energy * self.initial_energy_ratio,
                alive=True,
                toughness=toughness,
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

    def _has_next_wave(self) -> bool:
        return (self.current_wave + 1) in self.wave_enemies

    def _should_terminate(self) -> bool:
        term = self.encounter.termination
        if not self._enemies_alive() and not self._has_next_wave():
            return True
        if term.mode == "fixed_av" and self.state.cycle_av >= term.max_action_value and not self._has_next_wave():
            return True
        if term.mode == "kill_target" and not self._enemies_alive() and not self._has_next_wave():
            return True
        return False

    # ------------------------------------------------------------------
    # 波次切换
    # ------------------------------------------------------------------

    def _advance_wave_if_needed(self) -> None:
        """当前波敌人全灭且还有下一波：新敌人登场."""
        if self._enemies_alive() or not self._has_next_wave():
            return
        assert self.scheduler is not None
        self.current_wave += 1
        newcomers = self.wave_enemies[self.current_wave]
        for actor in newcomers:
            toughness = actor.stats.max_toughness if self._is_monster(actor) else 0.0
            self.state.actors[actor.actor_id] = ActorState(
                actor=actor, current_hp=actor.stats.hp,
                current_energy=actor.stats.max_energy * self.initial_energy_ratio,
                alive=True, toughness=toughness,
            )
            self.state.damage_by_actor.setdefault(actor.actor_id, 0.0)
            self.scheduler.add_actor(actor)
            self.bus.emit("actor_enter", {"actor": actor.actor_id, "wave_index": self.current_wave}, self.state)
        self.bus.emit("on_wave_start", {"wave_index": self.current_wave}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: —— 第 {self.current_wave + 1} 波 ——")

    # ------------------------------------------------------------------
    # modifier 基础层
    # ------------------------------------------------------------------

    def _apply_modifier(self, target: ActorState, mod: Modifier) -> None:
        existing = target.modifiers.get(mod.modifier_id)
        if existing is not None:
            existing.duration = max(existing.duration, mod.duration)  # refresh 时长
            existing.stacks = min(existing.stacks + mod.stacks, 99)
        else:
            target.modifiers[mod.modifier_id] = mod
        self.bus.emit("after_apply_modifier", {"modifier_id": mod.modifier_id, "target": target.actor.actor_id, "source": mod.source_id}, self.state)

    def _remove_modifier(self, target: ActorState, modifier_id: str, reason: str = "expire") -> None:
        if target.modifiers.pop(modifier_id, None) is not None:
            self.bus.emit("after_remove_modifier", {"modifier_id": modifier_id, "reason": reason, "target": target.actor.actor_id}, self.state)

    def _tick_dots(self, actor_state: ActorState) -> None:
        """A 类结算：回合开始 DOT 跳伤."""
        for mod in list(actor_state.modifiers.values()):
            if mod.modifier_type != "dot":
                continue
            if mod.dot_element == "physical":
                result = self.pipeline.bleed_tick(actor_state, mod)
            else:
                result = self.pipeline.dot_tick(actor_state, mod)
            self.state.total_damage += result.value
            self.state.damage_by_actor[mod.source_id] = self.state.damage_by_actor.get(mod.source_id, 0.0) + result.value
            self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 受到 {mod.name} 持续伤害 {result.value:,.0f}")
            self.bus.emit("on_dot_retrigger", {"modifier_id": mod.modifier_id, "target": actor_state.actor.actor_id}, self.state)
            self._check_death(actor_state, mod.source_id)

    def _tick_modifiers(self, actor_state: ActorState) -> None:
        """B 类结算：回合结束 modifier 时长 -1，到期移除."""
        for mod in list(actor_state.modifiers.values()):
            if mod.duration <= 0:
                continue
            mod.duration -= 1
            if mod.duration == 0:
                self._remove_modifier(actor_state, mod.modifier_id, "expire")

    def _check_death(self, target: ActorState, source_id: str = "") -> None:
        if target.current_hp <= 0 and target.alive:
            target.alive = False
            self.bus.emit("actor_exit", {"actor": target.actor.actor_id, "reason": "death"}, self.state)
            if source_id:
                self.bus.emit("on_kill", {"source": source_id, "target": target.actor.actor_id}, self.state)

    # ------------------------------------------------------------------
    # 击破
    # ------------------------------------------------------------------

    def _apply_toughness_damage(self, source: Actor, action: Action, target: ActorState) -> None:
        if action.toughness_dmg <= 0 or target.broken:
            return
        # toughness_scope 闸（默认 own_element：攻击属性 ∈ 目标弱点才可削）
        can_reduce = action.damage_type in target.actor.stats.weakness
        result = self.pipeline.toughness_damage(target, action.toughness_dmg, action.damage_type or "", can_reduce)
        if result.value > 0:
            self.bus.emit("on_toughness_damage", {"amount": result.value, "source": source.actor_id, "target": target.actor.actor_id, "bar_index": 0}, self.state)
        if target.toughness <= 0 and not target.broken:
            self._trigger_break(source, action, target)

    def _trigger_break(self, source: Actor, action: Action, target: ActorState) -> None:
        """击破：击破伤害 + 属性击破效果 + 通用推条 25%."""
        element = action.damage_type or "physical"
        target.broken = True
        self.bus.emit("on_break", {"source": source.actor_id, "target": target.actor.actor_id, "element": element, "bar_index": 0}, self.state)

        dmg = self.pipeline.break_damage(source, target, element)
        self.state.total_damage += dmg.value
        self.state.damage_by_actor[source.actor_id] += dmg.value
        self.state.log.append(f"AV{self.state.clock:.1f}: {source.name} 触发击破，对 {target.actor.name} 造成 {dmg.value:,.0f} 击破伤害")
        self._check_death(target, source.actor_id)

        eff = self.pipeline.break_effect_of(element)
        src_atk = source.stats.atk
        if eff["control"] == "freeze":
            self._apply_modifier(target, Modifier(
                modifier_id="BRK_FREEZE", name="冻结", modifier_type="control", debuff_kind="control",
                duration=1, source_id=source.actor_id, control_kind="freeze"))
        elif eff["control"] in ("entangle", "imprison"):
            self._apply_modifier(target, Modifier(
                modifier_id=f"BRK_{eff['control'].upper()}", name=eff["control"], modifier_type="control",
                debuff_kind="control", duration=1, source_id=source.actor_id, control_kind=eff["control"]))
        if eff["dot_ratio"] is not None and eff["dot_ratio"] > 0:
            self._apply_modifier(target, Modifier(
                modifier_id=f"BRK_DOT_{element}", name=f"{element}持续伤害", modifier_type="dot", debuff_kind="dot",
                duration=2, source_id=source.actor_id,
                dot_element=element, dot_ratio=eff["dot_ratio"], dot_source_atk=src_atk))
        elif element == "physical":
            self._apply_modifier(target, Modifier(
                modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot", debuff_kind="dot",
                duration=2, source_id=source.actor_id,
                dot_element="physical", dot_ratio=1.0, dot_source_atk=src_atk))
        # 通用推条 25%（量子/虚数额外延后）
        assert self.scheduler is not None
        self.scheduler.delay_action(target.actor, eff["delay"])

    # ------------------------------------------------------------------
    # 行动执行
    # ------------------------------------------------------------------

    def _first_enemy(self) -> Optional[ActorState]:
        alive = self._enemies_alive()
        return alive[0] if alive else None

    def _pick_ally_target(self) -> Optional[ActorState]:
        """敌方选目标：掷骰模式按嘲讽值加权，期望模式取最高嘲讽."""
        allies = [s for s in self.state.actors.values() if not self._is_monster(s.actor) and s.alive]
        if not allies:
            return None
        if self.pipeline.mode == MODE_ROLL and self.pipeline.rng:
            total = sum(s.actor.stats.taunt for s in allies)
            roll = self.pipeline.rng.random() * total
            acc = 0.0
            for s in allies:
                acc += s.actor.stats.taunt
                if roll <= acc:
                    return s
            return allies[-1]
        return max(allies, key=lambda s: s.actor.stats.taunt)

    def _execute_action(self, actor_state: ActorState, action: Action) -> None:
        actor = actor_state.actor
        target = self._first_enemy() if not self._is_monster(actor) else self._pick_ally_target()
        if target is None:
            return

        self.skill_points += action.skill_point_gain - action.skill_point_cost
        gain = action.energy_gain or (20 if action.action_type == "basic" else 30 if action.action_type == "skill" else 0)
        if gain:
            self.pipeline.gain_energy(actor_state, gain)

        if action.damage_type and action.scaling:
            result = self.pipeline.deal_damage(action, actor, target.actor, target_broken=target.broken)
            target.current_hp -= result.value
            self.state.total_damage += result.value
            self.state.damage_by_actor[actor.actor_id] += result.value
            self.bus.emit("after_being_hit", {"amount": result.value, "damage_type": action.damage_type, "source": actor.actor_id, "target": target.actor.actor_id, "is_critical": result.node.get("isCrit", False)}, self.state)
            self._log(actor, action, target, result.value, result.node.get("isCrit", False))
            if self._is_monster(target.actor):
                self._apply_toughness_damage(actor, action, target)
            self._check_death(target, actor.actor_id)

    def _try_ultimate(self, actor_state: ActorState, timing: str) -> bool:
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
    # 敌方回合
    # ------------------------------------------------------------------

    def _enemy_turn(self, actor_state: ActorState) -> None:
        actor = actor_state.actor
        frozen = any(m.control_kind == "freeze" for m in actor_state.modifiers.values())

        # 冻结：真正跳过一次行动（不恢复韧性；解冻后下次行动提前 50%）
        if frozen:
            for mod_id in [m.modifier_id for m in actor_state.modifiers.values() if m.control_kind == "freeze"]:
                self._remove_modifier(actor_state, mod_id, "expire")
            assert self.scheduler is not None
            self.scheduler.advance_action(actor, 0.5)
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 被冻结，跳过行动")
            return

        # 敌方回合开始：恢复全部韧性、解除击破状态
        if actor_state.broken:
            actor_state.broken = False
            actor_state.toughness = actor.stats.max_toughness
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 韧性恢复")

        actions = self.actions_by_actor.get(actor.actor_id, [])
        if not actions:
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 行动（占位）")
            return
        self._execute_action(actor_state, actions[0])
        self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": actions[0].action_type}, self.state)

    # ------------------------------------------------------------------
    # 回合四段
    # ------------------------------------------------------------------

    def _run_turn(self, actor_state: ActorState, kind: str) -> None:
        actor = actor_state.actor
        is_countdown = kind == EXTRA_COUNTDOWN

        # 阶段 1 · 回合开始（A 类结算：DOT 跳伤；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_start", {"actor": actor.actor_id}, self.state)
        self._tick_dots(actor_state)

        # 阶段 2 · 行动
        if self._is_monster(actor):
            self._enemy_turn(actor_state)
        else:
            self._try_ultimate(actor_state, ULT_BEFORE_ACTION)
            legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []), self.skill_points)
            if not legal:
                self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                return
            if self.compiled_runtime is not None:
                want = self.compiled_runtime.select_action_type(actor_state, self)
                action = next((a for a in legal if a.action_type == want), legal[0])
            else:
                action = self.policy.select_action(legal)
            self._execute_action(actor_state, action)
            self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": action.action_type}, self.state)
            # 阶段 3 · 行动后窗口
            self._try_ultimate(actor_state, ULT_AFTER_ACTION)

        # 阶段 4 · 回合结束（B 类结算：modifier tick；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_end", {"actor": actor.actor_id}, self.state)
        self._tick_modifiers(actor_state)
        self.state.turn_count += 1

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> BattleState:
        self._init_state()
        assert self.scheduler is not None

        for _ in range(MAX_TURNS_SAFETY):
            self._advance_wave_if_needed()
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
