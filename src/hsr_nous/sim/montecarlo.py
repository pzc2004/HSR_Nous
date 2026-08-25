"""多局统计聚合：roll 模式 N 局 → 伤害分布（v0.8 方差）.

用途：把"这个配队/策略的方差有多大"从感觉变成数字——均值、离散度、分位数。
铁律：每局从工厂完整重建（B16 纯净不变量），绝复用引擎实例；
     seed 逐局递增（seed0+i），同 seed0 两趟聚合逐字段全等。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.state import BattleState


@dataclass(frozen=True)
class DistributionStats:
    """N 局 total_damage 的分布摘要（truncated 截断局只计数不进样本——毒数据防线）."""

    n: int
    mean: float
    stdev: float
    minimum: float
    p5: float
    p50: float
    p95: float
    maximum: float
    n_truncated: int = 0  # 撞兜底上限被截断的局数（未计入均值/分位数）

    def summary(self) -> str:
        return (
            f"n={self.n} mean={self.mean:,.0f} σ={self.stdev:,.0f} "
            f"[p5={self.p5:,.0f} p50={self.p50:,.0f} p95={self.p95:,.0f}]"
            + (f" truncated={self.n_truncated}" if self.n_truncated else "")
        )


def _percentile(sorted_vals: List[float], q: float) -> float:
    """线性插值分位数（q ∈ [0,1]；sorted_vals 已升序）."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def summarize(values: List[float]) -> DistributionStats:
    """原始样本 → 分布摘要（纯函数，可单测）."""
    assert values, "样本不能为空"
    vals = sorted(values)
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return DistributionStats(
        n=n, mean=mean, stdev=var ** 0.5,
        minimum=vals[0], p5=_percentile(vals, 0.05),
        p50=_percentile(vals, 0.50), p95=_percentile(vals, 0.95),
        maximum=vals[-1],
    )


def run_distribution(
    engine_factory: Callable[[int], CombatEngine],
    n: int = 100,
    *,
    seed0: int = 0,
) -> DistributionStats:
    """跑 N 局聚合 total_damage 分布.

    engine_factory(seed) 必须返回**全新**引擎（B16：每局从编译产物重建）；
    引擎内部 seed 由工厂按入参设置——聚合器只管发 seed，不管引擎内部怎么用。

    truncated（撞 MAX_TURNS_SAFETY 没打完）的局**不进样本**（均值/分位数只统计
    完整局），单独计入返回值的 n_truncated——截断局是毒数据，不得当合法优化样本。
    """
    samples: List[float] = []
    n_truncated = 0
    for i in range(n):
        engine = engine_factory(seed0 + i)
        state: BattleState = engine.run()
        if state.truncated:
            n_truncated += 1
            continue
        samples.append(state.total_damage)
    if not samples:
        raise ValueError(
            f"N={n} 局全部 truncated（撞兜底上限没打完），无完整局可统计——"
            "先排查死循环/不可终止配置再聚合"
        )
    stats = summarize(samples)
    return DistributionStats(
        n=stats.n, mean=stats.mean, stdev=stats.stdev, minimum=stats.minimum,
        p5=stats.p5, p50=stats.p50, p95=stats.p95, maximum=stats.maximum,
        n_truncated=n_truncated,
    )
