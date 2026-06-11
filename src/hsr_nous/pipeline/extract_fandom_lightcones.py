#!/usr/bin/env python3
"""从 Fandom wiki 提取角色 → 专光映射, 输出两个文件.

数据来源: https://honkai-star-rail.fandom.com (MediaWiki API)
抓取策略: 角色页面 wikitext 里 `|lightcone =` 字段 (模板 Character Infobox)

输出:
    1. data/fandom_meta/character_lightcones.json
       Fandom 原始抓取缓存: {char_name: lc_name | null}.
       4★ 角色 / 无专光字段的填 null.
       这是 cache, 用于人审/手工补漏, 不直接喂给下游.

    2. data/signature_light_cones.json
       名字→ID 映射后的成品: {char_id: {char_name_*, lc_name_*, sig_lc_id}}.
       只含 5★ 角色. 给 query-game-data skill / agent 直接用.
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 开拓者 ({NICKNAME} 占位符) 在 Fandom 上没有 lightcone 字段 — 跟 4★ 一样没专光.
# 但 Fandom 有 "Trailblazer (Destruction)" 等命途页面, 我们抓 Destruction 兜底确认.
TRAILBLAZER_FANDOM_TITLE = "Trailblazer (Destruction)"


def _user_agent() -> str:
    return "HSR_Nous/0.1"


def fetch_page(title: str) -> str | None:
    """Fetch wiki page wikitext via Fandom MediaWiki API."""
    safe_title = urllib.parse.quote(title.replace(" ", "_"), safe="/:")
    url = (
        "https://honkai-star-rail.fandom.com/api.php?"
        f"action=query&titles={safe_title}&prop=revisions&rvprop=content&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
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


def parse_lightcone_field(content: str) -> str | None:
    """从 Character Infobox 模板里提取 `|lightcone =` 字段.

    返回 light cone 名, 没有该字段则 None.
    """
    if not content:
        return None
    # 模板 {{Character Infobox ... }} 块可能跨多行
    m = re.search(r"\{\{Character Infobox\s*\n(.*?)\}\}", content, re.DOTALL)
    if not m:
        return None
    for line in m.group(1).splitlines():
        lm = re.match(r"\|\s*lightcone\s*=\s*(.*)", line.strip())
        if lm:
            value = lm.group(1).strip()
            return value or None
    return None


def scrape_one(char_name: str) -> str | None:
    """抓单个角色页面的 lightcone 字段."""
    title = TRAILBLAZER_FANDOM_TITLE if char_name == "{NICKNAME}" else char_name
    content = fetch_page(title)
    return parse_lightcone_field(content)


# ---------------------------------------------------------------------------
# 步骤 A: Fandom 抓取 → fandom_meta/character_lightcones.json
# ---------------------------------------------------------------------------
def step_scrape_fandom(
    chars: dict,
    out_path: Path,
    *,
    single_id: str | None = None,
) -> dict:
    """抓所有 (或单个) 角色的 lightcone 字段. 返回 {char_name: lc_name | null}."""
    if single_id and out_path.exists():
        output = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"Loaded existing cache: {len(output)} entries")
    else:
        output = {}

    if single_id:
        if single_id not in chars:
            print(f"Error: char id {single_id} not in characters.json", file=sys.stderr)
            sys.exit(1)
        targets = [(single_id, chars[single_id])]
    else:
        targets = list(chars.items())

    total = len(targets)
    for i, (cid, char) in enumerate(targets, 1):
        name = char.get("name", "")
        fandom_name = "Trailblazer" if name == "{NICKNAME}" else name
        print(f"[{i}/{total}] {fandom_name} (id={cid})...", end=" ", flush=True)

        lc_name = scrape_one(name)
        if lc_name:
            print(f"-> {lc_name}")
        else:
            print("no lightcone (4★ or missing field)")
            lc_name = None

        output[fandom_name] = lc_name
        time.sleep(0.15)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output


# ---------------------------------------------------------------------------
# 步骤 B: 名字→ID 映射 → signature_light_cones.json
# ---------------------------------------------------------------------------
def step_build_json(
    fandom_data: dict,
    data_dir: Path,
    out_path: Path,
) -> None:
    """把 {char_name: lc_name} 转成 {char_id: {..., sig_lc_id}}.

    只输出 5★ 角色. 4★ 跳过 (Fandom 也会写专光但 query-game-data 不需要).

    data_dir: 项目根下的 data/ 目录, loader 内部需要 data/starrailres/.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from hsr_nous.pipeline.loader import (  # noqa: E402
        get_character,
        get_character_by_name,
        get_light_cone,
        get_light_cone_by_name,
    )

    # loader 假定 data_dir 指向 data/starrailres
    sr_data_dir = str(data_dir / "starrailres")

    out: dict = {}
    missing: list[str] = []

    for char_name, lc_name in sorted(fandom_data.items()):
        if not lc_name:
            continue
        # 角色: EN 名 → char_id
        char = get_character_by_name(char_name, data_dir=sr_data_dir, lang="en")
        if not char:
            char = get_character_by_name(char_name, data_dir=sr_data_dir, lang="cn")
        if not char:
            missing.append(f"char not found: {char_name}")
            continue
        char_id = char["id"]
        rarity = str(char.get("rarity", ""))
        if rarity != "5":
            # 4★ 跳过
            continue

        # 专光: EN 名 → lc_id
        lc = get_light_cone_by_name(lc_name, data_dir=sr_data_dir, lang="en")
        if not lc:
            missing.append(f"{char_name}: LC not found: {lc_name}")
            # 仍然写入, sig_lc_id 留 None (下游 query.py 已知会打 warning)
            cn_char = get_character(char_id, data_dir=sr_data_dir, lang="cn")
            en_char = get_character(char_id, data_dir=sr_data_dir, lang="en")
            out[char_id] = {
                "char_name_cn": cn_char.get("name", "") if cn_char else "",
                "char_name_en": en_char.get("name", "") if en_char else char_name,
                "lc_name_cn": "",
                "lc_name_en": lc_name,
                "sig_lc_id": None,
            }
            continue

        lc_id = lc["id"]
        cn_char = get_character(char_id, data_dir=sr_data_dir, lang="cn")
        en_char = get_character(char_id, data_dir=sr_data_dir, lang="en")
        cn_lc = get_light_cone(lc_id, data_dir=sr_data_dir, lang="cn")
        out[char_id] = {
            "char_name_cn": cn_char.get("name", "") if cn_char else "",
            "char_name_en": en_char.get("name", "") if en_char else char_name,
            "lc_name_cn": cn_lc.get("name", "") if cn_lc else "",
            "lc_name_en": lc_name,
            "sig_lc_id": lc_id,
        }

    # 写 json (sort_keys + indent 2 便于人审)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {cid: out[cid] for cid in sorted(out)},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(f"\nWrote {len(out)} entries to {out_path}")
    if missing:
        print("\nWarnings:")
        for m in missing:
            print(f"  - {m}")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "data"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 Fandom wiki 提取角色 → 专光映射, 输出 JSON cache + JSON 成品"
    )
    parser.add_argument(
        "--data-dir",
        default=str(_default_data_dir()),
        help="数据目录 (默认: 项目根目录/data)",
    )
    parser.add_argument(
        "--lang", default="en",
        help="StarRailRes 语言代码 (默认: en, Fandom 是英文 wiki)",
    )
    parser.add_argument(
        "--id", default=None,
        help="只补抓指定角色 ID, 并合并到现有 cache. 例: --id 1224",
    )
    parser.add_argument(
        "--skip-fandom", action="store_true",
        help="跳过 Fandom 抓取, 直接用现有 cache 生成 json",
    )
    parser.add_argument(
        "--skip-json", action="store_true",
        help="只跑 Fandom 抓取, 不生成 json",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    chars_file = data_dir / "starrailres" / "index_new" / args.lang / "characters.json"
    if not args.skip_fandom and not chars_file.exists():
        print(f"Error: {chars_file} not found", file=sys.stderr)
        return 1

    fandom_cache = data_dir / "fandom_meta" / "character_lightcones.json"
    json_out = data_dir / "signature_light_cones.json"

    if not args.skip_fandom:
        chars = json.loads(chars_file.read_bytes()) if chars_file.exists() else {}
        fandom_data = step_scrape_fandom(
            chars, fandom_cache, single_id=args.id
        )
    else:
        if not fandom_cache.exists():
            print(f"Error: {fandom_cache} not found, can't skip Fandom scrape",
                  file=sys.stderr)
            return 1
        fandom_data = json.loads(fandom_cache.read_text(encoding="utf-8"))
        print(f"Loaded {len(fandom_data)} entries from {fandom_cache}")

    if args.skip_json:
        return 0

    step_build_json(fandom_data, data_dir, json_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
