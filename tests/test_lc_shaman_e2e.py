"""同谐（Shaman）光锥 e2e：staging→fixtures 验收批.

本族 16 件（20005/20012/20019/21004/21011/21018/21032/21036/21046/21056/22002/22005/
23003/23019/23021/23038），每件：白值三围断言（path 不匹配例兼作命途限制阴性例——
白值无条件生效、机制全不触发）+ 机制行为断言手算对轴 + 叠影 S1 起（S5 差分抽查）。
面板/伤害对轴：假人 def 1000 → 防御区 0.5；弱点全配 → 抗性 1.0；未击破 0.9；
期望暴击 1.025（crit 0.05/0.5）。命途限制件分例：path="harmony" 触发 / 其他命途不触发。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 模子（验收手册光锥模子 + 本族扩展件）
# ---------------------------------------------------------------------------

_BASIC = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
          "target_type": "single", "damage_type": "fire", "energy_gain": 0,
          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_BASIC_SP = {**_BASIC, "action_id": "t_basic_sp", "name": "普攻·产点", "skill_point_gain": 1}
_BASIC_ICE = {**_BASIC, "action_id": "t_basic_i", "name": "普攻·冰", "damage_type": "ice"}
_SKILL = {"action_id": "t_skill", "name": "战技", "action_type": "skill",
          "target_type": "single", "damage_type": "fire", "energy_gain": 0,
          "skill_point_cost": 1, "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
_ULT = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "fire", "energy_cost": 100,
        "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
_ULT_ALLY = {"action_id": "t_ult_a", "name": "终结技·辅", "action_type": "ultimate",
             "target_type": "ally_single", "energy_cost": 100}
_FUA = {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
        "target_type": "single", "damage_type": "fire", "energy_gain": 0,
        "scaling": [{"atk": 1.0}], "toughness_dmg": 0}

#: 白值三围（pipeline.calc_light_cone_stats Lv.80 官值——promo_levels (70,80) 段修复后
#: lv80=A6 base+step×79，fixture 数值区原样；2026-09-15 前为 A5 病值，期望已重算）
_LC_WHITE = {
    "20005": (846.72, 317.52, 264.6),
    "20012": (846.72, 317.52, 264.6),
    "20019": (846.72, 317.52, 264.6),
    "21004": (952.56, 423.36, 396.9),
    "21011": (1058.4, 423.36, 330.75),
    "21018": (952.56, 423.36, 396.9),
    "21032": (952.56, 476.28, 330.75),
    "21036": (952.56, 423.36, 396.9),
    "21046": (952.56, 423.36, 396.9),
    "21056": (1058.4, 476.28, 396.9),
    "22002": (952.56, 476.28, 330.75),
    "22005": (952.56, 476.28, 330.75),
    "23003": (1164.2399999999998, 529.2, 463.04999999999995),
    "23019": (1058.4, 529.2, 529.2),
    "23021": (1164.2399999999998, 529.2, 463.04999999999995),
    "23038": (1270.08, 529.2, 396.9),
}

#: 装备者攻击白值派生锚（成员底攻 1000 + 光锥攻击白值）——攻击类面板/伤害期望共用取数点
_ATK = {k: 1000.0 + v[1] for k, v in _LC_WHITE.items()}


def _member(actor_id="w", *, lc_id=None, superimposition=1, path=None, element=None,
            actions=(), base_stats=None):
    m = {"actor_id": actor_id, "name": f"装备员{actor_id}", "inline": True,
         "base_stats": base_stats or {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
         "actions": list(actions)}
    if lc_id is not None:
        m["light_cone_template"] = lc_id
        m["light_cone"] = {"superimposition": superimposition}
    if path:
        m["path"] = path
    if element:
        m["element"] = element
    return m


def _build(lc_id, *, superimposition=1, path="harmony", actions=(_BASIC,),
           extra=(), member_kw=None):
    member = _member("w", lc_id=lc_id, superimposition=superimposition, path=path,
                     element="fire", actions=actions, **(member_kw or {}))
    return {"build": {"team": [member, *extra],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                        "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(lc_id, *, superimposition=1, path="harmony", actions=(_BASIC,), extra=(),
          initial_sp=3, member_kw=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(
            _build(lc_id, superimposition=superimposition, path=path, actions=actions,
                   extra=extra, member_kw=member_kw),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _cast(eng, owner, aid, target_id="e1"):
    """行动施放模子（照抄 8009/遗器 e2e——_execute_action + on_action 广播）."""
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


def _ult(eng, owner="w", aid="t_ult", target_id="e1"):
    """手动插队开大（ult_now 同漏斗）：能量拉满 → _fire_ultimate."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = 100.0
    assert eng._fire_ultimate(st, a) is True


def _hp(eng, aid="e1"):
    return eng.state.actors[aid].current_hp


def _remaining(eng, aid="w"):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _energy(eng, aid="w"):
    return eng.state.actors[aid].current_energy


#: 敌方打击（物理普攻——energy_grant 默认 0 不污染受击回能断言；单成员队恒命中装备员）
_ENEMY_HIT = Action(action_id="e_hit", name="敌击", action_type="basic",
                    target_type="single", damage_type="physical",
                    scaling=[{"atk": 1.0}], toughness_dmg=0)


def _enemy_hit(eng, times=1):
    for _ in range(times):
        eng._execute_action(eng.state.actors["e1"], _ENEMY_HIT)


def _turn_end(eng, aid):
    eng.bus.emit("on_turn_end", {"actor": aid}, eng.state)


def _turn_start(eng, aid):
    eng.bus.emit("on_turn_start", {"actor": aid}, eng.state)


def _assert_white(eng, lc_id):
    """白值三围 = 成员底值 + 光锥白值（path 不匹配例：机制不触发、白值照吃）."""
    hp, atk, df = _LC_WHITE[lc_id]
    p = _panel(eng)
    assert p["hp"] == pytest.approx(3000 + hp)
    assert p["atk"] == pytest.approx(1000 + atk)
    assert p["def_"] == pytest.approx(df)


def _no_lc_mods(eng):
    return [m for st in eng.state.actors.values()
            for m in st.modifiers if m.startswith("LC_")]


#: 伤害对轴常数：防御区 0.5 × 未击破 0.9 × 期望暴击 1.025
_Z = 0.5 * 0.9 * 1.025


# ---------------------------------------------------------------------------
# 20005 齐颂：进战我方全体攻击 +8%（同类不重复）
# ---------------------------------------------------------------------------

class TestLC20005:
    def test_white_stats_and_path_gate(self):
        eng = _make("20005", path="destruction")
        _assert_white(eng, "20005")
        assert not eng.state.actors["w"].modifiers, "命途不匹配：机制不触发"

    def test_team_atk_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("20005", extra=(ally,))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["20005"] * 1.08)   # 装备者 1317.52×1.08
        assert _panel(eng, "a2")["atk"] == pytest.approx(1000 * 1.08)   # 全队光环

    def test_team_atk_s5(self):
        eng = _make("20005", superimposition=5)
        assert _panel(eng)["atk"] == pytest.approx(_ATK["20005"] * 1.12)


# ---------------------------------------------------------------------------
# 20012 轮契：施放攻击/受击后额外回 4 能（单回合一次）
# ---------------------------------------------------------------------------

class TestLC20012:
    def test_white_stats_and_path_gate(self):
        eng = _make("20012", path="destruction")
        _assert_white(eng, "20012")
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(0.0), "命途不匹配：行动不回能"

    def test_energy_on_action_once_per_turn_s1(self):
        eng = _make("20012")
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(4.0)      # S1 +4
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(4.0)      # 单回合闸：同回合不再触发
        _turn_end(eng, "e1")                            # 任一目标回合结束清闸
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(8.0)      # 新回合可再触发

    def test_energy_on_being_hit_s1(self):
        eng = _make("20012")
        _enemy_hit(eng)
        assert _energy(eng) == pytest.approx(4.0)      # 受击 +4
        _enemy_hit(eng)
        assert _energy(eng) == pytest.approx(4.0)      # 同回合不再触发
        _turn_end(eng, "e1")
        _enemy_hit(eng)
        assert _energy(eng) == pytest.approx(8.0)

    def test_energy_s5(self):
        eng = _make("20012", superimposition=5)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(8.0)      # S5 +8


# ---------------------------------------------------------------------------
# 20019 调和：进战我方全体速度 +12（1 回合）
# ---------------------------------------------------------------------------

class TestLC20019:
    def test_white_stats_and_path_gate(self):
        eng = _make("20019", path="destruction")
        _assert_white(eng, "20019")
        assert _panel(eng)["spd"] == pytest.approx(100.0)

    def test_team_spd_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("20019", extra=(ally,))
        assert _panel(eng)["spd"] == pytest.approx(112.0)       # 平速 +12
        assert _panel(eng, "a2")["spd"] == pytest.approx(112.0)
        m = eng.state.actors["w"].modifiers["LC_20019_MEDIATION_SPD"]
        assert m.duration == 1                                   # 持续 1 回合（#2 恒 1）

    def test_team_spd_s5(self):
        eng = _make("20019", superimposition=5)
        assert _panel(eng)["spd"] == pytest.approx(120.0)


# ---------------------------------------------------------------------------
# 21004 记忆中的模样：击破 +28% + 施放攻击后额外回 4 能（单回合一次）
# ---------------------------------------------------------------------------

class TestLC21004:
    def test_white_stats_and_path_gate(self):
        eng = _make("21004", path="destruction")
        _assert_white(eng, "21004")
        assert _panel(eng)["break_effect"] == pytest.approx(0.0)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(0.0)

    def test_break_and_energy_s1(self):
        eng = _make("21004")
        assert _panel(eng)["break_effect"] == pytest.approx(0.28)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(4.0)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(4.0)      # 单回合锁
        _turn_end(eng, "w")
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(8.0)

    def test_break_and_energy_s5(self):
        eng = _make("21004", superimposition=5)
        assert _panel(eng)["break_effect"] == pytest.approx(0.56)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(8.0)      # S5 +8


# ---------------------------------------------------------------------------
# 21011 与行星相会：与装备者同属性的我方目标伤害 +12%
# ---------------------------------------------------------------------------

class TestLC21011:
    def _team(self):
        return (_member("a2", element="fire", actions=(_BASIC,)),
                _member("a3", element="ice", actions=(_BASIC_ICE,)))

    def test_white_stats_and_path_gate(self):
        eng = _make("21011", path="destruction", extra=self._team())
        _assert_white(eng, "21011")
        assert not _no_lc_mods(eng), "命途不匹配：无人持有光环"

    def test_element_match_s1(self):
        eng = _make("21011", extra=self._team())
        assert "LC_21011_ELEM_DMG" in eng.state.actors["w"].modifiers     # 同属性装备者
        assert "LC_21011_ELEM_DMG" in eng.state.actors["a2"].modifiers    # 同属性队友
        assert "LC_21011_ELEM_DMG" not in eng.state.actors["a3"].modifiers  # 冰属性队友无
        # 装备者火普攻 = 1423.36 × 1.12 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(_ATK["21011"] * 1.12 * _Z)
        # 冰队友冰普攻不吃 = 1000 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _cast(eng, "a3", "t_basic_i")
        assert before - _hp(eng) == pytest.approx(1000 * 1.0 * _Z)

    def test_element_match_s5(self):
        eng = _make("21011", superimposition=5, extra=self._team())
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(_ATK["21011"] * 1.24 * _Z)


# ---------------------------------------------------------------------------
# 21018 舞！舞！舞！：装备者开大后我方全体行动提前 16%
# ---------------------------------------------------------------------------

class TestLC21018:
    def test_white_stats_and_path_gate(self):
        eng = _make("21018", path="destruction", actions=(_ULT,))
        _assert_white(eng, "21018")
        _ult(eng)
        assert _remaining(eng) == pytest.approx(10000.0), "命途不匹配：不拉条"

    def test_advance_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("21018", actions=(_ULT,), extra=(ally,))
        assert _remaining(eng) == pytest.approx(10000.0)
        _ult(eng)
        assert _remaining(eng) == pytest.approx(8400.0)          # 装备者 -16%
        assert _remaining(eng, "a2") == pytest.approx(8400.0)    # 全队 -16%

    def test_advance_s5(self):
        eng = _make("21018", superimposition=5, actions=(_ULT,))
        _ult(eng)
        assert _remaining(eng) == pytest.approx(7600.0)          # S5 -24%


# ---------------------------------------------------------------------------
# 21032 镂月裁云之意：随机三选一【机制待收编——random_pick 原语未落地】
# ---------------------------------------------------------------------------

class TestLC21032:
    def test_white_stats(self):
        eng = _make("21032")
        _assert_white(eng, "21032")

    def test_pending_no_hooks_no_mods(self):
        # 随机三选一缺 random_pick 原语（05_effects §5.2 待收编）——不硬凑：
        # 无 hook 注册、无任何 modifier（staging 三件全上常驻与官方不符，已摘）
        eng = _make("21032")
        assert not eng._compiled_hooks
        assert not _no_lc_mods(eng)
        _cast(eng, "w", "t_basic")
        assert not _no_lc_mods(eng)


# ---------------------------------------------------------------------------
# 21036 美梦小镇大冒险：童心——最新使用类型技能伤害 +12%（换型覆盖）
# ---------------------------------------------------------------------------

class TestLC21036:
    def test_white_stats_and_path_gate(self):
        eng = _make("21036", path="destruction", actions=(_BASIC, _ULT))
        _assert_white(eng, "21036")
        _cast(eng, "w", "t_basic")
        assert not _no_lc_mods(eng)

    def test_childlike_swap_s1(self):
        eng = _make("21036", actions=(_BASIC, _ULT))
        _cast(eng, "w", "t_basic")      # 触发型行动本身不吃（on_action 结算后挂）
        assert _panel(eng)["dmg_bonus"].get("basic_dmg_boost", 0.0) == pytest.approx(0.12)
        assert "LC_21036_CHILDLIKE_ULT" not in eng.state.actors["w"].modifiers
        # 童心·普攻期间：普攻 = 1423.36 × 1.12 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(_ATK["21036"] * 1.12 * _Z)
        # 换型：开大 → 童心·终结技覆盖，普攻桶摘除
        _ult(eng)
        assert _panel(eng)["dmg_bonus"].get("basic_dmg_boost", 0.0) == pytest.approx(0.0)
        assert _panel(eng)["dmg_bonus"].get("ultimate_dmg_boost", 0.0) == pytest.approx(0.12)
        assert "LC_21036_CHILDLIKE_BASIC" not in eng.state.actors["w"].modifiers
        # 童心·终结技期间：终结技 = 1423.36 × 1.12 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _ult(eng)
        assert before - _hp(eng) == pytest.approx(_ATK["21036"] * 1.12 * _Z)

    def test_childlike_s5(self):
        eng = _make("21036", superimposition=5)
        _cast(eng, "w", "t_basic")
        assert _panel(eng)["dmg_bonus"].get("basic_dmg_boost", 0.0) == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# 21046 芳华待灼：装备者攻击 +16%；≥2 名同命途角色暴伤 +16%（任意相同命途）
# ---------------------------------------------------------------------------

class TestLC21046:
    def test_white_stats_and_path_gate(self):
        ally = _member("a2", path="destruction", actions=(_BASIC,))
        eng = _make("21046", path="destruction", extra=(ally,))
        _assert_white(eng, "21046")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["21046"]), "命途不匹配：攻击被动不触发"
        assert not _no_lc_mods(eng)

    def test_shared_path_s1(self):
        a2 = _member("a2", path="harmony", actions=(_BASIC,))
        a3 = _member("a3", path="destruction", actions=(_BASIC,))
        eng = _make("21046", extra=(a2, a3))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["21046"] * 1.16)      # 装备者攻击被动
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.16)     # 同谐 2 人互享
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.16)
        assert _panel(eng, "a3")["crit_dmg"] == pytest.approx(0.5)      # 独命途无

    def test_no_shared_path(self):
        a2 = _member("a2", path="destruction", actions=(_BASIC,))
        a3 = _member("a3", path="nihility", actions=(_BASIC,))
        eng = _make("21046", extra=(a2, a3))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["21046"] * 1.16)      # 攻击被动不受编队影响
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)            # 无相同命途对
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5)

    def test_shared_path_s5(self):
        a2 = _member("a2", path="harmony", actions=(_BASIC,))
        eng = _make("21046", superimposition=5, extra=(a2,))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["21046"] * 1.32)
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.32)


# ---------------------------------------------------------------------------
# 21056 追逐风的时候：进战我方全体击破伤害 +16%
# ---------------------------------------------------------------------------

class TestLC21056:
    def test_white_stats_and_path_gate(self):
        eng = _make("21056", path="destruction")
        _assert_white(eng, "21056")
        assert _panel(eng)["dmg_bonus"].get("break_dmg_boost", 0.0) == pytest.approx(0.0)

    def test_break_boost_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("21056", extra=(ally,))
        assert _panel(eng)["dmg_bonus"]["break_dmg_boost"] == pytest.approx(0.16)
        assert _panel(eng, "a2")["dmg_bonus"]["break_dmg_boost"] == pytest.approx(0.16)

    def test_break_boost_s5(self):
        eng = _make("21056", superimposition=5)
        assert _panel(eng)["dmg_bonus"]["break_dmg_boost"] == pytest.approx(0.24)


# ---------------------------------------------------------------------------
# 22002 为了明日的旅途：装备者攻击 +16%；开大后增伤 +18%（1 回合）
# ---------------------------------------------------------------------------

class TestLC22002:
    def test_white_stats_and_path_gate(self):
        eng = _make("22002", path="destruction", actions=(_BASIC, _ULT))
        _assert_white(eng, "22002")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22002"]), "命途不匹配：攻击被动不触发"
        _ult(eng)
        assert "LC_22002_DMG_BOOST" not in eng.state.actors["w"].modifiers

    def test_atk_and_ult_dmg_s1(self):
        eng = _make("22002", actions=(_BASIC, _ULT))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22002"] * 1.16)
        _ult(eng)       # 触发型终结技本身不吃（on_ultimate 结算后挂）
        m = eng.state.actors["w"].modifiers["LC_22002_DMG_BOOST"]
        assert m.stat_effects["all_dmg"] == pytest.approx(0.18)
        assert m.duration == 1
        # 增伤期间普攻 = 1476.28×1.16 × 1.18 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(_ATK["22002"] * 1.16 * 1.18 * _Z)

    def test_ult_dmg_s5(self):
        eng = _make("22002", superimposition=5, actions=(_BASIC, _ULT))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22002"] * 1.32)
        _ult(eng)
        m = eng.state.actors["w"].modifiers["LC_22002_DMG_BOOST"]
        assert m.stat_effects["all_dmg"] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# 22005 永远的迷境饭：装备者攻击 +16%；战技后攻击 +8%/层（至多 3 层）
# ---------------------------------------------------------------------------

class TestLC22005:
    def test_white_stats_and_path_gate(self):
        eng = _make("22005", path="destruction", actions=(_SKILL,))
        _assert_white(eng, "22005")
        _cast(eng, "w", "t_skill")
        assert "LC_22005_SKILL_ATK" not in eng.state.actors["w"].modifiers

    def test_skill_stacks_s1(self):
        eng = _make("22005", actions=(_SKILL,))
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * 1.16)          # 0 层
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * (1.16 + 0.08))  # 1 层
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * (1.16 + 0.16))  # 2 层
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * (1.16 + 0.24))  # 3 层
        m = eng.state.actors["w"].modifiers["LC_22005_SKILL_ATK"]
        assert m.stacks == 3
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * (1.16 + 0.24))  # 上限 3 层

    def test_skill_stacks_s5(self):
        eng = _make("22005", superimposition=5, actions=(_SKILL,))
        for _ in range(3):
            _cast(eng, "w", "t_skill")
        assert _panel(eng)["atk"] == pytest.approx(_ATK["22005"] * (1.32 + 0.48))  # S5 每层 +0.16


# ---------------------------------------------------------------------------
# 23003 但战斗还未结束：ERR +10%；对友开大每 2 次产 1 点；战技后下个行动队友增伤 30%
# ---------------------------------------------------------------------------

class TestLC23003:
    def test_white_stats_and_path_gate(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23003", path="destruction", actions=(_ULT_ALLY, _SKILL), extra=(ally,))
        _assert_white(eng, "23003")
        assert _panel(eng)["energy_regen"] == pytest.approx(1.0)
        _ult(eng, aid="t_ult_a", target_id="a2")
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert eng.state.skill_points == 3, "命途不匹配：对友开大不产点"
        _cast(eng, "w", "t_skill")
        assert "LC_23003_SKILL_MARK" not in eng.state.actors["w"].modifiers

    def test_energy_regen_s1(self):
        eng = _make("23003")
        assert _panel(eng)["energy_regen"] == pytest.approx(1.10)

    def test_sp_every_two_ally_ults_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23003", actions=(_ULT_ALLY,), extra=(ally,))
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert eng.state.skill_points == 3                      # 第 1 次不产
        assert eng.state.actors["w"].modifiers["LC_23003_ULT_COUNT"].stacks == 1
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert eng.state.skill_points == 4                      # 第 2 次产 1 点
        assert "LC_23003_ULT_COUNT" not in eng.state.actors["w"].modifiers
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert eng.state.skill_points == 4                      # 第 3 次重新计数
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert eng.state.skill_points == 5                      # 第 4 次再产

    def test_enemy_target_ult_not_counted(self):
        eng = _make("23003", actions=(_ULT,))
        _ult(eng)                                               # 对敌开大不触发「对我方目标」
        assert "LC_23003_ULT_COUNT" not in eng.state.actors["w"].modifiers
        assert eng.state.skill_points == 3

    def test_skill_next_ally_dmg_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23003", actions=(_SKILL,), extra=(ally,))
        _cast(eng, "w", "t_skill")
        assert "LC_23003_SKILL_MARK" in eng.state.actors["w"].modifiers
        _turn_start(eng, "a2")                                   # 下一个行动的队友
        m = eng.state.actors["a2"].modifiers["LC_23003_DMG_BOOST"]
        assert m.stat_effects["all_dmg"] == pytest.approx(0.30)
        assert m.duration == 1
        assert "LC_23003_SKILL_MARK" not in eng.state.actors["w"].modifiers
        # 增伤期间队友普攻 = 1000 × 1.30 × 0.5 × 0.9 × 1.025
        before = _hp(eng)
        _cast(eng, "a2", "t_basic")
        assert before - _hp(eng) == pytest.approx(1000 * 1.30 * _Z)

    def test_skill_mark_not_consumed_by_self_turn(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23003", actions=(_SKILL,), extra=(ally,))
        _cast(eng, "w", "t_skill")
        _turn_start(eng, "w")                                    # 装备者自身回合不消耗
        assert "LC_23003_SKILL_MARK" in eng.state.actors["w"].modifiers
        assert "LC_23003_DMG_BOOST" not in eng.state.actors["w"].modifiers

    def test_skill_next_ally_dmg_s5(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23003", superimposition=5, actions=(_SKILL,), extra=(ally,))
        _cast(eng, "w", "t_skill")
        _turn_start(eng, "a2")
        m = eng.state.actors["a2"].modifiers["LC_23003_DMG_BOOST"]
        assert m.stat_effects["all_dmg"] == pytest.approx(0.50)
        assert _panel(eng)["energy_regen"] == pytest.approx(1.18)


# ---------------------------------------------------------------------------
# 23019 镜中故我：击破 +60%；开大全队增伤 24%（3 回合）+击破≥150% 产点；
# 每波次开始全队回 10 能（ERR 豁免）
# ---------------------------------------------------------------------------

class TestLC23019:
    def test_white_stats_and_path_gate(self):
        eng = _make("23019", path="destruction")
        _assert_white(eng, "23019")
        assert _panel(eng)["break_effect"] == pytest.approx(0.0)
        assert _energy(eng) == pytest.approx(0.0), "命途不匹配：首波不回能"

    def test_break_and_first_wave_energy_s1(self):
        ally = _member("a2", actions=(_BASIC,),
                       base_stats={"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100,
                                   "energy_regen": 1.5})
        eng = _make("23019", extra=(ally,))
        assert _panel(eng)["break_effect"] == pytest.approx(0.60)
        assert _energy(eng) == pytest.approx(10.0)              # 首波（战斗开始）+10
        assert _energy(eng, "a2") == pytest.approx(10.0)        # ERR 1.5 也不乘——具名豁免
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert _energy(eng) == pytest.approx(20.0)              # 转波次再 +10

    def test_ult_team_dmg_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23019", actions=(_ULT,), extra=(ally,))
        _ult(eng)
        for aid in ("w", "a2"):
            m = eng.state.actors[aid].modifiers["LC_23019_TEAM_DMG"]
            assert m.stat_effects["all_dmg"] == pytest.approx(0.24)
            assert m.duration == 3
        assert eng.state.skill_points == 3, "击破 0.60 < 150%：不产点"

    def test_ult_sp_at_break_threshold(self):
        # 面板击破 = 自带 0.90 + 光锥 0.60 = 1.50 ≥ 150% → 开大产 1 点
        eng = _make("23019", actions=(_ULT,),
                    member_kw={"base_stats": {"atk": 1000, "spd": 100, "hp": 3000,
                                              "max_energy": 100, "break_effect": 0.9}})
        assert _panel(eng)["break_effect"] == pytest.approx(1.5)
        _ult(eng)
        assert eng.state.skill_points == 4
        # 面板击破 1.40 < 150% → 不产
        eng = _make("23019", actions=(_ULT,),
                    member_kw={"base_stats": {"atk": 1000, "spd": 100, "hp": 3000,
                                              "max_energy": 100, "break_effect": 0.8}})
        _ult(eng)
        assert eng.state.skill_points == 3

    def test_s5(self):
        eng = _make("23019", superimposition=5, actions=(_ULT,))
        assert _panel(eng)["break_effect"] == pytest.approx(1.00)
        _ult(eng)
        m = eng.state.actors["w"].modifiers["LC_23019_TEAM_DMG"]
        assert m.stat_effects["all_dmg"] == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# 23021 游戏尘寰：装备者暴伤 +32%；假面期间队友暴击 +10%/暴伤 +28%（不含装备者）；
# 每恢复 1 战技点 1 层彩焰，满 4 层转化假面 4 回合
# ---------------------------------------------------------------------------

class TestLC23021:
    def test_white_stats_and_path_gate(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23021", path="destruction", extra=(ally,))
        _assert_white(eng, "23021")
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)
        assert not _no_lc_mods(eng)

    def test_mask_team_crit_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23021", extra=(ally,))
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.32)   # 装备者只吃被动
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)        # 不吃假面光环
        assert _panel(eng, "a2")["crit_rate"] == pytest.approx(0.05 + 0.10)
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.28)
        m = eng.state.actors["w"].modifiers["LC_23021_MASK"]
        assert m.duration == 3                                         # 进战假面 3 回合

    def test_radiant_flame_to_mask_s1(self):
        ally = _member("a2", actions=(_BASIC_SP,))
        eng = _make("23021", extra=(ally,), initial_sp=0)
        _cast(eng, "a2", "t_basic_sp")
        assert eng.state.skill_points == 1
        assert eng.state.actors["w"].modifiers["LC_23021_RADIANT_FLAME"].stacks == 1
        _cast(eng, "a2", "t_basic_sp")
        _cast(eng, "a2", "t_basic_sp")
        assert eng.state.actors["w"].modifiers["LC_23021_RADIANT_FLAME"].stacks == 3
        _cast(eng, "a2", "t_basic_sp")                                 # 第 4 层→转化
        assert eng.state.skill_points == 4
        assert "LC_23021_RADIANT_FLAME" not in eng.state.actors["w"].modifiers
        m = eng.state.actors["w"].modifiers["LC_23021_MASK"]
        assert m.duration == 4                                         # 转化假面 4 回合
        assert _panel(eng, "a2")["crit_rate"] == pytest.approx(0.15)   # 光环随假面存续

    def test_s5(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23021", superimposition=5, extra=(ally,))
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.60)
        assert _panel(eng, "a2")["crit_rate"] == pytest.approx(0.05 + 0.14)
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.56)


# ---------------------------------------------------------------------------
# 23038 如果时间是一朵花：装备者暴伤 +36%；进战回 21 能+谕示（全队暴伤 +48%，
# 2 回合）；追加攻击后回 12 能+谕示
# ---------------------------------------------------------------------------

class TestLC23038:
    def test_white_stats_and_path_gate(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23038", path="destruction", extra=(ally,))
        _assert_white(eng, "23038")
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)
        assert _energy(eng) == pytest.approx(0.0)
        assert not _no_lc_mods(eng)

    def test_battle_start_s1(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23038", extra=(ally,))
        assert _energy(eng) == pytest.approx(21.0)                     # 进战 +21
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.36 + 0.48)  # 被动+谕示
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.48)   # 全队谕示
        m = eng.state.actors["w"].modifiers["LC_23038_PRESAGE"]
        assert m.duration == 2

    def test_follow_up_s1(self):
        eng = _make("23038", actions=(_FUA,))
        _cast(eng, "w", "t_fua")
        assert _energy(eng) == pytest.approx(21.0 + 12.0)              # 追加 +12
        assert "LC_23038_PRESAGE" in eng.state.actors["w"].modifiers   # 谕示续杯
        _cast(eng, "w", "t_fua")
        assert _energy(eng) == pytest.approx(21.0 + 24.0)              # 每次追加都回

    def test_s5(self):
        ally = _member("a2", actions=(_BASIC,))
        eng = _make("23038", superimposition=5, extra=(ally,))
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.60 + 0.96)
        assert _panel(eng, "a2")["crit_dmg"] == pytest.approx(0.5 + 0.96)
