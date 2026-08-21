"""数组化红黑树（行动值调度器的有序平衡树，Linux CFS 同构）.

节点池 = 平行数组（索引非指针）：整树状态即若干根数组，snapshot / 回放 /
逐字段比对免费（纯净不变量要求全状态可序列化）。

键 = (time, tie_break, seq) 全序元组：
- time：绝对时刻（全局时钟）
- tie_break：同刻次序（我方先于敌方、编队位小者先）
- seq：插入序号，单调递增——保证键全局唯一，无需处理重复键

实体→节点索引映射：拉条/推条改键 O(1) 定位（先删后插）。

参照 CLRS《算法导论》红黑树章（公共学术知识，无代码抄录）。
"""
from __future__ import annotations

BLACK, RED = 0, 1
NIL = 0  # 哨兵节点索引：黑色，所有链接指向自身（0）

__all__ = ["AVTree", "NIL"]


class AVTree:
    """数组化红黑树。实体为整数句柄（符号解析期分配）."""

    def __init__(self) -> None:
        # 槽 0 固定为 NIL 哨兵
        self._time: list[float] = [0.0]
        self._tie: list[int] = [0]
        self._seq: list[int] = [0]
        self._entity: list[int] = [-1]
        self._left: list[int] = [NIL]
        self._right: list[int] = [NIL]
        self._parent: list[int] = [NIL]
        self._color: list[int] = [BLACK]
        self._root: int = NIL
        self._free: list[int] = []           # 回收的节点槽
        self._entity_map: dict[int, int] = {}  # 实体 → 节点索引
        self._next_seq: int = 1

    # ------------------------------------------------------------------
    # 键序与基础操作
    # ------------------------------------------------------------------

    def _less(self, a: int, b: int) -> bool:
        return (self._time[a], self._tie[a], self._seq[a]) < (
            self._time[b],
            self._tie[b],
            self._seq[b],
        )

    def _alloc(self) -> int:
        if self._free:
            return self._free.pop()
        for arr in (self._time, self._tie, self._seq, self._entity,
                    self._left, self._right, self._parent, self._color):
            arr.append(type(arr[0])())
        return len(self._color) - 1

    def _release(self, x: int) -> None:
        self._left[x] = self._right[x] = self._parent[x] = NIL
        self._color[x] = BLACK
        self._entity[x] = -1
        self._free.append(x)

    def _minimum(self, x: int) -> int:
        while self._left[x] != NIL:
            x = self._left[x]
        return x

    def __len__(self) -> int:
        return len(self._entity_map)

    def __contains__(self, entity: int) -> bool:
        return entity in self._entity_map

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def peek_min(self) -> tuple[float, int, int]:
        """返回最左节点的 (time, tie_break, entity)；空树抛 IndexError."""
        if self._root == NIL:
            raise IndexError("peek_min on empty AVTree")
        x = self._minimum(self._root)
        return (self._time[x], self._tie[x], self._entity[x])

    def ordered(self) -> list[tuple[float, int, int]]:
        """中序遍历 = 行动条预览 [(time, tie_break, entity), ...]（升序）."""
        out: list[tuple[float, int, int]] = []
        stack: list[int] = []
        x = self._root
        while stack or x != NIL:
            while x != NIL:
                stack.append(x)
                x = self._left[x]
            x = stack.pop()
            out.append((self._time[x], self._tie[x], self._entity[x]))
            x = self._right[x]
        return out

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def insert(self, time: float, tie: int, entity: int) -> None:
        """插入调度实体；entity 重复 = ValueError."""
        if entity in self._entity_map:
            raise ValueError(f"entity {entity} 已在树中")
        z = self._alloc()
        self._time[z] = time
        self._tie[z] = tie
        self._seq[z] = self._next_seq
        self._next_seq += 1
        self._entity[z] = entity
        self._left[z] = self._right[z] = NIL
        self._entity_map[entity] = z

        # 标准 BST 插入
        y, x = NIL, self._root
        while x != NIL:
            y = x
            x = self._left[x] if self._less(z, x) else self._right[x]
        self._parent[z] = y
        if y == NIL:
            self._root = z
        elif self._less(z, y):
            self._left[y] = z
        else:
            self._right[y] = z
        self._color[z] = RED
        self._insert_fixup(z)

    def delete(self, entity: int) -> None:
        """删除调度实体；entity 不存在 = KeyError."""
        z = self._entity_map.pop(entity, None)
        if z is None:
            raise KeyError(f"entity {entity} 不在树中")
        y, y_original_color = z, self._color[z]
        if self._left[z] == NIL:
            x = self._right[z]
            self._transplant(z, self._right[z])
        elif self._right[z] == NIL:
            x = self._left[z]
            self._transplant(z, self._left[z])
        else:
            y = self._minimum(self._right[z])
            y_original_color = self._color[y]
            x = self._right[y]
            if self._parent[y] == z:
                self._parent[x] = y
            else:
                self._transplant(y, self._right[y])
                self._right[y] = self._right[z]
                self._parent[self._right[y]] = y
            self._transplant(z, y)
            self._left[y] = self._left[z]
            self._parent[self._left[y]] = y
            self._color[y] = self._color[z]
        if y_original_color == BLACK:
            self._delete_fixup(x)
        self._release(z)

    def update_key(self, entity: int, time: float, tie: int) -> None:
        """拉条/推条 = 删旧键插新键."""
        self.delete(entity)
        self.insert(time, tie, entity)

    def pop_min(self) -> tuple[float, int, int]:
        """弹出最左节点并返回 (time, tie_break, entity)."""
        if self._root == NIL:
            raise IndexError("pop_min on empty AVTree")
        x = self._minimum(self._root)
        entry = (self._time[x], self._tie[x], self._entity[x])
        self.delete(self._entity[x])
        return entry

    # ------------------------------------------------------------------
    # 旋转与修正（CLRS）
    # ------------------------------------------------------------------

    def _rotate_left(self, x: int) -> None:
        y = self._right[x]
        self._right[x] = self._left[y]
        if self._left[y] != NIL:
            self._parent[self._left[y]] = x
        self._parent[y] = self._parent[x]
        if self._parent[x] == NIL:
            self._root = y
        elif x == self._left[self._parent[x]]:
            self._left[self._parent[x]] = y
        else:
            self._right[self._parent[x]] = y
        self._left[y] = x
        self._parent[x] = y

    def _rotate_right(self, x: int) -> None:
        y = self._left[x]
        self._left[x] = self._right[y]
        if self._right[y] != NIL:
            self._parent[self._right[y]] = x
        self._parent[y] = self._parent[x]
        if self._parent[x] == NIL:
            self._root = y
        elif x == self._right[self._parent[x]]:
            self._right[self._parent[x]] = y
        else:
            self._left[self._parent[x]] = y
        self._right[y] = x
        self._parent[x] = y

    def _insert_fixup(self, z: int) -> None:
        while self._color[self._parent[z]] == RED:
            if self._parent[z] == self._left[self._parent[self._parent[z]]]:
                y = self._right[self._parent[self._parent[z]]]  # 叔叔
                if self._color[y] == RED:
                    self._color[self._parent[z]] = BLACK
                    self._color[y] = BLACK
                    self._color[self._parent[self._parent[z]]] = RED
                    z = self._parent[self._parent[z]]
                else:
                    if z == self._right[self._parent[z]]:
                        z = self._parent[z]
                        self._rotate_left(z)
                    self._color[self._parent[z]] = BLACK
                    self._color[self._parent[self._parent[z]]] = RED
                    self._rotate_right(self._parent[self._parent[z]])
            else:
                y = self._left[self._parent[self._parent[z]]]
                if self._color[y] == RED:
                    self._color[self._parent[z]] = BLACK
                    self._color[y] = BLACK
                    self._color[self._parent[self._parent[z]]] = RED
                    z = self._parent[self._parent[z]]
                else:
                    if z == self._left[self._parent[z]]:
                        z = self._parent[z]
                        self._rotate_right(z)
                    self._color[self._parent[z]] = BLACK
                    self._color[self._parent[self._parent[z]]] = RED
                    self._rotate_left(self._parent[self._parent[z]])
        self._color[self._root] = BLACK

    def _transplant(self, u: int, v: int) -> None:
        if self._parent[u] == NIL:
            self._root = v
        elif u == self._left[self._parent[u]]:
            self._left[self._parent[u]] = v
        else:
            self._right[self._parent[u]] = v
        self._parent[v] = self._parent[u]

    def _delete_fixup(self, x: int) -> None:
        while x != self._root and self._color[x] == BLACK:
            if x == self._left[self._parent[x]]:
                w = self._right[self._parent[x]]  # 兄弟
                if self._color[w] == RED:
                    self._color[w] = BLACK
                    self._color[self._parent[x]] = RED
                    self._rotate_left(self._parent[x])
                    w = self._right[self._parent[x]]
                if self._color[self._left[w]] == BLACK and self._color[self._right[w]] == BLACK:
                    self._color[w] = RED
                    x = self._parent[x]
                else:
                    if self._color[self._right[w]] == BLACK:
                        self._color[self._left[w]] = BLACK
                        self._color[w] = RED
                        self._rotate_right(w)
                        w = self._right[self._parent[x]]
                    self._color[w] = self._color[self._parent[x]]
                    self._color[self._parent[x]] = BLACK
                    self._color[self._right[w]] = BLACK
                    self._rotate_left(self._parent[x])
                    x = self._root
            else:
                w = self._left[self._parent[x]]
                if self._color[w] == RED:
                    self._color[w] = BLACK
                    self._color[self._parent[x]] = RED
                    self._rotate_right(self._parent[x])
                    w = self._left[self._parent[x]]
                if self._color[self._right[w]] == BLACK and self._color[self._left[w]] == BLACK:
                    self._color[w] = RED
                    x = self._parent[x]
                else:
                    if self._color[self._left[w]] == BLACK:
                        self._color[self._right[w]] = BLACK
                        self._color[w] = RED
                        self._rotate_left(w)
                        w = self._left[self._parent[x]]
                    self._color[w] = self._color[self._parent[x]]
                    self._color[self._parent[x]] = BLACK
                    self._color[self._left[w]] = BLACK
                    self._rotate_right(self._parent[x])
                    x = self._root
        self._color[x] = BLACK

    # ------------------------------------------------------------------
    # 序列化与自校验
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """整树状态 = 纯数据（可 JSON 序列化、可逐字段比对）."""
        return {
            "time": list(self._time),
            "tie": list(self._tie),
            "seq": list(self._seq),
            "entity": list(self._entity),
            "left": list(self._left),
            "right": list(self._right),
            "parent": list(self._parent),
            "color": list(self._color),
            "root": self._root,
            "free": list(self._free),
            "entity_map": dict(self._entity_map),
            "next_seq": self._next_seq,
        }

    def assert_invariants(self) -> None:
        """红黑树五条不变量自校验（debug；违反即 AssertionError）."""
        assert self._color[NIL] == BLACK, "NIL 必须为黑"
        if self._root == NIL:
            assert not self._entity_map, "空树但 entity_map 非空"
            return
        assert self._color[self._root] == BLACK, "根必须为黑"

        # BST 有序（中序升序，用内部比较器逐对检查）
        indices: list[int] = []
        stack: list[int] = []
        x = self._root
        while stack or x != NIL:
            while x != NIL:
                stack.append(x)
                x = self._left[x]
            x = stack.pop()
            indices.append(x)
            x = self._right[x]
        for prev, cur in zip(indices, indices[1:]):
            assert self._less(prev, cur), f"BST 键序被破坏：节点 {prev} 不小于 {cur}"

        def walk(x: int) -> int:
            """返回黑高；顺带校验红色不相邻与黑高一致."""
            if x == NIL:
                return 1  # NIL 计一个黑
            if self._color[x] == RED:
                assert self._color[self._left[x]] == BLACK, f"红节点 {x} 左子为红"
                assert self._color[self._right[x]] == BLACK, f"红节点 {x} 右子为红"
            lh, rh = walk(self._left[x]), walk(self._right[x])
            assert lh == rh, f"节点 {x} 左右黑高不等 {lh} != {rh}"
            return lh + (1 if self._color[x] == BLACK else 0)

        walk(self._root)
