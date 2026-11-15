# 研究台：只读研究呈现与 ACP 聊天视图

本章描述 `research/workbench` 的呈现契约。研究侧不创造新证据、统计或结论，只消费既有任务视图、candidate-v1、trial 报告与 EvidenceLink 解析结果；聊天侧经回环反代把页面请求转给 ACP 聊天桥子进程（`agents/chat_server`），人在页面与 DSH Agent 会话，执行全部经 ResearchGateway/DSH，研究台不产生可信结论。

## 启动与依赖边界

`hsr-research-web` 使用 FastAPI 和独立静态单页，监听本地地址并复用现有孤儿看护。研究侧只经 ResearchGateway 读取研究数据，不直接 import core、agents、pipeline 或 adapters；仅复用 `sim.web` 的本地服务函数。聊天桥是 workbench 代管的本地服务：spawn `agents.chat_server` 子进程（回环随机端口、`/healthz` 探活、shutdown 收尸）并做 `/chat/*` 流式反代——不 import agents 任何代码，进程边界即模块边界；前置校验（模型配置/DSH）内聚在子进程，失败即非零退出，workbench 探活失败后降级为无聊天。

页面不使用前端框架、CDN、npm 包或 Agent 生成 HTML。图表使用原生 SVG。

## 只读研究 API

| API | 行为 |
|---|---|
| `GET /api/tasks` | 按更新时间排序、带上限的候选任务清单 |
| `GET /api/tasks/{task_id}` | 任务状态、真实 completed/total progress、逐候选结果引用 |
| `GET /api/tasks/{task_id}/events` | 按 after_event_id 非阻塞增量读取持久事件 |
| `GET /api/tasks/{task_id}/report` | 最终 candidate-v1 报告；未形成时明确未就绪 |
| `GET /api/trials/{trial_id}/reports/{report_id}` | 单候选完整 trial 报告 |
| `GET /api/worldlines` | 按 worldline_id 排序、带上限的只读世界线摘要 |
| `GET /api/worldlines/{worldline_id}` | 经完整读时校验的单个 worldline-v1 artifact |
| `POST /api/focus` | 校验 Selection 并返回事件/modifier 焦点与回合 |
| `POST /api/evidence` | 只读解析既有 EvidenceLink 到 run/event/final modifier |

不提供任务 start/cancel/resume、任务编辑、任意路径、命令或 artifact 发布入口。非法 ID、证据不匹配和未就绪报告必须显式报错，不能把异常伪装成正常空态。

## 聊天视图（代管子进程 + 反代）

`chat_proxy` 传入桥子进程回环 base URL 时挂载 `/chat/*` 通用反代（SSE 逐 chunk 透传不缓冲，其余方法透传 body/status；子进程不可达 → 503，页面降级标注）。桥端点契约（实现见 `agents/chat_server`）：

| API（对外 `/chat` 前缀） | 行为 |
|---|---|
| `POST /sessions` | 建 ACP 会话（可带首条 prompt）；桥记账并起 update 泵 |
| `POST /sessions/{sid}/prompt` | 下发 prompt（202；在途重复下发 409） |
| `GET /sessions/{sid}/events` | SSE 推 `session/update` 流 + 本地 `prompt_closed`（环形历史重放） |
| `POST /sessions/{sid}/cancel` | 取消在途 prompt |
| `GET /sessions` | 合并列表：活跃 = 桥记账（摘要标题/最近用量），可恢复 = ACP `session/list` |
| `POST /sessions/{sid}/resume` | 恢复落盘会话并纳入活跃记账；ACP resume 不重放历史 |

缺模型配置或 DSH 时子进程非零退出、`chat_proxy` 为 None：不挂反代（页面标注未启用），研究 API 不受影响。聊天不产生研究 artifact：Agent 的工具调用与提交仍全部在 DSH 白名单与研究网关内完成，页面不自动新建会话（localStorage 记住上次会话，落盘会话需显式恢复）。

## 任务与候选呈现

任务侧栏与概览展示问题、状态、completed_runs/total_runs、attempt、错误和完成事件。终局后停止无意义轮询；task ID 深链只接受规范的 64 位十六进制 ID。

最终候选报告形成后，候选图使用每个候选的 `holdout_adjusted.effect` 与修正 CI，保留零轴、正负效应、dev_rank、selected 和未入选原因。dev effect 与 holdout 结果分栏展示，不能混称为同一数据集。`accepted` 仍只表示当前候选集内的模拟器确认，不表示全局最优或真实游戏校准。

任务尚未形成最终候选报告时，只展示真实进度与已经完成的单候选报告，不提前生成排名或 selected。

## 单候选与证据下钻

完整 trial 报告展示 claim 状态、固定模板结论、cohort n/failed/truncated、baseline/variant 的 mean/p5/p50/p95/min/max 与范围图。actor_damage 只作描述性解释，不进入 claim 判定；caveats 与 failure_reasons 不得隐藏。

证据链使用 `evidence.drilldown`：选择 baseline/variant run，查看事件 ordinal/kind/关键 payload 和 final modifier。事件与 modifier 通过只读 resolver 获取已验证详情，原始 JSON 可展开；缺失历史 modifier 状态保持 unresolved 原义，不虚构其生命周期。

失败候选、无赢家、无报告、无事件、无 modifier 和无效深链均有明确空态。动态文本统一转义，原始 JSON 不作为可信 HTML 注入。

## 世界线只读视图

`GET /api/worldlines` 的 `limit` 规则与任务列表一致，摘要按 `worldline_id` 字典序确定性排列，包含状态、observed、事件与 modifier 数、声明随机值总数和 `derived_from`。`GET /api/worldlines/{worldline_id}` 返回完整 worldline-v1 artifact；网关必须经 `ArtifactStore.read_worldline` 完成身份、证据、事件/modifier 和父链校验，不能把目录扫描或未经校验的 JSON 当作有效世界线。

页面展示状态、observed、声明与实际随机消费、failure_reasons、caveats、build/stage、父代链接，以及 event/final modifier/final_save 的结构化详情和原始 JSON。失败世界线同样可打开；空事件、空 modifier 和无父代均有明确空态。世界线详情直接消费已校验 artifact，不伪造 paired EvidenceLink、RunRecord 或 ComparisonSet。

completed 世界线通过 `/player/{worldline_id}/` 挂载现有 `sim.web` 战斗调试台，直接复用原面板的单位卡、行动条、单步、连续、0.5x/1x/2x/4x、回退、跳转、断点、终结技与检视按钮。`sim.web` 从世界线的 build/stage/random_values/初始资源重新创建内存会话，默认交还 scripted policy 自动决策；检查点与单位详情全部由同一 `DebugController` 产生，不另造回放面板或状态投影。

该面板是原 artifact 的内存回放/调试入口：不发布新世界线、不修改原 artifact，也不把内存中的分支状态提升为可信结论。failed 世界线没有 completed 终态证据，不挂载战斗面板，只展示失败原因、声明和 lineage。

点击事件列表时，页面保留该事件的 JSON 详情，并按最近一个 `turn_start` 的事件序计算回合，调用原面板 `/api/goto`。这是 `DebugController` 提供的回合级定位，不宣称精确到单个伤害或 modifier 发生的瞬时状态；没有 `turn_start` 的早期事件跳转到第 0 回合，modifier 详情不做时间跳转。

## Selection / FocusRequest 原型

`Selection` 是 frozen dataclass，字段为 `type + id + project + investigation + parent_context`，当前只支持 `worldline / event / modifier`。`FocusRequest` 只包含一个 selection。`POST /api/focus` 复用 `allow_read_artifacts` 和完整 artifact 读时校验，按 ID 找到真实记录：worldline 返回选择目标，event 返回 `worldline_id + ordinal + turn`，modifier 返回 `worldline_id + ordinal`。未知类型、缺父级或找不到对象均显式失败，不能静默跳错位置。

页面点击事件时先生成 Selection 并调用该 API，再按返回的回合导航；详情中同时保留原始事件 JSON 与 Selection JSON，便于后续 Agent 使用同一对象模型。通用 `focusEvidence(selection)` 复用同一路径选择世界线并打开事件，但当前不涉及 Agent 自动推送或全局 Memory。

世界线深链为 `#/worldline/<64 位小写 hex>`。研究 API 不提供世界线执行、派生或 fork 入口，内存面板中的操作不形成持久研究产物，单条轨迹也不展示为统计结论。

## 当前限制

不提供任务编辑、世界线执行或派生、fork、人工接管、共享 Memory、常驻 Agent 主动推送；聊天视图与研究视图本期仅标签级并列（「打开研究视图」入口）。Selection 当前仅覆盖上述 worldline / event / modifier，不支持其他证据类型或 Agent 主动 Selection 推送，也不做全局 Selection/FocusRequest 深度联动。只读展示本身不提升证据等级，所有结论继续标明 simulated/pending_real_validation 和当前候选集范围。
