"""模板回读校验器测试：正例全量过 + 负例抓错.

正例：生成器产出的模板过校验器必须零差异（全量四类实体）。
负例：人为篡改字段必须被抓出（校验器本身不失明）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsr_nous.adapters import template_verifier as verifier
from hsr_nous.adapters.template_generator import (
    write_character_template, write_enemy_template,
    write_light_cone_template, write_relic_set_template,
)
from hsr_nous.pipeline.loader import list_characters, list_light_cones, list_relic_sets

from tests._data_env import data_available, data_skip_reason

pytestmark = pytest.mark.skipif(not data_available(), reason=data_skip_reason())


@pytest.fixture(scope="module")
def templates():
    """全量模板生成一次（module 级）."""
    for cid, _ in list_characters(lang="cn"):
        write_character_template(cid, level=80, lang="cn")
    for lid, _ in list_light_cones(lang="cn"):
        write_light_cone_template(lid, level=80, lang="cn")
    for sid, _ in list_relic_sets(lang="cn"):
        write_relic_set_template(sid, lang="cn")
    mv = json.loads(Path("data/stages/hakushin/monstervalue.json").read_text(encoding="utf-8"))
    for eid in mv:
        write_enemy_template(eid, level=80)
    return True


class TestVerifyPositive:
    def test_all_characters_pass(self, templates):
        bad = {cid: verifier.verify_character_template(cid)
               for cid, _ in list_characters(lang="cn")}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"角色模板校验失败：{dict(list(bad.items())[:3])}"

    def test_all_light_cones_pass(self, templates):
        bad = {lid: verifier.verify_light_cone_template(lid)
               for lid, _ in list_light_cones(lang="cn")}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"光锥模板校验失败：{dict(list(bad.items())[:3])}"

    def test_all_relic_sets_pass(self, templates):
        bad = {sid: verifier.verify_relic_set_template(sid)
               for sid, _ in list_relic_sets(lang="cn")}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"遗器模板校验失败：{dict(list(bad.items())[:3])}"

    def test_all_enemies_pass(self, templates):
        mv = json.loads(Path("data/stages/hakushin/monstervalue.json").read_text(encoding="utf-8"))
        bad = {eid: verifier.verify_enemy_template(eid) for eid in mv}
        bad = {k: v for k, v in bad.items() if v}
        assert not bad, f"敌人模板校验失败：{dict(list(bad.items())[:3])}"


class TestVerifyNegative:
    """校验器失明检查：篡改字段必须被抓."""

    def test_tampered_scaling_caught(self, templates, monkeypatch):
        real_load = verifier._load

        def fake_load(kind, ref, *, roots):
            tpl = real_load(kind, ref, roots=roots)
            tpl["actions"][0]["scaling"][0]["atk"] += 0.01  # 篡改一档倍率
            return tpl

        monkeypatch.setattr(verifier, "_load", fake_load)
        diffs = verifier.verify_character_template("1002")
        assert any("scaling" in d for d in diffs), f"篡改倍率未被抓：{diffs}"

    def test_tampered_target_type_caught(self, templates, monkeypatch):
        real_load = verifier._load

        def fake_load(kind, ref, *, roots):
            tpl = real_load(kind, ref, roots=roots)
            tpl["actions"][0]["target_type"] = "aoe"  # 篡改形态
            return tpl

        monkeypatch.setattr(verifier, "_load", fake_load)
        diffs = verifier.verify_character_template("1002")
        assert any("target_type" in d for d in diffs), f"篡改形态未被抓：{diffs}"

    def test_missing_lookup_column_caught(self, templates, monkeypatch):
        real_load = verifier._load

        def fake_load(kind, ref, *, roots):
            tpl = real_load(kind, ref, roots=roots)
            tpl.get("lookup_tables", {}).pop("param_2", None)  # 删掉一列
            return tpl

        monkeypatch.setattr(verifier, "_load", fake_load)
        diffs = verifier.verify_light_cone_template("23042")
        assert any("param_2" in d for d in diffs), f"删列未被抓：{diffs}"


class TestVerifyRootsInjection:
    """A1：模板根注入——verify_* 缺省读生产根，注入 fixtures 根时读注入根."""

    def test_default_reads_production_root(self, templates):
        """缺省 roots = DEFAULT_TEMPLATE_ROOTS：生成器产物零差异."""
        assert verifier.verify_character_template("1002") == []

    def test_injected_root_takes_precedence(self, templates, tmp_path):
        """注入根优先：篡改模板放注入根 → 被抓；同 ID 生产根模板不受影响."""
        import yaml as _yaml

        tpl = verifier._load("characters", "1002", roots=verifier.DEFAULT_TEMPLATE_ROOTS)
        tpl["base_stats"]["atk"] += 123.0  # 篡改面板锚点
        fake_dir = tmp_path / "characters"
        fake_dir.mkdir()
        (fake_dir / "1002_tampered.yaml").write_text(
            _yaml.safe_dump(tpl, allow_unicode=True), encoding="utf-8")

        diffs = verifier.verify_character_template("1002", roots=[str(tmp_path)])
        assert any("base_stats.atk" in d for d in diffs), f"注入根篡改未被抓：{diffs}"
        # 默认缓存/生产根不受注入影响
        assert verifier.verify_character_template("1002") == []

    def test_injected_roots_ordered_with_fallback(self, templates, tmp_path):
        """多根有序回退：注入根无此 ID → 落到生产根（与编译器根序语义一致）."""
        diffs = verifier.verify_character_template(
            "1002", roots=[str(tmp_path), *verifier.DEFAULT_TEMPLATE_ROOTS])
        assert diffs == []
