"""打标 DAG 节点工厂（ops/annotator/nodes）——机械节点 + LLM 节点 + 闸路由.

内环形状（shape 纯函数扇出）：compile 闸 fail → [revise#n+1, compile#n+1]；过 → [smoke]；
smoke 过 → [golden_diff 金样对拍（v2 机械闸：白值/技能 id 集/scaling 全表对官方数据锚）]，
三闸 fail 同环打回；预算耗尽 → [human_queue]。每次尝试一等节点，错误输出经 deps 回喂。
LLM 节点 kind="llm" 走 `llm_api` 服务闸；机械节点 `game_data`/`compile` 闸。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.llm import LLMRunner
from hsr_nous.ops.dag import Node

ROOT = Path(__file__).resolve().parents[4]
_QUERY_PY = ROOT / ".agents/skills/query-game-data/query.py"
_CHECK_SH = ROOT / "scripts/annotator.sh"

def _strip_code_fence(text: str) -> str:
    """剥 markdown 代码围栏（```yaml/```——"只输出 YAML 本体"指令 LLM 照犯，
    结构性剥壳兜底：指令照发、围栏照剥（首个真跑 compile 预算耗尽全栽在这）。
    """
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip() + "\n"


#: 证据纪律（五层，AGENTS.md 代码约定）——LLM 节点 system prompt 公共件
_EVIDENCE_RULES = """你是机制打标流水线的证据研究员。纪律（五层证据，不可违背）：
1. 官方文本+数值数据是地基——**中英对照**：EN 措辞纪律可解 CN 歧义（"uses an ability 含终结技 /
uses Skill 仅战技 / uses Skill and Ultimate 明示双类"——语义触发域按 EN 层裁定）；
2. wiki（fandom/米游社）交叉校验——战技点以 BPNeed(tbgd) 为权威、
削韧/回能以 fandom 为权威，fandom 技能类型兜底是已知病灶不许照抄；
3. 社区操作向资料补交互语义；交互语义五项【站位/能量条有无/控制模型(回合玩家操控还是全自动)/
耗产点/目标选择】逐项必答，文本查不到标"待实测"，不脑补；
4. 每项机制标注证据来源（官方文本/wiki/社区/实测/待实测）；
5. 数值档位按提供的数据照抄——action scaling 与 skill_params **全表照抄**（lv1..lvN 每档一行；
取档 index=等级-1：15 行表的 lv10=第 10 行，**不许目测表尾当 lv10**）；注释标档写清 lvN。
6. 结构块速查（编译闸词表，照写别造键）：
- 护盾（无 apply_shield 键——一律 apply_modifier 承载）：shield: {scaling: {def_: 0.24}, flat: 320}
  （scaling/flat 至少其一；可选 accumulate: "池名"（跨件加算同池）+ cap: {multiplier: 3, scaling: {...}, flat: ...}）
- 净化：remove_modifier: {filter: "$mod.kind == 'debuff'", max_count: 1}
  （没有 kind/count 键——filter 是表达式、max_count 是逐目标 LIFO 截断数）
- 目标代数：{pool: allies|enemies|self|all, where: "...", order_by: "$it.<表达式>", take: N,
  mode: deterministic|random}——"最低血% 1 人" = {pool: allies, order_by: "$it.hp / $it.max_hp", take: 1}
  （mode 只有 deterministic/random 两值，没有 lowest_hp_ratio 这类键）。
- action_type 词表：basic/skill/ultimate/follow_up/memosprite_skill/assist——**没有 talent 键**：
  官方 Talent 类攻击写 follow_up（三月七反击族），纯机制天赋落 hooks 不落 actions。
- apply_modifier 的子块键（enable_if/stat_exprs/stat_effects/duration/dispellable/grants_immune 等）
  一律写进 modifier: {...} 块内——写在 effect 层必被键闸打回（1001 实证三轮修不回）。
- $event 字段以事件注册载荷为准：on_turn_start/on_turn_end 的主体是 **actor**（没有 target）——
  "回合开始谁行动/给谁回血"写 $event.actor，写 $event.target 必被载荷闸打回（1001 实证）。
- energy 是内建资源：custom_resources 不许声明 'energy'，gain_resource 也不许写 'energy'
  （能量机制走 action 的 energy_cost/energy_gain + gain_energy 钩——1004/1103 实证）。
- duration 是 int 直给（回合数）——**不是表达式槽**，param() 不许写（万敌嘲讽实证）；
  行迹/秘技等无等级轨道的数值一律写字面值。
- 资源平铺键 = res_+资源 id 逐字：id 无前导下划线→res_charge（单下划线），有→res__vendetta（双）——
  写错必被 res_ 对账闸打回（万敌/1224/1015 实证）。
- action_id 照抄官方技能清单的 id（data_pull 下发），不拼接发明——加强版（1{cid}xx）与原版
  并存时以官方清单为准（1005 卡芙卡 1100501 实证）。
- modifier 层的糖键（accumulate/every_n/tally/window/active_when 等）**未接线**——写了编译期炸；
  护盾池 accumulate 只在 shield 块内合法（1304 实证）。
- action 层 apply_modifiers 的 target 只有 all_enemies/self——目标代数 dict 只在 hook effects 的
  target 用（1111 实证）；表达式不支持 dict 字面量（目标代数 dict 是 target 字段专利，不能嵌进
  函数参数——1202 实证）。
- 形状纪律：scaling_effects 是 mapping（{stat: [source_stat, ratio]}）、grants_immune 是 list
  （["control"] 不是 true）、techniques 块没有 notes 键（备注写注释）、gain_energy 的 target
  只有 all_allies/self/$event.<字段>（1005/1008/1112/1304/1217 实证）。
- 概率门控：effect 层没有 chance 键——固定概率写 condition + mechanic_chance(资源id) 宿主函数
  （1224 实证）；remove_modifier filter 没有 includes 运算符——控制类用 controlled($it)（8007 实证）。
- 内部闩（_前缀资源）虽免声明，但**读前必须有写**——稳妥做法：custom_resources 显式声明
  （current 初始化）或 on_battle_start 置零（白厄 _immune_used 族）；只写不初始化就读=
  运行期"未定义变量"静默死钩（1501 res__punchline 实证）。
- $event.actor=**谁行动**（on_turn_start/on_turn_end 族）；$event.target=**谁被打/谁是目标**
  （on_become_target/on_hp_decrease/before_take_damage 族）——看事件主体选键，别互换
  （1307 实证：on_become_target 写 $event.actor 炸——该事件的"发起者"是 $event.source）。
- before_take_damage 载荷**没有 reason**——该事件只进攻击类伤害（DoT 不走此通道），
  "排除 DoT 只挡攻击"不用写过滤，写了必被载荷闸打回（1008 阿兰实证）。
- remove_modifier filter 的 $mod 字段：modifier_id/modifier_type/debuff_kind/control_kind/
  dispellable/kind——**没有 id/tags**（1112 写 $mod.id 实证）。
- 追加真伤段（deal_damage category: "true" 吃受击事件）**必须防递归**：condition 加
  `$event.damage_type != 'true'`——不然追加段自己也是 on_hp_decrease，自触发无限循环
  （昔涟 141502 先例；1004 瓦尔特时空扭曲撞重入硬帽 128 实证）。
- $event 的资源字段叫 **resource_id** 不叫 resource（on_resource_gain/before_consume/
  after_consume 族——1501 写 $event.resource 实证）。"""


def _prompt_salt(*extra: bytes) -> str:
    """打标提示词指纹（证据纪律/结构块速查 + 锚范例内容）——模块常量/锚文件改动经
    Node.salt 传导缓存失效（executor fn 指纹只覆盖函数体，闭包值漏检的兜底通道）。"""
    h = hashlib.sha256(_EVIDENCE_RULES.encode())
    for b in extra:
        h.update(b)
    return h.hexdigest()[:12]


def _vocabulary_cheatsheet() -> str:
    """闭合词表速查（代码现算——事件契约 + 宿主函数白名单；词表幻觉类的提示词疫苗：
    全名册批实证 未知事件×3/宿主函数不存在×4/未知键×7 占 human_queue 三分一）。
    从代码生成不落手写副本（防腐——bus.py/expression.py 改了速查自动变，salt 同源失效）。"""
    from hsr_nous.sim.bus import DEFAULT_CONTRACT
    from hsr_nous.sim_schema.expression import EFFECT_FUNCTIONS
    events = "、".join(f"{e}({'瀑布' if k == 'waterfall' else '通知'})"
                       for e, k in sorted(DEFAULT_CONTRACT.items()))
    fns = "、".join(sorted(EFFECT_FUNCTIONS))
    return (
        f"闭合词表（表内没有的不许用——用了必被闸打回）：\n"
        f"- 事件契约（hook event 只能从这里选，未登记的自造事件必炸）：{events}\n"
        f"- 宿主函数（表达式里只能调这些）：{fns}\n"
        f"- 其余键名（effect_type/target_type/资源/目标代数键等）照锚范例词表，不认识的键不许造。")


def data_pull_node(cid: str) -> Node:
    """官方数据拉取（query-game-data）：官方文本+params 摘录包。"""
    def fn(_inputs: Dict[str, Any]) -> Dict[str, Any]:
        r = subprocess.run(["python3", str(_QUERY_PY), "character", cid],
                           capture_output=True, text=True, cwd=ROOT, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"query-game-data 失败：{r.stderr[-500:]}")
        d = json.loads(r.stdout)
        # 白值官方管线实值（base_stats 唯一照抄源——hsr-optimizer 双源互证过；1002 丹恒
        # 试点实证：LLM 从社区页捡 1203.048 幻视，官方实值 882，金样打回三轮修不回=
        # 锚未下发是结构根因）
        from hsr_nous.pipeline import calc_character_stats
        base_stats = calc_character_stats(str(d.get("id") or cid), level=80, lang="cn")
        skills = [{"id": s.get("id"), "name_cn": s.get("name_cn"), "type_text": s.get("type_text"),
                   "effect_text": s.get("effect_text"), "desc": s.get("desc"),
                   "params": s.get("params") or []} for s in d.get("skills_detail", [])]
        ranks = [{"id": s.get("id"), "name": s.get("name"), "desc": s.get("desc")}
                 for s in (d.get("ranks_detail") or [])]
        # 大行迹（skill_trees A2/A4/A6 族——本体机制层：免死次数/免疫/充能比例全在这，
        # 漏拉=证据包缺一层（万敌 1404101 水与泥土"致命攻击不清空×3/场"实证）
        trees = [{"id": t.get("id"), "name": t.get("name"), "desc": t.get("desc"),
                  "params_max": (t.get("params") or [None])[-1]}
                 for t in (d.get("skill_trees_detail") or []) if t.get("desc")]
        # 加强版/原版去重（1{cid}xx 系=加强版现役，原版仅历史对照——characters.json
        # skills 清单两版并列实证：花火/黑天鹅/卡芙卡族；slot=id 末两位，同 slot 有
        # 加强版则现役取加强版）——golden 核心集与 draft 建模同口径
        # 加强版判定限本体四类型（Basic/Skill/Ultimate/Talent）——忆灵技/秘技的 1{cid}xx
        # 是独立技能不是加强版（记忆主 1800701 迷迷"坏人！麻烦！" MemospriteSkill 实证：
        # 误判加强版会让 golden 按忆灵技当现役战技要求，draft 按它建模错倍率）
        _CORE_TYPES = ("Basic ATK", "Skill", "Ultimate", "Talent")
        boosted_ids = {str(s_["id"]) for s_ in skills
                       if str(s_["id"]).startswith(f"1{cid}")
                       and s_.get("type_text") in _CORE_TYPES}
        for s_ in skills:
            sid = str(s_["id"])
            s_["version"] = "加强版" if sid in boosted_ids else "原版"
        current_ids = []
        for s_ in skills:
            sid = str(s_["id"])
            slot = sid[-2:]
            if sid in boosted_ids or f"1{cid}{slot}" not in boosted_ids:
                current_ids.append(sid)
        return {"cid": cid, "name_cn": d.get("name_cn") or d.get("name"),
                "name_en": d.get("name") or "",
                "path": d.get("path"), "element": d.get("element"),
                "max_sp": d.get("max_sp"), "base_stats": base_stats,
                "skills": skills, "ranks": ranks, "traces": trees,
                "boosted_ids": sorted(boosted_ids), "current_ids": current_ids}
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


# ---------------------------------------------------------------------------
# 社区调研层（五层③：操作向资料——控制模型/自动施放/站位/耗产点/目标选择）
# ---------------------------------------------------------------------------

def _default_search_fn(query: str, max_results: int) -> List[Dict[str, str]]:
    """ddgs 本地库（deedy5/ddgs——零基建免 key；web_search 服务闸礼貌限速）。"""
    from ddgs import DDGS

    with DDGS() as ddgs:
        return [{"title": r["title"], "url": r["href"], "snippet": r["body"]}
                for r in ddgs.text(query, max_results=max_results)]


def _default_fetch_fn(url: str, cap: int) -> str:
    """httpx 粗提正文（去脚本样式标签；JS 重页（米游社详情）后续走 webbridge 通道）。"""
    import re

    import httpx

    html = httpx.get(url, timeout=15, follow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0"}).text
    text = re.sub(r"(?s)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:cap]


def community_search_node(cid: str, *, search_fn=None, max_queries: int = 4,
                          per_query: int = 4) -> Node:
    """社区检索：官方包+对轴缺口 → 查询 → 去重结果（标题/链接/摘要——进 runs 可溯源）。"""
    search = search_fn or _default_search_fn

    def fn(inputs: Dict[str, Any]) -> List[Dict[str, str]]:
        official = inputs["data_pull"]
        name_cn = str(official["name_cn"])
        skills = official.get("skills", [])
        name_en = official.get("name_en") or ""
        queries = [f"{name_cn} 崩坏星穹铁道 机制 攻略", f"{name_en} hsr guide"]
        if any(str(s.get("id", "")).startswith("114") for s in skills):
            queries.append(f"{name_cn} 忆灵 自动 施放 控制")
        for c in (inputs["crosscheck"].get("conflicts") or [])[:2]:
            queries.append(f"{name_cn} {c.get('name_cn', '')} 战技点 消耗")
        queries = queries[:max_queries]
        out, seen, failed = [], set(), 0
        for q in queries:
            try:
                rows = search(q, per_query)
            except Exception:  # noqa: BLE001 —— 搜索引擎限流/断网属常态（ddgs "No results found"族）：
                failed += 1      # 单查询失败不拖死整层——降级为空层，evidence 有"社区层无结果"口径
                continue
            for r in rows:
                if r["url"] in seen:
                    continue
                seen.add(r["url"])
                out.append({"query": q, **r})
        if failed:
            out.append({"query": "", "title": f"（社区检索失败 ×{failed}——降级空层）",
                        "url": "", "snippet": ""})
        return out
    return Node("community_search", fn, deps=("data_pull", "crosscheck"), service="web_search")


def community_fetch_node(cid: str, *, fetch_fn=None, pages: int = 4, cap: int = 3000) -> Node:
    """社区正文抓取：top N 页 → 粗提正文截段（JS 重页标待 webbridge，不阻塞）。"""
    fetch = fetch_fn or _default_fetch_fn

    def fn(inputs: Dict[str, Any]) -> List[Dict[str, str]]:
        out = []
        for r in (inputs["community_search"] or [])[:pages]:
            if not r.get("url"):
                continue   # 检索失败降级标记（无 url 不抓——只留痕在 search 输出）
            try:
                text = fetch(r["url"], cap)
            except Exception as e:  # noqa: BLE001 —— 单页失败不拖死整层
                text = f"（抓取失败 {type(e).__name__}：{e}）"
            out.append({"url": r["url"], "title": r["title"], "text": text})
        return out
    return Node("community_fetch", fn, deps=("community_search",), service="web_fetch")


def evidence_node(cid: str, llm: LLMRunner) -> Node:
    """证据研究（LLM）：官方包+对轴表+社区包 → 证据笔记（机制结论+五级来源+五项清单+待实测）。"""
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        cross = inputs["crosscheck"]
        community = inputs.get("community_fetch") or []
        community_txt = "\n\n".join(
            f"【社区】{p['title']}（{p['url']}）\n{p['text'][:2000]}" for p in community) \
            or "（社区层无结果——按官方/wiki 层继续，社区相关项标待实测）"
        prompt = (f"角色 {cid} {official['name_cn']}（{official['path']}/{official['element']}，"
                  f"max_sp={official['max_sp']}，"
                  f"白值 calc lv80 实值={json.dumps(official.get('base_stats') or {}, ensure_ascii=False)}"
                  f"——base_stats 唯一照抄源，社区页数值一律以此为终审）。\n"
                  f"官方技能（含满级 params）：{json.dumps(official['skills'], ensure_ascii=False)}\n"
                  f"大行迹（本体机制层——免死/免疫/特殊比例全在这，不许漏评）："
                  f"{json.dumps(official.get('traces') or [], ensure_ascii=False)}\n"
                  f"星魂：{json.dumps(official['ranks'], ensure_ascii=False)}\n"
                  f"三方对轴表：{json.dumps(cross['rows'], ensure_ascii=False)}\n"
                  f"对轴冲突：{json.dumps(cross['conflicts'], ensure_ascii=False)}（{cross['note']}）\n\n"
                  f"社区操作向资料（交互语义取数层——控制模型/自动施放/站位/耗产点/目标选择；"
                  f"冲突裁决序 实测>社区>wiki>单一文本源）：\n{community_txt}\n\n"
                  "输出证据笔记（markdown）：每技能/星魂/忆灵一条——机制结论（含数值档）+ 证据来源"
                  "（官方文本/wiki/社区/实测/待实测）；交互语义五项逐项必答；末尾列待实测清单。"
                  "写不到证据的机制进待收，不许脑补。")
        return llm(system=_EVIDENCE_RULES, prompt=prompt, max_tokens=16000)
    return Node("evidence", fn, deps=("data_pull", "crosscheck", "community_fetch"),
                service="llm_api", kind="llm", salt=_prompt_salt())


def draft_node(cid: str, llm: LLMRunner, anchor_paths: List[Path]) -> Node:
    """模板起草（LLM）：证据笔记+最近似锚模板范例 → DSL YAML。"""
    anchors = "\n\n".join(f"# 锚范例 {p.name}\n{p.read_text(encoding='utf-8')}" for p in anchor_paths)
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        params_table = json.dumps(
            {str(s["id"]): {"name": s.get("name_cn"), "params": s.get("params") or [],
                            "version": s.get("version")}
             for s in official["skills"]}, ensure_ascii=False)
        boosted_note = (
            f"\n⚠ 该角色有加强版技能（1{cid}xx 系）——**现役技能以加强版为准建模**"
            f"（action_id 用加强版 id；原版仅历史对照，不写行动块）。"
            if official.get("boosted_ids") else "")
        core_ids = [str(s_["id"]) for s_ in official["skills"]
                    if str(s_["id"]) in set(official.get("current_ids") or [])
                    and s_.get("type_text") in ("Basic ATK", "Skill", "Ultimate")]
        core_note = (f"\n行动块清单（这些核心技能 id 一个不许缺——金样闸逐一点名："
                     f"{core_ids}——银狼LV.999 三味/花火百花齐放族多点技能不许漏）：\n")
        prompt = (f"把角色 {cid} {official['name_cn']} 的机制写成 DSL YAML 模板（照锚范例格式："
                  f"头注收录/待收清单、skill_params+param() 引用、数值注释标档）。\n"
                  f"base_stats 口径：hp/atk/def 照抄官方管线实值 "
                  f"{json.dumps(official.get('base_stats') or {}, ensure_ascii=False)}"
                  f"（社区页数值一律以此终审）；spd/crit_rate/crit_dmg 可并入行迹**平铺**节点加成"
                  f"（≥管线值——百分比节点走 trace_stat_effects 通道不并入 base_stats）。\n"
                  f"证据笔记：\n{inputs['evidence']}\n\n{anchors}\n\n"
                  f"官方 params 全表（scaling/skill_params 的**唯一照抄源**——逐行照抄，"
                  f"禁止线性内插/目测补行/只写 lv10 单行）：\n{params_table}\n{boosted_note}\n{core_note}\n"
                  "只输出 YAML 本体（首行 actor_id，完整模板），不写解释。收录/待收如实，待收带挡因。\n"
                  "YAML 卫生（违反必被编译闸打回）：① 字符串值含特殊字符（：→ + % ⚠ ❌ 等）一律双引号；"
                  "② 禁止 null/空值——缺数据写注释标待收或给保守默认，不许写 null；③ 键名照锚范例词表，"
                  "不认识的键不许造。\n\n"
                  + _vocabulary_cheatsheet())
        return _strip_code_fence(llm(system=_EVIDENCE_RULES, prompt=prompt, max_tokens=24576))
    return Node("draft", fn, deps=("evidence", "data_pull"), service="llm_api", kind="llm",
                salt=_prompt_salt(_vocabulary_cheatsheet().encode(),
                                  *(p.read_bytes() for p in anchor_paths)))


def _revise_node(n: int, cid: str, llm: LLMRunner, src_dep: str) -> Node:
    """修订（LLM）：闸门错误输出+现稿 → 修稿。src_dep=打回它的闸（compileN/smokeN）。"""
    def fn(inputs: Dict[str, Any]) -> str:
        prev = inputs[src_dep]
        prompt = (f"角色 {cid} 模板被闸门打回，修订。\n错误输出：\n{prev.get('err', '')}\n\n"
                  f"现稿：\n{prev.get('tpl', '')}\n\n"
                  "输出**完整模板**（actor_id 开头，含全部原有内容+你的修订——"
                  "**不是只输出改动段**，只输出改动段必被闸打回）。不写解释。\n"
                  "**先逐字搜索错误输出里的字段名/键名，把每一处出现都改掉**（错误涉及处可能在 "
                  "actions/hooks/eidolons/techniques 任意层级——不许只改注释不动错行）；"
                  "其余不动。**禁止写变更说明/修订注解行**（形如 `- 【本次闸门修订】...`——"
                  "修订理由不进 YAML，未加引号的长句必炸 ParserError）；"
                  "YAML 卫生：字符串含特殊字符一律双引号；禁止 null/空值。\n\n"
                  + _vocabulary_cheatsheet())
        return _strip_code_fence(llm(system=_EVIDENCE_RULES, prompt=prompt, max_tokens=24576))
    return Node(f"revise{n}", fn, deps=(src_dep,), service="llm_api", kind="llm",
                salt=_prompt_salt(_vocabulary_cheatsheet().encode()))


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
            return (golden_diff_node(n, cid, llm, budget, workdir, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_node(nxt, cid, llm, f"smoke{n}"),
                compile_gate_node(nxt, cid, llm, budget, workdir, f"revise{nxt}", staging_root))
        return (_human_queue_node(cid, "smoke 预算耗尽", f"smoke{n}"),)
    return Node(f"smoke{n}", fn, deps=(f"compile{n}",), service="compile", kind="gate", shape=shape)


# ---------------------------------------------------------------------------
# golden_diff 金样对拍（v2 机械闸：LLM 稿 vs 官方数据锚，零 LLM）
# ---------------------------------------------------------------------------

#: 相邻倍率索引（生成器同款——desc"相邻目标…#N[i]%"占位符定位 params[N-1]）
_GOLDEN_BLAST_RE = re.compile(r"相邻目标[^#]{0,30}?#(\d+)\[i\]")


def _golden_mismatches(cid: str, tpl_text: str, official: Dict[str, Any]) -> List[str]:
    """金样对拍：白值实值 / 技能 id 集 / scaling 全表（params 照抄，取档 index=等级-1）.

    三道机械对账（万敌人工闸实证的三类幻视全在这）：① 白值编造（初稿占位值）；
    ② 脑补技能 id / 缺核心行动块；③ scaling 单行误取末行（15 行表 lv15 误标 lv10——
    全表行数对账直接锁死）。返回可读 mismatch 清单（revise 提示词直接消费）。
    """
    import math

    import yaml

    try:
        doc = yaml.safe_load(tpl_text)
    except yaml.YAMLError as e:
        return [f"YAML 解析失败：{e}"]
    if not isinstance(doc, dict):
        return ["YAML 本体不是 mapping"]
    out: List[str] = []
    # ① 白值：hp/atk/def 照抄官方管线实值；spd/crit 行迹加成允许上调（只许高不许低）
    from hsr_nous.pipeline import calc_character_stats
    base = calc_character_stats(cid, level=80, lang="cn")
    dbs = doc.get("base_stats") or {}
    for k in ("hp", "atk", "def"):
        v = dbs.get(k)
        if not isinstance(v, (int, float)) or not math.isclose(
                float(v), float(base[k]), rel_tol=1e-6):
            out.append(f"base_stats.{k}={v!r} ≠ 官方管线实值 {base[k]}"
                       f"（calc_character_stats lv80——白值照抄，不许幻视）")
    for k in ("spd", "crit_rate", "crit_dmg"):
        v = dbs.get(k)
        if not isinstance(v, (int, float)):
            out.append(f"base_stats.{k} 缺失/非数值（官方 {base[k]}；行迹节点加成允许上调，须 ≥ 官方）")
        elif float(v) < float(base[k]) - 1e-9:
            out.append(f"base_stats.{k}={v} < 官方管线 {base[k]}（行迹加成只许上调不许低）")
    # ② 技能 id 集：不脑补（⊆ 官方 owned）、不缺核心（Basic/Skill/Ultimate ⊆ draft，
    # 加强版角色按现役集口径——原版仅历史对照不算缺；用原版 id 建模=错版，勘正指路）
    owned = {str(s["id"]) for s in official["skills"]}
    boosted = set(official.get("boosted_ids") or [])
    current = set(official.get("current_ids") or owned)
    core = {str(s["id"]) for s in official["skills"]
            if str(s["id"]) in current
            and s.get("type_text") in ("Basic ATK", "Skill", "Ultimate")}
    acts = {str(a.get("action_id")): a for a in (doc.get("actions") or []) if isinstance(a, dict)}
    for aid in sorted(set(acts) - owned):
        out.append(f"action {aid} 不在官方技能清单（脑补 id 不许——官方 owned：{sorted(owned)}）")
    for aid in sorted(core - set(acts)):
        out.append(f"官方核心技能 {aid} 缺行动块（Basic/Skill/Ultimate 不许缺——"
                   f"Talent/Technique/忆灵技可落 hooks）")
    for aid in sorted(set(acts) & (owned - current)):
        out.append(f"action {aid} 用了原版 id 建模——该角色现役技能是加强版 "
                   f"{sorted(boosted)}（1{{cid}}xx 系），同 slot 建模以加强版为准")
    # ③ scaling 全表对账：行数 == params 行数；主倍率逐行 == params[i][0]；
    #    相邻倍率按 desc 占位符定位 params[i][N-1]（定位不到退化为值在 row 内）
    params_by_id = {str(s["id"]): s for s in official["skills"]}
    for aid, a in acts.items():
        s = params_by_id.get(aid)
        if s is None:
            continue   # 非官方 id 已在 ② 炸
        params = s.get("params") or []
        sc = a.get("scaling") or []
        if not sc:
            continue   # 非攻击段（钩承担）不强制全表
        vals = [float(next(iter(d.values()))) for d in sc if isinstance(d, dict) and d]
        if len(vals) != len(params):
            out.append(f"action {aid} scaling 行数 {len(vals)} ≠ params 行数 {len(params)}"
                       f"（全表照抄——取档 index=等级-1，不许目测表尾当 lv10）")
        else:
            for i, (v, row) in enumerate(zip(vals, params)):
                if not any(math.isclose(v, float(x), rel_tol=1e-6, abs_tol=1e-12) for x in row):
                    out.append(f"action {aid} scaling[{i}]={v} 不在 params[{i}]={row} 内"
                               f"（lv{i+1} 主倍率对不上——行内值集对账：倍率列位置"
                               f"（#N 占位符语义）归人工闸判，机械闸只对行数与值）")
                    break
        sb = a.get("scaling_blast") or []
        if sb:
            bvals = [float(next(iter(d.values()))) for d in sb if isinstance(d, dict) and d]
            m = _GOLDEN_BLAST_RE.search(s.get("desc") or "")
            idx = int(m.group(1)) - 1 if m and int(m.group(1)) >= 2 else None
            if len(bvals) != len(params):
                out.append(f"action {aid} scaling_blast 行数 {len(bvals)} ≠ params 行数 {len(params)}")
            else:
                for i, (v, row) in enumerate(zip(bvals, params)):
                    hit = (idx is not None and len(row) > idx
                           and math.isclose(v, float(row[idx]), rel_tol=1e-6, abs_tol=1e-12))
                    loose = any(math.isclose(v, float(x), rel_tol=1e-6, abs_tol=1e-12) for x in row)
                    if not (hit or (idx is None and loose)):
                        where = f"params[{i}][{idx}]" if idx is not None else f"params[{i}]={row} 内"
                        out.append(f"action {aid} scaling_blast[{i}]={v} ≠ {where}（相邻倍率对不上）")
                        break
    return out


def golden_diff_node(n: int, cid: str, llm: LLMRunner, budget: int,
                     workdir: Path, staging_root: Optional[Path] = None) -> Node:
    """金样对拍闸（fn 机械对账）+ shape 纯路由：fail → 回 revise/compile 内环；过 → finalize。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[f"smoke{n}"]
        mismatches = _golden_mismatches(cid, prev["tpl"], inputs["data_pull"])
        err = "金样对拍打回（逐条修，不许动其他）：\n" + "\n".join(
            f"{i + 1}. {m}" for i, m in enumerate(mismatches))
        return {"ok": not mismatches, "tpl": prev["tpl"],
                "err": "" if not mismatches else err, "path": prev["path"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (_finalize_node(cid, n, staging_root, src_dep=f"golden{n}"),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_node(nxt, cid, llm, f"golden{n}"),
                compile_gate_node(nxt, cid, llm, budget, workdir, f"revise{nxt}", staging_root))
        return (_human_queue_node(cid, "golden_diff 预算耗尽", f"golden{n}"),)
    return Node(f"golden{n}", fn, deps=(f"smoke{n}", "data_pull"),
                service="compile", kind="gate", shape=shape)


def _finalize_node(cid: str, n: int, staging_root: Optional[Path] = None,
                   src_dep: Optional[str] = None) -> Node:
    """定稿：写 staging 模板 + 证据笔记（候选包，合并走人工闸——本节点不 git）。

    src_dep=供稿闸（v1=smoke#n；v2 金样对拍接入后=golden#n——模板从该闸的输出取）。
    """
    dep = src_dep or f"smoke{n}"

    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[dep]
        official = inputs["data_pull"]
        staging = staging_root or (ROOT / "data/annotator/staging")
        notes = (staging_root / "notes") if staging_root else (ROOT / "data/annotator/notes")
        staging.mkdir(parents=True, exist_ok=True)
        notes.mkdir(parents=True, exist_ok=True)
        tpl_path = staging / f"{cid}_{official['name_cn']}.yaml"
        tpl_path.write_text(prev["tpl"], encoding="utf-8")
        notes_path = notes / f"{cid}.md"
        notes_path.write_text(inputs["evidence"], encoding="utf-8")
        return {"staging": str(tpl_path), "notes": str(notes_path), "review": "ready_for_human"}
    return Node("finalize", fn, deps=(dep, "evidence", "data_pull"), kind="mechanical")


def _human_queue_node(cid: str, reason: str, src_dep: str) -> Node:
    """人工队列：预算耗尽/结构性失败——失败轨迹打包等人工（本节点即终点，不扇出；
    deps 挂打回它的闸——空 deps 会在图启动时被立即执行，闸路由节点不许悬空）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[src_dep]
        return {"review": "needs_human", "reason": reason, "cid": cid,
                "trail": prev.get("err", ""), "path": prev.get("path", "")}
    return Node("human_queue", fn, deps=(src_dep,), kind="human")
