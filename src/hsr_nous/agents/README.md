# agents

外部 Agent harness 适配层。当前只有 DSH headless，不包含自研 Agent loop、ACP、交互式前端或共享 Memory。

## 准备

```bash
bash scripts/setup_agent_env.sh
```

脚本把固定版本的 `@deepseek-ai/dsh` 安装到 gitignored 的 `external/dsh/`，不全局安装、不修改现有 `~/.dsh`。完整测试环境 `scripts/setup_test_env.sh` 也会执行这一步。可用 `HSR_NOUS_DSH_BIN` 指定另一个 DSH 可执行文件。

## 运行一个研究契约

```bash
hsr-research-agent /path/to/contract.json --research-root /path/to/research
```

研究根默认由 `HSR_NOUS_RESEARCH_ROOT` 决定，缺省为 `~/HSR_Nous`，必须独立于源码仓库。DSH 的 `HOME`、`DSH_HOME` 和 cwd 都由启动器设置为该根下的隔离目录，不继承用户现有 profile、会话或凭据。

真实 DeepSeek 调用需要调用方显式允许模型环境进入 DSH：

```bash
hsr-research-agent /path/to/contract.json --allow-model-env
```

此时只传递 `DEEPSEEK_API_KEY` 和可选的 `DEEPSEEK_BASE_URL`。默认不传递它们，也不读取仓库 `.env`。应使用独立测试凭据；密钥不会写入研究报告或 MCP 子进程环境。

## 可信边界

- DSH 只能调用 `mcp__nous__submit_claim/read_investigation/read_report/resolve_evidence`；配置禁用与插件 guard 同时拒绝其他工具。
- Bash、Pwsh、FS、workflow、subagent、内置 web、jobs、会话日志上传和 OTel 均关闭。
- `submit_claim` 进入现有 `ResearchGateway`，统计和报告只能由模拟证据及可信内核产生。
- 宿主先登记预期 contract，DSH 完成后核对唯一预期调用及其成功 tool_result，再重新读取 investigation 并独立复核报告。Agent 的自然语言文本标记为 untrusted，不能替代完成态 investigation 或可信报告。
- 跨 JavaScript 进程提交契约时使用 `contract_json` / `claim_json` 原样字符串，避免 `600.0` 被改成 `600` 后产生不同内容身份。

具体协议见 [08_agent_bridge.md](../research_schema/docs/08_agent_bridge.md)。

## 限制

局部 npm 安装、独立 HOME 和工具白名单不等于 OS 级安全沙箱；DSH 与 MCP 仍是本机进程。当前不支持多轮交互、多候选搜索或真实模型 CI。测试中的真实 DSH 端到端使用回环地址上的隔离 Messages 服务，不访问真实模型 API。
