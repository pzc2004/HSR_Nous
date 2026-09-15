"""丰饶（Priest→abundance）光锥族 e2e：staging→fixtures 验收批.

16 件（20001/20008/20015/21000/21007/21014/21021/21028/21035/21048/21055/22001/23008/
23013/23017/23032）。
每件：白值三围断言（面板=基础值+光锥白值）+ 机制行为断言（手算对轴）+ 命途限制分例
（path=abundance 触发 / path=destruction 不触发）+ 叠影差分（S1 全量 + S5 抽查）。
fixture 勘正条目见各 fixture 头注（tests/fixtures/templates/light_cones/）。

口径常数（手算对轴）：装备员 atk 1000 / spd 100 / hp 3000 / def 0 / max_energy 100，
inline 普攻 scaling atk 1.0；假人 def 1000 → 防御区 0.5（lv80），弱点全配 → 抗性区 1.0，
未击破 0.9，期望暴击区 = 0.05×1.5+0.95 = 1.025。直伤基准（无增伤易伤）=
1000×0.5×0.9×1.025 = 461.25。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

Z = 0.5 * 0.9 * 1.025            # 直伤链：防御区×未击破×期望暴击区
BASE_DMG = 1000 * Z              # 461.25

_BASIC = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_BASIC_ZERO_E = {**_BASIC, "energy_gain": 0}   # 显式不回能——能量断言隔离行动回能
_BASIC_AOE = {**_BASIC_ZERO_E, "action_id": "t_basic_aoe", "name": "普攻·群",
              "target_type": "aoe"}
_SKILL_ZERO_E = {"action_id": "t_skill", "name": "战技", "action_type": "skill",
                 "target_type": "single", "damage_type": "fire", "energy_gain": 0,
                 "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "skill_point_cost": 1}
_ULT = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
        "target_type": "single", "damage_type": "fire", "energy_cost": 100,
        "scaling": [{"atk": 1.0}], "toughness_dmg": 30, "energy_gain": 0}


def _member(aid, *, path="abundance", lc=None, sup=1, actions=(_BASIC,), stats=None):
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100,
                        **(stats or {})},
         "actions": list(actions)}
    if path:
        m["path"] = path
    if lc:
        m["light_cone_template"] = lc
        m["light_cone"] = {"superimposition": sup}
    return m


def _make(lc_id, *, sup=1, path="abundance", actions=(_BASIC,), extra=(), n_enemies=1,
          max_toughness=100, stats=None):
    member = _member("w", path=path, lc=lc_id, sup=sup, actions=actions, stats=stats)
    build = {"build": {"team": [member, *extra],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": f"e{i + 1}", "name": f"假人{i + 1}", "hp": 1e9, "spd": 100,
         "atk": 1000, "def": 1000, "max_toughness": max_toughness,
         "weakness": ["fire", "ice", "thunder", "wind",
                      "quantum", "imaginary", "physical"]}
        for i in range(n_enemies)],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
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


def _hp(eng, aid):
    return eng.state.actors[aid].current_hp


def _energy(eng, aid="w"):
    return eng.state.actors[aid].current_energy


def _remaining(eng, aid="w"):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _heal100(eng):
    """治疗管线 100 基数（装备员自疗）——heal_bonus 行为断言."""
    w = eng.state.actors["w"]
    return eng.pipeline.heal(w, w, 100.0).value


# ---------------------------------------------------------------------------
# 20001 物穰：治疗量 +12-24%（官方为战技/终结技施放域，按常驻收编——fixture 头注待实测条）
# ---------------------------------------------------------------------------

class TestLC20001:
    W = {"hp": 3952.56, "atk": 1264.6, "def": 264.6}

    def test_base_stats(self):
        p = _panel(_make("20001"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_heal_bonus_s1(self):
        eng = _make("20001")
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.12)
        assert _heal100(eng) == pytest.approx(112.0)

    def test_heal_bonus_s5(self):
        eng = _make("20001", sup=5)
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.24)
        assert _heal100(eng) == pytest.approx(124.0)

    def test_path_mismatch(self):
        eng = _make("20001", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"]), "白值不受命途限制"
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.0)
        assert _heal100(eng) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 20008 嘉果：战斗开始我方全体 +6-12 能量（吃 ERR，不在 §5.3 豁免清单）
# ---------------------------------------------------------------------------

class TestLC20008:
    W = {"hp": 3952.56, "atk": 1317.52, "def": 198.45}

    def test_base_stats(self):
        p = _panel(_make("20008"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_battle_start_energy_s1(self):
        eng = _make("20008", extra=(_member("a2", path=""),))
        assert _energy(eng) == pytest.approx(6.0)
        assert _energy(eng, "a2") == pytest.approx(6.0), "我方全体同回"

    def test_battle_start_energy_s5(self):
        eng = _make("20008", sup=5)
        assert _energy(eng) == pytest.approx(12.0)

    def test_path_mismatch(self):
        eng = _make("20008", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _energy(eng) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 20015 蕃息：装备者普攻后下一次行动提前 12-20%
# ---------------------------------------------------------------------------

class TestLC20015:
    W = {"hp": 3952.56, "atk": 1317.52, "def": 198.45}

    def test_base_stats(self):
        p = _panel(_make("20015"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_advance_after_basic_s1(self):
        eng = _make("20015")
        assert _remaining(eng) == pytest.approx(10000.0)
        _cast(eng, "w", "t_basic")
        assert _remaining(eng) == pytest.approx(8800.0)   # 提前 12% = 剩余距离 -1200

    def test_advance_after_basic_s5(self):
        eng = _make("20015", sup=5)
        _cast(eng, "w", "t_basic")
        assert _remaining(eng) == pytest.approx(8000.0)   # 提前 20%

    def test_ally_basic_no_advance(self):
        eng = _make("20015", extra=(_member("a2", path=""),))
        _cast(eng, "a2", "t_basic")
        assert _remaining(eng) == pytest.approx(10000.0), "队友普攻不拉装备者的条"

    def test_path_mismatch(self):
        eng = _make("20015", path="destruction")
        _cast(eng, "w", "t_basic")
        assert _remaining(eng) == pytest.approx(10000.0)


# ---------------------------------------------------------------------------
# 21000 一场术后对话：能量恢复效率 +8-16% + 治疗量 +12-24%（官方为终结技施放域，
# 按常驻收编——fixture 头注待实测条）
# ---------------------------------------------------------------------------

class TestLC21000:
    W = {"hp": 4058.4, "atk": 1423.36, "def": 330.75}

    def test_base_stats(self):
        p = _panel(_make("21000"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_err_and_heal_s1(self):
        eng = _make("21000")
        assert _panel(eng)["energy_regen"] == pytest.approx(1.08)
        assert _heal100(eng) == pytest.approx(112.0)
        _cast(eng, "w", "t_basic")      # 默认普攻回能 20 × 1.08
        assert _energy(eng) == pytest.approx(21.6)

    def test_err_and_heal_s5(self):
        eng = _make("21000", sup=5)
        assert _panel(eng)["energy_regen"] == pytest.approx(1.16)
        assert _heal100(eng) == pytest.approx(124.0)

    def test_path_mismatch(self):
        eng = _make("21000", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["energy_regen"] == pytest.approx(1.0)
        assert _heal100(eng) == pytest.approx(100.0)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# 21007 同一种心情：治疗量 +10-20% + 施放战技时我方全体 +2-4 能量（吃 ERR）
# ---------------------------------------------------------------------------

class TestLC21007:
    W = {"hp": 3952.56, "atk": 1423.36, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("21007"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_heal_and_skill_energy_s1(self):
        eng = _make("21007", actions=(_BASIC_ZERO_E, _SKILL_ZERO_E),
                    extra=(_member("a2", path=""),))
        assert _heal100(eng) == pytest.approx(110.0)
        _cast(eng, "w", "t_skill")
        assert _energy(eng) == pytest.approx(2.0)
        assert _energy(eng, "a2") == pytest.approx(2.0), "我方全体同回"

    def test_skill_energy_s5(self):
        eng = _make("21007", sup=5, actions=(_SKILL_ZERO_E,))
        assert _heal100(eng) == pytest.approx(120.0)
        _cast(eng, "w", "t_skill")
        assert _energy(eng) == pytest.approx(4.0)

    def test_basic_no_energy(self):
        eng = _make("21007", actions=(_BASIC_ZERO_E,))
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(0.0), "普攻不触发战技回能"

    def test_path_mismatch(self):
        eng = _make("21007", path="destruction", actions=(_SKILL_ZERO_E,))
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _heal100(eng) == pytest.approx(100.0)
        _cast(eng, "w", "t_skill")
        assert _energy(eng) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 21014 此时恰好：效果抵抗 +16-32% + 治疗量=min(效果抵抗×#2, #3)（stat_exprs 现场求值）
# ---------------------------------------------------------------------------

class TestLC21014:
    W = {"hp": 3952.56, "atk": 1423.36, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("21014"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_res_and_heal_s1(self):
        eng = _make("21014")
        assert _panel(eng)["effect_res"] == pytest.approx(0.16)
        # heal_bonus = min(0.33×0.16, 0.15) = 0.0528
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.33 * 0.16)
        assert _heal100(eng) == pytest.approx(100 * (1 + 0.33 * 0.16))

    def test_heal_s5(self):
        eng = _make("21014", sup=5)
        assert _panel(eng)["effect_res"] == pytest.approx(0.32)
        # heal_bonus = min(0.45×0.32, 0.27) = 0.144
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.45 * 0.32)

    def test_heal_cap(self):
        eng = _make("21014", stats={"effect_res": 0.5})
        # 面板效果抵抗 0.66 → min(0.33×0.66, 0.15) = 0.15（封顶档）
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.15)
        assert _heal100(eng) == pytest.approx(115.0)

    def test_path_mismatch(self):
        eng = _make("21014", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["effect_res"] == pytest.approx(0.0)
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 21028 暖夜不会漫长：生命上限 +16-32% + 普攻/战技后我方全体按各自生命上限 +2-4% 回血
# ---------------------------------------------------------------------------

class TestLC21028:
    W = {"hp": 4058.4, "atk": 1370.44, "def": 396.9}
    HP_S1 = 4058.4 * 1.16

    def test_base_stats(self):
        p = _panel(_make("21028"))
        assert p["hp"] == pytest.approx(self.W["hp"] * 1.16), "白值生命 ×1.16（S1 生命段）"
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_hp_pct_and_aoe_heal_s1(self):
        eng = _make("21028", actions=(_BASIC_ZERO_E, _SKILL_ZERO_E),
                    extra=(_member("a2", path=""),))
        assert _panel(eng)["hp"] == pytest.approx(self.HP_S1)
        eng.state.actors["w"].current_hp = 1000.0
        eng.state.actors["a2"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000 + self.HP_S1 * 0.02)
        assert _hp(eng, "a2") == pytest.approx(1000 + 3000 * 0.02), "各自生命上限缩放"
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_skill")
        assert _hp(eng, "w") == pytest.approx(1000 + self.HP_S1 * 0.02), "战技同触发"

    def test_heal_s5(self):
        eng = _make("21028", sup=5, actions=(_BASIC_ZERO_E,))
        hp_s5 = 4058.4 * 1.32
        assert _panel(eng)["hp"] == pytest.approx(hp_s5)
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000 + hp_s5 * 0.04)

    def test_ult_no_heal(self):
        eng = _make("21028", actions=(_ULT,))
        eng.state.actors["w"].current_hp = 1000.0
        _ult(eng)
        assert _hp(eng, "w") == pytest.approx(1000.0), "终结技不触发"

    def test_path_mismatch(self):
        eng = _make("21028", path="destruction", actions=(_BASIC_ZERO_E,))
        assert _panel(eng)["hp"] == pytest.approx(4058.4), "生命上限段不生效、白值仍在"
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# 21035 何物为真：击破特攻 +24-48% + 普攻后自疗 2-4% 生命上限 + 800
# ---------------------------------------------------------------------------

class TestLC21035:
    W = {"hp": 4058.4, "atk": 1423.36, "def": 330.75}

    def test_base_stats(self):
        p = _panel(_make("21035"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_break_effect_and_heal_s1(self):
        eng = _make("21035", actions=(_BASIC_ZERO_E,))
        assert _panel(eng)["break_effect"] == pytest.approx(0.24)
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000 + 0.02 * 4058.4 + 800)

    def test_heal_s5(self):
        eng = _make("21035", sup=5, actions=(_BASIC_ZERO_E,))
        assert _panel(eng)["break_effect"] == pytest.approx(0.48)
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000 + 0.04 * 4058.4 + 800)

    def test_path_mismatch(self):
        eng = _make("21035", path="destruction", actions=(_BASIC_ZERO_E,))
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["break_effect"] == pytest.approx(0.0)
        eng.state.actors["w"].current_hp = 1000.0
        _cast(eng, "w", "t_basic")
        assert _hp(eng, "w") == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# 21048 梦的蒙太奇：速度 +8-12% + 攻击已击破目标回 3-5 能（每次攻击 1 次、每回合 2 次）
# ---------------------------------------------------------------------------

class TestLC21048:
    W = {"hp": 3952.56, "atk": 1423.36, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("21048"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_spd_s1(self):
        assert _panel(_make("21048"))["spd"] == pytest.approx(108.0)

    def test_energy_proc_and_caps_s1(self):
        eng = _make("21048", actions=(_BASIC_ZERO_E,), max_toughness=30)
        for _ in range(3):               # 3 击削韧 30→0，第 3 击造成击破（命中前未破）
            _cast(eng, "w", "t_basic")
        assert eng.state.actors["e1"].broken is True
        assert _energy(eng) == pytest.approx(0.0), "造成击破的那一击不触发"
        _cast(eng, "w", "t_basic")       # 第 4 击：命中前已破 → 触发 1
        assert _energy(eng) == pytest.approx(3.0)
        assert eng.state.actors["w"].modifiers["LC_21048_PROC_TURN"].stacks == 1
        _cast(eng, "w", "t_basic")       # 触发 2
        assert _energy(eng) == pytest.approx(6.0)
        _cast(eng, "w", "t_basic")       # 每回合 2 次上限
        assert _energy(eng) == pytest.approx(6.0)
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)   # 回合开始重置
        assert eng.state.actors["w"].modifiers["LC_21048_PROC_TURN"].stacks == 2
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(9.0)

    def test_aoe_counts_once_per_attack(self):
        eng = _make("21048", actions=(_BASIC_AOE,), n_enemies=2, max_toughness=30)
        for _ in range(3):
            _cast(eng, "w", "t_basic_aoe")
        assert eng.state.actors["e1"].broken and eng.state.actors["e2"].broken
        _cast(eng, "w", "t_basic_aoe")   # 群攻命中 2 个已破目标 → 按一次攻击计 1 次
        assert _energy(eng) == pytest.approx(3.0)

    def test_energy_proc_s5(self):
        eng = _make("21048", sup=5, actions=(_BASIC_ZERO_E,), max_toughness=30)
        assert _panel(eng)["spd"] == pytest.approx(112.0)
        for _ in range(4):
            _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(5.0)

    def test_path_mismatch(self):
        eng = _make("21048", path="destruction", actions=(_BASIC_ZERO_E,), max_toughness=30)
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["spd"] == pytest.approx(100.0)
        for _ in range(4):
            _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 21055 直到明天的明天：治疗量 +12-24% + 我方目标 HP≥50% 时增伤 +12-20%（逐目标门控）
# ---------------------------------------------------------------------------

class TestLC21055:
    W = {"hp": 4058.4, "atk": 1476.28, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("21055"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_heal_and_conditional_dmg_s1(self):
        eng = _make("21055", extra=(_member("a2", path=""),))
        assert _heal100(eng) == pytest.approx(112.0)
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.12), "满血生效"
        assert _panel(eng, "a2")["dmg_bonus"]["all"] == pytest.approx(0.12), "队友同生效"
        eng.state.actors["a2"].current_hp = 1200.0      # a2 掉到 40%
        assert _panel(eng, "a2")["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0), \
            "逐目标门控：a2 失效不影响装备者"
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.12)
        eng.state.actors["w"].current_hp = 1200.0       # 装备者掉到 40%
        assert _panel(eng)["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0)

    def test_damage_number_s1(self):
        eng = _make("21055")
        dmg = 1476.28 * Z                     # 攻击含光锥白值 476.28
        before = _hp(eng, "e1")
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(dmg * 1.12)
        eng.state.actors["w"].current_hp = 1200.0
        before = _hp(eng, "e1")
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(dmg), "低于 50% 无增伤"

    def test_dmg_s5(self):
        eng = _make("21055", sup=5)
        assert _heal100(eng) == pytest.approx(124.0)
        assert _panel(eng)["dmg_bonus"]["all"] == pytest.approx(0.2)

    def test_path_mismatch(self):
        eng = _make("21055", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _heal100(eng) == pytest.approx(100.0)
        assert _panel(eng)["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 23008 棺的回响：攻击力 +24-40% + 攻击每击中 1 敌回 3-5 能（每次攻击 ≤3 次）
#   + 终结技后我方全体速度 +12-20（1 回合）
# ---------------------------------------------------------------------------

class TestLC23008:
    W = {"hp": 4164.24, "atk": 1582.12, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("23008"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"] * 1.24), "白值攻击 ×1.24"
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_attack_energy_single_s1(self):
        eng = _make("23008", actions=(_BASIC_ZERO_E,))
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(3.0)
        _cast(eng, "w", "t_basic")
        assert _energy(eng) == pytest.approx(6.0), "每次攻击后额度补满"

    def test_attack_energy_aoe_cap_s1(self):
        eng = _make("23008", actions=(_BASIC_AOE,), n_enemies=4)
        _cast(eng, "w", "t_basic_aoe")
        assert _energy(eng) == pytest.approx(9.0), "4 目标按每次攻击最多 3 次截断"

    def test_ult_spd_buff_s1(self):
        eng = _make("23008", actions=(_ULT,), extra=(_member("a2", path=""),))
        _ult(eng)
        assert _panel(eng)["spd"] == pytest.approx(112.0)
        assert _panel(eng, "a2")["spd"] == pytest.approx(112.0), "我方全体同加速"
        mod = eng.state.actors["w"].modifiers["LC_23008_SPD_BUFF"]
        assert mod.duration == 1
        assert _energy(eng) == pytest.approx(3.0), "终结技攻击同触发击中回能"

    def test_s5(self):
        eng = _make("23008", sup=5, actions=(_ULT,))
        assert _panel(eng)["atk"] == pytest.approx(self.W["atk"] * 1.4)
        _ult(eng)
        assert _panel(eng)["spd"] == pytest.approx(120.0)
        assert _energy(eng) == pytest.approx(5.0)

    def test_path_mismatch(self):
        eng = _make("23008", path="destruction", actions=(_ULT,))
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["atk"] == pytest.approx(self.W["atk"]), "攻击段不生效、白值仍在"
        _ult(eng)
        assert _panel(eng)["spd"] == pytest.approx(100.0)
        assert _energy(eng) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 23013 时节不居：生命上限 +18-30% + 治疗量 +12-20%
# （记录治疗量→附加伤害段未收编——通道缺口与待实测清单见 fixture 头注）
# ---------------------------------------------------------------------------

class TestLC23013:
    W = {"hp": 4270.08, "atk": 1476.28, "def": 463.05}

    def test_base_stats(self):
        p = _panel(_make("23013"))
        assert p["hp"] == pytest.approx(self.W["hp"] * 1.18), "白值生命 ×1.18（S1 生命段）"
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_hp_and_heal_s1(self):
        eng = _make("23013")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"] * 1.18)
        assert _heal100(eng) == pytest.approx(112.0)

    def test_hp_and_heal_s5(self):
        eng = _make("23013", sup=5)
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"] * 1.3)
        assert _heal100(eng) == pytest.approx(120.0)

    def test_path_mismatch(self):
        eng = _make("23013", path="destruction")
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"]), "生命段不生效、白值仍在"
        assert _heal100(eng) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 23032 唯有香如故：击破特攻 +60-100% + 终结技攻击命中挂【忘忧】（易伤 10-18%，
#   装备者当前击破特攻 ≥150% 追加 8-16%——施加时快照分流）
# ---------------------------------------------------------------------------

class TestLC23032:
    W = {"hp": 4058.4, "atk": 1529.2, "def": 529.2}

    def test_base_stats(self):
        p = _panel(_make("23032"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_break_effect_and_woefree_s1(self):
        eng = _make("23032", actions=(_BASIC_ZERO_E, _ULT))
        assert _panel(eng)["break_effect"] == pytest.approx(0.6)
        _cast(eng, "w", "t_basic")
        assert "LC_23032_WOEFREE" not in eng.state.actors["e1"].modifiers, "普攻不挂忘忧"
        _ult(eng)
        mod = eng.state.actors["e1"].modifiers["LC_23032_WOEFREE"]
        assert mod.stat_effects["vulnerability"] == pytest.approx(0.1), \
            "击破 0.6 < 1.5 无追加易伤"
        assert mod.duration == 2
        before = _hp(eng, "e1")
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(1529.2 * Z * 1.1)

    def test_woefree_extra_vuln_s1(self):
        eng = _make("23032", actions=(_BASIC_ZERO_E, _ULT), stats={"break_effect": 1.0})
        assert _panel(eng)["break_effect"] == pytest.approx(1.6)
        _ult(eng)
        mod = eng.state.actors["e1"].modifiers["LC_23032_WOEFREE"]
        assert mod.stat_effects["vulnerability"] == pytest.approx(0.1 + 0.08)
        before = _hp(eng, "e1")
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng, "e1") == pytest.approx(1529.2 * Z * 1.18)

    def test_woefree_s5(self):
        eng = _make("23032", sup=5, actions=(_ULT,))
        assert _panel(eng)["break_effect"] == pytest.approx(1.0)
        _ult(eng)
        assert eng.state.actors["e1"].modifiers[
            "LC_23032_WOEFREE"].stat_effects["vulnerability"] == pytest.approx(0.18)

    def test_ally_ult_no_woefree(self):
        eng = _make("23032", actions=(_BASIC_ZERO_E,),
                    extra=(_member("a2", path="", actions=(_ULT,)),))
        _ult(eng, owner="a2")
        assert "LC_23032_WOEFREE" not in eng.state.actors["e1"].modifiers, \
            "队友终结技不触发装备者的忘忧"

    def test_path_mismatch(self):
        eng = _make("23032", path="destruction", actions=(_ULT,))
        assert _panel(eng)["hp"] == pytest.approx(self.W["hp"])
        assert _panel(eng)["break_effect"] == pytest.approx(0.0)
        _ult(eng)
        assert "LC_23032_WOEFREE" not in eng.state.actors["e1"].modifiers


# ---------------------------------------------------------------------------
# 21021 等价交换：回合开始随机充能（能量百分比 <50% 的我方其他目标）
# ---------------------------------------------------------------------------
class TestLC21021:
    W = {"hp": 3952.56, "atk": 1423.36, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("21021"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_turn_start_energy_to_low_ally(self):
        """S1：装备者回合开始 → 能量 0/100（<50%）的队友 +8；expected 模式确定化取首."""
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E])
        eng = _make("21021", extra=(ally,))
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert _energy(eng, "a") == pytest.approx(8.0)
        assert _energy(eng, "w") == pytest.approx(0.0), "装备者自身不在候选（我方其他目标）"

    def test_above_threshold_no_gain(self):
        """队友能量 60%（≥#1=50%）→ 不充."""
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E])
        eng = _make("21021", extra=(ally,))
        eng.state.actors["a"].current_energy = 60.0
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert _energy(eng, "a") == pytest.approx(60.0)

    def test_s5_energy_diff(self):
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E])
        eng = _make("21021", sup=5, extra=(ally,))
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert _energy(eng, "a") == pytest.approx(16.0)

    def test_path_mismatch_no_effect(self):
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E])
        eng = _make("21021", path="destruction", extra=(ally,))
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert _energy(eng, "a") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 22001 嘿，我在这儿：生命常驻 + 战技后治疗量
# ---------------------------------------------------------------------------
class TestLC22001:
    W = {"hp": (3000 + 952.56) * 1.08, "atk": 1423.36, "def": 396.9}

    def test_base_stats(self):
        p = _panel(_make("22001"))
        assert p["hp"] == pytest.approx(self.W["hp"]), "生命上限 +8%（S1 白值口径）"
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])

    def test_heal_bonus_after_skill(self):
        """S1：施放战技 → 治疗量 +16% 两回合（#3 恒 2）；未放战技无."""
        eng = _make("22001", actions=(_BASIC, _SKILL_ZERO_E))
        assert _heal100(eng) == pytest.approx(100.0)
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.16)
        assert _heal100(eng) == pytest.approx(116.0)
        assert eng.state.actors["w"].modifiers["LC_22001_HEAL_BONUS"].duration == 2

    def test_path_mismatch_no_effect(self):
        eng = _make("22001", path="destruction", actions=(_BASIC, _SKILL_ZERO_E))
        assert _panel(eng)["hp"] == pytest.approx(3000 + 952.56)
        _cast(eng, "w", "t_skill")
        assert _panel(eng)["heal_bonus"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 23017 惊魂夜：能量恢复效率 + 终结技联动治疗 + 治疗加攻
# ---------------------------------------------------------------------------
class TestLC23017:
    W = {"hp": 4164.24, "atk": 1476.28, "def": 529.2}

    def test_base_stats(self):
        p = _panel(_make("23017"))
        assert p["hp"] == pytest.approx(self.W["hp"])
        assert p["atk"] == pytest.approx(self.W["atk"])
        assert p["def_"] == pytest.approx(self.W["def"])
        assert p["energy_regen"] == pytest.approx(1.12), "能量恢复效率 1.0+12%（S1）"

    def test_ally_ult_heals_lowest_and_grants_atk(self):
        """S1：队友终结技 → 装备者为生命百分比最低者（装备者 1000/4164.24）回复
        10% 生命上限 = 416.424；受疗目标（装备者）攻击叠 1 层 +2.4%."""
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E, _ULT])
        eng = _make("23017", extra=(ally,))
        w = eng.state.actors["w"]
        w.current_hp = 1000.0
        _ult(eng, "a", "t_ult")
        assert _hp(eng, "w") == pytest.approx(1000.0 + 4164.24 * 0.1)
        mod = w.modifiers["LC_23017_ATK"]
        assert mod.stacks == 1
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * (1 + 0.024))

    def test_heal_targets_actual_lowest(self):
        """队友残血时治疗落队友（order_by 生命百分比——非固定装备者）."""
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E, _ULT])
        eng = _make("23017", extra=(ally,))
        a = eng.state.actors["a"]
        a.current_hp = 500.0
        _ult(eng, "a", "t_ult")
        assert _hp(eng, "a") == pytest.approx(500.0 + 3000.0 * 0.1)
        assert a.modifiers["LC_23017_ATK"].stacks == 1, "受疗目标=叠层目标"

    def test_s5_values(self):
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E, _ULT])
        eng = _make("23017", sup=5, extra=(ally,))
        assert _panel(eng)["energy_regen"] == pytest.approx(1.2)
        w = eng.state.actors["w"]
        w.current_hp = 1000.0
        _ult(eng, "a", "t_ult")
        assert _hp(eng, "w") == pytest.approx(1000.0 + 4164.24 * 0.14)
        assert _panel(eng)["atk"] == pytest.approx((1000 + 476.28) * (1 + 0.04))

    def test_path_mismatch_no_effect(self):
        ally = _member("a", lc=None, actions=[_BASIC_ZERO_E, _ULT])
        eng = _make("23017", path="destruction", extra=(ally,))
        w = eng.state.actors["w"]
        w.current_hp = 1000.0
        _ult(eng, "a", "t_ult")
        assert _hp(eng, "w") == pytest.approx(1000.0)
        assert _panel(eng)["energy_regen"] == pytest.approx(1.0)
