## FAQ

**Q: `base_stats.def * 0.48 + 640` 怎么执行？**

A: 公式在 `game_config.formula` 里定义，参数从运行时状态读取。角色模板通过 `ability_expression` 定义每个技能的伤害/治疗基础值，公式只管加乘区：

```yaml
# global/formulas.yaml — 通用公式，只管乘区
formula:
  damage:
    expression: "ability * def_multi * res_multi * vuln_multi * boost_multi * crit_multi"
    parameters:
      - name: def_multi
        expression: "100 / (target_def * 10 + 200) * (1 - target_def_pen)"
      - name: res_multi
        expression: "1 - (target_res - hit_res_pen)"
      - name: vuln_multi
        expression: "1 + target_vuln"
      - name: boost_multi
        expression: "1 + attacker_dmg_boost + hit_element_boost"
      - name: crit_multi
        expression: "is_crit ? (1 + attacker_crit_dmg) : 1.0"
```

```yaml
# 风堇角色模板示例
character_id: "1409"
name: "风堇"

variable_bindings:
  - self.basic_scaling  = lookup_table("basic_scaling",  index=$build.skill_levels.basic - 1)
  - self.ult_scaling    = lookup_table("ult_scaling",    index=$build.skill_levels.ult - 1)
  - self.s1140901_ratio = lookup_table("1140901_ratio", index=$build.skill_levels.skill - 1)

actions:
  - action_id: "basic"
    ability_expression: "$self.atk * $self.basic_scaling"

  - action_id: "ultimate"
    ability_expression: "$self.hp * $self.ult_scaling"

  - action_id: "1140901"   # 小伊卡忆灵技
    ability_expression: "$self.resources.cumulative_heal * $self.s1140901_ratio"
```

公式不关心 ability 从哪个属性来——那是角色层的事，通过 YAML 配置里的 `ability_expression` 指定。

**Q: 复杂的条件判断（如"生命值低于 50% 时增伤"）怎么表达？**

A: 在 hook 的 `condition` 字段里写表达式，修饰 modifier 的生效条件：

```yaml
# 角色模板中——增伤 buff，仅在 target 生命值低于 50% 时生效
hooks:
  - event: "on_before_hit"
    condition: "target.hp / target.max_hp < 0.5"
    effects:
      - effect_type: "apply_modifier"
        stat: "dmg_bonus"
        value: 0.3
        duration: 2
```

`condition` 是字符串表达式，由 sim 引擎的表达式引擎求值。

**Q: 多段伤害（如希儿再现）怎么处理？**

A: 每段伤害是独立的 hit，通过不同的 trigger 绑定：

```yaml
# 希儿普攻：第一段 + 击杀后再现段
actions:
  - action_id: "basic"
    hits:
      - trigger: "on_cast"
        scaling: "$self.basic_scaling"
    effects:
      - effect_type: "grant_extra_turn"
        trigger: "on_kill"
      - effect_type: "deal_damage"
        trigger: "on_extra_turn"
        scaling: 0.8
```

第一段在 `on_cast` 触发，击杀后再现段在 `on_extra_turn` 触发。不同段可以有不同倍率、元素、伤害类型。

**Q: 嘲讽机制怎么实现？**

A: 基于 `taunt` 属性的概率选择，敌人随机选目标：

```yaml
# 受击概率 = 角色嘲讽值 / 队伍嘲讽值总和
hit_prob: "$target.taunt / sum($team.taunt)"
```

嘲讽值增减通过 modifier 实现（如刃战技地狱变 +1000% 嘲讽值，存护光锥 +200% 等）。详见 [10_taunt_system.md](../../mechanics/10_taunt_system.md)。

**强制嘲讽**：某些技能强制敌人攻击指定目标，用 modifier 的 `stack_mode="replace"`——新施加的覆盖旧的，敌人必须攻击最新施加者。

**Q: 欢愉命途怎么实现？**

A: 欢愉命途有独立的伤害类型和乘区：

```yaml
# 欢愉伤害公式（不享受增伤乘区）
formula:
  elation_damage:
    expression: "ability * elation_multi * punchline_multi * crit_multi * def_multi * res_multi * vuln_multi * true_dmg_multi"
    parameters:
      - name: elation_multi
        expression: "1 + elation"
      - name: punchline_multi
        expression: "1 + 5 * punchline / (punchline + 240)"
```

**阿哈时刻**：独立行动条单位（非额外回合），速度 = `80 + V1*0.2 + V2*0.1 + V3*0.05 + V4*0.02`（V1-V4 为欢愉角色速度从高到低排序）。阿哈的 AV 归零时：
1. 消耗所有累积笑点
2. 按欢愉编号顺序触发所有欢愉角色的技能
3. 给每个欢愉角色施加 **Certified Banger（好活当赏）** buff（持续 2 回合，独立计时，多个好活当赏可合并笑点）
4. 多波次保留：阿哈不需要重新跑条

**笑点累积**：欢愉角色通过普攻、战技、终结技累积笑点，全队共享。`punchline_multi` 收敛到 6（+500% 上限）：`6 - 1200 / (punchline + 240)`。

**Q: 记忆命途和召唤物（忆灵）怎么实现？**

A: 召唤物是类似角色的单位，但有特殊行为模式。参见 [12_summon.md](12_summon.md)。

---
