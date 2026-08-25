"""调度器调试视图（测试专用辅助）：行动条预览 / 剩余 AV / 内部状态快照.

原为 `sim/scheduler.py` 上的方法——生产路径零调用（纯测试消费），挪到测试侧
保持生产面干净；直接读调度器内部字段（测试白箱，不承诺稳定接口）。
"""
from __future__ import annotations

from typing import List, Tuple

from hsr_nous.sim.scheduler import Scheduler
from hsr_nous.sim_schema.actor import Actor


def preview(sch: Scheduler, n: int = 10) -> List[Tuple[str, float]]:
    """行动条预览 [(actor_id, 剩余AV), ...]（调试第一视图）."""
    out: List[Tuple[str, float]] = []
    for t, _tie, h in sch._tree.ordered():
        if h in sch._frozen:
            continue
        out.append((sch._actors[h].actor_id, max(0.0, t - sch.clock)))
        if len(out) >= n:
            break
    return out


def current_av(sch: Scheduler, actor: Actor) -> float:
    """查询当前剩余 AV（= remaining / 有效速度）."""
    handle = sch._handles[actor.actor_id]
    return sch._remaining[handle] / sch._eff_spd(handle)


def snapshot(sch: Scheduler) -> dict:
    """调度器内部状态快照（B16 两局全等比对的载体）."""
    return {
        "clock": round(sch.clock, 4),
        "tree": sch._tree.snapshot(),
        "frozen": sorted(sch._frozen),
        "extra_queue": [[h, k] for h, k in sch._extra_queue],
        "remaining": {h: round(g, 4) for h, g in sch._remaining.items()},
        # 倒计时状态 + 调度口径速度（句柄是 int，转 str 键保持序列化风格一致）
        "countdown": {str(h): {"left": cd["left"], "spd": round(cd["spd"], 4)}
                      for h, cd in sch._countdown.items()},
        "spd_now": {str(h): round(s, 4) for h, s in sch._spd_now.items()},
    }
