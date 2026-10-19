# research_core

研究执行、原始证据、可信统计与 JSON 报告包。DSH/MCP 传输由 agents/research_permissions 承接，本包不直接依赖外部 harness；前端和 Memory 尚未接入。当前同时执行 hypothetical mechanism YAML variant 和 canonical configuration build.json variant，artifact/report schema 为 v2，报告 world/flags 随类型动态生成。

## 代码入口

- `variants.py`：mechanism 的 loader 前校验/canonical 加载/内存 patch，以及 configuration 的 effective_build、parent/variant build hash 与两类内容身份。
- `fingerprint.py`：复用模拟器指纹并绑定 implementation/config/variant/protocol/artifact schema。
- `artifacts.py`：canonical、不可覆盖的 spec/variant/run/result/claim/report 存储与证据下钻。
- `runner.py`：两臂编译、逐 seed 新 engine、原始 run 与 ComparisonSet。
- `kernel.py`：无 I/O 的 Fraction 统计、paired comparison 和纯 claim 推导。
- `claims.py`：从 spec/result/run/variant 独立重算 claim，处理 rejected/inconclusive/stale。
- `report.py`：再验证后的 JSON 报告、动态 flags、固定结论句和仅用于解释的 actor_damage 拆解。
- `execution.py`：单进程 ExecutionManager，覆盖首次执行、取消、resume、cache_hit、replay_check 及 history/revision 持久化。

## 规范与调用顺序

详细规则和公开 Python API 示例统一在 research_schema 文档中维护：

- [00_overview.md](../research_schema/docs/00_overview.md)：三类模块职责与完整数据流。
- [03_execution_artifacts.md](../research_schema/docs/03_execution_artifacts.md)：variant、指纹、runner、目录布局及 store 边界。
- [04_kernel_claims.md](../research_schema/docs/04_kernel_claims.md)：统计、CI、独立重算和 claim 身份。
- [05_report_evidence.md](../research_schema/docs/05_report_evidence.md)：报告字段、证据下钻和停云 walkthrough。
- [07_permissions.md](../research_schema/docs/07_permissions.md)：权限角色、资源矩阵、反伪造契约及当前实现与目标态边界。
- [08_agent_bridge.md](../research_schema/docs/08_agent_bridge.md)：外部 DSH/MCP 传输与宿主复核边界。

模块 import 边界只以根目录 `AGENTS.md` 与 `tests/test_doc_lint.py` 的边界闸为准。
