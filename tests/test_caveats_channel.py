"""近似置信度通道（决策卡 #24）端到端钉：词表闸 / 编译产物聚合 / 结果附带 / B16 无关钉.

三层 + 边界：
① 模板 `caveats:` 机读键词表闸（合法编译过 / 未知 level 炸 / 缺 text 炸 / 非列表炸 /
   未知条目键炸——角色·光锥·遗器三模板同闸）；
② `CompiledEncounter.caveats` 聚合（模板件带 actor/ref/level 归属 + 编译器
   mechanic_chance 期望口径自动标注 `source="compiler"`；遗器仅激活套装聚合）；
③ 结果附带（montecarlo `summary["caveats"]` / `hsr-sim run` 输出末尾 / web
   state payload + 结果卡渲染块）与 B16 铁律钉（caveats 纯元数据——同 seed 两趟
   snapshot/summary 逐字段全等，数值零影响）。

真件锚：佩拉 1106「终结技/秘技 100% 基础概率按必挂」approx（人工策展在库）+
光锥 21015 `mechanic_chance($self.param_1)`（编译器自动标注来源）。
"""
from __future__ import annotations

import pytest
import yaml

from hsr_nous.sim import montecarlo as mc
from hsr_nous.sim.cli import main as cli_main
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


def _stage(**over):
    stage = {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
                     "max_toughness": 9999, "weakness": ["ice"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 400},
    }
    stage.update(over)
    return {"stage": stage}


def _pela_build(**over):
    """佩拉编队（1106 真模板 + inline 辅手）——over 深替换一层."""
    build = {
        "team": [
            {"character_template": "1106", "level": 80},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "ice",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        ],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]},
    }
    build.update(over)
    return {"build": build}


def _compile_with_tpl(monkeypatch, tpl_over, member=None):
    """内存角色模板编译（monkeypatch _load_template 单漏斗——所有模板种类同返）."""
    tpl = {
        "actor_id": "9999", "name": "测试员",
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
        "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "fire",
                     "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
        **tpl_over,
    }
    monkeypatch.setattr(BuildCompiler, "_load_template",
                        staticmethod(lambda kind, ref, *, roots, legacy=False: tpl))
    build = {"build": {"team": [member or {"character_template": "9999", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _stage())


# ---------------------------------------------------------------------------
# ① 词表闸（角色/光锥/遗器三模板同闸——编译期炸不静默吞）
# ---------------------------------------------------------------------------

class TestCaveatGate:
    def test_legal_entries_compile_and_normalize(self, monkeypatch):
        c = _compile_with_tpl(monkeypatch, {"caveats": [
            {"text": "  100% 基础概率按必挂写  ", "level": "approx", "mechanism": "999903"},
            {"text": "站位语义待实测", "level": "pending"}]})
        assert [x["text"] for x in c.caveats[:2]] == ["100% 基础概率按必挂写", "站位语义待实测"]
        assert c.caveats[0]["level"] == "approx" and c.caveats[0]["mechanism"] == "999903"
        assert c.caveats[1]["level"] == "pending" and "mechanism" not in c.caveats[1]
        assert all(x["source"] == "template" for x in c.caveats[:2])

    def test_unknown_level_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="caveats\\[0\\] 的 level 非法值 'maybe'"):
            _compile_with_tpl(monkeypatch, {"caveats": [{"text": "x", "level": "maybe"}]})

    def test_missing_text_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="缺 text"):
            _compile_with_tpl(monkeypatch, {"caveats": [{"level": "approx"}]})

    def test_non_list_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="caveats 须为列表"):
            _compile_with_tpl(monkeypatch, {"caveats": "待实测：站位"})

    def test_unknown_entry_key_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="含未知键 'severity'"):
            _compile_with_tpl(monkeypatch,
                              {"caveats": [{"text": "x", "level": "approx", "severity": "high"}]})

    def test_empty_text_rejected(self, monkeypatch):
        with pytest.raises(ValueError, match="缺 text"):
            _compile_with_tpl(monkeypatch, {"caveats": [{"text": "   ", "level": "pending"}]})

    def test_light_cone_template_same_gate(self, monkeypatch):
        lc_tpl = {"light_cone_id": "9999", "name": "测试锥",
                  "base_stats": {"hp": 100},
                  "caveats": [{"text": "x", "level": "guess"}]}
        monkeypatch.setattr(BuildCompiler, "_load_template",
                            staticmethod(lambda kind, ref, *, roots, legacy=False: lc_tpl))
        build = {"build": {"team": [{
            "inline": True, "actor_id": "hero", "name": "测试员", "level": 80,
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "fire",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
            "light_cone_template": "9999"}],
            "policy": {"name": "p", "action_rules": [
                {"condition": "true", "action": "basic", "priority": 0}]}}}
        with pytest.raises(ValueError, match="光锥模板 9999 caveats\\[0\\] 的 level 非法值"):
            compile_encounter(build, _stage())

    def test_relic_template_same_gate(self, monkeypatch):
        relic_tpl = {"relic_set_id": "999", "name": "测试套",
                     "caveats": [{"text": "x"}]}
        monkeypatch.setattr(BuildCompiler, "_load_template",
                            staticmethod(lambda kind, ref, *, roots, legacy=False: relic_tpl))
        build = {"build": {"team": [{
            "inline": True, "actor_id": "hero", "name": "测试员", "level": 80,
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "fire",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
            "relics": {"head": {"set_id": "999"}}}],
            "policy": {"name": "p", "action_rules": [
                {"condition": "true", "action": "basic", "priority": 0}]}}}
        with pytest.raises(ValueError, match="遗器套装模板 999 caveats\\[0\\] 的 level 非法值"):
            compile_encounter(build, _stage())


# ---------------------------------------------------------------------------
# ② 编译产物聚合（真 fixture：佩拉人工策展件 + 21015 编译器自动标注 + 遗器激活闸）
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_pela_template_caveats_present(self):
        c = compile_encounter(_pela_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        assert len(c.caveats) >= 3, "佩拉人工策展 caveats ≥3（卡 #24 验收口径）"
        approx = [x for x in c.caveats if x["level"] == "approx"]
        assert any(x["source"] == "template" and x["actor"] == "1106"
                   and x.get("mechanism") == "110603" and "必挂" in x["text"]
                   for x in approx), "100% 基础概率按必挂 approx 项（来源=模板）"
        assert all({"actor", "text", "level", "source", "ref"} <= set(x) for x in c.caveats)
        assert {x["level"] for x in c.caveats} <= {"approx", "pending"}

    def test_compiler_auto_annotation_mechanic_chance(self):
        """佩拉装备 21015（虚无锥——hook condition 含 mechanic_chance）：自动标注在场."""
        build = _pela_build()
        build["build"]["team"][0]["light_cone_template"] = "21015"
        c = compile_encounter(build, _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        auto = [x for x in c.caveats if x["source"] == "compiler"]
        assert any(x["level"] == "approx" and x.get("mechanism") == "mechanic_chance"
                   and x["actor"] == "1106" for x in auto), (
            "mechanic_chance 期望件自动标注在场（来源=compiler，归属=装备者）")
        # 光锥模板 caveats（21015 提取件）同聚合，ref 指路
        assert any(x["source"] == "template" and x["ref"] == "light_cones/21015"
                   for x in c.caveats)

    def test_relic_caveats_only_when_set_active(self):
        """遗器套装 caveats 仅激活（≥2pc）聚合：105 拳王 2pc 在场、1pc 不在场."""
        base = _pela_build()
        relic2 = {"head": {"set_id": "105"}, "body": {"set_id": "105"}}
        build2 = _pela_build()
        build2["build"]["team"][0]["relics"] = relic2
        c2 = compile_encounter(build2, _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        assert any(x["ref"] == "relics/105" for x in c2.caveats), "2pc 激活聚合"
        base["build"]["team"][0]["relics"] = {"head": {"set_id": "105"}}
        c1 = compile_encounter(base, _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        assert not any(x["ref"] == "relics/105" for x in c1.caveats), "1pc 未激活不聚合"


# ---------------------------------------------------------------------------
# ③ 结果附带（montecarlo / CLI / web 三出口同显）+ B16 铁律钉
# ---------------------------------------------------------------------------

def _pela_factory(seed: int) -> CombatEngine:
    eng = CombatEngine.from_compiled(
        compile_encounter(_pela_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, seed=seed, initial_energy_ratio=0.0)
    return eng


class TestResultAttachment:
    def test_montecarlo_summary_caveats(self):
        res = mc.run(_pela_factory, n=3, seed0=0)
        cav = res.summary["caveats"]
        assert len(cav) >= 3, "佩拉编队 summary caveats ≥3（卡 #24 验收口径）"
        assert any(x["level"] == "approx" and "必挂" in x["text"]
                   and x["source"] == "template" for x in cav)
        assert all({"actor", "text", "level", "source"} <= set(x) for x in cav)

    def test_cli_run_lists_caveats(self, tmp_path, capsys):
        build_f = tmp_path / "build.yaml"
        stage_f = tmp_path / "stage.yaml"
        build_f.write_text(yaml.safe_dump(_pela_build(), allow_unicode=True), encoding="utf-8")
        stage_f.write_text(yaml.safe_dump(_stage(), allow_unicode=True), encoding="utf-8")
        assert cli_main(["run", str(build_f), str(stage_f)]) == 0
        out = capsys.readouterr().out
        assert "总伤害" in out and "caveats" in out, "run 输出末尾列 caveats 清单"
        assert "[近似]" in out and "必挂" in out, "必挂 approx 项同显（总伤旁不藏）"

    def test_web_state_payload_caveats(self):
        from fastapi.testclient import TestClient

        from hsr_nous.sim.web import create_app
        client = TestClient(create_app())
        r = client.post("/api/load", json={
            "build_yaml": yaml.safe_dump(_pela_build(), allow_unicode=True),
            "stage_yaml": yaml.safe_dump(_stage(), allow_unicode=True),
            "mode": "expected", "seed": None})
        assert r.status_code == 200, r.text
        s = client.get("/api/state").json()
        assert any(x["level"] == "approx" and "必挂" in x["text"]
                   for x in s["caveats"]), "web state payload 下发 caveats 清单"

    def test_web_result_card_renders_caveats_block(self):
        """结果卡（done-block）caveats 渲染块静态在场——防误删（node 逻辑闸不测 DOM 段）."""
        from pathlib import Path
        html = (Path(__file__).parent.parent
                / "src/hsr_nous/sim/web_static/index.html").read_text(encoding="utf-8")
        assert "done-caveats" in html and "S.caveats" in html


class TestB16Unaffected:
    def test_same_seed_snapshot_identical_with_caveats(self):
        """同 seed 两局 snapshot 逐字段全等（caveats 纯元数据——不进结算不改数值）."""
        def _snap():
            return _pela_factory(seed=7).run().snapshot()
        assert _snap() == _snap()

    def test_montecarlo_two_runs_summary_identical(self):
        """同 seed0 两趟实验 summary 逐字段全等——caveats 键同含且全等（B16 聚合层）."""
        r1 = mc.run(_pela_factory, n=3, seed0=7)
        r2 = mc.run(_pela_factory, n=3, seed0=7)
        assert r1.summary == r2.summary
        assert r1.summary["caveats"], "caveats 非空参与全等比对"
