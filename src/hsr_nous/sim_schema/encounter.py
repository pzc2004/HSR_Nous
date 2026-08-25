"""关卡/遭遇战定义：轮次、结束条件、完整仿真输入."""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from hsr_nous.sim_schema.policy import Policy


@dataclass
class Cycle:
    """轮次配置.

    轮次是 AV（行动值）循环机制。每个轮次有固定的 AV 预算，
    当累计行动值消耗达到预算时进入下一轮次。
    不同玩法模式有不同的 AV 配置。
    """

    first_cycle_av: int = 150
    """首轮 AV 预算（如忘却之庭 150，异相仲裁 300）."""

    subsequent_cycle_av: int = 100
    """后续轮次 AV 预算."""

    max_cycles: int = 0
    """最大轮次数，0 表示不限制（由 TerminationConfig 控制结束）."""

    reset_on_wave: bool = False
    """转波次是否重置（忘却之庭=True，其余模式=False）：轮次预算重置为首轮值、
    全体单位行动值重置（倒计时实体除外——跨波续跑，owner 实战确认 2026-08-24）；
    轮次计数不变（mechanics 03 §3.1）。其他模式转波次不重置，新怪在当前时刻进场。"""

    def __post_init__(self) -> None:
        # 绑定期校验：AV 预算必须 > 0——0/负预算会让 engine._tick_cycle 的 while 永不退出（死循环）
        if self.first_cycle_av <= 0:
            raise ValueError(
                f"Cycle.first_cycle_av 必须 > 0（当前 {self.first_cycle_av}）——"
                "0/负预算会让轮次 tick 死循环")
        if self.subsequent_cycle_av <= 0:
            raise ValueError(
                f"Cycle.subsequent_cycle_av 必须 > 0（当前 {self.subsequent_cycle_av}）——"
                "0/负预算会让轮次 tick 死循环")


@dataclass
class TerminationConfig:
    """战斗结束条件."""

    mode: str = "fixed_av"
    """结束模式（四模式登记见 10_termination.md；引擎 `_should_terminate` 消费口径）：
    - fixed_av：已实现（AV 上限截断）
    - kill_target：未实现（全灭判停是模式无关的第一分支，与本值无关）
    - survival：未实现
    - wipe：未实现
    未实现值经 stage.yaml 进入时由 stage_compiler 编译期炸指路（不静默吞）。"""

    max_action_value: int = 1500
    """fixed_av 模式下的最大行动值"""


@dataclass
class Encounter:
    """完整仿真输入：关卡 + 队伍 + 策略."""

    encounter_id: str
    name: str
    cycle: Optional[Cycle] = None
    """轮次 AV 配置，None 表示不使用轮次机制."""

    actors: List[Any] = field(default_factory=list)
    policy: Optional[Policy] = None
    """仅组装期元数据，引擎不消费（运行时策略走 CompiledPolicyRuntime /
    ScriptedPolicy 通道）——adapters/screen 组装层用它捎带"这局该用什么策略"的语义。"""

    # 结束条件
    termination: TerminationConfig = field(default_factory=TerminationConfig)
