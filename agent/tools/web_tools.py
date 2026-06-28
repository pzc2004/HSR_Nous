"""网络搜索工具：从 Fandom Wiki、米游社等获取最新游戏信息.

当本地数据不完整或需要最新信息时，通过网络搜索补充。
使用 Fandom Wiki API 直接搜索，不依赖第三方搜索服务。
"""

import json
import urllib.request
from langchain_core.tools import tool


def _fandom_search(query: str, limit: int = 5) -> str:
    """通过 Fandom Wiki API 搜索."""
    try:
        url = (
            f"https://honkai-star-rail.fandom.com/api.php"
            f"?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&srlimit={limit}&format=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("query", {}).get("search", [])
        if not results:
            return f"Fandom Wiki 未找到相关结果: '{query}'"

        output = f"Fandom Wiki 搜索结果: '{query}'\n\n"
        for i, r in enumerate(results, 1):
            title = r.get("title", "未知")
            snippet = r.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
            page_url = f"https://honkai-star-rail.fandom.com/wiki/{title.replace(' ', '_')}"
            output += f"{i}. {title}\n"
            output += f"   链接: {page_url}\n"
            output += f"   摘要: {snippet[:200]}\n\n"

        return output
    except Exception as e:
        return f"Fandom 搜索失败: {e}"


def _fandom_page_content(page_title: str, sections: str = "") -> str:
    """获取 Fandom Wiki 页面内容."""
    try:
        # 先获取页面内容
        url = (
            f"https://honkai-star-rail.fandom.com/api.php"
            f"?action=parse&page={urllib.parse.quote(page_title)}"
            f"&prop=wikitext&format=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")

        # 截取前 3000 字符（避免太长）
        if len(wikitext) > 3000:
            wikitext = wikitext[:3000] + "\n\n... (内容已截断)"

        return f"Fandom Wiki 页面: {page_title}\n\n{wikitext}"
    except Exception as e:
        return f"获取页面失败: {e}"


import urllib.parse


@tool
def search_hsr_wiki(query: str) -> str:
    """从 Honkai Star Rail Wiki (Fandom) 搜索游戏信息。

    适用于查询角色详细机制、技能倍率、最优配装攻略等。
    数据来源: https://honkai-star-rail.fandom.com

    Args:
        query: 搜索关键词，如 "Acheron best light cone"、"Black Swan relics"
    """
    return _fandom_search(query)


@tool
def fetch_wiki_page(page_title: str) -> str:
    """获取 Fandom Wiki 上指定页面的内容。

    适用于获取角色详细信息、装备效果等。页面标题通常是角色英文名。
    常见页面标题: Acheron, Sparkle, Ruan Mei, Fu Xuan, Fandom:Acheron/Strategy

    Args:
        page_title: Wiki 页面标题，如 "Acheron"、"Sparkle"
    """
    return _fandom_page_content(page_title)


@tool
def search_hoyolab(query: str) -> str:
    """搜索米游社 (HoYoLAB) 的攻略和社区讨论。

    适用于查询玩家攻略、配装推荐、实战测试等社区内容。

    Args:
        query: 搜索关键词，如 "黄泉 配装"、"崩铁 深渊 攻略"
    """
    try:
        # 米游社没有公开 API，使用网页搜索
        url = (
            f"https://www.miyoushe.com/ys/search"
            f"?keyword={urllib.parse.quote(query)}"
        )
        return f"米游社搜索链接（需手动打开）:\n{url}\n\n提示: 米游社无公开 API，请参考搜索链接查看社区攻略。"
    except Exception as e:
        return f"米游社搜索失败: {e}"


@tool
def search_general(query: str) -> str:
    """通用搜索，获取最新的崩坏星穹铁道相关信息。

    先尝试 Fandom Wiki 搜索，如果结果不足再补充其他来源。

    Args:
        query: 搜索关键词
    """
    # 先搜 Fandom
    result = _fandom_search(query, limit=3)
    return result
