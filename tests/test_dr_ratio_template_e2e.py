"""真理医生 1305 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 天赋追击/
智者的短见/归纳/演绎/秘技/星魂 E1-E6 全链 → 手算全等.

口径常数：真理医生白值 atk 776.16、def 460.845、spd 103；行迹 atk_pct 28%、
def_pct 12.5%、暴击率 +12%（面板 crit 0.17/0.5——基础期望暴击区 1.085）。
有效面板 atk = 776.16×1.28 = 993.4848。假人 def 1000 → 防御区 0.5；虚数弱点
→ 抗性区 1.0；未击破 0.9（9999 韧性永不击破）。
归纳每层 crit +2.5%/暴伤 +5%（stat_exprs 动态读层）：
  1 层 = 0.195/0.55 → 期望暴击区 1.10725；2 层 = 0.22/0.60 → 1.132；
  4 层（E1 开战）= 0.27/0.70 → 1.189；5 层 = 0.295/0.75 → 1.22125；
  10 层（E1 上限）= 0.42/1.00 → 1.42。
档位（默认 basic 6 / skill 10 / ult 10 / talent 10；E3 终结技+2=lv12、普攻+1=lv7；
E5 战技/天赋+2=lv12）：战技 lv10 1.5（lv12 1.65）、追击 lv10 2.7（lv12 2.97）、
终结技 lv10 2.4（lv12 2.592）、普攻 lv6 1.0（lv7 1.1）、E2 附加段 0.2 固定。
愚行触发域 = 队友（排除自身——CN「队友」/EN teammates 双侧一致）；
层数判定 stacks()（has_modifier 存在性死钩已勘正）；E6 次数 2+1=3
（max_stack 3 结构上限，E0 只减不增天然 ≤2）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 776.16 * 1.28          # 有效攻击 993.4848（白值 × (1+行迹 28%)）
DEF_EFF = 460.845 * 1.125    # 有效防御 518.450625
Z0 = 0.5 * 0.9               # 防御区 × 未击破（抗性区 1.0 略写）
C0 = 1 + 0.17 * 0.5          # 1.085（0 层归纳）
C1 = 1 + 0.195 * 0.55        # 1.10725（1 层）
C2 = 1 + 0.22 * 0.60         # 1.132（2 层）
C4 = 1 + 0.27 * 0.70         # 1.189（4 层——E1 开战）
C5 = 1 + 0.295 * 0.75        # 1.22125（5 层）


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1305", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "战技", "action_type": "skill",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "skill_point_cost": 1},
                     {"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1305", "technique": "130507"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
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


def _dr(eng):
    return eng.state.actors["1305"]


def _dmg(eng):
    return eng.state.damage_by_actor["1305"]


def _exec(eng, owner, aid, target=None):
    """只执行行动（不发 on_action——伤害/扣点/回能立结，hooks 待 _emit_action）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    return a, tgt


def _emit_action(eng, owner, a, tgt):
    st = eng.state.actors[owner]
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": a.action_id,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _cast(eng, owner, aid, *, target=None):
    a, tgt = _exec(eng, owner, aid, target)
    _emit_action(eng, owner, a, tgt)


def _ult(eng, target=None):
    st = _dr(eng)
    st.current_energy = 140.0
    ult = next(a for a in eng.actions_by_actor["1305"] if a.action_id == "130503")
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


class TestDrRatioCompile:
    def test_actions_and_panel(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1305"]}
        assert acts == {"130501", "130502", "130503"}
        eng = _make(compiled)
        se = eng.pipeline.effective_stats(_dr(eng))
        assert math.isclose(se["atk"], ATK, rel_tol=1e-9), "776.16×1.28（行迹 atk_pct 28%）"
        assert math.isclose(se["def_"], DEF_EFF, rel_tol=1e-9), "460.845×1.125（行迹 def_pct 12.5%）"
        assert math.isclose(se["crit_rate"], 0.17, rel_tol=1e-9), "管线 0.05+行迹暴击 0.12（勘正①）"
        assert math.isclose(se["crit_dmg"], 0.5, rel_tol=1e-9)
        assert math.isclose(se["spd"], 103, rel_tol=1e-9)


class TestBasic:
    def test_basic_lv6(self, compiled):
        """普攻 lv6 = 1.0×ATK：993.4848×0.5×0.9×1.085 = 485.0689536；回能 20、产 1 点."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp0, sp0 = e1.current_hp, eng.state.skill_points
        _cast(eng, "1305", "130501")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.0 * Z0 * C0, rel_tol=1e-9)
        assert math.isclose(_dr(eng).current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, sp0 + 1), "普攻产 1 点"
        assert "SUMMATION" not in _dr(eng).modifiers, "普攻不挂归纳（官方「使用战技时」）"


class TestSkillTalentTraces:
    def test_first_skill_chain(self, compiled):
        """首战技全链：战技伤害（无归纳）→ 演绎 debuff → 归纳 1 层 → 追击（吃 1 层）→ 回能."""
        eng = _make(compiled)
        st, e1 = _dr(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        a, tgt = _exec(eng, "1305", "130502")
        # 战技伤害：挂点前面板（0 层）——993.4848×1.5×0.5×0.9×1.085 = 727.6034304
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.5 * Z0 * C0, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0), "战技耗 1 点"
        assert math.isclose(st.current_energy, 30.0)
        assert "INFERENCE_EFFECT_RES" not in e1.modifiers, "on_action 未发——演绎未挂"
        hp1 = e1.current_hp
        _emit_action(eng, "1305", a, tgt)
        assert "INFERENCE_EFFECT_RES" in e1.modifiers, "演绎：效果抵抗 -10%×2 回合"
        assert math.isclose(eng.pipeline.effective_stats(e1)["effect_res"], -0.1, rel_tol=1e-9)
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 1.0)
        se = eng.pipeline.effective_stats(st)
        assert math.isclose(se["crit_rate"], 0.195, rel_tol=1e-9), "1 层：0.17+0.025"
        assert math.isclose(se["crit_dmg"], 0.55, rel_tol=1e-9), "1 层：0.5+0.05"
        # 追击 lv10 = 2.7×ATK（1 层区 1.10725）：993.4848×2.7×0.5×0.9×1.10725 = 1336.543794432
        assert math.isclose(hp1 - e1.current_hp, ATK * 2.7 * Z0 * C1, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 35.0), "战技 30 + 追击 5（tbgd+mys 双源）"

    def test_second_skill_stacks(self, compiled):
        """二战技：伤害吃存量 1 层；归纳 → 2 层后追击吃 2 层区 1.132."""
        eng = _make(compiled)
        st, e1 = _dr(eng), eng.state.actors["e1"]
        _cast(eng, "1305", "130502")
        hp0 = e1.current_hp
        a, tgt = _exec(eng, "1305", "130502")
        # 993.4848×1.5×0.5×0.9×1.10725 = 742.52433024
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.5 * Z0 * C1, rel_tol=1e-9)
        hp1 = e1.current_hp
        _emit_action(eng, "1305", a, tgt)
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 2.0)
        # 993.4848×2.7×0.5×0.9×1.132 = 1366.419124224
        assert math.isclose(hp1 - e1.current_hp, ATK * 2.7 * Z0 * C2, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 70.0)

    def test_summation_cap6(self, compiled):
        """归纳上限 6（E0）：7 次战技仍 6 层."""
        eng = _make(compiled)
        eng.state.skill_points = 99.0
        st = _dr(eng)
        for _ in range(7):
            _cast(eng, "1305", "130502")
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 6.0)
        se = eng.pipeline.effective_stats(st)
        assert math.isclose(se["crit_rate"], 0.17 + 0.025 * 6, rel_tol=1e-9)
        assert math.isclose(se["crit_dmg"], 0.5 + 0.05 * 6, rel_tol=1e-9)


class TestUltimateFolly:
    def test_folly_teammate_chain(self, compiled):
        """终结技（2 层归纳面板）→ 愚行 2 层 → 队友攻击逐次消耗；0 层后不再触发
        （stacks() 判定——has_modifier 存在性死钩已勘正）；自身攻击不触发（队友域）."""
        eng = _make(compiled)
        eng.state.skill_points = 99.0
        st, e1 = _dr(eng), eng.state.actors["e1"]
        _cast(eng, "1305", "130502")
        _cast(eng, "1305", "130502")   # 2 层归纳
        hp0 = e1.current_hp
        _ult(eng)
        # 终结技 lv10 = 2.4×ATK（2 层区 1.132）：993.4848×2.4×0.5×0.9×1.132 = 1214.594777088
        assert math.isclose(hp0 - e1.current_hp, ATK * 2.4 * Z0 * C2, rel_tol=1e-9)
        assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, 2.0)
        assert math.isclose(st.current_energy, 5.0), "140 耗尽 + 施放返还 5"
        d0 = _dmg(eng)
        _exec(eng, "ally", "ally_basic")   # 队友命中 → 追击 + 扣 1 层（on_hp_decrease 引擎自发）
        assert math.isclose(_dmg(eng) - d0, ATK * 2.7 * Z0 * C2, rel_tol=1e-9)
        assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, 1.0)
        assert math.isclose(st.current_energy, 10.0), "追击回能 +5"
        d0 = _dmg(eng)
        _exec(eng, "ally", "ally_basic")
        assert math.isclose(_dmg(eng) - d0, ATK * 2.7 * Z0 * C2, rel_tol=1e-9)
        assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, 0.0)
        assert math.isclose(st.current_energy, 15.0)
        d0, hp1 = _dmg(eng), e1.current_hp
        _exec(eng, "ally", "ally_basic")   # 0 层不再触发（modifier 仍在——0 层不摘件）
        assert math.isclose(_dmg(eng), d0), "stacks()=0 闸住（has_modifier 会恒触发的死钩在案）"
        assert "WISEMANS_FOLLY" in e1.modifiers
        hp2 = e1.current_hp
        _cast(eng, "1305", "130502")   # 自身攻击不触发愚行（队友域勘正④）——只有战技+天赋追击
        assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, 0.0)

    def test_folly_latest_target_only(self, compiled):
        """「仅对终结技最新施放的目标生效」：换目标重开大 → 旧目标摘除、新目标挂 2 层."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _ult(eng, target=e1)
        assert "WISEMANS_FOLLY" in e1.modifiers
        _ult(eng, target=e2)
        assert "WISEMANS_FOLLY" not in e1.modifiers, "旧目标摘除（勘正⑫）"
        assert math.isclose(e2.modifiers["WISEMANS_FOLLY"].stacks, 2.0)
        d0 = _dmg(eng)
        _exec(eng, "ally", "ally_basic", target=e1)   # e1 无愚行 → 不触发
        assert math.isclose(_dmg(eng), d0)
        _exec(eng, "ally", "ally_basic", target=e2)   # e2 触发（0 层归纳区 1.085）
        assert math.isclose(_dmg(eng) - d0, ATK * 2.7 * Z0 * C0, rel_tol=1e-9)
        assert math.isclose(e2.modifiers["WISEMANS_FOLLY"].stacks, 1.0)


class TestTechnique:
    def test_idol_slow(self):
        """秘技：进战全体速度 -15%×2 回合（100×0.85 = 85）."""
        eng = _make(_compiled(pre_battle=True))
        for eid in ("e1", "e2"):
            e = eng.state.actors[eid]
            assert "IDOL_SLOW" in e.modifiers
            assert math.isclose(eng.pipeline.effective_stats(e)["spd"], 85.0, rel_tol=1e-9)


class TestEidolons:
    def test_e1_start4_and_cap10(self):
        """E1：开战 4 层归纳（crit 0.27/0.70）；1 次战技 → 5 层；再 6 次 → 上限 10."""
        eng = _make(_compiled(eidolon=1))
        eng.state.skill_points = 99.0
        st = _dr(eng)
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 4.0), "E1 开战 4 层"
        se = eng.pipeline.effective_stats(st)
        assert math.isclose(se["crit_rate"], 0.27, rel_tol=1e-9)
        assert math.isclose(se["crit_dmg"], 0.7, rel_tol=1e-9)
        _cast(eng, "1305", "130502")
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 5.0), "refresh 读首挂件上限 10"
        for _ in range(6):
            _cast(eng, "1305", "130502")
        assert math.isclose(st.modifiers["SUMMATION"].stacks, 10.0), "E1 上限 10（官方「上限提高4层」）"
        se = eng.pipeline.effective_stats(st)
        assert math.isclose(se["crit_rate"], 0.42, rel_tol=1e-9)
        assert math.isclose(se["crit_dmg"], 1.0, rel_tol=1e-9)

    def test_e2_additional_segment(self):
        """E2（联动 E1：开战 4 层）：追击命中 → 附加段 0.2×ATK（additional 类——
        不归 follow_up 域构造性防递归；基线 1 段，debuff 计数通道缺在案）."""
        eng = _make(_compiled(eidolon=2))
        st, e1 = _dr(eng), eng.state.actors["e1"]
        d0 = _dmg(eng)
        _cast(eng, "1305", "130502")   # 归纳 4→5 层后追击：区 1.22125
        fua = ATK * 2.7 * Z0 * C5                     # 1474.15137408
        add = ATK * 0.2 * Z0 * C5                     # 109.19639808
        total = ATK * 1.5 * Z0 * C4 + fua + add       # 战技(4层区) + 追击 + 附加段
        assert math.isclose(_dmg(eng) - d0, total, rel_tol=1e-9)

    def test_e3_level_linkage(self):
        """E3（联动 E1/E2）：终结技 lv12 = 2.592、普攻 lv7 = 1.1（E1 开战 4 层区 1.189）."""
        eng = _make(_compiled(eidolon=3))
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _ult(eng)
        # 993.4848×2.592×0.5×0.9×1.189 = 1377.81399748608
        assert math.isclose(hp0 - e1.current_hp, ATK * 2.592 * Z0 * C4, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1305", "130501")
        # 993.4848×1.1×0.5×0.9×1.189 = 584.720446464
        assert math.isclose(hp1 - e1.current_hp, ATK * 1.1 * Z0 * C4, rel_tol=1e-9)

    def test_e4_energy_on_talent(self):
        """E4（勘正⑩ 翻案）：触发天赋 +15 能——战技路径 30+5+15 = 50."""
        eng = _make(_compiled(eidolon=4))
        st = _dr(eng)
        _cast(eng, "1305", "130502")
        assert math.isclose(st.current_energy, 50.0)
        _ult(eng)
        assert math.isclose(st.current_energy, 5.0)
        _exec(eng, "ally", "ally_basic")   # 愚行路径追击同样 +5+15
        assert math.isclose(st.current_energy, 25.0)

    def test_e5_level_linkage(self):
        """E5（联动 E1-E4）：战技 lv12 = 1.65（4 层区 1.189）、追击 lv12 = 2.97
       （5 层区 1.22125）；param(130504,1) 编译期随档联动."""
        eng = _make(_compiled(eidolon=5))
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        a, tgt = _exec(eng, "1305", "130502")
        # 993.4848×1.65×0.5×0.9×1.189 = 877.080669696
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.65 * Z0 * C4, rel_tol=1e-9)
        hp1 = e1.current_hp
        d0 = _dmg(eng)
        _emit_action(eng, "1305", a, tgt)
        # 追击 993.4848×2.97×0.5×0.9×1.22125 = 1621.566511488；E2 附加段 109.19639808
        assert math.isclose(_dmg(eng) - d0, ATK * 2.97 * Z0 * C5 + ATK * 0.2 * Z0 * C5,
                            rel_tol=1e-9)

    def test_e6_folly3_and_followup_boost(self):
        """E6（联动 E1-E5）：愚行 2+1=3 层（max_stack 3 结构上限——draft max 2 钳死在案）；
        追击增伤 50% 走 follow_up 类型桶（追击 ×1.5；E2 附加段 additional 类不吃桶）."""
        eng = _make(_compiled(eidolon=6))
        eng.state.skill_points = 99.0
        st, e1 = _dr(eng), eng.state.actors["e1"]
        _cast(eng, "1305", "130502")   # 归纳 4→5 层
        d0 = _dmg(eng)
        _ult(eng)
        assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, 3.0), "E6：2+1（勘正⑦）"
        # 愚行追击 lv12 = 2.97（5 层区 1.22125 × 增伤区 1.5）= 2432.349767232
        # + E2 附加段（additional 类不吃 follow_up 桶）109.19639808 = 2541.546165312
        for expect_stacks in (2.0, 1.0, 0.0):
            d0 = _dmg(eng)
            _exec(eng, "ally", "ally_basic")
            assert math.isclose(_dmg(eng) - d0,
                                ATK * 2.97 * Z0 * C5 * 1.5 + ATK * 0.2 * Z0 * C5,
                                rel_tol=1e-9)
            assert math.isclose(e1.modifiers["WISEMANS_FOLLY"].stacks, expect_stacks)
        d0 = _dmg(eng)
        _exec(eng, "ally", "ally_basic")   # 第 4 次不再触发
        assert math.isclose(_dmg(eng), d0)
        assert math.isclose(st.current_energy, 5.0 + 3 * 20.0), "追击 +5 与 E4 +15 双路同吃"
