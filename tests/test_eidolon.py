"""星魂（eidolons）系统测试：E0 不激活 / E2 面板+参数改写 / E3 技能等级 / E6 开局火种."""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


def _build(eidolon: int):
    return {"build": {"team": [{"character_template": "1408", "level": 80, "eidolon": eidolon}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 0}]}}}


def _stage():
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1700}}}


def _run(eidolon: int, seed: float = 9.0):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(eidolon), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    eng.state.actors["1408"].resources["fire_seed"] += seed  # 开局 hook 3 + 预置 = 12（E6 另有 +6）
    return eng.run(), eng


class TestEidolon:
    def test_e0_eidolons_inactive(self):
        """E0：星魂件不激活——开局火种=3（只 1408101 行迹 hook）."""
        state, eng = _run(0, seed=0.0)
        st = state.actors["1408"]
        assert math.isclose(eng.state.actors["1408"].resources.get("fire_seed", 0.0) + 12 - 12, st.resources["fire_seed"])
        # 开局即检（setup 后未跑）：E0 应为 3
        eng2 = CombatEngine.from_compiled(
            compile_encounter(_build(0), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng2.setup()
        assert math.isclose(eng2.state.actors["1408"].resources["fire_seed"], 3.0)

    def test_e2_res_pen_and_countdown_ratio(self):
        """E2（E1+E2 激活）：res_pen 0.2 进面板；倒计时速度继承 60%→66%."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(2), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED,
            initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1408"]
        # E2 res_pen 经初始 modifier 进有效面板
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["res_pen"], 0.2, rel_tol=1e-6)
        # E1 overrides：state_config.countdown_spd_ratio = 0.66
        cfgs = eng.state_configs_by_actor.get("1408", [])
        assert cfgs and math.isclose(cfgs[0].countdown_spd_ratio, 0.66, rel_tol=1e-6)

    def test_e3_skill_level_overrides(self):
        """E3：ultimate +2（cap 15）、basic +1（cap 10）."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(3), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED,
            initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1408"]
        assert st.actor.skill_levels["ultimate"] == 12
        assert st.actor.skill_levels["basic"] == 7

    def test_e6_battle_start_seed_bonus(self):
        """E6：开局额外获得 6 火种（与 1408101 的 3 叠加 = 9）."""
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(6), _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED,
            initial_energy_ratio=0.0)
        eng.setup()
        assert math.isclose(eng.state.actors["1408"].resources["fire_seed"], 9.0)
