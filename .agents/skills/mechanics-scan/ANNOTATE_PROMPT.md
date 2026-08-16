# 机制标注 prompt 模板（机制扫描·标注引擎专用）

> 版本：v2（删 set_hp_to_percent 伪原语、机制粒度命名规范、新旧技能组以最新版为准）
> 用途：把一个角色的全部机制标注为"原语清单"。每个标注 subagent 拿到一个角色（id + 中文名 + 本轮 raw 目录），产出 `<本轮 raw 目录>/<id>.json`。
> 原则：**逐技能拆机制、每条给出处、定级看框架而非实现**。

## 输入（全部本地取数，禁止脑补数值/文本）

```bash
python3 .agents/skills/query-game-data/query.py character <中文名>
```

返回该角色全部技能/终结技/天赋/秘技/星魂/行迹的中英文文本与参数。机制判断以**技能文本**为准；数值不确定就写 `params` 原话，不要自己编。

## schema 原语参照（定级的依据）

- effect 原语：`src/hsr_nous/sim_schema/docs/05_effects.md`（deal_damage/heal/drain_hp/gain_energy/advance_action/immediate_action/delay_action/grant_extra_turn/apply_modifier/remove_modifier/summon/deploy_zone/consume_resource/gain_resource/trigger_dot/enter_state/override_action_param 等）
- modifier trigger 清单：`src/hsr_nous/sim_schema/docs/04_modifier.md` §4.8（含复合触发名=语法糖）
- 总线事件：`src/hsr_nous/sim_schema/docs/23_event_hook_system.md` §23.4
- 其余机制件：`12_summon.md`（召唤物/忆灵）、`16_custom_resources.md`（自定义资源计数器）、`17_actor_state.md`（形态状态机）、`19_zone_system.md`（结界）、`18_technique_system.md`（秘技）、`04_modifier.md` §4.2（flat_bonus/scaling_from_source/override）、§4.3（转化维度标签）

## 输出格式（严格）

写到主 agent 指定的本轮 raw 目录（如 `reports/mechanics_scan/roundN/raw/`）下的 `<id>.json`，JSON **数组**，每项一个原语：

```json
[
  {
    "character_id": "1005",
    "skill_id": "100502",
    "primitive": "deal_damage",
    "status": "green",
    "schema_evidence": "05_effects.md §5.2 deal_damage",
    "rationale": "战技对单体造成雷伤，标准直伤"
  }
]
```

- `skill_id`：技能/星魂/行迹的数据 id（星魂用 ranks id、行迹用 skill_trees id）
- `primitive`：**机制粒度名**（snake_case），按"这个机制是什么"命名——如 `trigger_existing_dot`（引爆已有 DOT）、`apply_dot_with_chance`（概率挂 DOT）、`deal_damage_blast`（扩散伤害）、`deal_toughness_damage`（削韧）、`per_turn_trigger_limit`（每回合限次）。**不要只写 schema 的 effect_type**（deal_damage/apply_modifier 太粗，丢失缺口信息）；定级时再去 schema 找它的表达路径。merge 阶段会做同义名归一，不怕名字新
- `status` 定级（**看框架能否表达，不看当前是否已实现**）：
  - `green`：schema 有直接原语/字段表达（必须给 `schema_evidence` 文档出处）
  - `yellow`：无直接原语但可组合表达（事件+condition 过滤 / 自定义资源计数器 / 状态机 / 语法糖），或能近似但有明确语义差（在 rationale 写清差在哪）
  - `red`：当前框架表达不了（缺原语/缺概念，rationale 写清缺什么）
- `rationale`：一句中文，含关键文本依据（引原文短语）

## 覆盖要求

- 每个含机制的技能/星魂/行迹至少 1 条；纯伤害可以只写 1 条 `deal_damage`
- 一条技能含多个机制就拆多条（如"消耗生命+扩散伤害+强化普攻"= 3 条）
- 禁漏：被动/星魂/行迹里的触发类效果（"当…时"、"每…时"）都要单独成条
- 不写无机制的词（纯叙事文本、纯升级节点、纯属性行迹节点不写）
- **新旧技能组并存时**（如 `1205xx` 旧版 vs `1120xx` 加强版、或 `1005xx` vs `11005xx`）：以**最新版**为准全量标注；旧版整组跳过，仅当某机制**只存在于旧版**时补 1 条并在 rationale 注明"旧版遗留"
