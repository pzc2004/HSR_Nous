## 8. 与 Adapter 的交互边界

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移是独立 PR（见 `designs/0001-mechanics-scan-redesign.md` §3.11）。文档是前瞻性定义，代码会后续对齐。

`adapters/` 负责把 `raw_schema`（StarRailRes / Fandom 数据）转换成 per-entity DSL 模板（`data/sim_templates/**/*.yaml`）。

### 8.1 Preprocessing 入口

```bash
python -m hsr_nous.adapters.generate_templates
```

### 8.2 执行流程

```
adapters/generate_templates.py
   ↓
遍历所有角色 / 光锥 / 遗器 / 敌人 / 关卡 ID
   ↓
对每个实体：
  1. pipeline.load_xxx(id) → raw dict
  2. raw_schema.XxxType(dict) → 类型化对象
  3. adapter.adapt_xxx() → sim_schema DSL 对象（含 lookup_tables + variable_bindings + effects）
  4. yaml.safe_dump() → 落盘到 data/sim_templates/{characters,light_cones,relics,enemies,stages}/{id}.yaml
```

### 8.3 模块边界更新

| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `pipeline/` | 无 | `raw_schema`, `sim_schema`, `sim`, `agents`, `api` |
| `raw_schema/` | 无 | `sim_schema`, `sim`, `agents`, `api` |
| `adapters/` | `pipeline`, `raw_schema`, `sim_schema` | `sim` |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents`, `api` |
| `agents/` | `adapters`, `sim` | `pipeline`, `raw_schema` |
| `api/` | `agents`, `adapters`, `sim` | `pipeline`, `raw_schema` |

只改一行：`adapters/` 新增 `pipeline`。其他保持不变。

### 8.4 角色数据映射

| raw_schema 数据 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| `Character` + `LightCone` + `Relics` | `Actor.base_stats` | 计算最终白值 + 绿值 |
| `Character.skills[]` | `Actor.actions[]` | 映射倍率、目标类型、效果 |
| `Character.traces[]` | `Actor.traces[]` | 提取被动效果 |
| `Character.eidolons[]` | `Actor.eidolons[]` / `variable_bindings` | 生成星魂 patch |
| `LightCone.effects` | 光锥模板 `effects` | 转换光锥特效 |
| `RelicSet.bonus` | 遗器模板 `effects` | 按件数组装套装效果 |

### 8.5 光锥资源映射

光锥模板需要把 `light_cone_ranks.json` 中的多值行拆成独立查表数组：

```yaml
# raw_schema 摘录
"23042":
  skill: "包容"
  desc: "..."
  params:
    [0.18, 0.010, 0, 0.180, 2, 2.500]   # S1
    [0.21, 0.0125, 0, 0.225, 2, 3.125]  # S2
    ...

# adapter 生成
lookup_tables:
  speed_pct:     [0.180, 0.225, 0.270, 0.315, 0.360]
  consume_pct:   [0.010, 0.0125, 0.015, 0.0175, 0.020]
  multiplier:    [2.500, 3.125, 3.750, 4.375, 5.000]

variable_bindings:
  - self.speed_pct   = lookup_table("speed_pct",   index=$build.light_cone.superimposition - 1)
  - self.consume_pct = lookup_table("consume_pct", index=$build.light_cone.superimposition - 1)
  - self.multiplier  = lookup_table("multiplier",  index=$build.light_cone.superimposition - 1)
```

### 8.6 敌人数据映射

敌人和角色共用 Actor 结构，字段映射如下：

| raw_schema 数据 | sim_schema 对应 | adapter 工作 |
|----------------|----------------|------------|
| `Enemy.id` | `Actor.actor_id` | 直接映射 |
| `Enemy.name` | `Actor.name` | 直接映射 |
| `Enemy.elemental_weaknesses` | `Actor.weakness` | 转小写 |
| `Enemy.elemental_resistance` | `Actor.resistance` | 直接映射 |
| `Enemy.skill_list[]` | `Actor.actions[]` | 映射技能 |
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
