# agents

外部 Agent harness 适配层。headless 单次调用之外新增交互式原型（DSH web 面与
ACP 聊天桥）；不包含自研 Agent loop 或共享 Memory。

## 准备

```bash
bash scripts/setup_agent_env.sh
```

脚本把固定版本的 `@deepseek-ai/dsh` 安装到 gitignored 的 `external/dsh/`，不全局安装、不修改现有 `~/.dsh`。完整测试环境 `scripts/setup_test_env.sh` 也会执行这一步。可用 `HSR_NOUS_DSH_BIN` 指定另一个 DSH 可执行文件。

## 运行一个研究契约

```bash
hsr-research-agent /path/to/contract.json --research-root /path/to/research
```

研究根默认由 `HSR_NOUS_RESEARCH_ROOT` 决定，缺省为 `~/HSR_Nous`，必须独立于源码仓库。DSH 的 `HOME`、`DSH_HOME` 使用该根下的隔离目录；cwd 是源码仓库以读取项目 `.env`，沙箱工作区和研究产物仍归研究根。

模型配置从仓库根 `.env.example` 复制到 `.env`，填写三项：

```dotenv
HSR_NOUS_LLM_AGENTS_API_KEY=
HSR_NOUS_LLM_AGENTS_MODEL=
HSR_NOUS_LLM_AGENTS_API_BASE=
```

DSH 启动时自行读取 `.env`；启动器只检查文件是否存在以选择 OpenAI 兼容 profile，不读取或打印其中的值。也可通过 `--allow-model-env` 显式传入同名环境变量。`.env` 已被 gitignore，应使用独立测试凭据且权限设为 600。

## 交互式原型（DSH web）

```bash
hsr-research-chat              # 起服务（默认 8002 端口，仅回环绑定）
hsr-research-chat --port 8080  # 换端口
```

启动后打印 `dsh web:` 令牌化 URL——**即访问凭证，注意保密**。远程开发场景（如 VS Code Remote 端口转发）在本地浏览器打开时把 host 换成本地 `localhost`；经反代暴露需要 `--trusted-host` 另配，不在本原型范围。

与 headless 同一信任边界：内置工具全禁、只读沙箱、仅 `mcp__nous__*` 白名单工具可用，人直接在浏览器里驱动多轮研究会话（提案→执行→复核）。会话状态在 DSH 自己的隔离 `dsh-home` 下，研究产物仍归研究根。

stock web 定位自此降级为 **capability matrix 试验台**（AUTORESEARCH_DESIGN §16 要求的"DSH 开始接入前一页 capability matrix"）：DSH 自带 UI 的呈现行为在那里观察，生产聊天路径走下面的 ACP 桥。

## ACP 桥（--serve）

```bash
hsr-research-chat --serve                # 起桥（默认 8003 端口，仅回环绑定）
hsr-research-chat --serve --port 8080
```

架构：

```
浏览器（vanilla JS 原型页，内嵌于 chat_server）
  ↔ POST 下发 / SSE 推送（EventSource，sse-starlette）
  ↔ chat_server（FastAPI，一个 app 持一个 AcpClient）
  ↔ AcpClient（asyncio，换行分隔 JSON-RPC over stdio，见 acp_client.py）
  ↔ dsh --profile acp（叠加 research/openai 两补丁，nous MCP 网关挂在内）
```

人在我们自己的页面聊天，DSH 完全退到幕后；一个 AcpClient = 一个 dsh 子进程
（内含多会话），POST /sessions 建会话、POST .../prompt 下发（202）、
GET .../events 推 `session/update` 流、POST .../cancel 取消、GET /sessions 列表。

协议事实（2026-10-22 实测探针，dsh 0.2.1-rc.2，细节见 acp_client.py docstring）：

- `initialize` 协商 ACP v1；dsh 的 `authMethods` 恒为空，无需认证。
- `session/new` 返回 `configOptions`（model/reasoning_effort 透明选择器）；
  **默认模型是目录首个路由而非 `agent-default-model` 补丁**——桥在建会话后显式
  `session/set_config_option` 把 model 钉到 `openai-gateway` 组（.env 端点）。
- `session/list` 只列已关闭（可恢复）会话；活动会话由本桥本地记账。
- prompt 的 settlement 等全部 `session/update` 排干——客户端读循环独立成 task，
  在途期间照常把 update 扇入订阅流（结算后发本地 `prompt_closed` 事件关"在途"态）。
- nous MCP 工具注册是**异步**的（实测数秒）：首个 prompt 可能早于
  `mcp__nous__*` 工具就绪，重试即可；测试用 mock 门控轮询规避。
- 错误形态：JSON-RPC error（-32601/-32602/-32603）映射为中文报错的
  `AcpProtocolError`；进程退出/管道断映射为 `AcpConnectionError`。

SSE/WS 选型注记（§16 待决项"main agent 与前端之间最终采用 SSE、WebSocket 还是
其他事件通道"的原型数据点）：update 流是单向、低频率（消息块/工具生命周期/
上下文用量）、允许断线重连（桥带 200 条环形历史重放），SSE + POST 已够；
websockets 库未装而 sse-starlette 已在依赖内，不引新依赖。若将来需要客户端
高频上行或多路复用单连接，再评估 WS 升级。

## 可信边界

- DSH 只能调用 `mcp__nous__submit_claim/read_investigation/read_report/resolve_evidence/submit_candidate_set/submit_candidate_proposals/start_candidate_set/start_candidate_proposals/read_candidate_task/wait_candidate_task/cancel_candidate_task/resume_candidate_task/read_candidate_set_report`；配置禁用与插件 guard 同时拒绝其他工具。
- 多候选输入使用 `hsr-research-agent --candidate-set /path/to/candidates.json`，候选集的 dev 排名、holdout 修正和 selected 都由后端计算。
- 候选任务附加 `--background` 后立即返回 task_id，不等待最终报告；可通过 MCP 查询进度与部分结果、等待完成通知、取消或恢复。
- 自然语言候选生成使用 `hsr-research-agent --candidate-proposals /path/to/space.json`。模型只提交 CandidateSpace 白名单内的 path/value 提案，宿主按实际提案重建候选集并复核报告。
- Bash、Pwsh、FS、workflow、subagent、内置 web、jobs、会话日志上传和 OTel 均关闭。
- `submit_claim` 进入现有 `ResearchGateway`，统计和报告只能由模拟证据及可信内核产生。
- 宿主先登记预期 contract，DSH 完成后核对唯一预期调用及其成功 tool_result，再重新读取 investigation 并独立复核报告。Agent 的自然语言文本标记为 untrusted，不能替代完成态 investigation 或可信报告。
- 跨 JavaScript 进程提交契约或提案时使用原样 JSON 字符串，避免 `600.0` 被改成 `600` 后产生不同内容身份。

具体协议见 [08_agent_bridge.md](../research/schema/docs/08_agent_bridge.md)。

## 限制

局部 npm 安装、独立 HOME 和工具白名单不等于 OS 级安全沙箱；DSH 与 MCP 仍是本机进程。交互式原型为人工看护场景：Agent 的每次工具调用与提交都在网关白名单内，但成本与误用风险由使用者自负（模型按 token 计费）。开放式多候选搜索与真实模型 CI 仍不支持。标准测试使用回环地址上的隔离 Messages 服务；真实模型 smoke 已另行使用独立凭据验证，不进入 CI。
