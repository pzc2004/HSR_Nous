"""长夜月全机制模板端到端对轴（记忆战舰 demo）：真模板 YAML → 编译 → 忆质/长夜全链 → 手算全等.

链：进战召唤长夜（max_hp_ratio 0.5 继承 + SPD 160 + 双方增伤/免控/嘲讽 + 立即行动 + 烛火起
70 能 1 质）→ 战技（耗血 10%+天黑黑 5% → 天赋产质 + 忆灵暴伤光环 source_turn_start 走字）
→ 受击每目标限 1 次（trigger_limit per_action 双计数器）→ 忆质 ≥16（驱散控制+免疫+闩锁
立即行动）→ 开大（至暗之谜三件 + Charge 2，AoE 先于状态——官方序）→ 1141307（全耗消失 +
1141306 速度档 + Charge -1 → 回合开始判退）。数值全按 expected 模式手算对轴（默认档：
basic 6 / skill 10 / ult 10 / talent 10 / 忆灵 10——数组 index = 等级-1）。

口径常数：长夜月有效上限 = 1319.472×1.18 = 1556.97696（行迹 hp_pct 0.18 引擎结算）；
长夜 = ×0.5 = 778.48848；双方暴击 0.587（烘焙行迹+天黑黑 35%）/暴伤 0.633 起；
假人 def 0 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9；无冰增伤行迹（增伤区只有
孤独 0.5 / 至暗 0.6）。施放时序增益（+1/+2/用后 +1）按注册序计入当次伤害基数（模板
scaling_notes 在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

EVN_HP = 1319.472 * 1.18             # 1556.97696（行迹 hp_pct 0.18）
EVEY_HP = EVN_HP * 0.5               # 778.48848（141304 #5 max_hp_ratio）
DEF_RES = 0.5                        # 假人 def 0 口径
UNBROKEN = 0.9
CRIT_RATE = 0.587
CRIT_BASE = 1 + CRIT_RATE * 0.633    # 1.371571（无 buff 期望暴击区）
CRIT_FULL = 1 + CRIT_RATE * (0.633 + 0.6 + 0.15)    # 1.812751（天赋 0.6 lv10 + 天黑黑 0.15——勘正：旧取 lv14 行 0.72）
SOLITUDE = 0.5                       # 1141303 双方增伤 lv6（忆灵在场——忆灵槽 E0 上限 lv6 勘正后）
DR_DMG = 0.6                         # 至暗之谜双方增伤（lv10 勘正——旧取 lv11 行 0.63）
DR_VULN = 0.3                        # 至暗之谜敌方易伤（lv10 勘正——旧取 lv11 行 0.315）


def _build(*, pre_battle=None, two_enemies=False):
    b = {"build": {"team": [
        {"character_template": "1413", "level": 80},
        {"actor_id": "ally", "name": "火攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


def _stage(two_enemies=False):
    enemies = [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
                "max_toughness": 9999, "weakness": ["ice"]}]
    if two_enemies:
        enemies.append({"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
                        "max_toughness": 9999, "weakness": ["ice"]})
    return {"stage": {"stage_id": "s", "enemies": enemies,
                      "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled, *, initial_sp=10):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _cast(eng, owner, aid):
    """手动施放（_execute_action 不发 on_action——由调用方补发，同 _run_turn 口径）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": owner,
        "actor_type": st.actor.actor_type}, eng.state)


def _eve(eng):
    return eng.state.actors["1413"]


def _evey(eng):
    return eng.state.actors["1413_evey"]


class TestEvernightCompile:
    def test_summon_def_and_resources_registered(self, compiled):
        sd = compiled.summon_defs["1413_evey"]
        assert sd.owner_id == "1413" and isinstance(sd.inheritance, tuple), (
            "部分继承（hp/spd 覆写通道让位——full 会连 spd 一起替换）")
        assert "crit_rate" in sd.inheritance and "spd" not in sd.inheritance
        assert math.isclose(sd.max_hp_ratio, 0.5), "141304 #5：生命上限 = 长夜月 ×50%"
        assert math.isclose(sd.actor.stats.spd, 160.0), "141304 #4：初始速度 160"
        assert "memoria" in compiled.resource_decls_by_actor["1413"]
        assert {"_dr_charge", "_eve_latch", "_ult_pending"} <= set(
            compiled.resource_decls_by_actor["1413"])
        assert "_eve_on_field" not in compiled.resource_decls_by_actor["1413"], (
            "在场闩绝育（2026-09-17 收官）——在场判归 actor_alive 谓词，1222/1407 同批")
        tl = [r for r in compiled.resource_decls_by_actor["1413"] if r.startswith("_tl_")]
        assert len(tl) == 2, "受击限次双 hook 各自独立计数器（per-hook 粒度）"
        acts = {a.action_id for a in compiled.actions_by_actor["1413"]}
        assert {"141301", "141302", "141303"} <= acts
        eacts = {a.action_id: a for a in compiled.actions_by_actor["1413_evey"]}
        assert eacts["1141301"].prefer_target == "owner_last_target", "优先忆师末目标"
        assert eacts["1141307"].prefer_target == ""
        assert eacts["1141307"].available_if == (
            "resource_of('1413', 'memoria') >= 16 && !controlled('1413')"), (
            "施放条件（忆质≥16 且不受控）——available_if 收编（03_actor §3.8.1）")
        assert eacts["1141307"].available_if_expr is not None, "编译期预编译产物随 Action 携带"
        assert eacts["1141301"].available_if == ""
        ult = next(a for a in compiled.actions_by_actor["1413"] if a.action_id == "141303")
        assert ult.energy_cost == 240


class TestBattleStartSummon:
    def test_evey_inherits_max_hp_ratio_and_battle_start_gains(self, compiled):
        eng = _make(compiled)
        eve, evey = _eve(eng), _evey(eng)
        assert evey.alive
        assert math.isclose(_eve(eng).actor.stats.hp * 1.18, EVN_HP)
        assert math.isclose(evey.actor.stats.hp, EVEY_HP), (
            "长夜 Max HP = 召唤时刻长夜月有效上限 ×0.5（max_hp_ratio 继承首实例）")
        assert math.isclose(evey.current_hp, EVEY_HP)
        assert math.isclose(evey.actor.stats.spd, 160.0)
        assert math.isclose(evey.actor.stats.crit_rate, 0.587), "full 继承忆师面板（含烘焙）"
        # 1141303：忆灵免控/嘲讽/双方增伤 50%（lv6 #1）
        sm = evey.modifiers["EVE_SOLITUDE_SELF"]
        assert "control" in sm.grants_immune and math.isclose(sm.stat_effects["all_dmg"], 0.5)
        assert math.isclose(sm.stat_effects["aggro_boost"], 3.0)
        assert math.isclose(eve.modifiers["EVE_SOLITUDE_OWNER"].stat_effects["all_dmg"], 0.5)
        # 1413102 烛火起：进战 70 能 + 1 忆质
        assert math.isclose(eve.current_energy, 70.0)
        assert math.isclose(eve.resources["memoria"], 1.0)
        # 1141305：被召唤立即行动（剩余距离 0 到顶）
        h = eng.scheduler.handle_of("1413_evey")
        assert math.isclose(eng.scheduler._remaining[h], 0.0)


class TestSkillDrainAura:
    def test_skill_drains_gains_memoria_and_aura_ticks(self, compiled):
        eng = _make(compiled, initial_sp=5)
        eve, evey = _eve(eng), _evey(eng)
        evey.current_hp = 100.0                 # 留缺口——在场回复 50% 可观察
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        sp0 = eng.state.skill_points
        _cast(eng, "1413", "141302")
        # 耗血：战技 10% 当前 → 天黑黑 5% 当前（链序）——开局当前 HP = 有效上限
        # 1556.97696（B-TR① 引擎补口：行迹 hp_pct 0.18 抬上限后开局顶满——旧「抬上限
        # 不抬当前」布场口径退役）→ 1556.97696×0.9×0.95
        assert math.isclose(eve.current_hp, 1319.472 * 1.18 * 0.9 * 0.95, rel_tol=1e-9)
        drains = [p for p in drops if p["reason"] == "drain" and p["target"] == "1413"]
        assert len(drains) == 2, "战技耗 10% + 天黑黑耗 5% 两笔 drain"
        # 忆质：开局 1 + 天赋（10% drain）2 + 战技 2 + 天赋（5% drain）2 + 烛火起 1 = 8
        assert math.isclose(eve.resources["memoria"], 8.0)
        # 忆灵暴伤光环：值 = 0.24×(0.633+0.6) + 0.05（烘焙基数含本次耗血天赋——声明序在案）
        aura = evey.modifiers["EVE_SKILL_CRIT"]
        assert math.isclose(aura.stat_effects["crit_dmg"], 0.24 * 1.233 + 0.05, rel_tol=1e-9)
        assert aura.tick_anchor == "source_turn_start" and aura.duration == 2
        assert aura.source_id == "1413", "source=长夜月 → 按长夜月回合开始走字"
        # 天赋/天黑黑双暴件（耗血触发，双方各一）
        assert math.isclose(eve.modifiers["EVE_TALENT_CRIT"].stat_effects["crit_dmg"], 0.6)
        assert math.isclose(evey.modifiers["EVE_TALENT_CRIT"].stat_effects["crit_dmg"], 0.6)
        assert math.isclose(eve.modifiers["EVE_TRACE_CRIT"].stat_effects["crit_dmg"], 0.15)
        # 在场回复 50%（官方"若长夜已在场，回复其生命上限 50%"——忆灵侧自施口径）
        assert math.isclose(evey.current_hp, 100.0 + 0.5 * EVEY_HP)
        assert eng.state.skill_points == sp0  # 战技不耗点（owner 实战确认 + tbgd/米游社双源）
        assert math.isclose(eve.current_energy, 70.0 + 30.0 + 5.0), "战技 30 + 烛火起 5"
        # 光环走字：长夜月回合开始 -1（source_turn_start）——两次后到期
        eng._tick_source_modifiers(eve.actor, "source_turn_start")
        assert evey.modifiers["EVE_SKILL_CRIT"].duration == 1
        eng._tick_source_modifiers(eve.actor, "source_turn_start")
        assert "EVE_SKILL_CRIT" not in evey.modifiers, "长夜月两次回合开始后光环到期"


class TestTalentPerTargetPerAttack:
    def test_aoe_hits_both_triggers_each_but_multihit_once(self, compiled):
        eng = _make(compiled)
        eve = _eve(eng)
        eve.current_energy = 0.0
        m0 = eve.resources["memoria"]
        # 敌方 AoE（一次行动打全体——长夜月与长夜各触发 1 次 = +4；队友不入族）
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_aoe", name="横扫", action_type="basic", target_type="aoe",
            damage_type="physical", scaling=[{"atk": 0.1}])]}
        eng._enemy_turn(eng.state.actors["e1"])
        assert math.isclose(eve.resources["memoria"], m0 + 4.0), (
            "同一攻击双目标各触发 1 次（双 hook 独立计数器）")
        # 单体两段打长夜月（同一行动多段 = 每目标限 1 次 = +2）
        m1 = eve.resources["memoria"]
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_multi", name="连击", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 0.1}], instances=2)]}
        eng._pick_ally_target = lambda attacker=None: eve
        eng._enemy_turn(eng.state.actors["e1"])
        assert math.isclose(eve.resources["memoria"], m1 + 2.0), (
            "同一行动两段单体只触发 1 次（per_action 窗）")
        # 敌方行动结束已重置窗口（on_action 充满）——再次受击可再触发
        eng._enemy_turn(eng.state.actors["e1"])
        assert math.isclose(eve.resources["memoria"], m1 + 4.0)


class TestThresholdDispelLatch:
    def test_dispel_immune_and_latched_immediate(self, compiled):
        eng = _make(compiled)
        eve, evey = _eve(eng), _evey(eng)
        eve.resources["memoria"] = 15.0
        eng._apply_modifier(eve, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        h = eng.scheduler.handle_of("1413_evey")
        eng.scheduler._remaining[h] = 50.0
        eng._gain_resource(eve, "memoria", 1.0, source_id="1413")   # 跨 16 阈值
        assert "FRZ" not in eve.modifiers, "忆质≥16：驱散控制类 debuff（$mod filter）"
        assert "EVE_MEMORIA_IMMUNE" in eve.modifiers, "并免疫控制类"
        assert math.isclose(eng.scheduler._remaining[h], 0.0), "长夜立即行动（闩锁首触发）"
        assert math.isclose(eve.resources["_eve_latch"], 1.0)
        # 硬免疫：再挂控制件被拒
        eng._apply_modifier(eve, Modifier(
            modifier_id="FRZ2", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        assert "FRZ2" not in eve.modifiers
        # 闩锁：再次跨档不重复立即行动（驱散/免疫仍刷新）
        eng.scheduler._remaining[h] = 50.0
        eng._gain_resource(eve, "memoria", 1.0, source_id="1413")
        assert math.isclose(eng.scheduler._remaining[h], 50.0), "闩锁未复位不重复触发"
        # 忆灵施放 1141307 → 闩复位（联动半；全耗数值在专项对轴）
        eve.resources["memoria"] = 20.0
        eng.trigger_action(evey, next(a for a in eng.actions_by_actor["1413_evey"]
                                      if a.action_id == "1141307"), tag="test")
        assert math.isclose(eve.resources["_eve_latch"], 0.0), "施放 1141307 后闩复位"


class TestDarkestRiddle:
    def _ult(self, eng):
        eve = _eve(eng)
        ult = next(a for a in eng.actions_by_actor["1413"] if a.action_id == "141303")
        eve.current_energy = 240.0
        assert eng._fire_ultimate(eve, ult) is True

    def test_dr_aura_charge_and_exit(self, compiled):
        eng = _make(compiled)
        eve, evey, e1 = _eve(eng), _evey(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        self._ult(eng)
        # 至暗之谜三件：双方增伤 60%+免疫控制 / 敌方易伤 30%；充能 2
        dr = eve.modifiers["DARKEST_RIDDLE"]
        assert math.isclose(dr.stat_effects["all_dmg"], DR_DMG) and "control" in dr.grants_immune
        assert math.isclose(evey.modifiers["DR_EVEY"].stat_effects["all_dmg"], DR_DMG)
        vuln = e1.modifiers["DR_VULN"]
        assert vuln.modifier_type == "debuff" and math.isclose(
            vuln.stat_effects["vulnerability"], DR_VULN)
        assert math.isclose(eve.resources["_dr_charge"], 2.0)
        # 终结技 AoE（200%×长夜上限 lv10——勘正：旧取 lv11 行 210%）先于至暗之谜（官方序）——增伤区只有孤独 0.5
        expected = 2.0 * EVEY_HP * CRIT_FULL * DEF_RES * 1.0 * UNBROKEN * (1 + SOLITUDE)
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-6), (
            "AoE 先结后入状态——不吃 60%（吃孤独 70% 与双暴全件）")
        assert math.isclose(e1.toughness, 9999.0 - 30.0), (
            "141303 终结技削韧 30（米游社在案——忆灵侧 hook toughness_dmg 回填，冰弱点匹配）")
        assert math.isclose(eve.current_energy, 10.0), "240 扣尽 + 终结技 5 + 烛火起 5"
        # 忆灵施放 1141307 → 充能 -1；回合开始判：充能 1 ≥1 → 状态存续
        eve.resources["memoria"] = 20.0
        eng.trigger_action(evey, next(a for a in eng.actions_by_actor["1413_evey"]
                                      if a.action_id == "1141307"), tag="test")
        assert math.isclose(e1.toughness, 9999.0 - 60.0), (
            "1141307 削韧 30（单发——主目标补差段建模拆分不重复削）")
        assert math.isclose(eve.resources["_dr_charge"], 1.0)
        eng.bus.emit("on_turn_start", {"actor": "1413"}, eng.state)
        assert "DARKEST_RIDDLE" in eve.modifiers, "充能未尽——状态存续"
        # 充能耗尽 → 长夜月回合开始三件全摘
        eve.resources["_dr_charge"] = 0.0
        eng.bus.emit("on_turn_start", {"actor": "1413"}, eng.state)
        assert "DARKEST_RIDDLE" not in eve.modifiers
        assert "DR_VULN" not in e1.modifiers, "敌方易伤同步摘除"


class TestDreamDissolving:
    def test_full_consumption_dismiss_and_spd_buff_expiry(self, compiled):
        eng = _make(compiled, initial_sp=3)
        eve, evey, e1 = _eve(eng), _evey(eng), eng.state.actors["e1"]
        eve.resources["memoria"] = 20.0
        hp0 = e1.current_hp
        sp0 = eng.state.skill_points
        eng.trigger_action(evey, next(a for a in eng.actions_by_actor["1413_evey"]
                                      if a.action_id == "1141307"), tag="test")
        # 施放时序增益按注册序计入当次：20 + 天黑黑耗血天赋 2 + 烛火起 1 = 23 点基数
        per_pt = 0.06 * EVEY_HP   # 1141307 每点倍率 lv6 #2（忆灵槽勘正：E0 上限 lv6）
        expected = 2 * (23 * per_pt) * CRIT_FULL * DEF_RES * 1.0 * UNBROKEN * (1 + SOLITUDE)
        assert math.isclose(hp0 - e1.current_hp, expected, rel_tol=1e-6), (
            "主目标 16.8%+其余 8.4%（单敌两段合计 16.8%）×23 点——手算对轴")
        assert math.isclose(e1.toughness, 9999.0 - 30.0), (
            "1141307 削韧 30（米游社在案——hook AoE 段承担，补差段不重复削）")
        assert not evey.alive, "消耗全部 HP → 长夜消失"
        assert math.isclose(eve.resources["memoria"], 0.0), "消耗全部忆质（自耗键控件清零）"
        #（在场判 = actor_alive 谓词直查——_eve_on_field 手工闩 2026-09-17 绝育收官，
        #  上方 not evey.alive 即事实源断言，无需闩值回显）
        assert eng.state.skill_points == sp0 + 1, "天黑黑：忆灵施放如露后回 1 战技点"
        # 1141306 合并速度档：0.1 + 0.01×23 = 0.33（泛消失档 0.1 被闩互斥不覆盖）
        spd = eve.modifiers["EVEY_PARTING_SPD"]
        assert math.isclose(spd.stat_effects["spd_pct"], 0.33, rel_tol=1e-9)
        assert spd.duration == 1 and spd.tick_anchor == "owner_turn_start"
        # 到期锚：长夜月下回合开始移除
        eng._tick_modifiers(eve, "owner_turn_start")
        assert "EVEY_PARTING_SPD" not in eve.modifiers, "长夜月下个回合开始时移除"


class TestDreamGate:
    """1141307 施放条件闸（available_if）：忆质 ≥16 且长夜月不受控才可放."""

    @staticmethod
    def _legal_ids(eng):
        from hsr_nous.sim import legal_action_set
        evey = eng.state.actors["1413_evey"]
        legal = legal_action_set(evey, eng.actions_by_actor["1413_evey"], eng.state.skill_points)
        legal = eng._legal_with_available_if(evey, legal)   # 与 _summon_turn 同漏斗
        return {a.action_id for a in legal}

    def test_memoria_tier_and_cc_gate(self, compiled):
        eng = _make(compiled)
        eve = _eve(eng)
        assert self._legal_ids(eng) == {"1141301"}, "开局忆质 1 < 16：如露被闸"
        eve.resources["memoria"] = 15.0
        assert "1141307" not in self._legal_ids(eng), "15 < 16：仍未达档"
        eve.resources["memoria"] = 16.0
        assert "1141307" in self._legal_ids(eng), "16 ≥ 16：进合法集"
        # 不受控条件：直挂冻结（不过 _gain_resource——避开 ≥16 驱散/免疫 hook 链）
        eng._apply_modifier(eve, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        assert "1141307" not in self._legal_ids(eng), "长夜月受控：如露出集（官方'不受控'）"
        assert "1141301" in self._legal_ids(eng), "追忆无施放条件——恒在集"
        eve.modifiers.clear()
        assert "1141307" in self._legal_ids(eng), "控制解除：回集"


class TestGenericDismissSpdBuff:
    def test_non_dream_dismiss_flat_spd_buff(self, compiled):
        """1141306 泛消失档：非 1141307 消失 → 速度 +10%（闩互斥的另一支）."""
        eng = _make(compiled)
        eve = _eve(eng)
        assert eng.dismiss_summon_actor("1413_evey") is True
        spd = eve.modifiers["EVEY_PARTING_SPD"]
        assert math.isclose(spd.stat_effects["spd_pct"], 0.1), "泛消失只有 10% 基础档"
        assert "EVE_SOLITUDE_OWNER" not in eve.modifiers, "消失即摘双方增伤（忆师件）"


class TestEveyPreferTarget:
    def test_evey_targets_evernight_last_attacked(self):
        build, stage = _build(two_enemies=True), _stage(two_enemies=True)
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=10)
        eng.setup()
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        # 长夜月普攻锁 e2（决策层覆写——真实行动链记账 _last_target_by_actor）
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: next(
            c for c in candidates if c.actor.actor_id == "e2")
        _cast(eng, "1413", "141301")
        assert eng._last_target_by_actor.get("1413") == "e2"
        # 长夜自动回合：1141301 优先忆师最后攻击的敌人——e2 吃主段+追加段，e1 无伤
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: None
        e1_hp0, e2_hp0 = e1.current_hp, e2.current_hp
        eng._summon_turn(_evey(eng))
        assert math.isclose(e1.current_hp, e1_hp0), "非忆师末目标——不挨打"
        # 忆质账：开局 1 + 长夜月普攻链（天赋 2 + 烛火起 1）= 4；长夜 1141301 链
        #（天赋 2 + 烛火起 1）= 7 → 追加 7//4=1 段 ×0.10；主段 0.5（lv6 #1/#2——忆灵槽勘正；双暴全件 + 孤独）
        memoria = _eve(eng).resources["memoria"]
        assert math.isclose(memoria, 7.0)
        expected = (0.5 + (7 // 4) * 0.10) * EVEY_HP * CRIT_FULL * DEF_RES * 1.0 * UNBROKEN * (
            1 + SOLITUDE)
        assert math.isclose(e2_hp0 - e2.current_hp, expected, rel_tol=1e-6), (
            "主段 0.5 + 每 4 点忆质 0.10 追加——优先命中忆师末目标 e2")


class TestTechnique:
    def test_technique_prebattle(self):
        build = _build(pre_battle=[{"actor_id": "1413", "technique": "141307"}])
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        eve, evey = _eve(eng), _evey(eng)
        # 秘技：进战获战技同款光环（开局无天赋件——烘焙 0.24×0.633+0.05）+ 1 忆质
        aura = evey.modifiers.get("EVE_SKILL_CRIT")
        assert aura is not None, "秘技光环随长夜进场挂上（途标→actor_enter 消费）"
        assert math.isclose(aura.stat_effects["crit_dmg"], 0.24 * 0.633 + 0.05, rel_tol=1e-9)
        assert aura.tick_anchor == "source_turn_start"
        assert math.isclose(eve.resources["memoria"], 2.0), "秘技 1 + 烛火起 1"
        assert math.isclose(eve.resources["_tech_pending"], 0.0), "途标已消费清零"


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        eng = _make(compiled)
        _eve(eng).current_energy = 230.0       # 政策窗口开战技/普攻后满 240 自动开大
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert "1413_evey" in state.actors, "长夜已入场"
        assert any("追忆，蹁跹，如雨" in l for l in log), "长夜自动回合施放忆灵技（首合法行动）"
        assert any("晚安，全世界无眠" in l for l in log), "政策窗口满能自动开大"
        assert "DARKEST_RIDDLE" in state.actors["1413"].modifiers, "至暗之谜存续"
        assert state.actors["1413"].resources["memoria"] >= 0.0


class TestDawnTier:
    """1413103 大行迹「天亮了，雨落了」：队伍「记忆」命途人数变档（count_team 通道对轴）."""

    def test_two_remembrance_tier(self):
        # demo 队 1 记忆 → +0.05（TestSkillDrainAura 已轴）；本队 +1 记忆队友 → 2 记忆档 +0.15
        build = {"build": {"team": [
            {"character_template": "1413", "level": 80},
            {"actor_id": "m2", "name": "记忆队友", "inline": True, "path": "remembrance",
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "m2_b", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "ice",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        ], "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=5)
        eng.setup()
        assert eng._count_team_path("remembrance") == 2.0, "1413 + 记忆队友 = 2（忆灵不计）"
        _cast(eng, "1413", "141302")
        aura = _evey(eng).modifiers["EVE_SKILL_CRIT"]
        assert math.isclose(aura.stat_effects["crit_dmg"], 0.24 * 1.233 + 0.15, rel_tol=1e-9), (
            "2 记忆档 +0.15（1/2/3/≥4 → +0.05/0.15/0.5/0.65——施加时刻快照，编成战中不变）")


def _compile_eidolon(n: int, *, two_enemies: bool = False):
    b = _build()
    b["build"]["team"][0]["eidolon"] = n
    return compile_encounter(b, _stage(two_enemies=two_enemies), template_roots=TEST_TEMPLATE_ROOTS)


class TestEvernightEidolons:
    """长夜月 E1-E6 星魂（member.eidolon 激活——数值/机制照 ranks_detail 官方文本）."""

    def test_e3_e5_skill_level_overrides(self):
        lv3 = next(a for a in _compile_eidolon(3).build_team if a.actor_id == "1413").skill_levels
        assert lv3["skill"] == 12 and lv3["basic"] == 7, "E3：战技+2、普攻+1"
        lv5 = next(a for a in _compile_eidolon(5).build_team if a.actor_id == "1413").skill_levels
        assert lv5["ultimate"] == 12 and lv5["talent"] == 12, "E5：终结技+2、天赋+2"

    def test_e3_e5_hook_segments_follow_level(self):
        """param() 随档实证：E3 skill+2 → 忆灵暴伤光环系数取 lv12=0.264；
        E5 ult+2/talent+2 → 至暗增伤/天赋暴伤同取 lv12=0.66（编译期替换产物直读；
        lv10 正档 0.24/0.6/0.6——回填勘正后基线）."""
        c3 = _compile_eidolon(3)
        aura = [eff["modifier"]["stat_effects"]["crit_dmg"] for h in c3.hooks
                for eff in h.effects
                if eff.get("effect_type") == "apply_modifier"
                and (eff.get("modifier") or {}).get("modifier_id") == "EVE_SKILL_CRIT"]
        assert aura and aura[0].startswith("0.264 *"), f"暴伤光环系数随档 lv12=0.264：{aura}"
        c5 = _compile_eidolon(5)
        dr = [eff["modifier"]["stat_effects"]["all_dmg"] for h in c5.hooks
              for eff in h.effects
              if eff.get("effect_type") == "apply_modifier"
              and (eff.get("modifier") or {}).get("modifier_id") == "DARKEST_RIDDLE"]
        assert dr and all(math.isclose(v, 0.66) for v in dr), f"至暗增伤随档 lv12=0.66：{dr}"
        tc = [eff["modifier"]["stat_effects"]["crit_dmg"] for h in c5.hooks
              for eff in h.effects
              if eff.get("effect_type") == "apply_modifier"
              and (eff.get("modifier") or {}).get("modifier_id") == "EVE_TALENT_CRIT"]
        assert tc and all(math.isclose(v, 0.66) for v in tc), f"天赋暴伤随档 lv12=0.66：{tc}"

    def test_e1_memosprite_final_dmg_tiers(self):
        eng = _make(_compile_eidolon(1))
        evey = _evey(eng)
        assert "E1_MEMO_FINAL_DMG" in evey.modifiers, "忆灵逐个挂（开局天赋召唤同覆盖）"
        assert math.isclose(
            eng.pipeline.effective_stats(evey)["dmg_bonus"].get("final_dmg_boost", 0.0), 0.5), (
            "敌方 1 名 → 原伤害 150%（独立乘区 dmg_final_dmg_boost）")
        eng2 = _make(_compile_eidolon(1, two_enemies=True))
        assert math.isclose(
            eng2.pipeline.effective_stats(_evey(eng2))["dmg_bonus"].get("final_dmg_boost", 0.0),
            0.3), "敌方 2 名 → 130%"
        # 减员 live 变档：击杀一个 → 回到 1 名档（懒求值零 stale）
        e1 = next(s for s in eng2.state.actors.values() if s.actor.actor_id == "e1")
        e1.current_hp = 0.0
        e1.alive = False
        assert math.isclose(
            eng2.pipeline.effective_stats(_evey(eng2))["dmg_bonus"].get("final_dmg_boost", 0.0),
            0.5), "敌方减员至 1 名 → 现场变档 150%"

    def test_e2_crit_dmg_and_memoria_gain_bonus(self):
        eng = _make(_compile_eidolon(2))
        eve = _eve(eng)
        assert math.isclose(eng.pipeline.effective_stats(eve)["crit_dmg"], 0.633 + 0.4), (
            "E2：长夜月暴伤 +40%（eidolon stat_effects 常驻件）")
        assert math.isclose(eng.pipeline.effective_stats(_evey(eng))["crit_dmg"], 0.633 + 0.4), (
            "E2：忆灵「长夜」暴伤 +40%（忆灵侧件）")
        assert math.isclose(eve.resources["memoria"], 3.0), (
            "烛火起 +1 → E2 补 +2 = 3（获得数量+2 进战即生效；防自循环闩不炸）")
        eng._gain_resource(eve, "memoria", 2.0, source_id="1413")   # 天赋族 +2 → E2 再 +2
        assert math.isclose(eve.resources["memoria"], 3.0 + 4.0), "每当获得忆质 +2（3+2+2=7…实 3+4）"

    def test_e4_memosprite_break_efficiency(self):
        eng = _make(_compile_eidolon(4))
        evey = _evey(eng)
        assert {"E4_MEMO_BREAK_EFF", "E4_EVEY_BREAK_EFF"} <= set(evey.modifiers)
        assert math.isclose(
            eng.pipeline.effective_stats(evey)["weakness_break_efficiency_boost"], 0.5), (
            "忆灵通用 +25% + 长夜额外 +25% = 50%（阮梅/流萤同池）")

    def test_e6_res_pen_and_memoria_return(self):
        eng = _make(_compile_eidolon(6))
        eve = _eve(eng)
        assert "E6_TEAM_RES_PEN" in eve.modifiers
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"], 0.2), (
            "长夜月在场：我方全体全属性抗性穿透 +20%（team 光环）")
        eve.resources["memoria"] = 20.0
        eng.trigger_action(_evey(eng), next(
            a for a in eng.actions_by_actor["1413_evey"] if a.action_id == "1141307"), tag="test")
        # 池账：20 起 → 天黑黑耗血天赋 +2(+E2+2) → 烛火起 +1(+E2+2) → 自耗天赋 +2(+E2+2) = 31
        # → 键控件全耗 31 → E6 返 30%=9.3 → E2 +2 → 11.3（"本次消耗忆质"=全耗时刻整池）
        assert math.isclose(eve.resources["memoria"], 11.3), (
            "如露全耗 31 → E6 返还 30%=9.3 → E2 获得+2 → 11.3（负值事件+_eve_used_1307 闩识别）")
