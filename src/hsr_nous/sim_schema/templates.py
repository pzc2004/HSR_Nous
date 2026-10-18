"""DSL 模板根：全仓唯一事实源.

per-entity DSL 模板（characters/light_cones/relics/enemies 四类 YAML）的存放根。
sim 编译侧（`sim/compile/build_compiler.py`，re-export 本常量）读它加载模板，
adapters 生成/校验侧（template_generator 写出、template_verifier 回读）对它对齐。

常量定义放 sim_schema 层的原因：模块边界闸允许 `sim → sim_schema` 与
`adapters → sim_schema`，但禁止 `adapters → sim`——定义若留在 build_compiler，
校验器/生成器够不到，只能复制字面量（A1 审计的事故起点）。

路径解析（公共层收口）：`repo_data_dir()` / `data_root()` 单一定义在
`hsr_nous/common/paths.py`（sim/sim_schema 岛不再自持副本，旧镜像闸已退役为
单一来源闸）——值从 CWD 相对字符串升级为 **env 感知绝对路径**：
`HSR_NOUS_DATA_DIR` 覆盖时缓存级根（sim_templates）跟随，仓库内容根
（library/battles）恒为仓库相对。解析在 import 期完成——进程内改环境变量不生效
（部署语义：env 先于进程启动设置，与 pipeline/paths 调用期解析的差异在闸的
覆盖语义上对齐为同一启动约定）。

稳定标签（SPECS 的首元素）：指纹/日志等**机器无关**场景用——绝对路径随机器变，
标签恒为仓库相对逻辑名（montecarlo fixtures_hash 键）。
"""
from __future__ import annotations

from hsr_nous.common.paths import data_root, repo_data_dir

__all__ = [
    "DEFAULT_TEMPLATE_ROOTS",
    "RUNTIME_TEMPLATE_ROOTS",
    "RUNTIME_TEMPLATE_ROOT_SPECS",
    "data_root",
    "repo_data_dir",
]


#: (稳定标签, 绝对路径) 有序对——运行时读根链（先命中根生效）：机制库正典根
#:（data/library——手写全机制模板 + 命途系统模块，git 追踪，仓库内容恒仓库相对）
#: 优先于 data/sim_templates 生成根（骨架兜底未覆盖实体，gitignored 纯生成物，
#: 缓存级随 HSR_NOUS_DATA_DIR 移动）。标签供机器无关指纹/日志（见模块 docstring）。
RUNTIME_TEMPLATE_ROOT_SPECS: tuple[tuple[str, str], ...] = (
    ("data/library", str(repo_data_dir() / "library")),
    ("data/sim_templates", str(data_root() / "sim_templates")),
)

#: 运行时读根缺省值（**sim 编译/加载侧的模板查找链**，有序、先命中根生效）——
#: 自 SPECS 派生；测试 monkeypatch 本常量替换临时根（契约不变）
RUNTIME_TEMPLATE_ROOTS: tuple[str, ...] = tuple(path for _, path in RUNTIME_TEMPLATE_ROOT_SPECS)

#: 模板根缺省值（**生成器写出目标 + 校验器回读对齐根**）：template_generator 生成
#: 骨架的落盘位置、template_verifier 的核对基准；缓存级，随 HSR_NOUS_DATA_DIR 移动
DEFAULT_TEMPLATE_ROOTS: tuple[str, ...] = (str(data_root() / "sim_templates"),)
