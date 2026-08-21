## 3. 参战单位 (Actor)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Actor 分为角色、怪物和召唤物，共用同一套结构。

```yaml
actor:
  actor_id: "1001"
  name: "三月七"
  actor_type: "character"    # character | monster | summon（monster 即敌人/enemy，schema 枚举值保留 monster）
  path: "preservation"
  damage_type: "ice"
  level: 80

  # ========== 基础属性（Layer 1）==========
  base_stats:
    hp: 1047
    max_hp: 1047
    atk: 564
    def: 485
    spd: 101

    crit_rate: 0.05
    crit_dmg: 0.50

    break_effect: 0.0
    break_efficiency_boost: 0.0   # 击破效率提升
    weakness_break_efficiency_boost: 0.0  # 弱点击破效率提升
    fixed_toughness_dmg: 0.0      # 固定削韧值（不受效率加成影响）

    effect_hit: 0.0
    effect_res: 0.0
    effect_res_pen: 0.0          # 效果抗性穿透（作用于目标 effect_res）
    type_res: 0.0                # 类型抵抗，按 debuff_kind 取（当前仅控制类有实例，如 boss 控制类类型抵抗；dot 类默认为 0，预留"持续伤害抵抗"落点）

    def_pen: 0.0                 # 防御穿透 / 防御降低汇总值
    res_pen: 0.0                 # 抗性穿透

    vulnerability: 0.0           # 易伤
    ind_vulnerability: 0.0       # 独立易伤
    final_dmg_bonus: 0.0         # 最终伤害加成
    dmg_reduction: 0.0           # 减伤（已汇总为乘积结果）
    weaken: 0.0                  # 虚弱

    max_energy: 120
    energy: 0
    energy_regen: 1.0

    heal_bonus: 0.0
    shield_bonus: 0.0
    incoming_heal: 0.0            # 受治疗加成

    # 增伤相关（公式层会解析为标量）
    # DSL/Modifier 层统一用 all_dmg_bonus / elemental_dmg_bonus / type_dmg_bonus / ind_dmg_bonus 作为 stat
    # dmg_bonus 字典是适配层/内部存储，最终汇总到上述标量字段
    all_dmg_bonus: 0.0            # 通用增伤（对应 dmg_bonus.all）
    elemental_dmg_bonus: 0.0      # 当前伤害属性对应的属性增伤（从 dmg_bonus[element] 解析）
    type_dmg_bonus: 0.0           # 当前 action_type 对应的技能类型增伤（从 dmg_bonus_by_type 解析）
    ind_dmg_bonus: 0.0            # 独立增伤

    dmg_bonus:
      all: 0.0
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    resistance:
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    weakness: ["ice", "wind"]

    taunt: 150

    # 欢愉度（StatBlock 面板属性，不是 custom_resource）
    elation: 0.0

    # 韧性 = 条列表（按序扣除，见 §3.10）；max_toughness / toughness 保留为主条（首条）的兼容别名
    max_toughness: 100
    toughness: 100
    toughness_bars: []            # 追加韧性条（add_toughness_bar 挂上，见 §3.10）；空 = 单条模型
    broken: false                 # 末条韧性归零时为 true（见 §3.10）

    dmg_bonus_by_type:
      basic: 0.0
      skill: 0.0
      ultimate: 0.0
      follow_up: 0.0
      dot: 0.0
      elation: 0.0
      joint: 0.0                  # 连携攻击（一等伤害类别标签，见 05_effects.md joint_attack）

  elation_number: 0             # 欢愉编号（Actor 级整型字段，不在 base_stats 内）

  # ========== 自定义资源容器 ==========
  custom_resources:
    punchline:
      max: 999999
      owner: "actor"
      scope: "team"

  # ========== 形态状态机 ==========
  actor_state: "normal"
  state_config: null

  # ========== 秘技 ==========
  techniques:
    - technique_id: "march_7th_technique"
      actor_id: "1001"
      point_cost: 1
      forces_battle_entry: true
      effects:
        - effect_type: "apply_modifier"
          target: "enemy_single"
          modifier:
            modifier_id: "frozen"
            duration: 1

  # ========== 队伍级修正 ==========
  team_modifiers:
    technique_point_initial_bonus: 0
    technique_point_max_bonus: 0

  # ========== 模板内嵌查表与变量绑定 ==========
  lookup_tables:
    base_hp_by_level: [1200, 1300, 1400]
    basic_scaling:    [0.50, 0.55, 0.60]
    ultimate_scaling: [2.00, 2.10, 2.20]

  variable_bindings:
    - self.base_hp         = lookup_table("base_hp_by_level", index=$build.level - 1)
    - self.basic_scaling   = lookup_table("basic_scaling",    index=$build.skill_levels.basic - 1)
    - self.ultimate_scaling = lookup_table("ultimate_scaling", index=$build.skill_levels.ultimate - 1)

  # ========== 技能 ==========
  actions:
    - action_id: "1001_basic"
      name: "寒冰之箭"
      action_type: "basic"
      target_type: "enemy_single"
      damage_type: "ice"
      energy_gain: 20
      skill_point_gain: 1
      toughness_dmg: 10
      effects:
        - trigger: "on_cast"
          target: "primary_target"
          effect_type: "deal_damage"
          formula: "damage"
          amount: "$self.atk * $self.basic_scaling"
        # 回能由 action 级 energy_gain 字段统一结算（勿再叠加 gain_energy effect，否则翻倍）

    - action_id: "1001_skill"
      name: "可爱即是正义"
      action_type: "skill"
      target_type: "ally_single"
      skill_point_cost: 1
      toughness_dmg: 20
      effects:
        - trigger: "on_cast"
          target: "primary_target"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_SHIELD"
          duration: 3

    - action_id: "1001_ultimate"
      name: "冰刻剑雨之时"
      action_type: "ultimate"
      target_type: "enemy_aoe"
      energy_cost: 120
      toughness_dmg: 30
      effects:
        - trigger: "on_cast"
          target: "all_enemies"
          effect_type: "deal_damage"
          formula: "damage"
          amount: "$self.atk * $self.ultimate_scaling"
        - trigger: "on_cast"
          target: "random_enemy"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_FREEZE"
          duration: 1
          chance: 0.5

  # ========== 行迹（被动能力）==========
  traces:
    - trace_id: "T_1001_1"
      name: "公主殿下"
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_TRACE_CRIT"
          duration: 0

  # ========== 星魂 ==========
  # 注意：这是模板内星魂定义列表（全部可能星魂的元数据）。
  #       build.yaml 中的 `eidolon`（单数）是玩家解锁数量，运行时按序号启用前 N 个。
  eidolons:
    - eidolon_id: "E_1001_1"
      name: "记忆中的你"
      effects:
        - trigger: "after_apply_modifier"
          condition: "$event.modifier_type == 'shield' && $event.modifier_id == \"MOD_1001_SHIELD\""
          target: "$event.target"
          effect_type: "heal"
          formula: "heal"
          amount: "$self.max_hp * 0.3"

  # ========== 光锥 ==========
  light_cone:
    light_cone_id: "20001"
    name: "余生的第一天"
    superimposition: 1
    effects:
      - trigger: "on_battle_start"
        target: "self"
        effect_type: "apply_modifier"
        modifier_id: "MOD_LC_20001_DEF"
        duration: 0
      - trigger: "on_battle_start"
        target: "all_allies"
        effect_type: "apply_modifier"
        modifier_id: "MOD_LC_20001_RES"
        duration: 0

  # ========== 遗器 ==========
  # 注意：以下展示的是完整 relic 实例（含主/副词条数值）。
  #       在 build.yaml 中玩家只声明 `main: "hp"` 和副词条强化次数，具体数值由模板/计算决定。
  relics:
    - relic_id: "R_101_1"
      set_id: "S_101"
      slot: "head"
      main_stat: {stat: "hp", value: 705.0}
      sub_stats:
        - {stat: "atk", value: 42.34}        # 两次高档（21.17×2）
        - {stat: "spd", value: 4.0}          # 两次低档（2.0×2）
    - relic_id: "R_101_2"
      set_id: "S_101"
      slot: "hand"
      main_stat: {stat: "atk", value: 352.0}
      sub_stats:
        - {stat: "crit_rate", value: 0.02916}  # 中档一次
        - {stat: "crit_dmg", value: 0.05832}   # 中档一次

  relic_set_effects:
    - set_id: "S_101"
      pieces: 4
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_SET_101_4P"
          duration: 0
```

### 3.1 新增字段说明

| 字段 | 类型 | 说明 | 详见 |
|------|------|------|------|
| `custom_resources` | `Dict[str, ResourceBlock]` | 战斗内可累积/消耗的资源 | `16_custom_resources.md` |
| `actor_state` | `ActorState` | 当前形态 | `17_actor_state.md` |
| `state_config` | `StateConfig?` | 当前形态配置 | `17_actor_state.md` |
| `techniques` | `List[TechniqueDef]` | 战前可施放的秘技 | `18_technique_system.md` |
| `team_modifiers` | `dict` | 角色在队时给全队加的修正（如秘技点上限） | `18_technique_system.md` |
| `lookup_tables` | `Dict[str, List[float]]` | 模板内嵌数值表 | `15_data_separation.md` |
| `variable_bindings` | `List[str]` | 按 build 查表/覆盖变量 | `15_data_separation.md` |
| `owner_id` | `str?` | 召唤者 actor_id（仅 `actor_type: "summon"`） | `12_summon.md` |
| `behavior` | `SummonBehavior?` | 召唤物行为模式（仅 `actor_type: "summon"`） | `12_summon.md` |
| `special_mechanics` | `List[MechanicDef]?` | 召唤物/忆灵特有机制描述 | `12_summon.md` |
| `relic_set_effects` | `List[Effect]` | 已激活遗器套装效果 | `06_relics.md` |
| `groups` | `List[str]` | 分组标签（开放命名空间：命途自动映射 `path:<name>`；阵营/官方分组如 `faction:xxx`） | 决策卡 #17 |
| `position` | `int` | 编队位（1-4，首位为 1）；敌人同样携带战场位置（相邻 = 位置差 ≤1，`actor_enter` payload 同字段）；**新入场/召唤物分配规则（决策卡 #20 钉死）：取当前空位最小编号，无空位取 max+1** | 决策卡 #17/#18/#20 |

### 3.2 增伤乘区拆分

```
dmg_boost_multi = 1 + all_dmg_bonus + elemental_dmg_bonus + type_dmg_bonus
```

`type_dmg_bonus` 根据当前伤害的**类别标签集合**从 `dmg_bonus_by_type` 取值：主类别 = `action_type`，附加标签如 `joint`（连携攻击）——命中各档**求和**（同属增伤乘区）。例：忆师普攻触发的连携伤害带 `[basic, joint]` 两标签，`basic` 档与 `joint` 档加成同时生效。`action_type` 可被 `modify_event` 改写（见 `23_event_hook_system.md` §23.6），改写后按新主类别取值。

### 3.3 属性计算公式

```
白值 = 角色基础值 + 光锥基础值
最终值 = 白值 × (1 + 百分比加成%) + 固定值加成
```

详见 `04_modifier.md` §4.10 两层属性模型。

### 3.4 弱点/抗性关系

- 弱点属性默认 **0%** 抗性
- 非弱点属性默认 **20%** 抗性
- 两者是**独立字段**

#### 削韧闸门：`toughness_scope`（action 级字段）

每个攻击的削韧资格由 `toughness_scope` 显式声明（默认 `"own_element"`，零迁移成本）：

| 取值 | 语义 |
|------|------|
| `"own_element"`（默认） | 仅当攻击属性 ∈ 目标弱点列表时 `toughness_dmg` 生效，否则削韧 = 0 |
| `"all"` | 无视弱点——任意属性都可削韧（黄泉终结技/秘技、黄泉 E6 类） |
| `[element, ...]` | 指定可削的属性列表（攻击属性 ∈ 列表即可削——覆盖银狼植入后跨属性等场景） |

**modifier 携带的动态削韧闸**（决策卡 #18）：modifier 可携带 `toughness_scope` / `toughness_dmg_ratio` 字段——运行时给**他人攻击**开闸/折扣（忘归人狐祈"无对应弱点也可削韧、削韧量 ×50%"）；跨源互斥走 `singleton_group`（§4.11）。action 级静态字段与 modifier 级动态字段并存：静态是技能固有属性，动态是 buff 授予属性。**静动合成规则（决策卡 #20 钉死）**：scope 取**并集**（静态 ∪ 全部动态来源），ratio 动态来源唯一（`singleton_group` 保证，多源同组替换）。

- 闸门只决定**能不能削**；削多少仍走 `01_formula.md` §1.5/§1.11 的削韧公式（`toughness_dmg` × 效率 + `fixed_toughness_dmg`），含固定削韧值一并受闸门约束
- 韧性保护（锁定弱点，见 `04_break_system.md` §4.1）与超韧性（§4.6）优先级高于闸门——锁定时任何 scope 都不可削

### 3.5 插入行动与 buff 回合

插入行动（追加攻击、终结技、额外回合）**不消耗 buff 回合数**（例外：`grant_extra_turn` 的 `after_action` 模式视同普通回合、正常消耗——见 `05_effects.md`）。

### 3.6 战技点特殊案例

| 案例 | YAML 表达 |
|------|----------|
| 技能消耗 0 点 | `skill_point_cost: 0` |
| 技能消耗 2 点 | `skill_point_cost: 2` |
| 强化普攻不回复 | `skill_point_gain: 0` |
| 终结技回复战技点 | `skill_point_gain: 1` |

### 3.7 追加攻击分类

- 描述中含“追加攻击”或“反击” → `action_type: "follow_up"`
- 终结技、希儿再现等**不是**追加攻击
- 追加攻击可触发其他追加攻击，需检查递归深度限制

### 3.8 action_type 枚举

| 取值 | 说明 |
|------|------|
| `basic` | 普攻 |
| `skill` | 战技 |
| `ultimate` | 终结技 |
| `follow_up` | 追加攻击 / 反击 |
| `memosprite_skill` | 忆灵技能（召唤物行动） |
| `assist` | 助战技（不占本人回合、带次数额度，见下） |

`dot` 触发、`break` 击破效果触发等不属于 `action_type`，它们通过总线事件表达（`on_dot_retrigger` 见 `23_event_hook_system.md` §23.4、`on_break` 见 `04_modifier.md` §4.8）。

**附加标签（tags）**：伤害包除主类别（`action_type`）外可携带附加标签集合 `tags`——已登记标签：`joint`（连携攻击，见 `05_effects.md` joint_attack）、`additional`（附加伤害——**不吃类型限定增伤、不再触发命中类监听**，决策卡 #19）；`dmg_bonus_by_type` 增伤按标签集合命中各档求和（§3.2），`hit_condition` 可写 `'joint' in $event.tags` 选中（`04_modifier.md` §4.2）。

**助战技（assist）**：不占本人回合的行动类别——发动时插入执行，不消耗发动者的回合（与追加攻击同属插入式行动）；**次数额度用 `custom_resources` 表达**（次数 = 资源），每次发动消耗 1，额度耗尽即不可发动（policy 只选不越权：资源门槛不满足的行动不进合法行动集）。

```yaml
# 姬子：助战技——额度 3 次，发动耗 1，耗尽即止
custom_resources:
  himeko_assist_charge:
    max: 3                      # 助战技次数额度

actions:
  - action_id: "himeko_assist"
    name: "助战技"
    action_type: "assist"       # 不占本人回合
    target_type: "enemy_aoe"
    damage_type: "fire"
    effects:
      - trigger: "on_cast"
        target: "self"
        effect_type: "consume_resource"
        resource_id: "himeko_assist_charge"
        amount: 1
      - trigger: "on_cast"
        target: "all_enemies"
        effect_type: "deal_damage"
        formula: "damage"
        damage_type: "fire"
        amount: "$self.atk * 1.2"
```

> 助战技的归因改写（"视为姬子施放战技"）走 `modify_event`，见 `23_event_hook_system.md` §23.6。

> 落地自决策卡 #10（2026-08-14）

### 3.9 关于 `elation`

`elation`（欢愉度）是 **StatBlock 面板属性**，参与欢愉伤害公式（见 `01_formula.md`、`21_elation.md`），**不是** `custom_resources` 中的资源。

### 3.10 韧性条列表

韧性从单值升级为**条列表**：主条（`max_toughness` / `toughness` 兼容别名）+ `toughness_bars` 追加条。规则：

- **按序扣除**：先扣主条，归零后按加入顺序扣追加条；前条未归零不流向后条
- **每条击破可观测**：每条归零经总线发射 `on_break`，payload 带 `bar_index`（主条 = 0，追加条按序递增）——二次击破 / 虚韧性击破用普通触发器 + `condition` 过滤（如 `$event.bar_index == 1`），不加事件人头税
- **弱点击破状态**：末条击破才进入（多层韧性规则，见 `../../../../docs/mechanics/04_break_system.md` §4.5）；带 `exo: true` 的条击破同样触发弱点击破、且可被任意属性削韧（超韧性规则，同文件 §4.6）
- **追加 / 移除**：新条由 `add_toughness_bar` effect 挂上（见 `05_effects.md`）；modifier 挂的条随 modifier 移除/过期一并移除
- `toughness_bars` 为空 ⇔ 旧单值模型，零迁移成本

```yaml
# 多层韧性敌人（两条）：主条 + 追加条
base_stats:
  max_toughness: 100
  toughness: 100
  toughness_bars:
    - bar_id: "layer_2"
      max: 60
      current: 60
```

> 落地自决策卡 #14（2026-08-14）

### 3.11 回合四段模型与额外回合两类型

**回合四段模型**（行动序视角；buff 结算视角的四阶段见 `04_modifier.md` §4.4）：

1. **回合开始**：A 类结算（DOT / 控制类在此结算）
2. **行动**：判定B，执行所选行动
3. **行动后窗口**：行动完成、回合结束结算之前的**合法插入点**——此时施放终结技 / 插入行动仍吃"本回合"效果（白厄天赋触发条件正落于此）
4. **回合结束**：B 类结算，AV 推进（重置满条继续排队）

**额外回合两类型**：

| 类型 | 回合事件 | 回合数 | 波次开始 | 实例 |
|------|---------|--------|---------|------|
| 正常回合类 | 有回合开始/结束事件（`on_turn_start` / `on_turn_end` / `on_extra_turn` 照常发射） | 视 `queue_mode`（见 `05_effects.md` grant_extra_turn） | 行动值随波次重置 | 希儿再现、终结技后额外回合 |
| 倒计时类 | **无**回合开始/结束事件（`on_extra_turn` 亦不发射） | **不消耗回合数**（卡厄斯兰那官方 tooltip 口径） | **不重置行动值**——跨波次按原行动值续跑 | 卡厄斯兰那倒计时回合（白厄变身）、衣匠 Garmentmaker 倒计时（见 `12_summon.md` §12.4） |

- 倒计时类由**倒计时实体**承载：行动轴上固定速度的倒计时单位（非 actor，不吃增益/治疗/推拉条）
- **不得误用**：德谬歌式手动衰减（`adjust_duration`，见 `05_effects.md`）与 buff 走字不得作用于倒计时类——它不在回合结算链上

> 落地自决策卡 #16（2026-08-15）

---
