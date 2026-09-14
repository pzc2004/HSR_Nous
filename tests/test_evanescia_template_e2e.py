"""绯英 1505 模板端到端对轴（验收型批·欢愉体系首租）：真模板 YAML → 编译 →
双向转化/狐狸老师/欢愉伤害/弹射/行迹/星魂全链 → 手算全等.

口径常数：绯英 atk 737.352、crit_rate 0.05+行迹 0.487=0.537、crit_dmg 0.5（E2 起 0.86）、
spd 104+5、max_energy 480（终结技耗能 240——米游社/fandom 双源，勘正②）。
欢愉伤害（02 §2.14/08 §8.1 直消费）：7535.107(lv80)×倍率×1.18(行迹欢愉增伤)×
(1+0.2×暴伤)(天赋 #5 欢愉度)×(1+5X/(X+240))——X=好活当赏（终结技系保底 480）/欢愉技=笑点。
假人 def 1000 → 防御区 0.5（E4 起无视 15% → 1000/1850）；弱点匹配 → 抗性区 1.0
（E1 起抗穿 20% → 1.2）；未击破 0.9；期望暴击区 0.537×(1+暴伤)+0.463。
档位（幻视族谱 #1/#18）：lv10=index9、lv12=index11——终结技 lv12 全体 1.76/每跳 1.296、
战技 lv12 主 3.3/邻 1.65、天赋 lv12 狐狸 1.1/欢愉 0.275/0.264/0.176/0.308、普攻 lv7=1.1。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 737.352
CRIT_E0 = 0.537 * 1.5 + 0.463        # 1.2685（E0-1）
CRIT_E2 = 0.537 * 1.86 + 0.463       # 1.46182（E2 起暴伤 0.86）
DEF_E0 = 0.5                          # 假人 def 1000
DEF_E4 = 1000 / (1000 * 0.85 + 1000)  # E4 无视 15% 防御 → 1000/1850
ELA_LVL = 7535.107                    # 欢愉伤害等级系数 lv80（08 §8.1）
ELA_BOOST = 1.18                      # 行迹欢愉增伤 0.04+0.06+0.08（无引擎槽字面折入）
ELATION_E0 = 1 + 0.2 * 0.5            # 天赋 #5 欢愉度 = 20%×暴伤
ELATION_E2 = 1 + 0.2 * 0.86


def _punch(x: float) -> float:
    return 1 + 5 * x / (x + 240)      # 笑点/好活当赏乘区（08 §8.1）


def _phys(scale, *, crit=CRIT_E0, defz=DEF_E0, res=1.0, vuln=1.0):
    return ATK * scale * defz * res * 0.9 * vuln * crit


def _ela(ratio, x, *, crit=CRIT_E0, defz=DEF_E0, res=1.0, elation=ELATION_E0,
         merry=1.0, vuln=1.0):
    return (ELA_LVL * ratio * ELA_BOOST * elation * _punch(x)) * defz * res * 0.9 * vuln * crit * merry


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1505", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1505", "technique": "150507"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _fx(eng):
    return eng.state.actors["1505"]


def _hp(eng, aid):
    return eng.state.actors[aid].current_hp


def _cast(eng, aid, *, target="e1"):
    st = _fx(eng)
    a = next(x for x in eng.actions_by_actor["1505"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "1505", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _fx(eng)
    st.current_energy = 240.0
    ult = next(a for a in eng.actions_by_actor["1505"] if a.action_id == "150503")
    assert eng._fire_ultimate(st, ult) is True


class TestCompile:
    def test_actions_resources_and_costs(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1505"]}
        assert acts == {"150501", "150502", "150503"}, "欢愉技 150520 不落 action（阿哈通道待收）"
        ult = next(a for a in compiled.actions_by_actor["1505"] if a.action_id == "150503")
        assert ult.energy_cost == 240, "终结技耗能 240（勘正②——上限 480 另物）"
        skill = next(a for a in compiled.actions_by_actor["1505"] if a.action_id == "150502")
        assert math.isclose(skill.scaling[9]["atk"], 3.0), "战技 lv10 主目标 #2=3.0（勘正①错列）"
        assert math.isclose(skill.scaling_blast[9]["atk"], 1.5)
        assert math.isclose(skill.resource_gain["punchline"], 10.0), "战技 #4=笑点 10（勘正③）"
        decls = compiled.resource_decls_by_actor["1505"]
        assert decls["banger"]["max"] == 1000
        assert decls["punchline"]["max"] == "inf"
        assert "_fox_meter" in decls and "_e6_n" in decls


class TestPanelTrace:
    def test_trace_panel(self, compiled):
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_fx(eng))
        assert math.isclose(eff["crit_rate"], 0.05 + 0.487, rel_tol=1e-9), "行迹暴击 0.3+0.187"
        assert math.isclose(eff["spd"], 109.0, rel_tol=1e-9), "行迹速度 +5"
        assert math.isclose(eff["atk"], ATK, rel_tol=1e-9)


class TestBattleStart:
    def test_entry_grants(self, compiled):
        """进战 +20 好活当赏（→转化 +20 能量 → +20 累计）+ 每欢愉角色 +1 笑点（08 §8.1/§8.2）."""
        eng = _make(compiled)
        st = _fx(eng)
        assert math.isclose(st.resources["banger"], 20.0)
        assert math.isclose(st.current_energy, 20.0), "好活当赏→能量同步转化（单步互锁）"
        assert math.isclose(st.resources["_fox_meter"], 20.0)
        assert math.isclose(st.resources["punchline"], 1.0), "count_team(path='elation')=1"


class TestBasic:
    def test_basic_damage_and_conversions(self, compiled):
        """普攻 lv6=1.0 ATK：737.352×1.0×0.5×0.9×1.2685；回能 20 → banger/meter 各 +20."""
        eng = _make(compiled)
        st = _fx(eng)
        h1 = _hp(eng, "e1")
        _cast(eng, "150501")
        assert math.isclose(h1 - _hp(eng, "e1"), _phys(1.0), rel_tol=1e-9)
        assert math.isclose(st.current_energy, 40.0)
        assert math.isclose(st.resources["banger"], 40.0)
        assert math.isclose(st.resources["_fox_meter"], 40.0)
        assert math.isclose(eng.state.skill_points, 4.0)


class TestSkill:
    def test_blast_and_elation_follow(self, compiled):
        """战技 lv10：主 #2=3.0/邻 #3=1.5 + 笑点 10；持有好活当赏(50) → 双敌 #7=0.16 欢愉段
        （X=好活当赏——能量转化先于命中结算，on_action 时点 banger=50）."""
        eng = _make(compiled)
        st = _fx(eng)
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        _cast(eng, "150502")
        assert math.isclose(h1 - _hp(eng, "e1"), _phys(3.0) + _ela(0.16, 50), rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), _phys(1.5) + _ela(0.16, 50), rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0)
        assert math.isclose(st.current_energy, 50.0)
        assert math.isclose(st.resources["banger"], 50.0)
        assert math.isclose(st.resources["punchline"], 11.0), "进战 1 + 战技 10"

    def test_banger_gate_strict(self, compiled):
        """持有门控（严）：banger=0 时裸发 on_action（不走行动回能转化）→ 欢愉段零触发."""
        eng = _make(compiled)
        st = _fx(eng)
        st.resources["banger"] = 0.0
        h1 = _hp(eng, "e1")
        eng.bus.emit("on_action", {
            "actor": "1505", "action_type": "skill", "action_id": "150502",
            "target_type": "blast", "target": "e1", "actor_type": "character"}, eng.state)
        assert math.isclose(h1 - _hp(eng, "e1"), 0.0, abs_tol=1e-9), "无好活当赏无欢愉段"

    def test_banger_refill_via_conversion(self, compiled):
        """门控自愈链：banger=0 开战技 → 回能 30 先转化 30 好活当赏 → 欢愉段照发（X=30）
        ——官方「获得能量时同步获得等值好活当赏」，持有判定在命中时点."""
        eng = _make(compiled)
        st = _fx(eng)
        st.resources["banger"] = 0.0
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        _cast(eng, "150502")
        assert math.isclose(h1 - _hp(eng, "e1"), _phys(3.0) + _ela(0.16, 30), rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), _phys(1.5) + _ela(0.16, 30), rel_tol=1e-9)


class TestUltimate:
    def test_aoe_bounces_and_elation(self, compiled):
        """终结技 lv10：全体 1.6 + 弹射 7 段（2 敌 → 5+2）×1.2 落 e1（expected 布场序首敌）；
        欢愉段：全体 #6=0.24 + 弹射 #8=0.28×7——X 保底 max(25, 480)=480."""
        eng = _make(compiled)
        st = _fx(eng)
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        _ult(eng)
        x1 = (_phys(1.6) + _ela(0.24, 480)
              + 7 * _phys(1.2) + 7 * _ela(0.28, 480))
        assert math.isclose(h1 - _hp(eng, "e1"), x1, rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), _phys(1.6) + _ela(0.24, 480), rel_tol=1e-9)
        assert math.isclose(st.current_energy, 5.0), "240 全扣 + 终结技回 5"
        assert math.isclose(st.resources["banger"], 25.0)
        assert math.isclose(st.resources["_fox_meter"], 25.0)

    def test_floor_480_with_empty_banger(self, compiled):
        """终结技保底（官方「至少计入等同于能量上限的【好活当赏】」）：banger=0 开大，
        回能 5 转化 5 → X=max(5,480)=480——欢愉段与 banger=25 时逐值全等."""
        eng = _make(compiled)
        st = _fx(eng)
        st.resources["banger"] = 0.0
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        _ult(eng)
        x1 = (_phys(1.6) + _ela(0.24, 480)
              + 7 * _phys(1.2) + 7 * _ela(0.28, 480))
        assert math.isclose(h1 - _hp(eng, "e1"), x1, rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), _phys(1.6) + _ela(0.24, 480), rel_tol=1e-9)
        assert math.isclose(st.resources["banger"], 5.0)


class TestFoxChain:
    def test_threshold_trigger_and_vuln(self, compiled):
        """镜像累计 235+20=255 ≥240 即触发：先消耗 240（余 15）→ 物理 #1=1.0 全体 +
        欢愉 #2=0.25（X=40，读回能前 banger）→ 行裁断易伤 12% → 回能 10（余量 15+10=25）."""
        eng = _make(compiled)
        st = _fx(eng)
        st.resources["_fox_meter"] = 235.0
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        eng._grant_energy(st, 20.0, source="1505", action_id=None, reason="test")
        x = _phys(1.0) + _ela(0.25, 40)
        assert math.isclose(h1 - _hp(eng, "e1"), x, rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), x, rel_tol=1e-9)
        assert math.isclose(st.resources["banger"], 50.0), "20+20(转化)+10(狐狸回能转化)"
        assert math.isclose(st.resources["_fox_meter"], 25.0), "255-240+10 余量保留"
        assert math.isclose(st.current_energy, 50.0)
        for aid in ("e1", "e2"):
            assert math.isclose(eng.pipeline.effective_stats(eng.state.actors[aid])["vulnerability"],
                                0.12, rel_tol=1e-9), "行裁断 12% 易伤 3 回合"
        # 易伤入网：狐狸后的普攻吃 ×1.12（伤害后挂——狐狸本段不吃）
        h1 = _hp(eng, "e1")
        _cast(eng, "150501")
        assert math.isclose(h1 - _hp(eng, "e1"), _phys(1.0, vuln=1.12), rel_tol=1e-9)


class TestConversionCaps:
    def test_cap_direction_and_lock(self, compiled):
        """勘正④⑤：能量→好活当赏**无**单次上限（150 全计）；好活当赏→能量单次 ≤100；
        CONV_LOCK 互锁单步（转化产物不再转化——banger 320 而非 420）."""
        eng = _make(compiled)
        st = _fx(eng)
        st.resources["_fox_meter"] = 0.0
        eng._grant_energy(st, 150.0, source="1505", action_id=None, reason="test")
        assert math.isclose(st.resources["banger"], 170.0), "20+150——能量侧等值无 cap"
        assert math.isclose(st.resources["_fox_meter"], 150.0)
        assert math.isclose(st.current_energy, 170.0)
        st.resources["_fox_meter"] = 0.0
        eng._gain_resource(st, "banger", 150.0, source_id="1505")
        assert math.isclose(st.resources["banger"], 320.0), "不再二次转化（互锁单步）"
        assert math.isclose(st.current_energy, 270.0), "170+100——好活当赏侧单次 cap 100"
        assert math.isclose(st.resources["_fox_meter"], 100.0)


class TestTechnique:
    def test_pre_battle_loadout(self, compiled):
        """秘技：全体 100% ATK（削韧 20）+ 好活当赏 20 → 与进战 20 合计 40/40/40."""
        eng = _make(_compiled(pre_battle=True))
        st = _fx(eng)
        for aid in ("e1", "e2"):
            assert math.isclose(1e9 - _hp(eng, aid), _phys(1.0), rel_tol=1e-9)
        assert math.isclose(st.resources["banger"], 40.0)
        assert math.isclose(st.current_energy, 40.0)
        assert math.isclose(st.resources["_fox_meter"], 40.0)
        assert math.isclose(st.resources["punchline"], 1.0)


class TestBounceBranches:
    """行迹 1505101：弹射次数按存活敌数 +1/+2/+4（≥3→6 / =2→7 / =1→9——主文件 7 段
    支在 TestUltimate；本类补 6 段与 9 段支，expected 落点=布场序首敌）."""

    @staticmethod
    def _stage_n(n: int):
        return {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100, "weakness": ["physical"]}
            for i in range(1, n + 1)],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

    def _ult_n(self, n: int):
        c = compile_encounter(_build(), self._stage_n(n), template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        st = _fx(eng)
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1505"] if a.action_id == "150503")
        assert eng._fire_ultimate(st, ult) is True
        return eng

    def test_three_enemies_six_bounces(self):
        eng = self._ult_n(3)
        x1 = (_phys(1.6) + _ela(0.24, 480)
              + 6 * _phys(1.2) + 6 * _ela(0.28, 480))
        assert math.isclose(1e9 - _hp(eng, "e1"), x1, rel_tol=1e-9), "6 段全落首敌"
        for aid in ("e2", "e3"):
            assert math.isclose(1e9 - _hp(eng, aid), _phys(1.6) + _ela(0.24, 480),
                                rel_tol=1e-9)

    def test_one_enemy_nine_bounces(self):
        eng = self._ult_n(1)
        x1 = (_phys(1.6) + _ela(0.24, 480)
              + 9 * _phys(1.2) + 9 * _ela(0.28, 480))
        assert math.isclose(1e9 - _hp(eng, "e1"), x1, rel_tol=1e-9), "5+4=9 段"


class TestE1:
    def test_res_pen_and_fox_elation_skill(self):
        """E1：抗穿 20%（抗性区 1.2）+ 狐狸攻击后追加欢愉技（X=笑点=1；行裁断易伤先入
        网——欢愉技在狐狸主段后触发吃 ×1.12；欢愉技给 5+10=15 好活当赏 → 转化 15 能）."""
        eng = _make(_compiled(eidolon=1))
        st = _fx(eng)
        h1 = _hp(eng, "e1")
        _cast(eng, "150501")
        assert math.isclose(h1 - _hp(eng, "e1"), _phys(1.0, res=1.2), rel_tol=1e-9)
        st.resources["_fox_meter"] = 235.0
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        eng._grant_energy(st, 20.0, source="1505", action_id=None, reason="test")
        x = (_phys(1.0, res=1.2) + _ela(0.25, 60, res=1.2)
             + _ela(1.1, 1, res=1.2, vuln=1.12))
        assert math.isclose(h1 - _hp(eng, "e1"), x, rel_tol=1e-9)
        assert math.isclose(h2 - _hp(eng, "e2"), x, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 85.0), "40+20+10(狐狸)+15(欢愉技好活当赏转化)"
        assert math.isclose(st.resources["banger"], 85.0)
        assert math.isclose(st.resources["_fox_meter"], 40.0), "255-240+10+15"
        assert math.isclose(st.resources["punchline"], 1.0)


class TestE4:
    def test_def_pen_and_levels(self):
        """E4 无视 15% 防御（def_pen 全局槽）；联动：E1 抗穿 1.2、E2 暴伤 0.86、
        E3 普攻 lv7=1.1、期望暴击区 0.537×1.86+0.463."""
        eng = _make(_compiled(eidolon=4))
        st = _fx(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], 0.86, rel_tol=1e-9)
        assert math.isclose(eff["def_pen"], 0.15, rel_tol=1e-9)
        h1 = _hp(eng, "e1")
        _cast(eng, "150501")
        assert math.isclose(h1 - _hp(eng, "e1"),
                            _phys(1.1, crit=CRIT_E2, defz=DEF_E4, res=1.2), rel_tol=1e-9)


class TestE6Fox:
    def test_merrymake_scoped_and_rebake(self):
        """E6 增笑（scoped 只罩欢愉段）：开战烘焙 0.154（banger 20）；狐狸链中随 banger
        重烘——狐狸欢愉段 m=1.158（banger 40）、E1 欢愉技 m=1.16（banger 50）且吃易伤；
        物理段不吃增笑（merrymakeMulti 是欢愉专属乘区，勘正⑫）."""
        eng = _make(_compiled(eidolon=6))
        st = _fx(eng)
        assert math.isclose(st.modifiers["E6_MERRYMAKE"].stat_effects["all_dmg"],
                            0.15 + 0.02 * 0.2, rel_tol=1e-9)
        st.resources["_fox_meter"] = 235.0
        h1 = _hp(eng, "e1")
        eng._grant_energy(st, 20.0, source="1505", action_id=None, reason="test")
        x = (_phys(1.1, crit=CRIT_E2, defz=DEF_E4, res=1.2)
             + _ela(0.275, 40, crit=CRIT_E2, defz=DEF_E4, res=1.2,
                    elation=ELATION_E2, merry=1.158)
             + _ela(1.21, 1, crit=CRIT_E2, defz=DEF_E4, res=1.2,
                    elation=ELATION_E2, merry=1.16, vuln=1.12))
        assert math.isclose(h1 - _hp(eng, "e1"), x, rel_tol=1e-9)
        assert math.isclose(st.modifiers["E6_MERRYMAKE"].stat_effects["all_dmg"],
                            0.15 + 0.02 * 0.65, rel_tol=1e-9), "banger 65 → 0.163 重烘"
        assert math.isclose(st.current_energy, 65.0)
        assert math.isclose(st.resources["banger"], 65.0)
        assert math.isclose(st.resources["_fox_meter"], 40.0)


class TestE6Ult:
    def test_ult_lv12_and_first_cast_energy(self):
        """终结技 lv12（E3）：全体 1.76 + 弹射 7×1.296；天赋 lv12（E5）：欢愉 #6=0.264/
        #8=0.308（X 保底 480；增笑 m=1.155——banger 25 时点）；E6 首次终结技固定回 120
        （err_exempt）→ banger +120（无 cap——能量侧）→ 增笑重烘 0.179."""
        eng = _make(_compiled(eidolon=6))
        st = _fx(eng)
        h1, h2 = _hp(eng, "e1"), _hp(eng, "e2")
        _ult(eng)
        x1 = (_phys(1.76, crit=CRIT_E2, defz=DEF_E4, res=1.2)
              + _ela(0.264, 480, crit=CRIT_E2, defz=DEF_E4, res=1.2,
                     elation=ELATION_E2, merry=1.155)
              + 7 * _phys(1.296, crit=CRIT_E2, defz=DEF_E4, res=1.2)
              + 7 * _ela(0.308, 480, crit=CRIT_E2, defz=DEF_E4, res=1.2,
                         elation=ELATION_E2, merry=1.155))
        assert math.isclose(h1 - _hp(eng, "e1"), x1, rel_tol=1e-9)
        x2 = (_phys(1.76, crit=CRIT_E2, defz=DEF_E4, res=1.2)
              + _ela(0.264, 480, crit=CRIT_E2, defz=DEF_E4, res=1.2,
                     elation=ELATION_E2, merry=1.155))
        assert math.isclose(h2 - _hp(eng, "e2"), x2, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 125.0), "240 全扣 +5 +120（首次固定回）"
        assert math.isclose(st.resources["banger"], 145.0), "20+5+120"
        assert math.isclose(st.resources["_fox_meter"], 145.0)
        assert math.isclose(st.resources["_e6_n"], 1.0)
        assert math.isclose(st.modifiers["E6_MERRYMAKE"].stat_effects["all_dmg"],
                            0.15 + 0.02 * 1.45, rel_tol=1e-9)

    def test_every_four_ults_cadence(self):
        """E6 节拍=第 1/5/9… 次终结技（勘正⑬ %4 闩）：能量序 125/5/5/5/125
        （第 5 次前置镜像清零——隔开狐狸阈值链，专验回能节拍）."""
        eng = _make(_compiled(eidolon=6))
        st = _fx(eng)
        seq = []
        for i in range(5):
            if i == 4:
                st.resources["_fox_meter"] = 0.0
            _ult(eng)
            seq.append(st.current_energy)
        assert seq == [125.0, 5.0, 5.0, 5.0, 125.0]
        assert math.isclose(st.resources["_e6_n"], 5.0)
