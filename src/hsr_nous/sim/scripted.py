"""固定随机序列与严格世界线执行。"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Optional

from hsr_nous.sim.compile.compiled import CompiledEncounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.montecarlo import OutcomeRecord, classify_outcome
from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim.state import BattleState


class ScriptedRandom(random.Random):
    """按调用顺序返回固定随机值，不伪装成 seed 随机源。"""

    def __init__(self, values: Iterable[float]) -> None:
        checked: list[float] = []
        for index, value in enumerate(values):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"随机脚本[{index}] 须为实数，实得 {value!r}")
            number = float(value)
            if not math.isfinite(number) or not 0.0 <= number < 1.0:
                raise ValueError(f"随机脚本[{index}] 须满足 0 <= value < 1，实得 {value!r}")
            checked.append(number)
        self._values = tuple(checked)
        self._cursor = 0
        super().__init__(0)

    @property
    def consumed(self) -> int:
        return self._cursor

    @property
    def remaining(self) -> tuple[float, ...]:
        return self._values[self._cursor:]

    def random(self) -> float:
        if self._cursor >= len(self._values):
            raise RuntimeError(
                f"脚本随机值已耗尽：引擎请求第 {self._cursor + 1} 个值，"
                f"脚本只有 {len(self._values)} 个")
        value = self._values[self._cursor]
        self._cursor += 1
        return value

    def _randbelow(self, n: int) -> int:
        if n <= 1:
            return 0
        return int(self.random() * n)

    def require_exhausted(self) -> None:
        if self.remaining:
            raise RuntimeError(
                f"脚本随机值未全部消费：已消费 {self.consumed}/{len(self._values)}，"
                f"剩余 {len(self.remaining)} 个（下一值 {self.remaining[0]!r}）")


@dataclass(frozen=True)
class ScriptedResult:
    state: BattleState
    record: OutcomeRecord
    random_source: ScriptedRandom

    @property
    def outcome(self) -> str:
        return self.record.outcome

    @property
    def action_value(self) -> float:
        return self.record.action_value


def run_scripted(
    compiled: CompiledEncounter,
    random_values: Iterable[float],
    *,
    seed: Optional[int] = None,
    initial_sp: Optional[int] = None,
    initial_energy_ratio: Optional[float] = None,
) -> ScriptedResult:
    """用固定随机序列实际执行一场 roll 战斗，seed 不参与脚本语义。"""
    rng = ScriptedRandom(random_values)
    engine = CombatEngine.from_compiled(
        compiled,
        mode=MODE_ROLL,
        seed=seed,
        initial_sp=initial_sp,
        initial_energy_ratio=initial_energy_ratio,
    )
    engine.pipeline.rng = rng
    state = engine.run()
    rng.require_exhausted()
    record = classify_outcome(engine, seed=0 if seed is None else seed)
    return ScriptedResult(state=state, record=record, random_source=rng)
