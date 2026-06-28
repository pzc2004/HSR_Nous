"""屏幕识别数据模型."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class BBox:
    """边界框（归一化坐标，0-1）."""

    x: float  # 左
    y: float  # 上
    w: float  # 宽
    h: float  # 高

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


@dataclass
class Detection:
    """单次检测结果."""

    label: str  # "character" | "enemy" | "buff_icon" | "cycle_counter" | ...
    bbox: BBox
    confidence: float = 1.0
    text: str = ""  # 可选 OCR 文本（如 "黄泉" / "12/15 轮次"）


@dataclass
class ScreenSnapshot:
    """一帧屏幕的检测结果."""

    width: int
    height: int
    detections: List[Detection] = field(default_factory=list)
    timestamp: float = 0.0  # 时间戳（time.time()）