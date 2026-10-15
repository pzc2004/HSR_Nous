"""光环辐射 effect_scope 测试：阮梅弦外音——挂源辐射全队、计时跟源走、到期全队回落."""
from __future__ import annotations

import math

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _actor(aid, spd, atk=1000):
    return Actor(actor_id=aid, name=aid, level=80,
                 stats=StatBlock(atk=atk, spd=spd, hp=3000, max_energy=100,
                                 crit_rate=0.0, crit_dmg=0.0))


def _dummy():
    return Actor(actor_id="e", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["fire"]))


def _engine():
    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=0)
    ruan_mei = _actor("rm", 90)
    ally = _actor("a", 80)
    enc = Encounter(encounter_id="t", name="t", actors=[ruan_mei, ally, _dummy()],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=250))
    eng = CombatEngine(enc, actions_by_actor={"rm": [basic], "a": [basic]},
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    # 弦外音：挂阮梅、scope=team（辐射全队）、tick_anchor=阮梅回合开始、duration=2
    eng._apply_modifier(eng.state.actors["rm"], Modifier(
        modifier_id="XWY", name="弦外音", modifier_type="buff", duration=2,
        tick_anchor="owner_turn_start", effect_scope="team",
        stat_effects={"all_dmg": 0.30}))  # 我方全体伤害+30%
    return eng


class TestAuraScope:
    def test_aura_radiates_to_team_not_self_only(self):
        """scope=team：挂阮梅身上的 buff，队友（和阮梅自己）都吃到加成."""
        eng = _engine()
        rm_eff = eng.pipeline.effective_stats(eng.state.actors["rm"])
        a_eff = eng.pipeline.effective_stats(eng.state.actors["a"])
        assert math.isclose(a_eff["dmg_bonus"]["all"], 0.30, rel_tol=1e-9), (
            f"队友应吃到光环 30%：{a_eff['dmg_bonus']}"
        )
        assert math.isclose(rm_eff["dmg_bonus"]["all"], 0.30, rel_tol=1e-9), (
            f"阮梅自己也应吃到（我方全体含源）：{rm_eff['dmg_bonus']}"
        )

    def test_aura_expires_by_source_turn_start_and_falls_off(self):
        """计时跟源走（阮梅回合开始）：duration=1 → 阮梅首次回合开始即到期，全队回落."""
        eng = _engine()
        state = eng.run()
        log = state.log
        # 阮梅首次行动在 @111.1（spd 90）；其回合开始时弦外音到期 → 之后的伤害回落
        a_hits = [l for l in log if "a 对" in l and "普攻" in l]
        assert len(a_hits) >= 2, f"队友应有多次行动：{a_hits}"
        # 第 1 次（弦外音在）：atk 1000×1.0×1.3×0.5×0.9 = 585；到期后：×1.0 = 450
        first_dmg = float(a_hits[0].split("造成 ")[1].split(" 伤害")[0].replace(",", ""))
        later_dmg = float(a_hits[-1].split("造成 ")[1].split(" 伤害")[0].replace(",", ""))
        assert math.isclose(first_dmg, 585.0, rel_tol=1e-3), f"光环期伤害应 585：{first_dmg}"
        assert math.isclose(later_dmg, 450.0, rel_tol=1e-3), f"到期回落应 450：{later_dmg}"

    def test_aura_excluded_from_holder_double_count(self):
        """防重复计：阮梅自己结算时，自己持有的光环不得算两遍."""
        eng = _engine()
        rm_eff = eng.pipeline.effective_stats(eng.state.actors["rm"])
        # 若重复计：0.30 会变 0.60
        assert math.isclose(rm_eff["dmg_bonus"]["all"], 0.30, rel_tol=1e-9), (
            f"持有者的光环不得双计：{rm_eff['dmg_bonus']}"
        )
