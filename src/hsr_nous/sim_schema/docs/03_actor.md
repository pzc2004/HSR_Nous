## 3. 参战单位 (Actor)

Actor 分为角色和怪物，共用同一套结构。

```yaml
actor:
  actor_id: "1001"
  name: "三月七"
  actor_type: "character"    # character | monster
  level: 80

  # ========== 基础属性（只定义变量，值由 adapter 填入）==========
  base_stats:
    # 基础属性
    hp: 1047
    atk: 564
    def: 485
    spd: 101

    # 暴击
    crit_rate: 0.05          # 基础 5%
    crit_dmg: 0.50           # 基础 50%

    # 击破
    break_effect: 0.0

    # 效果
    effect_hit: 0.0
    effect_res: 0.0

    # 能量
    max_energy: 120          # 从 characters.json max_sp
    energy: 0                # 当前能量
    energy_regen: 1.0        # 能量恢复效率（基础 100%）

    # 治疗/护盾
    heal_bonus: 0.0
    shield_bonus: 0.0

    # 增伤（按属性分类）
    dmg_bonus:
      all: 0.0               # 通用增伤
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    # 抗性（按属性分类）
    resistance:
      physical: 0.0
      fire: 0.0
      ice: 0.0
      thunder: 0.0
      wind: 0.0
      quantum: 0.0
      imaginary: 0.0

    # 弱点属性（敌人用）
    weakness: ["ice", "wind"]

    # 嘲讽值（受击概率权重）
    taunt: 150               # 存护=150, 毁灭=125, 其他=100, 智识/巡猎=75

    # 欢愉度
    elation: 0.0

    # 韧性（敌人用）
    max_toughness: 100       # 韧性上限
    toughness: 100           # 当前韧性

    # 追加攻击增伤（独立乘区）
    follow_up_dmg_bonus: 0.0

  # ========== 技能 ==========
  actions:
    - action_id: "1001_basic"
      name: "寒冰之箭"
      action_type: "basic"           # basic | skill | ultimate | talent | follow_up | elation_damage
      target_type: "enemy_single"    # enemy_single | enemy_blast | enemy_aoe | ally_single | ally_aoe | self
      damage_type: "ice"
      energy_gain: 20
      skill_point_gain: 1            # 普攻回复 1 战技点
      toughness_dmg: 10              # 普攻削韧值
      # 技能效果：事件响应列表
      effects:
        - trigger: "on_cast"         # 释放时触发
          target: "primary_target"
          effect_type: "deal_damage"
          formula: "damage"
          scaling: 0.5               # 倍率 50%
        - trigger: "on_cast"
          target: "self"
          effect_type: "gain_energy"
          value: 20

    - action_id: "1001_skill"
      name: "可爱即是正义"
      action_type: "skill"
      target_type: "ally_single"
      skill_point_cost: 1            # 战技消耗 1 战技点
      toughness_dmg: 20              # 战技削韧值
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
      toughness_dmg: 30              # 终结技削韧值
      effects:
        - trigger: "on_cast"
          target: "all_enemies"
          effect_type: "deal_damage"
          formula: "damage"
          scaling: 1.5
        - trigger: "on_cast"
          target: "random_enemy"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_FREEZE"
          duration: 1
          chance: 0.5                  # 50% 基础概率，受效果命中影响

  # ========== 行迹（被动能力）==========
  traces:
    - trace_id: "T_1001_1"
      name: "公主殿下"
      effects:
        - trigger: "on_battle_start"
          target: "self"
          effect_type: "apply_modifier"
          modifier_id: "MOD_1001_TRACE_CRIT"
          duration: 0                   # 0 表示永久

  # ========== 星魂 ==========
  eidolons:
    - eidolon_id: "E_1001_1"
      name: "记忆中的你"
      unlocked: true
      effects:
        - trigger: "on_shield_apply"
          condition: "modifier_id == MOD_1001_SHIELD"
          target: "shielded_target"
          effect_type: "heal"
          formula: "heal"
          scaling: 0.3                  # 回合同等生命值 30%

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
  relics:
    - relic_id: "R_101_1"       # 头部
      set_id: "S_101"            # 套装编号
      slot: "head"
      main_stat: {stat: "hp", value: 705.0}
      sub_stats:
        - {stat: "atk", value: 42.0}
        - {stat: "spd", value: 4.0}
    - relic_id: "R_101_2"       # 手部
      set_id: "S_101"
      slot: "hand"
      main_stat: {stat: "atk", value: 352.0}
      sub_stats:
        - {stat: "crit_rate", value: 0.06}
        - {stat: "crit_dmg", value: 0.08}
    # ... 躯干、脚部、位面球、连结绳

  # 套装效果（由 adapter 根据套装件数自动附加）
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

---
