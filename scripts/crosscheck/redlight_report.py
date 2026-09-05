#!/usr/bin/env python3
"""红灯清单：全量标注 needs_primitive 条目的清洗 / 分类 / 排序报告.

输入：`data/annotator/run_state.json`（断点续跑状态，pass 行带 needs_primitive）
或 `--report` 指定 full_run 风格报告 JSON（顶层 needs_primitive + characters）。

处理流水线（全部规则本文件内声明，可复现，无手工清单）：

1. 聚合：所有 pass 角色的 needs_primitive 条目（带 cid / 角色名）。
2. 清洗（噪音识别）：name 字段三条启发式 + 角色官方语料判定域——
   - punct：base 名含句子标点（。？！，、；：…—《》（）""'' 及 ASCII ?!;,:'"）。
     官方名从不含句子标点；「」【】·・• 是合法名号成分，不算标点。
   - too_long：name > 12 字符且不在官方语料（EN 官方名可超 12，语料命中则豁免）。
   - not_in_corpus：base 名不在该角色官方语料里（项目自己的名称纪律，同
     `mechanism_annotator.check_names`：base 按 ·・ 截断、去 「」【】后子串匹配）。
   语料构造与标注器同口径：query-game-data character <cid> + pipeline
   get_character_full(cid, lang="cn") 合并 JSON 文本；按 cid 缓存于
   `data/annotator/.redlight_corpus_cache/`（--refresh-corpus 重建，--no-corpus 跳过）。
   噪音条目不删除：instances 里标 noise:true + noise_reasons，并在顶层 noise[] 单列。
3. 分类：THEME_RULES 有序正则表（首个命中为主题，全部命中记 themes_all 备审）。
   规则表由 BACKLOG B31/B32 立项笔记 + 现有条目语料驱动，可在全量数据回归后修订。
4. 排序：主题按条目数降序（并列按角色数降序、主题名升序）。
5. 专项：memosprite 主题按缺口子类型细分（召唤动作/登场事件/消失事件/忆灵行动/
   对忆灵授予，规则见 MEMOSPRITE_SUBTYPE_RULES，可多标签）；filter_select 主题单列
   （B31 目标选择代数实例垫底）。other 主题自动按机制文本中「...」引用原语聚类
   （数据驱动的子主题发现）。

产出：`<out>`（默认 data/annotator/redlight_1.json）+ stdout 人读摘要。

用法：
    python3 scripts/crosscheck/redlight_report.py \
        [--state data/annotator/run_state.json | --report <full_run.json>] \
        [--out data/annotator/redlight_1.json] \
        [--recovered-counts <counts.json>] [--no-corpus] [--refresh-corpus]

`--recovered-counts`：外部恢复的每角色条目数矩阵（{cid: {name, count}}），用于
完整性判定（meta.complete）与头部覆盖率提示——run_state 被 --no-resume 重跑清空过
时（2026-08-30 第九轮事故），红灯清单只剩恢复矩阵能交代规模。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = REPO_ROOT / "data" / "annotator" / "run_state.json"
DEFAULT_OUT = REPO_ROOT / "data" / "annotator" / "redlight_1.json"
CORPUS_CACHE_DIR = REPO_ROOT / "data" / "annotator" / ".redlight_corpus_cache"
QUERY_SCRIPT = REPO_ROOT / ".agents" / "skills" / "query-game-data" / "query.py"

# ---------------------------------------------------------------------------
# 噪音判定规则
# ---------------------------------------------------------------------------

#: 句子标点（官方名的排除域；「」【】·・• 是合法名号成分，不在其列）
PUNCT_CHARS = "。！？，、；：…—《》（）“”‘’?!;,:'\""
PUNCT_RE = re.compile("[" + re.escape(PUNCT_CHARS) + "]")

#: name 长度上限（超过且语料不命中 → 疑似散文片段）
NAME_MAX_LEN = 12


def split_base(name: str) -> str:
    """与 mechanism_annotator.check_names 同口径的 base 名提取."""
    return re.split(r"[·・]", name)[0].strip().strip("「」【】")


def noise_reasons(name: str, corpus: Optional[str]) -> List[str]:
    """三条启发式 + 语料判定域。返回命中理由（空 = 干净）."""
    reasons: List[str] = []
    base = split_base(name)
    in_corpus = bool(base) and corpus is not None and base in corpus
    if PUNCT_RE.search(base):
        reasons.append("punct:" + "".join(sorted(set(PUNCT_RE.findall(base)))))
    if len(name) > NAME_MAX_LEN and not in_corpus:
        reasons.append(f"too_long({len(name)})")
    if corpus is not None and not in_corpus:
        reasons.append("not_in_corpus")
    return reasons


# ---------------------------------------------------------------------------
# 主题分类规则（有序；首个命中 = 主题，全命中记 themes_all）
# ---------------------------------------------------------------------------

THEME_RULES: List[Tuple[str, str]] = [
    ("memosprite",      r"忆灵|召唤|神君|账账|浮元|小伊卡|死龙|玻吕刻斯|德谬歌|Evey|Netherwing|memosprite|summon"),
    ("filter_select",   r"点名|按条件|(?:选择|指定|筛选|过滤).{0,6}目标|目标.{0,6}(?:筛选|过滤|选择器)|随机.{0,4}(?:名|个).{0,4}(?:敌方|我方|目标)|优先.{0,6}(?:持有|处于|攻击|目标)|持有.{0,8}的?(?:敌方|目标|敌人)|未持有|filter"),
    ("party_count",     r"黄金裔|编队|队伍.{0,10}(?:数量|计数|人数)|(?:数量|计数).{0,6}(?:记忆|命途|属性|黄金裔)|每名(?:队友|我方成员|记忆)|同命途"),
    ("hp_drain",        r"消耗.{0,4}(?:生命|HP|血量)|扣除.{0,4}生命|损失.{0,4}生命|(?:生命|血量).{0,4}消耗|烧血|生命上限.{0,6}(?:转化|扣除|降低)"),
    ("resource_bank",   r"计数器|银行|充能层|特殊.{0,4}(?:资源|点数|层数)|(?:积攒|累计|累积).{0,6}(?:层|点)|层数.{0,4}上限|叠层|新蕊|账户"),
    ("energy_special",  r"能量.{0,6}(?:特殊|替代|转化|不恢复|无法恢复|不回复|不守恒)|特殊.{0,2}能量|终结技.{0,6}(?:无|不耗|不需要).{0,2}能量|能量上限.{0,6}(?:变化|降低|提升|锁定)"),
    ("extra_turn",      r"额外回合|行动提前|立即行动|再次行动|连续行动|立即.{0,2}回合|再现|extra turn|action advance"),
    ("shield_deathward", r"免死|锁血|不死|致命伤害|免于.{0,2}(?:死亡|致命)|复活|死亡.{0,4}(?:免疫|回避)|deathward|revive"),
    ("form_switch",     r"形态|变身|姿态|切换.{0,4}(?:技能|普攻|战技|模式)|(?:技能|普攻|战技).{0,4}替换|进入.{0,6}(?:强化|觉醒|变身)"),
]
THEME_COMPILED = [(t, re.compile(p, re.IGNORECASE)) for t, p in THEME_RULES]

#: 忆灵主题缺口子类型（可多标签）
MEMOSPRITE_SUBTYPE_RULES: List[Tuple[str, str]] = [
    ("summon_action",      r"召唤动作|(?:施放|使用|执行).{0,6}召唤|召唤出|召唤忆灵|(?:忆灵|神君|账账).{0,4}召唤"),
    ("memosprite_enter",   r"登场|入场|上场|出现|被召唤(?:时|后)|进入战场"),
    ("memosprite_leave",   r"消失|退场|离场|消散|(?:忆灵|神君|账账|召唤物).{0,4}(?:死亡|阵亡|销毁)|(?:死亡|阵亡).{0,4}(?:忆灵|神君|召唤物)"),
    ("memosprite_action",  r"(?:忆灵|神君|账账|召唤物).{0,6}(?:行动|攻击|回合|施放|出手)|行动.{0,4}(?:忆灵|神君|召唤物)"),
    ("grant_to_memosprite", r"(?:使|令|对|向)(?:忆灵|神君|账账|召唤物).{0,6}(?:获得|赋予|授予|施加|提供)|(?:获得|赋予|授予|施加).{0,6}(?:忆灵|神君|召唤物)"),
]
MEMOSPRITE_SUBTYPE_COMPILED = [(t, re.compile(p, re.IGNORECASE)) for t, p in MEMOSPRITE_SUBTYPE_RULES]

#: other 主题的数据驱动子聚类：机制文本里「...」引用的原语名
QUOTE_RE = re.compile(r"「([^「」]{2,30})」")


def classify(name: str, mechanism: str) -> List[str]:
    text = f"{name}\n{mechanism}"
    hits = [theme for theme, rx in THEME_COMPILED if rx.search(text)]
    return hits or ["other"]


def memosprite_subtypes(mechanism: str) -> List[str]:
    hits = [t for t, rx in MEMOSPRITE_SUBTYPE_COMPILED if rx.search(mechanism)]
    return hits or ["unspecified"]


def summarize(mechanism: str, limit: int = 140) -> str:
    """条目摘要：优先取「缺口：」之后的缺口描述（这才是红灯本体）."""
    text = mechanism
    idx = text.find("缺口：")
    if idx >= 0:
        text = text[idx + len("缺口："):]
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------------------
# 语料（与 mechanism_annotator.gather_char_input 同口径）
# ---------------------------------------------------------------------------

def build_corpus(char_id: str, *, refresh: bool = False) -> Optional[str]:
    """query-game-data(en) + pipeline get_character_full(cn) 合并 JSON 文本，按 cid 缓存."""
    CORPUS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CORPUS_CACHE_DIR / f"{char_id}.json"
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))["corpus"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    proc = subprocess.run(
        [sys.executable, str(QUERY_SCRIPT), "character", str(char_id)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
    )
    if proc.returncode != 0:
        return None
    try:
        raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if "_error" in raw:
        return None
    try:
        from hsr_nous.pipeline.loader import get_character_full
        cn = get_character_full(str(char_id), lang="cn") or {}
    except Exception:  # pipeline 数据缺失不致命：退回 query 单侧语料
        cn = {}
    corpus = json.dumps({"cn": cn, "en": raw}, ensure_ascii=False)
    cache.write_text(json.dumps({"corpus": corpus}, ensure_ascii=False), encoding="utf-8")
    return corpus


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------

def load_entries(state_path: Optional[Path], report_path: Optional[Path]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """返回 (条目列表, 源信息)。条目 = {cid, char, name, mechanism}."""
    src = report_path or state_path
    assert src is not None
    data = json.loads(src.read_text(encoding="utf-8"))
    entries: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {"source": str(src.relative_to(REPO_ROOT) if src.is_relative_to(REPO_ROOT) else src)}
    if report_path is not None:
        chars = data.get("characters") or {}
        names = {cid: c.get("name", "") for cid, c in chars.items() if isinstance(c, dict)}
        np_map = data.get("needs_primitive") or {}
        info["chars_in_source"] = len(chars)
        info["pass_chars"] = sum(1 for c in chars.values() if isinstance(c, dict) and c.get("status") == "pass")
        for cid, items in np_map.items():
            for it in items or []:
                if isinstance(it, dict):
                    entries.append({"cid": str(cid), "char": names.get(cid, ""),
                                    "name": str(it.get("name", "")), "mechanism": str(it.get("mechanism", ""))})
    else:
        states = data.get("states") or {}
        info["chars_in_source"] = len(states)
        info["pass_chars"] = sum(1 for s in states.values() if isinstance(s, dict) and s.get("status") == "pass")
        for cid, st in states.items():
            if not isinstance(st, dict) or st.get("status") != "pass":
                continue
            for it in st.get("needs_primitive") or []:
                if isinstance(it, dict):
                    entries.append({"cid": str(cid), "char": str(st.get("name", "")),
                                    "name": str(it.get("name", "")), "mechanism": str(it.get("mechanism", ""))})
    return entries, info


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="红灯清单：needs_primitive 清洗/分类/排序")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--state", type=Path, default=DEFAULT_STATE, help="run_state.json 路径")
    src.add_argument("--report", type=Path, default=None, help="full_run 风格报告 JSON")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="产出 JSON 路径")
    ap.add_argument("--recovered-counts", type=Path, default=None,
                    help="外部恢复的每角色条目数矩阵（{cid:{name,count}}），用于完整性判定")
    ap.add_argument("--no-corpus", action="store_true", help="跳过语料判定（punct/too_long 仍生效）")
    ap.add_argument("--refresh-corpus", action="store_true", help="重建语料缓存")
    args = ap.parse_args()

    entries, info = load_entries(None if args.report else args.state, args.report)

    corpora: Dict[str, Optional[str]] = {}
    if not args.no_corpus:
        for cid in sorted({e["cid"] for e in entries}):
            try:
                corpora[cid] = build_corpus(cid, refresh=args.refresh_corpus)
            except Exception:
                corpora[cid] = None

    # 清洗 + 分类
    instances: List[Dict[str, Any]] = []
    noise_list: List[Dict[str, Any]] = []
    for e in entries:
        corpus = corpora.get(e["cid"]) if not args.no_corpus else None
        reasons = noise_reasons(e["name"], corpus)
        themes = classify(e["name"], e["mechanism"])
        inst: Dict[str, Any] = {
            "cid": e["cid"],
            "char": e["char"],
            "name": e["name"],
            "mechanism_summary": summarize(e["mechanism"]),
            "mechanism": e["mechanism"],
            "theme": themes[0],
            "themes_all": themes,
            "noise": bool(reasons),
            "noise_reasons": reasons,
            # 语料缺失时 not_in_corpus 不生效（只 punct/too_long），此标记供审计
            "corpus_checked": (not args.no_corpus) and corpus is not None,
        }
        if themes[0] == "memosprite":
            inst["memosprite_subtypes"] = memosprite_subtypes(e["mechanism"])
        instances.append(inst)
        if reasons:
            noise_list.append({"cid": e["cid"], "char": e["char"], "name": e["name"],
                               "reason": "+".join(reasons)})

    # 主题归组 + 排序（条目数降序 → 角色数降序 → 主题名）
    by_theme: Dict[str, List[Dict[str, Any]]] = {}
    for inst in instances:
        by_theme.setdefault(inst["theme"], []).append(inst)
    categories = [
        {"theme": theme,
         "count": len(items),
         "char_count": len({i["cid"] for i in items}),
         "instances": sorted(items, key=lambda i: (i["cid"], i["name"]))}
        for theme, items in by_theme.items()
    ]
    categories.sort(key=lambda c: (-c["count"], -c["char_count"], c["theme"]))

    # 专项统计（忆灵 / filter；噪音单列但也保留在实例里——统计给 raw/clean 两个口径）
    memo_items = by_theme.get("memosprite", [])
    subtype_counter: Counter = Counter()
    for i in memo_items:
        subtype_counter.update(i.get("memosprite_subtypes", []))
    filter_items = by_theme.get("filter_select", [])

    def clean(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [i for i in items if not i["noise"]]

    # other 主题的数据驱动子聚类（「...」引用原语频次）
    other_quotes: Counter = Counter()
    for i in by_theme.get("other", []):
        other_quotes.update(QUOTE_RE.findall(i["mechanism"]))

    # 完整性判定（对照外部恢复矩阵）
    recovered: Optional[Dict[str, Any]] = None
    complete: Optional[bool] = None
    if args.recovered_counts and args.recovered_counts.exists():
        recovered = json.loads(args.recovered_counts.read_text(encoding="utf-8"))
        expected = {cid for cid, r in recovered.items() if isinstance(r, dict) and r.get("count")}
        present = {i["cid"] for i in instances}
        complete = expected <= present

    report: Dict[str, Any] = {
        "meta": {
            "tool": "scripts/crosscheck/redlight_report.py",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            **info,
            "entries": len(instances),
            "chars_with_entries": len({i["cid"] for i in instances}),
            "noise_entries": len(noise_list),
            "corpus": "annotator-equivalent(query-game-data+pipeline cn)" if not args.no_corpus else "disabled",
            "complete": complete,
            **({"data_quality": "INCOMPLETE: 对照恢复矩阵有缺口——run_state 曾被 --no-resume 重跑清空，"
                                "本报告只覆盖现存条目，规模以 recovered_counts 为准"}
               if complete is False else {}),
            **({"recovered_counts": recovered} if recovered else {}),
        },
        "categories": categories,
        "memosprite_special": {
            "count": len(memo_items),
            "count_clean": len(clean(memo_items)),
            "chars": sorted({i["cid"] for i in memo_items}),
            "char_names": sorted({i["char"] for i in memo_items}),
            "subtypes": dict(subtype_counter.most_common()),
        },
        "filter_select_special": {
            "count": len(filter_items),
            "count_clean": len(clean(filter_items)),
            "chars": sorted({i["cid"] for i in filter_items}),
            "char_names": sorted({i["char"] for i in filter_items}),
        },
        "other_top_primitives": [
            {"primitive": q, "count": n} for q, n in other_quotes.most_common(20)
        ],
        "noise": noise_list,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # ---- stdout 人读摘要 ----
    m = report["meta"]
    print(f"红灯清单 · 来源 {m['source']} · pass {m['pass_chars']}/{m['chars_in_source']} · "
          f"条目 {m['entries']}（{m['chars_with_entries']} 角色）· 噪音 {m['noise_entries']}")
    if not args.no_corpus:
        unchecked = sum(1 for i in instances if not i["corpus_checked"])
        if unchecked:
            print(f"⚠ {unchecked} 条目语料缺失——not_in_corpus 判定未生效（仅 punct/too_long）")
    if recovered:
        exp_total = sum(r.get("count") or 0 for r in recovered.values() if isinstance(r, dict))
        print(f"覆盖率：现存 {m['entries']}/{exp_total} 条目"
              + (" —— ⚠ 数据不完整（state 被清空过），规模以恢复矩阵为准" if complete is False else "（完整）"))
    print("\n== 主题 × 条目数（降序）==")
    for c in categories:
        print(f"  {c['theme']:<18} {c['count']:>3} 条目 / {c['char_count']:>2} 角色")
    ms = report["memosprite_special"]
    print(f"\n== 忆灵/召唤物专项（B32）==  {ms['count']} 条目（净 {ms['count_clean']}）· "
          f"{len(ms['chars'])} 角色：{'、'.join(ms['char_names']) or '—'}")
    for st, n in ms["subtypes"].items():
        print(f"  {st:<22} {n}")
    fs = report["filter_select_special"]
    print(f"\n== 按条件点名专项（B31）==  {fs['count']} 条目（净 {fs['count_clean']}）· "
          f"{len(fs['chars'])} 角色：{'、'.join(fs['char_names']) or '—'}")
    if report["other_top_primitives"]:
        print("\n== other 主题引用原语 TOP（数据驱动聚类）==")
        for q in report["other_top_primitives"][:10]:
            print(f"  「{q['primitive']}」×{q['count']}")
    if noise_list:
        reason_counter = Counter(r.split("(")[0] for n in noise_list for r in n["reason"].split("+"))
        print(f"\n== 噪音 {len(noise_list)} 条 ==")
        for r, n in reason_counter.most_common():
            print(f"  {r:<16} {n}")
        for n in noise_list[:8]:
            print(f"  · {n['cid']} {n['char']} 「{n['name'][:40]}」— {n['reason']}")
    print(f"\n已写：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
