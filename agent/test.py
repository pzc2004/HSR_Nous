from agents.planner import create_planner
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")
load_dotenv(project_root / "agent" / ".env")

planner = create_planner()
result1 = planner.invoke(
    {"messages": [("user", "目标：为黄泉推荐最优遗器\n请制定执行计划")]})

llm = ChatOpenAI(
        model="mimo-v2.5", temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1"),
    )
result2 = llm.invoke("目标：为黄泉推荐最优遗器\n请制定执行计划")
print("Planner Agent 输出：")
print(result1['messages'][-1].content)
print("\n直接调用 LLM 输出：")
print(result2.content)