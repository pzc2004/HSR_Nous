"""Account 模块测试：覆盖未配置/已配置两条路径.

httpx 调用通过 monkeypatch 模拟，不发起真实网络请求。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# -------------------------------------------------------------------- credentials


def test_is_configured_false_by_default(monkeypatch):
    """未设置 env 时 is_configured 应返回 False."""
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)
    from hsr_nous.account import is_configured
    assert is_configured() is False


def test_is_configured_true_when_env_set(monkeypatch):
    monkeypatch.setenv("HSR_NOUS_HOYO_LTUID", "12345")
    monkeypatch.setenv("HSR_NOUS_HOYO_LTOKEN", "abcde")
    from hsr_nous.account import is_configured
    assert is_configured() is True


def test_get_owned_characters_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)
    from hsr_nous.account import get_owned_characters
    assert get_owned_characters() == []


def test_get_trailblaze_power_no_token_returns_zero(monkeypatch):
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)
    from hsr_nous.account import get_trailblaze_power
    assert get_trailblaze_power() == 0


def test_get_moc_records_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)
    from hsr_nous.account import get_moc_records
    assert get_moc_records() == []


# -------------------------------------------------------------------- tool integration


def test_query_my_account_unconfigured_friendly_message(monkeypatch):
    """未配置 token 时 query_my_account 应给出配置指引，不抛异常."""
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)

    from hsr_nous.agents.tools.data_tools import query_my_account
    out = query_my_account.invoke({})
    assert "未配置米游社账号" in out
    assert "HSR_NOUS_HOYO_LTUID" in out
    assert "docs/INTEGRATIONS.md" in out


# -------------------------------------------------------------------- mocked HTTP


def test_get_owned_characters_with_mocked_response(monkeypatch):
    """模拟 httpx 成功响应，验证 OwnedCharacter 解析."""
    monkeypatch.setenv("HSR_NOUS_HOYO_LTUID", "12345")
    monkeypatch.setenv("HSR_NOUS_HOYO_LTOKEN", "abcde")

    fake_response = {
        "retcode": 0,
        "data": {
            "list": [
                {
                    "avatar_id": 1308,
                    "name": "Acheron",
                    "level": 80,
                    "promotion": 6,
                    "rank": 2,
                    "equipment_id": 21039,
                    "equipment_level": 80,
                    "relic_list": [{"set_id": 101}, {"set_id": 102}],
                },
                {
                    "avatar_id": 1306,
                    "name": "Sparkle",
                    "level": 80,
                    "promotion": 6,
                    "rank": 1,
                    "equipment_id": None,
                    "equipment_level": 1,
                    "relic_list": [],
                },
            ]
        },
    }

    fake_json = lambda *a, **kw: fake_response
    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value.get.return_value.json.return_value = fake_response
    fake_ctx.__enter__.return_value.get.return_value.status_code = 200

    with patch("hsr_nous.account.client.httpx.Client", return_value=fake_ctx):
        from hsr_nous.account import get_owned_characters
        chars = get_owned_characters()
    assert len(chars) == 2
    assert chars[0].name == "Acheron"
    assert chars[0].eidolon == 2
    assert chars[0].light_cone_id == "21039"
    assert chars[1].name == "Sparkle"
    assert chars[1].light_cone_id is None


def test_get_trailblaze_power_with_mocked_response(monkeypatch):
    monkeypatch.setenv("HSR_NOUS_HOYO_LTUID", "12345")
    monkeypatch.setenv("HSR_NOUS_HOYO_LTOKEN", "abcde")

    fake_response = {"retcode": 0, "data": {"current_stamina": 240}}

    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value.get.return_value.json.return_value = fake_response
    fake_ctx.__enter__.return_value.get.return_value.status_code = 200

    with patch("hsr_nous.account.client.httpx.Client", return_value=fake_ctx):
        from hsr_nous.account import get_trailblaze_power
        assert get_trailblaze_power() == 240


def test_http_error_returns_empty(monkeypatch):
    """HTTP 5xx 应被吞掉，返回空结果而非抛异常."""
    monkeypatch.setenv("HSR_NOUS_HOYO_LTUID", "12345")
    monkeypatch.setenv("HSR_NOUS_HOYO_LTOKEN", "abcde")

    fake_ctx = MagicMock()
    fake_ctx.__enter__.return_value.get.return_value.status_code = 500

    with patch("hsr_nous.account.client.httpx.Client", return_value=fake_ctx):
        from hsr_nous.account import get_owned_characters, get_trailblaze_power, get_moc_records
        assert get_owned_characters() == []
        assert get_trailblaze_power() == 0
        assert get_moc_records() == []


# -------------------------------------------------------------------- account_adapter


def test_account_adapter_returns_none_for_missing_data():
    """adapters.account_adapter 查无官方数据返回 None（命名两态：不造编造兜底面板）."""
    from hsr_nous.account.models import OwnedCharacter
    from hsr_nous.adapters.account_adapter import adapt_owned_character

    oc = OwnedCharacter(character_id="99999_不存在的ID", name="Test", level=80)
    assert adapt_owned_character(oc) is None


def test_account_adapter_real_character_stats():
    """正常路径：面板全字段来自官方数据（无硬编码兜底），max_energy 取自 characters.max_sp."""
    from hsr_nous.account.models import OwnedCharacter
    from hsr_nous.adapters.account_adapter import adapt_owned_character
    from hsr_nous.pipeline import calc_character_stats, get_character

    oc = OwnedCharacter(character_id="1001", name="March 7th", level=80)
    actor = adapt_owned_character(oc)
    assert actor is not None
    want = calc_character_stats("1001", level=80, lang="en")
    assert actor.stats.hp == want["hp"] and actor.stats.atk == want["atk"]
    assert actor.stats.max_energy == float(get_character("1001", lang="en")["max_sp"])