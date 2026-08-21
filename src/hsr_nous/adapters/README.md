# Adapters 适配层

外部数据 → `sim_schema`（仿真器输入）的**唯一桥梁**。两条路径并存：

## 主路径：模板生成器（`template_generator.py`）

`pipeline.loader` 的结构化数据 → per-entity DSL YAML 模板（`data/sim_templates/**`），
供 `sim.compile` 编译成引擎输入。

配套校验：`template_verifier.py`（回读校验器）——模板 ↔ 原始数据逐字段独立比对，
**不 import 生成器的映射表**（生成器写错时校验器不能跟着错，双份映射互相盯梢）。

```python
from hsr_nous.adapters.template_generator import (
    generate_character_template,     # 角色：面板 + 倍率 + 形态 + 默认削韧/回能
    generate_light_cone_template,    # 光锥：白值 + 叠影 lookup 表 + properties 语义列
    generate_relic_set_template,     # 遗器：件套 + properties stat_effects + desc 留存
    generate_enemy_template,         # 敌人：calc_enemy_stats 公式链面板 + 弱点 + 占位行动
    write_character_template, write_light_cone_template, write_relic_set_template,
)
from hsr_nous.adapters.template_verifier import (
    verify_character_template, verify_light_cone_template,
    verify_relic_set_template, verify_enemy_template,  # 返回不一致清单，空=通过
)
```

**生成器铁律**：

- **不静默错生成**——吃不动的一律写 `notes`/`scaling_notes` 标人工，绝不脑补
- **能结构化不正则**——原始数据 `properties`/`effect`/`params` 字段直映射优先；
  desc 正则只用于结构化字段覆盖不到的部分（如 blast 副倍率占位符反解）
- **忠于原始数据**——倍率/副倍率按等级数组照抄（决策卡 #18 写法二），不做固定比例压缩

## 旧路径：对象适配器（`character_adapter.py` 等）

`raw_schema` 对象 → `sim_schema` 对象（`Character`+`LightCone`+`Relics` → `Actor`）。
现主要服务 `account/`（账号数据）与 `screen/`（截图解析）侧；模板生成器不接这条路径。

| 文件 | 职责 |
|------|------|
| `character_adapter.py` | 角色装配：raw 角色+光锥+遗器 → `Actor` |
| `skill_adapter.py` | 技能转换：raw 技能 → `Action` |
| `encounter_adapter.py` | 关卡转换：raw 敌人 → `Encounter` |
| `account_adapter.py` | HoYoLAB 账号数据 → raw_schema 兼容结构 |

## Import 规则

允许 `pipeline` / `raw_schema` / `sim_schema` / `account`；**禁止 `sim`**
（只输出 sim_schema，不调用仿真）。权威定义见根 `AGENTS.md` 模块边界表。

## 修改记录

- 模板生成器三器落地（角色/光锥/遗器），properties 结构化直映射 + 全量冒烟测试
- pct 族白值百分比语义配合引擎落地（`atk_pct` 等，flat 不吃百分比）
- 初始创建：对象适配器占位实现
