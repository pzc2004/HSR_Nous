"""测试脚本：验证 Agent 系统各个组件."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")
load_dotenv(project_root / "agent" / ".env")


def test_tools():
    """测试 Tools 是否正常工作."""
    print("\n" + "="*60)
    print("测试 1：Tools 功能测试")
    print("="*60)

    from agent.tools.data_tools import (
        query_character,
        query_character_stats,
        query_relic_sets,
        query_enemy,
        list_all_characters,
        list_all_enemies,
        list_all_relic_sets,
    )
    from agent.tools.sim_tools import simulate_battle, compare_configs

    # 测试 query_character
    print("\n[1] query_character('黄泉')")
    result = query_character.invoke({"character_name": "黄泉"})
    print(result[:200] + "..." if len(result) > 200 else result)

    # 测试 query_character_stats
    print("\n[2] query_character_stats('花火', 80)")
    result = query_character_stats.invoke({"character_name": "花火", "level": 80})
    print(result)

    # 测试 list_all_characters
    print("\n[3] list_all_characters()")
    result = list_all_characters.invoke({})
    print(result[:200] + "..." if len(result) > 200 else result)

    # 测试 list_all_relic_sets
    print("\n[4] list_all_relic_sets()")
    result = list_all_relic_sets.invoke({})
    print(result[:200] + "..." if len(result) > 200 else result)

    # 测试 simulate_battle
    print("\n[5] simulate_battle('黄泉+花火+阮梅+符玄', '雷4')")
    result = simulate_battle.invoke({
        "team_config": "黄泉+花火+阮梅+符玄",
        "relic_set": "雷4",
    })
    print(result)

    # 测试 compare_configs
    print("\n[6] compare_configs('黄泉+花火+阮梅+符玄', '黄泉+银狼+佩拉+符玄', '雷4', '量子4')")
    result = compare_configs.invoke({
        "team1": "黄泉+花火+阮梅+符玄",
        "team2": "黄泉+银狼+佩拉+符玄",
        "relic1": "雷4",
        "relic2": "量子4",
    })
    print(result)

    print("\n✅ Tools 测试完成")


def test_agents():
    """测试 Agents 是否正常创建."""
    print("\n" + "="*60)
    print("测试 2：Agents 创建测试")
    print("="*60)

    from agent.agents.planner import create_planner
    from agent.agents.researcher import create_researcher
    from agent.agents.evaluator import create_evaluator
    from agent.agents.explainer import create_explainer

    print("\n[1] 创建 Planner...")
    planner = create_planner()
    print(f"  ✅ Planner 创建成功，tools: {len(planner.nodes)} 个节点")

    print("\n[2] 创建 Researcher...")
    researcher = create_researcher()
    print(f"  ✅ Researcher 创建成功，tools: {len(researcher.nodes)} 个节点")

    print("\n[3] 创建 Evaluator...")
    evaluator = create_evaluator()
    print(f"  ✅ Evaluator 创建成功，tools: {len(evaluator.nodes)} 个节点")

    print("\n[4] 创建 Explainer...")
    explainer = create_explainer()
    print(f"  ✅ Explainer 创建成功，tools: {len(explainer.nodes)} 个节点")

    print("\n✅ Agents 测试完成")


def test_orchestrator():
    """测试 Orchestrator 是否正常工作."""
    print("\n" + "="*60)
    print("测试 3：Orchestrator 集成测试")
    print("="*60)

    from agent.orchestrator import Orchestrator

    print("\n⏳ 正在初始化 Orchestrator...")
    orchestrator = Orchestrator()
    print("✅ 初始化完成")

    # 测试简单任务
    goal = "查询黄泉的基础信息"
    print(f"\n🎯 测试目标: {goal}")
    result = orchestrator.run(goal)

    print("\n📄 最终报告:")
    print(result[:500] + "..." if len(result) > 500 else result)

    print("\n✅ Orchestrator 测试完成")


def main():
    """运行所有测试."""
    print("🧪 HSR_Nous Agent 测试")
    print("="*60)

    # 检查 API Key
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n❌ 错误：请设置 OPENAI_API_KEY 环境变量")
        return 1

    # 运行测试
    try:
        test_tools()
        test_agents()
        test_orchestrator()
        print("\n" + "="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
