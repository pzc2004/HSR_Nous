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
DEFAULT_CONTRACT: Dict[str, str] = {
    "on_battle_start": "emit",
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
    "actor_exit": "emit",
    "actor_enter": "emit",
    "on_toughness_damage": "emit",
    "toughness_recovered": "waterfall",  # 敌方回合开始韧性恢复结算前（cancel=阻止本次恢复、保持击破——残梅绽族）
    "on_gain_energy": "waterfall",  # before_gain：能量获得量可被改写
    "on_resource_gain": "emit",     # 自定义资源获得后（银行转移/阈值触发族的挂载点）
    "on_become_target": "emit",     # 成为技能目标（140804"成为目标获火种/队友给暴伤"族的挂载点）
    "on_state_change": "emit",      # 形态进入/退出（大行迹/境界族的挂载点）
    "on_break": "emit",
    "on_dot_retrigger": "emit",
    "after_apply_modifier": "emit",
    "after_remove_modifier": "emit",
    "on_immune": "emit",
    "on_resist": "emit",
    "on_ultimate": "emit",
    "shield_absorbed": "emit",  # 护盾逐实例吸收（payload 带 shield_id/amount/remaining/source/target）
    "shield_broken": "emit",    # 护盾后台破裂（级联摘除关联 modifier，reason=shield_broken）
    "on_revive": "emit",        # 死亡检查触发复活（消费复活件，按百分比回拉 HP）
}


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

    def snapshot(self) -> Dict[str, Any]:
        return {
            "contract": dict(self.contract),
            "emit_hooks": {k: len(v) for k, v in self._emit_hooks.items()},
            "waterfall_hooks": {k: len(v) for k, v in self._waterfall_hooks.items()},
        }
