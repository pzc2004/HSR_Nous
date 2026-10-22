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
`ByCompareSkillUsageLimit` 收 `IDFromTriggerKey` + 固定非负整数 `ActionDelay`，或已有
逐实例/关卡初值证据的 `_GlobalDelay` 单值读取：初始无使用记录时可用，执行对应技能后在
该技能的既有 `cooldown_left` 上写入 `max(AI_CD, ActionDelay)`，每回合末统一递减。
这里把 ActionDelay 对齐到回合冷却轴仍是实现期候选，待真实 golden；未登记的动态表达式、
目标/共享技能选择及显式 `LimitTimes` 均拒绝，不按 0 或 1 猜测。
静态支持表在 `sim_schema/config_ai.py`，未登记节点、目标选择器或技能不会写入 config；
队伍计数的 `CasterSummonedMinions` 别名只统计 `summoner_id` 等于施放者的敌方存活召唤物；
`AllLightTeam` 指我方全队，`AllDarkTeam` 指敌方全队，`AllDarkTeam - Caster` 再排除施放者；
`AllLightTeam.RemoveServant` 与技能目标别名 `AllEnemyIgnoreServant` 只保留非召唤我方角色，
召唤归属均由 `summoner_id` 判定；`TauntOrAggroEnemy.RemoveServant` 按同构上游分支同口径处理。
`Monster_W4_Griffin_00_LocalLegend_Partner` 与 `AllDarkTeam - Caster` 同义，仅含其他存活友方。
`Monster_Svarog_00_Unselectable` 对应无 `RL` 的 `W1_SvarogPart` 存活友方；
`Monster_Svarog_00_RL_Unselectable` 对应同时带 `W1_SvarogPart` 与 `RL` 的存活友方。
Claymore 的 `BlackSummon` 仅含 `4032052`（Black Tide's Decrepit Bow）与 `4032042`
（Black Tide Council），`WhiteSummon` 仅含 `4012033`（Furiae Archer）与 `4012023`
（Furiae Philosopher）；这些具名集合与 `CasterSummonedMinions` 的初始决策评估都按 0 个处理。
`Monster_W4_Claymore_01_Skill02_Target` 在非召唤我方角色中按 buff 实例数降序选择，数量相同按编队序。
动态键缺省为 0；`AIFlag`、`AICounter`、`AICounter_01`（允许怪物名前缀）缺省为 1。
`CONFIG_AI_INITIAL_DYNAMIC_VALUES` 以 `(AIName, 怪物 ID)` 为键收录经
`ConfigCharacter.CustomValues` 或 `PassiveSkillInitiate` 对账的初值（空 ID = 同 AIName 公共默认，
具体 ID 优先）：`Monster_W1_Bronya_00_RL.Bronya_AICounter_Act1=1`、
`Monster_XP_Elite01_00.Phase_Flag=1`、`XP_Elite01_01.Phase_Flag=1`、`AIFlag=1`、
`Monster_AML_Elite01_00_AICounter_01=2`、`AICounter_02=1`、`BreakCounter=0`，以及
`1004030`/`100403002` 的 `Bronya_AICounter_Act2=2`，
`3002010`/`3002011`/`3002021` 的 `FlopSide=-1`、`AIFlag=0`，`3002041` 的 `FlopSide=-1`、`AIFlag=1`，
`Monster_W2_Huanlong_00` 的 `AIFlag=0`、`Phase_Flag=1`，以及
`Monster_W2_Yanqing_00` 的 `W2_Yanqing_00_AICounter=1`、`W2_Yanqing_00_AIPhase=1`、
`W2_Yanqing_00_MaxPhaseNum=1`（PassiveSkillInitiate 对账后升为公共默认）。
静态初始决策评估与运行时共享该表，不让共享
AIName 的不同怪物串用初值。
初始决策评估不用怪物总数冒充。默认动态值/阶段 1 下
无可执行决策的配置，
在有序列时只保留原始序列候选并记 notes，不拿旧
sequence 解释器冒充完整专属 AI。`SelectAISkillTarget` 支持 modifier id/name 匹配及
`MCommon_DOT_Electric` / `MCommon_DOT_Burn` 的触电/灼烧目标识别；无对应自定义标记时
回退到现有默认目标。`Retarget` 按 `TargetType` 与 `Predicate` 过滤候选，仅收 `MaxNumber=1`：
成功时把首个候选（roll 且 `ByRandom` 时随机一个）写入 `target_override` 并执行 `TaskList`；
空候选清除目标覆盖并执行 `FailedTaskList`。`AIComplexSkillAISelector` 仅收自指一技能的
`UseSourceInSkillConfig == SkillName` 用法，目标覆盖留空并沿用 action 自身目标解析；跨技能引用拒绝。
`AIMonsterRankSelector` 当前仅收
`PropertyStrategy=Max`，在怪物候选中保留 Rank 数值最高者（并列全保留），供 Compose 求交集。
`CasterSummoner` 目标别名按 `summoner_id` 反查存活召唤者；非召唤物或召唤者离场时无候选。
`AITaskTargetTypeSelector.TargetType` 也接受 `TargetSequence`（别名/过滤/编队排序/索引）；
`TargetIndex.IndexType` 缺省按 `IndexStrict` 处理。`ByTargetListAny` 按 `TargetType`
解析候选，任意一个满足 `Predicate` 即为真；目标别名/序列仍走静态支持表，未知项拒绝。
`AICustomStringTagSelector` 按 `Actor.groups` 中的 `CustomStringTag` 过滤，
`InverseResultFlag` 取补集；敌人模板 `groups` 来自上游 `CustomValueTags`。
`SwitchCaseByDynamicValue`：Switch 为 `AQAR` 单动态值读取。键名可静态解析
（SkillParam 符号/只读 CustomValue）时生成期选定唯一 `CaseTaskList`，无匹配走
`DefaultTaskList`；键名解析到**本敌动态键**（生成期被写过的键，含可变 CustomValue）时
翻**活读**——每个 Case 的任务编译为 effect 级条件守卫 `dynamic_of($self, '键') == Case值`
的分支组（数值用变量、结构用组合，不加新原语），无匹配且声明 `DefaultTaskList` 时其
守卫为全部 Case 值不等；Case 值必须是静态数值且不重复。哈希缺失/冲突仍显式拒绝，
不猜测哈希含义。
`ByCheckCustomValueBool` 的 `Key.Hash` 经同一哈希算法与 pipeline 全量 `CustomValueTags`
名册对账并归一化为 `Key.Value`，运行时检查目标 `Actor.groups`；未解析键以
`custom_bool:Key` 拒绝，不把未知哈希当成恒假。`ByCompareHP` 以 `hp_of(target)` 读取当前
绝对 HP；`CasterSummoner`/`ModifierOwnerSummoner` 经 `summoner_of` 寻址，其他目标别名仍拒绝。
`ByTargetAliveState` 仅收 `Mask_AliveOnly` 并调用 `actor_alive`，支持 `Inverse`；
`Mask_AliveOrLimbo` 不把 limbo 近似成存活或死亡，继续显式拒绝。
`ByHasSummonRelation` 分别解析 `SummonerType` 与 `ServantType`，编译为
`summoner_of(servant) == summoner`，支持 `Inverse`；不能只检查召唤者字段非空来代替双向关系。
`ByTargetEntityType` 的 `Servant` 编译为 `actor_type_of(target) == 'summon' or
summoner_of(target) != ''`，同时覆盖我方召唤物与仍按 monster 登记的敌方召唤物；`Avatar`
取其反，支持 `Inverse`。当前只收缺省或 `Anyone` 的存活掩码，不把额外 AliveState 与类型取反混为一谈。
modifier 驱动的动态值迁移用 hook `set_dynamic_value`（`dynamic_key` + `amount`）写入目标敌人的
`dynamic_values`；目标必须已有敌方 policy 运行态，不写另一套影子计数。动态值和 `current_phase`
与冷却一样进入存档。`SetDynamicValueByProperty` 的 `Attack`/`Speed` 读取当前有效面板，
分别编译为 `stat_of(..., 'atk')`/`stat_of(..., 'spd')`；`BaseAttack`/`BaseSpeed` 仍走
`base_stat_of`，不混淆基础值与当前值。DoT `OnPhase1` 的 `CurrentHP` 映射 `$self.hp`，
与 `MaxHP` 映射 `$self.max_hp` 同为跳伤时持有者现值。`SetDynamicValueByProperty` 在
Retarget 内读取 `ParamEntity` 时，`target: self` 仍写施放者动态值，另以
`amount_target: ctx.retarget` 绑定 `$target` 求值语境；逐读取目标依次写入，空候选不写。
`CasterSummoner` 经 `summoner_of` 解析召唤者；`MaxStance` 以
`base_stat_of(..., 'max_toughness')` 读取基础韧性上限，`CurrentStance` 以 `toughness_of`
读取当前韧性。`DefineDynamicValue`/`SetDynamicValue` 的自指动态键读取改用
`dynamic_of($self.actor_id, key)` 在效果执行时取值，不再要求静态字面量。谓词写入后读取
（同技能 `Set/Define/Add/Copy` 或 `SetMonsterPhase` 之后再 `ByCompareDynamicValue`/
`ByCompareMonsterPhase`）自执行帧（#26）落地起**改翻帧感知活读**：整支谓词编译为
**单 hook + 纯 effect 级 condition**（effect 级 condition 是执行时活读，读得到帧覆盖层
的未提交写入），不再以"旧事件快照"拒收；PostfixExpr 里被写键的动态哈希经键名反查表回落为
`dynamic_of($self.actor_id, key)` 读取（同名哈希冲突不回落）。无写后读的普通谓词仍走
hook 级快照条件（事件间确定性语义不变）。`SetDynamicValueByModifierValue` 的 `Layer`/`LifeTime`
读取分别编译为 `stacks(...)`/`modifier_duration(...) × Multiplier`；省略 `ReadTargetType`
时读取施放者/当前 modifier 持有者的已命名 modifier，`ParamEntity` 同样经 `amount_target`
逐目标求值，其他值类型与其他目标仍显式拒绝。DoT 数值读取与摘除共用同技能来源绑定闸，
不能把其他技能生成的 DoT ID 拼到当前技能上。

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

敌人机制迁移期的首选结构路径是 `adapters/enemy_ability.py`：`CharacterConfig.SkillList`
以 trigger/`EntryAbility` 对齐 TBGD 技能，编译器递归消费 Ability 任务树与 modifier 定义；
`PostfixExpr` 的动态哈希必须能由 `DynamicValues.Floats.ReadInfo` 或 modifier 内的显式赋值
还原。`TASK_HANDLERS`/`EVENT_HANDLERS` 未注册的节点、无法唯一绑定的被动、缺失引用和
未证明的条件分支都记为 `unsupported`，不得拿部分结果冒充完整收编。写后读/概率分支经
执行帧改翻后，"同一技能写入后读取动态值会命中旧事件快照"与"运行时 Switch 尚未注册"
两类旧拒因退役；概率分支限主动技能域（事件域帧外发射暂不注册），战斗级随机记忆
（`RandomUnique`/`RandomMaskKey`）保持显式 unsupported。完整支持的主动技能
在正式生成器中优先走该路径；下述 Fandom 文本转换属于尚未迁移机制族的遗留路径。
`TargetInfo.AllTeamMember` 映射 `ally_aoe`，敌方行动时该类型返回全部存活友方怪物，
不落入玩家目标池。属性件仅在整个 stat 块可静态证明全为增益时标 `buff`；正向
`vulnerability`、任一负向其他 stat 或任一未判号表达式仍按保守 `debuff` 处理。
条件伤害只在谓词分支前已有主伤记录时转为 `on_action` 的 `deal_damage`，保留分支条件；
此时它属于主伤后的附加段。谓词前没有主伤时仍拒绝，避免条件主伤或后续主伤被错误重排。
概率分支（`PredicateTaskList` 的谓词为 `ByRandomChance`，109 节点全为静态 Chance）编译为
**单 hook + effect 级 condition**：前置 `bind_roll`（`roll_key` 按节点路径生成稳定键，
`scale` 缺省 1）绑定共享掷骰，Success 分支效果带 `roll('<键>') < Chance`、Failed 分支带
`roll('<键>') >= Chance` 的 effect 级 condition——hook 级快照发生在任何 effect 之前，
概率分支必须落 effect 级（执行帧 `23_event_hook_system.md` §23.15）。`RandomConfig`（无 `RandomUnique`/`RandomMaskKey`/
`RandomCount`，权重静态且和为正）按同一结构翻译：bind 带 `scale=Σ权重`，各选项守卫为
累计权重区间 `roll('<键>') <= 累计_i and roll('<键>') > 累计_{i-1}`（与上游
`rng.random()*Σ <= 累计` 同浮点序）；带战斗级记忆字段（`RandomUnique`/`RandomMaskKey`/
`RandomCount`）的节点保持 unsupported 进 human_queue，禁止猜测。事件域（被动/生命周期回调）
的概率分支因可在帧外发射（DoT 跳伤致死等）暂不注册，只翻主动技能域；写后读类活读
（不消耗随机流）两域均可。`bind_roll` 的 expected 模式绑 `0.5×scale`（0.5 取 0.5 的下邻
浮点），与 `mechanic_chance` 的 `p>=0.5` 期望口径逐比特一致。
`SetDynamicValueByCopying`（自指目标）编译为 `amount: dynamic_of($self, '<FromKey>')`
的 `set_dynamic_value`；`SetDynamicValueByAddValue` 的 Min/Max 钳制用表达式
`min(max(dynamic_of + AddValue, Min), Max)` 内联组合（AddValue/Min/Max 可为已解析表达式，
读的是帧覆盖层旧值——帧内累积语义），不加引擎原语。
单目标 `FireProjectile` 允许缺省或 `AbilityTargetEntity` 主目标；`OnProjectileHit` 支持
主目标直伤与已注册的非伤害任务，Retarget 内投射物仍拒绝。`FireWaveProjectile` 以
`Count` 展开为 `Action.instances`，逐段复用 `PerProjectileDamage`；`OnProjectileHitClientOnly`
仅在接受纯表现时忽略。

语义对齐不再按整表 zip：每个 TBGD 技能逐个尝试 Fandom 候选，只接受唯一转换；
一个语义不得服务多个原始技能，冲突时只有原始顺序也能对齐才保留，其余拒绝收编。
`PassiveSkillInitiate` 与 `SkillPxx` 只进被动扫描，不进入主动候选或主动位次；Fandom
`Talent` 同样不计主动位次，避免被动行让后续主动技能整体错一格。

生成器只为 Fandom 语义能与 TBGD 主动技能逐项对齐的**单段直接攻击**生成 action：
倍率文本须与 `ParamList` 逐值一致（single/AoE 一个值；Blast 主邻同倍率一个值或主/副
两个值），目标范围只收 single/Blast/AoE，`DamageType` 须一致；`SPHitBase` 为非负整数，
字段缺省按值类型默认值 0（`MonsterSkillRow.SPHitBase` 为 `FixPoint`），并显式写 `energy_gain: 0`。
Fandom `energy` 是 per-attack 受击回能，写 `energy_grant`；缺失时为 0。
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
确定两参数与 `Base Chance` 三参数两态，复用 `delay_action`；Suppressive Fire 的省略文本
实例按已核 Ability 两槽结算 300% 与 30%。effect `amount` 使用百分数，`apply_chance`
与 modifier 共用效果命中/抵抗，抵抗时不推条。
固定次数、每段同倍率的 Bounce 直接复用 `target_type: bounce` + `instances`；每段随机
主目标且同时命中相邻单位的变体写 `bounce_blast`，副倍率/副削韧与 `blast` 同槽。
已核实例的 Midnight Tumult 按上游两段各 50% 结算，不泛化到同名技能；省略文本从原始四槽
补齐伤害、概率、持续与 DoT 倍率。Caressing Moonlight 前两段只打主目标，第三段按 50%
主倍率同时打相邻目标；主目标 Shocked 时副目标也 Shock，省略实例从同怪 Skill01 补齐参数。
Sawing Evil: Sever 按 Ability 两段结算 200% + 240% Wind，每段削韧各 10；
`instance_variants` 逐段保留不同倍率，不把 440% 写成单段。Maddening 在 `on_battle_start`
挂 `MMonster_W2_Valkyrie01_01_SkillP01_ComboAttack`，供专属 ConfigAI 选择 Sever。
Happiness Charm 的三个随机分支可携带原始 `weight`；Strong Reverberation 持续 1 回合，
并在施加时推条 25%，不再写成无时长、无推条的永久控制。Windmill Defacer 单次发放
Punchline +2，按 `MCommon_Shake` 以 50% 基础概率施加 1 回合强震并推条 20%，不套前例 25%。
Autonomous Wand 的 Magic of Smiles 以持有者 used modifier 保证每个单位首次受击仅一次：
攻击方队伍 Punchline +3，并以 `trigger_action` 代放 Happiness Charm，不套全队共享 latch。
右侧优先、重复目标追加段的 Barrage 不冒充普通 bounce，改用 hook `barrage_damage`；
`instances_expr` 支持动态段数（Weeping Arrow 按 War Armor 是否大于 0 取 5/1 击）。
Collision of the Third Orbit 的四槽依次对账 300% 物伤、40% 概率、1 回合与 40% 推条：
War Armor 非零时对主目标施加 `MCommon_Unstable`，归零时改对自身施加
`MCommon_Unstable_Monster`；两者受击后分别转为对应 Shake，禁行动并推条 40%，
不是只结算 300% 直伤或把 40% 概率误用到破甲自伤分支。LocalLegend 变体的 Ability
则只有 300% 单体物伤，没有 War Armor/Reverberation，按 raw-only 直译且不挂这些 hooks。
基础 Rite of Great Arbor Metamorphosis 的省略段数按 Ability 的 FirstHit、两次模板与末段
收编为四段，每段分别施加 Wind Shear，不凭 Fandom 省略文本猜段数。
Black Prana's Snare 用 `recoverable_hp_reduction` 记录 30% 初始可回复上限削减，另以资源
累计 `after_being_hit.amount / max_hp`；受击重挂只刷新 2 回合时长，总削减封顶 99%，
净化或到期后清空累计资源。治疗管线按该值钳制可回复上限，当前 HP 高于上限时不反扣。
The Ascended (Bug) 每次施放另叠 20% 基础比例，基础与受击两本账合计封顶 50%、持续 3 回合；
Vitals Drained 只接受该怪自身攻击，按 `on_hp_decrease` 的实际 HP 损失累计并刷新。
首次施加从空账开始，重复施放保留累计，净化或到期同时清两本账。
Fickle Fortune 用 `before_take_damage` 的 `modify_amount: 0` 免伤；Gamble 目标攻击时
由 `random_choice` 六选一并 `set` 数值，未进入 Gamble 的攻击者不触发。原始两槽仅服务
DeathRattle 的伤害与削韧，Fickle 本体不读取，故不再按 ParamList 非空误拒。
Eternal Continuation 用 `fixed_hp_bars: 5` 统一固定直伤/DoT/击破伤害；破韧攻击由直伤与
击破各扣一条，不再叠加 `on_break` 扣血。
Swallow Return 召唤四把飞剑并给彦卿挂剑阵（SPD +50、锁韧），飞剑模板 ID 读取各变体自身的
`SummonIDList`。每把飞剑由 `random_choice` 独立选定 wind/thunder/imaginary 隐藏阵眼；
召唤引用的 `weakness: []` 覆盖上游三属性候选池，对应属性命中后摘除隐藏件并以
`weakness_add` 揭示唯一真实弱点，未揭示前由 `toughness_lock` 阻止削韧。飞剑击破即消灭；
全灭时 `actor_exit` 解除剑阵，并以 `drain_ratio: 0`、`floor: 1` 流失彦卿 10% Max HP（不致死）。
Reverberating Ice 先结算主/邻冰伤并解除主目标冻结，再以 `trigger_action.target` 随机选择
仍冻结的相邻目标递归施放；每次递归改以该相邻单位为新主目标，无合法候选时停止。
目标选择来自上游 Ability 的 `Retarget(ByRandom=true)`，不是反复攻击最初主目标。
Free Drinks 在 `before_take_damage` 按原 `action_id` 记录逐段盾前状态，段后按命中结算反噬；
无盾目标才进入冻结分支，破盾不会把有盾命中误判成无盾。SoulGlad Party 的两次召唤使用
原始 `SummonIDList`，两个参数对应两次召唤延迟。Unlimited Free Drinks 的文本 380% 与
TBGD 360% 冲突，未收编，不替任一源强行对齐。
Startling Broadcast 以 `available_if` 限定 Fright Channel，结算 160% Quantum AoE 后由
`consume_energy` 逐目标扣减各自 20% Max Energy；扣能走 `pipeline.consume_energy` 并钳到 0，
不把负值塞进 `gain_energy`（该入口按设计忽略非正获得量）。
Banascary Semester 同走 `consume_energy`，但为 Classroom Channel 限定、150% AoE 与 15 点定值扣能；
按目标当前能量钳到 0，不按 Max Energy 比例另造公式。
Rapid Gambit 复用 `immediate_action` 作用于全部友方怪物，对应上游
`SetActionDelay(AllTeammate, 0)`；该 Ability 不读取 ParamList 完成此效果，不另编参数含义。
Rapid Gambit: Urge 先给全部友方怪物叠 6% 增伤再立即行动，重复施放按层数累计，
不后置于队友行动之后。Rapid Gambit: Slay 仅在第三阶段同时叠 6% 增伤与 6% 速度，
同样先于全队立即行动。
Twig of Marple Leaf 的 Engender 保留上游 `MMonster_W2_Xuanlu_02_Buff` 作为 modifier_id，
ConfigAI 据此在强化与 Leaf Hinging 分支间选择，不另换内部 ID 使谓词失配。Retaliation 的
`MMonster_W2_Xuanlu_02_Counter` 以 1/2 层承载 CounterCheck 未就绪/就绪：`on_turn_end`
补至 2 层，`after_being_hit` 仅在 2 层时扣回 1 层并 `trigger_action` Leaf Hinging；
对应上游每回合一次反击，不是每次受击都触发，也不移除 Counter 本体。
Silvermane Lieutenant (Bug) 的 Shield Reflect 直接 `trigger_action` Pierce 攻击来源并消耗
Counter；该变体没有普通版的 ReturnAttackTarget 选择器，不套用标记 + ConfigAI 反击链。
Enrage Order 按文本与第三 ParamList 对齐的基础概率对全体施加 `control_kind: taunt` +
`forced_taunt`，第二参数给出持续回合；被嘲讽的玩家主目标强制指向施加者，首个 ParamList
不参与该效果，不另猜用途。公共 `MCommon_CTRL_Taunt` 同走该结构，并同时声明
`remove_on_source_death` / `remove_on_source_exit`；`ByContainBehaviorFlag(Taunt)` 直译为
`controlled(target, 'taunt')`，不再按纯表现件跳过。公共 `MCommon_CTRL_Frozen` 生成
`control_kind: freeze` + `prevent_action` 的控制件，并按任务的
`Modifier_Frozen_DamagePercentage` 在 `on_turn_start` 对冻结持有者结算 Pursued 冰伤；
随后才进入既有冻结跳过与 50% 补偿路径，倍率缺失仍拒绝。
Frozen Storm 按上游五段 `deal_damage` 结算（15%×4 + 40%，削韧 0.75×4 + 2），随后施加
Deep Freeze；每层 `res_ice +0.12`、`spd_pct +0.2`，最多 3 层，与原始参数逐项对齐。
Feast That Is Set For You 复用 `random_choice` 对全体施加 Poison 或 Electric：各 50% 分支；
ParamList 依次给出施加概率、持续回合、DoT 倍率，基础实例为 100% 概率、2 回合、120% ATK
DoT，Poison 最多 5 层、Electric 最多 1 层。
Precious Blood Shed For You 以 `target_type: single` 只对主目标施加同组随机 DoT；第四、五
ParamList 分别是 Poison/Electric 层数上限，基础实例均为 3 层，不写死全体的 5/1 上限。
A Cup Runneth Over For You 复用同组 `random_choice` 对全体施加随机 DoT，并以 self
Charge action 推进到 Wash Away All Sins For You；三个参数同样为概率、持续和 DoT 倍率。
Wash Away All Sins For You 将 `TriggerModifierCustomEvent(EventType.Value=1,
DynamicKey=DOT_TriggerRatio)` 直译为 `trigger_dot`，比例读取本技能 ParamList（基础实例
1.25），随后按 `STAT_DOT` 摘除；紧邻且定义缺失的 `MCommon_SkillTarget` 是该内建事件的
寻址标记，不另生成 DSL 件。有 `trigger_dot` 的技能不再被误判为缺少直伤。目标数量沿用
`Retarget(ByRandom=true)` 的现有结构化规则；Fandom 的全体描述与该结构存在口径冲突，
留真实 golden 复核，不靠文本擅自改写目标数。
Frigid Waterfall 的 SPRL 实例结算 380% AoE 冰伤并叠加 12% 自身增伤；其 Skill04
全 Ability 不读取第三 ParamList，仅该已核对 ID 接受对应三参数布局。
Sky-Piercing Lance 按已核对的原始 ID 分别结算 5 段 120% 或 6 段 100% Imaginary Bounce；
这些 ID 的 Skill04 Ability 均已核对，第三 ParamList 不参与段数或倍率，不泛化到其他技能。
Thunderstorm Condemnation 按原始参数生成多段 Lightning Bounce，并以 `after_being_hit` 逐段
判定 Shock；基础实例为 8 段 100% ATK、50% 概率、50% ATK DoT、2 回合，不在行动末只挂一次。
Void Cannon 以 33%/33%/34% 三段结算 400% ATK；75% 概率施加三层 Detonated，受击后追加
40% ATK 附加伤害并消耗一层，最后一次摘除。Overloaded 不用 `prevent_action` 阻断 Thermal
Barrier，而以 `available_if` 禁止再次攻击；Thermal Barrier 仅在过载时可施放并解除该状态。
Mirage Rush 分别挂自身 CommandMark、团队 CommandMarkLevel（`effect_scope: team` +
`mirage_rush_active` 标记）与目标 CommandMarkTarget，击破/死亡全链解除；Rumination of
Putrid Dream 仅在 `stat_of(..., 'mirage_rush_active') > 0` 时追加一次 200% 量子伤害。

敌人模板与角色模板共用 `custom_resources` 声明及 Action 资源字段：`resource_gain` 获得计数，
`instances_from_resource` / `instances_base` / `instances_per_point` / `instances_cap` 驱动段数，
`scaling_from_resource` / `scaling_per_point` 驱动 ATK 倍率增量，`consume_all_resource`
在段数和倍率定格后清空计数。编译产物把敌方资源声明并入 `resource_decls_by_actor`，
setup 与召唤布场均复用现有初始化通道。首个实例是 Obscure Blaze：
基础 1 击 + 每层追加 1 击，资源上限 3，因此总段数上限 4。
Gusto 不设上限：Wrathful Roar 获得 3 层并以 `lock_on` 标记监视目标，角色战技事件重定向该
标记；Simian Strike 以 `resource_gain: -1` 消耗，`available_if: res_gusto > 0` 在序列与
ConfigAI 两条选择链统一跳过空资源攻击，耗尽后清除标记。theBowja 与 TBGD 双源确认的两个
同名猱击原始 ID 可共享同一语义，不再按“一语义只能服务一技能”误删。长右（错误）改用
战技事件计数（最多 3 层）：Skill01 以 `scaling_from_resource` 表达 300%+200%×元气的单击，
Skill02 造成 50% 行动延后，弱点被击破时清空元气与监视。
Calamity Power 同样不设上限：Dying/Silent Sorrow 分别获得 6/8 层；But Suffering is Essential
以 `instances_per_point: 2` 结算每层两段 20% 并追加一次 200% 终结 AoE，`available_if` 阻止
空资源施放，耗尽在 `on_action` 终结段之前完成。Cry Not For The Discarded 改用
`instance_variants`：首段 250% 主击，其后每层一段 40%，最多 8 层追伤；敌人行动编译器
同样保留段级变体。

Garrison Aura Field 以目标代数选择首个其他友方并挂一次性 Barrier；`before_take_damage`
把首次攻击伤害改写为 0 并消耗该件，DoT 不走该事件因而不被拦截。目标选择是实现期候选并在
notes 留痕，待真实 golden 定稿。Fealty 复用同一 waterfall：先按 `category: "true"` 将原伤害
同额结算给 Security Doggo，发放 Punchline +3 并消耗标记，最后把保护目标的伤害改写为 0；
后续无标记攻击正常扣血。

Fleeting Veil 作为独立被动 hooks 保留：`before_take_damage` 仅对 Basic/Skill/Ultimate/Follow-up
把承伤改写为 90%；`on_action` 以 20% 基础概率给攻击目标挂 Imprisonment，并复用
`on_apply: delay_action` 推条 50%，不依附主动技能收编完整度。
Disembodied Shell 在 `on_battle_start` 注册未击破 60% 减伤与击破后 50% 易伤的条件件，
`on_break` 推条 75%。Planeshred Claws 的两个普通变体复用同一被动形状，从同怪 Skill01
后三槽读 40% 减伤、50% 推条与 50% 易伤；IF 变体的 PassiveSkillInitiate 不含守备，不附加。
被动扫描同时接受 `PassiveSkillInitiate`、`SkillPxx` 与 Talent 语义
（原生被动 ID 优先，Talent 只补未覆盖语义；仍须精确转换且唯一匹配，防止重复挂载）。
Cruelty 在 `after_being_hit` 检查 Shocked
目标，友方或 `controlled(source, 'dominate')` 命中时追加一次雷伤，并以专属 action_id 排除
追加段自递归。
Fiery Majesty 以 `stack_mode: refresh` 每次施放叠一层，`stat_exprs` 按层数计算 20% 增伤，
上限三层；`on_action` 后挂载的持续回合按现有 +1 口径处理。
Power Amplification 复用同一叠层通道，对全体友方每次施加一层 15% 增伤，不设时限与数值上限。
Phonation Unbound 在参数对齐的布局中以 modifier `shield.scaling.hp=0.09` 生成护盾，
并写 `all_dmg=0.2`；其他未对齐布局仍拒绝。
Vaneggiando 施加 Alien Dream（禁行动、按原始参数的易伤、2 回合），`on_turn_start` 以
`$target.max_hp` 比例回血（Great Septimus 35%，其他 5%），`after_being_hit` 立即解除。
All Is Calm 的 150% 实例使用 20% 易伤与 5% 回血；Sleep 的 75% 概率与文本 50% 冲突，仍拒绝。
Radiating Venom 的 Entanglement 以 dot 承载 60%×层数延迟伤害与 50% 推条，
`prevent_action` 禁行动、最多 5 层，并在同一 `on_action` 召唤一个 Gnaw Sting。
Fallen Star's Visit 复用同一原语，改为 50%×层数、30% 推条与 30% 基础概率。
Thick-Skinned 在 `on_battle_start` 挂 150% DEF，`on_break` 摘除；新阶段重挂仍待阶段机收编。

AoE + Imprisonment 已收编单段与 `ATK × N` 多段文本：概率、持续、推条和减速参数逐项
对账；单体另支持 locked-on 目标与 `on the attacked target` 语序（Track Down）。
控制 modifier 的 `on_apply: delay_action` 与 `apply_chance` 共用一次施加判定，
使命中目标的推条/减速同时发生、抵抗目标两者均不发生；多段总倍率与每段倍率交叉校验。
Ice + Freeze 收完整四槽、100% 基础概率省略概率槽的三槽、原文省略延迟倍率及原文省略
全部数值但 TBGD 四槽齐全的布局；主动冰伤按上游五段各 20% 结算，`on_turn_start`
按延迟倍率补一次冰伤，持续回合取原始槽。
Spirit Whisper 以 120% 基础概率施加三回合 `control_kind: dominate`，并把 `immediate_action`
放进 `on_apply`，因此仅在支配成功时立即触发强制普攻，目标阵营由现有支配回合逻辑决定。
Oppressive Embrace 以 `control_kind: restrain` 禁止目标行动，并用 `deal_damage` 的
`amount=0.5*$target.max_hp` 走物理直伤路由；机械臂被击破时按 modifier id 解除拘束。
Disabling Field 复用同一路由，目标代数只取一名 `controlled($it, 'restrain')` 目标，
没有拘束目标时不造成伤害。原始参数未解释的变体仍拒绝收编。
Heaven's Binds 以 self 支援 action 推进行动序列，并在 `on_action` 对自身调用 `immediate_action`，
形成一次额外行动。
Spiral Arrow 以目标侧 `lock_on` 固定下一次 End of Bow 主目标；End of Bow 的纠缠复用
`dot + on_apply delay_action` 表达延迟伤害与推条，并在行动后解除锁定。Nihility's Command
用 bounce 仅作随机单体选择，随后全体敌方单目标攻击都读同一 lock_on，并保留 10% 易伤。
Double Waxing Moon 以目标代数给前两个我方目标挂 `lock_on`；Sixfold Plenilune 的 hook 伤害
只选择携带该锁的目标，再施加 Oronyx's Mark，不把 AoE 文本误扩为全体命中。
Light the Future 锁一个目标；Praise Aquila 直接复用 Blast 主邻结算，`on_action` 再以
`has_modifier or is_adjacent` 选择主邻命中者施加 Aquila's Mark。
Sweep the Left!/Right! 的省略倍率实例按原始单槽 280% 结算，左右目标代数不变。
Triple Waning Moon 复用 Sweep 的目标代数 `-formation + take 3`，从右侧连续取三目标，
伤害后施加 Oronyx's Mark，并按同一目标集恢复受击能量。Heralding the Dawn 改用 `formation`，
并先 dismiss 再召唤四只 Meteoric Eagle（Fandom 写 3，但 Ability 与 SummonIDList 均为 4）。
Hemotort Teethgrind 按各实例文本倍率结算，有盾分支分两类：`reduce instead` 时不直接扣血并
`reduce_toughness(amount=60, floor=1)`；`trigger Barrier Recoil` 时伤害照发并额外
`reduce_toughness(amount=60, floor=0)`。两分支都在 `on_action` 分流，不依赖
`before_take_damage` 不存在的 action_id。
Hemotort Resonance 按上游 parallel ability 给自身及场上其他 Ichor Memosprite: Pheasant
施加 `MMonster_W4_Turkey_00_Skill02_Power`，已有该件的目标不重复挂载；专属 ConfigAI
先以 Resonance 建立 Power，再轮换到 Hemotort Graze。

Summon 目前限模板与数量明确：生成 self 支援 action 与 `on_action` 的 `summon` effects；
每个实例有独立 summon_id/enemy_template/level，`CompiledStage.enemy_summon_defs` 与 build 的
`summon_defs` 合并，召唤物的 actions/policy/hooks 也进入同一编译链。`Consumes HP (N% Max HP)`
变体先经 `drain_hp` 消耗再召唤，原始参数与比例逐值对账；英文单复数名称只在元数据严格
对应时放行。`SummonIDList` 多模板已收 Twin Bond、Omen、Spear & Shield 与 Siege Support；
随机/多模板召唤按原始名单允许同种组合，Siege Support 另给主目标挂 `lock_on`。
Automaton Grizzly (Bug) 的 Detonation Order 按 `SummonIDList` 名称分别落实
Automaton Spider ×2 + Automaton Beetle ×2，不把“两种各两只”压成总数两只。
Rallying Howl 的上游 `InheritPropertyList=[CurrentHP, MaxHP]` 复用 `12_summon.md` 的 `max_hp_ratio: 1`
召唤引用覆写（只覆写 Max HP，其余属性仍读召唤模板），再以 `actor_enter` hook 和
`set_hp_to_percent(percent=$self.hp/$self.max_hp)` 对齐召唤者的绝对当前 HP；敌方召唤引用
编译时把该比例传入既有 `SummonDef`，不另立 HP 继承原语。`SummonMonster.DelayRatio`
尚未进入时序结算，必须在 notes 单独留痕，不能由技能的 `DelayRatio` caveat 代为掩盖。
阶段召唤和召唤链资源条件尚未覆盖。

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
The Can's Creed 在 `after_being_hit` 按攻击属性植入独立 modifier，`weakness_count < 2`
保证最多两种且重复属性不重复计数；`on_break` 复用 `leave_battle` 以 flee 离场，不走击杀链。

Hardy Leaf Sheath 生成 self 加防 modifier，并以 `toughness_lock` 阻止存续期间削韧；
self `on_action` 后挂的 1 回合效果同样按声明时长 +1，避免当回合末先到期。
扑满倒计时技能生成 self 支援 action 并由原始序列推进；ConfigAI 明示
EscapingCharge 标记时从原配置提取真实 modifier id，并以 `singleton_group` 保证
Charge02 替换 Charge01，使后续决策继续推进。立即逃跑项复用 `leave_battle` 发
`actor_exit(reason=flee)`，不走死亡检查、不发 `on_kill`。Run 仅匹配 Skill02、Phew 仅匹配
Skill03；Fandom 缺条时 Skill01/02 以原始 trigger 与 EscapingCharge 对齐，避免同页语义串配。
Reverberation 受击后由 `after_being_hit` 钩转为 Strong Reverberation：原子推 70% 并
摘除原标记，Strong 的 `prevent_action` 使下一次行动空过且回合末正常结算。
Callous Tailwind 的 `202201001` / `202201003` 经双源确认为同名同文技能，保留两个
action_id；ConfigAI 的 `Monster_W2_Abomi01_00_Revive` 与既有 `ENEMY_REBIRTH`
同口识别，标记存续时选择 Skill01，消耗或解除后选择 Skill02。
Malefic Ape 的 Skill05 没有 Fandom 主动技文本，但 Ability 仅含解除 `Weak` 的机械效果；
按原始证据收为 self action，名称保留技能 ID，不脑补官方名，也不重复实现引擎已有的
回合前韧性恢复。`Monster_Beast02_Attack_Sign` 与 `ENEMY_202302004_MONITORED`
同口识别，完整轮转依次执行咆哮、增伤、三次猱击与 Skill05，之后 `AIFlag` 归 1。
Rapid Gambit: Adapt 与 Urge/Slay 共用 Ability 的 Skill01 两槽 6% 参数；第二阶段只叠
`Monster_Fuyan_00_RL_SpeedUp` 并立即行动，不附 DamageUp，也不复用第三阶段双增益。
Blazing Absorption 上挂自燃时同步 `Phase_Flag=2`。Bomb Warning 以 `absorb_modifier`
吸收全队 Enkindle 并累计层数，下一次 Bomb en Masse 按 75%/层增伤；资源在 `on_action`
后清零，不当次抹掉增伤，随后重新施加 Enkindle 并移除吸收强化件。
Voidranger Trampler 初值 `(AICounter_01=2, AICounter_02=1)` 来自 ConfigCharacter；
`MMonster_AML_Elite01_00_Aim` 复用现有 `lock_on` 判定，完整轮转依次为 Rule of Force、
Spiral Arrow、End of Bow、War Trample、Unreal Projection、War Trample、Rule of Force。
彦卿的同一 PassiveSkillInitiate 初值已升为公共默认，基准及变体共享；九步轮转覆盖全部
六个主动技，Skill02 实际布场四把 Flying Sword，Skill06 后 `AICounter` 归 1。
Searing Prowler (Bug) 的 High-Temperature Operation 与 Melt 复用基准机制及各自原始 ID；
Dancing Cinders 先结算已有 Burn 的追加伤害再重新施加；Scorching Burst 按 Skill08 三槽
依次结算 200% 主目标、100% 邻位与 100% 基础 AoE，追加段不递归，最后按名称摘除 Burn。
Leviathan's Vestige Valor 按技能 ID 分别映射 `8015010` 与 `8015011` 的三部件，
任一存活即 `cancel_event` 免伤，不跨变体复用部件 ID。
Illwish Lotus 的 Fatal Mockery 在 `on_kill` 以击杀者为事件持有者发放 Punchline +5，
不依附 First Bloom 或专属 AI 是否可执行。
布洛妮娅 Skill03 在 `SummonIDList` 为空时仍按 Ability 的显式 ID 收编，实际布场
Silvermane Soldier 与 Silvermane Gunner；AI 未调用该技能不再成为漏收理由。
Omen of Everlasting Freeze 在同 Boss 的总 `SummonIDList` 中只筛选 Ice Edge，避免把
Cocolia/Gepard 等其他技能的目标一并布场。
布洛妮娅（幻象）Skill03 先召唤一名 Silvermane Cannoneer，`dynamic_of($self, 'AIFlag') >= 10`
且友方少于 4 人时再召唤一名，条件与 Ability 同口径，不把强化召唤写成无条件双召。
煽动者以 `AIFlag=0`、`Phase_Flag=1` 起执行 Twin Bond 并布场两莲，后续 Acchata 单体攻击；
两次 Twin Bond 复用同一召唤定义，生成期按 `summon_id` 去重，不重复注册。
普通金人的 Farewell Etiquette 三层进入慎刑：速度固定值 +30、持续 2 回合、立即行动，
召唤两个由实例 `SummonIDList` 与 `W2_Mecha03_00_SummonID` 共同对账的单位；
`201301002` 因其实际实例 ID 召唤 Internal Alchemist，不硬写成灯昼龙鱼。普通形态不套用
错误形态的 75% 速度比例、三回合持续或三目标锁定；错误形态仍保留这些独立证据。
普通 Harpy 的 PassiveSkill 在 `OnListenAfterSkillUse` 中检查技能使用者持有自身状态后，
把 `_ListenSkillUsed` 置 1；生成器用既有 `on_action` + `set_dynamic_value` 保留这条链路，
不把 LocalLegend 的另一 PassiveSkill 错套过来。`MCommon_FastAction` / `_Permanent`
在 AI 目标过滤中同认 sim 的 Stormride 标记。Clock 的 Set Alarm 走无附加效果蓄力，
Wake-Up Alarm 按 Ability 的 `SetActionDelay(AllTeammate, 0)` 只立即行动其他友方；
两者由原始 ConfigAI 的 AIFlag 推进，不另写序列。
LocalLegend Harpy 的另一 PassiveSkill 用 `ByCompareStageID=426007` 分流 `_GlobalDelay`：
成功分支读 `Skill02[0]=6`，其余分支读 `Skill02[1]=12`；`2067290669` 已由
`dynamic_value_hash("_GlobalDelay")` 对账。运行时按 `Encounter.encounter_id` 选值，
不把两个槽位误当成技能效果参数，也不对没有这张初值表的怪物接受动态间隔。
Cirrus Soulsplit 以 `capabilities.enemy_targetable: false` 复用现有能力闸，行动目标与
通用 hook 的敌方池均不再选中它。其他非召唤敌方死亡时以 `drain_hp` 流失 10% Max HP；
TBGD `SkillP01=[0.1]` 优先于普通 Fandom 页的 5% 文本，Complete 页虽未写比例也共用同一
原始槽。`on_kill` 过滤自身与 `summoner_of($event.target) != ''` 的召唤物，避免死亡连锁
虚增扣血；这里不做伤害/治疗转化。
Sixfold Plenilune 按 Ability 的五组攻击直译：首个锁定者、末个、全体锁定者、首个、末个；
双锁时因此发生六次命中，而不是每个锁定者只打一段。每击系数为
`Skill04[0] × _TargetCount / 6`，目标数在攻击开始时快照；无锁定者时先按原回退逻辑给两个
目标 Other Sign，再复用同一目标序列。普通形态用 450%，LocalLegend 用原始 400%；
Triple Waning Moon 同步分流为 260% / 250%。`count_modifier` 只提供存活目标计数，
不把重复持有多种标记的同一单位算两次。
Fallen Star's Visit 与 Radiating Venom 的 Entanglement 只推条和结算延迟伤害，
不写 `prevent_action`；按 mechanics 04，纠缠/禁锢不跳过行动。

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
