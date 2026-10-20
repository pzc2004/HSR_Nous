# 候选集后台任务与完成通知

本章定义候选集的异步执行、进度查询、部分结果、取消恢复和通知。它复用现有 investigation/execution、CandidateRunner 与不可变报告，不增加另一套模拟或统计路径。

## CandidateTask 与身份

`CandidateTask` 保存 task_id、CandidateSet、各 candidate 的 investigation 引用、status、artifact_status、attempt、revision、report_id、error、时间与只追加 history。

task_id 由候选集内容派生。重复 start 同一候选集是去重读取，不是独立复核；resume 增加 attempt 并保留已有证据。任务执行状态与报告研究结论是不同维度，inconclusive 不是 worker 故障。

任务使用现有 `queued/running/cancel_requested/cancelled/completed/failed` 和 `partial/complete` 词表。只有全部候选处理完并形成最终候选报告后，任务才能以 completed + complete 结束。

## 生命周期存储

任务根位于 `candidate_tasks/<task_id>/`：

- `task.json`：原子更新的生命周期快照，revision 不得回退，history 只能追加；
- `results/`：逐候选完成后的只读 trial/report 引用；
- `events.jsonl`：只追加的 CandidateTaskEvent；
- `control/`：取消请求和 worker 协调信息；
- `worker.log`：受控 worker 输出。

这些是可变控制面或通知元数据，不改变 spec/run/result/claim/report 的不可变性。

读取任务时，completed_runs/total_runs 和各 candidate 状态由既有 investigation 重新汇总。已完成候选可以返回自己的 trial/report 引用；部分候选结果不构成完整候选集排名，最终 candidate-set report 只在完整组合后出现。

## 独立 worker 与并发约束

start 通过固定 Python 模块参数启动独立 worker，不使用 shell 或调用方命令，不向 worker 传模型凭据。worker 由任务记录、PID、日志和文件锁管理，可以活过发起调用的 MCP/DSH 进程。

同一 research root 的正式候选执行使用操作系统文件锁串行，避免共享 contract 的调查状态竞争；排队、读取和通知等待可以并行。重复 start 不重复执行。

## 取消与恢复

cancel 只写当前 attempt 的独立取消请求，并产生 cancel_requested 事件。worker 在每个 run 进度点和候选边界响应，避免控制方与 worker 并发改写 execution。

取消后保留所有已发布 run 和逐候选结果，不发布完整候选集报告。resume 新建 attempt：完成候选走 cache，部分候选走既有 resume/skip_existing；异常退出留下的活动状态先 reconcile，不能覆盖或重复已有 run。

## CandidateTaskEvent 与通知

事件包含稳定 event_id、task_id、attempt、kind、status、时间和可选 contract/report 引用。候选完成、取消请求和任务终局均可产生事件；每次终局 attempt 必须有明确的 completed/failed/cancelled 事件。

`wait(task_id, after_event_id, timeout_s)` 在服务端等待新事件：有事件立即返回，超时只返回当前快照。事件按 cursor 增量读取且不按单一消费者删除，多个读取方可以收到同一通知，worker/MCP 退出后仍可恢复读取。

completed 事件只携带报告身份，宿主仍须独立重算。当前 one-shot DSH 通过 wait 工具或宿主等待器接收通知；已退出进程的主动消息推送不冒充为已实现能力。

## 当前边界

首版是单 research root 的受控后台执行，不是分布式队列、优先级调度或强安全沙箱。图表、扩指标、多轮搜索和常驻 Agent 的主动消息推送不在本章范围内。
