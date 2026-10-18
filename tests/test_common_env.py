"""common.env 的 .env 解析与加载语义."""
from __future__ import annotations

import os

from hsr_nous.common.env import load_dotenv, parse_env_file


def test_duplicate_keys_keep_first_value(tmp_path):
    path = tmp_path / ".env"
    path.write_text("A=first\nA=second\n", encoding="utf-8")
    assert parse_env_file(path)["A"] == "first"


def test_external_environment_has_priority(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("A=file\n", encoding="utf-8")
    monkeypatch.setenv("A", "external")
    load_dotenv(path)
    assert os.environ["A"] == "external"


def test_research_root_prefers_environment(tmp_path, monkeypatch):
    from hsr_nous.common import RESEARCH_ROOT_ENV, research_root

    expected = tmp_path / "research-output"
    monkeypatch.setenv(RESEARCH_ROOT_ENV, str(expected))
    assert research_root() == expected


def test_research_root_defaults_to_user_home_not_repository(tmp_path, monkeypatch):
    from pathlib import Path

    from hsr_nous.common import RESEARCH_ROOT_ENV, research_root

    monkeypatch.delenv(RESEARCH_ROOT_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert research_root() == Path.home() / "HSR_Nous"
    assert research_root() != tmp_path / "HSR_Nous"
