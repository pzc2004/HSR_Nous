"""存护（Knight）光锥族 e2e：staging→fixtures 验收批.

16 件验收 fixture（tests/fixtures/templates/light_cones/）→ 编译 → 白值三围 + 机制行为
（手算对轴）+ 命途限制分例（preservation 触发 / 其他命途不触发）+ 叠影 S1→S5 差分。
勘正条目与各件待实测清单见 fixture 头注。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / def 0 / crit 0.05/0.5 / lv80；
假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、未击破 0.9、期望暴击区 1.025
（直伤链 Z=0.5×0.9×1.025=0.46125——灼烧跳伤走 hook deal_damage 同链，1109 虎克 Burn
先例口径）；inline 成员白板嘲讽种子 stats.taunt=100（build_compiler 缺省，显式值优先于
rulebook path_base——故 taunt_eff 基准 100 而非 150），aggro_boost 池 ×(1+Σ)；
能量恢复效率基础 1.0（乘区起点）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

Z = 0.5 * 0.9 * 1.025          # 直伤链：防御区×未击破×期望暴击区（lv80 vs def 1000 假人）

_BASIC = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_FUA = {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
        "target_type": "single", "damage_type": "fire",
        "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_ULT = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "fire",
        "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_cost": 100}

#: 13 件白值三围（pipeline lv80 实值，与 fixture 数值区一致——loader 白值病修复后口径）
LC_BASE = {
    "20003": (846.72, 264.6, 330.75),
    "20010": (952.56, 264.6, 264.6),
    "20017": (952.56, 264.6, 264.6),
    "21002": (952.56, 370.44, 463.05),
    "21009": (952.56, 423.36, 396.9),
    "21016": (1058.4, 370.44, 396.9),
    "21023": (740.88, 476.28, 463.05),
    "21030": (846.72, 370.44, 529.2),
    "21039": (952.56, 370.44, 463.05),
    "21043": (952.56, 370.44, 463.05),
    "21053": (1058.4, 370.44, 529.2),
    "23005": (1058.4, 476.28, 595.35),
    "23011": (1270.08, 423.36, 529.2),
    "23023": (1058.4, 423.36, 661.5),
    "23051": (1058.4, 582.12, 463.05),
    "24002": (1058.4, 423.36, 529.2),
}
LC_IDS = list(LC_BASE)


def _member(aid, lc_id=None, *, s=1, path="", actions=(), spd=100):
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100},
         "actions": list(actions) or [_BASIC]}
    if lc_id is not None:
        m["light_cone_template"] = lc_id
        m["light_cone"] = {"superimposition": s}
    if path:
        m["path"] = path
    return m


def _build(members):
    return {"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _one(lc_id, *, s=1, path="preservation", actions=(), ally=False):
    """单装备员（可选带一名 harmony 队友）."""
    members = [_member("w", lc_id, s=s, path=path, actions=actions)]
    if ally:
        members.append(_member("ally", path="harmony",
                               actions=[_BASIC, dict(_ULT, action_id="a_ult")]))
    return _make(_build(members))


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _hp(eng, aid):
    return eng.state.actors[aid].current_hp


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


def _cast(eng, owner, aid, target_id="e1"):
    """手动施放（8009 模子）：行动结算 + 补发 on_action（hook 触发域）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, owner, target_id="e1"):
    """满能手动开大（_fire_ultimate 漏斗：on_action + on_ultimate 双发）."""
    st = eng.state.actors[owner]
    st.current_energy = st.actor.stats.max_energy
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_type == "ultimate")
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


def _hit(eng, target, source="e1", action_type="basic"):
    """受击事件驱动（克拉拉先例 _hit_clara 模子）."""
    eng.bus.emit("after_being_hit", {
        "target": target, "source": source, "amount": 100.0,
        "action_type": action_type, "damage_type": "physical"}, eng.state)


class TestBaseStats:
    """白值三围：面板 = 成员白值 + 光锥白值（pct 被动不碰 hp/atk——除 23011 hp_pct
    与 23051 atk_pct 两件单独折算）."""

    @pytest.mark.parametrize("lc_id", LC_IDS)
    def test_base_stats_s1(self, lc_id):
        eng = _one(lc_id, s=1)
        hp, atk, df = LC_BASE[lc_id]
        eff = _eff(eng, "w")
        hp_pct = {"23011": 1.24}.get(lc_id, 1.0)
        atk_pct = {"23051": 1.64}.get(lc_id, 1.0)
        assert math.isclose(eff["hp"], (3000 + hp) * hp_pct, rel_tol=1e-9)
        assert math.isclose(eff["atk"], (1000 + atk) * atk_pct, rel_tol=1e-9)
        assert math.isclose(eff["spd"], 100.0, rel_tol=1e-9)

    @pytest.mark.parametrize("lc_id", LC_IDS)
    def test_base_stats_still_apply_off_path(self, lc_id):
        """命途不符只封技能，白值照给（光锥基础规则）."""
        eng = _one(lc_id, s=1, path="destruction")
        hp, atk, df = LC_BASE[lc_id]
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3000 + hp, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1000 + atk, rel_tol=1e-9)
        assert math.isclose(eff["def_"], df, rel_tol=1e-9)   # 防御%被动全封 → 白值原样


# ---------------------------------------------------------------------------
# 20003 琥珀：常驻防御% + 低血（<50%）额外防御%（enable_if 条件光环）
# ---------------------------------------------------------------------------
class TestLC20003:
    def test_def_full_and_low_hp_s1(self):
        eng = _one("20003", s=1)
        # S1：常驻 #1=0.16 → def = 330.75×1.16
        assert math.isclose(_eff(eng, "w")["def_"], 330.75 * 1.16, rel_tol=1e-9)
        # 压血到 40%（<50% 阈值 #2）→ 追加 #3=0.16 → 330.75×1.32
        eng.state.actors["w"].current_hp = 0.4 * _eff(eng, "w")["hp"]
        assert math.isclose(_eff(eng, "w")["def_"], 330.75 * 1.32, rel_tol=1e-9)

    def test_def_full_and_low_hp_s5(self):
        eng = _one("20003", s=5)
        assert math.isclose(_eff(eng, "w")["def_"], 330.75 * 1.32, rel_tol=1e-9)
        eng.state.actors["w"].current_hp = 0.4 * _eff(eng, "w")["hp"]
        assert math.isclose(_eff(eng, "w")["def_"], 330.75 * 1.64, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("20003", s=1, path="destruction")
        assert math.isclose(_eff(eng, "w")["def_"], 330.75, rel_tol=1e-9)
        eng.state.actors["w"].current_hp = 0.4 * _eff(eng, "w")["hp"]
        assert math.isclose(_eff(eng, "w")["def_"], 330.75, rel_tol=1e-9), "命途不符低血件也不生效"


# ---------------------------------------------------------------------------
# 20010 戍御：装备者施放终结技 → 按自身生命上限回血
# ---------------------------------------------------------------------------
class TestLC20010:
    def test_ult_heal_s1(self):
        eng = _one("20010", s=1, actions=[_BASIC, _ULT], ally=True)
        w = eng.state.actors["w"]
        w.current_hp = 1000.0
        _ult(eng, "w")
        # S1：#1=0.18 × max_hp(3000+952.56=3952.56) = 711.4608
        assert math.isclose(_hp(eng, "w"), 1000.0 + 0.18 * 3952.56, rel_tol=1e-9)
        hp_before = _hp(eng, "w")
        _ult(eng, "ally")
        assert math.isclose(_hp(eng, "w"), hp_before, rel_tol=1e-9), "队友开大不触发（source 过滤）"

    def test_ult_heal_s5(self):
        eng = _one("20010", s=5, actions=[_BASIC, _ULT])
        eng.state.actors["w"].current_hp = 1000.0
        _ult(eng, "w")
        assert math.isclose(_hp(eng, "w"), 1000.0 + 0.30 * 3952.56, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("20010", s=1, path="destruction", actions=[_BASIC, _ULT])
        eng.state.actors["w"].current_hp = 1000.0
        _ult(eng, "w")
        assert math.isclose(_hp(eng, "w"), 1000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 20017 开疆：装备者击破弱点 → 按自身生命上限回血
# ---------------------------------------------------------------------------
class TestLC20017:
    def test_break_heal_s1(self):
        eng = _one("20017", s=1)
        eng.state.actors["w"].current_hp = 1000.0
        eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                  "source": "w", "target": "e1"}, eng.state)
        assert math.isclose(_hp(eng, "w"), 1000.0 + 0.12 * 3952.56, rel_tol=1e-9)
        hp_before = _hp(eng, "w")
        eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                  "source": "ally", "target": "e1"}, eng.state)
        assert math.isclose(_hp(eng, "w"), hp_before, rel_tol=1e-9), "他人击破不触发"

    def test_break_heal_s5(self):
        eng = _one("20017", s=5)
        eng.state.actors["w"].current_hp = 1000.0
        eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                  "source": "w", "target": "e1"}, eng.state)
        assert math.isclose(_hp(eng, "w"), 1000.0 + 0.20 * 3952.56, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("20017", s=1, path="destruction")
        eng.state.actors["w"].current_hp = 1000.0
        eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                  "source": "w", "target": "e1"}, eng.state)
        assert math.isclose(_hp(eng, "w"), 1000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21009 朗道的选择：受击概率提高（aggro_boost）+ 受伤降低（dmg_dmg_reduction）
# ---------------------------------------------------------------------------
class TestLC21009:
    def test_passive_s1(self):
        eng = _one("21009", s=1)
        eff = _eff(eng, "w")
        assert math.isclose(eff["dmg_bonus"]["dmg_reduction"], 0.16, rel_tol=1e-9)
        assert math.isclose(eff["taunt_eff"], 100 * (1 + 2.0), rel_tol=1e-9), (
            "inline 白板嘲讽 100 ×(1+#1=2) = 300")

    def test_passive_s5(self):
        eng = _one("21009", s=5)
        eff = _eff(eng, "w")
        assert math.isclose(eff["dmg_bonus"]["dmg_reduction"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["taunt_eff"], 300.0, rel_tol=1e-9), "#1 全档恒定 2 → 嘲讽不随档"

    def test_path_gate(self):
        eng = _one("21009", s=1, path="destruction")
        eff = _eff(eng, "w")
        assert math.isclose(eff["dmg_bonus"].get("dmg_reduction", 0.0), 0.0, abs_tol=1e-12)
        assert math.isclose(eff["taunt_eff"], 100.0, rel_tol=1e-9), "无 aggro_boost → 白板种子 100"


# ---------------------------------------------------------------------------
# 21016 宇宙市场趋势：常驻防御% + 受击基础概率灼烧（装备者防御% DoT）
# ---------------------------------------------------------------------------
class TestLC21016:
    def test_def_and_burn_s1(self):
        eng = _one("21016", s=1, ally=True)
        # S1：常驻 #1=0.16 → def = 396.9×1.16 = 460.404
        def_eff = 396.9 * 1.16
        assert math.isclose(_eff(eng, "w")["def_"], def_eff, rel_tol=1e-9)
        _hit(eng, "w")                                  # 装备者受击 → 攻击方挂灼烧
        assert "LC_21016_BURN" in _mods(eng, "e1")
        assert _mods(eng, "e1")["LC_21016_BURN"].duration == 2   # #4 全档恒定 2 回合
        hp1 = _hp(eng, "e1")
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        # 灼烧跳伤 = def_eff×#3(0.4)×Z（1109 虎克 Burn 同链口径，含期望暴击区——待实测注见头注）
        assert math.isclose(hp1 - _hp(eng, "e1"), def_eff * 0.4 * Z, rel_tol=1e-9)

    def test_no_trigger_on_ally_hit(self):
        eng = _one("21016", s=1, ally=True)
        _hit(eng, "ally")                               # 队友受击 ≠ 装备者受击
        assert "LC_21016_BURN" not in _mods(eng, "e1")

    def test_burn_s5(self):
        eng = _one("21016", s=5)
        def_eff = 396.9 * 1.32                          # S5 #1=0.32
        assert math.isclose(_eff(eng, "w")["def_"], def_eff, rel_tol=1e-9)
        _hit(eng, "w")
        hp1 = _hp(eng, "e1")
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - _hp(eng, "e1"), def_eff * 0.8 * Z, rel_tol=1e-9), (
            "S5 #3=0.8 灼烧跳伤差分")

    def test_path_gate(self):
        eng = _one("21016", s=1, path="destruction")
        assert math.isclose(_eff(eng, "w")["def_"], 396.9, rel_tol=1e-9)
        _hit(eng, "w")
        assert "LC_21016_BURN" not in _mods(eng, "e1")


# ---------------------------------------------------------------------------
# 21023 我们是地火：开战全队减伤 5 回合 + 按各自已损失生命回血
# ---------------------------------------------------------------------------
class TestLC21023:
    def test_battle_start_s1(self):
        eng = _one("21023", s=1, ally=True)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["dmg_reduction"], 0.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["dmg_reduction"], 0.08, rel_tol=1e-9)
        assert _mods(eng, "w")["LC_21023_DMG_DOWN"].duration == 5   # #3 全档恒定 5 回合
        # 满血开战 → 治疗量 0；压血后重发开战事件 → 各自已损失生命 ×#1(0.3)
        eng.state.actors["w"].current_hp = 2000.0       # max 3740.88 → 缺 1740.88
        eng.state.actors["ally"].current_hp = 1000.0    # max 3000 → 缺 2000
        eng.bus.emit("on_battle_start", {"encounter": "s"}, eng.state)
        assert math.isclose(_hp(eng, "w"), 2000.0 + 0.3 * 1740.88, rel_tol=1e-9)
        assert math.isclose(_hp(eng, "ally"), 1000.0 + 0.3 * 2000.0, rel_tol=1e-9)

    def test_s5(self):
        eng = _one("21023", s=5, ally=True)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["dmg_reduction"], 0.16, rel_tol=1e-9)
        eng.state.actors["ally"].current_hp = 1000.0
        eng.bus.emit("on_battle_start", {"encounter": "s"}, eng.state)
        assert math.isclose(_hp(eng, "ally"), 1000.0 + 0.5 * 2000.0, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("21023", s=1, path="destruction", ally=True)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"].get("dmg_reduction", 0.0), 0.0, abs_tol=1e-12)
        eng.state.actors["ally"].current_hp = 1000.0
        eng.bus.emit("on_battle_start", {"encounter": "s"}, eng.state)
        assert math.isclose(_hp(eng, "ally"), 1000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21030 这就是我啦！：常驻防御%（终结技伤害值段待收——base_dmg_add 通道未接线）
# ---------------------------------------------------------------------------
class TestLC21030:
    def test_def_s1(self):
        eng = _one("21030", s=1)
        assert math.isclose(_eff(eng, "w")["def_"], 529.2 * 1.16, rel_tol=1e-9)

    def test_def_s5(self):
        eng = _one("21030", s=5)
        assert math.isclose(_eff(eng, "w")["def_"], 529.2 * 1.32, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("21030", s=1, path="destruction")
        assert math.isclose(_eff(eng, "w")["def_"], 529.2, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21039 织造命运之线：效果抵抗 + 防御转增伤（stat_exprs 现场求值）
# ---------------------------------------------------------------------------
class TestLC21039:
    def test_passive_s1(self):
        eng = _one("21039", s=1)
        eff = _eff(eng, "w")
        assert math.isclose(eff["effect_res"], 0.12, rel_tol=1e-9)
        # all_dmg = min(def/100×0.008, 0.32) = 463.05/100×0.008
        assert math.isclose(eff["dmg_bonus"]["all"], 463.05 / 100 * 0.008, rel_tol=1e-9)

    def test_passive_s5(self):
        eng = _one("21039", s=5)
        eff = _eff(eng, "w")
        assert math.isclose(eff["effect_res"], 0.20, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["all"], 463.05 / 100 * 0.012, rel_tol=1e-9)

    def test_stat_exprs_live_update(self):
        """stat_exprs 懒求值：战中防御变化即刻反映（非快照）."""
        eng = _one("21039", s=1)
        from hsr_nous.sim.state import Modifier
        eng._apply_modifier(eng.state.actors["w"], Modifier(
            modifier_id="T_DEF_UP", name="测试加防", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"def_pct": 1.0}))
        # def = 463.05×2 → all_dmg = min(926.1/100×0.008, 0.32)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"],
                            463.05 * 2 / 100 * 0.008, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("21039", s=1, path="destruction")
        eff = _eff(eng, "w")
        assert math.isclose(eff["effect_res"], 0.0, abs_tol=1e-12)
        assert math.isclose(eff["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 23005 制胜的瞬间：常驻防御%/效果命中/受击概率 + 受击后防御%（到自身回合结束）
# ---------------------------------------------------------------------------
class TestLC23005:
    def test_passive_and_hit_s1(self):
        eng = _one("23005", s=1, ally=True)
        eff = _eff(eng, "w")
        assert math.isclose(eff["def_"], 595.35 * 1.24, rel_tol=1e-9)
        assert math.isclose(eff["effect_hit"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["taunt_eff"], 300.0, rel_tol=1e-9)
        _hit(eng, "w")
        # 受击后再 +#3=0.24 → 595.35×1.48；时长 1（到自身回合结束）
        assert math.isclose(_eff(eng, "w")["def_"], 595.35 * 1.48, rel_tol=1e-9)
        assert _mods(eng, "w")["LC_23005_HIT_DEF"].duration == 1
        _hit(eng, "ally")
        assert math.isclose(_eff(eng, "w")["def_"], 595.35 * 1.48, rel_tol=1e-9), (
            "队友受击不叠加（主体过滤）")

    def test_s5(self):
        eng = _one("23005", s=5)
        assert math.isclose(_eff(eng, "w")["def_"], 595.35 * 1.4, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.4, rel_tol=1e-9)
        _hit(eng, "w")
        assert math.isclose(_eff(eng, "w")["def_"], 595.35 * 1.8, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("23005", s=1, path="destruction")
        eff = _eff(eng, "w")
        assert math.isclose(eff["def_"], 595.35, rel_tol=1e-9)
        assert math.isclose(eff["effect_hit"], 0.0, abs_tol=1e-12)
        assert math.isclose(eff["taunt_eff"], 100.0, rel_tol=1e-9)
        _hit(eng, "w")
        assert math.isclose(_eff(eng, "w")["def_"], 595.35, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23011 她已闭上双眼：生命%/能量恢复效率 + 降血全队增伤 + 波次全队回血
# ---------------------------------------------------------------------------
class TestLC23011:
    def test_passive_and_triggers_s1(self):
        eng = _one("23011", s=1, ally=True)
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], (3000 + 1270.08) * 1.24, rel_tol=1e-9)
        assert math.isclose(eff["energy_regen"], 1.0 + 0.12, rel_tol=1e-9)
        # 装备者生命值降低 → 全队增伤 #2=0.09，持续 2 回合（#5 全档恒定）
        eng.bus.emit("on_hp_decrease", {
            "amount": 1.0, "source": "e1", "reason": "hit", "target": "w",
            "damage_type": "fire", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.09, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["all"], 0.09, rel_tol=1e-9)
        assert _mods(eng, "ally")["LC_23011_TEAM_DMG"].duration == 2
        # 波次开始 → 各自已损失生命 ×#3(0.8)
        eng.state.actors["w"].current_hp = 2000.0       # max 5294.8992 → 缺 3294.8992
        eng.state.actors["ally"].current_hp = 1000.0    # max 3000 → 缺 2000
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(_hp(eng, "w"), 2000.0 + 0.8 * 3294.8992, rel_tol=1e-9)
        assert math.isclose(_hp(eng, "ally"), 1000.0 + 0.8 * 2000.0, rel_tol=1e-9)

    def test_s5(self):
        eng = _one("23011", s=5, ally=True)
        assert math.isclose(_eff(eng, "w")["hp"], (3000 + 1270.08) * 1.4, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.0 + 0.20, rel_tol=1e-9)
        eng.bus.emit("on_hp_decrease", {
            "amount": 1.0, "source": "e1", "reason": "hit", "target": "w",
            "damage_type": "fire", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["all"], 0.15, rel_tol=1e-9)
        eng.state.actors["ally"].current_hp = 1000.0
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(_hp(eng, "ally"), 3000.0, rel_tol=1e-9), "#3=1.0 → 全额补满"

    def test_path_gate(self):
        eng = _one("23011", s=1, path="destruction", ally=True)
        assert math.isclose(_eff(eng, "w")["hp"], 3000 + 1270.08, rel_tol=1e-9)
        eng.bus.emit("on_hp_decrease", {
            "amount": 1.0, "source": "e1", "reason": "hit", "target": "w",
            "damage_type": "fire", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-12)
        eng.state.actors["ally"].current_hp = 1000.0
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(_hp(eng, "ally"), 1000.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23023 命运从未公平：常驻防御% + 追加攻击命中挂易伤（供盾暴伤段待收）
# ---------------------------------------------------------------------------
class TestLC23023:
    def test_def_and_fua_vuln_s1(self):
        eng = _one("23023", s=1, actions=[_BASIC, _FUA])
        assert math.isclose(_eff(eng, "w")["def_"], 661.5 * 1.4, rel_tol=1e-9)
        _cast(eng, "w", "t_fua")
        assert "LC_23023_FUA_VULN" in _mods(eng, "e1"), "追加命中挂易伤（#4=1.0 期望必中）"
        assert _mods(eng, "e1")["LC_23023_FUA_VULN"].duration == 2   # #6 全档恒定 2
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.10, rel_tol=1e-9)

    def test_basic_no_vuln(self):
        eng = _one("23023", s=1, actions=[_BASIC, _FUA])
        _cast(eng, "w", "t_basic")
        assert "LC_23023_FUA_VULN" not in _mods(eng, "e1"), "普攻命中不挂（action_type 过滤）"

    def test_fua_vuln_s5(self):
        eng = _one("23023", s=5, actions=[_BASIC, _FUA])
        assert math.isclose(_eff(eng, "w")["def_"], 661.5 * 1.64, rel_tol=1e-9)
        _cast(eng, "w", "t_fua")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.16, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("23023", s=1, path="destruction", actions=[_BASIC, _FUA])
        assert math.isclose(_eff(eng, "w")["def_"], 661.5, rel_tol=1e-9)
        _cast(eng, "w", "t_fua")
        assert "LC_23023_FUA_VULN" not in _mods(eng, "e1")


# ---------------------------------------------------------------------------
# 23051 纵然山河万程：常驻攻击% + 终结技全队回血/最低血额外 + 卫戍（召唤物追加）
# ---------------------------------------------------------------------------
class TestLC23051:
    def test_atk_and_ult_s1(self):
        eng = _one("23051", s=1, actions=[_BASIC, _ULT], ally=True)
        atk_eff = (1000 + 582.12) * 1.64                # S1 #1=0.64
        assert math.isclose(_eff(eng, "w")["atk"], atk_eff, rel_tol=1e-9)
        eng.state.actors["w"].current_hp = 2000.0       # max 4058.4
        eng.state.actors["ally"].current_hp = 500.0     # 最低血 = ally
        _ult(eng, "w")
        heal = atk_eff * 0.1                            # #5=0.1 全队
        assert math.isclose(_hp(eng, "w"), 2000.0 + heal, rel_tol=1e-9)
        assert math.isclose(_hp(eng, "ally"), 500.0 + heal * 2, rel_tol=1e-9), (
            "最低血队友再吃 #6=0.1 额外回复")
        # 卫戍：全队基础增伤 #2=0.24；召唤物追加件挂上但无召唤物 → 门控关闭不计面板
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        assert "LC_23051_REDOUBT_SUMMON" in _mods(eng, "ally")
        assert _mods(eng, "ally")["LC_23051_REDOUBT"].duration == 3   # #4 全档恒定 3 回合

    def test_ult_s5(self):
        eng = _one("23051", s=5, actions=[_BASIC, _ULT], ally=True)
        atk_eff = (1000 + 582.12) * (1 + 1.28)          # S5 #1=1.28
        assert math.isclose(_eff(eng, "w")["atk"], atk_eff, rel_tol=1e-9)
        eng.state.actors["ally"].current_hp = 500.0
        _ult(eng, "w")
        assert math.isclose(_hp(eng, "ally"), 500.0 + atk_eff * 0.2 * 2, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["all"], 0.48, rel_tol=1e-9)

    def test_ally_ult_no_trigger(self):
        eng = _one("23051", s=1, actions=[_BASIC, _ULT], ally=True)
        eng.state.actors["ally"].current_hp = 500.0
        _ult(eng, "ally")
        assert math.isclose(_hp(eng, "ally"), 500.0, rel_tol=1e-9), "队友开大不触发（source 过滤）"
        assert "LC_23051_REDOUBT" not in _mods(eng, "ally")

    def test_path_gate(self):
        eng = _one("23051", s=1, path="destruction", actions=[_BASIC, _ULT], ally=True)
        assert math.isclose(_eff(eng, "w")["atk"], 1000 + 582.12, rel_tol=1e-9)
        eng.state.actors["ally"].current_hp = 500.0
        _ult(eng, "w")
        assert math.isclose(_hp(eng, "ally"), 500.0, rel_tol=1e-9)
        assert "LC_23051_REDOUBT" not in _mods(eng, "ally")


# ---------------------------------------------------------------------------
# 24002 记忆的质料：常驻效果抵抗（获盾/持盾减伤段待收——shield 数值槽不收
# 叠影绑定 + 无 has_shield 宿主，见 fixture 头注④）
# ---------------------------------------------------------------------------
class TestLC24002:
    def test_effect_res_s1(self):
        eng = _one("24002", s=1)
        assert math.isclose(_eff(eng, "w")["effect_res"], 0.08, rel_tol=1e-9)

    def test_effect_res_s5(self):
        eng = _one("24002", s=5)
        assert math.isclose(_eff(eng, "w")["effect_res"], 0.16, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _one("24002", s=1, path="destruction")
        assert math.isclose(_eff(eng, "w")["effect_res"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 21002 余生的第一天：防御常驻（全抗半待收——all_type_res 死键无消费端）
# ---------------------------------------------------------------------------
class TestLC21002:
    def test_def_s1(self):
        eng = _one("21002", s=1)
        assert math.isclose(_eff(eng, "w")["def_"], 463.05 * 1.16, rel_tol=1e-9)

    def test_def_s5(self):
        eng = _one("21002", s=5)
        assert math.isclose(_eff(eng, "w")["def_"], 463.05 * 1.24, rel_tol=1e-9)

    def test_all_res_pending(self):
        """全属性抗性半待收（fixture 头注挡因）——无全抗 modifier（不硬凑锚）."""
        eng = _one("21002", s=1)
        assert "LC_21002_ALL_RES" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 21043 两个人的演唱会：防御常驻（持盾计数增伤半待收）
# ---------------------------------------------------------------------------
class TestLC21043:
    def test_def_s1(self):
        eng = _one("21043", s=1)
        assert math.isclose(_eff(eng, "w")["def_"], 463.05 * 1.16, rel_tol=1e-9)

    def test_def_s5(self):
        eng = _one("21043", s=5)
        assert math.isclose(_eff(eng, "w")["def_"], 463.05 * 1.32, rel_tol=1e-9)

    def test_shield_count_dmg_pending(self):
        """持盾角色计数增伤待收（fixture 头注挡因——无 shield 计数查询通道）."""
        eng = _one("21043", s=1)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 21053 愿旅途永远坦然：护盾量常驻（持盾增伤半待收）
# ---------------------------------------------------------------------------
class TestLC21053:
    def test_shield_bonus_s1(self):
        eng = _one("21053", s=1)
        assert math.isclose(_eff(eng, "w")["shield_bonus"], 0.12, rel_tol=1e-9)

    def test_shield_bonus_s5(self):
        eng = _one("21053", s=5)
        assert math.isclose(_eff(eng, "w")["shield_bonus"], 0.24, rel_tol=1e-9)

    def test_shielded_dmg_pending(self):
        """「我方目标持有护盾时伤害提高」待收（fixture 头注挡因）."""
        eng = _one("21053", s=1)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-12)
