# HSR_Nous：博识尊驱动战斗分析与配装优化

本项目面向《崩坏：星穹铁道》的配装与配队优化，采用 ReAct 风格的多 Agent 闭环，将目标转化为可验证、可复现的决策结果。

## 目标

- 用数据与仿真替代纯经验型配装决策
- 系统性比较遗器、光锥、配速与队伍构成
- 输出可解释结论与清晰的方案权衡

## 项目结构

```
src/hsr_nous/
├── pipeline/          # 数据管道：从 StarRailRes + Fandom wiki 加载游戏数据
│   ├── loader.py      # JSON 数据加载器 + Fandom 数据合并
│   ├── update.py      # 从 GitHub 更新数据
│   ├── extract_fandom_skills.py  # 从 Fandom wiki 提取技能机制数据 + 嘲讽值加成
│   ├── extract_fandom_lightcones.py  # 从 Fandom wiki 提取角色 → 专光映射
│   └── README.md      # pipeline 模块详细文档
│
├── raw_schema/        # 原始数据模型（对应 StarRailRes schema）
│   ├── character.py   # 角色
│   ├── light_cone.py  # 光锥
│   ├── relic.py       # 遗器
│   ├── enemy.py       # 敌人
│   └── loader.py      # 原始数据 -> Python 对象
│
├── sim_schema/        # 仿真器输入格式（sim 的唯一输入）
│   ├── README.md      # 文档索引
│   ├── docs/          # 分章节数据格式设计（00_overview ~ 20_elation）
│   ├── examples/      # 示例输入（build / stage）
│   ├── actor.py       # 参战单位（角色/敌人）
│   ├── action.py      # 技能/普攻/终结技
│   ├── encounter.py   # 关卡/波次配置
│   ├── modifiers.py   # 增益/减益/特效
│   └── policy.py      # 策略模型（Rule-based + 参数化）
│
├── adapters/          # 适配层：raw_schema -> sim_schema
│   ├── character_adapter.py
│   ├── skill_adapter.py
│   └── encounter_adapter.py
│
├── sim/               # 战斗模拟器（纯仿真核心，只依赖 sim_schema）
│   ├── engine.py      # 回合制战斗循环 + PolicyInterpreter
│   ├── timeline.py    # 行动序管理
│   └── resolver.py    # 伤害/治疗/效果结算
│
├── agents/            # ReAct 风格多 Agent
│   ├── planner.py     # 目标拆解与评估计划
│   ├── builder.py     # 配装与配队候选生成
│   ├── search.py      # 参数空间搜索
│   ├── evaluator.py   # 仿真运行与指标计算
│   └── explainer.py   # 对比结论与可解释分析
│
└── api/               # 编排层
    └── orchestrator.py  # 多 Agent 协作闭环

docs/                       # 战斗规则文档（模拟器"唯一事实来源"）
├── README.md               # 文档导航与使用说明
├── game_rules.md           # 战斗规则总览
└── mechanics/              # 详细机制文档（按章节编号）
    ├── 00_game_basics.md        # 游戏基础概念（命途/属性/光锥/遗器/养成）
    ├── 01_base_stats.md        # 基础属性、技能、记忆命途
    ├── 02_damage_formula.md    # 伤害公式（12 乘区、击破、超击破、DOT、欢愉）
    ├── 03_action_sequence.md   # 行动序（回合/轮次/波次、拉条/推条、冻结）
    ├── 04_break_system.md      # 击破机制（韧性、击破效果、超击破）
    ├── 05_energy_system.md     # 能量恢复
    ├── 06_skill_points.md      # 战技点 + 秘技点
    ├── 07_buff_system.md       # Buff/Debuff 系统、属性二次转化
    ├── 08_elation_system.md    # 欢愉命途
    ├── 09_follow_up_attacks.md # 追加攻击
    ├── 10_taunt_system.md      # 嘲讽系统
    ├── 11_special_mechanics.md # 特殊机制（专属效果、结界/境界/连携攻击等）
    └── 12_technique_system.md  # 秘技系统

tests/                 # 测试目录

data/                  # 数据目录（gitignored）
├── starrailres/       # StarRailRes 索引数据（en/ cn/ 等多语言）
├── enemies/           # 敌人数据（来源: theBowja/starrail-data）
└── fandom_skill_data.json  # Fandom wiki 技能机制数据（削韧/回能/SP消耗/嘲讽值加成）
```

## 模块边界（严格遵守）

| 模块 | 允许 import | 禁止 import |
|------|------------|------------|
| `pipeline/` | 无 | `raw_schema`, `sim_schema`, `sim`, `agents`, `api` |
| `raw_schema/` | 无 | `sim_schema`, `sim`, `agents`, `api` |
| `adapters/` | `raw_schema`, `sim_schema` | `sim`（只输出 sim_schema，不调用 sim） |
| `sim/` | `sim_schema` | `raw_schema`, `pipeline`, `adapters`, `agents` |
| `agents/` | `adapters`, `sim` | `pipeline`, `raw_schema`（通过 adapters 间接使用） |
| `api/` | `agents`, `adapters`, `sim` | `pipeline`, `raw_schema` |

数据管道与战斗模拟器完全解耦：

```
StarRailRes (JSON) ──[pipeline.loader]──→ raw_schema
                                              │
                                              ▼
                                         [adapters.generate_templates]
                                              │
                                              ▼
                                    data/sim_templates/**/*.yaml
                                              │
                                              ▼
                                    [sim.loader] ──→ [sim.resolver]
                                              │
                                              ▼
                                    Encounter（绑定后的纯数据）
                                              │
                                              ▼
                                    [sim.engine] ──→ 仿真结果
```

## 核心设计亮点

### 事件-响应模型

技能、行迹、星魂、光锥、遗器本质都是**事件监听器**。所有持续效果通过 `Modifier` 表达，触发时机包括 `on_battle_start`、`on_turn_start`、`on_before_hit`、`on_kill` 等。

详见 [`sim_schema/README.md`](src/hsr_nous/sim_schema/README.md)。

### 策略模型

战斗策略采用 **Rule-based + 参数化混合** 设计，用结构化数据模型定义：

```yaml
policy:
  name: "march_7th_default"
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"
      action: "ultimate"
      priority: 100
    - condition: "skill_points > 0"
      action: "skill"
      priority: 50
    - condition: "true"
      action: "basic"
      priority: 0
  parameters:
    ULT_THRESHOLD: 120
```

- 模拟器直接 interpret，100% deterministic
- 参数（如 `ULT_THRESHOLD`）可独立调优，适合贝叶斯优化
- LLM 容易生成结构化的规则而非自然语言

详见 [`sim_schema/README.md`](src/hsr_nous/sim_schema/README.md) 第 9 节。

## 模块命名与世界观

核心模块命名对应游戏内星神/概念，只给核心模块起游戏名，工具层（pipeline、adapters、docs）不命名。

| 模块 | 命名 | 英文 key | 官方描述 | 对应理由 |
|------|------|----------|---------|---------|
| 项目整体 | 博识尊 | `nous` | "万物皆有未解之谜，万物皆有其解答。原为解答宇宙而生的天体计算机，升格为星神。" | 项目旨在求解配队配装问题 |
| Simulator | 翁法罗斯 | `amphoreus` | 博识尊的天体神经元——权杖 δ-me13 中运行的模拟世界，通过无数次循环实验求解"生命的第一因" | 通过重复模拟求解最优配装/配队 |
| Agent | 阿基维利 | `akivili` | "命运罗盘有三个方向——未知、已知、不可知。阿基维利离开孤立的佩加纳，不断开拓宇宙的未知边缘。" | 不断探索未知方案，用模拟器实战验证 |
| Memory | 浮黎 | `fuli` | "没有比纯粹的记忆更包罗万象的存在：它不偏不倚地记录一切，无私地保存每一个基本事实与每一种璀璨形态。" | 存储和检索经验，跨越旅程保持记忆 |
| data/ | 智库 | `data_bank` | 列车上的百科全书系统 | 存储角色/光锥/遗器/敌人数据 |

## 开发工具

本项目使用 **Claude Code** 作为 AI 编程助手，接入以下模型：

- **GLM-5.2**
- **MiMo-V2.5-Pro**
- **Kimi For Coding**
- **MiniMax-M3**

## 安装

使用 `uv`：

```bash
uv venv
uv pip install -e ".[dev]"
```

## CLI 命令

```bash
# 更新游戏数据（从 StarRailRes GitHub 拉取）
hsr-data-update

# 更新简体中文数据
hsr-data-update --lang cn

# 下载敌人数据（来源: theBowja/starrail-data）
hsr-data-update --enemies

# 使用 SSH 下载（国内网络更快，需配置 GitHub SSH key）
hsr-data-update --ssh

# 指定数据目录
hsr-data-update --data-dir ./my_data
```

## 数据来源

| 数据 | 来源 | 说明 |
|------|------|------|
| 角色/光锥/遗器 | [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes) | 基础数据（属性、倍率等） |
| 敌人数据 | [theBowja/starrail-data](https://github.com/theBowja/starrail-data) | 敌人弱点/抗性/技能 |
| 技能机制数据 | [Honkai Star Rail Wiki](https://honkai-star-rail.fandom.com)（Fandom） | 削韧值、回能值、SP 消耗、嘲讽值加成等 |

## 运行测试

```bash
pytest tests/ -v
```

## 决策闭环（ReAct）

1. **解析**：Planner 拆解目标与约束
2. **生成**：Builder 提出候选配装与队伍
3. **搜索**：Search 在参数空间细调（副词条/配速/策略参数）
4. **仿真**：Evaluator 运行战斗模拟并聚合指标
5. **对比**：Explainer 基于指标排序生成可解释报告
6. **迭代**：在预算内收敛到最优解

## 关键指标

- DPS 与伤害分布
- 生存率 / 存活时间
- 能量循环与终结技覆盖率
- 行动序稳定性 / 配速可行性
- RNG 敏感性（方差、最差情况）

## MVP 范围

- 支持敌人数据（弱点、抗性、技能），可用于更真实的战斗模拟
- 单队伍（4 人）与单关卡
- 限定遗器套装与光锥列表
- 固定随机种子与确定性仿真
- 简化的搜索预算与启发式策略

## 下一步

- [x] 完善 `raw_schema` 模型（字段映射与验证）
- [x] `sim_schema` 文档与规则文档交叉校验（公式冲突已修复、缺失机制已补充）
- [x] 完成 `sim_schema` v0.5 DSL-first 文档迁移（per-entity 模板、自定义资源、形态、秘技、场地、战前策略）
- [ ] 实现 `adapters.generate_templates` preprocessing 流程（raw_schema → `data/sim_templates/**/*.yaml`）
- [ ] 实现 `sim.loader` 模板索引 + `sim.resolver` 变量绑定
- [ ] 实现 `sim.engine` 伤害公式 / buff 管理 / 行动序 / 资源系统
- [ ] Pydantic v2 迁移（`sim_schema` 数据类）
- [ ] 完善 `sim.engine` 战斗循环（行动序、伤害结算、buff 管理）
- [ ] 添加 Agent 接口与评估闭环
- [ ] 构建基础 CLI 用于实验

## 协议

[MIT License](LICENSE)
