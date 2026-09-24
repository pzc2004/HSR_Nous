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
        if act.action_type == "assist":
            # 助战技是插入式行动（不占本人回合）——不进回合合法行动集；
            # 发动走引擎 fire_assist 原语（额度闸/消耗/插入执行）
            continue
        if act.action_type == "elation_skill":
            # 欢愉技是体系触发行动（阿哈时刻/代放族——21_elation.md §21.4）——不进
            # 回合合法行动集；发动走阿哈时刻主体/trigger_action 代放（两通道均不过本集）
            continue
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

    **单引擎一次性**：`_cursor` 随 select_action 单向推进、不自动复位——同一实例喂
    第二台引擎会从上一局中途继续（实例状态污染）；golden case 每局新建实例。
    """

    rotation: List[str] = field(default_factory=lambda: ["basic"])
    ult_timing: str = ULT_AFTER_ACTION

    def __post_init__(self) -> None:
        assert self.ult_timing in (ULT_BEFORE_ACTION, ULT_AFTER_ACTION, ULT_NEVER)
        assert self.rotation, "rotation 不能为空（空脚本 = 无行动可选，select_action 必回退 legal[0]，策略形同虚设）"
        self._cursor = 0  # 实例状态：见类 docstring"单引擎一次性"

    def select_action(self, actor_state: "ActorState", legal: List[Action], engine=None) -> Action:
        """统一决策接口：从合法行动集按脚本选择；脚本行动不合法时回退第一个合法行动."""
        if not legal:
            raise RuntimeError("legal_action_set 为空——policy 无可选")
        want = self.rotation[self._cursor % len(self.rotation)]
        self._cursor += 1
        for act in legal:
            if act.action_type == want:
                return act
        return legal[0]

    def select_target(self, actor_state: "ActorState", action_type: str,
                      candidates: list, engine=None):
        """统一决策接口（目标）：脚本策略不选目标——None=引擎缺省（首个存活敌人/自己）。"""
        return None

    def select_ultimate(self, actor_state: "ActorState", ready: list, engine=None):
        """统一决策接口（终结技窗口）：旧口径——只放行动方自己的终结技（ready 中查自己）；
        自己不 ready 则 None=本窗口不放（与 v2b 前 _try_ultimate 内联逻辑逐行为等价）。"""
        return next((a for st, a in ready if st is actor_state), None)

    def wait_segment(self, actor_state: "ActorState", action, seg_index: int, engine=None):
        """统一决策接口（段间决策，B35①②）：多段行动段间挂起点.

        返回 None = 缺省路径（index 对齐变体 + 保持当前目标）；手动实现可回答
        (变体下标, 目标 actor_id)（选招/换目标，见 debug.py `_ManualPolicy`）。
        脚本策略直通——expected/roll 确定性零影响。
        """
        return None


class CompiledPolicyRuntime:
    """CompiledPolicy 的运行时执行：按优先级降序评估条件，首个命中者生效."""

    def __init__(self, compiled_policy, expr_compiler=None) -> None:
        self.policy = compiled_policy
        self.ult_timing = compiled_policy.ult_timing  # 统一决策接口的一部分（原由 engine 外挂读取）
        self.expr = expr_compiler or ExprCompiler()

    def select_action(self, actor_state: ActorState, legal: List[Action], engine: "CombatEngine") -> Action:
        """统一决策接口：scripted/hybrid 先查逐回合脚本（B4 回放变体），未命中按 mode 分流；
        rule_based 走 select_action_type 求值 → 按 action_id / action_type 解析到具体行动."""
        if self.policy.mode in ("scripted", "hybrid"):
            hit = self._script_lookup(actor_state, engine)
            if hit is not None:
                return hit
            if self.policy.mode == "scripted":
                raise RuntimeError(
                    f"scripted policy 未覆盖 turn {engine.state.turn_count + 1} "
                    f"actor {actor_state.actor.actor_id}（严格模式——未覆盖即报错，14_policy）")
            # hybrid：未覆盖回合回退规则匹配
        want = self.select_action_type(actor_state, engine)
        return (next((a for a in legal if a.action_id == want), None)
                or next((a for a in legal if a.action_type == want), legal[0]))

    def _script_lookup(self, actor_state: ActorState, engine: "CombatEngine") -> Optional[Action]:
        """逐回合脚本查找（turn = state.turn_count + 1——turn_count 在回合末递增，决策时点
        看到的比人类回合数少 1；script turn 1 起）。actor 先按 actor_id 再按显示名匹配；
        action 先按 action_id 再按 action_type 匹配（合法集内解析，非法/被锁=None）。"""
        turn = engine.state.turn_count + 1
        aid = actor_state.actor.actor_id
        legal = legal_action_set(actor_state, engine.actions_by_actor.get(aid, []),
                                 engine.skill_points)
        # available_if 条件闸与决策点同源（03_actor §3.8.1）——脚本轴不能越过条件锁
        #（被闸行动按"不在合法集"报错，与被锁同口径）
        legal = engine._legal_with_available_if(actor_state, legal)
        for e in self.policy.script:
            if e["turn"] != turn:
                continue
            if e["actor"] not in (aid, actor_state.actor.name):
                continue
            hit = (next((a for a in legal if a.action_id == e["action"]), None)
                   or next((a for a in legal if a.action_type == e["action"]), None))
            if hit is None:
                raise RuntimeError(
                    f"scripted policy turn {turn} actor {e['actor']!r} 的行动 {e['action']!r}"
                    f" 不在合法集（被锁/不存在——脚本轴与战斗状态失配）")
            return hit
        return None

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
        # 敌人下一动行动值（14_policy 敌人意图可见性 5a：相对当前时钟的预计 AV——
        # "卡在敌人行动前开盾"族策略；无存活敌人 → 9999.0）
        ctx["enemy_next_av"] = self._enemy_next_av(engine)
        # $team 跨 actor 聚合（§22.4——max($team.atk) / sum($team.broken) 族策略）
        ctx["team"] = engine.team_namespace()
        ctx.update(self.policy.parameters)
        return ctx

    @staticmethod
    def _enemy_next_av(engine: "CombatEngine") -> float:
        if engine.scheduler is None:
            return 9999.0
        for actor, _kind, t in engine.scheduler.preview(20):
            if engine._is_monster(actor):
                return max(0.0, t - engine.state.clock)
        return 9999.0

    def select_action_type(self, actor_state: ActorState, engine: "CombatEngine") -> str:
        ctx = self._context(actor_state, engine)
        for rule in self.policy.action_rules:
            if rule.condition_expr is None or self.expr.evaluate(rule.condition_expr, ctx, engine.pipeline.rng):
                return rule.action
        return "basic"

    def _apply_selector(self, sel, candidates: List[ActorState], actor_state: ActorState,
                        ctx: Dict[str, Any], engine: "CombatEngine") -> Optional[ActorState]:
        """单个选择器求值（B31 目标代数求值器——字符串/旧 dict 脱糖别名，代数 dict 直写；
        词表对齐 target_algebra（单一事实源），无命中兜底 candidates[0]（原口径）."""
        from hsr_nous.sim.target_algebra import desugar_policy_legacy, eval_algebra

        if sel == "self":
            # self 是"从候选里找自己"（不是 take 1）——语义特殊，别名单列（与目标代数
            # where 同效但省去逐例注入 actor_id）
            return next((s for s in candidates if s.actor.actor_id == actor_state.actor.actor_id),
                        actor_state)
        spec = desugar_policy_legacy(sel)
        picked = eval_algebra(spec, pool=list(candidates), engine=engine, expr=self.expr)
        if picked:
            return picked[0]
        # 兜底：无命中退首个候选（filter/has_modifier 等原口径；空候选=None）
        return candidates[0] if candidates else None

    def select_ultimate(self, actor_state: ActorState, ready: list, engine: "CombatEngine") -> Optional[Any]:
        """统一决策接口（终结技窗口）：编译策略同 Scripted 旧口径——只放行动方自己的终结技."""
        return next((a for st, a in ready if st is actor_state), None)

    def wait_segment(self, actor_state: ActorState, action, seg_index: int, engine: "CombatEngine"):
        """统一决策接口（段间决策，B35①②）：编译策略直通——缺省路径（index 对齐变体 +
        保持当前目标；逐击选招恒取变体 0，与 ScriptedPolicy 同口径，确定性零影响）."""
        return None

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
