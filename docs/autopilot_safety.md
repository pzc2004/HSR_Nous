# 自动战斗安全说明

⚠️ **本模块默认关闭**。启用前请阅读本文档全部内容。

## 1. 风险声明

本模块通过模拟鼠标/键盘输入操作游戏客户端，**直接违反 HoYoverse 用户协议**。

| 风险 | 严重性 | 说明 |
|---|---|---|
| 账号封禁 | 🔴 高 | HoYoverse 主动检测自动化工具 |
| 设备封禁 | 🟡 中 | 硬件 ID 黑名单（极少发生） |
| 数据丢失 | 🟡 中 | 误点击可能导致通关失败/体力消耗 |

**作者立场**：本模块作为研究 PoC 发布，作者不为任何因使用本模块造成的损失负责。

## 2. 启用条件

**必须同时满足**：
1. 设置 `HSR_NOUS_ALLOW_AUTOPILOT=1`
2. 代码内显式 `PilotConfig(accept_text="I ACCEPT")`
3. 了解 ToS 风险

仅满足前两条不会启动真机 actuator —— PilotController 会拒绝并抛 RuntimeError。

## 3. 安全机制

### 3.1 默认 DryRun

不设置环境变量时，`PilotConfig(dry_run=True)`（默认）。`DryRunActuator` 只记录事件，**不触发真实点击**。

### 3.2 Fail-safe

```python
pyautogui.FAILSAFE = True
```

鼠标移到屏幕左上角立即停止脚本——可在紧急情况中止。

### 3.3 异常立即停止

任何检测/决策/点击异常会立即终止循环，不进入下一轮。

### 3.4 置信度阈值

`PilotConfig(min_confidence=0.6)` —— 检测置信度低于此值时跳过动作。

## 4. 使用流程

### 4.1 DryRun 模式（推荐先跑这个）

```python
from hsr_nous.pilot import PilotConfig, PilotController

cfg = PilotConfig(dry_run=True, max_cycles=10)
pilot = PilotController(cfg)
results = pilot.run()

for r in results:
    print(f"cycle={r.cycle} action={r.action_taken} target={r.target}")
```

输出会显示**将会**点击的坐标，但不会真的点击。

### 4.2 真机模式（极高风险）

```python
import os
os.environ["HSR_NOUS_ALLOW_AUTOPILOT"] = "1"

from hsr_nous.pilot import PilotConfig, PilotController

cfg = PilotConfig(
    dry_run=False,
    accept_text="I ACCEPT",  # 必须
    max_cycles=10,
    min_confidence=0.7,
)
pilot = PilotController(cfg)
results = pilot.run()
```

**注意**：默认 `screen/detector.py` 是 StubDetector——无 ONNX 模型权重。
真机模式前必须先训练并加载模型（详见 `docs/screen_setup.md`）。

## 5. CLI 入口（可选）

```bash
# DryRun 模式
uv run python -m hsr_nous.pilot --max-cycles 5

# 真机模式（确认风险后）
HSR_NOUS_ALLOW_AUTOPILOT=1 uv run python -m hsr_nous.pilot --max-cycles 5
```

CLI 会在启动时打印：

```
⚠️  自动战斗模块
⚠️  本模块违反 HoYoverse ToS，使用有账号封禁风险
⚠️  仅供学习研究，作者不承担责任
⚠️  继续即代表你接受上述风险
```

如 `dry_run=False` 且未键入 `I ACCEPT`，CLI 拒绝启动。

## 6. 与现有模块的关系

```
screen/          pilot/            sim/
   │                │                 │
   ▼                ▼                 ▼
 ScreenSnapshot → PilotController → 仿真（可选）
   │                │
   │                └─→ Actuator.click()
   │                       │
   │                       ├─ DryRunActuator（默认）
   │                       └─ PyAutoGuiActuator（真机，需 ACCEPT）
```

Pilot 可选地在每次循环前调用 `sim.engine.CombatEngine` 验证动作可行性——这部分**未实施**，属于未来工作。

## 7. 推荐替代方案

如果只是想要"提示该按什么键"，不需要真机点击：

```python
from hsr_nous.api.orchestrator import Orchestrator
print(Orchestrator().run("在忘却之庭 12 层帮我打 Boss"))
```

Orchestrator 的 Explainer 会输出**应当执行的动作描述**，玩家自己点。这是更安全的方案。

## 8. 调试

```python
from hsr_nous.pilot.actuator import DryRunActuator
act = DryRunActuator()
act.click(ClickEvent(x=100, y=200))
print(act.events)  # [('click', ClickEvent(x=100, y=200, ...))]
```

记录所有"将要点击"的事件，便于调试。