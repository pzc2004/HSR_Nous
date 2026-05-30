## 15. 数据分离：游戏机制 vs 玩家配装

模拟器输入拆为两个独立文件，职责分离：

| 文件 | 内容 | 来源 | 变化频率 |
|------|------|------|---------|
| `game_config.yaml` | 游戏机制（公式、角色模板、敌人、关卡配置） | pipeline 自动生成 | 游戏版本更新时 |
| `build.yaml` | 玩家配装（队伍、等级、星魂、光锥、遗器、策略） | 玩家编写 / 优化器生成 | 每次调整配装时 |

### game_config.yaml — 游戏机制

```yaml
# ===== 公式定义 =====
formula:
  damage:
    expression: "abilityMulti * dmgBoostMulti * ..."
    parameters: [...]
  break_damage:
    expression: "..."
  # ... 其他公式

# ===== 角色模板（从 pipeline/characters.json 提取）=====
character_templates:
  "1001":
    name: "三月七"
    path: "preservation"
    element: "ice"
    max_energy: 120
    taunt: 150
    base_stats:             # 等级 1 基础值（不含光锥/遗器）
      hp: 957
      atk: 511
      def: 485
      spd: 101
      crit_rate: 0.05
      crit_dmg: 0.5
    actions:
      - action_id: "1001_basic"
        action_type: "basic"
        target_type: "enemy_single"
        damage_type: "ice"
        energy_gain: 20
        skill_point_gain: 1
        toughness_dmg: 10
        effects: [...]
      - action_id: "1001_skill"
        action_type: "skill"
        # ...
      - action_id: "1001_ultimate"
        action_type: "ultimate"
        # ...
    traces:
      - trace_id: "T_1001_1"
        effects: [...]
    eidolon_defs:
      - eidolon_id: "E_1001_1"
        effects: [...]
      # ... E2-E6

  "1002":
    name: "丹恒"
    # ...

# ===== 光锥模板 =====
light_cone_templates:
  "20001":
    name: "余生的第一天"
    # 等级 1 基础值（来自 light_cone_promotions.json）
    base_stats:
      hp: { base: 391.68, step: 5.76 }    # adapter 计算: base + step * (level - 1)
      atk: { base: 122.4, step: 1.8 }
      def: { base: 153.0, step: 2.25 }
    superimposition_effects:
      1: [...]
      2: [...]
      3: [...]
      4: [...]
      5: [...]

# ===== 遗器规则 =====
relic_rules:
  main_stats:
    head: { stat: "hp", base: 705.0 }
    hand: { stat: "atk", base: 352.0 }
    body: ["hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "heal_bonus", "effect_hit"]
    feet: ["hp_pct", "atk_pct", "def_pct", "spd"]
    sphere: ["hp_pct", "atk_pct", "def_pct", "physical_dmg", "fire_dmg", "ice_dmg", "thunder_dmg", "wind_dmg", "quantum_dmg", "imaginary_dmg"]
    rope: ["hp_pct", "atk_pct", "def_pct", "break_effect", "energy_regen"]
  sub_stats:
    hp: { base: 33.87, step: 33.87 }
    atk: { base: 16.93, step: 16.93 }
    def: { base: 16.93, step: 16.93 }
    hp_pct: { base: 0.034, step: 0.034 }
    atk_pct: { base: 0.034, step: 0.034 }
    def_pct: { base: 0.043, step: 0.043 }
    spd: { base: 2.0, step: 2.3 }
    crit_rate: { base: 0.026, step: 0.032 }
    crit_dmg: { base: 0.052, step: 0.064 }
    break_effect: { base: 0.052, step: 0.064 }
    effect_hit: { base: 0.034, step: 0.043 }
    effect_res: { base: 0.034, step: 0.043 }

  set_bonuses:
    "S_101":
      name: "猎人"
      2pc: { stat: "crit_rate", value: 0.08 }
      4pc: { trigger: "on_kill", effect: "advance_action", value: 20 }
    # ...

# ===== 敌人配置 =====
enemies:
  - actor_id: "M_8001"
    name: "银鬃近卫"
    level: 80
    base_stats: { hp: 50000, atk: 800, def: 500, spd: 120 }
    max_toughness: 100
    weakness: ["ice", "fire"]
    resistance: { physical: 0.2, ice: 0.0, fire: 0.0 }
    actions: [...]

# ===== 关卡配置 =====
waves:
  - wave_index: 1
    enemy_ids: ["M_8001", "M_8002", "M_8003"]
    enemy_levels: [80, 80, 80]

cycle:
  first_cycle_av: 150
  subsequent_cycle_av: 100

termination:
  mode: "fixed_av"
  max_action_value: 1500
  max_turns: 50
```

### build.yaml — 玩家配装

```yaml
team:
  - character_id: "1001"         # 引用 game_config.character_templates
    level: 80
    eidolons: 6                  # 解锁到 E6

    light_cone:
      id: "20001"                # 引用 game_config.light_cone_templates
      level: 80
      superimposition: 5

    relics:
      head:
        set_id: "S_101"
        # 主词条固定 hp，不需要指定
        # subs 用强化次数表示：{ stat: 次数 }
        subs:
          hp_pct: 2              # 强化 2 次
          atk_pct: 1
          crit_rate: 1
          crit_dmg: 0

      hand:
        set_id: "S_101"
        subs: { crit_rate: 2, crit_dmg: 1, spd: 1, atk_pct: 0 }

      body:
        set_id: "S_101"
        main: "crit_rate"        # 主词条选择
        subs: { crit_dmg: 3, spd: 1, hp_pct: 0, atk_pct: 0 }

      feet:
        set_id: "S_101"
        main: "spd"
        subs: { crit_rate: 2, crit_dmg: 1, hp_pct: 1, atk_pct: 0 }

      sphere:
        set_id: "S_102"
        main: "ice_dmg"
        subs: { crit_rate: 1, crit_dmg: 2, atk_pct: 1, hp_pct: 0 }

      rope:
        set_id: "S_102"
        main: "atk_pct"
        subs: { crit_rate: 1, crit_dmg: 2, spd: 1, hp_pct: 0 }

  - character_id: "1002"
    level: 80
    eidolons: 0
    light_cone: { id: "20002", superimposition: 1 }
    relics: { ... }

# 策略
policy:
  name: "auto_test"
  action_rules:
    - condition: "energy >= parameters.ULT_THRESHOLD"
      action: "ultimate"
      priority: 100
    - condition: "skill_points > 0"
      action: "skill"
      priority: 50
    - condition: "true"
      action: "basic"
      priority: 0
  parameters:
    ULT_THRESHOLD: 120
```

### 运行时合并流程

```
game_config.yaml ─┐
                   ├─→ merge() ─→ Encounter ─→ sim/
build.yaml ───────┘
```

**merge 逻辑**：
1. 从 `game_config` 加载公式、敌人、波次、轮次配置
2. 遍历 `build.team`，对每个角色：
   a. 从 `game_config.character_templates[character_id]` 查找游戏数据
   b. 根据 `level` 计算等级成长属性
   c. 从 `game_config.light_cone_templates[light_cone.id]` 查找光锥数据
   d. 根据 `light_cone.superimposition` 选择叠影效果
   e. 根据 `relics` 各部位的 `set_id`/`main`/`subs` 计算遗器属性
   f. 从 `game_config.relic_rules.set_bonuses` 查找套装效果
   g. 合并所有属性到 `base_stats`
   h. 组装 `actions`、`traces`（按 eidolons 筛选）、`light_cone.effects`
3. 组装完整 `Encounter`

### 遗器 subs 格式

`subs` 字段有两种表示方式：

```yaml
# 方式一：强化次数（推荐，紧凑）
subs:
  crit_rate: 3      # crit_rate 副词条强化了 3 次
  crit_dmg: 1
  spd: 0            # 初始有但没强化

# 方式二：最终值（精确）
subs:
  crit_rate: 0.104   # 最终值 10.4%
  crit_dmg: 0.064
  spd: 2.3
```

adapter 根据 `game_config.relic_rules.sub_stats` 的 `base` 和 `step` 将强化次数转换为最终值：
```
最终值 = base + step × 强化次数
```
