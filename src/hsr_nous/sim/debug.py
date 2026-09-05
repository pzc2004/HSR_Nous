"""调试控制器（debug controller）：单步 / 断点 / 检视 / 快照 / 回退——CLI 与网页端共用的本体.

包一台 `CombatEngine`，把"一口气跑完"变成"走过去、走回去"。
- 推进：`step_turn()` 单调度回合 / `continue_()` 跑到断点或终局
- 断点：`break_on_turn(n)` / `break_on_actor(id)`
- 检视：`action_bar()` 行动条预览 / `inspect()` 单单位 / `field()` 全场概览 / `new_logs()` 增量日志
- 快照：`snapshot()` 当前局面纯数据字典（B16 可序列化的载体）
- 回退：`trace` 轨迹簿 + `back(n)` / `goto_turn(n)`——稀疏检查点（整机深拷贝）
  + 段内重放（决策簿：每次手动选择的 action_id，本身就是可落盘的最小轨迹）
- 手动：`set_action_hook()` 接管决策点 / `set_auto()` 交还编译策略

（名册代号 oronyx/岁月泰坦，见 sim/README.md 命名名册——泰坦名只活文档，不进标识符。）
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy

# 手动决策回调：吃合法行动列表，返回选中的行动（返回 None = 退化默认轮转）
ActionHook = Callable[[List[Any]], Optional[Any]]

# 检查点间隔（每 N 动存一档整机深拷贝；档间靠决策簿重放填缝）
DEFAULT_CHECKPOINT_INTERVAL = 20

# 手动 ult 闭包专用哨兵：交回 Scripted 旧自动口径（重放段 / 未挂手动 ult hook 时）
_AUTO_ULT = object()


class _ManualPolicy(ScriptedPolicy):
    """手动决策源（统一决策接口的手动实现）：行动/目标/终结技都挂回调；回调放弃时退化默认/缺省。"""

    def __init__(self, action_hook: Optional[ActionHook] = None,
                 target_hook: Optional[Any] = None, ult_hook: Optional[Any] = None,
                 **kw: Any) -> None:
        super().__init__(**kw)
        self._action_hook = action_hook
        self._target_hook = target_hook
        self._ult_hook = ult_hook

    def select_action(self, actor_state: Any, legal: List[Any], engine: Any = None) -> Any:
        if self._action_hook is not None:
            picked = self._action_hook(list(legal))
            if picked is not None:
                return picked
        return super().select_action(actor_state, legal, engine)

    def select_target(self, actor_state: Any, action_type: str, candidates: list, engine: Any = None) -> Any:
        if self._target_hook is not None:
            picked = self._target_hook(actor_state, action_type, list(candidates))
            if picked is not None:
                return picked
        return None  # 手动目标缺省 = 引擎缺省（首个存活敌人/自己）

    def select_ultimate(self, actor_state: Any, ready: list, engine: Any = None) -> Any:
        """手动终结技窗口：hook 回答 Action=放 / None=本窗口不放（skip）；
        哨兵 _AUTO_ULT=交回旧自动口径（重放段、未挂 hook——CLI REPL 旧行为）。"""
        if self._ult_hook is not None:
            picked = self._ult_hook(actor_state, list(ready))
            if picked is _AUTO_ULT:
                return super().select_ultimate(actor_state, ready, engine)
            return picked
        return super().select_ultimate(actor_state, ready, engine)


class DebugController:
    """调试控制器（debug controller）：引擎的棋钟、望远镜与回放机。名册代号 oronyx。"""

    def __init__(
        self,
        engine: CombatEngine,
        *,
        enable_rewind: bool = True,
        checkpoint_interval: int = DEFAULT_CHECKPOINT_INTERVAL,
    ) -> None:
        self.engine = engine
        self._rewind = enable_rewind
        self._interval = max(1, checkpoint_interval)
        self._break_turns: set[int] = set()
        self._break_actors: set[str] = set()
        self._log_cursor = 0
        self._done = False
        self.last_record: Optional[Dict[str, Any]] = None
        # 回退三本账：轻量轨迹簿（展示）/ 决策簿（turn_count → action_id，最小可落盘轨迹）/
        # 检查点簿（(turn_count, 整机深拷贝)，按间隔稀疏）
        self._trace: List[Dict[str, Any]] = []
        self._checkpoints: List[tuple[int, CombatEngine]] = []
        # 决策共享室：引擎深拷贝时闭包按引用穿过（函数是原子拷贝），所有检查点引擎共享
        # 同一本账——绝不能把 controller 的 bound method 挂进引擎（深拷贝会连 __self__
        # 一起冻住，重放永远读不到活账本）。
        self._cell: Dict[str, Any] = {
            "user_hook": None,      # 实时模式的手动决策回调（行动）
            "target_hook": None,    # 实时模式的手动决策回调（目标）
            "ult_hook": None,       # 实时模式的手动决策回调（终结技窗口）
            "replay_queue": None,   # None=实时；list=重放段（FIFO 供给 action_id）
            "replay_target_queue": None,  # None=实时；list=重放段（FIFO 供给 target_id，与行动队列对齐）
            "turn_label": 0,        # 当前步的 turn_count（controller 每步前写入）
            "record": [],           # [(turn_count, action_id, target_id|None)] 全量决策簿（含目标）
        }
        self._orig_decision: Any = None  # set_action_hook 前保存的原决策源（set_auto 还原用）

    @classmethod
    def from_compiled(
        cls,
        compiled: Any,
        *,
        mode: str = MODE_EXPECTED,
        seed: Optional[int] = None,
        manual: bool = False,
        action_hook: Optional[ActionHook] = None,
        **kw: Any,
    ) -> "DebugController":
        """从 CompiledEncounter 构建（DSL 模板入口）。manual=True 时决策点全部上交 action_hook。"""
        engine = CombatEngine.from_compiled(compiled, mode=mode, seed=seed, **kw)
        controller = cls(engine)
        if manual:
            controller.set_action_hook(action_hook)
        return controller

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    @property
    def done(self) -> bool:
        return self._done

    @property
    def state(self):  # BattleState（引擎全状态，慎改）
        return self.engine.state

    @property
    def trace(self) -> List[Dict[str, Any]]:
        """轻量轨迹簿（每动一条展示记录）。"""
        return self._trace

    @property
    def decisions(self) -> Dict[int, str]:
        """决策簿（turn_count → action_id）：可落盘的最小轨迹（目标见 decision_targets）。"""
        return {r[0]: r[1] for r in self._cell["record"]}

    @property
    def decision_targets(self) -> Dict[int, Optional[str]]:
        """决策目标簿（turn_count → target_id | None=当时走引擎缺省）。"""
        return {r[0]: r[2] for r in self._cell["record"]}

    # ------------------------------------------------------------------
    # 推进
    # ------------------------------------------------------------------

    def step_turn(self) -> Dict[str, Any]:
        """单步推进一个调度回合，返回本步记录（含增量日志）。"""
        if self._done:
            return {"done": True, "actor_id": None, "logs": []}
        self._ensure_checkpoint0()
        self._cell["turn_label"] = self.state.turn_count
        rec = self.engine.step()
        logs = self.new_logs()
        if rec is None:
            self._done = True
            record: Dict[str, Any] = {"done": True, "actor_id": None, "logs": logs}
        else:
            record = {**rec, "done": False, "logs": logs, "turn_count": self.state.turn_count}
            self._trace.append({k: record[k] for k in ("turn_count", "actor_id", "kind", "clock", "skipped")})
            self._maybe_checkpoint()
        self.last_record = record
        return record

    def continue_(self, max_steps: int = 10000) -> Dict[str, Any]:
        """连续推进直到断点命中或战斗结束，返回最后一步记录。"""
        last: Optional[Dict[str, Any]] = None
        for _ in range(max_steps):
            last = self.step_turn()
            if last["done"] or self._break_hit(last):
                break
        assert last is not None
        return last

    def _break_hit(self, rec: Dict[str, Any]) -> bool:
        if rec.get("done"):
            return False
        if not rec.get("skipped") and rec.get("actor_id") in self._break_actors:
            return True
        return rec.get("turn_count") in self._break_turns

    # ------------------------------------------------------------------
    # 回退（稀疏检查点 + 段内重放）
    # ------------------------------------------------------------------

    def back(self, n: int = 1) -> Dict[str, Any]:
        """回退 n 动（默认 1）。"""
        return self.goto_turn(self.state.turn_count - n)

    def goto_turn(self, n: int) -> Dict[str, Any]:
        """跳到第 n 动：向前=继续跑；向后=最近检查点恢复 + 决策簿重放填缝。"""
        current = self.state.turn_count
        if n == current:
            return self.last_record or {"done": self._done, "actor_id": None, "logs": []}
        if n > current:
            last: Optional[Dict[str, Any]] = None
            while not self._done and self.state.turn_count < n:
                last = self.step_turn()
            assert last is not None
            return last
        # 向后
        if not self._rewind:
            raise RuntimeError("回放未启用（构造时 enable_rewind=False / CLI --no-rewind）")
        if n < 0:
            raise ValueError(f"goto_turn({n})：目标不能为负")
        self._ensure_checkpoint0()
        cp = max((c for c in self._checkpoints if c[0] <= n), key=lambda c: c[0])
        self.engine = copy.deepcopy(cp[1])
        self._done = False
        self._log_cursor = len(self.state.log)
        # 旧未来作废：n 之后的决策/轨迹/检查点全部截断
        record = self._cell["record"]
        record[:] = [r for r in record if r[0] < n]
        self._trace = [e for e in self._trace if e["turn_count"] <= n]
        self._checkpoints = [c for c in self._checkpoints if c[0] <= n]
        # 段内重放填缝：检查点到 n 之间的手动选择排成 FIFO 队列供闭包消费；自动段确定性一致
        self._cell["replay_queue"] = [r[1] for r in record if cp[0] <= r[0] < n]
        self._cell["replay_target_queue"] = [r[2] for r in record if cp[0] <= r[0] < n]
        try:
            last: Optional[Dict[str, Any]] = None
            while not self._done and self.state.turn_count < n:
                last = self.step_turn()
        finally:
            self._cell["replay_queue"] = None
            self._cell["replay_target_queue"] = None
        if last is None:
            # 检查点恰好就在目标动：无需填缝，直接回报落点
            last = {"done": self._done, "actor_id": None, "logs": [],
                    "turn_count": self.state.turn_count}
            self.last_record = last
        return last

    def _ensure_checkpoint0(self) -> None:
        if self._rewind and not self._checkpoints:
            self.engine.setup()
            self._checkpoints.append((self.state.turn_count, copy.deepcopy(self.engine)))

    def _maybe_checkpoint(self) -> None:
        if not self._rewind:
            return
        t = self.state.turn_count
        if t % self._interval == 0 and (not self._checkpoints or self._checkpoints[-1][0] != t):
            self._checkpoints.append((t, copy.deepcopy(self.engine)))

    # ------------------------------------------------------------------
    # 断点
    # ------------------------------------------------------------------

    def break_on_turn(self, turn_count: int) -> None:
        self._break_turns.add(turn_count)

    def break_on_actor(self, actor_id: str) -> None:
        self._break_actors.add(actor_id)

    def clear_breaks(self) -> None:
        self._break_turns.clear()
        self._break_actors.clear()

    # ------------------------------------------------------------------
    # 检视
    # ------------------------------------------------------------------

    def new_logs(self) -> List[str]:
        """自上次读取后的新增战斗日志（游标前进）。"""
        logs = self.state.log[self._log_cursor:]
        self._log_cursor = len(self.state.log)
        return logs

    def action_bar(self, n: int = 10) -> List[Dict[str, Any]]:
        """行动条预览（只读）：[(actor, 回合类型, 预计时刻)]，前 n 条；spd=调度口径当前速度
        （前端幽灵条把 pct 拉/推条换算成 AV 用——距离 10000×pct ÷ spd）。

        倒计时实体额外附一条 kind=state_exit 的"退大终点"（最后一次倒计时回合的时刻），
        与常规条目合并后按 eta 重排——用户要看的是"什么时候退出变身"，不是下一次倒计时动。
        """
        self.engine.setup()
        sch = self.engine.scheduler
        assert sch is not None
        entries = [
            {"actor_id": a.actor_id, "name": a.name, "kind": kind, "eta": round(eta, 1),
             "spd": round(sch.spd_of(sch.handle_of(a.actor_id), 0.0) or 0.0, 1)}
            for a, kind, eta in sch.preview(n)
        ]
        exits = [
            {"actor_id": aid, "name": st.actor.name, "kind": "state_exit",
             "eta": round(eta, 1),
             "spd": round(sch.spd_of(sch.handle_of(aid), 0.0) or 0.0, 1)}
            for aid, st in self.state.actors.items()
            if (eta := sch.form_exit_eta(aid)) is not None
        ]
        entries.extend(exits)
        entries.sort(key=lambda e: e["eta"])
        return entries

    def inspect(self, actor_id: str) -> Dict[str, Any]:
        """单单位检视：HP/能量/韧性/modifier/资源/形态/护盾 全快照。"""
        self.engine.setup()
        return self.state.actors[actor_id].snapshot()

    def field(self) -> Dict[str, Any]:
        """全场概览：时钟/行动数/战技点 + 各单位生存面。"""
        self.engine.setup()
        return {
            "clock": round(self.state.clock, 1),
            "turn_count": self.state.turn_count,
            "cycle_index": self.state.cycle_index,
            "skill_points": self.state.skill_points,
            "total_damage": round(self.state.total_damage, 1),
            "actors": {
                aid: {
                    "name": st.actor.name,
                    "hp": round(st.current_hp, 1),
                    "energy": round(st.current_energy, 1),
                    "alive": st.alive,
                    "broken": st.broken,
                }
                for aid, st in self.state.actors.items()
            },
        }

    def snapshot(self) -> Dict[str, Any]:
        """当前局面全快照（纯数据 dict，可 json 序列化）。"""
        self.engine.setup()
        return self.state.snapshot()

    # ------------------------------------------------------------------
    # 手动 / 自动
    # ------------------------------------------------------------------

    def set_action_hook(self, hook: Optional[ActionHook]) -> None:
        """接管决策点：决策源换成手动实现，合法行动集上交 hook（None 时恢复默认轮转）."""
        if self._orig_decision is None:
            self._orig_decision = self.engine.decision
        self._cell["user_hook"] = hook
        self.engine.decision = _ManualPolicy(
            self._make_decision_hook(), self._make_target_hook(), self._make_ult_hook())

    def set_target_hook(self, hook: Optional[Any]) -> None:
        """手动目标接管：候选目标集 (actor_state, action_type, candidates) 上交 hook（None=引擎缺省）。"""
        self._cell["target_hook"] = hook

    def set_ult_hook(self, hook: Optional[Any]) -> None:
        """手动终结技接管：窗口 ready 清单 (actor_state, ready) 上交 hook.

        hook 回答 Action=放 / None=本窗口不放（skip）。须在 set_action_hook 后调用
        （手动决策源由它创建）；不调用=维持旧自动口径（CLI REPL 现状）。
        """
        self._cell["ult_hook"] = hook

    def set_auto(self) -> None:
        """交还原决策源（manual 的反向切换）。"""
        if self._orig_decision is not None:
            self.engine.decision = self._orig_decision
            self._orig_decision = None
            self._cell["user_hook"] = None
            self._cell["target_hook"] = None
            self._cell["ult_hook"] = None

    def _make_decision_hook(self) -> ActionHook:
        """决策点闭包：只捕获共享室 dict（不捕获 controller——引擎深拷贝时闭包按引用
        穿过，所有检查点引擎共享同一本活账）。重放段消费 FIFO 队列；实时段问用户并记账。"""
        cell = self._cell

        def hook(legal: List[Any]) -> Optional[Any]:
            queue = cell["replay_queue"]
            if queue is not None:
                while queue:
                    action_id = queue.pop(0)
                    hit = next((a for a in legal if a.action_id == action_id), None)
                    if hit is not None:
                        return hit
                return None  # 记录缺失：退化默认轮转
            user_hook = cell["user_hook"]
            if user_hook is None:
                return None
            picked = user_hook(list(legal))
            if picked is not None:
                cell["record"].append((cell["turn_label"], picked.action_id, None))
            return picked

        return hook

    def _make_target_hook(self) -> Any:
        """目标决策闭包（同决策行动闭包的共享室设计：深拷贝按引用穿过，检查点共享活账）。
        实时段问用户并把目标落账到最近一条手动决策记录；重放段消费目标 FIFO 队列。"""
        cell = self._cell

        def target_hook(actor_state: Any, action_type: str, candidates: List[Any]) -> Optional[Any]:
            # 重放段：消费目标队列（与行动队列逐条对齐；元素 None=当时走的引擎缺省）
            tqueue = cell["replay_target_queue"]
            if tqueue is not None:
                while tqueue:
                    tid = tqueue.pop(0)
                    if tid is None:
                        return None
                    return next((c for c in candidates if c.actor.actor_id == tid), None)
                return None
            user_hook = cell["target_hook"]
            if user_hook is None:
                return None
            picked = user_hook(actor_state, action_type, list(candidates))
            # 落账：写进本回合手动决策记录（行动 hook 刚 append 的条目）的第三位
            if cell["record"] and cell["record"][-1][0] == cell["turn_label"]:
                t, a, _ = cell["record"][-1]
                cell["record"][-1] = (t, a, picked.actor.actor_id if picked is not None else None)
            return picked

        return target_hook

    def _make_ult_hook(self) -> Any:
        """终结技窗口闭包（同行动/目标闭包的共享室设计）。重放段与未挂手动 hook 都回哨兵
        _AUTO_ULT（旧自动口径）——**手动 ult 决策不入决策簿**：原局手动放/跳过的 ult 在
        back/goto 重放时按自动口径重算，可能与原局分叉（已知取舍，v2b 文档注明）。"""
        cell = self._cell

        def ult_hook(actor_state: Any, ready: List[Any]) -> Optional[Any]:
            if cell["replay_queue"] is not None:
                return _AUTO_ULT
            user_hook = cell["ult_hook"]
            if user_hook is None:
                return _AUTO_ULT
            return user_hook(actor_state, list(ready))

        return ult_hook
