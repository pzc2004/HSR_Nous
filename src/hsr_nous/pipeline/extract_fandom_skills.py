#!/usr/bin/env python3
"""从 Fandom wiki 批量提取角色技能的机制数据（回能、削韧、SP消耗、嘲讽值加成）.

数据来源: https://honkai-star-rail.fandom.com
- 技能数据: 每个角色的 Ability 页面，从 {{Ability Infobox}} 模板提取字段
- 嘲讽值加成: 单个 Fandom Aggro 页面，解析表格（跨角色/光锥的嘲讽值加成清单）

默认值来自模板的 #switch 逻辑（网页渲染时自动展开，API 返回原始 wikitext 需手动填充）。

SP 数据模型（2026-09 四轮核查钉死）：
- Ability Infobox **没有** SP 耗点/产点字段（数据层/模板层/渲染层均无）——
  sp_cost/sp_gain 是**类型规则合成值**（Skill 耗 1 / Basic 产 1，与官方普通技规则一致，
  但 provenance=type_default，不是 fandom 数据），强化技例外靠 tag=Enhance 判别
- 产点特例另有类目：`Category:Skill Point Generation Abilities`（Skill Point 汇总页的
  类目表，category API 可拉）——标 sp_gain_source=fandom_category 作"有特殊产点机制"信号，
  具体机制仍走模板 hooks 考据，不改数值字段
- 耗点侧 fandom 无类目（官方设计就是默认耗 1）——逐技能权威源是 BWIKI 行迹/技能
  （3.x+ 带符号战技点）与文本考据（强化技）
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
    "Knight": "Preservation", "Warrior": "Destruction", "Rogue": "The Hunt",
    "Mage": "Erudition", "Shaman": "Harmony", "Warlock": "Nihility",
    "Priest": "Abundance", "Memory": "Remembrance", "Elation": "Elation",
}

# 模板默认值（来自 Template:Ability Infobox 的 #switch 逻辑）
DEFAULTS = {
    "Basic ATK": {"energy_gen": "20", "toughness_dmg": "10"},
    "Skill":     {"energy_gen": "30"},
    "Ultimate":  {"energy_gen": "5"},
}

# SP 消耗通用规则（战技点 SP，不是秘技点 TP）——**类型规则合成值，非 fandom 数据**
#（Ability Infobox 无 SP 字段，2026-09 核查钉死；与官方普通技规则一致才可用，强化技不适用）
SP_COST = {"Basic ATK": "0", "Skill": "1", "Ultimate": "0", "Talent": "0", "Technique": "0"}
SP_GAIN = {"Basic ATK": "1"}

#: SP 产点特例类目（Fandom Skill Point 汇总页的类目表；category API 可拉）
SP_GENERATION_CATEGORIES = (
    "Skill Point Generation Abilities",            # 特殊产点机制（Sunday 蒙福者/秘技/花火族）
    "Personal Skill Point Generation Abilities",   # 个人替代资源（饮月龙鳞族）
)

TAUNT_PAGE = "Aggro"

# Taunt（Fandom Aggro 页面）提取范围（统一白名单）：
# - character: 角色技能/行迹/星魂/天赋
# - light_cone: 光锥
# 暂不收: curio（奇物）/ 消耗品。未来出嘲讽值遗器时把 "relic" 加入此集合
TAUNT_SUPPORTED_SOURCE_TYPES = {"character", "light_cone"}

# Fandom 后缀 → StarRailRes effect_text
SUFFIX_TO_EFFECT = {"Single Target": "单攻", "Blast": "扩散"}


# ---------------------------------------------------------------------------
# 网络请求
# ---------------------------------------------------------------------------

def _api(params: str) -> dict | None:
    url = f"https://honkai-star-rail.fandom.com/api.php?{params}&format=json"
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


def get_category_members(category: str) -> list[str]:
    encoded = urllib.parse.quote(f"Category:{category}", safe="/:")
    data = _api(f"action=query&list=categorymembers&cmtitle={encoded}&cmlimit=50")
    if data:
        return [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
    return []


# ---------------------------------------------------------------------------
# 技能数据提取（per-character Ability 页面）
# ---------------------------------------------------------------------------

def parse_ability_infobox(content: str) -> dict:
    if not content:
        return {}
    m = re.search(r"\{\{Ability Infobox\s*\n(.*?)\}\}", content, re.DOTALL)
    if not m:
        return {}
    result = {}
    for line in m.group(1).strip().split("\n"):
        mm = re.match(r"\|(\w+)\s*=\s*(.*)", line.strip())
        if mm:
            result[mm.group(1)] = mm.group(2).strip()
    return result


def apply_defaults(info: dict) -> dict:
    stype = info.get("type", "")
    defaults = DEFAULTS.get(stype, {})
    eg = info.get("energyGen", "").strip()
    td = info.get("toughdmg", "").strip()
    if not eg and "energy_gen" in defaults:
        eg = defaults["energy_gen"]
    if not td and "toughness_dmg" in defaults:
        td = defaults["toughness_dmg"]
    return {
        "type": stype,
        # 强化技判别：enhanced 参数 或 tag=Enhance（140809 单页无 /Enhanced 后缀但 tag 在案）
        "enhanced": bool(info.get("enhanced", "")) or info.get("tag", "").strip().lower() == "enhance",
        "energy_cost": info.get("energyCost", "").strip(),
        "energy_gen": eg,
        "toughness_dmg": td,
        "sp_cost": SP_COST.get(stype, "0"),
        "sp_gain": SP_GAIN.get(stype, "0"),
        "sp_source": "type_default",   # 类型规则合成值（非 fandom 数据）；产点特例类目命中后改写
    }


def fetch_sp_generation_sets() -> dict:
    """SP 产点特例类目（Skill Point 汇总页类目表）→ {类目: set(页面标题)}."""
    return {cat: set(get_category_members(cat) or []) for cat in SP_GENERATION_CATEGORIES}


def find_abilities(character_name: str, path_name: str) -> list[dict]:
    fandom_path = PATH_MAP.get(path_name, path_name)
    wiki_name = character_name.replace(" & ", " and ")
    for cat in [
        f"{wiki_name}_Abilities",
        f"{wiki_name}_({fandom_path})_Abilities",
        f"{character_name}_Abilities",
        f"{character_name}_({fandom_path})_Abilities",
    ]:
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


# ---------------------------------------------------------------------------
# Fandom 页面标题 → StarRailRes 技能 ID 匹配
# ---------------------------------------------------------------------------

def build_skill_lookup(sr_dir: Path) -> tuple[dict, dict]:
    """构建 (cid, en_name) → [(sid, effect_text)] 和 trace name → tid 反查表."""
    chars_en = json.loads((sr_dir / "en" / "characters.json").read_text(encoding="utf-8"))
    skills_en = json.loads((sr_dir / "en" / "character_skills.json").read_text(encoding="utf-8"))
    skills_cn = json.loads((sr_dir / "cn" / "character_skills.json").read_text(encoding="utf-8"))
    trees_en = json.loads((sr_dir / "en" / "character_skill_trees.json").read_text(encoding="utf-8"))

    char_skills: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for cid, ch in chars_en.items():
        for sid in ch.get("skills", []):
            name = skills_en.get(sid, {}).get("name", "")
            if name:
                eff = skills_cn.get(sid, {}).get("effect_text", "")
                char_skills.setdefault((cid, name), []).append((sid, eff))

    tree_name_map = {t.get("name", ""): tid for tid, t in trees_en.items() if t.get("name")}
    return char_skills, tree_name_map


def match_skill_id(cid: str, page_title: str, char_skills: dict, tree_name_map: dict) -> str | None:
    """Fandom 页面标题 → StarRailRes 技能/行迹 ID.

    规则: 精确名 → 后缀消歧(Blast/SingleTarget→effect_text) → /Enhanced→加强版(1前缀) → 行迹名全局匹配
    """
    # 分离后缀
    clean = page_title
    is_enhanced = "/Enhanced" in clean
    if is_enhanced:
        clean = clean.split("/Enhanced")[0].strip()
    target_eff = None
    for sfx, eff in SUFFIX_TO_EFFECT.items():
        if f"({sfx})" in clean:
            target_eff = eff
            clean = clean.replace(f"({sfx})", "").strip()
            break

    # 过滤候选
    raw = char_skills.get((cid, clean), [])
    candidates = [sid for sid, eff in raw if target_eff is None or eff == target_eff]
    if not candidates:
        return tree_name_map.get(clean) or tree_name_map.get(page_title)

    # 前缀消歧: /Enhanced → 优先 "1"+cid, 否则优先 cid（非"1"+cid）
    want_prefix = "1" + cid if is_enhanced else cid
    avoid_prefix = cid if is_enhanced else "1" + cid
    for sid in candidates:
        if sid.startswith(want_prefix) and not sid.startswith(avoid_prefix):
            return sid
    return candidates[0]


# ---------------------------------------------------------------------------
# Taunt（嘲讽值加成）—— 单页 scrape
# ---------------------------------------------------------------------------

def _parse_taunt_row(row: str, last_char: str | None) -> tuple[dict, str | None]:
    """解析 Taunt 表格单行. 返回 (entry, new_last_char). rowspan=2 时复用角色名."""
    char_m = re.search(r"\{\{Character\|([^|}]+)", row)
    new_char = char_m.group(1).strip() if char_m else last_char

    skill_m = re.search(r"\{\{Skill\|([^|}]+)", row)
    item_m = re.search(r"\{\{Item\|([^|}]+)\|[^}]*?type=([^|}]+)", row)
    mod_m = re.search(r"([+−\-]|&minus;)\s*(\d+)%", row)
    if not mod_m:
        return {}, last_char

    # 确定 source_type + source_name
    if skill_m and new_char:
        source_type = "character"
        source_name = skill_m.group(1).strip()
    elif item_m:
        source_type = item_m.group(2).strip().lower().replace(" ", "_")
        source_name = item_m.group(1).strip()
    else:
        return {}, last_char

    if source_type not in TAUNT_SUPPORTED_SOURCE_TYPES:
        return {}, last_char

    # 解析数值
    value = int(mod_m.group(2))
    if mod_m.group(1) in ("−", "-", "&minus;"):
        value = -value

    # 解析 target
    cells = re.split(r"\|\|", row)
    target = re.sub(r"\{\{[^}]*\}\}", "", cells[-1]).strip() if cells else ""

    entry: dict = {"modifier_pct": value, "target": target,
                    "source_type": source_type, "source_name_en": source_name}
    if source_type == "character":
        entry["character_name_en"] = new_char
        if "prefix=Trace" in row:
            entry["source_subtype"] = "trace"
        elif "text=Talent" in row:
            entry["source_subtype"] = "talent"
        else:
            entry["source_subtype"] = "skill"
    return entry, new_char


def parse_taunt_section(content: str, section_title: str, is_special: bool = False) -> list[dict]:
    pattern = rf"={{2,3}}\s*{re.escape(section_title)}\s*={{2,3}}\s*(.*?)(?=\n={{2,3}}|\Z)"
    m = re.search(pattern, content, re.DOTALL)
    if not m:
        return []

    results, last_char = [], None
    for row in re.split(r"\n\|-", m.group(1)):
        row = row.strip()
        if not row.startswith("|"):
            continue
        row_content = row.lstrip("|").strip()
        if is_special and "Base Aggro" not in row_content:
            continue
        entry, last_char = _parse_taunt_row(row_content, last_char)
        if not entry:
            continue
        if is_special:
            entry["base_modifier_pct"] = entry.pop("modifier_pct")
            entry.pop("target", None)
        results.append(entry)
    return results


def match_taunt_to_ids(entries, chars_en, chars_cn, lcs_en, lcs_cn,
                        char_skills_lookup, tree_name_lookup) -> list[str]:
    """匹配英文名到 StarRailRes ID（原地修改 entries）."""
    lc_id_by_name = {lc["name"]: cid for cid, lc in lcs_en.items()}
    warnings = []

    for entry in entries:
        if entry.get("source_type") == "character":
            raw_name = entry.get("character_name_en", "")
            clean_name = raw_name.split("(")[0].strip()
            skill_name = entry.get("source_name_en", "")

            # 同名多角色（如 March 7th 存护/巡猎）用技能名反查消歧
            cids = [cid for cid, ch in chars_en.items() if ch.get("name") == clean_name]
            if len(cids) == 1:
                cid = cids[0]
            elif len(cids) > 1:
                cid = next((c for c in cids
                            if match_skill_id(c, skill_name, char_skills_lookup, tree_name_lookup)), None)
            else:
                cid = None

            if cid:
                entry["character_id"] = cid
                entry["character_name_cn"] = chars_cn.get(cid, {}).get("name", "")
                sid = match_skill_id(cid, skill_name, char_skills_lookup, tree_name_lookup)
                if sid:
                    entry["source_id"] = sid
                else:
                    warnings.append(f"skill unmatched: {raw_name} / {skill_name}")
            else:
                warnings.append(f"char unmatched: {raw_name}")

        elif entry.get("source_type") == "light_cone":
            lid = lc_id_by_name.get(entry.get("source_name_en", ""))
            if lid:
                entry["source_id"] = lid
                entry["source_name_cn"] = lcs_cn.get(lid, {}).get("name", "")
            else:
                warnings.append(f"light cone unmatched: {entry.get('source_name_en', '')}")

    return warnings


def fetch_taunt_modifiers(sr_dir, char_skills_lookup, tree_name_lookup):
    """抓取 Taunt 数据并匹配 ID. 返回 (modifiers, base_modifiers, warnings)."""
    content = fetch_page(TAUNT_PAGE)
    if not content:
        return [], [], [f"fetch failed: {TAUNT_PAGE}"]

    modifiers = parse_taunt_section(content, "Aggro Modifiers")
    base_mods = parse_taunt_section(content, "Special Aggro Modification Effects", is_special=True)
    print(f"Taunt: {len(modifiers)} modifiers, {len(base_mods)} base modifiers")

    chars_en = json.loads((sr_dir / "en" / "characters.json").read_text(encoding="utf-8"))
    chars_cn = json.loads((sr_dir / "cn" / "characters.json").read_text(encoding="utf-8"))
    lcs_en = json.loads((sr_dir / "en" / "light_cones.json").read_text(encoding="utf-8"))
    lcs_cn = json.loads((sr_dir / "cn" / "light_cones.json").read_text(encoding="utf-8"))

    warnings = []
    for entries in (modifiers, base_mods):
        warnings += match_taunt_to_ids(entries, chars_en, chars_cn, lcs_en, lcs_cn,
                                        char_skills_lookup, tree_name_lookup)
    return modifiers, base_mods, warnings


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "data"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 Fandom wiki 提取角色技能的机制数据（回能、削韧、SP消耗、嘲讽值加成）"
    )
    parser.add_argument("--data-dir", default=str(_default_data_dir()))
    parser.add_argument("--lang", default="en")
    parser.add_argument("--id", default=None, help="只补抓指定角色 ID")
    parser.add_argument("--only-taunt", action="store_true", help="只抓嘲讽值加成，合并到 fandom_skill_data.json")
    args = parser.parse_args()

    if args.id and args.only_taunt:
        print("Error: --id 和 --only-taunt 互斥", file=sys.stderr)
        return 1

    data_dir = Path(args.data_dir)
    sr_dir = data_dir / "starrailres" / "index_new"
    out_path = data_dir / "fandom_skill_data.json"

    # 构建反查表（技能 + taunt 共用）
    char_skills_lookup, tree_name_lookup = build_skill_lookup(sr_dir)

    # === 嘲讽值加成 ===
    modifiers, base_mods, taunt_warnings = fetch_taunt_modifiers(
        sr_dir, char_skills_lookup, tree_name_lookup,
    )
    if taunt_warnings:
        print(f"Taunt warnings ({len(set(taunt_warnings))}):")
        for w in sorted(set(taunt_warnings)):
            print(f"  - {w}")
    else:
        print("All taunt entries matched.")

    if args.only_taunt:
        existing = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
        if modifiers:
            existing["_taunt_modifiers"] = modifiers
        if base_mods:
            existing["_taunt_base_modifiers"] = base_mods
        out_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Merged into {out_path}")
        return 0

    # === 技能数据 ===
    chars_file = sr_dir / args.lang / "characters.json"
    if not chars_file.exists():
        print(f"Error: {chars_file} not found", file=sys.stderr)
        return 1

    chars = json.loads(chars_file.read_bytes())
    if args.id and out_path.exists():
        output = json.loads(out_path.read_text(encoding="utf-8"))
        chars = {args.id: chars[args.id]}
    else:
        output = {}

    total, skill_warnings = len(chars), []
    sp_gen_sets = fetch_sp_generation_sets()   # SP 产点特例类目（一次性拉取，全员共用）

    for i, (cid, char) in enumerate(chars.items(), 1):
        name = "Trailblazer" if char.get("name") == "{NICKNAME}" else char.get("name", "")
        path = char.get("path", "")
        print(f"[{i}/{total}] {name} ({path})...", end=" ", flush=True)

        skill_data = {}
        for ab in find_abilities(name, path):
            if ab.get("type") not in ("Basic ATK", "Skill", "Ultimate", "Talent", "Technique"):
                continue
            processed = apply_defaults(ab)
            title = ab.get("page_title", "")
            # SP 产点特例信号：类目命中=有特殊产点机制（机制本体仍走模板 hooks 考据，不改数值）
            if title in sp_gen_sets["Skill Point Generation Abilities"]:
                processed["sp_source"] = "fandom_category"
            if title in sp_gen_sets["Personal Skill Point Generation Abilities"]:
                processed["personal_sp_resource"] = True
                processed["sp_source"] = "fandom_category"
            sid = match_skill_id(cid, title, char_skills_lookup, tree_name_lookup)
            if sid:
                processed["fandom_page"] = title
                skill_data[sid] = processed
            else:
                skill_warnings.append(f"{name}({cid}): {title}")

        if skill_data:
            output[cid] = {"name": name, "path": path, "skills": skill_data}
            print(f"{len(skill_data)} skills")
        else:
            print("no data")
        time.sleep(0.2)

    # 合并 taunt
    if modifiers:
        output["_taunt_modifiers"] = modifiers
    if base_mods:
        output["_taunt_base_modifiers"] = base_mods

    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {out_path} ({len(output)}/{total} entries)")

    if skill_warnings:
        print(f"Skill warnings ({len(set(skill_warnings))}):")
        for w in sorted(set(skill_warnings)):
            print(f"  - {w}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
