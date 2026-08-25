## 21. 欢愉机制 (Elation System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。
>
> **实现状态**：欢愉体系整体**未实装**——公式入簿备镜（rulebook `elation_damage` 及乘区，与 `01_formula.md` 镜像一致、闸 13 保证），路由未接（引擎无欢愉伤害结算路径）；阿哈行动条、笑点/好活当赏/增笑资源、`elation` / `elation_number` 字段均无引擎路径。本章为目标 spec（与 rulebook"入簿备镜"标注同口径）。

### 21.1 核心定位

欢愉命途有独立的伤害类型和乘区。

- `elation`（欢愉度）是 **StatBlock 面板属性**（与 HP/ATK 并列），**不是** `custom_resources` 中的资源。
- `elation_number`（欢愉编号）是 Actor 的整型字段，用于阿哈时刻决定欢愉角色的技能触发顺序，编号越小越先触发。

与欢愉相关的资源（属于 `custom_resources`）：
- `punchline`（笑点）
- `certified_banger`（好活当赏）
- `merrymake`（增笑）

### 21.2 欢愉伤害公式

```yaml
elation_damage:
  expression: |
    elation_level_multiplier * ability_multiplier * orig_elation_dmg_multi * elation_dmg_boost_multi *
    crit_multi * elation_multi * punchline_multi * merrymake_multi *
    def_multi * res_multi * vuln_multi *
    dmg_red_multi * base_universal_multi * final_dmg_multi
```

> 乘区表达式（`elation_multi` / `punchline_multi` / `merrymake_multi` / `dmg_red_multi` / `final_dmg_multi` / `elation_dmg_boost_multi`）与参数定槽规则的唯一事实源见 `01_formula.md`（rulebook zones，闸 13 镜像保证）与 `../../../../docs/mechanics/02_damage_formula.md` §2.7——本节不抄录（防腐）。要点：`orig_elation_dmg_multi` 勿填 fandom "Original Elation DMG Multiplier"（归 `final_dmg_multi` 槽，防双重计算）；`elation_dmg_boost` 当前无实例（预留槽默认 1）。

`punchline_source` 是公式参数占位符：
- 施放欢愉技时，`punchline_source = $resource.punchline`
- 其他欢愉伤害触发时，`punchline_source = $resource.certified_banger`

**欢愉伤害特点**：
- 不享受增伤乘区
- 不受虚弱影响
- 基础伤害与击破类似，不基于角色属性

### 21.3 笑点 (Punchline)

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

### 21.4 阿哈时刻 (Aha Instant)

阿哈是独立行动条单位（非额外回合），速度公式：
```
aha_speed = 80 + V1*0.2 + V2*0.1 + V3*0.05 + V4*0.02
```
其中 V1-V4 为欢愉角色速度从高到低排序。

阿哈 AV 归零时：
1. 消耗所有累积笑点
2. 按欢愉编号顺序触发所有欢愉角色的技能
3. 给每个欢愉角色添加 `certified_banger` 资源层数（好活当赏，2 回合后清除）
4. 多波次保留：阿哈不需要重新跑条

### 21.5 Certified Banger（好活当赏）

- 持续 2 回合
- 多个好活当赏可合并笑点
- 施放欢愉伤害时消费 `certified_banger` 作为 `punchline_source`

### 21.6 Merrymake（增笑）

独立的“增笑”乘区，类似最终伤害：
```
merrymake_multi = 1 + merrymake
```

与笑点、好活当赏无关。

### 21.7 与 `custom_resources` 的关系

| 概念 | 类型 | 说明 |
|------|------|------|
| `elation` | StatBlock 面板属性 | 参与欢愉伤害公式 |
| `punchline` | custom_resource | 全队共享笑点 |
| `certified_banger` | custom_resource | 好活当赏层数 |
| `merrymake` | custom_resource | 增笑 |

详见 `16_custom_resources.md`。

### 21.8 TBD

- 阿哈行动条与队伍行动条的具体交互细节。
- 欢愉角色“欢愉编号”的确定规则。
- 笑点/好活当赏在多波次中的保留规则。

---
