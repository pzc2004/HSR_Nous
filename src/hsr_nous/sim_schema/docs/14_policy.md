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
> **被动事件族（2026-10-22 收编）**：`SkillList` 的 Passive/SkillP 条目（EntryAbility 指向被动
> 能力）整体走被动编译通道——语义三问按真实样例数据形态钉死：**何时挂**=战斗开始（能力
> `OnAdd`/`OnStart` 任务表编译为 `on_battle_start` 挂载钩，序=OnAdd 先于 OnStart，约定待实测；
> 波次 newcomers 由 `actor_enter`（`$event.wave_index >= 1` 且 actor==自身）补挂——初始阵容的
> actor_enter 在订阅前发射收不到，两触发集按 actor 实例互斥不双挂；波 0 召唤物被动挂载为已知
> 缺口）；**挂给谁**=`OnAdd`/`OnStart` 任务内 AddModifier 的 TargetType 决定（Caster=自身，
> LevelEntity 等未注册目标显式拒）；**活多久**=modifier 定义 LifeTime/Stacking（duration 0=永久，
> 既有 `_modifier_defaults` 口径）。挂载任务全族走既有 `_compile_tasks` 机器（写后读/概率分支
> 随 #26 期 2/3 一并可用）。modifier 回调事件映射表（`_PASSIVE_EVENT_MAP` 单一事实源）由主动与被动挂载共用，不再另维护主动白名单；表内无载体事件仍显式 unsupported，避免混合回调中漏掉未收编部分；普通事件回调中的召唤声明向父上下文注册，伤害效果保持原任务顺序，HP 双通道与未收编分段状态仍拒绝：
> OnCreate/OnDestroy/OnBeforeDying 落 modifier 生命周期槽（既有）；OnDeathrattle 按自身过滤，
> OnListenCharacterDie 无 Deathrattle 旗标时全局监听 on_kill.target（带旗标仍按自身过滤）；
> ability.Modifiers 继续由
> 专用亡语通道消费，来自全局 sources 且实际挂载的 OnDeathrattle/OnTriggerDeath 复用同一 on_kill
> 映射且不重复展开；该通道的子上下文保留 current_modifier，使 modifier 内 TaskListTemplate 与 RemoveSelfModifier 等自身语义可用；模板查找在全局 modifier 表缺项时回退到 current_ability 的局部 Modifiers；OnBeingBreak→
> `on_break`、OnListenBreak→`on_break`（不窄化）、OnBeforeBeingBreak 的现有成就监听同样复用 `on_break` 并限定击破目标为持有者；其层数读取服务于 SetBattleAchievement，不产生战斗状态效果、OnEndBreak/OnStanceReset→`toughness_recovered`（waterfall，后者限定恢复目标为持有者）、
> OnListenBeforeAction→`before_action`（全局监听）、OnActionPhaseBegin/OnListenActionPhaseBegin→`before_action`（分别限定持有者为行动者/全局监听，可读取 action_type 与行动者）；OnCharmAction→`on_action` + 持有者自身（MCommon_MindControl 存续期间的行动）、OnModifierAdd→`after_apply_modifier`、OnModifierRemove/OnListenModifierRemove→
> `after_remove_modifier`（主动技能侧也复用）、OnBeforeSkillUse 在主动技能侧同样复用 `before_action` + 持有者/技能类型窄化、OnListenModifierDispel→`after_remove_modifier` + reason=='dispel'、
> ByCheckModifierDeathSource(CasterDead) 对应 `$event.reason == 'source_death'`，
> OnAfterBeingHit(All)/OnAfterBeingAttacked(End/Adv)/OnListenCharmMakeDamage→`after_being_hit`；OnListenAfterBeingHitAll 同事件全局监听；OnBeingStanceDamage→`on_toughness_damage` + 持有者自身；OnDispel→`after_remove_modifier` + 自身 + reason=dispel；OnBeforeAction→`before_action` + 自身；OnTriggerDeathrattle→`on_kill` + 自身（上述伤害事件 ParamEntity=受击者、ParamEntity2=攻击来源）、OnBeforeBeingHit(All)/
> OnBeforeBeingAttacked→`before_take_damage`（waterfall）、OnBeforeHitAll→`before_take_damage` +
> 持有者为攻击来源（攻击者命中前视角）、OnEnterBattle→`actor_enter`（actor
> 窄化）、OnListenCharacterCreate→`actor_enter`（不窄化）、OnListenTurnBegin/End→
> `on_turn_start`/`on_turn_end`（不窄化）；OnListenModifierAdd 复用 OnModifierAdd 通道，
> OnListenEndBreak→`toughness_recovered`（不窄化），OnListenAfterAction→`on_action_end`（不窄化），
> OnAllowAction/OnListenAllowAction→`on_turn_start` + `not action_disabled($event.actor)`、
> OnListenTurnPhase1Begin/2Begin→`on_turn_start`/`on_turn_end`（BeforeTurnPhase1End 同归回合结束边界），
> OnDepartedStart/End 分别→`before_actor_exit`/`actor_exit` + actor 自身，Listen 形式为同事件全局监听；ParamEntity 读离场者 `$event.actor`，
> OnListenInsertAbilityStart/Finish
> 与 OnInsertAbilityFinish→`on_action`/`on_action_end` + insert=true；OnInsertAbilityStart 同接 on_action 并再按持有者自身窄化（OnListenInsertActionFinish
> 复用后一锚）；OnInsertActionStart/OnListenInsertActionStart→`before_action` + insert=true
> （分别再按持有者自身/全局区分）；OnBeforeInsertActionPrepare 同接 before_action + insert=true + 持有者自身，仍处于行动执行前；OnListenElationTimeStart→`aha_instant_start`；OnAfterHit 复用伤害事件并按
> `$event.source == $self.actor_id` 过滤攻击者，`DamageDefenderEntity` 读 `$event.target`；
> OnAfterHitAll 仍为受击者侧，OnBeforeHit、OnTriggerBreak 复用对应受击/击破事件。
> OnAfterSkillUse→`on_action` + 持有者自身 + action_type=='skill'；
> OnListenAfterSkillUse→`on_action` + 全局监听 + action_type=='skill'，ParamEntity 为技能使用者
> `$event.actor`，不能窄化为持有者自身或误读技能目标；OnBeforeSkillUse/OnListenBeforeSkillUse→
> `before_action` + action_type=='skill'（分别持有者自身/全局），OnBeforeAttack/OnListenBeforeAttack→
> `before_action`（分别持有者自身/全局），目标解析已完成但 SP/伤害等尚未结算（上游 "uses Skill" 仅战技措辞纪律）、OnAfterAttack/OnAfterAttackEnd/OnAfterAction→
> `on_action_end` + actor 自身、OnListenAfterAttack/OnListenAfterAttackEnd→`on_action_end` 全局（整段攻击结束，
> 可读取 after_being_hit 已提交写入）、OnHPChange/
> OnListenHPChange 分别注册 `on_hp_decrease` 与 `on_hp_increase`（每次变化只命中一侧，不会双跑）、
> OnUnselectableStart/End→`on_unselectable_start`/`on_unselectable_end` + 事件目标为持有者；set_targetable 分别在任一侧由可选变不可选、由不可选恢复可选时发射，ParamEntity 读取 `$event.target`、OnListenBpChange→`on_skill_point_change` 全局监听；该事件的 ParamEntity 是耗点者 `$event.consumer`，RawDelta/ParamValue 均读取 `$event.after - $event.before`，可经 SetDynamicValueByBPChange 或 SetDynamicValueByVariateType 写入既有动态值通道、
> OnBeforeBeingLoseHP→`before_drain` + 扣血目标为持有者；`ModifyLoseHPData.ConstFinalDamage` 复用 `modify_amount` 改写本次扣量。普通伤害的 `ModifyDamageData.AttackData_ConstFinalDamage` 则在 `before_take_damage` 中使用同一效果，`AttackData_FinalDamageMax` 编译为 `min($event.amount, 上限)`；OnBeforeHitAll 中纯条件的 `Attacker_AllDamageTypeAddedRatio` 直接归入攻击侧
`hit_condition + hit_stat_exprs(all_dmg)`，不经结算后的 amount waterfall；
`Defender_AllDamageTypeTakenRatio` 与 `Defender_Monster_DamageTakenRatio` 同走 `hit_stat_exprs(vulnerability)`，由规则层在目标与攻击者两侧收集命中域条件件；该结构化收编覆盖 OnBeforeHit、OnBeforeHitAll、OnBeforeBeingHit 与 OnBeforeBeingHitAll，共用 before_take_damage 载荷，防御归 0 仍仅限攻击侧 OnBeforeHitAll；条件块仅失败侧含机制时也走同一通道，并以 ByNot 对原谓词取反，双侧都有机制仍拒绝；同一回调混有其他顶层条件任务时，只把能独立完整收编的命中域条件块送入该通道，其余任务仍生成原事件 hook，不再要求整个回调只含命中域；无效果 modifier 是否被谓词引用须扫描 abilities/modifiers/global_templates/config_ai 全闭包，跨 modifier 引用同样保留其状态标记；
前置 SetDynamicValue 仅在该键无外部读者时折叠进表达式，其他写入键名不算读取；同为局部赋值的 SetDynamicValueByModifierValue 也可在“读取自身 modifier 的 Layer、无额外字段”形态下经既有编译器提取表达式，其他读取类型仍拒绝。外层谓词内的 `SwitchCaseByDynamicValue` 若各 Case/Default 都只改写同一个已注册命中属性，则各分支值折叠为该属性的条件表达式，运行时活读 Switch 动态键，无 Default 的未匹配分支保持零增量；
`Attacker_FixedCriticalChance` 编译为攻击侧 `hit_stat_exprs(fixed_crit_rate)`，经规则层 scoped_override 覆写本次 crit_rate，不与普通暴击率加算混用；`Defender_AllDamageReduce` 编译为命中域 `hit_stat_exprs(dmg_dmg_reduction)`，由直伤规则层按减伤乘算合并到既有 dmg_red_multi，不折算最终伤害；`Attacker_ForceStanceBreakRatio` 仅收静态值 1，编译为攻击侧 `hit_stat_exprs(force_stance_break)=1`，在原削韧闸处按 hit_condition 开闸，不进入伤害或削韧量公式；`Defender_DefenceDelta` 仅在完整形态为 `0 - ParamEntity.Defence`（即本次防御归 0）时编译为 `hit_stat_exprs(def_pen)=1`，其他伤害公式属性改写字段仍拒绝，两个事件域不混用。
> OnHPOverflow→`on_hp_increase` + `$event.excess > 0`（治疗溢出量已有载荷）；OnBeforeBeingHeal 的 ModifyHealData.Target_HealTakenRatio 编译为受疗者 hit_stat_exprs(incoming_heal)，按当次治疗求值而非新增事后事件；OnListenRevive→`on_revive` 全局监听，
> 其中 ParamEntity=复活目标 `$event.target`、ParamEntity2=复活来源 `$event.source`（与 on_kill 的目标/来源分工同构）；OnBeingRevived 同接 on_revive 并窄化为复活目标自身、OnLeaveBattle→
> `actor_exit`（actor 窄化）；OnBeforeEscape→`before_actor_exit` + 自身 + reason=flee，与离场后的监听分开、OnLockHPThresholdReached→`on_hp_lock`（target 窄化）、
> OnBeforeWaveMonster/OnWaveMonster→`on_wave_start`（近似：波开始 vs 怪登场前，待实测）、
> OnStack/OnStage→modifier 定义编译期消费；其中非 DoT OnStage 已由属性定义编译器经
> `_compile_tasks` 展开，消费核查同样认 TASK_HANDLERS，不再二次误报“无消费点”，未知节点仍由实际展开器拒绝。非 DoT OnPhase1/OnPhase2→持有者
> `on_turn_start`/`on_turn_end`。非 DoT modifier 回调内带显式 DamagePercentage 的
> `AttackType=DOT` 直接伤害段编译为 `deal_damage(action_type="dot")`，合法整数 DamageTag
> 原样透传；这不是声明式 DoT 定义，也不新增一次自然跳伤。DoT 仍走定义编译（visit_stack/DoT 既有口径，
> 非常消费任务显式拒；`OneMorePerTurn` 族走决策卡 #27 专用收编——boss 多动配额：
> 发放仅普通回合开始（相位不走额外回合）、`OnActionEnd`→`on_action_end` 扣额度、
> 重置监听所有回合结束、MaxOneMoreCount 默认 1 待实测）。持有者窄化条件按事件主体选
> `$event.target` / `$event.actor` / `$event.source == $self.actor_id`，不混用攻击者与受击者
> （owner 死亡不触发的 alive 闸天然生效）。无载体事件
> （OnAllowAction 族无发射点、OnBeforeAttack
> 族无发射点、limbo 域未收编等）
> 显式 unsupported 进 human_queue，逐条写理由；回调内容为纯表现（`_presentation_only`）时
> 无映射事件也可安全忽略。空被动（无 OnAdd/OnStart/回调机制内容，如 AI 控制壳）空翻译
> ok=True。公共 `Monster_ChangePhase` 模板使用 `emit_phase_custom_event`：13 在恢复前发
> `monster_phase_change_begin` 且包含 limbo，8 在恢复后发 `monster_phase_change_end` 且不含
> limbo；带 `CustomEvent_MonsterChangePhaseTrigger` 的 `OnCustomEvent` 只监听后者；DoT 的
> `OnCustomEvent` 是 `trigger_dot` 引爆时的定义回调，与 OnPhase1 共用倍率/属性消费核查，不另挂
> 重复跳伤钩。其他非 DoT/公共换阶段自定义事件经 `emit_modifier_custom_event` → `modifier_custom_event` 逐目标连接，载荷保留 event_type/dynamic_key/value，监听器按 target=持有者窄化；ParamEntity/ParamEntity2 分别读 target/source。`Monster_Common_*` 共享被动维持 deferred 不在本通道。
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
队伍计数的 `CasterSummonedMinions` / `ModifierOwnerSummonedMinions` 别名只统计 `summoner_id` 等于施放者/持有者的敌方存活召唤物；
`AllLightTeam` 指我方全队，`AllDarkTeam` 指敌方全队，`AllDarkTeam - Caster` 再排除施放者；
`AllLightTeam.RemoveServant` 与技能目标别名 `AllEnemyIgnoreServant` 只保留非召唤我方角色，
召唤归属均由 `summoner_id` 判定；`TauntOrAggroEnemy.RemoveServant` 按同构上游分支同口径处理。
Ability 目标代数同样收编 `AllEnemy.RemoveServant`（非召唤我方）、`AllDarkTeam + AllLightTeam`
（双方全体）与 `AllTeammateWithUnselectable`（含不可选单位的敌方全体）；
`LeftToRightDarkTeamTarget`/`RightToLeftDarkTeamTarget` 分别按敌方编队正序/逆序求值。
`AllLightAvatar` 只含 `actor_type=character` 的我方角色；`AllTeammate.RemoveUnselectable`
额外要求 `enemy_targetable` 与 `ally_targetable` 均为真，不能沿用敌方选择队友时不过滤的默认池。
`AllLightTeam.SortByHP.Reverse` 按 `$it.hp` 当前生命降序排列，同值保留编队序；
不读取最大生命，也不与站位排序混用。
`AbilityTargetLeftEntity`/`AbilityTargetRightEntity` 以 `$event.target` 为参照取同侧左右邻。
`ModifierOwnerEntityAllTeammate` 是排除持有者的其他队友；
`ModifierOwnerEntityAdjoinEntity` 取持有者的相邻位，`ProjectileHitEntityAdjoinEntity`
取 `$event.target` 的相邻位，均不包含参照自身。
`AbilityTargetEntity.GetSummoner` 则读取该目标的召唤者，不混用 `$self` 的召唤者；
`AllEnemy.GetServant` 只含我方召唤物；`ServantEntityList` 是不限阵营、含不可选与 Limbo
存活实体的召唤物查询。`AllLightTeamOnlyAddSPOnceForServant` 按上游定义等于
`AllLightTeam - AllLightTeam.GetServant`，增减能量均只作用于非召唤我方角色。
`AllLightTeam/AllDarkTeam - ModifierOwnerEntity`
分别从对应阵营排除持有者；`AllDarkTeamUnselectable` 只保留至少一种可选标记为假的敌方实体。
普通 hook 目标与 `Retarget` 共用 `_target_spec` 展开 `GlobalTargetAlias`：按上游序列和谓词求值，
不按 modifier 名称猜测持有者；循环别名和未注册谓词仍显式拒绝。跨文件 TargetAlias
引用递归进入装载闭包，只有能唯一消歧的定义才提供给编译器，内建别名不因此误报缺失。
`Monster_W4_Griffin_00_LocalLegend_Partner` 与 `AllDarkTeam - Caster` 同义，仅含其他存活友方。
`Monster_Svarog_00_Unselectable` 对应无 `RL` 的 `W1_SvarogPart` 存活友方；
`Monster_Svarog_00_RL_Unselectable` 对应同时带 `W1_SvarogPart` 与 `RL` 的存活友方。
`ParamEntity.WithSummoner` 用 concat 拼接目标自身与 ParamEntity.GetSummoner，非召唤物不会额外添加目标。
`Trailblazer` 按角色索引中 `{NICKNAME}`/Trailblazer 条目派生全部主角 ID，在我方池按 character_id 过滤，不按显示名匹配。
`ParamEntityActualOwner` 以 ParamEntity 为基准，在全体实体中选择 `summoner_of(ParamEntity) or ParamEntity`：
召唤物归召唤者，非召唤物归自身；谓词与效果目标共用该目标代数。
任意已注册单实体基目标的 `.GetServant` / `.GetSummoner` 后缀分别选择其召唤物/召唤者，
覆盖 ParamEntity、Caster、ModifierOwnerEntity 等同义基目标；`.GetBattleEvent` 则在 battle_events 池中按
`$it.summoner_id == 基目标` 选择该实体创建的战斗事件；
与 ParamEntity 用 `+` 拼接时分别求值，加号两侧空白可省略；来源闭包也按同一拆分规则收集子别名。`.WithServant` 先求基目标，再以 `include_summons`
追加其召唤物；外层 `.RemoveUnselectable` 再对展开结果附加双侧可选过滤，后缀顺序与语义一致。
`.GetAliveOnly` 显式写 `include_dead=false`，可覆盖基目标的死亡实体包含设置。
`AllTeammate - MMonster_*` 按 `not has_modifier` 排除持有者。
`AvatarNextTurnOwnerEntity` 编译为角色池中的行动条首位：`is_top_action_delay_target($it, 'light', 1)`，跳过召唤物。
`CasterLeftEntity`/`CasterRightEntity` 在 TargetSequence 中同样编译为敌方池 + `position_delta == -1/+1`，与谓词和 hook 映射一致。
`ByIsTeamLocationIndexType` 的 `Type` 缺省与 `Left` 同义，`Max` 与 `Right` 同义；依据是彦卿 Skill02 在主体两侧及队首/队尾召唤后，分别以这两型选取左右单位并命名为连续位置。其他未知类型仍拒绝。
`TargetQuery(TeamLight, Avatar, Mask_AliveOnly)` 编译为我方池 + 角色/存活过滤；未声明队伍/实体类型且仅有 `AliveStateMask=Bit_Deathrattle` 时编译为 `pool=all + include_dead + not actor_alive($it)`，只选死亡单位，其他查询仍拒绝。
带 `.SelectN` 的 hook 别名也复用 TargetSequence 的一基编队位置语义，剥离后缀后编译为 `index=N-1`；随机/洗牌结果仍不承接精确位置。
`SetDynamicEntityParam.ParamTargetType` 可接受已完整解析的目标代数，编译为 `set_dynamic_target(owner=self, target=spec)`；未解析的字面别名仍拒绝。
能量增减接受任意已绑定的 `unique:` 目标及完整 concat/差集目标代数；运行时按实际 actor_type 决定角色能量上限或战斗事件无上限，不再按池名限制。
`ModifierOwnerSkillTargetEntityList` 在 before_action/on_action 中均映射 `$event.targets`；ByCompareCharacterID(Equal) 与
ByIsContainModifier 对该列表表示“任一目标满足”，用 count_selected 实现，不把列表传给单目标函数。
`Elation_BE` 按全局模板实际创建的 EventID 解析为 `unique:$battle_event:70001` 与 `unique:$battle_event:70002` 的 concat；无事件时为空，不映射为 LevelEntity 或施放者。
`PartEntityN` 通过主体/部位共享的 `PartEntityN_MonsterID` 配置解析为 `monster_id($it)` 过滤；
`PartEntity0` 在主躯干/部位关系中指主躯干，谓词寻址用 `(summoner_of($self.actor_id) or $self.actor_id)`，主躯干无召唤者时回退自身；
部位变体再按 `PartEntity2_MonsterID=<变体>` 反查唯一主体，编译器不写死 Boss ID。
`ByCompareMonsterTemplateID` 的自身目标仍按当前模板静态求值；ParamEntity/CasterSummoner 等非自身
目标改用 `monster_id(target)` 逐目标归一化比较，不把编译者自己的模板 ID 错套到他人。
`.Shuffle` 使用独立 shuffle 模式，roll 全取也打乱顺序，
expected 保持确定顺序；after_being_hit 与 before_actor_exit 的 ParamEntity 分别读事件 target/actor；
on_turn_start/on_turn_end 均读 `$event.actor`，toughness_recovered 读 `$event.target`，before_take_damage 的 ParamEntity 同样读 `$event.target`，与 bus 载荷契约一致。
`Retarget.FailedTaskList` 的空候选条件复用 `count_selected`：普通静态池仍按 pool/where 计数；
事件语境或 TargetConcat 序列化目标规格后按同一求值器计数，递归剔除 mode/take/order_by，
只判断候选是否存在而不消耗随机流。缺失事件字段的子项计 0，其他拼接子项仍正常计数。
TargetSequence 允许 TargetConcat 及嵌套 TargetSequence 作为基座；后续 TargetFilter/TargetTake
等作用于完整结果，TargetFilterAliveState(Bit_OnStage) 排除放逐实体，TargetShuffle 在排序前
预洗牌，TargetSortByModifierValue 按 modifier 层数排序。`ByIsTargetUnselectable` 在候选域读取
双侧可选标记。RemoveModifier、ForceKill、ModifyActionDelay 的非别名 TargetType 统一走 `_task_target`。
`ByCompareTargetCount(AliveOnly=false)` 以 `include_dead` 计数死亡实体，事件目标列表同样保留死亡；
true 仍只数存活。含死亡、拼接、截取或事件池时序列化规格计数，普通静态路径不变。
Claymore 的 `BlackSummon` 仅含 `4032052`（Black Tide's Decrepit Bow）与 `4032042`
（Black Tide Council），`WhiteSummon` 仅含 `4012033`（Furiae Archer）与 `4012023`
（Furiae Philosopher）；这些具名集合与 `CasterSummonedMinions` 的初始决策评估都按 0 个处理。
`WhiteMonst` / `BlackMonst` 的 `StackCustomUnselectable` 编译为 `custom_unselectable`：
白卫对带 `BlackCurse` 的 TeamLight/TeamNeutral 来源不可选，黑斗者镜像排除 `WhiteCurse`；
这与白卫技能实际选择 `WhiteCurse_Target`、黑斗者选择 `BlackCurse_Target` 相互印证。
当前只收 `EntityTypes=All` 与 `ParamEntity` 上单 modifier 的 `ByIsContainModifier` 条件，
其他条件继续显式拒绝，不退化为全局不可选。
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
回退到现有默认目标。`Remodifier` 的自身目标在 IncludeLimbo=true 时沿用 self 池原有的 limbo 保留语义；CasterFilter 的 Caster/ModifierOwnerEntity 均为 `$self.actor_id` 自身来源过滤；也可解析为当前事件目标（如 on_kill 的 `$event.target`）或目标代数；后者经 `modifier_source + target_in_selected` 检查实际施加者是否属于候选集。StatusTypeMask=Buff 追加 `modifier_kind($it, modifier_id) == 'buff'`，读取候选实际实例类别；其它掩码仍拒绝。PredicateFilter 仅收 `ByCompareModifierCallBackDynamicValue` 的 DynamicKey/CompareType/CompareValue 形态，经 `modifier_dynamic_of` 比较当前实例值，并与其它合法过滤条件做 AND；未知谓词和额外字段仍拒绝。子任务显式写 Caster 时也继承同一 self 目标的过滤条件，不能退化成无过滤的 self 字符串；摘除任务的 ParamModifier 读取 Remodifier 当前选定的 modifier ID，不再误用字面量。其他池的 IncludeLimbo 与未知过滤目标仍拒绝。
`Retarget` 按 `TargetType` 与 `Predicate` 过滤候选，仅收 `MaxNumber=1`：
成功时把首个候选（roll 且 `ByRandom` 时随机一个）写入 `target_override` 并执行 `TaskList`；
空候选清除目标覆盖并执行 `FailedTaskList`。`AIComplexSkillAISelector` 仅收自指一技能的
`UseSourceInSkillConfig == SkillName` 用法，目标覆盖留空并沿用 action 自身目标解析；跨技能引用拒绝。
`AIMonsterRankSelector` 当前仅收
`PropertyStrategy=Max`，在怪物候选中保留 Rank 数值最高者（并列全保留），供 Compose 求交集。
`CasterSummoner` 目标别名按 `summoner_id` 反查存活召唤者；非召唤物或召唤者离场时无候选。
`AITaskTargetTypeSelector.TargetType` 也接受 `TargetSequence`（别名/过滤/编队排序/索引）；
`TargetIndex.IndexType` 缺省按 `IndexStrict` 处理；`TargetSortMonsterRank(HighestFirst=true)` 编译为 `order_by='-monster_rank($it)'`，复用 MONSTER_RANK_VALUES 与稳定排序。`ByTargetListAny` 按 `TargetType`
解析候选，任意一个满足 `Predicate` 即为真；目标别名/序列仍走静态支持表，未知项拒绝。
`AICustomStringTagSelector` 按 `Actor.groups` 中的 `CustomStringTag` 过滤，
`InverseResultFlag` 取补集；敌人模板 `groups` 来自上游 `CustomValueTags`。
`SwitchCaseByDynamicValue`：Switch 为 `AQAR` 单动态值读取。IncludeTaskListTemplate/IncludeGlobalTaskListTemplate 的 DynamicValues 与其他表达式共用调用方符号覆盖层；无同名 CustomValue 时 Switch 回退到该层解析，已有可变 CustomValue 仍优先走运行时活读。键名可静态解析
（SkillParam 符号/静态模板参数/只读 CustomValue）时生成期选定唯一 `CaseTaskList`，无匹配走
`DefaultTaskList`；模板参数是已注册动态表达式时直接以该表达式作 Case 守卫；键名解析到**本敌动态键**（生成期被写过的键，含可变 CustomValue）时
翻**活读**——每个 Case 的任务编译为 effect 级条件守卫 `dynamic_of($self, '键') == Case值`
的分支组（数值用变量、结构用组合，不加新原语），无匹配且声明 `DefaultTaskList` 时其
守卫为全部 Case 值不等；Case 值必须是静态数值且不重复。哈希缺失/冲突仍显式拒绝，
不猜测哈希含义。
`ByCheckCustomValueBool` 的 `Key.Hash` 经同一哈希算法与 pipeline 全量 `CustomValueTags`
名册对账并归一化为 `Key.Value`，运行时检查目标 `Actor.groups`；未解析键以
`custom_bool:Key` 拒绝，不把未知哈希当成恒假。`ByCompareHP` 以 `hp_of(target)` 读取当前
绝对 HP；`CasterSummoner`/`ModifierOwnerSummoner` 经 `summoner_of` 寻址，其他目标别名仍拒绝。
`ByTargetAliveState` 收 `Mask_AliveOnly`/`Mask_AliveOrLimbo` 并调用 `actor_alive`，支持 `Inverse`；`ByCasterAliveOrLimbo` 以自身为同一通道，其他掩码拒绝；
`Mask_AliveOrLimbo` 同样调用 `actor_alive`：引擎的 allow_negative_hp/limbo 分支保持 alive=true，死亡或放逐仍排除；不再把该掩码误拒。
`ByHasSummonRelation` 分别解析 `SummonerType` 与 `ServantType`，编译为
`summoner_of(servant) == summoner`，支持 `Inverse`；不能只检查召唤者字段非空来代替双向关系。
`ByIsBattleEventEntity` 与 `ByTargetEntityType(BattleEvent)` 同译为 `actor_type_of(target) == 'battle_event'`，支持 Inverse。
`ByTargetEntityType` 的 `Servant` 编译为 `actor_type_of(target) == 'summon' or
summoner_of(target) != ''`，同时覆盖我方召唤物与仍按 monster 登记的敌方召唤物；`Avatar`
取其反，支持 `Inverse`。当前只收缺省或 `Anyone` 的存活掩码，不把额外 AliveState 与类型取反混为一谈。
动态值迁移用 hook `set_dynamic_value`（`dynamic_key` + `amount`）按任意 actor_id 写入共享运行态表，
支持我方、敌方、战斗事件、队伍/关卡伪实体与已注册目标代数；无需已有 ConfigAI policy，也不写影子计数。
动态值和 `current_phase` 与冷却一样进入存档。`RemoveModifierByBehaviorFlag` 的多旗标列表按并集过滤，任一命中即纳入可驱散集合；空列表仍拒绝。
`SetDynamicValueByHPRatio` 在 Retarget 内以 amount_target 逐目标读取 ParamEntity，在 HP 事件中读取事件目标；闭包内命名目标别名与显式 TargetSequence/TargetCompute 也经同一 amount_target/$target 通道逐候选读取，写入目标仍为自身。`SetDynamicValueBySkillMaxHitSplitCount` 仅在 after_being_hit + ParamEntity2 形态读取事件 `max_hit_split_count` 并写入自身 DynamicKey，不另建技能段数状态。`SetDynamicValueByFormationIndex` 复用 `position_of(target, 'dark')`，支持自身及 Retarget 内 ParamEntity。`ByCompareCharacterNumber` 的 PartEntityN 在配置给出对应怪物 ID 时复用同一目标计数通道。
`SetDynamicValueByProperty` 的 `Attack`/`Speed` 读取当前有效面板，
分别编译为 `stat_of(..., 'atk')`/`stat_of(..., 'spd')`；`NegativeHP` 由 `max(0, -hp_of(target))` 派生，正 HP 对应 0；`RallyHP` 是逐目标资源余额，StackProperty 的增减复用 `gain_resource`，属性读取复用 `resource_of(target, 'rally_hp')`，OnStack 普通/条件分支均只生成实际叠层钩；HealHP 的 `IsHealRallyHP=true` 先正常治疗，再对同目标追加 `gain_resource(amount='-$last.actual_amount')`，只按实际治疗量扣余额，溢出部分不扣；`BaseAttack`/`BaseSpeed` 仍走
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
hook 级快照条件（事件间确定性语义不变）。Retarget/Remodifier 的过滤条件随目标效果在执行时求值，同样允许读取前序效果已写动态值；hook 级目标别名快照不在此列。`SetDynamicValueByModifierValue` 的 `Layer`/`LifeTime`
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
`PostfixExpr` 的动态哈希必须能由 `DynamicValues.Floats.ReadInfo`、modifier 内的显式赋值
或实例 `SummonIDList` 还原；保留段 `1509106746–1509106751` 依次读取该列表 0–5 号位，
仅在对应位置真实存在时接受，空列表和越界不回退为 0，也不借用 SummonID0 等自定义键。
`-797864550` 仅在 `LayerAddWhenStack` 识别为默认每次叠 1 层；它不外溢为通用动态常量，
其他哈希仍按原拒绝口径。`0x06` 是数值等值比较，静态求值返回 1.0/0.0，动态操作数保留为 DSL `==`，
真实形态为 Score == 10、标志 == 1，不是取模或幂。`TASK_HANDLERS`/`EVENT_HANDLERS` 未注册的节点、缺失引用和
未证明的条件分支都记为 `unsupported`，不得拿部分结果冒充完整收编；被动事件族已开编译通道
（上节），其无载体事件按 `_PASSIVE_EVENT_MAP` 逐条显式拒收。写后读/概率分支经
执行帧改翻后，"同一技能写入后读取动态值会命中旧事件快照"与"运行时 Switch 尚未注册"
两类旧拒因退役；条件附加段在伤害记录中保留 TargetSequence 等完整目标规格，
不再经 `_alias()` 归为空串后误报无目标，普通直伤与事件伤害共用该规格。
ForceKill 与 RemoveModifier 同样经统一 `_task_target` 保留 TargetSequence，只有
`before_actor_exit + Caster` 继续按防递归空操作处理，其他过滤后的击杀目标不再被默认为自身。
概率分支支持主动与事件域；帧外事件由 HookRuntime 自动建立单 hook 链执行帧。动态次数 LoopExecuteTaskList 收编直接动态写入、AddModifier、RemoveModifier、LoseHPByRatio、ForceKill、SwitchCaseByDynamicValue、RandomConfig（无跨局记忆字段）、AddEntityToTeamFormation（无召唤规格时为空操作）、以其为内容的 Retarget/RetargetList 及谓词分支，以及由这些已收编任务与 DamageByAttackProperty 组成的循环；局部 IncludeTaskListTemplate 也先展开，但产物若仍含 Action 主伤记录、召唤或逐击侧通道则整体拒绝，定义级 lifecycle_hooks 按本节规则并回父上下文。上述合法产物统一编译为 `loop_effects`：分支条件完整并入嵌套 effect；行动域直伤在循环内即时降为 `deal_damage`，保持与写入/修饰任务的相对顺序，每轮重新选目标并走完整伤害与事件管线；次数执行时求值一次，须为非负整数，超过安全上限显式报错；modifier 每次迭代都走正常施加/叠层与事件链；子上下文产生的 lifecycle_hooks 属于定义级注册，编译后按原顺序并回父上下文一次，不随循环次数复制，也不丢弃；含召唤或其他未收编机制副作用的循环不套用此通道；WaitSecond 等已登记表现等待仍按既有规则忽略。SetDynamicValueByDelayCumulate 仅在写入键及哈希于完整闭包内无其他引用时按 dead store 消除；存在读者仍要求真实 DelayCumulate 语义。多抽与跨局随机记忆
（`RandomCount`/`RandomMaskKey` 等）保持显式 unsupported；单独 `RandomUnique` 且无多抽/mask 字段时仍是单次抽取，不另建记忆。**任务节点长尾族（2026-10-22/23
收编）**：表现类零成本进 `IGNORED_TASK_TYPES`（TriggerCustomString 客户端串/
ModifyDefaultTeamFormation+RemoveEntityFromTeamFormation 站位编排/MappingAttachPoint
挂点映射/SetEntityArtRotation/ClearActionBarHighlightEntity 高亮清理/
SwitchChallengeBossInfoPanelState UI 面板/ShowUI 的 BattleCommonHintDialog 文本提示/PreloadBattleEventByID 预载/CreateBattleEventQTEUI 已有事件的 QTE 界面（不重复创建机制实体）/BENHFIGIMGL 仅 Textmap Hash 的技能提示/语音/MuteEntitySound 实体静音/SetLayerWeight 动画层权重/AbortModifierPhasePerform 中止阶段演出（不改 modifier 计时）/BlockCameraDitherUpdate
相机抖动/SetEntityForbidCameraDither 实体镜头抖动开关/MAvatar_AvatarChange_*_ResetCameraDither 仅复位变身演出镜头/模型透明化，未参与谓词时不生成战斗 modifier；Monster_APShow_* 是行动条预告标记，未参与谓词时添加与清除均不生成战斗状态，实际再动仍由独立机制负责/SetMonsterHUDVisibleType 怪物 HUD 显隐/SetControlSkillMapping 控制按钮映射；DGAOCHGKJKJ 是其混淆映射/开关形态，实样仅含 ControlSkill11/21 映射或布尔开关与目标）。`MOPOKJECALI` 是同一映射的严格两字段混淆形态：仅接受 ControlSkill 字段与既有技能名两个非空字符串，校验后无战斗 effect，额外字段仍拒绝。`DNBOLDHOBML` 只携带部件血条目标与可选布尔显隐值，严格校验后无战斗 effect；部件阻挡/移除仍由真实 modifier 状态表达。`Modifier_FateRin_MonsterPreview_PreCal` 是活动预览代理上的客户端预计算件，定义缺失且未参与谓词时不生成战斗状态；模拟器预览仍从当前状态重算。`OHONOHOIOJA` 仅接受目标对象与显式空禁用列表，空集合无 effect；非空禁用列表和其他字段仍拒绝。
`IncludeGlobalTaskListTemplate` 与 IncludeTaskListTemplate 共用同一展开器；全局模板须已在数据闭包，动态参数、ParamTarget 和循环引用检查不变，缺失仍显式拒绝。
机制族翻译：`MEDEPLMJCIC` 是标准 AttackData 伤害节点的混淆类型别名，直接复用 DamageByAttackProperty 编译链。
`DamageStance`（ForceStanceDamage=true）→ `reduce_toughness`（DefenderTargetType=被削韧
者；`StanceDamageType` 属性与 Force=false 的削韧减免交互引擎无载体，照算削韧=已知近似、
Force=false 显式拒）；`SetResilience` 与 `ChangeCharacterConfigParam.Resilience` 是受击反应动画等级/复位，
S/A/B/C/D 对应 `ResilienceHitAdditiveWeights` 的表现权重，不修改当前或最大韧性，按表现节点忽略；
无参数的 `ApplyMonsterPhaseOverrideConfig` 同样只应用 PhaseList.OverrideConfig 的模型/UI/碰撞与空间布场覆写，
在当前离散站位模型中不产生战斗 effect；同级 PhaseMaxHPRatio 等其他阶段字段不由本规则消除，节点带额外参数仍拒绝；`AddWeakness` →
`apply_modifier(weakness_add=[元素])`（永久弱点植入，命名 `ENEMY_<skill_id>_WEAKNESS_<元素>`，
dispellable=false 防误驱散）；任务位 `StackWeakness` 分流——OPType=Protected 且全七属性
→ `toughness_lock` modifier（命名 `ENEMY_<skill_id>_TOUGHNESS_LOCK`，与 `ClearWeakness`
（Protected 全七）摘除同件配对；非全七按元素保护）。无 OPType 的 `WeakList` 是覆写，
翻译为 `weakness_override`（空列表清空，不是 no-op），`WeakList`/`SecretList` 的
`AllType` 展开为全七属性；`SecretList` 只记录显示隐藏，不阻挡
正确属性削韧；`ClearWeakness(Secret)` 只解除显示隐藏。`Attach` 才逐元素复用 `AddWeakness`
追加通道；`Protected` 的部分元素记录 `protected_weakness`，只挡对应属性的默认弱点范围削韧，
不冒充全局韧性锁，`ClearWeakness` 的 OPType 缺省与显式 Protected 同义，按元素清除，全七仍摘原 `toughness_lock` 件；`ClearWeakness(Attach)` 改走 `clear_attached_weakness`，只从各 modifier 的 `weakness_add` 撤销对应附加弱点，不动 Protected、Secret 或基底弱点。
`SetColliderCenterFollowAttachPoint` 只配置碰撞中心附着点与跟随/重置表现，和 SetCustomLocationConfig 一样不改变编队站位或战斗数值，登记纯表现节点。
`AvatarIntensityEffect`、`SetCharacterVisibleInViewMode`、`ShowBattleTalkBGUI`、`ToggleHitCountUITop`、`TriggerModelShake` 的实样字段均只控制对应视觉/UI 表现，同族登记，不吞含机制任务的分支。`ChangeAnimEventConfig`、`FrameCaptureIfNeed`、`LockAnimatorSpeed`、`SetCharacterAtlasFaceEmotion` 也分别只配置动画事件、帧捕获、动画速度或表情；`BattlePlayVideo` 的回调须递归证明纯表现。`ForbidBattleConditionOnStart` 只禁用开局条件提示；`SetSignedAngleByTarget` 的 Skill02Angle 实样仅供 TriggerEffect.DynamicYaw 消费，不改变战斗数值。`AlignTargetToTeamCenter`、`SetCharacterFormation`、`SetCharacterCustomTeamFormation` 的实样仅含模型对齐、物理偏移或锚点资源，不改动逻辑站位与目标池。
`ReduceStanceRatio` 编译为 `reduce_toughness(amount=base_stat_of(目标, 'max_toughness') × ReduceValue)`，自身沿用 `$self`，其他目标由 `$target` 逐实体求值；LastSummonMonsters 使用最近召唤组，不再按全体召唤物近似。
`LockStance(StanceValueRatio=0)` 同样复用全局锁韧：普通回调生成 `ENEMY_<skill_id>_TOUGHNESS_LOCK`，
`OnStack` 直接标记所属 modifier，缺省目标为 `ModifierOwnerEntity`，不重复施加锁件；
比例 1 另经同目标 `reset_stance` 恢复主条满值，不附带解除击破，其他非零比例继续拒绝。其余拒；`PerformDelayExecute` 纯表现内容忽略、机制内容显式拒
（Perform 时点延迟执行时机未收编）。`AddBuffPerform` 仅在 TaskList 全为已注册表现节点时忽略，机制任务与未知字段仍拒绝。
`LoseHPByRatio` 支持 MaxHP/CurrentHP 两种基数与可选 Floor 保底，复用 drain_hp；其他比例基数仍拒绝。
`SetHP.ModifyValue` 是绝对 HP 设值，经 `set_hp_to_percent(percent=ModifyValue/$target.max_hp)` 复用同一死亡与 HP 事件链；`ModifyRatio` 仍直接作为比例。`LoseHP` 的 DamageValue 直译 drain_hp；CasterSummoner/ModifierOwnerSummoner 作为效果目标时改用对应的
“全体中查找召唤者”目标代数，不把表达式字符串当 pool；字面 Monster_* 目标由 MonsterTemplateConfig 解析到有序模板 ID 集，覆盖同配置的合法变体；组合别名先拆 concat 再逐项解析。自身 HP 回调中的自身扣血仍拒绝，避免未核定的递归回流。同名 modifier 先按实际引用它的 Ability 局部定义解析；
仅内容唯一时接受，多份不同局部定义继续报歧义；无局部引用时再按来源文件与内容唯一性消歧。
`SequenceConfig` 是顺序执行容器，直接按原 TaskList 顺序递归编译，不展开为循环，
不引入额外时序或重复效果。其余未注册任务节点经 `_UNREGISTERED_TASK_REASONS`
逐型写理由（LockHP 比例阈值 vs 引擎钳 1 血/CreateBattleEvent 战斗事件体系/RetargetList
多目标重定向/DefineHPSharedGroup HP 共享组等未收编机制/
AttachEntityUnselectable 不可选标记/
AttachSkillTypeDisable 技能类型禁用/SetModifierValue
族 modifier 值改写/SetEntityActionState 具名实体（`AddGlobalDynamicOffset` 与
`SetEffectAnimatorParameter` 为镜头/特效表现，已忽略）
行动态/ConstructBodyPart 部位构造/任务位 StackProperty+StackStatusResistance+
StackWeakResistance 立即面板改写无 modifier 载体——语义待钉全列明），不再只报
"未注册任务节点"。`LockActionDelayChange` 已收编具名 `Mask_TurnBasedAdvance` 与
`Bit_Decrease` 子集：翻译为 `lock_action_delay`，保留施加者白名单、可选方向限制和显式解锁；
`immediate_action`/击破/冻结不走该常规推拉条锁，数字原因掩码继续拒绝。
`OnBeingLimbo`/`OnLimboWaitHeal` 在父 modifier 仍存在且 `hp_of(target) <= 0` 时复用
`on_hp_decrease`；`allow_negative_hp` 保证负血不直接判死，不把普通治疗事件当 limbo。
`SetDynamicValueByModifierValue` 的缺省 ValueType=Count，按 modifier 是否存在读取，
不等于 Layer 层数；ByCompareModifierValue 的 ValueType 缺省同样按 Count，编译为 has_modifier。
Layer/LifeTime/MaxLayer/CurrentShield 可读取事件目标、事件目标召唤者
或 GlobalTargetAlias 的 `$target`，不局限 Retarget。
`SetDynamicValueByCopying` 的源可为 self、LevelEntity、事件目标、CasterSummoner 或目标代数，
ToKey 默认仍写自身；ToTargetType=LevelEntity 时明确写入 `$level`，Ripper 的 7023RoleID 即此形态。
具名 `FromModifierName` 通过 `modifier_dynamic_of` 读取来源单位上该
modifier 实例的 DynamicValues；AddModifier 的 DynamicValues 编译进实例声明，表达式读取时在来源实例
语境求值，不退化为角色级动态值。`SetModifierDynamicValue` 的具名 Set/Add 写入同一实例槽，
TargetType 缺省按 Caster/自身；缺失实例跳过，这取代早期写角色级 set_dynamic_value 的近似。
跨技能 Bleed 未绑定改名实例，仍显式拒绝。唯一既有载体例外是
`OneMorePerTurn.OneMoreCount`：内建额外回合配额本就存于角色级动态值，Caster.Set 直接设值，Caster.Add 通过 `dynamic_of($self.actor_id, 'OneMoreCount') + NewValue` 累加；不写 modifier 实例槽，非自身目标仍拒绝。
当前 modifier 回调中的 AddModifier.DynamicValues 哈希可重新绑定为 `modifier_dynamic_of($self, 当前实例, 键)`；编译器按本敌实际 AddModifier 引用建表，不把实例载荷误读成角色级动态值。改名实例不套原始名称。
`FromModifierName=ParamModifier` 仅在两种明确作用域读取：Remodifier.TaskList 使用当前选中的
modifier ID（失败分支不继承），after_apply/after_remove_modifier 事件使用 `$event.modifier_id`；
无作用域读取、ParamModifier 动态写入及 DoT/AttackSign 等跨技能改名实例仍显式拒绝。
`SetDynamicValueByBattleTargetParam` 读取 `BattleTargetConfig.json` 中该 ID 的 `TargetParam`
静态阈值并写入自身 DynamicKey，例如 5001802/5001803 分别写 6/10，5001812/5001813
写 18000/10000；它不是当前进度读取。缺表、未知 ID 或缺 TargetParam 继续显式拒绝。
`SetBattleTargetProgress` 则把 ModifyValue 作为增量写入 `$level` 黑板的
`_battle_target_progress:<BattleTargetID>` 键，表达式先读旧值再加增量；不盖成固定 1，
也不按 TargetParam 截断。复用 `set_dynamic_value` 因而共享执行帧回滚与真存档，不另建
易漂移的进度副本。
`SetDynamicValueByAddValue` 支持 self、LevelEntity、单事件目标和目标代数：
分别读 `$self` / `$level` / `$event.target` / `$target`，增量和 Min/Max 钳制仍逐效果求值；
CasterSummoner 脱糖为召唤者过滤池，不用不可哈希的集合成员判定。
已解析 GlobalTargetAlias 的属性读取使用 `$target` + amount_target 逐目标求值，不按 `_Self`
后缀猜施放者；TargetFilter 内的 ParamEntity 始终绑定 `$it` 候选，过滤器外才映射事件目标。
`SetDynamicValueByProperty` 的 ParamEntity 在 on_hp_decrease/on_hp_increase 中直接读取
`$event.target` 的属性，不生成 amount_target；Retarget 多目标仍走逐候选求值通道。
`SkillTargetEntityList` 在 on_action 中读取 `$event.targets`，保留行动解析出的技能目标；
其直接伤害仍按 TargetInfo 编译主动 Action，不改成事件钩。
`AttackTargetList`/`ParamEntityAttackTargetList` 仅在 on_action_end 语境映射到 `$event.hit_targets`，读取执行帧按首次命中
顺序去重的实际命中列表；`SkillTargetEntityList` 不与其混用，也不接到缺失的目标字段。
MonsterSkillConfig 的 DamageType/AttackType 是元数据，不是 Ability 必须含伤害的证明；蓄力、标记和提示技能也可携带这些字段。完整任务树没有伤害时不再补报 DamageMissing；未知节点、缺失引用及伤害字段编译失败仍各自明确拒绝。
`ByCheckCharacterFly` 在当前实体模型中编译为 `1 == 0`：引擎没有飞行状态、飞行实体或飞行类型产生端，不能用动画/位移表现代替飞行机制。
`ByCompareSpecialAvatarType` 对 TYPE_TRIAL/TYPE_MISSION/TYPE_PLOT 在当前实体模型中编译为 `1 == 0`：TBGD 只有读取端，引擎没有这些特殊 Avatar 实体或类型元数据，普通 character 不能误判；其他特殊类型仍拒绝。
`AutoUseUltraSkill` 仅收单目标、单个 BindUltraSkillNames 且 WaitCutinFinished=false 的启停形态：Enable=false 施加 `locked_action_types=['ultimate']` 的具名锁，Enable=true/缺省时移除同 ID 锁；不按立即免费终结技处理。
`ByCurrentTurnState` 的 `ModifierPhase1Begin` 读取非倒计时回合的开始结算窗口：从 on_turn_start 到回合开始计时与 DoT 结算结束，进入行动阶段前复位；倒计时回合、行动阶段、回合末与回合外均为假。该瞬态标记不进存档。
Painter 的 `AIGHNCCAJPL` / `AGPCKNGHOAH` 仅设置或移除 `BPSkillPriority`、`AdvancedBPReserve`、`BPHealingSkill`、`IgnoreBPFail` 四项客户端自动战斗偏好。显式策略与手动决策不读取这些偏好，严格校验具名 modifier、已知字段及静态数值后无战斗 effect；额外字段、动态值与未知偏好仍拒绝，不与 SpecialBpFeature 混淆。
`ByIsControlSkillDisable` 在 MCommon_MindControl 的 OnCharmAction 语境编译为 `has_behavior_flag(target, 'Charm')`，只表示魅惑导致的控制按钮禁用，不泛化为任意控制或禁止行动。
`ByContainsParamFlag(Flag=IsFakeAvatarAttack)` 在当前实体模型中编译为 `1 == 0`：TBGD 只有读取端，引擎没有 FakeAvatar 实体或旗标产生路径，真实角色/怪物攻击不能误标为该类型；不新增事件字段，也不与 is_indirect 混淆，其他 ParamFlag 仍拒绝。
`ByCurrentSkillName` 的 SkillNameList 编译为各已绑定 action_id 的 OR 判等，任一名称无法绑定仍拒绝；`ByCurrentSkillName`/`ByCurrentSkillType` 可消费 on_action、on_action_end、攻击/受击及
on_hp_decrease 的 action_type/action_id 载荷；SkillType 缺省及数值 0 均按 Normal 映射 basic，
数值 1/2/3 分别映射 Skill/Ultra/Servant；`Elation` 映射引擎原生 `elation_skill`，不降为普通 skill/ultimate；
Servant 按行动来源 actor_type=summon 判定，
on_action/on_action_end 读 `$event.actor`，before_action 同样提供 action_id/action_type，受击事件读 `$event.source`；缺失 SkillType 仍拒绝。
`SetMonsterPhase.Inc` 不带 PhaseNum 时，self、单事件目标和已注册目标代数均可逐目标递增；
每个被选中敌人的 current_phase 分别 +1，不共用阶段，也不使用 amount_target 造成多目标重复求值。
`OnUltraSkillPrepare`/`OnBeforeUltraSkillPrepare`/`OnListenUltraSkillPrepare` 分别按自身/自身/全局复用 `on_ultimate_prepare`：事件在终结技选定后、扣能与执行前发射，和实际 `on_ultimate` 严格分开；目标尚未解析，不伪造 target。
`OnModifierOnStack`/`OnListenModifierOnStack` 复用 `after_apply_modifier` 的全局监听，
回调名/行为旗标读事件载荷；`ByCheckModifierCallBackModifierValue(Layer)` 在 after_apply_modifier 中以
`stacks($event.target, $event.modifier_id)` 比较本次事件 modifier 的当前层数；`ParamEntity`/`ParamEntity2` 在该语境指向当前目标，
`ByCompareCurrentModifierStatusType` 读 `$event.modifier_type`，不与定义期 `OnStack` 混淆。
`OwnerEntityAddAbility` 对机制 Ability 写入自身动态值 `_ability_enabled:<名称>=1`，表示注册而非立即执行；后续 Trigger/TurnInsert/TriggerParallelAbility 对该名称加 `dynamic_of(...) > 0` 调用闸。初始 AbilityList 已有的能力不重复加闸，纯表现引用仍无需注册。动态值沿用执行帧与存档，不另建状态副本。
`AddStageAbilityByName` 的同构子集把 `_stage_ability_enabled:<名称>` 写到 `$level`，实际调用走同一注册闸。CanReplace!=true 时支持静态持久 DynamicValues：注册时求值并保存到编译器的关卡 Ability 参数表，后续 Trigger/TurnInsert/Parallel 与被调用方参数合并，显式调用参数覆盖同名注册参数；任何非静态参数或 CanReplace=true 继续拒绝，不用布尔注册冒充动态绑定。
`TriggerAbility`/`TurnInsertAbility` 的 DynamicValues 按名称哈希绑定到被调用 Ability 的表达式作用域，
调用方值覆盖同名外层符号，调用结束恢复；子 Ability 的倍率、条件与动态写入共用该参数层。
AbortBehaviorFlags 的 `STAT_MonsterChangePhase` 复用 `has_behavior_flag` 检查持有者实际 modifier 旗标并反向门控；不另建“正在换阶段”的瞬时布尔状态。
`TriggerParallelAbility` 收编 `Delay=0` 的子技能：单条目直接顺序展开，允许多类机制任务；
多条目为避免虚构并行交叉时序，仍仅收无状态副作用的直接伤害。事件、单条展开与原生主动技能的伤害倍率均可读动态值；原生倍率在每段结算时经统一表达式宿主求值，覆盖多段变体和扩散副倍率。主/副目标段数匹配、元素一致且副倍率逐段相同时，复用同一多段扩散；不等副倍率仍拒绝。主目标别名按 target_type 区分敌我；ByAttack/ByMaxHP 分别写 scaling.atk/hp，主目标多段不得混用缩放属性；不同元素逐段写入 instance_variants.damage_type；不同副倍率逐段写入 instance_variants.scaling_blast，由引擎同点覆写；StanceValue/toughness_dmg 及扩散、变体形式也复用该段级动态求值通道。逐条展开 `ParallelAbilityList`
中的 Ability 引用，`TargetIndex(IndexStrict)` 以 `index=IndexValue` 精确选择零基位置，不截取前缀；
默认目标按 `TargetInfo.TargetType` 决定，非零延迟与多条目副作用仍显式拒。
`SetActionDelay` 与 ForceKill/RemoveModifier 共用 `_task_target`，TargetSequence 的过滤条件与完整目标规格不再被单别名解析吞掉。
非 DoT `OnStack` 的 `BaseSpeed`/`SpeedOverride`/`CriticalChanceBase`/`MaxStance` 写 `override_effects`
（MaxStance→max_toughness，重置与恢复均读有效韧性上限），
`AllDamageTypeResistance` 展开七元素 `res_*`，各 `XxxResistanceDelta` 也映射对应元素抗性；
DoT 按 DamageValue → DamagePercentage → BreakDamagePercentage 顺序取可用倍率（真实 AddModifier 可只提供后两者之一）；全部失败仍拒绝。
`SetDynamicValue` 先把 DynamicKey 写入编译符号表供后续 StackProperty 读取；局部符号表叠加在全局动态键名册上，不遮蔽其他已注册键，同时保留 after_apply_modifier
运行时写入。Set/DefineDynamicValue 若写入自身且完整来源闭包无任何读者，可在不求解写入值的情况下按 dead store 消除；LevelEntity、事件目标及任何有读者的写入不适用。
DoT 的 OnStack `SetDynamicValueByModifierValue(Layer)` 同样登记 ModifierLayers，
供 OnPhase1 DamageValue 使用。DoT OnStack 的 DefineDynamicValue 仅在完整来源闭包无任何后续读者时按 dead store 消除；存在读者的动态状态仍拒绝。带 `AttackSign` 的 modifier 始终生成目标侧 `lock_on`，
不再仅限 OnCreate 空回调；其 OnStack 动态目标等合法回调仍按原链执行。`StatusResistanceBase` 复用现有 `effect_res` 面板槽，与敌人基础效果和模板属性映射一致。`Level_FinalDamageAddedRatio` 归入既有 `dmg_final_dmg_boost` 最终伤害桶，与“提高至原伤害的 X%”同构，不走普通增伤池。`Monster_DamageTakenRatio` 是怪物持有者的全伤害承受增量，复用 `vulnerability`，不另建重复乘区。`IceTakenRatio` 等元素限定承伤属性复用目标侧 hit_condition + hit_stat_exprs(vulnerability)，只在对应伤害属性命中时计入既有易伤区；不与抗性混算，也不与普通面板属性混挂同件。`AllDamageTypePenetrate` 复用攻击侧全属性 `res_pen`，不按单一元素重复建槽。`BreakDamageAddedRatioBase` 与既有模板映射一致，写入击破特攻 `break_effect`，不是另建击破伤害加成池。`StanceBreakAddedRatio` 写攻击侧 `break_efficiency_boost`，`StanceBreakTakenRatio` 写目标侧 `toughness_taken`；`StanceBreakResistance` 作为该目标槽的负向增量（1=完全不受削韧）。
`AddModifier.ReferenceModifierName` 是被引用定义的显式来源：数据闭包同时收录 ModifierName 与该引用；槽位名自身无定义时才以引用定义编译，实例 ID 仍保留 ModifierName，已有自身定义不覆盖。`LockTargetActionDelay` 复用 `lock_action_delay`，TargetType 为被锁目标、Lock 缺省 true；目标支持自身、事件目标、战斗事件及其他已注册目标代数，不再硬限自身。WhitelistSourceEntity 仍只接受自身来源豁免。同一 modifier 的 OnStack/OnDestroy 分别上锁与解锁。
`TargetSortByActionOrder` 用 `action_delay_of / stat_of(spd)` 升序排列，按剩余距离÷速度还原实际行动先后，而不是只比较行动条比例。
`SetTargetTeamLocation` 经 `set_team_location` 支持队首/队尾与 CustomCaster 前后；AfterCaster 是紧邻参照之后，不复用召唤簇尾档位。SummonMonster 的 KeepOnFirst/KeepOnLast 分别复用 first/last 布场；FormationRecord 复用 record_formation_index 按阵营记录的原站位，ClearRecordEntityFormation 清除对应槽。动态怪物 ID 仅在 SummonIDList 提供非空候选闭集时收编，运行时按 summon_id_source 选择已登记变体。仅给 Row=N 时经动态值 `_FormationRow` 保存目标排号，N 须为非负整数。`ByIsEntityActionState` 复用 `action_disabled`，ActionState 缺省 true 表示可行动，false 查询禁用状态；`ByIsTargetAbleToAction` 同义编译为 `not action_disabled(target)`。`SetActionDelay` 的旧 `Value` 与 `NormalizedValue` 同走非负比例设值通道，0 仍编译为立即行动。`SetActionDelayNearTarget` 仅收 `NearType=After + IsInit=true`，复用同一 effect 的可选 `near_target`，剩余距离取近目标值的 `math.nextafter(..., +inf)`，不按比例推拉条。`ByCompareAbilityProperty` 与属性动态写入支持 CurrentSpecialSP/MaxSpecialSP，分别读取 `special_sp_of`/`max_special_sp_of`，数值来自 CharacterConfig 同名字段。ModifySPNew 的 IgnoreBlock 在当前无禁能载体的数据集合中不改变行为；引入禁能后须实现真实绕过。ByCompareTeamFormationRowIndex 读取目标动态值 `_FormationRow`（缺省 0），与 SetTargetTeamLocation.Row 的写入共用状态；不使用常量代替真实排号。ByAttackType(Servant) 按事件来源是否为召唤物判定（含 monster 类型的敌方召唤物）。ByTurnOwnerHasActionInTurn 读取当前回合归属者正在行动或行动阶段已结束的状态，复用执行帧与既有相位标记。`on_kill` 中 ParamEntity 是死亡目标、ParamEntity2 是击杀来源 `$event.source`；after_apply/after_remove_modifier 的
ParamEntity2 与既有谓词一样读 `$event.target`。这些别名在目标列表相交谓词与效果目标中也走同一映射；
其他事件的 ParamEntity2 仍按各自载荷单独核定。ByContainBehaviorFlag 多旗标缺省 ContainType=Or，显式 And 才要求全部；Frozen_Effect 复用 has_behavior_flag。`TargetFetchUniqueNameEntity` 与其他已注册目标代数共用任意 actor_id 动态值通道，不再额外要求敌方属性证明。`SpecialActionState` 与 Stealth 同走 `has_behavior_flag`，读取 modifier 实例保存的原始旗标。
`ByIsTriggeredBlockDamage` 只在持有者的 `after_being_hit` 语境读取 `$event.block_damage_triggered`：一次性免伤屏障消费后，即使 modifier 已离场，仍能识别本次命中；Inverse 取反，不以伤害量为零反推屏障触发。
`ByIsIndirectDamage` 在受击前/后读取 `$event.is_indirect`，该字段只来自 Action/DealDamage 的显式 `is_indirect`（上游 AttackData.IsIndirect）；Inverse 取反，不把相邻目标或追加攻击擅自当作间接伤害。
`ByCompareDamageTag` 仅在 DamageTagList 含一个 EnumIndex=3 的整数标签时编译为该值 `in $event.damage_tags`，Inverse 取反；多标签的集合比较语义未核定，继续显式拒绝。
标准 `DeathSetCamera`/`MuteHitFly` Ability 属死亡镜头与受击飞行动画，即使旧配置引用而定义未入闭包也不产生模拟效果；宽泛的 DeathEffect 不在此列。`SwitchBattleArea` 只切换场景 UnifiedId/演出状态，当前无区域战斗状态读取方，因此不生成模拟效果。`InsertBattlePerform` 只播放 Story/BattlePerformance 资产；改变通关判定的 `EnableStoryWin` 不属于表现节点。`SetMonsterHPTotalSeg` 只设置血条分段显示，不写 HP 或阶段阈值。
动态覆写由 override_exprs 现场求值，敌方速度统一经 `_sync_speed` 同步调度器。`ByCompareParamString` 的实样按当前 Ability 名在编译期比较，Inverse 取反；无当前 Ability 或空值拒绝。`ByCurrentTurnState` 收编 InsertAbilityActionPhase/InsertUltraSkillExecuting，读取执行帧的 insert/action_type，其他状态仍拒绝。谓词长尾同批收编：`ByCurrentSkillName`/`ByCurrentSkillType`（带 `action_type` 的行动/伤害事件，
`$event.action_id`/`$event.action_type` 窄化，SkillParam 绑定与词表外类型显式拒）、
`ByIsDamageType`/`ByAttackType`（伤害事件语境 `$event.damage_type`/`action_type` 窄化；`ByIsSplitDamage` 读取同事件的 `split != ''`，空串表示非均分；
BPSkill 复用 skill，ElationDamage 复用伤害管线既有 elation_damage，TrueDamage 读取 `$event.damage_type == 'true'`，Pursued 复用 follow_up；Servant 按事件来源是否为召唤物判定；Maze 是大世界秘技攻击类型，战斗内伤害事件中恒假，混合 OR 列表保留其他分支）、`ByHasStanceWeak` → `has_weakness(target, 元素)`，`ByTargetIsStanceWeak` → `has_weakness(target, element_of(attacker))`；`ByCompareStanceRatio` 的 Greater 0 边界复用 `toughness_of(target) > 0`，其他比例与比较符仍拒绝；动态 `ByCompareMonsterID` 经 `monster_id_equals(target, 表达式)` 做数值到模板 ID 的归一化比较、`ByCompareMonsterUniqueID`
自身静态支（ByCompareMonsterID 静态求值先例同口径，跨实例拒）、`ByIsTurnOwnerEntity`
（回合/行动事件语境 `$event.actor` 窄化）；`ByIsTurnActionEntity` 同样比较 `turn_owner_of()`，
自身、行动/受击目标或死亡目标由现有事件语境解析；语境不符一律显式拒（谓词语境无对应事件载荷），
其余未注册谓词经 `_UNREGISTERED_PREDICATE_REASONS` 逐型写理由（modifier 回调名/
站位索引/关卡语境/目标集交集/体型体系/侧判定词表待实测钉等）。`ByCompareWaveCount`
直译 `wave_index()`；`ByCompareAliveEnemyNumber` 按目标所属阵营取对立侧 `side_size`，
不等同引擎怪物计数；`ByTargetListAny` 以目标代数 `count_selected(...) > 0` 表达；
`ByIsTeammate` 比较目标与 caster 是否同属怪物侧/角色侧，不再缺省丢弃。
`CurrentTurnActionEntity` 与 `CurrentTurnOwnerEntity` 同指当前行动归属者，复用 `turn_owner_of()`。
`ByCompareTarget` 的单实体按 actor_id 比较；一侧为目标集合时先完整求值目标代数，再以
`target_in_selected` 判断实体是否属于结果，不把成员过滤提前塞进带 `index/take` 的候选池。
`ModifierOwnerSummonedMinions` 读取持有者的召唤物，`TargetFetchUniqueNameEntity` 读取具名绑定；
`AllDarkTeam.Select3` 等 `.SelectN` 后缀按一基编队位置编译为 `index=N-1`，随机/洗牌后的顺序仍显式拒绝。
`ByCompareMonsterPhase.CompareValue` 与动态阈值共用 `_value`，允许已登记的 MaxPhase 等表达式；
未知哈希和未注册部位目标仍拒绝。`ParamEntity.GetSummoner` 在逐候选过滤中读 `summoner_of($it)`；`CasterFilter=ModifierOwnerEntity`
按当前 hook 持有者过滤 modifier 来源，移除事件里也不改读 `$event.source`。
`AbilityTargetLeft/RightEntity` 分别取事件主目标左右一位，`GetCreator` 在角色登场与
modifier 持有者语境读对应 `summoner_id`；`count_selected` 的 `where` 同步继承事件命名空间。
`SetDynamicValueByProperty` 的 `ModifierOwnerSummoner` 与 `CasterSummoner` 同指召唤者，
`Defence` 读取有效防御 `def_`；混淆节点 BIEFKHPDHPI 的 FHLJGDGMMHK/OLPAJJAEEHH/IMOPHAJMIFO 分别归一为 SetDynamicValueByProperty 的 DynamicKey/ReadTargetType/Value，属性缺省为 MaxHP，额外字段仍拒绝；before_take_damage 的 ParamEntity 读受击者 `$event.target`，
ActionDelay 等已注册属性沿用对应读取函数；`ByCompareAbilityProperty` 的 CompareValue 可用
已解析动态表达式，MaxSpecialSP 等无运行载体的属性仍拒绝。`SetDynamicValueByModifierValue` 的 `CurrentShield` 直译 `shield_of(target, modifier_id)`，
读取关联盾的剩余值；队伍动态值可写 `$light_team/$dark_team` 运行态，普通玩家角色仍拒绝。
`LightTeamEntity` / `DarkTeamEntity` 按上游 `TargetFetchTeamEntity` 映射独立阵营伪实体；
modifier 谓词、施加与队伍盾共用该载体，不以 `$level` 或任一普通角色冒充。队伍盾由我方成员
受击共享消耗，存档保留载体。`TauntOrRandomEnemy` 按上游 `TargetFetchByTauntAndAggro(RandomByAggroWhenFail=false)`
编译为 `enemy_targets + taunt_or_random`：强制嘲讽/锁定优先，否则普通随机而非嘲讽值加权；
`WithoutServant` 与 `.RemoveServant` 变体额外排除有召唤者的单位。`SetDynamicEntityParam`
的 `TargetFetchUniqueNameEntity` 复用 `unique:` 目标池绑定具名实体，不改为自身目标；
其他跨主体绑定不在该别名收编范围内。`AllLightTeamWithAllLightTeamUnselectable` 等明确包含不可选目标的别名通过目标代数
`include_unselectable: true` 取存活单位，不改变默认目标池；`.RemoveServant` 保留
`not $it.summoner_id`，`.RemoveBattleEvent` 保留战斗事件排除，双队别名使用 `pool: all`。
`AllUnselectable` 则只取不可选单位与战斗事件，使用独立 `pool: unselectable`，不扩大为全体；
`GridFight_AllBackEnd` 是敌方全体并包含不可选，人数计数经 `count_selected` 第三参保留同口径。
`AllLightTeamWithAllDarkTeamWithAllUnSelectable` 才是双阵营并包含不可选（不含战斗事件）。
`AllLightTeamIgnoreServant.RemoveCharacterChangeTarget` 编译为我方池中 `actor_type_of($it) == 'character'` 的子集，排除召唤物与角色替换辅助实体；SetDynamicValueByCharacterCount 对该规格复用 count_selected。
能量任务的 `ModifierOwnerEntity` 直译自身；Retarget 的 `enemy_targets` 与 `AllUnselectable`
战斗事件也可作为 ModifySPNew 目标，`battle_event_create` 的 ParamEntity 读新实体 `$event.actor`。AddValue/FixedAddValue 的动态正负号在执行期分流到 gain_energy/consume_energy，绝对值复用同一表达式。ModifyActionDelay.AddNormalizedValue 同法分流 delay_action/advance_action，不提前猜动态符号。ChangeDelayVersion 与行动条预演配置中的同名字段一致，只使预演版本失效；模拟器总按当前状态重算，不改变 AddNormalizedValue 的实际增减量。ModifyTeamBoostPoint 的 ModifyValue 可为动态表达式，Set 在运行时经非负整数闸，Add 走原队级增减通道。
战斗事件正向回能不受角色 `max_energy=0` 上限钳制，消耗仍以下限 0 为界；`on_break` 的
ParamEntity 读取 `$event.target`。`ByCompareHPRatio.CompareValue` 与
`ByCompareModifierValue.CompareValue` 允许经 SkillParam、全局模板动态键与已绑定 modifier
参数求值；怪物 ID 已能静态确定的分支先做布尔短路，不编译不可达支。写后读标志在
`ByAnd/ByAny/ByNot` 与 `OnStack` 属性分支中同步透传，嵌套阶段谓词仍走 effect 级活读。
主动技能挂载与被动挂载的 modifier 都可监听 OnHPChange/OnListenHPChange，复用同一 HP 事件拆分通道；其他主动侧事件仍逐类核定。事件语境的 Retarget 直接伤害只生成 deal_damage，不再写入主动 Action 专用的 retarget_damage_records；后者仅在 action 语境登记并参与段组装，避免同一伤害被回调包装器重复判为未实现。
AddModifier 的 Chance 与 delay_action 的 apply_chance 可在执行时读取动态表达式，再进入既有效果命中/抵抗判定；编译器将 apply_chance 纳入表达式槽校验。
`SetDynamicValueByMaxBP` 仅含 DynamicKey 时写自身该键，值由 `max_skill_points()` 读取引擎统一 `_sp_max()`；这是队伍上限的只读查询，不另建 BP 状态。
`OnSPChange` 是能量变化监听，映射到 `on_energy_change` 并窄化到 `$event.target` 持有者；SetDynamicValueByChangeValue(RawDelta) 与 ByCompareParamValue 均读取 after-before，ByCompareSPRatio 复用 energy_of/max_energy_of。事件在回能、耗能和设值实际完成后发射，值不变不发射；与队级战技点事件严格分开。
`SetDynamicValueByVariateType.MaxMonsterPhase` 优先读取 CharacterConfig 同名上限；缺字段时可从当前来源闭包内显式静态 SetMonsterPhase.PhaseNum 写入取最大值，Inc/动态写入不参与，仍无证据则拒绝。HP 变化事件的
`ParamValue` 是有符号净变化量：on_hp_decrease 为 `-$event.amount`，on_hp_increase 为 `$event.amount`。
`SetDynamicValueByChangeValue` 在这两个事件中把同一净变化量写入自身 DynamicKey，其他 ChangeValue 语境仍拒绝；
`ByCompareParamValue` 比较同一值。引擎事件自身的 `amount` 仍是非负实际变化量，不改公共事件契约。
HealHP 的 ModifyValue 是与 HealPercentage 互斥的同义数值槽，按 FormulaType 走既有治疗公式；两字段同时声明仍拒绝。FormulaType 省略时使用上游枚举零值 HealByHealerAttack，即 `heal.amount = 数值 × $self.atk`，不按目标生命上限猜测。HealerTargetType 为 Caster/ModifierOwnerEntity 时确认治疗者就是 `$self`，其他独立治疗者目标仍拒绝。HealByBaseValue 直接写 heal.amount，HealByTargetMaxHP/HealerMaxHP 仍按各自生命上限计算。`ByCompareDamageCustomName` 在受击前/后事件中比较 `$event.damage_custom_name == CustomName.Value`，支持 Inverse；Action 与 hook 的 damage_custom_name 均由 AttackData.CustomName 原样供给，不拿 action_id 或显示名替代。`SetDynamicValueByDamageDataProperty` 在受击前/后事件中把当前 `$event.amount` 写入自身 DynamicKey；ReadTargetType 接受同义的 Caster/ModifierOwnerEntity 与事件目标 ParamEntity，不改变两种事件各自的 amount 口径。
`WaitFor` 仅接受 ByDieAnimFinished 与 ByHaveInsertUltraWait：死亡链和插入技能在模拟器中均同步完成，演出等待不产生额外效果；其他等待谓词仍拒绝。`WaitMissionTalkFinish` 同样只是剧情对话演出屏障，不改变战斗状态；因此 ByBattleMissionTalkFinish 的两个分支若均只含此类等待，整个条件节点直接消除，含机制分支仍拒绝。`WaitAbilityStartTimeStamp`/`WaitSkillPerformAbilityFinish` 同为技能演出计时屏障；`EnableEmotion` 为表情开关。`WaitCustomString` 等待对应的客户端表现信号，在当前同步技能/死亡链中同样不保存墙钟等待或生成战斗状态；实际机制仍由相邻任务独立编译。空 `TaskConfig` 与空 `ApplyOperation`（键集严格只有 `$type`）是序列化占位，不产生 effect；出现任何额外字段仍拒绝。`OPBLGCPAKKI` 仅在原始形态为 `Origin`/`Root` 两个挂点名字段时按模型表现消除，新增字段仍拒绝。
`SetDynamicValueByStanceCount` 在 ReadTargetType=ModifierOwnerEntity 时复用 `stance_count_of`，把主条与全部追加条的总数写入自身 DynamicKey。`SetStanceCount` 仅在不含 IsReset/AddCustomValue 及其他参数时按“不改变条数”的空操作收编；真正重置或增减条数仍显式拒绝。
`TriggerStanceCountDown` 编译为 `trigger_stance_countdown`，逐目标发射 `on_stance_countdown` 并透传 IgnoreMuteBreak；`OnBeingStanceCountDown` 按 `$event.target == $self.actor_id` 监听。该事件任务不直接削韧或置击破。
`TriggerBreak` 在无额外字段时编译为 `trigger_break`，复用引擎完整击破链；on_break 语境沿用 `$event.element`，其他语境按既有缺省 physical。已条尽目标跳过，防止 OnBeingBreak 连锁重入；IgnoreMuteBreak 缺省/false 时目标若持有 MuteBreak 行为旗标则跳过，true 才绕过；其他额外字段仍拒绝。
`SwitchCaseByAttackDamageType` 在 ReadTargetType/AllType 形态下按当前 `$event.damage_type` 分流：各 Case 编译为 effect 级等值守卫，Default 使用全部 Case 的反向守卫；纯表现整树仍直接忽略，非法或重复属性显式拒绝。通用 `SwitchCase` 在 WithBreak=false 时逐项复用 PredicateTaskList；DefaultTask 仅允许纯表现子树，带 break 或机制默认分支仍需排他守卫并显式拒绝。任意 PredicateTaskList 的原始 SuccessTaskList 与 FailedTaskList 若完全相等，则无论谓词为何都只编译一次共同任务，不再需要该谓词的运行时载体；近似或不同分支不在此列。命中域回调中若每个 SuccessTaskList 都只改写同一已注册属性、Failed/Default 均纯表现，则每项编译为 `谓词 ? 数值 : 0` 并加算，保留多分支同时成立的语义。LoopTargetList 内无参数的 GoNextTargetInList 由目标池逐项求值吸收，不另维护游标；循环外同名节点仍拒绝。无载荷的 `ResetTeammateAttackPerform` 只复位攻击演出，控制解除仍由相邻 RemoveModifier 独立编译。`SetBossHPStanceChangeType(ChangeType=Heal)` 只设置血条恢复演出与 ChangeTime，不改写 HP；其他 ChangeType 仍拒绝。`BySimulateSpeedUp` 的成功/失败分支若均为纯表现（含上述血条恢复演出），整个条件节点不产出战斗效果；任一分支含机制时仍须显式处理谓词，不按固定倍速猜测。
CharacterConfig 主动技能缺 MonsterSkillConfig 行时，纯表现 EntryAbility 可跳过；含机制的 Ability 也可由配置直接编译，行动 ID 使用稳定的 `敌人ID:触发键`。但伤害段若未显式给 StanceValue，不能猜缺行中的基础削韧，仍拒绝。缺 Ability 或其他无法解析内容同样拒绝。
反向的孤立 TBGD 行不生成行动：整个来源闭包内被 SkillParam 引用的行是被动参数容器；无 CharacterConfig 入口、无 SkillParam 引用且无 ConfigAI 引用的行是不可达数值孤儿，不按主被动名称区别对待。ConfigAI 仍引用的缺行保留数据不匹配错误。
`ParamEntityAdjoinEntity` 以 `$event.target` 为参照复用 `is_adjacent`，与 AbilityTargetAdjoinEntity 同为相邻单位目标代数。`AbilityTargetEntity.WithServant` 用主目标或 `$it.summoner_id == $event.target` 选择主目标及其召唤物。`ParamEntity.GetCreator` 在 after_being_hit 中取受击目标创建者；战斗事件创建时记录 summoner_id=创建者，谓词与后续效果共用该链。
`ByAvatarBaseType`
按官方命途内部名经 PATH_ALIASES 归一后查询 path_of；`ByCompareStance` 读取 toughness_of；
`ByCompareTurnActionEntityTeamType` 用 turn_owner_of 的怪物侧归属判断 TeamDark/TeamLight，
TeamLight 包含召唤物而非只限 character。`ByCurrentSkillTargetType(AllEnemy)` 在 on_action
语境比较 target_type=aoe；`ByIsMatchTeammateCount` 按 Count0/1/2/3 比较对应阵营存活数，
缺省为 Count0。完整支持的主动技能
在正式生成器中优先走该路径；下述 Fandom 文本转换属于尚未迁移机制族的遗留路径。
`CreateBattleEvent` 的 EventID 注册与 OnBattleEventCreate 已收编：创建任务生成独立伪
ActorState（不入场/不占位/可持 modifier），`ParamEntity` 经保留 UniqueName 指向该实体；
公开 UniqueName、存活谓词与 JSON 存档均复用同一实体，不再把 ParamEntity 错解为角色。
注册后发射 `battle_event_create`，OnListenBattleEventCreate 直接订阅；当前事件的
TargetBattleEventID 直译 `$event.event_id`，ParamEntity.GetCreator 直译 `$event.source`。
`SetMonsterViewPhase(PhaseType=Form)` 直译自身 `current_phase=PhaseNum`，与后续阶段事件共用
动态值写入链，不按纯表现忽略。`OnMonsterPhaseChanged` 订阅 `monster_phase_changed`，事件只在
最外层执行帧提交后发射，嵌套先并入父帧，回滚/同值不发。
`TargetInfo.AllTeamMember` 映射 `ally_aoe`，敌方行动时该类型返回全部存活友方怪物，
不落入玩家目标池。属性件仅在整个 stat 块可静态证明全为增益时标 `buff`；正向
`vulnerability`、任一负向其他 stat 或任一未判号表达式仍按保守 `debuff` 处理。
条件伤害只在谓词分支前已有主伤记录时转为 `on_action` 的 `deal_damage`，保留分支条件；
此时它属于主伤后的附加段。谓词前没有主伤时仍拒绝，避免条件主伤或后续主伤被错误重排。
概率分支（`PredicateTaskList` 的谓词为 `ByRandomChance`，109 节点全为静态 Chance）编译为
**单 hook + effect 级 condition**：前置 `bind_roll`（`roll_key` 按节点路径生成稳定键，
`scale` 缺省 1）绑定共享掷骰，Success 分支效果带 `roll('<键>') < Chance`、Failed 分支带
`roll('<键>') >= Chance` 的 effect 级 condition——hook 级快照发生在任何 effect 之前，
概率分支必须落 effect 级（执行帧 `23_event_hook_system.md` §23.15）。`RandomConfig`（无 `RandomMaskKey`/`RandomCount`；单独 `RandomUnique` 的单次抽取不受唯一性影响；权重可为已注册运行时表达式，静态值仍须非负且总和为正）按同一结构翻译：bind 带 `scale=Σ权重`，各选项守卫为
累计权重区间 `roll('<键>') <= 累计_i and roll('<键>') > 累计_{i-1}`（与上游
`rng.random()*Σ <= 累计` 同浮点序）；带多抽/战斗级记忆字段（`RandomCount`/`RandomMaskKey` 等）的节点保持 unsupported 进 human_queue，禁止猜测。事件域概率分支与主动域共用
同一翻译，帧外事件由 HookRuntime 自动建帧；写后读类活读（不消耗随机流）两域均可。
`ByAnd`/`ByAny`/`ByNot` 内嵌套的 `ByRandomChance` 直译为带稳定键的 effect 级 `roll` 守卫，不额外生成前置 bind；`roll` 在首次实际求值时才采样并于当前帧绑定，保留逻辑短路和同键零重复消耗。`bind_roll` 的 expected 模式绑 `0.5×scale`（0.5 取 0.5 的下邻
浮点），与 `mechanic_chance` 的 `p>=0.5` 期望口径逐比特一致。
`SetDynamicValueByCopying`（自指目标）编译为 `amount: dynamic_of($self, '<FromKey>')`
的 `set_dynamic_value`；`SetDynamicValueByAddValue` 的 Min/Max 钳制用表达式
`min(max(dynamic_of + AddValue, Min), Max)` 内联组合（AddValue/Min/Max 可为已解析表达式，
`LockTargetHP` 复用 `LockHP` 的阈值锁血 modifier，`UnlockTargetHP` 按同一
`ENEMY_LOCK_HP_<enemy_id>` 摘除；无法解析的事件目标仍拒绝。`LayerAddWhenStack` 允许 `dynamic_of` 等运行时表达式，复用 hook `apply_modifier.stacks`
逐目标求值与取整；`MaxLayer` 仍须静态，未知哈希不猜固定层数。
`ModifyTeamBoostPointMax(ModifyFunction=Set)` 复用 `set_sp_max` 设置全队战技点上限；
Add/其他修改方式、负值与非整数继续显式拒绝。读的是帧覆盖层旧值——帧内累积语义），不加引擎原语。DefineDynamicValue/SetDynamicValue
保留解析后的 $level/召唤者/召唤物写入目标，不在生成 effect 时回落为 self；明确的
AllDarkTeam、pool=enemies（含部位实体）与 unique:$battle_event 目标分别逐敌方或战斗事件写入。
战斗事件动态值以其实体 ID 为运行态键；ParamEntity 和未证明敌我属性的具名目标仍拒绝。
单目标 `FireProjectile` 允许缺省或 `AbilityTargetEntity` 主目标；`Caster` 与
`ModifierOwnerEntity` 编译为 `pool:self` 的自身目标。`OnProjectileHit` 支持主目标直伤、AbilityTargetAdjoinEntity 相邻段与已注册的非伤害任务；相邻段原样进入既有 scaling_blast/段级变体通道。紧跟主目标的左/右分写仅在经同一伤害编译器干跑、归一化记录完全等价时合并为一条相邻段，避免双倍结算；未配对或不等价仍拒绝。Retarget 内仅在 take=1 或唯一实体给出单主目标时允许，
多目标仍拒绝。`NewFireProjectile` 的 NewProjectile 飞行数据与旧节点不同，但命中任务同构，
复用同一编译链；RemoveEffect/空命中
仍按纯表现处理。`ByIsInElationTime` 读取 `_elation_time_active`，不把它与
`AddStageAbilityByName` 的阶段 Ability 加装混为一谈。`ByTurnOwnerActionPhaseEnd`
读取行动末至回合末结算间的 `_turn_owner_action_phase_end`，下一回合开始复位，不按
`on_action_end` 近似。`FireWaveProjectile` 以
`Count` 展开为 `Action.instances`，逐段复用 `PerProjectileDamage`；`OnProjectileHitClientOnly`
仅在接受纯表现时忽略。`TargetTimeSlow` 与共用 `SlowKey` 的 `ClearTargetTimeSlow` /
`RemoveGlobalTimeSlow` 同属表现层慢动作设置/清除，不改变行动值、速度或事件时序；
`ChangeCharacterConfigParamClientOnly`、`UpdateMonsterFootIKMode`、`ChangeMonsterHeadIcon`、
`SetCharacterVisibilityFollow`、`SetMonsterHitCountEnergyBarState` 的原始载荷也只涉及客户端
HUD/头像/IK/可见性/能量条；`SetBattleItemProgressInfo` 仅进度展示，
`WriteCustomValueToStatistic` 仅挑战统计且不反哺战斗条件；`OverrideMonsterRankScore` 仅覆写或恢复挑战评分显示，不改变怪物 Rank 查询、目标选择、伤害或行动，也按表现节点处理；`PBEMMHIOJBO` 只控制
`Screen_Visible` 的屏幕显隐；`LHOKPKHEBIK` 仅设置 Screen 特效附着点与位置偏移，
在 OnStack 直接任务和条件分支中同样不产战斗 effect。`SetCustomLocationConfig` 仅设置模型/碰撞
Width 与刷新标记，不改变编队站位、目标池或战斗数值，也按表现节点处理。
`_visual_modifier` 与 `_presentation_only` 共享结论：Retarget/条件分支整棵子树仅产生
SetBattleAchievement 时同样按表现处理；一旦包含伤害、动态计数或其他战斗效果则不再忽略。
OnStack 的定义扫描也先消除双支均为纯表现的条件节点，再对其余分支求值谓词；因此
ByHaveUniqueNameEffect 等特效存在性判断不会在无副作用分支中产生虚假的战斗拒因。
`ShowBattleConditionUI` 仅显示战斗条件提示，不产战斗 effect；`HeadLookAt` 的朝向/根旋转只影响演出，不改变行动或伤害；`ResetTeammateAttackPerform`
即使空节点也没有足够证据证明可忽略，继续显式拒绝。

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
`MDF_MaxLayer` 在 modifier 声明了该动态槽但未传值时，读取当前父 modifier 的
`modifier_max_stacks`，不继承首次常量或重置重挂状态；条件光环同步提供 `$modifier/$mod`，
使 `MDF_Layer` 等层数表达式可正常求值。原始 `DirtyHPRatio` 统一映射 `recoverable_hp_reduction`，并列的 `DirtyHPDelta` 映射固定扣减 `recoverable_hp_delta`：可回复上限先按折扣减，再减固定量并钳到非负；OnStack 的 StackProperty 写入该面板字段，
SetDynamicValueByProperty 经 `stat_of` 读回同一有效值；不另造扣生命上限或治疗乘区。
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
`controlled(target, 'taunt')`，不再按纯表现件跳过。复数 `Flags` 的单元素形态等价于 `Flag`；
显式 `ContainType=And` 的多旗标逐项以 and 连接，未声明组合方式的多旗标仍拒绝。`STAT_DOT_Electric` 直译为
`dot_kind(target, 'shock')`；`Stealth` 直译为 `has_behavior_flag(target, 'Stealth')`，
只读取 modifier 原始旗标，不未经证据改写成不可选中能力。公共 `MCommon_CTRL_Frozen` 生成
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
寻址标记，不另生成 DSL 件。`EventType.Value=3/4` 且同样携带 `DOT_TriggerRatio` 时分别只引爆 Thunder/Wind DoT，复用 `trigger_dot.dot_element` 与比例槽；依据是 Electric/Poison 触发器和对应 OnCustomEvent 伤害定义，其他事件值仍拒绝。有 `trigger_dot` 的技能不再被误判为缺少直伤。目标数量沿用
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
`LocationType=LastDie` 仅在 `on_kill` 语境编译为 `position=last_die`，运行时取本次死亡目标的
原站位，尸体仍插在原实体之前；缺失或存活引用显式报错，不回退为 after_owner。
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
