# research/workbench

HSR_Nous 研究台（模块别名：伊德莉拉）：**唯一前端单页**——研究侧把后台任务、可信报告与证据呈现为可读页面；聊天侧提供 ACP Agent 会话视图。不执行任务编辑或模拟，可信结论仍只由 research/core 产出。

## 启动

```bash
hsr-research-web --research-root /path/to/research --port 8001 --no-open
```

默认监听 `127.0.0.1:8001`，复用现有本地服务与孤儿看护。研究根只读，目录约定与 `HSR_NOUS_RESEARCH_ROOT` 一致。

缺省即同时提供「研究」「聊天」两个视图（顶部标签切换）。聊天桥是 workbench 代管的第二个本地服务：启动时 spawn `python -m hsr_nous.agents.chat_server`（回环随机端口，`/healthz` 探活，shutdown 时 terminate），页面经 `/chat/*` 流式反代访问——**workbench 不 import agents 任何代码**。子进程自带前置校验：缺 `HSR_NOUS_LLM_AGENTS_*` 模型配置或 DSH 即打印中文错误并非零退出，workbench 探活失败后降级为无聊天（页面标注未启用）；运行期子进程死掉时反代 503，页面同样降级。

## 聊天视图（ACP 桥反代）

会话由幕后 DSH 经 ACP 桥承载（桥实现与契约在 `agents/chat_server`，经 `/chat/*` 反代）：

- 左栏会话列表：新建；每项 = 摘要标题（首条用户消息截断）、活跃/可恢复状态、最近上下文用量（该会话最近一次 `usage_update`），点击载入；
- 中栏消息流：思考过程默认折叠卡片、工具调用可折叠、取消按钮与在途态；
- 右栏会话信息：session_id、用量、恢复入口、「打开研究视图」。

落盘会话（ACP `session/list`）可恢复，`resume` 后历史不回放（页面标注）。localStorage 记住上次会话。信任边界与 stock web 一致：Agent 只能调用 `mcp__nous__*` 白名单工具，Agent 文本不可信。

## 页面链路（研究视图）

- 任务列表、真实 completed/total 进度、attempt、错误与完成事件；
- 最终候选报告的 dev 排名、holdout 效应与 Bonferroni 修正 CI（原生 SVG）；
- 单候选完整 trial 报告、两臂分布、描述性 actor_damage 与 caveats；
- run → event / final modifier 的结构化详情和原始 JSON。

运行中只有部分候选完成时，可先查看对应单候选报告，但不提前生成最终排名。页面持续显示 `simulated / pending_real_validation` 与当前候选集范围。

## 只读边界

研究 API（`/api/*`）仅提供任务/报告/证据读取：任务清单与详情、增量事件、候选报告、trial 报告和 EvidenceLink 解析。没有 start/cancel/resume、任务编辑、artifact 发布或 Agent 自由 HTML 入口。`POST /api/evidence` 仅用于提交 EvidenceLink 进行只读解析。

聊天路由（`/chat/*`，反代）不是研究数据 API：它把人在页面上的输入透传给回环上的桥子进程，Agent 的工具调用与提交仍全部在 DSH 白名单与研究网关内完成，workbench 不产生可信结论、不直接 import research/core 或 agents。

实现与契约见 `research/schema/docs/12_workbench.md`。测试包括真实 API、Node 纯函数和 Chromium 端到端链路。
