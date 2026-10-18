"""蒙特卡洛实验层：N 种子 × N 世界线 → 结果记录 / 指标聚合 / 事件级 CSV / 版本绑定指纹.

用途：把"这个配队/策略的方差有多大、能不能 0T、会不会团灭"从感觉变成数字。
铁律：每局从工厂完整重建（纯净不变量），绝复用引擎实例；
     seed 逐局递增（seed0+i），同 seed0 两趟聚合逐字段全等；
     truncated（撞 MAX_TURNS_SAFETY 没打完）的局只计数不进样本/比率分母（毒数据防线）。

四件输出（2026-10-12 落地）：

1. **结果分类器**（`classify_outcome` → `OutcomeRecord`）：每局终态纯读取分类，不进
   结算路径（引擎 run() 后调用）。outcome 三态镜像引擎 `_should_terminate` 通则分支序——
   我方全灭（存活在场口径，放逐不算死）= `"loss"` 先于对面全灭 = `"win"`；其余收尾
   （AV 预算耗尽 / 轮次上限 / 截断）= `"timeout"`。cycles_used 用引擎轮次口径
   （`state.cycle_index`，1 起——首轮内终结即 0T 评分基础，BattleState.snapshot
   `cycles_used` 同口径）；无轮次配置（encounter.cycle=None）时 `cycle_enabled=False`，
   `zero_cycle_kill` 恒 False（记录注明，不脑补）。
2. **指标族**（`run` 聚合 summary）：`win_rate` / `wipe_rate`（我方团灭比例）/
   `zero_cycle_kill_rate` / `stable_clear_rate` / `total_damage` 分布（DistributionStats，
   保留 v0.8 口径）/ `cvar`（下尾 CVaR，p 可配缺省 0.05）/ 能量循环（`ult_casts_mean`
   每局终结技施放总次数均值、`energy_gain_per_action_mean` 平均每动能量获得均值）/
   `caveats`（本队近似/未决语义清单，纯元数据随结果附带，近似显形不藏）。
   生存测试（survival 模式）的"存活率"派生 = 1 − wipe_rate，不另立键。
3. **事件级 CSV**（可选开关）：每事件一行，列 = trial_id, run_id, clock, actor,
   action_id, action_type, target, value, event_type（口径头注随文件写清）。
   开关两路：`run(..., csv_path=...)` 参数优先，环境变量 `HSR_NOUS_MC_CSV`（文件路径）兜底。
4. **版本绑定指纹**（`collect_version_fingerprint`）：实验记录 / CSV 头 / summary 同携
   `{git_commit, rulebook_hash, fixtures_hash, data_hash, policy_hash}`——全部现算，
   不落盘手写值（取法见函数 docstring）；trial_id 缺省由指纹派生（同输入同 trial）。

能量循环口径：探针（`RunRecorder`）在 engine.setup() 之后、run() 之前挂总线——订阅序
在编译钩之后，on_gain_energy waterfall 读到的是 hook 改写后终值（ERR/上限截断前的
名义获得量）；`energy_gained` = 我方战斗员该值合计（初始布能 reason="initial_energy"
不计——布能非循环，且布能窗口在 setup 内、探针尚未挂，天然不见）；
`energy_gain_per_action` = energy_gained / 我方战斗员 on_action 计数（含终结技——
on_action 双发机制之行动半；0 动 → 0.0）。我方战斗员 = 非敌方、非召唤物、无系统排除
标记（忆灵/系统单位不进能量循环口径——与 classify_outcome 名册同集）。
"""
from __future__ import annotations

import csv as _csv_mod
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from hsr_nous.common.paths import repo_root
from hsr_nous.sim.engine import _ALLY_EXCLUDE_FLAGS, CombatEngine
from hsr_nous.sim.state import BattleState
from hsr_nous.sim_schema import rulebook as _rulebook_mod
from hsr_nous.sim_schema.templates import RUNTIME_TEMPLATE_ROOT_SPECS, data_root

#: CSV 开关环境变量（run 的 csv_path 参数优先；值为输出文件路径）
_CSV_ENV_VAR = "HSR_NOUS_MC_CSV"

#: CSV 列（口径头注见 _csv_header_lines；字段可微调但头注同步——单一来源就近维护）
_CSV_COLUMNS = ["trial_id", "run_id", "clock", "actor", "action_id",
                "action_type", "target", "value", "event_type"]

#: data 指纹锚定文件（starrailres index_new/cn 核心实体表——机制数值由 fixtures/rulebook
#: 两键覆盖，本组钉白值/基础数据版本；集合唯一事实源即本表，增删改这里）
_DATA_CORE_FILES = ("characters.json", "light_cones.json", "relics.json")


# ---------------------------------------------------------------------------
# v0.8 分布统计（保留——run_distribution 消费）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DistributionStats:
    """N 局 total_damage 的分布摘要（truncated 截断局只计数不进样本——毒数据防线）."""

    n: int
    mean: float
    stdev: float
    minimum: float
    p5: float
    p50: float
    p95: float
    maximum: float
    n_truncated: int = 0  # 撞兜底上限被截断的局数（未计入均值/分位数）

    def summary(self) -> str:
        return (
            f"n={self.n} mean={self.mean:,.0f} σ={self.stdev:,.0f} "
            f"[p5={self.p5:,.0f} p50={self.p50:,.0f} p95={self.p95:,.0f}]"
            + (f" truncated={self.n_truncated}" if self.n_truncated else "")
        )


def _percentile(sorted_vals: List[float], q: float) -> float:
    """线性插值分位数（q ∈ [0,1]；sorted_vals 已升序）."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def summarize(values: List[float]) -> DistributionStats:
    """原始样本 → 分布摘要（纯函数，可单测）."""
    assert values, "样本不能为空"
    vals = sorted(values)
    n = len(vals)
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return DistributionStats(
        n=n, mean=mean, stdev=var ** 0.5,
        minimum=vals[0], p5=_percentile(vals, 0.05),
        p50=_percentile(vals, 0.50), p95=_percentile(vals, 0.95),
        maximum=vals[-1],
    )


def cvar(values: List[float], p: float = 0.05) -> float:
    """下尾 CVaR（p 尾部分位均值，纯函数）：升序取前 k=max(1, floor(p×n)) 个样本求均值.

    total_damage 语境下 = 最差 p 尾的平均伤害（≤VaR_p 的尾部条件均值，风险口径——
    均值好看但尾局拉胯的配队在本指标下显形）。
    """
    assert values, "样本不能为空"
    if not (0.0 < p <= 1.0):
        raise ValueError(f"cvar 的 p 必须 ∈ (0, 1]，实得 {p!r}")
    vals = sorted(values)
    k = max(1, int(p * len(vals)))
    return sum(vals[:k]) / k


def run_distribution(
    engine_factory: Callable[[int], CombatEngine],
    n: int = 100,
    *,
    seed0: int = 0,
) -> DistributionStats:
    """跑 N 局聚合 total_damage 分布.

    engine_factory(seed) 必须返回**全新**引擎（每局从编译产物重建）；
    引擎内部 seed 由工厂按入参设置——聚合器只管发 seed，不管引擎内部怎么用。

    truncated（撞 MAX_TURNS_SAFETY 没打完）的局**不进样本**（均值/分位数只统计
    完整局），单独计入返回值的 n_truncated——截断局是毒数据，不得当合法优化样本。
    """
    samples: List[float] = []
    n_truncated = 0
    for i in range(n):
        engine = engine_factory(seed0 + i)
        state: BattleState = engine.run()
        if state.truncated:
            n_truncated += 1
            continue
        samples.append(state.total_damage)
    if not samples:
        raise ValueError(
            f"N={n} 局全部 truncated（撞兜底上限没打完），无完整局可统计——"
            "先排查死循环/不可终止配置再聚合"
        )
    stats = summarize(samples)
    return DistributionStats(
        n=stats.n, mean=stats.mean, stdev=stats.stdev, minimum=stats.minimum,
        p5=stats.p5, p50=stats.p50, p95=stats.p95, maximum=stats.maximum,
        n_truncated=n_truncated,
    )


# ---------------------------------------------------------------------------
# 结果分类器（OutcomeRecord）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OutcomeRecord:
    """单世界线终局结果记录（引擎 run() 后由 classify_outcome 纯读取生成）.

    - outcome：`"win"`（对面全灭）/ `"loss"`（我方团灭——存活在场口径，放逐不算死；
      双亡同帧镜像引擎分支序判 loss）/ `"timeout"`（AV 预算/轮次上限/截断收尾）
    - cycles_used：引擎轮次口径（cycle_index，1 起；无轮次配置恒 1——配合 cycle_enabled 读）
    - cycle_enabled：是否配置轮次（False → zero_cycle_kill 恒 False，0T 无定义不脑补）
    - allies_alive：存活我方战斗员数（非敌方/非召唤物/无系统排除标记；放逐=存活计入——
      放逐不是死亡；与 loss 判定的"存活在场"口径差见模块 docstring）
    - enemies_alive：存活敌人数
    - zero_cycle_kill：首轮（cycle_index==1，0T）内对面全灭
    - stable_clear：对面全灭且我方零减员（无战斗员阵亡）
    - truncated：撞 MAX_TURNS_SAFETY 截断（毒数据——聚合层只计数不进比率分母）
    - ult_casts / energy_gained / energy_gain_per_action：能量循环三键（口径见模块 docstring）
    """

    outcome: str
    cycles_used: int
    cycle_enabled: bool
    allies_alive: int
    enemies_alive: int
    total_damage: float
    zero_cycle_kill: bool
    stable_clear: bool
    truncated: bool
    seed: int
    ult_casts: int = 0
    energy_gained: float = 0.0
    energy_gain_per_action: float = 0.0


def classify_outcome(
    engine: CombatEngine,
    *,
    seed: int = 0,
    ult_casts: int = 0,
    energy_gained: float = 0.0,
    ally_actions: int = 0,
) -> OutcomeRecord:
    """战斗终局 → 结果记录（纯读取终态，不侵入主循环——引擎 run() 返回后调用）.

    能量循环三键与 seed 由调用方传入（run() 内 RunRecorder/世界线号现算）；直调缺省 0。
    """
    state = engine.state
    # 判定镜像引擎 _should_terminate 通则分支序（我方全灭先于对面全灭——双亡同帧判 loss）
    if state.truncated:
        outcome = "timeout"
    elif not engine._allies_alive():
        outcome = "loss"
    elif not engine._enemies_alive():
        outcome = "win"
    else:
        outcome = "timeout"
    # 我方战斗员名册（零减员/存活数口径）：非敌方、非召唤物、无系统排除标记
    roster = [s for s in state.actors.values()
              if not engine._is_enemy(s.actor)
              and not s.actor.summoner_id
              and not (s.actor.system_flags & _ALLY_EXCLUDE_FLAGS)]
    ally_deaths = sum(1 for s in roster if not s.alive)
    cycle_enabled = engine.encounter.cycle is not None
    cycles_used = int(state.cycle_index)
    zero_cycle_kill = bool(cycle_enabled and outcome == "win" and cycles_used == 1)
    return OutcomeRecord(
        outcome=outcome,
        cycles_used=cycles_used,
        cycle_enabled=cycle_enabled,
        allies_alive=sum(1 for s in roster if s.alive),
        enemies_alive=len(engine._enemies_alive()),
        total_damage=float(state.total_damage),
        zero_cycle_kill=zero_cycle_kill,
        stable_clear=bool(outcome == "win" and ally_deaths == 0),
        truncated=bool(state.truncated),
        seed=int(seed),
        ult_casts=int(ult_casts),
        energy_gained=float(energy_gained),
        energy_gain_per_action=(float(energy_gained) / ally_actions) if ally_actions > 0 else 0.0,
    )


# ---------------------------------------------------------------------------
# 版本绑定指纹
# ---------------------------------------------------------------------------

def _git_commit() -> Optional[str]:
    """git rev-parse HEAD（subprocess 现算；非 git 环境/无 git 二进制/超时 → None 容错）."""
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root()),
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _sha256_file(path: Path) -> Optional[str]:
    """单文件内容 sha256（缺文件 → None）."""
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_hash(roots: List[tuple], suffixes: tuple) -> Optional[str]:
    """多根目录树内容指纹：根名/相对路径（排序）+ 文件字节链式并入 sha256；全缺 → None."""
    h = hashlib.sha256()
    n = 0
    for label, root in roots:
        if not root.is_dir():
            continue
        for p in sorted(q for q in root.rglob("*") if q.is_file() and q.suffix in suffixes):
            h.update(f"{label}/{p.relative_to(root)}".encode("utf-8"))
            h.update(p.read_bytes())
            n += 1
    return h.hexdigest() if n else None


def _data_hash() -> Optional[str]:
    """starrailres 核心实体表（`_DATA_CORE_FILES`）内容指纹：文件名 + 字节链式 sha256；
    缺文件跳过，全缺（数据 gitignored 未下载）→ None."""
    base = data_root() / "starrailres" / "index_new" / "cn"
    h = hashlib.sha256()
    n = 0
    for name in _DATA_CORE_FILES:
        p = base / name
        if not p.is_file():
            continue
        h.update(name.encode("utf-8"))
        h.update(p.read_bytes())
        n += 1
    return h.hexdigest() if n else None


def collect_version_fingerprint(*, policy_source: Optional[str] = None) -> Dict[str, Any]:
    """实验版本绑定指纹（五键，全部现算——不落盘手写值；单项不可得 → None 不炸实验）.

    - `git_commit`：`git rev-parse HEAD`（subprocess，仓库根；非 git 环境容错 None）
    - `rulebook_hash`：`sim_schema/rulebook.yaml` 内容 sha256（公式/常量唯一来源）
    - `fixtures_hash`：引用模板全集内容指纹——RUNTIME_TEMPLATE_ROOTS
      （data/library 正典 + data/sim_templates 兜底）下全部 YAML 链式 sha256
      （opaque 工厂无法反查实际引用集，取可引用全集为保守超集；根全缺 → None）
    - `data_hash`：starrailres 核心实体表（`_DATA_CORE_FILES`：characters/light_cones/
      relics.json，index_new/cn）内容指纹（数据未下载 → None）
    - `policy_hash`：`policy_source` 文本 sha256——调用方把 build policy 块原文（或任何
      能标识策略的文本）传入；未传 → None
    """
    return {
        "git_commit": _git_commit(),
        "rulebook_hash": _sha256_file(
            Path(_rulebook_mod.__file__).resolve().parent / "rulebook.yaml"),
        "fixtures_hash": _tree_hash(
            [(label, Path(path)) for label, path in RUNTIME_TEMPLATE_ROOT_SPECS],
            (".yaml", ".yml")),
        "data_hash": _data_hash(),
        "policy_hash": (hashlib.sha256(policy_source.encode("utf-8")).hexdigest()
                        if policy_source is not None else None),
    }


def _default_trial_id(version: Dict[str, Any]) -> str:
    """trial_id 缺省派生：版本指纹 canonical JSON 的 sha256 短码（同输入同 trial——可复现实验身份）."""
    digest = hashlib.sha256(
        json.dumps(version, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return f"mc-{digest[:12]}"


# ---------------------------------------------------------------------------
# 单世界线记录器（总线探针：能量循环计数 + 可选 CSV 事件行）
# ---------------------------------------------------------------------------

class RunRecorder:
    """单世界线记录器：挂总线收能量循环三键；挂接即录、被动只读（同 StructuredLogger 纪律——
    条目全部派生自总线事件，不进结算路径，确定性零影响）.

    挂接点位 = engine.setup() 之后、run() 之前——订阅序在编译钩之后，on_gain_energy
    waterfall 读到的是 hook 改写后终值（ERR/上限截断前的名义获得量）。
    计数口径：ult_casts=我方战斗员 on_ultimate 数；energy_gained=我方战斗员 waterfall
    amount 合计（reason="initial_energy" 初始布能不计——布能非循环，且布能在 setup 内
    天然不见）；ally_actions=我方战斗员 on_action 数（含终结技——on_action 双发机制之行动半；
    我方战斗员 = 非敌方、非召唤物、无系统排除标记——与 classify_outcome 名册同集）。
    """

    def __init__(self, engine: CombatEngine, *,
                 csv_writer: Any = None, trial_id: str = "", run_id: int = 0) -> None:
        self._engine = engine
        self._csv = csv_writer
        self._trial_id = trial_id
        self._run_id = run_id
        self.ult_casts = 0
        self.energy_gained = 0.0
        self.ally_actions = 0
        bus = engine.bus
        bus.subscribe("on_action", self._on_action)
        bus.subscribe("on_ultimate", self._on_ultimate)
        bus.subscribe_waterfall("on_gain_energy", self._wf_energy)
        if csv_writer is not None:
            bus.subscribe("after_being_hit", self._on_hit)
            bus.subscribe("on_hp_increase", self._on_heal)
            bus.subscribe("on_kill", self._on_kill)
            bus.subscribe("actor_exit", self._on_exit)
            bus.subscribe("on_cycle_start", self._on_cycle_start)
            bus.subscribe("battle_end", self._on_battle_end)

    def _is_ally(self, aid: Any) -> bool:
        # 我方战斗员口径（与 classify_outcome 名册同集：非敌方、非召唤物、无系统排除
        # 标记——忆灵/阿哈系统单位的行动不计入能量循环分母、其能量事件不计入分子）
        st = self._engine.state.actors.get(str(aid))
        return (st is not None
                and not self._engine._is_enemy(st.actor)
                and not st.actor.summoner_id
                and not (st.actor.system_flags & _ALLY_EXCLUDE_FLAGS))

    def _row(self, event_type: str, *, actor: Any = "", action_id: Any = "",
             action_type: Any = "", target: Any = "", value: Any = "") -> None:
        if self._csv is None:
            return
        self._csv.writerow([
            self._trial_id, self._run_id, round(float(self._engine.state.clock), 1),
            actor or "", action_id or "", action_type or "", target or "", value, event_type])

    # ---- 计数通道（CSV 行同挂） ----

    def _on_action(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        if self._is_ally(p.get("actor")):
            self.ally_actions += 1
        self._row("action", actor=p.get("actor"), action_id=p.get("action_id"),
                  action_type=p.get("action_type"), target=p.get("target"),
                  value=p.get("sp_consumed", 0))

    def _on_ultimate(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        if self._is_ally(p.get("source")):
            self.ult_casts += 1
        self._row("ultimate", actor=p.get("source"), action_id=p.get("action"),
                  action_type="ultimate", target=p.get("target"))

    def _wf_energy(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        if not p.get("cancel") and self._is_ally(p.get("actor")):
            amount = float(p.get("amount", 0.0))
            if p.get("reason") != "initial_energy" and amount > 0:
                self.energy_gained += amount
            # CSV 只记我方获得（敌方能量经济空转——max_energy 0 的名义事件不掺记录面）
            self._row("energy_gain", actor=p.get("actor"), action_id=p.get("action_id"),
                      action_type=p.get("reason"), value=round(amount, 1))
        return None

    # ---- CSV 纯记录通道 ----

    def _on_hit(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        self._row("damage", actor=p.get("source"), action_type=p.get("damage_type"),
                  target=p.get("target"), value=round(float(p.get("amount", 0.0)), 1))

    def _on_heal(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        self._row("heal", actor=p.get("source"), target=p.get("target"),
                  value=round(float(p.get("amount", 0.0)), 1))

    def _on_kill(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        self._row("kill", actor=p.get("source"), target=p.get("target"))

    def _on_exit(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        if p.get("reason") == "death":
            self._row("death", actor=p.get("actor"))

    def _on_cycle_start(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        self._row("cycle_start", value=p.get("cycle_index"))

    def _on_battle_end(self, et: str, p: Dict[str, Any], ctx: Any) -> None:
        self._row("battle_end", value=p.get("reason"))


_RunRecorder = RunRecorder


def _csv_header_lines(trial_id: str, version: Dict[str, Any]) -> List[str]:
    """CSV 头注（# 注释行——口径与版本绑定随文件自描述；列释义改列时同步）."""
    return [
        "# hsr_nous 蒙特卡洛事件级 CSV（实验输出四件之一）",
        f"# trial_id: {trial_id}",
        f"# version: {json.dumps(version, sort_keys=True, ensure_ascii=False)}",
        "# 列口径: trial_id=实验 id（版本指纹派生或显式）; run_id=世界线种子（seed0+i）; "
        "clock=事件时刻 AV; actor=行为者 actor_id; action_id=行动/终结技 id; "
        "action_type=行动类别（energy_gain 行=获得原因 reason）; target=主目标 actor_id; "
        "value=数值（释义按 event_type 见下）; event_type=事件词表",
        "# event_type 词表与 value 释义: action=行动施放（value=实际耗点 sp_consumed）; "
        "ultimate=终结技施放; damage=命中（value=伤害量, action_type=伤害属性）; "
        "heal=治疗（value=治疗量）; energy_gain=我方能量获得（value=hook 改写后/ERR 前名义量）; "
        "kill=击杀; death=死亡; cycle_start=轮次开始（value=轮次号）; "
        "battle_end=战斗终止（value=终止原因）",
    ]


# ---------------------------------------------------------------------------
# 实验入口
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExperimentResult:
    """蒙特卡洛实验产出：outcomes（逐世界线结果记录）+ summary（聚合键）+ 版本指纹."""

    trial_id: str
    version: Dict[str, Any]
    outcomes: List[OutcomeRecord]
    summary: Dict[str, Any]
    csv_path: Optional[str] = None


def run(
    engine_factory: Callable[[int], CombatEngine],
    n: int = 100,
    *,
    seed0: int = 0,
    cvar_p: float = 0.05,
    csv_path: Optional[Union[str, Path]] = None,
    trial_id: Optional[str] = None,
    policy_source: Optional[str] = None,
) -> ExperimentResult:
    """跑 N 局蒙特卡洛实验 → ExperimentResult（outcomes + summary + 版本指纹 + 可选 CSV）.

    engine_factory(seed) 必须返回**全新**引擎（同 run_distribution 契约；setup 幂等
    由本函数保证——记录器挂接点位在编译钩之后）。truncated 局只计 n_truncated、不进样本
    与比率分母（毒数据防线，与 run_distribution 同口径）；全部 truncated → ValueError。

    summary 聚合键：version（版本指纹——实验记录/CSV 头/summary 三载体同携）/ n /
    n_truncated / win_rate / wipe_rate / zero_cycle_kill_rate / stable_clear_rate /
    total_damage（DistributionStats）/ cvar / cvar_p /
    ult_casts_mean / energy_gain_per_action_mean（口径全见模块 docstring）/
    caveats（近似置信度通道——本队 caveats 聚合清单，取自引擎携带的
    CompiledEncounter.caveats：条目 {actor, text, level: approx|pending, source}；
    **纯元数据，不进结算不改数值**——总伤旁的"本结果含哪些近似/未决语义"显形件）。
    """
    if not (0.0 < cvar_p <= 1.0):
        raise ValueError(f"run 的 cvar_p 必须 ∈ (0, 1]，实得 {cvar_p!r}")
    version = collect_version_fingerprint(policy_source=policy_source)
    trial = trial_id or _default_trial_id(version)
    csv_target: Optional[str] = (str(csv_path) if csv_path is not None
                                 else os.environ.get(_CSV_ENV_VAR) or None)
    outcomes: List[OutcomeRecord] = []
    samples: List[float] = []
    n_truncated = 0
    caveats: List[Dict[str, Any]] = []
    fh = None
    writer = None
    if csv_target:
        fh = open(csv_target, "w", newline="", encoding="utf-8")
        writer = _csv_mod.writer(fh)
        for line in _csv_header_lines(trial, version):
            fh.write(line + "\n")
        writer.writerow(_CSV_COLUMNS)
    try:
        for i in range(n):
            seed = seed0 + i
            engine = engine_factory(seed)
            if i == 0:
                # caveats 是 encounter 级元数据（同 factory 各局同一份），取首局携带即可
                caveats = [dict(c) for c in getattr(engine, "caveats", [])]
            engine.setup()  # 幂等——保证记录器挂在编译钩之后（waterfall 读 hook 改写终值）
            recorder = RunRecorder(engine, csv_writer=writer, trial_id=trial, run_id=seed)
            engine.run()
            rec = classify_outcome(engine, seed=seed, ult_casts=recorder.ult_casts,
                                   energy_gained=recorder.energy_gained,
                                   ally_actions=recorder.ally_actions)
            outcomes.append(rec)
            if rec.truncated:
                n_truncated += 1
                continue
            samples.append(rec.total_damage)
    finally:
        if fh is not None:
            fh.close()
    completed = [r for r in outcomes if not r.truncated]
    if not completed:
        raise ValueError(
            f"N={n} 局全部 truncated（撞兜底上限没打完），无完整局可统计——"
            "先排查死循环/不可终止配置再聚合"
        )
    m = len(completed)
    summary: Dict[str, Any] = {
        "version": version,  # 版本绑定指纹随 summary 同携（实验记录/CSV 头/summary 三载体）
        "n": m,
        "n_truncated": n_truncated,
        "win_rate": sum(1 for r in completed if r.outcome == "win") / m,
        "wipe_rate": sum(1 for r in completed if r.outcome == "loss") / m,
        "zero_cycle_kill_rate": sum(1 for r in completed if r.zero_cycle_kill) / m,
        "stable_clear_rate": sum(1 for r in completed if r.stable_clear) / m,
        "total_damage": summarize(samples),
        "cvar": cvar(samples, cvar_p),
        "cvar_p": cvar_p,
        "ult_casts_mean": sum(r.ult_casts for r in completed) / m,
        "energy_gain_per_action_mean": sum(r.energy_gain_per_action for r in completed) / m,
        "caveats": caveats,  # 近似置信度通道（纯元数据——总伤旁的近似/未决语义清单）
    }
    return ExperimentResult(
        trial_id=trial, version=version, outcomes=outcomes, summary=summary,
        csv_path=csv_target,
    )
