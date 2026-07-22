## 15. 数据分离：模板 / 玩家配装 / 关卡配置

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 15.1 架构变更

原 `game_config.yaml`（单文件合并所有游戏机制）已移除，替换为 **per-entity DSL 模板**目录：

```
data/sim_templates/
├── characters/{id}_{romanized_name}.yaml
├── light_cones/{id}.yaml
├── relics/{id}.yaml
├── enemies/{id}.yaml
├── stages/{stage_id}.yaml
└── global/
    ├── formulas.yaml
    ├── team_defaults.yaml
    └── timing_rules.yaml
```

运行时输入保留两个正交文件：
- `build.yaml`：玩家配装（4 角色 + 装备 + policy）
- `stage.yaml`：关卡配置（敌人/波次/轮次/结束条件）

**设计目的**：同一套配装可以快速切换不同关卡测试，同一关卡也可以快速切换不同配装对比。

### 15.2 文件类型对比

| 类型 | 路径 | 谁写 | 内容 | 格式 |
|------|------|------|------|------|
| **模板** | `data/sim_templates/**` | adapters 自动生成 | 游戏机制（实体 + 公式 + 关卡定义），不含玩家选择 | DSL（YAML） |
| **运行时实例** | `build.yaml` / `stage.yaml` | 玩家 / 优化器 / 自动生成 | 玩家选择（team / 装备 / 关卡选择 / policy） | YAML |

`build.yaml` 和 `stage.yaml` **不进 `data/sim_templates/`**——它们是“用哪份模板”的引用，不是模板本身。

### 15.3 `build.yaml` vs `stage.yaml` 边界

| 文件 | 独立维度 | 内容 |
|------|---------|------|
| `build.yaml` | **玩家配装** | 角色引用、光锥引用、遗器、星魂、技能等级、policy |
| `stage.yaml` | **关卡** | stage 模板引用 + 运行时覆盖（敌人等级、环境 buff 微调等） |

两个轴正交：同一 build 跨多 stage 测试，同一 stage 跨多 build 测试。

### 15.4 模板目录结构

```
data/sim_templates/
├── characters/
│   ├── 1001_march_7th.yaml
│   ├── 1005_kafka.yaml
│   ├── 1205_blade.yaml
│   ├── 1306_sparkle.yaml
│   ├── 1408_phainon.yaml
│   ├── 1409_hyacine.yaml
│   └── ...
├── light_cones/
│   ├── 20003.yaml
│   ├── 23042.yaml
│   └── ...
├── relics/
│   ├── 101.yaml
│   └── ...
├── enemies/
│   ├── 1002011.yaml
│   └── ...
├── stages/
│   ├── FH_12_1_upper.yaml
│   ├── PF_04_2.yaml
│   └── ...
└── global/
    ├── formulas.yaml
    ├── timing_rules.yaml
    └── team_defaults.yaml
```

文件命名约定：
- 角色模板：`{id}_{romanized_name}.yaml`（便于人眼查找）
- 其他实体：`{id}.yaml`（跟 raw ID 一一对应）
- `global/*.yaml`：语义命名

loader 启动时扫描全部文件并建内存索引，**key = 模板内容里的 entity ID**，文件名只影响人眼不影响查找。

### 15.5 运行时合并流程

```
StarRailRes (JSON)
    ↓
[pipeline.loader] → raw_schema
    ↓
[adapters.generate_templates] → data/sim_templates/**/*.yaml
    ↓
[sim.loader.build_template_index] → 内存模板索引
    ↓
[sim.resolver.resolve_variables]  (按 build.yaml 查表)
    ↓
[sim.resolver.bind_template]      (替换 $self.xxx 为具体值)
    ↓
Encounter（运行时完整输入）
    ↓
[sim.engine.run] → 仿真结果
```

### 15.6 `variable_bindings` 解析

每个模板自带 `variable_bindings` 字段，描述“从 build config 求值该实体变量”的过程：

```yaml
# data/sim_templates/characters/1409_hyacine.yaml
actor_id: "1409"
name: "hyacine"
path: "remembrance"
damage_type: "wind"

lookup_tables:
  base_hp_by_level:        [1200, 1300, 1400]
  base_atk_by_level:       [ 400,  450,  500]
  skill_1140901_clear_ratio:  [0.50, 0.50, 0.50]
  skill_1140901_damage_ratio: [0.50, 0.55, 0.60]

variable_bindings:
  - self.base_hp      = lookup_table("base_hp_by_level",      index=$build.level - 1)
  - self.base_atk     = lookup_table("base_atk_by_level",     index=$build.level - 1)
  - self.clear_ratio  = lookup_table("skill_1140901_clear_ratio",  index=$build.skill_levels.skill - 1)
  - self.damage_ratio = lookup_table("skill_1140901_damage_ratio", index=$build.skill_levels.skill - 1)
  - if $build.eidolon >= 6:
      self.clear_ratio = 0.12
```

当前支持的原语：
- `lookup_table(name, index)`：查本模板内嵌的 `lookup_tables[name][index]`
- `if <condition>: <assign>`：星魂/行迹等条件覆盖

完整 BNF 语法 TBD。

### 15.7 全局公式配置

```yaml
# data/sim_templates/global/formulas.yaml
formulas:
  damage:
    expression: |
      ability_multiplier * dmg_boost_multi * ind_dmg_boost_multi *
      def_multi * res_multi * base_universal_multi *
      vuln_multi * ind_vuln_multi * final_dmg_multi *
      crit_multi * weaken_multi * dmg_red_multi
    parameters:
      - name: def_multi
        expression: "(attacker_level * 10 + 200) / (target_def * max(0, 1 - def_pen) + attacker_level * 10 + 200)"
      - name: res_multi
        expression: "1 - clamp(target_res - res_pen, -1.0, 0.9)"
      - name: crit_multi
        expression: "(random() < crit_rate) ? (1 + crit_dmg) : 1.0"

  break_damage:
    expression: "break_base_multi * be_multi * break_dmg_boost_multi * base_universal_multi * def_multi * res_multi * vuln_multi * final_dmg_multi * dmg_red_multi"
    parameters:
      - name: break_base_multi
        expression: "3767.5533 * elemental_break_scaling * (0.5 + max_toughness / 40) * special_scaling"
      - name: be_multi
        expression: "1 + break_effect"
      - name: break_dmg_boost_multi
        expression: "1 + break_dmg_boost"
```

全局公式 DSL 允许比 effect 表达式更复杂的数学函数（如 `clamp`、`random`），但仍限制在白名单内，禁止文件 I/O、网络、任意 Python 语法。

### 15.8 `build.yaml` 示例

```yaml
build:
  team:
    - character_template: "1409"     # 引用 data/sim_templates/characters/1409_hyacine.yaml
      level: 80
      eidolon: 0                     # 玩家解锁的星魂数量（对应角色模板中的 `eidolons` 列表）
      skill_levels:
        basic: 1
        skill: 10
        ultimate: 10
        talent: 10

      light_cone_template: "23042"   # 引用 data/sim_templates/light_cones/23042.yaml
      light_cone:
        level: 80
        superimposition: 1

      relics:
        head:  { set_id: "101", main: "hp",  subs: { spd: 2, atk: 1 } }
        hand:  { set_id: "101", main: "atk", subs: { crit_rate: 2, crit_dmg: 1 } }
        body:  { set_id: "101", main: "heal_bonus", subs: { spd: 2, hp_pct: 1 } }
        feet:  { set_id: "101", main: "spd", subs: { hp_pct: 2, def_pct: 1 } }
        sphere: { set_id: "101", main: "wind_dmg", subs: { atk_pct: 2, spd: 1 } }
        rope:  { set_id: "101", main: "energy_regen", subs: { atk_pct: 2, hp_pct: 1 } }

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

### 15.9 `stage.yaml` 示例

```yaml
stage:
  stage_template: "FH_12_1_upper"    # 引用 data/sim_templates/stages/FH_12_1_upper.yaml

  # 运行时覆盖
  enemy_level_overrides:
    "1002011": 95
    "1002012": 95

  environment_overrides:
    modifiers: []
```

### 15.10 Stage 模板示例

```yaml
# data/sim_templates/stages/FH_12_1_upper.yaml
stage_id: "FH_12_1_upper"
name: "忘却之庭 第12层 上半"
mode: "forgotten_hall"

enemies:
  - enemy_template: "1002011"
    level: 95
  - enemy_template: "1002012"
    level: 95

waves:
  - wave_index: 1
    enemy_ids: ["1002011", "1002012"]
    enemy_levels: [95, 95]
  - wave_index: 2
    enemy_ids: ["1002020"]
    enemy_levels: [95]

cycle:
  first_cycle_av: 150
  subsequent_cycle_av: 100

termination:
  mode: "fixed_av"
  max_action_value: 1500
```

### 15.11 玩法模式参考

| 模式 | mode 值 | 首轮 AV | 后续 AV | 特殊规则 |
|------|---------|---------|---------|---------|
| 忘却之庭 | `forgotten_hall` | 150 | 100 | 转波次重置 AV |
| 虚构叙事 | `pure_fiction` | 150 | 100 | 击杀回能 5（非 10） |
| 末日幻影 | `apocalyptic_shadow` | 300 | 100 | — |
| 异相仲裁 | `anomaly_arbitration` | 300 | 100 | Lv.120 敌人额外 +10% EHR/效果抗性 |

### 15.12 为什么把查表内嵌

- **模板自包含**：sim 加载即跑，不依赖 `data/starrailres/` 或 pipeline
- **显式快照**：`hsr-data-update` 后必须重跑 preprocessing 才能看到新数值（避免静默用过期数据）
- **per-build 缓存**：同 build 多次模拟时只构造一次绑定后对象

### 15.13 TBD

- `variable_bindings` 完整 BNF 语法（TBD）。
- 模板实例化结果的内容寻址缓存策略。
- build.yaml 中遗器 subs 的两种表示方式（强化次数 vs 最终值）是否都保留。

---
