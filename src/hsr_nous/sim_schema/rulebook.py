"""Rulebook 加载器：全局规则数据（sim_schema 第三类输入，与 build/stage 平行）.

承载 `rulebook.yaml`——伤害公式族 / 乘区表达式 / 伤害类别路由 / 常量 / 属性击破效果表。
能用白名单表达式写出来的数值全部进本簿，引擎代码零数值常数。

绑定期一次性 `parse(..., layer="formula")` 白名单预编译（B8），进程内缓存；
热循环只带 context `evaluate` 求值。与 `docs/01_formula.md` 的文档镜像一致由
`tests/test_doc_lint.py` 镜像闸保证。
"""
from __future__ import annotations

import ast
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from hsr_nous.sim_schema.expression import PreparedExpression, parse

__all__ = ["RULEBOOK_PATH", "Rulebook", "get_rulebook"]

RULEBOOK_PATH = Path(__file__).with_name("rulebook.yaml")


def _expression_idents(tree: ast.AST) -> List[str]:
    """表达式引用的变量标识符（**AST 求值序**——确定性冻结规则）.

    按求值器递归消费子节点的顺序深度优先遍历（BinOp 先左后右、IfExp 先 test 后
    body/orelse、Call 位置参数左到右再关键字参数、BoolOp/Compare 按操作数序……
    与 `expression.evaluate` 的递归序一致；由括号/优先级决定，**不是**源码书写
    位序），同名首见去重；白名单调用函数名不是数据槽，排除。

    通用 settle 按本表序逐个给公式引用的乘区/绑定取值——多 random() 区场景的
    随机流消耗序由此逐比特钉死（回归见 tests/test_rulebook.py）。
    """
    out: List[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            if node.id not in out:
                out.append(node.id)
            return
        if isinstance(node, ast.Call):
            # 函数名不是数据槽（func 不递归）；参数按求值序
            for arg in node.args:
                visit(arg)
            for kw in node.keywords:
                visit(kw.value)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return out


@dataclass(frozen=True)
class Rulebook:
    """预编译好的全局规则簿（不可变；一切表达式已过白名单静态校验）."""

    constants: Mapping[str, float]                     # 引擎侧解析/兜底用数据常数
    route: Mapping[str, Mapping[str, Any]]             # 伤害类别 → {模式 → 公式键，settle → 类别结算规格}
    zones: Mapping[str, PreparedExpression]            # 乘区表达式（预编译；map 形态条目取 expression 键）
    formulas: Mapping[str, PreparedExpression]         # 顶层公式（预编译）
    break_effects: Mapping[str, Mapping[str, Any]]     # 属性击破效果表
    taunt: Mapping[str, Mapping[str, Any]]             # 嘲讽值表（path_base / memosprite_base）
    modes: Mapping[str, Mapping[str, Any]]             # 玩法模式表（stage mode → Cycle 配置）
    energy: Mapping[str, float]                        # 行动默认回能表（action_type → 能量，mechanics 05 §5.1）
    relic_affixes: Mapping[str, Mapping[str, float]]   # 遗器词条数值表（main/sub → DSL 词条 id → 值，06_relics §6）
    zone_decls: Mapping[str, Mapping[str, Any]]        # 乘区取值声明（map 形态 zones 条目除 expression 外全量；通用 settle 消费）
    formula_idents: Mapping[str, List[str]]            # 公式键 → 引用的变量标识符（**AST 求值序**——确定性冻结规则，绑定期预解析；通用 settle 按表序逐个取值，多 random() 区随机流消耗序由此钉死）
    settle_gates: Mapping[str, PreparedExpression]     # 伤害类别 → 前置跳过闸表达式（预编译；route.<类别>.settle.gate.if）


@functools.lru_cache(maxsize=None)
def get_rulebook(path: Optional[Path] = None) -> Rulebook:
    """加载并预编译 rulebook（进程内缓存；非法表达式加载期即炸）.

    path 缺省 RULEBOOK_PATH；缓存键带路径——测试注入临时 rulebook 与默认单例互不污染。
    """
    p = RULEBOOK_PATH if path is None else Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    # zones 两态：纯字符串 = 仅表达式（legacy 形态）；
    # map = expression + 乘区取值声明（node/inputs/scoped/by_type…——声明进 zone_decls）
    zones: Dict[str, PreparedExpression] = {}
    zone_decls: Dict[str, Mapping[str, Any]] = {}
    for k, v in raw["zones"].items():
        if isinstance(v, str):
            zones[k] = parse(v, layer="formula")
        else:
            zones[k] = parse(str(v["expression"]), layer="formula")
            zone_decls[k] = {kk: vv for kk, vv in v.items() if kk != "expression"}
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
        zone_decls=zone_decls,
        formula_idents={k: _expression_idents(prepared.tree) for k, prepared in formulas.items()},
        settle_gates={
            cat: parse(str(spec["settle"]["gate"]["if"]), layer="formula")
            for cat, spec in raw["route"].items()
            if isinstance(spec.get("settle"), dict) and spec["settle"].get("gate")
        },
    )
