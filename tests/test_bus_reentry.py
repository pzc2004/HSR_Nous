"""重入软警告：递归超阈值写警告不掐断；普通链无警告."""
from __future__ import annotations

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
