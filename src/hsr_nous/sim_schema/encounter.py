"""关卡/遭遇战定义：敌人配置、波次、轮次、环境条件."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.policy import Policy


@dataclass
class Wave:
    """波次配置.

    每个波次定义一组敌人，当波次内所有敌人被击败后下一波次登场。
    """

    wave_index: int
    enemy_ids: List[str] = field(default_factory=list)
    enemy_levels: List[int] = field(default_factory=list)

    # 转波次时触发的效果（新敌人登场时）
    on_wave_start: List[Dict[str, Any]] = field(default_factory=list)


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

    on_cycle_start: List[Dict[str, Any]] = field(default_factory=list)
    """轮次开始时触发的效果."""

    on_cycle_end: List[Dict[str, Any]] = field(default_factory=list)
    """轮次结束时触发的效果."""


@dataclass
class FormulaConfig:
    """伤害公式配置."""

    expression: str
    parameters: List[Dict[str, Any]] = field(default_factory=list)


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

    target_ids: List[str] = field(default_factory=list)
    """kill_target 模式下要击杀的敌人 ID 列表，空列表表示全部"""

    max_turns: int = 50
    """最大回合数（防止死循环）"""

    max_battle_duration: int = 10000
    """最大行动值上限"""


@dataclass
class Encounter:
    """完整仿真输入：关卡 + 队伍 + 策略."""

    encounter_id: str
    name: str
    waves: List[Wave] = field(default_factory=list)
    cycle: Optional[Cycle] = None
    """轮次 AV 配置，None 表示不使用轮次机制."""

    environment: str = ""

    # 仿真配置
    formula: Dict[str, FormulaConfig] = field(default_factory=dict)
    globals: Dict[str, Any] = field(default_factory=dict)
    actors: List[Any] = field(default_factory=list)
    policy: Optional[Policy] = None
    initial_modifiers: List[Any] = field(default_factory=list)

    # 结束条件
    termination: TerminationConfig = field(default_factory=TerminationConfig)
