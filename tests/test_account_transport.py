"""记录接口 Chrome 指纹传输层（account/transport.py）测试——离线。

钉：
- 请求装配：endpoint URL / role_id+server params / DS 头 / Cookie 串 / 设备头合并；
- retcode → genshin.errors 映射（10035 = GeetestError，client 分类日志零改动）;
- 三接口模型构造（genshin 模型——它漂移我们跟随）；
- _fetch_snapshot 选择器：transport 可用走 curl 路径，缺 curl-cffi 回退 aiohttp。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import genshin.errors
from hsr_nous.account import client as client_mod
from hsr_nous.account import transport


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    """记录请求装配 + 按 endpoint 回罐头。"""

    def __init__(self, payloads):
        self._payloads = payloads
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        for key, payload in self._payloads.items():
            if key in url:
                return _FakeResp(payload)
        raise AssertionError(f"未预期的 endpoint：{url}")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_available_true_in_this_env():
    assert transport.available(), "curl-cffi 已入 account extra，本环境必可用"


def test_get_request_assembly():
    sess = _FakeSession({"note": {"retcode": 0, "data": {}}})
    data = transport._get(sess, "note", 100000001, {"ltuid": "1", "ltoken": "tok"},
                          {"x-rpc-device_id": "DID", "x-rpc-device_fp": "DFP"}, None, 30)
    assert data == {}
    call = sess.calls[0]
    assert call["url"].endswith("/game_record/app/hkrpg/api/note")
    assert call["params"]["role_id"] == 100000001
    assert call["params"]["server"] == "prod_gf_cn", "国服 uid 服务器推导"
    assert call["headers"]["x-rpc-device_id"] == "DID"
    assert call["headers"]["x-rpc-device_fp"] == "DFP"
    assert call["headers"]["ds"], "DS 签名头在场"
    assert call["headers"]["Cookie"] == "ltuid=1; ltoken=tok"


def test_get_geetest_retcode_mapping():
    sess = _FakeSession({"note": {"retcode": 10035, "message": "geetest",
                                  "data": None}})
    with pytest.raises(genshin.errors.GeetestError):
        transport._get(sess, "note", 100000001, {"ltuid": "1"}, {}, None, 30)


def test_get_success_requires_retcode_zero():
    sess = _FakeSession({"note": {"retcode": -100, "message": "nope", "data": None}})
    with pytest.raises(genshin.errors.GenshinException):
        transport._get(sess, "note", 100000001, {"ltuid": "1"}, {}, None, 30)


def test_fetch_three_endpoints_minimal_payloads():
    payloads = {
        "avatar/info": {"retcode": 0, "data": {
            "avatar_list": [],
            "equip_wiki": {}, "relic_wiki": {}, "property_info": {},
            "recommend_property": {}, "relic_properties": []}},
        "note": {"retcode": 0, "data": {
            "current_stamina": 160, "max_stamina": 240,
            "stamina_recover_time": 0,
            "accepted_epedition_num": 0,   # API 键名自带此 typo（模型 Aliased 对应）
            "total_expedition_num": 4, "expeditions": [],
            "current_train_score": 0, "max_train_score": 0,
            "current_rogue_score": 0, "max_rogue_score": 0,
            "rogue_tourn_weekly_unlocked": False,
            "rogue_tourn_weekly_max": 0, "rogue_tourn_weekly_cur": 0,
            "weekly_cocoon_cnt": 0, "weekly_cocoon_limit": 0,
            "current_reserve_stamina": 0, "is_reserve_stamina_full": False}},
        "challenge": {"retcode": 0, "data": {
            "has_data": False, "name": "忘却之庭", "schedule_id": 1,
            "star_num": 0, "max_floor": "", "max_floor_id": 0,
            "battle_num": 0, "all_floor_detail": [], "groups": [],
            "begin_time": {"year": 2026, "month": 1, "day": 1,
                           "hour": 0, "minute": 0},
            "end_time": {"year": 2026, "month": 12, "day": 31,
                         "hour": 0, "minute": 0}}},
    }

    class _S(_FakeSession):
        pass

    import hsr_nous.account.transport as tp
    monkey_s = _S(payloads)
    from curl_cffi import requests as cffi
    orig = cffi.Session
    try:
        cffi.Session = lambda **k: monkey_s  # type: ignore[assignment]
        detail, notes, challenge = tp.fetch_starrail_records(
            100000001, {"ltuid": "1", "ltoken": "t"},
            device_id="D", device_fp="F")
    finally:
        cffi.Session = orig  # type: ignore[assignment]

    assert detail.avatar_list == []
    assert notes.current_stamina == 160
    assert challenge.has_data is False
    endpoints = [c["url"].rsplit("/api/", 1)[1] for c in monkey_s.calls]
    assert endpoints == ["avatar/info", "note", "challenge"]


# ----------------------------------------------------------------- 选择器


def _fake_genshin_client(uid=80000001):
    return SimpleNamespace(uid=uid, custom_headers={"x-rpc-device_id": "D",
                                                    "x-rpc-device_fp": "F"})


def test_fetch_snapshot_prefers_transport(monkeypatch):
    detail = SimpleNamespace(avatar_list=[])
    notes = SimpleNamespace(current_stamina=240)
    challenge = SimpleNamespace(has_data=False)

    seen = {}

    def fake_fetch(uid, cookies, **kw):
        seen.update(uid=uid, cookies=cookies, kw=kw)
        return detail, notes, challenge

    monkeypatch.setattr(transport, "available", lambda: True)
    monkeypatch.setattr(transport, "fetch_starrail_records", fake_fetch)
    monkeypatch.setattr(client_mod, "_read_secret", lambda k: f"v_{k}")

    snap = asyncio.run(client_mod._fetch_snapshot(_fake_genshin_client()))
    assert snap.uid == "80000001" and snap.trailblaze_power == 240
    assert seen["uid"] == 80000001
    assert seen["cookies"] == {"ltuid": "v_HSR_NOUS_HOYO_LTUID",
                               "ltoken": "v_HSR_NOUS_HOYO_LTOKEN"}
    assert seen["kw"]["device_id"] == "D" and seen["kw"]["device_fp"] == "F"


def test_fetch_snapshot_legacy_fallback(monkeypatch):
    class _Legacy:
        uid = 80000001
        custom_headers: dict = {}

        async def get_game_accounts(self):
            raise AssertionError("uid 已给不该查账号列表")

        async def get_starrail_characters(self, uid=None, **k):
            return SimpleNamespace(avatar_list=())

        async def get_starrail_notes(self, uid=None, **k):
            return SimpleNamespace(current_stamina=42)

        async def get_starrail_challenge(self, uid=None, **k):
            return SimpleNamespace(has_data=False)

    monkeypatch.setattr(transport, "available", lambda: False)
    snap = asyncio.run(client_mod._fetch_snapshot(_Legacy()))
    assert snap.trailblaze_power == 42


def test_fetch_snapshot_uid_resolution_still_via_genshin(monkeypatch):
    """uid 缺省时的账号列表解析仍走 genshin（该接口不触发风控，无需换传输）。"""
    detail = SimpleNamespace(avatar_list=[])
    notes = SimpleNamespace(current_stamina=1)
    challenge = SimpleNamespace(has_data=False)

    class _NoUid:
        uid = None
        custom_headers: dict = {}

        async def get_game_accounts(self):
            return [SimpleNamespace(game_biz="hkrpg_cn", uid=111, nickname="x",
                                    level=5)]

    monkeypatch.setattr(transport, "available", lambda: True)
    monkeypatch.setattr(transport, "fetch_starrail_records",
                        lambda uid, cookies, **k: (detail, notes, challenge))
    monkeypatch.setattr(client_mod, "_read_secret", lambda k: "v")
    snap = asyncio.run(client_mod._fetch_snapshot(_NoUid()))
    assert snap.uid == "111" and snap.nickname == "x" and snap.level == 5


def test_get_uses_explicit_region(monkeypatch):
    """显式 region 必须同时控制端点和 DS，不得被默认国服覆盖。"""
    import genshin

    monkeypatch.setattr(transport._routes.RECORD_URL, "get_url",
                        lambda region, game: f"https://{region.name.lower()}.example")
    monkeypatch.setattr(transport._utility.ds, "get_ds_headers",
                        lambda region, params: {"x-region": region.name})
    sess = _FakeSession({"note": {"retcode": 0, "data": {}}})
    transport._get(sess, "note", 100000001, {"ltuid": "1"}, {}, None, 30,
                   region=genshin.Region.OVERSEAS)
    call = sess.calls[0]
    assert call["url"] == "https://overseas.example/note"
    assert call["headers"]["x-region"] == "OVERSEAS"


def test_fetch_snapshot_passes_region_to_transport(monkeypatch):
    """国际服配置必须传入 transport，不得只在 genshin 客户端侧生效。"""
    import genshin

    detail = SimpleNamespace(avatar_list=[])
    notes = SimpleNamespace(current_stamina=240)
    challenge = SimpleNamespace(has_data=False)
    seen = {}

    def fake_fetch(uid, cookies, **kw):
        seen.update(kw)
        return detail, notes, challenge

    monkeypatch.setenv("HSR_NOUS_HOYO_SERVER", "os_asia")
    monkeypatch.setattr(transport, "available", lambda: True)
    monkeypatch.setattr(transport, "fetch_starrail_records", fake_fetch)
    monkeypatch.setattr(client_mod, "_read_secret", lambda k: "v")
    asyncio.run(client_mod._fetch_snapshot(_fake_genshin_client()))
    assert seen["region"] == genshin.Region.OVERSEAS
