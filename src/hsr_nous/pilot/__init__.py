"""自动战斗执行层（opt-in）.

**默认关闭**。启用条件：
1. `HSR_NOUS_ALLOW_AUTOPILOT=1`
2. 启动时键入 `I ACCEPT`

**严禁**：本模块通过鼠标/键盘注入方式操作游戏，违反 HoYoverse ToS，
存在账号封禁风险。仅供学习研究使用，作者不承担任何责任。

详见 docs/autopilot_safety.md。
"""
from __future__ import annotations

from hsr_nous.pilot.actuator import Actuator, DryRunActuator, is_autopilot_enabled
from hsr_nous.pilot.controller import PilotController, PilotConfig, run_pilot

__all__ = [
    "Actuator",
    "DryRunActuator",
    "is_autopilot_enabled",
    "PilotController",
    "PilotConfig",
    "run_pilot",
]