"""打标 DAG 装备分支节点（ops/annotator/equipment_nodes）——光锥/遗器打标，与角色版同构不同参.

链形同角色版（节点 id 全同，运行图形状一致）：data_pull → crosscheck →
community_search/fetch → evidence(LLM) → draft(LLM) → compile1（内环：fail →
revise#n+compile#n；过 → smoke#n → golden#n 金样对拍 → oracle_report 对拍报告
（报告型闸：借载体角色穿装备逐核心行动与对方 equipment 场景比值，异常不打回不
阻塞，staging notes 挂异常数）→ finalize；预算尽 → human_queue）。

与角色版的三点不同：

1. **draft LLM 只产 hooks 块，不重生成已有件**——光锥只许顶层 `hooks:` 块；遗器只许
   `set_2pc:`/`set_4pc:` 两块且每块只含 `hooks:` 子键。compile 闸 fn 把 hooks **机械合并**
   进生成器草稿（白值/lookup 表/绑定/2pc stat_effects 原样保留——LLM 永不重写数值区，
   面板幻觉构造上不可能）；越权输出（多顶层键/块内多键）在合并处即拒，走内环 revise。
2. **编译/冒烟闸走装备 harness（in-process）**——inline 测试角色 + `light_cone_template` /
   `relics` 四件引用，`compile_encounter(template_roots=[候选临时根, fixtures,
   data/sim_templates])`（候选根压同 id 生成器草稿）；冒烟=expected 模式 fixed_av 截断局
   断言不炸 + 声明的无条件 on_battle_start modifier 经 after_apply_modifier 事件核实施加
   （角色版的 annotator.sh check/smoke 是角色形 harness，不复用）。
3. **golden_diff 对账数值区 vs 数据锚**——光锥白值（calc_light_cone_stats lv80）+
   lookup 表行数/行值（ranks params 全档）；遗器 2pc/4pc stat_effects（生成器重算）。
   对不上=生成器草稿 drift（数值区机械合并 LLM 改不动），打回信息指路重跑
   template_generator 再收编；hooks 层空缺（desc 非空但 hooks 空）同闸打回。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.llm import LLMRunner
from hsr_nous.ops.annotator.nodes import (
    ROOT,
    _community_txt,
    _default_fetch_fn,
    _default_search_fn,
    _human_queue_node,
    _oracle_salt,
    _strip_code_fence,
    _vocabulary_cheatsheet,
)
from hsr_nous.ops.dag import Node

#: 装备证据纪律（五层，AGENTS.md 代码约定）——装备分支 LLM 节点 system prompt 公共件；
#: 与角色版 _EVIDENCE_RULES 同构，但交互语义项换成装备面（叠加/刷新/叠影差分/持续与驱散）
_EQUIPMENT_RULES = """你是装备机制打标流水线的证据研究员。纪律（五层证据，不可违背）：
1. 官方 desc + params 是地基——**中英对照**（EN 措辞纪律可解 CN 歧义，语义触发域按 EN 层裁定）；
2. wiki（fandom/米游社）交叉校验——对轴杀数据源偏差，单一文本源结论标源；
3. 社区操作向资料补交互语义；装备交互语义五项【触发时机（挂谁身上/什么事件）/
叠加与刷新语义（可叠几层/重复触发刷新还是叠加）/持续与驱散（回合数/是否可驱散）/
叠影差分（S1..S5 哪几档变）/作用范围（装备者自身/全队/敌方）】逐项必答，
文本查不到标"待实测"，**不脑补——官方 desc 没写的效果不许造**；
4. 每项机制标注证据来源（官方文本/wiki/社区/实测/待实测）；
5. 数值档位按提供的数据照抄——叠影 params **全表照抄**（S1..S5 每档一列；desc 的
#N[i] 占位符按列定位：#1[i] ↔ params 第 1 列，取档 index=叠影-1——不许目测列位置）；
6. hooks 词表只许用编译闸能过的 effect_type（闭合词表随 draft 提示下发）——
超词表机制进待收清单，不许自造键。
结构块速查（装备层高频件，照写别造键）：
- 开战 buff：event: "on_battle_start" + apply_modifier（duration 0=常驻，N=回合数）；
  触发型 buff 挂对应事件钩（on_ultimate/on_become_target/on_hp_decrease 等，词表见下发）
- 叠影参数引用：$self.<列名>（生成器绑定层已把 lookup_tables 各列绑成装备者参数——
  desc 的 #N[i] ↔ lookup_tables 第 N 列 ↔ $self.<列名>，hooks 里引用参数名不抄字面量）
- duration 是 int 直给（回合数）——**不是表达式槽**，叠影变档的持续时间取 S1 值并注释标待收
- apply_modifier 的子块键（stat_effects/stat_exprs/enable_if/duration/dispellable/
  grants_immune 等）一律写进 modifier: {...} 块内——写在 effect 层必被键闸打回
- 战技点：gain_skill_point（amount 直给）；回能：gain_energy（target 只有
  all_allies/self/$event.<字段>）；拉条：advance_action；推条：delay_action
- target 语义：self=装备者自身，all_allies=我方全体，all_enemies=敌方全体——
  我方指向技不许写 single（single=敌方单体）
- $event 字段以事件注册载荷为准：on_turn_start/on_turn_end 的主体是 actor；
  on_become_target/on_hp_decrease 的主体（被打者）是 target、发起者是 source——
  看事件主体选键，别互换
- modifier_id 命名：装备词大写前缀（如 LC_<id>_xxx / SET_<id>_xxx），全大写下划线分隔
- YAML 卫生：注释内嵌英文双引号必须改「」；字符串含 :/#/& 等一律双引号；
  列表项别带尾逗号；禁止 null/空值（缺数据注释标待收，不许写 null）。

实证翻车禁止清单（首批 225 装备打标+验收实证，以下写法一律判错——照正解写）：
- hook 键 `trigger` 不存在——事件键是 `event`；`max_stacks` 不存在——层数上限键是
  `max_stack`；`effect_hit_rate` 不存在——`effect_hit`；元素 `lightning` 不存在——`thunder`
- `$event.<actor/source/target> == $self` / `== self` / `== 'self'` 恒为假（$self 是命名
  空间对象不是 id 串）——装备者判定一律 `$event.x == $self.actor_id`
- `stat_of($self, 'max_energy')` 读不到（effective_stats 无此键，恒 0=死条件）——
  急切槽 `$self.max_energy`；stat_of 必须两参 stat_of(<目标>, '<键>')
- `resource_of($self)` 单参非法——两参 `resource_of($self, '<资源id>')`；能量上限/当前
  能量用 `$self.max_energy`/`$self.energy`（内建字段，不走自定义资源）
- `count_team('ally')` 把 'ally' 当命途计（恒 0）——命途计数 `count_team(path='<英文命途>')`，
  在场人数 `count($team.actor_id)`，命途判定 `path_of($self)`
- stat 键只许 _KNOWN_STAT_KEYS 或 `dmg_<元素>` 前缀——`basic_atk_dmg_bonus`/
  `skill_dmg_bonus`/`followup_dmg(_bonus)`/`ult_dmg`/`ultimate_dmg(_bonus)`/
  `def_ignore(_pct)`/`dmg_taken(_increase)`/`energy_regen_rate`/`lightning_dmg_pct`/
  `ultimate_dmg_flat`/`shield`（stat_effects 里）全是无消费端死键。正解：类型增伤桶
  `dmg_<action_type>_dmg_boost`、无视防御 `def_pen`、承伤易伤 `vulnerability`、
  回能效率 `energy_regen`、元素增伤 `dmg_<元素>`
- 绑定参数名**禁止与面板键同名**（crit_rate/crit_dmg/break_effect/energy_regen/
  effect_res/effect_hit）——$self 面板优先解析会读错值，参数名一律 `param_<N>` 形
- `max_stack`/`duration`/`stacks` 槽**只收 int 字面量**——写表达式运行期必炸；
  叠影变档取 S1 值+注释标待收；「stat 值随层数变」用 `stat_exprs`（现场求值
  `×stacks($self,'<id>')`），`stat_effects` 不随 stacks 乘算
- 烘焙表达式件（stat_effects 含表达式）必须 `stack_mode: "replace"`——refresh 重挂
  只刷层数/时长，旧烘焙值死挂
- 「随机 N 选一」**不许把 N 个分支全挂常驻**——选一中：随机原语未落地时整机制
  转待收，不许伪随机=全真
- 官方「命途为 X 时」条件句必须落 `path_of($self) == '<path 英文小写>'`——漏写=
  全角色白吃机制；desc 无此句不许自加门
- 纯数值件（2pc 属性/常驻面板段）走 `stat_effects` **不需要 hooks**——生成器数值区
  已承载，加 hook/modifier = 重复+可能错键
- on_action/on_ultimate 结算后才挂的增伤，**触发当次吃不到**——要当次吃：
  on_become_target（伤害前）/常驻 enable_if 条件光环/hit_condition 命中域三选一
- owner 过滤是义务不是选项：on_action/on_ultimate/on_turn_start/on_kill/
  after_being_hit 全广播——装备者判定 `$event.actor|source == $self.actor_id` 漏写=
  全世界都给装备者叠层"""


def _equip_salt(*extra: bytes) -> str:
    """装备提示词指纹（证据纪律 + 锚范例内容）——经 Node.salt 传导缓存失效（同角色版通道）。"""
    h = hashlib.sha256(_EQUIPMENT_RULES.encode())
    for b in extra:
        h.update(b)
    return h.hexdigest()[:12]


def _equipment_cheatsheet() -> str:
    """装备闭合词表速查（代码现算——事件契约 + 宿主函数 + effect_type + target 选择器；
    从代码生成不落手写副本，防腐同角色版）。"""
    from hsr_nous.sim_schema.effect_types import ENGINE_EFFECT_TYPES, HOOK_TARGET_SELECTORS

    return (_vocabulary_cheatsheet() + "\n"
            f"- effect_type（hooks effects 只许用这些——词表外必被编译闸打回）："
            f"{'、'.join(sorted(ENGINE_EFFECT_TYPES))}\n"
            f"- hook target 选择器：{'、'.join(sorted(HOOK_TARGET_SELECTORS))}"
            f"（另支持 $event.<字段> 动态寻址）")


# ---------------------------------------------------------------------------
# 数据层（机械：生成器草稿 + 官方 desc/params/properties + 白值锚）
# ---------------------------------------------------------------------------

def _load_draft(kind_dir: str, eid: str) -> "tuple[str, Dict[str, Any]]":
    """读生成器草稿全文（data/sim_templates/<kind_dir>/<eid>_*.yaml——打标的数值区底稿）。"""
    import glob as _glob

    import yaml

    hits = sorted(h for h in _glob.glob(str(ROOT / "data/sim_templates" / kind_dir / f"{eid}_*.yaml"))
                  if not h.endswith("_legacy.yaml"))
    if not hits:
        raise RuntimeError(
            f"生成器草稿缺失：data/sim_templates/{kind_dir}/{eid}_*.yaml"
            f"（先跑 adapters/template_generator 生成再收编）")
    if len(hits) > 1:
        raise RuntimeError(f"生成器草稿撞名（同 id {len(hits)} 个）：{hits}——删到只剩一个")
    text = Path(hits[0]).read_text(encoding="utf-8")
    return text, (yaml.safe_load(text) or {})


def data_pull_lc_node(lc_id: str) -> Node:
    """光锥官方数据拉取：生成器草稿全文 + 叠影 desc/params/properties + 白值锚（中英双轨 desc）。"""
    def fn(_inputs: Dict[str, Any]) -> Dict[str, Any]:
        from hsr_nous.pipeline import calc_light_cone_stats, get_light_cone, get_light_cone_ranks

        draft_text, draft_doc = _load_draft("light_cones", lc_id)
        raw_en = get_light_cone(str(lc_id), lang="en") or {}
        ranks_cn = get_light_cone_ranks(str(lc_id), lang="cn") or {}
        ranks_en = get_light_cone_ranks(str(lc_id), lang="en") or {}
        return {"kind": "light_cone", "id": str(lc_id),
                "name_cn": draft_doc.get("name") or str(lc_id),
                "name_en": raw_en.get("name") or "",
                "path": draft_doc.get("path") or "",
                "rarity": draft_doc.get("rarity"),
                "draft_text": draft_text,
                "desc_cn": ranks_cn.get("desc") or "",
                "desc_en": ranks_en.get("desc") or "",
                "params": ranks_cn.get("params") or [],
                "properties": ranks_cn.get("properties") or [],
                # 白值锚（calc lv80 实值——crosscheck/golden 对轴唯一照抄源）
                "base_stats": calc_light_cone_stats(str(lc_id), level=80, lang="cn"),
                "lookup_names": sorted((draft_doc.get("lookup_tables") or {}).keys())}
    return Node("data_pull", fn, service="game_data")


def data_pull_relic_node(set_id: str) -> Node:
    """遗器套装官方数据拉取：生成器草稿全文 + 2pc/4pc desc（中英双轨）+ properties 属性表。"""
    def fn(_inputs: Dict[str, Any]) -> Dict[str, Any]:
        from hsr_nous.pipeline import get_relic_set

        draft_text, draft_doc = _load_draft("relics", set_id)
        raw_cn = get_relic_set(str(set_id), lang="cn") or {}
        raw_en = get_relic_set(str(set_id), lang="en") or {}
        desc_cn = raw_cn.get("desc") or []
        desc_en = raw_en.get("desc") or []
        return {"kind": "relic", "id": str(set_id),
                "name_cn": draft_doc.get("name") or raw_cn.get("name") or str(set_id),
                "name_en": raw_en.get("name") or "",
                "draft_text": draft_text,
                "desc_2pc_cn": desc_cn[0] if len(desc_cn) > 0 else "",
                "desc_4pc_cn": desc_cn[1] if len(desc_cn) > 1 else "",
                "desc_2pc_en": desc_en[0] if len(desc_en) > 0 else "",
                "desc_4pc_en": desc_en[1] if len(desc_en) > 1 else "",
                "properties": raw_cn.get("properties") or []}
    return Node("data_pull", fn, service="game_data")


# ---------------------------------------------------------------------------
# 对轴层（机械，无 LLM：草稿数值区 vs 数据锚；conflict=drift，只报告不阻塞）
# ---------------------------------------------------------------------------

def crosscheck_lc_node(lc_id: str) -> Node:
    """光锥对轴：草稿白值/叠影表行数与行值/绑定-表一致 vs 数据锚（calc + ranks params）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        import math

        import yaml

        official = inputs["data_pull"]
        doc = yaml.safe_load(official["draft_text"]) or {}
        rows: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        for k in ("hp", "atk", "def"):
            v = (doc.get("base_stats") or {}).get(k)
            w = (official.get("base_stats") or {}).get(k)
            ok = isinstance(v, (int, float)) and w is not None and math.isclose(
                float(v), float(w), rel_tol=1e-6)
            rows.append({"item": f"base_stats.{k}", "draft": v, "anchor": w, "ok": ok})
            if not ok:
                conflicts.append({"item": f"base_stats.{k}",
                                  "why": f"草稿 {v!r} ≠ 数据锚 {w}（drift——重跑生成器）"})
        params = official.get("params") or []
        for name, col in sorted((doc.get("lookup_tables") or {}).items()):
            bad = next((i for i, v in enumerate(col)
                        if i >= len(params) or not any(
                    math.isclose(float(v), float(x), rel_tol=1e-6, abs_tol=1e-12)
                    for x in params[i])), None)
            ok = len(col) == len(params) and bad is None
            rows.append({"item": f"lookup_tables.{name}", "rows": len(col),
                         "anchor_rows": len(params), "ok": ok})
            if not ok:
                conflicts.append({"item": f"lookup_tables.{name}",
                                  "why": f"行数 {len(col)} ≠ 叠影档数 {len(params)}"
                                         + (f" 或 S{bad + 1} 行值 {col[bad]} 不在 params 行内"
                                            if bad is not None and bad < len(col) else "")})
        tables = set((doc.get("lookup_tables") or {}).keys())
        bound = set()
        for stmt in doc.get("variable_bindings") or []:
            m = re.match(r'^\s*self\.(\w+)\s*=\s*lookup_table\("(\w+)"', str(stmt))
            if m:
                bound.add(m.group(2))
        rows.append({"item": "variable_bindings", "draft": sorted(bound),
                     "anchor": sorted(tables), "ok": bound == tables})
        if bound != tables:
            conflicts.append({"item": "variable_bindings",
                              "why": f"绑定表集 {sorted(bound)} ≠ lookup 表集 {sorted(tables)}"})
        return {"rows": rows, "conflicts": conflicts,
                "note": "光锥数值区锚=calc_light_cone_stats/ranks params——"
                        "conflict=草稿 drift，重跑 adapters/template_generator 再收编"}
    return Node("crosscheck", fn, deps=("data_pull",), service="game_data")


def crosscheck_relic_node(set_id: str) -> Node:
    """遗器对轴：草稿 2pc/4pc stat_effects 与 desc vs 数据锚（生成器重算 + 官方 desc 原文）。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        import math

        import yaml

        official = inputs["data_pull"]
        doc = yaml.safe_load(official["draft_text"]) or {}
        from hsr_nous.adapters.template_generator import generate_relic_set_template
        fresh = generate_relic_set_template(str(set_id), lang="cn")
        rows: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        for pc, desc_key in (("set_2pc", "desc_2pc_cn"), ("set_4pc", "desc_4pc_cn")):
            want = (fresh.get(pc) or {}).get("stat_effects") or {}
            got = (doc.get(pc) or {}).get("stat_effects") or {}
            for k in sorted(set(want) | set(got)):
                w, g = want.get(k), got.get(k)
                ok = (w is not None and g is not None
                      and math.isclose(float(g), float(w), rel_tol=1e-6))
                rows.append({"item": f"{pc}.stat_effects.{k}", "draft": g, "anchor": w, "ok": ok})
                if not ok:
                    conflicts.append({"item": f"{pc}.stat_effects.{k}",
                                      "why": f"草稿 {g!r} vs 数据锚 {w!r}（drift——重跑生成器）"})
            d_draft = (doc.get(pc) or {}).get("desc") or ""
            d_official = official.get(desc_key) or ""
            rows.append({"item": f"{pc}.desc", "ok": d_draft == d_official})
            if d_draft != d_official:
                conflicts.append({"item": f"{pc}.desc",
                                  "why": "desc 原文与官方不一致（drift——重跑生成器）"})
        return {"rows": rows, "conflicts": conflicts,
                "note": "遗器数值区锚=生成器重算（properties 直映射）+ 官方 desc 原文——"
                        "conflict=草稿 drift，重跑 adapters/template_generator 再收编"}
    return Node("crosscheck", fn, deps=("data_pull",), service="game_data")


# ---------------------------------------------------------------------------
# 社区调研层（装备面：叠加/刷新/触发语义——光锥叠影差分、套装触发条件有实测需求）
# ---------------------------------------------------------------------------

def community_search_equipment_node(kind: str, eid: str, *, search_fn=None,
                                    max_queries: int = 3, per_query: int = 4) -> Node:
    """装备社区检索：机制/叠加刷新/实测向查询 → 去重结果（失败降级空层，同角色版纪律）。"""
    search = search_fn or _default_search_fn

    def fn(inputs: Dict[str, Any]) -> List[Dict[str, str]]:
        official = inputs["data_pull"]
        name_cn = str(official["name_cn"])
        name_en = str(official.get("name_en") or "")
        if kind == "light_cone":
            queries = [f"{name_cn} 光锥 机制 叠加 刷新",
                       f"{name_en} hsr light cone",
                       f"{name_cn} 光锥 叠影 实测"]
        else:
            queries = [f"{name_cn} 遗器 套装 机制 触发",
                       f"{name_en} hsr relic set",
                       f"{name_cn} 遗器 实测 叠加 刷新"]
        queries = [q for q in queries if q.strip()][:max_queries]
        out, seen, failed = [], set(), 0
        for q in queries:
            try:
                rows_ = search(q, per_query)
            except Exception:  # noqa: BLE001 —— 单查询失败不拖死整层（降级空层，同角色版）
                failed += 1
                continue
            for r in rows_:
                if r["url"] in seen:
                    continue
                seen.add(r["url"])
                out.append({"query": q, **r})
        if failed:
            out.append({"query": "", "title": f"（社区检索失败 ×{failed}——降级空层）",
                        "url": "", "snippet": ""})
        return out
    return Node("community_search", fn, deps=("data_pull", "crosscheck"), service="web_search")


# ---------------------------------------------------------------------------
# LLM 层（evidence 机制拆解 / draft 只产 hooks 块 / revise 修 hooks 块）
# ---------------------------------------------------------------------------

def evidence_lc_node(lc_id: str, llm: LLMRunner) -> Node:
    """光锥证据研究（LLM）：官方包+对轴+社区 → 「条件→效果」清单（中文输出附官方术语）。"""
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        cross = inputs["crosscheck"]
        prompt = (f"光锥 {lc_id} {official['name_cn']}（{official.get('name_en') or ''}，"
                  f"命途 {official.get('path')}，{official.get('rarity')} 星，"
                  f"白值 calc lv80 实值={json.dumps(official.get('base_stats') or {}, ensure_ascii=False)}"
                  f"——白值已抽好，你只评机制层）。\n"
                  f"叠影机制 desc（CN）：{official.get('desc_cn') or ''}\n"
                  f"叠影机制 desc（EN——中英对照裁定语义层）：{official.get('desc_en') or ''}\n"
                  f"叠影 params 全表（S1..S5 × N 列，#N[i] 占位符按列定位，取档 index=叠影-1）："
                  f"{json.dumps(official.get('params') or [], ensure_ascii=False)}\n"
                  f"结构化 properties（官方面板加成直映射件）："
                  f"{json.dumps(official.get('properties') or [], ensure_ascii=False)}\n"
                  f"生成器草稿（已抽取件——白值/lookup 表/绑定原样保留，只读）：\n"
                  f"{official['draft_text']}\n"
                  f"草稿对轴冲突（vs 数据锚——conflict=drift 以数据锚为终审，不是机制问题）："
                  f"{json.dumps(cross.get('conflicts') or [], ensure_ascii=False)}（{cross.get('note')}）\n\n"
                  f"社区操作向资料（叠加/刷新/触发语义取数层；冲突裁决序 实测>社区>wiki>单一文本源）：\n"
                  f"{_community_txt(inputs.get('community_fetch') or [])}\n\n"
                  "输出证据笔记（markdown）：机制拆解成「条件→效果」清单——每条含 触发事件/条件/"
                  "效果/数值档（S1..S5 全档照抄 params 列并标 #N 出处）/持续与驱散/叠加与刷新语义/"
                  "作用范围；每项标证据来源（官方文本/wiki/社区/实测/待实测）；装备交互语义五项"
                  "逐项必答；查不到的标待实测，不脑补——官方 desc 没写的效果不许造；"
                  "写不到证据的机制列待收清单。")
        return llm(system=_EQUIPMENT_RULES, prompt=prompt, max_tokens=12000)
    return Node("evidence", fn, deps=("data_pull", "crosscheck", "community_fetch"),
                service="llm_api", kind="llm", salt=_equip_salt())


def evidence_relic_node(set_id: str, llm: LLMRunner) -> Node:
    """遗器证据研究（LLM）：2pc/4pc desc+properties+社区 → 「条件→效果」清单。"""
    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        cross = inputs["crosscheck"]
        prompt = (f"遗器套装 {set_id} {official['name_cn']}（{official.get('name_en') or ''}）。\n"
                  f"set_2pc desc（CN）：{official.get('desc_2pc_cn') or ''}\n"
                  f"set_2pc desc（EN——中英对照裁定语义层）：{official.get('desc_2pc_en') or ''}\n"
                  f"set_4pc desc（CN）：{official.get('desc_4pc_cn') or ''}\n"
                  f"set_4pc desc（EN）：{official.get('desc_4pc_en') or ''}\n"
                  f"结构化 properties（2pc/4pc 官方面板加成直映射件）："
                  f"{json.dumps(official.get('properties') or [], ensure_ascii=False)}\n"
                  f"生成器草稿（已抽取件——desc/stat_effects 原样保留，只读）：\n"
                  f"{official['draft_text']}\n"
                  f"草稿对轴冲突（vs 数据锚——conflict=drift 以数据锚为终审）："
                  f"{json.dumps(cross.get('conflicts') or [], ensure_ascii=False)}（{cross.get('note')}）\n\n"
                  f"社区操作向资料（触发/叠加/刷新语义取数层；冲突裁决序 实测>社区>wiki>单一文本源）：\n"
                  f"{_community_txt(inputs.get('community_fetch') or [])}\n\n"
                  "输出证据笔记（markdown）：2pc/4pc 分开拆——properties 已覆盖的纯数值部分"
                  "标注「已收（stat_effects 通道）」不重复拆；未覆盖部分拆成「条件→效果」清单"
                  "（触发事件/条件/效果/数值/持续与驱散/叠加与刷新语义/作用范围），"
                  "每项标证据来源（官方文本/wiki/社区/实测/待实测）；数值无等级/叠影轨道，"
                  "字面值照抄官方 desc；查不到的标待实测，不脑补——官方 desc 没写的效果不许造。")
        return llm(system=_EQUIPMENT_RULES, prompt=prompt, max_tokens=12000)
    return Node("evidence", fn, deps=("data_pull", "crosscheck", "community_fetch"),
                service="llm_api", kind="llm", salt=_equip_salt())


def draft_lc_node(lc_id: str, llm: LLMRunner, anchor_paths: List[Path]) -> Node:
    """光锥 hooks 起草（LLM）：证据笔记+锚范例 → **只产 hooks 块**（数值区机械合并保留）。"""
    anchors = "\n\n".join(f"# 锚范例 {p.name}\n{p.read_text(encoding='utf-8')}" for p in anchor_paths)

    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        prompt = (f"把光锥 {lc_id} {official['name_cn']} 的叠影机制写成 DSL hooks 块（YAML）。\n"
                  f"**只输出顶层 hooks: 块**——base_stats/lookup_tables/variable_bindings/"
                  f"name/rarity/path 由机械合并从生成器草稿原样保留，你重写任何一个都必被闸门"
                  f"打回（数值区幻觉零容忍）。\n"
                  f"可用叠影参数（绑定层已挂到装备者 $self 命名空间）："
                  f"{official.get('lookup_names') or []}——desc 的 #N[i] ↔ lookup_tables 第 N 列 "
                  f"↔ $self.<列名>；hooks 里**引用参数名，不抄字面量**（叠影档位由绑定层查表）。\n"
                  f"生成器草稿全文（数值区照抄源——只读不写）：\n{official['draft_text']}\n"
                  f"官方 desc（CN）：{official.get('desc_cn') or ''}\n"
                  f"官方 desc（EN）：{official.get('desc_en') or ''}\n"
                  f"params 全表：{json.dumps(official.get('params') or [], ensure_ascii=False)}\n"
                  f"证据笔记：\n{inputs['evidence']}\n\n{anchors}\n\n"
                  "纪律（违反必被打回）：① **不脑补——官方 desc 没写的效果不许造**（写不到证据的"
                  "进证据笔记待收清单，hooks 里不造）；② **hooks 词表只许用编译闸能过的 "
                  "effect_type**——闭合词表见下，自造键/自造事件必炸；③ 键名照锚范例词表；"
                  "④ YAML 卫生：字符串含特殊字符一律双引号，禁止 null/空值，"
                  "注释内嵌英文双引号改「」。\n"
                  "只输出 YAML 本体（首行 hooks:），不写解释。\n\n" + _equipment_cheatsheet())
        return _strip_code_fence(llm(system=_EQUIPMENT_RULES, prompt=prompt, max_tokens=16000))
    return Node("draft", fn, deps=("evidence", "data_pull"), service="llm_api", kind="llm",
                salt=_equip_salt(_equipment_cheatsheet().encode(),
                                 *(p.read_bytes() for p in anchor_paths)))


def draft_relic_node(set_id: str, llm: LLMRunner, anchor_paths: List[Path]) -> Node:
    """遗器 hooks 起草（LLM）：只产 set_2pc/set_4pc 的 hooks 子块（desc/stat_effects 机械保留）。"""
    anchors = "\n\n".join(f"# 锚范例 {p.name}\n{p.read_text(encoding='utf-8')}" for p in anchor_paths)

    def fn(inputs: Dict[str, Any]) -> str:
        official = inputs["data_pull"]
        prompt = (f"把遗器套装 {set_id} {official['name_cn']} 的套装机制写成 DSL hooks 块（YAML）。\n"
                  f"**只输出 set_2pc:/set_4pc: 两块、每块只许含 hooks: 子键**——desc/stat_effects "
                  f"由机械合并从生成器草稿原样保留，你重写任何一个都必被闸门打回。\n"
                  f"set_2pc（官方 desc CN）：{official.get('desc_2pc_cn') or ''}\n"
                  f"set_2pc（EN）：{official.get('desc_2pc_en') or ''}\n"
                  f"  ——2pc 已由 properties 直映射 stat_effects 覆盖的部分**不许重复进 hooks**；"
                  f"2pc 有 desc 未覆盖的条件效果才给 set_2pc 块，全覆盖就省略该块。\n"
                  f"set_4pc（官方 desc CN）：{official.get('desc_4pc_cn') or ''}\n"
                  f"set_4pc（EN）：{official.get('desc_4pc_en') or ''}\n"
                  f"  ——4pc 机制整块落 hooks（properties 覆盖的 stat 部分同样不重复）。\n"
                  f"数值无等级/叠影轨道——字面值直写官方 desc 数（注释标出处）。\n"
                  f"生成器草稿全文（数值区照抄源——只读不写）：\n{official['draft_text']}\n"
                  f"证据笔记：\n{inputs['evidence']}\n\n{anchors}\n\n"
                  "纪律（违反必被打回）：① **不脑补——官方 desc 没写的效果不许造**（写不到证据的"
                  "进证据笔记待收清单，hooks 里不造）；② **hooks 词表只许用编译闸能过的 "
                  "effect_type**——闭合词表见下，自造键/自造事件必炸；③ 键名照锚范例词表；"
                  "④ YAML 卫生：字符串含特殊字符一律双引号，禁止 null/空值，"
                  "注释内嵌英文双引号改「」。\n"
                  "只输出 YAML 本体（首行 set_2pc: 或 set_4pc:），不写解释。\n\n"
                  + _equipment_cheatsheet())
        return _strip_code_fence(llm(system=_EQUIPMENT_RULES, prompt=prompt, max_tokens=16000))
    return Node("draft", fn, deps=("evidence", "data_pull"), service="llm_api", kind="llm",
                salt=_equip_salt(_equipment_cheatsheet().encode(),
                                 *(p.read_bytes() for p in anchor_paths)))


def _revise_equipment_node(n: int, eid: str, llm: LLMRunner, src_dep: str, kind: str) -> Node:
    """修订（LLM）：闸门错误输出+现稿 hooks 块 → 修稿（仍只产 hooks 块，不碰数值区）。"""
    shape_desc = ("顶层 hooks: 块" if kind == "light_cone"
                  else "set_2pc:/set_4pc: 两块（每块只含 hooks: 子键）")

    def fn(inputs: Dict[str, Any]) -> str:
        prev = inputs[src_dep]
        prompt = (f"装备 {eid} 的 hooks 块被闸门打回，修订。\n"
                  f"错误输出：\n{prev.get('err', '')}\n\n"
                  f"现稿：\n{prev.get('hooks', '')}\n\n"
                  f"输出**完整 hooks 块**（{shape_desc}——不是只输出改动段）。"
                  "**不许输出数值区**（base_stats/lookup_tables/variable_bindings/desc/"
                  "stat_effects 由机械合并保留——写了必被合并处打回）。不写解释。\n"
                  "**先逐字搜索错误输出里的字段名/键名，把每一处出现都改掉**；其余不动。"
                  "**禁止写变更说明/修订注解行**；YAML 卫生：字符串含特殊字符一律双引号；"
                  "禁止 null/空值。\n\n" + _equipment_cheatsheet())
        return _strip_code_fence(llm(system=_EQUIPMENT_RULES, prompt=prompt, max_tokens=16000))
    return Node(f"revise{n}", fn, deps=(src_dep,), service="llm_api", kind="llm",
                salt=_equip_salt(_equipment_cheatsheet().encode()))


# ---------------------------------------------------------------------------
# 机械合并（draft/revise 的 hooks 块 + 生成器草稿 → 完整模板；越权输出在此即拒）
# ---------------------------------------------------------------------------

def _merge_lc_hooks(draft_text: str, hooks_text: str) -> "tuple[Optional[str], str]":
    """光锥机械合并：生成器草稿数值区原样 + LLM hooks 块。返回 (merged, err)——err 非空=拒收."""
    import yaml

    try:
        hdoc = yaml.safe_load(_strip_code_fence(hooks_text))
    except yaml.YAMLError as e:
        return None, f"hooks 块 YAML 解析失败：{e}（只输出 YAML 本体，围栏/解释文字不许带）"
    if not isinstance(hdoc, dict) or not hdoc:
        return None, ("draft 输出为空或不是 mapping——只许输出顶层 hooks: 块"
                      "（无机制可收也要给 hooks: [] 并在证据笔记标待收）")
    extra = set(hdoc) - {"hooks"}
    if extra:
        return None, (f"光锥 draft 只许输出顶层 hooks: 块（实得额外键 {sorted(extra)}）——"
                      f"base_stats/lookup_tables/variable_bindings 由机械合并保留，不许重写")
    if not isinstance(hdoc.get("hooks") or [], list):
        return None, "hooks 须为列表（hooks: [ ... ]）"
    doc = yaml.safe_load(draft_text) or {}
    doc["hooks"] = hdoc.get("hooks") or []
    header = (f"# 光锥模板：{doc.get('name')}（{doc.get('light_cone_id')}）——生成器草稿数值区 "
              f"+ 打标 hooks 机械合并（数值区勿手改，机制层改动只动 hooks 块）\n")
    return header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), ""


def _merge_relic_hooks(draft_text: str, hooks_text: str) -> "tuple[Optional[str], str]":
    """遗器机械合并：生成器草稿 desc/stat_effects 原样 + LLM hooks 子块。返回 (merged, err)."""
    import yaml

    try:
        hdoc = yaml.safe_load(_strip_code_fence(hooks_text))
    except yaml.YAMLError as e:
        return None, f"hooks 块 YAML 解析失败：{e}（只输出 YAML 本体，围栏/解释文字不许带）"
    if not isinstance(hdoc, dict) or not hdoc:
        return None, ("draft 输出为空或不是 mapping——只许输出 set_2pc:/set_4pc: 两块"
                      "（2pc 全覆盖可省略 set_2pc，set_4pc 机制必须收编）")
    extra = set(hdoc) - {"set_2pc", "set_4pc"}
    if extra:
        return None, (f"遗器 draft 只许输出 set_2pc:/set_4pc: 两块（实得额外键 {sorted(extra)}）"
                      f"——desc/stat_effects 由机械合并保留，不许重写")
    for pc, piece in hdoc.items():
        if not isinstance(piece, dict) or set(piece) - {"hooks"}:
            bad = sorted(set(piece) - {"hooks"}) if isinstance(piece, dict) else type(piece).__name__
            return None, f"{pc} 块只许含 hooks: 子键（实得额外键 {bad}）——desc/stat_effects 机械保留"
        if piece.get("hooks") is not None and not isinstance(piece["hooks"], list):
            return None, f"{pc}.hooks 须为列表"
    doc = yaml.safe_load(draft_text) or {}
    for pc, piece in hdoc.items():
        merged_piece = {**(doc.get(pc) or {}), "hooks": piece.get("hooks") or []}
        doc[pc] = merged_piece
    header = (f"# 遗器套装模板：{doc.get('name')}（{doc.get('relic_set_id')}）——生成器草稿数值区 "
              f"+ 打标 hooks 机械合并（数值区勿手改，机制层改动只动 hooks 块）\n")
    return header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), ""


# ---------------------------------------------------------------------------
# 装备 harness（编译/冒烟闸共用）：inline 测试角色 + 装备引用 + 候选临时根压生成器草稿
# ---------------------------------------------------------------------------

_PROBE_HERO = "probe_hero"
_KIND_DIRS = {"light_cone": "light_cones", "relic": "relics"}

#: 沙包 stage（fixed_av 截断局——约 3 回合；inline 敌人零模板依赖）
_PROBE_STAGE: Dict[str, Any] = {"stage": {
    "stage_id": "annotator_equip_probe",
    "enemies": [{"actor_id": "probe_e1", "name": "打标假人·甲", "hp": 1e9, "spd": 50,
                 "max_toughness": 9999, "weakness": ["physical"]},
                {"actor_id": "probe_e2", "name": "打标假人·乙", "hp": 1e9, "spd": 60,
                 "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 300}}}


def _probe_build(kind: str, eid: str) -> Dict[str, Any]:
    """inline 测试角色引用装备：光锥叠 1 / 遗器同套四件（2pc+4pc 双触发）。"""
    member: Dict[str, Any] = {
        "character_template": "inline", "actor_id": _PROBE_HERO, "name": "打标探针", "level": 80,
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 20},
        "actions": [
            {"action_id": "probe_basic", "name": "探针普攻", "action_type": "basic",
             "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.0}]},
            {"action_id": "probe_ult", "name": "探针终结", "action_type": "ultimate",
             "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 1.5}],
             "energy_cost": 20}]}
    if kind == "light_cone":
        member["light_cone_template"] = str(eid)
        member["light_cone"] = {"superimposition": 1}
    else:
        member["relics"] = {slot: {"set_id": str(eid)}
                            for slot in ("head", "hands", "body", "feet")}
    return {"build": {"team": [member], "policy": {
        "name": "annotator_equip_probe",
        "action_rules": [
            {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _equipment_roots(workdir: Path) -> List[str]:
    """模板根（有序，先命中生效）：runs 工作目录（候选已写入 <kind>/<eid>_candidate.yaml，
    压 data/ 同 id 生成器草稿）→ fixtures 人工根 → data/sim_templates。"""
    return [str(workdir), str(ROOT / "tests/fixtures/templates"),
            str(ROOT / "data/sim_templates")]


def _stage_candidate(kind: str, eid: str, tpl_text: str, workdir: Path) -> None:
    """候选模板写 runs 工作目录的 <kind>s/ 布局（glob 命中键=<eid>_ 前缀）。"""
    d = Path(workdir) / _KIND_DIRS[kind]
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{eid}_candidate.yaml").write_text(tpl_text, encoding="utf-8")


def _compile_equipment(kind: str, eid: str, tpl_text: str, workdir: Path) -> "tuple[bool, str]":
    """编译闸 harness：候选写临时布局 → 装备引用 build + 沙包 stage 全链编译（词表/键闸全过）。"""
    from hsr_nous.sim.compile import compile_encounter

    _stage_candidate(kind, eid, tpl_text, workdir)
    try:
        compile_encounter(_probe_build(kind, eid), _PROBE_STAGE,
                          template_roots=_equipment_roots(Path(workdir)))
    except Exception as e:  # noqa: BLE001 —— 编译闸：炸什么报什么
        return False, f"{type(e).__name__}: {e}"
    return True, ""


def _declared_battle_modifiers(kind: str, tpl_text: str) -> List[str]:
    """声明的无条件 on_battle_start apply_modifier modifier_id（冒烟核实对象——
    条件钩/其他事件钩不担保触发，不在此列）。"""
    import yaml

    doc = yaml.safe_load(tpl_text) or {}
    if kind == "light_cone":
        hooks = doc.get("hooks") or []
    else:
        hooks = [h for pc in ("set_2pc", "set_4pc")
                 for h in ((doc.get(pc) or {}).get("hooks") or [])]
    out: List[str] = []
    for h in hooks:
        if not isinstance(h, dict) or h.get("event") != "on_battle_start" or h.get("condition"):
            continue
        for eff in h.get("effects") or []:
            if isinstance(eff, dict) and eff.get("effect_type") == "apply_modifier":
                mid = (eff.get("modifier") or {}).get("modifier_id")
                if mid:
                    out.append(str(mid))
    return out


def _smoke_equipment(kind: str, eid: str, tpl_text: str, workdir: Path) -> "tuple[bool, str]":
    """冒烟闸 harness：编译 + expected 模式 fixed_av 截断局——断言不炸、动数 >0、
    声明的无条件开战 modifier 经 after_apply_modifier 事件核实施加；
    遗器另核 2pc stat_effects 转初始 Modifier（机械合并没丢数值件）。"""
    import yaml

    from hsr_nous.sim import CombatEngine, MODE_EXPECTED
    from hsr_nous.sim.compile import compile_encounter

    _stage_candidate(kind, eid, tpl_text, workdir)
    try:
        compiled = compile_encounter(_probe_build(kind, eid), _PROBE_STAGE,
                                     template_roots=_equipment_roots(Path(workdir)))
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=1,
                                         initial_energy_ratio=0.0)
        applied: List[str] = []
        eng.bus.subscribe("after_apply_modifier",
                          lambda _et, p, _ctx: applied.append(str((p or {}).get("modifier_id"))))
        state = eng.run()
    except Exception as e:  # noqa: BLE001 —— 冒烟闸：炸什么报什么
        return False, f"{type(e).__name__}: {e}"
    snap = state.snapshot()
    if not snap.get("turn_count"):
        return False, "冒烟零行动（fixed_av 截断局应有行动——策略/行动块检查）"
    missing = [m for m in _declared_battle_modifiers(kind, tpl_text) if m not in set(applied)]
    if missing:
        return False, (f"声明的无条件 on_battle_start modifier 未施加：{missing}"
                       f"（hook 挂了但没生效——查 event 名/effects 结构/modifier 块）")
    if kind == "relic":
        doc = yaml.safe_load(tpl_text) or {}
        if (doc.get("set_2pc") or {}).get("stat_effects"):
            ids = [m.modifier_id for m in (eng._initial_modifiers.get(_PROBE_HERO) or [])]
            if f"RELIC_{eid}_2PC" not in ids:
                return False, (f"set_2pc stat_effects 未转初始 Modifier（RELIC_{eid}_2PC 不在 "
                               f"{ids}）——机械合并丢了 2pc 数值件")
    return True, ""


# ---------------------------------------------------------------------------
# 内环三闸（compile → smoke → golden_diff；打回扇 revise+compile，预算尽扇 human_queue）
# ---------------------------------------------------------------------------

def _compile_gate_equipment(n: int, kind: str, eid: str, llm: LLMRunner, budget: int,
                            workdir: Path, src_dep: str,
                            staging_root: Optional[Path] = None) -> Node:
    """编译闸（fn：机械合并 hooks 进草稿 + harness 编译）+ shape 纯路由（同角色版内环）。"""
    merge = _merge_lc_hooks if kind == "light_cone" else _merge_relic_hooks

    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        hooks_text = inputs[src_dep]
        merged, err = merge(inputs["data_pull"]["draft_text"], hooks_text)
        if err:
            return {"ok": False, "hooks": hooks_text, "tpl": "", "err": err, "path": ""}
        p = Path(workdir) / f"{eid}_compile{n}.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(merged, encoding="utf-8")
        ok, out = _compile_equipment(kind, eid, merged, Path(workdir))
        return {"ok": ok, "hooks": hooks_text, "tpl": merged,
                "err": "" if ok else out, "path": str(p)}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (_smoke_gate_equipment(n, kind, eid, llm, budget, workdir, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_equipment_node(nxt, eid, llm, f"compile{n}", kind),
                _compile_gate_equipment(nxt, kind, eid, llm, budget, workdir,
                                        f"revise{nxt}", staging_root))
        return (_human_queue_node(eid, "compile 预算耗尽", f"compile{n}"),)
    return Node(f"compile{n}", fn, deps=(src_dep, "data_pull"),
                service="compile", kind="gate", shape=shape)


def compile_gate_lc_node(n: int, lc_id: str, llm: LLMRunner, budget: int,
                         workdir: Path, src_dep: str,
                         staging_root: Optional[Path] = None) -> Node:
    """光锥编译闸（同构不同参——见 _compile_gate_equipment）。"""
    return _compile_gate_equipment(n, "light_cone", lc_id, llm, budget, workdir,
                                   src_dep, staging_root)


def compile_gate_relic_node(n: int, set_id: str, llm: LLMRunner, budget: int,
                            workdir: Path, src_dep: str,
                            staging_root: Optional[Path] = None) -> Node:
    """遗器编译闸（同构不同参——见 _compile_gate_equipment）。"""
    return _compile_gate_equipment(n, "relic", set_id, llm, budget, workdir,
                                   src_dep, staging_root)


def _smoke_gate_equipment(n: int, kind: str, eid: str, llm: LLMRunner, budget: int,
                          workdir: Path, staging_root: Optional[Path] = None) -> Node:
    """冒烟闸（fn：harness 截断局）+ shape 纯路由：fail → 回 revise/compile 内环；过 → golden。"""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[f"compile{n}"]
        ok, out = _smoke_equipment(kind, eid, prev["tpl"], Path(workdir))
        return {"ok": ok, "hooks": prev["hooks"], "tpl": prev["tpl"],
                "err": "" if ok else out, "path": prev["path"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (golden_diff_equipment_node(n, kind, eid, llm, budget, workdir, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_equipment_node(nxt, eid, llm, f"smoke{n}", kind),
                _compile_gate_equipment(nxt, kind, eid, llm, budget, workdir,
                                        f"revise{nxt}", staging_root))
        return (_human_queue_node(eid, "smoke 预算耗尽", f"smoke{n}"),)
    return Node(f"smoke{n}", fn, deps=(f"compile{n}",), service="compile", kind="gate", shape=shape)


# ---------------------------------------------------------------------------
# golden_diff 金样对拍（装备版机械闸：数值区 vs 数据锚 + hooks 层空缺，零 LLM）
# ---------------------------------------------------------------------------

def _golden_mismatches_lc(tpl_text: str, official: Dict[str, Any]) -> List[str]:
    """光锥金样对拍：白值（calc lv80）/ lookup 表（行数=叠影档数、行值 ∈ params 行）/
    hooks 层空缺（desc 非空但 hooks 空=机制未收编）.

    数值区对不上只可能是生成器草稿 drift（机械合并 LLM 改不动）——打回信息指路重跑
    template_generator；这与角色版「LLM 白值幻视」病灶不同源，措辞区分开。
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
    base = official.get("base_stats") or {}
    for k in ("hp", "atk", "def"):
        v = (doc.get("base_stats") or {}).get(k)
        if not isinstance(v, (int, float)) or not math.isclose(
                float(v), float(base[k]), rel_tol=1e-6):
            out.append(f"base_stats.{k}={v!r} ≠ 数据锚 {base.get(k)}（calc_light_cone_stats lv80"
                       f"——数值区机械合并自生成器草稿，对不上=草稿 drift：重跑 "
                       f"adapters/template_generator 再收编，hooks 层不用动）")
    params = official.get("params") or []
    for name, col in sorted((doc.get("lookup_tables") or {}).items()):
        if len(col) != len(params):
            out.append(f"lookup_tables.{name} 行数 {len(col)} ≠ 叠影档数 {len(params)}"
                       f"（草稿 drift——重跑 template_generator）")
            continue
        for i, v in enumerate(col):
            if not any(math.isclose(float(v), float(x), rel_tol=1e-6, abs_tol=1e-12)
                       for x in params[i]):
                out.append(f"lookup_tables.{name}[{i}]={v} 不在叠影 S{i + 1} 参数行 "
                           f"{params[i]} 内（草稿 drift——重跑 template_generator）")
                break
    if (official.get("desc_cn") or "").strip() and not doc.get("hooks"):
        out.append("叠影机制 desc 非空但 hooks 为空——机制未收编（写不到证据的进证据笔记"
                   "待收清单，hooks 不许脑补造）")
    return out


def _golden_mismatches_relic(tpl_text: str, official: Dict[str, Any]) -> List[str]:
    """遗器金样对拍：2pc/4pc stat_effects（生成器重算=properties 直映射锚）/ 4pc hooks 空缺."""
    import math

    import yaml

    try:
        doc = yaml.safe_load(tpl_text)
    except yaml.YAMLError as e:
        return [f"YAML 解析失败：{e}"]
    if not isinstance(doc, dict):
        return ["YAML 本体不是 mapping"]
    from hsr_nous.adapters.template_generator import generate_relic_set_template
    fresh = generate_relic_set_template(str(official["id"]), lang="cn")
    out: List[str] = []
    for pc in ("set_2pc", "set_4pc"):
        want = (fresh.get(pc) or {}).get("stat_effects") or {}
        got = (doc.get(pc) or {}).get("stat_effects") or {}
        for k in sorted(set(want) | set(got)):
            w, g = want.get(k), got.get(k)
            if w is None or g is None or not math.isclose(float(g), float(w), rel_tol=1e-6):
                out.append(f"{pc}.stat_effects.{k}：模板 {g!r} vs 数据锚 {w!r}"
                           f"（properties 直映射件——对不上=草稿 drift：重跑 "
                           f"adapters/template_generator 再收编）")
    if (official.get("desc_4pc_cn") or "").strip() and not (
            (doc.get("set_4pc") or {}).get("hooks")):
        out.append("set_4pc desc 非空但 hooks 为空——4pc 机制未收编（stat_effects 只覆盖 "
                   "properties 直映射件，条件效果必须落 hooks；写不到证据的进证据笔记待收）")
    return out


def golden_diff_equipment_node(n: int, kind: str, eid: str, llm: LLMRunner, budget: int,
                               workdir: Path, staging_root: Optional[Path] = None) -> Node:
    """金样对拍闸（fn 机械对账）+ shape 纯路由：fail → 回 revise/compile 内环；过 → oracle_report 对拍报告。"""
    golden = _golden_mismatches_lc if kind == "light_cone" else _golden_mismatches_relic

    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[f"smoke{n}"]
        mismatches = golden(prev["tpl"], inputs["data_pull"])
        err = ("金样对拍打回（数值区对不上=草稿 drift，先重跑 template_generator；"
               "hooks 层问题逐条修，不许动其他）：\n"
               + "\n".join(f"{i + 1}. {m}" for i, m in enumerate(mismatches)))
        return {"ok": not mismatches, "hooks": prev["hooks"], "tpl": prev["tpl"],
                "err": "" if not mismatches else err, "path": prev["path"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (oracle_report_equipment_node(n, kind, eid, workdir, staging_root),)
        if n < budget:
            nxt = n + 1
            return (
                _revise_equipment_node(nxt, eid, llm, f"golden{n}", kind),
                _compile_gate_equipment(nxt, kind, eid, llm, budget, workdir,
                                        f"revise{nxt}", staging_root))
        return (_human_queue_node(eid, "golden_diff 预算耗尽", f"golden{n}"),)
    return Node(f"golden{n}", fn, deps=(f"smoke{n}", "data_pull"),
                service="compile", kind="gate", shape=shape)


# ---------------------------------------------------------------------------
# oracle_report 对拍报告（装备版报告型闸——借载体角色穿装备逐核心行动比值，
# 异常不打回不阻塞；报告落 runs 目录 + staging notes 挂异常数，同角色版）
# ---------------------------------------------------------------------------

def oracle_report_equipment_node(n: int, kind: str, eid: str, workdir: Path,
                                 staging_root: Optional[Path] = None, *,
                                 threshold: float = 1e-3, superimposition: int = 1,
                                 lc_conditionals: Optional[Dict[str, Any]] = None,
                                 set_conditionals: Optional[Dict[str, Any]] = None,
                                 carrier_key: Optional[str] = None,
                                 template_roots: Optional[List[str]] = None) -> Node:
    """装备对拍报告节点（golden 过闸后自动执行；fn 干活，shape 只接 finalize）.

    借载体角色（金样验收 fixture——LC 按命途选，遗器固定黑塔）穿候选装备打核心
    行动，与 hsr-optimizer 对拍：我方候选模板 fresh 编译取数 vs 对方
    kind="character"+equipment 场景，比值口径 对方/我方，|ratio-1| > threshold
    标 anomaly。报告落 runs_root/<kind>s/<id>/oracle_report.json，摘要经 finalize
    挂进 staging 候选包（notes 附录 + 输出 oracle 键）。

    降级口径（全部 pass-through 不阻塞）：装备/套装/载体对方未登记 →
    optimizer_not_covered；LC 命途无载体 → no_carrier；缺 node/rolldown →
    env_no_node。threshold/lc_conditionals/set_conditionals/carrier_key/
    template_roots 测试可注入（生产缺省 None = 对方 defaults() 生效，回显落报告）。
    """
    from hsr_nous.ops.annotator import oracle_report as _oracle

    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[f"golden{n}"]
        return _oracle.generate_equipment_report(
            kind, eid, prev["tpl"], inputs["data_pull"], workdir,
            threshold=threshold, superimposition=superimposition,
            lc_conditionals=lc_conditionals, set_conditionals=set_conditionals,
            carrier_key=carrier_key, template_roots=template_roots)

    def shape(value: Dict[str, Any]):
        return (_finalize_equipment_node(kind, eid, n, staging_root,
                                         src_dep=f"golden{n}", oracle_dep="oracle_report"),)
    return Node("oracle_report", fn, deps=(f"golden{n}", "data_pull"),
                service="compile", shape=shape, salt=_oracle_salt())


def _finalize_equipment_node(kind: str, eid: str, n: int,
                             staging_root: Optional[Path] = None,
                             src_dep: Optional[str] = None,
                             oracle_dep: Optional[str] = None) -> Node:
    """定稿：写 staging 模板（<staging_root>/<kind>s/<eid>_<名>.yaml——与模板根同构布局，
    staging_root 可直接当 template_roots 注入）+ 证据笔记（候选包，合并走人工闸）。
    oracle_dep=对拍报告节点 id（装备版 oracle_report 接入后——notes 挂对拍摘要 +
    输出 oracle 键，异常数进候选包元数据供人工过堂裁量；None=旧链无对拍）。"""
    dep = src_dep or f"golden{n}"
    deps = (dep, "evidence", "data_pull") + ((oracle_dep,) if oracle_dep else ())

    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        prev = inputs[dep]
        official = inputs["data_pull"]
        sroot = Path(staging_root) if staging_root else (ROOT / "data/annotator/staging_root")
        staging = sroot / _KIND_DIRS[kind]
        notes = sroot / "notes"
        staging.mkdir(parents=True, exist_ok=True)
        notes.mkdir(parents=True, exist_ok=True)
        safe = str(official["name_cn"]).replace("•", "_").replace("·", "_").replace("/", "_")
        tpl_path = staging / f"{eid}_{safe}.yaml"
        tpl_path.write_text(prev["tpl"], encoding="utf-8")
        notes_text = inputs["evidence"]
        dp = inputs.get(oracle_dep) if oracle_dep else None
        if dp:
            notes_text += (
                "\n\n## 对拍报告（oracle_report 报告型闸——异常不打回，过堂裁量）\n"
                f"- 状态：{dp.get('status')}\n"
                f"- 对拍异常数：{dp.get('anomalies')}（compared={dp.get('compared')}，"
                f"inconclusive={dp.get('inconclusive')}，skipped={dp.get('skipped')}）\n"
                f"- 报告全文：{dp.get('report_path')}\n")
        notes_path = notes / f"{eid}.md"
        notes_path.write_text(notes_text, encoding="utf-8")
        out = {"staging": str(tpl_path), "notes": str(notes_path), "review": "ready_for_human"}
        if dp:
            out["oracle"] = {"status": dp.get("status"), "anomalies": dp.get("anomalies"),
                             "compared": dp.get("compared"), "report": dp.get("report_path")}
        return out
    return Node("finalize", fn, deps=deps, kind="mechanical")
