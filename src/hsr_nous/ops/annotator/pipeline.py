"""打标 DAG 定义与驱动（ops/annotator/pipeline）——单角色端到端.

静态链：data_pull → crosscheck → evidence(LLM) → draft(LLM) → compile1（内环扇出本体：
打回扇 revise#n+compile#n，过扇 smoke，smoke 过扇 golden_diff 金样对拍（v2 机械闸——
白值/技能 id 集/scaling 全表对官方数据锚），三闸打回同环，预算尽扇 human_queue）→ finalize。
批量调度属 v2 后半；tribios 接线属 v1c（llm/ 解冻后）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.llm import LLMRunner
from hsr_nous.ops.annotator.nodes import (
    ROOT,
    community_fetch_node,
    community_search_node,
    compile_gate_node,
    crosscheck_node,
    data_pull_node,
    draft_node,
    evidence_node,
)
from hsr_nous.ops.dag import Runner, ServiceRegistry

#: 默认锚范例（起草时最近的机制族参照——drain/特殊充能/忆灵族；v2 按角色相似度选）。
# 锚喂**一篇**就够：两篇全文 ≈25k token 提示词，会把生成拖进 llm-server 上游超时空档
# （首个真跑 31.6k prompt + 32k 生成连撞 502；一篇锚 prompt ≈18k 实测稳）
DEFAULT_ANCHORS = [
    ROOT / "tests/fixtures/templates/characters/1407_遐蝶.yaml",
]


def run_character(
    cid: str,
    *,
    llm: LLMRunner,
    runs_root: "str | Path" = ROOT / "data/annotator/runs",
    budget: int = 3,
    anchors: Optional[List[Path]] = None,
    staging_root: Optional[Path] = None,
    search_fn=None,
    fetch_fn=None,
    max_workers: int = 2,
) -> Dict[str, Any]:
    """单角色打标端到端：返回运行图输出（含 finalize 候选包 或 human_queue 失败轨迹）。

    runs_root/<cid>/ 即本角色的重放状态机（断点续跑：同输入哈希命中缓存零重跑）。
    search_fn/fetch_fn：社区层注入点（测试 mock；生产缺省 ddgs 本地库 + httpx 粗提）。
    """
    workdir = Path(runs_root) / cid
    runner = Runner(workdir, services=ServiceRegistry(
        {"game_data": 4, "llm_api": 2, "compile": 1, "web_search": 2, "web_fetch": 3}),
        max_workers=max_workers)
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
