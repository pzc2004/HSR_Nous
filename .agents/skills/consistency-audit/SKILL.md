---
name: consistency-audit
description: 一致性审计——规则文档(docs/mechanics)与 schema 文档(sim_schema/docs)的四层核对流程。成批改文档、接入新数据源、游戏版本更新或 owner 点名再审一轮时使用。
---

# consistency-audit

规则文档与 schema 文档的四层一致性核对流程。审计对象是两套文档：
规则文档 `docs/mechanics/`（游戏机制事实）与 schema 文档 `src/hsr_nous/sim_schema/docs/`（模拟器输入格式）。

## 何时触发

- 两套文档发生成批改动后
- 新数据源接入（新 wiki 页、新社区攻略、游戏版本更新）
- owner 点名"再审一轮"

小改不用全量审计，跑 `tests/test_doc_lint.py` 即可（详见 `tests/README.md`）。

## 四层模型

| 层 | 内容 | 两侧 |
|---|---|---|
| L1 | 规则文档 vs 外部来源 | A=docs/mechanics；B=fandom/本地数据/optimizer/社区攻略 |
| L2 | 规则文档内部矛盾 | docs/mechanics 各章互查 |
| L3 | 规则 vs schema | docs/mechanics vs sim_schema/docs |
| L4 | schema 文档内部 | sim_schema/docs 各章互查 |

L1 裁决的来源优先级：**游戏数据（StarRailRes/fandom_meta）> fandom wiki > optimizer 实现 > 社区攻略**。owner 实测 > 一切。

## 数据通道 cheat sheet

- 角色技能/星魂：`data/starrailres/index_new/cn/character_skills.json`、`character_ranks.json`（按 id，如星期日 E6 = `131306`）
- 角色清单：`characters.json`（**生成清单一律从这里，别手写 id**）
- fandom 快照：`data/fandom_meta/`；在线查 fandom 可用 breezewiki 镜像绕反爬
- 光锥：`data/signature_light_cones.json`
- optimizer 参考实现：`external/hsr-optimizer/`（damageCalculator.ts 是公式侧；本地研究克隆，无则跳过该来源）
- gcsim 参考：`external/gcsim/`（本地研究克隆，无则跳过）
- 以上 data/external 均为本地数据目录（gitignored）

## subagent 分工模板（五路并行）

1. **L1a**：规则文档 vs fandom+本地数据+optimizer（公式逐因子对）
2. **L1b**：规则文档 vs 社区攻略（表格逐行对）
3. **L2**：规则文档内部（跨章引用、数值复算、修改记录抽查）
4. **L3+L4**：schema 两侧 + 规则↔schema 漂移
5. **专项**（按需）：某角色族/某机制族定点深挖

每个 subagent 产出统一格式：发现项 = `A 侧引用（文件:行）vs B 侧引用（文件:行）+ 差异描述 + 证据强度`。

## 工作表协议

1. 工作表写进 `reports/consistency_audit/AUDIT_REVIEW_<日期>_R<N>.md`（本地产物目录），每条给「我的倾向」+ 留「处置：」行
2. owner 逐条填处置；**留空 = 不动**
3. agent 按处置执行，执行完同文件回报；owner 确认后归档进 `reports/consistency_audit/archive/`（开新轮前可先翻归档取先例）
4. 一轮结束的标准：零待裁决项，执行层修复全落地

## 禁区

- git commit 必须 owner 逐次确认
- `agent/`（根目录）与 `src/hsr_nous/agents/` 是别人的代码，不碰
- 被追踪文档禁止引用本地文件（工作表名、决策卡号、BACKLOG 都不行）
