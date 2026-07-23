# Pipeline 数据管道

从社区维护的数据源加载《崩坏：星穹铁道》游戏数据。`pipeline/` **不 import 任何其他模块**（raw_schema、sim_schema、sim、agents、api），通过 `adapters/` 桥接。

## 模块结构

```
pipeline/
├── __init__.py                # 暴露核心加载接口
├── loader.py                  # 本地 JSON 加载 + 查询 + 计算辅助
├── update.py                  # 从 GitHub 拉取最新 StarRailRes 数据
├── extract_fandom_skills.py   # 从 Fandom wiki 提取技能机制 (回能/削韧/SP/嘲讽值加成)
├── extract_fandom_lightcones.py  # 从 Fandom wiki 提取角色 → 专光 映射
└── README.md
```

## 数据来源

### 1. StarRailRes（主数据源）

来源: [Mar-7th/StarRailRes](https://github.com/Mar-7th/StarRailRes)（上游 Dimbreath/StarRailData）

提供：角色基础信息、技能倍率、行迹、星魂、光锥、遗器等。
**不包含**削韧值、回能值、战技点消耗等机制数值。

数据文件存放于 `data/starrailres/index_new/{lang}/`：

| 文件 | 内容 |
|------|------|
| `characters.json` | 角色基础信息 |
| `character_skills.json` | 角色技能（含 params 倍率数组） |
| `character_skill_trees.json` | 行迹节点 |
| `character_promotions.json` | 角色晋阶与等级成长 |
| `character_ranks.json` | 星魂（6 魂/角色） |
| `light_cones.json` | 光锥基础信息 |
| `light_cone_promotions.json` | 光锥晋阶数据 |
| `light_cone_ranks.json` | 光锥叠影效果 (S1~S5 params) |
| `relic_sets.json` | 遗器套装（2pc / 4pc 描述在 `desc[0]` / `desc[1]`） |
| `relics.json` | 遗器基础信息 |
| `relic_main_affixes.json` | 遗器主词条数值 |
| `relic_sub_affixes.json` | 遗器副词条数值 |
| `properties.json` | 属性类型映射 (HealRatioBase → Outgoing Healing Boost) |
| `paths.json` | 命途映射 (Knight → Preservation) |
| `elements.json` | 元素映射 |

### 2. Fandom Wiki（机制数据 + 专光映射）

来源: [Honkai: Star Rail Wiki](https://honkai-star-rail.fandom.com)

提供 StarRailRes 中缺失的数据：

#### 2a. 技能机制（回能/削韧/SP）+ 嘲讽值加成

`extract_fandom_skills.py` 做两件事：

**技能数据**：从每个角色的 `{{Ability Infobox}}` 模板提取结构化数据，并根据模板 `#switch` 逻辑填充默认值（普攻回能 20/削韧 10、战技回能 30、终结技回能 5）。技能 key 用 **StarRailRes 技能 ID**（不是 Fandom 页面标题），通过 `match_skill_id()` 函数自动匹配（规则：精确名 → `(Blast)`/`(Single Target)` 后缀用 effect_text 消歧 → `/Enhanced` 对应加强版 `1` 前缀 → 行迹名全局匹配）。

**嘲讽值加成**：从 [Fandom - Aggro](https://honkai-star-rail.fandom.com/wiki/Aggro) 单页提取角色技能/行迹/光锥的嘲讽值百分比加成清单。

输出：`data/fandom_skill_data.json`
```json
{
  "1205": {"name": "Blade", "path": "Warrior", "skills": {"120502": {..., "fandom_page": "Hellscape"}, ...}},
  ...
  "_taunt_modifiers": [{"character_id": "1205", "modifier_pct": 1000, "source_id": "1120502", ...}, ...],
  "_taunt_base_modifiers": [{"character_id": "1209", "base_modifier_pct": -60, ...}]
}
```

#### 2b. 角色 → 专光 映射

`extract_fandom_lightcones.py` 从角色页面 `{{Character Infobox}}` 模板的 `|lightcone =` 字段提取，再通过 `loader.get_light_cone_by_name` 把名字映射到 StarRailRes ID。

输出两个文件：

- `data/fandom_meta/character_lightcones.json`（Fandom 原始 cache: `{char_name: lc_name | null}`，4★ 填 null）
- `data/signature_light_cones.json`（成品: `{char_id: {char_name_cn, char_name_en, lc_name_cn, lc_name_en, sig_lc_id}}`，只含 5★）

### 3. 敌人数据（theBowja）

来源: [theBowja/starrail-data](https://github.com/theBowja/starrail-data)

存放于 `data/enemies/enemies.json`。字段：`Id` / `Name` / `Introduction` / `ElementalWeaknesses` / `ElementalResistance` / `SkillList` / `VersionAdded`。

### 4. 派生数据

| 文件 | 生成方式 | 消费者 |
|------|----------|--------|
| `data/fandom_skill_data.json` | `extract_fandom_skills` | `adapters/`, `sim/` |
| `data/fandom_meta/character_lightcones.json` | `extract_fandom_lightcones`（cache） | 人审 |
| `data/signature_light_cones.json` | `extract_fandom_lightcones` | `query-game-data` skill, `adapters/` |

`data/` 整个目录是 gitignored 的——所有 derived data 跑一次脚本即可重生。

## Python API

### 加载

```python
from hsr_nous.pipeline import (
    load_characters, load_character_skills, load_character_skill_trees,
    load_character_ranks, load_light_cones, load_light_cone_ranks,
    load_relic_sets, load_relics, load_enemies,
    load_fandom_skill_data, load_signature_light_cones,
)

chars = load_characters()              # 整张表, 自动缓存
# {"1001": {"id": "1001", "name": "March 7th", "element": "Ice", "path": "Knight", ...}}
```

### 查询

```python
from hsr_nous.pipeline import (
    get_character, get_character_by_name, get_character_full,
    get_skill, get_skill_tree, get_skill_params, get_rank,
    get_light_cone, get_light_cone_by_name, get_light_cone_ranks,
    get_relic_set, get_relic_set_by_name, get_relic,
    get_enemy, get_enemy_by_name,
    list_characters, list_light_cones, list_relic_sets, list_enemies,
)

# 按 ID
march = get_character("1001")
# 按名称 (CN / EN, 单语言精确匹配)
march = get_character_by_name("March 7th", lang="en")

# 组装完整数据 (基础 + 技能 + 行迹 + 晋阶 + 星魂)
full = get_character_full("1001")
# full["skills_detail"] / "skill_trees_detail" / "promotion" / "ranks_detail"

# 技能 / 星魂 / 光锥叠影
skill = get_skill("100101")
print(skill["desc"])              # "Deals Ice DMG equal to #1[i]% of ..."
print(skill["params"][0])         # [0.5]  Lv.1 倍率
print(get_skill_params("100101", level=10))  # [1.4]

# 光锥叠影 (S1~S5 数值)
lc_ranks = get_light_cone_ranks("23042")
# {"skill": "...", "desc": "使装备者的速度提高#1[i]%...", "params": [[0.18, ...], ...], "properties": ...}
```

### 计算

```python
from hsr_nous.pipeline import calc_character_stats, calc_light_cone_stats

stats = calc_character_stats("1001", level=80)
# {"hp": 576.0, "atk": 278.4, "def": 312.0, "spd": 101, "crit_rate": 0.05, "crit_dmg": 0.5}
```

### 术语映射

```python
from hsr_nous.pipeline import get_path_name, get_element_name, get_property_name

print(get_path_name("Knight"))              # "Preservation"
print(get_element_name("Ice"))              # "Ice"
print(get_property_name("HealRatioBase"))   # "Outgoing Healing Boost"
```

### 敌人

```python
from hsr_nous.pipeline import load_enemies, get_enemy, get_enemy_by_name, list_enemies

enemy = get_enemy("1002011")
print(enemy["Name"])                  # "冰锋"
print(enemy["ElementalWeaknesses"])   # ["Fire", "Thunder"]
print(enemy["ElementalResistance"])   # {"Physical": 0.2, "Fire": 0, ...}

for eid, name in list_enemies()[:5]:
    print(f"{eid}: {name}")
```

### 远程加载（fallback）

本地文件缺失时直接从 GitHub 拉取：

```python
from hsr_nous.pipeline import fetch_from_github
chars = fetch_from_github("characters.json")
```

## CLI

### `hsr-data-update` —— 更新 StarRailRes + 敌人数据

```bash
# 更新英文数据 (默认)
hsr-data-update

# 更新简体中文
hsr-data-update --lang cn

# 下载敌人数据
hsr-data-update --enemies

# SSH 模式 (国内网络更快, 需配置 GitHub SSH key)
hsr-data-update --ssh
hsr-data-update --ssh --lang cn
hsr-data-update --ssh --enemies

# 自定义数据目录 / 限定文件 / 压缩索引
hsr-data-update --data-dir ./my_data
hsr-data-update --files characters.json,character_skills.json
hsr-data-update --index index_min
hsr-data-update --dry-run   # 只检查不写入
```

### `extract_fandom_skills` —— 抓 Fandom 技能机制 + 嘲讽值加成

```bash
# 全量（技能 + 嘲讽值，合并到 fandom_skill_data.json）
python -m hsr_nous.pipeline.extract_fandom_skills

# 只更新嘲讽值加成（秒完，不碰技能数据）
python -m hsr_nous.pipeline.extract_fandom_skills --only-taunt

# 补抓单个角色
python -m hsr_nous.pipeline.extract_fandom_skills --id 1224
# 输出: data/fandom_skill_data.json（技能 key = StarRailRes 技能 ID，嘲讽值在 _taunt_modifiers / _taunt_base_modifiers）
```

### `extract_fandom_lightcones` —— 抓 Fandom 角色 → 专光

```bash
# 全量 (Fandom 抓 + 名字→ID 映射)
python -m hsr_nous.pipeline.extract_fandom_lightcones

# StarRailRes 更新后重生成 mapping (复用 Fandom cache)
python -m hsr_nous.pipeline.extract_fandom_lightcones --skip-fandom

# 补抓单个角色
python -m hsr_nous.pipeline.extract_fandom_lightcones --id 1507
# 输出: data/fandom_meta/character_lightcones.json (cache)
#       data/signature_light_cones.json (成品)
```

## 下游消费者

- **`adapters/`**：通过 `from hsr_nous.pipeline import ...` 拿原始数据，转 sim_schema 格式
- **`.agents/skills/query-game-data/`**：纯路由层 CLI，**只调** `loader` 接口 + `load_signature_light_cones`（不自己读文件）。详见该 skill 的 SKILL.md

## 数据关联模型

StarRailRes 采用**分表 + ID 引用**：

```
characters.json              character_skills.json
    "1001"                       "100101"
    ├── skills: ["100101",       ├── name: "Frigid Cold Arrow"
    │            "100102",       ├── type_text: "Basic ATK"
    │            ...]            └── params: [[0.5], [0.6], ...]
    ├── skill_trees: [...]
    ├── ranks: [...]             character_skill_trees.json
    └── ...                          "1001001"
                                   ├── anchor: "Point01"
                                   ├── level_up_skills: [...]
                                   └── levels: [{properties: [...]}, ...]
```

`get_character_full()` 自动解析这些 ID 引用，把 `skills` / `skill_trees` / `ranks` 列表里的 ID 替换为完整对象（字段名加 `_detail` 后缀）。
