"""编排器：协调 5 Agent 完成 ReAct 配装优化闭环.

改进：
- 引入 tenacity 重试，单 Agent 调用失败最多 3 次
- 每个 Agent 的输出显式记录（便于调试与 Explain 解读）
- 工具调用基于 sim.engine.CombatEngine（真实引擎，不再是占位）
- logging 替代 print，支持日志级别控制
- 单 Agent 失败时 fallback 为部分结果继续流程"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from hsr_nous.agents.builder import create_builder
from hsr_nous.agents.evaluator import create_evaluator
from hsr_nous.agents.explainer import create_explainer
from hsr_nous.agents.planner import create_planner
from hsr_nous.agents.search import create_search

logger = logging.getLogger(__name__)

# 加载 .env（向上查找项目根目录）
_project_root = Path(__file__).resolve().parents[3]
load_dotenv(_project_root / ".env")


def _retryable():
    """tenacity 重试装饰器：最多 3 次，指数退避."""
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        reraise=True,
    )


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
        self._steps: dict[str, str] = {}

    @_retryable()
    def _invoke(self, agent, user_msg: str) -> str:
        """调用单个 Agent 并提取文本输出（带重试）."""
        result = agent.invoke({"messages": [("user", user_msg)]})
        return result["messages"][-1].content

    def _safe_invoke(
        self, agent, user_msg: str, step_name: str, fallback: str = ""
    ) -> str:
        """调用 Agent，失败时记录日志并返回 fallback."""
        try:
            output = self._invoke(agent, user_msg)
            self._steps[step_name] = output
            logger.info("[%s] 完成，输出 %d 字符", step_name, len(output))
            return output
        except Exception as e:
            logger.warning("[%s] 失败: %s，使用 fallback", step_name, e)
            self._steps[step_name] = f"[失败: {e}]"
            return fallback

    def run(self, user_goal: str) -> str:
        """执行完整的 5-Agent 协作流程.

        Args:
            user_goal: 用户目标，如 "为黄泉推荐最优遗器"

        Returns:
            最终推荐报告
        """
        logger.info("博识尊 (Nous) 多智能体协作开始，目标: %s", user_goal)

        # Step 1: Planner 制定计划
        plan = self._safe_invoke(
            self.planner,
            f"目标：{user_goal}\n请制定执行计划",
            "Planner",
            fallback=f"标准流程：查询角色数据 → 生成候选方案 → 搜索优化 → 评估 → 报告",
        )

        # Step 2: Builder 生成候选方案
        candidates = self._safe_invoke(
            self.builder,
            f"根据以下计划生成候选配装方案：\n{plan}\n\n用户目标：{user_goal}",
            "Builder",
            fallback="无法生成候选方案（Builder 失败）",
        )

        # Step 3: Search 搜索最优参数
        optimized = self._safe_invoke(
            self.search,
            f"对以下候选方案搜索最优参数配置：\n{candidates}",
            "Search",
            fallback=candidates,  # 搜索失败则使用原始方案
        )

        # Step 4: Evaluator 综合评估
        evaluation = self._safe_invoke(
            self.evaluator,
            f"对以下优化方案进行综合评估：\n{optimized}\n\n用户目标：{user_goal}",
            "Evaluator",
            fallback="无法完成评估（Evaluator 失败）",
        )

        # Step 5: Explainer 生成报告
        report = self._safe_invoke(
            self.explainer,
            f"根据以下信息生成推荐报告：\n"
            f"用户目标：{user_goal}\n"
            f"执行计划：{plan}\n"
            f"候选方案：{candidates}\n"
            f"优化结果：{optimized}\n"
            f"评估结论：{evaluation}",
            "Explainer",
            fallback=self._build_emergency_report(user_goal, candidates, evaluation),
        )

        logger.info("博识尊 (Nous) 协作完成")
        return report

    def _build_emergency_report(
        self, goal: str, candidates: str, evaluation: str
    ) -> str:
        """当 Explainer 失败时，生成紧急报告."""
        return (
            f"# 配装推荐报告\n\n"
            f"**用户目标**: {goal}\n\n"
            f"## 候选方案\n{candidates}\n\n"
            f"## 评估结果\n{evaluation}\n\n"
            f"---\n*注：Explainer 阶段失败，以上为原始数据*"
        )
