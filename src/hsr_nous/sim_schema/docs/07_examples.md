## 7. 完整输入示例

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 7.1 角色模板示例

```yaml
# data/sim_templates/characters/1409_hyacine.yaml
actor_id: "1409"
name: "hyacine"
path: "remembrance"
damage_type: "wind"

lookup_tables:
  base_hp_by_level:        [1200, 1300, 1400, 1500, 1600]
  base_atk_by_level:       [ 400,  450,  500,  550,  600]
  basic_scaling:           [0.50, 0.55, 0.60, 0.65, 0.70]
  ultimate_heal_pct:       [0.10, 0.11, 0.12, 0.13, 0.14]
  ultimate_heal_base:      [100, 120, 140, 160, 180]
  skill_1140901_clear_ratio:  [0.50, 0.50, 0.50, 0.50, 0.50]
  skill_1140901_damage_ratio: [0.50, 0.55, 0.60, 0.65, 0.70]
  memps_drain_pct:         [0.05, 0.05, 0.05, 0.05, 0.05]

variable_bindings:
  - self.base_hp      = lookup_table("base_hp_by_level",      index=$build.level - 1)
  - self.base_atk     = lookup_table("base_atk_by_level",     index=$build.level - 1)
  - self.basic_scaling   = lookup_table("basic_scaling",       index=$build.skill_levels.basic - 1)
  - self.ultimate_heal_pct  = lookup_table("ultimate_heal_pct",  index=$build.skill_levels.ultimate - 1)
  - self.ultimate_heal_base = lookup_table("ultimate_heal_base", index=$build.skill_levels.ultimate - 1)
  - self.clear_ratio  = lookup_table("skill_1140901_clear_ratio",  index=$build.skill_levels.skill - 1)
  - self.damage_ratio = lookup_table("skill_1140901_damage_ratio", index=$build.skill_levels.skill - 1)
  - self.memps_drain_pct = lookup_table("memps_drain_pct", index=$build.skill_levels.talent - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12

custom_resources:
  hyacine_cumulative_heal:
    max: 999999
    owner: "actor"
    scope: "actor"

actions:
  - action_id: "140901"
    name: "普通攻击"
    action_type: "basic"
    target_type: "enemy_single"
    damage_type: "wind"
    energy_gain: 20
    skill_point_gain: 1
    effects:
      - trigger: "on_cast"
        target: "primary_target"
        effect_type: "deal_damage"
        formula: "damage"
        amount: "$self.atk * $self.basic_scaling"

  - action_id: "1140901"
    name: "忆灵技"
    action_type: "memosprite_skill"
    effects:
      - effect_type: "deal_damage"
        target: "all_enemies"
        amount: "$resource.hyacine_cumulative_heal * $self.damage_ratio"
      - effect_type: "consume_resource"
        resource_id: "hyacine_cumulative_heal"
        amount: "ratio:$self.clear_ratio"

  - action_id: "140903"
    name: "终结技"
    action_type: "ultimate"
    target_type: "ally_aoe"
    energy_cost: 120
    effects:
      - trigger: "on_cast"
        target: "all_allies"
        effect_type: "heal"
        formula: "heal"
        amount: "$self.max_hp * $self.ultimate_heal_pct + $self.ultimate_heal_base"

hooks:
  # 事件 hook 示例：风堇小伊卡天赋（累积模式）
  # 完整语义见 23_event_hook_system.md
  - event: "on_hp_decrease"
    scope: "team"
    condition: "$event.target != $self.memosprite"
    accumulated: true
    flush_triggers: ["on_turn_start", "on_after_action"]
    effects:
      - effect_type: "drain_hp"
        target: "$self.memosprite"
        amount: "$self.memosprite.max_hp * $self.memps_drain_pct"
        drain_ratio: 1.0
        heal_target: "$event.targets"
```

### 7.2 光锥模板示例

```yaml
# data/sim_templates/light_cones/23042.yaml
light_cone_id: "23042"
name: "愿虹光永驻天空"

lookup_tables:
  speed_pct:          [0.180, 0.225, 0.270, 0.315, 0.360]
  consume_pct:        [0.010, 0.0125, 0.015, 0.0175, 0.020]
  vulnerability_pct:  [0.180, 0.225, 0.270, 0.315, 0.360]
  vulnerability_duration: [2, 2, 2, 2, 2]
  multiplier:         [2.500, 3.125, 3.750, 4.375, 5.000]

variable_bindings:
  - self.speed_pct          = lookup_table("speed_pct",          index=$build.light_cone.superimposition - 1)
  - self.consume_pct        = lookup_table("consume_pct",        index=$build.light_cone.superimposition - 1)
  - self.vulnerability_pct      = lookup_table("vulnerability_pct",      index=$build.light_cone.superimposition - 1)
  - self.vulnerability_duration = lookup_table("vulnerability_duration", index=$build.light_cone.superimposition - 1)
  - self.multiplier         = lookup_table("multiplier",         index=$build.light_cone.superimposition - 1)

custom_resources:
  lc23042_hp_consumed:
    max: 999999
    owner: "light_cone"
    scope: "actor"

effects:
  - trigger: "on_battle_start"
    effect_type: "apply_modifier"
    target: "self"
    modifier:
      modifier_id: "MOD_LC_23042_SPD"
      modifier_type: "buff"
      stat: "spd"
      flat_bonus: "$self.speed_pct"
      duration: 0
  - trigger: "on_after_action"
    effect_type: "drain_hp"
    target: "team_allies"
    amount: "ratio:$self.consume_pct"
    drain_ratio: 0
    into_resource: "lc23042_hp_consumed"
  - trigger: "on_memosprite_attack"
    effect_type: "deal_damage"
    target: "primary_target"
    amount: "$resource.lc23042_hp_consumed * $self.multiplier"
  - trigger: "on_memosprite_skill"
    effect_type: "apply_modifier"
    target: "all_enemies"
    modifier:
      modifier_id: "MOD_LC_23042_VULNERABILITY"
      modifier_type: "debuff"
      stat: "vulnerability"
      flat_bonus: "$self.vulnerability_pct"
      duration: "$self.vulnerability_duration"
```

### 7.3 `build.yaml` 示例

```yaml
build:
  team:
    - character_template: "1409"
      level: 80
      eidolon: 0                     # 玩家解锁的星魂数量
      skill_levels:
        basic: 1
        skill: 10
        ultimate: 10
        talent: 10

      light_cone_template: "23042"
      light_cone:
        level: 80
        superimposition: 1

      relics:
        head:   { set_id: "101", main: "hp",         subs: { spd: 2, atk: 1 } }
        hand:   { set_id: "101", main: "atk",        subs: { crit_rate: 2, crit_dmg: 1 } }
        body:   { set_id: "101", main: "heal_bonus", subs: { spd: 2, hp_pct: 1 } }
        feet:   { set_id: "101", main: "spd",        subs: { hp_pct: 2, def_pct: 1 } }
        sphere: { set_id: "101", main: "wind_dmg",   subs: { atk_pct: 2, spd: 1 } }
        rope:   { set_id: "101", main: "energy_regen", subs: { atk_pct: 2, hp_pct: 1 } }

  pre_battle_strategy:
    name: "hyacine_first"
    technique_order:
      - "hyacine_memosprite_pre_summon"
      - "kafka_technique"
    entry_attacker: "1409"
    point_policy: "auto"

  policy:
    name: "hyacine_default"
    action_rules:
      - condition: "energy >= max_energy"
        action: "ultimate"
        priority: 100
      - condition: "skill_points > 0"
        action: "skill"
        priority: 50
      - condition: "true"
        action: "basic"
        priority: 0
```

### 7.4 `stage.yaml` 示例

```yaml
stage:
  stage_template: "FH_12_1_upper"

  enemy_level_overrides:
    "1002011": 95
    "1002012": 95

  environment_overrides:
    modifiers: []
```

### 7.5 运行时 Encounter 结构

```yaml
encounter:
  encounter_id: "E_001"
  name: "测试关卡"
  formula: { ... }            # 来自 data/sim_templates/global/formulas.yaml
  globals: { ... }
  actors: [ ... ]             # 绑定后的角色 + 敌人
  waves: [ ... ]
  cycle: { ... }
  termination: { ... }
  pre_battle_strategy: { ... }
  policy: { ... }             # 策略配置，见 14_policy.md
  initial_modifiers: []
```

---
