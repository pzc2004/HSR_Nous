# Harness 最小生命周期

本章描述当前单进程、顺序执行的 investigation/execution 生命周期。它解决首次执行、取消、崩溃恢复、缓存命中、检查性重放、失败保留和状态持久化，不接 DSH、联网搜索、前端、多候选搜索或分布式队列。

## 对象区别

| 对象 | 表示什么 | 关键字段 | 是否包含原始战斗证据 |
|---|---|---|---|
| `ResearchContract` | 研究问题与实验配置 | build/stage、baseline/variant、protocol、budget | 不包含 run；是执行输入 |
| `InvestigationState` | 研究问题的可恢复快照 | investigation_id、contract、status、active_execution_id、execution_ids、trial_id、进度、artifact_status、next_action、revision、时间 | 不复制 run/event/claim；只保存 contract 和引用/进度 |
| `ExecutionRecord` | 一次执行动作及其迁移历史 | execution_id、investigation_id、kind、attempt、parent_execution_id、status、artifact_status、trial_id、contract_hash、进度、时间、error、history | 不复制 run；记录执行状态和错误 |
| `RunRecord` | 一个 seed 对应的确定性世界线 | run_id、trial_id、arm、cohort、seed、observed、events、final_save、modifiers、content_hash | 是原始战斗证据，仍走不可变 trial artifact |

`RunCancelledError` 位于 `research_core.runner`，供 progress 回调请求安全停止；它不是数据模型，也不是失败样本。

## 身份与词表

- `investigation_id = SHA256(canonical(contract))`。
- `execution_id = SHA256(investigation_id + contract_hash + kind + attempt)`。
- `kind`：`initial / cache_hit / replay_check / resume`。
- `status`：`draft / validated / queued / running / validating / completed / failed / cancel_requested / cancelled`。
- `artifact_status`：`partial / complete`。

resume、replay_check 和 cache_hit 都通过 `parent_execution_id` 关联前一次执行。缓存读取不是一次新的独立复核，run_id 的世界线身份也不因这些动作改变。

## 状态机

```text
create_investigation
        ↓ draft
    validate
        ↓ validated
      queue
        ↓ queued
     execute
        ↓ running
        │  每个 run 发布后更新 progress/history/revision
        │  可选：cancel_requested → cancelled + partial
        ▼
  全部 raw run 保留
        ↓ validating + complete
   ClaimValidator + ReportComposer 完成
        ↓ completed + complete
     cache / replay
```

`validating` 只允许在全部协议 raw run 已发布后进入。`completed` 还要求验证和报告均完成，并且 `artifact_status=complete`。raw run 完整后若验证失败，可以是 `failed + complete`：证据完整但执行动作失败，两者不是同一维度。

## Partial 与 Complete

- `partial`：draft/queued/running 的默认状态，或取消后只保留部分 run。此时没有完整 result，不能进入 validating，也不生成 accepted claim。
- `complete`：全部协议 raw run 已保留。验证与报告完成后，ExecutionRecord 和 InvestigationState 才进入 completed。

取消发生在进度点时，已经发布的 spec/variant/run 不受影响；未执行的剩余 run 不会伪造，result.json 不发布。

## 持久化与迁移

`ArtifactStore` 新增：

- `execution_path / read_execution / write_execution`：保存到 `executions/<execution_id>.json`；
- `investigation_path / read_investigation / write_investigation`：保存到 `investigations/<investigation_id>.json`。

这些文件使用 canonical bytes、全 SHA-256 ID 和原子更新。每次迁移同步更新 ExecutionRecord 与 InvestigationState：

- ExecutionRecord.history 只允许在原前缀上追加，不能缩短或重写；
- InvestigationState.revision 不能回退，execution_ids 也只能在原前缀上追加；
- created_at 不可改写；
- 读取时重新验证内容哈希和逻辑身份。

墙钟 created/started/finished/duration 只描述执行元数据，不参与 trial/run/claim 的内容身份。trial artifact 的 spec/run/result/claim/report 仍保持不可覆盖和冲突拒绝。

## 公开 API 顺序

```python
manager = ExecutionManager(store)

# 首次：draft → validated → queued → running → validating → completed
investigation = manager.create_investigation(contract)
investigation = manager.validate(investigation.investigation_id)
execution = manager.queue(investigation.investigation_id)
execution = manager.execute(execution.execution_id)

# 取消只能在 execute 处于 running 时进行，不能在 execute 已返回 completed 后调用：
# 控制方在 running 状态调用 cancel；execute 返回 cancelled 后再 resume
manager.cancel(execution.execution_id)
resumed = manager.resume(investigation.investigation_id)

# completed 后：只读取已有结果，不调用 runner
cached = manager.cache(investigation.investigation_id)

# 检查性重放：新建 replay_check，全量重跑并做幂等字节核对
replayed = manager.replay(investigation.investigation_id)
```

所有方法都是单进程顺序调用。`execute` 对已处于 completed/failed/cancelled 的记录只返回既有结果；新的复核或恢复必须走 replay/resume 的 parent 链。

## 取消与崩溃恢复示例

若在第 3 个 run 发布后请求取消：

1. `cancel(execution_id)` 把状态置为 `cancel_requested` 并持久化；
2. 下一个 runner progress 点抛出 `RunCancelledError`；
3. 已发布的 3 个 run 保留，ExecutionRecord 进入 `cancelled + partial`，不发布 result；
4. `resume(investigation_id)` 新建 `kind=resume` 的执行，parent 指向被取消的执行；
5. runner 使用 `skip_existing=True`，逐个 read_run 验证已有 3 局，只执行剩余 61 局，最终进入 completed。

## 缓存与检查性重放

- `cache()` 要求 investigation 和报告都已 completed，读取并验证已有 result，且 reports 目录至少有一个可读取且通过完整性校验的报告；缺报告时拒绝 cache_hit，不调用 `TrialRunner.run`。
- `replay()` 新建 `replay_check`，关联 parent，使用默认 `skip_existing=False` 全量重跑。已有 artifact 必须逐字节幂等，否则抛出冲突而不是覆盖。
- `resume()` 只服务 cancelled/failed 且 partial 的调查；`cache()` 不把读取缓存冒充为独立 replay。

## 当前边界

首版只提供最小生命周期，不提供异步 worker、优先级队列、联网任务分发、分布式锁或强安全隔离。ExecutionRecord 和 InvestigationState 是可恢复元数据，不替代原始 run、不可变 trial artifact 或独立 claim 重算。
