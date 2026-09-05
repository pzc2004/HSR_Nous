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

## 机制标注流水线（`mechanism_annotator.py`）

生成器产**机械层**（面板/倍率，回读零差异）之后的**语义层**生产者：LLM 把角色机制
原文（query-game-data）翻译成 hooks/modifier DSL 片段，合并进生成器模板（只补语义层，
不动机械字段），过四级验证链（① lint 词表/事件契约/表达式白名单 → ② 编译 →
③ template_verifier 回读 → ④ 假人队行为冒烟），失败带具体错误自愈重试，
终审失败进 human_queue。

**任务流（tribios 租户）**：LLM 调用走统一接入层 `hsr_nous.llm`（多 key 管理 +
每 key 并发 + 流式任务调度）。**每角色 = 一个任务**（组上下文 → chat → 四级验证）提交进
Scheduler，按 key 额度并发跑满、完成一个立刻补一个（不再分批大调用）；重试由 scheduler
限次重入队，dead → human_queue。CLI 实时打印 `scheduler.progress()`。

**边界（owner 裁决方案 B）**：adapters 严禁 import `sim`，无例外——验证链②④的
编译/引擎能力经 sim 域 CLI 子进程消费：`python -m hsr_nous.sim.template_check`
（单行 JSON 判级 compile_ok/smoke_ok，错误原文直接进自愈反馈）；①lint 用的 sim/ 侧
词表（事件契约、模板/hook/effect/modifier/action 键）以**内嵌镜像常量**双份维护
（template_verifier 映射表先例），一致由 tests 的镜像闸测试保证。

```bash
# 单角色 dry-run（只打印四级成绩单不写盘）+ JSON 报告
uv run python -m hsr_nous.adapters.mechanism_annotator --ids 1202 --dry-run --report /tmp/r.json
# 按模板目录顺序取前 N 个（每角色一个任务，并发按 key 额度），默认写盘
uv run python -m hsr_nous.adapters.mechanism_annotator --batch 8 --report reports/annotator.json
```

- 配置：`HSR_NOUS_LLM_ANNOTATOR_{API_KEY,MODEL,API_BASE,EFFORT,CONCURRENCY}`
  （API_KEY 支持逗号分隔多 key；缺省回落 `OPENAI_*`；CONCURRENCY=每 key 并发，默认 4），
  repo 根 `.env` 手写解析（不依赖 python-dotenv；解析本体在 `llm/config.py`）
- 手写锚 = `tests/fixtures/templates/characters/` 的人工全机制模板（锚集合从文件名 id
  派生——加锚 = 放新 fixture，代码不动）：默认**包含**（fixtures 永不被写，只有对拍收益），
  `--skip-anchors` 显式排除（`--include-anchors` 已废弃为兼容 no-op）
- 名称纪律：modifier 名只能是原始数据里的官方名，生造名 → 🔴 重试

## 旧路径：对象适配器（`character_adapter.py` 等）

`raw_schema` 对象 → `sim_schema` 对象（`Character`+`LightCone`+`Relics` → `Actor`）。
现主要服务 `account/`（账号数据）与 `screen/`（截图解析）侧；模板生成器不接这条路径。

> **`encounter_adapter.py` 是旧 demo 通道**（`_ENEMY_PRESETS`/`_RELIC_BONUS` 为启发式编造值，
> 非游戏数据）——正规通道 = 模板生成器产出的敌人/遗器模板，该通道待退役（A5/A6 审计标注）。

| 文件 | 职责 |
|------|------|
| `character_adapter.py` | 角色装配：raw 角色+光锥+遗器 → `Actor` |
| `skill_adapter.py` | 技能转换：raw 技能 → `Action` |
| `encounter_adapter.py` | 关卡转换：raw 敌人 → `Encounter`（**旧 demo 通道，待退役**） |
| `account_adapter.py` | HoYoLAB 账号数据 → raw_schema 兼容结构 |

## Import 规则

允许 `pipeline` / `raw_schema` / `sim_schema` / `account`；**禁止 `sim`**
（只输出 sim_schema，不调用仿真——标注流水线的编译/冒烟验证走 sim 域
`template_check` 子进程）。权威定义见根 `AGENTS.md` 模块边界表。

## 修改记录

- 呈现层旁车（`descriptions/`）：官方中文 desc/params + 能量槽显示名（DSL `energy_name`
  随实体走）落 per-角色 JSON，web 调试台旁路消费——显示文本不进 DSL 词表
- 机制标注流水线落地（`mechanism_annotator.py` + CLI）：LLM 语义层标注 + 四级验证链 +
  自愈重试 + human_queue；编译/冒烟验证经 sim 域 `template_check` 子进程（方案 B，
  adapters 零 sim import，sim 侧词表内嵌镜像双份维护）
- 原则 A 修复：模板根唯一事实源收敛 `sim_schema/templates.py`（verifier 接 `roots` 注入、
  生成器 `out_dir` 缺省同源派生）；敌人数据读取下沉 pipeline 查询函数（`data_dir` 注入启用）；
  账号兜底编造面板改返回 None；`encounter_adapter` 旧 demo 通道标注待退役
- 模板生成器三器落地（角色/光锥/遗器），properties 结构化直映射 + 全量冒烟测试
- pct 族白值百分比语义配合引擎落地（`atk_pct` 等，flat 不吃百分比）
- 初始创建：对象适配器占位实现
