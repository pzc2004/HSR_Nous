# research_permissions

外部研究权限策略与唯一结论提交通道。本包只依赖 `research_core`、`research_schema`、`research_protocol`、`research_web` 和 `common`，这些下层模块不得反向依赖本包。

## 当前能力

- `CapabilityPolicy`：不可变策略，默认仓库/artifact 只读、项目目录可写、允许模拟和 submit_claim，联网/Bash/Python/Docker 全禁。
- `ResearchGateway`：薄封装调查生命周期，逐项检查权限，不暴露 publish_run/publish_claim/publish_report；`open_research_gateway()` 统一 MCP 与宿主 CLI 的构造。
- `submit_claim`：只接受 contract、trial_id 或 claim 之一，拒绝 metrics/samples/effect/CI 等调用方数字；MCP 另提供原样 JSON 字符串形式以保持跨 JavaScript 数字语义。
- `submit_candidate_set` / `read_candidate_set_report` / `validate_candidate_set_report`：有界候选集执行、读取与独立复核；不能由调用方指定 selected、效应值或 CI。
- `submit_candidate_proposals` / `validate_candidate_proposals_report`：将白名单提案确定性转为候选集，复用同一执行与复核通道；宿主按实际工具提案重建预期身份。
- `start_candidate_set/proposals`、`read_candidate_task`、`wait_candidate_task`、`cancel_candidate_task`、`resume_candidate_task`：独立后台任务、进度与部分结果、取消恢复和持久通知；同步 submit 保留为 start + wait 兼容包装。
- `mcp.py`：stdio MCP 传输，开放 submit_claim、read_investigation、read_report、resolve_evidence、候选 submit/start、候选任务 read/wait/cancel/resume 和 read_candidate_set_report；证据经 canonical JSON 序列化。
- `authorize_path`：realpath 与根包含检查，拒绝 `..`、symlink 逃逸、`.env`、`.git`、凭证和 Docker socket。
- `execute_custom_code`：始终拒绝且不执行 payload；这不是可放开的执行接口。
- `search_web` / `fetch_web`：经 `research_web.DeepSeekWebProvider` 的可选检索入口，默认关闭，域名白名单、预算和完整 query/result set/usage ledger 由 provider 强制。

权限契约见 [07_permissions.md](../research_schema/docs/07_permissions.md)，DSH/MCP 接入见 [08_agent_bridge.md](../research_schema/docs/08_agent_bridge.md)。HMAC、OS/容器强隔离和真实联网 CI 仍未实现；同进程 Python 也不是硬安全边界。
