"""开拓者•存护 8004 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 灼热意志叠层/
换技能互斥/天赋盾/减伤+嘲讽/A2·A4·A6/星魂全链 → 手算全等.

过堂十二件（fixture 头注同录）：星魂幻名六连 / forced_taunt 收编 / dmg_dmg_reduction
双件收编 / 削韧三方对轴收编 / 行迹属性收编 / $self.def_ / shield param 随档 /
E5 cap10 误读 / 灼热意志幻名 / modifier_type·damage_type / resource_gain 压缩 /
available_if res_ 平铺误拼。

口径常数：火主白值 atk 601.524、def 606.375、hp 1241.856、crit 0.05/0.5
（期望暴击区 1.025）；行迹 atk+18%/def+35%/hp+10% → 有效面板 atk 709.79832、
def 818.60625、max_hp 1366.0416。默认档位：普攻 lv6、战技/终结技/天赋 lv10。
假人 def 1000 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9；
角色承伤：非弱点属性抗性区 0.8（1107 克拉拉先例）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

TB_ATK = 601.524
TB_DEF = 606.375
TB_HP = 1241.8560000000002
EFF_ATK = TB_ATK * 1.18          # 行迹 atk_pct 0.18 收编
EFF_DEF = TB_DEF * 1.35          # 行迹 def_pct 0.35 收编
EFF_HP = TB_HP * 1.10            # 行迹 hp_pct 0.10 收编
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)           # 攻击侧：防御区×未击破×期望暴击（抗性 1.0）
SHIELD10 = 0.06 * EFF_DEF + 80.0           # 天赋盾 lv10 = 6% DEF + 80


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8004", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8004", "technique": "800407"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 4):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _tb(eng):
    return eng.state.actors["8004"]


def _act(eng, aid):
    return next(x for x in eng.actions_by_actor["8004"] if x.action_id == aid)


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
    st = _tb(eng)
    st.current_energy = 120.0
    ult = _act(eng, "800403")
    assert eng._fire_ultimate(st, ult) is True


def _hit_tb(eng, source="e1"):
    eng.bus.emit("after_being_hit", {
        "target": "8004", "source": source, "amount": 100.0,
        "action_type": "basic", "damage_type": "physical"}, eng.state)


class TestTrailblazerCompile:
    def test_actions_resources_levels(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["8004"]}
        assert set(acts) == {"800401", "800402", "800403", "800408"}
        assert acts["800403"].energy_cost == 120
        assert acts["800401"].available_if and acts["800408"].available_if, "换技能互斥双半在"
        decls = compiled.resource_decls_by_actor["8004"]
        assert decls["magma_will"]["max"] == 8
        assert decls["_eb_free"]["max"] == 1
        lv = next(m for m in compiled.build_team if m.actor_id == "8004").skill_levels
        assert lv == {"basic": 6, "skill": 10, "ultimate": 10, "talent": 10}

    def test_trace_stat_panel(self, compiled):
        """行迹属性收编（勘正⑤）：atk×1.18 / def×1.35 / hp×1.10."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_tb(eng))
        assert math.isclose(eff["atk"], EFF_ATK, rel_tol=1e-9)
        assert math.isclose(eff["def_"], EFF_DEF, rel_tol=1e-9)
        assert math.isclose(eff["hp"], EFF_HP, rel_tol=1e-9)


class TestBasicAndStacks:
    def test_basic_damage_stack_energy_sp(self, compiled):
        """普攻 lv6=100% ATK：709.79832×Z；+1 层灼热意志（resource_gain 压缩实证）、
        回能 20、产 1 点."""
        eng = _make(compiled)
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        sp0 = eng.state.skill_points
        hp1 = e1.current_hp
        _cast(eng, "8004", "800401")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * EFF_ATK * Z, rel_tol=1e-9)
        assert math.isclose(st.resources["magma_will"], 1.0)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, sp0 + 1.0)

    def test_swap_available_if(self, compiled):
        """换技能硬闸：4 层后 800401 不可用、800408 可用（available_if 双半）."""
        eng = _make(compiled)
        st = _tb(eng)
        for _ in range(4):
            _cast(eng, "8004", "800401")
        assert math.isclose(st.resources["magma_will"], 4.0)
        assert eng._available_if_ok(st, _act(eng, "800401")) is False
        assert eng._available_if_ok(st, _act(eng, "800408")) is True


class TestEnhancedBasic:
    def test_blast_damage_consume_heal(self, compiled):
        """强化普攻 lv6：主 135% / 相邻 54%；耗 4 层（闩未置位）；A4 回血 5% Max；
        回能 30；天赋盾全队 6% DEF+80."""
        eng = _make(compiled)
        st = _tb(eng)
        st.resources["magma_will"] = 4.0
        st.current_hp = 100.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8004", "800408", target=e1)
        assert math.isclose(hp1 - e1.current_hp, 1.35 * EFF_ATK * Z, rel_tol=1e-9), "主目标"
        assert math.isclose(hp2 - e2.current_hp, 0.54 * EFF_ATK * Z, rel_tol=1e-9), "相邻"
        assert math.isclose(st.resources["magma_will"], 0.0), "耗 4 层"
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.current_hp, 100.0 + 0.05 * EFF_HP, rel_tol=1e-9), (
            "A4 8004102 回血 5% Max HP")
        for aid in ("8004", "ally"):
            sh = eng.state.actors[aid].shields
            assert sh and math.isclose(sh[0].remaining, SHIELD10, rel_tol=1e-9), (
                f"{aid} 天赋盾 lv10 = 0.06×{EFF_DEF}+80")


class TestSkill:
    def test_dr_taunt_stack_sp(self, compiled):
        """战技：耗 1 点/回能 30/+1 层；自体减伤 50%（dmg_dmg_reduction 收编）+
        A2 全队 15%（乘算折叠 0.575）；嘲讽双假人 forced_taunt."""
        eng = _make(compiled)
        st = _tb(eng)
        ally = eng.state.actors["ally"]
        sp0 = eng.state.skill_points
        _cast(eng, "8004", "800402")
        assert math.isclose(eng.state.skill_points, sp0 - 1.0)
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.resources["magma_will"], 1.0)
        assert math.isclose(st.modifiers["TB_FIRE_SKILL_DR"].stat_effects["dmg_dmg_reduction"],
                            0.5, rel_tol=1e-9), "lv10 自体减伤 50%"
        dr_self = eng.pipeline.effective_stats(st)["dmg_bonus"]["dmg_reduction"]
        assert math.isclose(dr_self, 1 - (1 - 0.5) * (1 - 0.15), rel_tol=1e-9), (
            "自体 50%×A2 15% 乘算折叠 = 0.575")
        dr_ally = eng.pipeline.effective_stats(ally)["dmg_bonus"]["dmg_reduction"]
        assert math.isclose(dr_ally, 0.15, rel_tol=1e-9), "A2 8004101 全队 15%"
        for eid in ("e1", "e2"):
            assert eng.state.actors[eid].modifiers["TB_FIRE_TAUNT"].forced_taunt is True
        assert eng._pick_ally_target(eng.state.actors["e1"]) is st, "强制嘲讽覆盖层"

    def test_dr_shield_chain_vs_enemy_hit(self, compiled):
        """全链承伤：敌 1000 物理重击 → 防御区×0.8（非弱点抗性）×0.9×期望暴击×(1-0.575)
        减伤 → 天赋盾先吸 129.116375、溢出扣血."""
        eng = _make(compiled)
        st = _tb(eng)
        _cast(eng, "8004", "800402")   # 减伤+A2+嘲讽+天赋盾 129.116375
        from hsr_nous.sim_schema.action import Action
        eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
            action_id="e_hit", name="重击", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 1.0}])]}
        def_zone = 1 - EFF_DEF / (EFF_DEF + 1000.0)
        raw = 1000 * def_zone * 0.8 * 0.9 * (1 + 0.05 * 0.5) * (1 - 0.575)
        hp0 = st.current_hp
        eng._enemy_turn(eng.state.actors["e1"])
        absorbed = min(SHIELD10, raw)
        assert math.isclose(hp0 - st.current_hp, raw - absorbed, rel_tol=1e-9), (
            "盾吸后溢出才扣血")
        assert math.isclose(st.resources["magma_will"], 2.0), "受击 +1 层（天赋受击叠层）"


class TestUltimate:
    def test_aoe_damage_free_enhance_latch(self, compiled):
        """终结技 lv10：双假人各 (100% ATK + 150% DEF)×Z；返 5 能；挂 _eb_free 闩 →
        0 层也可强化普攻且不耗层，用后闩清."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        want = (1.0 * EFF_ATK + 1.5 * EFF_DEF) * Z
        assert math.isclose(hp1 - e1.current_hp, want, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, want, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 5.0), "开大返还 5"
        assert math.isclose(st.resources["_eb_free"], 1.0), "免费强化闩置位"
        assert eng._available_if_ok(st, _act(eng, "800408")) is True, "闩开路（0 层可用）"
        assert eng._available_if_ok(st, _act(eng, "800401")) is False
        st.resources["magma_will"] = 0.0
        hp1 = e1.current_hp
        _cast(eng, "8004", "800408", target=e1)
        assert math.isclose(hp1 - e1.current_hp, 1.35 * EFF_ATK * Z, rel_tol=1e-9)
        assert math.isclose(st.resources["magma_will"], 0.0), "免费强化不耗层"
        assert math.isclose(st.resources["_eb_free"], 0.0), "闩已清"
        assert eng._available_if_ok(st, _act(eng, "800401")) is True


class TestTalent:
    def test_hit_stacks_and_cap(self, compiled):
        """受击叠层：after_being_hit +1；8 层封顶（custom_resources max 钳制）."""
        eng = _make(compiled)
        st = _tb(eng)
        _hit_tb(eng)
        assert math.isclose(st.resources["magma_will"], 1.0)
        st.resources["magma_will"] = 8.0
        _hit_tb(eng)
        assert math.isclose(st.resources["magma_will"], 8.0), "8 层封顶"

    def test_shield_refresh_not_stacked(self, compiled):
        """护盾整换不叠（引擎现状口径 + KQM 'Shields do not stack' 同向——待收①在案）：
        两次动作后盾池仍单实例、值为新烘."""
        eng = _make(compiled)
        st = _tb(eng)
        _cast(eng, "8004", "800401")
        _cast(eng, "8004", "800401")
        own = [s for s in st.shields if s.shield_id == "TB_FIRE_TALENT_SHIELD"]
        assert len(own) == 1 and math.isclose(own[0].remaining, SHIELD10, rel_tol=1e-9)


class TestTraceA6:
    def test_shielded_turn_start_atk_energy(self, compiled):
        """A6 8004103：有盾回合开始 → ATK+15%（601.524×1.33）+ 回能 5，owner_turn_end 失效；
        无盾不触发."""
        eng = _make(compiled)
        st = _tb(eng)
        eng.bus.emit("on_turn_start", {"actor": "8004"}, eng.state)
        assert "TB_A6_ATK" not in st.modifiers, "无盾不触发"
        _cast(eng, "8004", "800401")   # 天赋盾上身
        eng.bus.emit("on_turn_start", {"actor": "8004"}, eng.state)
        assert "TB_A6_ATK" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            TB_ATK * (1.18 + 0.15), rel_tol=1e-9)
        assert math.isclose(st.current_energy, 20.0 + 5.0), "普攻 20 + A6 5"
        eng._tick_modifiers(st, "owner_turn_end")
        assert "TB_A6_ATK" not in st.modifiers, "行动结束即失效"
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], EFF_ATK, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_shield(self):
        """秘技 800407：开战自盾 30% DEF + 384（单档字面值）."""
        eng = _make(_compiled(pre_battle=True))
        st = _tb(eng)
        assert "TB_FIRE_TECH_SHIELD" in st.modifiers
        assert math.isclose(st.shields[0].remaining, 0.3 * EFF_DEF + 384.0, rel_tol=1e-9)


class TestEidolons:
    def test_e1_additional_def_damage(self):
        """E1 大地芯髓的鸣动：普攻追加 25% DEF / 强化普攻追加 50% DEF 火伤
        （category additional + $self.def_ 勘正实证）；强化段只打主目标."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8004", "800401")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.0 * EFF_ATK + 0.25 * EFF_DEF) * Z, rel_tol=1e-9)
        st.resources["magma_will"] = 4.0
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8004", "800408", target=e1)
        assert math.isclose(hp1 - e1.current_hp,
                            (1.35 * EFF_ATK + 0.5 * EFF_DEF) * Z, rel_tol=1e-9), "主目标双段"
        assert math.isclose(hp2 - e2.current_hp, 0.54 * EFF_ATK * Z, rel_tol=1e-9), (
            "相邻不吃 E1 追加段")

    def test_e2_second_shield_layer(self):
        """E2 古老寒铁的坚守：天赋盾外第二盾层 = 2% DEF + 27（独立分层建模在案）."""
        eng = _make(_compiled(eidolon=2))
        _cast(eng, "8004", "800401")
        ally = eng.state.actors["ally"]
        pool = {s.shield_id: s.remaining for s in ally.shields}
        assert math.isclose(pool["TB_FIRE_TALENT_SHIELD"], SHIELD10, rel_tol=1e-9)
        assert math.isclose(pool["TB_E2_SHIELD"], 0.02 * EFF_DEF + 27.0, rel_tol=1e-9)

    def test_e3_shield_and_dr_lv12(self):
        """E3 天赋+2：盾 lv12 = 6.4% DEF + 89（shield param 随档实证）；战技+2：
        自体减伤 lv12 = 52%."""
        eng = _make(_compiled(eidolon=3))
        st = _tb(eng)
        _cast(eng, "8004", "800402")
        assert math.isclose(st.shields[0].remaining, 0.064 * EFF_DEF + 89.0, rel_tol=1e-9)
        assert math.isclose(st.modifiers["TB_FIRE_SKILL_DR"].stat_effects["dmg_dmg_reduction"],
                            0.52, rel_tol=1e-9)

    def test_e4_battle_start_stacks(self):
        """E4 驻留文明的誓言：开战 4 层 → 强化普攻立即可用."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        assert math.isclose(st.resources["magma_will"], 4.0)
        assert eng._available_if_ok(st, _act(eng, "800408")) is True

    def test_e5_ult_lv12_basic_lv7(self):
        """E5：终结技 lv12 = 110% ATK + 165% DEF；普攻 lv7 = 110%（cap10 官方语义在案；
        eidolon=5 含 E1 → 普攻带 25% DEF 追加段）."""
        eng = _make(_compiled(eidolon=5))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8004", "800401")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.1 * EFF_ATK + 0.25 * EFF_DEF) * Z, rel_tol=1e-9), "普攻 lv7+E1"
        hp1 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (1.1 * EFF_ATK + 1.65 * EFF_DEF) * Z, rel_tol=1e-9), "终结技 lv12"

    def test_e6_def_stacks_baked(self):
        """E6 永屹城垣的壁垒：强化普攻/终结技后 DEF+10% 叠 3（计数层+烘焙值双件；
        同钩先叠后烘当次即吃）；eidolon=6 含 E4 → 开战 4 层可直接强化."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        _cast(eng, "8004", "800408", target=e1)   # E4 开战 4 层 → 首次强化
        assert math.isclose(st.modifiers["TB_E6_STACKS"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"],
                            TB_DEF * (1.35 + 0.1), rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(st.modifiers["TB_E6_STACKS"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"],
                            TB_DEF * (1.35 + 0.2), rel_tol=1e-9)
        st.resources["magma_will"] = 8.0
        _cast(eng, "8004", "800408", target=e1)
        _cast(eng, "8004", "800408", target=e1)
        assert math.isclose(st.modifiers["TB_E6_STACKS"].stacks, 3.0), "3 层封顶"
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"],
                            TB_DEF * (1.35 + 0.3), rel_tol=1e-9)
