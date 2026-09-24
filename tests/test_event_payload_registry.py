"""payload 注册表收割闸：sim/bus.py DEFAULT_PAYLOAD_FIELDS == sim/ 源码 AST 收割集.

注册表勿手改的 enforcement——发射点（bus.emit/bus.waterfall 字面 dict）改键后必须同步
注册表（与 23 章事件表"实发集"同义）。两腿皆在本文件：收割双向对拍（事件集+键集）
+ 契约内已发射事件全覆盖。（原 annotator 镜像第三腿随 test_mechanism_annotator 删除截肢。）
"""

from __future__ import annotations

import ast
from pathlib import Path

from hsr_nous.sim.bus import DEFAULT_CONTRACT, DEFAULT_PAYLOAD_FIELDS

_SIM_DIR = Path(__file__).resolve().parents[1] / "src" / "hsr_nous" / "sim"


def _harvest() -> dict:
    """bus.emit/bus.waterfall 调用点：第一参数字面事件名 + 第二参数字面 dict 键并集."""
    harvest: dict = {}
    for f in sorted(_SIM_DIR.rglob("*.py")):
        if "web_static" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in ("emit", "waterfall")):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant) \
                    or not isinstance(node.args[0].value, str):
                continue
            ev = node.args[0].value
            if ev not in DEFAULT_CONTRACT:
                continue
            if len(node.args) < 2:
                harvest.setdefault(ev, set())
                continue
            payload = node.args[1]
            assert isinstance(payload, ast.Dict), (
                f"{f}:{node.lineno} 事件 {ev!r} 的 payload 不是字面 dict——收割不可见："
                "改回字面 dict 或先更新收割函数")
            for k in payload.keys:
                assert isinstance(k, ast.Constant) and isinstance(k.value, str), (
                    f"{f}:{node.lineno} 事件 {ev!r} 的 payload 含非字面键——收割不可见")
                harvest.setdefault(ev, set()).add(k.value)
    return harvest


def test_registry_matches_harvest():
    harvest = _harvest()
    only_registry = set(DEFAULT_PAYLOAD_FIELDS) - set(harvest)
    only_engine = set(harvest) - set(DEFAULT_PAYLOAD_FIELDS)
    assert not only_registry and not only_engine, (
        f"事件集合漂移：only-registry={sorted(only_registry)} only-engine={sorted(only_engine)}")
    for ev, keys in harvest.items():
        assert DEFAULT_PAYLOAD_FIELDS[ev] == frozenset(keys), (
            f"{ev} payload 字段漂移：registry={sorted(DEFAULT_PAYLOAD_FIELDS[ev])} "
            f"engine={sorted(keys)}——改发射点后同步 sim/bus.py DEFAULT_PAYLOAD_FIELDS")


def test_registry_covers_all_emitted_contract_events():
    """契约内事件凡有发射点必须在表（未发射事件不在表——模板引用其字段即炸，正确行为）。"""
    emitted = {ev for ev, keys in _harvest().items() if keys}
    assert emitted <= set(DEFAULT_PAYLOAD_FIELDS)
