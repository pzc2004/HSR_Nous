"""UI 检测器抽象 + 默认实现.

`Detector` 是抽象接口；`StubDetector` 返回空检测（默认）；
`OnnxDetector` 提供 ONNX Runtime 推理框架（待 RT-DETR-r18 权重训练）。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from hsr_nous.screen.models import BBox, Detection, ScreenSnapshot


class Detector(ABC):
    """UI 检测器抽象基类."""

    @abstractmethod
    def detect(self, frame) -> List[Detection]:
        """对单帧图像做检测，返回 Detection 列表."""
        raise NotImplementedError

    @abstractmethod
    def is_ready(self) -> bool:
        """模型是否加载完毕."""
        raise NotImplementedError


class StubDetector(Detector):
    """占位检测器：始终返回空检测."""

    def __init__(self, reason: str = "no model loaded") -> None:
        self._reason = reason

    def detect(self, frame) -> List[Detection]:
        return []

    def is_ready(self) -> bool:
        return False

    def __repr__(self) -> str:
        return f"StubDetector(reason={self._reason!r})"


class OnnxDetector(Detector):
    """ONNX Runtime 检测器框架.

    Args:
        model_path: .onnx 模型权重路径（如 RT-DETR-r18 导出的 onnx）
        confidence_threshold: 检测置信度阈值
        labels: 可选 label 列表（顺序对应模型输出）；不提供则用默认 HSR UI vocab

    用法：
        det = OnnxDetector("data/yolo/rtdetr_r18.onnx")
        if det.is_ready():
            frame = capture_frame()
            detections = det.detect(frame)
    """

    DEFAULT_HSR_LABELS = [
        "character_portrait",
        "enemy",
        "buff_icon",
        "debuff_icon",
        "ultimate_ready",
        "cycle_counter",
        "enemy_hp_bar",
        "character_hp_bar",
    ]

    def __init__(
        self,
        model_path: str | Path,
        *,
        confidence_threshold: float = 0.5,
        labels: List[str] | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.labels = labels or self.DEFAULT_HSR_LABELS
        self._session = None
        self._try_load()

    def _try_load(self) -> None:
        if not self.model_path.exists():
            return
        try:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception:
            self._session = None

    def is_ready(self) -> bool:
        return self._session is not None

    def detect(self, frame) -> List[Detection]:
        if not self.is_ready():
            return []
        # 真实实现需要：图像预处理 → ONNX 推理 → 后处理（NMS）→ 转 BBox
        # 当前 stub：返回空
        return []


def get_default_detector() -> Detector:
    """根据环境选择默认检测器.

    优先级：
    1. 若 `data/yolo/rtdetr_r18.onnx` 存在 → OnnxDetector
    2. 否则 → StubDetector（不报错，detector.detect() 返回空）
    """
    candidates = [
        Path("data/yolo/rtdetr_r18.onnx"),
        Path(os.environ.get("HSR_NOUS_YOLO_MODEL", "")),
    ]
    for p in candidates:
        if p and p.exists():
            return OnnxDetector(p)
    return StubDetector(reason="未配置 ONNX 模型权重；detector.detect() 返回空")