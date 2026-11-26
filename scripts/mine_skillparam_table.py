#!/usr/bin/env python3
"""一次性批处理：全语料挖矿「SkillParam 哈希 → (TriggerKey, Index)」静态反查表（tracked 生成物）.

背景（B48/#545）：上游 PostfixExpr 的动态值引用按 .NET 字符串哈希寻址
（sim_schema/config_ai.dynamic_value_hash）。SkillParam 哈希在 ConfigCharacter 的
DynamicValues.Floats 里以 ReadInfo.Type=SkillParam + TriggerKey + Index 声明，但
adapters 只读加载 Config 自身 Floats——跨变体声明的哈希（共享 Ability 引用了只在
特定变体 Config 声明的技能参数槽）被报"未知 DynamicHash"。

挖矿口径（数据形态核证，不猜）：
- 键名来源 = 全语料 ConfigCharacter 的 DynamicValues.Floats 中 ReadInfo.Type=SkillParam
  的条目；哈希 → (TriggerKey, Index) 槽位映射；
- 同一哈希映射到不同 (TriggerKey, Index) → 该哈希整桶丢弃（不可猜）；
- 值不在此表：解析时由 adapters 用加载 Config 自身 skills[TriggerKey].param_list[Index]
  取值（不拉外变体技能行，区别于 #537 SkillList 并集翻车）；技能缺失/槽越界仍显式拒绝。

用法：.venv/bin/python scripts/mine_skillparam_table.py（直接重写
src/hsr_nous/pipeline/enemies/skillparam_hash_table.py；tbgd 更新后重跑本脚本）
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TARGET = ROOT / "src/hsr_nous/pipeline/enemies/skillparam_hash_table.py"


def mine(tbgd_dir: Path) -> dict[int, tuple[str, int]]:
    decl: dict[int, set] = defaultdict(set)
    files = 0
    base = tbgd_dir / "Config" / "ConfigCharacter"
    assert base.is_dir(), f"扫描域缺失：{base}（tbgd 目录结构变更？）"
    for path in sorted(base.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        files += 1
        floats = (data.get("DynamicValues") or {}).get("Floats") or {}
        for raw_hash, item in floats.items():
            info = (item or {}).get("ReadInfo") or {}
            if info.get("Type") != "SkillParam":
                continue
            trigger = str(info.get("TriggerKey") or "")
            slot = info.get("Index")
            if not trigger or not isinstance(slot, int):
                continue
            try:
                decl[int(raw_hash)].add((trigger, slot))
            except (TypeError, ValueError):
                continue
    table: dict[int, tuple[str, int]] = {}
    collisions = 0
    for hashed, slots in decl.items():
        if len(slots) != 1:
            collisions += 1
            continue
        table[hashed] = next(iter(slots))
    print(f"扫描文件 {files} | SkillParam 哈希 {len(decl)} | 冲突桶丢弃 {collisions} "
          f"| 入表 {len(table)}", file=sys.stderr)
    return table


def main() -> int:
    tbgd_dir = ROOT / "data/turnbasedgamedata"
    table = mine(tbgd_dir)
    lines = [
        '"""SkillParam 哈希反查表（GENERATED——scripts/mine_skillparam_table.py 产出，勿手改）.',
        '',
        "上游 PostfixExpr 动态值引用按 .NET 字符串哈希寻址；本表是全语料 ConfigCharacter",
        "DynamicValues.Floats 中 ReadInfo.Type=SkillParam 声明的「哈希 → (TriggerKey, Index)」",
        "静态反查镜像（同一哈希映射不同槽位的冲突桶除外，口径见生成脚本 docstring）。",
        "消费方：adapters（enemy_ability._character_symbols 跨变体铺底层）；解析时值取加载",
        "Config 自身 skills[TriggerKey].param_list[Index]，技能缺失/槽越界仍显式拒绝——",
        "本表只供槽位映射，不拉外变体技能行（区别于 SkillList 继承并集）。",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Dict, Tuple",
        "",
        "#: 反查表唯一事实源（生成物——tbgd 更新后重跑 scripts/mine_skillparam_table.py）",
        "SKILLPARAM_HASH_TABLE: Dict[int, Tuple[str, int]] = {",
    ]
    for hashed in sorted(table):
        trigger, slot = table[hashed]
        lines.append(f"    {hashed}: ({trigger!r}, {slot}),")
    lines += [
        "}",
        "",
        "",
        "def lookup_skillparam_slot(hashed: int):",
        '    """反查 (TriggerKey, Index) 槽位；未收录/冲突桶丢弃的哈希返回 None."""',
        "    return SKILLPARAM_HASH_TABLE.get(hashed)",
        "",
    ]
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {TARGET.relative_to(ROOT)}（{len(table)} 哈希）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
