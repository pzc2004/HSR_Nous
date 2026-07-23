# 机制矩阵盘点方法论

> **目的**：记录"用 LLM 标原语 + 对照 sim_schema"的完整流程，供未来工程师和 LLM 复用扩展
> **适用场景**：补加新角色、扩展新原语、验证 sim_schema 文档的覆盖度
> **对应产出**：`02_matrix.md`（矩阵视图）+ `04_gap_analysis.md`（GAP 报告）
> **历史说明**：§5/§6/附录为早期试点轮（round1/round2，23 角色时代）实录；§1–§4 是通用方法论，但其中数字与批次示例（23 角色 / 168 原语 / 6 subagent 等）也取自试点轮，仅作说明。文中提到的产物文件在本机 `reports/mechanics_scan/`（gitignored，新克隆不存在）。

阅读路径：§1 术语 → §2 prompt → §3 归一化 → §4 数据流 → §5 限制 → §6 扩展

---

## 1. 术语定义

### 1.1 什么是"原语"（Primitive）

**原语** = 战斗机制可被模拟器执行的最小动作单元，粒度等同于 sim_schema 中 `05_effects.md` 的 `effect_type` 字段或 `04_modifier.md` 的触发动作。判定标准：能否用一行 `effect_type: "<name>"` + 参数表达。

| 例子 | 是否原语 | 说明 |
|------|----------|------|
| `gain_skill_point` / `deal_damage` / `transform_state` | 是 | 标准 effect_type |
| "火种"（Coreflame）/ "好活当赏" | **否** | 资源/buff **实例**，不是动作 |
| "Phainon 转形态" / "阿哈时刻" | **否** | 由多个原语**组合**的高层行为/复合时机 |

**关键区分**：原语是**动词级别**（verb-level）的机制单元，描述"做什么动作"；游戏概念是**名词级别**（noun-level）的实体或状态，描述"是什么东西"。

### 1.2 三个状态色的定义

| 状态 | 含义 | 判定依据 |
|------|------|----------|
| 🟢 **green** | sim_schema 已有明确原语与文档支持，标注无歧义 | `effect_type` / `modifier_type` / `trigger` 字段直接对应；能在文档中定位到具体段落 |
| 🟡 **yellow** | sim_schema 有相关原语但描述不明确、变体缺失或需多文档交叉验证 | 同一原语有 `effect_type` 但缺变体；或需多文档推断（如 `apply_modifier` 的 `mitigation` 减伤类型） |
| 🔴 **red** | sim_schema 完全缺失该原语或相关机制；需要新建文档或扩展枚举 | 文档中无任何对应原语；或只能由通用 `script` effect 模拟但语义不直接 |

### 1.3 主题分类（用于横向汇总）

168 个原语归为 9 个主题：

| 主题 | 代表原语 | 23 角色覆盖 |
|------|----------|------------|
| 资源/能量 | `gain_resource` / `consume_resource` / `gain_energy` / `gain_punchline` | 36 |
| 伤害/效果 | `deal_damage` / `deal_dot_damage` / `apply_modifier` | 36 |
| 其他/特殊 | `add_stat` / `override_action_param` / `forced_taunt` | 28 |
| 联动/触发 | `trigger_follow_up` / `grant_extra_turn` / `transfer_stacks` | 20 |
| 限制/生存 | `immune_death` / `per_turn_trigger_cap` / `set_hp_to_percent` | 19 |
| 欢愉/阿哈 | `unlock_elation_skill` / `aha_instant_execution` | 10 |
| 状态/变形 | `transform_state` / `extend_buff_duration` | 9 |
| 场地/区域 | `deploy_zone` / `dispatch_top_loot_box` | 6 |
| 召唤/忆灵 | `summon` / `modify_summon_hits_per_action` | 4 |

---

## 2. LLM Prompt 模板

> 注：本节是试点轮的 prompt 设计记录；**当前标注模板以同目录 `ANNOTATE_PROMPT.md` 为准**（输出格式已改为列表记录）。

盘点分两阶段：先标"角色用到了什么原语"（应有清单的子集），再标"schema 已有什么原语"（应有清单的超集）。两阶段结果对比得到 GAP。

### 2.1 阶段 1 Prompt：标注角色使用的原语

**输入**：

```json
{
  "character_id": "1005", "name": "Kafka", "path": "Warlock", "element": "Thunder",
  "skill": {
    "skill_id": "100502", "skill_name": "Caressing Moonlight", "skill_type": "BPSkill",
    "desc": "Deals Lightning DMG to a target enemy and Lightning DMG to enemies adjacent to it. If the target enemy is currently receiving DoT, all DoTs ... immediately produce DMG",
    "parameters": [{"name": "主目标倍率", "value": 0.80}, {"name": "相邻目标倍率", "value": 0.50}],
    "fandom": {"toughness_dmg": "20/10", "sp_cost": 1, "energy_gen": 30}
  }
}
```

**Prompt 模板**：

```text
你是一位崩坏：星穹铁道战斗机制分析专家。请阅读下面这个技能的描述与数值，识别它**用到了哪些 sim_schema 原语**。

## sim_schema 原语清单
（以下清单从 05_effects.md + 04_modifier.md + 12_summon.md 抽取，约 60+ 条标准 effect_type；
  完整清单见 src/hsr_nous/sim_schema/docs/）
- deal_damage / deal_dot_damage / deal_toughness_damage
- heal / set_hp_to_percent / fix_hp_floor
- gain_skill_point / consume_skill_point
- gain_energy / gain_resource / consume_resource
- apply_modifier / remove_modifier / spread_modifier
- add_stat / override_action_param / append_action_param
- advance_action / grant_extra_turn
- summon_action / dispatch_summon
- trigger_follow_up / trigger_talent_*
- transform_state / enter_state / exit_state
- immune_death / immune_to_cc / ignore_debuff
- deploy_zone / dispatch_top_loot_box
- 欢愉专属：unlock_elation_skill / aha_instant_execution / gain_punchline / gain_certified_banger

## 任务
对技能里的每一句"做什么"，识别：
1. 用到了哪些**原语**（可能一个原语被多次使用）
2. 给出该原语的**定义**（一句话）
3. 给出**技能原文证据**（贴出 desc 中的关键短语）
4. 判定该原语在 sim_schema 中的**支持状态**（green/yellow/red）

## schema_status 判定标准

- **green**：sim_schema 中有**直接对应**的 effect_type / modifier_type / trigger；
  能在文档中定位到具体段落（如 `05_effects.md` 列出 `effect_type: deal_damage`）
- **yellow**：sim_schema 有**相关**原语但**描述不明确、缺少变体**或**需多文档交叉推断**。
  例：标准 `add_stat` 存在但"按 HP% 加成 ATK"（Jingliu 谱状态）无现成公式
- **red**：sim_schema **完全没有对应原语**；或只能由通用 `script` effect 模拟但语义不直接。
  例：`consume_resource`（标准资源外的自定义资源）、`transform_state`（actor 形态切换）

## 输出格式（严格遵守，每行一个原语）

[
  {
    "name": "<原语名，snake_case>",
    "definition": "<该原语在此技能中做什么，一句话>",
    "evidence": "<desc 中的关键原文或 Fandom 数值>",
    "schema_status": "<green|yellow|red>",
    "schema_evidence": "<对应 sim_schema 文档位置，如 'docs/05_effects.md effect_type: deal_damage'；若 red 则说明无对应原语>"
  },
  ...
]

## 重要规则
1. 原语粒度 = `effect_type` 级别，不要拆得过细（不要把 `deal_damage` 拆成 `deal_damage_with_split_scaling` 等变体）
2. 不要漏标：desc 中每一句"做什么"都应对应至少一个原语
3. 不要重复：同一原语在同一技能中应只出现一次；若多次触发则合并标注
4. 资源类原语用通用名 `gain_resource` / `consume_resource`，不要为每个新资源造独立原语
5. 形态切换用 `transform_state`，不要用 `enter_hellscape_state` 等具体形态名
6. 欢愉命途的角色额外标注 `path: elation` 到角色元信息，但原语用 `unlock_elation_skill` 等通用名

## 输入
{skill_json}
```

**输出示例**（Kafka 战技 `Caressing Moonlight`，简化）：

```json
[
  {
    "name": "deal_damage",
    "definition": "对单体目标造成雷属性伤害，并扩散到相邻目标",
    "evidence": "desc: Deals Lightning DMG to a target enemy and Lightning DMG to enemies adjacent to it",
    "schema_status": "green",
    "schema_evidence": "docs/05_effects.md effect_type: deal_damage"
  },
  {
    "name": "trigger_existing_dot",
    "definition": "若目标已有 DoT 立即结算一次",
    "evidence": "desc: If the target enemy is currently receiving DoT, all DoTs ... immediately produce DMG",
    "schema_status": "red",
    "schema_evidence": "01_formula.md 仅定义 dot_damage 公式，无立即触发既有 DoT 的 effect_type; 04_modifier.md 触发时机无 on_dot_retrigger"
  },
  {
    "name": "consume_skill_point",
    "definition": "释放战技消耗 1 个战技点",
    "evidence": "Fandom sp_cost=1",
    "schema_status": "green",
    "schema_evidence": "docs/03_actor.md skill_point_cost 字段"
  },
  {
    "name": "gain_energy",
    "definition": "释放战技后回复 30 能量",
    "evidence": "Fandom energy_gen=30",
    "schema_status": "green",
    "schema_evidence": "docs/02_globals.md section 2.1 战技 30 能量"
  }
]
```

### 2.2 阶段 2 Prompt：标注 schema 文档定义的所有原语

**目的**：抽取 sim_schema 全部文档（20+ 章）中**已定义**的原语，作为"应有清单"的超集。

**Prompt 模板**：

```text
你是一位 sim_schema 文档分析专家。请通读下面全部 sim_schema 文档（20+ 章），提取所有"可被模拟器执行的原语"。

## 原语判定标准
1. **effect_type**（05_effects.md）：如 `deal_damage` / `gain_skill_point` / `apply_modifier`
2. **modifier_type**（04_modifier.md）：如 `buff` / `debuff` / `shield` / `heal`（dot/control 已并入 debuff 作 debuff_kind 子类型）
3. **trigger**（04_modifier.md §4.8）：如 `on_battle_start` / `on_kill` / `on_energy_full`
4. **action_type**（03_actor.md）：如 `basic` / `skill` / `ultimate` / `follow_up`
5. **state**（03_actor.md）：如 `character` / `monster` / `summon`
6. **target_type**（03_actor.md / 05_effects.md）：如 `enemy_single` / `enemy_aoe` / `all_allies` / `self`

## 输出格式
[
  { "name": "<原语名>",
    "category": "<effect_type|modifier_type|trigger|action_type|state|target_type>",
    "definition": "<一句话>",
    "doc_location": "<对应文档路径>",
    "parameters": ["<参数>", ...] }
]

## 输入
{sim_schema_docs}
```

**示例输出**（节选）：

```json
[
  { "name": "deal_damage", "category": "effect_type",
    "definition": "对指定目标造成直接伤害", "doc_location": "docs/05_effects.md",
    "parameters": ["formula", "target", "scaling", "damage_type"] },
  { "name": "on_kill", "category": "trigger",
    "definition": "击杀敌人时触发", "doc_location": "docs/04_modifier.md §4.8",
    "parameters": [] }
]
```

### 2.3 GAP 推导

两阶段结果对比：
- **阶段 1 出现的原语** ∖ **阶段 2 出现的原语** = **红色缺口**（角色用到但 schema 无）
- **阶段 1 出现的原语** ∩ **阶段 2 出现的原语** = **绿色/黄色**（按阶段 1 标注的 schema_status）
- **阶段 2 出现的原语** ∖ **阶段 1 出现的原语** = **schema 过度定义**（理论优化方向，本盘点未深入）

`04_gap_analysis.md` §2 对应红色缺口，§3 对应黄色弱化。

---

## 3. 归一化规则

### 3.1 为什么需要归一化

阶段 1 的 LLM 输出**粒度不一致**。同一原语可能被不同 subagent 标成不同名字：

| JSON 实际名 | subagent 习惯 | 出现次数 |
|-------------|---------------|----------|
| `deal_damage_with_split_scaling` | Blade 终结技用 | 1 |
| `deal_damage_by_tally` | Hyacine 忆灵用 | 1 |
| `deal_max_hp_scaled_damage` | 各种"按最大生命值比例" | 2 |
| `deal_dot_damage` | DoT 命中 | 5 |

这些在游戏机制层面都是 `deal_damage`（基础 effect_type），变体由 `scaling` 表达式参数区分。若不归一化，23 角色会得到 ~370 个 unique primitive name，无法横向对比。

### 3.2 归一化原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **语义相同则合并** | 同一 `effect_type` 下，所有变体归并到通用名 | `consume_hp_percent` / `consume_tally` / `consume_overflow_resource` → `consume_resource` |
| **语义不同则保留细分** | 当变体本身需要独立原语（如 `trigger_dot_immediately` 是 `deal_dot_damage` 的特例，但需独立 effect_type 表达） | `trigger_existing_dot` 保持独立，不归并到 `deal_dot_damage` |
| **动词级别** | canonical key 以动词开头 | `gain_*` / `consume_*` / `apply_*` / `deploy_*` / `trigger_*` / `transform_*` |
| **资源类用通用名** | 自定义资源（Coreflame / Punchline / MMR / Tally）都归到 `gain_resource` / `consume_resource` | `gain_coreflame` / `gain_punchline` / `gain_hidden_mmr` → `gain_resource`（但 `gain_punchline` 因 5 角色高频使用作为独立 canonical key 保留） |
| **形态切换用通用名** | 所有变形态（Hellaspe / Khaslana / Godmode / Amplification）都归到 `transform_state` | `enter_hellscape_state` / `transform_to_godmode` → `transform_state` |

### 3.3 主要归类（synonym map 分类摘要）

`.agents/skills/mechanics-scan/run_round.py` 的 `synonyms` 字典有约 400 条目（归一化权威，diff 默认启用）。归一化结果按主类汇总（仅列代表性变体，详细见脚本）：

| canonical key | 吸收的细粒度名（节选） | 涉及角色数 |
|---------------|------------------------|------------|
| `deal_damage` | `deal_dmg_by_max_hp` / `deal_aoe_damage` / `deal_blast_damage` / `deal_damage_with_split_scaling` / `deal_damage_by_tally` / `deal_max_hp_scaled_damage` / `deal_true_damage` / `deal_elation_damage` 等 20+ | 20+ |
| `add_stat` | `add_dmg_bonus` / `add_crit_rate` / `add_res_pen` / `add_def_reduction` / `add_vulnerability` / `excess_spd_to_crit_dmg` / `stack_based_damage` / `conditional_add_stat` 等 40+ | 16 |
| `apply_modifier` | `apply_dmg_reduction_modifier` / `apply_freeze` / `apply_weakness` / `debuff_enemy` / `apply_vulnerability` / `apply_zone` 等 20+ | 10+ |
| `remove_modifier` | `dispel_debuff` / `remove_debuff` / `remove_state` / `dismiss_zone` / `remove_resource_cap` | 5+ |
| `gain_resource` | `gain_charge_stack` / `gain_punchline` / `gain_certified_banger` / `gain_hidden_mmr` / `gain_thrill` / `gain_elation` 等 10+ | 12+ |
| `consume_resource` | `consume_charge_stacks` / `consume_overflow_resource` / `consume_tally` / `consume_hp_percent` / `consume_ultimate_energy` / `convert_resource` 等 25+ | 4+ |
| `transform_state` | `transform_actor` / `transform_action` / `enter_state` / `enter_hellscape_state` / `exit_state` / `change_damage_type` / `set_action_state` / `transform_to_godmode` / `replace_action_in_state` / `set_spd_to_zero` / `banish_ally` / `lock_turn_entry` | 7+ |
| `immune_death` | `immune_to_cc` / `immune_crowd_control` / `death_save` / `death_immunity` / `ignore_debuff` | 5+ |
| `deal_dot_damage` | `dot_chance_apply` / `dot_add` / `dot_spread` / `trigger_dot_immediately` / `trigger_existing_dot` | 5+ |
| `trigger_follow_up` | `follow_up_attack` / `trigger_on_heal_received` / `trigger_on_ally_hp_decreased` / `trigger_on_energy_received` | 8+ |
| `heal` | `heal_on_attack` / `heal_on_battle_start` / `consume_hp_to_heal` / `fix_hp_floor` | 6+ |
| `deploy_zone` | `deploy_territory` / `deploy_zone_indefinite` / `zone_create` / `zone_expire` / `maze_zone` | 3+ |
| `summon` | `summon_unit_on_battle_start` / `dismiss_summon` / `inherit_stats_from_owner` / `joint_attack` | 6+ |
| `set_hp_to_percent` | `set_hp_to_value` / `set_hp_to_1` / `self_damage_on_insufficient_hp` / `set_max_hp` / `modify_max_hp` | 3+ |
| `override_action_param` | `override_skill_max_level` / `modify_action_param` / `skill_level_up` / `append_action_param` | 8+ |
| `advance_action` | `advance_all_action` / `advance_action_on_summon_disappear` / `repeat_advance_action` / `self_action_advance` | 7+ |
| `grant_extra_turn` | `grant_extra_turn_on_kill` / `grant_extra_turn_to_summon` / `grant_extra_conditional_turn` | 5+ |
| `mitigate_damage` | `distribute_damage_to_self` / `resist_debuff` | 3+ |

**未归一化、保持独立的原语**（约 30+）：

- 欢愉专属：`aha_instant_execution` / `unlock_elation_skill` / `aha_moment`
- 触发时机：`on_ally_certified_banger_gain` / `on_ally_certified_banger_expire` / `on_target_dead_redirect` / `on_energy_threshold_reach` / `on_follow_up_attack_dispatch`
- 高度特化：`sync_hp_pct` / `refresh_extra_turns` / `instant_defeat_normal_enemy` / `select_random_debuff_from_pool` / `dispatch_top_loot_box*`（3 个变体）
- 资源类高频独立：`gain_punchline` / `gain_certified_banger` / `gain_hidden_mmr`（3 角色共用，但作为 `gain_resource` 之外的独立 canonical key 保留）

### 3.4 canonical key 命名约定

| 规则 | 说明 | 示例 |
|------|------|------|
| snake_case | 全小写 + 下划线分隔 | `transform_state` |
| 动词在前 | 原语是动作，动词打头 | `gain_*` / `consume_*` / `apply_*` / `deploy_*` |
| 名词在后 | 资源/目标类型/状态名 | `gain_skill_point` / `consume_resource` / `transform_state` |
| 变体用 `with_` / `on_` / `to_` 介词 | 表达"附加条件" | `deal_damage_with_split_scaling` / `apply_vulnerability_on_elation_skill` / `transform_basic_to_enhanced_basic` |
| 同一动作的不同变体在 CSV 中合并 | 阶段 1 输出多版本，merge 时按 synonyms 折叠到主名 | `p_deal_damage` 列覆盖 20+ 变体 |

**column 前缀**：CSV 中所有原语列以 `p_` 开头（primitive 缩写），便于与元数据列（`character_id` / `name` / `path`）区分。

---

## 4. 数据流

### 4.1 数据源

| 数据 | 来源 | 格式 |
|------|------|------|
| 角色基础数据 | StarRailRes（Mar-7th/StarRailRes） | JSON，每个技能含 `desc` / `simple_desc` / `parameters` / `fandom` 数值 |
| 技能机制数值 | Fandom Wiki（honkai-star-rail.fandom.com） | 提取脚本：`pipeline/extract_fandom_skills.py` |
| sim_schema 文档 | `src/hsr_nous/sim_schema/docs/` | Markdown 按 `NN_topic.md` 编号（自 `00_overview.md` 起） |
| sim_schema 字段基线 | `src/hsr_nous/sim_schema/actor.py` + `validator.py` | Python dataclass |

### 4.2 处理流程

**试点轮（round1/round2，23 角色）流程**：

```
StarRailRes + Fandom + sim_schema 文档
        ↓
6 个 subagent 并行标注（每个负责 3-5 角色）
        ↓
raw/01~06_<角色>.json（6 个原始输出）
        ↓
merge_to_matrix.py
  - 合并 6 raw → 02_matrix.json
  - synonyms 字典归一化 primitive name
  - 构建 23 角色 × 168 原语矩阵（取最严重 schema_status）
        ↓
02_matrix.json / .csv / .md
        ↓
人工 review + 统计 + P0/P2 分类
        ↓
04_gap_analysis.md
```

**现行流程（全量轮起，工具链见同目录 `run_round.py`）**：

```
run_round.py todo（从游戏数据发现未扫角色）
        ↓
每角色一个标注 subagent（按 ANNOTATE_PROMPT.md）
        ↓
<本轮 raw>/<id>.json（列表格式，每角色一文件）
        ↓
run_round.py check（格式/id/白名单校验）→ status（对账）
        ↓
run_round.py diff（与上轮对比：红翻绿要有 schema 依据，绿翻红必须解释）
```

### 4.3 subagent 标注的 JSON schema

> 注：本节是试点轮的 dict 格式存档（merge_to_matrix.py 仅吃此格式）；**现行标注输出为列表记录格式，以 `ANNOTATE_PROMPT.md` 为准**。

```json
{
  "<character_id>": {
    "name": "<角色中文名>",
    "path": "<命途英文>",
    "element": "<属性英文>",
    "annotations": [
      {
        "skill_id": "<StarRailRes skill id>",
        "skill_name": "<技能中文名>",
        "skill_type": "<Normal|BPSkill|Ultra|Talent|Technique|Trace|Eidolon>",
        "primitives": [
          {
            "name": "<原语 snake_case>",
            "definition": "<一句话>",
            "evidence": "<desc 关键原文 / Fandom 数值>",
            "schema_status": "<green|yellow|red>",
            "schema_evidence": "<对应 sim_schema 文档位置>"
          }
        ]
      }
    ]
  }
}
```

### 4.4 merge_to_matrix.py 的关键步骤

1. 合并 6 raw → `02_matrix.json`（按 `character_id` 去重）
2. 归一化 primitive name → canonical key（`synonyms` 字典）
3. 构建矩阵 23 角色 × 168 原语，单元格 = 最严重 `schema_status`（red > yellow > green）
4. 输出 `02_matrix.json`（完整 evidence）/ `02_matrix.csv`（仅状态色）/ `02_matrix.md`（人类可读）

### 4.5 人工 review 关键统计

- 23 角色 × 168 原语 = 153 green + 117 yellow + 101 red = **371 原语实例**
- 红/黄比最高主题：欢愉/阿哈 100% > 场地/区域 100% > 限制/生存 94.7%
- 绿占比最低角色：风堇 6.7% > Silver Wolf LV.999 11.1% > Cyrene 13.6%
- 优先级分类：P0（≥2 角色跨用）+ P2（单角色特化）→ 写入 `04_gap_analysis.md`

---

## 5. 已知限制

### 5.1 缺失角色

**试点轮（23 角色）无缺失角色**（历史实录）。

**补盘示例**（增量补扫的标准做法——单独批次标注再合并入库）：试点轮后续通过补盘子任务（35+32=67 annotations、64+52=116 实例）补齐了缺失的 1501 火花 / 1502 爻光。两个角色合计引入 21 个红色实例，并把 `p_aha_instant_execution / p_gain_punchline / p_unlock_elation_skill` 三个欢愉系列原语的覆盖角色数从 3 推到 5，触发 1 个新的 P0 红色缺口（`p_add_stat`，从单角色 P2 升级到 2 角色 P0）。

### 5.2 归一化覆盖率

| 维度 | 数值 | 备注 |
|------|------|------|
| JSON 原始 primitive 实例 | 676 | 23 角色所有 subagent 标注 |
| JSON 唯一 primitive 名 | 373 | subagent 自创的细粒度原语 |
| CSV 归一化后唯一原语 | 168 | 约 205 个 JSON 独有被吸收，约 5 个 CSV 独有（subagent 较少触发但归一化保留） |
| CSV 单元格状态总数 | 371 | 153 green + 117 yellow + 101 red |

**未覆盖场景**：

- LLM 偶尔漏标（如 `BounceCount` 等次要原语）→ 归一化后仍为 168 之外的实际原语
- 同一原语的不同 subagent 命名差异极大（如 `apply_dmg_reduction_modifier` vs `apply_mitigation` vs `damage_taken_reduction`）→ 当前 synonyms map 不一定覆盖所有变体

### 5.3 LLM 标注的可靠性

| 风险 | 表现 | 缓解 |
|------|------|------|
| **非确定性** | 同 prompt 重跑结果可能不同 | 6 subagent 分片，单角色由 1 个 subagent 标注 → 暂未做交叉验证 |
| **漏标** | 复杂技能的多步效果可能少识别 1-2 个原语 | 人工 review（已发现部分 yellow/red 标错） |
| **错标** | subagent 可能将 `apply_modifier` 误标为 red（实际 schema 已有但 variant 缺） | 通过 02_matrix.json 的 `schema_evidence` 字段人工复核 |
| **schema 位置不准** | `schema_evidence` 写的章节可能不精确（如 `04_modifier.md §4.6` 应为 `04_modifier.md`） | 不影响 GAP 判定，仅影响补丁定位精度 |

**校验方法**：盘点过程中已用 `04_gap_analysis.md` §1.3 "绿占比最低 3 角色" + §2.1 "P0 红色原语" 反向核查，与 LLM 标注基本一致。

### 5.4 schema_status 判定的边界案例

| 案例 | subagent 判定 | 实际 | 处理 |
|------|---------------|------|------|
| `apply_modifier` 减伤 | 3 subagent 标 red，1 标 green | schema 缺 `mitigation` modifier_type，标 red 合理 | 已统一为 red |
| `transform_state` 形态切换 | 3 subagent 标 red（Cyrene/Silver Wolf LV.999），5 标 yellow | 状态机完全缺失，标 red 合理 | 已统一为 red |
| `consume_resource` 自定义资源 | 4 subagent 标 red，1 标 yellow | schema 仅支持标准资源，标 red 合理 | 已统一为 red |
| `immune_death` 矩阵保护 | 2 标 red，2 标 yellow | `matrix_save` vs `death_save` 边界模糊，schema 缺独立机制 | 已统一为 red |

**经验法则**：当 ≥2 个 subagent 标 red，即使其他标 yellow/red，也按 red 处理（保守策略，宁可误报为缺口）。

---

## 6. 如何扩展

### 6.1 补加新角色

**场景**：游戏版本更新出现新角色。

**现行步骤**：

1. **更新数据**：`hsr-data-update --lang cn`（fandom 机制页未建时，技能数值写 `params` 原话，不脑补）
2. **发现**：`python3 .agents/skills/mechanics-scan/run_round.py todo` 自动列出新角色
3. **标注**：按 `ANNOTATE_PROMPT.md` 派标注 subagent，产出 `<本轮 raw>/<id>.json`（列表格式）
4. **校验**：`run_round.py check`（error 必须清零）→ `status` 看状态分布
5. **登记**：在 `roster.yaml` 追加该角色

（试点轮的做法——§2.1 prompt + §4.2 dict 格式 + merge_to_matrix 追加矩阵行——仅在使用旧矩阵产物时参考。）

### 6.2 补加新原语

**场景**：新增 1 个原语到 sim_schema 后，需要在盘点中体现。

**步骤**：

1. **更新 sim_schema 文档**：在 `docs/05_effects.md` 增加 `effect_type: <new_primitive>`，在 `04_modifier.md` 完善 trigger 等
2. **更新 `actor.py` / `validator.py`**：如需新字段
3. **决定归一化**：
   - 若新原语是现有原语的**变体** → 在 `run_round.py` 的 `synonyms` 字典增加映射（归一化权威）
   - 若新原语是**新概念** → 作为独立 canonical key 保留
4. **验证红翻绿**：对受影响角色的标注重跑或人工改判后 `run_round.py diff <旧raw> <新raw>`——相关 red 应变 yellow/green；无变化说明 schema 改动没堵住缺口
5. **更新本文（`METHODOLOGY.md`）§3.3**：在主要归类表中增加新原语条目

### 6.3 重新盘点

**场景**：sim_schema 大改或 LLM 升级后，需重跑全流程。

**现行步骤**：

1. **开新轮次目录**：`reports/mechanics_scan/roundN/raw/`（不覆盖旧轮，便于 diff）
2. **全量标注**：`run_round.py todo` 列全量 → 按 `ANNOTATE_PROMPT.md` 派 swarm（全量约百个 subagent，token 量级 ~12M，开跑前知会 owner）
3. **校验对账**：`run_round.py check` → `status`
4. **跨轮对比**：`run_round.py diff <上轮raw> <本轮raw>`——红翻绿要有 schema 依据，绿翻红必须解释
5. **版本管理**：模板变更记在 `ANNOTATE_PROMPT.md` 顶部版本行

**耗时参考**：试点轮（23 角色 / 6 subagent）单人 1 工作日（含 2-4 小时人工 review）；全量轮（92 角色 / 约百个 subagent）标注机时约 1-2 小时 + ~12M token，人工 review 另计。

### 6.4 阶段 2 Prompt 集成

**未来工作**：当前盘点未做"阶段 2：标 schema 文档的全部原语"。`04_gap_analysis.md` 附录 B 提到这步的输出"应有清单"，但实际未执行。

集成方式：

1. 跑 §2.2 prompt → 得到 `sim_schema_primitives.json`（~60+ 标准 effect_type + 30+ trigger + 20+ action_type）
2. 与 `02_matrix.json` 对比：
   - JSON 出现但 schema 无 → 红色缺口（已有）
   - JSON 出现且 schema 有 → 按 schema_status（已有）
   - schema 有但 JSON 无 → 过度定义（新增维度）
3. 写入 `04_gap_analysis.md` 新增章节

---

## 附录 A：盘点参与角色与 subagent 分配

| Subagent | 角色 | 备注 |
|----------|------|------|
| 1 | 卡芙卡 / 银狼 / 希儿 / 景元 / 刃 | 经典体系（DoT / debuff / 额外回合 / 召唤 / tally） |
| 2 | 符玄 / 镜流 / 飞霄 / 花火 / 黑天鹅 | 矩阵保护 / 谱状态 / tally / 战技点 / Arcana |
| 3 | 黄泉 / 流萤 / 阿格莱雅 / 缇宝 / 万敌 | 积蓄终结技 / 击破转化 / 忆灵 / 数值膨胀 / 状态机 |
| 4 | Phainon / 风堇 / Cyrene | 形态切换 / 忆灵+tally / 忆灵+Zone+多资源 |
| 5 | 开拓者·欢愉 / Evanescia / Silver Wolf LV.999 | 欢愉机制（基础 / 2.0 / 终极形态） |
| 6 | 火花 / 爻光 | 欢愉机制（补盘：分散 / 弱点植入 / 直播连线 / 资源系统） |

完整角色 ID 映射与 23 命途/属性组合见试点轮产物 `02_matrix.csv` 与 `04_gap_analysis.md` 附录 C（本机 `reports/` 目录，新克隆不存在）。

## 附录 B：术语表

| 中文 | 英文（代码用） | 说明 |
|------|----------------|------|
| 原语 | primitive | 一行 effect_type 可表达的动作单元 |
| 效果类型 | effect_type | `docs/05_effects.md` |
| 修饰器 | modifier | `docs/04_modifier.md` |
| 触发时机 | trigger | `docs/04_modifier.md` §4.8 |
| 动作类型 | action_type | `docs/03_actor.md` |
| 归一化 | normalize | `run_round.py` 的 `synonyms` + `normalize_primitive_name` |
| 状态色 | schema_status | `green` / `yellow` / `red` |
| 主题 | topic | §1.3 表格 |
| 角色 / actor | character | 含 character / monster / summon |
| 命途 | path | 8 种（7 命途 + Elation） |
| 属性 | element | 7 种（physical / fire / ice / thunder / wind / quantum / imaginary） |
| 回合 / 轮次 / 波次 | turn / cycle / wave | `docs/00_overview.md` §1 |
| 阿哈时刻 / 好活当赏 / 笑点 / 增笑 | aha_moment / certified_banger / punchline / merrymake | 欢愉专属，详见 `04_gap_analysis.md` 附录 D |
| 忆灵 / tally / 隐藏 MMR | memosprite / tally / hidden_mmr | 3.x 引入的机制 |
