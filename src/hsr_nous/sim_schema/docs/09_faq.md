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

**覆盖规则**：若敌人已被施加强制嘲讽，后来的强制嘲讽会覆盖前者——敌人改为攻击最新的施加者。实现方式：`MOD_FORCED_TAUNT` 使用 `stack_mode: "replace"`，新施加的强制嘲讽替换旧的。

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

# 阿哈时刻（独立行动条单位，非额外回合）
aha_moment:
  # 阿哈是行动条上的独立单位，有自己的速度
  speed: "80 + V1*0.2 + V2*0.1 + V3*0.05 + V4*0.02"
  # V1-V4 为欢愉角色速度从高到低排序

  # 阿哈的 AV 归零时行动：
  action:
    - "消耗所有累积笑点"
    - "按欢愉编号顺序触发所有欢愉角色的技能"
    - "给每个欢愉角色施加 Certified Banger（好活当赏）buff"

  # 多波次保留：阿哈不需要重新跑条
  retain_across_waves: true
```

**Certified Banger（好活当赏）**：
```yaml
certified_banger:
  duration: 2                    # 持续 2 回合
  stack_mode: "independent"      # 独立计时
  effect: "记录被消耗的笑点值，多个好活当赏可合并笑点"
  # 不同角色有不同效果：
  # - 爻光：队友攻击时造成欢愉伤害
  # - 花火：自身技能造成额外欢愉伤害
```

**欢愉编号**：每个欢愉角色有一个编号，决定阿哈时刻中技能执行顺序（编号小的先执行）。

**笑点累积**：欢愉角色通过普攻、战技、终结技累积笑点，全队共享。阿哈时刻消耗所有笑点并转换为角色笑点。`punchline_multi` 收敛到 6（+500% 上限）：`6 - 1200 / (punchline + 240)`。
```

**Q: 记忆命途和召唤物（忆灵）怎么实现？**

A: 召唤物是类似角色的单位，但有特殊行为模式。参见 [12_summon.md](12_summon.md)。

---
