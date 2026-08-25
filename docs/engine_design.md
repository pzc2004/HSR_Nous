# 引擎设计（翁法罗斯 / Amphoreus）

> 定稿 2026-08-21；2026-08-25 刷新至现行实现（距离制调度、rulebook 表达式驱动、模块落点与未实现清单）。
> 依据：`sim_schema/docs`（表达层正文档）、`docs/mechanics`（事实层正文档）、决策卡 #3–#20 + A1（追溯见落地注）。

## 00 总览：引擎 = 编译器 + 虚拟机

整个引擎按"写一门解释器"的形状分层：

```
YAML 输入 ──► [1] 前端 parse ──► [2] 绑定/编译（符号解析+AST 预编译+糖 desugar）
                                        │ 产物：不可变 CompiledEncounter
                                        ▼
                        [6] 运行时 VM ◄── [3] 调度核心（距离制：守恒剩余距离+回合四段）
                        │   ▲
                        │   └── [4] 事件总线（发射点/waterfall-emit 契约/modify_event）
                        ▼
                [5] 结算管线（两层求值 → effect 原语 → rulebook 公式表达式+节点值树）
                        ▼
                [7] 策略接口（legal_action_set → policy 决策点）──► 循环回 [3]
```

**三条全局不变量**（凌驾于所有模块）：

1. **纯净不变量**：同一配置 **+ 同一种子**连跑两局，终局状态逐字段全等。实现手段——全状态可序列化（调度树数组化、modifier 实例结构化）；**随机性种子化**（单一随机流、抽取点文档化、抽取顺序确定——种子是配置的一部分，不是干扰项）；每局从 CompiledEncounter 完整重建（绝不在上局战场增量修改）。**不禁止随机**——方差研究（N 种子→分布）是核心目标；期望值模式（不掷骰）只是对拍校准工具，非本不变量的实现手段。
2. **白名单求值**：一切 LLM/模板表达式只过 ast 白名单求值器（`expression.py`）。验收标准：白名单节点/函数单测全覆盖；非法输入拒绝（注入攻击回归）；模板绑定时预编译 AST，热循环只带 context 求值；纯函数输出"值 + 节点值树"；LLM 生成表达式的回归测试集。
3. **可改性契约**：事件表每个事件声明 waterfall/emit；emit 事件禁止 modify_event，validator 静态拦截。

**VM 指令集边界**（概念预算审计，98 概念）：VM = **求值器内核**（两层模型 / `hit_condition` 命中域 / `$modifier.source`）+ **modifier 生命周期五件**（apply / remove / duration / stack_mode / adjust_duration）+ **调度器** + **事件总线** + **三个账本**（伤害 / 资源 / 时长）+ **actor 生命周期**（summon / dismiss）。**其余一切皆是糖的展开目标**——形态机（§17，标记 modifier）、zone（§19，界外伪 actor）、计数器宏族、攻击窗等 33 个纯糖在编译期展开完毕，VM 零概念。

**当前进度**：直伤闭环 + 击破（削韧闸→击破伤害→属性击破效果→韧性恢复）+ 敌人行动 + 波次切换 + 能量/终结技插入 + 护盾/生存（锁血•月茧•复活）+ 光环 + 轮次统计 + 模板 hooks + StateConfig 形态机（白厄变身全链 e2e）已落地；掷骰/期望双模式与多局分布统计在册。未实现项见末节清单。

## 01 编译前端（parse）

- YAML → schema 对象（pydantic v2 模型，现状 dataclasses 迁移中）
- 编译期校验闸：未知键拒绝 / 枚举校验 / effect_type 白名单 / 表达式预编译（现役闸门见 `13_validator.md` §13.1-13.2）
- 落点 `sim/compile/`（`build_compiler.py` / `stage_compiler.py`）

## 02 绑定与编译（bind & compile）

产出**不可变的 CompiledEncounter**——一切运行时从它重建（纯净不变量的前提）。

- **符号解析**：modifier_id / resource_id / character_ref / 具名引用 → 内部整数句柄（运行时用整数不用字符串，可序列化）
- **AST 预编译**：模板绑定期间把所有表达式（amount/condition/hit_condition…）预编译为白名单 AST；热循环只带 context 求值（纯函数输出"值+节点值树"）
- **糖 desugar**：`trigger_limit`（§4.12）在此展开为 custom_resources 计数器三联件（资源声明+重置 hook+消耗门控）——引擎其余部分**永远看不到糖**
- **desugar 性能三级退路**（owner 定调 2026-08-21）：常数开销按"先测量、再优化"处理——① 最简展开先行，golden case 阶段实测 sim 吞吐（局/秒）再定是否需要优化（不为没测过的常数改设计）；② 真热则展开器内建优化：同实体同事件 hook 合并、标记整数句柄直查（模板/文档零感知）；③ 终极方案：热糖"编译为原生快路径"——语义唯一事实源仍是展开组合，VM 原生实现**必须经 property test 证明与组合展开在随机操作序列下全等**（编译器强度削减：语义不动实现换快）
- **宏系统扩展点（远期候选）**：糖的一般化形态——**宏定义进数据**（通用宏 → 世界规则文件随数据版本化；角色专用宏 → 角色 YAML），现阶段只做展开器接口预留：宏体纯数据变换（禁计算）、展开深度上限+禁循环引用、**先展开后过同一 validator**、VM 只见原语。trigger_limit 届时改写成数据里的第一个宏（dogfood）。决策原则：闭合关键字集（VM 层）+ 开放命名空间（表面层）——表面随便长，核心永远闭合
- **静态展开**：银枝双档 `ult_threshold: [90,180]` 等静态结构在编译期解析为分支表

## 03 调度核心：距离制（守恒剩余距离）+ 回合四段

**数据模型**（KQM 通式 / mechanics 03；原"绝对时刻键"口径已换代为本模型）：

- 每个实体持有一份**目标路程 goal**（距离，守恒量）——这是主状态：拉条扣距离、推条加距离、行动后 += 10000
- 有序平衡树的排序键 = **预计时刻 = goal / spd**（派生读数，不是主状态）；取最左 = 下一动，全局时钟 `clock` 拨到该键时刻
- **拉条/推条** = 纯距离运算（`goal ∓= 10000×pct`，与速度无关；剩余距离 ≤ 0 时拉条无效——mechanics 03 钉死）
- **变速时 goal 纹丝不动**——只是派生键按新速度重算（主状态不随属性漂，稳固）
- **AV（行动值）** = `max(0, goal/spd − clock)`——前端读数，随速度即时变化
- **banish/冻结** = 标记跳过（键保留，pop 时略过）
- **行动条预览** = 树切片遍历（调试第一视图）
- **波次切换**：倒计时类回合不重置 AV（决策卡 #16），其余按 rules 重建

**实现**（`sim/scheduler.py` + `sim/avtree.py`）：

- 手写**数组化红黑树**：节点池 = 预分配 int 数组（索引非指针）——整树即一根 int 数组，snapshot/回放/逐字段比对免费（纯净不变量）
- 实体→节点索引映射：拉条改键 O(1) 定位
- 五条不变量 debug 自校验 + **property test**（随机操作序列 vs 参考 sorted list，对拍法）——rbtree 删除分支是经典翻车点，无此测试不交付
- 参照 CLRS 伪代码（公共学术知识）；不抄 Linux rbtree.c（GPL）

**回合四段状态机**（决策卡 #16 确立，mechanics 03 §3.6）：

```
回合开始(A 类结算) → 行动 → 行动后窗口(合法插入点：终结技/插入行动吃"本回合"效果) → 回合结束(B 类结算，推进)
```

- 额外回合两类型（决策卡 #16 + R10-R3 补注）：正常回合类（吃回合事件）/ **倒计时类**——**不向总线广播**回合事件（不走字/不衰减/不可订阅），但**自身回合点存在**（自己声明的效果在该点执行，如昔涟烧血）
- `end_current_turn`（决策卡 #16）：保留已发生、丢弃未行动；先 adjust_duration(+1) 再正常回合末结算（"锁 buff"数学原理）
- AV999 显示钳（待实测，暂按硬钳）

## 04 事件总线

契约与事件表的唯一事实来源是 `sim_schema/docs/23_event_hook_system.md`（发射点生成式对账表、waterfall/emit 分派、modify_event 白名单、归因抹除），本节不复述。要点只两条：

- **发射点生成式**（决策卡 #16）：引擎**每个状态变更操作强制自动发射**事实，事件清单降级为对账表；闸"引擎变更操作必须有对应发射"
- **可改性契约**即不变量 3：waterfall 事件经 hook 链逐级修改 payload 后引擎按 `$event` 当前值继续；emit 只读；事实字段（resource_id/damage_type/reason/bar_index）不改

落点：`sim/bus.py`（发射/分派/modify_event）+ `sim/hooks.py`（模板 hooks 订阅与执行）。

## 05 结算管线

- **两层属性求值**（§4.10）：Layer 1 base（白值+flat）→ Layer 2（转化/覆写，读 source Layer 1 防二次转化循环）；阶段化求值，链式转化读"求值时点前已完成部分"（待实测钉）
- **effect 原语执行**：闭合指令集（05_effects 清单）——每个原语一个执行器；执行中的一切状态变更走 [4] 发射
- **伤害公式全部走 rulebook**（决策卡 A1）：`sim_schema/rulebook.yaml` 是公式/乘区/常数/模式表的**可执行唯一来源**（文档镜像 `01_formula.md`，数值事实 mechanics 02——一致性由 lint 镜像闸保证）；引擎公式链零 Python 算术，绑定期白名单预编译、热循环带 context 求值。**节点值树输出**——每次结算输出"值 + 逐节点拆解树"，是 Evaluator 的显微镜，也是对拍的对齐粒度
- **随机模式**（owner 修正 2026-08-20）：掷骰是主力——N 种子 × N 条世界线 → 方差分布（核心研究目标）；随机性种子化，种子进配置。**期望值模式**（不掷骰，暴击按期望）降级为校准工具：仅用于 optimizer 对拍与无方差基准 golden case
- **削韧与击破**：toughness_scope 静态闸 + 决策卡 #18 modifier 动态闸；击破链（削韧→击破伤害→属性击破效果→敌方回合开始韧性恢复，冻结顺延）已落地

落点：`sim/pipeline.py`（结算）+ `sim/modifiers.py`（modifier 生命周期与护盾）。

## 06 自定义资源与形态机

- **资源三段式**（决策卡 #13）：`max` / `ult_threshold`（可多档）/ `activation_grant`；溢出 `overflow_mode: none|bank`（extend 已退役，R10-O4）。能量内建资源已落地（`sim/resources.py`）
- **终结技插入**：合法行动集内能量满即可插入，吃"本回合"效果（行动后窗口，决策卡 #16.4）
- **StateConfig 形态机**（§17，**决策卡 #20 糖化**）：表面语法不变；编译期展开为——形态 = 标记 modifier（`dispellable: false`）+ `singleton_group: "actor_state"`，replaces/locked = 合法性条件注入（has_modifier 合取），exit_conditions 映射计数器宏族。白厄变身全链（决策卡 #16 验收：火种→变身→锁 buff→end_current_turn→倒计时回合→最后一击均分→回场）e2e 在册
- **银行**（§16.12）与 **host/provenance**（§16.13）：spec 在册，引擎未落地（见末节清单）

## 07 策略接口

- **legal_action_set 生成**：当前状态下的合法行动（能量不满大招不在集里；形态标记条件过滤——决策卡 #20 糖化后 replaces/locked 的展开产物（has_modifier 合取）；资源门槛越权不进集——§3.8 assist 例）
- **决策点注入**：policy 在决策点接管（action_rules/target_rules + 可调参数，policy.py；timing_rules 未落地已退役）；内置**固定脚本 policy**（手写 rotation，golden case 用）与编译策略运行时
- 落点 `sim/policy_api.py`（`legal_action_set` / `ScriptedPolicy` / `CompiledPolicyRuntime`）
- 优化器/agent 后置——但接口形状已定死：**policy 只选不越权**，引擎保证任何 policy 无法产生非法状态

## 08 对拍与验收（三层）

1. **optimizer 公式层对拍**：静态伤害结算对 fribbels damageCalculator——同一 build/buff 快照/木桩参数，逐 hit 比对。校准锚点：击破 3767.5533 / 欢愉 7535.107 / cLevelConst 80
2. **游戏实测 golden case**（待实测清单）：白厄变身全链、AV999 等——owner 有空时做，回报注进文档
3. **自洽**：同配置连跑两局逐字段全等；property test（调度树、求值器）

v0.1 验收（单角色白板打木桩手算对轴 + 两局全等）已通过——golden case 在 `tests/test_engine_v01.py` 在册；optimizer 批量对拍按 BACKLOG B22 推进。

## 模块落点（sim/ 现行）

```
sim/
├── compile/      # [1][2] 前端+绑定编译 → CompiledEncounter（build/stage 编译器、AST 预编译、糖 desugar）
├── scheduler.py  # [3] 距离制调度：守恒剩余距离 + 回合四段 + 两型额外回合 + end_current_turn
├── avtree.py     # [3] 数组化红黑树 + property test
├── bus.py        # [4] 发射点 / waterfall-emit 分派 / modify_event
├── hooks.py      # [4] 模板 hooks 运行时（订阅 / 条件求值 / 效果执行）
├── pipeline.py   # [5] 两层求值 / effect 执行器 / rulebook 公式求值 / 节点值树
├── modifiers.py  # [5] modifier 生命周期 + 护盾吸收
├── resources.py  # [6] 能量三段式
├── state.py      # 全状态 dataclass（可序列化，纯净不变量）
├── policy_api.py # [7] legal_action_set / 决策点 / 固定脚本与编译策略运行时
├── montecarlo.py # 多局分布统计（roll 模式 N 局 → 伤害分布）
└── engine.py     # 主循环编织（hooks/modifiers/策略运行时已拆出，本类薄委托）
```

公式/乘区/常数/模式表不在引擎代码里——唯一来源是 `sim_schema/rulebook.yaml`（决策卡 A1，见下）。

## 引擎零数值常数（决策卡 A1，2026-08-22 owner 定）

**原则**：能用 B8 白名单表达式写出来的，全部进输入数据（rulebook / 模板）；引擎代码零数值常数、零版本常数、零数据常数。

- **rulebook（全局规则，sim_schema 第三类输入，与 build/stage 平行）**：承载全部游戏数值与公式表达式——10000 距离、0.9 未击破、RES 钳位、DEF 公式（`1 - def/(def + 200 + 10*lv)`）、击破基数表、属性击破倍率、周期 AV、回能数值、韧性系数 /40（**单位=显示点，全链路统一**，adapter 审计各数据源单位）。判据：凡有版本足迹或 B19 待实测足迹的数值，一律进这层——实测修正/版本更新只改数据，引擎不新发版。
- **引擎只剩两样**：① **语义**（控制流：事件流、waterfall/emit 契约、距离守恒调度、受击链步骤顺序）——这些不是常数，数据化它们=发明图灵完备语言（压缩原则明文拒绝）② **护栏**（工程保险丝：hook 递归熔断、浮点 ε——实现的常数，非游戏的常数）。
- **判错线**：一个常数变了需要改引擎代码并发版 = 放错地方。
- 先例证据：GCC 目标机常数全部在 `.md` 机器描述数据文件，硬编的只有 C 语言语义；hsr-sim 校准缝（BattleKernelOptions 全注入）同构。
- schema 落点：`02_globals.md` 雏形已扩为完整 rulebook；数值事实的单一来源仍是 `docs/mechanics/`（schema 不复制数值）。

## 当前未实现清单（以 designs/BACKLOG.md 为准）

- **超击破结算路径**：`super_break_damage` 表达式在簿（rulebook / 01_formula），引擎零结算路径（B27 在案）
- **dot 快照口径**：tick 时哪些量吃快照未建模（B19 待实测；现为 v0.2 简化零乘区口径）
- **Aha 窗口**：阿哈时刻一等状态化（爻光 150% 窗口、插队派发）未落地（B9 真缺口）
- **续段执行**：全灭后续打多段的检查点/可恢复模型（§17.8 操控序列 spec 在册；B9 真缺口最大项）
- **虚韧性多条模型**：`add_toughness_bar` / toughness_bars 按序扣除（03 §3.10 spec 在册），引擎未落地
- **资源银行 / host provenance**（§16.12 / §16.13）：spec 在册，引擎未落地

明文非目标不变：大世界一切（R10-R2 裁决）、模拟宇宙（决策卡 #16/#18 缓议）、连携/助战/代放（B9 真缺口在案）、GPU、屏幕/pilot 层联动。
