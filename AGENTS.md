# HSR_Nous 项目指南

## 项目简介

面向《崩坏：星穹铁道》的配装与配队优化系统，采用 ReAct 多 Agent 闭环架构。

## 术语规范

代码和 LLM 交互使用**英文 canonical key**，文档和用户界面使用**中文显示名**。映射表见 `terminology.yaml`。

- 代码中一律用英文（`turn`、`cycle`、`wave`、`break_effect`）
- 文档/注释中可使用中文（回合、轮次、波次、击破特攻）
- 核心模块对应游戏世界观星神：

| 模块 | 命名 | 官方描述 | 职责 |
|------|------|---------|------|
| 项目整体 | 博识尊 (Nous) | "原为解答宇宙而生的天体计算机，升格为星神" | 求解配队配装问题 |
| Simulator | 翁法罗斯 (Amphoreus) | 博识尊的天体神经元——权杖 δ-me13 中运行的模拟世界，通过无数次循环实验求解"生命的第一因" | 通过重复模拟求解最优配装/配队 |
| Agent | 阿基维利 (Akivili) | "不断开拓宇宙的未知边缘" | 探索新方案、规划决策 |
| Memory | 浮黎 (Fuli) | "不偏不倚地记录一切，无私地保存每一个基本事实" | 存储和检索经验 |
| data/ | 智库 (Data Bank) | 列车百科全书 | 角色/光锥/遗器/敌人数据 |

> 星神名只给平级模块；引擎**内部组件**用泰坦级命名（janus 事件总线 / talanton 校验器 / oronyx 调试控制器 / georios 构建器 / phagousa modifier 体系 / aquila 边界层 / cerces 理性计算（AST/策略求值） / mnestia 呈现层 / nikador 伤害管线 / thanatos 死亡链 / zagreus 随机源 / kephale、demiurge 候补），名册与命名规则见 `src/hsr_nous/sim/README.md`。

## 项目结构速查

```
src/hsr_nous/
├── pipeline/      # 数据访问层：下载 + 加载 + 查询 StarRailRes/Fandom 数据 — 独立，不 import 其他模块
│   └── README.md  # pipeline 详细使用文档
├── raw_schema/    # 原始数据模型（StarRailRes schema）
├── sim_schema/    # 仿真器输入格式
│   ├── README.md  # 文档索引
│   ├── docs/      # 分章节数据格式设计（按编号分章，00_overview 起）
│   ├── examples/  # 示例输入（build / stage）
│   └── policy.py  # 策略数据结构
├── adapters/      # 外部数据 → sim_schema 桥梁（模板生成器产 DSL YAML + 旧对象适配器）
├── sim/           # 纯战斗模拟器（只认识 sim_schema）
│   └── engine.py  # 含 PolicyInterpreter
├── agents/        # ReAct 五 Agent（Planner/Builder/Search/Evaluator/Explainer）
├── api/           # 编排器（Orchestrator）
├── account/       # Mihoyo 账号集成（HoYoLAB API，keyring 优先）
├── screen/        # 屏幕识别框架（ONNX 检测器 + 状态解析）
└── pilot/         # 自动战斗执行层（opt-in，HSR_NOUS_ALLOW_AUTOPILOT=1）
```

## 模块边界（严格遵守）

| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `pipeline/` | 无 | `raw_schema`, `sim_schema`, `sim`, `agents`, `api` |
| `raw_schema/` | 无 | `sim_schema`, `sim`, `agents`, `api` |
| `sim_schema/` | 无 | `pipeline`, `raw_schema`, `sim`, `adapters`, `agents`, `api` |
| `adapters/` | `pipeline`, `raw_schema`, `sim_schema`, `account`（账号数据适配）, `llm`（LLM 统一接入层 tribios） | `sim`（只输出 sim_schema，不调用仿真） |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents` |
| `agents/` | `adapters`, `sim`, `pipeline`（仅数据查询，与 data_tools 同模式）, `account`（账号数据查询）, `llm`（LLM 统一接入层 tribios） | `raw_schema`（通过 pipeline/adapters 间接使用） |
| `api/` | `agents`, `adapters`, `sim`, `pipeline`（仅编排元数据）, `llm`（LLM 统一接入层 tribios） | `raw_schema` |
| `llm/` | 无 | `pipeline`, `raw_schema`, `sim_schema`, `sim`, `adapters`, `agents`, `api` |
| `account/` | 无 | `sim`, `agents`, `pipeline`, `adapters` |
| `screen/` | `adapters`, `sim_schema` | `sim`, `agents`, `pipeline` |
| `pilot/` | `screen` | `sim`, `agents`, `pipeline`, `adapters` |

**核心原则**：数据管道与 sim 解耦，中间通过 adapters 桥接。

> 本表受 `tests/test_doc_lint.py` 模块边界闸双向校验（表格文本 ↔ 闸门配置 ↔ 实际 import），改表需同步闸门配置。

**关于 `llm/` 的放宽说明**：`llm/`（tribios/缇里西庇俄丝）是 LLM 调用统一接入层
（多 key 管理 + 每 key 并发 + 流式任务调度），自身零项目依赖（只标准库 + httpx），
不 import 任何项目模块；`adapters`/`agents`/`api` 允许 import `llm`——标注流水线、
agents、将来的 evaluator 共用同一 `LLMClient` + `Scheduler`。

**关于 `pipeline` 的放宽说明**：`pipeline/` 实际上是数据访问层（下载/更新 + JSON 加载 + 属性计算），
不包含任何运行时编排逻辑。`agents/` 和 `adapters/` 需要调用 `pipeline.calc_character_stats`、
`pipeline.get_character_by_name` 等纯函数，因此允许 `pipeline → 上述模块`。
**禁止**：从 `pipeline` 反向调用任何 `sim` 或 `agents` 函数。

## 工具依赖

**硬性要求**：所有 Python 包安装必须使用 `uv`（`uv pip install`、`uv run`、`uv venv`）。
**禁止**使用 `pip install` 或 `conda`。

## 技术栈

- Python >= 3.10
- `uv` 包管理 + `hatchling` 构建后端
- `pytest` 测试
- dataclasses（模型层，计划迁移至 Pydantic v2）

## 常用命令

```bash
# 安装（editable mode，含所有可选模块）
uv pip install -e ".[dev,account,screen,pilot,web]"

# 仅安装核心 + dev
uv pip install -e ".[dev]"

# 测试
pytest tests/ -v

# 更新游戏数据（从 StarRailRes GitHub 拉取）
hsr-data-update

# 更新简体中文数据
hsr-data-update --lang cn

# 下载敌人数据（来源: theBowja/starrail-data）
hsr-data-update --enemies

# 下载关卡编成数据（深渊，含红线过滤）
hsr-data-update --stages

# 下载技能机制数据（战技点耗产复核 + 米游社五项标签；红线依赖主数据，先跑默认更新）
hsr-data-update --mechanics

# 使用 SSH 下载（国内网络更快，需配置 GitHub SSH key）
hsr-data-update --ssh

# 指定数据目录
hsr-data-update --data-dir ./my_data
```

## 代码约定

- **压缩优先（最高设计原则）**：面对新需求先问"能不能用现有件组合出来"——删/并/一般化永远优先于新增概念；新关键字/新字段/新原语必须证明现有件组合不出，且压缩收益显著（一个顶多个）。反面同样成立：**不许过度抽象**——泛化必须有实例垫底（扫描/数据证据），拒绝凭空设计。本项目的 DSL 哲学（闭合关键字集+开放命名空间、事件总线、结算原子化）都是此原则的实例
- **实现严格按文档设计**：`sim_schema/docs` 与 `docs/mechanics` 是 spec，代码不得静默偏离——确需偏离时**先改文档再写码**；发现的 doc-vs-code divergence 一律登记 BACKLOG（B27）过堂。执行三层：能"代码直接消费 spec"的一律做成消费（如公式=表达式数据，divergence 构造上不可能）；不能直接消费的挂 lint 闸（先例：模块边界闸/镜像公式闸）；存量靠 B27 收官清算
- 类型注解尽量完整
- pipeline 中的 CLI 函数使用 `main() -> int` 签名，`raise SystemExit(main())` 模式
- 测试放在 `tests/` 下，与 `src/` 目录结构对应
- 实际数据文件放在 `data/`（gitignored），模型代码放在 `src/`
- **易变数字三原则**：文档/注释不写会过期的精确计数（文件数/行数/章节数/闸数）——规模修饰用模糊量词（十余个/约两千/20+），能算的让工具现场算，承载信息的枚举（对照表/清单）与所指物同文件就近维护
- **防腐原则**：上层文档不重复下层事实——能删就删（只指路）；必须重复就让 `tests/test_doc_lint.py` 的闸保证一致，改被检对象时同步闸门配置；已有闸：索引（README↔磁盘）、模块边界（AGENTS.md 表↔实际 import）、镜像公式、§引用等，详见 `tests/README.md`
- **模板格式**：角色/光锥/遗器/敌人/关卡机制用 per-entity DSL YAML 模板描述（`data/sim_templates/**/*.yaml`，由 adapters 生成），`build.yaml` / `stage.yaml` 保持 YAML（纯数据声明）
- **命名两态原则**：入库的角色/技能/光锥名只有两种合法状态——官方名（先经 query-game-data 查数据）或明显假名（"测试员/假人"），不许存在"听起来像真的"的中间态（脑补名是幻觉温床）
- **同人物多实体必须消歧**：SP 角色（姬子•启行≠姬子、丹恒•饮月/丹恒•腾荒≠丹恒、三月七 1001/1224 同名两实体、停云≠忘归人、刃≠千冶•刃、开拓者按命途写如"开拓者•欢愉"）引用机制时必须全称或带 ID，不得简称；间隔号 • 不必然是 SP 标记——**判断依据是是否存在同人物另一实体**：千冶•刃（1507）有刃（1205）→ 是 SP；阮•梅（1303）无另一实体 → • 是名字本体，别误"纠正"；query skill 对同名查询报歧义+列候选
- **外部输入核查三关**：外部评审/社区结论/wiki 的**事实主张**（"X 未定义/Y 不存在"）采纳前必须过三关——① 查文档原文（真的没写吗）② 查实现现状（真的没做吗）③ 查亲历证据（我们自己踩过吗）；三关全过才采纳。纯审美判断（优雅/高级）当共鸣不当依据；越笃定的主张越要查。（教训：2026-08-22 外部评审"accumulated×waterfall 无定义"被 §23.4 文档自身第 148 行证伪——评审没读到，我们差点跟风立错规则）

## 数据查询

Coding agent 要查角色/光锥/遗器/敌人的机制、数值、中英文时，调用 `query-game-data` skill（**不要**直接读 `data/starrailres/index_new/cn/*.json`）：

```bash
python3 .agents/skills/query-game-data/query.py <entity_type> <query>
```

详见 `.agents/skills/query-game-data/SKILL.md`。
关键规则：

- 角色查询附带 `signature_light_cone_id`（**不**附带专光机制——专光机制要单独查）
- 光锥查询**不**返回装备该光锥的角色 ID
- 查不到时**先怀疑数据源过时**——`hsr-data-update` / `extract_fandom_lightcones` 重跑后再报不存在

要查**游戏机制规则**（伤害公式 / 击破 / 战技点 / 行动序 / buff 叠加……）时，调用 `query-game-rules` skill——agent 自己 `Read` `docs/mechanics/*.md` + `docs/game_rules.md`，找不到再用 `WebFetch` 兜底（Fandom / 米游社）。详见 `.agents/skills/query-game-rules/SKILL.md`。
- 查不到时返回 `_error` + `_hint`，**不要脑补数据**
- 中英术语映射查 `terminology.yaml`

## 工程流程 skills

- **机制扫描**（角色技能 → 原语红绿灯矩阵，检验 schema 表达力）：`.agents/skills/mechanics-scan/`，开新扫描轮次、补扫新角色、对比两轮结果时用
- **一致性审计**（规则文档 vs schema 文档四层核对）：`.agents/skills/consistency-audit/`，成批改文档、接新数据源、版本更新后用
- 日常小改动只需跑文档 lint：`pytest tests/test_doc_lint.py -v`（详见 `tests/README.md`）

> skill 真身统一放 `.agents/skills/`（Kimi Code Project 域自动扫描）；`.claude/skills/` 内每个条目都是指向前者的软链接（Claude Code 官方支持的兼容入口）。改 skill 只改 `.agents/skills/`。

## 关键设计决策

1. **为什么用 `src/` layout**：避免运行时代码与测试代码路径冲突，支持 `pip install -e .` 正确安装。
2. **为什么 pipeline 要独立**：外部数据源（StarRailRes）的格式可能变化，pipeline 改动不应影响 sim。
3. **为什么用 `adapters` 而不是让 sim 直接读 raw**：让 sim 专注于仿真逻辑，不关心外部数据源 schema。
4. **为什么保留 `scripts/` 目录**：未来放真正的一次性运维脚本，pipeline 代码已迁移到 `src/hsr_nous/pipeline/`。
5. **策略设计**：`sim_schema/policy.py` 定义策略数据结构（action_rules / target_rules + 可调参数；timing_rules 未落地已退役，见 14_policy.md），优化器调参数，sim 引擎 interpret 执行；战前策略（秘技顺序）见 `sim_schema/docs/20_pre_battle_strategy.md`。

## 扩展方向

- 添加新数据源：在 `pipeline/` 新增 loader，输出到 `raw_schema/` 兼容格式
- 扩展仿真机制：只在 `sim_schema/` 和 `sim/` 中修改
- 新 Agent：在 `agents/` 中新增，通过 `api/orchestrator.py` 注册
- 策略优化：修改 `sim_schema/policy.py` 参数，通过 `PolicyInterpreter` 执行

## 数据来源

| 数据 | 来源 | 本地路径 |
|------|------|----------|
| 角色/光锥/遗器等 | [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes) | `data/starrailres/index_new/{lang}/` |
| 敌人基础数值 | Hakushin monstervalue（单文件全怪 base 值 + 修正系数，随 `--stages` 更新） | `data/stages/hakushin/monstervalue.json` |
| 敌人技能/抗性 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom）Enemy 模板，提取脚本 `pipeline/extract_fandom_enemies.py` | `data/fandom_enemy_data.json` |
| 敌人数据（遗留） | [theBowja/starrail-data](https://github.com/theBowja/starrail-data)——**断更于 3.2（上游 DimBreath 2024-10 被 DMCA），降级为遗留源** | `data/enemies/enemies.json` |
| 技能机制数据 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom） | `data/fandom_skill_data.json` |
| 技能机制五项（类型/能量上限/削韧/回能/战技点，逐技能权威源） | [米游社·开拓者笔记](https://bbs.mihoyo.com/sr/wiki/)（官方 WIKI 静态 CDN 接口），提取脚本 `pipeline/extract_miyoushe_skills.py` | `data/miyoushe_skill_data.json`（缓存 `data/miyoushe/cache/`） |
| 关卡编成（深渊） | [Hakushin API](https://static.nanoka.cc)（hakush.in 数据后端） | `data/stages/hakushin/` |
| 关卡编成（含异相仲裁） | [buhflipexplode-src](https://github.com/spiritfxxxx/buhflipexplode-src) | `data/stages/buhflipexplode/` |

StarRailRes 提供倍率等基础数据，Fandom wiki 补充削韧值、回能值、战技点消耗等机制数值。提取脚本：`pipeline/extract_fandom_skills.py`。米游社官方 WIKI（`pipeline/extract_miyoushe_skills.py`）提供逐技能结构化的类型/能量上限/削韧/回能/战技点五项标签——战技点含强化/派生技真实耗产，是该五项的权威源；Fandom 的 SP 值为类型规则合成（provenance 见各自数据文件）。

> **红线：只接入已正式上线版本的数据**——未发布内容不拉、不存、不发布；`hsr-data-update` 只在版本正式更新后运行。红线适用于**所有**数据源——期数类源（stages）按内容过滤，版本追踪类源（StarRailRes/theBowja）以 Hakushin 已上线花名册做版本对齐校验（warn-only，神谕仅作绊线，官方公告为终审），实现见 `pipeline/redline.py`。
