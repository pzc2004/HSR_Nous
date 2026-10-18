# Tests 测试

项目测试目录，扁平布局——按版本线 + 横向族组织（见下「测试组织」）。

## 运行测试

### 最小测试（文档 lint 或纯单元测试）

只需安装项目与 dev 依赖，不需要数据、optimizer 或浏览器：

```bash
uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/test_doc_lint.py -v
```

### 全量回归

本地与 CI 共用同一个环境准备脚本。它会安装项目依赖、从 GitHub Release 恢复固定数据快照、生成模板、安装 pinned optimizer 和 Playwright：

```bash
bash scripts/setup_test_env.sh
.venv/bin/python -m pytest tests/ -q -rs
```

本地已有完整数据时默认复用；需要强制从 Release 刷新时运行 `TEST_ENV_REFRESH_DATA=1 bash scripts/setup_test_env.sh`。CI 每次都会从 Release 恢复快照。缺依赖导致的 skip 是环境诊断信息，应先检查环境而不是直接接受。

## 文档 lint（tests/test_doc_lint.py）

把 `sim_schema/docs` 全部章节当代码做机械全量检查——文档即代码，全量、机械、无语义判断。
闸按编号组织（编号见下表；部分闸拆多个测试函数，数量以现场 `pytest --collect-only` 为准）：

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
| 13 | rulebook 镜像闸 | `sim_schema/rulebook.yaml` ↔ 01_formula 公式/乘区逐字一致（双向）+ rulebook 表达式过白名单 + break_effects 逐元素字段级镜像 | 改公式/击破效果两边同步（rulebook 为可执行唯一来源，01_formula 为文档镜像） |
| 14 | 词表闸 | §22.4 函数表"已实现"集 == `sim_schema/expression.py` 白名单（EFFECT ∪ FORMULA），"未实现"集与之不交 | 改白名单只改 expression.py；§22.4 新登记函数必须标状态 |
| 15 | terminology 乘区键闸 | terminology.yaml"伤害乘区"键 ⊆ rulebook zones ∪ 公式标识符 | 乘区键改名先改 rulebook（唯一来源），terminology 跟随 |
| 16 | 事件契约闸 | §23.4 表"状态"列 ↔ `sim/bus.py` DEFAULT_CONTRACT（已登记集 == 契约 − §4.8 生命周期表；未登记集与契约不交；契约每个键必须在 §23.4 已登记行或 §4.8 表登记） | 改契约只改 bus.py；§23.4 新事件行必须标状态；生命周期事件（on_turn_start 族）归 §4.8 表 |
| 17 | 遗器词条镜像闸 | `rulebook.yaml` relic_affixes 段逐值 == pipeline 词条数据重算（`calc_relic_main/sub_affix_values`）；键集与编译器 `_AFFIX_FIELD` 词表互锁 | 数值漂移按重算结果改 rulebook；词表增删三处（rulebook/_AFFIX_FIELD/闸 `_AFFIX_ID2PROP`）同步 |
| 18 | 公共基建单一来源闸 | 路径根（`repo_root`/`data_root`/`repo_data_dir`）与 `.env` 解析只许住在 `common/`：全库扫描禁止其它模块重新定义；另钉 `common/` 零项目依赖 | 重复实现删掉、改 import `hsr_nous.common`；`common/` 不许 import 项目模块 |
| 19 | 生产写保护闸 | tests/ 调生成器 `write_*_template` 必须显式 `out_dir=`（缺省写生产 `data/sim_templates/`） | 给调用补 `out_dir=` 指向测试隔离目录——写生产会覆盖标注层 |
| 20 | import 有效闸 | 全库 `hsr_nous.*` import 必须解析到磁盘真实模块（合法模块集现场推导，无人工清单） | 导入路径拼错/模块删搬后漏改 |

```bash
pytest tests/test_doc_lint.py -v
```

原则：能写成闸的规矩就不要只靠口头约定。新增"文档必须遵守"的硬规矩时，优先加闸。

## 测试组织

按版本线组织：`test_engine_v01`（直伤闭环）→ `test_engine_v02`（击破/敌动/波次）→ `test_compile`（编译层）→ `test_modifier_v04`（modifier 完整版）→ `test_template_gen` / `test_enemy_template`（模板生成+全量冒烟）→ `test_state_machine_v06`（形态机）→ `test_multitarget_v07` / `test_policy_v07` / `test_multihit_v07`（多目标/策略/多段）→ `test_montecarlo_v08` / `test_perf_v08`（方差/性能看守）→ `test_*_v09` 族（`test_hit_chain_e2e_v09` 命中链 / `test_hit_energy_v09` 受击回能 / `test_shield_v09` 护盾 / `test_survival_v09` 生存 / `test_compile_merge_v09` 编译合并）→ `test_taunt_v10`（嘲讽）→ `test_cycle_v11`（轮次）。实验层专项：`test_montecarlo_experiment`（终止 survival/wipe、结果分类器、指标族、CSV、版本指纹四件 e2e 钉）。

版本线之外的横向族：hook DSL 与模板 e2e（`test_hook_dsl` / `test_ruan_mei_template` / `test_tribbie_template` / `test_phainon_*` / `test_thanatoplum`——手工模板真身在 `data/library/`（机制库正典根，git 追踪），测试编译经 `template_roots=TEST_TEMPLATE_ROOTS` 注入（正典根优先于 data/sim_templates 生成根，见 `tests/template_materialize.py`））、`test_caveats_channel`（近似置信度通道三层钉：caveats 词表闸/编译聚合/结果附带+确定性无关钉）、`test_extract_caveats`（提取脚本 `_classify` 规则闸钉：空账/完成陈述不误提、真挂账不误杀）、`test_save_restore`（真·全状态存档与恢复两层钉：三编队 roll+expected 世界线全等（含 JSON 落盘往返/转波后存档/累积队列非空时刻）+ 完备性闸（存档字段策略表 ↔ dataclasses 反射、引擎/调度器/管线/hooks 字段「存档∪豁免」二分））、`test_doc_lint`（文档闸，见上）、`test_pipeline*` / `test_crosscheck_optimizer`（数据管道与对拍）。`scheduler_debug.py` 是调度器调试辅助（行动条预览/快照，纯测试消费的白箱视图，不是测试文件，pytest 不收集）。

研究后端横向族：`test_research_schema` / `test_research_protocol`（mechanism/configuration 契约组合、override 冻结与固定协议）、`test_research_core_artifacts` / `test_research_core_runner`（YAML/build.json variant、两臂 policy 指纹、只读 store 与真实 64 局证据）、`test_research_core_kernel`（Fraction 统计与固定 bootstrap golden）、`test_research_core_claims`（独立重算及 accepted/rejected/inconclusive/stale）、`test_research_core_e2e`（停云 mechanism、黄泉速度鞋/攻击鞋、白板四人队缇宝/赛飞儿 configuration 的 schema v2 报告、动态 flags、描述性 actor_damage、伪造拒绝与下钻）。共享纯 Python 构造件 `tests/_research_builders.py`，不新增 YAML fixture。文档一致性另有两道机械闸：`test_doc_lint` 的 research_schema/README ↔ docs 双向索引，以及 `test_research_protocol` 的 02_protocol.md ↔ PAIRED_V1 参数镜像。

## 修改记录

- 公共基座 `common/` 落地：路径根（`repo_root`/`data_root`/`repo_data_dir`）与 `.env` 解析统一收口——`pipeline/paths.py`、`sim_schema/templates.py` 的重复数据根解析、`llm`/`account` 的重复 `.env` 解析全部消除；`test_env_parity` 对拍闸退役，doc_lint 闸18 由「数据根镜像闸」改为「公共基建单一来源闸」（全库扫描盯防重复实现回潮 + 钉 `common/` 零项目依赖）
- 补登记闸 19（生产写保护闸，1a7ef51 引入；编号无闸 18——按测试文件实际编号）：tests/ 调 `write_*_template` 必须显式 `out_dir=`，缺省写生产 `data/sim_templates/`（标注层团灭事故见测试文件头注）
- 首行结构描述勘正：目录实为扁平布局（版本线 + 横向族，见「测试组织」），非与 `src/hsr_nous/` 对应
- 新增闸 17（遗器词条镜像闸）：`rulebook.yaml` relic_affixes ↔ pipeline 重算 ↔ 编译器 `_AFFIX_FIELD` 词表三向互锁
- 测试组织改为版本线索引（原"待补充测试"规划表过时删除——各模块均已有测试）
- 初始创建：目录结构占位
