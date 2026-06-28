# 端到端 Demo：账号感知配装顾问（30 行）

## 目标

把 account / screen / sim / agents 串成一个**可离线跑通**的端到端 demo：
从"模拟账号数据"到"配队 + 养成建议"。

## 30 行 Demo 脚本

```python
"""end_to_end_demo.py — 不需要真实 API key，跑通完整流程."""
from unittest.mock import patch

# 1. Mock 米游社账号（不调用真实 API）
from hsr_nous.account.models import OwnedCharacter
fake_chars = [
    OwnedCharacter(character_id="1308", name="Acheron", level=80, eidolon=2, light_cone_id="21039"),
    OwnedCharacter(character_id="1306", name="Sparkle", level=80, eidolon=1),
    OwnedCharacter(character_id="1303", name="Ruan Mei", level=80, eidolon=0),
    OwnedCharacter(character_id="1208", name="Fu Xuan", level=80, eidolon=0),
]

# 2. Mock LLM 工厂（返回固定 agent；实际生产替换为真实 ChatOpenAI）
from hsr_nous.api.orchestrator import Orchestrator
from langchain_core.messages import AIMessage
from langchain.agents import create_agent

def fake_factory(llm, tools, system_prompt):
    agent = type("FakeAgent", (), {})()
    agent.invoke = lambda inp: {"messages": [AIMessage(content="OK 推荐报告（mock）")]}
    return agent

with patch("hsr_nous.agents.planner.create_agent", fake_factory), \
     patch("hsr_nous.agents.builder.create_agent", fake_factory), \
     patch("hsr_nous.agents.search.create_agent", fake_factory), \
     patch("hsr_nous.agents.evaluator.create_agent", fake_factory), \
     patch("hsr_nous.agents.explainer.create_agent", fake_factory), \
     patch("hsr_nous.account.get_owned_characters", return_value=fake_chars), \
     patch("hsr_nous.account.is_configured", return_value=True):
    # 3. 跑 simulate_battle 验证配队
    from hsr_nous.agents.tools.sim_tools import simulate_battle
    print(simulate_battle.invoke({
        "team_config": "Acheron+Sparkle+Ruan Mei+Fu Xuan",
        "relic_set": "雷4",
    }))
    # 4. 跑 recommend_investment 给资源优先级
    from hsr_nous.agents.tools.data_tools import recommend_investment
    print(recommend_investment.invoke({
        "target_team": "Acheron+Sparkle+Ruan Mei+Fu Xuan",
    }))
    # 5. 跑 Orchestrator（mock LLM，但仍走完整 5-Agent 流程）
    orch = Orchestrator()
    print(orch.run("我已有 Acheron E2+Sparkle E1+Fu Xuan E0，推荐配队"))
```

## 输出预期

```
战斗模拟结果（基于 sim.engine.CombatEngine Phase 1）：
...
总伤害 (total_damage): 13,583
回合数 (turn_count): 49
...

资源优先级建议：
  - Acheron (dps, E2): 投入 30% 资源
  - Sparkle (support, E1): 投入 22% 资源
  - Ruan Mei (support, 未拥有): 投入 28% 资源
  - Fu Xuan (sustain, E0): 投入 20% 资源

🚀 博识尊 (Nous) 多智能体协作开始
✅ ... 协作完成
OK 推荐报告（mock）
```

## 完整版本（不 mock LLM）

去掉第 2 步的 `patch(...)`，设置环境变量后跑：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=claude-opus-4.8  # 或 gpt-4 / claude-3-5-sonnet 等
uv run python docs/demo_end_to_end.py
```

## 验收

```bash
uv run python -c "
# 直接验证 account-aware pipeline 不依赖 LLM
from hsr_nous.agents.tools.data_tools import recommend_investment
print(recommend_investment.invoke({
    'target_team': 'Acheron+Sparkle+Ruan Mei+Fu Xuan',
    'owned_chars': 'Acheron:E2+Sparkle:E1+Fu Xuan:E0',
}))
"
```

应输出资源优先级（无需 API key）。