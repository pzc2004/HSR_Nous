# paired-v1 实验协议与统计纪律

`paired-v1` 是当前唯一注册的实验协议。`resolve_protocol()` 只从 `PROTOCOL_PROFILES` 注册表解析，调用方不能通过额外参数覆盖 seed、holdout 或 bootstrap 配置。

## 固定参数

| 参数 | 当前值 | 含义 |
|---|---|---|
| `mode` | `roll` | 每个 seed 创建独立随机世界线 |
| dev seed 为 `0..15` | 16 个连续 seed | 只用于探索性展示 |
| holdout seed 为 `16..31` | 与 dev 不相交的 16 个连续 seed | 唯一可用于 accepted 方向性结论的 cohort |
| `min_valid_n=16` | 每臂每个 cohort 的配对有效样本要求 | 不足时 inconclusive |
| `required_runs=64` | `2 × (16 + 16)` | 两臂全部 dev/holdout run 的总数 |
| `bootstrap_resamples` | 2000 | paired percentile bootstrap 重采样次数 |
| `confidence` | 0.95 | CI 置信度 |
| `bootstrap_seed` | 0 | bootstrap 专用固定随机种子 |

协议文档与代码镜像由 `tests/test_research_protocol.py` 校验，上述起止 seed 和数值不应独立手工漂移。

## Cohort 不变量

`ResolvedProtocol` 在构造时检查：

- dev 和 holdout 都不能为空，seed 必须是非负整数且不能是 bool。
- 每个 cohort 内部不得有重复 seed，dev 与 holdout 不得相交。
- `min_valid_n` 必须为正整数，并且不超过两个 cohort 的样本数。
- bootstrap 次数必须为正整数，confidence 必须位于 0 和 1 之间，bootstrap seed 必须是非负整数。
- `required_runs` 由两个 cohort 的长度和两臂数派生，不是另一个可独立修改的配置。

baseline 与 variant 使用完全相同的 dev 和 holdout seed 序列。配对比较按 seed 对齐，不允许把不同 seed 的样本拼接成一对。

## 预算

`ResearchContract.budget` 只允许 `max_runs`：

- 小于 `required_runs` 时，在任何战斗执行前拒绝。
- 等于或大于 `required_runs` 时通过；更大的值只表示资源上限宽松，不改变 seed、样本数、bootstrap 次数或结论规则。
- 不接受尚不执行的 timeout 等额外预算字段。

## 两类对照与 World

`comparison_kind` 与 `world` 是独立维度：

- `mechanism`：baseline 为 canonical，variant 为 hypothetical，必须有机制 patch 且不能有 build_override。
- `configuration`：两臂都是 canonical，variant 必须有完整 build_override 且不能有 patch。
- baseline 在任何类型下都必须 canonical，并且不能携带 patch 或 build_override。

configuration 的 override 必须非空，且与 baseline build 的 canonical JSON 不同；否则拒绝。它只替换 build，stage、seed 和统计协议保持不变。protocol 不重新实现 build schema，具体队伍、装备、星魂、光锥、遗器和 policy 合法性仍由 `compile_encounter` 与现有静态校验负责。

## Patch 与 Contract 校验

### Loader 前置：`validate_patch_reference`

在 `BuildCompiler.load_template` 之前逐个 patch 校验：

- 只允许 `op="set_number"`。
- kind 必须属于 `characters` / `light_cones` / `relics` / `enemies`。
- template ID 只能匹配 `[A-Za-z0-9_-]+`，拒绝 `../`、`*`、路径分隔符和空白等输入。
- path 非空，组件只能是 string/int，不能是 bool；结构 ID/type 字段禁止修改。
- 新值必须是有限数值且不能是 bool。

这一步保证未校验的 kind/template ID 不会进入 glob 或文件系统查找。

### 加载后复核：`validate_contract`

模板加载后继续检查：

- `contract_id`、`question`、`spec_id` 非空，协议已注册，预算足够。
- 只有一个 baseline/variant，arm ID 非空且不同。
- baseline 是 canonical 且无 patch/override；mechanism variant 是 hypothetical 且至少一个 patch，configuration variant 是 canonical 且有非空、不同的完整 build_override。
- patch 目标模板和 path 必须存在，原值是有限数值且不是 bool。
- 不允许同模板同一路径重复 patch，不允许越界增删列表项。
- metric 只能是 `total_damage` + `paired_mean_difference` + 协议 confidence + `higher_is_better`。

`validate_fingerprint()` 另外拒绝缺少执行必需 rulebook/fixtures/data/implementation/config/protocol/artifact schema 指纹的输入。`git_commit` 缺失不是失败理由，因为真正身份由内容哈希承担。

## 状态语义

| 状态 | 当前含义 | 是否允许方向性结论 |
|---|---|---|
| `accepted` | 证据和推导完全一致，holdout 无 failed/truncated，有效配对数达到 `min_valid_n`，且 holdout CI 不含 0 | 允许，但仅限指定模拟版本、hypothesis 和协议 |
| `inconclusive` | holdout 有 failed/truncated、有效样本不足、无法形成比较，或 CI 跨 0 | 不允许；可展示结构化统计和失败原因 |
| `rejected` | artifact、证据链接、run 成员或 claim 推导校验失败 | 不允许；只呈现校验失败及原因 |
| `stale` | 当前内容指纹与 claim 前提指纹不一致 | 不允许；这是派生视图，不改写历史 accepted claim |

CI 完全位于 0 以下也可以 accepted：这表示在该协议下得到了负向效应，而不是证据校验失败。`rejected` 不能被用作“结果不喜欢”或“variant 更差”的标签。

## 统计纪律

- dev 只作探索性展示，不能用于 accepted 的方向性结论。
- holdout 的 failed/truncated run 必须保留并计数；不能删除后假装样本完整。
- 有效配对数不足或 CI 跨 0 时只能 inconclusive。
- 证据或推导不一致时才进入 rejected；版本变化则进入 stale。
- 首版只有一个 variant，不处理多候选搜索、多重比较或 winner's curse。
- accepted 不表示真实游戏已经校准，也不表示全局最优；真实游戏验证仍是 `pending_real_validation`。

统计实现和 CI 的进一步解释见 [04_kernel_claims.md](04_kernel_claims.md)。
