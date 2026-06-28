## 4. Buff / Modifier 定义

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

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
      flat_bonus: "base_stats.def * 0.48 + 640"

  on_turn_start:
    - effect_type: "none"

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
      flat_bonus: 0.3
```

### 4.2 数值字段：flat_bonus 与 scaling_from_source

Modifier 的数值加成拆分为两个字段，均属于 **Layer 2 tagged**（见 §4.7 两层属性模型）：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `flat_bonus` | expression | `0` | 固定数值加成（Layer 2 tagged） |
| `scaling_from_source` | expression | `0` | 按来源 actor 的对应属性 Layer 1 比例加成（Layer 2 tagged） |
| `source_stat` | enum | 同 `stat` | scaling 读的 source 属性（跨属性 scaling 用） |
| `source_actor` | actor_ref | `self` | scaling 的 source actor（默认自身） |

**旧 `value` 字段的迁移**：
- 纯固定加成：`value: 0.3` → `flat_bonus: 0.3`
- 纯比例加成：`value: "base_stats.atk * 0.3"` → `scaling_from_source: 0.3` + `source_stat: "atk"`

### 4.3 转化维度标签

为防止属性二次转化形成循环，modifier 带 4 个维度标签：

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `tagged_as_conversion` | bool | `true` | 本次转化产生的值是否标记为“转化所得” |
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
        target: "single_ally"
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
modifier:
  stat: "dmg_bonus"
  scaling_from_source: "$self.xueyi_ratio"
  source_stat: "break_effect"
  tagged_as_conversion: false
  reads_converted_values: true
  dynamic_update: true
  continuous: true
```

### 4.4 A/B 类 Buff 判定与结算

崩铁 buff 分为 A 类和 B 类，判定和结算时机不同：

| 类型 | 判定时机 | 结算时机 | 来源 |
|------|---------|---------|------|
| A 类 | 判定A(回合开始) 或 判定B(行动进行) | 结算1(回合开始) 或 结算2(回合结束) | DOT、冻结/纠缠/禁锢、遗器/光锥/技能产生的 buff |
| B 类 | 判定B(行动进行) | 结算2(回合结束) | 部分终结技产生的 buff |

**回合四阶段**：
1. **回合开始**：判定A + 结算1（DOT 和控制效果在此结算）
2. **行动准备**：推拉条、冻结补偿
3. **行动进行**：判定B（A/B 类 buff 均可在此判定）
4. **回合结束**：结算2（除 DOT 外的计时状态在此结算）

> 部分永久状态（如火主"灼烧意志"）**不受回合结算影响**，持续到特定移除条件。

**击破状态 + 控制效果交互**：
- 冻结/纠缠/禁锢在敌人回合开始时结算
- 结算后敌人仍处于击破状态（韧性 = 0），直到真正行动
- 此期间无法再次削韧

### 4.5 叠加模式

| `stack_mode` | 行为 | 适用场景 |
|-------------|------|---------|
| `"refresh"` | 刷新持续时间（默认） | 多数 buff |
| `"independent"` | 每层独立计时 | 风化 DOT |
| `"replace"` | 替换旧的 | 护盾 |

### 4.6 驱散规则

| `dispellable` | 说明 |
|---------------|------|
| `True` | 可驱散（默认） |
| `False` | 不可驱散（如控制效果） |

驱散顺序：LIFO；净化顺序：LIFO。

> 净化**不会优先解除控制效果**。

### 4.7 效果命中公式

```yaml
hit_chance: "min(1, base_chance * (1 + effect_hit) * (1 - target_effect_res + effect_res_pen) * (1 - type_res))"
```

### 4.8 Buff 触发时机清单

| 触发时机 | 说明 |
|---------|------|
| `on_battle_start` | 战斗开始时 |
| `on_wave_start` | 波次开始时 |
| `on_cycle_start` | 轮次开始时 |
| `on_cycle_end` | 轮次结束时 |
| `on_turn_start` | 携带者回合开始时 |
| `on_turn_end` | 携带者回合结束时 |
| `on_before_action` | 行动前 |
| `on_after_action` | 行动后 |
| `on_before_hit` | 造成伤害前 |
| `on_after_hit` | 造成伤害后 |
| `on_being_hit` | 受击时 |
| `on_being_targeted` | 被选为目标时 |
| `on_kill` | 击杀敌人时 |
| `on_ally_kill` | 队友击杀时 |
| `on_hp_change` | 生命值变化时 |
| `on_break` | 击破韧性时 |
| `on_weakness_break` | 造成弱点击破时 |
| `on_energy_full` | 能量满时 |
| `on_death` | 死亡时 |
| `on_hit` | 攻击命中时（与 `on_being_hit` 区分） |
| `on_extra_turn` | 额外回合开始时 |
| `on_dot_retrigger` | DOT 立即触发时 |
| `on_ally_action` | 队友行动时 |
| `on_ally_damage` | 队友造成伤害时 |
| `on_target_dead` | 目标死亡时（被击杀方触发） |
| `on_resource_threshold` | 自定义资源达到阈值时 |
| `on_energy_threshold` | 能量达到阈值时 |
| `on_aha_moment_end` | 阿哈时刻结束时 |
| `on_holding_resource` | 持有特定资源时（条件门控） |
| `on_elation_skill` | 释放欢愉技时 |
| `on_self_basic_skill` | 自身普攻/战技时 |
| `on_ultimate` | 终结技时 |

### 4.9 Modifier Triggers 与 Event Hooks 的关系

Modifier 的 `on_turn_start` / `on_before_hit` 等 trigger 是 **buff/debuff 生命周期事件**，由 modifier 自身状态驱动，主要用于属性加成/减成的持续效果。

通用 **Event Hook**（`22_event_hook_system.md`）是 actor-level 的事件反应机制，监听资源/伤害/HP/状态变化并触发 effects，用于表达抵扣、分摊、双向同步、累积治疗等复杂逻辑。

两者有语义重叠但当前保持分离。是否合并是 TBD。

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
| **Layer 1（base）** | 基础值 + 装备 + 被动行迹/星魂 | 启动时计算 |
| **Layer 2（tagged）** | `apply_modifier` 产生的所有数值（flat 和 scaling） | modifier 生命周期 |
| **effective** | Layer 1 + Layer 2 | 公式/伤害计算使用 |

> **关键**：`apply_modifier` 产生的所有数值都属于 Layer 2，不管 flat 还是 scaling。其他 scaling modifier 读 source 时默认只读 Layer 1（`reads_converted_values=false`）。

#### 4.10.3 引擎求值流程

每次 Layer 1 变化时跑两遍 pass：

```
Pass 1 — 重算 Layer 1
  layer1[stat] = base_value[stat]
                + Σ 行迹加成
                + Σ 装备加成
                + Σ flat modifier（target = 本 actor）

Pass 2 — 重算 Layer 2
  layer2[stat] = Σ scaling modifier.source_actor.layer1[source_stat] * ratio

effective[stat] = layer1[stat] + layer2[stat]
```

触发重算的事件：加/移除 flat modifier、加/移除 scaling modifier、actor 死亡/复活、modifier 过期。

#### 4.10.4 跨属性 scaling

```yaml
modifier:
  stat: "spd"
  scaling_from_source: "$self.atk_to_spd_ratio"
  source_stat: "atk"
```

读 source.atk 的 Layer 1 加成 target.spd 的 Layer 2。

---
