---
name: query-game-data
description: 查角色/光锥/遗器/敌人的机制、数值、中英文名 (实时合并 StarRailRes + Fandom + 专光映射)
---

# query-game-data

查游戏数据（角色/光锥/遗器/敌人）—— 实时从本地 StarRailRes + Fandom 抓取的数据合集。

## 何时使用

- 需要查某角色的 ID、技能 ID、星魂 ID、专光 ID（不附带专光机制）
- 需要查某光锥的描述、S1~S5 params、叠影参数
- 需要查某遗器套装的 2pc/4pc 效果、包含的部件
- 需要查某敌人的弱点/抗性/技能
- 需要角色/光锥的中英对照名
- 实施 sim_schema 改动前要核对"游戏实际机制"时

**不要用**：
- 查机制效果数值（伤害公式/削韧/回能等）—— 那是 `docs/mechanics/` 的事
- 查 sim_schema 自身的字段定义 —— 那是 `src/hsr_nous/sim_schema/docs/` 的事
- 修改任何数据文件 —— 只读

## 调用

```bash
python3 .claude/skills/query-game-data/query.py <entity_type> <query>
```

### entity_type

| 值 | 含义 | 返回 |
|---|---|---|
| `character` | 角色 | 角色完整数据 + `signature_light_cone_id` |
| `light_cone` | 光锥 | 光锥数据 + `params_by_superimposition` (S1~S5) |
| `relic` | 遗器套装 | set_2pc/set_4pc + relic_ids |
| `enemy` | 敌人 | 弱点/抗性/技能列表 |
| `list <kind>` | 列出所有 | `<kind>` $\in$ {characters, light_cones, relic_sets, enemies} |

### query

- 数字 ID (如 `1005`)：按 ID 精确查
- 名字：CN/EN 都支持，大小写不敏感，**精确匹配**（不要模糊）

## 数据源

| 数据 | 来源 |
|---|---|
| 角色/光锥/遗器基础 | `data/starrailres/index_new/{cn,en}/*.json` (Mar-7th/StarRailRes) |
| 角色 → 专光映射 | `data/signature_light_cones.json` (Fandom 抓的, 脚本: `extract_fandom_lightcones.py`) |
| 专光机制数值 | `data/starrailres/index_new/cn/light_cone_ranks.json` |
| 敌人 | `data/enemies/enemies.json` (theBowja/starrail-data) |

## 重要规则

1. **角色查询附带 `signature_light_cone_id`，但不附带专光机制** —— 要查专光机制请单独 `light_cone <sig_lc_id>`
2. **光锥查询不返回角色 ID** —— 反向查询请查角色
3. **查不到时** 返回 `{"_error": ..., "_hint": "try `list ...`"}` —— 但**先怀疑数据源过时**而不是怀疑 skill；见下方"数据缺失处理"
4. **真实数据是底线** —— 如果返回的数据看起来不对（比如 S5 的伤害值显然偏低），停下来怀疑数据源，**不要脑补**
5. **5★ 角色查无专光** 会返回 `_warning` —— 通常是 signature_light_cones.json 缺失/过时；先跑 `extract_fandom_lightcones --skip-fandom` 重生成

## 数据缺失处理

**优先级：先更新数据 → 还查不到才报不存在**。

| 查不到什么 | 第一步 | 第二步 |
|---|---|---|
| 角色/光锥/遗器基础数据 | `hsr-data-update --lang cn && hsr-data-update --lang en` | 重跑 `python3 .claude/skills/query-game-data/query.py` |
| 5★ 角色无专光（`_warning`） | `python3 -m hsr_nous.pipeline.extract_fandom_lightcones --skip-fandom` | `--id <char_id>` 补抓 Fandom |
| 技能机制（回能/削韧/SP） | `python3 -m hsr_nous.pipeline.extract_fandom_skills` | `--id <char_id>` 补抓单角色 |
| 敌人 | `hsr-data-update --enemies` | — |

更新后仍查不到，再报"不存在"并附 `_hint`。

## 预期限制（非数据缺失）

- **4★ 角色** 没有 5★ 专光（by design，不在 `signature_light_cones.json`）
- **开拓者** 没有 5★ 专光（跟 4★ 角色一样）；Fandom 上所有命途页面 lightcone 字段均为空
- **命途/属性/稀有度** 只返回英文枚举（如 `path: Warlock`），中英对照查 `terminology.yaml`

## 示例

```bash
# 卡芙卡的 ID、专光 ID、技能 ID 列表
python3 .claude/skills/query-game-data/query.py character 1005

# 风堇（按中文名）
python3 .claude/skills/query-game-data/query.py character 风堇

# 愿虹光永驻天空（S1~S5 叠影数值）
python3 .claude/skills/query-game-data/query.py light_cone 23042

# 风套遗器 4pc 效果
python3 .claude/skills/query-game-data/query.py relic 102

# 冰锋弱点
python3 .claude/skills/query-game-data/query.py enemy 1002011

# 列出所有光锥
python3 .claude/skills/query-game-data/query.py list light_cones
```

## 输出格式

JSON（stdout），UTF-8，中英字段名同存，2 空格缩进：
- `id`: 数字 ID 永远是字符串
- `name_cn` / `name_en`: 中英名
- `signature_light_cone_id`: 专光 ID（仅 character）
- `params_by_superimposition`: 5 个元素的二维数组（仅 light_cone），S1 在前

## 维护

- 改脚本逻辑：`.claude/skills/query-game-data/query.py`
- 改数据源说明：本文档
- 加新 entity_type：在 query.py 加新函数 + 在本文档加 entity_type 表
