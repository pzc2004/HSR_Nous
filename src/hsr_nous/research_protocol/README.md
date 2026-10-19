# research_protocol

固定实验协议与执行前校验包。本包只依赖 `research_schema`，不调用模拟器，不计算 CI，也不生成 claim 或报告。除 mechanism 外，当前还校验 canonical configuration 的完整 build_override；configuration 与 world 是两个独立维度。

## 代码入口

- `profiles.py`：`ResolvedProtocol`、`PAIRED_V1` 和只读协议注册表。
- `validation.py`：`resolve_protocol()`、`validate_contract()`、`validate_candidate_set()`、`validate_patch_reference()`、`validate_fingerprint()` 与 `ProtocolValidationError`。

## 规范

完整参数、seed/cohort 不变量、预算、两阶段 patch 校验和统计纪律统一见：

- [02_protocol.md](../research_schema/docs/02_protocol.md)：当前协议与状态语义。
- [01_contracts.md](../research_schema/docs/01_contracts.md)：本包消费的数据模型。
- [00_overview.md](../research_schema/docs/00_overview.md)：协议在完整研究数据流中的位置。
- [09_candidates.md](../research_schema/docs/09_candidates.md)：有界候选集的共享约束与确认规则。

文档中的 `paired-v1` 起止 seed、`min_valid_n`、`required_runs` 和 bootstrap 参数由 `tests/test_research_protocol.py` 与代码值做镜像校验。
