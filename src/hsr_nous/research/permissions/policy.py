"""Immutable capability policy for the external research gateway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PermissionDeniedError(PermissionError):
    """The requested capability is disabled by the trusted policy owner."""


@dataclass(frozen=True)
class CapabilityPolicy:
    allowed_project_root: Path
    policy_version: str = "1"
    allow_read_repo: bool = True
    allow_read_artifacts: bool = True
    allow_write_project: bool = True
    allow_run_simulation: bool = True
    allow_submit_claim: bool = True
    allow_web_search: bool = False
    allow_web_fetch: bool = False
    allowed_web_domains: tuple[str, ...] = ()
    max_web_queries: int = 0
    max_web_fetch: int = 0
    allow_bash: bool = False
    allow_python: bool = False
    allow_docker: bool = False

    def __post_init__(self) -> None:
        if not self.policy_version:
            raise ValueError("policy_version must be non-empty")
        object.__setattr__(self, "allowed_project_root", Path(self.allowed_project_root))
        object.__setattr__(self, "allowed_web_domains", tuple(self.allowed_web_domains))
        if self.max_web_queries < 0 or self.max_web_fetch < 0:
            raise ValueError("web budgets must be non-negative")
