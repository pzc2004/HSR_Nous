"""手工角色模板的物化机制（fixtures 源 → data/ 物化副本）.

真身在 `tests/fixtures/templates/`；`data/sim_templates/characters/` 下的同名文件由
测试经本模块 copy 物化（直接改 data/ 副本会被冲掉）。物化前清掉同 entity ID 的
生成器文件（如 `1408_白厄.yaml`）——loader 侧防线是撞名即炸
（`BuildCompiler._load_template`，报全部文件名），本模块保证测试物化后同 ID 唯一。
"""
from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "templates"
DATA_CHARS_DIR = Path(__file__).parent.parent / "data" / "sim_templates" / "characters"


def materialize_template(fixture_name: str) -> Path:
    """把 fixtures 模板物化到 data/：先删同 ID 文件（生成器副本），再 copy。返回物化路径。"""
    src = FIXTURES_DIR / fixture_name
    entity_id = fixture_name.split("_", 1)[0]
    DATA_CHARS_DIR.mkdir(parents=True, exist_ok=True)
    for old in DATA_CHARS_DIR.glob(f"{entity_id}_*.yaml"):
        old.unlink()
    dst = DATA_CHARS_DIR / fixture_name
    shutil.copy(src, dst)
    return dst
