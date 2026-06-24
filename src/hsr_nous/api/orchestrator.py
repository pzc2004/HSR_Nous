"""编排器：协调 5 Agent 完成 ReAct 配装优化闭环."""

import os
from pathlib import Path
from dotenv import load_dotenv

from hsr_nous.agents.planner import create_planner
from hsr_nous.agents.builder import create_builder
from hsr_nous.agents.search import create_search
from hsr_nous.agents.evaluator import create_evaluator
from hsr_nous.agents.explainer import create_explainer

# 加载 .env（向上查找项目根目录）
_project_root = Path(__file__).resolve().parents[3]
load_dotenv(_project_root / ".env")


class Orchestrator:
    """ReAct 风格 5-Agent 编排器.

    流水线：
    1) Planner  — 拆解目标，制定执行计划
    2) Builder  — 查询数据，生成候选配装/配队方案
    3) Search   — 在候选方案上搜索最优参数
    4) Evaluator — 多场景模拟评估
    5) Explainer — 汇总对比，生成推荐报告
    """

    def __init__(self) -> None:
        self.planner = create_planner()
        self.builder = create_builder()
        self.search = create_search()
        self.evaluator = create_evaluator()
        self.explainer = create_explainer()

    def run(self, user_goal: str) -> str:
        """执行完整的 5-Agent 协作流程.

        Args:
            user_goal: 用户目标，如 "为黄泉推荐最优遗器"

        Returns:
            最终推荐报告
        """
        print("\n" + "=" * 60)
        print("🚀 博识尊 (Nous) 多智能体协作开始")
        print("=" * 60)

        # Step 1: Planner 制定计划
        print("\n📋 [Planner] 分析目标，制定计划...")
        plan_result = self.planner.invoke(
            {"messages": [("user", f"目标：{user_goal}\n请制定执行计划")]}
        )
        plan = plan_result["messages"][-1].content
        print("✅ 计划制定完成")

        # Step 2: Builder 生成候选方案
        print("\n🔨 [Builder] 查询数据，生成候选方案...")
        build_result = self.builder.invoke(
            {"messages": [("user", f"根据以下计划生成候选配装方案：\n{plan}\n\n用户目标：{user_goal}")]}
        )
        candidates = build_result["messages"][-1].content
        print("✅ 候选方案生成完成")

        # Step 3: Search 搜索最优参数
        print("\n🔍 [Search] 搜索最优参数...")
        search_result = self.search.invoke(
            {"messages": [("user", f"对以下候选方案搜索最优参数配置：\n{candidates}")]}
        )
        optimized = search_result["messages"][-1].content
        print("✅ 参数搜索完成")

        # Step 4: Evaluator 综合评估
        print("\n📊 [Evaluator] 运行模拟，综合评估...")
        eval_result = self.evaluator.invoke(
            {"messages": [("user", f"对以下优化方案进行综合评估：\n{optimized}\n\n用户目标：{user_goal}")]}
        )
        evaluation = eval_result["messages"][-1].content
        print("✅ 方案评估完成")

        # Step 5: Explainer 生成报告
        print("\n📝 [Explainer] 汇总结果，生成报告...")
        report_result = self.explainer.invoke(
            {"messages": [("user",
                           f"根据以下信息生成推荐报告：\n"
                           f"用户目标：{user_goal}\n"
                           f"执行计划：{plan}\n"
                           f"候选方案：{candidates}\n"
                           f"优化结果：{optimized}\n"
                           f"评估结论：{evaluation}")]}
        )
        report = report_result["messages"][-1].content

        print("\n" + "=" * 60)
        print("✅ 博识尊 (Nous) 协作完成")
        print("=" * 60)

        return report
