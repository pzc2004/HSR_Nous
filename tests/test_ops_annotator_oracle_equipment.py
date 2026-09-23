"""装备分支 oracle_report 对拍报告节点（打标 DAG 装备版报告型闸）单测 + DAG 集成.

覆盖：装备场景生成器（与对拍战役手摆场景等价——LC 23007 黄泉载体/遗器 116 黑塔
载体）/ 金样装备比值全等 0 异常（LC 20000 锋镝×真理医生、遗器 116 系囚×黑塔）/
对方 defaults 非中性异常检出（23007 双开关默认 true——钉中性后归零）/
降级三态（装备未登记 optimizer_not_covered/无载体命途 no_carrier/缺 node
env_no_node）/ B1 id 映射（1006→1006b1 注册表覆盖 + 无映射 id 原样）/
DAG 端到端（20000 光锥/101 遗器：golden 过闸自动对拍 → finalize 挂异常数 +
notes 附录 + runs 目录落报告全文）。

node/optimizer 依赖走 test_crosscheck_optimizer 的 optimizer_driver fixture
（缺环境整模块 skip 的降级模式照搬——本模块对拍行用例全部挂该 fixture）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsr_nous.ops.annotator import FakeRunner, run_light_cone, run_relic
from hsr_nous.ops.annotator import oracle_report as oracle_mod
from hsr_nous.ops.annotator.equipment_nodes import (
    data_pull_lc_node,
    data_pull_relic_node,
)
from hsr_nous.ops.annotator.oracle_report import (
    OPT_B1_IDS,
    build_equipment_scenarios,
    build_scenarios,
    generate_equipment_report,
    generate_report,
)
from tests.test_crosscheck_optimizer import optimizer_driver  # noqa: F401
from tests.test_crosscheck_equipment import (  # noqa: F401
    AC_ATK,
    LC23007_ATK,
    _acheron_opt,
    _herta_opt,
)

ROOT = Path(__file__).resolve().parents[1]
LC23007_TPL = (ROOT / "tests/fixtures/templates/light_cones/23007_雨一直下.yaml").read_text(
    encoding="utf-8")
LC20000_TPL = (ROOT / "tests/fixtures/templates/light_cones/20000_锋镝.yaml").read_text(
    encoding="utf-8")
RELIC116_TPL = (ROOT / "tests/fixtures/templates/relics/116_幽锁深牢的系囚.yaml").read_text(
    encoding="utf-8")

#: 23007 对方 LC 开关中性钉（IncessantRain defaults 双 true 非中性——defaults 族
#: 异常检出样例；钉 false 后两侧同净板）
_LC23007_NEUTRAL = {"enemy3DebuffsCrBoost": False, "targetCodeDebuff": False}


# ---------------------------------------------------------------------------
# 场景生成器（不依赖 node——纯函数；与对拍战役手摆 builder 逐键对账）
# ---------------------------------------------------------------------------

def test_lc_scenarios_match_hand_built():
    """LC 23007（虚无→黄泉载体）：场景与先例 _acheron_opt 逐键对账——
    两处有意差注释在案：① base.hp/def=角色+光锥白值（driver 头注「base=白值
    （角色+光锥）」口径；先例 char-only 对 atk 系载体惰性）；② attacker 多
    effect_hit 0.24 钉（官方 properties 属性段——对方控制器不承载钉面板，
    先例未钉因无伤害消费；面板 parity 口径）。"""
    import yaml

    doc = yaml.safe_load(LC23007_TPL)
    official = data_pull_lc_node("23007").fn({})
    carrier = oracle_mod.equipment_carrier("light_cone", doc)
    assert carrier["cid"] == "1308"
    rows = build_equipment_scenarios("light_cone", "23007", doc, official, carrier=carrier)
    got = {r["opt_action"]: r["scenario"] for r in rows if "scenario" in r}
    assert set(got) == {"basic", "skill"}, "载体核心行动集（黄泉 ult 排除挡因见注册表注）"
    for action in ("basic", "skill"):
        hand = _acheron_opt(action, atk=AC_ATK + LC23007_ATK, equipment={"light_cone": {
            "id": "23007", "superimposition": 1, "path": "Nihility", "conditionals": {}}})
        sc = got[action]
        assert sc["kind"] == hand["kind"] and sc["character_id"] == hand["character_id"]
        assert sc["action"] == hand["action"] and sc["element"] == hand["element"]
        assert sc["conditionals"] == hand["conditionals"], "载体中性钉逐键相等"
        assert sc["self_path"] == hand["self_path"] and sc["enemy"] == hand["enemy"]
        assert sc["base"]["atk"] == pytest.approx(hand["base"]["atk"]), "白值 atk=角色+光锥（先例同口径）"
        assert sc["base"]["hp"] == pytest.approx(hand["base"]["hp"] + official["base_stats"]["hp"])
        assert sc["base"]["def"] == pytest.approx(hand["base"]["def"] + official["base_stats"]["def"])
        assert sc["base"]["spd"] == hand["base"]["spd"]
        for k in ("atk", "spd", "cr", "cd"):
            assert sc["attacker"][k] == pytest.approx(hand["attacker"][k]), f"attacker.{k}"
        for k in ("hp", "def"):
            assert sc["attacker"][k] == pytest.approx(
                hand["attacker"][k] + official["base_stats"][k]), (
                f"attacker.{k}=角色+光锥白值（driver 头注口径）")
        assert sc["attacker"]["effect_hit"] == 0.24, "属性段钉面板（S1 效果命中 24%）"
        assert sc["equipment"]["light_cone"]["id"] == "23007"
        assert sc["equipment"]["light_cone"]["path"] == "Nihility", "命途门控两侧同构"


def test_relic_scenarios_match_hand_built():
    """遗器 116（黑塔载体）：场景与先例 _herta_opt 逐键全等（遗器无光锥白值/
    属性段——base=角色白值，面板=白值零行迹，与先例 builder 零差）。"""
    import yaml

    doc = yaml.safe_load(RELIC116_TPL)
    official = data_pull_relic_node("116").fn({})
    carrier = oracle_mod.equipment_carrier("relic", doc)
    assert carrier["cid"] == "1013"
    rows = build_equipment_scenarios("relic", "116", doc, official, carrier=carrier)
    got = {r["opt_action"]: r["scenario"] for r in rows if "scenario" in r}
    assert set(got) == {"basic", "skill", "ult"}
    for action in ("basic", "skill", "ult"):
        hand = _herta_opt(action, equipment={"relic_sets": [
            {"id": "116", "pieces": 4, "conditionals": {}}]})
        assert got[action] == hand, f"{action} 场景与手摆逐键相等"


def test_carrier_selection_by_lc_path():
    """LC 按命途选载体（Warlock→黄泉/Rogue→真理）；遗器固定黑塔；无载体命途 → None."""
    import yaml

    assert oracle_mod.equipment_carrier(
        "light_cone", yaml.safe_load(LC23007_TPL))["cid"] == "1308"
    assert oracle_mod.equipment_carrier(
        "light_cone", yaml.safe_load(LC20000_TPL))["cid"] == "1305"
    assert oracle_mod.equipment_carrier(
        "relic", yaml.safe_load(RELIC116_TPL))["cid"] == "1013"
    assert oracle_mod.equipment_carrier("light_cone", {"path": "Shaman"}) is None


# ---------------------------------------------------------------------------
# 报告生成（金样 0 异常 / defaults 非中性检出 / 降级——依赖 node driver）
# ---------------------------------------------------------------------------

def test_golden_lc_zero_anomalies(optimizer_driver, tmp_path):  # noqa: F811
    """金样：20000 锋镝 S1×真理医生——对方 critBuff 默认 true 与我方开战钩
    对齐，basic/ult 比值全等 → 0 异常。"""
    official = data_pull_lc_node("20000").fn({})
    s = generate_equipment_report("light_cone", "20000", LC20000_TPL, official, tmp_path)
    assert s["status"] == "ok" and s["anomalies"] == 0 and s["compared"] == 2
    for r in s["rows"]:
        assert r["status"] == "ok", f"{r['action_id']} {r.get('note')}"
        assert r["ratio"] == pytest.approx(1.0, abs=1e-3)
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert report["carrier"]["cid"] == "1305", "载体回显落报告（过堂判读口径）"
    assert report["conditionals_effective"]["light_cone"] == {"critBuff": True}, (
        "LC 生效开关回显落报告")


def test_golden_relic_zero_anomalies(optimizer_driver, tmp_path):  # noqa: F811
    """金样：116 系囚 4pc×黑塔——2pc 攻击两侧各自原生通道，4pc 穿透档 0 对齐
    （0 DoT 净板），核心三行动比值全等 → 0 异常。"""
    official = data_pull_relic_node("116").fn({})
    s = generate_equipment_report("relic", "116", RELIC116_TPL, official, tmp_path)
    assert s["status"] == "ok" and s["anomalies"] == 0 and s["compared"] == 3
    for r in s["rows"]:
        assert r["status"] == "ok", f"{r['action_id']} {r.get('note')}"
        assert r["ratio"] == pytest.approx(1.0, abs=1e-3)
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert report["conditionals_effective"]["sets"] == {"valuePrisonerInDeepConfinement": 0}, (
        "套装生效开关回显落报告")


def test_lc_nonneutral_defaults_flagged(optimizer_driver, tmp_path):  # noqa: F811
    """defaults 非中性检出：23007 双开关默认 true（对方 +12% 暴击 +12% 承伤），
    我方净板无负面/挂码在后 → 各行 anomaly ≈×1.1856；lc_conditionals 钉中性后归零
    （报告型闸语义：defaults 与场景态差如实标红，过堂裁量）。"""
    official = data_pull_lc_node("23007").fn({})
    s = generate_equipment_report("light_cone", "23007", LC23007_TPL, official,
                                  tmp_path / "a")
    assert s["status"] == "ok" and s["anomalies"] == 2
    for r in s["rows"]:
        assert r["status"] == "anomaly"
        assert r["ratio"] == pytest.approx(1.0585 * 1.12, rel=1e-3), (
            "暴击档 1.085/1.025 × 承伤 1.12——对方 defaults 双开关结构差")
    s2 = generate_equipment_report("light_cone", "23007", LC23007_TPL, official,
                                   tmp_path / "b", lc_conditionals=_LC23007_NEUTRAL)
    assert s2["anomalies"] == 0, "中性钉后同场归零（装备逻辑层金样）"


def test_optimizer_not_covered_lc(optimizer_driver, tmp_path):  # noqa: F811
    """对方注册表查无此光锥（99999 假 id）→ pass-through 标 optimizer_not_covered."""
    official = data_pull_lc_node("20000").fn({})
    tpl = LC20000_TPL.replace("light_cone_id: '20000'", "light_cone_id: '99999'")
    s = generate_equipment_report("light_cone", "99999", tpl, official, tmp_path)
    assert s["status"] == "optimizer_not_covered" and s["anomalies"] == 0
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert "light cone not registered" in report["note"]


def test_no_carrier_passthrough(optimizer_driver, tmp_path):  # noqa: F811
    """LC 命途无载体（23003 同谐——_EQUIP_CARRIERS 未覆盖）→ no_carrier 不阻塞。"""
    tpl = (ROOT / "tests/fixtures/templates/light_cones/23003_但战斗还未结束.yaml").read_text(
        encoding="utf-8")
    official = data_pull_lc_node("23003").fn({})
    s = generate_equipment_report("light_cone", "23003", tpl, official, tmp_path)
    assert s["status"] == "no_carrier" and s["anomalies"] == 0
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert "无对拍载体" in report["note"]


def test_env_no_node_passthrough(tmp_path, monkeypatch):
    """缺 node/rolldown → env_no_node 降级不阻塞（不跑对拍不炸 DAG）。"""
    monkeypatch.setattr(oracle_mod, "ensure_driver", lambda: None)
    official = data_pull_lc_node("20000").fn({})
    s = generate_equipment_report("light_cone", "20000", LC20000_TPL, official, tmp_path)
    assert s["status"] == "env_no_node" and s["anomalies"] == 0
    assert (tmp_path / "oracle_report.json").is_file(), "降级也落报告（留痕）"


# ---------------------------------------------------------------------------
# B1 id 映射（我方现役 id → 对方加强版注册 id）
# ---------------------------------------------------------------------------

def test_b1_id_mapping_unit():
    """映射表纯函数：加强版 8 件全映射（1004/1005/1006/1205/1212/1217/1306/1310），
    场景 character_id 经映射；无映射 id（1102 希儿 stub 族）原样透传。"""
    assert OPT_B1_IDS == {"1004": "1004b1", "1005": "1005b1", "1006": "1006b1",
                          "1205": "1205b1", "1212": "1212b1", "1217": "1217b1",
                          "1306": "1306b1", "1310": "1310b1"}
    doc = {"actor_id": "1006", "path": "nihility", "element": "quantum",
           "actions": [{"action_id": "1100601", "action_type": "basic"}]}
    rows = build_scenarios(doc, {"base_stats": {"atk": 1, "hp": 1, "def": 1, "spd": 100}})
    assert rows[0]["scenario"]["character_id"] == "1006b1", "现役 id 经 B1 映射查询"
    doc2 = {"actor_id": "1102", "path": "hunt", "element": "quantum",
            "actions": [{"action_id": "110201", "action_type": "basic"}]}
    rows2 = build_scenarios(doc2, {"base_stats": {"atk": 1, "hp": 1, "def": 1, "spd": 100}})
    assert rows2[0]["scenario"]["character_id"] == "1102", "无映射 id 原样（stub 不拍）"


def test_b1_mapping_end_to_end(optimizer_driver, tmp_path):  # noqa: F811
    """1006 银狼：映射前=对方注册表查无（optimizer_not_covered）；映射后经
    1006b1 覆盖 → 对拍真跑（status ok + 映射回显落报告）。"""
    from hsr_nous.pipeline import calc_character_stats

    tpl = (ROOT / "tests/fixtures/templates/characters/1006_银狼.yaml").read_text(
        encoding="utf-8")
    official = {"name_cn": "银狼", "element": "Quantum", "path": "Warlock",
                "base_stats": calc_character_stats("1006", level=80, lang="cn")}
    s = generate_report("1006", tpl, official, tmp_path)
    assert s["status"] == "ok", "B1 映射后对方注册表覆盖（不再 optimizer_not_covered）"
    assert s["compared"] >= 1
    report = json.loads((tmp_path / "oracle_report.json").read_text(encoding="utf-8"))
    assert report["optimizer_character_id"] == "1006b1", "B1 映射回显落报告"


# ---------------------------------------------------------------------------
# DAG 集成：单装备端到端（golden 过闸 → 自动对拍 → finalize 挂异常数）
# ---------------------------------------------------------------------------

_LC_HOOKS_OK = """hooks:
  - event: "on_battle_start"
    effects:
      - effect_type: "apply_modifier"
        modifier:
          modifier_id: "LC_20000_CRIT"
          name: "锋镝暴击"
          modifier_type: "buff"
          duration: 3
          dispellable: false
          stack_mode: "replace"
          stat_effects:
            crit_rate: "$self.param_1"
"""

_RELIC_HOOKS_OK = """set_4pc:
  hooks:
    - event: "on_battle_start"
      effects:
        - effect_type: "gain_skill_point"
          amount: 1
"""


def _fake_llm(v_draft: str) -> FakeRunner:
    return FakeRunner([("的 hooks 块被闸门打回", v_draft), ("DSL hooks 块", v_draft),
                       ("输出证据笔记", "# 证据笔记\n")])


def _fake_search(query, max_results):
    return [{"title": f"{query} 结果", "url": f"https://example.com/{abs(hash(query)) % 1000}",
             "snippet": "社区摘要"}]


def _fake_fetch(url, cap):
    return f"正文:{url}"


def test_dag_integration_oracle_report_lc(optimizer_driver, tmp_path):  # noqa: F811
    """20000 光锥端到端：draft 罐头=开战暴击 hooks → 三闸过 → oracle_report 自动
    执行 → finalize 输出挂 oracle 元数据 + notes 附录 + runs 目录落报告全文."""
    out = run_light_cone("20000", llm=_fake_llm(_LC_HOOKS_OK), search_fn=_fake_search,
                         fetch_fn=_fake_fetch, runs_root=tmp_path / "runs",
                         staging_root=tmp_path / "staging")
    assert "oracle_report" in out and "finalize" in out, "对拍节点在运行图且不阻塞 finalize"
    dp = out["oracle_report"]
    assert dp["status"] == "ok" and dp["compared"] == 2 and dp["anomalies"] == 0, (
        "罐头 hooks 与对方 critBuff 默认对齐——金样零异常")
    fin = out["finalize"]
    assert fin["oracle"]["status"] == "ok" and fin["oracle"]["anomalies"] == 0
    assert Path(fin["oracle"]["report"]).is_file(), "报告全文落 run 目录"
    notes = (tmp_path / "staging" / "notes" / "20000.md").read_text(encoding="utf-8")
    assert "对拍报告" in notes and "对拍异常数" in notes, "候选包 notes 挂对拍摘要"


def test_dag_integration_oracle_report_relic(optimizer_driver, tmp_path):  # noqa: F811
    """101 遗器端到端：4pc 罐头 hooks（开战 +1 战技点——无伤害机制）→ 对拍三行动
    比值全等零异常 → finalize 挂 oracle 元数据。"""
    out = run_relic("101", llm=_fake_llm(_RELIC_HOOKS_OK), search_fn=_fake_search,
                    fetch_fn=_fake_fetch, runs_root=tmp_path / "runs",
                    staging_root=tmp_path / "staging")
    assert "oracle_report" in out and "finalize" in out
    dp = out["oracle_report"]
    assert dp["status"] == "ok" and dp["compared"] == 3 and dp["anomalies"] == 0
    fin = out["finalize"]
    assert fin["oracle"]["status"] == "ok"
    assert Path(fin["oracle"]["report"]).is_file()
    notes = (tmp_path / "staging" / "notes" / "101.md").read_text(encoding="utf-8")
    assert "对拍异常数" in notes
