"""编译产物：不可变 CompiledEncounter 及其组件.

纯净不变量的前提——一切运行时从这些不可变产物完整重建，
绝不在上一次战斗的战场上增量修改。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


@dataclass(frozen=True)
class CompiledPolicyRule:
    """一条编译好的策略规则（condition 已预编译为 AST 句柄）."""

    action: str
    priority: int
    condition_expr: Optional[Any] = None   # PreparedExpression（None = 恒真）
    selector: Optional[Any] = None         # 目标选择器（字符串或参数化 dict）
    description: str = ""


@dataclass(frozen=True)
class CompiledPolicy:
    """编译好的策略：优先级降序的规则表 + 参数."""

    name: str
    action_rules: tuple[CompiledPolicyRule, ...]
    target_rules: tuple[CompiledPolicyRule, ...]
    parameters: Dict[str, Any] = field(default_factory=dict)
    ult_timing: str = "after_action"  # before_action | after_action | never


@dataclass(frozen=True)
class CompiledStage:
    """编译好的关卡：初始阵容 + 波次敌人 + 环境."""

    stage_id: str
    enemies: tuple[Actor, ...]                          # 初始阵容（第 1 波）
    waves: Dict[int, tuple[Actor, ...]] = field(default_factory=dict)  # 第 2 波起
    termination_mode: str = "fixed_av"
    max_action_value: float = 450.0


@dataclass(frozen=True)
class CompiledEncounter:
    """不可变的完整战斗输入：队伍 + 关卡 + 策略."""

    build_team: tuple[Actor, ...]
    actions_by_actor: Dict[str, List[Action]]
    stage: CompiledStage
    policy: CompiledPolicy

    def to_encounter(self) -> Encounter:
        """还原为引擎 v0.1 认识的 Encounter 对象（兼容层）."""
        return Encounter(
            encounter_id=self.stage.stage_id,
            name=self.stage.stage_id,
            actors=list(self.build_team) + list(self.stage.enemies),
            termination=TerminationConfig(
                mode=self.stage.termination_mode,
                max_action_value=self.stage.max_action_value,
            ),
        )
