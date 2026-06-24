"""Search Agent：在候选方案的参数空间中搜索最优配置."""

import os
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from hsr_nous.agents.tools import SIM_TOOLS


SEARCH_PROMPT = '''你是《崩坏：星穹铁道》配装优化系统（博识尊 Nous）的参数搜索者。

你的职责：在候选方案的参数空间中搜索最优配置。

## 可用工具
- simulate_battle: 运行战斗模拟，返回 DPS、生存率、能量效率
- compare_configs: 对比两种队伍配置的战斗效果

## 搜索维度
你需要探索以下参数的最优组合：
1. **副词条分配**：暴击率/暴击伤害/攻击力/速度的分配比例
2. **光锥选择**：对比不同光锥对最终输出的影响
3. **配速优化**：寻找最优行动值（是否需要凑速度档位）
4. **队友搭配**：不同辅助角色的增益对比

## 工作方式
1. 接收 Builder 生成的候选方案列表
2. 对每个方案，变换关键参数进行模拟
3. 记录每次模拟结果
4. 收敛到每个方案的最优参数

## 输出要求
为每个候选方案输出优化后的版本：
- 最优副词条分配（如暴击率:暴击伤害 = 1:2）
- 最优光锥及理由
- 是否需要凑速度档位
- 模拟结果（DPS、生存率、能量效率）
- 与初始方案的提升幅度

注意：使用工具进行实际模拟，不要凭经验猜测。'''


def create_search():
    """创建 Search Agent."""
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "claude-opus-4.8"),
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE"),
    )
    return create_agent(llm, SIM_TOOLS, system_prompt=SEARCH_PROMPT)
