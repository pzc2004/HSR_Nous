"""战斗引擎：直伤闭环 + 击破 + 敌人行动 + 波次切换；护盾/生存（锁血·月茧·复活）/光环/轮次/模板 hooks 已落地.

回合四段（决策卡 #16 / mechanics 03 §3.6）：
    回合开始(A 类结算：DOT 跳伤) → 行动 → 行动后窗口(终结技/插入合法点) → 回合结束(B 类结算：modifier tick)
击破（mechanics 04）：削韧闸 → 击破伤害 → 属性击破效果（DOT/控制/延后）→ 敌方回合开始韧性恢复（冻结顺延）。
"""
from __future__ import annotations

import copy
import warnings
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Dict, List, Optional

from hsr_nous.sim.bus import EventBus
from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.hooks import HookRuntime, _CondSelfNS, _HookSelfNS  # noqa: F401  # _HookSelfNS 为 re-export（tests 直引本模块）
from hsr_nous.sim.modifiers import ModifierBook
from hsr_nous.sim.pipeline import MODE_ROLL, SettlementPipeline
from hsr_nous.sim.policy_api import (  # CompiledPolicyRuntime 本体已迁 policy_api.py，此处为 re-export（tests 直引本模块）
    ULT_AFTER_ACTION, ULT_BEFORE_ACTION, CompiledPolicyRuntime, ScriptedPolicy, legal_action_set,
)
from hsr_nous.sim.resources import ult_threshold_of, ultimate_available
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN, EXTRA_NORMAL, Scheduler
from hsr_nous.sim.state import BREAK_DOT_ID_PREFIX, MOON_COCOON_ID, ActorState, BattleState, Modifier, StateConfig
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter

MAX_TURNS_SAFETY = 200  # 兜底防死循环


class _LazyTeamNS:
    """`$team` 命名空间惰性版（§22.4 口径不变）：构造零 effective_stats 调用.

    hp/energy/broken/actor_id 急切（裸状态直读零开销）；atk/max_hp/spd 面板键首次
    访问才逐 ally 求值 effective_stats 并缓存——_HookSelfNS 同纪律（不引用面板键的
    hook/policy 条件零面板开销；急切版每 hook ctx 全队求值，重蹈 54% 浪费审计覆辙）。
    """

    __slots__ = ("_engine", "_allies", "_effs", "hp", "energy", "broken", "actor_id")

    def __init__(self, engine: "CombatEngine") -> None:
        self._engine = engine
        self._allies = [s for s in engine._allies_alive()
                        if s.actor.summon_flags.get("ally_targetable", True)]
        self._effs: Optional[List[Dict[str, Any]]] = None
        self.hp = [s.current_hp for s in self._allies]
        self.energy = [s.current_energy for s in self._allies]
        self.broken = [bool(s.broken) for s in self._allies]
        self.actor_id = [s.actor.actor_id for s in self._allies]

    def _panels(self) -> List[Dict[str, Any]]:
        """面板统计：首次访问逐 ally 求值一次并缓存（同一条件内多键共享）."""
        if self._effs is None:
            self._effs = [self._engine.pipeline.effective_stats(s) for s in self._allies]
        return self._effs

    @property
    def atk(self) -> List[float]:
        return [e["atk"] for e in self._panels()]

    @property
    def max_hp(self) -> List[float]:
        return [e["hp"] for e in self._panels()]

    @property
    def spd(self) -> List[float]:
        return [e["spd"] for e in self._panels()]

    @property
    def certified_banger(self) -> List[float]:
        """逐 ally 好活当赏合并值（21_elation.md §21.7——「按我方最高好活当赏值计算」
        族取数源：`max($team.certified_banger)`，欢愉主 800904 天赋追加段首实例）."""
        return [self._engine._resource_value(s, "certified_banger") for s in self._allies]

    @property
    def elation(self) -> List[float]:
        """逐 ally 欢愉度面板（爻光战技光环「按我方欢愉角色欢愉度」族取数源）."""
        return [e["elation"] for e in self._panels()]


class CombatEngine:
    """回合制战斗模拟器（机制面见模块 docstring；输入只认 sim_schema）.

    hooks 运行时（模板 hooks 订阅/条件求值/effect 分发）已迁 `sim/hooks.py`（`HookRuntime`），
    本类 `_subscribe_compiled_hooks`/`_hook_ctx`/`_hook_target_states`/`_run_hook_effect` 为薄委托；
    modifier 生命周期（施加/tick 走字/驱散净化/spec 物化）与护盾（物化/并行吸收）已迁
    `sim/modifiers.py`（`ModifierBook`），本类同名方法为薄委托；
    编译策略运行时（action_rules/target_rules 求值 + 目标选择器）已迁 `sim/policy_api.py`
    （`CompiledPolicyRuntime`，本模块同名 import 为 re-export，tests 直引口径不变）。
    """

    MONSTER_TYPES = {"monster", "enemy"}

    def __init__(
        self,
        encounter: Encounter,
        actions_by_actor: Optional[Dict[str, List[Action]]] = None,
        policy: Optional[ScriptedPolicy] = None,
        mode: str = MODE_ROLL,
        seed: Optional[int] = None,
        initial_sp: Optional[int] = None,
        initial_energy_ratio: Optional[float] = None,
        wave_enemies: Optional[Dict[int, List[Actor]]] = None,
        expr: Optional[Any] = None,
        summon_defs: Optional[Dict[str, Any]] = None,
        binding_params: Optional[Dict[str, Dict[str, float]]] = None,
        resource_decls: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        self.encounter = encounter
        self.actions_by_actor = actions_by_actor or {}
        # 召唤物定义注册件（模板 summons 块的编译产物 SummonDef；from_compiled 注入——
        # summon effect 按 summon_id 查表布场，见 12_summon）
        self.summon_defs: Dict[str, Any] = summon_defs or {}
        # 绑定参数注册件（variable_bindings 求值产物——光锥叠影参数族；
        # hook 表达式经 `$self.<param>` 命名空间消费，见 hooks.py _HookSelfNS）
        self._binding_params: Dict[str, Dict[str, float]] = binding_params or {}
        # 统一决策源（行动+目标+终结技时机一个接口）：ScriptedPolicy / CompiledPolicyRuntime /
        # ManualDecision（debug）三实现可换；不再有 compiled_runtime/policy/target_hook 三段式特例
        self.decision = policy or ScriptedPolicy()
        # 自动施放目标免问旗标（玩家没点放的行动不问玩家目标——12_summon §12.6 control=auto
        # 忆灵回合 / trigger_action 插入式行动（万敌"automatically used"族）两通道挂/摘，
        # 嵌套计数安全；_resolve_targets 见此旗标跳过决策源直接 prefer/缺省；
        # 手动触发型（manual_trigger 窗口放）不挂旗标→照问）
        self._auto_target_ctx = 0
        # 阿哈时刻 pool 覆写锚（21_elation.md §21.4——额外阿哈时刻固定值结算时，行动层
        # elation 路由读此锚代替实时池；常规时刻/非阿哈代放=None 读实时池）
        self._aha_pool_override: Optional[float] = None
        # 表达式编译器：一台引擎一份（共享 _cache）——build 编译期创建经 from_compiled 注入，
        # hook condition / policy runtime / pipeline scoped 加成三处共用
        self._expr = expr or ExprCompiler()
        self.pipeline = SettlementPipeline(mode=mode, seed=seed, expr=self._expr)
        # 光环提供者注入：全队 scope=team 光环（排除目标自己已持有的，防重复计）
        # 辐射仅限**持有者同侧**（scope=team=我方队伍光环——1507 大行迹3"Zone 内队友伤害+50%"
        # 实证：此前敌方面板也吃到我方 team 光环（e1 all_dmg+0.5），辐射域错配=敌方白吃 buff；
        # 同侧判定=_is_monster 相等（我方光环→我方、敌方光环→敌方））
        self.pipeline.set_aura_provider(lambda st: [
            m for other in self.state.actors.values()
            if other is not st and other.alive and not other.banished
            and self._is_monster(other.actor) == self._is_monster(st.actor)
            for m in other.modifiers.values() if m.effect_scope == "team"
        ])
        # 条件光环运行时注入（04_modifier §4.16：enable_if/stat_exprs 语境工厂 + ⚠ 告警槽）；
        # _cond_aura_present = 场上存在条件件标记（HP 事件后速度重同步的开销闸，modifiers 挂载时置位）
        self.pipeline.set_condition_runtime(self._cond_runtime, self._cond_warn)
        # hit_condition 命中域宿主函数注入（debuff_count($event.target) 族——hooks 函数集
        # 同槽，$self 绑定携带者）+ actor 反查（DoT 跳伤时刻按 source_id 反查施加者——
        # 跳伤攻击侧 scoped 求值源）
        self.pipeline.set_hit_functions(lambda st: self._hooks._hook_functions(st),
                                        lambda st: _HookSelfNS(self, st))
        self.pipeline.set_actor_lookup(lambda aid: self.state.actors.get(aid))
        self._cond_aura_present = False
        self.bus = EventBus()
        self.state = BattleState()
        self.scheduler: Optional[Scheduler] = None
        self._last_target_id: Optional[str] = None  # 最近行动主目标（on_action payload 寻址槽）
        # 逐 actor 最近行动主目标（prefer_target "owner_last_target" 的取数锚——
        # 忆灵"优先忆师最后攻击的敌人"族，长夜月 Evey 1141301；_last_target_id 的 per-actor 版）
        self._last_target_by_actor: Dict[str, str] = {}
        # 最近一次行动的实际战技点消耗（on_action payload sp_consumed 槽——爻光 150204
        # 大吉大利「攻击消耗战技点额外触发」/23053 耗点叠层族；before_consume 抵扣后
        # 净值，_execute_action 每次行动覆写）
        self._last_sp_consumed: int = 0
        # 缺省读簿（rulebook constants.initial_sp / initial_energy_ratio——决策卡 A1 零字面量）
        self.initial_sp = initial_sp if initial_sp is not None else self.pipeline.initial_sp_default()
        self.state.skill_points = self.initial_sp
        self.initial_energy_ratio = (initial_energy_ratio if initial_energy_ratio is not None
                                     else self.pipeline.initial_energy_ratio_default())
        self.wave_enemies = wave_enemies or {}
        self.current_wave = 0  # 0 = encounter.actors 初始阵容；1..N = waves
        self.state_configs_by_actor: Dict[str, List[StateConfig]] = {}
        self._initial_modifiers: Dict[str, List[Modifier]] = {}  # from_compiled 注入，_init_state 时挂载
        self._banished_by_state: Dict[str, List[str]] = {}  # 形态境界离场的队友名单（exit 时回场）
        # 入口技（变身族）"结束本回合"：置位后本回合行动阶段整体跳过——官方原文"结束本回合"，
        # 无论谁的回合（ult_now 插队/窗口 before 两路同口径；after 路行动已发生不受影响）
        self._turn_consumed = False
        self._compiled_hooks: List[Any] = []  # 模板 hooks 块的编译产物（from_compiled 注入）
        self._hooks = HookRuntime(self)  # hooks 运行时本体在 sim/hooks.py（同名方法为薄委托）
        self._modifiers = ModifierBook(self)  # modifier/护盾运行时本体在 sim/modifiers.py（同名方法为薄委托）
        self._resource_decls: Dict[str, Dict[str, Any]] = resource_decls or {}  # 模板 custom_resources 值块（setup 初始化 current、获得统一入口截断）
        # 资源来源记账（provenance: true 族——(actor_id, rid) → 来源集合；"当前持有"口径，耗尽清空重计）
        self._resource_provenance: Dict[tuple, set] = {}
        self.state_entry_actions: Dict[str, tuple[str, StateConfig]] = {}
        # 月茧"同时死亡"批处理的瞬时事件号（结算临时量，不进 snapshot；同种子递增值一致，B16 不破）：
        # _cocoon_event_counter 单调递增发号；_cocoon_event_seq 当前结算中的事件号（0=不在事件内，
        # 嵌套事件退出时还原外层）；_cocoon_saved_event 本战斗月茧救人发生时的事件号
        self._cocoon_event_counter = 0
        self._cocoon_event_seq = 0
        self._cocoon_saved_event = 0

    @property
    def skill_points(self) -> int:
        """战技点读取别名：本体在 `state.skill_points`（B16：SP 是战斗状态，进 snapshot）."""
        return self.state.skill_points

    def _count_team_path(self, path: str) -> float:
        """队伍编成计数（count_team 宿主，04_modifier §4.16）：我方**角色**中命途为 path 的
        人数——含阵亡（"队伍中"=编成口径与存活无关）；忆灵/召唤物（actor_type summon）不计."""
        return float(sum(1 for s in self.state.actors.values()
                         if not self._is_monster(s.actor)
                         and s.actor.actor_type == "character"
                         and s.actor.path == path))

    def _actor_in_group(self, st: ActorState, group: str) -> bool:
        """in_group 判定单漏斗（03_actor §3.1）：`path:<name>` 按 path 字段自动映射
        （命途分组无需声明）；其余查 actor.groups 声明表（faction:xxx 开放命名空间）."""
        if group.startswith("path:"):
            return st.actor.path == group[len("path:"):]
        return group in (st.actor.groups or [])

    def _count_team_group(self, path: str = "", group: str = "") -> float:
        """count_team 析取扩展（昔涟 1415102"黄金裔或「记忆」命途"族）：path 单给=命途计数；
        group 单给=分组计数；同给=**析取**（命途匹配或分组命中）；双空=旧口径（path=="" 计数）."""
        if not path and not group:
            return self._count_team_path("")
        return float(sum(1 for s in self.state.actors.values()
                         if not self._is_monster(s.actor)
                         and s.actor.actor_type == "character"
                         and ((bool(path) and s.actor.path == path)
                              or (bool(group) and self._actor_in_group(s, group)))))

    def _cond_warn(self, msg: str) -> None:
        """条件光环求值失败告警槽（B8 同口径：按不生效 + ⚠ 战斗日志留痕）."""
        self.state.log.append(f"AV{self.state.clock:.1f}: {msg}")

    def _cond_runtime(self, target_st: ActorState, mod: Modifier, panel_of: Any):
        """条件光环语境工厂（04_modifier §4.16，pipeline 注入回调）.

        - holder 解析：光环件（scope=team）辐射到他人面板时携带者≠面板目标——反查持有者，
          条件/档位按**携带者**语境求值（昔涟 1415103 队友增伤按昔涟速度判定）
        - `$self` = _CondSelfNS（面板预置无条件件面板——条件域一切面板读取经 panel_of，
          读不到任何条件件贡献，构造防环）
        - 宿主函数：hook 函数集 + count_team/stat_of；max_hp_of 改写为无条件件面板口径
          （hook 版读全量面板会在条件域重入条件求值）
        """
        if target_st.modifiers.get(mod.modifier_id) is mod:
            holder = target_st
        else:
            holder = next((s for s in self.state.actors.values()
                           if s.modifiers.get(mod.modifier_id) is mod), target_st)
        ns = _CondSelfNS(self, holder, panel_of(holder))

        def _resolve(target: Any) -> Optional[ActorState]:
            if isinstance(target, ActorState):
                return target
            if isinstance(target, _HookSelfNS):
                return target._st
            aid = getattr(target, "actor_id", None) or str(target)
            return self.state.actors.get(str(aid))

        def stat_of(target: Any, stat: Any) -> float:
            st2 = _resolve(target)
            if st2 is None:
                return 0.0
            v = panel_of(st2).get(str(stat), 0.0)
            return float(v) if isinstance(v, (int, float)) else 0.0

        functions = dict(self._hooks._hook_functions(holder))
        functions["count_team"] = lambda path="", group="": self._count_team_group(str(path), str(group))
        functions["stat_of"] = stat_of
        functions["max_hp_of"] = lambda target: (
            0.0 if _resolve(target) is None else float(panel_of(_resolve(target))["hp"]))
        # res_ 平铺同 hook/available_if 域（三域同槽——1507 千冶•刃 Zone 门控光环
        # enable_if "res__zone_on >= 1" 实证：缺平铺=条件域求值失败按不生效+B8 静默死件）
        return {"self": ns,
                **self._res_ns(holder)}, functions

    def _resync_cond_speed(self, _et: str, _payload: Dict[str, Any], _ctx: Any) -> None:
        """条件光环速度重同步（04_modifier §4.16：HP 变化翻转速度档——倒置的火炬族；
        面板域唯一推式消费点，其余全懒求值；场上无条件件时零开销）."""
        if not self._cond_aura_present:
            return
        for st in self.state.actors.values():
            if not self._is_monster(st.actor) and st.alive:
                self._modifiers._sync_speed(st)   # 内部本就全队扫——任一我方单位作入口即可
                break

    def team_namespace(self) -> Any:
        """`$team` 命名空间（跨 actor 聚合，§22.4）：我方全员逐值列表（all_allies 同口径
        ——ally_targetable 过滤），外套白名单聚合函数使用（`max($team.atk)` /
        `sum($team.broken)` / `count($team.atk)`）。惰性版：构造零 effective_stats 调用，
        面板键（atk/max_hp/spd）首次访问才逐 ally 求值一次并缓存（$self 同纪律——
        不引用面板键的 hook/policy 条件零面板开销）。"""
        return _LazyTeamNS(self)

    def _sp_max(self) -> int:
        """战技点上限（mechanics 06 §6.1）：默认 rulebook constants.sp_max_default（5）；
        state.sp_max_override > 0 时被改写（花火天赋"上限提高至 7"族挂点——实例未到，预留）."""
        return int(self.state.sp_max_override or self.pipeline.sp_max_default())

    def _adjust_skill_points(self, delta: int, *, reason: str = "") -> None:
        """SP 增减唯一通道：clamp 到 [0, _sp_max()]（mechanics 06 §6.1：上限默认 5、下限 0）.

        reason=变化源（on_skill_point_change 载荷——花火"因战技消耗"过滤族：
        `action:<id>`（行动耗产）/ `hook`（gain_skill_point 钩）/ `""`（其余路径））。"""
        if delta < 0:
            # 战技点消耗前 waterfall（火花 climax 抵扣族：改写消耗量/取消——抵扣发生在扣点前；
            # SP 是队级资源，payload actor 恒 ""（无单一归属单位）——**reason 透传行动归属**
            #（f"action:<id>" 串：抵扣"仅特定角色自身耗点"族的唯一判定凭据——饮月逆鳞
            # 只抵自身三档强化普攻 1213 首实例，2026-09-12 补口）
            wp = self.bus.waterfall("before_consume", {
                "actor": "", "resource_id": "sp", "amount": -float(delta),
                "reason": reason}, self.state)
            if wp.get("cancel"):
                return   # 消耗被取消（全额抵扣——技能照放但不扣点）
            delta = -max(0, int(round(float(wp.get("amount", -float(delta))))))
        before = self.state.skill_points
        self.state.skill_points = max(0, min(self._sp_max(), self.state.skill_points + int(delta)))
        if self.state.skill_points != before:
            # SP 变化发射点（结构化日志 skill_point_change 槽取数点；11_combat_log）
            self.bus.emit("on_skill_point_change", {
                "before": before, "after": self.state.skill_points,
                "reason": reason}, self.state)
        if delta < 0 and self.state.skill_points < before:
            self.bus.emit("after_consume", {
                "actor": "", "resource_id": "sp", "amount": before - self.state.skill_points,
                "current": self.state.skill_points}, self.state)

    def _resource_value(self, st: ActorState, rid: str) -> float:
        """资源读取统一口径（21_elation §21.7）.

        - `punchline`（笑点）= **队伍账**全局池（state.punchline——全队共享，不属任何 actor）
        - `certified_banger`（好活当赏）= 引擎原生条目列表合并值（21_elation §21.5）
        - 其余 = 持有者账（st.resources）
        """
        if rid == "punchline":
            return float(self.state.punchline)
        if rid == "certified_banger":
            return float(sum(e["value"] for e in st.banger_entries))
        return float(st.resources.get(rid, 0.0))

    def _res_ns(self, st: ActorState) -> Dict[str, float]:
        """表达式 `res_` 命名空间：持有者账平铺 + 两个重定向键覆写（三域同槽——
        hook ctx / available_if ctx / modifier 烘焙 ctx，1507 Zone 门控同族防线）。
        res_punchline 额外阿哈覆写档（_aha_pool_override——覆写的是「池」本身，
        凡读池处同锚：复合表达式（150621 "res_punchline*(1+E4闩)" 族）与钩条件
        同读锚定值，hooks.py 字符串等值特判之外的唯一通道）。"""
        ns = {f"res_{k}": v for k, v in st.resources.items()}
        ns["res_punchline"] = (float(self._aha_pool_override)
                               if self._aha_pool_override is not None
                               else float(self.state.punchline))
        ns["res_certified_banger"] = self._resource_value(st, "certified_banger")
        return ns

    def _gain_resource(self, st: ActorState, rid: str, amount: float, *,
                       source_id: str = "", from_bank: bool = False) -> float:
        """自定义资源获得/消耗统一入口（16_custom_resources 值块 v1）.

        - clamp [0, max]（decl.max，"inf"=无上限）；消耗 floor 0
        - 溢出路由：decl.overflow_mode == "bank" 且非返还路径时，截断溢出量灌 `<rid>_bank`
          （银行自身也按其 max clamp——二层溢出作废；③防递归：from_bank=True（返还路径）
          只 clamp 不回流，多出作废）
        - provenance: true 时记录获得来源集合（"当前持有"口径——耗尽清空重计，决策卡 #20）
        一切获得路径（action.resource_gain 通道 / hook gain_resource|set_resource / 特殊充能
        消耗）都经此。返回实际增减量（截断后）。
        """
        if rid == "punchline":
            # 笑点队伍账（21_elation §21.3）：写全局池（无上限——公式自收敛），事件
            # actor 仍记持有者（模板 on_resource_gain 的 $event.actor 口径不变）；
            # 消耗不走 before_consume waterfall（阿哈清池=系统结算非抵扣语义，P2b）
            cur = self.state.punchline
            new = max(0.0, cur + float(amount))
            self.state.punchline = new
            self.bus.emit("on_resource_gain", {
                "actor": st.actor.actor_id, "resource_id": rid,
                "amount": new - cur, "current": new, "overflow": 0.0}, self.state)
            return new - cur
        if rid == "certified_banger":
            # 好活当赏条目列表（21_elation §21.5 引擎原生形制）：正=新增条目（回合数=
            # 持有者 banger_turns 资源档（缺省 2——spec 固定时长；爻光行迹 1502103 #2=1
            # → 3 回合族经 decl current 覆写），逐条目独立计时）；负=LIFO 逐条扣减
            #（实例未到，先定口径）
            if amount > 0:
                turns = float(st.resources.get("banger_turns", 2.0))
                st.banger_entries.append({"value": float(amount), "turns": turns})
            elif amount < 0:
                rest = -float(amount)
                while rest > 0 and st.banger_entries:
                    rest -= st.banger_entries.pop()["value"]
            merged = self._resource_value(st, rid)
            self.bus.emit("on_resource_gain", {
                "actor": st.actor.actor_id, "resource_id": rid,
                "amount": float(amount), "current": merged, "overflow": 0.0}, self.state)
            return float(amount)
        decl = (self._resource_decls.get(st.actor.actor_id, {}) or {}).get(rid) or {}
        cur = st.resources.get(rid, 0.0)
        if amount < 0:
            # 消耗前 waterfall（火花 climax 抵扣族：改写消耗量/取消——抵扣发生在扣减前）；
            # reason 键与 SP 通道同形（自定义资源暂无来源语义、恒 ""——$event.reason 恒可读）
            wp = self.bus.waterfall("before_consume", {
                "actor": st.actor.actor_id, "resource_id": rid,
                "amount": -float(amount), "reason": ""}, self.state)
            if wp.get("cancel"):
                return 0.0   # 消耗被取消（全额抵扣——hook 侧已自理代偿）
            amount = -float(wp.get("amount", -float(amount)))
        new = cur + float(amount)
        max_v = decl.get("max")
        cap = None if max_v in (None, "inf") else float(max_v)
        # max_override（16 §16.12——modifier 覆写资源上限，昔涟 1141517 新蕊溢出至 200% 族）：
        # 携带者本资源覆写件取最大（多覆写/基础 cap 同取大——v1 只抬不压，压低实例未到达；
        # 覆写件到期不回收已超限值，下次获得按有效上限截断自然回落）
        ov = [m.max_override for m in st.modifiers.values()
              if m.target_resource == rid and m.max_override > 0]
        if ov:
            cap = max(cap, max(ov)) if cap is not None else max(ov)
        overflow = 0.0   # 溢出截断量（on_resource_gain 载荷字段——溢出驱动族读取端：黄泉残梦→四相断我）
        if cap is not None and new > cap:
            overflow = new - cap
            new = cap
            if decl.get("overflow_mode") == "bank" and not from_bank and overflow > 0:
                bank_rid = f"{rid}_bank"
                bank_decl = (self._resource_decls.get(st.actor.actor_id, {}) or {}).get(bank_rid) or {}
                bank_max = bank_decl.get("max")
                bank_cap = None if bank_max in (None, "inf") else float(bank_max)
                bank_cur = st.resources.get(bank_rid, 0.0)
                bank_new = bank_cur + overflow if bank_cap is None else min(bank_cur + overflow, bank_cap)
                st.resources[bank_rid] = bank_new   # 二层溢出作废（不回流）
                if bank_new != bank_cur:
                    self.bus.emit("on_resource_gain", {
                        "actor": st.actor.actor_id, "resource_id": bank_rid,
                        "amount": bank_new - bank_cur, "current": bank_new}, self.state)
            # from_bank 或 overflow_mode != bank：溢出作废（防递归钉③）
        if new < 0.0:
            new = 0.0
        st.resources[rid] = new
        if decl.get("provenance") and amount > 0 and source_id:
            self._resource_provenance.setdefault((st.actor.actor_id, rid), set()).add(source_id)
        if new <= 0.0:
            self._resource_provenance.pop((st.actor.actor_id, rid), None)   # 耗尽清空重计
        self.bus.emit("on_resource_gain", {
            "actor": st.actor.actor_id, "resource_id": rid,
            "amount": new - cur, "current": new, "overflow": overflow}, self.state)
        if amount < 0:
            # 消耗后发射（实际消耗 = 截断后的真实减量；记账/对偶触发族挂载点）
            self.bus.emit("after_consume", {
                "actor": st.actor.actor_id, "resource_id": rid,
                "amount": cur - new, "current": new}, self.state)
        return new - cur

    @classmethod
    def from_compiled(
        cls,
        compiled,
        *,
        mode: str = MODE_ROLL,
        seed: Optional[int] = None,
        initial_sp: Optional[int] = None,
        initial_energy_ratio: Optional[float] = None,
    ) -> "CombatEngine":
        """从 CompiledEncounter 直接构建引擎（DSL 模板 → 战斗的正式入口）."""
        engine = cls(
            compiled.to_encounter(),
            actions_by_actor=compiled.actions_by_actor,
            policy=ScriptedPolicy(),
            mode=mode,
            seed=seed,
            initial_sp=initial_sp,
            initial_energy_ratio=initial_energy_ratio,
            wave_enemies={i: list(w) for i, w in compiled.stage.waves.items()},
            expr=compiled.expr,
            summon_defs=dict(compiled.summon_defs),
            binding_params={k: dict(v) for k, v in compiled.binding_params_by_actor.items()},
        )
        engine.decision = CompiledPolicyRuntime(compiled.policy, expr_compiler=engine._expr)
        engine._initial_modifiers = compiled.modifiers_by_actor
        engine._compiled_hooks = list(compiled.hooks)
        engine._resource_decls = {k: {r: dict(d) for r, d in v.items()}
                                  for k, v in compiled.resource_decls_by_actor.items()}
        engine._trigger_order = dict(compiled.trigger_order)
        for actor_id, (cfg, entry_id) in compiled.state_configs_by_actor.items():
            engine.register_state_config(actor_id, cfg, entry_action_id=entry_id)
        return engine

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """公开初始化：构建全状态与调度器（测试预置 modifier 前先调）."""
        if self.scheduler is None:
            self._init_state()

    def _spawn_actor(self, actor: Actor) -> ActorState:
        """参战单位布场：ActorState 创建（敌人初始满韧、按 initial_energy_ratio 布能）+ 伤害账本登记."""
        toughness = actor.stats.max_toughness if self._is_monster(actor) else 0.0
        st = ActorState(
            actor=actor,
            current_hp=actor.stats.hp,
            current_energy=actor.stats.max_energy * self.initial_energy_ratio,
            alive=True,
            toughness=toughness,
        )
        self.state.actors[actor.actor_id] = st
        self.state.damage_by_actor.setdefault(actor.actor_id, 0.0)
        return st

    # ------------------------------------------------------------------
    # 召唤物（12_summon：布场/离场单漏斗；hook effect summon/dismiss_summon 经此）
    # ------------------------------------------------------------------

    def summon_actor(self, owner_state: ActorState, summon_id: str) -> ActorState:
        """召唤物入场：按 SummonDef 布场（继承召唤者 Layer-1 面板 → 上行动条 → actor_enter）.

        继承的是召唤者**编译期面板**（含光锥/遗器归并），不是战斗内 effective（12_summon §12.5）。
        av:false（triggered 型，小伊卡族）挂入行动条即冻结——正常条永不弹出，但额外回合
        队列不受 freeze 影响（next_actor 先弹队列），机制仍可授其额外回合。
        重复召唤口径：已在场存活 = 不动（日志留名）；曾离场 = 重新布场（旧 handle 已随
        离场冻结，调度映射由 add_actor 换新）。
        """
        sdef = self.summon_defs.get(str(summon_id))
        if sdef is None:
            raise ValueError(
                f"summon effect 引用未登记召唤物 {summon_id!r}"
                f"（合法集合：{sorted(self.summon_defs)}——模板 summons 块编译产物）")
        existing = self.state.actors.get(sdef.actor.actor_id)
        if existing is not None and existing.alive:
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {sdef.actor.name} 已在场，重复召唤不生效")
            return existing
        stats = sdef.actor.stats
        if sdef.inheritance == "full":
            stats = copy.deepcopy(owner_state.actor.stats)
        elif isinstance(sdef.inheritance, tuple):
            stats = copy.deepcopy(stats)
            for f in sdef.inheritance:
                # 列表项按 base_stats YAML 键名书写——StatBlock 字段名对齐（"def"→def_，
                # 编译期 base_stats 映射同口径；长夜月忆灵部分继承首实例踩到）
                f2 = "def_" if f == "def" else f
                setattr(stats, f2, copy.deepcopy(getattr(owner_state.actor.stats, f2)))
        if sdef.max_hp_ratio > 0:
            # max_hp_ratio（12_summon v1.1）：hp 覆写 = 召唤时刻召唤者**有效**生命上限 × 比例
            # （含行迹/装备与召唤瞬间战斗内 buff；一次性定格不追踪后续——小伊卡 = 风堇 ×0.5 族）。
            # 覆盖 inheritance 的 hp 分量；none 分支的 stats 是编译资产本体，覆写前防御性拷贝
            if stats is sdef.actor.stats:
                stats = copy.deepcopy(stats)
            stats.hp = float(self.pipeline.effective_stats(owner_state)["hp"]) * sdef.max_hp_ratio
        # 忆灵无能量经济（mechanics 01 §能量恢复/05 §5.1：行动/受击回能归忆师）——领域事实
        # 定格 max_energy=0（含 full 继承来 summoner 能量上限的情形）：能量获得天然 clamp 到 0，
        # 一切消费方（web/调试器/策略）读同一事实，呈现层零特判。none 分支同上的防御性拷贝
        if stats is sdef.actor.stats:
            stats = copy.deepcopy(stats)
        stats.max_energy = 0.0
        actor = replace(sdef.actor, stats=stats)
        st = self._spawn_actor(actor)
        self._place_after_owner(actor.actor_id, owner_state.actor.actor_id)
        # 召唤物 custom_resources 初始化（12_summon v1.2：模板 summons 块值块——
        # 风堇 tally 由小伊卡记账族；布场时按 decl.current 初始化，与 setup 的角色通道同口径）
        for rid, decl in (self._resource_decls.get(actor.actor_id) or {}).items():
            st.resources.setdefault(rid, float((decl or {}).get("current", 0.0)))
        assert self.scheduler is not None
        self.scheduler.add_actor(actor)
        if not actor.summon_flags.get("av", True):
            self.scheduler.freeze(actor.actor_id)
        self.bus.emit("actor_enter", {
            "actor": actor.actor_id, "reason": "summon",
            "actor_type": actor.actor_type, "wave_index": self.current_wave,
        }, self.state)
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {owner_state.actor.name} 召唤 {actor.name} 入场")
        return st

    def _place_after_owner(self, summon_id: str, owner_id: str) -> None:
        """布场站位（12_summon position=after_owner）：召唤物紧邻忆师右侧，忆师已有
        忆灵簇时排簇尾。state.actors 插入序即站位（blast 相邻/前端卡序/受击范围同源）；
        离场不离字典，重召天然回原位。
        """
        actors = self.state.actors
        if summon_id not in actors or owner_id not in actors:
            return
        st = actors.pop(summon_id)
        items = list(actors.items())
        idx = next(i for i, (aid, _) in enumerate(items) if aid == owner_id)
        end = idx + 1
        while end < len(items) and items[end][1].actor.summoner_id == owner_id:
            end += 1
        items.insert(end, (summon_id, st))
        self.state.actors = dict(items)

    def dismiss_summon_actor(self, summon_id: str, *, reason: str = "dismiss") -> bool:
        """召唤物离场：before_actor_exit（生前）→ alive=False + 调度器冻结 + actor_exit（reason=dismiss）.

        未在场/已离场 = no-op（False）；召唤者死亡由 _check_death 单漏斗自动调用。
        before_actor_exit 在 alive=False 之前发射——持有者在世（alive 闸不挡），
        「消失时」生前结算族挂载点（遐蝶 1140706 晦翼自爆首实例，2026-09-17 时序扶正）。
        """
        st = self.state.actors.get(str(summon_id))
        if st is None or not st.alive or st.actor.actor_type != "summon":
            return False
        self.bus.emit("before_actor_exit", {"actor": st.actor.actor_id, "reason": reason}, self.state)
        st.alive = False
        if self.scheduler is not None:
            self.scheduler.freeze(st.actor.actor_id)
        self.bus.emit("actor_exit", {"actor": st.actor.actor_id, "reason": reason}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {st.actor.name} 离场（{reason}）")
        return True

    def _init_state(self) -> None:
        for actor in self.encounter.actors:
            self._spawn_actor(actor)
        self.scheduler = Scheduler(list(self.encounter.actors))
        self.state.skill_points = self.initial_sp
        # 轮次系统：预算终点初始化（encounter.cycle 为 None 时保持 0 占位、不参与 tick——见 _tick_cycle）
        if self.encounter.cycle is not None:
            self.state.cycle_end_clock = float(self.encounter.cycle.first_cycle_av)
        # 编译期归并的初始 modifier（遗器套装等）挂载
        for actor_id, mods in self._initial_modifiers.items():
            st = self.state.actors.get(actor_id)
            if st is not None:
                for m in mods:
                    # 拷贝挂载（replace 浅拷贝）：compiled 的初始件是编译资产——直接挂共享
                    # 实例会让上一局的 tick/叠层突变（duration/stacks）流入同一 compiled
                    # 重建的下一台引擎
                    self._apply_modifier(st, replace(m))
        # 开局满血口径：初始件（行迹/遗器/光锥 hp 族）抬有效上限后 current 顶到有效上限——
        # 否则携 hp% 初始件的角色以残血进场（B-TR① 回填暴露：阿兰天赋失血比
        # 1199.52/1319.472=0.909 误读为已损血；游戏语义=进场恒满血）
        for st in self.state.actors.values():
            st.current_hp = float(self.pipeline.effective_stats(st)["hp"])
        # 模板声明资源初始化（16_custom_resources 值块：init=decl.current——表达式 res_* 恒有定义的前提）
        for actor_id, decls in self._resource_decls.items():
            st = self.state.actors.get(actor_id)
            if st is not None:
                for rid, decl in decls.items():
                    st.resources.setdefault(rid, float((decl or {}).get("current", 0.0)))
        # 阿哈时刻特殊调度单位（21_elation.md §21.4，B40 P2b）：初始 modifier 挂载之后、
        # hook 订阅之前（进战笑点发射不触达模板钩——「进战即得」非事件语义，待实测终审）
        self._init_aha()
        # 模板 hooks 订阅（必须在 on_battle_start 之前挂上——开局类 hook 才收得到）
        self._subscribe_compiled_hooks()
        # 条件光环速度重同步订阅（04_modifier §4.16：HP 变化翻转速度档的唯一推式消费点；
        # _init_state 每台引擎一次——scheduler None 闸保证，不会重复订阅）
        self.bus.subscribe("on_hp_decrease", self._resync_cond_speed)
        self.bus.subscribe("on_hp_increase", self._resync_cond_speed)
        self.bus.emit("on_battle_start", {"encounter": self.encounter.encounter_id}, self.state)

    # ------------------------------------------------------------------
    # 阿哈时刻（21_elation.md §21.4，B40 P2b）——特殊调度单位主体
    # ------------------------------------------------------------------

    def _elation_members(self) -> List[ActorState]:
        """存活欢愉角色（阿哈流程的参与集——离场/阵亡不参与本次结算）."""
        return [st for st in self._allies_alive() if st.actor.path == "elation"]

    def _aha_speed(self, members: List[ActorState]) -> float:
        """阿哈速度公式（21_elation.md §21.4：80+V1×0.2+V2×0.1+V3×0.05+V4×0.02，
        V=欢愉角色有效速度降序前 4；V4 系数 0.02 采米游社含演算实例版——0.025 备选待实测）."""
        spds = sorted((float(self.pipeline.effective_stats(st)["spd"]) for st in members),
                      reverse=True)[:4]
        return 80.0 + sum(c * v for c, v in zip((0.2, 0.1, 0.05, 0.02), spds))

    def _init_aha(self) -> None:
        """阿哈时刻布场（B40 P2b）：队伍存在欢愉角色即进战在条.

        - actor_type "aha"：不算我方单位（_allies_alive 排除——不可被选目标/不计全灭/
          不吃光环辐射），只是行动条上的结算触发器
        - 进战每欢愉角色 +1 阿哈笑点（队伍账——21_elation.md §21.3）+ 进战 20 好活
          当赏（§8.1，2 回合条目）
        - 波次重置豁免（「转面不重跑」——scheduler._wave_reset_exempt 注册）
        """
        members = self._elation_members()
        if not members:
            return
        aha = Actor(actor_id="aha_instant", name="阿哈时刻", actor_type="aha",
                    stats=StatBlock(spd=self._aha_speed(members)))
        self.state.actors[aha.actor_id] = ActorState(actor=aha, current_hp=1.0)
        assert self.scheduler is not None
        self.scheduler.add_actor(aha)
        self.scheduler._wave_reset_exempt.add(self.scheduler.handle_of(aha.actor_id))
        for st in members:
            self._gain_resource(st, "punchline", 1.0)
            # §8.1 进战 20 好活当赏（2 回合条目——回合数档 banger_turns 覆写见 _gain_resource）
            self._gain_resource(st, "certified_banger", 20.0)
        self.state.log.append(
            f"AV{self.state.clock:.1f}: 阿哈时刻在条（速度 {self._aha_speed(members):.1f}，"
            f"欢愉角色 {len(members)} 名）")

    def _run_aha_turn(self, *, extra_pool: Optional[float] = None) -> None:
        """阿哈时刻结算（21_elation.md §21.4）.

        常规（extra_pool=None）：解控 → 共读实时池（行动层 elation 路由现场读值——清池
        在代放之后，官方「消耗笑点→触发欢愉技」全体欢愉技共享总值口径）→ 按参演编号
        升序代放各欢愉技 → 授好活当赏（值=本次消耗池）→ 清池 → on_aha_instant。
        额外阿哈时刻（extra_pool 给定——爻光终结技族）：固定值结算、不耗池、照授，
        行动层路由经 `_aha_pool_override` 覆写锚定固定值。
        结算后按全体欢愉角色现场速度重算阿哈速度（活体面板——米游社「E2 加速加到阿哈
        头上」实证；转波次不重新跑条由 scheduler 豁免集承载）。
        """
        members = sorted(self._elation_members(),
                         key=lambda st: (st.actor.elation_number or 9999))
        if not members:
            return
        # 解控（欢愉角色控制类件——dispellable 闸同常规驱散）
        for st in members:
            for mid in [m.modifier_id for m in st.modifiers.values()
                        if m.control_kind and m.dispellable]:
                self._remove_modifier(st, mid, "cleanse")
        pool = float(extra_pool) if extra_pool is not None else float(self.state.punchline)
        self.bus.emit("aha_instant_start", {
            "consumed": pool, "extra": 1 if extra_pool is not None else 0,
            "actors": [st.actor.actor_id for st in members]}, self.state)
        for st in members:
            eskill = next((a for a in self.actions_by_actor.get(st.actor.actor_id, [])
                           if a.action_type == "elation_skill"
                           and self._available_if_ok(st, a)), None)
            if eskill is None:
                continue
            if extra_pool is not None:
                self._aha_pool_override = pool
            try:
                self.trigger_action(st, eskill, tag="aha")
            finally:
                self._aha_pool_override = None
        # 授好活当赏（逐角色账，值=本次结算笑点；0 值不记条目——21_elation.md §21.5）
        if pool > 0:
            for st in members:
                self._gain_resource(st, "certified_banger", pool)
        if extra_pool is None:
            self.state.punchline = 0.0
        self.state.log.append(
            f"AV{self.state.clock:.1f}: 阿哈时刻结算——消耗笑点 {pool:.0f}"
            f"（{'额外' if extra_pool is not None else '常规'}，参演 {len(members)} 名）")
        self.bus.emit("aha_instant_end", {
            "consumed": pool, "extra": 1 if extra_pool is not None else 0,
            "actors": [st.actor.actor_id for st in members]}, self.state)
        # 速度重算（活体面板——结算后按现场有效速度重排下一趟）
        aha_st = self.state.actors.get("aha_instant")
        if aha_st is not None and self.scheduler is not None:
            new_spd = self._aha_speed(members)
            handle = self.scheduler.handle_of("aha_instant")
            old = float(self.scheduler.spd_of(handle, new_spd) or new_spd)
            if abs(new_spd - old) > 1e-9:
                aha_st.actor.stats.spd = new_spd
                self.scheduler.on_speed_change(aha_st.actor, old, new_spd)

    # ------------------------------------------------------------------
    # 终止判定
    # ------------------------------------------------------------------

    def _is_monster(self, actor: Actor) -> bool:
        return actor.actor_type in self.MONSTER_TYPES

    def _enemies_alive(self) -> List[ActorState]:
        return [s for s in self.state.actors.values() if self._is_monster(s.actor) and s.alive]

    def _allies_alive(self) -> List[ActorState]:
        """存活且在场（未 banish）的我方单位——选择器/敌方选目标/光环辐射的统一口径.

        `aha`（阿哈时刻特殊调度单位，21_elation.md §21.4）不算我方单位：不可被选
        目标、不计全灭判定、不吃光环辐射——它只是行动条上的一个结算触发器。
        """
        return [s for s in self.state.actors.values()
                if not self._is_monster(s.actor) and s.actor.actor_type != "aha"
                and s.alive and not s.banished]

    def _has_next_wave(self) -> bool:
        return (self.current_wave + 1) in self.wave_enemies

    def _should_terminate(self) -> bool:
        term = self.encounter.termination
        # 我方全灭：模式无关通则（游戏规则）——存活在场口径（放逐不算死；白厄 solo 期
        # 队友放逐仍在场不算全灭，白厄本人死了才是）
        if not self._allies_alive():
            return True
        # 对面全灭：模式无关通则（kill_target 模式即靠本分支判停，输出所需行动值/回合数）
        if not self._enemies_alive() and not self._has_next_wave():
            return True
        if term.mode == "fixed_av" and self.state.clock >= term.max_action_value and not self._has_next_wave():
            return True
        # 轮次上限截断（cycle.max_cycles > 0 且预算耗尽）
        cyc = self.encounter.cycle
        if cyc is not None and cyc.max_cycles > 0 and self.state.cycle_index > cyc.max_cycles:
            return True
        return False

    # ------------------------------------------------------------------
    # 轮次（全局时钟纯函数：预算满 → 进下一轮，mechanics 03 §3.1）
    # ------------------------------------------------------------------

    def _tick_cycle(self) -> None:
        """clock 前进后调用：跨过预算终点则进下一轮次（可连续跨多轮——长时间无行动）.

        轮次与任何单位的行动值/速度/推拉条无关，只在时钟前进时结算。
        """
        cyc = self.encounter.cycle
        if cyc is None:
            return
        while self.state.clock >= self.state.cycle_end_clock:
            self.bus.emit("on_cycle_end", {"cycle_index": self.state.cycle_index}, self.state)
            self.state.cycle_index += 1
            self.state.cycle_end_clock += float(cyc.subsequent_cycle_av)
            self.bus.emit("on_cycle_start", {
                "cycle_index": self.state.cycle_index,
                "budget": float(cyc.subsequent_cycle_av),
            }, self.state)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: —— 轮次 {self.state.cycle_index} ——")

    # ------------------------------------------------------------------
    # 波次切换
    # ------------------------------------------------------------------

    def _advance_wave_if_needed(self) -> None:
        """当前波敌人全灭且还有下一波：新敌人登场（忘却之庭模式附带转波次重置）."""
        if self._enemies_alive() or not self._has_next_wave():
            return
        assert self.scheduler is not None
        self.current_wave += 1
        newcomers = self.wave_enemies[self.current_wave]
        for actor in newcomers:
            self._spawn_actor(actor)
            self.scheduler.add_actor(actor)
            self.bus.emit("actor_enter", {"actor": actor.actor_id, "wave_index": self.current_wave,
                                          "actor_type": actor.actor_type}, self.state)
        # 转波次重置（cycle.reset_on_wave，忘却之庭；owner 实战确认 2026-08-24）：
        # 全体剩余距离重置 10000——倒计时实体除外（跨波按原行动值续跑，mechanics 03 §3.4）；
        # 轮次预算重置为首轮值、轮次计数不变（mechanics 03 §3.1"轮次数不重置"）。
        cyc = self.encounter.cycle
        if cyc is not None and cyc.reset_on_wave:
            self.scheduler.reset_action_gauge(except_countdown=True)
            self.state.cycle_end_clock = self.state.clock + float(cyc.first_cycle_av)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: 转波次重置——全体行动值重排（倒计时续跑），轮次预算重置 {cyc.first_cycle_av}")
        self.bus.emit("on_wave_start", {"wave_index": self.current_wave}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: —— 第 {self.current_wave + 1} 波 ——")

    # ------------------------------------------------------------------
    # modifier 基础层——运行时已迁 sim/modifiers.py（ModifierBook）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    def _apply_modifier(self, target: ActorState, mod: Modifier, *, apply_chance: float = 1.0) -> bool:
        return self._modifiers._apply_modifier(target, mod, apply_chance=apply_chance)

    def _sync_speed(self, target: ActorState) -> None:
        self._modifiers._sync_speed(target)

    def dispel(self, target: ActorState, max_count: int = 1) -> int:
        return self._modifiers.dispel(target, max_count)

    def purify(self, target: ActorState, max_count: int = 1) -> int:
        return self._modifiers.purify(target, max_count)

    def _remove_modifier(self, target: ActorState, modifier_id: str, reason: str = "expire") -> None:
        self._modifiers._remove_modifier(target, modifier_id, reason)

    def _tick_dots(self, actor_state: ActorState) -> None:
        self._modifiers._tick_dots(actor_state)

    def _tick_modifiers(self, actor_state: ActorState, anchor: str = "owner_turn_end") -> None:
        self._modifiers._tick_modifiers(actor_state, anchor)
        if anchor == "owner_turn_end" and actor_state.banger_entries:
            # 好活当赏条目计时（21_elation §21.5——持有者回合结束 -1，尽则除名；
            # 与 modifier duration 同拍；无事件词表实例——日志留痕不发明词汇）
            kept = []
            for e in actor_state.banger_entries:
                e["turns"] -= 1.0
                if e["turns"] > 0:
                    kept.append(e)
            if len(kept) != len(actor_state.banger_entries):
                dropped = sum(e["value"] for e in actor_state.banger_entries) - sum(
                    e["value"] for e in kept)
                actor_state.banger_entries = kept
                self.state.log.append(
                    f"AV{self.state.clock:.1f}: {actor_state.actor.name} 好活当赏 "
                    f"{dropped:.0f} 点到期（余 {sum(e['value'] for e in kept):.0f}）")

    def _tick_one_modifier(self, actor_state: ActorState, mod: Modifier) -> None:
        self._modifiers._tick_one_modifier(actor_state, mod)

    def _tick_source_modifiers(self, turn_actor: Actor, anchor: str = "source_turn_end") -> None:
        self._modifiers._tick_source_modifiers(turn_actor, anchor)

    @contextmanager
    def _damage_event(self):
        """一次伤害结算的批处理域：同事件内多个致死共享全队仅 1 次的月茧机会.

        owner 实战确认（2026-08-22）：同一次伤害事件（一次行动的多目标/多段结算，
        或同一批 hook 伤害）同时致死 N 人 → 这 1 次机会把 N 个全部送进月茧。
        嵌套事件（结算中 hook 触发反击/追加）各自独立发号，退出时还原外层事件号。
        """
        self._cocoon_event_counter += 1
        outer = self._cocoon_event_seq
        self._cocoon_event_seq = self._cocoon_event_counter
        try:
            yield
        finally:
            self._cocoon_event_seq = outer

    def _moon_cocoon_available(self) -> bool:
        """全队月茧次数当前是否可用：未消耗；或本次伤害事件内已消耗（同时致死共享同一次机会）."""
        if not self.state.moon_cocoon_used:
            return True
        return self._cocoon_event_seq != 0 and self._cocoon_saved_event == self._cocoon_event_seq

    def _emit_after_being_hit(self, *, amount: float, absorbed: float, damage_type: Any,
                              source_id: str, target_id: str, is_critical: bool,
                              seg_index: int, actor_type: str, action_type: Any,
                              hit_targets: List[str]) -> None:
        """after_being_hit 单发射口（23 章 §23.4 受击链收尾事件——钩子上读到盾吸收/锁血/复活/回能后的终态）.

        action 伤害段（_execute_action）与 hook 伤害（hooks.py deal_damage 的 follow_up/
        elation 族）共用同一发射契约——payload 键集 = bus DEFAULT_PAYLOAD_FIELDS 注册表
        （收割闸对账，勿手改）。附加伤害（category 'additional'——决策卡 #19「不再触发
        命中类监听」）与真实伤害（无攻击判定——mechanics 02 §2.8）不走本口。
        """
        self.bus.emit("after_being_hit", {
            "amount": amount, "absorbed": absorbed, "damage_type": damage_type,
            "source": source_id, "target": target_id, "is_critical": is_critical,
            "seg_index": seg_index, "actor_type": actor_type, "action_type": action_type,
            "hit_targets": hit_targets}, self.state)

    def _check_death(self, target: ActorState, source_id: str = "", *, action_id: str = "") -> None:
        """死亡检查：锁血 → 月茧 → 复活 → 真死（受击链末段四层分工）.

        与免死（before_take_damage waterfall cancel 伤害本身，test_death_immunity）的分工：
        - 免死：伤害根本不落账（cancel；140805"受到致命攻击不死"族）
        - 锁血（modifier.hp_lock）：伤害照算，HP 钳 1 不死（发 on_hp_lock——
          "无法被继续削减生命值"族挂载点，遐蝶 1407102 死龙半支）
        - 月茧（modifier.moon_cocoon 授予件 + state.moon_cocoon_used 战斗级次数）：
          留 1 血进月茧态，下次回合开始前受治疗/获得护盾则解除存活，否则到期真死
          （mechanics 11 §11.1）。次数语义（owner 实战确认 2026-08-22）：
          **全队每场共用 1 次**；同一伤害事件内多人同时致死 → 一次全部进茧；
          之后（含茧中人自己）再受致命击 → 直接真死（茧中不再保 1 血，无"延迟倒下"）
        - 复活（modifier.revive_percent）：HP 归零后消费复活件，按生命上限百分比回拉（发 on_revive）
        - 真死：四层全放行 → before_actor_exit（alive=False 之前——生前结算族挂载点，
          与 dismiss 漏斗同一事件；召唤物被打死由本发射点覆盖）→ alive=False →
          来源件生命周期摘除（remove_on_source_death 旗标件全场扫描，04_modifier §4.15）
          → actor_exit（死亡后清理族挂载点）

        action_id：致死行动归属（on_kill/on_hp_lock payload 携带——"指定技能击杀"族
        过滤锚）；无行动来源（dot/hook 非行动触发伤害）为 ""（hook 伤害由调用方
        继承触发事件的 action_id 传入）。
        """
        if target.current_hp > 0 or not target.alive:
            return
        # 锁血层：致命伤留 1 血
        if any(m.hp_lock for m in target.modifiers.values()):
            target.current_hp = 1.0
            self.bus.emit("on_hp_lock", {
                "source": source_id, "target": target.actor.actor_id,
                "action_id": action_id}, self.state)
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 锁血，HP 保持 1")
            return
        # 月茧层：授予件 + 全队次数可用 → 消耗次数进月茧态（茧中人授予件已消耗、
        # 次数已用，再受致命击自然落不到本层 → 真死，无需特判）
        cocoon_grant = next((m for m in target.modifiers.values()
                             if m.moon_cocoon and m.modifier_id != MOON_COCOON_ID), None)
        if cocoon_grant is not None and self._moon_cocoon_available():
            self._remove_modifier(target, cocoon_grant.modifier_id, "moon_cocoon")
            self.state.moon_cocoon_used = True
            self._cocoon_saved_event = self._cocoon_event_seq
            target.current_hp = 1.0
            self._apply_modifier(target, Modifier(
                modifier_id=MOON_COCOON_ID, name="月茧", modifier_type="buff",
                duration=1, dispellable=False, tick_anchor="owner_turn_start",
                # 记入致死来源：到期真死走 _check_death 单漏斗时 on_kill 据此发放
                source_id=source_id,
                moon_cocoon=True))
            self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 进入月茧状态")
            return
        # 复活层：消费复活件，set_hp_to_percent 回拉
        rev = next((m for m in target.modifiers.values() if m.revive_percent > 0), None)
        if rev is not None:
            self._remove_modifier(target, rev.modifier_id, "revive")
            # 茧中人被复活接住：月茧态随之结束（次数不退——进茧时已消耗）——否则到期会误杀
            if MOON_COCOON_ID in target.modifiers:
                self._remove_modifier(target, MOON_COCOON_ID, "cocoon_release")
                self.state.log.append(f"AV{self.state.clock:.1f}: {target.actor.name} 的月茧解除（复活）")
            max_hp = float(self.pipeline.effective_stats(target)["hp"])
            target.current_hp = max_hp * rev.revive_percent
            self.bus.emit("on_revive", {
                "target": target.actor.actor_id, "percent": rev.revive_percent,
                "hp": target.current_hp, "source": rev.source_id or source_id}, self.state)
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {target.actor.name} 触发复活，HP 回复至 {target.current_hp:,.0f}")
            return
        # 真死定论（锁血/月茧/复活三层均已放行）——before_actor_exit 在 alive=False 之前
        # 发射：持有者在世（alive 闸不挡），「死亡时」生前结算族挂载点；与 dismiss 漏斗
        # 同一事件（payload actor/reason 同 actor_exit——召唤物被打死不过 dismiss 漏斗，
        # 由本发射点盖「被打死」消失原因，2026-09-17 时序扶正）
        self.bus.emit("before_actor_exit", {"actor": target.actor.actor_id, "reason": "death"}, self.state)
        target.alive = False
        # 来源件生命周期摘除（modifier.remove_on_source_death，04_modifier §4.15）：死者为
        # 施加者的带旗 modifier 全场摘除——「陷入无法战斗状态时 X 效果也会被解除」族
        #（1313 蒙福者首实例）。点位在 alive=False 后、actor_exit 发射前：死后清理监听者
        # 读到摘除后终态；alive 闸使「自己听自己 actor_exit」结构性不触发，本扫描是引擎层
        # 统一通道（dismiss/放逐不经过——只认真死定论）
        for st in self.state.actors.values():
            for m in list(st.modifiers.values()):
                if m.remove_on_source_death and m.source_id == target.actor.actor_id:
                    self._remove_modifier(st, m.modifier_id, "source_death")
        # 形态主死亡：形态随死亡解除（exit_state 单漏斗）——境界 banish 的队友回场，
        # 防"主死形态未退"导致的队友永久 banish/frozen 孤儿化
        if target.state_config is not None:
            self.exit_state(target, reason="death")
        self.bus.emit("actor_exit", {"actor": target.actor.actor_id, "reason": "death"}, self.state)
        if source_id:
            self.bus.emit("on_kill", {
                "source": source_id, "target": target.actor.actor_id,
                "action_id": action_id}, self.state)
        # 召唤者死亡：其在场召唤物随之离场（owner_leave，12_summon 离场条件）
        for sd in self.summon_defs.values():
            if sd.owner_id == target.actor.actor_id:
                self.dismiss_summon_actor(sd.actor.actor_id)

    # ------------------------------------------------------------------
    # 击破
    # ------------------------------------------------------------------

    def _apply_toughness_damage(self, source: Actor, action: Action, target: ActorState) -> None:
        if action.toughness_dmg <= 0 or target.bars_exhausted:
            return
        # toughness_scope 闸（默认 own_element：攻击属性 ∈ 目标有效弱点才可削，植入弱点计入；
        # "all"=无视弱点（乱破/波提欧族）；元素列表=这些元素无视弱点可削（决策卡 #5）
        if action.toughness_scope == "all":
            can_reduce = True
        elif action.toughness_scope:
            can_reduce = action.damage_type in (
                set(self.pipeline.effective_weakness(target))
                | {str(e).lower() for e in action.toughness_scope})
        else:
            can_reduce = action.damage_type in self.pipeline.effective_weakness(target)
        # 削韧量 = rulebook toughness_damage 表达式求值（双效率池乘算 (1+a)(1+b)——spec 双池，实测待确认 B19；
        # 含光环辐射，pipeline 统一生效面；固定削韧项无实例，公式内中性 0）
        src_state = self.state.actors.get(source.actor_id)
        amount = self.pipeline.toughness_damage_amount(
            src_state, float(action.toughness_dmg),
            action_type=action.action_type, damage_type=action.damage_type or "")
        result = self.pipeline.toughness_damage(target, amount, action.damage_type or "", can_reduce)
        if result.value > 0:
            self.bus.emit("on_toughness_damage", {"amount": result.value, "source": source.actor_id, "target": target.actor.actor_id, "bar_index": target.bar_index}, self.state)
        if target.toughness <= 0 and not target.bars_exhausted:
            self._trigger_break(source, action, target)

    def _trigger_break(self, source: Actor, action: Action, target: ActorState) -> None:
        """击破（多韧性条 §3.10）：击破伤害 + 属性击破效果 + 通用推条 25% + 追加条切入.

        条序口径（v1 钉，§4.5/§4.6 对齐）：击破伤害**每条**结算（虚击破同公式——击破基数
        按主条 max 读，追加条口径待实测 B19）；**弱点击破状态/属性击破效果/通用推条仅末条**
        （多层韧性规则 §4.5——末条击破才进入弱点击破状态；`exo` 超韧性条（任意属性可削+
        击破同触发弱点击破，§4.6）v1 未收，无 DSL 字段）；追加条切入满值承接、削韧继续
        （虚韧性族）；末条破尽 = bars_exhausted（不再可削，至敌方回合开始韧性恢复回 bar 0）。
        击破伤害扣血**绕盾直扣**（不走 _absorb_with_shields）= B19 冻结口径
        （hsr-sim 对拍：击破绕盾直扣；游戏真相待实测）——与 mechanics 01 §1.3
        "护盾吸收层普适于一切伤害"的表述存在张力，实测后统一。
        """
        element = action.damage_type or "physical"
        idx = target.bar_index
        # 弱点击破状态载体条 = **主序末条**（idx == toughness_bars 声明条数；无声明条=主条
        # idx 0）。三种韧性风味对齐（mechanics 04 §4.5/§4.6 + 122504 云火昭）：
        # ① §4.5 多层韧性=主序声明条全走、末条才置 broken+效果（added_bars 为空时与旧
        #    is_last_bar 规则同值——行为不变）；② 云火昭虚韧性（add_toughness_bar 机制
        #    赋予条）=主条破即置 broken+效果，虚条破**只再吃击破伤害**不重复效果（赋予条
        #    在主序外，天然出载体集——击破伤害每条照结算不变）；③ exo 超韧性（§4.6
        #    "再次触发弱点击破"全效果）v1 未收、无 DSL 字段/实例——首个生产者落地时再立
        #    风味键（压缩优先，无实例不造键）。
        is_state_break = idx == len(target.actor.stats.toughness_bars)
        if is_state_break:
            target.broken = True   # 弱点击破状态仅主序末条
        self.bus.emit("on_break", {"source": source.actor_id, "target": target.actor.actor_id, "element": element, "bar_index": idx}, self.state)

        # 活体 ActorState 优先（削韧路径同口径）：裸 Actor 会被 pipeline._as_state 包成
        # 无 modifier 裸壳——攻击方战斗 modifier 全丢，且裸壳骗过光环身份排除（other is not st）。
        # None 兜底：外部直调 pipeline/引擎的旧测试可能传不在册的裸 Actor，退回兼容入口。
        src_state = self.state.actors.get(source.actor_id)
        dmg = self.pipeline.break_damage(src_state if src_state is not None else source, target, element)
        # 扣血在引擎层（pipeline.break_damage 纯结算不扣血；绕盾直扣=B19 冻结口径，见上）
        target.current_hp -= dmg.value
        if dmg.value > 0:
            # HP 下降发射点（击破伤害——受击族；reason='break'，词表冻结见 _execute_action）
            self.bus.emit("on_hp_decrease", {
                "amount": dmg.value, "source": source.actor_id,
                "reason": "break", "target": target.actor.actor_id}, self.state)
        self.state.total_damage += dmg.value
        self.state.damage_by_actor[source.actor_id] += dmg.value
        self.state.log.append(f"AV{self.state.clock:.1f}: {source.name} 触发击破，对 {target.actor.name} 造成 {dmg.value:,.0f} 击破伤害")
        self._check_death(target, source.actor_id, action_id=str(action.action_id or ""))

        if is_state_break:
            # 属性击破效果与通用推条仅主序末条（云火昭虚条破不重复效果——只再吃击破伤害）
            eff = self.pipeline.break_effect_of(element)
            # DoT 攻击侧快照（B27#3 快照切分）：施加时刻按施加者**有效面板**算好存件——
            # 跳伤时攻击侧乘区全读快照包（dot_snapshot_ctx），目标侧取现值（mechanics 02 §2.12）
            dot_src = src_state if src_state is not None else source
            # 控制/DoT 持续回合读 rulebook break_effects 表（mechanics 04 §4.8：控制 1 回合 / DoT 2 回合）
            if eff["control"] == "freeze":
                self._apply_modifier(target, Modifier(
                    modifier_id="BRK_FREEZE", name="冻结", modifier_type="control", debuff_kind="control",
                    duration=int(eff["control_duration"]), source_id=source.actor_id, control_kind="freeze"))
            elif eff["control"] in ("entangle", "imprison"):
                self._apply_modifier(target, Modifier(
                    modifier_id=f"BRK_{eff['control'].upper()}", name=eff["control"], modifier_type="control",
                    debuff_kind="control", duration=int(eff["control_duration"]), source_id=source.actor_id, control_kind=eff["control"]))
            if eff["dot_ratio"] is not None and eff["dot_ratio"] > 0:
                ratio = float(eff["dot_ratio"])
                self._apply_modifier(target, Modifier(
                    modifier_id=f"{BREAK_DOT_ID_PREFIX}{element}", name=f"{element}持续伤害", modifier_type="dot", debuff_kind="dot",
                    duration=int(eff["dot_duration"]), source_id=source.actor_id,
                    dot_element=element, dot_ratio=ratio,
                    dot_source_atk=float(self.pipeline.effective_stats(dot_src)["atk"]),
                    dot_snapshot_ctx=self.pipeline.dot_snapshot_context(dot_src, target, element, ratio)))
            elif eff.get("bleed_ratio"):
                # 裂伤：dot_ratio=null 的显式标记槽（bleed_ratio = 击破裂伤 ratio 值，rulebook 表驱动，无元素名特判）
                ratio = float(eff["bleed_ratio"])
                self._apply_modifier(target, Modifier(
                    modifier_id=f"{BREAK_DOT_ID_PREFIX}{element}", name="裂伤", modifier_type="dot", debuff_kind="dot",
                    duration=int(eff["dot_duration"]), source_id=source.actor_id,
                    dot_element=element, dot_ratio=ratio,
                    dot_source_atk=float(self.pipeline.effective_stats(dot_src)["atk"]),
                    dot_snapshot_ctx=self.pipeline.dot_snapshot_context(dot_src, target, element, ratio)))
            # 通用推条 25%（量子/虚数额外延后）
            assert self.scheduler is not None
            self.scheduler.delay_action(target.actor, eff["delay"])

        # 追加条切入（虚韧性族）：本条归零后下一条满值承接（bar_index 越过末条=条尽不可再削）
        if idx < len(target.extra_bars):
            target.bar_index = idx + 1
            target.toughness = float(target.extra_bars[idx])
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {target.actor.name} 的第 {idx + 1} 条韧性展开"
                f"（{target.toughness:.0f}，虚韧性族追加条）")
        else:
            target.bar_index = idx + 1   # 末条破尽（bars_exhausted 标记位）

    def _try_super_break(self, actor_state: ActorState, action: Action, target: ActorState, *,
                         was_broken: bool, source_action_id: str = "") -> None:
        """超击破（B38）：已击破目标受击 → 本击名义削韧值转化为超击破伤害.

        触发闸（mechanics 04 §4.4/§4.7）：命中前目标已处弱点击破状态（was_broken——
        造成击破的那一击本身不触发，与"双击破"段序一致：破击段只出击破伤害，后续段
        才出超击破）；本击名义削韧 > 0（超击破伤害不算攻击、不产生实际削韧——已击破
        目标按"该攻击若可削应削多少"结算）；任意属性攻击均触发（不看弱点，RES 区按
        攻击属性结算）；攻击方转换倍率池 > 0（pipeline 内判，无源=0 不造成超击破）。
        有效削韧 = toughness_damage_amount 同口径（双效率池 + hit_condition scoped——
        名义值，与实际削韧无关）。扣血绕盾直扣（击破族 B19 冻结口径，与 _trigger_break
        同）；发 on_super_break（契约冻结见 bus.DEFAULT_CONTRACT）+ on_hp_decrease
        （reason='break' 击破族词表——§4.7 击破伤害不算攻击，自然出 'hit' 域）。
        source_action_id：hook 段归属用（载荷父语境行动 id——"指定技能"族过滤锚；
        缺省取 action.action_id）。
        """
        if not was_broken or action.toughness_dmg <= 0:
            return
        effective_toughness = self.pipeline.toughness_damage_amount(
            actor_state, float(action.toughness_dmg),
            action_type=action.action_type, damage_type=action.damage_type or "")
        dmg = self.pipeline.super_break_damage(
            actor_state, target, effective_toughness=effective_toughness,
            damage_type=action.damage_type or "physical", action_type=action.action_type)
        if dmg.value <= 0:
            return
        target.current_hp -= dmg.value
        aid = source_action_id or str(action.action_id or "")
        self.bus.emit("on_super_break", {
            "source": actor_state.actor.actor_id, "target": target.actor.actor_id,
            "action_id": aid, "amount": dmg.value,
            "element": action.damage_type or "physical"}, self.state)
        self.bus.emit("on_hp_decrease", {
            "amount": dmg.value, "source": actor_state.actor.actor_id,
            "reason": "break", "target": target.actor.actor_id}, self.state)
        self.state.total_damage += dmg.value
        self.state.damage_by_actor[actor_state.actor.actor_id] += dmg.value
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor_state.actor.name} 触发超击破，"
            f"对 {target.actor.name} 造成 {dmg.value:,.0f} 超击破伤害")
        self._check_death(target, actor_state.actor.actor_id, action_id=aid)

    # ------------------------------------------------------------------
    # 形态机（#20 糖化：形态 = 标记 modifier + 合法性注入）
    # ------------------------------------------------------------------

    def register_state_config(self, actor_id: str, config: StateConfig, *, entry_action_id: str = "") -> None:
        """登记角色的形态配置；entry_action_id 非空 = 该 action 施放即进入形态."""
        self.state_configs_by_actor.setdefault(actor_id, []).append(config)
        if entry_action_id:
            self.state_entry_actions[entry_action_id] = (actor_id, config)

    def enter_state(self, actor_state: ActorState, config: StateConfig, duration: int = 0) -> None:
        """进入形态：挂标记（singleton_group=actor_state 互斥）+ 合法性注入生效."""
        marker = Modifier(
            modifier_id=config.marker_id(), name=config.state, modifier_type="buff",
            duration=duration, dispellable=False, singleton_group="actor_state",
            stat_effects=dict(config.stat_effects),  # 形态内面板（白厄"攻击力提高X%"族）
            grants_immune=list(config.grants_immune),  # 形态内免疫（140805 控制免疫族）
            # F2 来源记账：形态标记件（ref=形态显示名，缺省回退 state 标识符）
            source_kind="state", source_ref=config.name or config.state,
        )
        self._apply_modifier(actor_state, marker)
        actor_state.state_config = config
        # 计数器清零：上次形态（若曾进入）的残留不影响本轮倒计时
        actor_state.resources[f"_state_actions_{config.state}"] = 0.0
        # 境界：其他队友离场且无法行动（banish 族；退出时回场）
        if config.banish_allies_on_enter:
            for s in self.state.actors.values():
                if s is actor_state or self._is_monster(s.actor) or not s.alive or s.banished:
                    continue
                s.banished = True
                self.scheduler.freeze(s.actor.actor_id)
                self._banished_by_state.setdefault(actor_state.actor.actor_id, []).append(s.actor.actor_id)
                self.bus.emit("actor_exit", {"actor": s.actor.actor_id, "reason": "banish"}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {s.actor.name} 离场（境界）")
        self.bus.emit("on_state_change", {"actor": actor_state.actor.actor_id,
                                          "to_state": config.state, "from_state": None}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 进入形态 {config.name or config.state}")

    def exit_state(self, actor_state: ActorState, reason: str = "exit") -> None:
        """退出形态：摘标记（on_exit 全路径经 remove 单漏斗）+ 境界植入件清理."""
        if actor_state.state_config is None:
            return
        old_cfg = actor_state.state_config
        old = old_cfg.state
        # 境界植入件随形态解除（exit_remove_modifiers 清单，对全体敌人）
        for mid in old_cfg.exit_remove_modifiers:
            for e in self._enemies_alive():
                self._remove_modifier(e, mid, "state_exit")
        # 离场队友回场（banish 解除 + AV 解冻）
        for aid in self._banished_by_state.pop(actor_state.actor.actor_id, []):
            s = self.state.actors.get(aid)
            if s is not None and s.banished:
                s.banished = False
                self.scheduler.unfreeze(aid)
                self.bus.emit("actor_enter", {"actor": aid, "reason": "unbanish",
                                              "actor_type": s.actor.actor_type}, self.state)
                self.state.log.append(f"AV{self.state.clock:.1f}: {s.actor.name} 回场")
        self._remove_modifier(actor_state, actor_state.state_config.marker_id(), reason)
        actor_state.state_config = None
        self.bus.emit("on_state_change", {"actor": actor_state.actor.actor_id,
                                          "from_state": old, "to_state": None}, self.state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 退出形态 {old_cfg.name or old}")

    @staticmethod
    def _replaced_ids(replaces) -> set:
        """replaces_actions 的值归一为集合（str 或 List[str] 兼容）."""
        out: set = set()
        for v in replaces.values():
            out |= set(v) if isinstance(v, (list, tuple)) else {v}
        return out

    def _legal_with_state(self, actor_state: ActorState, legal: List[Action]) -> List[Action]:
        """合法性注入：replaces/locked 生效 + 增强行动仅形态下可用."""
        cfg = actor_state.state_config
        enhanced_ids = set()
        for c in self.state_configs_by_actor.get(actor_state.actor.actor_id, []):
            enhanced_ids |= self._replaced_ids(c.replaces_actions)
            if c.final_action_id:
                enhanced_ids.add(c.final_action_id)
        out: List[Action] = []
        for act in legal:
            if cfg is not None:
                if act.action_type in cfg.locked_actions:
                    continue
                if act.action_type in cfg.replaces_actions:
                    replaced = cfg.replaces_actions[act.action_type]
                    replaced_set = set(replaced) if isinstance(replaced, (list, tuple)) else {replaced}
                    if act.action_id not in replaced_set:
                        continue  # 原型被替换（增强件（可多个）之外的原行动不可用）
                out.append(act)
            else:
                if act.action_id in enhanced_ids:
                    continue
                out.append(act)
        return out

    def _available_if_ok(self, actor_state: ActorState, act: Action) -> bool:
        """行动级可用条件（03_actor §3.8.1）：无声明恒真；有声明现场求值——
        `$self`=行动方 + `res_<rid>` 平铺 + hook 函数族（controlled/resource_of 等）。
        求值失败按不可用 + ⚠ 战斗日志（B8 同口径）；手工构造的 Action（无预编译产物）懒解析."""
        if not act.available_if:
            return True
        expr = act.available_if_expr
        if expr is None:
            from hsr_nous.sim_schema.expression import parse
            try:
                expr = parse(act.available_if, layer="effect")
                act.available_if_expr = expr
            except Exception as e:
                self.state.log.append(
                    f"AV{self.state.clock:.1f}: ⚠ {actor_state.actor.name} 行动 {act.action_id}"
                    f" available_if 解析失败按不可用处理：{e!r}")
                return False
        ctx = {"self": _HookSelfNS(self, actor_state),
               **self._res_ns(actor_state)}
        try:
            return bool(self._expr.evaluate(
                expr, ctx, functions=self._hooks._hook_functions(actor_state)))
        except Exception as e:
            self.state.log.append(
                f"AV{self.state.clock:.1f}: ⚠ {actor_state.actor.name} 行动 {act.action_id}"
                f" available_if 求值失败按不可用处理：{e!r}")
            return False

    def _legal_with_available_if(self, actor_state: ActorState, legal: List[Action]) -> List[Action]:
        """available_if 条件闸：合法行动集只读过滤（政策/手动/web/召唤自动同一漏斗，
        时序在 _legal_with_state 形态注入之后——03_actor §3.8.1 / 14_policy 合法性契约③）."""
        return [act for act in legal if self._available_if_ok(actor_state, act)]

    def end_current_turn(self, actor_state: ActorState) -> None:
        """结束当前回合（#16）：保留已发生、丢弃未行动；先 +1 延长再正常末结算.

        净效果：已有增益时长不变，本回合新挂增益白赚 +1（"锁 buff"数学原理）。
        +1 只补 owner_turn_end 锚——回合末 B 类结算只走该锚的字；其他锚
        （owner_turn_start/on_action）本回合末本就不走字，无需补偿
        （"已有增益时长不变"对它们天然成立，+1 反而白送时长）。
        """
        for mod in actor_state.modifiers.values():
            if mod.duration > 0 and mod.tick_anchor == "owner_turn_end":
                mod.duration += 1
        self._tick_modifiers(actor_state)
        self.state.log.append(f"AV{self.state.clock:.1f}: {actor_state.actor.name} 的回合被结束")

    def _check_exit_conditions(self, actor_state: ActorState) -> None:
        """形态退出条件检查（行动后）：on_action_count / on_resource_depleted."""
        cfg = actor_state.state_config
        if cfg is None:
            return
        for cond in cfg.exit_conditions:
            trigger = cond.get("trigger")
            if trigger == "on_action_count":
                count = actor_state.resources.get(f"_state_actions_{cfg.state}", 0.0)
                if count >= float(cond.get("value", 1)):
                    self.exit_state(actor_state, "exit_condition")
                    return
            elif trigger == "on_resource_depleted":
                rid = cond.get("value", "")
                if actor_state.resources.get(rid, 0.0) <= 0.0:
                    self.exit_state(actor_state, "exit_condition")
                    return

    def _count_state_action(self, actor_state: ActorState, had_state_at_turn_start: bool) -> None:
        """形态行动计数 + 退出检查（仅本回合开始时就已在形态内的行动计入倒计时——当动变身不计）."""
        if not had_state_at_turn_start or actor_state.state_config is None:
            return
        key = f"_state_actions_{actor_state.state_config.state}"
        actor_state.resources[key] = actor_state.resources.get(key, 0.0) + 1
        self._check_exit_conditions(actor_state)

    def _pick_ally_target(self, attacker: Optional[ActorState] = None) -> Optional[ActorState]:
        """敌方选目标（mechanics 10）：覆盖层 > 加权——掷骰按 taunt_eff 加权，期望取最高（并列按编队序）.

        覆盖层：强制嘲讽（attacker 身上 forced_taunt 件 → 必打其 source，Fandom Aggro
        "ignoring Aggro and Lock On"）；锁定暂由同槽位后续接入（敌方脚本域，暂无实例）。
        """
        # enemy_targetable:false 的召唤物（Netherwing/Demiurge 族）不进敌方一切目标池（v1 口径含 AoE，
        # B19 待实测：AoE 是否豁免）；taunt:false 权重置 0（永不加权命中，强制嘲讽仍可指）
        allies = [s for s in self._allies_alive() if s.actor.summon_flags.get("enemy_targetable", True)]
        if not allies:
            return None
        if attacker is not None:
            for mod in attacker.modifiers.values():
                if mod.forced_taunt:
                    src = self.state.actors.get(mod.source_id)
                    if src is not None and any(s is src for s in allies):
                        return src
        weights = {id(s): (self.pipeline.effective_stats(s)["taunt_eff"]
                           if s.actor.summon_flags.get("taunt", True) else 0.0) for s in allies}
        if self.pipeline.mode == MODE_ROLL and self.pipeline.rng:
            total = sum(weights.values())
            roll = self.pipeline.rng.random() * total
            acc = 0.0
            for s in allies:
                acc += weights[id(s)]
                if roll <= acc:
                    return s
            return allies[-1]
        return max(allies, key=lambda s: weights[id(s)])

    def _skill_level_of(self, actor: Actor, action: Action) -> int:
        """倍率表取档等级：level_key 优先，缺省按 action_type 映射（follow_up 等归 ultimate）."""
        key = action.level_key or action.action_type
        return int(actor.skill_levels.get(key, actor.skill_levels.get("ultimate", 10)))

    def _resolve_targets(self, actor_state: ActorState, action: Action) -> tuple[Optional[ActorState], List[ActorState]]:
        """按 target_type 解析 (主目标, 目标集)（站位=编队序；blast 相邻=存活列表索引 ±1）.

        主目标选择：统一决策源 `self.decision.select_target` 优先（手动 > policy target_rules > 缺省首个存活敌人）.
        """
        actor = actor_state.actor
        tt = action.target_type
        if self._is_monster(actor):
            # 敌方视角的我方目标池：enemy_targetable:false 召唤物剔除（与 _pick_ally_target 同口径）
            allies = [s for s in self._allies_alive() if s.actor.summon_flags.get("enemy_targetable", True)]
            if tt == "aoe":
                return (allies[0] if allies else None), allies
            if tt == "bounce":
                picked = (self.pipeline.rng.choice(allies)
                          if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None and allies
                          else (allies[0] if allies else None))
                return picked, ([picked] if picked is not None else [])
            if tt == "blast":
                # 敌方扩散：主目标 ±1 相邻同受击（站位=编队序，忆灵紧邻忆师右侧也吃相邻——
                # 与我方 blast 同口径；此前漏分支静默退单体）
                t = self._pick_ally_target(actor_state)
                if t is None:
                    return None, []
                idx = allies.index(t)
                return t, allies[max(0, idx - 1): idx + 2]
            t = self._pick_ally_target(actor_state)
            return t, ([t] if t is not None else [])
        if tt == "self":
            return actor_state, [actor_state]
        if tt in ("ally_single", "ally_aoe"):
            # 我方目标池：ally_targetable:false 召唤物剔除（Demiurge 界外族——全体效果除外的
            # 反例由 hook 直选通道另行表达，选择器池按通用约定口径）
            allies = [s for s in self._allies_alive() if s.actor.summon_flags.get("ally_targetable", True)]
            if tt == "ally_aoe":
                return (allies[0] if allies else None), allies
            picked = (None if self._auto_target_ctx
                      else self.decision.select_target(actor_state, tt, allies, self))
            primary = picked if picked is not None else actor_state
            return primary, [primary]
        enemies = self._enemies_alive()
        if not enemies:
            return None, []
        if tt == "aoe":
            return enemies[0], enemies
        if tt == "bounce":
            # 弹射每段随机（roll）/ 期望模式全中主目标（与 optimizer 单体口径一致）
            picked = (self.pipeline.rng.choice(enemies)
                      if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None
                      else enemies[0])
            return picked, [picked]
        primary = self._preferred_target(actor_state, action, enemies)
        if primary is None and not self._auto_target_ctx:
            primary = self.decision.select_target(actor_state, tt, enemies, self)
        if primary is None:
            primary = enemies[0]
        if tt == "blast":
            idx = enemies.index(primary)
            return primary, enemies[max(0, idx - 1): idx + 2]
        return primary, [primary]

    def _preferred_target(self, actor_state: ActorState, action: Action,
                          enemies: List[ActorState]) -> Optional[ActorState]:
        """action.prefer_target 机制级优先目标（03_actor §3.8.1）——
        "owner_last_target"：召唤物优先召唤者最后攻击的敌人（长夜月 Evey 1141301 族）.

        无法解析（无 prefer_target / 非召唤物 / 召唤者无记录 / 记录目标已不在存活池）
        → None 回落统一决策链（手动 > policy target_rules > 缺省首个存活）。
        """
        if getattr(action, "prefer_target", "") != "owner_last_target":
            return None
        sdef = self.summon_defs.get(actor_state.actor.actor_id)
        if sdef is None:
            return None
        tid = self._last_target_by_actor.get(sdef.owner_id)
        if tid is None:
            return None
        return next((s for s in enemies if s.actor.actor_id == tid), None)

    @staticmethod
    def _apply_variant(action: Action, variant: Dict[str, Any]) -> Action:
        """段级变体覆写（B35②）：target_type/scaling/damage_type/toughness_dmg 逐段替换——
        黄泉混合段型（3 单刀+1 群攻）与飞霄逐击选招共用；未列字段沿用基础行动."""
        return replace(
            action,
            target_type=str(variant.get("target_type", action.target_type)),
            damage_type=variant.get("damage_type", action.damage_type),
            toughness_dmg=int(variant.get("toughness_dmg", action.toughness_dmg)),
            scaling=([{k: float(x) for k, x in row.items()} for row in variant["scaling"]]
                     if variant.get("scaling") is not None else action.scaling),
        )

    def _execute_action(self, actor_state: ActorState, action: Action, *, _insert: bool = False) -> None:
        actor = actor_state.actor
        primary, targets = self._resolve_targets(actor_state, action)
        if not targets:
            return
        # on_action 事件 payload 的主目标寻址（星期日/蒙福者族需要知道技能打在谁身上——
        # 各 emit 点统一读这个槽；未解析出目标时为 None，条件求值按不触发处理同口径）
        self._last_target_id = primary.actor.actor_id if primary is not None else None
        if primary is not None:
            # 逐 actor 记账（prefer_target "owner_last_target" 取数锚——忆灵优先忆师末目标族）
            self._last_target_by_actor[actor.actor_id] = primary.actor.actor_id
        # 成为技能目标（对每个目标发射；140804"成为目标获火种/队友给暴伤"族）
        for t in targets:
            self.bus.emit("on_become_target", {
                "target": t.actor.actor_id, "source": actor.actor_id,
                "action_id": action.action_id, "action_type": action.action_type,
                "insert": _insert,
            }, self.state)

        sp_before = self.state.skill_points
        self._adjust_skill_points(action.skill_point_gain - action.skill_point_cost,
                                  reason=f"action:{action.action_id}")
        # 实际耗点记账（before_consume 抵扣/clamp 后净值——sp_consumed 载荷槽取数点）
        self._last_sp_consumed = max(0, sp_before - self.state.skill_points)
        # None=按类型默认回能（rulebook energy 节查表，mechanics 05 §5.1）；显式 0=该技能不回能（如形态内强化普攻）
        gain = action.energy_gain if action.energy_gain is not None else (
            self.pipeline.energy_gain_default(action.action_type)
        )
        if gain:
            # 行动级结算一次（整动作一回，非逐段——mechanics 05 §5.1 现状语义）
            self._grant_energy(actor_state, gain, source=actor.actor_id,
                               action_id=action.action_id, reason=action.action_type)
        self._apply_action_side_effects(actor_state, action)

        # 净化自身所有可驱散负面（140811"解除自身所有负面效果"族）
        if action.cleanse_self:
            for mid in [m.modifier_id for m in actor_state.modifiers.values()
                        if m.modifier_type == "debuff" and m.dispellable]:
                self._remove_modifier(actor_state, mid, "cleanse")

        if action.damage_type and action.scaling:
            # 段数：静态 instances，或资源驱动（instances_from_resource × per_point，消耗前读）
            instances = max(1, action.instances)
            if action.instances_from_resource:
                n = actor_state.resources.get(action.instances_from_resource, 0.0)
                instances = max(1, int(n * action.instances_per_point))
                if action.instances_cap > 0:
                    instances = min(instances, action.instances_cap)
            if action.consume_all_resource:
                rid = action.consume_all_resource
                # 消耗同样可观察（统一入口发负值事件——"消耗≥N 触发额外"族（140811）的挂钩点；
                # 耗尽联动 provenance 清空由入口口径保证）
                self._gain_resource(actor_state, rid, -actor_state.resources.get(rid, 0.0))
            # 多段（#19 instances）：SP/能量行动级结算一次，伤害/削韧逐段；段间目标死亡则后续段落空（鞭尸损失）
            # 整段结算 = 一次伤害事件：多目标/多段同时致死共享全队仅 1 次的月茧机会（owner 实战确认 2026-08-22）
            with self._damage_event():
                for seg in range(instances):
                    seg_action = action
                    if action.instance_variants:
                        if action.segment_choice:
                            # 逐击选招（飞霄族）：缺省恒取变体 0（确定性口径；首段=变体 0——
                            # ult 按下即首段，选招决策自第 2 段起）——不按段序对齐
                            if action.instance_variants[0] is not None:
                                seg_action = self._apply_variant(action, action.instance_variants[0])
                        elif (seg < len(action.instance_variants)
                                and action.instance_variants[seg] is not None):
                            # index 对齐变体（黄泉混合段型族）：逐段覆写
                            seg_action = self._apply_variant(action, action.instance_variants[seg])
                    if (seg > 0 and not self._is_monster(actor)
                            and not self._enemies_alive() and self._has_next_wave()):
                        # 续段执行（B9）：段间全灭且有下波——转波续段（黄泉族砍穿波次；
                        # 复用现有波次推进重解析目标，不立检查点/可恢复模型）
                        self._advance_wave_if_needed()
                        primary, targets = self._resolve_targets(actor_state, seg_action)
                        if not targets:
                            break
                    if seg > 0 and (action.segment_confirm or action.segment_choice):
                        # 段间决策（B35①确认 / B35②选招+换目标）：脚本/编译直通（缺省 = index
                        # 对齐变体 + 保持当前目标）；手动挂起等回答；回答入决策簿（B35② 起）
                        pick = self.decision.wait_segment(actor_state, seg_action, seg, self)
                        if pick:
                            v_idx, t_id = pick
                            if (v_idx is not None and action.instance_variants
                                    and 0 <= v_idx < len(action.instance_variants)
                                    and action.instance_variants[v_idx] is not None):
                                seg_action = self._apply_variant(action, action.instance_variants[v_idx])
                            if t_id is not None:
                                hit = self.state.actors.get(str(t_id))
                                if hit is not None and hit.alive:
                                    primary = hit
                                    if seg_action.target_type == "blast":
                                        pool = self._enemies_alive()
                                        if primary in pool:
                                            idx = pool.index(primary)
                                            targets = pool[max(0, idx - 1): idx + 2]
                                        else:
                                            targets = [primary]
                                    else:
                                        targets = [primary]
                    if seg > 0 and seg_action.target_type == "bounce":
                        # 弹射每段独立重选目标（可重复命中；全灭即终止）
                        primary, targets = self._resolve_targets(actor_state, seg_action)
                        if not targets:
                            break
                    elif seg_action.target_type != action.target_type:
                        # 段级变体改了作用范围（单体↔群攻等）：目标集按变体重解析
                        # （v1 不重发 on_become_target——段间补目标的事件口径归 B19 待实测）
                        primary, targets = self._resolve_targets(actor_state, seg_action)
                        if not targets:
                            break
                    for target in targets:
                        if not target.alive:
                            continue
                        eff = seg_action
                        if seg_action.target_type == "blast" and target is not primary:
                            # 扩散副目标：副倍率 + 副削韧（None 时副削韧 = 主 × rulebook
                            # blast_toughness_ratio（默认 0.5，04_break_system 基线 10/20/10））
                            eff = replace(
                                seg_action,
                                scaling=seg_action.scaling_blast if seg_action.scaling_blast is not None else seg_action.scaling,
                                toughness_dmg=seg_action.toughness_dmg_blast
                                if seg_action.toughness_dmg_blast is not None
                                else seg_action.toughness_dmg * self.pipeline.blast_toughness_ratio(),
                            )
                        if seg_action.split == "even":
                            # 分配轴：总伤按存活目标数均分，逐目标各自跑公式（05_effects §split）
                            alive_n = max(1, sum(1 for t in targets if t.alive))
                            eff = replace(
                                eff,
                                scaling=[{k: v / alive_n for k, v in s.items()} for s in eff.scaling],
                            )
                        if any("elation" in s for s in eff.scaling):
                            # 欢愉技段（B40 P2a——纯倍率×等级系数路由；punchline_source=
                            # 阿哈笑点池实时值，21_elation §21.2 定槽；blast/split 的
                            # scaling 变体已在上游折算，行键 elation 随变体同替；
                            # 额外阿哈时刻经 _aha_pool_override 锚定固定值——B40 P2b）
                            result = self.pipeline.elation_damage(
                                actor_state, target,
                                ability_multiplier=self.pipeline._elation_ability_multi(
                                    eff, self._skill_level_of(actor, eff)),
                                punchline_source=float(
                                    self._aha_pool_override
                                    if self._aha_pool_override is not None
                                    else self.state.punchline),
                                damage_type=str(eff.damage_type or "physical"),
                                action_type=eff.action_type)
                        else:
                            result = self.pipeline.deal_damage(
                                eff, actor_state, target, target_broken=target.broken,
                                skill_level=self._skill_level_of(actor, eff))
                        was_broken = target.broken   # 超击破快照（B38）：破的那一击本身不触发
                        # 伤害入口 waterfall（before_take_damage）：免死 cancel / 分摊·减伤改写 amount 的总入口
                        wp = self.bus.waterfall("before_take_damage", {
                            "amount": result.value, "damage_type": eff.damage_type,
                            "source": actor.actor_id, "target": target.actor.actor_id,
                            "action_type": eff.action_type, "is_critical": result.node.get("isCrit", False),
                        }, self.state)
                        if wp.get("cancel"):
                            continue  # 伤害被取消（免死类 hook 侧已自理回血/反击）
                        final_amount = float(wp.get("amount", result.value))
                        # 护盾吸收层：乘区结算后、扣 HP 前（并行吸收，本体只承溢出；真伤同走本层）
                        overflow = self._absorb_with_shields(target, final_amount, actor.actor_id)
                        target.current_hp -= overflow
                        if overflow > 0:
                            # HP 下降发射点（mechanics 11 §11.3：受击是 HP 降低来源之一）
                            # reason 词表：spec 仅钉 drain_hp 的 'drain'（05_effects §生命汲取/生命流失），
                            # 其余按扣血路径名冻结（hit/dot/break/set_hp）——spec 未写，勿扩
                            # damage_type 仅 'hit' 族携带（昔涟结界真伤防递归闸——"非真伤才触发"过滤）；
                            # action_type 同族携带（"指定技能造成的伤害"族过滤——遐蝶 E1 四技限定）
                            self.bus.emit("on_hp_decrease", {
                                "amount": overflow, "source": actor.actor_id,
                                "reason": "hit", "target": target.actor.actor_id,
                                "damage_type": eff.damage_type or "",
                                "action_type": eff.action_type,
                                "is_critical": result.node.get("isCrit", False)}, self.state)
                        self.state.total_damage += final_amount
                        self.state.damage_by_actor[actor.actor_id] += final_amount
                        self._log(actor, eff, target, final_amount, result.node.get("isCrit", False))
                        if self._is_monster(target.actor):
                            self._apply_toughness_damage(actor, eff, target)
                            self._try_super_break(actor_state, eff, target, was_broken=was_broken)
                        self._check_death(target, actor.actor_id, action_id=str(eff.action_id or ""))
                        # 受击回能（mechanics 05 §5.1：per-attack 归属、吃 ERR、打盾照回、多段逐段）
                        if target.alive and eff.energy_grant > 0:
                            self._grant_hit_energy(actor, eff, target)
                        # after_being_hit 是受击链收尾事件：钩子上读到盾吸收/锁血/复活/回能后的终态
                        # （actor_type/action_type/hit_targets 供"我方攻击后…"族过滤——缇宝境界/残梅绽挂标）
                        self._emit_after_being_hit(
                            amount=final_amount, absorbed=final_amount - overflow,
                            damage_type=eff.damage_type, source_id=actor.actor_id,
                            target_id=target.actor.actor_id,
                            is_critical=result.node.get("isCrit", False), seg_index=seg,
                            actor_type=actor.actor_type, action_type=eff.action_type,
                            hit_targets=[t3.actor.actor_id for t3 in targets])
        else:
            # 无伤害行动（self buff/铺场类）也留行动日志——可观察性是机制对轴的前提
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {actor.name} 使用 {action.name}"
            )
        # 计时锚"每次行动"（行动次数型 buff 族；插入行动不算"一次行动"（待实测 B19 候选），v1 仅回合内主动行动 tick）
        if not _insert:
            self._tick_modifiers(actor_state, "on_action")

    def _apply_action_side_effects(self, actor_state: ActorState, action: Action) -> None:
        """行动的副作用通道（resource_gain / act_now / apply_modifiers）——
        普通施放与变身 entry 特判共用（entry 不经 _execute_action 的伤害段）."""
        # 自定义资源获得（火种/毁伤/新蕊族；统一入口——max 截断/bank 溢出/provenance）
        for rid, amt in action.resource_gain.items():
            self._gain_resource(actor_state, rid, amt, source_id=actor_state.actor.actor_id)
        # 立即行动（白厄 140809"使敌方全体立即行动"族）
        if action.act_now_targets == "all_enemies":
            for e in self._enemies_alive():
                self.scheduler.act_now(e.actor)
        # 施放后挂 modifier（dict 声明→物化；target: self（默认）/ all_enemies（植入 debuff 族）；
        # F2 来源记账：kind=action、ref=action_id——C 面板来源「战技『…』」与就地展开的取数锚）
        for spec in action.apply_modifiers:
            tgt = [actor_state] if spec.get("target", "self") == "self" else self._enemies_alive()
            for t in tgt:
                self._apply_modifier_spec(t, spec, actor_state,
                                          source_kind="action", source_ref=action.action_id)

    # ------------------------------------------------------------------
    # modifier 物化 + 护盾——运行时已迁 sim/modifiers.py（ModifierBook）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    @staticmethod
    def _modifier_from_spec(spec: Dict[str, Any]) -> Modifier:
        return ModifierBook._modifier_from_spec(spec)

    def _apply_modifier_spec(self, target: ActorState, spec: Dict[str, Any],
                             source: Optional[ActorState], *,
                             source_kind: str = "", source_ref: str = "") -> bool:
        return self._modifiers._apply_modifier_spec(
            target, spec, source, source_kind=source_kind, source_ref=source_ref)

    def _attach_shield(self, target: ActorState, mod: Modifier, shield_spec: Dict[str, Any],
                       source: Optional[ActorState]) -> None:
        self._modifiers._attach_shield(target, mod, shield_spec, source)

    def _absorb_with_shields(self, target: ActorState, amount: float, source_id: str = "") -> float:
        return self._modifiers._absorb_with_shields(target, amount, source_id)

    # ------------------------------------------------------------------
    # 模板 hooks（机制自包含 DSL）——运行时已迁 sim/hooks.py（HookRuntime）；
    # 以下同名方法为薄委托（tests 直调口径不变），转发不包逻辑
    # ------------------------------------------------------------------

    def _subscribe_compiled_hooks(self) -> None:
        self._hooks._subscribe_compiled_hooks()

    def _hook_ctx(self, st: ActorState, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._hooks._hook_ctx(st, payload)

    def _hook_target_states(self, sel: Any, st: ActorState, payload: Dict[str, Any]) -> List[ActorState]:
        return self._hooks._hook_target_states(sel, st, payload)

    def _run_hook_effect(self, st: ActorState, eff: Dict[str, Any], payload: Dict[str, Any],
                         updates: Optional[Dict[str, Any]] = None) -> None:
        self._hooks._run_hook_effect(st, eff, payload, updates)

    def _ult_action_of(self, st: ActorState) -> Optional[Action]:
        """当前形态下可用的终结技行动（replaces/locked 合法性注入，与 _legal_with_state 同口径）.

        形态锁 ultimate → None；形态替换 ultimate（昔涟涟漪 141503→141514 族）→ 替换件；
        非形态下增强件（replaces 值）不可用——原 _ready_ultimates 直取首个 ultimate 行动，
        双终结技声明（原+替换件）时形态内仍命中原型，本方法为唯一形态感知解析点。
        """
        cfg = st.state_config
        if cfg is not None and "ultimate" in cfg.locked_actions:
            return None
        cands = [a for a in self.actions_by_actor.get(st.actor.actor_id, [])
                 if a.action_type == "ultimate"]
        if cfg is not None and "ultimate" in cfg.replaces_actions:
            rep = cfg.replaces_actions["ultimate"]
            rep_ids = set(rep) if isinstance(rep, (list, tuple)) else {rep}
            cands = [a for a in cands if a.action_id in rep_ids]
        else:
            enhanced: set = set()
            for c in self.state_configs_by_actor.get(st.actor.actor_id, []):
                enhanced |= self._replaced_ids(c.replaces_actions)
            cands = [a for a in cands if a.action_id not in enhanced]
        return cands[0] if cands else None

    def _ready_ultimates(self) -> List[tuple]:
        """当前窗口可放终结技的清单 [(ActorState, ult Action)]（ultimate_available 能量/充能门槛
        + available_if 条件闸双件——03_actor §3.8.1：终结技同吃行动级可用条件）.

        扫全场存活单位（含敌人——旧内联逻辑对任何持 ultimate 行动的单位都放行；
        实际敌人能量恒 0/无 ult 行动，恒不 ready）。编队序即清单序。
        """
        ready: List[tuple] = []
        for st in self.state.actors.values():
            if not st.alive or st.banished:
                continue   # 放逐=离场无法行动（05_effects 放逐三语义）——终结技同样禁放
            ult = self._ult_action_of(st)
            if ultimate_available(st, ult) and self._available_if_ok(st, ult):
                ready.append((st, ult))
            # manual_trigger 忆灵技（如露 1141307 族——游戏：条件满足时玩家窗口手动点放）：
            # 与终结技同窗口同 ready 清单，available_if 过闸即可点（不耗能量，非终结技语义）
            for a in self.actions_by_actor.get(st.actor.actor_id, []):
                if a.manual_trigger and self._available_if_ok(st, a):
                    ready.append((st, a))
        return ready

    def _fire_manual_trigger(self, caster: ActorState, action: Action) -> bool:
        """manual_trigger 行动执行体（长夜月忆灵「如露」1141307 族——游戏：条件满足时
        玩家手动点放+手选目标）：不耗能量/充能、不入形态机、**不发 on_ultimate**（非终结技，
        误发会带偏 on_ultimate hook 族）；行动结算与 on_action 广播同 _execute_action 口径。
        """
        self._execute_action(caster, action)
        self.bus.emit("on_action", {"actor": caster.actor.actor_id,
                                     "action_type": action.action_type,
                                     "action_id": action.action_id,
                                     "target_type": action.target_type,
                                     "target": self._last_target_id,
                                     "sp_consumed": self._last_sp_consumed,
                                     "actor_type": caster.actor.actor_type}, self.state)
        return True

    def _activate_ultimate(self, st: ActorState) -> bool:
        """activate_ultimate 原语执行体：目标终结技立即作为插入行动发动、不耗充能（昔涟族）.

        v1 口径（B19 待实测在案）：无视能量/特殊充能门槛直接发动、不扣量（是否白嫖待实测）；
        插入行动语义（不吃正常回合、不耗行动）；形态锁/无终结技/死亡/放逐目标跳过。
        """
        if not st.alive or st.banished:
            return False
        ult = self._ult_action_of(st)
        if ult is None:
            return False
        return self._fire_ultimate(st, ult, free=True)

    def _try_ultimate(self, actor_state: ActorState, timing: str) -> bool:
        if self.decision.ult_timing != timing:
            return False
        fired = False
        # 窗口连放（游戏同款）：放一个 → 重查 ready → 再问，直到决策不放/无人就绪——
        # 多人同窗口连大、星期日充能大充满队友接着放都靠这个环；16 上限 = 回能 hook 自供能保险丝
        for _ in range(16):
            ready = self._ready_ultimates()
            if not ready:
                break
            # 统一决策接口第三件：窗口 ready 清单上交决策源（None=本窗口不放；
            # 手动实现可跨单位选——施放者不一定是行动方，按回答反查 caster）
            ult = self.decision.select_ultimate(actor_state, ready, self)
            caster = next((st for st, a in ready if a is ult), None) if ult is not None else None
            if caster is None:
                break  # 本窗口不放 / ready 之外的回答（越权不收——policy 只选不越权）
            ult = next(a for st, a in ready if st is caster)
            fired_ok = (self._fire_manual_trigger(caster, ult) if ult.manual_trigger
                        else self._fire_ultimate(caster, ult))
            if not fired_ok:
                break  # 变身重复触发被拒——同回答再来是死循环，断
            fired = True
        else:
            self.state.log.append("⚠ 终结技窗口连放撞上限 16（回能 hook 自供能？）")
        return fired

    def _fire_ultimate(self, caster: ActorState, ult: Action, *, free: bool = False) -> bool:
        """终结技执行体（成本/变身/施放/广播）：_try_ultimate 窗口与手动插队
        （web 决策点 ult_now，游戏同款"随时可大"）共用同一漏斗.

        free=True（activate_ultimate 原语族）：跳过充能消耗（能量与特殊充能资源同免——
        v1 口径，是否白嫖待实测 B19），其余路径（变身/施放/广播）同口径。

        广播双发（B37 方案 A）：施放成功 = on_action（一切能力施放口径，官方
        "uses an ability" 含终结技）+ on_ultimate（终结技专属子集），序先前者后后者；
        变身重复触发被拒（return False）两事件都不发。
        """
        entry = self.state_entry_actions.get(ult.action_id)
        if entry is not None and caster.state_config is entry[1]:
            return False  # 已在该形态：变身技不重复触发（防能量回充连锁变身）
        cost = ult_threshold_of(ult, caster.actor.stats.max_energy)  # 开大能耗 = 阈值全扣
        # 形态入口技：施放即变身（进入形态 + 结束本回合 + 授予倒计时回合）
        if not free:
            if ult.ult_cost_resource:
                # 特殊充能：扣资源不扣能量（白厄火种/遐蝶新蕊族；统一入口——消耗 floor 0 与
                # provenance 耗尽清空由入口口径保证）；实际扣量 = ult_consume_amount
                # 显式声明值（昔涟 141503 门槛 24 扣 12 族），缺省 = 阈值全扣
                consume = ult.ult_consume_amount if ult.ult_consume_amount > 0 else ult.ult_cost_amount
                self._gain_resource(caster, ult.ult_cost_resource, -consume)
            else:
                self.pipeline.consume_energy(caster, cost)
        if entry is not None:
            _owner, config = entry
            self.enter_state(caster, config)
            self._apply_action_side_effects(caster, ult)  # 入口技副作用（资源获得/挂身件）
            if config.entry_end_turn:
                self.end_current_turn(caster)
                # 官方原文"结束本回合"：行动阶段整体跳过（无论谁的回合——ult_now 插队/
                # 窗口 before 两路同口径；after 路行动已发生，置位无影响）
                self._turn_consumed = True
            if config.exit_conditions:
                # 倒计时回合按固定速度占 AV 流逝（countdown_spd_ratio 模板声明）；
                # 初始行动值规则同属模板声明（countdown_initial_ratio）——数值=固定比例，
                # "uniform"=均匀随机（官方 tooltip"平均设置在 0~100% 之间"，owner 拍板均匀分布：
                # roll 按种子抽、expected 取期望 0.5），engine 只执行声明、不私有规则。
                # 永续形态（无退出条件——昔涟涟漪族）不授予倒计时回合（倒计时为退出计数服务）
                n_turns = int(config.exit_conditions[0].get("value", 1))
                init = config.countdown_initial_ratio
                if init == "uniform":
                    ratio = (self.pipeline.rng.random()
                             if self.pipeline.mode == MODE_ROLL and self.pipeline.rng is not None else 0.5)
                else:
                    ratio = float(init)
                self.scheduler.grant_countdown(
                    caster.actor.actor_id, n_turns,
                    spd=caster.actor.stats.spd * config.countdown_spd_ratio,
                    initial_ratio=ratio,
                )
        else:
            self._execute_action(caster, ult)
        # B37 方案 A：终结技施放成功也发 on_action（官方 "uses an ability" 三层措辞在案——
        # on_action = 一切能力施放；入口变身技与常态技同口径，activate_ultimate 免费激活
        # 同经此漏斗同发）。形状对齐常态行动；序 = 先 on_action 后 on_ultimate
        self.bus.emit("on_action", {"actor": caster.actor.actor_id,
                                     "action_type": ult.action_type,
                                     "action_id": ult.action_id,
                                     "target_type": ult.target_type,
                                     "target": self._last_target_id,
                                     "sp_consumed": self._last_sp_consumed,
                                     "actor_type": caster.actor.actor_type}, self.state)
        self.bus.emit("on_ultimate", {"source": caster.actor.actor_id, "action": ult.action_id,
                                      "target": self._last_target_id}, self.state)
        return True

    def _grant_energy(self, recipient: ActorState, amount: float, *, source: str,
                      action_id: Optional[str], reason: str, err_exempt: bool = False) -> float:
        """能量获得统一入口（§23.4 对账表：一切获得路径的发射点）.

        on_gain_energy waterfall（before_gain 模式，获得量可改写/可取消）→ pipeline.gain_energy。
        行动回能（_execute_action）/ 受击回能（_grant_hit_energy）/ hook 原语 gain_energy
        （含秘技装填预置）都经此；初始能量布场不是事件，不在此列。返回实际获得量。
        忆灵与忆师共享能量池（mechanics 01 §能量恢复/05 §5.1）：**任何路径**指向忆灵的
        能量获得在此重定向忆师（行动/受击/hook/秘技全覆盖，非逐调用点路由）。
        """
        if recipient.actor.actor_type == "summon" and recipient.actor.summoner_id:
            recipient = self.state.actors.get(recipient.actor.summoner_id) or recipient
        wp = self.bus.waterfall("on_gain_energy", {
            "actor": recipient.actor.actor_id, "amount": amount, "source": source,
            "action_id": action_id, "reason": reason, "err_exempt": err_exempt,
        }, self.state)
        if wp.get("cancel"):
            return 0.0
        final = float(wp.get("amount", amount))
        if final <= 0:
            return 0.0
        res = self.pipeline.gain_energy(recipient, final, err_exempt=err_exempt)
        return float(res.node.get("actualAmount", 0.0))

    def _grant_hit_energy(self, source: Actor, action: Action, target: ActorState) -> None:
        """受击回能：受击方获得 = 攻击 energy_grant × 受击方 ERR（忆灵受击归忆师）.

        规则（mechanics 05 §5.1/§5.3）：per-attack 归属（攻击自带档位 5/10/15/20/25）；
        吃受击方 ERR（不在具名豁免清单）；护盾挡住照回（owner 实战确认）；多段按段拆分；
        忆灵受击归忆师——忆师+忆灵同被多目标命中时两次都归忆师。
        发射点：on_gain_energy waterfall（before_gain 模式，获得量可改写）。
        """
        recipient = target
        if target.actor.actor_type == "summon" and target.actor.summoner_id:
            recipient = self.state.actors.get(target.actor.summoner_id) or recipient
        if not recipient.alive or self._is_monster(recipient.actor):
            return
        actual = self._grant_energy(
            recipient, action.energy_grant, source=source.actor_id,
            action_id=action.action_id, reason="being_hit")
        if actual > 0:
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {recipient.actor.name} 受击回能 +{actual:.1f}")

    def _log(self, actor: Actor, action: Action, target: ActorState, damage: float, is_crit: bool) -> None:
        crit_mark = "（暴击）" if is_crit else ""
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor.name} 对 {target.actor.name} "
            f"使用 {action.name} 造成 {damage:,.0f} 伤害{crit_mark}"
        )

    # ------------------------------------------------------------------
    # 敌方回合
    # ------------------------------------------------------------------

    def _enemy_turn(self, actor_state: ActorState) -> None:
        actor = actor_state.actor
        frozen = any(m.control_kind == "freeze" for m in actor_state.modifiers.values())

        # 冻结：真正跳过一次行动（不恢复韧性；解冻后下次行动提前——比例读 rulebook constants.freeze_advance，mechanics 03 §3.5）
        if frozen:
            for mod_id in [m.modifier_id for m in actor_state.modifiers.values() if m.control_kind == "freeze"]:
                self._remove_modifier(actor_state, mod_id, "expire")
            assert self.scheduler is not None
            self.scheduler.advance_action(actor, self.pipeline.freeze_advance())
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 被冻结，跳过行动")
            return

        # 敌方回合开始：恢复全部韧性、解除击破状态
        # toughness_recovered waterfall（残梅绽族：cancel = 阻止本次恢复、保持击破、
        # 该次行动被消耗——mechanics 04"冻结/残梅绽真跳过"分流）
        if actor_state.broken:
            wp = self.bus.waterfall("toughness_recovered", {
                "target": actor.actor_id, "amount": actor.stats.max_toughness,
            }, self.state)
            if wp.get("cancel"):
                # 恢复被阻止：击破态维持、本次不行动。回合弹出时已无条件重置剩余距离
                # （scheduler.next_actor），本次未行动不该白赚整条约——撤回重置，
                # 只留 hook 推条（残梅绽延后 = BE×20%+10%）后的余量
                assert self.scheduler is not None
                self.scheduler.undo_gauge_reset(actor)
                self.state.log.append(
                    f"AV{self.state.clock:.1f}: [敌] {actor.name} 韧性恢复被阻止，击破状态延长")
                return
            actor_state.broken = False
            actor_state.bar_index = 0   # 韧性恢复回主条（多韧性条 §3.10：追加条随下次主条破再循环）
            actor_state.toughness = float(wp.get("amount", actor.stats.max_toughness))
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 韧性恢复")

        actions = self.actions_by_actor.get(actor.actor_id, [])
        if not actions:
            self.state.log.append(f"AV{self.state.clock:.1f}: [敌] {actor.name} 行动（占位）")
            return
        self._execute_action(actor_state, actions[0])
        self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": actions[0].action_type,
                                     "action_id": actions[0].action_id,
                                     "target_type": actions[0].target_type,
                                     "target": self._last_target_id,
                                     "sp_consumed": self._last_sp_consumed,
                                     "actor_type": actor.actor_type}, self.state)

    def trigger_action(self, actor_state: ActorState, action: Action, *, tag: str = "insert",
                       pool_override: Optional[float] = None) -> None:
        """插入式行动（反击/追加攻击/代放族）：立即结算，不占回合、不调度、不改计数.

        与回合内行动的区别：不走 legal/政策、不影响形态计数器；事件带 insert 标记
        （hook 监听时可区分主动行动与插入行动，防"反击触发反击"无限递归）。
        自动施放=自动目标（万敌血仇战技"automatically used"族同通道）：玩家没点放的
        行动不问玩家目标——挂 _auto_target_ctx 旗标（嵌套计数安全）。
        pool_override：欢愉代放族固定笑点档（21_elation.md §21.2——欢愉主终结技
        「固定计入 20 笑点」结算口径/额外阿哈时刻同族；嵌套安全：进出存复旧值）。
        """
        self.state.log.append(
            f"AV{self.state.clock:.1f}: {actor_state.actor.name} 插入发动 {action.name}"
        )
        self._auto_target_ctx += 1
        old_override = self._aha_pool_override
        if pool_override is not None:
            self._aha_pool_override = float(pool_override)
        try:
            self._execute_action(actor_state, action, _insert=True)
            self.bus.emit("on_action", {
                "actor": actor_state.actor.actor_id, "action_type": action.action_type,
                "action_id": action.action_id, "target_type": action.target_type,
                "target": self._last_target_id,
                "sp_consumed": self._last_sp_consumed,
                "insert": True, "tag": tag, "actor_type": actor_state.actor.actor_type,
            }, self.state)
        finally:
            # 恢复在 emit 之后——覆写锚罩整个代放含其 on_action 段钩（凡读池处同锚：
            # 行动层与 hook 段一致结算，欢愉主终结技固定 20 族实证）
            self._aha_pool_override = old_override
            self._auto_target_ctx -= 1

    def fire_assist(self, actor_state: ActorState, action: Action) -> bool:
        """助战技发动（assist 族）：额度闸 → 消耗 1 → 插入执行（不占本人回合、不调度、
        不改计数——与追加攻击同 trigger_action 口径）.

        额度 = `assist_cost_resource` 指向的自定义资源（>0 才可发动，次数=资源）；
        空 = 无额度闸（无限次）。返回 False = 额度不足未发动；非 assist 行动大声炸。
        触发面（手动按钮/策略助战窗口）待实例角色——v1 为引擎结算原语。
        """
        if action.action_type != "assist":
            raise ValueError(
                f"fire_assist 收到非 assist 行动 {action.action_id!r}"
                f"（action_type={action.action_type!r}）")
        rid = action.assist_cost_resource
        if rid and actor_state.resources.get(rid, 0.0) < 1.0:
            self.state.log.append(
                f"AV{self.state.clock:.1f}: {actor_state.actor.name} 助战技 {action.name}"
                f" 额度不足，未发动")
            return False
        if rid:
            self._gain_resource(actor_state, rid, -1.0)
        self.trigger_action(actor_state, action, tag="assist")
        return True

    def _final_action_if_last(self, actor_state: ActorState, is_countdown: bool) -> Optional[Action]:
        """倒计时最后一动返回 final_action_id 指定的行动，否则 None."""
        cfg = actor_state.state_config
        if not is_countdown or cfg is None or not cfg.final_action_id:
            return None
        n = float(cfg.exit_conditions[0].get("value", 1)) if cfg.exit_conditions else 1.0
        count = actor_state.resources.get(f"_state_actions_{cfg.state}", 0.0)
        if count < n - 1:
            return None
        return next(
            (a for a in self.actions_by_actor.get(actor_state.actor.actor_id, [])
             if a.action_id == cfg.final_action_id),
            None,
        )

    # ------------------------------------------------------------------
    # 回合四段
    # ------------------------------------------------------------------

    def _run_turn(self, actor_state: ActorState, kind: str) -> None:
        actor = actor_state.actor
        is_countdown = kind == EXTRA_COUNTDOWN

        # 阶段 1 · 回合开始（A 类结算：DOT 跳伤；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_start", {"actor": actor.actor_id}, self.state)
        self._tick_modifiers(actor_state, "owner_turn_start")  # 计时锚"回合开始"（阮梅弦外音族）
        self._tick_source_modifiers(actor, "source_turn_start")  # 施加者回合开始锚（长夜月忆灵光环族）
        self._tick_dots(actor_state)
        # 回合开始结算致死（DOT/月茧到期）：死亡单位不进入行动阶段（与主循环的 dead-skip 同口径）
        if not actor_state.alive:
            return

        # 阶段 2 · 行动（快照回合开始时的形态：本回合内才变身的，当动不计入倒计时）
        had_state_at_turn_start = actor_state.state_config is not None
        self._turn_consumed = False   # 回合级置位复位（入口技"结束本回合"见 _fire_ultimate）
        if self._is_monster(actor):
            self._enemy_turn(actor_state)
            # 敌方行动后窗口（游戏同款"敌方行动完也能按大"——被击攒满即弹窗/随时插大；
            # 手动钩 ready 空直通不弹；auto/脚本决策只放行动方自己的大（敌人无）→ 基线零影响）
            self._try_ultimate(actor_state, ULT_AFTER_ACTION)
        elif actor.actor_type == "summon":
            self._summon_turn(actor_state)
        else:
            self._try_ultimate(actor_state, ULT_BEFORE_ACTION)
            if self._turn_consumed:
                pass   # before 窗口放变身 = 本回合行动阶段结束（官方"结束本回合"）
            else:
                forced = self._final_action_if_last(actor_state, is_countdown)
                if forced is not None:
                    # 倒计时最后一动：强制最后一击（"最后的额外回合开始时立即发动"）
                    self._execute_action(actor_state, forced)
                    self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": forced.action_type,
                                             "action_id": forced.action_id,
                                             "target_type": forced.target_type,
                                             "target": self._last_target_id,
                                             "sp_consumed": self._last_sp_consumed,
                                             "actor_type": actor.actor_type}, self.state)
                    self._count_state_action(actor_state, had_state_at_turn_start)
                else:
                    legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []), self.state.skill_points)
                    legal = self._legal_with_state(actor_state, legal)
                    legal = self._legal_with_available_if(actor_state, legal)
                    if not legal:
                        # 全部行动被锁=空过：无可执行行动，但回合末结算照走（不 return——
                        # 否则 modifier 不 tick / on_turn_end 不发 / turn_count 不增，回合静默蒸发）
                        self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                    else:
                        action = self.decision.select_action(actor_state, legal, self)
                        if self._turn_consumed:
                            pass   # 决策点内放变身（ult_now 入口技）= 本回合行动已被消耗
                        else:
                            self._execute_action(actor_state, action)
                            self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": action.action_type,
                                                 "action_id": action.action_id,
                                                 "target_type": action.target_type,
                                                 "target": self._last_target_id,
                                                 "sp_consumed": self._last_sp_consumed,
                                                 "actor_type": actor.actor_type}, self.state)
                            # 阶段 3 · 行动后窗口
                            self._try_ultimate(actor_state, ULT_AFTER_ACTION)
                            self._count_state_action(actor_state, had_state_at_turn_start)

        # 阶段 4 · 回合结束（B 类结算：modifier tick；倒计时类不广播）
        if not is_countdown:
            self.bus.emit("on_turn_end", {"actor": actor.actor_id}, self.state)
        self._tick_modifiers(actor_state)
        self._tick_source_modifiers(actor)  # source_turn_end 锚（§4.14 tick_on：按施加者回合走字）
        self.state.turn_count += 1

    def _summon_turn(self, actor_state: ActorState) -> None:
        """召唤物行动（12_summon §12.6 控制模型）.

        control="auto"（缺省，多数忆灵——游戏实况）：回合全自动——行动取首个合法
        非 manual_trigger，目标也自动（_auto_target_ctx 旗标，决策源不问，手动模式
        也不弹）；manual_trigger 行动永不在此放（玩家窗口点放）。
        control="manual"（死龙族）：行动+目标走统一决策源（与角色同流）。
        无终结技窗口；回合开始/结束的事件与 modifier tick 由 _run_turn 外圈统一处理。
        """
        actor = actor_state.actor
        legal = legal_action_set(actor_state, self.actions_by_actor.get(actor.actor_id, []),
                                 self.state.skill_points)
        legal = self._legal_with_available_if(actor_state, legal)
        sdef = self.summon_defs.get(actor.actor_id)
        if sdef is not None and sdef.control == "manual":
            if not legal:
                self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                return
            action = self.decision.select_action(actor_state, legal, self)
        else:
            legal = [a for a in legal if not a.manual_trigger]
            if not legal:
                self.state.log.append(f"AV{self.state.clock:.1f}: {actor.name} 无可用行动")
                return
            action = legal[0]
        if sdef is None or sdef.control != "manual":
            self._auto_target_ctx += 1     # 自动回合目标免问（嵌套 trigger 同免）
        try:
            self._execute_action(actor_state, action)
        finally:
            if sdef is None or sdef.control != "manual":
                self._auto_target_ctx -= 1
        self.bus.emit("on_action", {"actor": actor.actor_id, "action_type": action.action_type,
                                     "action_id": action.action_id,
                                     "target_type": action.target_type,
                                     "target": self._last_target_id,
                                     "sp_consumed": self._last_sp_consumed,
                                     "actor_type": actor.actor_type}, self.state)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def step(self) -> Optional[Dict[str, Any]]:
        """单步推进一个调度回合（增量驱动入口：调试控制器/网页端用；`run()` 就是它的循环）.

        返回本步记录 `{"actor_id", "kind", "clock", "skipped"}`；战斗结束（终止条件 /
        fixed_av 截断）返回 None。`skipped=True` 表示该单位已死亡、回合被跳过（行为与
        run() 旧循环的 dead-skip 分支同口径）。
        """
        if self.scheduler is None:
            self._init_state()
        assert self.scheduler is not None

        self._advance_wave_if_needed()
        if self._should_terminate():
            self._emit_battle_end(self._termination_reason())
            return None
        actor, kind, now = self.scheduler.next_actor()
        # 正常类额外回合发射 on_extra_turn（倒计时类按文档口径不发射，03_actor §3.11）
        if kind == EXTRA_NORMAL:
            self.bus.emit("on_extra_turn", {"actor": actor.actor_id}, self.state)
        # fixed_av 截断看"本回合时刻"：超过上限的回合不执行（含端点：恰好在上限的回合照跑）
        term = self.encounter.termination
        if (term.mode == "fixed_av" and now > term.max_action_value
                and not self._has_next_wave()):
            self._emit_battle_end("max_action_value_reached")
            return None
        self.state.clock = now
        self._tick_cycle()
        actor_state = self.state.actors[actor.actor_id]
        if not actor_state.alive:
            return {"actor_id": actor.actor_id, "kind": kind, "clock": now, "skipped": True}
        if actor.actor_type == "aha":
            # 阿哈时刻（21_elation.md §21.4）：不走回合内行动（无 legal/政策/形态计数），
            # 结算主体见 _run_aha_turn；回合事件（on_turn_start/end）不广播——特殊单位口径
            self._run_aha_turn()
            return {"actor_id": actor.actor_id, "kind": kind, "clock": now, "skipped": False}
        self._run_turn(actor_state, kind)
        return {"actor_id": actor.actor_id, "kind": kind, "clock": now, "skipped": False}

    def _termination_reason(self) -> str:
        """终止原因（battle_end payload；与 _should_terminate 分支同序镜像——
        改判停分支时同步（防腐：两处分支必须同源，见 _should_terminate）."""
        if not self._allies_alive():
            return "all_allies_dead"
        if not self._enemies_alive() and not self._has_next_wave():
            return "target_killed"
        term = self.encounter.termination
        if term.mode == "fixed_av" and self.state.clock >= term.max_action_value:
            return "max_action_value_reached"
        cyc = self.encounter.cycle
        if cyc is not None and cyc.max_cycles > 0 and self.state.cycle_index > cyc.max_cycles:
            return "max_cycles"
        return "unknown"

    def _emit_battle_end(self, reason: str) -> None:
        """battle_end 发射（11_combat_log 终局锚点；一次性——终局后重复 step 不重发）."""
        if getattr(self, "_battle_end_emitted", False):
            return
        self._battle_end_emitted = True
        self.bus.emit("battle_end", {"reason": reason}, self.state)

    def run(self) -> BattleState:
        if self.scheduler is None:
            self._init_state()

        for _ in range(MAX_TURNS_SAFETY):
            if self.step() is None:
                return self.state
        # 撞兜底上限：局没打完——标记 + 日志 + 告警（毒数据防线：截断局不得当合法优化样本）
        self.state.truncated = True
        self._emit_battle_end("max_turns")
        self.state.log.append(
            f"AV{self.state.clock:.1f}: ⚠ 行动数撞兜底上限 {MAX_TURNS_SAFETY}，战斗被截断（truncated）")
        warnings.warn(
            f"战斗撞 MAX_TURNS_SAFETY={MAX_TURNS_SAFETY} 兜底上限被截断：局未打完，"
            "state.truncated=True，snapshot 不得作为合法优化样本",
            RuntimeWarning, stacklevel=2)

        return self.state
