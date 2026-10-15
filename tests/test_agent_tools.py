"""Agent 工具层 smoke 测试：验证 data/sim/web 三个工具集的真实可用性.

注：sim_tools 已退役（2026-10-12——旧 demo 通道 encounter_adapter 删除，工具壳
恒返回退役说明），sim 段钉退役语义不断链。
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


# -------------------------------------------------------------------- sim_tools (已退役)


def test_simulate_battle_retired():
    """demo 通道已退役（2026-10-12——encounter_adapter 启发式编造值随 2026-10-12 整改
    整文件删除）：工具壳保留（SIM_TOOLS 注册不断链），调用恒返回退役说明，
    不得再输出编造数值（prompts 约定错误 → 降级纯数据查询）。"""
    from hsr_nous.agents.tools.sim_tools import simulate_battle

    out = simulate_battle.invoke({"team_config": "Acheron+Sparkle+Ruan Mei+Fu Xuan", "relic_set": "雷4"})
    assert "已退役" in out
    assert "total_damage" not in out, "退役后不得再输出编造数值"


def test_compare_configs_retired():
    from hsr_nous.agents.tools.sim_tools import compare_configs

    out = compare_configs.invoke({
        "team1": "Acheron+Sparkle+Ruan Mei+Fu Xuan",
        "team2": "Seele+Bronya+Pela+Luocha",
        "relic1": "雷4",
        "relic2": "量子4",
    })
    assert "已退役" in out
    assert "total_damage" not in out, "退役后不得再输出编造数值"


# -------------------------------------------------------------------- web_tools


def test_search_hoyolab_explicitly_placeholder():
    """显式锁定 search_hoyolab / search_general 为占位实现。"""
    from hsr_nous.agents.tools.web_tools import search_hoyolab, search_general

    out1 = search_hoyolab.invoke({"query": "黄泉 配装"})
    out2 = search_general.invoke({"query": "星穹铁道 1.5 版本"})
    assert "暂未接入" in out1, "search_hoyolab 应返回功能未接入提示"
    assert "暂未接入" in out2, "search_general 应返回功能未接入提示"


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


# -------------------------------------------------------------------- recommend_investment


def test_recommend_investment_with_owned_string():
    """owned_chars 字符串应被正确解析."""
    from hsr_nous.agents.tools.data_tools import recommend_investment

    out = recommend_investment.invoke({
        "target_team": "Acheron+Sparkle+Ruan Mei+Fu Xuan",
        "owned_chars": "Acheron:E2+Sparkle:E1+Fu Xuan:E0",
    })
    assert "资源优先级建议" in out
    # DPS (Acheron) 与 Sustain (Fu Xuan) 都应出现
    assert "Acheron" in out
    assert "Fu Xuan" in out


def test_recommend_investment_no_data_friendly_message():
    """无 target_team 无 owned_chars 应返回友好提示，不抛异常."""
    from hsr_nous.agents.tools.data_tools import recommend_investment

    out = recommend_investment.invoke({})
    assert "无法生成建议" in out
    assert "示例" in out