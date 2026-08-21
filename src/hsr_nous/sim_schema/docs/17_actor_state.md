## 17. Actor 形态状态机 (Actor State)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 17.1 设计目标

建模“actor 在战斗中有多个形态”的机制，例如：
- 刃「地狱变」
- 白厄 Khaslana 终极形态
- Silver Wolf LV.999 Godmode
- 火花「直播连线」
- 希儿「蝶舞」

形态影响：
- 可用 action 集合（替换或锁定某些 action）
- 属性加成（通过 modifier 机制表达，见 §17.5）

### 17.1.1 本章定位：整体糖化（决策卡 #20）

**VM 不认识形态机**——本章全部概念在绑定/编译期展开为既有原语，引擎只见普通 modifier 与条件过滤：

| 形态概念 | desugar（展开目标） |
|----------|---------------------|
| 形态本身 | **标记 modifier**（`dispellable: false`、duration 承载）+ `singleton_group: "actor_state"`（`04_modifier.md` §4.11；互斥 = 同组，可叠加 = 不同组） |
| `enter_state` / `exit_state` | `apply_modifier`（标记）/ `remove_modifier`（标记） |
| `replaces_actions` / `locked_actions` | 合法性条件注入：目标 action 合法性 += `has_modifier(标记)`，被替换者 += 全部替换标记的否定合取（生成算法唯一） |
| `exit_conditions` 私有枚举 | **废除**——`on_resource_depleted` → `04_modifier.md` §4.12 计数器宏族（after_consume + `$resource ≤ 0`）；`on_action_count` → tally 计数（映射表与本章同文件维护） |
| `on_enter` / `on_exit` | 标记 `on_apply` 内联 / `after_remove_modifier` hook——**退出全路径经 remove 单漏斗汇聚**（含边界清理：波次/战斗结束清理点必须发射 `after_remove_modifier`，钉在引擎边界清理一处） |
| `$self.actor_state` 查询 | `has_modifier` 派生视图 |
| `on_state_change` 事件 | 现态引擎原生发射；**B24 数据宏落地后降格为宏**（展开为 `after_apply_modifier` / `after_remove_modifier` + `singleton_group` 过滤，模板写法不变） |

**叠加规则（§17.9 钉死）**：多形态替换同一 action = validator error（宁严勿宽）；放逐期间标记冻结由 banish 状态冻结既有语义覆盖。表面语法（StateConfig 字段）全部保留——模板写法不变，变的是"引擎是否原生实现"。

### 17.2 ActorState 枚举

```python
class ActorState(str, Enum):
    normal = "normal"
    transformed = "transformed"      # Phainon 终结技后
    khaslana = "khaslana"            # Phainon 终极形态
    hellscape = "hellscape"          # 刃 战技
    godmode = "godmode"              # Silver Wolf LV.999
    live_link = "live_link"          # 火花 直播连线
    amplification = "amplification"  # 希儿 蝶舞
    ult_sequence = "ult_sequence"    # 终结技操控序列（姬子·启行 6 连自选、Silver Wolf LV.999 续段，见 §17.8）
```

| 值 | 角色 / 触发 |
|----|------------|
| `normal` | 默认 |
| `transformed` | Phainon 终结技后 |
| `khaslana` | Phainon 终极形态 |
| `hellscape` | 刃 战技 |
| `godmode` | Silver Wolf LV.999 |
| `live_link` | 火花 直播连线 |
| `amplification` | 希儿 蝶舞 |
| `ult_sequence` | 终结技操控序列：开大进入、额度耗尽/选择完毕退出并续放终结段（见 §17.8） |

> **离场（放逐）不是 ActorState 枚举值**：离场是正交的**在场性**维度，由 `banish_actor` 管理（不可选中 / 状态冻结 / 回场恢复三语义，见 `05_effects.md`）——形态状态机管"可用行动与形态配置"，离场管"在不在场"。actor 可在任意形态下被放逐，离场期间形态配置冻结原样、回场后照旧；因此 ActorState 不设 `departed` / `banished` 值。离场事实的 `actor_exit`（`reason: "exile"`）见 `23_event_hook_system.md` §23.4。
>
> 落地自决策卡 #16（2026-08-15）

### 17.3 StateConfig 字段

```python
class StateConfig(BaseModel):
    state: ActorState
    replaces_actions: dict[str, str] = {}
    locked_actions: list[str] = []
    exit_conditions: list[dict] = []
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `state` | `ActorState` | 必填 | 形态标识 |
| `replaces_actions` | `Dict[action_id, action_id]` | `{}` | 行动替换映射，如 `basic → enhanced_basic` |
| `locked_actions` | `List[action_id]` | `[]` | 该形态下禁用的行动 |
| `exit_conditions` | `List[{trigger, value}]` | `[]` | 退出条件，如 `{trigger: "on_action_count", value: 3}`（`on_action_count` / `on_resource_depleted` 为 StateConfig 私有枚举，非 §4.8/§23.4 总线事件） |

### 17.4 Actor 新增字段

```python
class Actor(BaseModel):
    # ... 既有字段 ...
    actor_state: ActorState = ActorState.normal
    state_config: StateConfig | None = None
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `actor_state` | `ActorState` | `normal` | 当前形态 |
| `state_config` | `StateConfig?` | `None` | 当前形态配置（`actor_state != normal` 时有效） |

形态状态机适用于**所有 actor**：角色、忆灵、召唤物、敌人。

### 17.5 形态属性加成走 modifier

**已定决策**：形态带来的属性变化（如刃地狱变“造成伤害提高”）通过 `enter_state` 触发的 modifier 表达，**不引入额外的 `state_stats_override` 字段**。

保持单一属性修改路径，让形态加成跟普通 buff 处理逻辑一致。

### 17.6 新增 effect_type

#### `enter_state`

```yaml
effect_type: "enter_state"
to_state: "hellscape"
duration: 3
replaces_actions:
  shard_sword: forest_of_swords
locked_actions: ["blade_skill"]
on_enter_effects:
  # 假设 self.hellscape_dmg_boost / self.hellscape_duration 已通过 variable_bindings 绑定
  - effect_type: "apply_modifier"
    modifier:
      modifier_id: "hellscape_dmg_boost"
      stat: "all_dmg_bonus"
      flat_bonus: "$self.hellscape_dmg_boost"
      duration: "$self.hellscape_duration"
on_exit_effects:
  - effect_type: "remove_modifier"
    modifier_id: "hellscape_dmg_boost"
```

| 字段 | 说明 |
|------|------|
| `from_state` | 允许从哪些形态切换（可选，默认任何形态） |
| `to_state` | 目标形态 |
| `duration` | 持续回合数；`0` 表示永久 |
| `replaces_actions` | action 替换映射 |
| `locked_actions` | 锁定 action 列表 |
| `exit_conditions` | 自定义退出条件 |
| `on_enter_effects` | 进入形态时触发的效果 |
| `on_exit_effects` | 退出形态时触发的效果 |

#### `exit_state`

```yaml
effect_type: "exit_state"
target_state: "normal"
```

#### `transform_action`

```yaml
# 单独把某个 action 替换为另一个 action，不切换整体形态
effect_type: "transform_action"
target_action: "basic"
new_action_id: "enhanced_basic"
```

### 17.7 示例：刃 (1205) Hellscape

```yaml
# data/sim_templates/characters/1205_blade.yaml
actor_id: "1205"
name: "blade"

lookup_tables:
  hellscape_duration:   [3, 3, 3, 3, 3]
  hellscape_dmg_boost:  [0.20, 0.25, 0.30, 0.35, 0.40]
  hellscape_taunt:      [10.0, 10.0, 10.0, 10.0, 10.0]   # +1000%（scaling 后最终 = 基础 ×11）

variable_bindings:
  - self.hellscape_duration  = lookup_table("hellscape_duration",  index=$build.skill_levels.skill - 1)
  - self.hellscape_dmg_boost = lookup_table("hellscape_dmg_boost", index=$build.skill_levels.skill - 1)
  - self.hellscape_taunt     = lookup_table("hellscape_taunt",     index=$build.skill_levels.skill - 1)
  - self.m2_crit_rate        = 0.15  # 星魂效果固定值，不按行迹等级索引

actions:
  - action_id: "120502"
    name: "地狱变"
    action_type: "skill"
    effects:
      - effect_type: "enter_state"
        to_state: "hellscape"
        duration: "$self.hellscape_duration"
        replaces_actions:
          shard_sword: forest_of_swords
        locked_actions: ["blade_skill"]
        on_enter_effects:
          - effect_type: "apply_modifier"
            target: "self"
            modifier:
              modifier_id: "hellscape_dmg_boost"
              stat: "all_dmg_bonus"
              flat_bonus: "$self.hellscape_dmg_boost"
              duration: "$self.hellscape_duration"
          - effect_type: "apply_modifier"
            target: "self"
            modifier:
              modifier_id: "hellscape_taunt"
              stat: "taunt"
              scaling_from_source: "$self.hellscape_taunt"
              source_stat: "taunt"
              duration: "$self.hellscape_duration"
          - effect_type: "apply_modifier"
            condition: "$build.eidolon >= 2"
            target: "self"
            modifier:
              modifier_id: "hellscape_m2_crit_rate"
              stat: "crit_rate"
              flat_bonus: "$self.m2_crit_rate"
              duration: "$self.hellscape_duration"
        on_exit_effects:
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_dmg_boost"
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_taunt"
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_m2_crit_rate"
```

### 17.8 操控序列：终结技续段执行

一类终结技不是"一次结算完"，而是**开大进入操控形态 → 逐段选择 → 满足条件退出并自动续放终结段**。按状态机建模——**复用 `enter_state` / `exit_state` + `custom_resources` 额度计数，不引入检查点 / 可恢复执行模型**：

1. **进入**：终结技 `enter_state` 进入操控形态（`ult_sequence`），同时初始化额度资源（如 6 次自选）
2. **操控段**：形态内可用行动被 `replaces_actions` 替换为"自选段"行动，每次选择消耗 1 点额度
3. **退出 + 续段**：额度耗尽（`exit_conditions` 用 `on_resource_depleted`）或操控方选择完毕（主动 `exit_state`）→ 退出形态，`on_exit_effects` 自动续放终结段
4. **全灭续段**：波次提前结束（敌方全灭）导致形态结束时，`on_exit_effects` 照常结算——续放段不丢失（Silver Wolf LV.999 全灭续段）

```yaml
# 姬子·启行终结技：6 次自选 + 耗尽自动续放终结段
custom_resources:
  himeko_ult_charges:
    max: 6                       # 操控额度

actions:
  - action_id: "himeko_ultimate"
    name: "终结技"
    action_type: "ultimate"
    effects:
      - effect_type: "enter_state"
        to_state: "ult_sequence"
        replaces_actions:
          himeko_basic: himeko_ult_pick
          himeko_skill: himeko_ult_pick
        exit_conditions:
          - {trigger: "on_resource_depleted", value: "himeko_ult_charges"}   # StateConfig 私有枚举（见 §17.3），非总线事件
        on_exit_effects:
          # 终结段：退出形态时自动续放
          - effect_type: "deal_damage"
            target: "all_enemies"
            damage_type: "fire"
            amount: "$self.atk * 2.0"

  - action_id: "himeko_ult_pick"
    name: "自选段"
    action_type: "ultimate"
    target_type: "enemy_single"
    effects:
      - trigger: "on_cast"
        target: "self"
        effect_type: "consume_resource"
        resource_id: "himeko_ult_charges"
        amount: 1
      - trigger: "on_cast"
        target: "primary_target"
        effect_type: "deal_damage"
        formula: "damage"
        damage_type: "fire"
        amount: "$self.atk * 0.8"
```

> 落地自决策卡 #11（2026-08-14）

### 17.9 形态叠加规则（TBD）

形态通常互斥（如不能同时 `godmode` + `khaslana`），但 `transformed` 可以累加。具体优先级、互斥、共享语义待决策（TBD）。

### 17.10 TBD

- 形态叠加/互斥/优先级规则（TBD）。
- 状态切换的“过渡帧”是否建模（如 Phainon 终极技动画，TBD）。

---
