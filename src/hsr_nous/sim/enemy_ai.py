"""ConfigAI 行为树解释器：只执行已登记节点，未知节点不得静默进入正式路径.

策略的 `config` 是上游原始 JSON（不是另一套手写 AI）。动态值、阶段与冷却状态都放进
既有 `_enemy_policy_state`，因此存档/恢复与 SequenceThree 共用同一条世界线。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.config_ai import MONSTER_RANK_VALUES, is_self_target_alias, is_team_count_alias, unsupported_config_nodes  # noqa: F401  # 静态收编共用入口


def _fixed_number(value: Any) -> float:
    if isinstance(value, dict) and "FixedValue" in value:
        return float(value["FixedValue"].get("Value", 0))
    if isinstance(value, dict) and "Value" in value:
        return float(value["Value"])
    return float(value or 0)


def _dynamic_key(value: Any) -> str:
    if isinstance(value, dict) and "Value" in value:
        return str(value["Value"])
    return str(value)


def _compare(actual: float, expected: float, compare_type: str) -> bool:
    return {
        "Equal": actual == expected,
        "NotEqual": actual != expected,
        "Less": actual < expected,
        "LessEqual": actual <= expected,
        "Greater": actual > expected,
        "GreaterEqual": actual >= expected,
    }.get(compare_type, False)


class ConfigAIInterpreter:
    """一台敌方单位的 ConfigAI 执行器；每次敌方回合重新评分并执行任务."""

    def __init__(self, engine: Any, actor_state: Any) -> None:
        self.engine = engine
        self.actor_state = actor_state
        self.actor_id = actor_state.actor.actor_id
        self.policy = engine._enemy_policies[self.actor_id]
        self.runtime = engine._enemy_policy_state[self.actor_id]
        self.runtime.setdefault("dynamic_values", {})
        self.runtime.setdefault("current_phase", 1)
        self.actions = {
            action.action_id: action
            for action in engine.actions_by_actor.get(self.actor_id, [])
        }
        self.target_override: Optional[Any] = None

    def _dynamic(self, key: str) -> float:
        values = self.runtime["dynamic_values"]
        if key in values:
            return float(values[key])
        # AIFlag/首计数器允许怪物名前缀，均以 1 起步；其他动态键默认 0。
        return 1.0 if key.endswith("AIFlag") or key.endswith(("AICounter", "AICounter_01")) else 0.0

    def _set_dynamic(self, key: str, value: float, *, add: bool = False) -> None:
        current = self._dynamic(key) if add else 0.0
        self.runtime["dynamic_values"][key] = current + float(value)

    def _cooldown_ready(self, action_id: str) -> bool:
        phases = self.policy.skill_phases.get(action_id, ())
        return (action_id in self.actions
                and self.runtime["cooldown_left"].get(action_id, 0) <= 0
                and (not phases or self.runtime["current_phase"] in phases)
                and self.engine._available_if_ok(self.actor_state, self.actions[action_id]))

    def _mark_executed(self, action_id: str) -> None:
        self.runtime["cooldown_left"][action_id] = self.policy.cooldown.get(action_id, 0)

    def _team_members(self, spec: Any) -> Optional[list]:
        if isinstance(spec, dict) and spec.get("$type") == "RPG.GameCore.TargetSequence":
            members = None
            for item in spec.get("Sequence") or []:
                item_type = item.get("$type")
                if item_type == "RPG.GameCore.TargetAlias":
                    group = self._team_members(str(item.get("Alias", "")))
                    members = group if members is None else [
                        st for st in members if st in group]
                elif item_type == "RPG.GameCore.TargetFilter":
                    members = [st for st in members or []
                               if self._predicate(item.get("Predicate") or {}, st)]
                elif item_type == "RPG.GameCore.TargetIndex":
                    if item.get("IndexType") != "IndexStrict":
                        return None
                    index = int(_fixed_number(item.get("IndexValue")))
                    members = [members[index]] if members and 0 <= index < len(members) else []
                elif item_type == "RPG.GameCore.TargetSortByFormation":
                    if item.get("HighestFirst"):
                        members = list(reversed(members or []))
                else:
                    return None
            if members is not None and spec.get("AliveOnly"):
                members = [st for st in members if st.alive]
            return members
        if not is_team_count_alias(spec):
            return None
        if spec in {"AllDarkTeam", "AllTeammate", "AllTeamMember"}:
            return self.engine._enemies_alive()
        if spec in {"AllEnemy", "AllLightTeam"}:
            return self.engine._allies_alive()
        if spec == "CasterSummonedMinions":
            return [st for st in self.engine._enemies_alive()
                    if st.actor.summoner_id == self.actor_id]
        if spec == "AllLightTeam.RemoveServant":
            return [st for st in self.engine._allies_alive() if not st.actor.summoner_id]
        return self.engine._enemies_alive()

    def _team_count(self, spec: Any, predicate: Optional[Dict[str, Any]] = None) -> Optional[float]:
        members = self._team_members(spec)
        if members is None:
            return None
        if predicate is not None:
            return float(sum(1 for st in members if self._predicate(predicate, st)))
        return float(len(members))

    def _behavior_flag(self, owner: Any, flag: Any) -> bool:
        flag = str(flag)
        if flag == "Break":
            return bool(owner.broken)
        if flag == "STAT_DOT":
            return any(mod.modifier_type == "dot" for mod in owner.modifiers.values())
        if flag == "STAT_CTRL":
            return any(mod.debuff_kind == "control" or mod.control_kind
                       for mod in owner.modifiers.values())
        if flag == "DisableAction":
            return any(mod.prevent_action for mod in owner.modifiers.values())
        return False

    def _predicate(self, node: Dict[str, Any], target_state: Optional[Any] = None) -> bool:
        """谓词统一处理 Inverse；嵌套过滤可改绑到候选目标而非施放者."""
        result = self._predicate_raw(node, target_state)
        return not result if node.get("Inverse", False) else result

    def _predicate_raw(self, node: Dict[str, Any], target_state: Optional[Any] = None) -> bool:
        node_type = node.get("$type")
        owner = target_state or self.actor_state
        if node_type == "RPG.GameCore.ByCompareDynamicValue":
            return _compare(
                self._dynamic(_dynamic_key(node.get("DynamicKey"))),
                _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByCompareMonsterPhase":
            return _compare(
                float(self.runtime["current_phase"]), _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByIsContainModifier":
            name = _dynamic_key(node.get("ModifierName"))
            return any(mod.modifier_id == name or mod.name == name
                       for mod in owner.modifiers.values())
        if node_type == "RPG.GameCore.ByContainBehaviorFlag":
            return self._behavior_flag(owner, node.get("Flag"))
        if node_type == "RPG.GameCore.ByAnd":
            return all(self._predicate(child, target_state) for child in node.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByAny":
            return any(self._predicate(child, target_state) for child in node.get("PredicateList") or [])
        if node_type == "RPG.GameCore.ByNot":
            return not self._predicate(node.get("Predicate") or {}, target_state)
        if node_type == "RPG.GameCore.ByTargetAliveState":
            return owner.alive == (str(node.get("CompareType", "Alive")) == "Alive")
        if node_type == "RPG.GameCore.ByCompareHPRatio":
            max_hp = max(1e-9, self.engine.pipeline.effective_stats(owner)["hp"])
            return _compare(
                owner.current_hp / max_hp, _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")),
            )
        if node_type == "RPG.GameCore.ByRandomChance":
            return self.engine.pipeline.mechanic_chance(_fixed_number(node.get("CompareValue")))
        if node_type == "RPG.GameCore.ByCompareMonsterID":
            actual_id = owner.actor.actor_id if target_state is not None else self.actor_id
            actual = actual_id.split("__", 1)[0]
            return actual == str(int(_fixed_number(node.get("TargetMonsterID"))))
        if node_type == "RPG.GameCore.ByCompareTarget":
            actual_alias = str((node.get("TargetType") or {}).get("Alias", ""))
            compare_alias = str((node.get("CompareType") or {}).get("Alias", ""))
            if actual_alias not in {"ParamEntity", "Caster"} or compare_alias not in {"ParamEntity", "Caster"}:
                return False
            actual = self.actor_state if actual_alias == "Caster" else owner
            expected = self.actor_state if compare_alias == "Caster" else owner
            return actual is expected
        if node_type == "RPG.GameCore.ByCompareBP":
            return _compare(
                float(self.engine.state.skill_points), _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")))
        if node_type == "RPG.GameCore.ByCompareAliveEnemyNumber":
            return _compare(
                float(len(self.engine._allies_alive())),
                _fixed_number(node.get("CompareValue")),
                str(node.get("CompareType", "Equal")))
        if node_type == "RPG.GameCore.ByCompareMonsterRank":
            actual_rank = float(MONSTER_RANK_VALUES.get(self.policy.monster_rank, 0))
            return _compare(actual_rank, _fixed_number(node.get("CompareValue")),
                            str(node.get("CompareType", "Equal")))
        if node_type in {"RPG.GameCore.ByCompareCharacterNumber", "RPG.GameCore.ByCompareTargetCount"}:
            target_type = node.get("TargetType") or {}
            spec = target_type.get("Alias") if target_type.get("$type") == "RPG.GameCore.TargetAlias" else target_type
            actual = self._team_count(spec, node.get("Predicate"))
            if actual is None:
                return False
            expected_key = "CompareNumber" if node_type.endswith("CharacterNumber") else "Number"
            return _compare(actual, _fixed_number(node.get(expected_key)),
                            str(node.get("CompareType", "Equal")))
        if node_type == "RPG.GameCore.ByCompareModifierValue":
            name = _dynamic_key(node.get("ModifierName"))
            modifier = next((mod for mod in owner.modifiers.values()
                             if mod.modifier_id == name or mod.name == name), None)
            value_type = str(node.get("ValueType", ""))
            if value_type == "LifeTime":
                actual = float(modifier.duration) if modifier is not None else 0.0
            elif value_type in {"Stack", "Stacks"}:
                actual = float(modifier.stacks) if modifier is not None else 0.0
            else:
                return False
            return _compare(actual, _fixed_number(node.get("CompareValue")),
                            str(node.get("CompareType", "Equal")))
        return False

    def _decision_score(self, decision: Dict[str, Any]) -> float:
        if not decision.get("ConsiderAxisList"):
            return _fixed_number(decision.get("Weight", 1.0))
        score = 0.0
        for axis in decision.get("ConsiderAxisList") or []:
            axis_type = axis.get("$type")
            if axis_type == "RPG.GameCore.ChoseSequencedSkillAxis":
                axis_score = _fixed_number(axis.get("CheckScore"))
            elif axis_type == "RPG.GameCore.CheckSkillUsabilityAxis":
                skill_name = str(axis.get("SkillName", ""))
                action_id = self.policy.skill_ids.get(skill_name, skill_name)
                axis_score = (_fixed_number(axis.get("CheckScore"))
                              if self._cooldown_ready(action_id) else 0.0)
            elif axis_type == "RPG.GameCore.CheckPredicateAxis":
                axis_score = (_fixed_number(axis.get("SuccessScore"))
                              if self._predicate(axis.get("Predicate") or {}) else 0.0)
            else:
                return 0.0
            score += axis_score
            if score == 0:
                return 0.0
        return score * _fixed_number(decision.get("Weight", 1.0))

    def _choose(self, decisions: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for decision in decisions or []:
            node_type = decision.get("$type")
            if node_type == "RPG.GameCore.AIStepperDecisionGroupConfig":
                group_score = self._decision_score(decision)
                if group_score <= 0:
                    continue
                chosen = self._choose(decision.get("DecisionList") or [])
                if chosen is not None:
                    score = group_score * self._decision_score(chosen)
                    if score > best_score:
                        best, best_score = chosen, score
            elif node_type == "RPG.GameCore.AIDecisionConfig":
                score = self._decision_score(decision)
                if score > best_score:
                    best, best_score = decision, score
        return best

    def _modifier_candidates(self, modifier_name: str, *, inverse: bool = False) -> list:
        pool = self.engine._allies_alive() + self.engine._enemies_alive()
        matched = []
        for target in pool:
            if any(mod.modifier_id == modifier_name or mod.name == modifier_name
                   for mod in target.modifiers.values()):
                matched.append(target)
        dot_element = {
            "MCommon_DOT_Electric": "thunder",
            "MCommon_DOT_Burn": "fire",
        }.get(modifier_name)
        if dot_element is not None:
            for target in pool:
                if target not in matched and any(
                        mod.modifier_type == "dot" and mod.dot_element == dot_element
                        for mod in target.modifiers.values()):
                    matched.append(target)
        if inverse:
            return [target for target in pool if target not in matched]
        return matched

    def _select_target_candidates(self, selector: Dict[str, Any]) -> list:
        selector_type = selector.get("$type")
        if selector_type == "RPG.GameCore.AIModifierNameSelector":
            return self._modifier_candidates(
                _dynamic_key(selector.get("ModifierName")),
                inverse=bool(selector.get("InverseResultFlag")))
        if selector_type == "RPG.GameCore.AIMonsterIDSelector":
            monster_ids = {int(value) for value in selector.get("MonsterIDList") or []}
            pool = self.engine._allies_alive() + self.engine._enemies_alive()
            matched = []
            for target in pool:
                try:
                    actor_id = int(target.actor.actor_id.split("__", 1)[0])
                except (TypeError, ValueError):
                    continue
                if actor_id in monster_ids:
                    matched.append(target)
            if selector.get("InverseResultFlag"):
                return [target for target in pool if target not in matched]
            return matched
        if selector_type == "RPG.GameCore.AIMonsterRankSelector":
            if selector.get("PropertyStrategy") != "Max":
                return []
            pool = self.engine._enemies_alive()

            def rank_of(target: Any) -> float:
                policy = self.engine._enemy_policies.get(target.actor.actor_id)
                return float(MONSTER_RANK_VALUES.get(policy.monster_rank if policy else "", 0))

            highest = max((rank_of(target) for target in pool), default=0.0)
            return [target for target in pool if rank_of(target) == highest]
        if selector_type == "RPG.GameCore.AIBehaviorFlagSelector":
            pool = self.engine._allies_alive() + self.engine._enemies_alive()
            matched = [st for st in pool if self._behavior_flag(st, selector.get("BehaviorFlag"))]
            if selector.get("InverseResultFlag"):
                return [st for st in pool if st not in matched]
            return matched
        if selector_type == "RPG.GameCore.AIPropertySelector":
            pool = self.engine._allies_alive()
            prop = str(selector.get("Property"))
            strategy = str(selector.get("PropertyStrategy"))
            if prop not in {"CurrentHP", "MaxHP"} or strategy not in {"MaxRatio", "MinRatio", "Max", "Min"}:
                return []
            if strategy in {"MaxRatio", "MinRatio"}:
                key = lambda st: st.current_hp / max(
                    1e-9, self.engine.pipeline.effective_stats(st)["hp"])
            elif prop == "CurrentHP":
                key = lambda st: st.current_hp
            else:
                key = lambda st: self.engine.pipeline.effective_stats(st)["hp"]
            result = sorted(pool, key=key, reverse=strategy in {"MaxRatio", "Max"})
            if selector.get("InverseResultFlag"):
                result.reverse()
            return result
        if selector_type == "RPG.GameCore.TargetFilter":
            pool = self.engine._allies_alive() + self.engine._enemies_alive()
            matched = [st for st in pool if self._predicate(selector.get("Predicate") or {}, st)]
            if selector.get("InverseResultFlag"):
                return [st for st in pool if st not in matched]
            return matched
        if selector_type == "RPG.GameCore.TargetSequence":
            return self._team_members(selector) or []
        if selector_type == "RPG.GameCore.AITaskTargetTypeSelector":
            alias = str((selector.get("TargetType") or {}).get("Alias", ""))
            if alias == "Caster":
                pool = self.engine._enemies_alive()
                candidates = [self.actor_state]
            elif alias in {"AllTeammate", "AllTeamMember"}:
                pool = self.engine._enemies_alive()
                candidates = list(pool)
            elif alias == "AllEnemy":
                pool = self.engine._allies_alive()
                candidates = list(pool)
            elif alias == "AllEnemyIgnoreServant":
                pool = self.engine._allies_alive()
                candidates = [st for st in pool if not st.actor.summoner_id]
            elif alias == "CasterSummonedMinions":
                pool = self.engine._enemies_alive()
                candidates = [st for st in pool if st.actor.summoner_id == self.actor_id]
            else:
                return []
            if selector.get("InverseResultFlag"):
                return [target for target in pool if target not in candidates]
            return candidates
        if selector_type == "RPG.GameCore.TargetSortByFormation":
            pool = self.engine._allies_alive() + self.engine._enemies_alive()
            return list(reversed(pool)) if selector.get("HighestFirst") else pool
        if selector_type == "RPG.GameCore.TargetIndex":
            if selector.get("IndexType") != "IndexStrict":
                return []
            pool = self.engine._allies_alive() + self.engine._enemies_alive()
            index = int(_fixed_number(selector.get("IndexValue")))
            return [pool[index]] if 0 <= index < len(pool) else []
        if selector_type == "RPG.GameCore.AIComposeSelector":
            compose_type = selector.get("ComposeType") or "ByAnd"
            if compose_type == "ByOr":
                for child in selector.get("SelectorList") or []:
                    candidates = self._select_target_candidates(child)
                    if candidates:
                        return candidates
                return []
            if compose_type == "ByAnd":
                result = None
                for child in selector.get("SelectorList") or []:
                    candidates = self._select_target_candidates(child)
                    result = candidates if result is None else [
                        target for target in result if target in candidates]
                return result or []
        return []

    def _select_target(self, selector: Dict[str, Any]) -> Optional[Any]:
        candidates = self._select_target_candidates(selector)
        if not candidates:
            return None
        if (selector.get("RandomWhenEquals") and self.engine.pipeline.mode == MODE_ROLL
                and self.engine.pipeline.rng is not None):
            return self.engine.pipeline.rng.choice(candidates)
        return candidates[0]

    def _run_tasks(self, tasks: Iterable[Dict[str, Any]]) -> Optional[Action]:
        selected: Optional[Action] = None
        for task in tasks or []:
            task_type = task.get("$type")
            if task_type == "RPG.GameCore.DefineDynamicValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")))
            elif task_type == "RPG.GameCore.SetDynamicValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")))
            elif task_type == "RPG.GameCore.SetDynamicValueByAddValue":
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")),
                                  _fixed_number(task.get("ResetValue")), add=True)
            elif task_type == "RPG.GameCore.SetDynamicValueByCopying":
                alias = str((task.get("FromTargetType") or {}).get("Alias", ""))
                if not is_self_target_alias(alias):
                    return None
                self._set_dynamic(_dynamic_key(task.get("ToDynamicKey")),
                                  self._dynamic(_dynamic_key(task.get("FromDynamicKey"))))
            elif task_type == "RPG.GameCore.SetDynamicValueByCharacterCount":
                alias = str((task.get("ReadTargetType") or {}).get("Alias", ""))
                count = self._team_count(alias)
                if count is None:
                    return None
                self._set_dynamic(_dynamic_key(task.get("DynamicKey")), count)
            elif task_type == "RPG.GameCore.RandomConfig":
                task_list = task.get("TaskList") or []
                odds = task.get("OddsList") or []
                if not task_list or len(task_list) != len(odds):
                    return None
                weights = [_fixed_number(odd) for odd in odds]
                if any(weight < 0 for weight in weights) or sum(weights) <= 0:
                    return None
                index = 0
                if self.engine.pipeline.mode == MODE_ROLL and self.engine.pipeline.rng is not None:
                    roll = self.engine.pipeline.rng.random() * sum(weights)
                    acc = 0.0
                    for i, weight in enumerate(weights):
                        acc += weight
                        if roll <= acc:
                            index = i
                            break
                selected = self._run_tasks(task_list[index]) or selected
            elif task_type == "RPG.GameCore.Retarget":
                target_type = task.get("TargetType") or {}
                spec = (target_type.get("Alias")
                        if target_type.get("$type") == "RPG.GameCore.TargetAlias" else target_type)
                members = self._team_members(spec)
                if members is None or _fixed_number(task.get("MaxNumber") or 1) != 1.0:
                    return None
                predicate = task.get("Predicate")
                if predicate is not None:
                    members = [st for st in members if self._predicate(predicate, st)]
                if members:
                    if (task.get("ByRandom") and self.engine.pipeline.mode == MODE_ROLL
                            and self.engine.pipeline.rng is not None):
                        self.target_override = self.engine.pipeline.rng.choice(members)
                    else:
                        self.target_override = members[0]
                    selected = self._run_tasks(task.get("TaskList") or []) or selected
                else:
                    self.target_override = None
                    selected = self._run_tasks(task.get("FailedTaskList") or []) or selected
            elif task_type == "RPG.GameCore.PredicateTaskList":
                branch = "SuccessTaskList" if self._predicate(task.get("Predicate") or {}) else "FailedTaskList"
                selected = self._run_tasks(task.get(branch) or []) or selected
            elif task_type == "RPG.GameCore.SelectAISkillTarget":
                chosen = self._select_target(task.get("Selector") or {})
                self.target_override = chosen or self.engine._pick_ally_target(self.actor_state)
            elif task_type == "RPG.GameCore.AddModifier":
                alias = str((task.get("TargetType") or {}).get("Alias", ""))
                if not is_self_target_alias(alias):
                    return None
                modifier_id = _dynamic_key(task.get("ModifierName"))
                self.engine._apply_modifier(self.actor_state, Modifier(
                    modifier_id=modifier_id, name=modifier_id, modifier_type="buff",
                    duration=0, dispellable=False))
            elif task_type == "RPG.GameCore.RemoveModifier":
                alias = str((task.get("TargetType") or {}).get("Alias", ""))
                if not is_self_target_alias(alias):
                    return None
                self.engine._remove_modifier(
                    self.actor_state, _dynamic_key(task.get("ModifierName")), "config_ai")
            elif task_type == "RPG.GameCore.UseSkill":
                action_id = self.policy.skill_ids.get(str(task.get("SkillName", "")),
                                                      str(task.get("SkillName", "")))
                if self._cooldown_ready(action_id):
                    selected = self.actions[action_id]
                    self._mark_executed(action_id)
            elif task_type == "RPG.GameCore.UseSequencedSkill":
                selected = self.engine._select_enemy_policy_action(self.actor_state)
            elif task_type == "RPG.GameCore.DebugLog":
                continue
            else:
                return None
        return selected

    def choose_action(self) -> Optional[Action]:
        decision = self._choose(self.policy.config.get("DecisionList") or [])
        if decision is None:
            return None
        root = decision.get("RootTask") or {}
        if root.get("$type") != "RPG.GameCore.SequenceConfig":
            return None
        dynamic_before = dict(self.runtime["dynamic_values"])
        action = self._run_tasks(root.get("TaskList") or [])
        if action is None:
            # 冷却/不可用导致空行动时，决策任务不得遗留计数器或目标副作用。
            self.runtime["dynamic_values"] = dynamic_before
            self.target_override = None
        return action
