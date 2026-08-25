"""DSL 模板根：全仓唯一事实源.

per-entity DSL 模板（characters/light_cones/relics/enemies 四类 YAML）的存放根。
sim 编译侧（`sim/compile/build_compiler.py`，re-export 本常量）读它加载模板，
adapters 生成/校验侧（template_generator 写出、template_verifier 回读）对它对齐。

常量定义放 sim_schema 层的原因：模块边界闸允许 `sim → sim_schema` 与
`adapters → sim_schema`，但禁止 `adapters → sim`——定义若留在 build_compiler，
校验器/生成器够不到，只能复制字面量（A1 审计的事故起点）。
"""
from __future__ import annotations

__all__ = ["DEFAULT_TEMPLATE_ROOTS"]

#: 模板根缺省值（生产唯一来源，相对 CWD——与不注入时的历史行为一致）：
#: 调用方不传 template_roots/out_dir 时只查 data/sim_templates
DEFAULT_TEMPLATE_ROOTS: tuple[str, ...] = ("data/sim_templates",)
