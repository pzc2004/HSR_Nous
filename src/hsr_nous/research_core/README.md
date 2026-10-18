# research_core

确定性研究执行、原始证据、可信统计与 JSON 报告。当前包含 variant、指纹、
artifact store、`TrialRunner`、纯统计 kernel、claim 校验和报告，不接 DSH/MCP/前端/Memory。

## 执行链

`VariantMaterializer` 经 `BuildCompiler.load_template` 的同一加载漏斗读取 canonical
模板，先跑 `research_protocol` 校验，再只在内存在副本上应用 `set_number`。
`ArtifactStore` 在 `artifacts/trials/<trial_id>/variants/<variant_id>/` 发布实际
YAML；variant 编译根排在默认根之前，canonical 文件不写入。

指纹复用 `sim.montecarlo.collect_version_fingerprint`，并增加
implementation/config/variant/protocol/artifact schema 绑定。implementation hash 覆盖
`sim`、`sim_schema`、三个 research 包的 Python 源码及 `uv.lock`。`git_commit` 仅是
信息字段，不参与 trial 内容身份。

`TrialRunner` 每个 arm 编译一次，每个协议 seed 创建全新 engine，并在 `setup()` 前挂
`StructuredLogger`，在 setup 后、run 前挂公开 `RunRecorder`。每局保存带真实
ult/energy 统计的 observed outcome、全部 structured events、全精度 `save_state()` 和
final modifier 全字段。编译或单局异常写成 failed run；result 只在全部协议 run 均有
记录后发布，并冻结 run 顺序与 `ComparisonSet`，failure reason 与原始 failed run 逐条
精确一致。同输入重跑逐字节核对，同 ID 不同内容抛 `ArtifactConflictError`。

## 可信统计、Claim 与报告

`kernel.py` 是无 I/O 纯函数层：样本先转 `Fraction(str(x))`，mean/population variance/
分位数/paired diff 用有理数计算；effect 与 bootstrap 始终消费未舍入差值，只有公开
paired_differences 和最终输出做六位 rounding。holdout 同 seed 的 `variant - baseline`
percentile bootstrap 固定消费 resolved protocol 的重采样数、置信度和 seed；空样本、
非有限值、seed/cohort 错位直接拒绝。

Dev 只作探索展示，accepted 的方向性结论只看 holdout。holdout failed/truncated/有效样本
不足或 CI 跨 0 为 inconclusive；证据或推导校验失败为 rejected；当前指纹与前提不一致为
stale 派生视图，不改写历史 claim。首版只有一个 baseline/variant，不解决多候选搜索或
winner's curse。

`ClaimValidator` 从 spec/result/run/variant 重新加载证据并重跑 compare/CI/build_claim，
不信任 claim/report 携带的数值。逻辑 `claim_id` 只由主体、前提和推导计算，不含
status/failure_reason；为同时保留 accepted/rejected 等历史且不覆盖，claim 文件名使用
完整 claim 内容的独立 record hash。`ReportComposer` 发布前再次调用 validator，只输出
JSON；accepted 必须有完全一致的重算，rejected/inconclusive/stale 不输出方向性结论。
结论句固定带 `simulated/hypothetical/pending_real_validation`。

## Artifact 边界

- spec/run/result 使用 canonical JSON 和全 SHA-256 ID；临时文件与 `os.replace` 原子发布，
  同字节幂等，发布后设只读，读取重算内容哈希。completed run 在 publish/read 两侧交叉
  核对 observed.seed/total_damage/truncated 与 run seed 及 final_save.state；failed run
  只接受结构化 error + 空 final_save。
- `read_variant()` 核对 metadata_hash、variant_id 推导绑定、文档相对路径和每份 YAML
  content hash，返回 variant root 与已验证 metadata，供后续证据校验消费。
- claim/report 以完整内容的 SHA-256 record ID 发布且不覆盖；公开 `publish_report()` 与
  `read_report()` 均校验 `spec.trial_id` 等于路径 trial，读取重算身份与内容哈希。
  `resolve_evidence()` 支持 claim→trial→run→event/final modifier 下钻；event/modifier
  链接必须带 run_id，final 集合外的 modifier 返回 `unresolved` 和原因，不虚构历史代际。
- result 读取还会从 spec 重建预期 seed/cohort/run 顺序并读取全部 run，追加或删除成员、
  改变 seed、遗漏 failed run 都不能静默通过。
- started/finished 等墙钟信息只写独立 `metadata.json`，可原子更新，不参与 ID、确定性
  内容哈希或 replay 字节比较。
- modifier 下钻只保留 final modifier 全量详情；不记录或虚构事件时刻的 modifier
  生命周期代际，已消失 modifier 的历史详情留待后续证据模型。

只读权限和 SHA-256 是**完整性与防误改护栏**，不是对同用户恶意进程的强安全沙箱。
硬隔离属于后续独立进程/OS 用户/容器工作。Replay 仍要求指纹对应的 canonical 模板根
可用，完整离线模板闭包导出、真实游戏校准均不在当前保证范围内。
