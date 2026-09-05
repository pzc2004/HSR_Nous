# Sim 战斗模拟器（翁法罗斯 / Amphoreus）

纯战斗仿真核心，只依赖 `sim_schema`，不认识 `raw_schema` 和 `pipeline`。
形状是"编译器 + 虚拟机"：`compile/` 把 DSL YAML 编译为不可变 `CompiledEncounter`，
运行时 VM（调度 / 事件总线 / 结算管线）从它完整重建每一局。

## 模块地图

| 文件 | 职责 |
|------|------|
| `engine.py` | `CombatEngine` 战斗主干：回合四段主循环 + 击破 + 敌人行动 + 波次切换 + 护盾/生存/光环/轮次（hooks/modifier/策略运行时已拆出，本类薄委托） |
| `scheduler.py` | `Scheduler`：距离制调度器——守恒剩余距离为主状态，红黑树排序键 = 派生预计时刻 |
| `avtree.py` | `AVTree`：数组化红黑树（CFS 同构有序平衡树，整树一根 int 数组，snapshot 免费） |
| `bus.py` | `EventBus`：事件总线——发射点 / waterfall-emit 分派 / modify_event |
| `hooks.py` | `HookRuntime`：模板 hooks 运行时（订阅 + 条件求值 + 效果执行） |
| `modifiers.py` | `ModifierBook`：modifier 生命周期（施加/tick 走字/驱散净化/物化）+ 护盾吸收 |
| `pipeline.py` | `SettlementPipeline`：结算管线（两层求值 → effect 原语 → 伤害公式），公式全部来自 `sim_schema/rulebook.yaml` 表达式，节点值树输出 |
| `state.py` | 战斗全状态 dataclass：可序列化快照（纯净不变量的载体） |
| `resources.py` | 能量资源三段式（ult_threshold / 终结技可用性判定） |
| `policy_api.py` | 策略接口：`legal_action_set` 生成 + 决策点注入 + `ScriptedPolicy` / `CompiledPolicyRuntime` |
| `montecarlo.py` | 多局统计聚合：roll 模式 N 局 → 伤害分布 |
| `debug.py` | `DebugController` 调试控制器：单步/断点/检视/快照 + 决策点接管（CLI/网页端共用本体；名册代号 oronyx，见下表） |
| `battles.py` | 战斗配置库：`data/battles/` 一局一个自包含 YAML（内嵌 build/stage 文本），web 大厅与 CLI 选择器共用；空目录自动物化三个内置演示配置 |
| `compile/` | 绑定编译层：build/stage YAML → 不可变 `CompiledEncounter`（符号解析 + AST 预编译 + 糖 desugar） |
| `web.py` | 呈现层服务端（hsr-sim-web）：会话/决策收发室 + 状态序列化 + 技能详情/面板聚合端点 |
| `web_static/` | 呈现层前端（单文件 GUI）：战斗调试台——交互纪律见下文「呈现层纪律」 |

## 呈现层纪律（web_static 前端）

前端的所有用户行为遵循三层结构，**新功能只允许往指定位置加**——这是"改了 A 漏了 B"
类事故（灰技预览改鼠标漏键盘、长按预览改行动态漏瞄准态、目标圈改瞄准漏终结技确认态）
的结构解，任何改动不得绕开：

1. **语义动作层唯一来源**：一个用户行为全项目只有一处定义（`actChoice` / `actUltRow` /
   `actGrey` / `confirmAiming` / `startAiming` 族等）。鼠标 click、键盘 tap、E2E 合成事件
   一律只做事件翻译后调语义函数，**翻译处禁止写业务逻辑**。新交互 = 语义层加一个函数 +
   路由表加一行。
2. **交互状态机 + 键位路由表**：`uiMode()` 从 `(S, aiming, ultAim, pending)` 唯一派生
   （`idle/action/aiming/phase2/ultAim/ultWindow`）；`routeKey` 按 `(mode, key)` 数据表
   分发。新交互态 = `uiMode` 派生加分支 + 路由表加条目，**禁止在 keydown 里新写嵌套分支**。
3. **视觉单点派生**：目标圈/高亮/瞄准计数从 `visualAim()` 单点取数（瞄准态直通 + 终结技
   确认态折同形状），渲染代码不各自读 `aiming`/`ultAim` 原始状态。
4. **行为对拍闸**：改行为必跑——`tests/test_web_ui_logic.py`（node 逻辑闸）+
   `tests/test_web_e2e.py`（Playwright）+ 行为脚本套件（长按/灰技/槽位/终结技目标段/
   敌方窗口+倒计时，见 `tests/README.md` 与 /tmp 历史脚本口径）；行为脚本落后语义时
   **更新脚本不松语义**。

## 命名名册（泰坦级）

星神级命名（博识尊/翁法罗斯/阿基维利/浮黎/智库）见根目录 `AGENTS.md`；
引擎**内部组件**用翁法罗斯世界内部的泰坦名，名册如下（有岗位才入座，入座不触发重构）——
按**翁法罗斯历十二月**排序（历法见 `docs/lore/amphoreus.md` §十三），第十三泰坦德谬歌居历法之外置末：

| 代号 | 泰坦 | 称号 | 权能 | 月份 | 席位 | 代码形态 | 备注（权能↔席位对位） |
|------|------|------|------|------|------|----------|------|
| `janus` | 雅努斯 | 万径之门 | 门径 | 一月·门关月 | 事件总线 | `bus.py`（文档别名） | 信使传谕=事件分派；隔绝与监禁=waterfall/emit 把关 |
| `talanton` | 塔兰顿 | 公正之秤 | 律法 | 二月·平衡月 | 模板校验器 | 待收拢（现散于 lint 与校验逻辑） | 公平天秤=裁决合法性 |
| `oronyx` | 欧洛尼斯 | 永夜之帷 | 岁月 | 三月·长夜月 | 调试控制器 | `debug.py`（`DebugController`） | 祷言回溯=快照回退；远瞻过去=检视；祭司解读梦呓=行动条谕示（`action_bar`） |
| `georios` | 吉奥里亚 | 磐岩之脊 | 大地 | 四月·耕耘月 | 战场构建器 | `compile/` | 构筑世界=编译战场（"大地曾参与构筑忆潮世界"） |
| `phagousa` | 法吉娜 | 满溢之杯 | 海洋 | 五月·欢喜月 | modifier/effect 体系 | `modifiers.py`（文档别名） | 蜜酿赐福=施加增益（游戏内"法吉娜的赐福"即 buff）；满溢之杯=叠层；洗刷污秽=驱散净化 |
| `aquila` | 艾格勒 | 晨昏之眼 | 天空 | 六月·长昼月 | 边界层：一切出入口（CLI/将来网页端） | `cli.py` | 天幕=世界边界 ↔ 出入口层 ⚠️ 消歧见下 |
| `kephale` | 刻法勒 | 全世之座 | 负世 | 七月·自由月 | 快照/状态承载体系 | 未建 | 负世=承载全状态（候补：**落盘快照/跨局恢复**——v1 内存回退已由深拷贝实现，本席为全状态审计+JSON 往返的完整形态） |
| `cerces` | 瑟希斯 | 裂分之枝 | 理性 | 八月·收获月 | 理性计算层：AST 求值 + 策略决策求值 | `sim_schema/expression.py`、`policy_api.py`（文档别名） | 裂分之枝=语法树+决策树；理性=白名单求值（B8）+条件评估/优先级选择（策略内容是经验不是理性，不归此席） |
| `mnestia` | 墨涅塔 | 黄金之茧 | 浪漫 | 九月·拾线月 | 呈现层：GUI 视觉外观 | 未建（hsr-sim-web） | 收拢幻影之丝织成美=数据织成可见呈现；黄金之茧=世界外面那层皮（aquila 管进出，mnestia 管看见） |
| `nikador` | 尼卡多利 | 天谴之矛 | 纷争 | 十月·纷争月 | 伤害结算管线 | `pipeline.py` 瀑布乘区 | 天谴之矛=每次攻击结算 ⚠️ 消歧见下 |
| `thanatos` | 塞纳托斯 | 灰黯之手 | 死亡 | 十一月·哀悼月 | 死亡处置链 | `engine._check_death`（文档别名，不拆件） | 残茧收殓=锁血→月茧→复活→真死 |
| `zagreus` | 扎格列斯 | 翻飞之币 | 诡计 | 十二月·机缘月 | 随机源 | `pipeline.rng`（文档别名，不包类） | 翻飞之币=掷骰：期望=按住硬币，roll=抛起 |
| `demiurge` | 德谬歌 | 翁法罗斯之心 | 创世 | 历法之外 | 模拟器↔记忆之桥 | 未建（agents 层，B30） | 世界↔记忆之桥（候补 ⚠️ 消歧见下） |

除名：来古士（反派，owner 决定 2026-08-26；EN: Lygus——LykoS 只是权杖日志的管理员 ID 非人名；
3.5 已进本当 boss=实体级数据，双重不可用）。
称号与权能以 `docs/lore/amphoreus.md` 泰坦总表为准；备注统一为"权能↔席位的功能对位"（缇宝检验法）。

命名规则：

- **三档**：设定级（星神/世界，永不进实体数据）随便用；泰坦级可用、boss 化打 ⚠️；
  实体级（角色/忆灵/形态，必进模板数据）禁用——`demiurge` 经数据核实为忆灵名，
  但模板实体一律用**中文官方名+数字 id**（见 `data/sim_templates/` 约定），
  英文 token 不在模板生成路径上，故降级为 ⚠️ 可控，与 `nikador` 同例。
- **碰撞不变量**：同一字符串不在同一语境（LLM 上下文/同一命名空间）指两个东西。
- **只活文档**：代码标识符一律朴素自描述（如 `debug.py`）；泰坦名只活在本名册、
  docstring 别名与显示层（GUI 标题/横幅），**不进任何代码标识符**——碰撞面压到零，
  新人零神话课门槛（owner 定，2026-08-26）。别名出现处必须与人话并存（如 `thanatos` 标注 `_check_death`），不做谜语。
- **消歧条款**：代码层英文名 ↔ 数据层中文名+id；若模板出现 romanized state id，
  用限定 token（如 `state_demiurge`）与模块名区分。当前 ⚠️ 席：`nikador`（boss「颁赐者，
  千军首，天谴之矛」）、`aquila`（boss「至高，至阳，天空的化身」，见 hakushin 关卡数据）、`demiurge`（忆灵）。

## 设计文档

- 机制规格（唯一事实来源）：`src/hsr_nous/sim_schema/docs/`（含公式镜像 `01_formula.md` ↔ 可执行来源 `rulebook.yaml`）
- 架构文档（入库）：`docs/engine_design.md`——编译器+VM 分层、三条全局不变量（纯净 / 白名单求值 / waterfall-emit 契约）、当前未实现清单
- 设计草稿（本地不入库）：`designs/ENGINE_DESIGN.md`

## 使用方式

```python
from hsr_nous.sim import CombatEngine, MODE_EXPECTED
from hsr_nous.sim.compile import compile_encounter_yaml

compiled = compile_encounter_yaml(build_yaml_text, stage_yaml_text)
state = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=42).run()
print(state.total_damage)
```

低层入口（手写 sim_schema 对象，golden case 用）：直接构造 `CombatEngine(Encounter, ...)`，
见 `tests/test_engine_v01.py`。

## 测试

- golden case / 两局全等（纯净不变量）：`tests/test_engine_v01.py` 起的一批 `test_engine_*.py`
- 调度树 property test、表达式注入防护、rulebook↔文档镜像闸等：`pytest tests/`
