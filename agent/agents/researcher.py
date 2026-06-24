"""Researcher Agent：查询角色、遗器、敌人等游戏数据."""

import os
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from agent.tools.data_tools import (
    query_character,
    query_character_stats,
    query_relic_sets,
    query_enemy,
    list_all_characters,
    list_all_enemies,
    list_all_relic_sets,
)
from agent.tools.web_tools import search_hsr_wiki, search_hoyolab, search_general


RESEARCHER_PROMPT = '''你是《崩坏：星穹铁道》配装优化团队的研究员。

你的职责：根据计划查询和收集相关信息。

## 可用工具（本地数据）
- query_character: 查询角色完整信息（属性、技能、行迹、星魂）
- query_character_stats: 查询角色指定等级的属性面板
- query_relic_sets: 查询所有遗器套装效果
- query_enemy: 查询敌人弱点和抗性
- list_all_characters: 列出所有角色
- list_all_enemies: 列出所有敌人
- list_all_relic_sets: 列出所有遗器套装

## 可用工具（网络搜索）
- search_hsr_wiki: 从 Fandom Wiki 搜索角色机制、技能倍率等
- search_hoyolab: 从米游社搜索玩家攻略、配装推荐
- search_general: 通用搜索，获取最新游戏信息

## 工作方式
1. 优先使用本地数据查询（更快、更稳定）
2. 如果本地数据不足或需要最新信息，使用网络搜索
3. 如果需要验证数据准确性，可以用网络搜索交叉验证
4. 整理成结构化的格式返回

## 输出要求
- 使用游戏术语（遗器、光锥、行迹、命途等）
- 给出具体数值（基础攻击、速度、暴击率等）
- 整理成清晰的结构化格式
- 标注数据来源（本地数据 / Fandom Wiki / 米游社）
- 如果信息不足，说明缺少什么'''


def create_researcher():
    """创建 Researcher Agent."""
    llm = ChatOpenAI(
        model=os.environ.get("OPENAI_MODEL", "claude-opus-4.8"),
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE"),
    )
    tools = [
        # 本地数据工具
        query_character,
        query_character_stats,
        query_relic_sets,
        query_enemy,
        list_all_characters,
        list_all_enemies,
        list_all_relic_sets,
        # 网络搜索工具
        search_hsr_wiki,
        search_hoyolab,
        search_general,
    ]
    return create_agent(llm, tools, system_prompt=RESEARCHER_PROMPT)
