"""打标 DAG 节点工厂（ops/annotator/nodes）——机械节点 + LLM 节点 + 闸路由.

内环形状（shape 纯函数扇出）：compile 闸 fail → [revise#n+1, compile#n+1]；过 → [smoke]；
smoke 同理；预算耗尽 → [human_queue]。每次尝试一等节点，错误输出经 deps 回喂。
LLM 节点 kind="llm" 走 `llm_api` 服务闸；机械节点 `game_data`/`compile` 闸。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.llm import LLMRunner
from hsr_nous.ops.dag import Node

ROOT = Path(__file__).resolve().parents[4]
_QUERY_PY = ROOT / ".agents/skills/query-game-data/query.py"
_CHECK_SH = ROOT / "scripts/annotator.sh"

#: 证据纪律（五层，AGENTS.md 代码约定）——LLM 节点 system prompt 公共件
_EVIDENCE_RULES = """你是机制打标流水线的证据研究员。纪律（五层证据，不可违背）：
1. 官方文本+数值数据是地基；2. wiki（fandom/米游社）交叉校验——战技点以 BPNeed(tbgd) 为权威、
削韧/回能以 fandom 为权威，fandom 技能类型兜底是已知病灶不许照抄；
3. 交互语义五项【站位/能量条有无/控制模型(回合玩家操控还是全自动)/耗产点/目标选择】逐项必答，
文本查不到标"待实测"，不脑补；4. 每项机制标注证据来源（官方文本/wiki/社区/实测/待实测）；
5. 数值档位按提供的数据照抄，取档约定 lv10（params 第 10 档）。"""


def data_pull_node(cid: str) -> Node:
    """官方数据拉取（query-game-data）：官方文本+params 摘录包。"""
    def fn(_inputs: Dict[str, Any]) -> Dict[str, Any]:
        r = subprocess.run(["python3", str(_QUERY_PY), "character", cid],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"query-game-data 失败：{r.stderr[-500:]}")
        d = json.loads(r.stdout)
        skills = [{"id": s.get("id"), "name_cn": s.get("name_cn"), "type_text": s.get("type_text"),
                   "effect_text": s.get("effect_text"), "desc": s.get("desc"),
                   "params_max": (s.get("params") or [None])[-1]} for s in d.get("skills_detail", [])]
        ranks = [{"id": s.get("id"), "name": s.get("name"), "desc": s.get("desc")}
                 for s in (d.get("ranks_detail") or [])]
        return {"cid": cid, "name_cn": d.get("name_cn") or d.get("name"),
                "path": d.get("path"), "element": d.get("element"),
                "max_sp": d.get("max_sp"), "skills": skills, "ranks": ranks}
    return Node("data_pull", fn, service="game_data")


def crosscheck_node(cid: str) -> Node:
    """三方对轴（战技点/回能/削韧/能量上限）——tbgd 战技点权威，fandom 削韧回能，米游社标签。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        official = inputs["data_pull"]
        tbgd = json.loads((ROOT / "data/tbgd_skill_data.json").read_text(encoding="utf-8"))["skills"]
        mys = json.loads((ROOT / "data/miyoushe_skill_data.json").read_text(encoding="utf-8"))[
            "characters"].get(cid, {})
        fandom_all = json.loads((ROOT / "data/fandom_skill_data.json").read_text(encoding="utf-8"))
        fandom = fandom_all.get(cid, {})
        mys_skills = {s.get("name"): s for s in mys.get("skills", [])}
        rows = []
        for s in official["skills"]:
            sid = str(s["id"])
            t = tbgd.get(sid, {})
            m = mys_skills.get(s.get("name_cn"), {})
            rows.append({
                "id": sid, "name_cn": s.get("name_cn"), "type_text": s.get("type_text"),
                "sp_cost_tbgd": t.get("sp_cost"), "sp_gain_tbgd": t.get("sp_gain"),
                "energy_tbgd": t.get("energy_gen"), "mys_sub_tag": m.get("sub_tag"),
                "fandom": {k: fandom.get(k) for k in ()},  # fandom 结构各异，v1 摘米游社/tbgd 即可
            })
        conflicts = []
        for r in rows:
            tags = r["mys_sub_tag"] or []
            sp = r["sp_cost_tbgd"]
            if sp is None or not tags:
                continue
            has_cost_tag = any("消耗战技点" in t for t in tags)
            if (sp == 0) == has_cost_tag:
                conflicts.append({**r, "why": f"tbgd sp_cost={sp} ↔ 米游社"
                                              f"{'有' if has_cost_tag else '无'}消耗标 不一致"})
        return {"rows": rows, "conflicts": conflicts,
                "note": "sp_cost 以 tbgd 为权威；米游社 sub_tag 无'消耗战技点/技能点'标=不耗不产"}
    return Node("crosscheck", fn, deps=("data_pull",), service="game_data")


def evidence_node(cid: str, llm: LLMRunner) -> Node:
    """证据研究（LLM）：官方包+对轴表 → 证据笔记（机制结论+五级来源+五项清单+待实测）。"""
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        cross = inputs["crosscheck"]
        prompt = (f"角色 {cid} {official['name_cn']}（{official['path']}/{official['element']}，"
                  f"max_sp={official['max_sp']}）。\n"
                  f"官方技能（含满级 params）：{json.dumps(official['skills'], ensure_ascii=False)}\n"
                  f"星魂：{json.dumps(official['ranks'], ensure_ascii=False)}\n"
                  f"三方对轴表：{json.dumps(cross['rows'], ensure_ascii=False)}\n"
                  f"对轴冲突：{json.dumps(cross['conflicts'], ensure_ascii=False)}（{cross['note']}）\n\n"
                  "输出证据笔记（markdown）：每技能/星魂/忆灵一条——机制结论（含数值档）+ 证据来源"
                  "（官方文本/wiki/社区/实测/待实测）；交互语义五项逐项必答；末尾列待实测清单。"
                  "写不到证据的机制进待收，不许脑补。")
        return llm(system=_EVIDENCE_RULES, prompt=prompt)
    return Node("evidence", fn, deps=("data_pull", "crosscheck"), service="llm_api", kind="llm")


def draft_node(cid: str, llm: LLMRunner, anchor_paths: List[Path]) -> Node:
    """模板起草（LLM）：证据笔记+最近似锚模板范例 → DSL YAML。"""
    anchors = "\n\n".join(f"# 锚范例 {p.name}\n{p.read_text(encoding='utf-8')}" for p in anchor_paths)
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        prompt = (f"把角色 {cid} {official['name_cn']} 的机制写成 DSL YAML 模板（照锚范例格式："
                  f"头注收录/待收清单、skill_params+param() 引用、数值注释标档）。\n"
                  f"证据笔记：\n{inputs['evidence']}\n\n{anchors}\n\n"
                  "只输出 YAML 本体（首行 actor_id），不写解释。收录/待收如实，待收带挡因。")
        return llm(system=_EVIDENCE_RULES, prompt=prompt)
    return Node("draft", fn, deps=("evidence", "data_pull"), service="llm_api", kind="llm")


def _revise_node(n: int, cid: str, llm: LLMRunner, src_dep: str) -> Node:
    """修订（LLM）：闸门错误输出+现稿 → 修稿。src_dep=打回它的闸（compileN/smokeN）。"""
    def fn(inputs: Dict[str, Any]) -> str:
        prev = inputs[src_dep]
        prompt = (f"角色 {cid} 模板被闸门打回，修订。\n错误输出：\n{prev.get('err', '')}\n\n"
                  f"现稿：\n{prev.get('tpl', '')}\n\n"
                  "只输出修订后 YAML 本体，不写解释；只修错误涉及处，别动其他。")
        return llm(system=_EVIDENCE_RULES, prompt=prompt)
    return Node(f"revise{n}", fn, deps=(src_dep,), service="llm_api", kind="llm")


def _run_check(tpl_path: Path, mode: str) -> "tuple[bool, str]":
    r = subprocess.run(["bash", str(_CHECK_SH), mode, str(tpl_path)],
                       capture_output=True, text=True, cwd=ROOT, timeout=600)
    out = (r.stdout or "") + (r.stderr or "")
    return (r.returncode == 0 and "PASS" in out), out[-2000:]


def compile_gate_node(n: int, cid: str, llm: LLMRunner, budget: int,
                      workdir: Path, src_dep: str,
                      staging_root: Optional[Path] = None) -> Node:
    """编译闸（fn 干活：写稿跑 check）+ shape 纯路由（内环本体：fail → revise+compile
    （预算内）/ human_queue（预算尽）；过 → smoke 闸）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        tpl = inputs[src_dep]
        p = workdir / f"{cid}_compile{n}.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tpl, encoding="utf-8")
        ok, out = _run_check(p, "check")
        return {"ok": ok, "tpl": tpl, "err": "" if ok else out, "path": str(p)}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (_smoke_gate_node(n, cid, llm, budget, workdir, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_node(nxt, cid, llm, f"compile{n}"),
                compile_gate_node(nxt, cid, llm, budget, workdir, f"revise{nxt}", staging_root))
        return (_human_queue_node(cid, "compile 预算耗尽", f"compile{n}"),)
    return Node(f"compile{n}", fn, deps=(src_dep,), service="compile", kind="gate", shape=shape)


def _smoke_gate_node(n: int, cid: str, llm: LLMRunner, budget: int, workdir: Path,
                     staging_root: Optional[Path] = None) -> Node:
    """冒烟闸（fn 干活）+ shape 纯路由：fail → 回 revise/compile 内环；过 → finalize。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[f"compile{n}"]
        ok, out = _run_check(Path(prev["path"]), "smoke")
        return {"ok": ok, "tpl": prev["tpl"], "err": "" if ok else out, "path": prev["path"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (_finalize_node(cid, n, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_node(nxt, cid, llm, f"smoke{n}"),
                compile_gate_node(nxt, cid, llm, budget, workdir, f"revise{nxt}", staging_root))
        return (_human_queue_node(cid, "smoke 预算耗尽", f"smoke{n}"),)
    return Node(f"smoke{n}", fn, deps=(f"compile{n}",), service="compile", kind="gate", shape=shape)


def _finalize_node(cid: str, n: int, staging_root: Optional[Path] = None) -> Node:
    """定稿：写 staging 模板 + 证据笔记（候选包，合并走人工闸——本节点不 git）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        smoke = inputs[f"smoke{n}"]
        official = inputs["data_pull"]
        staging = staging_root or (ROOT / "data/annotator/staging")
        notes = (staging_root / "notes") if staging_root else (ROOT / "data/annotator/notes")
        staging.mkdir(parents=True, exist_ok=True)
        notes.mkdir(parents=True, exist_ok=True)
        tpl_path = staging / f"{cid}_{official['name_cn']}.yaml"
        tpl_path.write_text(smoke["tpl"], encoding="utf-8")
        notes_path = notes / f"{cid}.md"
        notes_path.write_text(inputs["evidence"], encoding="utf-8")
        return {"staging": str(tpl_path), "notes": str(notes_path), "review": "ready_for_human"}
    return Node("finalize", fn, deps=(f"smoke{n}", "evidence", "data_pull"), kind="mechanical")


def _human_queue_node(cid: str, reason: str, src_dep: str) -> Node:
    """人工队列：预算耗尽/结构性失败——失败轨迹打包等人工（本节点即终点，不扇出；
    deps 挂打回它的闸——空 deps 会在图启动时被立即执行，闸路由节点不许悬空）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[src_dep]
        return {"review": "needs_human", "reason": reason, "cid": cid,
                "trail": prev.get("err", ""), "path": prev.get("path", "")}
    return Node("human_queue", fn, deps=(src_dep,), kind="human")
