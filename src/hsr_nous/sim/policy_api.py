"""策略接口：legal_action_set 生成 + 决策点注入 + 固定脚本 policy（golden case 用）+ 编译策略运行时.

原则：policy 只选不越权——legal_action_set 之外的选择引擎不接受。
CompiledPolicyRuntime 从 engine.py 迁入（God-object 切分第三刀，纯搬家零逻辑改动）：
CompiledPolicy（action_rules/target_rules）的运行时求值与目标选择器解析本体；
engine 侧同名 import 为 re-export 口径（tests 直引 engine 不变）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim.resources import ultimate_available
from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.effect_types import POLICY_SELECTOR_DICT_TYPES, POLICY_TARGET_SELECTORS

if TYPE_CHECKING:
    from hsr_nous.sim.engine import CombatEngine

# 终结技插入时机
ULT_BEFORE_ACTION = "before_action"   # 行动准备期插入
ULT_AFTER_ACTION = "after_action"     # 行动后窗口插入（吃"本回合"效果）
ULT_NEVER = "never"


def legal_action_set(
    state: ActorState,
    actions: List[Action],
    skill_points: int,
) -> List[Action]:
    """当前状态下的合法行动集.

    - basic / follow_up 类恒合法
    - skill：战技点够才在集
    - ultimate：能量满才在集（ultimate_available）
    """
    legal: List[Action] = []
    for act in actions:
        if act.action_type == "ultimate":
            if ultimate_available(state, act):
                legal.append(act)
        elif act.skill_point_cost > 0:
            if skill_points >= act.skill_point_cost:
                legal.append(act)
        else:
            legal.append(act)
    return legal


@dataclass
class ScriptedPolicy:
    """固定脚本 policy（golden case / 回归测试用）.

    rotation：按回合循环的行动类型列表，如 ["skill", "basic", "basic"]；
    ult_timing：终结技插入时机（可大时如何处理）。
    """

    rotation: List[str] = field(default_factory=lambda: ["basic"])
    ult_timing: str = ULT_AFTER_ACTION

    def __post_init__(self) -> None:
        assert self.ult_timing in (ULT_BEFORE_ACTION, ULT_AFTER_ACTION, ULT_NEVER)
        assert self.rotation, "rotation 不能为空（空脚本 = 无行动可选，select_action 必回退 legal[0]，策略形同虚设）"
        self._cursor = 0

    def select_action(self, legal: List[Action]) -> Action:
        """从合法行动集按脚本选择；脚本行动不合法时回退第一个合法行动."""
        if not legal:
            raise RuntimeError("legal_action_set 为空——policy 无可选")
        want = self.rotation[self._cursor % len(self.rotation)]
        self._cursor += 1
        for act in legal:
            if act.action_type == want:
                return act
        return legal[0]
class CompiledPolicyRuntime:
    """CompiledPolicy 的运行时执行：按优先级降序评估条件，首个命中者生效."""

    def __init__(self, compiled_policy, expr_compiler=None) -> None:
        self.policy = compiled_policy
        self.expr = expr_compiler or ExprCompiler()

    def _context(self, actor_state: ActorState, engine: "CombatEngine") -> Dict[str, Any]:
        st = actor_state.actor.stats
        ctx: Dict[str, Any] = {
            "energy": actor_state.current_energy,
            "max_energy": st.max_energy,
            "skill_points": engine.skill_points,
            "hp": actor_state.current_hp,
            # effective 口径（吃 hp_pct/flat/覆写 modifier）——与 hook $self.max_hp 同口径
            "max_hp": engine.pipeline.effective_stats(actor_state)["hp"],
        }
        # 自定义资源平铺（res_<rid>——策略条件可读火种/毁伤等，"火种<12 攒战技"族策略的前提）
        for rid, val in actor_state.resources.items():
            ctx[f"res_{rid}"] = val
        # 形态状态（"常态攒资源/形态内打强化"双段策略的前提）
        cfg = actor_state.state_config
        ctx["in_state"] = cfg is not None
        ctx["state"] = cfg.state if cfg is not None else ""
        ctx.update(self.policy.parameters)
        return ctx

    def select_action_type(self, actor_state: ActorState, engine: "CombatEngine") -> str:
        ctx = self._context(actor_state, engine)
        for rule in self.policy.action_rules:
            if rule.condition_expr is None or self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                return rule.action
        return "basic"

    @staticmethod
    def _key_of(s: ActorState, key: str) -> float:
        """选择器 key 解析："stats.X"→面板属性，"current_hp"→当前生命，"hp_pct"→生命百分比."""
        if key == "current_hp":
            return s.current_hp
        if key == "hp_pct":
            return s.current_hp / max(s.actor.stats.hp, 1e-6)
        if key.startswith("stats."):
            return float(getattr(s.actor.stats, key[6:], 0.0) or 0.0)
        return 0.0

    def _apply_selector(self, sel, candidates: List[ActorState], actor_state: ActorState,
                        ctx: Dict[str, Any], engine: "CombatEngine") -> Optional[ActorState]:
        """单个选择器求值；词表对齐 effect_types（POLICY_TARGET_SELECTORS / POLICY_SELECTOR_DICT_TYPES 单一事实源）."""
        rng = engine.pipeline.rng

        def pick_random() -> ActorState:
            # 期望模式不掷骰（B22）：退化为第一个候选，保持确定性
            if engine.pipeline.mode == MODE_ROLL and rng is not None:
                return rng.choice(candidates)
            return candidates[0]

        if isinstance(sel, str):
            if sel in ("primary_target", "enemy_single", "all_enemies", "all_allies"):
                return candidates[0]  # 全体语义由 target_type=aoe/ally_aoe 表达，这里定主目标
            if sel == "self":
                return next((s for s in candidates if s.actor.actor_id == actor_state.actor.actor_id),
                            actor_state)
            if sel == "lowest_hp":
                return min(candidates, key=lambda s: s.current_hp)
            if sel == "lowest_hp_ally":
                return min(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_hp":
                return max(candidates, key=lambda s: s.current_hp)
            if sel == "lowest_hp_pct":
                return min(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_hp_pct":
                return max(candidates, key=lambda s: self._key_of(s, "hp_pct"))
            if sel == "highest_atk":
                return max(candidates, key=lambda s: self._key_of(s, "stats.atk"))
            if sel == "lowest_atk":
                return min(candidates, key=lambda s: self._key_of(s, "stats.atk"))
            if sel == "highest_spd":
                return max(candidates, key=lambda s: self._key_of(s, "stats.spd"))
            if sel == "lowest_spd":
                return min(candidates, key=lambda s: self._key_of(s, "stats.spd"))
            if sel == "broken":
                return next((s for s in candidates if s.broken), candidates[0])
            if sel == "highest_break":
                return max(candidates, key=lambda s: self._key_of(s, "stats.break_effect"))
            if sel == "random":
                return pick_random()
            # 未知选择器编译期就该炸（build_compiler._compile_policy 白名单）；
            # 走到这里=绕过编译层手写 CompiledPolicy，同口径炸，不许静默兜底 candidates[0]
            raise ValueError(
                f"未知 policy target 选择器 {sel!r}（合法集合：{sorted(POLICY_TARGET_SELECTORS)}）"
            )
        if isinstance(sel, dict):
            t = sel.get("type")
            if t == "min":
                return min(candidates, key=lambda s: self._key_of(s, sel.get("key", "current_hp")))
            if t == "max":
                return max(candidates, key=lambda s: self._key_of(s, sel.get("key", "current_hp")))
            if t == "random":
                return pick_random()
            if t == "has_modifier":
                mid = sel.get("modifier_id", "")
                return next((s for s in candidates if mid in s.modifiers), candidates[0])
            if t in ("filter", "first"):
                cond = sel.get("condition", "")
                expr = self.expr.try_compile(cond) if cond else None
                matched = [s for s in candidates if expr is None
                           or self.expr.evaluate(expr, {**ctx, **self._target_ctx(s)}, rng)]
                return matched[0] if matched else candidates[0]
            raise ValueError(
                f"未知 policy target 参数化选择器 type {t!r}（合法集合：{sorted(POLICY_SELECTOR_DICT_TYPES)}）"
            )
        raise ValueError(f"policy target 选择器须为字符串或参数化 dict，收到 {type(sel).__name__}：{sel!r}")

    @staticmethod
    def _target_ctx(s: ActorState) -> Dict[str, Any]:
        """filter/first 条件里可用的目标侧上下文."""
        return {
            "target_hp": s.current_hp,
            "target_hp_pct": s.current_hp / max(s.actor.stats.hp, 1e-6),
            "target_broken": s.broken,
        }

    def select_target(self, actor_state: ActorState, action_type: str, candidates: List[ActorState], engine: "CombatEngine") -> Optional[ActorState]:
        if not candidates:
            return None
        ctx = self._context(actor_state, engine)
        ctx["action_type"] = action_type
        for rule in self.policy.target_rules:
            if rule.condition_expr is not None and not self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                continue
            picked = self._apply_selector(rule.selector, candidates, actor_state, ctx, engine)
            if picked is not None:
                return picked
        return candidates[0]
