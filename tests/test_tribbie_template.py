"""缇宝手工模板端到端（光环第二例+境界 dogfood）：神启辐射/境界易伤+附加伤害/天赋计数重置/秘技."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

_TEMPLATE_SRC = Path(__file__).parent / "fixtures" / "templates" / "1403_tribbie.yaml"
_TEMPLATE_DST = Path("data/sim_templates/characters/1403_tribbie.yaml")


def _ally(actor_id: str, name: str, with_ult: bool = True):
    actions = [{"action_id": f"{actor_id}_basic", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "fire",
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 20},
               {"action_id": f"{actor_id}_aoe", "name": "横扫", "action_type": "skill",
                "target_type": "aoe", "damage_type": "fire",
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 30}]
    if with_ult:
        actions.append({"action_id": f"{actor_id}_ult", "name": "终结", "action_type": "ultimate",
                        "target_type": "aoe", "damage_type": "fire", "energy_cost": 100,
                        "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "energy_gain": 5})
    return {"actor_id": actor_id, "name": name, "inline": True,
            "base_stats": {"atk": 1000, "spd": 80, "hp": 3000, "max_energy": 100},
            "actions": actions}


@pytest.fixture(scope="module")
def engine_factory():
    _TEMPLATE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_TEMPLATE_SRC, _TEMPLATE_DST)

    def build(with_technique: bool = False):
        b = {"build": {"team": [
            {"character_template": "1403", "level": 80},
            _ally("ally_a", "队友A"),
        ], "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}
        if with_technique:
            b["build"]["pre_battle"] = [{"actor_id": "1403", "technique": "140307"}]
        return b

    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e_high", "name": "高血怪", "hp": 1e10, "spd": 50,
         "max_toughness": 9999, "weakness": ["fire"]},
        {"actor_id": "e_low", "name": "低血怪", "hp": 1000.0, "spd": 50,
         "max_toughness": 9999, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 800}}}

    def make(with_technique: bool = False):
        eng = CombatEngine.from_compiled(
            compile_encounter(build(with_technique), stage),
            mode=MODE_EXPECTED, initial_energy_ratio=1.0)
        eng.setup()
        return eng
    return make


def _act(eng, actor_id: str, action_suffix: str):
    st = eng.state.actors[actor_id]
    act = next(a for a in eng.actions_by_actor[actor_id] if a.action_id.endswith(action_suffix))
    eng._execute_action(st, act)


class TestNuminosityAura:
    def test_aura_radiates_team_and_ticks_at_owner_start(self, engine_factory):
        """光环第二例：神启挂缇宝、辐射全队 res_pen+24%、缇宝回合开始计时."""
        eng = engine_factory()
        _act(eng, "1403", "140302")
        tr = eng.state.actors["1403"]
        ally = eng.state.actors["ally_a"]
        assert math.isclose(eng.pipeline.effective_stats(tr)["res_pen"], 0.24), "缇宝自己吃光环"
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.24), "队友吃辐射"
        assert "NUMINOSITY" in tr.modifiers and tr.modifiers["NUMINOSITY"].duration == 3
        # 计时跟缇宝走：她的回合开始才减（owner_turn_start），队友回合不影响
        eng._tick_modifiers(ally, anchor="owner_turn_start")
        assert tr.modifiers["NUMINOSITY"].duration == 3, "队友回合计时不动神启"
        for _ in range(3):
            eng._tick_modifiers(tr, anchor="owner_turn_start")
        assert "NUMINOSITY" not in tr.modifiers, "缇宝 3 次回合开始后神启到期"
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.0), "到期辐射消失"


class TestZone:
    def test_zone_vuln_and_additional_damage(self, engine_factory):
        """境界：敌方易伤 +30%；我方攻击后按命中数对最高 HP 者附加量子伤害."""
        eng = engine_factory()
        _act(eng, "1403", "140303")
        tr = eng.state.actors["1403"]
        e_high, e_low = eng.state.actors["e_high"], eng.state.actors["e_low"]
        assert "TR_ZONE" in tr.modifiers, "境界标记在缇宝身上"
        for e in (e_high, e_low):
            assert "TR_ZONE_VULN" in e.modifiers
            assert math.isclose(eng.pipeline.effective_stats(e)["vulnerability"], 0.30)
        # AoE 命中 2 目标 → 对 HP 最高的 e_high 附加 12%×2 HP；e_low 不吃附加
        hp_high_before, hp_low_before = e_high.current_hp, e_low.current_hp
        hp_tr = tr.actor.stats.hp
        _act(eng, "ally_a", "ally_a_aoe")
        dealt_high = hp_high_before - e_high.current_hp
        aoe_base = dealt_high  # 含横扫本体+附加；用另一组对照拆附加
        # 对照：无境界时同一发 AoE 的伤害
        eng2 = engine_factory()
        e2h, e2l = eng2.state.actors["e_high"], eng2.state.actors["e_low"]
        hp2h_before, hp2l_before = e2h.current_hp, e2l.current_hp
        _act(eng2, "ally_a", "ally_a_aoe")
        base_high = hp2h_before - e2h.current_hp
        base_low = hp2l_before - e2l.current_hp
        # 附加部分 = 有境界 − 无境界（同一发 AoE，同乘区——易伤 +30% 影响双方，用比例剥离）
        # 直接验证：附加打在 e_high（高 HP）而非 e_low
        low_delta = hp_low_before - e_low.current_hp
        assert math.isclose(low_delta, base_low * 1.0, rel_tol=0.5), \
            "e_low 只受 AoE 本体（+易伤），不吃附加"
        # 附加量 = 12%×命中数(2)×缇宝HP，经 e_high 防御/抗性/易伤等乘区——量级校验
        expected_raw = 0.12 * 2 * hp_tr
        extra = dealt_high - base_high
        assert extra > expected_raw * 0.5, f"附加伤害显著存在（附加段对最高 HP 者）: {extra:.0f}"

    def test_zone_expiry_removes_vuln(self, engine_factory):
        """境界到期（缇宝回合开始×2）→ 敌方易伤摘除."""
        eng = engine_factory()
        _act(eng, "1403", "140303")
        tr = eng.state.actors["1403"]
        e_high = eng.state.actors["e_high"]
        eng._tick_modifiers(tr, anchor="owner_turn_start")
        assert "TR_ZONE" in tr.modifiers, "1 次计时后仍在（duration 2→1）"
        eng._tick_modifiers(tr, anchor="owner_turn_start")
        assert "TR_ZONE" not in tr.modifiers, "2 次计时后境界到期"
        assert "TR_ZONE_VULN" not in e_high.modifiers, "易伤随境界摘除"


class TestTalentFua:
    def test_fua_once_per_ally_and_reset_on_own_ult(self, engine_factory):
        """天赋：其他角色开大→全体追加（18%HP）；每角色 1 次；缇宝开大重置."""
        from hsr_nous.sim.policy_api import ULT_AFTER_ACTION
        eng = engine_factory()
        ally = eng.state.actors["ally_a"]
        tr = eng.state.actors["1403"]
        dmg0 = eng.state.damage_by_actor.get("1403", 0.0)
        eng._try_ultimate(ally, ULT_AFTER_ACTION)
        dmg1 = eng.state.damage_by_actor["1403"]
        assert dmg1 > dmg0, "队友开大触发缇宝追加"
        assert "TR_FUA_SPENT" in ally.modifiers, "该角色已计 1 次"
        eng._try_ultimate(ally, ULT_AFTER_ACTION)
        assert math.isclose(eng.state.damage_by_actor["1403"], dmg1), "同角色不再触发"
        eng._try_ultimate(tr, ULT_AFTER_ACTION)
        assert "TR_FUA_SPENT" not in ally.modifiers, "缇宝开大重置计数"
        eng._try_ultimate(ally, ULT_AFTER_ACTION)
        assert eng.state.damage_by_actor["1403"] > dmg1, "重置后可再触发"


class TestTechnique:
    def test_technique_grants_numinosity(self, engine_factory):
        """秘技装填：进战即带神启 3 回合（辐射生效）."""
        eng = engine_factory(with_technique=True)
        tr = eng.state.actors["1403"]
        ally = eng.state.actors["ally_a"]
        assert "NUMINOSITY" in tr.modifiers, "进战自带神启"
        assert tr.modifiers["NUMINOSITY"].duration == 3
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.24)
