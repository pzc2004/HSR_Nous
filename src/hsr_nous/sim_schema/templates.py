"""DSL 模板根：全仓唯一事实源.

per-entity DSL 模板（characters/light_cones/relics/enemies 四类 YAML）的存放根。
sim 编译侧（`sim/compile/build_compiler.py`，re-export 本常量）读它加载模板，
adapters 生成/校验侧（template_generator 写出、template_verifier 回读）对它对齐。

常量定义放 sim_schema 层的原因：模块边界闸允许 `sim → sim_schema` 与
`adapters → sim_schema`，但禁止 `adapters → sim`——定义若留在 build_compiler，
校验器/生成器够不到，只能复制字面量（A1 审计的事故起点）。
"""
from __future__ import annotations

__all__ = ["DEFAULT_TEMPLATE_ROOTS", "RUNTIME_TEMPLATE_ROOTS"]

#: 模板根缺省值（**生成器写出目标 + 校验器回读对齐根**，相对 CWD——与不注入时的
#: 历史行为一致）：template_generator 生成骨架的落盘位置、template_verifier 的核对基准
DEFAULT_TEMPLATE_ROOTS: tuple[str, ...] = ("data/sim_templates",)

#: 运行时读根缺省值（**sim 编译/加载侧的模板查找链**，有序、先命中根生效）：
#: 人工 fixtures 根（tests/fixtures/templates——全机制正典，git 追踪）优先于
#: data/ 生成根（骨架兜底未覆盖实体）。2026-10-12 前读根即 DEFAULT_TEMPLATE_ROOTS
#: （生产裸跑只有骨架——fixtures 全机制不到生产的缺口；web --templates 显式注入
#: fixtures 时两根同链、首命中仍 fixtures，与旧注入行为一致）
RUNTIME_TEMPLATE_ROOTS: tuple[str, ...] = ("tests/fixtures/templates", "data/sim_templates")
