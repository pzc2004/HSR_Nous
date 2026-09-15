## 21. 欢愉机制 (Elation System)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。
>
> **实现状态**：欢愉体系 **B40 落地中**。公式入簿备镜（rulebook `elation_damage` 及乘区，与 `01_formula.md` 镜像一致、闸 13 保证）。分面状态：`elation_skill` 枚举+`trigger_action` 跨 actor（✅ P1a）/ `StatBlock.elation`+`Actor.elation_number`+笑点队伍账+好活当赏条目列表（✅ P1b）/ 欢愉伤害路由（✅ P2a——`pipeline.elation_damage`+route 表+action 层 `elation` 行键+hook `category: "elation"`）/ 阿哈时刻调度主体（✅ P2b——生成/速度公式/回合流程（解控→编号序代放→授好活当赏→清池）/波次豁免/`aha_instant` 额外时刻 effect/`aha_instant_start|end` 事件词表）。剩余：进战 20 好活当赏原生统发与 6 角色 fixture 迁移（P3）。规则层三 TBD 已于 B40 P0 定案（见 §21.8）。

### 21.1 核心定位

欢愉命途有独立的伤害类型和乘区。

- `elation`（欢愉度）是 **StatBlock 面板属性**（与 HP/ATK 并列），**不是** `custom_resources` 中的资源。
  - 行迹节点 property type `ElationDamageAddedRatioBase` → 映射 `elation` 面板（CN 显示名「欢愉度强化」终审——property 名有误导性，勿按字面映射 `elation_dmg_boost`）。
- `elation_number`（参演编号）是 Actor 的整型字段，用于阿哈时刻决定欢愉角色的技能触发顺序，编号越小越先触发。
  - 参演编号是**固定数值**（同能量上限性质），官方数据文本无此字段——模板手填标源（社区值：爻光 116 / 开拓者•欢愉 120 / 火花 144 / 绯英 146 / 银狼LV.999 999）。

与欢愉相关的资源：
- `punchline`（笑点）——**队伍账**（全队共享一池，战技点上方显示），不是 per-actor 资源
- `certified_banger`（好活当赏）——**逐角色账 + 带数值载荷**（见 §21.5 形制定案）
- `merrymake`（增笑）——per-actor 乘区池（`custom_resources` 或面板池均可承载，按 modifier 池先例）

### 21.2 欢愉伤害公式

```yaml
elation_damage:
  expression: |
    elation_level_multiplier * ability_multiplier * orig_elation_dmg_multi * elation_dmg_boost_multi *
    crit_multi * elation_multi * punchline_multi * merrymake_multi *
    def_multi * res_multi * vuln_multi *
    dmg_red_multi * base_universal_multi * final_dmg_multi
```

> 乘区表达式（`elation_multi` / `punchline_multi` / `merrymake_multi` / `dmg_red_multi` / `final_dmg_multi` / `elation_dmg_boost_multi`）与参数定槽规则的唯一事实源见 `01_formula.md`（rulebook zones，闸 13 镜像保证）与 `../../../../docs/mechanics/02_damage_formula.md` §2.7——本节不抄录（防腐）。要点：`orig_elation_dmg_multi` 勿填 fandom "Original Elation DMG Multiplier"（归 `final_dmg_multi` 槽，防双重计算）；`elation_dmg_boost` 当前无实例（预留槽默认 1——行迹「欢愉度强化」节点映射 `elation` 面板，不归本池）。

`punchline_source` 是公式参数占位符：
- 施放欢愉技时，`punchline_source = 阿哈笑点池当前值`（阿哈时刻内全体欢愉技**共用同一结算总值**，非逐人扣减；非阿哈时刻的欢愉技施放——如开拓者•欢愉终结技代放——同取实时笑点池）
- 其他欢愉伤害触发时，`punchline_source = 该角色的 certified_banger 合并值`

**欢愉伤害特点**：
- 不享受增伤乘区
- 不受虚弱影响
- 基础伤害与击破类似，不基于角色属性（等级系数 Lv.80 = 7535.1070）

### 21.3 笑点 (Punchline)

**累积**：欢愉角色通过普攻、战技、终结技累积笑点，**全队共享一池**（队伍账——不属于任何单个 actor；进战时每有 1 名欢愉角色 +1 笑点）。

**乘区公式**：
```
punchline_multi = 1 + 5 * punchline / (punchline + 240)
```
收敛上限为 6（+500%），等价形式：
```
punchline_multi = 6 - 1200 / (punchline + 240)
```

**消费方**：
- 施放欢愉技时用笑点池实时值
- 其他欢愉伤害用该角色的 `certified_banger` 合并值

**波次保留（推定）**：阿哈笑点计数器是全局计数，波次切换不构成战斗结束——推定跨波保留，无直接证据，待实测。

### 21.4 阿哈时刻 (Aha Instant)

阿哈是**独立跑条的特殊调度单位**（非角色、非召唤物、非额外回合——类比神君/呼雷），速度公式：
```
aha_speed = 80 + V1*0.2 + V2*0.1 + V3*0.05 + V4*0.02
```
其中 V1-V4 为欢愉角色速度从高到低排序（V4 系数 0.02 采米游社含演算实例版；0.025 备选——末位待实测）。

**生成**：队伍中存在欢愉角色即自战斗开始在行动轴上（进战即在场）。

**结算优先级 = 终结技同级**（插入位同终结技插入规则——17173 实测）。

阿哈 AV 归零时（阿哈时刻）：
1. 解除我方所有欢愉角色的控制状态
2. 读取当前阿哈笑点池总值（**本时刻内所有欢愉技共用此总值**）
3. 按参演编号从小到大触发所有欢愉角色的欢愉技（各一次）
4. 给每个欢愉角色添加 `certified_banger` 条目（值=本次消耗的笑点总值，2 回合后独立过期）
5. 清空阿哈笑点池，开始新一轮累积

**波次行为**：转波次**不重新跑条**（AV 保留——「转面不重跑」）；阿哈时刻内欢愉技**跨波次自动转火**（结算落到新波敌人）。

**额外阿哈时刻**（爻光终结技、环境 buff 等触发）：
- 具有额外回合的一切特点（不可插入终结技）
- **固定按 20 笑点结算，不消耗当前阿哈笑点池**
- 结束后照常授 20 点好活当赏
- 转波次不吞欢愉技

### 21.5 Certified Banger（好活当赏）

**形制定案（B40）**：好活当赏是**逐角色账、带数值载荷、逐条目独立过期**的结构——modifier（无数值载荷槽）与 custom_resource（单值无逐条计时）两态都装不下，定为**引擎原生第三条目列表**：

```
banger_entries: [{value: 笑点值, expiry: 回合序号}, ...]   # actor 态
certified_banger = Σ 未过期条目的 value                     # DSL 读通道（合并值）
```

- **获取途径**：进战全体欢愉角色 20 点（2 回合）/ 阿哈时刻结算转化 / 角色技能直给（绯英欢愉技等）
- 每次获得=新增一条目（独立 2 回合计时），合并计算按加和
- 消费方：非欢愉技的欢愉伤害以合并值作 `punchline_source`
- 不同角色持有好活当赏时的附加效果（爻光队友附伤/火花技能附伤等）走各角色模板 hooks，门控条件=持有未过期条目

### 21.6 Merrymake（增笑）

独立的"增笑"乘区，类似最终伤害：
```
merrymake_multi = 1 + merrymake
```

与笑点、好活当赏无关。来源稀有（现役仅爻光/绯英/银狼LV.999 六星魂）。

### 21.7 与 schema 的映射

| 概念 | 承载 | 说明 |
|------|------|------|
| `elation`（欢愉度） | StatBlock 面板属性 | 参与欢愉伤害公式；行迹 `ElationDamageAddedRatioBase` → 本键 |
| `elation_number`（参演编号） | Actor 整型字段 | 模板手填标源（社区值表见 §21.1） |
| `punchline`（笑点） | **队伍账资源**（engine 态，非 per-actor custom_resource） | 全队共享一池；`res_punchline` 读通道维持模板口径 |
| `certified_banger`（好活当赏） | 引擎原生条目列表（§21.5） | DSL 读合并值；hooks 以持有条目为门控 |
| `merrymake`（增笑） | modifier 池/custom_resource（按池先例） | 稀有乘区 |

详见 `16_custom_resources.md`（队伍账为 B40 新增 scope）。

### 21.8 TBD 定案记录（B40 P0）

~~阿哈行动条与队伍行动条的具体交互细节~~ → **定案**：独立跑条特殊单位，结算优先级=终结技同级；转波次不重跑+自动转火（§21.4）。

~~欢愉角色"欢愉编号"的确定规则~~ → **定案**：官方术语「参演编号」，固定数值（同能量上限性质），官方数据文本无字段——模板手填，社区值在案（§21.1）。

~~笑点/好活当赏在多波次中的保留规则~~ → **定案**：好活当赏=逐条目 2 回合独立计时自然跨波；阿哈笑点池跨波**推定保留**（待实测）；阿哈本体转面不重跑（实证）。

**仍开放（落地期标工作实现）**：
- 欢愉技削韧口径（角色 fixture 现按保守 0——待实测）
- 阿哈是否免疫行动提前/延后修饰（「超越规则限制的腿」目前仅证实转面不重跑——待实测）
- 笑点池跨波保留（推定——待实测）
