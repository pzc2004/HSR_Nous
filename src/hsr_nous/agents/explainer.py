"""Explainer Agent：汇总评估结果，生成用户友好的推荐报告."""

from langchain.agents import create_agent

from hsr_nous.agents.llm import make_chat_model
from hsr_nous.agents.prompts import EXPLAINER_PROMPT


def create_explainer():
    """创建 Explainer Agent."""
    return create_agent(make_chat_model(), [], system_prompt=EXPLAINER_PROMPT)


__all__ = ["create_explainer", "EXPLAINER_PROMPT"]
EXPLAINER_PROMPT = EXPLAINER_PROMPT