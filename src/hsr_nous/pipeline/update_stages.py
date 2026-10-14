"""兼容壳：真身已迁 `pipeline/stages/update.py`（P1 三域归置）.

旧 import 路径保留（`from hsr_nous.pipeline import update_stages` 零改动——
sys.modules 别名，下划线私有件同真身）；新代码请引 `pipeline.stages.update`。
"""
import sys

from hsr_nous.pipeline.stages import update as _real

sys.modules[__name__] = _real
