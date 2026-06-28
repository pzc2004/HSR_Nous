"""Pilot 测试：覆盖决策与安全检查，绝不触发真机 click."""
from __future__ import annotations

import os

import pytest


# -------------------------------------------------------------------- dry-run safety


def test_dry_run_default():
    """默认 PilotConfig 应当是 dry-run."""
    from hsr_nous.pilot import PilotConfig

    cfg = PilotConfig()
    assert cfg.dry_run is True


def test_is_autopilot_disabled_by_default(monkeypatch):
    monkeypatch.delenv("HSR_NOUS_ALLOW_AUTOPILOT", raising=False)
    from hsr_nous.pilot.actuator import is_autopilot_enabled

    assert is_autopilot_enabled() is False


def test_is_autopilot_enabled_when_env_set(monkeypatch):
    monkeypatch.setenv("HSR_NOUS_ALLOW_AUTOPILOT", "1")
    from hsr_nous.pilot.actuator import is_autopilot_enabled

    assert is_autopilot_enabled() is True


# -------------------------------------------------------------------- build actuator


def test_build_real_actuator_requires_env(monkeypatch):
    """未设置 ALLOW_AUTOPILOT 时启动真机模式应抛 RuntimeError."""
    monkeypatch.delenv("HSR_NOUS_ALLOW_AUTOPILOT", raising=False)
    from hsr_nous.pilot import PilotConfig, PilotController

    cfg = PilotConfig(dry_run=False, accept_text="I ACCEPT")
    with pytest.raises(RuntimeError, match="HSR_NOUS_ALLOW_AUTOPILOT"):
        PilotController(cfg)


def test_build_real_actuator_requires_accept_text(monkeypatch):
    """未键入 'I ACCEPT' 时启动真机模式应抛 RuntimeError."""
    monkeypatch.setenv("HSR_NOUS_ALLOW_AUTOPILOT", "1")
    from hsr_nous.pilot import PilotConfig, PilotController

    cfg = PilotConfig(dry_run=False, accept_text="我接受")
    with pytest.raises(RuntimeError, match="I ACCEPT"):
        PilotController(cfg)


def test_dry_run_actuator_records_events():
    """DryRunActuator 应记录所有事件而不实际触发."""
    from hsr_nous.pilot.actuator import ClickEvent, DryRunActuator

    act = DryRunActuator()
    assert act.is_dry_run() is True
    act.click(ClickEvent(x=100, y=200))
    act.press_key("q")
    assert len(act.events) == 2
    assert act.events[0] == ("click", ClickEvent(x=100, y=200))
    assert act.events[1] == ("key", "q")


# -------------------------------------------------------------------- decision loop


def test_decider_returns_pass_when_no_detections():
    """无检测结果时 decider 应返回 pass（不点击）."""
    from hsr_nous.pilot import PilotConfig, PilotController

    def empty_detector(frame):
        return []

    cfg = PilotConfig(dry_run=True, max_cycles=3)
    pilot = PilotController(cfg, detector=empty_detector)
    results = pilot.run()
    assert len(results) == 1  # 第一轮 pass，提前结束
    assert results[0].action_taken == "pass"


def test_decider_clicks_when_character_detected():
    """检测到角色头像时应触发 click 事件."""
    from hsr_nous.pilot import PilotConfig, PilotController
    from hsr_nous.pilot.actuator import DryRunActuator
    from hsr_nous.screen.models import BBox, Detection

    detections = [
        Detection(label="character_portrait", bbox=BBox(0.1, 0.2, 0.05, 0.1), confidence=0.9)
    ]

    def fake_detector(frame):
        return detections

    act = DryRunActuator()
    cfg = PilotConfig(dry_run=True, max_cycles=1)
    pilot = PilotController(cfg, detector=fake_detector, actuator=act)
    pilot.run()

    # 期望 1 次 click 事件
    click_events = [e for e in act.events if e[0] == "click"]
    assert len(click_events) == 1
    # 坐标：BBox(0.1, 0.2, 0.05, 0.1) → (0.1+0.025)*1920=240, (0.2+0.05)*1080=270
    assert click_events[0][1].x == 240
    assert click_events[0][1].y == 270


def test_low_confidence_breaks_loop():
    """置信度低于阈值应 pass（不点击）."""
    from hsr_nous.pilot import PilotConfig, PilotController
    from hsr_nous.pilot.actuator import DryRunActuator
    from hsr_nous.screen.models import BBox, Detection

    detections = [
        Detection(label="character_portrait", bbox=BBox(0.1, 0.2, 0.05, 0.1), confidence=0.3)
    ]

    def fake_detector(frame):
        return detections

    act = DryRunActuator()
    cfg = PilotConfig(dry_run=True, max_cycles=5, min_confidence=0.6)
    pilot = PilotController(cfg, detector=fake_detector, actuator=act)
    results = pilot.run()

    assert results[0].action_taken == "pass"
    assert any(e[0] == "click" for e in act.events) is False


def test_exception_in_loop_stops_safely():
    """循环内异常应立即停止（fail-safe）."""
    from hsr_nous.pilot import PilotConfig, PilotController

    def broken_detector(frame):
        raise RuntimeError("simulated failure")

    cfg = PilotConfig(dry_run=True, max_cycles=5)
    pilot = PilotController(cfg, detector=broken_detector)
    results = pilot.run()
    assert results == []  # 第一轮就 fail，立即停止