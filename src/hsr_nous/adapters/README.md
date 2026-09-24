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

## 呈现层旁车（`data/sim_templates/descriptions/`）

模板 DSL 只收机制（编译器词表零改动）；**显示文本走旁车**——官方中文技能描述
（desc 原文 + params 档位）与能量槽显示名，per-角色 JSON（`{char_id}.json`）：

```json
{"actor_id": "1408", "energy_name": "火种",
 "actions": {"140801": {"name": "…", "desc": "…#1[i]…", "params": [[0.5], …, [1.4]], "type_text": "普攻"}},
 "traces": {"1408103": {"name": "照见英雄本色", "desc": "…#1[i]…", "params": [[0.5, 2]]}},
 "ranks": {"140802": {"rank": 2, "name": "天与地，世间的泡沫", "desc": "…", "params": []}}}
```

- **生成方**：`template_generator.generate/write_description_sidecar`（actions 全收该角色
  character_skills 条目——普攻/战技/终结技/天赋/秘技，不按骨架裁剪，附官方 type_text；
  traces 收大行迹节点（name+desc 俱全者，属性小行迹/技能等级节点不收），键按技能/节点 id；
  ranks 全收 character_ranks 星魂条目，键按 rank id；`write_all_description_sidecars` 全量）
- **能量名取数**：角色 DSL 模板顶层 `energy_name` 字段（随实体走的唯一事实源——
  只收官方中文技能文本可查证的槽位名，如 1408→火种（天赋「此身为炬」含【火种】）；
  无该字段 = 普通能量，前端回落"能量"。历史：`data/energy_display_names.json` 全局表
  与 `sim/battles._SPECIAL_CHARGE_BY_ID` 硬表均已退役（2026-09-05 owner 裁定，防多源漂移）
- **消费方**：`sim/battles.description_doc` → web 调试台（技能悬浮卡 desc 服务端格式化
  `#N[i]` 满级档代入、能量条标签、状态 tab 来源就地展开），前端保持哑
- **回落规则**：旁车缺失/坏文件 → desc None（前端"无描述"）、energy_name null（前端"能量"）

## 机制标注流水线（ops/annotator DAG）

生成器产**机械层**（面板/倍率，回读零差异）之后的**语义层**生产者，现役 = ops/annotator
打标 DAG：`scripts/annotator.sh batch`——单实体链 data_pull→crosscheck→社区层→evidence→
draft（LLM 只产 hooks 块，数值区机械合并自生成器草稿，杜绝面板幻觉）→
compile/smoke/golden_diff 三闸内环（打回 revise，预算耗尽进 human_queue）→
oracle_report 对拍报告闸（vs hsr-optimizer，异常挂 notes 不打回）→finalize。
runs_root 断点续跑、--workers 外层并行、staging 候选包合并走人工闸。
**权威描述见根 `AGENTS.md`「打标 DAG 批量调度」条目**（本文件不重复细节）。

> 历史：初代单文件流水线 `adapters/mechanism_annotator.py`（LLM 标注 + 四级验证链）
> 已退役（2026-09，从未入库）——DAG 全取代。当时「adapters 禁 import sim、编译/冒烟
> 走 sim 域子进程 + 镜像词表双份维护」的边界约束随 DAG 落 ops/ 域自然消解
>（ops/ 允许 import sim；compile/smoke 闸走 `scripts/annotator_check.py` 固定件）。

## 旧路径：对象适配器（`character_adapter.py` 等）

pipeline 查询的结构化 dict → `sim_schema` 对象（角色名 → `Actor`）。
现主要服务 `account/`（账号数据）与 `screen/`（截图解析）侧；模板生成器不接这条路径。

> **`encounter_adapter.py` 是旧 demo 通道**（`_ENEMY_PRESETS`/`_RELIC_BONUS` 为启发式编造值，
> 非游戏数据）——正规通道 = 模板生成器产出的敌人/遗器模板，该通道待退役（A5/A6 审计标注）。

| 文件 | 职责 |
|------|------|
| `character_adapter.py` | 角色装配：角色名 → 官方面板 `Actor`；`make_dummy_enemy` 假人 |
| `skill_adapter.py` | 技能转换：raw 技能 → `Action` |
| `encounter_adapter.py` | 关卡组装：队伍名 + 敌人 → `Encounter`（**旧 demo 通道，待退役**） |
| `account_adapter.py` | HoYoLAB 账号数据 → `Actor` |

## Import 规则

允许 `pipeline` / `sim_schema` / `account` / `llm`；**禁止 `sim`**
（只输出 sim_schema，不调用仿真）。权威定义见根 `AGENTS.md` 模块边界表。

## 修改记录

- 呈现层旁车（`descriptions/`）：官方中文 desc/params + 能量槽显示名（DSL `energy_name`
  随实体走）落 per-角色 JSON，web 调试台旁路消费——显示文本不进 DSL 词表
- 机制标注流水线落地（`mechanism_annotator.py` + CLI）：LLM 语义层标注 + 四级验证链 +
  自愈重试 + human_queue；编译/冒烟验证经 sim 域 `template_check` 子进程（方案 B，
  adapters 零 sim import，sim 侧词表内嵌镜像双份维护）——**已退役（2026-09，单文件
  从未入库），ops/annotator DAG 全取代**
- 原则 A 修复：模板根唯一事实源收敛 `sim_schema/templates.py`（verifier 接 `roots` 注入、
  生成器 `out_dir` 缺省同源派生）；敌人数据读取下沉 pipeline 查询函数（`data_dir` 注入启用）；
  账号兜底编造面板改返回 None；`encounter_adapter` 旧 demo 通道标注待退役
- 模板生成器三器落地（角色/光锥/遗器），properties 结构化直映射 + 全量冒烟测试
- pct 族白值百分比语义配合引擎落地（`atk_pct` 等，flat 不吃百分比）
- 初始创建：对象适配器占位实现
