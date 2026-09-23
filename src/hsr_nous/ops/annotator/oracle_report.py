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
- 对方未覆盖（注册表查无此 id——原版 stub 空壳（1102 希儿族，对拍战役 wave①
  版本对齐口径：现役=加强版，stub 不拍）或未登记角色）→ pass-through
  标 optimizer_not_covered；缺 node/rolldown → env_no_node。均不阻塞 DAG。
- B1 id 映射：对方注册表加强版以 B1 后缀 id 登记（OPT_B1_IDS）——我方现役 id
  先经映射再查询（1006→1006b1 族）；映射表来源=对拍战役 wave① 版本对齐口径
  （tests/test_crosscheck_legacy_1000/1300.py：B1 加强版套件按对方 id 直呼，
  我方 fixture=现役加强版）。

**装备分支（光锥/遗器）**：装备模板无行动块——对拍借**载体角色**（金样验收
fixture + 对方注册表双在册）穿装备打核心行动，比值口径同角色版。场景=对方
kind=character + equipment 块（LC 用 light_cone 子块、遗器/位面用 relic_sets），
载体/面板/开关钉死值照对拍战役装备先例逐键抄录（tests/test_crosscheck_equipment*.py
的场景 builder）。光锥属性段（官方 properties——暴击/命中/增伤族，对方控制器
不承载）按叠影档钉进对方面板，我方走模板 hooks 通道（先例同口径）；遗器套装
基础件（p2c/p4c）两侧各自原生通道不钉面板。LC 命途门控两侧同构（path 不匹配
→ 对方空控制器/我方 hooks 全灭）→ 载体按 LC 命途选（_EQUIP_CARRIERS，无载体
命途 → no_carrier pass-through）。
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

#: 我方 canonical 命途 → 对方 PathName（countTeamPath 计数口径元数据——值=对方
#: PathNames 枚举原值（constants.ts），非显示名：巡猎是 'Hunt' 不是 'The Hunt'）
OPT_PATHS = {
    "destruction": "Destruction", "erudition": "Erudition", "hunt": "Hunt",
    "harmony": "Harmony", "nihility": "Nihility", "preservation": "Preservation",
    "abundance": "Abundance", "remembrance": "Remembrance", "elation": "Elation",
}

#: 模板 action_type → 对方 AbilityKind 场景键（follow_up/memosprite/assist 不自动铺）
_ACTION_KINDS = {"basic": "basic", "skill": "skill", "ultimate": "ult"}

#: 我方现役 id → 对方加强版（B1）注册 id——对方注册表把加强版以 B1 后缀 id 登记
#: （external/hsr-optimizer src/lib/conditionals/character/** 实证：1004b1 WeltB1/
#: 1005b1 KafkaB1/1006b1 SilverWolfB1/1205b1 BladeB1/1212b1 JingliuB1/
#: 1217b1 HuohuoB1/1306b1 SparkleB1/1310b1 FireflyB1）。来源=对拍战役 wave①
#: 版本对齐口径（tests/test_crosscheck_legacy_1000/1300.py：B1 加强版套件按对方
#: id 直呼，我方 fixture=现役加强版）。对方原版多为 stub 空壳（1102 希儿族，
#: 对拍战役实证不拍）——不在本表且注册表查无 → optimizer_not_covered pass-through。
OPT_B1_IDS = {
    "1004": "1004b1", "1005": "1005b1", "1006": "1006b1",
    "1205": "1205b1", "1212": "1212b1", "1217": "1217b1",
    "1306": "1306b1", "1310": "1310b1",
}

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
                "kind": "character",
                "character_id": OPT_B1_IDS.get(str(doc.get("actor_id")),
                                               str(doc.get("actor_id"))),
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
                      enemy_hp_ratio: float = 1.0,
                      member_extra: Optional[Dict[str, Any]] = None,
                      setup: Optional[str] = None) -> Tuple[Optional[float], str, int]:
    """单动作我方总伤：fresh 编译 + fresh 引擎（状态零污染），bus 记录仪收
    on_hp_decrease（setup 前订阅——嵌套伤害因果序，L2 先例 _make_logged 同口径）。
    返回 (总伤|None, 错误串, 命中段数)；None = 未能施放（如特殊充能门槛）。
    member_extra=装备块并入 member（装备分支对拍——光锥/遗器引用）；
    setup=载体战前准备钩（"clean_knots"=黄泉开局结摘除，对拍战役 _clean_knots 同口径）。"""
    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim.engine import CombatEngine
    from hsr_nous.sim.pipeline import MODE_EXPECTED

    member = {"character_template": cid, "level": 80, **(member_extra or {})}
    build = {"build": {"team": [member], "policy": _POLICY}}
    compiled = compile_encounter(build, _stage(element), template_roots=template_roots)
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0)
    log: List[Dict[str, Any]] = []
    eng.bus.subscribe("on_hp_decrease", lambda et, payload, ctx: log.append(dict(payload)))
    eng.setup()
    if setup == "clean_knots":
        # 黄泉开局结摘除（负面计数类装备对拍要求负面件数=场景假设，0 负面净板；
        # 开局结经引擎施加会正规触发 117 翻倍钩——连坐摘除回空白 slate）
        for st_ in eng.state.actors.values():
            st_.modifiers.pop("CRIMSON_KNOT", None)
        for mid in [m for m in eng.state.actors[cid].modifiers if "DOUBLE" in m]:
            eng.state.actors[cid].modifiers.pop(mid)
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
    if cid in OPT_B1_IDS:
        report["optimizer_character_id"] = OPT_B1_IDS[cid]   # B1 映射回显（过堂判读）
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
                                       "（原版 stub 空壳/未登记——对拍战役 wave① 口径："
                                       "现役=加强版（B1 映射见 OPT_B1_IDS），stub 不拍）")
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


# ---------------------------------------------------------------------------
# 装备分支对拍（光锥/遗器——借载体角色穿装备打核心行动，比值口径同角色版）
# ---------------------------------------------------------------------------

#: 载体注册表（LC 命途 canonical key → 载体规格）——载体=对拍战役金样验收角色
#: （我方 fixture 模板 + 对方注册表双在册），面板/开关钉死值照装备先例逐键抄录：
#: - pins：对方角色 conditionals 中性钉（先例 builder 同套——defaults 非中性的
#:   开关必须钉，否则载体自身机制两侧状态不齐，装备比值被载体差污染）；
#: - actions：参与对拍的核心行动（对方 AbilityKind 键）——排除项逐一带挡因：
#:   黄泉 ult=残梦/啼泽逐段族对方开关镜像成本高（待收）；真理 skill=天赋追击
#:   骑手段（对方 FUA 独立 ability，sum-all 口径必差——先例 FUA 段单独比等）；
#: - setup：我方战前准备钩（"clean_knots"=开局结摘除，先例 _clean_knots 同口径）。
_EQUIP_CARRIERS = {
    "nihility": {
        "cid": "1308", "template": "1308_黄泉.yaml", "opt_id": "1308",
        "element": "thunder", "opt_path": "Nihility",
        "actions": ["basic", "skill"],
        "pins": {"crimsonKnotStacks": 9, "nihilityTeammatesBuff": False,
                 "e1EnemyDebuffed": False, "thunderCoreStacks": 0,
                 "stygianResurgeHitsOnTarget": 6, "e4UltVulnerability": True,
                 "e6UltBuffs": True},
        "setup": "clean_knots",
        "precedent": "tests/test_crosscheck_equipment.py _acheron_opt",
    },
    "erudition": {
        "cid": "1013", "template": "1013_黑塔.yaml", "opt_id": "1013",
        "element": "ice", "opt_path": "Erudition",
        "actions": ["basic", "skill", "ult"],
        "pins": {"fuaStacks": 1, "techniqueBuff": False, "targetFrozen": False,
                 "enemyHpGte50": False, "enemyHpLte50": False,
                 "e2TalentCritStacks": 0, "e6UltAtkBuff": True},
        "setup": None,
        "precedent": "tests/test_crosscheck_characters.py _opt_herta（角色版金样同套钉）",
    },
    "hunt": {
        "cid": "1305", "template": "1305_真理医生.yaml", "opt_id": "1305",
        "element": "imaginary", "opt_path": "Hunt",
        "actions": ["basic", "ult"],
        "pins": {"enemyDebuffStacks": 0, "summationStacks": 0},
        "setup": None,
        "precedent": "tests/test_crosscheck_equipment.py _ratio_opt",
    },
}

#: 遗器默认载体 key（遗器无命途门控——黑塔金样最简：面板=白值零行迹、单人队
#: 无追击骑手段；机制绑定特定条件的套装（忆灵/耗血/追击族）两侧同不触发 →
#: 比值 1 无信息但不误报）
_RELIC_CARRIER_KEY = "erudition"

#: 光锥官方 properties（属性段）→ 对方面板钉槽——属性段对方控制器不承载，由场景
#: 钉进 attacker 终值面板（先例口径：暴击/命中/增伤族；我方走模板 hooks 通道）。
#: flat=百分点/平值直加面板；pct=乘白值（白值=角色+光锥——与我方 _merge_light_cone
#: 并入后同构）。无直伤消费通道不钉（SPRatioBase=能量恢复效率/HealRatioBase=
#: 治疗量/HealTakenRatio=受治疗/ElationDamageAddedRatioBase=欢愉增伤——载体行动不吃）。
_LC_PROP_PINS = {
    "CriticalChanceBase": ("cr", "flat"),
    "CriticalDamageBase": ("cd", "flat"),
    "StatusProbabilityBase": ("effect_hit", "flat"),
    "StatusResistanceBase": ("effect_res", "flat"),
    "AllDamageTypeAddedRatio": ("dmg_boost", "flat"),
    "BreakDamageAddedRatioBase": ("be", "flat"),
    "BaseSpeed": ("spd", "flat"),
    "AttackAddedRatio": ("atk", "pct"),
    "HPAddedRatio": ("hp", "pct"),
    "DefenceAddedRatio": ("def", "pct"),
    "SpeedAddedRatio": ("spd", "pct"),
}

#: 对方 AbilityKind 键 → 载体模板 action_type（行动块定位用）
_OPT_TO_ACTION_TYPE = {"basic": "basic", "skill": "skill", "ult": "ultimate"}


def _load_carrier_fixture(template: str) -> Dict[str, Any]:
    """读载体 fixture 模板（base_stats/trace_stat_effects/actions——面板钉死数据源）."""
    import yaml

    p = ROOT / "tests" / "fixtures" / "templates" / "characters" / template
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def equipment_carrier(kind: str, doc: Dict[str, Any],
                      carrier_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """装备模板 → 载体规格（LC 按命途选载体；遗器固定默认载体）——无载体命途 → None."""
    if carrier_key:
        return _EQUIP_CARRIERS.get(carrier_key)
    if kind == "relic":
        return _EQUIP_CARRIERS[_RELIC_CARRIER_KEY]
    from hsr_nous.sim_schema.actor import PATH_ALIASES

    raw = str(doc.get("path") or "").lower()
    return _EQUIP_CARRIERS.get(PATH_ALIASES.get(raw, raw))


def build_equipment_scenarios(kind: str, eid: str, doc: Dict[str, Any],
                              official: Dict[str, Any], *, carrier: Dict[str, Any],
                              superimposition: int = 1,
                              lc_conditionals: Optional[Dict[str, Any]] = None,
                              set_conditionals: Optional[Dict[str, Any]] = None
                              ) -> List[Dict[str, Any]]:
    """装备模板 + 载体 → 对方 kind=character+equipment 场景清单（含 skipped 行）.

    面板钉死口径（对拍战役装备先例）：base=角色+光锥白值（遗器=角色白值）；
    attacker=白值×(1+行迹 pct+属性段 pct)+属性段 flat（cr/cd 恒带载体 fixture
    白值基——flat 行迹已并入 fixture base_stats，真理医生 crit 0.17 先例）；
    套装基础件（p2c/p4c）两侧各自原生通道不钉面板。LC/套装 conditionals 缺省
    {} = 对方 defaults() 生效（回显落报告）。行动集=载体核心行动（carrier["actions"]，
    排除项挡因见 _EQUIP_CARRIERS 注）。
    """
    from hsr_nous.sim_schema.actor import PATH_ALIASES

    fixture = _load_carrier_fixture(carrier["template"])
    base_stats = fixture.get("base_stats") or {}
    trace = fixture.get("trace_stat_effects") or {}
    lc_base = (official.get("base_stats") or {}) if kind == "light_cone" else {}
    white = {k: float(base_stats.get(k, 0)) + float(lc_base.get(k, 0) or 0)
             for k in ("atk", "hp", "def")}
    white["spd"] = float(base_stats.get("spd", 0))
    flat_pins: Dict[str, float] = {}
    pct_pins: Dict[str, float] = {}
    if kind == "light_cone":
        ranks = official.get("properties") or []
        props = ranks[superimposition - 1] if 0 <= superimposition - 1 < len(ranks) else []
        for p in props:
            m = _LC_PROP_PINS.get(str((p or {}).get("type")))
            if not m:
                continue
            key, mode = m
            if mode == "flat":
                flat_pins[key] = flat_pins.get(key, 0) + float(p.get("value") or 0)
            else:
                pct_pins[key] = pct_pins.get(key, 0) + float(p.get("value") or 0)
    attacker = {
        "atk": white["atk"] * (1 + trace.get("atk_pct", 0) + pct_pins.get("atk", 0)),
        "hp": white["hp"] * (1 + trace.get("hp_pct", 0) + pct_pins.get("hp", 0)),
        "def": white["def"] * (1 + trace.get("def_pct", 0) + pct_pins.get("def", 0)),
        "spd": white["spd"] * (1 + trace.get("spd_pct", 0) + pct_pins.get("spd", 0))
               + flat_pins.get("spd", 0),
        "cr": float(base_stats.get("crit_rate", 0.05)) + flat_pins.get("cr", 0),
        "cd": float(base_stats.get("crit_dmg", 0.5)) + flat_pins.get("cd", 0),
    }
    for k in ("be", "dmg_boost", "effect_hit", "effect_res"):
        if k in flat_pins:
            attacker[k] = flat_pins[k]
    if kind == "light_cone":
        raw_path = str(doc.get("path") or "").lower()
        canonical = PATH_ALIASES.get(raw_path, raw_path)
        equipment: Dict[str, Any] = {"light_cone": {
            "id": str(eid), "superimposition": superimposition,
            "path": OPT_PATHS.get(canonical, canonical),
            "conditionals": dict(lc_conditionals or {})}}
    else:
        pieces = 2 if str(eid).startswith("3") else 4
        equipment = {"relic_sets": [{
            "id": str(eid), "pieces": pieces,
            "conditionals": dict(set_conditionals or {})}]}
    acts_by_type = {str(a.get("action_type")): str(a.get("action_id"))
                    for a in (fixture.get("actions") or []) if isinstance(a, dict)}
    rows: List[Dict[str, Any]] = []
    for act in carrier["actions"]:
        aid = acts_by_type.get(_OPT_TO_ACTION_TYPE.get(act, ""))
        if aid is None:
            rows.append({"action_id": f"{carrier['cid']}:{act}", "action_type": act,
                         "status": "skipped",
                         "reason": f"载体模板缺 {_OPT_TO_ACTION_TYPE.get(act)} 行动块"})
            continue
        rows.append({
            "action_id": aid, "action_type": act, "opt_action": act,
            "scenario": {
                "kind": "character", "character_id": carrier["opt_id"], "eidolon": 0,
                "action": act, "element": carrier["element"],
                "conditionals": dict(carrier["pins"]),
                "base": {"atk": white["atk"], "hp": white["hp"],
                         "def": white["def"], "spd": white["spd"]},
                "attacker": attacker, "self_path": carrier["opt_path"],
                "enemy": {"level": 80, "damage_resistance": 0.0,
                          "weakness_broken": False, "count": 1},
                "equipment": equipment,
            }})
    return rows


def generate_equipment_report(kind: str, eid: str, tpl_text: str, official: Dict[str, Any],
                              workdir: "str | Path", *, threshold: float = 1e-3,
                              superimposition: int = 1,
                              lc_conditionals: Optional[Dict[str, Any]] = None,
                              set_conditionals: Optional[Dict[str, Any]] = None,
                              carrier_key: Optional[str] = None,
                              template_roots: Optional[List[str]] = None) -> Dict[str, Any]:
    """装备对拍报告主入口：逐行动 对方/我方 比值，落 oracle_report.json，返回摘要.

    报告型闸——本函数任何路径都不抛异常（internal_error 也落报告返回摘要）。
    降级口径（全部 pass-through 不阻塞）：装备/套装/载体对方未登记 →
    optimizer_not_covered；LC 命途无载体 → no_carrier；缺 node/rolldown →
    env_no_node。lc_conditionals/set_conditionals=None = 对方 defaults() 生效
    （生效开关回显落报告——生产缺省；金样测试用全中性钉）。
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "kind": kind, "eid": str(eid), "name_cn": official.get("name_cn"),
        "threshold": threshold, "ratio_convention": "对方/我方",
        "superimposition": superimposition,
        "carrier_convention": "载体=金样验收角色穿装备打核心行动（_EQUIP_CARRIERS——"
                              "面板/开关钉死值照对拍战役装备先例）；LC 属性段钉对方面板/"
                              "套装基础件两侧各自原生通道",
        "enemy_convention": "假人 lvl80/def1000/匹配弱点/未击破/hp1e9/toughness9999"
                            " ≡ 对方 enemy{level:80,res:0,broken:false,count:1}",
        "lc_conditionals_overrides": dict(lc_conditionals or {}),
        "set_conditionals_overrides": dict(set_conditionals or {}),
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
        carrier = equipment_carrier(kind, doc, carrier_key)
        if carrier is None:
            report.update(status="no_carrier",
                          note=f"LC 命途 {doc.get('path')!r} 无对拍载体（_EQUIP_CARRIERS "
                               "未覆盖——载体需金样验收 fixture+对方注册表双在册；"
                               "扩载体=按先例登记钉死值）")
            return _summary(report, _write_report(workdir, report))
        report["carrier"] = {"cid": carrier["cid"], "template": carrier["template"],
                             "precedent": carrier["precedent"]}
        scenarios = build_equipment_scenarios(
            kind, eid, doc, official, carrier=carrier, superimposition=superimposition,
            lc_conditionals=lc_conditionals, set_conditionals=set_conditionals)
        report["rows"] = scenarios   # skipped 行 + 可对拍行（后者原地补比值状态）
        runnable = [r for r in scenarios if "scenario" in r]
        if not runnable:
            report.update(status="no_scenarios", note="载体无可对拍核心行动块")
            return _summary(report, _write_report(workdir, report))

        # 对方侧先行（覆盖探针：装备/套装/载体注册表查无 → pass-through，我方侧省跑）
        defaults_echo: Optional[Dict[str, Any]] = None
        for r in runnable:
            res, err = run_optimizer(driver, r["scenario"])
            if res is None:
                if ("light cone not registered" in err or "set not found" in err
                        or "character not registered" in err):
                    err_line = next((ln.strip() for ln in err.splitlines()
                                     if ln.strip().startswith("Error")), "")
                    report.update(status="optimizer_not_covered",
                                  note=f"对方未覆盖：{err_line[:120]}"
                                       "（装备未登记/套装表查无/载体未登记——pass-through 不阻塞）")
                    return _summary(report, _write_report(workdir, report))
                first_line = next((ln.strip() for ln in err.splitlines()
                                   if "Error" in ln), err.splitlines()[0] if err else "")
                r.update(status="driver_error", note=first_line[:200])
                continue
            if defaults_echo is None:
                defaults_echo = {"character": res.get("conditionals"),
                                 "light_cone": res.get("light_cone_conditionals"),
                                 "sets": res.get("set_conditionals")}
            r["theirs"] = res.get("total")
            r["their_hits"] = len(res.get("hits") or [])
        report["conditionals_effective"] = defaults_echo

        # 我方侧：候选模板落 runs 工作目录（<kind>s/<eid>_candidate.yaml 压 data
        # 同 id 生成器草稿）+ 载体 fixture 根（fixtures 在 _equipment_roots 内）
        from hsr_nous.ops.annotator.equipment_nodes import (
            _equipment_roots,
            _stage_candidate,
        )

        _stage_candidate(kind, str(eid), tpl_text, workdir)
        roots = [*(template_roots or []), *_equipment_roots(workdir)]
        hp_ratio = 0.4 if carrier["pins"].get("enemyHpGte50") is False else 1.0
        if kind == "light_cone":
            member_extra: Dict[str, Any] = {
                "light_cone_template": str(eid),
                "light_cone": {"superimposition": superimposition}}
        else:
            slots = ("slot0", "slot1") if str(eid).startswith("3") else (
                "slot0", "slot1", "slot2", "slot3")
            member_extra = {"relics": {s: {"set_id": str(eid)} for s in slots}}
        for r in runnable:
            if r.get("status") == "driver_error":
                continue
            try:
                total, err, n_hits = ours_action_total(
                    carrier["cid"], r, element=carrier["element"], template_roots=roots,
                    enemy_hp_ratio=hp_ratio, member_extra=member_extra,
                    setup=carrier["setup"])
            except Exception as e:  # noqa: BLE001 —— 单行动我方侧炸只记行不上抛
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
