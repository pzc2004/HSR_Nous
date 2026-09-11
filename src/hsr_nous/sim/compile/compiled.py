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
    # B4 回放变体（14_policy）：mode=rule_based(默认)/scripted(严格脚本)/hybrid(脚本+规则回退)；
    # script 逐回合有序条目（{turn(1 起), actor(id 或名), action(id 或类型), target?}）
    mode: str = "rule_based"
    script: tuple = ()


@dataclass(frozen=True)
class CompiledHook:
    """编译好的机制 hook（模板 hooks 块）：事件 + 预编译条件 + 效果列表.

    模板形态（机制自包含的 DSL）：
        hooks:
          - event: "on_state_change"
            condition: "$event.from_state == 'khaslana'"   # 白名单表达式（可缺省=恒真）
            effects:
              - effect_type: "gain_resource"
                resource_id: "fire_seed"
                amount: 1
    condition 编译期过 ExprCompiler 白名单（B8：非法表达式编译期炸，不进运行时）。
    """

    owner_id: str
    event: str
    condition_expr: Optional[Any] = None   # PreparedExpression（None = 恒真）
    effects: tuple = ()                    # tuple[Dict[str, Any]]（effect_type + 参数，运行期解释）
    # 累积模式（§23.9）：主事件只入队不执行；flush_triggers 命中时聚合队列执行一次——
    # $event = 末事件 payload + targets（按首现序去重、target_filter 过滤后）
    accumulated: bool = False
    flush_triggers: tuple = ()             # tuple[str]（hook 事件名；空 + accumulated 编译期炸）
    target_filter_expr: Optional[Any] = None   # PreparedExpression（$it=候选 target id；None=恒真）


@dataclass(frozen=True)
class CompiledStage:
    """编译好的关卡：初始阵容 + 波次敌人 + 环境."""

    stage_id: str
    enemies: tuple[Actor, ...]                          # 初始阵容（第 1 波）
    waves: Dict[int, tuple[Actor, ...]] = field(default_factory=dict)  # 第 2 波起
    termination_mode: str = "fixed_av"
    max_action_value: float = 450.0
    enemy_actions: Dict[str, List[Action]] = field(default_factory=dict)  # 敌人模板自带的行动表
    cycle: Any = None  # sim_schema.encounter.Cycle（玩法模式轮次配置；stage.yaml mode → rulebook modes 查得，无 mode 则 None）


@dataclass(frozen=True)
class SummonDef:
    """编译好的召唤物定义（模板 summons 块；12_summon）.

    actor：静态本体（actor_type="summon"、summoner_id、summon_flags 已烘焙）——
    召唤时引擎按 inheritance 从召唤者 Layer-1 面板重算 stats 后克隆入场
    （继承的是编译期面板（含光锥/遗器归并），不是战斗内 effective——12_summon §12.5）。
    """

    owner_id: str               # 召唤者 actor_id
    actor: Actor                # 召唤物静态本体
    inheritance: Any = "full"   # "full" | "none" | tuple[stat 字段名, ...]（部分继承）
    # hp 覆写比例（12_summon v1.1）：>0 时召唤物 hp = 召唤时刻召唤者有效生命上限 × 本值
    # （一次性定格，覆盖 inheritance 的 hp 分量；0 = 不覆写——小伊卡 = 风堇 ×0.5 族）
    max_hp_ratio: float = 0.0
    # 召唤物 custom_resources 值块（12_summon v1.2 / §12.5：忆灵自带资源——
    # 昔涟德谬歌 story 族；召唤布场时初始化 current。
    # 反例在案：风堇 tally 曾挂忆灵（v1.2 首实例），2026-09-07 迁入忆师——"本场累计"跨重召保留）
    resource_decls: Dict[str, Any] = field(default_factory=dict)
    # 回合控制模型（12_summon §12.6）："auto"=回合全自动（行动取首个合法非 manual_trigger、
    # 目标自动选——小伊卡/长夜/德谬歌族，游戏实况多数忆灵）；
    # "manual"=回合玩家操控（行动+目标走统一决策源——死龙族）
    control: str = "auto"


@dataclass(frozen=True)
class CompiledEncounter:
    """不可变的完整战斗输入：队伍 + 关卡 + 策略."""

    build_team: tuple[Actor, ...]
    actions_by_actor: Dict[str, List[Action]]
    stage: CompiledStage
    policy: CompiledPolicy
    # 初始 modifier（遗器套装等编译期归并的挂身件；sim.state.Modifier，用 Any 避免循环 import）
    modifiers_by_actor: Dict[str, List[Any]] = field(default_factory=dict)
    # 形态配置注册件：{actor_id: (StateConfig, entry_action_id)}（模板 state_config 块）
    state_configs_by_actor: Dict[str, tuple[Any, str]] = field(default_factory=dict)
    # 机制 hook 注册件：模板 hooks 块的编译产物（CompiledHook 列表）
    hooks: List[Any] = field(default_factory=list)
    # 模板 custom_resources 值块注册件：{actor_id: {rid: decl}}（decl 含 max/current/
    # overflow_mode/ult_threshold/provenance——setup 初始化 current、获得统一入口按 decl 截断）
    resource_decls_by_actor: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # 召唤物定义注册件：{summon_actor_id: SummonDef}（模板 summons 块；引擎 summon effect 消费）
    summon_defs: Dict[str, Any] = field(default_factory=dict)
    # 绑定参数注册件：{actor_id: {param 名: 数值}}（variable_bindings 求值产物——
    # 光锥叠影参数族；引擎 hook 表达式经 `$self.<param>` 命名空间消费，15_data_separation）
    binding_params_by_actor: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # 跨 actor hook 执行序（23 §23.11 v1）：{事件名: (actor_id 优先序…)}——
    # global/trigger_order.yaml（可选；未列事件/单位按编译产物列表序兜底）
    trigger_order: Dict[str, tuple] = field(default_factory=dict)
    # 表达式编译器（build 编译期创建的唯一实例——经 engine 注入 policy runtime / pipeline，全链共享 _cache）
    expr: Any = None

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
            cycle=self.stage.cycle,
        )
