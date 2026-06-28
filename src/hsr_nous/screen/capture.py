"""屏幕截屏：基于 mss（跨平台 MIT）.

默认截取主显示器全屏（1920×1080 起），可指定区域。
"""
from __future__ import annotations

import os
from typing import Optional


def _mss_available() -> bool:
    try:
        import mss  # noqa: F401
        return True
    except ImportError:
        return False


class ScreenCapture:
    """屏幕截屏封装."""

    def __init__(self, monitor: int = 0) -> None:
        self.monitor = monitor
        self._mss = None

    def _ensure_mss(self) -> None:
        if self._mss is None:
            import mss

            self._mss = mss.mss()

    def grab(self) -> "numpy.ndarray":
        """截取一帧 RGB 图像（numpy 数组）.

        返回 shape=(H, W, 3)，dtype=uint8 的 RGB 图像。
        """
        if not _mss_available():
            raise RuntimeError(
                "mss 未安装。请运行: uv pip install mss"
            )
        self._ensure_mss()
        import numpy as np

        img = np.array(self._mss.grab(self._mss.monitors[self.monitor]))
        # mss 返回 BGRA → 转 RGB
        return img[:, :, :3][:, :, ::-1].copy()

    def size(self) -> tuple[int, int]:
        """返回当前监视器的 (width, height)."""
        if not _mss_available():
            return (1920, 1080)  # 默认假设
        self._ensure_mss()
        m = self._mss.monitors[self.monitor]
        return (m["width"], m["height"])


_default_capture: Optional[ScreenCapture] = None


def capture_frame() -> "numpy.ndarray":
    """便捷接口：截取主显示器一帧 RGB 图像."""
    global _default_capture
    if _default_capture is None:
        _default_capture = ScreenCapture()
    return _default_capture.grab()


def is_screen_enabled() -> bool:
    """屏幕模块是否启用（mss 安装 + 监视器可达）."""
    if not _mss_available():
        return False
    if os.environ.get("HSR_NOUS_SCREEN_DISABLED") == "1":
        return False
    return True