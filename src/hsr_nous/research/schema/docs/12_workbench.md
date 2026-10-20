# 只读研究台：任务、图表与证据下钻

本章描述 `research/workbench` 的只读呈现契约。研究台不创造新证据、统计或结论，只消费既有任务视图、candidate-v1、trial 报告与 EvidenceLink 解析结果。

## 启动与依赖边界

`hsr-research-web` 使用 FastAPI 和独立静态单页，监听本地地址并复用现有孤儿看护。`research/workbench` 只经 ResearchGateway 读取研究数据，不直接 import core、agents、pipeline 或 adapters；仅复用 `sim.web` 的本地服务函数。

页面不使用前端框架、CDN、npm 包或 Agent 生成 HTML。图表使用原生 SVG。

## 只读 API

| API | 行为 |
|---|---|
| `GET /api/tasks` | 按更新时间排序、带上限的候选任务清单 |
| `GET /api/tasks/{task_id}` | 任务状态、真实 completed/total progress、逐候选结果引用 |
| `GET /api/tasks/{task_id}/events` | 按 after_event_id 非阻塞增量读取持久事件 |
| `GET /api/tasks/{task_id}/report` | 最终 candidate-v1 报告；未形成时明确未就绪 |
| `GET /api/trials/{trial_id}/reports/{report_id}` | 单候选完整 trial 报告 |
| `POST /api/evidence` | 只读解析既有 EvidenceLink 到 run/event/final modifier |

不提供任务 start/cancel/resume、任务编辑、任意路径、命令或 artifact 发布入口。非法 ID、证据不匹配和未就绪报告必须显式报错，不能把异常伪装成正常空态。

## 任务与候选呈现

任务侧栏与概览展示问题、状态、completed_runs/total_runs、attempt、错误和完成事件。终局后停止无意义轮询；task ID 深链只接受规范的 64 位十六进制 ID。

最终候选报告形成后，候选图使用每个候选的 `holdout_adjusted.effect` 与修正 CI，保留零轴、正负效应、dev_rank、selected 和未入选原因。dev effect 与 holdout 结果分栏展示，不能混称为同一数据集。`accepted` 仍只表示当前候选集内的模拟器确认，不表示全局最优或真实游戏校准。

任务尚未形成最终候选报告时，只展示真实进度与已经完成的单候选报告，不提前生成排名或 selected。

## 单候选与证据下钻

完整 trial 报告展示 claim 状态、固定模板结论、cohort n/failed/truncated、baseline/variant 的 mean/p5/p50/p95/min/max 与范围图。actor_damage 只作描述性解释，不进入 claim 判定；caveats 与 failure_reasons 不得隐藏。

证据链使用 `evidence.drilldown`：选择 baseline/variant run，查看事件 ordinal/kind/关键 payload 和 final modifier。事件与 modifier 通过只读 resolver 获取已验证详情，原始 JSON 可展开；缺失历史 modifier 状态保持 unresolved 原义，不虚构其生命周期。

失败候选、无赢家、无报告、无事件、无 modifier 和无效深链均有明确空态。动态文本统一转义，原始 JSON 不作为可信 HTML 注入。

## 当前限制

只读 v1 不提供任务编辑、fork、人工接管、共享 Memory、常驻 Agent 主动推送或复杂 Selection/FocusRequest 联动。只读展示本身不提升证据等级，所有结论继续标明 simulated/pending_real_validation 和当前候选集范围。
