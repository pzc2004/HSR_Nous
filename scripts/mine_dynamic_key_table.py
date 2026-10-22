#!/usr/bin/env python3
"""一次性批处理：全语料挖矿「动态键哈希 → 键名」静态反查表（tracked 生成物）.

背景（审计显形）：上游 PostfixExpr 的动态值引用按 .NET 字符串哈希寻址
（sim_schema/config_ai.dynamic_value_hash），编译器本只能解析本敌已见键名——
全局键/跨文件键哈希解不开名 → `dynamic_of` 活读出不来，落"未知 DynamicHash"拒因。

挖矿口径（数据形态核证，不猜）：
- 键名来源 = 全语料**写入节点**的目标键字段（Set/Define 族的 DynamicKey/Key/
  ToDynamicKey）——只有被写入的键才有运行时读语义（四层读链 ②已提交态）；
- 排除 `MDF_*`/`Modifier_*` 内联参数命名族：该族是 AddModifier 任务内联参数表
  的跨语境读取（参数随施加任务携带），读点落在 modifier 定义编译语境时解析成
  runtime 动态值会得到缺省 0——静默错值，比显式未知更坏（保持未知真拒因）；
- 两名撞同一哈希 → 该哈希整桶丢弃（不可猜）；含引号/反斜杠的名不入表达式槽；
- 扫描域：Config/ConfigAbility/Monster + Config/ConfigGlobalModifier + ConfigAI
  （GlobalModifier/ConfigAI 是全局键的主要寄生地——OneMorePerTurn 族在案）。

已知不可回收（数据证据，勿再尝试）：GlobalModifier OneMorePerTurn 的 OnCreate
读哈希 1227332892 ≠ 语料任意键名哈希（其自槽 ReadInfo Type=None 无名字段）——
哈希不可逆，无名可反查，保持未知。

用法：.venv/bin/python scripts/mine_dynamic_key_table.py（直接重写
src/hsr_nous/pipeline/enemies/dynamic_key_table.py；tbgd 更新后重跑本脚本）
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hsr_nous.sim_schema.config_ai import dynamic_value_hash  # noqa: E402

SCAN_SUBDIRS = ("ConfigAbility/Monster", "ConfigGlobalModifier", "ConfigAI")
WRITE_PREFIXES = ("SetDynamicValue", "DefineDynamicValue")
WRITE_FIELDS = ("DynamicKey", "Key", "ToDynamicKey")
INLINE_PARAM_PREFIXES = ("MDF_", "Modifier_")
TARGET = ROOT / "src/hsr_nous/pipeline/enemies/dynamic_key_table.py"


def mine(tbgd_dir: Path) -> tuple[dict[int, str], Counter]:
    names: Counter = Counter()
    files = 0
    for sub in SCAN_SUBDIRS:
        base = tbgd_dir / "Config" / sub
        assert base.is_dir(), f"扫描域缺失：{base}（tbgd 目录结构变更？）"
        for path in sorted(base.rglob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            files += 1
            walk(data, names)
    # 冲突整桶丢弃 + 内联参数族排除 + 表达式不安全名排除
    by_hash: dict[int, str] = {}
    collisions: set[int] = set()
    for name in names:
        if name.startswith(INLINE_PARAM_PREFIXES) or any(c in name for c in "'\"\\"):
            continue
        hashed = dynamic_value_hash(name)
        if hashed in by_hash and by_hash[hashed] != name:
            collisions.add(hashed)
            continue
        by_hash[hashed] = name
    for hashed in collisions:
        by_hash.pop(hashed, None)
    print(f"扫描文件 {files} | 写入键名 {len(names)} | 冲突桶丢弃 {len(collisions)} "
          f"| 入表 {len(by_hash)}", file=sys.stderr)
    return by_hash, names


def walk(value: object, names: Counter) -> None:
    if isinstance(value, dict):
        node_type = str(value.get("$type") or "").rsplit(".", 1)[-1]
        if node_type.startswith(WRITE_PREFIXES):
            for field in WRITE_FIELDS:
                raw = value.get(field)
                candidate = raw.get("Value") if isinstance(raw, dict) else raw
                if candidate is not None and str(candidate):
                    names[str(candidate)] += 1
        for child in value.values():
            walk(child, names)
    elif isinstance(value, list):
        for child in value:
            walk(child, names)


def main() -> int:
    tbgd_dir = ROOT / "data/turnbasedgamedata"
    table, _ = mine(tbgd_dir)
    lines = [
        '"""动态键哈希反查表（GENERATED——scripts/mine_dynamic_key_table.py 产出，勿手改）.',
        '',
        "上游 PostfixExpr 动态值引用按 .NET 字符串哈希寻址；本表是全语料挖矿的",
        "「哈希 → 键名」静态反查镜像（写入键才入表——只有被写入的键有运行时读语义；",
        "MDF_*/Modifier_* 内联参数族与哈希冲突桶除外，口径见生成脚本 docstring）。",
        "消费方：adapters（enemy_ability 的 dynamic_name_symbols 最低优先级回落层）；",
        "解析后的读仍走 config_ai_dynamic_value 四层读链（帧覆盖层语义不变）。注意：入表",
        "只证明「语料中有写入方」——具体敌人运行时能否读到值取决于该敌的写入回调是否",
        "被编译执行，读不到按四层链缺省层回落（AIFlag/AICounter 族 1、其余 0），非本表职责。",
        '"""',
        "from __future__ import annotations",
        "",
        "from typing import Dict, Optional",
        "",
        "#: 反查表唯一事实源（生成物——tbgd 更新后重跑 scripts/mine_dynamic_key_table.py）",
        "DYNAMIC_KEY_HASH_TABLE: Dict[int, str] = {",
    ]
    for hashed in sorted(table):
        lines.append(f"    {hashed}: {table[hashed]!r},")
    lines += [
        "}",
        "",
        "",
        "def lookup_dynamic_key_name(hashed: int) -> Optional[str]:",
        '    """反查键名；未收录/冲突桶丢弃的哈希返回 None（调用方保持显式未知拒因）."""',
        "    return DYNAMIC_KEY_HASH_TABLE.get(hashed)",
        "",
    ]
    TARGET.write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {TARGET.relative_to(ROOT)}（{len(table)} 键）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
