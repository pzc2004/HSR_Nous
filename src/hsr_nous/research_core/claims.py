"""Evidence orchestration and independent claim recomputation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from hsr_nous.research_core.artifacts import ArtifactIntegrityError, ArtifactStore
from hsr_nous.research_core.fingerprint import collect_research_fingerprint
from hsr_nous.research_core.kernel import build_claim, compare, distribution, make_claim_id, validate_claim
from hsr_nous.research_protocol import ResolvedProtocol
from hsr_nous.research_schema import (
    Claim,
    EvidenceLink,
    ResearchContract,
    RunRecord,
    TrialArtifact,
    VersionFingerprint,
    content_hash,
)


@dataclass(frozen=True)
class ClaimValidationResult:
    claim: Claim
    claim_record_id: str | None
    spec: dict[str, Any]
    trial: TrialArtifact | None
    records: tuple[RunRecord, ...]
    summaries: dict[str, Any]
    comparisons: dict[str, Any]
    variant_metadata: dict[str, Any]


class ClaimValidator:
    def __init__(self, store: ArtifactStore) -> None:
        self.store = store

    def _spec_parts(self, trial_id: str):
        payload = self.store.read_spec(trial_id)
        return (
            payload,
            ResearchContract.from_dict(payload["contract"]),
            ResolvedProtocol(**payload["resolved_protocol"]),
            VersionFingerprint.from_dict(payload["fingerprint"]),
        )

    def _variant_metadata(self, trial_id: str) -> dict[str, Any]:
        variants_root = self.store.trial_dir(trial_id) / "variants"
        roots = sorted(path for path in variants_root.iterdir() if path.is_dir())
        if len(roots) != 1:
            raise ArtifactIntegrityError("trial must contain exactly one variant")
        _, metadata = self.store.read_variant(trial_id, roots[0].name)
        return metadata

    @staticmethod
    def _premises(
        spec: dict[str, Any],
        artifact: TrialArtifact,
        records: tuple[RunRecord, ...],
        variant_metadata: dict[str, Any],
    ) -> tuple[EvidenceLink, ...]:
        trial_id = artifact.trial_id
        links = [
            EvidenceLink(trial_id=trial_id, artifact_hash=spec["spec_hash"]),
            EvidenceLink(trial_id=trial_id, artifact_hash=content_hash(artifact)),
            EvidenceLink(
                trial_id=trial_id,
                artifact_hash=variant_metadata["metadata_hash"],
            ),
        ]
        links.extend(
            EvidenceLink(
                trial_id=trial_id,
                run_id=record.run_id,
                artifact_hash=record.content_hash,
            )
            for record in records
        )
        return tuple(links)

    def _compare_evidence(self, artifact: TrialArtifact, records: tuple[RunRecord, ...]):
        resolved = ResolvedProtocol(**artifact.resolved_protocol)
        by_id = {record.run_id: record for record in records}
        summaries = {"baseline": {}, "variant": {}}
        comparisons = {}
        holdout_details = {}
        for cohort, seeds in (
            ("dev", resolved.dev_seeds),
            ("holdout", resolved.holdout_seeds),
        ):
            values_by_arm = {}
            failed_by_arm = {}
            truncated_by_arm = {}
            for role in ("baseline", "variant"):
                run_ids = getattr(artifact.comparison_set, f"{role}_{cohort}")
                values = {}
                failed = []
                truncated = []
                for seed, run_id in zip(seeds, run_ids):
                    record = by_id[run_id]
                    if record.status == "failed":
                        failed.append(run_id)
                        continue
                    if record.observed.get("truncated"):
                        truncated.append(run_id)
                        continue
                    if "total_damage" not in record.observed:
                        raise ArtifactIntegrityError(
                            f"completed run {run_id} lacks observed total_damage"
                        )
                    values[seed] = record.observed["total_damage"]
                values_by_arm[role] = values
                failed_by_arm[role] = failed
                truncated_by_arm[role] = truncated
                ordered_values = [values[seed] for seed in seeds if seed in values]
                summaries[role][cohort] = {
                    "n": len(values),
                    "distribution": distribution(ordered_values) if values else None,
                    "failed": len(failed),
                    "truncated": len(truncated),
                    "failed_run_ids": failed,
                    "truncated_run_ids": truncated,
                }
            expected = set(seeds)
            if set(values_by_arm["baseline"]) == expected and set(
                values_by_arm["variant"]
            ) == expected:
                comparisons[cohort] = compare(
                    values_by_arm["baseline"],
                    values_by_arm["variant"],
                    protocol=resolved,
                    cohort=cohort,
                )
            else:
                comparisons[cohort] = None
            if cohort == "holdout":
                holdout_details = {
                    "valid_n": len(
                        set(values_by_arm["baseline"]) & set(values_by_arm["variant"])
                    ),
                    "failed_run_ids": tuple(
                        failed_by_arm["baseline"] + failed_by_arm["variant"]
                    ),
                    "truncated_run_ids": tuple(
                        truncated_by_arm["baseline"] + truncated_by_arm["variant"]
                    ),
                }
        return summaries, comparisons, holdout_details

    def _expected(self, trial_id: str):
        spec, contract, resolved, fingerprint = self._spec_parts(trial_id)
        artifact = self.store.read_result(trial_id)
        records = tuple(self.store.read_run(trial_id, run_id) for run_id in artifact.run_ids)
        variant_metadata = self._variant_metadata(trial_id)
        if variant_metadata["variant_hash"] != fingerprint.variant_hash:
            raise ArtifactIntegrityError("fingerprint variant_hash does not match variant metadata")
        summaries, comparisons, holdout = self._compare_evidence(artifact, records)
        premises = self._premises(spec, artifact, records, variant_metadata)
        comparison = artifact.comparison_set
        expected = build_claim(
            trial_id=trial_id,
            comparison_set_id=comparison.comparison_set_id,
            subject=contract.experiment.variant.arm_id,
            metric=contract.experiment.metric,
            protocol=resolved,
            fingerprint=fingerprint,
            premises=premises,
            holdout=comparisons["holdout"],
            valid_n=holdout["valid_n"],
            baseline_run_ids=comparison.baseline_holdout,
            variant_run_ids=comparison.variant_holdout,
            failed_run_ids=holdout["failed_run_ids"],
            truncated_run_ids=holdout["truncated_run_ids"],
            comparison_kind=contract.experiment.comparison_kind,
            world=contract.experiment.variant.world,
        )
        context = {
            "trial": artifact,
            "records": records,
            "summaries": summaries,
            "comparisons": comparisons,
            "variant_metadata": variant_metadata,
        }
        return spec, contract, resolved, expected, context

    @staticmethod
    def _fingerprint_identity(fingerprint: VersionFingerprint) -> dict[str, Any]:
        payload = fingerprint.to_dict()
        payload.pop("git_commit", None)
        return payload

    def _current_fingerprint(
        self,
        contract: ResearchContract,
        resolved: ResolvedProtocol,
        variant_metadata: dict[str, Any],
    ) -> VersionFingerprint:
        current = collect_research_fingerprint(contract, resolved)
        return replace(current, variant_hash=variant_metadata["variant_hash"])

    @staticmethod
    def _rejected(claim: Claim, reason: str) -> Claim:
        return replace(
            claim,
            claim_id=make_claim_id(claim.subject, claim.premises, claim.derivation_steps),
            status="rejected",
            failure_reason=reason,
        )

    @staticmethod
    def _result(
        claim: Claim,
        record_id: str | None,
        spec: dict[str, Any],
        context: dict[str, Any],
    ) -> ClaimValidationResult:
        return ClaimValidationResult(
            claim=claim,
            claim_record_id=record_id,
            spec=spec,
            trial=context.get("trial"),
            records=context.get("records", ()),
            summaries=context.get("summaries", {}),
            comparisons=context.get("comparisons", {}),
            variant_metadata=context.get("variant_metadata", {}),
        )

    def validate_trial(self, trial_id: str) -> ClaimValidationResult:
        spec, contract, resolved, expected, context = self._expected(trial_id)
        current = self._current_fingerprint(
            contract, resolved, context["variant_metadata"]
        )
        if self._fingerprint_identity(current) != self._fingerprint_identity(
            VersionFingerprint.from_dict(
                expected.statistical_metadata["fingerprint"]
            )
        ):
            stale = replace(
                expected,
                status="stale",
                failure_reason="current fingerprint differs from claim premises",
            )
            return self._result(stale, None, spec, context)
        record_id = self.store.publish_claim(trial_id, expected)
        return self._result(expected, record_id, spec, context)

    def validate(self, claim: Claim) -> ClaimValidationResult:
        spec = self.store.read_spec(claim.trial_id)
        try:
            spec, contract, resolved, expected, context = self._expected(claim.trial_id)
            current = self._current_fingerprint(
                contract, resolved, context["variant_metadata"]
            )
        except Exception as error:
            rejected = self._rejected(
                claim, f"evidence reload failed: {type(error).__name__}: {error}"
            )
            record_id = self.store.publish_claim(claim.trial_id, rejected)
            return self._result(rejected, record_id, spec, {})

        try:
            premise_fingerprint = VersionFingerprint.from_dict(
                claim.statistical_metadata["fingerprint"]
            )
        except (KeyError, TypeError, ValueError):
            premise_fingerprint = None
        if (premise_fingerprint is not None
                and self._fingerprint_identity(current)
                != self._fingerprint_identity(premise_fingerprint)):
            stale = replace(
                claim,
                status="stale",
                failure_reason="current fingerprint differs from claim premises",
            )
            return self._result(stale, None, spec, context)

        mismatches = validate_claim(claim, expected)
        if mismatches:
            rejected = self._rejected(
                claim, "claim derivation mismatch: " + ", ".join(mismatches)
            )
            record_id = self.store.publish_claim(claim.trial_id, rejected)
            return self._result(rejected, record_id, spec, context)
        record_id = self.store.publish_claim(claim.trial_id, expected)
        return self._result(expected, record_id, spec, context)
