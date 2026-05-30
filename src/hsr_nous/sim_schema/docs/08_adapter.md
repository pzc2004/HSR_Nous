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

**弱点/抗性映射注意**：
- 弱点属性默认 **0%** 抗性，非弱点属性默认 **20%** 抗性
- 弱点和抗性是**独立字段**——添加弱点不会自动降低抗性
- adapter 需确保未在 `resistance` 中显式指定的属性有正确默认值

**韧性保护**：部分敌人有韧性保护（弱点图标锁定），此时任何攻击无法削减韧性。

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
