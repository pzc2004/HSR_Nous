"""oracle_report 对拍报告节点（打标 DAG v3 报告型闸）单测 + DAG 集成.

覆盖：场景生成器（与对方 defaults/手摆场景等价）/ 金样角色比值全等 0 异常 /
已知结构差异常检出（D1 战技 HP≥50% ×1.45）/ 降级三态（对方未覆盖/缺 node）/
DAG 端到端（1013 黑塔：golden 过闸自动对拍 → finalize 挂异常数 + notes 附录）。

node/optimizer 依赖走 test_crosscheck_optimizer 的 optimizer_driver fixture
（缺环境整模块 skip 的降级模式照搬——本模块对拍行用例全部挂该 fixture）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsr_nous.ops.annotator import FakeRunner, run_character
from hsr_nous.ops.annotator.oracle_report import build_scenarios, generate_report
from tests.test_crosscheck_optimizer import optimizer_driver  # noqa: F401
from tests.test_crosscheck_characters import _opt_herta

ROOT = Path(__file__).resolve().parents[1]
HERTA_TPL = (ROOT / "tests/fixtures/templates/characters/1013_黑塔.yaml").read_text(
    encoding="utf-8")

#: 黑塔官方包（base_stats=终审白值——手摆场景 _opt_herta 同值，等价性断言零浮点差）
_HERTA_OFFICIAL = {
    "name_cn": "黑塔", "element": "Ice", "path": "Mage",
    "base_stats": {"hp": 952.56, "atk": 582.12, "def": 396.9, "spd": 100,
                   "crit_rate": 0.05, "crit_dmg": 0.5},
}

#: 全中性钉（手摆场景 _opt_herta 同套——映射表见 test_crosscheck_characters docstring）
_NEUTRAL_PINS = {"fuaStacks": 1, "techniqueBuff": False, "targetFrozen": False,
                 "enemyHpGte50": False, "enemyHpLte50": False,
                 "e2TalentCritStacks": 0, "e6UltAtkBuff": True}


# ---------------------------------------------------------------------------
# 场景生成器（不依赖 node——纯函数）
# ---------------------------------------------------------------------------

def test_scenarios_match_hand_built():
    """生成器口径 == 手摆场景（_opt_herta）：动作集/面板钉死/假人/无队友装备逐项相等."""
    import yaml

    doc = yaml.safe_load(HERTA_TPL)
    rows = build_scenarios(doc, _HERTA_OFFICIAL, conditionals=_NEUTRAL_PINS)
    got = {r["opt_action"]: r["scenario"] for r in rows if "scenario" in r}
    assert set(got) == {"basic", "skill", "ult"}, "核心三行动块全覆盖"
    for action in ("basic", "skill", "ult"):
        assert got[action] == _opt_herta(action), f"{action} 场景与手摆逐键相等"


def test_scenarios_skip_unreachable_action_types():
    """follow_up/忆灵技/assist 自动场景不可达 → skipped 行（不静默消失）."""
    doc = {"actor_id": "9999", "path": "erudition", "element": "ice",
           "actions": [
               {"action_id": "999901", "action_type": "basic"},
               {"action_id": "999902", "action_type": "follow_up"},
               {"action_id": "999903", "action_type": "memosprite_skill"},
               {"action_id": "999904", "action_type": "assist"}]}
    rows = build_scenarios(doc, _HERTA_OFFICIAL)
    skipped = [r for r in rows if r.get("status") == "skipped"]
    assert [r["action_id"] for r in skipped] == ["999902", "999903", "999904"]
    assert all("scenario" not in r for r in skipped)
    assert len([r for r in rows if "scenario" in r]) == 1


# ---------------------------------------------------------------------------
# 报告生成（金样 0 异常 / 异常检出 / 降级——依赖 node driver）
# ---------------------------------------------------------------------------

def test_golden_herta_zero_anomalies(optimizer_driver, tmp_path):  # noqa: F811
    """金样：全中性钉下黑塔核心三行动比值全等（ratio≈1）→ 0 异常."""
    s = generate_report("1013", HERTA_TPL, _HERTA_OFFICIAL, tmp_path,
                        conditionals=_NEUTRAL_PINS)
    assert s["status"] == "ok" and s["anomalies"] == 0 and s["compared"] == 3
    for r in s["rows"]:
        assert r["status"] == "ok", f"{r['action_id']} {r.get('note')}"
        assert r["ratio"] == pytest.approx(1.0, abs=1e-3)
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert report["conditionals_effective"]["enemyHpGte50"] is False, (
        "生效开关回显落报告（过堂判读口径）")


def test_anomaly_detected_known_divergence(optimizer_driver, tmp_path):  # noqa: F811
    """D1 结构差：敌方 HP≥50% 增伤（我方待收）——skill 行 anomaly 恰 ×1.45；
    threshold 可配：threshold=2.0 时同场 0 异常."""
    pins = {**_NEUTRAL_PINS, "enemyHpGte50": True}
    s = generate_report("1013", HERTA_TPL, _HERTA_OFFICIAL, tmp_path / "a",
                        conditionals=pins)
    assert s["status"] == "ok" and s["anomalies"] == 1
    row = next(r for r in s["rows"] if r["action_id"] == "101302")
    assert row["status"] == "anomaly" and row["ratio"] == pytest.approx(1.45, rel=1e-3)
    s2 = generate_report("1013", HERTA_TPL, _HERTA_OFFICIAL, tmp_path / "b",
                         conditionals=pins, threshold=2.0)
    assert s2["anomalies"] == 0, "阈值放宽 → 同场不再标红（报告型闸不硬拦）"


def test_optimizer_not_covered_passthrough(optimizer_driver, tmp_path):  # noqa: F811
    """对方注册表查无此 id（万敌 1404 未覆盖）→ pass-through 标 optimizer_not_covered."""
    from tests._annotator_dogfood import TPL_1404_GOLDEN_CLEAN

    official_1404 = {"name_cn": "万敌", "element": "Imaginary", "path": "Warrior",
                     "base_stats": {"hp": 1552.32, "atk": 426.888, "def": 194.04,
                                    "spd": 100.0, "crit_rate": 0.05, "crit_dmg": 0.873}}
    s = generate_report("1404", TPL_1404_GOLDEN_CLEAN, official_1404, tmp_path)
    assert s["status"] == "optimizer_not_covered" and s["anomalies"] == 0
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert "对方注册表无 id" in report["note"]


def test_env_no_node_passthrough(tmp_path, monkeypatch):
    """缺 node/rolldown → env_no_node 降级不阻塞（不跑对拍不炸 DAG）."""
    from hsr_nous.ops.annotator import oracle_report

    monkeypatch.setattr(oracle_report, "ensure_driver", lambda: None)
    s = generate_report("1013", HERTA_TPL, _HERTA_OFFICIAL, tmp_path)
    assert s["status"] == "env_no_node" and s["anomalies"] == 0
    assert (tmp_path / "oracle_report.json").is_file(), "降级也落报告（留痕）"


# ---------------------------------------------------------------------------
# DAG 集成：单角色端到端（golden 过闸 → 自动对拍 → finalize 挂异常数）
# ---------------------------------------------------------------------------

def _fake_search(query, max_results):
    return [{"title": f"{query} 结果", "url": f"https://example.com/{abs(hash(query)) % 1000}",
             "snippet": "社区摘要"}]


def _fake_fetch(url, cap):
    return f"正文:{url}"


def test_dag_integration_oracle_report(optimizer_driver, tmp_path):  # noqa: F811
    """1013 黑塔端到端：draft 罐头=已验收 fixture → 三闸过 → oracle_report 自动执行
    → finalize 输出挂 oracle 元数据 + notes 附录 + runs 目录落报告全文."""
    llm = FakeRunner([("DSL YAML 模板", HERTA_TPL), ("证据笔记", "# 黑塔证据笔记\n")])
    out = run_character("1013", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                        runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "oracle_report" in out and "finalize" in out, "对拍节点在运行图且不阻塞 finalize"
    dp = out["oracle_report"]
    assert dp["status"] == "ok" and dp["compared"] == 3
    assert dp["anomalies"] >= 1, "对方 defaults 非中性（D1/D2 在案结构差）——异常如实标红"
    fin = out["finalize"]
    assert fin["oracle"]["status"] == "ok" and fin["oracle"]["anomalies"] == dp["anomalies"]
    assert Path(fin["oracle"]["report"]).is_file(), "报告全文落 run 目录"
    notes = (tmp_path / "staging" / "notes" / "1013.md").read_text(encoding="utf-8")
    assert "对拍报告" in notes and "对拍异常数" in notes, "候选包 notes 挂对拍摘要"
