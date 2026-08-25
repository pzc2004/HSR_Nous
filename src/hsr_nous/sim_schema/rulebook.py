"""Rulebook 加载器：全局规则数据（sim_schema 第三类输入，与 build/stage 平行）.

承载 `rulebook.yaml`——伤害公式族 / 乘区表达式 / 伤害类别路由 / 常量 / 属性击破效果表。
决策卡 A1：能用白名单表达式写出来的数值全部进本簿，引擎代码零数值常数。

绑定期一次性 `parse(..., layer="formula")` 白名单预编译（B8），进程内缓存；
热循环只带 context `evaluate` 求值。与 `docs/01_formula.md` 的文档镜像一致由
`tests/test_doc_lint.py` 镜像闸保证。
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from hsr_nous.sim_schema.expression import PreparedExpression, parse

__all__ = ["RULEBOOK_PATH", "Rulebook", "get_rulebook"]

RULEBOOK_PATH = Path(__file__).with_name("rulebook.yaml")


@dataclass(frozen=True)
class Rulebook:
    """预编译好的全局规则簿（不可变；一切表达式已过白名单静态校验）."""

    constants: Mapping[str, float]                     # 引擎侧解析/兜底用数据常数
    route: Mapping[str, Mapping[str, str]]             # 伤害类别 → {模式 → 公式键}
    zones: Mapping[str, PreparedExpression]            # 乘区表达式（预编译）
    formulas: Mapping[str, PreparedExpression]         # 顶层公式（预编译）
    break_effects: Mapping[str, Mapping[str, Any]]     # 属性击破效果表
    taunt: Mapping[str, Mapping[str, Any]]             # 嘲讽值表（path_base / memosprite_base）
    modes: Mapping[str, Mapping[str, Any]]             # 玩法模式表（stage mode → Cycle 配置）
    energy: Mapping[str, float]                        # 行动默认回能表（action_type → 能量，mechanics 05 §5.1）
    relic_affixes: Mapping[str, Mapping[str, float]]   # 遗器词条数值表（main/sub → DSL 词条 id → 值，06_relics §6）


@functools.lru_cache(maxsize=None)
def get_rulebook(path: Optional[Path] = None) -> Rulebook:
    """加载并预编译 rulebook（进程内缓存；非法表达式加载期即炸）.

    path 缺省 RULEBOOK_PATH；缓存键带路径——测试注入临时 rulebook 与默认单例互不污染。
    """
    p = RULEBOOK_PATH if path is None else Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    zones: Dict[str, PreparedExpression] = {
        k: parse(str(v), layer="formula") for k, v in raw["zones"].items()
    }
    formulas: Dict[str, PreparedExpression] = {
        k: parse(str(v["expression"]), layer="formula") for k, v in raw["formulas"].items()
    }
    return Rulebook(
        constants=raw.get("constants", {}),
        route=raw["route"],
        zones=zones,
        formulas=formulas,
        break_effects=raw.get("break_effects", {}),
        taunt=raw.get("taunt", {}),
        modes=raw.get("modes", {}),
        energy=raw.get("energy", {}),
        relic_affixes=raw.get("relic_affixes", {}),
    )
