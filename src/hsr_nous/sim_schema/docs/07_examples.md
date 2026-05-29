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
