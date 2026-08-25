"""模板 hooks 运行时（机制自包含 DSL）：订阅 + 条件求值 + 效果执行.

从 engine.py 切出的 hooks 职责域（God-object 切分第一刀，纯搬家零逻辑改动）：
CompiledHook 订阅进事件总线、hook 条件/数值的白名单表达式求值、effect_type 分发与
目标选择器解析。战斗状态回调全走 CombatEngine 现成方法（HookRuntime 持 engine 门面，
不复制状态）；engine 上 `_subscribe_compiled_hooks`/`_hook_ctx`/`_hook_target_states`/
`_run_hook_effect` 为同名薄委托（tests 直调口径不变）。
"""
from __future__ import annotations

import types
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hsr_nous.sim.scheduler import EXTRA_NORMAL
from hsr_nous.sim.state import MOON_COCOON_ID, ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.effect_types import HOOK_TARGET_SELECTORS

if TYPE_CHECKING:
    from hsr_nous.sim.engine import CombatEngine


class _HookSelfNS:
    """hook `$self` 命名空间：基础字段急切 + 面板统计惰性（不引用面板零开销）.

    面板键（max_hp/atk/spd/...）首次访问才求值一次 effective_stats 并缓存——不读
    面板键的 hook 条件零 effective_stats 调用（审计实测急切求值 54% 浪费且利用率 0，
    改回按需）。max_hp 保持 effective 口径（effective_stats["hp"]，吃 hp_pct/flat/
    覆写 modifier，与 heal_self/复活的生命上限同口径）。
    """

    __slots__ = ("_engine", "_st", "_eff", "hp", "energy", "state")

    def __init__(self, engine: "CombatEngine", st: ActorState) -> None:
        self._engine = engine
        self._st = st
        self._eff: Optional[Dict[str, Any]] = None
        cfg = st.state_config
        self.hp = st.current_hp
        self.energy = st.current_energy
        self.state = cfg.state if cfg else ""

    @property
    def max_hp(self) -> float:
        """有效生命上限（effective 口径；惰性求值，与面板键同一份缓存）."""
        return self._panel()["hp"]

    def _panel(self) -> Dict[str, Any]:
        """面板统计：首次访问求值 effective_stats 并缓存（同一 hook 条件内多键共享一次求值）."""
        if self._eff is None:
            self._eff = self._engine.pipeline.effective_stats(self._st)
        return self._eff

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._panel()[name]
        except KeyError:
            raise AttributeError(name) from None


class HookRuntime:
    """模板 hooks 运行时：构造持 engine 门面，回调全走 CombatEngine 现成方法."""

    def __init__(self, engine: "CombatEngine") -> None:
        self._engine = engine

    def _subscribe_compiled_hooks(self) -> None:
        for h in self._engine._compiled_hooks:
            kind = self._engine.bus.contract.get(h.event, "emit")
            if kind == "waterfall":
                def wf_handler(et, payload, ctx, _h=h):
                    return self._run_compiled_hook(_h, payload or {})
                self._engine.bus.subscribe_waterfall(h.event, wf_handler)
            else:
                def handler(et, payload, ctx, _h=h) -> None:
                    self._run_compiled_hook(_h, payload or {})
                self._engine.bus.subscribe(h.event, handler)

    def _hook_ctx(self, st: ActorState, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            # insert/cancel 缺省 False：condition 里 `!$event.insert` / `!$event.cancel`
            # 对无该键的普通事件不炸（cancel 仅 waterfall 链上前序 hook 改写后出现）
            "event": types.SimpleNamespace(**{"insert": False, "cancel": False, **payload}),
            "self": _HookSelfNS(self._engine, st),
            **{f"res_{k}": v for k, v in st.resources.items()},
        }

    def _run_compiled_hook(self, h, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        st = self._engine.state.actors.get(h.owner_id)
        if st is None or not st.alive:
            return None
        if h.condition_expr is not None:
            try:
                ok = bool(self._engine._expr.evaluate(
                    h.condition_expr, self._hook_ctx(st, payload),
                    functions=self._hook_functions(st)))
            except Exception as e:
                ok = False  # 条件求值失败=不触发（B8：表达式本身编译期已过白名单）
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: ⚠ hook {h.owner_id}/{h.event} 条件求值失败按不触发处理：{e!r}")
            if not ok:
                return None
        updates: Dict[str, Any] = {}
        for eff in h.effects:
            self._run_hook_effect(st, eff, payload, updates)
        return updates or None

    def _hook_functions(self, st: ActorState) -> Dict[str, Any]:
        """hook 表达式可用的宿主函数实现（stacks/enemies_alive：§22.4 登记，缺省 0 钉死）."""
        def stacks(target: Any, modifier_id: str) -> float:
            # v1 仅支持自身（$self 命名空间或 st 本体）；跨 actor 的 stacks 待 resource_of 族实例
            if isinstance(target, ActorState) and target is not st:
                raise ValueError("stacks() v1 仅支持自身目标")
            m = st.modifiers.get(str(modifier_id))
            return float(m.stacks) if m is not None else 0.0

        def enemies_alive() -> float:
            # 存活敌人数（"敌方全体行动完毕"类阈值条件的计数源——弑魂之炽/云璃反击族）
            return float(len(self._engine._enemies_alive()))

        def has_modifier(target: Any, modifier_id: str) -> float:
            # 目标是否持有指定 modifier（§22.4 登记；target = actor_id 或 ActorState，
            # 跨 actor 查询通道——残梅绽"恢复者身上有无标记"族）
            if isinstance(target, ActorState):
                st2 = target
            else:
                st2 = self._engine.state.actors.get(str(target))
                if st2 is None:
                    return 0.0
            return 1.0 if str(modifier_id) in st2.modifiers else 0.0

        def count(x: Any) -> float:
            # 列表/集合长度（命中目标数计数——缇宝境界"每命中 1 目标 1 段"族，§22.4 登记）
            try:
                return float(len(x))
            except TypeError:
                return 0.0

        return {"stacks": stacks, "enemies_alive": enemies_alive, "has_modifier": has_modifier,
                "count": count}

    def _hook_amount(self, raw: Any, st: ActorState, payload: Dict[str, Any]) -> float:
        """hook 数值参数：数值直用；字符串按白名单表达式求值."""
        if isinstance(raw, (int, float)):
            return float(raw)
        return float(self._engine._expr.evaluate(
            self._engine._expr.compile(str(raw), layer="effect"),
            self._hook_ctx(st, payload),
            functions=self._hook_functions(st),
        ))

    def _event_actor(self, ref: str, payload: Dict[str, Any]) -> Optional[ActorState]:
        """`$event.<字段>` 目标寻址：payload 字段（actor_id）→ ActorState（事件目标族通用）."""
        aid = payload.get(ref.split(".", 1)[1])
        return self._engine.state.actors.get(str(aid)) if aid is not None else None

    def _hook_target_states(self, sel: Any, st: ActorState, payload: Dict[str, Any]) -> List[ActorState]:
        """hook effect 目标选择器统一解析（deal_damage/break_damage/delay_action/remove_modifier 共用）.

        self / all_allies / other_allies / all_enemies / enemy_first / highest_hp /
        highest_hp_hit（本次攻击命中目标集中 HP 最高——payload hit_targets，缇宝境界族）/
        `$event.<字段>`（事件寻址：残梅绽恢复者、缇宝天赋计数标记族）。
        """
        sel = str(sel)
        if sel == "self":
            return [st]
        if sel in ("all_allies", "other_allies"):
            return [s for s in self._engine._allies_alive()
                    if sel == "all_allies" or s is not st]
        if sel == "all_enemies":
            return self._engine._enemies_alive()
        if sel == "highest_hp":
            alive = self._engine._enemies_alive()
            return [max(alive, key=lambda s: s.current_hp)] if alive else []
        if sel == "highest_hp_hit":
            pool = [s for s in (self._engine.state.actors.get(str(i)) for i in payload.get("hit_targets") or [])
                    if s is not None and s.alive]
            return [max(pool, key=lambda s: s.current_hp)] if pool else []
        if sel.startswith("$event."):
            t = self._event_actor(sel, payload)
            return [t] if t is not None else []
        if sel == "enemy_first":
            return self._engine._enemies_alive()[:1]
        # 未知选择器编译期就该炸（build_compiler 白名单）；走到这里=绕过编译层，同口径炸
        raise ValueError(
            f"未知 hook target 选择器 {sel!r}（合法集合：{sorted(HOOK_TARGET_SELECTORS)} + '$event.<字段>'）"
        )

    def _run_hook_effect(self, st: ActorState, eff: Dict[str, Any], payload: Dict[str, Any],
                         updates: Optional[Dict[str, Any]] = None) -> None:
        t = eff.get("effect_type")
        if t == "cancel_event":
            # waterfall 事件取消（免死族；updates 进 waterfall 链）
            if updates is not None:
                updates["cancel"] = True
            return
        if t == "gain_resource":
            rid = eff["resource_id"]
            amt = self._hook_amount(eff.get("amount", 0), st, payload)
            st.resources[rid] = st.resources.get(rid, 0.0) + amt
            self._engine.bus.emit("on_resource_gain", {
                "actor": st.actor.actor_id, "resource_id": rid, "amount": amt,
                "current": st.resources[rid],
            }, self._engine.state)
        elif t == "gain_skill_point":
            self._engine._adjust_skill_points(int(self._hook_amount(eff.get("amount", 0), st, payload)))
        elif t == "gain_energy":
            amt = self._hook_amount(eff.get("amount", 0), st, payload)
            sel = str(eff.get("target", "self"))
            # err_exempt：具名豁免不乘 ERR（mechanics 05 §5.3 清单：停云/藿藿/镜中故我族）
            err_exempt = bool(eff.get("err_exempt", False))
            # target 词表按 05_effects §回复能量收窄为二值（self/all_allies）——其余值
            # 与其他选择器同纪律炸（曾 else 静默当全体：highest_hp 写成全体充能的雷）；
            # 停云单充族实例到达时再开 '$event.<字段>' 通道
            if sel == "self":
                targets = [st]
            elif sel == "all_allies":
                targets = self._engine._allies_alive()
            else:
                raise ValueError(
                    f"gain_energy 的 target 非法值 {sel!r}"
                    f"（合法集合：['all_allies', 'self']，见 05_effects §回复能量）")
            for t2 in targets:
                self._engine._grant_energy(t2, amt, source=st.actor.actor_id,
                                           action_id=None, reason="effect", err_exempt=err_exempt)
        elif t == "set_resource":
            rid = eff["resource_id"]
            st.resources[rid] = self._hook_amount(eff.get("amount", 0), st, payload)
        elif t == "heal_self":
            ratio = self._hook_amount(eff.get("ratio", 0), st, payload)
            # 走管线统一治疗路径（rulebook heal 式：hp_scaling=ratio × 施放者有效 HP，
            # 吃施放者 heal_bonus + 受疗者 incoming_heal——mechanics 01 §1.3）
            result = self._engine.pipeline.heal(st, st, hp_scaling=ratio)
            actual = float(result.node.get("actualAmount", 0.0))
            if actual > 0:
                self._engine.bus.emit("on_hp_increase", {"amount": actual, "source": st.actor.actor_id,
                                                         "reason": "heal", "target": st.actor.actor_id},
                                      self._engine.state)
                # 月茧解除条件之一：受到治疗（mechanics 11 §11.1）
                if MOON_COCOON_ID in st.modifiers:
                    self._engine._remove_modifier(st, MOON_COCOON_ID, "cocoon_release")
                    self._engine.state.log.append(
                        f"AV{self._engine.state.clock:.1f}: {st.actor.name} 的月茧解除（受到治疗）")
        elif t == "set_hp_to_percent":
            # B9 原语：HP 设为生命上限×比例（刃 120503/复活族效果）；可致死（走 _check_death 四层）
            pct = self._hook_amount(eff.get("percent", eff.get("amount", 0)), st, payload)
            max_hp = float(self._engine.pipeline.effective_stats(st)["hp"])
            old_hp = st.current_hp
            st.current_hp = max(0.0, min(max_hp, max_hp * pct))
            if st.current_hp < old_hp:
                # HP 下降发射点（HP 消耗族——mechanics 11 §11.3；reason='set_hp'，词表冻结见 _execute_action）
                self._engine.bus.emit("on_hp_decrease", {
                    "amount": old_hp - st.current_hp, "source": st.actor.actor_id,
                    "reason": "set_hp", "target": st.actor.actor_id}, self._engine.state)
            if st.current_hp <= 0:
                self._engine._check_death(st)
        elif t == "apply_modifier":
            tgt = self._hook_target_states(eff.get("target", "self"), st, payload)
            for t2 in tgt:
                self._engine._apply_modifier_spec(t2, dict(eff.get("modifier") or {}), st)
        elif t == "deal_damage":
            targets = self._hook_target_states(eff.get("target", "enemy_first"), st, payload)
            if not targets:
                return
            # scaling_atk / scaling_hp 合并同一行（scaling 列表逐行=等级档，拆开会被当成两档）
            row: Dict[str, float] = {}
            if eff.get("scaling_atk") is not None:
                row["atk"] = self._hook_amount(eff["scaling_atk"], st, payload)
            if eff.get("scaling_hp") is not None:
                row["hp"] = self._hook_amount(eff["scaling_hp"], st, payload)
            # category: "additional" = 角色附加伤害（mechanics 02 §2.1 生效表：吃常规乘区，
            # 不吃类型限定增伤——action_type 归 "additional"，dmg_bonus_by_type 桶不命中）
            category = str(eff.get("category", ""))
            pseudo = Action(
                action_id=f"hook_{eff.get('name', 'dmg')}", name=str(eff.get("name", "hook")),
                action_type="additional" if category == "additional" else "follow_up",
                target_type="aoe" if len(targets) > 1 else "single",
                damage_type=eff.get("damage_type"),
                scaling=[row],
            )
            for t2 in targets:
                with self._engine._damage_event():  # 每个 hook 伤害目标一批（月茧同时致死批处理域）
                    result = self._engine.pipeline.deal_damage(pseudo, st, t2, target_broken=t2.broken)
                    overflow = self._engine._absorb_with_shields(t2, result.value, st.actor.actor_id)
                    t2.current_hp -= overflow
                    if overflow > 0:
                        # HP 下降发射点（hook 附加/追加伤害——受击族；reason='hit'，词表冻结见 _execute_action）
                        self._engine.bus.emit("on_hp_decrease", {
                            "amount": overflow, "source": st.actor.actor_id,
                            "reason": "hit", "target": t2.actor.actor_id}, self._engine.state)
                    self._engine.state.total_damage += result.value
                    self._engine.state.damage_by_actor[st.actor.actor_id] += result.value
                    self._engine._log(st.actor, pseudo, t2, result.value, result.node.get("isCrit", False))
                    self._engine._check_death(t2, st.actor.actor_id)
        elif t == "trigger_action":
            aid = str(eff.get("action_id", ""))
            action = next((a for a in self._engine.actions_by_actor.get(st.actor.actor_id, [])
                           if a.action_id == aid), None)
            if action is not None:
                if eff.get("scaling_atk") is not None:
                    # 动态倍率覆写（计数器反击族：倍率随 stacks/资源现场求值，见 05_effects trigger_action）
                    action = replace(
                        action,
                        scaling=[{"atk": self._hook_amount(eff["scaling_atk"], st, payload)}],
                    )
                self._engine.trigger_action(st, action, tag="hook")
        elif t == "remove_modifier":
            # 摘除 modifier（计数器消耗/状态解除族；target 默认 self，支持全体/事件寻址——
            # 缇宝天赋计数重置、境界易伤联动摘除族；与 05_effects remove_modifier 声明对齐）
            mid = str(eff["modifier_id"])
            reason = str(eff.get("reason", "remove"))
            for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
                self._engine._remove_modifier(t2, mid, reason)
        elif t == "break_damage":
            # 击破伤害执行体（阮梅天赋/残梅绽族）：pipeline.break_damage × ratio（击破公式，非直伤）
            # 扣血分工：pipeline 纯结算不扣血，本层按 val=值×ratio 一次性扣（恰降 ratio×击破值）；
            # 绕盾直扣（不走 _absorb_with_shields）= B19 冻结口径（注记见 _trigger_break docstring）
            targets = self._hook_target_states(eff.get("target", "enemy_first"), st, payload)
            if not targets:
                return
            element = str(eff.get("element", "physical"))
            ratio = self._hook_amount(eff.get("ratio", 1.0), st, payload)
            for t2 in targets:
                with self._engine._damage_event():  # 每个 hook 击破伤害目标一批（月茧同时致死批处理域）
                    res = self._engine.pipeline.break_damage(st, t2, element)
                    val = res.value * ratio
                    t2.current_hp -= val
                    if val > 0:
                        # HP 下降发射点（hook 击破伤害；reason='break'，词表冻结见 _execute_action）
                        self._engine.bus.emit("on_hp_decrease", {
                            "amount": val, "source": st.actor.actor_id,
                            "reason": "break", "target": t2.actor.actor_id}, self._engine.state)
                    self._engine.state.total_damage += val
                    self._engine.state.damage_by_actor[st.actor.actor_id] += val
                    self._engine.state.log.append(
                        f"AV{self._engine.state.clock:.1f}: {st.actor.name} 对 {t2.actor.name} "
                        f"造成 {val:,.0f} 击破伤害（{str(eff.get('name', 'break'))}）"
                    )
                    self._engine._check_death(t2, st.actor.actor_id)
        elif t == "grant_extra_turn":
            self._engine.scheduler.grant_extra_turn(st.actor.actor_id, EXTRA_NORMAL)
        elif t == "delay_action":
            # 行动延后（05_effects §delay_action；amount 为百分数——30 = 延后 30% 行动条）
            pct = self._hook_amount(eff.get("amount", 0), st, payload) / 100.0
            for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
                assert self._engine.scheduler is not None
                self._engine.scheduler.delay_action(t2.actor, pct)
        elif t == "adjust_stacks":
            mid = str(eff.get("modifier_id", ""))
            m = st.modifiers.get(mid)
            if m is not None:
                # clamp [0, max_stack]（05_effects §adjust_stacks）——max_stack=0 的
                # 0 层件不再被抬到 1（曾钳 [1, max]：max=0 时下界压上界的退化）
                m.stacks = max(0, min(int(m.stacks + self._hook_amount(eff.get("delta", 0), st, payload)),
                                      m.max_stack))
        else:
            # 编译期闸在 build_compiler._compile_hooks（同读 effect_types 单一事实源）；
            # 走到这里=绕过编译层手写 CompiledHook，同口径炸，不许静默吞
            raise ValueError(f"未知 effect_type {t!r}，已实现集合见 sim_schema/effect_types.py")
