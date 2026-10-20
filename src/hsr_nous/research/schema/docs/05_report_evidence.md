# JSON 报告与证据下钻

`ReportComposer` 只输出 JSON，不输出 HTML 或前端模型。报告发布前会重新验证 claim，随后由 store 以 canonical bytes 和完整 `report_id` 保存。多候选结果使用独立的 candidate-v1 报告与复核流程，见 [09_candidates.md](09_candidates.md)。

## 报告字段

所有状态的报告都包含以下基础字段：

| 字段 | 当前内容 |
|---|---|
| `schema_version` | 当前报告结构版本 2 |
| `spec` | 已验证 spec payload：contract、resolved protocol、fingerprint、trial_id、spec_hash |
| `canonical` | baseline arm ID 与 `world="canonical"` |
| `variant` | variant arm ID、真实 world、comparison_kind 和已验证 metadata；configuration 还可用 build.json 复核 |
| `flags` | `source="simulated"`、随 variant 变化的 world、`validation="pending_real_validation"` |
| `comparison_set` | 冻结的两臂 dev/holdout run 队列及 comparison_set_id |
| `fingerprint` | spec 中的完整版本指纹 |
| `claim` | 当前状态的 claim 视图 |
| `evidence` | claim record ID、comparison_set_id、premises 和 drilldown |
| `caveats` | 编译和执行保留的结构化近似/未决语义 |
| `failure_reasons` | 与 failed run 精确对应的失败原因 |
| `validation_reason` | 当前 claim 的状态原因 |
| `conclusion` | 由结构化 claim 固定模板生成的结论文本 |
| `report_id` | 完整报告内容的 SHA-256 |

`accepted` 和 `inconclusive` 还包含：

- `cohorts`：baseline/variant 各自 dev/holdout 的有效样本数、分布、failed/truncated 数量和 run ID；
- `comparisons`：dev 与 holdout 的 paired comparison，缺少完整配对时为 `null`；
- `effect`：holdout paired mean difference，无法比较时为 `null`；
- `confidence_interval`：holdout CI 及固定 bootstrap 参数，无法比较时为 `null`；
- `actor_damage`：描述性 actor 伤害拆解，按 baseline/variant 与 dev/holdout 汇总每个 actor_id 的 display_name、present/absent、n 和 distribution；不进入 total_damage、CI 或 claim 状态；
- `derivation_steps`：取样、paired mean difference、bootstrap 等结构化推导。

`rejected` 和 `stale` 不输出上述方向性统计区，只保留 spec、状态、原因、证据和必要元数据。`inconclusive` 可以包含结构化 effect/CI 供审查，但其结论文本不得给出方向性结论。

## 结论句生成

accepted 使用固定模板，数值只能来自重新验证的 claim；结论前缀由 claim.scope 动态生成：

```text
simulated/<world>/pending_real_validation: holdout variant - baseline mean total_damage = <effect>; <confidence>% CI [<lower>, <upper>]; n=<n>.
```

其他状态使用：

```text
simulated/<world>/pending_real_validation: <status> — <failure_reason>
```

三类 flags 同时存在于结构化字段和结论前缀中：

- `simulated`：证据来自模拟器，不是真实游戏观测；
- `hypothetical` 或 `canonical`：mechanism 使用 hypothetical，configuration 使用 canonical，不再把真实配装/配队误标为机制假设；
- `pending_real_validation`：真实游戏验证仍待完成。

因此 accepted 也不能被解读为真实游戏正确、全局最优或完成实测校准。

## Cohorts、Comparisons 与 Derivation

`cohorts` 用于回答“每个臂、每个数据集有多少可用样本和失败样本”：distribution 由有效 run 现算，failed/truncated 不会被删除。

`comparisons` 用于回答“同一 seed 上 variant 与 baseline 的差值是什么”：dev 只作探索，holdout 才决定 accepted。paired seed 不完整时，对应 comparison 为 `null`，不能沿用其他 cohort 的 CI 顶替。

`derivation_steps` 用于回答“这些数字如何产生”：包括 holdout seed、两臂 run ID、有效样本数、失败/truncated 清单、精确配对差、效应值和 bootstrap 参数。ClaimValidator 会逐项核对这些推导，不接受只改统计摘要而不改证据的做法。

## 证据链接与下钻

### Premises

`evidence.premises` 包含：

1. spec 的 `EvidenceLink`；
2. result 的 `EvidenceLink`；
3. variant metadata 的 `EvidenceLink`；
4. 全部相关 run 的 `EvidenceLink`。

链接保存 `trial_id`、`artifact_hash` 和可选 `run_id` / `event_id` / `modifier_id`，不复制结论数字或文本摘录。

### Drilldown

`evidence.drilldown` 当前为每个 arm 选取首个 run，并展开：

- run 链接；
- 该 run 全部 structured event 链接；
- 该 run 全部 final modifier 链接。

`ArtifactStore.resolve_evidence()` 会重新读取并校验对应 artifact：

- run 链接返回已验证 RunRecord；
- event 链接返回对应事件；
- modifier 链接返回 final modifier 的全字段详情；
- spec/result/variant 链接返回相应已验证内容。

event 或 modifier 链接必须带 `run_id`，并且不能在同一条链接中同时选择二者。

### Unresolved

如果 modifier 不在 final modifier 集合中，resolver 返回：

```json
{
  "status": "unresolved",
  "kind": "modifier",
  "reason": "modifier is absent from final state; historical lifecycle is not recorded"
}
```

这表示当前证据无法解析该 modifier；它不等于证明 modifier 曾经存在或不存在。当前没有事件时刻 modifier 快照，因此不能虚构其历史生命周期代际。缺失 event 同样显式返回 `unresolved`。

## 公开 Python API 调用顺序

下面只展示当前公开 API 的正常调用顺序；`contract` 应按 [01_contracts.md](01_contracts.md) 构造，测试和 demo 的详细构造见 [00_overview.md](00_overview.md)。

```python
from hsr_nous.common import research_root
from hsr_nous.research.core import (
    ArtifactStore,
    ClaimValidator,
    ReportComposer,
    TrialRunner,
)
from hsr_nous.research.schema import EvidenceLink

# 生产默认写到 <research_root>/artifacts；测试应显式传 tmp_path。
store = ArtifactStore(research_root() / "artifacts")

# 1. 已按契约构造好的 ResearchContract，不接受自定义协议 seed。
artifact = TrialRunner(store).run(contract)

# 2. 从真实 artifact 重建统计与 claim。
validated = ClaimValidator(store).validate_trial(artifact.trial_id)

# 3. Composer 发布前会再次 validate；不向它传手写 metrics。
report = ReportComposer(store).compose(validated)

# 4. 已发布内容通过只读接口复核。
same_report = store.read_report(artifact.trial_id, report["report_id"])
assert same_report == report

# 5. JSON 中的链接先恢复为 EvidenceLink，再下钻。
link = report["evidence"]["drilldown"][0]["run"]
resolved = store.resolve_evidence(EvidenceLink.from_dict(link))
assert resolved["status"] == "resolved"
```

`publish_report()` 是 store 的底层发布 API，负责 trial 归属和完整性校验；可信研究结论的正常入口仍是 `ReportComposer.compose()`，因为它会重新验证推导。

## 停云 Walkthrough

以 `demo_停云白板` 为例，当前端到端路径是：

1. 只读解析 demo 的 build/stage，构造一个 baseline/variant contract；variant 对角色 `1202` 的 `base_stats.atk` 使用 `set_number`。
2. `TrialRunner` 分别编译 canonical 与覆盖根 variant，并执行 `paired-v1` 全部 64 局。
3. 检查每个 run 的 observed、events、final_save 和 final modifier 都已发布，且 baseline/variant 使用相同 seed 队列。
4. `ClaimValidator.validate_trial()` 重算 paired difference 和 holdout CI。状态由真实样本决定：CI 不含 0 且证据完整才是 accepted；CI 跨 0 是 inconclusive，不能用换 seed 追求特定状态。
5. `ReportComposer.compose()` 再验证并发布 JSON。报告包含两臂 dev/holdout 分布、比较、claim、推导、指纹和证据链接。
6. 通过 `resolve_evidence()` 从 claim 下钻到 trial、run、event 和 final modifier；不存在的 modifier 显式得到 `unresolved`。
7. 再次执行相同 contract 和验证流程，确定性 artifact 与 report 内容保持一致。

本文不写入该例子的当前伤害效应值或 CI；读者应从实际 report 和原始 run 获取这些值。

## 黄泉 Configuration Walkthrough

- **配装**：baseline 使用黄泉的 `feet={set_id:"101", main:"spd", subs:{}}`，variant 仅改同一 feet 的 main 为 `atk_pct`。`build.json` 保存 variant 的完整 effective build；两臂跑真实 64 局，报告 flags 和结论前缀均为 `simulated/canonical/pending_real_validation`。
- **白板四人队机制对照**：baseline 为黄泉 + 椒丘 + 缇宝 + 砂金，variant 仅把 index 2 的缇宝替换为赛飞儿。四人全 E0、无光锥、无遗器，stage/policy 沿用 demo；它不是完整毕业配装。测试核对两个真实四人编队、build.json、parent lineage、canonical flags 和证据下钻。

configuration 的 accepted/rejected/inconclusive/stale 判定与 mechanism 完全相同。攻击鞋外部社区预期不进入统计内核，任何实际结果都不能通过换 seed 追求。本文同样不记录这些场景的当前效应值。

四人报告的 `actor_damage` 只作描述性解释：completed 且未 truncated run 以 `final_save.state.actors` 的合法我方名册判断 present（排除 monster、召唤物与系统单位），`n` 是实际在场的有效 run 数；`damage_by_actor` 只提供伤害值，零伤害在场仍为 present 且 distribution 为 null，absent 只用于该 arm 中不在场的角色。固定成员与替换成员都保留 actor_id/display_name。它不参与 total_damage 判定、CI 或 claim 状态，rejected/stale 不输出该字段。

## 当前限制

- 只保存 final modifier 全量详情，没有事件时刻 modifier 生命周期快照。
- 完整离线模板闭包尚未导出，replay 仍依赖 canonical 模板根。
- 真实游戏校准尚未完成，所有结论都是 simulated，configuration 的 canonical 也不等于真实游戏已验证。
- 只读权限和 SHA-256 是防误改护栏，不是恶意同用户进程沙箱。
- 首版只有一个 baseline/variant，不提供多候选搜索或多重比较结论。
