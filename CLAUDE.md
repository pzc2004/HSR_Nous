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
│   ├── docs/      # 分章节数据格式设计（00_overview ~ 15_data_separation）
│   ├── examples/  # 示例输入（game_config / build / stage）
│   └── policy.py  # 策略 DSL 数据结构
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
| `adapters/` | `raw_schema`, `sim_schema`, `pipeline`（仅数据查询/计算） | `sim`（只输出 sim_schema，不调用仿真） |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents` |
| `agents/` | `adapters`, `sim`, `pipeline`（仅数据查询，与 data_tools 同模式） | `raw_schema`（通过 pipeline/adapters 间接使用） |
| `api/` | `agents`, `adapters`, `sim`, `pipeline`（仅编排元数据） | `raw_schema` |

**核心原则**：数据管道与 sim 解耦，中间通过 adapters 桥接。

**关于 `pipeline` 的放宽说明**：`pipeline/` 实际上是数据访问层（JSON 加载 + 属性计算），
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
- dataclasses（模型层）

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
- **表达式求值**：`sim_schema` 中的 `expression` 字段目前用占位 eval，后续需替换为安全表达式引擎

## 关键设计决策

1. **为什么用 `src/` layout**：避免运行时代码与测试代码路径冲突，支持 `pip install -e .` 正确安装。
2. **为什么 pipeline 要独立**：外部数据源（StarRailRes）的格式可能变化，pipeline 改动不应影响 sim。
3. **为什么用 `adapters` 而不是让 sim 直接读 raw**：让 sim 专注于仿真逻辑，不关心外部数据源 schema。
4. **为什么保留 `scripts/` 目录**：未来放真正的一次性运维脚本，pipeline 代码已迁移到 `src/hsr_nous/pipeline/`。
5. **策略 DSL 设计**：Rule-based + 参数化混合，LLM 生成结构，优化器调参数，模拟器稳定执行。

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
