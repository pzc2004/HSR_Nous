---
name: query-game-rules
description: 查游戏机制规则 — 用 Read 工具读 docs/mechanics + docs/game_rules, WebFetch 兜底
---

# query-game-rules

查游戏机制规则（伤害公式 / 击破 / 战技点 / 行动序 / buff 叠加……）。

**核心原则：让 agent 自己读文档，用 LLM 智能匹配——不要写关键词搜索脚本**。
docs/mechanics 就 11 个文件 1446 行，agent 用 Read 全读消耗 token 极少，但能跨行跨段语义理解，
比任何关键词 grep/AND 匹配都准。

## 数据流（优先级从高到低）

1. **本地** `docs/mechanics/*.md` + `docs/game_rules.md` — 项目内化、模拟器"唯一事实来源"
2. **Fandom wiki** 角色专页 / 机制页 — 详细公式推导
3. **米游社** `bbs.mihoyo.com/sr/wiki` — 攻略 / 国服环境

## 何时使用

- 不确定某机制怎么算（例：增伤和独立增伤的区别、暴击期望公式、击破伤害公式）
- 查角色机制描述里某个"机制名词"的准确含义
- 设计 sim_schema 改动时核对"游戏规则"细节
- 写代码注释 / 文档时引用游戏规则

**不要用**：
- 查具体角色的 ID / 数值 / 名称 → 用 `query-game-data` skill
- 查角色技能的具体 params / 倍率 → 用 `query-game-data`
- 查 sim_schema 自身字段定义 → 读 `src/hsr_nous/sim_schema/docs/`

## 工作流

### 步骤 1：先读本地 docs/mechanics

按问题主题读对应文档（不需要全读，agent 自己判断）：

| 主题 | 文档 |
|------|------|
| 命途/属性/光锥/遗器/养成/基础属性总览 | `docs/mechanics/00_game_basics.md` |
| 角色/敌人属性、技能分类、记忆命途与忆灵 | `docs/mechanics/01_base_stats.md` |
| 伤害公式、乘区、暴击期望、真实伤害 | `docs/mechanics/02_damage_formula.md` |
| 回合/轮次/波次、行动值、拉条推条、速度、额外回合 | `docs/mechanics/03_action_sequence.md` |
| 韧性削减、弱点击破、击破伤害、超击破 | `docs/mechanics/04_break_system.md` |
| 终结技能量、能量恢复效率 | `docs/mechanics/05_energy_system.md` |
| 战技点 / 秘技点获取消耗 | `docs/mechanics/06_skill_points.md` |
| Buff / Debuff 叠加、效果命中、属性二次转化 | `docs/mechanics/07_buff_system.md` |
| 欢愉命途机制 | `docs/mechanics/08_elation_system.md` |
| 追加攻击触发条件 | `docs/mechanics/09_follow_up_attacks.md` |
| 嘲讽值、被攻击目标选择 | `docs/mechanics/10_taunt_system.md` |
| 特殊机制（专属效果、结界/境界/连携攻击、HP 事件区分） | `docs/mechanics/11_special_mechanics.md` |
| 秘技系统（秘技点、分类、战前策略） | `docs/mechanics/12_technique_system.md` |

跨主题的"是什么"问题先读 `docs/game_rules.md`（综合总纲）。

### 步骤 2：本地没找到 → WebFetch Fandom

```
WebFetch(url="https://honkai-star-rail.fandom.com/wiki/<角色名>", prompt="<要查的机制>")
```

常用入口：
- 角色专页：`<角色名>` 找机制描述
- 机制术语：`Memosprite` / `Energy` / `Toughness` / `Break Effect` 等

### 步骤 3：Fandom 也没找到 → WebFetch 米游社

```
WebFetch(url="https://bbs.mihoyo.com/sr/wiki/search?keyword=<关键词>", prompt="...")
```

米游社无公开 API，agent 用 WebFetch 解读 HTML。可能需要多次试不同关键词。

## 重要规则

1. **本地优先** —— 本地文档是模拟器"唯一事实来源"，与 sim_schema 实现一致。Fandom / 米游社是参考，可能与实现有差异
2. **本地命中后不一定要走远程** —— agent 自己判断信息是否够用
3. **远程结果与本地矛盾时**，**以本地为准**（它是设计实现），但要在 PR 讨论里同步修订本地
4. **不要写关键词 grep 脚本** —— docs/mechanics 量小，agent 读全文 + LLM 理解是最高效的

## 维护

- 加新机制文档 → 在 `docs/mechanics/` 加 `NN_xxx.md`，并把新文档主题加入本 SKILL.md 表格
- 改工作流 / 数据源 → 改本文档

## 已知限制

- 本地文档依赖人工维护 —— 新机制出了未及时补文档时，本地搜不到
- 米游社需要登录的页面 agent 抓不到
- WebFetch 单次只能拿一个 URL，需要多源对比时多次调用
