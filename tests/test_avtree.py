"""avtree 对拍测试：随机操作序列 vs 参考 sorted list（对拍法 B22）.

红黑树删除分支是经典翻车点——本测试就是设计文档里"无此测试不交付"的那道闸：
- property test：多种子 × 随机操作序列，每步校验五条不变量 + 与参考实现逐键全等
- 确定性冒烟：手排序列的基本行为
"""
from __future__ import annotations

import bisect
import random

import pytest

from hsr_nous.sim.avtree import AVTree


def _smoke():
    t = AVTree()
    t.insert(100.0, 0, 1)
    t.insert(50.0, 0, 2)
    t.insert(50.0, 1, 3)  # 同刻 tie_break 决定先后
    assert t.peek_min() == (50.0, 0, 2)
    assert t.pop_min() == (50.0, 0, 2)
    assert t.peek_min() == (50.0, 1, 3)
    t.update_key(3, 200.0, 0)  # 推条
    assert t.peek_min() == (100.0, 0, 1)
    t.update_key(3, 25.0, 0)   # 拉条
    assert t.peek_min() == (25.0, 0, 3)
    assert len(t) == 2  # 实体 2 已被 pop_min 弹出，存活 = {1, 3}
    t.assert_invariants()


def _snapshot_equality():
    a, b = AVTree(), AVTree()
    for i, (tm, ent) in enumerate([(90.0, 1), (30.0, 2), (60.0, 3)]):
        a.insert(tm, 0, ent)
        b.insert(tm, 0, ent)
    assert a.snapshot() == b.snapshot(), "同构两树 snapshot 必须逐字段全等（纯净不变量）"
    b.pop_min()
    assert a.snapshot() != b.snapshot()


def _property_random_ops(seed: int, rounds: int = 4000) -> None:
    """随机操作序列 vs 参考 sorted list（实体集合与键序双对拍）."""
    rng = random.Random(seed)
    tree = AVTree()
    ref: list[tuple[float, int, int, int]] = []  # (time, tie, seq, entity)，bisect 保序
    alive: dict[int, tuple[float, int, int]] = {}  # entity → (time, tie, seq)
    ref_seq = 1

    def ref_inorder():
        return [(tm, tie, ent) for tm, tie, _s, ent in ref]

    for step in range(rounds):
        op = rng.choices(["insert", "delete", "update", "pop"], weights=[5, 3, 3, 1])[0]

        if op == "insert" or (op == "update" and not alive):
            ent = rng.randint(1, 64)
            if ent in alive:
                ent = max(alive, default=0) + 1
            tm = round(rng.uniform(0, 500), 2)
            tie = rng.randint(0, 1)
            tree.insert(tm, tie, ent)
            bisect.insort(ref, (tm, tie, ref_seq, ent))
            alive[ent] = (tm, tie, ref_seq)
            ref_seq += 1
        elif op == "delete" and alive:
            ent = rng.choice(list(alive))
            tree.delete(ent)
            tm, tie, s = alive.pop(ent)
            ref.remove((tm, tie, s, ent))
        elif op == "update" and alive:
            ent = rng.choice(list(alive))
            tm_old, tie_old, s_old = alive.pop(ent)
            ref.remove((tm_old, tie_old, s_old, ent))
            tm = round(rng.uniform(0, 500), 2)
            tie = rng.randint(0, 1)
            tree.update_key(ent, tm, tie)
            bisect.insort(ref, (tm, tie, ref_seq, ent))
            alive[ent] = (tm, tie, ref_seq)
            ref_seq += 1
        elif op == "pop" and alive:
            got = tree.pop_min()
            want = ref.pop(0)
            assert got == (want[0], want[1], want[3]), (
                f"seed={seed} step={step}: pop_min {got} != 参考 {want}"
            )
            alive.pop(want[3])

        # 每步双对拍 + 五条不变量
        tree.assert_invariants()
        assert tree.ordered() == ref_inorder(), (
            f"seed={seed} step={step} op={op}: 中序与参考不一致\n"
            f"tree: {tree.ordered()}\nref:  {ref_inorder()}"
        )
        assert len(tree) == len(alive)


@pytest.mark.parametrize("seed", [1, 7, 42, 20260821])
def test_avtree(seed: int) -> None:
    _smoke()
    _snapshot_equality()
    _property_random_ops(seed)
