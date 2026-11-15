"""打标生产 DAG（ops/annotator）——角色/装备/敌人机制打标流水线.

角色/装备走 LLM 证据/模板 + 编译闸内环；敌人走 AbilityCompiler 机械转换，
完整支持时零 LLM，覆盖缺口直接 human_queue。出口均为 staging 候选包或人工闸。
LLMRunner 生产经 tribios 接线，测试/dogfood 用 FakeRunner。
"""

from hsr_nous.ops.annotator.llm import FakeRunner, LLMRunner
from hsr_nous.ops.annotator.pipeline import (
    run_character, run_enemy, run_light_cone, run_relic)

__all__ = [
    "FakeRunner", "LLMRunner", "run_character", "run_enemy", "run_light_cone", "run_relic",
]
