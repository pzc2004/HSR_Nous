## 12. 召唤物系统 (Summon/Memosprite)

> **实现状态**：**v1 已落地**（2026-09-06）——`actor_type: "summon"` + `summoner_id` +
> `summon_flags` 能力闸（§12.4 通用约定）+ 角色模板 `summons:` 块（name/inheritance/
> base_stats/capabilities/actions/hooks/max_hp_ratio）+ `summon` / `dismiss_summon` / `heal` 三个
> effect_type + 召唤物自动回合（`_summon_turn`）+ owner 死亡联动离场 + 受击回能归忆师。
> **v1.1 补键**（2026-09-07）：`max_hp_ratio`（召唤物 Max HP = 召唤者 Max HP × 比例——
> 小伊卡 = 风堇 ×50%（140904）、Evey = 长夜月 ×比例，同构两实例垫底开键；语义见 §12.1 末）。
> **压缩裁决**（同批）：`behavior` / `special_mechanics` / `triggers` / `sustain_mechanic`
> 描述层**不立**——triggered 行为 = 召唤物自身 `hooks:` + `trigger_action`（复用现有 hook
> 机制）；能力/继承用 `capabilities` / `inheritance` 两个键表达；召唤物 hooks 编译期注册
> （owner 未入场时按 `state.actors` 查无即跳过，入场自然生效，无运行时订阅）。
> 下文章节保留为目标态设计参考；与 v1 落地件的出入以本注为准。

召唤物是角色在战斗中召唤的独立单位，拥有自己的速度和行动序列。造成伤害时使用召唤者的当前属性。一般情况下召唤物不能被敌方或我方选中为目标。

**忆灵**是记忆命途角色的专属召唤物，与普通召唤物不同，忆灵**可以被选中为目标**（接受我方 buff/治疗，也会被敌方攻击）。

### 12.1 召唤物 Actor 结构

```yaml
actor:
  actor_id: "SUMMON_001"
  name: "小伊卡"
  actor_type: "summon"           # character | monster | summon
  level: 80
  summoner_id: "1001"          # 召唤者 ID（代码真身字段名，见 sim_schema/actor.py）

  # 召唤物属性（可选，不一定全部拥有）
  base_stats:
    hp: 5000                     # 可选：有些召唤物没有生命值
    atk: 800
    def: 300
    spd: 100
    # ... 其他属性可选

  # 召唤物行为模式
  behavior:
    # 行动模式
    action_mode: "independent"   # "independent" | "triggered"

    # independent：出现在行动条上，独立计算行动值
    # triggered：不出现在行动条上，仅在触发条件满足时行动

    # 触发条件（triggered 模式下）
    # 复合触发名是"发射点 × 过滤"的语法糖（不逐机制膨胀枚举）
    triggers:
      - event: "on_after_action"       # 发射点：任意行动后
        condition: "$event.actor == $self.summoner_id"   # 过滤：行动者是召唤者（原 on_owner_action_end）
        description: "风堇的小伊卡"
      - event: "after_being_hit"       # 发射点：任意友方被命中
        condition: "$event.target != $self"        # 过滤：非自身（队友受击，原 on_ally_hit）
        description: "反击型召唤物"
      - event: "on_hp_decrease"        # 发射点：HP 降低
        condition: "$event.target == $self.summoner_id"  # 过滤：目标是召唤者（原 on_owner_hp_low；低血量阈值在 effects 的 condition 中给出）
        description: "保护型召唤物"

    # 离场条件
    leave_conditions:
      - type: "hp_zero"          # 生命值归零
      - type: "duration_expire"  # 持续时间到期
      - type: "owner_leave"      # 召唤者离场
      - type: "manual"           # 手动召回（技能效果）
      - type: "mechanic"         # 自身机制（如特定条件触发）

    # 继承规则（继承的是召唤者的战斗外面板，非战斗内状态）
    inheritance:
      stats: "partial"           # "full" | "partial" | "none"
      # full：继承召唤者战斗外面板全部属性
      # partial：部分继承（如只继承攻击力）
      # none：使用召唤物自身属性

    # 战斗内属性独立性
    combat_independence: true
    # 召唤者和召唤物的战斗内属性变化互不干扰
    # 单体 buff 不会共享（给召唤者加攻不影响召唤物）


  # 召唤物技能
  actions:
    - action_id: "SUMMON_001_basic"
      name: "伊卡攻击"
      action_type: "basic"
      target_type: "enemy_single"
      toughness_dmg: 10

  # 召唤物特有机制（可选，用于描述非标准 action 的被动机制）
  # （目标态字段——v1 压缩裁决不立本层（复用 summons 块 hooks）；下列 effect_type 实现状态逐行标注）
  special_mechanics:
    - mechanic: "heal_on_action"
      description: "每次行动后恢复召唤者生命值"
      trigger: "on_after_action"
      effect_type: "heal"            # 已实现（2026-09-06 收编——`05_effects.md` §5.2）
      target: "$self.summoner_id"
      amount: "$self.max_hp * 0.1"

    # 忆灵行动时为召唤者恢复能量
    - mechanic: "energy_restore_to_owner"
      description: "忆灵施放技能时为召唤者恢复能量"
      trigger: "on_after_action"
      effect_type: "gain_energy"
      target: "$self.summoner_id"
      amount: 10
```

`special_mechanics` 是召唤物/忆灵的可选描述字段，每个条目包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `mechanic` | string | 机制标识名 |
| `description` | string | 人类可读描述 |
| `trigger` | enum | 触发时机（Modifier trigger 命名空间） |
| `effect_type` | enum | 触发效果类型 |
| `target` | selector | 效果目标 |
| `amount` / `pct` / 其他 | 视 `effect_type` | 效果参数 |

> **触发名命名空间归属**：`on_after_action` / `on_cast` / `on_hp_zero` 属 `04_modifier.md` §4.8 modifier 生命周期触发器命名空间（**非** `23_event_hook_system.md` §23.4 hook 契约事件——hook `event:` 写了编译期炸）；`after_being_hit` / `on_hp_decrease` 才是 §23.4 契约事件（已登记）。

> `special_mechanics` 中的 effect 语义上等价于在 `actions` / `hooks` / `eidolons` 中显式声明的 effect（角色模板实键，见 `13_validator.md` §13.2 未知键拒绝）；它只是一种更紧凑的召唤物专用描述方式。

#### summons 块 `max_hp_ratio` 键（v1.1）

```yaml
summons:
  "1409_ika":
    name: "小伊卡"
    inheritance: "full"          # 其余字段继承忆师面板
    max_hp_ratio: 0.5            # hp 覆写 = 召唤者当前 Max HP × 50%（140904 天赋）
```

- **语义**：`inheritance` 计算完成后，召唤物的 `hp` 覆写为 **召唤时刻召唤者有效生命上限 × ratio**（`effective_stats` 口径——含行迹/遗器/光锥与召唤瞬间已挂的战斗内 buff；一次性定格，不追踪召唤者后续面板变化）。
- **与 `inheritance` 的关系**：**覆盖**而非互斥——`inheritance` 照常决定其余字段（atk/def/spd/...），`hp` 一律以 `max_hp_ratio` 为准（`inheritance` 的 hp 分量被覆盖；`"none"` + `max_hp_ratio` 时 `base_stats.hp` 仍必填——编译闸沿用，作为 ratio 缺省时的兜底与静态校验锚）。
- **取值**：正浮点（`(0, +∞)`；0 / 负数 / 非数值编译期炸）。
- 实例：小伊卡 = 风堇 Max HP ×50%（140904「最初之光治愈世界」）；Evey = 长夜月 Max HP × 比例（同构）。

### 12.2 召唤物行为模式

| 模式 | 说明 | 示例 |
|------|------|------|
| `independent` | 出现在行动条上，独立计算行动值 | 景元的神君 |
| `triggered` | 不出现在行动条上，仅在触发条件满足时行动 | 风堇的小伊卡、反击型召唤物 |

**触发条件示例**（写法均为"发射点 + `condition` 过滤"）：
- `on_after_action` + `condition: "$event.actor == $self.summoner_id"`：召唤者行动后（小伊卡）
- `after_being_hit` + `condition: "$event.target != $self"`：队友受击时（反击型）
- `on_hp_decrease` + `condition: "$event.target == $self.summoner_id"`：召唤者血量降低时（保护型；阈值另行给定）
- `on_kill`：击杀敌人时（追击型）

### 12.3 召唤物生命周期

#### 召唤入场

召唤通过角色 action 的 `summon` effect 触发：

```yaml
actions:
  - action_id: "140902"
    action_type: "skill"
    effects:
      - trigger: "on_cast"               # 04_modifier.md §4.8 modifier 生命周期触发器（非 §23.4 hook 契约事件）
        effect_type: "summon"            # 已实现（2026-09-06 收编——`05_effects.md` §5.2）
        summon_id: "hyacine_memosprite"
        position: "after_owner"        # 召唤位置：after_owner | before_owner | fixed_position
```

#### 离场/解散

召唤物生命值归零或满足特定条件时，通过 `dismiss_summon` effect 离场：

```yaml
# 在召唤物自身模板中
actions:
  - action_id: "hyacine_memosprite_passive"
    action_type: "basic"
    effects:
      - trigger: "on_hp_zero"            # 04_modifier.md §4.8 modifier 生命周期触发器（非 §23.4 hook 契约事件）
        effect_type: "dismiss_summon"    # 已实现（2026-09-06 收编——`05_effects.md` §5.2）
        summon_id: "hyacine_memosprite"
```

离场时序（2026-09-17 时序扶正）：`before_actor_exit`（`alive=False` **之前**——持有者在世，
「消失时」生前结算族挂载点）→ 置 `alive=False` + 调度器冻结 → `actor_exit`（死后清理族
挂载点）。两发射点盖全部消失原因：`dismiss_summon_actor` 单漏斗（倒计时/主动解散/召唤者
死亡联动）+ `_check_death` 真死定论点（被打死——召唤物 HP 归零不过 dismiss 漏斗）。
事件契约与 payload 见 `23_event_hook_system.md` §23.4 名册。

#### 续命机制

某些召唤物可以被治疗/续命：

```yaml
sustain_mechanic:
  can_be_healed: true            # 是否可被治疗
  can_be_shielded: true          # 是否可被套盾
  persistence: "temporary"       # "permanent" | "temporary"
```

### 12.4 忆灵特性

忆灵与普通召唤物的关键区别：

| 特性 | 普通召唤物 | 忆灵（记忆命途） |
|------|-----------|----------------|
| 可被选中 | 否 | 是（可接受 buff/治疗/被敌方攻击） |
| 属性继承 | 视角色而定 | 默认继承忆师战斗外面板，有特殊说明的优先 |
| 状态效果 | 独立 | 独立于忆师（单体 buff 不共享） |
| 遗器套装效果 | — | 大部分条件性加成不生效（除非特殊说明） |
| 影响范围 | — | 影响忆师的效果不影响忆灵，反之亦然（全体效果除外） |
| 召唤位置 | — | 忆师右侧（不可能是队伍第一个目标）——**已实现**（2026-09-08：布场即插入忆师右侧/簇尾，`state.actors` 插入序=站位，blast 相邻/前端卡序/受击范围同源；离场不离字典，重召回原位） |
| 技能升级 | — | 忆灵技能和忆灵天赋独立于忆师行迹升级 |
| 行动模式 | 多为 `independent` | 有固定速度，出现在行动条上 |
| 嘲讽 | — | 有独立嘲讽值 |
| 能量 | — | **与忆师共享能量池，无独立能量条**（mechanics 01 能量恢复节 / 05 能量系统章）——**已实现**（2026-09-08：一切指向忆灵的能量获得在 `_grant_energy` 统一入口重定向忆师——行动/受击/hook/秘技全路径覆盖；布场定格 `max_energy=0`（含 full 继承覆写）= 无能量槽领域事实，消费方零特判） |

**忆灵/召唤物能力通用约定**：能力集合**默认全开**——可被敌方选中、可被我方选中、有 AV（上行动条）、参与嘲讽；仅技能文本明确否认的能力才剔除（逐实例显式标注为 `false`）。已确认示例：

- **Demiurge**（Cyrene 忆灵）：`av: false` + `enemy_targetable: false`——忆灵天赋 1141503 原文：SPD 恒为 0、不上行动条（Action Order）、在场视为界外（Out-of-Bounds）
- **Netherwing（波吕刻斯，Pollux——遐蝶忆灵）**：`enemy_targetable: false`，但有 AV（能否被我方治疗/护盾单点选中**待实测**）
- **小伊卡**（Hyacine 忆灵）：`av: false`——SPD=0，不出现在行动条上，只能通过额外回合行动

**忆灵离场条件**：
- 生命值归零
- 特定条件（如 Garmentmaker 倒计时、Pollux 回合限制）
- 离场后忆师需重新召唤

### 12.5 与自定义资源、形态状态机的关系

- 忆灵/召唤物可以有自己的 `custom_resources`（**v1.2 已落地** 2026-09-07——summons 块内声明，
  与角色模板同一 `_RESOURCE_BLOCK_KEYS` 闸；布场时初始化 `current`，不入 setup 通道）。
  实例：昔涟忆灵德谬歌的 `story`（`tests/fixtures/templates/characters/1415_昔涟.yaml`），
  见 `16_custom_resources.md`。
  > 反例在案：风堇 `hyacine_cumulative_heal` 曾挂忆灵小伊卡（v1.2 首实例），2026-09-07
  > 迁入忆师风堇——官方口径"本场累计"须跨重召保留，忆灵离场布场重置会清账；
  > 忆灵侧读写经跨 actor 写通道（`set_resource` target）与 `resource_of` 读完成。
- 忆灵/召唤物也可以有 `actor_state` 和 `state_config`，用于表达形态切换，见 `17_actor_state.md`。
- 召唤物继承召唤者的 Layer 1 属性（不是 effective），避免 scaling 循环。详见 `04_modifier.md` §4.10。
- **召唤物施放的治疗，治疗源归主人面板**（2026-09-21 owner 裁决，灵砂浮元族 R-LS1 收官）：
  召唤物无 OHB（Outgoing_Healing_Boost）属性，「治疗量提高」主体为召唤者——`heal_bonus`
  （面板 + 命中域 scoped 件）读主人 `effective_stats`，不取主人+召唤物并集（主人面板已含
  一切加成）；atk/hp 缩放仍读施放者，受疗方 `incoming_heal` 不变。公式口径 mechanics 01
  §1.3，引擎落点 `sim/pipeline.py` `heal`（经 `_actor_lookup` 反查 `summoner_id`）。

### 12.6 回合控制模型与 manual_trigger（v1.3，2026-09-08 落地）

游戏实况里忆灵分两种回合控制模型，summons 块 `control` 键表达：

| control | 语义 | 实例 |
|---------|------|------|
| `auto`（缺省） | 回合**全自动**：行动取首个合法非 manual_trigger、目标自动选（prefer_target 机制优先，无法解析回落缺省）——任何决策源（含手动模式）都不弹问 | 小伊卡 / 长夜 / 德谬歌 / 龙灵 |
| `manual` | 回合**玩家操控**：行动+目标走统一决策源（与角色同流） | 死龙（爪痕/焰息每回合玩家选） |

auto 回合的目标免问由引擎 `_auto_target_ctx` 旗标承载（`_summon_turn` 挂/摘，嵌套 trigger 同免）；
`_resolve_targets` 见旗标跳过决策源。

> 通用语义（非忆灵专属）：**自动施放 = 自动目标**——玩家没点放的行动不问玩家目标。
> 角色侧同族走 `trigger_action` 插入式行动通道（挂同款旗标）：万敌血仇战技 140409/140411
> （"This ability will be automatically used."——140404 天赋回合开始/充能满自动施放）是首个
> 角色实例，模板写法 = on_turn_start/充能 hook → `trigger_action`，无需新原语。

**`manual_trigger: true`**（action 键）：手动触发型忆灵技——游戏实况是"忆灵回合全自动，
唯此类技能条件满足时玩家手动点放+手选目标"（长夜月「如露」1141307 族：忆质≥16 且不受控）。
语义：自动回合合法集**永远剔除**（绝不自动放）；改入终结技窗口 ready 清单
（`available_if` 过闸即可点放）；执行不耗能量/充能、不入形态机、**不发 `on_ultimate`**
（非终结技，防带偏 on_ultimate hook 族），`on_action` 广播照常；目标走统一决策源（窗口点放=手动）。

---

