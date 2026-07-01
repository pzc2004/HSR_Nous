## 3. 参战单位 (Actor)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Actor 分为角色、怪物和召唤物，共用同一套结构。

```yaml
actor:
  actor_id: "1001"
  name: "三月七"
  actor_type: "character"    # character | monster | summon（monster 即敌人/enemy，schema 枚举值保留 monster）
  path: "preservation"
  damage_type: "ice"
  level: 80

  # ========== 基础属性（Layer 1）==========
  base_stats:
    hp: 1047
    max_hp: 1047
    atk: 564
    def: 485
    spd: 101

    crit_rate: 0.05
    crit_dmg: 0.50

    break_effect: 0.0
    break_efficiency_boost: 0.0   # 击破效率提升
    weakness_break_efficiency_boost: 0.0  # 弱点击破效率提升
    fixed_toughness_dmg: 0.0      # 固定削韧值（不受效率加成影响）

    effect_hit: 0.0
    effect_res: 0.0
    effect_res_pen: 0.0          # 效果抗性穿透（作用于目标 effect_res）

    def_pen: 0.0                 # 防御穿透 / 防御降低汇总值
    res_pen: 0.0                 # 抗性穿透

    vulnerability: 0.0           # 易伤
    ind_vulnerability: 0.0       # 独立易伤
    final_dmg_bonus: 0.0         # 最终伤害加成
    dmg_reduction: 0.0           # 减伤（已汇总为乘积结果）
    weaken: 0.0                  # 虚弱
    dmg_mitigation: 0.0          # 伤害减免（欢愉公式用）

    max_energy: 120
    energy: 0
    energy_regen: 1.0

    heal_bonus: 0.0
    shield_bonus: 0.0
    incoming_heal: 0.0            # 受治疗加成

    # 增伤相关（公式层会解析为标量）
    # DSL/Modifier 层统一用 all_dmg_bonus / elemental_dmg_bonus / type_dmg_bonus / ind_dmg_bonus 作为 stat
    # dmg_bonus 字典是适配层/内部存储，最终汇总到上述标量字段
    all_dmg_bonus: 0.0            # 通用增伤（对应 dmg_bonus.all）
    elemental_dmg_bonus: 0.0      # 当前伤害属性对应的属性增伤（从 dmg_bonus[element] 解析）
    type_dmg_bonus: 0.0           # 当前 action_type 对应的技能类型增伤（从 dmg_bonus_by_type 解析）
    ind_dmg_bonus: 0.0            # 独立增伤

    dmg_bonus:
      all: 0.0
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    resistance:
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    weakness: ["ice", "wind"]

    taunt: 150

    # 欢愉度（StatBlock 面板属性，不是 custom_resource）
    elation: 0.0

    max_toughness: 100
    toughness: 100
    broken: false                 # toughness == 0 时为 true

    dmg_bonus_by_type:
      basic: 0.0
      skill: 0.0
      ultimate: 0.0
      follow_up: 0.0
      dot: 0.0
      elation: 0.0

  elation_number: 0             # 欢愉编号（Actor 级整型字段，不在 base_stats 内）

  # ========== 自定义资源容器 ==========
  custom_resources:
    punchline:
      max: 999999
      owner: "actor"
      scope: "team"

  # ========== 形态状态机 ==========
  actor_state: "normal"
  state_config: null

  # ========== 秘技 ==========
  techniques:
    - technique_id: "march_7th_technique"
      actor_id: "1001"
      point_cost: 1
      forces_battle_entry: false
      effects:
        - effect_type: "apply_modifier"
          target: "enemy_single"
          modifier:
            modifier_id: "frozen"
            duration: 1

  # ========== 队伍级修正 ==========
  team_modifiers:
    technique_point_initial_bonus: 0
    technique_point_max_bonus: 0

  # ========== 模板内嵌查表与变量绑定 ==========
  lookup_tables:
    base_hp_by_level: [1200, 1300, 1400]
    basic_scaling:    [0.50, 0.55, 0.60]
    ultimate_scaling: [2.00, 2.10, 2.20]

  variable_bindings:
    - self.base_hp         = lookup_table("base_hp_by_level", index=$build.level - 1)
    - self.basic_scaling   = lookup_table("basic_scaling",    index=$build.skill_levels.basic - 1)
    - self.ultimate_scaling = lookup_table("ultimate_scaling", index=$build.skill_levels.ultimate - 1)

  # ========== 技能 ==========
  actions:
    - action_id: "1001_basic"
      name: "寒冰之箭"
      action_type: "basic"
      target_type: "enemy_single"
      damage_type: "ice"
      energy_gain: 20
      skill_point_gain: 1
      toughness_dmg: 10
      effects:
        - trigger: "on_cast"
          target: "primary_target"
          effect_type: "deal_damage"
          formula: "damage"
          amount: "$self.atk * $self.basic_scaling"
        - trigger: "on_cast"
          target: "self"
          effect_type: "gain_energy"
          amount: 20

    - action_id: "1001_skill"
      name: "可爱即是正义"
      action_type: "skill"
      target_type: "ally_single"
      skill_point_cost: 1
      toughness_dmg: 20
      effects:
        - trigger: "on_cast"
          target: "primary_target"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_SHIELD"
          duration: 3

    - action_id: "1001_ultimate"
      name: "冰刻剑雨之时"
      action_type: "ultimate"
      target_type: "enemy_aoe"
      energy_cost: 120
      toughness_dmg: 30
      effects:
        - trigger: "on_cast"
          target: "all_enemies"
          effect_type: "deal_damage"
          formula: "damage"
          amount: "$self.atk * $self.ultimate_scaling"
        - trigger: "on_cast"
          target: "random_enemy"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_FREEZE"
          duration: 1
          chance: 0.5

  # ========== 行迹（被动能力）==========
  traces:
    - trace_id: "T_1001_1"
      name: "公主殿下"
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_TRACE_CRIT"
          duration: 0

  # ========== 星魂 ==========
  # 注意：这是模板内星魂定义列表（全部可能星魂的元数据）。
  #       build.yaml 中的 `eidolon`（单数）是玩家解锁数量，运行时按序号启用前 N 个。
  eidolons:
    - eidolon_id: "E_1001_1"
      name: "记忆中的你"
      effects:
        - trigger: "on_shield_apply"
          condition: "$event.modifier_id == \"MOD_1001_SHIELD\""
          target: "$event.target"
          effect_type: "heal"
          formula: "heal"
          amount: "$self.max_hp * 0.3"

  # ========== 光锥 ==========
  light_cone:
    light_cone_id: "20001"
    name: "余生的第一天"
    superimposition: 1
    effects:
      - trigger: "on_battle_start"
        target: "self"
        effect_type: "apply_modifier"
        modifier_id: "MOD_LC_20001_DEF"
        duration: 0
      - trigger: "on_battle_start"
        target: "all_allies"
        effect_type: "apply_modifier"
        modifier_id: "MOD_LC_20001_RES"
        duration: 0

  # ========== 遗器 ==========
  # 注意：以下展示的是完整 relic 实例（含主/副词条数值）。
  #       在 build.yaml 中玩家只声明 `main: "hp"` 和副词条强化次数，具体数值由模板/计算决定。
  relics:
    - relic_id: "R_101_1"
      set_id: "S_101"
      slot: "head"
      main_stat: {stat: "hp", value: 705.0}
      sub_stats:
        - {stat: "atk", value: 42.0}
        - {stat: "spd", value: 4.0}
    - relic_id: "R_101_2"
      set_id: "S_101"
      slot: "hand"
      main_stat: {stat: "atk", value: 352.0}
      sub_stats:
        - {stat: "crit_rate", value: 0.06}
        - {stat: "crit_dmg", value: 0.08}

  relic_set_effects:
    - set_id: "S_101"
      pieces: 4
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_SET_101_4P"
          duration: 0
```

### 3.1 新增字段说明

| 字段 | 类型 | 说明 | 详见 |
|------|------|------|------|
| `custom_resources` | `Dict[str, ResourceBlock]` | 战斗内可累积/消耗的资源 | `16_custom_resources.md` |
| `actor_state` | `ActorState` | 当前形态 | `17_actor_state.md` |
| `state_config` | `StateConfig?` | 当前形态配置 | `17_actor_state.md` |
| `techniques` | `List[TechniqueDef]` | 战前可施放的秘技 | `18_technique_system.md` |
| `team_modifiers` | `dict` | 角色在队时给全队加的修正（如秘技点上限） | `18_technique_system.md` |
| `lookup_tables` | `Dict[str, List[float]]` | 模板内嵌数值表 | `15_data_separation.md` |
| `variable_bindings` | `List[str]` | 按 build 查表/覆盖变量 | `15_data_separation.md` |
| `owner_id` | `str?` | 召唤者 actor_id（仅 `actor_type: "summon"`） | `12_summon.md` |
| `behavior` | `SummonBehavior?` | 召唤物行为模式（仅 `actor_type: "summon"`） | `12_summon.md` |
| `special_mechanics` | `List[MechanicDef]?` | 召唤物/忆灵特有机制描述 | `12_summon.md` |
| `relic_set_effects` | `List[Effect]` | 已激活遗器套装效果 | `06_relics.md` |

### 3.2 增伤乘区拆分

```
dmg_boost_multi = 1 + all_dmg_bonus + elemental_dmg_bonus + type_dmg_bonus
```

`type_dmg_bonus` 根据当前技能的 `action_type` 从 `dmg_bonus_by_type` 取值。

### 3.3 属性计算公式

```
白值 = 角色基础值 + 光锥基础值
最终值 = 白值 × (1 + 百分比加成%) + 固定值加成
```

详见 `04_modifier.md` §4.9 两层属性模型。

### 3.4 弱点/抗性关系

- 弱点属性默认 **0%** 抗性
- 非弱点属性默认 **20%** 抗性
- 两者是**独立字段**

### 3.5 插入行动与 buff 回合

插入行动（追加攻击、终结技、额外回合）**不消耗 buff 回合数**。

### 3.6 战技点特殊案例

| 案例 | YAML 表达 |
|------|----------|
| 技能消耗 0 点 | `skill_point_cost: 0` |
| 技能消耗 2 点 | `skill_point_cost: 2` |
| 强化普攻不回复 | `skill_point_gain: 0` |
| 终结技回复战技点 | `skill_point_gain: 1` |

### 3.7 追加攻击分类

- 描述中含“追加攻击”或“反击” → `action_type: "follow_up"`
- 终结技、希儿再现等**不是**追加攻击
- 追加攻击可触发其他追加攻击，需检查递归深度限制

### 3.8 action_type 枚举

| 取值 | 说明 |
|------|------|
| `basic` | 普攻 |
| `skill` | 战技 |
| `ultimate` | 终结技 |
| `follow_up` | 追加攻击 / 反击 |
| `memosprite_skill` | 忆灵技能（召唤物行动） |

`dot` 触发、`break` 击破效果触发等不属于 `action_type`，它们通过 modifier trigger（如 `on_dot_retrigger`、`on_break`）或 hook 事件表达。

### 3.9 关于 `elation`

`elation`（欢愉度）是 **StatBlock 面板属性**，参与欢愉伤害公式（见 `01_formula.md`、`21_elation.md`），**不是** `custom_resources` 中的资源。

---
