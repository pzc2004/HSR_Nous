"""PilotController：高层循环 capture → detect → decide → click.

**设计原则**：
1. 默认 DryRunActuator——只记录事件，不实际触发
2. 真机模式要求 `HSR_NOUS_ALLOW_AUTOPILOT=1` 且用户键入 `I ACCEPT`
3. 任何异常立即停止循环（fail-safe）
4. 检测置信度 < 阈值时停止（防止误操作）
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

from hsr_nous.pilot.actuator import (
    Actuator,
    ClickEvent,
    DryRunActuator,
    PyAutoGuiActuator,
    is_autopilot_enabled,
)


@dataclass
class PilotConfig:
    """Pilot 运行配置."""

    max_cycles: int = 10
    """最大循环次数（防止无限循环）."""

    min_confidence: float = 0.6
    """检测置信度下限；低于此值停止循环."""

    dry_run: bool = True
    """True = DryRunActuator；False = PyAutoGuiActuator（需 ALLOW_AUTOPILOT=1）."""

    accept_text: str = ""
    """用户键入的接受语；需等于 "I ACCEPT" 才允许真机模式."""


@dataclass
class CycleResult:
    """单次循环的结果."""

    cycle: int
    action_taken: str  # "skill" | "basic" | "ultimate" | "pass"
    target: Optional[tuple]  # (x, y) 或 None
    confidence: float = 1.0


class PilotController:
    """主循环控制器.

    每轮循环：
    1. capture_frame() → current frame
    2. detector.detect(frame) → ScreenSnapshot
    3. decide(snapshot) → action (skill/basic/ultimate/pass) + target coord
    4. actuator.click(target) / press_key(key)
    """

    def __init__(
        self,
        config: PilotConfig,
        detector: Optional[Callable] = None,
        decider: Optional[Callable] = None,
        actuator: Optional[Actuator] = None,
    ) -> None:
        self.config = config
        self.detector = detector or self._default_detector
        self.decider = decider or self._default_decider
        if actuator is not None:
            self.actuator = actuator
        elif config.dry_run:
            self.actuator = DryRunActuator()
        else:
            self.actuator = self._build_real_actuator()

    def _build_real_actuator(self) -> Actuator:
        """构建真机 actuator；任何前置条件失败时抛 RuntimeError."""
        if not is_autopilot_enabled():
            raise RuntimeError(
                "未启用自动战斗：HSR_NOUS_ALLOW_AUTOPILOT != 1"
            )
        if self.config.accept_text != "I ACCEPT":
            raise RuntimeError(
                "未键入 'I ACCEPT' 接受 ToS 风险；真机模式拒绝启动"
            )
        return PyAutoGuiActuator()

    def _default_detector(self, frame):
        """默认 detector：尝试使用 screen 模块；缺失时返回空."""
        try:
            from hsr_nous.screen import get_default_detector

            return get_default_detector().detect(frame)
        except Exception:
            return []

    def _default_decider(self, detections):
        """默认 decider：第一个检测到的角色头像位置 → 点 'skill'（启发式）."""
        for det in detections:
            if det.label == "character_portrait":
                # BBox 归一化坐标 → 假设 1920×1080 屏幕
                cx = int(det.bbox.x * 1920 + det.bbox.w * 960)
                cy = int(det.bbox.y * 1080 + det.bbox.h * 540)
                return ("skill", (cx, cy), det.confidence)
        return ("pass", None, 0.0)

    def run_once(self, frame=None) -> CycleResult:
        """执行单次循环."""
        if frame is None:
            try:
                from hsr_nous.screen import capture_frame

                frame = capture_frame()
            except Exception:
                frame = None

        detections = self.detector(frame)
        action, target, conf = self.decider(detections)

        if conf < self.config.min_confidence:
            return CycleResult(cycle=0, action_taken="pass", target=None, confidence=conf)

        if target is not None and action in ("skill", "ultimate", "basic"):
            x, y = target
            self.actuator.click(ClickEvent(x=int(x), y=int(y)))

        return CycleResult(cycle=0, action_taken=action, target=target, confidence=conf)

    def run(self) -> list[CycleResult]:
        """执行 max_cycles 轮循环."""
        results: list[CycleResult] = []
        for i in range(self.config.max_cycles):
            try:
                result = self.run_once()
                result.cycle = i + 1
                results.append(result)
                if result.action_taken == "pass":
                    break  # 无可执行动作，提前结束
            except Exception as e:
                print(f"⚠️  第 {i+1} 轮异常: {e}", file=sys.stderr)
                break  # fail-safe
        return results


def run_pilot(config: Optional[PilotConfig] = None) -> list[CycleResult]:
    """便捷入口：构造 PilotController 并执行."""
    if config is None:
        config = PilotConfig()
    return PilotController(config).run()