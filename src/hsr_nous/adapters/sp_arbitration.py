"""战技点耗产模板补丁器：客户端复核值 → 模板 YAML 行级改写.

数据源：`data/tbgd_skill_data.json`（extract_tbgd_skills 产出，sp_cost/sp_gain 全技能
覆盖，与模板全库对拍 358/358 零不符——2026-09-05 定案：战技点耗产以此为准，
类型默认（普攻 耗0/产1、战技 耗1/产0）仅作缺项兜底）。

补丁器纪律：行级改写，只动 skill_point_cost/skill_point_gain 两行——
模板 YAML 有丰富注释与 LLM 标注层，整体 dump 重写会全丢。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: 类型默认 (cost, gain)——tbgd 缺项时的兜底（如未来新增派生技能组）
_TYPE_DEFAULT: dict[str, tuple[int, int]] = {
    "basic": (0, 1),
    "skill": (1, 0),
}

_tbgd_cache: dict[str, dict] | None = None


def _tbgd(data_dir: str = "data") -> dict[str, dict]:
    global _tbgd_cache
    if _tbgd_cache is None:
        p = Path(data_dir) / "tbgd_skill_data.json"
        _tbgd_cache = json.loads(p.read_text(encoding="utf-8"))["skills"] if p.exists() else {}
    return _tbgd_cache


def resolve(action_id: str, action_type: str, *, data_dir: str = "data") -> tuple[int, int]:
    """取值：tbgd 复核值优先，缺项回落类型默认。返回 (cost, gain)."""
    t = _tbgd(data_dir).get(action_id)
    if t is not None:
        return t["sp_cost"], t["sp_gain"]
    return _TYPE_DEFAULT.get(action_type, (0, 0))


_ACTION_ID_RE = re.compile(r"^(\s*)- action_id: '?(\d+)'?\s*$")
_KEY_RE = re.compile(r"^(\s+)(skill_point_cost|skill_point_gain):\s*(-?\d+)(.*)$")


def patch_file(path: Path, *, dry_run: bool = False, data_dir: str = "data") -> list[str]:
    """行级补丁：只改 skill_point_cost/gain 值与注释；缺的非零行补插到 action_type 后。
    返回变更描述（人审用），dry_run 不落盘。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[dict] = []
    cur: dict | None = None
    for idx, line in enumerate(lines):
        if m := _ACTION_ID_RE.match(line):
            if cur:
                cur["end"] = idx
                blocks.append(cur)
            cur = {"start": idx, "action_id": m.group(2), "action_type": None, "keys": {}}
            continue
        if cur is None:
            continue
        if m := re.match(r"^\s+action_type: (\w+)", line):
            cur["action_type"] = m.group(1)
        elif m := _KEY_RE.match(line):
            indent, key, val, tail = m.groups()
            cur["keys"][key] = (idx, indent, int(val), tail)
    if cur:
        cur["end"] = len(lines)
        blocks.append(cur)

    changes: list[str] = []
    for b in reversed(blocks):  # 从后往前改，行号不失效
        aid, atype = b["action_id"], b["action_type"] or ""
        cost, gain = resolve(aid, atype, data_dir=data_dir)
        for key, target in (("skill_point_cost", cost), ("skill_point_gain", gain)):
            hit = b["keys"].get(key)
            if hit:
                idx, indent, old, tail = hit
                if old != target:
                    lines[idx] = f"{indent}{key}: {target}    # 战技点数值复核"
                    changes.append(f"  {aid} {key}: {old} → {target}")
            elif target != 0:
                insert_at = b["start"] + 1
                for j in range(b["start"] + 1, b["end"]):
                    if re.match(r"^\s+action_type:", lines[j]):
                        insert_at = j + 1
                        break
                lines.insert(insert_at, f"  {key}: {target}    # 战技点数值复核")
                changes.append(f"  {aid} +{key}: {target}")
    changes.reverse()
    if changes and not dry_run:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description="战技点耗产模板补丁器（客户端复核值 → 模板）")
    ap.add_argument("--templates", default="data/sim_templates/characters",
                    help="模板目录（默认 data/sim_templates/characters）")
    ap.add_argument("--data-dir", default="data", help="数据目录（默认 data）")
    ap.add_argument("--dry-run", action="store_true", help="只打印不落盘")
    args = ap.parse_args()

    total = 0
    for f in sorted(Path(args.templates).glob("*.yaml")):
        changes = patch_file(f, dry_run=args.dry_run, data_dir=args.data_dir)
        if changes:
            print(f"{f.name}: {len(changes)} 处")
            for c in changes:
                print(c)
            total += len(changes)
    print(f"\n共 {total} 处{'（dry-run 未落盘）' if args.dry_run else '已落盘'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
