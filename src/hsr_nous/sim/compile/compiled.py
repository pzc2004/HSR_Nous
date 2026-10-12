"""编译产物：不可变 CompiledEncounter 及其组件.

纯净不变量的前提——一切运行时从这些不可变产物完整重建，
绝不在上一次战斗的战场上增量修改。

不可变边界（两层）：

- **顶层容器结构不可变由类型保证**：各 frozen dataclass 的 `__post_init__` 把
  dict 字段包装为 `types.MappingProxyType`、list 字段收敛为 tuple——构造后对
  actions_by_actor/hooks/waves/parameters 等顶层容器的写入（`[..] =` / append /
  extend / pop）直接 TypeError / AttributeError；包装时防御性浅拷贝，与构造方
  手中的原 dict 断活引用（`dataclasses.replace` 重组装幂等——已是代理的值原样保留）。
- **嵌套不冻，靠纪律**：resource_decls/binding_params 的内层 dict、actions/modifiers
  列表与 Actor/Action/Modifier 实例本体不冻结。边界纪律：引擎与一切消费方不得写
  编译产物（全 src 对 compiled 容器零原地写，2026-10-12 grep 实证；运行期状态全在
  ActorState/BattleState 侧，引擎 from_compiled 注入点自拷贝顶层容器）。

拷贝语义：`MappingProxyType` 不支持 pickle 系协议——全仓库无 compiled 的
pickle/multiprocessing 消费（2026-10-12 grep 实证），故不配 `__reduce__`；新增
pickle 消费须先补。deepcopy 经各 frozen 类的 `__deepcopy__`（解代理深拷后重挂代理，
副本同守顶层冻结）支撑 debug checkpoint 链——`copy.deepcopy(engine)` 经共享的
SummonDef/CompiledPolicy 实例到达本族。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _freeze_containers(obj: Any, mapping_fields: tuple, tuple_fields: tuple) -> None:
    """frozen dataclass `__post_init__` 共用件：顶层 dict → MappingProxyType（防御浅拷贝
    断活引用）、list → tuple；已冻结的值原样跳过（replace/深拷重组装幂等）."""
    for name in mapping_fields:
        v = getattr(obj, name)
        if not isinstance(v, MappingProxyType):
            object.__setattr__(obj, name, MappingProxyType(dict(v)))
    for name in tuple_fields:
        v = getattr(obj, name)
        if not isinstance(v, tuple):
            object.__setattr__(obj, name, tuple(v))


def _frozen_deepcopy(self: Any, memo: Dict[int, Any]) -> Any:
    """frozen 编译产物通用深拷贝：MappingProxyType 不支持 pickle 系拷贝协议——解代理
    深拷后重挂代理，副本同守顶层结构不可变（重复深拷链式可用）."""
    cls = type(self)
    new = cls.__new__(cls)
    memo[id(self)] = new
    for f in fields(self):
        v = getattr(self, f.name)
        if isinstance(v, MappingProxyType):
            v = MappingProxyType(copy.deepcopy(dict(v), memo))
        else:
            v = copy.deepcopy(v, memo)
        object.__setattr__(new, f.name, v)
    return new


@dataclass(frozen=True)
class CompiledPolicyRule:
    """一条编译好的策略规则（condition 已预编译为 AST 句柄）."""

    action: str
    priority: int
    condition_expr: Optional[Any] = None   # PreparedExpression（None = 恒真）
    selector: Optional[Any] = None         # 目标选择器（字符串或参数化 dict）


@dataclass(frozen=True)
class CompiledPolicy:
    """编译好的策略：优先级降序的规则表 + 参数（parameters 顶层只读映射视图）."""

    name: str
    action_rules: tuple[CompiledPolicyRule, ...]
    target_rules: tuple[CompiledPolicyRule, ...]
    parameters: Mapping[str, Any] = field(default_factory=dict)
    ult_timing: str = "after_action"  # before_action | after_action | never
    # B4 回放变体（14_policy）：mode=rule_based(默认)/scripted(严格脚本)/hybrid(脚本+规则回退)；
    # script 逐回合有序条目（{turn(1 起), actor(id 或名), action(id 或类型), target?}）
    mode: str = "rule_based"
    script: tuple = ()

    def __post_init__(self) -> None:
        _freeze_containers(self, ("parameters",), ())

    __deepcopy__ = _frozen_deepcopy


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
    """编译好的关卡：初始阵容 + 波次敌人 + 环境（waves/enemy_actions 顶层只读映射视图）."""

    stage_id: str
    enemies: tuple[Actor, ...]                              # 初始阵容（第 1 波）
    waves: Mapping[int, tuple[Actor, ...]] = field(default_factory=dict)  # 第 2 波起
    termination_mode: str = "fixed_av"
    max_action_value: float = 450.0
    enemy_actions: Mapping[str, List[Action]] = field(default_factory=dict)  # 敌人模板自带的行动表
    cycle: Any = None  # sim_schema.encounter.Cycle（玩法模式轮次配置；stage.yaml mode → rulebook modes 查得，无 mode 则 None）

    def __post_init__(self) -> None:
        _freeze_containers(self, ("waves", "enemy_actions"), ())

    __deepcopy__ = _frozen_deepcopy


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
    # 昔涟德谬歌 story 族；召唤布场时初始化 current。顶层只读映射视图，内层 decl 不冻）
    # 反例在案：风堇 tally 曾挂忆灵（v1.2 首实例），2026-09-07 迁入忆师——"本场累计"跨重召保留）
    resource_decls: Mapping[str, Any] = field(default_factory=dict)
    # 回合控制模型（12_summon §12.6）："auto"=回合全自动（行动取首个合法非 manual_trigger、
    # 目标自动选——小伊卡/长夜/德谬歌族，游戏实况多数忆灵）；
    # "manual"=回合玩家操控（行动+目标走统一决策源——死龙族）
    control: str = "auto"

    def __post_init__(self) -> None:
        _freeze_containers(self, ("resource_decls",), ())

    __deepcopy__ = _frozen_deepcopy


@dataclass(frozen=True)
class CompiledEncounter:
    """不可变的完整战斗输入：队伍 + 关卡 + 策略（dict 字段顶层只读映射视图，list 字段 tuple）."""

    build_team: tuple[Actor, ...]
    actions_by_actor: Mapping[str, List[Action]]
    stage: CompiledStage
    policy: CompiledPolicy
    # 初始 modifier（遗器套装等编译期归并的挂身件；sim.state.Modifier，用 Any 避免循环 import）
    modifiers_by_actor: Mapping[str, List[Any]] = field(default_factory=dict)
    # 形态配置注册件：{actor_id: (StateConfig, entry_action_id)}（模板 state_config 块）
    state_configs_by_actor: Mapping[str, tuple[Any, str]] = field(default_factory=dict)
    # 机制 hook 注册件：模板 hooks 块的编译产物（CompiledHook 元组）
    hooks: tuple[Any, ...] = ()
    # 模板 custom_resources 值块注册件：{actor_id: {rid: decl}}（decl 含 max/current/
    # overflow_mode/ult_threshold/provenance——setup 初始化 current、获得统一入口按 decl 截断）
    resource_decls_by_actor: Mapping[str, Dict[str, Any]] = field(default_factory=dict)
    # 召唤物定义注册件：{summon_actor_id: SummonDef}（模板 summons 块；引擎 summon effect 消费）
    summon_defs: Mapping[str, Any] = field(default_factory=dict)
    # 绑定参数注册件：{actor_id: {param 名: 数值}}（variable_bindings 求值产物——
    # 光锥叠影参数族；引擎 hook 表达式经 `$self.<param>` 命名空间消费，15_data_separation）
    binding_params_by_actor: Mapping[str, Dict[str, float]] = field(default_factory=dict)
    # 跨 actor hook 执行序（23 §23.11 v1）：{事件名: (actor_id 优先序…)}——
    # global/trigger_order.yaml（可选；未列事件/单位按编译产物列表序兜底）
    trigger_order: Mapping[str, tuple] = field(default_factory=dict)
    # 系统单位注册件（命途系统模块 `system/paths/<path>.yaml` units 声明的编译产物——
    # 引擎托管单位（阿哈时刻族）：布场延迟到 _init_system_units，调度/排除语义读
    # 声明标记（system_flags/speed_rule/turn_handler），见 21_elation §21.4）
    system_actors: tuple[Actor, ...] = ()
    # 近似置信度通道：本队 caveats 聚合清单——各模板 caveats 机读键
    # （带 actor/来源 ref 归属）+ 编译器自动标注（mechanic_chance 期望口径族，source=compiler）。
    # 条目形 {actor, text, level: approx|pending, source: template|compiler, ref, mechanism?}。
    # **纯元数据字段——不进结算、不改任何数值（B16 铁律）**；消费点 = engine/montecarlo/
    # web 结果附带（近似显形不藏）
    caveats: tuple[Dict[str, Any], ...] = ()
    # 表达式编译器（build 编译期创建的唯一实例——经 engine 注入 policy runtime / pipeline，全链共享 _cache）
    expr: Any = None

    def __post_init__(self) -> None:
        _freeze_containers(
            self,
            ("actions_by_actor", "modifiers_by_actor", "state_configs_by_actor",
             "resource_decls_by_actor", "summon_defs", "binding_params_by_actor",
             "trigger_order"),
            ("hooks", "caveats"),
        )

    __deepcopy__ = _frozen_deepcopy

    def to_encounter(self) -> Encounter:
        """还原为引擎 v0.1 认识的 Encounter 对象（兼容层）."""
        return Encounter(
            encounter_id=self.stage.stage_id,
            name=self.stage.stage_id,
            actors=(list(self.build_team) + list(self.stage.enemies)
                    + list(self.system_actors)),
            termination=TerminationConfig(
                mode=self.stage.termination_mode,
                max_action_value=self.stage.max_action_value,
            ),
            cycle=self.stage.cycle,
        )
