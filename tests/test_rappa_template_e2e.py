"""乱破 1317 模板端到端对轴（验收型批·单轨）：真模板 YAML → 编译 →
印结状态机/强化普攻三段/天赋充能/行迹三件/星魂全链 → 手算全等.

口径常数：乱破 atk 白值 717.948（行迹 atk_pct 0.28 → 有效 918.97344）、spd 96+9=105、
crit 0.05/0.5（期望暴击区 1.025）、max_energy 140；行迹击破特攻 0.133。
强化普攻 lv6 [1.0,0.5,1.0]（E5 lv7 [1.08,0.54,1.08]）；终结技 lv10 WBE 0.5/BE 0.3
（E5 lv12 BE 0.34）。假人 def 1000 → 防御区 0.5（E1 印结内 def_pen 0.15 → 1000/1850）；
弱点匹配虚数 → 抗性区 1.0；未击破 0.9/已击破 1.0。
削韧（tbgd）：强化普攻主 10/邻 5/群 5——印结 WBE 池 2 → ×1.5（15/7.5/7.5）。
击破基数 = 3767.5533×0.5（虚数）×(0.5+max_toughness/40)；超击破基数 = 376.75533×有效削韧。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---- 手算常数（全部推导见模块 docstring 与各行注释）----
ATK_W = 717.948                  # 白值（管线对轴）
ATK_E = ATK_W * 1.28             # 有效面板（行迹 atk_pct 0.28）
CRIT_ZONE = 1 + 0.05 * 0.5       # 期望暴击区 1.025
DEF_ZONE = 0.5                   # 假人 def 1000：1000/(1000+1000)
DEF_ZONE_E1 = 1000 / 1850        # E1 def_pen 0.15：1000/(1000×0.85+1000)
BE_BASE = 0.133                  # 行迹击破特攻
BE_SEAL = BE_BASE + 0.3          # 印结 lv10 +0.3
BE_SEAL_E5 = BE_BASE + 0.34      # 印结 lv12（E5）+0.34


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1317", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1317", "technique": "131707"}]
    return build


def _stage(toughness: float = 9999):
    """双假人（9999 满韧不破 / 20 低韧一触即破两档）；弱点虚数 → 抗性区 1.0."""
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人1", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
         "max_toughness": toughness, "weakness": ["imaginary"]},
        {"actor_id": "e2", "name": "假人2", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
         "max_toughness": toughness, "weakness": ["imaginary"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, toughness: float = 9999):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle),
                             _stage(toughness), template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _rappa(eng):
    return eng.state.actors["1317"]


def _cast(eng, aid, *, target="e1"):
    st = _rappa(eng)
    a = next(x for x in eng.actions_by_actor["1317"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "1317", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _rappa(eng)
    st.current_energy = 140.0
    ult = next(a for a in eng.actions_by_actor["1317"] if a.action_id == "131703")
    assert eng._fire_ultimate(st, ult) is True
    return st


def _basic_expected(scaling_main: float, scaling_adj: float, def_zone: float = DEF_ZONE):
    """强化普攻整次（9999 满韧双假人，全未击破）：段1/2 主+邻、段3 双全体——
    主 4 段（段1/2 主 + 段3 两体）+ 邻 2 段（段1/2 邻）."""
    main = ATK_E * scaling_main * def_zone * 1.0 * 0.9 * CRIT_ZONE
    adj = ATK_E * scaling_adj * def_zone * 1.0 * 0.9 * CRIT_ZONE
    return 4 * main + 2 * adj


class TestRappaCompile:
    def test_actions_resources(self, compiled):
        """散装零成本 action 全摘除：只剩 普攻/战技/终结技/强化普攻 四件."""
        acts = {a.action_id for a in compiled.actions_by_actor["1317"]}
        assert acts == {"131701", "131702", "131703", "131718"}
        decls = compiled.resource_decls_by_actor["1317"]
        assert decls["chroma_ink"]["max"] == 3
        assert decls["talent_stacks"]["max"] == 10     # E6 +5 走 max_override，非常驻 15
        assert decls["_sealform"]["max"] == 1

    def test_trace_stats(self, compiled):
        """行迹平铺：spd 96+9=105 入白值；atk_pct 0.28/BE 0.133 入 trace_stat_effects."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_rappa(eng))
        assert math.isclose(eff["spd"], 105.0, rel_tol=1e-9)
        assert math.isclose(eff["atk"], ATK_E, rel_tol=1e-9)
        assert math.isclose(eff["break_effect"], BE_BASE, rel_tol=1e-9)


class TestSealform:
    def test_ult_enters_sealform(self, compiled):
        """终结技：能量 140→5、闩/彩墨置位、WBE/BE 烘焙（lv10 0.5/0.3）、额外回合入队."""
        eng = _make(compiled)
        st = _ult(eng)
        assert math.isclose(st.current_energy, 5.0), "140 全扣 + 终结技回 5（tbgd）"
        assert st.resources["_sealform"] == 1.0 and st.resources["chroma_ink"] == 3.0
        mod = st.modifiers["RAPPA_SEALFORM"]
        assert math.isclose(mod.stat_effects["weakness_break_efficiency_boost"], 0.5)
        assert math.isclose(mod.stat_effects["break_effect"], 0.3)
        handles = [h for h, _kind in eng.scheduler._extra_queue]
        assert eng.scheduler._handles["1317"] in handles, "额外回合（grant_extra_turn）"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["break_effect"], BE_SEAL, rel_tol=1e-9)
        assert math.isclose(eff["weakness_break_efficiency_boost"], 0.5, rel_tol=1e-9)

    def test_available_if_mutex(self, compiled):
        """available_if 互斥：印结外禁 131718；印结内禁普攻/战技/终结技（EN 双证）."""
        eng = _make(compiled)
        st = _rappa(eng)
        avail = {a.action_id: eng._available_if_ok(st, a) for a in eng.actions_by_actor["1317"]}
        assert avail == {"131701": True, "131702": True, "131703": True, "131718": False}
        _ult(eng)
        avail = {a.action_id: eng._available_if_ok(st, a) for a in eng.actions_by_actor["1317"]}
        assert avail == {"131701": False, "131702": False, "131703": False, "131718": True}, (
            "印结内终结技同禁——官方 EN \"Skill and Ultimate cannot be used\"")

    def test_enhanced_basic_three_segments(self, compiled):
        """强化普攻 instances 3：段1/2 blast+段3 aoe 伤害手算全等；削韧 15/7.5/7.5（WBE 池2）."""
        eng = _make(compiled)
        _ult(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        d0 = eng.state.total_damage
        _cast(eng, "131718")
        expected = _basic_expected(1.0, 0.5)   # lv6：主 1.0/邻 0.5
        assert math.isclose(eng.state.total_damage - d0, expected, rel_tol=1e-9), (
            f"三段合计 {expected}（主 423.8764992×4 + 邻 211.9382496×2）")
        assert math.isclose(e1.toughness, 9999 - 37.5), "主 10×1.5 ×2 + 群 5×1.5 = 37.5"
        assert math.isclose(e2.toughness, 9999 - 22.5), "邻 5×1.5 ×2 + 群 5×1.5 = 22.5"

    def test_ink_consume_and_exit(self, compiled):
        """彩墨逐次消耗（快照判退补偿 -1）：3 次强化普攻后退出印结、摘增益、行动解禁."""
        eng = _make(compiled)
        st = _ult(eng)
        _cast(eng, "131718")
        assert st.resources["chroma_ink"] == 2.0 and st.resources["_sealform"] == 1.0
        _cast(eng, "131718")
        assert st.resources["chroma_ink"] == 1.0 and st.resources["_sealform"] == 1.0
        _cast(eng, "131718")
        assert st.resources["chroma_ink"] == 0.0 and st.resources["_sealform"] == 0.0
        assert "RAPPA_SEALFORM" not in st.modifiers, "退出印结摘增益"
        assert math.isclose(st.current_energy, 65.0), "5 + 20×3（强化普攻行动级 20/次）"
        avail = {a.action_id: eng._available_if_ok(st, a) for a in eng.actions_by_actor["1317"]}
        assert avail["131701"] and avail["131702"] and avail["131703"] and not avail["131718"]


class TestBreakChain:
    def test_talent_trace_break_full_chain(self):
        """20 韧假人一次强化普攻全链：段2 破 e1（击破伤害吃枯叶 1.02）→ 段3 超击破
        （海鸣 0.6 转化）→ 段3 再破 e2；充能 4（天赋+魔天 ×2 破）、魔天回能 20、禁锢双挂."""
        eng = _make(_compiled(toughness=20))
        st = _ult(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        d0 = eng.state.total_damage
        _cast(eng, "131718")
        # 手算（枯叶值 = 0.02：有效 ATK 918.97 < 2400 → 无附加档）
        h_main = ATK_E * 1.0 * DEF_ZONE * 0.9 * CRIT_ZONE            # 段1/2 主（未击破 0.9）
        h_adj = ATK_E * 0.5 * DEF_ZONE * 0.9 * CRIT_ZONE             # 段1/2 邻
        brk = (3767.5533 * 0.5 * (0.5 + 20 / 40)                     # 击破基数 1883.77665
               * (1 + BE_SEAL) * DEF_ZONE * 1.02)                    # ×BE 1.433 ×防御 ×枯叶 1.02
        h3_e1 = ATK_E * 1.0 * DEF_ZONE * 1.0 * CRIT_ZONE             # 段3 e1（已击破 1.0；枯叶限定击破族直击不吃）
        sb_e1 = (376.75533 * 7.5                                     # 超击破基数（名义削韧 5×1.5）
                 * 0.6 * (1 + BE_SEAL) * DEF_ZONE * 1.02)            # ×转化 0.6 ×BE ×防御 ×枯叶
        h3_e2 = ATK_E * 1.0 * DEF_ZONE * 0.9 * CRIT_ZONE             # 段3 e2（伤害时未击破；破在伤害后）
        expected = 2 * h_main + 2 * h_adj + brk + h3_e1 + sb_e1 + h3_e2 + brk
        assert math.isclose(eng.state.total_damage - d0, expected, rel_tol=1e-9), (
            f"全链合计 {expected}（破 e1 {brk} + 超击破 {sb_e1} + 破 e2 {brk} + 直伤五段）")
        assert e1.broken and e2.broken
        assert math.isclose(st.resources["talent_stacks"], 4.0), "天赋+1、魔天+1 ×2 破"
        assert math.isclose(st.current_energy, 45.0), "5（终结技）+ 20（行动）+ 10×2（魔天）"
        assert math.isclose(e1.modifiers["RAPPA_WITHERED_LEAF"].stat_effects["vulnerability"],
                            0.02, rel_tol=1e-9), "枯叶烘焙：918.97<2400 → 仅底数 2%"
        assert any(m.control_kind == "imprison" for m in e1.modifiers.values()), "虚数击破禁锢"
        assert any(m.control_kind == "imprison" for m in e2.modifiers.values())

    def test_withered_leaf_atk_bake(self):
        """枯叶 ATK 条件档烘焙：atk +2000 → 2918.97，(2918.97-2400)//100=5 → 2%+5%=7%；
        击破伤害 1883.77665×1.433×0.5×1.07."""
        eng = _make(_compiled(toughness=20))
        st = _ult(eng)
        eng._apply_modifier(st, Modifier(
            modifier_id="TEST_ATK", name="测试攻击", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"atk": 2000.0}))
        e1 = eng.state.actors["e1"]
        _cast(eng, "131718")
        leaf = e1.modifiers["RAPPA_WITHERED_LEAF"]
        assert math.isclose(leaf.stat_effects["vulnerability"], 0.07, rel_tol=1e-9), (
            "烘焙 = 0.02 + min(0.08, (2918.97344-2400)//100 × 0.01) = 0.07（挂点快照）")


class TestTechnique:
    def test_pre_battle_technique(self):
        """秘技：入战回能 10 + 30 无视弱点削韧（toughness-only；击破伤害段待收→0 伤害）."""
        eng = _make(_compiled(pre_battle=True, toughness=100))
        st = _rappa(eng)
        assert math.isclose(st.current_energy, 10.0)
        assert math.isclose(eng.state.actors["e1"].toughness, 70.0)
        assert math.isclose(eng.state.actors["e2"].toughness, 70.0)
        assert eng.state.total_damage == 0.0, "200%/180% 虚数击破伤害待收——不脑补直伤"


class TestEidolons:
    def test_e1_def_pen_and_exit_energy(self):
        """E1：印结内 def_pen 0.15（防御区 1000/1850）+ 退出印结回能 20."""
        eng = _make(_compiled(eidolon=1))
        st = _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.15, rel_tol=1e-9)
        d0 = eng.state.total_damage
        _cast(eng, "131718")
        assert math.isclose(eng.state.total_damage - d0,
                            _basic_expected(1.0, 0.5, DEF_ZONE_E1), rel_tol=1e-9)
        _cast(eng, "131718")
        _cast(eng, "131718")   # 第 3 次耗尽退出
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.0, abs_tol=1e-9)
        assert math.isclose(st.current_energy, 85.0), "5 + 20×3 + E1 退出 20"

    def test_e4_team_spd(self):
        """E4：印结内我方全体速度 +12%（含自身 117.6/辅手 100.8），退出印结全队摘除."""
        eng = _make(_compiled(eidolon=4))
        st = _ult(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 105 * 1.12, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 90 * 1.12, rel_tol=1e-9)
        _cast(eng, "131718")
        _cast(eng, "131718")
        _cast(eng, "131718")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 105.0, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], 90.0, rel_tol=1e-9), (
            "remove_modifier target all_allies——draft 缺省 self 会留队友件")

    def test_e5_ult_lv12_and_basic_lv7(self):
        """E5（联动 E1）：印结 BE = 0.133+0.34（lv12）；强化普攻 lv7 [1.08,0.54] 实取."""
        eng = _make(_compiled(eidolon=5))
        st = _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            BE_SEAL_E5, rel_tol=1e-9)
        mod = st.modifiers["RAPPA_SEALFORM"]
        assert math.isclose(mod.stat_effects["break_effect"], 0.34, rel_tol=1e-9)
        d0 = eng.state.total_damage
        _cast(eng, "131718")
        assert math.isclose(eng.state.total_damage - d0,
                            _basic_expected(1.08, 0.54, DEF_ZONE_E1), rel_tol=1e-9), (
            "lv7 档 1.08/0.54 + E1 def_pen 联动")

    def test_e6_charge_cap_and_seg3_gain(self):
        """E6：开战 +5 充能、上限 max_override 15、强化普攻（第 3 段后）再 +5——
        首动 5+4（双破）+5=14（>10 证上限已抬）、再动 14+5→钳 15."""
        eng = _make(_compiled(eidolon=6, toughness=20))
        st = _rappa(eng)
        assert math.isclose(st.resources["talent_stacks"], 5.0), "E6 开战 +5"
        _ult(eng)
        _cast(eng, "131718")
        assert math.isclose(st.resources["talent_stacks"], 14.0), (
            "5 + (天赋+魔天)×2 破 + E6 第3段后 5——超过底上限 10 证 max_override 15")
        _cast(eng, "131718")   # 双假人已破无新击破：仅 E6 +5
        assert math.isclose(st.resources["talent_stacks"], 15.0), "19 → 钳上限 15"
