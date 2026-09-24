"""托帕&账账 1112 全机制模板端到端对轴（打标 staging 过堂修正版）：真模板 YAML → 编译
→ 召唤/负债证明/战技结算/天赋推进/Windfall 循环/秘技门控/星魂全链 → 手算全等.

过堂修正四件（打标稿实证 bug）：① A2 能量钩无 Windfall 门控（常态攻击误回 10）；
② 秘技能量钩无 _tech_armed 门控（每次账账攻击误回 60）；③ 战技 hook 目标 pool+take1
恒首敌（PoD 不在首敌时打错人）→ $event.target 精确；④ 战技基数白值烘焙 → $self.atk
托帕实时面板。另：账账基础削韧 0→20 回填（fandom，Windfall 段 30 待收）。

口径常数：托帕白值 atk 620.928（无行迹攻击节点）= 账账基数（官方"Topaz's ATK"）；
账账 spd 80（Talent #1 恒值）；假人 def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9；
暴击 0.05/0.5 → 期望暴击区 1.025。默认档全 lv10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

NUMBY_ATK = 620.928
DEF_RES, UNBROKEN = 0.5, 0.9
CRIT_EXP = 1 + 0.17 * 0.5             # 1.085（B-TR② 行迹暴击+0.12 回填后 0.05+0.12=0.17）
ZONES = DEF_RES * UNBROKEN * CRIT_EXP * 1.224   # 1.224=B-TR② 行迹火伤+22.4% 回填后增伤区
SKILL_DMG = NUMBY_ATK * 1.5 * ZONES * 1.5   # 战技 lv10 #1=1.5×账账 ATK ×1.5=PoD 易伤
                                            # （结算段官方「视为追加攻击」吃 scoped 承伤——
                                            #  B-TP① 死键→vulnerability 复活后正当收益）
NUMBY_DMG = NUMBY_ATK * 1.5 * ZONES   # 账账 lv10 #2=1.5（天赋表同值——无 PoD 场景口径）


def _build(*, eidolon: int = 0, pre_battle=None):
    member = {"character_template": "1112", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"build": {"team": [member,
        {"actor_id": "ally", "name": "追击手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 90, "hp": 4000, "max_energy": 100},
         "actions": [{"action_id": "ally_fu", "name": "追击", "action_type": "follow_up",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _topaz(eng):
    return eng.state.actors["1112"]


def _numby(eng):
    return eng.state.actors.get("1112_numby")


def _cast(eng, owner, aid):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


def _hit(eng, source, target, *, action_type, amount):
    eng.bus.emit("after_being_hit", {
        "amount": amount, "absorbed": 0.0, "damage_type": "fire", "source": source,
        "target": target, "is_critical": False, "action_type": action_type,
        "actor_type": "character", "hit_targets": [target], "seg_index": 0}, eng.state)


class TestTopazCompile:
    def test_resources_summon_actions(self, compiled):
        decls = set(compiled.resource_decls_by_actor["1112"])
        assert {"_tech_armed", "_wf_active", "_wf_hits", "_wf_cap"} <= decls
        sd = compiled.summon_defs["1112_numby"]
        assert sd.inheritance == "none" and math.isclose(sd.actor.stats.spd, 80.0), (
            "账账独立面板 + spd 80（Talent #1 恒值）")
        assert sd.control == "auto", "账账全自动（12_summon §12.6）"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1112"]}
        assert acts["111202"].skill_point_cost == 1 and acts["111202"].toughness_dmg == 20
        numby_acts = {a.action_id: a for a in compiled.actions_by_actor["1112_numby"]}
        assert numby_acts["111204"].toughness_dmg == 20, "账账基础削韧 20（fandom 回填）"
        assert numby_acts["111204"].action_type == "follow_up", "天赋类攻击归 follow_up（无 talent 键）"


class TestBattleStartAndPod:
    def test_numby_summoned_and_pod_auto_applied(self, compiled):
        eng = _make(compiled)
        assert _numby(eng) is not None, "开战未召唤账账"
        # 队友回合开始无 PoD → 自动补挂
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        holders = [a.actor.actor_id for a in eng.state.actors.values()
                   if "PROOF_OF_DEBT" in a.modifiers]
        assert len(holders) == 1 and holders[0].startswith("e"), "PoD 自动补挂唯一敌"


class TestSkillChain:
    def test_skill_applies_pod_and_numby_damage(self, compiled):
        """战技：目标挂 PoD（全局唯一）+ 账账火伤手算全等（$event.target 精确+实时面板）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        # e2 先挂旧标 → 战技指 e1：旧标清除、新标上 e1（全局唯一）
        eng._apply_modifier(e2, Modifier(
            modifier_id="PROOF_OF_DEBT", name="负债证明", modifier_type="debuff",
            duration=0, dispellable=False))
        hp1 = e1.current_hp
        _cast(eng, "1112", "111202")
        assert "PROOF_OF_DEBT" not in e2.modifiers, "旧标未清（全局唯一）"
        assert "PROOF_OF_DEBT" in e1.modifiers, "新标未挂战技目标"
        assert math.isclose(hp1 - e1.current_hp, SKILL_DMG, rel_tol=1e-9), (
            "账账火伤 = 1.5×托帕实时面板×乘区（B-TR② 行迹火伤/暴击回填+B-TP① 易伤复活）")
        pod = e1.modifiers["PROOF_OF_DEBT"]
        assert math.isclose(pod.stat_effects["vulnerability"], 0.5), (
            "PoD 易伤 lv10=0.5（B-TP① 死键 follow_up_dmg_taken→vulnerability 换绑）")
        assert pod.hit_condition_expr is not None, (
            "易伤限定追加攻击承伤（hit_condition_expr——1218/1203 先例）")


class TestTalentAdvance:
    def test_follow_up_hit_advances_numby_50(self, compiled):
        """PoD 敌受我方追加攻击 → 账账行动提前 50%（托帕 basic 经 A6 同值不同源）."""
        eng = _make(compiled)
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        pod_holder = next(a.actor.actor_id for a in eng.state.actors.values()
                          if "PROOF_OF_DEBT" in a.modifiers)
        rem0 = eng.scheduler._remaining[eng.scheduler._handles["1112_numby"]]
        _hit(eng, "ally", pod_holder, action_type="follow_up", amount=1000.0)
        rem1 = eng.scheduler._remaining[eng.scheduler._handles["1112_numby"]]
        assert math.isclose(rem0 - rem1, 10000 * 0.5, rel_tol=1e-9), "追加攻击命中推账账 50%"
        # 账账自身命中不触发（官方"账账自身回合内不触发"）
        _hit(eng, "1112_numby", pod_holder, action_type="follow_up", amount=1000.0)
        rem2 = eng.scheduler._remaining[eng.scheduler._handles["1112_numby"]]
        assert math.isclose(rem1, rem2), "账账自身攻击不触发推进"


class TestWindfallCycle:
    def test_windfall_stat_count_energy_exit(self, compiled):
        """Windfall 循环：开启（增伤/暴伤件+计数清零）→ 账账攻击计数+A2 回能 → 达 2 次退出."""
        eng = _make(compiled)
        tp = _topaz(eng)
        tp.current_energy = 130.0
        e0 = tp.current_energy
        ult = next(a for a in eng.actions_by_actor["1112"] if a.action_id == "111203")
        assert eng._fire_ultimate(tp, ult) is True
        nb = _numby(eng)
        wf = nb.modifiers["WINDFALL_BONANZA"]
        assert math.isclose(wf.stat_effects["all_dmg"], 1.5) and \
            math.isclose(wf.stat_effects["crit_dmg"], 0.25), "lv10 #1/#2"
        assert math.isclose(tp.resources["_wf_active"], 1.0)
        assert math.isclose(tp.resources["_wf_cap"], 2.0), "#4=2（E0 无 E6_MARK）"
        assert math.isclose(tp.current_energy, e0 - 130.0 + 5.0), "开大耗 130 返还 5"
        # 常态（非 Windfall）A2 不回能——门控补正实证：先开一局不带 Windfall 的
        eng2 = _make(compiled)
        tp2 = _topaz(eng2)
        e0_2 = tp2.current_energy
        _cast(eng2, "1112_numby", "111204")
        assert math.isclose(tp2.current_energy, e0_2), "非 Windfall 账账攻击 A2 不回 10"
        # Windfall 中：计数/回能/达阈退出
        for i in (1, 2):
            e_before = tp.current_energy
            _cast(eng, "1112_numby", "111204")
            assert math.isclose(tp.resources["_wf_hits"], float(i))
            assert math.isclose(tp.current_energy, e_before + 10.0), "Windfall 中 A2 每次 +10"
        assert math.isclose(tp.resources["_wf_active"], 0.0), "达 #4=2 次退出 Windfall"
        assert "WINDFALL_BONANZA" not in nb.modifiers, "退出后状态件摘除"

    def test_e6_cap_three_and_res_pen(self):
        """E6：阈值 2→3 + Windfall 期间账账火抗穿 10%（随退出链同摘）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        tp = _topaz(eng)
        tp.current_energy = 130.0
        ult = next(a for a in eng.actions_by_actor["1112"] if a.action_id == "111203")
        eng._fire_ultimate(tp, ult)
        assert math.isclose(tp.resources["_wf_cap"], 3.0), "E6：#4+1=3"
        assert "E6_WF_RES_PEN" in _numby(eng).modifiers
        for _ in range(2):
            _cast(eng, "1112_numby", "111204")
        assert math.isclose(tp.resources["_wf_active"], 1.0), "E6 下 2 次不退出"
        _cast(eng, "1112_numby", "111204")
        assert math.isclose(tp.resources["_wf_active"], 0.0), "E6 下 3 次退出"
        assert "E6_WF_RES_PEN" not in _numby(eng).modifiers, "抗穿件随退出同摘"


class TestTechniqueLatch:
    def test_tech_armed_first_attack_only(self):
        """秘技：账账首次攻击回 60（门控补正实证——第二次不回）."""
        b = _build(pre_battle=[{"actor_id": "1112", "technique": "111207"}])
        compiled = compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        tp = _topaz(eng)
        assert math.isclose(tp.resources["_tech_armed"], 1.0), "秘技进战武装"
        e0 = tp.current_energy
        _cast(eng, "1112_numby", "111204")
        assert math.isclose(tp.current_energy, e0 + 60.0), "首次攻击 +60（#1）"
        assert math.isclose(tp.resources["_tech_armed"], 0.0), "闩已清"
        _cast(eng, "1112_numby", "111204")
        assert math.isclose(tp.current_energy, e0 + 60.0), "第二次不再回（门控实证）"


class TestEidolon1And4:
    def test_e1_debtor_stacks_cap2(self):
        """E1：PoD 敌受追击 → Debtor 叠层（上限 2）——本件=纯层账本（死键已摘）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        holder = next(a for a in eng.state.actors.values() if "PROOF_OF_DEBT" in a.modifiers)
        for expect in (1.0, 2.0, 2.0):
            _hit(eng, "ally", holder.actor.actor_id, action_type="follow_up", amount=1000.0)
            assert math.isclose(holder.modifiers["DEBTOR"].stacks, expect)
        assert not holder.modifiers["DEBTOR"].stat_effects, (
            "Debtor 本件=纯层账本（follow_up_crit_dmg 死键已摘——B-TP②，效果走攻击侧 "
            "scoped 件，见 test_e1_debtor_crit_dmg_effect 效果钉）")

    def test_e1_debtor_crit_dmg_effect(self):
        """E1 暴伤效果钉（B-TP② 收编实证）：队友追加攻击按 Debtor 层数 +25%/层 暴伤——
        攻击侧 scoped crit_dmg 通道（hit_condition follow_up + hit_stat_exprs 层数现值），
        0/1/2 层三点手算全等；托帕/队友/账账全员各挂."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        for aid in ("1112", "ally", "1112_numby"):
            assert "E1_DEBTOR_CD" in eng.state.actors[aid].modifiers, (
                f"{aid} 未挂 scoped 暴伤件（全队族各挂——账账经 allies 池，"
                f"模板 summon 钩先于星魂钩订阅 on_battle_start）")
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        holder = next(a for a in eng.state.actors.values() if "PROOF_OF_DEBT" in a.modifiers)
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
            holder if holder in candidates else (candidates[0] if candidates else None))
        a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_fu")
        base = 2000 * 0.5 * 0.9 * 1.5   # ATK×防御区×未击破×PoD 易伤 0.5（追击承伤 scoped，B-TP①）
        for stacks in (0, 1, 2):
            hp0 = holder.current_hp
            eng._execute_action(eng.state.actors["ally"], a)
            crit_zone = 1 + 0.05 * (0.5 + 0.25 * stacks)   # 期望暴击区：暴伤 0.5+0.25×层数
            assert math.isclose(hp0 - holder.current_hp, base * crit_zone, rel_tol=1e-9), (
                f"Debtor {stacks} 层：受追击暴伤 0.5+0.25×{stacks}（hit_stat_exprs 现值，"
                f"本次命中后 after_being_hit 再叠 1 层）")
        assert math.isclose(holder.modifiers["DEBTOR"].stacks, 2.0), "层数钳顶 2"

    def test_e4_numby_turn_advances_topaz(self):
        """E4：账账回合开始 → 托帕行动提前 20%."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        rem0 = eng.scheduler._remaining[eng.scheduler._handles["1112"]]
        eng.bus.emit("on_turn_start", {"actor": "1112_numby"}, eng.state)
        rem1 = eng.scheduler._remaining[eng.scheduler._handles["1112"]]
        assert math.isclose(rem0 - rem1, 10000 * 0.2, rel_tol=1e-9)
