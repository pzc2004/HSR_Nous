"""Actuator：抽象点击/键盘接口 + DryRunActuator.

DryRunActuator 是默认实现——只打印坐标，不实际触发。
真机 Actuator 仅在 `HSR_NOUS_ALLOW_AUTOPILOT=1` 且通过 I ACCEPT 后由
PilotController 实例化。
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple


@dataclass
class ClickEvent:
    """一次点击的描述."""

    x: int
    y: int
    button: str = "left"  # "left" | "right" | "middle"
    duration: float = 0.05  # 按住时长（秒）


class Actuator(ABC):
    """点击/键盘抽象."""

    @abstractmethod
    def click(self, event: ClickEvent) -> None:
        """执行一次点击."""
        raise NotImplementedError

    @abstractmethod
    def press_key(self, key: str) -> None:
        """按一次键盘按键."""
        raise NotImplementedError

    @abstractmethod
    def is_dry_run(self) -> bool:
        """是否为 dry-run（不实际触发）."""
        raise NotImplementedError


class DryRunActuator(Actuator):
    """默认实现：只打印坐标，不触发."""

    def __init__(self) -> None:
        self._events: list = []  # 记录所有事件用于测试

    def click(self, event: ClickEvent) -> None:
        self._events.append(("click", event))

    def press_key(self, key: str) -> None:
        self._events.append(("key", key))

    def is_dry_run(self) -> bool:
        return True

    @property
    def events(self):
        return list(self._events)


class PyAutoGuiActuator(Actuator):
    """真机 Actuator：基于 pyautogui. 默认不 import 此模块."""

    def __init__(self) -> None:
        # 故意不在 import 时加载 pyautogui
        import pyautogui  # type: ignore

        self._pg = pyautogui
        self._pg.FAILSAFE = True  # 鼠标移到屏幕角落立即停止

    def click(self, event: ClickEvent) -> None:
        self._pg.click(
            x=event.x,
            y=event.y,
            button=event.button,
            duration=event.duration,
        )

    def press_key(self, key: str) -> None:
        self._pg.press(key)

    def is_dry_run(self) -> bool:
        return False


def is_autopilot_enabled() -> bool:
    """是否启用自动战斗."""
    return os.environ.get("HSR_NOUS_ALLOW_AUTOPILOT") == "1"