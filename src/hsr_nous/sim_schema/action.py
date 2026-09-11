"""技能/行动定义：普攻、战技、终结技、天赋等."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: 元素词表（内部小写 canonical key——damage_type / toughness_scope / Actor.element 同词表；
#: 单一事实源（原 build_compiler 私有 `_ELEMENTS` 上提——hook 动态元素求值结果校验同读）
ELEMENTS = frozenset({"physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary"})


@dataclass
class Action:
    """技能/行动."""

    action_id: str
    name: str
    action_type: str  # "basic", "skill", "ultimate", "talent", "follow_up", "elation_damage"
    target_type: str  # "single", "blast", "aoe", "self", "ally_single", "ally_aoe"
    damage_type: Optional[str] = None  # "physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary"

    # 技能倍率（按等级）
    scaling: List[Dict[str, float]] = field(default_factory=list)

    # 能量
    energy_cost: int = 0      # 终结技能量消耗
    energy_gain: Optional[int] = None  # 释放后获得的能量；None=按 action_type 查 rulebook energy 节（普攻20/战技30/终结技5），显式 0=不回能
    energy_grant: float = 0.0  # 受击回能（per-attack 归属，mechanics 05 §5.1）：命中时受击方回能 = 本值 × 受击方 ERR；打盾照回、多段逐段

    # 战技点
    skill_point_cost: int = 0  # 战技点消耗（普攻=-1回复，战技=1消耗）
    skill_point_gain: int = 0  # 战技点获取（普攻默认+1）

    # 削韧值（击破系统核心参数）
    toughness_dmg: int = 0     # 削韧值（普攻10, 战技20, 终结技30）
    # 削韧作用域（决策卡 #5，乱破/波提欧"无视弱点属性削减韧性"族）：""=默认闸
    # （攻击属性 ∈ 目标有效弱点才可削，植入弱点计入）；"all"=无视弱点任意属性可削；
    # 元素列表=这些元素无视弱点可削（静闸；modifier 携带的动态闸未落地，见 03_actor §3.8 注）
    toughness_scope: Any = ""

    # 扩散副目标（Blast：主目标 + 相邻；数值锚点 docs/mechanics/04_break_system.md 基线 10/20/10）
    scaling_blast: Optional[List[Dict[str, float]]] = None  # 相邻目标倍率表（按等级）；None=与主目标相同
    toughness_dmg_blast: Optional[int] = None  # 相邻目标削韧；None=主目标一半

    # 多段（决策卡 #19 instances 的引擎层表达）：scaling/toughness_dmg 均为**每段**数值
    instances: int = 1  # 段数；>1 时逐段结算，段间目标死亡则后续段落空（鞭尸损失）
    # 逐段确认（B35①，黄泉三段/飞霄逐击族）：>1 段时第 2 段起每段结算前挂起回决策点等确认——
    # 仅手动模式有观察效应（脚本/编译直通，expected/roll 确定性零影响）；确认不带信息，
    # 决策簿不记账、重放天然安全。段间换目标与段级变体归 B35②，本字段不表达
    segment_confirm: bool = False
    # 段级变体（B35②）：逐段覆写 {target_type, scaling, damage_type, toughness_dmg}——
    # 下标对齐段序（None=该段用基础行动）；黄泉 3 单刀+1 群攻混合段型族
    instance_variants: Optional[List[Optional[Dict[str, Any]]]] = None
    # 逐击选招（B35②，飞霄族）：每段的变体是一次真决策（玩家从变体表选）——
    # 蕴含 segment_confirm；脚本/编译策略恒取变体 0（确定性缺省口径）
    segment_choice: bool = False

    # 自定义资源（火种/毁伤/新蕊族，决策卡 #19 资源族）
    resource_gain: Dict[str, float] = field(default_factory=dict)  # 释放后获得的自定义资源 {resource_id: amount}
    ult_cost_resource: str = ""    # 非空=特殊充能：该资源 ≥ ult_cost_amount 时终结技可激活（不走能量）
    ult_cost_amount: float = 0.0
    # 实际扣量（≠门槛时显式声明——昔涟 141503 门槛 24 扣 12 族，fandom/params #4 双源）；
    # 缺省 0 = 与 ult_cost_amount 同（门槛=扣量全扣，遐蝶新蕊族口径）
    ult_consume_amount: float = 0.0
    # 免确认立即释放（ult_now/窗口按下即放，不进确认态）：白厄变身/遐蝶召唤/银狼LV.999 族——
    # 与机制类型无关（阿格莱雅变身反例：变身≠免确认），游戏设计逐角色定，必须显式标注
    ult_quick_cast: bool = False

    # 分配轴（05_effects §split）："even"=总伤按结算时存活目标数均分（逐目标各自跑公式）
    split: str = ""

    # 立即行动效果（拉条族）：非空时施放后使指定目标立即行动（"all_enemies"=敌方全体，白厄 140809 族）
    act_now_targets: str = ""

    # 助战技额度资源（assist 族）：非空时该助战技需此资源 >0 才可发动、发动消耗 1
    # （次数额度 = 资源计数，耗尽即不可发动）；空 = 无额度闸（无限次）
    assist_cost_resource: str = ""

    # 施放后挂身 modifier（dict 声明→引擎物化；v1 仅 self 目标：buff 类技能通道）
    apply_modifiers: List[Dict[str, Any]] = field(default_factory=list)

    # 资源驱动段数（毁伤族，白厄 140811）：非空时段数 = 该资源当前值 × instances_per_point（消耗前读）
    instances_from_resource: str = ""
    instances_per_point: float = 1.0  # 每 1 点资源对应几段（140811：每毁伤 4 段）
    instances_cap: int = 0            # 段数上限（140811：总倍率上限换算 26 段；0=无上限）
    consume_all_resource: str = ""    # 非空时施放后消耗该资源全部当前值（段数已先读）

    # 净化（解除自身所有可驱散负面，140811 族）
    cleanse_self: bool = False

    # 技能等级键（倍率表取档）：非空时按此键读 actor.skill_levels（如 "talent"——追加攻击倍率跟天赋级）
    level_key: str = ""

    # 机制级优先目标（03_actor §3.8.1）：非空时目标解析先按词表求值——
    # "owner_last_target"=召唤物"优先召唤者最后攻击的敌人"族（长夜月 Evey 1141301 首实例）；
    # 无法解析（无记录/目标已离场/非召唤物）回落统一决策链（手动 > policy > 缺省首个）
    prefer_target: str = ""

    # 行动级可用条件（03_actor §3.8.1，合法性表达式）：非空时进合法行动集前现场求值——
    # $self=行动方 + res_<rid> 平铺 + hook 函数族；假=不进合法集（政策/手动/web/召唤自动
    # 同一漏斗）。expr 为编译期预编译产物（build_compiler；手工构造的 Action 引擎侧懒解析）
    available_if: str = ""
    available_if_expr: object = None

    # 手动触发型忆灵技（12_summon，长夜月「如露」1141307 族——游戏：忆灵回合全自动，
    # 唯此类技能条件满足时由玩家手动点放+手选目标）：自动回合合法集剔除（绝不自动放），
    # 改入终结技窗口 ready 清单（available_if 过闸即可点放；不耗能量/不发 on_ultimate）
    manual_trigger: bool = False
