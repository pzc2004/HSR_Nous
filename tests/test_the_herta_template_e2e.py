"""大黑塔 1401 模板端到端对轴（验收型批·单轨）：真模板 YAML → 编译 →
天赋【解读】/谜底/灵感/行迹三件套/强化战技/星魂全链 → 手算全等.

口径常数：大黑塔 atk 679.14（白值）、crit_rate 0.05、spd 99（行迹 flat +5）、max_energy 220；
行迹小节点 atk_pct 0.18 / dmg_ice 0.224（trace_stat_effects）。
1401102（双智识）：全队 crit_dmg +0.8 → 0.5+0.8=1.3 → 期望暴击区 = 1+0.05×1.3 = 1.065。
假人 def 1000 → 防御区 0.5；冰弱点匹配 → 抗性区 1.0（E6 穿透 0.2 → 1.2）；未击破 0.9；
冰伤区 1.224。普攻 lv6=1.0 / 战技 lv10=0.7 / 终结技 lv10=2.0 / 强化战技 lv10=0.8+收尾 0.4。
波 1（on_battle_start 双轨）：e1=1+25=26 层、 e2=1 层【解读】（expected 模式 random 取池首），
谜底 = 1 + (enemies_alive 2 + 24) = 27。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK_W = 679.1400000000001          # 白值（管线实值）
ATK0 = ATK_W * 1.18                # 行迹 atk_pct 0.18 后
CRIT_Z = 1 + 0.05 * 1.3            # 期望暴击区（1401102 双智识 crit_dmg 1.3）
ZONE = 0.5 * 1.224 * CRIT_Z * 0.9  # 防御 0.5 × 冰伤 1.224 × 期望暴击 × 未击破 0.9（抗性 1.0）


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1401", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True, "path": "erudition",
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "战技", "action_type": "skill",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_cost": 1},
                     {"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 5, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1401", "technique": "140107"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _herta(eng):
    return eng.state.actors["1401"]


def _interp(eng, aid):
    m = eng.state.actors[aid].modifiers.get("INTERPRETATION")
    return m.stacks if m is not None else 0.0


def _answer(eng):
    m = _herta(eng).modifiers.get("ANSWER")
    return m.stacks if m is not None else 0.0


def _inspiration(eng):
    m = _herta(eng).modifiers.get("INSPIRATION")
    return m.stacks if m is not None else 0.0


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _hp(eng, aid):
    return eng.state.actors[aid].current_hp


def _cast(eng, owner, aid, *, target="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _herta(eng)
    st.current_energy = 220.0
    ult = next(a for a in eng.actions_by_actor["1401"] if a.action_id == "140103")
    assert eng._fire_ultimate(st, ult) is True


class TestTheHertaCompile:
    def test_actions_and_trace_stats(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1401"]}
        assert acts == {"140101", "140102", "140103", "140109"}
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_herta(eng))
        assert math.isclose(eff["atk"], ATK0, rel_tol=1e-9), "行迹 atk_pct 0.18（勘正①）"
        assert math.isclose(eff["spd"], 99 + 5, rel_tol=1e-9), "行迹 SpeedDelta flat +5"
        assert math.isclose(eff["dmg_bonus"]["ice"], 0.224, rel_tol=1e-9), "行迹冰伤 0.224"


class TestBattleStartDualTrack:
    def test_wave1_interpretation_and_answer(self, compiled):
        """波 1 双轨（勘正⑪）：e1=1+25=26（expected 取池首）、e2=1；谜底=2 敌+25=27."""
        eng = _make(compiled)
        assert math.isclose(_interp(eng, "e1"), 26.0)
        assert math.isclose(_interp(eng, "e2"), 1.0)
        assert math.isclose(_answer(eng), 27.0), "谜底配对 = 命中 2 + 波次 25（勘正⑤）"

    def test_trace_critdmg_aura(self, compiled):
        """1401102 上半：双智识 → 全队 crit_dmg +0.8（自身与辅手同吃）."""
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_herta(eng))["crit_dmg"],
                            1.3, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"],
                            1.3, rel_tol=1e-9)


class TestBasic:
    def test_basic_damage_stacks_energy(self, compiled):
        """普攻 lv6=1.0：单段伤害 + 命中/③/④ 叠层链 + 固定回能 9（floor 3×3）."""
        eng = _make(compiled)
        st = _herta(eng)
        hp0 = _hp(eng, "e1")
        sp0 = eng.state.skill_points
        _cast(eng, "1401", "140101")
        exp = ATK0 * 1.0 * ZONE
        assert math.isclose(hp0 - _hp(eng, "e1"), exp, rel_tol=1e-9), (
            f"普攻期望 {exp:.3f}")
        # 链：e1 = 26 +1(命中 1401101①) +1(③) +2(④ 智识) = 30；e2 不动
        assert math.isclose(_interp(eng, "e1"), 30.0)
        assert math.isclose(_interp(eng, "e2"), 1.0)
        assert math.isclose(_answer(eng), 27 + 1 + 1 + 2, abs_tol=1e-9)
        assert math.isclose(st.current_energy, 20 + 9, abs_tol=1e-9), (
            "行动回 20 + 1401101② 固定 9（err_exempt——勘正③）")
        assert math.isclose(eng.state.skill_points, sp0 + 1)
        assert math.isclose(eng.state.actors["e1"].toughness, 100 - 10)


class TestSkill:
    def test_skill_blast_damage_and_stacks(self, compiled):
        """战技 lv10=0.7：主/邻同倍率（scaling_blast）+ 主目标施加 1 层（勘正⑧）."""
        eng = _make(compiled)
        st = _herta(eng)
        hp1, hp2 = _hp(eng, "e1"), _hp(eng, "e2")
        _cast(eng, "1401", "140102")
        exp = ATK0 * 0.7 * ZONE
        assert math.isclose(hp1 - _hp(eng, "e1"), exp, rel_tol=1e-9), "主目标 0.7"
        assert math.isclose(hp2 - _hp(eng, "e2"), exp, rel_tol=1e-9), "相邻同倍率 0.7"
        # e1 = 26 +1(命中) +1(主目标施加) +1(③) +2(④) = 31；e2 = 1 +1(相邻命中) = 2
        assert math.isclose(_interp(eng, "e1"), 31.0)
        assert math.isclose(_interp(eng, "e2"), 2.0)
        assert math.isclose(_answer(eng), 27 + 2 + 1 + 1 + 2, abs_tol=1e-9)
        assert math.isclose(st.current_energy, 30 + 9, abs_tol=1e-9)
        assert math.isclose(eng.state.actors["e1"].toughness, 100 - 5)
        assert math.isclose(eng.state.actors["e2"].toughness, 100 - 5), (
            "相邻逐击同 5（toughness_dmg_blast 显式覆盖——勘正⑨）")


class TestUlt:
    def test_ult_full_chain(self, compiled):
        """终结技 lv10：ATK+80%（自身伤害同吃）→ 2.0 全体 + 谜底段 0.29（=27+2 命中——
        判读点勘正⑬）+ 灵感 1 + 立即行动（remaining=0）+ 固定回能 9（aoe floor）+ 回 5."""
        eng = _make(compiled)
        st = _herta(eng)
        hp1, hp2 = _hp(eng, "e1"), _hp(eng, "e2")
        _ult(eng)
        atk_ult = ATK_W * (1.18 + 0.8)          # HERTA_ULT_ATK param(140103,4)=0.8 先挂后伤
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], atk_ult, rel_tol=1e-9)
        assert math.isclose(st.modifiers["HERTA_ULT_ATK"].duration, 3)
        exp_each = atk_ult * (2.0 + 0.01 * 29) * ZONE
        assert math.isclose(hp1 - _hp(eng, "e1"), exp_each, rel_tol=1e-9), (
            "主段 2.0 + 谜底段 0.29（判读点=27 开战 +2 本次命中——③④ 不计，勘正⑬）")
        assert math.isclose(hp2 - _hp(eng, "e2"), exp_each, rel_tol=1e-9)
        assert math.isclose(_inspiration(eng), 1.0), "施放后 +1 灵感"
        assert math.isclose(_remaining(eng, "1401"), 0.0), "立即行动（immediate_action 勘正⑩）"
        assert math.isclose(st.current_energy, 5 + 9, abs_tol=1e-9), (
            "终结技回 5 + 固定回能 aoe 档 3×clamp(2,3,5)=9")
        assert math.isclose(eng.state.actors["e1"].toughness, 100 - 20)
        # e1 = 26 +1(命中) +1(③) +2(④) = 30；谜底 = 27 +2(命中) +1 +2 = 32
        assert math.isclose(_interp(eng, "e1"), 30.0)
        assert math.isclose(_answer(eng), 32.0)

    def test_available_if_swap(self, compiled):
        """换技能互斥（03_actor §3.8.1）：无灵感→140102 可用/140109 锁；持灵感→反转."""
        eng = _make(compiled)
        st = _herta(eng)
        a102 = next(a for a in eng.actions_by_actor["1401"] if a.action_id == "140102")
        a109 = next(a for a in eng.actions_by_actor["1401"] if a.action_id == "140109")
        assert eng._available_if_ok(st, a102) and not eng._available_if_ok(st, a109)
        _ult(eng)
        assert not eng._available_if_ok(st, a102) and eng._available_if_ok(st, a109)


class TestEnhancedSkill:
    def test_enhanced_full_chain(self, compiled):
        """强化战技 lv10：消耗 1 灵感 + 主/邻 0.8 + 收尾全体 0.4（削韧 5）+ 主目标
        解读重置 1（勘正⑦）→ ③④ 见重置后值（e2 反超成最高）."""
        eng = _make(compiled)
        st = _herta(eng)
        _ult(eng)                      # 灵感 1、ATK buff 在场、谜底 32、e1=30/e2=2
        hp1, hp2 = _hp(eng, "e1"), _hp(eng, "e2")
        atk_ult = ATK_W * 1.98
        _cast(eng, "1401", "140109")
        exp_main = atk_ult * (0.8 + 0.4) * ZONE     # 主段 0.8 + 收尾段 0.4 同命中
        exp_adj = atk_ult * (0.8 + 0.4) * ZONE      # 相邻同 0.8（scaling_blast）+ 收尾
        assert math.isclose(hp1 - _hp(eng, "e1"), exp_main, rel_tol=1e-9)
        assert math.isclose(hp2 - _hp(eng, "e2"), exp_adj, rel_tol=1e-9)
        assert math.isclose(_inspiration(eng), 0.0), "消耗 1 灵感"
        assert math.isclose(_interp(eng, "e1"), 1.0), "主目标重置为 1（天赋 140104——勘正⑦）"
        # e2 = 2 +1(命中) = 3 > e1=1 → ③④ 选 e2：3 +1 +2 = 6
        assert math.isclose(_interp(eng, "e2"), 6.0)
        assert math.isclose(_answer(eng), 32 + 2 + 1 + 1 + 2, abs_tol=1e-9)
        assert math.isclose(st.current_energy, 14 + 30 + 9, abs_tol=1e-9)
        # 削韧：主段 5 + 收尾 5（hook deal_damage 同漏斗——勘正⑨）
        assert math.isclose(eng.state.actors["e1"].toughness, 80 - 5 - 5)
        assert math.isclose(eng.state.actors["e2"].toughness, 80 - 5 - 5)
        a102 = next(a for a in eng.actions_by_actor["1401"] if a.action_id == "140102")
        assert eng._available_if_ok(st, a102), "灵感耗尽 → 普通战技回槽"


class TestEidolons:
    def test_e1_reset_to_15(self):
        """E1②：重置改置 15 层（基础钩置 1 + 注册序后钩 +14——§23.11 注册序）."""
        eng = _make(_compiled(eidolon=1))
        _ult(eng)
        _cast(eng, "1401", "140109")
        assert math.isclose(_interp(eng, "e1"), 15.0)

    def test_e2_inspiration_and_advance(self):
        """E2：入场 +1 灵感；终结技后再 +1（合计 3）；强化战技后行动提前 35%（-3500）."""
        eng = _make(_compiled(eidolon=2))
        assert math.isclose(_inspiration(eng), 1.0), "入场 +1 灵感（E2①）"
        _ult(eng)
        assert math.isclose(_inspiration(eng), 3.0), "1 入场 +1 终结技 +1 E2 追加"
        before = _remaining(eng, "1401")
        # 立即行动已置 0 → 先手动复位一条整距再验拉条（remaining≤0 拉条无效口径）
        eng.scheduler._remaining[eng.scheduler._handles["1401"]] = 10000.0
        before = _remaining(eng, "1401")
        _cast(eng, "1401", "140109")
        assert math.isclose(before - _remaining(eng, "1401"), 3500.0, rel_tol=1e-9), (
            "E2③ 提前 35%（10000×0.35）")

    def test_e3_skill_lv12(self):
        """E3 战技+2：140102 实取 lv12 档 0.77（联动勘——幻视族谱 #18）."""
        eng = _make(_compiled(eidolon=3))
        hp1 = _hp(eng, "e1")
        _cast(eng, "1401", "140102")
        exp = ATK0 * 0.77 * ZONE
        assert math.isclose(hp1 - _hp(eng, "e1"), exp, rel_tol=1e-9), "lv12=0.77"

    def test_e4_erudition_spd(self):
        """E4：智识角色速度 +12%（spd_pct 白值口径；自身 99×1.12+5，辅手 90×1.12）."""
        eng = _make(_compiled(eidolon=4))
        assert math.isclose(eng.pipeline.effective_stats(_herta(eng))["spd"],
                            99 * 1.12 + 5, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["spd"],
                            90 * 1.12, rel_tol=1e-9)

    def test_e5_ult_lv12_and_basic_lv7(self):
        """E5 终结技+2：lv12 档倍率 2.2 + ATK buff 0.88；普攻+1：lv7 档 1.1."""
        eng = _make(_compiled(eidolon=5))
        hp1 = _hp(eng, "e1")
        _ult(eng)
        atk_ult = ATK_W * (1.18 + 0.88)
        exp_each = atk_ult * (2.2 + 0.01 * 29) * ZONE
        assert math.isclose(hp1 - _hp(eng, "e1"), exp_each, rel_tol=1e-9), (
            "lv12：主段 2.2 + 谜底段 0.29（ATK buff param(140103,4)=0.88 随档）")
        hp1 = _hp(eng, "e1")
        _cast(eng, "1401", "140101")
        exp_basic = ATK_W * (1.18 + 0.88) * 1.1 * ZONE
        assert math.isclose(hp1 - _hp(eng, "e1"), exp_basic, rel_tol=1e-9), (
            "普攻 lv7=第 7 行=1.1（lv6=1.0 起 +0.1/档——15 档表行序铁律）")

    def test_e6_res_pen_and_tiered_segment(self):
        """E6：冰抗穿 +20%（抗性区 1.2）+ 终结技倍率段（2 敌 → +250%）——均随 E5 lv12 档."""
        eng = _make(_compiled(eidolon=6))
        st = _herta(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9)
        hp1 = _hp(eng, "e1")
        _ult(eng)
        atk_ult = ATK_W * (1.18 + 0.88)
        exp_each = atk_ult * (2.2 + 0.01 * 29 + 2.5) * ZONE * 1.2
        assert math.isclose(hp1 - _hp(eng, "e1"), exp_each, rel_tol=1e-9), (
            "lv12 主段 2.2 + 谜底 0.29 + E6 段 2.5（2 敌档）× 抗性区 1.2")


class TestAllyAttackTriggers:
    def test_ally_attack_stacks_and_energy(self, compiled):
        """1401101/1401102 对队友攻击同口径响应（含大黑塔本人条件勘正③的对面：
        非 1401 我方攻击同样叠层+回能；辅手智识 → ①+② 合计 3 层）."""
        eng = _make(compiled)
        st = _herta(eng)
        _cast(eng, "ally", "ally_skill")
        # e1 = 26 +1(命中) +1(③) +2(④ 辅手智识) = 30；谜底 = 27 +1 +1 +2 = 31
        assert math.isclose(_interp(eng, "e1"), 30.0)
        assert math.isclose(_answer(eng), 31.0)
        assert math.isclose(st.current_energy, 9.0), "固定回能 9（err_exempt 不乘 ERR）"


class TestTechnique:
    def test_pre_battle_atk_buff(self):
        """秘技：进战 ATK +60% 持续 2 回合（战前装填——与行迹 0.18 同池加算）."""
        eng = _make(_compiled(pre_battle=True))
        st = _herta(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            ATK_W * (1.18 + 0.6), rel_tol=1e-9)
        assert math.isclose(st.modifiers["HERTA_TECH_ATK"].duration, 2)
