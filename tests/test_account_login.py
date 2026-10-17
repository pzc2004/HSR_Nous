"""扫码登录凭证落盘与 keyring 半失败测试."""
from __future__ import annotations

import sys
from types import SimpleNamespace

from hsr_nous.account import login as login_mod
from hsr_nous.common import paths as common_paths


def test_save_to_env_uses_repo_root_and_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(common_paths, "repo_root", lambda: tmp_path)
    login_mod._save_to_env({"ltuid": "123", "ltoken": "tok"})
    path = tmp_path / ".env"
    assert path.is_file()
    assert "HSR_NOUS_HOYO_LTUID=123" in path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o777 == 0o600


def test_keyring_partial_failure_cleans_first_key(monkeypatch):
    calls = []

    class _FakeKeyring:
        @staticmethod
        def set_password(service, key, value):
            calls.append(("set", service, key, value))
            if key == "HSR_NOUS_HOYO_LTOKEN":
                raise RuntimeError("backend unavailable")

        @staticmethod
        def delete_password(service, key):
            calls.append(("delete", service, key, None))

    monkeypatch.setitem(sys.modules, "keyring", _FakeKeyring)
    assert not login_mod._save_to_keyring({"ltuid": "123", "ltoken": "tok"})
    assert ("delete", "hsr_nous", "HSR_NOUS_HOYO_LTUID", None) in calls
