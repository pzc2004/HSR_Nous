"""模板 hooks 运行时（机制自包含 DSL）：订阅 + 条件求值 + 效果执行.

从 engine.py 切出的 hooks 职责域（God-object 切分第一刀，纯搬家零逻辑改动）：
CompiledHook 订阅进事件总线、hook 条件/数值的白名单表达式求值、effect_type 分发与
目标选择器解析。战斗状态回调全走 CombatEngine 现成方法（HookRuntime 持 engine 门面，
不复制状态）；engine 上 `_subscribe_compiled_hooks`/`_hook_ctx`/`_hook_target_states`/
`_run_hook_effect` 为同名薄委托（tests 直调口径不变）。
"""
from __future__ import annotations

import json
import math
import re
import types
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hsr_nous.sim.frame import ExecutionFrame
from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim.scheduler import DISTANCE, EXTRA_NORMAL
from hsr_nous.sim.state import MOON_COCOON_ID, ActorState
from hsr_nous.sim_schema.action import DOT_KIND_ELEMENTS, ELEMENTS, Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.config_ai import MONSTER_RANK_VALUES
from hsr_nous.sim_schema.effect_types import HOOK_TARGET_SELECTORS
from hsr_nous.sim_schema.expression import ExpressionError

if TYPE_CHECKING:
    from hsr_nous.sim.engine import CombatEngine


def _scoped_roll_key(key: Any, payload: Dict[str, Any]) -> str:
    name = str(key)
    index = payload.get("loop_index")
    return f"{name}@loop:{index}" if index is not None else name


class _HookSelfNS:
    """hook `$self` 命名空间：基础字段急切 + 面板统计惰性（不引用面板零开销）.

    面板键（max_hp/atk/spd/...）首次访问才求值一次 effective_stats 并缓存——不读
    面板键的 hook 条件零 effective_stats 调用（审计实测急切求值 54% 浪费且利用率 0，
    改回按需）。max_hp 保持 effective 口径（effective_stats["hp"]，吃 hp_pct/flat/
    覆写 modifier，与 heal_self/复活的生命上限同口径）。
    """

    __slots__ = ("_engine", "_st", "_eff", "hp", "energy", "max_energy", "state", "actor_id",
                 "summoner_id")

    def __init__(self, engine: "CombatEngine", st: ActorState) -> None:
        self._engine = engine
        self._st = st
        self._eff: Optional[Dict[str, Any]] = None
        cfg = st.state_config
        self.hp = st.current_hp
        self.energy = st.current_energy
        # 基础能量上限（回能%公式口径："恢复目标能量上限 20%"族——固定面板，不吃 modifier）
        self.max_energy = float(st.actor.stats.max_energy)
        self.state = cfg.state if cfg else ""
        # 持有者 actor_id（"$self.actor_id == $event.source" 族条件——自己的事件才触发）
        self.actor_id = st.actor.actor_id
        # 召唤者 id（忆灵读忆师 `resource_of($self.summoner_id, ...)` 族——非召唤物为 ""；
        # 原仅条件光环域（_CondSelfNS）暴露，hook/available_if 域编译闸放行却运行期炸的
        # 陷阱随 available_if 落地一并消除——三域同 NS）
        self.summoner_id = st.actor.summoner_id

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
        # 绑定参数优先（variable_bindings 求值产物——光锥叠影参数族，15_data_separation）：
        # 显式赋值遮蔽面板派生键（2026-09-23——pct 池暴露后 hp_pct 面板键与光锥
        # variable_bindings 同名冲突，绑定值被面板值遮蔽的病灶实证）
        params = self._engine._binding_params.get(self._st.actor.actor_id) or {}
        if name in params:
            return params[name]
        try:
            return self._panel()[name]
        except KeyError:
            raise AttributeError(name) from None


class _CondSelfNS(_HookSelfNS):
    """条件光环域 `$self`（04_modifier §4.16）：与 hook 版唯一差异——面板**预置为无条件件
    面板**（条件域防环钉：读不到任何 enable_if/stat_exprs 件的贡献）。`summoner_id` 已
    上提基类（hook/available_if/条件光环三域同槽）."""

    __slots__ = ()

    def __init__(self, engine: "CombatEngine", st: ActorState, panel: Dict[str, Any]) -> None:
        super().__init__(engine, st)
        self._eff = panel


class HookRuntime:
    """模板 hooks 运行时：构造持 engine 门面，回调全走 CombatEngine 现成方法."""

    def __init__(self, engine: "CombatEngine") -> None:
        self._engine = engine
        # 累积队列（§23.9）：id(CompiledHook) → [payload 快照...]——挂在实例上随引擎深拷贝
        # （检查点语义：back/goto 恢复的是检查点时刻的未消费队列；放共享 _cell 会串账）
        self._acc_queues: Dict[int, list] = {}

    def _subscribe_compiled_hooks(self) -> None:
        by_event: Dict[str, list] = {}
        acc_hooks: list = []
        order_map = getattr(self._engine, "_trigger_order", {}) or {}

        def _prio(h: Any) -> int:
            ids = order_map.get(h.event, ())
            return ids.index(h.owner_id) if h.owner_id in ids else len(ids)

        # 跨 actor 执行序（23 §23.11 v1）：trigger_order.yaml 声明序 → 编译产物列表序兜底
        # （同事件多 hook 的显式先后；sorted 稳定——同优先级保持编译序）
        indexed = sorted(enumerate(self._engine._compiled_hooks),
                         key=lambda t: (_prio(t[1]), t[0]))
        for _i, h in indexed:
            # getattr 容错：tests 直构的 SimpleNamespace 假 hook 无 accumulated 字段（默认非累积）
            if getattr(h, "accumulated", False):
                acc_hooks.append(h)
                continue
            kind = self._engine.bus.contract.get(h.event, "emit")
            if kind == "waterfall":
                def wf_handler(et, payload, ctx, _h=h):
                    return self._run_compiled_hook(_h, payload or {})
                self._engine.bus.subscribe_waterfall(h.event, wf_handler)
            else:
                by_event.setdefault(h.event, []).append(h)
        for ev, hooks in by_event.items():
            # emit 类事件一事件一订阅：条件快照求值后统一跑效果（语义见 _run_event_hooks_snapshot）
            def handler(et, payload, ctx, _hooks=hooks):
                self._run_event_hooks_snapshot(_hooks, payload or {})
            self._engine.bus.subscribe(ev, handler)
        # 累积模式（§23.9）：主事件入队订阅 + flush 事件消费订阅——flush 后于主事件注册
        # （§23.11 次序：on_* 异步累积在最后；同事件先跑普通 hook 再消费队列）
        for h in acc_hooks:
            def acc_handler(et, payload, ctx, _h=h):
                self._queue_accumulated(_h, payload or {})
            self._engine.bus.subscribe(h.event, acc_handler)
        for h in acc_hooks:
            for fe in h.flush_triggers:
                def flush_handler(et, payload, ctx, _h=h):
                    self._flush_accumulated(_h)
                self._engine.bus.subscribe(fe, flush_handler)

    def _queue_accumulated(self, h, payload: Dict[str, Any]) -> None:
        """累积主事件：条件快照求值（与普通 hook 同口径）→ 通过则 payload 快照入队，不执行 effects."""
        st = self._engine.state.actors.get(h.owner_id)
        if st is None or not self._hook_condition_ok(h, st, payload):
            return
        self._acc_queues.setdefault(id(h), []).append(dict(payload))

    def _flush_accumulated(self, h) -> None:
        """累积消费：聚合队列（targets 按首现序去重 + target_filter 过滤）→ 执行一次 effects → 清空.

        聚合 $event = 末事件 payload 覆写 targets（首现序去重的目标 id 清单）；
        target_filter 对每个候选求值（$it=候选 id，$event=聚合包）；owner 存活才执行
        （放逐不静默——与普通 hook 同口径）；无队/owner 离场 = 无事发生（队列保留）。
        """
        queue = self._acc_queues.get(id(h))
        if not queue:
            return
        st = self._engine.state.actors.get(h.owner_id)
        if st is None or not st.alive:
            return
        targets: list = []
        for p in queue:
            tid = p.get("target")
            if tid is not None and str(tid) not in targets:
                targets.append(str(tid))
        agg = {**queue[-1], "targets": targets}
        if h.target_filter_expr is not None:
            kept = []
            for tid in targets:
                ctx = {**self._hook_ctx(st, agg), "it": tid}
                try:
                    if self._engine._expr.evaluate(
                            h.target_filter_expr, ctx, functions=self._hook_functions(st, agg)):
                        kept.append(tid)
                except Exception as e:
                    self._engine.state.log.append(
                        f"AV{self._engine.state.clock:.1f}: ⚠ hook {h.owner_id}/{h.event} "
                        f"target_filter 求值失败按不收录处理（{tid}）：{e!r}")
            agg["targets"] = kept
        queue.clear()
        if not agg["targets"]:
            return   # 全被过滤=本次消费无事发生（队列已清，防"过滤残渣反复触发"）
        self._run_hook_effects(st, h, agg)

    def _run_event_hooks_snapshot(self, hooks: list, payload: Dict[str, Any]) -> None:
        """emit 类事件分发：条件先**统一快照求值**（所有 hook 都按"事件发生前、彼此效果
        未落地"的状态判定），再按注册序跑通过者的效果——修复互斥分支连环触发
        （1412 征服者：分支1给目标挂上军功后，分支2的 has_modifier 才变真 → 双跑，
        速度 buff 重复刷 + 充能 +2 而非 +1）。alive 判定保持执行时
        （同旧口径：前序效果致死者不再触发；放逐**不**静默——军功体系这类全局机制
        挂在事件上继续生效（实战确认：放逐刻律德菈充能/奇袭照跑）；waterfall 链不走此路
        （取消/改写依赖前序更新，必须逐个）。

        与执行帧的分层共存（23_event_hook_system.md §23.15）：本快照冻结的是**已提交态**；
        执行帧覆盖层是"执行内未提交写入"，快照层的 condition 同为帧内读者、照常经
        `config_ai_dynamic_value` 读覆盖层（read-your-writes），但读不到同窗 hook 效果
        对普通状态的未提交改动——repeatable-read 与 read-your-writes 两层互不替代。"""
        passed = []
        for h in hooks:
            st = self._engine.state.actors.get(h.owner_id)
            if st is not None and self._hook_condition_ok(h, st, payload):
                passed.append((h, st))
        for h, st in passed:
            if not st.alive and h.event not in {"on_kill", "actor_exit"}:
                continue   # 死亡/离场自身的终结回调必须能执行
            self._run_hook_effects(st, h, payload)

    def _hook_condition_ok(self, h, st: ActorState, payload: Dict[str, Any]) -> bool:
        """hook 条件求值（快照与逐 hook 共用）：失败按不触发 + 战斗日志留 ⚠（B8 同口径）。

        condition 是快照域——`_roll_readonly=True`：roll 只许读已绑定键、
        禁止采样（condition 无副作用的纯洁性，§23.15 分域规则）。"""
        if h.condition_expr is None:
            return True
        try:
            return bool(self._engine._expr.evaluate(
                h.condition_expr, self._hook_ctx(st, payload),
                functions=self._hook_functions(st, payload, _roll_readonly=True)))
        except Exception as e:
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: ⚠ hook {h.owner_id}/{h.event} 条件求值失败按不触发处理：{e!r}")
            return False

    def _run_hook_effects(self, st: ActorState, h, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        frame = None
        if self._engine.current_frame is None:
            frame = ExecutionFrame(
                action_id=str(payload.get("action_id") or getattr(h, "event", "")),
                actor_id=st.actor.actor_id,
                action_type=str(payload.get("action_type") or ""), insert=bool(payload.get("insert", False)))
            self._engine._frame_stack.append(frame)
        try:
            result = self._run_hook_effects_inner(st, h, payload)
        except Exception:
            if frame is not None:
                self._engine._frame_stack.pop()
            raise
        if frame is not None:
            self._engine._frame_stack.pop()
            self._engine._commit_frame(frame)
        return result

    def _run_hook_effects_inner(self, st: ActorState, h, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        updates: Dict[str, Any] = {}
        # $last/$prev 前序快照（合并命名，两键同值）：链内逐 effect 可见上一个
        # effect 的主数值结果（deal_damage/heal 记 actual_amount 合计；实例变量通道，
        # 嵌套事件自成一链——外层链在嵌套返回后恢复）
        prev_chain = getattr(self, "_chain_last", None)
        self._chain_last: Dict[str, Any] = {}
        # 链内命中序号（after_being_hit seg_index 口径——一次 hook 触发 = 一次攻击，链内
        # 第 N 个发伤 deal_damage = 第 N-1 段，镜像 action 层多段 seg_index；嵌套事件
        # 自成一链，与 _chain_last 同保存/还原节律）
        prev_hit_seq = getattr(self, "_chain_hit_seq", None)
        self._chain_hit_seq = 0
        try:
            for eff in h.effects:
                if eff.get("effect_type") == "once_per_battle":
                    latch_id = str(eff["latch_id"])
                    if latch_id in self._engine.state.once_latches:
                        break
                    self._engine.state.once_latches.add(latch_id)
                    continue
                self._run_hook_effect(st, eff, payload, updates)
        finally:
            self._chain_last = prev_chain
            self._chain_hit_seq = prev_hit_seq
        return updates or None

    def _run_compiled_hook(self, h, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        st = self._engine.state.actors.get(h.owner_id)
        if st is None or (not st.alive and h.event not in {"on_kill", "actor_exit"}):
            return None   # 放逐不静默；on_kill/actor_exit 允许终结回调
        if not self._hook_condition_ok(h, st, payload):
            return None
        return self._run_hook_effects(st, h, payload)

    def _hook_ctx(self, st: ActorState, payload: Dict[str, Any]) -> Dict[str, Any]:
        ctx = {
            # insert/cancel 缺省 False：condition 里 `!$event.insert` / `!$event.cancel`
            # 对无该键的普通事件不炸（cancel 仅 waterfall 链上前序 hook 改写后出现）
            "event": types.SimpleNamespace(**{"insert": False, "cancel": False, **payload}),
            "self": _HookSelfNS(self._engine, st),
            # $level 关卡黑板（决策卡 #31）——伪 ActorState，不占站位/目标池
            "level": self._engine._level_state,
            "light_team": self._engine._team_entity_state("TeamLight"),
            "dark_team": self._engine._team_entity_state("TeamDark"),
            # $team 跨 actor 聚合（§22.4——max($team.atk) / sum($team.broken) 族）
            "team": self._engine.team_namespace(),
            **self._engine._res_ns(st),
        }
        # $modifier 命名空间（modifier 相关事件的 payload 驱动）：modifier_id / source
        # （施加者——昔涟"标记消耗后回源追忆"族；source 由发射点供给/实例反查兜底）/
        # stacks / duration / max_stacks（注意复数 max_stacks，映射 modifier.max_stack 字段）
        if "modifier_id" in payload:
            target_id = str(payload.get("target", st.actor.actor_id))
            t_st = (self._engine.state.actors.get(target_id)
                    or self._engine._pseudo_entity_state(target_id))
            m = t_st.modifiers.get(str(payload["modifier_id"])) if t_st else None
            src = payload.get("source", "")
            if not src:
                src = m.source_id if m is not None else ""
            ctx["modifier"] = types.SimpleNamespace(
                modifier_id=str(payload["modifier_id"]), source=src,
                stacks=m.stacks if m is not None else 0,
                duration=m.duration if m is not None else 0,
                max_stacks=m.max_stack if m is not None else 0)
        return ctx

    def _count_selected_with_self(self, pool: Any, where: Any, self_ns: Any,
                                  owner: ActorState, event_ns: Any = None,
                                  include_unselectable: bool = False) -> float:
        """count_selected 透传外层 self/event；owner 决定嵌套池的属主。"""
        # 归一为目标规格后委托唯一解析路径 _hook_target_states（禁采样）——不再自实现
        # concat/take/where：旧 dict 分支把外层 take 逐子块应用再求和（count=N×take，
        # effect 对并集只取 take），且忽略函数级 where/include_unselectable、random 模式
        # 经 _hook_target_states 掷骰耗主 RNG。单一路径令计数与 effect 选择恒等且条件域纯。
        if isinstance(pool, dict):
            spec = dict(pool)
        elif isinstance(pool, str) and pool.lstrip().startswith("{"):
            spec = json.loads(pool)
        else:
            if str(pool).startswith("$event."):
                raise ValueError("count_selected 的字符串 pool 不支持 $event；请改用目标规格对象")
            spec = {"pool": str(pool)}
        # 函数级 where/include_unselectable 并入规格（与 effect target 同口径）
        if where is not None and str(where).strip() not in {"", "true", "True"}:
            spec["where"] = (f"({spec['where']}) and ({where})"
                             if spec.get("where") else str(where))
        if include_unselectable:
            spec["include_unselectable"] = True
        event_payload = dict(vars(event_ns)) if event_ns is not None else {}
        # 规格引用了 payload 缺失的 $event 字段 → 无事件语境，计 0（沿用旧口径）
        required = set(re.findall(r"\$event\.([A-Za-z_]\w*)", json.dumps(spec)))
        if any(field not in event_payload for field in required):
            return 0.0
        return float(len(self._hook_target_states(
            spec, owner, event_payload, allow_sample=False)))

    def _hook_functions(self, st: ActorState, payload: Optional[Dict[str, Any]] = None,
                        *, _roll_readonly: bool = False) -> Dict[str, Any]:
        """hook 表达式可用的宿主函数实现（stacks/enemies_alive：§22.4 登记，缺省 0 钉死）.

        `_roll_readonly`：condition（快照）域为 True——roll 只读已绑定、禁止采样；
        其余求值域（effect amount/effect 级 condition/target_filter/命中域）为
        False——roll 首调采样绑定。分域规则见 23_event_hook_system.md §23.15。
        """
        # 目标反查两通道（原 21 处内联样板收编——is_adjacent 内联 _resolve 先例上提共享）：
        # `_resolve` = has_modifier 通道（四分支全型：ActorState 直用 / _HookSelfNS 拆包 ._st /
        # actor_id 属性（$it 命名空间）反查 / 裸 str 反查；查无 → None，各宿主按自身缺省口径
        # 落 0.0/""）；`_lookup` = actor_type_of 通道（ActorState 直用 + actor_id 属性或裸 str
        # 反查——两通道对 ActorState 直传已对齐（2026-09-24 潜伏差消除，实测无现网直传路径，
        # 统一口径防未来模板踩静默落空））
        def _resolve(target: Any) -> Optional[ActorState]:
            pseudo = self._engine._pseudo_entity_state(
                getattr(target, "actor_id", None) or str(target))
            if pseudo is not None:
                return pseudo
            aid = getattr(target, "actor_id", None)
            if isinstance(target, ActorState):
                return target
            if isinstance(target, _HookSelfNS):
                return target._st
            if aid is not None:
                from hsr_nous.sim.target_algebra import battle_event_actor
                return (self._engine.state.actors.get(str(aid))
                        or battle_event_actor(self._engine, aid))
            from hsr_nous.sim.target_algebra import battle_event_actor
            return (self._engine.state.actors.get(str(target))
                    or battle_event_actor(self._engine, target))

        def _lookup(target: Any) -> Optional[ActorState]:
            pseudo = self._engine._pseudo_entity_state(
                getattr(target, "actor_id", None) or str(target))
            if pseudo is not None:
                return pseudo
            if isinstance(target, ActorState):
                return target
            aid = getattr(target, "actor_id", None) or str(target)
            from hsr_nous.sim.target_algebra import battle_event_actor
            return (self._engine.state.actors.get(str(aid))
                    or battle_event_actor(self._engine, aid))

        def stacks(target: Any, modifier_id: str) -> float:
            # 目标持有的 modifier 层数（§22.4 登记，缺省 0 钉死）；目标解析与 has_modifier
            # 同通道（$self/ActorState/actor_id/$it 命名空间——跨 actor 读，昔涟 1141519
            # 「天空」层数门控首实例）；查无 actor/无该 modifier 返回 0.0（false-y 安全缺省）
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            m = st2.modifiers.get(str(modifier_id))
            if m is None:
                return 0.0
            return float(m.stacks + sum(x.stacks for x in m.instances))

        def modifier_duration(target: Any, modifier_id: str) -> float:
            # 目标持有的 modifier 剩余时长；目标解析与 stacks/has_modifier 同通道，查无返回 0。
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            m = st2.modifiers.get(str(modifier_id))
            if m is None:
                return 0.0
            return float(max([m.duration, *(x.duration for x in m.instances)]))

        def modifier_max_stacks(target: Any, modifier_id: str) -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            modifier = st2.modifiers.get(str(modifier_id))
            return float(modifier.max_stack) if modifier is not None else 0.0

        def modifier_dynamic_of(target: Any, modifier_id: Any, dynamic_key: Any) -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return self._modifier_dynamic_value(st2, str(modifier_id), str(dynamic_key))

        def sum_stacks(modifier_id: Any, side: Any = "enemy") -> float:
            # 当前在场单位指定 modifier 的总层数（720-Degree Review 跨 Grunt 聚合首实例）。
            side_name = str(side)
            if side_name not in {"ally", "enemy", "all"}:
                raise ValueError(f"sum_stacks side 非法：{side_name!r}")
            total = 0.0
            for st2 in self._engine.state.actors.values():
                if not st2.alive or st2.banished:
                    continue
                is_enemy = self._engine._is_enemy(st2.actor)
                if (side_name == "ally" and is_enemy) or (side_name == "enemy" and not is_enemy):
                    continue
                modifier = st2.modifiers.get(str(modifier_id))
                if modifier is not None:
                    total += float(modifier.stacks + sum(x.stacks for x in modifier.instances))
            return total

        def enemies_alive() -> float:
            # 存活敌人数（"敌方全体行动完毕"类阈值条件的计数源——弑魂之炽/云璃反击族）
            return float(len(self._engine._enemies_alive()))

        def hp_locked(target: Any) -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return 1.0 if any(m.hp_lock for m in st2.all_modifiers()) else 0.0

        def damageable_enemies() -> float:
            # 仍可被削减生命值的敌人数（存活且无任何 hp_lock 件——官方"敌方无法被继续削减
            # 生命值"判定源，1510 拓星者"致命/锁血立即最后一击"首实例；与 enemies_alive 同宿主）
            return float(sum(1 for e in self._engine._enemies_alive() if not hp_locked(e)))

        def broken_of(target: Any) -> float:
            """目标是否处于弱点击破状态（`ActorState.broken` 直读——击破查询正式通道：
            1206 素裳挡因③/1220 飞霄终结技逐击切换首实例；目标解析与 has_modifier
            同通道（actor_id / ActorState / $self / $it 反查），查无返回 0.0."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return 1.0 if st2.broken else 0.0

        def is_adjacent(target: Any, ref: Any) -> float:
            """目标是否与参照目标**相邻**（blast 扩散相邻判定正式通道——与
            `engine._resolve_targets` blast 同口径：站位=编队序、相邻=同侧存活
            列表索引 ±1；敌方池=存活敌人，我方池=存活且 enemy_targetable 的我方
            单位，忆灵紧邻忆师右侧也吃相邻）。两参各自按 has_modifier 同通道解析
            （actor_id / ActorState / $self / 目标代数 $it 反查）；查无 actor /
            不同侧 / 同一体 / 任一不在存活池返回 0.0。刃 1120503 终结技 tally
            相邻段（官方 desc 主目标 #5×tally / 相邻 #6×tally——主/邻区分
            通道，1205 E1/1212 E1 同族挡因收编）首实例."""
            st_t, st_r = _resolve(target), _resolve(ref)
            if st_t is None or st_r is None or st_t is st_r:
                return 0.0
            if self._engine._is_enemy(st_t.actor) != self._engine._is_enemy(st_r.actor):
                return 0.0
            if self._engine._is_enemy(st_r.actor):
                pool = self._engine._enemies_alive()
            else:
                pool = [s for s in self._engine._allies_alive()
                        if s.actor.summon_flags.get("enemy_targetable", True)]
            if st_t not in pool or st_r not in pool:
                return 0.0
            return 1.0 if abs(pool.index(st_t) - pool.index(st_r)) == 1 else 0.0

        def target_lists_intersect(first: Any, second: Any) -> float:
            left = self._hook_target_states(json.loads(str(first)), st, payload or {})
            right = self._hook_target_states(json.loads(str(second)), st, payload or {})
            right_ids = {state.actor.actor_id for state in right}
            return 1.0 if any(state.actor.actor_id in right_ids for state in left) else 0.0

        def target_in_selected(spec: Any, target: Any) -> float:
            selected = self._hook_target_states(json.loads(str(spec)), st, payload or {})
            resolved = _resolve(target)
            if resolved is None:
                return 0.0
            actor_id = resolved.actor.actor_id
            return 1.0 if any(state.actor.actor_id == actor_id for state in selected) else 0.0

        def weakness_count(target: Any) -> float:
            """目标当前弱点列表的属性种类数（面板弱点 ∪ modifier weakness_add 植入——
            pipeline.effective_weakness 同口径；22004 宇宙大生意「每有 1 个不同属性弱点
            增伤」/那刻夏按弱点种类计数族首实例）。目标解析与 has_modifier 同通道，
            查无返回 0.0（false-y 安全缺省同口径）."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return float(len(self._engine.pipeline.effective_weakness(st2)))

        def has_weakness(target: Any, element: Any) -> float:
            """目标当前弱点列表是否含指定属性（含植入——pipeline.effective_weakness
            同口径，weakness_count 的单属性谓词形；316 火弱点击破特攻/108 量子弱点
            无视防御族首实例，2026-10-12 接线）。element 小写归一；字面量参
            词表闸在编译期（expression._FUNC_LITERAL_ARG_VOCAB——词表外错拼编译期炸），
            动态参（element_of 族）运行期非词表值按 0.0（false-y 安全缺省——element_of
            查无得 '' 落此）。目标解析与 broken_of 同通道（_resolve），查无返回 0.0."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            elem = str(element).lower()
            if elem not in ELEMENTS:
                return 0.0
            return 1.0 if elem in self._engine.pipeline.effective_weakness(st2) else 0.0

        def dot_kind(target: Any, kind: Any) -> float:
            """目标是否持有指定种类的 DoT 件（种类词表 = DOT_KIND_ELEMENTS——触电 shock/
            风化 wind_shear/灼烧 burn/裂伤 bleed；判定 = modifier_type=='dot' 严口径
            （dot_count 同漏斗）且 dot_element 命中种类映射属性；21022 延长记号「触电或
            风化目标增伤」/21026 灼裂集合/23022 按类叠层族首实例，2026-10-12
            接线）。kind 小写归一；字面量参词表闸在编译期（错拼编译期炸），动态参运行期
            非词表值按 0.0（false-y 安全缺省）。目标解析与 has_modifier 同通道，查无返回 0.0."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            elem = DOT_KIND_ELEMENTS.get(str(kind).lower())
            if elem is None:
                return 0.0
            return 1.0 if any(
                m.modifier_type == "dot" and m.dot_element == elem
                for m in st2.all_modifiers()) else 0.0

        def has_behavior_flag(target: Any, flag: Any) -> float:
            """目标是否持有携带指定原始行为旗标的 modifier；不从可选性等状态反推。"""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            name = str(flag)
            return 1.0 if any(name in m.behavior_flags
                              for m in st2.all_modifiers()) else 0.0

        def has_stat_penalty(target: Any, stat: Any) -> float:
            """目标是否持有指定 stat 的负面修饰（泛化「防御降低/减速」检索原语——
            按 stat_effects 负值扫描非 buff 件（debuff/dot/control 全计，与 has_debuff
            同 new_kind 漏斗）；21044 无边曼舞「对防御降低或减速敌暴伤」族。
            边界：stat_exprs 条件件数值运行期才求值不静态判号（当前无实例）；
            override_effects 覆写族不判（降防均为 def_pct 负值先例）。目标解析与
            has_modifier 同通道，查无返回 0.0."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            key = str(stat)
            for m in st2.all_modifiers():
                kind = m.debuff_kind or ("control" if m.control_kind else m.modifier_type)
                if kind == "buff":
                    continue
                if float(m.stat_effects.get(key, 0.0)) < 0:
                    return 1.0
            return 0.0

        def has_shield(target: Any, source: Any = "") -> float:
            """目标是否持有护盾实例（ActorState.shields 非空直读——128 隐士 4pc
            「持盾友方暴伤」/21053 持盾增伤族；逐目标持盾判定通道）。
            source 非空时窄化为「持有指定施加者提供的护盾」（隐士 4pc「装备者提供的
            护盾」字面口径）。目标解析与 has_modifier 同通道，查无返回 0.0."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            if not st2.shields:
                return 0.0
            src = str(source)
            if src and not any(str(s.source_id) == src for s in st2.shields):
                return 0.0
            return 1.0

        def shield_of(target: Any, modifier_id: Any = "") -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            wanted = str(modifier_id)
            return float(sum(shield.remaining for shield in st2.shields
                             if not wanted or shield.modifier_id == wanted))

        def shielded_count() -> float:
            """场上持有护盾的角色数（非怪 actor——21043 两个人的演唱会「每有一名
            持有护盾的角色增伤」族；has_shield 的计数聚合形）."""
            return float(sum(1 for s in self._engine.state.actors.values()
                             if not self._engine._is_enemy(s.actor) and s.shields))

        def has_modifier(target: Any, modifier_id: str, source: Any = "") -> float:
            # 目标是否持有指定 modifier（§22.4 登记；target = actor_id 或 ActorState 或
            # 目标代数 $it 命名空间（actor_id 反查）——跨 actor 查询通道——
            # 残梅绽"恢复者身上有无标记"族；
            # $self（_HookSelfNS 面板命名空间包装）按 hook 持有者处理——曾落 str($self)
            # 查无此人恒 0，"单场一次"闸集体失效（1412 见者每次终结技都触发病例）；
            # 拆包 ._st 而非直用闭包 st（2026-09-24）：$self 的 _st 恒=持有者（同值），
            # $target 逐目标注入件（_hook_amount target_st 槽）的 _st=该目标——宿主函数
            # 读 $target 不再错落持有者（桑博 1108 E4 stacks($target,…) 首实例）
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            modifier = st2.modifiers.get(str(modifier_id))
            if modifier is None:
                return 0.0
            if source:
                return 1.0 if any(x.source_id == str(source)
                                  for x in [modifier, *modifier.instances]) else 0.0
            return 1.0

        def modifier_source(target: Any, modifier_id: Any) -> str:
            """目标所持 modifier 的原施加者 id；查无 actor/实例返回空串."""
            st2 = _resolve(target)
            if st2 is None:
                return ""
            modifier = st2.modifiers.get(str(modifier_id))
            return str(modifier.source_id) if modifier is not None else ""

        def modifier_kind(target: Any, modifier_id: Any) -> str:
            st2 = _resolve(target)
            if st2 is None:
                return ""
            modifier = st2.modifiers.get(str(modifier_id))
            if modifier is None:
                return ""
            return str(modifier.debuff_kind or (
                "control" if modifier.control_kind else modifier.modifier_type))

        def controlled(target: Any, kind: str = "") -> float:
            # 目标是否受控（可选 control_kind 精确过滤）——合成 kind=="control" 口径与硬免疫
            # 判定/$mod.kind 同漏斗；目标解析与 has_modifier 同通道，查无返回 0.0。
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return 1.0 if any(
                (m.debuff_kind or ("control" if m.control_kind else m.modifier_type)) == "control"
                and (not kind or m.control_kind == kind)
                for m in st2.all_modifiers()) else 0.0

        def action_disabled(target: Any) -> float:
            """目标是否持有任一 prevent_action 件（ConfigAI DisableAction 同口径）."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return 1.0 if any(m.prevent_action for m in st2.all_modifiers()) else 0.0

        def immune_debuff(target: Any) -> float:
            """目标是否持有已启用的全减益免疫件；单独控制免疫不算."""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            required = {"debuff", "dot", "control"}
            return 1.0 if any(
                required.issubset(m.grants_immune)
                and self._engine.pipeline.modifier_enabled(st2, m)
                for m in st2.all_modifiers()) else 0.0

        def has_debuff(target: Any) -> float:
            # 目标是否持有任一负面状态（§22.4 登记；游戏「负面状态」口径——debuff/dot/
            # control 全计，与硬免疫判定（modifiers._apply_modifier new_kind）/$mod.kind
            # 同漏斗：debuff_kind or (control if control_kind else modifier_type) != "buff"；
            # 117 死水 2pc"受负面状态影响的敌人"族首实例）。目标解析与 has_modifier
            # 同通道（$self/ActorState/actor_id/$it），查无返回 0.0（false-y 安全缺省同口径）
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return 1.0 if any(
                (m.debuff_kind or ("control" if m.control_kind else m.modifier_type)) != "buff"
                for m in st2.all_modifiers()) else 0.0

        def debuff_count(target: Any, source: Any = "") -> float:
            # 目标持有的负面状态件数（同 has_debuff 的 new_kind 漏斗——dot/control 子类
            # 不特殊全计；按 modifier 实例数，stacks 不展开（同源覆盖/异源并存口径，
            # mechanics 02 §2.12 同名规则）；21001 晚安/23007 雨下/23020 洗礼按数增益族
            # 首实例）。目标解析与 has_modifier 同通道，查无返回 0.0（false-y 安全缺省同口径）。
            # source 参（2026-10-12）：非空时窄化为「指定施加者（source_id）施加的
            # 负面效果」计数——23047 魂迷「装备者施加的负面效果」/24003「装备者施加的
            # DoT」来源检索族；空串 = 全口径（原语义不变）
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            src = str(source)
            return float(sum(
                1 for m in st2.all_modifiers()
                if (m.debuff_kind or ("control" if m.control_kind else m.modifier_type)) != "buff"
                and (not src or str(m.source_id) == src)))

        def dot_count(target: Any) -> float:
            # 目标持有的 DoT 件数（modifier_type=="dot" 严口径——116 幽锁 4pc"每承受 1 个
            # 持续伤害效果无视 6% 防御"族首实例；控制/纯 debuff 不计）。目标解析与
            # has_modifier 同通道，查无返回 0.0（false-y 安全缺省同口径）
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return float(sum(1 for m in st2.all_modifiers() if m.modifier_type == "dot"))

        def dot_value(target: Any, modifier_id: Any) -> float:
            """目标指定 DoT modifier 的当跳基数（跳伤/引爆读数唯一事实源——pipeline
            .dot_tick_base 单漏斗，静态件=快照 ability_multiplier×跳伤时刻层数、表达式件=
            持有者现值+施加者快照现场求值、击破裂伤=bleed_base_multi×ratio；乘区不在内）。
            「按原 DoT X%」族表达式读数通道（首实例曾卢卡 111104——2026-10-12 迁 trigger_dot
            ratio 槽声明式；表达式内需读跳伤基数的场景仍走本函数）——dot_snapshot_ctx
            里存了什么就读什么。目标解析与 has_modifier 同通道；查无 actor/无该 modifier/
            非 dot 类返回 0.0（false-y 安全缺省同口径）"""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            m = st2.modifiers.get(str(modifier_id))
            if m is None or m.modifier_type != "dot":
                return 0.0
            return float(self._engine.pipeline.dot_tick_base(st2, m))

        def count(x: Any) -> float:
            # 列表/集合长度（命中目标数计数——缇宝境界"每命中 1 目标 1 段"族，§22.4 登记）
            try:
                return float(len(x))
            except TypeError:
                return 0.0

        def count_selected(pool: Any, where: Any = "true",
                           include_unselectable: Any = False) -> float:
            # 字符串 pool 不支持事件池；目标规格对象/JSON 复用 effect target 全语境。
            event_ns = (types.SimpleNamespace(**{"insert": False, "cancel": False, **payload})
                        if payload is not None else None)
            return self._count_selected_with_self(
                pool, where, _HookSelfNS(self._engine, st), st, event_ns,
                bool(include_unselectable))

        def unique_sources(resource_id: Any) -> float:
            # 资源来源去重计数（provenance: true 族——昔涟"不同队友数"；
            # "当前持有"口径：来源集合随资源耗尽清空重计）
            return float(len(self._engine._resource_provenance.get(
                (st.actor.actor_id, str(resource_id)), set())))

        def actor_type_of(target: Any) -> str:
            # 目标 actor 类别（character/monster/summon——"我方目标"过滤写
            # actor_type_of($it) != 'monster'，风堇 1140903 族；目标解析 = id 直查通道
            #（_lookup，见本方法头部两通道注），查无返回 ""（过滤/条件语境 false-y 安全缺省）
            st2 = _lookup(target)
            return "" if st2 is None else str(st2.actor.actor_type)

        def path_of(target: Any) -> str:
            # 目标命途（英文 canonical key——Actor.path 已接线字段的 hook 条件消费口：
            # "对同谐命途角色施放时不触发 X"族，星期日 131302 同谐限制首实例；
            # 目标解析与 actor_type_of 同通道，查无 actor/无命途返回 ""（false-y 安全缺省同口径）
            st2 = _lookup(target)
            return "" if st2 is None else str(st2.actor.path or "")

        def has_summon(target: Any) -> float:
            # 目标是否持有在场召唤物（存活未放逐、summoner_id 反指目标——"若目标持有召唤物则 X"
            # 存在性判定族，星期日 131302 增伤额外 +50% 首实例；目标解析与 actor_type_of
            # 同通道，查无返回 0.0——false-y 安全缺省同口径）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            tid = st2.actor.actor_id
            return 1.0 if any(
                s.alive and not s.banished and s.actor.summoner_id == tid
                for s in self._engine.state.actors.values()) else 0.0

        def summoner_of(target: Any) -> str:
            # 目标的忆师/召唤者 actor_id（Actor.summoner_id 直读——「装备者的忆灵」归属
            # 判定正式通道：summoner_of($event.actor) == $self.actor_id，替换 has_summon
            # 存在性近似（多忆师编队 A 的忆灵在场时 B 的机制误挂病灶——20021/21050/21054/
            # 21057/123/124/125/127 八件 2026-10-12 收编）；非召唤物返回 ''
            #（summoner_id 缺省空串）。目标解析与 stat_of/element_of 同通道（_lookup），
            # 查无返回 ''（false-y 安全缺省同口径）
            st2 = _lookup(target)
            if st2 is None:
                return ""
            return str(st2.actor.summoner_id or "")

        def actor_alive(target: Any) -> float:
            # 目标是否在场（存活未放逐——"在场"判定正式通道：召唤物在场闩绝育后的唯一事实源，
            # 1222 _fy_on_field / 1407 _nw_on_field 手工记账闩全废，2026-09-17；离场不离字典
            # （dismiss 后 actor 仍在 state.actors 但 alive=False），actor_type_of 查表不含
            # 存活态故单独立谓词。目标解析与 actor_type_of 同通道，查无/已离场/放逐返回 0.0
            # ——false-y 安全缺省同口径）
            st2 = _lookup(target)
            if st2 is None:
                # 关卡实例 actor_id 可带 "__<stage>" 后缀；精确查无后按模板基础 ID 回查。
                base = str(target)
                st2 = next((st for st in self._engine.state.actors.values()
                            if st.actor.actor_id.split("__", 1)[0] == base), None)
            if st2 is None:
                return 0.0
            return 1.0 if (st2.alive and not st2.banished) else 0.0

        def hp_of(target: Any) -> float:
            # 目标当前 HP（跨 actor 面板读取——遐蝶 1140703 死龙替身阈值判定族；
            # 目标解析与 actor_type_of 同通道，查无返回 0.0（false-y 安全缺省同口径）
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.current_hp)

        def max_hp_of(target: Any) -> float:
            # 目标有效生命上限（跨 actor 面板读取——昔涟 1141503 忆灵 HP% 同步判定族；
            # effective 口径，与 $self.max_hp 同通道；查无返回 0.0（false-y 安全缺省同口径）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            return float(self._engine.pipeline.effective_stats(st2)["hp"])

        def energy_of(target: Any) -> float:
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.current_energy)

        def max_energy_of(target: Any) -> float:
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.actor.stats.max_energy)

        def special_sp_of(target: Any) -> float:
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.special_sp)

        def max_special_sp_of(target: Any) -> float:
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.actor.stats.max_special_sp)

        def toughness_of(target: Any) -> float:
            # 目标当前韧性（ActorState.toughness 直读；目标解析与 hp_of 同通道，查无返回 0）。
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(st2.toughness)

        def stance_count_of(target: Any) -> float:
            st2 = _lookup(target)
            return 0.0 if st2 is None else float(len(st2.extra_bars) + 1)

        def _side_alive(st2: ActorState, team: str) -> list:
            want_enemy = str(team) == "dark"
            return [s for s in self._engine.state.actors.values()
                    if s.alive and self._engine._is_enemy(s.actor) == want_enemy]

        def has_pending_one_more(target: Any) -> float:
            """目标是否有挂起的额外回合（ByTurnOwnerHasPendingOneMore 直译通道）。"""
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            handle = self._engine.scheduler._handles.get(st2.actor.actor_id)
            return 1.0 if any(h == handle for h, _kind in self._engine.scheduler._extra_queue) else 0.0

        def battle_event_exists(event_id: Any) -> float:
            """EventID 是否已注册（ByCompareBattleEventID 直译通道）。"""
            return 1.0 if int(event_id) in self._engine.battle_events else 0.0

        def unique_target(name: Any) -> str:
            from hsr_nous.sim.target_algebra import unique_target_id
            return unique_target_id(self._engine, name, st)

        def turn_owner_of() -> str:
            """当前回合归属者 actor_id（ByIsTurnOwnerEntity 全语境直译通道）。"""
            return str(getattr(self._engine, "_current_turn_actor_id", ""))

        def stage_id() -> Any:
            raw = str(self._engine.encounter.encounter_id)
            return float(raw) if raw.isdigit() else raw

        def wave_index() -> float:
            """当前波次索引（CurWaveIndex 直译通道，与引擎 current_wave 同值）。"""
            return float(self._engine.current_wave)

        def position_of(target: Any, team: Any = "dark") -> float:
            # 站位索引（同侧存活列表序，1 起）——与 blast 相邻判定同口径（存活列表 ±1）。
            # team='dark' 敌方 / 'light' 我方；目标不在该侧/查无返回 0（false-y 安全缺省）。
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            for i, s in enumerate(_side_alive(st2, str(team))):
                if s.actor.actor_id == st2.actor.actor_id:
                    return float(i + 1)
            return 0.0

        def neighbor_of(reference: Any, offset: Any) -> str:
            """参照单位在同侧存活序中偏移 offset 的邻居 actor_id（左邻=-1/右邻=+1）。
            CasterLeft/RightEntity 等谓词目标别名的直译通道；无此邻返回 ""（安全缺省）。"""
            st_r = _resolve(reference)
            if st_r is None:
                return ""
            team = "dark" if self._engine._is_enemy(st_r.actor) else "light"
            pos = position_of(st_r, team)
            if pos <= 0:
                return ""
            want = int(pos + int(offset))
            for s2 in self._engine.state.actors.values():
                if s2.alive and self._engine._is_enemy(s2.actor) == self._engine._is_enemy(st_r.actor)                         and position_of(s2, team) == want:
                    return s2.actor.actor_id
            return ""

        def position_delta(target: Any, reference: Any) -> float:
            """目标与参照的同侧站位差（存活列表序差）——CasterLeft/RightEntity 等
            左右邻谓词的直译通道；不同侧/查无返回 0（false-y 安全缺省）。"""
            st_t, st_r = _resolve(target), _resolve(reference)
            if st_t is None or st_r is None:
                return 0.0
            if self._engine._is_enemy(st_t.actor) != self._engine._is_enemy(st_r.actor):
                return 0.0
            team = "dark" if self._engine._is_enemy(st_r.actor) else "light"
            return position_of(st_t, team) - position_of(st_r, team)

        def side_size(target: Any, team: Any = "dark") -> float:
            # 该侧存活单位数（position_of 的右端点参照；目标解析同通道）。
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            return float(len(_side_alive(st2, str(team))))

        def resource_of(target: Any, resource_id: Any) -> float:
            # 目标自定义资源当前值（跨 actor 资源读取唯一通道——长夜月 1413 忆灵技读忆师
            # Memoria 族（§22.4"首个真实实例到达时再收"收编）；目标解析与 hp_of 同通道，
            # 查无 actor/无该资源返回 0.0（false-y 安全缺省同口径）；
            # punchline/certified_banger 经 engine._resource_value 重定向（21_elation §21.7）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            return self._engine._resource_value(st2, str(resource_id))

        def dynamic_of(target: Any, dynamic_key: Any) -> float:
            # ConfigAI 动态值读取（运行态/核定初值/缺省规则与解释器同通道）。
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            from hsr_nous.sim.enemy_ai import config_ai_dynamic_value
            return config_ai_dynamic_value(self._engine, st2.actor.actor_id, str(dynamic_key))

        def max_skill_points() -> float:
            return float(self._engine._sp_max())

        def mechanic_chance(p: Any) -> float:
            # 机制概率判定（可变概率变量通道——概率=自定义资源（0-1），本函数只裁判：
            # roll 真掷 / expected ≥0.5 生效（银狼 LV.999 Top Loot Box 族；bool→1.0/0.0）
            return 1.0 if self._engine.pipeline.mechanic_chance(float(p)) else 0.0

        def roll(key: Any) -> float:
            # 执行级随机绑定（23 §23.15）：effect 域首调采样一次（消耗主流 pipeline.rng）
            # 绑定当前帧、后续读取零消耗；condition（快照）域（_roll_readonly）只许读
            # 已绑定键、读未绑定显式报错——condition 无副作用的纯洁性不破；无活动
            # 执行帧（策略/available_if 等决策期求值）显式报错——roll 只活在行动执行内。
            # 绑定不跨帧提交合并（frame.py docstring）。
            frame = self._engine.current_frame
            name = _scoped_roll_key(key, payload)
            if frame is None:
                raise ExpressionError(
                    f"roll({name!r}) 需要活动执行帧——仅行动执行内的 effect 表达式可用")
            if _roll_readonly:
                return frame.roll_read(name)
            sampler = (self._engine.pipeline.rng.random
                       if self._engine.pipeline.mode == MODE_ROLL
                       else lambda: math.nextafter(0.5, 0.0))
            return frame.roll_bind(name, sampler)

        def count_team(path: Any = "", group: Any = "") -> float:
            # 队伍编成计数（按命途——长夜月 1413103 变档/昔涟 1415102 进战追忆族；
            # 口径钉：含阵亡编成口径，engine._count_team_group 单漏斗）；
            # group 参（2026-09-10）：分组计数，与 path 同给=析取（"黄金裔或「记忆」命途"族）
            return self._engine._count_team_group(str(path), str(group))

        def in_group(target: Any, group: Any) -> float:
            # 目标是否属于指定分组（03_actor §3.1——faction:xxx 查 actor.groups 声明表；
            # path:<name> 按命途自动映射；黄金裔析取/阵营过滤族）。目标解析与 actor_type_of
            # 同通道，查无 actor 返回 0.0（false-y 安全缺省同口径）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            return 1.0 if self._engine._actor_in_group(st2, str(group)) else 0.0

        def count_modifier(*modifier_ids: Any, side: Any = "ally") -> float:
            # 持有任一指定 modifier 的存活单位数；多 ID 是 OR，不重复计同一单位。
            side_name = str(side)
            if side_name not in {"ally", "enemy", "all"}:
                raise ValueError(f"count_modifier side 非法：{side_name!r}")
            mids = {str(value) for value in modifier_ids}
            total = 0
            for state in self._engine.state.actors.values():
                if not state.alive:
                    continue
                is_enemy = self._engine._is_enemy(state.actor)
                if (side_name == "ally" and is_enemy) or (side_name == "enemy" and not is_enemy):
                    continue
                if any(mod.modifier_id in mids or mod.name in mids
                       for mod in state.all_modifiers()):
                    total += 1
            return float(total)

        def who_has(modifier_id: Any, side: Any = "ally") -> str:
            # 持有指定 modifier 的单位 actor_id（反查寻址——"X 的持有者"动态引用族：
            # 丹恒•腾荒 1414 同袍 stat_of/element_of(who_has('TONGPAO')) 是我方首实例；
            # 炼形者「采气」用 side='enemy' 查询持有【重生】的敌方单位。
            # 编成序（state.actors 插入序）首命中；无持有者返回 ""——下游 stat_of/element_of
            # 查无按各自缺省口径（0.0/""）；side 非法不静默退回我方。
            side_name = str(side)
            if side_name not in {"ally", "enemy", "all"}:
                raise ValueError(f"who_has side 非法：{side_name!r}")
            mid = str(modifier_id)
            for s in self._engine.state.actors.values():
                is_enemy = self._engine._is_enemy(s.actor)
                if (side_name == "ally" and is_enemy) or (side_name == "enemy" and not is_enemy):
                    continue
                if mid in s.modifiers:
                    return s.actor.actor_id
            return ""

        def action_delay_of(target: Any) -> float:
            st2 = _lookup(target)
            scheduler = self._engine.scheduler
            if st2 is None or scheduler is None or st2.actor.actor_id not in scheduler._handles:
                return 0.0
            handle = scheduler.handle_of(st2.actor.actor_id)
            return float(scheduler._remaining[handle] / DISTANCE)

        def character_id(target: Any) -> str:
            """角色实例 ID 的模板段，与 ConfigAI 的 __ 阶段后缀归一化同口径."""
            st2 = _lookup(target)
            return "" if st2 is None else str(st2.actor.actor_id).split("__", 1)[0]

        def monster_id(target: Any) -> str:
            """怪物实例 ID 的模板段，与 character_id 共用同一归一化."""
            return character_id(target)

        def current_turn_state(state: Any) -> float:
            if state == "ModifierPhase1Begin":
                return float(self._engine._modifier_phase1_begin)
            frame = self._engine.current_frame
            if frame is None:
                return 0.0
            if state == "InsertAbilityActionPhase":
                return float(frame.insert and frame.action_type != "ultimate")
            if state == "InsertUltraSkillExecuting":
                return float(frame.insert and frame.action_type == "ultimate")
            return 0.0

        def turn_owner_has_action_in_turn() -> float:
            owner = self._engine._current_turn_actor_id
            frame = self._engine.current_frame
            in_action = frame is not None and frame.actor_id == owner
            return float(bool(owner) and (in_action or self._engine._turn_owner_action_phase_end))

        def is_top_action_delay_target(target: Any, team: Any = "", avatar_only: Any = False) -> float:
            st2 = _resolve(target)
            scheduler = self._engine.scheduler
            if st2 is None or scheduler is None:
                return 0.0
            want_enemy = {"dark": True, "light": False}.get(str(team))
            for actor, _kind, _eta in scheduler.preview():
                if avatar_only and actor.actor_type != "character":
                    continue
                # 死者/放逐者不占行动条首位（F07：preview 只滤冻结，谓词须自滤死亡）
                ast = self._engine.state.actors.get(actor.actor_id)
                if ast is None or not ast.alive or ast.banished:
                    continue
                if want_enemy is None or self._engine._is_enemy(actor) == want_enemy:
                    return float(actor.actor_id == st2.actor.actor_id)
            return 0.0

        def target_unselectable(target: Any, side: Any = "") -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            flags = st2.actor.summon_flags
            if side == "dark":
                return float(not flags.get("enemy_targetable", True))
            if side == "light":
                return float(not flags.get("ally_targetable", True))
            return float(not (flags.get("enemy_targetable", True)
                              and flags.get("ally_targetable", True)))

        def monster_id_equals(target: Any, raw_id: Any) -> float:
            try:
                normalized = str(int(float(raw_id)))
            except (TypeError, ValueError, OverflowError):
                return 0.0
            return 1.0 if character_id(target) == normalized else 0.0

        def monster_unique_id(target: Any) -> float:
            """怪物 UniqueID = 模板 ID // 10（决策卡 #30——UniqueID 值域 ×10 反推模板
            全存在的映射实证）；实例 __ 后缀归一化与 monster_id 同通道，查无/非数值返回 0。"""
            raw = character_id(target)
            return float(int(raw) // 10) if raw.isdigit() else 0.0

        def monster_rank(target: Any) -> float:
            """怪物等级数值，与 ConfigAI 使用同一 policy 与 MONSTER_RANK_VALUES."""
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            policy = self._engine._enemy_policies.get(st2.actor.actor_id)
            return float(MONSTER_RANK_VALUES.get(policy.monster_rank if policy else "", 0))

        def element_of(target: Any) -> str:
            # 目标元素（伤害属性小写 canonical key——动态元素族：丹恒•腾荒 1414 同袍
            # "相应属性"附加伤害的 damage_type 取数源；Actor.element 字段，模板/inline
            # member `element` 键声明）。目标解析与 actor_type_of 同通道，查无 actor/
            # 未声明返回 ""（deal_damage damage_type 表达式求值结果词表闸拦报错）
            st2 = _lookup(target)
            return "" if st2 is None else str(st2.actor.element or "")

        def elation_of(target: Any) -> float:
            # 目标有效面板欢愉度（跨 actor 单键读取——爻光 150204 大吉大利「攻击者欢愉度
            # 低于爻光时用爻光的算」择优族首实例：hook 伤害源恒持有者，攻击者更高时的
            # 择优读取通道；与 hp_of/max_hp_of/stat_of 同族单键读，hook 语境读**全量
            # 面板**（含条件件——大吉大利按攻击者实时面板择优，04_modifier §4.16 防环
            # 域不适用）。目标解析与 element_of 同通道，查无返回 0.0（false-y 安全缺省）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            v = self._engine.pipeline.effective_stats(st2).get("elation", 0.0)
            return float(v) if isinstance(v, (int, float)) else 0.0

        def stat_of(target: Any, stat: Any, no_aura: Any = 0) -> float:
            # 目标面板单键读取（hp_of/max_hp_of 泛化——昔涟 1415103 德谬歌读忆师抗性穿透档族；
            # hook 语境读**全量面板**（04_modifier §4.16 口径钉，与 max_hp_of 同通道）；
            # 目标解析与 hp_of 同通道，查无 actor/无该键返回 0.0（false-y 安全缺省同口径）。
            # no_aura 非零 = 不并光环（德谬歌镜像忆师 HP_P% 专用——忆师池经镜像进忆灵，
            # 光环直辐射忆灵，两侧不双计，2026-09-23）
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            v = self._engine.pipeline.effective_stats(
                st2, _skip_aura=bool(no_aura)).get(str(stat), 0.0)
            return float(v) if isinstance(v, (int, float)) else 0.0

        def base_stat_of(target: Any, stat: Any) -> float:
            # 目标 StatBlock 基础面板（不含 modifier/光环——Ability BaseAttack 直读族首实例：
            # 吞神子嗣 Devour 按 BaseAttack 窃取，不能用 effective ATK 近似）。
            st2 = _lookup(target)
            if st2 is None:
                return 0.0
            field = "def_" if str(stat) == "def" else str(stat)
            value = getattr(st2.actor.stats, field, 0.0)
            return float(value) if isinstance(value, (int, float)) else 0.0

        return {"stacks": stacks, "sum_stacks": sum_stacks,
                "modifier_duration": modifier_duration,
                "modifier_max_stacks": modifier_max_stacks,
                "modifier_dynamic_of": modifier_dynamic_of,
                "enemies_alive": enemies_alive, "has_modifier": has_modifier,
                "has_behavior_flag": has_behavior_flag,
                "modifier_source": modifier_source, "modifier_kind": modifier_kind,
                "count": count, "count_selected": count_selected,
                "unique_sources": unique_sources,
                "mechanic_chance": mechanic_chance, "roll": roll,
                "actor_type_of": actor_type_of,
                "hp_of": hp_of, "max_hp_of": max_hp_of,
                "energy_of": energy_of, "max_energy_of": max_energy_of,
                "special_sp_of": special_sp_of, "max_special_sp_of": max_special_sp_of,
                "max_skill_points": max_skill_points,
                "toughness_of": toughness_of, "stance_count_of": stance_count_of,
                "action_delay_of": action_delay_of,
                "has_pending_one_more": has_pending_one_more,
                "battle_event_exists": battle_event_exists,
                "in_elation_time": lambda: float(self._engine._elation_time_active),
                "turn_owner_action_phase_end": lambda: float(self._engine._turn_owner_action_phase_end),
                "turn_owner_has_action_in_turn": turn_owner_has_action_in_turn,
                "unique_target": unique_target,
                "turn_owner_of": turn_owner_of, "wave_index": wave_index,
                "stage_id": stage_id,
                "position_of": position_of, "side_size": side_size,
                "position_delta": position_delta, "neighbor_of": neighbor_of,
                "resource_of": resource_of,
                "dynamic_of": dynamic_of, "count_team": count_team,
                "stat_of": stat_of, "base_stat_of": base_stat_of, "controlled": controlled,
                "action_disabled": action_disabled, "immune_debuff": immune_debuff,
                "path_of": path_of, "has_summon": has_summon, "in_group": in_group,
                "who_has": who_has, "count_modifier": count_modifier,
                "character_id": character_id, "monster_id": monster_id,
                "monster_id_equals": monster_id_equals, "monster_unique_id": monster_unique_id,
                "monster_rank": monster_rank,
                "element_of": element_of, "elation_of": elation_of,
                "target_unselectable": target_unselectable,
                "is_top_action_delay_target": is_top_action_delay_target,
                "current_turn_state": current_turn_state,
                "broken_of": broken_of,
                "has_debuff": has_debuff, "debuff_count": debuff_count,
                "weakness_count": weakness_count, "has_stat_penalty": has_stat_penalty,
                "has_shield": has_shield, "shielded_count": shielded_count,
                "shield_of": shield_of,
                "dot_count": dot_count, "actor_alive": actor_alive,
                "damageable_enemies": damageable_enemies, "hp_locked": hp_locked,
                "dot_value": dot_value,
                "is_adjacent": is_adjacent, "target_lists_intersect": target_lists_intersect,
                "target_in_selected": target_in_selected,
                "has_weakness": has_weakness, "dot_kind": dot_kind,
                "summoner_of": summoner_of}

    def _modifier_dynamic_value(self, st: ActorState, modifier_id: str, dynamic_key: str) -> float:
        modifier = st.modifiers.get(str(modifier_id))
        if modifier is None:
            return 0.0
        value = modifier.dynamic_values.get(str(dynamic_key), 0.0)
        if not isinstance(value, str):
            return float(value)
        return self._hook_amount(value, st, {
            "modifier_id": modifier.modifier_id, "source": modifier.source_id,
            "target": st.actor.actor_id})

    def _hook_amount(self, raw: Any, st: ActorState, payload: Dict[str, Any],
                     target_st: Optional[ActorState] = None) -> float:
        """hook 数值参数：数值直用；字符串按白名单表达式求值.

        target_st：`$target` 命名空间注入（per-target 求值槽——按目标面板伸缩的效果，
        如星期日终结技"恢复目标能量上限 20%"）；None=无 $target（表达式引用了会
        AttributeError——按 hook 求值失败口径处理，不静默吞）。
        `$last`/`$prev`：effects 链前序快照（`_run_hook_effects` 的实例变量通道，
        链外/首 effect 求值时为空命名空间）。
        """
        if isinstance(raw, (int, float)):
            return float(raw)
        ctx = self._hook_ctx(st, payload)
        if target_st is not None:
            ctx["target"] = _HookSelfNS(self._engine, target_st)
        chain = getattr(self, "_chain_last", None)
        if chain is not None:
            ctx["last"] = ctx["prev"] = types.SimpleNamespace(**chain)
        return float(self._engine._expr.evaluate(
            self._engine._expr.compile(str(raw), layer="effect"),
            ctx,
            functions=self._hook_functions(st, payload),
        ))

    def _event_actor(self, ref: str, payload: Dict[str, Any]) -> Optional[ActorState]:
        """`$event.<字段>` 目标寻址：payload 字段（actor_id）→ ActorState（事件目标族通用）."""
        aid = payload.get(ref.split(".", 1)[1])
        return self._engine.state.actors.get(str(aid)) if aid is not None else None

    def _hook_target_states(self, sel: Any, st: ActorState, payload: Dict[str, Any],
                            *, allow_sample: bool = True) -> List[ActorState]:
        """hook effect 目标选择器统一解析（目标代数求值器）.

        allow_sample=False：计数/条件快照域禁掷骰（透传 eval_algebra），选中个数与
        roll 全等但不推进主随机流——count_selected 唯一解析路径（不再自实现目标代数）。

        字符串 = 脱糖别名（`_HOOK_SELECTOR_ALIASES`，模板零改动）；dict = 代数直写
        （`{pool, where, order_by, index, take, mode}`）；`$event.targets` / `$event.<字段>` 为
        payload 寻址通道（池解析归 target_algebra.resolve_pool）。
        代数 `where`/`order_by` 语境注入 `$event`（与 hook condition 同 payload 命名空间——
        "召唤物 of $event.target" 寻址族，2026-09-09 接线）。
        """
        from hsr_nous.sim.target_algebra import (
            _HOOK_SELECTOR_ALIASES, eval_algebra, resolve_pool,
        )
        pseudo = self._engine._pseudo_entity_state(str(sel))
        if pseudo is not None:
            return [pseudo]
        event_ns = types.SimpleNamespace(**{"insert": False, "cancel": False, **payload})
        # $self 注入=hook 持有者（"装备者的忆灵"寻址族——$it.summoner_id == $self.actor_id，
        # 与 hook condition/cond 光环域同口径；policy 通道无持有者语义不注）
        self_ns = _HookSelfNS(self._engine, st)
        if isinstance(sel, dict) and "concat" in sel:
            children = sel["concat"]
            if not isinstance(children, list) or not children:
                raise ValueError("TargetConcat 的 concat 须为非空目标数组")
            spec = dict(sel)
            spec.pop("concat")
            pool = [target for child in children
                    for target in self._hook_target_states(child, st, payload, allow_sample=allow_sample)]
            return eval_algebra(spec, pool=pool, engine=self._engine,
                                expr=self._engine._expr, event_ns=event_ns,
                                self_ns=self_ns, allow_sample=allow_sample)
        if isinstance(sel, dict):
            spec = dict(sel)
            pool = resolve_pool(spec.pop("pool", "enemies"),
                                engine=self._engine, st=st, payload=payload,
                                include_dead=bool(spec.get("include_dead", False)),
                                include_unselectable=bool(spec.get("include_unselectable", False)))
            return eval_algebra(spec, pool=pool, engine=self._engine,
                                expr=self._engine._expr, event_ns=event_ns,
                                self_ns=self_ns, allow_sample=allow_sample)
        sel = str(sel)
        if sel.startswith("$event."):
            # payload 寻址通道（$event.targets / $event.hit_targets / $event.<字段>）——
            # 池解析归 resolve_pool，无 where/order/take（直返）
            return resolve_pool(sel, engine=self._engine, st=st, payload=payload)
        if sel == "other_allies":
            spec = dict(_HOOK_SELECTOR_ALIASES[sel])
            pool = [s for s in resolve_pool(spec.pop("pool"), engine=self._engine,
                                            st=st, payload=payload) if s is not st]
            return eval_algebra(spec, pool=pool, engine=self._engine,
                                expr=self._engine._expr, event_ns=event_ns,
                                self_ns=self_ns, allow_sample=allow_sample)
        spec = _HOOK_SELECTOR_ALIASES.get(sel)
        if spec is None:
            # 未知选择器编译期就该炸（build_compiler 白名单）；走到这里=绕过编译层，同口径炸
            raise ValueError(
                f"未知 hook target 选择器 {sel!r}"
                f"（合法集合：{sorted(_HOOK_SELECTOR_ALIASES)} + '$event.<字段>' + 代数 dict）"
            )
        spec = dict(spec)
        pool = resolve_pool(spec.pop("pool"), engine=self._engine, st=st, payload=payload)
        return eval_algebra(spec, pool=pool, engine=self._engine,
                            expr=self._engine._expr, event_ns=event_ns,
                            self_ns=self_ns, allow_sample=allow_sample)

    def _emit_heal_settled(self, st: ActorState, t2: ActorState, result: Any,
                           payload: Dict[str, Any]) -> float:
        """治疗结算后段统一通道（heal_self / drain_hp 反哺 / heal 三处同口径——差异仅
        目标源/参数/healed_total 记账，故收编；pipeline.heal 调用本身留各调用方）：
        actual/excess 读数 → on_hp_increase 发射（溢出量 = 拟回 − 实际；excess > 0 即便
        actual == 0（满血被奶）也发——载荷语义「受到治疗（含溢出）」，岐黄要论"治疗溢出"
        族判定点，消费者按 amount/excess 自取，0 值无害；action_id = 引发本治疗的行动归属，
        hook 链 payload 透传——战技多跳/终结技奶/受击奶可分辨，1211 E4 族）→ 月茧
        「受到治疗」解除（mechanics 11 §11.1——按实际回血判定，满血溢出奶不算）。
        返回 actual（heal 处 healed_total 记账由调用方自累）。
        """
        actual = float(result.node.get("actualAmount", 0.0))
        excess = max(0.0, float(result.value) - actual)
        if actual > 0 or excess > 0:
            self._engine.bus.emit("on_hp_increase", {
                "amount": actual, "excess": excess, "source": st.actor.actor_id,
                "reason": "heal", "target": t2.actor.actor_id,
                "action_id": str(payload.get("action_id") or payload.get("action") or "")},
                self._engine.state)
            if actual > 0 and MOON_COCOON_ID in t2.modifiers:
                self._engine._remove_modifier(t2, MOON_COCOON_ID, "cocoon_release")
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: {t2.actor.name} 的月茧解除（受到治疗）")
        return actual

    def _run_hook_effect(self, st: ActorState, eff: Dict[str, Any], payload: Dict[str, Any],
                         updates: Optional[Dict[str, Any]] = None) -> None:
        condition = eff.get("condition")
        if condition is not None and not bool(self._hook_amount(condition, st, payload)):
            return
        t = eff.get("effect_type")
        handler = getattr(self, f"_h_{t}", None)
        if handler is None:
            raise ValueError(f"未知 effect_type {t!r}，已实现集合见 sim_schema/effect_types.py")
        handler(st, eff, payload, updates)

    def _h_cancel_event(self, st, eff, payload, updates):
        # waterfall 事件取消（免死族；updates 进 waterfall 链）
        if updates is not None:
            updates["cancel"] = True
        return


    def _h_modify_amount(self, st, eff, payload, updates):
        # waterfall 事件 amount 改写（抵扣/减免族——与 cancel_event 具名对偶，05_effects
        # §modify_amount：0=全额免扣、中间值=部分抵扣；表达式同 _hook_amount 通道；
        # emit 事件上写无效果——updates 仅 waterfall 链非 None）
        if updates is not None:
            updates["amount"] = self._hook_amount(eff.get("amount", 0), st, payload)
        return


    def _h_gain_resource(self, st, eff, payload, updates):
        rid = eff["resource_id"]
        # 统一入口（16 值块 v1：max 截断/bank 溢出/provenance 来源记账）。
        # source：provenance 来源覆写（昔涟 Future"消耗来源=行动队友"族——'$event.<字段>'
        # 事件寻址或字面 actor_id；缺省 = hook 持有者自身）。
        # target：跨 actor 写通道（05_effects §5.3——缺省 self 现状不变；显式给=对解析目标
        # 逐各写，amount 按 $target 逐目标求值，gain_energy 同先例；与 source 正交——
        # 写谁的面板 ≠ 谁触发的；昔涟 1141519 tally 加账/1141524 忆质+1 首实例）
        src_ref = str(eff.get("source", ""))
        if src_ref.startswith("$event."):
            src_st = self._event_actor(src_ref, payload)
            source_id = src_st.actor.actor_id if src_st is not None else st.actor.actor_id
        elif src_ref:
            source_id = src_ref
        else:
            source_id = st.actor.actor_id
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            amt = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            self._engine._gain_resource(t2, rid, amt, source_id=source_id)


    def _h_gain_skill_point(self, st, eff, payload, updates):
        amount = int(self._hook_amount(eff.get("amount", 0), st, payload))
        # overflow_to（花火 1130603 溢出记录族）：恢复超出上限的部分转记入指定资源
        # （「记录溢出的战技点数」——sp_overflow 池；池上限由资源声明 max 截断）
        overflow_to = str(eff.get("overflow_to", "") or "")
        if overflow_to and amount > 0:
            cur = self._engine.state.skill_points
            cap = self._engine._sp_max()
            overflow = max(0, cur + amount - cap)
            if overflow > 0:
                self._engine._gain_resource(st, overflow_to, overflow)
        self._engine._adjust_skill_points(amount, reason="hook")


    def _h_set_skill_point(self, st, eff, payload, updates):
        value = self._hook_amount(eff.get("amount", 0), st, payload)
        if value < 0 or int(value) != value:
            raise ValueError("set_skill_point 的 amount 必须是非负整数")
        self._engine._adjust_skill_points(
            int(value) - self._engine.state.skill_points, reason="set")


    def _h_set_sp_max(self, st, eff, payload, updates):
        # 战技点上限覆写（花火天赋「上限额外增加」族——state.sp_max_override 挂点
        # （engine._sp_max 读数端预留已久），本 effect=首个实例）
        self._engine.state.sp_max_override = int(
            self._hook_amount(eff.get("amount", 0), st, payload))


    def _h_refill_skill_point(self, st, eff, payload, updates):
        # 溢出池回补（花火 1130603 族）：战技点 < 上限时从 from_resource 记录池补足
        # 至上限（「消耗记录值为我方恢复战技点，直至恢复至上限」；池耗尽即止——
        # 模板挂在 on_turn_end（我方角色）触发）
        rid = str(eff.get("from_resource", ""))
        if rid:
            need = int(self._engine._sp_max() - self._engine.state.skill_points)
            have = int(st.resources.get(rid, 0.0))
            take = min(need, have)
            if need > 0 and take > 0:
                st.resources[rid] = st.resources.get(rid, 0.0) - take
                self._engine._adjust_skill_points(take, reason="refill")
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: {st.actor.name} 消耗溢出记录 "
                    f"{take} 点为我方恢复战技点（余 {st.resources[rid]:.0f}）")


    def _h_gain_energy(self, st, eff, payload, updates):
        sel = eff.get("target", "self")
        # err_exempt：具名豁免不乘 ERR（mechanics 05 §5.3 清单：停云/藿藿/镜中故我族）
        err_exempt = bool(eff.get("err_exempt", False))
        # target 词表按 05_effects §回复能量收窄为二值 + 事件寻址通道
        # （'$event.<字段>'：停云/星期日单充族——实例已到达（131303 恢复目标能量上限
        # 20%，amount 按目标面板逐目标求值，$target 命名空间）；其余选择器值
        # 与其他选择器同纪律炸（曾 else 静默当全体：highest_hp 写成全体充能的雷）；
        # **dict 走目标代数通用通道**（藿藿 1217 终结技"excluding this unit"排自身首实例
        # ——代数 where 槽是排他语义唯一承载，2026-09-14 接线）
        if isinstance(sel, dict):
            targets = self._hook_target_states(sel, st, payload)
        elif str(sel) == "self":
            targets = [st]
        elif str(sel) == "all_allies":
            targets = self._engine._allies_alive()
        elif str(sel).startswith("$event."):
            targets = self._hook_target_states(sel, st, payload)
        else:
            raise ValueError(
                f"gain_energy 的 target 非法值 {sel!r}"
                f"（合法集合：['all_allies', 'self'] + '$event.<字段>' + 代数 dict，"
                f"见 05_effects §回复能量）")
        for t2 in targets:
            # 放逐=状态冻结：能量不涨（全局机制（军功充能/奇袭族）照跑，个人面板冻结——
            # 裁决边界：充能照跑、能量冻结、终结技禁放）
            if t2.banished:
                continue
            amt = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            self._engine._grant_energy(t2, amt, source=st.actor.actor_id,
                                       action_id=None, reason="effect", err_exempt=err_exempt)


    def _h_consume_energy(self, st, eff, payload, updates):
        sel = eff.get("target", "self")
        if isinstance(sel, dict):
            targets = self._hook_target_states(sel, st, payload)
        elif str(sel) == "self":
            targets = [st]
        elif str(sel) == "all_allies":
            targets = self._engine._allies_alive()
        elif str(sel).startswith("$event."):
            targets = self._hook_target_states(sel, st, payload)
        else:
            raise ValueError(
                f"consume_energy 的 target 非法值 {sel!r}"
                f"（合法集合：['all_allies', 'self'] + '$event.<字段>' + 代数 dict，"
                f"见 05_effects §消耗能量）")
        for t2 in targets:
            if t2.banished:
                continue
            amt = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            if amt < 0:
                raise ValueError("consume_energy 的 amount 必须非负")
            before = t2.current_energy
            self._engine.pipeline.consume_energy(t2, amt)
            self._engine._emit_energy_change(
                t2, before, source=st.actor.actor_id, reason="effect")


    def _h_modify_special_sp(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            amount = self._hook_amount(eff["amount"], st, payload, target_st=t2)
            maximum = max(0.0, float(t2.actor.stats.max_special_sp))
            t2.special_sp = min(maximum, max(0.0, t2.special_sp + amount))


    def _h_set_energy(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            if t2.banished:
                continue
            amount = self._hook_amount(eff["amount"], st, payload, target_st=t2)
            if amount < 0:
                raise ValueError("set_energy 的 amount 必须非负")
            before = t2.current_energy
            t2.current_energy = amount
            self._engine._emit_energy_change(
                t2, before, source=st.actor.actor_id, reason="set")


    def _h_set_resource(self, st, eff, payload, updates):
        rid = eff["resource_id"]
        # 设值 = 差量走统一入口（同拿 clamp/provenance 口径）；target 跨 actor 写通道
        # 同 gain_resource（风堇 1140901 忆灵侧清 tally——账挂忆师——首实例）
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            target = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            # 差量现值走统一读取口径（punchline/certified_banger 重定向——
            # 队伍账/条目列表；直读 st.resources 会拿持有者空账算错差量）
            self._engine._gain_resource(t2, rid, target - self._engine._resource_value(t2, rid))


    def _h_emit_phase_custom_event(self, st, eff, payload, updates):
        phase_event = str(eff["phase_event"])
        if phase_event not in {"monster_phase_change_begin", "monster_phase_change_end"}:
            raise ValueError(f"未知阶段自定义事件 {phase_event!r}")
        targets = self._hook_target_states(
            {"pool": "all_with_battle_events", "include_unselectable": True}, st, payload)
        target_ids = [t2.actor.actor_id for t2 in targets
                      if t2.current_hp > 0 or eff.get("include_limbo", False)]
        param_entity = st.actor.actor_id
        if "param_entity" in eff:
            selected = self._hook_target_states(eff["param_entity"], st, payload)
            param_entity = selected[0].actor.actor_id if selected else ""
        if phase_event == "monster_phase_change_begin":
            self._engine.bus.emit("monster_phase_change_begin", {
                "actor": st.actor.actor_id, "param_entity": param_entity,
                "targets": target_ids}, self._engine.state)
        else:
            self._engine.bus.emit("monster_phase_change_end", {
                "actor": st.actor.actor_id, "param_entity": param_entity,
                "targets": target_ids}, self._engine.state)


    def _h_emit_modifier_custom_event(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            self._engine.bus.emit("modifier_custom_event", {
                "source": st.actor.actor_id, "target": t2.actor.actor_id,
                "event_type": int(eff["event_type"]),
                "dynamic_key": str(eff.get("dynamic_key") or ""),
                "value": self._hook_amount(eff.get("value", 0), st, payload, target_st=t2),
            }, self._engine.state)


    def _h_create_battle_event(self, st, eff, payload, updates):
        event_id = int(eff["event_id"])
        actor_id = f"$battle_event:{event_id}"
        actor_state = ActorState(actor=Actor(
            actor_id=actor_id, name=f"Battle Event {event_id}", actor_type="battle_event",
            summoner_id=st.actor.actor_id,
            stats=StatBlock(hp=1, spd=100, max_energy=0)), current_hp=1.0)
        self._engine.battle_events[event_id] = {
            "team": str(eff.get("team") or ""), "created": True,
            "actor_state": actor_state}
        runtime = self._engine._enemy_policy_state.setdefault("$level", {
            "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
            "dynamic_values": {}, "dynamic_targets": {}})
        runtime.setdefault("dynamic_targets", {})[actor_id] = actor_id
        self._engine.bus.emit("battle_event_create", {
            "actor": actor_id, "event_id": event_id,
            "source": st.actor.actor_id, "team": str(eff.get("team") or "")}, self._engine.state)


    def _h_set_dynamic_target(self, st, eff, payload, updates):
        targets = self._hook_target_states(eff.get("target", "self"), st, payload)
        if eff.get("scope") == "unique_name":
            if len(targets) != 1:
                raise ValueError("UniqueName 绑定要求恰好一个目标")
            runtime = self._engine._enemy_policy_state.setdefault("$level", {
                "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
                "dynamic_values": {}, "dynamic_targets": {}})
            runtime.setdefault("dynamic_targets", {})[str(eff["dynamic_key"])] = \
                targets[0].actor.actor_id
        else:
            owners = self._hook_target_states(
                eff.get("owner", eff.get("target", "self")), st, payload)
            for owner in owners:
                for t2 in targets:
                    runtime = self._engine._enemy_policy_state.setdefault(owner.actor.actor_id, {
                        "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
                        "dynamic_values": {}, "dynamic_targets": {}})
                    runtime.setdefault("dynamic_targets", {})[str(eff["dynamic_key"])] = \
                        t2.actor.actor_id


    def _h_loop_effects(self, st, eff, payload, updates):
        if "condition" in eff:
            # 条件驱动循环（ConditionLoopExecuteTaskList，#544）：逐轮重求值，
            # 读得到帧内写后读；谓词不收敛撞安全上限显式报错，不静默截断。
            condition = eff["condition"]
            index = 0
            while bool(self._hook_amount(condition, st, payload)):
                if index >= 10000:
                    raise ValueError("条件循环超过安全上限 10000 轮（谓词未收敛）")
                nested_payload = {**payload, "loop_index": index}
                for nested in eff.get("effects") or []:
                    self._run_hook_effect(st, nested, nested_payload)
                index += 1
            return
        count = self._hook_amount(eff["count"], st, payload)
        if not math.isfinite(count) or count < 0 or int(count) != count:
            raise ValueError(f"动态循环次数必须是非负有限整数，得到 {count!r}")
        if count > 10000:
            raise ValueError(f"动态循环次数 {int(count)} 超过安全上限 10000")
        for index in range(int(count)):
            nested_payload = {**payload, "loop_index": index}
            for nested in eff.get("effects") or []:
                self._run_hook_effect(st, nested, nested_payload)


    def _h_record_formation_index(self, st, eff, payload, updates):
        functions = self._hook_functions(st, payload)
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            team = "dark" if self._engine._is_enemy(t2.actor) else "light"
            position = functions["position_of"](t2, team)
            self._run_hook_effect(st, {
                "effect_type": "set_dynamic_value", "target": "$level",
                "dynamic_key": f"_FormationRecord:{team}", "amount": position,
            }, payload)


    def _h_set_dynamic_value(self, st, eff, payload, updates):
        key = str(eff["dynamic_key"])
        # amount_target 只提供 $target 求值语境，写入仍由 target 决定；
        # 每个读取候选依次求值并写入，空候选不写，多候选后者覆盖前者。
        # 执行帧内写入进帧覆盖层（写后读：同执行内立即可读，提交时才落已提交态、
        # 异常随帧回滚丢弃）；帧外维持直写已提交态（§23.15 四层读取链）。
        frame = self._engine.current_frame
        read_targets = (self._hook_target_states(eff["amount_target"], st, payload)
                        if "amount_target" in eff else None)
        if read_targets is not None and not read_targets:
            return
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            runtime = self._engine._enemy_policy_state.get(t2.actor.actor_id)
            if runtime is None:
                # 同一表按任意 actor_id 保存动态值；是否有 ConfigAI policy 与读写资格无关。
                runtime = self._engine._enemy_policy_state.setdefault(t2.actor.actor_id, {
                    "seq_idx": 0, "cooldown_left": {}, "current_phase": 1,
                    "dynamic_values": {},
                })
            for amount_st in read_targets if read_targets is not None else [t2]:
                value = self._hook_amount(eff["amount"], st, payload, target_st=amount_st)
                if key == "current_phase":
                    if not float(value).is_integer():
                        raise ValueError(f"current_phase 必须为整数，得到 {value!r}")
                    new_phase = int(value)
                    old_phase = (frame.writes.get(t2.actor.actor_id, {}).get(
                        "current_phase", runtime["current_phase"])
                        if frame is not None else runtime["current_phase"])
                    if frame is not None:
                        if new_phase != old_phase:
                            frame.record_phase_change(
                                t2.actor.actor_id, int(old_phase), new_phase)
                        frame.write(t2.actor.actor_id, key, new_phase)
                    else:
                        if new_phase != old_phase:
                            self._engine.bus.emit("monster_phase_changed", {
                                "actor": t2.actor.actor_id,
                                "from_phase": old_phase, "to_phase": new_phase}, self._engine.state)
                        runtime["current_phase"] = new_phase
                elif frame is not None:
                    frame.write(t2.actor.actor_id, key, float(value))
                else:
                    runtime.setdefault("dynamic_values", {})[key] = float(value)


    def _h_set_modifier_dynamic_value(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            modifier = t2.modifiers.get(str(eff["modifier_id"]))
            if modifier is None:
                continue
            value = self._hook_amount(eff["amount"], st, payload, target_st=t2)
            if eff.get("mode", "set") == "add":
                value += self._modifier_dynamic_value(
                    t2, modifier.modifier_id, str(eff["dynamic_key"]))
            modifier.dynamic_values[str(eff["dynamic_key"])] = float(value)


    def _h_bind_roll(self, st, eff, payload, updates):
        # 执行帧共享掷骰绑定锚（23 §23.15 / 05_effects §bind_roll）：编译器概率分支
        # （ByRandomChance/RandomConfig）翻译的前置绑定——绑定值 = roll(roll_key) × scale。
        # roll 模式采 pipeline.rng（消耗主流一次）；expected 模式绑 0.5 的下邻浮点
        # （与 mechanic_chance 的 p>=0.5 期望口径逐比特一致，两通道不许两种期望语义）。
        # 帧外调用显式报错（roll 只活在行动执行内）。
        frame = self._engine.current_frame
        if frame is None:
            raise ExpressionError(
                f"bind_roll({eff.get('roll_key')!r}) 需要活动执行帧"
                f"——仅行动执行内的 effect 表达式可用")
        scale = self._hook_amount(eff["scale"], st, payload) if "scale" in eff else 1.0
        key = _scoped_roll_key(eff["roll_key"], payload)
        if self._engine.pipeline.mode == MODE_ROLL:
            frame.roll_bind(key, lambda: self._engine.pipeline.rng.random() * scale)
        else:
            frame.roll_bind(key, lambda: math.nextafter(0.5, 0.0) * scale)


    def _h_refund_bank(self, st, eff, payload, updates):
        # bank 返还（16 §16.12 糖展开原语）：<rid>_bank → <rid> clamp 回填——
        # ③防递归：from_bank=True（不回流）；多出作废（银行全清，钉字面口径）
        rid = str(eff["resource_id"])
        bank_rid = f"{rid}_bank"
        bank_cur = st.resources.get(bank_rid, 0.0)
        if bank_cur > 0:
            moved = self._engine._gain_resource(st, rid, bank_cur, from_bank=True)
            st.resources[bank_rid] = 0.0
            if moved < bank_cur:
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: {st.actor.name} 的 {bank_rid}"
                    f" 返还截断——回填 {moved}，超出上限部分 {bank_cur - moved} 作废")
            self._engine.bus.emit("on_resource_gain", {
                "actor": st.actor.actor_id, "resource_id": bank_rid,
                "amount": -bank_cur, "current": 0.0}, self._engine.state)


    def _h_heal_self(self, st, eff, payload, updates):
        ratio = self._hook_amount(eff.get("ratio", 0), st, payload)
        # 走管线统一治疗路径（rulebook heal 式：hp_scaling=ratio × 施放者有效 HP，
        # 吃治疗源 heal_bonus（召唤物施放归主人面板——2026-09-21 裁决）+ 受疗者
        # incoming_heal——mechanics 01 §1.3）
        result = self._engine.pipeline.heal(st, st, hp_scaling=ratio)
        # 后段（on_hp_increase 发射 + 月茧解除）= _emit_heal_settled 统一通道
        self._emit_heal_settled(st, st, result, payload)


    def _h_set_hp_to_percent(self, st, eff, payload, updates):
        # B9 原语：HP 设为生命上限×比例（刃 120503/复活族效果）；可致死（走 _check_death 四层）。
        # target 走通用选择器通道（1217 E2 免死"队友回复至 50%"首实例——旧实现无视
        # target 键恒作用 hook 持有者（1205 刃 target:self 恰好自洽未暴露）；上限读
        # 被 set 者有效面板）
        source_id = st.actor.actor_id
        death_source_id = ""
        source_ref = str(eff.get("source") or "")
        if source_ref:
            if not source_ref.startswith("modifier:"):
                raise ValueError(f"set_hp_to_percent 的 source 无法解析：{source_ref!r}")
            held = st.modifiers.get(source_ref.split(":", 1)[1])
            source = (self._engine.state.actors.get(held.source_id)
                      if held is not None else None)
            if source is None:
                raise ValueError(f"set_hp_to_percent 的 source 无法解析：{source_ref!r}")
            source_id = source.actor.actor_id
            death_source_id = source_id
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            pct = self._hook_amount(eff.get("percent", eff.get("amount", 0)), st, payload,
                                    target_st=t2)
            max_hp = float(self._engine.pipeline.effective_stats(t2)["hp"])
            old_hp = t2.current_hp
            t2.current_hp = max(0.0, min(max_hp, max_hp * pct))
            if t2.current_hp < old_hp:
                # HP 下降发射点（HP 消耗族——mechanics 11 §11.3；reason='set_hp'，词表冻结见 _execute_action）
                self._engine.bus.emit("on_hp_decrease", {
                    "amount": old_hp - t2.current_hp, "source": source_id,
                    "reason": "set_hp", "target": t2.actor.actor_id}, self._engine.state)
            if t2.current_hp <= 0:
                self._engine._check_death(t2, death_source_id)


    def _h_drain_hp(self, st, eff, payload, updates):
        # 生命流失/汲取（05_effects §生命汲取/生命流失 v1 收编——遐蝶耗血/小伊卡反哺族）：
        # 每目标实际流失 = min(amount, 当前 HP - floor)（floor 保底耗不致死，缺省 0 可致死）；
        # 发 on_hp_decrease（reason='drain'，词表冻结见 _execute_action）；不是伤害——
        # 不走 before_take_damage/护盾/总伤记账；drain_ratio × 总额走统一治疗管线。
        # before_drain 可改写口（2026-09-10 收编——遐蝶 E2 炽意抵扣首实例）：逐目标扣减前
        # 走 waterfall（modify_amount 改写扣量 0=免扣 / cancel 整笔跳过；payload action_id
        # 继承触发上下文——焰息耗血=1140702 族定位锚），改写/取消后无扣减不发 on_hp_decrease
        floor = self._hook_amount(eff.get("floor", 0), st, payload)
        drained_total = 0.0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            amt = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            wp = self._engine.bus.waterfall("before_drain", {
                "source": st.actor.actor_id, "target": t2.actor.actor_id,
                "amount": amt, "floor": floor, "reason": "drain",
                "action_id": str(payload.get("action_id") or "")}, self._engine.state)
            if wp.get("cancel"):
                continue   # 抵扣整笔取消——无扣减不发射（遐蝶 E2 炽意全额抵扣族）
            amt = float(wp.get("amount", amt))
            actual = min(amt, max(0.0, t2.current_hp - floor))
            if actual <= 0:
                continue
            t2.current_hp -= actual
            drained_total += actual
            # HP 下降发射点（HP 消耗族——mechanics 11 §11.3；reason='drain'，spec 钉死）
            self._engine.bus.emit("on_hp_decrease", {
                "amount": actual, "source": st.actor.actor_id,
                "reason": "drain", "target": t2.actor.actor_id}, self._engine.state)
            if t2.current_hp <= 0:
                self._engine._check_death(t2, st.actor.actor_id)
        ratio = self._hook_amount(eff.get("drain_ratio", 1.0), st, payload)
        if ratio > 0 and drained_total > 0:
            for t2 in self._hook_target_states(eff.get("heal_target", "self"), st, payload):
                result = self._engine.pipeline.heal(st, t2, drained_total * ratio)
                # 反哺治疗后段 = _emit_heal_settled 统一通道（与 heal 同口径）
                self._emit_heal_settled(st, t2, result, payload)
        if eff.get("into_resource") is not None and drained_total > 0:
            # 流失实际总额灌资源（光锥 23042 累计计数族；统一入口同 gain_resource）
            self._engine._gain_resource(st, str(eff["into_resource"]), drained_total,
                                        source_id=st.actor.actor_id)


    def _h_heal(self, st, eff, payload, updates):
        # 治疗（忆灵/丰饶族；12_summon 收编）：target 选择器 + ratio/amount **逐目标**
        # 求值（$target 注入——"按受疗者生命上限治疗"族首实例：阿格莱雅 1402 战技
        # param(140202,1)×$target.max_hp（官方"为衣匠回复等同于其生命上限的生命"）；ratio=施放者 HP 比例 + amount=固定量进 rulebook heal 公式
        # flat_heal 槽——风堇族"MaxHP×比例 + 定值"结构）——与 heal_self 同一管线口径
        # （吃治疗源 heal_bonus（召唤物施放归主人面板——2026-09-21 裁决）+ 受疗者
        # incoming_heal）；施放者侧写法求值不变（ratio/amount 表达式仍按钩持有者 $self 求值）
        healed_total = 0.0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            ratio = self._hook_amount(eff.get("ratio", 0), st, payload, t2)
            flat = self._hook_amount(eff.get("amount", 0), st, payload, t2)
            result = self._engine.pipeline.heal(st, t2, flat, hp_scaling=ratio)
            # 后段（溢出/0 值发射/月茧判定）= _emit_heal_settled 统一通道；actual 自累记账
            healed_total += self._emit_heal_settled(st, t2, result, payload)
        if getattr(self, "_chain_last", None) is not None:
            self._chain_last["actual_amount"] = healed_total   # $last/$prev 前序快照


    def _h_summon(self, st, eff, payload, updates):
        # 召唤物入场（12_summon）：布场/继承/上行动条/actor_enter 全在引擎单漏斗
        position = str(eff.get("position", "after_owner"))
        summon_id = str(eff.get("summon_id") or "")
        if "summon_id_source" in eff:
            selected = self._hook_amount(eff["summon_id_source"], st, payload)
            key = str(int(selected)) if float(selected).is_integer() else str(selected)
            variants = {str(k): str(v) for k, v in (eff.get("summon_variants") or {}).items()}
            summon_id = variants.get(key, "")
            if not summon_id:
                raise ValueError(f"动态召唤 ID {key!r} 不在已登记候选闭集")
        self._engine.summon_actor(
            st, summon_id, position=position,
            reference_actor_id=str(payload.get("target", "")) if position == "last_die" else "",
            summon_group=str(eff.get("summon_group") or ""))


    def _h_dismiss_summon(self, st, eff, payload, updates):
        # 召唤物离场（12_summon；未登记/未在场由引擎按 no-op/报错口径处理）
        self._engine.dismiss_summon_actor(str(eff["summon_id"]))


    def _h_modify_shield(self, st, eff, payload, updates):
        modifier_ids = {str(item) for item in eff.get("modifier_ids") or []}
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            for shield in list(t2.shields):   # 快照：破裂级联会移除实例
                if modifier_ids and shield.modifier_id not in modifier_ids:
                    continue
                amount = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
                if eff.get("max"):
                    shield.max_value = max(0.0, float(amount))
                    shield.remaining = min(shield.remaining, shield.max_value)
                else:
                    base = shield.remaining if eff.get("mode", "set") == "add" else 0.0
                    shield.remaining = max(0.0, base + float(amount))
                    if shield.max_value > 0 and not eff.get("allow_expand_max"):
                        shield.remaining = min(shield.remaining, shield.max_value)
                # F12：归零走破裂级联（与吸收破盾同口径），不留活零值盾
                if shield.remaining <= 1e-9:
                    self._engine._modifiers._break_shield(t2, shield, st.actor.actor_id)


    def _h_remove_shield(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            t2.shields.clear()


    def _h_leave_battle(self, st, eff, payload, updates):
        # 非击杀离场/逃跑：与 summon dismiss 共用 actor_exit 链，但不走 _check_death/on_kill
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            self._engine.leave_actor(t2.actor.actor_id, reason=str(eff.get("reason", "flee")))


    def _h_apply_modifier(self, st, eff, payload, updates):
        tgt = self._hook_target_states(eff.get("target", "self"), st, payload)
        base_spec = dict(eff.get("modifier") or {})
        # 现场求值族（蒙福者"暴伤=施加者暴伤×比例+定值"）：stat_effects 字符串值
        # 按 hook 上下文求值后烘焙成定值——施加时刻快照（重挂重算），与
        # trigger_action 的 scaling_atk 动态倍率同一 _hook_amount 通道。
        # 多目标烘焙一次（2026-09-12 布洛妮娅 110103 钓出）：逐目标重烘在"修饰件本身
        # 改写烘焙读数"时串染（全体暴伤 buff 读 $self.crit_dmg——首目标挂完自己暴伤
        # 变 0.78，后续目标按 0.78 重烘越挂越高）；_hook_amount 只吃 (st, payload)
        # 与 t2 无关，提前烘焙语义等价且全目标同值。
        se = base_spec.get("stat_effects")
        if se:
            base_spec["stat_effects"] = {
                k: (self._hook_amount(v, st, payload) if isinstance(v, str) else v)
                for k, v in se.items()}
        overrides = base_spec.get("override_effects")
        if overrides:
            base_spec["override_effects"] = {
                k: (self._hook_amount(v, st, payload) if isinstance(v, str) else v)
                for k, v in overrides.items()}
        # DoT 载体槽同走现场求值烘焙（2026-09-22 DoT 双通道合并——dot_ratio 表达式族：
        # 桂乃芬 S2「param(121002,4)×(1+0.4×res__s2_burn)」/桑博 E6「param(110804,2)
        # +0.15×marker」——星魂闩运行期读数，编译期 param() 只能取档不能求值；
        # 烘焙一次全目标同值，与 stat_effects 同口径）。stacks 同槽（计数驱动载荷族：
        # 海瑟音 Zone 追加「min(实例数, cap−trigs) 层」/黄泉集真赤转移「stacks($event.actor,…)」
        # ——运行期层数编译期不可求值；烘焙 float 由 _modifier_from_spec int() 取整）。
        for _dk in ("dot_ratio", "dot_base_chance"):
            _dv = base_spec.get(_dk)
            if isinstance(_dv, str):
                base_spec[_dk] = self._hook_amount(_dv, st, payload)
        stacks_expr = base_spec.get("stacks")
        source = st
        source_ref = str(eff.get("source") or "")
        if source_ref:
            if source_ref.startswith("$event."):
                source = self._event_actor(source_ref, payload)
            elif source_ref.startswith("modifier:"):
                holder = (self._event_actor("$event.actor", payload)
                          if "actor" in payload else st)
                held = (holder.modifiers.get(source_ref.split(":", 1)[1])
                        if holder is not None else None)
                source = (self._engine.state.actors.get(held.source_id)
                          if held is not None else None)
            else:
                source = self._engine.state.actors.get(source_ref)
            if source is None:
                raise ValueError(f"apply_modifier 的 source 无法解析：{source_ref!r}")
        for t2 in tgt:
            # stacks 允许 $target 逐目标取值（RL 双倍投注按各目标现有点数翻倍）；
            # 与 stat_effects/DoT 的一次烘焙隔离，避免目标间串值。
            spec = dict(base_spec)
            if isinstance(stacks_expr, str):
                spec["stacks"] = self._hook_amount(stacks_expr, st, payload, target_st=t2)
            for field in ("duration", "max_stack"):
                value = base_spec.get(field)
                if isinstance(value, str):
                    spec[field] = self._hook_amount(value, st, payload, target_st=t2)
            # F2 来源记账：kind=hook；ref=修饰件可展示名（hook 编译产物无更细出处，没有就空）
            self._engine._apply_modifier_spec(
                t2, spec, source,
                source_kind="hook",
                source_ref=str(spec.get("name", "")),
                apply_chance=self._hook_amount(eff.get("apply_chance", 1.0), st, payload),
                payload=payload)


    def _h_barrage_damage(self, st, eff, payload, updates):
        instances = int(self._hook_amount(eff.get("instances_expr", 1), st, payload))
        if instances <= 0:
            return
        hit_ids = set()
        for _ in range(instances):
            alive = self._engine._allies_alive()
            if not alive:
                break
            remaining = [t2 for t2 in alive if t2.actor.actor_id not in hit_ids]
            if remaining:
                target = remaining[-1]
            elif self._engine.pipeline.mode == MODE_ROLL and self._engine.pipeline.rng is not None:
                target = self._engine.pipeline.rng.choice(alive)
            else:
                # expected 确定化：优先命中后的随机段取编队首个，不掷骰。
                target = alive[0]
            nested_payload = {**payload, "barrage_target": target.actor.actor_id}
            base = dict(eff)
            base["effect_type"] = "deal_damage"
            base["target"] = "$event.barrage_target"
            base.pop("instances_expr", None)
            base.pop("repeat_scaling_atk", None)
            repeated = target.actor.actor_id in hit_ids
            self._run_hook_effect(st, base, nested_payload, updates)
            if repeated:
                bonus = dict(base)
                bonus["scaling_atk"] = eff.get("repeat_scaling_atk", 0.0)
                self._run_hook_effect(st, bonus, nested_payload, updates)
            hit_ids.add(target.actor.actor_id)


    def _h_random_choice(self, st, eff, payload, updates):
        options = eff.get("options") or []
        if not options:
            return
        if self._engine.pipeline.mode == MODE_ROLL and self._engine.pipeline.rng is not None:
            if any("weight" in option for option in options):
                total = sum(float(option.get("weight", 1.0)) for option in options)
                threshold = self._engine.pipeline.rng.random() * total
                cumulative = 0.0
                option = options[-1]
                for candidate in options:
                    cumulative += float(candidate.get("weight", 1.0))
                    if threshold < cumulative:
                        option = candidate
                        break
            else:
                option = self._engine.pipeline.rng.choice(options)
        else:
            option = options[0]
        self._run_hook_effect(st, dict(option), payload, updates)


    def _h_deal_damage(self, st, eff, payload, updates):
        targets = self._hook_target_states(eff.get("target", "enemy_first"), st, payload)
        if not targets:
            return
        # 基数区二态（互斥，编译期闸）：amount = ability_multiplier 直写（资源值即基数——
        # 风堇忆灵技 tally×比例族，01_formula §1.1 "由 effect 的 amount 表达式喂入"）；
        # scaling_atk / scaling_hp 合并同一行（scaling 列表逐行=等级档，拆开会被当成两档）
        # amount 逐目标求值通道（2026-09-24 收编）：`$target` 注入与 heal/gain_energy
        # 同槽——池选目标在数值槽内经 `$target` 引用（桑博 1108 E4「命中目标的风化
        # 层数」首实例：池 where 选层数达标者、amount 按命中目标层数结算——事件主目标
        # 与池选目标错位时不再错读主目标层数）；不引用 `$target` 的表达式逐目标同值，
        # 与旧一次性求值语义等价。惰性闭包：elation/true 分支的「须配 amount」判空
        # 读 amount_raw，不在此预求值（$target 引用须在逐目标循环内有注入点）
        amount_raw = eff.get("amount")

        def _base_override(t2: ActorState) -> Optional[float]:
            if amount_raw is None:
                return None
            return self._hook_amount(amount_raw, st, payload, target_st=t2)
        row: Dict[str, float] = {}
        if eff.get("scaling_atk") is not None:
            row["atk"] = self._hook_amount(eff["scaling_atk"], st, payload)
        if eff.get("scaling_hp") is not None:
            row["hp"] = self._hook_amount(eff["scaling_hp"], st, payload)
        # category: "additional" = 角色附加伤害（mechanics 02 §2.1 生效表：吃常规乘区，
        # 不吃类型限定增伤——action_type 归 "additional"，dmg_bonus_by_type 桶不命中）；
        # "true" = 真实伤害（rulebook true_damage 式：amount=fixed_value 直写，常规乘区
        # 全不命中，护盾同走——昔涟结界"原伤害%"族，mechanics 02 §2.8）
        category = str(eff.get("category", ""))
        ignore_shield = bool(eff.get("ignore_shield", False))
        # damage_type 二态（动态元素族——丹恒•腾荒 1414 同袍"相应属性"附加伤害首实例）：
        # 元素字面量直用；词表外按白名单表达式现场求值（element_of/who_has 宿主），
        # 求值结果词表闸（编译期已预编译——静态非法炸在编译期，动态结果非法炸在这里）；
        # category "true" 的真伤可写伪属性字面量 "true"（真伤分支不读 damage_type——
        # 编译期同口径豁免，勿按元素/表达式校验）
        dtype = eff.get("damage_type")
        if str(eff.get("category", "")) == "true" and dtype == "true":
            dtype = None
        if isinstance(dtype, str) and dtype and dtype.lower() not in ELEMENTS:
            dtype = str(self._engine._expr.evaluate(
                self._engine._expr.compile(dtype, layer="effect"),
                self._hook_ctx(st, payload),
                functions=self._hook_functions(st, payload))).lower()
            if dtype not in ELEMENTS:
                raise ValueError(
                    f"deal_damage damage_type 表达式求值结果 {dtype!r} 非合法元素"
                    f"（合法词表：{sorted(ELEMENTS)}——element_of 目标未声明 element 时得 ''）")
        if category == "elation":
            # 欢愉伤害（21_elation.md §21.2 路由）：amount=纯倍率表达式
            #（比例量纲不基于角色属性，02 §2.14 abilityMultiplier 口径）；
            # punchline_source 表达式槽定槽——缺省持有者好活当赏合并值（其他欢愉伤害），
            # 欢愉技段族写 "res_punchline"（阿哈笑点池实时值；覆写域内读取点拦截
            # 同锚——engine._resource_value 单点，字面值特判退役 2026-10-11）；
            # 爻光「触发角色无好活用爻光的算」族写 resource_of('1502','certified_banger')
            if amount_raw is None:
                raise ValueError(
                    "deal_damage category 'elation' 须配 amount（纯倍率表达式槽——"
                    "比例量纲，02 §2.14）")
            pl_src = eff.get("punchline_source")
            if pl_src is None:
                pl_val = self._engine._resource_value(st, "certified_banger")
            else:
                pl_val = float(self._hook_amount(pl_src, st, payload))
            # 削韧开闸（2026-10-11——火花 150104 天赋附伤 stance [15,0,0]÷3=5 米游社
            # /tbgd 双源实证，原「口径待实测」编译互斥闸退役）：与直伤同走
            # _apply_toughness_damage 单漏斗（own_element 默认闸/双效率池/击破判定/
            # 多韧性条/超击破转化全同口径），逐目标各削；pseudo action 建制同直伤分支
            #（削韧参 + 伪行动类别 + decl_action_type 命中域事件字段喂入——
            # 「强化普攻期间」族行动域隔离 scoped 判定读，04_modifier §hit_condition）
            toughness = 0.0
            if eff.get("toughness_dmg") is not None:
                toughness = float(self._hook_amount(eff["toughness_dmg"], st, payload))
            pseudo = Action(
                action_id=f"hook_{eff.get('name', 'dmg')}", name=str(eff.get("name", "hook")),
                action_type=str(eff.get("action_type") or "follow_up"),
                target_type="aoe" if len(targets) > 1 else "single",
                damage_type=dtype, is_indirect=bool(eff.get("is_indirect", False)),
                damage_tags=[int(tag) for tag in eff.get("damage_tags") or []],
                damage_custom_name=str(eff.get("damage_custom_name") or ""),
                toughness_dmg=toughness,
                toughness_scope=str(eff.get("toughness_scope") or ""),
            )
            # elation 覆写槽（2026-10-11——大吉大利择优族：爻光「攻击者欢愉度低于爻光
            # 用爻光的算」max(elation_of(触发者), $self.elation) 表达式现场求值喂
            # params；缺省不喂=读攻击者面板（rulebook elation_multi override_param））
            params: Dict[str, Any] = {"punchline_source": pl_val}
            if eff.get("elation") is not None:
                params["elation"] = self._hook_amount(eff["elation"], st, payload)
            dealt_el = 0.0
            seg_idx = getattr(self, "_chain_hit_seq", None)   # 链内命中序号（after_being_hit seg_index）
            for t2 in targets:
                with self._engine._damage_event():  # 每个 hook 伤害目标一批（月茧同时致死批处理域）
                    was_broken = t2.broken   # 超击破快照（同直伤分支）：破的那一击本身不触发
                    result = self._engine.pipeline.settle_damage(
                        "elation", st, t2, action=pseudo,
                        element=str(dtype or "physical"),
                        params={"ability_multiplier": _base_override(t2), **params})
                    dealt_el += float(result.value)
                    overflow = result.value if ignore_shield else self._engine._absorb_with_shields(
                    t2, result.value, st.actor.actor_id)
                    t2.current_hp -= overflow
                    if overflow > 0:
                        # HP 下降发射点（同 hit 族携带 damage_type/action_type——
                        # 伪行动类别经 action_type 声明槽（欢愉技段族标 elation_skill））
                        self._engine.bus.emit("on_hp_decrease", {
                            "amount": overflow, "source": st.actor.actor_id,
                            "reason": "hit", "target": t2.actor.actor_id,
                            "damage_type": str(dtype or ""),
                            "action_type": pseudo.action_type,
                            "is_critical": result.node.get("isCrit", False)}, self._engine.state)
                    self._engine.state.total_damage += result.value
                    self._engine.state.damage_by_actor[st.actor.actor_id] += result.value
                    self._engine.state.log.append(
                        f"AV{self._engine.state.clock:.1f}: {st.actor.name} 对 {t2.actor.name} "
                        f"造成 {result.value:,.0f} 欢愉伤害（{str(eff.get('name', 'elation'))}）")
                    # 削韧落点与直伤分支同位（伤害入账后、死亡检查前——击破致死链同序）
                    if self._engine._is_enemy(t2.actor):
                        self._engine._apply_toughness_damage(st.actor, pseudo, t2)
                        self._engine._try_super_break(
                            st, pseudo, t2, was_broken=was_broken,
                            source_action_id=str(payload.get("action_id") or ""))
                    self._engine._check_death(
                        t2, st.actor.actor_id,
                        action_id=str(payload.get("action_id") or ""))
                    # after_being_hit（受击链收尾——欢愉伤害是真攻击，action 层欢愉技段同发）
                    self._engine._emit_after_being_hit(
                        amount=float(result.value), absorbed=float(result.value) - overflow,
                        damage_type=str(dtype or "physical"), source_id=st.actor.actor_id,
                        target_id=t2.actor.actor_id,
                        is_critical=result.node.get("isCrit", False),
                        seg_index=seg_idx or 0, actor_type=st.actor.actor_type,
                        action_type=pseudo.action_type,
                        hit_targets=[t3.actor.actor_id for t3 in targets], action_id=pseudo.action_id,
                        split=str(eff.get("split") or ""), is_indirect=pseudo.is_indirect,
                        damage_tags=pseudo.damage_tags,
                        damage_custom_name=pseudo.damage_custom_name)
            if seg_idx is not None:
                self._chain_hit_seq = (seg_idx or 0) + 1
            if getattr(self, "_chain_last", None) is not None:
                self._chain_last["actual_amount"] = dealt_el   # $last/$prev 前序快照
            return
        if category in {"true", "atrophy"}:
            if amount_raw is None:
                raise ValueError(
                    f"deal_damage category {category!r} 须配 amount（fixed_value 直写槽）")
            dealt_true = 0.0
            for t2 in targets:
                with self._engine._damage_event():  # 每个 hook 伤害目标一批（月茧同时致死批处理域）
                    result = self._engine.pipeline.settle_damage("true", st, t2,
                                                   params={"fixed_value": _base_override(t2)})
                    dealt_true += float(result.value)
                    overflow = result.value if ignore_shield else self._engine._absorb_with_shields(
                    t2, result.value, st.actor.actor_id)
                    t2.current_hp -= overflow
                    if overflow > 0:
                        # HP 下降发射点：真伤保留 damage_type='true'（昔涟结界防递归闸）；
                        # Atrophy 保留声明元素与源行动类别，供命中域条件按量子/技能识别。
                        self._engine.bus.emit("on_hp_decrease", {
                            "amount": overflow, "source": st.actor.actor_id,
                            "reason": "hit", "target": t2.actor.actor_id,
                            "damage_type": ("true" if category == "true" else str(dtype or "")),
                            "action_type": ("follow_up" if category == "true" else str(
                                payload.get("action_type") or "skill")),
                            "is_critical": False}, self._engine.state)
                    self._engine.state.total_damage += result.value
                    self._engine.state.damage_by_actor[st.actor.actor_id] += result.value
                    self._engine.state.log.append(
                        f"AV{self._engine.state.clock:.1f}: {st.actor.name} 对 {t2.actor.name} "
                        f"造成 {result.value:,.0f} "
                        f"{'真实伤害' if category == 'true' else 'Atrophy 伤害'}"
                        f"（{str(eff.get('name', category))}）")
                    energy_grant = float(eff.get("energy_grant", 0.0) or 0.0)
                    grant_action = Action(
                        action_id=str(payload.get("action_id") or f"hook_{eff.get('name', 'dmg')}"),
                        name=str(eff.get("name", "hook")), action_type="skill",
                        target_type="single", damage_type=dtype,
                        toughness_dmg=int(eff.get("toughness_dmg", 0) or 0),
                        energy_grant=energy_grant)
                    if eff.get("toughness_dmg") is not None and self._engine._is_enemy(t2.actor):
                        self._engine._apply_toughness_damage(st.actor, grant_action, t2)
                    self._engine._check_death(
                        t2, st.actor.actor_id,
                        action_id=str(payload.get("action_id") or ""))
                    if t2.alive and energy_grant > 0:
                        self._engine._grant_hit_energy(st.actor, grant_action, t2)
            if getattr(self, "_chain_last", None) is not None:
                self._chain_last["actual_amount"] = dealt_true   # $last/$prev 前序快照
            return
        # 削韧（2026-09-07 收编，05_effects §造成伤害）：toughness_dmg 与 action 层同键
        # 同语义——缺省 0=不削；同走引擎 _apply_toughness_damage 单漏斗（own_element 默认闸/
        # 双效率池/击破判定/多韧性条全同口径），逐目标各削（多段=多个 deal_damage 各声明）；
        # category "true" 互斥由编译期闸拦（真伤无属性不削韧，上方分支不触碰本参）
        toughness = 0.0
        if eff.get("toughness_dmg") is not None:
            toughness = float(self._hook_amount(eff["toughness_dmg"], st, payload))
        pseudo = Action(
            action_id=f"hook_{eff.get('name', 'dmg')}", name=str(eff.get("name", "hook")),
            # 伪行动类别：缺省 follow_up/additional；模板可经 action_type 声明槽改写
            #（飞霄 1220 终结技子击标 ultimate——"终结技伤害"身份族（E6 穿透
            # scoped/Formshift 反向族）的挂载点，2026-09-14 接线；
            # "dot" = DoT 路由——桑博 1108 风化 tick 族 2026-09-22 接线：通用
            # deal_damage 路径增伤区按 f"{action_type}_dmg_boost" 读 dot_dmg_boost
            # 桶（「持续伤害提高」），攻击侧池与声明式 DoT 跳伤（settle "dot" 路由）
            # 增伤合成同口径；
            # 边界①暴击口径不变——事件承载含期望暴击（R-SV1/R-KF3 在案结构差，
            # 官方 DoT 不暴击，待迁移声明式通道后统一）；②一次性结算读现值，
            # 非施加-跳伤模型，快照切分不适用）
            action_type=str(eff.get("action_type")
                            or ("additional" if category == "additional" else "follow_up")),
            target_type="aoe" if len(targets) > 1 else "single",
            damage_type=dtype, is_indirect=bool(eff.get("is_indirect", False)),
            damage_tags=[int(tag) for tag in eff.get("damage_tags") or []],
            damage_custom_name=str(eff.get("damage_custom_name") or ""), scaling=[row],
            toughness_dmg=toughness,
            energy_grant=float(eff.get("energy_grant", 0.0) or 0.0),
            # toughness_scope（黄泉秘技"无视弱点削减全体韧性"族——action 层同键同语义，
            # 缺省 own_element 默认闸；首个 hook 层实例 130807）
            toughness_scope=str(eff.get("toughness_scope") or ""),
        )
        dealt_total = 0.0
        # 链内命中序号（after_being_hit seg_index 口径；附加伤害不发不占段——
        # 03_actor §3.8 tags「不再触发命中类监听」）
        seg_idx = getattr(self, "_chain_hit_seq", None)
        for t2 in targets:
            with self._engine._damage_event():  # 每个 hook 伤害目标一批（月茧同时致死批处理域）
                was_broken = t2.broken   # 超击破快照：破的那一击本身不触发
                result = self._engine.pipeline.settle_damage(
                    "direct", st, t2, action=pseudo,
                    params={"target_broken": t2.broken, "base_override": _base_override(t2)})
                wp = self._engine.bus.waterfall("before_take_damage", {
                    "amount": result.value, "damage_type": dtype,
                    "source": st.actor.actor_id, "target": t2.actor.actor_id,
                    "action_id": pseudo.action_id, "action_type": pseudo.action_type,
                    "is_critical": result.node.get("isCrit", False),
                    "split": str(eff.get("split") or ""), "is_indirect": pseudo.is_indirect,
                    "damage_tags": list(pseudo.damage_tags),
                    "damage_custom_name": pseudo.damage_custom_name,
                    "block_damage_triggered": any(
                        mod.block_damage for mod in t2.all_modifiers())}, self._engine.state)
                if wp.get("cancel"):
                    continue
                final_amount = float(wp.get("amount", result.value))
                dealt_total += final_amount
                overflow = final_amount if ignore_shield else self._engine._absorb_with_shields(
                    t2, final_amount, st.actor.actor_id)
                t2.current_hp -= overflow
                if overflow > 0:
                    # HP 下降发射点（hook 附加/追加伤害——受击族；reason='hit'，词表冻结见 _execute_action）
                    # damage_type 仅 'hit' 族携带（昔涟结界真伤防递归闸同口径）；
                    # action_type 同族携带=伪行动类别（"指定技能造成的伤害"族过滤——遐蝶 E1）
                    self._engine.bus.emit("on_hp_decrease", {
                        "amount": overflow, "source": st.actor.actor_id,
                        "reason": "hit", "target": t2.actor.actor_id,
                        "damage_type": str(dtype or ""),
                        "action_type": pseudo.action_type,
                        "is_critical": result.node.get("isCrit", False)}, self._engine.state)
                self._engine.state.total_damage += final_amount
                self._engine.state.damage_by_actor[st.actor.actor_id] += final_amount
                self._engine._log(st.actor, pseudo, t2, final_amount, result.node.get("isCrit", False))
                # 削韧落点与 action 层同位（伤害入账后、死亡检查前——击破致死链同序）
                if self._engine._is_enemy(t2.actor):
                    self._engine._apply_toughness_damage(st.actor, pseudo, t2)
                    self._engine._try_super_break(
                        st, pseudo, t2, was_broken=was_broken,
                        source_action_id=str(payload.get("action_id") or ""))
                self._engine._check_death(
                    t2, st.actor.actor_id,
                    action_id=str(payload.get("action_id") or ""))
                # 与 action 层同序：存活目标逐段受击回能，打盾照回，致死段不回。
                if t2.alive and pseudo.energy_grant > 0:
                    self._engine._grant_hit_energy(st.actor, pseudo, t2)
                if pseudo.action_type != "additional" and result.value > 0:
                    # after_being_hit 受击链收尾（镜像 action 层 _execute_action 发法——
                    # 契约单口 engine._emit_after_being_hit）；附加伤害不发（03_actor §3.8 tags）；
                    # 0 伤害非命中不发——模板「×(条件)」置零=不发惯用法（1308 结爆
                    # n=0 族）的收尾事件对齐：盾全吸收 result.value>0 照发，置零幻影
                    # （无扣血无吸收）不算被击中（2026-09-17 组队对拍钓出：黄泉大招
                    # 返渡/Core 段幻影结爆误触发缇宝境界 7 次）
                    self._engine._emit_after_being_hit(
                        amount=float(final_amount), absorbed=float(final_amount) - overflow,
                        damage_type=dtype, source_id=st.actor.actor_id,
                        target_id=t2.actor.actor_id,
                        is_critical=result.node.get("isCrit", False),
                        seg_index=seg_idx or 0, actor_type=st.actor.actor_type,
                        action_type=pseudo.action_type,
                        hit_targets=[t3.actor.actor_id for t3 in targets], action_id=pseudo.action_id,
                        split=str(eff.get("split") or ""), is_indirect=pseudo.is_indirect,
                        damage_tags=pseudo.damage_tags,
                        damage_custom_name=pseudo.damage_custom_name,
                        block_damage_triggered=bool(wp.get("block_damage_triggered")))
        if (pseudo.action_type != "additional" and seg_idx is not None
                and dealt_total > 0):
            # 链内命中序号只计真发伤的 deal_damage（0 置零幻影不占段——与发射闸同口径）
            self._chain_hit_seq = (seg_idx or 0) + 1
        if getattr(self, "_chain_last", None) is not None:
            self._chain_last["actual_amount"] = dealt_total   # $last/$prev 前序快照


    def _h_trigger_action(self, st, eff, payload, updates):
        aid = str(eff.get("action_id", ""))
        if aid == "$event.action_id":
            # 动态行动（奇袭"复制即将施放的战技"族）：行动与施放者都按事件寻址——
            # 复刻事件方刚施放的行动并由其再放一次（刻律德菈军功持有者的战技复制；
            # 与静态版的差别：行动属于事件方而非 hook 持有者）
            src_st = self._engine.state.actors.get(str(payload.get("actor")))
            action = None
            if src_st is not None:
                action = next((a for a in self._engine.actions_by_actor.get(
                    src_st.actor.actor_id, [])
                    if a.action_id == str(payload.get("action_id"))), None)
            if src_st is not None and action is not None:
                # 奇袭可见性：复制本身要留名——否则日志只有一条无头"插入发动"，
                # 用户看不出是刻律德菈复制的（前端体验反馈 2026-09-05）
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: {st.actor.name} 奇袭复制——"
                    f"{src_st.actor.name} 再次施放 {action.name}")
                self._engine.trigger_action(src_st, action, tag="hook")
            return
        # v1 跨 actor（开拓者•欢愉终结技代放队友欢愉技族）：caster 缺省 self=
        # hook 持有者；action_id 在 caster 行动表解析；action_type 按类索引
        #（各角色欢愉技 id 不同——恰 1 件，0/>1 大声炸不许静默）
        casters = self._hook_target_states(eff.get("caster", "self"), st, payload)
        if len(casters) != 1:
            raise ValueError(
                f"trigger_action 的 caster 须解析为单一目标（实得 {len(casters)} 个："
                f"{eff.get('caster', 'self')!r}）——代放执行者不定即语义不定")
        cst = casters[0]
        atype = eff.get("action_type")
        if atype is not None:
            cands = [a for a in self._engine.actions_by_actor.get(cst.actor.actor_id, [])
                     if a.action_type == str(atype)]
            if len(cands) != 1:
                raise ValueError(
                    f"trigger_action 按 action_type {atype!r} 在 {cst.actor.name} "
                    f"行动表恰取 1 件失败（实得 {len(cands)}）——0=无此类行动、"
                    f">1=选择子歧义，都不许静默")
            action = cands[0]
        else:
            action = next((a for a in self._engine.actions_by_actor.get(cst.actor.actor_id, [])
                           if a.action_id == aid), None)
        if action is not None:
            if eff.get("scaling_atk") is not None:
                # 动态倍率覆写（计数器反击族：倍率随 stacks/资源现场求值，见 05_effects trigger_action）
                action = replace(
                    action,
                    scaling=[{"atk": self._hook_amount(eff["scaling_atk"], st, payload)}],
                )
            # pool_override（欢愉代放固定笑点档——欢愉主终结技「固定计入 20 笑点」族，
            # 05_effects trigger_action；表达式槽现场求值）
            pool_ov = (self._hook_amount(eff["pool_override"], st, payload)
                       if eff.get("pool_override") is not None else None)
            forced_target = None
            if "target" in eff:
                # 显式 target = 强制主目标；空候选 = 不代放（递归自然终止），不回落默认目标。
                targets = self._hook_target_states(eff["target"], st, payload)
                if not targets:
                    return
                if len(targets) != 1:
                    raise ValueError(
                        f"trigger_action 的 target 须解析为单一目标（实得 {len(targets)} 个）")
                forced_target = targets[0]
            self._engine.trigger_action(
                cst, action, tag="hook", pool_override=pool_ov, forced_target=forced_target)


    def _h_aha_instant(self, st, eff, payload, updates):
        # 额外阿哈时刻（爻光终结技族——21_elation.md §21.4：结算档=模板 amount 槽
        # 声明（表达式经 _hook_amount 现场求值，同三行之上 pool_override 先例；
        # 引擎零游戏数值——缺槽编译期炸）、不耗当前池、照授同值好活当赏；
        # 具有额外回合特性不可插入终结技）
        self._engine._run_aha_turn(
            extra_pool=self._hook_amount(eff["amount"], st, payload))


    def _h_absorb_modifier(self, st, eff, payload, updates):
        # 按名称吸收可驱散 modifier：逐目标累计层数，资源统一记到 hook 持有者。
        modifier_name = str(eff["modifier_name"])
        resource_id = str(eff["resource_id"])
        absorbed = 0.0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            for mod in list(t2.all_modifiers()):
                if not mod.dispellable or mod.name != modifier_name:
                    continue
                absorbed += max(1.0, float(mod.stacks))
                self._engine._remove_modifier(t2, mod.modifier_id, "absorb")
        if absorbed > 0:
            self._engine._gain_resource(st, resource_id, absorbed,
                                          source_id=st.actor.actor_id)


    def _h_remove_modifier(self, st, eff, payload, updates):
        # 摘除 modifier（计数器消耗/状态解除族；target 默认 self，支持全体/事件寻址——
        # 缇宝天赋计数重置、境界易伤联动摘除族；与 05_effects remove_modifier 声明对齐）
        # filter（$mod 绑定，2026-09-07 落地）：按类摘除（长夜月天赋"驱散控制类 debuff"族）——
        # 与 modifier_id 至少其一（都写=交集）；命中仅限 dispellable，LIFO 逐个
        # max_count（2026-09-08 落地）：逐目标截断——命中清单（LIFO 序）只摘前 N 个
        # （丹恒•腾荒 141404 龙灵"解除我方全体的 1 个负面效果"族首实例）
        mid = str(eff.get("modifier_id") or "")
        filt = eff.get("filter")
        max_count = eff.get("max_count")
        reason = str(eff.get("reason", "remove"))
        order = str(eff.get("order", "newest"))
        if order not in {"newest", "oldest"}:
            raise ValueError(f"remove_modifier.order 非法：{order!r}")
        removed_count = 0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            if not filt:
                if mid in t2.modifiers:
                    removed_count += 1
                self._engine._remove_modifier(t2, mid, reason)
                continue
            prepared = self._engine._expr.compile(str(filt), layer="effect")
            hit: List[str] = []
            modifiers = list(t2.all_modifiers())
            if order == "newest":
                modifiers = list(reversed(modifiers))
            for mod in modifiers:
                if not mod.dispellable:
                    continue
                if mid and mod.modifier_id != mid:
                    continue
                kind = mod.debuff_kind or ("control" if mod.control_kind else mod.modifier_type)
                mod_ns = types.SimpleNamespace(
                    modifier_id=mod.modifier_id, modifier_type=mod.modifier_type,
                    debuff_kind=mod.debuff_kind, control_kind=mod.control_kind,
                    dot_element=mod.dot_element, dispellable=mod.dispellable, kind=kind,
                    behavior_flags=list(mod.behavior_flags),
                    prevent_action=mod.prevent_action, name=mod.name, source=mod.source_id)
                ctx = self._hook_ctx(st, payload)
                ctx["mod"] = mod_ns
                if self._engine._expr.evaluate(
                        prepared, ctx, functions=self._hook_functions(st, payload)):
                    hit.append(mod.modifier_id)
            if max_count is not None:
                hit = hit[: int(max_count)]
            for hid in hit:
                self._engine._remove_modifier(t2, hid, reason)
            removed_count += len(hit)
        if getattr(self, "_chain_last", None) is not None:
            self._chain_last["removed_count"] = float(removed_count)


    def _h_clear_protected_weakness(self, st, eff, payload, updates):
        removed = {str(element) for element in eff["weak_list"]}
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            for mod in t2.all_modifiers():
                if mod.protected_weakness:
                    mod.protected_weakness = [
                        element for element in mod.protected_weakness if element not in removed]


    def _h_clear_attached_weakness(self, st, eff, payload, updates):
        removed = {str(element) for element in eff["weak_list"]}
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            for mod in t2.all_modifiers():
                if mod.weakness_add:
                    mod.weakness_add = [
                        element for element in mod.weakness_add if element not in removed]


    def _h_clear_secret_weakness(self, st, eff, payload, updates):
        removed = {str(element) for element in eff["weak_list"]}
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            for mod in t2.all_modifiers():
                if mod.secret_weakness:
                    mod.secret_weakness = [
                        element for element in mod.secret_weakness if element not in removed]


    def _h_adjust_duration(self, st, eff, payload, updates):
        # 时长 ±N（B9 原语；≠ refresh 重置满值——刃族"延长/缩短持续回合"）：
        # clamp ≥0，调到 0 即按到期移除（与走字到期同口径 reason=expire）
        mid = str(eff["modifier_id"])
        delta = int(self._hook_amount(eff.get("delta", 0), st, payload))
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            m = t2.modifiers.get(mid)
            if m is None:
                continue
            m.duration = max(0, m.duration + delta)
            if m.duration == 0:
                self._engine._remove_modifier(t2, mid, "expire")


    def _h_trigger_dot(self, st, eff, payload, updates):
        # 强制结算目标 DoT（卡芙卡"立即触发持续伤害"族）——不消耗 duration，
        # on_dot_retrigger 照发（与自然跳伤共用 _settle_one_dot 单漏斗）。
        # 选择性（缺省全结=旧行为不变）：scope="all"（缺省）/"self"（仅触发者施加的）/
        # modifier_id（只结指定件）；dot_element 非空按跳伤属性再窄化（AND 叠加——
        # 卢卡「只引爆裂伤」族首实例；与 modifier 的 dot_element 字段同名对齐）；
        # ratio=引爆比例（缺省 1.0 全额——「立即产生原伤害 X%」族，表达式通道同
        # break_damage 先例，引爆值=ratio×正典跳伤值）
        scope = str(eff.get("scope") or "all")
        ratio = float(self._hook_amount(eff.get("ratio", 1.0), st, payload))
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            self._engine._modifiers.trigger_dots(
                t2, scope=scope, dot_element=str(eff.get("dot_element") or ""),
                ratio=ratio, source_id=st.actor.actor_id)


    def _h_trigger_stance_countdown(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            self._engine.bus.emit("on_stance_countdown", {
                "source": st.actor.actor_id, "target": t2.actor.actor_id,
                "ignore_mute_break": bool(eff.get("ignore_mute_break", False)),
            }, self._engine.state)


    def _h_trigger_break(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            if t2.bars_exhausted or (not eff.get("ignore_mute_break", False) and any(
                    "MuteBreak" in modifier.behavior_flags
                    for modifier in t2.all_modifiers())):
                continue
            damage_type = str(eff.get("damage_type") or "physical")
            if damage_type.startswith("$event."):
                damage_type = str(self._engine._expr.evaluate(
                    self._engine._expr.compile(damage_type, layer="effect"),
                    self._hook_ctx(st, payload),
                    functions=self._hook_functions(st, payload))).lower()
            pseudo = Action(
                action_id="trigger_break", name="trigger_break", target_type="single",
                action_type="skill", damage_type=damage_type)
            self._engine._trigger_break(st.actor, pseudo, t2)


    def _h_reduce_toughness(self, st, eff, payload, updates):
        # 固定削韧（05_effects §reduce_toughness）：不吃效率池；floor>0 只钳下限不击破。
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            if not self._engine._is_enemy(t2.actor):
                continue
            amount = float(self._hook_amount(eff["amount"], st, payload, target_st=t2))
            floor = float(self._hook_amount(eff.get("floor", 0), st, payload, target_st=t2))
            if amount < 0 or floor < 0:
                raise ValueError("reduce_toughness 的 amount/floor 必须非负")
            if t2.bars_exhausted or any(mod.toughness_lock for mod in t2.all_modifiers()):
                continue
            current = float(t2.toughness)
            actual = min(amount, max(0.0, current - floor))
            if actual > 0:
                t2.toughness = current - actual
                self._engine.bus.emit("on_toughness_damage", {
                    "amount": actual, "source": st.actor.actor_id,
                    "target": t2.actor.actor_id, "bar_index": t2.bar_index}, self._engine.state)
            if t2.toughness <= 0 and not t2.bars_exhausted:
                pseudo = Action(
                    action_id="reduce_toughness", name="reduce_toughness",
                    action_type="skill", damage_type=str(eff.get("damage_type") or "physical"))
                self._engine._trigger_break(st.actor, pseudo, t2)


    def _h_exit_break_state(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            t2.broken = False
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: {t2.actor.name} 退出击破状态")


    def _h_reset_stance(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            t2.bar_index = 0
            maximum = float(self._engine.pipeline.effective_stats(t2)["max_toughness"])
            if "amount" not in eff:
                t2.toughness = maximum
            else:
                amount = self._hook_amount(eff["amount"], st, payload, target_st=t2)
                mode = str(eff.get("mode") or "set")
                if mode == "add":
                    value = t2.toughness + amount
                elif mode == "set":
                    value = amount
                else:
                    raise ValueError(f"reset_stance 的 mode 非法值 {mode!r}")
                t2.toughness = min(maximum, max(0.0, value))
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: {t2.actor.name} 韧性重置")


    def _h_set_targetable(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            before = {key: bool(t2.actor.summon_flags.get(key, True))
                      for key in ("enemy_targetable", "ally_targetable")}
            for key, old in before.items():
                if key in eff:
                    t2.actor.summon_flags[key] = bool(eff[key])
            current = {key: bool(t2.actor.summon_flags.get(key, True)) for key in before}
            if any(old and not current[key] for key, old in before.items()):
                self._engine.bus.emit("on_unselectable_start", {
                    "target": t2.actor.actor_id, "source": st.actor.actor_id,
                    "enemy_targetable": current["enemy_targetable"],
                    "ally_targetable": current["ally_targetable"],
                }, self._engine.state)
            if any(not old and current[key] for key, old in before.items()):
                self._engine.bus.emit("on_unselectable_end", {
                    "target": t2.actor.actor_id, "source": st.actor.actor_id,
                    "enemy_targetable": current["enemy_targetable"],
                    "ally_targetable": current["ally_targetable"],
                }, self._engine.state)


    def _h_restore_toughness(self, st, eff, payload, updates):
        # 韧性恢复（05_effects §restore_toughness）：与自然恢复同态——回主条、补满、
        # 追加条保留；未击破时仅补足当前韧性，不另发事件。
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            t2.broken = False
            t2.bar_index = 0
            t2.toughness = float(self._engine.pipeline.effective_stats(t2)["max_toughness"])
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: {t2.actor.name} 韧性恢复")


    def _h_add_toughness_bar(self, st, eff, payload, updates):
        # 追加韧性条（03_actor §3.10 虚韧性族机制赋予）：运行期追加条（max=amount，
        # 按加入序承接；恢复不消失——随下次主条破再切入）；
        # amount **逐目标求值**（target_st 语境——云火昭「等同于各自韧性上限×比例」族
        # （122504 param×$target.max_toughness），drain_hp 同通道；旧版循环外单算
        # 无 $target 消费未暴露）
        for t2 in self._hook_target_states(eff.get("target", "enemy_first"), st, payload):
            amount = self._hook_amount(eff.get("amount", 0), st, payload, target_st=t2)
            t2.added_bars.append(amount)
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: {t2.actor.name} 被赋予追加韧性条"
                f"（{amount:.0f}，第 {len(t2.extra_bars)} 条）")


    def _h_break_damage(self, st, eff, payload, updates):
        # 击破伤害执行体（阮梅天赋/残梅绽族）：pipeline.break_damage × ratio（击破公式，非直伤）
        # 扣血分工：pipeline 纯结算不扣血，本层按 val=值×ratio 一次性扣（恰降 ratio×击破值）；
        # 绕盾直扣（不走 _absorb_with_shields）= 冻结口径（注记见 _trigger_break docstring）
        targets = self._hook_target_states(eff.get("target", "enemy_first"), st, payload)
        if not targets:
            return
        element = str(eff.get("element", "physical"))
        ratio = self._hook_amount(eff.get("ratio", 1.0), st, payload)
        for t2 in targets:
            with self._engine._damage_event():  # 每个 hook 击破伤害目标一批（月茧同时致死批处理域）
                res = self._engine.pipeline.settle_damage("break", st, t2, element=element)
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
                self._engine._check_death(
                    t2, st.actor.actor_id,
                    action_id=str(payload.get("action_id") or ""))


    def _h_grant_extra_turn(self, st, eff, payload, updates):
        # target 同其他 hook effect 走统一解析（曾恒授 hook 携带者——1313 拉目标
        # 变拉自己的雷）；缺省 self = 再现/青雀族原行为不变
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            self._engine.scheduler.grant_extra_turn(t2.actor.actor_id, EXTRA_NORMAL)


    def _h_immediate_action(self, st, eff, payload, updates):
        # 立即行动（05_effects §立即行动）：剩余距离置 0 直接到顶（无视推条）——
        # 产出行动轴上的普通回合（吃回合事件、消耗 buff），星期日/布洛妮娅战技族
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            assert self._engine.scheduler is not None
            self._engine.scheduler.act_now(t2.actor)


    def _h_set_action_delay(self, st, eff, payload, updates):
        if "near_target" in eff:
            near_targets = self._hook_target_states(eff["near_target"], st, payload)
            if not near_targets:
                return
            if len(near_targets) != 1:
                raise ValueError("set_action_delay 的 near_target 必须恰好一个实体")
            for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
                assert self._engine.scheduler is not None
                self._engine.scheduler.set_action_delay_near(t2.actor, near_targets[0].actor)
            return
        pct = self._hook_amount(eff.get("amount", 0), st, payload) / 100.0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            assert self._engine.scheduler is not None
            self._engine.scheduler.set_action_delay(t2.actor, pct)


    def _h_delay_action(self, st, eff, payload, updates):
        # 行动延后（05_effects §delay_action；amount 为百分数——30 = 延后 30% 行动条）
        pct = self._hook_amount(eff.get("amount", 0), st, payload) / 100.0
        apply_chance = self._hook_amount(eff.get("apply_chance", 1.0), st, payload)
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            assert self._engine.scheduler is not None
            if self._engine._effect_application_succeeded(
                    st, t2, apply_chance,
                    modifier_id=str(payload.get("action_id") or "delay_action"), label="行动延后"):
                if self._engine._action_delay_change_allowed(
                        t2, st.actor.actor_id, "increase"):
                    self._engine.scheduler.delay_action(t2.actor, pct)


    def _h_advance_action(self, st, eff, payload, updates):
        # 行动提前（05_effects §advance_action 收编；amount 为百分数——30 = 提前 30% 行动条；
        # 剩余距离 ≤ 0 时无效（scheduler 内部口径，mechanics 03 钉死）——小伊卡消失拉忆师族）
        pct = self._hook_amount(eff.get("amount", 0), st, payload) / 100.0
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            assert self._engine.scheduler is not None
            if self._engine._action_delay_change_allowed(
                    t2, st.actor.actor_id, "decrease"):
                self._engine.scheduler.advance_action(t2.actor, pct)


    def _h_set_team_location(self, st, eff, payload, updates):
        position = str(eff["position"])
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            if position in {"first", "last"}:
                reference = t2.actor.actor_id
            else:
                refs = self._hook_target_states(eff.get("reference", "self"), st, payload)
                if not refs:
                    continue
                if len(refs) != 1:
                    raise ValueError("编队移动的参照目标必须唯一")
                reference = refs[0].actor.actor_id
                if reference == t2.actor.actor_id:
                    continue
            self._engine._place_relative_owner(
                t2.actor.actor_id, reference, position)


    def _h_lock_action_delay(self, st, eff, payload, updates):
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            key = f"{st.actor.actor_id}:{eff['lock_id']}"
            if eff.get("locked", True):
                source_id = (st.actor.actor_id
                             if eff.get("whitelist_source") == "self" else "")
                t2.action_delay_locks[key] = {
                    "source_id": source_id,
                    "change_type": str(eff.get("whitelist_change_type") or ""),
                }
            else:
                t2.action_delay_locks.pop(key, None)


    def _h_adjust_stacks(self, st, eff, payload, updates):
        mid = str(eff.get("modifier_id", ""))
        # target 跨 actor 层写（05_effects §adjust_stacks——昔涟 1141519 风堇施放
        # 战技/终结技后消耗 1 层「天空」首实例）；目标未持有 = 该目标无效果（不报错）
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            m = t2.modifiers.get(mid)
            if m is not None:
                # clamp [0, max_stack]（05_effects §adjust_stacks）——max_stack=0 的
                # 0 层件不再被抬到 1（曾钳 [1, max]：max=0 时下界压上界的退化）
                m.stacks = max(0, min(int(m.stacks + self._hook_amount(
                    eff.get("delta", 0), st, payload, target_st=t2)),
                    m.max_stack))


    def _h_activate_ultimate(self, st, eff, payload, updates):
        # 激活终结技（05_effects §激活终结技 收编——昔涟 141503"激活全体队友的终结技"族）：
        # 目标终结技立即作为插入行动发动、不耗充能（v1 口径）；缺省 other_allies（"队友"主语）
        for t2 in self._hook_target_states(eff.get("target", "other_allies"), st, payload):
            self._engine._activate_ultimate(t2)


    def _h_exit_state(self, st, eff, payload, updates):
        # 退出当前形态（17_actor_state §17.6 收编——非倒计时退出条件族（致命/锁血即收、
        # 玩家选择完毕）的 hook 通道，1510 拓星者首实例）：走 engine.exit_state 单漏斗
        # （摘标记/境界清理/on_state_change 广播同口径）；无形态时安全空转
        for t2 in self._hook_target_states(eff.get("target", "self"), st, payload):
            self._engine.exit_state(t2, reason=str(eff.get("reason", "hook")))

