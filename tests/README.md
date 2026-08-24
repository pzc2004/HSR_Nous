# Tests 测试

项目测试目录，结构与 `src/hsr_nous/` 对应。

## 运行测试

```bash
pytest tests/ -v
```

> **agents 区测试已知破损**：`test_account.py` / `test_agent_prompts.py` / `test_agent_tools.py` /
> `test_agents_mocked.py` / `test_llm_factory.py` / `test_deepseek_smoke.py` 属 agents/account 线
> （LLM 凭据与外部服务依赖，模块边界见 `AGENTS.md` 模块表），当前已知破损，修复走另一条线。
> sim/pipeline 域绿基线以带 ignore 的命令为准：
>
> ```bash
> .venv/bin/python -m pytest tests/ -q --ignore=tests/test_account.py --ignore=tests/test_agent_prompts.py --ignore=tests/test_agent_tools.py --ignore=tests/test_agents_mocked.py --ignore=tests/test_llm_factory.py --ignore=tests/test_deepseek_smoke.py
> ```

## 文档 lint（tests/test_doc_lint.py）

把 `sim_schema/docs` 全部章节当代码做机械全量检查——文档即代码，全量、机械、无语义判断。
共 14 闸（闸 9 拆两个测试函数，合计 15 个测试）：

| # | 闸 | 检查内容 | 失败时怎么办 |
|---|----|---------|-------------|
| 1 | 表达式闸 | 文档所有表达式字符串过 ast 白名单解析 | 表达式写错或白名单缺函数，改文档或 `sim_schema/expression.py` |
| 2 | effect_type 闸 | 用法命中声明清单（05 + 17/19/23 章） | 新 effect_type 要先在 05 章声明 |
| 3 | 触发器闸 | trigger/hook 事件名命中 §4.8 + §23.4 清单 | 新事件先改 §4.8/§23.4 |
| 4 | 公式闸 | 01_formula 顶层公式的标识符有 parameters 定义 | 缺定义补 parameters |
| 5 | 命名残留闸 | 已退役标识符 0 命中（豁免修改记录/废弃语境） | 退役清单在测试文件 `RESIDUE`，改名后把旧名加进去 |
| 6 | 镜像闸 | 同名公式跨文件逐字相等（归一化） | 登记在 `MIRRORS`；改公式必须两边同步 |
| 7 | 公式↔表格闸 | 伤害类型：公式乘区 = 02 生效表行 = §1.9 矩阵列 | 三处必须同增同减 |
| 8 | 引用闸 | 文档间 §X.Y 引用解析到真实章节 | 改章节号时全局搜引用 |
| 9 | 算术闸 | a) 遗器副词条三档对原始数据；b) EHR 断点表按公式重算 | 数值按公式重算后改表 |
| 10 | 索引闸 | README 索引清单 ↔ 磁盘文件双向一致 | 加/删章节文件后更新 `docs/README.md`、`sim_schema/README.md` |
| 11 | 边界闸 | AGENTS.md 模块边界表 ↔ 闸门配置 ↔ 实际 import 三向一致 | 越界 import 改代码；新增合法边改 AGENTS.md 表 + `BOUNDARY_ALLOWED` |
| 12 | 同步闸 | README `<!-- module-boundaries -->` 标记区 == AGENTS.md 边界表 | 改表只改 AGENTS.md，把该节表格同步进 README 标记区 |
| 13 | rulebook 镜像闸 | `sim_schema/rulebook.yaml` ↔ 01_formula 公式/乘区逐字一致（双向）+ rulebook 表达式过白名单 | 改公式两边同步（rulebook 为可执行唯一来源，01_formula 为文档镜像） |
| 14 | 词表闸 | §22.4 函数表"已实现"集 == `sim_schema/expression.py` 白名单（EFFECT ∪ FORMULA），"未实现"集与之不交 | 改白名单只改 expression.py；§22.4 新登记函数必须标状态 |

```bash
pytest tests/test_doc_lint.py -v
```

原则：能写成闸的规矩就不要只靠口头约定。新增"文档必须遵守"的硬规矩时，优先加闸。

## 测试组织

按版本线组织：`test_engine_v01`（直伤闭环）→ `test_engine_v02`（击破/敌动/波次）→ `test_compile`（编译层）→ `test_modifier_v04`（modifier 完整版）→ `test_template_gen` / `test_enemy_template`（模板生成+全量冒烟）→ `test_state_machine_v06`（形态机）→ `test_multitarget_v07` / `test_policy_v07` / `test_multihit_v07`（多目标/策略/多段）→ `test_montecarlo_v08` / `test_perf_v08`（方差/性能看守）→ `test_*_v09` 族（`test_hit_chain_e2e_v09` 命中链 / `test_hit_energy_v09` 受击回能 / `test_shield_v09` 护盾 / `test_survival_v09` 生存 / `test_compile_merge_v09` 编译合并）→ `test_taunt_v10`（嘲讽）→ `test_cycle_v11`（轮次）。

版本线之外的横向族：hook DSL 与模板 e2e（`test_hook_dsl` / `test_ruan_mei_template` / `test_tribbie_template` / `test_phainon_*` / `test_thanatoplum`——手工模板经 `tests/template_materialize.py` 从 `tests/fixtures/templates/` 物化到 `data/sim_templates/characters/`，物化前清同 ID 生成文件）、`test_doc_lint`（文档闸，见上）、`test_pipeline*` / `test_crosscheck_optimizer`（数据管道与对拍）、`test_screen` / `test_pilot`（屏幕识别/自动驾驶，opt-in）。`scheduler_debug.py` 是调度器调试辅助（行动条预览/快照，纯测试消费的白箱视图，不是测试文件，pytest 不收集）。

## 修改记录

- 测试组织改为版本线索引（原"待补充测试"规划表过时删除——各模块均已有测试）
- 初始创建：目录结构占位
