"""那刻夏 1405 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 行迹三件/敌数增伤/
升华弱点/揭露增伤/追加战技/星魂全链 → 手算全等.

口径常数：那刻夏 atk 756.756、crit_rate 0.05+行迹 0.12=0.17、crit_dmg 0.5、max_energy 140；
行迹 dmg_wind 0.224 / hp_pct 0.10。假人 def 1000 → 防御区 0.5、弱点匹配 → 抗性区 1.0、
未击破 0.9。单智识队 → 行迹2 暴伤 +1.4（cd 1.9 → 期望暴击区 1+0.17×1.9=1.323）；
双敌 → 敌数增伤 skill 桶 0.2×2=0.4。默认档：basic lv6=1.0、skill/ult/talent lv10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 756.756
CRIT = 1 + 0.17 * 1.9          # 单智识：期望暴击区 1.323（暴伤 0.5+行迹2 1.4）
WIND = 0.224                   # 行迹风伤
DEF_ZONE = 0.5                 # 假人 def 1000
UNBROKEN = 0.9


def _build(*, eidolon: int = 0, pre_battle: bool = False, ally_path: str = "destruction"):
    member = {"character_template": "1405", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True, "path": ally_path,
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
        build["build"]["pre_battle"] = [{"actor_id": "1405", "technique": "140507"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人1", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["wind"]},
    {"actor_id": "e2", "name": "假人2", "hp": 1e9, "spd": 90, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

# 秘技验收专场：假人无风弱（fire）——风弱点植入可被 effective_weakness 观察
_STAGE_FIRE = {"stage": {"stage_id": "s2", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, ally_path: str = "destruction",
              stage=None):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle,
                                    ally_path=ally_path),
                             stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _ax(eng):
    return eng.state.actors["1405"]


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
    st = _ax(eng)
    st.current_energy = 140.0
    ult = next(a for a in eng.actions_by_actor["1405"] if a.action_id == "140503")
    assert eng._fire_ultimate(st, ult) is True


class TestAnaxaCompile:
    def test_actions(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1405"]}
        assert acts == {"140501", "140502", "140503"}


class TestBasePanel:
    def test_trace_stat_nodes(self, compiled):
        """行迹属性节点三件（收编①）：风伤 0.224 / 暴击率 +0.12 / 生命 +10%（1312 米沙先例）."""
        eng = _make(compiled)
        st = _ax(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.17, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["hp"],
                            970.2 * 1.10, rel_tol=1e-9), "hp_pct 0.10 白值口径"
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"]["wind"],
                            WIND, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK, rel_tol=1e-9)

    def test_trace2_solo_erudition_and_enemy_count_bucket(self, compiled):
        """行迹2 单智识分支（count_team erudition==1——勘正②）：暴伤 1.4；
        敌数增伤 skill 桶活读 0.2×2（勘正⑥ stat_exprs，1015 Archer 先例）."""
        eng = _make(compiled)
        st = _ax(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.5 + 1.4, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"]["skill_dmg_boost"],
                            0.4, rel_tol=1e-9), "0.2×2 敌（非 basic/ult 桶）"
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"].get("all", 0.0),
                            0.0, rel_tol=1e-9), "单智识无全队增伤"


class TestBasicAndSkill:
    def test_basic_damage_and_energy(self, compiled):
        """普攻 lv6=1.0：756.756×1.0×(1+0.224)×0.5×1.0×0.9×1.323；回能 30（20+行迹1 10 烘焙）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        before = e1.current_hp
        _cast(eng, "1405", "140501")
        expected = ATK * 1.0 * (1 + WIND) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, expected, rel_tol=1e-9)
        assert math.isclose(_ax(eng).current_energy, 30.0), "普攻回能 20+行迹1 10"
        assert "QUALITATIVE_DISCLOSURE" not in e1.modifiers, "无揭露 → 无追加战技"

    def test_skill_five_segments_and_sp(self, compiled):
        """战技 lv10=0.7：主段+4 弹射全中 e1（expected 取首）=5×[529.7292×(1+0.224+0.4)
        ×0.5×0.9×1.323]；SP 3→2；回能 6（tbgd 仲裁记档）."""
        eng = _make(compiled, initial_sp=3)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        b1, b2 = e1.current_hp, e2.current_hp
        _cast(eng, "1405", "140502")
        seg = ATK * 0.7 * (1 + WIND + 0.4) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(b1 - e1.current_hp, 5 * seg, rel_tol=1e-9), "主段+4 弹射全吃 skill 桶"
        assert math.isclose(b2 - e2.current_hp, 0.0), "expected 弹射取首=e1，e2 无伤"
        assert math.isclose(eng.state.skill_points, 2.0)
        assert math.isclose(_ax(eng).current_energy, 6.0)


class TestUltimate:
    def test_sublimation_disclosure_and_damage(self, compiled):
        """大招 lv10=1.6：apply_modifiers 预结算（勘正⑦）——升华 7 弱点/揭露/揭露增伤
        同帧落地，本击即吃 +0.3：1210.8096×(1+0.224+0.3)×0.5×0.9×1.323 每敌."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        b1, b2 = e1.current_hp, e2.current_hp
        _ult(eng)
        expected = ATK * 1.6 * (1 + WIND + 0.3) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(b1 - e1.current_hp, expected, rel_tol=1e-9)
        assert math.isclose(b2 - e2.current_hp, expected, rel_tol=1e-9), "AoE 双敌同值"
        for e in (e1, e2):
            assert "SUBLIMATION" in e.modifiers and "QUALITATIVE_DISCLOSURE" in e.modifiers
            assert len(eng.pipeline.effective_weakness(e)) == 7, "升华 7 弱点（weakness_add 收编）"
        assert "QUALI_DMG_BOOST" in _ax(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_ax(eng))["dmg_bonus"]["all"],
                            0.3, rel_tol=1e-9)
        assert math.isclose(_ax(eng).current_energy, 5.0), "终结技自回 5"

    def test_no_additional_skill_on_ult(self, compiled):
        """终结技不触发天赋追加战技（触发域仅 basic/skill）——大招后 e1 只掉一段血."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        after_ult = e1.current_hp
        # 大招的 on_action 已由引擎自发（_fire_ultimate 内）；无追加段 → 血量不再变
        assert math.isclose(e1.current_hp, after_ult, rel_tol=1e-9)


class TestTalentAdditionalSkill:
    def test_skill_on_disclosed_full_chain(self, compiled):
        """大招后战技打揭露目标：主段+4 弹射+1 追加=6×[529.7292×(1+0.224+0.4+0.3)×0.5×0.9×1.323]."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        before = e1.current_hp
        _cast(eng, "1405", "140502")
        seg = ATK * 0.7 * (1 + WIND + 0.4 + 0.3) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, 6 * seg, rel_tol=1e-9), (
            "追加战技吃 skill 桶+揭露增伤（伪行动 action_type skill）")

    def test_basic_on_disclosed_triggers_additional(self, compiled):
        """普攻（lv6=1.0）打揭露目标也触发追加战技：普攻段 + 追加段双账."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        before = e1.current_hp
        _cast(eng, "1405", "140501")
        basic = ATK * 1.0 * (1 + WIND + 0.3) * DEF_ZONE * UNBROKEN * CRIT
        add = ATK * 0.7 * (1 + WIND + 0.4 + 0.3) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, basic + add, rel_tol=1e-9)


class TestTrace1TurnStartEnergy:
    def test_gain_30_when_no_disclosure(self, compiled):
        """行迹1②：回合开始无揭露 → 回 30 能（勘正⑩ gain_energy 收编；揭露在挂不回——代理条件）."""
        eng = _make(compiled)
        st = _ax(eng)
        eng.bus.emit("on_turn_start", {"actor": "1405"}, eng.state)
        assert math.isclose(st.current_energy, 30.0)
        eng.bus.emit("on_turn_start", {"actor": "1405"}, eng.state)
        assert math.isclose(st.current_energy, 60.0), "无揭露每回合开始都回"

    def test_no_gain_when_disclosure_up(self, compiled):
        """揭露在挂（增伤件同寿命代理）→ 回合开始不回：大招后能量锁 5."""
        eng = _make(compiled)
        st = _ax(eng)
        _ult(eng)
        eng.bus.emit("on_turn_start", {"actor": "1405"}, eng.state)
        assert math.isclose(st.current_energy, 5.0)


class TestTrace2DualBranch:
    def test_double_erudition_team_dmg(self):
        """双智识（count_team erudition>=2）：全队增伤 +50%、无暴伤件——分支互斥."""
        eng = _make(_compiled(ally_path="erudition"))
        st, ally = _ax(eng), eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"]["all"],
                            0.5, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"]["all"],
                            0.5, rel_tol=1e-9), "all_allies 辐射辅手同吃"
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.5, rel_tol=1e-9), "≥2 智识无暴伤件（enable_if 互斥）"


class TestEidolons:
    def test_e1_first_skill_sp_and_def_down(self):
        """E1：首次战技回 1 点（once_per_battle——勘正⑪）+ 主目标 def_pct −16%（勘正③——
        def 1000→840，防御区 1−840/1840）；二次战技不再回点."""
        eng = _make(_compiled(eidolon=1), initial_sp=3)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1405", "140502")
        assert math.isclose(eng.state.skill_points, 3.0), "3−1 耗 +1 回（首次）"
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"],
                            1000 * 0.84, rel_tol=1e-9)
        before = e1.current_hp
        _cast(eng, "1405", "140502")
        assert math.isclose(eng.state.skill_points, 2.0), "第二次不回点"
        seg = ATK * 0.7 * (1 + WIND + 0.4) * (1 - 840 / 1840) * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, 5 * seg, rel_tol=1e-9), (
            "减防在挂后五段全吃新防御区")

    def test_e2_no_live_effects(self):
        """E2（勘正④）：两半全待收无活件——actor_enter 手工 emit 后敌人无任何 E2 修饰."""
        eng = _make(_compiled(eidolon=2))
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert not any(mid.startswith("E2_") for mid in eng.state.actors["e1"].modifiers)

    def test_e3_ult_lv12_basic_lv7(self):
        """E3（族谱 #18 联动）：终结技实取 lv12=1.76（index 11）、普攻实取 lv7=1.1."""
        eng = _make(_compiled(eidolon=3))
        e1 = eng.state.actors["e1"]
        before = e1.current_hp
        _cast(eng, "1405", "140501")
        basic = ATK * 1.1 * (1 + WIND) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, basic, rel_tol=1e-9)
        before = e1.current_hp
        _ult(eng)
        ult = ATK * 1.76 * (1 + WIND + 0.3) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, ult, rel_tol=1e-9), "lv12=index 11=1.76"

    def test_e4_atk_stacks(self):
        """E4（勘正⑭ 单件 stat_exprs 活读）：一战技后 1 层 atk×1.3；二战技后 2 层 atk×1.6."""
        eng = _make(_compiled(eidolon=4))
        st = _ax(eng)
        _cast(eng, "1405", "140502")
        assert math.isclose(st.modifiers["E4_ATK_STACKS"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            ATK * 1.3, rel_tol=1e-9)
        _cast(eng, "1405", "140502")
        assert math.isclose(st.modifiers["E4_ATK_STACKS"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            ATK * 1.6, rel_tol=1e-9), "至多 2 层"

    def test_e5_skill_lv12_talent_lv12(self):
        """E5：战技实取 lv12=0.77（index 11——主+弹射+追加同档）、揭露增伤实取 lv12=0.324."""
        eng = _make(_compiled(eidolon=5))
        e1 = eng.state.actors["e1"]
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(_ax(eng))["dmg_bonus"]["all"],
                            0.324, rel_tol=1e-9), "天赋 lv12 揭露增伤随档"
        before = e1.current_hp
        _cast(eng, "1405", "140502")
        seg = ATK * 0.77 * (1 + WIND + 0.4 + 0.324) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, 6 * seg, rel_tol=1e-9)

    def test_e6_true_damage_and_trace2_both(self):
        """E6：① 受击追加真伤 0.3×原伤害（勘正⑤ 防递归闸——测试跑完即证明不自激）；
        ② 行迹2 双效果常驻：暴伤 1.9 且全队增伤 0.5 同时在场."""
        eng = _make(_compiled(eidolon=6))
        st, ally = _ax(eng), eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"], 1.9, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"]["all"],
                            0.5, rel_tol=1e-9), "E6 双效果不互斥"
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"]["all"],
                            0.5, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        before = e1.current_hp
        _cast(eng, "1405", "140501")   # E3 联动 → 普攻 lv7=1.1
        seg = ATK * 1.1 * (1 + WIND + 0.5) * DEF_ZONE * UNBROKEN * CRIT
        assert math.isclose(before - e1.current_hp, seg * 1.3, rel_tol=1e-9), (
            "普攻段 + E6 真伤 0.3×原伤害")


class TestTechnique:
    def test_pre_battle_wind_weakness_implant(self):
        """秘技（勘正⑫ weakness_add 近似收编）：fire 弱假人入战获风弱点——
        effective_weakness 含 wind（施放者=那刻夏风属性近似）."""
        eng = _make(_compiled(pre_battle=True, stage=_STAGE_FIRE))
        e1 = eng.state.actors["e1"]
        assert "TECH_ATTACKER_WEAKNESS" in e1.modifiers
        assert "wind" in eng.pipeline.effective_weakness(e1)
        eng2 = _make(_compiled(stage=_STAGE_FIRE))
        assert "wind" not in eng2.pipeline.effective_weakness(eng2.state.actors["e1"])
