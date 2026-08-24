"""modifier 生命周期 + 护盾（机制层）：施加/tick 走字/驱散净化/spec 物化/护盾吸收.

从 engine.py 切出的 modifier 职责域（God-object 切分第二刀，纯搬家零逻辑改动）：
modifier 施加（硬免疫/效果命中/叠层/互斥组）、计时锚走字（owner/source 双锚 + DoT
跳伤）、dispel/purify、dict 声明物化（duration 糖解析）、护盾物化与并行吸收。
战斗状态回调全走 CombatEngine 现成方法（ModifierBook 持 engine 门面，不复制状态）；
engine 上同名方法为薄委托（tests 直调口径不变）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hsr_nous.sim.state import MOON_COCOON_ID, ActorState, Modifier, ShieldInstance
from hsr_nous.sim_schema.actor import Actor
from hsr_nous.sim_schema.expression import parse

if TYPE_CHECKING:
    from hsr_nous.sim.engine import CombatEngine

#: duration dict 糖（04_modifier §4.14）的 tick_on 锚点名 → 引擎 tick_anchor 值
#: （词表镜像：build_compiler DURATION_TICK_ON——按引擎实现冻结，改一边同步另一边）
_DURATION_TICK_ON = {"$modifier.source": "source_turn_end"}

#: duration dict 糖合法键（until 已登记未落地——写了报错指路，不静默吞）
_DURATION_DICT_KEYS = frozenset({"value", "tick_on", "until"})


def _parse_duration_spec(spec: Dict[str, Any]) -> tuple[int, Optional[str]]:
    """duration 槽解析（04_modifier §4.14）：int 直给；dict 糖 {value, tick_on} → (duration, tick_anchor 覆盖).

    tick_on "$modifier.source" → source_turn_end 锚（施加者回合结束走字，见 _tick_source_modifiers）；
    until 事件到期形态未落地——报错指路，不静默吞（曾运行期 int(dict) TypeError 裸炸）。
    """
    d = spec.get("duration", 0)
    if not isinstance(d, dict):
        return int(d), None
    where = f"modifier {spec.get('modifier_id')!r} 的 duration"
    for k in d:
        if k not in _DURATION_DICT_KEYS:
            raise ValueError(f"{where} 含未知键 {k!r}（合法集合：{sorted(_DURATION_DICT_KEYS)}，见 04_modifier §4.14）")
    if "until" in d:
        raise ValueError(
            f"{where} 的 until 事件到期形态未落地（04_modifier §4.14 设计预览）——"
            "已落地形态：int 直给 / {value, tick_on}")
    tick_on = d.get("tick_on")
    if tick_on is not None and str(tick_on) not in _DURATION_TICK_ON:
        raise ValueError(
            f"{where} 的 tick_on 非法值 {tick_on!r}（合法集合：{sorted(_DURATION_TICK_ON)}，见 04_modifier §4.14）")
    anchor = _DURATION_TICK_ON[str(tick_on)] if tick_on is not None else None
    return int(d.get("value", 0)), anchor


class ModifierBook:
    """modifier 生命周期 + 护盾运行时：构造持 engine 门面，回调全走 CombatEngine 现成方法."""

    def __init__(self, engine: "CombatEngine") -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # modifier 基础层
    # ------------------------------------------------------------------

    def _apply_modifier(self, target: ActorState, mod: Modifier, *, apply_chance: float = 1.0) -> bool:
        """施加 modifier：硬免疫判定 → 效果命中判定（debuff 系）→ singleton_group → stack_mode 语义.

        返回是否成功挂上（免疫/抵抗则失败）.
        """
        # 硬免疫（#18.6：apply 前硬拒，与 100% 效果抵抗的概率模型语义区分）
        new_kind = mod.debuff_kind or ("control" if mod.control_kind else mod.modifier_type)
        if new_kind != "buff":
            for held in target.modifiers.values():
                if new_kind in held.grants_immune:
                    self._engine.bus.emit("on_immune", {"modifier_id": mod.modifier_id,
                                                "target": target.actor.actor_id}, self._engine.state)
                    return False
        # 效果命中判定（§4.7：debuff/dot/control 且 chance<1 时掷/判）
        if mod.modifier_type in ("debuff", "dot", "control") and apply_chance < 1.0:
            src_state = self._engine.state.actors.get(mod.source_id)
            se = self._engine.pipeline.effective_stats(src_state) if src_state else {}
            te = self._engine.pipeline.effective_stats(target)
            chance = self._engine.pipeline.hit_chance(se, te, apply_chance,
                                              effect_res_pen=se.get("effect_res_pen", 0.0))
            if not self._engine.pipeline.roll_debuff_apply(chance):
                self._engine.bus.emit("on_resist", {"modifier_id": mod.modifier_id, "target": target.actor.actor_id, "chance": chance}, self._engine.state)
                self._engine.state.log.append(f"AV{self._engine.state.clock:.1f}: {target.actor.name} 抵抗了 {mod.name}（命中率 {chance:.0%}）")
                return False

        # singleton_group：同组先摘旧
        if mod.singleton_group:
            for old in list(target.modifiers.values()):
                if old.singleton_group == mod.singleton_group and old.modifier_id != mod.modifier_id:
                    self._remove_modifier(target, old.modifier_id, "replace")

        existing = target.modifiers.get(mod.modifier_id)
        if existing is not None:
            if mod.stack_mode == "replace":
                self._remove_modifier(target, mod.modifier_id, "replace")
                target.modifiers[mod.modifier_id] = mod
            elif mod.stack_mode == "set":
                # 层数设为 stacks_value，clamp 到 [1, max_stack]（无 clamp 时 0 层件=死挂）
                existing.stacks = max(1, min(int(mod.stacks_value), existing.max_stack))
                existing.duration = max(existing.duration, mod.duration)
            else:  # refresh / independent（v0.4 均视同 refresh 时长）
                existing.stacks = min(existing.stacks + mod.stacks, existing.max_stack)
                existing.duration = max(existing.duration, mod.duration)
        else:
            target.modifiers[mod.modifier_id] = mod
        self._engine.bus.emit("after_apply_modifier", {"modifier_id": mod.modifier_id, "target": target.actor.actor_id, "source": mod.source_id}, self._engine.state)
        self._sync_speed(target)
        return True

    def _sync_speed(self, target: ActorState) -> None:
        """有效速度同步到调度器（速度类 modifier 挂上/摘除后行动序才生效）.

        历史缺口：有效速度（effective_stats.spd）变化从未传给调度器——速度 buff 在行动序上
        曾是"死"的（on_speed_change 无人调用）。此处为唯一接线点。
        """
        if self._engine.scheduler is None or self._engine._is_monster(target.actor):
            return
        # 光环（scope=team）变化会辐射全队速度——同步全体非怪单位，不只 target
        for st in self._engine.state.actors.values():
            if self._engine._is_monster(st.actor) or not st.alive:
                continue
            handle = self._engine.scheduler.handle_of(st.actor.actor_id)
            new_spd = self._engine.pipeline.effective_stats(st)["spd"]
            old_spd = self._engine.scheduler.spd_of(handle, new_spd)
            if abs(new_spd - old_spd) > 1e-9:
                self._engine.scheduler.on_speed_change(st.actor, old_spd, new_spd)

    def dispel(self, target: ActorState, max_count: int = 1) -> int:
        """驱散（解除敌方增益）：LIFO 摘 dispellable 的 buff 系."""
        removed = 0
        for mod in reversed(list(target.modifiers.values())):
            if removed >= max_count:
                break
            if mod.modifier_type in ("buff",) and mod.dispellable:
                self._remove_modifier(target, mod.modifier_id, "dispel")
                removed += 1
        if removed:
            self._engine.state.log.append(f"AV{self._engine.state.clock:.1f}: {target.actor.name} 被驱散 {removed} 个增益")
        return removed

    def purify(self, target: ActorState, max_count: int = 1) -> int:
        """净化（解除我方负面）：LIFO 摘 dispellable 的 debuff/dot/control 系."""
        removed = 0
        for mod in reversed(list(target.modifiers.values())):
            if removed >= max_count:
                break
            if mod.modifier_type in ("debuff", "dot", "control") and mod.dispellable:
                self._remove_modifier(target, mod.modifier_id, "purify")
                removed += 1
        if removed:
            self._engine.state.log.append(f"AV{self._engine.state.clock:.1f}: {target.actor.name} 被净化 {removed} 个负面")
        return removed

    def _remove_modifier(self, target: ActorState, modifier_id: str, reason: str = "expire") -> None:
        if target.modifiers.pop(modifier_id, None) is not None:
            # 反向摘盾：modifier 消失（过期/驱散/净化/破盾级联），其护盾实例一并移除
            target.shields = [s for s in target.shields if s.modifier_id != modifier_id]
            self._engine.bus.emit("after_remove_modifier", {"modifier_id": modifier_id, "reason": reason, "target": target.actor.actor_id}, self._engine.state)
            self._sync_speed(target)

    def _tick_dots(self, actor_state: ActorState) -> None:
        """A 类结算：回合开始 DOT 跳伤."""
        # 同一携带者的整批 DoT 跳伤 = 一次伤害事件（月茧同时致死批处理域）
        with self._engine._damage_event():
            for mod in list(actor_state.modifiers.values()):
                if mod.modifier_type != "dot":
                    continue
                if mod.dot_element == "physical":
                    result = self._engine.pipeline.bleed_tick(actor_state, mod)
                else:
                    result = self._engine.pipeline.dot_tick(actor_state, mod)
                dealt = result.value
                if actor_state.shields and dealt > 0:
                    # DoT 走同一护盾层（pipeline 已全额扣血：吸收量退回，本体只承溢出）
                    overflow = self._absorb_with_shields(actor_state, dealt, mod.source_id)
                    actor_state.current_hp += dealt - overflow
                    dealt = overflow
                if dealt > 0:
                    # HP 下降发射点（DoT/裂伤跳伤——mechanics 11 §11.3；reason='dot'，词表冻结见 _execute_action）
                    self._engine.bus.emit("on_hp_decrease", {
                        "amount": dealt, "source": mod.source_id,
                        "reason": "dot", "target": actor_state.actor.actor_id}, self._engine.state)
                self._engine.state.total_damage += result.value
                self._engine.state.damage_by_actor[mod.source_id] = self._engine.state.damage_by_actor.get(mod.source_id, 0.0) + result.value
                self._engine.state.log.append(f"AV{self._engine.state.clock:.1f}: {actor_state.actor.name} 受到 {mod.name} 持续伤害 {result.value:,.0f}")
                self._engine.bus.emit("on_dot_retrigger", {"modifier_id": mod.modifier_id, "target": actor_state.actor.actor_id}, self._engine.state)
                self._engine._check_death(actor_state, mod.source_id)
                if not actor_state.alive:
                    break  # 尸体不跳后续 DoT（与主循环/_run_turn 的 dead-skip 同口径）

    def _tick_modifiers(self, actor_state: ActorState, anchor: str = "owner_turn_end") -> None:
        """B 类结算：按计时锚点把 duration-1，到期移除.

        anchor：owner_turn_end（携带者回合结束，默认）/ owner_turn_start（携带者回合开始，
        阮梅弦外音族）/ on_action（每次行动——行动次数型 buff 族）。
        source_turn_end 锚不走这里——见 _tick_source_modifiers（按施加者回合扫全场）。
        """
        for mod in list(actor_state.modifiers.values()):
            if mod.duration <= 0 or mod.tick_anchor != anchor:
                continue
            self._tick_one_modifier(actor_state, mod)

    def _tick_one_modifier(self, actor_state: ActorState, mod: Modifier) -> None:
        """单件走字：duration-1，到期移除（月茧到期真死特判——两锚点共用）."""
        mod.duration -= 1
        if mod.duration == 0:
            self._remove_modifier(actor_state, mod.modifier_id, "expire")
            if mod.moon_cocoon:
                # 月茧到期未解除（未受治疗/未获护盾）→ 置 0 血走 _check_death 单漏斗
                # （engine 门面回调，同 _tick_dots 先例）——锁血/复活层照走，形态
                # exit_state/actor_exit/on_kill 由 _check_death 统一发放；直接置
                # alive=False 曾绕过 exit_state（境界队友 banish 孤儿化、
                # exit_remove_modifiers 残留、on_kill 丢失）
                actor_state.current_hp = 0.0
                self._engine._check_death(actor_state, mod.source_id)
                outcome = "倒下" if not actor_state.alive else "被生存层接住"
                self._engine.state.log.append(
                    f"AV{self._engine.state.clock:.1f}: {actor_state.actor.name} 月茧到期，{outcome}")

    def _tick_source_modifiers(self, turn_actor: Actor) -> None:
        """B 类结算补：source_turn_end 锚（04_modifier §4.14 duration.tick_on "$modifier.source"）——
        施加者回合结束时，其施加的该锚 modifier 走字（挂在哪个携带者身上不限）.

        决策卡 #20 补钉由构造满足：施加者离场（死亡）后无回合，挂靠自然停止走字，不立即移除。
        """
        for st in self._engine.state.actors.values():
            for mod in list(st.modifiers.values()):
                if mod.duration <= 0 or mod.tick_anchor != "source_turn_end":
                    continue
                if mod.source_id != turn_actor.actor_id:
                    continue
                self._tick_one_modifier(st, mod)

    # ------------------------------------------------------------------
    # dict 声明物化（apply_modifiers / hook effects 共用）
    # ------------------------------------------------------------------

    @staticmethod
    def _modifier_from_spec(spec: Dict[str, Any]) -> Modifier:
        """dict 声明 → Modifier 物化（apply_modifiers / hook effects 共用）.

        hit_condition：命中域条件（04_modifier §hit_condition 组合原语）——声明期即
        预编译为 PreparedExpression（白名单校验在此完成），不存裸字符串。
        """
        duration, anchor_override = _parse_duration_spec(spec)
        hit_condition = spec.get("hit_condition")
        return Modifier(
            modifier_id=spec["modifier_id"],
            name=spec.get("name", spec["modifier_id"]),
            modifier_type=spec.get("modifier_type", "buff"),
            duration=duration,
            stacks=int(spec.get("stacks", 1)),
            max_stack=int(spec.get("max_stack", 99)),
            stack_mode=str(spec.get("stack_mode", "refresh")),
            stacks_value=float(spec.get("stacks_value", 0.0)),  # stack_mode=="set" 的目标层数
            singleton_group=str(spec.get("singleton_group", "")),  # 同目标同组互斥（新挂替换旧挂）
            dispellable=bool(spec.get("dispellable", True)),
            stat_effects={k: float(v) for k, v in (spec.get("stat_effects") or {}).items()},
            scaling_effects={str(k): (str(v[0]), float(v[1]))
                             for k, v in (spec.get("scaling_effects") or {}).items()},
            override_effects={str(k): float(v) for k, v in (spec.get("override_effects") or {}).items()},
            hit_condition_expr=(parse(str(hit_condition), layer="effect")
                                if hit_condition is not None else None),
            weakness_add=[str(w) for w in spec.get("weakness_add") or []],
            grants_immune=[str(x) for x in spec.get("grants_immune") or []],
            tick_anchor=anchor_override or str(spec.get("tick_anchor", "owner_turn_end")),
            effect_scope=str(spec.get("effect_scope", "self")),
            hp_lock=bool(spec.get("hp_lock", False)),
            revive_percent=float(spec.get("revive_percent", 0.0)),
            moon_cocoon=bool(spec.get("moon_cocoon", False)),
            forced_taunt=bool(spec.get("forced_taunt", False)),
        )

    def _apply_modifier_spec(self, target: ActorState, spec: Dict[str, Any],
                             source: Optional[ActorState]) -> bool:
        """dict 声明 → modifier 挂载；声明带 shield 块时同时物化护盾实例."""
        mod = self._modifier_from_spec(spec)
        if source is not None and not mod.source_id:
            # 施加者记账（source_turn_end 锚走字/事件 payload 都读 source_id）
            mod.source_id = source.actor.actor_id
        if not self._apply_modifier(target, mod):
            return False
        if spec.get("shield"):
            self._attach_shield(target, mod, spec["shield"], source)
        return True

    # ------------------------------------------------------------------
    # 护盾（mechanics 01 §1.3：独立栈 + 并行吸收；生命周期复用关联 modifier）
    # ------------------------------------------------------------------

    def _attach_shield(self, target: ActorState, mod: Modifier, shield_spec: Dict[str, Any],
                       source: Optional[ActorState]) -> None:
        """护盾物化：值 = (属性×倍率 + 固定值) × (1 + 施加者 Shield_Bonus%).

        同 modifier 重复施加 = 护盾整换为新值（与 stack_mode: refresh 同口径）。
        """
        se = self._engine.pipeline.effective_stats(source) if source is not None else {}
        base = float(shield_spec.get("flat", 0.0))
        for stat, ratio in (shield_spec.get("scaling") or {}).items():
            key = "def_" if stat == "def" else str(stat)
            base += float(se.get(key, 0.0)) * float(ratio)
        value = base * (1.0 + float(se.get("shield_bonus", 0.0)))
        target.shields = [s for s in target.shields if s.modifier_id != mod.modifier_id]
        target.shields.append(ShieldInstance(
            shield_id=mod.modifier_id, name=mod.name, remaining=value,
            source_id=(source.actor.actor_id if source is not None else mod.source_id),
            modifier_id=mod.modifier_id,
        ))
        self._engine.state.log.append(
            f"AV{self._engine.state.clock:.1f}: {target.actor.name} 获得护盾 {mod.name}（{value:,.0f}）")
        # 月茧解除条件之一：获得护盾（mechanics 11 §11.1）
        if MOON_COCOON_ID in target.modifiers:
            self._remove_modifier(target, MOON_COCOON_ID, "cocoon_release")
            self._engine.state.log.append(f"AV{self._engine.state.clock:.1f}: {target.actor.name} 的月茧解除（获得护盾）")

    def _absorb_with_shields(self, target: ActorState, amount: float, source_id: str = "") -> float:
        """护盾并行吸收：返回溢出量（本体承伤）.

        规则（mechanics 01 §1.3，唯一事实来源）：
        - 所有护盾**同时吸收全额伤害**（各扣 min(自身剩余, amount)），互不转嫁
        - 有效护盾 = 最高实例剩余值（多盾不叠加）→ 本体承伤 = max(0, amount − 最高剩余)
        - 归零实例后台破裂：发 `shield_broken`，级联摘除关联 modifier（附带效果一并移除）
        - 真伤同走本层（mechanics 02 §2.13：护盾非乘区，是乘区结算后的吸收层）
        """
        if amount <= 0 or not target.shields:
            return max(0.0, amount)
        overflow = max(0.0, amount - max(s.remaining for s in target.shields))
        broken: List[ShieldInstance] = []
        for s in list(target.shields):
            take = min(s.remaining, amount)
            s.remaining -= take
            self._engine.bus.emit("shield_absorbed", {
                "shield_id": s.shield_id, "amount": take, "remaining": max(0.0, s.remaining),
                "source": source_id, "target": target.actor.actor_id,
            }, self._engine.state)
            if s.remaining <= 1e-9:
                s.remaining = 0.0
                broken.append(s)
        for s in broken:
            target.shields.remove(s)
            self._engine.bus.emit("shield_broken", {
                "shield_id": s.shield_id, "source": source_id, "target": target.actor.actor_id,
            }, self._engine.state)
            self._engine.state.log.append(
                f"AV{self._engine.state.clock:.1f}: {target.actor.name} 的护盾 {s.name} 被击破")
            if s.modifier_id:
                self._remove_modifier(target, s.modifier_id, "shield_broken")
        return overflow
