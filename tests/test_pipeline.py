"""pipeline 加载和查询函数的单元测试."""

import math

import pytest
from pathlib import Path

from hsr_nous.pipeline import (
    load_characters,
    load_character_skills,
    load_character_skill_trees,
    load_character_promotions,
    load_character_ranks,
    load_light_cones,
    load_light_cone_promotions,
    load_relic_sets,
    load_relics,
    load_relic_main_affixes,
    load_relic_sub_affixes,
    load_properties,
    load_paths,
    load_elements,
    get_character,
    get_character_by_name,
    get_character_full,
    get_skill,
    get_skill_tree,
    get_promotion,
    get_rank,
    get_light_cone,
    get_light_cone_by_name,
    get_relic_set,
    get_relic,
    list_characters,
    list_light_cones,
    list_relic_sets,
    calc_character_stats,
    calc_light_cone_stats,
    get_skill_params,
    get_property_name,
    get_path_name,
    get_element_name,
)


DATA_DIR = str(Path(__file__).parent.parent / "data" / "starrailres")


# ---------------------------------------------------------------------------
# 数据加载测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestLoadFunctions:
    def test_load_characters(self):
        chars = load_characters(data_dir=DATA_DIR)
        assert "1001" in chars
        assert chars["1001"]["name"] == "March 7th"

    def test_load_character_skills(self):
        skills = load_character_skills(data_dir=DATA_DIR)
        assert len(skills) > 0
        assert "100101" in skills

    def test_load_character_skill_trees(self):
        trees = load_character_skill_trees(data_dir=DATA_DIR)
        assert len(trees) > 0

    def test_load_character_promotions(self):
        promos = load_character_promotions(data_dir=DATA_DIR)
        assert "1001" in promos

    def test_load_character_ranks(self):
        ranks = load_character_ranks(data_dir=DATA_DIR)
        assert len(ranks) > 0

    def test_load_light_cones(self):
        lcs = load_light_cones(data_dir=DATA_DIR)
        assert "20000" in lcs

    def test_load_relic_sets(self):
        sets = load_relic_sets(data_dir=DATA_DIR)
        assert len(sets) > 0

    def test_load_relics(self):
        relics = load_relics(data_dir=DATA_DIR)
        assert len(relics) > 0

    def test_load_elements(self):
        elements = load_elements(data_dir=DATA_DIR)
        assert "Ice" in elements

    def test_load_paths(self):
        paths = load_paths(data_dir=DATA_DIR)
        assert "Knight" in paths

    def test_load_properties(self):
        props = load_properties(data_dir=DATA_DIR)
        assert len(props) > 0


# ---------------------------------------------------------------------------
# 查询接口测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestQueryFunctions:
    def test_get_character(self):
        char = get_character("1001", data_dir=DATA_DIR)
        assert char is not None
        assert char["name"] == "March 7th"

    def test_get_character_not_found(self):
        char = get_character("99999", data_dir=DATA_DIR)
        assert char is None

    def test_get_character_by_name(self):
        char = get_character_by_name("March 7th", data_dir=DATA_DIR)
        assert char is not None
        assert char["id"] == "1001"

    def test_get_character_by_name_not_found(self):
        char = get_character_by_name("Nonexistent Character", data_dir=DATA_DIR)
        assert char is None

    def test_get_skill(self):
        skill = get_skill("100101", data_dir=DATA_DIR)
        assert skill is not None
        assert skill["name"] == "Frigid Cold Arrow"

    def test_get_skill_not_found(self):
        skill = get_skill("999999", data_dir=DATA_DIR)
        assert skill is None

    def test_get_skill_tree(self):
        trees = load_character_skill_trees(data_dir=DATA_DIR)
        tree_id = list(trees.keys())[0]
        tree = get_skill_tree(tree_id, data_dir=DATA_DIR)
        assert tree is not None

    def test_get_promotion(self):
        promo = get_promotion("1001", data_dir=DATA_DIR)
        assert promo is not None
        assert "values" in promo

    def test_get_rank(self):
        ranks = load_character_ranks(data_dir=DATA_DIR)
        rank_id = list(ranks.keys())[0]
        rank = get_rank(rank_id, data_dir=DATA_DIR)
        assert rank is not None

    def test_get_light_cone(self):
        lc = get_light_cone("20000", data_dir=DATA_DIR)
        assert lc is not None
        assert lc["name"] == "Arrows"

    def test_get_light_cone_by_name(self):
        lc = get_light_cone_by_name("Arrows", data_dir=DATA_DIR)
        assert lc is not None

    def test_get_relic_set(self):
        sets = load_relic_sets(data_dir=DATA_DIR)
        set_id = list(sets.keys())[0]
        rs = get_relic_set(set_id, data_dir=DATA_DIR)
        assert rs is not None

    def test_get_relic(self):
        relics = load_relics(data_dir=DATA_DIR)
        relic_id = list(relics.keys())[0]
        relic = get_relic(relic_id, data_dir=DATA_DIR)
        assert relic is not None

    def test_list_characters(self):
        chars = list_characters(data_dir=DATA_DIR)
        assert len(chars) > 0
        assert all(isinstance(c, tuple) and len(c) == 2 for c in chars)

    def test_list_light_cones(self):
        lcs = list_light_cones(data_dir=DATA_DIR)
        assert len(lcs) > 0

    def test_list_relic_sets(self):
        sets = list_relic_sets(data_dir=DATA_DIR)
        assert len(sets) > 0


# ---------------------------------------------------------------------------
# 完整数据组装测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestCharacterFull:
    def test_get_character_full(self):
        full = get_character_full("1001", data_dir=DATA_DIR)
        assert full is not None
        assert full["id"] == "1001"
        assert full["name"] == "March 7th"
        assert "skills_detail" in full
        assert "skill_trees_detail" in full
        assert "promotion" in full
        assert "ranks_detail" in full

    def test_get_character_full_not_found(self):
        full = get_character_full("99999", data_dir=DATA_DIR)
        assert full is None

    def test_skills_detail_populated(self):
        full = get_character_full("1001", data_dir=DATA_DIR)
        assert len(full["skills_detail"]) > 0
        assert all("name" in s for s in full["skills_detail"])

    def test_ranks_detail_populated(self):
        full = get_character_full("1001", data_dir=DATA_DIR)
        assert len(full["ranks_detail"]) == 6


# ---------------------------------------------------------------------------
# 属性计算测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestStatCalculation:
    def test_calc_character_stats(self):
        stats = calc_character_stats("1001", level=80, data_dir=DATA_DIR)
        assert "hp" in stats
        assert "atk" in stats
        assert "def" in stats
        assert "spd" in stats
        assert "crit_rate" in stats
        assert "crit_dmg" in stats
        assert stats["hp"] > 0
        assert stats["atk"] > 0

    def test_calc_character_stats_level1(self):
        stats = calc_character_stats("1001", level=1, data_dir=DATA_DIR)
        assert stats["hp"] > 0

    def test_calc_light_cone_stats(self):
        stats = calc_light_cone_stats("20000", level=80, data_dir=DATA_DIR)
        assert "hp" in stats
        assert "atk" in stats
        assert "def" in stats
        assert stats["hp"] > 0

    def test_calc_character_stats_invalid_id(self):
        with pytest.raises(ValueError, match="promotion data not found"):
            calc_character_stats("99999", data_dir=DATA_DIR)

    def test_calc_light_cone_stats_invalid_id(self):
        with pytest.raises(ValueError, match="promotion data not found"):
            calc_light_cone_stats("99999", data_dir=DATA_DIR)

    def test_calc_relic_affix_values(self):
        """A3：遗器词条数值查询（5★ 锚点：主 hp 705.6 / 副 spd 高档 2.6；主表无效果抵抗）."""
        from hsr_nous.pipeline import calc_relic_main_affix_values, calc_relic_sub_affix_values
        main = calc_relic_main_affix_values(data_dir=DATA_DIR)
        sub = calc_relic_sub_affix_values(data_dir=DATA_DIR)
        assert len(main) == 19 and len(sub) == 12
        assert "StatusResistanceBase" not in main  # 主词条无效果抵抗（编造值防线）
        assert math.isclose(main["HPDelta"], 705.6, abs_tol=1e-6)
        assert math.isclose(sub["SpeedDelta"], 2.6)
        assert math.isclose(sub["HPDelta"], 42.33752)


# ---------------------------------------------------------------------------
# 技能参数测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestSkillParams:
    def test_get_skill_params(self):
        params = get_skill_params("100101", level=1, data_dir=DATA_DIR)
        assert isinstance(params, list)
        assert len(params) > 0
        assert all(isinstance(p, (int, float)) for p in params)

    def test_get_skill_params_level10(self):
        params = get_skill_params("100101", level=10, data_dir=DATA_DIR)
        assert isinstance(params, list)

    def test_get_skill_params_invalid_id(self):
        with pytest.raises(ValueError, match="skill not found"):
            get_skill_params("999999", data_dir=DATA_DIR)


# ---------------------------------------------------------------------------
# 属性名称映射测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestNameMapping:
    def test_get_property_name(self):
        name = get_property_name("HealRatioBase", data_dir=DATA_DIR)
        assert isinstance(name, str)
        assert len(name) > 0

    def test_get_property_name_unknown(self):
        name = get_property_name("UnknownProp", data_dir=DATA_DIR)
        assert name == "UnknownProp"

    def test_get_path_name(self):
        name = get_path_name("Knight", data_dir=DATA_DIR)
        assert name == "Preservation"

    def test_get_path_name_unknown(self):
        name = get_path_name("UnknownPath", data_dir=DATA_DIR)
        assert name == "UnknownPath"

    def test_get_element_name(self):
        name = get_element_name("Ice", data_dir=DATA_DIR)
        assert name == "Ice"

    def test_get_element_name_unknown(self):
        name = get_element_name("UnknownElement", data_dir=DATA_DIR)
        assert name == "UnknownElement"


# ---------------------------------------------------------------------------
# 中文数据测试
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(DATA_DIR).exists(), reason="数据文件不存在")
class TestChineseData:
    @pytest.fixture(autouse=True)
    def skip_if_no_cn(self):
        cn_path = Path(__file__).parent.parent / "data" / "starrailres" / "index_new" / "cn"
        if not cn_path.exists():
            pytest.skip("中文数据不存在")

    def test_load_chinese_characters(self):
        chars = load_characters(data_dir=DATA_DIR, lang="cn")
        assert "1001" in chars
        assert chars["1001"]["name"] != "March 7th"  # 应该是中文名

    def test_get_chinese_character(self):
        char = get_character("1001", data_dir=DATA_DIR, lang="cn")
        assert char is not None
        assert isinstance(char["name"], str)
