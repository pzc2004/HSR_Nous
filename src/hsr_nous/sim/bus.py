"""事件总线 v0.1：发射点 / waterfall-emit 分派 / modify_event 最小集.

契约（23_event_hook_system.md）：
- 引擎每个状态变更操作强制自动发射事实（发射点生成式）
- waterfall 事件经 hook 链逐级修改 payload 后按当前值继续；emit 只读
- modify_event v0.1 白名单：amount / cancel
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# hook 签名：fn(event_type, payload, ctx) -> None（emit 链上只读执行）
EmitHook = Callable[[str, Dict[str, Any], Any], None]
# waterfall hook 签名：fn(event_type, payload, ctx) -> 修改后的 payload（或 {"cancel": True}）
WaterfallHook = Callable[[str, Dict[str, Any], Any], Optional[Dict[str, Any]]]

# v0.1 登记的可改性表（emit=只读 / waterfall=可改）
DEFAULT_CONTRACT: Dict[str, str] = {    "on_battle_start": "emit",
    "on_wave_start": "emit",
    "on_turn_start": "emit",
    "on_turn_end": "emit",
    "on_cycle_start": "emit",   # 轮次开始（发射已接线于 engine._tick_cycle，契约表补登记）
    "on_cycle_end": "emit",     # 轮次结束（同上）
    "on_extra_turn": "emit",
    "on_action": "emit",
    "before_take_damage": "waterfall",
    "after_being_hit": "emit",
    "on_hp_decrease": "emit",
    "on_hp_increase": "emit",
    "on_kill": "emit",
    "before_actor_exit": "emit",  # 离场前（alive=False 之前——生前结算族挂载点：遐蝶 1140706 晦翼自爆）
    "actor_exit": "emit",
    "actor_enter": "emit",
    "on_toughness_damage": "emit",
    "toughness_recovered": "waterfall",  # 敌方回合开始韧性恢复结算前（cancel=阻止本次恢复、保持击破——残梅绽族）
    "on_gain_energy": "waterfall",  # before_gain：能量获得量可被改写
    "on_resource_gain": "emit",     # 自定义资源获得后（银行转移/阈值触发族的挂载点）
    "before_consume": "waterfall",  # 资源消耗前（改写消耗量/取消——火花 climax 抵扣族的挂载点）
    "after_consume": "emit",        # 资源消耗后（绯英 after_gain 对偶/记账族的挂载点）
    "before_drain": "waterfall",    # drain_hp 逐目标扣减前（改写扣量/取消——遐蝶 E2 炽意抵扣族的挂载点）
    "battle_end": "emit",           # 战斗终止（termination reason 见 23.4；结构化日志终局锚点）
    "on_skill_point_change": "emit",  # 战技点增减（before/after——结构化日志 SP 槽取数点）
    "on_become_target": "emit",     # 成为技能目标（140804"成为目标获火种/队友给暴伤"族的挂载点）
    "on_state_change": "emit",      # 形态进入/退出（大行迹/境界族的挂载点）
    "on_break": "emit",
    "on_super_break": "emit",
    "on_dot_retrigger": "emit",
    "after_apply_modifier": "emit",
    "after_remove_modifier": "emit",
    "on_immune": "emit",
    "on_resist": "emit",
    "on_ultimate": "emit",
    "shield_absorbed": "emit",  # 护盾逐实例吸收（payload 带 shield_id/amount/remaining/source/target）
    "shield_broken": "emit",    # 护盾后台破裂（级联摘除关联 modifier，reason=shield_broken）
    "on_revive": "emit",        # 死亡检查触发复活（消费复活件，按百分比回拉 HP）
    "on_hp_lock": "emit",       # 锁血钳制（伤害致死被 hp_lock 钳 1 血——"无法被继续削减生命值"族挂载点）
    "aha_instant_start": "emit",   # 阿哈时刻开始（解控后、欢愉技代放前——21_elation §21.4）
    "aha_instant_end": "emit",     # 阿哈时刻结束（授好活当赏/清池后——「阿哈时刻结束时」族挂载点：火花 E1/E2）
}


#: 事件 payload 字段注册表（与 23 章事件表"实发集"同义——AST 收割闸双向校验，见
#: tests/test_event_payload_registry.py；勿手改，改发射点后跑收割闸同步）——双侧闸：
#: ① 发射侧：bus.emit/waterfall 入口校验 payload 键 ⊆ 表（waterfall 放行链控键 cancel）
#: ② 模板侧：build_compiler 对 hook condition/effects 表达式槽的 `$event.<字段>` 对账
#: （打标稿 `$event.crit` 错拼族实证——载荷无此键=B8 静默死钩，compile 期锁死）
DEFAULT_PAYLOAD_FIELDS: Dict[str, frozenset] = {
    "actor_enter": frozenset({'actor', 'actor_type', 'reason', 'wave_index'}),
    "actor_exit": frozenset({'actor', 'reason'}),
    "after_apply_modifier": frozenset({'modifier_id', 'modifier_type', 'source', 'stat', 'target'}),
    "after_being_hit": frozenset({'absorbed', 'action_type', 'actor_type', 'amount', 'damage_type', 'hit_targets', 'is_critical', 'seg_index', 'source', 'target'}),
    "after_consume": frozenset({'actor', 'amount', 'current', 'resource_id'}),
    "after_remove_modifier": frozenset({'modifier_id', 'reason', 'source', 'target'}),
    "battle_end": frozenset({'reason'}),
    "before_actor_exit": frozenset({'actor', 'reason'}),
    "before_consume": frozenset({'actor', 'amount', 'reason', 'resource_id'}),
    "before_drain": frozenset({'action_id', 'amount', 'floor', 'reason', 'source', 'target'}),
    "before_take_damage": frozenset({'action_type', 'amount', 'damage_type', 'is_critical', 'source', 'target'}),
    "on_action": frozenset({'action_id', 'action_type', 'actor', 'actor_type', 'insert', 'sp_consumed', 'tag', 'target', 'target_type'}),
    "aha_instant_end": frozenset({'actors', 'consumed', 'extra'}),
    "aha_instant_start": frozenset({'actors', 'consumed', 'extra'}),
    "on_battle_start": frozenset({'encounter'}),
    "on_become_target": frozenset({'action_id', 'action_type', 'insert', 'source', 'target'}),
    "on_break": frozenset({'bar_index', 'element', 'source', 'target'}),
    "on_cycle_end": frozenset({'cycle_index'}),
    "on_cycle_start": frozenset({'budget', 'cycle_index'}),
    "on_dot_retrigger": frozenset({'modifier_id', 'target'}),
    "on_extra_turn": frozenset({'actor'}),
    "on_gain_energy": frozenset({'action_id', 'actor', 'amount', 'err_exempt', 'reason', 'source'}),
    "on_hp_decrease": frozenset({'action_type', 'amount', 'damage_type', 'is_critical', 'reason', 'source', 'target'}),
    "on_hp_increase": frozenset({'action_id', 'amount', 'excess', 'reason', 'source', 'target'}),
    "on_hp_lock": frozenset({'action_id', 'source', 'target'}),
    "on_immune": frozenset({'modifier_id', 'target'}),
    "on_kill": frozenset({'action_id', 'source', 'target'}),
    "on_super_break": frozenset({'action_id', 'amount', 'element', 'source', 'target'}),
    "on_resist": frozenset({'chance', 'modifier_id', 'target'}),
    "on_resource_gain": frozenset({'actor', 'amount', 'current', 'overflow', 'resource_id'}),
    "on_revive": frozenset({'hp', 'percent', 'source', 'target'}),
    "on_skill_point_change": frozenset({'after', 'before', 'reason'}),
    "on_state_change": frozenset({'actor', 'from_state', 'to_state'}),
    "on_toughness_damage": frozenset({'amount', 'bar_index', 'source', 'target'}),
    "on_turn_end": frozenset({'actor'}),
    "on_turn_start": frozenset({'actor'}),
    "on_ultimate": frozenset({'action', 'source', 'target'}),
    "on_wave_start": frozenset({'wave_index'}),
    "shield_absorbed": frozenset({'amount', 'remaining', 'shield_id', 'source', 'target'}),
    "shield_broken": frozenset({'shield_id', 'source', 'target'}),
    "toughness_recovered": frozenset({'amount', 'target'}),
}


def _check_payload_keys(event_type: str, payload: Optional[Dict[str, Any]], *,
                        waterfall: bool) -> None:
    """发射侧 payload 键闸：键 ⊆ DEFAULT_PAYLOAD_FIELDS[event]（waterfall 放行链控键
    cancel——modify_event 白名单注入；insert 为 on_action 族注册键不走本通道）。

    契约外事件（未登记/引擎内部临时件）不对账——契约闸另有 DEFAULT_CONTRACT 管。
    """
    allowed = DEFAULT_PAYLOAD_FIELDS.get(event_type)
    if allowed is None or not payload:
        return
    extra = set(payload) - set(allowed) - ({"cancel"} if waterfall else set())
    if extra:
        raise ValueError(
            f"事件 {event_type!r} 的 payload 含未注册键 {sorted(extra)}"
            f"（注册表见 sim/bus.py DEFAULT_PAYLOAD_FIELDS——新增键先同步注册表与收割闸）")


@dataclass
class EventBus:
    """事件总线：emit / waterfall 双通道 + 可改性契约.

    重入软警告：hook 链触发新事件的嵌套深度被计数，超阈值写一条警告日志
    （不掐断——追击队合法长链不受限；真死循环在日志里显形）。
    重入硬帽：深度超 REENTRY_HARD_CAP 抛 RuntimeError——把 RecursionError
    裸崩转成带事件名的可诊断错误（自供能 hook 链的熔断）。
    """

    contract: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CONTRACT))
    _emit_hooks: Dict[str, List[EmitHook]] = field(default_factory=dict)
    _waterfall_hooks: Dict[str, List[WaterfallHook]] = field(default_factory=dict)
    _depth: int = 0
    _warned: bool = False

    REENTRY_WARN_DEPTH = 20  # 重入软警告阈值（合法追击长链 ~10+，留足余量）
    REENTRY_HARD_CAP = 128   # 重入硬帽（熔断阈值；远低于 Python 递归上限 ~1000，先于此崩）

    def subscribe(self, event_type: str, fn: EmitHook) -> None:
        self._emit_hooks.setdefault(event_type, []).append(fn)

    def subscribe_waterfall(self, event_type: str, fn: WaterfallHook) -> None:
        self._waterfall_hooks.setdefault(event_type, []).append(fn)

    def _enter(self, event_type: str, ctx: Any) -> None:
        self._depth += 1
        if self._depth > self.REENTRY_HARD_CAP:
            self._depth -= 1  # 计数还原：抛出后逐层 finally 退栈，深度自然回落
            raise RuntimeError(
                f"事件重入深度撞硬帽 {self.REENTRY_HARD_CAP}（{event_type}）——"
                "hook 自供能链死循环（无燃料耗尽机制），检查相关 hook 的触发条件")
        if self._depth > self.REENTRY_WARN_DEPTH and not self._warned:
            self._warned = True
            log = getattr(ctx, "log", None)
            msg = (f"⚠ 事件重入深度超 {self.REENTRY_WARN_DEPTH}（{event_type}）——"
                   "若非预期的连锁触发，检查相关 hook 是否缺燃料（耗尽型资源）")
            if isinstance(log, list):
                log.append(msg)

    def _exit(self) -> None:
        self._depth -= 1
        if self._depth <= 0:
            self._depth = 0
            self._warned = False

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None, ctx: Any = None) -> None:
        """只读事实通知；对 waterfall 事件调用本方法 = 错误（契约校验）."""
        kind = self.contract.get(event_type, "emit")
        if kind == "waterfall":
            raise ValueError(f"事件 {event_type} 是 waterfall，必须用 bus.waterfall() 发射")
        _check_payload_keys(event_type, payload, waterfall=False)
        self._enter(event_type, ctx)
        try:
            for fn in self._emit_hooks.get(event_type, []):
                fn(event_type, payload or {}, ctx)
        finally:
            self._exit()

    def waterfall(self, event_type: str, payload: Optional[Dict[str, Any]] = None, ctx: Any = None) -> Dict[str, Any]:
        """可修改事件：hook 链逐级改写 payload（v0.1 可改键：amount / cancel）."""
        kind = self.contract.get(event_type, "emit")
        if kind == "emit":
            raise ValueError(f"事件 {event_type} 是 emit（只读），禁止 modify_event")
        _check_payload_keys(event_type, payload, waterfall=True)
        self._enter(event_type, ctx)
        try:
            current = dict(payload or {})
            for fn in self._waterfall_hooks.get(event_type, []):
                updated = fn(event_type, current, ctx)
                if updated is None:
                    continue
                # v0.1 白名单：只允许 amount / cancel 被改写
                for key in updated:
                    if key not in ("amount", "cancel"):
                        raise ValueError(f"modify_event 白名单禁止改写字段 {key}（v0.1 仅 amount/cancel）")
                current.update(updated)
                if current.get("cancel"):
                    break
            return current
        finally:
            self._exit()
