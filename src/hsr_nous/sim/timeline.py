"""行动序管理：速度条与行动值计算.

核心机制（见 docs/mechanics/03_action_sequence.md）：
- 总路程 10000，行动值 AV = 10000 / 速度
- 所有单位同时消耗行动值，谁先归零谁先行动
- 行动后立刻重置为新的初始行动值
- 支持拉条（行动提前）与推条（行动延后）
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from hsr_nous.sim_schema.actor import Actor

# 行动条总路程
DISTANCE = 10000.0


@dataclass
class TimelineEntry:
    """单个参战单位的行动值状态."""

    actor: Actor
    action_value: float
    order_index: int  # 队伍编排顺序，用于 AV 相同时的 tie-break


class Timeline:
    """管理参战单位的行动顺序（基于行动值的连续时间轴）."""

    def __init__(self, actors: List[Actor]) -> None:
        self.entries: List[TimelineEntry] = [
            TimelineEntry(
                actor=a,
                action_value=self._initial_av(a),
                order_index=i,
            )
            for i, a in enumerate(actors)
        ]
        self.total_elapsed_av: float = 0.0

    @staticmethod
    def _initial_av(actor: Actor) -> float:
        """初始行动值 = 10000 / 速度."""
        spd = max(actor.stats.spd, 1e-6)  # 防止除零
        return DISTANCE / spd

    def _entry_of(self, actor: Actor) -> Optional[TimelineEntry]:
        for e in self.entries:
            if e.actor is actor:
                return e
        return None

    def next_actor(self) -> Tuple[Actor, float]:
        """推进时间轴，返回下一个行动的单位及本次消耗的行动值.

        步骤：
        1. 找到行动值最小的单位（AV 相同时按队伍编排顺序）
        2. 全体减去该最小 AV（时间流逝）
        3. 该单位行动，AV 重置为新的初始值
        """
        if not self.entries:
            raise RuntimeError("时间轴上没有任何参战单位")

        # 找最小 AV，tie-break 用 order_index
        nxt = min(self.entries, key=lambda e: (e.action_value, e.order_index))
        elapsed = nxt.action_value

        # 时间流逝：全体减去 elapsed
        for e in self.entries:
            e.action_value -= elapsed
        self.total_elapsed_av += elapsed

        # 行动单位重置 AV
        nxt.action_value = self._initial_av(nxt.actor)
        return nxt.actor, elapsed

    def advance_action(self, actor: Actor, pct: float) -> None:
        """拉条（行动提前 pct）：当前 AV 减去 10000/速度 × pct，下限 0.

        pct=1.0 等价于提前一个完整行动值（非"立即行动"，见 §3.2）。
        """
        e = self._entry_of(actor)
        if e is None:
            return
        spd = max(actor.stats.spd, 1e-6)
        e.action_value = max(0.0, e.action_value - DISTANCE / spd * pct)

    def delay_action(self, actor: Actor, pct: float) -> None:
        """推条（行动延后 pct）：当前 AV 加上 10000/速度 × pct."""
        e = self._entry_of(actor)
        if e is None:
            return
        spd = max(actor.stats.spd, 1e-6)
        e.action_value += DISTANCE / spd * pct

    def act_now(self, actor: Actor) -> None:
        """立即行动：将单位拉到行动条顶端（AV 归零，无视当前值）."""
        e = self._entry_of(actor)
        if e is not None:
            e.action_value = 0.0

    def on_speed_change(self, actor: Actor, old_spd: float, new_spd: float) -> None:
        """速度变化时按比例调整当前行动值（见 §3.3）.

        变化后行动值 = 当前行动值 × 变化前速度 / 变化后速度
        """
        e = self._entry_of(actor)
        if e is None or new_spd <= 0:
            return
        e.action_value = e.action_value * old_spd / new_spd

    def snapshot(self) -> Dict[str, float]:
        """返回当前各单位的行动值快照（调试用）."""
        return {e.actor.name: round(e.action_value, 3) for e in self.entries}
