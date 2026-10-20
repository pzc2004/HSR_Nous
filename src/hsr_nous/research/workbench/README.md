# research/workbench

HSR_Nous 研究台（模块别名：伊德莉拉）：把后台任务、可信报告与证据呈现为可读页面，不执行任务编辑或模拟。

## 启动

```bash
hsr-research-web --research-root /path/to/research --port 8001 --no-open
```

默认监听 `127.0.0.1:8001`，复用现有本地服务与孤儿看护。研究根只读，目录约定与 `HSR_NOUS_RESEARCH_ROOT` 一致。

## 页面链路

- 任务列表、真实 completed/total 进度、attempt、错误与完成事件；
- 最终候选报告的 dev 排名、holdout 效应与 Bonferroni 修正 CI（原生 SVG）；
- 单候选完整 trial 报告、两臂分布、描述性 actor_damage 与 caveats；
- run → event / final modifier 的结构化详情和原始 JSON。

运行中只有部分候选完成时，可先查看对应单候选报告，但不提前生成最终排名。页面持续显示 `simulated / pending_real_validation` 与当前候选集范围。

## 只读边界

API 仅提供任务/报告/证据读取：任务清单与详情、增量事件、候选报告、trial 报告和 EvidenceLink 解析。没有 start/cancel/resume、任务编辑、artifact 发布或 Agent 自由 HTML 入口。`POST /api/evidence` 仅用于提交 EvidenceLink 进行只读解析。

实现与契约见 `research/schema/docs/12_workbench.md`。测试包括真实 API、Node 纯函数和 Chromium 端到端链路。
