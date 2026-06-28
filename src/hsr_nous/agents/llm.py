"""共享 LLM 工厂：消除 5 个 Agent 文件中重复的 ChatOpenAI 配置.

所有 Agent 都通过 `make_chat_model()` 获取 LLM 实例，
统一从环境变量读取模型名、API base、API key。
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def make_chat_model(temperature: float = 0) -> ChatOpenAI:
    """构造一个 ChatOpenAI 实例，统一配置.

    优先级：
    - OPENAI_MODEL：默认 "claude-opus-4.8"（通常配合 OPENAI_API_BASE 指向 Claude 代理）
    - OPENAI_API_BASE：可选的 OpenAI 兼容端点
    - OPENAI_API_KEY：必须设置（即使指向代理）

    Args:
        temperature: 默认 0（确定性输出，Agent 任务首选）

    Returns:
        ChatOpenAI 实例
    """
    return ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "claude-opus-4.8"),
        temperature=temperature,
        base_url=os.environ.get("OPENAI_API_BASE") or None,
        api_key=os.environ.get("OPENAI_API_KEY"),
    )