"""欢愉伤害路由（B40 P2a）端到端：行动层 elation 行键 / hook category "elation" /
punchline_source 定槽（池 vs 好活当赏）/ 乘区生效与隔离（不吃增伤）/ 编译互斥闸。

模子同 P1a/P1b（tmp_path 微型模板）。口径常数：等级系数 7535.107、假人 def 1000 →
防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9、期望暴击区 1.025（crit 0.05/0.5）、
面板 elation 0.5（elation_multi=1.5）；pool=20 → punchline_multi=1+100/260≈1.384615；
banger=40 → 1+200/280≈1.714286。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

LV_COEF = 7535.107
DEF_ZONE = 0.5
CRIT_EXP = 1.025
ELATION = 0.5                    # 面板欢愉度（elation_multi=1.5）
POOL = 20.0
POOL_MULTI = 1 + 5 * POOL / (POOL + 240)
BANGER = 40.0
BANGER_MULTI = 1 + 5 * BANGER / (BANGER + 240)

_DPS = """\
actor_id: "900301"
name: "欢愉输出测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100, elation: 0.5,
             crit_rate: 0.05, crit_dmg: 0.5}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "fire"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
  - action_id: "t_elation"
    name: "测试欢愉技"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "fire"
    scaling: [{elation: 0.1}, {elation: 0.15}, {elation: 0.2}, {elation: 0.25},
              {elation: 0.3}, {elation: 0.35}, {elation: 0.4}, {elation: 0.45},
              {elation: 0.48}, {elation: 0.5}]
hooks:
  - event: "on_action"
    condition: "$event.actor == '900301' && $event.action_id == 't_basic'"
    effects:
      - effect_type: "deal_damage"
        name: "好活附伤"
        category: "elation"
        damage_type: "fire"
        amount: 0.4
  - event: "on_action"
    condition: "$event.actor == '900301' && $event.action_id == 't_elation'"
    effects:
      - effect_type: "deal_damage"
        name: "池附伤"
        category: "elation"
        damage_type: "fire"
        amount: 0.4
        punchline_source: "res_punchline"
        action_type: "elation_skill"
"""

_BAD = """\
actor_id: "900302"
name: "互斥测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "fire"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
hooks:
  - event: "on_action"
    condition: "$event.actor == '900302'"
    effects:
      - effect_type: "deal_damage"
        name: "坏欢愉"
        category: "elation"
        damage_type: "fire"
        amount: 0.4
        toughness_dmg: 10
"""

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture()
def roots(tmp_path):
    d = tmp_path / "characters"
    d.mkdir()
    (d / "900301_欢愉输出.yaml").write_text(_DPS, encoding="utf-8")
    (d / "900302_互斥.yaml").write_text(_BAD, encoding="utf-8")
    return [str(tmp_path)]


def _make(roots, tpl="900301"):
    c = compile_encounter({"build": {"team": [
        {"character_template": tpl, "level": 80}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}},
        _STAGE, template_roots=roots)
    eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _st(eng):
    return eng.state.actors["900301"]


def _cast(eng, aid):
    st = _st(eng)
    a = next(x for x in eng.actions_by_actor["900301"] if x.action_id == aid)
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "900301", "action_type": a.action_type, "action_id": a.action_id,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


def _apply(eng, stat, val):
    st = _st(eng)
    eng._modifiers._apply_modifier_spec(st, {
        "modifier_id": f"T_{stat}", "name": "测试件", "modifier_type": "buff",
        "duration": 0, "stat_effects": {stat: val}}, st)


class TestActionLevelRoute:
    def test_elation_skill_full_formula(self, roots):
        """行动层 elation 行键：7535.107×0.5×(1+0.5)×池(20)×期望暴击×防御×抗性×未击破
        （+同模板池附伤钩 0.4 段——两段同池定槽合并对轴）。"""
        eng = _make(roots)
        eng._gain_resource(_st(eng), "punchline", POOL)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "t_elation")
        skill_part = (LV_COEF * 0.5 * (1 + ELATION) * POOL_MULTI * CRIT_EXP
                      * DEF_ZONE * 1.0 * 0.9)
        hook_part = (LV_COEF * 0.4 * (1 + ELATION) * POOL_MULTI * CRIT_EXP
                     * DEF_ZONE * 1.0 * 0.9)
        assert math.isclose(hp - tgt.current_hp, skill_part + hook_part, rel_tol=1e-9), (
            "欢愉技全公式链（池定槽——action 层恒取阿哈笑点池实时值）")

    def test_no_generic_dmg_bonus(self, roots):
        """隔离：通用增伤 all_dmg 0.5 + 火伤 0.5 挂上后伤害不变（不吃增伤区）。"""
        eng = _make(roots)
        eng._gain_resource(_st(eng), "punchline", POOL)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "t_elation")
        base = hp - tgt.current_hp
        eng.state.actors["e1"].current_hp = 1e9
        _apply(eng, "all_dmg", 0.5)
        _apply(eng, "dmg_fire", 0.5)
        hp2 = tgt.current_hp
        _cast(eng, "t_elation")
        assert math.isclose(hp2 - tgt.current_hp, base, rel_tol=1e-9), (
            "通用增伤/属性增伤不进欢愉公式（21_elation.md §21.2 隔离语义）")

    def test_elation_zones_fold_in(self, roots):
        """欢愉增伤 elation_dmg_boost 0.3 ×1.3、增笑 merrymake 0.2 ×1.2 正常生效
        （行动段 0.5 与 hook 段 0.4 同吃两区）。"""
        eng = _make(roots)
        eng._gain_resource(_st(eng), "punchline", POOL)
        tgt = eng.state.actors["e1"]
        _apply(eng, "elation_dmg_boost", 0.3)
        hp = tgt.current_hp
        _cast(eng, "t_elation")
        expect_boost = (LV_COEF * (0.5 + 0.4) * (1 + ELATION) * 1.3 * POOL_MULTI * CRIT_EXP
                        * DEF_ZONE * 0.9)
        assert math.isclose(hp - tgt.current_hp, expect_boost, rel_tol=1e-9), "欢愉增伤区"
        eng.state.actors["e1"].current_hp = 1e9
        _apply(eng, "merrymake", 0.2)
        hp2 = tgt.current_hp
        _cast(eng, "t_elation")
        assert math.isclose(hp2 - tgt.current_hp, expect_boost * 1.2, rel_tol=1e-9), "增笑区"


class TestHookElation:
    def test_banger_default_source(self, roots):
        """hook category elation 缺省定槽=好活当赏合并值：普攻触发 0.4 纯倍率附伤."""
        eng = _make(roots)
        eng._gain_resource(_st(eng), "certified_banger", BANGER)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "t_basic")
        elation_part = (LV_COEF * 0.4 * (1 + ELATION) * BANGER_MULTI * CRIT_EXP
                        * DEF_ZONE * 0.9)
        direct_part = 1000 * 1.0 * DEF_ZONE * 0.9 * CRIT_EXP
        assert math.isclose(hp - tgt.current_hp, direct_part + elation_part, rel_tol=1e-9), (
            "直伤 + 欢愉附伤（好活当赏 40 合并值定槽）")

    def test_pool_explicit_source(self, roots):
        """punchline_source: res_punchline 显式定槽=阿哈笑点池实时值（欢愉技段族）。"""
        eng = _make(roots)
        eng._gain_resource(_st(eng), "punchline", POOL)
        eng._gain_resource(_st(eng), "certified_banger", BANGER)
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _cast(eng, "t_elation")
        skill_part = (LV_COEF * 0.5 * (1 + ELATION) * POOL_MULTI * CRIT_EXP
                      * DEF_ZONE * 0.9)
        hook_part = (LV_COEF * 0.4 * (1 + ELATION) * POOL_MULTI * CRIT_EXP
                     * DEF_ZONE * 0.9)
        assert math.isclose(hp - tgt.current_hp, skill_part + hook_part, rel_tol=1e-9), (
            "行动段 + hook 段同池定槽（banger 40 在场也不误取——显式槽胜出）")


class TestCompileGates:
    def test_elation_toughness_mutex(self, roots):
        with pytest.raises(ValueError, match="互斥"):
            compile_encounter({"build": {"team": [
                {"character_template": "900302", "level": 80}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "true", "action": "basic", "priority": 0}]}}},
                _STAGE, template_roots=roots)
