# research_core

第二步确定性研究执行与原始证据层。当前只包含 variant、指纹、artifact store 和
`TrialRunner`；可信统计内核、claim 校验与报告尚未实现。

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

## Artifact 边界

- spec/run/result 使用 canonical JSON 和全 SHA-256 ID；临时文件与 `os.replace` 原子发布，
  同字节幂等，发布后设只读，读取重算内容哈希。
- `read_variant()` 核对 metadata_hash、variant_id 推导绑定、文档相对路径和每份 YAML
  content hash，返回 variant root 与已验证 metadata，供后续证据校验消费。
- result 读取还会从 spec 重建预期 seed/cohort/run 顺序并读取全部 run，追加或删除成员、
  改变 seed、遗漏 failed run 都不能静默通过。
- started/finished 等墙钟信息只写独立 `metadata.json`，可原子更新，不参与 ID、确定性
  内容哈希或 replay 字节比较。
- modifier 下钻只保留 final modifier 全量详情；不记录或虚构事件时刻的 modifier
  生命周期代际，已消失 modifier 的历史详情留待后续证据模型。

只读权限和 SHA-256 是**完整性与防误改护栏**，不是对同用户恶意进程的强安全沙箱。
硬隔离属于后续独立进程/OS 用户/容器工作。Replay 仍要求指纹对应的 canonical 模板根
可用，完整离线模板闭包导出、真实游戏校准均不在当前保证范围内。
