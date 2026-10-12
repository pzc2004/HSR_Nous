"""ops/dag 通用执行器语义钉（v1a）.

六类：线性链 / 动态扇出内环（gate 打回→revise→再闸，append-only）/ 重放（缓存命中跳过、
脏子图重跑）/ 服务并发闸 / 声明期错误（重复 id、未注册依赖）/ fail-fast。
"""

from __future__ import annotations

import threading
import time

import pytest

from hsr_nous.ops.dag import DagError, Node, Runner, ServiceRegistry


def test_linear_chain_order_and_outputs(tmp_path):
    order = []

    def mk(name):
        def fn(inputs):
            order.append(name)
            return name.upper()
        return fn

    r = Runner(tmp_path)
    r.add(Node("c", mk("c"), deps=("b",)), Node("a", mk("a")), Node("b", mk("b"), deps=("a",)))
    out = r.run()
    assert order == ["a", "b", "c"], "拓扑序执行"
    assert out == {"a": "A", "b": "B", "c": "C"}


def _loop_chain(calls):
    """draft → gate#N（打回则扇出 revise#N+gate#N+1，通过则扇出 finalize）——内环本体.

    fn 只干活（评测）、shape 纯函数路由（从值推子图）——重放缓存命中时 shape 仍会
    从缓存值重建扇出图。
    """

    def draft(inputs):
        calls["draft"] += 1
        return "tpl_v1"

    def make_gate(n):
        def gate(inputs):
            calls["gate"] += 1
            tpl = next(iter(inputs.values()))
            ok = calls["gate"] >= 3
            return {"tpl": tpl, "ok": ok, "err": "" if ok else f"词表闸: v{n} bad key"}

        def shape(value):
            if value["ok"]:
                return (Node("finalize", lambda i: f"落库 {i[f'gate{n}']['tpl']}",
                             deps=(f"gate{n}",)),)
            nxt = n + 1
            g, s = make_gate(nxt)
            return (
                Node(f"revise{n}", make_revise(nxt), deps=(f"gate{n}",)),
                Node(f"gate{nxt}", g, deps=(f"revise{n}",), shape=s),
            )

        return gate, shape

    def make_revise(n):
        def revise(inputs):
            calls["revise"] += 1
            err = inputs[f"gate{n - 1}"]["err"]     # 错误输出回喂（内环反馈通道）
            return f"tpl_v{n}_fixed({err})"
        return revise

    gate1, shape1 = make_gate(1)
    return [Node("draft", draft), Node("gate1", gate1, deps=("draft",), shape=shape1)]


def test_fanout_inner_loop_append_only(tmp_path):
    calls = {"draft": 0, "revise": 0, "gate": 0}
    r = Runner(tmp_path)
    r.add(*_loop_chain(calls))
    out = r.run()
    assert calls == {"draft": 1, "revise": 2, "gate": 3}, "打回两次第三次过"
    assert "revise1" in r._nodes and "gate3" in r._nodes, "每次尝试都是一等节点（append-only）"
    assert out["finalize"] == "落库 tpl_v3_fixed(词表闸: v2 bad key)", "错误输出回喂进修订"


def test_replay_cache_hit_and_dirty_subgraph(tmp_path):
    calls = {"a": 0, "b": 0}

    def a(inputs):
        calls["a"] += 1
        return "A"

    def b(inputs):
        calls["b"] += 1
        return inputs["a"] + "B"

    def build():
        r = Runner(tmp_path)
        r.add(Node("a", a), Node("b", b, deps=("a",)))
        return r

    build().run()
    assert calls == {"a": 1, "b": 1}
    out2 = build().run()
    assert calls == {"a": 1, "b": 1}, "输入哈希不变 → 全缓存命中零执行"
    assert out2 == {"a": "A", "b": "AB"}, "缓存值照样可用"

    def a2(inputs):
        calls["a"] += 1
        return "A2"

    def build2():
        r = Runner(tmp_path)
        r.add(Node("a", a2), Node("b", b, deps=("a",)))
        return r

    out3 = build2().run()
    assert calls == {"a": 2, "b": 2}, "输入变 → 自身与下游标脏重跑"
    assert out3 == {"a": "A2", "b": "A2B"}


def test_replay_cache_hit_cascades_ready_scan(tmp_path):
    """全缓存重放：命中解决的节点间接满足他人依赖——就绪集必须重扫（曾因 running 空
    且 pending 未清误判'不可满足依赖'炸出）。."""
    calls = {"n": 0}

    def mk(name):
        def fn(inputs):
            calls["n"] += 1
            return name
        return fn

    def build():
        r = Runner(tmp_path)
        # 声明序刻意逆拓扑（c→b→a），全缓存趟内 a 命中后 b/c 才就绪
        r.add(Node("c", mk("c"), deps=("b",)), Node("b", mk("b"), deps=("a",)), Node("a", mk("a")))
        return r

    build().run()
    assert calls["n"] == 3
    out = build().run()   # 全缓存第二趟：不得炸、不得执行
    assert calls["n"] == 3 and out == {"a": "a", "b": "b", "c": "c"}


def test_service_semaphore_limits_concurrency(tmp_path):
    active = {"cur": 0, "max": 0}
    lock = threading.Lock()

    def slow(inputs):
        with lock:
            active["cur"] += 1
            active["max"] = max(active["max"], active["cur"])
        time.sleep(0.05)
        with lock:
            active["cur"] -= 1
        return 1

    r = Runner(tmp_path, services=ServiceRegistry({"svc": 1}), max_workers=4)
    r.add(Node("n1", slow, service="svc"), Node("n2", slow, service="svc"),
          Node("n3", slow, service="svc"))
    r.run()
    assert active["max"] == 1, "同服务并发闸=1 → 不重叠"


def test_declaration_errors(tmp_path):
    r = Runner(tmp_path)
    r.add(Node("a", lambda i: 1))
    with pytest.raises(DagError, match="重复"):
        r.add(Node("a", lambda i: 2))
    r.add(Node("b", lambda i: 1, deps=("ghost",)))   # 声明乱序可——依赖存在性 run() 才校验
    with pytest.raises(DagError, match="未注册"):
        r.run()


def test_fail_fast_carries_node_id(tmp_path):
    def boom(inputs):
        raise ValueError("炸了")

    r = Runner(tmp_path)
    r.add(Node("ok", lambda i: 1), Node("bad", boom))
    with pytest.raises(DagError, match="'bad'"):
        r.run()


def test_salt_change_invalidates_cache(tmp_path):
    """Node.salt（闭包值指纹兜底通道）：同 fn 同输入，salt 变 → 缓存失效重跑——
    打标提示词/锚范例内容改动不复活旧稿（executor fn 指纹只覆盖函数体）。"""
    from hsr_nous.ops.dag import Node, Runner
    calls = []

    def fn(_inputs):
        calls.append(1)
        return "v"

    r = Runner(tmp_path / "r")
    r.add(Node("a", fn, salt="s1"))
    r.run()
    assert len(calls) == 1
    r2 = Runner(tmp_path / "r")
    r2.add(Node("a", fn, salt="s1"))
    r2.run()
    assert len(calls) == 1, "同 salt：缓存命中零重跑"
    r3 = Runner(tmp_path / "r")
    r3.add(Node("a", fn, salt="s2"))
    r3.run()
    assert len(calls) == 2, "salt 变：指纹变 → 缓存失效重跑"


# ---------------------------------------------------------------------------
# compile/smoke 闸语义源 salt（闸 fn 是薄壳——写文件+跑 harness，fn 指纹不覆盖
# 编译器/引擎本体；本体改动靠 _COMPILE_SEMANTIC_SOURCES 内容 hash 经 salt 传导缓存失效）
# ---------------------------------------------------------------------------

def test_compile_semantics_sources_exist_and_gates_salted(tmp_path):
    """承载表六件全在盘上（路径漂移=指纹退化的静默破口，存在性即钉）+
    角色/装备两分支 compile/smoke 四闸同挂该 salt."""
    from hsr_nous.ops.annotator import equipment_nodes as _equip
    from hsr_nous.ops.annotator import nodes as _nodes

    for rel in _nodes._COMPILE_SEMANTIC_SOURCES:
        assert (_nodes.ROOT / rel).is_file(), f"语义承载文件缺失：{rel}"
    want = _nodes._compile_semantics_salt()
    assert want, "salt 非空"
    gates = [
        _nodes.compile_gate_node(1, "c", None, 1, tmp_path, "draft"),
        _nodes._smoke_gate_node(1, "c", None, 1, tmp_path),
        _equip._compile_gate_equipment(1, "relic", "101", None, 1, tmp_path, "draft"),
        _equip._smoke_gate_equipment(1, "relic", "101", None, 1, tmp_path),
    ]
    assert all(g.salt == want for g in gates), "四闸 salt=语义源指纹（同源失效）"


def test_compile_smoke_gate_cache_invalidation(tmp_path, monkeypatch):
    """双闸缓存钉：同输入同语义源 → 重放零重跑；语义源内容变 → 失效重跑
    （借 tmp 文件换入承载表模拟本体改动——不碰真源文件；链：draft→compile1 过
    →smoke1 打回→预算 1 尽→human_queue 终态，harness 全 mock 计数）."""
    from hsr_nous.ops.annotator import nodes as _nodes
    from hsr_nous.ops.dag import Node, Runner

    calls = {"check": 0, "smoke": 0}

    def fake_run_check(_path, mode):
        calls[mode] += 1
        return (True, "PASS") if mode == "check" else (False, "FAIL 冒烟炸")

    monkeypatch.setattr(_nodes, "_run_check", fake_run_check)

    def build():
        r = Runner(tmp_path / "runs")
        r.add(Node("draft", lambda _i: "actor_id: '9999'\n"))
        r.add(_nodes.compile_gate_node(1, "9999", None, 1, tmp_path / "work", "draft"))
        return r

    build().run()
    assert calls == {"check": 1, "smoke": 1}, "首趟双闸实跑"
    build().run()
    assert calls == {"check": 1, "smoke": 1}, "同输入同语义源：双闸缓存命中零重跑"

    probe = tmp_path / "probe.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(_nodes, "_COMPILE_SEMANTIC_SOURCES", (str(probe),))
    build().run()
    assert calls == {"check": 2, "smoke": 2}, "承载表换入 → salt 变 → 双闸失效重跑"
    build().run()
    assert calls == {"check": 2, "smoke": 2}, "换入后同内容：再命中"
    probe.write_text("x = 2\n", encoding="utf-8")
    build().run()
    assert calls == {"check": 3, "smoke": 3}, "承载文件内容变 → 缓存失效重跑"
