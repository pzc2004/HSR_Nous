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
