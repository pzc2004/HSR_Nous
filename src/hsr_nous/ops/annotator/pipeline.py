"""打标 DAG 定义与驱动（ops/annotator/pipeline）——角色/装备/敌人端到端.

角色/装备静态链：data_pull → crosscheck → evidence(LLM) → draft(LLM) → compile1（内环扇出
本体：打回扇 revise#n+compile#n，过扇 smoke/golden/oracle_report，预算尽扇 human_queue）
→ finalize。装备只产 hooks 块，数值区机械合并（详见 equipment_nodes）。
敌人分支由 AbilityCompiler 机械产候选，完整支持时零 LLM；未知节点与覆盖缺口直接
human_queue，编译/冒烟/结构 golden 不经过 LLM 修订（详见 enemy_nodes）。
批量调度见 batch；tribios 接线见 llm（`make_tribios_runner`）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.equipment_nodes import (
    community_search_equipment_node,
    compile_gate_lc_node,
    compile_gate_relic_node,
    crosscheck_lc_node,
    crosscheck_relic_node,
    data_pull_lc_node,
    data_pull_relic_node,
    draft_lc_node,
    draft_relic_node,
    evidence_lc_node,
    evidence_relic_node,
)
from hsr_nous.ops.annotator.llm import LLMRunner
from hsr_nous.ops.annotator.nodes import (
    community_fetch_node,
    community_search_node,
    compile_gate_node,
    crosscheck_node,
    data_pull_node,
    draft_node,
    evidence_node,
)
from hsr_nous.ops.dag import QueueBackend, Runner
from hsr_nous.pipeline.paths import annotator_runs_dir, library_dir

#: 默认锚范例（起草时最近的机制族参照——drain/特殊充能/忆灵族；v2 按角色相似度选）。
# 锚喂**一篇**就够：两篇全文 ≈25k token 提示词，会把生成拖进 llm-server 上游超时空档
# （首个真跑 31.6k prompt + 32k 生成连撞 502；一篇锚 prompt ≈18k 实测稳）
DEFAULT_ANCHORS = [
    library_dir() / "characters/1407_遐蝶.yaml",
]

#: 单实体直跑缺省非 LLM 服务容量（批量由 batch.run_batch 注入批级共享容量）
_DEFAULT_SERVICES = {"game_data": 4, "compile": 1, "web_search": 2, "web_fetch": 3}


def _default_backend(max_workers: int) -> QueueBackend:
    """llm_api 只给 DAG 宽度级技术上界；实际配额由 tribios 客户端统一控制."""
    return QueueBackend({**_DEFAULT_SERVICES, "llm_api": max_workers},
                        local_capacity=max_workers)


def run_character(
    cid: str,
    *,
    llm: LLMRunner,
    runs_root: "str | Path | None" = None,
    budget: int = 3,
    anchors: Optional[List[Path]] = None,
    staging_root: Optional[Path] = None,
    search_fn=None,
    fetch_fn=None,
    max_workers: int = 2,
    backend: Optional[QueueBackend] = None,
) -> Dict[str, Any]:
    """单角色打标端到端：返回运行图输出（含 finalize 候选包 或 human_queue 失败轨迹）。

    runs_root/<cid>/ 即本角色的重放状态机（断点续跑：同输入哈希命中缓存零重跑）；
    缺省 = paths.annotator_runs_dir()（数据根唯一事实源）。
    search_fn/fetch_fn：社区层注入点（测试 mock；生产缺省 ddgs 本地库 + httpx 粗提）。
    缺省执行后端为 QueueBackend；批量共享 backend 时由调用方负责关闭。
    """
    base = Path(runs_root) if runs_root is not None else annotator_runs_dir()
    workdir = base / cid
    owned_backend = backend is None
    if owned_backend:
        backend = _default_backend(max_workers)
    runner = Runner(workdir, max_workers=max_workers, backend=backend)
    try:
        runner.add(
            data_pull_node(cid),
            crosscheck_node(cid),
            community_search_node(cid, search_fn=search_fn),
            community_fetch_node(cid, fetch_fn=fetch_fn),
            evidence_node(cid, llm),
            draft_node(cid, llm, anchors or DEFAULT_ANCHORS),
            compile_gate_node(1, cid, llm, budget, workdir, "draft", staging_root),
        )
        return runner.run()
    finally:
        if owned_backend:
            backend.shutdown()


# ---------------------------------------------------------------------------
# 装备分支（光锥/遗器）——链形同角色版；runs_root/<kind>/<id>/ 断点续跑与角色隔离
# ---------------------------------------------------------------------------

#: 装备默认锚范例：dogfood 件（光锥/套装机制通道标准形状——明显假名命名两态）+
#: 一篇真实已验收角色 fixture 当 hooks 风格锚（1303 阮·梅：光环/触发/重挂锁族写法；
#: 单篇 ≈8k 字节，token 预算安全——角色版实证单锚 ≈18k 是上限）
DEFAULT_LC_ANCHORS = [
    library_dir() / "light_cones/99001_测试光锥.yaml",
    library_dir() / "characters/1303_ruan_mei.yaml",
]
DEFAULT_RELIC_ANCHORS = [
    library_dir() / "relics/990_测试套装.yaml",
    library_dir() / "characters/1303_ruan_mei.yaml",
]


def _run_equipment(kind: str, eid: str, *, llm: LLMRunner,
                   runs_root: "str | Path", budget: int,
                   anchors: List[Path], staging_root: Optional[Path],
                   search_fn, fetch_fn, max_workers: int,
                   backend: Optional[QueueBackend] = None) -> Dict[str, Any]:
    """装备打标端到端共用驱动（kind=light_cone/relic，同构不同参）。"""
    workdir = Path(runs_root) / f"{kind}s" / str(eid)
    owned_backend = backend is None
    if owned_backend:
        backend = _default_backend(max_workers)
    runner = Runner(workdir, max_workers=max_workers, backend=backend)
    try:
        if kind == "light_cone":
            runner.add(
                data_pull_lc_node(eid),
                crosscheck_lc_node(eid),
                community_search_equipment_node(kind, eid, search_fn=search_fn),
                community_fetch_node(eid, fetch_fn=fetch_fn),
                evidence_lc_node(eid, llm),
                draft_lc_node(eid, llm, anchors),
                compile_gate_lc_node(1, eid, llm, budget, workdir, "draft", staging_root),
            )
        else:
            runner.add(
                data_pull_relic_node(eid),
                crosscheck_relic_node(eid),
                community_search_equipment_node(kind, eid, search_fn=search_fn),
                community_fetch_node(eid, fetch_fn=fetch_fn),
                evidence_relic_node(eid, llm),
                draft_relic_node(eid, llm, anchors),
                compile_gate_relic_node(1, eid, llm, budget, workdir, "draft", staging_root),
            )
        return runner.run()
    finally:
        if owned_backend:
            backend.shutdown()


def run_light_cone(
    lc_id: str,
    *,
    llm: LLMRunner,
    runs_root: "str | Path | None" = None,
    budget: int = 3,
    anchors: Optional[List[Path]] = None,
    staging_root: Optional[Path] = None,
    search_fn=None,
    fetch_fn=None,
    max_workers: int = 2,
    backend: Optional[QueueBackend] = None,
) -> Dict[str, Any]:
    """单光锥打标端到端：返回运行图输出（含 finalize 候选包 或 human_queue 失败轨迹）。

    runs_root/light_cones/<lc_id>/ 即本光锥的重放状态机（断点续跑同角色版）；
    缺省 = paths.annotator_runs_dir()。
    staging_root 缺省 data/annotator/staging_root（staging/light_cones/<id>_<名>.yaml
    与模板根同构布局——staging_root 可直接当 template_roots 注入消费）。
    search_fn/fetch_fn：社区层注入点（测试 mock；生产缺省 ddgs 本地库 + httpx 粗提）。
    缺省执行后端为 QueueBackend；批量共享 backend 时由调用方负责关闭。
    """
    base = Path(runs_root) if runs_root is not None else annotator_runs_dir()
    return _run_equipment("light_cone", str(lc_id), llm=llm, runs_root=base,
                          budget=budget, anchors=anchors or DEFAULT_LC_ANCHORS,
                          staging_root=staging_root, search_fn=search_fn,
                          fetch_fn=fetch_fn, max_workers=max_workers, backend=backend)


def run_relic(
    set_id: str,
    *,
    llm: LLMRunner,
    runs_root: "str | Path | None" = None,
    budget: int = 3,
    anchors: Optional[List[Path]] = None,
    staging_root: Optional[Path] = None,
    search_fn=None,
    fetch_fn=None,
    max_workers: int = 2,
    backend: Optional[QueueBackend] = None,
) -> Dict[str, Any]:
    """单遗器套装打标端到端（runs_root/relics/<set_id>/ 重放状态机；余同 run_light_cone）。"""
    base = Path(runs_root) if runs_root is not None else annotator_runs_dir()
    return _run_equipment("relic", str(set_id), llm=llm, runs_root=base,
                          budget=budget, anchors=anchors or DEFAULT_RELIC_ANCHORS,
                          staging_root=staging_root, search_fn=search_fn,
                          fetch_fn=fetch_fn, max_workers=max_workers, backend=backend)


def run_enemy(
    enemy_id: str,
    *,
    llm: LLMRunner,
    runs_root: "str | Path | None" = None,
    budget: int = 3,
    staging_root: Optional[Path] = None,
    max_workers: int = 2,
    backend: Optional[QueueBackend] = None,
) -> Dict[str, Any]:
    """单敌人机械打标；llm/budget 仅为统一 runner 签名，完整支持时调用次数为零."""
    from hsr_nous.ops.annotator.enemy_nodes import (
        crosscheck_enemy_node, data_pull_enemy_node, draft_enemy_node)

    del llm, budget
    base = Path(runs_root) if runs_root is not None else annotator_runs_dir()
    workdir = base / "enemies" / str(enemy_id)
    owned_backend = backend is None
    if owned_backend:
        backend = _default_backend(max_workers)
    runner = Runner(workdir, max_workers=max_workers, backend=backend)
    try:
        runner.add(
            data_pull_enemy_node(str(enemy_id)),
            crosscheck_enemy_node(str(enemy_id)),
            draft_enemy_node(str(enemy_id), workdir, staging_root),
        )
        return runner.run()
    finally:
        if owned_backend:
            backend.shutdown()
