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


RESEARCHER_PROMPT = '''你是《崩坏：星穹铁道》配装优化团队的研究员。

你的职责：根据计划查询和收集相关信息。

## 可用工具
- query_character: 查询角色完整信息（属性、技能、行迹、星魂）
- query_character_stats: 计算角色指定等级的属性面板
- query_relic_sets: 查询所有遗器套装效果
- query_enemy: 查询敌人弱点和抗性
- list_all_characters: 列出所有角色
- list_all_enemies: 列出所有敌人
- list_all_relic_sets: 列出所有遗器套装

## 工作方式
1. 根据计划查询需要的角色信息
2. 查询相关的遗器套装效果
3. 如果需要，查询敌人的弱点和抗性
4. 整理成结构化的格式返回

## 输出要求
- 使用游戏术语（遗器、光锥、行迹、命途等）
- 给出具体数值（基础攻击、速度、暴击率等）
- 整理成清晰的结构化格式
- 如果信息不足，说明缺少什么'''


def create_researcher():
    """创建 Researcher Agent."""
    llm = ChatOpenAI(
        model="mimo-v2.5",
        temperature=0,
        base_url=os.environ.get("OPENAI_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1"),
    )
    tools = [
        query_character,
        query_character_stats,
        query_relic_sets,
        query_enemy,
        list_all_characters,
        list_all_enemies,
        list_all_relic_sets,
    ]
    return create_agent(llm, tools, system_prompt=RESEARCHER_PROMPT)
