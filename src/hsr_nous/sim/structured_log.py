"""结构化战斗日志（11_combat_log 落地 v1）：引擎事件流 → spec 形事件序列.

引擎侧 mnestia 呈现层通道——web 事件箱（`_event_box`）的同源升格：挂接即录、被动只读、
不进结算路径（B16 确定性零影响——条目全部派生自总线事件，同 seed 同日志）。

- `StructuredLogger(engine)`：订阅总线 → spec 24 类事件条目（`logger.entries`）+ 终局汇总
  （`logger.summary`）。共享室设计（同 debug.py `_cell` 纪律：闭包只捕普通 dict——引擎
  深拷贝时检查点共享同一记录器，back/goto 重放段事件自然重灌）。
- before/after 槽（hp/energy/sp/toughness）由记录器按序观测维护（总线 payload 无此槽，
  不扩 payload——呈现层自理）。
- v1 未发射：`zone_deploy` / `zone_dismiss`（zone 体系未实装）、`technique_cast`
  （秘技标识不进编译产物）、modifier_apply 的 duration 槽（payload 无——归后续）。
"""
from __future__ import annotations

from typing import Any, Dict, List

#: spec 事件类型（11_combat_log §事件类型清单；zone/technique 三类 v1 未发射见模块头注）
SPEC_EVENT_TYPES = frozenset({
    "battle_start", "battle_end", "turn_start", "turn_end", "action", "damage", "heal",
    "effect", "modifier_apply", "modifier_expire", "break", "kill", "death",
    "energy_change", "skill_point_change", "wave_start", "wave_end",
    "cycle_start", "cycle_end", "resource_change", "state_change",
    "zone_deploy", "zone_dismiss", "technique_cast",
})


class StructuredLogger:
    """结构化战斗日志记录器（mnestia 呈现层）."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine
        # 共享室（同 debug.py `_cell` 纪律）：普通 dict——深拷贝检查点共享同一记录器
        self._cell: Dict[str, Any] = {
            "entries": [],
            "hp": {aid: st.current_hp for aid, st in engine.state.actors.items()},
            "energy": {aid: st.current_energy for aid, st in engine.state.actors.items()},
            "sp": float(engine.state.skill_points),
            "toughness": {aid: st.toughness for aid, st in engine.state.actors.items()},
        }
        self._subscribe()

    # ------------------------------------------------------------------
    # 取数
    # ------------------------------------------------------------------

    @property
    def entries(self) -> List[Dict[str, Any]]:
        return self._cell["entries"]

    @property
    def summary(self) -> Dict[str, Any]:
        """终局汇总（total_damage/dps/kills/deaths/turns/total_action_value）."""
        eng = self._engine
        kills = sum(1 for e in self.entries if e.get("event_type") == "kill")
        deaths = sum(1 for e in self.entries
                     if e.get("event_type") == "death"
                     and str(e.get("actor_id", "")) in {
                         a.actor_id for a in eng.encounter.actors
                         if a.actor_type != "monster" and not a.summoner_id})
        av = round(float(eng.state.clock), 1)
        total = round(float(eng.state.total_damage), 1)
        return {
            "total_damage": total,
            "total_action_value": av,
            "total_turns": int(eng.state.turn_count),
            "dps": round(total / av, 2) if av > 0 else 0.0,
            "kills": kills,
            "deaths": deaths,
        }

    # ------------------------------------------------------------------
    # 订阅翻译层（bus 事件 → spec 条目；闭包只捕 _cell）
    # ------------------------------------------------------------------

    def _subscribe(self) -> None:
        eng = self._engine
        cell = self._cell
        bus = eng.bus

        def put(entry: Dict[str, Any]) -> None:
            entry["timestamp"] = round(float(eng.state.clock), 1)
            cell["entries"].append(entry)

        def hp_after(aid: str, new: float) -> tuple:
            old = cell["hp"].get(aid, new)
            cell["hp"][aid] = new
            return old, new

        def energy_after(aid: str, new: float) -> tuple:
            old = cell["energy"].get(aid, new)
            cell["energy"][aid] = new
            return old, new

        bus.subscribe("on_battle_start", lambda et, p, ctx: put(
            {"event_type": "battle_start", "data": {}}))
        bus.subscribe("battle_end", lambda et, p, ctx: put(
            {"event_type": "battle_end", "reason": p.get("reason")}))

        bus.subscribe("on_turn_start", lambda et, p, ctx: put(
            {"event_type": "turn_start", "actor_id": p.get("actor"),
             "action_value": round(float(eng.state.clock), 1)}))
        bus.subscribe("on_turn_end", lambda et, p, ctx: put(
            {"event_type": "turn_end", "actor_id": p.get("actor")}))

        def on_action(et: str, p: Dict[str, Any], ctx: Any) -> None:
            after = float(eng.state.skill_points)
            put({"event_type": "action", "actor_id": p.get("actor"),
                 "action_id": p.get("action_id"),
                 "target_ids": ([p["target"]] if p.get("target") else []),
                 "skill_points_before": cell["sp"], "skill_points_after": after})
            cell["sp"] = after
        bus.subscribe("on_action", on_action)

        def on_hit(et: str, p: Dict[str, Any], ctx: Any) -> None:
            tid = str(p.get("target"))
            st = eng.state.actors.get(tid)
            before, after = hp_after(tid, st.current_hp if st else cell["hp"].get(tid, 0.0))
            put({"event_type": "damage", "source_id": p.get("source"),
                 "target_id": tid, "damage": round(float(p.get("amount", 0.0)), 1),
                 "damage_type": p.get("damage_type", ""),
                 "is_critical": bool(p.get("is_critical", False)),
                 "target_hp_before": round(before, 1), "target_hp_after": round(after, 1)})
        bus.subscribe("after_being_hit", on_hit)

        def on_heal(et: str, p: Dict[str, Any], ctx: Any) -> None:
            tid = str(p.get("target"))
            st = eng.state.actors.get(tid)
            before, after = hp_after(tid, st.current_hp if st else cell["hp"].get(tid, 0.0))
            put({"event_type": "heal", "source_id": p.get("source"),
                 "target_id": tid, "heal": round(float(p.get("amount", 0.0)), 1),
                 "target_hp_before": round(before, 1), "target_hp_after": round(after, 1)})
        bus.subscribe("on_hp_increase", on_heal)

        bus.subscribe("after_apply_modifier", lambda et, p, ctx: put(
            {"event_type": "modifier_apply", "modifier_id": p.get("modifier_id"),
             "modifier_type": p.get("modifier_type", ""),
             "source_id": p.get("source"), "target_id": p.get("target")}))
        bus.subscribe("after_remove_modifier", lambda et, p, ctx: put(
            {"event_type": "modifier_expire", "modifier_id": p.get("modifier_id"),
             "reason": p.get("reason"), "target_id": p.get("target")}))

        def on_break(et: str, p: Dict[str, Any], ctx: Any) -> None:
            tid = str(p.get("target"))
            before = cell["toughness"].get(tid, 0.0)
            cell["toughness"][tid] = 0.0
            put({"event_type": "break", "source_id": p.get("source"),
                 "target_id": tid, "bar_index": p.get("bar_index", 0),
                 "toughness_before": round(before, 1), "toughness_after": 0.0})
        bus.subscribe("on_break", on_break)

        bus.subscribe("on_kill", lambda et, p, ctx: put(
            {"event_type": "kill", "killer_id": p.get("source"),
             "target_id": p.get("target")}))
        bus.subscribe("actor_exit", lambda et, p, ctx: (
            put({"event_type": "death", "actor_id": p.get("actor")})
            if p.get("reason") == "death" else None))

        def on_energy(et: str, p: Dict[str, Any], ctx: Any) -> None:
            aid = str(p.get("actor"))
            st = eng.state.actors.get(aid)
            before, after = energy_after(
                aid, st.current_energy if st else cell["energy"].get(aid, 0.0))
            put({"event_type": "energy_change", "actor_id": aid,
                 "before": round(before, 1), "after": round(after, 1)})
        def wf_energy(et: str, p: Dict[str, Any], ctx: Any) -> None:
            on_energy(et, p or {}, ctx)
            return None
        bus.subscribe_waterfall("on_gain_energy", wf_energy)

        def on_sp(et: str, p: Dict[str, Any], ctx: Any) -> None:
            after = float(p.get("after", eng.state.skill_points))
            put({"event_type": "skill_point_change",
                 "before": cell["sp"], "after": after})
            cell["sp"] = after
        bus.subscribe("on_skill_point_change", on_sp)

        def on_wave(et: str, p: Dict[str, Any], ctx: Any) -> None:
            idx = int(p.get("wave_index", 0))
            if idx > 0:
                put({"event_type": "wave_end", "wave_index": idx - 1})
            put({"event_type": "wave_start", "wave_index": idx})
        bus.subscribe("on_wave_start", on_wave)

        bus.subscribe("on_cycle_start", lambda et, p, ctx: put(
            {"event_type": "cycle_start", "cycle_number": p.get("cycle_index"),
             "cycle_av": p.get("budget")}))
        bus.subscribe("on_cycle_end", lambda et, p, ctx: put(
            {"event_type": "cycle_end", "cycle_number": p.get("cycle_index")}))

        bus.subscribe("on_resource_gain", lambda et, p, ctx: put(
            {"event_type": "resource_change", "actor_id": p.get("actor"),
             "resource_id": p.get("resource_id"),
             "before": round(float(p.get("current", 0.0)) - float(p.get("amount", 0.0)), 2),
             "after": p.get("current")}))
        bus.subscribe("on_state_change", lambda et, p, ctx: put(
            {"event_type": "state_change", "actor_id": p.get("actor"),
             "from_state": p.get("from_state"), "to_state": p.get("to_state")}))
