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
    "on_gain_energy": "waterfall",  # before_gain：能量获得量可被改写
    "on_ultimate": "emit",
}


@dataclass
class EventBus:
    """事件总线：emit / waterfall 双通道 + 可改性契约."""

    contract: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CONTRACT))
    _emit_hooks: Dict[str, List[EmitHook]] = field(default_factory=dict)
    _waterfall_hooks: Dict[str, List[WaterfallHook]] = field(default_factory=dict)

    def subscribe(self, event_type: str, fn: EmitHook) -> None:
        self._emit_hooks.setdefault(event_type, []).append(fn)

    def subscribe_waterfall(self, event_type: str, fn: WaterfallHook) -> None:
        self._waterfall_hooks.setdefault(event_type, []).append(fn)

    def declare(self, event_type: str, mutability: str) -> None:
        """声明新发射点（发射点生成式：引擎变更操作对应的发射在此登记）."""
        assert mutability in ("emit", "waterfall")
        self.contract[event_type] = mutability

    def emit(self, event_type: str, payload: Optional[Dict[str, Any]] = None, ctx: Any = None) -> None:
        """只读事实通知；对 waterfall 事件调用本方法 = 错误（契约校验）."""
        kind = self.contract.get(event_type, "emit")
        if kind == "waterfall":
            raise ValueError(f"事件 {event_type} 是 waterfall，必须用 bus.waterfall() 发射")
        for fn in self._emit_hooks.get(event_type, []):
            fn(event_type, payload or {}, ctx)

    def waterfall(self, event_type: str, payload: Optional[Dict[str, Any]] = None, ctx: Any = None) -> Dict[str, Any]:
        """可修改事件：hook 链逐级改写 payload（v0.1 可改键：amount / cancel）."""
        kind = self.contract.get(event_type, "emit")
        if kind == "emit":
            raise ValueError(f"事件 {event_type} 是 emit（只读），禁止 modify_event")
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

    def snapshot(self) -> Dict[str, Any]:
        return {
            "contract": dict(self.contract),
            "emit_hooks": {k: len(v) for k, v in self._emit_hooks.items()},
            "waterfall_hooks": {k: len(v) for k, v in self._waterfall_hooks.items()},
        }
