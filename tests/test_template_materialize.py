"""物化机制钉死：fixtures 源 ↔ data 物化字节一致 + 物化后同 ID 唯一 + loader 撞名必炸.

防线对（见 tests/template_materialize.py docstring）：物化侧清同 ID 文件保唯一；
loader 侧（BuildCompiler._load_template）同 ID 双文件必炸报全名——两侧都钉死，
防"人工模板/生成器副本静默选边"复发（1303/1403/1408 曾双文件同存）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from tests.template_materialize import DATA_CHARS_DIR, FIXTURES_DIR, materialize_template

MANUAL_TEMPLATES = ("1303_ruan_mei.yaml", "1403_tribbie.yaml", "1408_phainon.yaml")


class TestMaterialize:
    @pytest.mark.parametrize("name", MANUAL_TEMPLATES)
    def test_materialized_copy_is_byte_identical(self, name):
        """copy 机制：data/ 物化副本与 fixtures 源字节一致（头注"勿直接改 data 副本"由一致性强约束）."""
        dst = materialize_template(name)
        assert dst.read_bytes() == (FIXTURES_DIR / name).read_bytes(), (
            f"{name} 物化副本与 fixtures 源不一致——改请改 fixtures 源文件再物化"
        )

    @pytest.mark.parametrize("name", MANUAL_TEMPLATES)
    def test_after_materialize_same_id_is_unique(self, name):
        """物化后同 entity ID 在 data/ 唯一（生成器副本被清，loader 撞名闸不会误伤手工模板）."""
        materialize_template(name)
        entity_id = name.split("_", 1)[0]
        hits = sorted(DATA_CHARS_DIR.glob(f"{entity_id}_*.yaml"))
        assert hits == [DATA_CHARS_DIR / name], f"同 ID 多文件残留：{hits}"


class TestLoaderCollision:
    def test_duplicate_id_files_explode_with_both_names(self):
        """loader 防线：同 ID 双文件必炸，报错带两个文件名（不许静默排序选边）."""
        a = DATA_CHARS_DIR / "9998_coll_a.yaml"
        b = DATA_CHARS_DIR / "9998_coll_b.yaml"
        DATA_CHARS_DIR.mkdir(parents=True, exist_ok=True)
        a.write_text('actor_id: "9998"\n', encoding="utf-8")
        b.write_text('actor_id: "9998"\n', encoding="utf-8")
        try:
            with pytest.raises(ValueError, match=r"撞名.*9998_coll_a\.yaml.*9998_coll_b\.yaml"):
                BuildCompiler._load_template("characters", "9998")
        finally:
            a.unlink(missing_ok=True)
            b.unlink(missing_ok=True)
