# 参考实现研究笔记

> `external/` 是本地只读研究克隆（gitignored，见"重新克隆"节）。本文沉淀各参考项目的关键结论及其对本项目设计决策的影响。

## gcsim（原神模拟器）

- 仓库：<https://github.com/genshinsim/gcsim> → `external/gcsim/`
- **架构**：核极简、边粗糙——约 155 行单事件总线支撑全角色（100+）；帧级连续时间轴；角色机制全部以"挂事件边"的方式实现，核心引擎不为单个角色写特判
- **对本项目的影响**："modifier trigger 与 event hook 合并为统一事件总线"决策的直接证据——同构架构已被验证可覆盖全角色；"简单核心 + 组合边缘"是可行的覆盖策略
- **输入/输出**：gcsl 配置语言（队伍 + 装备 + 动作序列 + 敌人/目标）→ 逐帧战斗日志 + DPS 统计；在线版 simpact.app
- **与我们的差异**：原神是实时动作（帧/碰撞/取消后摇都影响伤害），必须连续建模；崩铁回合制是离散事件序列，我们的 AV/行动序模型天然更简

## hsr-optimizer（崩铁配装器）

- 仓库：<https://github.com/fribbels/hsr-optimizer> → `external/hsr-optimizer/`
- **价值**：伤害公式侧的社区参考实现（`damageCalculator.ts`），一致性审计 L1 层的三方佐证来源之一
- **关键结论**（均已并入规则文档）：
  - 击破/超击破公式**不含**虚弱乘区（促成我方文档的虚弱回滚）
  - 超击破为单一加算池（与 fandom wiki 的双乘区表述冲突时，以实现为背书）
  - `tickCoefficient` 是手动引爆 DOT 的比例结算参数（卡芙卡类），非通用乘区——防止误入通用公式
  - 固定削韧在乘区后加算（与 wiki 公式表述不同，以实测/实现为准）
- **局限**：拉表计算，不建模回能/拉条/行动序等实战动态——这正是本项目 sim 的差异化定位

## 其他调研记录

- ~~**崩铁无 gcsim 类模拟器**~~（修正 2026-08-22）：已有先例但均浅/早/停（见下方新增条目）；本项目的差异化 = 唯一同时举"1:1 逐位"与"LLM 可写"两面旗
- **StarBench**（[arXiv:2510.18483](https://arxiv.org/abs/2510.18483)，AAMAS'26）：基于崩铁真实客户端的 AI agent benchmark——从截图直接输出键鼠低级动作（direct control）或借检测器/OCR 辅助（tool-assisted），外加 ask-or-act 信息检索诊断，共八个战斗任务。它不是模拟器（用真实客户端而非重建战斗规则）。**实测结论**：① DC（纯截图→像素点击）2024 代 VLM 全灭（0% 胜率），端到端像素接地目前是死路；② TA（YOLO+OCR 文本化状态+高层动作三元组）GPT-4o-mini 追平人类——验证了 `screen/`（检测+状态解析）+ `pilot/`（高层动作接口）的技术路线；③ OCR 消融显示**文本化状态（HP%/战技点/大招就绪）是决策质量载体**，检测框其次——screen/ 资源先投状态解析；④ 其 Limitations 计划做回放模拟器解决真机不可复现，我们的 sim 天然就是这个确定性评测环境。可作将来屏幕层的参照基准
- **永动机类轴**：社区系实战测出而非拉表算出，说明"回能/拉条全循环建模"是拉表工具的天花板，也是 sim 必须覆盖策略层的原因（见 `sim_schema/docs/14_policy.md`）

## 崩铁同赛道模拟器（2026-08-22 补）

> 协议红线统一原则：**列出/引用/读思想永远合法；搬代码按 license 分级**——GPLv3 我们 MIT 碰不得（传染），无 license 默认保留所有权利（最严格，一行不搬），MIT 可借鉴但保留 attribution。

### SRSim（ZSim-Dev，崩铁模拟器先例）

- 仓库：<https://github.com/ZSim-Dev/SRSim> → `external/SRSim/`；**GPLv3——只读思路，一行不搬**
- **定位**：跑通最小战斗循环（2026-04-25 停更，源码数千行 Python，引擎核为其中子集）；机制 Python 硬编码、事件纯枚举无改写权（符玄分摊类只能硬编码——我方 waterfall 契约必要性的反例实证）
- **金矿**：`docs/battle-system-mechanics/` 23 章机制报告（A/B/C 可信度分层，与 docs/mechanics 方法论同款）——**第二个独立事实底座，逐节对拍的冲突点=待实测清单**（全 23 章对拍完成）

### ZSim（ZSim-Dev，绝区零模拟器）

- 仓库：<https://github.com/ZSim-Dev/ZSim> → `external/ZSim/`；**GPLv3——同上**
- **定位**：775★ 活跃，Hoyoverse 模拟器做到成熟的形态参照（模块边界/electron-app 用户入口/更新节奏）；其 ZZZ 侧困境（弹刀闪避交互不可丢弃、敌人节奏数据不可得）反证崩铁"交互可枚举"的选型优势

### FateSky12/hsr-sim（校准纪律建制派）

- 仓库：<https://github.com/FateSky12/hsr-sim> → `external/hsr-sim/`；**MIT——可读可借鉴，attribution 保留**
- **定位**：AI 重度辅助的爆发产物（2026-08-18 创建）；纯函数 BattleKernel + Vite 网页/Worker 池产品形态（README：95 角色可选）；有校准框架未对真（自我声明"内部黄金≠客户端校准"）
- **金矿**：其 `docs/calibration.md`（hsr-sim 仓库内）——**L0 面板 / L1 单跳 / L2 行动序三级校准** + JSON 固件 CI 门禁格式（expected/observed/容差）——**我方验收体系（+自补"机制状态机"第四级）与待实测产出物形态的现成参照**；其内置 4.4 击破表 Lv80=3767.5535 与我方锚点 3767.5533 第四位小数冲突（已登记待实测）
- **引擎级对拍（2026-08-22）**：抓到其公式级 bug 一批（RES_PEN 对弱点短路/护盾串行吸收/ERR 一刀切/终结技插队副作用/纠缠无伤害）——反证我方位置；值得借鉴：纯函数内核（回放/分支搜索/hash 对账）、版本化校准缝（常数全注入）、DoT 快照模型、SHIELD_ABSORBED 等发射点候选

### hessiser/veritas（游戏内记录仪，golden case 工厂）

- 仓库：<https://github.com/hessiser/veritas> → `external/veritas/`；**MIT——同上**
- **定位**：IL2CPP 注入级记录仪（钩 `RPG_GameCore_TurnBasedGameMode` 读真实内部状态：真实 AV/逐跳伤害/StatChange/事件流），socket+CSV 导出
- **对我们的三重价值**：① 待实测项的机器化采集（注入式工具的 ToS 风险评估见 `autopilot_safety.md`）② 真实事件流 = 我方发射点对账表的第一个 ground truth ③ 敌人行为分布数据源（两家模拟器都缺的地基）
- **侦察归档（2026-08-22）**：**Windows only**（需 Windows 环境运行）+ 钉游戏版本（混淆名硬编码，版本一换可能全断）；能采逐跳伤害（仅我方）/真实内部 AV（双方）/CurrentHP/敌人等级——待实测项约一半直接可采；**盲区：能量/韧性/SP/buff 全无事件**（ON_STAT_CHANGE 是死代码，fork 接 `SetProperty` 一步解锁最大面）

### LoranAndos/Honkai-Star-Rail-Combat-Simulator（覆盖最广研磨派）

- 仓库：<https://github.com/LoranAndos/Honkai-Star-Rail-Combat-Simulator> → `external/loranandos-hsr-sim/`（2026-08-22 已克隆，活跃至 2026-08-19）；**无 LICENSE——默认保留所有权利，只读语义，一行不搬**
- **定位**：覆盖最广的研磨派——15.7k 行 Python、**34 角色（36 文件）+ 80 光锥 + 31 遗器/位面**（9 命途子目录，Fate 联动齐）；击破常数与我互证（3767.5533 / ÷40）；价值=**角色 kit Turn 四元组（倍率/削韧/回能/SP）+ E3/E5 两档倍率的语义语料**——已发现个体 bug（Saber 秘技符号写反），数值一律回查官方

> **核实注记（2026-08-22）**：本节初稿据外部调研文本录入，复核后修正三处——SRSim 行数口径（"~1300 行"→源码数千行全量）、hsr-sim 校准分级（"L0-L3 四级"→**calibration.md 实为 L0-L2 三级**，"机制状态机"是我方自补的第四级）、LoranAndos 条目（repo 名/角色数/命途数均按 GitHub 实测改正）。此核查过程本身即 AGENTS.md"外部输入核查三关"的实例。

## 理论参照

## Algebraic World Model（AWM，arXiv:2610.40503）

- 论文：*Algebraic World Model: From Exploration to Proofs*（Guancheng Pan、Qixin Tan、Yang Yuan、Andrew Chi-Chih Yao，v2），[arXiv:2610.40503](https://arxiv.org/abs/2610.40503)，[项目页与模型/证明](https://ephemeral6.github.io/awm-site/)，[GitHub 仓库与逐游戏归档](https://github.com/Ephemeral6/awm-site) → `external/awm-site/`；PDF → `external/awm/2610.40503.pdf`。仓库主要公开网站、逐游戏 Lean 专案和实验产物，不是可直接导入的通用 AWM 库，且未声明 LICENSE，只读方法不搬代码
- **三段链路**：Explore & Prototype 把环境交互写成可执行 Python 假设并用观测持续复核；Structure & Simplify 抽取 typed objects/shared rules，以范畴论极限引导分解、组合、泛化和特化；Formalize & Prove 在 Lean 4 中重放轨迹，并对全部合法行动序列证明可达或不可达（§2）
- **与本项目同向且可直接借鉴的纪律**：
  - 假设的 checker 一旦与观测冲突，必须先修正或撤回，不能带着 FALSE/ERR 继续探索——对应我们 rejected/inconclusive 不得靠换 seed、改口径或删失败样本强行通过
  - 泛化/压缩不能只追求更短：变换必须保持已记录转移的判定，并用扰动反例确保原有拒绝不丢失（§2.3）——这是我方「压缩优先」与「共享源必验」的同类约束；golden case、失败保留和反例集应成为机制合并的硬闸
  - typed objects、命名规则、轨迹重放与证明依赖让错误可以沿结论反向定位到具体规则（§4.3）——对应 worldline artifact、只读 lineage 和证据下钻；后续展示 claim/证明依赖时，应优先服务反例定位，而不是只展示结论
- **对全局 Memory / EEG 的直接启示**：
  - **概念书 ↔ 结构化 Memory**：保存的是机制的适用范围、支持观测、checker 和证据引用，而不是自然语言聊天摘要；冲突知识应经 rejected/stale/supersession 失效并保留历史，不能继续冒充最新事实
  - **分解/组合/泛化/特化 ↔ 全局知识合并与重构**：相似机制可以归纳成共享规则，特殊情况也可重新拆开，但合并后必须保留原观测判定和反例。EEG 本来允许共享证据、反事实分支与修订回边，不是单纯 DAG；AWM 为这种可检验的知识演化提供了同构参照
  - **证明依赖 ↔ claim 证据—推导图**：从结论可回溯依赖的规则、实验、版本与推导步骤；新证据推翻规则时，也能正向找出哪些旧结论需重算或标 stale。知识体系自身必须持续接受验证，不能只负责存储结果
- **落地时必须按结论类型分流**：资源非负、能量不足不能开大、速度阈值、固定轨迹可达/不可达等封闭性质，可借鉴 Lean 做形式验证；「辅助最好都带风套/翁瓦克」这类配装偏好则是条件化统计结论，必须绑定队伍、关卡、策略、指标和候选集，由 paired dev/holdout 证据支撑。全局 Memory 不得把这种经验偏好保存成无条件最优或普遍定理
- **不能混同的能力边界**：AWM 的不可达结论是在学习模型的显式前提下，经 Lean kernel 对全部合法序列成立的形式证明；转移到真实环境还需 sufficient cover 等条件（§2.4、§4.4）。我方 paired-v1 是固定协议下的统计比较，worldline-v1 是单条轨迹证据，当前可信内核是重算/完整性校验而非 Lean 形式证明——单条回放成功或若干 seed 未胜均不能升级为全局不可达证明。全局 Memory 目前仍是目标设计，规划保存的是统计与模拟证据，不是全局形式证明
- **共同校准问题**：论文同样把「模型内证明正确」与「模型是否覆盖真实环境」分开，交互核验负责后者（§6）。这与我方区分确定性重放和真实游戏校准一致；AWM 可借鉴之处是进一步显式记录结论依赖哪些规则与前提，而不是把 accepted 当作现实真值

## Hyra 2.0（从解题到造工具）

- 官方发布：[Hyra 2.0 研究页](https://hy.tencent.com/research/hyra2) / [微信推送](https://mp.weixin.qq.com/s/WnIFZYIRLdk7tw7cJIVpJA)；[Hyra 1.0 架构说明](https://www.tencentcloud.com/techpedia/144774?lang=en)；成果仓库：[Tencent-Hunyuan/hyra-results](https://github.com/Tencent-Hunyuan/hyra-results) → `external/hyra-results/`（Apache-2.0，含模型、报告、验证工具和复现脚本，不是通用 harness 源码）
- **可继续核对的公开资料**：[Petty 五维等距点论文（HyProver 生成 + 人类核验改写）](https://arxiv.org/abs/2610.39967)、[HyInv 技术报告](https://github.com/Tencent-Hunyuan/Hyra-results/blob/main/AI4Science/hyinv/HyInv_Technical_Report.pdf)、[HyPLM-Flash 技术报告](https://github.com/Tencent-Hunyuan/Hyra-results/blob/main/AI4Science/hyplm_flash/HyPLM_Technical_Report.pdf)、[HyFF 技术报告](https://github.com/Tencent-Hunyuan/Hyra-results/blob/main/AI4Science/hyff/paper/HyFF_Technical_Report.pdf)、[Yau 圆周作用猜想结果](https://github.com/Tencent-Hunyuan/Hyra-results/blob/main/AI4Science/yau_circle_action_conjecture/yau_circle-action_conjecture.pdf)。Research Board、Books、Mission/Worker 暂无单独公开技术白皮书或 harness 实现可考
- **范式变化**：1.0 用轻量循环寻找更优答案；2.0 让 Agent 研发可复用的模型、工作流、验证工具和 skill，使一次研究投入能由后续任务反复受益——与 AWM 的形式模型证明不同，它主攻长期科研项目管理和工具复利
- **Harness 的关键件**：Overall 管目标/资源，Mission 长期负责研究问题，Worker 探索/实验/质疑；持久化队列与 Research Board 保存协作状态；独立 Review Worker 重新接触原始问题和证据，可要求缩小结论范围；高算力或影响共享知识的操作需人工审批
- **Books 与 skill 的分层**：Books 分「观察 / 已验证 / 约定」，记录做法、理由、适用条件和原始证据，新证据到来可修正；可迁移方法再整理为 skill。观察可供参考，独立复现后才成为可靠依据，影响团队行为的约定需人类确认
- **对本项目的映射**：Research Board ↔ Investigation/Execution 的结构化状态而非聊天历史；独立 Review ↔ 可信内核与宿主复核；Books ↔ 全局 Memory / EEG 的认识论分层和 stale/supersession；skill ↔ 把经验固化成 checker、验证流程、DSL 模板与自动化工具，而不只是保存一段自然语言总结
- **借鉴边界**：只在长任务调度、独立复核和工具复用出现真实需求时引入 Mission/Worker 分工，不照搬成角色扮演式多 Agent。AWM 提供 Lean 形式化参照，Hyra 2.0 提供知识分层与工具化参照；二者都不能替代确定性执行、固定协议统计和真实游戏校准

### Cordis（时空可组合性编程范式）

- 论文：*A Programming Paradigm for Spatiotemporal Composability*（Yifan Shi 等，北大 + DeepSeek），<https://github.com/cordiverse/paper>（88 页，PDF 在仓库 main）
- **思想一句话**：让组件像电池一样热插拔——装上即用、拔掉无痕。两根支柱：revertible effect（副作用登记逆操作、移除即回滚）与 reactive coeffect（组件声明"我读什么"，上下文变化按声明通知）
- **与本项目的映射**：
  - modifier 的 effect/coeffect 分野 = "改什么 / 读什么"（`reads_converted_values` 即 coeffect 声明）
  - **阶段化求值（读基本→标准转化→链式转化）= 空间组合性（依赖拓扑排序）的工程近似**：转化家族是封闭集，依赖 DAG 小到可一次性手排成固定三阶段。背书是双向的——方向（拓扑序求值）被证明正确，**失效条件也划出**：出现跨阶段回流的依赖边（标准转化读链式产出 / 互读成环）时固定阶段模型失效，需退到动态依赖解析
  - revertible effect → 引擎纪律：一切非面板副作用必须挂在可移除的登记项上（面板属性本身走重算模型，无需逆操作）
  - 事件可改性契约（emit 只读 / waterfall 逐层修改，Koishi 式公开约定）→ 事件表可加"可修改/只读"列 + lint 闸
- **不借鉴**：形式化演算（preservation/confluence 证明）与 Cordis 的 TS 热替换实现——运行时热拔插不是 sim 的问题，代码零可移植性

## 重新克隆

```bash
mkdir -p external && cd external
git clone --depth 1 git@github.com:genshinsim/gcsim.git
git clone --depth 1 git@github.com:fribbels/hsr-optimizer.git
mkdir -p starbench && curl -sL "https://arxiv.org/pdf/2510.18483" -o starbench/2510.18483.pdf
mkdir -p cordis && curl -sL "https://raw.githubusercontent.com/cordiverse/paper/main/paper.pdf" -o cordis/paper.pdf
mkdir -p awm && curl -sL "https://arxiv.org/pdf/2610.40503" -o awm/2610.40503.pdf
git clone --depth 1 git@github.com:Tencent-Hunyuan/hyra-results.git
```

StarBench 官方代码（检测 checkpoint、LightRAG checkpoint）论文承诺发布但截至本笔记写入时未放出，arxiv 页面无代码链接；放出后克隆至 `external/starbench/` 同级。
