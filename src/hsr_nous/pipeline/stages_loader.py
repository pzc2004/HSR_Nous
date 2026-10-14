"""兼容壳：真身已迁 `pipeline/stages/loader.py`（P1 三域归置）.

旧 import 路径保留（`from hsr_nous.pipeline.stages_loader import ...` 零改动——
sys.modules 别名，下划线私有件同真身）；新代码请引 `pipeline.stages.loader`。
"""
import sys

from hsr_nous.pipeline.stages import loader as _real

sys.modules[__name__] = _real
