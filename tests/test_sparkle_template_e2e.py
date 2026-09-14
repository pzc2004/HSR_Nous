"""花火 1306 模板端到端对轴（验收型批·加强版单轨）：真模板 YAML → 编译 →
天赋 SP 上限/梦游鱼/谜诡易伤/溢出池/行迹/星魂全链 → 手算全等.

口径常数：花火 atk 523.908、crit_dmg 0.5、spd 101、max_energy 110；辅手 atk 1500。
梦游鱼 lv10：暴伤 = 0.24×自身暴伤 + 0.45；谜诡 lv10：回 6 点、易伤 +6%/层（叠天赋 4%）；
天赋 lv10：SP 上限 +2（#3 勘正）、幻景易伤 4%/层、持续 2、至多 3 层。
假人 def 1000 → 防御区 0.5；溢出池上限 10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


def _build(*, eidolon: int = 0, pre_battle: bool = False, initial_sp: int = 3):
    member = {"character_template": "1306", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1306", "technique": "1130607"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
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


def _spk(eng):
    return eng.state.actors["1306"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


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
    st = _spk(eng)
    st.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1306"] if a.action_id == "1130603")
    assert eng._fire_ultimate(st, ult) is True


class TestSparkleCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1306"]}
        assert acts == {"1130601", "1130602", "1130603"}
        decls = compiled.resource_decls_by_actor["1306"]
        assert decls["sp_overflow"]["max"] == 10


class TestTalentAndNocturne:
    def test_sp_max_override_and_nocturne_atk(self, compiled):
        """天赋：SP 上限 5+2=7（set_sp_max 首实例）；夜幕：全队 ATK+45%（atk_pct 在案）."""
        eng = _make(compiled)
        assert eng.state.sp_max_override == 7
        assert math.isclose(eng.pipeline.effective_stats(_spk(eng))["atk"],
                            523.908 * 1.45, rel_tol=1e-9), "夜幕 ATK+45%（花火自身）"
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["atk"],
                            1500 * 1.45, rel_tol=1e-9), "夜幕 ATK+45%（team scope 辅手同吃）"

    def test_figment_stacks_and_vuln_bake(self, compiled):
        """幻景：辅手耗点 → 花火 1 层；SPK_VULN 烘焙 = 层数×4%（无谜诡率）；
        谜诡在挂 → 率变 4%+6%（lv10 双件并入）."""
        eng = _make(compiled)
        tgt = eng.state.actors["e1"]
        _cast(eng, "ally", "ally_skill")   # 耗 1 点 → 幻景 1 层
        assert math.isclose(_spk(eng).modifiers["SPK_FIGMENT"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(tgt)["vulnerability"],
                            0.04, rel_tol=1e-9), "1 层 × 4%（烘焙追层）"
        _cast(eng, "ally", "ally_basic")   # 产点不触发
        assert math.isclose(_spk(eng).modifiers["SPK_FIGMENT"].stacks, 1.0)
        _ult(eng)   # 谜诡挂 → 重挂率变 10%/层（下次耗点重烘）
        _cast(eng, "ally", "ally_skill")   # 幻景 2 层 + 重烘
        assert math.isclose(_spk(eng).modifiers["SPK_FIGMENT"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(tgt)["vulnerability"],
                            2 * (0.04 + 0.06), rel_tol=1e-9), "2 层 ×（4%+谜诡 6%）"


class TestSkillDreamfish:
    def test_crit_dmg_respen_advance(self, compiled):
        """梦游鱼：目标暴伤 = 0.24×花火暴伤+0.45 = 0.57（lv10）+ 抗穿 10% + 拉条 50%."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        before = _remaining(eng, "ally")
        _cast(eng, "1306", "1130602", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"],
                            0.5 + 0.24 * 0.5 + 0.45, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"],
                            0.10, rel_tol=1e-9), "11306103 夜幕·抗穿半件"
        assert math.isclose(before - _remaining(eng, "ally"), 5000.0, rel_tol=1e-9), (
            "拉条 50%")
        assert "SPK_NOCTURNE_RESPEN" in ally.modifiers

    def test_self_cast_no_advance(self, compiled):
        """对自己施放不触发拉条（官方明文分支——condition 排除 self）."""
        eng = _make(compiled)
        before = _remaining(eng, "1306")
        _cast(eng, "1306", "1130602", target=_spk(eng))
        assert math.isclose(_remaining(eng, "1306"), before, rel_tol=1e-9)


class TestUltOverflow:
    def test_gain_overflow_bank_and_refill(self, compiled):
        """大招：SP 5+6 溢出 → 钳 7 记 4；辅手耗 1 点后回合结束 → 回补 1 至 7（池余 3）."""
        eng = _make(compiled, initial_sp=5)
        eng.state.skill_points = 5.0
        _ult(eng)
        assert math.isclose(eng.state.skill_points, 7.0), "钳到上限 7"
        assert math.isclose(_spk(eng).resources["sp_overflow"], 4.0), "溢出 4 记池"
        assert all("SPK_CIPHER" in eng.state.actors[aid].modifiers for aid in ("1306", "ally"))
        _cast(eng, "ally", "ally_skill")   # 7→6
        eng.bus.emit("on_turn_end", {"actor": "ally"}, eng.state)
        assert math.isclose(eng.state.skill_points, 7.0), "回合结束回补至上限"
        assert math.isclose(_spk(eng).resources["sp_overflow"], 3.0), "池余 3"

    def test_bank_cap_10(self, compiled):
        """池上限 10：SP 7 满时开大 → 6 点全溢出但只记…（7+6-7=6，池容 10 内）."""
        eng = _make(compiled, initial_sp=7)
        eng.state.skill_points = 7.0
        _ult(eng)
        assert math.isclose(_spk(eng).resources["sp_overflow"], 6.0), "满点开大 6 点全入池"


class TestTraces:
    def test_almanac_basic_energy_and_sp_consume_energy(self, compiled):
        """星历①：普攻回 20+10=30 能；星历②：耗 SP → 花火回 1 能."""
        eng = _make(compiled)
        st = _spk(eng)
        _cast(eng, "1306", "1130601")
        assert math.isclose(st.current_energy, 30.0)
        _cast(eng, "ally", "ally_skill")
        assert math.isclose(st.current_energy, 31.0), "星历② 耗点回 1 能"


class TestEidolons:
    def test_e1_atk_and_spd(self):
        """E1（新版）：谜诡 ATK+40%（3 回合）+ 开战/施放战技花火速度+15%（2 回合）."""
        eng = _make(_compiled(eidolon=1))
        st = _spk(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"],
                            101 * 1.15, rel_tol=1e-9), "开战速度+15%"
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["atk"],
                            1500 * (1 + 0.45 + 0.4), rel_tol=1e-9), "夜幕 45%+E1 40%"
        before = eng.pipeline.effective_stats(st)["spd"]
        _cast(eng, "1306", "1130602", target=st)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], before, rel_tol=1e-9), (
            "战技再触发速度件（refresh 同值）")

    def test_e2_def_shred(self):
        """E2（新版）：幻景每层敌方防御 -10%（def_pct 负值——2 层=-20%）."""
        eng = _make(_compiled(eidolon=2))
        tgt = eng.state.actors["e1"]
        _cast(eng, "ally", "ally_skill")
        _cast(eng, "ally", "ally_basic")
        _cast(eng, "ally", "ally_skill")
        assert math.isclose(eng.pipeline.effective_stats(tgt)["def_"],
                            1000 * (1 - 0.2), rel_tol=1e-9), "2 层 → 防御 -20%（800）"

    def test_e4_sp_max8_and_gain7(self):
        """E4：SP 上限 5+3=8；大招回 6+1=7（溢出同口径入池）."""
        eng = _make(_compiled(eidolon=4))
        assert eng.state.sp_max_override == 8
        eng.state.skill_points = 8.0
        _ult(eng)
        assert math.isclose(eng.state.skill_points, 8.0)
        assert math.isclose(_spk(eng).resources["sp_overflow"], 7.0), "6+1 全入池"

    def test_e6_extra_crit_dmg(self):
        """E6①：Skill 暴伤再 +30%×花火暴伤（eidolon=6 含 E3 → 战技 lv12 联动：
        0.264×0.5+0.486=0.618——合计 0.5+0.618+0.15=1.268）."""
        eng = _make(_compiled(eidolon=6))
        ally = eng.state.actors["ally"]
        _cast(eng, "1306", "1130602", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"],
                            0.5 + (0.264 * 0.5 + 0.486) + 0.3 * 0.5, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：进战回 3 点 + 花火回 20 能（#2 同参复用勘正）+ 迷误标记."""
        eng = _make(_compiled(pre_battle=True), initial_sp=0)
        st = _spk(eng)
        assert math.isclose(eng.state.skill_points, 3.0)
        assert math.isclose(st.current_energy, 20.0)
        assert "MISDIRECT" in st.modifiers
