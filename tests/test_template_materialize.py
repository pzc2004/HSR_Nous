"""根注入钉死：根序优先级 / 生成根兜底 / 根内撞名炸 / 跨根不炸 / 生产默认不变.

loader（`BuildCompiler._load_template`）的 roots 由调用方注入：测试用
`TEST_TEMPLATE_ROOTS`（人工 fixtures 根优先于 data/ 生成根），生产缺省
`data/sim_templates`。历史 copy 物化机制已退役（见 tests/template_materialize.py
docstring），本文件钉死根注入语义，防"人工模板/生成器副本静默选边"复发
（1303/1403/1408 曾双文件同存）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from tests.template_materialize import (
    DATA_CHARS_DIR, FIXTURES_DIR, TEST_TEMPLATE_ROOTS, materialize_template)

_TPL = 'actor_id: "{aid}"\nname: "{name}"\nbase_stats: {{atk: 1000}}\nactions: []\n'


def _write(root, kind, fname, text):
    d = root / kind
    d.mkdir(parents=True, exist_ok=True)
    p = d / fname
    p.write_text(text, encoding="utf-8")
    return p


class TestRootInjection:
    """合成双根（tmp_path）：根序 / 兜底 / 根内撞名 / 跨根 / 零命中语义."""

    def test_root_order_priority(self, tmp_path):
        """根序优先级：同名引用 → 先命中根版生效；换序 → 另一版（人工根压生成根的机制底座）."""
        a, b = tmp_path / "a", tmp_path / "b"
        _write(a, "characters", "2001_x.yaml", _TPL.format(aid="2001", name="人工版"))
        _write(b, "characters", "2001_x.yaml", _TPL.format(aid="2001", name="生成版"))
        assert BuildCompiler._load_template("characters", "2001", roots=[a, b])["name"] == "人工版"
        assert BuildCompiler._load_template("characters", "2001", roots=[b, a])["name"] == "生成版"

    def test_fallback_to_later_root(self, tmp_path):
        """生成根兜底：前根无此 ID → 后根版生效（roots 是有序列表，非并集合并）."""
        a, b = tmp_path / "a", tmp_path / "b"
        _write(b, "characters", "2004_gen.yaml", _TPL.format(aid="2004", name="生成版"))
        tpl = BuildCompiler._load_template("characters", "2004", roots=[a, b])
        assert tpl["name"] == "生成版"

    def test_collision_within_root_explodes(self, tmp_path):
        """根内撞名炸：同一根放两份同 ID → 炸且报错带全部文件名（不许根内排序选边）."""
        a = tmp_path / "manual"
        _write(a, "characters", "2002_coll_a.yaml", 'actor_id: "2002"\n')
        _write(a, "characters", "2002_coll_b.yaml", 'actor_id: "2002"\n')
        with pytest.raises(ValueError, match=r"撞名.*2002_coll_a\.yaml.*2002_coll_b\.yaml"):
            BuildCompiler._load_template("characters", "2002", roots=[a])

    def test_cross_root_same_id_no_explosion(self, tmp_path):
        """跨根不炸：两版同 ID 分居两根 → 不抛，先命中根（人工位）版生效."""
        manual, gen = tmp_path / "manual", tmp_path / "gen"
        _write(manual, "characters", "2003_dup.yaml", _TPL.format(aid="2003", name="人工版"))
        _write(gen, "characters", "2003_dup.yaml", _TPL.format(aid="2003", name="生成版"))
        tpl = BuildCompiler._load_template("characters", "2003", roots=[manual, gen])
        assert tpl["name"] == "人工版"

    def test_not_found_lists_all_roots(self, tmp_path):
        """所有根零命中 → not-found 报错带查过的全部根路径."""
        a, b = tmp_path / "a", tmp_path / "b"
        with pytest.raises(FileNotFoundError) as ei:
            BuildCompiler._load_template("characters", "2099", roots=[a, b])
        assert "不存在" in str(ei.value)
        assert str(a) in str(ei.value) and str(b) in str(ei.value)

    def test_str_and_path_roots_accepted(self, tmp_path):
        """roots 元素 str/Path 均可."""
        _write(tmp_path, "characters", "2005_x.yaml", _TPL.format(aid="2005", name="路径件"))
        tpl = BuildCompiler._load_template("characters", "2005", roots=[str(tmp_path)])
        assert tpl["name"] == "路径件"


class TestTemplateRootsIntegration:
    """真实 TEST_TEMPLATE_ROOTS：人工根压制 + 生成根兜底 + 生产默认不变."""

    def test_manual_template_wins_via_test_roots(self):
        """1408 同名引用 → 人工 fixtures 版（hooks/eidolons 是人工全机制版指纹）."""
        tpl = BuildCompiler()._load_character_template("1408", roots=TEST_TEMPLATE_ROOTS)
        assert tpl["actor_id"] == "1408"
        assert "hooks" in tpl and "eidolons" in tpl, "应命中人工全机制版而非生成器副本"

    def test_data_root_fallback_for_unshadowed_id(self):
        """fixtures 无此 ID → data/ 生成根版兜底."""
        marker = DATA_CHARS_DIR / "9996_fallback.yaml"
        marker.write_text(_TPL.format(aid="9996", name="兜底件"), encoding="utf-8")
        try:
            tpl = BuildCompiler()._load_character_template("9996", roots=TEST_TEMPLATE_ROOTS)
            assert tpl["name"] == "兜底件"
        finally:
            marker.unlink(missing_ok=True)

    def test_production_default_root_unchanged(self):
        """生产默认不变：不传 template_roots → data/sim_templates 根（与写死时代行为一致）；
        loader 层无隐藏默认（roots 必填，调用方注入）."""
        marker = DATA_CHARS_DIR / "9995_prod.yaml"
        marker.write_text(
            'actor_id: "9995"\nname: "默认根件"\n'
            "base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}\n"
            "actions:\n"
            '  - action_id: "b"\n    name: "普攻"\n    action_type: "basic"\n'
            '    target_type: "single"\n    damage_type: "fire"\n'
            "    scaling: [{atk: 1.0}]\n    toughness_dmg: 10\n",
            encoding="utf-8")
        try:
            build = {"build": {"team": [{"character_template": "9995", "level": 80}],
                               "policy": {"name": "p", "action_rules": [
                                   {"condition": "true", "action": "basic", "priority": 0}]}}}
            stage = {"stage": {"stage_id": "s", "enemies": [
                {"actor_id": "e1", "name": "假人", "hp": 1e6, "spd": 100, "max_toughness": 30}],
                "termination": {"mode": "fixed_av", "max_action_value": 150}}}
            compiled = compile_encounter(build, stage)  # 不传 roots → 生产缺省
            assert compiled.build_team[0].actor_id == "9995"
            with pytest.raises(TypeError):
                BuildCompiler()._load_character_template("9995")  # loader 层 roots 必填
        finally:
            marker.unlink(missing_ok=True)

    def test_materialize_template_is_retired_noop(self):
        """copy 物化已退役：no-op 返回 fixtures 源路径，data/ 无人工版副本（生产根无人工版）."""
        assert materialize_template("1408_phainon.yaml") == (
            FIXTURES_DIR / "characters" / "1408_phainon.yaml")
        assert not (DATA_CHARS_DIR / "1408_phainon.yaml").exists()
