"""上游 CharacterConfig/Ability → 敌人 sim_schema 的通用编译器.

只按上游节点类型注册转换，不写怪物/技能 ID 分支。TBGD 提供数值与结构；
Fandom 仅由调用方传入名字和受击回能等文本补充。未注册节点、未知动态哈希、
条件分支或目标语义不明都会进入 ``unsupported``，候选不得因此定稿。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from hsr_nous.sim_schema.config_ai import dynamic_value_hash

#: 纯表现/动画节点。含机制 TaskList 的动画节点不在此列，由专门处理器递归。
IGNORED_TASK_TYPES = frozenset({
    "RPG.GameCore.DamagePerformFinish",
    "RPG.GameCore.GlobalMainIntensityEffect",
    "RPG.GameCore.LookAt",
    "RPG.GameCore.MoveToTargetList",
    "RPG.GameCore.RadialBlurEffect",
    "RPG.GameCore.RemoveEffect",
    "RPG.GameCore.SetEffectAnimSpeed",
    "RPG.GameCore.SetEntityVisible",
    "RPG.GameCore.ShowSkillTextDialog",
    "RPG.GameCore.SkillExecutionStart",
    "RPG.GameCore.SkillPerformFinish",
    "RPG.GameCore.TriggerEffect",
    "RPG.GameCore.TriggerAnimState",
    "RPG.GameCore.VCameraConfigChange",
    "RPG.GameCore.WaitAnimState",
    "RPG.GameCore.WaitSecond",
})

#: 注册表即节点覆盖矩阵；值为 AbilityCompiler 方法名。
TASK_HANDLERS = {
    "RPG.GameCore.AddModifier": "_compile_add_modifier",
    "RPG.GameCore.DamageByAttackProperty": "_compile_damage",
    "RPG.GameCore.ForceKill": "_compile_force_kill",
    "RPG.GameCore.LoseHPByRatio": "_compile_lose_hp",
    "RPG.GameCore.SetActionDelay": "_compile_action_delay",
    "RPG.GameCore.SetDieImmediately": "_compile_set_die",
    "RPG.GameCore.TriggerAbility": "_compile_trigger_ability",
    "RPG.GameCore.TriggerAnimStateWithMove": "_compile_animation_events",
    "RPG.GameCore.TurnInsertAbility": "_compile_trigger_ability",
}
EVENT_HANDLERS = {
    "OnDeathrattle": "_compile_deathrattle",
    "OnListenCharacterDie": "_compile_deathrattle",
}

_ELEMENT = {"Thunder": "thunder", "Lightning": "thunder"}


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
    """编译上游 PostfixExpr；支持固定值、动态槽及 + - * /，其余显式拒绝.

    返回数值或 DSL 表达式字符串。字节码中 0/1 分别为 FixedValues /
    DynamicHashes 下标读取，0x11 为结束；未知 opcode 不猜测。
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
    damages: List[Dict[str, Any]] = field(default_factory=list)
    effects: List[Dict[str, Any]] = field(default_factory=list)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    handled: List[str] = field(default_factory=list)


class AbilityCompiler:
    """按节点类型递归编译一个敌人的技能与被动."""

    def __init__(
        self,
        enemy_id: str,
        skills: List[Dict[str, Any]],
        sources: Dict[str, Any],
        *,
        semantics: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.enemy_id = str(enemy_id)
        self.skills = {str(s.get("trigger_key")): s for s in skills if s.get("trigger_key")}
        self.sources = sources
        self.config = sources.get("character_config") or {}
        self.abilities = sources.get("abilities") or {}
        self.modifiers = sources.get("modifiers") or {}
        self.semantics = semantics or {}
        self.config_skills = {
            str(s.get("Name")): s for s in self.config.get("SkillList") or [] if s.get("Name")
        }
        self.dynamic_symbols = self._character_symbols()

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

    def _value(self, raw: Any, ctx: _Context, path: str,
               symbols: Optional[Dict[int, Any]] = None) -> Any:
        try:
            return compile_dynamic_value(raw, symbols or self.dynamic_symbols)
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
        for index, task in enumerate(tasks or []):
            node_path = f"{path}/{index}"
            node_type = str(task.get("$type") or "")
            if node_type in IGNORED_TASK_TYPES:
                continue
            method_name = TASK_HANDLERS.get(node_type)
            if method_name is None:
                self._issue(ctx, node_path, node_type or "<missing $type>", "未注册任务节点")
                continue
            ctx.handled.append(node_type)
            getattr(self, method_name)(task, ctx, node_path, stack)

    def _compile_ability(self, name: str, ctx: _Context, path: str,
                         stack: Tuple[str, ...]) -> None:
        if name.endswith("_Camera"):
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

    def _compile_trigger_ability(self, task: Dict[str, Any], ctx: _Context,
                                 path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("AbilityName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        if not name:
            self._issue(ctx, path, str(task.get("$type")), "缺 AbilityName")
            return
        self._compile_ability(str(name), ctx, path, stack)

    def _compile_animation_events(self, task: Dict[str, Any], ctx: _Context,
                                  path: str, stack: Tuple[str, ...]) -> None:
        for index, event in enumerate(task.get("EventList") or []):
            self._compile_tasks(event.get("TaskList") or [], ctx,
                                f"{path}/EventList/{index}/TaskList", stack)

    @staticmethod
    def _alias(task: Dict[str, Any]) -> str:
        target = task.get("TargetType")
        if isinstance(target, dict):
            return str(target.get("Alias") or target.get("TargetType") or "")
        return str(target or "")

    def _hook_target(self, alias: str) -> Any:
        return {
            "Caster": "self",
            "ModifierOwnerEntity": "self",
            "AbilityTargetEntity": "$event.target",
            "AllTeammate": "all_enemies",
            "AllDarkTeam": "all_enemies",
            "AllEnemy": "all_allies",
            "AllLightTeam": "all_allies",
            "AbilityTargetAdjoinEntity": {
                "pool": "allies", "where": "is_adjacent($it, $event.target)"},
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
        if ctx.mode == "event":
            target = self._hook_target(alias)
            if target is None:
                self._issue(ctx, path, "TargetAlias", f"未注册事件目标别名：{alias}")
                return
            effect = {
                "effect_type": "deal_damage", "target": target,
                "damage_type": record["element"],
                "scaling_hp" if record["formula"] == "ByMaxHP" else "scaling_atk": ratio,
                "toughness_dmg": record["stance_value"] or 0,
            }
            ctx.effects.append(effect)
        else:
            ctx.damages.append(record)

    def _compile_add_modifier(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task.get("ModifierName")
        name = (raw or {}).get("Value") if isinstance(raw, dict) else raw
        definition = self.modifiers.get(str(name))
        if definition is None:
            self._issue(ctx, path, str(task.get("$type")), f"modifier 定义缺失：{name}")
            return
        flags = set(definition.get("BehaviorFlagList") or [])
        target = self._hook_target(self._alias(task))
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册 modifier 目标：{self._alias(task)}")
            return
        chance = self._number(task.get("Chance", 1), ctx, f"{path}/Chance")
        if "STAT_DOT" in flags:
            modifier = self._compile_dot(name, task, definition, ctx, path)
        else:
            modifier = self._compile_property_modifier(name, task, definition, ctx, path)
        if modifier is None or chance is None:
            return
        ctx.effects.append({
            "effect_type": "apply_modifier", "target": target,
            "apply_chance": chance, "modifier": modifier,
        })

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
        return {
            "duration": int(duration), "max_stack": int(maximum), "stacks": int(stacks),
            "stack_mode": stack_mode,
            "dispellable": "CannotDispel" not in set(definition.get("BehaviorFlagList") or []),
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
                    if item.get("Value") != "MaxHP":
                        self._issue(ctx, path, node_type, f"未注册 DoT 属性：{item.get('Value')}")
                        continue
                    symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = "$self.max_hp"
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
        ratio = self._value(attack.get("DamageValue"), ctx, f"{path}/DOT/DamageValue", symbols)
        if ratio is None:
            return None
        kind = next((str(flag).split("STAT_DOT_", 1)[1] for flag in
                     definition.get("BehaviorFlagList") or [] if str(flag).startswith("STAT_DOT_")),
                    "dot")
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        return {
            "modifier_id": f"ENEMY_{skill_id}_{kind.upper()}",
            "name": kind.capitalize(), "modifier_type": "dot",
            "dot_element": _element(attack.get("DamageType")),
            "dot_ratio_expr": ratio if isinstance(ratio, str) else str(ratio),
            "dot_base_chance": self._number(task.get("Chance", 1), ctx, f"{path}/Chance"),
            **defaults,
        }

    def _compile_property_modifier(self, name: str, task: Dict[str, Any],
                                   definition: Dict[str, Any], ctx: _Context,
                                   path: str) -> Optional[Dict[str, Any]]:
        defaults = self._modifier_defaults(name, task, definition, ctx, path)
        if defaults is None:
            return None
        symbols = dict(self.dynamic_symbols)
        for key, raw in (task.get("DynamicValues") or {}).items():
            value = self._value(raw, ctx, f"{path}/DynamicValues/{key}")
            if value is not None:
                symbols[dynamic_value_hash(str(key))] = value
        stats: Dict[str, str] = {}
        supported = False
        for callback in definition.get("_CallbackList") or []:
            if callback.get("Event") != "OnStack":
                continue
            for item in callback.get("CallbackConfig") or []:
                node_type = str(item.get("$type") or "")
                if node_type == "RPG.GameCore.SetDynamicValueByModifierValue":
                    if item.get("ValueType") == "Layer":
                        symbols[dynamic_value_hash(str(item.get("DynamicKey")))] = \
                            "max(1, $modifier.stacks)"
                elif node_type == "RPG.GameCore.StackProperty":
                    stat = {"AllDamageTypeTakenRatio": "vulnerability"}.get(item.get("Property"))
                    if stat is None:
                        self._issue(ctx, path, node_type, f"未注册属性：{item.get('Property')}")
                        continue
                    value = self._value(item.get("PropertyValue"), ctx,
                                        f"{path}/StackProperty/{stat}", symbols)
                    if value is not None:
                        stats[stat] = value if isinstance(value, str) else str(value)
                        supported = True
        if not supported:
            self._issue(ctx, path, "Modifier", f"未注册 modifier 语义：{name}")
            return None
        skill_id = str(ctx.skill.get("skill_id") or self.enemy_id)
        return {
            "modifier_id": f"ENEMY_{skill_id}_{name.upper()}",
            "name": name, "modifier_type": "debuff", "stat_exprs": stats, **defaults,
        }

    def _compile_lose_hp(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        if task.get("RatioType") != "MaxHP":
            self._issue(ctx, path, str(task.get("$type")), f"未注册 RatioType：{task.get('RatioType')}")
            return
        ratio = self._value(task.get("Ratio"), ctx, f"{path}/Ratio")
        target = self._hook_target(self._alias(task))
        if ratio is None or target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册自伤目标：{self._alias(task)}")
            return
        amount = _binary("*", _atom("$self.max_hp" if target == "self" else "$target.max_hp"),
                         _atom(ratio))
        ctx.effects.append({"effect_type": "drain_hp", "target": target,
                            "amount": _format(amount), "drain_ratio": 0.0})

    def _compile_action_delay(self, task: Dict[str, Any], ctx: _Context,
                              path: str, stack: Tuple[str, ...]) -> None:
        raw = task["NormalizedValue"] if "NormalizedValue" in task else task.get("Value")
        value = self._number(raw, ctx, f"{path}/Value")
        target = self._hook_target(self._alias(task))
        if value != 0 or target is None:
            self._issue(ctx, path, str(task.get("$type")), "只支持归零立即行动与已注册目标")
            return
        ctx.effects.append({"effect_type": "immediate_action", "target": target})

    def _compile_set_die(self, task: Dict[str, Any], ctx: _Context,
                         path: str, stack: Tuple[str, ...]) -> None:
        if ctx.event == "on_kill":
            return
        ctx.effects.append({"effect_type": "set_hp_to_percent", "target": "self", "percent": 0.0})

    def _compile_force_kill(self, task: Dict[str, Any], ctx: _Context,
                            path: str, stack: Tuple[str, ...]) -> None:
        target = self._hook_target(self._alias(task))
        if target is None:
            self._issue(ctx, path, "TargetAlias", f"未注册击杀目标：{self._alias(task)}")
            return
        ctx.effects.append({"effect_type": "set_hp_to_percent", "target": target, "percent": 0.0})

    def _target_type(self, config_skill: Dict[str, Any]) -> Optional[str]:
        info = config_skill.get("TargetInfo") or {}
        target = info.get("TargetType")
        if target == "Caster":
            return "self"
        if target == "EnemySelect":
            return "blast" if info.get("SubTargetType") == "TargetAdjoinEntity" else "single"
        if target == "AllEnemy":
            return "aoe"
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
        if not ctx.damages:
            if skill.get("damage_type") or skill.get("param_list"):
                self._issue(ctx, "DamageByAttackProperty", "DamageMissing",
                            "MonsterSkillConfig 声明伤害/倍率，但 Ability 未编译出伤害")
                return None
            return action
        main = [d for d in ctx.damages if d["alias"] in {
            "AbilityTargetEntity", "AllEnemy", "AllLightTeam"}]
        if not main or any(d["formula"] != "ByAttack" for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "主动技能缺主目标 ATK 伤害")
            return action
        first = main[0]
        if any(d["ratio"] != first["ratio"] or d["element"] != first["element"] for d in main):
            self._issue(ctx, "DamageByAttackProperty", "Damage", "多段倍率/元素不一致，需显式序列语义")
            return action
        toughness = float(skill.get("sp_hit_base") or 0) * (first["stance_ratio"] or 0)
        action = {
            "action_id": action["action_id"], "name": action["name"],
            "action_type": action["action_type"], "target_type": action["target_type"],
            "damage_type": first["element"], "scaling": [{"atk": first["ratio"]}],
            "toughness_dmg": int(toughness) if toughness.is_integer() else toughness,
            "energy_gain": action["energy_gain"], "energy_grant": action["energy_grant"],
        }
        if len(main) > 1:
            action["instances"] = len(main)
        blast = [d for d in ctx.damages if d["alias"] == "AbilityTargetAdjoinEntity"]
        if blast:
            if len(blast) > 1 or blast[0]["element"] != first["element"]:
                self._issue(ctx, "DamageByAttackProperty", "Damage", "副目标多段/元素语义未注册")
                return action
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
        hooks = []
        if ctx.effects and skill is not None:
            hooks.append({
                "event": "on_action",
                "condition": (f"$event.actor == $self.actor_id and "
                              f"$event.action_id == '{skill['skill_id']}'"),
                "effects": ctx.effects,
            })
        return {
            "ok": not ctx.unsupported and action is not None,
            "action": action, "hooks": hooks, "unsupported": ctx.unsupported,
            "handled": sorted(set(ctx.handled)),
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
        hooks = []
        if ctx.effects:
            hooks.append({"event": "on_kill", "condition": "$event.target == $self.actor_id",
                          "effects": ctx.effects})
        return {"ok": not ctx.unsupported and bool(hooks), "action": None, "hooks": hooks,
                "unsupported": ctx.unsupported, "handled": sorted(set(ctx.handled))}

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
        unsupported: List[Dict[str, str]] = []
        handled: set = set()
        deferred: List[str] = []
        results: Dict[str, Any] = {}
        if not self.config:
            return {
                "ok": False, "actions": [], "hooks": [],
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
            if ability_name.endswith("_Camera"):
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
            "unsupported": unsupported, "deferred": sorted(deferred),
            "handled": sorted(handled), "skill_results": results,
        }
