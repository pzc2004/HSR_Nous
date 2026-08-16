---
name: mechanics-scan
description: 机制扫描——用 LLM 给角色技能标"原语+红绿灯"，对照 sim_schema 检验机制表达力。开新一轮扫描、补扫新角色、对比两轮结果时使用。
---

# mechanics-scan

给角色技能标注"原语 + 红绿灯（green/yellow/red）"，检验 sim_schema 能否表达全部角色机制。
方法论细节（术语/原语粒度/归一化规则）见同目录 `METHODOLOGY.md`。

## 何时使用

- 开一轮新扫描（全量或增量）
- 游戏版本更新后补扫新角色
- schema 改动后对比两轮扫描结果（红翻绿要有 schema 依据，绿翻红必须解释）

## 一轮扫描的流程

1. **定范围**：`roster.yaml` 是花名册（勿手写 id——以
   `data/starrailres/index_new/cn/characters.json` 为准）。
   `python3 .agents/skills/mechanics-scan/run_round.py todo [raw_dir]`
   列出未扫角色，输出可直接当 AgentSwarm 的 items。
2. **派标注 agent**：每角色一个 subagent，按 `ANNOTATE_PROMPT.md` 标注，
   产出 `<id>.json` 放进本轮 raw 目录（`reports/mechanics_scan/roundN/raw/`，本地目录）。
   模板有版本号，改模板要记版本。
3. **校验**：`run_round.py check <raw_dir>`——JSON 合法、id 与文件名一致、字段齐全、
   status 合法、skill_id 对得上游戏数据（技能/星魂/行迹三表全集）。error 必须清零。
4. **对账**：`run_round.py status <raw_dir>` 看状态分布与缺漏。
5. **对比上轮**：`run_round.py diff <上轮raw> <本轮raw>`——状态迁移矩阵 + 逐条变化清单。
6. **汇总**：跨轮对比直接用第 5 步的 diff（默认归一化，改名不会误报）。
   矩阵生成器 `merge_to_matrix.py` 仅吃早期 dict 格式，已随 round1 产物归档；
   现行列表格式轮次暂无矩阵生成器，需要时再泛化。

## raw 文件格式

每角色一个 `<id>.json`，标注记录列表：

```json
[
  {
    "character_id": "1308",
    "skill_id": "130802",
    "primitive": "gain_resource",
    "status": "green",
    "schema_evidence": "16_custom_resources.md §16.5",
    "rationale": "残梦点数走自定义资源容器"
  }
]
```

- `status` ∈ `green`（schema 直接支持）/ `yellow`（近似可绕）/ `red`（无原语）
- `primitive` 用机制粒度命名（如 `trigger_existing_dot`），不照抄 effect_type
- 新旧技能组并存的角色以最新版为准

## run_round.py 子命令速查

| 命令 | 作用 |
|------|------|
| `check [raw_dir]` | 校验标注文件，默认自动探测最近一次轮次的 raw 目录 |
| `status [raw_dir]` | 花名册对账 + 状态分布 + roster 与游戏数据一致性 |
| `todo [raw_dir]` | 列未扫角色（swarm items 格式） |
| `diff <dirA> <dirB>` | 两轮状态迁移矩阵 + 变化清单 |

## 注意

- `reports/` 是本地产物目录（gitignored，可再生）；本 skill 的代码与模板入库
- 全量扫描约百个 subagent，token 消耗量级 ~12M，开跑前知会 owner
