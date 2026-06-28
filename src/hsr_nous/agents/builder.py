"""Builder Agent：查询数据并生成候选配装/配队方案."""

from langchain.agents import create_agent

from hsr_nous.agents.llm import make_chat_model
from hsr_nous.agents.prompts import BUILDER_PROMPT
from hsr_nous.agents.tools import DATA_TOOLS, WEB_TOOLS


def create_builder():
    """创建 Builder Agent."""
    tools = DATA_TOOLS + WEB_TOOLS
    return create_agent(make_chat_model(), tools, system_prompt=BUILDER_PROMPT)


__all__ = ["create_builder", "BUILDER_PROMPT"]
BUILDER_PROMPT = BUILDER_PROMPT
