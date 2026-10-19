# research_permissions

外部研究权限策略与唯一结论提交通道。本包只依赖 `research_core`、`research_schema`、`research_protocol` 和 `common`，这些下层模块不得反向依赖本包。

## 当前能力

- `CapabilityPolicy`：不可变策略，默认仓库/artifact 只读、项目目录可写、允许模拟和 submit_claim，联网/Bash/Python/Docker 全禁。
- `ResearchGateway`：薄封装调查生命周期，逐项检查权限，不暴露 publish_run/publish_claim/publish_report。
- `submit_claim`：只接受 `contract`、`trial_id` 或 `claim` 之一，拒绝 metrics/samples/effect/CI 等调用方数字。
- `authorize_path`：realpath 与根包含检查，拒绝 `..`、symlink 逃逸、`.env`、`.git`、凭证和 Docker socket。
- `execute_custom_code`：始终拒绝且不执行 payload；这不是可放开的执行接口。
- `search_web` / `fetch_web`：经 `research_web.DeepSeekWebProvider` 的可选检索入口，默认关闭，域名白名单、预算和完整 query/result set/usage ledger 由 provider 强制。

完整契约见 [07_permissions.md](../research_schema/docs/07_permissions.md)。HMAC、OS/容器强隔离和真实联网 CI 仍未实现；同进程 Python 也不是硬安全边界。
