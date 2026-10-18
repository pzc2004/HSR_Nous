# research_core

研究执行、原始证据、可信统计与 JSON 报告包。当前不接 DSH、MCP、前端或 Memory。

## 代码入口

- `variants.py`：loader 前校验、canonical 加载、内存 patch 和 variant 内容身份。
- `fingerprint.py`：复用模拟器指纹并绑定 implementation/config/variant/protocol/artifact schema。
- `artifacts.py`：canonical、不可覆盖的 spec/variant/run/result/claim/report 存储与证据下钻。
- `runner.py`：两臂编译、逐 seed 新 engine、原始 run 与 ComparisonSet。
- `kernel.py`：无 I/O 的 Fraction 统计、paired comparison 和纯 claim 推导。
- `claims.py`：从 spec/result/run/variant 独立重算 claim，处理 rejected/inconclusive/stale。
- `report.py`：再验证后的 JSON 报告与固定结论句。

## 规范与调用顺序

详细规则和公开 Python API 示例统一在 research_schema 文档中维护：

- [00_overview.md](../research_schema/docs/00_overview.md)：三类模块职责与完整数据流。
- [03_execution_artifacts.md](../research_schema/docs/03_execution_artifacts.md)：variant、指纹、runner、目录布局及 store 边界。
- [04_kernel_claims.md](../research_schema/docs/04_kernel_claims.md)：统计、CI、独立重算和 claim 身份。
- [05_report_evidence.md](../research_schema/docs/05_report_evidence.md)：报告字段、证据下钻和停云 walkthrough。

模块 import 边界只以根目录 `AGENTS.md` 与 `tests/test_doc_lint.py` 的边界闸为准。
