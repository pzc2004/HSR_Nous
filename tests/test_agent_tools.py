"""Agent 工具层 smoke 测试：验证 data/sim/web 三个工具集的真实可用性。

注：sim_tools 当前为占位实现，断言其**显式标注**"占位"以锁定语义——
阶段 2 替换为真实引擎后，本断言需同步更新。
"""
from __future__ import annotations

import socket
from pathlib import Path

import pytest


DATA_DIR = Path("data/starrailres/index_new/en")


def _has_network() -> bool:
    """最佳努力探测 Fandom 可达性。"""
    try:
        socket.create_connection(("honkai-star-rail.fandom.com", 443), timeout=2).close()
        return True
    except OSError:
        return False


# -------------------------------------------------------------------- data_tools


@pytest.fixture
def data_tools_en(monkeypatch):
    """data_tools 模块默认 lang='cn'，测试环境下切换到 'en'。"""
    import hsr_nous.agents.tools.data_tools as dt

    monkeypatch.setattr(dt, "_LANG", "en")
    return dt


@pytest.mark.skipif(not DATA_DIR.exists(), reason="需要 data/starrailres 数据")
def test_query_character_returns_structured_text(data_tools_en):
    """query_character("Acheron") 应返回包含属性面板的报告。"""
    out = data_tools_en.query_character.invoke({"character_name": "Acheron"})
    assert isinstance(out, str)
    assert "HP" in out
    assert "ATK" in out or "攻击力" in out
    assert "SPD" in out or "速度" in out


@pytest.mark.skipif(not DATA_DIR.exists(), reason="需要 data/starrailres 数据")
def test_query_character_unknown_name(data_tools_en):
    out = data_tools_en.query_character.invoke({"character_name": "NotExistXYZ"})
    assert "未找到" in out or "找不到" in out


@pytest.mark.skipif(not DATA_DIR.exists(), reason="需要数据")
def test_list_all_characters_nonempty(data_tools_en):
    out = data_tools_en.list_all_characters.invoke({})
    assert "共有" in out
    # 英文数据中应包含至少一个标准角色
    assert len(out) > 50


@pytest.mark.skipif(not Path("data/enemies/enemies.json").exists(), reason="需要敌人数据")
def test_query_enemy_returns_resistance(data_tools_en):
    out = data_tools_en.query_enemy.invoke({"enemy_name": "冰锋"})
    assert "弱点" in out or "抗性" in out or "Weakness" in out or "Resistance" in out


# -------------------------------------------------------------------- sim_tools (占位)


def test_simulate_battle_returns_placeholder():
    """锁定 sim_tools 的占位语义——阶段 2 替换为真实引擎后必须更新本测试。"""
    from hsr_nous.agents.tools.sim_tools import simulate_battle

    out = simulate_battle.invoke({"team_config": "黄泉+花火+阮梅+符玄", "relic_set": "雷4"})
    assert "DPS" in out
    assert "占位" in out, (
        "simulate_battle 仍应为占位实现；若已替换为真实引擎，请同步更新本测试"
    )


def test_compare_configs_returns_two_results():
    from hsr_nous.agents.tools.sim_tools import compare_configs

    out = compare_configs.invoke({
        "team1": "黄泉+花火+阮梅+符玄",
        "team2": "银狼+布洛妮娅+佩拉+罗刹",
        "relic1": "雷4",
        "relic2": "量子4",
    })
    assert "配置 1" in out
    assert "配置 2" in out
    assert "占位" in out


# -------------------------------------------------------------------- web_tools


def test_search_hoyolab_explicitly_placeholder():
    """显式锁定 search_hoyolab / search_general 为占位实现。"""
    from hsr_nous.agents.tools.web_tools import search_hoyolab, search_general

    out1 = search_hoyolab.invoke({"query": "黄泉 配装"})
    out2 = search_general.invoke({"query": "星穹铁道 1.5 版本"})
    assert "[占位]" in out1, "search_hoyolab 应返回显式占位标记"
    assert "[占位]" in out2, "search_general 应返回显式占位标记"


@pytest.mark.skipif(
    not _has_network(), reason="需要联网访问 Fandom API"
)
def test_search_hsr_wiki_reachable():
    """search_hsr_wiki 是唯一真实的网络工具——CI/无网环境 skip。"""
    import socket

    from hsr_nous.agents.tools.web_tools import search_hsr_wiki

    try:
        socket.create_connection(("honkai-star-rail.fandom.com", 443), timeout=2).close()
    except OSError:
        pytest.skip("无法连接 Fandom API")

    out = search_hsr_wiki.invoke({"query": "Acheron"})
    # 即便 API 限流也应返回某种结构化文本
    assert isinstance(out, str)
    assert len(out) > 0