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

研究根默认由 `HSR_NOUS_RESEARCH_ROOT` 决定，缺省为 `~/HSR_Nous`，必须独立于源码仓库。DSH 的 `HOME`、`DSH_HOME` 使用该根下的隔离目录；cwd 是源码仓库以读取项目 `.env`，沙箱工作区和研究产物仍归研究根。

模型配置从仓库根 `.env.example` 复制到 `.env`，填写三项：

```dotenv
HSR_NOUS_LLM_AGENTS_API_KEY=
HSR_NOUS_LLM_AGENTS_MODEL=
HSR_NOUS_LLM_AGENTS_API_BASE=
```

DSH 启动时自行读取 `.env`；启动器只检查文件是否存在以选择 OpenAI 兼容 profile，不读取或打印其中的值。也可通过 `--allow-model-env` 显式传入同名环境变量。`.env` 已被 gitignore，应使用独立测试凭据且权限设为 600。

## 可信边界

- DSH 只能调用 `mcp__nous__submit_claim/read_investigation/read_report/resolve_evidence/submit_candidate_set/read_candidate_set_report`；配置禁用与插件 guard 同时拒绝其他工具。
- 多候选输入使用 `hsr-research-agent --candidate-set /path/to/candidates.json`，候选集的 dev 排名、holdout 修正和 selected 都由后端计算。
- Bash、Pwsh、FS、workflow、subagent、内置 web、jobs、会话日志上传和 OTel 均关闭。
- `submit_claim` 进入现有 `ResearchGateway`，统计和报告只能由模拟证据及可信内核产生。
- 宿主先登记预期 contract，DSH 完成后核对唯一预期调用及其成功 tool_result，再重新读取 investigation 并独立复核报告。Agent 的自然语言文本标记为 untrusted，不能替代完成态 investigation 或可信报告。
- 跨 JavaScript 进程提交契约时使用 `contract_json` / `claim_json` 原样字符串，避免 `600.0` 被改成 `600` 后产生不同内容身份。

具体协议见 [08_agent_bridge.md](../research_schema/docs/08_agent_bridge.md)。

## 限制

局部 npm 安装、独立 HOME 和工具白名单不等于 OS 级安全沙箱；DSH 与 MCP 仍是本机进程。当前不支持多轮交互、开放式多候选搜索或真实模型 CI。标准测试使用回环地址上的隔离 Messages 服务；真实模型 smoke 已另行使用独立凭据验证，不进入 CI。
