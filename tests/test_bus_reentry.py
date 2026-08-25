"""重入软警告：递归超阈值写警告不掐断；普通链无警告；自供能死循环撞硬帽熔断."""
from __future__ import annotations

import pytest

from hsr_nous.sim.bus import EventBus


class _Ctx:
    def __init__(self):
        self.log: list = []


class TestReentryWarn:
    def test_recursive_chain_warns_but_not_blocked(self):
        bus = EventBus()
        ctx = _Ctx()
        count = {"n": 0}

        def recursive(et, payload, c):
            count["n"] += 1
            if count["n"] < 25:  # 自终止的"准死循环"（深度 25 > 阈值 20）
                bus.emit("ping", {}, ctx)

        bus.subscribe("ping", recursive)
        bus.emit("ping", {}, ctx)

        assert count["n"] == 25, "软警告不掐断——合法/自终止长链正常跑完"
        warn_logs = [l for l in ctx.log if "重入深度超" in l]
        assert len(warn_logs) == 1, f"警告应恰好一条（每链一次不刷屏）：{ctx.log}"

    def test_shallow_chain_no_warn(self):
        bus = EventBus()
        ctx = _Ctx()
        bus.subscribe("ping", lambda et, p, c: bus.emit("pong", {}, ctx))
        bus.subscribe("pong", lambda et, p, c: None)
        bus.emit("ping", {}, ctx)
        assert not any("重入深度超" in l for l in ctx.log)


class TestReentryHardCap:
    def test_self_feeding_chain_raises_runtime_error(self):
        """自供能 hook 链（无燃料耗尽）：硬帽熔断 RuntimeError 而非 RecursionError 裸崩."""
        bus = EventBus()
        ctx = _Ctx()
        bus.subscribe("ping", lambda et, p, c: bus.emit("ping", {}, ctx))
        with pytest.raises(RuntimeError, match="ping"):
            bus.emit("ping", {}, ctx)
        assert bus._depth == 0, "熔断逐层退栈后深度计数应归零（总线可诊断复用）"

    def test_hard_cap_above_warn_depth(self):
        """硬帽（128）远高于软警告（20）：合法长链有充分余量不被误熔."""
        assert EventBus.REENTRY_HARD_CAP >= 4 * EventBus.REENTRY_WARN_DEPTH

    def test_waterfall_self_feeding_raises(self):
        """waterfall 链同受硬帽约束."""
        bus = EventBus()
        ctx = _Ctx()
        bus.subscribe_waterfall(
            "before_take_damage",
            lambda et, p, c: bus.waterfall("before_take_damage", dict(p), ctx))
        with pytest.raises(RuntimeError, match="before_take_damage"):
            bus.waterfall("before_take_damage", {"amount": 1.0}, ctx)
