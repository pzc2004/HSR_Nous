"""翁法罗斯遗器族（123/124/125/126/127/130）e2e：staging→fixtures 验收批.

六套验收 fixture（tests/fixtures/templates/relics/）→ 编译 → 2pc/4pc 面板与行为断言
（手算对轴）；勘正条目见各 fixture 头注。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / crit 0.05/0.5；
景元 1204 atk 698.544 / spd 99 / hp 1164.24 / crit 0.05/0.5（行迹平铺空表——面板=白值）、
神君 1204_lord hp 1164.24 / spd 60 / crit 0.05/0.5（inheritance none 烘焙白值）。
假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、未击破 0.9、期望暴击区 1+cr×cd。
忆灵依赖件（123/124/127）用景元+神君（开战自动在场）承载；面板直读
eng.pipeline.effective_stats（条件光环 enable_if 面板读取即重估——忆灵上下场即时翻转）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

JY_ATK = 698.544
JY_SPD = 99.0
JY_HP = 1164.24


def _basic(aid="t_basic"):
    return {"action_id": aid, "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _inline_member(aid, set_id=None, pieces=0, spd=100, actions=None):
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100},
         "actions": actions if actions is not None else [_basic(f"{aid}_basic")]}
    if set_id is not None:
        m["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    return m


def _build(members):
    return {"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _jy(set_id, pieces, *, allies=()):
    """景元（忆灵=神君开战在场）+ 可选 inline 队友."""
    members = [{"character_template": "1204", "level": 80,
                "relics": {f"slot{i}": {"set_id": set_id} for i in range(pieces)}}]
    members += list(allies)
    return _build(members)


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
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


def _heal(eng, src_id, tgt_id, amount=500.0):
    """真治疗管线 + on_hp_increase 发射（与引擎 hook 侧治疗同一事件契约）."""
    src, tgt = eng.state.actors[src_id], eng.state.actors[tgt_id]
    result = eng.pipeline.heal(src, tgt, amount)
    actual = float(result.node.get("actualAmount", 0.0))
    excess = max(0.0, float(result.value) - actual)
    eng.bus.emit("on_hp_increase", {
        "amount": actual, "excess": excess, "source": src_id,
        "reason": "heal", "target": tgt_id, "action_id": ""}, eng.state)


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


# ---------------------------------------------------------------------------
# 123 凯歌祝捷的英豪（景元+神君承载忆灵）
# ---------------------------------------------------------------------------
class TestSet123:
    def test_2pc_only(self):
        """2 件：atk +12%（698.544×1.12）；无 4pc——忆灵攻击不挂暴伤、速度不变."""
        eng = _make(_jy("123", 2))
        assert math.isclose(_eff(eng, "1204")["atk"], JY_ATK * 1.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD, rel_tol=1e-9), "2 件无速度件"
        _cast(eng, "1204_lord", "120404")
        assert "SET_123_CRITDMG" not in _mods(eng, "1204"), "2 件不触发 4pc"
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.5, rel_tol=1e-9)

    def test_4pc_spd_toggle_with_memosprite(self):
        """4 件：忆灵在场 spd 99×1.06=104.94；忆灵离场回落 99（enable_if 面板即重估）."""
        eng = _make(_jy("123", 4))
        assert math.isclose(_eff(eng, "1204")["atk"], JY_ATK * 1.12, rel_tol=1e-9), "2pc 同发"
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD * 1.06, rel_tol=1e-9), "忆灵在场 +6%"
        eng.dismiss_summon_actor("1204_lord")
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD, rel_tol=1e-9), "忆灵离场即失效"

    def test_4pc_critdmg_on_memosprite_attack(self):
        """4 件：忆灵攻击 → 装备者/忆灵各 +30% 暴伤（0.5+0.3=0.8），duration 2；
        再攻击刷新不叠层（max_stack 1——仍 0.8）；装备者自己行动不触发."""
        eng = _make(_jy("123", 4))
        _cast(eng, "1204", "120401")
        assert "SET_123_CRITDMG" not in _mods(eng, "1204"), "装备者普攻非忆灵攻击"
        _cast(eng, "1204_lord", "120404")
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.8, rel_tol=1e-9), "装备者 +30%"
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.8, rel_tol=1e-9), "忆灵 +30%"
        assert math.isclose(_mods(eng, "1204")["SET_123_CRITDMG"].duration, 2.0), "持续 2 回合"
        _cast(eng, "1204_lord", "120404")
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.8, rel_tol=1e-9), "刷新不叠层"


# ---------------------------------------------------------------------------
# 124 哀歌覆国的诗人
# ---------------------------------------------------------------------------
class TestSet124:
    def test_2pc_only(self):
        """2 件：量子伤 +10%；无 4pc——速度不降（99）、暴击率不变、忆灵无档."""
        eng = _make(_jy("124", 2))
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["quantum"], 0.1, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["crit_rate"], 0.05, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["crit_rate"], 0.05, rel_tol=1e-9)

    def test_4pc_low_tier_with_memosprite(self):
        """4 件（景元 spd 99）：-8% → 91.08 < 95 → 极低速档 +32%（0.05+0.32=0.37）；
        忆灵同档（actor_enter 镜像钩）；量子伤 +10% 同发."""
        eng = _make(_jy("124", 4))
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD * 0.92, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["crit_rate"], 0.37, rel_tol=1e-9), "极低速档"
        assert math.isclose(_eff(eng, "1204_lord")["crit_rate"], 0.37, rel_tol=1e-9), (
            "「该效果同时对装备者的忆灵生效」")
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["quantum"], 0.1, rel_tol=1e-9)

    def test_4pc_mid_tier(self):
        """4 件（inline spd 108）：108×0.92=99.36 ∈ [95,110) → 低速档 +20%（0.25）."""
        eng = _make(_build([_inline_member("w", "124", 4, spd=108)]))
        assert math.isclose(_eff(eng, "w")["spd"], 108 * 0.92, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.25, rel_tol=1e-9), "低速档"
        assert "SET_124_CRIT_TIER_LOW" not in _mods(eng, "w"), "双档互斥"

    def test_4pc_no_tier(self):
        """4 件（inline spd 120）：120×0.92=110.4 ≥ 110 → 无档（crit 0.05）."""
        eng = _make(_build([_inline_member("w", "124", 4, spd=120)]))
        assert math.isclose(_eff(eng, "w")["spd"], 120 * 0.92, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9), "≥110 不加"


# ---------------------------------------------------------------------------
# 125 烈阳惊雷的女武神
# ---------------------------------------------------------------------------
class TestSet125:
    def test_2pc_only(self):
        """2 件：spd +6%（106）；治疗他人不触发甘霖."""
        eng = _make(_build([_inline_member("w", "125", 2), _inline_member("a")]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        _heal(eng, "w", "a")
        assert "SET_125_RAIN" not in _mods(eng, "w"), "2 件不触发 4pc"

    def test_4pc_trigger_and_panel(self):
        """4 件：装备者治疗他人 → 甘霖（spd 100×1.12=112）+ 全队暴伤 +15%
        （装备者/队友各 0.65）+ 触发锁；duration 2/2/1."""
        eng = _make(_build([_inline_member("w", "125", 4), _inline_member("a")]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9), "触发前只 2pc"
        _heal(eng, "w", "a")
        w, a = _mods(eng, "w"), _mods(eng, "a")
        assert {"SET_125_RAIN", "SET_125_RAIN_TEAM", "SET_125_RAIN_LOCK"} <= set(w)
        assert math.isclose(w["SET_125_RAIN"].duration, 2.0)
        assert math.isclose(w["SET_125_RAIN_LOCK"].duration, 1.0), "每回合最多触发1次=锁"
        assert math.isclose(_eff(eng, "w")["spd"], 112.0, rel_tol=1e-9), "甘霖 +6%"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.65, rel_tol=1e-9), "全队含装备者"
        assert math.isclose(_eff(eng, "a")["crit_dmg"], 0.65, rel_tol=1e-9), "光环辐射队友"

    def test_4pc_lock_blocks_retrigger(self):
        """4 件：锁期内再治疗不重复触发（stacks 仍 1、速度不二次叠加——勘正②）."""
        eng = _make(_build([_inline_member("w", "125", 4), _inline_member("a")]))
        _heal(eng, "w", "a")
        _heal(eng, "w", "a")
        assert math.isclose(_mods(eng, "w")["SET_125_RAIN"].stacks, 1.0), "锁阻断重复触发"
        assert math.isclose(_eff(eng, "w")["spd"], 112.0, rel_tol=1e-9), "不叠 12%"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.65, rel_tol=1e-9), "不叠 30%"

    def test_4pc_wrong_source_or_target(self):
        """4 件：治疗装备者自己（target=self）不发；队友互奶（source 非装备者）不发."""
        eng = _make(_build([_inline_member("w", "125", 4), _inline_member("a")]))
        _heal(eng, "w", "w")
        assert "SET_125_RAIN" not in _mods(eng, "w"), "治疗自身不发（以外目标）"
        _heal(eng, "a", "a")
        assert "SET_125_RAIN" not in _mods(eng, "w"), "非装备者来源不发"


# ---------------------------------------------------------------------------
# 126 恶海逐波的船长
# ---------------------------------------------------------------------------
def _126_build(pieces):
    ally = _inline_member("a", actions=[
        _basic("a_basic"),
        {"action_id": "a_buff", "name": "增益", "action_type": "skill",
         "target_type": "ally_single", "skill_point_cost": 1}])
    wearer = _inline_member("w", "126", pieces, actions=[
        _basic("w_basic"),
        {"action_id": "w_ult", "name": "终结技", "action_type": "ultimate",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 1.0}], "energy_cost": 100, "toughness_dmg": 20}])
    return _build([wearer, ally])


def _ult_126(eng):
    st = eng.state.actors["w"]
    st.current_energy = 100.0
    ult = next(a for a in eng.actions_by_actor["w"] if a.action_id == "w_ult")
    assert eng._fire_ultimate(st, ult) is True


class TestSet126:
    def test_2pc_only(self):
        """2 件：暴伤 +16%（0.66）；成为队友技能目标不叠助力."""
        eng = _make(_126_build(2))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.66, rel_tol=1e-9)
        _cast(eng, "a", "a_buff", target_id="w")
        assert "SET_126_HELP_STACK" not in _mods(eng, "w"), "2 件不触发 4pc"

    def test_4pc_help_stacks_cap(self):
        """4 件：队友三指 → 1/2/2 层（cap 2——勘正②）；装备者自身行动/敌方目标不叠."""
        eng = _make(_126_build(4))
        _cast(eng, "a", "a_buff", target_id="w")
        assert math.isclose(_mods(eng, "w")["SET_126_HELP_STACK"].stacks, 1.0)
        _cast(eng, "w", "w_basic")
        assert math.isclose(_mods(eng, "w")["SET_126_HELP_STACK"].stacks, 1.0), "自身行动不叠"
        _cast(eng, "a", "a_buff", target_id="w")
        _cast(eng, "a", "a_buff", target_id="w")
        assert math.isclose(_mods(eng, "w")["SET_126_HELP_STACK"].stacks, 2.0), "最多叠加 2 层"

    def test_4pc_ultimate_consume_and_atk(self):
        """4 件：2 层助力 + 终结技 → 消耗助力、atk +48%（1000×1.48=1480）duration 1；
        终结技自身不吃（挂点在伤害结算后——待实测在案）：1000×1.0×0.5×0.9×1.033=464.85；
        后续普攻吃：1480×0.5×0.9×1.033=687.258."""
        eng = _make(_126_build(4))
        e1 = eng.state.actors["e1"]
        _cast(eng, "a", "a_buff", target_id="w")
        _cast(eng, "a", "a_buff", target_id="w")
        hp1 = e1.current_hp
        _ult_126(eng)
        cz = 1 + 0.05 * 0.66            # 期望暴击区（2pc 暴伤 0.66）
        assert math.isclose(hp1 - e1.current_hp, 1000 * 1.0 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "触发终结技自身不吃 48%（on_ultimate 发射序——待实测）")
        assert "SET_126_HELP_STACK" not in _mods(eng, "w"), "消耗所有助力"
        assert math.isclose(_mods(eng, "w")["SET_126_ATK_BOOST"].duration, 1.0)
        assert math.isclose(_eff(eng, "w")["atk"], 1480.0, rel_tol=1e-9), "攻击 +48%"
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, 1480 * 1.0 * 0.5 * 0.9 * cz, rel_tol=1e-9)

    def test_4pc_ultimate_without_full_stacks(self):
        """4 件：1 层助力放大 → 不消耗、不加攻."""
        eng = _make(_126_build(4))
        _cast(eng, "a", "a_buff", target_id="w")
        _ult_126(eng)
        assert math.isclose(_mods(eng, "w")["SET_126_HELP_STACK"].stacks, 1.0), "不足 2 层不消耗"
        assert "SET_126_ATK_BOOST" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 127 再创天地的救世主（景元+神君承载忆灵）
# ---------------------------------------------------------------------------
class TestSet127:
    def test_2pc_only(self):
        """2 件：暴击率 +8%（0.13）；施放普攻不挂 4pc 件."""
        eng = _make(_jy("127", 2, allies=[_inline_member("a")]))
        assert math.isclose(_eff(eng, "1204")["crit_rate"], 0.13, rel_tol=1e-9)
        _cast(eng, "1204", "120401")
        assert "SET_127_SELF_HP" not in _mods(eng, "1204"), "2 件不触发 4pc"
        assert math.isclose(_eff(eng, "1204")["hp"], JY_HP, rel_tol=1e-9)

    def test_4pc_basic_trigger(self):
        """4 件：普攻（忆灵在场）→ 装备者/忆灵生命 +24%（1164.24×1.24=1443.6576）、
        我方全体增伤 +15%（装备者/忆灵/队友 dmg_bonus.all 各 0.15）."""
        eng = _make(_jy("127", 4, allies=[_inline_member("a")]))
        _cast(eng, "1204", "120401")
        assert math.isclose(_eff(eng, "1204")["hp"], JY_HP * 1.24, rel_tol=1e-9), "装备者 +24%"
        assert math.isclose(_eff(eng, "1204_lord")["hp"], JY_HP * 1.24, rel_tol=1e-9), (
            "「及其忆灵」生命上限（勘正③）")
        for aid in ("1204", "1204_lord", "a"):
            assert math.isclose(_eff(eng, aid)["dmg_bonus"]["all"], 0.15, rel_tol=1e-9), (
                f"我方全体增伤（{aid}）")

    def test_4pc_refresh_not_stack(self):
        """4 件：再战技 = 摘除+重挂（刷新）——生命仍 ×1.24 不翻倍（勘正② A→B 声明序）."""
        eng = _make(_jy("127", 4))
        _cast(eng, "1204", "120401")
        _cast(eng, "1204", "120402")
        assert math.isclose(_eff(eng, "1204")["hp"], JY_HP * 1.24, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.15, rel_tol=1e-9)

    def test_4pc_expires_without_memosprite(self):
        """4 件：忆灵离场后施放普攻 → 旧件纯摘除（「持续至下次施放后」到期语义——
        staging 单钩滞留 bug 勘正②）：生命/增伤回落."""
        eng = _make(_jy("127", 4, allies=[_inline_member("a")]))
        _cast(eng, "1204", "120401")
        eng.dismiss_summon_actor("1204_lord")
        _cast(eng, "1204", "120401")
        assert "SET_127_SELF_HP" not in _mods(eng, "1204"), "忆灵缺席=到期摘除"
        assert "SET_127_TEAM_DMG" not in _mods(eng, "1204")
        assert math.isclose(_eff(eng, "1204")["hp"], JY_HP, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["dmg_bonus"].get("all", 0.0), 0.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 130 应天涉远的卜者
# ---------------------------------------------------------------------------
def _130_build(pieces, spd=100):
    wearer = _inline_member("w", "130", pieces, spd=spd, actions=[
        _basic("w_basic"),
        {"action_id": "w_ela", "name": "欢愉技", "action_type": "elation_skill",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 1.0}], "energy_gain": 0, "toughness_dmg": 0}])
    return _build([wearer, _inline_member("a")])


class TestSet130:
    def test_2pc_only(self):
        """2 件：spd +6%（106）；无档位；施放欢愉技不发全体欢愉度."""
        eng = _make(_130_build(2))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)
        _cast(eng, "w", "w_ela")
        assert math.isclose(_eff(eng, "w")["elation"], 0.0, rel_tol=1e-9), "2 件不触发 4pc"

    def test_4pc_below_threshold(self):
        """4 件（spd 100）：100×1.06=106 < 120 → 无档（crit 0.05）."""
        eng = _make(_130_build(4, spd=100))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)

    def test_4pc_tier1(self):
        """4 件（spd 114）：114×1.06=120.84 ≥ 120 → 一档 +10%（0.15）；档位判定含 2pc."""
        eng = _make(_130_build(4, spd=114))
        assert math.isclose(_eff(eng, "w")["spd"], 114 * 1.06, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.15, rel_tol=1e-9), "速度阈值一档"
        assert "SET_130_CRIT_TIER_T2" not in _mods(eng, "w"), "双档互斥"

    def test_4pc_tier2(self):
        """4 件（spd 151）：151×1.06=160.06 ≥ 160 → 二档 +18%（0.23）."""
        eng = _make(_130_build(4, spd=151))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.23, rel_tol=1e-9), "速度阈值二档"

    def test_4pc_first_elation_skill_team_elation(self):
        """4 件：首次欢愉技 → 我方全体欢愉度 +10%（装备者/队友 elation 各 0.1）+ 首次闩；
        再放不重复（闩阻断 + max_stack 1 幂等）."""
        eng = _make(_130_build(4, spd=100))
        _cast(eng, "w", "w_ela")
        assert math.isclose(_eff(eng, "w")["elation"], 0.1, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["elation"], 0.1, rel_tol=1e-9), "我方全体"
        assert "SET_130_FIRST_LOCK" in _mods(eng, "w"), "每场战斗首次闩"
        _cast(eng, "w", "w_ela")
        assert math.isclose(_eff(eng, "w")["elation"], 0.1, rel_tol=1e-9), "无法叠加"
