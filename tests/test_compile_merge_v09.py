"""v0.9 编译归并端到端：角色+光锥+遗器套装+敌人模板引用 → 编译 → 跑局对轴.

对轴方式：同怪同技能，全装局/裸装局伤害比 = (角色白值+光锥白值)×(1+atk_pct) / 角色白值
——光锥白值与 pct 族（白值口径）同时被验证。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

DAN_HENG = "1002"
LC_ID = "23042"      # 愿虹光永驻天空（白值 atk 441.72 @80）
RELIC_SET = "102"    # 快枪手：2pc atk_pct 0.12
ENEMY = "1002011"    # 冰锋


@pytest.fixture(scope="module")
def templates():
    from hsr_nous.adapters.template_generator import (
        write_character_template, write_enemy_template,
        write_light_cone_template, write_relic_set_template,
    )
    write_character_template(DAN_HENG, level=80, lang="cn")
    write_light_cone_template(LC_ID, level=80, lang="cn")
    write_relic_set_template(RELIC_SET, lang="cn")
    write_enemy_template(ENEMY, level=80)
    return True


def _build(with_gear: bool):
    member = {"character_template": DAN_HENG, "level": 80}
    if with_gear:
        member["light_cone_template"] = LC_ID
        member["light_cone"] = {"level": 80, "superimposition": 1}
        # 两件同套装触发 2pc；main 选非攻击词条（hp/heal_bonus），不干扰伤害对轴
        member["relics"] = {
            "head": {"set_id": RELIC_SET, "main": "hp", "subs": {}},
            "body": {"set_id": RELIC_SET, "main": "heal_bonus", "subs": {}},
        }
    return {"build": {"team": [member], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage():
    return {"stage": {"stage_id": "s", "enemies": [{"enemy_template": ENEMY, "level": 80}],
                      "termination": {"mode": "fixed_av", "max_action_value": 100}}}


class TestCompileMerge:
    def test_light_cone_base_stats_merged(self, templates):
        compiled = compile_encounter(_build(True), _stage())
        from hsr_nous.pipeline import calc_character_stats, calc_light_cone_stats
        char_atk = calc_character_stats(DAN_HENG, level=80, lang="cn")["atk"]
        lc_atk = calc_light_cone_stats(LC_ID, level=80, lang="cn")["atk"]
        assert math.isclose(compiled.build_team[0].stats.atk, char_atk + lc_atk, rel_tol=1e-9)

    def test_relic_set_modifier_compiled(self, templates):
        compiled = compile_encounter(_build(True), _stage())
        mods = compiled.modifiers_by_actor.get(DAN_HENG, [])
        assert any(m.modifier_id == "RELIC_102_2PC" for m in mods)
        m2 = next(m for m in mods if m.modifier_id == "RELIC_102_2PC")
        assert math.isclose(m2.stat_effects["atk_pct"], 0.12)

    def test_enemy_template_actions_merged(self, templates):
        compiled = compile_encounter(_build(False), _stage())
        assert compiled.stage.enemies[0].actor_id == ENEMY
        assert f"{ENEMY}_basic" in {a.action_id for a in compiled.actions_by_actor[ENEMY]}

    def test_gear_damage_ratio_hand_calc(self, templates):
        """全装/裸装伤害比 = (白值+光锥)×1.12 / 白值（pct 白值口径端到端验证）."""
        from hsr_nous.pipeline import calc_character_stats, calc_light_cone_stats
        char_atk = calc_character_stats(DAN_HENG, level=80, lang="cn")["atk"]
        lc_atk = calc_light_cone_stats(LC_ID, level=80, lang="cn")["atk"]

        bare = CombatEngine.from_compiled(
            compile_encounter(_build(False), _stage()), mode=MODE_EXPECTED,
            initial_energy_ratio=0.0).run()
        geared = CombatEngine.from_compiled(
            compile_encounter(_build(True), _stage()), mode=MODE_EXPECTED,
            initial_energy_ratio=0.0).run()

        expected_ratio = (char_atk + lc_atk) * 1.12 / char_atk
        assert math.isclose(geared.total_damage / bare.total_damage, expected_ratio, rel_tol=1e-6), (
            f"伤害比 {geared.total_damage / bare.total_damage:.4f} vs 手算 {expected_ratio:.4f}"
        )
