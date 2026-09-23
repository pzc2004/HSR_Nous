"""卡芙卡 1005 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 触电挂载/跳伤/引爆/
FUA 充能链/行迹门控/星魂全链 → 手算全等.

过堂五件（fixture 头注同录）：FUA 回能补记 / 三钩目标过滤 / E1E2 死键摘除 /
相邻引爆触电过滤 / Torture 键名 effect_hit 勘正。

口径常数：卡芙卡白值 atk 679.14、crit 0.05/0.5（期望暴击区 1.025——仅直击段）；
行迹 atk+28%/EHR+18%（B-TR② 已回填——面板 869.2992；EHR 0.18<0.75 Torture 门控
不达）；假人 def 0 → 防御区 0.5、雷弱点 → 抗性区 1.0、未击破 0.9。触电跳伤走
**声明式 dot 通道**（2026-09-22 双通道合并——不暴击 ×0.45+施加时刻快照+EHR 0.18
命中区截 1.0 中性；引爆段为 param 表达式独立结算不受影响——声明式 DoT 可被引爆
实证就绪）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

KF_ATK = 679.14
KF_EFF = KF_EFF = KF_ATK * 1.28                        # 869.2992（B-TR② 行迹 atk 0.28 回填后面板）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
ALLY_Z = Z                              # 辅手同雷伤（雷弱点 → 抗性区 1.0）
SHOCK_LV10 = 2.9                        # param(1100503,4) lv10 触电单跳倍率


def _build(*, eidolon: int = 0, ally_ehr: float = 0.0):
    member = {"character_template": "1005", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    ally_stats = {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100}
    if ally_ehr:
        ally_stats["effect_hit"] = ally_ehr
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": ally_stats,
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _kf(eng):
    return eng.state.actors["1005"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng._pick_ally_target = lambda attacker=None: tgt
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    m7 = _kf(eng)
    m7.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["1005"] if a.action_id == "1100503")
    assert eng._fire_ultimate(m7, ult) is True


def _shock(eng, tid="e1", *, ratio=2.9):
    """直接挂声明式触电件（modifier_type dot——跳伤走引擎 A 类结算；ratio 默认
    lv10=2.9，E6 场传烘焙后合计值）."""
    eng._apply_modifier_spec(eng.state.actors[tid], {
        "modifier_id": "KAFKA_SHOCK", "name": "触电", "modifier_type": "dot",
        "dot_element": "thunder", "dot_ratio": ratio, "duration": 2,
        "dispellable": True}, source=eng.state.actors["1005"])


class TestKafkaCompile:
    def test_resources_actions(self, compiled):
        decls = compiled.resource_decls_by_actor["1005"]
        assert decls["_fua_charges"]["max"] == 2, "FUA 充能上限 2（1100504 #5）"
        assert {"_e4", "_e6_shock"} <= set(decls)
        acts = {a.action_id: a for a in compiled.actions_by_actor["1005"]}
        assert acts["1100504"].action_type == "follow_up" and acts["1100504"].energy_gain == 10
        assert acts["1100503"].energy_cost == 120
        # 触电挂载 2026-09-22 双通道合并迁 on_action 钩（E6 表达式烘焙通道——
        # action apply_modifiers 无烘焙不接表达式），action 层不再携带 apply_modifiers
        assert not acts["1100503"].apply_modifiers


class TestTortureGate:
    def test_ehr_gate_atk_double(self):
        """Torture：EHR≥75% 我方 ATK+100%（键名 effect_hit 勘正实证——错名门控永不通过）."""
        compiled = compile_encounter(_build(ally_ehr=0.8), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        assert "TORTURE_ATK" in ally.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["atk"], 3000.0, rel_tol=1e-9), (
            "1500×(1+1.0)")
        assert "TORTURE_ATK" not in _kf(eng).modifiers, "卡芙卡 EHR 0 不过门"


class TestUltimateShock:
    def test_ult_shock_detonate_and_thorns(self, compiled):
        """大招：AoE 0.8 + 全体触电挂载 + 引爆 120%×2.9（lv10 param(1100503,5)=1.2——
        2026-09-23 勘正：旧基线 1.0 误抄原版 100503 曲线，加强版官方 #5=1.2）
        + Thorns 充能 +1 + 行动回能 5."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        dmg = (0.8 + 1.2 * SHOCK_LV10) * KF_EFF * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, dmg, rel_tol=1e-9)
        assert "KAFKA_SHOCK" in e1.modifiers and "KAFKA_SHOCK" in e2.modifiers
        assert math.isclose(_kf(eng).resources["_fua_charges"], 1.0), "Thorns 大招后 +1"
        assert math.isclose(_kf(eng).current_energy, 5.0)

    def test_shock_tick_and_plunder(self, compiled):
        """触电跳伤 = 2.9×ATK×0.45（声明式 dot 通道：不暴击；EHR 0.18 命中区截
        1.0 中性）；Plunder 触电目标阵亡 +5 能."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _shock(eng, "e1")
        hp1 = e1.current_hp
        eng._tick_dots(e1)   # 声明式跳伤走引擎 A 类结算（非 on_turn_start 事件）
        assert math.isclose(hp1 - e1.current_hp, SHOCK_LV10 * KF_EFF * 0.45, rel_tol=1e-9)
        e2 = eng.state.actors["e2"]
        _shock(eng, "e2")
        e2.current_hp = 100.0
        _cast(eng, "1005", "1100501", target=e2)
        assert not e2.alive
        assert math.isclose(_kf(eng).current_energy, 20.0 + 5.0), "普攻 20 + Plunder 5"


class TestFuaChain:
    def test_fua_damage_energy_consume(self, compiled):
        """FUA：队友攻击怪物目标+充能≥1 → 1.4×ATK + 回能 10（过堂补记实证）+ 触电
        + 耗 1 充能；无充能不触发."""
        eng = _make(compiled)
        _kf(eng).resources["_fua_charges"] = 1.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        dmg = 1500 * ALLY_Z + 1.4 * KF_EFF * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9)
        assert "KAFKA_SHOCK" in e1.modifiers, "FUA 挂触电（1100504 #2 基础概率 1.0）"
        assert math.isclose(_kf(eng).current_energy, 10.0), "FUA 回能 10（deal_damage 不过路由——hook 补记）"
        assert math.isclose(_kf(eng).resources["_fua_charges"], 0.0)
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * ALLY_Z, rel_tol=1e-9), "无充能不追击"
        assert math.isclose(_kf(eng).current_energy, 10.0)

    def test_fua_turn_end_regen_and_monster_filter(self, compiled):
        """充能回复：卡芙卡回合结束 +1（1100504 #4）；目标过滤实证——队友行动目标为
        友方时不触发（过堂②：draft 无 monster 过滤会误击队友+白扣充能；纯事件注入，
        不过伤害路径——过滤判定只读事件载荷）."""
        eng = _make(compiled)
        eng.bus.emit("on_turn_end", {"actor": "1005"}, eng.state)
        assert math.isclose(_kf(eng).resources["_fua_charges"], 1.0)
        eng.bus.emit("on_action", {
            "actor": "ally", "action_type": "skill", "action_id": "ally_buff",
            "target_type": "ally_single", "target": "ally",
            "actor_type": "character"}, eng.state)
        assert math.isclose(_kf(eng).resources["_fua_charges"], 1.0), "友方目标不扣充能"
        assert math.isclose(_kf(eng).current_energy, 0.0), "友方目标不追击（monster 过滤实证）"
    def test_fua_triggers_on_inserted_ally_attack(self, compiled):
        """FUA 触发域含队友插入攻击（官方 "teammate uses an attack" 无插入排除——
        队友追击经 trigger_action 插入（insert=True）同触发；2026-09-24 勘正：
        旧 `!$event.insert` 闸把插入追击全漏=漏插，纯事件注入实证）."""
        eng = _make(compiled)
        _kf(eng).resources["_fua_charges"] = 1.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng.bus.emit("on_action", {
            "actor": "ally", "action_type": "follow_up", "action_id": "ally_fua",
            "target_type": "single", "target": "e1", "insert": True,
            "actor_type": "character"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 1.4 * KF_EFF * Z, rel_tol=1e-9), (
            "队友插入追击同触发 FUA（1.4×ATK 一段，不多插）")
        assert math.isclose(_kf(eng).resources["_fua_charges"], 0.0), "耗 1 充能"
        assert math.isclose(_kf(eng).current_energy, 10.0), "FUA 回能 10 随触发到账"

    def test_thorns_detonation_rides_fua_exactly_one_charge(self, compiled):
        """Thorns 引爆随 FUA 同发·恰 1 充能档（官方 11005103 "the Talent's Follow-Up
        ATK can cause all DoTs debuffs currently on the target to immediately produce
        DMG"——引爆 iff FUA 触发。emit 类事件条件统一快照求值：两钩同按事件前充能
        判定，FUA 效果先耗能不挡 Thorns——hooks.py _run_event_hooks_snapshot 实证）."""
        eng = _make(compiled)
        _kf(eng).resources["_fua_charges"] = 1.0
        _shock(eng, "e1")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        dmg = 1500 * ALLY_Z + 1.4 * KF_EFF * Z + 0.8 * SHOCK_LV10 * KF_EFF * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "恰 1 充能：FUA 1.4×ATK + Thorns 0.8×2.9×ATK 同发（非 FUA 发 Thorns 漏）")
        assert math.isclose(_kf(eng).resources["_fua_charges"], 0.0)

    def test_thorns_no_charge_no_detonation(self, compiled):
        """0 充能：FUA 与 Thorns 都不发（充能闩快照同灭——预挂触电也不引爆）."""
        eng = _make(compiled)
        _kf(eng).resources["_fua_charges"] = 0.0
        _shock(eng, "e1")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, 1500 * ALLY_Z, rel_tol=1e-9), (
            "0 充能：仅队友普攻一段——FUA 不发则 Thorns 无宿主可随")
        assert math.isclose(_kf(eng).current_energy, 0.0), "FUA 不发 → 回能 0"

    def test_thorns_no_duplicate_detonation_two_charges(self, compiled):
        """≥2 充能：Thorns 仍单发不重复（快照只过一次条件，非按效果后充能重判；
        FUA 耗 1 余 1）."""
        eng = _make(compiled)
        _kf(eng).resources["_fua_charges"] = 2.0
        _shock(eng, "e1")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        dmg = 1500 * ALLY_Z + 1.4 * KF_EFF * Z + 0.8 * SHOCK_LV10 * KF_EFF * Z
        assert math.isclose(hp1 - e1.current_hp, dmg, rel_tol=1e-9), (
            "2 充能档同 1 充能档伤害——Thorns 单发不重复引爆")
        assert math.isclose(_kf(eng).resources["_fua_charges"], 1.0), "耗 1 余 1"


class TestSkillDetonate:
    def test_main_and_adjacent_detonate(self, compiled):
        """战技引爆：主目标 75%×单跳 + 相邻（带触电）50%×单跳；官方"or the adjacent
        targets are currently afflicted with DoT"——相邻也需触电（过堂④实证）."""
        eng = _make(compiled)
        _shock(eng, "e1")
        _shock(eng, "e2")
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1005", "1100502")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.6 + 0.75 * SHOCK_LV10) * KF_EFF * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp,
                            (0.6 + 0.5 * SHOCK_LV10) * KF_EFF * Z, rel_tol=1e-9)

    def test_unshocked_adjacent_no_detonate(self, compiled):
        """相邻未感电：只吃 Blast 0.6，不吃引爆（where has_modifier 过滤实证）."""
        eng = _make(compiled)
        _shock(eng, "e1")
        e2 = eng.state.actors["e2"]
        hp2 = e2.current_hp
        _cast(eng, "1005", "1100502")
        assert math.isclose(hp2 - e2.current_hp, 0.6 * KF_EFF * Z, rel_tol=1e-9)


class TestEidolons:
    def test_e4_tick_energy(self):
        """E4：触电每跳 +2 能（_e4 闩开战置 1——跳伤 on_hp_decrease 触发）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(_kf(eng).resources["_e4"], 1.0)
        _shock(eng, "e1")
        eng._tick_dots(eng.state.actors["e1"])
        assert math.isclose(_kf(eng).current_energy, 2.0)

    def test_e6_shock_ratio(self):
        """E6：触电倍率 +156%（E5 大招+2 → 单跳 lv12=3.1827；合计 4.7427×ATK
        ——dot_ratio 表达式施加时烘焙）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        assert math.isclose(_kf(eng).resources["_e6_shock"], 1.0)
        e1 = eng.state.actors["e1"]
        _shock(eng, "e1", ratio=3.1827 + 1.56)   # E5 lv12 档 + E6 加成（烘焙后合计）
        hp1 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp1 - e1.current_hp, (3.1827 + 1.56) * KF_EFF * 0.45,
                            rel_tol=1e-9), (
            "E6 tick = 4.7427×ATK×0.45（不暴击——声明式 dot 通道）")
