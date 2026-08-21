"""策略接口：legal_action_set 生成 + 决策点注入 + 固定脚本 policy（golden case 用）.

原则：policy 只选不越权——legal_action_set 之外的选择引擎不接受。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from hsr_nous.sim.resources import ultimate_available
from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action

# 终结技插入时机
ULT_BEFORE_ACTION = "before_action"   # 行动准备期插入
ULT_AFTER_ACTION = "after_action"     # 行动后窗口插入（吃"本回合"效果）
ULT_NEVER = "never"


def legal_action_set(
    state: ActorState,
    actions: List[Action],
    skill_points: int,
) -> List[Action]:
    """当前状态下的合法行动集.

    - basic / follow_up 类恒合法
    - skill：战技点够才在集
    - ultimate：能量满才在集（ultimate_available）
    """
    legal: List[Action] = []
    for act in actions:
        if act.action_type == "ultimate":
            if ultimate_available(state, act):
                legal.append(act)
        elif act.skill_point_cost > 0:
            if skill_points >= act.skill_point_cost:
                legal.append(act)
        else:
            legal.append(act)
    return legal


@dataclass
class ScriptedPolicy:
    """固定脚本 policy（golden case / 回归测试用）.

    rotation：按回合循环的行动类型列表，如 ["skill", "basic", "basic"]；
    ult_timing：终结技插入时机（可大时如何处理）。
    """

    rotation: List[str] = field(default_factory=lambda: ["basic"])
    ult_timing: str = ULT_AFTER_ACTION

    def __post_init__(self) -> None:
        assert self.ult_timing in (ULT_BEFORE_ACTION, ULT_AFTER_ACTION, ULT_NEVER)
        self._cursor = 0

    def select_action(self, legal: List[Action]) -> Action:
        """从合法行动集按脚本选择；脚本行动不合法时回退第一个合法行动."""
        if not legal:
            raise RuntimeError("legal_action_set 为空——policy 无可选")
        want = self.rotation[self._cursor % len(self.rotation)]
        self._cursor += 1
        for act in legal:
            if act.action_type == want:
                return act
        return legal[0]

    def snapshot(self) -> dict:
        return {"rotation": list(self.rotation), "ult_timing": self.ult_timing, "cursor": self._cursor}
