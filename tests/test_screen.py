"""屏幕识别测试：用 fake numpy frames 验证 detector 与 state_parser 逻辑.

不依赖真实 mss / 显示器 / 模型权重。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

# 数据依赖闸：data/ 为 gitignored 本地数据，CI 无数据环境时跳过对应测试
_STARRES_CHARS = (
    Path(__file__).parent.parent / "data" / "starrailres" / "index_new" / "en" / "characters.json"
)


def test_stub_detector_returns_empty():
    from hsr_nous.screen import StubDetector

    det = StubDetector()
    assert det.is_ready() is False
    assert det.detect(None) == []


def test_onnx_detector_handles_missing_model(tmp_path):
    """onnx 文件不存在时 OnnxDetector 应回退到 stub 状态（不抛异常）."""
    from hsr_nous.screen import OnnxDetector

    det = OnnxDetector(tmp_path / "nonexistent.onnx")
    assert det.is_ready() is False
    assert det.detect(None) == []


def test_default_detector_returns_stub_when_no_model():
    """无 ONNX 模型时默认检测器是 StubDetector."""
    from hsr_nous.screen import get_default_detector

    det = get_default_detector()
    assert det.is_ready() is False


def test_parse_state_extracts_characters():
    from hsr_nous.screen import parse_state
    from hsr_nous.screen.models import BBox, Detection, ScreenSnapshot

    snap = ScreenSnapshot(
        width=1920,
        height=1080,
        timestamp=time.time(),
        detections=[
            Detection(label="character_portrait", bbox=BBox(0.1, 0.1, 0.1, 0.1), text="Acheron"),
            Detection(label="character_portrait", bbox=BBox(0.3, 0.1, 0.1, 0.1), text="Sparkle"),
            Detection(label="enemy", bbox=BBox(0.5, 0.5, 0.2, 0.2)),
            Detection(label="enemy", bbox=BBox(0.7, 0.5, 0.2, 0.2)),
            Detection(label="cycle_counter", bbox=BBox(0.5, 0.0, 0.1, 0.05), text="12/15"),
            Detection(label="buff_icon", bbox=BBox(0.1, 0.8, 0.05, 0.05), text="攻击力↑"),
        ],
    )
    state = parse_state(snap)
    assert state["characters"] == ["Acheron", "Sparkle"]
    assert state["enemies"] == 2
    assert state["cycle"] == 12
    assert "攻击力↑" in state["buffs"]


def test_parse_state_handles_missing_fields():
    """解析应容忍字段缺失，不抛异常."""
    from hsr_nous.screen import parse_state
    from hsr_nous.screen.models import ScreenSnapshot

    snap = ScreenSnapshot(width=1920, height=1080, timestamp=time.time())
    state = parse_state(snap)
    assert state["characters"] == []
    assert state["enemies"] == 0
    assert state["cycle"] is None


def test_snapshot_to_encounter_with_empty_snapshot():
    """空快照应至少生成 1 个 dummy 敌人 + 终结 Encounter."""
    from hsr_nous.screen import snapshot_to_encounter
    from hsr_nous.screen.models import ScreenSnapshot

    snap = ScreenSnapshot(width=1920, height=1080, timestamp=time.time())
    enc, parsed = snapshot_to_encounter(snap)
    assert len(enc.actors) >= 1  # 至少 1 个 dummy enemy
    assert parsed["characters"] == []


@pytest.mark.skipif(not _STARRES_CHARS.exists(), reason="本地无 starrailres 数据（CI 跳过）")
def test_snapshot_to_encounter_with_known_chars():
    """检测到已知角色名时应用真实适配器."""
    from hsr_nous.screen import snapshot_to_encounter
    from hsr_nous.screen.models import BBox, Detection, ScreenSnapshot

    snap = ScreenSnapshot(
        width=1920,
        height=1080,
        timestamp=time.time(),
        detections=[
            Detection(label="character_portrait", bbox=BBox(0.1, 0.1, 0.1, 0.1), text="Acheron"),
            Detection(label="enemy", bbox=BBox(0.5, 0.5, 0.2, 0.2)),
        ],
    )
    enc, parsed = snapshot_to_encounter(snap, lang="en")
    char_actors = [a for a in enc.actors if a.actor_type == "character"]
    assert any(a.name == "Acheron" for a in char_actors)


def test_screen_module_disabled_without_mss(monkeypatch):
    """mss 不可用时 is_screen_enabled 应返回 False（不让用户意外触发）."""
    import builtins

    from hsr_nous.screen import capture as capture_mod

    # 强制 mss import 失败
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mss":
            raise ImportError("mss disabled for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert capture_mod._mss_available() is False
    assert capture_mod.is_screen_enabled() is False