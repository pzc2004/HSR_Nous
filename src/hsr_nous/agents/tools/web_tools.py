"""网络搜索工具：从 Fandom Wiki 等获取游戏信息."""

import urllib.request
import urllib.parse
import json
import warnings

from langchain_core.tools import tool


def _fandom_search(query: str, limit: int = 3) -> list:
    """调用 Fandom Wiki API 搜索."""
    base_url = "https://honkai-star-rail.fandom.com/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "format": "json",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("query", {}).get("search", [])
    except Exception as e:
        warnings.warn(f"Fandom API 请求失败: {type(e).__name__}: {e}")
        return []


def _fandom_page_content(title: str) -> str:
    """获取 Fandom Wiki 页面摘要."""
    base_url = "https://honkai-star-rail.fandom.com/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "exintro": "true",
        "explaintext": "true",
        "format": "json",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "")[:2000]
    except Exception as e:
        warnings.warn(f"Fandom 页面获取失败: {type(e).__name__}: {e}")
    return ""


@tool
def search_hsr_wiki(query: str) -> str:
    """从崩坏星穹铁道 Fandom Wiki 搜索信息。

    适用于查询角色机制、技能倍率、削韧值等。

    Args:
        query: 搜索关键词，如 "Acheron skill"、"break effect"
    """
    results = _fandom_search(query)
    if not results:
        return f"Wiki 搜索无结果: {query}"

    output = f"Wiki 搜索结果 ({query}):\n\n"
    for r in results:
        title = r.get("title", "")
        snippet = r.get("snippet", "").replace('<span class="searchmatch">', "").replace("</span>", "")
        output += f"【{title}】\n{snippet}\n\n"

        content = _fandom_page_content(title)
        if content:
            output += f"摘要: {content[:500]}\n\n"

    return output


@tool
def search_hoyolab(query: str) -> str:
    """从米游社/HoYoLAB 搜索玩家攻略和讨论。

    注意：此功能暂未接入，会返回说明信息。
    建议：优先使用 search_hsr_wiki 查询游戏机制数据。

    Args:
        query: 搜索关键词
    """
    return (
        f"米游社搜索 '{query}' 暂未接入。\n"
        f"请使用 search_hsr_wiki 查询游戏机制，或使用本地数据工具查询角色/遗器信息。"
    )


@tool
def search_general(query: str) -> str:
    """通用网络搜索，获取最新游戏信息。

    注意：此功能暂未接入，会返回说明信息。
    建议：优先使用 search_hsr_wiki 或本地数据工具。

    Args:
        query: 搜索关键词
    """
    return (
        f"通用搜索 '{query}' 暂未接入。\n"
        f"请使用 search_hsr_wiki 查询 Fandom Wiki，或使用本地数据工具查询角色/遗器/敌人信息。"
    )
