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
| `exit_conditions` | `List[{trigger, value}]` | `[]` | 退出条件，如 `{trigger: "on_action_count", value: 3}`（`on_action_count` 为 StateConfig 私有枚举，非 §4.8/§23.4 总线事件） |

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

### 17.8 形态叠加规则（TBD）

形态通常互斥（如不能同时 `godmode` + `khaslana`），但 `transformed` 可以累加。具体优先级、互斥、共享语义待决策（TBD）。

### 17.9 TBD

- 形态叠加/互斥/优先级规则（TBD）。
- 状态切换的“过渡帧”是否建模（如 Phainon 终极技动画，TBD）。

---
