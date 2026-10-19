# HSR_Nous 项目指南

## 项目简介

面向《崩坏：星穹铁道》的配装与配队优化系统——当前为战斗模拟器 + 机制数据底座；Agent 层退役重建中。

## 术语规范

代码和 LLM 交互使用**英文 canonical key**，文档和用户界面使用**中文显示名**。映射表见 `terminology.yaml`。

- 代码中一律用英文（`turn`、`cycle`、`wave`、`break_effect`）
- 文档/注释中可使用中文（回合、轮次、波次、击破特攻）

## 项目结构速查

```
src/hsr_nous/
├── common/        # 公共基座：路径 / 环境变量 / .env / IO 基元（零项目依赖，所有模块可 import）
│   ├── paths.py   # 路径唯一事实源（repo/data/research 三类根；data 默认仓库 ./data，research 默认 ~/HSR_Nous，均可 env 覆盖）
│   ├── env.py     # .env 手写解析 + load_repo_env（不覆盖已有环境变量）
│   └── README.md  # 准入规则与 API 清单
├── pipeline/      # 数据访问层：下载 + 加载 + 查询 StarRailRes/Fandom 数据 — 独立，不 import 业务模块
│   ├── paths.py   # 数据域路径（缓存级/内容级 helper；公共根由 common/paths 转出）
│   └── README.md  # pipeline 详细使用文档
├── sim_schema/    # 仿真器输入格式
│   ├── README.md  # 文档索引
│   ├── docs/      # 分章节数据格式设计（按编号分章，00_overview 起）
│   └── examples/  # 示例输入（build / stage）
├── adapters/      # 外部数据 → 仿真输入桥梁（模板生成器产 per-entity DSL YAML + 对象适配器）
├── sim/           # 纯战斗模拟器（只认识 sim_schema）
│   └── policy_api.py  # 策略运行时（ScriptedPolicy / CompiledPolicyRuntime）
├── research_schema/    # 研究契约纯数据模型 + canonical JSON（零项目依赖）
│   ├── README.md       # research spec 文档索引
│   └── docs/           # 分章节研究后端规范（00_overview 起）
├── research_protocol/  # paired-v1 固定协议解析与契约校验（不执行模拟）
├── research_core/      # 机制 variant + 只读 artifact + 可信内核/claim/JSON 报告
├── research_permissions/ # CapabilityPolicy + ResearchGateway/submit_claim（外部权限边界）
├── research_web/    # 可选外部检索与证据（DeepSeek Search/Fetch provider + WebEvidenceStore）
├── agents/        # 外部 Agent harness 适配（DSH headless + 工具白名单；不直接制造可信结论）
├── ops/           # 生产运行时与批量流水线（DAG 执行器 + 生产 DAG——打标 annotator 首租）
└── account/       # Mihoyo 账号集成（HoYoLAB API，keyring 优先）
```

模板/配置数据布局（`data/` 其余内容全 gitignored——游戏数据 dump 见「数据来源」节）：

```
data/library/          # 机制库正典根（手写全机制 DSL 模板，全部 tracked——运行时模板查找链首根，
│                      #   见 sim_schema/templates.py RUNTIME_TEMPLATE_ROOTS）
├── characters/        # 角色（含 9999xx 测试假人——命名两态之明显假名，web catalog 列出是预期行为）
├── light_cones/       # 光锥
├── relics/            # 遗器
├── enemies/           # 敌人手写件（sandbag_假人——demo/打标 probe 木桩）
└── system/paths/      # 命途系统模块（elation.yaml——模板 import 机制 auto-import 按命途注入）
data/sim_templates/    # 生成兜底根（adapters 生成器纯产出，gitignored——正典根未覆盖实体兜底）
data/battles/          # 对局配置库（tracked，约定只放策展件——demo/验收 build+stage）
tests/                 # 纯测试代码（零 YAML——模板正典已全部迁 data/library）
```

## 模块边界（严格遵守）

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

**核心原则**：数据管道与 sim 解耦，中间通过 adapters 桥接。

> 本表受 `tests/test_doc_lint.py` 模块边界闸双向校验（表格文本 ↔ 闸门配置 ↔ 实际 import），改表需同步闸门配置。

**关于 `pipeline` 的放宽说明**：`pipeline/` 实际上是数据访问层（下载/更新 + JSON 加载 + 属性计算），
不包含任何运行时编排逻辑。`adapters/` 需要调用 `pipeline.calc_character_stats`、
`pipeline.get_character_by_name` 等纯函数，因此允许 `pipeline → 上述模块`。
**禁止**：从 `pipeline` 反向调用任何 `sim` 函数。

**关于 `llm/` 的放宽说明**：`llm/`（tribios/缇里西庇俄丝）是 LLM 调用统一接入层
（多 key 管理 + 每 key 并发 + 流式任务调度），自身不 import 业务模块（只标准库 +
httpx + 公共基座 `common`）；`adapters` 允许 import `llm`——标注流水线、
将来的 evaluator 共用同一 `LLMClient` + `Scheduler`。

**关于 `common/` 的说明**：公共基座（零项目依赖、无业务语义的基建：路径解析 /
环境变量 / `.env` / IO 基元）——唯一允许被**所有**模块 import 的叶子层，本身允许集为空。
路径根（`repo_root`/`data_root`/`repo_data_dir`/`research_root`）与 `.env` 解析的单一事实源都在这里；
禁止在其它模块重新自持实现（`tests/test_doc_lint.py` 单一来源闸盯防）。

## 模块分类（命名与依赖归属）

模块按职责分类，命名规则随之而定（星神名只给核心域；接入层目录用平实英文，内部组件
可挂泰坦名；公共基座用平实英文）：

| 分类 | 模块 | 职责 | 命名 |
|------|------|------|------|
| 公共基座 | `common/` | 路径 / 环境变量 / `.env` / IO 基元（无业务语义） | 平实英文（不做星神/泰坦命名） |
| 核心域 | `sim_schema/`、`sim/` | 仿真数据模型与战斗引擎 | 星神名（翁法罗斯）/ 引擎内部件泰坦名 |
| 研究域 | `research_schema/`、`research_protocol/`、`research_core/`、`research_permissions/` | 研究契约、固定实验协议、可信执行与证据报告、外部权限边界 | schema/permissions 平实英文；protocol/core 星神名（太一/克里珀） |
| 外部接入 | `pipeline/`、`account/`、`llm/`、`research_web/` | 各包一个外部系统（游戏数据 / 米游社 / LLM provider / 检索服务） | 目录平实英文；内部组件可挂泰坦名（如 llm=tribios） |
| Agent 接入 | `agents/` | DSH 外部进程、工具白名单与宿主复核 | 星神名（阿基维利） |
| 桥接 | `adapters/` | 外部数据 → sim_schema | 平实英文 |
| 应用编排 | `ops/` | 组合下层完成闭环 | 平实英文 |

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
uv pip install -e ".[dev,account,web,ops]"

# 仅安装核心 + dev
uv pip install -e ".[dev]"

# 全量回归（先准备数据、optimizer 与 Playwright）
bash scripts/setup_test_env.sh
.venv/bin/python -m pytest tests/ -q -rs

# 数据更新（统一入口——缺省三域全量：StarRailRes 中英 + tbgd 敌人五件 +
# theBowja 冻结备料 + Hakushin/buh 期数 + 机制数值 + Fandom 语义）
hsr-data update

# 增量更新（远端 ETag 快检只下变化；Fandom 爬虫默认跳过，--with-fandom 才跑）
hsr-data update --incr

# 单域更新（build=配装 / enemies=敌人 / stages=期数）
hsr-data update build

# 数据状态报告（本地版本 / 远端可更新 / 红线滤除——不写入）
hsr-data check

# 使用 SSH 下载（国内网络更快，需配置 GitHub SSH key）
hsr-data update --ssh

# 指定数据目录（另见 common/paths.py：HSR_NOUS_DATA_DIR 环境变量可全局覆盖）
hsr-data update --data-dir ./my_data

# 旧命令（过渡别名，一个版本后退役）
hsr-data-update [--lang cn] [--enemies|--enemies-tbgd|--stages|--mechanics] [--ssh]
```

## 代码约定

- **压缩优先（最高设计原则）**：面对新需求先问"能不能用现有件组合出来"——删/并/一般化永远优先于新增概念；新关键字/新字段/新原语必须证明现有件组合不出，且压缩收益显著（一个顶多个）。反面同样成立：**不许过度抽象**——泛化必须有实例垫底（扫描/数据证据），拒绝凭空设计。本项目的 DSL 哲学（闭合关键字集+开放命名空间、事件总线、结算原子化）都是此原则的实例
- **实现严格按文档设计**：`sim_schema/docs` 与 `docs/mechanics` 是 spec，代码不得静默偏离——确需偏离时**先改文档再写码**；发现的 doc-vs-code divergence 一律登记本地待办台账过堂。执行三层：能"代码直接消费 spec"的一律做成消费（如公式=表达式数据，divergence 构造上不可能）；不能直接消费的挂 lint 闸（先例：模块边界闸/镜像公式闸）；存量靠台账逐项收官清算
- 类型注解尽量完整
- pipeline 中的 CLI 函数使用 `main() -> int` 签名，`raise SystemExit(main())` 模式
- 测试放在 `tests/` 下，与 `src/` 目录结构对应
- 实际数据文件放在 `data/`（gitignored），模型代码放在 `src/`
- **易变数字三原则**：文档/注释不写会过期的精确计数（文件数/行数/章节数/闸数）——规模修饰用模糊量词（十余个/约两千/20+），能算的让工具现场算，承载信息的枚举（对照表/清单）与所指物同文件就近维护
- **单一来源三层**：每个事实只住一处（规则=rulebook/模板、词表=词表文件、待办=台账、案例=fixture 头注——漂移的第一成因是同一事实写两份）；**能从源机械派生的一律派生**，不维护第二份（白名单由实现表构造、公式=表达式数据、清单从台账现算——「实现严格按文档设计」执行三层同旨）；**不能派生的重复必须挂闸**（文档镜像/索引/边界表，即下条防腐原则）
- **防腐原则**：上层文档不重复下层事实——能删就删（只指路）；必须重复就让 `tests/test_doc_lint.py` 的闸保证一致，改被检对象时同步闸门配置；已有闸：索引（README↔磁盘）、模块边界（AGENTS.md 表↔实际 import）、镜像公式、§引用等，详见 `tests/README.md`
- **共享源必验**：多处共用的映射表/清单/词表，本身必须有核对手段（与消费它的代码对照、与官方数据对照、拿真实例子跑一遍验证）——只放一处只能保证"不改出两个版本"，保证不了"那一份本身没写错"（HealRatioBase 病例：生成器与校验器共用同一张错表，自洽地错遍全链）
- **提交前全量回归必绿**：所有地方从同一处读规则（rulebook/词表/fixture），改错一行则所有地方一起错——每次提交前按 `tests/README.md` 准备环境并跑全量回归，必绿是硬性规矩，不是可选项
- **commit 信息自解释**：提交信息必须脱离私有上下文可读（读者 = 第一次 clone 仓库的人）——信息中任何引用都必须能在本仓库或公开网络上找到；**禁止**引用只存在于本机或聊天上下文中的文档、清单、编号与内部称谓；黑话写人话（"flaky"→"偶发失败/时序不稳定"、"parity"→"对拍"）。依据指向仓库内文件（tests/docs）或公开来源（fandom/Prydwen/hsr-optimizer 等）；内部决策留痕归本地文档，不进提交信息
- **模板格式**：角色/光锥/遗器/敌人/关卡机制用 per-entity DSL YAML 模板描述（正典在 `data/library/**`（手写全机制，tracked），生成骨架在 `data/sim_templates/**`（adapters 生成，gitignored）——运行时查找链正典优先、生成兜底），`build.yaml` / `stage.yaml` 保持 YAML（纯数据声明）；命途专属体系单位（阿哈时刻族）用**命途系统模块**描述（`data/library/system/paths/<path>.yaml`——手写机制声明，入版本；模板 import 机制 auto-import 按成员命途注入，合并语义见 `sim_schema/docs/00_overview.md` 数据流章）
- **命名两态原则**：入库的角色/技能/光锥名只有两种合法状态——官方名（先经 query-game-data 查数据）或明显假名（"测试员/假人"），不许存在"听起来像真的"的中间态（脑补名是幻觉温床）
- **同人物多实体必须消歧**：SP 角色（姬子•启行≠姬子、丹恒•饮月/丹恒•腾荒≠丹恒、三月七 1001/1224 同名两实体、停云≠忘归人、刃≠千冶•刃、开拓者按命途写如"开拓者•欢愉"）引用机制时必须全称或带 ID，不得简称；间隔号 • 不必然是 SP 标记——**判断依据是是否存在同人物另一实体**：千冶•刃（1507）有刃（1205）→ 是 SP；阮•梅（1303）无另一实体 → • 是名字本体，别误"纠正"；query skill 对同名查询报歧义+列候选
- **外部输入核查三关**：外部评审/社区结论/wiki 的**事实主张**（"X 未定义/Y 不存在"）采纳前必须过三关——① 查文档原文（真的没写吗）② 查实现现状（真的没做吗）③ 查亲历证据（我们自己踩过吗）；三关全过才采纳。纯审美判断（优雅/高级）当共鸣不当依据；越笃定的主张越要查。（教训：2026-08-22 外部评审"accumulated×waterfall 无定义"被 §23.4 文档自身第 148 行证伪——评审没读到，我们差点跟风立错规则）
- **后台进程纪律**：agent 起 dev 服务器（`hsr-sim web` 等）一律用 run_in_background 任务（跨调用存活 + 可 TaskStop 收尸），**禁止**一次性 `bash -c '… &'` 起完就丢——服务器自带孤儿看护会秒杀这种孤儿（`--no-orphan-guard` 可关，详见 docs/usage.md）；发现存量孤儿跑 `scripts/kill_dev_servers.sh` 清扫。（教训：2026-09-07 单机清出 159 个孤儿 web 服务，整机负载主犯）
- **机制重建知识分层（证据来源五层）**：技能文本无法完整重建机制（2026-09 忆灵四件套/战技点勘正实证）。取数按层、**逐项标注证据来源**：① 官方文本+数值数据（地基——StarRailRes params/BPNeed；**中英对照**——EN 措辞纪律可解 CN 歧义："uses an ability 含终结技 / uses Skill 仅战技 / uses Skill and Ultimate 明示双类"，§4.8 事件契约在案）② wiki 交叉校验（fandom/米游社/BWIKI 对轴杀数据源偏差——fandom 类型兜底病灶在案）③ 社区操作向资料（米游社攻略/测评/实战——补交互语义大头：控制模型/自动施放/站位体感）④ **交互语义五项**（站位/能量条/控制模型/耗产点/目标选择）逐项标来源，文本查不到标**待实测**、不脑补（脑补=幻觉温床）⑤ 游戏内实测（云崩铁 webbridge）终审——冲突裁决序：实测 > 社区 > wiki 交叉 > 单一文本源。模板注释/e2e 数值按"官方文本/wiki/社区/实测/待实测"五级标源

## 数据查询

Coding agent 要查角色/光锥/遗器/敌人的机制、数值、中英文时，调用 `query-game-data` skill（**不要**直接读 `data/starrailres/index_new/cn/*.json`）：

```bash
python3 .agents/skills/query-game-data/query.py <entity_type> <query>
```

详见 `.agents/skills/query-game-data/SKILL.md`。
关键规则：

- 角色查询附带 `signature_light_cone_id`（**不**附带专光机制——专光机制要单独查）
- 光锥查询**不**返回装备该光锥的角色 ID
- 查不到时**先怀疑数据源过时**——`hsr-data-update` / `python -m hsr_nous.pipeline.build.semantic lightcones` 重跑后再报不存在

要查**游戏机制规则**（伤害公式 / 击破 / 战技点 / 行动序 / buff 叠加……）时，调用 `query-game-rules` skill——agent 自己 `Read` `docs/mechanics/*.md` + `docs/game_rules.md`，找不到再用 `WebFetch` 兜底（Fandom / 米游社）。详见 `.agents/skills/query-game-rules/SKILL.md`。
- 查不到时返回 `_error` + `_hint`，**不要脑补数据**
- 中英术语映射查 `terminology.yaml`

## 工程流程 skills

- **机制扫描**（角色技能 → 原语红绿灯矩阵，检验 schema 表达力）：`.agents/skills/mechanics-scan/`，开新扫描轮次、补扫新角色、对比两轮结果时用
- **一致性审计**（规则文档 vs schema 文档四层核对）：`.agents/skills/consistency-audit/`，成批改文档、接新数据源、版本更新后用
- **打标 DAG 批量调度**：`scripts/annotator.sh batch [--kind character|light_cone|relic] [--ids|--limit|--include-anchors|--workers N]`（ops/annotator——单实体 DAG：data_pull→crosscheck→社区层→evidence→draft→compile/smoke/golden_diff 三闸内环→oracle_report→finalize；角色版金样对拍=白值/path canonical/技能 id 集/scaling 全表对官方数据锚机械闸；oracle_report=对拍报告型闸（ops/annotator/oracle_report.py——hook 逻辑层数值神谕：模板 actions 核心三件套自动铺场景 vs hsr-optimizer kind=character driver，假人 lvl80/def1000/匹配弱点/未击破，比值口径对方/我方、阈值可配，报告落 runs_root/<cid>/oracle_report.json + staging notes 挂「对拍异常数」；异常不打回不阻塞，对方未覆盖/缺 node 降级 pass-through）；装备分支（光锥/遗器，equipment_nodes）链形同构——draft LLM 只产 hooks 块、数值区机械合并自生成器草稿（杜绝面板幻觉），金样=白值/叠影行/2pc 属性对数据锚，drift 指路重跑生成器；runs_root/<kind>s/<id>/ 断点续跑（角色在 runs_root/<cid>/），汇总 `_batch_summary{,_kind}.json`；staging 候选包合并走人工闸；--workers=多实体外层并行（热更：`~/.config/hsr_nous/annotator_live_config.json` 的 `batch_workers` 键——运行中调档免重启，升档补位/降档排干），宽度受 LLM 客户端 key 并发帽统一限流）
- 日常小改动只需跑文档 lint：`pytest tests/test_doc_lint.py -v`（详见 `tests/README.md`）

> skill 真身统一放 `.agents/skills/`（Kimi Code Project 域自动扫描）；`.claude/skills/` 内每个条目都是指向前者的软链接（Claude Code 官方支持的兼容入口）。改 skill 只改 `.agents/skills/`。

## 关键设计决策

1. **为什么用 `src/` layout**：避免运行时代码与测试代码路径冲突，支持 `pip install -e .` 正确安装。
2. **为什么 pipeline 要独立**：外部数据源（StarRailRes）的格式可能变化，pipeline 改动不应影响 sim。
3. **为什么用 `adapters` 而不是让 sim 直接读外部数据**：让 sim 专注于仿真逻辑；外部数据经 adapters 生成 per-entity DSL YAML 模板（生成骨架落 `data/sim_templates/**`，过堂后全机制正典归 `data/library/**`），sim 只消费模板编译产物（`CompiledEncounter`），不认识数据源 schema。
4. **为什么保留 `scripts/` 目录**：未来放真正的一次性运维脚本，pipeline 代码已迁移到 `src/hsr_nous/pipeline/`。
5. **策略设计**：策略以 build.yaml 的 `policy` dict 声明（action_rules / target_rules + 可调参数，结构 spec 见 `sim_schema/docs/14_policy.md`），经 `sim.compile` `_compile_policy` 编译为 `CompiledPolicy`，运行时由 `CompiledPolicyRuntime` / `ScriptedPolicy`（`sim/policy_api.py`）执行；v1 `sim_schema/policy.py` dataclass（Policy/PolicyRule/TargetRule）已退役删除；战前策略（秘技顺序）见 `sim_schema/docs/20_pre_battle_strategy.md`。

## 扩展方向

- 添加新数据源：在 `pipeline/` 新增 loader，经 adapters 生成 per-entity DSL 模板
- 扩展仿真机制：只在 `sim_schema/` 和 `sim/` 中修改
- 策略优化：调整 build.yaml 的 `policy` 规则与参数，经编译由 `CompiledPolicyRuntime` 执行

## 数据来源

| 数据 | 来源 | 本地路径 |
|------|------|----------|
| 角色/光锥/遗器等 | [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes) | `data/starrailres/index_new/{lang}/` |
| 敌人基础数值 | [Dimbreath/turnbasedgamedata](https://gitlab.com/Dimbreath/turnbasedgamedata)（GitLab 官方配置表镜像，五件：Monster/Template/Skill/EliteGroup/HardLevelGroup——**enemies 域数值权威**，与 hakushin 公式链全量对拍一致在案），下载 `hsr-data-update --enemies-tbgd`，查询 `pipeline/enemies/loader.py` | `data/turnbasedgamedata/` |
| 敌人基础数值（冻结保留） | Hakushin monstervalue（单文件全怪 base 值 + 修正系数，随 `--stages` 更新——与 tbgd 全等，P3 切源后冻结） | `data/stages/hakushin/monstervalue.json` |
| 敌人技能/抗性 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom）Enemy 模板，提取脚本 `pipeline/enemies/semantic.py`（语义补充——数值权威为 turnbasedgamedata） | `data/fandom_enemy_data.json` |
| 敌人数据（遗留） | [theBowja/starrail-data](https://github.com/theBowja/starrail-data)——**断更于 3.2（上游 DimBreath 2024-10 被 DMCA），降级为遗留源** | `data/enemies/enemies.json` |
| 技能机制数据 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom） | `data/fandom_skill_data.json` |
| 技能机制数值（战技点耗产/基础回能/削韧，逐技能权威源） | [Dimbreath/turnbasedgamedata](https://gitlab.com/Dimbreath/turnbasedgamedata)（GitLab 官方配置表镜像，项目内缩写 `tbgd`——fixture 注释的「tbgd 权威/以 tbgd 为准」即以本数据源为准），提取脚本 `pipeline/extract_tbgd_skills.py` | `data/tbgd_skill_data.json` |
| 技能机制五项（类型/能量上限/削韧/回能/战技点）【已归档·停爬】 | [米游社·开拓者笔记](https://bbs.mihoyo.com/sr/wiki/)（官方 WIKI 静态 CDN 接口），提取脚本 `pipeline/extract_miyoushe_skills.py`（社区口径质量参差，仅留作 crosscheck 可选校验列） | `data/miyoushe_skill_data.json`（缓存 `data/miyoushe/cache/`） |
| 关卡编成（深渊） | [Hakushin API](https://static.nanoka.cc)（hakush.in 数据后端） | `data/stages/hakushin/` |
| 关卡编成（含异相仲裁） | [buhflipexplode-src](https://github.com/spiritfxxxx/buhflipexplode-src) | `data/stages/buhflipexplode/` |

StarRailRes 提供倍率等基础数据，Fandom wiki 补充削韧值、回能值、战技点消耗等机制数值。提取脚本：`pipeline/build/semantic.py`（skills/lightcones 子命令，P1 由 extract_fandom_skills/lightcones 合并）。米游社官方 WIKI（`pipeline/extract_miyoushe_skills.py`）曾提供逐技能五项标签，因社区口径质量参差**已归档停爬**——存量文件仅留作 crosscheck 可选校验列（缺失自动跳过），战技点等数值以 turnbasedgamedata 为权威源；Fandom 的 SP 值为类型规则合成（provenance 见各自数据文件）。

> **红线：只接入已正式上线版本的数据**——未发布内容不拉、不存、不发布；`hsr-data-update` 只在版本正式更新后运行。红线适用于**所有**数据源——期数类源（stages）按内容过滤，版本追踪类源（StarRailRes/theBowja）以 Hakushin 已上线花名册做版本对齐校验（warn-only，神谕仅作绊线，官方公告为终审），实现见 `pipeline/redline.py`。
