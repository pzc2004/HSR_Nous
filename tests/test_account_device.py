"""设备身份（account/device.py）测试——离线：签发/持久化/env 覆写/接线。

风控背景（docs/integrations.md §1.8）：身份一次签发、永久复用；env 覆写优先。
本文件钉：签发幂等、失败降级不抛、env 短路不发网络、client/login 接线真生效。
"""
from __future__ import annotations

import json
import urllib.request

import pytest

import hsr_nous.account.client as client_mod
import hsr_nous.account.device as device_mod
from hsr_nous.account.device import ensure_device_identity, load_device_identity


@pytest.fixture()
def cfg_home(tmp_path, monkeypatch):
    """隔离配置目录（XDG_CONFIG_HOME 指向 tmp——不落真 ~/.config）."""
    monkeypatch.setattr(device_mod, "_config_dir",
                        lambda: tmp_path / "hsr_nous")
    monkeypatch.setattr(device_mod, "_IDENTITY_CACHE", {})
    return tmp_path / "hsr_nous"


# ----------------------------------------------------------------- 读/写/优先级


def test_env_override_wins_and_skips_file(cfg_home, monkeypatch):
    monkeypatch.setenv("HSR_NOUS_HOYO_DEVICE_ID", "ENV_DID")
    monkeypatch.setenv("HSR_NOUS_HOYO_DEVICE_FP", "ENV_DFP")
    assert load_device_identity() == ("ENV_DID", "ENV_DFP")
    assert not cfg_home.exists(), "env 覆写时不应触碰持久化文件"


def test_env_partial_id_only(cfg_home, monkeypatch):
    monkeypatch.setenv("HSR_NOUS_HOYO_DEVICE_ID", "ONLY_ID")
    monkeypatch.delenv("HSR_NOUS_HOYO_DEVICE_FP", raising=False)
    assert load_device_identity() == ("ONLY_ID", None)


def test_file_roundtrip(cfg_home):
    cfg_home.mkdir(parents=True)
    (cfg_home / "device_identity.json").write_text(json.dumps(
        {"device_id": "FILE_DID", "device_fp": "FILE_DFP", "fp_issued_at": 42}),
        encoding="utf-8")
    assert load_device_identity() == ("FILE_DID", "FILE_DFP")


def test_corrupt_file_treated_as_missing(cfg_home, monkeypatch):
    cfg_home.mkdir(parents=True)
    (cfg_home / "device_identity.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(device_mod, "_sign_device_fp", lambda *a, **k: None)
    did, dfp = ensure_device_identity()
    assert did, "坏文件 = 未签发：现场重新生成 device_id"
    assert dfp is None


# ----------------------------------------------------------------- 签发与幂等


def test_ensure_generates_then_signs_and_persists(cfg_home, monkeypatch):
    calls = []

    def fake_sign(device_id, timeout=15.0):
        calls.append(device_id)
        return "SIGNED_FP"

    monkeypatch.setattr(device_mod, "_sign_device_fp", fake_sign)
    did1, fp1 = ensure_device_identity()
    assert did1 and fp1 == "SIGNED_FP"
    assert calls == [did1], "签发恰好一次"

    # 持久化落盘且二次调用幂等（不重复签发）
    did2, fp2 = ensure_device_identity()
    assert (did2, fp2) == (did1, fp1)
    assert calls == [did1], "已有身份不重复 getFp"
    data = json.loads((cfg_home / "device_identity.json").read_text(encoding="utf-8"))
    assert data == {"device_id": did1, "device_fp": "SIGNED_FP",
                    "fp_issued_at": data["fp_issued_at"]}


def test_ensure_sign_failure_returns_id_without_fp(cfg_home, monkeypatch):
    monkeypatch.setattr(device_mod, "_sign_device_fp", lambda *a, **k: None)
    did, dfp = ensure_device_identity()
    assert did and dfp is None, "拒签/离线降级：device_id 可用，fp 缺省不阻塞"
    data = json.loads((cfg_home / "device_identity.json").read_text(encoding="utf-8"))
    assert data["device_fp"] is None
    # fp 缺席时下次 ensure 会再尝试签发（机会自愈）
    monkeypatch.setattr(device_mod, "_sign_device_fp", lambda *a, **k: "LATER_FP")
    assert ensure_device_identity() == (did, "LATER_FP")


def test_fp_only_reuses_generated_id(cfg_home, monkeypatch):
    """仅 env FP 时也复用持久化 ID，不得每次调用换 device_id。"""
    monkeypatch.setenv("HSR_NOUS_HOYO_DEVICE_FP", "ENV_FP")

    def _no_sign(*args, **kwargs):
        raise AssertionError("不应重复签发")

    monkeypatch.setattr(device_mod, "_sign_device_fp", _no_sign)
    did1, fp1 = ensure_device_identity()
    did2, fp2 = ensure_device_identity()
    assert did1 == did2 and fp1 == fp2 == "ENV_FP"
    data = json.loads((cfg_home / "device_identity.json").read_text(encoding="utf-8"))
    assert data["device_id"] == did1 and data["device_fp"] == "ENV_FP"


def test_save_failure_reuses_process_cache(cfg_home, monkeypatch):
    """写盘失败时进程内缓存也必须保证身份稳定，不得反复生成/签发。"""
    (cfg_home / "device_identity.json").mkdir(parents=True)
    calls = []

    def fake_sign(device_id, timeout=15.0):
        calls.append(device_id)
        return "SIGNED_FP"

    monkeypatch.setattr(device_mod, "_sign_device_fp", fake_sign)
    did1, fp1 = ensure_device_identity()
    did2, fp2 = ensure_device_identity()
    assert did1 == did2 and fp1 == fp2 == "SIGNED_FP"
    assert calls == [did1], "写盘失败也不得重复 getFp"


# ----------------------------------------------------------------- getFp 协议形状


def _fake_urlopen(payload_box):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": {"code": 200,
                                        "device_fp": "SERVER_FP_9"}}).encode()

    def _opener(req, timeout=None):
        payload_box["url"] = req.full_url
        payload_box["payload"] = json.loads(req.data.decode("utf-8"))
        return _Resp()

    return _opener


def test_sign_posts_getfp_payload_cn(cfg_home, monkeypatch):
    box = {}
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(box))
    fp = device_mod._sign_device_fp("DID")
    assert fp == "SERVER_FP_9"
    assert box["url"] == device_mod._GET_FP_URLS["cn"], "缺省国服端点"
    p = box["payload"]
    assert p["device_id"] == "DID"
    assert len(p["device_fp"]) == 13, "种子 fp=13 位 hex（genshin.py 形状）"
    assert p["app_name"] == "bbs_cn" and p["platform"] == "2"
    assert "bbs_device_id" in p
    oaid = json.loads(p["ext_fields"]).get("oaid")
    assert oaid and len(oaid) == 16, "空 oaid 被端点拒签（code 500 内部错误实证）——必须非空"
    assert oaid == device_mod._stable_oaid("DID"), "oaid 从 device_id 稳定派生"


def test_sign_overseas_endpoint_and_rejection(cfg_home, monkeypatch):
    box = {}
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen(box))
    monkeypatch.setenv("HSR_NOUS_HOYO_SERVER", "os_asia")
    assert device_mod._sign_device_fp("DID") == "SERVER_FP_9"
    assert box["url"] == device_mod._GET_FP_URLS["os"]
    assert box["payload"]["app_name"] == "bbs_oversea"
    assert "hoyolab_device_id" in box["payload"]

    class _Reject:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"data": {"code": 400, "msg": "bad ext"}}).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Reject())
    assert device_mod._sign_device_fp("DID") is None, "拒签降级 None 不抛"


# ----------------------------------------------------------------- 接线


def test_make_client_wires_device_identity(cfg_home, monkeypatch):
    monkeypatch.setattr(client_mod, "ensure_device_identity",
                        lambda *a, **k: ("DID_1", "DFP_1"))
    monkeypatch.setenv("HSR_NOUS_HOYO_LTUID", "12345")
    monkeypatch.setenv("HSR_NOUS_HOYO_LTOKEN", "tok")
    c = client_mod._make_client()
    assert c is not None
    assert c.custom_headers["x-rpc-device_id"] == "DID_1"
    assert c.custom_headers["x-rpc-device_fp"] == "DFP_1"


def test_make_client_unconfigured_returns_none(cfg_home, monkeypatch, caplog):
    monkeypatch.delenv("HSR_NOUS_HOYO_LTUID", raising=False)
    monkeypatch.delenv("HSR_NOUS_HOYO_LTOKEN", raising=False)
    monkeypatch.setattr(client_mod, "_read_secret", lambda k: None)
    import logging
    with caplog.at_level(logging.INFO, logger="hsr_nous.account.client"):
        assert client_mod._make_client() is None
    assert any("未配置" in r.message for r in caplog.records)


def test_fetch_geetest_logs_warning(monkeypatch, caplog):
    import asyncio
    import genshin.errors
    import logging

    monkeypatch.setattr(client_mod, "_make_client", lambda: object())

    def _raise(coro):
        coro.close()
        raise genshin.errors.GeetestError({"retcode": 10035})

    monkeypatch.setattr(asyncio, "run", _raise)
    with caplog.at_level(logging.WARNING, logger="hsr_nous.account.client"):
        assert client_mod.fetch_account_snapshot() is None
    assert any("10035" in r.message for r in caplog.records), "风控触发必须留痕"


def test_qr_login_uses_persisted_identity(monkeypatch):
    from hsr_nous.account.login import QRLogin
    monkeypatch.setattr(device_mod, "ensure_device_identity",
                        lambda *a, **k: ("QR_DID", "QR_DFP"))
    q = QRLogin()
    try:
        assert q.device_id == "QR_DID" and q.device_fp == "QR_DFP"
    finally:
        q.close()
