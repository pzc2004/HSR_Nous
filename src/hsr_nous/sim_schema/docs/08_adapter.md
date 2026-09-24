## 8. 与 Adapter 的交互边界

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

`adapters/` 负责把 pipeline 加载的原始数据（StarRailRes / Fandom）转换成 per-entity DSL 模板（`data/sim_templates/**/*.yaml`）。

### 8.1 Preprocessing 入口

生成器是库不是 CLI——`generate_*` / `write_*` 函数经 import 调用（用法与铁律见 `adapters/README.md` 主路径节）：

```python
from hsr_nous.adapters.template_generator import (
    generate_character_template, write_character_template,  # 等
)
```

### 8.2 执行流程

```
adapters/template_generator.py
   ↓
遍历角色 / 光锥 / 遗器 / 敌人 ID
   ↓
对每个实体：
  1. pipeline 查询函数 → 结构化数据
  2. generate_xxx_template() → 模板 dict（面板/倍率照抄原始数据；吃不动的写 notes 标人工，不脑补）
  3. write_xxx_template() → yaml.safe_dump 落盘 data/sim_templates/{characters,light_cones,relics,enemies}/{id}_{显示名}.yaml
   ↓
template_verifier.py 回读校验（不 import 生成器映射表，双份映射互相盯梢）
```

### 8.3 模块边界

模块边界表的唯一事实来源是根目录 `AGENTS.md`（受 `tests/test_doc_lint.py` 边界闸三向校验：表格 ↔ 闸门配置 ↔ 实际 import），本节不另维护副本。

### 8.4 角色数据映射

| 原始数据字段 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| 角色 + 光锥 + 遗器面板 | `Actor.base_stats` | 计算最终白值 + 绿值 |
| 角色 `max_sp` | `Actor.base_stats.max_energy` | 字段名映射 |
| 角色 `skills[]` | `Actor.actions[]` | 映射倍率、目标类型、效果 |
| 角色 `traces[]` | `Actor.traces[]` | 提取被动效果 |
| 角色 `eidolons[]` | `Actor.eidolons[]` / `variable_bindings` | 生成星魂 patch |
| 光锥 `effects` | 光锥模板 `effects` | 转换光锥特效 |
| 遗器套装 `bonus` | 遗器模板 `effects` | 按件数组装套装效果 |

> **装备机制通道（2026-09-06 已接线）**：光锥模板顶层新增 `hooks:` 键（与角色模板同一编译闸，
> owner=装备者；被动数值经 `variable_bindings` 叠影求值后由 hook 表达式 `$self.<param>` 消费）；
> 遗器套装模板的 `set_2pc`/`set_4pc` 件新增 `hooks:` 键（条件效果族——无条件纯数值仍走
> `stat_effects` 通道）。notes 态自由文本 → DSL 的 per-entity 转化归标注批次（BACKLOG B36）。

### 8.5 光锥资源映射

光锥模板需要把 `light_cone_ranks.json` 中的多值行拆成独立查表数组：

```text
# 原始数据摘录（light_cone_ranks.json）
"23042":
  skill: "包容"
  desc: "..."
  params:
    [0.18, 0.010, 0, 0.180, 2, 2.500]   # S1
    [0.21, 0.0125, 0, 0.225, 2, 3.125]  # S2
    ...
```

```yaml
# adapter 生成
lookup_tables:
  speed_pct:          [0.180, 0.225, 0.270, 0.315, 0.360]
  consume_pct:        [0.010, 0.0125, 0.015, 0.0175, 0.020]
  vulnerability_pct:  [0.180, 0.225, 0.270, 0.315, 0.360]
  vulnerability_duration: [2, 2, 2, 2, 2]
  multiplier:         [2.500, 3.125, 3.750, 4.375, 5.000]

variable_bindings:
  - self.speed_pct          = lookup_table("speed_pct",          index=$build.light_cone.superimposition - 1)
  - self.consume_pct        = lookup_table("consume_pct",        index=$build.light_cone.superimposition - 1)
  - self.vulnerability_pct      = lookup_table("vulnerability_pct",      index=$build.light_cone.superimposition - 1)
  - self.vulnerability_duration = lookup_table("vulnerability_duration", index=$build.light_cone.superimposition - 1)
  - self.multiplier         = lookup_table("multiplier",         index=$build.light_cone.superimposition - 1)
```

### 8.6 敌人数据映射

敌人和角色共用 Actor 结构，字段映射如下：

| 原始数据字段 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| 敌人 `id` | `Actor.actor_id` | 直接映射 |
| 敌人 `name` | `Actor.name` | 直接映射 |
| 敌人 `elemental_weaknesses` | `Actor.weakness` | 转小写 |
| 敌人 `elemental_resistance` | `Actor.resistance` | 直接映射 |
| 敌人 `skill_list[]` | `Actor.actions[]` | 映射技能 |
| 无 | `Actor.base_stats` | 从敌人模板读取 |
| 无 | `Actor.max_toughness` | 从敌人模板读取 |

**弱点/抗性映射注意**：
- 弱点属性默认 **0%** 抗性，非弱点属性默认 **20%** 抗性
- 弱点和抗性是**独立字段**
- adapter 需确保未在 `resistance` 中显式指定的属性有正确默认值

### 8.7 星魂/行迹 patch 生成

`character_ranks.json` 中星魂只有 desc 文字。当前计划：等 sim_schema 完备后，用 LLM 辅助把 desc 转换成结构化的 `variable_bindings` + `effects` patch。

在此之前，关键星魂可人工写规则映射。

### 8.8 质量保证

- preprocessing 跑完打印 missing / ambiguous 报告
- 模板入 git（便于 diff、回滚、人工 review）
- DSL 加载后通过 validator 静态检查

---
