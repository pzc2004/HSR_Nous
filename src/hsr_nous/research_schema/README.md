# Research Schema 确定性研究契约

本目录是研究后端的规范与纯数据契约入口。当前实现使用 frozen dataclass、递归只读 mapping、tuple 和严格 canonical JSON；不是 Pydantic 模型，也不是早期 Agent 设计稿。

## 文档结构

| 文件 | 内容 |
|------|------|
| [00_overview.md](docs/00_overview.md) | 目标/非目标、三类模块职责、完整数据流、可信边界与停云例子 |
| [01_contracts.md](docs/01_contracts.md) | 全部数据模型字段、不变量、递归冻结、round-trip 与 canonical JSON |
| [02_protocol.md](docs/02_protocol.md) | `paired-v1` 固定 seed/cohort/预算/bootstrap、patch 校验和状态语义 |
| [03_execution_artifacts.md](docs/03_execution_artifacts.md) | variant、指纹、research_root、runner、artifact 目录与安全边界 |
| [04_kernel_claims.md](docs/04_kernel_claims.md) | Fraction 统计、精确中间 paired diff、CI、claim 重算与 stale |
| [05_report_evidence.md](docs/05_report_evidence.md) | JSON 报告、结论句、证据下钻、公开 API 与停云 walkthrough |

## 数据流

```text
ResearchContract
    ↓
research_protocol 校验并解析 paired-v1
    ↓
research_core variant / fingerprint / TrialRunner
    ↓
只读 spec + variant + run + result artifacts
    ↓
ClaimValidator 独立重算
    ↓
ReportComposer 再验证并发布 JSON
    ↓
resolve_evidence 下钻到 run / event / final modifier
```

## 模块边界

> 模块允许与禁止 import 的唯一事实来源是根目录 `AGENTS.md` 的模块边界表及 `tests/test_doc_lint.py` 边界闸，本入口不重复维护。

- 数据模型与 canonical 规则见 [01_contracts.md](docs/01_contracts.md)。
- 协议和状态语义见 [02_protocol.md](docs/02_protocol.md)。
- 执行、统计、报告和安全限制分别见后续三章。
