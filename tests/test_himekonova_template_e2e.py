"""姬子•启行 1510 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
天赋境界经济/旗语/助战三技/Starblazer 序列/行迹/星魂全链 → 手算全等.

口径常数：姬子白值 atk 756.756、crit 0.05/0.5；行迹 atk_pct+28%/暴击率+12%/火伤+8%
→ 有效 atk = 756.756×1.28 = 968.64768，暴击率 0.17。天赋 lv10：暴伤+0.80/全抗穿+0.20。
假人 def 1000 → 防御区 0.5；火弱点 → 基础抗性 0（抗性区 = 1+res_pen）；未击破 0.9。
期望暴击区 = 0.17×(1+暴伤)+0.83。assist 唯一入口 fire_assist（额度=助战次数）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK_W = 756.756
ATK = ATK_W * 1.28          # 行迹 atk_pct +28%
CR = 0.05 + 0.12            # 0.17（行迹暴击率 +12%）
CD0 = 0.5 + 0.80            # 1.30（天赋 lv10 暴伤）
CD5 = 0.5 + 0.88            # 1.38（E5 天赋 lv12）
FIRE = 0.08                 # 行迹火伤 +8%


def _crit_exp(cd):
    return CR * (1 + cd) + (1 - CR)


def _z(cd, pen, boost):
    """单目标单位倍率乘区 = 防御区 0.5 × 抗性区(1+pen) × 未击破 0.9 × 期望暴击 × 增伤区."""
    return 0.5 * (1 + pen) * 0.9 * _crit_exp(cd) * (1 + boost)


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1510", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1510", "technique": "151007"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
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


def _nova(eng):
    return eng.state.actors["1510"]


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


def _assist(eng, aid="151022"):
    st = _nova(eng)
    a = next(x for x in eng.actions_by_actor["1510"] if x.action_id == aid)
    return eng.fire_assist(st, a)


def _ult(eng):
    st = _nova(eng)
    st.current_energy = 150.0
    ult = next(a for a in eng.actions_by_actor["1510"] if a.action_id == "151003")
    assert eng._fire_ultimate(st, ult) is True


class TestNovaCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1510"]}
        assert set(acts) == {"151001", "151002", "151003", "151022", "151025", "151026"}, (
            "终结技子段 151008/151009/151014 散装 action 已摘除（available_if 闸死死件）")
        for aid in ("151022", "151025", "151026"):
            assert acts[aid].action_type == "assist"
            assert acts[aid].assist_cost_resource == "assist_uses", "助战额度闸（无闸=免费后门）"
            assert acts[aid].level_key == "talent", "助战技取档随天赋（E5 官方同列 +2）"
        assert acts["151001"].toughness_dmg == 10        # 米游社五项
        assert acts["151003"].energy_gain == 5           # tbgd+米游社双源
        assert acts["151003"].energy_cost == 150
        decls = compiled.resource_decls_by_actor["1510"]
        assert decls["assist_uses"]["max"] == 1
        assert decls["source_energy"]["max"] == 3
        assert "_starblazer_ctl" not in decls and "_territory" not in decls, "死件资源随删"


class TestTalentAndTraces:
    def test_battle_start_panel(self, compiled):
        """天赋+行迹面板：atk×1.28 / 暴击率 0.17 / 暴伤 1.30 / 全抗穿 0.20 / 火伤 8%."""
        eng = _make(compiled)
        st = _nova(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], ATK, rel_tol=1e-9)
        assert math.isclose(eff["crit_rate"], 0.17, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], CD0, rel_tol=1e-9), "0.5+天赋 lv10 0.80"
        assert math.isclose(eff["res_pen"], 0.20, rel_tol=1e-9), "天赋 lv10 全抗穿"
        assert math.isclose(eff["dmg_bonus"].get("fire", 0.0), FIRE, rel_tol=1e-9)
        assert math.isclose(st.resources["assist_uses"], 1.0), "天赋：开战 1 次助战"
        assert math.isclose(st.resources["source_energy"], 0.0)
        assert "NAV_SEMAPHORE" not in st.modifiers, "未施秘技/未放战技不该有旗语"

    def test_basic_damage_sp_energy(self, compiled):
        """普攻 lv6=1.0：1.0×ATK×Z(暴伤1.30/抗穿0.20/火伤0.08)；SP+1、回能 20、削韧 10."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1510", "151001")
        z = _z(CD0, 0.20, FIRE)
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK * z, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "普攻产 1 点"
        assert math.isclose(_nova(eng).current_energy, 20.0), "普攻回能 20（tbgd）"
        assert math.isclose(e1.toughness, 90.0), "普攻削韧 10（米游社）"


class TestSkillSemaphore:
    def test_skill_semaphore_and_quota(self, compiled):
        """战技：SP-1/回能 30/助战回满 1/旗语 3 回合（owner_turn_start 锚）全队增伤 20%."""
        eng = _make(compiled)
        st = _nova(eng)
        ally = eng.state.actors["ally"]
        st.resources["assist_uses"] = 0.0
        _cast(eng, "1510", "151002")
        assert math.isclose(eng.state.skill_points, 2.0)
        assert math.isclose(st.current_energy, 30.0)
        assert math.isclose(st.resources["assist_uses"], 1.0), "施放战技立即回满助战次数"
        mod = st.modifiers["NAV_SEMAPHORE"]
        assert mod.duration == 3 and mod.tick_anchor == "owner_turn_start"
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"].get("all", 0.0),
                            0.20, rel_tol=1e-9), "旗语 lv10 全队增伤（自身）"
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.20, rel_tol=1e-9), "旗语 effect_scope=team（辅手同吃）"

    def test_semaphore_tick_owner_turn_start(self, compiled):
        """旗语计时：姬子回合开始锚 3→2→1→到期移除（官方「每回合开始时持续回合数减1」）."""
        eng = _make(compiled)
        st = _nova(eng)
        _cast(eng, "1510", "151002")
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.modifiers["NAV_SEMAPHORE"].duration == 2
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.modifiers["NAV_SEMAPHORE"].duration == 1
        eng._tick_modifiers(st, "owner_turn_start")
        assert "NAV_SEMAPHORE" not in st.modifiers, "第 3 次回合开始到期"

    def test_turn_start_regain_and_trace_energy(self, compiled):
        """回合开始经济：旗语在→回 1 次；次数=上限→+5 能（快照语义各读事件前旧值）."""
        eng = _make(compiled)
        st = _nova(eng)
        # 无旗语、次数=上限 1：只发 +5 能
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(st.current_energy, 5.0), "1510101②：次数=上限 → +5 能"
        assert math.isclose(st.resources["assist_uses"], 1.0)
        # 次数 0（无旗语）：两钩都不动
        st.resources["assist_uses"] = 0.0
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(st.current_energy, 5.0) and math.isclose(st.resources["assist_uses"], 0.0)
        # 旗语在、次数 0：快照读 0 → 只回次数不加能；下一回合开始次数=1 → +5
        _cast(eng, "1510", "151002")
        st.resources["assist_uses"] = 0.0
        eng.bus.emit("on_turn_start", {"actor": "1510"}, eng.state)
        assert math.isclose(st.resources["assist_uses"], 1.0), "旗语期间回合开始回 1 次"
        assert math.isclose(st.current_energy, 35.0), "快照读旧值 0 → 本次不加 5 能"
        eng.bus.emit("on_turn_start", {"actor": "1510"}, eng.state)
        assert math.isclose(st.current_energy, 40.0), "次数=上限 → +5 能"


class TestAssist:
    def test_fire_assist_damage_and_refund(self, compiled):
        """助战 151022（姬子使用分支）：全体 2.0 + 随机 4×0.32；1510101① 免耗返还；回能 18."""
        eng = _make(compiled)
        st = _nova(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        assert _assist(eng) is True
        z = _z(CD0, 0.20, FIRE)
        assert math.isclose(hp1 - e1.current_hp, (2.0 + 4 * 0.32) * ATK * z, rel_tol=1e-9), (
            "全体 #4=2.0 落双假人 + 随机 #5×#6=4×0.32 全落 e1")
        assert math.isclose(hp2 - e2.current_hp, 2.0 * ATK * z, rel_tol=1e-9)
        assert math.isclose(st.resources["assist_uses"], 1.0), "免耗：扣 1 后同钩返还 1"
        assert math.isclose(st.current_energy, 18.0), "助战回能 18（tbgd）"

    def test_quota_gate(self, compiled):
        """额度闸：次数 0 → fire_assist 拒发（assist_cost_resource 承载）."""
        eng = _make(compiled)
        st = _nova(eng)
        st.resources["assist_uses"] = 0.0
        assert _assist(eng) is False, "无次数不可发动"
        st.resources["assist_uses"] = 1.0
        assert _assist(eng) is True


class TestUltSequence:
    def test_starblazer_sequence_e0(self, compiled):
        """终结技 E0 固定序列：Beam×6(0.32) → Pulse(0.20)+随机 2×(0.30+0.30) → Final 3×0.80；
        随机段全落 e1；耗能 150 回 5；源能记账归零；削韧 6×2+2=14."""
        eng = _make(compiled)
        st = _nova(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(st.current_energy, 5.0), "150 全扣 + 回 5（勘正⑬）"
        z = _z(CD0, 0.20, FIRE)
        mult_aoe = 6 * 0.32 + 0.20                       # 2.12（双假人同吃）
        mult_e1 = mult_aoe + 2 * (0.30 + 0.30) + 3 * 0.80  # +1.20+2.40=5.72
        assert math.isclose(hp1 - e1.current_hp, mult_e1 * ATK * z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, mult_aoe * ATK * z, rel_tol=1e-9)
        assert math.isclose(st.resources["source_energy"], 0.0), "Pulse 消耗所有源能"
        assert math.isclose(e1.toughness, 100 - 14.0), "Beam 6×2 + Pulse 2（米游社子标签）"

    def test_ult_with_semaphore(self, compiled):
        """旗语下的终结技：增伤区 = 火 0.08 + 旗语 0.20."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1510", "151002")
        hp1 = e1.current_hp
        _ult(eng)
        z = _z(CD0, 0.20, FIRE + 0.20)
        mult_e1 = 6 * 0.32 + 0.20 + 2 * 0.60 + 3 * 0.80
        assert math.isclose(hp1 - e1.current_hp, mult_e1 * ATK * z, rel_tol=1e-9)


class TestEidolons:
    def test_e1_extra_instance(self):
        """E1④：姬子发动助战额外段数 +1——随机段 4→5（段值 0.32 lv10）."""
        eng = _make(_compiled(eidolon=1))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        assert _assist(eng) is True
        z = _z(CD0, 0.20, FIRE)
        assert math.isclose(hp1 - e1.current_hp, (2.0 + 5 * 0.32) * ATK * z, rel_tol=1e-9)

    def test_e3_level_overrides(self):
        """E3：终结技 lv12（Beam 0.352/Pulse 0.22/随机 0.33+0.30/Final 0.88）+ 普攻 lv7=1.1."""
        eng = _make(_compiled(eidolon=3))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1510", "151001")
        z = _z(CD0, 0.20, FIRE)
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK * z, rel_tol=1e-9), "普攻 lv7"
        hp1 = e1.current_hp
        _ult(eng)
        mult_e1 = 6 * 0.352 + 0.22 + 2 * (0.33 + 0.30) + 3 * 0.88   # 2.112+0.22+1.26+2.64
        assert math.isclose(hp1 - e1.current_hp, mult_e1 * ATK * z, rel_tol=1e-9), "终结技 lv12 全链"

    def test_e4_team_res_pen(self):
        """E4：天赋全抗穿辐射全队（辅手 0.20）+ 姬子额外 +0.10（自身 0.30）."""
        eng = _make(_compiled(eidolon=4))
        st = _nova(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.20, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.30, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1510", "151001")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK * _z(CD0, 0.30, FIRE), rel_tol=1e-9), (
            "E3 联动：普攻 lv7=1.1（eidolon=4 含 E3）")

    def test_e5_level_overrides(self):
        """E5：天赋 lv12（暴伤 1.38/抗穿 0.22+E4 0.10=0.32）+ 旗语 lv12=0.22 +
        助战 lv12（AoE 2.2/段 0.348，E1 5 段）."""
        eng = _make(_compiled(eidolon=5))
        st = _nova(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"], CD5, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.32, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"],
                            0.22, rel_tol=1e-9)
        _cast(eng, "1510", "151002")
        assert math.isclose(st.modifiers["NAV_SEMAPHORE"].stat_effects["all_dmg"],
                            0.22, rel_tol=1e-9), "旗语 lv12"
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        assert _assist(eng) is True
        z = _z(CD5, 0.32, FIRE + 0.22)
        assert math.isclose(hp1 - e1.current_hp, (2.2 + 5 * 0.348) * ATK * z, rel_tol=1e-9)

    def test_e6_fire_pen_and_assist_boost(self):
        """E6：火穿 +0.20（自 0.52）+ 助战增伤 75%（dmg_assist_dmg_boost 桶）."""
        eng = _make(_compiled(eidolon=6))
        st = _nova(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"],
                            0.22 + 0.10 + 0.20, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"].get(
            "assist_dmg_boost", 0.0), 0.75, rel_tol=1e-9)
        _cast(eng, "1510", "151002")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        assert _assist(eng) is True
        z = _z(CD5, 0.52, FIRE + 0.22 + 0.75)
        assert math.isclose(hp1 - e1.current_hp, (2.2 + 5 * 0.348) * ATK * z, rel_tol=1e-9)


class TestCompanionProtocols:
    def test_verdict_state_and_ult_boost(self, compiled):
        """151025→裁决：增伤 100% + 终结技增伤 100%（type 桶）；后续助战/终结技全链吃."""
        eng = _make(compiled)
        st = _nova(eng)
        assert _assist(eng, "151025") is True
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["dmg_bonus"].get("all", 0.0), 1.00, rel_tol=1e-9), "裁决 #8 lv10"
        assert math.isclose(eff["dmg_bonus"].get("ultimate_dmg_boost", 0.0),
                            1.00, rel_tol=1e-9), "裁决 #10 lv10（勘正⑮ 补收）"
        # 后续 151022：增伤区 = 火 0.08 + 裁决 1.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        assert _assist(eng, "151022") is True
        z = _z(CD0, 0.20, FIRE + 1.00)
        assert math.isclose(hp1 - e1.current_hp, (2.0 + 4 * 0.32) * ATK * z, rel_tol=1e-9)
        # 终结技全链：增伤区 = 0.08 + 1.0 + 终结技 type 1.0
        hp1 = e1.current_hp
        _ult(eng)
        z_ult = _z(CD0, 0.20, FIRE + 1.00 + 1.00)
        mult_e1 = 6 * 0.32 + 0.20 + 2 * 0.60 + 3 * 0.80
        assert math.isclose(hp1 - e1.current_hp, mult_e1 * ATK * z_ult, rel_tol=1e-9)

    def test_decimation_team_crit_dmg(self, compiled):
        """151026→歼破：全队暴伤 +100%（team scope——辅手 0.5→1.5，姬子 1.3→2.3）."""
        eng = _make(compiled)
        st = _nova(eng)
        ally = eng.state.actors["ally"]
        assert _assist(eng, "151026") is True
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"], 1.50, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            CD0 + 1.00, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_wave_skill(self):
        """秘技：进战（第 1 波）立即施放战技——回满助战 + 旗语 3 回合；转波再施放."""
        eng = _make(_compiled(pre_battle=True))
        st = _nova(eng)
        assert math.isclose(st.resources["assist_uses"], 1.0)
        assert st.modifiers["NAV_SEMAPHORE"].duration == 3, "进战即旗语（on_battle_start 钩）"
        eng._tick_modifiers(st, "owner_turn_start")
        assert st.modifiers["NAV_SEMAPHORE"].duration == 2
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert st.modifiers["NAV_SEMAPHORE"].duration == 3, "第 2 波开始再施放（刷新）"

    def test_no_technique_no_semaphore(self):
        """未施秘技：开局无旗语（主干无 on_wave_start 无条件装填——勘正⑫）."""
        eng = _make(_compiled(pre_battle=False))
        assert "NAV_SEMAPHORE" not in _nova(eng).modifiers
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert "NAV_SEMAPHORE" not in _nova(eng).modifiers
