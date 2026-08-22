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
- **定位**：引擎核 ~1300 行跑通最小战斗循环，2026-04-25 停更；机制 Python 硬编码、事件纯枚举无改写权（符玄分摊类只能硬编码——我方 waterfall 契约必要性的反例实证）
- **金矿**：`docs/battle-system-mechanics/` 23 章机制报告（A/B/C 可信度分层，与 docs/mechanics 方法论同款）——**第二个独立事实底座，逐节对拍的冲突点=待实测清单**

### ZSim（ZSim-Dev，绝区零模拟器）

- 仓库：<https://github.com/ZSim-Dev/ZSim> → `external/ZSim/`；**GPLv3——同上**
- **定位**：775★ 活跃，Hoyoverse 模拟器做到成熟的形态参照（模块边界/electron-app 用户入口/更新节奏）；其 ZZZ 侧困境（弹刀闪避交互不可丢弃、敌人节奏数据不可得）反证崩铁"交互可枚举"的选型优势

### FateSky12/hsr-sim（校准纪律建制派）

- 仓库：<https://github.com/FateSky12/hsr-sim> → `external/hsr-sim/`；**MIT——可读可借鉴，attribution 保留**
- **定位**：AI 重度辅助 5 天爆发产物；纯函数 BattleKernel + Vite 网页/Worker 池产品形态；有校准框架未对真（自我声明"内部黄金≠客户端校准"）
- **金矿**：`docs/calibration.md`——L0 面板 / L1 单跳 / L2 行动序 / L3 机制状态机四级校准 + JSON 固件 CI 门禁格式（expected/observed/容差）——**我方四级验收体系与 B19 实测产出物形态的现成参照**；其内置 4.4 击破表 Lv80=3767.5535 与我方锚点 3767.5533 第四位小数冲突（已登记 B19 待实测）

### hessiser/veritas（游戏内记录仪，golden case 工厂）

- 仓库：<https://github.com/hessiser/veritas> → `external/veritas/`；**MIT——同上**
- **定位**：IL2CPP 注入级记录仪（钩 `RPG_GameCore_TurnBasedGameMode` 读真实内部状态：真实 AV/逐跳伤害/StatChange/事件流），socket+CSV 导出
- **对我们的三重价值**：① B19 待实测项的机器化采集（注入式工具的 ToS 风险评估见 `autopilot_safety.md`）② 真实事件流 = 我方发射点对账表的第一个 ground truth ③ 敌人行为分布数据源（两家模拟器都缺的地基）

### LoranAndos/HSR-Combat-Simulator（覆盖最广研磨派）

- 仓库：<https://github.com/LoranAndos/HSR-Combat-Simulator>（未 clone）；**无 LICENSE——默认保留所有权利，只读语义，一行不搬**
- **定位**：15.7k 行 Python、36 角色硬编码（覆盖最广，Fate 联动齐）；架构无可学（ZSim 同款研磨流），价值是**36 个角色 kit 的手工编码语义**——mechanics 文档的第三方交叉校验语料（机制知识本身自由，放心读）

## 重新克隆

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
```

StarBench 官方代码（检测 checkpoint、LightRAG checkpoint）论文承诺发布但截至本笔记写入时未放出，arxiv 页面无代码链接；放出后克隆至 `external/starbench/` 同级。
