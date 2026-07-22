"""raw_schema 模型的单元测试."""

from hsr_nous.raw_schema import (
    Character,
    CharacterPromotion,
    CharacterRank,
    CharacterSkill,
    CharacterSkillTree,
    Element,
    LightCone,
    LightConePromotion,
    LightConeRank,
    HsrPath,
    Property,
    Relic,
    RelicSet,
    RelicMainAffix,
    RelicSubAffix,
)


# ---------------------------------------------------------------------------
# 模型测试
# ---------------------------------------------------------------------------


class TestCharacter:
    def test_from_dict(self):
        data = {
            "id": "1001",
            "name": "March 7th",
            "tag": "mar7th",
            "rarity": 4,
            "path": "Knight",
            "element": "Ice",
            "max_sp": 120,
            "skills": ["100101", "100102"],
            "skill_trees": ["1001001"],
            "ranks": ["100101"],
            "icon": "some_icon.png",
            "preview": "some_preview.png",
            "portrait": "some_portrait.png",
        }
        char = Character(data)

        assert char.id == "1001"
        assert char.name == "March 7th"
        assert char.tag == "mar7th"
        assert char.rarity == 4
        assert char.path == "Knight"
        assert char.element == "Ice"
        assert char.max_sp == 120
        assert char.skills == ["100101", "100102"]
        assert char.skill_trees == ["1001001"]
        assert char.ranks == ["100101"]
        assert char.icon == "some_icon.png"

    def test_missing_fields(self):
        char = Character({"id": "9999"})
        assert char.id == "9999"
        assert char.name == ""
        assert char.rarity == 0
        assert char.skills == []

    def test_to_dict(self):
        data = {"id": "1001", "name": "Test"}
        char = Character(data)
        assert char.to_dict() == data


class TestLightCone:
    def test_from_dict(self):
        data = {
            "id": "20000",
            "name": "Arrows",
            "rarity": 3,
            "path": "Rogue",
            "desc": "A basic light cone.",
            "icon": "icon.png",
            "preview": "preview.png",
            "portrait": "portrait.png",
        }
        lc = LightCone(data)

        assert lc.id == "20000"
        assert lc.name == "Arrows"
        assert lc.rarity == 3
        assert lc.path == "Rogue"
        assert lc.desc == "A basic light cone."


class TestRelicSet:
    def test_from_dict(self):
        data = {
            "id": "101",
            "name": "Passerby of Wandering Cloud",
            "desc": ["2-piece: ...", "4-piece: ..."],
            "properties": [[{"type": "HealRatioBase", "value": 0.1}]],
            "icon": "icon.png",
        }
        rs = RelicSet(data)

        assert rs.id == "101"
        assert rs.name == "Passerby of Wandering Cloud"
        assert len(rs.desc) == 2
        assert len(rs.properties) == 1


class TestRelic:
    def test_from_dict(self):
        data = {
            "id": "61011",
            "set_id": "101",
            "name": "Wandering Cloud Hat",
            "rarity": 5,
            "type": "HEAD",
            "max_level": 15,
            "main_affix_id": "1",
            "sub_affix_id": "1",
            "icon": "icon.png",
        }
        relic = Relic(data)

        assert relic.id == "61011"
        assert relic.set_id == "101"
        assert relic.type == "HEAD"
        assert relic.rarity == 5
        assert relic.max_level == 15


class TestCharacterSkill:
    def test_from_dict(self):
        data = {
            "id": "100101",
            "name": "Frigid Cold Arrow",
            "max_level": 6,
            "element": "Ice",
            "type": "Normal",
            "type_text": "Basic ATK",
            "effect": "SingleAttack",
            "effect_text": "Single Target",
            "simple_desc": "Deals Ice DMG...",
            "desc": "Deals Ice DMG equal to #1[i]%...",
            "params": [[0.5], [0.6]],
            "icon": "icon.png",
        }
        skill = CharacterSkill(data)

        assert skill.id == "100101"
        assert skill.type_text == "Basic ATK"
        assert skill.params == [[0.5], [0.6]]


class TestCharacterPromotion:
    def test_from_dict(self):
        data = {
            "id": "1001",
            "values": [
                {"hp": {"base": 100, "step": 10}, "atk": {"base": 50, "step": 5}}
            ],
            "materials": [[{"id": "1", "num": 4}]],
        }
        promo = CharacterPromotion(data)

        assert promo.id == "1001"
        assert len(promo.values) == 1
        assert promo.values[0]["hp"]["base"] == 100


class TestCharacterRank:
    def test_from_dict(self):
        data = {
            "id": "100101",
            "name": "Butterfly Flurry",
            "rank": 1,
            "desc": "When using Skill...",
            "materials": [],
            "level_up_skills": [],
            "icon": "icon.png",
        }
        rank = CharacterRank(data)

        assert rank.id == "100101"
        assert rank.rank == 1


class TestCharacterSkillTree:
    def test_from_dict(self):
        data = {
            "id": "1001001",
            "name": "ATK Boost",
            "max_level": 6,
            "desc": "ATK increases by...",
            "params": [0.02, 0.04],
            "anchor": "Point01",
            "pre_points": [],
            "level_up_skills": [],
            "levels": [],
            "icon": "icon.png",
        }
        tree = CharacterSkillTree(data)

        assert tree.id == "1001001"
        assert tree.anchor == "Point01"
        assert tree.params == [0.02, 0.04]


class TestLightConePromotion:
    def test_from_dict(self):
        data = {
            "id": "20000",
            "values": [{"hp": {"base": 50, "step": 5}, "atk": {"base": 25, "step": 3}}],
            "materials": [],
        }
        promo = LightConePromotion(data)

        assert promo.id == "20000"


class TestLightConeRank:
    def test_from_dict(self):
        data = {
            "id": "20000",
            "skill": "Arrow",
            "desc": "Increases ATK by #1[i]%",
            "params": [[0.08], [0.10]],
            "properties": [[{"type": "AttackAddedRatio", "value": 0.08}]],
        }
        rank = LightConeRank(data)

        assert rank.id == "20000"
        assert rank.skill == "Arrow"


class TestRelicAffix:
    def test_main_affix(self):
        data = {
            "id": "1",
            "affixes": {
                "1": {"affix_id": "1", "property": "HPDelta", "base": 100, "step": 50}
            },
        }
        affix = RelicMainAffix(data)

        assert affix.id == "1"
        assert "1" in affix.affixes

    def test_sub_affix(self):
        data = {
            "id": "1",
            "affixes": {
                "1": {
                    "affix_id": "1",
                    "property": "HPDelta",
                    "base": 50,
                    "step": 25,
                    "step_num": 1,
                }
            },
        }
        affix = RelicSubAffix(data)

        assert affix.id == "1"
        assert affix.affixes["1"]["step_num"] == 1


class TestElement:
    def test_from_dict(self):
        data = {
            "id": "Ice",
            "name": "Ice",
            "desc": "Freezes enemies.",
            "color": "#4FC1E9",
            "icon": "icon.png",
        }
        elem = Element(data)

        assert elem.id == "Ice"
        assert elem.color == "#4FC1E9"


class TestPath:
    def test_from_dict(self):
        data = {
            "id": "Knight",
            "text": "Preservation",
            "name": "Preservation",
            "desc": "Uses shields to protect allies.",
            "icon": "icon.png",
            "icon_middle": "mid.png",
            "icon_small": "small.png",
        }
        path = HsrPath(data)

        assert path.id == "Knight"
        assert path.text == "Preservation"


class TestProperty:
    def test_from_dict(self):
        data = {
            "type": "HPDelta",
            "name": "HP",
            "field": "hp",
            "affix": True,
            "ratio": False,
            "percent": False,
            "order": 1,
            "icon": "icon.png",
        }
        prop = Property(data)

        assert prop.type == "HPDelta"
        assert prop.affix is True
        assert prop.ratio is False

