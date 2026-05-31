## 5. 效果类型 (Effect Type)

```yaml
# 造成伤害
effect_type: "deal_damage"
formula: "damage"           # 引用 formula 中定义的公式
target: "primary_target"    # 主目标 | all_enemies | all_allies | self | random_enemy | lowest_hp_enemy
scaling: 1.0                # 技能倍率
damage_type: "ice"          # 伤害属性

# 回复生命
effect_type: "heal"
formula: "heal"
target: "ally_single"
scaling: 0.3

# 施加 buff
effect_type: "apply_modifier"
modifier_id: "MOD_XXX"
target: "self"
duration: 3
chance: 1.0                  # 基础概率，受效果命中/抵抗影响

# 移除 buff
effect_type: "remove_modifier"
modifier_id: "MOD_XXX"
target: "enemy_single"

# 修改属性（立即/持续）
effect_type: "add_stat"
stat: "spd"
value: "base_stats.spd * 0.25"   # 支持表达式

# 回复能量
effect_type: "gain_energy"
target: "self"
value: 30

# 推进/拉条
effect_type: "advance_action"
target: "self"
value: 100                     # 行动值推进 100（立即行动）

# 回复战技点
effect_type: "gain_skill_point"
value: 1

# 召唤/召唤物行动
effect_type: "summon_action"
action_id: "SUMMON_XXX"

# 覆盖技能参数（用于星魂/行迹修改技能倍率等）
effect_type: "override_action_param"
action_id: "120502"              # 要修改的技能 ID
param_index: 0                   # 修改 params[level][index] 的哪个值
value: 0.65                      # 新值（覆盖原值）
condition: "eidolon >= 1"        # 触发条件（如星魂等级）

# 追加技能参数（在原值基础上加）
effect_type: "append_action_param"
action_id: "100103"
param_index: 1                   # 修改 params[level][index]
value: 10                        # 追加值（原值 + 10）
condition: "eidolon >= 1"

# 直接结算（用于表达式中的复杂逻辑）
effect_type: "script"
expression: "if target.hp < target.max_hp * 0.5 then apply_modifier(MOD_CRIT_BOOST)"
```

**参数覆盖 vs 追加**：
- `override_action_param`：直接替换参数值（如万敌 E1 把战技主目标倍率从 0.55 改为 0.65）
- `append_action_param`：在原值基础上加（如爻光 E1 使终结技触发的额外阿哈时刻多 10 笑点）

两者都支持 `condition` 字段，可用于星魂等级、行迹解锁等条件判断。

---
