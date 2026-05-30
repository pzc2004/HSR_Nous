## 15. 数据分离：游戏机制 / 玩家配装 / 关卡配置

模拟器输入拆为三个独立文件，职责分离：

| 文件 | 内容 | 来源 | 变化频率 |
|------|------|------|---------|
| `game_config.yaml` | 游戏机制（公式、角色模板、光锥模板、遗器规则） | adapters 从 raw_schema 生成 | 游戏版本更新时 |
| `build.yaml` | 玩家配装（队伍、等级、星魂、光锥、遗器、策略） | 玩家编写 / 优化器生成 | 每次调整配装时 |
| `stage.yaml` | 关卡配置（敌人、波次、玩法模式、轮次、结束条件） | 玩家选择 / 自动生成 | 每次换关卡时 |

**设计目的**：同一套配装可以快速切换不同关卡测试，同一关卡也可以快速切换不同配装对比。

---

### game_config.yaml — 游戏机制

所有输入共用，由 pipeline 从 StarRailRes + Fandom wiki 自动生成。

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
    base_stats:
      hp: { base: 489.6, step: 7.2 }     # adapter 计算: base + step * (level - 1)
      atk: { base: 236.64, step: 3.48 }
      def: { base: 265.2, step: 3.9 }
      spd: 101
      crit_rate: 0.05
      crit_dmg: 0.5
    trace_stats:
      ice_dmg: 0.224
      def_pct: 0.225
      effect_res: 0.10
    actions: [...]
    traces: [...]
    eidolon_defs: [...]

  "1002":
    name: "丹恒"
    # ...

# ===== 光锥模板 =====
light_cone_templates:
  "20003":
    name: "琥珀"
    base_stats:
      hp: { base: 391.68, step: 5.76 }
      atk: { base: 122.4, step: 1.8 }
      def: { base: 153.0, step: 2.25 }
    superimposition:
      1: { def_pct: 0.16, def_pct_conditional: 0.16, hp_threshold: 0.50 }
      # ...

# ===== 遗器规则 =====
relic_rules:
  main_stats:
    head: { stat: "hp", base: 705.0 }
    hand: { stat: "atk", base: 352.0 }
    body: ["hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "heal_bonus", "effect_hit"]
    feet: ["hp_pct", "atk_pct", "def_pct", "spd"]
    sphere: ["hp_pct", "atk_pct", "def_pct", "physical_dmg", "fire_dmg", "ice_dmg", ...]
    rope: ["hp_pct", "atk_pct", "def_pct", "break_effect", "energy_regen"]
  sub_stats:
    crit_rate: { base: 0.026, step: 0.032 }
    # ...
  set_bonuses:
    "103":
      name: "Knight of Purity Palace"
      2pc: [{ type: "DefenceAddedRatio", value: 0.15 }]
      4pc: [{ type: "shield_bonus", value: 0.20 }]
```

---

### build.yaml — 玩家配装

玩家编写或优化器生成，只包含玩家选择。

```yaml
team:
  - character_id: "1001"         # 引用 game_config.character_templates
    level: 80
    eidolons: 6

    light_cone:
      id: "20003"                # 引用 game_config.light_cone_templates
      level: 80
      superimposition: 5

    relics:
      head:
        set_id: "103"
        subs: { def_pct: 3, hp_pct: 1, spd: 0, effect_hit: 0 }
      hand:
        set_id: "103"
        subs: { def_pct: 2, hp_pct: 2, spd: 0, effect_hit: 0 }
      body:
        set_id: "103"
        main: "def_pct"
        subs: { spd: 2, hp_pct: 1, effect_hit: 1, def_pct: 0 }
      feet:
        set_id: "103"
        main: "spd"
        subs: { def_pct: 2, hp_pct: 1, effect_hit: 1, spd: 0 }
      sphere:
        set_id: "103"
        main: "ice_dmg"
        subs: { def_pct: 2, spd: 1, hp_pct: 1, effect_hit: 0 }
      rope:
        set_id: "103"
        main: "def_pct"
        subs: { spd: 2, hp_pct: 1, effect_hit: 1, def_pct: 0 }

  # - character_id: "1002"
  #   ...

policy:
  name: "march_7th_default"
  action_rules:
    - condition: "skill_points > 0 && ally_without_shield"
      action: "skill"
      priority: 100
    - condition: "energy >= 120"
      action: "ultimate"
      priority: 90
    - condition: "true"
      action: "basic"
      priority: 0
  target_rules: [...]
  parameters: {}
```

---

### stage.yaml — 关卡配置

描述战斗场景，独立于配装。同一配装可套用不同关卡配置。

```yaml
# ===== 关卡元信息 =====
stage_id: "FH_12_1"
name: "忘却之庭 第12层 上半"
mode: "forgotten_hall"           # forgotten_hall | pure_fiction | apocalyptic_shadow | divergent_universe

# ===== 敌人模板（引用 game_config 中的数据，补充关卡特定属性）=====
enemies:
  - enemy_id: "1002011"          # 引用 game_config 或直接定义
    name: "冰锋"
    level: 95
    base_stats: { hp: 150000, atk: 1200, def: 600, spd: 100 }
    max_toughness: 100
    weakness: ["fire", "thunder"]
    resistance: { physical: 0.2, fire: 0.0, ice: 0.2, thunder: 0.0, wind: 0.2, quantum: 0.2, imaginary: 0.2 }
    actions: [...]

  - enemy_id: "1002012"
    name: "冰锋"
    level: 95
    # ...

# ===== 波次配置 =====
waves:
  - wave_index: 1
    enemy_instances:
      - enemy_id: "1002011"
      - enemy_id: "1002012"
      - enemy_id: "1002013"
    on_wave_start: []

  - wave_index: 2
    enemy_instances:
      - enemy_id: "1002020"
      - enemy_id: "1002021"
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_2"
        target: "all_allies"

# ===== 轮次配置（按玩法模式）=====
cycle:
  first_cycle_av: 150            # 忘却之庭首轮 150 AV
  subsequent_cycle_av: 100       # 后续 100 AV
  # 异相仲裁: first_cycle_av: 300

# ===== 结束条件 =====
termination:
  mode: "fixed_av"               # fixed_av | kill_target | survival | wipe
  max_action_value: 1500
  max_turns: 50

# ===== 环境效果 =====
environment:
  modifiers: []
  # 忘却之庭当期环境 buff、异相仲裁中盘激战等
```

**玩法模式参考**：

| 模式 | mode 值 | 首轮 AV | 后续 AV | 特殊规则 |
|------|---------|---------|---------|---------|
| 忘却之庭 | `forgotten_hall` | 150 | 100 | 转波次重置 AV |
| 虚构叙事 | `pure_fiction` | 150 | 100 | 击杀回能 5（非 10） |
| 末日幻影 | `apocalyptic_shadow` | 300 | 100 | — |
| 异相仲裁 | `divergent_universe` | 300 | 100 | Lv.120 敌人额外 +10% EHR/效果抗性 |

---

### 运行时合并流程

```
game_config.yaml ─┐
build.yaml ───────┼─→ merge() ─→ Encounter ─→ sim/
stage.yaml ───────┘
```

**merge 逻辑**：
1. 从 `game_config` 加载公式、角色模板、光锥模板、遗器规则
2. 从 `stage` 加载敌人、波次、轮次、结束条件、环境效果
3. 遍历 `build.team`，对每个角色：
   a. 从 `game_config.character_templates[character_id]` 查找游戏数据
   b. 根据 `level` 计算等级成长属性
   c. 从 `game_config.light_cone_templates[light_cone.id]` 查找光锥数据
   d. 根据 `light_cone.superimposition` 选择叠影效果
   e. 根据 `relics` 各部位的 `set_id`/`main`/`subs` 计算遗器属性
   f. 从 `game_config.relic_rules.set_bonuses` 查找套装效果
   g. 合并所有属性到 `base_stats`
   h. 组装 `actions`、`traces`（按 eidolons 筛选）、`light_cone.effects`
4. 组装完整 `Encounter`

---

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
