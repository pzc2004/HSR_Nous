"""银枝 1302 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 天赋升格叠层/
双阈值终极技/六段弹射/行迹三件/星魂 E1-E5 全链 → 手算全等.

口径常数：银枝 atk 737.352（行迹 atk_pct 0.28 → 有效 943.81056）、物理增伤 0.144
（行迹 trace_stat_effects）、crit_rate 0.05、crit_dmg 0.5、max_energy 180。
假人 def 1000 → 防御区 0.5；弱点 physical 匹配 → 抗性区 1.0；未击破 0.9；
期望暴击区 = min(1,rate)×(1+dmg) + (1-min(1,rate))（0 层时 = 1.025）。
天赋 lv10：每敌回能 3、每层暴击率 +2.5%、上限 10（E4 → 12）；
130203 lv10 主段 1.6 / 130214 lv10 主段 2.8 + 6×0.95 弹射。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 737.352
ATK_EFF = ATK * 1.28          # 行迹攻击 28%（pct 白值口径）
DMG_ZONE = 1.144              # 行迹物理增伤 14.4%
DEF_ZONE = 0.5                # 假人 def 1000 → 1000/(1000+1000)
UNBROKEN = 0.9
CRIT0 = 0.05 * 1.5 + 0.95     # 期望暴击区（0 层升格）= 1.025


def _build(*, eidolon: int = 0, pre_battle: bool = False, n_enemies: int = 2):
    member = {"character_template": "1302", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1302", "technique": "130207"}]
    enemies = [{"actor_id": f"e{i+1}", "name": f"假人{i+1}", "hp": 1e9, "spd": 100,
                "atk": 1000, "def": 1000, "max_toughness": 100,
                "weakness": ["physical"]} for i in range(n_enemies)]
    stage = {"stage": {"stage_id": "s", "enemies": enemies,
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
    return build, stage


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, n_enemies: int = 2):
    build, stage = _build(eidolon=eidolon, pre_battle=pre_battle, n_enemies=n_enemies)
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _arg(eng):
    return eng.state.actors["1302"]


def _dmg_taken(eng, aid):
    st = eng.state.actors[aid]
    return st.actor.stats.hp - st.current_hp


def _cast(eng, aid, *, target="e1"):
    st = _arg(eng)
    a = next(x for x in eng.actions_by_actor["1302"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "1302", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, aid, *, energy: float):
    st = _arg(eng)
    st.current_energy = energy
    ult = next(a for a in eng.actions_by_actor["1302"] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _expected(mult, crit):
    """手算期望伤害：倍率×有效攻击×增伤区×防御区×抗性区×未击破×期望暴击区."""
    return mult * ATK_EFF * DMG_ZONE * DEF_ZONE * 1.0 * UNBROKEN * crit


def _crit(rate, dmg):
    """期望暴击区（rulebook crit_expected_multi 镜像）."""
    return min(1.0, rate) * (1 + dmg) + (1 - min(1.0, rate))


class TestArgentiCompile:
    def test_actions_resources_levels(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1302"]}
        assert acts == {"130201", "130202", "130203", "130214"}
        assert "apotheosis" in compiled.resource_decls_by_actor["1302"]
        levels = compiled.build_team[0].skill_levels
        assert levels == {"basic": 6, "skill": 10, "ultimate": 10, "talent": 10, "elation_skill": 10}

    def test_e3_e5_level_overrides(self):
        lv3 = _compiled(eidolon=3).build_team[0].skill_levels
        assert lv3["skill"] == 12 and lv3["talent"] == 12, "E3 战技/天赋 +2"
        lv5 = _compiled(eidolon=5).build_team[0].skill_levels
        assert lv5["ultimate"] == 12 and lv5["basic"] == 7, "E5 终结技 +2 / 普攻 +1（6+1）"


class TestTraceStats:
    def test_trace_stat_effects(self, compiled):
        """行迹 10 节点：攻击 28% / 物理增伤 14.4% / 生命 10%（初始 modifier 通道）."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_arg(eng))
        assert math.isclose(eff["atk"], ATK * 1.28, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("physical", 0.0), 0.144, rel_tol=1e-9)
        assert math.isclose(eff["hp"], 1047.816 * 1.1, rel_tol=1e-9)


class TestTalentApotheosis:
    def test_basic_hit_energy_stack_crit(self, compiled):
        """普攻：回 20+3=23 能（天赋每敌 3）；+1 层；暴击率现场 0.075（stat_exprs 追层）."""
        eng = _make(compiled)
        st = _arg(eng)
        _cast(eng, "130201")
        assert math.isclose(st.current_energy, 23.0)
        assert math.isclose(st.resources["apotheosis"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.05 + 0.025, rel_tol=1e-9)

    def test_skill_aoe_hit_counts(self, compiled):
        """战技全体：回 30+3×2=36 能；+2 层；耗 1 SP；每敌伤害 = 1.2×atk×zones."""
        eng = _make(compiled)
        st = _arg(eng)
        _cast(eng, "130202")
        assert math.isclose(st.current_energy, 36.0)
        assert math.isclose(st.resources["apotheosis"], 2.0)
        assert math.isclose(eng.state.skill_points, 2.0)
        for aid in ("e1", "e2"):
            assert math.isclose(_dmg_taken(eng, aid), _expected(1.2, CRIT0), rel_tol=1e-9), (
                f"战技 lv10 1.2 倍（首放 0 层）{aid}")

    def test_crit_rate_cap_10(self, compiled):
        """上限门控：层数超 10 暴击率钳 0.30（stat_exprs min 门控，E4 标记缺席）."""
        eng = _make(compiled)
        st = _arg(eng)
        st.resources["apotheosis"] = 15.0
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.05 + 0.025 * 10, rel_tol=1e-9)

    def test_piety_turn_start_stack(self, compiled):
        """虔诚：回合开始 +1 层（on_turn_start 手动 emit）."""
        eng = _make(compiled)
        st = _arg(eng)
        eng.bus.emit("on_turn_start", {"actor": "1302"}, eng.state)
        assert math.isclose(st.resources["apotheosis"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.05 + 0.025, rel_tol=1e-9), "虔诚加层后暴击率现场追层（无重挂烘焙）"

    def test_generosity_actor_enter_energy(self, compiled):
        """慷慨：敌方入战 +2 能量（actor_enter 手动 emit，monster 过滤）."""
        eng = _make(compiled)
        st = _arg(eng)
        eng.bus.emit("actor_enter", {"actor": "e2", "wave_index": 0}, eng.state)
        assert math.isclose(st.current_energy, 2.0)
        eng.bus.emit("actor_enter", {"actor": "1302"}, eng.state)   # 我方入战不触发
        assert math.isclose(st.current_energy, 2.0)


class TestUltimates:
    def test_ult90_damage_energy_toughness(self, compiled):
        """130203：耗 90 → 回 5+3×2=11；全体 1.6 倍（0 层暴击 1.025）；削韧 20/敌."""
        eng = _make(compiled)
        st = _arg(eng)
        _ult(eng, "130203", energy=90.0)
        assert math.isclose(st.current_energy, 11.0)
        assert math.isclose(st.resources["apotheosis"], 2.0)
        for aid in ("e1", "e2"):
            assert math.isclose(_dmg_taken(eng, aid), _expected(1.6, CRIT0), rel_tol=1e-9)
            assert math.isclose(eng.state.actors[aid].toughness, 80.0), "130203 削韧 20"

    def test_ult180_main_and_six_bounces(self, compiled):
        """130214：耗 180 → 回 5+3×2+3×6=29（主段 2 敌 + 弹射逐段自结）；+8 层；
        e1 = 主段 2.8（0 层暴击）+ Σ弹射 0.95×crit（爬坡：弹射 i 吃 主段 2 层+前 i-1 段，
        expected 模式随机确定化=布场序首敌），e2 = 仅主段；削韧 e1 20+5×6=50，e2 20."""
        eng = _make(compiled)
        st = _arg(eng)
        _ult(eng, "130214", energy=180.0)
        assert math.isclose(st.current_energy, 29.0)
        assert math.isclose(st.resources["apotheosis"], 8.0)
        main = _expected(2.8, CRIT0)
        bounces = sum(_expected(0.95, _crit(0.05 + 0.025 * (2 + i - 1), 0.5))
                      for i in range(1, 7))
        assert math.isclose(_dmg_taken(eng, "e1"), main + bounces, rel_tol=1e-9), (
            "e1 主段+6 弹射（逐段爬坡）")
        assert math.isclose(_dmg_taken(eng, "e2"), main, rel_tol=1e-9), "e2 仅主段"
        assert math.isclose(eng.state.actors["e1"].toughness, 50.0), "e1 削韧 20+5×6"
        assert math.isclose(eng.state.actors["e2"].toughness, 80.0), "e2 削韧 20"


class TestTraceCourage:
    def test_courage_low_hp_bonus(self, compiled):
        """勇气：目标 HP≤50% → 伤害 ×1.15（before_take_damage modify_amount 承载）."""
        eng = _make(compiled)
        eng.state.actors["e1"].current_hp = 4e8      # ≤ 0.5×1e9
        before = _dmg_taken(eng, "e1")
        _cast(eng, "130201", target="e1")
        assert math.isclose(_dmg_taken(eng, "e1") - before,
                            _expected(1.0, CRIT0) * 1.15, rel_tol=1e-9)
        _cast(eng, "130201", target="e2")            # 满血对照：无勇气；已持 1 层 → 暴击 1.0375
        assert math.isclose(_dmg_taken(eng, "e2"),
                            _expected(1.0, _crit(0.05 + 0.025, 0.5)), rel_tol=1e-9)


class TestEidolons:
    def test_e1_crit_dmg_per_stack(self):
        """E1 审美王国的缺口：每层暴伤 +4%（stat_exprs 追层）——2 层 → 0.58."""
        eng = _make(_compiled(eidolon=1))
        st = _arg(eng)
        _cast(eng, "130202")
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], 0.5 + 0.04 * 2, rel_tol=1e-9)
        assert math.isclose(eff["crit_rate"], 0.05 + 0.025 * 2, rel_tol=1e-9)

    def test_e2_atk_up_with_3_enemies(self):
        """E2 玛瑙石的谦卑：终结技时敌≥3 → 攻击 +40%（737.352×(1+0.28+0.4)）."""
        eng = _make(_compiled(eidolon=2, n_enemies=3))
        st = _arg(eng)
        _ult(eng, "130203", energy=90.0)
        assert "E2_ATK_UP" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            ATK * (1 + 0.28 + 0.4), rel_tol=1e-9)
        assert math.isclose(st.resources["apotheosis"], 3.0), "3 敌命中 +3 层"

    def test_e2_not_triggered_with_2_enemies(self):
        """E2 负例：2 敌不触发."""
        eng = _make(_compiled(eidolon=2))
        _ult(eng, "130203", energy=90.0)
        assert "E2_ATK_UP" not in _arg(eng).modifiers

    def test_e3_skill_lv12_talent_lv12(self):
        """E3 联动：战技实取 lv12=1.32；天赋 lv12 每层 +2.8% → 2 层暴击率 0.106."""
        eng = _make(_compiled(eidolon=3))
        st = _arg(eng)
        _cast(eng, "130202")
        assert math.isclose(_dmg_taken(eng, "e1"), _expected(1.32, CRIT0), rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.05 + 0.028 * 2, rel_tol=1e-9)

    def test_e4_battle_start_and_cap_12(self):
        """E4 号角的奉献：开战 +2 层；eidolon=4 含 E3 → 天赋 lv12（每层 +2.8%）：
        开战暴击率 0.106/暴伤 0.58（E1 同池）；上限 10→12（E4_CAP_UP 标记门控——
        13 层钳 12 → 暴击率 0.386、暴伤 0.98）."""
        eng = _make(_compiled(eidolon=4))
        st = _arg(eng)
        assert math.isclose(st.resources["apotheosis"], 2.0)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.05 + 0.028 * 2, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], 0.5 + 0.04 * 2, rel_tol=1e-9)
        st.resources["apotheosis"] = 13.0
        eff2 = eng.pipeline.effective_stats(st)
        assert math.isclose(eff2["crit_rate"], 0.05 + 0.028 * 12, rel_tol=1e-9)
        assert math.isclose(eff2["crit_dmg"], 0.5 + 0.04 * 12, rel_tol=1e-9)

    def test_e5_ult_lv12_with_full_eidolon_chain(self):
        """E5 联动（含 E1/E3/E4）：130214 实取 lv12（主段 3.024、弹射 1.026——
        lv12=index 11，非 lv11 的 2.912/0.988）；开战 2 层（E4）→ 主段暴击率
        0.106/暴伤 0.58；弹射 i 吃 2(E4)+2(主段)+i-1 = 3+i 层（爬坡逐段：
        rate=0.05+0.028s、dmg=0.5+0.04s）；放后回 5+3×2+3×6=29 能、层数 2+8=10."""
        eng = _make(_compiled(eidolon=5))
        st = _arg(eng)
        _ult(eng, "130214", energy=180.0)
        main = _expected(3.024, _crit(0.05 + 0.028 * 2, 0.5 + 0.04 * 2))
        bounces = sum(
            _expected(1.026, _crit(0.05 + 0.028 * (3 + i), 0.5 + 0.04 * (3 + i)))
            for i in range(1, 7))
        assert math.isclose(_dmg_taken(eng, "e1"), main + bounces, rel_tol=1e-9)
        assert math.isclose(_dmg_taken(eng, "e2"), main, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 29.0)
        assert math.isclose(st.resources["apotheosis"], 10.0)

    def test_e6_no_silent_modeling(self):
        """E6「你」的光芒（无视 30% 防御）待收——技域 def_pen 通道缺，不静默建模：
        面板 def_pen 恒 0（防回归闸：将来收编后本断言应随通道落地改写）."""
        eng = _make(_compiled(eidolon=6))
        st = _arg(eng)
        _ult(eng, "130214", energy=180.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.0)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技：入战全体 0.8×ATK 物理伤 + 自回 15 能（开战 0 层 → 暴击 1.025）."""
        eng = _make(_compiled(pre_battle=True))
        st = _arg(eng)
        assert math.isclose(st.current_energy, 15.0)
        for aid in ("e1", "e2"):
            assert math.isclose(_dmg_taken(eng, aid), _expected(0.8, CRIT0), rel_tol=1e-9)
