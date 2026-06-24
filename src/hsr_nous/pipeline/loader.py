"""StarRailRes 数据加载器.

从本地缓存或远程 GitHub 加载 Mar-7th/StarRailRes 的索引数据.
所有数据文件以 dict 形式组织，key 为字符串 ID.
"""

import json
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "starrailres"
_DEFAULT_LANG = "en"
_DEFAULT_INDEX = "index_new"

_GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/Mar-7th/StarRailRes/main/{index}/{lang}/{filename}"
)

# 需要加载的核心数据文件列表
CORE_FILES = [
    "characters.json",
    "character_skills.json",
    "character_skill_trees.json",
    "character_promotions.json",
    "character_ranks.json",
    "light_cones.json",
    "light_cone_promotions.json",
    "light_cone_ranks.json",
    "relic_sets.json",
    "relics.json",
    "relic_main_affixes.json",
    "relic_sub_affixes.json",
    "properties.json",
    "paths.json",
    "elements.json",
]

# ---------------------------------------------------------------------------
# 路径解析
# ---------------------------------------------------------------------------


def _resolve_data_dir(data_dir: Optional[str]) -> Path:
    if data_dir is None:
        return _DEFAULT_DATA_DIR
    return Path(data_dir)


def _resolve_lang(lang: Optional[str]) -> str:
    return lang or _DEFAULT_LANG


def _resolve_index(index: Optional[str]) -> str:
    return index or _DEFAULT_INDEX


def _file_path(
    filename: str,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
    index: Optional[str] = None,
) -> Path:
    return (
        _resolve_data_dir(data_dir)
        / _resolve_index(index)
        / _resolve_lang(lang)
        / filename
    )


# ---------------------------------------------------------------------------
# 核心加载函数
# ---------------------------------------------------------------------------


def load_json(
    filename: str,
    *,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
    index: Optional[str] = None,
) -> Dict[str, Any]:
    """加载指定 JSON 文件.

    Args:
        filename: JSON 文件名，如 "characters.json"
        data_dir: 自定义数据目录
        lang: 语言代码，默认 "en"
        index: 索引目录，默认 "index_new"

    Returns:
        以 ID 为 key 的字典
    """
    path = _file_path(filename, data_dir=data_dir, lang=lang, index=index)
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def _load_cached(
    filename: str,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
    index: Optional[str] = None,
) -> Dict[str, Any]:
    """带缓存的加载（内部使用）."""
    return load_json(filename, data_dir=data_dir, lang=lang, index=index)


def load_characters(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("characters.json", data_dir=data_dir, lang=lang)


def load_character_skills(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("character_skills.json", data_dir=data_dir, lang=lang)


def load_character_skill_trees(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("character_skill_trees.json", data_dir=data_dir, lang=lang)


def load_character_promotions(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("character_promotions.json", data_dir=data_dir, lang=lang)


def load_character_ranks(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("character_ranks.json", data_dir=data_dir, lang=lang)


def load_light_cones(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("light_cones.json", data_dir=data_dir, lang=lang)


def load_light_cone_promotions(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("light_cone_promotions.json", data_dir=data_dir, lang=lang)


def load_relic_sets(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("relic_sets.json", data_dir=data_dir, lang=lang)


def load_relics(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("relics.json", data_dir=data_dir, lang=lang)


def load_relic_main_affixes(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("relic_main_affixes.json", data_dir=data_dir, lang=lang)


def load_relic_sub_affixes(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("relic_sub_affixes.json", data_dir=data_dir, lang=lang)


def load_properties(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("properties.json", data_dir=data_dir, lang=lang)


def load_paths(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("paths.json", data_dir=data_dir, lang=lang)


def load_elements(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    return _load_cached("elements.json", data_dir=data_dir, lang=lang)


# ---------------------------------------------------------------------------
# Fandom wiki 机制数据
# ---------------------------------------------------------------------------


def load_fandom_skill_data(
    *, data_dir: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """加载 Fandom wiki 提取的技能机制数据.

    返回格式: {character_id: {name, path, skills: {page_title: {type, energy_cost, ...}}}}
    """
    root = _resolve_data_dir(data_dir).parent  # data/
    path = root / "fandom_skill_data.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_character_skills_merged(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Dict[str, Any]:
    """加载角色技能并合并 Fandom 机制数据.

    StarRailRes 提供: id, name, element, type, effect, params 等
    Fandom 补充: energy_cost, energy_gen, toughness_dmg, sp_cost, sp_gain, enhanced

    返回格式与 load_character_skills() 相同，但每个技能多了机制字段。
    """
    skills = load_character_skills(data_dir=data_dir, lang=lang)
    fandom = load_fandom_skill_data(data_dir=data_dir)
    if not fandom:
        return skills

    # 构建 character_id → Fandom skills 的映射
    # Fandom 数据按角色分组，技能用 page_title 做 key
    # 需要反向查找：skill_id → character_id
    characters = load_characters(data_dir=data_dir, lang=lang)
    char_skill_map: Dict[str, str] = {}  # skill_id → character_id
    for cid, char in characters.items():
        for sid in char.get("skills", []):
            char_skill_map[sid] = cid

    # Fandom type → StarRailRes type 映射
    _TYPE_MAP = {
        "Basic ATK": "Normal",
        "Skill": "BPSkill",
        "Ultimate": "Ultra",
        "Talent": "Talent",
        "Technique": "Maze",
    }

    # 合并 Fandom 数据到 StarRailRes 技能
    merged = dict(skills)
    for cid, fdata in fandom.items():
        fskills = fdata.get("skills", {})
        # 按 type 分组 Fandom 技能，处理强化版
        by_type: Dict[str, list] = {}
        for page_title, finfo in fskills.items():
            fandom_type = finfo.get("type", "")
            sr_type = _TYPE_MAP.get(fandom_type)
            if not sr_type:
                continue
            by_type.setdefault(sr_type, []).append(finfo)

        # 找到该角色的所有 StarRailRes 技能
        char_sids = [sid for sid, c in char_skill_map.items() if c == cid]

        for sr_type, finfo_list in by_type.items():
            # 找到匹配的 StarRailRes skill
            matching_sids = [
                sid for sid in char_sids
                if skills.get(sid, {}).get("type") == sr_type
            ]
            if not matching_sids:
                continue

            # 按 Fandom 的 enhanced 标记匹配
            # 非强化版匹配普通 skill_id，强化版匹配 1 开头的 ID
            for finfo in finfo_list:
                is_enhanced = finfo.get("enhanced", False)
                target_sid = None
                for sid in matching_sids:
                    sid_is_enhanced = sid.startswith("1") and len(sid) > 5 and sid[0] == "1"
                    if is_enhanced == sid_is_enhanced:
                        target_sid = sid
                        break
                if not target_sid:
                    # fallback: 取第一个未匹配的
                    for sid in matching_sids:
                        if sid not in [finfo.get("_matched_sid") for finfo in finfo_list]:
                            target_sid = sid
                            break
                if not target_sid:
                    target_sid = matching_sids[0]

                # 合并机制字段
                skill_copy = dict(merged.get(target_sid, skills.get(target_sid, {})))
                for key in ("energy_cost", "energy_gen", "toughness_dmg", "sp_cost", "sp_gain", "enhanced"):
                    val = finfo.get(key)
                    if val is not None and val != "":
                        if key in ("energy_cost", "energy_gen", "toughness_dmg", "sp_cost", "sp_gain"):
                            try:
                                skill_copy[key] = int(val)
                            except (ValueError, TypeError):
                                skill_copy[key] = val
                        else:
                            skill_copy[key] = val
                merged[target_sid] = skill_copy

    return merged


# ---------------------------------------------------------------------------
# 便捷查询接口
# ---------------------------------------------------------------------------


def get_character(
    char_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询角色基础信息."""
    return load_characters(data_dir=data_dir, lang=lang).get(char_id)


def get_character_by_name(
    name: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按名称查询角色（遍历搜索）."""
    for char in load_characters(data_dir=data_dir, lang=lang).values():
        if char.get("name") == name:
            return char
    return None


def get_skill(
    skill_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询技能."""
    return load_character_skills(data_dir=data_dir, lang=lang).get(skill_id)


def get_skill_tree(
    tree_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询行迹节点."""
    return load_character_skill_trees(data_dir=data_dir, lang=lang).get(tree_id)


def get_promotion(
    char_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按角色 ID 查询晋阶数据."""
    return load_character_promotions(data_dir=data_dir, lang=lang).get(char_id)


def get_rank(
    rank_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询星魂."""
    return load_character_ranks(data_dir=data_dir, lang=lang).get(rank_id)


def get_light_cone(
    lc_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询光锥."""
    return load_light_cones(data_dir=data_dir, lang=lang).get(lc_id)


def get_light_cone_by_name(
    name: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按名称查询光锥（遍历搜索）."""
    for lc in load_light_cones(data_dir=data_dir, lang=lang).values():
        if lc.get("name") == name:
            return lc
    return None


def get_relic_set(
    set_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询遗器套装."""
    return load_relic_sets(data_dir=data_dir, lang=lang).get(set_id)


def get_relic(
    relic_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询遗器."""
    return load_relics(data_dir=data_dir, lang=lang).get(relic_id)


def list_characters(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> List[Tuple[str, str]]:
    """返回所有角色 (id, name) 列表."""
    return [
        (char_id, info.get("name", ""))
        for char_id, info in load_characters(data_dir=data_dir, lang=lang).items()
    ]


def list_light_cones(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> List[Tuple[str, str]]:
    """返回所有光锥 (id, name) 列表."""
    return [
        (lc_id, info.get("name", ""))
        for lc_id, info in load_light_cones(data_dir=data_dir, lang=lang).items()
    ]


def list_relic_sets(
    *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> List[Tuple[str, str]]:
    """返回所有遗器套装 (id, name) 列表."""
    return [
        (set_id, info.get("name", ""))
        for set_id, info in load_relic_sets(data_dir=data_dir, lang=lang).items()
    ]


# ---------------------------------------------------------------------------
# 完整角色数据组装
# ---------------------------------------------------------------------------


def get_character_full(
    char_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """组装角色的完整数据（基础信息 + 技能 + 行迹 + 晋阶 + 星魂）.

    返回结构:
        {
            "id": "1001",
            "name": "March 7th",
            ... (characters.json 中的基础字段)
            "skills_detail": [skill_obj, ...],      # 从 character_skills.json 解析
            "skill_trees_detail": [tree_obj, ...],  # 从 character_skill_trees.json 解析
            "promotion": promotion_obj,             # 从 character_promotions.json 解析
            "ranks_detail": [rank_obj, ...],        # 从 character_ranks.json 解析
        }
    """
    char = get_character(char_id, data_dir=data_dir, lang=lang)
    if char is None:
        return None

    skills = load_character_skills(data_dir=data_dir, lang=lang)
    trees = load_character_skill_trees(data_dir=data_dir, lang=lang)
    promotions = load_character_promotions(data_dir=data_dir, lang=lang)
    ranks = load_character_ranks(data_dir=data_dir, lang=lang)

    result = dict(char)
    result["skills_detail"] = [
        skills.get(sid) for sid in char.get("skills", []) if sid in skills
    ]
    result["skill_trees_detail"] = [
        trees.get(tid) for tid in char.get("skill_trees", []) if tid in trees
    ]
    result["promotion"] = promotions.get(char_id)
    result["ranks_detail"] = [
        ranks.get(rid) for rid in char.get("ranks", []) if rid in ranks
    ]

    return result


# ---------------------------------------------------------------------------
# 属性计算
# ---------------------------------------------------------------------------


def calc_character_stats(
    char_id: str,
    level: int = 80,
    promotion: Optional[int] = None,
    *,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
) -> Dict[str, float]:
    """计算角色在指定等级下的基础属性.

    StarRailRes 的 promotion 数据分为 6 段（0-5），对应等级区间：
        0: Lv.1-20, 1: 20-30, 2: 30-40, 3: 40-50, 4: 50-60, 5: 60-80

    属性公式: base + step * (level - min_level_of_promotion)

    Args:
        char_id: 角色 ID（如 "1001"）
        level: 目标等级（默认 80）
        promotion: 指定突破阶段（默认根据 level 自动推断）

    Returns:
        {"hp": ..., "atk": ..., "def": ..., "spd": ..., "crit_rate": ..., "crit_dmg": ...}
    """
    promo = get_promotion(char_id, data_dir=data_dir, lang=lang)
    if promo is None:
        raise ValueError(f"character promotion data not found: {char_id}")

    values = promo.get("values", [])
    if not values:
        raise ValueError(f"character {char_id} has no promotion values")

    # 根据 level 推断 promotion 阶段（7 段对应 7 次晋升 0-6）
    promo_levels = [(1, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 80)]
    if promotion is None:
        for idx, (lo, hi) in enumerate(promo_levels):
            if lo <= level <= hi:
                promotion = idx
                break
        if promotion is None:
            promotion = len(values) - 1

    pv = values[min(promotion, len(values) - 1)]

    def _calc(stat: str) -> float:
        entry = pv.get(stat, {})
        base = entry.get("base", 0)
        step = entry.get("step", 0)
        # base 是该晋升阶段的基础加成，step 是从 Lv.1 起的逐级增长
        return base + step * (level - 1)

    return {
        "hp": _calc("hp"),
        "atk": _calc("atk"),
        "def": _calc("def"),
        "spd": _calc("spd"),
        "crit_rate": _calc("crit_rate"),
        "crit_dmg": _calc("crit_dmg"),
    }


def calc_light_cone_stats(
    lc_id: str,
    level: int = 80,
    promotion: Optional[int] = None,
    *,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
) -> Dict[str, float]:
    """计算光锥在指定等级下的基础属性.

    逻辑与角色类似，但光锥只有 hp/atk/def 三个属性.
    """
    promos = load_light_cone_promotions(data_dir=data_dir, lang=lang)
    promo = promos.get(lc_id)
    if promo is None:
        raise ValueError(f"light cone promotion data not found: {lc_id}")

    values = promo.get("values", [])
    if not values:
        raise ValueError(f"light cone {lc_id} has no promotion values")

    promo_levels = [(1, 20), (20, 30), (30, 40), (40, 50), (50, 60), (60, 80)]
    if promotion is None:
        for idx, (lo, hi) in enumerate(promo_levels):
            if lo <= level <= hi:
                promotion = idx
                break
        if promotion is None:
            promotion = len(values) - 1

    pv = values[min(promotion, len(values) - 1)]

    def _calc(stat: str) -> float:
        entry = pv.get(stat, {})
        base = entry.get("base", 0)
        step = entry.get("step", 0)
        # base 是该晋升阶段的基础加成，step 是从 Lv.1 起的逐级增长
        return base + step * (level - 1)

    return {
        "hp": _calc("hp"),
        "atk": _calc("atk"),
        "def": _calc("def"),
    }


# ---------------------------------------------------------------------------
# 技能参数查询
# ---------------------------------------------------------------------------


def get_skill_params(
    skill_id: str,
    level: int = 1,
    *,
    data_dir: Optional[str] = None,
    lang: Optional[str] = None,
) -> List[float]:
    """获取技能在指定等级下的参数列表.

    Args:
        skill_id: 技能 ID
        level: 技能等级（1 开始）

    Returns:
        参数数值列表，如 [0.5, 0.0]
    """
    skill = get_skill(skill_id, data_dir=data_dir, lang=lang)
    if skill is None:
        raise ValueError(f"skill not found: {skill_id}")

    params = skill.get("params", [])
    idx = max(0, min(level - 1, len(params) - 1))
    return params[idx]


# ---------------------------------------------------------------------------
# 属性/命途/元素映射
# ---------------------------------------------------------------------------


def get_property_name(
    prop_type: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> str:
    """获取属性类型对应的显示名称."""
    props = load_properties(data_dir=data_dir, lang=lang)
    return props.get(prop_type, {}).get("name", prop_type)


def get_path_name(
    path_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> str:
    """获取命途 ID 对应的显示名称."""
    paths = load_paths(data_dir=data_dir, lang=lang)
    return paths.get(path_id, {}).get("name", path_id)


def get_element_name(
    element_id: str, *, data_dir: Optional[str] = None, lang: Optional[str] = None
) -> str:
    """获取元素 ID 对应的显示名称."""
    elements = load_elements(data_dir=data_dir, lang=lang)
    return elements.get(element_id, {}).get("name", element_id)


# ---------------------------------------------------------------------------
# 远程加载（fallback）
# ---------------------------------------------------------------------------


def fetch_from_github(
    filename: str,
    *,
    lang: str = "en",
    index: str = "index_new",
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """直接从 StarRailRes GitHub 仓库加载最新数据."""
    url = _GITHUB_RAW_URL.format(index=index, lang=lang, filename=filename)
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# 敌人数据
# ---------------------------------------------------------------------------


def load_enemies(
    *, data_dir: Optional[str] = None
) -> Dict[str, Any]:
    """加载敌人数据.

    数据来源: theBowja/starrail-data
    文件位置: data/enemies/enemies.json
    """
    if data_dir is None:
        # 默认使用项目根目录下的 data/enemies
        root = Path(__file__).parent.parent.parent.parent / "data" / "enemies"
    else:
        root = Path(data_dir) / "enemies"
    path = root / "enemies.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_enemy(
    enemy_id: str, *, data_dir: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 ID 查询敌人."""
    return load_enemies(data_dir=data_dir).get(enemy_id)


def list_enemies(
    *, data_dir: Optional[str] = None
) -> List[Tuple[str, str]]:
    """返回所有敌人 (id, name) 列表."""
    return [
        (eid, info.get("Name", ""))
        for eid, info in load_enemies(data_dir=data_dir).items()
    ]
