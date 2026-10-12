#!/usr/bin/env python3
"""一次性批处理（决策卡 #24 ④）：data/library 存量挂账注 → 模板 caveats 机读键.

提取源（两路机读/半机读，原中文注释一律不动——机读化不是替换）：
A. YAML 机读注块：顶层 trace_notes/scaling_notes/notes + eidolons.*.notes 中含标记词的条目；
B. 注释行 `# 待实测：<文本>` 模式（含更深缩进的续行合并）。

判级（任务口径）：「待实测/官方未写/口径未定/待复核/待确认/待收」→ pending；
「近似/≈/宽口径」→ approx。已核销语义（收编/收官/核销/翻案/退役/消灭语境）不提取；
「待实测：无」显式空账不提取；拿不准的不进（脚本输出未进清单供人工核）。

已含 caveats 键的文件（人工策展件）整文件跳过，不机械合并。
用法：.venv/bin/python scripts/extract_caveats.py [--apply]（缺省 dry-run 只出报告）
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MARK_RE = re.compile(r"待实测|官方未写|口径未定|待复核|待确认|待收")
APPROX_RE = re.compile(r"近似|≈|宽口径")
#: 已核销语境（标记词出现在这些语境=历史记录不是活账——整条皆核销才跳过）
RESOLVED_RE = re.compile(r"已收编|已收官|已核销|已消灭|收编消灭|翻案|退役|旧待收|旧近似|核销|消解|同销|已收口|收口")
#: 条目切分（子句级判活——核销子句不计，活子句定级）
CLAUSE_SPLIT = re.compile(r"[；;。\n]")
#: 注释挂账行两态：`# 待实测：<文本>`（前缀即标记——正文无标记词默认 pending）与
#: `# 待收[清单][（…）]：<①…②…>`（头注枚举——按 ①②③ 数字序号切条，序号前字黑名单防
#: 「待收⑦/勘正⑯」类行内引用误切）
HEADER_RE = re.compile(r"^\s*#\s*待实测(?:/[^：:\n]{1,12})?[:：]\s*(.*)$")
PENDING_RE = re.compile(r"^\s*#\s*(?:待收|挂账)(?:清单)?(?:（[^）]*）)?\s*[:：]?\s*(.*)$")
#: 条目序号切分：序号后须跟空格/CJK（防「②DoT」「③1108102」「⑥65%」类行内引用误切），
#: 前字黑名单防「待收⑦/勘正⑯/星历②/…/②」类引用误切
NUMERAL_SPLIT_RE = re.compile(
    r"(?<![待收勘正同见案例批项条族谱历#第在/])([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])(?=[\s一-鿿])")
#: 枚举序号字符（参与「≥2 个才切」判定——单序号多为行内引用不切）
_NUMERALS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _notes_entries(doc: dict) -> list[str]:
    """YAML 机读注块条目（顶层 trace_notes/scaling_notes/notes + eidolons.*.notes）."""
    out: list[str] = []
    for key in ("trace_notes", "scaling_notes", "notes"):
        v = doc.get(key)
        if isinstance(v, list):
            out += [str(x) for x in v]
        elif isinstance(v, str):
            out.append(v)
    eid = doc.get("eidolons")
    if isinstance(eid, dict):
        for e in eid.values():
            if isinstance(e, dict):
                v = e.get("notes")
                if isinstance(v, list):
                    out += [str(x) for x in v]
                elif isinstance(v, str):
                    out.append(v)
    return out


def _comment_entries(raw: str) -> list[tuple[str, str]]:
    """注释挂账行 → [(text, default_level)]（续行=更深缩进的注释行，合并为一条）.

    默认级来源：`# 待实测：` 前缀本身即 pending 标记（正文无标记词不再漏——20004 幽邃
    「可驱散性」病例）；`# 待收…：` 列表成员身份即 pending 标记（待收=未建模未决语义）。
    """
    lines = raw.splitlines()
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        m = HEADER_RE.match(lines[i])
        if m is None:
            m = PENDING_RE.match(lines[i])
        if m is None:
            i += 1
            continue
        text = m.group(1).strip()
        j = i + 1
        while j < len(lines):
            cont = re.match(r"^\s*#\s{2,}(\S.*)$", lines[j])
            if not cont:
                break
            text += cont.group(1).strip()
            j += 1
        # 头注枚举按 ①②③ 切条（≥2 个序号才切；序号前字黑名单防行内引用误切）
        parts = [text]
        if sum(text.count(n) for n in _NUMERALS) >= 2:
            segs = NUMERAL_SPLIT_RE.split(text)
            # segs = [前缀, 序号, 体, 序号, 体, …]——重组为 序号+体 条目
            items = [segs[k] + segs[k + 1] for k in range(1, len(segs) - 1, 2)]
            if items:
                parts = items
        for p in parts:
            p = p.strip(" ；;。").rstrip("/").strip()
            if len(p) >= 8:  # 碎渣（「随注）。」族）不收
                out.append((p, "pending"))
        i = j
    return out


def _classify(text: str, default: str | None = None) -> str | None:
    """活账子句定级：approx（近似族活子句）/ pending（其余活子句）；全核销/空账 → default."""
    if not MARK_RE.search(text) and not APPROX_RE.search(text):
        return default
    if re.match(r"^无[（(。；;]", text.strip()):  # 「待实测：无（…）」显式空账
        return None
    live = [c for c in CLAUSE_SPLIT.split(text)
            if (MARK_RE.search(c) or APPROX_RE.search(c)) and not RESOLVED_RE.search(c)]
    if not live:
        return None
    if any(APPROX_RE.search(c) for c in live):
        return "approx"
    return "pending"


def _norm(text: str) -> str:
    return re.sub(r"[\s，。；：、「」（）()【】]", "", text)


def _dedup(cands: list[dict]) -> list[dict]:
    """规范化文本互相包含的去重（留长者——注释行常与 notes 条目互为子集）."""
    kept: list[dict] = []
    for c in sorted(cands, key=lambda x: -len(x["text"])):
        n = _norm(c["text"])
        if any(n in _norm(k["text"]) or _norm(k["text"]) in n for k in kept):
            continue
        kept.append(c)
    return kept


def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


#: 机提块标记（幂等重跑：含此标记的 caveats 块=本脚本产物——重跑时剥掉重提；
#: 无标记的 caveats 键=人工策展件，整文件跳过不机械合并）
_MACHINE_MARK = "# 挂账语义机读键（决策卡 #24——scripts/extract_caveats.py 批量提取，"


def _strip_machine_block(raw: str) -> str:
    """剥掉文件末尾的机提块（标记注释行起到 EOF；机提块恒为文件末块）."""
    lines = raw.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(_MACHINE_MARK):
            # 块头前一行是分隔空行（本脚本写入形态），一并剥掉
            start = i - 1 if i > 0 and not lines[i - 1].strip() else i
            return "\n".join(lines[:start]) + "\n"
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（缺省 dry-run）")
    args = ap.parse_args()
    files = sorted(
        glob.glob(str(ROOT / "data/library/characters/*.yaml"))
        + glob.glob(str(ROOT / "data/library/light_cones/*.yaml"))
        + glob.glob(str(ROOT / "data/library/relics/*.yaml")))
    report = {"hand_curated": [], "extracted": {}, "skipped_resolved": {},
              "marked_but_not_extracted": [], "no_marks": 0}
    for f in files:
        raw = Path(f).read_text(encoding="utf-8")
        rel = str(Path(f).relative_to(ROOT))
        if _MACHINE_MARK in raw:
            raw = _strip_machine_block(raw)  # 幂等：剥掉旧机提块重提（人工段不动）
            if args.apply:
                Path(f).write_text(raw, encoding="utf-8")
        try:
            doc = yaml.safe_load(raw)
        except yaml.YAMLError as e:
            report["marked_but_not_extracted"].append({"file": rel, "reason": f"YAML 解析失败 {e}"})
            continue
        if not isinstance(doc, dict):
            report["no_marks"] += 1
            continue
        if doc.get("caveats") is not None:
            report["hand_curated"].append(rel)
            continue
        cands: list[dict] = []
        skipped: list[str] = []
        for text, default in [(t.strip(), None) for t in _notes_entries(doc)] + _comment_entries(raw):
            level = _classify(text, default)
            if level is None:
                if MARK_RE.search(text) or APPROX_RE.search(text):
                    skipped.append(text[:60])
                continue
            cands.append({"text": text, "level": level})
        cands = _dedup(cands)
        if cands:
            report["extracted"][rel] = cands
        else:
            has_marks = bool(MARK_RE.search(raw) or APPROX_RE.search(raw))
            if has_marks:
                report["marked_but_not_extracted"].append(
                    {"file": rel, "reason": "标记注全属已核销/显式空账/非机读形态（内联碎注/头注枚举）",
                     "skipped_samples": skipped[:3]})
            else:
                report["no_marks"] += 1
        if cands and args.apply:
            block = ["", _MACHINE_MARK,
                     "# 源=本文件 notes 机读注块与 `# 待实测：`/`# 待收…：`/`# 挂账…：` 注释行；原文不动，判级口径见脚本头注）",
                     "caveats:"]
            for c in cands:
                block.append(f"  - text: {_yaml_str(c['text'])}")
                block.append(f"    level: {c['level']}")
            with open(f, "a", encoding="utf-8") as fh:
                fh.write("\n".join(block) + "\n")
            # 写后自检：重解析确认 YAML 合法且 caveats 落上（坏一个文件=编译期全链炸，不许静默）
            chk = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
            assert isinstance(chk, dict) and len(chk.get("caveats") or ()) == len(cands), \
                f"{rel} 写入后自检失败（caveats {len(chk.get('caveats') or ())} != {len(cands)}）"
    n_ext = sum(len(v) for v in report["extracted"].values())
    print(f"人工策展（整文件跳过）: {len(report['hand_curated'])}")
    print(f"提取文件: {len(report['extracted'])}，条目: {n_ext}")
    print(f"有标记但未提取: {len(report['marked_but_not_extracted'])}")
    print(f"无标记: {report['no_marks']}")
    out = ROOT / "reports" / "caveats_extraction.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
