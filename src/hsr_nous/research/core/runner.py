"""Deterministic paired-trial execution and raw evidence retention."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hsr_nous.common import research_root
from hsr_nous.research.core.artifacts import (
    ArtifactIntegrityError,
    ArtifactStore,
    make_comparison_set,
    make_event_id,
    make_modifier_id,
    make_run_id,
    run_failure_reason,
)
from hsr_nous.research.core.fingerprint import collect_research_fingerprint
from hsr_nous.research.core.variants import VariantMaterializer
from hsr_nous.research.schema import ResearchContract, RunRecord, TrialArtifact
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.montecarlo import RunRecorder, classify_outcome
from hsr_nous.sim.structured_log import StructuredLogger


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _events(run_id: str, entries: Any) -> tuple[dict[str, Any], ...]:
    events = []
    for ordinal, entry in enumerate(entries or ()):
        payload = deepcopy(entry)
        events.append({
            "event_id": make_event_id(run_id, ordinal, payload),
            "ordinal": ordinal,
            "payload": payload,
        })
    return tuple(events)


def _final_modifiers(
    run_id: str, final_save: dict[str, Any]
) -> tuple[dict[str, Any], ...]:
    modifiers = []
    actors = final_save.get("state", {}).get("actors", {})
    for actor_id in sorted(actors):
        actor_modifiers = actors[actor_id].get("modifiers", {})
        for engine_modifier_id in sorted(actor_modifiers):
            modifiers.append({
                "modifier_id": make_modifier_id(run_id, actor_id, engine_modifier_id),
                "actor_id": actor_id,
                "engine_modifier_id": engine_modifier_id,
                "details": deepcopy(actor_modifiers[engine_modifier_id]),
            })
    return tuple(modifiers)


def _record(
    trial_id: str,
    arm_id: str,
    cohort: str,
    seed: int,
    *,
    parent_run_id: str | None,
    status: str,
    observed: dict[str, Any],
    entries: Any = (),
    final_save: dict[str, Any] | None = None,
) -> RunRecord:
    run_id = make_run_id(trial_id, arm_id, cohort, seed)
    final_save = final_save or {}
    return RunRecord(
        run_id=run_id,
        trial_id=trial_id,
        arm_id=arm_id,
        cohort=cohort,
        seed=seed,
        status=status,
        observed=observed,
        events=_events(run_id, entries),
        final_save=final_save,
        modifiers=_final_modifiers(run_id, final_save) if final_save else (),
        content_hash="",
        parent_run_id=parent_run_id,
    )


def _error(error: Exception) -> dict[str, Any]:
    return {"error": {"type": type(error).__name__, "message": str(error)}}


class RunCancelledError(RuntimeError):
    """A progress callback requested a safe stop after the latest published run."""


class TrialRunner:
    def __init__(
        self,
        store: ArtifactStore | None = None,
        materializer: VariantMaterializer | None = None,
    ) -> None:
        self.store = store or ArtifactStore(research_root() / "artifacts")
        self.materializer = materializer or VariantMaterializer()

    @staticmethod
    def _execute(
        compiled: Any,
        *,
        trial_id: str,
        arm_id: str,
        cohort: str,
        seed: int,
        parent_run_id: str | None,
        mode: str,
    ) -> RunRecord:
        logger = None
        try:
            engine = CombatEngine.from_compiled(compiled, mode=mode, seed=seed)
            logger = StructuredLogger(engine)
            engine.setup()
            recorder = RunRecorder(engine)
            engine.run()
            observed = asdict(classify_outcome(
                engine,
                seed=seed,
                ult_casts=recorder.ult_casts,
                energy_gained=recorder.energy_gained,
                ally_actions=recorder.ally_actions,
            ))
            final_save = engine.save_state()
            return _record(
                trial_id,
                arm_id,
                cohort,
                seed,
                parent_run_id=parent_run_id,
                status="completed",
                observed=observed,
                entries=logger.entries,
                final_save=final_save,
            )
        except Exception as error:
            return _record(
                trial_id,
                arm_id,
                cohort,
                seed,
                parent_run_id=parent_run_id,
                status="failed",
                observed=_error(error),
                entries=logger.entries if logger is not None else (),
            )

    def run(
        self,
        contract: ResearchContract,
        *,
        progress: Callable[[int, int], None] | None = None,
        skip_existing: bool = False,
    ) -> TrialArtifact:
        started_at = _utcnow()
        prepared = self.materializer.prepare(contract, hypothesis=contract.question)
        resolved = prepared.resolved_protocol
        fingerprint = collect_research_fingerprint(contract, resolved, prepared)
        trial_id = self.store.publish_spec(contract, resolved, fingerprint)
        self.store.write_metadata(trial_id, {"started_at": started_at})
        variant_root = self.store.publish_variant(trial_id, prepared)

        records = []
        caveats = []
        variant_roots = self.materializer.template_roots
        if contract.experiment.comparison_kind == "mechanism":
            variant_roots = (variant_root, *variant_roots)
        arms = (
            (
                contract.experiment.baseline,
                contract.experiment.build,
                self.materializer.template_roots,
            ),
            (contract.experiment.variant, prepared.effective_build, variant_roots),
        )
        for arm, effective_build, roots in arms:
            compiled = None
            compile_error = None
            try:
                compiled = compile_encounter(
                    effective_build,
                    contract.experiment.stage,
                    template_roots=roots,
                )
                caveats.extend(
                    {"arm_id": arm.arm_id, **dict(caveat)}
                    for caveat in compiled.caveats
                )
            except Exception as error:
                compile_error = error

            for cohort, seeds in (
                ("dev", resolved.dev_seeds),
                ("holdout", resolved.holdout_seeds),
            ):
                for seed in seeds:
                    run_id = make_run_id(trial_id, arm.arm_id, cohort, seed)
                    parent_run_id = None
                    if arm.arm_id == contract.experiment.variant.arm_id:
                        parent_run_id = make_run_id(
                            trial_id,
                            contract.experiment.baseline.arm_id,
                            cohort,
                            seed,
                        )
                    if skip_existing and self.store.run_path(trial_id, run_id).exists():
                        record = self.store.read_run(trial_id, run_id)
                        if (record.arm_id, record.cohort, record.seed) != (
                            arm.arm_id, cohort, seed
                        ) or record.parent_run_id != parent_run_id:
                            raise ArtifactIntegrityError("existing run lineage mismatch")
                        records.append(record)
                    else:
                        if compile_error is not None:
                            record = _record(
                                trial_id,
                                arm.arm_id,
                                cohort,
                                seed,
                                parent_run_id=parent_run_id,
                                status="failed",
                                observed=_error(compile_error),
                            )
                        else:
                            record = self._execute(
                                compiled,
                                trial_id=trial_id,
                                arm_id=arm.arm_id,
                                cohort=cohort,
                                seed=seed,
                                parent_run_id=parent_run_id,
                                mode=resolved.mode,
                            )
                        records.append(self.store.publish_run(record))
                    if progress is not None:
                        progress(len(records), resolved.required_runs)

        failed = [record for record in records if record.status == "failed"]
        artifact = TrialArtifact(
            trial_id=trial_id,
            spec=contract,
            resolved_protocol=asdict(resolved),
            fingerprint=fingerprint,
            comparison_set=make_comparison_set(trial_id, contract, resolved),
            run_ids=tuple(record.run_id for record in records),
            status="failed" if failed else "completed",
            caveats=tuple(caveats),
            failure_reasons=tuple(run_failure_reason(record) for record in failed),
        )
        self.store.publish_result(artifact)
        self.store.write_metadata(trial_id, {
            "started_at": started_at,
            "finished_at": _utcnow(),
            "status": artifact.status,
        })
        return artifact
