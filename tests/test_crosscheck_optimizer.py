"""对拍（BACKLOG B22）：hsr-optimizer TS 伤害计算器 vs 我方 SettlementPipeline.

裁判：`external/hsr-optimizer` 的 CritDamageFunction / BreakDamageFunction /
SuperBreakDamageFunction / ElationDamageFunction / DotDamageFunction，
经 `scripts/crosscheck/crosscheck.mts` 驱动（rolldown 打包成 dist/crosscheck.mjs 后 node 执行）。
同一场景两边各算一次，rel_tol=1e-4 比对；各伤害类别乘区同步做节点级比对。
真实结构差（击破韧性除数已结案为单位差；超击破增伤池/欢愉增伤池/DoT 独立易伤等
单边乘区）不测相等——钉"差值恰为记录值"的 divergence 测试，任一侧改动触红。

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
from hsr_nous.sim.state import ActorState, Modifier
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
        """BE=1.0 冰，精英 maxToughness=120，lvl80 vs lvl80，已击破，0 抗性.

        我方：3767.5533 × (0.5 + 120/40) × 2 × 0.5 = 13186.4366（toughness/40）
        对方：3767.5533 × (0.5 + 120/120) × 2 × 0.5 = 5651.32995（toughness/120）
        比值恰为 3.5/1.5 = 7/3 ≈ 2.3333。
        注：7/3 的成因已查明为**单位差**（客户端原始韧性点=3×显示点，raw/120≡display/40
        恒等，B19 已标"基本解决"）——本测试仍钉住两侧公式形态，任一侧改动都会触红。
        元素选冰（scaling=1.0 双侧一致），与倍率修正（fire/quantum 2026-08-22）解耦。
        """
        source = Actor(actor_id="atk", name="攻", level=80,
                       stats=StatBlock(break_effect=1.0))
        target_actor = Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                             stats=StatBlock(weakness=["ice"], max_toughness=120.0))
        target = ActorState(actor=target_actor, current_hp=1e9, broken=True)
        ours = SettlementPipeline(mode=MODE_EXPECTED).break_damage(source, target, "ice")

        theirs = run_optimizer(optimizer_driver, {
            "kind": "break",
            "element": "ice",
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
# 超击破（Super Break，B38 我方已落地）：公共子集（基数/BE/转换池/击破增伤池/
# 削韧效率/防御/抗性/易伤/韧性减伤）双方全等；我方独立「超击破增伤池」对方无键
# ——钉 divergence。口径：已击破 base_universal 恒 1.0；不暴击；不吃攻击/增伤/虚弱。
# ---------------------------------------------------------------------------

SB_BASE = 3767.5533 / 10  # rulebook super_break_base_multi 系数（双方同值——已核）


def _ours_super_break(*, be: float, conversion: float, toughness_dmg: float,
                      break_eff: float = 0.0, break_boost: float = 0.0,
                      sb_boost: float = 0.0, def_pen: float = 0.0,
                      res_pen: float = 0.0, vuln: float = 0.0,
                      element: str = "fire", weak: bool = True) -> Any:
    """我方超击破：有效削韧走 toughness_damage_amount（引擎同路径——含削韧效率池）."""
    hero = Actor(actor_id="atk", name="攻", level=80,
                 stats=StatBlock(break_effect=be, def_pen=def_pen, res_pen=res_pen,
                                 break_efficiency_boost=break_eff,
                                 dmg_bonus={"break_dmg_boost": break_boost} if break_boost else {}))
    src = ActorState(actor=hero, current_hp=hero.stats.hp)
    effs = {"super_break_modifier": conversion}
    if sb_boost:
        effs["super_break_dmg_boost"] = sb_boost
    src.modifiers["SB_CONV"] = Modifier(
        modifier_id="SB_CONV", name="超击破转化", modifier_type="buff",
        duration=0, stat_effects=effs)
    target = ActorState(
        actor=Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, weakness=[element] if weak else ["ice"],
                                    vulnerability=vuln, max_toughness=120.0)),
        current_hp=1e9, broken=True)
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    eff_toughness = pipe.toughness_damage_amount(src, toughness_dmg)
    return pipe.super_break_damage(src, target, effective_toughness=eff_toughness,
                                   damage_type=element)


def _optimizer_super_break_scenario(*, be: float, conversion: float,
                                    toughness_dmg: float, break_eff: float = 0.0,
                                    break_boost: float = 0.0, def_pen: float = 0.0,
                                    res_pen: float = 0.0, vuln: float = 0.0,
                                    element: str = "fire", enemy_res: float = 0.0) -> Dict[str, Any]:
    # break_boost 由驱动写入 **hit 层** HKey.BOOST——对方超击破增伤唯一读口
    return {
        "kind": "super_break",
        "element": element,
        "attacker": {
            "level": 80, "be": be, "super_break_modifier": conversion,
            "break_boost": break_boost, "break_efficiency_boost": break_eff,
            "def_pen": def_pen, "res_pen": res_pen, "vulnerability": vuln,
        },
        "hit": {"toughness_dmg": toughness_dmg},
        "enemy": {"level": 80, "damage_resistance": enemy_res, "weakness_broken": True},
    }


# (场景名, 双方共有 kwargs, 我方侧 weak, 对方侧 enemy_res, 手算基准)
SUPER_BREAK_SCENARIOS = [
    # 基础链：eff=30×1.0，基数 11302.6599 ×BE 2.0 ×def 0.5（火弱点/已击破）
    ("hand_calc_baseline",
     dict(be=1.0, conversion=1.0, toughness_dmg=30.0),
     True, 0.0,
     SB_BASE * 30 * 2.0 * 0.5),
    # 全面板链：削韧效率 0.5 → eff=20×1.5=30；转换 1.6；击破增伤 0.375（对方 hit 层 BOOST）；
    # def_pen 0.4 → 1000/(600+1000)=0.625；非弱点 0.2 抗 + res_pen 0.1 → 0.9；易伤 0.25
    ("full_panel",
     dict(be=1.5, conversion=1.6, toughness_dmg=20.0, break_eff=0.5,
          break_boost=0.375, def_pen=0.4, res_pen=0.1, vuln=0.25),
     False, 0.2,
     SB_BASE * 30 * 2.5 * 1.6 * 1.375 * 0.625 * 0.9 * 1.25),
]


class TestSuperBreakDuipai:
    @pytest.mark.parametrize(
        "name,kw,weak,enemy_res,hand",
        SUPER_BREAK_SCENARIOS,
        ids=[s[0] for s in SUPER_BREAK_SCENARIOS],
    )
    def test_damage_matches(self, optimizer_driver, name, kw, weak, enemy_res, hand):
        ours = _ours_super_break(**kw, weak=weak)
        theirs = run_optimizer(optimizer_driver,
                               _optimizer_super_break_scenario(**kw, enemy_res=enemy_res))

        # 双锚：手算基准 + 双方互对（rel_tol 1e-4）
        assert math.isclose(ours.value, hand, rel_tol=REL_TOL), f"{name} 我方 vs 手算"
        assert math.isclose(theirs["damage"], hand, rel_tol=REL_TOL), f"{name} optimizer vs 手算"
        assert math.isclose(ours.value, theirs["damage"], rel_tol=REL_TOL), f"{name} 双方互对"

        # 乘区节点级比对（同名直比 + 异名映射：转换池/击破增伤池）
        bd = theirs["breakdown"]
        for node_key in ("superBreakBaseMulti", "beMulti", "defMulti", "resMulti", "vulnMulti"):
            assert math.isclose(ours.node[node_key], bd[node_key], rel_tol=REL_TOL), \
                f"{name} 乘区 {node_key}: 我方 {ours.node[node_key]} vs optimizer {bd[node_key]}"
        assert math.isclose(ours.node["superBreakConversionMulti"], bd["superBreakModMulti"],
                            rel_tol=REL_TOL), f"{name} 转换倍率池"
        assert math.isclose(ours.node["breakDmgBoostMulti"], bd["dmgBoostMulti"],
                            rel_tol=REL_TOL), f"{name} 击破增伤池（对方 hit 层 BOOST）"
        assert math.isclose(ours.node["superBreakDmgBoostMulti"], 1.0, rel_tol=REL_TOL), \
            f"{name} 超击破增伤池未启用（divergence 见专测）"


class TestSuperBreakKnownDivergence:
    def test_boost_pool_divergence(self, optimizer_driver):
        """已核实的结构差——独立「超击破增伤池」：我方有乘区（忘归人 E4/乱破族，
        (1+池) 与击破增伤池乘算），对方 SuperBreakDamageFunction 无此键。
        池 0.3 → 我方恰为对方 ×1.3；其余乘区全等。"""
        kw = dict(be=1.0, conversion=1.0, toughness_dmg=30.0, sb_boost=0.3)
        ours = _ours_super_break(**kw)
        theirs = run_optimizer(optimizer_driver, _optimizer_super_break_scenario(
            be=1.0, conversion=1.0, toughness_dmg=30.0))

        base = SB_BASE * 30 * 2.0 * 0.5
        assert math.isclose(theirs["damage"], base, rel_tol=REL_TOL), "对方无该池 = 基础链值"
        assert math.isclose(ours.value, base * 1.3, rel_tol=REL_TOL)
        # 差值倍数核实：恰为 (1 + 超击破增伤池)
        assert math.isclose(ours.value / theirs["damage"], 1.3, rel_tol=REL_TOL)
        assert math.isclose(ours.node["superBreakDmgBoostMulti"], 1.3, rel_tol=REL_TOL)
        # 公共乘区一致——差值全部来自该池
        for node_key in ("superBreakBaseMulti", "beMulti", "defMulti", "resMulti"):
            assert math.isclose(ours.node[node_key], theirs["breakdown"][node_key],
                                rel_tol=REL_TOL), f"公共乘区 {node_key}"


# ---------------------------------------------------------------------------
# 欢愉伤害（Elation，B40 我方已落地）：等级系数 7535.107×纯倍率 双方同值；
# 欢愉度/笑点/好活当赏/双暴/防御/抗性/易伤/最终伤害/韧性减伤全等；**不吃通用
# 增伤**双方同构（scenario 2 高增伤面板隔离验证）。我方独立乘区 elation_dmg_boost
# （爻光族槽位）与 dmg_red（读目标减伤桶）对方无键——钉 divergence。
# ---------------------------------------------------------------------------

ELATION_BASE = 7535.107  # rulebook constants.elation_level_multiplier（对方 ELATION_BASE_DMG 同值——已核）


def _ours_elation(*, ability: float, punchline: float, elation: float = 0.0,
                  merrymake: float = 0.0, cr: float = 0.0, cd: float = 0.0,
                  def_pen: float = 0.0, res_pen: float = 0.0, vuln: float = 0.0,
                  final: float = 0.0, el_boost: float = 0.0, dmg_all: float = 0.0,
                  element_boost: float = 0.0, element: str = "fire",
                  weak: bool = True, broken: bool = False) -> Any:
    bonus: Dict[str, float] = {}
    if final:
        bonus["final_dmg_boost"] = final
    if dmg_all:
        bonus["all"] = dmg_all
    if element_boost:
        bonus[element] = element_boost
    hero = Actor(actor_id="atk", name="攻", level=80,
                 stats=StatBlock(elation=elation, crit_rate=cr, crit_dmg=cd,
                                 def_pen=def_pen, res_pen=res_pen, dmg_bonus=bonus))
    src = ActorState(actor=hero, current_hp=hero.stats.hp)
    effs: Dict[str, float] = {}
    if merrymake:
        effs["merrymake"] = merrymake
    if el_boost:
        effs["elation_dmg_boost"] = el_boost
    if effs:
        src.modifiers["EL"] = Modifier(modifier_id="EL", name="欢愉", modifier_type="buff",
                                       duration=0, stat_effects=effs)
    target = ActorState(
        actor=Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                    stats=StatBlock(hp=1e9, weakness=[element] if weak else ["ice"],
                                    vulnerability=vuln)),
        current_hp=1e9, broken=broken)
    return SettlementPipeline(mode=MODE_EXPECTED).elation_damage(
        src, target, ability_multiplier=ability, punchline_source=punchline,
        damage_type=element)


def _optimizer_elation_scenario(*, ability: float, punchline: float, elation: float = 0.0,
                                merrymake: float = 0.0, cr: float = 0.0, cd: float = 0.0,
                                def_pen: float = 0.0, res_pen: float = 0.0, vuln: float = 0.0,
                                final: float = 0.0, dmg_all: float = 0.0,
                                element_boost: float = 0.0, element: str = "fire",
                                enemy_res: float = 0.0, broken: bool = False) -> Dict[str, Any]:
    return {
        "kind": "elation",
        "element": element,
        "attacker": {
            "level": 80, "cr": cr, "cd": cd, "elation": elation,
            "merrymaking": merrymake, "def_pen": def_pen, "res_pen": res_pen,
            "vulnerability": vuln, "final_dmg_boost": final,
            "dmg_boost": dmg_all, "element_boost": element_boost,
        },
        "hit": {"elation_scaling": ability, "punchline_stacks": punchline},
        "enemy": {"level": 80, "damage_resistance": enemy_res, "weakness_broken": broken},
    }


# (场景名, 双方共有 kwargs, 手算基准——按 rulebook elation_damage 表达式)
ELATION_SCENARIOS = [
    # 基础链：7535.107×0.5 ×(1+0.5) ×(1+5×20/260) ×期望暴击 1.025 ×def 0.5 ×未击破 0.9
    ("hand_calc_baseline",
     dict(ability=0.5, punchline=20.0, elation=0.5, cr=0.05, cd=0.5),
     ELATION_BASE * 0.5 * 1.5 * (1 + 5 * 20 / 260) * 1.025 * 0.5 * 1.0 * 1.0 * 0.9),
    # 全面板链 + 增伤隔离：通用 0.5/属性 0.388 高增伤面板**双方均不吃**（隔离验证）；
    # 笑点 40、好活 0.6、双暴 0.5/1.0 → 期望 1.5、def_pen 0.2 → 1000/1800、
    # 弱点 0 抗 + res_pen 0.1 → 1.1、易伤 0.3、最终伤害 0.25（双方同键）、已击破 1.0
    ("full_panel_boost_isolated",
     dict(ability=0.4, punchline=40.0, elation=0.8, merrymake=0.6, cr=0.5, cd=1.0,
          def_pen=0.2, res_pen=0.1, vuln=0.3, final=0.25,
          dmg_all=0.5, element_boost=0.388, broken=True),
     ELATION_BASE * 0.4 * 1.8 * (1 + 5 * 40 / 280) * 1.5 * 1.6
     * (1000 / 1800) * 1.1 * 1.3 * 1.25 * 1.0),
]


class TestElationDuipai:
    @pytest.mark.parametrize(
        "name,kw,hand",
        ELATION_SCENARIOS,
        ids=[s[0] for s in ELATION_SCENARIOS],
    )
    def test_damage_matches(self, optimizer_driver, name, kw, hand):
        ours = _ours_elation(**kw)
        theirs = run_optimizer(optimizer_driver, _optimizer_elation_scenario(**kw))

        # 双锚：手算基准 + 双方互对（rel_tol 1e-4）
        assert math.isclose(ours.value, hand, rel_tol=REL_TOL), f"{name} 我方 vs 手算"
        assert math.isclose(theirs["damage"], hand, rel_tol=REL_TOL), f"{name} optimizer vs 手算"
        assert math.isclose(ours.value, theirs["damage"], rel_tol=REL_TOL), f"{name} 双方互对"

        # 乘区节点级比对
        bd = theirs["breakdown"]
        for node_key in ("abilityMulti", "elationLevelMultiplier", "elationMulti",
                         "punchlineMulti", "merrymakeMulti", "critMulti", "defMulti",
                         "resMulti", "vulnMulti", "baseUniversalMulti", "finalDmgMulti"):
            assert math.isclose(ours.node[node_key], bd[node_key], rel_tol=REL_TOL), \
                f"{name} 乘区 {node_key}: 我方 {ours.node[node_key]} vs optimizer {bd[node_key]}"


class TestElationKnownDivergence:
    def test_elation_dmg_boost_pool_divergence(self, optimizer_driver):
        """已核实的结构差——欢愉增伤池 elation_dmg_boost（爻光族槽位）：我方独立乘区，
        对方 ElationDamageFunction 无此键（乘区表无 elation boost/dmg red）。
        池 0.4 → 我方恰为对方 ×1.4；其余乘区全等。"""
        kw = dict(ability=0.5, punchline=20.0, elation=0.5, cr=0.05, cd=0.5, el_boost=0.4)
        ours = _ours_elation(**kw)
        theirs = run_optimizer(optimizer_driver, _optimizer_elation_scenario(
            ability=0.5, punchline=20.0, elation=0.5, cr=0.05, cd=0.5))

        base = ELATION_BASE * 0.5 * 1.5 * (1 + 5 * 20 / 260) * 1.025 * 0.5 * 1.0 * 1.0 * 0.9
        assert math.isclose(theirs["damage"], base, rel_tol=REL_TOL), "对方无该池 = 基础链值"
        assert math.isclose(ours.value, base * 1.4, rel_tol=REL_TOL)
        # 差值倍数核实：恰为 (1 + 欢愉增伤池)
        assert math.isclose(ours.value / theirs["damage"], 1.4, rel_tol=REL_TOL)
        assert math.isclose(ours.node["elationDmgBoostMulti"], 1.4, rel_tol=REL_TOL)
        # 公共乘区一致——差值全部来自该池
        for node_key in ("elationMulti", "punchlineMulti", "critMulti", "defMulti", "resMulti"):
            assert math.isclose(ours.node[node_key], theirs["breakdown"][node_key],
                                rel_tol=REL_TOL), f"公共乘区 {node_key}"


# ---------------------------------------------------------------------------
# DoT（B27#3 我方已收官）：快照切分（攻击侧施加时刻快照 / 目标侧跳伤现值）下，
# 公共子集（倍率基数/增伤池/命中区/防御/抗性/易伤/最终伤害/韧性减伤）双方全等；
# 对方无独立「DoT 增伤」键——我方 dot_dmg_boost 桶与对方 BOOST 池加算等价
# （scenario 2 验证）。单边乘区：我方独立易伤区 ind_vuln 对方无键；对方
# tickCoefficient/dotSplit/dotStacks 槽我方无对应——钉 divergence。
# ---------------------------------------------------------------------------


def _ours_dot(*, atk: float, ratio: float, element: str = "fire",
              effect_hit: float = 0.0, dmg_all: float = 0.0, element_boost: float = 0.0,
              dot_boost: float = 0.0, final: float = 0.0, def_pen: float = 0.0,
              res_pen: float = 0.0, vuln: float = 0.0, ind_vuln: float = 0.0,
              effect_res: float = 0.0, weak: bool = True, broken: bool = False) -> Any:
    """我方 DoT 跳伤：施加时刻快照包（dot_snapshot_context）+ 跳伤全乘区链."""
    bonus: Dict[str, float] = {}
    if dmg_all:
        bonus["all"] = dmg_all
    if element_boost:
        bonus[element] = element_boost
    if dot_boost:
        bonus["dot_dmg_boost"] = dot_boost
    if final:
        bonus["final_dmg_boost"] = final
    src = ActorState(actor=Actor(actor_id="src", name="施加者", level=80,
                                 stats=StatBlock(atk=atk, spd=100, hp=5000, max_energy=100,
                                                 effect_hit=effect_hit, def_pen=def_pen,
                                                 res_pen=res_pen, dmg_bonus=bonus)),
                     current_hp=5000.0)
    holder = ActorState(actor=Actor(actor_id="tgt", name="敌", actor_type="monster", level=80,
                                    stats=StatBlock(hp=1e9, spd=100, def_=1000.0,
                                                    max_toughness=120.0,
                                                    weakness=[element] if weak else ["ice"],
                                                    effect_res=effect_res,
                                                    vulnerability=vuln)),
                        current_hp=1e9)
    holder.broken = broken
    if ind_vuln:
        holder.modifiers["IV"] = Modifier(
            modifier_id="IV", name="独立易伤", modifier_type="debuff",
            stat_effects={"dmg_ind_vulnerability": ind_vuln})
    pipe = SettlementPipeline(mode=MODE_EXPECTED)
    mod = Modifier(modifier_id="DOT_T", name="持续伤害", modifier_type="dot",
                   debuff_kind="dot", duration=2, source_id=src.actor.actor_id,
                   dot_element=element, dot_ratio=ratio,
                   dot_source_atk=pipe.effective_stats(src)["atk"])
    mod.dot_snapshot_ctx = pipe.dot_snapshot_context(src, holder, element, ratio)
    return pipe.dot_tick(holder, mod)


def _optimizer_dot_scenario(*, atk: float, ratio: float, element: str = "fire",
                            effect_hit: float = 0.0, dmg_all: float = 0.0,
                            element_boost: float = 0.0, dot_boost: float = 0.0,
                            final: float = 0.0, def_pen: float = 0.0, res_pen: float = 0.0,
                            vuln: float = 0.0, effect_res: float = 0.0,
                            enemy_res: float = 0.0, broken: bool = False,
                            extra_hit: Dict[str, Any] = None) -> Dict[str, Any]:
    # dot_boost 由驱动并入 action 层 BOOST（对方无独立键，增伤池内加算等价）
    hit = {"atk_scaling": ratio, "dot_base_chance": 1.0}
    if extra_hit:
        hit.update(extra_hit)
    return {
        "kind": "dot",
        "element": element,
        "attacker": {
            "level": 80, "atk": atk, "effect_hit": effect_hit,
            "dmg_boost": dmg_all, "dot_boost": dot_boost, "element_boost": element_boost,
            "final_dmg_boost": final, "def_pen": def_pen, "res_pen": res_pen,
            "vulnerability": vuln,
        },
        "hit": hit,
        "enemy": {"level": 80, "damage_resistance": enemy_res,
                  "effect_resistance": effect_res, "weakness_broken": broken},
    }


# (场景名, 双方共有 kwargs, 手算基准——按 rulebook dot_damage 表达式)
DOT_SCENARIOS = [
    # 命中区链：effect_hit 0.4 / 目标效果抵抗 0.3 → ehr = min(1, 1.0×1.4×0.7) = 0.98；
    # 2000×def 0.5×未击破 0.9×0.98 = 882
    ("hand_calc_ehr_chain",
     dict(atk=2000.0, ratio=1.0, effect_hit=0.4, effect_res=0.3),
     2000.0 * 0.5 * 0.9 * 0.98),
    # 全面板链：ability = 3000×1.5；增伤池 1+0.1+0.2+0.24=1.54（dot_dmg_boost 桶 ↔
    # 对方 BOOST 加算等价）；def_pen 0.5 → 2/3；弱点 0 抗 + res_pen 0.2 → 1.2；
    # 易伤 0.3、最终伤害 0.15、已击破 1.0
    ("full_panel",
     dict(atk=3000.0, ratio=1.5, dmg_all=0.1, element_boost=0.2, dot_boost=0.24,
          final=0.15, def_pen=0.5, res_pen=0.2, vuln=0.3, broken=True),
     4500.0 * 1.54 * (2 / 3) * 1.2 * 1.3 * 1.15 * 1.0),
]


class TestDotDuipai:
    @pytest.mark.parametrize(
        "name,kw,hand",
        DOT_SCENARIOS,
        ids=[s[0] for s in DOT_SCENARIOS],
    )
    def test_damage_matches(self, optimizer_driver, name, kw, hand):
        ours = _ours_dot(**kw)
        theirs = run_optimizer(optimizer_driver, _optimizer_dot_scenario(**kw))

        # 双锚：手算基准 + 双方互对（rel_tol 1e-4）
        assert math.isclose(ours.value, hand, rel_tol=REL_TOL), f"{name} 我方 vs 手算"
        assert math.isclose(theirs["damage"], hand, rel_tol=REL_TOL), f"{name} optimizer vs 手算"
        assert math.isclose(ours.value, theirs["damage"], rel_tol=REL_TOL), f"{name} 双方互对"

        # 乘区节点级比对
        bd = theirs["breakdown"]
        for node_key in ("abilityMulti", "dmgBoostMulti", "ehrMulti", "defMulti",
                         "resMulti", "vulnMulti", "baseUniversalMulti", "finalDmgMulti"):
            assert math.isclose(ours.node[node_key], bd[node_key], rel_tol=REL_TOL), \
                f"{name} 乘区 {node_key}: 我方 {ours.node[node_key]} vs optimizer {bd[node_key]}"


class TestDotKnownDivergence:
    def test_ind_vuln_zone_divergence(self, optimizer_driver):
        """已核实的结构差①——独立易伤区 ind_vuln（常规 DoT 生效列，mechanics 02 §2.12）：
        我方独立乘区，对方 DotDamageFunction 无此键（其 VULNERABILITY 单池已中性）。
        目标独立易伤 0.4 → 我方恰为对方 ×1.4；其余乘区全等。"""
        ours = _ours_dot(atk=2000.0, ratio=1.0, ind_vuln=0.4)
        theirs = run_optimizer(optimizer_driver,
                               _optimizer_dot_scenario(atk=2000.0, ratio=1.0))

        base = 2000.0 * 0.5 * 0.9
        assert math.isclose(theirs["damage"], base, rel_tol=REL_TOL), "对方无该区 = 基础链值"
        assert math.isclose(ours.value, base * 1.4, rel_tol=REL_TOL)
        # 差值倍数核实：恰为 (1 + 独立易伤)
        assert math.isclose(ours.value / theirs["damage"], 1.4, rel_tol=REL_TOL)
        assert math.isclose(ours.node["indVulnMulti"], 1.4, rel_tol=REL_TOL)
        for node_key in ("abilityMulti", "dmgBoostMulti", "defMulti", "resMulti"):
            assert math.isclose(ours.node[node_key], theirs["breakdown"][node_key],
                                rel_tol=REL_TOL), f"公共乘区 {node_key}"

    def test_tick_coefficient_divergence(self, optimizer_driver):
        """已核实的结构差②——对方专槽 hit.tickCoefficient（默认 1，dotSplit/dotStacks
        同族专槽）：我方 dot_damage 公式链无对应槽。槽置 2.0 → 对方恰为我方 ×2.0。"""
        ours = _ours_dot(atk=2000.0, ratio=1.0)
        theirs = run_optimizer(optimizer_driver, _optimizer_dot_scenario(
            atk=2000.0, ratio=1.0, extra_hit={"tick_coefficient": 2.0}))

        base = 2000.0 * 0.5 * 0.9
        assert math.isclose(ours.value, base, rel_tol=REL_TOL), "我方无该槽 = 基础链值"
        assert math.isclose(theirs["damage"], base * 2.0, rel_tol=REL_TOL)
        # 差值倍数核实：恰为 tickCoefficient
        assert math.isclose(theirs["damage"] / ours.value, 2.0, rel_tol=REL_TOL)
        assert math.isclose(theirs["breakdown"]["tickCoefficientMulti"], 2.0, rel_tol=REL_TOL)


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
