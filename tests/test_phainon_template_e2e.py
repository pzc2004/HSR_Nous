"""白厄全机制模板端到端对轴（刀 1 验收）：真模板 YAML → 编译 → 火种变身全链 → 手算全等.

链：预置火种 10 → T1 战技（+2=12）→ 变身（扣 12，毁伤+4，倒计时 8）
→ cd1-7 血棘渡亡（各毁伤+2）→ cd8 强制最后一击（均分）→ 退出。
注意：技能等级系统未接（deal_damage 恒 lv1），对轴按 lv1 倍率。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 582.12 * 1.5            # 含照见英雄本色 1 层（atk_pct 0.5，行迹 hook 进战即挂）
K_ATK = 582.12 * 2.3          # 倒计时：形态 0.8 + 行迹 1 层 0.5（Σpct 白值加算）
CRIT_EXP = 1 + 0.17 * 0.873  # 1.14841（含行迹面板：crit 0.17/0.873）
DEF_RES = 0.5              # 假人 def 0 口径
UNBROKEN = 0.9


@pytest.fixture(scope="module")
def compiled():
    build = {"build": {"team": [{"character_template": "1408", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "not in_state", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]} for i in (1, 2, 3)],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


class TestPhainonTemplateE2E:
    def _run(self, compiled):
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        eng.state.actors["1408"].resources["fire_seed"] += 7.0  # 开局 hook 3 + 预置 7 + T1 战技 2 = 12
        return eng.run()

    def test_full_chain_hand_calc(self, compiled):
        state = self._run(compiled)
        log = state.log

        # 1. 变身与退出发生（日志用形态显示名"卡厄斯兰那"）
        assert any("进入形态 卡厄斯兰那" in l for l in log)
        assert any("退出形态 卡厄斯兰那" in l for l in log)
        # 2. 倒计时 8 动：7 血棘 + 1 最后一击
        assert sum(1 for l in log if "创生•血棘渡亡" in l and "白厄 对 假人1" in l) == 7
        assert sum(1 for l in log if "最后一击" in l) == 3  # aoe 3 怪各一条日志
        # 3. 资源轨迹：火种扣 12 后由 1408101 返还 1（模板 hook）；毁伤 4(变身)+2×7(血棘)=18
        st = state.actors["1408"]
        assert math.isclose(st.resources["fire_seed"], 1.0), f"1408101 变身结束应返还 1：{st.resources}"
        assert math.isclose(st.resources["ruin"], 18.0)
        # 4. 形态已退出
        assert st.state_config is None

        # 5. 伤害全链手算（满级档：战技 lv10 3.0/1.2、血棘 lv6 2.5/0.75（普攻系满级 6）、终结技 lv10 9.6）
        skill_main = ATK * 3.0 * CRIT_EXP * DEF_RES * UNBROKEN
        skill_sub = ATK * 1.2 * CRIT_EXP * DEF_RES * UNBROKEN
        k_atk = K_ATK
        k_main = k_atk * 2.5 * CRIT_EXP * DEF_RES * UNBROKEN
        k_sub = k_atk * 0.75 * CRIT_EXP * DEF_RES * UNBROKEN
        fin = k_atk * 3.2 * CRIT_EXP * DEF_RES * UNBROKEN  # 9.6/3 均分
        expected = (skill_main + skill_sub) + 7 * (k_main + k_sub) + 3 * fin
        assert math.isclose(state.total_damage, expected, rel_tol=1e-6), (
            f"手算 {expected:.2f} vs 实际 {state.total_damage:.2f}"
        )

    def test_state_config_registered_from_template(self, compiled):
        """模板 state_config 块经编译进引擎（非手动注册）."""
        assert "1408" in compiled.state_configs_by_actor
        cfg, entry = compiled.state_configs_by_actor["1408"]
        assert cfg.state == "khaslana" and entry == "140803"
        assert cfg.final_action_id == "final_strike"
        assert math.isclose(cfg.stat_effects["atk_pct"], 0.8)
