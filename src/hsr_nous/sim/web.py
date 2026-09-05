"""网页端调试台（web 边界层）：FastAPI 单页应用，复用 `DebugController` 全部能力.

- 单会话：一次服务一场战斗；`POST /api/load` 换 YAML 重开一局（也接受 `{config: 名字}`
  直接从配置库 `battles.py` 取局——大厅卡片[开始]走此路）；
  `POST /api/restart` 同配置一键重开（当局 build/stage/mode/seed 原样重载，不进编辑器）
- 启动界面：空会话启动落 `#/home` 大厅（配置库 CRUD：`/api/battles` + save/delete）；
  带 YAML/`--config` 启动直达 `#/battle` 战斗视图
- 表单编辑器：`/api/catalog` 四张候选清单（角色/光锥/遗器/敌人）；
  `/api/battles/assemble` 表单→YAML 预览（不落库）；`/api/battles/save` 接受
  `{form}` 或原 `{build_yaml, stage_yaml}` 两种形态（组装唯一事实源在 battles.py）
- 推进：`/api/step` 单调度回合 / `/api/continue` 跑到断点或终局
- 断点：`/api/break` + `/api/clear_breaks`；回退：`/api/back` + `/api/goto`
- 检视：`/api/state` 全场概览 / `/api/bar` 行动条 / `/api/inspect/{id}` 单单位
  （snapshot + effective 有效面板 + modifier 完整明细）/ `/api/snapshot`
- 事件旁听（呈现层只读，引擎零行为差）：bus emit 事件 → 结构化事件箱，`/api/state`
  与推进响应附增量 `events`（前端跳字/事件卡取数）；back/goto 先清箱，重放段按决策簿
  重灌并以 `events_reset` 全量重发
- 单位资料：`/api/unit_skills/{id}` 全技能详情（悬浮卡取数）；
  `/api/unit_sheet/{id}` C 面板聚合（技能+星魂+光锥+遗器一处取数）
- 手动决策收发室（三阶段）：引擎线程在决策点登记 `pending` 后阻塞等 `threading.Event`，
  `/api/choose` 写入选择并放行——因此引擎调用一律 `asyncio.to_thread` 放后台线程，
  event loop 不被堵死，choose 才进得来。pending 带 `phase`：`"action"`（choices=合法行动，
  choose {index}）→ 引擎进 `_execute_action` → `"target"`（candidates=合法目标 + `default`，
  choose {actor_id}）；行动前/后窗口另起 `"ultimate"`（ready=能量满我方 + key_hint 1234，
  choose {actor_id} 放 / "skip" 不放）。三把 Event 各管各。目标记忆 `last_target`：同行动方
  下次 target pending 的 default 取上次选择（死了/不在候选回首个）。self/aoe/bounce/ally_aoe
  不触发 target 阶段（引擎 `_resolve_targets` 路由天然直通），候选 ≤1 也直通

线程纪律：`session.lock` 是"引擎忙"闸——推进/回退类端点非阻塞抢锁，抢不到即 409
（决策点挂起期间 back/goto 会踩正在等的 step，必须排他）；换局端点（load/restart）
先排干旧局（交还编译策略 + 放行挂起决策点）再等锁收尾，决策点卡死时也能换局；
`/api/choose` 与检视类读端点不拿锁（choose 若拿锁会与持锁等答案的 step 死锁；
state 轮询必须看得见 pending）。
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

from hsr_nous.sim.battles import (
    assemble_form,
    battle_catalog,
    build_team_member,
    delete_battle,
    description_doc,
    list_battles,
    load_battle,
    save_battle,
    set_extra_template_roots,
    template_doc,
    template_hit,
    template_roots,
)
from hsr_nous.sim.compile import compile_encounter_yaml
from hsr_nous.sim.debug import DebugController
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.resources import ultimate_available

_STATIC = Path(__file__).parent / "web_static" / "index.html"

#: 官方 desc 占位符：#N[i]（可紧跟 %——该值是分数，显示 ×100 取整）
_DESC_PARAM_RE = re.compile(r"#(\d+)\[(i|f\d+)\](%?)")

#: 官方文本【机制名】标记（xref 可点名集合抽取用）
_BRACKET_RE = re.compile(r"【([^【】]+)】")


def _format_desc(desc: Any, params: Any) -> Optional[str]:
    """旁车官方 desc 服务端格式化（前端保持哑）：#N[i] 整数档、#N[f1]/[f2] 浮点档（N 位小数）
    按 params 满级档（末档，模板等级）代入；占位符紧跟 % 的值 ×100（0.5→50 / 0.23→23.0），
    否则原值（2→2 / 2.5→2.5）；索引越界原样保留（显示降级不炸）。无 desc → None。"""
    if not desc:
        return None
    text = str(desc)
    top = [float(v) for v in (params[-1] if isinstance(params, list) and params else [])]

    def _sub(m: "re.Match[str]") -> str:
        idx = int(m.group(1)) - 1
        if not (0 <= idx < len(top)):
            return m.group(0)
        v, kind, pct = top[idx], m.group(2), m.group(3)
        if kind == "i":
            if pct:  # 紧跟 %：分数 ×100 取整（% 保留）
                return str(round(v * 100)) + pct
            return str(int(v)) if v.is_integer() else str(v)
        nd = int(kind[1:])   # [fN]：浮点 N 位小数（% 时 ×100）
        return (f"{v * 100:.{nd}f}" + pct) if pct else f"{v:.{nd}f}"

    return _DESC_PARAM_RE.sub(_sub, text)


def _serialize_action(action: Any, index: int) -> Dict[str, Any]:
    """合法行动 → 决策候选卡片（只挑决策用得上的字段）。"""
    return {
        "index": index,
        "action_id": action.action_id,
        "name": action.name,
        "action_type": action.action_type,
        "target_type": action.target_type,
        "skill_point_cost": action.skill_point_cost,
        "skill_point_gain": action.skill_point_gain,   # 按钮"产点 N"标签
    }


def _scaling_rows(rows: Any) -> Optional[List[Dict[str, float]]]:
    """倍率表（按等级 list）→ 可 JSON 的纯数据；None 直通。"""
    if rows is None:
        return None
    return [{k: round(float(v), 4) for k, v in row.items()} for row in rows]


def _serialize_skill(action: Any, desc: Optional[str], energy_gain_default_fn: Any = None) -> Dict[str, Any]:
    """Action → 技能详情（技能悬浮卡 / C 面板技能 tab 共用；scaling 保留按等级全表）。

    energy_gain_default_fn：类型缺省回能查表（pipeline.energy_gain_default——rulebook
    energy 节唯一来源；web 不私有副本，防腐原则"能代码直接消费 spec 的一律消费"）。
    """
    if energy_gain_default_fn is None:
        energy_gain_default_fn = lambda _t: 0
    return {
        "action_id": action.action_id,
        "name": action.name,
        "action_type": action.action_type,
        "target_type": action.target_type,
        "damage_type": action.damage_type,
        "scaling": _scaling_rows(action.scaling) or [],
        "scaling_blast": _scaling_rows(action.scaling_blast),
        "energy_cost": action.energy_cost,
        "energy_gain": (action.energy_gain if action.energy_gain is not None
                        else energy_gain_default_fn(action.action_type)),
        "energy_gain_default": action.energy_gain is None,  # True=按类型缺省（前端括注）
        "toughness_dmg": action.toughness_dmg,
        "skill_point_cost": action.skill_point_cost,
        "skill_point_gain": action.skill_point_gain,
        "instances": action.instances,
        "desc": desc,  # 模板 actions 原文 desc；无 → None（前端"无描述"）
    }


def _shield_formula_text(spec: Optional[Dict[str, Any]]) -> str:
    """shield 声明块 → 公式原文（前端保持哑，服务端格式化）：
    amount 表达式族直出表达式原文；scaling/flat 族出声明块紧凑 JSON；无声明 → ""。"""
    if not spec:
        return ""
    if spec.get("amount") is not None:
        return str(spec["amount"])
    return json.dumps(spec, ensure_ascii=False)


def _serialize_modifier(m: Any, state: Any, actions_by_actor: Any = None,
                        shields: Any = ()) -> Dict[str, Any]:
    """Modifier → 状态明细（C 面板状态 tab / 徽章弹层共用；snapshot() 之外的完整版）。

    source_kind/source_ref 是 F2 引擎侧附加记账（action/hook/trace/light_cone/relic/state/""）；
    source_action_name/type 为 ref=action_id 时反查施加者行动表的解析件（查不到空串——
    前端来源文案逐级回落）。
    shields：携带者护盾栈（B3 盾值行取数——公式原文读 m.shield_spec 留底，当前值按
    modifier_id 关联 ShieldInstance；取不到实例 → remaining=None 只显示公式）。
    """
    src = state.actors.get(m.source_id)
    src_action = next((a for a in (actions_by_actor or {}).get(m.source_id, [])
                       if a.action_id == m.source_ref), None)
    row = {
        "modifier_id": m.modifier_id,
        "name": m.name,
        "type": m.modifier_type,
        "stacks": m.stacks,
        "max_stack": m.max_stack,
        "duration": m.duration,          # 剩余时长（携带者回合 tick；0=永久）
        "source_id": m.source_id,
        "source_name": src.actor.name if src is not None else (m.source_id or ""),
        "source_kind": m.source_kind,
        "source_ref": m.source_ref,
        "source_action_name": src_action.name if src_action is not None else "",
        "source_action_type": src_action.action_type if src_action is not None else "",
        "stat_effects": dict(m.stat_effects),
        "scaling_effects": {k: [s, r] for k, (s, r) in m.scaling_effects.items()},
        "override_effects": dict(m.override_effects),
        "dispellable": m.dispellable,
    }
    inst = next((s for s in shields if s.modifier_id == m.modifier_id), None)
    if getattr(m, "shield_spec", None) or inst is not None:
        row["shield"] = {
            "formula": _shield_formula_text(getattr(m, "shield_spec", None)),
            "remaining": (round(float(inst.remaining), 1) if inst is not None else None),
        }
    return row


class WebSession:
    """单会话战斗：一台 DebugController + 手动决策收发室（pending / choice event）。"""

    def __init__(self) -> None:
        self.ctl: Optional[DebugController] = None
        self.mode: str = MODE_EXPECTED       # 仿真模式（expected/roll）
        self.seed: Optional[int] = None
        self.build_yaml: str = ""            # 当局 build 原文（unit_sheet 聚合取数用）
        self.stage_yaml: str = ""
        self.manual: bool = False            # 决策模式（manual=决策点问网页 / auto=编译策略）
        self.pending: Optional[Dict[str, Any]] = None  # 待决策点（phase=action/target），None=无
        self.lock = threading.Lock()         # 引擎忙闸（见模块 docstring 线程纪律）
        # 两阶段收发室：行动与目标各一把 Event（分开——复用同一把会把 target 放行错喂给 action）
        self._action_choice: Optional[int] = None
        self._action_event = threading.Event()
        self._target_choice: Optional[str] = None
        self._target_event = threading.Event()
        # 终结技窗口（第三把 Event，v2b）：choose "skip"=本窗口不放
        self._ult_choice: Optional[str] = None
        self._ult_event = threading.Event()
        # 决策点插队终结技（第四路，ult_now）：瞄准/行动选择中随时开大（游戏同款）——
        # 写 actor_id 放行，引擎线程唤醒后在 _decision_hook 内施放并重返决策点
        self._ult_now: Optional[str] = None
        # 目标记忆：行动方 actor_id → 上次选择的目标 actor_id（崩铁本体"记住上次目标"交互）
        self.last_target: Dict[str, str] = {}
        self._log_cursor = 0                 # 网页端独立日志游标（增量喂前端，与 ctl 游标互不干扰）
        self._event_box: List[Dict[str, Any]] = []  # 呈现层事件箱（bus 旁听；跳字/事件卡取数）
        self._event_cursor = 0               # 事件箱游标（与 _log_cursor 同模式）
        self._sidecars: Dict[str, Optional[Dict[str, Any]]] = {}  # 呈现层旁车缓存（actor_id → dict/None）
        self._tpl_provenance: Dict[str, Optional[Dict[str, str]]] = {}  # 模板来源缓存（actor_id → {source,path}/None）
        self._av_fx: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}  # AV 变动效果缓存（actor_id → action_id → 效果列）

    # ------------------------------------------------------------------
    # 开局 / 模式
    # ------------------------------------------------------------------

    def load(self, build_yaml: str, stage_yaml: str, mode: str, seed: Optional[int]) -> None:
        """编译 YAML 重开一局（默认手动决策，对齐 CLI debug 的 REPL 默认）。"""
        if mode not in (MODE_EXPECTED, MODE_ROLL):
            raise ValueError(f"未知仿真模式 {mode!r}（{MODE_EXPECTED}/{MODE_ROLL}）")
        self._release_pending()  # 旧局若卡在决策点：先放行旧引擎线程（None=退回默认/缺省）
        # 模板根查找链惰性读取（battles 唯一事实源）：--templates 注入的附加根在此生效
        compiled = compile_encounter_yaml(build_yaml, stage_yaml, template_roots=template_roots())
        self.ctl = DebugController.from_compiled(compiled, mode=mode, seed=seed)
        self.mode, self.seed = mode, seed
        self.build_yaml, self.stage_yaml = build_yaml, stage_yaml  # 原文留底（unit_sheet 取 LC/遗器/星魂配置）
        self.pending = None
        self._action_choice, self._target_choice, self._ult_choice = None, None, None
        self._ult_now = None
        self._action_event = threading.Event()
        self._target_event = threading.Event()
        self._ult_event = threading.Event()
        self.last_target = {}
        self._log_cursor = 0
        self._event_box = []
        self._event_cursor = 0
        self._tap_events()  # 事件旁听挂上新引擎 bus（须在首个检查点深拷贝前，重放才可重灌）
        self._sidecars = {}  # 换局重读旁车（data 可能重新生成过）
        self._tpl_provenance = {}  # 换局重查模板来源（--templates 可能变过）
        self._av_fx = {}     # 换局重扫 AV 变动效果（同上，模板可能重新生成）
        self.set_manual()

    def set_manual(self) -> None:
        ctl = self._require_ctl()
        ctl.set_action_hook(self._decision_hook)
        ctl.set_target_hook(self._target_hook)  # 须在 set_action_hook 后（它才建手动决策源）
        ctl.set_ult_hook(self._ult_hook)        # 同上
        self.manual = True

    def set_auto(self) -> None:
        self._require_ctl().set_auto()
        self.manual = False
        self._release_pending()  # 卡在决策点的等待放行（None=本次退回默认/缺省）

    def _release_pending(self) -> None:
        """放行挂起的决策点（若有）：按阶段写 None 选择并 set 对应 Event。"""
        if self.pending is None:
            return
        if self.pending["phase"] == "action":
            self._action_choice = None
            self._action_event.set()
        elif self.pending["phase"] == "target":
            self._target_choice = None
            self._target_event.set()
        else:
            self._ult_choice = None
            self._ult_event.set()

    # ------------------------------------------------------------------
    # 手动决策收发室（在引擎线程里跑）
    # ------------------------------------------------------------------

    def _build_action_pending(self, actor_id: Optional[str], legal: List[Any]) -> Dict[str, Any]:
        """行动决策点 payload（phase=action）：choices(含 av_fx 幽灵条数据) + unavailable 灰显。

        不可用行动（灰显下发）：过形态过滤但被战技点/能量拦下的——游戏同款灰按钮，
        不是从按钮行消失（曾致"变身三技能没了"的误判：0 战技点时合法集只剩普攻）。
        """
        unavailable: List[Dict[str, Any]] = []
        eng = self.ctl.engine if self.ctl else None
        st = eng.state.actors.get(actor_id) if eng is not None and actor_id else None
        if eng is not None and st is not None:
            legal_ids = {a.action_id for a in legal}
            rest = [a for a in eng.actions_by_actor.get(actor_id, [])
                    if a.action_id not in legal_ids and a.action_type != "follow_up"]
            rest = eng._legal_with_state(st, rest)
            # 灰显技能键位（游戏同款：灰技仍占原键位——可悬停/长按看描述，轻点只报原因）。
            # 与前端 keyOf 同规约：单战技=E，双战技=W、E（按钮行给出顺序 = legal 序 + 灰显序）
            skills_vis = ([a for a in legal if a.action_type == "skill"]
                          + [a for a in rest if a.action_type == "skill"])

            def _grey_key(a: Any) -> str:
                if a.action_type != "skill":
                    return ""
                if len(skills_vis) == 1:
                    return "e"
                if len(skills_vis) == 2:
                    return "w" if skills_vis.index(a) == 0 else "e"
                return ""   # >2 战技现无实例（同前端 keyOf 注释）

            for a in rest:
                if a.action_type == "ultimate":
                    continue   # 终结技不走灰显行——归右侧 1-4 槽位行（全槽常显带原因，见 _ready_ult_rows）
                if a.skill_point_cost > 0:
                    reason = "战技点不足"
                else:
                    reason = "不可用"
                unavailable.append({"name": a.name, "action_id": str(a.action_id),
                                    "action_type": a.action_type, "target_type": a.target_type,
                                    "skill_point_cost": a.skill_point_cost,
                                    "skill_point_gain": a.skill_point_gain,
                                    "key_hint": _grey_key(a), "reason": reason})
        return {
            "phase": "action",
            "actor_id": actor_id,
            "choices": [{**_serialize_action(a, i),
                         "av_fx": self._av_fx_of(actor_id).get(str(a.action_id), [])}
                        for i, a in enumerate(legal)],
            "unavailable": unavailable,
        }

    def _decision_hook(self, legal: List[Any]) -> Optional[Any]:
        """行动决策回调（phase=action）：登记候选 → 阻塞等 /api/choose → 返回选中的 Action.

        等待循环多一路 ult_now：瞄准/选择中随时开大（游戏同款）——引擎线程唤醒后在
        本 hook 内施放（_fire_ultimate 统一漏斗；目标 ult 内嵌目标决策点），施放完
        重挂同一行动决策点继续等（前端瞄准态因此不断）；变身入口技=本回合结束，直接返回。
        """
        actor_id = self._actor_of(legal)
        # 每次决策先清事件：Event 一旦 set 不自动复位，不清则后续决策 wait() 被陈旧 set 秒放
        # （症状：首个决策后全部走默认轮转、pending 不再出现）
        self._action_event.clear()
        self.pending = self._build_action_pending(actor_id, legal)
        while True:
            self._action_event.wait()
            if self._ult_now is not None:
                token, self._ult_now = self._ult_now, None
                # 先清再放（不是放完再清）：施放期间 choose 到达的 set 必须存活到下一轮
                # wait——放完再清会把"施放窗口内到达的回答"抹掉，hook 永眠死锁
                # （test_ult_now 曾整文件卡死 600s：死锁线程非 daemon，pytest 进程退不出）
                self._action_event.clear()
                if self._fire_ult_now(token):
                    self.pending = None
                    return None   # 变身/入口技=本回合结束（引擎口径退回默认，不再重问）
                self.pending = self._build_action_pending(actor_id, legal)   # 重返决策点
                continue
            idx, self.pending, self._action_choice = self._action_choice, None, None
            if idx is None or not (0 <= idx < len(legal)):
                return None
            return legal[idx]

    def _fire_ult_now(self, actor_id: str) -> bool:
        """决策点插队终结技（引擎线程内执行）：返回 True=入口技已变身（回合结束）。"""
        if self.ctl is None:
            return False
        eng = self.ctl.engine
        st = eng.state.actors.get(actor_id)
        ult = next((a for a in eng.actions_by_actor.get(actor_id, [])
                    if a.action_type == "ultimate"), None)
        if st is None or ult is None:
            return False
        entry = eng.state_entry_actions.get(ult.action_id)
        eng._fire_ultimate(st, ult)
        return entry is not None

    def choose_ultimate_now(self, actor_id: str) -> None:
        """/api/choose（ult_now）：行动决策点排队插队终结技——校验就绪后放行引擎线程。

        游戏同款"随时可大"；可取消性不变（窗口 Esc=skip、瞄准 Esc=取消，owner 裁决
        不抄游戏"终结技瞄准不可取消"的规矩）。
        """
        if self.pending is None or self.pending["phase"] != "action":
            raise RuntimeError("当前不在行动决策点")
        if self.ctl is None:
            raise RuntimeError("未开局")
        eng = self.ctl.engine
        st = eng.state.actors.get(actor_id)
        if st is None or not st.alive or st.banished:
            raise ValueError(f"单位 {actor_id!r} 不存在/已阵亡/已离场")
        ult = next((a for a in eng.actions_by_actor.get(actor_id, [])
                    if a.action_type == "ultimate"), None)
        if ult is None or not ultimate_available(st, ult):
            raise ValueError(f"{st.actor.name} 终结技未就绪")
        self._ult_now = actor_id
        self._action_event.set()

    def _target_hook(self, actor_state: Any, target_type: str, candidates: List[Any]) -> Optional[Any]:
        """目标决策回调（phase=target）：候选 → 阻塞等 /api/choose → 返回选中的 ActorState.

        直通情形（返回 None=引擎缺省，不空弹窗）：
        - 重放段（back/goto 填缝，replay_queue 非 None——debug.py 闭包直接消费决策簿
          目标队列（record 三元组第三位），user_hook 根本不被调；此处判断只是双保险）
        - 候选 ≤1（空集/单怪/单队友）
        引擎只在 single/blast（敌方候选）与 ally_single（我方候选）时调本 hook——self/aoe/bounce
        天然直通（engine._resolve_targets 的路由决定）。
        """
        if self.ctl is None or self.ctl._cell["replay_queue"] is not None:
            return None
        if len(candidates) <= 1:
            return None
        actor_id = actor_state.actor.actor_id
        ids = [c.actor.actor_id for c in candidates]
        memory = self.last_target.get(actor_id)
        default = memory if memory in ids else ids[0]  # 目标记忆：记忆值死了/不在候选则回首个
        self._target_event.clear()
        self.pending = {
            "phase": "target",
            "actor_id": actor_id,
            "target_type": target_type,
            "candidates": [
                {"actor_id": c.actor.actor_id, "name": c.actor.name, "hp": round(c.current_hp, 1)}
                for c in candidates
            ],
            "default": default,
        }
        self._target_event.wait()
        picked_id, self.pending, self._target_choice = self._target_choice, None, None
        if picked_id is not None:
            hit = next((c for c in candidates if c.actor.actor_id == picked_id), None)
            if hit is not None:
                self.last_target[actor_id] = picked_id  # 记帐：该行动方上次选了谁
                return hit
        return None

    def choose_action(self, index: int) -> None:
        """/api/choose（行动阶段）：写入编号并放行引擎线程。"""
        if self.pending is None or self.pending["phase"] != "action":
            raise RuntimeError("当前不在行动决策点")
        if not (0 <= index < len(self.pending["choices"])):
            raise ValueError(f"无效编号 {index}（共 {len(self.pending['choices'])} 个候选）")
        self._action_choice = index
        self._action_event.set()

    def choose_target(self, actor_id: str) -> None:
        """/api/choose（目标阶段）：写入目标 actor_id 并放行引擎线程。"""
        if self.pending is None or self.pending["phase"] != "target":
            raise RuntimeError("当前不在目标决策点")
        ids = [c["actor_id"] for c in self.pending["candidates"]]
        if actor_id not in ids:
            raise ValueError(f"无效目标 {actor_id!r}（候选：{ids}）")
        self._target_choice = actor_id
        self._target_event.set()

    def _ult_hook(self, actor_state: Any, ready: List[Any]) -> Optional[Any]:
        """终结技窗口回调（phase=ultimate）：ready 清单 → 阻塞等 /api/choose → Action / None(skip).

        重放短路由 debug.py 闭包兜（user_hook 根本不被调）；空 ready 直通不空弹窗。
        """
        if not ready or self.ctl is None:
            return None
        allies = [aid for aid, st in self.ctl.state.actors.items()
                  if st.actor.actor_type != "monster"]
        self._ult_event.clear()
        self.pending = {
            "phase": "ultimate",
            "actor_id": actor_state.actor.actor_id,  # 窗口所属行动方（回合高亮用）
            "ready": [
                {
                    "actor_id": st.actor.actor_id,
                    "name": st.actor.name,
                    "ult_name": action.name,
                    "target_type": action.target_type,   # 确认态作用范围标签（群攻/单体…）
                    "key_hint": str(allies.index(st.actor.actor_id) + 1)
                                if st.actor.actor_id in allies else "",
                    # 免确认立即释放（ult_quick_cast 显式标注族）：窗口里按下即放不进确认态
                    "immediate": bool(action.ult_quick_cast),
                }
                for st, action in ready
            ],
        }
        self._ult_event.wait()
        token, self.pending, self._ult_choice = self._ult_choice, None, None
        if token is None or token == "skip":
            return None  # 跳过=本窗口不放（能量保留，下一窗口再问）
        hit = next((a for st, a in ready if st.actor.actor_id == token), None)
        return hit

    def choose_ultimate(self, token: str) -> None:
        """/api/choose（终结技阶段）：写入 ready 单位 actor_id 或 "skip" 并放行引擎线程。"""
        if self.pending is None or self.pending["phase"] != "ultimate":
            raise RuntimeError("当前不在终结技决策点")
        if token != "skip":
            ids = [r["actor_id"] for r in self.pending["ready"]]
            if token not in ids:
                raise ValueError(f"无效终结技选择 {token!r}（ready：{ids}，或 skip）")
        self._ult_choice = token
        self._ult_event.set()

    def _actor_of(self, legal: List[Any]) -> Optional[str]:
        """由合法行动反查决策方（actions_by_actor 归属）。"""
        if not legal or self.ctl is None:
            return None
        for aid, actions in self.ctl.engine.actions_by_actor.items():
            if any(a.action_id == legal[0].action_id for a in actions):
                return aid
        return None

    # ------------------------------------------------------------------
    # 检视
    # ------------------------------------------------------------------

    def _require_ctl(self) -> DebugController:
        if self.ctl is None:
            raise RuntimeError("尚未开局——先 POST /api/load 或用 hsr-sim web <build> <stage> 启动")
        return self.ctl

    def delta_logs(self) -> List[str]:
        """自上次读取后的新增日志（回退截断时游标钳位）。"""
        if self.ctl is None:
            return []
        log = self.ctl.state.log
        start = min(self._log_cursor, len(log))
        self._log_cursor = len(log)
        return log[start:]

    # ------------------------------------------------------------------
    # 事件旁听（呈现层只读：bus emit → 结构化战斗事件箱）
    # ------------------------------------------------------------------

    def _tap_events(self) -> None:
        """bus 只读 emit 事件 → 结构化事件箱（T1 跳字 / T2 事件卡 / T3 关键点检测的取数 backbone）。

        纪律对齐 debug.py `_cell`：闭包只捕普通 list/dict（函数是深拷贝原子——所有检查点
        引擎按引用共享同一箱，back/goto 重放段事件自动重灌）；绝不捕 self/engine
        （锁与重对象会被冻进检查点）。ult 的行动名在 delta_events 取数时补（此处无引擎）。
        """
        assert self.ctl is not None
        box = self._event_box
        mod_names: Dict[str, str] = {}   # modifier_id → 显示名（移除时已摘，靠缓存回填）

        def _base(ctx: Any) -> Dict[str, Any]:
            return {"turn": int(getattr(ctx, "turn_count", 0) or 0),
                    "clock": round(float(getattr(ctx, "clock", 0.0) or 0.0), 1)}

        def _on_hit(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            box.append({**_base(ctx), "kind": "hit",
                        "source": p.get("source"), "target": p.get("target"),
                        "amount": round(float(p.get("amount", 0.0)), 1),
                        "absorbed": round(float(p.get("absorbed", 0.0)), 1),
                        "crit": bool(p.get("is_critical")),
                        "action_type": p.get("action_type", ""),
                        "seg": int(p.get("seg_index", 0) or 0)})

        def _on_hp_dec(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            reason = p.get("reason")
            if reason not in ("dot", "break"):
                return  # hit 段已由 after_being_hit 全包（带暴击/段序/盾吸收），不重复记
            box.append({**_base(ctx), "kind": reason,
                        "source": p.get("source"), "target": p.get("target"),
                        "amount": round(float(p.get("amount", 0.0)), 1)})

        def _on_hp_inc(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            box.append({**_base(ctx), "kind": "heal",
                        "source": p.get("source"), "target": p.get("target"),
                        "amount": round(float(p.get("amount", 0.0)), 1)})

        def _on_kill(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            box.append({**_base(ctx), "kind": "death",
                        "source": p.get("source"), "target": p.get("target")})

        def _on_wave(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            box.append({**_base(ctx), "kind": "wave", "wave": int(p.get("wave_index", 0)) + 1})

        def _on_mod_add(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            mid = str(p.get("modifier_id") or "")
            st = getattr(ctx, "actors", {}).get(p.get("target"))
            m = st.modifiers.get(mid) if st is not None else None
            name = m.name if m is not None else mid
            mod_names[mid] = name
            box.append({**_base(ctx), "kind": "mod_add",
                        "target": p.get("target"), "source": p.get("source"),
                        "mod": name, "mod_type": p.get("modifier_type", "")})

        def _on_mod_del(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            mid = str(p.get("modifier_id") or "")
            box.append({**_base(ctx), "kind": "mod_del",
                        "target": p.get("target"),
                        "mod": mod_names.get(mid, mid), "reason": p.get("reason", "")})

        def _on_ult(_et: str, p: Dict[str, Any], ctx: Any) -> None:
            box.append({**_base(ctx), "kind": "ult",
                        "source": p.get("source"), "action": p.get("action", "")})

        bus = self.ctl.engine.bus
        bus.subscribe("after_being_hit", _on_hit)
        bus.subscribe("on_hp_decrease", _on_hp_dec)
        bus.subscribe("on_hp_increase", _on_hp_inc)
        bus.subscribe("on_kill", _on_kill)
        bus.subscribe("on_wave_start", _on_wave)
        bus.subscribe("after_apply_modifier", _on_mod_add)
        bus.subscribe("after_remove_modifier", _on_mod_del)
        bus.subscribe("on_ultimate", _on_ult)

    def delta_events(self) -> List[Dict[str, Any]]:
        """自上次读取后的新增战斗事件（回退截断时游标钳位；ult 事件取数时补行动名）。"""
        if self.ctl is None:
            return []
        start = min(self._event_cursor, len(self._event_box))
        items = self._event_box[start:]
        self._event_cursor = start + len(items)
        for e in items:  # ult 旁听只记 action_id（闭包不持引擎），此处反查行动名
            if e.get("kind") == "ult" and e.get("source") and e.get("action"):
                hit = next((a for a in self.ctl.engine.actions_by_actor.get(e["source"], [])
                            if a.action_id == e["action"]), None)
                if hit is not None:
                    e["name"] = hit.name
        return items

    def reset_events(self) -> None:
        """回退/跳转前清事件箱（原地清——检查点引擎的旁听闭包共享此箱，重放段会重灌）。"""
        del self._event_box[:]
        self._event_cursor = 0

    def _intent_of(self, actor_id: str, st: Any) -> Optional[str]:
        """敌人下一动意图（纯展示）：镜像 `engine._enemy_turn` 的 actions[0] 直选口径；
        无行动（占位空过）/非敌 → None（前端不显示）。scheduler preview 只含 (actor, kind, eta)
        无行动身份，"做什么"只能取自引擎行动表——与敌方回合实际执行同一份数据。"""
        if st.actor.actor_type != "monster":
            return None
        actions = self.ctl.engine.actions_by_actor.get(actor_id, [])
        return actions[0].name if actions else None

    def state_payload(self) -> Dict[str, Any]:
        """/api/state：field() + 终局/模式/待决策点/目标记忆，单位卡补 max_hp/能量(含显示名)/韧性/modifier 数。"""
        if self.ctl is None:
            return {"loaded": False, "pending": None}
        payload = self.ctl.field()
        actors = {}
        for aid, info in payload["actors"].items():
            st = self.ctl.state.actors[aid]
            actors[aid] = {
                **info,
                "max_hp": round(st.actor.stats.hp, 1),
                "max_energy": round(st.actor.stats.max_energy, 1),
                # 护盾当前值（ShieldInstance.remaining 求和；无盾 → 0——卡片盾条/HP 叠加层取数）
                "shield": round(sum(float(getattr(s, "remaining", 0.0) or 0.0)
                                  for s in getattr(st, "shields", [])), 1),
                # 能量槽显示名（旁车；None → 前端回落"能量"）
                "energy_name": (self._sidecar_of(aid) or {}).get("energy_name"),
                # 特殊充能槽（ult_cost_resource 驱动，如白厄火种；常规能量角色 → None）
                "charge": self._charge_of(aid, st),
                # 自定义资源行（毁伤/充能族；无声明 → []）
                "resources": self._custom_resources_of(aid, st),
                # 模板来源徽章（"anchor"=附加根 / "generated"=默认根；inline 无模板 → None 不标）
                "template_source": (self._template_provenance_of(aid) or {}).get("source"),
                "actor_type": st.actor.actor_type,
                "banished": st.banished,
                "toughness": round(st.toughness, 1),
                "max_toughness": round(st.actor.stats.max_toughness, 1),
                "weakness": list(st.actor.stats.weakness),
                # 抗性小徽标取数（纯展示；只下发非零项，零抗不刷屏）
                "resistance": {k: round(float(v), 4)
                               for k, v in st.actor.stats.resistance.items() if v},
                # 敌人下一动意图（纯展示；见 _intent_of）
                "intent": self._intent_of(aid, st),
                "modifiers": len(st.modifiers),
                "modifier_list": [m.name for m in st.modifiers.values()],  # 徽章 chips（③）
                # buff 小方块图标行三件套（L1/L5 纯展示；modifier_list 纯名数组保持不动）
                "modifier_icons": [
                    {"name": m.name, "stacks": m.stacks, "type": m.modifier_type}
                    for m in st.modifiers.values()
                ],
            }
        return {
            **payload,
            "actors": actors,
            # B1 编队序显式下发（= build 编队序，与终结技窗口 key_hint 同源同口径）：
            # actor_id 是纯数字字符串，JS 对象整数键会按数值升序重排（1313 先于 1408），
            # 前端直接信 S.actors 键序会把卡片排成数值序——编队序必须由本清单承载
            "ally_order": [aid for aid, st in self.ctl.state.actors.items()
                           if st.actor.actor_type != "monster"],
            # 敌方同口径（= stage 布场序，引擎 _enemies_alive / blast 邻接 ±1 的同源顺序）：
            # 库怪/深渊怪 actor_id 是纯数字模板 id（1002030 先于 1002011 列出也会被 JS
            # 重排到后面），敌卡排列/瞄准候选/扩散高亮都必须以本清单为准
            "enemy_order": [aid for aid, st in self.ctl.state.actors.items()
                            if st.actor.actor_type == "monster"],
            "loaded": True,
            "done": self.ctl.done,
            "mode": self.mode,
            "seed": self.seed,
            "manual": self.manual,
            "pending": self.pending,
            # 就绪终结技常态下发（ult_now 按钮取数；非入口技——变身类走 1 键/窗口，不双通道）
            "ults": self._ready_ult_rows(),
            "last_target": dict(self.last_target),
            # 当前波次（1 起，与日志"—— 第 N 波 ——"同口径；T3 波次切换检测用）
            "wave": self.ctl.engine.current_wave + 1,
            # 事件旁听增量（单游标——推进响应与 state 轮询谁先谁拿，不重复）
            "events": self.delta_events(),
        }

    def _ready_ult_rows(self) -> List[Dict[str, Any]]:
        """终结技 1-4 槽位行（state 轮询下发）：**全槽常显**（游戏右侧常态大钮）——
        就绪=金钮可放（ready=True），未就绪=灰钮带原因（ready=False + reason：
        能量/特殊充能不足、离场、阵亡），灰钮同样可长按看描述、按出原因提示。

        就绪判定与行动条徽章同口径（ultimate_available）；键位 = 编队站位序。
        """
        rows: List[Dict[str, Any]] = []
        if self.ctl is None:
            return rows
        eng = self.ctl.engine
        allies = [aid for aid, st in self.ctl.state.actors.items()
                  if st.actor.actor_type != "monster"]
        for pos, aid in enumerate(allies, 1):
            st = self.ctl.state.actors[aid]
            ult = next((a for a in eng.actions_by_actor.get(aid, [])
                        if a.action_type == "ultimate"), None)
            if ult is None:
                continue
            reason = None
            if not st.alive:
                reason = "已阵亡"
            elif st.banished:
                reason = "离场"   # 放逐=终结技禁放（owner 裁决边界），槽位照显
            elif st.state_config is not None and "ultimate" in (st.state_config.locked_actions or []):
                reason = "形态锁定"   # 卡厄斯兰那"无法施放终结技"（140805），槽位照显
            elif not ultimate_available(st, ult):
                chg = self._charge_of(aid, st)
                reason = f"{chg['label']}不足" if chg else "能量不足"
            rows.append({"actor_id": aid, "name": st.actor.name, "ult_name": ult.name,
                         "key_hint": str(pos), "target_type": ult.target_type,
                         "ready": reason is None, "reason": reason,
                         # 免确认立即释放（白厄变身/遐蝶召唤族，模板 ult_quick_cast 显式标注）：
                         # 按下即放不进确认态；其余进确认态（选中锁定→空格放→Esc 取消）
                         "immediate": bool(ult.ult_quick_cast)})
        return rows

    def resolve_actor(self, token: str) -> str:
        """单位名或 id → actor_id（同 CLI _resolve；先 setup 保证 actors 已布场）。"""
        ctl = self._require_ctl()
        ctl.engine.setup()
        actors = ctl.state.actors
        if token in actors:            return token
        for aid, st in actors.items():
            if st.actor.name == token:
                return aid
        raise KeyError(f"找不到单位 {token!r}")

    # ------------------------------------------------------------------
    # 单位资料（技能详情 / C 面板聚合）
    # ------------------------------------------------------------------

    @staticmethod
    def _template_descs(actor_id: str) -> Dict[str, str]:
        """角色/敌人模板 actions 的原文 desc 索引（action_id → desc；无模板/无 desc → 空）。"""
        for kind in ("characters", "enemies"):
            doc = template_doc(kind, actor_id)
            if doc is not None:
                return {str(a.get("action_id")): str(a["desc"]) for a in doc.get("actions") or []
                        if isinstance(a, dict) and a.get("desc")}
        return {}

    def _av_fx_of(self, actor_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """模板 hooks/行动声明里挂在各行动上的 AV 变动效果（瞄准态幽灵条数据源；只读模板不碰引擎）。

        扫描面（owner 裁决：行动值变动一律给预览，变速与推拉条同待遇）：
        - 拉条类 hook effects：immediate_action/advance_action/delay_action/grant_extra_turn
          → {who, kind, pct}
        - 变速类 apply_modifier effects：modifier.stat_effects 含 spd（flat）/spd_pct（比例）
          → {who, kind: spd/spd_pct, delta/pct}
        - 行动级键：act_now_targets → {who, kind: immediate}（白厄 140809 族）；
          行动 apply_modifiers 含 spd 同样收
        who：$event.target→target（幽灵跟箭头）、self、all_allies、all_enemies；
        其余选择器跳过（预览宁缺毋假）。condition 只按 action_id 归属，其余条件（击杀等）
        不求值——幽灵条 = 该行动**可能**引发的 AV 变动预览，不是承诺。
        lazy + 会话缓存（换局重扫，模板可能重新生成）。
        """
        if actor_id in self._av_fx:
            return self._av_fx[actor_id]
        kinds = {"immediate_action": "immediate", "advance_action": "advance",
                 "delay_action": "delay", "grant_extra_turn": "extra"}
        who_map = {"$event.target": "target", "self": "self",
                   "all_allies": "all_allies", "all_enemies": "all_enemies"}
        out: Dict[str, List[Dict[str, Any]]] = {}

        def add(action_id: str, fx: Dict[str, Any]) -> None:
            out.setdefault(action_id, []).append(fx)

        def spd_fx(stat_effects: Any, who: Optional[str]) -> None:
            """stat_effects 里的变速成分 → fx 条目（spd=flat delta / spd_pct=比例）。"""
            if who is None or not isinstance(stat_effects, dict):
                return
            try:
                if "spd" in stat_effects:
                    spd_fx_items.append({"who": who, "kind": "spd",
                                         "delta": float(stat_effects["spd"])})
                if "spd_pct" in stat_effects:
                    spd_fx_items.append({"who": who, "kind": "spd_pct",
                                         "pct": float(stat_effects["spd_pct"])})
            except (TypeError, ValueError):
                pass  # 非数值槽：预览宁缺毋假

        doc = template_doc("characters", actor_id)
        for h in (doc or {}).get("hooks") or []:
            if not isinstance(h, dict):
                continue
            cond = str(h.get("condition") or "")
            action_ids = [m.group(1) for m in re.finditer(r"action_id\s*==\s*'([^']+)'", cond)]
            if not action_ids:
                continue
            for eff in h.get("effects") or []:
                if not isinstance(eff, dict):
                    continue
                who = who_map.get(str(eff.get("target", "self")))
                kind = kinds.get(str(eff.get("effect_type")))
                if kind is not None and who is not None:
                    pct = 1.0
                    if kind in ("advance", "delay"):
                        try:
                            pct = float(eff.get("amount")) / 100.0
                        except (TypeError, ValueError):
                            continue  # 表达式槽：预览宁缺毋假
                    for aid in action_ids:
                        add(aid, {"who": who, "kind": kind, "pct": pct})
                elif str(eff.get("effect_type")) == "apply_modifier" and who is not None:
                    # 变速 buff（征服者 spd+20 族）：同一 hook 多段 modifier 各自收割
                    spd_fx_items: List[Dict[str, Any]] = []
                    spd_fx((eff.get("modifier") or {}).get("stat_effects"), who)
                    for fx in spd_fx_items:
                        for aid in action_ids:
                            add(aid, fx)
        # 行动级 AV 效果（act_now_targets 行动键——白厄 140809"使敌方全体立即行动"族）：
        # hook 扫描的另一通道，目标域直接就是 AV 语义；行动 apply_modifiers 变速同收
        for a in (doc or {}).get("actions") or []:
            if not isinstance(a, dict):
                continue
            act_now = str(a.get("act_now_targets") or "")
            if act_now in who_map:
                add(str(a.get("action_id")),
                    {"who": who_map[act_now], "kind": "immediate", "pct": 1.0})
            for spec in a.get("apply_modifiers") or []:
                if not isinstance(spec, dict):
                    continue
                who = who_map.get(str(spec.get("target", "self")))
                spd_fx_items = []
                spd_fx((spec or {}).get("stat_effects"), who)
                for fx in spd_fx_items:
                    add(str(a.get("action_id")), fx)
        self._av_fx[actor_id] = out
        return out

    def _sidecar_of(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """呈现层旁车 lazy 读取（首用读盘 + 会话缓存；文件缺失/角色缺失/坏文件 → None 优雅降级）。"""
        if actor_id not in self._sidecars:
            self._sidecars[actor_id] = description_doc(actor_id)
        return self._sidecars[actor_id]

    def _charge_of(self, actor_id: str, st: Any) -> Optional[Dict[str, Any]]:
        """特殊充能槽下发（通用机制，ult_cost_resource 驱动，无 per-角色特例）：
        max_energy==0 且某 ult 行动声明 ult_cost_resource → {resource_id, value, cap, label}；
        否则 None（前端走原能量条——黄泉残梦类 max_energy>0 天然走原条）。

        cap：ult_cost_amount（激活线——游戏内"x/N"的 N）；0 则回落模板 custom_resources
        声明上限。label：旁车 energy_name（官方槽位名），缺省回落资源 id 原文（不脑补翻译）。
        """
        if float(st.actor.stats.max_energy) > 0:
            return None
        ult = next((a for a in self.ctl.engine.actions_by_actor.get(actor_id, [])
                    if a.action_type == "ultimate" and a.ult_cost_resource), None)
        if ult is None:
            return None
        rid = str(ult.ult_cost_resource)
        cap = float(ult.ult_cost_amount or 0.0)
        doc = template_doc("characters", actor_id) or {}
        if cap <= 0:
            cap = float(((doc.get("custom_resources") or {}).get(rid) or {}).get("max") or 0.0)
        return {"resource_id": rid,
                "value": round(float(st.resources.get(rid, 0.0)), 1),
                "cap": cap,
                "label": (doc.get("energy_name")
                          or (self._sidecar_of(actor_id) or {}).get("energy_name") or rid)}

    def _custom_resources_of(self, actor_id: str, st: Any) -> List[Dict[str, Any]]:
        """自定义资源下发（毁伤/充能族卡片资源行）：模板 custom_resources 全声明项
        → [{resource_id, value, cap, label}]；终结技充能槽（_charge_of 已显）跳过不重复。

        显示纪律（命名两态）：**只显示声明了中文官方名（`name`）的资源**——无名的
        （fire_seed_bank 银行刀、_pyre_n 计数器这类内部簿记）一律不显示，
        不拿资源 id 英文原文凑数（脑补翻译/英文 id 上屏都是事故）。
        value：st.resources 当前值（缺省 0）；cap：声明 max（0=不显示——无上限资源不做槽）。
        """
        doc = template_doc("characters", actor_id) or {}
        cr = doc.get("custom_resources") or {}
        charge = self._charge_of(actor_id, st)
        skip = charge["resource_id"] if charge else None
        out: List[Dict[str, Any]] = []
        for rid, rspec in cr.items():
            if str(rid) == skip:
                continue
            spec = rspec if isinstance(rspec, dict) else {}
            name = spec.get("name")
            cap = float(spec.get("max") or 0.0)
            if not name or cap <= 0:
                continue   # 无名（内部簿记）/无上限：不显示
            out.append({"resource_id": str(rid),
                        "value": round(float(st.resources.get(rid, 0.0)), 1),
                        "cap": cap,
                        "label": str(name)})
        return out

    def _template_provenance_of(self, actor_id: str) -> Optional[Dict[str, str]]:
        """单位模板 provenance（{source, path}）：characters → enemies 顺查（与 _template_descs
        同口径）；inline/未命中 → None。source 词表见 battles（"anchor"=附加根 / "generated"=
        默认根）；lazy + 会话缓存（同 _sidecar_of，state 轮询不重复 glob）。
        """
        if actor_id not in self._tpl_provenance:
            prov = None
            for kind in ("characters", "enemies"):
                hit = template_hit(kind, actor_id)
                if hit is not None:
                    prov = {"source": hit[1], "path": str(hit[0].resolve())}
                    break
            self._tpl_provenance[actor_id] = prov
        return self._tpl_provenance[actor_id]

    def _sidecar_source_map(self, actor_id: str) -> Dict[str, Dict[str, str]]:
        """旁车全量来源索引（ref → {name, desc, kind}）——状态 tab 来源就地展开取数（F3）。

        ref：技能 id（actions 段，kind=官方 type_text：普攻/战技/终结技/天赋/秘技）或
        行迹节点 id（traces 段，kind="行迹"）或 "rank:" 前缀星魂 id（ranks 段，kind="星魂"
        ——星魂 id 与技能 id 同号段（140801 既是普攻也是 E1），前缀防覆盖）；
        desc 服务端格式化（满级档代入）。
        """
        side = self._sidecar_of(actor_id) or {}
        out: Dict[str, Dict[str, str]] = {}
        for ref, sa in (side.get("actions") or {}).items():
            out[str(ref)] = {
                "name": str(sa.get("name", "")),
                "desc": _format_desc(sa.get("desc"), sa.get("params")) or "",
                "kind": str(sa.get("type_text") or ""),
            }
        for ref, tr in (side.get("traces") or {}).items():
            out[str(ref)] = {
                "name": str(tr.get("name", "")),
                "desc": _format_desc(tr.get("desc"), tr.get("params")) or "",
                "kind": "行迹",
            }
        for ref, rk in (side.get("ranks") or {}).items():
            out[f"rank:{ref}"] = {
                "name": str(rk.get("name", "")),
                "desc": _format_desc(rk.get("desc"), rk.get("params")) or "",
                "kind": "星魂",
            }
        return out

    @staticmethod
    def _xref_kind_tier(kind: str) -> int:
        """xref kind 解析优先级：行迹 0 > 天赋 1 > 技能 2 > 星魂 3（其余 type_text 归技能层）。"""
        if kind == "行迹":
            return 0
        if kind == "天赋":
            return 1
        if kind == "星魂":
            return 3
        return 2

    def _xref_sidecar_lookup(self, actor_id: str, name: str) -> Optional[Dict[str, str]]:
        """旁车 name 精确匹配 → {ref, name, desc, kind}（X1/X2 共用）。

        纪律（不脑补）：只查**本角色**旁车（SP 同名事故预防）；kind 优先级逐层收，
        同层多命中 = 歧义 → None（不许二选一）；零命中 → None。
        """
        smap = self._sidecar_source_map(actor_id)
        for tier in range(4):
            hits = [(ref, e) for ref, e in smap.items()
                    if e["name"] == name and self._xref_kind_tier(e["kind"]) == tier]
            if len(hits) > 1:
                return None
            if hits:
                ref, e = hits[0]
                return {"ref": ref, **e}
        return None

    def _source_resolved_id(self, m: Any) -> str:
        """F3/X1 来源可展开解析：命中施加者旁车 → 目标 ref；查不到 → ""（不可点）。

        action 类 ref=action_id 直查；hook/其他 ref=显示名 → 本角色旁车 name 精确匹配
        （照见英雄本色 → 行迹 1408103 族）。
        """
        if not m.source_ref or not m.source_id:
            return ""
        if m.source_ref in self._sidecar_source_map(m.source_id):
            return m.source_ref  # action 类：ref 即 id
        hit = self._xref_sidecar_lookup(m.source_id, m.source_ref)
        return hit["ref"] if hit is not None else ""

    def _xref_names(self, actor_id: str) -> List[str]:
        """本角色可点 xref 名集合（前端链接化预判用；服务端 xref_resolve 才是权威解析）：
        旁车全部条目名 ∪ 条目 desc 内全部【机制名】（desc 含【X】即自解析——见 ③）。"""
        names: set = set()
        for e in self._sidecar_source_map(actor_id).values():
            if e["name"]:
                names.add(e["name"])
            names.update(_BRACKET_RE.findall(e["desc"] or ""))
        return sorted(names)

    def xref_resolve(self, actor_id: str, name: str) -> Dict[str, Any]:
        """X2/X3 xref 权威解析（前端哑，点击带 actor_id+name 查此）：
        ① 场上激活 modifier（请求单位优先，其余按编队序——其状态行+来源）
        ② 本角色旁车 name 精确命中（kind 优先级，同层歧义不收）
        ③ 本角色旁车 desc 首个含【name】的条目（索引序：技能 → 行迹 → 星魂，各段 id 升序）
        全部 miss → {"found": False}（前端回落纯文本/提示，不脑补）。
        """
        ctl = self._require_ctl()
        ctl.engine.setup()   # 与 resolve_actor 同口径：先 setup 保证开局件（on_battle_start 族）已布场
        ordered = [actor_id] + [a for a in ctl.state.actors if a != actor_id]
        for aid in ordered:
            st = ctl.state.actors.get(aid)
            if st is None:
                continue
            for m in st.modifiers.values():
                if m.name == name:
                    row = _serialize_modifier(m, ctl.state, ctl.engine.actions_by_actor,
                                              shields=st.shields)
                    resolved = self._source_resolved_id(m)
                    row["expandable"] = bool(resolved)
                    row["source_ref_id"] = resolved
                    return {"found": True, "via": "active_modifier", "modifier": row}
        hit = self._xref_sidecar_lookup(actor_id, name)
        if hit is not None:
            return {"found": True, "via": "sidecar_name", "entry": hit}
        for ref, e in self._sidecar_source_map(actor_id).items():
            if f"【{name}】" in e["desc"]:
                return {"found": True, "via": "sidecar_desc", "entry": {"ref": ref, **e}}
        return {"found": False}

    def skill_details(self, actor_id: str) -> List[Dict[str, Any]]:
        """/api/unit_skills：该单位全技能详情（引擎 actions_by_actor + 旁车/模板 desc）。

        desc 优先级：呈现层旁车（官方原文，服务端格式化）> 模板 actions 原文 > None。
        """
        ctl = self._require_ctl()
        aid = self.resolve_actor(actor_id)
        descs = self._template_descs(aid)
        side_actions = (self._sidecar_of(aid) or {}).get("actions") or {}
        st = ctl.state.actors.get(aid)
        rows = []
        for a in ctl.engine.actions_by_actor.get(aid, []):
            sa = side_actions.get(str(a.action_id)) or {}
            desc = (_format_desc(sa.get("desc"), sa.get("params")) if sa.get("desc")
                    else descs.get(a.action_id))
            row = _serialize_skill(a, desc, ctl.engine.pipeline.energy_gain_default)
            if a.action_type == "ultimate" and st is not None:
                # 预览卡游戏同款：等级 + 消耗底行（消耗能量 cur/max；特殊充能=技能消耗 cur/cap点【label】）
                row["level"] = int(st.actor.skill_levels.get("ultimate", 10))
                row["cost_line"] = self._ult_cost_line(aid, st)
            rows.append(row)
        return rows

    def _ult_cost_line(self, actor_id: str, st: Any) -> str:
        """终结技消耗底行（服务端格式化，前端保持哑）：常规=消耗能量 cur/max；
        特殊充能=技能消耗 cur/cap点【label】（昔涟"21/12点【追忆】"同款——_charge_of 同口径）。"""
        chg = self._charge_of(actor_id, st)
        if chg:
            return f"技能消耗 {chg['value']:g}/{chg['cap']:g}点【{chg['label']}】"
        return f"消耗能量 {float(st.current_energy):g}/{float(st.actor.stats.max_energy):g}"

    def _eidolon_rows(self, tpl: Optional[Dict[str, Any]], member: Optional[Dict[str, Any]],
                      actor_id: str) -> List[Dict[str, Any]]:
        """星魂 tab：模板 eidolons 段 ∪ 旁车 ranks 段 → 行（E1..E6 逐魂合并）。

        - desc：官方星魂描述（旁车 ranks 段，服务端 `_format_desc` 代入——与技能 desc 同
          管线；实测 ranks 全表无占位符，代入为恒等）；模板机制注记降次级字段 note
        - active=build 配置 eidolon 等级激活；名优先模板（机制注记版），回落旁车官方名
        - 回落：缺旁车/缺条目 → desc 空串（前端只显示 note 或"（无描述）"，现状口径）
        """
        eds = (tpl or {}).get("eidolons") or {}
        active = int((member or {}).get("eidolon", 0) or 0)
        ranks = (self._sidecar_of(actor_id) or {}).get("ranks") or {}
        rows = []
        for n in range(1, 7):
            e = eds.get(f"E{n}")
            off = ranks.get(f"{actor_id}0{n}")
            if e is None and off is None:
                continue  # 模板无段且旁车无此魂（inline/敌人）→ 不产行
            rows.append({
                "rank": f"E{n}",
                "name": str((e or {}).get("name") or (off or {}).get("name") or f"E{n}"),
                "active": n <= active,
                "desc": _format_desc((off or {}).get("desc"), (off or {}).get("params")) or "",
                "note": "；".join(str(x) for x in (e or {}).get("notes") or []),
            })
        return rows

    @staticmethod
    def _light_cone_row(member: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """光锥 tab：build 配置 light_cone_template + 模板 notes（desc 原文在 notes 里）。"""
        ref = (member or {}).get("light_cone_template")
        if ref is None:
            return None
        doc = template_doc("light_cones", str(ref)) or {}
        lc_cfg = (member or {}).get("light_cone") or {}
        return {
            "name": str(doc.get("name") or ref),
            "superimposition": int(lc_cfg.get("superimposition", 1)),
            "level": int(lc_cfg.get("level", 1)),
            "desc": [str(n) for n in doc.get("notes") or []],
        }

    @staticmethod
    def _relic_rows(member: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """遗器 tab：build 配置各部位 → 套装名/主副词条（游戏内看不到，build 配置里有）。"""
        relics = (member or {}).get("relics") or {}
        if not relics:
            return None
        names: Dict[str, str] = {}

        def set_name(set_id: str) -> str:
            if set_id not in names:
                doc = template_doc("relics", set_id) or {}
                names[set_id] = str(doc.get("name") or set_id)
            return names[set_id]

        pieces = []
        for slot, r in relics.items():
            set_id = str((r or {}).get("set_id", ""))
            pieces.append({"slot": str(slot), "set_id": set_id, "set_name": set_name(set_id),
                           "main": (r or {}).get("main"), "subs": (r or {}).get("subs") or {}})
        counts: Dict[str, int] = {}
        for p in pieces:
            counts[p["set_id"]] = counts.get(p["set_id"], 0) + 1
        sets = [{"set_id": sid, "name": set_name(sid), "count": n}
                for sid, n in sorted(counts.items())]
        return {"pieces": pieces, "sets": sets}

    def unit_sheet(self, actor_id: str) -> Dict[str, Any]:
        """/api/unit_sheet：C 面板聚合端点——技能 + 星魂 + 光锥 + 遗器一处取数。

        取数来源：技能=引擎 actions_by_actor + 模板 desc；星魂=角色模板 eidolons 段；
        光锥/遗器=当局 build YAML 原文（session 留底）+ 光锥/遗器模板。inline/敌人
        无模板无配置 → 各块为空（前端显示"无数据"/"无"）。
        """
        ctl = self._require_ctl()
        aid = self.resolve_actor(actor_id)
        member = build_team_member(self.build_yaml, aid)
        tpl = template_doc("characters", aid)
        return {
            "actor_id": aid,
            "name": ctl.state.actors[aid].actor.name,
            "template": self._template_provenance_of(aid),  # 来源+模板文件完整路径（C 面板顶行）
            "skills": self.skill_details(aid),
            "eidolons": self._eidolon_rows(tpl, member, aid),
            "light_cone": self._light_cone_row(member),
            "relics": self._relic_rows(member),
            "sidecar": self._sidecar_source_map(aid),  # 全量来源索引（F3 状态 tab 来源展开取数）
            "xref_names": self._xref_names(aid),       # X2 可点名集合（前端【】链接化预判）
        }

    def inspect_full(self, actor_id: str) -> Dict[str, Any]:
        """/api/inspect 增强版：snapshot + effective 有效面板块 + modifier 完整明细。

        effective 用引擎 `pipeline.effective_stats` 口径（白值 + modifier flat/pct/转化/覆写，
        含光环）——与伤害结算同一份面板；modifier_detail 补 snapshot.modifiers 没有的
        名字/层数上限/stat_effects 明细（状态 tab 与徽章弹层共用）。
        """
        ctl = self._require_ctl()
        aid = self.resolve_actor(actor_id)
        data = ctl.inspect(aid)
        st = ctl.state.actors[aid]
        eff = ctl.engine.pipeline.effective_stats(st)
        data["effective"] = {
            "hp": round(float(eff["hp"]), 1),
            "atk": round(float(eff["atk"]), 1),
            "def": round(float(eff["def_"]), 1),
            "spd": round(float(eff["spd"]), 1),
            "crit_rate": round(float(eff["crit_rate"]), 4),
            "crit_dmg": round(float(eff["crit_dmg"]), 4),
            "break_effect": round(float(eff["break_effect"]), 4),
            "effect_hit": round(float(eff["effect_hit"]), 4),
            "effect_res": round(float(eff["effect_res"]), 4),
            "energy_regen": round(float(eff["energy_regen"]), 4),
            "heal_bonus": round(float(eff.get("heal_bonus", 0.0)), 4),
        }
        data["modifier_detail"] = []
        for m in st.modifiers.values():
            row = _serialize_modifier(m, ctl.state, ctl.engine.actions_by_actor,
                                      shields=st.shields)
            # F3/X1：旁车解析得到目标 ref 才可点展开（action 直查 / 显示名 name 匹配）
            resolved = self._source_resolved_id(m)
            row["expandable"] = bool(resolved)
            row["source_ref_id"] = resolved
            data["modifier_detail"].append(row)
        return data


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app(
    build_yaml: Optional[str] = None,
    stage_yaml: Optional[str] = None,
    *,
    mode: str = MODE_EXPECTED,
    seed: Optional[int] = None,
    extra_template_roots: Optional[List[str]] = None,
) -> FastAPI:
    """建 app：YAML 可空（空会话启动，稍后 /api/load 开局）。

    extra_template_roots：附加模板根（有序，优先于默认 data/sim_templates，逐实体
    first-hit-wins）——battles 查找链（preview/catalog/旁车）与引擎编译链共用同组根；
    空/None = 只查默认根（历史行为）。
    """
    set_extra_template_roots(extra_template_roots or [])
    session = WebSession()
    if build_yaml is not None and stage_yaml is not None:
        session.load(build_yaml, stage_yaml, mode, seed)
    app = FastAPI(title="翁法罗斯 · HSR_Nous 战斗调试台")

    def _busy_guard() -> None:
        if not session.lock.acquire(blocking=False):
            raise HTTPException(409, "引擎忙——有操作进行中或决策点待选择")

    async def _acquire_engine() -> None:
        """拿引擎忙闸（换局专用）：先排干旧局再等锁（最长 10s）。

        旧局若卡在决策点（step/continue 的引擎线程持锁挂起等 choose），非阻塞抢锁必
        409——load 里的 _release_pending 永远够不到（曾是死代码）。先交还编译策略
        （后续决策点不再阻塞，continue 在途也能跑完）+ 放行当前挂起点，旧线程收尾
        即放锁。无旧局 → 直接抢锁（首次 load）。
        """
        if session.ctl is not None:
            session.ctl.set_auto()       # 旧局后续决策交还编译策略（不再挂起）
            session._release_pending()   # 放行当前挂起的决策点（None=退回默认/缺省）
        if not await asyncio.to_thread(session.lock.acquire, True, 10):
            raise HTTPException(409, "引擎忙——在途操作等待 10s 未收尾")

    async def _op(fn: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """推进/回退类端点公共骨架：抢忙闸 → 后台线程跑引擎 → 附增量日志+事件。"""
        _busy_guard()
        try:
            record = await asyncio.to_thread(fn, *args, **kwargs)
            return {"record": record, "logs": session.delta_logs(), "events": session.delta_events()}
        finally:
            session.lock.release()

    @app.get("/")
    def index() -> FileResponse:
        # 调试台页面 no-store：浏览器启发式缓存会拿旧 JS 配新服务端，催生"行动条凭空消失"
        # 这类陈旧 DOM 悬案——页面每次都拿盘上新文件（本地服务，零成本）
        return FileResponse(_STATIC, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def get_state() -> Dict[str, Any]:
        return session.state_payload()

    @app.get("/api/bar")
    def get_bar(n: int = 10) -> List[Dict[str, Any]]:
        return session._require_ctl().action_bar(n)

    @app.get("/api/inspect/{actor_id}")
    def get_inspect(actor_id: str) -> Dict[str, Any]:
        try:
            return session.inspect_full(actor_id)
        except (KeyError, RuntimeError) as e:
            raise HTTPException(404, str(e))

    @app.get("/api/unit_skills/{actor_id}")
    def get_unit_skills(actor_id: str) -> List[Dict[str, Any]]:
        try:
            return session.skill_details(actor_id)
        except (KeyError, RuntimeError) as e:
            raise HTTPException(404, str(e))

    @app.get("/api/unit_sheet/{actor_id}")
    def get_unit_sheet(actor_id: str) -> Dict[str, Any]:
        try:
            return session.unit_sheet(actor_id)
        except (KeyError, RuntimeError) as e:
            raise HTTPException(404, str(e))

    @app.get("/api/xref/{actor_id}/{name}")
    def get_xref(actor_id: str, name: str) -> Dict[str, Any]:
        """X2/X3 交叉引用权威解析：【机制名】/buff 徽章点击 → 激活 modifier / 旁车条目。"""
        try:
            return session.xref_resolve(actor_id, name)
        except RuntimeError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/snapshot")
    def get_snapshot() -> Dict[str, Any]:
        try:
            return session._require_ctl().snapshot()
        except RuntimeError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/load")
    async def post_load(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        config = body.get("config")
        if config is not None:  # 配置库取局（大厅卡片[开始]）：名字 → 内嵌 YAML
            try:
                build_yaml, stage_yaml = load_battle(str(config))
            except (KeyError, ValueError) as e:
                raise HTTPException(404, str(e))
        else:
            build_yaml = str(body.get("build_yaml", ""))
            stage_yaml = str(body.get("stage_yaml", ""))
        await _acquire_engine()
        try:
            await asyncio.to_thread(
                session.load,
                build_yaml,
                stage_yaml,
                str(body.get("mode", MODE_EXPECTED)),
                body.get("seed"),
            )
        except (ValueError, KeyError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        finally:
            session.lock.release()
        # 重开后日志全量重发（前端清屏重建）；事件箱是新的（空），同帧声明 reset
        return {"record": None, "logs": session.delta_logs(), "logs_reset": True,
                "events": session.delta_events(), "events_reset": True}

    @app.post("/api/restart")
    async def post_restart() -> Dict[str, Any]:
        """B4 同配置一键重开：当局 build/stage/mode/seed 原样重载（不进配置编辑器）。"""
        if session.ctl is None:
            raise HTTPException(400, "尚未开局——无同配置可重开")
        await _acquire_engine()
        try:
            await asyncio.to_thread(
                session.load,
                session.build_yaml,
                session.stage_yaml,
                session.mode,
                session.seed,
            )
        except (ValueError, KeyError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        finally:
            session.lock.release()
        # 与 /api/load 同帧语义：日志/事件全量重发（前端清屏重建）
        return {"record": None, "logs": session.delta_logs(), "logs_reset": True,
                "events": session.delta_events(), "events_reset": True}

    # ------------------------------------------------------------------
    # 配置库（大厅）：列表 / 保存 / 删除——本体在 battles.py，此处纯转发
    # ------------------------------------------------------------------

    @app.get("/api/battles")
    def get_battles() -> List[Dict[str, Any]]:
        return list_battles()

    @app.get("/api/catalog")
    def get_catalog() -> Dict[str, List[Dict[str, Any]]]:
        """表单编辑器四张清单（characters/light_cones/relic_sets/enemies）。"""
        return battle_catalog()

    @app.post("/api/battles/assemble")
    def post_battles_assemble(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """表单 → build/stage YAML（不落库）：高级模式实时预览与[仅开始]的取数口。"""
        try:
            build_yaml, stage_yaml = assemble_form(body.get("form") or {})
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"build_yaml": build_yaml, "stage_yaml": stage_yaml}

    @app.post("/api/battles/save")
    def post_battles_save(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        try:
            if body.get("form") is not None:  # 表单形态：先组装再走原 save 逻辑
                build_yaml, stage_yaml = assemble_form(body["form"])
            else:                             # 原 YAML 字符串形态（高级模式手改/旧调用兼容）
                build_yaml = str(body.get("build_yaml", ""))
                stage_yaml = str(body.get("stage_yaml", ""))
            save_battle(
                str(body.get("name", "")),
                str(body.get("description", "")),
                build_yaml,
                stage_yaml,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/battles/delete")
    def post_battles_delete(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        try:
            delete_battle(str(body.get("name", "")))
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @app.post("/api/step")
    async def post_step() -> Dict[str, Any]:
        try:
            return await _op(session._require_ctl().step_turn)
        except RuntimeError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/continue")
    async def post_continue(body: Optional[Dict[str, Any]] = Body(None)) -> Dict[str, Any]:
        max_steps = int((body or {}).get("max_steps", 10000))
        try:
            return await _op(session._require_ctl().continue_, max_steps)
        except RuntimeError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/break")
    def post_break(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        ctl = session._require_ctl()
        kind, value = body.get("kind"), body.get("value")
        if kind == "turn":
            ctl.break_on_turn(int(value))
        elif kind == "actor":
            ctl.break_on_actor(session.resolve_actor(str(value)))
        else:
            raise HTTPException(400, f"未知断点类型 {kind!r}（turn/actor）")
        return {"ok": True}

    @app.post("/api/clear_breaks")
    def post_clear_breaks() -> Dict[str, Any]:
        session._require_ctl().clear_breaks()
        return {"ok": True}

    @app.post("/api/back")
    async def post_back(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        session.reset_events()  # 先清箱：重放段事件在 back 内重灌（见 reset_events）
        try:
            result = await _op(session._require_ctl().back, int(body.get("n", 1)))
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        # 回退后日志被截断：前端清屏，全量重发当前日志；事件箱同理——_op 带回的 events
        # 即重放重灌后的全量（单游标，不得再 delta 二次排空），只补 reset 标记
        result.update({"logs": list(session._require_ctl().state.log), "logs_reset": True,
                       "events_reset": True})
        session._log_cursor = len(session._require_ctl().state.log)
        return result

    @app.post("/api/goto")
    async def post_goto(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        session.reset_events()
        try:
            result = await _op(session._require_ctl().goto_turn, int(body["n"]))
        except (KeyError, ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        result.update({"logs": list(session._require_ctl().state.log), "logs_reset": True,
                       "events_reset": True})
        session._log_cursor = len(session._require_ctl().state.log)
        return result

    @app.post("/api/mode")
    def post_mode(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        session._require_ctl()
        mode_req = body.get("mode")
        if mode_req == "manual":
            session.set_manual()
        elif mode_req == "auto":
            session.set_auto()
        else:
            raise HTTPException(400, f"未知决策模式 {mode_req!r}（manual/auto）")
        return {"ok": True, "manual": session.manual}

    @app.post("/api/choose")
    def post_choose(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        """三阶段共用入口：{index} 喂行动阶段；{actor_id} 按当前阶段喂目标/终结技
        （ultimate 阶段额外接受 "skip"=本窗口不放）；{ult_now} 行动决策点插队终结技
        （瞄准中随时开大，游戏同款）；阶段不符 400。"""
        try:
            if body.get("ult_now") is not None:
                session.choose_ultimate_now(str(body["ult_now"]))
            elif body.get("actor_id") is not None:
                token = str(body["actor_id"])
                phase = (session.pending or {}).get("phase")
                if phase == "target":
                    session.choose_target(token)
                elif phase == "ultimate":
                    session.choose_ultimate(token)
                else:
                    raise RuntimeError("当前不在目标/终结技决策点")
            elif body.get("index") is not None:
                session.choose_action(int(body["index"]))
            else:
                raise HTTPException(400, "choose 需要 index（行动阶段）或 actor_id（目标/终结技阶段）或 ult_now")
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    return app


def run_server(app: FastAPI, port: int) -> None:
    """uvicorn 起服务（独立函数便于 CLI 延迟 import uvicorn）。"""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
