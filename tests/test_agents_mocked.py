"""Agent 契约测试：mock LLM，验证 5-Agent 结构与编排器连通性。

**不依赖真实 API Key**——通过 patch `langchain.agents.create_agent` 注入伪 agent，
验证每个 Agent 的输入输出契约、Orchestrator 的串联。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# -------------------------------------------------------------------- fixtures


def _fake_agent(content: str) -> MagicMock:
    """返回一个伪 Agent：invoke(...) 返回 {"messages": [AIMessage(content)]}。"""
    from langchain_core.messages import AIMessage

    agent = MagicMock()
    agent.invoke.return_value = {"messages": [AIMessage(content=content)]}
    return agent


PLANNER_OUT = "执行计划：\n1. [Builder] 查询黄泉数据\n2. [Search] 搜索最优副词条\n3. [Evaluator] 多场景模拟\n4. [Explainer] 输出报告"
BUILDER_OUT = "候选方案：\n- 暴击流（雷4遗器 + 暴击主词条）\n- 速度流（速度鞋 + 速度光锥）\n- 击破流（击破4 + 击破主词条）"
SEARCH_OUT = "优化结果：\n暴击流：CR:CD = 70:140，攻击力 +20%\n速度流：速度 160档位\n击破流：击破特攻 250%"
EVALUATOR_OUT = "评估结果：\n- 暴击流：S 级，DPS 165,000\n- 速度流：A 级，DPS 142,000\n- 击破流：B 级，DPS 128,000"
EXPLAINER_OUT = "📋 最终推荐报告\n\n推荐方案：暴击流\n核心理由：DPS 165,000，对单一目标输出最高\n替代方案：速度流（适用多目标）\n注意事项：需凑 70:140 暴击配比"


@pytest.fixture
def patched_agents(monkeypatch):
    """一次性 patch ChatOpenAI + 5 个 create_agent 调用，避免真实 LLM 调用。

    关键：必须 patch `langchain_openai.ChatOpenAI`，因为 `create_*()` 函数体
    里直接调用 `ChatOpenAI(model=...)`，不 patch 就会发起网络请求。
    """
    # 1. Patch ChatOpenAI 构造，避免实例化时校验 API key
    # 阶段 2 重构后 Agent 文件统一从 hsr_nous.agents.llm import make_chat_model
    fake_chat = MagicMock()
    monkeypatch.setattr("hsr_nous.agents.llm.ChatOpenAI", lambda **kw: fake_chat)

    # 2. Patch create_agent 工厂，返回伪 agent
    monkeypatch.setattr(
        "hsr_nous.agents.planner.create_agent",
        lambda llm, tools, system_prompt: _fake_agent(PLANNER_OUT),
    )
    monkeypatch.setattr(
        "hsr_nous.agents.builder.create_agent",
        lambda llm, tools, system_prompt: _fake_agent(BUILDER_OUT),
    )
    monkeypatch.setattr(
        "hsr_nous.agents.search.create_agent",
        lambda llm, tools, system_prompt: _fake_agent(SEARCH_OUT),
    )
    monkeypatch.setattr(
        "hsr_nous.agents.evaluator.create_agent",
        lambda llm, tools, system_prompt: _fake_agent(EVALUATOR_OUT),
    )
    monkeypatch.setattr(
        "hsr_nous.agents.explainer.create_agent",
        lambda llm, tools, system_prompt: _fake_agent(EXPLAINER_OUT),
    )


# -------------------------------------------------------------------- tests


def test_planner_contract(patched_agents):
    from hsr_nous.agents.planner import create_planner

    agent = create_planner()
    out = agent.invoke({"messages": [("user", "为黄泉推荐最优遗器")]})
    text = out["messages"][-1].content
    assert "Builder" in text or "评估" in text, f"Planner 应输出执行计划，实际: {text[:200]}"


def test_builder_contract(patched_agents):
    from hsr_nous.agents.builder import create_builder

    agent = create_builder()
    out = agent.invoke({"messages": [("user", "生成候选配装")]})
    text = out["messages"][-1].content
    assert "候选" in text or "方案" in text, f"Builder 应输出候选方案，实际: {text[:200]}"


def test_search_contract(patched_agents):
    from hsr_nous.agents.search import create_search

    agent = create_search()
    out = agent.invoke({"messages": [("user", "搜索最优参数")]})
    text = out["messages"][-1].content
    assert any(k in text for k in ["副词条", "速度", "光锥", "优化"]), (
        f"Search 应输出优化参数，实际: {text[:200]}"
    )


def test_evaluator_contract(patched_agents):
    from hsr_nous.agents.evaluator import create_evaluator

    agent = create_evaluator()
    out = agent.invoke({"messages": [("user", "评估方案")]})
    text = out["messages"][-1].content
    assert any(grade in text for grade in ["S", "A", "B", "C"]), (
        f"Evaluator 应给出 S/A/B/C 评分，实际: {text[:200]}"
    )


def test_explainer_contract(patched_agents):
    from hsr_nous.agents.explainer import create_explainer

    agent = create_explainer()
    out = agent.invoke({"messages": [("user", "生成报告")]})
    text = out["messages"][-1].content
    assert "推荐" in text, f"Explainer 应输出推荐，实际: {text[:200]}"


def test_orchestrator_end_to_end(patched_agents):
    """Orchestrator 应串通 5 个 Agent，最终输出报告。"""
    from hsr_nous.api.orchestrator import Orchestrator

    orch = Orchestrator()
    final = orch.run("为黄泉推荐最优遗器")
    assert final == EXPLAINER_OUT, f"Orchestrator 最终输出应等于 Explainer 输出"
    assert "Planner" in orch._steps
    assert "Builder" in orch._steps


def test_orchestrator_fallback_on_agent_failure(monkeypatch):
    """单个 Agent 失败时，Orchestrator 应 fallback 并继续流程。"""
    from langchain_core.messages import AIMessage
    from hsr_nous.api.orchestrator import Orchestrator

    call_count = {"count": 0}

    def _failing_builder(llm, tools, system_prompt):
        def _invoke(input_dict):
            raise RuntimeError("Builder 模拟失败")

        agent = MagicMock()
        agent.invoke = _invoke
        return agent

    def _ok_agent(content):
        agent = MagicMock()
        agent.invoke.return_value = {"messages": [AIMessage(content=content)]}
        return agent

    monkeypatch.setattr("hsr_nous.agents.llm.ChatOpenAI", lambda **kw: MagicMock())
    monkeypatch.setattr("hsr_nous.agents.planner.create_agent", lambda *a, **kw: _ok_agent("计划: 1.查数据 2.配装 3.评估"))
    monkeypatch.setattr("hsr_nous.agents.builder.create_agent", _failing_builder)
    monkeypatch.setattr("hsr_nous.agents.search.create_agent", lambda *a, **kw: _ok_agent("优化: 暴击70:140"))
    monkeypatch.setattr("hsr_nous.agents.evaluator.create_agent", lambda *a, **kw: _ok_agent("评估: S级"))
    monkeypatch.setattr("hsr_nous.agents.explainer.create_agent", lambda *a, **kw: _ok_agent("推荐: 暴击流"))

    orch = Orchestrator()
    result = orch.run("测试 fallback")

    assert "推荐: 暴击流" in result, "Explainer 输出应在最终结果中"
    assert "[失败" in orch._steps.get("Builder", ""), "Builder 步骤应记录失败"
    assert "优化: 暴击70:140" in orch._steps.get("Search", ""), "Search 步骤应正常执行"


def test_agents_have_distinct_prompts():
    """5 个 Agent 的 prompt 必须互不相同（防复制粘贴回归）。"""
    from hsr_nous.agents.planner import PLANNER_PROMPT
    from hsr_nous.agents.builder import BUILDER_PROMPT
    from hsr_nous.agents.search import SEARCH_PROMPT
    from hsr_nous.agents.evaluator import EVALUATOR_PROMPT
    from hsr_nous.agents.explainer import EXPLAINER_PROMPT

    prompts = [PLANNER_PROMPT, BUILDER_PROMPT, SEARCH_PROMPT, EVALUATOR_PROMPT, EXPLAINER_PROMPT]
    assert len(set(prompts)) == 5, "5 个 prompt 应当各不相同"


def test_factory_imports_without_api_key():
    """即使无 OPENAI_API_KEY，import create_* 也应成功（懒加载 ChatOpenAI）。"""
    # 这一步应只触发 import，不真正实例化 ChatOpenAI
    import hsr_nous.agents  # noqa: F401
    from hsr_nous.agents import (
        create_planner,
        create_builder,
        create_search,
        create_evaluator,
        create_explainer,
    )

    assert callable(create_planner)
    assert callable(create_builder)
    assert callable(create_search)
    assert callable(create_evaluator)
    assert callable(create_explainer)