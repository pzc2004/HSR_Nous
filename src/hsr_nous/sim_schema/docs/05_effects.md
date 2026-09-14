## 5. 效果类型 (Effect Type)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

Effect 是技能/行动/事件触发的最小执行单元。所有 effect 共享若干通用字段：

```yaml
effect:
  effect_type: "deal_damage"   # 必填：effect 类型
  target: "primary_target"     # 选填：目标选择器
  condition: "$self.energy >= 120"   # 选填：触发条件（受限 DSL）
  trigger: "on_cast"           # 选填：触发时机（ Modifier / Action 内）
```

### 5.1 数值字段 `amount` 统一说明

多个 effect 的数值字段统一为 `amount`（或 `pct`），支持以下形式：

| 形式 | 示例 | 说明 |
|------|------|------|
| 常量 | `amount: 5` | 固定数值 |
| 关键字 | `amount: "all"` | 全部当前值 |
| 比例 | `amount: "ratio:0.5"` | 当前值的 50% |
| 表达式 | `amount: "$self.max_hp * 0.3"` | 受限 DSL 求值 |
| 引用资源 | `amount: "$resource.punchline * 0.1"` | 读资源当前值 |
| 引用前序 | `amount: "$prev.amount * 0.8"` | 同一 action 内前一个 effect 结果 |
| params 引用 | `amount: "param(140903, 3)"` | 编译期按有效技能等级取 `skill_params` 表替换为字面量（见下） |

#### params 引用 `param(<skill_id>, <N>)`（编译期取档——已接线 2026-09-08）

hook/modifier 侧系数（治疗量、光环数值、tally 比例……）与 action `scaling` 数组同源——
都是原始数据 params 表的某行某列。手抄某一档字面量会让**烘焙值不随等级**：星魂 E3/E5
技能等级 +2 时 action 层 scaling 跳档而 hook 字面值原地踏步。params 引用把取档收敛到
**编译期**（等级战斗中不变，替换零运行期成本——`22_syntax_reference.md` §22.13
"VM 只见原语"同口径）：

```yaml
skill_params:                 # 角色模板顶层块——hook 侧系数的等级表载体
  "140903":                   # 技能 id（有 action 段的技能与 hook 专属技能同通道）
    level_key: ultimate       # 取档槽位（读 actor.skill_levels 的哪一键）
    rows:                     # lv1..lv15 全表，照抄原始数据 params（与 action scaling 同纪律）
      - [0.05, 50, 0.15, 150, 3, 0.06, 60]
      - [0.0563, 80, 0.165, 240, 3, 0.0675, 96]

hooks:
  - event: "on_action"
    effects:
      - effect_type: "heal"
        ratio: "param(140903, 1)"            # #1：治疗比例——编译期替换为字面量
        amount: "param(140903, 2) * 0.5"     # 与表达式混写合法（替换后过同一表达式闸）
```

- **语法**：`param(<skill_id>, <N>)`——skill_id **不加引号**；`N` 从 1 起（对应官方描述
  `#N[i]` 序号）。写法非法（id 加引号/参数个数错/替换后仍有 `param(` 残留）编译期炸
- **取档等级** = 编译期最终 `skill_levels[level_key]`（默认档 + member `skill_levels`
  覆写 + 星魂 `skill_level_overrides` 加算**之后**）；`level_key` 缺键回落 `ultimate`
  （与引擎 `_skill_level_of` 同口径）。忆灵技/忆灵天赋用 `memosprite_skill` /
  `memosprite_talent` 键（默认 10 档——角色 `skill_levels` 无此键时的种子值）
- **钳位**：有效等级越出 `rows` 表尾 → 钳到表尾并 ⚠ 编译警告（忆灵技/忆灵天赋官方
  数据上限 10 档，E3/E5"忆灵 +1"无第 11 档可取——钳位即"无数据不脑补"）
- **适用槽位**：一切过编译期表达式预编译闸的字符串槽——hook `condition` /
  `target_filter` / effects 数值槽（`EFFECT_EXPR_SLOTS`）/ `remove_modifier.filter` /
  modifier 的 `stat_effects` 字符串值 / `stat_exprs` / `enable_if` / `hit_condition` /
  action `available_if` / `state_config.stat_effects` 字符串值（纯字面量槽——替换后须为
  数值，不承接混写表达式）；action `apply_modifiers` 同通道。替换发生在预编译**之前**，
  产物是字面量/常规表达式。2026-09-12 补三槽（B27 #6 收编）：shield 的
  `scaling`/`flat` 与 `cap.multiplier`（护盾随档——三月七族；**纯字面量槽**，替换后仍非
  数值=表达式槽未接线，编译期炸指路）+ 目标代数 dict 的 `where`/`order_by`（就地写回，
  藿藿加强版阈值族）
- **报错**：`skill_id` 无表（本模板 `skill_params` 未声明——光锥/遗器 hooks 语境无
  角色等级轨道，等同无表）/ `N` 越出该行长度，均编译期炸；越界仅警告不炸
- **边界**：action `scaling` / `scaling_blast` 数组维持原通道（运行期按等级取行），
  本语法面向无 action 段或 hook/modifier 侧的系数；召唤物侧 hooks 引用**角色模板**
  的 `skill_params`，取档读模板主角色等级（星魂等级覆写落在角色上，召唤物无星魂）

### 5.2 标准 effect_type 列表

> **实现状态对账**（2026-08-24 起编译期强制）：引擎 `sim/hooks.py` `HookRuntime._run_hook_effect` 已实现集合的单一事实源是 `sim_schema/effect_types.py`——编译器对模板 hook effects 做白名单校验，**待收编的 effect_type 写进模板会编译期报错**（不是静默吞）。
>
> **字段级语境**：hook 语境合法字段集以 `sim_schema/effect_types.py`（effect_type / target 选择器 / 表达式槽位）与 `sim/compile/build_compiler.py` `_EFFECT_PARAM_KEYS`（各 effect_type 参数字段词表）为单一事实来源——**下文示例超出该集合的字段写了编译期炸**，各节按 **action 语境 / hook 语境 / 未实现** 逐字段标注（action 语境字段 = Action 顶层键，词表 `_ACTION_KEYS`）。

| effect_type | 状态 |
|-------------|------|
| `deal_damage` / `apply_modifier` / `remove_modifier` / `gain_energy` / `gain_skill_point` / `gain_resource` / `set_hp_to_percent` / `grant_extra_turn` / `immediate_action` / `delay_action` / `trigger_action` | **已实现**（hook 通道） |
| `break_damage` / `cancel_event` / `set_resource` / `heal_self` / `adjust_stacks` | **已实现**（hook 通道；原引擎暗原语，本节补登，见下） |
| `heal` / `summon` / `dismiss_summon` / `trigger_dot` / `adjust_duration` / `add_toughness_bar` | **已实现**（hook 通道——2026-09 收编：heal=任意目标治疗；summon/dismiss=召唤物入离场；trigger_dot=强制结算目标全部 DoT 不耗 duration；adjust_duration=时长 ±N ≠ refresh；add_toughness_bar=追加韧性条（虚韧性族，`03_actor.md` §3.10 条序模型）） |
| `advance_action` | **已实现**（hook 通道——2026-09-07 收编：amount 百分数拉条，剩余距离 ≤ 0 时无效；风堇 1140906 小伊卡消失拉忆师族） |
| `drain_hp` | **已实现**（hook 通道——2026-09-07 收编：生命流失/汲取，发 `on_hp_decrease`（reason='drain'）不触发伤害类 hook；遐蝶 140702/140709 耗全队当前生命、死龙 1140702 耗自身生命族，见 §生命汲取/生命流失） |
| `activate_ultimate` | **已实现**（hook 通道——2026-09-07 收编：目标终结技立即作为插入行动发动、不耗充能；昔涟 141503"激活全体队友的终结技"族，见 §激活终结技） |
| `set_sp_max` / `refill_skill_point`（+ `gain_skill_point` 增 `overflow_to` 键） | **已实现**（hook 通道——2026-09-14 收编：战技点上限覆写（花火天赋「上限额外增加」族，`state.sp_max_override` 挂点）；溢出记录（恢复超上限部分转记入资源池，`overflow_to` 键）与溢出回补（回合结束战技点 < 上限时从记录池补足，花火 1130603 族）） |
| `modify_amount` | **已实现**（hook 通道——2026-09-10 收编：waterfall 事件 `amount` 改写（抵扣/减免族，0=全额免扣；遐蝶 E2「炽意」抵扣焰息耗血首实例），见 §`modify_amount`） |
| `joint_attack` / `transfer_modifier` / `add_stat` / `remove_stat` / `none` / `banish_actor` / `end_current_turn` / `random_pick` / `summon_action` / `override_action_param` / `append_action_param` / `consume_resource` / `enter_state` / `exit_state` / `transform_action` / `deploy_zone` / `dismiss_zone` / `modify_event` | 待收编（前瞻定义，引擎未实现） |

#### 造成伤害

```yaml
# 假设 self.basic_scaling 已通过 variable_bindings 绑定
effect_type: "deal_damage"
formula: "damage"           # 引用 rulebook.yaml 中定义的公式
target: "primary_target"    # 主目标 | all_enemies | all_allies | self | random_enemy | lowest_hp_enemy
amount: "$self.atk * $self.basic_scaling"   # 技能倍率/基础伤害（支持表达式）
damage_type: "ice"          # 伤害属性
split: "even"               # 可选：总量按结算时存活目标均分（缺省 = 每目标全额）
```

> 旧字段 `scaling` 已被 `amount` 取代。`formula` 字段缺省为 `"damage"`（直伤公式）；仅使用其他公式（如 `dot_damage`、`elation_damage`）时需显式写明。

**字段语境对账**（上方为目标 schema 形状；当前两语境的实际收字以 `_EFFECT_PARAM_KEYS` / `_ACTION_KEYS` 为准）：

| 字段 | 语境 |
|------|------|
| `target` | hook 语境收（选择器词表以 `sim_schema/effect_types.py` `HOOK_TARGET_SELECTORS` + `$event.<字段>` 为准；示例的 `primary_target` / `random_enemy` / `lowest_hp_enemy` 是 action/policy 语境词表，hook 写了编译期炸） |
| `formula` | **未实现**（两语境写了都编译期炸；公式路由 = rulebook `route:` 按伤害类别自动选，不需显式声明） |
| `amount` | hook 语境**已收编**（2026-09-07）：基数区直写——`ability_multiplier` 由 amount 表达式喂入（`01_formula.md` §1.1 source 注），与 `scaling_atk`/`scaling_hp` **互斥**（同写编译期炸）；tally×比例族"资源值即基数"的落点（风堇 1140901、23042 光锥，`16_custom_resources.md` §16.8）。action 语境仍走 Action `scaling` 等级档表（写了编译期炸） |
| `damage_type` | hook 语境收（**二态**，2026-09-10 动态元素族收编——丹恒•腾荒 1414 同袍「相应属性」附加伤害首实例）：元素字面量直用（词表 `sim_schema/action.py` `ELEMENTS`）；词表外字符串按**白名单表达式**编译期预编译 + 运行期现场求值（`element_of` / `who_has` 宿主——"属性随动态目标"族），求值结果词表闸（非合法元素运行期炸——`element_of` 目标未声明 `element` 时得 `""`）；`category: "true"` 的真伤可写伪属性字面量 `"true"`（运行期真伤分支不读 `damage_type`） |
| `category` | hook 语境收（`"additional"` = 附加伤害；`"true"` = 真实伤害——2026-09-07 收编：走 rulebook `true_damage` 式（`amount` = `fixed_value` 直写，**须配 amount 且与 scaling 互斥**），防御/抗性/增伤/暴击/易伤/减伤/虚弱等常规乘区全不命中，护盾吸收层同走（mechanics 02 §2.8）；发射的 `on_hp_decrease` 带 `damage_type: "true"`——昔涟结界"原伤害 %"族防递归闸，见 `23_event_hook_system.md` §23.4） |
| `toughness_dmg` | hook 语境**已收编**（2026-09-07）：削韧值（缺省 0 = 不削；常量/表达式同 `_hook_amount` 通道）——与 action 层**同键同语义**：走 `_apply_toughness_damage` 单漏斗（own_element 默认闸——攻击属性 ∈ 目标有效弱点才削、`01_formula.md` §1.5 双效率池、击破判定、多韧性条全同口径，见 `03_actor.md` §3.4），仅对怪物生效；**逐目标逐 effect 各削**——多段伤害的多段削韧 = 多个 `deal_damage` effect 各声明各削（mechanics 04"削韧值按比例分布在每一段"同构）；与 `category: "true"` **互斥**（真伤无属性不削韧，mechanics 02 §2.8——同写编译期炸）；hook 语境**无 `toughness_scope` 参**（无视弱点削韧无实例垫底——写了编译期炸） |
| `split` | **action 语境**（Action 顶层键，已实现 `even` 均分，见下）；hook 语境写了编译期炸 |
| `instances` | **action 语境**（Action 顶层键，已实现多段展开；`instances_from_resource` 族同）；hook 语境写了编译期炸 |

**类别与段数（决策卡 #19）**：`category: "additional"` 声明附加伤害（写入事件 payload `tags: [additional]`——不吃类型限定增伤、不再触发命中类监听，见 `03_actor.md` §3.8 tags 登记）；`instances: <expr>` 声明多段/动态段数——DSL 禁循环，循环只存在于编译期：按表达式展开为 N 段独立结算（`target: "random_each"` 时逐段独立随机），并注入 `$seg.index` 段序号（"第 N 段起生效"类条件可读）。

**分配轴 `split`（可选）**：与范围轴（`target` / `target_type`：单体/扩散/群攻/弹射）**正交**——范围轴定"打谁"，分配轴定"每目标全额还是总量均分"（均分与打击范围是两个维度，不并入范围轴字段）。`split: even` 时 `amount` 为**总量**，按结算时**存活目标数**均分（目标中途退场，存活者份额随之变大）；弹射类按段均分到随机目标。实例：开拓者•欢愉欢愉技（均分欢愉伤害）、赛飞儿终结技终结一击、白厄最后一击。公式层零改动——effect 层均分后逐目标喂入 `ability_multiplier`（见 `01_formula.md` §1.1）。

> 落地自决策卡 #16（2026-08-15）

#### 击破伤害（break_damage）【已实现•补登】

击破公式伤害执行体（非直伤——走击破公式管线 × ratio；阮梅天赋/残梅绽族的落点）：

```yaml
# 残梅绽：击破伤害经 hook 发射（目标选择器与 deal_damage 同一实现集）
- effect_type: "break_damage"
  target: "$event.actor"        # 缺省 enemy_first；合法选择器见 sim_schema/effect_types.py
  element: "ice"                # 击破属性（缺省 physical）
  ratio: 0.25                   # 击破公式结果 × 本比例（缺省 1.0，支持表达式）
```

- 与 `deal_damage` 的区别：不吃直伤乘区，按击破公式结算（mechanics 04）；吃目标击破态
- 发射 `on_hp_decrease`（`reason: "break"`），计入伤害账本

#### 连携攻击（joint_attack）

单行动、多伤害包：一次行动产生多个**独立伤害结算**，每包带 `caster` 引用、按**各自面板/属性**求值（机制事实见 `../../../../docs/mechanics/11_special_mechanics.md` §11.6：单次行动、多次结算、固定顺序）。

```yaml
# 忆师 + 忆灵连携（迷迷 / 阿格莱雅类）：忆师先攻、忆灵后攻
effect_type: "joint_attack"
packets:
  - caster: "self"
    target: "all_enemies"
    damage_type: "ice"
    amount: "$self.atk * 1.0"
  - caster: "$self.memosprite"
    target: "all_enemies"
    damage_type: "ice"
    amount: "$self.atk * 0.6"
```

```yaml
# 联动角色连携（远坂凛×Archer / 吉尔伽美什×Saber）：caster 用具名绑定，与忆灵连携同构
effect_type: "joint_attack"
packets:
  - caster: "self"
    target: "enemy_single"
    damage_type: "wind"
    amount: "$self.atk * 1.2"
  - caster: "character_ref('archer')"
    target: "enemy_single"
    damage_type: "imaginary"
    amount: "$self.atk * 0.8"
```

| 字段 | 说明 |
|------|------|
| `packets` | 伤害包列表，按序结算；每包字段同 `deal_damage`（`target` / `damage_type` / `amount` / `formula`），另加 `caster` |
| `caster` | 该包的伤害来源：`self` / `$self.memosprite` / `character_ref(id)`（具名队友绑定，见 `22_syntax_reference.md` §22.7）；**包内表达式的 `$self` 绑定到该包 caster**（各自面板/属性） |

**"连携攻击"是一等可被选中的标签（伤害类别）**：joint_attack 打出的伤害包除主类别（`action_type`）外附加 `joint` 标签——`dmg_bonus_by_type` 增伤按标签集合命中各档求和（见 `03_actor.md` §3.2），`hit_condition` 可写 `'joint' in $event.tags` 选中（见 `04_modifier.md` §4.2）。忆灵连携（迷迷/阿格莱雅）与联动角色连携（远坂凛×Archer、吉尔伽美什×Saber）同构，差别只在 `caster` 的写法。

> 落地自决策卡 #10（2026-08-14）

#### 立即结算持续伤害（trigger_dot）

强制让目标身上的 DOT modifier **立即结算一次**——卡芙卡终结技、昔涟类"引爆"机制。

```yaml
effect_type: "trigger_dot"
target: "primary_target"     # 结算对象身上的 DOT
scope: "all"                 # "all"（卡芙卡 A2：全部来源）| "self"（仅自己施加的）| modifier_id（指定单一 DOT，如只引爆 Shock）
consume: false               # true = 消耗原跳数（本跳并入）；false = 额外结算一次（原计时不受影响的 Jump）
```

**语义**：

- 被结算的 DOT 按其**施加者面板**计算（不是施放 `trigger_dot` 的角色——后手归属：dot 伤害属施加者）
- `trigger_dot` 是**动作**不是事件；它产生的事件是统一的 **`on_dot_retrigger`**（见 `23_event_hook_system.md` §23.4：自然回合结算与本效果强制结算共用同一事件，`retriggered: true` 标记强制来源）
- 自然跳伤（回合开始 判定A/结算1）不需要此效果——那是 modifier 生命周期结算

#### 回复生命【已实现】

> **已实现**（2026-09-06 收编）：`heal` = 任意目标治疗——`target` 走 hook 选择器统一解析
> （缺省 `self`），`ratio` = 施放者有效生命上限 × 比例（支持表达式）；与 `heal_self` 同一
> 治疗管线口径（吃施放者 heal_bonus + 受疗者 incoming_heal），实际治疗量 > 0 发
> `on_hp_increase`（`reason: "heal"`）并触发月茧"受到治疗"解除。2026-09-07 补 `amount`
> 键：固定治疗量（缺省 0，支持表达式）——与 `ratio` 叠加进 rulebook `heal` 公式的
> `flat_heal` 槽（"MaxHP×比例 + 定值"官方治疗结构——风堇族）；下例 `formula` 写法是
> 旧目标态，现役参数键为 `ratio` / `amount`。2026-09-12 起 `ratio`/`amount` **逐目标
> 求值**（`$target` 注入——"按受疗者生命上限治疗"族首实例：阿格莱雅 1402 战技
> `param(140202, 1) * $target.max_hp`（官方"为衣匠回复等同于其生命上限的生命"——
> 治疗倍率按**受疗者**缩放；管线 hp_scaling 默认施放者口径，故此族必须 $target 通道）；
> 施放者侧 `$self` 写法求值不变）。

```yaml
effect_type: "heal"
target: "all_allies"           # hook 选择器（缺省 self）
ratio: 0.1                     # 施放者有效生命上限 × 本比例
amount: 205                    # 固定治疗量（缺省 0；与 ratio 叠加，进公式 flat_heal 槽）
```

#### 治疗自身（heal_self）【已实现•补登】

```yaml
# 免死回血族：致命伤取消 + 自疗 25%（白厄 140805 同构）
- effect_type: "heal_self"
  ratio: 0.25                  # 施放者有效生命上限 × 本比例（支持表达式）
```

- 走统一治疗管线：`hp_scaling = ratio × 施放者有效 HP`，吃施放者 heal_bonus 与受疗者 incoming_heal（mechanics 01 §1.3）
- 实际治疗量 > 0 时发射 `on_hp_increase`（`reason: "heal"`），并触发月茧"受到治疗"解除（`../../../../docs/mechanics/11_special_mechanics.md` §11.1）

#### 设定生命百分比（set_hp_to_percent）

把目标当前 HP 直接设为**生命上限 × 比例**（B9 登记原语；刃 120503 自调血线、复活族效果的落点）：

```yaml
effect_type: "set_hp_to_percent"
target: "self"
percent: 0.5             # 生命上限的 50%；0 = 致死（走死亡检查：锁血/月茧/复活/真死，见 04_modifier.md §4.15）
```

- 与 `heal` 的区别：不是"治疗"（不吃治疗加成、不发 `on_hp_increase`），是直接设定数值——可升可降
- 与 `drain_hp` 的区别：无保底 floor 语义、无治疗转化；`percent: 0` 会触发死亡结算

#### 施加/移除 modifier

```yaml
effect_type: "apply_modifier"
modifier_id: "MOD_XXX"
modifier: { ... }            # 可内联完整 modifier 定义
target: "self"
duration: 3
chance: 1.0                  # 基础概率，受效果命中/抵抗影响
```

**字段语境对账**（hook 语境只收 `modifier` 块 + `target`，平铺字段写了编译期炸）：

| 字段 | 语境 |
|------|------|
| `modifier` 块 | hook 语境**唯一通道**（内联完整 modifier 定义；块内合法键 = `sim/compile/build_compiler.py` `_MODIFIER_SPEC_KEYS`，含 `modifier_id` / `duration`） |
| 平铺 `modifier_id` | **未实现**（写了编译期炸——ID 写进 `modifier` 块内） |
| 平铺 `duration` | **未实现**（写了编译期炸——时长写进 `modifier` 块 `duration` 键） |
| `chance` | **未实现**（写了编译期炸——施加概率/EHR 结算未接） |
| `target` | hook 语境收（缺省 `self`） |

> **弱点植入不新增 effect_type**：用 `apply_modifier` + 弱点操作类 modifier（`weakness_add` 字段，见 `04_modifier.md` §4.11）表达；已挂 modifier 的时长增减用 `adjust_duration` 结算原子（同节）。

```yaml
effect_type: "remove_modifier"
modifier_id: "MOD_XXX"       # 可选；缺省 = 不限定 ID（配合 filter / max_count 使用）
target: "enemy_single"
filter: "$mod.debuff_kind == 'control'"   # 可选：表达式过滤，$mod 绑定待审 modifier（复用 ast 求值器，见 22_syntax_reference.md §22.4）
max_count: 1                 # 可选：最多移除个数（缺省 = 全部匹配）
order: "newest"              # 可选：移除顺序 newest（默认，LIFO）| oldest
```

**字段语境对账**（`filter` 已落地（2026-09-07，长夜月 141304 天赋"驱散控制类 debuff"族首实例）；`max_count` 已落地（2026-09-08，丹恒•腾荒 141404 龙灵"解除我方全体的 1 个负面效果"族首实例）；`order` 许诺未实现，写了编译期炸）：

| 字段 | 语境 |
|------|------|
| `modifier_id` | hook 语境与 `filter` **至少其一**（都写 = 交集；都不写编译期炸） |
| `target` | hook 语境收（缺省 `self`；示例的 `enemy_single` 不在 hook 选择器词表） |
| `filter`（`$mod` 绑定） | **已实现**（2026-09-07）——`$mod` 绑定待审 modifier（字段：`modifier_id` / `modifier_type` / `debuff_kind` / `control_kind` / `dispellable` + 合成 `kind`——免疫判定同口径 `debuff_kind or (control if control_kind else modifier_type)`，`"$mod.kind == 'control'"` 一把罩住两写法）；命中的仍仅限 `dispellable: true` 实例（见 `04_modifier.md` §4.6），按 LIFO 逐个摘除 |
| `max_count` | **已实现**（2026-09-08）——逐目标截断：命中清单（LIFO 序）只摘前 N 个，须为 ≥1 整数（编译期闸）；仅配 `filter` 路径有意义（`modifier_id` 定点摘除本就一次一件，写上不改变语义） |
| `order` | **未实现**（写了编译期炸） |
| `reason` | hook 语境收（缺省 `"remove"`，进移除日志/事件载荷） |

三个可选字段的组合对应常见净化/驱散族：流萤类"驱散全部" = 无 `filter`；知更鸟类/长夜月类"净化控制" = `filter: "$mod.kind == 'control'"`（已落地）；灵砂类/丹恒•腾荒龙灵类按个数 = `filter` + `max_count`（已落地——"解除 N 个负面"= `filter: "$mod.modifier_type == 'debuff'"` + `max_count: N`，debuff 全子类型含 dot/control 一把罩）。当前 hook 通道支持按 `modifier_id` 定点摘除 + 按 `filter` 成类摘除 + `max_count` 逐目标按数截断。

#### 调整层数（adjust_stacks）【已实现•补登】

modifier 层数增减（计数器消耗/叠层族）：

```yaml
- effect_type: "adjust_stacks"
  modifier_id: "SOUL_PYRE"
  delta: -1                    # 增量（支持表达式）；结果 clamp 到 [0, max_stack]
```

- `target`（可选，2026-09-07 跨 actor 写通道收编）：缺省 = hook 携带者自身；显式给 =
  对解析目标（们）逐各调层（选择器词表 / `$event.<字段>` / 目标代数 dict——与
  `apply_modifier` 等同一目标通道；昔涟 1141519"风堇施放战技/终结技后消耗 1 层「天空」"
  首实例）；目标未持有该 modifier 时该目标无效果（不报错）
- modifier 不存在时无效果（不报错）；`delta` 为正同样受 max_stack 封顶

#### 转移 modifier（transfer_modifier）

把 modifier 实例从 source 转移到 target，**保留剩余时长/层数**（区别于"重挂"——重新施加是全新实例）：

```yaml
# 椒丘【烬煨】死亡转移：携带者死亡 → 转移到当前层数最高的其他敌人
hooks:
  - event: "actor_exit"
    condition: "$event.actor_type == 'monster' && $event.reason == 'death'"
    effects:
      - effect_type: "transfer_modifier"
        modifier_id: "MOD_JQ_ASHEN_ROAST"
        source: "$event.actor"          # 从谁身上取下（缺省 = 事件/行动当前目标）
        target: "min_by(enemies, 'ashen_roast_stacks')"   # min_by 目标表达式（见 22_syntax_reference.md §22.4）
```

hook 驱动（`actor_exit` 死亡发射点 + `condition` + 目标表达式）即可覆盖椒丘/大黑塔同族；银狼植入的"重挂式"转移见 `04_modifier.md` §4.11。

**重排目标表达式（优先精英）**：大黑塔【解读】重排——携带者死亡/离场时层数转移，**优先精英及以上**目标；多键优先级用参数化选择器 `type: "priority"`（`22_syntax_reference.md` §22.7 参数化选择器族扩展：按 `keys` 列顺序逐键降序比较，取首个）：

```yaml
# 大黑塔【解读】重排：携带者死亡/离场 → 优先转移到精英及以上敌人，其次按层数高者
hooks:
  - event: "actor_exit"
    condition: "$event.actor_type == 'monster' && ($event.reason == 'death' || $event.reason == 'exile')"
    effects:
      - effect_type: "transfer_modifier"
        modifier_id: "MOD_THERTA_INTERPRETATION"
        source: "$event.actor"
        target:
          type: "priority"
          keys: ["is_elite", "interpretation_stacks"]   # 先精英层级、再按层数，逐键降序取首个
```

> 落地自决策卡 #9（2026-08-14）、#14（2026-08-14）、#16（2026-08-15）

#### 调整时长（adjust_duration）

modifier 剩余时长的**增量**加减（±N）——回合结束 tick（全体 -1）、延长植入（+1）、界外单位手动衰减（-1）共用同一**结算原子**：

```yaml
effect_type: "adjust_duration"
target: "primary_target"
amount: 1                    # +N 延长 / -N 衰减（增量：剩 1 回合 +1 = 2 回合；不是 refresh 重置满值）
filter: "$mod.modifier_id == 'MOD_SW_IMPLANT'"   # 可选：$mod 绑定待审 modifier（复用 remove_modifier.filter 语义，见 22_syntax_reference.md §22.4）；缺省 = 目标全部持续效果
```

- **职责分离**：原子 = 系统结算（改系统账本）；hook 要改时长必须调本原子，不直接改时长账本；时长变化事实照常经总线发射
- 与 `stack_mode: "refresh"` 的区别：refresh 把剩余时长**重置为满值**；本原子在剩余时长上**加减 N**（示例与界外单位用法见 `04_modifier.md` §4.11）
- 目标上无匹配 modifier 时无效果（区别于 apply_modifier 的施加语义）

> 落地自决策卡 #15（2026-08-15）、#16（2026-08-15）

#### 修改属性

```yaml
effect_type: "add_stat"
stat: "spd"
amount: "$self.spd * 0.25"
```

> `add_stat` 通常用于一次性/瞬时属性调整；持续属性加成应使用 `apply_modifier`。

#### 无效果 / 占位

```yaml
effect_type: "none"
```

用于 modifier / action trigger 中必须声明 effect 列表但无实际行为的占位场景。

#### 移除属性

```yaml
effect_type: "remove_stat"
stat: "shield"
```

用于 modifier 过期/移除时清理临时属性（如护盾清零）。`remove_stat` 只清指定 stat 的加成源，不处理完整的 modifier 生命周期；完整移除 modifier 应使用 `remove_modifier`。

#### 回复能量

```yaml
effect_type: "gain_energy"
target: "self"
amount: 30
```

- `target`：`"self"`（默认）/ `"all_allies"`（我方全体，停云/藿藿/秘技族）/ `"$event.<字段>"`（事件寻址单充族——停云/星期日终结技对单目标充能，实例：131303）
- `amount`：数值或表达式；表达式可引用 `$target` 命名空间（**按目标面板逐目标求值**——`0.2 * $target.max_energy` = 恢复目标能量上限 20%，星期日终结技 131303 实例）
- `err_exempt: true` 时该笔回能为具名豁免（mechanics 05 §5.3 清单：停云终结技/秘技、藿藿终结技、白露星魂 1、光锥「镜中故我」等），**不乘能量恢复效率**；缺省 `false` 吃 ERR
- 发射点：本原语与行动回能、受击回能一样经 `on_gain_energy` waterfall 发射（载荷与契约见 `23_event_hook_system.md` §23.4）；初始能量布场非事件，不发射

#### 激活终结技（activate_ultimate）

> **已实现**（2026-09-07，hook 通道收编——昔涟 141503"激活全体队友的终结技"是首个真实实例）。
> **语义冻结（与前瞻稿不同，按实例改写）**：目标的终结技**立即作为插入行动发动、
> 不耗充能**（能量与特殊充能资源同免）——不是"把充能资源补到激活阈值"（前瞻稿
> 的充能语义随本收编作废，`16_custom_resources.md` §16.2 `activation_grant` 行
> 同步失效——无消费点，保持指路炸）。

```yaml
# 昔涟 141503：激活全体队友的终结技（队友 ult 按编队序逐个插入发动）
- effect_type: "activate_ultimate"
  target: "other_allies"     # 缺省 = other_allies（官方主语"队友"）；走统一目标解析
```

- v1 口径（**B19 待实测**在案）：无视能量/特殊充能门槛直接发动、不扣量（是否白嫖待实测）；
  插入行动语义（不吃正常回合、不耗行动）；真人实机由玩家逐个点放并选目标——v1 按编队序
  自动连放、目标走各 ult 统一决策链
- 跳过：死亡/放逐/形态锁 ultimate/无 ult 行动的目标；形态替换 ult 按当前形态解析
  （与 `_legal_with_state` 同口径——昔涟涟漪态 141503→141514 族）
- 发动走 `_fire_ultimate` 同一漏斗（free 通道）：变身入口/`on_ultimate` 广播/行动副作用同口径

#### 推进/拉条

> **已实现**（2026-09-07 收编）：hook 通道 `advance_action`——`target` 走统一目标解析
> （缺省 `self`），`amount` 为百分数（30 = 提前 30% 行动条，支持表达式）；剩余距离 ≤ 0 时
> 拉条无效（`sim/scheduler.py` `advance_action` 内部口径，mechanics 03 钉死）。

```yaml
effect_type: "advance_action"
target: "self"
amount: 100                  # 行动值推进百分比：100 = 拉条 100%（通常可立即行动，但 ≠ "立即行动"原语——后者无视推条直接归零，见下节）
```

#### 立即行动

```yaml
effect_type: "immediate_action"
target: "self"
```

与 `advance_action: 100` 的区别：`immediate_action` 直接将该 actor 的 AV 设为 0，不受当前推条影响；`advance_action: 100` 是按当前速度减去 100% 行动条，若之前被推条可能无法到 0。

#### 授予额外回合

```yaml
effect_type: "grant_extra_turn"
target: "self"
queue_mode: "insert"      # insert = 插入第 2 层额外回合队列（再现/终结技类）；after_action = 战技类"本回合不结束"
```

> **字段语境对账**：`queue_mode` **未实现**（hook 语境写了编译期炸）——当前 hook 通道只授予 insert 语义（第 2 层 FIFO）额外回合，`target` 走统一目标解析（`$event.<字段>` 可用；缺省 `self` = 授予 hook 携带者）；`after_action` 语义待引擎落地。下表 queue_mode 语义为目标设计。

语义（详见 `../../../../docs/mechanics/03_action_sequence.md` §3.4 分层 FIFO）：

| `queue_mode` | 机制 | 语义 |
|---|---|---|
| `"insert"`（默认） | 希儿再现、终结技后额外回合类 | 进入第 2 层额外回合队列（与终结技同级 FIFO，不能插其他额外回合的队）；**不消耗 buff 回合数**；不受推条/减速影响；触发 `on_extra_turn` 事件 |
| `"after_action"` | 刃/青雀/波提欧战技、乱破终结技（游戏文本"本回合不会结束"） | 排在第 2 层队列**之后**，视同普通回合（消耗 buff 回合数） |

与 `advance_action` / `immediate_action` 的区别：后两者产出的是行动轴上的**普通回合**（消耗 buff 回合数；advance 可被推条抵消）；`grant_extra_turn` 产出**插入式**额外回合，不动行动轴。再现（希儿）标准写法见 `09_faq.md` 多段伤害示例。

#### 放逐 / 离场（banish_actor）

强制目标离场（白厄变身放逐队友类）：

```yaml
effect_type: "banish_actor"
target: "team_allies"        # 放逐对象
until: "transformation_end"  # 回场时机：变身终局结算后（关键字；也可写条件表达式）
```

三条语义（缺一不是放逐）：

- **不可选中**：离场者不进任何 `target` 选择器（见 `22_syntax_reference.md` §22.7）
- **状态冻结**：AV / buff / 生命保持离场前值，离场期间不 tick（时长不衰减、DOT 不结算、不在行动条上跑字）
- **回场恢复**：`until` 时机到、终局结算后按冻结值恢复（AV 与状态从冻结点续跑）

- 离场事实经总线发射 `actor_exit`（`reason: "exile"`，见 `23_event_hook_system.md` §23.4）；回场 = 再入场，发 `actor_enter`
- **例外注**：分摊类持续效果（符玄穷观阵）对离场者不生效——离场排除粒度为实测口径：不止"不被选中"，持续效果的作用域同样排除离场者
- 放逐**不是**控制类 debuff——不可驱散/净化（技能原文"不属于晕眩，无法被解除"）
- 离场是正交的**在场性**维度，不是 ActorState 形态（见 `17_actor_state.md` §17.2 注）

> 落地自决策卡 #16（2026-08-15）

#### 结束当前回合（end_current_turn）

立即结束目标当前回合（白厄天赋：变身时结束当前回合锁增益类）：

```yaml
effect_type: "end_current_turn"
target: "self"               # 被结束者
```

语义 = **保留已发生、丢弃未行动**：

- 已发生的行动/效果全部保留；被结束者本回合**未行动**的部分丢弃（不再行动）
- 被结束者 AV 重置满条（`10000 / speed`）；其他队友与倒计时 AV **冻结**（变身结束后按冻结值续跑）

**时序**（"锁 buff"数学原理）：引擎先对被结束者执行 `adjust_duration(+1)`（时长原子，见本节 adjust_duration）→ 再按**正常回合末结算**（B 类结算，时长 tick -1）→ 净效果：已有增益时长不变（+1 −1），本回合新挂增益**白赚 +1**。**+1 只补 `owner_turn_end` 锚**——B 类结算只走该锚的字，其他锚（`owner_turn_start` / `on_action`）本回合末本就不走字，无需补偿（对它们"已有增益时长不变"天然成立）。机制事实见 `../../../../docs/mechanics/03_action_sequence.md` §3.6。

> 落地自决策卡 #16（2026-08-15）

#### 示例：白厄变身全链

```yaml
# 白厄终结技全链：火种 → 变身 → 锁 buff → 结束当前回合 → 倒计时回合 → 最后一击均分 → 队友回场
custom_resources:
  coreflame:                       # 火种：12 点激活终结技
    max: 12
    ult_threshold: 12              # 充能三段式，见 16_custom_resources.md §16.12
  khaslana_turns:                  # 卡厄斯兰那倒计时回合额度（8 回）
    max: 8

actions:
  - action_id: "140803"
    name: "He Who Bears the World Must Burn"
    action_type: "ultimate"
    target_type: "self"
    effects:
      # ① 变身：队友放逐离场（不可选中/状态冻结/终局回场），自身进入 Khaslana 形态
      - effect_type: "banish_actor"
        target: "team_allies"
        until: "transformation_end"
      - effect_type: "enter_state"
        to_state: "khaslana"
        exit_conditions:
          - {trigger: "on_resource_depleted", value: "khaslana_turns"}   # StateConfig 私有枚举，见 17_actor_state.md §17.3
        on_exit_effects:
          # ⑥ 最后一击：总量按存活敌人均分（split 与 target 正交，见本节 deal_damage）
          - effect_type: "deal_damage"
            target: "all_enemies"
            split: "even"
            damage_type: "physical"
            amount: "$self.atk * $self.final_hit_scaling"
      # ②③ 锁 buff + 结束当前回合：end_current_turn 时序内置 adjust_duration(+1) → 正常回合末结算，
      #    本回合新挂增益白赚 +1（见本节 end_current_turn 时序注）
      - effect_type: "end_current_turn"
        target: "self"

# ④ 倒计时回合：卡厄斯兰那 8 个倒计时类额外回合——不消耗回合数、无回合开始/结束事件、
#    波次开始不重置行动值（额外回合两类型，见 03_actor.md §3.11）；
#    形态内行动（140808/140809/140811）各自带 consume_resource(khaslana_turns, 1)，
#    耗尽退出形态 → on_exit_effects 最后一击 → 终局结算后队友按冻结值回场（⑦）
```

#### 代放 / 复制行动（trigger_action）

以指定 caster 发起一次行动——覆盖"代放"（开拓者•欢愉代放欢愉技）与"复制"（刻律德菈复制战技）两族：

```yaml
# 静态引用：开拓者•欢愉代放欢愉技
effect_type: "trigger_action"
caster: "self"                  # 代放执行者
action: "tb_elation_skill"      # 静态引用 action_id
cost: "none"                    # none（不支付正常消耗）| pay（照付）
attribution: "original_caster"  # 归因：trigger_caster（算代放者发动）| original_caster（算原行动者发动）
timing: "immediate"             # immediate（立即插入执行）| queue（排入插入队列）
```

**`scaling_atk`（可选，动态倍率覆写）**：声明时以表达式现场求值，覆写被触发行动的 atk 倍率——计数器反击族的"倍率随层数/资源动态"（弑魂之炽、云璃/克拉拉反击族）落点：

```yaml
# 白厄弑魂之炽：敌方全体行动完毕 → 反击，倍率 = 0.4×(1+0.2/层)（层数现场读）
- effect_type: "trigger_action"
  action_id: "pyre_counter"
  scaling_atk: "0.4 * (1 + 0.2 * stacks($self, 'SOUL_PYRE'))"
```

```yaml
# 动态引用 = 复制：刻律德菈复制队友战技（hook 驱动）
hooks:
  - event: "on_cast"
    condition: "$event.action_type == 'skill' && $event.source != $self"
    effects:
      - effect_type: "trigger_action"
        caster: "self"
        action: "$event.action"       # 动态引用事件中的行动 = 复制
        cost: "none"
        attribution: "trigger_caster"
        timing: "immediate"
```

- `action: "$event.action"` 动态引用 = 复制该次行动（含其 effects 与数值上下文）
- 复制的行动会再经总线发射——模板需用 `condition` 排除自身（如上例 `$event.source != $self`）防自循环
- 代放不消耗被代放者的回合；是否支付消耗由 `cost` 控制

> **字段语境对账（hook 通道实装口径）**：hook 通道实装字段为 `action_id` / `scaling_atk`——
> `action_id` 静态引用 **hook 持有者自己**的行动（施放者=持有者；上例 caster/cost/
> attribution/timing 为目标设计未落地，写了编译期炸）。动态引用形态已实装：
> `action_id: "$event.action_id"`——行动与施放者都按事件寻址（复刻事件方刚施放的
> 行动并由其再放一次，刻律德菈奇袭"军功持有者战技复制"族；`on_action` 事件 payload
> 自 2026-09 起携带 `action_id` 字段）。

> 落地自决策卡 #13（2026-08-14）

#### 行动延后（推条）

```yaml
effect_type: "delay_action"
target: "primary_target"
amount: 30                  # 延后 30% 行动条
```

行动延后增加目标当前 AV：`new_av = current_av + 10000/speed * amount%`；999 仅为显示层封顶，内部值不钳（社区实测 B站 BV1rp4y1T7wG，旁证 BV1dqZyYBEya；单一来源，未独立复现）。

#### 追加韧性条（add_toughness_bar）

给目标追加一条韧性条（韧性条列表模型见 `03_actor.md` §3.10）——忘归人虚韧性条 = 挂 modifier 加条：

```yaml
# 忘归人：虚韧性条（modifier 驱动；条随 modifier 移除/过期一并移除）
modifier:
  modifier_id: "MOD_FUGUE_EXO_BAR"
  modifier_type: "debuff"
  duration: 2
  on_apply:
    - effect_type: "add_toughness_bar"
      target: "self"            # modifier 携带者
      bar_id: "fugue_exo"       # 条标识；同 ID 重复施加 = 刷新该条
      amount: 40                # 条的韧性值
      exo: true                 # 超韧性条：任意属性可削、击破再次触发弱点击破
```

- 追加条按加入顺序排在主条之后，**按序扣除**（前条未归零不扣后条）
- 每条归零经总线发射 `on_break`（payload 带 `bar_index`，主条 = 0）——二次击破用普通触发器 + `condition` 过滤，不加事件人头税
- modifier 施加的条登记来源：modifier 移除/过期时其挂载的条一并移除（无需 remove 原语）

#### 随机抽取（random_pick）

受控随机原语——效果层的随机性只走显式原语（同 `chance(N)` 哲学，见 `22_syntax_reference.md` §22.10）：

```yaml
# 银狼随机 debuff 池：加权抽 1 个挂上
effect_type: "random_pick"
pool: ["MOD_SW_DEF_DOWN", "MOD_SW_ATK_DOWN", "MOD_SW_SPD_DOWN"]
weights: [1, 1, 1]            # 可选：加权（缺省等权）
count: 1                      # 抽取个数（默认 1，不放回）
into: "picked_debuff"         # 结果写入模板变量，后续 effect 用 $self.picked_debuff 引用
```

| 字段 | 说明 |
|------|------|
| `pool` | 候选列表（modifier_id / 值） |
| `weights` | 可选权重列表（缺省等权） |
| `count` | 抽取个数（默认 1，不放回） |
| `rolls` / `keep` | 可选：重 roll 次数与保留策略——`rolls: 2` + `keep: "highest"` = 保留最高重 roll（砂金类） |
| `into` | 结果写入的变量名（后续 effect 以 `$self.xxx` 引用） |

- 青雀摸牌 = `pool` 牌型抽取；银狼随机 debuff 池 = `pool` + `weights`；砂金 = `rolls` + `keep: "highest"`
- **衰减概率变量**不是新原语：概率存 `custom_resources` 计数，`condition: "chance($resource.xxx * 5)"` 引用，触发后 gain/consume 该资源调整概率（黑天鹅衰减链）

> 落地自决策卡 #14（2026-08-14）

#### 生命汲取 / 生命流失【已实现 v1】

> **已实现**（2026-09-07，hook 通道收编——按本节冻结语义在 `sim/hooks.py`
> `HookRuntime._run_hook_effect` 重建；pipeline 侧旧零调用 `drain_hp` 结算件不复活）。

```yaml
effect_type: "drain_hp"
target: "all_allies"            # 流失 HP 的目标（选择器同其他 hook effect）
amount: "0.3 * $target.hp"      # 流失量（per-target 求值——$target 命名空间注入，
                                # "消耗全体当前生命 30%"族按目标各自当前 HP 结算）
drain_ratio: 1.0                # 流失量中转化为治疗的比例（0~1，默认 1.0）
heal_target: "self"             # 治疗目标，默认自身（hook 持有者）；选择器同词表
into_resource: "lc23042_hp_consumed"   # 可选：流失总额灌进资源（见下）
floor: 1                         # 可选：流失保底——耗不致死（决策卡 #19 小件族；缺省 0=可致死）
```

**语义**：使 `target` 失去 HP，并按 `drain_ratio` 治疗 `heal_target`。

- 每目标实际流失量 = `min(amount, 当前 HP - floor)`（floor 保底：当前 HP 不足时降到 floor 为止——
  遐蝶战技"当前生命不足时降至 1 点"= `floor: 1`）；floor 缺省 0（可致死，走死亡结算）。
- 治疗量 = 全部目标实际流失总额 × `drain_ratio`，走统一治疗管线（flat 槽——吃施放者
  heal_bonus + 受疗者 incoming_heal，发 `on_hp_increase` reason='heal'）；施放者 = hook 持有者。

**`into_resource`（可选）**：声明时，本次流失的**实际总额**（多目标时求和）灌入指定自定义资源，**替代** `consume_team_hp_pct`（已废弃）。用于表达"消耗全队生命累计计数"类机制（如光锥 23042）：

```yaml
# 光锥 23042：消耗全队当前生命 X% 并累计到资源
effect_type: "drain_hp"
target: "all_allies"
amount: "$target.hp * $self.consume_pct"
drain_ratio: 0                     # 不治疗
into_resource: "lc23042_hp_consumed"
```

**与 `deal_damage` + `heal` 的区别**：
- `drain_hp` **不触发** `before_take_damage` / `after_being_hit` 等**伤害类** hook（drain 不是伤害，避免"受击后"类效果被自伤误触发）。
- 但 `drain_hp` **触发** `on_hp_decrease`（reason='drain'）——HP 消耗与受击、DOT、流血一样都是 HP 降低来源（见 `docs/mechanics/11_special_mechanics.md` §11.3），刃天赋叠层、小伊卡天赋治疗、遐蝶新蕊等都挂在这个事件上。
- 适合表达"自残回血""小伊卡流失生命治疗队友"等机制。

**`before_drain` 可改写口（2026-09-10 收编——遐蝶 E2「炽意」抵扣首实例）**：每目标扣减前
走 `before_drain` waterfall（逐目标一发，`23_event_hook_system.md` §23.4 已登记）——hook 可 `modify_amount` 改写扣量
（0 = 全额免扣）或 `cancel_event` 整笔跳过该目标；改写/取消后无扣减即**不发** `on_hp_decrease`
（抵扣≠扣后回补）。payload 的 `action_id` 继承触发上下文（hook 链内的行动 id，焰息耗血=
`1140702`——抵扣条件的定位锚）；多目标流失按目标逐个判定（抵扣可只落部分目标）。

当 `heal_target` 与 `target` 相同时，就是典型的吸血；当 `heal_target` 为其他 actor 时，就是生命转移/反哺。

#### 回复战技点

```yaml
effect_type: "gain_skill_point"
amount: 1
```

#### 召唤/解散召唤物【已实现 v1】

> **已实现**（2026-09-06，12_summon v1）：`summon_id` 引用的是**召唤者模板 `summons:` 块的
> 键**（不是独立模板文件）；布场/继承/上行动条/`actor_enter`（`reason: "summon"`）全在
> 引擎单漏斗。`position`（行动条位置）v1 未收——新召唤物按满行动值入场。
> `dismiss_summon` → `actor_exit`（`reason: "dismiss"`）；未在场按 no-op。

```yaml
# 召唤单位
effect_type: "summon"
summon_id: "hyacine_memosprite"      # 召唤者模板 summons: 块的键
```

```yaml
# 解散召唤物
effect_type: "dismiss_summon"
summon_id: "hyacine_memosprite"
```

#### 召唤物行动【待收编】

> `summon_action` 未实现——v1 压缩裁决：召唤物代打复用 `trigger_action`（召唤物自身
> hooks 块声明触发条件），不立新 effect。

#### 覆盖/追加技能参数

```yaml
# 直接替换参数值
effect_type: "override_action_param"
action_id: "120502"
param_index: 0
amount: 0.65
condition: "$build.eidolon >= 1"
```

```yaml
# 在原值基础上加
effect_type: "append_action_param"
action_id: "100103"
param_index: 1
amount: 10
condition: "$build.eidolon >= 1"
```

### 5.3 资源相关 effect_type

见 `16_custom_resources.md` 详细说明。

#### `gain_resource`

```yaml
effect_type: "gain_resource"
resource_id: "punchline"
amount: 5
overflow_policy: "cap"       # "cap" | "allow" | "convert_to_extra"
```

- `target`（可选，2026-09-07 跨 actor 写通道收编）：写入目标——缺省 `self`（hook 携带者
  自身，存量语义不变）；显式给 = 对解析目标（们）逐各写（选择器词表 / `$event.<字段>` /
  目标代数 dict，与 `apply_modifier`/`heal` 等同一目标通道，`amount` 按 `$target`
  逐目标求值——`gain_energy` 同先例；昔涟 1141519 tally 加账 / 1141524 忆质 +1 首实例）。
  `set_resource` / `adjust_stacks` 同通道。**与 `source` 正交**：`target` = 写谁的面板，
  `source` = provenance 记谁触发的（写谁的不等于谁触发的）
- `source`（可选，2026-09-07 收编）：provenance 来源覆写——`"$event.<字段>"` 事件寻址或
  字面 actor_id；缺省 = hook 持有者自身。昔涟 Future"消耗来源 = 行动队友"族
  （`Ode to Ego` 按不同队友来源计数多段的记账前提，见 `16_custom_resources.md` §16.13）
- `overflow_policy`：**未实现**（写了编译期炸；溢出形态走资源声明 `overflow_mode`，§16.12）

#### `consume_resource`

```yaml
effect_type: "consume_resource"
resource_id: "hyacine_cumulative_heal"
amount: "ratio:0.5"
on_insufficient: "fail"      # "fail" | "clamp" | "consume_all"
```

#### `set_resource`【已实现•补登】

资源直接**设值**（与 `gain_resource` 的增量语义互补；银行清零/阈值重置族）：

```yaml
# 火种银行返还后清零（白厄 140804 同构）
- effect_type: "set_resource"
  resource_id: "fire_seed_bank"
  amount: 0                  # 设为目标值（支持表达式）
```

- `target`（可选，2026-09-07 跨 actor 写通道收编）：缺省 `self`；显式给 = 对解析目标（们）
  逐各设值（通道与 `gain_resource` 同；风堇 1140901 忆灵侧清 tally——账挂忆师——首实例）
- 设值 = 差量走 `_gain_resource` 统一入口（同拿 clamp/provenance 口径，`on_resource_gain`
  与负向 `after_consume` 照发——银行返还 `refund_bank` 的防回流由 `from_bank` 专道承担）

### 5.4 形态相关 effect_type

见 `17_actor_state.md` 详细说明。

#### `enter_state`

```yaml
effect_type: "enter_state"
to_state: "hellscape"
duration: 3
replaces_actions:
  shard_sword: forest_of_swords
locked_actions: ["blade_skill"]
on_enter_effects: []
on_exit_effects: []
```

#### `exit_state`

```yaml
effect_type: "exit_state"
target_state: "normal"
```

#### `transform_action`

```yaml
effect_type: "transform_action"
target_action: "basic"
new_action_id: "enhanced_basic"
```

### 5.5 场地相关 effect_type

见 `19_zone_system.md` 详细说明。

#### `deploy_zone`

```yaml
effect_type: "deploy_zone"
zone_id: "ruinous_irontomb"
area_shape: "battlefield"
duration: 3
on_turn_start: []
on_enter: []
on_damage_deal: []
scoped_modifiers: []
```

#### `dismiss_zone`

```yaml
effect_type: "dismiss_zone"
zone_id: "ruinous_irontomb"
```

### 5.6 Hook 相关 effect_type

见 `23_event_hook_system.md` 详细说明。

#### `modify_event`

在 hook effects 中修改原事件参数：

```yaml
effect_type: "modify_event"
event_updates:
  amount: "$event.amount - $last.actual_amount"
  target: "$self"
  cancel: false
```

#### `cancel_event`【已实现•补登】

取消当前 waterfall 事件（免死/免消耗族；仅对 waterfall 事件有意义——emit 事件无取消语义）：

```yaml
# 免死：致命伤 waterfall 取消（白厄 140805 同构；同 hook 内前序 effect 先结算）
- event: "before_take_damage"
  condition: "$event.amount >= $self.hp"
  effects:
    - effect_type: "heal_self"
      ratio: 0.25
    - effect_type: "cancel_event"
```

- 语义 = waterfall 链返回 `cancel: True`（与 `modify_event` 的 `cancel` 字段同通道，见 §23.6）；emit 事件上写 `cancel_event` 无效果

#### `modify_amount`【已实现】

改写当前 waterfall 事件的 `amount`（抵扣/减免族；仅对 waterfall 事件有意义——`amount` 是
可改键白名单 v0.1 两键之一，见 §23.6）：

```yaml
# 遐蝶 E2「炽意」：死龙施放【燎尽黯泽的焰息】时消耗 1 层【炽意】抵扣本次生命值消耗
#（before_drain 改写首实例——扣量改写 0 = 全额免扣）并令遐蝶行动提前 100%
- event: "before_drain"
  condition: "$event.action_id == '1140702' && $event.target == '1407_netherwing' && stacks($self, 'E2_ARDENT_WILL') >= 1"
  effects:
    - effect_type: "modify_amount"
      amount: 0
    - effect_type: "adjust_stacks"
      modifier_id: "E2_ARDENT_WILL"
      delta: -1
    - effect_type: "advance_action"
      amount: 100
```

- 语义 = waterfall 链返回 `amount: <求值结果>`（表达式走 `_hook_amount` 同通道——`$event`/
  `$self`/宿主函数可用；写槽 = `updates["amount"]`，与 `cancel_event` 可同 hook 组合）；emit 事件上写无效果
- 与 `cancel_event` 的分工：`modify_amount` = 改写数值（0=全额抵扣，中间值=部分抵扣）；
  `cancel_event` = 否决整笔（事件不再继续——对 drain 等价免扣，对伤害=整笔免伤）

### 5.7 已移除的 effect_type

| 旧 effect | 替代方案 |
|----------|---------|
| `convert_resource` | 并列 `consume_resource` + `gain_resource` |
| `consume_resource_substitute` | 事件 hook 系统（见 `23_event_hook_system.md`） |
| `script`（任意 Python 表达式） | 受限 DSL 表达式；复杂逻辑拆分为多个声明式 effect 或 hook |

### 5.8 参数覆盖 vs 追加

- `override_action_param`：直接替换参数值（如爻光 E1 把终结技额外阿哈回合固定计入笑点数从 20 覆盖为 40，params[3]）。
- `append_action_param`：在原值基础上加（如万敌 E1 使弑神登神主目标倍率 +30%，params[0] 加算）。

两者都支持 `condition` 字段，可用于星魂等级、行迹解锁等条件判断。

---
