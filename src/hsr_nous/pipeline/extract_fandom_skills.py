#!/usr/bin/env python3
"""从 Fandom wiki 批量提取角色技能的机制数据（回能、削韧、SP消耗）.

数据来源: https://honkai-star-rail.fandom.com
使用 MediaWiki API 获取 wikitext，从 {{Ability Infobox}} 模板提取字段。
默认值来自模板的 #switch 逻辑（网页渲染时自动展开，API 返回原始 wikitext 需手动填充）。
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Fandom wiki 命途名映射（StarRailRes path → Fandom path）
PATH_MAP = {
    "Knight": "Preservation",
    "Warrior": "Destruction",
    "Rogue": "The Hunt",
    "Mage": "Erudition",
    "Shaman": "Harmony",
    "Warlock": "Nihility",
    "Priest": "Abundance",
    "Memory": "Remembrance",
    "Elation": "Elation",
}

# 模板默认值（来自 Template:Ability Infobox 的 #switch 逻辑）
DEFAULTS = {
    "Basic ATK": {"energy_gen": "20", "toughness_dmg": "10"},
    "Skill":     {"energy_gen": "30"},
    "Ultimate":  {"energy_gen": "5"},
    # Talent / Technique 无默认值
}

# SP 消耗通用规则
SP_COST = {
    "Basic ATK": "0",   # 普攻回 1 SP（用 gain 表示）
    "Skill": "1",        # 战技消耗 1 SP
    "Ultimate": "0",     # 终结技不消耗
    "Talent": "0",       # 天赋不消耗
    "Technique": "0",    # 秘技不消耗
}
SP_GAIN = {
    "Basic ATK": "1",   # 普攻回复 1 SP
}


def fetch_page(title: str) -> str | None:
    """Fetch wiki page content via Fandom API."""
    safe_title = urllib.parse.quote(title.replace(" ", "_"), safe="/:")
    url = (
        "https://honkai-star-rail.fandom.com/api.php?"
        f"action=query&titles={safe_title}&prop=revisions&rvprop=content&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            for page in data.get("query", {}).get("pages", {}).values():
                revisions = page.get("revisions", [])
                if revisions:
                    return revisions[0].get("*", "")
    except Exception:
        return None
    return None


def get_category_members(category: str) -> list[str]:
    """Get all pages in a Fandom category."""
    encoded = urllib.parse.quote(f"Category:{category}", safe="/:")
    url = (
        "https://honkai-star-rail.fandom.com/api.php?"
        f"action=query&list=categorymembers&cmtitle={encoded}&cmlimit=50&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            return [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    except Exception:
        return []


def parse_ability_infobox(content: str) -> dict:
    """Extract fields from Ability Infobox template."""
    if not content:
        return {}
    match = re.search(r"\{\{Ability Infobox\s*\n(.*?)\}\}", content, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).strip().split("\n"):
        m = re.match(r"\|(\w+)\s*=\s*(.*)", line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def apply_defaults(info: dict) -> dict:
    """Apply template default values and normalize fields."""
    stype = info.get("type", "")
    enhanced = bool(info.get("enhanced", ""))

    # 获取原始值
    ec = info.get("energyCost", "").strip()
    eg = info.get("energyGen", "").strip()
    td = info.get("toughdmg", "").strip()

    # 应用模板默认值
    defaults = DEFAULTS.get(stype, {})
    if not eg and "energy_gen" in defaults:
        eg = defaults["energy_gen"]
    if not td and "toughness_dmg" in defaults:
        td = defaults["toughness_dmg"]

    # SP 消耗/回复
    sp_cost = SP_COST.get(stype, "0")
    sp_gain = SP_GAIN.get(stype, "0")

    return {
        "type": stype,
        "enhanced": enhanced,
        "energy_cost": ec or "",
        "energy_gen": eg or "",
        "toughness_dmg": td or "",
        "sp_cost": sp_cost,
        "sp_gain": sp_gain,
    }


def find_abilities(character_name: str, path_name: str) -> list[dict]:
    """Find all abilities for a character, trying multiple category patterns."""
    fandom_path = PATH_MAP.get(path_name, path_name)
    wiki_name = character_name.replace(" & ", " and ")

    categories = [
        f"{wiki_name}_Abilities",
        f"{wiki_name}_({fandom_path})_Abilities",
        f"{character_name}_Abilities",
        f"{character_name}_({fandom_path})_Abilities",
    ]

    for cat in categories:
        members = get_category_members(cat)
        if members and not isinstance(members, str):
            abilities = []
            for name in members:
                content = fetch_page(name)
                if content:
                    info = parse_ability_infobox(content)
                    info["page_title"] = name
                    abilities.append(info)
                time.sleep(0.15)
            return abilities

    return []


def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "data"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 Fandom wiki 提取角色技能的机制数据（回能、削韧、SP消耗）"
    )
    parser.add_argument(
        "--data-dir",
        default=str(_default_data_dir()),
        help="数据目录（默认: 项目根目录/data）",
    )
    parser.add_argument(
        "--lang", default="en",
        help="StarRailRes 语言代码（默认: en）",
    )
    parser.add_argument(
        "--id", default=None,
        help="只补抓指定角色 ID（如 1224），并合并到现有 fandom_skill_data.json",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    chars_file = data_dir / "starrailres" / "index_new" / args.lang / "characters.json"
    if not chars_file.exists():
        print(f"Error: {chars_file} not found", file=sys.stderr)
        return 1

    chars = json.loads(chars_file.read_bytes())

    out_path = data_dir / "fandom_skill_data.json"
    if args.id and out_path.exists():
        # 单角色补抓：加载现有 JSON 作为基础
        output = json.loads(out_path.read_text(encoding="utf-8"))
        if args.id in output:
            print(f"Warning: {args.id} 已在现有 JSON 中，将被覆盖")
        # 只处理指定 ID
        chars = {args.id: chars[args.id]}
    else:
        output = {}

    total = len(chars)

    for i, (cid, char) in enumerate(chars.items()):
        name = char.get("name", "")
        # 开拓者 10 个版本的 name 是 {NICKNAME} 占位符，替换为 "Trailblazer"
        # Fandom 上对应 "Trailblazer (Destruction)" 等条目
        if name == "{NICKNAME}":
            name = "Trailblazer"
        path = char.get("path", "")
        print(f"[{i+1}/{total}] {name} ({path})...", end=" ", flush=True)

        raw_abilities = find_abilities(name, path)
        skill_data = {}

        for ab in raw_abilities:
            stype = ab.get("type", "")
            if stype not in ("Basic ATK", "Skill", "Ultimate", "Talent", "Technique"):
                continue

            processed = apply_defaults(ab)
            title = ab.get("page_title", "")
            skill_data[title] = processed

        if skill_data:
            output[cid] = {"name": name, "path": path, "skills": skill_data}
            print(f"{len(skill_data)} skills")
        else:
            print("no data")

        time.sleep(0.2)

    out_path = data_dir / "fandom_skill_data.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.id:
        print(f"\nSaved to {out_path} ({len(output)} total, 本次处理 1 个角色)")
    else:
        print(f"\nSaved to {out_path} ({len(output)}/{total} characters)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
