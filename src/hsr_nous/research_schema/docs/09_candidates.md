# 多候选研究与确认性验证

本章描述当前已经落地的有界候选集。它解决“一次比较多个 variant 时，如何保留全部证据、避免只挑赢家”的问题，不是开放式自动搜索或全局最优求解器。

## 候选契约

`CandidateSet` 是递归冻结的数据模型：

| 字段 | 含义 |
|---|---|
| `question` | 本组候选共同的研究问题 |
| `candidates` | 至少两个 `ResearchContract`，每个仍包含自己的 baseline/variant |
| `top_k` | dev 阶段最多允许进入 holdout 确认的候选数，默认 1 |
| `correction` | 当前固定为 `bonferroni` |

`candidate_set_id = content_hash(candidate_set)`。候选必须共享 question、baseline、build、stage、metric、protocol、comparison_kind 和 `budget.max_runs`；contract/spec ID 与契约内容不得重复。候选总数和总预算有上限，具体由 `validate_candidate_set()` 机械校验。每个 contract 仍须通过原有 `validate_contract` 和模板校验。

## 执行与复核

`CandidateRunner` 为每个候选独立执行既有双方案流程：

```text
create_investigation → validate → queue → execute
    ↓
ClaimValidator + ReportComposer
    ↓
dev 全量排名
    ↓
top_k 候选的 holdout 修正 CI
    ↓
不可变 candidate-v1 报告
```

已完成 investigation 使用 cache，部分失败可 resume；单个候选失败不会阻塞其他候选。`run()` 执行实验，`validate()` 只读 artifact 重新计算，`validate_report()` 要求既有报告并重建期望值，不能用再次执行掩盖 Agent 没有执行的事实。

## dev 与 holdout 修正

所有候选先按 metric direction 使用 dev 的 effect 排序，完整保留排名。只有前 `top_k` 个候选进入 holdout 确认。

对 N 个候选，修正后的置信度为：

```text
adjusted_confidence = 1 - (1 - protocol.confidence) / N
```

holdout 修正 CI 继续使用同一组原始样本、固定 bootstrap seed 和精确中间差值，不通过换 seed 或删失败样本改善结果。修正 CI 排除零才允许入选。dev 未选中不等于证明该方案无效；dev 选中但 holdout 未确认表示证据不足，而不是强行宣称失败。

`accepted` 表示至少一个候选通过确认；无入选为 `inconclusive`，全部执行失败为 `failed`。这些状态都不是全局最优或真实游戏校准结论。

## 报告与证据

报告位于：

```text
candidate_sets/<candidate_set_id>/reports/<report_id>.json
```

`schema_version="candidate-v1"`，包含：

- 候选计划与 `candidate_set_id`；
- dev 全量排名、每个候选的 dev/holdout 比较及修正 CI；
- `selected`、`dev_rank`、`selection_reason`、失败原因；
- 每个候选的 `trial_id`、`report_id`、状态和证据链接；
- `simulated/pending_real_validation` 与仅限当前候选集的 scope。

报告不包含执行时间或 cache/initial 标记，同一候选计划和证据产生稳定 report ID。原始 run、事件和 final modifier 仍归各 trial 的既有 artifact，不复制到候选报告。

## 权限与传输

`ResearchGateway.submit_candidate_set()` 只接受候选计划，不能传 selected、效应值或 CI。`read_candidate_set_report()` 做完整性校验，`validate_candidate_set_report()` 独立重算并校验 report ID。

MCP 提供 `submit_candidate_set` 和 `read_candidate_set_report`，支持对象或原样 `candidate_set_json`，输入互斥。响应先提供 `candidate_report_id` 和 `candidate_set_id`，再嵌完整报告，避免 DSH 的 `tool_result` 投影截断时无法定位报告。`candidate_report_id` 是便于传输的别名，实际 report identity 仍是完整报告中的 `report_id`，不是第二份报告。

DSH 宿主还会核对唯一预期调用、成功 tool_result 和 candidate_set 身份，再调用 `validate_candidate_set_report()` 独立复核。模型自然语言不能替代这些检查。

## 当前限制

- 只支持固定候选集，不自动扩展候选或修改 baseline。
- 只有 Bonferroni 修正，未实现其他多重比较模型或开放式搜索。
- 当前仍是单进程顺序执行，不支持异步 worker、优先级队列或分布式调度。
- `accepted` 仅限模拟器内当前候选集，未经过真实游戏校准，也不证明全局最优。
