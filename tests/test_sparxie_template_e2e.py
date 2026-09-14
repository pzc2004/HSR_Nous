"""火花 1501 模板端到端对轴（验收型批·欢愉命途首模板）：真模板 YAML → 编译 →
直播态换技能/好活当赏天赋附伤/笑点经济/欢愉技段链/行迹/星魂全链 → 手算全等.

口径常数：火花 atk 640.332；行迹后 crit 0.17/0.633（期望暴击区 1+0.17×0.633=1.10761）；
假人 def 1000 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9 → Z0=0.45×1.10761。
档位：普攻/强化普攻 lv6（E3→lv7），战技/终结技/天赋/欢愉技 lv10（E3 欢愉技→lv11；
E5 终结技/天赋/欢愉技→lv12）。削韧显示值=tbgd ShowStanceList÷3。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 640.332
CRIT_ZONE = 1 + (0.05 + 0.12) * (0.5 + 0.133)   # 1.10761（行迹后期望暴击区）
Z0 = 0.5 * 0.9 * CRIT_ZONE                       # 防御区×未击破×期望暴击（抗性区 1.0）


def _build(*, eidolon: int = 0, pre_battle: bool = False, extra_elation: int = 0):
    member = {"character_template": "1501", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member]
    for i in range(extra_elation):
        team.append({"actor_id": f"ela{i}", "name": f"欢愉{i}", "inline": True,
                     "path": "elation",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": f"ela{i}_basic", "name": "普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "fire", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10}]})
    team.append({"actor_id": "ally", "name": "辅手", "inline": True,
                 "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
                 "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "fire",
                              "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
                              "skill_point_gain": 1}]})
    build = {"build": {"team": team,
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1501", "technique": "150107"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, extra_elation: int = 0):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle,
                                    extra_elation=extra_elation),
                             _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _spx(eng):
    return eng.state.actors["1501"]


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
    st = _spx(eng)
    st.current_energy = 160.0
    ult = next(a for a in eng.actions_by_actor["1501"] if a.action_id == "150103")
    assert eng._fire_ultimate(st, ult) is True


def _avail(eng, aid):
    st = _spx(eng)
    a = next(x for x in eng.actions_by_actor["1501"] if x.action_id == aid)
    return eng._available_if_ok(st, a)


class TestSparxieCompile:
    def test_actions_resources_level_key(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1501"]}
        assert set(acts) == {"150101", "150102", "150103", "150108",
                             "150109", "150110", "150120"}
        assert acts["150120"].level_key == "elation_skill", "勘正⑨：欢愉技独立取档键"
        decls = compiled.resource_decls_by_actor["1501"]
        assert decls["punchline"]["max"] == 10
        assert decls["thrill"]["max"] == 10
        assert decls["_live"]["max"] == 1
        assert decls["_engagement"]["max"] == 20, "互动陷阱本次技能内上限 param(150102,1)"


class TestTraces:
    def test_trace_crit_stats(self, compiled):
        """行迹数值节点：暴击率 0.05+0.12=0.17、暴伤 0.5+0.133=0.633（勘正③ trace_stat_effects 收）."""
        eng = _make(compiled)
        es = eng.pipeline.effective_stats(_spx(eng))
        assert math.isclose(es["atk"], 640.332, rel_tol=1e-9)
        assert math.isclose(es["crit_rate"], 0.17, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.633, rel_tol=1e-9)


class TestBasic:
    def test_basic_damage_economy(self, compiled):
        """普攻 lv6=1.0 档：e1 伤 1.0×ATK×Z0；产 1 点、回 20 能、削韧 10."""
        eng = _make(compiled)
        st, e1 = _spx(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp0 - e1.current_hp, 1.0 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点（3→4）"
        assert math.isclose(st.current_energy, 20.0), "回能 20"
        assert math.isclose(e1.toughness, 90.0), "削韧 10（tbgd 30÷3）"


class TestLivestream:
    def test_open_toggle_and_availability(self, compiled):
        """150102 开播：耗 1 点、_live 闩置 1、好活当赏挂上、计数复位；换技能互斥生效."""
        eng = _make(compiled)
        st = _spx(eng)
        assert _avail(eng, "150101") and not _avail(eng, "150108")
        assert not _avail(eng, "150110"), "150110 重名变体恒不可用（1 < 0 良构闸）"
        _cast(eng, "1501", "150102")
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点（3→2，tbgd 权威）"
        assert math.isclose(st.resources["_live"], 1.0)
        assert math.isclose(st.resources["_engagement"], 0.0)
        assert "CERTIFIED_BANGER" in st.modifiers, "好活当赏（直播态同域推定挂，B19 在案）"
        assert not _avail(eng, "150101") and _avail(eng, "150108")
        assert _avail(eng, "150109") and not _avail(eng, "150102"), "直播态内开播技互斥"

    def test_enhanced_basic_finalize(self, compiled):
        """强化普攻 lv6（主 1.0/邻 0.5）+ 天赋主段 0.4（好活当赏门内）：e1 吃 1.4×ATK×Z0、
        e2 吃 0.5×ATK×Z0；削韧主 10+天赋 5、邻 5；结算下播 _live 回 0."""
        eng = _make(compiled)
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150108")
        assert math.isclose(hp1 - e1.current_hp, 1.4 * ATK * Z0, rel_tol=1e-9), (
            "主 1.0 + 天赋 0.4（param(150104,3) lv10）")
        assert math.isclose(hp2 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9), (
            "相邻 lv6=0.5；天赋相邻段 #4 待收不计")
        assert math.isclose(e1.toughness, 85.0), "主 10 + 天赋 5"
        assert math.isclose(e2.toughness, 95.0), "邻 5（tbgd 15÷3）"
        assert math.isclose(st.resources["_live"], 0.0), "结算直播连线结果（官方 desc）"
        assert math.isclose(eng.state.skill_points, 3.0), "开播-1 强普+1"
        assert math.isclose(st.current_energy, 40.0), "强普回能 40（tbgd）"
        assert _avail(eng, "150101") and not _avail(eng, "150108")


class TestTalentGate:
    def test_no_banger_no_bonus(self, compiled):
        """好活当赏门：未开播直接打强化普攻/终结技 → 天赋附伤两子句都不发（勘正②终结技半）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "1501", "150108")   # 绕过 available_if 直施——无好活当赏
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK * Z0, rel_tol=1e-9), (
            "无天赋主段 0.4（CERTIFIED_BANGER 未挂）")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9), (
            "终结技 lv10 #2=0.5——无天赋全体 0.48")
        assert math.isclose(hp2 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9)


class TestUltimate:
    def test_ult_damage_and_economy(self, compiled):
        """终结技（无好活当赏）：全体 0.5×ATK×Z0、削韧 20、返能 5；
        笑点 2（本体）+2（万花筒 1 欢愉）=4、爆点 +1；palette 重烘暴伤 +0.32."""
        eng = _make(compiled)
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(e1.toughness, 80.0), "削韧 20（tbgd 60÷3）"
        assert math.isclose(st.current_energy, 5.0), "满 160 开大返 5"
        assert math.isclose(st.resources["punchline"], 4.0), "2+2（单欢愉档）"
        assert math.isclose(st.resources["thrill"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.08 * 4, rel_tol=1e-9), "1501103：4 笑点×8% 重烘"
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"],
                            0.5 + 0.08 * 4, rel_tol=1e-9), "team scope 辅手同吃"

    def test_ult_with_banger_talent(self, compiled):
        """开播后开大：全体 (0.5+0.48)×ATK×Z0（天赋终结技半 lv10 #2=0.48，好活当赏门内）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, 0.98 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.98 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(e1.toughness, 75.0), "终结技 20 + 天赋 5"
        assert math.isclose(_spx(eng).resources["punchline"], 4.0)


class TestKaleidoscope:
    def test_two_elation(self, compiled):
        """1501102 二欢愉档：开大额外 +4 笑点 +1 爆点（count_team('elation')==2）."""
        eng = _make(_compiled(extra_elation=1))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(st.resources["punchline"], 6.0), "2+4"
        assert math.isclose(st.resources["thrill"], 1.0), "爆点档 1/1/4——二欢愉 +1（终结技本体不产爆点）"

    def test_three_elation(self, compiled):
        """1501102 ≥3 欢愉档：开大额外 +8 笑点（钳上限 10）+4 爆点."""
        eng = _make(_compiled(extra_elation=2))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(st.resources["punchline"], 10.0), "2+8=10（max 10 保守口径）"
        assert math.isclose(st.resources["thrill"], 4.0), "≥3 档 +4"


class TestElationSkill:
    def test_signal_overflow_segments(self, compiled):
        """欢愉技 lv10：全体 0.5 + 追加 20 段×0.25 随机单体（expected 按序取首全落 e1）——
        e1 吃 5.5×ATK×Z0；e2 只吃全体 0.5（勘正①：hook 全体段已删，无双倍）."""
        eng = _make(compiled)
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2, sp0 = e1.current_hp, e2.current_hp, eng.state.skill_points
        _cast(eng, "1501", "150120")
        assert math.isclose(hp1 - e1.current_hp, (0.5 + 20 * 0.25) * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9), (
            "全体主段 action scaling 单承——无 hook 重复结算")
        assert math.isclose(st.resources["thrill"], 2.0), "#4=2 爆点"
        assert math.isclose(eng.state.skill_points, sp0), "不耗点（tbgd）"
        assert math.isclose(st.current_energy, 5.0), "回能 5（tbgd）"
        assert math.isclose(e1.toughness, 100.0), "削韧待实测保守 0"

    def test_e3_level_gear(self, compiled):
        """E3 联动：欢愉技 lv11（全体 0.525、追加 0.2625×20）+ 普攻 lv7=1.1 档."""
        eng = _make(_compiled(eidolon=3))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150120")
        assert math.isclose(hp1 - e1.current_hp, (0.525 + 20 * 0.2625) * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.525 * ATK * Z0, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK * Z0, rel_tol=1e-9), (
            "普攻默认 lv6，E3+1 → lv7=index 6=1.1（勘正⑫）")

    def test_e5_level_gear(self, compiled):
        """E5 联动：终结技 lv12=index 11=0.54 + 天赋 lv12 #2=0.528；欢愉技 lv12（全体 0.55、追加 0.275×20）."""
        eng = _make(_compiled(eidolon=5))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, (0.54 + 0.528) * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, (0.54 + 0.528) * ATK * Z0, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150120")
        # 开大后笑点 2+2+5(E4)=9：palette 暴伤 0.633+0.72=1.353、E1 抗穿 0.015×9=0.135——实时面板
        z = 0.5 * 0.9 * (1 + 0.015 * 9) * (1 + 0.17 * (0.633 + 0.08 * 9))
        assert math.isclose(_spx(eng).resources["punchline"], 9.0)
        assert math.isclose(hp1 - e1.current_hp, (0.55 + 20 * 0.275) * ATK * z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.55 * ATK * z, rel_tol=1e-9)


class TestEidolons:
    def test_e1_res_pen_halo(self):
        """E1（勘正⑤收编）：每笑点全体抗穿 +1.5%——开大后 4 笑点 → 0.06；再开大 8 笑点 → 0.12."""
        eng = _make(_compiled(eidolon=1))
        st, ally = _spx(eng), eng.state.actors["ally"]
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.015 * 4, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.015 * 4, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(st.resources["punchline"], 8.0)
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.015 * 8, rel_tol=1e-9), (
            "on_resource_gain 重挂 replace 重烘追层")

    def test_e4_extra_punchline(self):
        """E4：开大额外 +5 笑点 → 2+2+5=9；palette 重烘 0.08×9=0.72."""
        eng = _make(_compiled(eidolon=4))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(st.resources["punchline"], 9.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.08 * 9, rel_tol=1e-9)

    def test_e6_res_pen_and_damage(self):
        """E6：全属性抗穿 +20%（stat_effects 直挂）——普攻抗性区 1.0→1.2."""
        eng = _make(_compiled(eidolon=6))
        st, e1 = _spx(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp1 - e1.current_hp,
                            1.1 * ATK * 0.5 * 1.2 * 0.9 * CRIT_ZONE, rel_tol=1e-9), (
            "eidolon=6 含 E3 → 普攻 lv7=1.1 档联动")
        _ult(eng)   # E1 联动：9 笑点（2+2+5）→ 抗穿合计 0.2+0.135
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"],
                            0.2 + 0.015 * 9, rel_tol=1e-9)


class TestEngagementGate:
    def test_counter_cap_and_reset(self, compiled):
        """互动陷阱计数：手动施放 +1（≤20 闸）；打满 20 后不可用；再开播复位（勘正④）."""
        eng = _make(compiled)
        st = _spx(eng)
        _cast(eng, "1501", "150102")
        _cast(eng, "1501", "150109")
        assert math.isclose(st.resources["_engagement"], 1.0)
        st.resources["_engagement"] = 19.0
        assert _avail(eng, "150109"), "19<20 仍可用"
        eng.state.skill_points = 5.0
        _cast(eng, "1501", "150109")
        assert math.isclose(st.resources["_engagement"], 20.0)
        assert not _avail(eng, "150109"), "本次技能内最多发动 20 次（param(150102,1)）"
        _cast(eng, "1501", "150108")   # 结算下播
        _cast(eng, "1501", "150102")   # 再开播 → 计数复位
        assert math.isclose(st.resources["_engagement"], 0.0)
        assert _avail(eng, "150109")


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技流量变现：进战全体 0.5×ATK×Z0 火伤 + 回 2 战技点（勘正⑩ gain_skill_point 收编）."""
        eng = _make(_compiled(pre_battle=True), initial_sp=0)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(eng.state.skill_points, 2.0), "#1=2 战技点"
        assert math.isclose(1e9 - e1.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9), "#2=50% ATK"
        assert math.isclose(1e9 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9)
