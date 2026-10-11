"""通用 settle 公式预期验收（决策卡 #23 P2/P3——per-type 函数已删除）：

`settle_damage`（全数据驱动唯一结算路径）对每个伤害类别的结果必须符合
rulebook 公式链预期——本文件用**独立手算**（公式同序浮点运算）对 value 逐比特
断言（`==`/rel_tol=1e-12），并断言：
- `SettleResult.node` 键集与各类别乘区拆解形状（含 node_drop/跳过态/条件键）
- 随机抽取数契约：expected 模式零抽取；roll 模式含判定区（crit）类别恰好一次
  抽取、其余零抽取（B16 随机流消费序的锚）
- 类别差冻结（vuln 宽/窄 scoped 集、res_pen scoped 仅 direct、dmg_red/final_dmg
  中性 vs 实读——手算按冻结口径计，引擎"顺手修正"立即红）
- 新伤害类别 = rulebook 纯数据（pierce 注入——#23 验收②）

手算口径：乘区/公式链全部按 rulebook 表达式同序 Python 复算（`_chain` 左结合与
表达式 BinOp 求值序一致）；roll 暴击用同种子 fresh Random 复演（本文件场景里
判定区是首次也是唯一一次抽取）。
"""
from __future__ import annotations

import functools
import math
import operator
import random

import pytest

from hsr_nous.sim.compile.expr_compiler import ExprCompiler
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL, SettlementPipeline
from hsr_nous.sim.state import BREAK_DOT_ID_PREFIX, ActorState, Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.expression import parse

_MODES = (MODE_ROLL, MODE_EXPECTED)
_SEED = 42
# 口径常数（rulebook 镜像）：白板假人 def 1000 → 防御区 0.5；火弱点 → 抗性区 1.0；
# 非弱点默认抗 0.2 → 0.8；未击破 0.9 / 已击破 1.0；等级系数 7535.107。
LV_COEF = 7535.107
DEF_ZONE = 0.5
NON_WEAK_RES_ZONE = 0.8


# ---------------------------------------------------------------------------
# 构造件
# ---------------------------------------------------------------------------

def _pipe(mode: str, seed: int = _SEED, expr=None) -> SettlementPipeline:
    return SettlementPipeline(mode=mode, seed=seed, expr=expr)


def _hero(*, actor_id: str = "hero", **stats) -> ActorState:
    base = {"hp": 5000.0, "atk": 2000.0, "spd": 100.0, "max_energy": 100.0}
    base.update(stats)
    a = Actor(actor_id=actor_id, name="测试员", level=80, stats=StatBlock(**base))
    return ActorState(actor=a, current_hp=a.stats.hp)


def _dummy(*, actor_id: str = "e1", actor_type: str = "monster", **stats) -> ActorState:
    base = {"hp": 1e9, "spd": 100.0, "def_": 1000.0, "max_toughness": 120.0,
            "weakness": ["fire"]}
    base.update(stats)
    a = Actor(actor_id=actor_id, name="假人", actor_type=actor_type, level=80,
              stats=StatBlock(**base))
    return ActorState(actor=a, current_hp=a.stats.hp)


def _action(**kw) -> Action:
    base = {"action_id": "b", "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 1.0}]}
    base.update(kw)
    return Action(**base)


def _stat_mod(mid: str, stats: dict, **kw) -> Modifier:
    return Modifier(modifier_id=mid, name=mid, modifier_type="buff",
                    stat_effects=dict(stats), **kw)


def _scoped_mod(cc: ExprCompiler, mid: str, stats: dict, cond: str) -> Modifier:
    return Modifier(modifier_id=mid, name=mid, modifier_type="buff",
                    stat_effects=dict(stats), hit_condition_expr=cc.compile(cond))


# ---------------------------------------------------------------------------
# 手算件（rulebook 公式链同序复算）
# ---------------------------------------------------------------------------

def _chain(*xs: float) -> float:
    """公式链左结合连乘（与表达式 BinOp 求值序逐比特一致）."""
    return functools.reduce(operator.mul, xs)


def _def_zone(def_pen: float, target_def: float = 1000.0, level: int = 80) -> float:
    return (level * 10 + 200) / (target_def * max(0, 1 - def_pen) + level * 10 + 200)


def _res_zone(target_res: float, res_pen: float) -> float:
    return 1 - max(-1.0, min(0.9, target_res - res_pen))


def _crit_expected(cr: float, cd: float) -> float:
    return min(1, cr) * (1 + cd) + (1 - min(1, cr))


def _crit_roll(cr: float, cd: float, seed: int = _SEED) -> tuple[float, bool]:
    """roll 判定区复演（本文件场景中判定区 = 同种子 rng 的首次抽取）."""
    r = random.Random(seed).random()
    return (1 + cd, True) if r < cr else (1.0, False)


def _assert_draws(pipe: SettlementPipeline, n: int, seed: int = _SEED) -> None:
    """随机抽取数契约：settle 后 rng 状态 == 同种子 fresh Random 抽取 n 次."""
    r = random.Random(seed)
    for _ in range(n):
        r.random()
    assert pipe.rng.getstate() == r.getstate(), f"抽取数 != {n}（随机流消费漂移）"


# ---------------------------------------------------------------------------
# direct
# ---------------------------------------------------------------------------
class TestDirectExpectations:
    def test_plain(self):
        """中性链：2000×0.5×0.9×暴击区（roll 0.05 不暴=1.0；expected=1.025）."""
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("direct", _hero(), _dummy(), action=_action())
            crit = _crit_roll(0.05, 0.5)[0] if mode == MODE_ROLL else _crit_expected(0.05, 0.5)
            assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0, 1.0,
                                     crit, 1.0, 1.0)
            assert set(r.node) == {"formula", "abilityMulti", "dmgBoostMulti",
                                   "indDmgBoostMulti", "defMulti", "resMulti",
                                   "baseUniversalMulti", "vulnMulti", "indVulnMulti",
                                   "finalDmgMulti", "critMulti", "isCrit",
                                   "weakenMulti", "dmgRedMulti"}
            assert r.node["isCrit"] is False
            _assert_draws(p, 1 if mode == MODE_ROLL else 0)

    def test_full_buckets_and_scoped(self):
        """全桶+全 scoped（expected）：手算按冻结口径（dmg 求值后加 scoped、vuln 宽集）."""
        cc = ExprCompiler()

        def src():
            st = _hero(def_pen=0.1, res_pen=0.05, crit_rate=0.6, crit_dmg=1.2,
                       dmg_bonus={"fire": 0.2, "all": 0.1, "basic_dmg_boost": 0.15,
                                  "ind_dmg_boost": 0.12, "final_dmg_boost": 0.08})
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"dmg_fire": 0.1, "all_dmg": 0.05},
                                             "$event.action_type == 'basic'")
            st.modifiers["S2"] = _scoped_mod(cc, "S2", {"def_pen": 0.08, "res_pen": 0.03},
                                             "$event.damage_type == 'fire'")
            st.modifiers["S3"] = _scoped_mod(cc, "S3", {"crit_rate": 0.2, "crit_dmg": 0.3},
                                             "$event.target_hp_ratio > 0.5")
            return st

        def tgt():
            st = _dummy(vulnerability=0.1,
                        dmg_bonus={"weaken": 0.1, "dmg_reduction": 0.2,
                                   "ind_vulnerability": 0.06})
            st.modifiers["T1"] = _stat_mod("T1", {"vulnerability": 0.05})
            st.modifiers["T2"] = _scoped_mod(cc, "T2", {"vulnerability": 0.15},
                                             "$event.action_type == 'basic'")
            st.modifiers["T3"] = _scoped_mod(cc, "T3", {"ind_vulnerability": 0.07},
                                             "$event.action_type == 'basic'")
            return st

        p = _pipe(MODE_EXPECTED, expr=cc)
        r = p.settle_damage("direct", src(), tgt(), action=_action())
        dmg = (1 + (0.1 + 0.2 + 0.15)) + (0.1 + 0.05)     # scoped 先聚合再一次性加（结合序冻结）
        expected = _chain(2000.0, dmg, 1.12, _def_zone(0.18), _res_zone(0.0, 0.08), 0.9,
                          1 + 0.1 + 0.05 + 0.15 + 0.07,   # vuln 宽集：scoped ind_vuln 并入本区
                          1.06, 1.08, _crit_expected(0.8, 1.5), 0.9, 0.8)
        assert r.value == expected
        assert r.node["dmgBoostMulti"] == dmg
        assert r.node["vulnMulti"] == 1 + 0.1 + 0.05 + 0.15 + 0.07
        _assert_draws(p, 0)

    def test_base_override_and_target_broken_param(self):
        """base_override 直写基数 + target_broken 参数（base_universal=1.0）."""
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("direct", _hero(), _dummy(), action=_action(),
                                params={"base_override": 1234.5, "target_broken": True})
            crit = _crit_roll(0.05, 0.5)[0] if mode == MODE_ROLL else _crit_expected(0.05, 0.5)
            assert r.value == _chain(1234.5, 1.0, 1.0, DEF_ZONE, 1.0, 1.0, 1.0, 1.0, 1.0,
                                     crit, 1.0, 1.0)
            assert r.node["abilityMulti"] == 1234.5

    def test_skill_level_tier_and_clamp(self):
        """倍率取档（skill_level=2 取第二行 2.0×atk）与越界钳（99 → 末行 3.0×atk）."""
        act = _action(scaling=[{"atk": 1.0}, {"atk": 2.0}, {"atk": 3.0}])
        for lv, multi in ((2, 2.0), (99, 3.0)):
            p = _pipe(MODE_EXPECTED)
            r = p.settle_damage("direct", _hero(), _dummy(), action=act, skill_level=lv)
            assert r.value == _chain(2000.0 * multi, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0,
                                     1.0, 1.0, _crit_expected(0.05, 0.5), 1.0, 1.0)

    def test_res_resolution(self):
        """抗性解析三态：非弱点 0.2 / 抗性表命中 / 弱点优先于抗性表."""
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(), _dummy(), action=_action(damage_type="ice"))
        assert r.node["resMulti"] == NON_WEAK_RES_ZONE
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(), _dummy(resistance={"ice": 0.4}),
                            action=_action(damage_type="ice"))
        assert r.node["resMulti"] == _res_zone(0.4, 0.0)
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(),
                            _dummy(weakness=["fire", "ice"], resistance={"ice": 0.4}),
                            action=_action(damage_type="ice"))
        assert r.node["resMulti"] == 1.0

    def test_typeless_action(self):
        """无属性技能：元素桶不计 + 非弱点默认抗."""
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(dmg_bonus={"fire": 0.5}), _dummy(),
                            action=_action(damage_type=None))
        assert r.node["dmgBoostMulti"] == 1.0
        assert r.node["resMulti"] == NON_WEAK_RES_ZONE

    def test_def_resolution(self):
        """目标防御三态：覆写 0 → 区 1.0；白板（无覆写 def_=0）→ 兜底 1000 → 0.5."""
        def tgt_zero():
            st = _dummy()
            st.modifiers["DEF0"] = Modifier(modifier_id="DEF0", name="零防",
                                            modifier_type="debuff",
                                            override_effects={"def_": 0.0})
            return st
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(), tgt_zero(), action=_action())
        assert r.node["defMulti"] == 1.0
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero(), _dummy(def_=0.0), action=_action())
        assert r.node["defMulti"] == DEF_ZONE

    def test_crit_branches(self):
        """roll：crit_rate 1.5 恒暴（isCrit True/×2.3）、0.0 恒不暴（×1.0）；expected 钳 min(1,·)."""
        act = _action()
        for cr, cd in ((1.5, 0.8), (0.0, 0.8)):
            for mode in _MODES:
                p = _pipe(mode)
                r = p.settle_damage("direct", _hero(crit_rate=cr, crit_dmg=cd), _dummy(),
                                    action=act)
                if mode == MODE_ROLL:
                    crit, is_crit = _crit_roll(cr, cd)
                else:
                    crit, is_crit = _crit_expected(cr, cd), False
                assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0,
                                         1.0, crit, 1.0, 1.0)
                assert r.node["isCrit"] is is_crit
                _assert_draws(p, 1 if mode == MODE_ROLL else 0)

    def test_bare_actor_entry(self):
        """裸 Actor 兼容入口（_as_state 包壳——无 modifier 中性链）."""
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("direct", _hero().actor, _dummy().actor, action=_action())
        assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0, 1.0,
                                 _crit_expected(0.05, 0.5), 1.0, 1.0)


# ---------------------------------------------------------------------------
# true
# ---------------------------------------------------------------------------
class TestTrueExpectations:
    def test_plain(self):
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("true", _hero(), _dummy(),
                                params={"fixed_value": 1234.5, "true_dmg_rate": 0.4})
            assert r.value == _chain(1234.5, 0.4, 1.0)
            assert set(r.node) == {"formula", "fixedValue", "trueDmgRate",
                                   "trueDmgMulti", "isCrit"}
            assert r.node["isCrit"] is False
            _assert_draws(p, 0)

    def test_boost_bucket_and_default_rate(self):
        """true_dmg_boost 桶实读；true_dmg_rate 缺省 1.0（legacy 签名缺省口径）."""
        for mode in _MODES:
            p = _pipe(mode)

            def src():
                st = _hero()
                st.modifiers["TD"] = _stat_mod("TD", {"dmg_true_dmg_boost": 0.25})
                return st

            r = p.settle_damage("true", src(), _dummy(), params={"fixed_value": 100.0})
            assert r.value == _chain(100.0, 1.0, 1.25)
            assert r.node["trueDmgRate"] == 1.0


# ---------------------------------------------------------------------------
# break
# ---------------------------------------------------------------------------
class TestBreakExpectations:
    def test_plain(self):
        """火击破：3767.5533×2.0×(0.5+120/40) × BE2.2 × 0.5×1.0×1.0（base_universal 恒 1）."""
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("break", _hero(break_effect=1.2), _dummy(), element="fire")
            base = 3767.5533 * 2.0 * (0.5 + 120 / 40) * 1.0
            assert r.value == _chain(base, 2.2, 1.0, 1.0, DEF_ZONE, 1.0, 1.0, 1.0, 1.0)
            # node_drop：base_universal/final_dmg/dmg_red 三区求值但不落 node（冻结形状）
            assert set(r.node) == {"formula", "breakBaseMulti", "beMulti",
                                   "breakDmgBoostMulti", "defMulti", "resMulti", "vulnMulti"}
            _assert_draws(p, 0)

    def test_pools_and_scoped(self):
        """击破增伤桶 + scoped 冻结类别差：def_pen/vuln 命中；res_pen/ind_vuln scoped 不激活."""
        cc = ExprCompiler()

        def src():
            st = _hero(break_effect=1.2, res_pen=0.1, dmg_bonus={"break_dmg_boost": 0.3})
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"def_pen": 0.2},
                                             "$event.action_type == 'break'")
            st.modifiers["S2"] = _scoped_mod(cc, "S2", {"res_pen": 0.5},
                                             "$event.action_type == 'break'")
            return st

        def tgt():
            st = _dummy(vulnerability=0.1)
            st.modifiers["T1"] = _scoped_mod(cc, "T1", {"vulnerability": 0.2},
                                             "$event.action_type == 'break'")
            st.modifiers["T2"] = _scoped_mod(cc, "T2", {"ind_vulnerability": 0.5},
                                             "$event.action_type == 'break'")
            return st

        p = _pipe(MODE_EXPECTED, expr=cc)
        r = p.settle_damage("break", src(), tgt(), element="fire")
        base = 3767.5533 * 2.0 * (0.5 + 120 / 40) * 1.0
        assert r.value == _chain(base, 2.2, 1.3, 1.0, _def_zone(0.2),
                                 _res_zone(0.0, 0.1),   # scoped res_pen 不激活（面板 0.1 实读）
                                 1 + 0.1 + 0.2, 1.0, 1.0)

    def test_non_weakness_and_def_override(self):
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("break", _hero(), _dummy(), element="ice")
        assert r.node["resMulti"] == NON_WEAK_RES_ZONE

        def tgt_zero():
            st = _dummy(max_toughness=240.0)
            st.modifiers["DEF0"] = Modifier(modifier_id="DEF0", name="零防",
                                            modifier_type="debuff",
                                            override_effects={"def_": 0.0})
            return st
        p = _pipe(MODE_EXPECTED)
        r = p.settle_damage("break", _hero(), tgt_zero(), element="fire")
        base = 3767.5533 * 2.0 * (0.5 + 240 / 40) * 1.0
        assert r.value == _chain(base, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
# super_break
# ---------------------------------------------------------------------------
class TestSuperBreakExpectations:
    @staticmethod
    def _src(cc=None):
        st = _hero(break_effect=1.2, dmg_bonus={"break_dmg_boost": 0.2})
        st.modifiers["SB"] = _stat_mod("SB", {"super_break_modifier": 1.5,
                                              "super_break_dmg_boost": 0.3})
        if cc is not None:
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"def_pen": 0.2},
                                             "$event.action_type == 'super_break'")
            st.modifiers["S2"] = _scoped_mod(cc, "S2", {"res_pen": 0.5},
                                             "$event.action_type == 'super_break'")
        return st

    def test_full_pools(self):
        """全池：(3767.5533/10×30) × BE2.2 × 转换1.5 × 增伤1.2 × 超增1.3 × 目标侧链."""
        cc = ExprCompiler()

        def tgt():
            st = _dummy(vulnerability=0.1)
            st.broken = True
            st.modifiers["T1"] = _scoped_mod(cc, "T1", {"vulnerability": 0.2},
                                             "$event.action_type == 'super_break'")
            return st

        for mode in _MODES:
            p = _pipe(mode, expr=cc)
            r = p.settle_damage("super_break", self._src(cc), tgt(), element="fire",
                                params={"effective_toughness": 30.0})
            base = (3767.5533 / 10) * 30.0
            assert r.value == _chain(1.0, _def_zone(0.2), 1.0, 1 + 0.1 + 0.2, 1.0,
                                     base, 2.2, 1.5, 1.2, 1.3, 1.0)
            assert set(r.node) == {"formula", "superBreakBaseMulti", "beMulti",
                                   "superBreakConversionMulti", "breakDmgBoostMulti",
                                   "superBreakDmgBoostMulti", "defMulti", "resMulti",
                                   "vulnMulti"}
            assert r.node["superBreakConversionMulti"] == 1.5   # sum(池) 逐比特同面板聚合
            _assert_draws(p, 0)

    def test_skip_gates(self):
        """无转换源 / 零削韧 → skipped 态（0.0 + 模板 node）."""
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("super_break", _hero(), _dummy(), element="fire",
                                params={"effective_toughness": 30.0})
            assert r.value == 0.0
            assert r.node == {"formula": "super_break_damage",
                              "superBreakConversionMulti": 0.0,
                              "effectiveToughness": 30.0, "skipped": True}
            p = _pipe(mode)
            r = p.settle_damage("super_break", self._src(), _dummy(), element="fire",
                                params={"effective_toughness": 0.0})
            assert r.value == 0.0
            assert r.node == {"formula": "super_break_damage",
                              "superBreakConversionMulti": 1.5,
                              "effectiveToughness": 0.0, "skipped": True}
            _assert_draws(p, 0)


# ---------------------------------------------------------------------------
# elation
# ---------------------------------------------------------------------------
class TestElationExpectations:
    def test_plain(self):
        """7535.107×0.35 × elation1.5 × punchline(1+100/260) × crit × 0.5×1.0×0.9."""
        for mode in _MODES:
            p = _pipe(mode)
            r = p.settle_damage("elation", _hero(elation=0.5), _dummy(), element="fire",
                                params={"ability_multiplier": 0.35, "punchline_source": 20.0})
            crit = _crit_roll(0.05, 0.5)[0] if mode == MODE_ROLL else _crit_expected(0.05, 0.5)
            pl = 1 + 5 * 20.0 / (20.0 + 240)
            assert r.value == _chain(LV_COEF, 0.35, 1.0, 1.0, crit, 1.5, pl, 1.0,
                                     DEF_ZONE, 1.0, 1.0, 1.0, 0.9, 1.0)
            assert set(r.node) == {"formula", "abilityMulti", "elationLevelMultiplier",
                                   "elationDmgBoostMulti", "elationMulti", "punchlineMulti",
                                   "merrymakeMulti", "critMulti", "isCrit", "defMulti",
                                   "resMulti", "vulnMulti", "baseUniversalMulti",
                                   "finalDmgMulti", "dmgRedMulti", "punchlineSource"}
            assert r.node["punchlineSource"] == 20.0
            _assert_draws(p, 1 if mode == MODE_ROLL else 0)

    def test_full_pools_broken_and_scoped(self):
        """全池实读（merrymake/elation_dmg_boost/final_dmg/减伤）+ 已击破 + scoped."""
        cc = ExprCompiler()

        def src():
            st = _hero(elation=0.5, dmg_bonus={"final_dmg_boost": 0.15})
            st.modifiers["EM"] = _stat_mod("EM", {"merrymake": 0.2, "elation_dmg_boost": 0.1})
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"def_pen": 0.2},
                                             "$event.action_type == 'elation_damage'")
            return st

        def tgt():
            st = _dummy(dmg_bonus={"dmg_reduction": 0.1}, vulnerability=0.1)
            st.broken = True
            st.modifiers["T1"] = _scoped_mod(cc, "T1", {"vulnerability": 0.2},
                                             "$event.action_type == 'elation_damage'")
            return st

        p = _pipe(MODE_EXPECTED, expr=cc)
        r = p.settle_damage("elation", src(), tgt(), element="fire",
                            params={"ability_multiplier": 0.35, "punchline_source": 40.0})
        pl = 1 + 5 * 40.0 / (40.0 + 240)
        assert r.value == _chain(LV_COEF, 0.35, 1.0, 1.1, _crit_expected(0.05, 0.5), 1.5,
                                 pl, 1.2, _def_zone(0.2), 1.0, 1 + 0.1 + 0.2, 0.9, 1.0, 1.15)
        assert r.node["baseUniversalMulti"] == 1.0
        assert r.node["dmgRedMulti"] == 0.9   # 减伤实读（与 break 族中性 0 的冻结类别差）

    def test_skip_gate(self):
        """零倍率闸——skipped 态（roll 模式同样零抽取：闸先于判定区）."""
        for mode in _MODES:
            for am in (0.0, -1.0):
                p = _pipe(mode)
                r = p.settle_damage("elation", _hero(), _dummy(), element="fire",
                                    params={"ability_multiplier": am,
                                            "punchline_source": 20.0})
                assert r.value == 0.0
                assert r.node == {"formula": "elation_damage", "abilityMulti": am,
                                  "skipped": True}
                _assert_draws(p, 0)

    def test_crit_branches(self):
        """roll/expected 双公式（route 模式分发——expected 引 crit_expected_multi 区）."""
        for cr, cd in ((1.5, 0.8), (0.0, 0.8)):
            for mode in _MODES:
                p = _pipe(mode)
                r = p.settle_damage("elation", _hero(crit_rate=cr, crit_dmg=cd), _dummy(),
                                    element="fire",
                                    params={"ability_multiplier": 0.3, "punchline_source": 0.0})
                if mode == MODE_ROLL:
                    crit, is_crit = _crit_roll(cr, cd)
                else:
                    crit, is_crit = _crit_expected(cr, cd), False
                assert r.value == _chain(LV_COEF, 0.3, 1.0, 1.0, crit, 1.0, 1.0, 1.0,
                                         DEF_ZONE, 1.0, 1.0, 1.0, 0.9, 1.0)
                assert r.node["isCrit"] is is_crit
                _assert_draws(p, 1 if mode == MODE_ROLL else 0)


# ---------------------------------------------------------------------------
# dot
# ---------------------------------------------------------------------------

def _dot_mod(pipe: SettlementPipeline, src: ActorState, holder: ActorState, *,
             element: str = "fire", ratio: float = 1.0, stacks: int = 1,
             legacy: bool = False) -> Modifier:
    mod = Modifier(modifier_id="DOT_T", name="持续伤害", modifier_type="dot",
                   debuff_kind="dot", duration=2, stacks=stacks,
                   source_id=src.actor.actor_id, dot_element=element, dot_ratio=ratio,
                   dot_source_atk=pipe.effective_stats(src)["atk"])
    if not legacy:
        mod.dot_snapshot_ctx = pipe.dot_snapshot_context(src, holder, element, ratio)
    return mod


_DOT_NODE_KEYS = {"formula", "element", "ratio", "abilityMulti", "dmgBoostMulti",
                  "indDmgBoostMulti", "defMulti", "resMulti", "baseUniversalMulti",
                  "vulnMulti", "indVulnMulti", "finalDmgMulti", "weakenMulti",
                  "dmgRedMulti", "ehrMulti", "isCrit", "actualAmount"}


class TestDotExpectations:
    def test_snapshot_basic(self):
        """快照链中性：2000×0.5×0.9 + 跳伤扣血（holder HP 同步减）."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy()
            mod = _dot_mod(builder, _hero(), h, ratio=1.0)
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0,
                                     1.0, 1.0, 1.0, 1.0)
            assert set(r.node) == _DOT_NODE_KEYS
            assert r.node["isCrit"] is False
            assert r.node["actualAmount"] == r.value
            assert h.current_hp == 1e9 - r.value, "跳伤扣血"
            _assert_draws(p, 0)

    def test_stacked_dot(self):
        """叠层：基数 = 每层倍率快照 × max(1, stacks) 现值（0.5×2000×3）."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy()
            mod = _dot_mod(builder, _hero(), h, ratio=0.5, stacks=3)
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(2000.0 * 0.5 * 3, 1.0, 1.0, DEF_ZONE, 1.0, 0.9,
                                     1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert h.current_hp == 1e9 - r.value

    def test_legacy_bare_mod(self):
        """裸件兜底：攻击侧全中性、基数 dot_source_atk×dot_ratio（5432.1×1.234）."""
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy()
            mod = _dot_mod(p, _hero(), h, ratio=1.234, legacy=True)
            mod.dot_source_atk = 5432.1
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(5432.1 * 1.234, 1.0, 1.0, DEF_ZONE, 1.0, 0.9,
                                     1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert h.current_hp == 1e9 - r.value

    def test_dot_ratio_expr(self):
        """跳伤时求值件：表达式值即当跳基数 + ratioExpr node 键（无该件不落键）."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy()
            mod = _dot_mod(builder, _hero(), h, ratio=0.0)
            mod.dot_ratio_expr = parse("$snapshot.atk * 0.25", layer="effect")
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(2000.0 * 0.25, 1.0, 1.0, DEF_ZONE, 1.0, 0.9,
                                     1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert set(r.node) == _DOT_NODE_KEYS | {"ratioExpr"}
            assert r.node["ratioExpr"] == "$snapshot.atk * 0.25"
            assert h.current_hp == 1e9 - r.value

    def test_scoped_via_actor_lookup(self):
        """跳伤时刻 scoped：施加者反查（dmg/def_pen）+ 承伤宽集（vuln+ind_vuln 并入 vuln 区）."""
        builder = _pipe(MODE_EXPECTED)
        cc = ExprCompiler()

        def src():
            st = _hero(dmg_bonus={"dot_dmg_boost": 0.24})
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"dmg_fire": 0.2},
                                             "$event.action_type == 'dot'")
            st.modifiers["S2"] = _scoped_mod(cc, "S2", {"def_pen": 0.3},
                                             "$event.action_type == 'dot'")
            return st

        def tgt():
            st = _dummy(vulnerability=0.1)
            st.modifiers["T1"] = _scoped_mod(cc, "T1",
                                             {"vulnerability": 0.15, "ind_vulnerability": 0.07},
                                             "$event.action_type == 'dot'")
            return st

        for mode in _MODES:
            p = _pipe(mode, expr=cc)
            src_st = src()
            p.set_actor_lookup(lambda aid: src_st if aid == "hero" else None)
            h = tgt()
            mod = _dot_mod(builder, src_st, h, ratio=1.0)
            r = p.settle_damage("dot", h, h, modifier=mod)
            dmg = 1.24 + 0.2   # 快照 1.24（dot_dmg_boost 桶）+ 跳伤时刻 scoped
            assert r.value == _chain(2000.0, dmg, 1.0, _def_zone(0.3), 1.0, 0.9,
                                     1 + 0.1 + 0.15 + 0.07, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert r.node["dmgBoostMulti"] == dmg
            assert h.current_hp == 1e9 - r.value

    def test_no_lookup_scoped_neutral(self):
        """未注入反查：施加者 scoped 不计（裸路径中性兜底）."""
        builder = _pipe(MODE_EXPECTED)
        cc = ExprCompiler()

        def src():
            st = _hero()
            st.modifiers["S2"] = _scoped_mod(cc, "S2", {"def_pen": 0.3},
                                             "$event.action_type == 'dot'")
            return st

        for mode in _MODES:
            p = _pipe(mode, expr=cc)
            h = _dummy()
            mod = _dot_mod(builder, src(), h, ratio=1.0)
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0,
                                     1.0, 1.0, 1.0, 1.0)
            assert h.current_hp == 1e9 - r.value

    def test_non_weakness_and_broken(self):
        """冰 DoT 打火弱假人（0.8）+ 已击破（1.0）."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy()
            h.broken = True
            mod = _dot_mod(builder, _hero(), h, element="ice", ratio=1.0)
            r = p.settle_damage("dot", h, h, modifier=mod)
            assert r.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, NON_WEAK_RES_ZONE, 1.0,
                                     1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert h.current_hp == 1e9 - r.value


# ---------------------------------------------------------------------------
# bleed
# ---------------------------------------------------------------------------

def _bleed_mod(pipe: SettlementPipeline, src: ActorState, holder: ActorState, *,
               ratio: float = 1.0) -> Modifier:
    return Modifier(modifier_id=f"{BREAK_DOT_ID_PREFIX}physical", name="裂伤",
                    modifier_type="dot", debuff_kind="dot", duration=2,
                    source_id=src.actor.actor_id, dot_element="physical", dot_ratio=ratio,
                    dot_snapshot_ctx=pipe.dot_snapshot_context(src, holder, "physical", ratio))


_BLEED_NODE_KEYS = {"formula", "ratio", "bleedBaseMulti", "beMulti", "defMulti",
                    "resMulti", "baseUniversalMulti", "vulnMulti", "finalDmgMulti",
                    "dmgRedMulti", "enemyType", "actualAmount"}


class TestBleedExpectations:
    def test_elite_holder(self):
        """精英档：min(0.07×100000, cap 26372.8731)=7000 × BE快照2.5 × 0.5×0.8×0.9."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy(hp=100000.0)
            h.current_hp = 100000.0
            mod = _bleed_mod(builder, _hero(break_effect=1.5), h)
            r = p.settle_damage("bleed", h, h, modifier=mod)
            base = min(0.07 * 100000.0, 2 * 3767.5533 * (0.5 + 120 / 40))   # elite 档 0.07×HP 命中
            assert math.isclose(base, 7000.0, rel_tol=1e-15)
            assert r.value == _chain(base, 1.0, 2.5, DEF_ZONE, NON_WEAK_RES_ZONE, 0.9,
                                     1.0, 1.0, 1.0)
            assert set(r.node) == _BLEED_NODE_KEYS
            assert r.node["enemyType"] == "elite"
            assert r.node["actualAmount"] == r.value
            assert h.current_hp == 100000.0 - r.value
            _assert_draws(p, 0)

    def test_normal_holder(self):
        """普通档（非 monster/enemy → 0.16 系数；hp 50000 → min(8000, cap)=8000）."""
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy(actor_type="character", hp=50000.0)
            h.current_hp = 50000.0
            mod = _bleed_mod(builder, _hero(), h)
            r = p.settle_damage("bleed", h, h, modifier=mod)
            base = min(0.16 * 50000.0, 2 * 3767.5533 * (0.5 + 120 / 40))
            assert base == 8000.0
            assert r.value == _chain(base, 1.0, 1.0, DEF_ZONE, NON_WEAK_RES_ZONE, 0.9,
                                     1.0, 1.0, 1.0)
            assert r.node["enemyType"] == "normal"
            assert h.current_hp == 50000.0 - r.value

    def test_scoped_narrow(self):
        """裂伤承伤 scoped 窄集：vulnerability 命中、ind_vulnerability **不命中**（冻结类别差）."""
        builder = _pipe(MODE_EXPECTED)
        cc = ExprCompiler()

        def src():
            st = _hero(break_effect=1.5)
            st.modifiers["S1"] = _scoped_mod(cc, "S1", {"def_pen": 0.2},
                                             "$event.action_type == 'dot'")
            return st

        def tgt():
            st = _dummy(hp=100000.0)
            st.current_hp = 100000.0
            st.modifiers["T1"] = _scoped_mod(cc, "T1",
                                             {"vulnerability": 0.2, "ind_vulnerability": 0.5},
                                             "$event.action_type == 'dot'")
            return st

        for mode in _MODES:
            p = _pipe(mode, expr=cc)
            src_st = src()
            p.set_actor_lookup(lambda aid: src_st if aid == "hero" else None)
            h = tgt()
            mod = _bleed_mod(builder, src_st, h)
            r = p.settle_damage("bleed", h, h, modifier=mod)
            base = min(0.07 * 100000.0, 2 * 3767.5533 * (0.5 + 120 / 40))
            assert r.value == _chain(base, 1.0, 2.5, _def_zone(0.2), NON_WEAK_RES_ZONE,
                                     0.9, 1 + 0.2, 1.0, 1.0)
            assert r.node["vulnMulti"] == 1.2, "ind_vulnerability 不并入（窄集）"
            assert h.current_hp == 100000.0 - r.value

    def test_broken_holder(self):
        builder = _pipe(MODE_EXPECTED)
        for mode in _MODES:
            p = _pipe(mode)
            h = _dummy(hp=100000.0)
            h.current_hp = 100000.0
            h.broken = True
            mod = _bleed_mod(builder, _hero(), h)
            r = p.settle_damage("bleed", h, h, modifier=mod)
            base = min(0.07 * 100000.0, 2 * 3767.5533 * (0.5 + 120 / 40))
            assert r.value == _chain(base, 1.0, 1.0, DEF_ZONE, NON_WEAK_RES_ZONE, 1.0,
                                     1.0, 1.0, 1.0)
            assert h.current_hp == 100000.0 - r.value


# ---------------------------------------------------------------------------
# 数据驱动验收（决策卡 #23 验收②）：新伤害类别 = rulebook 纯数据增加
# ---------------------------------------------------------------------------
class TestDataDrivenNewType:
    def test_new_category_is_pure_data(self, tmp_path, monkeypatch):
        """自定义 rulebook 注入新类别 "pierce"（复用 damage 公式 + direct 规格克隆），
        引擎零改动 settle_damage 直接可结算，与标准簿 direct 同公式预期同值."""
        import yaml

        from hsr_nous.sim_schema import rulebook as rb_mod

        raw = yaml.safe_load(rb_mod.RULEBOOK_PATH.read_text(encoding="utf-8"))
        raw["route"]["pierce"] = {
            "roll": "damage", "expected": "damage_expected",
            "settle": raw["route"]["direct"]["settle"],
        }
        p = tmp_path / "rulebook_pierce.yaml"
        p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
        custom = rb_mod.get_rulebook(p)
        monkeypatch.setattr("hsr_nous.sim.pipeline.get_rulebook", lambda *a, **k: custom)

        act = _action()
        for mode in _MODES:
            pa, pb = _pipe(mode), _pipe(mode)   # 同种子：pa 标准簿 direct，pb 注入簿 pierce
            ra = pa.settle_damage("direct", _hero(), _dummy(), action=act)
            rb = pb.settle_damage("pierce", _hero(), _dummy(), action=act)
            assert rb.value == ra.value
            assert rb.node == ra.node
            crit = _crit_roll(0.05, 0.5)[0] if mode == MODE_ROLL else _crit_expected(0.05, 0.5)
            assert rb.value == _chain(2000.0, 1.0, 1.0, DEF_ZONE, 1.0, 0.9, 1.0, 1.0,
                                      1.0, crit, 1.0, 1.0)
