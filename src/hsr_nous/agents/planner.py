"""Planner Agent：分析目标，制定执行计划."""

from langchain.agents import create_agent

from hsr_nous.agents.llm import make_chat_model
from hsr_nous.agents.prompts import PLANNER_PROMPT


def create_planner():
    """创建 Planner Agent."""
    return create_agent(make_chat_model(), [], system_prompt=PLANNER_PROMPT)


__all__ = ["create_planner", "PLANNER_PROMPT"]
# 兼容旧 API：测试文件从 hsr_nous.agents.planner import PLANNER_PROMPT
PLANNER_PROMPT = PLANNER_PROMPT