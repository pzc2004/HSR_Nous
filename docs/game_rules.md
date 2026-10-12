# 崩坏：星穹铁道 战斗规则

本文档记录崩铁核心战斗机制，作为战斗模拟器的**唯一事实来源**。

> 当本文档与代码实现冲突时，以本文档为准，代码需要修正。

---

## 目录

> 分册文件清单的唯一来源是 [README.md](README.md) 目录树（索引闸 `tests/test_doc_lint.py` 双向校验磁盘）；本表为章节导航，说明列如有出入以分册正文为准。

| 章节 | 说明 | 详细文档 |
|------|------|---------|
| **0. 游戏基础** | 命途/属性/光锥/遗器/养成/基础属性总览 | [mechanics/00_game_basics.md](mechanics/00_game_basics.md) |
| **1. 基础属性** | 角色/敌人属性计算、治疗与护盾、技能分类、记忆命途与忆灵 | [mechanics/01_base_stats.md](mechanics/01_base_stats.md) |
| **2. 伤害公式** | 完整伤害乘区体系（增伤、易伤、防御、抗性、暴击、真实伤害等） | [mechanics/02_damage_formula.md](mechanics/02_damage_formula.md) |
| **3. 行动序** | 回合/轮次/波次概念、行动值计算、拉条/推条、速度变化、额外回合、冻结 | [mechanics/03_action_sequence.md](mechanics/03_action_sequence.md) |
| **4. 击破机制** | 韧性削减、弱点击破、击破伤害、超击破 | [mechanics/04_break_system.md](mechanics/04_break_system.md) |
| **5. 能量机制** | 能量获取、终结技释放、能量恢复效率 | [mechanics/05_energy_system.md](mechanics/05_energy_system.md) |
| **6. 战技点机制** | 战技点上限、获取与消耗规则 | [mechanics/06_skill_points.md](mechanics/06_skill_points.md) |
| **7. Buff / Debuff** | 持续时间、结算机制、层数叠加、驱散规则 | [mechanics/07_buff_system.md](mechanics/07_buff_system.md) |
| **8. 欢愉命途** | 欢愉伤害、阿哈时刻、笑点、好活当赏 | [mechanics/08_elation_system.md](mechanics/08_elation_system.md) |
| **9. 追加攻击** | 触发条件、反击（Counter）、追加攻击限制 | [mechanics/09_follow_up_attacks.md](mechanics/09_follow_up_attacks.md) |
| **10. 嘲讽机制** | 基础嘲讽值、受击概率计算 | [mechanics/10_taunt_system.md](mechanics/10_taunt_system.md) |
| **11. 特殊机制** | 专属效果、控制效果、HP 事件 vs 伤害事件、结界/境界/连携攻击 | [mechanics/11_special_mechanics.md](mechanics/11_special_mechanics.md) |
| **12. 秘技系统** | 秘技点（TP）、秘技分类、战前策略 | [mechanics/12_technique_system.md](mechanics/12_technique_system.md) |

---

## 核心公式速查

公式不双份存放（防腐）——查询入口：

- **可执行唯一来源**：`src/hsr_nous/sim_schema/rulebook.yaml`（伤害公式/乘区/常数/模式表，引擎直接消费）
- **文档镜像**：`src/hsr_nous/sim_schema/docs/01_formula.md`（与 rulebook 逐字一致，lint 镜像闸保证）
- **数值事实与各乘区讲解**：[mechanics/02_damage_formula.md](mechanics/02_damage_formula.md)（伤害）、[mechanics/03_action_sequence.md](mechanics/03_action_sequence.md)（行动值/拉条）、[mechanics/04_break_system.md](mechanics/04_break_system.md)（削韧/击破）

---

## 待确认事项

- [ ] 追加攻击的触发条件分类是否需要进一步细化（关联本地待办台账"追加攻击事件流"待实测行）
- [ ] 强烈震荡的触发来源与抵抗机制

## 修改记录

- 2026-10-12：**「暴露已有信息」三通道落地 + 对应装备族收编（B36 批 2）**——三条「信息已在引擎/数据、只欠暴露给表达式/载荷」的通道各按「白名单注册（`sim_schema/expression.py` 唯一事实来源 + hooks 宿主函数表）+ 字面量参词表闸（错拼编译期炸）+ 文档登记（`sim_schema/docs/22_syntax_reference.md` §22.4/§22.10、`04_modifier.md` §4.11/dot 载体节）」落地：① `has_weakness(target, element)` 弱点查询谓词（`pipeline.effective_weakness` 同口径含植入，元素词表 `sim_schema/action.py` `ELEMENTS` 闸、小写归一、动态参运行期非词表值 false-y 缺省）；② `dot_kind(target, kind)` DoT 种类谓词（新词表 `DOT_KIND_ELEMENTS`：触电 shock=雷 / 风化 wind_shear=风 / 灼烧 burn=火 / 裂伤 bleed=物理，判定 = `modifier_type=='dot'` + `dot_element` 映射）+ `debuff_count(target, source)` 可选 source 参（按 modifier `source_id` 窄化计数）；③ `summoner_of(actor)` 忆灵归属谓词（`Actor.summoner_id` 直读，`stat_of/element_of` 同目标解析通道，查无返回 `""`）。装备族收编 11 件 + 2 件挂账收窄：通道①——108 繁星璀璨的天才 4pc（量子弱点额外无视 10% 防御，`has_weakness` + scoped `def_pen` 命中域）/316 劫火莲灯铸炼宫 2pc 件 B（击中火弱点目标击破特攻 +40% 1 回合，`after_being_hit` 攻击方视角 + `has_weakness`）；21040 银河沦陷日暴伤段与 23041 生命当付之一炬弱点段经官方文本复核（query-game-data 对轴）维持挂账——挡因分别收窄为攻击级目标集按谓词计数（`count_where` 未实现）与「装备者添加的」弱点来源归属检索（`weakness_add`×`source_id` 双键谓词无通道），挂账口径 e2e 钉在案。通道②——21022 延长记号（触电/风化目标增伤，`dot_kind` 双值析取 scoped all_dmg）/23022 重塑时光之忆①（先知按类叠层：四类 `dot_kind` 判定 × 直伤 `after_being_hit` 与跳伤 `on_hp_decrease reason=='dot'` 双通道 × 按类记账闩，计数件 `refresh` +1 层 `max_stack` 4，每层 atk 经 `stat_exprs` 条件光环按层现值；与批 1 已收编的 ②DoT 穿透联动成整段）/24003 孤独的疗愈②（装备者施加 DoT 目标被消灭回能，`on_kill` + `debuff_count(source=…)`——全负面口径偏宽在案，kind×source 交叉窄化待下批）/23047 海洋为何而歌①（魂迷层叠六件计数加来源过滤——批 1 全口径近似收口；命中域 `$self`=敌方件读不到装备者 id，经 `who_has('LC_23047_EHR')` 我方反查）/21026 汪！散步时间！（`dot_count` 宽口径升级 `dot_kind` 灼烧/裂伤精确集合）。通道③——8 件「装备者的忆灵」近似件逐件换 `summoner_of` 归属判定：20021 焚影/21050 胜利只在朝夕间/21054 故事的下一页/21057 花儿不会忘记/123 凯歌祝捷的英豪 4pc/124 哀歌覆国的诗人 4pc/125 烈阳惊雷的女武神 4pc（来源侧+目标侧双侧替换）/127 再创天地的救世主 4pc（目标代数 `$it.summoner_id == $self.actor_id`）；「忆灵在场」存在性语义件（123 速度件 `enable_if`、127 B 钩）保持 `has_summon($self)`——己属召唤物反查本即精确。23050 勿忘她的火焰「添加弱点回 SP」挂账标下批（需「植入动作」事件/谓词 + 开战队友记账，计数器闩可组）。e2e：每通道每族生效+反例两侧钉（多忆师编队误挂反例 8 钉，`tests/test_lc_memory_e2e.py`/`tests/test_relic_amphoreus_e2e.py`），对拍红钉三处修收敛（108 量子弱点档双方同值、23047 官方口径 1 层、23041/23022 挂账注收窄）

- 2026-10-12：**装备 stale 挡因批量收编一波（B36 批 1，17 件——零引擎工作，通道全部已在库）**——2026-09-16/09-23 引擎通道批（debuff 判定三原语/scoped 双暴/scoped def_pen/target_hp_ratio/has_stat_penalty/has_shield/hit_stat_exprs，`sim_schema/docs/04_modifier.md` hit_condition 节）落地前登记的 17 件装备「待收」 fixture 机制，自 notes 收编进 DSL hooks：① 光锥 15 件——20009 乐圮（目标 HP%>50% 增伤，`$event.target_hp_ratio` scoped all_dmg）/21006「我」的诞生（目标 HP≤50% 追加额外增伤）/21012 秘密誓心（目标 HP%≥装备者 HP% 额外增伤，`hp_of/max_hp_of` 跨 actor 比较）/20011 渊环（对减速目标增伤，`has_stat_penalty` spd 双键）/22000 新手任务开始前（攻击减防目标回能，on_become_target 钩 + def 双键）/23004 以世界之名（对负面目标增伤，`has_debuff`）/23001 于夜色中（终结技暴伤速度档，hit_stat_exprs per-hit 求值）/24001 星海巡航（对 HP≤50% 目标暴击率）/23027 驶向第二次生命（击破伤害无视防御，`'break'` 路由限定）/23028 偏偏希望无价（终结技/追加无视防御双类析取 + 进战/普攻双钩挂窗）/23031 我将，巡征追猎（流光每层终结技无视防御，hit_stat_exprs 按层现值）/21053 愿旅途永远坦然（我方持盾增伤，`has_shield` + on_turn_start 懒扫描双钩，128 隐士同通道）/24003 孤独的疗愈①（终结技持续增伤 2 回合，`dmg_dot_dmg_boost` 桶）/23022 重塑时光之忆②（先知每层 DoT 无视防御，hit_stat_exprs——叠层钩①按类记账挂账下批）/23047 海洋为何而歌②（魂迷 DoT 承伤 #4×min(N,6)，116 族层叠六件——承伤件挂敌方读不到装备者叠影绑定，hit_stat_exprs 不适用故走阈值件求和；①「装备者施加的」来源过滤挂账下批，现按全口径计数近似在案）；② 遗器 2 套——112 盗匪荒漠的废土客 4pc（对负面目标暴击率/对禁锢目标暴伤，`"imprison" in $event.target_control_kinds` 分类型控制判定）/119 荡除蠹灾的铁骑 4pc（BE≥150% 击破无视 10%/BE≥250% 超击破无视 15%，`stat_of($self,'break_effect')` 命中域现值阈值）。语义纪律：官方文本拿不准段一律挂账不硬凑（24003②击杀回能=DoT 来源检索族、23022①按类叠层、23047①来源过滤三族下批）；逐件机制→hooks 映射与收编记见各 fixture 头注（`data/library/light_cones/`、`data/library/relics/`），e2e 钉（机制生效 + 反例不生效两侧）见 `tests/test_lc_{destruction,erudition,warlock,hunt,knight}_e2e.py` 与 `tests/test_relic_110_120_e2e.py`

- 2026-10-12：**`trigger_dot` 选择性引爆槽扩编 + 卢卡天赋引爆收编声明式**——① 过滤槽 `element` 改名 `dot_element`（与 modifier 的 dot_element 字段对齐——旧键编译期即炸；元素词表闸/小写归一/与 scope AND 叠加语义不变）；② 新增 `ratio` 引爆比例槽（缺省 1.0=全额跳伤，表达式通道同 break_damage 先例）——「立即产生原伤害 X%」族正典口径：引爆值 = ratio×正典跳伤值（dot/bleed 正典链不暴击、快照/现值取头与自然跳伤同 `_settle_one_dot` 单漏斗、不耗 duration、`on_dot_retrigger` 照发）；引擎实现为 settle 全额扣血后退回未引爆部（账目/护盾/事件全按 ratio×跳伤值记，ratio=1.0 路径逐比特不变）；③ 卢卡（1111）天赋「火花四溅」自 deal_damage×dot_value 绕路钩迁 `trigger_dot + dot_element: physical + ratio: param(111104, 2)`（双槽首实例）——绕路钩直伤链期望暴击（×1.025）偏差随收编消灭（官方文本 "the Bleed status will immediately deal DMG for 1 time equal to X% of the original DMG"——DoT 不暴击），引爆跳自此照发 `on_dot_retrigger`（黑天鹅奥迹「每收到 1 次持续伤害」族正确连锁）（`sim_schema/docs/05_effects.md` §trigger_dot 节与 §5.2 行、`sim_schema/effect_types.py` 词表注释、1111/1410 fixture 头注同步）

- 2026-10-12（三批）：**机制正典归位 `data/library/` + `_is_enemy` 术语改正**（数据布局终态，零行为变化）——① 手写全机制 DSL 模板（characters/light_cones/relics/enemies 四类）自 `tests/fixtures/templates/` `git mv` 至 `data/library/`（机制库正典根，全 tracked、rename 100% 保历史），命途系统模块同迁 `data/library/system/paths/`；`data/sim_templates/` 回归纯生成物兜底根（gitignored），`data/battles/` 对局配置入库（gitignore 放行收窄为 `!data/library/` + `!data/battles/` 两行，旧 sim_templates 夹心例外撤销）；tests/ 零 YAML。② 运行时模板查找链 `RUNTIME_TEMPLATE_ROOTS=("data/library", "data/sim_templates")`（正典优先、生成兜底，唯一事实源 `sim_schema/templates.py`）——生产裸编译全机制可达（2026-10-12 一批 fixtures 过渡根收官）；annotator 锚根/载体根、对拍脚本根、web `--templates` 示例、e2e 路径字面量全链同步。③ 引擎 `_is_monster` → `_is_enemy`（机制按敌我分不按物种分：我方角色/召唤物/忆灵均无韧性属性——韧性为敌方专属机制，人形 Boss 同走韧性逻辑）+ 类常量 `MONSTER_TYPES` → `ENEMY_TYPES`（actor_type 词表值 "monster"/"enemy" 是数据值、上游文件名常量，均不动）（`15_data_separation` §15.2/§15.4、`12_summon`、`21_elation`、AGENTS.md 结构节同步）

- 2026-10-12：**模板 import 机制 + 命途系统模块落地**（架构演进——阿哈时刻自引擎硬编码迁入数据层，行为逐比特不变）——① 模板新槽 `imports: ["<scope>/<name>"]`（角色模板顶层/build member 级，显式备用）+ **auto-import**：编译 team 时按成员有效命途去重，`data/sim_templates/system/paths/<path>.yaml` 存在即注入（不存在静默跳过——非欢愉队无阿哈与旧行为一致；encounter 级去重单实例）；② 系统模块 = 不挂在任何角色身上的模板片段，合并语义：单位声明并入 `CompiledEncounter.system_actors`（引擎按标记托管布场）、hooks 并入订阅池且**模块钩先于角色钩**（体系先于个体——发放/结算在角色钩之前的现序保持）、资源重名编译期炸（模块资源建议 `_` 前缀惯例）；③ 系统单位声明 schema 首发：语义标记集 `flags`（`untargetable` 不可被选目标 / `no_wipe` 不计全灭 / `no_aura` 不吃光环辐射 / `wave_reset_exempt` 波次重置豁免——词表唯一源 `sim_schema/actor.py`，词表外编译期炸）+ `speed_rule` 具名速度规则（`"aha"`——系数归 rulebook constants）+ `turn_handler` 具名回合结算原语（`"aha_turn"` = `engine._run_aha_turn`）；④ 阿哈迁移（首租 dogfood）：`data/sim_templates/system/paths/elation.yaml`（**声明归数据，有序结算序列留引擎原语**——「解控→共读池→编号序代放→授条目→清池→重算速度」无 DSL 原语可表达，引擎从"阿哈的主人"降级为"提供原语的运行时"）——`_init_aha`/`_init_aha_grants` 退役：单位创建改模块声明驱动、进战发放（每欢愉角色 +1 笑点 / +20 好活当赏）改模块钩挂新事件 `before_battle_start`（进战系统发放窗口：初始能量事件之后、on_battle_start 之前——04 §4.8 登记），发放数值经新编译期宏 `const(<name>)` 读 rulebook constants（体系常量单源，模板引用而非镜像——与 `param()` 同通道，05 §5.1 / 22 §22.5 同步）；actor_type "aha" 的调度/排除语义改读声明标记（不再按类型名硬编码）（`00_overview` 数据流章 / `21_elation` §21.4 / `05_effects` §5.1 / `22_syntax_reference` §22.5 / `04_modifier` §4.8 / `15_data_separation` §15.4 同步）

- 2026-10-12（二批）：**打标对拍（oracle_report）装备载体扩名册**——装备版对拍报告（2026-09-24 落地：借载体角色穿装备逐核心行动与 hsr-optimizer 比值，报告型闸异常不打回）的光锥命途覆盖从三命途扩到**八命途**：新增毁灭=白厄、存护=砂金、丰饶=罗刹、记忆=遐蝶、欢愉=火花五载体（钉死值照对拍战役各批先例逐键抄录，见 `src/hsr_nous/ops/annotator/oracle_report.py` `_EQUIP_CARRIERS`）；配套修正两处场景生成器病灶——① 同 action_type 多行动块改取**首个（基底版）**（强化版后出：白厄 140808/火花 150110/遐蝶 140709，旧末位覆盖会拿 2.5× 强化普攻打对方常态 1.0×）；② 载体行迹 flat 暴击/暴伤与元素增伤桶补钉对方面板（fixture `trace_stat_effects` crit_rate/crit_dmg/dmg_<元素> 与 `base_stats.dmg_bonus` 两态——火花 crit 0.12/0.133、砂金/遐蝶元素 0.144，漏钉=期望暴击/增伤区两侧差）。金样五件（defaults 异常检出+中性钉归零双跑）：23044×白厄（烈阳 60% 恒开 ×1.6）、23023×砂金（供盾暴伤+易伤复合 ×1.176）、23032×罗刹（忘忧窗口 ×1.10）、23042×遐蝶（诗行易伤 ×1.18）、24006×火花（defaults 空开直接 0 异常）。挂账两族：同谐专光（buff 落队友——需 teammates 镜像链+多成员队我方侧通道）、位面阈值件（306/309/311 族 CR/SPD 档——需双侧终值面板注入通道；两族通道 driver 侧均已备（batch5 先例），oracle 自动场景侧未接，误报零风险（无载体 pass-through/阈值两侧同灭=比值 1 无信息）

- 2026-10-11（三批）：**欢愉体系引擎/DSL 通道五件 + 到期事件一件**——① hook 欢愉段削韧开闸（火花天赋附伤官方 stance 数据与米游社双源证实削韧 5，原「口径待实测」的 category elation × toughness_dmg 编译互斥退役，与直伤同走 `_apply_toughness_damage` 单漏斗：own_element 默认闸/多段各削/击破与超击破判定同口径）；② `aha_instant` effect 增 `amount` 结算档槽（必填、表达式现场求值、缺槽编译期炸——引擎零游戏数值，原固定 20 字面量退役；爻光终结技档 20、一星魂经闩表达式 40）；③ 新增宿主函数 `elation_of(actor_id)`（读指定角色有效面板欢愉度）+ 欢愉伤害 `elation` 覆写槽（rulebook `elation_multi` 输入 override_param 承接）——爻光天赋【大吉大利】「攻击者欢愉度低于爻光时用爻光的算」择优落地（`max(elation_of($event.actor), $self.elation)`）；⑤ merrymake/final_dmg_boost 两键开通行动域隔离（官方「强化普攻期间」族）：乘区 scoped 命中域通道（hit_condition/hit_stat_exprs 件按命中计入、面板不读）+ elation 路由事件新字段 `decl_action_type`（行动声明类别流入——本路由 `action_type` 仍喂路由 id `elation_damage` 供承伤 scoped 判定），银狼LV.999 六星魂增笑与强化普攻增伤档两件改命中域件（本体「basic」声明段才命中，追加/盲盒/欢愉技出集——旧常驻近似域偏差核销）；⑥ `res_punchline` 覆写域读取点拦截下沉 `engine._resource_value` 单点（固定笑点档覆写域内凡读池处同锚——复合表达式/resource_of/钩条件同读锚定值，无覆写域逐比特不变；hook 侧字面值特判退役）；⑦ 好活当赏到期口径定案（实测裁定：**到期仅消失、不转化笑点**——mechanics 08 §8.4 结案）+ 条目到期逐条目发射 `on_banger_expire`（载荷 actor/条目值/除名后合并值，23 章 §23.4 登记）——绯英行迹「开不败」（队友好活当赏结束 50% 转化）与二星魂加倍落地（`05_effects` aha_instant/category/toughness_dmg/punchline_source/elation 行、`04_modifier` 命中域节、`21_elation` §21.2/§21.4/§21.5、`22_syntax_reference` §22.4、`23_event_hook_system` §23.4、mechanics 08 §8.4 同步）

- 2026-10-11（二批）：**进战发放事件化**（owner 忘却之庭实测终审——50% 初始能量、E1 绯英、回能效率 140.2%：开局能量 313/好活 298、狐狸老师与欢愉技开局即触发）——进战初始能量（initial_energy_ratio 布能）、每欢愉角色 +1 笑点、进战 20 好活当赏三笔皆裁定为**「获得」语义**，触发获得联动（绯英天赋①②③/银狼LV.999 笑点→Hidden MMR/火花 E1 抗穿光环开局引燃）。引擎：ActorState 创建 0 起账、hook 订阅后按序补发（初始能量事件 `_grant_energy` source/reason=`"initial_energy"`、err_exempt=True——50% 布能不吃 ERR → 阿哈进战两笔发放 → on_battle_start）；开局级联就地结算不设延后队列。旧「初始能量布场非事件」翻案（`23_event_hook_system` §23.4 / `05_effects` 回能节 / `21_elation` §21.4 / mechanics 08 §8.1 同步）

- 2026-10-11：易伤乘区修正为**单一池**（fandom/Prydwen/hsr-optimizer 三源一致：DMG Taken = 1 + 全部易伤池内加算）；删除推测预留的独立易伤乘区（从未有实例赋值）。02/01/rulebook 同步。同批：多 random() 区取值顺序显式冻结为公式 **AST 求值序**（rulebook `formula_idents` 绑定期预解析；随机流消耗序逐比特钉死，01 顶部注 + rulebook 卷头 + tests/test_rulebook.py 回归）

- 2026-08-25：核心公式速查去双份——公式表达式改指路 rulebook.yaml（可执行唯一来源）/01_formula.md（文档镜像）/mechanics 02–04（防腐，lint 镜像闸同步收缩）；待确认事项核销（真实伤害条已确认移除，余两条保留）

- 2026-07-22（四批，审计 R4/R5/R6/R7 工作表落地）：`grant_extra_turn` 原语落地（05_effects 新增"授予额外回合"节：insert=第 2 层 FIFO 不耗 buff 不受推条、after_action=视同普通回合；09_faq 再现示例改用原语）；欢愉增伤区独立成池 `elationDmgBoostMulti`（02 定义/公式/生效表/乘区表、08 公式、01 表达式+参数+矩阵、21 表达式+参数，当前无实例预留槽）；击破效果框架补 `× 韧性减伤`（裂伤等 2 回合 DOT 第二跳正确吃 0.9）、回滚击破增伤（fandom piecewise "if Break DMG; 1 otherwise"——击破 DOT/附加伤害不吃）；`override` 字段落地（04 §4.2：最终面板覆写如万敌血仇 DEF=0，冲突即错+互斥即错，13 validator 两条检查）；02 生效表与 2.12 表多轮补全（DOT 行"2.1 常规乘区（除双暴）+ ehrMulti"、独立增伤/超击破增伤/最终伤害/韧性减伤行、表下待实测与外推标注）；DOT 公式删除跳数系数、卡芙卡类引爆注改"引爆技能给定的固定百分比"；真实伤害补"来源间加算稀释、被护盾抵挡"（紫喵 11 置顶）；角色附加伤害 vs 击破附加伤害限定词全局统一（02/04/11/01）；§7.7.3 "属性→增伤也纳入转化标签"明示、§7.7.4 知更鸟行注实测来源、§7.7.4 范围限定为"百分比+固定点数"、§7.7.6 链式例子补阮•梅；ability 命名全库统一 `ability_multiplier`（01 表达式+参数+矩阵、09、15、02 驼峰）；merge_to_matrix.py 清理 17 处同键冲突+注册 drain_hp/grant_extra_turn 家族；01 §1.4 裂伤 min 显式注（min 整体替代 level_base×effect_multiplier）；01 矩阵补"击破列≠击破效果"注；小伊卡三处 hook 统一 drain 模型；23:208 风堇 M2 rank id 注；03:133/147 "视同普通回合"限定到 buff 维度
- 2026-07-21（三批，审计 R3 工作表 47 项落地）：欢愉伤害公式补 `finalDmgMulti`（02/01/矩阵/生效表；§2.7 术语对照注：角色文本="为原伤害的 X%"、fandom=Original DMG Multiplier、模式 buff="最终伤害提高"，同属推断已标注）；普攻扩散削韧修正（基线 20/10 刃、饮月特例 30/10·40/20，04/01/22 三处）；卡芙卡类引爆注改"引爆技能给定的固定百分比"；04 削韧表表头改"邻/主/邻"并补弹射列、超击破补大丽花例外；§4.8 删除 7 行与总线重复的事件糖（能量阈值/死亡/HP 变化/受击/护盾/资源持有），`on_dot_retrigger` 补入 §23.4；函数白名单统一（§22.10 为唯一事实来源，effect 层补 sum/lookup_table/zone_owner、chance/in_zone 限 condition）；秘技 effects 队列模型落地（20.2 `battle_start_effects` 字段 + 20.4 流程）；小伊卡示例统一 drain 模型（22.11/23.9 对齐 07）；受击事件统一 `before_take_damage`/`after_being_hit`；生效表补韧性减伤/原始欢愉伤害倍率/独立增伤独立易伤不生效列；风化 5 层+精英首领；残梅绽补 30% 系数与不可重复附加；治疗"受治疗量可为负"（萨姆领域）；22.11/07 示例变量绑定修正；白厄 TP+3 出处统一为秘技「终结之始」；01_base_stats/06 节号重排；索引补 00_game_basics；异相仲裁 Anomaly Arbitration；validator/17/18/20/21 等一批字段级修正
- 2026-07-21（二批，审计 R2 工作表 30 项裁决落地）：**超击破三池拆分**——超击破公式改 `× 超击破转换倍率 × 击破增伤区 × 超击破增伤区`（三池各自池内加算、池间乘算；米游社 67198368 实测 + fandom + optimizer 一致），击破公式补 `× 击破增伤区`，SUPER_BREAK_MODIFIER 注释纠正为转换倍率；裂伤 cap 改写为 `2×韧性系数(0.5+最大韧性/40)` 并注基数层比较有实测（米游社 58632087）；通用 DOT 公式删除跳数系数（卡芙卡类手动引爆按比例单独结算）；03 行动序轮次定义与示例按全局时间轴重写、插入行动改三层 FIFO 模型（追加行动 > 额外回合含终结技同层 FIFO > 普通回合）；04 冻结/残梅绽（真跳过+锁韧性恢复）与纠缠/禁锢（仅延后）分流；`drain_hp` 改触发 `on_hp_decrease`（reason='drain'）；01 断点表 6 格重算；07 星期日 E6 散文与连续标签修正；`04_modifier`/`23_event_hook_system` 按合并口径扫清"保持分离 TBD"残留并去重事件定义；刃地狱变（战技 120502、嘲讽 +1000% scaling）、validator 等级/modifier_type、秘技强制进战与扣 TP、遗器副词条三档、异相仲裁 `anomaly_arbitration` 等 schema 修正
- 2026-07-21：击破系公式回滚虚弱乘区——击破伤害/超击破伤害/击破效果伤害/纠缠均**不受虚弱影响**（fandom `Weaken`、`Toughness` 两页 + hsr-optimizer 实现 + 紫喵Azunya 入坑指南 07 四方一致）；常规 DOT 仍受虚弱影响（紫喵入坑指南 10）；`02_damage_formula.md` 生效表/DOT 乘区表同步，`01_formula.md`、`15_data_separation.md` 公式同步删除 `weaken_multi`
- 2026-06-15：大量补充
  - 新建 `00_game_basics.md`：命途/属性/光锥/遗器/养成/基础属性总览
  - 新建 `12_technique_system.md`：秘技系统（TP 秘技点、分类、战前策略），基于 [Fandom - Technique](https://honkai-star-rail.fandom.com/wiki/Technique)
  - `06_skill_points.md`：新增 §6.5（当时节号，现为 §6.3）战技点（SP）vs 秘技点（TP）对比
  - `07_buff_system.md`：新增 §7.7 属性二次转化（基本部分/额外部分模型 + 4 维度 + 全角色盘点表 + 知更鸟/玲可固定值特殊处理），基于 [B 站 · 夜殇黑羽《论属性的二次转化》](https://www.bilibili.com/opus/1176311260863528979)
  - `10_taunt_system.md`：全面重写（公式 `嘲讽值 = 基础 × (1 + Σ 百分比加成)` + 全角色技能/光锥加成清单 + 彦卿特殊修改 Base），基于 [Fandom - Taunt](https://honkai-star-rail.fandom.com/wiki/Aggro)
  - `11_special_mechanics.md`：新增 §11.3 HP 变化事件 vs 伤害事件区分；§11.4 结界 (Zone)；§11.5 境界 (Territory)；§11.6 连携攻击 (Joint ATK)
  - 更新 `docs/README.md` 和 `game_rules.md` 索引
- 2026-05-16：新增 elation_system.md 欢愉命途机制；damage_formula.md 新增 2.14 欢愉伤害；术语统一（笑点乘区 `humorMulti` → `punchlineMulti`，与官方英文对齐：Elation/Punchline/Certified Banger/Aha Instant）；伤害类型表格补充真实伤害与欢愉伤害
- 2026-05-16：修复章节编号与 game_rules.md 索引对齐（elation 8.x、follow_up_attacks 9.x、taunt 10.x、special 11.x）
- 2026-05-16：补充 skill_points.md 战技点特殊机制（上限可提升、战技不耗点/多耗点、普攻不回复、终结技回复等）
- 2026-05-16：确认真实伤害完全不受任何常规乘区影响（包括减伤、虚弱、易伤、防御、抗性、增伤、暴伤等）
- 2026-05-16：批量修复文档矛盾（game_rules.md 速查公式删除残留 `trueDmgMulti`；待确认事项更新；修改记录修正抗性上下限描述和 `superBreakModMulti` 描述；break_system.md 补充量子/虚数击破独立推条比例；damage_formula.md 暴击表格改用 effectiveCR/effectiveCD、DOT 公式区分角色/击破 DOT、效果命中公式统一加入 EFFECT_RES_PEN、防御等价形式条件修正；energy_system.md 明确能量恢复效率面板为总倍率；buff_system.md 效果命中公式加入 EFFECT_RES_PEN）
- 2026-05-16：damage_formula.md 修复（删除击破伤害公式中多余的 `增伤(dmgBoostMulti)`；精简 `击破特攻(击破特攻(BE))`、`等级基数(等级基数(levelBase))`、`效果倍率(效果倍率(effectMultiplier))` 等重复嵌套命名）
- 2026-05-16：修正 base_stats.md 中打击方式示例角色（单体/扩散/弹射）
- 2026-05-16：公式变量名统一为中文+英文格式（如 `防御(defMulti)`）；补充参考来源（紫喵Azunya 入坑指南系列）
- 2026-05-16：超击破公式修正（删除 `dmgBoostMulti`；削韧效率拆为两个乘算乘区；`superBreakModMulti` 修正为 `1 + SUPER_BREAK_MODIFIER + extraSuperBreakModifier`）；添加双击破机制；击破/超击破/DOT 删除 `trueDmgMulti`；主公式删除 `trueDmgMulti`；添加 `weakenMulti` 和 `dmgRedMulti`；普攻削韧值修正为 10；速度公式修正为百分比加成；能量恢复效率基础值修正为 100%；效果命中公式加 `min(1, ...)` 上限
- 2026-05-15：拆分为 `mechanics/` 目录下的独立文档，`game_rules.md` 改为总纲
- 2026-05-15：新增 1.4 记忆命途与忆灵、2.8 真实伤害、2.2 防御乘区收益特性
- 2026-05-15：新增独立增伤区、独立易伤区；修正抗性上限为 90%、下限为 -100%
