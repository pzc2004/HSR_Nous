## 18. 秘技系统 (Technique System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 18.1 设计目标

完整建模“大世界秘技 → 战前预置 → 强制进战 → 进入战斗”这一链条，包括：
- 秘技点消耗
- 强制进战标志
- 进战时机的策略选择

### 18.2 秘技定义 (TechniqueDef)

**核心设计**：秘技视为一种 `action`，跟 `basic` / `skill` / `ultimate` 同体系，只是触发时机是**战前阶段**而非战斗内。秘技的 `effects` 字段跟其他 action 完全同构。

```python
class TechniqueDef(BaseModel):
    technique_id: str
    actor_id: str
    point_cost: int
    forces_battle_entry: bool = False
    effects: list[Effect] = []
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `technique_id` | string | 必填 | 秘技唯一 ID |
| `actor_id` | string | 必填 | 持有者 |
| `point_cost` | int | 必填 | 消耗秘技点数（每个秘技各自定义；多数 1，少数 0 或 2） |
| `forces_battle_entry` | bool | `false` | 释放后是否短路战前策略、强制进战 |
| `effects` | `List[Effect]` | `[]` | 战前释放时触发的 effect 列表 |

### 18.3 effects 触发时机

technique 的 effects **不在释放瞬间执行**——而是累积到 PreBattleStrategy 的 `battle_start_effects` 队列，进战时按顺序 fire。

这样跟游戏机制一致：秘技是“装填预置”，进战才生效。

### 18.4 旧 BattleStartPreload → 新 effects 映射

| 旧字段 | 新写法（effects 列表元素） |
|--------|---------------------------|
| `modifiers` | `effect_type: "apply_modifier"` |
| `summon_ids` | `effect_type: "summon"` |
| `resources` | `effect_type: "gain_resource"` |
| `zone_ids` | `effect_type: "deploy_zone"` |

### 18.5 示例

#### 卡芙卡秘技

```yaml
# data/sim_templates/characters/1005_kafka.yaml
techniques:
  - technique_id: "kafka_technique"
    actor_id: "1005"
    point_cost: 1
    forces_battle_entry: false
    effects:
      - effect_type: "apply_modifier"
        target: "all_enemies"
        modifier:
          modifier_id: "shock"
          duration: 3
```

#### 召唤忆灵型秘技

```yaml
# data/sim_templates/characters/1409_hyacine.yaml
techniques:
  - technique_id: "hyacine_memosprite_pre_summon"
    actor_id: "1409"
    point_cost: 1
    forces_battle_entry: false
    effects:
      - effect_type: "summon"
        summon_id: "hyacine_memosprite"
      # 假设 self.memosprite_tech_spd_bonus / self.memosprite_tech_spd_duration 已通过 variable_bindings 绑定
      - effect_type: "apply_modifier"
        target: "self"
        modifier:
          stat: "spd"
          flat_bonus: "$self.memosprite_tech_spd_bonus"
          duration: "$self.memosprite_tech_spd_duration"
```

### 18.6 `point_cost` 与 `forces_battle_entry` 正交

| 组合 | 例子 |
|------|------|
| `point_cost=1, forces_battle_entry=false` | 大多数预置秘技（三月七冰冻、卡芙卡追加） |
| `point_cost=0, forces_battle_entry=false` | 不消耗秘技点的纯预置 / 位移秘技 |
| `point_cost=1, forces_battle_entry=true` | 白厄/刃/飞霄 进战技 |
| `point_cost=2, forces_battle_entry=false` | 部分强力预置秘技 |

**已确认的强制进战案例**：
- 白厄 (1408) 秘技「黎明焚身」
- 刃 (1205) 秘技「无间地狱」
- 飞霄 (1220) 秘技「天锋」

### 18.7 秘技点 (Technique Point)

**定位**：纯**战前预算**——所有秘技在战斗开始前施放，进战后秘技点不再参与任何计算。

**不在 `custom_resources` 里**：它没有 current/max/overflow/regen 这些战斗内语义。

**归属**：默认值在 `global/team_defaults.yaml`；角色模板可声明 `team_modifiers` 加成。

```yaml
# data/sim_templates/global/team_defaults.yaml
team_defaults:
  technique_point_initial: 5
  technique_point_max: 5
```

```yaml
# data/sim_templates/characters/1408_phainon.yaml 片段
team_modifiers:
  technique_point_initial_bonus: 3
  technique_point_max_bonus: 3
```

**Composer 计算**：

```
technique_point_initial = team_defaults.technique_point_initial
                        + Σ team.member.team_modifiers.technique_point_initial_bonus

technique_point_max     = team_defaults.technique_point_max
                        + Σ team.member.team_modifiers.technique_point_max_bonus
```

例：默认 initial=5 / max=5，队伍含 Phainon（各 +3）→ initial=8 / max=8。

**消耗规则**：
- 按 `technique_order` 顺序遍历，每个秘技扣对应 `point_cost`。
- 剩余 < `point_cost` 时按 `point_policy` 处理（见 `20_pre_battle_strategy.md`）。
- 不存在“溢出”或“回复”。

### 18.8 战技点 vs 秘技点

| 概念 | 中文 | 战斗内？ | 数据字段 |
|------|------|---------|---------|
| 战技点 | Skill Point (SP) | ✅ | `skill_point_cost` / `skill_point_gain` |
| 秘技点 | Technique Point (TP) | ❌ | `point_cost`（TechniqueDef） |

---
