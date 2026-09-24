"""社区调研层（community_search/community_fetch + 证据包接线）——fake 注入不碰真网."""

from __future__ import annotations

import pytest

from hsr_nous.ops.annotator import FakeRunner, run_character
from hsr_nous.ops.annotator.nodes import community_fetch_node, community_search_node
from tests._annotator_dogfood import TPL_1404_GOLDEN_CLEAN
from tests._data_env import data_available, data_skip_reason

_need_data = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

_OFFICIAL = {
    "cid": "1404", "name_cn": "万敌", "name_en": "Mydei", "path": "Warrior",
    "element": "Imaginary", "max_sp": 160,
    "skills": [{"id": "140401"}, {"id": "1140401"}],
    "ranks": [],
}
_CROSS = {"rows": [], "conflicts": [{"name_cn": "万死无悔", "why": "tbgd 0 ↔ 米游社有消耗标"}],
          "note": "sp_cost 以 tbgd 为权威"}


def _fake_search(q, n):
    import zlib
    return [
        {"title": f"{q} 结果A", "url": f"https://example.com/a-{zlib.crc32(q.encode()) % 97}",
         "snippet": "操控细节"},
        {"title": "重复页", "url": "https://example.com/dup", "snippet": "重复摘要"},
    ]


def test_search_queries_and_dedupe():
    node = community_search_node("1404", search_fn=_fake_search, per_query=2)
    out = node.fn({"data_pull": _OFFICIAL, "crosscheck": _CROSS})
    queries = {r["query"] for r in out}
    assert any("Mydei hsr guide" in q for q in queries), "EN 名检索词（name_en 取数）"
    assert any("忆灵" in q for q in queries), "114 系技能检出 → 忆灵交互语义检索词"
    assert any("战技点" in q for q in queries), "对轴冲突驱动检索词"
    urls = [r["url"] for r in out]
    assert urls.count("https://example.com/dup") == 1, "跨查询按 url 去重"


def test_evidence_prompt_carries_community_pack():
    llm = FakeRunner([("证据笔记", "# 笔记")])
    node = community_fetch_node("1404", fetch_fn=lambda url, cap: "正文" + url)
    pages = node.fn({"community_search": [
        {"url": "https://a", "title": "甲"}, {"url": "https://b", "title": "乙"}]})
    assert pages[0]["text"] == "正文https://a"
    from hsr_nous.ops.annotator.nodes import evidence_node
    ev = evidence_node("1404", llm)
    ev.fn({"data_pull": _OFFICIAL, "crosscheck": _CROSS, "community_fetch": pages})
    prompt = llm.calls[0]["prompt"]
    assert "【社区】甲（https://a）" in prompt and "正文https://a" in prompt, "社区包进证据提示词"
    assert "实测>社区>wiki" in prompt, "冲突裁决序随包下发"


_TPL = TPL_1404_GOLDEN_CLEAN


@_need_data
def test_pipeline_with_community_layer(tmp_path):
    llm = FakeRunner([("被闸门打回", _TPL), ("DSL YAML 模板", _TPL), ("证据笔记", "# 笔记")])
    out = run_character(
        "1404", llm=llm, runs_root=tmp_path / "runs", staging_root=tmp_path / "staging",
        search_fn=_fake_search, fetch_fn=lambda url, cap: f"正文:{url}")
    assert "community_search" in out and "community_fetch" in out, "社区两节点入图"
    assert out["community_fetch"][0]["text"].startswith("正文:")
    assert "finalize" in out, "社区层接线后全链仍到 finalize"


def test_community_search_degrades_on_engine_failure():
    """搜索引擎全挂 → 降级空层不抛 DagError（1001 试点实证：ddgs 'No results found'
    直接炸死整角色）——留失败标记供溯源，fetch 跳过无 url 标记。"""
    from hsr_nous.ops.annotator.nodes import community_fetch_node, community_search_node

    def _boom(query, max_results):
        raise RuntimeError("No results found.")

    s = community_search_node("1001", search_fn=_boom)
    out = s.fn({"data_pull": {"name_cn": "三月七", "name_en": "March 7th", "skills": []},
                "crosscheck": {"conflicts": []}})
    assert all(r.get("url") == "" for r in out), "全挂 → 只剩降级标记"
    assert any("降级空层" in r["title"] for r in out)
    f = community_fetch_node("1001", fetch_fn=lambda url, cap: "x")
    assert f.fn({"community_search": out}) == [], "无 url 标记不进抓取"


def test_community_search_partial_failure_keeps_hits():
    """单查询挂、其余命中 → 命中保留 + 失败标记一条（不拖死整层）。"""
    from hsr_nous.ops.annotator.nodes import community_search_node

    def _flaky(query, max_results):
        if "攻略" in query:
            raise RuntimeError("boom")
        return [{"title": "T", "url": "https://a", "snippet": "s"}]

    s = community_search_node("1001", search_fn=_flaky)
    out = s.fn({"data_pull": {"name_cn": "三月七", "name_en": "March 7th", "skills": []},
                "crosscheck": {"conflicts": []}})
    assert any(r.get("url") == "https://a" for r in out), "命中保留"
    assert any("降级空层" in r["title"] for r in out), "失败留痕"
