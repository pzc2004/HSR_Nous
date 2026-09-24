"""超击破体系端到端（B38）：③ 超击破结算分支 + ④ 云火昭虚韧性条.

口径常数：假人 def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、已击破 base_universal=1.0；
超击破基数 = 3767.5533/10 × 有效削韧（rulebook super_break_base_multi——名义削韧，
与实际削韧无关）；不吃攻击/增伤区/双暴/虚弱。火击破系数 2.0（break_effects.fire）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

BASE_PER_TOUGH = 3767.5533 / 10          # super_break_base_multi 系数
BREAK_DMG = 3767.5533 * 2.0 * 3.0 * 2.0 * 0.5   # 火击破：3767.5533×scaling 2.0×(0.5+100/40)×be 2.0×防御 0.5
DIRECT = 1000 * 0.5                       # 直伤：atk 1000×倍率 1.0×防御区（暴击率 0 → 期望区 1）


def _engine(hero_stats=None, max_toughness=100):
    hero = Actor(actor_id="hero", name="hero", level=80,
                 stats=hero_stats or StatBlock(atk=1000, spd=100, hp=3000, max_energy=100,
                                               crit_rate=0.0, crit_dmg=0.5, break_effect=1.0))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=max_toughness,
                                  weakness=["fire"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0)
    eng.setup()
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    return eng


def _fire(**kw):
    base = dict(action_id="s", name="斩", action_type="skill", target_type="single",
                damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
    base.update(kw)
    return Action(**base)


def _grant_conversion(eng, rate=1.0, boost=0.0):
    effs = {"super_break_modifier": rate}
    if boost:
        effs["super_break_dmg_boost"] = boost
    eng._apply_modifier(eng.state.actors["hero"], Modifier(
        modifier_id="SB_CONV", name="超击破转化", modifier_type="buff",
        duration=0, dispellable=False, stat_effects=effs))


def _hit(eng, action=None):
    """对 e1 直调一击（行动层主路径——含直伤/削韧/超击破全链）."""
    eng._execute_action(eng.state.actors["hero"], action or _fire())


class TestSuperBreakSettlement:
    def test_basic_super_break_value(self):
        """基础链：击破后下一击 → 超击破 = 有效削韧 10×系数×be 2.0×防御区（转化 1.0）."""
        eng = _engine()
        _grant_conversion(eng, 1.0)
        tgt = eng.state.actors["e1"]
        _hit(eng, _fire(toughness_dmg=120))   # 击破
        assert tgt.broken
        hp = tgt.current_hp
        _hit(eng)
        sb = 10 * BASE_PER_TOUGH * 2.0 * 0.5
        assert math.isclose(hp - tgt.current_hp, DIRECT + sb, rel_tol=1e-9)

    def test_breaking_hit_itself_no_super_break(self):
        """破击段本身不触发（双击破段序：破击段=击破伤害 only，后续段才超击破）."""
        eng = _engine()
        _grant_conversion(eng, 1.0)
        events = []
        eng.bus.subscribe("on_super_break", lambda et, p, ctx: events.append(p))
        _hit(eng, _fire(toughness_dmg=120))
        assert eng.state.actors["e1"].broken and not events, "破击段不出超击破"
        _hit(eng)
        assert len(events) == 1 and events[0]["action_id"] == "s"
        assert events[0]["element"] == "fire"

    def test_no_conversion_source_no_super_break(self):
        """无转换源（池=0）→ 只出直伤，不造成超击破（spec：无转换源则为 0）."""
        eng = _engine()
        _hit(eng, _fire(toughness_dmg=120))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _hit(eng)
        assert math.isclose(hp - tgt.current_hp, DIRECT, rel_tol=1e-9)

    def test_ignores_dmg_bonus_and_crit(self):
        """不吃增伤区/暴击：all_dmg+100%、暴击 100%/200%——直伤翻六倍，超击破照旧."""
        eng = _engine(hero_stats=StatBlock(
            atk=1000, spd=100, hp=3000, max_energy=100,
            crit_rate=1.0, crit_dmg=2.0, break_effect=1.0))
        _grant_conversion(eng, 1.0)
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="DMG", name="增伤", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"all_dmg": 1.0}))
        _hit(eng, _fire(toughness_dmg=120))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _hit(eng)
        direct = 1000 * 0.5 * 2.0 * 3.0     # 增伤区 2.0 × 期望暴击区 3.0
        sb = 10 * BASE_PER_TOUGH * 2.0 * 0.5
        assert math.isclose(hp - tgt.current_hp, direct + sb, rel_tol=1e-9)

    def test_super_break_boost_pool(self):
        """超击破增伤池（super_break_dmg_boost 0.5 → ×1.5，仅超击破生效）."""
        eng = _engine()
        _grant_conversion(eng, 1.0, boost=0.5)
        _hit(eng, _fire(toughness_dmg=120))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _hit(eng)
        sb = 10 * BASE_PER_TOUGH * 2.0 * 0.5 * 1.5
        assert math.isclose(hp - tgt.current_hp, DIRECT + sb, rel_tol=1e-9)

    def test_efficiency_scales_nominal_toughness(self):
        """削韧效率进名义有效削韧（weakness_break_efficiency_boost 0.5 → 10×1.5=15）."""
        eng = _engine()
        _grant_conversion(eng, 1.0)
        eng._apply_modifier(eng.state.actors["hero"], Modifier(
            modifier_id="EFF", name="削韧效率", modifier_type="buff",
            duration=0, dispellable=False,
            stat_effects={"weakness_break_efficiency_boost": 0.5}))
        _hit(eng, _fire(toughness_dmg=120))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        _hit(eng)
        sb = 15 * BASE_PER_TOUGH * 2.0 * 0.5
        assert math.isclose(hp - tgt.current_hp, DIRECT + sb, rel_tol=1e-9)

    def test_hook_segment_also_triggers(self):
        """hook 段（附加/弹射族）带削韧命中已击破目标同样触发——载荷归父语境行动 id."""
        eng = _engine()
        _grant_conversion(eng, 1.0)
        _hit(eng, _fire(toughness_dmg=120))
        tgt = eng.state.actors["e1"]
        events = []
        eng.bus.subscribe("on_super_break", lambda et, p, ctx: events.append(p))
        hp = tgt.current_hp
        eng._hooks._run_hook_effect(eng.state.actors["hero"], {
            "effect_type": "deal_damage", "name": "测试附加段", "target": "enemy_first",
            "damage_type": "fire", "amount": "100", "toughness_dmg": 10},
            {"action_id": "parent_x"})
        sb = 10 * BASE_PER_TOUGH * 2.0 * 0.5
        assert math.isclose(hp - tgt.current_hp, 100 * 0.5 + sb, rel_tol=1e-9)
        assert events and events[0]["action_id"] == "parent_x", "hook 段载荷归父语境行动 id"


class TestCloudflameBar:
    def _add_bar(self, eng, amount=50):
        eng._hooks._run_hook_effect(eng.state.actors["hero"], {
            "effect_type": "add_toughness_bar", "target": "enemy_first",
            "amount": amount}, {})

    def test_main_break_effects_then_added_bar_damage_only(self):
        """云火昭流：主条破=击破态+效果（灼烧/推条——载体=主序末条）；
        虚条破=只再吃击破伤害（不重复击破效果、击破态维持、条尽）."""
        eng = _engine()
        tgt = eng.state.actors["e1"]
        self._add_bar(eng)
        assert tgt.extra_bars == [50.0]
        _hit(eng, _fire(toughness_dmg=120))   # 主条破
        assert tgt.broken, "主条破即置击破态（云火昭在册不挡载体判定）"
        assert tgt.bar_index == 1 and tgt.toughness == 50.0, "虚条切入满值承接"
        assert "BURN_DOT" in tgt.modifiers or any(
            m.modifier_type == "dot" for m in tgt.modifiers.values()), "主条破发灼烧"
        mods_after_main = dict(tgt.modifiers)
        hp = tgt.current_hp
        _hit(eng, _fire(toughness_dmg=60))    # 虚条破
        assert math.isclose(hp - tgt.current_hp, DIRECT + BREAK_DMG, rel_tol=1e-9), (
            "虚条破=直伤+击破伤害（每条结算——主条破已含第一笔，本击第二笔）")
        assert dict(tgt.modifiers) == mods_after_main, "虚条破不重复击破效果"
        assert tgt.broken and tgt.bars_exhausted, "击破态维持 + 条尽"

    def test_recovery_recycles_added_bar(self):
        """恢复后云火昭随下周期再切入：added_bars 不消失，主条破仍置击破态."""
        eng = _engine()
        tgt = eng.state.actors["e1"]
        self._add_bar(eng)
        _hit(eng, _fire(toughness_dmg=120))
        _hit(eng, _fire(toughness_dmg=60))
        assert tgt.bars_exhausted
        # 恢复（与恢复点同口径手动复位——test_small_primitives 同法）
        tgt.broken = False
        tgt.bar_index = 0
        tgt.toughness = float(tgt.actor.stats.max_toughness)
        assert tgt.extra_bars == [50.0] and not tgt.bars_exhausted
        _hit(eng, _fire(toughness_dmg=120))
        assert tgt.broken, "第二周期主条破仍置击破态"
        assert tgt.bar_index == 1 and tgt.toughness == 50.0, "云火昭第二周期再切入"
