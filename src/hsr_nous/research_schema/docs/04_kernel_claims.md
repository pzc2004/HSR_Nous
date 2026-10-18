# 可信统计内核与 Claim 重算

`research_core.kernel` 是无 I/O 的纯函数层；文件系统、artifact 和当前指纹编排全部位于 `ClaimValidator`。

## Fraction 与基础统计

所有数值样本先经过 `Fraction(str(x))` 转换。bool、NaN、Inf、空样本和无法解释为有限数值的输入都会拒绝。

当前纯函数包括：

- `mean(values)`：算术平均值。
- `variance(values)`：**population variance**，分母是 `N`，不是样本方差的 `N-1`；与既有 Monte Carlo 口径一致。
- `quantile(values, q)`：排序后做线性插值；单样本直接返回该值，`q` 必须位于 `[0, 1]`。
- `distribution(values)`：返回 `n`、`mean`、`variance`、`stdev`、`minimum`、`p5`、`p50`、`p95`、`maximum`。
- `paired_diff(baseline, variant)`：返回逐对 `variant - baseline` 的展示值。
- `compare(...)`：按协议 seed 对齐两臂并生成 paired comparison。
- `confidence_interval(...)`：对 paired differences 做固定参数的 percentile bootstrap。
- `build_claim(...)` / `validate_claim(...)`：构建和比对纯结构化 claim。

公开展示值统一六位 `canonical_round()`，但原始 run 数值不因此改写。

## 精确中间 Paired Difference

`compare()` 内部先用 `Fraction` 形成精确差值 tuple：

```text
exact_difference[i] = Fraction(str(variant[i])) - Fraction(str(baseline[i]))
```

effect 和 bootstrap 始终消费这组未舍入差值。只有报告中的 `paired_differences` 展示数组和最终输出才做六位 rounding，避免“先把每个差值舍入，再计算均值和 CI”的中间精度损失。

`compare()` 还要求 baseline/variant 的 seed 集合与指定 cohort 完全一致。缺 seed、额外 seed、dev/holdout 错位、空样本和非有限值都直接拒绝。

## Paired Percentile Bootstrap

当前 holdout CI 的计算过程是：

1. 按协议 holdout seed 顺序形成 `variant - baseline` 差值。
2. 使用 resolved protocol 的 `bootstrap_seed` 创建独立 `Random`。
3. 每次从 `N` 个配对差值中有放回地抽取 `N` 个索引，计算该重采样集合的 paired mean difference。
4. 重复 resolved protocol 的 `bootstrap_resamples` 次；当前固定为 2000 次。
5. 将均值排序，在 `(1-confidence)/2` 与 `1-(1-confidence)/2` 两个分位点做线性插值，得到 percentile CI。
6. 只对最终 effect、CI 和展示差值做六位 rounding。

实验协议与 ClaimValidator 不接受另一套重采样 seed 或次数。常数差值的 CI 退化为同一个常数；非平凡序列由固定 golden 测试锁定。

## CI 的含义与常见误解

当前 CI 描述的是：**在指定模拟实现、build/stage/policy、协议 seed 集和 paired bootstrap 方法下，holdout 平均配对差值的重采样分布区间**。

它不代表：

- 真实游戏中存在同样的概率分布；
- 每一局伤害都落在该区间；
- variant 是全局最优或已经解决多候选选择偏差；
- CI 跨 0 时证明“没有效应”，此时只能判为 inconclusive；
- CI 位于 0 以下时属于 rejected；负向效应同样可以是 accepted 的方向性结果。

accepted 只表示结构化证据和推导成立，并且 holdout CI 不含 0。它不替代真实游戏校准。

## ClaimValidator 的独立重算

`ClaimValidator` 不读取 claim 携带的统计数字作为事实，而是执行以下步骤：

1. 从 `trial_id` 重新读取 spec，解析 contract、resolved protocol 和 fingerprint。
2. 从 result 读取冻结的 `ComparisonSet`，重建两臂 dev/holdout 的 run 顺序。
3. 读取全部相关 run；store 已校验内容哈希、坐标、事件/modifier ID 和 observed/final_save 一致性。
4. 读取并验证唯一 hypothetical variant 的 metadata 和每份 YAML，确认 `variant_hash` 与 fingerprint 一致。
5. 从 completed 且未 truncated 的 `observed.total_damage` 重新形成配对样本；failed/truncated 清单单独保留。
6. 重新计算 dev/holdout 分布、paired comparison、bootstrap CI 和 expected claim。
7. 重建 spec/result/variant/all-run premises，并逐项比较 claim 的 effect、CI、n、cohort、seed、derivation steps、status 和证据 hash。
8. 重新收集当前 fingerprint，与 claim 前提指纹比较（git_commit 不作为内容身份）。

任何证据或推导不一致都会生成新的 `rejected` claim record，不能通过修改状态、换 holdout、删除失败样本或重复提交洗成 accepted。

## 状态与历史

- **accepted**：expected claim 完全一致，holdout 有效且 CI 不含 0。
- **inconclusive**：holdout failed/truncated/有效样本不足/比较不可用，或 CI 跨 0。
- **rejected**：证据加载、artifact 完整性或 claim 推导校验失败。
- **stale**：当前内容指纹与前提指纹不同。

stale 是通过 `dataclasses.replace` 生成的派生视图，不发布新的 claim record，也不修改历史 accepted 文件。ReportComposer 可为这个派生视图生成状态报告，但不会输出方向性结论。

## claim_id 与 claim record ID

两者服务于不同目的：

- `claim_id`：逻辑推导身份，只由 `subject + premises + derivation_steps` 计算。status 和 failure_reason 不参与，因此同一推导的状态视图不会改变逻辑 ID。
- claim record ID：完整 `Claim` 的内容哈希，用于 `claims/<record_id>.json` 的不可覆盖存储。它包含 status/failure_reason，使 rejected 等新记录可以与历史 accepted 共存。

发布和读取 claim 时，store 同时校验逻辑 `claim_id` 绑定和 record 内容哈希。

## 报告前的第二次验证

`ReportComposer.compose()` 接收 `ClaimValidationResult` 后，还会再次调用 `ClaimValidator.validate()`。报告使用的 spec、comparison、cohort 统计和 claim 都来自这次重算，而不是调用方自行填入的 metrics。
