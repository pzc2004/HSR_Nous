"""单条脚本化世界线的确定性执行与证据留存（worldline-v1）。

平行于 paired-v1 试验链：一条 WorldlineSpec → 一次确定性 run_scripted 执行 →
一个不可变 WorldlineArtifact。成功与失败都发布、都留存；读取时 store 深度重算
身份与证据（见 artifacts.py 的 worldline 方法对）。失败保留语义镜像
TrialRunner：任何异常（编译失败、脚本失配、随机耗尽）都转成 status="failed"
的 artifact，而不是丢弃样本。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from hsr_nous.common import research_root
from hsr_nous.research.core.artifacts import ArtifactStore
from hsr_nous.research.core.fingerprint import collect_worldline_fingerprint
from hsr_nous.research.core.runner import _events, _final_modifiers
from hsr_nous.research.schema import (
    WorldlineArtifact,
    WorldlineSpec,
    canonical_json,
    content_hash,
)
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


def _plain_json(value: Any) -> Any:
    """冻结视图（mappingproxy/元组嵌套）→ 可改 plain JSON 形数据。

    deepcopy 不支持 mappingproxy；经 canonical JSON 往返既解开只读包装又保证
    数据是 canonical JSON 兼容形态（与构造期 _snapshot 的内容同构）。
    """
    return json.loads(canonical_json(value))


def derive_child_spec(
    parent: WorldlineArtifact,
    *,
    script: list[dict[str, Any]] | None = None,
    ultimate_script: list[dict[str, Any]] | None = None,
    random_values: tuple[float, ...] | list[float] | None = None,
    initial_sp: int | None = None,
    initial_energy_ratio: float | None = None,
    note: str | None = None,
) -> WorldlineSpec:
    """从父代世界线派生子代声明：声明式覆盖，未指定的字段一律继承父值。

    - `script`/`ultimate_script` 覆盖 build["build"]["policy"] 的对应键；
      `initial_sp`/`initial_energy_ratio` 替换顶层字段；`random_values` 给则
      使用（转 tuple）——其余（stage、build 其余部分、未点名的资源字段）
      原样继承（压缩优先：派生是声明式覆盖，不引入 diff 格式）；
    - `derived_from` 绑定父代 worldline_id 与其 worldline.json 的
      content_hash（= content_hash(parent.to_dict())，与 publish 时的存储
      哈希同公式），可选 note 为人类可读派生说明；
    - 父代是 failed artifact 允许派生——"修脚本错误再跑"是合法场景；
      父链是否完整由读侧校验（read_worldline 的父链上溯）保证。
    """
    build = _plain_json(parent.spec.build)
    policy = build["build"]["policy"]
    if script is not None:
        policy["script"] = _plain_json(list(script))
    if ultimate_script is not None:
        policy["ultimate_script"] = _plain_json(list(ultimate_script))
    derived_from: dict[str, Any] = {
        "worldline_id": parent.worldline_id,
        "content_hash": content_hash(parent.to_dict()),
    }
    if note:
        derived_from["note"] = note
    return WorldlineSpec(
        build=build,
        stage=_plain_json(parent.spec.stage),
        random_values=(tuple(random_values) if random_values is not None
                       else parent.spec.random_values),
        initial_sp=parent.spec.initial_sp if initial_sp is None else initial_sp,
        initial_energy_ratio=(parent.spec.initial_energy_ratio
                              if initial_energy_ratio is None
                              else initial_energy_ratio),
        derived_from=derived_from,
    )
