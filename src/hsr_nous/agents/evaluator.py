"""Evaluator Agent：运行战斗模拟，综合评估方案."""

from langchain.agents import create_agent

from hsr_nous.agents.llm import make_chat_model
from hsr_nous.agents.prompts import EVALUATOR_PROMPT
from hsr_nous.agents.tools import SIM_TOOLS


def create_evaluator():
    """创建 Evaluator Agent."""
    return create_agent(make_chat_model(), SIM_TOOLS, system_prompt=EVALUATOR_PROMPT)


__all__ = ["create_evaluator", "EVALUATOR_PROMPT"]
EVALUATOR_PROMPT = EVALUATOR_PROMPT
