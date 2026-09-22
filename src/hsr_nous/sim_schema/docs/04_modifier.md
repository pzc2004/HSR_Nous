## 4. Buff / Modifier 定义

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Buff 是核心机制，所有持续效果都用它表达。

> **三语义分解（概念模型）**：一个 modifier 的本体只有两半——**效果**（谁吃、吃什么）与**持续时间的演化规则**（计时 hook）；"挂在谁身上"不是它的属性，只是默认值。三层语义各自独立：
>
> - **效果语义**（`effect_scope`：谁吃）——self（默认，携带者）/ team（光环：挂源辐射全队，阮梅弦外音/缇宝族）
> - **计时语义**（`tick_anchor`：怎么减）——owner_turn_end（默认，携带者回合结束）/ owner_turn_start（阮梅"每回合开始减 1"族）/ on_action（行动次数型）/ source_turn_end（施加者回合结束）/ source_turn_start（施加者回合开始——携带者非施加者但按施加者回合走字族，长夜月 141302 忆灵暴伤光环挂 Evey 按长夜月回合开始 -1；与 source_turn_end 同扫场通道，2026-09-07 落地）
> - **管理语义**（挂载点）——驱散/净化/免疫/查询**按人**发起的定位句柄（"驱散谁的""净化谁的"）；结界（zone）= 挂载点放在**战斗状态**上而非角色身上（罗刹"白花盛放"、姬子•启行"拓星视界"、白厄"时墟铁墓"——见 `19_zone_system.md`）
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

> **引擎运行时 DoT 载体（`modifier_type: "dot"` + `dot_*` 字段，B27#3 收官全乘区接链）**：
> 上例的「标记 debuff + on_turn_start hook 结算」是模板侧形态；引擎另有一条**运行时载体**
> 形态——`modifier_type: "dot"` 的 modifier 由回合开始结算链（A 类）统一跳伤，是击破裂伤/
> 灼烧/触电/风化当前唯一在跑形态。字段：
>
> | 字段 | 含义 |
> |------|------|
> | `dot_element` | 跳伤属性。**路由**：击破裂伤（engine 击破链建件，id 带 `BRK_DOT_` 前缀）且 physical 走裂伤特判（bleed_base_multi 基数区，`01_formula.md` §1.4）；其余（含角色物理 DoT——天赋裂伤/Zone 追加族）走常规 dot 链（`route["dot"]`） |
> | `dot_ratio` | 跳伤倍率，**两态互斥**：① 静态数值（击破裂伤=1.0，rulebook `break_effects.*.dot_ratio/bleed_ratio`；**叠层 DoT=每层倍率**——跳伤基数 ×跳伤时刻 `max(1, stacks)` 现值，桑博 1108 风化族；单档件 stacks 恒 1 无观察差）——字符串值走 param() 编译期取档，残留表达式=hook `apply_modifier` 现场求值烘焙族（星魂闩读数——桂乃芬 S2「param×(1+0.4×res__s2_burn)」/桑博 E6「param+0.15×marker」——施加时 `_hook_amount` 烘焙成全目标同值定值；action `apply_modifiers` 通道无烘焙，残留表达式编译期炸）；② **跳伤时求值表达式**（引用 `$snapshot`/`$modifier` 命名空间——编译期分类并预编译存件，见下行 `dot_ratio_expr`）：跳伤时刻以持有者为语境现场求值，**表达式值即当跳基数**（不再 ×快照 atk/×stacks——层数语义由表达式自含）。首实例：黑天鹅 1307 奥迹「(base+inc×($modifier.stacks−1))×$snapshot.atk」（base+increment 仿射叠层）/海瑟音 1410 裂伤「min(20%×$self.max_hp, 25%×$snapshot.atk)」（HP 帽形） |
> | `dot_ratio_expr` | `dot_ratio` 跳伤时求值态的运行时载体（`PreparedExpression`，`hit_condition_expr` 同先例——模板写 `dot_ratio` 表达式字符串，编译期分类后预编译存此字段，不直接声明）：跳伤时刻以**持有者为语境**求值——`$self`=持有者现值（敌方：hp/energy/max_hp/atk/def_/spd 等有效面板，`_SELF_NS_FIELDS` 白名单）+ `$snapshot`=施加者攻击侧快照包（dot_snapshot_ctx 键 + atk=dot_source_atk）+ `$modifier`=modifier 自身（stacks/duration/max_stack/modifier_id/dot_element）。语境闭合（仅内建数学函数 min/max/abs/round/clamp/sum——宿主函数不注入），编译闸 `_check_dot_tick_expr` 对语境外引用/白名单外字段/非内建函数调用编译期炸 |
> | `dot_base_chance` | 施加基础概率（缺省 1.0）——**期望值建模层**：施加本身确定性恒挂，概率以期望权重乘进跳伤命中区快照 `ehr_multi = min(1, dot_base_chance×(1+EHR)×(1-敌效果抵抗+穿透))`（与 optimizer standardDot `dotBaseChance` 同口径；01_formula dot_damage 注）。字符串值同 `dot_ratio` ①通道（施加时烘焙，无跳伤时求值族——施加时刻快照输入） |
> | `dot_source_atk` | 施加者攻击快照（跳伤基数；施加时刻**有效面板**；跳伤时求值件的 `$snapshot.atk` 读此） |
> | `dot_snapshot_ctx` | 攻击侧快照包（`Dict[str, float]`——**施加时引擎算好存件**，模板/测试不手填）：ability_multiplier（静态 dot_ratio 件；跳伤时求值件不烤此槽）/ dmg_boost_multi / ind_dmg_boost_multi / final_dmg_multi / weaken_multi / ehr_multi / be_multi + 防御/抗性区的攻击侧输入（source_level/def_pen/res_pen）；跳伤时只补目标侧链乘（mechanics 02 §2.12 快照切分）。refresh 重挂不刷新快照（首次施加源存件——同 id 多源施加（桂乃芬战技 1.0/High Poles 0.8）按首次源口径在案） |
>
> 模板经 hook `apply_modifier` 声明 `modifier_type: "dot"` + `dot_element`/`dot_ratio` 时，
> `dot_source_atk`/`dot_snapshot_ctx` 由引擎在施加时刻从施加者有效面板结算填入（source 缺失
> = 无快照源，运行期报错指路）；空 ctx 的裸件（手建 modifier 直调 pipeline）按攻击侧全中性兜底。
> 跳伤公式链：击破裂伤（`BRK_DOT_` 前缀 id）走 route["bleed"] → `bleed_dot_damage`，其余走 route["dot"] → `dot_damage`（角色物理 DoT——天赋裂伤/Zone 追加族——同常规链，不吃击破基数/BE 乘区）。
> 跳伤命中域：`on_hp_decrease` 发 `reason: "dot"` + `damage_type: dot_element`（桂乃芬 WoK
> 「本体火伤」按元素过滤 tick 的挂载点）；`action_type` 不携带（dot 非行动类别，`03_actor.md` §3.8）。

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
  - **伤害命中** `$event` 字段：`action_type` / `damage_type` / `target_broken` / `target_controlled` / `target`（本次命中目标 `ActorState`——按目标状态判定的宿主函数（`has_debuff`/`debuff_count`/`dot_count` 等，`has_modifier` 同解析通道）经 `$event.target` 读目标；由结算点统一注入，调用方 payload dict 不含此键）。命中域可用函数 = `22_syntax_reference.md` §22.4 白名单（宿主注入同 `_hook_functions` 集，`$self` 绑定携带者）
  - 计入 stat（按乘区分族，攻击侧/承伤侧携带者不同——逐区枚举即引擎 `_scoped_boost` accept 清单）：
    - 增伤区（攻击侧携带）：`dmg_*` / `all_dmg`（增伤族——刻律德菈 Peerage 类；按目标负面状态判定族——117 死水 2pc / 21001 晚安）
    - 穿透区（攻击侧携带）：`res_pen`（飞霄 E6 族）/ `def_pen`（**逐目标无视防御通道**——116 幽锁 4pc 按目标 DoT 数族，2026-09-16；直伤/击破/超击破/欢愉/DoT 跳伤全伤害路由同通道）
    - 暴击区（攻击侧携带）：`crit_rate` / `crit_dmg`（**目标条件暴击通道**——23007 雨下「≥3 负面暴击率」/23020 洗礼「按负面数暴伤」/117 死水 4pc 族，2026-09-16；仅直伤路由消费——DoT/击破不暴击天然无消费端）
    - 承伤区（**目标侧携带**——承伤件挂敌方）：`vulnerability` / `ind_vulnerability`（椒丘结界族；击破/超击破/欢愉/DoT 路由 action_type 喂路由 id `"break"` / `"super_break"` / `"elation_damage"` / `"dot"`）
    - 削韧区（攻击侧携带）：`break_efficiency_boost`（飞霄 E4 族）
  - **DoT 跳伤命中域**：`action_type` 喂 `"dot"` 路由 id；施加者的增伤/无视防御条件件按**跳伤时刻**目标状态现值判定（逐目标条件件不进施加时刻快照——`dot_snapshot_ctx` 只含无条件面板；21001「该效果对持续伤害也会生效」族）
  - **治疗命中** `$event` 字段：`target_hp_ratio` = 受疗者当前 HP / 有效生命上限（**治疗前**现场值——"为当前生命值 ≤N% 的我方目标提供治疗时治疗量提高"族，1409 大行迹「阴云莞尔」首实例）；计入 stat = `heal_bonus`（施放者侧 Outgoing Healing）
  - scoped 判定只扫**携带者自身持有**件——`effect_scope: team` 光环**不辐射** hit_condition 件（全队族双件各挂：阴云莞尔忆灵侧同 §4.16 暴风停歇 `stat_of($self.summoner_id, ...)` 先例）；求值失败静默按不计入（命中热循环不留 ⚠，与面板域条件光环 B8 口径分工）
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
| 阮•梅额外能力 | `false` | `true` | `true` | `false` |
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

> 部分永久状态（如火主"灼热意志"，buff 本体为 `800204 牵制盗垒`，开拓者•存护天赋）**不受回合结算影响**，持续到特定移除条件。

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

> **`grants_immune`（modifier 级授予免疫）**：修饰符字段——携带者免疫列表内类别的负面（apply 前硬拒，同 `debuff_immune` 通道发 `on_immune`）。**字面 kind 词表成员判定**（`"control"` 等，与 `new_kind = debuff_kind or control or modifier_type` 取值空间对齐），**不是表达式**（写 `"$mod.kind == 'debuff'"` 不生效——1207 驭空过堂勘正③病例）。**条件件（`enable_if`）的免疫随启用态开关**——未启用 = 免疫不在场（`pipeline.modifier_enabled` 统一判定；驭空「青镞」冷却闩族首实例，闩期间免疫关闭）。形态通道 `state_config.grants_immune`（140805 控制免疫族）经形态标记 modifier 并入同字段、同判定。

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
| `on_action` | 一切能力施放结算后（普攻/战技/**终结技同发**——B37 方案 A 收编 2026-09-10：官方英文三层措辞实锤 "uses an ability"=含终结技（1413101/1413102 在案）/"uses Skill"=仅战技（1313103）/"uses Skill and Ultimate"=明示双类（1409102），`on_action` 即 "uses an ability" 的发射点，"uses Skill" 仅战技族用 `action_type`/`action_id` 过滤表达；入口变身技与常态技同口径，`activate_ultimate` 免费激活同发。插入行动带 `insert: true` 标记；行动计数型 buff 的计时锚点 `tick_anchor: "on_action"` 同源——bus 契约已登记。payload：`actor` / `action_type` / `action_id`（2026-09 起携带——`trigger_action` 的 `$event.action_id` 动态复刻取数锚，奇袭战技复制族） / `target_type`（2026-09 起携带——"以敌方为目标的战技"族过滤锚，奇袭限定） / `target`（主目标 id） / `actor_type`；插入行动另带 `insert` / `tag`） | emit |
| `on_before_hit` | 造成伤害前 | waterfall |
| `on_after_hit` | 造成伤害后 | emit |
| `on_being_targeted` | 被选为目标时 | emit |
| `on_kill` | 击杀敌人时（payload：`source` 击杀者 / `target` 被击杀者 / `action_id` 致死行动 id——action 伤害与击破致死为行动 id，hook 伤害继承触发事件的行动 id，dot/流失等无行动来源为 `""`；"指定技能击杀"族过滤锚——遐蝶 1407102 死龙半"焰息致命全灭"支配 `enemies_alive() == 0` 全灭判定） | emit |
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
| `on_ultimate` | 终结技时（`on_action` 的终结技专属子集——B37 方案 A 起终结技两事件同发，序 = 先 `on_action` 后 `on_ultimate`；终结技专属监听保留不破。payload：`source`（施放者） / `action`（终结技 action id） / `target`（主目标 id）） | emit |

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

> **① 已接线（2026-09-06，B24 首糖）**：`trigger_limit` 挂接点 = **hook 顶层键**，desugar
> 为计数器四联件（资源注册 + 充满 hooks + 门控并入 condition + 消耗追加 `gain_resource`
> 负值）——VM 只见展开产物，`sim/compile/sugar.py`。计数器粒度 = **每 hook 声明一件**
> （同模板同事件多个 trigger_limit 各自独立计数，2026-09-07 钉——长夜月 141304 天赋
> "每目标每次受击限 1 次"双 hook 族是首个多 hook 实例；此前按（模板，事件）共享，单 hook
> 时代无碰撞）。v1 窗口档：`per_turn`（on_turn_start
> 重置）/ `per_wave` / `per_action`（on_action 口径）/ `per_battle: N` / `once_per_battle`
> + `reset_on`（须为 §23.4 契约事件）；`count` 与窗口档数值同义。v1 不收（写了大声炸指路）：
> `per_attack`（与 per_action 语义差未钉）/ `per_instance` / `per_target` / `cooldown_turns` /
> on_battle_start 挂钩（初始充满与同事件快照时序边）/ 非模板·星魂通道（召唤物/光锥/套装/
> 秘技 hooks——资源注册通道未接）。②③④ 与 §4.13/§4.14 糖键仍未接线（炸得认得）。

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

> **落地注记（2026-09-07）**：`active_when` 糖**仍未接线**（写了编译期炸指路）。条件生效/失效/变档需求已由 **`enable_if` 门控 + `stat_exprs` 现场求值**两个**原语**字段收编（§4.16）——语义与"双向 hook 挂摘对"不同（门控非挂摘，件仍在挂载），糖将来若接线应指向该原语。

**时长锚点（决策卡 #19 族 6）**：duration 扩展两个修饰轴——

```yaml
duration:
  value: 2
  tick_on: "$modifier.source"   # 非携带者回合计时（按施加者回合走字）

duration:
  until: "summon_turn_end"      # 事件到期（"state_exit(X)" / "owner_down" 同构）
```

desugar：抑制默认 tick + 锚点事件的 `adjust_duration(-1)` / `remove_modifier` hook（§4.11 adjust_duration 原子复用）。**补钉（决策卡 #20）**：`tick_on` 锚点 actor 离场时——挂靠立即停止走字（标记随 actor 销毁语义），不立即移除；需立即移除的由模板显式 `actor_exit` hook 表达——**例外（2026-09-17）**：「施加者自身无法战斗时立即解除」族不能写自身 `actor_exit` hook（alive 闸使「自己听自己」结构性不触发，B27#10），走 modifier `remove_on_source_death` 生命周期字段（§4.15）。

> **落地注记（2026-08-24）**：`{value, tick_on}` 形态**已落地**——编译期校验（duration dict 未知键 diff + `tick_on` 词表，13_validator 闸表），运行期解析为 `duration=value` + `tick_anchor` 扩展值 `source_turn_end`（锚原语复用而非 hook desugar，语义同构：施加者回合结束时其施加的该锚 modifier 全场走字；施加者离场后无回合、自然停走——补钉语义由构造满足）。`until` 事件到期形态**未落地**：写了编译期炸指路，不静默吞。
>
> **落地注记（2026-09-07）**：`tick_anchor` 扩展值 `source_turn_start` **已落地**——`source_turn_end` 的开始侧对称锚（施加者回合**开始**时其施加的该锚 modifier 全场走字，补钉同构：施加者离场自然停走）。首个实例：长夜月 141302 忆灵暴伤光环（挂忆灵、官方原文"This duration decreases by 1 at the start of Evernight's every turn"）——owner_* 锚携带者=忆灵走字 pace 错（忆灵 160 vs 忆师 99），source_turn_end 在忆灵高频行动下窗口提前结束（可观察差异），现有四锚组合不出，收第五锚。

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

**`accumulate` / `cap`：具名累积池（"护盾量可以叠加，上限为…"族——丹恒•腾荒 141402/141403/141404/1414103 四源同池首实例，2026-09-09 落地）**

```yaml
  shield:
    scaling: {"atk": 0.1}
    flat: 200
    accumulate: "PERMANSON_SHIELD"     # 累积池名：同池实例跨件加算，合并为一个吸收单元
    cap:                               # 池封顶（授予时闸）：multiplier × 子块按 shield 公式求值
      multiplier: 3                    #   ——"上限为当前战技护盾量的 300%"（施加者当前有效面板）
      scaling: {"atk": 0.2}
      flat: 400
```

- **`accumulate: <池名>`**（缺省 = 独立实例，本节上段语义不变）：同池名实例**跨件加算**——池是吸收单元（有效值 = 成员剩余合计），受击时池作为一个整体吸收、成员按获得先后 FIFO 逐扣（归零各自发 `shield_broken` 级联）；**同 modifier 重复授予 = 旧剩余并入本件新实例**（非整换——"重复获得可叠加"）；吸收单元推广后，上段"多盾不叠加"的取最高在**单元**间进行（独立实例各自一单元 / 每池一单元），溢出口径不变
- **`cap`**（仅配 `accumulate`，单写编译期炸）：池**动态封顶** = `multiplier` ×（cap 子块 `scaling`/`flat` 走 rulebook `shield` 公式、按**施加者当前有效面板**求值——"当前战技护盾量"随面板浮动，含 shield_bonus 与条件件同口径）；**授予时闸**：每次入池后池合计超出帽沿的部分截断留痕（同 modifier 并入先算、跨件余额为他人腾出），战中面板回落**不回溯**已入池值
- 池成员的时长/驱散/净化生命周期仍各随关联 modifier（逐件 3t 走字互不影响）；池名是模板内自由命名空间，跨模板组合按各自模板池名互不相干

**生存三字段（受击链末段四层分工，引擎 `_check_death` 为唯一结算点）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `hp_lock` | bool | **锁血**：HP 不会降至 1 以下（伤害照算、致命留 1 血；区别于免死 `before_take_damage` cancel 与复活回拉） |
| `revive_percent` | float | **复活**：>0 时携带者 HP 归零消费本件，以生命上限×该比例回拉（发 `on_revive`，见 §23.4） |
| `moon_cocoon` | bool | **月茧**（mechanics `11_special_mechanics.md` §11.1）：携带者受致命伤进入月茧态（留 1 血、消耗授予件）。次数为**战斗级状态**（`BattleState.moon_cocoon_used`，owner 实战确认 2026-08-22）：**全队每场共用 1 次**——同一伤害事件（一次行动的多目标/多段结算）内多人同时致死则一次全部进茧；此后（含茧中人自己）再受致命击直接真死（茧中不再保 1 血）。茧中人下次回合开始前受治疗或获得护盾则解除存活，否则到期真死 |

**生命周期字段（施加者死亡联动——「陷入无法战斗状态时 X 效果也会被解除」族，2026-09-17 落地）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `remove_on_source_death` | bool | **施加者**（`source_id` 记账对象）**真死定论**时引擎全场摘除本件（`_check_death` 单漏斗：`alive=False` 后、`actor_exit` 发射前扫全场——死后清理监听者读到摘除后终态；摘除走 `_remove_modifier` 常轨，`after_remove_modifier` 带 `reason: "source_death"`）。alive 闸使「自己听自己 `actor_exit`」hook 结构性不触发（B27#10），本字段是引擎层统一通道；dismiss/放逐不触发（只认真死定论）。星期日 1313 蒙福者（BEATIFIED）首实例 |

**资源上限覆写两字段（`16_custom_resources.md` §16.12——获得统一入口 `_gain_resource` 唯一 clamp 点消费）**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_resource` | str | 覆写哪个自定义资源的 `max`（与 `max_override` 成对，单写编译期炸） |
| `max_override` | float | 覆写后的上限值（>0）。**有效上限 = max（基础 `max`，全部生效覆写）**——v1 只抬不压（压低实例未到达）；时序 = 持有覆写件期间生效，**到期不回收已超限值**（下次获得按有效上限截断自然回落）。昔涟 1141517「献予生死之诗」新蕊溢出至 200% 首实例（2026-09-10 收编） |

> 落地自工作件"受击结算链闭环"（2026-08-22）：护盾栈/生存三字段/发射点登记。

---

### 4.16 条件光环：`enable_if` 门控 + `stat_exprs` 现场求值

> **落地注记（2026-09-07）**：本节为**已落地原语**（非糖）。生效条件随战况变化的
> modifier（速度阈值档 / HP 比例档 / 队伍编成档——风堇「暴风停歇」、遐蝶「倒置的火炬」、
> 昔涟 1415103「三相的因果」、长夜月 1413103「天亮了，雨落了」族）由此收编；§4.14
> `active_when` 糖维持未接线（将来接线应指向本原语）。

```yaml
modifier:
  modifier_id: "HYACINE_STORM_CALM"
  duration: 0                       # 常驻行迹件
  dispellable: false
  enable_if: "$self.spd > 200"      # 生效条件（effect 层表达式）：不成立时数值不计入面板
  stat_effects: {"hp_pct": 0.2}     # 条件成立时的静态部分（与无案件同池）
  stat_exprs:                        # 条件成立时的现场求值部分（档位随条件源变档）
    heal_bonus: "min(max($self.spd - 200, 0), 200) * 0.01"
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `enable_if` | expression | `None`（恒生效） | 生效条件：不成立时该件的 stat_effects / scaling_effects / override_effects / stat_exprs **全部不计入面板** |
| `stat_exprs` | mapping[stat → expression] | `{}` | 现场求值数值槽：每次面板求值现场算（超速度档治疗量/抗性穿透族——条件源战中变化立即反映）；通过门控后与 stat_effects 并入同一加算池（pct 族同走白值口径） |

**语义钉**：

- **门控非挂摘**：条件不成立只是数值不计——件**仍在挂载**（`has_modifier` 可见、驱散/净化/走字/叠层照常）。无"回收"动作，条件翻回成立即恢复；与挂/摘语义严格区分
- **重估时机 = 面板读取即重估**（懒求值）：伤害公式、行动值插入、转化读取等一切面板消费点自动覆盖，无快照、无 stale。唯一推式消费点 = 调度器速度同步——HP 变化事件（`on_hp_decrease`/`on_hp_increase`）后若场上存在条件件则全队速度重同步（modifier 挂/摘本有 `_sync_speed` 通道；倒置的火炬"HP≥50% 速度+40%"族靠此上路）
- **条件域面板 = 无条件件面板**：`enable_if` / `stat_exprs` 语境的一切面板读取（`$self.spd`、`stat_of(...)`）读到的**不含任何条件件的贡献**——构造上无环（A 件条件读不到 B 条件件的产出，互相不致递归）；条件件彼此不可互相观察，"条件件产出喂另一条件件"的设计不支持
- **`$self` = 携带者**：光环件（`effect_scope: team`）辐射到他人面板时，条件仍读**携带者（源）**的面板而非目标面板（昔涟 1415103：队友吃到的增伤按昔涟速度判定）；忆灵侧条件件读忆师面板用 `stat_of($self.summoner_id, 'spd')`（小伊卡/德谬歌件）
- **求值失败按不生效 + ⚠ 日志**（B8 hook 条件同口径；语法错由编译期预编译闸拦截）
- 可用函数 = effect 层白名单；本域宿主实现含 `count_team(path=...)`（队伍编成计数）与 `stat_of(target, stat)`（跨 actor 面板读）——登记见 `22_syntax_reference.md` §22.4

> 落地自引擎缺口收口"条件光环重估通道"（2026-09-07）：四在案件收编——1409 暴风停歇 /
> 1407 倒置的火炬（速度半）/ 1415 1415103 / 1413 天亮了变档 + 1415 1415102 进战追忆档。
