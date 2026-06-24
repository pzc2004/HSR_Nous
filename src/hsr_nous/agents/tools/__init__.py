"""Agent 工具集：数据查询、战斗模拟、网络搜索."""

from hsr_nous.agents.tools.data_tools import (
    query_character,
    query_character_stats,
    query_relic_sets,
    query_enemy,
    list_all_characters,
    list_all_enemies,
    list_all_relic_sets,
)
from hsr_nous.agents.tools.sim_tools import simulate_battle, compare_configs
from hsr_nous.agents.tools.web_tools import search_hsr_wiki, search_hoyolab, search_general

DATA_TOOLS = [
    query_character,
    query_character_stats,
    query_relic_sets,
    query_enemy,
    list_all_characters,
    list_all_enemies,
    list_all_relic_sets,
]

WEB_TOOLS = [search_hsr_wiki, search_hoyolab, search_general]

SIM_TOOLS = [simulate_battle, compare_configs]
