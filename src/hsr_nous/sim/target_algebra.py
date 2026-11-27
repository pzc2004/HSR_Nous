"""通用目标选择代数：pool → where → order_by → index → take → mode 一台求值器.

两通道（hook effect `target` / policy `target_rules.selector`）共用；存量字符串与旧 dict
选择器全部**脱糖为代数**（别名表在 `_HOOK_SELECTOR_ALIASES` / `_POLICY_SELECTOR_ALIASES`——
模板零改动，新写法直接用代数 dict）。

- `pool`（仅 hook 通道；policy 池 = 调用方候选集）：`self` / `allies` / `enemies` /
  `enemy_targets`（敌方攻击的我方候选）/ `all` / `$event.<字段>`（payload 寻址）
- `where`：cerces 表达式（`$it` 绑定候选 + legacy 平铺键 target_hp/target_hp_pct/target_broken）；
  None = 恒真
- `order_by`：cerces 表达式（`$it`），`-` 前缀 = 降序；**全序纪律**：sorted 稳定排序，
  同值按池序（站位序）决胜；特殊键 `formation` / `-formation` = 池序原样 / 反转编队序
- `index`：非负整数，精确选择过滤、排序后的第 N 项（从 0 起），越界为空
- `take`：`"all"` | 整数（取前 N；"first" = take:1 降糖）
- `mode`：`deterministic`（按序取）| `random`（roll 抽 N；expected 按序取前 N）|
  `shuffle`（roll 全取也做全排列；expected 保持原序）| `taunt_or_random` / `taunt_or_aggro`
  （仅 hook 单目标：嘲讽/锁定优先，否则分别均匀抽取或按有效嘲讽值加权）

语义边界（拍板）：bounce/repeat（那刻夏弹射、白露 #4[i] 次随机治疗）归结算层
多段实例，**不进**本代数——"选谁"与"选几次"分家。
"""
from __future__ import annotations

import types
from typing import Any, Dict, List, Optional

from hsr_nous.sim.pipeline import MODE_ROLL

#: 代数 dict 合法键（编译期闸与文档单一事实源）
TARGET_ALGEBRA_KEYS = frozenset({
    "pool", "where", "order_by", "index", "take", "mode", "include_dead", "include_unselectable", "include_summons", "pre_shuffle", "concat"})
#: pool 合法值（$event.<字段> 为动态前缀通道）
TARGET_ALGEBRA_POOLS = frozenset({
    "self", "allies", "enemies", "enemy_targets", "all", "all_with_battle_events",
    "battle_events", "unselectable", "last_summons", "$level", "$light_team", "$dark_team"})
#: mode 合法值
TARGET_ALGEBRA_MODES = frozenset({"deterministic", "random", "shuffle", "taunt_or_random", "taunt_or_aggro"})
UNIQUE_TARGET_PREFIX = "unique:"


def unique_target_id(engine: Any, name: Any) -> str:
    runtime = engine._enemy_policy_state.get("$level") or {}
    return str((runtime.get("dynamic_targets") or {}).get(str(name)) or "")


def battle_event_actor(engine: Any, actor_id: Any) -> Any:
    for payload in engine.battle_events.values():
        state = payload.get("actor_state")
        if state is not None and state.actor.actor_id == str(actor_id):
            return state
    return None


def unique_target_actor(engine: Any, name: Any) -> Any:
    actor_id = unique_target_id(engine, name)
    return engine.state.actors.get(actor_id) or battle_event_actor(engine, actor_id)


def _it_namespace(engine: Any, s: Any) -> Dict[str, Any]:
    """候选上下文（dict 形态，与表达式求值器口径一致）：`$it` 命名空间（actor_id/面板/
    broken/shield（当前护盾值=护盾栈剩余合计——峥嵘"护盾值最低目标"族，2026-09-08）/
    summoner_id（召唤物反指召唤者——"召唤物 of X"寻址，星期日 131302 族，2026-09-09；
    非召唤物为空串）直读，has_modifier($it, …) 可经 actor_id 反查）+ legacy 平铺键."""
    eff = engine.pipeline.effective_stats(s)
    # 开放命名空间防撞：eff 的自定义 stat 键（如模板把 "max_hp" 当 stat_effects 键——
    # 1208 打标实证）与显式键撞名时**显式键胜**（面板口径唯一事实源；先铺开放键再盖显式键，
    # SimpleNamespace(**显式, **eff) 形态会 TypeError 撞键炸）
    ns = {k: v for k, v in eff.items() if k not in ("dmg_bonus", "hp")}
    ns.update(
        actor_id=s.actor.actor_id,
        name=s.actor.name,
        hp=s.current_hp,
        energy=s.current_energy,
        max_hp=float(eff["hp"]),
        max_energy=float(s.actor.stats.max_energy),
        state=(s.state_config.state if s.state_config else ""),
        broken=bool(s.broken),
        alive=bool(s.alive),
        shield=float(sum(x.remaining for x in s.shields)),
        summoner_id=str(s.actor.summoner_id or ""),
        banished=bool(s.banished),
        enemy_targetable=bool(s.actor.summon_flags.get("enemy_targetable", True)),
        ally_targetable=bool(s.actor.summon_flags.get("ally_targetable", True)),
    )
    return {
        "it": types.SimpleNamespace(**ns),
        # legacy 平铺键（policy filter/first 旧条件兼容层）
        "target_hp": s.current_hp,
        "target_hp_pct": s.current_hp / max(s.actor.stats.hp, 1e-6),
        "target_broken": bool(s.broken),
    }


def resolve_pool(spec: Any, *, engine: Any, st: Any, payload: Dict[str, Any],
                 include_dead: bool = False, include_unselectable: bool = False) -> List[Any]:
    """hook 通道池解析：self/allies/enemies/all/$event.<字段>/unique:<名称> → 候选集."""
    if spec in {"$level", "$light_team", "$dark_team"}:
        target = engine._pseudo_entity_state(spec)
        return [target] if target is not None and (include_dead or target.alive) else []
    if spec == "self":
        return [st]
    if spec == "unselectable":
        candidates = resolve_pool(
            "all_with_battle_events", engine=engine, st=st, payload=payload,
            include_dead=include_dead, include_unselectable=True)
        return [s for s in candidates
                if s.actor.actor_type == "battle_event"
                or not s.actor.summon_flags.get("enemy_targetable", True)
                or not s.actor.summon_flags.get("ally_targetable", True)]
    if spec == "battle_events":
        return [payload.get("actor_state") for payload in engine.battle_events.values()
                if payload.get("actor_state") is not None
                and (include_dead or payload["actor_state"].alive)]
    if spec == "last_summons":
        result = []
        for actor_id in engine.state.last_summon_ids:
            state = engine.state.actors.get(actor_id) or battle_event_actor(engine, actor_id)
            if state is not None and (include_dead or state.alive):
                result.append(state)
        return result
    if spec == "all_with_battle_events":
        return resolve_pool("all", engine=engine, st=st, payload=payload,
                            include_dead=include_dead,
                            include_unselectable=include_unselectable) + resolve_pool(
                                "battle_events", engine=engine, st=st, payload=payload,
                                include_dead=include_dead,
                                include_unselectable=include_unselectable)
    if include_dead and spec in {"allies", "enemies", "all"}:
        want_enemy = spec != "allies"
        return [state for state in engine.state.actors.values()
                if spec == "all" or engine._is_enemy(state.actor) == want_enemy]
    if spec == "enemy_targets":
        return [s for s in engine._allies_alive()
                if include_unselectable or s.actor.summon_flags.get("enemy_targetable", True)]
    if spec == "allies":
        return [s for s in engine._allies_alive()
                if include_unselectable or s.actor.summon_flags.get("ally_targetable", True)]
    if spec == "enemies":
        if include_unselectable:
            return [s for s in engine._enemies_alive() if not s.banished]
        return engine._hostile_target_pool(st.actor)
    if spec == "all":
        return ([s for s in engine._allies_alive()
                 if include_unselectable or s.actor.summon_flags.get("ally_targetable", True)]
                + ([s for s in engine._enemies_alive() if not s.banished]
                   if include_unselectable else engine._hostile_target_pool(st.actor)))
    if isinstance(spec, str) and spec.startswith(UNIQUE_TARGET_PREFIX):
        target = unique_target_actor(engine, spec[len(UNIQUE_TARGET_PREFIX):])
        return [target] if target is not None else []
    if isinstance(spec, str) and spec.startswith("$event."):
        if spec in ("$event.targets", "$event.hit_targets"):
            return [s for s in (engine.state.actors.get(str(i))
                                for i in payload.get(spec.split(".", 1)[1]) or [])
                    if s is not None and (include_dead or s.alive)]
        aid = payload.get(spec.split(".", 1)[1])
        t = aid if hasattr(aid, "actor") and hasattr(aid, "alive") else (
            (engine.state.actors.get(str(aid)) or battle_event_actor(engine, aid))
            if aid is not None else None)
        return [t] if t is not None else []
    raise ValueError(
        f"未知目标代数 pool {spec!r}（合法：{sorted(TARGET_ALGEBRA_POOLS)} + '$event.<字段>' + 'unique:<名称>'；伪实体键见文档）")


def eval_algebra(
    spec: Dict[str, Any],
    *,
    pool: List[Any],
    engine: Any,
    expr: Any,
    event_ns: Any = None,
    self_ns: Any = None,
) -> List[Any]:
    """代数求值（池已解析）：where 过滤 → order_by 全序 → index 精确选择 → take 截取 → mode.

    expr：表达式编译器（cerces——ExprCompiler 实例，调用方注入与全链共享 _cache 同实例）。
    event_ns：hook 通道 `$event` 注入（与 hook condition 同 payload 命名空间——
    "召唤物 of $event.target" 族，2026-09-09 接线；policy 通道无事件语境不传）。
    self_ns：hook 通道 `$self` 注入（=hook 持有者，与 hook condition/cond 光环域同
    口径——"$it.summoner_id == $self.actor_id"「装备者的忆灵」寻址族，2026-09-16 接线；
    policy 通道不传）。
    """
    def _ctx(s: Any) -> Dict[str, Any]:
        ctx = _it_namespace(engine, s)
        if event_ns is not None:
            ctx["event"] = event_ns
        if self_ns is not None:
            ctx["self"] = self_ns
        ctx["light_team"] = engine._team_entity_state("TeamLight")
        ctx["dark_team"] = engine._team_entity_state("TeamDark")
        return ctx

    def _functions(s: Any) -> Dict[str, Any]:
        functions = dict(engine._hooks._hook_functions(
            s, vars(event_ns) if event_ns is not None else {}))
        owner = getattr(self_ns, "_st", None) or s
        functions["count_selected"] = (
            lambda pool, where="true", include_unselectable=False:
                engine._hooks._count_selected_with_self(
                    pool, where, self_ns, owner, event_ns, include_unselectable))
        return functions

    where_src = spec.get("where")
    if where_src and str(where_src).strip() not in {"true", "True"}:
        wex = expr.compile(str(where_src), layer="effect")
        pool = [s for s in pool if expr.evaluate(wex, _ctx(s), functions=_functions(s))]
    if spec.get("include_summons"):
        base_ids = {s.actor.actor_id for s in pool}
        existing = set(base_ids)
        pool = pool + [s for s in engine.state.actors.values()
                       if s.alive and s.actor.summoner_id in base_ids and s.actor.actor_id not in existing]
    if spec.get("pre_shuffle") and engine.pipeline.mode == MODE_ROLL and engine.pipeline.rng is not None:
        pool = list(engine.pipeline.rng.sample(pool, len(pool)))
    order_src = spec.get("order_by")
    if order_src:
        order_src = str(order_src)
        if order_src in {"formation", "-formation"}:
            # 编队序（非表达式键）：池序即编队序，负号仅反转，供左右横扫族复用。
            if order_src == "-formation":
                pool = list(reversed(pool))
            order_src = ""
        else:
            desc = order_src.startswith("-")
            oex = expr.compile(order_src[1:] if desc else order_src, layer="effect")
            # sorted 稳定 = 同值按池序（站位序）决胜（全序纪律）
            pool = sorted(
                pool,
                key=lambda s: float(expr.evaluate(oex, _ctx(s), functions=_functions(s))),
                reverse=desc,
            )
    if "index" in spec:
        index = spec["index"]
        pool = [pool[index]] if 0 <= index < len(pool) else []
    take = spec.get("take", "all")
    if isinstance(take, str) and take != "all":
        owner = getattr(self_ns, "_st", None) or (pool[0] if pool else None)
        functions = engine._hooks._hook_functions(owner) if owner is not None else {}
        take_ctx = {}
        if event_ns is not None:
            take_ctx["event"] = event_ns
        if self_ns is not None:
            take_ctx["self"] = self_ns
        value = expr.evaluate(expr.compile(take, layer="effect"), take_ctx, functions=functions)
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or value < 0 or int(value) != value:
            raise ValueError(f"take 表达式须返回非负整数，得到 {value!r}")
        take = int(value)
    n = len(pool) if take == "all" else max(0, min(int(take), len(pool)))
    mode = spec.get("mode", "deterministic")
    if mode in {"taunt_or_random", "taunt_or_aggro"}:
        # 判声明的 take 而非裁剪后的 n：take:1 + 空池应返回空，不是误炸（F06）
        if take != 1:
            raise ValueError(f"{mode} 仅支持 take: 1，得到 {take!r}")
        if not pool:
            return []
        owner = getattr(self_ns, "_st", None)
        if owner is None:
            raise ValueError(f"{mode} 需要 hook 持有者作为攻击者语境")
        picked = engine._pick_ally_target(
            owner, candidates=pool, random_by_aggro=(mode == "taunt_or_aggro"))
        return [picked] if picked is not None else []
    if mode in {"random", "shuffle"}:
        rng = engine.pipeline.rng
        if engine.pipeline.mode == MODE_ROLL and rng is not None:
            if mode == "shuffle" or n < len(pool):
                return list(rng.sample(pool, n))
            return list(pool)
        # expected 确定化口径：按序取前 N（不掷骰）
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
    if "concat" in spec:
        if not allow_pool:
            raise ValueError(f"{where} concat 仅支持 hook 通道")
        if set(spec) & {"pool", "include_dead", "include_unselectable"}:
            raise ValueError(f"{where} concat 外层仅支持 where/order_by/index/take/mode，pool/include_* 请放子目标")
        children = spec["concat"]
        if not isinstance(children, list) or not children:
            raise ValueError(f"{where} concat 须为非空目标数组")
        for index, child in enumerate(children):
            if not isinstance(child, dict):
                raise ValueError(f"{where} concat[{index}] 不是目标代数对象")
            validate_algebra(child, where=f"{where} concat[{index}]", expr=expr,
                             allow_pool=allow_pool)
    if "pool" in spec:
        if not allow_pool:
            raise ValueError(f"{where} 不允许 pool 键（policy 池由行动 target_type 决定）")
        p = spec["pool"]
        if (p not in TARGET_ALGEBRA_POOLS and not str(p).startswith("$event.")
                and not str(p).startswith(UNIQUE_TARGET_PREFIX)):
            raise ValueError(
                f"{where} 非法 pool {p!r}（合法：{sorted(TARGET_ALGEBRA_POOLS)} + '$event.<字段>' + 'unique:<名称>'）")
    index = spec.get("index")
    if index is not None and (not isinstance(index, int) or isinstance(index, bool) or index < 0):
        raise ValueError(f"{where} index 须为非负整数，得到 {index!r}")
    take = spec.get("take", "all")
    if take != "all" and not (isinstance(take, int) and take >= 1):
        if isinstance(take, str):
            if "$it." in take:
                raise ValueError(f"{where} take 不能引用 `$it`（动态截取无候选命名空间）")
            expr.compile(take, layer="effect")
        else:
            raise ValueError(f"{where} take 非法值 {take!r}（合法：'all'、≥1 整数或表达式）")
    mode = spec.get("mode", "deterministic")
    if mode not in TARGET_ALGEBRA_MODES:
        raise ValueError(
            f"{where} 非法 mode {mode!r}（合法：{sorted(TARGET_ALGEBRA_MODES)}）")
    if mode in {"taunt_or_random", "taunt_or_aggro"}:
        if not allow_pool:
            raise ValueError(f"{where} {mode} 仅支持有攻击者语境的 hook 通道")
        if take != 1:
            raise ValueError(f"{where} {mode} 仅支持 take: 1，得到 {take!r}")
    for slot in ("where", "order_by"):
        src = spec.get(slot)
        if src and (slot != "order_by" or str(src) not in {"formation", "-formation"}):
            expr.compile(str(src).lstrip("-"), layer="effect")   # 非法表达式编译期炸（B8 同口径）
