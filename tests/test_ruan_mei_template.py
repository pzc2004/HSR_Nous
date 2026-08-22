"""阮梅手工模板端到端（光环 dogfood）：弦外音/结界/天赋速度/天赋击破追加/源回合计时."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

_TEMPLATE_SRC = Path(__file__).parent / "fixtures" / "templates" / "1303_ruan_mei.yaml"
_TEMPLATE_DST = Path("data/sim_templates/characters/1303_ruan_mei.yaml")


@pytest.fixture(scope="module")
def engine_factory():
    _TEMPLATE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_TEMPLATE_SRC, _TEMPLATE_DST)
    build = {"build": {"team": [
        {"character_template": "1303", "level": 80},
        {"actor_id": "ally", "name": "冰攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100,
                        "crit_rate": 0.0, "crit_dmg": 0.0},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
         "max_toughness": 30, "weakness": ["ice"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 600}}}

    def make():
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage), mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        return eng
    return make


class TestRuanMeiTemplate:
    def test_xwy_aura_buffs_team_and_self(self, engine_factory):
        """战技后：弦外音辐射——队友和阮梅都吃增伤 32% + 击破效率 50%."""
        eng = engine_factory()
        ally_state = eng.state.actors["ally"]
        rm_state = eng.state.actors["1303"]
        # 阮梅首动（spd 109 最快）放战技挂弦外音；检查有效面板
        eng._execute_action(rm_state, next(a for a in eng.actions_by_actor["1303"] if a.action_id == "130302"))
        a_eff = eng.pipeline.effective_stats(ally_state)
        r_eff = eng.pipeline.effective_stats(rm_state)
        assert math.isclose(a_eff["dmg_bonus"].get("all", 0.0), 0.32, rel_tol=1e-9)
        assert math.isclose(a_eff["break_efficiency"], 0.5, rel_tol=1e-9)
        assert math.isclose(r_eff["dmg_bonus"]["all"], 0.32, rel_tol=1e-9)

    def test_break_efficiency_actually_multiplies_toughness_damage(self, engine_factory):
        """击破效率 50% 生效：30 韧性假人，2 动（10×1.5×2）击破——无效率要 3 动."""
        eng = engine_factory()
        rm_state = eng.state.actors["1303"]
        eng._execute_action(rm_state, next(a for a in eng.actions_by_actor["1303"] if a.action_id == "130302"))
        ally_basic = eng.actions_by_actor["ally"][0]
        e1 = eng.state.actors["e1"]
        ally_actor = ally_basic and eng.state.actors["ally"].actor
        eng._apply_toughness_damage(ally_actor, ally_basic, e1)
        assert math.isclose(e1.toughness, 30 - 15.0), f"一击削 15（10×1.5）：{e1.toughness}"
        eng._apply_toughness_damage(ally_actor, ally_basic, e1)
        assert e1.broken, "两击（30）应击破"

    def test_ult_zone_res_pen_and_talent_spd_ex_self(self, engine_factory):
        """终结技：全队 res_pen+25%；天赋：队友速度+10%，阮梅自己不加（除自身外）."""
        eng = engine_factory()
        a_eff = eng.pipeline.effective_stats(eng.state.actors["ally"])
        r_eff = eng.pipeline.effective_stats(eng.state.actors["1303"])
        # 天赋速度（on_battle_start 已挂）
        assert math.isclose(a_eff["spd"], 80 * 1.1, rel_tol=1e-9), f"队友应 +10% 速：{a_eff['spd']}"
        assert math.isclose(r_eff["spd"], 109.0, rel_tol=1e-9), f"阮梅自己不应加（除自身外）：{r_eff['spd']}"
        # 终结技结界
        rm_state = eng.state.actors["1303"]
        rm_state.current_energy = 130.0
        eng._execute_action(rm_state, next(a for a in eng.actions_by_actor["1303"] if a.action_id == "130303"))
        a_eff2 = eng.pipeline.effective_stats(eng.state.actors["ally"])
        assert math.isclose(a_eff2["res_pen"], 0.25, rel_tol=1e-9), f"结界抗性穿透：{a_eff2['res_pen']}"

    def test_talent_break_followup_and_xwy_expiry(self, engine_factory):
        """天赋：我方击破时阮梅追加冰击破伤害；弦外音第 3 次阮梅回合开始时到期."""
        eng = engine_factory()
        rm_state = eng.state.actors["1303"]
        eng._execute_action(rm_state, next(a for a in eng.actions_by_actor["1303"] if a.action_id == "130302"))
        state = eng.run()
        log = state.log
        # 天赋击破追加（假人第 2 动被击破后）
        assert any("击破伤害（分型的螺旋）" in l for l in log), f"应有天赋追加击破伤害：{[l for l in log if '击破' in l][:6]}"
        # 弦外音 duration=3、阮梅第 3 次回合开始时到期 → 终局面板无 all_dmg 加成
        a_eff = eng.pipeline.effective_stats(eng.state.actors["ally"])
        assert math.isclose(a_eff["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-9), (
            f"弦外音第 3 次阮梅回合开始应到期：{a_eff['dmg_bonus']}"
        )
