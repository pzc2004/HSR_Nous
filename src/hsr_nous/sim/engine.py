"""战斗引擎：直伤闭环 + 击破 + 敌人行动 + 波次切换；护盾/生存（锁血·月茧·复活）/光环/轮次/模板 hooks 已落地.

回合四段（决策卡 #16 / mechanics 03 §3.6）：
    回合开始(A 类结算：DOT 跳伤) → 行动 → 行动后窗口(终结技/插入合法点) → 回合结束(B 类结算：modifier tick)
击破（mechanics 04）：削韧闸 → 击破伤害 → 属性击破效果（DOT/控制/延后）→ 敌方回合开始韧性恢复（冻结顺延）。
"""
from __future__ import annotations

import warnings
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Dict, List, Optional

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.hooks import HookRuntime, _HookSelfNS  # noqa: F401  # _HookSelfNS 为 re-export（tests 直引本模块）
from hsr_nous.sim.modifiers import ModifierBook
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import (  # CompiledPolicyRuntime 本体已迁 policy_api.py，此处为 re-export（tests 直引本模块）
    ULT_AFTER_ACTION, ULT_BEFORE_ACTION, CompiledPolicyRuntime, ScriptedPolicy, legal_action_set,
)
from hsr_nous.sim.resources import ult_threshold_of, ultimate_available
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN, EXTRA_NORMAL, Scheduler
from hsr_nous.sim.state import MOON_COCOON_ID, ActorState, BattleState, Modifier, StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter

MAX_TURNS_SAFETY = 200  # 兜底防死循环


class CombatEngine:
    """回合制战斗模拟器（机制面见模块 docstring；输入只认 sim_schema）.

    hooks 运行时（模板 hooks 订阅/条件求值/effect 分发）已迁 `sim/hooks.py`（`HookRuntime`），
    本类 `_subscribe_compiled_hooks`/`_hook_ctx`/`_hook_target_states`/`_run_hook_effect` 为薄委托；
    modifier 生命周期（施加/tick 走字/驱散净化/spec 物化）与护盾（物化/并行吸收）已迁
    `sim/modifiers.py`（`ModifierBook`），本类同名方法为薄委托；
    编译策略运行时（action_rules/target_rules 求值 + 目标选择器）已迁 `sim/policy_api.py`
    （`CompiledPolicyRuntime`，本模块同名 import 为 re-export，tests 直引口径不变）。
    """

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
        expr: Optional[Any] = None,
    ) -> None:
        self.encounter = encounter
        self.actions_by_actor = actions_by_actor or {}
        self.policy = policy or ScriptedPolicy()
        # 表达式编译器：一台引擎一份（共享 _cache）——build 编译期创建经 from_compiled 注入，
        # hook condition / policy runtime / pipeline scoped 加成三处共用
        self._expr = expr or ExprCompiler()
        self.pipeline = SettlementPipeline(mode=mode, seed=seed, expr=self._expr)
        # 光环提供者注入：全队 scope=team 光环（排除目标自己已持有的，防重复计）
        self.pipeline.set_aura_provider(lambda st: [
            m for other in self.state.actors.values()
            if other is not st and not self._is_monster(other.actor) and other.alive and not other.banished
            for m in other.modifiers.values() if m.effect_scope == "team"
        ])
        self.bus = EventBus()
        self.state = BattleState()
        self.scheduler: Optional[Scheduler] = None
        self.initial_sp = initial_sp
        self.state.skill_points = initial_sp
        self.initial_energy_ratio = initial_energy_ratio
        self.wave_enemies = wave_enemies or {}
        self.current_wave = 0  # 0 = encounter.actors 初始阵容；1..N = waves
        self.compiled_runtime: Optional[CompiledPolicyRuntime] = None
        self.state_configs_by_actor: Dict[str, List[StateConfig]] = {}
        self._initial_modifiers: Dict[str, List[Modifier]] = {}  # from_compiled 注入，_init_state 时挂载
        self._banished_by_state: Dict[str, List[str]] = {}  # 形态境界离场的队友名单（exit 时回场）
        self._compiled_hooks: List[Any] = []  # 模板 hooks 块的编译产物（from_compiled 注入）
        self._hooks = HookRuntime(self)  # hooks 运行时本体在 sim/hooks.py（同名方法为薄委托）
        self._modifiers = ModifierBook(self)  # modifier/护盾运行时本体在 sim/modifiers.py（同名方法为薄委托）
        self._resource_ids: Dict[str, List[str]] = {}  # 模板 custom_resources 声明键（setup 初始化缺省 0）
        self.state_entry_actions: Dict[str, tuple[str, StateConfig]] = {}
        # 月茧"同时死亡"批处理的瞬时事件号（结算临时量，不进 snapshot；同种子递增值一致，B16 不破）：
        # _cocoon_event_counter 单调递增发号；_cocoon_event_seq 当前结算中的事件号（0=不在事件内，
        # 嵌套事件退出时还原外层）；_cocoon_saved_event 本战斗月茧救人发生时的事件号
        self._cocoon_event_counter = 0
        self._cocoon_event_seq = 0
        self._cocoon_saved_event = 0

    @property
    def skill_points(self) -> int:
        """战技点读取别名：本体在 `state.skill_points`（B16：SP 是战斗状态，进 snapshot）."""
        return self.state.skill_points

    def _sp_max(self) -> int:
        """战技点上限（mechanics 06 §6.1）：默认 rulebook constants.sp_max_default（5）；
        state.sp_max_override > 0 时被改写（花火天赋"上限提高至 7"族挂点——实例未到，预留）."""
        return int(self.state.sp_max_override or self.pipeline.sp_max_default())

    def _adjust_skill_points(self, delta: int) -> None:
        """SP 增减唯一通道：clamp 到 [0, _sp_max()]（mechanics 06 §6.1：上限默认 5、下限 0）."""
        self.state.skill_points = max(0, min(self._sp_max(), self.state.skill_points + int(delta)))

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
            expr=compiled.expr,
        )
        engine.compiled_runtime = CompiledPolicyRuntime(compiled.policy, expr_compiler=engine._expr)
        engine.policy.ult_timing = compiled.policy.ult_timing
        engine._initial_modifiers = compiled.modifiers_by_actor
        engine._compiled_hooks = list(compiled.hooks)
        engine._resource_ids = dict(compiled.resource_ids_by_actor)
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

    def _spawn_actor(self, actor: Actor) -> ActorState:
        """参战单位布场：ActorState 创建（敌人初始满韧、按 initial_energy_ratio 布能）+ 伤害账本登记."""
        toughness = actor.stats.max_toughness if self._is_monster(actor) else 0.0
        st = ActorState(
            actor=actor,
            current_hp=actor.stats.hp,
            current_energy=actor.stats.max_energy * self.initial_energy_ratio,
            alive=True,
            toughness=toughness,
        )
        self.state.actors[actor.actor_id] = st
        self.state.damage_by_actor.setdefault(actor.actor_id, 0.0)
        return st

    def _init_state(self) -> None:
        for actor in self.encounter.actors:
            self._spawn_actor(actor)
        self.scheduler = Scheduler(list(self.encounter.actors))
        self.state.skill_points = self.initial_sp
        # 轮次系统：预算终点初始化（encounter.cycle 为 None 时保持 0 占位、不参与 tick——见 _tick_cycle）
        if self.encounter.cycle is not None:
            self.state.cycle_end_clock = float(self.encounter.cycle.first_cycle_av)
        # 编译期归并的初始 modifier（遗器套装等）挂载
        for actor_id, mods in self._initial_modifiers.items():
            st = self.state.actors.get(actor_id)
            if st is not None:
                for m in mods:
                    self._apply_modifier(st, m)
        # 模板声明资源初始化缺省 0（表达式 res_* 恒有定义的前提）
        for actor_id, rids in self._resource_ids.items():
            st = self.state.actors.get(actor_id)
            if st is not None:
                for rid in rids:
                    st.resources.setdefault(rid, 0.0)
        # 模板 hooks 订阅（必须在 on_battle_start 之前挂上——开局类 hook 才收得到）
        self._subscribe_compiled_hooks()
        self.bus.emit("on_battle_start", {"encounter": self.encounter.encounter_id}, self.state)

    # ------------------------------------------------------------------
    # 终止判定
    # ------------------------------------------------------------------

    def _is_monster(self, actor: Actor) -> bool:
        return actor.actor_type in self.MONSTER_TYPES

    def _enemies_alive(self) -> List[ActorState]:
        return [s for s in self.state.actors.values() if self._is_monster(s.actor) and s.alive]

    def _allies_alive(self) -> List[ActorState]:
        """存活且在场（未 banish）的我方单位——选择器/敌方选目标/光环辐射的统一口径."""
        return [s for s in self.state.actors.values()
                if not self._is_monster(s.actor) and s.alive and not s.banished]

    def _has_next_wave(self) -> bool:
        return (self.current_wave + 1) in self.wave_enemies

    def _should_terminate(self) -> bool:
        term = self.encounter.termination
        if not self._enemies_alive() and not self._has_next_wave():
            return True
        if term.mode == "fixed_av" and self.state.clock >= term.max_action_value and not self._has_next_wave():
            return True
        # 轮次上限截断（cycle.max_cycles > 0 且预算耗尽）
        cyc = self.encounter.cycle
        if cyc is not None and cyc.max_cycles > 0 and self.state.cycle_index > cyc.max_cycles:
            return True
        return False

    # ------------------------------------------------------------------
    # 轮次（全局时钟纯函数：预算满 → 进下一轮，mechanics 03 §3.1）
    # ------------------------------------------------------------------

    def _tick_cycle(self) -> None:
        """clock 前进后调用：跨过预算终点则进下一轮次（可连续跨多轮——长时间无行动）.

        轮次与任何单位的行动值/速度/推拉条无关，只在时钟前进时结算。
        """
        cyc = self.encounter.cycle
        if cyc is None:
            return
        while self.state.clock >= self.state.cycle_end_clock:
            self.bus.emit("on_cycle_end", {"cycle_index": self.state.cycle_index}, self.state)
            self.state.cycle_index += 1
            self.state.cycle_end_clock += float(cyc.subsequent_cycle_av)
            self.bus.emit("on_cycle_start", {
                "cycle_index": self.state.cycle_index,
                "budget": float(cyc.subsequent_cycle_av),
            }, self.state)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: —— 轮次 {self.state.cycle_index} ——")

    # ------------------------------------------------------------------
    # 波次切换
    # ------------------------------------------------------------------

    def _advance_wave_if_needed(self) -> None:
        """当前波敌人全灭且还有下一波：新敌人登场（忘却之庭模式附带转波次重置）."""
        if self._enemies_alive() or not self._has_next_wave():
            return
        assert self.scheduler is not None
        self.current_wave += 1
        newcomers = self.wave_enemies[self.current_wave]
        for actor in newcomers:
            self._spawn_actor(actor)
            self.scheduler.add_actor(actor)
            self.bus.emit("actor_enter", {"actor": actor.actor_id, "wave_index": self.current_wave,
                                          "actor_type": actor.actor_type}, self.state)
        # 转波次重置（cycle.reset_on_wave，忘却之庭；owner 实战确认 2026-08-24）：
        # 全体剩余距离重置 10000——倒计时实体除外（跨波按原行动值续跑，mechanics 03 §3.4）；
        # 轮次预算重置为首轮值、轮次计数不变（mechanics 03 §3.1"轮次数不重置"）。
        cyc = self.encounter.cycle
        if cyc is not None and cyc.reset_on_wave:
            self.scheduler.reset_action_gauge(except_countdown=True)
            self.state.cycle_end_clock = self.state.clock + float(cyc.first_cycle_av)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: 转波次重置——全体行动值重排（倒计时续跑），轮次预算重置 {cyc.first_cycle_av}")
        self.bus.emit("on_wave_start", {"wave_index": self.current_wave}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: —— 第 {self.current_wave + 1} 波 ——")

    # ------------------------------------------------------------------
    # modifier 基础层——运行时已迁 sim/modifiers.py（ModifierBook）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    def _apply_modifier(self, target: ActorState, mod: Modifier, *, apply_chance: float = 1.0) -> bool:
        return self._modifiers._apply_modifier(target, mod, apply_chance=apply_chance)

    def _sync_speed(self, target: ActorState) -> None:
        self._modifiers._sync_speed(target)

    def dispel(self, target: ActorState, max_count: int = 1) -> int:
        return self._modifiers.dispel(target, max_count)

    def purify(self, target: ActorState, max_count: int = 1) -> int:
        return self._modifiers.purify(target, max_count)

    def _remove_modifier(self, target: ActorState, modifier_id: str, reason: str = "expire") -> None:
        self._modifiers._remove_modifier(target, modifier_id, reason)

    def _tick_dots(self, actor_state: ActorState) -> None:
        self._modifiers._tick_dots(actor_state)

    def _tick_modifiers(self, actor_state: ActorState, anchor: str = "owner_turn_end") -> None:
        self._modifiers._tick_modifiers(actor_state, anchor)

    def _tick_one_modifier(self, actor_state: ActorState, mod: Modifier) -> None:
        self._modifiers._tick_one_modifier(actor_state, mod)

    def _tick_source_modifiers(self, turn_actor: Actor) -> None:
        self._modifiers._tick_source_modifiers(turn_actor)

    @contextmanager
    def _damage_event(self):
        """一次伤害结算的批处理域：同事件内多个致死共享全队仅 1 次的月茧机会.

        owner 实战确认（2026-08-22）：同一次伤害事件（一次行动的多目标/多段结算，
        或同一批 hook 伤害）同时致死 N 人 → 这 1 次机会把 N 个全部送进月茧。
        嵌套事件（结算中 hook 触发反击/追加）各自独立发号，退出时还原外层事件号。
        """
        self._cocoon_event_counter += 1
        outer = self._cocoon_event_seq
        self._cocoon_event_seq = self._cocoon_event_counter
        try:
            yield
        finally:
            self._cocoon_event_seq = outer

    def _moon_cocoon_available(self) -> bool:
        """全队月茧次数当前是否可用：未消耗；或本次伤害事件内已消耗（同时致死共享同一次机会）."""
        if not self.state.moon_cocoon_used:
            return True
        return self._cocoon_event_seq != 0 and self._cocoon_saved_event == self._cocoon_event_seq

    def _check_death(self, target: ActorState, source_id: str = "") -> None:
        """死亡检查：锁血 → 月茧 → 复活 → 真死（受击链末段四层分工）.

        与免死（before_take_damage waterfall cancel 伤害本身，test_death_immunity）的分工：
        - 免死：伤害根本不落账（cancel；140805"受到致命攻击不死"族）
        - 锁血（modifier.hp_lock）：伤害照算，HP 钳 1 不死
        - 月茧（modifier.moon_cocoon 授予件 + state.moon_cocoon_used 战斗级次数）：
          留 1 血进月茧态，下次回合开始前受治疗/获得护盾则解除存活，否则到期真死
          （mechanics 11 §11.1）。次数语义（owner 实战确认 2026-08-22）：
          **全队每场共用 1 次**；同一伤害事件内多人同时致死 → 一次全部进茧；
          之后（含茧中人自己）再受致命击 → 直接真死（茧中不再保 1 血，无"延迟倒下"）
        - 复活（modifier.revive_percent）：HP 归零后消费复活件，按生命上限百分比回拉（发 on_revive）
        """
        if target.current_hp > 0 or not target.alive:
            return
        # 锁血层：致命伤留 1 血
        if any(m.hp_lock for m in target.modifiers.values()):
            target.current_hp = 1.0
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 锁血，HP 保持 1")
            return
        # 月茧层：授予件 + 全队次数可用 → 消耗次数进月茧态（茧中人授予件已消耗、
        # 次数已用，再受致命击自然落不到本层 → 真死，无需特判）
        cocoon_grant = next((m for m in target.modifiers.values()
                             if m.moon_cocoon and m.modifier_id != MOON_COCOON_ID), None)
        if cocoon_grant is not None and self._moon_cocoon_available():
            self._remove_modifier(target, cocoon_grant.modifier_id, "moon_cocoon")
            self.state.moon_cocoon_used = True
            self._cocoon_saved_event = self._cocoon_event_seq
            target.current_hp = 1.0
            self._apply_modifier(target, Modifier(
                modifier_id=MOON_COCOON_ID, name="月茧", modifier_type="buff",
                duration=1, dispellable=False, tick_anchor="owner_turn_start",
                moon_cocoon=True))
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 进入月茧状态")
            return
        # 复活层：消费复活件，set_hp_to_percent 回拉
        rev = next((m for m in target.modifiers.values() if m.revive_percent > 0), None)
        if rev is not None:
            self._remove_modifier(target, rev.modifier_id, "revive")
            # 茧中人被复活接住：月茧态随之结束（次数不退——进茧时已消耗）——否则到期会误杀
            if MOON_COCOON_ID in target.modifiers:
                self._remove_modifier(target, MOON_COCOON_ID, "cocoon_release")
                self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 的月茧解除（复活）")
            max_hp = float(self.pipeline.effective_stats(target)["hp"])
            target.current_hp = max_hp * rev.revive_percent
            self.bus.emit("on_revive", {
                "target": target.actor.actor_id, "percent": rev.revive_percent,
                "hp": target.current_hp, "source": rev.source_id or source_id}, self.state)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {target.actor.name} 触发复活，HP 回复至 {target.current_hp:,.0f}")
            return
        target.alive = False
        # 形态主死亡：形态随死亡解除（exit_state 单漏斗）——境界 banish 的队友回场，
        # 防"主死形态未退"导致的队友永久 banish/frozen 孤儿化
        if target.state_config is not None:
            self.exit_state(target, reason="death")
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
        # 削韧量 = rulebook toughness_damage 表达式求值（双效率池乘算 (1+a)(1+b)——spec 双池，实测待确认 B19；
        # 含光环辐射，pipeline 统一生效面；固定削韧项无实例，公式内中性 0）
        src_state = self.state.actors.get(source.actor_id)
        amount = self.pipeline.toughness_damage_amount(src_state, float(action.toughness_dmg))
        result = self.pipeline.toughness_damage(target, amount, action.damage_type or "", can_reduce)
        if result.value > 0:
            self.bus.emit("on_toughness_damage", {"amount": result.value, "source": source.actor_id, "target": target.actor.actor_id, "bar_index": 0}, self.state)
        if target.toughness <= 0 and not target.broken:
            self._trigger_break(source, action, target)

    def _trigger_break(self, source: Actor, action: Action, target: ActorState) -> None:
        """击破：击破伤害 + 属性击破效果 + 通用推条 25%.

        击破伤害扣血**绕盾直扣**（不走 _absorb_with_shields）= B19 冻结口径
        （hsr-sim 对拍：击破绕盾直扣；游戏真相待实测）——与 mechanics 01 §1.3
        "护盾吸收层普适于一切伤害"的表述存在张力，实测后统一。
        """
        element = action.damage_type or "physical"
        target.broken = True
        self.bus.emit("on_break", {"source": source.actor_id, "target": target.actor.actor_id, "element": element, "bar_index": 0}, self.state)

        # 活体 ActorState 优先（削韧路径同口径）：裸 Actor 会被 pipeline._as_state 包成
        # 无 modifier 裸壳——攻击方战斗 modifier 全丢，且裸壳骗过光环身份排除（other is not st）。
        # None 兜底：外部直调 pipeline/引擎的旧测试可能传不在册的裸 Actor，退回兼容入口。
        src_state = self.state.actors.get(source.actor_id)
        dmg = self.pipeline.break_damage(src_state if src_state is not None else source, target, element)
        # 扣血在引擎层（pipeline.break_damage 纯结算不扣血；绕盾直扣=B19 冻结口径，见上）
        target.current_hp -= dmg.value
        if dmg.value > 0:
            # HP 下降发射点（击破伤害——受击族；reason='break'，词表冻结见 _execute_action）
            self.bus.emit("on_hp_decrease", {
                "amount": dmg.value, "source": source.actor_id,
                "reason": "break", "target": target.actor.actor_id}, self.state)
        self.state.total_damage += dmg.value
        self.state.damage_by_actor[source.actor_id] += dmg.value
        self.state.log.append(f"AV{self.state.clock:.1f}: {source.name} 触发击破，对 {target.actor.name} 造成 {dmg.value:,.0f} 击破伤害")
        self._check_death(target, source.actor_id)

        eff = self.pipeline.break_effect_of(element)
        src_atk = source.stats.atk
        # 控制/DoT 持续回合读 rulebook break_effects 表（mechanics 04 §4.8：控制 1 回合 / DoT 2 回合）
        if eff["control"] == "freeze":
            self._apply_modifier(target, Modifier(
                modifier_id="BRK_FREEZE", name="冻结", modifier_type="control", debuff_kind="control",
                duration=int(eff["control_duration"]), source_id=source.actor_id, control_kind="freeze"))
        elif eff["control"] in ("entangle", "imprison"):
            self._apply_modifier(target, Modifier(
                modifier_id=f"BRK_{eff['control'].upper()}", name=eff["control"], modifier_type="control",
                debuff_kind="control", duration=int(eff["control_duration"]), source_id=source.actor_id, control_kind=eff["control"]))
        if eff["dot_ratio"] is not None and eff["dot_ratio"] > 0:
            self._apply_modifier(target, Modifier(
                modifier_id=f"BRK_DOT_{element}", name=f"{element}持续伤害", modifier_type="dot", debuff_kind="dot",
                duration=int(eff["dot_duration"]), source_id=source.actor_id,
                dot_element=element, dot_ratio=eff["dot_ratio"], dot_source_atk=src_atk))
        elif element == "physical":
            self._apply_modifier(target, Modifier(
                modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot", debuff_kind="dot",
                duration=int(eff["dot_duration"]), source_id=source.actor_id,
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
            grants_immune=list(config.grants_immune),  # 形态内免疫（140805 控制免疫族）
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
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 进入形态 {config.name or config.state}")

    def exit_state(self, actor_state: ActorState, reason: str = "exit") -> None:
        """退出形态：摘标记（on_exit 全路径经 remove 单漏斗）+ 境界植入件清理."""
        if actor_state.state_config is None:
            return
        old_cfg = actor_state.state_config
        old = old_cfg.state
        # 境界植入件随形态解除（exit_remove_modifiers 清单，对全体敌人）
        for mid in old_cfg.exit_remove_modifiers:
            for e in self._enemies_alive():
                self._remove_modifier(e, mid, "state_exit")
        # 离场队友回场（banish 解除 + AV 解冻）
        for aid in self._banished_by_state.pop(actor_state.actor.actor_id, []):
            s = self.state.actors.get(aid)
            if s is not None and s.banished:
                s.banished = False
                self.scheduler.unfreeze(aid)
                self.bus.emit("actor_enter", {"actor": aid, "reason": "unbanish",
                                              "actor_type": s.actor.actor_type}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {s.actor.name} 回场")
        self._remove_modifier(actor_state, actor_state.state_config.marker_id(), reason)
        actor_state.state_config = None
        self.bus.emit("on_state_change", {"actor": actor_state.actor.actor_id, "from_state": old}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 退出形态 {old_cfg.name or old}")

    @staticmethod
    def _replaced_ids(replaces) -> set:
        """replaces_actions 的值归一为集合（str 或 List[str] 兼容）."""
        out: set = set()
        for v in replaces.values():
            out |= set(v) if isinstance(v, (list, tuple)) else {v}
        return out

    def _legal_with_state(self, actor_state: ActorState, legal: List[Action]) -> List[Action]:
        """合法性注入：replaces/locked 生效 + 增强行动仅形态下可用."""
        cfg = actor_state.state_config
        enhanced_ids = set()
        for c in self.state_configs_by_actor.get(actor_state.actor.actor_id, []):
            enhanced_ids |= self._replaced_ids(c.replaces_actions)
            if c.final_action_id:
                enhanced_ids.add(c.final_action_id)
        out: List[Action] = []
        for act in legal:
            if cfg is not None:
                if act.action_type in cfg.locked_actions:
                    continue
                if act.action_type in cfg.replaces_actions:
                    replaced = cfg.replaces_actions[act.action_type]
                    replaced_set = set(replaced) if isinstance(replaced, (list, tuple)) else {replaced}
                    if act.action_id not in replaced_set:
                        continue  # 原型被替换（增强件（可多个）之外的原行动不可用）
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

    def _count_state_action(self, actor_state: ActorState, had_state_at_turn_start: bool) -> None:
        """形态行动计数 + 退出检查（仅本回合开始时就已在形态内的行动计入倒计时——当动变身不计）."""
        if not had_state_at_turn_start or actor_state.state_config is None:
            return
        key = f"_state_actions_{actor_state.state_config.state}"
        actor_state.resources[key] = actor_state.resources.get(key, 0.0) + 1
        self._check_exit_conditions(actor_state)

    def _pick_ally_target(self, attacker: Optional[ActorState] = None) -> Optional[ActorState]:
        """敌方选目标（mechanics 10）：覆盖层 > 加权——掷骰按 taunt_eff 加权，期望取最高（并列按编队序）.

        覆盖层：强制嘲讽（attacker 身上 forced_taunt 件 → 必打其 source，Fandom Aggro
        "ignoring Aggro and Lock On"）；锁定暂由同槽位后续接入（敌方脚本域，暂无实例）。
        """
        allies = self._allies_alive()
        if not allies:
            return None
        if attacker is not None:
            for mod in attacker.modifiers.values():
                if mod.forced_taunt:
                    src = self.state.actors.get(mod.source_id)
                    if src is not None and any(s is src for s in allies):
                        return src
        weights = {id(s): self.pipeline.effective_stats(s)["taunt_eff"] for s in allies}
        if self.pipeline.mode == MODE_ROLL and self.pipeline.rng:
            total = sum(weights.values())
            roll = self.pipeline.rng.random() * total
            acc = 0.0
            for s in allies:
                acc += weights[id(s)]
                if roll <= acc:
                    return s
            return allies[-1]
        return max(allies, key=lambda s: weights[id(s)])

    def _skill_level_of(self, actor: Actor, action: Action) -> int:
        """倍率表取档等级：level_key 优先，缺省按 action_type 映射（follow_up 等归 ultimate）."""
        key = action.level_key or action.action_type
        return int(actor.skill_levels.get(key, actor.skill_levels.get("ultimate", 10)))

    def _resolve_targets(self, actor_state: ActorState, action: Action) -> tuple[Optional[ActorState], List[ActorState]]:
        """按 target_type 解析 (主目标, 目标集)（站位=编队序；blast 相邻=存活列表索引 ±1）.

        主目标选择：policy target_rules（compiled_runtime）优先，缺省=第一个存活敌人.
        """
        actor = actor_state.actor
        tt = action.target_type
        if self._is_monster(actor):
            allies = self._allies_alive()
            if tt == "aoe":
                return (allies[0] if allies else None), allies
            if tt == "bounce":
                picked = (self.pipeline.rng.choice(allies)
                          if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None and allies
                          else (allies[0] if allies else None))
                return picked, ([picked] if picked is not None else [])
            t = self._pick_ally_target(actor_state)
            return t, ([t] if t is not None else [])
        if tt == "self":
            return actor_state, [actor_state]
        if tt in ("ally_single", "ally_aoe"):
            allies = self._allies_alive()
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

    def _execute_action(self, actor_state: ActorState, action: Action, *, _insert: bool = False) -> None:
        actor = actor_state.actor
        primary, targets = self._resolve_targets(actor_state, action)
        if not targets:
            return
        # 成为技能目标（对每个目标发射；140804"成为目标获火种/队友给暴伤"族）
        for t in targets:
            self.bus.emit("on_become_target", {
                "target": t.actor.actor_id, "source": actor.actor_id,
                "action_id": action.action_id, "action_type": action.action_type,
                "insert": _insert,
            }, self.state)

        self._adjust_skill_points(action.skill_point_gain - action.skill_point_cost)
        # None=按类型默认回能（rulebook energy 节查表，mechanics 05 §5.1）；显式 0=该技能不回能（如形态内强化普攻）
        gain = action.energy_gain if action.energy_gain is not None else (
            self.pipeline.energy_gain_default(action.action_type)
        )
        if gain:
            # 行动级结算一次（整动作一回，非逐段——mechanics 05 §5.1 现状语义）
            self._grant_energy(actor_state, gain, source=actor.actor_id,
                               action_id=action.action_id, reason=action.action_type)
        self._apply_action_side_effects(actor_state, action)

        # 净化自身所有可驱散负面（140811"解除自身所有负面效果"族）
        if action.cleanse_self:
            for mid in [m.modifier_id for m in actor_state.modifiers.values()
                        if m.modifier_type == "debuff" and m.dispellable]:
                self._remove_modifier(actor_state, mid, "cleanse")

        if action.damage_type and action.scaling:
            # 段数：静态 instances，或资源驱动（instances_from_resource × per_point，消耗前读）
            instances = max(1, action.instances)
            if action.instances_from_resource:
                n = actor_state.resources.get(action.instances_from_resource, 0.0)
                instances = max(1, int(n * action.instances_per_point))
                if action.instances_cap > 0:
                    instances = min(instances, action.instances_cap)
            if action.consume_all_resource:
                rid = action.consume_all_resource
                spent = actor_state.resources.get(rid, 0.0)
                actor_state.resources[rid] = 0.0
                # 消耗同样可观察（负值事件——"消耗≥N 触发额外"族（140811）的挂钩点）
                self.bus.emit("on_resource_gain", {
                    "actor": actor_state.actor.actor_id, "resource_id": rid,
                    "amount": -spent, "current": 0.0,
                }, self.state)
            # 多段（#19 instances）：SP/能量行动级结算一次，伤害/削韧逐段；段间目标死亡则后续段落空（鞭尸损失）
            # 整段结算 = 一次伤害事件：多目标/多段同时致死共享全队仅 1 次的月茧机会（owner 实战确认 2026-08-22）
            with self._damage_event():
                for seg in range(instances):
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
                        result = self.pipeline.deal_damage(
                            eff, actor_state, target, target_broken=target.broken,
                            skill_level=self._skill_level_of(actor, eff))
                        # 伤害入口 waterfall（before_take_damage）：免死 cancel / 分摊·减伤改写 amount 的总入口
                        wp = self.bus.waterfall("before_take_damage", {
                            "amount": result.value, "damage_type": eff.damage_type,
                            "source": actor.actor_id, "target": target.actor.actor_id,
                            "action_type": eff.action_type, "is_critical": result.node.get("isCrit", False),
                        }, self.state)
                        if wp.get("cancel"):
                            continue  # 伤害被取消（免死类 hook 侧已自理回血/反击）
                        final_amount = float(wp.get("amount", result.value))
                        # 护盾吸收层：乘区结算后、扣 HP 前（并行吸收，本体只承溢出；真伤同走本层）
                        overflow = self._absorb_with_shields(target, final_amount, actor.actor_id)
                        target.current_hp -= overflow
                        if overflow > 0:
                            # HP 下降发射点（mechanics 11 §11.3：受击是 HP 降低来源之一）
                            # reason 词表：spec 仅钉 drain_hp 的 'drain'（05_effects §生命汲取/生命流失），
                            # 其余按扣血路径名冻结（hit/dot/break/set_hp）——spec 未写，勿扩
                            self.bus.emit("on_hp_decrease", {
                                "amount": overflow, "source": actor.actor_id,
                                "reason": "hit", "target": target.actor.actor_id}, self.state)
                        self.state.total_damage += final_amount
                        self.state.damage_by_actor[actor.actor_id] += final_amount
                        self._log(actor, eff, target, final_amount, result.node.get("isCrit", False))
                        if self._is_monster(target.actor):
                            self._apply_toughness_damage(actor, eff, target)
                        self._check_death(target, actor.actor_id)
                        # 受击回能（mechanics 05 §5.1：per-attack 归属、吃 ERR、打盾照回、多段逐段）
                        if target.alive and eff.energy_grant > 0:
                            self._grant_hit_energy(actor, eff, target)
                        # after_being_hit 是受击链收尾事件：钩子上读到盾吸收/锁血/复活/回能后的终态
                        # （actor_type/action_type/hit_targets 供"我方攻击后…"族过滤——缇宝境界/残梅绽挂标）
                        self.bus.emit("after_being_hit", {"amount": final_amount, "absorbed": final_amount - overflow, "damage_type": eff.damage_type, "source": actor.actor_id, "target": target.actor.actor_id, "is_critical": result.node.get("isCrit", False), "seg_index": seg, "actor_type": actor.actor_type, "action_type": eff.action_type, "hit_targets": [t3.actor.actor_id for t3 in targets]}, self.state)
        else:
            # 无伤害行动（self buff/铺场类）也留行动日志——可观察性是机制对轴的前提
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {actor.name} 使用 {action.name}"
            )
        # 计时锚"每次行动"（行动次数型 buff 族；插入行动不算"一次行动"（待实测 B19 候选），v1 仅回合内主动行动 tick）
        if not _insert:
            self._tick_modifiers(actor_state, "on_action")

    def _apply_action_side_effects(self, actor_state: ActorState, action: Action) -> None:
        """行动的副作用通道（resource_gain / act_now / apply_modifiers）——
        普通施放与变身 entry 特判共用（entry 不经 _execute_action 的伤害段）."""
        # 自定义资源获得（火种/毁伤/新蕊族）
        for rid, amt in action.resource_gain.items():
            actor_state.resources[rid] = actor_state.resources.get(rid, 0.0) + amt
            self.bus.emit("on_resource_gain", {
                "actor": actor_state.actor.actor_id, "resource_id": rid, "amount": amt,
                "current": actor_state.resources[rid],
            }, self.state)
        # 立即行动（白厄 140809"使敌方全体立即行动"族）
        if action.act_now_targets == "all_enemies":
            for e in self._enemies_alive():
                self.scheduler.act_now(e.actor)
        # 施放后挂 modifier（dict 声明→物化；target: self（默认）/ all_enemies（植入 debuff 族））
        for spec in action.apply_modifiers:
            tgt = [actor_state] if spec.get("target", "self") == "self" else self._enemies_alive()
            for t in tgt:
                self._apply_modifier_spec(t, spec, actor_state)

    # ------------------------------------------------------------------
    # modifier 物化 + 护盾——运行时已迁 sim/modifiers.py（ModifierBook）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    @staticmethod
    def _modifier_from_spec(spec: Dict[str, Any]) -> Modifier:
        return ModifierBook._modifier_from_spec(spec)

    def _apply_modifier_spec(self, target: ActorState, spec: Dict[str, Any],
                             source: Optional[ActorState]) -> bool:
        return self._modifiers._apply_modifier_spec(target, spec, source)

    def _attach_shield(self, target: ActorState, mod: Modifier, shield_spec: Dict[str, Any],
                       source: Optional[ActorState]) -> None:
        self._modifiers._attach_shield(target, mod, shield_spec, source)

    def _absorb_with_shields(self, target: ActorState, amount: float, source_id: str = "") -> float:
        return self._modifiers._absorb_with_shields(target, amount, source_id)

    # ------------------------------------------------------------------
    # 模板 hooks（机制自包含 DSL）——运行时已迁 sim/hooks.py（HookRuntime）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    def _subscribe_compiled_hooks(self) -> None:
        self._hooks._subscribe_compiled_hooks()

    def _hook_ctx(self, st: ActorState, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._hooks._hook_ctx(st, payload)

    def _hook_target_states(self, sel: Any, st: ActorState, payload: Dict[str, Any]) -> List[ActorState]:
        return self._hooks._hook_target_states(sel, st, payload)

    def _run_hook_effect(self, st: ActorState, eff: Dict[str, Any], payload: Dict[str, Any],
                         updates: Optional[Dict[str, Any]] = None) -> None:
        self._hooks._run_hook_effect(st, eff, payload, updates)

    def _try_ultimate(self, actor_state: ActorState, timing: str) -> bool:
        if self.policy.ult_timing != timing:
            return False
        actions = self.actions_by_actor.get(actor_state.actor.actor_id, [])
        ult = next((a for a in actions if a.action_type == "ultimate"), None)
        if not ultimate_available(actor_state, ult):
            return False
        cost = ult_threshold_of(ult, actor_state.actor.stats.max_energy)  # 开大能耗 = 阈值全扣
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

    def _grant_energy(self, recipient: ActorState, amount: float, *, source: str,
                      action_id: Optional[str], reason: str, err_exempt: bool = False) -> float:
        """能量获得统一入口（§23.4 对账表：一切获得路径的发射点）.

        on_gain_energy waterfall（before_gain 模式，获得量可改写/可取消）→ pipeline.gain_energy。
        行动回能（_execute_action）/ 受击回能（_grant_hit_energy）/ hook 原语 gain_energy
        （含秘技装填预置）都经此；初始能量布场不是事件，不在此列。返回实际获得量。
        """
        wp = self.bus.waterfall("on_gain_energy", {
            "actor": recipient.actor.actor_id, "amount": amount, "source": source,
            "action_id": action_id, "reason": reason, "err_exempt": err_exempt,
        }, self.state)
        if wp.get("cancel"):
            return 0.0
        final = float(wp.get("amount", amount))
        if final <= 0:
            return 0.0
        res = self.pipeline.gain_energy(recipient, final, err_exempt=err_exempt)
        return float(res.node.get("actualAmount", 0.0))

    def _grant_hit_energy(self, source: Actor, action: Action, target: ActorState) -> None:
        """受击回能：受击方获得 = 攻击 energy_grant × 受击方 ERR（忆灵受击归忆师）.

        规则（mechanics 05 §5.1/§5.3）：per-attack 归属（攻击自带档位 5/10/15/20/25）；
        吃受击方 ERR（不在具名豁免清单）；护盾挡住照回（owner 实战确认）；多段按段拆分；
        忆灵受击归忆师——忆师+忆灵同被多目标命中时两次都归忆师。
        发射点：on_gain_energy waterfall（before_gain 模式，获得量可改写）。
        """
        recipient = target
        if target.actor.actor_type == "summon" and target.actor.summoner_id:
            recipient = self.state.actors.get(target.actor.summoner_id) or recipient
        if not recipient.alive or self._is_monster(recipient.actor):
            return
        actual = self._grant_energy(
            recipient, action.energy_grant, source=source.actor_id,
            action_id=action.action_id, reason="being_hit")
        if actual > 0:
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {recipient.actor.name} 受击回能 +{actual:.1f}")

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

        # 冻结：真正跳过一次行动（不恢复韧性；解冻后下次行动提前——比例读 rulebook constants.freeze_advance，mechanics 03 §3.5）
        if frozen:
            for mod_id in [m.modifier_id for m in actor_state.modifiers.values() if m.control_kind == "freeze"]:
                self._remove_modifier(actor_state, mod_id, "expire")
            assert self.scheduler is not None
            self.scheduler.advance_action(actor, self.pipeline.freeze_advance())
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 被冻结，跳过行动")
            return

        # 敌方回合开始：恢复全部韧性、解除击破状态
        # toughness_recovered waterfall（残梅绽族：cancel = 阻止本次恢复、保持击破、
        # 该次行动被消耗——mechanics 04"冻结/残梅绽真跳过"分流）
        if actor_state.broken:
            wp = self.bus.waterfall("toughness_recovered", {
                "target": actor.actor_id, "amount": actor.stats.max_toughness,
            }, self.state)
            if wp.get("cancel"):
                # 恢复被阻止：击破态维持、本次不行动。回合弹出时已无条件重置剩余距离
                # （scheduler.next_actor），本次未行动不该白赚整条约——撤回重置，
                # 只留 hook 推条（残梅绽延后 = BE×20%+10%）后的余量
                assert self.scheduler is not None
                self.scheduler.undo_gauge_reset(actor)
                self.state.log.append(
                    f"AV{self.state.clock:.1f}: [敌] {actor.name} 韧性恢复被阻止，击破状态延长")
                return
            actor_state.broken = False
            actor_state.toughness = float(wp.get("amount", actor.stats.max_toughness))
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 韧性恢复")

        actions = self.actions_by_actor.get(actor.actor_id, [])
        if not actions:
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 行动（占位）")
            return
        self._execute_action(actor_state, actions[0])
        self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": actions[0].action_type,
                                     "actor_type": actor.actor_type}, self.state)

    def trigger_action(self, actor_state: ActorState, action: Action, *, tag: str = "insert") -> None:
        """插入式行动（反击/追加攻击/代放族）：立即结算，不占回合、不调度、不改计数.

        与回合内行动的区别：不走 legal/政策、不影响形态计数器；事件带 insert 标记
        （hook 监听时可区分主动行动与插入行动，防"反击触发反击"无限递归）。
        """
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor_state.actor.name} 插入发动 {action.name}"
        )
        self._execute_action(actor_state, action, _insert=True)
        self.bus.emit("on_action", {
            "actor": actor_state.actor.actor_id, "action_type": action.action_type,
            "insert": True, "tag": tag, "actor_type": actor_state.actor.actor_type,
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
        self._tick_modifiers(actor_state, "owner_turn_start")  # 计时锚"回合开始"（阮梅弦外音族）
        self._tick_dots(actor_state)
        # 回合开始结算致死（DOT/月茧到期）：死亡单位不进入行动阶段（与主循环的 dead-skip 同口径）
        if not actor_state.alive:
            return

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
                self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": forced.action_type,
                                         "actor_type": actor.actor_type}, self.state)
                self._count_state_action(actor_state, had_state_at_turn_start)
            else:
                legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []), self.state.skill_points)
                legal = self._legal_with_state(actor_state, legal)
                if not legal:
                    # 全部行动被锁=空过：无可执行行动，但回合末结算照走（不 return——
                    # 否则 modifier 不 tick / on_turn_end 不发 / turn_count 不增，回合静默蒸发）
                    self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                else:
                    if self.compiled_runtime is not None:
                        want = self.compiled_runtime.select_action_type(actor_state, self)
                        # want 可以是 action_type 或具体 action_id（策略指定技能，如倒计时第 N 动指定 140811）
                        action = (next((a for a in legal if a.action_id == want), None)
                                  or next((a for a in legal if a.action_type == want), legal[0]))
                    else:
                        action = self.policy.select_action(legal)
                    self._execute_action(actor_state, action)
                    self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": action.action_type,
                                             "actor_type": actor.actor_type}, self.state)
                    # 阶段 3 · 行动后窗口
                    self._try_ultimate(actor_state, ULT_AFTER_ACTION)
                    self._count_state_action(actor_state, had_state_at_turn_start)

        # 阶段 4 · 回合结束（B 类结算：modifier tick；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_end", {"actor": actor.actor_id}, self.state)
        self._tick_modifiers(actor_state)
        self._tick_source_modifiers(actor)  # source_turn_end 锚（§4.14 tick_on：按施加者回合走字）
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
            # 正常类额外回合发射 on_extra_turn（倒计时类按文档口径不发射，03_actor §3.11）
            if kind == EXTRA_NORMAL:
                self.bus.emit("on_extra_turn", {"actor": actor.actor_id}, self.state)
            # fixed_av 截断看"本回合时刻"：超过上限的回合不执行（含端点：恰好在上限的回合照跑）
            term = self.encounter.termination
            if (term.mode == "fixed_av" and now > term.max_action_value
                    and not self._has_next_wave()):
                break
            self.state.clock = now
            self._tick_cycle()
            actor_state = self.state.actors[actor.actor_id]
            if not actor_state.alive:
                continue
            self._run_turn(actor_state, kind)
        else:
            # 撞兜底上限：局没打完——标记 + 日志 + 告警（毒数据防线：截断局不得当合法优化样本）
            self.state.truncated = True
            self.state.log.append(
                f"AV{self.state.clock:.1f}: ⚠ 行动数撞兜底上限 {MAX_TURNS_SAFETY}，战斗被截断（truncated）")
            warnings.warn(
                f"战斗撞 MAX_TURNS_SAFETY={MAX_TURNS_SAFETY} 兜底上限被截断：局未打完，"
                "state.truncated=True，snapshot 不得作为合法优化样本",
                RuntimeWarning, stacklevel=2)

        return self.state
