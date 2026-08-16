#!/usr/bin/env python3
"""从 Fandom EN wiki 批量提取敌人机制数据（基础信息/抗性/技能倍率/阶段）.

数据来源: https://honkai-star-rail.fandom.com （Category:Enemies 全部成员页面）
- {{Enemy Infobox}}: tier / type(攻击属性) / weakness / tough(韧性，多变体取主值并保留注记) / faction / ability
- {{Enemy Stats}}: 各元素抗性 + debuff 抵抗 + hp/spd/atk/eres（首页块为主值，后续块为多阶段变体）
- {{Enemy Skills}}: 技能名/类型/描述（含倍率，如 350% ATK）/phase 阶段

只提取模板里的机制数值字段，lore 散文（Enemy Info 等）不存；解析失败的页面记入 _meta.failed 不中断。

用法:
    python -m hsr_nous.pipeline.extract_fandom_enemies --limit 5   # 先跑 5 个验证
    python -m hsr_nous.pipeline.extract_fandom_enemies             # 全量
输出: data/fandom_enemy_data.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_API_URL = "https://honkai-star-rail.fandom.com/api.php"
_ENEMY_CATEGORY = "Category:Enemies"

# Enemy Stats 结构化字段（元素抗性 / debuff 抵抗 / 数值缩放）
_RES_FIELDS = [
    "physical_res", "fire_res", "ice_res", "lightning_res",
    "wind_res", "quantum_res", "imaginary_res",
]
_DEBUFF_RES_FIELDS = [
    "bleed_res", "burn_res", "frozen_res", "shock_res",
    "windsheer_res", "entanglement_res", "imprisonment_res", "ctrleff_res",
]
_SCALE_FIELDS = ["hp", "spd", "atk", "eres", "scaling_type"]


# ---------------------------------------------------------------------------
# 网络请求（带重试，调用方负责 sleep 礼貌限速）
# ---------------------------------------------------------------------------

def _api(params: str, timeout: float = 20.0, retries: int = 3) -> dict | None:
    url = f"{_API_URL}?{params}&format=json"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt == retries - 1:
                print(f"[warn] 请求失败({retries} 次): {url} -> {exc}", file=sys.stderr)
            else:
                time.sleep(2.0 * (attempt + 1))
    return None


def list_enemy_pages(*, timeout: float = 20.0) -> list[str]:
    """枚举 Category:Enemies 全部成员页面名（cmcontinue 分页）."""
    titles: list[str] = []
    cont = ""
    while True:
        params = (
            "action=query&list=categorymembers"
            f"&cmtitle={urllib.parse.quote(_ENEMY_CATEGORY)}&cmlimit=500"
        )
        if cont:
            params += f"&cmcontinue={urllib.parse.quote(cont)}"
        data = _api(params, timeout=timeout)
        if not data:
            break
        # 只要主命名空间（ns=0）：子分类页（Category:Enemies by * 等）不是敌人，
        # 不过滤会空解析污染 failed
        titles += [
            m["title"]
            for m in data.get("query", {}).get("categorymembers", [])
            if m.get("ns") == 0
        ]
        cont = data.get("continue", {}).get("cmcontinue", "")
        if not cont:
            break
        time.sleep(0.3)
    return titles


def fetch_wikitext(title: str, *, timeout: float = 20.0) -> str | None:
    safe = urllib.parse.quote(title.replace(" ", "_"), safe="/:")
    data = _api(f"action=parse&page={safe}&prop=wikitext", timeout=timeout)
    if data:
        return data.get("parse", {}).get("wikitext", {}).get("*")
    return None


# ---------------------------------------------------------------------------
# 模板解析（纯函数，离线可测）
# ---------------------------------------------------------------------------

def _iter_templates(wikitext: str, name: str):
    """产出所有 {{name ...}} 顶层模板的 (起始位置, 全文)，按大括号配平收尾."""
    needle = "{{" + name
    start = 0
    while True:
        i = wikitext.find(needle, start)
        if i < 0:
            return
        j = i + len(needle)
        # 模板名后必须是 | / 换行 / 空白 / }}，防止误中同名前缀模板
        if j < len(wikitext) and wikitext[j] not in "\n\r\t |}":
            start = j
            continue
        depth, k = 0, i
        while k < len(wikitext) - 1:
            two = wikitext[k:k + 2]
            if two == "{{":
                depth += 1
                k += 2
                continue
            if two == "}}":
                depth -= 1
                k += 2
                if depth == 0:
                    break
                continue
            k += 1
        yield i, wikitext[i:k]
        start = k


def _split_params(template: str) -> dict[str, str]:
    """把模板体按行切为 {参数名: 值}（敌人模板一行一个参数；跨行值只取首行够用字段）."""
    body = template[2:-2] if template.endswith("}}") else template[2:]
    params: dict[str, str] = {}
    for line in body.split("\n")[1:]:
        line = line.strip()
        if not line.startswith("|"):
            continue
        m = re.match(r"\|([^=|]+?)\s*=\s*(.*)$", line)
        if m:
            params[m.group(1).strip()] = m.group(2).strip()
    return params


def _strip_markup(text: str) -> str:
    """轻量剥 wiki 标记：粗斜体记号、[[link|text]]/[[text]]、简单展示模板取最后参数."""
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)

    def _tpl(m: re.Match) -> str:
        parts = m.group(1).split("|")
        return parts[-1].strip() if len(parts) > 1 else ""

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\{\{([^{}]*)\}\}", _tpl, text)
    text = re.sub(r"<br\s*/?>", "; ", text)
    return re.sub(r"\s+", " ", text).strip()


def _num(text: str) -> int | float | None:
    """解析数值字符串；整数给 int，否则 float；解析不了给 None."""
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value == int(value) else value


def _parse_tough(raw: str) -> tuple[int | float | None, str | None]:
    """韧性字段：`240 (Normal)<br />200 (''[[X]]'' only)` 多变体——取首行主值，
    全文清理 `<br />`/括号注记后作为 toughness_detail 保留（无注记给 None）."""
    raw = raw.strip()
    if not raw:
        return None, None
    first_line = re.split(r"<br\s*/?>", raw)[0]
    m = re.search(r"\d+(?:\.\d+)?", first_line)
    main = _num(m.group(0)) if m else None
    detail = _strip_markup(raw)
    # 干净单值（如 "150"）无注记；带变体/括号说明才保留 detail
    bare = re.fullmatch(r"\d+(?:\.\d+)?", raw)
    return main, (None if bare else detail or None)


def parse_enemy_infobox(wikitext: str) -> dict:
    """{{Enemy Infobox}} -> tier / attack_element / weaknesses / toughness / faction / abilities."""
    tpl = next((t for _pos, t in _iter_templates(wikitext, "Enemy Infobox")), None)
    if tpl is None:
        return {}
    p = _split_params(tpl)
    toughness, toughness_detail = _parse_tough(p.get("tough", ""))
    out = {
        "tier": p.get("tier", "").strip(),
        "attack_element": p.get("type", "").strip() or None,
        "weaknesses": [s.strip() for s in p.get("weakness", "").split(";") if s.strip()],
        "toughness": toughness,
        "faction": p.get("faction", "").strip() or None,
        "abilities": [s.strip() for s in p.get("ability", "").split(";") if s.strip()],
    }
    if toughness_detail:
        out["toughness_detail"] = toughness_detail
    return out


def _parse_stats_block(template: str) -> dict:
    p = _split_params(template)
    rec: dict = {}
    for key in _RES_FIELDS + _DEBUFF_RES_FIELDS + _SCALE_FIELDS:
        value = _num(p.get(key, ""))
        if value is not None:
            rec[key] = value
    return rec


def _section_label_before(wikitext: str, pos: int, floor: int) -> str | None:
    """找 pos 之前最近的 ===小节=== 标题（不越过上一个模板块 floor）."""
    head = wikitext[floor:pos]
    m = None
    for m in re.finditer(r"^={2,}\s*(.+?)\s*={2,}\s*$", head, re.M):
        pass
    return m.group(1).strip() if m else None


def parse_enemy_stats(wikitext: str) -> tuple[dict, list[dict]]:
    """{{Enemy Stats}} -> (主 stats, 变体列表). 首页块为主值；后续块按前方小节标题打标."""
    blocks = list(_iter_templates(wikitext, "Enemy Stats"))
    if not blocks:
        return {}, []
    stats = _parse_stats_block(blocks[0][1])
    variants: list[dict] = []
    for i in range(1, len(blocks)):
        pos, tpl = blocks[i]
        rec = _parse_stats_block(tpl)
        label = _section_label_before(wikitext, pos, blocks[i - 1][0])
        if label:
            rec["variant"] = label
        variants.append(rec)
    return stats, variants


def parse_enemy_skills(wikitext: str) -> list[dict]:
    """{{Enemy Skills}} -> [{name, type, desc, phase, ...}]. 参数按数字后缀分组（跳过 file*）."""
    tpl = next((t for _pos, t in _iter_templates(wikitext, "Enemy Skills")), None)
    if tpl is None:
        return []
    p = _split_params(tpl)
    indices = sorted(
        int(m.group(1))
        for key in p
        for m in [re.fullmatch(r"name(\d+)", key)]
        if m
    )
    skills: list[dict] = []
    for i in indices:
        name = _strip_markup(p.get(f"name{i}", ""))
        if not name:
            continue
        skill = {
            "name": name,
            "type": p.get(f"type{i}", "").strip() or None,
            "desc": _strip_markup(p.get(f"desc{i}", "")),
            "phase": p.get(f"phase{i}", "").strip() or None,
        }
        energy = _num(p.get(f"energy{i}", ""))
        if energy is not None:
            skill["energy"] = energy
        if p.get(f"danger{i}", "").strip():
            skill["danger"] = True
        caption = _strip_markup(p.get(f"caption{i}", ""))
        if caption:
            skill["caption"] = caption
        skills.append(skill)
    return skills


def parse_enemy_page(wikitext: str) -> dict:
    """汇总一个敌人页面；三个模板一个都没解析出来时返回 {}（调用方记 failed）."""
    if not wikitext:
        return {}
    infobox = parse_enemy_infobox(wikitext)
    stats, stats_variants = parse_enemy_stats(wikitext)
    skills = parse_enemy_skills(wikitext)
    if not infobox and not stats and not skills:
        return {}
    out = dict(infobox)
    if stats:
        out["stats"] = stats
    if stats_variants:
        out["stats_variants"] = stats_variants
    out["skills"] = skills
    return out


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "data"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 Fandom EN wiki 提取敌人机制数据（基础信息/抗性/技能倍率/阶段）"
    )
    parser.add_argument("--data-dir", default=str(_default_data_dir()))
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个页面（调试用，0=全量）")
    parser.add_argument("--sleep", type=float, default=0.3, help="页面间礼貌限速秒数")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    out_path = data_dir / "fandom_enemy_data.json"

    print("[1/2] 枚举 Category:Enemies ...")
    titles = list_enemy_pages(timeout=args.timeout)
    if not titles:
        print("Error: 分类枚举为空", file=sys.stderr)
        return 1
    if args.limit:
        titles = titles[: args.limit]
    print(f"  共 {len(titles)} 个页面待解析")

    output: dict = {}
    failed: list[str] = []
    total = len(titles)
    for i, title in enumerate(titles, 1):
        wikitext = fetch_wikitext(title, timeout=args.timeout)
        if wikitext is None:
            failed.append(title)
            print(f"[{i}/{total}] {title}: 拉取失败")
            time.sleep(args.sleep)
            continue
        record = parse_enemy_page(wikitext)
        if not record:
            failed.append(title)
            print(f"[{i}/{total}] {title}: 模板解析为空，记 failed")
        else:
            record["_page_title"] = title
            record["_extracted_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            output[title] = record
            print(f"[{i}/{total}] {title}: {len(record['skills'])} skills")
        time.sleep(args.sleep)

    output["_meta"] = {
        "source": "https://honkai-star-rail.fandom.com (Category:Enemies wikitext templates)",
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(output),
        "failed": failed,
    }
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved to {out_path} ({len(output) - 1}/{total} 条, failed={len(failed)})")
    return 0 if len(output) > 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
