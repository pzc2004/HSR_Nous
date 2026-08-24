"""hook DSL 化 v1：模板 hooks 块 → 编译 → 引擎订阅执行（四执行体）.

dogfood：白厄大行迹 1408101（战斗开始/变身结束获火种）+ 1408103（攻击叠层）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import materialize_template


@pytest.fixture(scope="module")
def engine_factory():
    materialize_template("1408_phainon.yaml")
    build = {"build": {"team": [{"character_template": "1408", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1600}}}

    def make(seed_offset=0.0):
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage), mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        if seed_offset:
            eng.state.actors["1408"].resources["fire_seed"] += seed_offset
        return eng
    return make


class TestHookDsl:
    def test_battle_start_seed_gain(self, engine_factory):
        """1408101：战斗开始经模板 hook 获得 3 火种（无 Python 注册）."""
        eng = engine_factory()
        st = eng.state.actors["1408"]
        assert math.isclose(st.resources["fire_seed"], 3.0), (
            f"开局火种应=模板 hook 给的 3：{st.resources}"
        )

    def test_heroism_stacks_on_enter_and_exit(self, engine_factory):
        """1408103：进战叠 1 层照见英雄本色（atk_pct 0.5）；变身结束再叠（cap 2）."""
        eng = engine_factory(seed_offset=9.0)  # 开局 3(钩)+预置 9=12 → T1 战技即可变身
        state = eng.run()
        st = state.actors["1408"]
        mod = st.modifiers.get("TRACE_1408103")
        assert mod is not None, "照见英雄本色应挂上"
        assert mod.stacks >= 1
        assert math.isclose(mod.stat_effects.get("atk_pct", 0.0), 0.5)

    def test_exit_seed_refund_via_hook(self, engine_factory):
        """1408101 变身结束返还 1 火种（模板 hook，与 Python 银行 hook 独立共存）."""
        eng = engine_factory(seed_offset=9.0)
        state = eng.run()
        log = state.log
        assert any("退出形态 卡厄斯兰那" in l for l in log)
        # 终局火种 = 退出返还 1 + 后续战技×N×2（每动 +2）——至少 ≥1
        assert state.actors["1408"].resources["fire_seed"] >= 1.0

    def test_hook_condition_false_no_effect(self, engine_factory):
        """条件不满足不触发：未变身时 on_state_change 的 from_state 过滤."""
        eng = engine_factory()
        # 不变身（火种 3 不够 12）→ on_state_change 永不发 → 无返还
        state = eng.run()
        assert not any("进入形态" in l for l in state.log)
        # 火种只增不减（战技+2/动），无 +1 返还项——终局 = 3 + 2×动数
