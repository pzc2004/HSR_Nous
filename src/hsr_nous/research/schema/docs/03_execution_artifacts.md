# Variant、执行与 Artifact Store

本章描述当前 `research/core.variants`、`fingerprint`、`runner`、`artifacts` 以及 `common.research_root` 的实际行为。

## 统一模板加载与两类 Variant

### 只读 loader

`BuildCompiler.load_template()` 是受支持的只读模板加载入口，旧 `_load_template()` 保留为兼容别名。根查找顺序、同根撞名处理、legacy 排除和 YAML 严格解析都继续由 BuildCompiler 负责，research 不复制这些规则。

### 内存准备阶段

`PreparedVariant` 同时携带 `comparison_kind`、`world` 和 `effective_build`：

- **mechanism**：先逐个调用 `validate_patch_reference`，再经统一 loader 读取 canonical 模板，完整 `validate_contract` 复核后只在内存副本上 `set_number`。保留 documents、parent/variant 模板哈希和 YAML 覆盖根。
- **configuration**：不调用模板 loader，`documents=()`；`parent_base_hash=hash(baseline_build)`，`variant_hash=hash(build_override)`，`effective_build=build_override`。具体 build 合法性留给编译器。

两类 `variant_id` 都绑定 comparison_kind、world、parent/variant hash、patch 和 hypothesis；configuration 因而同时绑定 baseline build 与 override。准备阶段不写 canonical 文件，也不要求先有 trial ID。

### 发布与编译优先级

mechanism 发布 `variant.json` 和实际 YAML；configuration 发布 `variant.json` 与 canonical `build.json`，不伪造空 YAML 文档。metadata 同时记录 comparison_kind/world、parent/variant hash、patch、hypothesis 和文档清单。`read_variant()` 按类型分别校验 build.json 或机制 YAML，以及 metadata hash、variant ID 推导绑定和路径安全；configuration 还会与已发布 spec 对账 `parent_base_hash == content_hash(baseline experiment.build)`，mechanism 的 parent hash 语义不变。

mechanism variant 编译使用 `(variant_root, *RUNTIME_TEMPLATE_ROOTS)`，覆盖根先命中。configuration 两臂都使用默认模板根，variant 直接编译 `effective_build`。baseline 始终编译原 `experiment.build`，canonical 文件字节不变。

## 指纹

`collect_research_fingerprint()` 先复用 `sim.montecarlo.collect_version_fingerprint(policy_source=...)`，再补充：

- `implementation_hash`：按相对路径和文件内容哈希 `sim`、`sim_schema`、`research/schema`、`research/protocol`、`research/core` 的 Python 源码及 `uv.lock`。
- `config_hash`：comparison_kind、canonical build/stage、resolved protocol、baseline/variant arm 定义及 build_override 的 canonical JSON 哈希；仅语义类型变化也会改变配置身份。
- `variant_hash`：mechanism 的实际 YAML 内容哈希，或 configuration 的 build_override 内容哈希。
- `policy_hash`：同时绑定两臂 effective build 中的 policy，避免 configuration 改 policy 只记录 baseline。
- `protocol_id` 和 `artifact_schema_version`；当前 schema 为 2。

缺少执行必需的 rulebook/fixtures/data/implementation/config 指纹会在战斗前拒绝。`git_commit` 仅保留为信息字段，不参与 trial 内容身份；dirty 源码和锁文件变化则会改变 implementation identity。

## research_root 与目录布局

`common.research_root()` 按以下优先级解析：

1. `HSR_NOUS_RESEARCH_ROOT` 环境变量；
2. `Path.home() / "HSR_Nous"`。

默认不会写当前仓库或 CWD。ArtifactStore 使用 `<research_root>/artifacts`；测试始终传 `tmp_path`，不写用户 home 或 `data/library`。

当前目录布局：

```text
<research_root>/artifacts/trials/<trial_id>/
├── spec.json                 # contract、resolved protocol、fingerprint、spec_hash
├── metadata.json             # started/finished 等墙钟元数据，可独立更新
├── variants/<variant_id>/
│   ├── variant.json          # comparison_kind/world、hashes、patch/hypothesis、文档清单
│   ├── <kind>/<id>_variant.yaml  # 仅 mechanism
│   └── build.json            # 仅 configuration 的完整 effective build
├── runs/<run_id>.json        # observed、events、final_save、final modifiers、content_hash
├── result.json               # 全部 run、ComparisonSet、状态、caveats、失败原因
├── claims/<claim_record_id>.json
└── reports/<report_id>.json
```

`ARTIFACT_SCHEMA_VERSION` 当前为 2。claim record ID 与逻辑 `claim_id` 不同：前者哈希完整 claim（含状态），后者只哈希 subject/premises/derivation。这样可在不覆盖历史的情况下保存 accepted、rejected 等不同记录。

候选报告使用独立的 `candidate-v1` schema，路径为 `candidate_sets/<candidate_set_id>/reports/<report_id>.json`。它保存候选计划、dev 全量排名、holdout 修正结果、selected 和各 trial/report 链接；不包含执行时间或 cache/initial 标记，保证同计划同证据时身份稳定。

## 全 SHA-256 内容身份

所有 ID 都是完整的 64 位小写十六进制 SHA-256，不使用短哈希：

| 身份 | 计算内容 |
|---|---|
| `trial_id` | contract、resolved protocol、内容指纹（排除信息性 git_commit） |
| `run_id` | trial ID、arm ID、cohort、seed |
| `event_id` | run ID、ordinal、canonical event payload |
| `modifier_id` | run ID、actor ID、引擎 modifier ID |
| `comparison_set_id` | trial ID 与四个冻结 run 队列 |
| `variant_id` | comparison_kind、world、parent/variant hash、patch、hypothesis |
| 逻辑 `claim_id` | subject、premises、derivation steps，不含 status/failure_reason |
| claim record ID | 完整 Claim 内容，用于不可覆盖的历史存储 |
| `report_id` | 完整报告内容 |

同坐标产生不同结果会撞 run ID 并暴露冲突，而不是覆盖旧世界线。

## TrialRunner 逐步行为

`TrialRunner.run(contract)` 当前按以下顺序执行：

1. 用 `VariantMaterializer.prepare` 完成对应类型的校验和内存准备。
2. 收集并验证完整 fingerprint，包括两臂有效 policy。
3. 发布或幂等核对 spec.json，并将 started 时间写入独立的 metadata.json；它不参与 trial/run/result 内容身份。
4. 发布 variant：mechanism 写 YAML，configuration 写 build.json。
5. baseline 编译 `experiment.build`，variant 编译 `effective_build`；mechanism 额外叠加覆盖根，configuration 两臂都用默认模板根。
6. 按 baseline dev、baseline holdout、variant dev、variant holdout 顺序遍历固定 seed。
7. 每个 seed 通过 `CombatEngine.from_compiled(..., mode, seed)` 创建全新 engine，避免串态。
8. 在 `setup()` 前挂 `StructuredLogger`，在 setup 后、run 前挂 `RunRecorder`。
9. 运行战斗并保存：`classify_outcome` 的完整 observed（含真实 ult/energy 统计）、全部 structured events、`save_state()` 全精度终态和 final modifier 全字段。
10. variant run 写入同 seed baseline 的 `parent_run_id`；随后逐 run 发布 canonical JSON。
11. 全部协议 run 都有记录后，构建 `ComparisonSet`、caveats 和精确失败原因，发布 result.json。

同 contract 重跑会重新核对确定性 payload：同 ID 同字节是幂等 no-op，不同内容抛 `ArtifactConflictError`。墙钟 started/finished 可以变化，但 spec/run/result/claim/report 的 replay 字节不因此改变。

## Harness 持久化与 Runner 生命周期

`TrialRunner.run()` 另支持两个可选参数：`progress(completed,total)` 和 `skip_existing`（默认 False）。progress 在每个 run 发布或已有 run 验证复用后调用；回调异常向上抛出，不发布 result。`RunCancelledError` 用于安全停止，已发布 run 不受影响。

`skip_existing=True` 时，runner 按协议坐标逐个 `read_run` 验证已有 run，只创建缺失世界线；已有 run 的 arm/cohort/seed/parent lineage 不符会拒绝，而不是复用错误证据。默认 False 仍执行全量重放和逐字节幂等核对。

ExecutionRecord 与 InvestigationState 分别保存到 `executions/<execution_id>.json` 和 `investigations/<investigation_id>.json`，使用 canonical bytes、全 SHA-256 和原子更新。ExecutionRecord.history 只能追加，InvestigationState.revision 不能回退且 execution_ids 只能追加；它们不改变 trial artifact 的不可覆盖语义。详细状态机见 [06_harness.md](06_harness.md)。

## 失败保留与 observed/final_save 交叉核验

编译失败会让对应 arm 的协议 run 全部成为 failed run，另一个 arm 仍继续执行。单局构造、setup、run、分类或存档异常也会形成 failed run，而不是删除样本。

failed run 使用：

```text
status = failed
observed = {"error": {"type": ..., "message": ...}}
final_save = {}
```

completed run 在 publish/read 两侧强制核对：

- `observed.seed` 与 run 坐标 seed 一致；
- `observed.total_damage` 与 `final_save.state.total_damage` 一致；
- `observed.truncated` 与 `final_save.state.truncated` 一致，并且都是 bool。

ClaimValidator 因而可以只从 `observed.total_damage` 取样；交叉核验已经在 store 边界完成。result 还会精确比较 failed run 与 failure reason，缺失或篡改失败样本不能被静默接受。

## Store 完整性机制

- **Canonical bytes**：spec/run/result/claim/report 发布均为 canonical JSON；读取时拒绝非发布形态的 JSON。
- **原子发布**：同目录临时文件写入、flush/fsync、设置只读，再 `os.replace`。
- **幂等与冲突**：同 ID 同字节不重复写；同 ID 不同字节抛 `ArtifactConflictError`，永不覆盖。
- **只读发布**：发布文件设为只读；POSIX 测试精确 mode，其他平台仍依靠冲突和哈希检查。
- **路径防逃逸**：ID 只接受全 SHA-256，variant 路径组件有闭合格式，resolve 后必须仍在 store root 内；符号链接逃逸也会被拒绝。
- **读取校验**：重算 spec/run/result/claim/report/variant 的内容哈希和逻辑身份。
- **Cohort 完整性**：result 读取按 spec 重建 seed、run 顺序、ComparisonSet、lineage 和失败清单。
- **Report 归属**：`publish_report` 和 `read_report` 都要求 `spec.trial_id` 等于路径 trial。
- **Variant 完整性**：`read_variant` 不仅读取 metadata，还重新验证每份 YAML。

## 已知安全与能力边界

只读权限、SHA-256 和原子发布是**完整性与防误改护栏**，不是同用户恶意进程的强安全沙箱。硬隔离需要后续独立进程、OS 用户或容器机制，当前没有实现。

replay 仍依赖指纹对应的 canonical 模板根，完整离线模板闭包导出尚未完成。当前实现也不提供事件时刻 modifier 生命周期、真实游戏校准或全局最优保证。
