"""上游 CharacterConfig/Ability → 敌人 sim_schema 的通用编译器.

只按上游节点类型注册转换，不写怪物/技能 ID 分支。TBGD 提供数值与结构；
Fandom 仅由调用方传入名字和受击回能等文本补充。未注册节点、未知动态哈希、
条件分支或目标语义不明都会进入 ``unsupported``，候选不得因此定稿。

执行帧感知翻译（#26 期 2/3，语义锚 23_event_hook_system.md §23.15 +
14_policy.md 概率分支节）：写后读谓词（同技能写入后再 ByCompareDynamicValue/
ByCompareMonsterPhase）与概率分支（ByRandomChance/RandomConfig）编译为
**单 hook + 纯 effect 级 condition**——effect 级 condition 是执行时活读，
读得到帧覆盖层的未提交写入；概率分支前置 ``bind_roll`` 绑定共享掷骰（roll 键
按节点路径生成稳定键）。PostfixExpr 中被写键的动态哈希经键名反查表回落为
``dynamic_of`` 活读。概率分支限主动技能域（事件域可在帧外发射）；战斗级随机
记忆（RandomUnique/RandomMaskKey/RandomCount）保持显式 unsupported。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from hsr_nous.sim_schema.config_ai import dynamic_value_hash

#: 纯表现/动画节点。含机制 TaskList 的动画节点不在此列，由专门处理器递归。
IGNORED_TASK_TYPES = frozenset({
    "RPG.GameCore.AddChallengeBossInfoPanelState",
    "RPG.GameCore.AnimSetParameter",
    "RPG.GameCore.AudioSetRTPCValueByRatio",
    "RPG.GameCore.ChangeTargetModifierEffectState",
    "RPG.GameCore.CharacterChangePhase",
    "RPG.GameCore.CharacterReactionAnimConfig",
    "RPG.GameCore.ClearEntityFollowAttachPoint",
    "RPG.GameCore.DamagePerformFinish",
    "RPG.GameCore.DebugLog",
    "RPG.GameCore.GlobalMainIntensityEffect",
    "RPG.GameCore.GetGapSecondsForSyncWithBgm",
    "RPG.GameCore.HideCharacterFilteredEffect",
    "RPG.GameCore.HideEffectByCharacterType",
    "RPG.GameCore.HideEntityForCurrentCamera",
    "RPG.GameCore.HideLevelStage",
    "RPG.GameCore.HideModifierEffect",
    "RPG.GameCore.LevelAudioState",
    "RPG.GameCore.LevelAudioSwitch",
    "RPG.GameCore.LookAt",
    "RPG.GameCore.MakeCharacterHUDVisible",
    "RPG.GameCore.ModifierAttachEffect",
    "RPG.GameCore.ModifierDetachEffect",
    "RPG.GameCore.MoveToTargetList",
    "RPG.GameCore.MoveToTargetPosition",
    "RPG.GameCore.PlayMonsterHPBarTween",
    "RPG.GameCore.PlayScreenTransfer",
    "RPG.GameCore.PlayTimeline",
    "RPG.GameCore.RadialBlurCurveEffect",
    "RPG.GameCore.RadialBlurEffect",
    "RPG.GameCore.RefreshChangePhaseUI",
    "RPG.GameCore.ReleaseCharacterHUDVisibleControl",
    "RPG.GameCore.RemoveEffect",
    "RPG.GameCore.RemoveChallengeBossInfoPanelState",
    "RPG.GameCore.ResetBattleBGMToStage",
    "RPG.GameCore.ResetHeadLookAt",
    "RPG.GameCore.ScaleCharacterModel",
    "RPG.GameCore.SetAttachmentScale",
    "RPG.GameCore.SetAttachmentVisibility",
    "RPG.GameCore.SetAttachEffectTimeSlow",
    "RPG.GameCore.SetBattleAchievement",
    "RPG.GameCore.SetBattleBGMState",
    "RPG.GameCore.SetCharacterEffectMaterialBlock",
    "RPG.GameCore.SetCharacterPartsVisibility",
    "RPG.GameCore.SetCharacterScaleFollow",
    "RPG.GameCore.SetEffectAnimSpeed",
    "RPG.GameCore.SetEffectAnimatorTrigger",
    "RPG.GameCore.SetEntityFollowAttachPoint",
    "RPG.GameCore.SetEntityPosition",
    "RPG.GameCore.SetEntityVisible",
    "RPG.GameCore.SetLocalOffsetAsMoveTarget",
    "RPG.GameCore.SetMonsterEnergyBarState",
    "RPG.GameCore.SetSimulationSpeedEnable",
    "RPG.GameCore.SetSkillTargetFormationByPos",
    "RPG.GameCore.SetTargetDamageTextVisible",
    "RPG.GameCore.SetTeamFormation",
    "RPG.GameCore.SetTeamRootOffset",
    "RPG.GameCore.SetTriggeredFormationAssetAutoCenter",
    "RPG.GameCore.ShowBattleAlert",
    "RPG.GameCore.ShowBattleUI",
    "RPG.GameCore.ShowBossInfoBar",
    "RPG.GameCore.ShowEntityFloatMessage",
    "RPG.GameCore.ShowSkillTextDialog",
    "RPG.GameCore.ShowUIPage",
    "RPG.GameCore.SkillExecutionStart",
    "RPG.GameCore.SkillPerformFinish",
    "RPG.GameCore.StackStatusDesc",
    "RPG.GameCore.StartAim",
    "RPG.GameCore.StopAim",
    "RPG.GameCore.SyncMonsterLightByCameraDir",
    "RPG.GameCore.TargetTimeSlow",
    "RPG.GameCore.ToggleUITop",
    "RPG.GameCore.TriggerEffect",
    "RPG.GameCore.TriggerEnergyBarEffect",
    "RPG.GameCore.TriggerAnimState",
    "RPG.GameCore.TriggerSound",
    "RPG.GameCore.TriggerUINotify",
    "RPG.GameCore.VCameraConfigChange",
    "RPG.GameCore.WaitAnimEvent",
    "RPG.GameCore.WaitAnimState",
    "RPG.GameCore.WaitParallelTimeStamp",
    "RPG.GameCore.WaitSecond",
    "RPG.GameCore.WaitTimelineFinish",
})

#: 注册表即节点覆盖矩阵；值为 AbilityCompiler 方法名。
TASK_HANDLERS = {
    "RPG.GameCore.AddModifier": "_compile_add_modifier",
    "RPG.GameCore.DamageByAttackProperty": "_compile_damage",
    "RPG.GameCore.DispelStatus": "_compile_dispel_status",
    "RPG.GameCore.DefineDynamicValue": "_compile_define_dynamic",
    "RPG.GameCore.ForceKill": "_compile_force_kill",
    "RPG.GameCore.FireProjectile": "_compile_projectile",
    "RPG.GameCore.FireWaveProjectile": "_compile_wave_projectile",
    "RPG.GameCore.HealHP": "_compile_heal_hp",
    "RPG.GameCore.IncludeTaskListTemplate": "_compile_include_tasks",
    "RPG.GameCore.LoseHPByRatio": "_compile_lose_hp",
    "RPG.GameCore.LoopExecuteTaskList": "_compile_loop",
    "RPG.GameCore.ModifyActionDelay": "_compile_modify_action_delay",
    "RPG.GameCore.ModifySPNew": "_compile_modify_energy",
    "RPG.GameCore.ModifyTeamBoostPoint": "_compile_modify_skill_point",
    "RPG.GameCore.PredicateTaskList": "_compile_predicate_tasks",
    "RPG.GameCore.RandomConfig": "_compile_random_config",
    "RPG.GameCore.Retarget": "_compile_retarget",
    "RPG.GameCore.RemoveModifier": "_compile_remove_modifier",
    "RPG.GameCore.RemoveModifierByBehaviorFlag": "_compile_remove_modifier_by_behavior_flag",
    "RPG.GameCore.RemoveSelfModifier": "_compile_remove_self_modifier",
    "RPG.GameCore.SetActionDelay": "_compile_action_delay",
    "RPG.GameCore.SetDieImmediately": "_compile_set_die",
    "RPG.GameCore.SetDynamicValue": "_compile_define_dynamic",
    "RPG.GameCore.SetDynamicValueByAddValue": "_compile_dynamic_add",
    "RPG.GameCore.SetDynamicValueByCharacterCount": "_compile_character_count",
    "RPG.GameCore.SetDynamicValueByCopying": "_compile_dynamic_copying",
    "RPG.GameCore.SetDynamicValueByHPRatio": "_compile_hp_ratio_dynamic",
    "RPG.GameCore.SetDynamicValueByModifierValue": "_compile_modifier_value",
    "RPG.GameCore.SetDynamicValueByProperty": "_compile_property_value",
    "RPG.GameCore.SetMonsterPhase": "_compile_monster_phase",
    "RPG.GameCore.SummonMonster": "_compile_summon_monster",
    "RPG.GameCore.SwitchCaseByDynamicValue": "_compile_switch",
    "RPG.GameCore.TriggerModifierCustomEvent": "_compile_trigger_modifier_custom_event",
    "RPG.GameCore.TriggerAbility": "_compile_trigger_ability",
    "RPG.GameCore.TriggerAnimStateWithMove": "_compile_animation_events",
    "RPG.GameCore.TurnInsertAbility": "_compile_trigger_ability",
}
EVENT_HANDLERS = {
    "OnDeathrattle": "_compile_deathrattle",
    "OnListenCharacterDie": "_compile_deathrattle",
}

_ELEMENT = {"Thunder": "thunder", "Lightning": "thunder"}


def _is_camera_ability(name: Any) -> bool:
    text = str(name or "")
    return (text.endswith("_Camera") or "_Camera_" in text
            or ("_Camera" in text and text.rsplit("_Camera", 1)[1].isdigit()))


def _element(raw: Any) -> str:
    value = str((raw or {}).get("DamageType") if isinstance(raw, dict) else raw or "").lower()
    return _ELEMENT.get(str((raw or {}).get("DamageType") if isinstance(raw, dict) else raw), value)


def _fixed(raw: Any) -> Any:
    if isinstance(raw, dict) and not raw.get("IsDynamic"):
        return (raw.get("FixedValue") or {}).get("Value")
    return raw


def _atom(value: Any) -> Any:
    return ("atom", value) if isinstance(value, str) else value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _binary(op: str, left: Any, right: Any) -> Any:
    if _is_number(left) and _is_number(right):
        if op == "+":
            return left + right
        if op == "*":
            return left * right
        if op == "-":
            return left - right
        if op == "/":
            if right == 0:
                raise ValueError("PostfixExpr 除数为 0")
            return left / right
    if op == "*":
        parts: List[Any] = []
        for value in (left, right):
            if isinstance(value, tuple) and value and value[0] == "*":
                parts.extend(value[1])
            else:
                parts.append(value)
        coefficient = 1.0
        others = []
        for value in parts:
            if _is_number(value):
                coefficient *= value
            else:
                others.append(value)
        if coefficient == 0:
            return 0.0
        parts = ([] if coefficient == 1 and others else [coefficient]) + others
        if len(parts) == 1:
            return parts[0]
        return ("*", parts)
    return (op, left, right)


def _format(value: Any, parent: str = "") -> str:
    if _is_number(value):
        return str(value)
    if isinstance(value, tuple) and value[0] == "atom":
        return str(value[1])
    op = value[0]
    parts = value[1] if op == "*" else list(value[1:])
    rendered = []
    for part in parts:
        text = _format(part, op)
        if isinstance(part, tuple) and part[0] not in {"atom", op}:
            text = f"({text})"
        rendered.append(text)
    return f" {op} ".join(rendered)


def compile_dynamic_value(raw: Any, symbols: Optional[Dict[int, Any]] = None) -> Any:
    """编译上游 PostfixExpr；支持固定值、动态槽、四则运算及单目取负，其余显式拒绝.

    返回数值或 DSL 表达式字符串。字节码中 0/1 分别为 FixedValues /
    DynamicHashes 下标读取，0x0e 为单目取负，0x11 为结束；未知 opcode 不猜测。
    """
    if not isinstance(raw, dict) or not raw.get("IsDynamic"):
        return _fixed(raw)
    expr = raw.get("PostfixExpr") or {}
    symbols = symbols or {}
    try:
        code = base64.b64decode(str(expr.get("OpCodes") or ""))
    except Exception as exc:
        raise ValueError("PostfixExpr.OpCodes 不是合法 base64") from exc
    fixed = expr.get("FixedValues") or []
    dynamic = expr.get("DynamicHashes") or []
    stack: List[Any] = []
    index = 0
    ended = False
    while index < len(code):
        op = code[index]
        index += 1
        if op in (0, 1):
            if index >= len(code):
                raise ValueError("PostfixExpr 槽读取缺下标")
            slot = code[index]
            index += 1
            source = fixed if op == 0 else dynamic
            if slot >= len(source):
                raise ValueError(f"PostfixExpr {'固定' if op == 0 else '动态'}槽越界：{slot}")
            if op == 0:
                stack.append((source[slot] or {}).get("Value"))
            else:
                key = int(source[slot])
                if key not in symbols:
                    raise ValueError(f"未知 DynamicHash：{key}")
                stack.append(_atom(symbols[key]))
            continue
        operators = {2: "+", 3: "-", 4: "*", 5: "/"}
        if op in operators:
            if len(stack) < 2:
                raise ValueError("PostfixExpr 二元运算栈不足")
            right, left = stack.pop(), stack.pop()
            stack.append(_binary(operators[op], left, right))
            continue
        if op == 14:
            if not stack:
                raise ValueError("PostfixExpr 单目取负栈不足")
            stack.append(_binary("-", 0, stack.pop()))
            continue
        if op == 17:
            ended = True
            break
        raise ValueError(f"未知 PostfixExpr opcode：0x{op:02x}")
    if not ended or len(stack) != 1:
        raise ValueError("PostfixExpr 未正常结束或栈不唯一")
    value = stack[0]
    return value if _is_number(value) else _format(value)


@dataclass
class _Context:
    mode: str
    skill: Dict[str, Any]
    event: str = "on_action"
    condition: str = "true"
    damages: List[Dict[str, Any]] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    pre_effects: List[Dict[str, Any]] = field(default_factory=list)
    seen_damage: bool = False
    conditional_damage: bool = False
    hit_effects: List[Dict[str, Any]] = field(default_factory=list)
    loop_depth: int = 0
    retarget: Any = None
    retarget_damage: bool = False
    retarget_damage_records: List[Dict[str, Any]] = field(default_factory=list)
    current_modifier: str = ""
    dynamic_writes: set[str] = field(default_factory=set)
    count_expressions: Dict[int, str] = field(default_factory=dict)
    lifecycle_hooks: List[Dict[str, Any]] = field(default_factory=list)
    before_dying_stack: Tuple[str, ...] = ()
    summons: List[Dict[str, Any]] = field(default_factory=list)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    handled: List[str] = field(default_factory=list)
    live_condition: str = "true"


class AbilityCompiler:
    """按节点类型递归编译一个敌人的技能与被动."""

    def __init__(
        self,
        enemy_id: str,
        skills: List[Dict[str, Any]],
        sources: Dict[str, Any],
        *,
        semantics: Optional[Dict[str, Dict[str, Any]]] = None,
        level: int = 80,
    ) -> None:
        self.enemy_id = str(enemy_id)
        self.level = int(level)
        self.skills = {str(s.get("trigger_key")): s for s in skills if s.get("trigger_key")}
        self.sources = sources
        self.config = sources.get("character_config") or {}
        self.abilities = sources.get("abilities") or {}
        self.modifiers = sources.get("modifiers") or {}
        self.semantics = semantics or {}
        self.custom_values = sources.get("custom_values") or {}
        self.custom_value_tags = sources.get("custom_value_tags") or []
        self.target_aliases = sources.get("target_aliases") or {}
        self.monster_template_id = str(sources.get("monster_template_id") or self.enemy_id)
        self.config_skills = {
            str(s.get("Name")): s for s in self.config.get("SkillList") or [] if s.get("Name")
        }
        self.dynamic_keys, self.written_dynamic_keys = self._scan_dynamic_keys()
        self.dynamic_symbols = self._character_symbols()
        # 被写键的哈希 → dynamic_of 活读回落（最低优先级符号层）：PostfixExpr 读取
        # 本敌任意已登记动态键（含生成期被写键与 modifier 自槽）时不再"未知哈希"——
        # 活读走四层读链最高优先的帧覆盖层（写后读，#26 期 2/3）；同名哈希冲突不回落。
        name_symbols: Dict[int, str] = {}
        for name in self.dynamic_keys:
            if any(ch in name for ch in "'\"\\"):
                continue
            hashed = dynamic_value_hash(name)
            if hashed in name_symbols:
                name_symbols.pop(hashed, None)   # 冲突撤回落（保持显式拒绝）
            else:
                name_symbols[hashed] = f"dynamic_of($self.actor_id, '{name}')"
        self.dynamic_name_symbols = name_symbols
        # 只读 CustomValue 与 SkillParam 分命名空间，保留 Switch 的哈希冲突检测。
        self.custom_value_symbols = {
            dynamic_value_hash(str(name)): value
            for name, value in self.custom_values.items()
            if _is_number(value) and self._custom_value_is_readonly(str(name))
        }

    def _character_symbols(self) -> Dict[int, Any]:
        out: Dict[int, Any] = {}
        floats = ((self.config.get("DynamicValues") or {}).get("Floats") or {})
        for raw_hash, item in floats.items():
            info = (item or {}).get("ReadInfo") or {}
            if info.get("Type") != "SkillParam":
                continue
            trigger = str(info.get("TriggerKey") or "")
            slot = info.get("Index")
            skill = self.skills.get(trigger) or {}
            params = skill.get("param_list") or []
            if isinstance(slot, int) and 0 <= slot < len(params):
                out[int(raw_hash)] = params[slot]
        return out

    def _issue(self, ctx: _Context, path: str, node_type: str, reason: str) -> None:
        issue = {"path": path, "node_type": node_type, "reason": reason}
        if issue not in ctx.unsupported:
            ctx.unsupported.append(issue)

    @staticmethod
    def _add_effect(ctx: _Context, effect: Dict[str, Any]) -> None:
        if ctx.live_condition != "true":
            # 帧感知分支（写后读/概率）的 effect 级活读守卫：执行时求值，读得到帧
            # 覆盖层（#26 期 2/3）；与 hook 级快照条件（ctx.condition → _condition）
            # 正交互——两层都求值。
            effect = {**effect, "condition": AbilityCompiler._and_condition(
                str(effect.get("condition") or "true"), ctx.live_condition)}
        if ctx.condition != "true":
            effect = {**effect, "_condition": ctx.condition}
            target = effect.get("target")
            if "count_selected" in ctx.condition and isinstance(target, dict) and target.get("take") == 1:
                # 单目标计数门控改在效果执行期过滤，避免读到本事件前序效果前的旧快照。
                target = dict(target)
                target["where"] = AbilityCompiler._and_condition(
                    target.get("where", "true"), ctx.condition)
                effect = {**effect, "target": target, "_condition": "true"}
        if (ctx.mode == "action" and ctx.loop_depth
                and effect.get("effect_type") == "apply_modifier"):
            if effect not in ctx.hit_effects:
                ctx.hit_effects.append(effect)
            return
        if (ctx.mode == "action" and not ctx.seen_damage
                and effect.get("effect_type") != "set_hp_to_percent"):
            ctx.pre_effects.append(effect)
        else:
            ctx.effects.append(effect)

    @staticmethod
    def _add_live_effect(ctx: _Context, effect: Dict[str, Any], guard: str) -> None:
        """帧感知分支的效果入口：guard 链入 ctx.live_condition 后经 _add_effect 落
        **effect 级 condition**（执行时活读，读得到帧覆盖层）。"""
        previous = ctx.live_condition
        ctx.live_condition = AbilityCompiler._and_condition(previous, guard)
        AbilityCompiler._add_effect(ctx, effect)
        ctx.live_condition = previous

    @staticmethod
    def _stable_roll_key(path: str) -> str:
        """概率分支 roll 稳定键：节点路径 sanit 成表达式安全的标识（帧 rolls 表键）."""
        return "R" + "".join(ch if (ch.isalnum() or ch == "_") else "_"
                             for ch in str(path))[:96]

    @staticmethod
    def _make_hooks(ctx: _Context, base_condition: str, *,
                    event: Optional[str] = None,
                    effects: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        groups: List[Tuple[str, List[Dict[str, Any]]]] = []
        selected = ctx.effects if effects is None else effects
        for effect in selected:
            condition = str(effect.get("_condition") or "true")
            clean = {key: value for key, value in effect.items() if key != "_condition"}
            if not groups or groups[-1][0] != condition:
                groups.append((condition, []))
            groups[-1][1].append(clean)
        if any("$last" in condition or "$prev" in condition for condition, _effects in groups):
            # 链内计数必须在同一 hook 内逐效果判定；拆钩会重置 $last/$prev。
            conditioned = []
            for condition, grouped in groups:
                for effect in grouped:
                    if condition != "true":
                        effect = dict(effect)
                        effect["condition"] = (f"({effect['condition']}) and ({condition})"
                                               if effect.get("condition") else condition)
                    conditioned.append(effect)
            return [{"event": event or ctx.event, "condition": base_condition,
                     "effects": conditioned}]
        hooks = []
        for condition, grouped in groups:
            hooks.append({
                "event": event or ctx.event,
                "condition": base_condition if condition == "true"
                else f"({base_condition}) and ({condition})",
                "effects": grouped,
            })
        return hooks

    def _value(self, raw: Any, ctx: _Context, path: str,
               symbols: Optional[Dict[int, Any]] = None) -> Any:
        selected = ({**self.dynamic_name_symbols, **self.custom_value_symbols,
                     **self.dynamic_symbols, **ctx.count_expressions}
                    if symbols is None else {**self.custom_value_symbols, **symbols})
        try:
            return compile_dynamic_value(raw, selected)
        except ValueError as exc:
            self._issue(ctx, path, "DynamicValue", str(exc))
            return None

    def _number(self, raw: Any, ctx: _Context, path: str,
                symbols: Optional[Dict[int, Any]] = None) -> Optional[float]:
        value = self._value(raw, ctx, path, symbols)
        if value is None:
            return None
        if not _is_number(value):
            self._issue(ctx, path, "DynamicValue", f"需要静态数值，得到表达式 {value!r}")
            return None
        return value

    def _compile_tasks(self, tasks: Iterable[Dict[str, Any]], ctx: _Context,
                       path: str, stack: Tuple[str, ...]) -> None:
        rows = list(tasks or [])
        index = 0
        while index < len(rows):
            task = rows[index]
            node_path = f"{path}/{index}"
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                index += 1
                continue
            next_task = rows[index + 1] if index + 1 < len(rows) else {}
            if (node_type == "RPG.GameCore.AddModifier"
                    and (task.get("ModifierName") or {}).get("Value") == "MCommon_SkillTarget"
                    and self.modifiers.get("MCommon_SkillTarget") is None
                    and set(task) <= {"$type", "TargetType", "ModifierName"}
                    and self._alias(task) == self._alias(next_task) == "ParamEntity"
                    and next_task.get("$type") == "RPG.GameCore.TriggerModifierCustomEvent"
                    and (next_task.get("EventType") or {}).get("Value") == 1
                    and next_task.get("DynamicKey") == "DOT_TriggerRatio"):
                # 内建 DoT 事件的寻址标记；trigger_dot 直接寻址，不生成无定义 DSL 件。
                index += 1
                continue
            if node_type in {"RPG.GameCore.ExitBreakState", "RPG.GameCore.ResetStance"}:
                if (node_type == "RPG.GameCore.ExitBreakState"
                        and self._is_default_reset_stance(next_task)
                        and self._alias(next_task) == self._alias(task)):
                    ctx.handled.extend([node_type, "RPG.GameCore.ResetStance"])
                    self._compile_restore_toughness(task, ctx, node_path)
                    index += 2
                    continue
                self._issue(ctx, node_path, node_type,
                            "仅支持同目标相邻的 ExitBreakState + 默认 ResetStance")
                index += 1
                continue
            method_name = TASK_HANDLERS.get(node_type)
            if method_name is None:
                self._issue(ctx, node_path, node_type or "<missing $type>", "未注册任务节点")
                index += 1
                continue
            ctx.handled.append(node_type)
            getattr(self, method_name)(task, ctx, node_path, stack)
            index += 1

    @staticmethod
    def _is_default_reset_stance(task: Dict[str, Any]) -> bool:
        return (task.get("$type") == "RPG.GameCore.ResetStance"
                and "ConstantValue" not in task and "AddValue" not in task
                and not task.get("ForbidWhenEmpty"))

    def _compile_restore_toughness(self, task: Dict[str, Any], ctx: _Context, path: str) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")), "韧性恢复目标未注册")
            return
        self._add_effect(ctx, {"effect_type": "restore_toughness", "target": target})

    def _compile_ability(self, name: str, ctx: _Context, path: str,
                         stack: Tuple[str, ...]) -> None:
        if _is_camera_ability(name):
            return
        ability = self.abilities.get(name)
        if ability is None:
            self._issue(ctx, path, "AbilityReference", f"Ability 定义缺失：{name}")
            return
        if name in stack:
            self._issue(ctx, path, "AbilityReference", f"Ability 循环引用：{' → '.join(stack + (name,))}")
            return
        self._compile_tasks(ability.get("OnStart") or [], ctx, f"{path}:{name}/OnStart",
                            stack + (name,))

    def _compile_trigger_modifier_custom_event(self, task: Dict[str, Any], ctx: _Context,
                                               path: str, stack: Tuple[str, ...]) -> None:
        if ((task.get("EventType") or {}).get("Value") != 1
                or task.get("DynamicKey") != "DOT_TriggerRatio"):
            self._issue(ctx, path, str(task.get("$type")), "未注册 modifier 自定义事件")
            return
        target = self._hook_target(self._alias(task), ctx)
        ratio = self._value(task.get("Value"), ctx, f"{path}/Value")
        if target is None or ratio is None:
            self._issue(ctx, path, str(task.get("$type")), "DoT 引爆目标或比例未注册")
            return
        self._add_effect(ctx, {"effect_type": "trigger_dot", "target": target, "ratio": ratio})

    def _compile_trigger_ability(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("AbilityName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "缺 AbilityName")
            return
        flags = set(task.get("AbortBehaviorFlags") or [])
        if flags:
            previous = ctx.condition
            conditions = []
            for flag in sorted(flags):
                if flag in {"STAT_CTRL", "STAT_Confine"}:
                    conditions.append("not controlled($self.actor_id)")
                elif flag == "Break":
                    conditions.append("not broken_of($self.actor_id)")
                elif flag == "DisableAction":
                    conditions.append("not action_disabled($self.actor_id)")
                else:
                    self._issue(ctx, path, "AbortBehaviorFlags", f"未注册中止旗标：{flag}")
                    return
            ctx.condition = self._and_condition(previous, " and ".join(conditions))
            self._compile_ability(str(name), ctx, path, stack)
            ctx.condition = previous
        else:
            self._compile_ability(str(name), ctx, path, stack)

    def _compile_animation_events(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        for index, event in enumerate(task.get("EventList") or []):
            self._compile_tasks(event.get("TaskList") or [], ctx,
                                f"{path}/EventList/{index}/TaskList", stack)

    def _compile_projectile(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        hits = task.get("OnProjectileHit") or []
        if not hits:
            return  # 无命中任务的投射物仅承担表现。
        if ctx.retarget is not None:
            self._issue(ctx, path, str(task.get("$type")), "Retarget 内投射物主目标未证明")
            return
        if self._alias(task) not in {"", "AbilityTargetEntity"}:
            self._issue(ctx, path, str(task.get("$type")), "投射物目标不是 Action 主目标")
            return
        for index, item in enumerate(hits):
            node_type = str(item.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                continue
            if node_type == "RPG.GameCore.DamageByAttackProperty":
                if self._alias(item) not in {"ProjectileHitEntity", "AbilityTargetEntity"}:
                    self._issue(ctx, f"{path}/OnProjectileHit/{index}", node_type,
                                "仅支持主目标直接命中伤害，其他命中任务尚未注册")
                    continue
                direct = dict(item)
                direct["TargetType"] = {
                    "$type": "RPG.GameCore.TargetAlias", "Alias": "AbilityTargetEntity"}
                self._compile_damage(direct, ctx, f"{path}/OnProjectileHit/{index}", stack)
            else:
                self._compile_tasks([item], ctx, f"{path}/OnProjectileHit/{index}", stack)

    def _compile_wave_projectile(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        if ctx.retarget is not None:
            self._issue(ctx, path, str(task.get("$type")), "Retarget 内 Wave 投射物主目标未证明")
            return
        if self._alias(task) not in {"", "EnemyTeamEntity", "AllEnemy", "AbilityTargetEntity"}:
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物目标未注册")
            return
        count = self._number(task.get("Count"), ctx, f"{path}/Count")
        if count is None or count < 1 or int(count) != count:
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物次数必须是正整数")
            return
        damage = task.get("PerProjectileDamage")
        if not isinstance(damage, dict):
            if damage is not None:
                self._issue(ctx, path, str(task.get("$type")), "Wave 投射物伤害节点未注册")
            return
        if not self._presentation_only(task.get("OnProjectileHitClientOnly") or []):
            self._issue(ctx, path, str(task.get("$type")), "Wave 投射物命中后任务未注册")
            return
        for index in range(int(count)):
            self._compile_damage(damage, ctx, f"{path}/PerProjectileDamage/{index}", stack)

    def _compile_include_tasks(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        if set(task) - {"$type", "Name"}:
            self._issue(ctx, path, str(task.get("$type")), "带参数 TaskListTemplate 尚未注册")
            return
        template_name = str(task.get("Name") or "")
        owner = next((name for name in reversed(stack) if name in self.abilities), "")
        container = (self.abilities.get(owner) if owner
                     else self.modifiers.get(ctx.current_modifier) or {})
        rows = container.get("TaskListTemplate") or []
        template = next((row for row in rows if row.get("Name") == template_name), None)
        if template is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"局部 TaskListTemplate 缺失或属未收编全局作用域：{template_name}")
            return
        scope = owner or ctx.current_modifier or "<unknown>"
        key = f"{scope}/TaskListTemplate/{template_name}"
        if key in stack:
            self._issue(ctx, path, str(task.get("$type")), f"TaskListTemplate 循环引用：{key}")
            return
        self._compile_tasks(template.get("TaskList") or [], ctx, f"{path}:{key}", stack + (key,))

    def _compile_loop(self, task: Dict[str, Any], ctx: _Context,
                      path: str, stack: Tuple[str, ...]) -> None:
        count = self._number(task.get("MaxLoopCount"), ctx, f"{path}/MaxLoopCount")
        if count is None or count < 1 or int(count) != count:
            self._issue(ctx, path, str(task.get("$type")), "循环次数必须是正整数")
            return
        for index in range(int(count)):
            ctx.loop_depth += 1
            self._compile_tasks(task.get("TaskList") or [], ctx,
                                f"{path}/Loop/{index}/TaskList", stack)
            ctx.loop_depth -= 1

    def _presentation_only(self, tasks: Iterable[Dict[str, Any]]) -> bool:
        """条件分支是否纯表现；只有整棵子树都可证明无机制效果时才可忽略."""
        for task in tasks or []:
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                continue
            if node_type == "RPG.GameCore.TriggerAbility":
                raw = task.get("AbilityName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if _is_camera_ability(name):
                    continue
                return False
            if node_type == "RPG.GameCore.TriggerAnimStateWithMove":
                if all(self._presentation_only(event.get("TaskList") or [])
                       for event in task.get("EventList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.AddBuffPerform":
                if self._presentation_only(task.get("TaskList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.PredicateTaskList":
                if (self._presentation_only(task.get("SuccessTaskList") or [])
                        and self._presentation_only(task.get("FailedTaskList") or [])):
                    continue
                return False
            if node_type == "RPG.GameCore.RandomConfig":
                if all(self._presentation_only(
                        option if isinstance(option, list) else [option])
                        for option in task.get("TaskList") or []):
                    continue
                return False
            return False
        return True

    def _visual_tasks(self, tasks: Iterable[Dict[str, Any]]) -> bool:
        for task in tasks or []:
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES or node_type in {
                    "RPG.GameCore.RemoveModifier", "RPG.GameCore.RemoveSelfModifier"}:
                continue
            if node_type == "RPG.GameCore.AddModifier":
                raw = task.get("ModifierName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if str(name) == "Monster_APShow" and self.modifiers.get(str(name)) is None:
                    continue
            if node_type == "RPG.GameCore.TriggerAbility":
                raw = task.get("AbilityName")
                name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
                if _is_camera_ability(name):
                    continue
                return False
            if node_type == "RPG.GameCore.TriggerAnimStateWithMove":
                if all(self._visual_tasks(event.get("TaskList") or [])
                       for event in task.get("EventList") or []):
                    continue
                return False
            if node_type == "RPG.GameCore.PredicateTaskList":
                if (self._visual_tasks(task.get("SuccessTaskList") or [])
                        and self._visual_tasks(task.get("FailedTaskList") or [])):
                    continue
                return False
            return False
        return True

    def _visual_modifier(self, definition: Dict[str, Any]) -> bool:
        return all(self._visual_tasks(callback.get("CallbackConfig") or [])
                   for callback in definition.get("_CallbackList") or [])

    def _modifier_used_in_predicates(self, name: str) -> bool:
        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                if value.get("$type") == "RPG.GameCore.ByIsContainModifier":
                    raw = value.get("ModifierName")
                    wanted = raw.get("Value") if isinstance(raw, dict) else raw
                    if str(wanted) == name:
                        return True
                return any(walk(child) for child in value.values())
            if isinstance(value, list):
                return any(walk(child) for child in value)
            return False
        return any(walk(ability) for ability in self.abilities.values())

    @staticmethod
    def _and_condition(left: str, right: str) -> str:
        if left == "true":
            return right
        if right == "true":
            return left
        return f"({left}) and ({right})"

    @staticmethod
    def _negate_condition(expression: str) -> str:
        return f"not {expression}" if " " not in expression else f"not ({expression})"

    @staticmethod
    def _compare_operator(raw: Any) -> Optional[str]:
        return {"Equal": "==", "NotEqual": "!=", "Greater": ">",
                "GreaterEqual": ">=", "Less": "<", "LessEqual": "<="}.get(str(raw or "Equal"))

    @staticmethod
    def _predicate_target(alias: str) -> Optional[str]:
        return {"ParamEntity": "$it", "AbilityTargetEntity": "$event.target",
                "Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
                "": "$self.actor_id"}.get(alias)

    def _static_monster_predicate(self, predicate: Dict[str, Any]) -> Optional[bool]:
        """仅供属性编译期选支：怪物 ID 及其布尔组合可在生成期唯一求值."""
        node_type = str((predicate or {}).get("$type") or "")
        if node_type == "RPG.GameCore.ByCompareMonsterID":
            if self._alias(predicate) not in {"", "Caster", "ModifierOwnerEntity"}:
                return None
            raw = predicate.get("TargetMonsterID")
            if isinstance(raw, dict) and raw.get("IsDynamic"):
                return None
            value = _fixed(raw)
            if not _is_number(value):
                return None
            result = str(self.enemy_id) == str(int(value))
            return not result if predicate.get("Inverse") else result
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            values = [self._static_monster_predicate(child)
                      for child in predicate.get("PredicateList") or []]
            if not values or any(value is None for value in values):
                return None
            return all(values) if node_type.endswith("ByAnd") else any(values)
        if node_type == "RPG.GameCore.ByNot":
            value = self._static_monster_predicate(predicate.get("Predicate") or {})
            return None if value is None else not value
        return None

    def _predicate_reads_written(self, predicate: Dict[str, Any], ctx: _Context) -> bool:
        """谓词树是否读取了本技能已写入的动态值/阶段（写后读——必须走 effect 级活读，
        hook 级快照发生在任何 effect 之前，读不到帧覆盖层；#26 期 2/3）."""
        node_type = str((predicate or {}).get("$type") or "")
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            raw_key = predicate.get("DynamicKey") or {}
            key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
            return str(key) in ctx.dynamic_writes
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            return "current_phase" in ctx.dynamic_writes
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            return any(self._predicate_reads_written(child, ctx)
                       for child in predicate.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByNot":
            return self._predicate_reads_written(predicate.get("Predicate") or {}, ctx)
        return False

    def _predicate_expr(self, predicate: Dict[str, Any], ctx: _Context,
                        path: str, *, allow_written: bool = False) -> Optional[str]:
        node_type = str((predicate or {}).get("$type") or "")
        alias = self._alias(predicate)
        target = self._predicate_target(alias)
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            if target is None:
                self._issue(ctx, path, node_type, f"动态值谓词目标未注册：{alias}")
                return None
            raw_key = predicate.get("DynamicKey") or {}
            key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if not key or compare is None or operator is None:
                self._issue(ctx, path, node_type, "动态值键/比较值/比较符未注册")
                return None
            count_expr = ctx.count_expressions.get(dynamic_value_hash(str(key)))
            if count_expr is not None and target == "$self.actor_id":
                return f"({count_expr}) {operator} {compare}"
            if str(key) in ctx.dynamic_writes and not allow_written:
                # 调用方（Retarget where/目标过滤等无 effect 级 condition 承载的语境）
                # 无法表达写后读活读——保持拒绝；PredicateTaskList 分支走 allow_written。
                self._issue(ctx, path, node_type, "写后读谓词仅限 PredicateTaskList 分支活读")
                return None
            namespace = "$self" if target == "$self.actor_id" else target
            return f"dynamic_of({namespace}, '{key}') {operator} {compare}"
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            if alias not in {"", "Caster", "ModifierOwnerEntity"}:
                self._issue(ctx, path, node_type, f"阶段谓词目标未注册：{alias}")
                return None
            if "current_phase" in ctx.dynamic_writes and not allow_written:
                self._issue(ctx, path, node_type, "写后读阶段谓词仅限 PredicateTaskList 分支活读")
                return None
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "阶段比较值/比较符未注册")
                return None
            return f"dynamic_of($self, 'current_phase') {operator} {compare}"
        if node_type == "RPG.GameCore.ByCompareMonsterRank":
            if target is None:
                self._issue(ctx, path, node_type, f"怪物等级谓词目标未注册：{alias}")
                return None
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "怪物等级比较值/比较符未注册")
                return None
            expr = f"monster_rank({target}) {operator} {compare}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareCharacterID":
            if target is None:
                self._issue(ctx, path, node_type, f"角色 ID 谓词目标未注册：{alias}")
                return None
            character_id = self._number(
                predicate.get("TargetCharacterID"), ctx, f"{path}/TargetCharacterID")
            if character_id is None:
                return None
            expr = f"character_id({target}) == '{int(character_id)}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareMonsterID":
            if target is None:
                self._issue(ctx, path, node_type, f"怪物 ID 谓词目标未注册：{alias}")
                return None
            monster_id = self._number(predicate.get("TargetMonsterID"), ctx, f"{path}/TargetMonsterID")
            if monster_id is None:
                return None
            if alias in {"", "Caster"}:
                expr = "1 == 1" if str(self.enemy_id) == str(int(monster_id)) else "1 == 0"
            else:
                expr = f"monster_id({target}) == '{int(monster_id)}'"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareMonsterTemplateID":
            if alias not in {"", "Caster", "ModifierOwnerEntity"}:
                self._issue(ctx, path, node_type, f"怪物模板 ID 谓词目标未注册：{alias}")
                return None
            monster_id = self._number(
                predicate.get("TargetMonsterTemplateID"), ctx, f"{path}/TargetMonsterTemplateID")
            if monster_id is None:
                return None
            expr = "1 == 1" if self.monster_template_id == str(int(monster_id)) else "1 == 0"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCheckCustomValueBool":
            if target is None:
                self._issue(ctx, path, node_type, f"CustomValueBool 目标未注册：{alias}")
                return None
            raw_key = predicate.get("Key") or {}
            if raw_key.get("Value") is not None:
                tags = [str(raw_key["Value"])]
            else:
                try:
                    key_hash = int(raw_key.get("Hash"))
                except (TypeError, ValueError):
                    self._issue(ctx, path, node_type, "CustomValueBool 缺有效 Key.Hash")
                    return None
                tags = [tag for tag in self.custom_value_tags
                        if dynamic_value_hash(str(tag)) == key_hash]
            if len(tags) != 1 or "'" in tags[0]:
                self._issue(ctx, path, node_type, "CustomValueBool 哈希缺失、冲突或含非法字符")
                return None
            expr = f"in_group({target}, '{tags[0]}')"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareModifierValue":
            raw_name = predicate.get("ModifierName")
            name = (raw_name.get("Value") if isinstance(raw_name, dict) else raw_name) \
                or ctx.current_modifier
            value_type = predicate.get("ValueType")
            if value_type not in {"Layer", "LifeTime"} or target is None or not name:
                self._issue(ctx, path, node_type, "modifier 数值类型/目标/名称未注册")
                return None
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "modifier 数值比较值/比较符未注册")
                return None
            definition = self.modifiers.get(str(name)) or {}
            modifier_id = self._modifier_id(
                str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            reader = "stacks" if value_type == "Layer" else "modifier_duration"
            return f"{reader}({target}, '{modifier_id}') {operator} {compare}"
        if node_type == "RPG.GameCore.ByContainBehaviorFlag":
            if target is None:
                self._issue(ctx, path, node_type, f"BehaviorFlag 目标未注册：{alias}")
                return None
            flag = predicate.get("Flag")
            if flag == "Shield":
                expr = f"has_shield({target})"
            elif flag in {"STAT_CTRL", "STAT_Confine"}:
                expr = f"controlled({target})"
            elif flag == "Break":
                expr = f"broken_of({target})"
            elif flag == "STAT_DOT":
                expr = f"dot_count({target}) > 0"
            elif flag == "DisableAction":
                expr = f"action_disabled({target})"
            elif flag == "Taunt":
                expr = f"controlled({target}, 'taunt')"
            else:
                self._issue(ctx, path, node_type, f"未注册 BehaviorFlag：{flag}")
                return None
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByIsContainModifier":
            if target is None:
                self._issue(ctx, path, node_type, f"modifier 谓词目标未注册：{alias}")
                return None
            raw = predicate.get("ModifierName") or {}
            name = raw.get("Value") if isinstance(raw, dict) else raw
            definition = self.modifiers.get(str(name)) or {}
            modifier_id = self._modifier_id(
                str(name), definition, str(ctx.skill.get("skill_id") or self.enemy_id))
            source = predicate.get("CasterFilter")
            if source is None:
                expr = f"has_modifier({target}, '{modifier_id}')"
            else:
                source_alias = self._alias({"TargetType": source})
                if source_alias != "Caster":
                    self._issue(ctx, path, node_type, f"CasterFilter 未注册：{source_alias}")
                    return None
                if ctx.event in {"on_apply", "after_remove_modifier"}:
                    source_expr = "$event.source"
                elif ctx.event == "before_actor_exit":
                    current_definition = self.modifiers.get(ctx.current_modifier) or {}
                    current_id = self._modifier_id(
                        ctx.current_modifier, current_definition,
                        str(ctx.skill.get("skill_id") or self.enemy_id))
                    source_expr = f"modifier_source($event.actor, '{current_id}')"
                else:
                    source_expr = "$self.actor_id"
                expr = f"has_modifier({target}, '{modifier_id}', {source_expr})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByHasSummonRelation":
            summoner = self._predicate_target(self._alias({"TargetType": predicate.get("SummonerType")}))
            servant = self._predicate_target(self._alias({"TargetType": predicate.get("ServantType")}))
            if summoner is None or servant is None:
                self._issue(ctx, path, node_type, "召唤关系目标未注册")
                return None
            expr = f"summoner_of({servant}) == {summoner}"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByTargetEntityType":
            mask = predicate.get("EntityTypeMask")
            alive_mask = predicate.get("AliveStateMask")
            if target is None or mask not in {"Avatar", "Servant"} or alive_mask not in {None, "Anyone"}:
                self._issue(ctx, path, node_type,
                            f"实体类型目标/掩码未注册：{alias} / {mask} / {alive_mask}")
                return None
            expr = f"actor_type_of({target}) == 'summon' or summoner_of({target}) != ''"
            negate = (mask == "Avatar") != bool(predicate.get("Inverse"))
            return self._negate_condition(expr) if negate else expr
        if node_type == "RPG.GameCore.ByCompareTarget":
            other = str((predicate.get("CompareType") or {}).get("Alias") or "")
            if target is None or other != "Caster":
                self._issue(ctx, path, node_type, f"目标比较未注册：{alias} / {other}")
                return None
            return (f"{target} != $self.actor_id" if predicate.get("Inverse")
                    else f"{target} == $self.actor_id")
        if node_type == "RPG.GameCore.ByTargetAliveState":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"
            if target is None or predicate.get("AliveStateMask") != "Mask_AliveOnly":
                self._issue(ctx, path, node_type,
                            f"存活谓词目标/掩码未注册：{alias} / {predicate.get('AliveStateMask')}")
                return None
            expr = f"actor_alive({target})"
            return self._negate_condition(expr) if predicate.get("Inverse") else expr
        if node_type == "RPG.GameCore.ByCompareHP":
            if alias in {"CasterSummoner", "ModifierOwnerSummoner"}:
                target = "summoner_of($self.actor_id)"
            if target is None:
                self._issue(ctx, path, node_type, f"HP 谓词目标未注册：{alias}")
                return None
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "HP 比较值/比较符未注册")
                return None
            return f"hp_of({target}) {operator} {compare}"
        if node_type == "RPG.GameCore.ByCompareHPRatio":
            if target is None:
                self._issue(ctx, path, node_type, f"HP 比例谓词目标未注册：{alias}")
                return None
            compare = self._number(predicate.get("CompareValue"), ctx, f"{path}/CompareValue")
            operator = self._compare_operator(predicate.get("CompareType"))
            if compare is None or operator is None:
                self._issue(ctx, path, node_type, "HP 比例比较值/比较符未注册")
                return None
            return f"({target}.hp / {target}.max_hp) {operator} {compare}"
        if node_type in {"RPG.GameCore.ByCompareCharacterNumber", "RPG.GameCore.ByCompareTargetCount"}:
            if node_type == "RPG.GameCore.ByCompareTargetCount" and not predicate.get("AliveOnly"):
                self._issue(ctx, path, node_type, "只支持 AliveOnly=true 的存活人数谓词")
                return None
            target_raw = predicate.get("TargetType")
            if (predicate.get("Predicate") or alias in self.target_aliases
                    or alias in {
                        "AbilityTargetAdjoinEntity", "AbilityTargetAndAdjoinEntity",
                        "CasterAdjoinEntity", "AllLightTeam.RemoveServant",
                        "CasterSummonedMinions"}
                    or (isinstance(target_raw, dict)
                        and target_raw.get("$type") == "RPG.GameCore.TargetSequence")):
                count_expr = self._count_expression(
                    target_raw, ctx, path, predicate.get("Predicate"))
            else:
                count_expr = {
                    "AllTeammate": "enemies_alive()", "AllDarkTeam": "enemies_alive()",
                    "AllTeamMember": "enemies_alive()",
                    "AllDarkTeamWithAllDarkTeamUnselectable": "enemies_alive()",
                    "AllDarkTeam - Caster": "(enemies_alive() - 1)",
                    "AllEnemy": "count($team.actor_id)", "AllLightTeam": "count($team.actor_id)",
                    "AllLightTeamIgnoreServant": "count_selected(\"allies\", \"actor_type_of($it) != 'summon'\")",
                }.get(alias)
            raw_compare = (predicate.get("CompareNumber")
                           if node_type == "RPG.GameCore.ByCompareCharacterNumber"
                           else predicate.get("Number"))
            compare = self._number(raw_compare, ctx, f"{path}/CompareNumber")
            operator = self._compare_operator(predicate.get("CompareType"))
            if count_expr is None or compare is None or operator is None:
                self._issue(ctx, path, node_type, f"人数谓词目标/比较值未注册：{alias}")
                return None
            return f"{count_expr} {operator} {compare}"
        if node_type in {"RPG.GameCore.ByAnd", "RPG.GameCore.ByAny"}:
            joiner = " and " if node_type.endswith("ByAnd") else " or "
            parts = [self._predicate_expr(child, ctx, f"{path}/PredicateList/{index}")
                     for index, child in enumerate(predicate.get("PredicateList") or [])]
            if not parts or any(part is None for part in parts):
                return None
            return "(" + joiner.join(parts) + ")"
        if node_type == "RPG.GameCore.ByNot":
            child = self._predicate_expr(predicate.get("Predicate") or {}, ctx, f"{path}/Predicate")
            return self._negate_condition(child) if child is not None else None
        self._issue(ctx, path, node_type or "<missing $type>", "未注册条件谓词")
        return None

    def _damage_only_records(self, tasks: Iterable[Dict[str, Any]], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> Optional[List[Dict[str, Any]]]:
        """在隔离上下文中验证任务树是否仅含主动伤害，不污染正式效果/写入状态."""
        if ctx.condition != "true":
            return None
        probe = _Context(
            mode=ctx.mode, skill=ctx.skill, event=ctx.event, condition=ctx.condition,
            loop_depth=ctx.loop_depth, retarget=ctx.retarget,
            current_modifier=ctx.current_modifier, dynamic_writes=set(ctx.dynamic_writes),
            before_dying_stack=ctx.before_dying_stack,
        )
        self._compile_tasks(tasks, probe, path, stack)
        if (probe.unsupported or probe.effects or probe.pre_effects or probe.hit_effects
                or probe.lifecycle_hooks or probe.summons or probe.retarget_damage
                or probe.conditional_damage
                or probe.dynamic_writes != ctx.dynamic_writes or not probe.damages):
            return None
        return probe.damages

    def _compile_probability_guards(self, task: Dict[str, Any], ctx: _Context,
                                    path: str) -> Optional[Tuple[str, str]]:
        """`ByRandomChance` 谓词 → (success 守卫, failed 守卫)；非该谓词或不可用返回 None.

        真实数据 109 节点全为静态 `Chance`（0-1）+ 无 Inverse；Chance 可动态（表达式）。
        守卫用 effect 级 condition 承载——hook 级快照发生在任何 effect 之前，概率分支
        必须落 effect 级（执行帧 §23.15）。"""
        predicate = task.get("Predicate") or {}
        if str(predicate.get("$type") or "") != "RPG.GameCore.ByRandomChance":
            return None
        raw_chance = predicate.get("Chance", predicate.get("CompareValue"))
        chance = self._value(raw_chance, ctx, f"{path}/Predicate/Chance")
        if chance is None:
            self._issue(ctx, path, str(predicate.get("$type")), "概率分支的 Chance 未注册")
            return None
        shown = f"({chance})" if isinstance(chance, str) else str(chance)
        key = self._stable_roll_key(f"{path}/Predicate/ByRandomChance")
        less = f"roll('{key}') < {shown}"
        no_less = f"roll('{key}') >= {shown}"
        if predicate.get("Inverse"):
            less, no_less = no_less, less
        self._add_live_effect(ctx, {
            "effect_type": "bind_roll", "roll_key": key}, "true")
        return less, no_less

    def _compile_live_branch(self, tasks: List[Dict[str, Any]], guard: str,
                             ctx: _Context, path: str, stack: Tuple[str, ...]) -> None:
        """帧感知分支编译：守卫落 effect 级活读（写后读/概率共用），伤害记录按分支
        条件重发为 deal_damage（同既有条件伤害口径，但条件走 effect 级）。"""
        previous = ctx.live_condition
        ctx.live_condition = self._and_condition(previous, guard)
        before = len(ctx.damages)
        self._compile_tasks(tasks, ctx, path, stack)
        if len(ctx.damages) != before:
            if before == 0:
                self._issue(ctx, path, "ConditionalDamage",
                            "条件主伤或后续主伤重排尚未由 Action/Hook 时序表达")
                del ctx.damages[before:]
                ctx.live_condition = previous
                return
            added = list(ctx.damages[before:])
            del ctx.damages[before:]
            for record in added:
                target = self._hook_target(record["alias"], ctx)
                if target is None:
                    self._issue(ctx, path, "ConditionalDamage",
                                f"条件附加段目标未注册：{record['alias']}")
                    continue
                self._add_live_effect(ctx, {
                    "effect_type": "deal_damage", "target": target,
                    "damage_type": record["element"],
                    "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": record["ratio"],
                    "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                      else float(ctx.skill.get("sp_hit_base") or 0)
                                      * (record["stance_ratio"] or 0)),
                }, "true")
        ctx.live_condition = previous

    def _compile_predicate_tasks(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        if (self._presentation_only(task.get("SuccessTaskList") or [])
                and self._presentation_only(task.get("FailedTaskList") or [])):
            return
        is_chance = str((task.get("Predicate") or {}).get("$type") or "") == \
            "RPG.GameCore.ByRandomChance"
        probability: Optional[Tuple[str, str]] = None
        if is_chance:
            if ctx.mode != "action":
                # 事件域概率分支可在帧外发射（DoT 跳伤致死等）——bind_roll/roll 需要
                # 活动执行帧，显式拒收不猜（14_policy.md 概率分支节）。
                self._issue(ctx, path, str(task.get("$type")),
                            "事件域概率分支可在执行帧外发射，暂不注册")
                return
            probability = self._compile_probability_guards(task, ctx, path)
            if probability is None:
                return   # Chance 不可用已记 unsupported
        live = probability is not None or self._predicate_reads_written(
            task.get("Predicate") or {}, ctx)
        predicate = None
        if probability is not None:
            success_guard, failed_guard = probability
        else:
            predicate = self._predicate_expr(
                task.get("Predicate") or {}, ctx, f"{path}/Predicate",
                allow_written=live)
            if predicate is None:
                self._issue(ctx, path, str(task.get("$type")), "条件谓词或分支未完整支持")
                return
            success_guard, failed_guard = predicate, self._negate_condition(predicate)
        success = self._damage_only_records(
            task.get("SuccessTaskList") or [], ctx, f"{path}/SuccessTaskList", stack)
        failed = self._damage_only_records(
            task.get("FailedTaskList") or [], ctx, f"{path}/FailedTaskList", stack)
        if success is not None and success == failed:
            # 两支规范化伤害完全相同：条件与伤害无关，只在原位置结算一次。
            self._compile_tasks(task.get("SuccessTaskList") or [], ctx,
                                f"{path}/SharedDamage", stack)
            return
        if live:
            # 帧感知路径：守卫全落 effect 级活读，不动 hook 级 ctx.condition
            # （外层快照条件若存在仍叠加生效——_add_live_effect 正交互）。
            base_counts = dict(ctx.count_expressions)
            self._compile_live_branch(
                task.get("SuccessTaskList") or [], success_guard,
                ctx, f"{path}/SuccessTaskList", stack)
            ctx.count_expressions = dict(base_counts)
            self._compile_live_branch(
                task.get("FailedTaskList") or [], failed_guard,
                ctx, f"{path}/FailedTaskList", stack)
            ctx.count_expressions = base_counts
            return
        base = ctx.condition
        base_counts = dict(ctx.count_expressions)
        for branch, tasks in (("SuccessTaskList", task.get("SuccessTaskList") or []),
                              ("FailedTaskList", task.get("FailedTaskList") or [])):
            condition = predicate if branch == "SuccessTaskList" else self._negate_condition(predicate)
            ctx.condition = self._and_condition(base, condition)
            ctx.count_expressions = dict(base_counts)
            before = len(ctx.damages)
            self._compile_tasks(tasks, ctx, f"{path}/{branch}", stack)
            if len(ctx.damages) != before:
                if before == 0:
                    self._issue(ctx, f"{path}/{branch}", "ConditionalDamage",
                                "条件主伤或后续主伤重排尚未由 Action/Hook 时序表达")
                    del ctx.damages[before:]
                    continue
                added = list(ctx.damages[before:])
                del ctx.damages[before:]
                for record in added:
                    target = self._hook_target(record["alias"], ctx)
                    if target is None:
                        self._issue(ctx, f"{path}/{branch}", "ConditionalDamage",
                                    f"条件附加段目标未注册：{record['alias']}")
                        continue
                    self._add_effect(ctx, {
                        "effect_type": "deal_damage", "target": target,
                        "damage_type": record["element"],
                        "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": record["ratio"],
                        "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                          else float(ctx.skill.get("sp_hit_base") or 0)
                                          * (record["stance_ratio"] or 0)),
                    })
        ctx.condition = base
        ctx.count_expressions = base_counts

    @staticmethod
    def _string_literal(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _target_spec(self, raw: Any, ctx: _Context, path: str,
                     seen: Tuple[str, ...] = ()) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            self._issue(ctx, path, "TargetType", "目标规格不是对象")
            return None
        node_type = str(raw.get("$type") or "")
        if node_type == "RPG.GameCore.TargetAlias":
            alias = str(raw.get("Alias") or "")
            if alias in seen:
                self._issue(ctx, path, node_type, f"目标别名循环引用：{alias}")
                return None
            if alias in self.target_aliases:
                return self._target_spec(self.target_aliases[alias], ctx, path, seen + (alias,))
            if alias == "ParamEntity":
                if ctx.retarget is None:
                    self._issue(ctx, path, node_type, "ParamEntity 缺少 Retarget 语境")
                    return None
                return dict(ctx.retarget)
            pool = {
                "AllTeammate": "enemies", "AllDarkTeam": "enemies", "AllTeamMember": "enemies",
                "AllDarkTeamWithAllDarkTeamUnselectable": "enemies",
                "AllEnemy": "allies", "AllLightTeam": "allies", "AllLightTeamIgnoreServant": "allies",
                "AllLightTeam.RemoveServant": "allies",
                "Caster": "self", "AbilityTargetAdjoinEntity": "allies",
                "AbilityTargetAndAdjoinEntity": "allies", "CasterAdjoinEntity": "enemies",
                "CasterSummonedMinions": "enemies", "AbilityTargetEntity": "$event.target",
            }.get(alias)
            if pool is None:
                self._issue(ctx, path, node_type, f"目标别名未注册：{alias}")
                return None
            spec: Dict[str, Any] = {"pool": pool}
            if alias == "CasterSummonedMinions":
                spec["where"] = "$it.summoner_id == $self.actor_id"
            elif alias == "AllDarkTeam - Caster":
                spec["where"] = "$it.actor_id != $self.actor_id"
            elif alias == "AllLightTeamIgnoreServant":
                spec["where"] = "actor_type_of($it) != 'summon'"
            elif alias == "AllLightTeam.RemoveServant":
                spec["where"] = "not $it.summoner_id"
            elif alias == "AbilityTargetAdjoinEntity":
                spec["where"] = "is_adjacent($it, $event.target)"
            elif alias == "AbilityTargetAndAdjoinEntity":
                spec["where"] = (
                    "($it.actor_id == $event.target or is_adjacent($it, $event.target))")
            elif alias == "CasterAdjoinEntity":
                spec["where"] = "is_adjacent($it, $self.actor_id)"
            return spec
        if node_type != "RPG.GameCore.TargetSequence":
            self._issue(ctx, path, node_type or "<missing $type>", "目标规格类型未注册")
            return None
        spec: Dict[str, Any] = {}
        has_base = False
        for index, item in enumerate(raw.get("Sequence") or []):
            item_type = str(item.get("$type") or "")
            if item_type == "RPG.GameCore.TargetAlias":
                if has_base:
                    self._issue(ctx, path, item_type, "TargetSequence 多基础别名尚未注册")
                    return None
                base = self._target_spec(item, ctx, f"{path}/Sequence/{index}", seen)
                if base is None:
                    return None
                spec = base
                has_base = True
            elif item_type == "RPG.GameCore.TargetFilter":
                where = self._predicate_expr(item.get("Predicate") or {}, ctx,
                                             f"{path}/Sequence/{index}/Predicate")
                if where is None:
                    return None
                spec["where"] = self._and_condition(spec.get("where", "true"), where)
            elif item_type == "RPG.GameCore.TargetSortByFormation":
                spec["order_by"] = "-formation" if item.get("HighestFirst") else "formation"
            elif item_type == "RPG.GameCore.TargetTake":
                count = self._number(item.get("Count"), ctx, f"{path}/Sequence/{index}/Count")
                if count is None or count < 1 or int(count) != count:
                    self._issue(ctx, path, item_type, "TargetTake 需要正整数")
                    return None
                spec["take"] = int(count)
            else:
                self._issue(ctx, path, item_type or "<missing $type>", "TargetSequence 子节点未注册")
                return None
        if not has_base:
            self._issue(ctx, path, node_type, "TargetSequence 缺基础别名")
            return None
        return spec

    def _count_expression(self, raw: Any, ctx: _Context, path: str,
                          extra_predicate: Optional[Dict[str, Any]] = None) -> Optional[str]:
        spec = self._target_spec(raw, ctx, path)
        if spec is None:
            return None
        if "take" in spec or str(spec["pool"]).startswith("$event."):
            self._issue(ctx, path, "TargetCount", "带截取或事件池的人数计数尚未注册")
            return None
        if extra_predicate is not None:
            where = self._predicate_expr(extra_predicate, ctx, f"{path}/Predicate")
            if where is None:
                return None
            spec["where"] = self._and_condition(spec.get("where", "true"), where)
        pool = self._string_literal(str(spec["pool"]))
        where = self._string_literal(str(spec.get("where", "true")))
        return f"count_selected({pool}, {where})"

    def _compile_retarget(self, task: Dict[str, Any], ctx: _Context,
                          path: str, stack: Tuple[str, ...]) -> None:
        alias = self._alias(task)
        spec = self._target_spec(task.get("TargetType"), ctx, path)
        if spec is None:
            return
        number = self._value(task.get("MaxNumber"), ctx, f"{path}/MaxNumber") \
            if "MaxNumber" in task else None
        if number is not None:
            if _is_number(number):
                if number < 1 or int(number) != number:
                    self._issue(ctx, path, str(task.get("$type")), "Retarget 上限需要正整数")
                    return
                spec["take"] = int(number)
            else:
                spec["take"] = number
        # 非随机缺省 MaxNumber 取全部候选；ByRandom 缺省随机取 1。ConfigAI target_override 不介入。
        if task.get("ByRandom"):
            spec["mode"] = "random"
            if "MaxNumber" not in task:
                spec["take"] = 1
        predicate = task.get("Predicate")
        if predicate:
            predicate_type = str(predicate.get("$type") or "")
            if predicate_type == "RPG.GameCore.ByIsPropertyValueMinOrMax":
                compare_alias = self._alias({"TargetType": predicate.get("CompareTargetType")})
                if (predicate.get("PropertyRatioType") != "HPRatio" or compare_alias != alias
                        or predicate.get("MinOrMax") not in {"Min", "Max"}):
                    self._issue(ctx, path, predicate_type, "Retarget 属性极值/比较池未注册")
                    return
                spec["order_by"] = (("-" if predicate["MinOrMax"] == "Max" else "")
                                    + "$it.hp / $it.max_hp")
            else:
                where = self._predicate_expr(predicate, ctx, f"{path}/Predicate")
                if where is None:
                    self._issue(ctx, path, str(task.get("$type")), "Retarget 谓词未注册")
                    return
                if spec.get("where"):
                    spec["where"] = self._and_condition(spec["where"], where)
                else:
                    spec["where"] = where
        if not self._presentation_only(task.get("FailedTaskList") or []):
            self._issue(ctx, path, str(task.get("$type")), "Retarget 空候选机制分支未注册")
            return
        previous = ctx.retarget
        before = len(ctx.damages)
        ctx.retarget = spec
        self._compile_tasks(task.get("TaskList") or [], ctx, f"{path}/TaskList", stack)
        if len(ctx.damages) != before:
            self._issue(ctx, path, str(task.get("$type")), "Retarget 伤害目标尚未接入 Action")
            del ctx.damages[before:]
        ctx.retarget = previous

    def _compile_character_count(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        expression = self._count_expression(
            task.get("ReadTargetType"), ctx, path, task.get("Predicate"))
        if not key or expression is None:
            self._issue(ctx, path, str(task.get("$type")), "人数动态键或目标规格未注册")
            return
        ctx.count_expressions[dynamic_value_hash(key)] = expression
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        })

    def _compile_dynamic_add(self, task: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        raw_key = task.get("Key") or {}
        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
        # AddValue/Min/Max 允许已解析表达式（动态槽经 PostfixExpr 符号层）——钳制用
        # min/max 内联组合，不加引擎原语；读旧值走 dynamic_of 四层读链（帧覆盖层
        # 优先），语义 = 帧内累积（#26 期 2/3，14_policy.md）。
        add = self._value(task.get("AddValue"), ctx, f"{path}/AddValue")
        minimum = self._value(task.get("Min"), ctx, f"{path}/Min") if "Min" in task else None
        maximum = self._value(task.get("Max"), ctx, f"{path}/Max") if "Max" in task else None
        target = self._hook_target(self._alias(task), ctx)
        if (not key or add is None
                or ("Min" in task and minimum is None)
                or ("Max" in task and maximum is None)
                or target != "self"):
            self._issue(ctx, path, str(task.get("$type")), "动态加值键/增量/钳制/自指目标未注册")
            return
        expression = f"dynamic_of($self, '{key}') + ({add})"
        if minimum is not None:
            expression = f"max({expression}, ({minimum}))"
        if maximum is not None:
            expression = f"min({expression}, ({maximum}))"
        ctx.dynamic_writes.add(str(key))
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": str(key), "amount": expression,
        })

    def _compile_dynamic_copying(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        """SetDynamicValueByCopying：ToKey := dynamic_of($self, FromKey)——与解释器同口径
        （enemy_ai `_run_tasks`：FromTargetType 须自指别名，写入总是落施放者运行态）；
        `FromModifierName` 跨 modifier 读与 LevelEntity/CasterSummoner 等非自指源拒绝。
        读旧值走四层读链（帧覆盖层优先，写后读语义正确）。"""
        from hsr_nous.sim_schema.config_ai import is_self_target_alias
        raw_to = task.get("ToDynamicKey") or {}
        raw_from = task.get("FromDynamicKey") or {}
        to_key = raw_to.get("Value") if isinstance(raw_to, dict) else raw_to
        from_key = raw_from.get("Value") if isinstance(raw_from, dict) else raw_from
        from_alias = str((task.get("FromTargetType") or {}).get("Alias") or "")
        if not to_key or not from_key or not is_self_target_alias(from_alias) \
                or task.get("FromModifierName"):
            self._issue(ctx, path, str(task.get("$type")),
                        "动态拷贝的源/目标键、自指源或未注册的跨 modifier 读")
            return
        ctx.dynamic_writes.add(str(to_key))
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": str(to_key),
            "amount": f"dynamic_of($self, '{from_key}')",
        })

    def _compile_random_config(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        """RandomConfig 权重掷（无战斗级记忆字段时）→ bind_roll + 累计权重区间守卫.

        与上游 `rng.random()*Σ <= 累计` 同浮点序（bind 绑 u×Σ，守卫比累计值）；
        `RandomUnique`/`RandomMaskKey`/`RandomCount` 是战斗级记忆/不放回语义，
        保持显式 unsupported 进 human_queue，禁止猜测。"""
        memory_fields = [field for field in ("RandomUnique", "RandomMaskKey", "RandomMaskTarget",
                                             "AutoResetRandomMask", "RandomCount")
                         if field in task]
        if memory_fields:
            self._issue(ctx, path, str(task.get("$type")),
                        f"战斗级随机记忆字段尚未注册：{sorted(memory_fields)}")
            return
        if ctx.mode != "action":
            # 同 ByRandomChance：事件域概率分支可在帧外发射，显式拒收不猜。
            self._issue(ctx, path, str(task.get("$type")),
                        "事件域概率分支可在执行帧外发射，暂不注册")
            return
        task_list = task.get("TaskList") or []
        odds = task.get("OddsList") or []
        options = [option if isinstance(option, list) else [option]
                   for option in task_list]
        if all(self._presentation_only(option) for option in options):
            return   # 纯表现权重掷：无可观察效果，不消耗随机流
        if not options or len(options) != len(odds):
            self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重/任务表缺数或对齐")
            return
        weights: List[float] = []
        for index, raw in enumerate(odds):
            weight = self._number(raw, ctx, f"{path}/OddsList/{index}")
            if weight is None:
                self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重必须是静态数值")
                return
            weights.append(float(weight))
        if any(weight < 0 for weight in weights) or sum(weights) <= 0:
            self._issue(ctx, path, str(task.get("$type")), "RandomConfig 权重须非负且和为正")
            return
        key = self._stable_roll_key(f"{path}/RandomConfig")
        self._add_live_effect(ctx, {
            "effect_type": "bind_roll", "roll_key": key, "scale": sum(weights)}, "true")
        previous = ctx.live_condition
        acc_before = 0.0
        for index, weight in enumerate(weights):
            acc_after = acc_before + weight   # 运行和累计——与上游同浮点序，不做减法
            upper = f"roll('{key}') <= {acc_after}"
            guard = upper if index == 0 else \
                f"roll('{key}') > {acc_before} and {upper}"
            ctx.live_condition = self._and_condition(previous, guard)
            self._compile_tasks(options[index], ctx, f"{path}/Odds/{index}", stack)
            acc_before = acc_after
        ctx.live_condition = previous

    def _compile_define_dynamic(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        raw_key = task.get("DynamicKey") or task.get("Key") or {}
        key = raw_key.get("Value") if isinstance(raw_key, dict) else raw_key
        raw_value = task["ResetValue"] if "ResetValue" in task else task.get("Value")
        # 自指/被写键的哈希读取经 _value 的 dynamic_name_symbols 统一回落活读
        # （与 ConfigAI 解释器同口径：Define/Set 均为绝对写，ResetValue/Value 皆写）。
        value = self._value(raw_value, ctx, f"{path}/Value") if raw_value is not None else 0
        alias = self._alias(task)
        if not alias and task.get("$type") == "RPG.GameCore.SetDynamicValue":
            # 上游省略 TargetType 的 SetDynamicValue 由施放者持有；ConfigAI 也从自身读取该键。
            alias = "Caster"
        target = self._hook_target(alias, ctx)
        if not key or value is None or target != "self":
            self._issue(ctx, path, str(task.get("$type")), "动态键/值/自指目标未注册")
            return
        ctx.dynamic_writes.add(str(key))
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": str(key), "amount": value,
        })

    def _compile_property_value(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "AbilityTargetEntity": "$event.target", "ParamEntity": "$target",
               "CasterSummoner": "summoner_of($self.actor_id)"}.get(alias)
        if alias == "ParamEntity" and ctx.retarget is None:
            ref = None
        stat = {
            "MaxHP": ("max_hp_of", ""),
            "MaxStance": ("base_stat_of", "max_toughness"),
            "CurrentStance": ("toughness_of", ""),
            "CurrentHP": ("hp_of", ""),
            "Attack": ("stat_of", "atk"),
            "Speed": ("stat_of", "spd"),
            "BaseAttack": ("base_stat_of", "atk"),
            "BaseSpeed": ("base_stat_of", "spd"),
        }.get(task.get("Value"))
        if not key or ref is None or stat is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"属性动态键/读取目标/属性未注册：{key} / {alias} / {task.get('Value')}")
            return
        function, stat_name = stat
        expression = (f"{function}({ref})" if not stat_name
                      else f"{function}({ref}, '{stat_name}')")
        ctx.dynamic_writes.add(key)
        effect = {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        }
        if alias == "ParamEntity":
            effect["amount_target"] = dict(ctx.retarget)
        self._add_effect(ctx, effect)

    def _compile_modifier_value(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        raw_target = task.get("ReadTargetType")
        alias = self._alias({"TargetType": raw_target}) if raw_target is not None \
            else "ModifierOwnerEntity"
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "ParamEntity": "$target", "CasterSummoner": "summoner_of($self.actor_id)"}.get(alias)
        if alias == "ParamEntity" and ctx.retarget is None:
            ref = None
        name = str(task.get("ModifierName") or ctx.current_modifier or "")
        definition = self.modifiers.get(name) or {}
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        modifier_id = self._modifier_id(name, definition, skill_id) if name else ""
        multiplier = self._value(task.get("Multiplier", 1), ctx, f"{path}/Multiplier")
        value_type = task.get("ValueType")
        if value_type not in {"Layer", "LifeTime"} or not key or ref is None or not modifier_id:
            self._issue(ctx, path, str(task.get("$type")),
                        "仅支持已绑定 modifier 的 Layer/LifeTime 读取与已注册目标")
            return
        trigger = str(ctx.skill.get("trigger_key") or "")
        entry = str((self.config_skills.get(trigger) or {}).get("EntryAbility") or "")
        if ("STAT_DOT" in set(definition.get("BehaviorFlagList") or [])
                and not self._ability_adds_modifier(entry, name)):
            self._issue(ctx, path, str(task.get("$type")), "跨技能 DoT 数值读取未能绑定来源技能")
            return
        if multiplier is None:
            return
        reader = "stacks" if value_type == "Layer" else "modifier_duration"
        expression = _format(_binary(
            "*", _atom(f"{reader}({ref}, '{modifier_id}')"), _atom(multiplier)))
        ctx.dynamic_writes.add(key)
        effect = {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": expression,
        }
        if alias == "ParamEntity":
            effect["amount_target"] = dict(ctx.retarget)
        self._add_effect(ctx, effect)

    def _compile_hp_ratio_dynamic(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        key = str(task.get("DynamicKey") or "")
        alias = self._alias({"TargetType": task.get("ReadTargetType")})
        ref = {"Caster": "$self.actor_id", "ModifierOwnerEntity": "$self.actor_id",
               "AbilityTargetEntity": "$event.target"}.get(alias)
        if not key or ref is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"HP 比例动态键/读取目标未注册：{key} / {alias}")
            return
        ctx.dynamic_writes.add(key)
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": key, "amount": f"hp_of({ref}) / max_hp_of({ref})",
        })

    def _scan_dynamic_keys(self) -> Tuple[set[str], set[str]]:
        """收集 Ability/Modifier/ConfigAI 全部动态键及所有 Set/Define 写入键."""
        all_keys: set[str] = set()
        written_keys: set[str] = set()
        containers = [*self.abilities.values(), *self.modifiers.values(), self.sources.get("config_ai")]

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                node_type = str(value.get("$type") or "")
                for field in ("DynamicKey", "Key", "ToDynamicKey", "FromDynamicKey"):
                    raw = value.get(field)
                    candidate = raw.get("Value") if isinstance(raw, dict) else raw
                    if candidate is not None and str(candidate):
                        all_keys.add(str(candidate))
                        if field != "FromDynamicKey" and node_type.startswith((
                                "RPG.GameCore.SetDynamicValue", "RPG.GameCore.DefineDynamicValue")):
                            written_keys.add(str(candidate))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for container in containers:
            walk(container)
        return all_keys, written_keys

    def _custom_value_is_readonly(self, name: str) -> bool:
        return name not in self.written_dynamic_keys

    def _switch_value(self, raw: Any, ctx: _Context, path: str) -> Optional[Tuple[str, Any]]:
        """Switch 解析：("static", 值) = 生成期唯一选支（SkillParam 符号/只读 CustomValue/
        静态数值）；("live", 键名) = 被写动态键或生成期可见写入的可变 CustomValue——
        由 `_compile_switch` 翻活读（dynamic_of 条件守卫）；不可用记 unsupported 返 None。"""
        if not isinstance(raw, dict) or not raw.get("IsDynamic"):
            value = self._number(raw, ctx, path)
            return ("static", value) if value is not None else None
        expr = raw.get("PostfixExpr") or {}
        hashes = expr.get("DynamicHashes") or []
        if expr.get("OpCodes") != "AQAR" or expr.get("FixedValues") or len(hashes) != 1:
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "Switch 只支持 AQAR 单动态值")
            return None
        try:
            key_hash = int(hashes[0])
        except (TypeError, ValueError):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "Switch 哈希无效")
            return None
        matches = [(name, value) for name, value in self.custom_values.items()
                   if dynamic_value_hash(str(name)) == key_hash]
        hash_names = {name for name in self.dynamic_keys
                      if dynamic_value_hash(str(name)) == key_hash}
        if (len(matches) > 1 or len(hash_names) > 1
                or (matches and key_hash in self.dynamic_symbols)
                or (matches and any(name != matches[0][0] for name in hash_names))):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "动态键/CustomValue 哈希命名空间冲突")
            return None
        if key_hash in self.dynamic_symbols:
            value = self.dynamic_symbols[key_hash]
            if not _is_number(value):
                self._issue(ctx, path, "SwitchCaseByDynamicValue", "运行时 Switch 尚未注册")
                return None
            return ("static", value)
        if not matches and len(hash_names) == 1:
            return ("live", self._validated_switch_key(ctx, path, str(next(iter(hash_names)))))
        if not matches:
            self._issue(ctx, path, "SwitchCaseByDynamicValue", "CustomValue 哈希缺失或冲突")
            return None
        name, value = matches[0]
        if not self._custom_value_is_readonly(name):
            if name in self.dynamic_keys:
                return ("live", self._validated_switch_key(ctx, path, str(name)))
            self._issue(ctx, path, "SwitchCaseByDynamicValue",
                        f"可变 CustomValue 的运行时 Switch 尚未注册：{name}")
            return None
        value = value or 0
        if not _is_number(value):
            self._issue(ctx, path, "SwitchCaseByDynamicValue", f"CustomValue 非数值：{name}")
            return None
        return ("static", value)

    @staticmethod
    def _validated_switch_key(ctx: _Context, path: str, name: str) -> Optional[str]:
        if any(ch in name for ch in "'\"\\"):
            AbilityCompiler._issue(ctx, path, "SwitchCaseByDynamicValue",
                                   f"活读 Switch 键名非法：{name!r}")
            return None
        return name

    def _compile_switch(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        resolved = self._switch_value(task.get("Switch"), ctx, f"{path}/Switch")
        cases: List[Tuple[float, List[Dict[str, Any]]]] = []
        seen = set()
        for index, row in enumerate(task.get("CaseTaskList") or []):
            case_value = self._number(row.get("Case"), ctx, f"{path}/CaseTaskList/{index}/Case")
            if case_value is None:
                self._issue(ctx, path, "SwitchCaseByDynamicValue", "Case 必须是静态数值")
                return
            if case_value in seen:
                self._issue(ctx, path, "SwitchCaseByDynamicValue", f"Case 值重复：{case_value}")
                return
            seen.add(case_value)
            cases.append((case_value, row.get("TaskList") or []))
        if resolved is not None and resolved[0] == "static":
            selected = next((tasks for value, tasks in cases if value == resolved[1]),
                            task.get("DefaultTaskList") or [])
            self._compile_tasks(selected, ctx, f"{path}/Selected", stack)
            return
        if resolved is None or resolved[1] is None:
            return   # Switch 不可用已记 unsupported
        # 活读翻译：各 Case 编译为 effect 级条件守卫 dynamic_of($self, '键') == Case 值
        # 的分支组（#26 期 2/3，14_policy.md SwitchCase 节）；DefaultTaskList 守卫为
        # 全部 Case 值不等。
        key_name = resolved[1]
        default_tasks = task.get("DefaultTaskList") or []
        if not cases and not default_tasks:
            return
        previous = ctx.live_condition
        for case_value, tasks in cases:
            ctx.live_condition = self._and_condition(
                previous, f"dynamic_of($self, '{key_name}') == {case_value}")
            self._compile_tasks(tasks, ctx, f"{path}/Case/{case_value}", stack)
        if default_tasks:
            unmatched = " and ".join(
                f"dynamic_of($self, '{key_name}') != {case_value}"
                for case_value, _tasks in cases)
            ctx.live_condition = (self._and_condition(previous, unmatched)
                                  if unmatched else previous)
            self._compile_tasks(default_tasks, ctx, f"{path}/Default", stack)
        ctx.live_condition = previous

    def _compile_monster_phase(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        if task.get("SetMode") != "Inc":
            self._issue(ctx, path, str(task.get("$type")),
                        f"只支持 SetMode=Inc，得到 {task.get('SetMode')!r}")
            return
        ctx.dynamic_writes.add("current_phase")
        self._add_effect(ctx, {
            "effect_type": "set_dynamic_value", "target": "self",
            "dynamic_key": "current_phase",
            "amount": "dynamic_of($self, 'current_phase') + 1",
        })

    def _compile_summon_monster(self, task: Dict[str, Any], ctx: _Context,
                                path: str, stack: Tuple[str, ...]) -> None:
        rows = task.get("SummonMonsterDataList") or []
        if not rows:
            self._issue(ctx, path, str(task.get("$type")), "SummonMonsterDataList 为空")
            return
        for index, row in enumerate(rows):
            raw_id = row.get("MonsterID")
            if "MonsterIDFromCustomValue" in row:
                try:
                    key_hash = int((row.get("MonsterIDFromCustomValue") or {}).get("Hash"))
                except (TypeError, ValueError):
                    self._issue(ctx, f"{path}/{index}", "SummonMonster", "CustomValue 哈希缺失")
                    continue
                values = [value for name, value in self.custom_values.items()
                          if dynamic_value_hash(str(name)) == key_hash]
                if not values or any(value != values[0] for value in values[1:]):
                    self._issue(ctx, f"{path}/{index}", "SummonMonster",
                                "CustomValue 怪物 ID 哈希缺失或冲突")
                    continue
                raw_id = values[0]
            monster_id = self._number(raw_id, ctx, f"{path}/{index}/MonsterID")
            delay = self._number(row.get("DelayRatio", 0), ctx, f"{path}/{index}/DelayRatio")
            if monster_id is None or delay is None:
                continue
            if int(monster_id) != monster_id:
                self._issue(ctx, f"{path}/{index}", "SummonMonster", "怪物 ID 必须为整数")
                continue
            if delay != 0:
                self._issue(ctx, f"{path}/{index}", "SummonMonster",
                            "非零召唤 DelayRatio 尚未接入行动时序")
                continue
            summon_id = f"{int(monster_id)}__{self.enemy_id}_s{len(ctx.summons) + 1}"
            ctx.summons.append({
                "summon_id": summon_id, "enemy_template": str(int(monster_id)),
                "level": self.level,
            })
            self._add_effect(ctx, {"effect_type": "summon", "summon_id": summon_id})

    def _ability_adds_modifier(self, ability_name: str, modifier_name: str,
                               seen: Optional[set] = None) -> bool:
        seen = set() if seen is None else seen
        if ability_name in seen or ability_name not in self.abilities:
            return False
        seen.add(ability_name)

        def walk(value: Any) -> bool:
            if isinstance(value, dict):
                node_type = str(value.get("$type") or "")
                if node_type == "RPG.GameCore.AddModifier":
                    raw = value.get("ModifierName")
                    name = raw.get("Value") if isinstance(raw, dict) else raw
                    if str(name) == modifier_name:
                        return True
                if node_type in {"RPG.GameCore.TriggerAbility", "RPG.GameCore.TurnInsertAbility"}:
                    raw = value.get("AbilityName")
                    child = raw.get("Value") if isinstance(raw, dict) else raw
                    if child and self._ability_adds_modifier(str(child), modifier_name, seen):
                        return True
                return any(walk(child) for child in value.values())
            if isinstance(value, list):
                return any(walk(child) for child in value)
            return False

        return walk(self.abilities[ability_name])

    def _compile_dispel_status(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        if task.get("BuffType") != "Buff" or task.get("Order") != "LastAdded":
            self._issue(ctx, path, str(task.get("$type")), "仅支持按最后添加顺序驱散增益")
            return
        target = self._hook_target(self._alias(task), ctx)
        count = self._number(task.get("Numbers"), ctx, f"{path}/Numbers")
        if target is None or count is None or count < 1 or int(count) != count:
            self._issue(ctx, path, str(task.get("$type")), "驱散目标或正整数数量未注册")
            return
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": target,
            "filter": "$mod.kind == 'buff'", "max_count": int(count), "reason": "dispel",
        })
        count_key = str(task.get("DispelCountKey") or "")
        if count_key:
            if ctx.mode != "action":
                self._issue(ctx, path, str(task.get("$type")), "驱散计数仅支持行动效果链")
                return
            ctx.count_expressions[dynamic_value_hash(count_key)] = "$last.removed_count"
            ctx.dynamic_writes.add(count_key)
            self._add_effect(ctx, {
                "effect_type": "set_dynamic_value", "target": "self",
                "dynamic_key": count_key, "amount": "$last.removed_count",
            })

    def _compile_remove_modifier_by_behavior_flag(self, task: Dict[str, Any], ctx: _Context,
                                                  path: str, stack: Tuple[str, ...]) -> None:
        flags = set(task.get("ModifierBehaviorFlags") or [])
        filters = {
            "STAT_CTRL": "$mod.kind == 'control'",
            "STAT_DOT": "$mod.kind == 'dot'",
            "DisableAction": "$mod.prevent_action",
        }
        if len(flags) != 1 or not flags.issubset(filters):
            self._issue(ctx, path, str(task.get("$type")),
                        f"未注册行为旗标摘除：{sorted(flags)}")
            return
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册行为旗标摘除目标：{self._alias(task)}")
            return
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": target,
            "filter": filters[next(iter(flags))], "reason": "dispel",
        })

    def _compile_remove_self_modifier(self, task: Dict[str, Any], ctx: _Context,
                                      path: str, stack: Tuple[str, ...]) -> None:
        if not ctx.current_modifier:
            self._issue(ctx, path, str(task.get("$type")), "RemoveSelfModifier 缺少当前 modifier 名")
            return
        self._add_effect(ctx, {
            "effect_type": "remove_modifier", "target": "self",
            "modifier_id": ctx.current_modifier,
        })

    def _compile_remove_modifier(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if str(name) in {"OneMore", "OneMorePerTurn", "Monster_APShow"} \
                and self.modifiers.get(str(name)) is None:
            # grant_extra_turn 不产生 modifier 实例，内建 OneMore/APShow 清理无需 DSL 状态。
            return
        definition = self.modifiers.get(str(name)) or {}
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"摘除目标未注册：{self._alias(task)}")
            return
        trigger = str(ctx.skill.get("trigger_key") or "")
        entry = str((self.config_skills.get(trigger) or {}).get("EntryAbility") or "")
        if ("STAT_DOT" in set(definition.get("BehaviorFlagList") or [])
                and not self._ability_adds_modifier(entry, str(name))):
            self._issue(ctx, path, str(task.get("$type")), "跨技能 DoT 摘除未能绑定来源技能")
            return
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        effect = {
            "effect_type": "remove_modifier", "target": target,
            "modifier_id": self._modifier_id(str(name), definition, skill_id),
        }
        if task.get("OnlyRemoveCasterAdded"):
            if ctx.event in {"on_apply", "after_remove_modifier"}:
                effect["filter"] = "$mod.source == $event.source"
            elif ctx.event == "before_actor_exit":
                current_definition = self.modifiers.get(ctx.current_modifier) or {}
                current_id = self._modifier_id(ctx.current_modifier, current_definition, skill_id)
                effect["filter"] = f"$mod.source == modifier_source($event.actor, '{current_id}')"
            else:
                effect["filter"] = "$mod.source == $self.actor_id"
        self._add_effect(ctx, effect)

    @staticmethod
    def _alias(task: Dict[str, Any]) -> str:
        target = task.get("TargetType")
        if isinstance(target, dict):
            return str(target.get("Alias") or target.get("TargetType") or "")
        return str(target or "")

    def _hook_target(self, alias: str, ctx: Optional[_Context] = None) -> Any:
        if alias == "ParamEntity":
            return ctx.retarget if ctx is not None else None
        return {
            "Caster": "self",
            "ModifierOwnerEntity": "self",
            "AbilityTargetEntity": "$event.target",
            "AllTeammate": "all_enemies",
            "AllTeamMember": "all_enemies",
            "AllDarkTeam": "all_enemies",
            "AllDarkTeamWithAllDarkTeamUnselectable": "all_enemies",
            "AllEnemy": "all_allies",
            "AllLightTeam": "all_allies",
            "AllLightTeamIgnoreServant": {
                "pool": "allies", "where": "actor_type_of($it) != 'summon'"},
            "AllLightTeam.RemoveServant": {
                "pool": "allies", "where": "not $it.summoner_id"},
            "CasterSummonedMinions": {
                "pool": "enemies", "where": "$it.summoner_id == $self.actor_id"},
            "AbilityTargetAdjoinEntity": {
                "pool": "allies", "where": "is_adjacent($it, $event.target)"},
            "AbilityTargetAndAdjoinEntity": {
                "pool": "allies",
                "where": "($it.actor_id == $event.target or is_adjacent($it, $event.target))"},
            "CasterAdjoinEntity": {
                "pool": "enemies", "where": "is_adjacent($it, $self.actor_id)"},
        }.get(alias)

    def _compile_damage(self, task: Dict[str, Any], ctx: _Context,
                        path: str, stack: Tuple[str, ...]) -> None:
        attack = task.get("AttackProperty") or {}
        if attack.get("AttackType") == "DOT":
            self._issue(ctx, path, str(task.get("$type")), "DoT 伤害须由 modifier 定义编译")
            return
        alias = self._alias(task)
        ratio = self._number(attack.get("DamagePercentage"), ctx, f"{path}/DamagePercentage")
        if ratio is None:
            return
        ctx.seen_damage = True
        if ctx.condition != "true":
            ctx.conditional_damage = True
        record = {
            "alias": alias,
            "ratio": ratio,
            "element": _element(attack.get("DamageType")),
            "formula": attack.get("FormulaType") or "ByAttack",
            "stance_ratio": self._number(attack.get("SPHitRatio", 1), ctx,
                                         f"{path}/SPHitRatio"),
            "stance_value": self._number(attack["StanceValue"], ctx, f"{path}/StanceValue")
            if "StanceValue" in attack else None,
        }
        if ctx.retarget is not None:
            ctx.retarget_damage = True
            ctx.retarget_damage_records.append(record)
            effect = {
                "effect_type": "deal_damage", "target": ctx.retarget,
                "damage_type": record["element"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": (record["stance_value"] if record["stance_value"] is not None
                                  else float(ctx.skill.get("sp_hit_base") or 0)
                                  * (record["stance_ratio"] or 0)),
            }
            self._add_effect(ctx, effect)
            return
        if ctx.mode == "event":
            target = self._hook_target(alias, ctx)
            if target is None:
                self._issue(ctx, path, "TargetAlias", f"未注册事件目标别名：{alias}")
                return
            effect = {
                "effect_type": "deal_damage", "target": target,
                "damage_type": record["element"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": record["stance_value"] or 0,
            }
            self._add_effect(ctx, effect)
        else:
            ctx.damages.append(record)

    def _compile_builtin_modifier(self, name: str, task: Dict[str, Any], ctx: _Context,
                                  path: str) -> bool:
        if name not in {"MCommon_Confine", "MCommon_FatigueRatio", "MCommon_CTRL_Crazy",
                         "MCommon_CTRL_Frozen", "MCommon_CTRL_Taunt", "MCommon_FastAction",
                         "WMonster_TY_Elite01_00_Skill07_Mark"}:
            return False
        target = self._hook_target(self._alias(task), ctx)
        chance = self._number(task.get("Chance", 1), ctx, f"{path}/Chance")
        duration = self._number(task.get("LifeTime", 0), ctx, f"{path}/LifeTime")
        if target is None or chance is None or duration is None:
            self._issue(ctx, path, "BuiltinModifier", f"内建 modifier 目标/概率/时长未注册：{name}")
            return True
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        base = {
            "duration": int(duration), "max_stack": 1, "stack_mode": "refresh", "dispellable": True,
        }
        if name == "MCommon_CTRL_Taunt":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_TAUNT", "name": "Taunt",
                "modifier_type": "debuff", "debuff_kind": "control", "control_kind": "taunt",
                "forced_taunt": True, "remove_on_source_death": True,
                "remove_on_source_exit": True, **base,
            }
        elif name == "MCommon_CTRL_Frozen":
            modifier = {
                "modifier_id": name, "name": name, "modifier_type": "control",
                "debuff_kind": "control", "control_kind": "freeze",
                "prevent_action": True, **base,
            }
            ratio = self._value(
                (task.get("DynamicValues") or {}).get("Modifier_Frozen_DamagePercentage"),
                ctx, f"{path}/Modifier_Frozen_DamagePercentage")
            if ratio is None:
                self._issue(ctx, path, "Modifier_Frozen_DamagePercentage", "冻结追击倍率未注册")
                return True
            ctx.lifecycle_hooks.append({
                "event": "on_turn_start",
                "condition": f"has_modifier($event.actor, '{name}')",
                "effects": [{
                    "effect_type": "deal_damage", "target": "$event.actor",
                    "damage_type": "ice", "action_type": "follow_up", "scaling_atk": ratio,
                }],
            })
        elif name == "WMonster_TY_Elite01_00_Skill07_Mark":
            modifier = {"modifier_id": name, "name": name, "modifier_type": "debuff", **base}
        elif name == "MCommon_CTRL_Crazy":
            modifier = {
                "modifier_id": "ENEMY_OUTRAGE", "name": "Outrage", "modifier_type": "debuff",
                "debuff_kind": "control", "control_kind": "outrage", **base,
            }
        elif name == "MCommon_Confine":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_IMPRISON", "name": "Imprisonment",
                "modifier_type": "debuff", "debuff_kind": "control", "control_kind": "imprison",
                **base,
            }
            raw_ratio = (task.get("DynamicValues") or {}).get("MDF_ActionDelayRatio")
            ratio = self._value(raw_ratio, ctx, f"{path}/MDF_ActionDelayRatio")
            if ratio is None:
                return True
            modifier["on_apply"] = [{
                "effect_type": "delay_action", "target": "self",
                "amount": f"({ratio}) * 100" if isinstance(ratio, str) else ratio * 100,
            }]
        elif name == "MCommon_FastAction":
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_STORMRIDE", "name": "Stormride",
                "modifier_type": "buff",
                "on_apply": [{"effect_type": "immediate_action", "target": "self"}],
                **base,
            }
        else:
            raw_value = (task.get("DynamicValues") or {}).get("MDF_PropertyValue")
            value = self._value(raw_value, ctx, f"{path}/MDF_PropertyValue")
            if value is None:
                return True
            modifier = {
                "modifier_id": f"ENEMY_{skill_id}_WEAKEN", "name": "Weaken",
                "modifier_type": "debuff",
                **({"stat_exprs": {"all_dmg": f"-({value})"}} if isinstance(value, str)
                   else {"stat_effects": {"all_dmg": -value}}),
                **base,
            }
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "apply_chance": chance, "modifier": modifier,
        })
        return True

    def _compile_modifier_lifecycle(self, name: str, definition: Dict[str, Any],
                                    modifier: Dict[str, Any], ctx: _Context, path: str) -> None:
        """创建/摘除写入实例；死亡前编译为全局 hook，避免递归 modifier 定义."""
        slots = {"OnCreate": "on_apply", "OnDestroy": "on_remove"}
        events = {"OnCreate": "on_apply", "OnDestroy": "after_remove_modifier",
                  "OnBeforeDying": "before_actor_exit"}
        for index, callback in enumerate(definition.get("_CallbackList") or []):
            event = str(callback.get("Event") or "")
            if event not in {*slots, "OnBeforeDying"}:
                continue
            if event == "OnBeforeDying" and name in ctx.before_dying_stack:
                continue  # 同一死亡回调的循环施加由既有全局 hook 覆盖，不递归展开。
            if self._presentation_only(callback.get("CallbackConfig") or []):
                ctx.handled.append(event)
                continue
            sub = _Context(
                mode="event", skill=ctx.skill, event=events[event], current_modifier=name,
                before_dying_stack=(ctx.before_dying_stack + (name,)
                                    if event == "OnBeforeDying" else ctx.before_dying_stack),
            )
            callback_path = f"{path}/_CallbackList/{index}/{event}"
            self._compile_tasks(callback.get("CallbackConfig") or [], sub, callback_path, ())
            ctx.handled.extend([event, *sub.handled])
            ctx.lifecycle_hooks.extend(sub.lifecycle_hooks)
            for issue in sub.unsupported:
                self._issue(ctx, issue["path"], issue["node_type"], issue["reason"])
            if (sub.damages or sub.pre_effects or sub.hit_effects or sub.summons
                    or sub.retarget_damage or sub.retarget_damage_records):
                self._issue(ctx, callback_path, event, "生命周期伤害/召唤/分段效果尚未注册")
            if event == "OnBeforeDying":
                skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
                modifier_id = self._modifier_id(name, definition, skill_id)
                for effect in sub.effects:
                    if effect.get("effect_type") == "apply_modifier":
                        effect.setdefault("source", f"modifier:{modifier_id}")
                condition = (f"$event.reason == 'death' "
                             f"and has_modifier($event.actor, '{modifier_id}')")
                ctx.lifecycle_hooks.extend(self._make_hooks(
                    sub, condition, event="before_actor_exit"))
                continue
            effects = []
            for effect in sub.effects:
                condition = str(effect.get("_condition") or "true")
                clean = {key: value for key, value in effect.items() if key != "_condition"}
                if condition != "true":
                    clean["condition"] = condition
                if clean.get("effect_type") == "apply_modifier":
                    clean.setdefault("source", "$event.source")
                effects.append(clean)
            if effects:
                modifier.setdefault(slots[event], []).extend(effects)

    def _compile_add_modifier(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        alias = self._alias(task)
        retarget_where = str((ctx.retarget or {}).get("where") or "") \
            if isinstance(ctx.retarget, dict) else ""
        servant_target = alias == "CasterSummonedMinions" or (
            alias == "ParamEntity" and "$it.summoner_id ==" in retarget_where)
        if str(name) == "MCommon_Servant" and servant_target:
            # 内建 Servant 标记与 summon spec 的 summoner_id 同义；公共定义存在也不重复造件。
            return
        if str(name) == "Monster_APShow" and self.modifiers.get(str(name)) is None:
            return  # 内建行动条显示件，不进入战斗状态。
        if str(name) in {"OneMore", "OneMorePerTurn"} and self.modifiers.get(str(name)) is None:
            target = self._hook_target(self._alias(task), ctx)
            if target is None:
                self._issue(ctx, path, "TargetAlias", "OneMore 目标未注册")
                return
            self._add_effect(ctx, {"effect_type": "grant_extra_turn", "target": target})
            return
        if self._compile_builtin_modifier(str(name), task, ctx, path):
            return
        definition = self.modifiers.get(str(name))
        if definition is None:
            self._issue(ctx, path, str(task.get("$type")), f"modifier 定义缺失：{name}")
            return
        flags = set(definition.get("BehaviorFlagList") or [])
        if (self._visual_modifier(definition) and not self._modifier_used_in_predicates(str(name))
                and "RemoveWhenCasterDead" not in flags):
            return
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册 modifier 目标：{self._alias(task)}")
            return
        chance = self._number(task.get("Chance", 1), ctx, f"{path}/Chance")
        if chance == 0:
            return
        if "STAT_DOT" in flags:
            modifier = self._compile_dot(name, task, definition, ctx, path)
        else:
            modifier = self._compile_property_modifier(name, task, definition, ctx, path)
        if modifier is None or chance is None:
            return
        self._compile_modifier_lifecycle(str(name), definition, modifier, ctx, path)
        self._add_effect(ctx, {
            "effect_type": "apply_modifier", "target": target,
            "apply_chance": chance, "modifier": modifier,
        })

    @staticmethod
    def _modifier_id(name: str, definition: Dict[str, Any], skill_id: str) -> str:
        kind = next((str(flag).split("STAT_DOT_", 1)[1] for flag in
                     definition.get("BehaviorFlagList") or []
                     if str(flag).startswith("STAT_DOT_")), "")
        if "AttackSign" in set(definition.get("BehaviorFlagList") or []):
            return f"ENEMY_{skill_id}_LOCK_ON"
        return f"ENEMY_{skill_id}_{kind.upper()}" if kind else name

    def _modifier_defaults(self, name: str, task: Dict[str, Any], definition: Dict[str, Any],
                           ctx: _Context, path: str) -> Optional[Dict[str, Any]]:
        duration = self._number(task.get("LifeTime", definition.get("LifeTime", 0)),
                                ctx, f"{path}/LifeTime")
        maximum = self._number(task.get("MaxLayer", definition.get("MaxLayer", 1)),
                               ctx, f"{path}/MaxLayer")
        stacks = self._number(task.get("LayerAddWhenStack",
                                       definition.get("LayerAddWhenStack", 1)),
                              ctx, f"{path}/LayerAddWhenStack")
        if duration is None or maximum is None or stacks is None:
            return None
        stacking = definition.get("Stacking") or "Refresh"
        stack_mode = {"Replace": "replace", "ReplaceByCaster": "refresh",
                      "Refresh": "refresh"}.get(stacking)
        if stack_mode is None:
            self._issue(ctx, path, "ModifierStacking", f"未注册叠加语义：{stacking}")
            return None
        flags = set(definition.get("BehaviorFlagList") or [])
        return {
            "duration": int(duration), "max_stack": int(maximum), "stacks": int(stacks),
            "stack_mode": stack_mode, "dispellable": "CannotDispel" not in flags,
            **({"remove_on_source_death": True} if "RemoveWhenCasterDead" in flags else {}),
        }

    def _compile_dot(self, name: str, task: Dict[str, Any], definition: Dict[str, Any],
                     ctx: _Context, path: str) -> Optional[Dict[str, Any]]:
        defaults = self._modifier_defaults(name, task, definition, ctx, path)
        if defaults is None:
            return None
        symbols = dict(self.dynamic_symbols)
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is not None:
                symbols[dynamic_value_hash(str(key))] = value
        damage = None
        for callback in definition.get("_CallbackList") or []:
            if callback.get("Event") != "OnPhase1":
                continue
            for item in callback.get("CallbackConfig") or []:
                node_type = str(item.get("$type") or "")
                if node_type == "RPG.GameCore.SetDynamicValueByProperty":
                    dot_property = {"MaxHP": "$self.max_hp", "CurrentHP": "$self.hp"}.get(
                        item.get("Value"))
                    if dot_property is None:
                        self._issue(ctx, path, node_type, f"未注册 DoT 属性：{item.get('Value')}")
                        continue
                    symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = dot_property
                elif node_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                    if item.get("ValueType") != "Layer" or self._number(
                            item.get("Multiplier", 1), ctx, path) != 1:
                        self._issue(ctx, path, node_type, "只支持一比一读取 DoT 层数")
                        continue
                    symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = \
                        "max(1, $modifier.stacks)"
                elif node_type == "RPG.GameCore.DamageByAttackProperty":
                    damage = item
        if damage is None:
            self._issue(ctx, path, "ModifierDOT", "OnPhase1 缺 DoT DamageByAttackProperty")
            return None
        attack = damage.get("AttackProperty") or {}
        raw_ratio = attack["DamageValue"] if "DamageValue" in attack else attack.get("DamagePercentage")
        ratio = self._value(raw_ratio, ctx, f"{path}/DOT/DamageValue", symbols)
        if ratio is None:
            self._issue(ctx, path, "ModifierDOT", "DoT 伤害倍率缺失或无法解析")
            return None
        kind = next((str(flag).split("STAT_DOT_", 1)[1] for flag in
                     definition.get("BehaviorFlagList") or [] if str(flag).startswith("STAT_DOT_")),
                    "dot")
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        return {
            "modifier_id": self._modifier_id(name, definition, skill_id),
            "name": kind.capitalize(), "modifier_type": "dot",
            "dot_element": _element(attack.get("DamageType")),
            "dot_ratio_expr": ratio if isinstance(ratio, str) else str(ratio),
            "dot_base_chance": self._number(task.get("Chance", 1), ctx, f"{path}/Chance"),
            **defaults,
        }

    def _compile_property_modifier(self, name: str, task: Dict[str, Any],
                                   definition: Dict[str, Any], ctx: _Context,
                                   path: str) -> Optional[Dict[str, Any]]:
        callbacks = definition.get("_CallbackList") or []
        if "AttackSign" in set(definition.get("BehaviorFlagList") or []) and all(
                callback.get("Event") == "OnCreate" and not callback.get("CallbackConfig")
                for callback in callbacks):
            defaults = self._modifier_defaults(name, task, definition, ctx, path)
            if defaults is None:
                return None
            defaults["stack_mode"] = "replace"
            skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
            return {
                "modifier_id": self._modifier_id(name, definition, skill_id),
                "name": name, "modifier_type": "debuff", "lock_on": True, **defaults,
            }
        defaults = self._modifier_defaults(name, task, definition, ctx, path)
        if defaults is None:
            return None
        symbols = dict(self.dynamic_symbols)
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is not None:
                symbols[dynamic_value_hash(str(key))] = value
        stats: Dict[str, Any] = {}
        toughness_lock = False
        has_cleanup = False
        previous_modifier = ctx.current_modifier
        previous_condition = ctx.condition
        ctx.current_modifier = name

        def visit_stack(tasks: Iterable[Dict[str, Any]]) -> None:
            nonlocal toughness_lock
            for item in tasks:
                node_type = str(item.get("$type") or "")
                if node_type == "RPG.GameCore.PredicateTaskList":
                    branch = self._static_monster_predicate(item.get("Predicate") or {})
                    if branch is None:
                        self._issue(ctx, path, node_type, "OnStack 属性分支不能由怪物 ID 静态判定")
                        continue
                    visit_stack(item.get("SuccessTaskList" if branch else "FailedTaskList") or [])
                elif node_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                    if item.get("ValueType") == "Layer":
                        symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = \
                            "max(1, $modifier.stacks)"
                elif node_type == "RPG.GameCore.StackProperty":
                    stat = {
                        "AllDamageReduce": "dmg_dmg_reduction",
                        "AllDamageTypeAddedRatio": "all_dmg",
                        "AllDamageTypeTakenRatio": "vulnerability",
                        "AttackAddedRatio": "atk_pct",
                        "AttackDelta": "atk",
                        "CriticalDamageBase": "crit_dmg",
                        "DefenceAddedRatio": "def_pct",
                        "HPAddedRatio": "hp_pct",
                        "HPDelta": "hp",
                        "SPRatioBase": "energy_regen",
                        "SpeedAddedRatio": "spd_pct",
                        "SpeedDelta": "spd",
                    }.get(item.get("Property"))
                    if stat is None:
                        self._issue(ctx, path, node_type, f"未注册属性：{item.get('Property')}")
                        continue
                    value = self._value(item.get("PropertyValue"), ctx,
                                        f"{path}/StackProperty/{stat}", symbols)
                    if value is not None:
                        stats[stat] = value
                elif node_type == "RPG.GameCore.StackWeakness":
                    all_elements = {"Physical", "Fire", "Ice", "Thunder", "Wind", "Quantum", "Imaginary"}
                    if item.get("OPType") != "Protected" or set(item.get("WeakList") or []) != all_elements:
                        self._issue(ctx, path, node_type, "只支持全七属性 WeakList 的 Protected 韧性锁")
                        continue
                    toughness_lock = True

        for callback in callbacks:
            event = callback.get("Event")
            if event in {"OnPhase2", "OnStage"}:
                before = len(ctx.effects)
                ctx.current_modifier = name
                ctx.condition = self._and_condition(
                    previous_condition, f"has_modifier($self.actor_id, '{name}')")
                self._compile_tasks(callback.get("CallbackConfig") or [], ctx,
                                    f"{path}/{event}", ())
                has_cleanup = has_cleanup or len(ctx.effects) > before
                ctx.condition = previous_condition
                ctx.current_modifier = previous_modifier
                continue
            if event == "OnStack":
                visit_stack(callback.get("CallbackConfig") or [])
        ctx.current_modifier = previous_modifier
        # 生命周期声明保留部分结果；纯表现与否由 _visual_modifier 独立判定。
        has_lifecycle = any(
            callback.get("Event") in {"OnCreate", "OnDestroy", "OnBeforeDying"}
            for callback in callbacks)
        if (not stats and not has_cleanup and not has_lifecycle and not self._visual_modifier(definition)
                and "RemoveWhenCasterDead" not in set(definition.get("BehaviorFlagList") or [])):
            self._issue(ctx, path, "Modifier", f"未注册 modifier 语义：{name}")
            return None
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        stat_effects = {key: value for key, value in stats.items() if not isinstance(value, str)}
        stat_exprs = {key: value for key, value in stats.items() if isinstance(value, str)}
        modifier_type = "buff"
        for stat, value in stats.items():
            if (isinstance(value, str) or (stat == "vulnerability" and value > 0)
                    or (stat != "vulnerability" and value < 0)):
                modifier_type = "debuff"  # 未判号或任一减益项保持保守口径。
                break
        return {
            "modifier_id": self._modifier_id(name, definition, skill_id),
            "name": name, "modifier_type": modifier_type,
            **({"stat_effects": stat_effects} if stat_effects else {}),
            **({"stat_exprs": stat_exprs} if stat_exprs else {}),
            **({"toughness_lock": True} if toughness_lock else {}), **defaults,
        }

    def _compile_heal_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        formula = task.get("FormulaType")
        if formula not in {"HealByTargetMaxHP", "HealByHealerMaxHP"}:
            self._issue(ctx, path, str(task.get("$type")), f"未注册治疗公式：{formula}")
            return
        if "HealPercentage" not in task:
            self._issue(ctx, path, str(task.get("$type")), "治疗倍率缺失")
            return
        if task.get("AliveOnly") is False:
            self._issue(ctx, path, str(task.get("$type")), "复活/死亡目标治疗尚未注册")
            return
        if task.get("HealerTargetType") is not None:
            self._issue(ctx, path, str(task.get("$type")), "独立治疗来源目标尚未注册")
            return
        if task.get("IsHealRallyHP"):
            self._issue(ctx, path, str(task.get("$type")), "RallyHP 治疗池尚未注册")
            return
        ratio = self._value(task.get("HealPercentage"), ctx, f"{path}/HealPercentage")
        target = self._hook_target(self._alias(task), ctx)
        if ratio is None:
            return
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册治疗目标：{self._alias(task)}")
            return
        effect = {
            "effect_type": "heal", "target": target,
            "ratio": ratio if formula == "HealByHealerMaxHP" else 0, "amount": 0,
        }
        if formula == "HealByTargetMaxHP":
            effect["amount"] = _format(_binary("*", _atom(ratio), _atom("$target.max_hp")))
        self._add_effect(ctx, effect)

    def _compile_lose_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        if task.get("RatioType") != "MaxHP":
            self._issue(ctx, path, str(task.get("$type")), f"未注册 RatioType：{task.get('RatioType')}")
            return
        ratio = self._value(task.get("Ratio"), ctx, f"{path}/Ratio")
        target = self._hook_target(self._alias(task), ctx)
        if ratio is None or target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册自伤目标：{self._alias(task)}")
            return
        amount = _binary("*", _atom("$self.max_hp" if target == "self" else "$target.max_hp"),
                         _atom(ratio))
        self._add_effect(ctx, {"effect_type": "drain_hp", "target": target,
                            "amount": _format(amount), "drain_ratio": 0.0})

    def _compile_modify_action_delay(self, task: Dict[str, Any], ctx: _Context,
                                     path: str, stack: Tuple[str, ...]) -> None:
        special = next((key for key in ("AddValue", "InitModify", "ChangeDelayVersion")
                        if key in task), None)
        if "AddNormalizedValue" not in task or special is not None:
            self._issue(ctx, path, str(task.get("$type")),
                        f"仅支持 AddNormalizedValue 推拉条；特殊字段：{special}")
            return
        value = self._number(task.get("AddNormalizedValue"), ctx, f"{path}/AddNormalizedValue")
        alias = self._alias(task)
        target = self._hook_target(alias, ctx)
        semantic = self.semantics.get(str(ctx.skill.get("trigger_key")), {})
        description = str(semantic.get("desc") or "").lower()
        if alias == "AllTeammate" and ("except this unit" in description
                                       or "apart from this unit" in description):
            target = {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}
        if value is None:
            return
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册推拉条目标：{alias}")
            return
        if value == 0:
            return
        self._add_effect(ctx, {
            "effect_type": "delay_action" if value > 0 else "advance_action",
            "target": target, "amount": abs(value) * 100.0,
        })

    def _compile_modify_energy(self, task: Dict[str, Any], ctx: _Context,
                               path: str, stack: Tuple[str, ...]) -> None:
        fields = [key for key in ("AddValue", "FixedAddValue", "AddMaxSPRatio", "FixedAddMaxSPRatio")
                  if key in task]
        if len(fields) != 1 or task.get("IgnoreBlock"):
            self._issue(ctx, path, str(task.get("$type")),
                        "仅支持普通/固定能量增减，设值与 IgnoreBlock 尚未注册")
            return
        field = fields[0]
        value = self._number(task[field], ctx, f"{path}/{field}")
        if value is None:
            return
        alias = self._alias(task)
        if alias == "AllLightTeamOnlyAddSPOnceForServant":
            # 正向回能时忆灵/忆师共享能量池，目标别名要求只记一次；耗能不去重。
            target = {"pool": "allies", "where": "not $it.summoner_id"} if value > 0 else "all_allies"
        else:
            target = self._hook_target(alias, ctx)
        valid_target = ((isinstance(target, str) and target in {"all_allies", "$event.target"})
                        or (isinstance(target, dict) and target.get("pool") == "allies"))
        if not valid_target:
            self._issue(ctx, path, "TargetAlias", f"未注册玩家侧能量目标：{alias}")
            return
        if value == 0:
            return
        amount: Any = abs(value)
        if field.endswith("MaxSPRatio"):
            amount = _format(_binary("*", _atom("$target.max_energy"), _atom(abs(value))))
        effect = {
            "effect_type": "gain_energy" if value > 0 else "consume_energy",
            "target": target, "amount": amount,
        }
        if value > 0 and field.startswith("Fixed"):
            effect["err_exempt"] = True
        self._add_effect(ctx, effect)

    def _compile_modify_skill_point(self, task: Dict[str, Any], ctx: _Context,
                                    path: str, stack: Tuple[str, ...]) -> None:
        if task.get("ModifyFunction") != "Add":
            self._issue(ctx, path, str(task.get("$type")), "仅支持 Add 战技点增减")
            return
        value = self._number(task.get("ModifyValue"), ctx, f"{path}/ModifyValue")
        if value is None:
            return
        if int(value) != value:
            self._issue(ctx, path, str(task.get("$type")), "战技点增减必须为整数")
            return
        if value == 0:
            return
        # IsSilence 仅控制提示；Add 统一走队级 SP 增减通道。
        self._add_effect(ctx, {"effect_type": "gain_skill_point", "amount": int(value)})

    def _compile_action_delay(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task["NormalizedValue"] if "NormalizedValue" in task else task.get("Value")
        value = self._number(raw, ctx, f"{path}/Value")
        alias = self._alias(task)
        target = self._hook_target(alias, ctx)
        semantic = self.semantics.get(str(ctx.skill.get("trigger_key")), {})
        if alias == "AllTeammate" and "apart from this unit" in str(semantic.get("desc") or ""):
            target = {"pool": "enemies", "where": "$it.actor_id != $self.actor_id"}
        if value != 0 or target is None:
            self._issue(ctx, path, str(task.get("$type")), "只支持归零立即行动与已注册目标")
            return
        self._add_effect(ctx, {"effect_type": "immediate_action", "target": target})

    def _compile_set_die(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        if ctx.event in {"on_kill", "before_actor_exit"}:
            return  # 已处于对应死亡链，自灭是 no-op，不递归重入。
        self._add_effect(ctx, {"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0})

    def _compile_force_kill(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task), ctx)
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册击杀目标：{self._alias(task)}")
            return
        if ctx.event == "before_actor_exit" and target == "self":
            return
        self._add_effect(ctx, {"effect_type": "set_hp_to_percent", "target": target, "percent": 0.0})

    def _target_type(self, config_skill: Dict[str, Any]) -> Optional[str]:
        info = config_skill.get("TargetInfo") or {}
        target = info.get("TargetType")
        if target == "Caster":
            return "self"
        if target == "EnemySelect":
            return "blast" if info.get("SubTargetType") == "TargetAdjoinEntity" else "single"
        if target == "AllEnemy":
            return "aoe"
        if target == "AllTeamMember":
            return "ally_aoe"
        if target == "FriendSelect":
            return "ally_single"
        return None

    def _action(self, ctx: _Context, config_skill: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        skill = ctx.skill
        skill_id = str(skill["skill_id"])
        semantic = self.semantics.get(str(skill.get("trigger_key")), {})
        target_type = self._target_type(config_skill)
        if target_type is None:
            self._issue(ctx, "SkillList/TargetInfo", "TargetInfo",
                        f"未注册技能目标：{config_skill.get('TargetInfo')}")
            return None
        action: Dict[str, Any] = {
            "action_id": skill_id, "name": semantic.get("name") or skill_id,
            "action_type": "skill", "target_type": target_type,
            "energy_gain": 0, "energy_grant": float(semantic.get("energy") or 0.0),
        }
        if not ctx.damages and ctx.retarget_damage:
            first = ctx.retarget_damage_records[0]
            toughness = (first["stance_value"] if first["stance_value"] is not None
                         else float(skill.get("sp_hit_base") or 0) * (first["stance_ratio"] or 0))
            action = {
                "action_id": action["action_id"], "name": action["name"],
                "action_type": action["action_type"], "target_type": action["target_type"],
                "damage_type": first["element"],
                "toughness_dmg": int(toughness) if toughness.is_integer() else toughness,
                "energy_gain": action["energy_gain"], "energy_grant": action["energy_grant"],
            }
            return action
        if not ctx.damages:
            damage_effects = [*ctx.pre_effects, *ctx.effects,
                              *[effect for hook in ctx.lifecycle_hooks for effect in hook["effects"]]]
            has_effect_damage = any(
                effect.get("effect_type") in {"trigger_dot", "deal_damage"}
                for effect in damage_effects)
            if skill.get("damage_type") and not has_effect_damage:
                self._issue(ctx, "DamageByAttackProperty", "DamageMissing",
                            "MonsterSkillConfig 声明伤害属性，但 Ability 未编译出伤害")
                return None
            return action
        main = [d for d in ctx.damages if d["alias"] in {
            "AbilityTargetEntity", "AllEnemy", "AllLightTeam"}]
        if not main or any(d["formula"] != "ByAttack" for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "主动技能缺主目标 ATK 伤害")
            return action
        first = main[0]
        if any(d["element"] != first["element"] for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "多段元素不一致，需显式序列语义")
            return action

        def segment_toughness(record: Dict[str, Any]) -> float:
            if record["stance_value"] is not None:
                return float(record["stance_value"])
            return float(skill.get("sp_hit_base") or 0) * (record["stance_ratio"] or 0)

        toughness = segment_toughness(first)
        action = {
            "action_id": action["action_id"], "name": action["name"],
            "action_type": action["action_type"], "target_type": action["target_type"],
            "damage_type": first["element"], "scaling": [{"atk": first["ratio"]}],
            "toughness_dmg": int(toughness) if toughness.is_integer() else toughness,
            "energy_gain": action["energy_gain"], "energy_grant": action["energy_grant"],
        }
        if len(main) > 1:
            action["instances"] = len(main)
            if any(d["ratio"] != first["ratio"] or d["stance_ratio"] != first["stance_ratio"]
                   or d["stance_value"] != first["stance_value"] for d in main):
                action["instance_variants"] = []
                for record in main:
                    value = segment_toughness(record)
                    action["instance_variants"].append({
                        "scaling": [{"atk": record["ratio"]}],
                        "toughness_dmg": int(value) if value.is_integer() else value,
                    })
        blast = [d for d in ctx.damages if d["alias"] == "AbilityTargetAdjoinEntity"]
        if blast:
            if len(blast) > 1 or blast[0]["element"] != first["element"]:
                self._issue(ctx, "DamageByAttackProperty", "Damage", "副目标多段/元素语义未注册")
                return action
            if blast[0]["ratio"] != first["ratio"]:
                action["scaling_blast"] = [{"atk": blast[0]["ratio"]}]
        return action

    def compile_skill(self, trigger_key: str) -> Dict[str, Any]:
        """编译 SkillList 的主动技能；``ok`` 仅在全任务树受支持时为真."""
        skill = self.skills.get(trigger_key)
        config_skill = self.config_skills.get(trigger_key)
        ctx = _Context(mode="action", skill=skill or {"skill_id": trigger_key})
        if skill is None or config_skill is None:
            self._issue(ctx, trigger_key, "SkillList", "TBGD trigger 与 CharacterConfig 未对齐")
        else:
            entry = config_skill.get("EntryAbility")
            if not entry:
                self._issue(ctx, trigger_key, "SkillList", "缺 EntryAbility")
            else:
                self._compile_ability(str(entry), ctx, trigger_key, ())
        action = self._action(ctx, config_skill or {}) if skill is not None else None
        if not ctx.damages:
            ctx.effects = ctx.pre_effects + ctx.effects
            ctx.pre_effects = []
        hooks = self._make_hooks(
            ctx, f"$event.source == $self.actor_id and $event.action_id == '{skill['skill_id']}'",
            event="on_become_target", effects=ctx.pre_effects
        ) if ctx.pre_effects and ctx.damages and skill is not None else []
        hooks.extend(self._make_hooks(
            ctx, f"$event.actor == $self.actor_id and $event.action_id == '{skill['skill_id']}'"
        ) if ctx.effects and skill is not None else [])
        if ctx.hit_effects and skill is not None:
            hooks.extend(self._make_hooks(
                ctx, f"$event.source == $self.actor_id and $event.action_id == '{skill['skill_id']}'",
                event="after_being_hit", effects=ctx.hit_effects))
        hooks.extend(ctx.lifecycle_hooks)
        return {
            "ok": not ctx.unsupported and action is not None,
            "action": action, "hooks": hooks, "summons": ctx.summons,
            "unsupported": ctx.unsupported, "handled": sorted(set(ctx.handled)),
        }

    def _compile_deathrattle(self, callback: Dict[str, Any], ctx: _Context,
                             path: str, stack: Tuple[str, ...]) -> None:
        self._compile_tasks(callback.get("CallbackConfig") or [], ctx, path, stack)

    def compile_passive(self, ability_name: str, skill_id: str) -> Dict[str, Any]:
        """编译 Ability.Modifiers 中的自身亡语；其他事件显式留给后续事件族."""
        skill = next((s for s in self.skills.values() if str(s.get("skill_id")) == str(skill_id)),
                     {"skill_id": str(skill_id)})
        ctx = _Context(mode="event", skill=skill, event="on_kill")
        ability = self.abilities.get(ability_name)
        if ability is None:
            self._issue(ctx, ability_name, "AbilityReference", "被动 Ability 定义缺失")
        else:
            for modifier_name, modifier in (ability.get("Modifiers") or {}).items():
                for index, callback in enumerate(modifier.get("_CallbackList") or []):
                    event = str(callback.get("Event") or "")
                    method_name = EVENT_HANDLERS.get(event)
                    if method_name is None:
                        continue
                    if event == "OnListenCharacterDie" and "Deathrattle" not in set(
                            modifier.get("BehaviorFlagList") or []):
                        self._issue(ctx, f"{ability_name}/{modifier_name}/{index}", event,
                                    "非自身 Deathrattle 的监听目标未证明")
                        continue
                    ctx.handled.append(event)
                    getattr(self, method_name)(callback, ctx,
                                               f"{ability_name}/{modifier_name}/{index}", ())
        hooks = self._make_hooks(ctx, "$event.target == $self.actor_id") if ctx.effects else []
        hooks.extend(ctx.lifecycle_hooks)
        return {"ok": not ctx.unsupported and bool(hooks), "action": None, "hooks": hooks,
                "summons": ctx.summons, "unsupported": ctx.unsupported,
                "handled": sorted(set(ctx.handled))}

    def _ability_dynamic_hashes(self, name: str, seen: Optional[set] = None) -> set:
        """收集 Ability 及其嵌套引用的动态哈希，用于被动→SkillParam 结构绑定."""
        seen = set() if seen is None else seen
        if name in seen or name not in self.abilities:
            return set()
        seen.add(name)
        hashes: set = set()

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                expr = value.get("PostfixExpr") or {}
                hashes.update(int(h) for h in expr.get("DynamicHashes") or [])
                node_type = str(value.get("$type") or "")
                if node_type in {"RPG.GameCore.TriggerAbility", "RPG.GameCore.TurnInsertAbility"}:
                    raw = value.get("AbilityName")
                    child = raw.get("Value") if isinstance(raw, dict) else raw
                    if child:
                        hashes.update(self._ability_dynamic_hashes(str(child), seen))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(self.abilities[name])
        return hashes

    def _passive_trigger(self, ability_name: str) -> Optional[str]:
        for config_skill in self.config.get("SkillList") or []:
            if (config_skill.get("EntryAbility") == ability_name
                    and config_skill.get("Name") in self.skills
                    and str(config_skill.get("Name")).startswith(("Passive", "SkillP"))):
                return str(config_skill["Name"])
        floats = ((self.config.get("DynamicValues") or {}).get("Floats") or {})
        triggers = set()
        for raw_hash in self._ability_dynamic_hashes(ability_name):
            info = (floats.get(str(raw_hash)) or {}).get("ReadInfo") or {}
            trigger = str(info.get("TriggerKey") or "")
            if info.get("Type") == "SkillParam" and trigger.startswith(("Passive", "SkillP")):
                triggers.add(trigger)
        return triggers.pop() if len(triggers) == 1 else None

    @staticmethod
    def _has_supported_event(ability: Dict[str, Any]) -> bool:
        for modifier in (ability.get("Modifiers") or {}).values():
            if any(callback.get("Event") in EVENT_HANDLERS
                   for callback in modifier.get("_CallbackList") or []):
                return True
        return False

    def compile_enemy(self) -> Dict[str, Any]:
        """编译整只敌人的主动与已注册被动，并给出完整覆盖审计."""
        actions: List[Dict[str, Any]] = []
        hooks: List[Dict[str, Any]] = []
        summons: List[Dict[str, Any]] = []
        unsupported: List[Dict[str, str]] = []
        handled: set = set()
        deferred: List[str] = []
        results: Dict[str, Any] = {}
        if not self.config:
            return {
                "ok": False, "actions": [], "hooks": [], "summons": [],
                "unsupported": [{
                    "owner": self.enemy_id, "path": "JsonConfig",
                    "node_type": "CharacterConfig", "reason": "CharacterConfig 缺失",
                }],
                "deferred": [], "handled": [], "skill_results": {},
            }

        def absorb(owner: str, result: Dict[str, Any]) -> None:
            results[owner] = result
            if result.get("action"):
                actions.append(result["action"])
            hooks.extend(result.get("hooks") or [])
            summons.extend(result.get("summons") or [])
            handled.update(result.get("handled") or [])
            unsupported.extend({"owner": owner, **issue}
                               for issue in result.get("unsupported") or [])

        for trigger in self.skills:
            if trigger not in self.config_skills:
                unsupported.append({
                    "owner": trigger, "path": trigger, "node_type": "SkillList",
                    "reason": "TBGD trigger 在 CharacterConfig 中不存在",
                })
        for trigger, config_skill in self.config_skills.items():
            if trigger.startswith(("Passive", "SkillP")):
                continue
            if trigger not in self.skills:
                unsupported.append({
                    "owner": trigger, "path": trigger, "node_type": "MonsterSkillConfig",
                    "reason": "CharacterConfig 主动技能在 MonsterSkillConfig 中不存在",
                })
                continue
            absorb(trigger, self.compile_skill(trigger))

        passive_candidates = {
            str(skill.get("EntryAbility"))
            for skill in self.config.get("SkillList") or []
            if str(skill.get("Name") or "").startswith(("Passive", "SkillP"))
            and skill.get("EntryAbility")
        }
        passive_candidates.update(
            str(name) for name in self.config.get("AbilityList") or []
            if self._has_supported_event(self.abilities.get(str(name)) or {}))
        for ability_name in sorted(passive_candidates):
            if _is_camera_ability(ability_name):
                continue
            if ability_name.startswith("Monster_Common_"):
                deferred.append(ability_name)
                continue
            ability = self.abilities.get(ability_name)
            if ability is None:
                unsupported.append({"owner": ability_name, "path": ability_name,
                                    "node_type": "AbilityReference",
                                    "reason": "被动 Ability 定义缺失"})
                continue
            if not self._has_supported_event(ability):
                unsupported.append({"owner": ability_name, "path": ability_name,
                                    "node_type": "PassiveAbility",
                                    "reason": "被动 OnStart/OnAdd 或其他事件尚未注册"})
                continue
            trigger = self._passive_trigger(ability_name)
            if trigger is None or trigger not in self.skills:
                unsupported.append({"owner": ability_name, "path": ability_name,
                                    "node_type": "PassiveBinding",
                                    "reason": "无法由 EntryAbility/SkillParam 唯一绑定被动技能"})
                continue
            absorb(ability_name, self.compile_passive(
                ability_name, str(self.skills[trigger]["skill_id"])))
        return {
            "ok": not unsupported and bool(actions or hooks),
            "actions": actions, "hooks": hooks,
            "summons": list({spec["summon_id"]: spec for spec in summons}.values()),
            "unsupported": unsupported, "deferred": sorted(deferred),
            "handled": sorted(handled), "skill_results": results,
        }
