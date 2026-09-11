"""通用目标选择代数（B31）：pool → where → order_by → take → mode 一台求值器.

两通道（hook effect `target` / policy `target_rules.selector`）共用；存量字符串与旧 dict
选择器全部**脱糖为代数**（别名表在 `_HOOK_SELECTOR_ALIASES` / `_POLICY_SELECTOR_ALIASES`——
模板零改动，新写法直接用代数 dict）。

- `pool`（仅 hook 通道；policy 池 = 调用方候选集）：`self` / `allies` / `enemies` / `all` /
  `$event.<字段>`（payload 寻址）
- `where`：cerces 表达式（`$it` 绑定候选 + legacy 平铺键 target_hp/target_hp_pct/target_broken）；
  None = 恒真
- `order_by`：cerces 表达式（`$it`），`-` 前缀 = 降序；**全序纪律**：sorted 稳定排序，
  同值按池序（站位序）决胜
- `take`：`"all"` | 整数（取前 N；"first" = take:1 降糖）
- `mode`：`deterministic`（按序取）| `random`（random 仅 zagreus 供种子——roll 抽 N；
  expected 确定化口径 = 按序取前 N，与 B22 期望模式不掷骰纪律一致）

语义边界（owner 拍板）：bounce/repeat（那刻夏弹射、白露 #4[i] 次随机治疗）归结算层
多段实例，**不进**本代数——"选谁"与"选几次"分家。
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Optional

from hsr_nous.sim.pipeline import MODE_ROLL

#: 代数 dict 合法键（编译期闸与文档单一事实源）
TARGET_ALGEBRA_KEYS = frozenset({"pool", "where", "order_by", "take", "mode"})
#: pool 合法值（$event.<字段> 为动态前缀通道）
TARGET_ALGEBRA_POOLS = frozenset({"self", "allies", "enemies", "all"})
#: mode 合法值
TARGET_ALGEBRA_MODES = frozenset({"deterministic", "random"})


def _it_namespace(engine: Any, s: Any) -> Dict[str, Any]:
    """候选上下文（dict 形态，与表达式求值器口径一致）：`$it` 命名空间（actor_id/面板/
    broken/shield（当前护盾值=护盾栈剩余合计——峥嵘"护盾值最低目标"族，2026-09-08）直读，
    has_modifier($it, …) 可经 actor_id 反查）+ legacy 平铺键."""
    eff = engine.pipeline.effective_stats(s)
    return {
        "it": types.SimpleNamespace(
            actor_id=s.actor.actor_id,
            hp=s.current_hp,
            energy=s.current_energy,
            max_hp=float(eff["hp"]),
            max_energy=float(s.actor.stats.max_energy),
            state=(s.state_config.state if s.state_config else ""),
            broken=bool(s.broken),
            alive=bool(s.alive),
            shield=float(sum(x.remaining for x in s.shields)),
            **{k: v for k, v in eff.items() if k not in ("dmg_bonus", "hp")},
        ),
        # legacy 平铺键（policy filter/first 旧条件兼容层）
        "target_hp": s.current_hp,
        "target_hp_pct": s.current_hp / max(s.actor.stats.hp, 1e-6),
        "target_broken": bool(s.broken),
    }


def resolve_pool(spec: Any, *, engine: Any, st: Any, payload: Dict[str, Any]) -> List[Any]:
    """hook 通道池解析：self/allies/enemies/all/$event.<字段> → 候选集."""
    if spec == "self":
        return [st]
    if spec == "allies":
        return [s for s in engine._allies_alive()
                if s.actor.summon_flags.get("ally_targetable", True)]
    if spec == "enemies":
        return engine._enemies_alive()
    if spec == "all":
        return ([s for s in engine._allies_alive()
                 if s.actor.summon_flags.get("ally_targetable", True)]
                + engine._enemies_alive())
    if isinstance(spec, str) and spec.startswith("$event."):
        if spec in ("$event.targets", "$event.hit_targets"):
            return [s for s in (engine.state.actors.get(str(i))
                                for i in payload.get(spec.split(".", 1)[1]) or [])
                    if s is not None and s.alive]
        aid = payload.get(spec.split(".", 1)[1])
        t = engine.state.actors.get(str(aid)) if aid is not None else None
        return [t] if t is not None else []
    raise ValueError(
        f"未知目标代数 pool {spec!r}（合法：{sorted(TARGET_ALGEBRA_POOLS)} + '$event.<字段>'）")


def eval_algebra(
    spec: Dict[str, Any],
    *,
    pool: List[Any],
    engine: Any,
    expr: Any,
) -> List[Any]:
    """代数求值（池已解析）：where 过滤 → order_by 全序 → take 截取 → mode.

    expr：表达式编译器（cerces——ExprCompiler 实例，调用方注入与全链共享 _cache 同实例）。
    """
    where_src = spec.get("where")
    if where_src:
        wex = expr.compile(str(where_src), layer="effect")
        pool = [s for s in pool
                if expr.evaluate(wex, _it_namespace(engine, s),
                                 functions=engine._hooks._hook_functions(s))]
    order_src = spec.get("order_by")
    if order_src:
        order_src = str(order_src)
        desc = order_src.startswith("-")
        oex = expr.compile(order_src[1:] if desc else order_src, layer="effect")
        # sorted 稳定 = 同值按池序（站位序）决胜（B31 全序纪律）
        pool = sorted(
            pool,
            key=lambda s: float(expr.evaluate(
                oex, _it_namespace(engine, s),
                functions=engine._hooks._hook_functions(s))),
            reverse=desc,
        )
    take = spec.get("take", "all")
    n = len(pool) if take == "all" else max(0, min(int(take), len(pool)))
    if spec.get("mode", "deterministic") == "random":
        rng = engine.pipeline.rng
        if engine.pipeline.mode == MODE_ROLL and rng is not None:
            return list(rng.sample(pool, n)) if n < len(pool) else list(pool)
        # expected 确定化口径：按序取前 N（不掷骰——B22 纪律）
        return pool[:n]
    return pool[:n]


# ---------------------------------------------------------------------------
# 存量选择器脱糖别名表（模板零改动——字符串/旧 dict 全部映射到代数）
# ---------------------------------------------------------------------------

#: hook 通道字符串选择器 → 代数（pool 键在 resolve_pool 解析；$event.targets 走既有分支）
_HOOK_SELECTOR_ALIASES: Dict[str, Dict[str, Any]] = {
    "self": {"pool": "self"},
    "all_allies": {"pool": "allies"},
    "other_allies": {"pool": "allies"},   # where 由调用方按 owner 注入（见 _hook_target_states）
    "all_enemies": {"pool": "enemies"},
    "enemy_first": {"pool": "enemies", "take": 1},
    "highest_hp": {"pool": "enemies", "order_by": "-$it.hp", "take": 1},
    "highest_hp_hit": {"pool": "$event.hit_targets", "order_by": "-$it.hp", "take": 1},
}

#: policy 通道字符串选择器 → 代数（池 = 调用方候选集，无 pool 键）
_POLICY_SELECTOR_ALIASES: Dict[str, Dict[str, Any]] = {
    "primary_target": {"take": 1},
    "enemy_single": {"take": 1},
    "all_enemies": {"take": 1},
    "all_allies": {"take": 1},
    "self": {"take": 1},
    "lowest_hp": {"order_by": "$it.hp", "take": 1},
    "lowest_hp_ally": {"order_by": "$it.hp / $it.max_hp", "take": 1},
    "highest_hp": {"order_by": "-$it.hp", "take": 1},
    "lowest_hp_pct": {"order_by": "$it.hp / $it.max_hp", "take": 1},
    "highest_hp_pct": {"order_by": "-$it.hp / $it.max_hp", "take": 1},
    "highest_atk": {"order_by": "-$it.atk", "take": 1},
    "lowest_atk": {"order_by": "$it.atk", "take": 1},
    "highest_spd": {"order_by": "-$it.spd", "take": 1},
    "lowest_spd": {"order_by": "$it.spd", "take": 1},
    "broken": {"where": "$it.broken", "take": 1},
    "highest_break": {"order_by": "-$it.break_effect", "take": 1},
    "random": {"take": 1, "mode": "random"},
}

#: policy 旧 dict 形态 → 代数（type 键脱糖）
_POLICY_DICT_TYPE_ALIASES: Dict[str, str] = {
    "min": "order_by",
    "max": "-order_by",
}


def desugar_policy_legacy(sel: Any) -> Dict[str, Any]:
    """policy 旧形态（字符串 / type dict）→ 代数 dict；已是代数 dict 原样返回."""
    if isinstance(sel, str):
        hit = _POLICY_SELECTOR_ALIASES.get(sel)
        if hit is None:
            raise ValueError(
                f"未知 policy target 选择器 {sel!r}（合法集合：{sorted(_POLICY_SELECTOR_ALIASES)}）")
        return dict(hit)
    if isinstance(sel, dict):
        if set(sel) & TARGET_ALGEBRA_KEYS:
            return dict(sel)   # 已是代数形态
        t = sel.get("type")
        key = sel.get("key", "current_hp")
        key_expr = {"current_hp": "$it.hp", "hp_pct": "$it.hp / $it.max_hp",
                    "stats.atk": "$it.atk", "stats.spd": "$it.spd",
                    "stats.break_effect": "$it.break_effect"}.get(key, "$it.hp")
        if t == "min":
            return {"order_by": key_expr, "take": 1}
        if t == "max":
            return {"order_by": f"-{key_expr}", "take": 1}
        if t == "random":
            return {"take": 1, "mode": "random"}
        if t == "has_modifier":
            mid = str(sel.get("modifier_id", ""))
            return {"where": f"has_modifier($it, '{mid}')", "take": 1}
        if t == "filter":
            return {"where": str(sel.get("condition", "true")), "take": "all"}
        if t == "first":
            return {"where": str(sel.get("condition", "true")), "take": 1}
        raise ValueError(
            f"未知 policy target 参数化选择器 type {t!r}"
            f"（合法：min/max/random/has_modifier/filter/first 或代数键 {sorted(TARGET_ALGEBRA_KEYS)}）")
    raise ValueError(f"policy target 选择器须为字符串或参数化 dict，收到 {type(sel).__name__}：{sel!r}")


def validate_algebra(spec: Dict[str, Any], *, where: str, expr: Any,
                     allow_pool: bool) -> None:
    """代数 dict 编译期闸（两通道共用）：键 diff + pool/take/mode 词表 + where/order_by 预编译."""
    unknown = set(spec) - TARGET_ALGEBRA_KEYS
    if unknown:
        raise ValueError(
            f"{where} 目标代数含未知键 {sorted(unknown)}（合法集合：{sorted(TARGET_ALGEBRA_KEYS)}）")
    if "pool" in spec:
        if not allow_pool:
            raise ValueError(f"{where} 不允许 pool 键（policy 池由行动 target_type 决定）")
        p = spec["pool"]
        if p not in TARGET_ALGEBRA_POOLS and not str(p).startswith("$event."):
            raise ValueError(
                f"{where} 非法 pool {p!r}（合法：{sorted(TARGET_ALGEBRA_POOLS)} + '$event.<字段>'）")
    take = spec.get("take", "all")
    if take != "all" and not (isinstance(take, int) and take >= 1):
        raise ValueError(f"{where} take 非法值 {take!r}（合法：'all' 或 ≥1 整数）")
    mode = spec.get("mode", "deterministic")
    if mode not in TARGET_ALGEBRA_MODES:
        raise ValueError(
            f"{where} 非法 mode {mode!r}（合法：{sorted(TARGET_ALGEBRA_MODES)}）")
    for slot in ("where", "order_by"):
        src = spec.get(slot)
        if src:
            expr.compile(str(src).lstrip("-"), layer="effect")   # 非法表达式编译期炸（B8 同口径）
