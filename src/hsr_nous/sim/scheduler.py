"""调度核心：全局时钟 + 数组化红黑树（CFS 同构）.

规则锚点（docs/mechanics/03_action_sequence.md）：
- AV = 10000 / 速度；绝对时刻键调度（零减法、零浮点累积）
- 拉条/推条 = 基础行动值（10000/spd）的 X% 绝对扣减/增加；AV=0 时拉条无效
- 额外回合两类型：正常回合类（吃回合事件）/ 倒计时类（不广播，但自身回合点存在）
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from hsr_nous.sim.avtree import AVTree
from hsr_nous.sim_schema.actor import Actor

DISTANCE = 10000.0
AV_HARD_CAP = 999.0  # 显示层硬钳（待实测，暂按硬钳）

# 额外回合类型
EXTRA_NORMAL = "normal_extra"  # 吃回合事件（与普通回合 kind="normal" 区分，发射 on_extra_turn）
EXTRA_COUNTDOWN = "countdown"  # 不广播，自身回合点存在


class Scheduler:
    """行动值调度器：绝对时刻键的有序平衡树 + 额外回合队列."""

    def __init__(self, actors: List[Actor]) -> None:
        self._tree = AVTree()
        self._actors: Dict[int, Actor] = {}
        self._handles: Dict[str, int] = {}  # actor_id → 实体句柄（int）
        self._tie_of: Dict[int, int] = {}   # 实体句柄 → 稳定 tie_break（我方先于敌方、编队位小者先）
        self._frozen: set[int] = set()       # banish/冻结：键保留，pop 时略过
        self._extra_queue: List[Tuple[int, str]] = []  # (实体句柄, 额外回合类型) FIFO
        self._countdown: Dict[int, Dict[str, float]] = {}  # 倒计时回合状态（句柄 → {left, spd}）
        self.clock: float = 0.0
        for i, actor in enumerate(actors):
            handle = i + 1
            self._actors[handle] = actor
            self._handles[actor.actor_id] = handle
            self._tie_of[handle] = i
            self._tree.insert(self._initial_av(actor), tie=i, entity=handle)

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------

    @staticmethod
    def _initial_av(actor: Actor) -> float:
        spd = max(actor.stats.spd, 1e-6)
        return DISTANCE / spd

    def handle_of(self, actor_id: str) -> int:
        return self._handles[actor_id]

    def actor_of(self, handle: int) -> Actor:
        return self._actors[handle]

    def add_actor(self, actor: Actor) -> None:
        """波次新敌人登场：按当前时钟挂入行动条."""
        handle = max(self._actors, default=0) + 1
        self._actors[handle] = actor
        self._handles[actor.actor_id] = handle
        self._tie_of[handle] = handle
        self._tree.insert(self.clock + self._initial_av(actor), tie=handle, entity=handle)

    def freeze(self, actor_id: str) -> None:
        self._frozen.add(self._handles[actor_id])

    def unfreeze(self, actor_id: str) -> None:
        self._frozen.discard(self._handles[actor_id])

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------

    def grant_extra_turn(self, actor_id: str, kind: str = EXTRA_NORMAL) -> None:
        """授予额外回合（FIFO 队首执行；倒计时类不广播但自身回合点存在）."""
        self._extra_queue.append((self._handles[actor_id], kind))

    def grant_countdown(self, actor_id: str, n: int, spd: float) -> None:
        """倒计时回合（白厄变身族）：按**固定速度占 AV 流逝**，排入行动条不走即时队列.

        与 grant_extra_turn 的区别：倒计时是"连续 N 个真实回合"（怪在期间正常行动、
        队友 banish 真实持续），不是"同一时刻连插 N 动"。
        """
        handle = self._handles[actor_id]
        self._countdown[handle] = {"left": n, "spd": max(spd, 1e-6)}
        self._reschedule(self._actors[handle], self.clock + DISTANCE / max(spd, 1e-6))

    def next_actor(self) -> Tuple[Actor, str, float]:
        """取下一行动者，返回 (actor, 回合类型, now).

        额外回合队列优先于正常行动条（额外回合优先级高于普通回合，mechanics 03）。
        回合类型："normal"（正常回合）/ EXTRA_NORMAL / EXTRA_COUNTDOWN。
        """
        if self._extra_queue:
            handle, kind = self._extra_queue.pop(0)
            return self._actors[handle], kind, self.clock

        while True:
            time, _tie, handle = self._tree.pop_min()
            self.clock = time
            if handle in self._frozen:
                # 冻结者键保留语义：按原周期重新挂起但跳过本次行动
                self._tree.insert(time + self._initial_av(self._actors[handle]), tie=_tie, entity=handle)
                continue
            cd = self._countdown.get(handle)
            if cd is not None:
                # 倒计时回合：按倒计时速度流逝，耗尽后恢复正常速度
                cd["left"] -= 1
                if cd["left"] > 0:
                    self._tree.insert(time + DISTANCE / cd["spd"], tie=_tie, entity=handle)
                else:
                    del self._countdown[handle]
                    self._tree.insert(time + self._initial_av(self._actors[handle]), tie=_tie, entity=handle)
                return self._actors[handle], EXTRA_COUNTDOWN, self.clock
            # 行动后按当前速度重挂（绝对时刻 = now + 10000/spd）
            self._tree.insert(time + self._initial_av(self._actors[handle]), tie=_tie, entity=handle)
            return self._actors[handle], "normal", self.clock

    # ------------------------------------------------------------------
    # 拉条/推条/速度变化
    # ------------------------------------------------------------------

    def _reschedule(self, actor: Actor, new_time: float) -> None:
        handle = self._handles[actor.actor_id]
        self._tree.delete(handle)
        self._tree.insert(new_time, tie=self._tie_of[handle], entity=handle)

    def current_av(self, actor: Actor) -> float:
        """查询当前剩余 AV（调试用）."""
        # 当前键时刻 - 时钟；树中存储的是绝对时刻
        handle = self._handles[actor.actor_id]
        for t, _tie, h in self._tree.ordered():
            if h == handle:
                return max(0.0, t - self.clock)
        return 0.0

    def _time_of(self, handle: int) -> float:
        for t, _tie, h in self._tree.ordered():
            if h == handle:
                return t
        raise KeyError(handle)

    def advance_action(self, actor: Actor, pct: float) -> None:
        """拉条（行动提前 pct）：按基础行动值的 pct 绝对扣减；AV=0 时无效."""
        handle = self._handles[actor.actor_id]
        cur = self._time_of(handle)
        if cur - self.clock <= 0.0:
            return  # AV=0 拉条无效（mechanics 03 钉死）
        delta = self._initial_av(actor) * pct
        self._reschedule(actor, max(self.clock, cur - delta))

    def delay_action(self, actor: Actor, pct: float) -> None:
        """推条（行动延后 pct）：按基础行动值的 pct 绝对增加."""
        handle = self._handles[actor.actor_id]
        cur = self._time_of(handle)
        delta = self._initial_av(actor) * pct
        self._reschedule(actor, cur + delta)

    def act_now(self, actor: Actor) -> None:
        """立即行动：直接拉到当前时钟（无视推条）."""
        handle = self._handles[actor.actor_id]
        self._reschedule(actor, self.clock)

    def on_speed_change(self, actor: Actor, old_spd: float, new_spd: float) -> None:
        """速度变化：剩余 AV 按 old/new 等比缩放."""
        if new_spd <= 0:
            return
        handle = self._handles[actor.actor_id]
        cur = self._time_of(handle)
        remaining = (cur - self.clock) * old_spd / new_spd
        self._reschedule(actor, self.clock + remaining)

    def preview(self, n: int = 10) -> List[Tuple[str, float]]:
        """行动条预览 [(actor_id, 剩余AV), ...]（调试第一视图）."""
        out: List[Tuple[str, float]] = []
        for t, _tie, h in self._tree.ordered():
            if h in self._frozen:
                continue
            out.append((self._actors[h].actor_id, max(0.0, t - self.clock)))
            if len(out) >= n:
                break
        return out

    def snapshot(self) -> dict:
        return {
            "clock": round(self.clock, 4),
            "tree": self._tree.snapshot(),
            "frozen": sorted(self._frozen),
            "extra_queue": [[h, k] for h, k in self._extra_queue],
        }
