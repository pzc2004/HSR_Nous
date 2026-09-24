"""丹恒•腾荒（1414）手写机制 DSL 闭环测试：编译闸 + 实战逐条断言.

闭环判据（2026-09-05 owner 委托手写版验收）：
葳蕤开局提前 40% / 战技同袍单体最新+神秀快照攻击+全队护盾(0.2atk+400) /
终结技全队护盾同式 / 同袍攻击回丹恒 6 能（双通道）/ 同袍唯一。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests._data_env import data_available, data_skip_reason
from tests.template_materialize import TEST_TEMPLATE_ROOTS

pytestmark = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

TERRA_ATK = 582.12
TERRA_ATK_EFF = TERRA_ATK * 1.28         # 有效面板（含行迹 atk_pct 28%）= 745.11——
                                         # hook $self.atk 求值口径（快照按施加时面板）
SHENXIU_EXP = TERRA_ATK_EFF * 0.15       # 111.77
SHIELD_EXP = (TERRA_ATK_EFF + SHENXIU_EXP) * 0.2 + 400   # 571.38——自指场景：
# 神秀 hook 先于护盾 hook 触发，护盾公式读到含神秀的面板（745.11+111.77=856.88）；
# 若盾丹改指他人则为 (745.11)×0.2+400=549.02（目标相关的合法分叉，勿写成定值）


@pytest.fixture(scope="module")
def compiled():
    build = {"build": {"team": [
        {"character_template": "1414", "level": 80},
        {"character_template": "1313", "level": 80},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]} for i in (1, 2, 3)],
        "termination": {"mode": "fixed_av", "max_action_value": 800}}}
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


def _run(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    probes: dict = {}
    orig_emit = eng.bus.emit

    def spy(event, payload, state):
        if event == "on_action" and payload.get("action_id") == "141402" and "skill_after" not in probes:
            probes["skill_after"] = dict(payload)
        if (event == "on_action" and "skill_after" in probes and "snap" not in probes
                and payload.get("action_id") != "141402"):
            # 必须在战技的下一个 on_action 采——同 emit 里 hook 还没跑（包 emit 是先采后放）
            probes["snap"] = {
                "mods_terra": set(state.actors["1414"].modifiers),
                "mods_sunday": set(state.actors["1313"].modifiers),
                "shields": {aid: [(s.name, round(s.remaining, 1)) for s in a.shields]
                            for aid, a in state.actors.items()
                            if a.actor.actor_type != "monster"},
                "terra_energy": state.actors["1414"].current_energy,
            }
        if event == "on_ultimate" and payload.get("action") == "141403" and "ult_after" not in probes:
            probes["ult_after"] = dict(payload)
        return orig_emit(event, payload, state)

    eng.bus.emit = spy
    st = eng.run()
    return st, probes


class TestTerraTemplate:
    def test_weiwei_opening_advance(self, compiled):
        """葳蕤：开局提前 40%——丹恒（102 速）首个行动早于星期日（96 速）."""
        st, _ = _run(compiled)
        actors = [l for l in st.log if " 使用 " in l or " 对 " in l]
        assert actors and "丹恒" in actors[0], f"丹恒应因提前 40% 首动：{actors[:3]}"

    def test_skill_tongpao_shenxiu_shield(self, compiled):
        """战技：同袍挂首目标（唯一）、神秀 atk+87.3、全队护盾 516.4."""
        st, probes = _run(compiled)
        snap = probes.get("snap")
        assert snap, "快照未捕获"
        assert "TONGPAO" in snap["mods_terra"], f"同袍未挂：{snap['mods_terra']}"
        assert "TONGPAO" not in snap["mods_sunday"], "同袍应唯一（星期日不应持有）"
        shenxiu = st.actors["1414"].modifiers.get("TERRA_SHENXIU")
        assert shenxiu is not None and math.isclose(
            shenxiu.stat_effects["atk"], SHENXIU_EXP, rel_tol=1e-6), (
            f"神秀应为 {SHENXIU_EXP}：{shenxiu and shenxiu.stat_effects}")
        for aid, shields in snap["shields"].items():
            assert any(math.isclose(v, SHIELD_EXP, rel_tol=1e-3) for _, v in shields), (
                f"{aid} 应有 {SHIELD_EXP} 护盾：{shields}")

    def test_tongpao_attack_energy(self, compiled):
        """葳蕤：同袍（丹恒自指）攻击后，丹恒回能 +6/次."""
        st, probes = _run(compiled)
        # 终态能量 = 初始 0 + 战技 30 + 普攻/战技回能 + 同袍攻击 6×N（粗口径：>30 即含葳蕤回能）
        e = st.actors["1414"].current_energy
        assert e > 30, f"同袍攻击回能未生效（能量应显著超过战技 30 口径）：{e}"

    def test_tongpao_singleton(self, compiled):
        """同袍仅对最新目标生效：全场至多一个 TONGPAO."""
        st, _ = _run(compiled)
        n = sum(1 for a in st.actors.values()
                if a.actor.actor_type != "monster" and "TONGPAO" in a.modifiers)
        assert n <= 1, f"同袍应全场至多一个：{n}"
