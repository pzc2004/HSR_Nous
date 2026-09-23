"""战斗全状态：可序列化的战场快照（纯净不变量的载体）.

设计约束：一切运行时状态都必须是纯数据（dataclass + 基本类型），
snapshot() 可逐字段比对——两局全等验证就靠它。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hsr_nous.sim_schema.actor import Actor

MOON_COCOON_ID = "MOON_COCOON"  # 月茧态标记（well-known id，同 BRK_FREEZE 先例；授予件消耗后挂本件）
BREAK_DOT_ID_PREFIX = "BRK_DOT_"  # 击破 DoT modifier id 前缀（engine 击破链建件；跳伤路由凭此识别击破裂伤走 bleed 链）


@dataclass
class StateConfig:
    """形态配置（#20 糖化：形态 = 标记 modifier，本配置驱动合法性注入）.

    replaces_actions：形态下行动替换映射（如 basic → enhanced_basic）；
    locked_actions：形态下禁用的行动类型；
    exit_conditions：退出条件 [{trigger, value}]（on_action_count/on_resource_depleted）；
    stat_effects：形态内面板加成（并进标记 modifier——白厄"攻击力提高 X%"族）；
    final_action_id：倒计时最后一动强制施放的行动（白厄"最后的额外回合开始时立即发动最后一击"）；
    exit_remove_modifiers：退出形态时对**全体敌人**移除的 modifier_id 清单（境界植入件随形态解除）；
    banish_allies_on_enter：进入形态时其他队友离场且无法行动（白厄境界族；退出时回场）；
    countdown_spd_ratio：倒计时回合速度 = 基础速度 × 该比值（白厄"速度固定为基础速度的 60%"）；
    countdown_initial_ratio：首次倒计时初始行动值占满条比例——数值=固定比例，
        字符串 "uniform"=均匀随机（官方 tooltip"倒计时的初始行动值平均设置在 0~100% 之间"，
        owner 拍板按均匀分布解读；roll 按种子抽、expected 取期望 0.5）；缺省 1.0=满条；
    name：形态显示名（日志用中文官方名，如"卡厄斯兰那"；缺省回退 state 标识符）；
    grants_immune：形态内免疫的 debuff 类别（140805"免疫控制类负面状态"→ ["control"]）；
    entry_end_turn：入口技施放是否"结束本回合"（白厄/流萤变身族官方原文有 → True 缺省；
        昔涟涟漪族无 → False）；永续形态（exit_conditions 空）不授予倒计时回合。
    """

    state: str
    replaces_actions: Dict[str, Any] = field(default_factory=dict)  # type→id 或 id 列表（多强化技能，140809/140811 族）
    locked_actions: List[str] = field(default_factory=list)
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    stat_effects: Dict[str, float] = field(default_factory=dict)
    final_action_id: str = ""
    exit_remove_modifiers: List[str] = field(default_factory=list)
    banish_allies_on_enter: bool = False
    countdown_spd_ratio: float = 1.0
    countdown_initial_ratio: Any = 1.0   # float=固定比例 | "uniform"=均匀随机（见 docstring）
    name: str = ""
    grants_immune: List[str] = field(default_factory=list)
    # 入口技"结束本回合"闸（白厄/流萤变身族官方原文"结束本回合"→ True 缺省；
    # 昔涟涟漪族无此文本 → False——插入式开大不吞任何回合）
    entry_end_turn: bool = True

    def marker_id(self) -> str:
        return f"STATE_{self.state}"


@dataclass
class Modifier:
    """挂在身上的状态件（buff/debuff/dot/control，v0.4 完整生命周期）.

    duration：剩余时长（携带者回合 tick，0 = 永久）；stacks：层数。
    stack_mode：refresh（重置时长+1层）| independent（每层独立计时，v0.4 视同 refresh 时长）
    | replace（新实例整换旧实例）| set（层数设为 stacks_value）。
    """

    modifier_id: str
    name: str
    modifier_type: str          # "buff" | "debuff" | "dot" | "control"
    debuff_kind: str = ""       # dot 类子类型（"dot"）/ 控制类（"control"）
    duration: int = 0
    stacks: int = 1
    max_stack: int = 99
    stack_mode: str = "refresh"
    stacks_value: float = 0.0   # stack_mode == "set" 时的目标层数
    dispellable: bool = True
    singleton_group: str = ""   # 同目标同组互斥（新挂替换旧挂）
    source_id: str = ""         # 施加者 actor_id
    # 来源细化（F2 呈现层记账，行为无关——snapshot/结算/全等校验一概不读；默认空串=只有施加者粒度）：
    source_kind: str = ""       # action / hook / trace / light_cone / relic / state / ""
    source_ref: str = ""        # kind=action → action_id；hook → 可展示名；light_cone/relic → 模板名；state → 形态名；trace/空 → ""
    # 生命周期旗标（**行为字段**，结算读取——与上方呈现层记账两态不同类）：施加者（source_id）
    # 真死定论时引擎全场摘除本件——「陷入无法战斗状态时 X 效果也会被解除」族
    #（星期日 1313 蒙福者首实例，2026-09-17；结算点 engine._check_death alive=False 后、
    # actor_exit 发射前，dismiss/放逐不触发，04_modifier §4.15）
    remove_on_source_death: bool = False
    # shield 声明块留底（B3 呈现层记账，同 source_kind 口径——行为无关，snapshot/结算/全等校验一概不读）：
    # 盾值运行时账本在 ActorState.shields（ShieldInstance），此处只留公式原文供状态行展示
    shield_spec: Optional[Dict[str, Any]] = None
    stat_effects: Dict[str, float] = field(default_factory=dict)  # stat → flat 值（Layer 1）
    scaling_effects: Dict[str, tuple[str, float]] = field(default_factory=dict)  # stat → (source_stat, ratio)（Layer 2 转化）
    override_effects: Dict[str, float] = field(default_factory=dict)  # stat → 覆写值（Layer 2 覆写）
    hit_condition_expr: object = None   # 命中域条件（PreparedExpression，scoped 加成用）
    # 条件光环（04_modifier §4.16）：enable_if 不成立时数值全部不计入面板（件仍在挂载——
    # 门控非挂摘）；stat_exprs = 条件成立时现场求值的数值槽（档位随条件源变档）。
    # 两域面板读取均为无条件件面板（构造防环——pipeline.effective_stats 阶段化求值）
    enable_if_expr: object = None
    stat_exprs: Dict[str, Any] = field(default_factory=dict)  # stat → PreparedExpression
    # 命中域表达式值（04_modifier §hit_condition——与 hit_condition 同语境求值：$event
    # 命中域 + 宿主函数，$self 绑定携带者）：条件通过时逐 stat 现场求值计入当次命中
    # （静态 stat_effects 是烘焙定值，本槽服务按目标状态伸缩的 per-hit 值——
    # 22004 弱点种类增伤/23053 耗点叠层穿透族首实例）
    hit_stat_exprs: Dict[str, Any] = field(default_factory=dict)  # stat → PreparedExpression
    dot_element: str = ""       # dot 跳伤属性（dot 类用；physical 且 id 带 BREAK_DOT_ID_PREFIX 走裂伤特判——rulebook bleed_base_multi 基数区，01_formula §1.4；角色物理 DoT 走常规 dot 链）
    dot_ratio: float = 0.0      # dot 跳伤倍率（击破裂伤=1.0——rulebook break_effects.physical.bleed_ratio；常规 DoT=dot_ratio 表值；叠层 DoT=**每层**倍率——跳伤 ×max(1, stacks)）
    dot_ratio_expr: object = None  # dot 基数跳伤时求值表达式（PreparedExpression，hit_condition_expr 同先例）：非 None 时跳伤时刻以持有者为语境求值——表达式值即当跳基数（不再 ×快照 atk/×stacks，层数语义由表达式自含）；None=静态 dot_ratio 通道（施加时烘焙/取档，行为逐位不变）
    dot_base_chance: float = 1.0  # dot 施加基础概率（快照 ehr_multi 的 base_chance——期望值建模层：跳伤乘 min(1, base×(1+EHR)×(1-敌抗+穿透))，与 optimizer standardDot 同口径；施加本身确定性恒挂）
    dot_source_atk: float = 0.0  # dot 施加者攻击快照（跳伤基数；施加时刻**有效面板**，B27#3 起）
    # 攻击侧快照包（B27#3 快照切分，mechanics 02 §2.12）：施加时引擎经 pipeline.dot_snapshot_context
    # 算好存件——ability_multiplier/dmg_boost_multi/ind_dmg_boost_multi/final_dmg_multi/weaken_multi/
    # ehr_multi/be_multi + 防御/抗性区的攻击侧输入（source_level/def_pen/res_pen）；跳伤时只补目标侧
    # 链乘（防御/抗性/易伤/独立易伤/减伤/韧性减伤现值）。空 dict = 裸件（手建直调路径），攻击侧全中性兜底。
    dot_snapshot_ctx: Dict[str, float] = field(default_factory=dict)
    control_kind: str = ""      # "freeze"（跳过行动）/ "imprison"（禁锢：推条）/ "entangle"（纠缠：推条）
    weakness_add: List[str] = field(default_factory=list)  # 弱点植入（B25 stat 本体；判定走 pipeline.effective_weakness）
    grants_immune: List[str] = field(default_factory=list)  # 携带者免疫的 debuff 类别（字面 kind 词表——"control"等，非表达式；enable_if 条件件随启用态开关，04_modifier §4.7）
    tick_anchor: str = "owner_turn_end"  # 计时锚点（duration-1 时点）：owner_turn_end（默认，携带者回合结束）/ owner_turn_start（携带者回合开始——阮梅弦外音族）/ on_action（每次行动——行动次数型 buff 族）/ source_turn_end（施加者回合结束——04_modifier §4.14 duration.tick_on "$modifier.source" 的落地点；施加者离场后自然停走）/ source_turn_start（施加者回合开始——source_turn_end 的开始侧对称锚，长夜月 141302 忆灵光环族）
    effect_scope: str = "self"  # 数值作用范围：self（默认，仅携带者）/ team（光环——挂源辐射全队，阮梅弦外音/缇宝族；计时仍走 tick_anchor）
    # ---- 生存三件套（受击链末段四层分工，见 engine._check_death docstring）----
    hp_lock: bool = False        # 锁血：HP 不会降至 1 以下（伤害照算、致命留 1 血；区别于免死 cancel 与复活回拉）
    revive_percent: float = 0.0  # 复活：>0 时携带者 HP 归零消费本件，以生命上限×该比例回拉（发 on_revive）
    moon_cocoon: bool = False    # 月茧（mechanics 11 §11.1）：携带者受致命伤进月茧态（留 1 血，下次回合开始前受治疗/获盾解除，否则到期真死）；次数为战斗级（见 BattleState.moon_cocoon_used，全队每场 1 次，owner 实战确认 2026-08-22）
    forced_taunt: bool = False   # 强制嘲讽（挂敌方，如火主战技）：携带本件的敌人必须攻击 source_id（覆盖加权选目标与锁定——Fandom Aggro "ignoring Aggro and Lock On"）
    # 资源上限覆写（16_custom_resources §16.12——昔涟 1141517 新蕊溢出至 200% 族）：
    # 携带者 target_resource 资源的获得上限在 _gain_resource 统一入口被抬至 max_override
    # （多覆写取最大；v1 只抬不压——压低实例未到；两键须成对，编译期闸）
    target_resource: str = ""
    max_override: float = 0.0

    def snapshot(self) -> Dict[str, Any]:
        return {
            "modifier_id": self.modifier_id,
            "type": self.modifier_type,
            "duration": self.duration,
            "stacks": self.stacks,
            "source_id": self.source_id,
        }


@dataclass
class ShieldInstance:
    """护盾实例（独立栈，mechanics 01 §1.3 护盾叠加规则的载体）.

    每实例独立剩余值/来源/关联 modifier：
    - 多护盾**不叠加**：有效护盾值 = 所有实例中最高 remaining；受击时**所有实例同时吸收全额伤害**
    - 单次伤害超过最高实例剩余值时，未吸收部分**溢出**扣本体 HP
    - 实例归零 = 后台破盾 → 关联 modifier（modifier_id）连带消失，附带效果一并移除
    生命周期（时长 tick/驱散）复用关联 modifier——本实例只管剩余值账本。
    `pool`（04_modifier §4.15 accumulate/cap 族）：非空时与同池名实例**跨件加算**——
    池是吸收单元（有效值 = 成员剩余合计，受击 FIFO 逐扣），授予时按 cap 动态封顶截断。
    """

    shield_id: str          # 实例标识（= 关联 modifier_id，一盾一件）
    name: str
    remaining: float        # 当前剩余护盾值
    source_id: str = ""     # 施加者 actor_id
    modifier_id: str = ""   # 关联 modifier（破裂级联摘除 / modifier 移除反向摘盾）
    pool: str = ""          # 累积池名（"" = 独立实例；同池跨件加算——丹恒•腾荒四源同池族）

    def snapshot(self) -> Dict[str, Any]:
        return {
            "shield_id": self.shield_id,
            "remaining": round(self.remaining, 4),
            "source_id": self.source_id,
            "modifier_id": self.modifier_id,
            "pool": self.pool,
        }


@dataclass
class ActorState:
    """单个参战单位的运行时状态."""

    actor: Actor
    current_hp: float
    current_energy: float = 0.0
    alive: bool = True
    banished: bool = False  # 放逐/离场（选择器统一排除；AV 冻结由 scheduler 处理）
    broken: bool = False    # 已击破（base_universal = 1.0，无韧性减伤）
    toughness: float = 0.0  # 当前韧性（敌人：初始满条，由引擎按 max_toughness 填入；非敌人恒 0）
    # 多韧性条（03_actor §3.10，虚韧性族）：0=主条（max=max_toughness），1..N=追加条
    # （max= stats.toughness_bars[i-1]，后接 added_bars 机制赋予条）；按序扣除、溢出作废
    bar_index: int = 0
    added_bars: List[float] = field(default_factory=list)  # add_toughness_bar 运行期追加条 max
    modifiers: Dict[str, Modifier] = field(default_factory=dict)  # modifier_id → 实例
    resources: Dict[str, float] = field(default_factory=dict)  # 自定义资源（trigger_limit 计数器等）
    # 好活当赏条目列表（21_elation §21.5——逐角色账、带数值载荷、逐条目独立 2 回合计时；
    # 引擎原生第三形态：modifier 无数值载荷槽、custom_resource 单值无逐条计时，两态装不下）
    banger_entries: List[Dict[str, float]] = field(default_factory=list)
    state_config: Optional[StateConfig] = None  # 当前形态（None = 常态）
    shields: List[ShieldInstance] = field(default_factory=list)  # 护盾栈（并行吸收，见 engine._absorb_with_shields）

    @property
    def extra_bars(self) -> List[float]:
        """全部追加条 max（模板声明条 + 机制赋予条，按加入序）."""
        return list(self.actor.stats.toughness_bars) + list(self.added_bars)

    @property
    def bars_exhausted(self) -> bool:
        """条尽（不可再削韧）：bar_index 越过末条——与弱点击破状态解耦
        （多层韧性规则 §4.5：末条击破才进入弱点击破状态；条序打完即止，溢出作废）."""
        return self.bar_index > len(self.extra_bars)

    def bar_max(self, index: int) -> float:
        """第 index 条的满值（0=主条；≥1=追加条 index-1）."""
        if index <= 0:
            return float(self.actor.stats.max_toughness)
        return float(self.extra_bars[index - 1])

    def snapshot(self) -> Dict[str, Any]:
        return {
            "actor_id": self.actor.actor_id,
            "current_hp": round(self.current_hp, 4),
            "current_energy": round(self.current_energy, 4),
            "alive": self.alive,
            "banished": self.banished,
            "broken": self.broken,
            "toughness": round(self.toughness, 4),
            "modifiers": {k: self.modifiers[k].snapshot() for k in sorted(self.modifiers)},
            "resources": {k: round(v, 4) for k, v in sorted(self.resources.items())},
            "banger_entries": [{"value": round(e["value"], 4), "turns": e["turns"]}
                               for e in self.banger_entries],
            "state": self.state_config.state if self.state_config else "normal",
            "shields": [s.snapshot() for s in self.shields],
        }


@dataclass
class BattleState:
    """整场战斗的运行时状态（纯数据）."""

    actors: Dict[str, ActorState] = field(default_factory=dict)  # actor_id → 状态
    clock: float = 0.0          # 全局时钟（绝对时刻）
    turn_count: int = 0         # 已完成的行动数
    cycle_index: int = 1        # 当前轮次（1 起；轮次=全局时钟纯函数，mechanics 03 §3.1）
    cycle_end_clock: float = 0.0  # 当前轮次预算结束时刻（0=未启用占位：cycle=None 时 _tick_cycle 直接 return；非 None 时 _init_state 必覆写为首轮预算；转波次重置模式按规则刷新）
    skill_points: int = 0       # 战技点（B16：SP 是战斗状态，snapshot 必须收录——同种子两局全等的载体）
    # 阿哈笑点池（21_elation §21.3——**队伍账**：全队共享一池，不属于任何单个 actor；
    # B16 同口径必须进 snapshot；池无上限——punchline_multi 公式自收敛）
    punchline: float = 0.0
    # 战技点上限改写（mechanics 06 §6.1 花火天赋族挂点——实例未到，预留字段）：
    # 0 = 未改写（用 rulebook constants.sp_max_default）；>0 = 战斗中上限被改写为该值
    # （engine._sp_max 唯一读取点；改写是战斗状态，必须进 snapshot）
    sp_max_override: int = 0
    truncated: bool = False     # 撞 MAX_TURNS_SAFETY 上限被截断（没打完的局；毒数据防线——优化器不得当合法样本）
    total_damage: float = 0.0
    damage_by_actor: Dict[str, float] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)  # 战斗日志（人类可读日志行；11_combat_log 的结构化事件流未落地，见该章目标态）
    # 月茧全队次数（mechanics 11 §11.1，owner 实战确认 2026-08-22）：全队每场共用 1 次的
    # 战斗级状态——一旦有人进茧即消耗；茧中（未解除/未到期）任何人再受致命击直接真死。
    # 同一伤害事件内多人同时致死共享本次机会（判定见 engine._damage_event）
    moon_cocoon_used: bool = False

    def snapshot(self) -> Dict[str, Any]:
        return {
            "clock": round(self.clock, 4),
            "turn_count": self.turn_count,
            "cycle_index": self.cycle_index,
            "cycle_end_clock": round(self.cycle_end_clock, 4),
            "cycles_used": self.cycle_index,   # 轮次评分基础（0T/几轮通）
            "skill_points": self.skill_points,
            "punchline": round(self.punchline, 4),
            "sp_max_override": self.sp_max_override,
            "truncated": self.truncated,
            "total_damage": round(self.total_damage, 4),
            "damage_by_actor": {k: round(v, 4) for k, v in sorted(self.damage_by_actor.items())},
            "actors": {k: self.actors[k].snapshot() for k in sorted(self.actors)},
            "moon_cocoon_used": self.moon_cocoon_used,
        }
