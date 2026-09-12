"""tribios 流式任务调度器：asyncio 任务队列 + 每 key 并发额度，完成一个立刻补一个.

与"分批大调用"相对：任务逐个提交，调度器按 key 并发额度自动跑满——任何任务完成
（成功/进 dead）立刻补下一个，长尾不被最慢任务拖住。同步任务体经 `asyncio.to_thread`
执行（阻塞 HTTP/子进程安全），单事件循环驱动，计数无竞态。

并发闸门 = `_inflight` 计数（单事件循环内先查后派，无 await 穿插，天然无竞态）——
历史上另有每 key 一把 asyncio.Semaphore 双保险，因它会冻住热更后的动态容量
（sem 初值无法调大）已移除，inflight 计数是唯一事实源。

热更新（可选）：挂 `LiveConfig` 后，每个派发 tick 前查文件 mtime，变了才 reload——
concurrency 调大立即加槽 / 调小等在飞自然回落；api_base/model/effort 只影响之后
派发的任务（client endpoint 级热替换，在飞在原端点跑完）。等待任务完成期间按
`live_poll_interval` 醒来轮询，所以调大不等慢任务结束也能生效。

用法::

    scheduler = Scheduler(client)                 # per_key_concurrency 缺省读 client.config
    fut = scheduler.submit(task_fn, label="1202 停云", max_retries=2)
    scheduler.run(progress_fn=print)              # 排空（含重试补位）才返回
    fut.result()                                  # 任务结果（dead 任务 = exception）
    scheduler.dead                                # 人工队列素材：[(label, error, attempts)]
"""
from __future__ import annotations

import asyncio
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, List, Optional, Set

from hsr_nous.llm.client import LLMClient, _KEY_SLOT
from hsr_nous.llm.config import LiveConfig

__all__ = ["Scheduler", "DeadTask"]


@dataclass
class DeadTask:
    """重试限次耗尽的任务（人工队列素材）."""

    label: str
    error: BaseException
    attempts: int          # 总尝试次数（1 + 已用重试）


@dataclass
class _TaskState:
    fn: Callable[[], Any]
    fut: Future
    label: str
    max_retries: int
    retries_used: int = 0


class Scheduler:
    """流式任务调度器：每 key 并发额度（inflight 计数闸），完成一个补一个（不等批）.

    - `submit`：任务进队即返回 concurrent.futures.Future（线程安全）
    - `run`：asyncio 驱动排空——有空 key 额度立刻起新任务，不等当前批
    - 失败任务经 `retry_in` 重入队尾（限 max_retries 次）；次数到 → dead 队列供人工
    - 任务体内 `client.chat()` 自动钉在获得额度的 key 上（contextvar `_KEY_SLOT`）
    - 挂 `live`（LiveConfig）后每派发 tick 前轮询热更文件：concurrency 动态调
      `per_key`（调大立即加槽 / 调小在飞自然回落，不杀在飞）；api_base/model/effort
      经 `client.apply_endpoint` 热替换，只影响之后派发的任务
    """

    def __init__(
        self,
        client: LLMClient,
        per_key_concurrency: Optional[int] = None,
        *,
        live: Optional[LiveConfig] = None,
        live_poll_interval: float = 1.0,
    ) -> None:
        self.client = client
        self._live = live
        self._live_poll_interval = float(live_poll_interval)
        if per_key_concurrency is not None:
            self.per_key = per_key_concurrency
        elif live is not None:
            self.per_key = live.current.concurrency
        else:
            self.per_key = client.config.concurrency
        if self.per_key < 1:
            raise ValueError(f"per_key_concurrency 须 ≥1：{self.per_key}")
        if live is not None:
            # 启动即以热更文件为准（文件先于 run 被编辑过也生效于首次派发）
            ov = live.current
            client.apply_endpoint(api_base=ov.api_base, model=ov.model, effort=ov.effort)
        self._inflight: List[int] = [0] * client.key_count
        self._queue: Deque[_TaskState] = deque()
        self._total = 0
        self._done = 0
        self._retries = 0
        self._dead: List[DeadTask] = []
        self._closed = False

    # ------------------------------------------------------------------
    # 提交 / 状态
    # ------------------------------------------------------------------

    def submit(self, task: Callable[[], Any], *, label: str = "",
               max_retries: int = 2) -> Future:
        """提交任务（run 前排空提交；retry 由 loop 内部重入队）。返回线程安全 Future."""
        if self._closed:
            raise RuntimeError("Scheduler 已 shutdown，拒绝新任务")
        fut: Future = Future()
        self._queue.append(_TaskState(fn=task, fut=fut, label=label or repr(task),
                                      max_retries=max_retries))
        self._total += 1
        return fut

    @property
    def dead(self) -> List[DeadTask]:
        return list(self._dead)

    @property
    def retries(self) -> int:
        return self._retries

    def progress(self) -> str:
        """进度一行：`23/95 完成 · key#1 2/4 · key#2 1/4 · 重试 3 · 人工 1`.

        挂 live 时追加当前生效的 endpoint/model/并发（热更后能看出已切换）：
        `… · stub-model @ http://stub · 并发 8/key`。
        """
        keys = " · ".join(
            f"key#{i + 1} {self._inflight[i]}/{self.per_key}"
            for i in range(self.client.key_count))
        line = (f"{self._done}/{self._total} 完成 · {keys}"
                f" · 重试 {self._retries} · 人工 {len(self._dead)}")
        if self._live is not None:
            cfg = self.client.config
            line += f" · {cfg.model} @ {cfg.api_base} · 并发 {self.per_key}/key"
            if self._live.last_error:
                line += f" · 热更配置非法（沿用旧值）：{self._live.last_error}"
        return line

    # ------------------------------------------------------------------
    # 驱动
    # ------------------------------------------------------------------

    def run(self, progress_fn: Optional[Callable[[str], None]] = None) -> None:
        """排空队列（含重试补位）才返回。progress_fn 在每个任务终态（成功/dead）时回调一行."""
        if self._closed:
            raise RuntimeError("Scheduler 已 shutdown")
        try:
            asyncio.run(self._drain(progress_fn))
        finally:
            self._closed = True

    def shutdown(self) -> None:
        """关闭（API 对称：run 后自然关闭；shutdown 后拒绝新提交）."""
        self._closed = True

    def _poll_live(self) -> None:
        """派发 tick 前查热更文件（mtime 变才 reload）：并发调 per_key，端点 client 热替换."""
        if self._live is None:
            return
        ov = self._live.poll()
        if ov is None:
            return
        self.per_key = ov.concurrency
        self.client.apply_endpoint(api_base=ov.api_base, model=ov.model, effort=ov.effort)

    def _pick_key(self) -> Optional[int]:
        """在飞数最少的空闲 key（None = 全部跑满）."""
        best: Optional[int] = None
        for i in range(self.client.key_count):
            if self._inflight[i] >= self.per_key:
                continue
            if best is None or self._inflight[i] < self._inflight[best]:
                best = i
        return best

    async def _drain(self, progress_fn: Optional[Callable[[str], None]]) -> None:
        pending: Set[asyncio.Task] = set()
        # 挂 live 时等待带超时：慢任务在飞期间也按 poll 间隔醒来查热更（调大立即加槽的关键）
        wait_timeout = self._live_poll_interval if self._live is not None else None
        while self._queue or pending:
            self._poll_live()  # 每派发 tick 前查热更新
            # 补位：有空 key 额度立刻起新任务（完成一个补一个的核心）
            while self._queue:
                ki = self._pick_key()
                if ki is None:
                    break
                ts = self._queue.popleft()
                self._inflight[ki] += 1
                pending.add(asyncio.create_task(self._run_one(ts, ki, progress_fn)))
            if not pending:
                break
            done, pending = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED, timeout=wait_timeout)

    async def _run_one(self, ts: _TaskState, key_index: int,
                       progress_fn: Optional[Callable[[str], None]]) -> None:
        try:
            _KEY_SLOT.set(key_index)  # to_thread 传播 context——chat 钉在本 key
            try:
                result = await asyncio.to_thread(ts.fn)
            except Exception as exc:  # noqa: BLE001——调度器不评判任务异常，一律走限次重试
                requeued = self.retry_in(ts, exc)
                if not requeued and progress_fn is not None:  # 进 dead 也是终态，刷一行
                    progress_fn(self.progress())
            else:
                if not ts.fut.done():
                    ts.fut.set_result(result)
                self._done += 1
                if progress_fn is not None:
                    progress_fn(self.progress())
        finally:
            self._inflight[key_index] -= 1

    def retry_in(self, ts: _TaskState, exc: BaseException) -> bool:
        """失败任务重入队尾（限次）；次数到 → dead 队列供人工，Future 置异常.

        返回 True = 已重入队（还会再跑）；False = 已进 dead 队列（终态）。
        """
        if ts.retries_used < ts.max_retries:
            ts.retries_used += 1
            self._retries += 1
            self._queue.append(ts)
            return True
        self._dead.append(DeadTask(label=ts.label, error=exc, attempts=ts.retries_used + 1))
        if not ts.fut.done():
            ts.fut.set_exception(exc)
        return False
