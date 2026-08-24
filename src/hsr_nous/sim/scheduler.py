"""调度核心：全局时钟 + 数组化红黑树（CFS 同构）——**主状态 = 目标路程（距离守恒）**.

距离制模型（KQM 通式 / mechanics 03）：
- 每个实体持有一份**目标路程 goal**（距离，守恒量）——拉条扣距离、推条加距离、行动后 += 10000
- 树的排序键 = **预计时刻 = goal / spd**（派生读数，不是主状态）
- 拉条 = goal -= 10000×pct（纯距离运算，与速度无关）
- **变速时 goal 纹丝不动**——只是派生键按新速度重算（主状态不随属性漂，稳固）
- AV（行动值）= max(0, goal/spd − clock)（前端读数，随速度即时变化）

规则锚点（docs/mechanics/03_action_sequence.md）：
- 距离 = 10000；拉条/推条 = 基础行动距离（10000）的 X% 绝对扣减/增加；剩余距离 ≤ 0 时拉条无效
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
        self._remaining: Dict[int, float] = {}  # 实体句柄 → 剩余距离（距离，守恒主状态）
        self._spd_now: Dict[int, float] = {}  # 实体句柄 → 当前速度（调度器口径；on_speed_change 更新）
        self.clock: float = 0.0
        for i, actor in enumerate(actors):
            handle = i + 1
            self._actors[handle] = actor
            self._handles[actor.actor_id] = handle
            self._tie_of[handle] = i
            self._remaining[handle] = DISTANCE
            self._spd_now[handle] = max(actor.stats.spd, 1e-6)
            self._tree.insert(self._eta(handle), tie=i, entity=handle)

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------

    def _spd_of(self, handle: int) -> float:
        """调度器口径的当前速度（_spd_now；on_speed_change 更新）."""
        return max(self._spd_now[handle], 1e-6)

    def _eff_spd(self, handle: int) -> float:
        """有效速度：倒计时期间用倒计时速度，否则用实体速度."""
        cd = self._countdown.get(handle)
        return cd["spd"] if cd is not None else self._spd_of(handle)

    def _eta(self, handle: int) -> float:
        """预计时刻（派生读数）= clock + remaining / 有效速度."""
        return self.clock + self._remaining[handle] / self._eff_spd(handle)

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
        self._remaining[handle] = DISTANCE
        self._spd_now[handle] = max(actor.stats.spd, 1e-6)
        self._tree.insert(self._eta(handle), tie=handle, entity=handle)

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
        self._remaining[handle] = DISTANCE
        self._reschedule(self._actors[handle], self._eta(handle))

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
            # 时钟推进：所有实体的剩余距离按各自有效速度统一扣减（∫spd dt 的事件驱动结算）
            delta = time - self.clock
            if delta > 0:
                for h, rem in self._remaining.items():
                    self._remaining[h] = max(0.0, rem - delta * self._eff_spd(h))
            self.clock = time
            if handle in self._frozen:
                # 冻结者键保留语义：按原周期重新挂起但跳过本次行动
                self._remaining[handle] = DISTANCE
                self._tree.insert(self._eta(handle), tie=_tie, entity=handle)
                continue
            cd = self._countdown.get(handle)
            if cd is not None:
                # 倒计时回合：按倒计时速度流逝，耗尽后恢复正常速度
                cd["left"] -= 1
                self._remaining[handle] = DISTANCE
                self._tree.insert(self._eta(handle), tie=_tie, entity=handle)
                if cd["left"] <= 0:
                    del self._countdown[handle]
                return self._actors[handle], EXTRA_COUNTDOWN, self.clock
            # 行动后剩余距离重置 10000，派生键 = clock + remaining/spd
            self._remaining[handle] = DISTANCE
            self._tree.insert(self._eta(handle), tie=_tie, entity=handle)
            return self._actors[handle], "normal", self.clock

    # ------------------------------------------------------------------
    # 拉条/推条/速度变化
    # ------------------------------------------------------------------

    def _reschedule(self, actor: Actor, new_time: float) -> None:
        handle = self._handles[actor.actor_id]
        self._tree.delete(handle)
        self._tree.insert(new_time, tie=self._tie_of[handle], entity=handle)

    def reset_action_gauge(self, *, except_countdown: bool = False) -> None:
        """行动条整体重置（忘却之庭转波次）：全体剩余距离置 10000 重排.

        except_countdown=True 时倒计时实体除外——跨波按原行动值续跑
        （mechanics 03 §3.4 倒计时类额外回合；owner 实战确认 2026-08-24）。
        """
        for handle in list(self._remaining):
            if except_countdown and handle in self._countdown:
                continue
            self._remaining[handle] = DISTANCE
            self._tree.delete(handle)
            self._tree.insert(self._eta(handle), tie=self._tie_of[handle], entity=handle)

    def current_av(self, actor: Actor) -> float:
        """查询当前剩余 AV（调试用；= remaining / 有效速度）."""
        handle = self._handles[actor.actor_id]
        return self._remaining[handle] / self._eff_spd(handle)

    def advance_action(self, actor: Actor, pct: float) -> None:
        """拉条（行动提前 pct）：remaining -= 10000×pct（纯距离运算，与速度无关）；剩余距离 ≤ 0 时无效."""
        handle = self._handles[actor.actor_id]
        if self._remaining[handle] <= 1e-9:
            return  # 剩余距离 ≤ 0 拉条无效（mechanics 03 钉死；epsilon 容差防浮点假非零）
        self._remaining[handle] = max(0.0, self._remaining[handle] - DISTANCE * pct)
        self._reschedule(actor, self._eta(handle))

    def delay_action(self, actor: Actor, pct: float) -> None:
        """推条（行动延后 pct）：remaining += 10000×pct."""
        handle = self._handles[actor.actor_id]
        self._remaining[handle] += DISTANCE * pct
        self._reschedule(actor, self._eta(handle))

    def act_now(self, actor: Actor) -> None:
        """立即行动：剩余距离置 0（预计时刻 = clock，无视推条）."""
        handle = self._handles[actor.actor_id]
        self._remaining[handle] = 0.0
        self._reschedule(actor, self._eta(handle))

    def undo_gauge_reset(self, actor: Actor) -> None:
        """撤回 next_actor 弹出处无条件写入的 10000 重置（未行动单位专用——残梅绽阻恢复族）.

        回合弹出时剩余距离已被重置满条；单位本次未行动（恢复被 cancel）不该白赚整条约——
        退回该重置，只保留 hook 推条（残梅绽延后）后的余量。
        """
        handle = self._handles[actor.actor_id]
        self._remaining[handle] = max(0.0, self._remaining[handle] - DISTANCE)
        self._reschedule(actor, self._eta(handle))

    def on_speed_change(self, actor: Actor, old_spd: float, new_spd: float) -> None:
        """速度变化：**remaining 纹丝不动**（距离守恒），更新调度口径速度并按新速度重算派生键（主状态不随属性漂）."""
        if new_spd <= 0:
            return
        handle = self._handles[actor.actor_id]
        self._spd_now[handle] = new_spd
        self._reschedule(actor, self.clock + self._remaining[handle] / new_spd)

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
            "remaining": {h: round(g, 4) for h, g in self._remaining.items()},
        }
