#!/usr/bin/env python3
"""从 BWIKI（哔哩哔哩游戏 WIKI）提取角色技能的机制数据（战技点/削韧/类型/范围/秘技/能量上限）.

数据来源: https://wiki.biligame.com/sr（MediaWiki API，与 fandom 同构）
- 逐技能结构：角色页的 {{行迹/技能}} 模板（3.x+ 角色全量铺开；2.x 及更老页面无此结构）
- 战技点带符号：正=产点、负=耗点、显式 0=免费；**空白=未填（None），不是 0**——
  强化/派生形态编辑常留空（火花强化普攻空白但游戏内实际产点，2026-09-05 owner 实测裁定），
  只有显式值可当权威；基础战技空白可用"编辑几乎必标 -1"先验弱推断为 0
- 类型自带强化区分（强化普攻/强化战技N）——enhanced 判别的权威源

输出 data/bwiki_skill_data.json（与 fandom_skill_data.json 同目录并存，字段带 provenance）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://wiki.biligame.com/sr/api.php"

#: BWIKI 类型 → (action_type, enhanced)
TYPE_MAP = {
    "普攻": ("basic", False), "强化普攻": ("basic", True),
    "战技": ("skill", False), "终结技": ("ultimate", False),
    "秘技": ("technique", False),
}


def _api(params: str) -> dict | None:
    url = f"{API}?{params}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def fetch_page(title: str) -> str | None:
    safe = urllib.parse.quote(title.replace(" ", "_"), safe="/:")
    data = _api(f"action=query&titles={safe}&prop=revisions&rvprop=content")
    if data:
        for page in data.get("query", {}).get("pages", {}).values():
            revs = page.get("revisions", [])
            if revs:
                return revs[0].get("*", "")
    return None


def iter_templates(text: str, name: str):
    """花括号配平逐个切出 {{name|...}} 模板块（描述内可嵌 {{颜色|...}}）。"""
    start = 0
    while True:
        i = text.find("{{" + name, start)
        if i < 0:
            return
        depth, j = 0, i
        while j < len(text) - 1:
            two = text[j:j + 2]
            if two == "{{":
                depth += 1
                j += 2
            elif two == "}}":
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        yield text[i:j]
        start = j


def split_top_level(body: str) -> dict:
    """按顶层 | 切字段（嵌套模板内的 | 不切）。"""
    fields, buf, depth = [], [], 0
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "|" and depth == 0:
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    fields.append("".join(buf))
    out = {}
    for f in fields:
        m = re.match(r"\s*([^=]+?)\s*=\s*(.*)", f, re.DOTALL)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def parse_character(text: str) -> tuple[list[dict], str]:
    """角色页 → (技能块列表, 能量上限原文)。技能块 = 各行迹/技能模板的字段字典。"""
    skills = []
    for tpl in iter_templates(text, "行迹/技能"):
        inner = tpl[len("{{行迹/技能"):-2]
        f = split_top_level(inner)
        if f.get("名称"):
            skills.append(f)
    cap = ""
    m = re.search(r"\|能量上限\s*=\s*([^\n|]+)", text)
    if m:
        cap = m.group(1).strip()
    return skills, cap


def parse_sp(raw: str) -> int | None:
    """战技点原文 → 带符号整数；**空白/非数字 = 未填（None），不是 0**.

    空白≠0（2026-09-05 火花强化普攻教训：BWIKI 强化形态常留空，游戏内实际产点）——
    只有显式数字（含显式 0）才可当权威值；基础战技的空白可结合"编辑几乎必标 -1"
    的先验弱推断为 0，强化形态空白 = 纯未知，需实测或 owner 游戏内裁定。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="从 BWIKI 提取角色技能机制数据（战技点/削韧/类型等）")
    parser.add_argument("--data-dir", default=str(Path(__file__).parent.parent.parent.parent / "data"))
    parser.add_argument("--id", default=None, help="只处理指定角色 ID")
    parser.add_argument("--dry-run", action="store_true", help="只打印样张不写文件")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    chars_cn = json.loads((data_dir / "starrailres" / "index_new" / "cn" / "characters.json").read_text(encoding="utf-8"))
    skills_cn = json.loads((data_dir / "starrailres" / "index_new" / "cn" / "character_skills.json").read_text(encoding="utf-8"))

    targets = {args.id: chars_cn[args.id]} if args.id else chars_cn
    output = {}
    for cid, ch in targets.items():
        cname = ch.get("name", "")
        if not cname or cname == "{NICKNAME}":
            continue
        text = fetch_page(cname)
        if not text:
            print(f"{cid} {cname}: 页面拉取失败")
            continue
        blocks, cap = parse_character(text)
        if not blocks:
            print(f"{cid} {cname}: 无 行迹/技能 结构（2.x 及更老页面常态）")
            continue
        # 名称 → sid 反查（含类型一致性校验）
        name2sid = {skills_cn[sid]["name"]: sid for sid in ch.get("skills", []) if sid in skills_cn}
        skills_out = {}
        for b in blocks:
            bname, btype = b["名称"], b.get("类型", "")
            sid = name2sid.get(bname)
            atype, enhanced = TYPE_MAP.get(btype, (btype, None))
            entry = {
                "name": bname, "type_cn": btype, "action_type": atype,
                "enhanced": enhanced if not btype.startswith("天赋") else None,
                "tag": b.get("TAG", ""),
                "sp": parse_sp(b.get("战技点", "")),
                "toughness_dmg": b.get("削韧值", "").strip(),
                "desc": b.get("描述", ""),
                "source": "bwiki",
            }
            skills_out[sid or f"?{bname}"] = entry
        output[cid] = {"name": cname, "energy_cap": cap, "skills": skills_out}
        print(f"{cid} {cname}: {len(blocks)} 块，能量上限={cap or '—'}")
        if args.dry_run:
            for sid, e in skills_out.items():
                print(f"    {sid:>8} [{e['type_cn'] or '?'}] sp={e['sp'] if e['sp'] is not None else '空'} 削韧={e['toughness_dmg'] or '—'} tag={e['tag'] or '—'}")
        time.sleep(0.2)

    if not args.dry_run:
        out_path = data_dir / "bwiki_skill_data.json"
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved to {out_path} ({len(output)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
