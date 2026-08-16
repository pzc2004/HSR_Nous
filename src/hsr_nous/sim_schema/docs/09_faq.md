## FAQ

**Q: 伤害公式里的 `ability` 从哪来？**

A: 公式在 `data/sim_templates/global/formulas.yaml` 里定义，参数从运行时状态读取。角色模板通过 `actions[].effects[].amount` 字段定义每个技能的伤害/治疗基础值，公式只管乘区：

```yaml
# data/sim_templates/global/formulas.yaml
# 以下为简化示例，完整 12 乘区见 01_formula.md
formulas:
  damage:
    expression: "ability_multiplier * dmg_boost_multi * def_multi * res_multi * vuln_multi * crit_multi"
    parameters:
      - name: ability_multiplier
        source: skill_scaling
      - name: dmg_boost_multi
        expression: "1 + elemental_dmg_bonus + all_dmg_bonus + type_dmg_bonus"
      - name: def_multi
        expression: "(attacker_level * 10 + 200) / (target_def * max(0, 1 - def_pen) + attacker_level * 10 + 200)"
      - name: res_multi
        expression: "1 - clamp(target_res - res_pen, -1.0, 0.9)"
      - name: vuln_multi
        expression: "1 + vulnerability"
      - name: crit_multi
        expression: "(random() < crit_rate) ? (1 + crit_dmg) : 1.0"
```

```yaml
# 风堇角色模板片段
variable_bindings:
  - self.basic_scaling  = lookup_table("basic_scaling",  index=$build.skill_levels.basic - 1)
  - self.ultimate_scaling = lookup_table("ultimate_scaling", index=$build.skill_levels.ultimate - 1)
  - self.s1140901_ratio = lookup_table("1140901_ratio", index=$build.skill_levels.skill - 1)

actions:
  - action_id: "basic"
    effects:
      - effect_type: "deal_damage"
        amount: "$self.atk * $self.basic_scaling"

  - action_id: "ultimate"
    effects:
      - effect_type: "deal_damage"
        amount: "$self.hp * $self.ultimate_scaling"

  - action_id: "1140901"
    effects:
      - effect_type: "deal_damage"
        amount: "$resource.hyacine_cumulative_heal * $self.s1140901_ratio"
```

公式不关心 `ability` 从哪个属性来——那是角色层的事，通过 YAML 配置里的 `amount` 表达式指定。

---

**Q: 复杂的条件判断（如“生命值低于 50% 时增伤”）怎么表达？**

A: 在 hook 的 `condition` 字段里写表达式：

```yaml
hooks:
  - event: "before_take_damage"
    condition: "$target.hp / $target.max_hp < 0.5"
    effects:
      - effect_type: "apply_modifier"
        modifier:
          stat: "all_dmg_bonus"
          flat_bonus: 0.3
          duration: 2
```

`condition` 是受限 DSL 字符串，由 sim 引擎表达式引擎求值。完整语法规则见 `22_syntax_reference.md`，事件 hook 完整语义见 `23_event_hook_system.md`。

---

**Q: 多段伤害 / 额外回合（如希儿再现）怎么处理？**

A: 用多个 effect 分别绑定 trigger。再现通过 `grant_extra_turn` 实现（游戏原文是额外回合，不是拉条）：

```yaml
actions:
  - action_id: "1001_basic"
    action_type: "basic"
    effects:
      - trigger: "on_cast"
        effect_type: "deal_damage"
        target: "primary_target"
        amount: "$self.atk * $self.basic_scaling"
      - trigger: "on_kill"
        effect_type: "grant_extra_turn"
        target: "self"                 # 第 2 层额外回合：不耗 buff、不受推条影响、触发 on_extra_turn
      - trigger: "on_extra_turn"
        effect_type: "deal_damage"
        target: "primary_target"
        amount: "$self.atk * $self.basic_scaling * 0.8"
```

第一段在 `on_cast` 触发，击杀后通过 `grant_extra_turn` 获得额外回合（`on_extra_turn` 事件由该原语触发），再现段在 `on_extra_turn` 触发。

> 历史说明：此前用 `advance_action: 100` 近似——那是普通回合（消耗 buff、可被推条抵消、不触发 `on_extra_turn`），与游戏原文"额外回合"不符；`grant_extra_turn` 落地后统一改用原语（见 `05_effects.md` 授予额外回合节）。

---

**Q: 嘲讽机制怎么实现？**

A: 基于 `taunt` 属性的概率选择：

```yaml
hit_prob: "$target.taunt / sum($team.taunt)"
```

嘲讽值增减通过 modifier 实现。详见 `../../../../docs/mechanics/10_taunt_system.md`。

**强制嘲讽**：某些技能强制敌人攻击指定目标，用 modifier 的 `stack_mode="replace"`——新施加的覆盖旧的。

---

**Q: 自定义资源怎么用？**

A: 参见 `16_custom_resources.md`。核心模式是：`custom_resources` 做纯存储，effect 读写，表达式做任意计算。

```yaml
custom_resources:
  punchline:
    max: 999999
    owner: "actor"
    scope: "team"

effects:
  - effect_type: "gain_resource"
    resource_id: "punchline"
    amount: 5
  - effect_type: "consume_resource"
    resource_id: "punchline"
    amount: "ratio:0.5"
```

---

**Q: 秘技系统怎么表达？**

A: 秘技是战前 action，通过 `Actor.techniques` 定义。详见 `18_technique_system.md` 和 `20_pre_battle_strategy.md`。

---

**Q: 形态切换怎么表达？**

A: 通过 `Actor.actor_state` + `StateConfig` + `enter_state` effect。详见 `17_actor_state.md`。

---

**Q: 欢愉命途怎么实现？**

A: 欢愉机制已提升为正式文档，详见 `21_elation.md`。FAQ 中只保留简要说明：

- `elation`（欢愉度）是 **StatBlock 面板属性**，不是 `custom_resource`。
- `punchline`（笑点）、`certified_banger`（好活当赏）、`merrymake`（增笑）是 `custom_resources`。
- 欢愉伤害公式不享受增伤乘区，见 `01_formula.md`。

---

**Q: 记忆命途和召唤物（忆灵）怎么实现？**

A: 召唤物是类似角色的单位，但有特殊行为模式。参见 `12_summon.md`。忆灵可以有自己的 `custom_resources` 和 `actor_state`。

---

**Q: 为什么用 DSL 而不是 Python 写模板？**

A: 因为 agent 面向所有玩家群体，无法保证每份输出都经过人工代码 review。DSL 是声明式、可静态验证的，天然比 Python 安全：

- 没有 `import` / `exec`
- 表达式无循环
- 不暴露 random/time
- 可静态 diff 和版本控制

内部 preprocessing 可以先用受限 Python 草稿，再 transpile 成 DSL。但进入 sim 的必须是 DSL。

---

**Q: 语法规则在哪里查？**

A: 完整 DSL 语法参考见 `22_syntax_reference.md`，事件 hook 系统完整语义见 `23_event_hook_system.md`，包括：

- `variable_bindings` 语法（`lookup_table`、`if` 条件覆盖）
- 表达式 DSL 白名单变量和函数
- `amount` / `condition` / `target` 字段写法
- 命名空间约定（`$self`、`$resource`、`$event`、`$target`、`$build`）
- hook 事件类型、`$event` 上下文、累积窗口模式
- 常见错误示例

---

**Q: 文档说 Pydantic，但代码还是 dataclass，以哪个为准？**

A: 文档是前瞻性定义，假设 Pydantic v2 实现。当前代码使用 `@dataclass` 作为临时实现。Pydantic 迁移是独立 PR，不会改字段语义。

---
