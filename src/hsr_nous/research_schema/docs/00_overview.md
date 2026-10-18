# Research Schema：确定性研究后端总览

> **实现说明**：本文档描述当前已经落地的 frozen dataclass 契约、固定协议、执行与证据链、纯统计内核和 JSON 报告，不描述尚未实现的 Agent 交互形态。

## 目标

研究后端解决的是一个窄而明确的问题：比较一个 baseline 与一个 variant，并让结论能够重新计算、重放和逐层追溯。当前支持两类对照：`mechanism` 用 hypothetical 模板 patch 研究机制反事实，`configuration` 用完整 `build_override` 比较 canonical 配装或配队。`comparison_kind` 与 `world` 是两个独立维度，configuration 不再被误标为 hypothetical。

当前实现保证：

- 实验输入是严格、递归冻结的 `ResearchContract`，协议参数只能来自注册表。
- mechanism 只通过声明式 `set_number` 修改既有数值；configuration 只通过完整 `build_override` 替换 build。两种路径都不改写 canonical 文件。
- 两臂使用同一组 dev/holdout seed，原始 run、事件、终态和 final modifier 全部保留。
- 统计值由纯函数从原始证据重算，报告数字不由调用方直接提供。
- `accepted`、`inconclusive`、`rejected`、`stale` 具有不同语义，失败样本不能被静默删除。
- claim、report、run、event、final modifier 都有可解析的内容身份和证据链接。

## 非目标

当前版本不做以下工作：

- 不接 DSH、MCP、前端或共享 Memory。
- 不做多候选搜索、winner's curse 修正或多重比较协议；首版只有一个 baseline/variant 对照。
- 不声称模拟结果已经过真实游戏校准，也不声称 accepted 等于真实游戏正确或全局最优。
- 不导出完整离线模板闭包；replay 仍要求指纹对应的 canonical 模板根可用。
- 不把只读权限和 SHA-256 当作同用户恶意进程的强安全沙箱。
- 不保存事件时刻的 modifier 生命周期代际，只承诺 final modifier 的全量详情。

## 三类模块的职责

| 模块 | 当前职责 | 明确不负责 |
|---|---|---|
| `research_schema` | frozen dataclass 数据契约、严格 round-trip、canonical JSON、内容哈希和输出 rounding | 不执行模拟、不解析协议、不读写 artifact |
| `research_protocol` | 注册并解析 `paired-v1`，校验 contract、patch、预算和必填指纹 | 不调用模拟器、不计算 CI、不生成 claim 或报告 |
| `research_core` | variant 物化、指纹、runner、artifact store、统计 kernel、claim 重算、证据下钻和 JSON 报告 | 不做 Agent 编排、真实客户端 expected、前端或多候选搜索 |

`common.research_root()` 只负责研究产物根的路径解析；`sim` 与 `sim_schema` 提供编译、战斗、日志、结果分类和版本指纹等既有能力。

## 完整数据流

```text
ResearchContract
    │
    ▼
VariantMaterializer.prepare
    ├─ mechanism：loader 前校验 → 统一加载 → 完整复核 → 内存 set_number
    ├─ configuration：完整 build_override，不调用模板 loader
    └─ effective_build + parent/variant 内容哈希
    │
    ▼
collect_research_fingerprint
    ├─ collect_version_fingerprint（既有五类信息）
    ├─ 两臂 effective policy
    └─ implementation/config/variant/protocol/artifact schema v2
    │
    ▼
ArtifactStore.publish_spec / publish_variant（mechanism YAML 或 configuration build.json）
    │
    ▼
TrialRunner
    ├─ baseline：experiment.build + 默认模板根编译一次
    ├─ variant：effective_build；mechanism 叠加覆盖根，configuration 仍用默认根
    ├─ 每个 seed 新建 engine
    ├─ setup 前 StructuredLogger，setup 后 RunRecorder
    └─ 发布全部 completed/failed run 与 result/ComparisonSet
    │
    ▼
ClaimValidator
    ├─ 重新读取 spec/result/run/variant
    ├─ 校验 artifact、指纹、seed、run 顺序和失败清单
    ├─ 从 observed 取样（store 已与 final_save 交叉核验）
    └─ compare / CI / build_claim / validate_claim
    │
    ├── accepted / inconclusive：发布对应 claim record
    ├── rejected：发布新的 rejected claim record
    └── stale：只生成派生视图，不改写历史 claim
    │
    ▼
ReportComposer（发布前再次 validate）
    ├─ accepted/inconclusive：渲染结构化统计与推导
    ├─ rejected/stale：只渲染状态和原因，不渲染方向性结论
    └─ publish_report / read_report
    │
    ▼
resolve_evidence：claim → trial → run → event / final modifier
```

## 可信边界

### 输入边界

`validate_patch_reference` 在文件查找前拒绝非法 kind、template ID、path 和新值；完整 `validate_contract` 在模板加载后再检查路径存在性、原值、预算、metric、arm 和重复 patch。调用方不能传自定义 seed、holdout 或 bootstrap 参数。

### 证据边界

runner 不信任单次成功返回值而丢弃异常：编译失败和单局失败都形成 failed run。store 在 publish/read 两侧核对 run 坐标、内容哈希、事件/modifier ID，以及 completed run 的 `observed` 与 `final_save.state` 一致性。result 还会按 spec 重建全部协议 run 的成员和顺序。

### 统计边界

kernel 是无 I/O 纯函数层。中间 effect 和 bootstrap 使用未舍入的 `Fraction` 差值；展示值才做六位 rounding。ClaimValidator 不相信 claim 已有的均值、CI、样本数、seed 或状态，而是重新加载证据并构建 expected claim。

### 报告边界

`ReportComposer.compose()` 只接受 `ClaimValidationResult`，并在渲染前再次调用 `ClaimValidator.validate()`。因此即使调用方伪造一个带有手写统计字段的结果对象，也不能直接得到 accepted 报告。report 发布和读取还校验 `spec.trial_id` 与目录 trial 一致。

### 文件系统边界

canonical bytes、完整 SHA-256、临时文件加 `os.replace`、只读位和路径 resolve 检查用于防止误写、误改和意外路径逃逸。它们不是针对同用户恶意进程的安全隔离；该进程仍可能修改文件权限、替换文件或伪造整套数据，因此可信结论还依赖独立重算和指纹变化检测。

## 停云端到端例子

当前正式测试使用只读的 `data/battles/demo_停云白板.yaml` 构造 contract：baseline 是停云 canonical E0 配置，variant 对角色 `1202` 的 `base_stats.atk` 声明一个 `set_number` patch。实验执行 `paired-v1` 的全部协议 run，而不是为了得到某种状态另换 seed。

端到端检查顺序是：

1. canonical 与 variant 分别编译，确认只有 variant 根中的停云模板命中覆盖，canonical 文件字节不变。
2. 两臂跑完 dev/holdout 的全部 run，保存 observed、events、`save_state()` 和 final modifier。
3. 再次运行同一 contract，确定性文件逐字节一致；不同内容不能覆盖同 ID artifact。
4. ClaimValidator 从真实 64 个 run 重建 paired 样本，按 holdout CI 和失败清单决定 claim 状态。
5. ReportComposer 再次验证后发布 JSON，报告能下钻到 run、event 和 final modifier；不存在的 modifier 返回 `unresolved`。
6. 手写统计、换 seed/cohort、漏 run、伪证据 hash 都会形成 rejected；当前指纹变化形成 stale 派生视图。

本文不固化该例子的伤害效应值或 CI；这些数字始终应从 artifact 现场重算。

## 黄泉配装与配队例子

当前另有两类 canonical configuration 验收，均从只读 `demo_黄泉队` 用 Python 构造，不新增 YAML fixture：

- **配装对照**：baseline 为黄泉 `1308` 的 `feet={set_id:"101", main:"spd", subs:{}}`，variant 仅把同一 feet 的 main 改为 `atk_pct`。其余队伍、光锥、遗器、stage 和 policy 完全一致，用于验证 build_override、build.json、真实 64 局、canonical flags 和报告重算。
- **配队对照**：从原始 demo 独立构造，保持成员顺序、stage 和 policy，仅把 `1403` 替换为 `1202`，用于验证实际编译队伍、parent lineage、指纹和证据下钻；不预设强弱方向。

两个场景都不得通过换 seed 追求预期状态。攻击鞋场景的外部社区预期只作参照，不进入内核；若实际统计不符，必须保留并解释，而不是更换场景。停云 mechanism 对照仍使用 hypothetical，与 configuration 的 canonical 语义互不串扰。

## 文档导航

章节索引以 [`../README.md`](../README.md) 为唯一入口，并由 `tests/test_doc_lint.py` 做 README 与磁盘文件的双向一致性检查。
