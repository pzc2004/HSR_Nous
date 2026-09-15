"""打标生产 DAG（ops/annotator）——机制打标流水线：单角色/单装备端到端.

形状（designs/ANNOTATOR_DAG.md）：数据层（pull/crosscheck）→ LLM 证据/模板 →
编译闸+冒烟（内环=动态扇出打回修订）→ finalize（staging 候选包）→ human_queue（人工闸）。
LLM 节点走 `LLMRunner` 协议（tribios 接线待 llm/ 解冻；测试/dogfood 用 FakeRunner）。
装备分支（光锥/遗器）链形同构——draft 只产 hooks 块、数值区机械合并（equipment_nodes）。
"""

from hsr_nous.ops.annotator.llm import FakeRunner, LLMRunner
from hsr_nous.ops.annotator.pipeline import run_character, run_light_cone, run_relic

__all__ = ["FakeRunner", "LLMRunner", "run_character", "run_light_cone", "run_relic"]
