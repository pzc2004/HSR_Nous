"""真·全状态存档与恢复（名册席 kephale/全世之座——落盘快照/跨局恢复，见 sim/README.md）.

与 `BattleState.snapshot()`（state.py）两态并存、互不替代：
- snapshot() = round-4 位取舍的**两局全等比对投影**（回归钉专用），不含调度器/
  RNG 流位置/引擎运行期字段，无恢复对偶——一行不动；
- 本模块 = **真存档通道**：`save_engine()` 产纯数据 dict（`json.dumps` 直接序列化，
  含 `save_version` 格式版本号），`restore_into()` 把存档注入 `from_compiled` 同路
  重建的引擎骨架——恢复后直接 `step()`/`run()` 续跑，世界线逐字段全等。

恢复纪律（重建不重新结算）：
- 骨架重建走 `CombatEngine.from_compiled`（编译产物——encounter/actions/hooks/策略/
  资源声明/形态注册表全部由它重带，不进存档）；
- **`_init_state` 不重跑**——初始 modifier 挂载/进战能量发放/on_battle_start 事件链
  属于历史，已在存档状态里（scheduler 非 None 即天然挡住 setup/step/run 的初始化分支）；
- EventBus 订阅从编译产物静态重挂（`_subscribe_compiled_hooks` + 条件光环速度重同步
  两件——与 `_init_state` 的订阅块同集，无运行期动态注册盲区）；
- 红黑树（AVTree）不序列化——恢复时按存档逐句柄 insert 派生重建（remaining 是守恒
  主状态；树键取存档里读自活树的逐句柄预计时刻，与浮点重算彻底脱钩）。

完备性闸（防漂移）：`FIELD_CODECS` 是本模块唯一字段策略源——被档 dataclass
（Modifier/ActorState/BattleState/Actor/StatBlock/ShieldInstance/StateConfig）每个
字段必须在表内登记编解码方式（无豁免件——actor 本体全字段嵌套存档）；tests 闸用
`dataclasses.fields` 反射双向比对，新增字段未登记即炸。引擎/调度器/管线/hooks 运行期
字段的存档↔豁免二分清单同理由 tests 闸钉死（清单在 tests/test_save_restore.py，
与所指物就近维护）。
"""
from __future__ import annotations

import copy
import random
from typing import Any, Dict, List, Optional

from hsr_nous.sim.avtree import AVTree
from hsr_nous.sim.scheduler import Scheduler
from hsr_nous.sim.state import ActorState, BattleState, Modifier, ShieldInstance, StateConfig
from hsr_nous.sim_schema.actor import Actor, StatBlock

#: 存档格式版本号（后续格式演进可识别——load 侧版本闸只收本版）
SAVE_VERSION = 1

# ---------------------------------------------------------------------------
# 字段编解码词表
# ---------------------------------------------------------------------------
#: 纯 JSON 数据直存（标量 / 嵌套 dict / list——deepcopy 断活引用）
_CODEC_PLAIN = "plain"
#: PreparedExpression | None —— 存 source 串，恢复时经引擎共享 ExprCompiler 重 parse
#:（AST 是派生物不存；编译缓存兜底开销）。modifier 表达式五槽同此族
_CODEC_EXPR = "expr"
#: Dict[str, PreparedExpression] —— 逐值存 source 串（stat_exprs / hit_stat_exprs）
_CODEC_EXPR_DICT = "expr_dict"
#: Dict[str, tuple[str, float]] —— JSON 无 tuple，存 [source_stat, ratio]，恢复转回 tuple
_CODEC_TUPLE2_DICT = "tuple2_dict"
#: Actor 全字段嵌套（见 _ACTOR_CODECS——运行期 actor 可能是 replace 产物：
#: 系统单位具名速度规则覆写 spd / 召唤物继承面板，只有全字段存档才无需求解重放）
_CODEC_ACTOR = "actor"
#: StatBlock 全字段嵌套
_CODEC_STAT_BLOCK = "stat_block"
#: frozenset[str] —— 存排序 list（序确定，JSON 可序列化），恢复转回 frozenset
_CODEC_FROZENSET = "frozenset"
#: Dict[str, Modifier]（modifier_id → 实例，插入序即挂载序——保序存档）
_CODEC_MODIFIERS = "modifiers"
#: List[ShieldInstance]
_CODEC_SHIELDS = "shields"
#: StateConfig | None（形态配置——恢复时优先按 state 名回挂引擎注册表同件，
#: 注册表查不到才按存档重建，与 enter_state 挂注册表同件的现语义对齐）
_CODEC_STATE_CONFIG = "state_config"
#: Dict[str, ActorState]（actor_id → 状态，插入序 = 站位——保序存档）
_CODEC_ACTOR_STATES = "actor_states"

#: 存档字段策略表（完备性闸唯一来源——被档 dataclass 全字段登记，无豁免；
#: 新增字段未进表 = tests 完备性闸炸，防"漏一个字段 = 世界线静默分叉"）
FIELD_CODECS: Dict[type, Dict[str, str]] = {
    Modifier: {
        "modifier_id": _CODEC_PLAIN,
        "name": _CODEC_PLAIN,
        "modifier_type": _CODEC_PLAIN,
        "debuff_kind": _CODEC_PLAIN,
        "duration": _CODEC_PLAIN,
        "stacks": _CODEC_PLAIN,
        "max_stack": _CODEC_PLAIN,
        "stack_mode": _CODEC_PLAIN,
        "stacks_value": _CODEC_PLAIN,
        "dispellable": _CODEC_PLAIN,
        "singleton_group": _CODEC_PLAIN,
        "source_id": _CODEC_PLAIN,
        "source_kind": _CODEC_PLAIN,
        "source_ref": _CODEC_PLAIN,
        "remove_on_source_death": _CODEC_PLAIN,
        "shield_spec": _CODEC_PLAIN,
        "stat_effects": _CODEC_PLAIN,
        "scaling_effects": _CODEC_TUPLE2_DICT,
        "override_effects": _CODEC_PLAIN,
        "hit_condition_expr": _CODEC_EXPR,
        "enable_if_expr": _CODEC_EXPR,
        "stat_exprs": _CODEC_EXPR_DICT,
        "hit_stat_exprs": _CODEC_EXPR_DICT,
        "dot_element": _CODEC_PLAIN,
        "dot_ratio": _CODEC_PLAIN,
        "dot_ratio_expr": _CODEC_EXPR,
        "dot_base_chance": _CODEC_PLAIN,
        "dot_source_atk": _CODEC_PLAIN,
        "dot_snapshot_ctx": _CODEC_PLAIN,
        "control_kind": _CODEC_PLAIN,
        "weakness_add": _CODEC_PLAIN,
        "grants_immune": _CODEC_PLAIN,
        "tick_anchor": _CODEC_PLAIN,
        "effect_scope": _CODEC_PLAIN,
        "hp_lock": _CODEC_PLAIN,
        "revive_percent": _CODEC_PLAIN,
        "moon_cocoon": _CODEC_PLAIN,
        "forced_taunt": _CODEC_PLAIN,
        "toughness_lock": _CODEC_PLAIN,
        "lock_on": _CODEC_PLAIN,
        "prevent_action": _CODEC_PLAIN,
        "target_resource": _CODEC_PLAIN,
        "max_override": _CODEC_PLAIN,
    },
    ShieldInstance: {
        "shield_id": _CODEC_PLAIN,
        "name": _CODEC_PLAIN,
        "remaining": _CODEC_PLAIN,
        "source_id": _CODEC_PLAIN,
        "modifier_id": _CODEC_PLAIN,
        "pool": _CODEC_PLAIN,
    },
    StateConfig: {
        "state": _CODEC_PLAIN,
        "replaces_actions": _CODEC_PLAIN,
        "locked_actions": _CODEC_PLAIN,
        "exit_conditions": _CODEC_PLAIN,
        "stat_effects": _CODEC_PLAIN,
        "final_action_id": _CODEC_PLAIN,
        "exit_remove_modifiers": _CODEC_PLAIN,
        "banish_allies_on_enter": _CODEC_PLAIN,
        "countdown_spd_ratio": _CODEC_PLAIN,
        "countdown_initial_ratio": _CODEC_PLAIN,  # float | "uniform"——皆 JSON 原生
        "name": _CODEC_PLAIN,
        "grants_immune": _CODEC_PLAIN,
        "entry_end_turn": _CODEC_PLAIN,
    },
    StatBlock: {
        "hp": _CODEC_PLAIN,
        "atk": _CODEC_PLAIN,
        "def_": _CODEC_PLAIN,
        "spd": _CODEC_PLAIN,
        "crit_rate": _CODEC_PLAIN,
        "crit_dmg": _CODEC_PLAIN,
        "break_effect": _CODEC_PLAIN,
        "elation": _CODEC_PLAIN,
        "break_efficiency_boost": _CODEC_PLAIN,
        "weakness_break_efficiency_boost": _CODEC_PLAIN,
        "effect_hit": _CODEC_PLAIN,
        "effect_res": _CODEC_PLAIN,
        "def_pen": _CODEC_PLAIN,
        "res_pen": _CODEC_PLAIN,
        "vulnerability": _CODEC_PLAIN,
        "max_energy": _CODEC_PLAIN,
        "energy_regen": _CODEC_PLAIN,
        "heal_bonus": _CODEC_PLAIN,
        "shield_bonus": _CODEC_PLAIN,
        "dmg_bonus": _CODEC_PLAIN,
        "resistance": _CODEC_PLAIN,
        "weakness": _CODEC_PLAIN,
        "taunt": _CODEC_PLAIN,
        "max_toughness": _CODEC_PLAIN,
        "toughness_bars": _CODEC_PLAIN,
    },
    Actor: {
        "actor_id": _CODEC_PLAIN,
        "name": _CODEC_PLAIN,
        "actor_type": _CODEC_PLAIN,
        "level": _CODEC_PLAIN,
        "stats": _CODEC_STAT_BLOCK,
        "actions": _CODEC_PLAIN,
        "skill_levels": _CODEC_PLAIN,
        "summoner_id": _CODEC_PLAIN,
        "summon_flags": _CODEC_PLAIN,
        "path": _CODEC_PLAIN,
        "groups": _CODEC_PLAIN,
        "element": _CODEC_PLAIN,
        "elation_number": _CODEC_PLAIN,
        "system_flags": _CODEC_FROZENSET,
        "speed_rule": _CODEC_PLAIN,
        "turn_handler": _CODEC_PLAIN,
    },
    ActorState: {
        "actor": _CODEC_ACTOR,
        "current_hp": _CODEC_PLAIN,
        "current_energy": _CODEC_PLAIN,
        "alive": _CODEC_PLAIN,
        "banished": _CODEC_PLAIN,
        "broken": _CODEC_PLAIN,
        "toughness": _CODEC_PLAIN,
        "bar_index": _CODEC_PLAIN,
        "added_bars": _CODEC_PLAIN,
        "modifiers": _CODEC_MODIFIERS,
        "resources": _CODEC_PLAIN,
        "banger_entries": _CODEC_PLAIN,
        "state_config": _CODEC_STATE_CONFIG,
        "shields": _CODEC_SHIELDS,
    },
    BattleState: {
        "actors": _CODEC_ACTOR_STATES,
        "clock": _CODEC_PLAIN,
        "turn_count": _CODEC_PLAIN,
        "cycle_index": _CODEC_PLAIN,
        "cycle_end_clock": _CODEC_PLAIN,
        "skill_points": _CODEC_PLAIN,
        "punchline": _CODEC_PLAIN,
        "sp_max_override": _CODEC_PLAIN,
        "truncated": _CODEC_PLAIN,
        "total_damage": _CODEC_PLAIN,
        "damage_by_actor": _CODEC_PLAIN,
        "log": _CODEC_PLAIN,
        "moon_cocoon_used": _CODEC_PLAIN,
    },
}

#: 引擎运行期字段存档清单（save["engine"] 键集——编译产物与注入件不在此列，
#: 由 from_compiled 重带；完备性闸在 tests/test_save_restore.py 与结构豁免单同钉）
_ENGINE_RUNTIME_FIELDS = (
    "current_wave",
    "_enemy_policy_state",
    "_last_target_id",
    "_last_target_by_actor",
    "_last_sp_consumed",
    "_auto_target_ctx",
    "_aha_pool_override",
    "_banished_by_state",
    "_turn_consumed",
    "_cocoon_event_counter",
    "_cocoon_event_seq",
    "_cocoon_saved_event",
    "_resource_provenance",
    "_cond_aura_present",
    "_battle_end_emitted",
)


# ---------------------------------------------------------------------------
# 通用编解码
# ---------------------------------------------------------------------------

def _encode(cls: type, obj: Any) -> Dict[str, Any]:
    """按 FIELD_CODECS[cls] 逐字段编码（键 = 字段名，无改名——反射闸纯键集比对）."""
    return {fname: _encode_value(getattr(obj, fname), codec)
            for fname, codec in FIELD_CODECS[cls].items()}


def _encode_value(value: Any, codec: str) -> Any:
    if codec == _CODEC_PLAIN:
        return copy.deepcopy(value)
    if codec == _CODEC_EXPR:
        return None if value is None else {"source": value.source}
    if codec == _CODEC_EXPR_DICT:
        return {k: {"source": e.source} for k, e in value.items()}
    if codec == _CODEC_TUPLE2_DICT:
        return {k: [s, r] for k, (s, r) in value.items()}
    if codec == _CODEC_ACTOR:
        return _encode(Actor, value)
    if codec == _CODEC_STAT_BLOCK:
        return _encode(StatBlock, value)
    if codec == _CODEC_FROZENSET:
        return sorted(value)
    if codec == _CODEC_MODIFIERS:
        return {mid: _encode(Modifier, m) for mid, m in value.items()}
    if codec == _CODEC_SHIELDS:
        return [_encode(ShieldInstance, s) for s in value]
    if codec == _CODEC_STATE_CONFIG:
        return None if value is None else _encode(StateConfig, value)
    if codec == _CODEC_ACTOR_STATES:
        return {aid: _encode(ActorState, st) for aid, st in value.items()}
    raise ValueError(f"未知存档编解码 {codec!r}（FIELD_CODECS 词表见 sim/save_load.py）")


def _decode(cls: type, d: Dict[str, Any], expr: Any) -> Any:
    """_encode 对偶：按 FIELD_CODECS[cls] 逐字段解码建件."""
    return cls(**{fname: _decode_value(d[fname], codec, expr)
                  for fname, codec in FIELD_CODECS[cls].items()})


def _decode_value(value: Any, codec: str, expr: Any) -> Any:
    if codec == _CODEC_PLAIN:
        return copy.deepcopy(value)
    if codec == _CODEC_EXPR:
        return None if value is None else expr.compile(value["source"], layer="effect")
    if codec == _CODEC_EXPR_DICT:
        return {k: expr.compile(e["source"], layer="effect") for k, e in value.items()}
    if codec == _CODEC_TUPLE2_DICT:
        return {k: (s, r) for k, (s, r) in value.items()}
    if codec == _CODEC_ACTOR:
        return _decode(Actor, value, expr)
    if codec == _CODEC_STAT_BLOCK:
        return _decode(StatBlock, value, expr)
    if codec == _CODEC_FROZENSET:
        return frozenset(value)
    if codec == _CODEC_MODIFIERS:
        return {mid: _decode(Modifier, m, expr) for mid, m in value.items()}
    if codec == _CODEC_SHIELDS:
        return [_decode(ShieldInstance, s, expr) for s in value]
    if codec == _CODEC_STATE_CONFIG:
        return None if value is None else _decode(StateConfig, value, expr)
    if codec == _CODEC_ACTOR_STATES:
        return {aid: _decode(ActorState, st, expr) for aid, st in value.items()}
    raise ValueError(f"未知存档编解码 {codec!r}（FIELD_CODECS 词表见 sim/save_load.py）")


# ---------------------------------------------------------------------------
# RNG 流位置（random.Random getstate/setstate —— 嵌套 tuple ↔ list 进 JSON）
# ---------------------------------------------------------------------------

def _tuples_to_lists(x: Any) -> Any:
    if isinstance(x, tuple):
        return [_tuples_to_lists(v) for v in x]
    if isinstance(x, list):
        return [_tuples_to_lists(v) for v in x]
    return x


def _lists_to_tuples(x: Any) -> Any:
    if isinstance(x, list):
        return tuple(_lists_to_tuples(v) for v in x)
    return x


def _save_rng(rng: Optional[random.Random]) -> Optional[Any]:
    return None if rng is None else _tuples_to_lists(rng.getstate())


def _restore_rng(rng: Optional[random.Random], saved: Optional[Any]) -> random.Random:
    if saved is None:
        if rng is None:
            return random.Random(0)
        return rng
    target = rng if rng is not None else random.Random(0)
    target.setstate(_lists_to_tuples(saved))
    return target


# ---------------------------------------------------------------------------
# 调度器（动态六件 + clock；红黑树逐句柄 insert 派生重建）
# ---------------------------------------------------------------------------

def _save_scheduler(sch: Scheduler) -> Dict[str, Any]:
    entities: List[Dict[str, Any]] = []
    for h in sorted(sch._actors):
        node = sch._tree._entity_map.get(h)
        # 树键读自活树（恢复原 pop 时刻逐比特的凭据）；句柄不在树中属构造不出的
        # 病态（档间树籍恒为全句柄），兜底按当前值重算预计时刻
        eta = sch._tree._time[node] if node is not None else sch._eta(h)
        entities.append({
            "handle": h,
            "actor_id": sch._actors[h].actor_id,
            "tie": sch._tie_of[h],
            "eta": eta,
            "remaining": sch._remaining[h],
            "spd_now": sch._spd_now[h],
            "frozen": h in sch._frozen,
            "countdown": dict(sch._countdown[h]) if h in sch._countdown else None,
            "wave_reset_exempt": h in sch._wave_reset_exempt,
        })
    return {
        "clock": sch.clock,
        "entities": entities,
        "extra_queue": [[h, kind] for h, kind in sch._extra_queue],
    }


def _restore_scheduler(d: Dict[str, Any], actors_by_id: Dict[str, Actor]) -> Scheduler:
    sch = Scheduler.__new__(Scheduler)
    sch._tree = AVTree()
    sch._actors = {}
    sch._handles = {}
    sch._tie_of = {}
    sch._frozen = set()
    sch._extra_queue = []
    sch._countdown = {}
    sch._wave_reset_exempt = set()
    sch._remaining = {}
    sch._spd_now = {}
    sch.clock = float(d["clock"])
    for e in d["entities"]:
        h = int(e["handle"])
        actor = actors_by_id[e["actor_id"]]
        sch._actors[h] = actor
        sch._handles[actor.actor_id] = h
        sch._tie_of[h] = int(e["tie"])
        sch._remaining[h] = float(e["remaining"])
        sch._spd_now[h] = float(e["spd_now"])
        if e["frozen"]:
            sch._frozen.add(h)
        if e["countdown"] is not None:
            sch._countdown[h] = {"left": int(e["countdown"]["left"]),
                                 "spd": float(e["countdown"]["spd"])}
        if e["wave_reset_exempt"]:
            sch._wave_reset_exempt.add(h)
        sch._tree.insert(float(e["eta"]), tie=int(e["tie"]), entity=h)
    sch._extra_queue = [(int(h), str(kind)) for h, kind in d["extra_queue"]]
    return sch


# ---------------------------------------------------------------------------
# 引擎运行期字段（清单见 _ENGINE_RUNTIME_FIELDS；编译产物由 from_compiled 重带）
# ---------------------------------------------------------------------------

def _save_engine_fields(engine: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for fname in _ENGINE_RUNTIME_FIELDS:
        if fname == "_resource_provenance":
            # 键是 tuple(actor_id, rid)、值是来源集合——JSON 化转 [aid, rid, sorted(srcs)]
            out[fname] = [[aid, rid, sorted(srcs)]
                          for (aid, rid), srcs in sorted(engine._resource_provenance.items())]
        elif fname == "_battle_end_emitted":
            # 惰性字段（首次 _emit_battle_end 才落实例）——getattr 缺省 False
            out[fname] = bool(getattr(engine, "_battle_end_emitted", False))
        else:
            out[fname] = copy.deepcopy(getattr(engine, fname))
    return out


def _restore_engine_fields(engine: Any, d: Dict[str, Any]) -> None:
    for fname in _ENGINE_RUNTIME_FIELDS:
        if fname == "_resource_provenance":
            engine._resource_provenance = {(aid, rid): set(srcs)
                                           for aid, rid, srcs in d[fname]}
        else:
            setattr(engine, fname, copy.deepcopy(d[fname]))


# ---------------------------------------------------------------------------
# 累积队列（§23.9——id(CompiledHook) 键跨进程不可移植，存档按编译钩列表序编号）
# ---------------------------------------------------------------------------

def _save_acc_queues(engine: Any) -> List[Dict[str, Any]]:
    index_of = {id(h): i for i, h in enumerate(engine._compiled_hooks)}
    out: List[Dict[str, Any]] = []
    for hid, queue in engine._hooks._acc_queues.items():
        if not queue:
            continue  # 空队列（flush 后残留键）等价于无队——不存档
        i = index_of.get(hid)
        if i is None:
            raise ValueError("累积队列挂着非编译钩实例——无法按编译钩编号存档")
        out.append({"hook_index": i, "queue": copy.deepcopy(queue)})
    return sorted(out, key=lambda e: e["hook_index"])


def _restore_acc_queues(engine: Any, entries: List[Dict[str, Any]]) -> None:
    for e in entries:
        h = engine._compiled_hooks[int(e["hook_index"])]
        engine._hooks._acc_queues[id(h)] = [dict(p) for p in e["queue"]]


# ---------------------------------------------------------------------------
# 顶层：存档 / 恢复
# ---------------------------------------------------------------------------

def save_engine(engine: Any) -> Dict[str, Any]:
    """整机存档（纯数据，json.dumps 可直接序列化）.

    契约：战斗进行中（setup/step/run 之后、步与步之间）调用；战斗未开始
    （scheduler 未建）无可存——直接报错（开前存档等价于 from_compiled 配置，无意义）。
    """
    if engine.scheduler is None:
        raise ValueError(
            "战斗未开始无可存档（scheduler 未建——先 setup()/step()/run()；"
            "开局前的等价物是 from_compiled 编译产物本身，不是存档）")
    sch_actor_ids = {sch_a.actor_id for sch_a in engine.scheduler._actors.values()}
    if sch_actor_ids != set(engine.state.actors):
        raise ValueError(
            f"调度器与战斗状态的单位集失配（{sch_actor_ids ^ set(engine.state.actors)}）"
            "——存档完整性闸：两册同源是恢复后世界线全等的前提")
    return {
        "save_version": SAVE_VERSION,
        "mode": engine.pipeline.mode,
        "state": _encode(BattleState, engine.state),
        "scheduler": _save_scheduler(engine.scheduler),
        "rng": _save_rng(engine.pipeline.rng),
        "engine": _save_engine_fields(engine),
        "acc_queues": _save_acc_queues(engine),
    }


def restore_into(engine: Any, save: Dict[str, Any]) -> None:
    """把存档注入 from_compiled 同路重建的引擎骨架（状态注入 + 订阅重挂）.

    不调 `_init_state`（初始挂载/进战发放属历史，已在存档状态里；scheduler 注入后
    非 None，setup/step/run 的初始化分支天然不再触发）。调用方随后直接 step()/run()。
    """
    if not isinstance(save, dict) or save.get("save_version") != SAVE_VERSION:
        raise ValueError(
            f"存档格式版本不符（期望 save_version={SAVE_VERSION}，"
            f"实际 {save.get('save_version') if isinstance(save, dict) else type(save).__name__}）"
            "——格式演进需配套迁移通道")
    if save.get("mode") != engine.pipeline.mode:
        raise ValueError(
            f"存档模式 {save.get('mode')!r} 与引擎模式 {engine.pipeline.mode!r} 不符"
            "——roll/expected 结算语义不同，混接 = 世界线必分叉")
    # ① 战斗全状态（含 actor 全字段、modifier 全字段、日志流——全精度）
    engine.state = _decode(BattleState, save["state"], engine._expr)
    # 形态配置回挂注册表同件（enter_state 挂的是注册表件——恢复同口径；
    # 注册表查不到（绕过编译层的手建局）按存档重建兜底）
    for aid, st in engine.state.actors.items():
        if st.state_config is None:
            continue
        for cfg in engine.state_configs_by_actor.get(aid, []):
            if cfg.state == st.state_config.state:
                st.state_config = cfg
                break
    # ② 调度器（actor 引用共享战斗状态同件——与原引擎同语义）
    actors_by_id = {aid: st.actor for aid, st in engine.state.actors.items()}
    engine.scheduler = _restore_scheduler(save["scheduler"], actors_by_id)
    # ③ RNG 流位置（就地 setstate——全引擎经 pipeline.rng 单点读取，不换实例）
    engine.pipeline.rng = _restore_rng(engine.pipeline.rng, save["rng"])
    # ④ 引擎运行期字段
    _restore_engine_fields(engine, save["engine"])
    # ⑤ 事件订阅重挂（编译产物静态注册——与 _init_state 订阅块同集；
    # 开局事件链不重发，属历史）
    engine._subscribe_compiled_hooks()
    engine.bus.subscribe("on_hp_decrease", engine._resync_cond_speed)
    engine.bus.subscribe("on_hp_increase", engine._resync_cond_speed)
    # ⑥ 累积队列（按编译钩列表序编号回挂）
    _restore_acc_queues(engine, save.get("acc_queues", []))
