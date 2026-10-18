"""Content-bound experiment fingerprints built on the existing simulator fingerprint."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hsr_nous.common import repo_root
from hsr_nous.research_core.variants import PreparedVariant
from hsr_nous.research_protocol import ResolvedProtocol, validate_fingerprint
from hsr_nous.research_schema import (
    ResearchContract,
    VersionFingerprint,
    canonical_json,
    content_hash,
)
from hsr_nous.sim.montecarlo import collect_version_fingerprint

ARTIFACT_SCHEMA_VERSION = "1"
_SOURCE_PACKAGES = (
    "sim",
    "sim_schema",
    "research_schema",
    "research_protocol",
    "research_core",
)


def implementation_hash(root: Path) -> str:
    """Hash simulator/research Python sources and uv.lock with relative paths."""
    root = Path(root)
    files = []
    for package in _SOURCE_PACKAGES:
        directory = root / "src" / "hsr_nous" / package
        package_files = sorted(directory.rglob("*.py"))
        if not package_files:
            raise FileNotFoundError(f"implementation source package is missing: {directory}")
        files.extend(package_files)
    lock = root / "uv.lock"
    if not lock.is_file():
        raise FileNotFoundError(f"implementation lockfile is missing: {lock}")
    files.append(lock)

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _policy_source(build: dict[str, Any]) -> str | None:
    policy = build.get("policy")
    if policy is None and isinstance(build.get("build"), Mapping):
        policy = build["build"].get("policy")
    return canonical_json(policy) if policy is not None else None


def collect_research_fingerprint(
    contract: ResearchContract,
    resolved: ResolvedProtocol,
    variant: PreparedVariant | None = None,
) -> VersionFingerprint:
    base = collect_version_fingerprint(policy_source=_policy_source(contract.experiment.build))
    config_hash = content_hash({
        "build": contract.experiment.build,
        "stage": contract.experiment.stage,
        "resolved_protocol": resolved,
        "baseline": contract.experiment.baseline,
        "variant": contract.experiment.variant,
    })
    fingerprint = VersionFingerprint(
        rulebook_hash=base.get("rulebook_hash"),
        fixtures_hash=base.get("fixtures_hash"),
        data_hash=base.get("data_hash"),
        policy_hash=base.get("policy_hash"),
        implementation_hash=implementation_hash(repo_root()),
        config_hash=config_hash,
        variant_hash=variant.variant_hash if variant is not None else None,
        protocol_id=resolved.protocol_id,
        artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
        git_commit=base.get("git_commit"),
    )
    return validate_fingerprint(fingerprint, protocol_id=resolved.protocol_id)
