# 开发环境配置

本文面向新机器或新 clone，说明如何配置代码、测试数据、`external/` 依赖和可选 Agent 服务。产品命令的使用方法见 [usage.md](usage.md)。

版本号、固定提交和下载地址不在本文重复维护，唯一事实源见文末「配置事实源」。

## 1. 按目标选择配置范围

| 目标 | 所需配置 |
|---|---|
| 只改代码、跑文档 lint 或纯单元测试 | Python/uv + `dev` 依赖 |
| 跑完整测试 | 执行 `scripts/setup_test_env.sh` |
| 使用网页调试台或研究台 | 完整测试环境 + `web` 依赖 |
| 使用真实 Agent 聊天或 DSH | DSH + `HSR_NOUS_LLM_AGENTS_*` 配置 |
| 使用打标 DAG | `ops` 依赖 + `HSR_NOUS_LLM_ANNOTATOR_*` 配置 |
| 阅读第三方参考实现 | 按需单独获取，不是模拟器或测试的前置条件 |

## 2. 系统前置条件

准备以下命令并加入 `PATH`：

- Python >= 3.10；
- `uv`：所有 Python 环境创建和包安装都必须使用 `uv`，不要使用 `pip install` 或 `conda`；
- `git`、`curl`、`tar`；
- Node.js 与 npm。

完整测试还需要访问 GitHub Release、npm registry 和 Playwright 下载源。CI 会用 Playwright 的系统依赖安装选项；在精简 Linux 环境本地安装浏览器失败时，可执行：

```bash
.venv/bin/playwright install --with-deps chromium
```

该命令可能安装系统包；需要 sudo 时由操作者自行确认，不由项目脚本静默提权。

## 3. 最小开发环境

```bash
git clone git@github.com:pzc2004/HSR_Nous.git
cd HSR_Nous
uv venv
uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/test_doc_lint.py -q
```

只装核心和 `dev` 时，不需要 `data/`、optimizer、DSH 或浏览器。

项目可选依赖按用途拆分，具体清单以 `pyproject.toml` 为准：

| extra | 用途 |
|---|---|
| `dev` | pytest |
| `account` | 米游社账号集成 |
| `web` | FastAPI 网页调试台与研究台 |
| `ops` | 打标流水线的社区搜索 |
| `agent` | MCP 与 Agent 接入 |

例如只补网页和 Agent 能力：

```bash
uv pip install -e ".[dev,web,agent]"
```

## 4. 完整测试环境

统一入口：

```bash
bash scripts/setup_test_env.sh
```

脚本会完成以下工作：

1. 创建 `.venv` 并安装项目及测试所需 extras；
2. 检查关键数据文件，缺失或要求刷新时从 GitHub Release 恢复固定数据快照；
3. 重新生成 `data/sim_templates/`，必要时补齐技能机制提取产物；
4. 获取并固定 `external/hsr-optimizer`，安装其 npm 依赖；
5. 通过 `scripts/setup_agent_env.sh` 在 `external/dsh` 安装固定版本 DSH；
6. 安装 Playwright 与 Chromium。

脚本可重复执行。本地已有完整数据时默认复用；需要强制恢复当前 pinned 快照时：

```bash
TEST_ENV_REFRESH_DATA=1 bash scripts/setup_test_env.sh
```

CI 每次都会恢复快照，并使用带系统依赖的 Playwright 安装方式。不要在普通本地开发中随意设置 `CI=true`，否则会改变数据刷新和浏览器安装行为。

准备完成后运行：

```bash
.venv/bin/python -m pytest tests/ -q -rs
```

缺依赖导致的 skip 是环境诊断信息，应先检查环境，不要直接把它当作完整回归通过。

## 5. 数据目录与更新方式

### 测试快照与日常更新不是一回事

- **可复现测试**：`scripts/setup_test_env.sh` 使用 `pipeline/pins.py` 指定的 Release 快照；
- **日常游戏版本更新**：使用 `hsr-data update`，只接入已正式上线的数据；
- **检查本地版本和可更新状态**：使用 `hsr-data check`，只报告，不写入。

常用日常命令：

```bash
hsr-data update          # 全量更新
hsr-data update --incr   # 增量快检
hsr-data update build    # 只更新配装域
hsr-data update --ssh    # 使用 SSH 下载
hsr-data check           # 只读状态报告
```

`hsr-data-update` 是旧命令的过渡别名，新文档和脚本优先使用 `hsr-data`。

### 自定义数据根

默认缓存级数据位于仓库 `data/`，可用环境变量覆盖：

```bash
export HSR_NOUS_DATA_DIR=/path/to/hsr-data
```

`data/library` 的手写机制正典和 `data/battles` 的策展对局属于仓库内容，不随该变量移动。可下载数据、提取产物和 `data/sim_templates` 等缓存级内容才随数据根移动。

研究产物与游戏数据分开存放，默认不写入仓库：

```text
HSR_NOUS_RESEARCH_ROOT
  > XDG_DATA_HOME/hsr_nous
  > ~/.local/share/hsr_nous
```

可显式指定：

```bash
export HSR_NOUS_RESEARCH_ROOT=/path/to/research
```

`setup_test_env.sh` 会写 `data/sim_templates/`。多个环境共享同一个数据根时，应协调生成任务；更简单的做法是让各开发环境使用独立数据根。

## 6. `external/` 依赖

| 内容 | 获取方式 | 是否必需 |
|---|---|---|
| `external/hsr-optimizer` | `setup_test_env.sh` 自动 clone、固定提交并安装 npm 依赖 | 完整测试与对拍需要 |
| `external/dsh` | `setup_agent_env.sh` 安装固定版本，不修改用户既有 DSH_HOME | Agent 功能与相关测试需要 |
| 其他研究仓库、论文与归档 | 按 `external_references.md` 单独获取 | 仅研究参考，按需 |

不要把“`external/` 中缺少某个研究 clone”误认为模拟器或测试环境不完整。必需依赖由脚本管理，其他 clone 只用于语义互证。

## 7. 可选 LLM 与 Agent 配置

安装 DSH 不等于已经配置模型服务。真实 Agent 聊天需要在仓库根 `.env` 中按 `.env.example` 配置：

```text
HSR_NOUS_LLM_AGENTS_API_BASE
HSR_NOUS_LLM_AGENTS_API_KEY
HSR_NOUS_LLM_AGENTS_MODEL
```

`.env.example` 只提供空值和说明，真实凭据不得写入 Git、测试 fixture、日志或提交信息。聊天桥显示未启用时，先检查这三项和 `external/dsh/node_modules/.bin/dsh` 是否存在。

打标 DAG 使用独立的 `HSR_NOUS_LLM_ANNOTATOR_*` 配置组；米游社账号集成的凭证方式见 `integrations.md`。不同用途的变量不要混用。

## 8. 常见问题

- **测试出现缺依赖 skip**：先重跑 `scripts/setup_test_env.sh`，再检查输出中的具体缺失项。
- **数据与当前编译器不兼容**：先尝试 `TEST_ENV_REFRESH_DATA=1 bash scripts/setup_test_env.sh`，不要直接修改缓存 JSON。
- **`external/hsr-optimizer` 已存在但不是 Git 仓库**：脚本会停止以避免覆盖；先人工移走该目录，再重跑。
- **浏览器无法启动**：检查 Playwright 和 Chromium 是否安装；精简 Linux 系统可能还缺系统库。
- **聊天桥未启用**：检查 Agent 三个必填变量和 DSH 安装，不要把它当成研究台 API 故障。
- **只需要参考实现**：按 `external_references.md` 获取对应仓库，不必先安装全部研究 clone。

## 配置事实源

| 内容 | 唯一事实源 |
|---|---|
| Python extras 与 CLI 入口 | `pyproject.toml` |
| 完整测试环境步骤 | `scripts/setup_test_env.sh` |
| DSH 版本与安装方式 | `scripts/setup_agent_env.sh` |
| 数据快照仓库、标签与资产名 | `src/hsr_nous/pipeline/pins.py` |
| 数据根与研究产物根 | `src/hsr_nous/common/paths.py` |
| 测试组织与运行方式 | `tests/README.md` |
| 可选研究参考 | `docs/external_references.md` |
| LLM 变量说明 | `.env.example` |
