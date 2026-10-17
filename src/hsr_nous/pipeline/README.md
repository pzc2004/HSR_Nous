# Pipeline 数据管道

从社区维护的数据源加载《崩坏：星穹铁道》游戏数据。`pipeline/` **不 import 任何业务模块**（sim_schema、sim、agents、api；仅可 import 公共基座 `common`），通过 `adapters/` 桥接。

## 模块结构

```
pipeline/
├── __init__.py                # 暴露核心加载接口
├── paths.py                   # 数据域路径（公共根由 common/paths 转出；HSR_NOUS_DATA_DIR > 仓库 ./data）
├── build/                     # ① 配装域（角色/光锥/遗器——build.yaml 输入数据）
│   ├── loader.py                # StarRailRes JSON 加载 + 查询 + 计算辅助（表驱动 load_entity）
│   ├── update.py                # StarRailRes 下载（hsr-data-update 默认/--lang 真身）
│   └── semantic.py              # 角色语义补充（Fandom 技能机制数值 + 专光映射 合并件）
├── enemies/                   # ② 敌人域（turnbasedgamedata 五表为数值权威）
│   ├── update.py                # tbgd 五表下载（GitLab raw + 红线对齐校验，--enemies-tbgd 真身）
│   ├── loader.py                # tbgd 口径统一查询（面板/弱点/抗性/技能倍率削韧/AI——
│   │                            #   与 hakushin 链全量对拍见 tests/test_enemy_source_parity.py）
│   └── semantic.py              # 敌人语义补充（Fandom 机制描述文本——语义补充非数值权威）
├── stages/                    # ③ 期数域（深渊/虚构/末日/异相仲裁）
│   ├── update.py                # 期数下载（Hakushin + buhflipexplode + 红线过滤）
│   └── loader.py                # 关卡/敌人统一查询接口（双源差异屏蔽 + 面板公式链）
├── loader.py                  # 【兼容壳】→ build/loader.py（旧 import 路径保留）
├── stages_loader.py           # 【兼容壳】→ stages/loader.py（旧 import 路径保留）
├── update_stages.py           # 【兼容壳】→ stages/update.py（旧 import 路径保留）
├── extract_fandom_enemies.py  # 【兼容壳】→ enemies/semantic.py（旧 import 路径保留）
├── update.py                  # hsr-data-update 统一入口（路由壳，按域分发）
├── redline.py                 # 红线过滤纯函数（未发布内容剔除，全部数据源共用）
├── extract_miyoushe_skills.py # 【已归档·停爬】米游社 WIKI 角色技能机制提取（保留不删，不再运行）
├── extract_tbgd_skills.py     # tbgd 角色技能机制数值提取（crosscheck 对轴用）
└── README.md
```

> 三域归置：`build/`（配装，P1）、`enemies/`（敌人，P2）、`stages/`（期数，P1）
> 已落地；P3 已切源——敌人**数值权威 = turnbasedgamedata 五表**（消费方全切
> `enemies/loader.py`，对拍闸 `tests/test_enemy_source_parity.py` 全绿），
> theBowja/monstervalue **冻结保留**（停更留回退），Fandom 降语义补充。

## 数据目录

全项目路径唯一事实源 = `common/paths.py`（缺省 = 仓库 `./data`；环境变量
`HSR_NOUS_DATA_DIR` 可整体指向别处——CI/多份数据并存/自定义位置）。本模块
`paths.py` 转出公共根（`repo_root`/`data_root`/`repo_data_dir`）并保留数据域专有路径
（starrailres/stages/... 与 library/battles 内容根）。注意两类数据命运不同：
`data/library`、`data/battles` 是 git 追踪的仓库内容，**不随** `HSR_NOUS_DATA_DIR` 移动；
其余 gitignored 下载物/生成物才会跟随。调用方一律调 `paths.*()` 函数，不写路径常量。

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

`build/semantic.py`（skills 子命令）做两件事：

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

`build/semantic.py`（lightcones 子命令）从角色页面 `{{Character Infobox}}` 模板的 `|lightcone =` 字段提取，再通过 `loader.get_light_cone_by_name` 把名字映射到 StarRailRes ID。

输出两个文件：

- `data/fandom_meta/character_lightcones.json`（Fandom 原始 cache: `{char_name: lc_name | null}`，4★ 填 null）
- `data/signature_light_cones.json`（成品: `{char_id: {char_name_cn, char_name_en, lc_name_cn, lc_name_en, sig_lc_id}}`，只含 5★）

### 3. 米游社 WIKI（官方开拓者笔记）【已归档·停爬】

来源: [米游社·崩坏：星穹铁道 WIKI](https://bbs.mihoyo.com/sr/wiki/)（开拓者笔记）

`extract_miyoushe_skills.py` 从官方静态 CDN 接口（`act-api-takumi-static`，裸 GET 无鉴权）提取角色行迹树：每技能 `subTag` 结构化标签（`["单攻","削韧值10","回能 20","战技点 +1"]`）。

> ⚠️ **已归档（2026-10）**：subTag 是社区维护口径，标签写法不统一、质量参差，在三方对轴中只作辅助校验列且会产误报噪音；战技点等数值以 turnbasedgamedata 为权威源已足够。脚本冻结保留不删、不再运行更新；存量 `data/miyoushe_skill_data.json` 仍在本地，crosscheck 节点已改为可选读取（缺失自动跳过米游社列）。

输出：`data/miyoushe_skill_data.json`（key = StarRailRes 角色 ID，来自行迹树 `roleId`）

> ⚠️ 敌人频道（敌对物种）只有弱点/抗性/介绍，**无技能/行动表**——敌人数据不走此源。

### 4. 敌人数据（theBowja）【冻结保留】

来源: [theBowja/starrail-data](https://github.com/theBowja/starrail-data)

存放于 `data/enemies/enemies.json`。字段：`Id` / `Name` / `Introduction` / `ElementalWeaknesses` / `ElementalResistance` / `SkillList` / `VersionAdded`。

> ⚠️ **断更于 3.2 且已冻结**：上游 DimBreath/StarRailData 2024-10 被 DMCA 下架；P3 切源后**数值权威为 turnbasedgamedata 五表**（`enemies/loader.py`，对拍见 `tests/test_enemy_source_parity.py`），本文件**冻结保留**——停更但保留可读作回退（`get_enemy_detail` 回退链 `_stale` 标记）。同冻结：`data/stages/hakushin/monstervalue.json`（与 tbgd 全等，留作回退/对拍参照）。

### 5. 关卡编成数据（stages，两源互补）

| 内容 | 来源 | 本地路径 |
|------|------|----------|
| 关卡配置（期数/波次/等级/系数） | [Hakushin API](https://static.nanoka.cc)（hakush.in 数据后端） | `data/stages/hakushin/` |
| 含异相仲裁的编成与期数时间 | [buhflipexplode-src](https://github.com/spiritfxxxx/buhflipexplode-src) | `data/stages/buhflipexplode/` |

下载：`hsr-data-update --stages`。**所有期数数据落盘前过红线过滤**（`pipeline/redline.py`：未上线期数/占位期/未引用实体一律剔除）。

### 6. 派生数据

| 文件 | 生成方式 | 消费者 |
|------|----------|--------|
| `data/fandom_skill_data.json` | `build/semantic.py skills` | `adapters/`, `sim/` |
| `data/miyoushe_skill_data.json` | `extract_miyoushe_skills`（已归档·停爬） | `ops/annotator`（crosscheck 可选校验列） |
| `data/fandom_enemy_data.json` | `enemies/semantic.py`（语义补充，数值权威为 tbgd 五表） | `adapters/`, `sim/` |
| `data/fandom_meta/character_lightcones.json` | `build/semantic.py lightcones`（cache） | 人审 |
| `data/signature_light_cones.json` | `build/semantic.py lightcones` | `query-game-data` skill, `adapters/` |
| `data/stages/` | `hsr-data-update --stages` | `stages_loader`, `adapters/` |

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

## CLI

### `hsr-data` —— 统一数据入口（推荐）

```bash
# 全量更新（缺省三域全跑：StarRailRes 中英 + tbgd 敌人五件 + theBowja 冻结备料
# + Hakushin/buh 期数 + 机制数值 + Fandom 语义）——零 flag 记忆
hsr-data update

# 增量更新（远端 ETag 快检只下变化；Fandom 爬虫默认跳过，--with-fandom 才跑）
hsr-data update --incr

# 单域（build=配装 / enemies=敌人 / stages=期数）
hsr-data update enemies

# 状态报告（本地版本 / 远端可更新 / 红线滤除——不写入）
hsr-data check
hsr-data check stages

# 全局参数：--ssh（git sparse-checkout 替代 HTTPS）/ --dry-run / --data-dir / --timeout / --lang
hsr-data update --ssh --dry-run
```

### `hsr-data-update` —— 旧命令（过渡别名，一个版本后退役）

```bash
hsr-data-update            # = hsr-data update build --lang en
hsr-data-update --lang cn
hsr-data-update --enemies  # theBowja 冻结备料
hsr-data-update --enemies-tbgd  # = hsr-data update enemies 的 tbgd 五件段
hsr-data-update --stages   # = hsr-data update stages
hsr-data-update --mechanics  # tbgd 技能机制提取（build 域段）
```

### `build/semantic.py skills` —— 抓 Fandom 技能机制 + 嘲讽值加成

```bash
# 全量（技能 + 嘲讽值，合并到 fandom_skill_data.json）
python -m hsr_nous.pipeline.build.semantic skills

# 只更新嘲讽值加成（秒完，不碰技能数据）
python -m hsr_nous.pipeline.build.semantic skills --only-taunt

# 补抓单个角色
python -m hsr_nous.pipeline.build.semantic skills --id 1224
# 输出: data/fandom_skill_data.json（技能 key = StarRailRes 技能 ID，嘲讽值在 _taunt_modifiers / _taunt_base_modifiers）
```

### `build/semantic.py lightcones` —— 抓 Fandom 角色 → 专光

```bash
# 全量 (Fandom 抓 + 名字→ID 映射)
python -m hsr_nous.pipeline.build.semantic lightcones

# StarRailRes 更新后重生成 mapping (复用 Fandom cache)
python -m hsr_nous.pipeline.build.semantic lightcones --skip-fandom

# 补抓单个角色
python -m hsr_nous.pipeline.build.semantic lightcones --id 1507
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
