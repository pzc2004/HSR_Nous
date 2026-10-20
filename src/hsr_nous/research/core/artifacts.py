"""Canonical, content-addressed research artifacts with accidental-tamper guardrails."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from hsr_nous.research.core.kernel import make_claim_id
from hsr_nous.research.core.variants import PreparedVariant
from hsr_nous.research.protocol import ResolvedProtocol, validate_fingerprint
from hsr_nous.research.schema import (
    Claim,
    ComparisonSet,
    EvidenceLink,
    ExecutionRecord,
    InvestigationState,
    ResearchContract,
    RunRecord,
    TrialArtifact,
    VersionFingerprint,
    canonical_bytes,
    content_hash,
)

_ID_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMPONENT_RE = re.compile(r"[A-Za-z0-9_-]+\Z")


class ArtifactError(Exception):
    pass


class ArtifactConflictError(ArtifactError):
    pass


class ArtifactIntegrityError(ArtifactError):
    pass


class ArtifactPathError(ArtifactError):
    pass


def _fingerprint_identity(fingerprint: VersionFingerprint) -> dict[str, Any]:
    payload = fingerprint.to_dict()
    payload.pop("git_commit", None)
    return payload


def _spec_identity(
    contract: ResearchContract,
    resolved: ResolvedProtocol,
    fingerprint: VersionFingerprint,
) -> dict[str, Any]:
    return {
        "contract": contract,
        "resolved_protocol": resolved,
        "fingerprint": _fingerprint_identity(fingerprint),
    }


def make_trial_id(
    contract: ResearchContract,
    resolved: ResolvedProtocol,
    fingerprint: VersionFingerprint,
) -> str:
    return content_hash(_spec_identity(contract, resolved, fingerprint))


def make_investigation_id(contract: ResearchContract) -> str:
    return content_hash(contract)


def make_execution_id(
    investigation_id: str,
    contract_hash: str,
    kind: str,
    attempt: int,
) -> str:
    return content_hash({
        "investigation_id": investigation_id,
        "contract_hash": contract_hash,
        "kind": kind,
        "attempt": attempt,
    })


def make_run_id(trial_id: str, arm_id: str, cohort: str, seed: int) -> str:
    return content_hash({
        "trial_id": trial_id,
        "arm_id": arm_id,
        "cohort": cohort,
        "seed": seed,
    })


def make_event_id(run_id: str, ordinal: int, event: dict[str, Any]) -> str:
    return content_hash({"run_id": run_id, "ordinal": ordinal, "event": event})


def make_modifier_id(run_id: str, actor_id: str, engine_modifier_id: str) -> str:
    return content_hash({
        "run_id": run_id,
        "actor_id": actor_id,
        "engine_modifier_id": engine_modifier_id,
    })


def _arm_run_ids(
    trial_id: str,
    arm_id: str,
    cohort: str,
    seeds: tuple[int, ...],
) -> tuple[str, ...]:
    return tuple(make_run_id(trial_id, arm_id, cohort, seed) for seed in seeds)


def make_comparison_set(
    trial_id: str,
    contract: ResearchContract,
    resolved: ResolvedProtocol,
) -> ComparisonSet:
    baseline = contract.experiment.baseline.arm_id
    variant = contract.experiment.variant.arm_id
    values = {
        "baseline_dev": _arm_run_ids(trial_id, baseline, "dev", resolved.dev_seeds),
        "baseline_holdout": _arm_run_ids(
            trial_id, baseline, "holdout", resolved.holdout_seeds
        ),
        "variant_dev": _arm_run_ids(trial_id, variant, "dev", resolved.dev_seeds),
        "variant_holdout": _arm_run_ids(
            trial_id, variant, "holdout", resolved.holdout_seeds
        ),
    }
    comparison_set_id = content_hash({"trial_id": trial_id, **values})
    return ComparisonSet(comparison_set_id=comparison_set_id, **values)


def _expected_run_ids(comparison: ComparisonSet) -> tuple[str, ...]:
    return (
        *comparison.baseline_dev,
        *comparison.baseline_holdout,
        *comparison.variant_dev,
        *comparison.variant_holdout,
    )


def run_failure_reason(record: RunRecord) -> str:
    if record.status != "failed":
        raise ArtifactIntegrityError("only failed runs have a failure reason")
    try:
        error = record.observed["error"]
        return f"{record.run_id}: {error['type']}: {error['message']}"
    except (KeyError, TypeError) as exc:
        raise ArtifactIntegrityError("failed run lacks structured error evidence") from exc


def _validate_run_evidence(record: RunRecord) -> None:
    if record.status == "failed":
        if not isinstance(record.observed.get("error"), Mapping) or record.final_save:
            raise ArtifactIntegrityError("failed run must contain error evidence and empty final_save")
        return
    state = record.final_save.get("state")
    if not isinstance(state, Mapping):
        raise ArtifactIntegrityError("completed run lacks final_save.state")
    if "seed" not in record.observed or record.observed["seed"] != record.seed:
        raise ArtifactIntegrityError("observed.seed does not match run seed")
    if ("total_damage" not in record.observed
            or "total_damage" not in state
            or record.observed["total_damage"] != state["total_damage"]):
        raise ArtifactIntegrityError("observed.total_damage does not match final_save.state")
    if ("truncated" not in record.observed
            or "truncated" not in state
            or not isinstance(record.observed["truncated"], bool)
            or not isinstance(state["truncated"], bool)
            or record.observed["truncated"] != state["truncated"]):
        raise ArtifactIntegrityError("observed.truncated does not match final_save.state")
    if ("action_value" in record.observed
            and ("clock" not in state or record.observed["action_value"] != state["clock"])):
        raise ArtifactIntegrityError("observed.action_value does not match final_save.state")


class ArtifactStore:
    """Filesystem artifact store; read-only bits and hashes are not a security sandbox."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        (self.root / "trials").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_id(value: str, label: str) -> str:
        if not isinstance(value, str) or not _ID_RE.fullmatch(value):
            raise ArtifactPathError(f"{label} must be a full lowercase SHA-256 ID")
        return value

    def _safe_path(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ArtifactPathError(f"artifact path escapes store root: {path}") from exc
        return resolved

    def trial_dir(self, trial_id: str) -> Path:
        self._validate_id(trial_id, "trial_id")
        return self._safe_path(self.root / "trials" / trial_id)

    def run_path(self, trial_id: str, run_id: str) -> Path:
        self._validate_id(run_id, "run_id")
        return self._safe_path(self.trial_dir(trial_id) / "runs" / f"{run_id}.json")

    def _publish_bytes(self, path: Path, data: bytes, *, overwrite: bool = False) -> bool:
        path = self._safe_path(path)
        if path.exists() and not overwrite:
            if path.read_bytes() == data:
                path.chmod(0o444)
                return False
            raise ArtifactConflictError(f"artifact already exists with different bytes: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._safe_path(path)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(0o444)
            if path.exists() and not overwrite:
                if path.read_bytes() == data:
                    temporary.unlink()
                    return False
                raise ArtifactConflictError(
                    f"artifact already exists with different bytes: {path}"
                )
            os.replace(temporary, path)
            path.chmod(0o444)
            return True
        finally:
            if temporary.exists():
                temporary.unlink()

    def _publish_json(self, path: Path, payload: Any, *, overwrite: bool = False) -> bool:
        return self._publish_bytes(path, canonical_bytes(payload), overwrite=overwrite)

    def _read_json(self, path: Path) -> Any:
        path = self._safe_path(path)
        raw = path.read_bytes()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArtifactIntegrityError(f"invalid artifact JSON: {path}") from exc
        if raw != canonical_bytes(payload):
            raise ArtifactIntegrityError(f"artifact is not canonical published bytes: {path}")
        return payload

    def publish_spec(
        self,
        contract: ResearchContract,
        resolved: ResolvedProtocol,
        fingerprint: VersionFingerprint,
    ) -> str:
        validate_fingerprint(fingerprint, protocol_id=resolved.protocol_id)
        trial_id = make_trial_id(contract, resolved, fingerprint)
        payload = {
            "trial_id": trial_id,
            "contract": contract,
            "resolved_protocol": resolved,
            "fingerprint": fingerprint,
        }
        payload["spec_hash"] = content_hash(payload)
        self._publish_json(self.trial_dir(trial_id) / "spec.json", payload)
        return trial_id

    def read_spec(self, trial_id: str) -> dict[str, Any]:
        payload = self._read_json(self.trial_dir(trial_id) / "spec.json")
        spec_hash = payload.pop("spec_hash", None)
        if spec_hash != content_hash(payload):
            raise ArtifactIntegrityError("spec content hash mismatch")
        contract = ResearchContract.from_dict(payload["contract"])
        resolved = ResolvedProtocol(**payload["resolved_protocol"])
        fingerprint = VersionFingerprint.from_dict(payload["fingerprint"])
        if payload.get("trial_id") != make_trial_id(contract, resolved, fingerprint):
            raise ArtifactIntegrityError("trial_id does not match spec content")
        payload["spec_hash"] = spec_hash
        return payload

    def publish_variant(self, trial_id: str, prepared: PreparedVariant) -> Path:
        self._validate_id(prepared.variant_id, "variant_id")
        root = self._safe_path(
            self.trial_dir(trial_id) / "variants" / prepared.variant_id
        )
        kind = prepared.comparison_kind
        if (kind, prepared.world) not in {
            ("mechanism", "hypothetical"),
            ("configuration", "canonical"),
        }:
            raise ArtifactIntegrityError("variant kind/world combination is invalid")
        documents = []
        if kind == "configuration":
            self._publish_json(root / "build.json", prepared.effective_build)
            if content_hash(json.loads(canonical_bytes(prepared.effective_build))) != prepared.variant_hash:
                raise ArtifactIntegrityError("configuration build hash mismatch")
        else:
            for document in prepared.documents:
                template_kind = document["template_kind"]
                template_id = document["template_id"]
                if not _COMPONENT_RE.fullmatch(template_kind) or not _COMPONENT_RE.fullmatch(template_id):
                    raise ArtifactPathError("unsafe variant template path component")
                relative = Path(template_kind) / f"{template_id}_variant.yaml"
                data = yaml.safe_dump(
                    document["content"], allow_unicode=True, sort_keys=False
                ).encode("utf-8")
                self._publish_bytes(root / relative, data)
                if content_hash(yaml.safe_load(data)) != document["content_hash"]:
                    raise ArtifactIntegrityError("materialized variant content hash mismatch")
                documents.append({
                    "template_kind": template_kind,
                    "template_id": template_id,
                    "parent_base_hash": document["parent_base_hash"],
                    "content_hash": document["content_hash"],
                    "path": relative.as_posix(),
                })
        metadata = {
            "comparison_kind": kind,
            "world": prepared.world,
            "variant_id": prepared.variant_id,
            "parent_base_hash": prepared.parent_base_hash,
            "variant_hash": prepared.variant_hash,
            "hypothesis": prepared.hypothesis,
            "patches": prepared.patches,
            "documents": documents,
        }
        metadata["metadata_hash"] = content_hash(metadata)
        self._publish_json(root / "variant.json", metadata)
        return root

    def read_variant(self, trial_id: str, variant_id: str) -> tuple[Path, dict[str, Any]]:
        self._validate_id(variant_id, "variant_id")
        root = self._safe_path(self.trial_dir(trial_id) / "variants" / variant_id)
        metadata = self._read_json(root / "variant.json")
        metadata_hash = metadata.pop("metadata_hash", None)
        if metadata_hash != content_hash(metadata):
            raise ArtifactIntegrityError("variant metadata_hash mismatch")
        try:
            kind = metadata["comparison_kind"]
            world = metadata["world"]
            bound_variant_id = content_hash({
                "comparison_kind": kind,
                "world": world,
                "parent_base_hash": metadata["parent_base_hash"],
                "variant_hash": metadata["variant_hash"],
                "patches": metadata["patches"],
                "hypothesis": metadata["hypothesis"],
            })
            documents = metadata["documents"]
        except (KeyError, TypeError) as exc:
            raise ArtifactIntegrityError("variant metadata is incomplete") from exc
        if (kind, world) not in {
            ("mechanism", "hypothetical"),
            ("configuration", "canonical"),
        }:
            raise ArtifactIntegrityError("variant kind/world combination is invalid")
        if metadata.get("variant_id") != variant_id or bound_variant_id != variant_id:
            raise ArtifactIntegrityError("variant_id does not match metadata identity")
        if kind == "configuration":
            if documents != []:
                raise ArtifactIntegrityError("configuration variant cannot declare YAML documents")
            spec = self.read_spec(trial_id)
            baseline_build = ResearchContract.from_dict(spec["contract"]).experiment.build
            if metadata["parent_base_hash"] != content_hash(baseline_build):
                raise ArtifactIntegrityError(
                    "configuration parent_base_hash does not match spec baseline build"
                )
            build = self._read_json(root / "build.json")
            if content_hash(build) != metadata["variant_hash"]:
                raise ArtifactIntegrityError("configuration build.json content hash mismatch")
            metadata["metadata_hash"] = metadata_hash
            return root, metadata
        if not isinstance(documents, list) or not documents:
            raise ArtifactIntegrityError("variant metadata has no documents")

        parent_identity = []
        variant_identity = []
        for document in documents:
            template_kind = document["template_kind"]
            template_id = document["template_id"]
            if (not isinstance(template_kind, str) or not isinstance(template_id, str)
                    or not _COMPONENT_RE.fullmatch(template_kind)
                    or not _COMPONENT_RE.fullmatch(template_id)):
                raise ArtifactIntegrityError("unsafe variant template path component")
            relative = Path(template_kind) / f"{template_id}_variant.yaml"
            if document.get("path") != relative.as_posix():
                raise ArtifactIntegrityError("variant document path mismatch")
            path = self._safe_path(root / relative)
            try:
                content = yaml.safe_load(path.read_bytes())
            except yaml.YAMLError as exc:
                raise ArtifactIntegrityError("invalid variant YAML") from exc
            if content_hash(content) != document["content_hash"]:
                raise ArtifactIntegrityError("variant YAML content hash mismatch")
            parent_identity.append({
                "template_kind": template_kind,
                "template_id": template_id,
                "content_hash": document["parent_base_hash"],
            })
            variant_identity.append({
                "template_kind": template_kind,
                "template_id": template_id,
                "content_hash": document["content_hash"],
            })
        if metadata["parent_base_hash"] != content_hash(parent_identity):
            raise ArtifactIntegrityError("variant parent base hash mismatch")
        if metadata["variant_hash"] != content_hash(variant_identity):
            raise ArtifactIntegrityError("variant aggregate content hash mismatch")
        metadata["metadata_hash"] = metadata_hash
        return root, metadata

    def publish_run(self, record: RunRecord) -> RunRecord:
        if record.status not in {"completed", "failed"}:
            raise ArtifactIntegrityError(f"unsupported run status: {record.status!r}")
        _validate_run_evidence(record)
        expected_run_id = make_run_id(
            record.trial_id, record.arm_id, record.cohort, record.seed
        )
        if record.run_id != expected_run_id:
            raise ArtifactIntegrityError("run_id does not match run coordinates")
        payload = record.to_dict()
        supplied_hash = payload.pop("content_hash")
        digest = content_hash(payload)
        if supplied_hash and supplied_hash != digest:
            raise ArtifactIntegrityError("run content hash mismatch before publication")
        payload["content_hash"] = digest
        self._publish_json(self.run_path(record.trial_id, record.run_id), payload)
        return RunRecord.from_dict(payload)

    def read_run(self, trial_id: str, run_id: str) -> RunRecord:
        payload = self._read_json(self.run_path(trial_id, run_id))
        supplied_hash = payload.pop("content_hash", None)
        if supplied_hash != content_hash(payload):
            raise ArtifactIntegrityError("run content hash mismatch")
        payload["content_hash"] = supplied_hash
        record = RunRecord.from_dict(payload)
        if record.trial_id != trial_id or record.run_id != run_id:
            raise ArtifactIntegrityError("run coordinates do not match its path")
        if record.run_id != make_run_id(trial_id, record.arm_id, record.cohort, record.seed):
            raise ArtifactIntegrityError("run coordinates do not match run_id")
        _validate_run_evidence(record)
        ordinals = []
        for event in record.events:
            ordinal = event["ordinal"]
            ordinals.append(ordinal)
            if event["event_id"] != make_event_id(
                record.run_id, ordinal, event["payload"]
            ):
                raise ArtifactIntegrityError("event_id does not match event payload")
        if ordinals != list(range(len(ordinals))):
            raise ArtifactIntegrityError("event ordinals are not the frozen sequence")
        for modifier in record.modifiers:
            if modifier["modifier_id"] != make_modifier_id(
                record.run_id, modifier["actor_id"], modifier["engine_modifier_id"]
            ):
                raise ArtifactIntegrityError("modifier_id does not match final modifier")
        return record

    def _spec_parts(
        self, trial_id: str
    ) -> tuple[ResearchContract, ResolvedProtocol, VersionFingerprint]:
        payload = self.read_spec(trial_id)
        return (
            ResearchContract.from_dict(payload["contract"]),
            ResolvedProtocol(**payload["resolved_protocol"]),
            VersionFingerprint.from_dict(payload["fingerprint"]),
        )

    def _validate_result(self, artifact: TrialArtifact) -> None:
        contract, resolved, fingerprint = self._spec_parts(artifact.trial_id)
        if artifact.spec != contract or artifact.fingerprint != fingerprint:
            raise ArtifactIntegrityError("result does not match its published spec")
        if artifact.resolved_protocol != asdict(resolved):
            raise ArtifactIntegrityError("result resolved protocol does not match spec")
        expected_comparison = make_comparison_set(artifact.trial_id, contract, resolved)
        if artifact.comparison_set != expected_comparison:
            raise ArtifactIntegrityError("comparison set does not match protocol cohorts")
        expected_ids = _expected_run_ids(expected_comparison)
        if artifact.run_ids != expected_ids:
            raise ArtifactIntegrityError("result run sequence does not match protocol")

        expected_coordinates = []
        for arm, dev_ids, holdout_ids in (
            (
                contract.experiment.baseline.arm_id,
                expected_comparison.baseline_dev,
                expected_comparison.baseline_holdout,
            ),
            (
                contract.experiment.variant.arm_id,
                expected_comparison.variant_dev,
                expected_comparison.variant_holdout,
            ),
        ):
            expected_coordinates.extend(
                (arm, "dev", seed, run_id)
                for seed, run_id in zip(resolved.dev_seeds, dev_ids)
            )
            expected_coordinates.extend(
                (arm, "holdout", seed, run_id)
                for seed, run_id in zip(resolved.holdout_seeds, holdout_ids)
            )

        failed = []
        for arm, cohort, seed, run_id in expected_coordinates:
            record = self.read_run(artifact.trial_id, run_id)
            if (record.arm_id, record.cohort, record.seed) != (arm, cohort, seed):
                raise ArtifactIntegrityError("run cohort membership mismatch")
            if arm == contract.experiment.variant.arm_id:
                expected_parent = make_run_id(
                    artifact.trial_id,
                    contract.experiment.baseline.arm_id,
                    cohort,
                    seed,
                )
                if record.parent_run_id != expected_parent:
                    raise ArtifactIntegrityError("variant run lineage mismatch")
            elif record.parent_run_id is not None:
                raise ArtifactIntegrityError("baseline run cannot have a parent run")
            if record.status == "failed":
                failed.append(record)
        expected_status = "failed" if failed else "completed"
        if artifact.status != expected_status:
            raise ArtifactIntegrityError("result status does not match retained runs")
        expected_reasons = tuple(run_failure_reason(record) for record in failed)
        if artifact.failure_reasons != expected_reasons:
            raise ArtifactIntegrityError("result failure reasons do not match failed runs")

    def publish_result(self, artifact: TrialArtifact) -> TrialArtifact:
        self._validate_result(artifact)
        payload = artifact.to_dict()
        payload["result_hash"] = content_hash(payload)
        self._publish_json(self.trial_dir(artifact.trial_id) / "result.json", payload)
        return artifact

    def read_result(self, trial_id: str) -> TrialArtifact:
        payload = self._read_json(self.trial_dir(trial_id) / "result.json")
        result_hash = payload.pop("result_hash", None)
        if result_hash != content_hash(payload):
            raise ArtifactIntegrityError("result content hash mismatch")
        artifact = TrialArtifact.from_dict(payload)
        if artifact.trial_id != trial_id:
            raise ArtifactIntegrityError("result trial_id does not match its path")
        self._validate_result(artifact)
        return artifact

    def write_metadata(self, trial_id: str, metadata: dict[str, Any]) -> None:
        self._publish_json(
            self.trial_dir(trial_id) / "metadata.json", metadata, overwrite=True
        )

    def read_metadata(self, trial_id: str) -> dict[str, Any]:
        return self._read_json(self.trial_dir(trial_id) / "metadata.json")

    def claim_path(self, trial_id: str, record_id: str) -> Path:
        self._validate_id(record_id, "claim record_id")
        return self._safe_path(self.trial_dir(trial_id) / "claims" / f"{record_id}.json")

    def publish_claim(self, trial_id: str, claim: Claim) -> str:
        if claim.trial_id != trial_id:
            raise ArtifactIntegrityError("claim trial_id does not match its path")
        if claim.claim_id != make_claim_id(
            claim.subject, claim.premises, claim.derivation_steps
        ):
            raise ArtifactIntegrityError("claim_id does not match subject/premises/derivation")
        record_id = content_hash(claim)
        payload = claim.to_dict()
        payload["artifact_hash"] = record_id
        self._publish_json(self.claim_path(trial_id, record_id), payload)
        return record_id

    def read_claim(self, trial_id: str, record_id: str) -> Claim:
        payload = self._read_json(self.claim_path(trial_id, record_id))
        artifact_hash = payload.pop("artifact_hash", None)
        if artifact_hash != record_id:
            raise ArtifactIntegrityError("claim artifact hash does not match its path")
        claim = Claim.from_dict(payload)
        if content_hash(claim) != record_id:
            raise ArtifactIntegrityError("claim content hash mismatch")
        if claim.trial_id != trial_id or claim.claim_id != make_claim_id(
            claim.subject, claim.premises, claim.derivation_steps
        ):
            raise ArtifactIntegrityError("claim identity binding mismatch")
        return claim

    @staticmethod
    def _validate_report_trial(trial_id: str, report: dict[str, Any]) -> None:
        spec = report.get("spec")
        if not isinstance(spec, Mapping) or spec.get("trial_id") != trial_id:
            raise ArtifactIntegrityError("report spec.trial_id does not match its path trial")

    def report_path(self, trial_id: str, report_id: str) -> Path:
        self._validate_id(report_id, "report_id")
        return self._safe_path(self.trial_dir(trial_id) / "reports" / f"{report_id}.json")

    def publish_report(self, trial_id: str, report: dict[str, Any]) -> str:
        self._validate_report_trial(trial_id, report)
        if "report_id" in report:
            raise ArtifactIntegrityError("report_id is assigned by the artifact store")
        report_id = content_hash(report)
        payload = {**report, "report_id": report_id}
        self._publish_json(self.report_path(trial_id, report_id), payload)
        return report_id

    def read_report(self, trial_id: str, report_id: str) -> dict[str, Any]:
        payload = self._read_json(self.report_path(trial_id, report_id))
        stored_id = payload.pop("report_id", None)
        if stored_id != report_id or content_hash(payload) != report_id:
            raise ArtifactIntegrityError("report content hash mismatch")
        self._validate_report_trial(trial_id, payload)
        payload["report_id"] = report_id
        return payload

    def candidate_report_path(self, candidate_set_id: str, report_id: str) -> Path:
        self._validate_id(candidate_set_id, "candidate_set_id")
        self._validate_id(report_id, "report_id")
        return self._safe_path(
            self.root / "candidate_sets" / candidate_set_id / "reports" / f"{report_id}.json"
        )

    def publish_candidate_report(self, candidate_set_id: str, report: dict[str, Any]) -> str:
        if report.get("candidate_set_id") != candidate_set_id:
            raise ArtifactIntegrityError("candidate report candidate_set_id does not match its path")
        if report.get("schema_version") != "candidate-v1":
            raise ArtifactIntegrityError("candidate report must use candidate-v1 schema")
        if "report_id" in report:
            raise ArtifactIntegrityError("report_id is assigned by the artifact store")
        report_id = content_hash(report)
        payload = {**report, "report_id": report_id}
        self._publish_json(self.candidate_report_path(candidate_set_id, report_id), payload)
        return report_id

    def read_candidate_report(self, candidate_set_id: str, report_id: str) -> dict[str, Any]:
        payload = self._read_json(self.candidate_report_path(candidate_set_id, report_id))
        stored_id = payload.pop("report_id", None)
        if stored_id != report_id or content_hash(payload) != report_id:
            raise ArtifactIntegrityError("candidate report content hash mismatch")
        if payload.get("candidate_set_id") != candidate_set_id:
            raise ArtifactIntegrityError("candidate report candidate_set_id does not match its path")
        if payload.get("schema_version") != "candidate-v1":
            raise ArtifactIntegrityError("candidate report must use candidate-v1 schema")
        payload["report_id"] = report_id
        return payload

    def resolve_evidence(self, link: EvidenceLink) -> dict[str, Any]:
        if link.run_id is None and (link.event_id is not None or link.modifier_id is not None):
            raise ArtifactIntegrityError("event_id/modifier_id evidence links require run_id")
        if link.event_id is not None and link.modifier_id is not None:
            raise ArtifactIntegrityError("evidence link cannot select event and modifier together")
        if link.run_id is not None:
            record = self.read_run(link.trial_id, link.run_id)
            if record.content_hash != link.artifact_hash:
                raise ArtifactIntegrityError("run evidence artifact hash mismatch")
            if link.event_id is not None:
                for event in record.events:
                    if event["event_id"] == link.event_id:
                        return {"status": "resolved", "kind": "event", "evidence": event}
                return {
                    "status": "unresolved",
                    "kind": "event",
                    "reason": "event is absent from the recorded run",
                }
            if link.modifier_id is not None:
                for modifier in record.modifiers:
                    if modifier["modifier_id"] == link.modifier_id:
                        return {"status": "resolved", "kind": "modifier", "evidence": modifier}
                return {
                    "status": "unresolved",
                    "kind": "modifier",
                    "reason": "modifier is absent from final state; historical lifecycle is not recorded",
                }
            return {"status": "resolved", "kind": "run", "evidence": record}

        spec = self.read_spec(link.trial_id)
        if spec["spec_hash"] == link.artifact_hash:
            return {"status": "resolved", "kind": "spec", "evidence": spec}
        artifact = self.read_result(link.trial_id)
        if content_hash(artifact) == link.artifact_hash:
            return {"status": "resolved", "kind": "result", "evidence": artifact}
        variants_root = self.trial_dir(link.trial_id) / "variants"
        for variant_root in sorted(variants_root.iterdir()):
            root, metadata = self.read_variant(link.trial_id, variant_root.name)
            if metadata["metadata_hash"] == link.artifact_hash:
                return {
                    "status": "resolved",
                    "kind": "variant",
                    "root": root,
                    "evidence": metadata,
                }
        raise ArtifactIntegrityError("evidence artifact hash does not match the trial")

    def execution_path(self, execution_id: str) -> Path:
        self._validate_id(execution_id, "execution_id")
        return self._safe_path(self.root / "executions" / f"{execution_id}.json")

    def investigation_path(self, investigation_id: str) -> Path:
        self._validate_id(investigation_id, "investigation_id")
        return self._safe_path(self.root / "investigations" / f"{investigation_id}.json")

    def write_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        self._validate_id(record.investigation_id, "investigation_id")
        self._validate_id(record.contract_hash, "contract_hash")
        expected_id = make_execution_id(
            record.investigation_id, record.contract_hash, record.kind, record.attempt
        )
        if record.execution_id != expected_id:
            raise ArtifactIntegrityError("execution_id does not match execution coordinates")
        path = self.execution_path(record.execution_id)
        if path.exists():
            previous = self.read_execution(record.execution_id)
            if record.created_at != previous.created_at:
                raise ArtifactConflictError("execution created_at cannot be rewritten")
            if record.history[:len(previous.history)] != previous.history:
                raise ArtifactConflictError("execution history cannot be shortened or rewritten")
        payload = record.to_dict()
        payload["artifact_hash"] = content_hash(record)
        self._publish_json(path, payload, overwrite=True)
        return record

    def read_execution(self, execution_id: str) -> ExecutionRecord:
        payload = self._read_json(self.execution_path(execution_id))
        artifact_hash = payload.pop("artifact_hash", None)
        record = ExecutionRecord.from_dict(payload)
        if artifact_hash != content_hash(record):
            raise ArtifactIntegrityError("execution content hash mismatch")
        if record.execution_id != execution_id or record.execution_id != make_execution_id(
            record.investigation_id, record.contract_hash, record.kind, record.attempt
        ):
            raise ArtifactIntegrityError("execution identity binding mismatch")
        return record

    def write_investigation(self, record: InvestigationState) -> InvestigationState:
        expected_id = make_investigation_id(record.contract)
        if record.investigation_id != expected_id:
            raise ArtifactIntegrityError("investigation_id does not match contract content")
        path = self.investigation_path(record.investigation_id)
        if path.exists():
            previous = self.read_investigation(record.investigation_id)
            if record.created_at != previous.created_at:
                raise ArtifactConflictError("investigation created_at cannot be rewritten")
            if record.revision < previous.revision:
                raise ArtifactConflictError("investigation revision cannot move backwards")
            if record.execution_ids[:len(previous.execution_ids)] != previous.execution_ids:
                raise ArtifactConflictError("investigation execution history cannot be rewritten")
        payload = record.to_dict()
        payload["artifact_hash"] = content_hash(record)
        self._publish_json(path, payload, overwrite=True)
        return record

    def read_investigation(self, investigation_id: str) -> InvestigationState:
        payload = self._read_json(self.investigation_path(investigation_id))
        artifact_hash = payload.pop("artifact_hash", None)
        record = InvestigationState.from_dict(payload)
        if artifact_hash != content_hash(record):
            raise ArtifactIntegrityError("investigation content hash mismatch")
        if record.investigation_id != investigation_id or record.investigation_id != \
                make_investigation_id(record.contract):
            raise ArtifactIntegrityError("investigation identity binding mismatch")
        return record
