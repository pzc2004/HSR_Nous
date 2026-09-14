"""忘归人 1225 模板端到端对轴（复杂型专项收官——B38 超击破体系首个消费者）：
真模板 YAML → 编译 → 天赋云火昭+全队超击破/狐祈/焚尾/行迹/星魂全链 → 手算全等.

口径常数：忘归人白值 atk 582.12、A2 trace 击破特攻 +0.3、spd 102、max_energy 130；
假人 def 1000 → 防御区 0.5（狐祈减防 -18% → def 820 → 区 1000/1820=0.54945）、
火弱点 → 抗性区 1.0、已击破 base_universal 1.0、max_toughness 100 → 云火昭 40（0.4×）。
超击破基数 376.75533×有效削韧；火击破系数 2.0；击破基数 (0.5+100/40)=3.0。
辅手 atk 1500、火普攻 1.0×atk、削韧 10、crit 0.05/0.5（期望暴击区 1.025）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SB_BASE = 3767.5533 / 10           # 超击破基数系数
BREAK_DMG_BASE = 3767.5533 * 2.0 * 3.0   # 火击破基数（scaling×(0.5+max_tough/40)）
DIRECT = 1500 * 0.5 * 1.025        # 辅手直伤（atk×倍率 1.0×防御区×期望暴击区 1.025）= 768.75


def _build(*, eidolon: int = 0):
    member = {"character_template": "1225", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0):
    return compile_encounter(_build(eidolon=eidolon), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _fg(eng):
    return eng.state.actors["1225"]


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


class TestFugueCompile:
    def test_actions_resources_trace(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1225"]}
        assert acts == {"122501", "122508", "122502", "122503"}
        decls = compiled.resource_decls_by_actor["1225"]
        assert {"_fengwei", "_fengwei_turns", "_a2_used"} <= set(decls)
        eng = _make(compiled)
        assert math.isclose(eng.pipeline.effective_stats(_fg(eng))["break_effect"],
                            0.3, rel_tol=1e-9), "A2 trace 击破特攻 +30%"


class TestTalent:
    def test_cloudflame_bar_and_team_conversion(self, compiled):
        """天赋：开战全体敌人云火昭 40（0.4×100）；全队 super_break_modifier 1.0（lv10）."""
        eng = _make(compiled)
        tgt = eng.state.actors["e1"]
        assert tgt.extra_bars == [40.0], "云火昭 = 0.4×满韧"
        for aid in ("1225", "ally"):
            st = eng.state.actors[aid]
            assert "FG_SUPER_BREAK_CONV" in st.modifiers
            assert math.isclose(eng.pipeline.effective_stats(st)["super_break_modifier"],
                                1.0, rel_tol=1e-9), "全队超击破转化 lv10=1.0"

    def test_super_break_conversion_value_with_a4(self, compiled):
        """辅手击破后下一击 → 超击破 = 10×系数×1.06（A4 一层 6% 已挂）×0.5×转化 1.0."""
        eng = _make(compiled)
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")   # 击破（A4 一层挂到辅手）
        assert tgt.broken and tgt.bar_index == 1 and tgt.toughness == 40.0, "主条破+云火昭承接"
        hp = tgt.current_hp
        _cast(eng, "ally", "ally_basic")   # 超击破位（云火昭 40→30 同步削减）
        sb = 10 * SB_BASE * 1.06 * 0.5
        assert math.isclose(hp - tgt.current_hp, DIRECT + sb, rel_tol=1e-9), (
            "直伤 768.75 + 超击破（A4 6% 已入 be_multi——stat_exprs 现场求值）")

    def test_cloudflame_second_break_damage_only(self, compiled):
        """虚条破=只再吃击破伤害：直伤+超击破+第二笔击破伤害全链；击破效果不重复."""
        eng = _make(compiled)
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")
        mods_after_main = dict(tgt.modifiers)
        hp = tgt.current_hp
        for _ in range(3):                 # 云火昭 40 → 10（10×3=30）
            _cast(eng, "ally", "ally_basic")
        _cast(eng, "ally", "ally_basic")   # 第 4 击虚条破：直伤+超击破+第二笔击破伤害
        sb = 10 * SB_BASE * 1.06 * 0.5
        # 虚条破当击：on_break 钩先于尾段结算落笔——A4 二层当击生效（emit 序在案）：
        # 超击破/击破伤害同吃 1.12（非 1.06）
        sb12 = 10 * SB_BASE * 1.12 * 0.5
        brk12 = BREAK_DMG_BASE * 1.12 * 0.5
        assert math.isclose(hp - tgt.current_hp,
                            3 * (DIRECT + sb) + (DIRECT + sb12 + brk12), rel_tol=1e-6)
        assert dict(tgt.modifiers) == mods_after_main, "虚条破不重复击破效果"
        assert tgt.broken and tgt.bars_exhausted

    def test_a1_delay_on_break(self, compiled):
        """A1 1225101：击破 → 该敌人行动延后 15%（与击破自带 25% 推条独立相加=+4000）."""
        eng = _make(compiled)
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        before = _remaining(eng, "e1")
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(_remaining(eng, "e1") - before, 4000.0, rel_tol=1e-9), (
            "击破自带 25%（+2500）+ A1 15%（+1500）独立推条相加——加算形式与官方同向，"
            "合并口径待实测")


class TestSkill:
    def test_prayer_fengwei_a2_and_def_down(self, compiled):
        """战技：狐祈挂目标（击破特攻 +30% lv10）+ 焚尾闩 + A2 首次返点（SP 净 0）+
        狐祈目标攻击 → 敌人减防 -18%（def 1000→820，区 0.5→0.54945）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        sp0 = eng.state.skill_points
        _cast(eng, "1225", "122502", target=ally)
        assert "FOXIAN_PRAYER" in ally.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.30, rel_tol=1e-9), "狐祈击破特攻 lv10 #2=0.30"
        assert math.isclose(_fg(eng).resources["_fengwei"], 1.0)
        assert math.isclose(eng.state.skill_points, sp0), "耗 1 + A2 返 1 = 净 0"
        assert math.isclose(_fg(eng).resources["_a2_used"], 1.0)
        hp = eng.state.actors["e1"].current_hp
        _cast(eng, "ally", "ally_basic")
        tgt = eng.state.actors["e1"]
        assert "FOXIAN_DEF_DOWN" in tgt.modifiers
        assert math.isclose(hp - tgt.current_hp, DIRECT * 0.9, rel_tol=1e-9), (
            "第一击减防未挂（on_hp_decrease 后置）——区 0.5×未击破 0.9")
        hp2 = tgt.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp2 - tgt.current_hp,
                            1500 * (1000 / (1000 + 820)) * 1.025 * 0.9, rel_tol=1e-6), (
            "第二击吃减防：区 1000/1820 × 期望暴击 1.025 × 未击破 0.9")

    def test_fengwei_enhanced_basic_swap(self, compiled):
        """焚尾期间 122508 在册/122501 出集（available_if 互斥声明——编译层钉）."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["1225"]}
        assert "res__fengwei < 1" in (acts["122501"].available_if or "")
        assert "res__fengwei >= 1" in (acts["122508"].available_if or "")


class TestTraces:
    def test_a4_stacks_and_threshold(self, compiled):
        """A4：两破 2 层（+6%/层）；忘归人 BE≥220% 档后 +18%/层（阈值读 stat_of 现场）."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        tgt = eng.state.actors["e1"]
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")   # 破 1（A4 一层）
        _cast(eng, "ally", "ally_basic")   # 云火昭削
        for _ in range(3):
            _cast(eng, "ally", "ally_basic")   # 虚条破（A4 二层）
        assert math.isclose(ally.modifiers["A4_BE_STACKS"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.12, rel_tol=1e-9), "6%×2 层（未达 220% 档）"
        eng._apply_modifier(_fg(eng), __import__("hsr_nous.sim.state", fromlist=["Modifier"]).Modifier(
            modifier_id="BE_FIX", name="BE", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 2.0}))
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_effect"],
                            0.36, rel_tol=1e-9), "220% 档后 18%×2 层（阈值含动态）"


class TestEidolons:
    def test_e1_efficiency_on_prayer_target(self):
        """E1：狐祈目标弱点击破效率 +50%（break_efficiency_boost 在案键）."""
        eng = _make(_compiled(eidolon=1))
        ally = eng.state.actors["ally"]
        _cast(eng, "1225", "122502", target=ally)
        assert math.isclose(eng.pipeline.effective_stats(ally)["break_efficiency_boost"],
                            0.5, rel_tol=1e-9)

    def test_e2_energy_and_ult_advance(self):
        """E2：①击破回 3 能（每条 on_break）；②大招全队拉条 24%（剩余距离 -2400）."""
        eng = _make(_compiled(eidolon=2))
        fg = _fg(eng)
        tgt = eng.state.actors["e1"]
        fg.current_energy = 0.0
        tgt.toughness = 5.0
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(fg.current_energy, 3.0), "E2① 击破回 3 能"
        fg.current_energy = 130.0
        before = _remaining(eng, "ally")
        ult = next(a for a in eng.actions_by_actor["1225"] if a.action_id == "122503")
        assert eng._fire_ultimate(fg, ult) is True
        assert math.isclose(before - _remaining(eng, "ally"), 2400.0, rel_tol=1e-9), (
            "E2② 全队行动提前 24%")

    def test_e4_break_dmg_boost(self):
        """E4：狐祈目标击破增伤 +20%（dmg_break_dmg_boost 桶键——击破/超击破共池）."""
        eng = _make(_compiled(eidolon=4))
        ally = eng.state.actors["ally"]
        _cast(eng, "1225", "122502", target=ally)
        assert math.isclose(
            eng.pipeline.effective_stats(ally)["dmg_bonus"].get("break_dmg_boost", 0.0),
            0.2, rel_tol=1e-9)

    def test_e6_team_wide_prayer(self):
        """E6：焚尾状态下狐祈全队覆盖（辅手/忘归人同挂 FOXIAN_PRAYER+E1+E4）；
        效率账：辅手=E1 0.5，忘归人=E1 0.5+E6① 0.5=1.0（双源加算官方语义）."""
        eng = _make(_compiled(eidolon=6))
        ally = eng.state.actors["ally"]
        _cast(eng, "1225", "122502", target=ally)
        for aid in ("1225", "ally"):
            st = eng.state.actors[aid]
            assert "FOXIAN_PRAYER" in st.modifiers
            assert "E1_BREAK_EFFICIENCY" in st.modifiers
            assert "E4_BREAK_DMG" in st.modifiers
        assert math.isclose(
            eng.pipeline.effective_stats(ally)["break_efficiency_boost"], 0.5, rel_tol=1e-9)
        assert math.isclose(
            eng.pipeline.effective_stats(_fg(eng))["break_efficiency_boost"],
            1.0, rel_tol=1e-9), "E6① 自身 0.5 + E1 狐祈 0.5（E6 全队覆盖自身同吃）"
