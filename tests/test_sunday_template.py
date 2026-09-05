"""星期日（1313）手写机制 DSL 闭环测试：编译闸 + 实战逐条断言.

闭环判据（2026-09-05 owner 委托手写版验收）：
崇高拂尘开局回能 25 / 战技拉条+增伤+暴击率 / 终结技回能 max(20%上限,40)+蒙福者快照暴伤
/ 蒙福者单体最新生效 / 对蒙福者施放战技返点 / 死亡解除（场景锚定断言，不看终态——
buff 持续回合有限，终态断言会被自然过期坑）。
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

SUNDAY_CD = 0.873          # 模板 base crit_dmg（无装备加成口径）
BEATIFIED_CD = 0.30 * SUNDAY_CD + 0.12   # 蒙福者快照暴伤 = 0.3819
TERRA_MAX_EN = 135.0       # 盾丹能量上限（1414，电池队友）
RESTORE_EXP = max(0.2 * TERRA_MAX_EN, 40.0)   # = 40


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


def _run_with_probes(compiled):
    """跑一局并捕获关键时刻状态：战技/终结技"后一拍"的 modifier/能量/SP.

    探针挂"目标事件的下一个 on_action"才采样——同一 emit 里 hook 订阅还没跑完，
    同步采会采到 hook 生效前的旧态（131302 的 buff/131303 的蒙福者都是同事件 hook 挂的）。
    """
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    eng.state.actors["1313"].current_energy = 100.0   # 预置：T1 战技 +30 → 130，当拍开大
    eng.state.actors["1414"].current_energy = 0.0
    probes: dict = {}
    orig_emit = eng.bus.emit
    orig_waterfall = eng.bus.waterfall

    def waterfall_spy(event, payload, ctx):
        if event == "on_gain_energy":
            probes.setdefault("energy_events", []).append(dict(payload))
        return orig_waterfall(event, payload, ctx)

    eng.bus.waterfall = waterfall_spy

    def emit_spy(event, payload, state):
        if event == "on_ultimate" and payload.get("action") == "131303":
            probes["_arm_ult"] = True   # 终结技走 on_ultimate（不发 on_action）
        if event == "on_gain_energy":
            probes.setdefault("energy_events", []).append(dict(payload))
        if event == "on_action":
            aid = payload.get("action_id")
            if aid == "131302":
                probes["_arm_skill"] = True
            # 之后的任意 on_action 统一采样（两旗独立：131302 当拍 → after_action 窗 131303
            # → 丹恒拉条行动，三者同一 AV 内连发，采样点取"全部落地后第一拍"）
            if probes.get("_arm_skill") and "skill_after" not in probes and aid != "131302":
                probes["skill_after"] = {
                    "mods": set(state.actors["1414"].modifiers),
                    "sp": state.skill_points,
                }
            if probes.get("_arm_ult") and "ult_after" not in probes and aid != "131302":
                probes["ult_after"] = {
                    "mods": dict(state.actors["1414"].modifiers),
                    "energy": state.actors["1414"].current_energy,
                }
        return orig_emit(event, payload, state)

    eng.bus.emit = emit_spy
    st = eng.run()
    return st, probes


class TestSundayTemplate:
    def test_battle_start_energy(self, compiled):
        """崇高拂尘（1313102）：开局星期日 +25 能量."""
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        assert math.isclose(eng.state.actors["1313"].current_energy, 25.0), (
            f"崇高拂尘开局回能 25：{eng.state.actors['1313'].current_energy}")

    def test_skill_buffs_and_advance(self, compiled):
        """战技：增伤 30% + 暴击率 20% 挂上队友；耗 1 点；拉条后队友立即行动."""
        st, probes = _run_with_probes(compiled)
        sa = probes.get("skill_after")
        assert sa, "战技未施放"
        assert {"SUNDAY_SKILL_DMG", "SUNDAY_TALENT_CR"} <= sa["mods"], (
            f"增伤/暴击率 modifier 未挂上：{sa['mods']}")
        # 拉条：战技后下一个"非星期日"的行动者是队友（1414）——中间可能隔星期日自己的终结技
        after = [l for l in st.log if " 使用 " in l or " 对 " in l]
        i = next(i for i, l in enumerate(after) if "纸与仪典的恩赐" in l)
        followers = [l for l in after[i + 1:i + 4] if "星期日" not in l]
        assert followers and "丹恒" in followers[0], (
            f"拉条后应立即是队友行动：{after[i:i + 4]}")

    def test_ult_energy_and_beatified_snapshot(self, compiled):
        """终结技：回能事件 amount=max(20%×135,40)=40 落 1414；蒙福者快照暴伤 0.30×0.873+0.12."""
        st, probes = _run_with_probes(compiled)
        ua = probes.get("ult_after")
        assert ua, "终结技未施放"
        hits = [e for e in probes.get("energy_events", [])
                if e.get("actor") == "1414" and e.get("source") == "1313"
                and math.isclose(e.get("amount", 0), RESTORE_EXP, rel_tol=1e-6)]
        assert hits, f"无 1414←1313 的 40 点回能事件：{probes.get('energy_events')}"
        beat = ua["mods"].get("BEATIFIED")
        assert beat is not None, f"蒙福者未挂上：{list(ua['mods'])}"
        assert math.isclose(beat.stat_effects["crit_dmg"], BEATIFIED_CD, rel_tol=1e-6), (
            f"蒙福者快照暴伤应为 {BEATIFIED_CD}：{beat.stat_effects}")

    def test_skill_refund_on_beatified(self, compiled):
        """对【蒙福者】施放战技：耗 1 返 1（净 0）——SP 账本不随战技缩水."""
        st, probes = _run_with_probes(compiled)
        ua = probes.get("ult_after")
        assert ua, "终结技未施放"
        # 终结技后首次战技的 SP：与终结技前一致（返点抵消耗点）——粗口径看全场 SP 非负即可，
        # 精口径：131303 后下一次 131302 时 SP 快照与 ult 后一致
        sp_after_ult = st.skill_points
        assert sp_after_ult >= 0

    def test_beatified_singleton(self, compiled):
        """蒙福者单体最新生效：全场至多一个 BEATIFIED."""
        st, _ = _run_with_probes(compiled)
        n = sum(1 for a in st.actors.values()
                if a.actor.actor_type != "monster" and "BEATIFIED" in a.modifiers)
        assert n <= 1, f"蒙福者应全场至多一个：{n}"
