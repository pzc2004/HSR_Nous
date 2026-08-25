## 14. 策略模型 (Policy)

策略是可独立输入、可搜索优化的战斗决策逻辑。采用 **Rule-based + 参数化混合** 设计，用结构化数据模型定义。

### 设计原则

- **可执行**：模拟器直接 interpret，不需要 LLM 实时参与
- **可参数化**：关键数值（如大招阈值）抽离为可调参数，方便网格搜索/贝叶斯优化
- **LLM 友好**：结构清晰，LLM 容易生成和修改
- **维度拆分**：技能选择、目标选择、时机策略分离

### 策略结构

```yaml
policy:
  name: "1001_default"           # 带 actor ID 前缀（同人物多实体消歧纪律）

  # ========== 技能选择规则（按 priority 降序匹配）==========
  action_rules:
    - condition: "energy >= ULT_THRESHOLD"    # 参数平铺注入（无 parameters. 前缀，见"表达式上下文"表）
      action: "ultimate"
      priority: 100
      description: "能量满时开大"

    - condition: "skill_points > 0"           # "队友无护盾"类谓词未接入上下文（见下表）
      action: "skill"
      priority: 50
      description: "有战技点时给盾"

    - condition: "true"
      action: "basic"
      priority: 0
      description: "默认普攻"

  # ========== 目标选择规则 ==========
  target_rules:
    - condition: "action_type == 'skill'"
      selector: "lowest_hp_ally"
      priority: 100

    - condition: "action_type == 'ultimate'"
      selector: "all_enemies"
      priority: 100

    - condition: "true"
      selector: "primary_target"
      priority: 0

  # ========== 时机策略（可选；未落地——引擎无时机决策点，代码侧 TimingRule 已退役，收编时重建）==========
  timing_rules:
    - condition: "buff.MOD_XXX.stack >= 3 && !enemy.broken"
      timing: "delay"
      delay_condition: "enemy.broken == true"
      description: "特定 buff 叠满但敌人未击破，延迟到击破后再出手"

  # ========== 可调参数 ==========
  parameters:
    ULT_THRESHOLD: 120        # 大招能量阈值
    SHIELD_PRIORITY: 0.8     # 护盾优先级权重
    HP_THRESHOLD: 0.5        # 低血量阈值
```

### 规则匹配逻辑

1. **技能选择**：按 `priority` 降序遍历 `action_rules`，第一条 `condition` 为真的规则被执行
2. **目标选择**：同样按优先级匹配，决定技能打谁

> 原第 3 条"时机选择"已删——`timing_rules` 未落地且代码侧已退役（见上文策略结构中的标注）。

### 合法性契约（legal action set）

policy **只选不越权**：引擎在每个决策点先计算 `legal_action_set`，分两段——

1. **形态换组**：当前形态/状态决定可用技能组（如白厄变身后普通战技不在集内）
2. **因子过滤**：资源门槛（能量/战技点/充能阈值）、控制状态、锁定/禁用、特殊回合限制（"仅能使用 X"类）

policy 的选择必须落在集内；静态非法（未知键/非法枚举/未知选择器/非法表达式）**编译期报错**（`_POLICY_KEYS` / `POLICY_TARGET_SELECTORS` / 表达式预编译等闸，见 `13_validator.md` §13.2）。"规则在动态上永不命中 legal set 时 validator 给 warning"的设想**未落地**——现役无此 warning 通道（validator.py 已退役删除）。实测未定项（如银枝满能量能否放小版终结技）只影响 legal set 的计算分支，不影响 policy 结构。

> 落地自决策卡 #4 合法性契约注（2026-08-14）

### 表达式上下文

策略表达式中可以访问的变量（单一事实源：`sim/policy_api.py` `CompiledPolicyRuntime._context` + `select_target` / `_target_ctx`）：

| 变量 | 说明 |
|------|------|
| `energy` / `max_energy` | 当前能量 / 能量上限 |
| `skill_points` | 当前战技点 |
| `hp` / `max_hp` | 当前生命 / 有效生命上限（effective 口径，吃 hp_pct/flat/覆写 modifier） |
| `res_<resource_id>` | 自定义资源当前值（**平铺**注入，如 `res_fire_seed`——"火种<12 攒战技"族） |
| `in_state` / `state` | 是否处于形态 / 形态标识（`state_config` 驱动，缺省 `False` / `""`） |
| `<parameters 键>` | 策略参数**平铺**注入（如 `ULT_THRESHOLD`——**无 `parameters.` 前缀**） |
| `action_type` | 当前待选 action 的类型（仅 `target_rules` 语境注入） |
| `target_hp` / `target_hp_pct` / `target_broken` | 候选目标状态（仅 `filter` / `first` 参数化选择器的 `condition` 内可用） |

> 历史登记的 `target_hp_ratio` / `buff.<id>` / `enemy.<attr>` / `ally_without_shield` / `allies[]` / `enemies[]` / `turn_count` / `cycle` / `wave_index` / `enemy_next_av` / `$resource.<id>` / `parameters.` 前缀均**未接线**——表达式 parse 放行裸 Name，上下文无此键，写了运行期"未定义变量"炸。

### 策略状态机（custom_resources 作相位容器）

> **实现状态**：本节整体**未落地**——`_POLICY_KEYS` 无 `mode` / `state_resources` / `state_hooks` 键（写了编译期炸）；hook 形态的 `state_hooks` 同样超出 `_HOOK_KEYS`（`scope` 未接线）。下文为目标态设计（仿 `timing_rules` 标注先例）。

policy 可声明 **team 级自定义资源**作策略计数器/相位容器，并通过 `state_hooks`（复用 `23_event_hook_system.md` 的 hook 形态）在战斗事件中维护；`condition` 用 `$resource.<id>` 读取。用于表达"相位"类策略（首回合特殊处理、每 N 回合循环等）。

```yaml
policy:
  name: "phase_demo"
  mode: "rule_based"          # rule_based（默认）| scripted | hybrid（见下节）

  # ========== 策略状态资源与维护 ==========
  state_resources:
    action_count: {max: 999, owner: "team"}       # 每次行动自增的相位计数器

  state_hooks:                                     # 复用 23 章 hook 形态
    - event: "on_after_action"
      scope: "team"
      effects:
        - effect_type: "gain_resource"
          resource_id: "action_count"
          amount: 1

  action_rules:
    - condition: "$resource.action_count == 0"
      action: "skill"
      priority: 100
      description: "相位策略：首回合战技"
    - condition: "true"
      action: "basic"
      priority: 0
      description: "之后普攻"
```

validator 检查：`state_resources` 的 `resource_id` 与 `state_hooks` 内引用必须存在；hook 字段同 23.5  schema。

### scripted_policy：脚本回放变体

> **实现状态**：本节整体**未落地**——`_POLICY_KEYS` 无 `mode` / `script` 键（写了编译期炸）。注意与现役 `ScriptedPolicy`（`sim/policy_api.py`：golden case 用的 **rotation 循环脚本**——按回合循环的行动类型列表 + `ult_timing`）**同名不同物**：本节的 `mode: "scripted"` 是 YAML policy 声明的逐回合有序脚本（目标态），现役 ScriptedPolicy 是 Python 侧测试用具，不进 build.yaml 编译通道。

`mode: "scripted"` 的策略用**有序行动脚本**驱动，仅用于**回放验证人肉发现的轴**（如永动机），**不进搜索空间**：

```yaml
policy:
  name: "replay_axis_demo"
  mode: "scripted"
  script:
    - {turn: 1, actor: "seele", action: "skill"}
    - {turn: 2, actor: "seele", action: "basic"}
    - {turn: 3, actor: "seele", action: "ultimate", target: "boss"}
```

- 脚本条目按 turn 序执行；`actor`/`action` 必须能解析到该 actor 的 actions 内
- `mode: "hybrid"`：脚本覆盖列出的决策点，未覆盖的回合/角色回退到 `action_rules` 默认匹配；`mode: "scripted"` 严格模式——未覆盖即报错
- 脚本策略同样可配 `state_resources`/`state_hooks`（如永动机的能量/计数校验）

### 敌人意图可见性（5a）

策略表达式可读敌人的**行动序信息**（`enemy_next_av` 等）——敌人何时行动是公开信息，用于"卡在敌人行动前开盾"类策略。敌人 AI 行为/目标预测（5b）**暂缓**（概率性，归场景二，不建模）。

> **实现状态**：`enemy_next_av` **未接线**——不在策略表达式上下文（见"表达式上下文"表末注），写了运行期"未定义变量"炸。

### 验收示例：留大给第二波

```yaml
action_rules:
  - condition: "energy >= ULT_THRESHOLD"   # 可运行形态（参数平铺注入）
    action: "ultimate"
    priority: 100
    description: "留大给第二波"
  - condition: "true"
    action: "basic"
    priority: 0
```

> 注：原示例的 `wave_index >= 2 && energy >= parameters.ULT_THRESHOLD` 不可运行——`wave_index` 未接入策略上下文、`parameters.` 前缀不存在（见"表达式上下文"表末注）；波次条件待 `wave_index` 接线后恢复。

### 为什么不用自然语言策略

| 自然语言 | Rule-based 模型 |
|---------|---------------|
| "优先使用战技" | `condition: "skill_points > 0", action: "skill"` |
| 不可精确执行 | 100% deterministic |
| 不可搜索优化 | 参数可独立调整，适合贝叶斯优化 |
| LLM 生成后需人工翻译 | LLM 直接生成可执行结构 |

### 参数优化示例

```python
# 网格搜索最佳大招阈值（取数口径真实；搜索循环从简）
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine

def evaluate(threshold: float) -> float:
    build["build"]["policy"]["parameters"]["ULT_THRESHOLD"] = threshold
    engine = CombatEngine.from_compiled(
        compile_encounter(build, stage),  # build/stage：build.yaml / stage.yaml 加载的 dict
        seed=42,
    )
    state = engine.run()                  # → BattleState（无 .dps 属性）
    return state.total_damage / max(state.clock, 1e-9)   # DPS 现算

# 在 [100, 140] 区间逐值扫描最优阈值
best_threshold = max(range(100, 141, 5), key=evaluate)
```

### 策略与 Encounter 的关系

```yaml
encounter:
  encounter_id: "E_001"
  name: "示例关卡"
  cycle: {first_cycle_av: 150, subsequent_cycle_av: 100}   # 可选，None = 不启用轮次
  actors: [...]          # 我方 + 敌方布场
  policy: {...}          # <-- 每个 encounter 可绑定不同策略（仅组装期元数据，引擎不消费——
                         #     运行时策略走 CompiledPolicyRuntime / ScriptedPolicy 通道，
                         #     见 sim_schema/encounter.py 字段注）
  termination: {mode: "fixed_av", max_action_value: 1500}
```

（字段按 `sim_schema/encounter.py` `Encounter` 重写——现役字段：`encounter_id` / `name` / `cycle` / `actors` / `policy` / `termination`；旧示例的 `formula` / `globals` / `initial_modifiers` 不是 Encounter 字段。）

同一个队伍配不同策略，可以对比不同操作手法的差异。

战前秘技顺序和进战策略单独在 `20_pre_battle_strategy.md` 中定义，可与 policy 组合使用。

---
