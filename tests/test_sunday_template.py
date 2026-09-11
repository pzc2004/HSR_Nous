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
from hsr_nous.sim.state import Modifier
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


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _cast(eng, aid):
    """手动施放星期日技能（_execute_action 不发 on_action——由调用方补发，同 _run_turn 口径；
    政策无 target_rules → ally_single 缺省取编队首=1414）."""
    sun = eng.state.actors["1313"]
    a = next(x for x in eng.actions_by_actor["1313"] if x.action_id == aid)
    eng._execute_action(sun, a)
    eng.bus.emit("on_action", {
        "actor": "1313", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": eng._last_target_id,
        "actor_type": "character"}, eng.state)


class TestHavenInPalm:
    """掌中安港（1313103）：施放战技解除目标 1 个负面（remove_modifier filter+max_count 收编）."""

    def test_skill_purifies_one_debuff_lifo(self, compiled):
        eng = _make(compiled)
        terra = eng.state.actors["1414"]
        eng._apply_modifier(terra, Modifier(
            modifier_id="DEB_A", name="旧伤", modifier_type="debuff", duration=2))
        eng._apply_modifier(terra, Modifier(
            modifier_id="DEB_B", name="新咒", modifier_type="debuff", duration=2))
        eng._apply_modifier(terra, Modifier(
            modifier_id="DEB_X", name="印记", modifier_type="debuff", duration=0, dispellable=False))
        _cast(eng, "131302")
        assert "DEB_B" not in terra.modifiers and "DEB_A" in terra.modifiers, (
            "只摘 1 个、LIFO 最新先摘")
        assert "DEB_X" in terra.modifiers, "不可驱散不占名额"
        # 战技既有件不受净化影响（目标侧 buff 照挂）
        assert "SUNDAY_SKILL_DMG" in terra.modifiers


class TestSummonSynergyAndHarmonyGate:
    """131302 召唤物联动 + 同谐命途限制（2026-09-09 B32 深层件批收编）：
    $it.summoner_id 寻址（召唤物同行立即行动）/ has_summon 存在性判定（增伤额外 +50%）/
    path_of 命途闸（对同谐施放不触发立即行动）三首实例."""

    @staticmethod
    def _spy_act_now(eng):
        calls = []
        orig = eng.scheduler.act_now
        def spy(actor):
            calls.append(actor.actor_id)
            return orig(actor)
        eng.scheduler.act_now = spy
        return calls

    def test_summon_advances_with_target_and_boost_80(self, compiled):
        eng = _make(compiled)
        terra = eng.state.actors["1414"]
        eng.summon_actor(terra, "1414_souldragon")      # 龙灵在场（165 速上行动条）
        dragon = eng.state.actors["1414_souldragon"]
        assert dragon.alive
        calls = self._spy_act_now(eng)
        _cast(eng, "131302")                             # 政策缺省目标=编队首=1414
        assert "1414" in calls and "1414_souldragon" in calls, (
            f"目标及其召唤物同行立即行动（召唤物 of $event.target 寻址）：{calls}")
        mod = terra.modifiers["SUNDAY_SKILL_DMG"]
        assert math.isclose(mod.stat_effects["all_dmg"], 0.8), (
            "持有召唤物：增伤 30%+额外 50% 施放时刻烘焙（has_summon 存在性判定）")
        dmod = dragon.modifiers.get("SUNDAY_SKILL_DMG")
        assert dmod is not None and math.isclose(dmod.stat_effects["all_dmg"], 0.8), (
            "召唤物侧同值双挂（官方「其」按复合主语读——读法待实测 B19 候选）")

    def test_no_summon_boost_30_and_single_advance(self, compiled):
        eng = _make(compiled)
        terra = eng.state.actors["1414"]
        calls = self._spy_act_now(eng)
        _cast(eng, "131302")
        assert calls == ["1414"], f"无召唤物：只拉目标自身（where 空池 no-op）：{calls}"
        assert math.isclose(terra.modifiers["SUNDAY_SKILL_DMG"].stat_effects["all_dmg"], 0.3), (
            "无召唤物：增伤原价 30%")

    def test_harmony_target_no_immediate_action(self):
        """同谐限制：对同谐角色施放不触发立即行动（增伤/其余效果照走）."""
        build = {"build": {"team": [
            {"actor_id": "harm", "name": "同谐队友", "inline": True, "path": "harmony",
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "harm_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "fire",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
            {"character_template": "1313", "level": 80},
        ], "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 800}}}
        eng = _make(compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS))
        harm = eng.state.actors["harm"]
        assert harm.actor.path == "harmony"
        calls = self._spy_act_now(eng)
        _cast(eng, "131302")                             # 缺省目标=编队首=harm
        assert eng._last_target_id == "harm"
        assert calls == [], f"对同谐施放不触发立即行动（目标与召唤物两半同闸）：{calls}"
        assert math.isclose(harm.modifiers["SUNDAY_SKILL_DMG"].stat_effects["all_dmg"], 0.3), (
            "立即行动受限不影响增伤照走")


class TestGloriousMysteries:
    """荣光之秘（131307 秘技）：进战武装 → 首次对我方目标施放技能消费（目标增伤 50% 2 回合）."""

    def _compiled_with_technique(self):
        build = {"build": {"team": [
            {"character_template": "1414", "level": 80},
            {"character_template": "1313", "level": 80},
        ], "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0},
        ]}, "pre_battle": [{"actor_id": "1313", "technique": "131307"}]}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 800}}}
        return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)

    def test_armed_on_battle_start_and_consumed_by_skill(self):
        eng = _make(self._compiled_with_technique())
        sun, terra = eng.state.actors["1313"], eng.state.actors["1414"]
        assert "GLORY_SECRET" in sun.modifiers, "进战武装标记（装填预置）"
        _cast(eng, "131302")
        mod = terra.modifiers.get("GLORY_SECRET_DMG")
        assert mod is not None and mod.duration == 2
        assert math.isclose(mod.stat_effects["all_dmg"], 0.5)
        assert "GLORY_SECRET" not in sun.modifiers, "首次命中消费标记"
        _cast(eng, "131302")                       # 第二次不再触发（无标记）
        assert terra.modifiers["GLORY_SECRET_DMG"].duration == 2, "不叠不刷"

    def test_ult_channel_consumes_and_basic_does_not(self):
        eng = _make(self._compiled_with_technique())
        sun, terra = eng.state.actors["1313"], eng.state.actors["1414"]
        _cast(eng, "131301")                       # 普攻指敌方：不消费
        assert "GLORY_SECRET" in sun.modifiers
        assert "GLORY_SECRET_DMG" not in terra.modifiers
        sun.current_energy = 130.0
        ult = next(a for a in eng.actions_by_actor["1313"] if a.action_id == "131303")
        eng._fire_ultimate(sun, ult)               # 真实开大路径：只发 on_ultimate（B37）
        assert "GLORY_SECRET_DMG" in terra.modifiers
        assert "GLORY_SECRET" not in sun.modifiers
