"""执行帧（ExecutionFrame，裁决卡 designs/DECISIONS.md #26）：一次行动执行的瞬态上下文.

帧随 `engine._execute_action` 同步调用栈生灭（进入压栈 / 正常返回提交 / 异常整帧丢弃
——与 ConfigAI 解释器选不出技能时回滚 dynamic_values 的既有先例同口径），承载两类
"执行内"语义：

1. **写后读**——`set_dynamic_value` 在行动执行内的写入先入覆盖层，同执行内（含同窗
   事件链上后续 hook 的 condition/effect）立即可读；最外层帧提交才把覆盖层合并进
   已提交态（`_enemy_policy_state[...]["dynamic_values"]`），嵌套子帧提交则并入
   父帧覆盖层（子执行 = 完整隔离单元；父帧若回滚，子帧已提交的写入一并丢弃）；
2. **执行级随机绑定**——`roll(key)` 在 effect 求值域首调采样一次（消耗主流
   `pipeline.rng`）并绑定帧内，后续读取零消耗；hook 级 condition（快照域）只许读
   已绑定键、读未绑定显式报错（condition 无副作用的纯洁性不破）；绑定不跨帧提交
   合并——跨执行的战斗级随机记忆走持久态，不归帧。

读取链四层优先级与 roll 分域规则见 `sim_schema/docs/23_event_hook_system.md` §23.15
（事件间快照语义一字未改：快照冻结已提交态，覆盖层只对帧内读者可见——repeatable-read
之上叠 read-your-writes）。

帧是瞬态字段：不进存档（#25 存档口径不变——已提交 dynamic_values 照旧走
`_enemy_policy_state` 存档通道）；战斗任意静止时刻帧栈恒空。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict

from hsr_nous.sim_schema.expression import ExpressionError


@dataclass
class ExecutionFrame:
    """单次行动执行的帧：宿主行动标识 + dynamic_value 覆盖层 + roll 绑定表.

    writes 按 actor_id 分桶（`set_dynamic_value` 是跨 actor 写通道）；rolls 以帧为
    命名空间（不按 actor 分键）——一次执行内所有求值点共享一份绑定。
    """

    action_id: str
    actor_id: str
    writes: Dict[str, Dict[str, float]] = field(default_factory=dict)  # actor_id → key → value
    rolls: Dict[str, float] = field(default_factory=dict)

    def write(self, actor_id: str, key: str, value: float) -> None:
        """覆盖层写入（未提交——仅帧内读者可见，提交时才落已提交态）."""
        self.writes.setdefault(actor_id, {})[key] = float(value)

    def roll_bind(self, key: str, sampler: Callable[[], float]) -> float:
        """effect 求值域：首调采样一次并绑定，后续读取零消耗返回绑定值."""
        if key not in self.rolls:
            self.rolls[key] = float(sampler())
        return self.rolls[key]

    def roll_read(self, key: str) -> float:
        """condition（快照）求值域：只许读已绑定 roll，禁止采样."""
        if key not in self.rolls:
            raise ExpressionError(
                f"roll({key!r}) 未绑定——condition（快照）层只许读已绑定 roll，禁止采样"
                f"（§23.15 分域规则）")
        return self.rolls[key]
