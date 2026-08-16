"""红线过滤（redline）与关卡编成查询层（stages_loader）的测试.

红线是法律敏感逻辑——只保留已正式上线版本的数据，重点覆盖：
期数时间解析、未来期/占位期剔除、引用 id 收集与白名单过滤、版本对齐校验。
stages_loader 用 data/stages/ 真实快照做 smoke；网络访问一律 mock。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from hsr_nous.pipeline import extract_fandom_enemies, stages_loader, update, update_stages
from hsr_nous.pipeline.redline import (
    check_release_alignment,
    collect_referenced_ids,
    filter_entities,
    filter_phases,
    parse_version_time,
)

_STAGES_DIR = Path(__file__).parent.parent / "data" / "stages"
_ENEMIES_PATH = Path(__file__).parent.parent / "data" / "enemies" / "enemies.json"

_TODAY = date(2026, 7, 23)

needs_stages_snapshot = pytest.mark.skipif(
    not _STAGES_DIR.is_dir(), reason="data/stages/ 快照不存在"
)


# ---------------------------------------------------------------------------
# parse_version_time
# ---------------------------------------------------------------------------


def test_parse_version_time_normal():
    start, end = parse_version_time("14/07/2026 - 25/08/2026")
    assert start == date(2026, 7, 14)
    assert end == date(2026, 8, 25)


def test_parse_version_time_placeholder():
    assert parse_version_time("xx/xx/20xx - xx/xx/20xx") == (None, None)


def test_parse_version_time_abnormal():
    assert parse_version_time("") == (None, None)
    assert parse_version_time("26/04/2023 - PRESENT") == (None, None)
    assert parse_version_time("2026-07-14") == (None, None)
    assert parse_version_time("14/07/2026 - 32/08/2026") == (None, None)
    assert parse_version_time(None) == (None, None)


# ---------------------------------------------------------------------------
# filter_phases
# ---------------------------------------------------------------------------


def _phase(name: str, time_str: str) -> dict:
    return {"versionName": name, "versionTime": time_str}


def test_filter_phases_keeps_past_and_ongoing():
    versions = {
        "past": _phase("已结束", "01/01/2026 - 01/02/2026"),
        "ongoing": _phase("进行中", "14/07/2026 - 25/08/2026"),
    }
    kept, removed = filter_phases(versions, _TODAY)
    assert set(kept) == {"past", "ongoing"}
    assert removed == []


def test_filter_phases_removes_future():
    versions = {
        "ongoing": _phase("进行中", "14/07/2026 - 25/08/2026"),
        "future": _phase("未来期", "17/08/2026 - 28/09/2026"),
    }
    kept, removed = filter_phases(versions, _TODAY)
    assert set(kept) == {"ongoing"}
    assert removed == ["future"]


def test_filter_phases_removes_empty_name_placeholder():
    versions = {
        "ongoing": _phase("进行中", "14/07/2026 - 25/08/2026"),
        "placeholder": _phase("", "xx/xx/20xx - xx/xx/20xx"),
    }
    kept, removed = filter_phases(versions, _TODAY)
    assert set(kept) == {"ongoing"}
    assert removed == ["placeholder"]


def test_filter_phases_removed_order_and_content():
    versions = {
        "a": _phase("未来一", "01/09/2026 - 01/10/2026"),
        "b": _phase("进行中", "14/07/2026 - 25/08/2026"),
        "c": _phase("", "xx/xx/20xx - xx/xx/20xx"),
    }
    _kept, removed = filter_phases(versions, _TODAY)
    assert removed == ["a", "c"]


# ---------------------------------------------------------------------------
# collect_referenced_ids / filter_entities
# ---------------------------------------------------------------------------

_VERSIONS_SAMPLE = {
    "4.4.1": {
        "versionBuffIDs": ["40000021", "40000022"],
        # debuff 可能嵌套 list，且 id 带小数后缀
        "versionDebuffIDs": [["41000002", "41000004"], ["41000002.1", "41000004.2"]],
        "versionEnemies": {
            "sides": [
                {
                    "sideHPMult": 800,
                    "waves": [
                        {"enemies": [{"id": "31101", "count": 1}, {"id": "31100.1"}]},
                        {"enemies": [{"id": "35200", "phase": 1}]},
                    ],
                }
            ]
        },
    }
}


def test_collect_referenced_ids_enemies_from_waves_only():
    enemy_ids, _buff_ids = collect_referenced_ids(_VERSIONS_SAMPLE)
    assert enemy_ids == {"31101", "31100.1", "35200"}


def test_collect_referenced_ids_enemy_ids_keep_decimal_suffix():
    # "31100.1" 这类带小数后缀的 id 在 enemies.json 中是真实键，不能去后缀
    enemy_ids, _ = collect_referenced_ids(_VERSIONS_SAMPLE)
    assert "31100.1" in enemy_ids
    assert "31100" not in enemy_ids


def test_collect_referenced_ids_buffs_nested_and_suffix_stripped():
    _enemy_ids, buff_ids = collect_referenced_ids(_VERSIONS_SAMPLE)
    assert buff_ids == {"40000021", "40000022", "41000002", "41000004"}


def test_collect_referenced_ids_ignores_id_outside_waves():
    data = {"periods": [{"id": "not-an-enemy", "waves": [{"enemies": [{"id": "100"}]}]}]}
    enemy_ids, _ = collect_referenced_ids(data)
    assert enemy_ids == {"100"}


def test_filter_entities_whitelist():
    entities = {"31101": {"name": "A"}, "35200": {"name": "B"}, "99999": {"name": "C"}}
    kept, n_removed = filter_entities(entities, {"31101", "35200"})
    assert set(kept) == {"31101", "35200"}
    assert n_removed == 1


def test_filter_entities_empty_keep_removes_all():
    kept, n_removed = filter_entities({"1": {}, "2": {}}, set())
    assert kept == {}
    assert n_removed == 2


# ---------------------------------------------------------------------------
# check_release_alignment
# ---------------------------------------------------------------------------


def test_check_release_alignment():
    live = ["8001", "8002", "8003"]
    assert check_release_alignment(["8001", "8003"], live) == []
    assert check_release_alignment(["8001", "9999"], live) == ["9999"]
    assert check_release_alignment([8002, "9998"], live) == ["9998"]


# ---------------------------------------------------------------------------
# update_stages 占位期判定（纯函数）
# ---------------------------------------------------------------------------


def test_is_placeholder_detail():
    assert update_stages._is_placeholder_detail([{"name": "", "begin_time": None}])
    assert update_stages._is_placeholder_detail({"name": "", "begin_time": ""})
    assert not update_stages._is_placeholder_detail([{"name": "X", "begin_time": None}])
    assert not update_stages._is_placeholder_detail([{"name": "", "begin_time": 100}])
    assert not update_stages._is_placeholder_detail([])


# ---------------------------------------------------------------------------
# update 版本对齐校验（mock 网络）
# ---------------------------------------------------------------------------


def _mock_download(payloads: dict):
    def _download(url: str, timeout: float = 30.0) -> bytes:
        for key, payload in payloads.items():
            if key in url:
                return json.dumps(payload).encode("utf-8")
        raise AssertionError(f"未 mock 的 url: {url}")

    return _download


def test_check_release_alignment_warns_unreleased(tmp_path, monkeypatch):
    (tmp_path / "characters.json").write_text(
        json.dumps({"8001": {}, "9999": {}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        update,
        "download_file",
        _mock_download({
            "manifest.json": {"hsr": {"live": "4.4"}},
            "character.json": {"8001": {}, "8002": {}},
        }),
    )
    assert update._check_release_alignment(tmp_path, timeout=1.0) == ["9999"]


def test_check_release_alignment_never_raises(tmp_path, monkeypatch):
    def _boom(url: str, timeout: float = 30.0) -> bytes:
        raise OSError("network down")

    monkeypatch.setattr(update, "download_file", _boom)
    # 网络失败、本地文件缺失等任何异常都必须吞掉，返回空列表
    assert update._check_release_alignment(tmp_path, timeout=1.0) == []


# ---------------------------------------------------------------------------
# stages_loader smoke（真实快照）
# ---------------------------------------------------------------------------


@needs_stages_snapshot
def test_list_modes():
    assert stages_loader.list_modes() == ["moc", "pf", "as", "aa"]


@needs_stages_snapshot
def test_list_stages_moc_two_sources():
    stages = stages_loader.list_stages("moc", stages_dir=str(_STAGES_DIR))
    sources = {s["source"] for s in stages}
    assert sources == {"buhflipexplode", "hakushin"}
    buh = [s for s in stages if s["source"] == "buhflipexplode"]
    assert buh, "buh 源应有期数"
    for s in buh:
        assert s["id"] and isinstance(s["name"], str)
        assert isinstance(s["begin"], date) and isinstance(s["end"], date)


@needs_stages_snapshot
def test_list_stages_aa_buh_only():
    stages = stages_loader.list_stages("aa", stages_dir=str(_STAGES_DIR))
    assert stages and all(s["source"] == "buhflipexplode" for s in stages)


def _first_aa_key() -> str:
    data = json.loads(
        (_STAGES_DIR / "buhflipexplode" / "aa-versions.json").read_text(encoding="utf-8")
    )
    return next(iter(data))


@needs_stages_snapshot
def test_get_stage_buh_structure():
    key = _first_aa_key()
    stage = stages_loader.get_stage_buh("aa", key, stages_dir=str(_STAGES_DIR))
    assert stage["version_key"] == key
    assert stage["versionName"]
    assert stage["versionTime"]
    assert stage["buffs"] and {"id", "text"} <= set(stage["buffs"][0])
    assert stage["sides"] and "sideHPMult" in stage["sides"][0]
    # buff/debuff id 均已去小数后缀
    for buff in stage["buffs"] + stage["debuffs"]:
        assert "." not in buff["id"]


@needs_stages_snapshot
def test_compute_buh_enemies_hp_and_assumptions():
    key = _first_aa_key()
    enemies_table = json.loads(
        (_STAGES_DIR / "buhflipexplode" / "enemies.json").read_text(encoding="utf-8")
    )
    stage = stages_loader.get_stage_buh("aa", key, stages_dir=str(_STAGES_DIR))
    result = stages_loader.compute_buh_enemies(key, stages_dir=str(_STAGES_DIR))
    assert result, "结算结果不应为空"

    # 具体数值断言：第一个敌人的 HP 必须等于 baseHP × 其所在侧 sideHPMult
    first = result[0]
    expected_hp = round(
        enemies_table[first["id"]]["baseHP"] * stage["sides"][first["side"]]["sideHPMult"]
    )
    assert first["hp"] == expected_hp
    assert first["speed"] == enemies_table[first["id"]]["baseSPD"]

    for foe in result:
        assert foe["level"] == 95 and foe["_level_assumption"] is True
        assert foe["attack"] is None and foe["defence"] is None
        assert foe["id"] in enemies_table


@needs_stages_snapshot
def test_get_stage_hakushin_structure():
    details_dir = _STAGES_DIR / "hakushin" / "details" / "maze"
    period_id = next(p.stem for p in sorted(details_dir.glob("*.json")))
    stage = stages_loader.get_stage_hakushin("moc", period_id, stages_dir=str(_STAGES_DIR))
    assert stage["period_id"] == period_id
    floor = stage["floors"][0]
    assert {"name", "desc", "param", "countdown", "damage_type", "sides"} <= set(floor)
    assert len(floor["damage_type"]) == 2
    event = floor["sides"][0][0]
    assert {"level", "elite_group", "hard_level_group", "monster_list"} <= set(event)


@needs_stages_snapshot
def test_get_enemy_detail_two_source_routing():
    enemies = json.loads(_ENEMIES_PATH.read_text(encoding="utf-8"))
    mv_path = _STAGES_DIR / "hakushin" / "monstervalue.json"
    mv_table = json.loads(mv_path.read_text(encoding="utf-8")) if mv_path.exists() else {}
    some_id = next(iter(enemies))

    detail = stages_loader.get_enemy_detail(some_id, enemies_path=str(_ENEMIES_PATH))
    assert detail is not None
    if some_id in mv_table:
        # hakushin 主源：base 数值，无技能表
        assert detail["_source"] == "hakushin"
        assert "HPBase" in detail
    else:
        assert detail["_source"] == "bowja_legacy" and detail["_stale"] is True

    # 主源文件缺失时强制回退 theBowja：技能/抗性表结构不变
    legacy = stages_loader.get_enemy_detail(
        some_id,
        enemies_path=str(_ENEMIES_PATH),
        monstervalue_path=str(_ENEMIES_PATH.parent / "nope.json"),
    )
    assert legacy["_source"] == "bowja_legacy" and legacy["_stale"] is True
    assert legacy["Id"] == int(some_id) or str(legacy["Id"]) == some_id
    assert "SkillList" in legacy and "ElementalResistance" in legacy
    assert stages_loader.get_enemy_detail("0", enemies_path=str(_ENEMIES_PATH)) is None


# ---------------------------------------------------------------------------
# monstervalue 加载 smoke（真实快照）
# ---------------------------------------------------------------------------

_MONSTERVALUE_PATH = _STAGES_DIR / "hakushin" / "monstervalue.json"

needs_monstervalue = pytest.mark.skipif(
    not _MONSTERVALUE_PATH.exists(), reason="data/stages/hakushin/monstervalue.json 不存在"
)


@needs_monstervalue
def test_monstervalue_smoke():
    table = json.loads(_MONSTERVALUE_PATH.read_text(encoding="utf-8"))
    assert len(table) > 500, "monstervalue 应覆盖全部怪物"
    entry = table["1002011"]
    assert {
        "AttackBase", "DefenceBase", "HPBase", "SpeedBase",
        "StanceBase", "StatusResistanceBase",
    } <= set(entry)
    assert isinstance(entry["child"], list) and entry["child"]
    assert {"Id", "EliteGroup", "HPModifyRatio", "HardLevelGroup"} <= set(entry["child"][0])


# ---------------------------------------------------------------------------
# get_enemy_detail 双源路由（tmp 构造，离线）
# ---------------------------------------------------------------------------


def _write_monstervalue(tmp_path) -> Path:
    table = {
        "9001": {
            "Rank": "Boss",
            "AttackBase": 18,
            "DefenceBase": 210,
            "HPBase": 69.75,
            "SpeedBase": 100,
            "StanceBase": 240,
            "StatusResistanceBase": 0.3,
            "child": [
                {"Id": 9001, "EliteGroup": 1, "HPModifyRatio": 1, "HardLevelGroup": 1},
                {"Id": 900101, "EliteGroup": 2, "HPModifyRatio": 0.5, "HardLevelGroup": 3},
            ],
        },
    }
    path = tmp_path / "monstervalue.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def _write_bowja(tmp_path) -> Path:
    table = {
        "9001": {"Id": "9001", "Name": "双源怪", "SkillList": [], "ElementalResistance": {}},
        "7777": {"Id": "7777", "Name": "仅旧源怪", "SkillList": [], "ElementalResistance": {}},
    }
    path = tmp_path / "enemies.json"
    path.write_text(json.dumps(table), encoding="utf-8")
    return path


def test_enemy_detail_hakushin_primary(tmp_path):
    mv, bowja = _write_monstervalue(tmp_path), _write_bowja(tmp_path)
    detail = stages_loader.get_enemy_detail(
        "9001", enemies_path=str(bowja), monstervalue_path=str(mv)
    )
    assert detail["_source"] == "hakushin"
    assert "_stale" not in detail
    assert detail["HPBase"] == 69.75 and detail["StanceBase"] == 240
    assert "SkillList" not in detail


def test_enemy_detail_hakushin_child_lookup(tmp_path):
    mv, bowja = _write_monstervalue(tmp_path), _write_bowja(tmp_path)
    detail = stages_loader.get_enemy_detail(
        "900101", enemies_path=str(bowja), monstervalue_path=str(mv)
    )
    assert detail["_source"] == "hakushin"
    assert detail["parent_id"] == "9001"
    # 合并视图：父 base 数值 + 子修正系数
    assert detail["AttackBase"] == 18
    assert detail["HPModifyRatio"] == 0.5 and detail["HardLevelGroup"] == 3


def test_enemy_detail_bowja_fallback_stale(tmp_path):
    mv, bowja = _write_monstervalue(tmp_path), _write_bowja(tmp_path)
    detail = stages_loader.get_enemy_detail(
        "7777", enemies_path=str(bowja), monstervalue_path=str(mv)
    )
    assert detail["_source"] == "bowja_legacy" and detail["_stale"] is True
    assert detail["Name"] == "仅旧源怪"


def test_enemy_detail_missing_everywhere(tmp_path):
    mv, bowja = _write_monstervalue(tmp_path), _write_bowja(tmp_path)
    assert stages_loader.get_enemy_detail(
        "0", enemies_path=str(bowja), monstervalue_path=str(mv)
    ) is None
    # 两个文件都不存在也应返回 None（而非抛异常）
    assert stages_loader.get_enemy_detail(
        "9001",
        enemies_path=str(tmp_path / "nope1.json"),
        monstervalue_path=str(tmp_path / "nope2.json"),
    ) is None


# ---------------------------------------------------------------------------
# get_enemy_mechanics（tmp 构造，离线）
# ---------------------------------------------------------------------------


def test_get_enemy_mechanics(tmp_path):
    path = tmp_path / "fandom_enemy_data.json"
    path.write_text(json.dumps({
        "Foo the Bar": {"tier": "Boss", "skills": [], "_page_title": "Foo the Bar"},
        "_meta": {"count": 1},
    }), encoding="utf-8")
    rec = stages_loader.get_enemy_mechanics("Foo the Bar", fandom_enemy_path=str(path))
    assert rec is not None and rec["tier"] == "Boss"
    assert stages_loader.get_enemy_mechanics("Nope", fandom_enemy_path=str(path)) is None


def test_get_enemy_mechanics_file_missing(tmp_path):
    # 文件不存在返回 None——需先跑 pipeline/extract_fandom_enemies.py
    assert stages_loader.get_enemy_mechanics(
        "Foo", fandom_enemy_path=str(tmp_path / "nope.json")
    ) is None


# ---------------------------------------------------------------------------
# extract_fandom_enemies 模板解析（fixture wikitext，离线）
# ---------------------------------------------------------------------------

_ENEMY_WIKITEXT = """\
{{Enemy Infobox
|image    = Enemy Borisin Warhead: Hoolay.png
|tier     = Boss
|type     = Lightning
|weakness = Physical;Fire;Wind
|tough    = 240 (Normal)<br />200 (''[[Comrade in Arms]]'' only)
|faction  = The Xianzhou Luofu
|location =
|ability  = Moon Rage; Terror Grip; Control Effects to Player
}}
'''Borisin Warhead: Hoolay''' is a [[Boss Enemy]].

==Stats==
{{Enemy Stats
|ice_res       = 0.2
|lightning_res = 0.2

|frozen_res       = 0.75
|imprisonment_res = 0.75

|hp   = 2557.5
|spd  = 200
|eres = 0.2
}}
===Story===
{{Enemy Stats
|ice_res       = 0.2

|hp   = 2790
|spd  = 172
|eres = 0.2
}}

==Skills==
{{Enemy Skills
|enemy = Borisin Warhead Hoolay

|name1      = Broken Blades as Fang
|type1      = Single Target
|desc1      = Deals Lightning DMG ('''200% ATK''') to a single target.
|energy1    = 10
|caption1   = Normal
|file1_2    = Borisin Warhead Hoolay Broken Blades as Fang 2
|phase1     = 1,2

|name2      = Barrenness of Earth
|type2      = AoE ATK
|desc2      = Deals massive {{Color|h|Lightning}} DMG ('''570% ATK''') to all targets.
|phase2     = 2
|danger2    = 1
}}
"""


def test_parse_enemy_infobox():
    info = extract_fandom_enemies.parse_enemy_infobox(_ENEMY_WIKITEXT)
    assert info["tier"] == "Boss"
    assert info["attack_element"] == "Lightning"
    assert info["weaknesses"] == ["Physical", "Fire", "Wind"]
    assert info["faction"] == "The Xianzhou Luofu"
    assert info["abilities"] == ["Moon Rage", "Terror Grip", "Control Effects to Player"]
    # tough 多变体：主值 240，注记保留
    assert info["toughness"] == 240
    assert "200" in info["toughness_detail"]
    assert "Comrade in Arms" in info["toughness_detail"]


def test_parse_tough_plain_and_empty():
    assert extract_fandom_enemies._parse_tough("150") == (150, None)
    assert extract_fandom_enemies._parse_tough("") == (None, None)
    main, detail = extract_fandom_enemies._parse_tough("60 ×3 (Phase 1/2)<br />36 ×9 (Phase 3)")
    assert main == 60
    assert "36 ×9 (Phase 3)" in detail


def test_parse_enemy_stats_main_and_variant():
    stats, variants = extract_fandom_enemies.parse_enemy_stats(_ENEMY_WIKITEXT)
    assert stats["ice_res"] == 0.2 and stats["hp"] == 2557.5
    assert stats["spd"] == 200 and stats["frozen_res"] == 0.75
    assert len(variants) == 1
    assert variants[0]["variant"] == "Story"
    assert variants[0]["hp"] == 2790 and variants[0]["spd"] == 172
    # 变体未声明的抗性字段不补默认值
    assert "fire_res" not in stats and "fire_res" not in variants[0]


def test_parse_enemy_skills():
    skills = extract_fandom_enemies.parse_enemy_skills(_ENEMY_WIKITEXT)
    assert len(skills) == 2
    s1, s2 = skills
    assert s1["name"] == "Broken Blades as Fang"
    assert s1["type"] == "Single Target"
    assert "200% ATK" in s1["desc"] and "'''" not in s1["desc"]
    assert s1["energy"] == 10 and isinstance(s1["energy"], int)
    assert s1["phase"] == "1,2" and s1["caption"] == "Normal"
    assert s2["danger"] is True and s2["phase"] == "2"
    assert "570% ATK" in s2["desc"]
    # {{Color|h|Lightning}} 取展示文本
    assert "Lightning" in s2["desc"] and "{{" not in s2["desc"]


def test_parse_enemy_page_full_and_empty():
    rec = extract_fandom_enemies.parse_enemy_page(_ENEMY_WIKITEXT)
    assert rec["tier"] == "Boss"
    assert rec["stats"]["hp"] == 2557.5
    assert len(rec["stats_variants"]) == 1
    assert len(rec["skills"]) == 2
    # 只有 lore 散文、无三个目标模板的页面返回 {}（调用方记 _meta.failed）
    assert extract_fandom_enemies.parse_enemy_page("'''Foo''' is an enemy.") == {}
    assert extract_fandom_enemies.parse_enemy_page("") == {}
