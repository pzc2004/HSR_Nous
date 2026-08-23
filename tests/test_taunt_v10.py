"""嘲讽值加权选目标（v1.0，mechanics 10_taunt_system 落地）.

覆盖：
- 基础嘲讽解析：显式 stats.taunt > 0 优先 > 忆灵表（按名）> 命途表 > 兜底 100（rulebook taunt 节）
- taunt_eff = base × (1 + Σ aggro_boost 池)（effective_stats 派生，池内加算）
- 期望模式确定性取 taunt_eff 最高者（实现约定，并列按编队序——max 取首个最大）
- roll 模式按 taunt_eff 加权（种子化，B16 同种子两局全等）
- 覆盖层：forced_taunt 件挂敌方 → 必打 source（Fandom Aggro "ignoring Aggro and Lock On"）
"""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _ally(actor_id: str, name: str, path: str = "", taunt: float = 0.0):
    return Actor(actor_id=actor_id, name=name, level=80, path=path,
                 stats=StatBlock(hp=3000, def_=1000, spd=100, max_energy=100, taunt=taunt))


def _enemy():
    return Actor(actor_id="e", name="强敌", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=100, spd=50, max_toughness=9999,
                                 weakness=["fire"]))


def _enemy_atk():
    return Action(action_id="e_atk", name="灭世一击", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _engine(allies, mode=MODE_EXPECTED, seed=None):
    enc = Encounter(encounter_id="t", name="t", actors=[*allies, _enemy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"e": [_enemy_atk()]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=mode, seed=seed,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _pick(eng):
    t, _ = eng._resolve_targets(eng.state.actors["e"], _enemy_atk())
    return t


class TestBaseTaunt:
    def test_path_table(self):
        """命途表：destruction=125、hunt=75（rulebook taunt.path_base）."""
        eng = _engine([_ally("h1", "毁灭员", path="destruction"), _ally("h2", "巡猎员", path="hunt")])
        eff1 = eng.pipeline.effective_stats(eng.state.actors["h1"])
        eff2 = eng.pipeline.effective_stats(eng.state.actors["h2"])
        assert math.isclose(eff1["taunt"], 125.0) and math.isclose(eff1["taunt_eff"], 125.0)
        assert math.isclose(eff2["taunt"], 75.0)

    def test_explicit_taunt_wins(self):
        """显式 stats.taunt > 0 优先于命途表."""
        eng = _engine([_ally("h", "毁灭员", path="destruction", taunt=500.0)])
        eff = eng.pipeline.effective_stats(eng.state.actors["h"])
        assert math.isclose(eff["taunt"], 500.0)

    def test_fallback_100(self):
        """无显式、无命途 → 兜底 100."""
        eng = _engine([_ally("h", "实验员")])
        eff = eng.pipeline.effective_stats(eng.state.actors["h"])
        assert math.isclose(eff["taunt"], 100.0)

    def test_memosprite_table(self):
        """忆灵按名查 memosprite_base（衣匠 125），summoner_id 标记忆灵."""
        memo = Actor(actor_id="m", name="衣匠", level=80, summoner_id="h",
                     stats=StatBlock(hp=1000, def_=500, spd=90, max_energy=0))
        eng = _engine([_ally("h", "阿格莱雅"), memo])
        eff = eng.pipeline.effective_stats(eng.state.actors["m"])
        assert math.isclose(eff["taunt"], 125.0)


class TestAggroBoostPool:
    def test_boost_multiplies(self):
        """aggro_boost 池：taunt_eff = base × (1+Σ)——+500% → ×6."""
        eng = _engine([_ally("h", "实验员")])
        st = eng.state.actors["h"]
        eng._apply_modifier(st, Modifier(
            modifier_id="AGG", name="求生反应", modifier_type="buff", duration=0,
            stat_effects={"aggro_boost": 5.0}))
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["taunt"], 100.0), "base 不变"
        assert math.isclose(eff["taunt_eff"], 600.0)

    def test_pool_additive_two_sources(self):
        """双源池内加算：+500% 与 +200% → ×8（非 ×15）."""
        eng = _engine([_ally("h", "实验员")])
        st = eng.state.actors["h"]
        for i, v in enumerate((5.0, 2.0)):
            eng._apply_modifier(st, Modifier(
                modifier_id=f"AGG{i}", name="嘲讽加成", modifier_type="buff", duration=0,
                stat_effects={"aggro_boost": v}))
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["taunt_eff"], 800.0)


class TestTargetPick:
    def test_expected_picks_highest(self):
        """期望模式：确定性取 taunt_eff 最高者（存护 150 > 巡猎 75）."""
        eng = _engine([_ally("h1", "巡猎员", path="hunt"), _ally("h2", "存护员", path="preservation")])
        assert _pick(eng).actor.actor_id == "h2"

    def test_tie_breaks_by_position(self):
        """并列按编队序：同嘲讽时取存活列表首位."""
        eng = _engine([_ally("h1", "实验员甲"), _ally("h2", "实验员乙")])
        assert _pick(eng).actor.actor_id == "h1"

    def test_boost_changes_pick(self):
        """aggro_boost 改变选目标：巡猎 75 + ×6 = 450 > 存护 150."""
        eng = _engine([_ally("h1", "巡猎员", path="hunt"), _ally("h2", "存护员", path="preservation")])
        eng._apply_modifier(eng.state.actors["h1"], Modifier(
            modifier_id="AGG", name="求生反应", modifier_type="buff", duration=0,
            stat_effects={"aggro_boost": 5.0}))
        assert _pick(eng).actor.actor_id == "h1"

    def test_forced_taunt_overrides(self):
        """覆盖层：forced_taunt 件挂敌方 → 必打 source（即使其嘲讽最低）."""
        eng = _engine([_ally("h1", "巡猎员", path="hunt"), _ally("h2", "存护员", path="preservation")])
        eng._apply_modifier(eng.state.actors["e"], Modifier(
            modifier_id="TAUNT", name="强制嘲讽", modifier_type="debuff", duration=0,
            source_id="h1", forced_taunt=True))
        assert _pick(eng).actor.actor_id == "h1", "强制嘲讽覆盖加权（Fandom：ignoring Aggro and Lock On）"

    def test_forced_taunt_source_dead_falls_through(self):
        """强制嘲讽来源已死/离场 → 回落加权."""
        eng = _engine([_ally("h1", "巡猎员", path="hunt"), _ally("h2", "存护员", path="preservation")])
        eng.state.actors["h1"].alive = False
        eng._apply_modifier(eng.state.actors["e"], Modifier(
            modifier_id="TAUNT", name="强制嘲讽", modifier_type="debuff", duration=0,
            source_id="h1", forced_taunt=True))
        assert _pick(eng).actor.actor_id == "h2"


class TestRollMode:
    def test_weighted_pick_deterministic_and_proportional(self):
        """roll 模式：同种子序列确定（B16）+ 频率按 taunt_eff 加权（100 vs 300 → ~1:3）."""
        def _seq():
            eng = _engine([_ally("h1", "甲", taunt=100.0), _ally("h2", "乙", taunt=300.0)],
                          mode=MODE_ROLL, seed=42)
            return [_pick(eng).actor.actor_id for _ in range(400)]
        s1, s2 = _seq(), _seq()
        assert s1 == s2, "同种子两局选目标序列全等（B16）"
        freq = s1.count("h2") / len(s1)
        assert 0.65 < freq < 0.85, f"加权频率应逼近 0.75，实测 {freq:.3f}"


class TestB16:
    def test_same_seed_identical_snapshot(self):
        """B16：带嘲讽加权的完整对局，同种子两局 snapshot 逐字段全等."""
        def _snap():
            eng = _engine([_ally("h1", "巡猎员", path="hunt"), _ally("h2", "存护员", path="preservation")],
                          mode=MODE_ROLL, seed=7)
            return eng.run().snapshot()
        assert _snap() == _snap()
