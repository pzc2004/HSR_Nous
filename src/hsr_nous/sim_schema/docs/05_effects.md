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

# 直接结算（用于表达式中的复杂逻辑）
effect_type: "script"
expression: "if target.hp < target.max_hp * 0.5 then apply_modifier(MOD_CRIT_BOOST)"
```

---
