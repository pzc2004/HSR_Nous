## 4. Buff / Modifier 定义

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Buff 是核心机制，所有持续效果都用它表达。

> **三语义分解（概念模型）**：一个 modifier 的本体只有两半——**效果**（谁吃、吃什么）与**持续时间的演化规则**（计时 hook）；"挂在谁身上"不是它的属性，只是默认值。三层语义各自独立：
>
> - **效果语义**（`effect_scope`：谁吃）——self（默认，携带者）/ team（光环：挂源辐射全队，阮梅弦外音/缇宝族）
> - **计时语义**（`tick_anchor`：怎么减）——owner_turn_end（默认，携带者回合结束）/ owner_turn_start（阮梅"每回合开始减 1"族）/ on_action（行动次数型）
> - **管理语义**（挂载点）——驱散/净化/免疫/查询**按人**发起的定位句柄（"驱散谁的""净化谁的"）；结界（zone）= 挂载点放在**战斗状态**上而非角色身上（罗刹"白花盛放"、姬子·启行"拓星视界"、白厄"时墟铁墓"——见 `19_zone_system.md`）
>
> 一句话：携带者正在从"buff 的本体"退化为"管理句柄的默认放置点"。

### 4.1 Modifier 结构

```yaml
# 护盾型 modifier 示例
modifier:
  modifier_id: "MOD_1001_SHIELD"
  name: "护盾"
  modifier_type: "shield"       # buff | debuff | shield | heal（dot/control 并入 debuff 作 debuff_kind 子类型，见本节末注）
  max_stack: 1
  duration: 3                    # 持续回合数；0 或缺省 = 永久（需提前移除时由状态机 `on_exit_effects` 等机制处理，见 17_actor_state.md）
  stack_mode: "refresh"          # 独立计时 | refresh | replace
  dispellable: true              # 是否可驱散

  # 触发时机和效果
  on_apply:
    - effect_type: "add_stat"
      stat: "shield"
      flat_bonus: "$self.def * 0.48 + 640"

  on_expire:
    - effect_type: "remove_stat"
      stat: "shield"
```

> **`modifier_type` 与 `debuff_kind`（层级枚举）**：`modifier_type: buff | debuff | shield | heal`；dot / control 不再与 debuff 并列，而是 debuff 的子类型，用 `debuff_kind: dot | control | generic | weaken | ...` 表达。监听"负面状态 / debuff"的机制和净化目标集**默认包含全部 `debuff_kind`**（黄泉类"队友挂负面得残梦"无需特殊处理）；需要精细化时按 `debuff_kind` 过滤。旧并列枚举（`buff | debuff | dot | shield | heal | control`）作废——旧模板迁移：`dot` → `debuff + debuff_kind: dot`，`control` → `debuff + debuff_kind: control`。

```yaml
# DOT 型 modifier 示例（dot 为 debuff 的子类型，见 debuff_kind）
modifier:
  modifier_id: "MOD_DOT_FIRE"
  name: "灼烧"
  modifier_type: "debuff"
  debuff_kind: "dot"
  duration: 2
  stack_mode: "independent"

  on_turn_start:
    - effect_type: "deal_damage"
      formula: "damage"
      damage_type: "fire"
      amount: 0.5
```

```yaml
# debuff 型 modifier 示例（减防）
# modifier 层用 stat: "def_reduction"；运行时所有 def_reduction 汇总为 actor.def_pen 参与公式
modifier:
  modifier_id: "MOD_DEF_REDUCTION"
  name: "减防"
  modifier_type: "debuff"
  stat: "def_reduction"
  flat_bonus: 0.3
  duration: 3

  on_apply:
    - effect_type: "apply_modifier"
      target: "enemy_single"
      modifier:
        modifier_id: "MOD_DEF_REDUCTION"
        modifier_type: "debuff"
        stat: "def_reduction"
        flat_bonus: 0.3
        duration: 3
```

### 4.2 数值字段：flat_bonus 与 scaling_from_source

Modifier 的数值加成拆分为两个字段。层级归属规则：scaling 部分恒为 Layer 2 tagged；flat 部分**默认也是 Layer 2 tagged**，特例可用 `flat_tagged: false` 标进 Layer 1（逐 buff 标注，见下）。

| 字段 | 类型 | 默认 | 归属层 | 说明 |
|------|------|------|--------|------|
| `flat_bonus` | expression | `0` | **Layer 2 tagged**（默认） | 固定数值加成；默认不可被再转化（知更鸟规则） |
| `scaling_from_source` | expression | `0` | **Layer 2 tagged** | 按来源 actor 的对应属性 Layer 1 比例加成 |
| `source_stat` | enum | 同 `stat` | - | scaling 读的 source 属性（跨属性 scaling 用） |
| `source_actor` | actor_ref | `self` | - | scaling 的 source actor（默认自身） |
| `flat_tagged` | bool | `true` | - | flat 部分是否标记为"转化所得"；`false` 时 flat 部分进 Layer 1（玲可类特例） |
| `override` | expression | `None` | - | **覆写**：生效期间目标属性最终面板 = 该表达式的值（跳过正常求值，见下） |
| `hit_condition` | expression | `None` | - | 命中域条件（可选）：仅命中求值时对 `$event` 求值，通过才计入该次命中 |

**`override`：覆写型数值（万敌血仇 DEF=0 类）**

与 flat/scaling 的加算语义正交：`override` 存在时，该属性的最终面板值（effective）= override 表达式的值，忽略 Layer 1 与所有加算型 modifier。

**`_pct` 族：白值百分比加成（遗器/光锥 properties 主力形态）**

`stat` 取值 `atk_pct | def_pct | hp_pct | spd_pct` 时语义为**白值百分比**：面板 = 白值 ×(1+Σpct) + Σflat——**flat 不吃百分比**（游戏内手套 +352 攻击类不进百分比基数，与 `scaling_from_source` 读 Layer 1（含 flat）的口径严格区分；写错口径会把固定值也乘进去）。引擎结算序：Layer 1（base+flat）→ **Layer 1.5（pct 族 ×白值）** → Layer 2（转化→覆写）。数据来源：原始数据 `properties` 字段（`AttackAddedRatio` 等）由 adapters 直映射为该族，无需 desc 正则。

```yaml
# 野穗伴行的快枪手 2pc：攻击力提高12%（= 白值攻击 ×0.12）
modifier:
  modifier_id: "RELIC_102_2PC"
  stat: "atk_pct"
  flat_bonus: 0.12
```

```yaml
# 万敌「血仇」状态：防御归零
modifier:
  modifier_id: "mydei_vendetta_def_zero"
  stat: "def"
  override: 0
  duration: "$self.vendetta_duration"
```

- **转化读取不受影响**：override 只作用于最终面板；`scaling_from_source` 等读 Layer 1 的场合读到的仍是原基础值（血仇 DEF=0 不污染其他属性的转化输入）
- **冲突即错**：同一属性同时只能有一个 override 生效——validator 检测到同属性多个 override 同时激活 → error（游戏中不存在此类设计，宁严勿宽）
- **互斥**：同一 modifier 不得同时携带 `override` 与 `flat_bonus`/`scaling_from_source`——覆写与加算不共存（validator error）。游戏里覆写类效果全是纯覆写，禁了不损失表达力；若未来出现真实设计再放宽
- 与 `duration` / `stack_mode` 正常组合（血仇退出即恢复原防御）

**`hit_condition`：命中域条件（组合原语）**

基础 stat × `$event` 条件的组合——不新增任何 type-scoped stat（如 `crit_dmg_by_type`）。

```yaml
# 刻律德菈 Peerage：只对"战技伤害"生效的暴击伤害 +36%
modifier:
  stat: "crit_dmg"
  flat_bonus: 0.36
  hit_condition: "$event.action_type == 'skill'"
```

**两域求值语义**：

- **面板求值**（速度用于行动值、属性用于转化读取/`$self.xxx` 引用等）：**一律忽略**带 `hit_condition` 的 modifier。面板值保持单值，两层模型（Layer 1 / Layer 2）的求值与缓存不受影响
- **命中求值**（伤害/治疗公式乘区取值时，即 `on_before_hit` 上下文）：对携带者每个 modifier 求 `hit_condition`（缺省视为 `true`），通过的才计入该次命中
- `hit_condition` 与转化标签（`tagged_as_conversion` 等）**正交**：层级归属规则照常；转化读取发生在面板域，永远读不到 `hit_condition` 的值
- 反例（不要这么做）：为"只对终结技生效的穿透"新增 `res_pen_ultimate` stat——用 `stat: "res_pen"` + `hit_condition: "$event.action_type == 'ultimate'"` 组合表达

**flat 部分的层级归属（逐 buff 标注）**：`flat_tagged: true`（默认）→ flat 部分归入 Layer 2 tagged，不可被再转化——知更鸟协奏规则（固定值被百分比部分"牵连"）；`flat_tagged: false` → flat 部分归入 Layer 1，可被其他转化读到——玲可战技特例（开服早期遗留设计，新 buff 一律按默认）。唯一事实来源：`docs/mechanics/07_buff_system.md` §7.7.4。

**`$modifier.source`：施加者引用（机制注入）**

挂在他人身上的 modifier，其 effects / 表达式可用 `$modifier.source` 引用**施加者**——昔涟未来标记挂在队友身上、队友消耗标记后给昔涟回追忆即此模式。与 `source_actor`（静态配置 scaling 读谁）正交：`$modifier.source` 是运行时归因。命名空间清单见 `22_syntax_reference.md` §22.4。

> 落地自决策卡 #13（2026-08-14）

**旧 `value` 字段的迁移**：
- 纯固定加成：`value: 0.3` → `flat_bonus: 0.3`
- 纯比例加成：`value: "$self.atk * 0.3"` → `scaling_from_source: 0.3` + `source_stat: "atk"`

### 4.3 转化维度标签

为防止属性二次转化形成循环，modifier 带 4 个维度标签（外加 flat 部分的层级标记，见 §4.2）。**"属性→增伤"同属本标签体系**（如雪衣 击破特攻→增伤，见 §4.3.4；mechanics 07 §7.7.3 注：HSR 不严格区分"属性→属性"，属性→增伤全部纳入）：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `tagged_as_conversion` | bool | `true` | 本次转化产生的值是否标记为“转化所得” |
| `flat_tagged` | bool | `true` | flat 部分是否标记为“转化所得”（进 Layer 2）；`false` 时 flat 部分进 Layer 1（玲可类特例，见 §4.2） |
| `reads_converted_values` | bool | `false` | 读 source 时是否包含其他转化产生的值 |
| `dynamic_update` | bool | `true` | `true` = 跟 source 实时联动；`false` = 释放瞬间快照锁定 |
| `continuous` | bool | `true` | 公式形式：`true` = 直接比例；`false` = 离散阶梯 |
| `threshold` | expression? | `None` | 来源属性超过此值才开始计算 |
| `max_bonus` | expression? | `None` | 加成上限 |
| `step` | expression? | `None` | 阶梯步长（仅 `continuous=false`） |
| `per_step_bonus` | expression? | `None` | 每档加成量（仅 `continuous=false`） |

#### 4.3.1 语义详解

- `tagged_as_conversion=true`：其他 scaling modifier 读 target 的 `source_stat` 时，会排除本次加成。
- `reads_converted_values=false`：读 source 时只读 Layer 1（防环默认值）。
- `dynamic_update=false`：释放瞬间读取 source 当前 Layer 1 值，之后 source 变化不影响本 buff（快照）。
- `continuous=false`：使用 `step` + `per_step_bonus` 表达“每 N 单位 source 给 M 单位 target”。

#### 4.3.2 典型组合

| 角色 / 来源 | tagged_as_conversion | reads_converted_values | dynamic_update | continuous |
|----------|---------------------|----------------------|----------------|-----------|
| 花火战技 | `true` | `false` | `false` | `true` |
| 星期日终结技 | `true` | `false` | `true` | `true` |
| 知更鸟终结技 | `true` | `false` | `true` | `true` |
| 昔涟额外能力 | `false` | `false` | `true` | `false` |
| 雪衣额外能力 | `false` | `true` | `true` | `true` |
| 阮·梅额外能力 | `false` | `true` | `true` | `false` |
| 大丽花额外能力 | `true` | `false` | `false` | `true` |
| 寒鸦终结技 | `true` | `false` | `false` | `true` |
| 符玄战技 | `true` | `false` | `false` | `true` |

#### 4.3.3 示例：花火 130602「梦游鱼」

```yaml
# data/sim_templates/characters/1306_sparkle.yaml
variable_bindings:
  - self.sparkle_ratio    = lookup_table("skill_130602_ratio",    index=$build.skill_levels.skill - 1)
  - self.sparkle_flat     = lookup_table("skill_130602_flat",     index=$build.skill_levels.skill - 1)
  - self.sparkle_duration = lookup_table("skill_130602_duration", index=$build.skill_levels.skill - 1)

actions:
  - action_id: "130602"
    name: "梦游鱼"
    action_type: "skill"
    effects:
      - effect_type: "apply_modifier"
        target: "ally_single"
        modifier:
          stat: "crit_dmg"
          flat_bonus: "$self.sparkle_flat"
          scaling_from_source: "$self.sparkle_ratio"
          source_stat: "crit_dmg"
          duration: "$self.sparkle_duration"
          tagged_as_conversion: true
          reads_converted_values: false
          dynamic_update: false    # 快照型
          continuous: true
```

#### 4.3.4 示例：雪衣额外能力

```yaml
# 假设 self.xueyi_ratio 已通过 variable_bindings 绑定
modifier:
  stat: "all_dmg_bonus"
  scaling_from_source: "$self.xueyi_ratio"
  source_stat: "break_effect"
  tagged_as_conversion: false
  reads_converted_values: true
  dynamic_update: true
  continuous: true
```

### 4.4 A/B 类 Buff 判定与结算

> **模型说明**：本节描述的是**游戏结算时机**（生命周期发射点），它们是统一事件总线上的事件；modifier 的"触发时机"是总线上的带过滤响应。A/B 类与回合四阶段作为发射点**原样保留**（游戏行为不变），其订阅模型统一收敛到 `23_event_hook_system.md` 的事件总线。

崩铁 buff 分为 A 类和 B 类，判定和结算时机不同：

| 类型 | 判定时机 | 结算时机 | 来源 |
|------|---------|---------|------|
| A 类 | 判定A(回合开始) 或 判定B(行动进行) | 结算1(回合开始) 或 结算2(回合结束) | DOT、冻结/纠缠/禁锢、遗器/光锥/技能产生的 buff |
| B 类 | 判定B(行动进行) | 结算2(回合结束) | 部分终结技产生的 buff |

**回合四阶段**：
1. **回合开始**：判定A + 结算1（DOT 与控制类效果在此结算；控制类枚举见 `docs/mechanics/07_buff_system.md`）
2. **行动准备**：推拉条、冻结补偿
3. **行动进行**：判定B（A/B 类 buff 均可在此判定）
4. **回合结束**：结算2（除 DOT 外的计时状态在此结算）

> 部分永久状态（如火主"灼热意志"，buff 本体为 `800204 牵制盗垒`，开拓者·存护天赋）**不受回合结算影响**，持续到特定移除条件。

**击破状态 + 控制效果交互**（详见 `../../../../docs/mechanics/04_break_system.md` §4.2）：
- 纠缠/禁锢仅行动延后、不跳过：敌人被推迟到达回合时照常恢复韧性、解除击破状态后正常行动（纠缠先结算量子击破附加伤害）
- 冻结/残梅绽真跳过一次行动：该次行动不恢复韧性，击破状态（韧性 = 0）维持到下一次真正行动开始
- 击破状态未恢复前无法再次削韧

### 4.5 叠加模式

| `stack_mode` | 行为 | 适用场景 |
|-------------|------|---------|
| `"refresh"` | 刷新持续时间（默认） | 多数 buff |
| `"independent"` | 每层独立计时 | 风化 DOT |
| `"replace"` | 替换旧的 | 同一 modifier 重复施加（注：不同来源护盾的全局共存规则——有效值取最高、受伤同时吸收、低盾破高盾留——见 01_base_stats.md，不由 stack_mode 表达） |
| `"set"` | 层数**设为**指定值（配 `stacks_value` 表达式；区别于加层/刷新） | 椒丘"层数同步至全场最高"族（决策卡 #18） |

### 4.6 驱散规则

`dispellable` 是**每个 modifier 实例上的正交属性**——与施加对象（我方/敌方）、类型（buff/debuff/shield/heal 及 `debuff_kind` 各子类型）全无关。**任何类型都不获得类别级可/不可解除特权**，可不可解除只看实例开关。

| `dispellable` | 说明 |
|---------------|------|
| `True` | 可解除（默认） |
| `False` | 不可解除，仅按实例显式标记——如 boss 施加在**我方角色**身上的【幸福傀儡】转化（4.2 首领 极乐颠倒•邪愿莲华主，玩家实测 + 米游社《敌人图鉴》原页），或部分 boss 自身印记 / 写明不可解除的效果 |

**驱散**（移除敌方 buff）与**净化**（移除我方 debuff，含全部 `debuff_kind` 子类型）都只命中 `dispellable: true` 的实例，顺序均为 LIFO。

> 净化**不会优先解除控制效果**。

### 4.7 效果命中公式

```yaml
hit_chance: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))"
```

> `type_res` 为类型抵抗，按 `debuff_kind` 取（当前内容仅控制类有实例，如 boss 控制类类型抵抗；dot 类默认为 0，预留"持续伤害抵抗"落点）。全体 debuff 共用本式（含 dot，参考 `docs/mechanics/07_buff_system.md:78`）。

> **`debuff_immune`（硬免疫，决策卡 #18）**：actor 级声明字段——apply 前**硬拒**，不进入命中判定。与 `type_res = 1` 的区分：效果抵抗是概率模型（可被"必中/无视抵抗"穿），硬免疫直接豁免（小伊卡"is immune to debuffs"）。控制类免疫仍走 `type_res`，不加新件。

### 4.8 Buff 触发时机清单

> **模型说明**：本清单正并入统一事件总线（`23_event_hook_system.md`，正文档）。其中的**复合触发名**（如 `on_memosprite_attack`、`on_ultimate`、`on_self_basic_skill`、`on_ally_action`）是"生命周期点 × 过滤条件"的语法糖，模板编写时等同视为 `condition` 对 `$event.actor` / `$event.action_type` 等的过滤；生命周期点本身（`on_turn_start` 等）保留为总线发射点。

| 触发时机 | 说明 | 可改性 |
|---------|------|--------|
| `on_battle_start` | 战斗开始时 | emit |
| `on_wave_start` | 波次开始时 | emit |
| `on_cycle_start` | 轮次开始时（已接线：轮次预算满时发射，见 engine._tick_cycle） | emit |
| `on_cycle_end` | 轮次结束时（已接线：同上） | emit |
| `on_turn_start` | 携带者回合开始时 | emit |
| `on_turn_end` | 携带者回合结束时 | emit |
| `on_before_action` | 行动前 | waterfall |
| `on_cast` | 技能/普攻/终结技释放时（判定效果前） | waterfall |
| `on_after_action` | 行动后 | emit |
| `on_before_hit` | 造成伤害前 | waterfall |
| `on_after_hit` | 造成伤害后 | emit |
| `on_being_targeted` | 被选为目标时 | emit |
| `on_kill` | 击杀敌人时 | emit |
| `on_ally_kill` | 队友击杀时 | emit |
| `on_break` | 击破韧性时（韧性条列表模型下 payload 带 `bar_index` 条序号） | emit |
| `on_weakness_break` | 造成弱点击破时 | emit |
| `on_hp_zero` | 生命值归零时（可能触发续命/假死等机制） | emit |
| `on_hit` | 攻击命中时（攻击方视角；受击方视角事件 `before_take_damage`/`after_being_hit` 见 §23.4） | emit |
| `on_extra_turn` | 额外回合开始时 | emit |
| `on_ally_action` | 队友行动时 | emit |
| `on_ally_damage` | 队友造成伤害时 | emit |
| `on_memosprite_attack` | 自身忆灵释放普攻/攻击时 | emit |
| `on_memosprite_skill` | 自身忆灵释放战技时 | emit |
| `on_elation_skill` | 释放欢愉技时 | emit |
| `on_self_basic_skill` | 自身普攻/战技时 | emit |
| `on_ultimate` | 终结技时 | emit |

> 以下事件以统一事件总线（`23_event_hook_system.md` §23.4）为唯一定义，本表不再重复列出（不设同名语法糖，需要时直接写总线事件 + `condition` 过滤）：受击（`before_take_damage`/`after_being_hit`）、HP 变化（`on_hp_decrease`/`on_hp_increase`）、资源阈值（`on_resource_threshold`——能量满/能量阈值用 `resource_id: energy` 过滤）、死亡/离场（`actor_exit`）、modifier 施加/移除（`after_apply_modifier`/`after_remove_modifier`——护盾类用 `modifier_type` 过滤）、阿哈时刻（`aha_instant_start`/`aha_instant_end`）、DOT 结算（`on_dot_retrigger`）、削韧（`on_toughness_damage`）、敌方主动行动（`on_enemy_action`）。

> **可改性**：`waterfall` = 判定/结算前事件，hook 可用 `modify_event` 改写白名单 payload（契约与白名单全文见 `23_event_hook_system.md` §23.6）；`emit` = 只读事实通知，禁止 `modify_event`（validator 校验）。存疑一律按 `emit`（宁严勿宽）。`on_break` 的 `bar_index` 见韧性条列表模型（`03_actor.md` §3.10）。

> 落地自决策卡 #12（2026-08-14）

### 4.9 Modifier Triggers 与 Event Hooks 的关系

Modifier 的 `on_turn_start` / `on_before_hit` 等 trigger 与通用 Event Hook **已合并为统一事件总线**（正文档：`23_event_hook_system.md`）：事件 = 发射点 + payload；响应（modifier / hook / zone 等）= `condition` 过滤 + effects。

- modifier trigger 即总线上的带过滤响应，聚焦于**状态加成/减成**的持续效果；§4.8 清单中的复合触发名（`on_memosprite_attack` 等）是"生命周期点 × 过滤条件"的语法糖
- hook 聚焦于**事件响应**的瞬时逻辑（抵扣、分摊、双向同步、累积治疗等）
- 事件枚举唯一事实来源是 `23_event_hook_system.md` §23.4；新增事件一律先考虑"现有发射点 + 过滤"，不逐机制膨胀枚举

### 4.10 两层属性模型（Layer 1 / Layer 2）

#### 4.10.1 动机

HSR 大量存在“基于某属性的比例加成”机制（如花火战技：目标暴伤 += 自身暴伤 × 30%）。如果两个这类 buff 互相施加，不分层就会形成循环：

```
花火 buff 星期日：星期日 CRIT DMG += 花火 CRIT DMG × 30%
星期日 CRIT DMG 涨了
星期日 buff 花火：花火 CRIT DMG += 星期日 CRIT DMG × 30%（用涨后的值）
... 无限循环
```

真实游戏规则：scaling modifier **只读 source 的“未被 scaling 加成过的”原始属性**。

#### 4.10.2 两层定义

每个属性拆两层（仅对可被 buff 的 stat 属性分层）：

| 层 | 内容 | 谁影响它 |
|---|------|---------|
| **Layer 1（base）** | 基础值 + 装备 + 被动行迹/星魂（+ `flat_tagged=false` 的 flat 部分，特例） | 启动时计算 / 变化时重算 |
| **Layer 2（tagged）** | `apply_modifier` 产生的数值（scaling + 默认的 flat） | modifier 生命周期 |
| **effective** | Layer 1 + Layer 2 | 公式/伤害计算使用 |

> **关键**：`apply_modifier` 产生的数值默认全部属于 Layer 2 tagged（含 `flat_bonus`）；仅当 modifier 显式标 `flat_tagged: false` 时，其 flat 部分才进 Layer 1。其他 scaling modifier 读 source 时默认只读 Layer 1（`reads_converted_values=false`），从而避免循环。逐 buff 特例规则见 `docs/mechanics/07_buff_system.md` §7.7.4。

#### 4.10.3 引擎求值流程（阶段化求值）

每次 Layer 1 变化时触发重算，按**三个阶段**执行，阶段内部按 modifier 注册顺序单遍：

```
阶段 1 — Layer 1（归入基本）
  layer1[stat] = base_value[stat]
                + Σ 行迹加成
                + Σ 装备加成
                + Σ flat_tagged=false 的 flat 部分（玲可规则，所有家族）
                + Σ 归入基本型转化（reads_converted_values=false 且
                                     tagged_as_conversion=false：读 source 当前 Layer 1）

阶段 2 — Layer 2（转化所得）
  layer2[stat] = Σ flat_tagged=true 的 flat 部分（知更鸟规则，所有家族）
                + Σ 标准转化（reads_converted_values=false 且
                              tagged_as_conversion=true：读 source 当前 Layer 1）

阶段 3 — 链式转化（reads_converted_values=true）
  读"总和" = 阶段 1+2 已完成的结果（layer1 + layer2）
  产出按 tagged_as_conversion 归层（false → Layer 1 / true → Layer 2）

effective[stat] = layer1[stat] + layer2[stat]
```

**语义钉**：

- 链式家族的"读总和" = **读其求值时点前已完成的全部部分**（与 `07_buff_system.md` §7.7.6"双向开放、吃别人转化"一致）
- 阶段 3 产出归 Layer 1 后，**本轮不重跑阶段 1/2**（读 Layer 1 的下游下一轮重算时覆盖；如需更贴游戏的即时行为，留作游戏内实验校准项）
- 快照型（`dynamic_update=false`）与阶段化正交：施加瞬间锁定来源 Layer 1，之后不变
- 阶段化保证全程单向、可终止、与注册顺序无关（顺序敏感被压缩为可终止的流水线；链式家族为开服遗留封闭集，新机制全为标准转化，问题集不再扩大）

触发重算的事件：加/移除 modifier（flat 或 scaling）、actor 死亡/复活、modifier 过期。

#### 4.10.4 跨属性 scaling

```yaml
# 假设 self.atk_to_spd_ratio 已通过 variable_bindings 绑定
modifier:
  stat: "spd"
  scaling_from_source: "$self.atk_to_spd_ratio"
  source_stat: "atk"
```

读 source.atk 的 Layer 1 加成 target.spd 的 Layer 2。

### 4.11 弱点操作类 modifier（弱点植入）

**弱点植入按 debuff 处理**——植入 = 给敌人挂一类特殊 modifier，其效果 = 修改目标弱点列表；**不加新 effect_type**（植入动作就是 `apply_modifier`，见 `05_effects.md`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `weakness_add` | `List[element]` | 存续期间目标弱点列表追加这些属性；**移除即还原**（目标弱点列表回到未植入状态） |
| `singleton_group` | string? | singleton 标签：同一目标上同组 modifier 互斥，新挂替换旧挂；加 `scope: "global" \| "team"` 升格为**跨目标单例**（师父/Bondmate"最新即唯一"族，policy: first\|latest——决策卡 #19 族 7，现状 remove(all)+apply 手写换标对收编） |

- **唯一性**：`stack_mode: "replace"`（同 ID 重挂替换）+ `singleton_group`（跨 ID 同族互斥）——银狼重复植入换属性 = 同组替换
- **削韧联动**：植入生效后目标弱点列表已含新属性，`toughness_scope` 闸门（`03_actor.md` §3.4）按修改后的列表判定，植入属性可正常削韧
- **机制事实**：见 `../../../../docs/mechanics/04_break_system.md` §4.1"弱点列表变动"

```yaml
# 银狼战技：植入弱点（弱点操作类 modifier）
- effect_type: "apply_modifier"
  target: "enemy_single"
  modifier:
    modifier_id: "MOD_SW_IMPLANT"
    name: "弱点植入"
    modifier_type: "debuff"
    debuff_kind: "generic"
    weakness_add: ["quantum"]      # 植入量子弱点（随机选属性用 random_pick 组合，见 05_effects.md）
    duration: 3
    stack_mode: "replace"
    singleton_group: "weakness_implant"   # 同目标同组互斥：新植入替换旧植入
```

**`adjust_duration(±N, filter)`：时长增减结算原子（通用）**

> 旧 `extend_duration` 字段已作废（决策卡 #15 改判）：时长增减与回合 tick 统一为同一结算原子 `adjust_duration`（effect 声明见 `05_effects.md`）。

延长/缩短已挂 modifier 的持续——**增量 ≠ refresh**：`stack_mode: "refresh"` 把剩余时长**重置为满值**；`adjust_duration` 在**剩余时长上加减 N**（剩 1 回合 +1 = 2 回合）。回合结束全体 tick（-1）、银狼行迹延长植入（+1）、界外单位手动衰减（-1）共用同一原子。目标尚无匹配 modifier 时无效果。

```yaml
# 银狼行迹：植入持续延长 1 回合
- effect_type: "adjust_duration"
  target: "primary_target"
  amount: 1                  # 剩 1 回合 +1 = 2 回合；不是 refresh 重置满值
  filter: "$mod.modifier_id == 'MOD_SW_IMPLANT'"
```

```yaml
# 德谬歌（昔涟忆灵，SPD=0 界外单位、不入行动序列没有回合）：施放技能后自身所有持续效果时长 -1
# ——无回合单位手动调用回合 tick 同一原子（无 filter = 全部持续效果）
- trigger: "on_after_action"
  effect_type: "adjust_duration"
  target: "self"
  amount: -1
```

**死亡转移 / 进战植入：总线发射点 + 重挂**

```yaml
# 银狼：被植入弱点的敌人死亡时，植入重挂到其他敌人（actor_exit 发射点 + 重挂）
hooks:
  - event: "actor_exit"
    condition: "$event.actor_type == 'monster' && $event.reason == 'death'"
    effects:
      # 需限定"死者携带植入"时叠加 has_modifier($event.actor, 'MOD_SW_IMPLANT') 过滤（白名单函数见 22_syntax_reference.md §22.4）
      - effect_type: "apply_modifier"
        target: "random_enemy"
        modifier:
          modifier_id: "MOD_SW_IMPLANT"
          name: "弱点植入"
          modifier_type: "debuff"
          debuff_kind: "generic"
          weakness_add: ["quantum"]
          duration: 3
          stack_mode: "replace"
          singleton_group: "weakness_implant"
```

```yaml
# 那刻夏族：新敌人进战即植入（actor_enter 发射点）
hooks:
  - event: "actor_enter"
    condition: "$event.actor_type == 'monster'"
    effects:
      - effect_type: "apply_modifier"
        target: "$event.actor"
        modifier:
          modifier_id: "MOD_ANAXA_IMPLANT"
          name: "进战植入"
          modifier_type: "debuff"
          debuff_kind: "generic"
          weakness_add: ["wind"]
          duration: 3
          stack_mode: "replace"
          singleton_group: "weakness_implant"
```

> 保留实例状态（剩余时长/层数）的转移用 `transfer_modifier`（见 `05_effects.md`）；本节的"重挂"是全新实例（银狼植入语义）。死亡/离场事实由 `actor_exit` 发射（`reason` 取值：`death` 死亡 / `exile` 放逐 / `dismiss_summon` 解散召唤物，见 `23_event_hook_system.md` §23.4）。

> 落地自决策卡 #9（2026-08-14）

---

### 4.12 计数器宏族（统一计数器框架）

> **未接线（设计预览）**：本节糖族（`trigger_limit` / `every_n` / `accumulate` / `tally`）的 desugar 链路未接入编译器——在模板中使用这些键会被编译器按"已知但未落地"**拒绝**（编译期报错指路本节，不是静默吞）。展开器原型见 `sim/compile/sugar.py`。

声明式计数/限次字段族——修饰 modifier/hook 的触发频率与累计阈值。**语法糖非原语**：绑定期统一 desugar 为 `16_custom_resources.md` 的计数器原语（资源声明 + 事件 hook + 门控 condition），引擎零新概念。四个表面糖共用同一 desugar 路径：

**① `trigger_limit`（额度限次）**：

```yaml
trigger_limit: {per_turn: 1}                         # 每回合最多 1 次
trigger_limit: {count: 2, reset_on: "cast:ultimate"} # 限 2 次，指定事件重置（开大重置族）
trigger_limit: {per_attack: 1}                       # 每次攻击限 1 次
trigger_limit: {per_wave: 1}                         # 每波次限 1 次
trigger_limit: {per_instance: 2}                     # 每实例限 2 次
trigger_limit: {per_target: 1, reset_on: "target_fatal_hit"}  # 按目标实例化 + 自定义重置
trigger_limit: {cooldown_turns: 3}                   # 冷却：每 3 回合 1 次
trigger_limit: {once_per_battle: true}               # 每场仅 1 次（per_battle: N 参数化）
```

- 窗口档：`per_turn`（默认）/ `per_wave` / `per_action` / `per_attack` / `per_instance` / `once_per_battle` / `per_battle: N` / `cooldown_turns: N` / `per_target`
- `reset_on: <event_spec>`：自定义重置事件，覆盖窗口默认重置点
- **边缘语义（钉死）**：`per_turn` 重置点 = 携带者**回合开始**；插入式行动（追加/终结技/助战）不算回合、不触发重置

**② `every_n`（累计满 N 触发，①的对偶）**：

```yaml
every_n: {event: "after_consume", filter: "resource_id == 'sp'", n: 3, then: [...]}
```

desugar：计数资源累加 + `condition: "$resource >= n"` 门控 + 触发时扣 n / 清零（非消耗 1）。

**③ `accumulate`（窗口累计阈值）**：

```yaml
accumulate: {from: {event: "after_consume", resource: "sp", amount: "$event.amount"}, window: "self_turn", threshold: 3, then: [...]}
```

desugar：累计资源 + 喂入 hook + 窗口重置 hook（window 枚举：`none` / `self_turn` / `any_action` / `per_attack` / `per_action`）+ 门控。

**④ `tally`（事件量级累计池，不重置，供他处引用）**：

```yaml
tally: {on: "hp_loss($self)", add: "$event.amount", cap: "0.9 * $self.max_hp"}
```

> 落地自决策卡 #17（2026-08-18，trigger_limit 三档）、#19（2026-08-20，升级为统一框架——59 实例宏族收编；desugar 产物与手写三联件语义全等）。

### 4.13 攻击窗宏族（one_shot / window / 闩锁）

"本次攻击 / 下一次攻击"窗口语义的声明式写法（决策卡 #19 族 2，~27 实例）。现状两种手写组合各错一边（多段丢加成 / 非攻击行动误耗）——宏把消耗点钉死：

```yaml
# 一次性窗：武装点挂标，首次匹配命中后消耗
one_shot: {arm_on: "on_ultimate", consume_on: "next_attack"}            # 开大后下一次攻击
one_shot: {arm_on: "cast:skill", consume_on: "next_action_type:skill"}  # 施放战技后下一次战技

# 攻击窗作用域：窗口内生效（"本次攻击伤害提高"族）
window: "this_attack"

# 可重装填闩锁（用完可再装填）
one_shot: {rearm_on: "cast:ultimate", consume_on: "cast:skill"}
```

**边缘语义（钉死）**：窗口标记由 `on_action_start` 置位 / `on_after_action` 清除，**插入式行动不清除**（追加/反击不丢窗、不被误耗）。desugar：旗标资源（`max: 1`）+ 武装 hook + 消耗 hook + 门控——与 §4.12 共用计数器原语。

### 4.14 门控与时长锚点

**`active_when`（modifier 级激活条件，决策卡 #19 族 4）**：

```yaml
modifier:
  active_when: "$self.hp / $self.max_hp < 0.5"       # 条件存续期间生效
```

desugar：modifier 本体 + 由谓词自动推导的**双向 hook 挂摘对**（hp → `on_hp_decrease`/`on_hp_increase`；resource → `after_gain`/`after_consume`；modifier 存续 → `after_apply`/`after_remove`）——对称性由展开保证，不再人肉对齐。

**时长锚点（决策卡 #19 族 6）**：duration 扩展两个修饰轴——

```yaml
duration:
  value: 2
  tick_on: "$modifier.source"   # 非携带者回合计时（按施加者回合走字）

duration:
  until: "summon_turn_end"      # 事件到期（"state_exit(X)" / "owner_down" 同构）
```

desugar：抑制默认 tick + 锚点事件的 `adjust_duration(-1)` / `remove_modifier` hook（§4.11 adjust_duration 原子复用）。**补钉（决策卡 #20）**：`tick_on` 锚点 actor 离场时——挂靠立即停止走字（标记随 actor 销毁语义），不立即移除；需立即移除的由模板显式 `actor_exit` hook 表达。

**`scale_by` / `scale_stat`（决策卡 #19 族 3/10，计数与资源联动缩放）**：

```yaml
scale_by: {count: "target_debuffs", per: 0.20, cap: 5}        # 按目标侧计数阶梯缩放（替代 N 档手写）
scale_stat: {source: "$resource.x", rate: 0.08, cap: 80, live: true}   # 资源→属性实时联动（live 自动生成重算订阅 hook）
```

> 落地自决策卡 #19（2026-08-20）。

### 4.15 护盾实例与生存字段（运行时落地）

> 本节是**运行时模型**备注（已落地的 dataclass 口径），与 §4.1 的前瞻 Pydantic schema 并行阅读。

**护盾 = modifier（生命周期）+ `shield` 数值块（剩余值账本）**：护盾机制声明为一个普通 modifier（时长走 `tick_anchor`、驱散/净化按 §4.6 命中实例），`apply_modifier` 声明带 `shield` 块时引擎同步物化一个 `ShieldInstance`（挂在携带者护盾栈上，`modifier_id` 双向关联）：

```yaml
# 三月七族：护盾 modifier + shield 数值块（附带效果写在 modifier 本体，破盾即连带消失）
- effect_type: "apply_modifier"
  target: "ally_single"
  modifier:
    modifier_id: "MOD_MARCH_SHIELD"
    name: "三月七护盾"
    modifier_type: "buff"
    duration: 3
    stat_effects: {"taunt": 500}       # 附带效果（嘲讽值提升）——破盾连带移除
  shield:
    scaling: {"def": 0.48}             # 属性×倍率（def/hp/atk，读施加者有效面板）
    flat: 640                          # 固定值
```

- **护盾值** = (属性×倍率 + 固定值) × (1 + 施加者 Shield_Bonus%)（mechanics `01_base_stats.md` §1.3 / `02_damage_formula.md` §2.13）
- **多盾不叠加**：有效护盾 = 所有实例中最高剩余值；受击时**所有实例同时吸收全额伤害**（各扣 min(自身剩余, 伤害)）；本体承伤 = max(0, 伤害 − 最高剩余)（溢出扣 HP）
- **后台破盾级联**：实例归零 → 发 `shield_broken` → 关联 modifier 连带摘除（`after_remove_modifier` 带 `reason: "shield_broken"`）；反向同样成立——modifier 被摘除（过期/驱散/净化），其实例一并移除
- **真伤同走护盾层**（`02_damage_formula.md` §2.13：护盾非乘区，是乘区结算后的吸收层）；DoT 跳伤同走
- 发射点：`shield_absorbed`（逐实例）/ `shield_broken`，登记见 `23_event_hook_system.md` §23.4；同 modifier 重复施加 = 实例整换为新值（与 `stack_mode: "refresh"` 同口径）

**生存三字段（受击链末段四层分工，引擎 `_check_death` 为唯一结算点）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hp_lock` | bool | **锁血**：HP 不会降至 1 以下（伤害照算、致命留 1 血；区别于免死 `before_take_damage` cancel 与复活回拉） |
| `revive_percent` | float | **复活**：>0 时携带者 HP 归零消费本件，以生命上限×该比例回拉（发 `on_revive`，见 §23.4） |
| `moon_cocoon` | bool | **月茧**（mechanics `11_special_mechanics.md` §11.1）：携带者受致命伤进入月茧态（留 1 血、消耗授予件）。次数为**战斗级状态**（`BattleState.moon_cocoon_used`，owner 实战确认 2026-08-22）：**全队每场共用 1 次**——同一伤害事件（一次行动的多目标/多段结算）内多人同时致死则一次全部进茧；此后（含茧中人自己）再受致命击直接真死（茧中不再保 1 血）。茧中人下次回合开始前受治疗或获得护盾则解除存活，否则到期真死 |

> 落地自工作件"受击结算链闭环"（2026-08-22）：护盾栈/生存三字段/发射点登记。

---
