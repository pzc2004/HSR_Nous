## 14. 策略模型 (Policy)

策略是可独立输入、可搜索优化的战斗决策逻辑。采用 **Rule-based + 参数化混合** 设计，用结构化数据模型定义。

### 设计原则

- **可执行**：模拟器直接 interpret，不需要 LLM 实时参与
- **可参数化**：关键数值（如大招阈值）抽离为可调参数，方便网格搜索/贝叶斯优化
- **LLM 友好**：结构清晰，LLM 容易生成和修改
- **维度拆分**：技能选择、目标选择、时机策略分离

### 策略结构

```yaml
policy:
  name: "1001_default"           # 带 actor ID 前缀（同人物多实体消歧纪律）

  # ========== 技能选择规则（按 priority 降序匹配）==========
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"    # 参数平铺注入（无 parameters. 前缀，见"表达式上下文"表）
      action: "ultimate"
      priority: 100

    - condition: "skill_points > 0"           # "队友无护盾"类谓词未接入上下文（见下表）
      action: "skill"
      priority: 50

    - condition: "true"
      action: "basic"
      priority: 0

  # ========== 目标选择规则 ==========
  target_rules:
    - condition: "action_type == 'skill'"
      selector: "lowest_hp_ally"
      priority: 100

    - condition: "action_type == 'ultimate'"
      selector: "all_enemies"
      priority: 100

    - condition: "true"
      selector: "primary_target"
      priority: 0

  # ========== 时机策略（可选；未落地——引擎无时机决策点，代码侧 TimingRule 已退役，收编时重建）==========
  timing_rules:
    - condition: "buff.MOD_XXX.stack >= 3 && !enemy.broken"
      timing: "delay"
      delay_condition: "enemy.broken == true"

  # ========== 可调参数 ==========
  parameters:
    ULT_THRESHOLD: 120        # 大招能量阈值
    SHIELD_PRIORITY: 0.8     # 护盾优先级权重
    HP_THRESHOLD: 0.5        # 低血量阈值
```

### 规则匹配逻辑

1. **技能选择**：按 `priority` 降序遍历 `action_rules`，第一条 `condition` 为真的规则被执行
2. **目标选择**：同样按优先级匹配，决定技能打谁

> 原第 3 条"时机选择"已删——`timing_rules` 未落地且代码侧已退役（见上文策略结构中的标注）。

### 合法性契约（legal action set）

policy **只选不越权**：引擎在每个决策点先计算 `legal_action_set`，分三段——

1. **形态换组**：当前形态/状态决定可用技能组（如白厄变身后普通战技不在集内）
2. **因子过滤**：资源门槛（能量/战技点/充能阈值）、控制状态、锁定/禁用、特殊回合限制（"仅能使用 X"类）
3. **条件闸**：action `available_if` 表达式现场求值（`03_actor.md` §3.8.1——在场换技能互斥/施放条件族；政策/手动/web/召唤自动同一漏斗，求值失败按不可用 + ⚠，同口径）

policy 的选择必须落在集内；静态非法（未知键/非法枚举/未知选择器/非法表达式）**编译期报错**（`_POLICY_KEYS` / `POLICY_TARGET_SELECTORS` / 表达式预编译等闸，见 `13_validator.md` §13.2）。"规则在动态上永不命中 legal set 时 validator 给 warning"的设想**未落地**——现役无此 warning 通道（validator.py 已退役删除）。实测未定项（如银枝满能量能否放小版终结技）只影响 legal set 的计算分支，不影响 policy 结构。

> 2026-08-14 落地（合法性契约注）

### 表达式上下文

策略表达式中可以访问的变量（单一事实源：`sim/policy_api.py` `CompiledPolicyRuntime._context` + `select_target`；目标侧 `target_*` 平铺键与 `$it` 命名空间 = `sim/target_algebra.py` `_it_namespace` 现役通道）：

| 变量 | 说明 |
|------|------|
| `energy` / `max_energy` | 当前能量 / 能量上限 |
| `skill_points` | 当前战技点 |
| `hp` / `max_hp` | 当前生命 / 有效生命上限（effective 口径，吃 hp_pct/flat/覆写 modifier） |
| `res_<resource_id>` | 自定义资源当前值（**平铺**注入，如 `res_fire_seed`——"火种<12 攒战技"族） |
| `in_state` / `state` | 是否处于形态 / 形态标识（`state_config` 驱动，缺省 `False` / `""`） |
| `<parameters 键>` | 策略参数**平铺**注入（如 `ULT_THRESHOLD`——**无 `parameters.` 前缀**） |
| `action_type` | 当前待选 action 的类型（仅 `target_rules` 语境注入） |
| `target_hp` / `target_hp_pct` / `target_broken` | 候选目标状态（仅 `filter` / `first` 参数化选择器的 `condition` 内可用） |
| `enemy_next_av` | 下一个敌人行动的预计时刻 − 当前时钟（相对 AV；无存活敌人时 9999.0——5a 敌人意图可见性，已接线） |
| `$team.<stat>` | 跨 actor 聚合：我方全员逐值列表（`atk` / `hp` / `max_hp` / `spd` / `energy` / `broken` / `actor_id`）——外套聚合函数（`max($team.atk)` / `sum($team.broken)` / `count($team.atk)`，2026-09-07 接线） |

> 历史登记的 `target_hp_ratio` / `buff.<id>` / `enemy.<attr>` / `ally_without_shield` / `allies[]` / `enemies[]` / `turn_count` / `cycle` / `wave_index` / `$resource.<id>` / `parameters.` 前缀均**未接线**——表达式 parse 放行裸 Name，上下文无此键，写了运行期"未定义变量"炸。

### 策略状态机（custom_resources 作相位容器）

> **实现状态**：本节整体**未落地**——`_POLICY_KEYS` 无 `mode` / `state_resources` / `state_hooks` 键（写了编译期炸）；hook 形态的 `state_hooks` 同样超出 `_HOOK_KEYS`（`scope` 未接线）。下文为目标态设计（仿 `timing_rules` 标注先例）。

policy 可声明 **team 级自定义资源**作策略计数器/相位容器，并通过 `state_hooks`（复用 `23_event_hook_system.md` 的 hook 形态）在战斗事件中维护；`condition` 用 `$resource.<id>` 读取。用于表达"相位"类策略（首回合特殊处理、每 N 回合循环等）。

```yaml
policy:
  name: "phase_demo"
  mode: "rule_based"          # rule_based（默认）| scripted | hybrid（见下节）

  # ========== 策略状态资源与维护 ==========
  state_resources:
    action_count: {max: 999, owner: "team"}       # 每次行动自增的相位计数器

  state_hooks:                                     # 复用 23 章 hook 形态
    - event: "on_after_action"
      scope: "team"
      effects:
        - effect_type: "gain_resource"
          resource_id: "action_count"
          amount: 1

  action_rules:
    - condition: "$resource.action_count == 0"
      action: "skill"
      priority: 100
    - condition: "true"
      action: "basic"
      priority: 0
```

validator 检查：`state_resources` 的 `resource_id` 与 `state_hooks` 内引用必须存在；hook 字段同 23.5  schema。

### scripted_policy：脚本回放变体

> **实现状态**：`mode: "scripted" | "hybrid"` + `script` **已落地**（2026-09-06）——逐回合有序脚本驱动（仅回放验证人肉发现的轴，**不进搜索空间**）；scripted 严格模式未覆盖即报错，hybrid 未覆盖回合回退 `action_rules` 匹配。turn 口径 = `state.turn_count + 1`（决策时点未递增；敌方空过也占 turn_count）；actor 先 id 后名、action 先 id 后类型解析。`state_resources` / `state_hooks`（策略相位容器）仍**未落地**（`_POLICY_KEYS` 无此二键，写了编译期炸——队级资源池与 `16_custom_resources.md` `scope: team` 同窗口待实例）。注意与现役 `ScriptedPolicy`（`sim/policy_api.py`：golden case 用的 **rotation 循环脚本**）**同名不同物**：本节是 YAML policy 声明的逐回合脚本，现役 ScriptedPolicy 是 Python 侧测试用具，不进 build.yaml 编译通道。

`mode: "scripted"` 的策略用**有序行动脚本**驱动，仅用于**回放验证人肉发现的轴**（如永动机），**不进搜索空间**：

```yaml
policy:
  name: "replay_axis_demo"
  mode: "scripted"
  script:
    - {turn: 1, actor: "seele", action: "skill"}
    - {turn: 2, actor: "seele", action: "basic"}
    - {turn: 3, actor: "seele", action: "ultimate"}
```

- 脚本条目按 turn 序执行；`actor`/`action` 必须能解析到该 actor 的 actions 内
- `mode: "hybrid"`：脚本覆盖列出的决策点，未覆盖的回合/角色回退到 `action_rules` 默认匹配；`mode: "scripted"` 严格模式——未覆盖即报错
- 脚本策略同样可配 `state_resources`/`state_hooks`（如永动机的能量/计数校验）

### 敌人序列/冷却 policy（实现期候选）

> **实现状态**：通用 `Monster_Common_SequenceThree_AI` 的主动技能子集已接线；
> 专属 AIPath 可由完整原始序列或可执行 ConfigAI 独立成立；后者不因实例技能 ID 与模板
> 序列不一致而被误拒。空原始序列只在存在可执行 ConfigAI 决策时生成 policy，不做表序兜底。
> 这里的状态机是实现期候选，
> 不是真实客户端语义定稿；最终仍须由 `designs/BATTLE_CLOSURE.md` 的真实 golden 对拍验收。
> 已收编被动技经独立 hooks 保留，不依赖主动 policy 是否可执行；阶段转换/形态切换不在此范围。
> `PhaseList` 只做技能可用性门控，专属 AIPath 被收编也不等于其完整 Boss 机制已验证。

敌人模板的 `policy` 与我方 build.yaml 的 rule-based policy 是两套输入，不复用玩家技能
优先级规则。v1 形状如下（冰锋 `1002011`）：

```yaml
policy:
  sequence: ["100201101"]          # 元素允许指向尚未收编的技能；仅 config-only 时可为空
  cooldown: {"100201101": 1}      # AI_CD，非负整数
  initial_cooldown: {"100201101": 1}  # AI_ICD，非负整数
  skill_phases: {"100201101": [1]} # PhaseList；仅列出的阶段可用
```

`policy` 还可带 `skill_ids`（`SkillTriggerKey → action_id`）与 `config`（ConfigAI 原始行为树）。
`ConfigAIInterpreter` 按 `DecisionList` 重新评分并执行 SequenceConfig：支持动态值比较、
阶段比较、怪物 ID、怪物 Rank、存活目标数、队伍计数、modifier 时长/层数、谓词 `Inverse`、
Define/Set/Add/Copy/CharacterCountDynamicValue、UseSkill、UseSequencedSkill、部分谓词组合。
静态支持表在 `sim_schema/config_ai.py`，未登记节点、目标选择器或技能不会写入 config；
队伍计数的 `CasterSummonedMinions` 别名只统计 `summoner_id` 等于施放者的敌方存活召唤物；
`AllLightTeam` 指我方全队，`AllDarkTeam` 指敌方全队；`AllLightTeam.RemoveServant` 与技能目标
别名 `AllEnemyIgnoreServant` 只保留非召唤我方角色，召唤归属均由 `summoner_id` 判定。
`CasterSummonedMinions` 的初始决策评估按 0 个处理，不用怪物总数冒充。默认动态值/阶段 1 下
无可执行决策的配置，
在有序列时只保留原始序列候选并记 notes，不拿旧
sequence 解释器冒充完整专属 AI。`SelectAISkillTarget` 支持 modifier id/name 匹配及
`MCommon_DOT_Electric` / `MCommon_DOT_Burn` 的触电/灼烧目标识别；无对应自定义标记时
回退到现有默认目标。`Retarget` 按 `TargetType` 与 `Predicate` 过滤候选，仅收 `MaxNumber=1`：
成功时把首个候选（roll 且 `ByRandom` 时随机一个）写入 `target_override` 并执行 `TaskList`；
空候选清除目标覆盖并执行 `FailedTaskList`。`AIMonsterRankSelector` 当前仅收
`PropertyStrategy=Max`，在怪物候选中保留 Rank 数值最高者（并列全保留），供 Compose 求交集。
动态值和 `current_phase` 与冷却一样进入存档。

候选转移规则：

1. 每个敌人独立持有 `seq_idx=0` 与 `cooldown_left=initial_cooldown`；序列位置按长度取模。
2. 每个敌方回合最多扫描一轮序列。每取一个候选就推进 `seq_idx`；未收编技能、当前阶段
   不在 `skill_phases` 内与 `cooldown_left>0` 的技能都显式跳过并继续看下一个，不得静默改放普攻。
3. 执行首个可执行技能，并把它的 `cooldown_left` 重置为 `cooldown[action_id]`（缺省 0）；
   一轮扫描后仍无可执行技能则本回合空过。
4. 存活敌人的每个回合结束，所有 `cooldown_left` 减 1、下限 0；本次未执行技能也算。
   因而 `AI_CD=1` 在执行回合末归零，下一回合可再次候选。
5. 无 `policy` 的老配置仍执行 `actions[0]`；显式空 `sequence` 编译期报错，生成器遇到
   空原始序列则不生成 policy，绝不按 actions 表序兜底。

语义对齐不再按整表 zip：每个 TBGD 技能逐个尝试 Fandom 候选，只接受唯一转换；
一个语义不得服务多个原始技能，冲突时只有原始顺序也能对齐才保留，其余拒绝收编。

生成器只为 Fandom 语义能与 TBGD 主动技能逐项对齐的**单段直接攻击**生成 action：
倍率文本须与 `ParamList` 逐值一致（single/AoE 一个值；Blast 主邻同倍率一个值或主/副
两个值），目标范围只收 single/Blast/AoE，`DamageType` 与非负整数 `SPHitBase` 必须存在，
并显式写 `energy_gain: 0`。Fandom `energy` 是 per-attack 受击回能，写 `energy_grant`；缺失时为 0。
Blast 主副不同倍率写 `scaling_blast`，单倍率沿用主倍率；副目标削韧暂不猜值，由引擎按 rulebook 的
`blast_toughness_ratio` 候选并在 notes 留痕。非 `Basic ATK` 的主动攻击暂以
`action_type: skill` 作为候选。`DelayRatio` 不进入当前结算；`PhaseList` 只写入
`skill_phases` 可用性门控，不据此推断阶段转换时机或波次关系。
完整纯直伤句可携带关联机制参数槽：只要描述经 `_enemy_pure_damage_description` 完整匹配，
且 ParamList 前缀与本击倍率逐值一致，就截取前缀倍率槽复用通用直伤路径；其余关联槽不参与
本击结算。非纯直伤句与前缀不一致的技能仍按原闸拒绝，不做全局放宽。

非直伤目前只收一类 Restore：Fandom 明确写“按施放者 Max HP 比例恢复敌方全体”时，
生成 `target_type: self` 的支援 action，并生成 `on_action` 敌人 hook，复用既有
`heal(target=all_enemies)` 管线；action 让序列真正推进并发射事件，hook 只在
`$event.actor == $self.actor_id` 且 action_id 匹配时治疗。Combat Redeployment 另以
目标代数排除施放者，先净化其他友方负面效果，再 `immediate_action`。
Barrenness of Earth Gouged 以 self action 发两个伤害 effect：我方全体 220% ATK，
其他敌方（排除施放者）3000% ATK，复用同一雷伤/削韧管线而非虚构双 target_type。
其余未列非直伤技能仍显式跳过。

单体雷伤 + Shock 已收编常规四项与倒序三项参数：伤害倍率、基础概率、持续回合、
DoT 倍率逐项一致后由 `on_action` hook 挂声明式 `modifier_type: dot`；单体火伤 + Burn
同走非叠层 ATK 快照 DoT，100% 概率也可省略原始概率槽。Fandom 把概率单位误写成 ATK
的条目只在 100% 且原始参数完整对账时接受。`apply_chance` 走统一效果命中/抵抗，
`max_stack=1` 防止重挂放大跳伤。单体风伤 + Wind Shear 另按 `DoT Per Stack` 保留叠层，
文本 `Max N Stacks` 写入上限；支持省略上限槽、DoT/持续回合倒序和 `Applies N Stacks`
初始层数三种布局，初始层数必须在文本与原始参数间一致。Arboreal Thorns 这类原文省略
伤害倍率的条目，只在 TBGD 给齐伤害、概率、持续、DoT 四槽时由原始倍率槽补齐。
Target Max HP Bleed 使用显式 `dot_ratio_expr`
在跳伤时读取持有者 `max_hp`，不与施加时烘焙混淆；条件施加与多目标 DoT 仍未覆盖。

直伤 + DEF 减益已收编单体/AoE 两态：伤害、基础概率、减防比例和持续回合与描述及
`ParamList` 逐项对账（100% 概率可省略原始概率槽）；`apply_chance` 在 effect 顶层，
逐目标走统一效果命中/抵抗，减防写 `stat_effects.def_pct` 负值。单体“承伤提高”
同通道写 `stat_effects.vulnerability` 正值且 `max_stack=1`；Weaken 按 mechanics 07
“降低造成伤害”写 `stat_effects.all_dmg` 负值；Effect RES 降低写 `effect_res` 负值，
100% 概率省略原始概率槽时以后两项对账。Great Ax: Irontalon 的具名 220350102 同走
`all_dmg=-0.2` 与一回合 debuff，未解释的关联参数槽不另猜语义。直伤 + 行动延后收
确定两参数与 `Base Chance` 三参数两态，复用 `delay_action`；effect `amount` 使用
百分数，`apply_chance` 与 modifier 共用效果命中/抵抗，抵抗时不推条。
固定次数、每段同倍率的 Bounce 直接复用 `target_type: bounce` + `instances`；每段随机
主目标且同时命中相邻单位的变体写 `bounce_blast`，副倍率/副削韧与 `blast` 同槽；优先覆盖
每个目标、重复命中追加伤害等 Barrage 规则不能冒充普通 bounce，仍排除。

敌人模板与角色模板共用 `custom_resources` 声明及 Action 资源字段：`resource_gain` 获得计数，
`instances_from_resource` / `instances_base` / `instances_per_point` / `instances_cap` 驱动段数，
`consume_all_resource` 在段数定格后清空计数。编译产物把敌方资源声明并入
`resource_decls_by_actor`， setup 与召唤布场均复用现有初始化通道。首个实例是 Obscure Blaze：
基础 1 击 + 每层追加 1 击，资源上限 3，因此总段数上限 4。
Gusto 不设上限：Wrathful Roar 获得 3 层并以 `lock_on` 标记监视目标，角色战技事件重定向该
标记；Simian Strike 以 `resource_gain: -1` 消耗，`available_if: res_gusto > 0` 在序列与
ConfigAI 两条选择链统一跳过空资源攻击，耗尽后清除标记。theBowja 与 TBGD 双源确认的两个
同名猱击原始 ID 可共享同一语义，不再按“一语义只能服务一技能”误删。
Calamity Power 同样不设上限：Dying/Silent Sorrow 分别获得 6/8 层；But Suffering is Essential
以 `instances_per_point: 2` 结算每层两段 20% 并追加一次 200% 终结 AoE，`available_if` 阻止
空资源施放，耗尽在 `on_action` 终结段之前完成。Cry Not For The Discarded 改用
`instance_variants`：首段 250% 主击，其后每层一段 40%，最多 8 层追伤；敌人行动编译器
同样保留段级变体。

Garrison Aura Field 以目标代数选择首个其他友方并挂一次性 Barrier；`before_take_damage`
把首次攻击伤害改写为 0 并消耗该件，DoT 不走该事件因而不被拦截。目标选择是实现期候选并在
notes 留痕，待真实 golden 定稿。

Fleeting Veil 作为独立被动 hooks 保留：`before_take_damage` 仅对 Basic/Skill/Ultimate/Follow-up
把承伤改写为 90%；`on_action` 以 20% 基础概率给攻击目标挂 Imprisonment，并复用
`on_apply: delay_action` 推条 50%，不依附主动技能收编完整度。
Disembodied Shell 在 `on_battle_start` 注册未击破 60% 减伤与击破后 50% 易伤的条件件，
`on_break` 推条 75%；被动扫描同时接受 `PassiveSkillInitiate`、`SkillPxx` 与 Talent 语义
（原生被动 ID 优先，Talent 只补未覆盖语义；仍须精确转换且唯一匹配，防止重复挂载）。
Cruelty 在 `after_being_hit` 检查 Shocked
目标，友方或 `controlled(source, 'dominate')` 命中时追加一次雷伤，并以专属 action_id 排除
追加段自递归。
Fiery Majesty 以 `stack_mode: refresh` 每次施放叠一层，`stat_exprs` 按层数计算 20% 增伤，
上限三层；`on_action` 后挂载的持续回合按现有 +1 口径处理。
Power Amplification 复用同一叠层通道，对全体友方每次施加一层 15% 增伤，不设时限与数值上限。
Phonation Unbound 在参数对齐的布局中以 modifier `shield.scaling.hp=0.09` 生成护盾，
并写 `all_dmg=0.2`；其他未对齐布局仍拒绝。
Vaneggiando 施加 Alien Dream（禁行动、50% 易伤、2 回合），`on_turn_start` 以
`$target.max_hp` 比例回血（Great Septimus 35%，其他 5%），`after_being_hit` 立即解除。
Radiating Venom 的 Entanglement 以 dot 承载 60%×层数延迟伤害与 50% 推条，
`prevent_action` 禁行动、最多 5 层，并在同一 `on_action` 召唤一个 Gnaw Sting。
Fallen Star's Visit 复用同一原语，改为 50%×层数、30% 推条与 30% 基础概率。
Thick-Skinned 在 `on_battle_start` 挂 150% DEF，`on_break` 摘除；新阶段重挂仍待阶段机收编。

AoE + Imprisonment 已收编单段与 `ATK × N` 多段文本：概率、持续、推条和减速参数逐项
对账；单体另支持 locked-on 目标与 `on the attacked target` 语序（Track Down）。
控制 modifier 的 `on_apply: delay_action` 与 `apply_chance` 共用一次施加判定，
使命中目标的推条/减速同时发生、抵抗目标两者均不发生；多段总倍率与每段倍率交叉校验。
Ice + Freeze 收三种参数布局：完整四槽、100% 基础概率省略概率槽的三槽，以及原文省略延迟
倍率但 TBGD 四槽齐全的布局；`on_turn_start` 按延迟倍率补一次冰伤，持续回合取原始槽。
Spirit Whisper 以 120% 基础概率施加三回合 `control_kind: dominate`，并把 `immediate_action`
放进 `on_apply`，因此仅在支配成功时立即触发强制普攻，目标阵营由现有支配回合逻辑决定。
Heaven's Binds 以 self 支援 action 推进行动序列，并在 `on_action` 对自身调用 `immediate_action`，
形成一次额外行动。
Spiral Arrow 以目标侧 `lock_on` 固定下一次 End of Bow 主目标；End of Bow 的纠缠复用
`dot + on_apply delay_action` 表达延迟伤害与推条，并在行动后解除锁定。Nihility's Command
用 bounce 仅作随机单体选择，随后全体敌方单目标攻击都读同一 lock_on，并保留 10% 易伤。
Double Waxing Moon 以目标代数给前两个我方目标挂 `lock_on`；Sixfold Plenilune 的 hook 伤害
只选择携带该锁的目标，再施加 Oronyx's Mark，不把 AoE 文本误扩为全体命中。
Light the Future 锁一个目标；Praise Aquila 直接复用 Blast 主邻结算，`on_action` 再以
`has_modifier or is_adjacent` 选择主邻命中者施加 Aquila's Mark。
Triple Waning Moon 复用 Sweep 的目标代数 `-formation + take 3`，从右侧连续取三目标，
伤害后施加 Oronyx's Mark，并按同一目标集恢复受击能量。
Hemotort Teethgrind 收两种有盾分支：`reduce instead` 时不直接扣血并
`reduce_toughness(amount=60, floor=1)`；`trigger Barrier Recoil` 时伤害照发并额外
`reduce_toughness(amount=60, floor=0)`。两分支都在 `on_action` 分流，不依赖
`before_take_damage` 不存在的 action_id。

Summon 目前限模板与数量明确：生成 self 支援 action 与 `on_action` 的 `summon` effects；
每个实例有独立 summon_id/enemy_template/level，`CompiledStage.enemy_summon_defs` 与 build 的
`summon_defs` 合并，召唤物的 actions/policy/hooks 也进入同一编译链。`Consumes HP (N% Max HP)`
变体先经 `drain_hp` 消耗再召唤，原始参数与比例逐值对账；英文单复数名称只在元数据严格
对应时放行。`SummonIDList` 多模板已收 Twin Bond、Omen、Spear & Shield 与 Siege Support
（枪兵/炮兵各一并给主目标挂 `lock_on`），阶段召唤和召唤链资源条件尚未覆盖。

Charge 目前收两类：增伤比例明确的下一击生成 self 支援 action 与 `all_dmg` modifier；
无附加效果的纯蓄力也只生成 self 支援 action，由原始序列/ConfigAI 推进到下一技能，覆盖
`The next action uses/casts`、`Uses/Casts ... in the next action` 与具名单位 `will use ... on next action`
等语序，不接纳锁目标、资源获得或其他附加效果。声明持续 N 回合时，由于 hook 在
`on_action` 后挂、当前回合末先走一次字，实际模板 duration 写 N+1 才能覆盖下一击。
自爆 Blast 复用 `set_hp_to_percent(self, 0)` 走统一死亡链。
蓄力锁定、阶段转换和其他 Charging 状态尚未覆盖。

The Can's Tribulations 使用 `stack_mode: replace` 保留使用次数并在替换前烘焙旧层数：
首次 ATK 加成取原始 ParamList，之后每次翻倍，`duration=0` 且 `dispellable=false`。
只有 ref 文本明确给出对应初始比例和翻倍规则时才收编。

Hardy Leaf Sheath 生成 self 加防 modifier，并以 `toughness_lock` 阻止存续期间削韧；
self `on_action` 后挂的 1 回合效果同样按声明时长 +1，避免当回合末先到期。
扑满倒计时技能生成 self 支援 action 并由原始序列推进；ConfigAI 明示
EscapingCharge 标记时从原配置提取真实 modifier id，并以 `singleton_group` 保证
Charge02 替换 Charge01，使后续决策继续推进。立即逃跑项复用 `leave_battle` 发
`actor_exit(reason=flee)`，不走死亡检查、不发 `on_kill`。
Reverberation 受击后由 `after_being_hit` 钩转为 Strong Reverberation：原子推 70% 并
摘除原标记，Strong 的 `prevent_action` 使下一次行动空过且回合末正常结算。

### 敌人意图可见性（5a）

策略表达式可读敌人的**行动序信息**（`enemy_next_av` 等）——敌人何时行动是公开信息，用于"卡在敌人行动前开盾"类策略。敌人 AI 行为/目标预测（5b）**暂缓**（概率性，归场景二，不建模）。

> **实现状态**：`enemy_next_av` **已接线**（2026-09-06——策略表达式上下文键，值为下一个敌人行动的预计时刻 − 当前时钟（相对 AV），无存活敌人时 9999.0；5b 行为/目标预测仍暂缓）。

### 验收示例：留大给第二波

```yaml
action_rules:
  - condition: "energy >= ULT_THRESHOLD"   # 可运行形态（参数平铺注入）
    action: "ultimate"
    priority: 100
  - condition: "true"
    action: "basic"
    priority: 0
```

> 注：原示例的 `wave_index >= 2 && energy >= parameters.ULT_THRESHOLD` 不可运行——`wave_index` 未接入策略上下文、`parameters.` 前缀不存在（见"表达式上下文"表末注）；波次条件待 `wave_index` 接线后恢复。

### 为什么不用自然语言策略

| 自然语言 | Rule-based 模型 |
|---------|---------------|
| "优先使用战技" | `condition: "skill_points > 0", action: "skill"` |
| 不可精确执行 | 100% deterministic |
| 不可搜索优化 | 参数可独立调整，适合贝叶斯优化 |
| LLM 生成后需人工翻译 | LLM 直接生成可执行结构 |

### 参数优化示例

```python
# 网格搜索最佳大招阈值（取数口径真实；搜索循环从简）
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine

def evaluate(threshold: float) -> float:
    build["build"]["policy"]["parameters"]["ULT_THRESHOLD"] = threshold
    engine = CombatEngine.from_compiled(
        compile_encounter(build, stage),  # build/stage：build.yaml / stage.yaml 加载的 dict
        seed=42,
    )
    state = engine.run()                  # → BattleState（无 .dps 属性）
    return state.total_damage / max(state.clock, 1e-9)   # DPS 现算

# 在 [100, 140] 区间逐值扫描最优阈值
best_threshold = max(range(100, 141, 5), key=evaluate)
```

### 策略与 Encounter 的关系

策略不进 `Encounter`——`Encounter` 只有布场与终止条件；策略声明在 build.yaml 的
`policy` 块，经 `_compile_policy` 编译进 `CompiledEncounter.policy`，运行时由
`CompiledPolicyRuntime` / `ScriptedPolicy` 通道执行（见 `sim/policy_api.py`）。

```yaml
encounter:
  encounter_id: "E_001"
  name: "示例关卡"
  cycle: {first_cycle_av: 150, subsequent_cycle_av: 100}   # 可选，None = 不启用轮次
  actors: [...]          # 我方 + 敌方布场
  termination: {mode: "fixed_av", max_action_value: 1500}
```

（字段按 `sim_schema/encounter.py` `Encounter` 重写——现役字段：`encounter_id` / `name` / `cycle` / `actors` / `termination`；旧示例的 `formula` / `globals` / `initial_modifiers` / `policy` 不是 Encounter 字段。）

同一个队伍配不同策略，可以对比不同操作手法的差异。

战前秘技顺序和进战策略单独在 `20_pre_battle_strategy.md` 中定义，可与 policy 组合使用。

---
