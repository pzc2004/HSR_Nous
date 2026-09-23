"""对拍报告机（ops/annotator/oracle）——打标 DAG 的 hook 逻辑层数值神谕.

定位：golden_diff 机械闸（白值/id/scaling/path 对官方数据锚）只管**数据保真**；
本件管**数值正确性**——draft 模板编译后，与 external/hsr-optimizer（钉 31255b93，
只读）逐技能对拍（kind="character" driver，口径见 scripts/crosscheck/crosscheck.mts
头注），产出逐技能比值报告写进 run 目录，staging 候选包挂「对拍异常数」。

**报告型闸语义**：异常不打回、不阻塞 DAG——误报率没实证前不做硬闸；人过堂时
看报告裁量（staging notes 挂摘要，全文 oracle_report.json）。

场景自动生成口径（与 tests/test_crosscheck_characters.py L2 先例同钉）：
- 动作集 = 模板 actions 中 action_type ∈ {basic, skill, ultimate} 的核心件
  （follow_up 触发条件/忆灵技/assist 自动场景不可达——跳过并记 skipped 行，
  对拍战役人工场景兜底）；每动作独立 fresh 编译 + fresh 引擎（状态零污染）。
- 无 teammates、无遗器光锥；星魂 E0（eidolon 可配）。
- 假人 lvl80 / def 1000 / 匹配弱点（抗性区 1.0）/ 未击破（0.9）/ hp 1e9 /
  max_toughness 9999——与对方 enemy {level:80, res 0, broken false, count 1} 同构。
- 面板钉死 = 官方管线实值（calc_character_stats lv80，data_pull 下发）——对方
  conditionals 行迹件叠在钉死面板上，我方模板行迹走自家通道；两侧同构
  「base + 行迹」，模板把行迹平铺并进 base_stats 也不会双计。
- 对方 conditionals：缺省 {} = 对方 defaults() 生效（回显落报告供过堂判读）；
  可按角色传覆盖（金样测试用全中性钉）。
- 比值口径 = **对方/我方**；|ratio-1| > threshold（默认 1e-3）标 anomaly。
- 对方未覆盖（注册表查无此 id——含 B1 加强版 id 映射未接）→ pass-through
  标 optimizer_not_covered；缺 node/rolldown → env_no_node。均不阻塞 DAG。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[4]
DRIVER_SRC = ROOT / "scripts" / "crosscheck" / "crosscheck.mts"
DRIVER_DIST = ROOT / "scripts" / "crosscheck" / "dist" / "crosscheck.mjs"
ROLLDOWN = ROOT / "external" / "hsr-optimizer" / "node_modules" / ".bin" / "rolldown"
ROLLDOWN_CONFIG = ROOT / "scripts" / "crosscheck" / "rolldown.config.mjs"

#: 我方 canonical 命途 → 对方 PathName（countTeamPath 计数口径元数据）
OPT_PATHS = {
    "destruction": "Destruction", "erudition": "Erudition", "hunt": "The Hunt",
    "harmony": "Harmony", "nihility": "Nihility", "preservation": "Preservation",
    "abundance": "Abundance", "remembrance": "Remembrance", "elation": "Elation",
}

#: 模板 action_type → 对方 AbilityKind 场景键（follow_up/memosprite/assist 不自动铺）
_ACTION_KINDS = {"basic": "basic", "skill": "skill", "ultimate": "ult"}

#: 最小策略（引擎占位——对拍不走决策层，直接 _execute_action/_fire_ultimate）
_POLICY = {"name": "oracle", "action_rules": [
    {"condition": "true", "action": "skill", "priority": 50},
    {"condition": "true", "action": "basic", "priority": 0}]}


def ensure_driver() -> Optional[Path]:
    """确保 driver bundle 存在（源码更新则重打）；缺环境返回 None（节点降级）."""
    if shutil.which("node") is None or not ROLLDOWN.exists():
        return None
    if (not DRIVER_DIST.exists()
            or DRIVER_DIST.stat().st_mtime < DRIVER_SRC.stat().st_mtime):
        try:
            subprocess.run([str(ROLLDOWN), "-c", str(ROLLDOWN_CONFIG)],
                           cwd=ROOT, check=True, capture_output=True, text=True, timeout=300)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
    return DRIVER_DIST


def run_optimizer(driver: Path, scenario: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    """node 子进程跑驱动：(结果 dict, 错误串)——错误不抛（报告型闸逐行记）."""
    try:
        proc = subprocess.run(["node", str(driver)], input=json.dumps(scenario),
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return None, "driver_timeout"
    if proc.returncode != 0:
        return None, (proc.stderr or "")[-500:]
    try:
        return json.loads(proc.stdout), ""
    except json.JSONDecodeError as e:
        return None, f"driver 输出非 JSON：{e}"


# ---------------------------------------------------------------------------
# 场景生成（模板 + 对方 defaults → kind=character 场景清单）
# ---------------------------------------------------------------------------

def build_scenarios(doc: Dict[str, Any], official: Dict[str, Any], *,
                    conditionals: Optional[Dict[str, Any]] = None,
                    eidolon: int = 0) -> List[Dict[str, Any]]:
    """模板 actions（basic/skill/ultimate 核心）→ 对方场景清单（含 skipped 行）.

    面板钉死 = official["base_stats"]（calc_character_stats lv80 实值——data_pull 下发）；
    元素取模板 element（缺省回落官方包）；self_path 取模板 canonical path 映射对方
    PathName。conditionals={} = 对方 defaults() 生效（回显落报告）。
    """
    from hsr_nous.sim_schema.actor import PATH_ALIASES

    base = official["base_stats"]
    element = str(doc.get("element") or official.get("element") or "").lower()
    raw_path = str(doc.get("path") or official.get("path") or "").lower()
    path = PATH_ALIASES.get(raw_path, raw_path)
    out: List[Dict[str, Any]] = []
    for a in doc.get("actions") or []:
        if not isinstance(a, dict):
            continue
        aid, at = str(a.get("action_id")), str(a.get("action_type"))
        kind = _ACTION_KINDS.get(at)
        if kind is None:
            out.append({"action_id": aid, "action_type": at, "status": "skipped",
                        "reason": "自动场景不可达（follow_up 触发条件/忆灵技/assist——"
                                  "对拍战役人工场景兜底）"})
            continue
        out.append({
            "action_id": aid, "action_type": at, "opt_action": kind,
            "scenario": {
                "kind": "character", "character_id": str(doc.get("actor_id")),
                "eidolon": eidolon, "action": kind, "element": element,
                "conditionals": dict(conditionals or {}),
                "base": {"atk": base["atk"], "hp": base["hp"],
                         "def": base["def"], "spd": base["spd"]},
                "attacker": {"atk": base["atk"], "hp": base["hp"], "def": base["def"],
                             "spd": base["spd"], "cr": base.get("crit_rate", 0.05),
                             "cd": base.get("crit_dmg", 0.5)},
                "self_path": OPT_PATHS.get(path, path),
                "enemy": {"level": 80, "damage_resistance": 0.0,
                          "weakness_broken": False, "count": 1},
            }})
    return out


# ---------------------------------------------------------------------------
# 我方侧取数（L2 对拍先例同形：fresh 编译 + bus 记录仪收 on_hp_decrease）
# ---------------------------------------------------------------------------

def _stage(element: str) -> Dict[str, Any]:
    return {"stage": {"stage_id": "oracle", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
         "def": 1000, "max_toughness": 9999, "weakness": [element]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def ours_action_total(cid: str, action: Dict[str, Any], *,
                      element: str, template_roots: List[str],
                      enemy_hp_ratio: float = 1.0) -> Tuple[Optional[float], str, int]:
    """单动作我方总伤：fresh 编译 + fresh 引擎（状态零污染），bus 记录仪收
    on_hp_decrease（setup 前订阅——嵌套伤害因果序，L2 先例 _make_logged 同口径）。
    返回 (总伤|None, 错误串, 命中段数)；None = 未能施放（如特殊充能门槛）。"""
    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim.engine import CombatEngine
    from hsr_nous.sim.pipeline import MODE_EXPECTED

    build = {"build": {"team": [{"character_template": cid, "level": 80}],
                       "policy": _POLICY}}
    compiled = compile_encounter(build, _stage(element), template_roots=template_roots)
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0)
    log: List[Dict[str, Any]] = []
    eng.bus.subscribe("on_hp_decrease", lambda et, payload, ctx: log.append(dict(payload)))
    eng.setup()
    if enemy_hp_ratio < 1.0:
        e1 = eng.state.actors["e1"]
        e1.current_hp = enemy_hp_ratio * eng.pipeline.effective_stats(e1)["hp"]
    st = eng.state.actors[cid]
    aid = action["action_id"]
    acts = [x for x in eng.actions_by_actor[cid] if x.action_id == aid]
    if not acts:
        return None, f"模板编译后无 action {aid}", 0
    act = acts[0]
    if action["action_type"] == "ultimate":
        st.current_energy = max(st.current_energy, float(st.actor.stats.max_energy or 0))
        if act.ult_cost_resource:   # 特殊充能大招（黄泉 slashed_dream 族）：资源钉到门槛
            st.resources[act.ult_cost_resource] = act.ult_cost_amount
        if not eng._fire_ultimate(st, act):
            return None, "ult_not_fired", 0
    else:
        tgt = eng.state.actors["e1"]
        eng.decision.select_target = (
            lambda actor_state, action_type, candidates, engine: (
                tgt if tgt in candidates else (candidates[0] if candidates else None)))
        eng._execute_action(st, act)
        eng.bus.emit("on_action", {
            "actor": cid, "action_type": act.action_type, "action_id": aid,
            "target_type": act.target_type, "target": tgt.actor.actor_id,
            "actor_type": st.actor.actor_type}, eng.state)
    hits = [e["amount"] for e in log
            if e.get("reason") == "hit" and e.get("source") == cid]
    return float(sum(hits)), "", len(hits)


# ---------------------------------------------------------------------------
# 报告生成（报告型闸本体：任何失败都只落报告，不上抛）
# ---------------------------------------------------------------------------

def _write_report(workdir: Path, report: Dict[str, Any]) -> Path:
    p = workdir / "oracle_report.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _summary(report: Dict[str, Any], report_path: Path) -> Dict[str, Any]:
    rows = report.get("rows") or []
    return {
        "status": report["status"],
        "anomalies": sum(1 for r in rows if r.get("status") == "anomaly"),
        "compared": sum(1 for r in rows if r.get("status") in ("ok", "anomaly", "no_damage")),
        "inconclusive": sum(1 for r in rows
                            if r.get("status") in ("ult_not_fired", "our_side_error",
                                                   "driver_error")),
        "skipped": sum(1 for r in rows if r.get("status") == "skipped"),
        "report_path": str(report_path),
        "rows": [{k: r.get(k) for k in ("action_id", "action_type", "status",
                                        "ratio", "ours", "theirs", "note")}
                 for r in rows],
    }


def generate_report(cid: str, tpl_text: str, official: Dict[str, Any], workdir: "str | Path",
                    *, threshold: float = 1e-3,
                    conditionals: Optional[Dict[str, Any]] = None,
                    template_roots: Optional[List[str]] = None,
                    eidolon: int = 0) -> Dict[str, Any]:
    """对拍报告主入口：逐技能 对方/我方 比值，落 oracle_report.json，返回摘要.

    报告型闸——本函数任何路径都不抛异常（internal_error 也落报告返回摘要）。
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "cid": cid, "name_cn": official.get("name_cn"),
        "threshold": threshold, "ratio_convention": "对方/我方",
        "panel_convention": "面板钉死=官方管线实值 calc lv80（data_pull base_stats）；"
                            "对方 conditionals 行迹件叠钉死面板，我方模板行迹走自家通道",
        "enemy_convention": "假人 lvl80/def1000/匹配弱点/未击破/hp1e9/toughness9999"
                            " ≡ 对方 enemy{level:80,res:0,broken:false,count:1}",
        "conditionals_overrides": dict(conditionals or {}),
        "eidolon": eidolon,
        "rows": [],
    }
    try:
        driver = ensure_driver()
        if driver is None:
            report.update(status="env_no_node",
                          note="缺 node 或 rolldown——环境降级不阻塞 DAG")
            return _summary(report, _write_report(workdir, report))
        import yaml

        doc = yaml.safe_load(tpl_text)
        if not isinstance(doc, dict):
            raise ValueError("模板 YAML 本体不是 mapping")
        scenarios = build_scenarios(doc, official, conditionals=conditionals,
                                    eidolon=eidolon)
        report["rows"] = scenarios   # skipped 行 + 可对拍行（后者原地补比值状态）
        runnable = [r for r in scenarios if "scenario" in r]
        if not runnable:
            report.update(status="no_scenarios", note="模板无可对拍核心行动块")
            return _summary(report, _write_report(workdir, report))

        # 对方侧先行（覆盖探针：注册表查无此 id → pass-through，我方侧省跑）
        defaults_echo: Optional[Dict[str, Any]] = None
        for r in runnable:
            res, err = run_optimizer(driver, r["scenario"])
            if res is None:
                if "character not registered" in err:
                    report.update(status="optimizer_not_covered",
                                  note=f"对方注册表无 id {doc.get('actor_id')}"
                                       "（B1 加强版 id 映射未接——对拍战役已拍角色不受影响）")
                    return _summary(report, _write_report(workdir, report))
                first_line = next((ln.strip() for ln in err.splitlines()
                                   if "Error" in ln), err.splitlines()[0] if err else "")
                r.update(status="driver_error", note=first_line[:200])
                continue
            if defaults_echo is None:
                defaults_echo = res.get("conditionals")
            r["theirs"] = res.get("total")
            r["their_hits"] = len(res.get("hits") or [])
        report["conditionals_effective"] = defaults_echo

        # 我方侧：draft 模板落盘编译（workdir 模板根优先于 data 生成根）
        tpl_root = workdir / "oracle_tpl"
        (tpl_root / "characters").mkdir(parents=True, exist_ok=True)
        tpl_path = tpl_root / "characters" / f"{cid}.yaml"
        tpl_path.write_text(tpl_text, encoding="utf-8")
        roots = [*(template_roots or []), str(tpl_root), str(ROOT / "data/sim_templates")]
        element = str(doc.get("element") or official.get("element") or "").lower()
        for r in runnable:
            if r.get("status") == "driver_error":
                continue
            try:
                # 敌态对齐：对方条件开关描述其敌态假设（如 enemyHpGte50=False）——
                # 我方假人同步打残，否则 HP 条件件两侧状态不一致（2026-09-23 黑塔 D1 收编后实证）
                cond = (r["scenario"].get("conditionals") or {})
                hp_ratio = 0.4 if cond.get("enemyHpGte50") is False else 1.0
                total, err, n_hits = ours_action_total(
                    cid, r, element=element, template_roots=roots,
                    enemy_hp_ratio=hp_ratio)
            except Exception as e:  # noqa: BLE001 —— 单动作我方侧炸只记行不上抛
                r.update(status="our_side_error", note=f"{type(e).__name__}: {e}"[:300])
                continue
            if err == "ult_not_fired":
                r.update(status="ult_not_fired",
                         note="终结技未能施放（特殊门槛/形态前置——需人工钉资源， inconclusive）")
                continue
            if err:
                r.update(status="our_side_error", note=err[:300])
                continue
            r["ours"], r["our_hits"] = total, n_hits

        # 比值对账（对方/我方）
        for r in runnable:
            if "ours" not in r or "theirs" not in r:
                continue
            ours, theirs = r["ours"], r["theirs"]
            if ours == 0 and theirs == 0:
                r.update(status="no_damage", ratio=None,
                         note="双侧零伤害段（治疗/机制行动）——比值无意义")
            elif ours == 0 or theirs == 0:
                r.update(status="anomaly", ratio=None,
                         note=f"单侧零伤害段（我方 {ours} / 对方 {theirs}）——"
                              "机制缺失或口径差，过堂裁量")
            else:
                ratio = theirs / ours
                r["ratio"] = ratio
                if abs(ratio - 1) > threshold:
                    r.update(status="anomaly",
                             note=f"|ratio-1|={abs(ratio - 1):.4g} > {threshold}")
                else:
                    r.update(status="ok")
        report["status"] = "ok"
    except Exception as e:  # noqa: BLE001 —— 报告型闸：任何内部错误只落报告
        import traceback

        report.update(status="internal_error",
                      note=f"{type(e).__name__}: {e}"[:300],
                      traceback=traceback.format_exc()[-1500:])
    return _summary(report, _write_report(workdir, report))
