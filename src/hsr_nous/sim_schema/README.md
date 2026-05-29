# Sim Schema 仿真器输入格式

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：**一切机制都抽象为"事件-响应"模型**。

## 设计哲学

- **技能、行迹、星魂、光锥、遗器**：本质都是**事件监听器**——在特定时机触发效果
- **buff/debuff**：也是事件监听器——在持续期间内响应特定事件
- **伤害公式**：参数化配置，默认使用崩铁标准公式，支持自定义
- **纯数据驱动**：所有机制用 JSON/YAML 描述，不写硬编码逻辑

---

## 数据流概览

```
Encounter（关卡配置）
├── globals（全局状态：行动值、战技点、随机种子）
├── formula（伤害公式定义）
├── actors[]（参战单位）
│   ├── [角色] base_stats / actions[] / traces[] / eidolons[] / light_cone / relics[]
│   └── [敌人] base_stats / weakness / resistance / max_toughness / actions[]
├── waves[]（波次配置）
│   ├── wave_index / enemy_ids / enemy_levels
│   └── on_wave_start[]（转波次触发的效果）
├── cycle（轮次 AV 配置）
│   ├── first_cycle_av / subsequent_cycle_av
│   └── on_cycle_start[] / on_cycle_end[]
└── modifiers[]（初始 buff，如环境效果）

数据来源：
├── 角色数据 ← pipeline → raw_schema (Character/LightCone/Relic)
└── 敌人数据 ← pipeline → raw_schema (Enemy) + 关卡配置(base_stats/toughness)
```

### 波次机制

波次定义战斗中的敌人分组。当一个波次的所有敌人被击败后，下一个波次的敌人登场。

```yaml
waves:
  - wave_index: 1
    enemy_ids: ["1002011", "1002012", "1002013"]
    enemy_levels: [80, 80, 80]
    # 新敌人登场时触发的效果
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_1"
        target: "all_allies"
        description: "忘却之庭环境 buff"

  - wave_index: 2
    enemy_ids: ["1002020", "1002021"]
    enemy_levels: [80, 80]
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_2"
        target: "all_allies"
```

**波次触发时机**：
- `on_wave_start`：新波次敌人登场时触发
- 可用于：环境 buff、波次奖励、难度变化等
- 忘却之庭特殊机制：转波次会清空当前轮次 AV（重置为 150），所有角色和敌人重新计算行动值

---

### 轮次机制

轮次是 AV（行动值）循环机制，与角色的回合(Turn)是不同概念。每个轮次有固定的 AV 预算，当累计行动值消耗达到预算时进入下一轮次。不同玩法模式有不同的 AV 配置。

详见 `docs/mechanics/action_sequence.md`。

```yaml
cycle:
  first_cycle_av: 150        # 忘却之庭首轮 150 AV（异相仲裁 300）
  subsequent_cycle_av: 100   # 后续轮次 100 AV
  on_cycle_start:
    - effect_type: "apply_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
      description: "忘却之庭当期环境 buff"
  on_cycle_end:
    - effect_type: "remove_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
```

**轮次触发时机**：
- `on_cycle_start`：新轮次开始时触发，通常用于环境 buff
- `on_cycle_end`：轮次结束时触发
- 忘却之庭：每轮次开始触发当期环境 buff
- 异相仲裁：每过一定轮次增加角色伤害（如第 3 轮开始每轮给所有角色加一层"中盘激战"：每层 +50% 最终伤害）

**轮次与回合的区别**：
- **回合 (Turn)**：角色/敌人的单次行动，由速度决定行动顺序
- **轮次 (Cycle)**：AV 循环周期，独立于速度，不能被推拉条影响

---

## 1. 伤害公式 (Formula)

公式单独定义，参数从运行时状态读取。完整公式参见 `docs/mechanics/damage_formula.md`。

### 1.1 标准伤害公式

```yaml
formula:
  # 标准伤害（12 个乘区）
  damage:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * indVulnMulti * finalDmgMulti * critMulti * weakenMulti * dmgRedMulti"

    parameters:
      # 1. 技能倍率乘区
      - name: abilityMulti
        source: skill_scaling  # 从技能倍率表读取

      # 2. 增伤乘区（DMG_BOOST）
      - name: dmgBoostMulti
        expression: "1 + dmg_bonus + all_dmg_bonus"

      # 3. 独立增伤乘区（独立于增伤）
      - name: indDmgBoostMulti
        expression: "1 + ind_dmg_bonus"

      # 4. 防御乘区
      - name: defMulti
        expression: "max(0, 1 - def_pen) * (attacker_level * 10 + 200) / (target_def * (1 - def_pen) + attacker_level * 10 + 200)"

      # 5. 抗性乘区（clamp 到 [-1.0, 0.9]）
      - name: resMulti
        expression: "clamp(1 - target_res + res_pen, -1.0, 0.9)"

      # 6. 基础通用乘区（韧性状态）
      - name: baseUniversalMulti
        expression: "target_toughness > 0 ? 1.0 : 0.9"

      # 7. 易伤乘区
      - name: vulnMulti
        expression: "1 + vulnerability"

      # 8. 独立易伤乘区
      - name: indVulnMulti
        expression: "1 + ind_vulnerability"

      # 9. 最终伤害乘区
      - name: finalDmgMulti
        expression: "1 + final_dmg_bonus"

      # 10. 暴击乘区（单次判定形式）
      - name: critMulti
        expression: "is_crit ? (1 + crit_dmg) : 1.0"

      # 11. 虚弱乘区
      - name: weakenMulti
        expression: "1 - weaken"

      # 12. 减伤乘区
      - name: dmgRedMulti
        expression: "1 - dmg_reduction"
```

### 1.2 期望伤害公式

用于理论计算（不模拟随机）：

```yaml
  damage_expected:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * indVulnMulti * finalDmgMulti * critExpectedMulti * weakenMulti * dmgRedMulti"

    parameters:
      # 暴击使用期望值形式
      - name: critExpectedMulti
        expression: "effective_crit_rate * (1 + crit_dmg) + (1 - effective_crit_rate)"
      # ... 其他乘区同上
```

### 1.3 特殊伤害类型

```yaml
  # 真实伤害（无视防御/抗性/减伤）
  true_damage:
    expression: "abilityMulti * dmgBoostMulti * critMulti"
    description: "只受增伤和暴击影响"

  # 击破伤害
  break_damage:
    expression: "breakBaseMulti * beMulti * baseUniversalMulti * defMulti * resMulti * vulnMulti * finalDmgMulti * weakenMulti * dmgRedMulti"
    parameters:
      - name: breakBaseMulti
        expression: "3767.5533 * elemental_break_scaling * (0.5 + max_toughness / 120) * special_scaling"
      - name: beMulti
        expression: "1 + break_effect"

  # 超击破伤害
  super_break_damage:
    expression: "breakBaseMulti * super_break_scaling * beMulti * defMulti * resMulti * vulnMulti * finalDmgMulti * weakenMulti * dmgRedMulti"
    parameters:
      - name: super_break_scaling
        source: skill_super_break_scaling

  # DOT 持续伤害
  dot_damage:
    expression: "abilityMulti * dmgBoostMulti * indDmgBoostMulti * defMulti * resMulti * vulnMulti * finalDmgMulti * ehrMulti * dot_tick_coefficient"
    parameters:
      - name: ehrMulti
        expression: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res))"
      - name: dot_tick_coefficient
        source: dot_tick_coefficient  # 不同 DOT 类型不同

  # 欢愉伤害
  elation_damage:
    expression: "abilityMulti * dmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * critMulti * elation_multi * laugh_point_multi"
    parameters:
      - name: elation_multi
        expression: "1 + elation_damage_bonus"
      - name: laugh_point_multi
        expression: "1 + 5 * laugh_point / (laugh_point + 240)"

  # 治疗
  heal:
    expression: "heal_scaling * (1 + heal_bonus) + flat_heal"

  # 护盾
  shield:
    expression: "shield_scaling * (1 + shield_bonus)"
```

### 1.4 属性击破效果

```yaml
break_effects:
  physical:  # 裂伤
    type: "dot"
    scaling: "target_max_hp * 0.07"  # 或固定值，取较大
    duration: 3

  fire:  # 灼烧
    type: "dot"
    scaling: "breakBaseMulti * 0.5"
    duration: 3

  ice:  # 冻结
    type: "control"
    duration: 1
    action_value_penalty: 0.5  # 解冻后行动值为 50%

  thunder:  # 触电
    type: "dot"
    scaling: "breakBaseMulti * 0.5"
    duration: 3

  wind:  # 风化
    type: "dot"
    scaling: "breakBaseMulti * 1.0"
    duration: 3

  quantum:  # 纠缠
    type: "control"
    duration: 1
    extra_damage: "breakBaseMulti * 0.5"  # 解除时造成额外伤害

  imaginary:  # 禁锢
    type: "control"
    duration: 1
    action_value_delay: 0.3  # 行动延后 30%
```

### 1.5 削韧值表

基础削韧值（按打击方式）：

| 打击方式 | 削韧值 | 示例 |
|---------|--------|------|
| 单体 (SingleAttack) | 10 | 普攻、单体战技 |
| 扩散 (Blast) | 10(主) + 5(扩散) | 普攻扩散、战技扩散 |
| 群体 (AoEAttack) | 10 | 群体战技、群体终结技 |
| 弹射 (Bounce) | 5×N | 弹射技能 |

**削韧效率公式**：
```
实际削韧 = 基础削韧 × (1 + breakEfficiencyBoost) × (1 + weaknessBreakEfficiencyBoost)
```

### 1.6 双击破机制

当削韧值 >= 剩余韧性时，触发双击破：
1. 先结算当前攻击的伤害
2. 再结算击破伤害
3. 如果是弱点击破，额外触发弱点击破效果

**设计意图**：
- 公式与机制解耦，想改公式只需改这里
- `expression` 用简单数学表达式，运行时求值
- `source` 指向运行时状态中的某个值
- 支持自定义新公式（如追加伤害、持续伤害等）
- 乘区定义与 `docs/mechanics/damage_formula.md` 完全对齐

---

## 2. 全局状态 (Globals)

```yaml
globals:
  action_value: 10000        # 行动值上限（崩铁标准）
  skill_points:
    max: 5                   # 可动态提升（如花火至 7）
    current: 3
  # 可扩展：场地效果、环境变量等
```

### 2.1 能量系统

能量上限从 `characters.json` 的 `max_sp` 字段获取。

**能量来源与数值**：

| 来源 | 基础回能 | 受能量恢复效率影响 |
|------|---------|------------------|
| 普攻 | 20 | 是 |
| 战技 | 30 | 是 |
| 终结技回能 | 5 | 否（固定值） |
| 追加攻击 | 5/10/0 | 是 |
| 受击 | 5/10/15/20 | 是 |
| 击杀 | 10 | 否（固定值） |

**能量恢复效率公式**：
```yaml
# 实际回能 = 基础回能 × (1 + 能量恢复效率)
energy_gain: "base_energy * energy_regen"

# 部分固定回能不享受加成
energy_gain_fixed: "base_energy"  # 如终结技回能、击杀回能
```

**终结技机制**：
- 能量满时可释放，释放后能量清零
- 终结技可立即插队（插入行动序列）
- 部分角色支持弱化版终结技或存储多次

---

## 3. 参战单位 (Actor)

Actor 分为角色和怪物，共用同一套结构。

```yaml
actor:
  actor_id: "1001"
  name: "三月七"
  actor_type: "character"    # character | monster
  level: 80

  # ========== 基础属性（只定义变量，值由 adapter 填入）==========
  base_stats:
    # 基础属性
    hp: 1047
    atk: 564
    def: 485
    spd: 101

    # 暴击
    crit_rate: 0.05          # 基础 5%
    crit_dmg: 0.50           # 基础 50%

    # 击破
    break_effect: 0.0

    # 效果
    effect_hit: 0.0
    effect_res: 0.0

    # 能量
    max_energy: 120          # 从 characters.json max_sp
    energy: 0                # 当前能量
    energy_regen: 1.0        # 能量恢复效率（基础 100%）

    # 治疗/护盾
    heal_bonus: 0.0
    shield_bonus: 0.0

    # 增伤（按属性分类）
    dmg_bonus:
      all: 0.0               # 通用增伤
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    # 抗性（按属性分类）
    resistance:
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    # 弱点属性（敌人用）
    weakness: ["ice", "wind"]

    # 嘲讽值（受击概率权重）
    taunt: 150               # 存护=150, 毁灭=125, 其他=100, 智识/巡猎=75

    # 欢愉度
    elation: 0.0

    # 韧性（敌人用）
    max_toughness: 100       # 韧性上限
    toughness: 100           # 当前韧性

    # 追加攻击增伤（独立乘区）
    follow_up_dmg_bonus: 0.0

  # ========== 技能 ==========
  actions:
    - action_id: "1001_basic"
      name: "寒冰之箭"
      action_type: "basic"           # basic | skill | ultimate | talent | follow_up | elation_damage
      target_type: "enemy_single"    # enemy_single | enemy_blast | enemy_aoe | ally_single | ally_aoe | self
      damage_type: "ice"
      energy_gain: 20
      skill_point_gain: 1            # 普攻回复 1 战技点
      toughness_dmg: 10              # 普攻削韧值
      # 技能效果：事件响应列表
      effects:
        - trigger: "on_cast"         # 释放时触发
          target: "primary_target"
          effect_type: "deal_damage"
          formula: "damage"
          scaling: 0.5               # 倍率 50%
        - trigger: "on_cast"
          target: "self"
          effect_type: "gain_energy"
          value: 20

    - action_id: "1001_skill"
      name: "可爱即是正义"
      action_type: "skill"
      target_type: "ally_single"
      skill_point_cost: 1            # 战技消耗 1 战技点
      toughness_dmg: 20              # 战技削韧值
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
      toughness_dmg: 30              # 终结技削韧值
      effects:
        - trigger: "on_cast"
          target: "all_enemies"
          effect_type: "deal_damage"
          formula: "damage"
          scaling: 1.5
        - trigger: "on_cast"
          target: "random_enemy"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_FREEZE"
          duration: 1
          chance: 0.5                  # 50% 基础概率，受效果命中影响

  # ========== 行迹（被动能力）==========
  traces:
    - trace_id: "T_1001_1"
      name: "公主殿下"
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_TRACE_CRIT"
          duration: 0                   # 0 表示永久

  # ========== 星魂 ==========
  eidolons:
    - eidolon_id: "E_1001_1"
      name: "记忆中的你"
      unlocked: true
      effects:
        - trigger: "on_shield_apply"
          condition: "modifier_id == MOD_1001_SHIELD"
          target: "shielded_target"
          effect_type: "heal"
          formula: "heal"
          scaling: 0.3                  # 回合同等生命值 30%

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
  relics:
    - relic_id: "R_101_1"       # 头部
      set_id: "S_101"            # 套装编号
      slot: "head"
      main_stat: {stat: "hp", value: 705.0}
      sub_stats:
        - {stat: "atk", value: 42.0}
        - {stat: "spd", value: 4.0}
    - relic_id: "R_101_2"       # 手部
      set_id: "S_101"
      slot: "hand"
      main_stat: {stat: "atk", value: 352.0}
      sub_stats:
        - {stat: "crit_rate", value: 0.06}
        - {stat: "crit_dmg", value: 0.08}
    # ... 躯干、脚部、位面球、连结绳

  # 套装效果（由 adapter 根据套装件数自动附加）
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

---

## 4. Buff / Modifier 定义

Buff 是核心机制，所有持续效果都用它表达。

### 4.1 Modifier 结构

```yaml
modifier:
  modifier_id: "MOD_1001_SHIELD"
  name: "护盾"
  modifier_type: "shield"       # buff | debuff | dot | shield | heal | control
  max_stack: 1
  duration: 3                    # 持续回合数，0 为永久
  stack_mode: "refresh"          # 独立计时 | refresh | replace
  dispellable: true              # 是否可驱散

  # 触发时机和效果
  on_apply:
    - effect_type: "add_stat"
      stat: "shield"
      value: "base_stats.def * 0.48 + 640"

  on_turn_start:                 # 回合开始时
    - effect_type: "none"        # 护盾回合开始时无效果

  on_expire:
    - effect_type: "remove_stat"
      stat: "shield"

  # 如果是 dot：
  on_turn_start:
    - effect_type: "deal_damage"
      formula: "damage"
      damage_type: "fire"
      scaling: 0.5

  # 如果是 debuff（减防）：
  on_apply:
    - effect_type: "add_stat"
      stat: "def_reduction"
      value: 0.3                  # 减防 30%
```

### 4.2 A/B 类 Buff 判定与结算

崩铁 buff 分为 A 类和 B 类，判定和结算时机不同：

| 类型 | 判定时机 | 结算时机 | 示例 |
|------|---------|---------|------|
| A 类 | 回合开始 或 行动进行 | 回合开始 或 回合结束 | 多数增伤 buff |
| B 类 | 行动进行 | 回合结束 | 部分 debuff |

**回合四阶段**：
1. 回合开始：A 类 buff 判定 + 结算
2. 行动准备：推拉条、冻结补偿
3. 行动进行：A/B 类 buff 判定
4. 回合结束：A/B 类 buff 结算、DOT 伤害

### 4.3 叠加模式

```yaml
stack_mode: "refresh"  # 默认

# 独立计时：每层独立计算持续时间
# 示例：风化 DOT，每层独立倒计时

# refresh：刷新持续时间
# 示例：多数 buff，重复施加时刷新持续时间

# replace：替换
# 示例：护盾，新护盾替换旧护盾
```

### 4.4 驱散规则

```yaml
dispellable: true       # 可驱散（默认）
dispellable: false      # 不可驱散（如控制效果）

# 驱散顺序：LIFO（后进先出）
# 净化顺序：LIFO（后进先出）
```

### 4.5 效果命中公式

```yaml
# 实际命中概率
hit_chance: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))"
```

### 4.6 Buff 触发时机清单

| 触发时机 | 说明 |
|---------|------|
| `on_battle_start` | 战斗开始时 |
| `on_wave_start` | 波次开始时 |
| `on_cycle_start` | 轮次开始时 |
| `on_cycle_end` | 轮次结束时 |
| `on_turn_start` | 携带者回合开始时 |
| `on_turn_end` | 携带者回合结束时 |
| `on_before_action` | 行动前（用于增伤 buff） |
| `on_after_action` | 行动后 |
| `on_before_hit` | 造成伤害前 |
| `on_after_hit` | 造成伤害后 |
| `on_being_hit` | 受击时 |
| `on_being_targeted` | 被选为目标时（嘲讽用） |
| `on_kill` | 击杀敌人时 |
| `on_ally_kill` | 队友击杀时 |
| `on_hp_change` | 生命值变化时 |
| `on_break` | 击破韧性时 |
| `on_weakness_break` | 造成弱点击破时 |
| `on_energy_full` | 能量满时（用于自动开大） |
| `on_death` | 死亡时 |

---

## 5. 效果类型 (Effect Type)

```yaml
# 造成伤害
effect_type: "deal_damage"
formula: "damage"           # 引用 formula 中定义的公式
target: "primary_target"    # 主目标 | all_enemies | all_allies | self | random_enemy | lowest_hp_enemy
scaling: 1.0                # 技能倍率
damage_type: "ice"          # 伤害属性

# 回复生命
effect_type: "heal"
formula: "heal"
target: "ally_single"
scaling: 0.3

# 施加 buff
effect_type: "apply_modifier"
modifier_id: "MOD_XXX"
target: "self"
duration: 3
chance: 1.0                  # 基础概率，受效果命中/抵抗影响

# 移除 buff
effect_type: "remove_modifier"
modifier_id: "MOD_XXX"
target: "enemy_single"

# 修改属性（立即/持续）
effect_type: "add_stat"
stat: "spd"
value: "base_stats.spd * 0.25"   # 支持表达式

# 回复能量
effect_type: "gain_energy"
target: "self"
value: 30

# 推进/拉条
effect_type: "advance_action"
target: "self"
value: 100                     # 行动值推进 100（立即行动）

# 回复战技点
effect_type: "gain_skill_point"
value: 1

# 召唤/召唤物行动
effect_type: "summon_action"
action_id: "SUMMON_XXX"

# 直接结算（用于表达式中的复杂逻辑）
effect_type: "script"
expression: "if target.hp < target.max_hp * 0.5 then apply_modifier(MOD_CRIT_BOOST)"
```

---

## 6. 遗器数值设计

遗器数值分两部分：**主词条**（固定值，由部位决定）和**副词条**（随机数值，由强化次数决定）。

```yaml
relic_main_stats:
  head: {stat: "hp", base: 705.0}           # 固定
  hand: {stat: "atk", base: 352.0}          # 固定
  body:                                         # 可选
    candidates: ["hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "heal_bonus", "effect_hit"]
  feet:
    candidates: ["hp_pct", "atk_pct", "def_pct", "spd"]
  sphere:
    candidates: ["hp_pct", "atk_pct", "def_pct", "physical_dmg", "fire_dmg", "ice_dmg", ...]
  rope:
    candidates: ["hp_pct", "atk_pct", "def_pct", "break_effect", "energy_regen"]

relic_sub_stats:
  # 副词条每次强化增加的数值（崩铁标准）
  hp: {base: 33.87, step: 33.87}           # 小生命
  atk: {base: 16.93, step: 16.93}          # 小攻击
  def: {base: 16.93, step: 16.93}          # 小防御
  hp_pct: {base: 0.034, step: 0.034}
  atk_pct: {base: 0.034, step: 0.034}
  def_pct: {base: 0.043, step: 0.043}
  spd: {base: 2.0, step: 2.3}              # 速度有 2.0 / 2.3 两档
  crit_rate: {base: 0.026, step: 0.032}    # 2.6% / 3.2%
  crit_dmg: {base: 0.052, step: 0.064}     # 5.2% / 6.4%
  break_effect: {base: 0.052, step: 0.064}
  effect_hit: {base: 0.034, step: 0.043}
  effect_res: {base: 0.034, step: 0.043}
```

**adapter 职责**：根据遗器配置计算最终属性，合并到 `base_stats` 中。

---

## 7. 完整输入示例

```yaml
# 一份完整的仿真输入
encounter_id: "E_001"
name: "测试关卡"

formula:
  damage:
    expression: "base_dmg * dmg_multiplier * (1 + dmg_bonus) * def_multiplier * res_multiplier * crit_multiplier"

globals:
  action_value: 10000
  skill_points: {max: 5, current: 3}

actors:
  - actor_id: "1001"
    name: "三月七"
    actor_type: "character"
    level: 80
    base_stats: {hp: 2000, atk: 1000, def: 1200, spd: 101, crit_rate: 0.3, crit_dmg: 1.0}
    actions: [...]
    traces: [...]
    eidolons: [...]
    light_cone: {...}
    relics: [...]

  - actor_id: "M_8001"
    name: "测试怪物"
    actor_type: "monster"
    level: 80
    base_stats: {hp: 50000, atk: 500, def: 500, spd: 120, crit_rate: 0, crit_dmg: 0}
    max_toughness: 120
    weakness: ["ice", "fire"]
    actions:
      - action_id: "M_8001_basic"
        name: "爪击"
        action_type: "basic"
        target_type: "enemy_single"
        effects:
          - trigger: "on_cast"
            target: "primary_target"
            effect_type: "deal_damage"
            formula: "damage"
            scaling: 1.0

initial_modifiers: []   # 开局 buff，如场地效果
```

---

## 8. 与 Adapter 的交互边界

`adapters/` 负责把 `raw_schema`（StarRailRes 数据）转换成本文定义的格式：

### 角色数据映射

| raw_schema 数据 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| `Character` + `LightCone` + `Relics` | `Actor.base_stats` | 计算最终白值 + 绿值 |
| `Character.skills[]` | `Actor.actions[]` | 映射倍率、目标类型、效果 |
| `Character.traces[]` | `Actor.traces[]` | 提取被动效果 |
| `Character.eidolons[]` | `Actor.eidolons[]` | 按解锁状态筛选 |
| `LightCone.effects` | `Actor.light_cone.effects` | 转换光锥特效 |
| `RelicSet.bonus` | `Actor.relic_set_effects` | 按件数组装套装效果 |

### 敌人数据映射

敌人和角色共用 Actor 结构，字段映射如下：

| raw_schema 数据 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| `Enemy.id` | `Actor.actor_id` | 直接映射 |
| `Enemy.name` | `Actor.name` | 直接映射 |
| `Enemy.elemental_weaknesses` | `Actor.weakness` | 转为小写：`["Fire", "Ice"]` → `["fire", "ice"]` |
| `Enemy.elemental_resistance` | `Actor.resistance` | 直接映射：`{"Physical": 0.2}` → `{"physical": 0.2}` |
| `Enemy.skill_list[]` | `Actor.actions[]` | 映射技能（见下方） |
| 无（需配置） | `Actor.base_stats` | 从关卡配置或模板读取 |
| 无（需配置） | `Actor.max_toughness` | 从关卡配置读取 |

**敌人技能映射**：

```yaml
# EnemySkill → Action
enemy_skill:
  Id: 100201101
  Name: "冰风"
  SkillDesc: "对我方全体造成少量冰属性伤害。"
  ElementType: "Ice"

# 映射为
action:
  action_id: "100201101"
  name: "冰风"
  action_type: "basic"          # 默认 basic，可根据 SkillTypeDesc 判断
  target_type: "enemy_aoe"      # 根据 SkillDesc 推断
  damage_type: "ice"            # ElementType 转小写
  effects:
    - trigger: "on_cast"
      target: "all_allies"
      effect_type: "deal_damage"
      formula: "damage"
      scaling: 1.0              # 需从配置或测试获取
```

**敌人属性配置**：

敌人基础属性（hp、atk、def、spd）不在 enemies.json 中，需要从关卡配置或模板获取：

```yaml
# encounter 中的敌人配置
actors:
  - actor_id: "1002011"
    actor_type: "monster"
    level: 80
    base_stats:
      hp: 50000
      atk: 800
      def: 500
      spd: 120
    max_toughness: 100
    # 以下从 enemies.json 自动填充
    weakness: ["fire", "thunder"]
    resistance: {"physical": 0.2, "ice": 0.2}
    actions: [...]  # 从 SkillList 映射
```

---

## FAQ

**Q: 表达式 `"base_stats.def * 0.48 + 640"` 怎么执行？**

A: 运行时维护一个 `Context`，包含当前 actor、目标、全局状态等。表达式用安全的 eval 环境求值，或者实现一个小型表达式引擎。

**Q: 复杂的条件判断（如"生命值低于 50% 时增伤"）怎么表达？**

A: 在 `effects` 里加 `condition` 字段，用表达式表示：
```yaml
effects:
  - trigger: "on_before_hit"
    condition: "target.hp / target.max_hp < 0.5"
    effect_type: "add_stat"
    stat: "dmg_bonus"
    value: 0.3
```

**Q: 多段伤害（如希儿再现）怎么处理？**

A: 每段伤害是一个独立的 `deal_damage` effect，可以设置不同的 `trigger`：
```yaml
effects:
  - trigger: "on_cast"      # 第一段
    effect_type: "deal_damage"
    scaling: 2.0
  - trigger: "on_kill"       # 击杀后再现
    effect_type: "grant_extra_turn"
  - trigger: "on_extra_turn"  # 再现段
    effect_type: "deal_damage"
    scaling: 0.8
```

**Q: 嘲讽机制怎么实现？**

A: 基于 `taunt` 属性的概率选择：
```yaml
# 受击概率 = 角色嘲讽值 / 队伍嘲讽值总和
hit_probability: "actor.taunt / sum(all_ally.taunt)"
```
嘲讽值增减通过 modifier 的 `add_stat` 实现。

**强制嘲讽**：某些技能（如万敌终结技）会强制嘲讽敌人：
```yaml
effect_type: "apply_modifier"
modifier_id: "MOD_FORCED_TAUNT"
target: "all_enemies"
duration: 1
# 效果：被嘲讽的敌人必须攻击施加者
on_being_targeted:
  condition: "source.has_modifier(MOD_FORCED_TAUNT)"
  forced_target: "modifier.caster"
```

**Q: 欢愉命途怎么实现？**

A: 欢愉命途有独立的伤害类型和乘区：
```yaml
# 欢愉伤害公式
elation_damage:
  expression: "abilityMulti * dmgBoostMulti * defMulti * resMulti * baseUniversalMulti * vulnMulti * critMulti * elation_multi * laugh_point_multi"
  parameters:
    - name: elation_multi
      expression: "1 + elation_damage_bonus"  # 欢愉度乘区
    - name: laugh_point_multi
      expression: "1 + 5 * laugh_point / (laugh_point + 240)"  # 笑点乘区（含稀释）

# 阿哈时刻（欢愉命途特殊机制）
aha_moment:
  trigger: "on_laugh_point_full"
  effect: "extra_turn"  # 获得额外回合
  speed_bonus: "laugh_point * 0.01"  # 速度加成
```

**Q: 记忆命途和召唤物（忆灵）怎么实现？**

A: 召唤物是类似角色的单位，但有特殊行为模式。参见下方"召唤物系统"章节。

---

## 9. 战斗结束条件 (Termination)

结束条件决定模拟何时停止，支持多种模式组合。

```yaml
# 模式一：固定行动值，统计总伤害
termination:
  mode: "fixed_av"
  max_action_value: 1500
  max_turns: 50

# 模式二：击杀目标，统计所需行动值
termination:
  mode: "kill_target"
  target_ids: ["M_8001", "M_8002"]  # 指定敌人 ID，空列表表示全部
  max_turns: 50

# 模式三：生存测试，统计存活回合数
termination:
  mode: "survival"
  max_turns: 20

# 模式四：全灭测试
termination:
  mode: "wipe"
  max_turns: 50
```

### 9.1 行动值系统

**行动值公式**：
```yaml
action_value: "10000 / speed"
```

**拉条/推条**：
```yaml
# 拉条（行动提前）
effect_type: "advance_action"
value: 100  # 行动提前 100（立即行动）

# 推条（行动延后）
effect_type: "delay_action"
value: 30   # 行动延后 30%

# 立即行动
effect_type: "immediate_action"
```

**速度变化时行动值调整**：
```yaml
# 当速度发生变化时，行动值需要实时调整
new_action_value: "current_action_value * old_speed / new_speed"
```

**冻结/强烈震荡补偿**：
```yaml
# 冻结解除后，行动值为初始值的 50%
action_value_penalty: 0.5

# 强烈震荡解除后，行动值为初始值的 70%
action_value_penalty: 0.7
```

**插入行动优先级**：
1. 追加攻击
2. 终结技
3. 命途回响
4. 额外回合
5. 战技触发

**后拉先动原则**：行动值相同时，后拉条的单位先行动。

**输出指标（根据模式不同）**：

| 模式 | 主要输出 | 次要输出 |
|------|---------|---------|
| `fixed_av` | 总伤害、DPS | 伤害分布、击杀数 |
| `kill_target` | 所需行动值、回合数 | 伤害效率 |
| `survival` | 存活回合数、存活率 | 承伤总量、治疗量 |
| `wipe` | 是否全灭、全灭回合 | 剩余敌人血量 |

---

## 10. 战斗日志 (Combat Log)

战斗模拟器的输出是一个结构化的事件序列，描述从开始到结束的全过程。

### 日志结构

```yaml
combat_log:
  encounter_id: "E_001"
  policy_name: "三月七_default"
  termination_reason: "max_action_value_reached"  # 或 "target_killed" | "all_allies_dead" | "max_turns"

  # 汇总统计
  summary:
    total_damage: 125000
    total_action_value: 1500
    total_turns: 12
    dps: 83.3
    kills: 3
    deaths: 0

  # 事件序列（核心输出）
  events:
    - timestamp: 0
      event_type: "battle_start"
      data: {}

    - timestamp: 0
      event_type: "turn_start"
      actor_id: "1001"
      actor_name: "三月七"
      action_value: 100

    - timestamp: 0
      event_type: "action"
      actor_id: "1001"
      action_id: "1001_skill"
      action_name: "可爱即是正义"
      target_ids: ["1001"]
      skill_points_before: 3
      skill_points_after: 2

    - timestamp: 0
      event_type: "effect"
      effect_type: "apply_modifier"
      source_id: "1001"
      target_id: "1001"
      modifier_id: "MOD_1001_SHIELD"
      duration: 3

    - timestamp: 0
      event_type: "turn_end"
      actor_id: "1001"

    - timestamp: 100
      event_type: "turn_start"
      actor_id: "M_8001"
      actor_name: "银鬃近卫"

    - timestamp: 100
      event_type: "action"
      actor_id: "M_8001"
      action_id: "M_8001_basic"
      action_name: "爪击"
      target_ids: ["1001"]

    - timestamp: 100
      event_type: "damage"
      source_id: "M_8001"
      target_id: "1001"
      damage: 500
      damage_type: "physical"
      is_crit: false
      target_hp_before: 2000
      target_hp_after: 1500

    - timestamp: 100
      event_type: "turn_end"
      actor_id: "M_8001"

    - timestamp: 1500
      event_type: "battle_end"
      reason: "max_action_value_reached"
```

### 事件类型清单

| event_type | 说明 | 关键字段 |
|------------|------|---------|
| `battle_start` | 战斗开始 | - |
| `battle_end` | 战斗结束 | `reason` |
| `turn_start` | 回合开始 | `actor_id`, `action_value` |
| `turn_end` | 回合结束 | `actor_id` |
| `action` | 执行动作 | `action_id`, `target_ids`, `skill_points_before/after` |
| `damage` | 造成伤害 | `source_id`, `target_id`, `damage`, `damage_type`, `is_crit` |
| `heal` | 回复生命 | `source_id`, `target_id`, `heal`, `target_hp_before/after` |
| `effect` | 效果触发 | `effect_type`, `source_id`, `target_id` |
| `modifier_apply` | 施加 buff | `modifier_id`, `duration` |
| `modifier_expire` | buff 过期 | `modifier_id` |
| `break` | 击破韧性 | `source_id`, `target_id`, `toughness_before/after` |
| `kill` | 击杀 | `killer_id`, `target_id` |
| `death` | 死亡 | `actor_id` |
| `energy_change` | 能量变化 | `actor_id`, `before`, `after` |
| `skill_point_change` | 战技点变化 | `before`, `after` |
| `wave_start` | 波次开始 | `wave_index` |
| `wave_end` | 波次结束 | `wave_index` |
| `cycle_start` | 轮次开始 | `cycle_number`, `cycle_av` |
| `cycle_end` | 轮次结束 | `cycle_number`, `av_consumed` |

### Agent 分析友好

日志设计考虑了 Agent 分析需求：

1. **可追溯**：每个事件有 `timestamp`（行动值），可重建时间线
2. **可聚合**：通过 `event_type` 过滤，快速统计伤害/治疗/buff 覆盖率
3. **可归因**：`source_id` → `target_id` 链路清晰，可追踪伤害来源
4. **可比较**：相同 encounter 不同 policy 的日志可直接对比

```python
# Agent 分析示例
def analyze_log(log: dict) -> dict:
    events = log["events"]

    # 统计伤害分布
    damage_events = [e for e in events if e["event_type"] == "damage"]
    total_damage = sum(e["damage"] for e in damage_events)

    # 统计 buff 覆盖率
    buff_events = [e for e in events if e["event_type"] == "modifier_apply"]

    # 统计死亡
    deaths = [e for e in events if e["event_type"] == "death"]

    return {
        "total_damage": total_damage,
        "buff_count": len(buff_events),
        "deaths": len(deaths),
    }
```

---

## 11. 召唤物系统 (Summon/Memosprite)

召唤物（忆灵）是类似角色的战斗单位，但有特殊行为模式。

### 11.1 召唤物 Actor 结构

```yaml
actor:
  actor_id: "SUMMON_001"
  name: "小伊卡"
  actor_type: "summon"           # character | monster | summon
  level: 80
  owner_id: "1001"               # 召唤者 ID

  # 召唤物属性（可选，不一定全部拥有）
  base_stats:
    hp: 5000                     # 可选：有些召唤物没有生命值
    atk: 800
    def: 300
    spd: 100
    # ... 其他属性可选

  # 召唤物行为模式
  behavior:
    # 行动模式
    action_mode: "independent"   # "independent" | "triggered"

    # independent：出现在行动条上，独立计算行动值
    # triggered：不出现在行动条上，仅在触发条件满足时行动

    # 触发条件（triggered 模式下）
    triggers:
      - event: "on_owner_action_end"  # 召唤者行动后
        description: "风堇的小伊卡"
      - event: "on_ally_hit"          # 队友受击时
        description: "反击型召唤物"
      - event: "on_owner_hp_low"      # 召唤者血量低时
        description: "保护型召唤物"

    # 离场条件
    leave_conditions:
      - type: "hp_zero"          # 生命值归零
      - type: "duration_expire"  # 持续时间到期
      - type: "owner_leave"      # 召唤者离场
      - type: "manual"           # 手动召回（技能效果）
      - type: "mechanic"         # 自身机制（如特定条件触发）

    # 继承规则
    inheritance:
      stats: "partial"           # "full" | "partial" | "none"
      # full：继承召唤者全部属性
      # partial：部分继承（如只继承攻击力）
      # none：使用召唤物自身属性

  # 召唤物技能
  actions:
    - action_id: "SUMMON_001_basic"
      name: "伊卡攻击"
      action_type: "basic"
      target_type: "enemy_single"
      toughness_dmg: 10

  # 召唤物特有机制
  special_mechanics:
    - mechanic: "heal_on_action"
      description: "每次行动后恢复召唤者生命值"
      trigger: "on_after_action"
      effect_type: "heal"
      target: "owner"
      scaling: 0.1
```

### 11.2 召唤物行为模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `independent` | 出现在行动条上，独立计算行动值 | 景元的神君 |
| `triggered` | 不出现在行动条上，仅在触发条件满足时行动 | 风堇的小伊卡、反击型召唤物 |

**触发条件示例**：
- `on_owner_action_end`：召唤者行动后（小伊卡）
- `on_ally_hit`：队友受击时（反击型）
- `on_owner_hp_low`：召唤者血量低时（保护型）
- `on_kill`：击杀敌人时（追击型）

### 11.3 召唤物生命周期

```yaml
# 召唤流程
summon_flow:
  trigger: "on_skill_cast"       # 触发时机
  condition: "skill_id == XXX"   # 触发条件
  effect_type: "summon"
  summon_id: "SUMMON_001"
  position: "after_owner"        # 召唤位置

# 离场流程
leave_flow:
  trigger: "on_hp_zero"          # 生命值归零
  effect_type: "dismiss_summon"
  summon_id: "SUMMON_001"

# 续命机制（某些召唤物可以被治疗/续命）
sustain_mechanic:
  can_be_healed: true            # 是否可被治疗
  can_be_shielded: true          # 是否可被套盾
  persistence: "temporary"       # "permanent" | "temporary"
```

### 11.4 召唤物与忆灵的区别

| 特性 | 普通召唤物 | 忆灵（记忆命途） |
|------|-----------|----------------|
| 行动模式 | 多为 `independent` | 多为 `triggered`（on_owner_action_end） |
| 属性继承 | 部分继承 | 通常独立属性 |
| 离场条件 | 多样 | 通常与召唤者绑定 |
| 技能组 | 固定 | 可能随召唤者成长 |

---

## 12. 输入验证 (Validator)

验证器检查 Encounter 配置的合法性，防止非法输入导致模拟器异常。

### 使用方式

```python
from hsr_nous.sim_schema import validate_encounter, Encounter, Actor

encounter = Encounter(
    encounter_id="E_001",
    name="测试关卡",
    actors=[
        Actor(actor_id="1001", name="三月七", actor_type="character", level=80),
    ],
)

result = validate_encounter(encounter)
if result.valid:
    print("验证通过")
else:
    for error in result.errors:
        print(f"ERROR: {error.path} - {error.message}")
    for warning in result.warnings:
        print(f"WARNING: {warning.path} - {warning.message}")
```

### 验证规则

| 类别 | 规则 | 严重程度 |
|------|------|---------|
| 角色数量 | 上限 4 个 | error |
| 敌人数量 | 每波次上限 10 个 | error |
| 波次数 | 上限 10 个 | error |
| 轮次 AV | 首轮/后续 AV >= 1 | error |
| 最大轮次数 | 上限 99 | error |
| 等级 | 1-90 | error |
| 速度 | 必须 > 0 | error |
| 能量 | 当前 <= 上限 | error |
| 韧性 | 当前 <= 上限 | error |
| 暴击率 | 建议 0-1 | warning |
| 战技点 | current <= max | error |
| actor_type | character/monster/summon | error |
| modifier_type | buff/debuff/dot/shield/heal/control | error |

---

## 13. 策略 DSL (Policy)

策略是可独立输入、可搜索优化的战斗决策逻辑。采用 **Rule-based DSL + 参数化混合** 设计。

### 设计原则

- **可执行**：模拟器直接 interpret，不需要 LLM 实时参与
- **可参数化**：关键数值（如大招阈值）抽离为可调参数，方便网格搜索/贝叶斯优化
- **LLM 友好**：结构清晰，LLM 容易生成和修改
- **维度拆分**：技能选择、目标选择、时机策略分离

### 策略结构

```yaml
policy:
  name: "三月七_default"
  version: "1.0"

  # ========== 技能选择规则（按 priority 降序匹配）==========
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"
      action: "ultimate"
      priority: 100
      description: "能量满时开大"

    - condition: "skill_points > 0 && ally_without_shield"
      action: "skill"
      priority: 50
      description: "有战技点且队友没护盾时给盾"

    - condition: "true"
      action: "basic"
      priority: 0
      description: "默认普攻"

  # ========== 目标选择规则 ==========
  target_rules:
    - condition: "action_type == 'skill'"
      selector: "lowest_hp_ally"
      priority: 100

    - condition: "action_type == 'ultimate'"
      selector: "all_enemies"
      priority: 100

    - condition: "true"
      selector: "primary_target"
      priority: 0

  # ========== 时机策略（可选）==========
  timing_rules:
    - condition: "buff.stack >= 3 && !enemy.broken"
      timing: "delay"
      delay_condition: "enemy.broken == true"
      description: "buff叠满但敌人未击破，延迟到击破后再出手"

  # ========== 可调参数 ==========
  parameters:
    ULT_THRESHOLD: 120        # 大招能量阈值
    SHIELD_PRIORITY: 0.8     # 护盾优先级权重
    HP_THRESHOLD: 0.5        # 低血量阈值
```

### 规则匹配逻辑

1. **技能选择**：按 `priority` 降序遍历 `action_rules`，第一条 `condition` 为真的规则被执行
2. **目标选择**：同样按优先级匹配，决定技能打谁
3. **时机选择**：决定是否立即出手或延迟等待条件

### 表达式上下文

策略表达式中可以访问的变量：

| 变量 | 说明 |
|------|------|
| `energy` | 当前能量 |
| `skill_points` | 当前战技点 |
| `hp` / `max_hp` | 生命值 |
| `buff.<modifier_id>` | 特定 buff 的引用（如 `buff.MOD_1001_SHIELD.stack`） |
| `enemy.<attr>` | 主目标属性 |
| `allies[]` | 队友列表 |
| `enemies[]` | 敌人列表 |
| `parameters.<name>` | 策略参数 |

### 为什么不用自然语言策略

| 自然语言 | Rule-based DSL |
|---------|---------------|
| "优先使用战技" | `condition: "skill_points > 0", action: "skill"` |
| 不可精确执行 | 100% deterministic |
| 不可搜索优化 | 参数可独立调整，适合贝叶斯优化 |
| LLM 生成后需人工翻译 | LLM 直接生成可执行结构 |

### 参数优化示例

```python
# 用贝叶斯优化搜索最佳大招阈值
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim_schema.policy import Policy

def evaluate(threshold: float) -> float:
    policy = Policy(
        action_rules=[...],
        parameters={"ULT_THRESHOLD": threshold}
    )
    engine = CombatEngine(encounter, policy=policy)
    result = engine.run()
    return result.dps

# 在 [100, 140] 区间搜索最优阈值
best_threshold = bayesian_optimize(evaluate, bounds=(100, 140))
```

### 策略与 Encounter 的关系

```yaml
encounter:
  encounter_id: "E_001"
  formula: {...}
  globals: {...}
  actors: [...]
  policy: {...}        # <-- 每个 encounter 可绑定不同策略
  initial_modifiers: []
```

同一个队伍配不同策略，可以对比不同操作手法的差异。
