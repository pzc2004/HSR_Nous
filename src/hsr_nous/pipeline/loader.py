"""兼容壳：真身已迁 `pipeline/build/loader.py`（P1 三域归置）.

旧 import 路径保留（`from hsr_nous.pipeline.loader import ...` 与
`from hsr_nous.pipeline import ...` 均零改动——sys.modules 别名，下划线
私有件同真身）；新代码请引 `pipeline.build.loader`。
"""
import sys

from hsr_nous.pipeline.build import loader as _real

sys.modules[__name__] = _real
