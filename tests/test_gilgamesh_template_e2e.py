"""吉尔伽美什 1509 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 战技无视防/
兴致链/来兴致了/连携追击/Saber 协同/终结技弹射/行迹/星魂全链 → 手算全等.

口径常数：吉尔伽美什 atk 717.948、crit 0.05/0.5、spd 97、max_energy 360；行迹
atk+18%/暴击率+18.7%/雷伤+8%；1509103 光环 atk+20%/暴伤+20%（team）。
面板 atk = 717.948×1.38 = 990.76824；crit_rate 0.237；crit_dmg 0.7 → 期望暴击区
1+0.237×0.7 = 1.1659；雷伤区 1.08。假人 def 1000 → 防御区 0.5（持王来承认
def_pen 0.3 → 1000/1700；E3 lv12 0.33 → 1000/1670）；雷弱点 → 抗性 1.0；未击破 0.9。
战技 lv10 主 2.8 邻 1.4（lv12：3.08/1.54）；终结技 lv10 全体 4.0 + 弹射 1.0×10
（lv12：4.4/1.1）；追击 lv10 4.0（lv12 4.4）；普攻 lv6 1.0（E3 lv7 1.1）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# 面板推导常数（手算锚）
ATK = 717.948 * 1.38            # 行迹 0.18 + 1509103 光环 0.20
CRIT_EXP = 1 + 0.237 * 0.7      # 期望暴击区（crit_rate 0.05+0.187，crit_dmg 0.5+0.2）
DMG = 1.08                      # 雷伤区（行迹 dmg_thunder 0.08）
DEF0 = 0.5                      # 假人 def 1000 → (80×10+200)/(1000+80×10+200)
DEF_PEN3 = 1000 / 1700          # def_pen 0.3 → 1000/(1000×0.7+1000)
DEF_PEN33 = 1000 / 1670         # def_pen 0.33（E3 lv12 #5）
WEAKEN = 0.9                    # 未击破


def _ally_actions():
    return [
        {"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1},
        {"action_id": "ally_ult", "name": "终结技", "action_type": "ultimate",
         "target_type": "self", "damage_type": "none", "energy_cost": 100},
    ]


def _build(*, eidolon: int = 0, pre_battle: bool = False, with_saber: bool = False):
    team = [{"character_template": "1509", "level": 80},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": _ally_actions()}]
    if with_saber:
        # Saber 位替身（明显假名——不占真模板，专验 where actor_id=='1014' 代数寻址）
        team.append({"actor_id": "1014", "name": "Saber位替身", "inline": True,
                     "base_stats": {"atk": 2000, "spd": 95, "hp": 3000, "max_energy": 240},
                     "actions": [{"action_id": "saber_basic", "name": "替身普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "wind", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10, "skill_point_gain": 1}]})
    if eidolon:
        team[0]["eidolon"] = eidolon
    build = {"build": {"team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1509", "technique": "150907"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, with_saber: bool = False):
    return compile_encounter(
        _build(eidolon=eidolon, pre_battle=pre_battle, with_saber=with_saber),
        _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _gil(eng):
    return eng.state.actors["1509"]


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


def _ult(eng, owner, aid, energy):
    st = eng.state.actors[owner]
    st.current_energy = float(energy)
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _hp_lost(eng, aid):
    return 1e9 - eng.state.actors[aid].current_hp


class TestGilgameshCompile:
    def test_actions_resources_levels(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1509"]}
        assert acts == {"150901", "150902", "150903", "150905", "150909"}
        decls = compiled.resource_decls_by_actor["1509"]
        assert decls["interest"]["max"] == "inf"      # 官方文本无上限——不脑补
        assert decls["golden_rule"]["max"] == 3
        assert decls["_atk_count"]["max"] == 8

    def test_trace_panel(self, compiled):
        """行迹属性 + 1509103 光环：crit_rate 0.237 / atk ×1.38 / 暴伤 0.7."""
        eng = _make(compiled)
        es = eng.pipeline.effective_stats(_gil(eng))
        assert math.isclose(es["crit_rate"], 0.237, rel_tol=1e-9)
        assert math.isclose(es["atk"], ATK, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.7, rel_tol=1e-9)
        ally = eng.pipeline.effective_stats(eng.state.actors["ally"])
        assert math.isclose(ally["atk"], 1500 * 1.2, rel_tol=1e-9), "1509103 光环 team scope"
        assert math.isclose(ally["crit_dmg"], 0.5 + 0.2, rel_tol=1e-9)


class TestBasicAndSkill:
    def test_basic_lv6_damage(self, compiled):
        """普攻 lv6 1.0：ATK×1.0×1.08×0.5×1.1659×0.9；回 20 能 + 产 1 点."""
        eng = _make(compiled, initial_sp=3)
        sp0 = eng.state.skill_points
        _cast(eng, "1509", "150901")
        assert math.isclose(_hp_lost(eng, "e1"), ATK * 1.0 * DMG * DEF0 * CRIT_EXP * WEAKEN,
                            rel_tol=1e-9)
        assert math.isclose(_gil(eng).current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, sp0 + 1)

    def test_skill_blast_and_def_pen(self, compiled):
        """战技 lv10：主 2.8/邻 1.4，apply_modifiers 伤害前挂载——本次即吃 def_pen 0.3
        （防御区 1000/1700）；耗产 0/0 + 回 30 能；王来承认 3 回合."""
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        _cast(eng, "1509", "150902")
        assert math.isclose(_hp_lost(eng, "e1"), ATK * 2.8 * DMG * DEF_PEN3 * CRIT_EXP * WEAKEN,
                            rel_tol=1e-9), "主目标 2.8 倍"
        assert math.isclose(_hp_lost(eng, "e2"), ATK * 1.4 * DMG * DEF_PEN3 * CRIT_EXP * WEAKEN,
                            rel_tol=1e-9), "相邻 1.4 倍"
        assert "KINGS_ACKNOWLEDGEMENT" in _gil(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_gil(eng))["def_pen"], 0.3,
                            rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, sp0), "tbgd BPNeed=-1 不耗不产"
        assert math.isclose(_gil(eng).current_energy, 30.0)


class TestInterestChain:
    def test_gain_spd_hauteur_piqued_clear(self, compiled):
        """兴致链：队友行动 +1（SPD 烘焙 0.1/点 + 暴伤层 0.25/层）→ 队友开大 +1+2
        → 累计 10 进【来兴致了！】（普攻禁/战技通）→ 战技清空（SPD 归零、层数保留）."""
        eng = _make(compiled)
        gil = _gil(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(gil.resources["interest"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(gil)["spd"], 97 * 1.1, rel_tol=1e-9)
        assert math.isclose(gil.modifiers["HERO_HAUTEUR_STACKS"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(gil)["crit_dmg"], 0.7 + 0.25,
                            rel_tol=1e-9)
        _ult(eng, "ally", "ally_ult", 100)   # on_action +1 → on_ultimate +2 + 王来背负
        assert math.isclose(gil.resources["interest"], 4.0)
        assert "KINGS_BURDEN" in gil.modifiers
        es = eng.pipeline.effective_stats(gil)
        assert math.isclose(es["dmg_bonus"]["ultimate_dmg_boost"], 0.4, rel_tol=1e-9), "lv10 #3"
        for _ in range(5):
            _cast(eng, "ally", "ally_basic")
        assert math.isclose(gil.resources["interest"], 9.0)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(gil.resources["interest"], 10.0)
        assert "INTEREST_PIQUED" in gil.modifiers, "首次达 10 进来兴致了"
        basic = next(a for a in eng.actions_by_actor["1509"] if a.action_id == "150901")
        skill = next(a for a in eng.actions_by_actor["1509"] if a.action_id == "150902")
        assert eng._available_if_ok(gil, basic) is False, "状态内仅能施放战技"
        assert eng._available_if_ok(gil, skill) is True
        assert math.isclose(gil.modifiers["HERO_HAUTEUR_STACKS"].stacks, 6.0), "层数钳 6"
        assert math.isclose(eng.pipeline.effective_stats(gil)["crit_dmg"], 0.7 + 1.5,
                            rel_tol=1e-9)
        _cast(eng, "1509", "150902")   # 施放战技 → 清空兴致
        assert math.isclose(gil.resources["interest"], 0.0)
        assert math.isclose(eng.pipeline.effective_stats(gil)["spd"], 97.0, rel_tol=1e-9), (
            "清空后 SPD 烘焙归零（on_resource_gain 全路径重挂）")
        assert math.isclose(gil.modifiers["HERO_HAUTEUR_STACKS"].stacks, 6.0), (
            "暴伤层本场累计不清 + 清空事件 amount>0 门不误加")
        assert "INTEREST_PIQUED" in gil.modifiers, "状态持续整场"

    def test_multi_point_gain_stacks(self, compiled):
        """一次 +N 点 = +N 层（1509102 语义）：秘技 +3 → 3 层."""
        eng = _make(_compiled(pre_battle=True))
        gil = _gil(eng)
        assert math.isclose(gil.resources["interest"], 3.0)
        assert math.isclose(gil.modifiers["HERO_HAUTEUR_STACKS"].stacks, 3.0)
        assert math.isclose(eng.pipeline.effective_stats(gil)["crit_dmg"], 0.7 + 0.75,
                            rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(gil)["spd"], 97 * 1.3, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_damage_and_interest(self):
        """秘技：进战 200% 雷 AoE（#2）+ 3 兴致（#3）。战前装填结算先于 on_battle_start
        （引擎时序在案）——光环 atk/暴伤与兴致 HERO 层均不吃：atk 区仅行迹 1.18、
        暴伤基础 0.5 → 期望暴击区 1+0.237×0.5."""
        eng = _make(_compiled(pre_battle=True))
        crit_exp = 1 + 0.237 * 0.5
        lost = _hp_lost(eng, "e1")
        assert math.isclose(lost, 2 * (717.948 * 1.18) * DMG * DEF0 * crit_exp * WEAKEN,
                            rel_tol=1e-9)
        assert math.isclose(lost, _hp_lost(eng, "e2")), "全体同值"


class TestUltimate:
    def test_aoe_plus_10_bounces(self, compiled):
        """终结技 lv10：全体 4.0 + 10 段弹射 1.0（EXPECTED random 取首全落 e1）；
        削韧 40+2×10；弹射标 ultimate 吃王来背负."""
        eng = _make(compiled)
        _ult(eng, "1509", "150903", 360)
        assert math.isclose(_hp_lost(eng, "e1"),
                            ATK * DMG * DEF0 * CRIT_EXP * WEAKEN * (4.0 + 10 * 1.0),
                            rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng, "e2"),
                            ATK * DMG * DEF0 * CRIT_EXP * WEAKEN * 4.0, rel_tol=1e-9)
        assert math.isclose(eng.state.actors["e1"].toughness, 100 - 40 - 20)
        assert math.isclose(eng.state.actors["e2"].toughness, 100 - 40)
        assert math.isclose(_gil(eng).resources["interest"], 2.0), "1509101③ 自开大 +2"
        assert math.isclose(_gil(eng).current_energy, 5.0)

    def test_burden_boosts_bounces(self, compiled):
        """王来背负 0.4 入增伤区（1.08+0.4）：全体与弹射同吃（弹射 ultimate 身份勘正）.
        ally 开大喂兴致 +3（on_action+1/on_ultimate+2）→ HERO 3 层 → 暴伤 1.45."""
        eng = _make(compiled)
        _ult(eng, "ally", "ally_ult", 100)
        crit_exp = 1 + 0.237 * 1.45
        _ult(eng, "1509", "150903", 360)
        assert math.isclose(_hp_lost(eng, "e1"),
                            ATK * (DMG + 0.4) * DEF0 * crit_exp * WEAKEN * (4.0 + 10 * 1.0),
                            rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng, "e2"),
                            ATK * (DMG + 0.4) * DEF0 * crit_exp * WEAKEN * 4.0, rel_tol=1e-9)


class TestFollowUp:
    def test_tally_8_joint_attack(self, compiled):
        """天赋②：吉 8 次攻击 → 连携追击 4.0 AoE（lv10）+ 回 10 能 + 兴致 +3 + 计数清零；
        快照补偿 res+1>=8 第 8 次即触发，第 9 次不追."""
        eng = _make(compiled)
        for _ in range(7):
            _cast(eng, "1509", "150901")
        assert math.isclose(_gil(eng).resources["_atk_count"], 7.0)
        assert math.isclose(_hp_lost(eng, "e2"), 0.0), "前 7 次无追击"
        e1_before = _hp_lost(eng, "e1")
        _cast(eng, "1509", "150901")   # 第 8 次：普攻 + 追击
        assert math.isclose(_hp_lost(eng, "e1") - e1_before,
                            ATK * 1.0 * DMG * DEF0 * CRIT_EXP * WEAKEN
                            + ATK * 4.0 * DMG * DEF0 * CRIT_EXP * WEAKEN, rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng, "e2"),
                            ATK * 4.0 * DMG * DEF0 * CRIT_EXP * WEAKEN, rel_tol=1e-9)
        assert math.isclose(_gil(eng).resources["_atk_count"], 0.0), "触发即清零"
        assert math.isclose(_gil(eng).resources["interest"], 3.0), "追击后兴致 +3"
        assert math.isclose(_gil(eng).current_energy, 8 * 20 + 10), "8 普攻 + 追击回 10"
        assert math.isclose(_gil(eng).modifiers["HERO_HAUTEUR_STACKS"].stacks, 3.0)
        e2_before = _hp_lost(eng, "e2")
        _cast(eng, "1509", "150901")   # 第 9 次：计数 1 不触发
        assert math.isclose(_hp_lost(eng, "e2"), e2_before)
        assert math.isclose(_gil(eng).resources["_atk_count"], 1.0)

    def test_saber_coop(self):
        """Saber 协同：双主体计数（吉 4 + 替身 4）→ 替身第 4 击触发；Saber 固定回 120
        （代数 where 寻址 1014）；替身行动同时喂兴致（我方其他目标）.
        全打 e1：替身段 2400(2000×光环1.2)×0.5×0.8(风非弱点抗)×0.9×1.035(光环暴伤0.7)；
        追击时兴致 4（替身4击各喂1）→ HERO 4 层暴伤 1.7；替身能量 4×20+120=200."""
        eng = _make(_compiled(with_saber=True))
        saber = eng.state.actors["1014"]
        for _ in range(4):
            _cast(eng, "1509", "150901")
        for _ in range(3):
            _cast(eng, "1014", "saber_basic")
        assert math.isclose(saber.current_energy, 3 * 20.0), "替身自身普攻回能"
        e1_before = _hp_lost(eng, "e1")
        e2_before = _hp_lost(eng, "e2")
        _cast(eng, "1014", "saber_basic")   # 第 8 击（替身）→ 触发
        saber_hit = 2400 * 1.0 * DEF0 * 0.8 * WEAKEN * (1 + 0.05 * 0.7)
        fua = ATK * 4.0 * DMG * DEF0 * (1 + 0.237 * 1.7) * WEAKEN
        assert math.isclose(_hp_lost(eng, "e1") - e1_before, saber_hit + fua, rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng, "e2") - e2_before, fua, rel_tol=1e-9)
        assert math.isclose(saber.current_energy, 4 * 20.0 + 120.0), "Saber 固定回 120"
        # 兴致：替身 4 次行动 +4、追击 +3（吉自己行动不喂）
        assert math.isclose(_gil(eng).resources["interest"], 7.0)


class TestEidolons:
    def test_e1_share_def_pen_atk_energy(self):
        """E1：队友同享 def_pen 0.3（排自身——吉不双倍）+ 自 atk +60% + 战技回 40."""
        eng = _make(_compiled(eidolon=1))
        _cast(eng, "1509", "150902")
        gil = _gil(eng)
        assert math.isclose(eng.pipeline.effective_stats(gil)["def_pen"], 0.3, rel_tol=1e-9), (
            "排自身——不自叠 0.6")
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["def_pen"], 0.3, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(gil)["atk"],
                            717.948 * (1.38 + 0.6), rel_tol=1e-9), "王来承认·攻 +60%"
        assert math.isclose(gil.current_energy, 30.0 + 40.0), "战技回 30 + E1 固定 40（吃 ERR 1.0）"

    def test_e2_battle_start_and_ult_interest(self):
        """E2：开战 +5 兴致（SPD/暴伤层联动）+ 自开大 +5."""
        eng = _make(_compiled(eidolon=2))
        gil = _gil(eng)
        assert math.isclose(gil.resources["interest"], 5.0)
        assert math.isclose(eng.pipeline.effective_stats(gil)["spd"], 97 * 1.5, rel_tol=1e-9)
        assert math.isclose(gil.modifiers["HERO_HAUTEUR_STACKS"].stacks, 5.0)
        _ult(eng, "1509", "150903", 360)
        assert math.isclose(gil.resources["interest"], 5.0 + 5.0 + 2.0), "E2 +5 + 1509101 +2"
        assert "INTEREST_PIQUED" in gil.modifiers, "12≥10 进状态"

    def test_e3_level_overrides(self):
        """E3：战技 lv12（主 3.08/邻 1.54、def_pen 0.33 → 1000/1670）+ 普攻 lv7 1.1.
        eidolon=3 联动 E2：开战兴致 5 → HERO 5 层 → 暴伤 1.95（期望暴击区 1+0.237×1.95）."""
        crit_exp = 1 + 0.237 * 1.95
        eng = _make(_compiled(eidolon=3))
        _cast(eng, "1509", "150901")
        assert math.isclose(_hp_lost(eng, "e1"), ATK * 1.1 * DMG * DEF0 * crit_exp * WEAKEN,
                            rel_tol=1e-9), "普攻 lv7=1.1（勘正⑯——非 lv8）"
        eng2 = _make(_compiled(eidolon=3))
        _cast(eng2, "1509", "150902")
        assert math.isclose(_hp_lost(eng2, "e1"),
                            ATK * 3.08 * DMG * DEF_PEN33 * crit_exp * WEAKEN, rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng2, "e2"),
                            ATK * 1.54 * DMG * DEF_PEN33 * crit_exp * WEAKEN, rel_tol=1e-9)
        assert math.isclose(eng2.pipeline.effective_stats(_gil(eng2))["def_pen"], 0.33,
                            rel_tol=1e-9)

    def test_e4_err(self):
        """E4：能量恢复效率 +20% → 面板 1.2，普攻回 20×1.2=24."""
        eng = _make(_compiled(eidolon=4))
        assert math.isclose(eng.pipeline.effective_stats(_gil(eng))["energy_regen"], 1.2,
                            rel_tol=1e-9)
        _cast(eng, "1509", "150901")
        assert math.isclose(_gil(eng).current_energy, 24.0)

    def test_e5_level_overrides(self):
        """E5：终结技 lv12（全体 4.4 + 弹射 1.1）+ 天赋 lv12（王来背负 0.44 / 追击 4.4）.
        eidolon=5 联动 E2：开战 5 + ally 开大 +3 → 兴致 8 → HERO 钳 6 → 暴伤 2.2；
        追击例兴致恒 5（自己行动不喂）→ 暴伤 1.95."""
        eng = _make(_compiled(eidolon=5))
        _ult(eng, "ally", "ally_ult", 100)
        assert math.isclose(
            eng.pipeline.effective_stats(_gil(eng))["dmg_bonus"]["ultimate_dmg_boost"],
            0.44, rel_tol=1e-9), "天赋 lv12 #3"
        crit_exp = 1 + 0.237 * 2.2
        _ult(eng, "1509", "150903", 360)
        assert math.isclose(_hp_lost(eng, "e1"),
                            ATK * (DMG + 0.44) * DEF0 * crit_exp * WEAKEN * (4.4 + 10 * 1.1),
                            rel_tol=1e-9)
        assert math.isclose(_hp_lost(eng, "e2"),
                            ATK * (DMG + 0.44) * DEF0 * crit_exp * WEAKEN * 4.4, rel_tol=1e-9)
        eng2 = _make(_compiled(eidolon=5))
        crit_exp_f = 1 + 0.237 * 1.95
        for _ in range(8):
            _cast(eng2, "1509", "150901")
        assert math.isclose(_hp_lost(eng2, "e2"),
                            ATK * 4.4 * DMG * DEF0 * crit_exp_f * WEAKEN, rel_tol=1e-9), (
            "追击 lv12 #1=4.4")

    def test_e6_respen_golden_rule_and_bounces(self):
        """E6：res_pen 0.2 team（抗性区 1.0→1.2）+ 黄金律（队友开大 +1 钳 3、自开大消耗
        清零）+ 弹射 +80% 等值 10 段 0.88（lv12 联动）——总段 全体4.4 + 10×1.1 + 10×0.88.
        eidolon=6 联动：E2 开战 5 + ally 4 大 +12 → HERO 钳 6（暴伤 2.2）；王来背负
        lv12 0.44 在挂（增伤区 1.08+0.44）."""
        eng = _make(_compiled(eidolon=6))
        gil = _gil(eng)
        assert math.isclose(eng.pipeline.effective_stats(gil)["res_pen"], 0.2, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"],
                            0.2, rel_tol=1e-9), "team scope"
        for _ in range(4):
            _ult(eng, "ally", "ally_ult", 100)
        assert math.isclose(gil.resources["golden_rule"], 3.0), "最多累计 3 点（钳）"
        e1_before = _hp_lost(eng, "e1")
        _ult(eng, "1509", "150903", 360)
        assert math.isclose(gil.resources["golden_rule"], 0.0), "自开大消耗全部"
        crit_exp = 1 + 0.237 * 2.2
        assert math.isclose(_hp_lost(eng, "e1") - e1_before,
                            ATK * (DMG + 0.44) * DEF0 * crit_exp * WEAKEN * 1.2
                            * (4.4 + 10 * 1.1 + 10 * 0.88),
                            rel_tol=1e-9), "全体 4.4 + 主弹射 10×1.1 + E6 10×0.88（抗区 1.2）"
        assert math.isclose(eng.state.actors["e1"].toughness, 100 - 40 - 20), (
            "E6 额外段不削韧（倍率提高非额外段）")
