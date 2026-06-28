"""LLM 工厂测试：验证 make_chat_model 正确读取环境变量."""

import os

import pytest


def test_make_chat_model_reads_env(monkeypatch):
    """make_chat_model 应从环境变量读取模型配置."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.deepseek.com")

    from hsr_nous.agents.llm import make_chat_model

    model = make_chat_model()
    assert model.model_name == "deepseek-v4-flash"
    assert model.openai_api_base == "https://api.deepseek.com"


def test_make_chat_model_default_model(monkeypatch):
    """未设置 OPENAI_MODEL 时应使用默认值."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)

    from hsr_nous.agents.llm import make_chat_model

    model = make_chat_model()
    assert model.model_name == "deepseek-v4-flash"


def test_make_chat_model_temperature():
    """temperature 参数应正确传递."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from hsr_nous.agents.llm import make_chat_model

    model_zero = make_chat_model(temperature=0)
    assert model_zero.temperature == 0.0

    model_one = make_chat_model(temperature=0.7)
    assert model_one.temperature == 0.7

    monkeypatch.undo()


def test_make_chat_model_returns_chat_openai():
    """应返回 ChatOpenAI 实例."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from langchain_openai import ChatOpenAI
    from hsr_nous.agents.llm import make_chat_model

    model = make_chat_model()
    assert isinstance(model, ChatOpenAI)

    monkeypatch.undo()
