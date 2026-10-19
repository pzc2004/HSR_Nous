# HSR_Nous：博识尊驱动战斗分析与配装优化

> 本项目为非官方粉丝项目，与 miHoYo/HoYoverse 无关；《崩坏：星穹铁道》的游戏内容、角色与数值版权归 miHoYo/HoYoverse 所有。
>
> 本项目仅面向已正式上线内容的分析与优化，不支持、不认可任何未公开（测试服/解包）内容的测试与传播。

本项目面向《崩坏：星穹铁道》的配装与配队优化，以自研战斗模拟器为裁判、记忆驱动的探索循环为骨架，将目标转化为可验证、可复现的决策结果——快查秒回配装结论，探索模式持续沉淀机制新知。

## 目标

- 用数据与仿真替代纯经验型配装决策
- 系统性比较遗器、光锥、配速与队伍构成
- 输出可解释结论与清晰的方案权衡

## 为什么是崩铁：模拟精度天花板

数据驱动决策的前提是模拟器能和真实战斗对上。不同品类的游戏，这个前提的可达成度天差地别：

| | 实时动作游戏（如原神） | 崩铁（回合制） |
|---|---|---|
| 伤害耦合 | 帧率（30/60fps 输出不同）、输入时序（操作技术）、3D 物理 | 无——纯面板 × 公式 × 随机种子 |
| 系统性质 | 连续（物理 + 动画帧） | 离散（确定性状态机） |
| 模拟器天花板 | 理想化近似（"完美操作下的理论上限"） | **逐位一致**（小数点可对齐） |
| 失真来源 | 原理性不可修复 | 可修复的未知（数据/语义歧义/舍入） |

把"可模拟性"拆成两根轴看会更清楚：

- **轴一 · 系统复杂度**（规则逆向难度）：原神的元素反应最难（元素量/ICD/双结算，社区考古数年才钉死），但它是**确定性规则，可完全逆向**；崩铁乘区复杂但完全文档化；绝区零异常/紊乱比原神反应简单
- **轴二 · 交互建模难度**（敌人行为/空间/输入）：崩铁（回合制、空间可枚举）< 原神（实时但可整层砍掉——gcsim 不模拟敌人攻击，玩家不死，木桩化损失在一阶近似内可接受）< 绝区零（弹刀闪避就是数值本身，不可丢弃且节奏数据不可得）

可行公式 = **系统可逆向 × 交互可丢弃**——原神占一个半（可逆向 + 可丢弃），绝区零只占半个（交互不可丢弃），崩铁三项全赢：系统可完全文档化、交互空间小到可枚举、敌人行为可实测采集。

崩铁的战斗是确定性状态机：无 3D、无帧率、无操作技术、无物理——给定输入和随机种子，输出唯一。这使"逐位一致"的模拟在原理上成立，本项目的数据驱动决策因此有地基。

残余误差来源（均可治理）：

- **数据错误**：解包/文档数值偏差 → pipeline 更新 + 多源对拍
- **顺序语义歧义**：buff/事件触发顺序 → 设计文档决策 + 测试钉死
- **舍入规则**：显示整数取整方式 → 游戏内微实验反推
- **敌人 AI 随机性**：无法逐位复现 → 统计建模（方差、最差情况）

AI 驱动研究的共性结构是"生成 × 验证 × 循环"，**裁判（验证器）的成本决定一切**：数学有 Lean、代码有编译器、湿实验室按小时计费。本项目自带裁判——战斗模拟器就是零成本、确定性的实验台。多数配装工具只能拉表估算，我们直接"实战"复现。

## 设计哲学

**最高原则：找正交基。** 在一堆具体案例里认出"这 N 个东西其实是同一个东西的不同投影"——一旦找到，剩下的一切都变成基底的线性组合，表达力免费爆炸。传奇系统全是这么赢的：

- **vim**：操作符 × 动作（dw、cw、y}）——几十个按键组合出几千种编辑。不是背快捷键，是语法
- **Lisp**：极小核心 + 代码即数据——几个特殊形式长出整个语言。本项目的"闭合关键字集 + 开放命名空间"正是特殊形式 vs 库函数之分
- **Unix**：小工具各干一件事，管道组合——本项目的结算原子化即 Unix 原语
- **Emacs**：一切都是 buffer，一切皆可 Lisp 改写——一个通用容器承载所有操作，整个环境运行时可自省

学术出处：Fred Brooks《没有银弹》把复杂度分为**本质复杂度与偶然复杂度**——正交基砍的永远是偶然复杂度："这个新概念真的需要存在吗？"

**唯物主义检验**：泛化必须有实例垫底，拒绝凭空设计。本项目的每次泛化都由全量机制扫描（全角色、数千条标注）垫底，并由 lint 闸机器校验——实践是检验抽象的唯一标准。

**数据三分**：一切实体 = **配置**（常量数值）/ **状态**（自定义变量）/ **规则**（技能机制）。角色、光锥、遗器、敌人同构；战前组装时全部实体编译归并进 actor 的三桶（数值→面板、机制→挂身 modifier、叠层→资源）。因此内容可以自由组装：新角色永远只改输入，不动源码。

> 这套哲学在当代的印证（组件热插拔的形式化、可逆副作用等）见 `docs/external_references.md` 理论参照节。

## 项目结构

```
src/hsr_nous/
├── common/            # 公共基座：路径 / .env / IO 基元（零项目依赖，所有模块可 import）
│   ├── paths.py       # 路径唯一事实源（repo/data/research 三类根；data 默认仓库 ./data，research 默认 ~/HSR_Nous，均可 env 覆盖）
│   ├── env.py         # .env 手写解析 + load_repo_env（不覆盖已有环境变量）
│   └── README.md      # 准入规则与 API 清单
│
├── pipeline/          # 数据访问层：下载 + 加载 + 查询（StarRailRes + Fandom wiki + 关卡编成）
│   └── README.md      # pipeline 模块详细文档（文件清单与数据源以彼处为准）
│
├── sim_schema/        # 仿真器输入格式（sim 的唯一输入）
│   ├── README.md      # 文档索引（含各章主题）
│   ├── docs/          # 分章节数据格式设计（按编号分章，00_overview 起）
│   ├── examples/      # 示例输入（build / stage）
│   └── *.py           # 数据类定义（actor/action/encounter/rulebook 等）
│
├── adapters/          # 适配层：外部数据 -> 仿真输入（主路径为模板生成器，详见 adapters/README.md）
│   ├── template_generator.py  # pipeline 结构化数据 -> per-entity DSL YAML 模板
│   ├── template_verifier.py   # 模板回读校验（与生成器双份映射互相盯梢）
│   └── *_adapter.py   # 对象适配器（pipeline 数据 -> sim_schema 对象，服务 account 侧）
│
├── sim/               # 战斗模拟器（纯仿真核心，只依赖 sim_schema；编译器+VM 分层，模块地图详见 sim/README.md）
│   ├── engine.py      # CombatEngine 战斗主干（回合四段主循环 + 击破 + 敌人行动 + 波次切换）
│   ├── scheduler.py   # 距离制调度器（守恒剩余距离主状态 + 红黑树排序）
│   ├── avtree.py      # 数组化红黑树（CFS 同构，整树可序列化）
│   ├── bus.py         # 事件总线（发射点 / waterfall-emit / modify_event）
│   ├── hooks.py       # 模板 hooks 运行时（订阅 + 条件求值 + 效果执行）
│   ├── modifiers.py   # modifier 生命周期 + 护盾吸收
│   ├── pipeline.py    # 结算管线（两层求值 → effect 原语 → 伤害公式）
│   ├── state.py       # 战斗全状态 dataclass（可序列化快照）
│   ├── resources.py   # 能量资源三段式（终结技阈值 / 可用性判定）
│   ├── policy_api.py  # 策略接口（legal_action_set + 编译策略运行时）
│   ├── montecarlo.py  # 多局统计聚合（roll 模式 N 局 → 伤害分布）
│   └── compile/       # 绑定编译层（build/stage YAML → 不可变 CompiledEncounter）
│
├── research_schema/   # 研究契约纯数据模型 + canonical JSON（不依赖 sim）
│   ├── README.md      # research spec 文档索引
│   └── docs/          # 分章节研究后端规范（00_overview 起）
├── research_protocol/ # paired-v1 固定协议解析与契约校验（不执行模拟）
├── research_core/     # 机制 variant + 只读 artifact + 可信内核/claim/JSON 报告
├── research_permissions/ # CapabilityPolicy + ResearchGateway/submit_claim（外部权限边界）
├── research_web/      # 可选外部检索与证据（DeepSeek Search/Fetch provider + WebEvidenceStore）
├── agents/          # 外部 Agent harness 适配（DSH headless + 工具白名单）

docs/                       # 战斗规则文档（模拟器"唯一事实来源"）
├── README.md               # 文档导航与使用说明
├── game_rules.md           # 战斗规则总览
└── mechanics/              # 详细机制文档（按章节编号，00_game_basics 起，索引见 docs/README.md）

tests/                 # 测试目录

data/                  # 数据目录（gitignored）
├── starrailres/       # StarRailRes 索引数据（en/ cn/ 等多语言）
├── stages/            # 关卡编成 + 怪物数值（Hakushin + buhflipexplode，红线过滤后落盘）
├── enemies/           # 敌人数据（来源: theBowja/starrail-data，遗留源，断更于 3.2）
├── fandom_skill_data.json  # Fandom wiki 技能机制数据（削韧/回能/SP消耗/嘲讽值加成）
└── fandom_enemy_data.json  # Fandom 敌人技能/抗性/弱点（extract_fandom_enemies 提取）
```

## 模块边界（严格遵守）

<!-- module-boundaries -->
| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `common/` | 无 | `pipeline`, `sim_schema`, `adapters`, `sim`, `ops`, `account`, `llm`, `research_schema`, `research_protocol`, `research_core`, `research_permissions`, `research_web`（公共基座是叶子层，零项目依赖） |
| `pipeline/` | `common` | `sim_schema`, `sim` |
| `sim_schema/` | `common` | `pipeline`, `sim`, `adapters` |
| `adapters/` | `pipeline`, `sim_schema`, `account`（账号数据适配）, `llm`（LLM 统一接入层 tribios）, `common` | `sim`（只输出 sim_schema，不调用仿真） |
| `sim/` | `sim_schema`, `common` | `pipeline`, `adapters` |
| `research_schema/` | 无 | `research_protocol`, `research_core`, `sim`, `pipeline`, `adapters`（纯数据契约） |
| `research_protocol/` | `research_schema` | `research_core`, `sim`, `pipeline`, `adapters`（固定协议解析与校验，不执行模拟） |
| `research_core/` | `research_schema`, `research_protocol`, `sim`, `sim_schema`, `common` | `pipeline`, `adapters`（执行、证据、可信计算与报告层） |
| `research_permissions/` | `research_core`, `research_schema`, `research_protocol`, `research_web`, `common` | `sim`, `pipeline`, `adapters`（外部权限网关） |
| `research_web/` | `research_schema`, `common` | `research_core`, `research_permissions`, `sim`, `pipeline`, `adapters`（外部检索与证据层） |
| `agents/` | `research_schema`, `research_permissions`, `common` | `sim`, `research_core`, `pipeline`, `adapters`（外部 harness 适配，可信执行只经网关） |
| `ops/` | `llm`, `adapters`, `sim`, `pipeline`, `sim_schema`, `common` | — |
| `account/` | `common` | `sim`, `pipeline`, `adapters` |
| `llm/` | `common` | `pipeline`, `sim_schema`, `sim`, `adapters` |
<!-- /module-boundaries -->

数据访问层与战斗模拟器完全解耦：

```
StarRailRes (JSON) ──[pipeline 加载]──→ 结构化 dict
                                              │
                                              ▼
                                         [adapters.template_generator]
                                              │
                                              ▼
                                    data/sim_templates/**/*.yaml
                                              │
                                              ▼
                                    [sim.compile.compile_encounter]
                                              │
                                              ▼
                                    CompiledEncounter（绑定后的不可变纯数据）
                                              │
                                              ▼
                                    [sim.engine.CombatEngine.from_compiled] ──→ 仿真结果
```

## 核心设计亮点

### 事件-响应模型

技能、行迹、星魂、光锥、遗器本质都是**事件监听器**。所有持续效果通过 `Modifier` 表达，触发时机包括 `on_battle_start`、`on_turn_start`、`on_before_hit`、`on_kill` 等。

详见 [`sim_schema/README.md`](src/hsr_nous/sim_schema/README.md)。

### 策略模型

战斗策略采用 **Rule-based + 参数化混合** 设计，用结构化数据模型定义：

```yaml
policy:
  name: "march_7th_default"
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"
      action: "ultimate"
      priority: 100
    - condition: "skill_points > 0"
      action: "skill"
      priority: 50
    - condition: "true"
      action: "basic"
      priority: 0
  parameters:
    ULT_THRESHOLD: 120
```

- 模拟器直接 interpret，100% deterministic
- 参数（如 `ULT_THRESHOLD`）可独立调优，适合贝叶斯优化
- LLM 容易生成结构化的规则而非自然语言

详见 [`14_policy.md`](src/hsr_nous/sim_schema/docs/14_policy.md)（策略模型：规则匹配、参数优化）。

## 模块命名与世界观

核心模块命名对应游戏内星神/概念，只给平级核心模块起游戏名，工具层（pipeline、adapters、docs）与纯数据契约不命名。代码目录仍使用朴素功能名，英文 key 只用于名册和显示层。Agent 层重建尚未完成；各研究模块的实现状态在行内标注。

| 模块 | 命名 | 英文 key | 官方描述 | 对应理由 |
|------|------|----------|---------|---------|
| 项目整体 | 博识尊 | `nous` | "万物皆是疑问，一切必有解答。原为用于求解万物的星体计算机，由机器升格而成的星神。"[1] | 项目旨在求解配队配装问题 |
| Simulator | 翁法罗斯 | `amphoreus` | 博识尊的天体神经元——权杖 δ-me13 中运行的模拟世界，通过无数次循环实验求解"生命的第一因"[2] | 通过重复模拟求解最优配装/配队 |
| Research Protocol | 太一 | `ena` | "万事万物归于一统，共存共荣，永在「秩序」之中。"[1] | `research_protocol`：规定 paired-v1 固定协议并校验契约、seed/holdout、预算与 patch，不执行模拟；比较组与 claim 状态流转由 research_core 承接 |
| Research Core | 克里珀 | `qlipoth` | "祂知晓大敌的吞噬迫在眉睫。因此不得不以光年为单位铸造障壁加以封印，隔绝保护尚有生机的世界。"[1] | `research_core`：强制执行协议、调用模拟器、保存只读证据、运行可信内核并校验 claim，守护可信结论的唯一通道 |
| Agent（DSH 最小接入） | 阿基维利 | `akivili` | "阿基维利离开孤绝世界裴伽纳，不断开拓着宇宙未知的边界，试图找寻存在之树的端点。"[1] | `agents`：提出假设、生成研究契约并调用工具探索方案，不直接制造可信结论 |
| Memory（规划） | 浮黎 | `fuli` | "世间再无比纯粹的记忆更加包容的存在：它记录一切，不嫌恶，不偏爱；它无私地保留每个基本的事实，每种绮丽的姿态。"[1] | `memory`：跨项目保存 claim、证据—推导关系、失败与反例，不修改原始 artifact |
| Research Workbench（规划） | 伊德莉拉 | `idrila` | "在诡丽变幻的宇宙图景中，伊德莉拉窥见了世界存在的终极意义：人们谓之「美」的存在。"[1] | `research_workbench`：把结构化结果呈现为可读、可交互的研究文档，支持下钻、选中联动、重放与人工接管 |
| data/ | 智库 | `data_bank` | 列车上的百科全书系统[3] | 存储角色/光锥/遗器/敌人数据 |

**主要信息源：**

- [1] 萌娘百科·崩坏：星穹铁道/智库（游戏内智库星神与派系词条总汇；本地分节摘录见 [docs/lore/universe.md](docs/lore/universe.md) §三）
- [2] 萌娘百科·翁法罗斯（权杖 δ-me13 与实验设定；本地整理及交叉来源见 [docs/lore/amphoreus.md](docs/lore/amphoreus.md) §一）
- [3] 百度百科·智库（列车智库的访问与管理设定）

[1]: https://zh.moegirl.org.cn/zh-cn/%E5%B4%A9%E5%9D%8F%EF%BC%9A%E6%98%9F%E7%A9%B9%E9%93%81%E9%81%93/%E6%99%BA%E5%BA%93

[2]: https://zh.moegirl.org.cn/zh-cn/%E7%BF%81%E6%B3%95%E7%BD%97%E6%96%AF

[3]: https://baike.baidu.com/item/%E6%99%BA%E5%BA%93/63845944

## 开发工具

本项目以 Claude Code / Kimi Code 为 AI 编程助手，开发配置与工程 skill 见 `AGENTS.md`。

## 安装

使用 `uv`（全 extras——`web` 组的 fastapi/uvicorn 是 web 测试的硬依赖；`ops` 组的 ddgs 是打标流水线（ops/annotator）社区搜索层依赖；各 extras 的可选面见 `pyproject.toml`）：

```bash
uv venv
uv pip install -e ".[dev,account,web,ops]"
```

## CLI 命令

```bash
# 更新游戏数据（从 StarRailRes GitHub 拉取）
hsr-data-update

# 更新简体中文数据
hsr-data-update --lang cn

# 下载敌人数据（来源: theBowja/starrail-data）
hsr-data-update --enemies

# 下载关卡编成数据（Hakushin + buhflipexplode，含未发布内容红线过滤）
hsr-data-update --stages

# 使用 SSH 下载（国内网络更快，需配置 GitHub SSH key）
hsr-data-update --ssh

# 指定数据目录
hsr-data-update --data-dir ./my_data
```

## 数据来源

| 数据 | 来源 | 说明 |
|------|------|------|
| 角色/光锥/遗器 | [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes) | 基础数据（属性、倍率等） |
| 敌人基础数值 | Hakushin（hakush.in 数据后端） | HP/攻击/防御/速度/韧性 base 值 + 关卡系数 |
| 敌人技能/抗性 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom）Enemy 模板 | 技能倍率、七元素抗性、debuff 抵抗 |
| 敌人数据（遗留） | [theBowja/starrail-data](https://github.com/theBowja/starrail-data) | 断更于 3.2（上游被 DMCA 下架），≤3.2 敌人数据仍可用 |
| 技能机制数据 | Fandom wiki | 削韧值、回能值、SP 消耗、嘲讽值加成等 |
| 关卡编成（深渊） | [Hakushin API](https://static.nanoka.cc) + [buhflipexplode-src](https://github.com/spiritfxxxx/buhflipexplode-src) | 期数/波次/等级/系数/关卡 buff，含异相仲裁；落盘前经红线过滤剔除未上线内容 |

## 运行测试

全量回归前，先用本地与 CI 共用的脚本准备数据、optimizer 和 Playwright：

```bash
bash scripts/setup_test_env.sh
.venv/bin/python -m pytest tests/ -q -rs
```

最小测试与数据刷新方式见 `tests/README.md`。缺依赖导致的 skip 应先按环境诊断信息排查，不应直接视为回归通过。

## 决策闭环（autoresearch 形态）

记忆驱动的探索循环，同一循环两档：

1. **假设**：快查档枚举候选（如遗器组合），探索档由 agent 自生成或按用户方向生成
2. **实验**：组装 sim 配置，运行确定性仿真（固定种子，N 次重复）
3. **评审**：按指标 + 惊讶度（与社区先验的偏差 × 验证强度）排序
4. **入库**：结论经复核后沉淀进记忆库（正典），跨项目复用
5. **迭代**：快查档跑完即止（秒级），探索档循环至挖不动或预算尽

## 关键指标

- DPS 与伤害分布
- 生存率 / 存活时间
- 能量循环与终结技覆盖率
- 行动序稳定性 / 配速可行性
- RNG 敏感性（方差、最差情况）

## MVP 范围

- 支持敌人数据（弱点、抗性、技能），可用于更真实的战斗模拟
- 单队伍（4 人）与单关卡
- 限定遗器套装与光锥列表
- 固定随机种子与确定性仿真
- 简化的搜索预算与启发式策略

## 下一步

- [x] `sim_schema` 文档与规则文档交叉校验（公式冲突已修复、缺失机制已补充）
- [x] 完成 `sim_schema` v0.5 DSL-first 文档迁移（per-entity 模板、自定义资源、形态、秘技、场地、战前策略）
- [x] 实现 `adapters.template_generator` 模板生成流程（角色/光锥/遗器/敌人 → `data/sim_templates/**/*.yaml`，含 verifier 回读校验）
- [x] 实现 `sim.compile` 绑定编译层（build/stage YAML → `CompiledEncounter`：符号解析 + AST 预编译 + 糖 desugar）
- [x] 实现 `sim.engine` 伤害公式 / buff 管理 / 行动序 / 资源系统
- [ ] Pydantic v2 迁移（`sim_schema` 数据类）
- [x] 完善 `sim.engine` 战斗循环（回合四段主循环、击破、敌人行动、波次切换）
- [x] 添加 Agent 接口与评估闭环（五 Agent + `api/orchestrator.py`）（旧层已于 2026-10-15 删除，新形态另行重建）
- [ ] 构建基础 CLI 用于实验

## 协议

[MIT License](LICENSE)
