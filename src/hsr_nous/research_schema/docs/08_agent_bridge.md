# Agent Bridge：DSH 与 MCP

本章描述当前已经落地的 DSH headless → MCP → ResearchGateway 接入。ACP、交互式前端、共享 Memory 和多候选搜索仍不在当前实现内。

## 数据流与信任归属

```text
ResearchContract（宿主登记预期身份）
    ↓
agents.cli → agents.dsh（隔离外部进程）
    ↓
DSH headless + 工具白名单
    ↓
MCP stdio → ResearchGateway
    ↓
固定协议 / 模拟 / 不可变 artifact / 独立 claim 复核
    ↓
宿主重新读取预期 investigation，返回真实报告
```

DSH 的自然语言最终文本不是 claim，也不能替代完成态 investigation。宿主在运行前创建或读取预期 investigation，运行后要求它完成并具有 trial_id，再核对本次 DSH 只有一次预期 `contract_json` 的 submit_claim 调用且具有成功 tool_result，最后经 `submit_claim(trial_id=...)` 独立复核。已经完成的 contract 不能被宿主冒充为一次新的 Agent 执行；仅有旧完成状态或其他实验也不能通过本次关联检查。

## MCP 工具面

`research_permissions.mcp` 只注册四个工具，DSH 中的名字为 `mcp__nous__<name>`。

| 工具 | 输入 | 行为 |
|---|---|---|
| `submit_claim` | 五类输入任选且只能选一项：`contract`、`contract_json`、`trial_id`、`claim`、`claim_json` | 复用唯一结论提交通道，不接受独立 metrics/samples/effect/CI 数字 |
| `read_investigation` | `investigation_id` | 读取持久化生命周期状态 |
| `read_report` | `trial_id` + `report_id` | 重读并校验报告身份与归属 |
| `resolve_evidence` | 一个 `EvidenceLink` | 下钻到 run/event/final modifier；递归只读对象经 canonical JSON 转为线协议值 |

`contract` 和 `claim` 使用对象输入。跨 JavaScript 进程时优先使用 `contract_json` 和 `claim_json` 的原样 JSON 字符串：JavaScript 可能把 `600.0` 规范化为 `600`，如果直接传对象，同一实验会因数字表示变化获得不同内容身份。字符串由 Python 端 `json.loads` 后再经严格 `ResearchContract.from_dict` / `Claim.from_dict` 校验，不绕过任何协议检查。

这两个字符串字段在 MCP 函数签名中是纯 `str`，以空字符串表示未提供，不是 `str | None`。当前官方 Python MCP SDK 会预解析非纯 `str` 字段中的 JSON 文本；保持纯 `str` 注解可防止契约字符串在函数调用前被提前变成对象。五类输入的互斥校验仍然生效。

MCP 不暴露 `publish_run/publish_claim/publish_report`、任意路径读写、Bash、Python、Docker 或联网工具。`open_research_gateway()` 是 MCP 与宿主 CLI 共用的构造入口，默认策略保持联网关闭。

## DSH 进程与配置

`agents.dsh.run_headless` 用参数数组启动 `dsh --profile headless --patch <research.cordis.yml> --json`，任务经 stdin 传入，不使用 shell。研究根必须独立于仓库；`HOME`、`DSH_HOME` 和 cwd 都指向该根下的隔离目录，不继承用户现有 `~/.dsh`。

`research.cordis.yml` 配置 stdio MCP，启动当前 Python 环境的 `hsr_nous.research_permissions.mcp`，并设置 `failOnStartupError: true` 和覆盖实验执行的调用超时。`research_policy.mjs` 用 `ctx.tools.guard()` 对四个 MCP 工具做最终允许名单；其他名字一律拒绝。配置还关闭 Bash/Pwsh、FS、workflow、subagent、内置 web、jobs、会话日志上传和 OTel。

默认环境不携带模型密钥。只有调用方显式提供 `model_env`，或 CLI 使用 `--allow-model-env` 时，`DEEPSEEK_API_KEY` 与可选 `DEEPSEEK_BASE_URL` 才进入 DSH 环境。DSH 的 MCP 子进程环境会清除这类密钥，MCP 配置只显式补充研究根和 Python 路径。CLI 不读取仓库 `.env`，也不把密钥写入报告。

DSH 的 `--json` 事件流用于进程诊断和工具调用关联，其中的 `tool_result` 可能被截断；它不作为完整报告载体。可信报告始终由宿主从 artifact 重新读取并复核。

## 验收与当前边界

测试分为三层：

- MCP stdio client 真实调用：工具清单、完整模拟、报告、事件下钻、伪造 claim 拒绝；
- 假 DSH 可执行文件与 Node guard 测试：argv/stdin/cwd/env、超时清理、非零退出和白名单；
- 真实 DSH + 回环 Messages 服务 + 真实 MCP + 真实模拟：模型请求只发往 `127.0.0.1` 的隔离服务，使用测试占位密钥，不访问真实 DeepSeek API 或用户凭据。

因此当前已验证的是 DSH、MCP 与模拟后端的实际端到端链路，不是 DeepSeek 真实模型的指令遵循能力。真实模型仍需使用独立测试凭据另行验收。

局部 npm 安装、独立 HOME、进程组和工具白名单不构成针对同用户恶意进程的强安全沙箱。当前也没有异步 worker、ACP、多轮前端、共享 Memory 或真实游戏校准；这些能力不得从本章推断。
