"""毁灭（Warrior/Destruction）光锥 e2e：staging→fixtures 验收批.

23 件全族：3★ 20002/20009/20016；4★ 21005/21012/21019/21026/21033/21038/21042/21058/22003；
5★ 23002/23009/23014/23015/23025/23030/23039/23044/23045/23062/24000。
逐件勘正台账见各 fixture 头注（tests/fixtures/templates/light_cones/）。

口径常数：装备员 atk 1000/hp 3000/spd 100/max_energy 100（分例外注），等级 80；
假人 def 1000 → 防御区 1000/(1000+1000)=0.5、火弱点 → 抗性区 1.0、未击破 0.9、
期望暴击区基础 1+0.05×0.5=1.025（随各锥暴击面板变档逐件换算）。
命途限制：所有光锥被动挂 path_of($self)=='destruction' 闸（引擎无命途闸由模板表达），
逐件分例 path='hunt' 不触发。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 模子（手册光锥 e2e 模子扩展：四行动 + 可选队友/能量上限分例）
# ---------------------------------------------------------------------------

def _member(lc_id, *, s=1, path="destruction", hp=3000, max_energy=100, actor_id="w"):
    m = {"actor_id": actor_id, "name": "装备员", "inline": True, "path": path,
         "base_stats": {"atk": 1000, "spd": 100, "hp": hp, "max_energy": max_energy},
         "light_cone_template": lc_id, "light_cone": {"superimposition": s},
         "actions": [
             {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
              "target_type": "single", "damage_type": "fire",
              "scaling": [{"atk": 1.0}], "toughness_dmg": 10},
             {"action_id": "t_skill", "name": "战技", "action_type": "skill",
              "target_type": "single", "damage_type": "fire",
              "scaling": [{"atk": 1.0}], "toughness_dmg": 20},
             {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
              "target_type": "single", "damage_type": "fire",
              "scaling": [{"atk": 1.5}], "toughness_dmg": 30, "energy_cost": max_energy},
             {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
              "target_type": "single", "damage_type": "fire",
              "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}
    return m


def _build(lc_id, *, s=1, path="destruction", hp=3000, max_energy=100, with_ally=False):
    team = [_member(lc_id, s=s, path=path, hp=hp, max_energy=max_energy)]
    if with_ally:
        team.append({"actor_id": "ally", "name": "队友", "inline": True, "path": "harmony",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": "a_basic", "name": "普攻", "action_type": "basic",
                                  "target_type": "single", "damage_type": "ice",
                                  "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]})
    return {"build": {"team": team, "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                        "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(lc_id, *, s=1, path="destruction", hp=3000, max_energy=100, with_ally=False):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(lc_id, s=s, path=path, hp=hp, max_energy=max_energy,
                                 with_ally=with_ally),
                          _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _w(eng):
    return eng.state.actors["w"]


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _cast(eng, aid="t_basic", owner="w", target_id="e1"):
    """施放普攻/战技/追加并补发 on_action（ult 走 _ult——_fire_ultimate 双发同构）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    hp0 = tgt.current_hp
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)
    return hp0 - tgt.current_hp


def _ult(eng, owner="w", target_id="e1"):
    st = eng.state.actors[owner]
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = float(st.actor.stats.max_energy)
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_type == "ultimate")
    hp0 = tgt.current_hp
    assert eng._fire_ultimate(st, ult) is True
    return hp0 - tgt.current_hp


def _hit(eng, target, source="e1", amount=100.0):
    """受击事实（after_being_hit 收尾事件直发，克拉拉 e2e 同模子）."""
    eng.bus.emit("after_being_hit", {
        "target": target, "source": source, "amount": amount,
        "action_type": "basic", "damage_type": "physical"}, eng.state)


def _hp_down(eng, target, amount, *, reason="hit", source="e1"):
    eng.bus.emit("on_hp_decrease", {
        "target": target, "source": source, "amount": amount, "reason": reason}, eng.state)


def _hp_up(eng, target, amount, *, source="ally"):
    eng.bus.emit("on_hp_increase", {
        "target": target, "source": source, "amount": amount, "excess": 0.0,
        "reason": "heal"}, eng.state)


Z = 0.5 * 0.9 * 1.025          # 基础直伤链（防御区×未击破×期望暴击区）


def _watk(lc_id):
    """装备员白值攻击总账 = member 1000 + 光锥白值 atk（锚表第 1 列，官方正确值现算）."""
    return 1000.0 + _LC_BASE[lc_id][1]


def _whp(lc_id):
    """装备员白值生命总账 = member 3000 + 光锥白值 hp（锚表第 0 列）."""
    return 3000.0 + _LC_BASE[lc_id][0]


def _cz(crit_rate, crit_dmg):
    return 1 + min(1, crit_rate) * crit_dmg


#: 全族 23 件白值（生成器实值，fixture 数值区逐项复核=staging 同值未动）
_LC_BASE = {
    "20002": (846.72, 370.44000000000005, 198.45), "20009": (846.72, 370.44000000000005, 198.45),
    "20016": (846.72, 370.44000000000005, 198.45), "21005": (1058.4, 476.28, 264.6),
    "21012": (1058.4, 476.28, 264.6),
    "21019": (952.56, 476.28, 330.75), "21026": (952.56, 476.28, 330.75),
    "21033": (952.56, 529.2, 264.6),
    "21038": (1058.4, 476.28, 264.6),
    "21042": (952.56, 476.28, 330.75), "21058": (1058.4, 529.2, 330.75),
    "22003": (1058.4, 476.28, 264.6),
    "23002": (1164.2399999999998, 582.1199999999999, 396.9), "23009": (1270.08, 582.1199999999999, 330.75),
    "23014": (1164.2399999999998, 582.1199999999999, 396.9), "23015": (1058.4, 635.04, 396.9),
    "23025": (1164.2399999999998, 476.28, 529.2),
    "23030": (1058.4, 582.1199999999999, 463.04999999999995),
    "23039": (1375.92, 476.28, 396.9), "23044": (952.56, 687.96, 396.9),
    "23045": (952.56, 582.1199999999999, 529.2),
    "23062": (952.56, 635.04, 463.04999999999995), "24000": (1058.4, 529.2, 396.9),
}


class TestWhiteValues:
    """白值三围归并（23 件全量；白值与命途无关——path 不闸白值）."""

    @pytest.mark.parametrize("lc_id", sorted(_LC_BASE))
    def test_base_stats_merged(self, lc_id):
        eng = _make(lc_id)
        st = _w(eng).actor.stats
        hp, atk, df = _LC_BASE[lc_id]
        assert math.isclose(st.hp, 3000 + hp, rel_tol=1e-9), f"{lc_id} hp 白值"
        assert math.isclose(st.atk, 1000 + atk, rel_tol=1e-9), f"{lc_id} atk 白值"
        assert math.isclose(st.def_, 0.0 + df, rel_tol=1e-9), f"{lc_id} def 白值"

    @pytest.mark.parametrize("lc_id", sorted(_LC_BASE))
    def test_base_stats_path_irrelevant(self, lc_id):
        eng = _make(lc_id, path="hunt")
        st = _w(eng).actor.stats
        hp, atk, df = _LC_BASE[lc_id]
        assert math.isclose(st.atk, 1000 + atk, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 3★
# ---------------------------------------------------------------------------

class TestLC20002天倾:
    """普攻/战技类型桶增伤（dmg_basic/skill_dmg_boost）；终结技不吃."""

    def test_mechanism_s1(self):
        eng = _make("20002")
        assert "LC_20002_DMG" in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_basic"), _watk("20002") * 1.2 * Z, rel_tol=1e-9)
        assert math.isclose(_cast(eng, "t_skill"), _watk("20002") * 1.2 * Z, rel_tol=1e-9)
        assert math.isclose(_ult(eng), _watk("20002") * 1.5 * 1.0 * Z, rel_tol=1e-9), "终结技无类型桶"

    def test_superimposition_s5(self):
        eng = _make("20002", s=5)
        assert math.isclose(_cast(eng, "t_basic"), _watk("20002") * 1.4 * Z, rel_tol=1e-9), "S5=0.40"

    def test_path_gate(self):
        eng = _make("20002", path="hunt")
        assert "LC_20002_DMG" not in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_basic"), _watk("20002") * 1.0 * Z, rel_tol=1e-9)


class TestLC20009乐圮:
    """目标 HP%>50% 条件增伤——命中域无目标 HP 载荷，全段待收编（fixture 头注勘正①）；只验白值."""

    def test_unexpressed_segment_honest(self):
        eng = _make("20009")
        assert _w(eng).modifiers == {}, "条件增伤段未落地——无任何 modifier（不硬凑）"
        assert math.isclose(_cast(eng, "t_basic"), _watk("20009") * 1.0 * Z, rel_tol=1e-9)


class TestLC20016俱殁:
    """HP<80% 条件光环暴击率（enable_if 现场重估）."""

    def test_hp_threshold_toggle(self):
        eng = _make("20016")
        st = _w(eng)
        assert "LC_20016_MUTUAL_DEMISE_CRIT" in st.modifiers, "件常驻挂载（门控非挂摘）"
        assert math.isclose(_panel(eng)["crit_rate"], 0.05), "满血档不生效"
        st.current_hp = st.current_hp * 0.5
        assert math.isclose(_panel(eng)["crit_rate"], 0.05 + 0.12, rel_tol=1e-9), "半血档 +12%"
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("20016") * 0.5 * 0.9 * _cz(0.17, 0.5), rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("20016", path="hunt")
        st = _w(eng)
        assert "LC_20016_MUTUAL_DEMISE_CRIT" not in st.modifiers
        st.current_hp = st.current_hp * 0.5
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)


# ---------------------------------------------------------------------------
# 4★
# ---------------------------------------------------------------------------

class TestLC21005鼹鼠党:
    """三类行动分别叠一层淘气值（各 max_stack 1，同类重复不复叠），每层 atk_pct."""

    def test_three_stacks_respectively(self):
        eng = _make("21005")
        assert math.isclose(_panel(eng)["atk"], _watk("21005"), rel_tol=1e-9), "开局无层"
        _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["atk"], _watk("21005") * 1.12, rel_tol=1e-9), "普攻一层"
        _cast(eng, "t_skill")
        assert math.isclose(_panel(eng)["atk"], _watk("21005") * 1.24, rel_tol=1e-9), "战技再一层"
        _ult(eng)
        assert math.isclose(_panel(eng)["atk"], _watk("21005") * 1.36, rel_tol=1e-9), "终结技第三层"
        _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["atk"], _watk("21005") * 1.36, rel_tol=1e-9), "同类行动不复叠"

    def test_path_gate(self):
        eng = _make("21005", path="hunt")
        _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["atk"], _watk("21005"), rel_tol=1e-9)
        assert not [m for m in _w(eng).modifiers if m.startswith("LC_21005")]


class TestLC21012秘密誓心:
    """常驻全增伤；HP% 比较额外段待收编（fixture 头注勘正②）."""

    def test_constant_all_dmg(self):
        eng = _make("21012")
        assert math.isclose(_cast(eng, "t_basic"), _watk("21012") * 1.2 * Z, rel_tol=1e-9)
        assert math.isclose(_cast(eng, "t_skill"), _watk("21012") * 1.2 * Z, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("21012", path="hunt")
        assert "LC_21012_DMG_BONUS" not in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_basic"), _watk("21012") * 1.0 * Z, rel_tol=1e-9)


class TestLC21019在蓝天下:
    """常驻 atk_pct + 击杀暴击 3 回合."""

    def test_constant_and_on_kill(self):
        eng = _make("21019")
        assert math.isclose(_panel(eng)["atk"], _watk("21019") * 1.16, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["crit_rate"], 0.05), "未击杀无暴击档"
        eng.state.actors["e1"].current_hp = 1.0   # 压血喂击杀
        _cast(eng, "t_basic")
        assert not eng.state.actors["e1"].alive, "击杀成立"
        assert math.isclose(_panel(eng)["crit_rate"], 0.05 + 0.12, rel_tol=1e-9)
        assert _w(eng).modifiers["LC_21019_CRITRATE_ON_KILL"].duration == 3, "持续 3 回合"

    def test_path_gate(self):
        eng = _make("21019", path="hunt")
        assert math.isclose(_panel(eng)["atk"], _watk("21019"), rel_tol=1e-9), "常驻段被命途闸"
        eng.state.actors["e1"].current_hp = 1.0
        _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)


class TestLC21026散步时间:
    """常驻 atk_pct；灼烧/裂伤增伤段待收编（fixture 头注勘正②）."""

    def test_constant_atk_pct(self):
        eng = _make("21026")
        assert math.isclose(_panel(eng)["atk"], _watk("21026") * 1.10, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("21026", path="hunt")
        assert math.isclose(_panel(eng)["atk"], _watk("21026"), rel_tol=1e-9)


class TestLC21033无处可逃:
    """常驻 atk_pct + 击杀按攻击力回血."""

    def test_on_kill_heal(self):
        eng = _make("21033")
        st = _w(eng)
        assert math.isclose(_panel(eng)["atk"], _watk("21033") * 1.24, rel_tol=1e-9)
        st.current_hp = 2000.0
        eng.state.actors["e1"].current_hp = 1.0
        _cast(eng, "t_basic")
        assert not eng.state.actors["e1"].alive
        assert math.isclose(st.current_hp, 2000.0 + _watk("21033") * 1.24 * 0.12, rel_tol=1e-9), (
            "回复 = 有效攻击力 ×12%（heal flat 槽，无治疗加成源）")

    def test_path_gate(self):
        eng = _make("21033", path="hunt")
        st = _w(eng)
        st.current_hp = 2000.0
        eng.state.actors["e1"].current_hp = 1.0
        _cast(eng, "t_basic")
        assert math.isclose(st.current_hp, 2000.0), "命途不匹配击杀不回血"


class TestLC21038在火的远处:
    """单次受击/耗血 >25% 生命上限 → 回血 15% + 增伤 2 回合；3 回合冷却."""

    def test_hit_branch_and_cooldown(self):
        eng = _make("21038")
        st = _w(eng)
        st.current_hp = 500.0   # 假定位损后血线（事件只载事实，扣血手动对齐）
        _hp_down(eng, "w", 1100.0)   # > 4058.4×0.25 = 1014.6 阈值（A6 白值口径）
        assert math.isclose(st.current_hp, 500.0 + _whp("21038") * 0.15, rel_tol=1e-9), "立即回血 15%"
        assert "LC_21038_DMG_BOOST" in st.modifiers
        assert "LC_21038_CD" in st.modifiers, "触发锁在场"
        assert math.isclose(_cast(eng, "t_basic"), _watk("21038") * 1.25 * Z, rel_tol=1e-9), "增伤 25%"
        hp_now = st.current_hp
        _hp_down(eng, "w", 1200.0)   # 冷却期内再大损也不触发
        assert math.isclose(st.current_hp, hp_now), "CD 锁不重触发（不再回血）"
        assert st.modifiers["LC_21038_DMG_BOOST"].duration == 2, "增伤件未被重挂刷新"

    def test_drain_branch_and_below_threshold(self):
        eng = _make("21038")
        st = _w(eng)
        _hp_down(eng, "w", 500.0)    # 未达阈值
        assert "LC_21038_DMG_BOOST" not in st.modifiers
        st.current_hp = 500.0
        _hp_down(eng, "w", 1100.0, reason="drain", source="w")   # 自身耗血支（>1014.6 阈值）
        assert math.isclose(st.current_hp, 500.0 + _whp("21038") * 0.15, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("21038", path="hunt")
        _hp_down(eng, "w", 1200.0)
        assert "LC_21038_DMG_BOOST" not in _w(eng).modifiers


class TestLC21042铭记于心:
    """常驻击破特攻 + 终结技暴击 2 回合."""

    def test_break_effect_and_ult_crit(self):
        eng = _make("21042")
        assert math.isclose(_panel(eng)["break_effect"], 0.28, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(_panel(eng)["crit_rate"], 0.05 + 0.15, rel_tol=1e-9)
        assert _w(eng).modifiers["LC_21042_CRIT_RATE_MOD"].duration == 2

    def test_path_gate(self):
        eng = _make("21042", path="hunt")
        assert math.isclose(_panel(eng)["break_effect"], 0.0), "常驻段被命途闸"
        _ult(eng)
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)


class TestLC21058往日的血:
    """常驻暴击率 + 战技/终结技类型桶增伤；普攻不吃."""

    def test_mechanism(self):
        eng = _make("21058")
        assert math.isclose(_panel(eng)["crit_rate"], 0.17, rel_tol=1e-9)
        cz = _cz(0.17, 0.5)
        assert math.isclose(_cast(eng, "t_basic"), _watk("21058") * 1.0 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "普攻无类型桶")
        assert math.isclose(_cast(eng, "t_skill"), _watk("21058") * 1.24 * 0.5 * 0.9 * cz, rel_tol=1e-9)
        assert math.isclose(_ult(eng), _watk("21058") * 1.5 * 1.24 * 0.5 * 0.9 * cz, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("21058", path="hunt")
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)
        assert math.isclose(_cast(eng, "t_skill"), _watk("21058") * 1.0 * Z, rel_tol=1e-9)


class TestLC22003忍事录:
    """常驻 hp_pct + 损血/回血触发暴伤 2 回合，每回合一次（owner_turn_start 锚锁）."""

    def test_hp_pct_and_trigger_lock(self):
        eng = _make("22003")
        st = _w(eng)
        assert math.isclose(_panel(eng)["hp"], _whp("22003") * 1.12, rel_tol=1e-9)
        _hp_down(eng, "w", 1.0)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.18, rel_tol=1e-9)
        assert "LC_22003_CD_LOCK" in st.modifiers
        st.modifiers["LC_22003_CRIT_DMG"].duration = 1   # 人为压旧——锁期内重触发会刷新回 2
        _hp_down(eng, "w", 1.0)
        assert st.modifiers["LC_22003_CRIT_DMG"].duration == 1, "锁期内不重触发（未刷新时长）"

    def test_heal_branch_and_overflow_guard(self):
        eng = _make("22003")
        _hp_up(eng, "w", 0.0)     # 满血溢出奶（amount=0）不算「回复生命值」
        assert "LC_22003_CRIT_DMG" not in _w(eng).modifiers
        _hp_up(eng, "w", 50.0)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.18, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("22003", path="hunt")
        assert math.isclose(_panel(eng)["hp"], _whp("22003"), rel_tol=1e-9)
        _hp_down(eng, "w", 1.0)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5)


# ---------------------------------------------------------------------------
# 5★
# ---------------------------------------------------------------------------

class TestLC23002无可取代:
    """常驻 atk_pct + 受击/击杀：按攻击力回血 + 增伤至下回合结束（每回合一次）."""

    def test_being_hit_branch(self):
        eng = _make("23002")
        st = _w(eng)
        assert math.isclose(_panel(eng)["atk"], _watk("23002") * 1.24, rel_tol=1e-9)
        st.current_hp = 2000.0
        _hit(eng, "w")
        assert math.isclose(st.current_hp, 2000.0 + _watk("23002") * 1.24 * 0.08, rel_tol=1e-9), (
            "回复 = 有效攻击力 ×8%")
        assert "LC_23002_DMG_BUFF" in st.modifiers
        assert "LC_23002_TRIGGER_LOCK" in st.modifiers
        assert math.isclose(_cast(eng, "t_basic"), _watk("23002") * 1.24 * 1.24 * Z, rel_tol=1e-9)
        hp_now = st.current_hp
        _hit(eng, "w")
        assert math.isclose(st.current_hp, hp_now), "每回合一次锁"

    def test_on_kill_branch(self):
        eng = _make("23002")
        st = _w(eng)
        st.current_hp = 2000.0
        eng.state.actors["e1"].current_hp = 1.0
        _cast(eng, "t_basic")
        assert not eng.state.actors["e1"].alive
        assert math.isclose(st.current_hp, 2000.0 + _watk("23002") * 1.24 * 0.08, rel_tol=1e-9)
        assert "LC_23002_DMG_BUFF" in st.modifiers

    def test_path_gate(self):
        eng = _make("23002", path="hunt")
        st = _w(eng)
        st.current_hp = 2000.0
        _hit(eng, "w")
        assert math.isclose(st.current_hp, 2000.0)
        assert "LC_23002_DMG_BUFF" not in st.modifiers


class TestLC23009彼岸:
    """常驻暴击+生命；受击/耗血增伤，施放攻击后解除."""

    def test_hit_then_attack_releases(self):
        eng = _make("23009")
        assert math.isclose(_panel(eng)["crit_rate"], 0.23, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["hp"], _whp("23009") * 1.18, rel_tol=1e-9)
        _hit(eng, "w")
        assert "LC_23009_UNREACHABLE_DMG" in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("23009") * 1.24 * 0.5 * 0.9 * _cz(0.23, 0.5), rel_tol=1e-9)
        assert "LC_23009_UNREACHABLE_DMG" not in _w(eng).modifiers, "攻击后解除"

    def test_drain_branch_and_hit_reason_guard(self):
        eng = _make("23009")
        _hp_down(eng, "w", 100.0, reason="hit")   # 受击的 hp_decrease 不重复承载（after_being_hit 支）
        assert "LC_23009_UNREACHABLE_DMG" not in _w(eng).modifiers
        _hp_down(eng, "w", 100.0, reason="drain", source="w")
        assert "LC_23009_UNREACHABLE_DMG" in _w(eng).modifiers

    def test_path_gate(self):
        eng = _make("23009", path="hunt")
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)
        _hit(eng, "w")
        assert "LC_23009_UNREACHABLE_DMG" not in _w(eng).modifiers


class TestLC23014此身为剑:
    """队友受击/耗血叠月蚀（上限 3），每层增伤下次攻击；满层额外无视防御；攻击后解除."""

    def test_stacks_and_release(self):
        eng = _make("23014", with_ally=True)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.2, rel_tol=1e-9)
        _hit(eng, "ally")
        assert _w(eng).modifiers["LC_23014_ECLIPSE"].stacks == 1
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("23014") * 1.14 * 0.5 * 0.9 * _cz(0.05, 0.7), rel_tol=1e-9)
        assert "LC_23014_ECLIPSE" not in _w(eng).modifiers, "攻击后解除"

    def test_full_stacks_def_pen(self):
        eng = _make("23014", with_ally=True)
        for _ in range(3):
            _hit(eng, "ally")
        assert _w(eng).modifiers["LC_23014_ECLIPSE"].stacks == 3
        assert math.isclose(_panel(eng)["def_pen"], 0.12, rel_tol=1e-9), "满层无视防御闸开"
        def_multi = 1000 / (1000 * 0.88 + 1000)
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("23014") * (1 + 3 * 0.14) * def_multi * 0.9 * _cz(0.05, 0.7),
                            rel_tol=1e-9)
        assert math.isclose(_panel(eng)["def_pen"], 0.0), "攻击后月蚀摘→闸自动关"

    def test_wearer_hit_no_stack_and_cap(self):
        eng = _make("23014", with_ally=True)
        _hit(eng, "w")
        assert "LC_23014_ECLIPSE" not in _w(eng).modifiers, "装备者自身受击不叠"
        for _ in range(4):
            _hit(eng, "ally")
        assert _w(eng).modifiers["LC_23014_ECLIPSE"].stacks == 3, "3 层封顶"

    def test_ally_drain_branch(self):
        eng = _make("23014", with_ally=True)
        _hp_down(eng, "ally", 100.0, reason="drain", source="ally")
        assert _w(eng).modifiers["LC_23014_ECLIPSE"].stacks == 1, "队友耗血叠层"

    def test_path_gate(self):
        eng = _make("23014", path="hunt", with_ally=True)
        _hit(eng, "ally")
        assert "LC_23014_ECLIPSE" not in _w(eng).modifiers


class TestLC23015比阳光更明亮:
    """常驻暴击 + 普攻叠龙吟（上限 2，持续 2 回合）：每层 atk_pct + energy_regen."""

    def test_dragons_call_stacking(self):
        eng = _make("23015")
        assert math.isclose(_panel(eng)["crit_rate"], 0.23, rel_tol=1e-9)
        cz = _cz(0.23, 0.5)
        assert math.isclose(_cast(eng, "t_basic"), _watk("23015") * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "首击无层（on_action 事后叠）")
        assert math.isclose(_panel(eng)["atk"], _watk("23015") * 1.18, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["energy_regen"], 1.06, rel_tol=1e-9), (
            "面板 ERR = 基础 1.0 + 0.06（总倍率口径，mechanics 05 §5.3）")
        assert math.isclose(_cast(eng, "t_basic"), _watk("23015") * 1.18 * 0.5 * 0.9 * cz, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["atk"], _watk("23015") * 1.36, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["energy_regen"], 1.12, rel_tol=1e-9)
        _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["atk"], _watk("23015") * 1.36, rel_tol=1e-9), "2 层封顶"

    def test_path_gate(self):
        eng = _make("23015", path="hunt")
        _cast(eng, "t_basic")
        assert "LC_23015_DRAGONS_CALL" not in _w(eng).modifiers


class TestLC23025梦归何处:
    """常驻击破特攻；击破伤害 → 溃败（减速面板件 + 击破易伤 scoped 件）2 回合."""

    def test_break_effect_and_routed(self):
        eng = _make("23025")
        assert math.isclose(_panel(eng)["break_effect"], 0.6, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        e1.toughness = 5.0
        hp0 = e1.current_hp
        dealt = _cast(eng, "t_basic")
        assert e1.broken, "击破成立"
        assert math.isclose(_panel(eng, "e1")["spd"], 80.0, rel_tol=1e-9), "减速 20%（白值口径）"
        assert math.isclose(_panel(eng, "e1")["vulnerability"], 0.0), (
            "scoped 易伤不进面板（hit_condition 命中域件）")
        assert e1.modifiers["LC_23025_ROUTED_SPD"].duration == 2
        assert "LC_23025_ROUTED_VULN" in e1.modifiers
        # 击破伤害手算：火 scaling 2.0×(0.5+100/40)×3767.5533×BE1.6×防 0.5×抗 1.0×易伤 1.24
        # （on_break 发射在 break_damage 结算前——首破即吃到溃败易伤口径，fixture 头注在案）；
        # 击破那击本身结算时目标尚未击破（先伤害后削韧——_execute_action 序），base_universal=0.9
        break_dmg = 3767.5533 * 2.0 * 3.0 * 1.6 * 0.5 * 1.24
        basic_dmg = _watk("23025") * Z
        assert math.isclose(dealt, basic_dmg + break_dmg, rel_tol=1e-9), (
            "普攻伤害 + 击破伤害（含溃败易伤 ×1.24）")
        assert hp0 - e1.current_hp == dealt

    def test_path_gate(self):
        eng = _make("23025", path="hunt")
        assert math.isclose(_panel(eng)["break_effect"], 0.0)
        e1 = eng.state.actors["e1"]
        e1.toughness = 5.0
        _cast(eng, "t_basic")
        assert "LC_23025_ROUTED_VULN" not in e1.modifiers


class TestLC23030落日时起舞:
    """常驻暴伤 + 嘲讽 +500%（aggro_boost 池）；终结技叠火舞（上限 2）追加攻击增伤."""

    def test_panel_and_firedance(self):
        eng = _make("23030")
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.36, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["taunt_eff"], 100.0 * 6.0, rel_tol=1e-9), (
            "inline 白板基础嘲讽 100×(1+5)——mechanics 10 +500% 登记口径")
        cz = _cz(0.05, 0.86)
        _ult(eng)
        assert _w(eng).modifiers["LC_23030_FIREDANCE"].stacks == 1
        assert math.isclose(_cast(eng, "t_fua"), _watk("23030") * 1.36 * 0.5 * 0.9 * cz, rel_tol=1e-9)
        _ult(eng)
        assert _w(eng).modifiers["LC_23030_FIREDANCE"].stacks == 2
        assert math.isclose(_cast(eng, "t_fua"), _watk("23030") * 1.72 * 0.5 * 0.9 * cz, rel_tol=1e-9)
        _ult(eng)
        assert _w(eng).modifiers["LC_23030_FIREDANCE"].stacks == 2, "2 层封顶"
        eng.state.actors["e1"].broken = False   # 前三连削韧已破——复位旗标隔离「火舞不吃普攻」断言
        assert math.isclose(_cast(eng, "t_basic"), _watk("23030") * 1.0 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "火舞只命中追加攻击桶")

    def test_path_gate(self):
        eng = _make("23030", path="hunt")
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5)
        assert math.isclose(_panel(eng)["taunt_eff"], 100.0, rel_tol=1e-9), (
            "命途不匹配无嘲讽加成（白板基础 100）")
        _ult(eng)
        assert "LC_23030_FIREDANCE" not in _w(eng).modifiers


class TestLC23039血火燃烧:
    """常驻生命+受疗；战技/终结技耗血 6%（floor 1）且该次攻击增伤（hit_condition 类型闸）."""

    def test_skill_drain_and_scoped_boost(self):
        eng = _make("23039")
        st = _w(eng)
        assert math.isclose(_panel(eng)["hp"], _whp("23039") * 1.18, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["incoming_heal"], 0.2, rel_tol=1e-9)
        hp0 = st.current_hp
        assert math.isclose(_cast(eng, "t_skill"), _watk("23039") * 1.3 * Z, rel_tol=1e-9)
        assert math.isclose(hp0 - st.current_hp, _whp("23039") * 1.18 * 0.06, rel_tol=1e-9), (
            "耗血 = 有效生命上限 ×6%")
        hp1 = st.current_hp
        assert math.isclose(_cast(eng, "t_basic"), _watk("23039") * 1.0 * Z, rel_tol=1e-9), (
            "普攻不吃 hit_condition 闸")
        assert math.isclose(st.current_hp, hp1), "普攻不耗血"

    def test_extra_boost_threshold(self):
        eng = _make("23039", hp=6000)   # (6000+1276.08)×1.18×0.06 = 515.1 > 500 → 附加段挂载
        assert "LC_23039_DMG_BONUS" in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_skill"), _watk("23039") * 1.6 * Z, rel_tol=1e-9), (
            "主 30% + 附加 30%（hit_condition 双件同闸加算）")

    def test_drain_floor_one(self):
        eng = _make("23039")
        st = _w(eng)
        st.current_hp = 100.0
        _cast(eng, "t_skill")
        assert math.isclose(st.current_hp, 1.0), "当前生命不足最多降至 1 点"

    def test_path_gate(self):
        eng = _make("23039", path="hunt")
        st = _w(eng)
        assert math.isclose(_panel(eng)["hp"], _whp("23039"), rel_tol=1e-9)
        hp0 = st.current_hp
        assert math.isclose(_cast(eng, "t_skill"), _watk("23039") * 1.0 * Z, rel_tol=1e-9)
        assert math.isclose(st.current_hp, hp0), "命途不匹配不耗血"


class TestLC23044黎明燃烧:
    """基础速度 + 无视防御常驻；终结技得烈阳（下回合开始移除）增伤."""

    def test_spd_def_pen_and_blazing_sun(self):
        eng = _make("23044")
        assert math.isclose(_panel(eng)["spd"], 112.0, rel_tol=1e-9)
        def_multi = 1000 / (1000 * 0.82 + 1000)
        assert math.isclose(_cast(eng, "t_basic"), _watk("23044") * def_multi * 0.9 * 1.025, rel_tol=1e-9)
        _ult(eng)
        assert "LC_23044_BLAZING_SUN" in _w(eng).modifiers
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("23044") * 1.6 * def_multi * 0.9 * 1.025, rel_tol=1e-9), "烈阳增伤 60%"
        eng._modifiers._tick_modifiers(_w(eng), "owner_turn_start")   # 回合开始走字
        assert "LC_23044_BLAZING_SUN" not in _w(eng).modifiers, "回合开始时移除"
        assert math.isclose(_cast(eng, "t_basic"), _watk("23044") * def_multi * 0.9 * 1.025, rel_tol=1e-9)

    def test_path_gate(self):
        eng = _make("23044", path="hunt")
        assert math.isclose(_panel(eng)["spd"], 100.0)
        assert math.isclose(_cast(eng, "t_basic"), _watk("23044") * 0.5 * 0.9 * 1.025, rel_tol=1e-9)
        _ult(eng)
        assert "LC_23044_BLAZING_SUN" not in _w(eng).modifiers


class TestLC23045加冕:
    """常驻暴伤；终结技加攻（其一）+ 能量上限≥300 闸：固定回能 10%（ERR 豁免）+ 加攻（其二）."""

    def test_low_max_energy_branch(self):
        eng = _make("23045")   # max_energy 100 < 300
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.36, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(_panel(eng)["atk"], _watk("23045") * 1.4, rel_tol=1e-9), "只有其一"
        assert "LC_23045_ATK_SECOND" not in _w(eng).modifiers
        assert math.isclose(_w(eng).current_energy, 5.0), "无固定回能支（仅终结技释放本身回 5）"

    def test_high_max_energy_branch(self):
        eng = _make("23045", max_energy=300)
        _ult(eng)
        assert math.isclose(_w(eng).current_energy, 300 * 0.1 + 5.0, rel_tol=1e-9), (
            "固定恢复能量上限 10%（§5.3 具名豁免，不吃 ERR）+ 终结技释放本身回 5")
        assert math.isclose(_panel(eng)["atk"], _watk("23045") * 1.8, rel_tol=1e-9), "其一 40% + 其二 40%"

    def test_path_gate(self):
        eng = _make("23045", path="hunt", max_energy=300)
        _ult(eng)
        assert "LC_23045_ATK_FIRST" not in _w(eng).modifiers
        assert math.isclose(_w(eng).current_energy, 5.0)


class TestLC23062所见即我:
    """常驻攻击+能量恢复效率；终结技增伤按能量上限烘焙（0.2%/点封顶 72%）；王之娱乐全队暴伤."""

    def test_panel_ult_boost_and_kings_entertainment(self):
        eng = _make("23062", with_ally=True)
        assert math.isclose(_panel(eng)["atk"], _watk("23062") * 1.18, rel_tol=1e-9)
        assert math.isclose(_panel(eng)["energy_regen"], 1.1, rel_tol=1e-9), "基础 1.0 + 0.1"
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5 + 0.24, rel_tol=1e-9), "进战即持王之娱乐"
        assert math.isclose(_panel(eng, "ally")["crit_dmg"], 0.5 + 0.24, rel_tol=1e-9), (
            "effect_scope: team 全队辐射")
        cz = _cz(0.05, 0.74)
        assert math.isclose(_cast(eng, "t_basic"), _watk("23062") * 1.18 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "普攻不吃终结技桶")
        assert math.isclose(_ult(eng),
                            _watk("23062") * 1.18 * 1.5 * 1.2 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "min(100×0.2%, 72%) = +20% 终结技伤害")
        assert _w(eng).modifiers["LC_23062_KINGS_ENTERTAINMENT"].duration == 3

    def test_superimposition_s5(self):
        eng = _make("23062", s=5)
        cz = _cz(0.05, 0.98)   # 暴伤 0.5 + S5 王之娱乐 0.48
        assert math.isclose(_ult(eng),
                            _watk("23062") * 1.3 * 1.5 * 1.4 * 0.5 * 0.9 * cz, rel_tol=1e-9), (
            "S5：攻击 30%、min(100×0.4%, 144%) = +40%")

    def test_path_gate(self):
        eng = _make("23062", path="hunt", with_ally=True)
        assert math.isclose(_panel(eng)["atk"], _watk("23062"), rel_tol=1e-9)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5)
        assert math.isclose(_panel(eng, "ally")["crit_dmg"], 0.5), "光环同闸"
        assert math.isclose(_ult(eng), _watk("23062") * 1.5 * 1.0 * Z, rel_tol=1e-9)


class TestLC24000星神陨落:
    """施放攻击叠攻击层（上限 4，战斗常驻）；击破弱点后增伤 2 回合."""

    def test_attack_stacks_cap4(self):
        eng = _make("24000")
        assert math.isclose(_cast(eng, "t_basic"), _watk("24000") * 1.0 * Z, rel_tol=1e-9), "首击无层"
        for expect_pct in (1.08, 1.16, 1.24, 1.32):
            assert math.isclose(_panel(eng)["atk"], _watk("24000") * expect_pct, rel_tol=1e-9)
            _cast(eng, "t_basic")
        assert math.isclose(_panel(eng)["atk"], _watk("24000") * 1.32, rel_tol=1e-9), "4 层封顶"
        _cast(eng, "t_fua")
        assert math.isclose(_panel(eng)["atk"], _watk("24000") * 1.32, rel_tol=1e-9), (
            "追加计入「施放攻击」（社区口径在案——已 4 层封顶不变）")

    def test_break_dmg_bonus(self):
        eng = _make("24000")
        e1 = eng.state.actors["e1"]
        e1.toughness = 5.0
        _cast(eng, "t_basic")   # 击破 + 第 1 层
        assert _w(eng).modifiers["LC_24000_DMG_BONUS"].duration == 2
        assert math.isclose(_cast(eng, "t_basic"),
                            _watk("24000") * 1.08 * 1.12 * 0.5 * 1.0 * 1.025, rel_tol=1e-9), (
            "1 层攻击 + 击破增伤 12%；目标已击破 base_universal=1.0（不再 0.9）")

    def test_path_gate(self):
        eng = _make("24000", path="hunt")
        _cast(eng, "t_basic")
        assert "LC_24000_ATK_STACK" not in _w(eng).modifiers
        e1 = eng.state.actors["e1"]
        e1.toughness = 5.0
        _cast(eng, "t_basic")
        assert "LC_24000_DMG_BONUS" not in _w(eng).modifiers
