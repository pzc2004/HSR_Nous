"""Evaluator Agent：运行战斗模拟，评估不同方案."""

import os
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agent.tools.sim_tools import simulate_battle, compare_configs


EVALUATOR_PROMPT = '''你是《崩坏：星穹铁道》配装优化团队的评估者。

你的职责：运行战斗模拟，评估不同配装方案的效果。

## 可用工具
- simulate_battle: 运行战斗模拟，返回 DPS、生存率、能量效率
- compare_configs: 对比两种队伍配置的战斗效果

## 工作方式
1. 根据收集的信息构建队伍配置
2. 为每种遗器方案运行模拟
3. 对比不同方案的数据
4. 给出评估结论

## 输出要求
- 列出每种方案的 DPS、生存率、能量效率
- 明确指出最优方案
- 说明推荐理由
- 如果数据接近，说明各方案的优缺点

## 注意
- 当前使用占位模拟数据，等 sim/ 引擎完成后将替换为真实数据
- 模拟结果仅供参考，实际效果可能因战斗环境而异'''


def create_evaluator():
    """创建 Evaluator Agent."""
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "claude-opus-4.8"),
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE"),
    )
    tools = [simulate_battle, compare_configs]
    return create_agent(llm, tools, system_prompt=EVALUATOR_PROMPT)
