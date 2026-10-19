"""受限表达式 DSL 求值器.

基于 Python ast 的白名单表达式引擎，用于 DSL 模板中的
`amount` / `condition` / `target_filter` / 全局公式等字符串表达式。

设计来源：
- `sim_schema/docs/22_syntax_reference.md`（语法：C 三元、`&&`/`||`/`!`、命名空间）
- `sim_schema/docs/13_validator.md`（变量/函数白名单）

用法::

    from hsr_nous.sim_schema.expression import parse, evaluate

    prepared = parse("$self.max_hp * 0.3 + 200")
    result = evaluate(prepared, context={"self": {"max_hp": 6000}})
    result.value          # 2000.0
    result.trace          # 节点值树（供乘区拆解 UI）

模板绑定时对同一表达式只应 `parse` 一次（白名单校验在此完成），
战斗热循环中重复 `evaluate` 传入不同 context。
"""

from __future__ import annotations

import ast
import random as _random_mod
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from hsr_nous.sim_schema.action import DOT_KIND_ELEMENTS, ELEMENTS

__all__ = ["ExpressionError", "PreparedExpression", "EvalOutcome", "parse", "evaluate"]


class ExpressionError(ValueError):
    """表达式非法：语法错误 / 未知命名空间 / 非白名单节点或函数 / 未定义变量 / 求值失败."""


# ---------------------------------------------------------------------------
# 预处理：C 三元、布尔运算符、命名空间
# ---------------------------------------------------------------------------

_NS_PATTERN = re.compile(r"\$(self|resource|event|target|build|prev|last|team|it|modifier|mod|snapshot)\b")


def _convert_ternary(expr: str) -> str:
    """把 `cond ? a : b`（含嵌套）改写为 Python `(a if cond else b)`.

    按顶层括号深度切分，左右分支递归处理；找不到配对的 `?`/`:` 时报错。
    """

    def split_top(s: str) -> Optional[Tuple[str, str, str]]:
        depth = 0
        q_pos = -1
        for i, ch in enumerate(s):
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "?" and depth == 0:
                if q_pos >= 0:
                    raise ExpressionError(f"同一层级出现多个 '?'：{s!r}")
                q_pos = i
            elif ch == ":" and depth == 0 and q_pos >= 0:
                cond = s[:q_pos].strip()
                a = s[q_pos + 1 : i].strip()
                b = s[i + 1 :].strip()
                if not cond or not a or not b:
                    raise ExpressionError(f"三元表达式缺少分支：{s!r}")
                return cond, a, b
        return None

    def convert(s: str) -> str:
        # 先递归处理括号内部的嵌套三元
        out: List[str] = []
        i = 0
        while i < len(s):
            if s[i] in "([":
                close = ")" if s[i] == "(" else "]"
                depth, j = 0, i
                while True:
                    if s[j] == s[i]:
                        depth += 1
                    elif s[j] == close:
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                out.append(s[i] + convert(s[i + 1 : j]) + close)
                i = j + 1
            else:
                out.append(s[i])
                i += 1
        s = "".join(out)
        parts = split_top(s)
        if parts is None:
            if "?" in s:
                raise ExpressionError(f"三元表达式不完整（缺 ':'）：{s!r}")
            return s
        cond, a, b = parts
        return f"(({convert(a)}) if ({convert(cond)}) else ({convert(b)}))"

    if "?" in expr:
        return convert(expr)
    return expr


def _preprocess(expr: str) -> str:
    """DSL 语法 → Python 语法：C 三元 → `&&`/`||`/`!` → 命名空间去 `$` → 保留字改写.

    字符串字面量保护（审查实测的静默改名）：全部变换只作用于非字符串段——
    先把字面量mask成占位符，变换结束后还原。否则 `has_modifier("a && b")` 的
    参数会被改成 "a and b"、`"x!y"` → "x not y"、`"def"` → "defense"、
    `"if only"` 被 if/else 检查误杀。
    """
    masked, literals = _mask_strings(expr)
    if re.search(r"\b(if|else)\b", masked):
        raise ExpressionError(
            f"不支持 Python 风格三元 / if-else 关键字：{expr!r}（请用 C 风格 `cond ? a : b`）"
        )
    s = _convert_ternary(masked.strip())
    s = s.replace("&&", " and ").replace("||", " or ")
    s = re.sub(r"!(?!=)", " not ", s)
    s = _NS_PATTERN.sub(lambda m: m.group(1), s)
    if "$" in s:
        raise ExpressionError(f"未知命名空间引用：{expr!r}")
    # Python 保留字作标识符：属性访问 `.def` → `["def"]`；裸 `def` → `defense`（统一 dict key）
    s = re.sub(r"\.(def|global|pass|class|import|lambda|del|raise|yield)\b",
               lambda m: f"[{m.group(1)!r}]", s)
    s = re.sub(r"\bdef\b", "defense", s)
    # 公式允许折行书写（expression: | 块标量）——ast eval 只收单行，先压平
    # strip 兜底：`!`→` not ` 在表达式首位会留下前导空格（曾致 "unexpected indent"）
    s = " ".join(s.splitlines()).strip()
    return _unmask_strings(s, literals)


def _mask_strings(expr: str) -> Tuple[str, List[str]]:
    """引号字符串 → 占位符（\\x01N\\x02）：预处理变换只作用于非字符串段."""
    out: List[str] = []
    literals: List[str] = []
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch in "'\"":
            j = i + 1
            while j < len(expr):
                if expr[j] == "\\":
                    j += 2
                    continue
                if expr[j] == ch:
                    break
                j += 1
            if j >= len(expr):
                raise ExpressionError(f"字符串引号未闭合：{expr!r}")
            literals.append(expr[i : j + 1])
            out.append(f"\x01{len(literals) - 1}\x02")
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out), literals


def _unmask_strings(expr: str, literals: List[str]) -> str:
    for idx, lit in enumerate(literals):
        expr = expr.replace(f"\x01{idx}\x02", lit)
    return expr


# ---------------------------------------------------------------------------
# 白名单定义
# ---------------------------------------------------------------------------

#: effect 表达式允许的函数（**函数白名单唯一事实来源**；
#: 13_validator §13.5.2 + 22_syntax_reference §22.4/§22.10 为镜像复述，
#: 一致由 tests/test_doc_lint.py 词表闸保证——改白名单只改这里）
EFFECT_FUNCTIONS = frozenset(
    {"min", "max", "abs", "round", "clamp", "sum", "chance", "in_zone", "stacks", "sum_stacks",
     "enemies_alive", "has_modifier", "count", "count_modifier", "unique_sources", "mechanic_chance",
     "actor_type_of", "hp_of", "max_hp_of", "resource_of", "dynamic_of", "count_team", "stat_of",
     "base_stat_of", "controlled", "path_of", "has_summon", "in_group", "element_of", "who_has",
     "elation_of",
     "broken_of", "has_debuff", "debuff_count", "dot_count", "actor_alive",
     "weakness_count", "has_stat_penalty", "has_shield", "shielded_count",
     "damageable_enemies", "dot_value", "is_adjacent",
     "has_weakness", "dot_kind", "summoner_of"}
)

#: 全局公式层额外允许（13_validator §13.5.3 / 22_syntax_reference §22.10 镜像复述）
FORMULA_FUNCTIONS = EFFECT_FUNCTIONS | {"random", "lookup_table"}

_LAYERS = {"effect": EFFECT_FUNCTIONS, "formula": FORMULA_FUNCTIONS}

#: 函数字面量参词表闸（编译期，2026-10-12）：func → (位置参序号, 词表)——该位置参为
#: 字符串字面量时必须落在词表内（小写归一后比对，错拼编译期炸）；动态表达式参
#: （element_of(...) 族）静态不可判放行，运行期宿主侧口径见 22_syntax_reference §22.4
#: 各函数行。词表唯一源 sim_schema/action.py（ELEMENTS / DOT_KIND_ELEMENTS）
_FUNC_LITERAL_ARG_VOCAB = {
    "has_weakness": (1, ELEMENTS),
    "dot_kind": (1, frozenset(DOT_KIND_ELEMENTS)),
}

# ---------------------------------------------------------------------------
# 运算符实现表（白名单与求值共用唯一事实来源——放行集构造上=实现集子集：
# 未实现运算符 parse 期即炸，不再漏到 evaluate 才报"非法运算符"。曾收
# ast.operator/ast.cmpop 基类，位运算/is 等无实现运算符过 parse 进求值才炸，
# 2026-10-12 收紧）
# ---------------------------------------------------------------------------

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}

_CMP_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    # 成员判定（2026-09-23——列表命名空间随命中域字段落地：target_control_kinds 族；
    # 左操作数标量、右操作数 list/tuple）
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

#: 一元/布尔运算符实现集（与 evaluate 的 USub/UAdd/Not、And/Or 分支一一对应——
#: 分支无表可引，在此点名；Invert(~) 无实现故不在列，改分支同步改本集）
_UNARY_OPS = (ast.USub, ast.UAdd, ast.Not)
_BOOL_OPS = (ast.And, ast.Or)

#: 允许的 AST 节点类型（其余一律拒绝：无语句、无循环、无推导式、无 f-string、无 lambda）。
#: 运算符只收实现表/实现集点名的具体类——`& | ^ << >> @`、`~`、`is/is not` 等
#: 无实现运算符在 parse 期被拒（实现集见上方三张表）
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.Subscript,
    ast.List,
    ast.Tuple,
    *_BIN_OPS,          # + - * / // % **（实现表键即白名单）
    *_CMP_OPS,          # == != < <= > >= in not in（同）
    *_UNARY_OPS,        # - + not
    *_BOOL_OPS,         # and or
    ast.Load,           # expr_context 在 eval 模式的唯一形态
    ast.keyword,        # 调用中的关键字参数
)


@dataclass(frozen=True)
class PreparedExpression:
    """parse 后的产物：可直接重复 evaluate，可缓存."""

    source: str
    tree: ast.AST = field(compare=False)


@dataclass
class EvalOutcome:
    """求值结果：value + 每个 AST 节点的中间值（trace 树）."""

    value: Any
    trace: Dict[str, Any]


def parse(source: str, layer: str = "effect") -> PreparedExpression:
    """解析并做白名单静态校验。layer: "effect" | "formula"."""
    if layer not in _LAYERS:
        raise ExpressionError(f"未知 layer: {layer!r}")
    py_src = _preprocess(source)
    try:
        tree = ast.parse(py_src, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"表达式语法错误：{source!r}（{e.msg}）") from e

    allowed_funcs = _LAYERS[layer]
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"非法语法结构 {type(node).__name__}：{source!r}（表达式只支持算术/比较/布尔/三元/白名单函数调用）"
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExpressionError(f"禁止访问内部属性 {node.attr!r}：{source!r}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ExpressionError(f"只允许调用白名单函数（禁止方法调用/间接调用）：{source!r}")
            if node.func.id not in allowed_funcs:
                raise ExpressionError(
                    f"函数 {node.func.id!r} 不在 {layer} 层白名单（{sorted(allowed_funcs)}）：{source!r}"
                )
            vocab_spec = _FUNC_LITERAL_ARG_VOCAB.get(node.func.id)
            if vocab_spec is not None:
                arg_idx, vocab = vocab_spec
                if len(node.args) > arg_idx:
                    arg = node.args[arg_idx]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                            and arg.value.lower() not in vocab:
                        raise ExpressionError(
                            f"函数 {node.func.id!r} 第 {arg_idx + 1} 参字面量 {arg.value!r} "
                            f"不在词表（{sorted(vocab)}——错拼编译期炸；动态元素请用 "
                            f"element_of(...) 表达式参）：{source!r}"
                        )
    return PreparedExpression(source=source, tree=tree)


# ---------------------------------------------------------------------------
# 求值
# ---------------------------------------------------------------------------

def _builtins(rng: Optional[_random_mod.Random]) -> Dict[str, Callable[..., Any]]:
    def chance(n: float) -> bool:
        if rng is None:
            raise ExpressionError("chance(N) 需要注入随机源（rng 参数）")
        return rng.random() * 100 < n

    def uniform() -> float:
        if rng is None:
            raise ExpressionError("random() 需要注入随机源（rng 参数）")
        return rng.random()

    return {
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "clamp": lambda x, lo, hi: max(lo, min(hi, x)),
        "sum": sum,
        "chance": chance,
        "random": uniform,
    }


def _get_attr(obj: Any, name: str, source: str) -> Any:
    if isinstance(obj, Mapping):
        if name not in obj:
            raise ExpressionError(f"属性/字段 {name!r} 不存在：{source!r}")
        return obj[name]
    if not hasattr(obj, name):
        raise ExpressionError(f"属性 {name!r} 不存在于对象 {type(obj).__name__}：{source!r}")
    return getattr(obj, name)


def _get_item(obj: Any, key: Any, source: str) -> Any:
    try:
        return obj[key]
    except (KeyError, IndexError, TypeError) as e:
        raise ExpressionError(f"下标 {key!r} 访问失败：{source!r}（{e}）") from e


def evaluate(
    prepared: PreparedExpression,
    context: Optional[Mapping[str, Any]] = None,
    rng: Optional[_random_mod.Random] = None,
    functions: Optional[Mapping[str, Callable[..., Any]]] = None,
    trace: bool = True,
    zone_refs: Optional[Mapping[str, PreparedExpression]] = None,
    zone_cache: Optional[Dict[str, Any]] = None,
) -> EvalOutcome:
    """纯函数求值：context 提供 self/resource/event/... 命名空间对象.

    - `rng`：chance/random 的来源（确定性靠注入 seed，如 random.Random(42)）
    - `functions`：宿主提供的 in_zone / lookup_table 等实现
    - `trace=False`：快路径——不构建节点值树（trace 字段为 {}），宿主函数表惰性构建
      （无函数调用的表达式零 dict 开销）。求值序/短路语义与 trace 路径一致，同 context 同值。
    - `zone_refs`：乘区引用表（统一 AST 求值——公式大 AST 按名字引用乘区
      小子 AST）。Name 命中表时**就地对被引用子 AST 求值**（子树共享自 rulebook——
      乘区定义一次、处处引用，不做文本拷贝），trace 路径产出 ZoneRef 标记节点
      （含子树节点值树——乘区拆解结构自带）；子树内部不再解析乘区引用（乘区表达式
      只引用输入变量，rulebook 声明闸同口径）。
    - `zone_cache`：乘区求值缓存（exactly-once 语义）：命中即回传缓存的
      (值, 子树 trace) 而不再求值；未命中求值后**写回**——公式引用的每个乘区全表
      恰好求值一次（**含短路与三元未取分支**——zone 级 eager 求值语义冻结：
      随机流消耗序 = 引用点在求值器首遇序），调用方可在求值前按 AST 首遇序
      预填缓存以钉死顺序。
    """
    ctx = dict(context or {})
    funcs_cache: Optional[Dict[str, Callable[..., Any]]] = None
    in_zone_ref = False  # 乘区子树求值中——子树内 Name 只读 context（引用不嵌套）

    def funcs() -> Dict[str, Callable[..., Any]]:
        # 宿主函数表惰性构建：无函数调用的表达式不重建 builtins dict（热循环乘区主力路径）
        nonlocal funcs_cache
        if funcs_cache is None:
            funcs_cache = _builtins(rng)
            for name, fn in (functions or {}).items():
                funcs_cache[name] = fn
        return funcs_cache

    def ev_fast(node: ast.AST) -> Any:
        """trace=False 求值器：与 ev 同求值序/短路语义（rng 消耗序一致），零节点值树."""
        if isinstance(node, ast.Expression):
            return ev_fast(node.body)

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, (ast.List, ast.Tuple)):
            items = [ev_fast(elt) for elt in node.elts]
            return items if isinstance(node, ast.List) else tuple(items)

        if isinstance(node, ast.Name):
            nonlocal in_zone_ref
            if zone_refs is not None and not in_zone_ref and node.id in zone_refs:
                if zone_cache is not None and node.id in zone_cache:
                    return zone_cache[node.id][0]
                in_zone_ref = True
                try:
                    value = ev_fast(zone_refs[node.id].tree.body)
                finally:
                    in_zone_ref = False
                if zone_cache is not None:
                    zone_cache[node.id] = (value, {})
                return value
            if node.id not in ctx:
                raise ExpressionError(f"未定义变量 {node.id!r}：{prepared.source!r}")
            return ctx[node.id]

        if isinstance(node, ast.Attribute):
            return _get_attr(ev_fast(node.value), node.attr, prepared.source)

        if isinstance(node, ast.Subscript):
            return _get_item(ev_fast(node.value), ev_fast(node.slice), prepared.source)

        if isinstance(node, ast.BinOp):
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ExpressionError(f"非法运算符 {type(node.op).__name__}：{prepared.source!r}")
            return op(ev_fast(node.left), ev_fast(node.right))

        if isinstance(node, ast.UnaryOp):
            operand = ev_fast(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise ExpressionError(f"非法一元运算符 {type(node.op).__name__}：{prepared.source!r}")

        if isinstance(node, ast.BoolOp):
            value: Any = None
            for item in node.values:
                value = ev_fast(item)
                if isinstance(node.op, ast.And) and not value:
                    break
                if isinstance(node.op, ast.Or) and value:
                    break
            return value

        if isinstance(node, ast.Compare):
            left = ev_fast(node.left)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = ev_fast(comparator)
                op = _CMP_OPS.get(type(op_node))
                if op is None:
                    raise ExpressionError(f"非法比较运算符 {type(op_node).__name__}：{prepared.source!r}")
                if not op(left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.IfExp):
            return ev_fast(node.body) if ev_fast(node.test) else ev_fast(node.orelse)

        if isinstance(node, ast.Call):
            name = node.func.id  # parse 时已校验是白名单 Name
            fn = funcs().get(name)
            if fn is None:
                raise ExpressionError(f"函数 {name!r} 无宿主实现：{prepared.source!r}")
            args = [ev_fast(a) for a in node.args]
            kwargs = {kw.arg: ev_fast(kw.value) for kw in node.keywords}
            return fn(*args, **kwargs)

        raise ExpressionError(f"未支持的语法结构 {type(node).__name__}：{prepared.source!r}")

    def ev(node: ast.AST) -> Tuple[Any, Dict[str, Any]]:
        label = type(node).__name__

        if isinstance(node, ast.Expression):
            value, trace = ev(node.body)
            return value, trace

        if isinstance(node, ast.Constant):
            return node.value, {"kind": "Constant", "value": node.value}

        if isinstance(node, (ast.List, ast.Tuple)):
            items, traces = [], []
            for elt in node.elts:
                v, t = ev(elt)
                items.append(v)
                traces.append(t)
            value = items if isinstance(node, ast.List) else tuple(items)
            return value, {"kind": type(node).__name__, "value": value, "children": traces}

        if isinstance(node, ast.Name):
            nonlocal in_zone_ref
            if zone_refs is not None and not in_zone_ref and node.id in zone_refs:
                # 乘区引用（统一 AST）：缓存命中回传（exactly-once——未取分支同样
                # 已求值）；未命中就地求值并写回缓存，trace 挂 ZoneRef 标记节点
                if zone_cache is not None and node.id in zone_cache:
                    value, sub_trace = zone_cache[node.id]
                    return value, {"kind": "ZoneRef", "id": node.id, "value": value,
                                   "children": [sub_trace]}
                in_zone_ref = True
                try:
                    value, sub_trace = ev(zone_refs[node.id].tree.body)
                finally:
                    in_zone_ref = False
                if zone_cache is not None:
                    zone_cache[node.id] = (value, sub_trace)
                return value, {"kind": "ZoneRef", "id": node.id, "value": value,
                               "children": [sub_trace]}
            if node.id not in ctx:
                raise ExpressionError(f"未定义变量 {node.id!r}：{prepared.source!r}")
            return ctx[node.id], {"kind": "Name", "id": node.id, "value": ctx[node.id]}

        if isinstance(node, ast.Attribute):
            obj, obj_trace = ev(node.value)
            value = _get_attr(obj, node.attr, prepared.source)
            return value, {
                "kind": "Attribute", "attr": node.attr, "value": value,
                "children": [obj_trace],
            }

        if isinstance(node, ast.Subscript):
            obj, obj_trace = ev(node.value)
            key, key_trace = ev(node.slice)
            value = _get_item(obj, key, prepared.source)
            return value, {
                "kind": "Subscript", "value": value,
                "children": [obj_trace, key_trace],
            }

        if isinstance(node, ast.BinOp):
            left, lt = ev(node.left)
            right, rt = ev(node.right)
            op = _BIN_OPS.get(type(node.op))
            if op is None:
                raise ExpressionError(f"非法运算符 {type(node.op).__name__}：{prepared.source!r}")
            value = op(left, right)
            return value, {
                "kind": "BinOp", "op": type(node.op).__name__, "value": value,
                "children": [lt, rt],
            }

        if isinstance(node, ast.UnaryOp):
            operand, ot = ev(node.operand)
            if isinstance(node.op, ast.USub):
                value = -operand
            elif isinstance(node.op, ast.UAdd):
                value = +operand
            elif isinstance(node.op, ast.Not):
                value = not operand
            else:
                raise ExpressionError(f"非法一元运算符 {type(node.op).__name__}：{prepared.source!r}")
            return value, {
                "kind": "UnaryOp", "op": type(node.op).__name__, "value": value,
                "children": [ot],
            }

        if isinstance(node, ast.BoolOp):
            results: List[Tuple[Any, Dict[str, Any]]] = []
            for item in node.values:
                v, t = ev(item)
                results.append((v, t))
                if isinstance(node.op, ast.And) and not v:
                    break
                if isinstance(node.op, ast.Or) and v:
                    break
            value = results[-1][0]
            return value, {
                "kind": "BoolOp", "op": type(node.op).__name__, "value": value,
                "children": [t for _, t in results],
            }

        if isinstance(node, ast.Compare):
            left, lt = ev(node.left)
            traces = [lt]
            for op_node, comparator in zip(node.ops, node.comparators):
                right, rt = ev(comparator)
                traces.append(rt)
                op = _CMP_OPS.get(type(op_node))
                if op is None:
                    raise ExpressionError(f"非法比较运算符 {type(op_node).__name__}：{prepared.source!r}")
                if not op(left, right):
                    return False, {"kind": "Compare", "value": False, "children": traces}
                left = right
            return True, {"kind": "Compare", "value": True, "children": traces}

        if isinstance(node, ast.IfExp):
            cond, ct = ev(node.test)
            branch = node.body if cond else node.orelse
            value, bt = ev(branch)
            return value, {
                "kind": "IfExp", "value": value,
                "children": [ct, bt],
            }

        if isinstance(node, ast.Call):
            name = node.func.id  # parse 时已校验是白名单 Name
            fn = funcs().get(name)
            if fn is None:
                raise ExpressionError(f"函数 {name!r} 无宿主实现：{prepared.source!r}")
            args, arg_traces, kwargs = [], [], {}
            for a in node.args:
                v, t = ev(a)
                args.append(v)
                arg_traces.append(t)
            for kw in node.keywords:
                v, t = ev(kw.value)
                kwargs[kw.arg] = v
                arg_traces.append(t)
            value = fn(*args, **kwargs)
            return value, {
                "kind": "Call", "func": name, "value": value,
                "children": arg_traces,
            }

        raise ExpressionError(f"未支持的语法结构 {type(node).__name__}：{prepared.source!r}")

    if not trace:
        return EvalOutcome(value=ev_fast(prepared.tree), trace={})
    value, trace_tree = ev(prepared.tree)
    return EvalOutcome(value=value, trace=trace_tree)
