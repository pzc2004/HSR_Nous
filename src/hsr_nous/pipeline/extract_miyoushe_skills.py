#!/usr/bin/env python3
"""从米游社官方 WIKI（开拓者笔记）批量提取角色技能的机制数据（类型/能量上限/削韧/回能/战技点）.

数据来源: https://bbs.mihoyo.com/sr/wiki/ （米游社·崩坏：星穹铁道 WIKI）
- 全花名册: act-api-takumi-static .../home/content/list?channel_id=17（频道树，角色频道 id=18）
- 单角色详情: act-api-takumi-static .../content/info?content_id=<id>
  （rpg_new_tmp_content 行迹树：points[].subList[].subTag = ["单攻","削韧值10","回能 20","战技点 +1"]）

数据模型（2026-09-05 端点挖掘钉死）：
- 两端点均为静态 CDN 裸 GET——无鉴权、无 DS 签名、无 cookie；响应带 mtime 可做条件更新
- subTag 标签写法不统一（削韧值10 / 削韧 10 / 回能30 / 回能 5），解析用宽松正则，
  无法归类的标签原样保留进 unparsed 报告，不静默丢
- 战技点标签显式带符号（战技点 +1 / 战技点 -1）——**含强化/派生技的真实耗产**，
  这是 StarRailRes 与 Fandom 都缺的逐技能权威源（Fandom SP 是类型规则合成值，见
  extract_fandom_skills.py docstring）
- 敌人频道（23 敌对物种）只有弱点/抗性/介绍，无技能/行动表——敌人数据此路不通
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://act-api-takumi-static.mihoyo.com/common/blackboard/sr_wiki/v1"
ROSTER_URL = f"{BASE}/home/content/list?app_sn=sr_wiki&channel_id=17"
INFO_URL = f"{BASE}/content/info?app_sn=sr_wiki&content_id={{cid}}"
CHANNEL_CHARACTER = 18  # 角色频道（频道树 children 里 id=18）

UA = {"User-Agent": "HSR_Nous/0.1 (miyoushe wiki extractor)"}
FETCH_INTERVAL = 0.3  # 串行礼貌间隔（秒）
RETRY_BACKOFF = (1.0, 3.0, 8.0)

# 机制承载标签（属性加成为纯数值节点，不收）
SKILL_TAGS = ("普攻", "战技", "终结技", "天赋", "秘技", "忆灵技", "忆灵天赋", "额外能力")

# 非机制标签（行迹节点解锁条件等）——已知噪音，静默忽略
RE_NOISE = re.compile(r"^角色(晋阶|等级)\s*\d+$")

RE_SP = re.compile(r"^(?:战技点|技能点)\s*([+-]?\d+)$")  # 战技点 +1 / 技能点 -2（Fate 联动写法）
RE_ENERGY_CAP = re.compile(r"(\d+(?:\.\d+)?)")
RE_NUM = r"\d+(?:\.\d+)?"
RE_ARITH = re.compile(rf"^{RE_NUM}(\s*[+*]\s*{RE_NUM})*$")  # 纯算术式（20+10*2）
RE_RES = re.compile(r"【[^】]*】")                           # 特殊充能资源名（【飞黄】【追忆】）
RE_RES_ACTION = re.compile(r"^(消耗|获得)\s*.+$")            # 特殊资源耗产（消耗 所有【源能】）

_TYPE_WORD = ("单攻|单体|群攻|群体|扩散|弹射|随机|防御|回复|辅助|强化|妨害|妨碍|召唤|"
              "天赋|秘技|专属|助战技|普攻")
RE_TYPE = re.compile(rf"^(?:{_TYPE_WORD})+$")                    # 单攻/群体/单体弹射
RE_STAGE_TYPE = re.compile(rf"^(?:一段|二段|三段)(?:{_TYPE_WORD})+$")  # 一段单体/二段群体
RE_PREFIX = r"(?:一段|二段|三段|强化后|消耗|" + _TYPE_WORD + ")"


# ---------------------------------------------------------------------------
# 网络请求（串行 + 间隔 + 退避重试 + 落盘缓存）
# ---------------------------------------------------------------------------

def _get(url: str) -> dict | None:
    last_err: Exception | None = None
    for attempt, backoff in enumerate((*RETRY_BACKOFF, None)):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:  # noqa: BLE001
            last_err = e
            if backoff is not None:
                time.sleep(backoff)
    print(f"  !! 请求失败（{attempt + 1} 次重试后放弃）: {url} -> {last_err}", file=sys.stderr)
    return None


def _fetch_character(cid: int, cache_dir: Path, refresh: bool) -> dict | None:
    cache = cache_dir / f"{cid}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))
    d = _get(INFO_URL.format(cid=cid))
    if d is None or d.get("retcode") != 0:
        return None
    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    time.sleep(FETCH_INTERVAL)
    return d


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def _eval_arith(expr: str) -> float | None:
    """"20+10*2" → 40.0；含 n/每段 等非算术内容返回 None（fullmatch 保证只含数字与 +*）."""
    if RE_ARITH.match(expr.strip()):
        return float(eval(expr))  # noqa: S307 - fullmatch 已锁死字符集
    return None


def _split_number_tag(t: str, keyword: str) -> tuple[float | None, str | None, str | None] | None:
    """削韧/回能/能量 类标签 → (数值, 类型, 备注)；不含该关键字返回 None.

    覆盖变体：削韧值10 / 削韧 20+10*2 / 强化后削韧 / 二段削韧 5+10*2 / 单体削韧 30 /
    回能 30 (6*5) / 回能 0.5点【飞黄】 / 消耗能量 360 / 削韧 10+5*n（不可算→None+备注）/
    裸"削韧"/"回能"（无数值→备注）。
    """
    if keyword not in t:
        return None
    m = re.match(rf"^((?:{RE_PREFIX})*?)\s*{keyword}值?\s*(.*?)\s*$", t)
    if not m:
        return None
    prefix, rest = m.group(1), m.group(2)
    notes: list[str] = []
    type_hit = None
    for stage in re.findall(r"一段|二段|三段|强化后", prefix):
        notes.append(stage)
    tp = re.sub(r"一段|二段|三段|强化后|消耗", "", prefix)
    if tp:
        type_hit = tp
    for res in RE_RES.findall(rest):
        notes.append(res)
    rest = RE_RES.sub("", rest)
    if p := re.search(r"\((.+?)\)", rest):
        notes.append(f"({p.group(1)})")
        rest = rest[:p.start()]
    rest = rest.replace("点", "").strip()
    if not rest:
        notes.append("裸标签")
        return None, type_hit, " ".join(notes) or None
    val = _eval_arith(rest)
    if val is None:
        notes.append(rest)  # 不可算表达式（10+5*n / 5每段）留原文
    return val, type_hit, " ".join(notes) or None


def _parse_subtag(raw_tags: list[str]) -> dict:
    """subTag 数组 → 结构化五项；未识别标签进 unparsed（不静默丢）."""
    out: dict = {"type": None, "toughness": None, "energy_gen": None,
                 "sp": None, "energy_cost": None, "note": None, "unparsed": []}
    notes: list[str] = []
    for t in raw_tags:
        t = t.strip()
        if not t or RE_NOISE.match(t):
            continue
        if m := RE_SP.match(t):
            out["sp"] = int(m.group(1))
            continue
        if RE_RES_ACTION.match(t):
            notes.append(t)  # 特殊资源耗产（源能族）——不是能量/战技点，记备注
            continue
        if RE_STAGE_TYPE.match(t) or RE_TYPE.match(t):
            out["type"] = out["type"] or t
            continue
        hit = False
        for keyword, field in (("削韧", "toughness"), ("回能", "energy_gen"),
                               ("能量", "energy_cost")):
            r = _split_number_tag(t, keyword)
            if r is not None:
                val, type_hit, note = r
                if val is not None:
                    out[field] = val
                if type_hit and not out["type"]:
                    out["type"] = type_hit
                if note:
                    notes.append(f"{keyword}:{note}")
                hit = True
                break
        if not hit:
            out["unparsed"].append(t)
    out["note"] = " ".join(notes) or None
    return out


def _find_trace_module(payload: dict) -> dict | None:
    """行迹树定位（双模板）：
    新模板 rpg_new_tmp_content.modules（components[0].data 解析出 points）；
    旧模板 contents[].text 的 data-data（URL 编码 JSON，partKey=="trace"，attr.points）。
    统一返回 {"roleId", "path", "points"}（旧模板无 roleId → None，走名字回填）."""
    content = (payload.get("data") or {}).get("content") or {}
    rpg = content.get("rpg_new_tmp_content") or {}
    for module in rpg.get("modules") or []:
        for comp in module.get("components") or []:
            try:
                data = json.loads(comp.get("data") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("points"):
                return data
    for section in content.get("contents") or []:
        for m in re.finditer(r'data-data="([^"]+)"', (section or {}).get("text") or ""):
            try:
                blob = json.loads(urllib.parse.unquote(m.group(1)))
            except (json.JSONDecodeError, TypeError):
                continue
            for entry in blob if isinstance(blob, list) else []:
                attr = ((entry or {}).get("data") or {}).get("attr") or {}
                if entry.get("partKey") == "trace" and attr.get("points"):
                    return {"roleId": None, "path": attr.get("path"), "points": attr["points"]}
    return None


def _find_energy_cap(payload: dict) -> float | None:
    """属性模块里找 终结技启动所需（"140 能量"/"120点能量"/"12点【火种】"取首个数）.
    旧模板（椒丘族）在 HTML 表格里——整串正则兜底."""
    rpg = (payload.get("data") or {}).get("content", {}).get("rpg_new_tmp_content") or {}
    for module in rpg.get("modules") or []:
        for comp in module.get("components") or []:
            try:
                data = json.loads(comp.get("data") or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                continue
            for tab in data["list"]:
                for attr in (tab or {}).get("attr") or []:
                    if (attr or {}).get("key") == "终结技启动所需":
                        vals = attr.get("value") or []
                        if vals and (m := RE_ENERGY_CAP.search(str(vals[0]))):
                            return float(m.group(1))
    s = json.dumps(payload, ensure_ascii=False)
    i = s.find("终结技启动所需")
    if i >= 0:
        m = re.search(r"(\d+(?:\.\d+)?)\s*点?\s*(?:能量|【)", s[i:i + 300])
        if m:
            return float(m.group(1))
    return None


def parse_character(cid: int, title: str, payload: dict,
                    name_to_id: dict[str, str] | None = None) -> dict | None:
    content = (payload.get("data") or {}).get("content") or {}
    trace = _find_trace_module(payload)
    if trace is None:
        return None
    skills = []
    for p in trace.get("points") or []:
        if not p:
            continue
        if "tag" in p:
            tag, name = p["tag"], p.get("name")
            subs = [((s or {}).get("subTag") or [], (s or {}).get("subDesc") or "")
                    for s in (p.get("subList") or [{}])]
        else:
            # 旧模板（椒丘族）：tag/标签都在 HTML 的 colorful-tag span 里
            name_spans = re.findall(r'<span[^>]*colorful-tag[^>]*>([^<]+)</span>',
                                    p.get("name") or "")
            tag = name_spans[0] if name_spans else None
            name = re.sub(r"<[^>]+>", "", p.get("name") or "").strip() or None
            if name and tag and name.startswith(tag):
                name = name[len(tag):].strip() or None  # 剥 span 残留的 tag 前缀
            subs = [(re.findall(r'<span[^>]*colorful-tag[^>]*>([^<]+)</span>',
                                p.get("desc") or ""), p.get("desc") or "")]
        if tag not in SKILL_TAGS:
            continue
        for raw_tags, desc in subs:
            if not raw_tags and not re.sub(r"<[^>]+>", "", desc).strip():
                continue  # 占位空条目（阿格莱雅战技族：subList 里带 subTag=[] subDesc=<p></p>）
            raw = [t for t in raw_tags if isinstance(t, str)]
            parsed = _parse_subtag(raw)
            skills.append({
                "tag": tag, "name": name,
                "type": parsed["type"], "toughness": parsed["toughness"],
                "energy_gen": parsed["energy_gen"], "sp": parsed["sp"],
                "energy_cost": parsed["energy_cost"], "note": parsed["note"],
                "sub_tag": raw, "unparsed": parsed["unparsed"],
            })
    name = content.get("title") or title
    return {
        "content_id": cid,
        "name": name,
        "role_id": trace.get("roleId") or (name_to_id or {}).get(name),
        "path": trace.get("path"),
        "mtime": content.get("mtime"),
        "energy_cap": _find_energy_cap(payload),
        "skills": skills,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="米游社 WIKI 角色技能机制数据提取")
    ap.add_argument("--data-dir", default="data", help="数据目录（默认 data）")
    ap.add_argument("--refresh", action="store_true", help="忽略缓存重新抓取")
    ap.add_argument("--only", help="只抓指定角色名（调试用）")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    cache_dir = data_dir / "miyoushe" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    roster_payload = _get(ROSTER_URL)
    if not roster_payload or roster_payload.get("retcode") != 0:
        print("频道树获取失败", file=sys.stderr)
        return 1
    tree = (roster_payload.get("data") or {}).get("list") or []
    channels = {c.get("id"): c for t in tree for c in (t.get("children") or [])}
    roster = (channels.get(CHANNEL_CHARACTER) or {}).get("list") or []
    if args.only:
        roster = [r for r in roster if r.get("title") == args.only]
        if not roster:
            print(f"花名册里找不到角色: {args.only}", file=sys.stderr)
            return 1
    print(f"角色花名册: {len(roster)} 条")

    # StarRailRes 在册角色：roleId 回填（旧模板页无 roleId）+ 红线绊线（未上线角色不入库）
    live_ids: set[str] = set()
    name_to_id: dict[str, str] = {}
    srr_path = data_dir / "starrailres" / "index_new" / "cn" / "characters.json"
    if srr_path.exists():
        srr = json.loads(srr_path.read_text(encoding="utf-8"))
        live_ids = set(srr.keys())
        name_to_id = {c["name"]: cid for cid, c in srr.items()}
    else:
        print("!! 未找到 StarRailRes characters.json——红线校验与旧模板 roleId 回填跳过",
              file=sys.stderr)

    characters: dict[str, dict] = {}
    failures: list[str] = []
    redline_blocked: list[str] = []
    unparsed_report: dict[str, list[str]] = {}
    no_subtag: list[str] = []
    for i, entry in enumerate(roster, 1):
        cid, title = entry["content_id"], entry.get("title") or str(entry["content_id"])
        payload = _fetch_character(cid, cache_dir, args.refresh)
        ch = parse_character(cid, title, payload, name_to_id) if payload else None
        if ch is None:
            failures.append(title)
            print(f"[{i}/{len(roster)}] {title} ({cid}) —— 解析失败/无行迹树")
            continue
        if live_ids and ch.get("role_id") not in live_ids:
            # 米游社已上架但游戏内未上线（如 真珠：roleId 空/不在册）——红线不存
            redline_blocked.append(ch["name"])
            print(f"[{i}/{len(roster)}] {ch['name']} ({cid}) —— 红线拦截（未上线）")
            continue
        if not ch.get("role_id"):
            failures.append(title)
            print(f"[{i}/{len(roster)}] {title} ({cid}) —— roleId 缺失且名字未匹配")
            continue
        characters[ch["role_id"]] = ch
        bad = sorted({t for s in ch["skills"] for t in s["unparsed"]})
        if bad:
            unparsed_report[ch["name"]] = bad
        if any(not s["sub_tag"] for s in ch["skills"]
               if s["tag"] in ("普攻", "战技", "终结技", "天赋", "忆灵技")):
            no_subtag.append(ch["name"])
        print(f"[{i}/{len(roster)}] {ch['name']} ({ch['role_id']}) —— 技能 {len(ch['skills'])} 条")

    out = {
        "_meta": {
            "source": "米游社·开拓者笔记（官方 WIKI）",
            "endpoints": {"roster": ROSTER_URL, "info": INFO_URL},
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "character_count": len(characters),
        },
        "characters": characters,
    }
    out_path = data_dir / "miyoushe_skill_data.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n写入 {out_path}（{len(characters)} 角色）")

    # ---- 报告（不静默）----
    if redline_blocked:
        print(f"-- 红线拦截（米游社已上架但未上线，不入库）{len(redline_blocked)}: "
              f"{', '.join(redline_blocked)}")
    if failures:
        print(f"!! 解析失败 {len(failures)}: {', '.join(failures)}")
    if no_subtag:
        print(f"!! 有无 subTag 技能的角色 {len(no_subtag)}: {', '.join(no_subtag)}")
    if unparsed_report:
        print(f"!! 未识别 subTag（需扩词表/正则）:")
        for name, tags in unparsed_report.items():
            print(f"   {name}: {tags}")
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
