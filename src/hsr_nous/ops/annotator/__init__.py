"""打标生产 DAG（ops/annotator）——机制打标流水线：单角色端到端.

形状（designs/ANNOTATOR_DAG.md）：数据层（pull/crosscheck）→ LLM 证据/模板 →
编译闸+冒烟（内环=动态扇出打回修订）→ finalize（staging 候选包）→ human_queue（人工闸）。
LLM 节点走 `LLMRunner` 协议（tribios 接线待 llm/ 解冻；测试/dogfood 用 FakeRunner）。
社区调研/golden_diff 节点属 v2。
"""

from hsr_nous.ops.annotator.llm import FakeRunner, LLMRunner
from hsr_nous.ops.annotator.pipeline import run_character

__all__ = ["FakeRunner", "LLMRunner", "run_character"]
