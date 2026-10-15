"""手工全机制模板（机制库正典）的测试根注入入口.

手工全机制模板真身在 `data/library/characters/`（机制库正典根，git 追踪；与
data/sim_templates 生成根同构的 {kind}/ 子目录布局）。loader
（`sim/compile/build_compiler.py:_load_template`）已支持根注入：测试编译时传
`template_roots=TEST_TEMPLATE_ROOTS`（有序，正典根优先于生成根——
同名引用由正典根压制，生成器在 data/sim_templates 再生成多少副本都不会撞）。

历史 copy 物化机制（fixtures → data/ 同名副本 + 物化前清同 ID 生成文件）随之退役：
`materialize_template` 保留为 no-op 兼容旧调用点（只返回正典源路径，不写生成根），
新测试请直接传 roots。
"""
from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent.parent / "data" / "library"
DATA_CHARS_DIR = Path(__file__).parent.parent / "data" / "sim_templates" / "characters"

#: 测试模板根（有序，正典根优先）：compile_encounter(..., template_roots=TEST_TEMPLATE_ROOTS)
TEST_TEMPLATE_ROOTS = [str(FIXTURES_DIR), "data/sim_templates"]


def materialize_template(fixture_name: str) -> Path:
    """已退役 no-op：loader 支持根注入后 copy 物化不再需要。返回正典源路径。"""
    return FIXTURES_DIR / "characters" / fixture_name
