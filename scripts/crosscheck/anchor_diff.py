#!/usr/bin/env python3
"""锚三对拍：LLM 标注版 vs 人工锚版——同 build/stage/seed 行为对比（可重复跑）.

- A 组（LLM 标注版）：template_roots = ["data/sim_templates"]
- B 组（人工锚版）：template_roots = ["tests/fixtures/templates", "data/sim_templates"]
  （fixtures 压制锚角色本身，队友/敌人/其余解析两组一致）
- 每锚同一 build/stage/policy/seed：锚 + 2 inline 假人队友（产点） vs inline 全弱点木桩
  （敌人行动 setup 后注入——stage inline 不支持 actions 键，同 tests/test_phainon_full_kit 先例）
- 输出：stdout 人读摘要 + data/annotator/anchor_diff.json（--out 可覆盖）
- 预期差异分离：data/annotator/run_state.json 的 needs_primitive 按角色登记；
  差异明细命中其主题名 → [预期]，否则 [意外]（意外 = LLM 标注问题/引擎问题候选）
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from hsr_nous.sim.compile import compile_encounter  # noqa: E402
from hsr_nous.sim.engine import CombatEngine  # noqa: E402
from hsr_nous.sim.pipeline import MODE_EXPECTED  # noqa: E402
from hsr_nous.sim_schema.action import Action  # noqa: E402

LLM_ROOTS = ["data/sim_templates"]
FIX_ROOTS = ["tests/fixtures/templates", "data/sim_templates"]
SEED = 42
MAX_AV = 2000

_ANCHORS = ("1303", "1403", "1408")

#: 每锚 policy（A/B 同套）：1408 火种是资源不是能量（energy>=max_energy 恒真会永远
#: 回落普攻攒不出火种——web E2E 踩过的坑），单独给 not in_state 驱动；1303/1403 常规能量
_POLICIES = {
    "default": [
        {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
        {"condition": "skill_points > 0", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ],
    "1408": [
        {"condition": "not in_state", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ],
}

#: 事件流 markers（日志子串计数，双版命名变体都收——LLM/人工件名不同源）
_MARKERS = {
    "common": ["施放", "造成", "击破"],
    "1303": ["结界", "Zone", "残梅绽", "Rebloom", "分型的螺旋", "Helix",
             "弦外音", "Overtone", "击破伤害", "Inert"],
    "1403": ["神启", "NUMINOSITY", "境界", "ZONE", "追加", "忙个不停", "礼物", "猜猜"],
    "1408": ["进入形态", "退出形态", "最后一击", "弑魂", "死星天裁", "火种",
             "卡厄斯兰那", "时墟铁墓", "血棘"],
}

_AV_PREFIX_RE = re.compile(r"^AV[\d.]+: ")
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _ally(aid: str, name: str, spd: float) -> Dict[str, Any]:
    """inline 假人队友：普攻产 2 点（fixtures 普攻未声明 skill_point_gain，不产点会卡战技循环）。"""
    return {
        "inline": True, "actor_id": aid, "name": name, "actor_type": "character",
        "base_stats": {"hp": 3000, "atk": 1000, "def": 800, "spd": spd, "max_energy": 100},
        "actions": [{
            "action_id": f"{aid}_basic", "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 20,
            "skill_point_gain": 2,
        }],
    }


def _build_stage(anchor_id: str) -> tuple:
    """每锚同一配置（A/B 共用）：锚 + 2 产点假人队友 vs 全弱点木桩（240 韧性可击破）。"""
    build = {"build": {
        "team": [
            {"character_template": anchor_id, "level": 80},
            _ally("dummy_a", "假人甲", 95),
            _ally("dummy_b", "假人乙", 90),
        ],
        "policy": {"name": "xref_diff", "action_rules": _POLICIES.get(anchor_id, _POLICIES["default"]),
                   "target_rules": [], "parameters": {}},
    }}
    stage = {"stage": {
        "stage_id": "anchor_diff",
        "enemies": [{
            "actor_id": "e1", "name": "木桩", "level": 80, "hp": 1e9, "atk": 400,
            "def": 500, "spd": 50, "max_toughness": 240,
            "weakness": ["physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary"],
        }],
        "termination": {"mode": "fixed_av", "max_action_value": MAX_AV},
    }}
    return build, stage


def _enemy_attack() -> Action:
    """木桩反击件（setup 后注入；打编队首 = 锚——taunt 并列取编队序，触发 become_target 族）。"""
    return Action(action_id="e1_atk", name="撕咬", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)


def _norm_log(line: str) -> str:
    """日志行规整化（序列对比用）：去 AV 前缀 + 数字打码（对齐行动/事件结构，不比数值）。"""
    return _NUM_RE.sub("#", _AV_PREFIX_RE.sub("", line))


def _is_warn_line(line: str) -> bool:
    """⚠ 兜底告警行判定（AV 前缀之后以 ⚠ 起头——hook 条件/效果求值失败族）。"""
    return _AV_PREFIX_RE.sub("", line).lstrip().startswith("⚠")


def _norm_lines(log: List[str]) -> List[str]:
    """规整化序列：剔除 ⚠ 兜底告警行（条件求值失败族——单列计数，不进序列一致率，
    否则 LLM 版的告警刷屏会淹没真实行为差）。告警数本身就是差异指标（见 log.warn_lines）。"""
    return [_norm_log(l) for l in log if not _is_warn_line(l)]


def _run_one(build: Dict[str, Any], stage: Dict[str, Any], roots: List[str]) -> Dict[str, Any]:
    """单组编译+运行：警告全收（惰性 stat 键证据），异常吞进结果（跑不动也是结论）。"""
    out: Dict[str, Any] = {"compile_ok": False, "compile_error": None, "warnings": []}
    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter("always")
        try:
            compiled = compile_encounter(build, stage, template_roots=roots)
            out["compile_ok"] = True
        except Exception as e:  # noqa: BLE001——对拍脚本：炸=结果
            out["compile_error"] = f"{type(e).__name__}: {e}"
    out["warnings"] = sorted({str(w.message) for w in ws})
    if not out["compile_ok"]:
        return out
    try:
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=SEED)
        eng.setup()
        eng.actions_by_actor.setdefault("e1", []).append(_enemy_attack())  # 双组同注入
        base_stats = {aid: dict(vars(st.actor.stats)) for aid, st in eng.state.actors.items()}
        state = eng.run()
    except Exception as e:  # noqa: BLE001
        out["run_error"] = f"{type(e).__name__}: {e}"
        return out
    snap = state.snapshot()
    out.update({
        "run_ok": True,
        "total_damage": snap["total_damage"],
        "turn_count": snap["turn_count"],
        "cycles_used": snap["cycles_used"],
        "damage_by_actor": snap["damage_by_actor"],
        "log": list(state.log),
        "resources": {aid: a["resources"] for aid, a in snap["actors"].items()},
        "modifiers": {aid: sorted(a["modifiers"]) for aid, a in snap["actors"].items()},
        "base_stats": base_stats,
    })
    return out


def _marker_counts(log: List[str], anchor_id: str) -> Dict[str, int]:
    marks = _MARKERS["common"] + _MARKERS.get(anchor_id, [])
    return {m: sum(1 for line in log if m in line) for m in marks}


def _load_needs_primitive() -> Dict[str, List[str]]:
    """run_state.json（live）+ full_run_1.json（历史汇总）双源合并，按角色取 needs_primitive 名。"""
    out: Dict[str, List[str]] = {}
    try:
        rs = json.loads(Path("data/annotator/run_state.json").read_text(encoding="utf-8"))
        for cid, row in (rs.get("states") or {}).items():
            names = [str(x.get("name")) for x in row.get("needs_primitive") or []
                     if isinstance(x, dict) and x.get("name")]
            if names:
                out.setdefault(str(cid), []).extend(names)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        fr = json.loads(Path("data/annotator/full_run_1.json").read_text(encoding="utf-8"))
        for cid, row in (fr.get("characters") or {}).items():
            names = [str(x.get("name")) for x in row.get("needs_primitive") or []
                     if isinstance(x, dict) and x.get("name")]
            if names:
                out.setdefault(str(cid), []).extend(names)
    except (OSError, json.JSONDecodeError):
        pass
    return {cid: sorted(set(names)) for cid, names in out.items()}


def _stat_diff(run_a: Dict[str, Any], run_b: Dict[str, Any], anchor_id: str) -> Dict[str, Any]:
    """锚本体基础面板差（LLM/人工模板 base_stats 不一致项——伤害差的混淆因子，单列）。

    浮点容差 isclose：生成器浮点尾数（659.7360000000001 vs 659.736）不算差异。
    """
    import math
    sa = (run_a.get("base_stats") or {}).get(anchor_id) or {}
    sb = (run_b.get("base_stats") or {}).get(anchor_id) or {}
    keys = sorted(set(sa) | set(sb))
    out: Dict[str, Any] = {}
    for k in keys:
        va, vb = sa.get(k), sb.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            if not math.isclose(float(va), float(vb), rel_tol=1e-9, abs_tol=1e-9):
                out[k] = {"A": va, "B": vb}
        elif va != vb:
            out[k] = {"A": va, "B": vb}
    return out


def _first_divergence(log_a: List[str], log_b: List[str]) -> Dict[str, Any]:
    """规整化日志序列首个分叉点（±2 行上下文证据窗）。"""
    na, nb = _norm_lines(log_a), _norm_lines(log_b)
    for i, (x, y) in enumerate(zip(na, nb)):
        if x != y:
            return {"index": i,
                    "A": log_a[max(0, i - 1):i + 3],
                    "B": log_b[max(0, i - 1):i + 3]}
    return {"index": min(len(na), len(nb)), "A": log_a[-2:], "B": log_b[-2:],
            "note": "前缀全一致，长度差" if len(na) != len(nb) else "全序列一致"}


def _seq_ratio(log_a: List[str], log_b: List[str]) -> float:
    """事件流一致率：规整化日志序列的 SequenceMatcher ratio（0~1，1=逐行全同）。"""
    return difflib.SequenceMatcher(None, _norm_lines(log_a), _norm_lines(log_b)).ratio()


def diff_anchor(anchor_id: str, np_names: List[str]) -> Dict[str, Any]:
    """单锚对拍：双组运行 → 指标 + 差异清单（[预期]/[意外] 按 needs_primitive 主题名分离）。"""
    build, stage = _build_stage(anchor_id)
    run_a = _run_one(build, stage, LLM_ROOTS)
    run_b = _run_one(build, stage, FIX_ROOTS)
    rep: Dict[str, Any] = {
        "anchor": anchor_id, "needs_primitive": np_names,
        "A_llm": {k: v for k, v in run_a.items() if k != "log"},
        "B_fixture": {k: v for k, v in run_b.items() if k != "log"},
        "divergences": [],
    }

    def add(topic: str, detail: str, evidence: Any = None) -> None:
        tag = "预期" if any(n in detail or n in topic for n in np_names) else "意外"
        rep["divergences"].append(
            {"tag": tag, "topic": topic, "detail": detail, "evidence": evidence})

    if not run_a.get("compile_ok"):
        add("A 组编译失败", f"LLM 版模板编译不过：{run_a.get('compile_error')}")
        return rep
    if not run_a.get("run_ok"):
        add("A 组运行失败", f"LLM 版运行期炸：{run_a.get('run_error')}")
        return rep
    if not run_b.get("compile_ok") or not run_b.get("run_ok"):
        add("B 组运行失败", f"人工锚版异常：{run_b.get('compile_error') or run_b.get('run_error')}")
        return rep

    # 面板差（混淆因子单列）
    sd = _stat_diff(run_a, run_b, anchor_id)
    if sd:
        add("基础面板不一致", f"锚本体 base_stats 差异键：{list(sd)}", sd)

    da, db = run_a["total_damage"], run_b["total_damage"]
    pct = (da - db) / db * 100 if db else float("inf")
    rep["damage"] = {"A": da, "B": db, "abs_diff": da - db, "pct_diff": pct}
    rep["turns"] = {"A": run_a["turn_count"], "B": run_b["turn_count"]}
    if abs(pct) > 0.1:
        add("总伤害差", f"A(LLM)={da:,.1f} vs B(人工)={db:,.1f}（{pct:+.2f}%）")
    if run_a["turn_count"] != run_b["turn_count"]:
        add("行动数差", f"A={run_a['turn_count']} vs B={run_b['turn_count']}")

    # 事件流：一致率 + 首个分叉点（⚠ 告警行单列，不进序列）
    log_a, log_b = run_a["log"], run_b["log"]
    warn_a = sum(1 for l in log_a if _is_warn_line(l))
    warn_b = sum(1 for l in log_b if _is_warn_line(l))
    rep["log"] = {"len_A": len(log_a), "len_B": len(log_b),
                  "warn_lines": {"A": warn_a, "B": warn_b},
                  "seq_ratio": _seq_ratio(log_a, log_b),
                  "first_divergence": _first_divergence(log_a, log_b)}
    if warn_a or warn_b:
        sample = next((l for l in log_a if _is_warn_line(l)), "")
        add("A 组运行期告警行", f"hook 兜底告警 {warn_a} 行（B={warn_b}）——"
            f"条件/效果求值失败按不触发处理，机制实际缺失", sample)
    if rep["log"]["seq_ratio"] < 0.999:
        fd = rep["log"]["first_divergence"]
        add("事件流分叉", f"规整化序列第 {fd['index']} 行起不一致"
            f"（一致率 {rep['log']['seq_ratio']:.1%}）",
            {"A": fd["A"], "B": fd["B"]})

    # markers 计数差
    ca, cb = _marker_counts(log_a, anchor_id), _marker_counts(log_b, anchor_id)
    rep["markers"] = {"A": ca, "B": cb}
    for m in ca:
        if ca[m] != cb[m]:
            add(f"机制事件计数差：{m}", f"{m}: A={ca[m]} vs B={cb[m]}")

    # 终局 modifier 集合差（按单位合并 A 有 B 无 / B 有 A 无）
    ma, mb = run_a["modifiers"], run_b["modifiers"]
    only_a = {aid: sorted(set(ma.get(aid, [])) - set(mb.get(aid, []))) for aid in ma}
    only_b = {aid: sorted(set(mb.get(aid, [])) - set(ma.get(aid, []))) for aid in mb}
    only_a = {k: v for k, v in only_a.items() if v}
    only_b = {k: v for k, v in only_b.items() if v}
    rep["modifier_sets"] = {"only_A": only_a, "only_B": only_b}
    for aid, mods in only_a.items():
        add("modifier 仅 A 有", f"{aid}: {mods}")
    for aid, mods in only_b.items():
        add("modifier 仅 B 有", f"{aid}: {mods}")

    # 资源轨迹差
    ra, rb = run_a["resources"].get(anchor_id, {}), run_b["resources"].get(anchor_id, {})
    if ra != rb:
        rep["resources"] = {"A": ra, "B": rb}
        add("资源轨迹差", f"锚终局资源：A={ra} vs B={rb}")

    # 编译期未知 stat 键警告（惰性键证据）
    for w in run_a.get("warnings") or []:
        add("A 组编译警告", w)
    return rep


def _print_summary(rep: Dict[str, Any]) -> None:
    aid = rep["anchor"]
    print(f"\n{'=' * 72}\n锚 {aid}（needs_primitive: {rep['needs_primitive'] or '无登记'}）")
    if "damage" in rep:
        d = rep["damage"]
        print(f"  总伤害  A(LLM)={d['A']:,.1f}  B(人工)={d['B']:,.1f}  Δ={d['abs_diff']:+,.1f}（{d['pct_diff']:+.2f}%）")
        print(f"  行动数  A={rep['turns']['A']}  B={rep['turns']['B']}   "
              f"事件流一致率={rep['log']['seq_ratio']:.1%}（{rep['log']['len_A']} vs {rep['log']['len_B']} 行）")
    n_unexp = sum(1 for x in rep["divergences"] if x["tag"] == "意外")
    n_exp = sum(1 for x in rep["divergences"] if x["tag"] == "预期")
    print(f"  差异 {len(rep['divergences'])} 条（意外 {n_unexp} / 预期 {n_exp}）")
    for x in rep["divergences"]:
        print(f"    [{x['tag']}] {x['topic']}：{x['detail'][:150]}")


def main() -> int:
    ap = argparse.ArgumentParser(description="锚三对拍：LLM 标注版 vs 人工锚版行为对比")
    ap.add_argument("--out", default="data/annotator/anchor_diff.json",
                    help="JSON 输出路径（默认 data/annotator/anchor_diff.json）")
    ap.add_argument("--anchors", nargs="*", default=list(_ANCHORS),
                    help="只跑指定锚（默认三个全跑）")
    args = ap.parse_args()

    np_all = _load_needs_primitive()
    reports = [diff_anchor(aid, np_all.get(aid, [])) for aid in args.anchors]
    for rep in reports:
        _print_summary(rep)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": SEED, "max_av": MAX_AV, "anchors": reports},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nJSON 已写：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
