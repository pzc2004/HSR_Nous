"""Registered, fixed research protocols."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ResolvedProtocol:
    protocol_id: str
    mode: str
    dev_seeds: tuple[int, ...]
    holdout_seeds: tuple[int, ...]
    min_valid_n: int
    bootstrap_resamples: int
    confidence: float
    bootstrap_seed: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "dev_seeds", tuple(self.dev_seeds))
        object.__setattr__(self, "holdout_seeds", tuple(self.holdout_seeds))
        if self.mode != "roll":
            raise ValueError("only roll mode is supported")
        for name, seeds in (
            ("dev_seeds", self.dev_seeds),
            ("holdout_seeds", self.holdout_seeds),
        ):
            if not seeds:
                raise ValueError(f"{name} must not be empty")
            if any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
                   for seed in seeds):
                raise ValueError(f"{name} must contain non-negative integers")
            if len(set(seeds)) != len(seeds):
                raise ValueError(f"{name} must not contain duplicate seeds")
        if set(self.dev_seeds) & set(self.holdout_seeds):
            raise ValueError("dev_seeds and holdout_seeds must be disjoint")
        if (isinstance(self.min_valid_n, bool) or not isinstance(self.min_valid_n, int)
                or not 1 <= self.min_valid_n <= min(
                    len(self.dev_seeds), len(self.holdout_seeds))):
            raise ValueError("min_valid_n must fit both cohorts")
        if (isinstance(self.bootstrap_resamples, bool)
                or not isinstance(self.bootstrap_resamples, int)
                or self.bootstrap_resamples <= 0):
            raise ValueError("bootstrap_resamples must be a positive integer")
        if not math.isfinite(self.confidence) or not 0.0 < self.confidence < 1.0:
            raise ValueError("confidence must be finite and between zero and one")
        if (isinstance(self.bootstrap_seed, bool)
                or not isinstance(self.bootstrap_seed, int)
                or self.bootstrap_seed < 0):
            raise ValueError("bootstrap_seed must be a non-negative integer")

    @property
    def required_runs(self) -> int:
        return 2 * (len(self.dev_seeds) + len(self.holdout_seeds))


PAIRED_V1 = ResolvedProtocol(
    protocol_id="paired-v1",
    mode="roll",
    dev_seeds=tuple(range(16)),
    holdout_seeds=tuple(range(16, 32)),
    min_valid_n=16,
    bootstrap_resamples=2000,
    confidence=0.95,
    bootstrap_seed=0,
)

PROTOCOL_PROFILES: Mapping[str, ResolvedProtocol] = MappingProxyType({
    PAIRED_V1.protocol_id: PAIRED_V1,
})


def get_profile(protocol_id: str) -> ResolvedProtocol:
    return PROTOCOL_PROFILES[protocol_id]
