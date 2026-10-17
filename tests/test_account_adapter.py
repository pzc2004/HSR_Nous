"""账号快照到 build member 的适配测试."""
from __future__ import annotations

from hsr_nous.account.showcase import _to_character
from hsr_nous.adapters.account_adapter import account_character_to_member
from tests.test_account_showcase import _canned


def test_showcase_relic_affixes_and_set_id_reach_member(tmp_path):
    root = tmp_path / "library"
    (root / "characters").mkdir(parents=True)
    (root / "light_cones").mkdir(parents=True)
    (root / "characters" / "1313_test.yaml").write_text("actor_id: '1313'\n", encoding="utf-8")
    (root / "light_cones" / "23049_test.yaml").write_text("light_cone_id: '23049'\n", encoding="utf-8")

    character = _to_character(_canned()["characters"][0])
    member, dropped = account_character_to_member(character, library_root=root)

    assert dropped == []
    relic = member["relics"]["head"]
    assert relic["set_id"] == "127"
    assert relic["main"] == "hp"
    assert relic["main_value"] == 705.6
    assert relic["subs"] == {"hp_pct": 2, "spd": 1}
    assert relic["sub_values"] == {"hp_pct": 0.094, "spd": 2.6}

    from hsr_nous.pipeline.build.loader import calc_light_cone_stats
    expected = calc_light_cone_stats("23049", level=80)
    assert member["light_cone"]["base_stats"] == {
        "hp": expected["hp"], "atk": expected["atk"], "def_": expected["def"]
    }


def test_elemental_affix_uses_relic_id_not_panel_field():
    """元素增伤词条 ID 必须是 ice_dmg，而不是面板字段 dmg_ice。"""
    from hsr_nous.account.models import RelicStat
    from hsr_nous.adapters.account_adapter import _affix_id
    assert _affix_id(RelicStat("IceAddedRatio", "0.388803")) == "ice_dmg"
