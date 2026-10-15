"""表达式编译器：模板绑定期预编译 AST，热循环只带 context 求值.

B8 验收标准：白名单节点/函数单测全覆盖、非法输入拒绝、纯函数输出。
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from hsr_nous.sim_schema.expression import EvalOutcome, PreparedExpression, evaluate, parse


class ExprCompiler:
    """表达式编译与求值（parse 缓存：同一源码只编译一次）."""

    def __init__(self) -> None:
        self._cache: Dict[tuple[str, str], PreparedExpression] = {}

    def compile(self, source: str, layer: str = "effect") -> PreparedExpression:
        """编译（白名单静态校验）；非法输入抛 ExpressionError."""
        key = (source, layer)
        if key not in self._cache:
            self._cache[key] = parse(source, layer)
        return self._cache[key]

    def try_compile(self, source: str, layer: str = "effect") -> Optional[PreparedExpression]:
        """恒真/空表达式 → None；其余同 compile."""
        if source is None or str(source).strip() in ("", "true", "True"):
            return None
        return self.compile(source, layer)

    def evaluate(
        self,
        prepared: PreparedExpression,
        context: Optional[Mapping[str, Any]] = None,
        rng: Any = None,
        functions: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        """纯函数求值：context 注入命名空间，rng 决定 chance/random."""
        return evaluate(prepared, context=context, rng=rng, functions=functions).value
