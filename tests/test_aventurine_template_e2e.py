"""砂金 1304 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 护盾同池/盲注全链/
追加攻击 bounce×7/免控闩/Leverage 动态暴击/行迹/星魂全链 → 手算全等.

口径常数：砂金 def 654.885（行迹 def_pct 0.35 → 有效 884.09475）、crit 0.05/0.5、
spd 106、max_energy 110；行迹 dmg_imaginary 0.144（增伤区 1.144）、effect_res 0.10。
假人 def 1000 → 防御区 0.5、虚数弱点 → 抗性区 1.0、未击破 0.9、期望暴击 1.025
（E1 带盾暴伤 +0.2 → 1.035）。护盾 lv10 = 0.24×884.09475+320 = 532.18274（cap 2×），
lv12 = 0.256×884.09475+356 = 582.328256；Bingo 盾 = 0.072×884.09475+96 = 159.654822。
普攻 lv6=1.0 DEF；终结技 lv10=2.7（lv12=2.916）；追击 lv10=0.25/段（lv12=0.275）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

AV_DEF = 654.885
DEF_EFF = AV_DEF * 1.35            # 行迹 def_pct 0.35 → 884.09475
DMG_Z = 1.144                      # 行迹 dmg_imaginary 0.144
Z0 = 0.5 * 0.9 * (1 + 0.05 * 0.5)  # 防御区 × 未击破 × 期望暴击（E0）
Z1 = 0.5 * 0.9 * (1 + 0.05 * 0.7)  # E1 带盾暴伤 +0.2
SHIELD10 = 0.24 * DEF_EFF + 320    # 532.18274
CAP10 = 2 * SHIELD10               # 1064.36548
SHIELD12 = 0.256 * DEF_EFF + 356   # 582.328256
CAP12 = 2 * SHIELD12               # 1164.656512
BINGO = 0.072 * DEF_EFF + 96       # 159.654822
E4_DEF = AV_DEF * 1.75             # E4 def_pct +0.4 并入行迹 0.35 → 1146.04875


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1304", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1},
                     {"action_id": "ally_fua", "name": "追击", "action_type": "follow_up",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1304", "technique": "130407"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]}],
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


def _av(eng):
    return eng.state.actors["1304"]


def _pool(eng, aid):
    """坚垣筹码 accumulate 池合计（同池跨件加算口径——04_modifier §4.15）."""
    return sum(s.remaining for s in eng.state.actors[aid].shields
               if s.pool == "fortified_wager")


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


def _ult(eng, *, energy: float = 110.0):
    st = _av(eng)
    st.current_energy = energy
    ult = next(a for a in eng.actions_by_actor["1304"] if a.action_id == "130403")
    assert eng._fire_ultimate(st, ult) is True


class TestAventurineCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1304"]}
        assert acts == {"130401", "130402", "130403", "130404"}
        fua = next(a for a in compiled.actions_by_actor["1304"] if a.action_id == "130404")
        assert (fua.action_type, fua.target_type, fua.instances) == ("follow_up", "bounce", 7)
        assert fua.energy_gain == 7            # 米游社逐段 1×7（行动级一次记账）
        assert fua.toughness_dmg == 3          # int 闸截断（官方 3.3/段——缺口在案，勿改断言）
        decls = compiled.resource_decls_by_actor["1304"]
        assert decls["blind_bet"]["max"] == 10   # 官方 "Blind Bet is capped at 10"
        assert decls["bingo_stack"]["max"] == 3
        assert decls["cc_immune_cd"]["max"] == 2

    def test_battle_start_panel(self, compiled):
        """行迹属性回填 + Hot Hand 开局盾 + 效果抵抗门控（标记在→0.6）+ Leverage 0 档."""
        eng = _make(compiled)
        st = _av(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["def_"], DEF_EFF, rel_tol=1e-9), "行迹 def_pct 0.35"
        assert math.isclose(eff["dmg_bonus"]["imaginary"], 0.144, rel_tol=1e-9), "行迹虚数 3 节点"
        assert math.isclose(eff["effect_res"], 0.10 + 0.5, rel_tol=1e-9), (
            "行迹 0.10 + 天赋 0.5（lv10 param——标记在门控过）")
        assert math.isclose(eff["crit_rate"], 0.05, rel_tol=1e-9), (
            "Leverage 0 档（884.09 < 1600——stat_exprs 动态通道）")
        assert math.isclose(eff["crit_dmg"], 0.5, rel_tol=1e-9)
        assert float(st.actor.stats.max_energy) == 110
        assert math.isclose(_pool(eng, "1304"), SHIELD10, rel_tol=1e-9), (
            "Hot Hand = 100% 战技盾 = 0.24×884.09475+320")
        assert math.isclose(_pool(eng, "ally"), SHIELD10, rel_tol=1e-9)
        assert all("FORTIFIED_WAGER" in eng.state.actors[a].modifiers for a in ("1304", "ally"))
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])["effect_res"],
            0.5, rel_tol=1e-9), "辅手无行迹——效果抵抗仅天赋 0.5"


class TestBasicSkill:
    def test_basic_damage_energy_sp(self, compiled):
        """普攻 lv6：1.0×有效DEF × 增伤 1.144 × 防御区 0.5 × 未击破 0.9 × 期望暴击 1.025；回 20 能 +1 点."""
        eng = _make(compiled)
        st, e1 = _av(eng), eng.state.actors["e1"]
        _cast(eng, "1304", "130401")
        assert math.isclose(1e9 - e1.current_hp, 1.0 * DEF_EFF * DMG_Z * Z0, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(eng.state.skill_points, 4.0)

    def test_skill_shield_pool_and_cap(self, compiled):
        """战技：耗 1 点回 30 能；护盾同池加算——Hot Hand 532.18 + 战技 532.18 = cap 恰满；
        第二次战技池不越 cap（200% 当次战技盾截断）."""
        eng = _make(compiled)
        st = _av(eng)
        _cast(eng, "1304", "130402")
        assert math.isclose(eng.state.skill_points, 2.0)
        assert math.isclose(st.current_energy, 30.0)
        for aid in ("1304", "ally"):
            assert math.isclose(_pool(eng, aid), CAP10, rel_tol=1e-9), (
                "532.18274 × 2 = cap（ accumulate 同池加算至恰封顶）")
        _cast(eng, "1304", "130402")
        for aid in ("1304", "ally"):
            assert math.isclose(_pool(eng, aid), CAP10, rel_tol=1e-9), "cap 截断不越顶"
        assert math.isclose(st.current_energy, 60.0)


class TestUltChain:
    def test_ult_blindbet_fua_bingo_chain(self, compiled):
        """终结技全链：2.7×DEF 单攻 → 盲注 +7（确定化上界）→ 满 7 消耗触发 bounce×7
        （期望模式全中 e1）→ Bingo!② 全队追盾 + 最低盾加追（同值平手站位序=砂金）
        → 盲注归零；回能 5（终结技）+7（追击）=12。「不安」死件摘除不留痕."""
        eng = _make(compiled)
        st, e1, e2 = _av(eng), eng.state.actors["e1"], eng.state.actors["e2"]
        _ult(eng)
        fua_hit = 0.25 * DEF_EFF * DMG_Z * Z0
        assert math.isclose(1e9 - e1.current_hp,
                            2.7 * DEF_EFF * DMG_Z * Z0 + 7 * fua_hit, rel_tol=1e-9), (
            "终结技 lv10 + 7 段追击全中 e1")
        assert math.isclose(1e9 - e2.current_hp, 0.0), "e2 不受击"
        assert math.isclose(st.resources["blind_bet"], 0.0), "满 7 触发后消耗归零"
        assert math.isclose(st.current_energy, 5.0 + 7.0), "终结技 5 + 追击 7"
        # Bingo!②：全队 +159.65；最低盾（平手站位序首=砂金）再 +159.65
        assert math.isclose(_pool(eng, "1304"), SHIELD10 + 2 * BINGO, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "ally"), SHIELD10 + BINGO, rel_tol=1e-9)
        assert "UNNERVED" not in e1.modifiers, "「不安」= crit_dmg_taken 死键——摘除记待收，不留死件"


class TestBlindBetAccumulation:
    def _become(self, eng, source, target):
        eng.bus.emit("on_become_target", {
            "action_id": "e_atk", "action_type": "basic", "insert": False,
            "source": source, "target": target}, eng.state)

    def test_attacked_gains_and_enemy_source_filter(self, compiled):
        """带盾我方被敌方攻击 +1；砂金本人被击 +2（官方 additionally 叠加）；
        过堂补敌方源过滤——我方技能点带盾队友不产点（官方 "get attacked"）."""
        eng = _make(compiled)
        st = _av(eng)
        self._become(eng, "e1", "ally")
        assert math.isclose(st.resources["blind_bet"], 1.0), "带盾队友被击 +1"
        self._become(eng, "e1", "1304")
        assert math.isclose(st.resources["blind_bet"], 3.0), "砂金本人被击 +2（两钩叠加）"
        self._become(eng, "ally", "1304")     # 我方源——不过滤则假阳
        assert math.isclose(st.resources["blind_bet"], 3.0), "我方源不产点（get attacked 明文）"
        eng._remove_modifier(eng.state.actors["ally"], "FORTIFIED_WAGER", "test")
        self._become(eng, "e1", "ally")
        assert math.isclose(st.resources["blind_bet"], 3.0), "无盾标记被击不产点"

    def test_bingo1_cap_and_turn_reset(self, compiled):
        """Bingo!①：队友 FUA 产点 ≤3/回合（计数闩），砂金回合开始重置；跨过 7 即触发追击."""
        eng = _make(compiled)
        st = _av(eng)
        for _ in range(3):
            _cast(eng, "ally", "ally_fua")
        assert math.isclose(st.resources["blind_bet"], 3.0)
        assert math.isclose(st.resources["bingo_stack"], 3.0)
        _cast(eng, "ally", "ally_fua")
        assert math.isclose(st.resources["blind_bet"], 3.0), "每回合 3 次上限闩"
        eng.bus.emit("on_turn_start", {"actor": "1304"}, eng.state)
        assert math.isclose(st.resources["bingo_stack"], 0.0), "砂金回合开始重置计数"
        _cast(eng, "ally", "ally_fua")
        assert math.isclose(st.resources["blind_bet"], 4.0)

    def test_bingo1_crosses_seven_triggers_fua(self, compiled):
        """产点链跨 7 → 立即触发（嵌套于队友 FUA 事件内）：盲注 6 → +1 → 追击 7 段 → 归零."""
        eng = _make(compiled)
        st, e1 = _av(eng), eng.state.actors["e1"]
        eng._gain_resource(st, "blind_bet", 6.0)
        assert math.isclose(st.resources["blind_bet"], 6.0), "6 < 7 不触发"
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_fua")   # 辅手 FUA 伤害 + 砂金追击 7 段（全中 e1）
        ally_hit = 1500 * 1.0 * 0.5 * 0.9 * 1.025 * 0.8   # 火 vs 虚数弱点 → 非弱点抗性区 0.8
        assert math.isclose(hp0 - e1.current_hp,
                            ally_hit + 7 * 0.25 * DEF_EFF * DMG_Z * Z0, rel_tol=1e-9)
        assert math.isclose(st.resources["blind_bet"], 0.0)


class TestCCImmune:
    @staticmethod
    def _control():
        return Modifier(modifier_id="TEST_CTRL", name="测试冻结", modifier_type="debuff",
                        debuff_kind="control", duration=2, dispellable=True, source_id="e1")

    def test_immune_then_cd_then_recover(self, compiled):
        """免控全链：带标记免疫（grants_immune control）→ on_immune 置 CD 2 → 二次失控
        → 砂金两回合开始递减归零 → 恢复可免疫."""
        eng = _make(compiled)
        st = _av(eng)
        assert eng._apply_modifier(st, self._control()) is False, "首次免疫（硬拒）"
        assert "TEST_CTRL" not in st.modifiers
        assert math.isclose(st.resources["cc_immune_cd"], 2.0), "on_immune 置 CD 2"
        assert eng._apply_modifier(st, self._control()) is True, "CD 内门控关——失控"
        assert "TEST_CTRL" in st.modifiers
        eng._remove_modifier(st, "TEST_CTRL", "test")
        eng.bus.emit("on_turn_start", {"actor": "1304"}, eng.state)
        assert math.isclose(st.resources["cc_immune_cd"], 1.0)
        eng.bus.emit("on_turn_start", {"actor": "1304"}, eng.state)
        assert math.isclose(st.resources["cc_immune_cd"], 0.0)
        assert eng._apply_modifier(st, self._control()) is False, "CD 归零恢复免疫"

    def test_no_marker_no_immune(self, compiled):
        """无坚垣筹码标记 → enable_if 门控关 → 不免疫（条件免疫随启用态开关）."""
        eng = _make(compiled)
        st = _av(eng)
        eng._remove_modifier(st, "FORTIFIED_WAGER", "test")
        assert eng._apply_modifier(st, self._control()) is True


class TestLeverage:
    def test_dynamic_crit_rate(self, compiled):
        """Leverage：DEF 超 1600 每 100 → +2%（round 近似在案）。外挂 def_pct 1.5 →
        DEF = 654.885×(1+0.35+1.5) = 1866.42225 → round(2.6642)=3 → 暴击率 0.05+0.06=0.11."""
        eng = _make(compiled)
        st = _av(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05, rel_tol=1e-9)
        eng._apply_modifier(st, Modifier(
            modifier_id="TEST_DEF", name="测试防御", modifier_type="buff", duration=0,
            dispellable=False, stat_effects={"def_pct": 1.5}, source_id="1304"))
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["def_"], AV_DEF * 2.85, rel_tol=1e-9)
        assert math.isclose(eff["crit_rate"], 0.05 + 0.02 * 3, rel_tol=1e-9), (
            "stat_exprs 现场追档（非挂点烘焙）")


class TestEidolons:
    def test_e1_crit_dmg_and_ult_shield(self):
        """E1 囚徒博弈：带盾暴伤 +0.2（期望暴击区 1.035）；终结技后全队追战技盾
        → 池顶 cap（Hot Hand + Bingo + E1 超顶截断）."""
        eng = _make(_compiled(eidolon=1))
        st = _av(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"], 0.7, rel_tol=1e-9)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"], 0.7, rel_tol=1e-9)
        _ult(eng)
        for aid in ("1304", "ally"):
            assert math.isclose(_pool(eng, aid), CAP10, rel_tol=1e-9), (
                "532.18(HotHand)+159.65×2(Bingo)+532.18(E1) → cap 1064.37 截断")

    def test_e2_no_dead_modifier(self):
        """E2 有限理性摘除记待收——普攻后敌方无抗性降低 modifier（死件不留）."""
        eng = _make(_compiled(eidolon=2))
        e1 = eng.state.actors["e1"]
        _cast(eng, "1304", "130401")
        assert "E2_ALL_RES_DOWN" not in e1.modifiers

    def test_e4_def_up_extra_hits_energy(self):
        """E4 意外绞刑：追击触发 → DEF +40%（7 段本体不吃本次加防——近似在案）
        + 追加 3 段（吃加防后面板）+ 逐段回能 +3；E1 联动期望暴击区 1.035."""
        eng = _make(_compiled(eidolon=4))
        st, e1 = _av(eng), eng.state.actors["e1"]
        _ult(eng)
        assert "E4_DEF_UP" in st.modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], E4_DEF, rel_tol=1e-9)
        expect = (2.916 * DEF_EFF * DMG_Z * Z1               # E3 联动：终结技 lv12（非 2.7）
                  + 7 * 0.25 * DEF_EFF * DMG_Z * Z1          # 7 段本体 lv10（无本次加防）
                  + 3 * 0.25 * E4_DEF * DMG_Z * Z1)          # E4 追加 3 段（吃 +40%）
        assert math.isclose(1e9 - e1.current_hp, expect, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 5.0 + 7.0 + 3.0), "终结技 5 + 追击 7 + E4 段 3"

    def test_e5_level_overrides_full_chain(self):
        """E3+E5 跳档联动（eidolon=5 全激活）：终结技 lv12=2.916 / 追击 lv12=0.275 /
        战技盾 lv12=0.256+356 / 效果抵抗 lv12=0.55 / 普攻 lv7=1.1（E1 在→1.035）."""
        eng = _make(_compiled(eidolon=5))
        st, e1 = _av(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(st)["effect_res"],
                            0.10 + 0.55, rel_tol=1e-9), "天赋效果抵抗随档 lv12（param 通道）"
        assert math.isclose(_pool(eng, "1304"), SHIELD12, rel_tol=1e-9), "Hot Hand 随档 lv12"
        _cast(eng, "1304", "130402")
        assert math.isclose(_pool(eng, "1304"), CAP12, rel_tol=1e-9), "战技盾 lv12 ×2 = cap"
        _ult(eng)
        expect = (2.916 * DEF_EFF * DMG_Z * Z1
                  + 7 * 0.275 * DEF_EFF * DMG_Z * Z1
                  + 3 * 0.275 * E4_DEF * DMG_Z * Z1)
        assert math.isclose(1e9 - e1.current_hp, expect, rel_tol=1e-9), (
            "终结技 lv12 + 追击 lv12×7 + E4×3")
        assert math.isclose(st.current_energy, 5.0 + 7.0 + 3.0)
        hp1 = e1.current_hp
        _cast(eng, "1304", "130401")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * E4_DEF * DMG_Z * Z1, rel_tol=1e-9), (
            "普攻 lv7=1.1（E3 +1——draft 误写 0.7 勘正在案）；E4 加防 2 回合未到期，"
            "DEF 缩放普攻吃 1146.04875")


class TestTechnique:
    def test_red_black_def_and_hot_hand_order(self):
        """秘技（保守最低档 24%）：DEF = 654.885×(1+0.35+0.24) = 1041.26715；
        装填预置先于模板钩 → Hot Hand 盾读加防后面板 = 0.24×1041.26715+320."""
        eng = _make(_compiled(pre_battle=True))
        st = _av(eng)
        tech_def = AV_DEF * 1.59
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], tech_def, rel_tol=1e-9)
        assert math.isclose(_pool(eng, "1304"), 0.24 * tech_def + 320, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05, rel_tol=1e-9), (
            "1041 < 1600——Leverage 仍 0 档")
