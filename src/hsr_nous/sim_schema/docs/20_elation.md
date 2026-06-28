## 20. 欢愉机制 (Elation System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

### 20.1 核心定位

欢愉命途有独立的伤害类型和乘区。`elation`（欢愉度）是 **StatBlock 面板属性**（与 HP/ATK 并列），**不是** `custom_resources` 中的资源。

与欢愉相关的资源（属于 `custom_resources`）：
- `punchline`（笑点）
- `certified_banger`（好活当赏）
- `merrymake`（欢庆值）

### 20.2 欢愉伤害公式

```yaml
elation_damage:
  expression: |
    level_multiplier * ability_multiplier * orig_elation_dmg_multi *
    crit_multi * elation_multi * punchline_multi * merrymake_multi *
    def_multi * res_multi * vuln_multi *
    dmg_mitigation_multi * base_universal_multi
  parameters:
    level_multiplier:        7535.1070   # Lv.80 等级系数
    ability_multiplier:      "来自技能"
    orig_elation_dmg_multi:  "来自技能"
    elation_multi:           "1 + elation_damage_bonus"
    punchline_multi:         "1 + 5 * punchline_source / (punchline_source + 240)"
    merrymake_multi:         "1 + merrymake"
    dmg_mitigation_multi:    "1 - dmg_mitigation"
```

**欢愉伤害特点**：
- 不享受增伤乘区
- 不受虚弱影响
- 基础伤害与击破类似，不基于角色属性

### 20.3 笑点 (Punchline)

**累积**：欢愉角色通过普攻、战技、终结技累积笑点，全队共享。

**乘区公式**：
```
punchline_multi = 1 + 5 * punchline / (punchline + 240)
```
收敛上限为 6（+500%），等价形式：
```
punchline_multi = 6 - 1200 / (punchline + 240)
```

**消费方**：
- 施放欢愉技时用 `punchline`
- 其他欢愉伤害用 `certified_banger`

### 20.4 阿哈时刻 (Aha Moment)

阿哈是独立行动条单位（非额外回合），速度公式：
```
aha_speed = 80 + V1*0.2 + V2*0.1 + V3*0.05 + V4*0.02
```
其中 V1-V4 为欢愉角色速度从高到低排序。

阿哈 AV 归零时：
1. 消耗所有累积笑点
2. 按欢愉编号顺序触发所有欢愉角色的技能
3. 给每个欢愉角色施加 **Certified Banger（好活当赏）** buff（持续 2 回合，独立计时）
4. 多波次保留：阿哈不需要重新跑条

### 20.5 Certified Banger（好活当赏）

- 持续 2 回合
- 多个好活当赏可合并笑点
- 施放欢愉伤害时消费 `certified_banger` 作为 `punchline_source`

### 20.6 Merrymake（欢庆值）

独立的“增笑”乘区，类似最终伤害：
```
merrymake_multi = 1 + merrymake
```

与笑点、好活当赏无关。

### 20.7 与 `custom_resources` 的关系

| 概念 | 类型 | 说明 |
|------|------|------|
| `elation` | StatBlock 面板属性 | 参与欢愉伤害公式 |
| `punchline` | custom_resource | 全队共享笑点 |
| `certified_banger` | custom_resource | 好活当赏层数 |
| `merrymake` | custom_resource | 欢庆值 |

详见 `16_custom_resources.md`。

### 20.8 TBD

- 阿哈行动条与队伍行动条的具体交互细节。
- 欢愉角色“欢愉编号”的确定规则。
- 笑点/好活当赏在多波次中的保留规则。

---
