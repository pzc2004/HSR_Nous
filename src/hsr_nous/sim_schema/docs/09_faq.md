## FAQ

**Q: 表达式 `"base_stats.def * 0.48 + 640"` 怎么执行？**

A: 运行时维护一个 `Context`，包含当前 actor、目标、全局状态等。表达式用安全的 eval 环境求值，或者实现一个小型表达式引擎。

**Q: 复杂的条件判断（如"生命值低于 50% 时增伤"）怎么表达？**

A: 在 `effects` 里加 `condition` 字段，用表达式表示：
```yaml
effects:
  - trigger: "on_before_hit"
    condition: "target.hp / target.max_hp < 0.5"
    effect_type: "add_stat"
    stat: "dmg_bonus"
    value: 0.3
```

**Q: 多段伤害（如希儿再现）怎么处理？**

A: 每段伤害是一个独立的 `deal_damage` effect，可以设置不同的 `trigger`：
```yaml
effects:
  - trigger: "on_cast"      # 第一段
    effect_type: "deal_damage"
    scaling: 2.0
  - trigger: "on_kill"       # 击杀后再现
    effect_type: "grant_extra_turn"
  - trigger: "on_extra_turn"  # 再现段
    effect_type: "deal_damage"
    scaling: 0.8
```

**Q: 嘲讽机制怎么实现？**

A: 基于 `taunt` 属性的概率选择：
```yaml
# 受击概率 = 角色嘲讽值 / 队伍嘲讽值总和
hit_probability: "actor.taunt / sum(all_ally.taunt)"
```
嘲讽值增减通过 modifier 的 `add_stat` 实现。

**强制嘲讽**：某些技能（如万敌终结技）会强制嘲讽敌人：
```yaml
effect_type: "apply_modifier"
modifier_id: "MOD_FORCED_TAUNT"
target: "all_enemies"
duration: 1
# 效果：被嘲讽的敌人必须攻击施加者
on_being_targeted:
  condition: "source.has_modifier(MOD_FORCED_TAUNT)"
  forced_target: "modifier.caster"
```

**Q: 欢愉命途怎么实现？**

A: 欢愉命途有独立的伤害类型和乘区：
```yaml
# 欢愉伤害公式（不享受增伤乘区）
elation_damage:
  expression: "abilityMulti * elation_multi * punchline_multi * critMulti * defMulti * resMulti * vulnMulti * trueDmgMulti * special_multi"
  parameters:
    - name: elation_multi
      expression: "1 + elation_damage_bonus"  # 欢愉度乘区
    - name: punchline_multi
      expression: "1 + 5 * punchline / (punchline + 240)"  # 笑点乘区（含稀释）

# 阿哈时刻（欢愉命途特殊机制）
aha_moment:
  trigger: "on_punchline_full"
  effect: "extra_turn"  # 获得额外回合
  speed_bonus: "punchline * 0.01"  # 速度加成
```

**Q: 记忆命途和召唤物（忆灵）怎么实现？**

A: 召唤物是类似角色的单位，但有特殊行为模式。参见 [12_summon.md](12_summon.md)。

---
