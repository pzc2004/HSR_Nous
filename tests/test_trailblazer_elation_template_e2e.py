"""开拓者•欢愉 8010 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 好活当赏层账/
笑点账/天赋追加/终结技双分支/欢愉技九段/行迹/星魂全链 → 手算全等（过堂勘正十六件
见 fixture 头注）。

口径常数：开拓者 atk 465.696、行迹 atk_pct 0.28 → 实战面板 596.09088；crit_rate 面板
0.32（0.05+小节点 0.12+大行迹 0.15）、crit_dmg 面板 0.633（0.5+小节点 0.133）→ 期望
暴击区 1+0.32×0.633=1.20256。假人 def 1000 → 防御区 0.5、雷弱点 → 抗性区 1.0、未击破
0.9。Z=0.5×0.9×1.20256=0.541152。
终结技暴伤 +50%（lv10）后 crit_dmg 1.133 → Z_ULT=0.45×1.36256=0.613152；
E5 暴伤 +54%（lv12）后 crit_dmg 1.173 → Z_E5ULT=0.45×1.37536=0.618912；
E6 暴伤再 +100% 后 crit_dmg 1.633 → Z_E6=0.45×1.52256=0.685152。
天赋追加段/801020 伤害为 ATK 基数占位（欢愉管线待收②——只对轴 DSL 接线）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

TB_ATK = 465.696 * 1.28                    # 行迹 atk_pct 0.28 后实战面板 = 596.09088
Z = 0.5 * 0.9 * (1 + 0.32 * 0.633)         # 防御区×未击破×期望暴击区（行迹后面板）
Z_ULT = 0.5 * 0.9 * (1 + 0.32 * 1.133)     # 终结技暴伤 +0.5（lv10）后
Z_E5ULT = 0.5 * 0.9 * (1 + 0.32 * 1.173)   # E5 终结技暴伤 +0.54（lv12）后
Z_E6 = 0.5 * 0.9 * (1 + 0.32 * 1.633)      # E6 暴伤再 +1.0 后


def _build(*, eidolon: int = 0):
    member = {"character_template": "8010", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True, "element": "thunder",
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0):
    return compile_encounter(_build(eidolon=eidolon), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _tb(eng):
    return eng.state.actors["8010"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _cast(eng, owner, aid, target_id="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, target_id="8010"):
    st = _tb(eng)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = 160.0
    ult = next(a for a in eng.actions_by_actor["8010"] if a.action_id == "801003")
    assert eng._fire_ultimate(st, ult) is True


class TestTrailblazerCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["8010"]}
        assert acts == {"801001", "801002", "801003", "801020"}
        decls = compiled.resource_decls_by_actor["8010"]
        assert set(decls) == {"punchline", "aha_turn"}

    def test_elation_skill_sealed(self, compiled):
        """欢愉技 available_if 封手动后门（勘正⑤）：res_aha_turn 恒 0 → 不可用."""
        eng = _make(compiled)
        a = next(x for x in eng.actions_by_actor["8010"] if x.action_id == "801020")
        assert eng._available_if_ok(_tb(eng), a) is False


class TestBattleStart:
    def test_loadout(self, compiled):
        """进战两件（勘正⑩）：+1 笑点（欢愉角色×1）/ 好活当赏 20 层 2 回合；行迹面板."""
        eng = _make(compiled)
        st = _tb(eng)
        assert math.isclose(st.resources["punchline"], 1.0), "§8.2 进战每欢愉角色 +1"
        cb = st.modifiers["CERTIFIED_BANGER"]
        assert math.isclose(cb.stacks, 20.0) and math.isclose(cb.duration, 2.0), (
            "§8.1 进战 20 点好活当赏，持续 2 回合")
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.32, rel_tol=1e-9), "0.05+小节点0.12+大行迹0.15"
        assert math.isclose(eff["crit_dmg"], 0.633, rel_tol=1e-9), "0.5+小节点0.133"
        assert math.isclose(eff["atk"], 465.696 * 1.28, rel_tol=1e-9), "atk_pct 0.28"


class TestBasicAndSkill:
    def test_basic_lv6(self, compiled):
        """普攻 lv6=index5=1.0 单体；产 1 点；回能 20+天赋 10=30；笑点 1+3=4."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0)
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点"
        assert math.isclose(st.current_energy, 30.0), "普攻回 20 + 天赋攻击后回 10"
        assert math.isclose(st.resources["punchline"], 4.0), "天赋攻击后 +3 笑点"

    def test_skill_lv10_with_cb_extra(self, compiled):
        """战技 lv10：0.6 全体 + 天赋追加 0.3（持好活当赏）；自体好活当赏 20+20=40."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * (0.6 + 0.3) * Z, rel_tol=1e-9), (
            "战技 0.6 + 天赋追加 0.3（勘正⑦——持好活当赏门）")
        assert math.isclose(hp2 - e2.current_hp, TB_ATK * (0.6 + 0.3) * Z, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点"
        assert math.isclose(st.current_energy, 40.0), "战技回 30 + 天赋 10"
        assert math.isclose(st.resources["punchline"], 4.0)
        cb = st.modifiers["CERTIFIED_BANGER"]
        assert math.isclose(cb.stacks, 40.0) and math.isclose(cb.duration, 2.0), (
            "进战 20 + 战技 20（refresh 重挂加层=合并，勘正⑨）")

    def test_skill_extra_gate_snapshot(self, compiled):
        """天赋追加门读事件开始旧值（族谱#9）：摘除好活当赏后施放战技→本发无追加，
        但战技发放钩仍重挂 20 层."""
        eng = _make(compiled)
        st = _tb(eng)
        eng._remove_modifier(st, "CERTIFIED_BANGER", "test")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 0.6 * Z, rel_tol=1e-9), (
            "门按施放时判定——本发不追加（文本序：伤害在先获得在后）")
        assert math.isclose(st.modifiers["CERTIFIED_BANGER"].stacks, 20.0), "战技重挂 20"


class TestUltimate:
    def test_self_target_branch_a(self, compiled):
        """终结技指自己（欢愉目标）：暴伤 +50% → 面板 1.133；好活当赏 20+10=30；立即触发
        欢愉技（吃暴伤后 Z_ULT）：e1=8×0.2+均摊 0.3、e2=0.3；+5 笑点/回 5 能/回 1 点；
        触发的欢愉技再计天赋（+10 能 +3 笑点）."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "8010")
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.5, rel_tol=1e-9), "暴伤 +50%（lv10）"
        assert math.isclose(st.modifiers["CERTIFIED_BANGER"].stacks, 30.0), "分支 A +10"
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.2 + 0.6 / 2) * Z_ULT, rel_tol=1e-9), (
            "触发欢愉技：8 段×0.2+均摊 0.3（暴伤挂在触发前——文本序一致）")
        assert math.isclose(hp2 - e2.current_hp, TB_ATK * (0.6 / 2) * Z_ULT, rel_tol=1e-9)
        assert math.isclose(st.resources["punchline"], 9.0), "进战 1+终结技 5+天赋 3"
        assert math.isclose(st.current_energy, 20.0), "160 全扣→回 5+欢愉技 5+天赋 10"
        assert math.isclose(eng.state.skill_points, 4.0), "行迹 8010102：放大回 1 点"
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0), (
            "触发的欢愉技=我方施放 → 阿哈咬它挂账（含自身，勘正⑭）")

    def test_ally_target_branch_b_and_dispel(self, compiled):
        """终结技指非欢愉队友：暴伤 +50% 挂队友 + 净化控制类（普通 debuff 保留）+
        行动提前 50%（-5000）；分支 A 不发（队友无欢愉技、无好活当赏）；敌方零伤害."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_FREEZE", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2, dispellable=True))
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_DOT", name="裂伤", modifier_type="debuff",
            duration=2, dispellable=True))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        before = _remaining(eng, "ally")
        _ult(eng, "ally")
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"],
                            0.5 + 0.5, rel_tol=1e-9), "指定队友暴伤 +50%"
        assert "TEST_FREEZE" not in ally.modifiers, "控制类被净化（勘正⑧）"
        assert "TEST_DOT" in ally.modifiers, "非控制类 debuff 保留"
        assert math.isclose(before - _remaining(eng, "ally"), 5000.0, rel_tol=1e-9), (
            "分支 B：行动提前 50%")
        assert "CERTIFIED_BANGER" not in ally.modifiers, "非欢愉目标不发放好活当赏"
        assert math.isclose(hp1 - e1.current_hp, 0.0), "不触发欢愉技"
        assert math.isclose(eng.state.skill_points, 4.0), "放大回 1 点"


class TestElationSkillManual:
    def test_nine_segments(self, compiled):
        """欢愉技 lv10（手动对轴）：8 段随机 0.2（expected 确定化首敌）+ 均摊 0.6/2；
        回 5+天赋 10 能；天赋 +3 笑点；阿哈咬它挂账."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.2 + 0.6 / 2) * Z, rel_tol=1e-9), (
            "8×0.2 + 均摊 0.3（勘正⑥ scaling_atk 占位基数）")
        assert math.isclose(hp2 - e2.current_hp, TB_ATK * (0.6 / 2) * Z, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 15.0), "欢愉技回 5（tbgd）+天赋 10"
        assert math.isclose(st.resources["punchline"], 4.0)
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0)

    def test_aha_sic_em_clear_on_skill(self, compiled):
        """阿哈咬它清账（行迹 8010103）：欢愉技挂账 1 层 → 战技好活当赏 20+20+2=42，账摘."""
        eng = _make(compiled)
        st = _tb(eng)
        _cast(eng, "8010", "801020")
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0)
        _cast(eng, "8010", "801002")
        assert math.isclose(st.modifiers["CERTIFIED_BANGER"].stacks, 42.0), (
            "进战 20+战技 20+清账 2")
        assert "AHA_SIC_EM_ARMED" not in st.modifiers


class TestEidolons:
    def test_e1_armed_bank(self):
        """E1：战技挂账 1 层（好活当赏 40）→ 终结技指自己：分支 A 10+E1 兑现 2=52，账摘."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        _cast(eng, "8010", "801002")
        assert math.isclose(st.modifiers["E1_CB_ARMED"].stacks, 1.0)
        assert math.isclose(st.modifiers["CERTIFIED_BANGER"].stacks, 40.0)
        _ult(eng, "8010")
        assert math.isclose(st.modifiers["CERTIFIED_BANGER"].stacks, 52.0), (
            "40+分支A 10+E1 2×1（加算读，待实测在案）")
        assert "E1_CB_ARMED" not in st.modifiers, "下次终结技后清账"

    def test_e3_level_tracks(self):
        """E3（勘正①）：战技 lv12=0.66/天赋 lv12=0.33/欢愉技 lv11（0.21·0.63）；普攻仍 lv6."""
        eng = _make(_compiled(eidolon=3))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.21 + 0.63 / 2) * Z, rel_tol=1e-9), "lv11：8×0.21+0.315"
        assert math.isclose(hp2 - e2.current_hp, TB_ATK * (0.63 / 2) * Z, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * (0.66 + 0.33) * Z, rel_tol=1e-9), (
            "战技 lv12=0.66+天赋 lv12=0.33")
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z, rel_tol=1e-9), (
            "E3 不加普攻——仍 lv6=1.0")

    def test_e5_level_tracks(self):
        """E5：普攻 lv7=1.1（勘正①——非钳表尾）；终结技 lv12 暴伤 +54% → 面板 1.173；
        触发欢愉技 lv12（0.22·0.66）."""
        eng = _make(_compiled(eidolon=5))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.1 * Z, rel_tol=1e-9), "普攻 lv7=1.1"
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "8010")
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.54, rel_tol=1e-9), "暴伤 +54%（lv12）"
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.22 + 0.66 / 2) * Z_E5ULT, rel_tol=1e-9), (
            "lv12：8×0.22+0.33，暴伤后 Z_E5ULT")
        assert math.isclose(hp2 - e2.current_hp, TB_ATK * (0.66 / 2) * Z_E5ULT, rel_tol=1e-9)

    def test_e4_vulnerability(self):
        """E4：欢愉技后敌方全体易伤 10%·2 回合（当次不吃勘正⑬）→ 下次普攻 ×1.1."""
        eng = _make(_compiled(eidolon=4))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.21 + 0.63 / 2) * Z, rel_tol=1e-9), (
            "E4 挂在结算后——本发不吃（lv11 档）")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.1, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e2)["vulnerability"], 0.1, rel_tol=1e-9)
        assert math.isclose(e1.modifiers["E4_VULNERABILITY"].duration, 2.0)
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z * 1.1, rel_tol=1e-9), (
            "下次攻击吃易伤 ×1.1")

    def test_e6_crit_dmg_next_cast(self):
        """E6：欢愉技后自身暴伤 +100%·3 回合（当次不吃）→ 第二次欢愉技 lv12 全链：
        e1=2.09×Z_E6×1.1（E4 易伤随 eidolon=6 联动）."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.22 + 0.66 / 2) * Z, rel_tol=1e-9), "首发不吃 E6/E4"
        assert "E6_CRIT_DMG" in st.modifiers
        assert math.isclose(st.modifiers["E6_CRIT_DMG"].duration, 3.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 1.0, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * (8 * 0.22 + 0.66 / 2) * Z_E6 * 1.1, rel_tol=1e-9), (
            "二发吃 E6 暴伤+E4 易伤")
        assert math.isclose(hp2 - e2.current_hp,
                            TB_ATK * (0.66 / 2) * Z_E6 * 1.1, rel_tol=1e-9)
