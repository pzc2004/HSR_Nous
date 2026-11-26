# research/web

可选外部检索与证据层，只依赖 `research/schema` 和 `common`，不依赖 `research/permissions`。

- `DeepSeekWebProvider`：调用 DeepSeek 官方 Search/Fetch API，使用 `httpx`。
- `WebEvidenceStore`：按 investigation 保存完整 query、结果集和 usage ledger。
- 默认关闭；白名单、预算、SSRF/重定向检查、有限退避均由 provider 强制执行。
- 域外结果保留但标为 `allowed=false`，不静默删除；正文、矛盾来源和失败记录都保存。
- 网页内容只作外部先验，不进入可信内核、Claim 或 accepted 推导。

完整权限契约见 [07_permissions.md](../research/schema/docs/07_permissions.md)。HMAC、OS/容器隔离和真实联网 CI 不在当前范围；测试使用 mock transport。
