"""单条脚本化世界线的确定性执行与证据留存（worldline-v1）。

平行于 paired-v1 试验链：一条 WorldlineSpec → 一次确定性 run_scripted 执行 →
一个不可变 WorldlineArtifact。成功与失败都发布、都留存；读取时 store 深度重算
身份与证据（见 artifacts.py 的 worldline 方法对）。失败保留语义镜像
TrialRunner：任何异常（编译失败、脚本失配、随机耗尽）都转成 status="failed"
的 artifact，而不是丢弃样本。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from hsr_nous.common import research_root
from hsr_nous.research.core.artifacts import ArtifactStore
from hsr_nous.research.core.fingerprint import collect_worldline_fingerprint
from hsr_nous.research.core.runner import _events, _final_modifiers
from hsr_nous.research.schema import WorldlineArtifact, WorldlineSpec, canonical_json
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.montecarlo import RunRecorder
from hsr_nous.sim.scripted import run_scripted
from hsr_nous.sim.structured_log import StructuredLogger


def _caveat_lines(caveats: Any) -> tuple[str, ...]:
    """编译 caveats（机读 dict 条目）→ 世界线声明的 str 行（canonical 文本，确定性）。"""
    return tuple(canonical_json(dict(caveat)) for caveat in caveats)


class WorldlineRunner:
    """世界线执行器：spec → 指纹 → 发布 spec → 执行 → 发布 artifact（成功失败均留存）。"""

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore(research_root() / "artifacts")

    def run(self, spec: WorldlineSpec, *, skip_existing: bool = False) -> WorldlineArtifact:
        fingerprint = collect_worldline_fingerprint(spec)
        worldline_id, _ = self.store.publish_worldline_spec(spec, fingerprint)
        if skip_existing and self.store.worldline_path(worldline_id).exists():
            return self.store.read_worldline(worldline_id)
        logger: StructuredLogger | None = None
        recorder: RunRecorder | None = None
        caveats: tuple[str, ...] = ()
        try:
            compiled = compile_encounter(spec.build, spec.stage)
            caveats = _caveat_lines(compiled.caveats)
            holder: dict[str, Any] = {}

            def prepare(engine: Any) -> None:
                nonlocal logger, recorder
                holder["engine"] = engine
                logger = StructuredLogger(engine)
                engine.setup()
                recorder = RunRecorder(engine)

            result = run_scripted(
                compiled,
                list(spec.random_values),
                initial_sp=spec.initial_sp,
                initial_energy_ratio=spec.initial_energy_ratio,
                prepare_engine=prepare,
            )
            final_save = holder["engine"].save_state()
            observed = asdict(result.record)
            observed["turn_count"] = result.state.turn_count
            observed["random_consumed"] = result.random_source.consumed
            observed["random_total"] = len(spec.random_values)
            artifact = WorldlineArtifact(
                worldline_id=worldline_id,
                spec=spec,
                fingerprint=fingerprint,
                status="completed",
                observed=observed,
                events=_events(worldline_id, logger.entries if logger is not None else ()),
                final_save=final_save,
                modifiers=_final_modifiers(worldline_id, final_save),
                caveats=caveats,
                failure_reasons=(),
            )
        except Exception as error:
            artifact = WorldlineArtifact(
                worldline_id=worldline_id,
                spec=spec,
                fingerprint=fingerprint,
                status="failed",
                observed={},
                events=(),
                final_save=None,
                modifiers=(),
                caveats=caveats,
                failure_reasons=(f"{type(error).__name__}: {error}",),
            )
        self.store.publish_worldline(artifact)
        return self.store.read_worldline(worldline_id)


def verify_worldline(store: ArtifactStore, worldline_id: str) -> WorldlineArtifact:
    """读时全量校验入口：read_worldline 本身即完成身份/字节/证据深度重算，直接转发。"""
    return store.read_worldline(worldline_id)
