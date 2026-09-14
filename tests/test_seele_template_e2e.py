"""希儿 1102 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 增幅单池/
天赋再现压制/自动追放配额/大行迹门控/星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：双 id 轴单轨化（本体行动块摘除）/
天赋再现 grant_extra_turn 收编 + 压制闩。

口径常数：希儿白值 atk 640.332、spd 115、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。
增幅增伤 lv10 param(1110204,1)=0.8；Lacerate 增幅内抗穿 0.25（弱点目标区 1.25）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SE_ATK = 640.332
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1102", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage(n=2):
    enemies = [{"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100, "atk": 1000,
                "max_toughness": 9999, "weakness": ["quantum"]} for i in range(1, n + 1)]
    return {"stage": {"stage_id": "s", "enemies": enemies,
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _se(eng):
    return eng.state.actors["1102"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    m7 = _se(eng)
    m7.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["1102"] if a.action_id == "1110203")
    assert eng._fire_ultimate(m7, ult) is True


class TestSeeleCompile:
    def test_single_track_actions(self, compiled):
        """现役单轨（过堂①）：本体 1102xx 行动块摘除——仅存 11102xx 三件."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1102"]}
        assert set(acts) == {"1110201", "1110202", "1110203"}
        decls = compiled.resource_decls_by_actor["1102"]
        assert {"_auto_skill_used", "_bf_proc", "_seele_extra"} <= set(decls)


class TestSkillAndUlt:
    def test_skill_spd_buff(self, compiled):
        """战技：3.6 对轴 + SPD+25% 三回合（115→143.75）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1102", "1110202")
        assert math.isclose(hp1 - e1.current_hp, 3.6 * SE_ATK * Z, rel_tol=1e-9)
        buff = _se(eng).modifiers.get("SEELE_SPD_BUFF")
        assert buff is not None and buff.duration == 3
        assert math.isclose(eng.pipeline.effective_stats(_se(eng))["spd"], 115 * 1.25, rel_tol=1e-9)

    def test_ult_amplification_and_lacerate(self, compiled):
        """大招：7.2 对轴 + 进增幅（增伤 0.8 三回合）→ Lacerate 门控开（抗穿 0.25）——
        下一发普攻吃 增伤区 1.8 × 抗性区 1.25."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, 7.2 * SE_ATK * Z, rel_tol=1e-9)
        s = _se(eng)
        assert "AMPLIFICATION" in s.modifiers
        assert math.isclose(eng.pipeline.effective_stats(s)["res_pen"], 0.25, rel_tol=1e-9), (
            "Lacerate enable_if 门控开（增幅在场）")
        assert math.isclose(s.current_energy, 5.0)
        hp1 = e1.current_hp
        _cast(eng, "1102", "1110201")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * SE_ATK * Z * 1.8 * 1.25, rel_tol=1e-9)


class TestTalentReignite:
    def test_kill_grant_and_suppression_latch(self):
        """再现：三技枚举击杀 → 增幅 + 额外回合 + 压制闩；闩内再杀不触发（挂载计数实证）；
        自身回合结束清零后可再触发."""
        compiled = compile_encounter(_build(), _stage(n=3), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        amps = []
        eng.bus.subscribe("after_apply_modifier", lambda et, p, ctx: (
            amps.append(p) if p.get("modifier_id") == "AMPLIFICATION" else None))
        s = _se(eng)
        e2, e3 = eng.state.actors["e2"], eng.state.actors["e3"]
        e2.current_hp = 10.0
        _cast(eng, "1102", "1110201", target=e2)
        assert not e2.alive and len(amps) == 1, "首杀进增幅 + 额外回合"
        assert math.isclose(s.resources["_seele_extra"], 1.0), "压制闩置位"
        e3.current_hp = 10.0
        _cast(eng, "1102", "1110201", target=e3)
        assert len(amps) == 1, "闩内再杀不重复触发（官方额外回合内豁免）"
        eng.bus.emit("on_turn_end", {"actor": "1102"}, eng.state)
        assert math.isclose(s.resources["_seele_extra"], 0.0)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 10.0
        _cast(eng, "1102", "1110201", target=e1)
        assert len(amps) == 2, "清零后可再触发"
        # Nightshade 三杀叠 3 层：增伤 0.8(增幅)+0.5×3(夜幕) → all 桶 2.3
        assert math.isclose(eng.pipeline.effective_stats(s)["dmg_bonus"].get("all", 0.0),
                            2.3, rel_tol=1e-9), "Nightshade 击杀叠层 50%×3 + 增幅 0.8"


class TestAutoSkill:
    def test_auto_skill_quota_and_reset(self, compiled):
        """自动追放：友方攻击后目标 HP≤50% → 追放 3.6（不耗点不回能）+ 配额闩；
        闩内不发；希儿回合开始复位可再发."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 4e8   # ≤50%×1e9 且吃三轮攻击不死（追放测试专用存活血档）
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * Z + 3.6 * SE_ATK * Z, rel_tol=1e-9), (
            "辅手普攻 + 自动追放 3.6")
        assert math.isclose(_se(eng).resources["_auto_skill_used"], 1.0)
        assert math.isclose(_se(eng).current_energy, 0.0), "自动追放不回能（官方明示）"
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * Z, rel_tol=1e-9), "配额闩内不追放"
        eng.bus.emit("on_turn_start", {"actor": "1102"}, eng.state)
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * Z + 3.6 * SE_ATK * Z, rel_tol=1e-9), (
            "复位后可再追放")


class TestEidolons:
    def test_e2_spd_two_stacks(self):
        """E2：加速可叠 2 层（115×1.5=172.5）；E0 主干 max_stack=1 对照在案."""
        compiled = compile_encounter(_build(eidolon=2), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1102", "1110202")
        _cast(eng, "1102", "1110202")
        assert math.isclose(eng.pipeline.effective_stats(_se(eng))["spd"], 115 * 1.5, rel_tol=1e-9)

    def test_e4_kill_energy(self):
        """E4：击杀回能 15."""
        compiled = compile_encounter(_build(eidolon=4), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e2 = eng.state.actors["e2"]
        e2.current_hp = 10.0
        _cast(eng, "1102", "1110201", target=e2)
        assert math.isclose(_se(eng).current_energy, 20.0 + 15.0), "普攻 20 + E4 15"

    def test_e6_butterfly_flurry(self):
        """E6（新版）：大招挂乱蝶 3 回合 + 记录本次终结技实额（E5 lv12=7.92×ATK×Z——
        大招自身不吃增幅/抗穿）→ 目标再被击附加**真伤** 0.3×实额（跳乘区）."""
        compiled = compile_encounter(_build(eidolon=6), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng)
        ult_dmg = 7.92 * SE_ATK * Z
        assert math.isclose(hp1 - e1.current_hp, ult_dmg, rel_tol=1e-9)
        assert "BUTTERFLY_FLURRY" in e1.modifiers
        assert e1.modifiers["BUTTERFLY_FLURRY"].duration == 3, "新版乱蝶 3 回合（旧版 1）"
        s = _se(eng)
        assert math.isclose(s.resources["_e6_ult_dmg"], ult_dmg, rel_tol=1e-9), "实额锚点"
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            1500 * Z + 0.3 * ult_dmg, rel_tol=1e-9), (
            "辅手普攻 + 蝶影真伤（0.3×实额，不吃乘区——旧版量子段吃区作废）")

    def test_e6_flurry_kill_triggers_reignite(self):
        """E6 新版豁免翻案：任意单位消灭乱蝶目标 → 触发再现（非枚举来源补发——
        辅手击杀乱蝶目标，希儿获得再现（压制闩置 1）且不与我方天赋钩双发）."""
        compiled = compile_encounter(_build(eidolon=6), _stage(), template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        assert math.isclose(_se(eng).resources["_seele_extra"], 0.0)
        e1.current_hp = 100.0   # 压血线让辅手完成击杀
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(_se(eng).resources["_seele_extra"], 1.0), (
            "乱蝶目标被辅手消灭 → 再现触发（旧版豁免作废）")
