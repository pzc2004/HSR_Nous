# common/ 公共基座

零项目依赖、无业务语义的基建层（路径 / 环境变量 / `.env` / IO 基元）。

## 准入规则（硬约束）

1. **不 import 任何其它 `hsr_nous.*`**（只标准库；第三方依赖由消费方自持）——
   本层是全项目依赖图的叶子，任何反向边都会制造环。
2. **其它所有模块都允许 import 本层**：这是唯一"人人可依赖"的公共层
   （AGENTS.md「模块边界」表 + doc_lint 边界闸双向校验）。
3. **只放无业务语义的基建**。判断标准：
   - 与具体游戏/仿真/LLM/账号语义无关（`data/library`、模板根链这类概念不进来）；
   - 多个模块真的都要用（泛化必须有实例垫底，不为假想复用新增 API）。
4. **不出 import 期冻结的路径常量**：路径一律走函数（调用时解析），否则
   `HSR_NOUS_DATA_DIR` 覆盖会被 import 顺序架空。

## 模块

| 文件 | 内容 |
|---|---|
| `paths.py` | `repo_root()` / `repo_data_dir()` / `data_root()` / `DATA_DIR_ENV`——路径唯一事实源（数据根 env 覆盖语义在此） |
| `env.py` | `parse_env_file()`（纯函数）/ `load_dotenv()`（setdefault 写入）/ `load_repo_env()`——手写 `.env` 解析 |
| `__init__.py` | 公开 API 汇总 |

## 与相邻层的区别

- **不是**外部接入层：不跟任何外部系统/协议/OS 交互（pipeline/account/llm/screen/pilot 才是）；
- **不是**核心域：不承载仿真/数据模型语义（sim_schema/sim 才是）；
- 消费方：`pipeline`（数据根）、`sim_schema`（模板根）、`sim`（版本指纹取 repo_root）、
  `llm` / `account`（.env 与仓库根）——将来任何模块需要路径或环境变量都从这里取。

## 测试

一致性由单一来源闸守着（`tests/test_doc_lint.py`：全库扫描禁止在 `common/` 之外
重新定义路径根/`.env` 解析，防止重复实现回潮）。
