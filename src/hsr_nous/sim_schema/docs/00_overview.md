# Sim Schema 仿真器输入格式

本文档定义战斗模拟器的完整输入数据结构。核心设计原则：**一切机制都抽象为"事件-响应"模型**。

## 设计哲学

- **技能、行迹、星魂、光锥、遗器**：本质都是**事件监听器**——在特定时机触发效果
- **buff/debuff**：也是事件监听器——在持续期间内响应特定事件
- **伤害公式**：参数化配置，默认使用崩铁标准公式，支持自定义
- **纯数据驱动**：所有机制用 JSON/YAML 描述，不写硬编码逻辑

---

## 数据流概览

```
Encounter（关卡配置）
├── globals（全局状态：行动值、战技点、随机种子）
├── formula（伤害公式定义）
├── actors[]（参战单位）
│   ├── [角色] base_stats / actions[] / traces[] / eidolons[] / light_cone / relics[]
│   └── [敌人] base_stats / weakness / resistance / max_toughness / actions[]
├── waves[]（波次配置）
│   ├── wave_index / enemy_ids / enemy_levels
│   └── on_wave_start[]（转波次触发的效果）
├── cycle（轮次 AV 配置）
│   ├── first_cycle_av / subsequent_cycle_av
│   └── on_cycle_start[] / on_cycle_end[]
└── modifiers[]（初始 buff，如环境效果）

数据来源：
├── 角色数据 ← pipeline → raw_schema (Character/LightCone/Relic)
└── 敌人数据 ← pipeline → raw_schema (Enemy) + 关卡配置(base_stats/toughness)
```

### 波次机制

波次定义战斗中的敌人分组。当一个波次的所有敌人被击败后，下一个波次的敌人登场。

```yaml
waves:
  - wave_index: 1
    enemy_ids: ["1002011", "1002012", "1002013"]
    enemy_levels: [80, 80, 80]
    # 新敌人登场时触发的效果
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_1"
        target: "all_allies"
        description: "忘却之庭环境 buff"

  - wave_index: 2
    enemy_ids: ["1002020", "1002021"]
    enemy_levels: [80, 80]
    on_wave_start:
      - effect_type: "apply_modifier"
        modifier_id: "MOD_ENV_BUFF_2"
        target: "all_allies"
```

**波次触发时机**：
- `on_wave_start`：新波次敌人登场时触发
- 可用于：环境 buff、波次奖励、难度变化等
- 忘却之庭特殊机制：转波次会清空当前轮次 AV（重置为 150），所有角色和敌人重新计算行动值

---

### 轮次机制

轮次是 AV（行动值）循环机制，与角色的回合(Turn)是不同概念。每个轮次有固定的 AV 预算，当累计行动值消耗达到预算时进入下一轮次。不同玩法模式有不同的 AV 配置。

详见 `docs/mechanics/action_sequence.md`。

```yaml
cycle:
  first_cycle_av: 150        # 忘却之庭首轮 150 AV（异相仲裁 300）
  subsequent_cycle_av: 100   # 后续轮次 100 AV
  on_cycle_start:
    - effect_type: "apply_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
      description: "忘却之庭当期环境 buff"
  on_cycle_end:
    - effect_type: "remove_modifier"
      modifier_id: "MOD_ENV_BUFF"
      target: "all_allies"
```

**轮次触发时机**：
- `on_cycle_start`：新轮次开始时触发，通常用于环境 buff
- `on_cycle_end`：轮次结束时触发
- 忘却之庭：每轮次开始触发当期环境 buff
- 异相仲裁：每过一定轮次增加角色伤害（如第 3 轮开始每轮给所有角色加一层"中盘激战"：每层 +50% 最终伤害）

**轮次与回合的区别**：
- **回合 (Turn)**：角色/敌人的单次行动，由速度决定行动顺序
- **轮次 (Cycle)**：AV 循环周期，独立于速度，不能被推拉条影响

---

