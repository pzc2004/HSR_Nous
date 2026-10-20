# 数据契约与 Canonical JSON

本章列出 `research_schema.models` 当前实际模型及其字段和不变量。所有模型都是 frozen dataclass，并共享递归冻结与严格 round-trip 行为。

## 通用模型不变量

### 递归冻结

构造模型时会递归处理输入：

- `Mapping` 转为新的 `MappingProxyType`，嵌套 mapping 也不能在模型内原地赋值。
- list/tuple 转为 tuple，内部元素继续递归处理。
- 其他可变输入执行 defensive deepcopy；已经冻结的嵌套模型可以安全共享。
- frozen dataclass 禁止字段重新赋值，mappingproxy 和 tuple 进一步禁止修改嵌套内容。

`to_dict()` 会重新生成普通 JSON dict/list，不暴露内部 mappingproxy；修改返回值不会反向修改模型。

### 严格 round-trip

每个模型都支持：

```python
payload = model.to_dict()
restored = type(model).from_dict(payload)
assert restored == model
```

`from_dict()` 接受 `collections.abc.Mapping`，按 dataclass 类型递归解码，并拒绝：

- 未声明字段；
- 错误的对象/数组形状；
- 不符合字段类型的值；
- 无法按声明的 tuple、nested dataclass 或 optional 类型解码的内容。

这不是宽松 schema migration 层：未知键不会被静默忽略，字符串不会被随意强转成其他对象。

## ResearchContract

字段：`contract_id`、`question`、`protocol_id`、`experiment`、`budget`。

不变量：

- `contract_id` 和 `question` 在协议校验时必须是非空字符串。
- 当前只接受已注册的 `protocol_id`。
- `budget` 只能包含 `max_runs`，且必须是整数；低于协议 `required_runs` 会被拒绝。更大预算不会扩大固定 seed 集。

## ExperimentSpec

字段：`spec_id`、`build`、`stage`、`baseline`、`variant`、`metric`、`comparison_kind`。

不变量：

- `spec_id` 必须是非空字符串。
- 当前只有一个 baseline 和一个 variant；stage、协议 seed 和统计协议始终共享。
- `comparison_kind` 默认为 `mechanism`，也可为 `configuration`，其他值拒绝。
- 两个 arm 的 `arm_id` 必须是非空字符串且互不相同。
- 单个 `ExperimentSpec` 仍只有 baseline/variant；多候选由 `CandidateSet` 组合多个 contract，不展开为单个 experiment 内的 arms 集合。

## CandidateSet

字段：`question`、`candidates`、`top_k`、`correction`。`candidate_set_id` 由完整候选计划的内容哈希派生，不由调用方指定。

不变量：

- 至少两个 `ResearchContract`，所有候选共享 question、baseline、build、stage、metric、protocol、comparison_kind 和预算。
- `top_k` 必须落在候选数内，`correction` 当前固定为 `bonferroni`；总数和总预算有上限。
- 候选集不改变单个 contract 的 baseline、stage、seed 或统计协议，不能事后删候选或替换有利样本。

## CandidateSpace / CandidateRule / CandidateProposal

`CandidateSpace` 字段为 `base_contract`、`rules`、`max_candidates`；`CandidateRule` 字段为 `path`、`values` 和可选的 `template_kind/template_id`；`CandidateProposal` 字段为 `path`、`value` 和可选 `label`。

它们用于把自然语言候选建议约束为白名单内的单路径修改。规则路径在同一 space 内唯一，机制规则必须带模板身份，配置规则不得带模板身份；提案数量、重复值、标识和值域由 `CandidateGenerator` 校验。`base_contract` 只提供共享实验条件，其 variant 不会夹带到生成结果。

生成器只产出现有 `CandidateSet`，不增加另一套执行或报告格式。完整字段约束、类型规则、MCP 传输和宿主复核见 [10_candidate_proposals.md](10_candidate_proposals.md)。

## ExperimentArm

字段：`arm_id`、`world`、`patches`、`build_override`。

不变量：

- baseline 永远为 `world="canonical"`，且不能有 patch 或 build_override。
- mechanism variant 必须为 `world="hypothetical"`，至少一个 patch，且不能有 build_override。
- configuration variant 必须为 `world="canonical"`，不能有 patch，且必须提供非空、与 baseline canonical JSON 不同的完整 `build_override`。
- `build_override` 只覆盖 build，不能修改 stage、seed 或统计协议；具体 build 合法性仍由 `compile_encounter` 和现有静态校验负责，protocol 不复制 build schema。
- patch 只描述声明的机制变量，不允许任意脚本或替换整份 build/stage。

## MechanismPatch

字段：`template_kind`、`template_id`、`path`、`value`、`op`。

不变量：

- `op` 首版只能为 `set_number`。
- `template_kind` 只能为 `characters`、`light_cones`、`relics`、`enemies`。
- `template_id` 只能匹配 `[A-Za-z0-9_-]+`，因此路径分隔符、glob 通配符和空白不会进入 loader。
- `path` 是非空 tuple，组件只允许 string/int（不允许 bool）；必须指向已存在节点。
- 不允许修改 `id`、`type`、以 `_id` 或 `_type` 结尾的结构字段，也不允许通过越界索引增删列表项。
- 原值和新值都必须是有限数值且不能是 bool；同模板同一路径不能重复 patch。

loader 前先校验引用形态，loader 后再校验路径和原值，两个阶段不可互相替代。

## MetricSpec

字段：`metric_id`、`statistic`、`confidence`、`direction`。

当前协议固定为：

- `metric_id="total_damage"`；
- `statistic="paired_mean_difference"`；
- `confidence=0.95`；
- `direction="higher_is_better"`。

`direction="higher_is_better"` 不表示负向效应要被误标为 rejected；它只描述指标偏好，claim 的 relation 仍是精确的 `variant - baseline`。

## VersionFingerprint

字段：`rulebook_hash`、`fixtures_hash`、`data_hash`、`policy_hash`、`implementation_hash`、`config_hash`、`protocol_id`、`artifact_schema_version`、`git_commit`、`variant_hash`。

不变量与用途：

- 执行前必须存在 `rulebook_hash`、`fixtures_hash`、`data_hash`、`implementation_hash`、`config_hash`、`protocol_id` 和 `artifact_schema_version`。
- `protocol_id` 必须与 contract 协议一致。
- `git_commit` 是可选信息字段，不作为内容身份；修改它本身不应制造新 trial。
- 每个 trial 的 `variant_hash` 都必须与已验证 variant metadata 一致：mechanism 对 YAML，configuration 对 build.json。
- `policy_hash` 同时绑定 baseline 与 variant 的有效 policy，configuration 改 policy 不会只记录 baseline；config hash 另行绑定 build/stage/resolved protocol/arm 定义及 override。
- 当前 `artifact_schema_version` 为 2，用来区分带 comparison_kind/build_override 的新契约，旧格式不冒充当前格式。

## RunRecord

字段：`run_id`、`trial_id`、`arm_id`、`cohort`、`seed`、`status`、`observed`、`events`、`final_save`、`modifiers`、`content_hash`、`kind`、`parent_run_id`。

不变量：

- `kind` 首版只能为 `recorded`。
- `run_id` 由 trial、arm、cohort、seed 计算；文件路径和 payload 中的坐标必须一致。
- `status` 在 store 中只接受 `completed` 或 `failed`。
- completed run 要求：`observed.seed == seed`，`observed.total_damage == final_save.state.total_damage`，`observed.truncated == final_save.state.truncated`。
- failed run 使用结构化 `observed.error` 和空 `final_save`，不能伪装成 completed。
- `events` 的 ordinal 必须从 0 连续递增，每个 event ID 都由 run ID、ordinal 和 payload 重算校验。
- `modifiers` 只表示 final modifier 集合；每项 ID 由 run、actor 和引擎 modifier ID 计算。
- variant run 的 `parent_run_id` 指向同 cohort、同 seed 的 baseline run；baseline 没有 parent。

## TrialArtifact

字段：`trial_id`、`spec`、`resolved_protocol`、`fingerprint`、`comparison_set`、`run_ids`、`status`、`caveats`、`failure_reasons`。

不变量：

- `spec` 是完整 `ResearchContract`，resolved protocol 和 fingerprint 必须与已发布 spec.json 一致。
- `run_ids` 顺序固定为 baseline dev、baseline holdout、variant dev、variant holdout；每个队列内部遵循协议 seed 顺序。
- 只有全部协议 run 都存在时才能发布 result。
- `status` 为 `failed` 当且仅当存在 failed run；每个失败 run 都必须有逐条一致的 `failure_reasons`。
- `caveats` 是结构化 dict 的 tuple，保留 actor/text/level/source 等模拟器和编译器元数据，不是自由文本结论。

## ComparisonSet

字段：`comparison_set_id`、`baseline_dev`、`baseline_holdout`、`variant_dev`、`variant_holdout`。

不变量：

- 四个 run ID tuple 显式冻结两臂、两个 cohort 的成员和顺序。
- 派生 run 或 replay 不得向原集合追加成员。
- `comparison_set_id` 由 trial ID 和四个队列计算，读取 result 时会按协议重新构建并比对。

## EvidenceLink

字段：`trial_id`、`artifact_hash`、`run_id`、`event_id`、`modifier_id`、`source_type`。

不变量：

- `source_type` 首版只能为 `simulated`。
- `artifact_hash` 指向包含证据的 artifact，而不是在链接里复制结论数字或文本摘录。
- event/modifier 下钻必须同时提供 `run_id`；同一条链接不能同时选择 event 和 modifier。
- 找不到 final modifier 时，resolver 返回 `unresolved` 和原因，不虚构历史状态。

## Claim

字段：`claim_id`、`trial_id`、`comparison_set_id`、`subject`、`metric`、`relation`、`status`、`premises`、`derivation_steps`、`statistical_metadata`、`scope`、`failure_reason`。

不变量：

- `status` 只能为 `accepted`、`rejected`、`inconclusive`、`stale`。
- `rejected` 专指证据或推导校验失败；variant 效应更差本身不是 rejected。
- `premises` 是 spec、result、variant 和全部相关 run 的 `EvidenceLink`，不是手写结论数字。
- `derivation_steps` 记录取样、paired mean difference 和 bootstrap 等结构化推导。
- `statistical_metadata` 保存 cohort、有效样本数、effect、CI、失败/truncated 清单和前提指纹；验证时仍需从原始证据重建并比对。
- `scope` 保存 source、真实 variant world、validation、cohort、protocol_id 和 comparison_kind；mechanism 为 hypothetical，configuration 为 canonical。
- 逻辑 `claim_id` 只由 subject、premises、derivation steps 计算，不包含 status/failure_reason；存储 record ID 则哈希完整 claim，用于保存不同状态的历史记录。

## ExecutionRecord

字段：`execution_id`、`investigation_id`、`kind`、`attempt`、`parent_execution_id`、`status`、`artifact_status`、`trial_id`、`contract_hash`、`completed_runs`、`total_runs`、`created_at`、`started_at`、`finished_at`、`duration_ms`、`error`、`history`。

不变量：

- 表示一次执行动作，不是战斗结果或世界线；run_id 仍只属于 RunRecord。
- `kind` 为 `initial / cache_hit / replay_check / resume`，`status` 为 `draft / validated / queued / running / validating / completed / failed / cancel_requested / cancelled`，`artifact_status` 为 `partial / complete`。
- execution_id 由 investigation、contract、kind、attempt 计算；resume/replay/cache 通过 parent_execution_id 关联，不冒充独立复核。
- history 保存每次状态迁移的时间、状态、进度、artifact_status 和说明，只允许在原前缀上追加。

## InvestigationState

字段：`investigation_id`、`contract`、`status`、`active_execution_id`、`execution_ids`、`trial_id`、`completed_runs`、`total_runs`、`artifact_status`、`next_action`、`revision`、`created_at`、`updated_at`。

不变量：

- 保存完整 ResearchContract 和恢复所需引用/进度，不复制 run、event 或 claim。
- status/artifact_status 与 ExecutionRecord 共用词表；execution_ids 只允许追加，revision 不得回退。
- ExecutionRecord 与 InvestigationState 都复用递归冻结、严格 round-trip 和 canonical JSON。

## Canonical JSON 与内容哈希

`research_schema.canonical` 是唯一 canonical JSON 与内容哈希入口：

- `canonical_json()`：sort keys、保留 Unicode、紧凑分隔符、`allow_nan=False`。
- `canonical_bytes()`：上述 JSON 的 UTF-8 bytes。
- `content_hash()`：对 canonical bytes 计算完整 SHA-256。
- `canonical_round()`：把 JSON 形状中的 float 统一舍入到六位小数，用于 kernel 输出。

不支持的对象、非字符串 mapping key、NaN 和 Inf 都直接拒绝，没有 `default=str` 兜底。原始模拟数值不会因为存储而被预先舍入；只有公开展示和最终统计输出才使用 `canonical_round()`。
