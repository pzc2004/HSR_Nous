## 17. Actor 形态状态机 (Actor State)

> **实现说明**：本文档按 Pydantic v2 类型描述目标 schema。当前代码仍使用 `@dataclass`，Pydantic 迁移尚未完成。文档是前瞻性定义，代码会后续对齐。

### 17.1 设计目标

建模“actor 在战斗中有多个形态”的机制，例如：
- 刃「地狱变」
- 白厄 Khaslana 终极形态
- Silver Wolf LV.999 Godmode
- 火花「直播连线」
- 希儿「蝶舞」

形态影响：
- 可用 action 集合（替换或锁定某些 action）
- 属性加成（通过 modifier 机制表达，见 §17.5）

### 17.1.1 本章定位：整体糖化（决策卡 #20）

**VM 不认识形态机**——本章全部概念在绑定/编译期展开为既有原语，引擎只见普通 modifier 与条件过滤（desugar 列为目标语义；"状态"列为引擎/编译器现状，单一事实源 `sim/state.py` `StateConfig` + `sim/engine.py` `enter_state` / `exit_state` / `register_state_config`）：

| 形态概念 | desugar（展开目标） | 状态 |
|----------|---------------------|------|
| 形态本身 | **标记 modifier**（`dispellable: false`、duration 承载）+ `singleton_group: "actor_state"`（`04_modifier.md` §4.11；互斥 = 同组，可叠加 = 不同组） | **已落地**（引擎原生：`enter_state` 挂 `STATE_<state>` 标记，`stat_effects` / `grants_immune` 并进标记） |
| `enter_state` / `exit_state` | `apply_modifier`（标记）/ `remove_modifier`（标记） | **已落地**（引擎原生 `enter_state` / `exit_state` 方法——注意：§17.6 的 `enter_state` / `exit_state` **effect_type 形态待收编**，写了编译期炸；现役通道 = 模板 `state_config` 块 + `entry_action_id`） |
| `replaces_actions` / `locked_actions` | 合法性条件注入：目标 action 合法性 += `has_modifier(标记)`，被替换者 += 全部替换标记的否定合取（生成算法唯一） | **已落地**（引擎原生合法性注入） |
| `exit_conditions` | `{trigger, value}` 列表——`on_action_count`（行动计数）/ `on_resource_depleted`（资源耗尽） | **已落地**（引擎原生 `_check_exit_conditions`，行动后检查——本章旧表"废除、映射表维护"口径作废，非糖化路径） |
| `on_enter` / `on_exit` | 进入：`entry_action_id`（该 action 施放即进入形态，`register_state_config` 登记）；退出：全路径经 `remove_modifier` 单漏斗汇聚（`exit_state` 内部统一摘标记 + `exit_remove_modifiers` 清理，发 `after_remove_modifier`） | **已落地**（原生路径） |
| `$self.actor_state` 查询 | hook ctx `$self.state`（急切字段，`sim/hooks.py` `_HookSelfNS`；缺省 `""`）；policy ctx `in_state` / `state`（`sim/policy_api.py`） | **已落地** |
| `on_state_change` 事件 | 引擎原生发射（进入发 `{actor, to_state}`、退出发 `{actor, from_state}`，bus 契约 emit） | **已落地**；**B24 数据宏落地后降格为宏**（展开为 `after_apply_modifier` / `after_remove_modifier` + `singleton_group` 过滤，模板写法不变）——宏化为目标态 |

**叠加规则（§17.9 钉死）**：多形态替换同一 action = validator error（宁严勿宽）；放逐期间标记冻结由 banish 状态冻结既有语义覆盖。表面语法（StateConfig 字段）全部保留——模板写法不变，变的是"引擎是否原生实现"。

### 17.2 ActorState 枚举

```python
class ActorState(str, Enum):
    normal = "normal"
    transformed = "transformed"      # Phainon 终结技后
    khaslana = "khaslana"            # Phainon 终极形态
    hellscape = "hellscape"          # 刃 战技
    godmode = "godmode"              # Silver Wolf LV.999
    live_link = "live_link"          # 火花 直播连线
    amplification = "amplification"  # 希儿 蝶舞
    ult_sequence = "ult_sequence"    # 终结技操控序列（姬子•启行 6 连自选、Silver Wolf LV.999 续段，见 §17.8）
```

| 值 | 角色 / 触发 |
|----|------------|
| `normal` | 默认 |
| `transformed` | Phainon 终结技后 |
| `khaslana` | Phainon 终极形态 |
| `hellscape` | 刃 战技 |
| `godmode` | Silver Wolf LV.999 |
| `live_link` | 火花 直播连线 |
| `amplification` | 希儿 蝶舞 |
| `ult_sequence` | 终结技操控序列：开大进入、额度耗尽/选择完毕退出并续放终结段（见 §17.8） |

> **实现状态**：本枚举为**目标枚举**——引擎 `StateConfig.state` 是自由字符串（`sim/state.py`，无枚举校验、无 `ActorState` Enum 类）；`hellscape` / `godmode` / `ult_sequence` 等值均无模板实例（现役实例：白厄卡厄斯兰那族）。

> **离场（放逐）不是 ActorState 枚举值**：离场是正交的**在场性**维度，由 `banish_actor` 管理（不可选中 / 状态冻结 / 回场恢复三语义，见 `05_effects.md`）——形态状态机管"可用行动与形态配置"，离场管"在不在场"。actor 可在任意形态下被放逐，离场期间形态配置冻结原样、回场后照旧；因此 ActorState 不设 `departed` / `banished` 值。离场事实的 `actor_exit`（`reason: "banish"`）见 `23_event_hook_system.md` §23.4。
>
> 落地自决策卡 #16（2026-08-15）

### 17.3 StateConfig 字段

```python
class StateConfig(BaseModel):  # 目标形态；现身为 @dataclass（sim/state.py，字段一一对应）
    state: str                                 # 形态标识（自由字符串，非 §17.2 枚举校验）
    replaces_actions: dict = {}                # type→id 或 id 列表（多强化技能）
    locked_actions: list[str] = []
    exit_conditions: list[dict] = []           # [{trigger, value}]
    stat_effects: dict[str, float] = {}        # 形态内面板加成（并进标记 modifier）
    final_action_id: str = ""                  # 倒计时最后一动强制施放的行动
    exit_remove_modifiers: list[str] = []      # 退出形态时对全体敌人移除的 modifier 清单
    banish_allies_on_enter: bool = False       # 进入形态时队友离场（白厄境界族；退出时回场）
    countdown_spd_ratio: float = 1.0           # 倒计时回合速度 = 基础速度 × 该比值
    name: str = ""                             # 形态显示名（日志用中文官方名，如"卡厄斯兰那"）
    grants_immune: list[str] = []              # 形态内免疫的 debuff 类别
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `state` | `str` | 必填 | 形态标识（自由字符串——§17.2 为目标枚举） |
| `replaces_actions` | `Dict` | `{}` | 行动替换映射：type→id 或 id 列表（如 `basic → enhanced_basic`；多强化技能 140809/140811 族） |
| `locked_actions` | `List[action_id]` | `[]` | 该形态下禁用的行动 |
| `exit_conditions` | `List[{trigger, value}]` | `[]` | 退出条件，如 `{trigger: "on_action_count", value: 3}`（`on_action_count` / `on_resource_depleted` 原生实现，行动后检查——`sim/engine.py` `_check_exit_conditions`；为 StateConfig 私有枚举，非 §4.8/§23.4 总线事件） |
| `stat_effects` | `Dict[str, float]` | `{}` | 形态内面板加成（并进标记 modifier——白厄"攻击力提高 X%"族，见 §17.5） |
| `final_action_id` | `str` | `""` | 倒计时最后一动强制施放的行动（白厄"最后的额外回合开始时立即发动最后一击"） |
| `exit_remove_modifiers` | `List[str]` | `[]` | 退出形态时对**全体敌人**移除的 modifier_id 清单（境界植入件随形态解除） |
| `banish_allies_on_enter` | `bool` | `False` | 进入形态时其他队友离场且无法行动（白厄境界族；退出时回场） |
| `countdown_spd_ratio` | `float` | `1.0` | 倒计时回合速度 = 基础速度 × 该比值（白厄"速度固定为基础速度的 60%"） |
| `name` | `str` | `""` | 形态显示名（日志用中文官方名；缺省回退 `state` 标识符） |
| `grants_immune` | `List[str]` | `[]` | 形态内免疫的 debuff 类别（140805"免疫控制类负面状态" → `["control"]`） |

> 模板 `state_config` 块另有编译键 `entry_action_id`（`_STATE_CONFIG_KEYS` 第 12 键）——**非 StateConfig 字段本体**，编译期随 StateConfig 配对传递（`register_state_config(actor_id, cfg, entry_action_id=...)`）：非空 = 该 action 施放即进入形态。

### 17.4 Actor 新增字段

```python
class Actor(BaseModel):
    # ... 既有字段 ...
    actor_state: ActorState = ActorState.normal
    state_config: StateConfig | None = None
```

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `actor_state` | `ActorState` | `normal` | 当前形态 |
| `state_config` | `StateConfig?` | `None` | 当前形态配置（`actor_state != normal` 时有效） |

形态状态机适用于**所有 actor**：角色、忆灵、召唤物、敌人。

### 17.5 形态属性加成走 modifier

**已定决策**：形态带来的属性变化（如刃地狱变“造成伤害提高”）通过 `StateConfig.stat_effects` 表达、**并进形态标记 modifier**（`enter_state` 挂标记时 `stat_effects` 一并入件，`sim/engine.py`）——保持单一属性修改路径，让形态加成跟普通 buff 处理逻辑一致；**不引入额外的 `state_stats_override` 字段**。

### 17.6 新增 effect_type

> **实现状态**：本节三个 effect_type（`enter_state` / `exit_state` / `transform_action`）**待收编**——写了编译期炸（`05_effects.md` §5.2）；现役形态通道 = 模板 `state_config` 块（§17.3）+ `entry_action_id`（见 §17.1.1 状态列）。下文为目标形态。

#### `enter_state`

```yaml
effect_type: "enter_state"
to_state: "hellscape"
duration: 3
replaces_actions:
  shard_sword: forest_of_swords
locked_actions: ["blade_skill"]
on_enter_effects:
  # 假设 self.hellscape_dmg_boost / self.hellscape_duration 已通过 variable_bindings 绑定
  - effect_type: "apply_modifier"
    modifier:
      modifier_id: "hellscape_dmg_boost"
      stat: "all_dmg_bonus"
      flat_bonus: "$self.hellscape_dmg_boost"
      duration: "$self.hellscape_duration"
on_exit_effects:
  - effect_type: "remove_modifier"
    modifier_id: "hellscape_dmg_boost"
```

| 字段 | 说明 |
|------|------|
| `from_state` | 允许从哪些形态切换（可选，默认任何形态） |
| `to_state` | 目标形态 |
| `duration` | 持续回合数；`0` 表示永久 |
| `replaces_actions` | action 替换映射 |
| `locked_actions` | 锁定 action 列表 |
| `exit_conditions` | 自定义退出条件 |
| `on_enter_effects` | 进入形态时触发的效果 |
| `on_exit_effects` | 退出形态时触发的效果 |

#### `exit_state`

```yaml
effect_type: "exit_state"
target_state: "normal"
```

#### `transform_action`

```yaml
# 单独把某个 action 替换为另一个 action，不切换整体形态
effect_type: "transform_action"
target_action: "basic"
new_action_id: "enhanced_basic"
```

### 17.7 示例：刃 (1205) Hellscape

> **实现状态**：本示例为**目标形态**——使用 §17.6 待收编的 `enter_state` effect_type（写了编译期炸）；非现役模板（现行 `1205_刃.yaml` 为生成器骨架，无此机制块）。现役等价通道 = 模板 `state_config` 块（§17.3）。

```yaml
# 示例（示意——非文件路径，勿按模板引用）
actor_id: "1205"
name: "blade"

lookup_tables:
  hellscape_duration:   [3, 3, 3, 3, 3]
  hellscape_dmg_boost:  [0.20, 0.25, 0.30, 0.35, 0.40]
  hellscape_taunt:      [10.0, 10.0, 10.0, 10.0, 10.0]   # +1000%（scaling 后最终 = 基础 ×11）

variable_bindings:
  - self.hellscape_duration  = lookup_table("hellscape_duration",  index=$build.skill_levels.skill - 1)
  - self.hellscape_dmg_boost = lookup_table("hellscape_dmg_boost", index=$build.skill_levels.skill - 1)
  - self.hellscape_taunt     = lookup_table("hellscape_taunt",     index=$build.skill_levels.skill - 1)
  - self.m2_crit_rate        = 0.15  # 星魂效果固定值，不按行迹等级索引

actions:
  - action_id: "120502"
    name: "地狱变"
    action_type: "skill"
    effects:
      - effect_type: "enter_state"
        to_state: "hellscape"
        duration: "$self.hellscape_duration"
        replaces_actions:
          shard_sword: forest_of_swords
        locked_actions: ["blade_skill"]
        on_enter_effects:
          - effect_type: "apply_modifier"
            target: "self"
            modifier:
              modifier_id: "hellscape_dmg_boost"
              stat: "all_dmg_bonus"
              flat_bonus: "$self.hellscape_dmg_boost"
              duration: "$self.hellscape_duration"
          - effect_type: "apply_modifier"
            target: "self"
            modifier:
              modifier_id: "hellscape_taunt"
              stat: "taunt"
              scaling_from_source: "$self.hellscape_taunt"
              source_stat: "taunt"
              duration: "$self.hellscape_duration"
          - effect_type: "apply_modifier"
            condition: "$build.eidolon >= 2"
            target: "self"
            modifier:
              modifier_id: "hellscape_m2_crit_rate"
              stat: "crit_rate"
              flat_bonus: "$self.m2_crit_rate"
              duration: "$self.hellscape_duration"
        on_exit_effects:
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_dmg_boost"
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_taunt"
          - effect_type: "remove_modifier"
            modifier_id: "hellscape_m2_crit_rate"
```

### 17.8 操控序列：终结技续段执行

> **实现状态**：本节为**目标形态**——依赖 §17.6 待收编的 `enter_state` / `exit_state` effect_type（写了编译期炸）；`exit_conditions` 的 `on_resource_depleted` 退出条件本身已原生实现（§17.3）。示例为示意（非现役模板——1510 `姬子•启行` 为生成器骨架）。

一类终结技不是"一次结算完"，而是**开大进入操控形态 → 逐段选择 → 满足条件退出并自动续放终结段**。按状态机建模——**复用 `enter_state` / `exit_state` + `custom_resources` 额度计数，不引入检查点 / 可恢复执行模型**：

1. **进入**：终结技 `enter_state` 进入操控形态（`ult_sequence`），同时初始化额度资源（如 6 次自选）
2. **操控段**：形态内可用行动被 `replaces_actions` 替换为"自选段"行动，每次选择消耗 1 点额度
3. **退出 + 续段**：额度耗尽（`exit_conditions` 用 `on_resource_depleted`）或操控方选择完毕（主动 `exit_state`）→ 退出形态，`on_exit_effects` 自动续放终结段
4. **全灭续段**：波次提前结束（敌方全灭）导致形态结束时，`on_exit_effects` 照常结算——续放段不丢失（Silver Wolf LV.999 全灭续段）

```yaml
# 姬子•启行终结技：6 次自选 + 耗尽自动续放终结段
custom_resources:
  himeko_ult_charges:
    max: 6                       # 操控额度

actions:
  - action_id: "himeko_ultimate"
    name: "终结技"
    action_type: "ultimate"
    effects:
      - effect_type: "enter_state"
        to_state: "ult_sequence"
        replaces_actions:
          himeko_basic: himeko_ult_pick
          himeko_skill: himeko_ult_pick
        exit_conditions:
          - {trigger: "on_resource_depleted", value: "himeko_ult_charges"}   # StateConfig 私有枚举（见 §17.3），非总线事件
        on_exit_effects:
          # 终结段：退出形态时自动续放
          - effect_type: "deal_damage"
            target: "all_enemies"
            damage_type: "fire"
            amount: "$self.atk * 2.0"

  - action_id: "himeko_ult_pick"
    name: "自选段"
    action_type: "ultimate"
    target_type: "enemy_single"
    effects:
      - trigger: "on_cast"
        target: "self"
        effect_type: "consume_resource"
        resource_id: "himeko_ult_charges"
        amount: 1
      - trigger: "on_cast"
        target: "primary_target"
        effect_type: "deal_damage"
        formula: "damage"
        damage_type: "fire"
        amount: "$self.atk * 0.8"
```

> 落地自决策卡 #11（2026-08-14）

### 17.9 形态叠加规则

**引擎现状（已钉死）**：形态互斥经 `singleton_group: "actor_state"` 实现——形态标记 modifier 同组，**同目标同时仅一形态**：新形态进入时旧标记被替换摘除（`sim/modifiers.py` 同组先摘旧，`reason: "replace"`），即"新形态顶掉旧形态"。多形态替换同一 action = validator error（宁严勿宽，见 §17.1.1）；放逐期间标记冻结由 banish 状态冻结语义覆盖。

`transformed` 可累加等例外形态（叠加 = 不同 `singleton_group`）与共享语义的细化**待决策（TBD）**——叠加语义目标态见 §17.1.1 desugar 表"互斥 = 同组，可叠加 = 不同组"。

### 17.10 TBD

- 状态切换的“过渡帧”是否建模（如 Phainon 终极技动画，TBD）。

---
