"""智识（Mage/Erudition）光锥族 e2e：staging→fixtures 验收批.

本族 22 件（20006/20013/20020/21006/21013/21020/21027/21034/21040/21045/21060/
22004/23000/23010/23018/23028/23033/23037/23041/23060/23061/24004），逐件：
白值三围断言（面板 = 角色基值 + 光锥白值，数值区 = pipeline.calc_light_cone_stats Lv80 实值）
+ 机制行为断言手算对轴（假人 def 1000 → 防御区 1000/(def_eff+1000)；弱点全配 → 抗性 1.0；
未击破 0.9；期望暴击 crit_expected = min(1,cr)×(1+cd)+(1-min(1,cr))，基线 0.05/0.5 → 1.025）
+ 叠影差分（S1 行为断言 + S1/S5 绑定参数全族对轴）。

命途限制分例说明：本族 22 件官方叠影文本均无「装备者命途为智识时」条件句
（light_cone_ranks.json cn desc 逐件复核），无 path_of 门控件——命途限制分例不适用；
模板 path: Mage 仅为声明字段（引擎对光锥机制不做命途闸，见验收报告遗留项）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 模子（验收手册光锥 e2e 模子 + 本族扩展件）
# ---------------------------------------------------------------------------

_BASIC = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
          "energy_gain": 0, "skill_point_cost": -1}
_SKILL = {"action_id": "t_skill", "name": "战技", "action_type": "skill",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
          "energy_gain": 0, "skill_point_cost": 1}
_ULT = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "fire", "energy_cost": 100,
        "scaling": [{"atk": 1.0}], "toughness_dmg": 30, "energy_gain": 0}
_FUA = {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
        "target_type": "single", "damage_type": "fire",
        "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}
_ASSIST = {"action_id": "t_assist", "name": "助战", "action_type": "assist",
           "target_type": "single", "damage_type": "fire",
           "scaling": [{"atk": 1.0}], "toughness_dmg": 0, "energy_gain": 0}


def _member(lc_id, s=1, actions=(_BASIC,), max_energy=100):
    return {"actor_id": "w", "name": "装备员", "inline": True, "path": "erudition",
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": max_energy},
            "light_cone_template": lc_id,
            "light_cone": {"superimposition": s},
            "actions": list(actions)}


def _stage(hp=1e9, max_toughness=100, count=1):
    enemies = [{"actor_id": f"e{i + 1}", "name": f"假人{i + 1}", "hp": hp, "spd": 100,
                "atk": 1000, "def": 1000, "max_toughness": max_toughness,
                "weakness": ["fire", "ice", "thunder", "wind",
                             "quantum", "imaginary", "physical"]}
               for i in range(count)]
    return {"stage": {"stage_id": "s", "enemies": enemies,
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(lc_id, s=1, actions=(_BASIC,), max_energy=100, hp=1e9, max_toughness=100, count=1):
    build = {"build": {"team": [_member(lc_id, s, actions, max_energy)],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _stage(hp, max_toughness, count),
                          template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _force_target(eng, target_id):
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))


def _cast(eng, aid, target_id="e1", owner="w"):
    """行动施放模子（照抄 8009/110-120 e2e——_execute_action + on_action 广播）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    _force_target(eng, target_id)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": eng.state.actors[target_id].actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, owner="w", aid="t_ult", target_id="e1"):
    """手动插队开大（ult_now 同漏斗）：能量拉满 → _fire_ultimate（内部序：结算→on_action→on_ultimate）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    _force_target(eng, target_id)
    st.current_energy = float(a.energy_cost or st.actor.stats.max_energy)
    assert eng._fire_ultimate(st, a) is True


def _assist(eng, owner="w", aid="t_assist", target_id="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    _force_target(eng, target_id)
    assert eng.fire_assist(st, a) is True


def _hp(eng, aid):
    return eng.state.actors[aid].current_hp


def _energy(eng, aid="w"):
    return eng.state.actors[aid].current_energy


def _remaining(eng, aid="w"):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _dmg(atk, boost=0.0, *, tgt_def=1000.0, def_pen=0.0, crit_rate=0.05, crit_dmg=0.5,
         broken=False):
    """期望伤害手算对轴：atk×(1+增伤)×防御区×抗性1.0×期望暴击×虚弱区（余区全 1）."""
    def_multi = 1000.0 / (tgt_def * max(0.0, 1.0 - def_pen) + 1000.0)
    cr = min(1.0, crit_rate)
    crit = cr * (1.0 + crit_dmg) + (1.0 - cr)
    return atk * (1.0 + boost) * def_multi * crit * (1.0 if broken else 0.9)


#: 白值三围（生成器实值——loader 白值病修复后复核全部 20 件 == pipeline.calc_light_cone_stats Lv80）
_WHITE = {
    "20006": (740.88, 370.44, 264.6),
    "20013": (740.88, 370.44, 264.6),
    "20020": (740.88, 370.44, 264.6),
    "21006": (952.56, 476.28, 330.75),
    "21013": (846.72, 476.28, 396.9),
    "21020": (846.72, 476.28, 396.9),
    "21027": (846.72, 476.28, 396.9),
    "21034": (846.72, 529.2, 330.75),
    "21040": (952.56, 476.28, 330.75),
    "21045": (846.72, 476.28, 396.9),
    "21060": (952.56, 529.2, 396.9),
    "22004": (952.56, 476.28, 330.75),
    "23000": (1164.24, 582.12, 396.9),
    "23010": (1058.4, 582.12, 463.05),
    "23018": (1058.4, 582.12, 463.05),
    "23033": (952.56, 582.12, 529.2),
    "23028": (952.56, 582.12, 529.2),
    "23037": (952.56, 635.04, 463.05),
    "23041": (952.56, 582.12, 529.2),
    "23060": (846.72, 635.04, 529.2),
    "23061": (846.72, 635.04, 529.2),
    "24004": (1058.4, 529.2, 396.9),
}

#: 叠影差分对轴（首绑定参数 S1/S5 官方 params 行值；21045/21060/23010/23018/23033/23037/23061
#: 生成器语义命名 crit_rate/crit_dmg/break_effect 与 $self 面板键同名死参——fixture 已更名 param_1）
_PARAM_S1_S5 = {
    "20006": ("param_1", 0.28, 0.56), "20013": ("param_1", 8.0, 12.0),
    "20020": ("param_1", 0.24, 0.48), "21006": ("param_1", 0.24, 0.48),
    "21013": ("param_1", 0.32, 0.64), "21020": ("atk_pct", 0.16, 0.32),
    "21027": ("param_1", 0.12, 0.24), "21034": ("param_1", 0.002, 0.004),
    "21040": ("atk_pct", 0.16, 0.24), "21045": ("param_1", 0.28, 0.56),
    "21060": ("param_1", 0.12, 0.2), "23000": ("param_1", 0.3, 0.5),
    "23010": ("param_1", 0.36, 0.6), "23018": ("param_1", 0.36, 0.6),
    "23033": ("param_1", 0.6, 1.0), "23037": ("param_1", 0.12, 0.2),
    "23028": ("param_1", 0.16, 0.28), "23041": ("param_2", 0.12, 0.24),
    "22004": ("atk_pct", 0.08, 0.16), "23060": ("param_7", 0.32, 0.48),
    "23061": ("param_1", 0.18, 0.3), "24004": ("atk_pct", 0.08, 0.12),
}


class TestWhiteStatsAndSuperimposition:
    @pytest.mark.parametrize("lc_id", sorted(_WHITE))
    def test_base_stats_merge(self, lc_id):
        """白值三围并入基础面板（角色 3000/1000/0 + 光锥白值——读 Layer 0 StatBlock，
        隔离常驻 buff 的有效面板扰动）."""
        eng = _make(lc_id)
        hp, atk, def_ = _WHITE[lc_id]
        st = eng.state.actors["w"].actor.stats
        assert st.hp == pytest.approx(3000 + hp)
        assert st.atk == pytest.approx(1000 + atk)
        assert st.def_ == pytest.approx(def_)

    @pytest.mark.parametrize("lc_id", sorted(_PARAM_S1_S5))
    def test_superimposition_binding(self, lc_id):
        """叠影查表取档：S1/S5 绑定参数 = 官方 params 第 1/5 行."""
        name, v1, v5 = _PARAM_S1_S5[lc_id]
        eng1 = _make(lc_id, 1)
        eng5 = _make(lc_id, 5)
        assert math.isclose(eng1._binding_params["w"][name], v1), f"{lc_id} S1"
        assert math.isclose(eng5._binding_params["w"][name], v5), f"{lc_id} S5"


# ---------------------------------------------------------------------------
# 20006 智库：终结技伤害 +28%（S1）
# ---------------------------------------------------------------------------

class TestLC20006:
    def test_ult_dmg_boost_panel_and_damage(self):
        eng = _make("20006", actions=(_ULT,))
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.28)
        before = _hp(eng, "e1")
        _ult(eng)
        atk = 1000 + 370.44
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.28))

    def test_basic_unaffected(self):
        eng = _make("20006", actions=(_BASIC,))
        atk = 1000 + 370.44
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.0)), "普攻不吃终结技桶"

    def test_s5_boost(self):
        eng = _make("20006", 5, actions=(_ULT,))
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.56)


# ---------------------------------------------------------------------------
# 20013 灵钥：施放战技后额外回 8 能（S1），单回合内不可重复触发
# ---------------------------------------------------------------------------

class TestLC20013:
    def test_skill_energy_once_per_turn(self):
        eng = _make("20013", actions=(_SKILL,))
        _cast(eng, "t_skill")
        assert _energy(eng) == pytest.approx(8.0), "战技后额外 +8 能（行动本身 energy_gain 0 隔离）"
        _cast(eng, "t_skill")
        assert _energy(eng) == pytest.approx(8.0), "限流锁：单回合内不再触发"
        eng.bus.emit("on_turn_end", {"actor": "w"}, eng.state)
        _cast(eng, "t_skill")
        assert _energy(eng) == pytest.approx(16.0), "装备者回合结束摘锁 → 下回合可再触发"

    def test_other_actor_turn_end_keeps_lock(self):
        eng = _make("20013", actions=(_SKILL,))
        _cast(eng, "t_skill")
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        _cast(eng, "t_skill")
        assert _energy(eng) == pytest.approx(8.0), "非装备者回合结束不摘锁（$event.actor 过滤）"

    def test_s5_energy(self):
        eng = _make("20013", 5, actions=(_SKILL,))
        _cast(eng, "t_skill")
        assert _energy(eng) == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# 20020 睿见：施放终结技时攻击力 +24%（S1）持续 2 回合
# ---------------------------------------------------------------------------

class TestLC20020:
    def test_atk_boost_after_ult(self):
        eng = _make("20020", actions=(_ULT,))
        atk0 = 1000 + 370.44
        assert _panel(eng)["atk"] == pytest.approx(atk0)
        _ult(eng)
        assert _panel(eng)["atk"] == pytest.approx(atk0 * 1.24)
        assert eng.state.actors["w"].modifiers["LC_20020_SAGACITY_ATK"].duration == 2

    def test_s5_atk_boost(self):
        eng = _make("20020", 5, actions=(_ULT,))
        _ult(eng)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 370.44) * 1.48)


# ---------------------------------------------------------------------------
# 21006 「我」的诞生：追加攻击伤害 +24%（S1）；低血额外段待实测（头注）
# ---------------------------------------------------------------------------

class TestLC21006:
    def test_follow_up_boost_and_damage(self):
        eng = _make("21006", actions=(_FUA,))
        assert _panel(eng)["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.24)
        atk = 1000 + 476.28
        before = _hp(eng, "e1")
        _cast(eng, "t_fua")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.24))

    def test_basic_unaffected(self):
        eng = _make("21006", actions=(_BASIC,))
        atk = 1000 + 476.28
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.0)), "普攻不吃追加桶"

    def test_s5_boost(self):
        eng = _make("21006", 5, actions=(_FUA,))
        assert _panel(eng)["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.48)


# ---------------------------------------------------------------------------
# 21013 别让世界静下来：进战回 20 能 + 终结技伤害 +32%（S1）
# ---------------------------------------------------------------------------

class TestLC21013:
    def test_battle_start_energy_and_boost(self):
        eng = _make("21013", actions=(_ULT,))
        assert _energy(eng) == pytest.approx(20.0), "进战立即恢复 20 能（initial_energy_ratio 0）"
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.32)
        atk = 1000 + 476.28
        before = _hp(eng, "e1")
        _ult(eng)
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.32))

    def test_s5(self):
        eng = _make("21013", 5, actions=(_ULT,))
        assert _energy(eng) == pytest.approx(32.0)
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.64)


# ---------------------------------------------------------------------------
# 21020 天才们的休憩：攻击 +16%（S1）常驻；消灭敌方后暴伤 +24% 持续 3 回合
# ---------------------------------------------------------------------------

class TestLC21020:
    def test_permanent_atk(self):
        eng = _make("21020")
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.16)

    def test_crit_dmg_on_kill(self):
        eng = _make("21020", hp=500)   # 一击必杀（普攻期望 ≈771 > 500）
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)
        _cast(eng, "t_basic")
        assert not eng.state.actors["e1"].alive, "击杀前提"
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.24)
        m = eng.state.actors["w"].modifiers["LC_21020_CRIT_DMG"]
        assert m.duration == 3 and m.dispellable is False

    def test_s5(self):
        eng = _make("21020", 5)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.32)


# ---------------------------------------------------------------------------
# 21027 早餐的仪式感：增伤 +12%（S1）常驻；每消灭 1 敌攻击 +4%（最多 3 层）
# ---------------------------------------------------------------------------

class TestLC21027:
    def test_permanent_all_dmg(self):
        eng = _make("21027")
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.12)

    def test_kill_stacks_to_cap(self):
        eng = _make("21027", hp=400, count=4)   # 普攻期望 ≈745 > 400，逐个点杀
        atk0 = 1000 + 476.28
        for i, want in enumerate((0.04, 0.08, 0.12, 0.12), start=1):
            _cast(eng, "t_basic", target_id=f"e{i}")
            assert _panel(eng)["atk"] == pytest.approx(atk0 * (1 + want)), (
                f"第 {i} 杀后攻击 +{want:.0%}（cap 3 层）")
        m = eng.state.actors["w"].modifiers["LC_21027_BF_ATK_STACK"]
        assert m.stacks == 3, "max_stack 3 钳住第 4 杀"

    def test_s5(self):
        eng = _make("21027", 5)
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.24)


# ---------------------------------------------------------------------------
# 21034 今日亦是和平的一日：按能量上限增伤 每点 0.2%（S1）最多计入 160
# ---------------------------------------------------------------------------

class TestLC21034:
    def test_all_dmg_by_energy_cap(self):
        eng = _make("21034")   # max_energy 100 → 100×0.002 = 0.20
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.2)
        atk = 1000 + 529.2
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.2))

    def test_energy_cap_clamp(self):
        eng = _make("21034", max_energy=200)   # min(200,160)=160 → 160×0.002 = 0.32
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.32)

    def test_s5(self):
        eng = _make("21034", 5)
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 21040 银河沦陷日：攻击 +16%（S1）常驻；弱点计数暴伤段待实测（头注）
# ---------------------------------------------------------------------------

class TestLC21040:
    def test_permanent_atk(self):
        eng = _make("21040")
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.16)

    def test_s5(self):
        eng = _make("21040", 5)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.24)


# ---------------------------------------------------------------------------
# 21045 谐乐静默之后：击破特攻 +28%（S1）常驻；终结技后速度 +8% 持续 2 回合
# ---------------------------------------------------------------------------

class TestLC21045:
    def test_permanent_break_effect(self):
        eng = _make("21045")
        assert _panel(eng)["break_effect"] == pytest.approx(0.28)

    def test_spd_after_ult(self):
        eng = _make("21045", actions=(_ULT,))
        assert _panel(eng)["spd"] == pytest.approx(100.0)
        _ult(eng)
        assert _panel(eng)["spd"] == pytest.approx(108.0)
        assert eng.state.actors["w"].modifiers["LC_21045_SPD_UP_AFTER_ULT"].duration == 2

    def test_s5(self):
        eng = _make("21045", 5, actions=(_ULT,))
        assert _panel(eng)["break_effect"] == pytest.approx(0.56)
        _ult(eng)
        assert _panel(eng)["spd"] == pytest.approx(116.0)


# ---------------------------------------------------------------------------
# 21060 氤氲麦香的梦：暴击率 +12%（S1）；终结技/追加攻击伤害 +24%
# ---------------------------------------------------------------------------

class TestLC21060:
    def test_panel_and_fua_damage(self):
        eng = _make("21060", actions=(_FUA,))
        eff = _panel(eng)
        assert eff["crit_rate"] == pytest.approx(0.17)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.24)
        assert eff["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.24)
        atk = 1000 + 529.2
        before = _hp(eng, "e1")
        _cast(eng, "t_fua")
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.24, crit_rate=0.17))

    def test_s5(self):
        eng = _make("21060", 5, actions=(_ULT,))
        eff = _panel(eng)
        assert eff["crit_rate"] == pytest.approx(0.25)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 23000 银河铁道之夜：每敌攻击 +9%（S1，最多 5 层）；击破后增伤 +30% 持续 1 回合
# ---------------------------------------------------------------------------

class TestLC23000:
    def test_atk_per_enemy_live(self):
        """stat_exprs 活读敌数：2 敌 → +18%，杀 1 敌后立即回落 +9%（烘焙快照做不到）."""
        eng = _make("23000", count=2, hp=400)
        atk0 = 1000 + 582.12
        assert _panel(eng)["atk"] == pytest.approx(atk0 * (1 + 0.09 * 2))
        _cast(eng, "t_basic", target_id="e1")   # 点杀 e1（期望 ≈767 > 400）
        assert _panel(eng)["atk"] == pytest.approx(atk0 * (1 + 0.09 * 1))

    def test_all_dmg_on_break(self):
        eng = _make("23000", max_toughness=10)   # 普攻削韧 10 → 一击即破
        _cast(eng, "t_basic")
        assert eng.state.actors["e1"].broken, "击破前提"
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.3)
        m = eng.state.actors["w"].modifiers["LC_23000_DMG_ON_BREAK"]
        assert m.duration == 1
        atk = (1000 + 582.12) * 1.09   # 1 敌 → +9%
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.3, broken=True)), "击破后增伤 30% + 已击破无 0.9 虚弱"

    def test_s5(self):
        eng = _make("23000", 5)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 582.12) * 1.15)


# ---------------------------------------------------------------------------
# 23010 拂晓之前：暴伤 +36%（S1）/ 战技终结技 +18% 常驻；【梦身】消耗式追加 +48%
# ---------------------------------------------------------------------------

class TestLC23010:
    def test_permanent_panel(self):
        eng = _make("23010", actions=(_SKILL,))
        eff = _panel(eng)
        assert eff["crit_dmg"] == pytest.approx(0.86)
        assert eff["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.18)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.18)
        assert eff["dmg_bonus"].get("follow_up_dmg_boost", 0.0) == pytest.approx(0.0), (
            "无梦身 → enable_if 关 → 追加桶 0")

    def test_somnus_cycle(self):
        """战技得梦身 → 追加当次吃 +48%（结算时梦身仍在挂）→ 结算后消耗 → 下次追加不加."""
        eng = _make("23010", actions=(_SKILL, _FUA))
        atk = 1000 + 582.12
        _cast(eng, "t_skill")
        assert "LC_23010_SOMNUS" in eng.state.actors["w"].modifiers
        assert _panel(eng)["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.48)
        before = _hp(eng, "e1")
        _cast(eng, "t_fua")
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.48, crit_dmg=0.86)), "触发当次追加吃梦身增伤"
        assert "LC_23010_SOMNUS" not in eng.state.actors["w"].modifiers, "追加后消耗梦身"
        before = _hp(eng, "e1")
        _cast(eng, "t_fua")
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.0, crit_dmg=0.86)), "无梦身追加不加成"

    def test_ult_grants_somnus(self):
        eng = _make("23010", actions=(_ULT,))
        _ult(eng)
        assert "LC_23010_SOMNUS" in eng.state.actors["w"].modifiers, (
            "on_action 终结技同发（B37）——施放终结技亦得梦身")

    def test_s5(self):
        eng = _make("23010", 5)
        eff = _panel(eng)
        assert eff["crit_dmg"] == pytest.approx(1.1)
        assert eff["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# 23018 片刻，留在眼底：暴伤 +36%（S1）；终结技伤害按能量上限 每点 0.36% 最多 180
# ---------------------------------------------------------------------------

class TestLC23018:
    def test_panel_and_ult_damage(self):
        eng = _make("23018", actions=(_ULT,))   # max_energy 100 → 100×0.0036 = 0.36
        eff = _panel(eng)
        assert eff["crit_dmg"] == pytest.approx(0.86)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.36)
        atk = 1000 + 582.12
        before = _hp(eng, "e1")
        _ult(eng)
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.36, crit_dmg=0.86))

    def test_energy_cap_clamp(self):
        eng = _make("23018", actions=(_ULT,), max_energy=200)   # min(200,180)=180 → 0.648
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.648)

    def test_s5(self):
        eng = _make("23018", 5, actions=(_ULT,))
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# 23033 忍法帖•缭乱破魔：击破 +60%（S1）；进战回 30 能；【雷遁】2 普攻后提前 50%
# ---------------------------------------------------------------------------

class TestLC23033:
    def test_battle_start(self):
        eng = _make("23033")
        assert _panel(eng)["break_effect"] == pytest.approx(0.6)
        assert _energy(eng) == pytest.approx(30.0)

    def test_raiton_two_basics_advance(self):
        eng = _make("23033", actions=(_BASIC, _ULT))
        _ult(eng)
        m = eng.state.actors["w"].modifiers["LC_23033_RAITON"]
        assert m.stacks == 2, "开大得雷遁 2 层计数（施放 2 次普攻）"
        assert _remaining(eng) == pytest.approx(10000.0)
        _cast(eng, "t_basic")
        m = eng.state.actors["w"].modifiers["LC_23033_RAITON"]
        assert m.stacks == 1 and _remaining(eng) == pytest.approx(10000.0), (
            "第 1 次普攻只减层不拉条")
        _cast(eng, "t_basic")
        assert "LC_23033_RAITON" not in eng.state.actors["w"].modifiers, "第 2 次普攻后移除雷遁"
        assert _remaining(eng) == pytest.approx(5000.0), "行动提前 50% = 剩余距离 -5000"

    def test_raiton_reset_on_second_ult(self):
        eng = _make("23033", actions=(_BASIC, _ULT))
        _ult(eng)
        _cast(eng, "t_basic")          # 2 → 1
        _ult(eng)                      # 重置 → 2
        assert eng.state.actors["w"].modifiers["LC_23033_RAITON"].stacks == 2

    def test_s5(self):
        eng = _make("23033", 5, actions=(_BASIC, _ULT))
        assert _panel(eng)["break_effect"] == pytest.approx(1.0)
        assert _energy(eng) == pytest.approx(40.0)
        _ult(eng)
        _cast(eng, "t_basic")
        _cast(eng, "t_basic")
        assert _remaining(eng) == pytest.approx(3000.0), "S5 提前 70% = -7000"


# ---------------------------------------------------------------------------
# 23037 向着不可追问处：暴击率 +12%（S1）；开大后战技/终结技 +60% 3 回合；
# 终结技耗能 ≥140 回 1 战技点（模型 = 能量上限 ≥140，见 fixture 头注）
# ---------------------------------------------------------------------------

class TestLC23037:
    def test_permanent_crit(self):
        eng = _make("23037")
        assert _panel(eng)["crit_rate"] == pytest.approx(0.17)

    def test_dmg_buff_after_ult(self):
        eng = _make("23037", actions=(_SKILL, _ULT))
        _ult(eng)
        eff = _panel(eng)
        assert eff["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.6)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.6)
        assert eng.state.actors["w"].modifiers["LC_23037_SKILL_ULT_DMGBUFF"].duration == 3
        atk = 1000 + 635.04
        before = _hp(eng, "e1")
        _cast(eng, "t_skill")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.6, crit_rate=0.17)), (
            "开大后战技吃 +60%")
        assert eng.state.skill_points == pytest.approx(2.0), (
            "能量上限 100 < 140 → 不回战技点（3 - 战技耗 1 = 2）")

    def test_sp_refund_at_140_cap(self):
        eng = _make("23037", actions=({**_ULT, "energy_cost": 140},), max_energy=140)
        _ult(eng)
        assert eng.state.skill_points == pytest.approx(4.0), "能量上限 140 ≥ 140 → 回 1 点"

    def test_s5(self):
        eng = _make("23037", 5, actions=(_ULT,))
        assert _panel(eng)["crit_rate"] == pytest.approx(0.25)
        _ult(eng)
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 23041 生命当付之一炬：装备者回合开始回 10 能；受装备者攻击的敌方降防 12%（S1）2 回合
# ---------------------------------------------------------------------------

class TestLC23041:
    def test_turn_start_energy_owner_only(self):
        eng = _make("23041")
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert _energy(eng) == pytest.approx(0.0), "非装备者回合开始不回能（$event.actor 过滤）"
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert _energy(eng) == pytest.approx(10.0)

    def test_def_down_on_hit(self):
        eng = _make("23041")
        atk = 1000 + 582.12
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.0)), (
            "首击不自带降防（after_being_hit 后置）")
        debuff = eng.state.actors["e1"].modifiers["LC_23041_DEF_DOWN"]
        assert debuff.duration == 2 and debuff.modifier_type == "debuff"
        assert _panel(eng, "e1")["def_"] == pytest.approx(1000 * (1 - 0.12)), (
            "降防 = def_pct 负值——假人 1000 → 880")
        before = _hp(eng, "e1")
        _cast(eng, "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.0, tgt_def=880.0)), (
            "次击吃降防防御区")
        assert len([m for m in eng.state.actors["e1"].modifiers
                    if m == "LC_23041_DEF_DOWN"]) == 1, "同类效果无法叠加（replace 重挂）"

    def test_s5_def_down(self):
        eng = _make("23041", 5)
        _cast(eng, "t_basic")
        assert _panel(eng, "e1")["def_"] == pytest.approx(1000 * (1 - 0.24))


# ---------------------------------------------------------------------------
# 23060 当一颗星照亮夜空：无视防御 32%（S1）；助战技回 6 能 +【启航】叠层
# （每层助战技 +20%；3 层时每层终结技 +20%）
# ---------------------------------------------------------------------------

class TestLC23060:
    def test_def_pen_and_assist_cycle(self):
        eng = _make("23060", actions=(_ASSIST, _ULT))
        atk = 1000 + 635.04
        eff = _panel(eng)
        assert eff["def_pen"] == pytest.approx(0.32)
        assert eff["dmg_bonus"].get("assist_dmg_boost", 0.0) == pytest.approx(0.0)
        assert eff["dmg_bonus"].get("ultimate_dmg_boost", 0.0) == pytest.approx(0.0), (
            "启航 0 层 → 终结技读层件 enable_if 关")
        # 第 1 助战：启航后置获得 → 当次不吃；回 6 能
        before = _hp(eng, "e1")
        _assist(eng)
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.0, def_pen=0.32)), (
            "无视防御 32% → 防御区 1/(2-0.32)；启航当次不吃")
        assert _energy(eng) == pytest.approx(6.0)
        assert eng.state.actors["w"].modifiers["LC_23060_QIHANG"].stacks == 1
        assert _panel(eng)["dmg_bonus"]["assist_dmg_boost"] == pytest.approx(0.2)
        # 第 2 助战：1 层在挂 → 当次 +20%
        before = _hp(eng, "e1")
        _assist(eng)
        assert before - _hp(eng, "e1") == pytest.approx(_dmg(atk, 0.2, def_pen=0.32))
        assert _energy(eng) == pytest.approx(12.0)
        # 第 3 助战 → 3 层：助战 +60%、终结技读层件开（每层 +20% → 60%）
        _assist(eng)
        eff = _panel(eng)
        assert eng.state.actors["w"].modifiers["LC_23060_QIHANG"].stacks == 3
        assert eff["dmg_bonus"]["assist_dmg_boost"] == pytest.approx(0.6)
        assert eff["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.6)
        # 第 4 助战：层数钳 3、回能照发
        _assist(eng)
        assert eng.state.actors["w"].modifiers["LC_23060_QIHANG"].stacks == 3
        assert _energy(eng) == pytest.approx(24.0)

    def test_s5(self):
        eng = _make("23060", 5, actions=(_ASSIST,))
        assert _panel(eng)["def_pen"] == pytest.approx(0.48)
        _assist(eng)
        assert _panel(eng)["dmg_bonus"]["assist_dmg_boost"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 23061 星火悄然闪耀：暴击率 +18%（S1）；【闪耀王冠】全条待实测（头注——
# 按角色同一回合累计耗点记账通道缺）
# ---------------------------------------------------------------------------

class TestLC23061:
    def test_permanent_crit(self):
        eng = _make("23061")
        assert _panel(eng)["crit_rate"] == pytest.approx(0.23)

    def test_s5(self):
        eng = _make("23061", 5)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.35)


# ---------------------------------------------------------------------------
# 24004 不息的演算：攻击 +8%（S1）常驻；击中叠层/≥3 名增速段待实测（头注——
# 攻击级命中计数通道缺，1314 翡翠同案）
# ---------------------------------------------------------------------------

class TestLC24004:
    def test_permanent_atk(self):
        eng = _make("24004")
        assert _panel(eng)["atk"] == pytest.approx((1000 + 529.2) * 1.08)

    def test_s5(self):
        eng = _make("24004", 5)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 529.2) * 1.12)


# ---------------------------------------------------------------------------
# 22004 宇宙大生意：攻击常驻（弱点计数增伤半待收）
# ---------------------------------------------------------------------------
class TestLC22004:
    def test_atk_pct_panel(self):
        eng = _make("22004")
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.08)

    def test_atk_pct_s5(self):
        eng = _make("22004", 5)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * 1.16)

    def test_weakness_count_dmg_pending(self):
        """「每拥有1个不同属性弱点增伤」待收（fixture 头注挡因——无弱点计数通道）."""
        eng = _make("22004")
        assert _panel(eng)["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 23028 偏偏希望无价：暴击常驻 + 暴伤档追击增伤（scoped 无视防御半待收）
# ---------------------------------------------------------------------------
class TestLC23028:
    def test_crit_rate_panel(self):
        eng = _make("23028")
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.16)

    def test_fua_boost_below_threshold(self):
        """暴伤 0.5 < #2=1.2 → 0 档（条件光环算术钳 0）."""
        eng = _make("23028", actions=(_FUA,))
        assert _panel(eng)["dmg_bonus"].get("follow_up_dmg_boost", 0.0) == pytest.approx(0.0)

    def test_fua_boost_full_tier(self):
        """暴伤 2.0 → (2.0−1.2)//0.2=4 档（钳顶 #5=4）→ 追击增伤 +48%（S1）；
        伤害对轴：atk×1.48×区."""
        eng = _make("23028", actions=(_FUA,))
        eng.state.actors["w"].actor.stats.crit_dmg = 2.0
        assert _panel(eng)["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.48)
        before = _hp(eng, "e1")
        _cast(eng, "t_fua")
        atk = 1000 + 582.12
        assert before - _hp(eng, "e1") == pytest.approx(
            _dmg(atk, 0.48, crit_rate=0.05 + 0.16, crit_dmg=2.0))

    def test_fua_boost_partial_tier_s5(self):
        """S5（#4=0.2）：暴伤 1.7 → (1.7−1.2)//0.2=2 档 → +40%；暴击率 +28%."""
        eng = _make("23028", 5, actions=(_FUA,))
        eng.state.actors["w"].actor.stats.crit_dmg = 1.7
        assert _panel(eng)["dmg_bonus"]["follow_up_dmg_boost"] == pytest.approx(0.4)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.28)

    def test_scoped_def_pen_pending(self):
        """「终结技或追加攻击无视防御」待收（scoped def_pen 无通道——fixture 头注挡因）."""
        eng = _make("23028", actions=(_ULT, _FUA))
        _cast(eng, "t_fua")
        assert _panel(eng)["def_pen"] == pytest.approx(0.0)
