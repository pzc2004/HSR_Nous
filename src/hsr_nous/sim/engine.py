"""战斗引擎 v0.2：直伤闭环 + 击破 + 敌人行动 + 波次切换.

回合四段（决策卡 #16 / mechanics 03 §3.6）：
    回合开始(A 类结算：DOT 跳伤) → 行动 → 行动后窗口(终结技/插入合法点) → 回合结束(B 类结算：modifier tick)
击破（mechanics 04）：削韧闸 → 击破伤害 → 属性击破效果（DOT/控制/延后）→ 敌方回合开始韧性恢复（冻结顺延）。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import ULT_AFTER_ACTION, ULT_BEFORE_ACTION, ScriptedPolicy, legal_action_set
from hsr_nous.sim.resources import cast_cost, ultimate_available
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN, Scheduler
from hsr_nous.sim.state import ActorState, BattleState, Modifier, StateConfig
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

    @staticmethod
    def _key_of(s: ActorState, key: str) -> float:
        """选择器 key 解析："stats.X"→面板属性，"current_hp"→当前生命，"hp_pct"→生命百分比."""
        if key == "current_hp":
            return s.current_hp
        if key == "hp_pct":
            return s.current_hp / max(s.actor.stats.hp, 1e-6)
        if key.startswith("stats."):
            return float(getattr(s.actor.stats, key[6:], 0.0) or 0.0)
        return 0.0

    def _apply_selector(self, sel, candidates: List[ActorState], actor_state: ActorState,
                        ctx: Dict[str, Any], engine: "CombatEngine") -> Optional[ActorState]:
        """单个选择器求值；对齐 sim_schema/policy.py TargetRule 声明的集合."""
        rng = engine.pipeline.rng

        def pick_random() -> ActorState:
            # 期望模式不掷骰（B22）：退化为第一个候选，保持确定性
            if engine.pipeline.mode == MODE_ROLL and rng is not None:
                return rng.choice(candidates)
            return candidates[0]

        if isinstance(sel, str):
            if sel in ("primary_target", "enemy_single", "all_enemies", "all_allies"):
                return candidates[0]  # 全体语义由 target_type=aoe/ally_aoe 表达，这里定主目标
            if sel == "self":
                return next((s for s in candidates if s.actor.actor_id == actor_state.actor.actor_id),
                            actor_state)
            if sel == "lowest_hp":
                return min(candidates, key=lambda s: s.current_hp)
            if sel == "lowest_hp_ally":
                return min(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_hp":
                return max(candidates, key=lambda s: s.current_hp)
            if sel == "lowest_hp_pct":
                return min(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_hp_pct":
                return max(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_atk":
                return max(candidates, key=lambda s: self._key_of(s, "stats.atk"))
            if sel == "highest_spd":
                return max(candidates, key=lambda s: self._key_of(s, "stats.spd"))
            if sel == "lowest_spd":
                return min(candidates, key=lambda s: self._key_of(s, "stats.spd"))
            if sel == "broken":
                return next((s for s in candidates if s.broken), candidates[0])
            if sel == "highest_break":
                return max(candidates, key=lambda s: self._key_of(s, "stats.break_effect"))
            if sel == "random":
                return pick_random()
            return candidates[0]
        if isinstance(sel, dict):
            t = sel.get("type")
            if t == "min":
                return min(candidates, key=lambda s: self._key_of(s, sel.get("key", "current_hp")))
            if t == "max":
                return max(candidates, key=lambda s: self._key_of(s, sel.get("key", "current_hp")))
            if t == "random":
                return pick_random()
            if t == "has_modifier":
                mid = sel.get("modifier_id", "")
                return next((s for s in candidates if mid in s.modifiers), candidates[0])
            if t in ("filter", "first"):
                cond = sel.get("condition", "")
                expr = self.expr.try_compile(cond) if cond else None
                matched = [s for s in candidates if expr is None
                           or self.expr.evaluate(expr, {**ctx, **self._target_ctx(s)}, rng)]
                return matched[0] if matched else candidates[0]
        return candidates[0]

    @staticmethod
    def _target_ctx(s: ActorState) -> Dict[str, Any]:
        """filter/first 条件里可用的目标侧上下文."""
        return {
            "target_hp": s.current_hp,
            "target_hp_pct": s.current_hp / max(s.actor.stats.hp, 1e-6),
            "target_broken": s.broken,
        }

    def select_target(self, actor_state: ActorState, action_type: str, candidates: List[ActorState], engine: "CombatEngine") -> Optional[ActorState]:
        if not candidates:
            return None
        ctx = self._context(actor_state, engine)
        ctx["action_type"] = action_type
        for rule in self.policy.target_rules:
            if rule.condition_expr is not None and not self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                continue
            picked = self._apply_selector(rule.selector, candidates, actor_state, ctx, engine)
            if picked is not None:
                return picked
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
        self.state_configs_by_actor: Dict[str, List[StateConfig]] = {}
        self._initial_modifiers: Dict[str, List[Modifier]] = {}  # from_compiled 注入，_init_state 时挂载
        self._banished_by_state: Dict[str, List[str]] = {}  # 形态境界离场的队友名单（exit 时回场）
        self.state_entry_actions: Dict[str, tuple[str, StateConfig]] = {}

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
        engine._initial_modifiers = compiled.modifiers_by_actor
        for actor_id, (cfg, entry_id) in compiled.state_configs_by_actor.items():
            engine.register_state_config(actor_id, cfg, entry_action_id=entry_id)
        return engine

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """公开初始化：构建全状态与调度器（测试预置 modifier 前先调）."""
        if self.scheduler is None:
            self._init_state()

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
        # 编译期归并的初始 modifier（遗器套装等）挂载
        for actor_id, mods in self._initial_modifiers.items():
            st = self.state.actors.get(actor_id)
            if st is not None:
                for m in mods:
                    self._apply_modifier(st, m)
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

    def _apply_modifier(self, target: ActorState, mod: Modifier, *, apply_chance: float = 1.0) -> bool:
        """施加 modifier：效果命中判定（debuff 系）→ singleton_group → stack_mode 语义.

        返回是否成功挂上（抵抗则失败）.
        """
        # 效果命中判定（§4.7：debuff/dot/control 且 chance<1 时掷/判）
        if mod.modifier_type in ("debuff", "dot", "control") and apply_chance < 1.0:
            src_state = self.state.actors.get(mod.source_id)
            se = self.pipeline.effective_stats(src_state) if src_state else {}
            te = self.pipeline.effective_stats(target)
            chance = self.pipeline.hit_chance(se, te, apply_chance)
            if not self.pipeline.roll_debuff_apply(chance):
                self.bus.emit("on_resist", {"modifier_id": mod.modifier_id, "target": target.actor.actor_id, "chance": chance}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 抵抗了 {mod.name}（命中率 {chance:.0%}）")
                return False

        # singleton_group：同组先摘旧
        if mod.singleton_group:
            for old in list(target.modifiers.values()):
                if old.singleton_group == mod.singleton_group and old.modifier_id != mod.modifier_id:
                    self._remove_modifier(target, old.modifier_id, "replace")

        existing = target.modifiers.get(mod.modifier_id)
        if existing is not None:
            if mod.stack_mode == "replace":
                self._remove_modifier(target, mod.modifier_id, "replace")
                target.modifiers[mod.modifier_id] = mod
            elif mod.stack_mode == "set":
                existing.stacks = mod.stacks_value
                existing.duration = max(existing.duration, mod.duration)
            else:  # refresh / independent（v0.4 均视同 refresh 时长）
                existing.stacks = min(existing.stacks + mod.stacks, existing.max_stack)
                existing.duration = max(existing.duration, mod.duration)
        else:
            target.modifiers[mod.modifier_id] = mod
        self.bus.emit("after_apply_modifier", {"modifier_id": mod.modifier_id, "target": target.actor.actor_id, "source": mod.source_id}, self.state)
        return True

    def dispel(self, target: ActorState, max_count: int = 1, source_id: str = "") -> int:
        """驱散（解除敌方增益）：LIFO 摘 dispellable 的 buff 系."""
        removed = 0
        for mod in reversed(list(target.modifiers.values())):
            if removed >= max_count:
                break
            if mod.modifier_type in ("buff",) and mod.dispellable:
                self._remove_modifier(target, mod.modifier_id, "dispel")
                removed += 1
        if removed:
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 被驱散 {removed} 个增益")
        return removed

    def purify(self, target: ActorState, max_count: int = 1, source_id: str = "") -> int:
        """净化（解除我方负面）：LIFO 摘 dispellable 的 debuff/dot/control 系."""
        removed = 0
        for mod in reversed(list(target.modifiers.values())):
            if removed >= max_count:
                break
            if mod.modifier_type in ("debuff", "dot", "control") and mod.dispellable:
                self._remove_modifier(target, mod.modifier_id, "purify")
                removed += 1
        if removed:
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 被净化 {removed} 个负面")
        return removed

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
        # toughness_scope 闸（默认 own_element：攻击属性 ∈ 目标有效弱点才可削；植入弱点计入）
        can_reduce = action.damage_type in self.pipeline.effective_weakness(target)
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
    # 形态机（#20 糖化：形态 = 标记 modifier + 合法性注入）
    # ------------------------------------------------------------------

    def register_state_config(self, actor_id: str, config: StateConfig, *, entry_action_id: str = "") -> None:
        """登记角色的形态配置；entry_action_id 非空 = 该 action 施放即进入形态."""
        self.state_configs_by_actor.setdefault(actor_id, []).append(config)
        if entry_action_id:
            self.state_entry_actions[entry_action_id] = (actor_id, config)

    def enter_state(self, actor_state: ActorState, config: StateConfig, duration: int = 0) -> None:
        """进入形态：挂标记（singleton_group=actor_state 互斥）+ 合法性注入生效."""
        marker = Modifier(
            modifier_id=config.marker_id(), name=config.state, modifier_type="buff",
            duration=duration, dispellable=False, singleton_group="actor_state",
            stat_effects=dict(config.stat_effects),  # 形态内面板（白厄"攻击力提高X%"族）
        )
        self._apply_modifier(actor_state, marker)
        actor_state.state_config = config
        # 计数器清零：上次形态（若曾进入）的残留不影响本轮倒计时
        actor_state.resources[f"_state_actions_{config.state}"] = 0.0
        # 境界：其他队友离场且无法行动（banish 族；退出时回场）
        if config.banish_allies_on_enter:
            for s in self.state.actors.values():
                if s is actor_state or self._is_monster(s.actor) or not s.alive or s.banished:
                    continue
                s.banished = True
                self.scheduler.freeze(s.actor.actor_id)
                self._banished_by_state.setdefault(actor_state.actor.actor_id, []).append(s.actor.actor_id)
                self.bus.emit("actor_exit", {"actor": s.actor.actor_id, "reason": "banish"}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {s.actor.name} 离场（境界）")
        self.bus.emit("on_state_change", {"actor": actor_state.actor.actor_id, "to_state": config.state}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 进入形态 {config.state}")

    def exit_state(self, actor_state: ActorState, reason: str = "exit") -> None:
        """退出形态：摘标记（on_exit 全路径经 remove 单漏斗）+ 境界植入件清理."""
        if actor_state.state_config is None:
            return
        old = actor_state.state_config.state
        # 境界植入件随形态解除（exit_remove_modifiers 清单，对全体敌人）
        for mid in actor_state.state_config.exit_remove_modifiers:
            for e in self._enemies_alive():
                self._remove_modifier(e, mid, "state_exit")
        # 离场队友回场（banish 解除 + AV 解冻）
        for aid in self._banished_by_state.pop(actor_state.actor.actor_id, []):
            s = self.state.actors.get(aid)
            if s is not None and s.banished:
                s.banished = False
                self.scheduler.unfreeze(aid)
                self.bus.emit("actor_enter", {"actor": aid, "reason": "unbanish"}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {s.actor.name} 回场")
        self._remove_modifier(actor_state, actor_state.state_config.marker_id(), reason)
        actor_state.state_config = None
        self.bus.emit("on_state_change", {"actor": actor_state.actor.actor_id, "from_state": old}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 退出形态 {old}")

    def _legal_with_state(self, actor_state: ActorState, legal: List[Action]) -> List[Action]:
        """合法性注入：replaces/locked 生效 + 增强行动仅形态下可用."""
        cfg = actor_state.state_config
        enhanced_ids = {
            v for c in self.state_configs_by_actor.get(actor_state.actor.actor_id, [])
            for v in c.replaces_actions.values()
        } | {
            c.final_action_id for c in self.state_configs_by_actor.get(actor_state.actor.actor_id, [])
            if c.final_action_id
        }
        out: List[Action] = []
        for act in legal:
            if cfg is not None:
                if act.action_type in cfg.locked_actions:
                    continue
                if act.action_type in cfg.replaces_actions and act.action_id != cfg.replaces_actions[act.action_type]:
                    continue  # 原型被替换
                out.append(act)
            else:
                if act.action_id in enhanced_ids:
                    continue
                out.append(act)
        return out

    def end_current_turn(self, actor_state: ActorState) -> None:
        """结束当前回合（#16）：保留已发生、丢弃未行动；先 +1 延长再正常末结算.

        净效果：已有增益时长不变，本回合新挂增益白赚 +1（"锁 buff"数学原理）。
        """
        for mod in actor_state.modifiers.values():
            if mod.duration > 0:
                mod.duration += 1
        self._tick_modifiers(actor_state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 的回合被结束")

    def _check_exit_conditions(self, actor_state: ActorState) -> None:
        """形态退出条件检查（行动后）：on_action_count / on_resource_depleted."""
        cfg = actor_state.state_config
        if cfg is None:
            return
        for cond in cfg.exit_conditions:
            trigger = cond.get("trigger")
            if trigger == "on_action_count":
                count = actor_state.resources.get(f"_state_actions_{cfg.state}", 0.0)
                if count >= float(cond.get("value", 1)):
                    self.exit_state(actor_state, "exit_condition")
                    return
            elif trigger == "on_resource_depleted":
                rid = cond.get("value", "")
                if actor_state.resources.get(rid, 0.0) <= 0.0:
                    self.exit_state(actor_state, "exit_condition")
                    return

    def _first_enemy(self) -> Optional[ActorState]:
        alive = self._enemies_alive()
        return alive[0] if alive else None

    def _pick_ally_target(self) -> Optional[ActorState]:
        """敌方选目标：掷骰模式按嘲讽值加权，期望模式取最高嘲讽."""
        allies = [s for s in self.state.actors.values() if not self._is_monster(s.actor) and s.alive and not s.banished]
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

    def _resolve_targets(self, actor_state: ActorState, action: Action) -> tuple[Optional[ActorState], List[ActorState]]:
        """按 target_type 解析 (主目标, 目标集)（站位=编队序；blast 相邻=存活列表索引 ±1）.

        主目标选择：policy target_rules（compiled_runtime）优先，缺省=第一个存活敌人.
        """
        actor = actor_state.actor
        tt = action.target_type
        if self._is_monster(actor):
            allies = [s for s in self.state.actors.values() if not self._is_monster(s.actor) and s.alive and not s.banished]
            if tt == "aoe":
                return (allies[0] if allies else None), allies
            if tt == "bounce":
                picked = (self.pipeline.rng.choice(allies)
                          if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None and allies
                          else (allies[0] if allies else None))
                return picked, ([picked] if picked is not None else [])
            t = self._pick_ally_target()
            return t, ([t] if t is not None else [])
        if tt == "self":
            return actor_state, [actor_state]
        if tt in ("ally_single", "ally_aoe"):
            allies = [s for s in self.state.actors.values() if not self._is_monster(s.actor) and s.alive and not s.banished]
            if tt == "ally_aoe":
                return (allies[0] if allies else None), allies
            picked = None
            if self.compiled_runtime is not None:
                picked = self.compiled_runtime.select_target(actor_state, tt, allies, self)
            primary = picked if picked is not None else actor_state
            return primary, [primary]
        enemies = self._enemies_alive()
        if not enemies:
            return None, []
        if tt == "aoe":
            return enemies[0], enemies
        if tt == "bounce":
            # 弹射每段随机（roll）/ 期望模式全中主目标（与 optimizer 单体口径一致）
            picked = (self.pipeline.rng.choice(enemies)
                      if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None
                      else enemies[0])
            return picked, [picked]
        primary = enemies[0]
        if self.compiled_runtime is not None:
            picked = self.compiled_runtime.select_target(actor_state, tt, enemies, self)
            if picked is not None:
                primary = picked
        if tt == "blast":
            idx = enemies.index(primary)
            return primary, enemies[max(0, idx - 1): idx + 2]
        return primary, [primary]

    def _execute_action(self, actor_state: ActorState, action: Action) -> None:
        actor = actor_state.actor
        primary, targets = self._resolve_targets(actor_state, action)
        if not targets:
            return

        self.skill_points += action.skill_point_gain - action.skill_point_cost
        # None=按类型默认回能；显式 0=该技能不回能（如形态内强化普攻）
        gain = action.energy_gain if action.energy_gain is not None else (
            20 if action.action_type == "basic" else 30 if action.action_type == "skill" else 0
        )
        if gain:
            self.pipeline.gain_energy(actor_state, gain)
        self._apply_action_side_effects(actor_state, action)

        if action.damage_type and action.scaling:
            # 多段（#19 instances）：SP/能量行动级结算一次，伤害/削韧逐段；段间目标死亡则后续段落空（鞭尸损失）
            for seg in range(max(1, action.instances)):
                if seg > 0 and action.target_type == "bounce":
                    # 弹射每段独立重选目标（可重复命中；全灭即终止）
                    primary, targets = self._resolve_targets(actor_state, action)
                    if not targets:
                        break
                for target in targets:
                    if not target.alive:
                        continue
                    eff = action
                    if action.target_type == "blast" and target is not primary:
                        # 扩散副目标：副倍率 + 副削韧（None 时副削韧=主的一半，04_break_system 基线 10/20/10）
                        eff = replace(
                            action,
                            scaling=action.scaling_blast if action.scaling_blast is not None else action.scaling,
                            toughness_dmg=action.toughness_dmg_blast
                            if action.toughness_dmg_blast is not None else action.toughness_dmg // 2,
                        )
                    if action.split == "even":
                        # 分配轴：总伤按存活目标数均分，逐目标各自跑公式（05_effects §split）
                        alive_n = max(1, sum(1 for t in targets if t.alive))
                        eff = replace(
                            eff,
                            scaling=[{k: v / alive_n for k, v in s.items()} for s in eff.scaling],
                        )
                    result = self.pipeline.deal_damage(eff, actor_state, target, target_broken=target.broken)
                    # 伤害入口 waterfall（before_take_damage）：免死 cancel / 分摊·减伤改写 amount 的总入口
                    wp = self.bus.waterfall("before_take_damage", {
                        "amount": result.value, "damage_type": eff.damage_type,
                        "source": actor.actor_id, "target": target.actor.actor_id,
                        "action_type": eff.action_type, "is_critical": result.node.get("isCrit", False),
                    }, self.state)
                    if wp.get("cancel"):
                        continue  # 伤害被取消（免死类 hook 侧已自理回血/反击）
                    final_amount = float(wp.get("amount", result.value))
                    target.current_hp -= final_amount
                    self.state.total_damage += final_amount
                    self.state.damage_by_actor[actor.actor_id] += final_amount
                    self.bus.emit("after_being_hit", {"amount": final_amount, "damage_type": eff.damage_type, "source": actor.actor_id, "target": target.actor.actor_id, "is_critical": result.node.get("isCrit", False), "seg_index": seg}, self.state)
                    self._log(actor, eff, target, final_amount, result.node.get("isCrit", False))
                    if self._is_monster(target.actor):
                        self._apply_toughness_damage(actor, eff, target)
                    self._check_death(target, actor.actor_id)
        else:
            # 无伤害行动（self buff/铺场类）也留行动日志——可观察性是机制对轴的前提
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {actor.name} 使用 {action.name}"
            )

    def _apply_action_side_effects(self, actor_state: ActorState, action: Action) -> None:
        """行动的副作用通道（resource_gain / act_now / apply_modifiers）——
        普通施放与变身 entry 特判共用（entry 不经 _execute_action 的伤害段）."""
        # 自定义资源获得（火种/毁伤/新蕊族）
        for rid, amt in action.resource_gain.items():
            actor_state.resources[rid] = actor_state.resources.get(rid, 0.0) + amt
        # 立即行动（白厄 140809"使敌方全体立即行动"族）
        if action.act_now_targets == "all_enemies":
            for e in self._enemies_alive():
                self.scheduler.act_now(e.actor)
        # 施放后挂 modifier（dict 声明→物化；target: self（默认）/ all_enemies（植入 debuff 族））
        for spec in action.apply_modifiers:
            tgt = [actor_state] if spec.get("target", "self") == "self" else self._enemies_alive()
            for t in tgt:
                self._apply_modifier(t, Modifier(
                    modifier_id=spec["modifier_id"],
                    name=spec.get("name", spec["modifier_id"]),
                    modifier_type=spec.get("modifier_type", "buff"),
                    duration=int(spec.get("duration", 0)),
                    stacks=int(spec.get("stacks", 1)),
                    max_stack=int(spec.get("max_stack", 99)),
                    dispellable=bool(spec.get("dispellable", True)),
                    stat_effects={k: float(v) for k, v in (spec.get("stat_effects") or {}).items()},
                    weakness_add=[str(w) for w in spec.get("weakness_add") or []],
                ))

    def _try_ultimate(self, actor_state: ActorState, timing: str) -> bool:
        if self.policy.ult_timing != timing:
            return False
        actions = self.actions_by_actor.get(actor_state.actor.actor_id, [])
        ult = next((a for a in actions if a.action_type == "ultimate"), None)
        if not ultimate_available(actor_state, ult):
            return False
        cost = cast_cost(ult, actor_state.actor.stats.max_energy)
        # 形态入口技：施放即变身（进入形态 + 结束本回合 + 授予倒计时回合）
        entry = self.state_entry_actions.get(ult.action_id)
        if entry is not None and actor_state.state_config is entry[1]:
            return False  # 已在该形态：变身技不重复触发（防能量回充连锁变身）
        if ult.ult_cost_resource:
            # 特殊充能：扣资源不扣能量（白厄火种/遐蝶新蕊族）
            actor_state.resources[ult.ult_cost_resource] = (
                actor_state.resources.get(ult.ult_cost_resource, 0.0) - ult.ult_cost_amount
            )
        else:
            self.pipeline.consume_energy(actor_state, cost)
        if entry is not None:
            _owner, config = entry
            self.enter_state(actor_state, config)
            self._apply_action_side_effects(actor_state, ult)  # 入口技副作用（资源获得/挂身件）
            self.end_current_turn(actor_state)
            n_turns = int(config.exit_conditions[0].get("value", 1)) if config.exit_conditions else 1
            # 倒计时回合按固定速度占 AV 流逝（白厄"速度固定为基础速度的 60%"）
            self.scheduler.grant_countdown(
                actor_state.actor.actor_id, n_turns,
                spd=actor_state.actor.stats.spd * config.countdown_spd_ratio,
            )
        else:
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

    def trigger_action(self, actor_state: ActorState, action: Action, *, tag: str = "insert") -> None:
        """插入式行动（反击/追加攻击/代放族）：立即结算，不占回合、不调度、不改计数.

        与回合内行动的区别：不走 legal/政策、不影响形态计数器；事件带 insert 标记
        （hook 监听时可区分主动行动与插入行动，防"反击触发反击"无限递归）。
        """
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor_state.actor.name} 插入发动 {action.name}"
        )
        self._execute_action(actor_state, action)
        self.bus.emit("on_action", {
            "actor": actor_state.actor.actor_id, "action_type": action.action_type,
            "insert": True, "tag": tag,
        }, self.state)

    def _final_action_if_last(self, actor_state: ActorState, is_countdown: bool) -> Optional[Action]:
        """倒计时最后一动返回 final_action_id 指定的行动，否则 None."""
        cfg = actor_state.state_config
        if not is_countdown or cfg is None or not cfg.final_action_id:
            return None
        n = float(cfg.exit_conditions[0].get("value", 1)) if cfg.exit_conditions else 1.0
        count = actor_state.resources.get(f"_state_actions_{cfg.state}", 0.0)
        if count < n - 1:
            return None
        return next(
            (a for a in self.actions_by_actor.get(actor_state.actor.actor_id, [])
             if a.action_id == cfg.final_action_id),
            None,
        )

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

        # 阶段 2 · 行动（快照回合开始时的形态：本回合内才变身的，当动不计入倒计时）
        had_state_at_turn_start = actor_state.state_config is not None
        if self._is_monster(actor):
            self._enemy_turn(actor_state)
        else:
            self._try_ultimate(actor_state, ULT_BEFORE_ACTION)
            forced = self._final_action_if_last(actor_state, is_countdown)
            if forced is not None:
                # 倒计时最后一动：强制最后一击（"最后的额外回合开始时立即发动"）
                self._execute_action(actor_state, forced)
                self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": forced.action_type}, self.state)
                if had_state_at_turn_start and actor_state.state_config is not None:
                    actor_state.resources[f"_state_actions_{actor_state.state_config.state}"] = (
                        actor_state.resources.get(f"_state_actions_{actor_state.state_config.state}", 0.0) + 1
                    )
                    self._check_exit_conditions(actor_state)
            else:
                legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []), self.skill_points)
                legal = self._legal_with_state(actor_state, legal)
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
                if had_state_at_turn_start and actor_state.state_config is not None:
                    actor_state.resources[f"_state_actions_{actor_state.state_config.state}"] = (
                        actor_state.resources.get(f"_state_actions_{actor_state.state_config.state}", 0.0) + 1
                    )
                    self._check_exit_conditions(actor_state)

        # 阶段 4 · 回合结束（B 类结算：modifier tick；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_end", {"actor": actor.actor_id}, self.state)
        self._tick_modifiers(actor_state)
        self.state.turn_count += 1

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> BattleState:
        if self.scheduler is None:
            self._init_state()
        assert self.scheduler is not None

        for _ in range(MAX_TURNS_SAFETY):
            self._advance_wave_if_needed()
            if self._should_terminate():
                break
            actor, kind, now = self.scheduler.next_actor()
            # fixed_av 截断看"本回合时刻"：超过上限的回合不执行（含端点：恰好在上限的回合照跑）
            term = self.encounter.termination
            if (term.mode == "fixed_av" and now > term.max_action_value
                    and not self._has_next_wave()):
                break
            self.state.clock = now
            self.state.cycle_av = now
            actor_state = self.state.actors[actor.actor_id]
            if not actor_state.alive:
                continue
            self._run_turn(actor_state, kind)

        return self.state
