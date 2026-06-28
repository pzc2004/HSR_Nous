"""Search Agent：在候选方案的参数空间中搜索最优配置."""

from langchain.agents import create_agent

from hsr_nous.agents.llm import make_chat_model
from hsr_nous.agents.prompts import SEARCH_PROMPT
from hsr_nous.agents.tools import SIM_TOOLS


def create_search():
    """创建 Search Agent."""
    return create_agent(make_chat_model(), SIM_TOOLS, system_prompt=SEARCH_PROMPT)


__all__ = ["create_search", "SEARCH_PROMPT"]
SEARCH_PROMPT = SEARCH_PROMPT