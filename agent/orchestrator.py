"""多智能体编排器：协调 4 个专业 Agent 完成配装优化."""

from agent.agents.planner import create_planner
from agent.agents.researcher import create_researcher
from agent.agents.evaluator import create_evaluator
from agent.agents.explainer import create_explainer


class Orchestrator:
    """多智能体编排器.

    协调 4 个专业 Agent 完成配装优化：
    1. Planner（规划者）：分析目标，制定计划
    2. Researcher（研究员）：查询角色、遗器、敌人信息
    3. Evaluator（评估者）：运行模拟，评估方案
    4. Explainer（解释者）：汇总结果，生成报告
    """

    def __init__(self):
        self.planner = create_planner()
        self.researcher = create_researcher()
        self.evaluator = create_evaluator()
        self.explainer = create_explainer()

    def run(self, user_goal: str) -> str:
        """执行完整的多智能体协作流程.

        Args:
            user_goal: 用户目标，如 "为黄泉推荐最优遗器"

        Returns:
            最终报告
        """
        print("\n" + "="*60)
        print("🚀 多智能体协作开始")
        print("="*60)

        # Step 1: Planner 制定计划
        print("\n📋 [Planner] 分析目标，制定计划...")
        plan_result = self.planner.invoke(
            {"messages": [("user", f"目标：{user_goal}\n请制定执行计划")]}
        )
        plan = plan_result['messages'][-1].content
        print(f"✅ 计划制定完成")

        # Step 2: Researcher 收集信息
        print("\n🔍 [Researcher] 查询相关信息...")
        research_result = self.researcher.invoke(
            {"messages": [("user", f"根据以下计划收集信息：\n{plan}")]}
        )
        research = research_result['messages'][-1].content
        print(f"✅ 信息收集完成")

        # Step 3: Evaluator 评估方案
        print("\n📊 [Evaluator] 运行模拟，评估方案...")
        eval_result = self.evaluator.invoke(
            {"messages": [("user", f"基于以下信息评估方案：\n{research}\n目标：{user_goal}")]}
        )
        evaluation = eval_result['messages'][-1].content
        print(f"✅ 方案评估完成")

        # Step 4: Explainer 生成报告
        print("\n📝 [Explainer] 汇总结果，生成报告...")
        report_result = self.explainer.invoke(
            {"messages": [("user", f"汇总以下信息生成报告：\n目标：{user_goal}\n计划：{plan}\n信息：{research}\n评估：{evaluation}")]}
        )
        report = report_result['messages'][-1].content

        print("\n" + "="*60)
        print("✅ 多智能体协作完成")
        print("="*60)

        return report
