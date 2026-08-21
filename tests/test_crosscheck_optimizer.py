"""对拍（BACKLOG B22）：hsr-optimizer TS 伤害计算器 vs 我方 SettlementPipeline.

裁判：`external/hsr-optimizer` 的 CritDamageFunction / BreakDamageFunction，
经 `scripts/crosscheck/crosscheck.mts` 驱动（rolldown 打包成 dist/crosscheck.mjs 后 node 执行）。
同一场景两边各算一次，rel_tol=1e-4 比对；直伤乘区（def/res/crit/base_universal）
同步做节点级比对。

环境兜底：缺 node 或缺 optimizer 依赖时整模块 skip（不判红）。
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

import pytest

from hsr_nous.sim.pipeline import MODE_EXPECTED, SettlementPipeline
from hsr_nous.sim.state import ActorState
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock

ROOT = Path(__file__).resolve().parents[1]
DRIVER_SRC = ROOT / "scripts" / "crosscheck" / "crosscheck.mts"
DRIVER_DIST = ROOT / "scripts" / "crosscheck" / "dist" / "crosscheck.mjs"
ROLLDOWN = ROOT / "external" / "hsr-optimizer" / "node_modules" / ".bin" / "rolldown"
ROLLDOWN_CONFIG = ROOT / "scripts" / "crosscheck" / "rolldown.config.mjs"

REL_TOL = 1e-4


@pytest.fixture(scope="session")
def optimizer_driver() -> Path:
    """确保驱动 bundle 存在（源码更新则重打）；缺环境则整模块 skip."""
    if shutil.which("node") is None:
        pytest.skip("node 不可用，跳过 optimizer 对拍")
    if not ROLLDOWN.exists():
        pytest.skip("external/hsr-optimizer 依赖未安装（无 rolldown），跳过对拍")
    if (not DRIVER_DIST.exists()
            or DRIVER_DIST.stat().st_mtime < DRIVER_SRC.stat().st_mtime):
        subprocess.run(
            [str(ROLLDOWN), "-c", str(ROLLDOWN_CONFIG)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
    return DRIVER_DIST


def run_optimizer(driver: Path, scenario: Dict[str, Any]) -> Dict[str, Any]:
    """node 子进程跑驱动，拿 {damage, breakdown}."""
    proc = subprocess.run(
        ["node", str(driver)],
        input=json.dumps(scenario), capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# 直伤（Crit）：同场景双方数值 + 乘区节点比对
# ---------------------------------------------------------------------------

# (场景名, 攻击方面板, 元素, optimizer 侧敌方抗性, 我方侧是否弱点, 手算基准)
CRIT_SCENARIOS = [
    ("hand_calc_baseline", {"atk": 2000.0, "crit_rate": 0.5, "crit_dmg": 1.0},
     "thunder", 0.0, True, 1350.0),
    ("non_weakness_res", {"atk": 2000.0, "crit_rate": 0.5, "crit_dmg": 1.0},
     "thunder", 0.2, False, 1080.0),
    ("high_def_pen", {"atk": 2000.0, "crit_rate": 0.5, "crit_dmg": 1.0, "def_pen": 0.8},
     "thunder", 0.0, True, 2250.0),
]


def _ours_crit(atk_kw: Dict[str, float], element: str, weak: bool) -> Any:
    attacker = Actor(actor_id="atk", name="攻", level=80, stats=StatBlock(**atk_kw))
    target = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                   stats=StatBlock(weakness=[element] if weak else ["fire"]))
    action = Action(action_id="a1", name="普攻", action_type="basic",
                    target_type="single", damage_type=element, scaling=[{"atk": 1.0}])
    return SettlementPipeline(mode=MODE_EXPECTED).deal_damage(action, attacker, target)


def _optimizer_crit_scenario(atk_kw: Dict[str, float], element: str,
                             enemy_res: float) -> Dict[str, Any]:
    return {
        "kind": "crit",
        "element": element,
        "attacker": {
            "level": 80,
            "atk": atk_kw.get("atk", 0.0),
            "cr": atk_kw.get("crit_rate", 0.0),
            "cd": atk_kw.get("crit_dmg", 0.0),
            "def_pen": atk_kw.get("def_pen", 0.0),
        },
        "hit": {"atk_scaling": 1.0},
        "enemy": {"level": 80, "damage_resistance": enemy_res, "weakness_broken": False},
    }


class TestCritDuipai:
    @pytest.mark.parametrize(
        "name,atk_kw,element,enemy_res,weak,hand",
        CRIT_SCENARIOS,
        ids=[s[0] for s in CRIT_SCENARIOS],
    )
    def test_damage_matches(self, optimizer_driver, name, atk_kw, element,
                            enemy_res, weak, hand):
        ours = _ours_crit(atk_kw, element, weak)
        theirs = run_optimizer(optimizer_driver,
                               _optimizer_crit_scenario(atk_kw, element, enemy_res))

        # 双锚：手算基准 + 双方互对（rel_tol 1e-4）
        assert math.isclose(ours.value, hand, rel_tol=REL_TOL), f"{name} 我方 vs 手算"
        assert math.isclose(theirs["damage"], hand, rel_tol=REL_TOL), f"{name} optimizer vs 手算"
        assert math.isclose(ours.value, theirs["damage"], rel_tol=REL_TOL), f"{name} 双方互对"

        # 乘区节点级比对（对拍显微镜）
        bd = theirs["breakdown"]
        for node_key in ("defMulti", "resMulti", "critMulti", "baseUniversalMulti",
                         "dmgBoostMulti", "abilityMulti"):
            assert math.isclose(ours.node[node_key], bd[node_key], rel_tol=REL_TOL), \
                f"{name} 乘区 {node_key}: 我方 {ours.node[node_key]} vs optimizer {bd[node_key]}"


# ---------------------------------------------------------------------------
# 击破（Break）：已核实的公式差——韧性除数 /40（我方，fandom 口径）vs /120（optimizer）。
# 不测相等，测"差值恰为文档记录的倍数"，任一侧公式改动都会触红。
# ---------------------------------------------------------------------------

class TestBreakKnownDivergence:
    def test_toughness_divisor_divergence(self, optimizer_driver):
        """BE=1.0 火，精英 maxToughness=120，lvl80 vs lvl80，已击破，0 抗性.

        我方：3767.5533 × (0.5 + 120/40) × 2 × 0.5 = 13186.4366（toughness/40）
        对方：3767.5533 × (0.5 + 120/120) × 2 × 0.5 = 5651.32995（toughness/120）
        比值恰为 3.5/1.5 = 7/3 ≈ 2.3333。
        """
        source = Actor(actor_id="atk", name="攻", level=80,
                       stats=StatBlock(break_effect=1.0))
        target_actor = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                             stats=StatBlock(weakness=["fire"], max_toughness=120.0))
        target = ActorState(actor=target_actor, current_hp=1e9, broken=True)
        ours = SettlementPipeline(mode=MODE_EXPECTED).break_damage(source, target, "fire")

        theirs = run_optimizer(optimizer_driver, {
            "kind": "break",
            "element": "fire",
            "attacker": {"level": 80, "be": 1.0},
            "enemy": {"level": 80, "max_toughness": 120,
                      "damage_resistance": 0.0, "weakness_broken": True},
            "break": {"element_scaling": 1.0},
        })

        assert math.isclose(ours.value, 13186.43655, rel_tol=REL_TOL)
        assert math.isclose(theirs["damage"], 5651.32995, rel_tol=REL_TOL)
        # 差值倍数核实：我方/对方 = (0.5+120/40)/(0.5+120/120) = 7/3
        assert math.isclose(ours.value / theirs["damage"], 7.0 / 3.0, rel_tol=REL_TOL)
        # 公共乘区（防御/抗性）一致——差值全部来自韧性除数
        assert math.isclose(ours.node["defMulti"], theirs["breakdown"]["defMulti"],
                            rel_tol=REL_TOL)
        assert math.isclose(ours.node["resMulti"], theirs["breakdown"]["resMulti"],
                            rel_tol=REL_TOL)


# ---------------------------------------------------------------------------
# 多目标/多段（v0.9 扩展）：我方引擎结算路径 vs optimizer 逐发之和
# ---------------------------------------------------------------------------

from hsr_nous.sim.engine import CombatEngine  # noqa: E402
from hsr_nous.sim.policy_api import ScriptedPolicy  # noqa: E402
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig  # noqa: E402


def _engine_damage(action: Action, n_enemies: int = 2) -> float:
    """我方引擎层：atk=2000 crit(0.5,1.0) spd=150 打 n 个默认假人，一动总伤."""
    attacker = Actor(actor_id="atk", name="攻", level=80,
                     stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                     crit_rate=0.5, crit_dmg=1.0))
    dummies = [Actor(actor_id=f"e{i}", name=f"敌{i}", actor_type="monster", level=80,
                     stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["thunder"]))
               for i in range(n_enemies)]
    enc = Encounter(encounter_id="t", name="t", actors=[attacker] + dummies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70.0))
    eng = CombatEngine(enc, actions_by_actor={"atk": [action]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng.run().total_damage


class TestMultiTargetDuipai:
    def test_blast_total_vs_optimizer_sum(self, optimizer_driver):
        """blast 主 1.0/副 0.5：我方引擎总伤 == optimizer（主单发 + 副单发）."""
        blast = Action(action_id="b", name="扩散", action_type="basic", target_type="blast",
                       damage_type="thunder", scaling=[{"atk": 1.0}],
                       scaling_blast=[{"atk": 0.5}], toughness_dmg=20)
        ours = _engine_damage(blast, n_enemies=2)

        base_scenario = _optimizer_crit_scenario(
            {"atk": 2000.0, "crit_rate": 0.5, "crit_dmg": 1.0}, "thunder", 0.0)
        main = run_optimizer(optimizer_driver, base_scenario)
        secondary = run_optimizer(optimizer_driver, {
            **base_scenario, "hit": {"atk_scaling": 0.5}})

        assert math.isclose(ours, main["damage"] + secondary["damage"], rel_tol=REL_TOL), (
            f"我方 blast 总伤 {ours} vs optimizer 主+副 {main['damage'] + secondary['damage']}"
        )

    def test_multihit_total_vs_optimizer_times_n(self, optimizer_driver):
        """instances=3 每段 0.5：我方引擎总伤 == optimizer 单发 × 3."""
        multi = Action(action_id="m", name="连击", action_type="basic", target_type="single",
                       damage_type="thunder", scaling=[{"atk": 0.5}], toughness_dmg=10,
                       instances=3)
        ours = _engine_damage(multi, n_enemies=1)

        scenario = _optimizer_crit_scenario(
            {"atk": 2000.0, "crit_rate": 0.5, "crit_dmg": 1.0}, "thunder", 0.0)
        scenario["hit"] = {"atk_scaling": 0.5}
        seg = run_optimizer(optimizer_driver, scenario)

        assert math.isclose(ours, seg["damage"] * 3, rel_tol=REL_TOL), (
            f"我方 3 段总伤 {ours} vs optimizer 单发×3 {seg['damage'] * 3}"
        )
