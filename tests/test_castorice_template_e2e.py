"""遐蝶全机制模板端到端对轴（记忆战舰 demo）：真模板 YAML → 编译 → 新蕊/死龙全链 → 手算全等.

链：T1 战技（drain_hp 耗全队当前 30% 保底 1 → 天赋产新蕊 + 增伤双件 2 层）
→ 满蕊开大（ult_cost_resource 门槛 + 扣 34000；召唤死龙 Max HP=新蕊上限×100%、死龙提前 100%、
境界 res_pen 光环）→ 在场转化不产蕊（失 HP 等量回死龙）→ 替身保底 1（waterfall cancel +
死龙承担 5%）→ 焰息连发倍率递增（0.336/0.392/0.476 不清零 + 西风驻足 + 天赋增伤命中）
→ 3 回合消失 / 低血消失 → 1140706 消逝 6 段+全体治疗+境界摘除。数值全按 expected 模式
手算对轴（默认档：basic 6 / skill 10 / ult 10 / talent 10 / 忆灵 10——数组 index = 等级-1）。

口径常数：遐蝶有效上限 = 1629.936（无生命%行迹）；死龙 = 34000（新蕊上限×100%）；
假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0（境界后 1.2）、未击破 0.9；
遐蝶/死龙暴击 0.237/0.633（同面板）→ 期望暴击区 1.150021。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.resources import ultimate_available
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

CAS_HP = 1629.936
NW_HP = 34000.0                       # = 新蕊上限 ×100%（ult lv10 #3）
DEF_RES = 0.5                         # 假人 def 0 口径（缺省防御 → def_multi 0.5）
UNBROKEN = 0.9
CRIT_EXP = 1 + 0.237 * 0.633          # 1.150021（遐蝶/死龙同面板）
RES_TERR = 1.2                        # 境界：抗性区 1 - (0 - 0.2)
QDMG = 0.144                          # 行迹量子增伤（遐蝶/死龙同面板烘焙；增伤区与 all_dmg 加算）


def _build(*, pre_battle=None):
    b = {"build": {"team": [
        {"character_template": "1407", "level": 80},
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


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


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


def _ult(eng):
    """满蕊开大（_fire_ultimate 正规路径：资源门槛 + 扣 34000）."""
    cas = eng.state.actors["1407"]
    ult = next(a for a in eng.actions_by_actor["1407"] if a.action_id == "140703")
    cas.resources["newbud"] = 34000.0
    assert ultimate_available(cas, ult), "新蕊满 → 终结技可激活（特殊充能资源门槛）"
    assert eng._fire_ultimate(cas, ult) is True


def _nw(eng):
    return eng.state.actors["1407_netherwing"]


class TestCastoriceCompile:
    def test_summon_def_and_resources_registered(self, compiled):
        sd = compiled.summon_defs["1407_netherwing"]
        assert sd.owner_id == "1407" and sd.inheritance == "none", (
            "Max HP=新蕊上限×100% 常量基数——hp 分量不继承")
        assert math.isclose(sd.actor.stats.hp, NW_HP)
        assert math.isclose(sd.actor.stats.spd, 165.0), "140703 #1：初始速度 165"
        assert math.isclose(sd.actor.stats.crit_rate, 0.237), "其余面板照忆师烘焙（12.4 继承口径）"
        assert {"_breath_n", "_nw_turns"} <= set(compiled.resource_decls_by_actor["1407_netherwing"])
        assert "newbud" in compiled.resource_decls_by_actor["1407"]
        acts = {a.action_id for a in compiled.actions_by_actor["1407"]}
        assert {"140701", "140702", "140703", "140709"} <= acts
        by_id = {a.action_id: a for a in compiled.actions_by_actor["1407"]}
        assert by_id["140702"].available_if == "res__nw_on_field < 1", (
            "换技能互斥半：死龙不在场才可用（available_if——03_actor §3.8.1）")
        assert by_id["140702"].available_if_expr is not None, "编译期预编译产物随 Action 携带"
        assert by_id["140709"].available_if == "res__nw_on_field >= 1", (
            "换技能互斥半：仅死龙在场可用（与 140702 互补——同槽替换）")
        assert by_id["140701"].available_if == "" and by_id["140703"].available_if == ""
        ult = next(a for a in compiled.actions_by_actor["1407"] if a.action_id == "140703")
        assert ult.ult_cost_resource == "newbud" and ult.ult_cost_amount == 34000.0
        assert ult.apply_modifiers[0]["modifier_id"] == "LOST_NETHERLAND"
        assert ult.apply_modifiers[0]["effect_scope"] == "team", "境界挂遐蝶辐射全队（含后入场死龙）"


class TestSkillDrainNewbud:
    def test_skill_drains_30pct_and_gains_newbud(self, compiled):
        eng = _make(compiled, initial_sp=5)
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        cas = eng.state.actors["1407"]
        ally = eng.state.actors["ally"]
        e1 = eng.state.actors["e1"]
        e1_hp0 = e1.current_hp
        sp0 = eng.state.skill_points
        _cast(eng, "1407", "140702")
        # drain_hp：全队当前 30%（floor 1）——遐蝶 0.3×1629.936 / 队友 0.3×3000
        assert math.isclose(cas.current_hp, CAS_HP - 0.3 * CAS_HP)
        assert math.isclose(ally.current_hp, 3000.0 - 900.0)
        drain_events = [p for p in drops if p["reason"] == "drain"]
        assert {p["target"] for p in drain_events} == {"1407", "ally"}
        # 140704：死龙不在场 → 失 HP 全量产新蕊（1 点换 1 点）
        assert math.isclose(cas.resources["newbud"], 0.3 * CAS_HP + 900.0)
        # 天赋增伤双件：2 个失 HP 事件 → 2 层（本动伤害先于 hooks 结算，不吃本动增伤）
        stacks = cas.modifiers["NEWBUD_DMG_STACKS"]
        boost = cas.modifiers["NEWBUD_DMG_BOOST"]
        assert stacks.stacks == 2 and math.isclose(boost.stat_effects["all_dmg"], 0.4)
        # 战技伤害（blast 单敌主目标 lv10 0.5×遐蝶上限；无增伤/无境界）
        expected = 0.5 * CAS_HP * CRIT_EXP * DEF_RES * 1.0 * UNBROKEN * (1 + QDMG)
        assert math.isclose(e1_hp0 - e1.current_hp, expected, rel_tol=1e-6)
        assert eng.state.skill_points == sp0  # 战技不耗点（tbgd BPNeed sp_cost 0 + 米游社无消耗标）
        assert cas.current_energy == 0.0, "特殊充能角色无能量（fandom 回能 0）"

    def test_skill_floor_one(self, compiled):
        """当前生命不足时降至 1 点（drain floor 1）."""
        eng = _make(compiled)
        cas = eng.state.actors["1407"]
        cas.current_hp = 100.0
        _cast(eng, "1407", "140702")
        assert math.isclose(cas.current_hp, 70.0), "耗当前 30%（非上限）——100→70"
        cas.current_hp = 1.0
        eng.state.actors["ally"].current_hp = 1.0
        nb0 = cas.resources["newbud"]
        _cast(eng, "1407", "140702")
        assert math.isclose(cas.current_hp, 1.0), "floor 1：耗不致死"
        assert math.isclose(cas.resources["newbud"], nb0), "全队 HP=1 时实际流失 0 → 不产新蕊"


class TestUltimateSummon:
    def test_full_newbud_ult_summons_netherwing(self, compiled):
        eng = _make(compiled)
        _ult(eng)
        cas = eng.state.actors["1407"]
        nw = _nw(eng)
        assert math.isclose(cas.resources["newbud"], 0.0), "开大扣全部新蕊 34000"
        assert nw.alive
        assert math.isclose(nw.actor.stats.hp, NW_HP) and math.isclose(nw.current_hp, NW_HP), (
            "死龙 Max HP = 新蕊上限 ×100%（140703 #3）")
        assert math.isclose(nw.actor.stats.spd, 165.0)
        h = eng.scheduler.handle_of("1407_netherwing")
        assert h not in eng.scheduler._frozen, "死龙上行动条（与 av:false 小伊卡相反）"
        assert math.isclose(eng.scheduler._remaining[h], 0.0), "140703：死龙行动提前 100%"
        # 境界【遗世冥域】：挂遐蝶 effect_scope team 光环 res_pen 0.2
        terr = cas.modifiers["LOST_NETHERLAND"]
        assert terr.effect_scope == "team" and math.isclose(terr.stat_effects["res_pen"], 0.2)
        # 1140705：被召唤时全体伤害 +10%（3 回合）
        assert "NETHERWING_ROAR" in cas.modifiers and "NETHERWING_ROAR" in nw.modifiers
        # 抗性区对轴：境界后遐蝶普攻 = 0.5 档 ×乘区 ×1.2 ×(1+ROAR 0.1)
        e1 = eng.state.actors["e1"]
        dmg0 = eng.state.total_damage
        _cast(eng, "1407", "140701")
        expected = 0.5 * CAS_HP * CRIT_EXP * DEF_RES * RES_TERR * UNBROKEN * (1 + QDMG + 0.1)
        assert math.isclose(eng.state.total_damage - dmg0, expected, rel_tol=1e-6), (
            "境界抗性区 1.2 + 怒啸增伤 10%")


class TestConversionNoNewbud:
    def test_hp_loss_converts_to_netherwing_not_newbud(self, compiled):
        eng = _make(compiled)
        _ult(eng)
        cas = eng.state.actors["1407"]
        nw = _nw(eng)
        ally = eng.state.actors["ally"]
        nw.current_hp = 20000.0                 # 留出转化空间
        cas.current_hp = 1000.0
        ally.current_hp = 2000.0
        nb0 = cas.resources["newbud"]
        # 敌方攻击注入（inline 敌人无行动表——手动给一刀，1409 同款直调；rebind 拷贝
        # 不污染 module 级 compiled 的共享 actions_by_actor）
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_slash", name="挥砍", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 0.5}])]}
        e1 = eng.state.actors["e1"]
        eng._enemy_turn(e1)
        hit_target = ally if ally.current_hp < 2000.0 else cas
        lost = (2000.0 if hit_target is ally else 1000.0) - hit_target.current_hp
        assert lost > 0
        assert math.isclose(cas.resources["newbud"], nb0), "死龙在场：失 HP 不产新蕊（140704）"
        assert math.isclose(nw.current_hp, 20000.0 + lost), (
            "全队（除死龙）失去的 HP 等量转化为死龙 HP")


class TestBackupFloorOne:
    def test_netherwing_bears_lethal_damage(self, compiled):
        eng = _make(compiled)
        _ult(eng)
        nw = _nw(eng)
        ally = eng.state.actors["ally"]
        ally.current_hp = 100.0
        nw.current_hp = 20000.0                # 留缺口——满血时转化 heal 实回 0 不可观察
        # 致命刀注入（atk 拉满确保一刀 >> 100；rebind 拷贝不污染共享表）
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_heavy", name="重击", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 50.0}])]}
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        e1 = eng.state.actors["e1"]
        # 锁队友成唯一目标（遐蝶满血 1629.936，队友 100——forced_taunt 太重，直调目标选择）
        eng._pick_ally_target = lambda attacker=None: ally
        eng._enemy_turn(e1)
        assert math.isclose(ally.current_hp, 1.0), "1140703：当前 HP 最多降至 1 点"
        assert ally.alive
        ally_drain = next(p for p in drops if p["target"] == "ally" and p["reason"] == "drain")
        assert math.isclose(ally_drain["amount"], 99.0), "降至 1 = 流失 hp-1"
        nw_drain = next(p for p in drops
                        if p["target"] == "1407_netherwing" and p["reason"] == "drain")
        original = nw_drain["amount"] / 0.05
        # 死龙净变化：承担 -5%×原值 + 转化 +99（140704 在场转化同链）
        assert math.isclose(nw.current_hp, 20000.0 - 0.05 * original + 99.0)
        assert original > 99.0, "原伤害足以致命才触发替身"


class TestBreathRamp:
    def test_breath_multiplier_ramps_and_persists(self, compiled):
        eng = _make(compiled)
        _ult(eng)
        cas = eng.state.actors["1407"]
        nw = _nw(eng)
        breath = next(a for a in eng.actions_by_actor["1407_netherwing"]
                      if a.action_id == "1140702")
        expected_mults = [0.336, 0.392, 0.476]
        for i, mult in enumerate(expected_mults):
            nw_boost = nw.modifiers.get("NEWBUD_DMG_BOOST")
            talent = nw_boost.stat_effects["all_dmg"] if nw_boost else 0.0
            ww = nw.modifiers.get("WESTWIND_BOOST")
            westwind = ww.stat_effects["all_dmg"] if ww else 0.0
            assert math.isclose(talent, 0.2 * i) and math.isclose(westwind, 0.3 * i)
            hp_before = nw.current_hp
            dmg0 = eng.state.total_damage
            eng.trigger_action(nw, breath, tag="test")     # 连发=同回合插入再放
            assert math.isclose(hp_before - nw.current_hp, 8500.0), (
                "每发耗自身 Max HP 25%（1140702 #1）")
            expected = (CAS_HP * mult * CRIT_EXP * DEF_RES * RES_TERR * UNBROKEN
                        * (1 + QDMG + 0.1 + 0.2 * (i + 1) + westwind))
            actual = eng.state.total_damage - dmg0
            assert math.isclose(actual, expected, rel_tol=1e-6), (
                f"第 {i + 1} 发：倍率 {mult}（递增不清零）+ 天赋 {0.2 * (i + 1)}"
                f"（drain 先于伤害——本发吃当次叠层）+ 西风 {westwind} + 怒啸 0.1"
                f"——手算 {expected:.2f} vs {actual:.2f}")
        assert math.isclose(nw.resources["_breath_n"], 3.0)
        assert math.isclose(nw.current_hp, NW_HP - 3 * 8500.0)
        assert nw.alive, "第 3 发后 HP=8500=25% 档——施放前判（快照）不触发低血消失"
        # 第 4 发：施放前 HP 8500 ≤ 25%×34000 → 主动降到 1 + 触发 1140706 消失链
        eng.state.actors["ally"].current_hp = 100.0      # 留缺口——满血治疗实回 0 不可观察
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        eng.trigger_action(nw, breath, tag="test")
        assert math.isclose(nw.current_hp, 1.0), "低血档：drain floor 1 主动降到 1"
        assert not nw.alive, "≤25% 档施放 → 触发等同 1140706 的消失"
        heal = sum(g["amount"] for g in gains if g["reason"] == "heal")
        assert heal > 0, "消失链带出 1140706 全体治疗"
        assert "LOST_NETHERLAND" not in cas.modifiers, "消失即解除境界"


class TestDismissAndWings:
    def test_wings_bounce_and_team_heal(self, compiled):
        eng = _make(compiled)
        _ult(eng)
        cas = eng.state.actors["1407"]
        ally = eng.state.actors["ally"]
        ally.current_hp = 100.0                  # 留出治疗空间
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        assert math.isclose(e1.toughness, 9999.0 - 30.0), (
            "1140706 消逝 6 段逐段各削 5（米游社在案——hook toughness_dmg 回填）")
        # 1140706：6 段随机单体（expected 确定化按序取首=e1），每段 56%×遐蝶上限；
        # 增伤区只有怒啸 10%（开大链无失血，天赋 0 层）
        per_hit = 0.56 * CAS_HP * CRIT_EXP * DEF_RES * RES_TERR * UNBROKEN * (1 + QDMG + 0.1)
        assert math.isclose(hp0 - e1.current_hp, 6 * per_hit, rel_tol=1e-6)
        # 全体治疗 8.4%×遐蝶上限 + 1120（遐蝶满血实回 0；队友 100 → 全额）
        heal_amount = 0.084 * CAS_HP + 1120
        assert math.isclose(ally.current_hp, 100.0 + heal_amount)
        healed = {g["target"]: g["amount"] for g in gains if g["reason"] == "heal"}
        assert math.isclose(healed.get("ally", 0.0), heal_amount)
        assert "1407_netherwing" not in healed, "死龙已离场不吃治疗"
        # 收容的暗潮：死龙不在场 → 治疗 12% 转化为新蕊（开大已扣光）
        assert math.isclose(cas.resources["newbud"], 0.12 * heal_amount, rel_tol=1e-6)
        assert "LOST_NETHERLAND" not in cas.modifiers, "境界随死龙消失解除"
        # 境界摘除后抗性区回落 1.0（怒啸 3 回合独立走字，不随死龙消失解除——1140705 官方
        # "持续 3 回合"无消失联动，增伤区仍含 0.1）
        dmg0 = eng.state.total_damage
        _cast(eng, "1407", "140701")
        expected = 0.5 * CAS_HP * CRIT_EXP * DEF_RES * 1.0 * UNBROKEN * (1 + QDMG + 0.1)
        assert math.isclose(eng.state.total_damage - dmg0, expected, rel_tol=1e-6)

    def test_joint_claw_toughness_10_plus_10(self, compiled):
        """140709 骸爪连携：遐蝶半 action 层削韧 10 + 死龙半 hook deal_damage 削韧 10（fandom "10+10"）."""
        eng = _make(compiled)
        _ult(eng)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1407", "140709")
        assert math.isclose(e1.toughness, 9999.0 - 20.0), (
            "遐蝶半 action 10 + 死龙半 hook 10（米游社/fandom 在案——hook toughness_dmg 回填）")

    def test_three_turns_dismiss(self, compiled):
        """140703 #2：死龙经过 3 个回合后消失（行动计数满 3 即 dismiss）."""
        eng = _make(compiled)
        _ult(eng)
        nw = _nw(eng)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        for i in range(2):
            _cast(eng, "1407_netherwing", "1140701")
            assert nw.alive and math.isclose(nw.resources["_nw_turns"], i + 1)
        eng.state.actors["ally"].current_hp = 100.0      # 留缺口——满血治疗实回 0 不可观察
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        _cast(eng, "1407_netherwing", "1140701")           # 第 3 动 → 本动结算后消失
        assert not nw.alive
        # 爪痕 3 发（56%×遐蝶上限×乘区——无天赋层/有怒啸）+ 消逝 6 段同倍率
        per_claw = 0.56 * CAS_HP * CRIT_EXP * DEF_RES * RES_TERR * UNBROKEN * (1 + QDMG + 0.1)
        assert math.isclose(hp0 - e1.current_hp, 3 * per_claw + 6 * per_claw, rel_tol=1e-6)
        assert any(g["reason"] == "heal" for g in gains), "3 回合消失同样触发 1140706 治疗"


class TestTechnique:
    def test_technique_prebattle(self):
        build = _build(pre_battle=[{"actor_id": "1407", "technique": "140707"}])
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        eng.setup()                                    # on_battle_start 在此发射——先订阅再 setup
        cas = eng.state.actors["1407"]
        ally = eng.state.actors["ally"]
        nw = _nw(eng)
        # 死龙入场当前 HP = 新蕊上限×50%（#2，布场 drain 等值承载）；耗全队（除死龙）当前
        # 40%（#1）；死龙在场 → 耗血不产新蕊、等量转化为死龙 HP（50% 基础上回）——终态对轴
        assert math.isclose(cas.current_hp, CAS_HP * 0.6)
        assert math.isclose(ally.current_hp, 3000.0 * 0.6)
        assert math.isclose(cas.resources["newbud"], 0.0)
        converted = 0.4 * CAS_HP + 0.4 * 3000.0
        assert math.isclose(nw.current_hp, 0.5 * NW_HP + converted)
        assert "LOST_NETHERLAND" in cas.modifiers, "秘技展开境界"
        h = eng.scheduler.handle_of("1407_netherwing")
        assert math.isclose(eng.scheduler._remaining[h], 0.0), "死龙行动提前 100%"


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        eng = _make(compiled)
        # 预置新蕊近满（drain 按当前 HP 几何衰减，1500 AV 自然攒不满 34000——smoke 验链路
        # 跑通，数值对轴在专项测试）：首动战技后满蕊 → 政策窗口开大 → 死龙在场窗口
        # 遐蝶多动（SP 未枯竭）→ 骸爪真实上场
        eng.state.actors["1407"].resources["newbud"] = 33500.0
        casts = []
        eng.bus.subscribe("on_action", lambda et, p, ctx: casts.append(
            (p["action_id"], eng.state.actors["1407"].resources.get("_nw_on_field", 0.0))))
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert any("亡喉怒哮，苏生之颂铃" in l for l in log), "政策窗口满蕊自动开大"
        assert "1407_netherwing" in state.actors, "死龙已入场"
        assert any("擘裂冥茫的爪痕" in l or "燎尽黯泽的焰息" in l for l in log), (
            "死龙自动回合施放忆灵技（_summon_turn 首个合法行动）")
        assert state.actors["1407"].resources["newbud"] >= 0.0
        # 换技能硬闸（available_if）：140702 每次上场闩必为 0——政策驱动 full run 不再
        # 误放（死龙在场时骸爪顶替战技位，合法集只读过滤）；且骸爪真实上过场（非空转）
        cas_casts = [(aid, latch) for aid, latch in casts if aid in ("140701", "140702", "140709")]
        assert any(aid == "140709" for aid, _l in cas_casts), (
            f"死龙在场窗口政策战技位 = 骸爪：{cas_casts}")
        assert all(latch == 0.0 for aid, latch in cas_casts if aid == "140702"), (
            f"140702 只在死龙不在场时可放（硬闸）：{cas_casts}")


class TestSkillSwapGate:
    """换技能硬闸（140702↔140709 available_if 互斥）：合法集层分态断言."""

    @staticmethod
    def _legal_ids(eng):
        from hsr_nous.sim import legal_action_set
        cas = eng.state.actors["1407"]
        legal = legal_action_set(cas, eng.actions_by_actor["1407"], eng.state.skill_points)
        legal = eng._legal_with_state(cas, legal)
        legal = eng._legal_with_available_if(cas, legal)   # 与 _run_turn 决策点同漏斗
        return {a.action_id for a in legal}

    def test_gate_flips_with_netherwing_presence(self, compiled):
        eng = _make(compiled, initial_sp=5)
        ids = self._legal_ids(eng)
        assert "140702" in ids and "140709" not in ids, "死龙未召：战技位=幽蝶，骸爪被闸"
        _ult(eng)                                   # 死龙入场 → _nw_on_field 闩置 1
        ids = self._legal_ids(eng)
        assert "140709" in ids and "140702" not in ids, (
            "死龙在场：战技换骸爪——幽蝶出集、骸爪进集（政策/手动 choices 同源）")
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        ids = self._legal_ids(eng)
        assert "140702" in ids and "140709" not in ids, "死龙消失（闩落 0）：战技位换回幽蝶"


class TestInvertedTorch:
    """1407102 大行迹「倒置的火炬」速度半：HP≥50% 门控 spd_pct +40%（条件光环重估通道对轴）."""

    _WIPE_STAGE = {"stage": {"stage_id": "s_wipe", "enemies": [
        {"actor_id": "e1", "name": "脆皮壹", "hp": 200.0, "spd": 100, "atk": 1000,
         "max_toughness": 9999, "weakness": ["quantum"]},
        {"actor_id": "e2", "name": "脆皮贰", "hp": 200.0, "spd": 100, "atk": 1000,
         "max_toughness": 9999, "weakness": ["quantum"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

    _TANK_STAGE = {"stage": {"stage_id": "s_tank", "enemies": [
        {"actor_id": "e1", "name": "脆皮", "hp": 200.0, "spd": 100, "atk": 1000,
         "max_toughness": 9999, "weakness": ["quantum"]},
        {"actor_id": "e2", "name": "坦克", "hp": 1e9, "spd": 100, "atk": 1000,
         "max_toughness": 9999, "weakness": ["quantum"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

    def _wipe_engine(self, stage):
        eng = CombatEngine.from_compiled(
            compile_encounter(_build(), stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=10)
        eng.setup()
        _ult(eng)
        return eng

    def test_hp_gate_flip_and_scheduler_resync(self, compiled):
        from hsr_nous.sim.state import Modifier  # noqa: F401（对称导入——本类无新件，仅占位防回归）
        eng = _make(compiled)
        cas = eng.state.actors["1407"]
        handle = eng.scheduler.handle_of("1407")
        assert "CASTORICE_INVERTED_TORCH" in cas.modifiers, "进战即挂（门控非挂摘）"
        # 满血 ≥50%：spd = 95×1.4 = 133（spd_pct 白值口径）——调度器同步上路
        assert math.isclose(eng.pipeline.effective_stats(cas)["spd"], 95 * 1.4)
        assert math.isclose(eng.scheduler.spd_of(handle), 95 * 1.4)
        # HP 掉到 40%：面板懒求值翻回 95 + HP 事件推式重同步调度器
        cas.current_hp = 0.4 * eng.pipeline.effective_stats(cas)["hp"]
        eng.bus.emit("on_hp_decrease", {"amount": 1.0, "source": "e1", "reason": "hit",
                                        "target": "1407"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(cas)["spd"], 95.0), "条件翻转：+40% 翻回"
        assert math.isclose(eng.scheduler.spd_of(handle), 95.0), "调度器经 HP 事件重同步"
        assert "CASTORICE_INVERTED_TORCH" in cas.modifiers, "门控非挂摘——件仍在"
        # 奶回 90%：翻回成立即恢复
        cas.current_hp = 0.9 * eng.pipeline.effective_stats(cas)["hp"]
        eng.bus.emit("on_hp_increase", {"amount": 1.0, "source": "ally", "reason": "heal",
                                        "target": "1407"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(cas)["spd"], 95 * 1.4)
        assert math.isclose(eng.scheduler.spd_of(handle), 95 * 1.4)

    def test_netherwing_half_lethal_wipe(self):
        """死龙半①（致命全灭）：焰息击杀使场上无存活敌方 → 死龙速度+100%（1 回合）.

        on_kill 逐杀发射：AoE 逐目标顺序结算，最后一杀 enemies_alive()==0 方挂（致命判定
        通道 2026-09-09 收编——action_id 归属 hook 伤害继承触发事件）。
        """
        eng = self._wipe_engine(self._WIPE_STAGE)
        nw = _nw(eng)
        assert eng.pipeline.effective_stats(nw)["spd"] == 165.0
        _cast(eng, "1407_netherwing", "1140702")
        assert not eng.state.actors["e1"].alive and not eng.state.actors["e2"].alive, "焰息全灭"
        mod = nw.modifiers.get("NW_TORCH_SPD")
        assert mod is not None, "全灭 → 倒置的火炬·死龙挂上"
        assert mod.duration == 1 and mod.tick_anchor == "owner_turn_start", (
            "持续 1 回合——owner_turn_start 锚（授予在本回合结算中，end 锚会当回合末到期提速落空）")
        assert math.isclose(eng.pipeline.effective_stats(nw)["spd"], 165.0 * 2.0), (
            "死龙速度 +100%（spd_pct 白值口径，#3=1.0）")

    def test_netherwing_half_partial_kill_no_buff(self):
        """死龙半①反例：焰息只杀一部分（场上有存活敌方）→ 不挂."""
        eng = self._wipe_engine(self._TANK_STAGE)
        nw = _nw(eng)
        _cast(eng, "1407_netherwing", "1140702")
        assert not eng.state.actors["e1"].alive and eng.state.actors["e2"].alive, "部分击杀"
        assert "NW_TORCH_SPD" not in nw.modifiers, "非全灭不触发（官方'对场上所有敌方造成致命伤害'）"

    def test_netherwing_half_hp_lock_branch(self):
        """死龙半②（无法被继续削减生命值）：焰息打到锁血敌人 → on_hp_lock 钳制发射 → 同挂."""
        from hsr_nous.sim.state import Modifier
        stage = {"stage": {"stage_id": "s_lock", "enemies": [
            {"actor_id": "e1", "name": "锁血怪", "hp": 200.0, "spd": 100, "atk": 1000,
             "max_toughness": 9999, "weakness": ["quantum"]},
            {"actor_id": "e2", "name": "坦克", "hp": 1e9, "spd": 100, "atk": 1000,
             "max_toughness": 9999, "weakness": ["quantum"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
        eng = self._wipe_engine(stage)
        nw = _nw(eng)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        locks = []
        eng.bus.subscribe("on_hp_lock", lambda et, p, ctx: locks.append(p))
        _cast(eng, "1407_netherwing", "1140702")
        assert e1.alive and e1.current_hp == 1.0, "锁血钳 1 不死（非击杀——全灭支不触发）"
        assert locks and locks[0]["action_id"] == "1140702" and locks[0]["source"] == "1407_netherwing"
        assert "NW_TORCH_SPD" in nw.modifiers, "敌方无法被继续削减生命值 → 同挂速度件"
        assert math.isclose(eng.pipeline.effective_stats(nw)["spd"], 165.0 * 2.0)

    def test_netherwing_half_other_action_no_buff(self):
        """死龙半反例②：非焰息行动击杀（1140701 爪痕）不挂——官方焰息限定."""
        stage = {"stage": {"stage_id": "s_claw", "enemies": [
            {"actor_id": "e1", "name": "脆皮", "hp": 200.0, "spd": 100, "atk": 1000,
             "max_toughness": 9999, "weakness": ["quantum"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
        eng = self._wipe_engine(stage)
        nw = _nw(eng)
        _cast(eng, "1407_netherwing", "1140701")
        assert not eng.state.actors["e1"].alive, "爪痕击杀"
        assert "NW_TORCH_SPD" not in nw.modifiers, "爪痕击杀≠焰息致命——不挂（action_id 归属闸）"


def _compile_eidolon(n: int):
    b = _build()
    b["build"]["team"][0]["eidolon"] = n
    return compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _claw_total(n: int, enemy_hp_ratio: float) -> float:
    """140709 骸爪总伤（遐蝶半 action + 死龙半 hook）——E1 对照组公用."""
    eng = _make(_compile_eidolon(n))
    _ult(eng)
    eng.state.actors["e1"].current_hp = enemy_hp_ratio * 1e9
    dmg0 = eng.state.total_damage
    _cast(eng, "1407", "140709")
    return eng.state.total_damage - dmg0


class TestCastoriceEidolons:
    """遐蝶 E1-E6 星魂（member.eidolon 激活——数值/机制照 ranks_detail 官方文本）."""

    def test_e3_e5_skill_level_overrides(self):
        lv3 = next(a for a in _compile_eidolon(3).build_team if a.actor_id == "1407").skill_levels
        assert lv3["ultimate"] == 12 and lv3["basic"] == 7, "E3：终结技+2、普攻+1"
        lv5 = next(a for a in _compile_eidolon(5).build_team if a.actor_id == "1407").skill_levels
        assert lv5["skill"] == 12 and lv5["talent"] == 12, "E5：战技+2、天赋+2"

    def test_e1_low_hp_tiers_on_four_abilities(self):
        # 骸爪（遐蝶半 skill+闩 / 死龙半 follow_up）80% 档 ×1.2、50% 档 ×1.4——
        # E0/E1 双跑对照（expected 确定化，比值即"原伤害%"——结界压缩口径严格等值）
        assert math.isclose(_claw_total(1, 0.75) / _claw_total(0, 0.75), 1.2, rel_tol=1e-9), (
            "敌方 HP ≤80%：骸爪两半对其伤害为原伤害 120%（真伤追加 0.2×原伤害）")
        assert math.isclose(_claw_total(1, 0.4) / _claw_total(0, 0.4), 1.4, rel_tol=1e-9), (
            "敌方 HP ≤50%：140%")
        assert math.isclose(_claw_total(1, 0.9) / _claw_total(0, 0.9), 1.0, rel_tol=1e-9), (
            "敌方 HP >80%：不触发")
        # 普攻（basic）与死龙离场后的 140702（skill 但闩 0）不在四技集——低血也不触发
        eng = _make(_compile_eidolon(1))
        e1 = eng.state.actors["e1"]
        e1.current_hp = 0.4e9
        dmg0 = eng.state.total_damage
        _cast(eng, "1407", "140701")
        basic_dmg = eng.state.total_damage - dmg0
        eng0 = _make(_compile_eidolon(0))
        eng0.state.actors["e1"].current_hp = 0.4e9
        d0 = eng0.state.total_damage
        _cast(eng0, "1407", "140701")
        assert math.isclose(basic_dmg, eng0.state.total_damage - d0, rel_tol=1e-9), (
            "普攻非四技——低血不加伤（action_type 过滤）")

    def test_e2_ardent_will_and_enhanced_skill_newbud(self):
        eng = _make(_compile_eidolon(2))
        _ult(eng)
        cas = eng.state.actors["1407"]
        will = cas.modifiers["E2_ARDENT_WILL"]
        assert will.stacks == 2 and will.max_stack == 2, "召唤死龙 → 遐蝶获得 2 层【炽意】"
        assert math.isclose(cas.resources["newbud"], 0.0), "开大扣光新蕊"
        _cast(eng, "1407", "140709")
        assert math.isclose(cas.resources["newbud"], 10200.0), (
            "下一次施放强化战技 → 获得新蕊上限 30%（34000×0.3=10200）")
        assert "E2_NEWBUD_ARMED" not in cas.modifiers, "兑现后摘除武装（每次召唤 1 次）"

    def test_e4_incoming_heal_team_aura(self):
        eng = _make(_compile_eidolon(4))
        cas, ally = eng.state.actors["1407"], eng.state.actors["ally"]
        assert "E4_INCOMING_HEAL" in cas.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["incoming_heal"], 0.2), (
            "遐蝶在场：我方全体受治疗量 +20%（incoming_heal 受疗者池 team 光环）")
        _ult(eng)
        ally.current_hp = 100.0
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        assert math.isclose(ally.current_hp, 100.0 + (0.084 * CAS_HP + 1120) * 1.2,
                            rel_tol=1e-9), "1140706 全体治疗吃 E4 +20% 受疗"

    def test_e6_res_pen_and_three_extra_bounces(self):
        eng = _make(_compile_eidolon(6))
        _ult(eng)
        cas, nw = eng.state.actors["1407"], _nw(eng)
        # param() 随档实证：E6 含 E3（ult+2）→ 境界抗穿取 lv12 行 0.22（旧烘焙扁平 0.2）
        assert math.isclose(eng.pipeline.effective_stats(cas)["res_pen"], 0.42), (
            "境界 0.22（param(140703,4) lv12——E3 跳档随档）+ E6 0.2 双叠")
        assert math.isclose(eng.pipeline.effective_stats(nw)["res_pen"], 0.42), (
            "死龙侧：E6 忆灵侧件 0.2 + 境界 team 光环辐射 0.22（lv12 随档）")
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        assert math.isclose(e1.toughness, 9999.0 - 45.0), (
            "E6：晦翼弹射 +3 → 9 段逐段各削 5（基础 6 段 30 + 追加 3 段 15）")
        assert math.isclose(eng.pipeline.effective_stats(cas)["res_pen"], 0.2), (
            "境界解除后 E6 自带 0.2 常驻")
        seg_realm = 0.56 * CAS_HP * CRIT_EXP * DEF_RES * 1.42 * UNBROKEN * (1 + QDMG + 0.1)
        seg_after = 0.56 * CAS_HP * CRIT_EXP * DEF_RES * RES_TERR * UNBROKEN * (1 + QDMG + 0.1)
        assert math.isclose(hp0 - e1.current_hp, 6 * seg_realm + 3 * seg_after, rel_tol=1e-6), (
            "基础 6 段吃境界 lv12+E6 双叠 1.42；追加 3 段在境界解除后吃 E6 自带 1.2（同值顶替在案）")


class TestArdentWillOffset:
    """E2③ 炽意抵扣（before_drain waterfall 首实例，2026-09-10）：死龙焰息耗血被抵扣
    （modify_amount 0=全额免扣，无扣减不发 on_hp_decrease）+ 遐蝶行动提前 100%，1 层/发；
    层尽恢复 25% 耗血."""

    def test_offset_negates_drain_and_advances_castorice(self):
        eng = _make(_compile_eidolon(2))
        _ult(eng)                                   # 召唤死龙 → E2① 挂 2 层【炽意】
        cas = eng.state.actors["1407"]
        nw = _nw(eng)
        assert cas.modifiers["E2_ARDENT_WILL"].stacks == 2
        breath = next(a for a in eng.actions_by_actor["1407_netherwing"]
                      if a.action_id == "1140702")
        advances = []
        orig_advance = eng.scheduler.advance_action
        def spy(actor, pct):
            advances.append((actor.actor_id, pct))
            return orig_advance(actor, pct)
        eng.scheduler.advance_action = spy
        drains = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drains.append(p))
        hp0 = nw.current_hp
        eng.trigger_action(nw, breath, tag="test")
        assert math.isclose(nw.current_hp, hp0), (
            "第 1 发：1 层抵扣全额免扣（before_drain modify_amount 0——抵扣≠扣后回补）")
        assert not [d for d in drains if d["target"] == "1407_netherwing"], (
            "免扣即发：无 on_hp_decrease（新蕊耗血记账不吃抵扣段）")
        assert cas.modifiers["E2_ARDENT_WILL"].stacks == 1, "1 层/发"
        assert advances == [("1407", 1.0)], "遐蝶行动提前 100%（抵扣绑定同句效果；scheduler 槽=比例 1.0）"
        eng.trigger_action(nw, breath, tag="test")
        assert math.isclose(nw.current_hp, hp0), "第 2 发：余 1 层再抵"
        assert cas.modifiers["E2_ARDENT_WILL"].stacks == 0
        hp2 = nw.current_hp
        eng.trigger_action(nw, breath, tag="test")
        assert math.isclose(hp2 - nw.current_hp, 8500.0), (
            "层尽第 3 发：恢复 25% Max HP 耗血（1140702 #1）")
        assert advances == [("1407", 1.0), ("1407", 1.0)], "无层不再提前"

    def test_no_ardent_will_no_offset(self):
        """E0/E1 无炽意：before_drain 链空转——耗血语义逐比特同旧（回归钉）."""
        eng = _make(_compile_eidolon(1))
        _ult(eng)
        nw = _nw(eng)
        assert "E2_ARDENT_WILL" not in eng.state.actors["1407"].modifiers
        breath = next(a for a in eng.actions_by_actor["1407_netherwing"]
                      if a.action_id == "1140702")
        hp0 = nw.current_hp
        eng.trigger_action(nw, breath, tag="test")
        assert math.isclose(hp0 - nw.current_hp, 8500.0), "无层不抵扣：25% 耗血照旧"
