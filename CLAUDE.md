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

## 项目结构速查

```
src/hsr_nous/
├── pipeline/      # 数据管道：从 StarRailRes 加载 JSON 数据 — 独立，不 import 其他模块
│   └── README.md  # pipeline 详细使用文档
├── raw_schema/    # 原始数据模型（StarRailRes schema）
├── sim_schema/    # 仿真器输入格式
│   ├── README.md  # 文档索引
│   ├── docs/      # 分章节数据格式设计（00_overview ~ 20_elation）
│   ├── examples/  # 示例输入（build / stage）
│   └── policy.py  # 策略数据结构
├── adapters/      # raw_schema → sim_schema 转换层
├── sim/           # 纯战斗模拟器（只认识 sim_schema）
│   └── engine.py  # 含 PolicyInterpreter
├── agents/        # ReAct 五 Agent
└── api/           # 编排器（Orchestrator）
```

## 模块边界（严格遵守）

| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `pipeline/` | 无 | `raw_schema`, `sim_schema`, `sim`, `agents`, `api` |
| `raw_schema/` | 无 | `sim_schema`, `sim`, `agents`, `api` |
| `adapters/` | `pipeline`, `raw_schema`, `sim_schema` | `sim`（只输出 sim_schema，不调用仿真） |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents` |
| `agents/` | `adapters`, `sim` | `pipeline`, `raw_schema`（通过 adapters 间接使用） |
| `api/` | `agents`, `adapters`, `sim` | `pipeline`, `raw_schema` |

**核心原则**：数据管道与 sim 解耦，中间通过 adapters 桥接。

## 技术栈

- Python >= 3.10
- `uv` 包管理 + `hatchling` 构建后端
- `pytest` 测试
- dataclasses（模型层，计划迁移至 Pydantic v2）

## 常用命令

```bash
# 安装（editable mode）
uv pip install -e ".[dev]"

# 测试
pytest tests/ -v

# 更新游戏数据（从 StarRailRes GitHub 拉取）
hsr-data-update

# 更新简体中文数据
hsr-data-update --lang cn

# 下载敌人数据（来源: theBowja/starrail-data）
hsr-data-update --enemies

# 使用 SSH 下载（国内网络更快，需配置 GitHub SSH key）
hsr-data-update --ssh

# 指定数据目录
hsr-data-update --data-dir ./my_data
```

## 代码约定

- 类型注解尽量完整
- pipeline 中的 CLI 函数使用 `main() -> int` 签名，`raise SystemExit(main())` 模式
- 测试放在 `tests/` 下，与 `src/` 目录结构对应
- 实际数据文件放在 `data/`（gitignored），模型代码放在 `src/`
- **模板格式**：角色/光锥/遗器/敌人/关卡机制用 per-entity DSL YAML 模板描述（`data/sim_templates/**/*.yaml`，由 adapters 生成），`build.yaml` / `stage.yaml` 保持 YAML（纯数据声明）

## 数据查询

Coding agent 要查角色/光锥/遗器/敌人的机制、数值、中英文时，调用 `query-game-data` skill（**不要**直接读 `data/starrailres/index_new/cn/*.json`）：

```bash
python3 .claude/skills/query-game-data/query.py <entity_type> <query>
```

详见 `.claude/skills/query-game-data/SKILL.md`。
关键规则：

- 角色查询附带 `signature_light_cone_id`（**不**附带专光机制——专光机制要单独查）
- 光锥查询**不**返回装备该光锥的角色 ID
- 查不到时**先怀疑数据源过时**——`hsr-data-update` / `extract_fandom_lightcones` 重跑后再报不存在

要查**游戏机制规则**（伤害公式 / 击破 / 战技点 / 行动序 / buff 叠加……）时，调用 `query-game-rules` skill——agent 自己 `Read` `docs/mechanics/*.md` + `docs/game_rules.md`，找不到再用 `WebFetch` 兜底（Fandom / 米游社）。详见 `.claude/skills/query-game-rules/SKILL.md`。
- 查不到时返回 `_error` + `_hint`，**不要脑补数据**
- 中英术语映射查 `terminology.yaml`

## 关键设计决策

1. **为什么用 `src/` layout**：避免运行时代码与测试代码路径冲突，支持 `pip install -e .` 正确安装。
2. **为什么 pipeline 要独立**：外部数据源（StarRailRes）的格式可能变化，pipeline 改动不应影响 sim。
3. **为什么用 `adapters` 而不是让 sim 直接读 raw**：让 sim 专注于仿真逻辑，不关心外部数据源 schema。
4. **为什么保留 `scripts/` 目录**：未来放真正的一次性运维脚本，pipeline 代码已迁移到 `src/hsr_nous/pipeline/`。
5. **策略设计**：`sim_schema/policy.py` 定义策略数据结构（action_rules / target_rules / timing_rules + 可调参数），优化器调参数，sim 引擎 interpret 执行；战前策略（秘技顺序）见 `sim_schema/docs/20_pre_battle_strategy.md`。

## 扩展方向

- 添加新数据源：在 `pipeline/` 新增 loader，输出到 `raw_schema/` 兼容格式
- 扩展仿真机制：只在 `sim_schema/` 和 `sim/` 中修改
- 新 Agent：在 `agents/` 中新增，通过 `api/orchestrator.py` 注册
- 策略优化：修改 `sim_schema/policy.py` 参数，通过 `PolicyInterpreter` 执行

## 数据来源

| 数据 | 来源 | 本地路径 |
|------|------|----------|
| 角色/光锥/遗器等 | [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes) | `data/starrailres/index_new/{lang}/` |
| 敌人数据 | [theBowja/starrail-data](https://github.com/theBowja/starrail-data) | `data/enemies/enemies.json` |
| 技能机制数据 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom） | `data/fandom_skill_data.json` |

StarRailRes 提供倍率等基础数据，Fandom wiki 补充削韧值、回能值、战技点消耗等机制数值。提取脚本：`pipeline/extract_fandom_skills.py`
