"""HSR_Nous Agent CLI 入口.

使用方式：
    python -m agent.main
    python agent/main.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")
load_dotenv(project_root / "agent" / ".env")

from agent.orchestrator import Orchestrator


def main():
    """CLI 入口."""
    print("🎮 HSR_Nous 配装优化智能体")
    print("="*60)
    print("基于 LangChain 多智能体协同的星穹铁道配装优化系统")
    print("="*60)

    # 检查 API Key
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n❌ 错误：请设置 OPENAI_API_KEY 环境变量")
        print("\n设置方法：")
        print("  1. 在项目根目录创建 .env 文件")
        print("  2. 添加: OPENAI_API_KEY=your-api-key")
        return 1

    # 创建编排器
    print("\n⏳ 正在初始化智能体...")
    orchestrator = Orchestrator()
    print("✅ 初始化完成")

    # 交互循环
    print("\n💡 输入你的问题，输入 'quit' 退出")
    print("-"*60)

    while True:
        try:
            user_input = input("\n🎯 你的问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("👋 再见！")
            break

        # 执行多智能体协作
        try:
            report = orchestrator.run(user_input)
            print("\n" + "="*60)
            print("📄 最终报告")
            print("="*60)
            print(report)
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
