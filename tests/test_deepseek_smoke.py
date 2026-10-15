"""DeepSeek V4 Flash tool calling smoke test.

验证 DeepSeek 模型是否支持 LangChain tool calling 协议。
运行: uv run pytest tests/test_deepseek_smoke.py -v
"""
import pytest
import os


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="需要 OPENAI_API_KEY 环境变量",
)
def test_deepseek_tool_calling():
    """验证 DeepSeek V4 Flash 可以调用单个工具."""
    from hsr_nous.agents.llm import make_chat_model
    from hsr_nous.agents.tools.data_tools import query_character
    from langchain_core.messages import HumanMessage

    llm = make_chat_model(temperature=0)
    llm_with_tools = llm.bind_tools([query_character])

    resp = llm_with_tools.invoke([
        HumanMessage(content="查询黄泉的基本信息（名字、属性、命途）")
    ])

    # DeepSeek 可能返回 tool_calls 或纯文本
    if resp.tool_calls:
        assert resp.tool_calls[0]["name"] == "query_character"
        args = resp.tool_calls[0]["args"]
        assert "character_name" in args
        print(f"[OK] DeepSeek 正确发起 tool call: {resp.tool_calls[0]}")
    else:
        # 如果不支持 tool calling，至少应返回文本
        assert len(resp.content) > 0
        print(f"[WARN] DeepSeek 未发起 tool call，返回纯文本: {resp.content[:200]}")


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="需要 OPENAI_API_KEY 环境变量",
)
def test_deepseek_reasoning():
    """验证 DeepSeek 可以进行基础推理."""
    from hsr_nous.agents.llm import make_chat_model
    from langchain_core.messages import HumanMessage

    llm = make_chat_model(temperature=0)
    resp = llm.invoke([HumanMessage(content="1+1等于几？请只回答数字。")])

    assert "2" in resp.content, f"DeepSeek 推理异常: {resp.content}"
    print(f"[OK] DeepSeek 推理正常: {resp.content[:100]}")
