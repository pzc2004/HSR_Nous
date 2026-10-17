"""账号真实词条值与光锥白值在编译器中的消费测试."""
from __future__ import annotations

from hsr_nous.account.showcase import _to_character
from hsr_nous.adapters.account_adapter import account_character_to_member
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim_schema.actor import StatBlock
from tests.test_account_showcase import _canned


def _member(tmp_path):
    root = tmp_path / "library"
    (root / "characters").mkdir(parents=True)
    (root / "light_cones").mkdir(parents=True)
    (root / "characters" / "1313_test.yaml").write_text("actor_id: '1313'\n", encoding="utf-8")
    (root / "light_cones" / "23049_test.yaml").write_text("light_cone_id: '23049'\n", encoding="utf-8")
    member, dropped = account_character_to_member(
        _to_character(_canned()["characters"][0]), library_root=root)
    assert dropped == []
    return member


def test_actual_relic_values_used_by_compiler(tmp_path):
    member = _member(tmp_path)
    out = BuildCompiler().apply_relics(StatBlock(), member["relics"])
    assert out["hp"] == 705.6
    assert out["hp_pct"] == 0.094
    assert out["spd"] == 2.6


def test_light_cone_base_stats_override(monkeypatch):
    compiler = BuildCompiler()
    monkeypatch.setattr(compiler, "_load_template",
                        lambda *args, **kwargs: {"base_stats": {"hp": 1, "atk": 2, "def": 3}})
    stats = StatBlock(hp=0.0, atk=0.0, def_=0.0, spd=0.0)
    spec = {
        "light_cone_template": "23049",
        "light_cone": {
            "superimposition": 1,
            "base_stats": {"hp": 11.0, "atk": 22.0, "def": 33.0},
        },
    }
    compiler._merge_light_cone(stats, spec, roots=[], actor_id="1313")
    assert stats.hp == 11.0 and stats.atk == 22.0 and stats.def_ == 33.0
