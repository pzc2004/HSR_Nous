"""数据管道：从 StarRailRes 加载游戏数据.

HSR_Nous 的数据来源为社区维护的 Mar-7th/StarRailRes，上游为 Dimbreath/StarRailData.

主要接口:
    - load_characters():          加载角色基础信息
    - load_character_skills():    加载角色技能
    - load_character_skill_trees(): 加载角色行迹
    - load_character_promotions(): 加载角色晋阶数据
    - load_character_ranks():     加载角色星魂
    - load_light_cones():         加载光锥
    - load_relic_sets():          加载遗器套装
    - load_relics():              加载遗器
    - get_character(id):          按 ID 查询角色
    - get_character_full(id):     组装角色完整数据（含技能/行迹/晋阶/星魂）
    - calc_character_stats():     计算角色指定等级下的基础属性
    - get_skill_params():         获取技能参数

CLI 命令:
    hsr-data-update  -- 从 GitHub 拉取最新数据
"""

from hsr_nous.pipeline.loader import (
    calc_character_stats,
    calc_light_cone_stats,
    calc_relic_main_affix_values,
    calc_relic_sub_affix_values,
    fetch_from_github,
    get_character,
    get_character_by_name,
    get_character_full,
    get_element_name,
    get_enemy,
    get_enemy_by_name,
    get_light_cone,
    get_light_cone_by_name,
    get_light_cone_ranks,
    get_path_name,
    get_promotion,
    get_property_name,
    get_rank,
    get_relic,
    get_relic_set,
    get_relic_set_by_name,
    get_skill,
    get_skill_params,
    get_skill_tree,
    list_characters,
    list_enemies,
    list_light_cones,
    list_relic_sets,
    load_character_promotions,
    load_character_ranks,
    load_character_skill_trees,
    load_character_skills,
    load_character_skills_merged,
    load_characters,
    load_elements,
    load_enemies,
    load_fandom_skill_data,
    load_json,
    load_light_cone_promotions,
    load_light_cone_ranks,
    load_light_cones,
    load_paths,
    load_properties,
    load_relic_main_affixes,
    load_relic_sets,
    load_relic_sub_affixes,
    load_relics,
    load_signature_light_cones,
)
from hsr_nous.pipeline.update import run_update

__all__ = [
    "load_json",
    "load_characters",
    "load_character_skills",
    "load_character_skills_merged",
    "load_character_skill_trees",
    "load_character_promotions",
    "load_character_ranks",
    "load_light_cones",
    "load_light_cone_promotions",
    "load_light_cone_ranks",
    "load_relic_sets",
    "load_relics",
    "load_relic_main_affixes",
    "load_relic_sub_affixes",
    "load_properties",
    "load_paths",
    "load_elements",
    "load_enemies",
    "load_fandom_skill_data",
    "load_signature_light_cones",
    "get_character",
    "get_character_by_name",
    "get_character_full",
    "get_skill",
    "get_skill_tree",
    "get_promotion",
    "get_rank",
    "get_light_cone",
    "get_light_cone_by_name",
    "get_light_cone_ranks",
    "get_relic_set",
    "get_relic_set_by_name",
    "get_relic",
    "get_enemy",
    "get_enemy_by_name",
    "list_characters",
    "list_light_cones",
    "list_relic_sets",
    "list_enemies",
    "calc_character_stats",
    "calc_light_cone_stats",
    "calc_relic_main_affix_values",
    "calc_relic_sub_affix_values",
    "get_skill_params",
    "get_property_name",
    "get_path_name",
    "get_element_name",
    "fetch_from_github",
    "run_update",
]
