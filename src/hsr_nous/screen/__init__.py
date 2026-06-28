"""屏幕识别模块：截屏 + UI 检测 + 状态解析.

**模块边界**：screen/ 零内部 import（与 pipeline/、account/ 平行）。
持有自己的 dataclass（BBox、Detection、ScreenSnapshot），通过 adapters 转 sim_schema。

**设计目标**：
- 截屏：基于 `mss`（跨平台 MIT），不依赖 ultralytics
- 检测：抽象 `Detector` 接口，默认 `StubDetector`（返回空）；提供 `OnnxDetector` 框架
  留待接入 RT-DETR-r18（Apache-2.0）权重
- 解析：把 Detection + （可选 OCR）→ `sim_schema.Encounter` 草案
- 默认 opt-in：未启用时所有函数返回友好提示

详见 docs/screen_setup.md。
"""
from __future__ import annotations

from hsr_nous.screen.capture import capture_frame, ScreenCapture, is_screen_enabled
from hsr_nous.screen.detector import (
    Detector,
    StubDetector,
    OnnxDetector,
    get_default_detector,
)
from hsr_nous.screen.models import BBox, Detection, ScreenSnapshot
from hsr_nous.screen.state_parser import (
    snapshot_to_encounter,
    parse_state,
)

__all__ = [
    "capture_frame",
    "ScreenCapture",
    "Detector",
    "StubDetector",
    "OnnxDetector",
    "get_default_detector",
    "BBox",
    "Detection",
    "ScreenSnapshot",
    "snapshot_to_encounter",
    "parse_state",
    "is_screen_enabled",
]