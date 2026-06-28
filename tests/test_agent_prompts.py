"""Prompt 稳定性测试：锁住 5 个 Agent 的 prompt 结构，防止回归。

阶段 2 把 prompt 集中到 prompts.py 时，本文件路径需要更新。
"""
from __future__ import annotations

import pytest


def _get_prompts() -> dict[str, str]:
    """从 5 个 Agent 模块收集 prompt 常量。"""
    from hsr_nous.agents.planner import PLANNER_PROMPT
    from hsr_nous.agents.builder import BUILDER_PROMPT
    from hsr_nous.agents.search import SEARCH_PROMPT
    from hsr_nous.agents.evaluator import EVALUATOR_PROMPT
    from hsr_nous.agents.explainer import EXPLAINER_PROMPT

    return {
        "planner": PLANNER_PROMPT,
        "builder": BUILDER_PROMPT,
        "search": SEARCH_PROMPT,
        "evaluator": EVALUATOR_PROMPT,
        "explainer": EXPLAINER_PROMPT,
    }


def test_all_prompts_mention_nous():
    """每个 prompt 都应包含"博识尊"品牌标识。"""
    for role, prompt in _get_prompts().items():
        assert "博识尊" in prompt, f"{role} 的 prompt 应包含 '博识尊' 品牌标识"


def test_prompts_are_distinct():
    """5 个 prompt 互不相同（防复制粘贴回归）。"""
    prompts = list(_get_prompts().values())
    assert len(set(prompts)) == 5, "5 个 prompt 必须互不相同"


def test_prompts_have_role_keywords():
    """每个 prompt 应至少提到自身角色名（中文/英文）。"""
    keywords = {
        "planner": ["规划", "计划"],
        "builder": ["构建", "候选", "方案"],
        "search": ["搜索", "参数", "优化"],
        "evaluator": ["评估", "评分", "模拟"],
        "explainer": ["解说", "解释", "报告", "推荐"],
    }
    for role, prompt in _get_prompts().items():
        assert any(k in prompt for k in keywords[role]), (
            f"{role} 的 prompt 应至少提到 {keywords[role]} 之一"
        )


@pytest.mark.xfail(
    reason="阶段 2 重写 sim_tools 后需同步移除 Evaluator prompt 的'占位模拟数据'字样",
    strict=True,
)
def test_evaluator_prompt_free_of_placeholder_marker():
    """Evaluator prompt 不应再保留"占位模拟数据"字样（阶段 2 必须替换）。

    阶段 1 当前会失败——标记为 xfail，阶段 2 完成 sim_tools 重写后转为通过。
    """
    eval_prompt = _get_prompts()["evaluator"]
    assert "占位模拟数据" not in eval_prompt, (
        "Evaluator 的 prompt 不应再含 '占位模拟数据'——sim_tools 阶段 2 替换后必须同步更新"
    )


def test_all_prompts_reasonable_length():
    """每个 prompt 应在合理长度（20-3000 字符）内。"""
    for role, prompt in _get_prompts().items():
        assert 20 < len(prompt) < 3000, f"{role} 的 prompt 长度异常: {len(prompt)}"