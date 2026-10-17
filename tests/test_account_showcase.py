"""展柜快照（account/showcase.py）测试——离线（_get_showcase_json 接缝打桩）。

钉 mihomo 词表映射（实读值 2026-10-17 在案）：
- path.id（开发名 Memory/Warrior…）→ AccountCharacter.path 词表；
- relic type=槽位 / main_affix+sub_affix（display 串）→ RelicStat；
- properties.display（"60.0%"/"705"）→ panel 浮点（与记录接口 _panel_value 同管线）；
- is_display=False → None（玩家未公开，不脑补）；网络失败 → None 不抛；
- 形状对拍：产出即 AccountSnapshot——消费方对来源无感。
"""
from __future__ import annotations

import pytest

import hsr_nous.account.showcase as showcase_mod
from hsr_nous.account import fetch_showcase_snapshot


def _canned() -> dict:
    return {
        "player": {"uid": "163476104", "nickname": "我要抽粉毛", "level": 70,
                   "is_display": True},
        "characters": [{
            "id": "1313", "name": "长夜月", "level": 80, "rank": 1, "rarity": 5,
            "path": {"id": "Memory", "name": "记忆"},
            "element": {"id": "Ice", "name": "冰"},
            "skills": [{"id": "141301", "name": "从此岁月朦胧", "level": 7,
                        "type": "Normal", "type_text": "普攻"}],
            "light_cone": {"id": "23049", "name": "致长夜的星光", "rarity": 5,
                           "rank": 1, "level": 80},
            "relics": [{
                "id": "61271", "name": "救世主的登程风帽", "type": 1, "set_id": "127",
                "rarity": 5, "level": 15,
                "main_affix": {"type": "HPDelta", "name": "生命值",
                               "value": 705.6, "display": "705", "percent": False},
                "sub_affix": [
                    {"type": "HPAddedRatio", "name": "生命值", "value": 0.047,
                     "display": "4.7%", "percent": True, "count": 2},
                    {"type": "SPDAddedRatio", "name": "速度", "value": 2.6,
                     "display": "2.6", "percent": False},
                ],
            }],
            "properties": [
                {"type": "CriticalChanceBase", "name": "暴击率", "value": 0.6007,
                 "display": "60.0%", "percent": True},
                {"type": "HPAddedRatio", "name": "生命值", "value": 8492.0,
                 "display": "8492", "percent": False},
            ],
            "attributes": [{"field": "hp", "name": "基础生命值", "value": 2483.7,
                            "display": "2483"}],
        }],
    }


def test_full_mapping(monkeypatch):
    monkeypatch.setattr(showcase_mod, "_get_showcase_json",
                        lambda uid, timeout=20.0: _canned())
    snap = fetch_showcase_snapshot("163476104")
    assert snap.uid == "163476104" and snap.nickname == "我要抽粉毛"
    assert snap.level == 70 and snap.trailblaze_power == 0 and snap.moc_records == ()

    c = snap.characters[0]
    assert c.id == "1313" and c.name == "长夜月" and c.level == 80
    assert c.eidolon == 1 and c.unlocked_eidolons == ()
    assert c.path == "Remembrance", "mihomo Memory→记录接口词表"
    assert c.element == "Ice"
    assert c.skill_levels == {"141301": 7}
    assert c.light_cone.name == "致长夜的星光" and c.light_cone.superimposition == 1
    assert c.has_memosprite is False

    relic = c.relics[0]
    assert relic.pos == 1 and relic.level == 15 and relic.rarity == 5
    assert relic.set_id == "127"
    assert relic.main.name == "HPDelta" and relic.main.value == "705.6"
    assert relic.subs[0].name == "HPAddedRatio"
    assert relic.subs[0].value == "0.047" and relic.subs[0].times == 2
    assert relic.subs[1].name == "SPDAddedRatio" and relic.subs[1].value == "2.6"

    assert c.panel["暴击率"] == pytest.approx(0.60, abs=1e-2)
    assert c.panel["生命值"] == pytest.approx(8492.0)


def test_all_known_path_ids_mapped():
    assert showcase_mod._map_path("Warrior") == "Destruction"
    assert showcase_mod._map_path("Shaman") == "Harmony"
    assert showcase_mod._map_path("Memory") == "Remembrance"


def test_unknown_path_passthrough(monkeypatch, caplog):
    import logging
    data = _canned()
    data["characters"][0]["path"] = {"id": "Joyous", "name": "欢愉"}
    monkeypatch.setattr(showcase_mod, "_get_showcase_json",
                        lambda uid, timeout=20.0: data)
    with caplog.at_level(logging.WARNING, logger="hsr_nous.account.showcase"):
        snap = fetch_showcase_snapshot("163476104")
    assert snap.characters[0].path == "Joyous", "未知命途透传不脑补"
    assert any("Joyous" in r.message for r in caplog.records)


def test_not_displayed_returns_none(monkeypatch):
    data = _canned()
    data["player"]["is_display"] = False
    monkeypatch.setattr(showcase_mod, "_get_showcase_json",
                        lambda uid, timeout=20.0: data)
    assert fetch_showcase_snapshot("163476104") is None


def test_network_failure_returns_none(monkeypatch):
    def boom(uid, timeout=20.0):
        raise OSError("down")
    monkeypatch.setattr(showcase_mod, "_get_showcase_json", boom)
    assert fetch_showcase_snapshot("163476104") is None


def test_empty_showcase_is_valid_snapshot(monkeypatch):
    monkeypatch.setattr(showcase_mod, "_get_showcase_json",
                        lambda uid, timeout=20.0: {"player": {"uid": uid},
                                                   "characters": []})
    snap = fetch_showcase_snapshot("163476104")
    assert snap.characters == () and snap.uid == "163476104"
