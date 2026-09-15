"""欢愉（Elation）光锥族 e2e：staging→fixtures 验收批.

五件验收 fixture（tests/fixtures/templates/light_cones/）→ 编译 → 白值三围 + 机制行为
断言（手算对轴）+ 叠影 S1/S5 差分；勘正条目见各 fixture 头注。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / def 0 / crit 0.05/0.5 /
energy_regen 1.0 / elation 0。假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、
未击破 0.9。笑点=队伍账 eng.state.punchline 直写对轴（21_elation §21.3）；
阿哈时刻事件按契约载荷直发（B40 P2b 事件词表——LC hook 触发域单测）。
命途门槛：本族 5 件官方文本均无「装备者命途为欢愉时」条件（ranks.json desc 终审）
——不设 path_of 门，留档测试钉死该决策。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

#: 光锥白值三围（生成器数值区照抄——验收只读不手改；loader 白值病修复后官方正确值）
LC_BASE = {
    "20023": (740.8800000000001, 370.44000000000005, 264.6),
    "20024": (846.72, 317.52, 264.6),
    "21065": (952.56, 529.2, 396.9),
    "23054": (1058.4, 529.2, 529.2),
    "23058": (952.56, 635.04, 463.04999999999995),
}


def _basic(aid="t_basic"):
    return {"action_id": aid, "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1,
            "energy_gain": 20}


def _elation(aid="t_elation"):
    return {"action_id": aid, "name": "欢愉技", "action_type": "elation_skill",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 5}


def _inline(lc_id, *, sup=1, path=None, aid="w", actions=None, max_energy=100):
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": max_energy},
         "actions": actions if actions is not None else [_basic(f"{aid}_basic")]}
    if lc_id:
        m["light_cone_template"] = lc_id
        m["light_cone"] = {"superimposition": sup}
    if path:
        m["path"] = path
    return m


def _build(members):
    return {"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build, *, sp=3):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=sp)
    eng.setup()
    return eng


def _cast(eng, owner, aid, target_id="e1"):
    """手动施放（8009 模子）：行动结算 + 补发 on_action（hook 触发域）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, owner, aid, energy, target_id="e1"):
    st = eng.state.actors[owner]
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = float(energy)
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    assert eng._fire_ultimate(st, a) is True


def _aha(eng, phase, actors=("w",)):
    """阿哈时刻事件（契约载荷：consumed/extra/actors——23_event_hook §23.4）."""
    eng.bus.emit(f"aha_instant_{phase}", {
        "consumed": 5.0, "extra": 0, "actors": list(actors)}, eng.state)


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


def _white(lc_id, *, hp_mult=1.0, atk_mult=1.0):
    """白值三围断言（mult=该锥 S1 常驻 pct 件口径，同 memory 族模子）."""
    hp, atk, dfn = LC_BASE[lc_id]
    eng = _make(_build([_inline(lc_id)]))
    eff = _eff(eng, "w")
    assert math.isclose(eff["hp"], (3000 + hp) * hp_mult, rel_tol=1e-9), f"{lc_id} hp 白值"
    assert math.isclose(eff["atk"], (1000 + atk) * atk_mult, rel_tol=1e-9), f"{lc_id} atk 白值"
    assert math.isclose(eff["def_"], dfn, rel_tol=1e-9), f"{lc_id} def 白值"


# ---------------------------------------------------------------------------
# 20023 嗤笑（3★）：阿哈时刻发动 → 欢愉度提高，持续到时刻结束
# ---------------------------------------------------------------------------
class TestLC20023:
    def test_white_stats(self):
        _white("20023")

    def test_aha_window_elation(self):
        """S1：阿哈时刻开始 → 欢愉度 +16%；结束 → 归零；重开再挂（max_stack 1 幂等）."""
        eng = _make(_build([_inline("20023")]))
        assert math.isclose(_eff(eng, "w")["elation"], 0.0, rel_tol=1e-9), "时刻外无加成"
        _aha(eng, "start")
        assert math.isclose(_eff(eng, "w")["elation"], 0.16, rel_tol=1e-9), "时刻内 +16%"
        assert math.isclose(_mods(eng, "w")["LC_20023_ELATION_UP"].stacks, 1.0)
        _aha(eng, "end")
        assert math.isclose(_eff(eng, "w")["elation"], 0.0, rel_tol=1e-9), "时刻结束即摘"
        _aha(eng, "start")
        assert math.isclose(_eff(eng, "w")["elation"], 0.16, rel_tol=1e-9), "重开再挂"
        assert math.isclose(_mods(eng, "w")["LC_20023_ELATION_UP"].stacks, 1.0)

    def test_s5_elation_diff(self):
        """S5（#1=0.32）：时刻内欢愉度 +32%."""
        eng = _make(_build([_inline("20023", sup=5)]))
        _aha(eng, "start")
        assert math.isclose(_eff(eng, "w")["elation"], 0.32, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 20024 残泪（3★）：笑点 ≥10 → 暴击伤害提高
# ---------------------------------------------------------------------------
class TestLC20024:
    def test_white_stats(self):
        _white("20024")

    def test_punchline_threshold_toggle(self):
        """S1：笑点 0/9 → 暴伤 0.5 不加；10/15 → 0.5+0.2=0.7（enable_if 面板读取即重估）."""
        eng = _make(_build([_inline("20024")]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "0 笑点不加"
        eng.state.punchline = 9.0
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "9 笑点不加"
        eng.state.punchline = 10.0
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.7, rel_tol=1e-9), "10 笑点门槛达标"
        eng.state.punchline = 15.0
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.7, rel_tol=1e-9), "门槛以上维持"
        eng.state.punchline = 3.0
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "回落即失效"

    def test_s5_crit_diff(self):
        """S5（#2=0.4）：达标暴伤 0.9."""
        eng = _make(_build([_inline("20024", sup=5)]))
        eng.state.punchline = 10.0
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.9, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21065 今日好手气（4★）：暴击率常驻 + 欢愉技叠层欢愉度（至多 2 层）
# ---------------------------------------------------------------------------
class TestLC21065:
    def test_white_stats(self):
        _white("21065")

    def test_elation_skill_stacks_cap2(self):
        """S1：暴击率 0.05+0.12=0.17；欢愉技×3 → 层数 1/2/2（钳 #3=2）、欢愉度
        0.12/0.24/0.24（数值件 replace 烘焙=参数×现场层数）."""
        eng = _make(_build([_inline("21065", actions=[_basic(), _elation()])]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9), "暴击率常驻"
        _cast(eng, "w", "t_elation")
        assert math.isclose(_mods(eng, "w")["LC_21065_LUCKY_STACK"].stacks, 1.0)
        assert math.isclose(_eff(eng, "w")["elation"], 0.12, rel_tol=1e-9)
        _cast(eng, "w", "t_elation")
        assert math.isclose(_mods(eng, "w")["LC_21065_LUCKY_STACK"].stacks, 2.0)
        assert math.isclose(_eff(eng, "w")["elation"], 0.24, rel_tol=1e-9)
        _cast(eng, "w", "t_elation")
        assert math.isclose(_mods(eng, "w")["LC_21065_LUCKY_STACK"].stacks, 2.0), "钳 2 层"
        assert math.isclose(_eff(eng, "w")["elation"], 0.24, rel_tol=1e-9), "叠层封顶"

    def test_basic_no_stack(self):
        """普攻非欢愉技——不叠层."""
        eng = _make(_build([_inline("21065", actions=[_basic(), _elation()])]))
        _cast(eng, "w", "t_basic")
        assert "LC_21065_LUCKY_STACK" not in _mods(eng, "w")

    def test_s5_stacks_diff(self):
        """S5（#1=0.2 / #2=0.2）：暴击率 0.25；两层欢愉度 0.4."""
        eng = _make(_build([_inline("21065", sup=5, actions=[_basic(), _elation()])]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.25, rel_tol=1e-9)
        _cast(eng, "w", "t_elation")
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "w")["elation"], 0.4, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23054 当她决定看见（5★）：速度常驻 + 上上签（进战/对我方终结技）+ 波次回能
# ---------------------------------------------------------------------------
class TestLC23054:
    def test_white_stats(self):
        _white("23054")

    def test_battle_start_great_fortune(self):
        """S1：spd 118；进战上上签——全队暴击率 +10%/暴伤 +30%（光环辐射队友）、
        装备者自身能量恢复效率 +12%（队友不吃）×3 回合."""
        eng = _make(_build([_inline("23054"), _inline(None, aid="a")]))
        assert math.isclose(_eff(eng, "w")["spd"], 118.0, rel_tol=1e-9), "速度常驻 #1"
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.15, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.8, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["crit_rate"], 0.15, rel_tol=1e-9), "团队暴击率光环"
        assert math.isclose(_eff(eng, "a")["crit_dmg"], 0.8, rel_tol=1e-9), "团队暴伤光环"
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.12, rel_tol=1e-9), "自身 ERR"
        assert math.isclose(_eff(eng, "a")["energy_regen"], 1.0, rel_tol=1e-9), "ERR 不辐射"
        assert math.isclose(_mods(eng, "w")["LC_23054_GREAT_FORTUNE"].duration, 3.0)

    def _ult_build(self, sup=1):
        actions = [_basic(),
                   {"action_id": "w_ult_ally", "name": "对我方终结技", "action_type": "ultimate",
                    "target_type": "ally_single", "energy_cost": 100},
                   {"action_id": "w_ult_foe", "name": "对敌终结技", "action_type": "ultimate",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "energy_cost": 100, "toughness_dmg": 30}]
        return _build([_inline("23054", sup=sup, actions=actions), _inline(None, aid="a")])

    def test_ult_on_ally_regrant(self):
        """对我方目标施放终结技 → 上上签重发（摘除后重挂；stacks 恒 1 不叠层）."""
        eng = _make(self._ult_build())
        w = eng.state.actors["w"]
        eng._remove_modifier(w, "LC_23054_GREAT_FORTUNE")
        eng._remove_modifier(w, "LC_23054_GREAT_FORTUNE_ERR")
        _ult(eng, "w", "w_ult_ally", 100, target_id="a")
        assert math.isclose(_eff(eng, "a")["crit_rate"], 0.15, rel_tol=1e-9), "重发团队光环"
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.12, rel_tol=1e-9), "重发自身 ERR"
        assert math.isclose(_mods(eng, "w")["LC_23054_GREAT_FORTUNE"].stacks, 1.0)

    def test_ult_on_enemy_no_regrant(self):
        """对敌方施放终结技 ≠ 对我方——不重发（勘正②：staging controlled() 全无关）."""
        eng = _make(self._ult_build())
        w = eng.state.actors["w"]
        eng._remove_modifier(w, "LC_23054_GREAT_FORTUNE")
        eng._remove_modifier(w, "LC_23054_GREAT_FORTUNE_ERR")
        _ult(eng, "w", "w_ult_foe", 100)
        assert "LC_23054_GREAT_FORTUNE" not in _mods(eng, "w")

    def test_wave_start_energy(self):
        """波次开始 → 回 15 能（统一管线乘 ERR：15×1.12=16.8——「固定」是否豁免 ERR
        待实测在案，见 fixture notes）."""
        eng = _make(_build([_inline("23054")]))
        st = eng.state.actors["w"]
        assert math.isclose(st.current_energy, 0.0)
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(st.current_energy, 15.0 * 1.12, rel_tol=1e-9)

    def test_s5_full_diff(self):
        """S5（#1=0.3 / #2=0.14 / #3=0.6 / #5=0.2）：spd 130、暴击率 0.19、暴伤 1.1、ERR 1.2."""
        eng = _make(_build([_inline("23054", sup=5), _inline(None, aid="a")]))
        assert math.isclose(_eff(eng, "w")["spd"], 130.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["crit_rate"], 0.19, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["crit_dmg"], 1.1, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.2, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23058 邂逅于下一个花季（5★）：暴伤常驻 + 能量恢复效率（含超出档）+ 欢愉技易伤
# ---------------------------------------------------------------------------
class TestLC23058:
    def test_white_stats(self):
        _white("23058")

    def test_crit_dmg_and_err_base(self):
        """S1：暴伤 0.5+0.6=1.1；能量上限 100（≤120 无超出）→ ERR 1.1."""
        eng = _make(_build([_inline("23058")]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 1.1, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.1, rel_tol=1e-9), "无超出档"

    def test_err_excess_tier(self):
        """能量上限 160：超出 40 → ERR=1+0.1+40/10×0.003=1.112（$self.max_energy 急切槽——
        stat_of 死键排雷，勘正③）；普攻回 20×1.112=22.24."""
        eng = _make(_build([_inline("23058", max_energy=160)]))
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.112, rel_tol=1e-9)
        st = eng.state.actors["w"]
        _cast(eng, "w", "w_basic")
        assert math.isclose(st.current_energy, 20 * 1.112, rel_tol=1e-9)

    def test_elation_skill_vulnerability(self):
        """S1：欢愉技 → 敌方全体承伤 +15%×2 回合（两假人同挂）；重放 replace 不叠层；
        普攻伤害对轴：atk 1635.04 × 防御区 0.5 × 未击破 0.9 × 期望暴击 1.055 × 易伤 1.15."""
        eng = _make(_build([_inline("23058", actions=[_basic(), _elation()])]))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        atk, cz = 1000 + 635.04, 1 + 0.05 * 1.1
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * 0.5 * 0.9 * cz, rel_tol=1e-9), "施放前无易伤"
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.15, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "e2")["vulnerability"], 0.15, rel_tol=1e-9), "敌方全体"
        assert math.isclose(_mods(eng, "e1")["LC_23058_VULNERABILITY"].duration, 2.0)
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.15, rel_tol=1e-9), (
            "同类效果无法叠加（replace 整换）")
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * 0.5 * 0.9 * cz * 1.15, rel_tol=1e-9)

    def test_s5_vulnerability_diff(self):
        """S5（#1=1.2 / #2=0.3）：暴伤 1.7；承伤 +30%."""
        eng = _make(_build([_inline("23058", sup=5, actions=[_basic(), _elation()])]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 1.7, rel_tol=1e-9)
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.3, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 族级留档：官方文本无命途门槛——path 不匹配照触发（本族代表两件）
# ---------------------------------------------------------------------------
class TestElationNoPathGate:
    def test_21065_on_non_elation_path(self):
        """21065 挂 path='destruction' 装备员：暴击率常驻与欢愉技叠层照触发——文本无
        「装备者命途为欢愉时」条件（ranks.json desc 终审，验收决策在案）."""
        eng = _make(_build([_inline("21065", path="destruction",
                                    actions=[_basic(), _elation()])]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9)
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "w")["elation"], 0.12, rel_tol=1e-9)

    def test_23058_on_non_elation_path(self):
        """23058 挂 path='destruction'：欢愉技易伤照触发."""
        eng = _make(_build([_inline("23058", path="destruction",
                                    actions=[_basic(), _elation()])]))
        _cast(eng, "w", "t_elation")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.15, rel_tol=1e-9)
