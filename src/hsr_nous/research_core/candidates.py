"""Bounded candidate-set execution and independently recomputed reports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hsr_nous.research_core.artifacts import ArtifactIntegrityError, ArtifactStore
from hsr_nous.research_core.claims import ClaimValidationResult, ClaimValidator
from hsr_nous.research_core.execution import ExecutionManager
from hsr_nous.research_core.kernel import compare
from hsr_nous.research_core.report import ReportComposer
from hsr_nous.research_core.runner import RunCancelledError
from hsr_nous.research_protocol import resolve_protocol, validate_candidate_set
from hsr_nous.research_schema import CandidateSet, ResearchContract, canonical_json, content_hash


@dataclass(frozen=True)
class _Evaluation:
    contract: ResearchContract
    status: str
    trial_id: str | None = None
    report_id: str | None = None
    validation: ClaimValidationResult | None = None
    error: str | None = None


class CandidateRunner:
    def __init__(
        self,
        store: ArtifactStore,
        manager: ExecutionManager | None = None,
        validator: ClaimValidator | None = None,
        composer: ReportComposer | None = None,
    ) -> None:
        self.store = store
        self._manager = manager or ExecutionManager(store)
        self._validator = validator or self._manager.validator
        self._composer = composer or self._manager.composer

    def _evaluate_from_trial(
        self, contract: ResearchContract, trial_id: str
    ) -> _Evaluation:
        validated = self._validator.validate_trial(trial_id)
        if canonical_json(validated.spec["contract"]) != canonical_json(contract):
            raise ArtifactIntegrityError("candidate trial contract mismatch")
        report = self._composer.compose(validated)
        return _Evaluation(
            contract=contract,
            status=validated.claim.status,
            trial_id=trial_id,
            report_id=report["report_id"],
            validation=validated,
        )

    def _execute(
        self,
        contract: ResearchContract,
        *,
        observer: Callable[[int, int], None] | None = None,
    ) -> _Evaluation:
        investigation = self._manager.create_investigation(contract)
        try:
            if investigation.status == "completed":
                execution = self._manager.cache(investigation.investigation_id)
            elif investigation.status == "failed" and investigation.artifact_status == "complete":
                execution = self._manager.replay(investigation.investigation_id)
            elif investigation.artifact_status == "partial" and investigation.status in {
                "cancelled", "failed",
            }:
                execution = self._manager.resume(
                    investigation.investigation_id, observer=observer
                )
            else:
                investigation = self._manager.validate(investigation.investigation_id)
                execution = self._manager.queue(investigation.investigation_id)
                execution = self._manager.execute(execution.execution_id, observer=observer)
            if execution.status != "completed":
                return _Evaluation(contract, execution.status, execution.trial_id)
            return self._evaluate_from_trial(contract, execution.trial_id)
        except ArtifactIntegrityError:
            raise
        except Exception as error:
            return _Evaluation(
                contract,
                "failed",
                investigation.trial_id,
                error=f"{type(error).__name__}: {error}",
            )

    def _read(self, contract: ResearchContract) -> _Evaluation:
        investigation = self._manager.create_investigation(contract)
        if investigation.trial_id is None:
            return _Evaluation(
                contract,
                investigation.status,
                error=f"no completed trial: {investigation.next_action}",
            )
        try:
            return self._evaluate_from_trial(contract, investigation.trial_id)
        except ArtifactIntegrityError:
            raise
        except Exception as error:
            return _Evaluation(
                contract,
                "failed",
                investigation.trial_id,
                error=f"{type(error).__name__}: {error}",
            )

    @staticmethod
    def _adjusted_comparison(
        evaluation: _Evaluation,
        confidence: float,
    ) -> dict[str, Any] | None:
        validated = evaluation.validation
        if validated is None or validated.trial is None:
            return None
        resolved = resolve_protocol(validated.trial.spec.protocol_id)
        by_arm = {}
        for arm in ("baseline", "variant"):
            values = {}
            for record in validated.records:
                if (record.arm_id != arm or record.cohort != "holdout"
                        or record.status != "completed" or record.observed.get("truncated")):
                    continue
                if "total_damage" not in record.observed:
                    raise ArtifactIntegrityError("completed run lacks observed total_damage")
                values[record.seed] = record.observed["total_damage"]
            by_arm[arm] = values
        expected = set(resolved.holdout_seeds)
        if any(set(values) != expected for values in by_arm.values()):
            return None
        return compare(
            by_arm["baseline"],
            by_arm["variant"],
            protocol=resolved,
            cohort="holdout",
            confidence=confidence,
        )

    def _compose(self, candidate_set: CandidateSet, evaluations: list[_Evaluation]) -> dict[str, Any]:
        first = candidate_set.candidates[0]
        resolved = resolve_protocol(first.protocol_id)
        direction = first.experiment.metric.direction
        adjusted_confidence = 1 - (1 - resolved.confidence) / len(evaluations)
        items = []
        for evaluation in evaluations:
            validated = evaluation.validation
            dev = validated.comparisons.get("dev") if validated is not None else None
            holdout = validated.comparisons.get("holdout") if validated is not None else None
            items.append({
                "evaluation": evaluation,
                "dev": dev,
                "holdout": holdout,
                "holdout_adjusted": self._adjusted_comparison(
                    evaluation, adjusted_confidence
                ),
            })

        def sort_key(item):
            effect = item["dev"]["effect"] if item["dev"] is not None else None
            if effect is None:
                return (1, 0)
            return (0, -effect if direction == "higher_is_better" else effect)

        ordered = sorted(items, key=sort_key)
        selected_ids = set()
        for item in ordered[:candidate_set.top_k]:
            adjusted = item["holdout_adjusted"]
            if adjusted is None:
                continue
            interval = adjusted["confidence_interval"]
            if ((direction == "higher_is_better" and interval["lower"] > 0)
                    or (direction == "lower_is_better" and interval["upper"] < 0)):
                selected_ids.add(item["evaluation"].contract.contract_id)

        views = []
        for rank, item in enumerate(ordered, start=1):
            evaluation = item["evaluation"]
            contract_id = evaluation.contract.contract_id
            selected = contract_id in selected_ids
            if selected:
                reason = "dev selected; holdout adjusted CI excludes 0"
            elif evaluation.status not in {"accepted", "inconclusive"}:
                reason = f"execution {evaluation.status}"
            elif item["dev"] is None:
                reason = "dev comparison unavailable"
            elif item in ordered[:candidate_set.top_k] and item["holdout_adjusted"] is None:
                reason = "holdout adjusted comparison unavailable"
            elif item in ordered[:candidate_set.top_k]:
                reason = "holdout adjusted CI contains 0"
            else:
                reason = "not selected by dev"
            views.append({
                "contract_id": contract_id,
                "dev_rank": rank,
                "trial_id": evaluation.trial_id,
                "report_id": evaluation.report_id,
                "status": evaluation.status,
                "dev": item["dev"],
                "holdout": item["holdout"],
                "holdout_adjusted": item["holdout_adjusted"],
                "selected": selected,
                "selection_reason": reason,
                "error": evaluation.error,
            })

        if selected_ids:
            status = "accepted"
        elif all(evaluation.status in {"failed", "cancelled"} for evaluation in evaluations):
            status = "failed"
        else:
            status = "inconclusive"
        report = {
            "schema_version": "candidate-v1",
            "candidate_set_id": content_hash(candidate_set),
            "candidate_set": candidate_set,
            "status": status,
            "question": candidate_set.question,
            "selection": {
                "top_k": candidate_set.top_k,
                "correction": candidate_set.correction,
                "dev_confidence": resolved.confidence,
                "adjusted_confidence": adjusted_confidence,
                "dev_selection": True,
                "holdout_confirmation": True,
            },
            "dev_ranking": [{
                "contract_id": item["evaluation"].contract.contract_id,
                "dev_rank": rank,
                "effect": item["dev"]["effect"] if item["dev"] is not None else None,
            } for rank, item in enumerate(ordered, start=1)],
            "candidates": views,
            "selected": [view["contract_id"] for view in views if view["selected"]],
            "flags": {
                "source": "simulated",
                "world": first.experiment.variant.world,
                "validation": "pending_real_validation",
            },
            "scope": {
                "comparison_kind": first.experiment.comparison_kind,
                "protocol_id": first.protocol_id,
                "note": "selection is valid only within this candidate set; not a global optimum",
            },
        }
        report_id = self.store.publish_candidate_report(report["candidate_set_id"], report)
        return self.store.read_candidate_report(report["candidate_set_id"], report_id)

    def run(
        self,
        candidate_set: CandidateSet,
        *,
        observer: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_candidate: Callable[[_Evaluation], None] | None = None,
    ) -> dict[str, Any]:
        validate_candidate_set(candidate_set)
        evaluations = []
        for contract in candidate_set.candidates:
            if should_cancel is not None and should_cancel():
                raise RunCancelledError("candidate task cancellation requested")
            evaluation = self._execute(contract, observer=observer)
            evaluations.append(evaluation)
            if on_candidate is not None:
                on_candidate(evaluation)
            if should_cancel is not None and should_cancel():
                raise RunCancelledError("candidate task cancellation requested")
        return self._compose(candidate_set, evaluations)

    def validate(self, candidate_set: CandidateSet) -> dict[str, Any]:
        validate_candidate_set(candidate_set)
        evaluations = [self._read(contract) for contract in candidate_set.candidates]
        return self._compose(candidate_set, evaluations)

    def validate_report(self, candidate_set: CandidateSet, report_id: str) -> dict[str, Any]:
        self.store.read_candidate_report(candidate_set.candidate_set_id, report_id)
        report = self.validate(candidate_set)
        if report["candidate_set_id"] != candidate_set.candidate_set_id:
            raise ArtifactIntegrityError("candidate set identity mismatch")
        if report["report_id"] != report_id:
            raise ArtifactIntegrityError("candidate report independently recomputed ID mismatch")
        return report
