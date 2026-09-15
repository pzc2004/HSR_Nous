"""位面饰品遗器族（314-328）e2e：staging→fixtures 验收批.

15 套验收 fixture（tests/fixtures/templates/relics/）→ 编译 → 2pc 面板与行为断言
（手算对轴）；勘正条目见各 fixture 头注。本族全是位面饰品——**只有 2pc、无 4pc**
（官方 desc 单条 + properties 单组，4pc 槽恒空）：「2 件/4 件分例」= 2 件触发 2pc、
4 件无增量（面板/行为与 2 件全等）。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / max_energy 100 / crit 0.05/0.5；
景元 1204 atk 698.544 / spd 99 / hp 1164.24 / crit 0.05/0.5（行迹平铺空表——面板=白值）、
神君 1204_lord hp 1164.24 / spd 60 / crit 0.05/0.5（开战自动在场，忆灵承载——
amphoreus 族同通道）。假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、未击破 0.9、
期望暴击区 1+cr×cd。面板直读 eng.pipeline.effective_stats（条件光环面板读取即重估）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

JY_ATK = 698.544
JY_SPD = 99.0
JY_HP = 1164.24


def _basic(aid="t_basic"):
    return {"action_id": aid, "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _fua(aid):
    return {"action_id": aid, "name": "追加攻击", "action_type": "follow_up",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _inline_member(aid, set_id=None, pieces=0, spd=100, hp=3000, atk=1000,
                   max_energy=100, path=None, groups=None, elation=0.0, actions=None):
    base = {"atk": atk, "spd": spd, "hp": hp, "max_energy": max_energy}
    if elation:
        base["elation"] = elation
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": base,
         "actions": actions if actions is not None else [_basic(f"{aid}_basic")]}
    if set_id is not None:
        m["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    if path:
        m["path"] = path
    if groups:
        m["groups"] = groups
    return m


def _build(members):
    return {"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _jy(set_id, pieces, *, allies=()):
    """景元（神君开战在场=忆灵承载）+ 可选 inline 队友."""
    members = [{"character_template": "1204", "level": 80,
                "relics": {f"slot{i}": {"set_id": set_id} for i in range(pieces)}}]
    members += list(allies)
    return _build(members)


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build, stage=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


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


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


# ---------------------------------------------------------------------------
# 314 出云显世与高天神国
# ---------------------------------------------------------------------------
class TestSet314:
    def test_2pc_same_path_teammate(self):
        """2 件（同命途队友在队）：atk 1000×1.12=1120；暴击率 0.05+0.12=0.17
        （count_team(path_of($self)) ≥ 2——装备者+另一名同命途）."""
        eng = _make(_build([_inline_member("w", "314", 2, path="destruction"),
                            _inline_member("a", path="destruction")]))
        assert math.isclose(_eff(eng, "w")["atk"], 1120.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9), "同命途队友 ≥1"
        assert "SET_314_CRITRATE" in _mods(eng, "w")

    def test_2pc_no_same_path(self):
        """2 件（队友命途不同 / 单飞）：暴击率不变 0.05——条件件不挂."""
        eng = _make(_build([_inline_member("w", "314", 2, path="destruction"),
                            _inline_member("a", path="harmony")]))
        assert math.isclose(_eff(eng, "w")["atk"], 1120.0, rel_tol=1e-9), "atk 件无条件"
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)
        assert "SET_314_CRITRATE" not in _mods(eng, "w")
        eng2 = _make(_build([_inline_member("w", "314", 2, path="destruction")]))
        assert math.isclose(_eff(eng2, "w")["crit_rate"], 0.05, rel_tol=1e-9), "单飞不计自身"

    def test_4pc_no_increment(self):
        """4 件：位面饰品无 4pc——面板与 2 件全等."""
        eng = _make(_build([_inline_member("w", "314", 4, path="destruction"),
                            _inline_member("a", path="destruction")]))
        assert math.isclose(_eff(eng, "w")["atk"], 1120.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 315 奔狼的都蓝王朝
# ---------------------------------------------------------------------------
def _315_build(pieces):
    wearer = _inline_member("w", "315", pieces, actions=[_basic("w_basic"), _fua("w_fua")])
    ally = _inline_member("a", actions=[_basic("a_basic"), _fua("a_fua")])
    return _build([wearer, ally])


class TestSet315:
    def test_2pc_merit_stacking(self):
        """2 件：我方角色（含队友）追击逐次叠【功勋】1..5 层——每层追击增伤 5%
        （dmg_bonus.follow_up_dmg_boost 0.05×层数），5 层额外暴伤 +25%（0.75）."""
        eng = _make(_315_build(2))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "无追击无件"
        _cast(eng, "a", "a_fua")
        assert math.isclose(_mods(eng, "w")["SET_315_MERIT"].stacks, 1.0), "队友追击也叠"
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["follow_up_dmg_boost"], 0.05, rel_tol=1e-9)
        _cast(eng, "w", "w_fua")
        _cast(eng, "a", "a_fua")
        assert math.isclose(_mods(eng, "w")["SET_315_MERIT"].stacks, 3.0)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["follow_up_dmg_boost"], 0.15, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "未满 5 层无暴伤"
        _cast(eng, "a", "a_fua")
        _cast(eng, "a", "a_fua")
        assert math.isclose(_mods(eng, "w")["SET_315_MERIT"].stacks, 5.0)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["follow_up_dmg_boost"], 0.25, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.75, rel_tol=1e-9), "叠满 +25%"
        _cast(eng, "a", "a_fua")
        assert math.isclose(_mods(eng, "w")["SET_315_MERIT"].stacks, 5.0), "5 层封顶"

    def test_2pc_merit_damage_axis(self):
        """2 件满层追击伤害手算：1000×1.0×1.25（类型桶）×0.5（防）×1.0（抗）×0.9（未破）
        ×1.0375（期望暴击 1+0.05×0.75）= 583.59375."""
        eng = _make(_315_build(2))
        for _ in range(5):
            _cast(eng, "a", "a_fua")
        fua = next(a for a in eng.actions_by_actor["w"] if a.action_id == "w_fua")
        dmg = eng.pipeline.deal_damage(fua, eng.state.actors["w"], eng.state.actors["e1"])
        assert math.isclose(dmg.value, 1000 * 1.25 * 0.5 * 1.0375 * 0.9, rel_tol=1e-9)

    def test_2pc_monster_action_not_counted(self):
        """2 件：敌方行动不叠（$event.actor_type != 'monster' 过滤）."""
        eng = _make(_315_build(2))
        eng.bus.emit("on_action", {
            "actor": "e1", "action_type": "follow_up", "action_id": "e_fua",
            "target_type": "single", "target": "w", "actor_type": "monster"}, eng.state)
        assert "SET_315_MERIT" not in _mods(eng, "w")

    def test_4pc_no_increment(self):
        """4 件：无 4pc——2 次追击后层数/面板与 2 件全等."""
        eng = _make(_315_build(4))
        _cast(eng, "a", "a_fua")
        _cast(eng, "w", "w_fua")
        assert math.isclose(_mods(eng, "w")["SET_315_MERIT"].stacks, 2.0)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["follow_up_dmg_boost"], 0.10, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 316 劫火莲灯铸炼宫
# ---------------------------------------------------------------------------
class TestSet316:
    def test_2pc_spd_only(self):
        """2 件：spd 100×1.06=106；火弱点命中件待收（has_weakness 族未接线）——
        施放攻击不挂任何击破件、击破特攻不变."""
        eng = _make(_build([_inline_member("w", "316", 2)]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        _cast(eng, "w", "w_basic")
        assert "SET_316_2PC_BREAK_EFFECT" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.0, rel_tol=1e-9)

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "316", 4)]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 317 沉陆海域露莎卡
# ---------------------------------------------------------------------------
class TestSet317:
    def test_2pc_buffs_slot1_ally(self):
        """2 件（装备者排第 2 位）：编队首位队友 atk 800×1.12=896；装备者自身
        energy_regen 1.0+0.05=1.05（ERR 面板基值 1）、atk 不变."""
        eng = _make(_build([_inline_member("a", atk=800),
                            _inline_member("w", "317", 2)]))
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.05, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["atk"], 800 * 1.12, rel_tol=1e-9), "slot 1 加攻"
        assert math.isclose(_eff(eng, "w")["atk"], 1000.0, rel_tol=1e-9), "装备者不自加"
        assert "SET_317_ATK_SLOT1" in _mods(eng, "a")

    def test_2pc_wearer_is_slot1_no_buff(self):
        """2 件（装备者排第 1 位）：条件不成立——任何人都不加攻."""
        eng = _make(_build([_inline_member("w", "317", 2),
                            _inline_member("a", atk=800)]))
        assert math.isclose(_eff(eng, "a")["atk"], 800.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["atk"], 1000.0, rel_tol=1e-9)
        assert "SET_317_ATK_SLOT1" not in _mods(eng, "w")
        assert "SET_317_ATK_SLOT1" not in _mods(eng, "a")

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("a", atk=800),
                            _inline_member("w", "317", 4)]))
        assert math.isclose(_eff(eng, "a")["atk"], 800 * 1.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["energy_regen"], 1.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 318 奇想蕉乐园（景元+神君承载召唤物）
# ---------------------------------------------------------------------------
class TestSet318:
    def test_2pc_summon_toggle(self):
        """2 件：常驻暴伤 +16%（0.66）；神君在场再 +32%（0.98）；神君离场回落 0.66
        （enable_if 面板读取即重估——「存在装备者召唤的目标」动态跟随）."""
        eng = _make(_jy("318", 2))
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.5 + 0.16 + 0.32, rel_tol=1e-9), (
            "召唤物在场全额")
        eng.dismiss_summon_actor("1204_lord")
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.66, rel_tol=1e-9), "离场即失效"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_jy("318", 4))
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.98, rel_tol=1e-9)
        eng.dismiss_summon_actor("1204_lord")
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.66, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 319 谧宁拾骨地（阈值件：inline 定 HP；忆灵侧：景元+神君 + HP 推档）
# ---------------------------------------------------------------------------
class TestSet319:
    def test_2pc_hp_below_threshold(self):
        """2 件（hp 3000）：3000×1.12=3360 < 5000 → 无暴伤（0.5）."""
        eng = _make(_build([_inline_member("w", "319", 2)]))
        assert math.isclose(_eff(eng, "w")["hp"], 3000 * 1.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)

    def test_2pc_hp_meets_threshold(self):
        """2 件（hp 4500）：4500×1.12=5040 ≥ 5000 → 暴伤 +28%（0.78）——档位判定含本套 12%."""
        eng = _make(_build([_inline_member("w", "319", 2, hp=4500)]))
        assert math.isclose(_eff(eng, "w")["hp"], 4500 * 1.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.78, rel_tol=1e-9)

    def test_2pc_memosprite_mirrors(self):
        """2 件（景元+神君）：景元 1164.24×1.12=1303.9 <5000 → 双侧 0.5；
        景元挂 +4000 生命件 → 5303.9 ≥5000 → 装备者/忆灵各 0.78（忆灵侧读
        召唤者生命上限 max_hp_of($self.summoner_id)，actor_enter 镜像钩）."""
        eng = _make(_jy("319", 2))
        assert "SET_319_MEMO_CRITDMG" in _mods(eng, "1204_lord"), "忆灵侧已挂（未启用）"
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.5, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.5, rel_tol=1e-9)
        eng._apply_modifier(eng.state.actors["1204"], Modifier(
            modifier_id="TEST_HP_BUFF", name="测试生命", modifier_type="buff",
            duration=0, stat_effects={"hp": 4000.0}))
        assert math.isclose(_eff(eng, "1204")["hp"], JY_HP * 1.12 + 4000, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.78, rel_tol=1e-9), "装备者 +28%"
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.78, rel_tol=1e-9), "忆灵 +28%"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "319", 4, hp=4500)]))
        assert math.isclose(_eff(eng, "w")["hp"], 4500 * 1.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.78, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 320 渊思寂虑的巨树（速度档：inline 定 SPD；忆灵侧：景元+神君 + SPD 推档）
# ---------------------------------------------------------------------------
class TestSet320:
    def test_2pc_spd_below_tier(self):
        """2 件（spd 100）：100×1.06=106 < 135 → 治疗量不加（0）、spd 106."""
        eng = _make(_build([_inline_member("w", "320", 2)]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["heal_bonus"], 0.0, rel_tol=1e-9)

    def test_2pc_spd_tier1(self):
        """2 件（spd 130）：130×1.06=137.8 ∈ [135,180) → 治疗量 +12%（含 2pc 速度判定）."""
        eng = _make(_build([_inline_member("w", "320", 2, spd=130)]))
        assert math.isclose(_eff(eng, "w")["spd"], 130 * 1.06, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["heal_bonus"], 0.12, rel_tol=1e-9)

    def test_2pc_spd_tier2(self):
        """2 件（spd 170）：170×1.06=180.2 ≥ 180 → 治疗量 +20%（取高不叠加——非 0.32）."""
        eng = _make(_build([_inline_member("w", "320", 2, spd=170)]))
        assert math.isclose(_eff(eng, "w")["spd"], 170 * 1.06, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["heal_bonus"], 0.20, rel_tol=1e-9)

    def test_2pc_memosprite_mirrors(self):
        """2 件（景元+神君）：景元 99×1.06=104.94 <135 → 双侧 0；景元挂 +40 速度件 →
        144.94 ≥135 → 双侧 0.12；再推 +36 → 180.94 ≥180 → 双侧 0.20
        （忆灵侧 stat_of($self.summoner_id, 'spd') 读召唤者面板定档）."""
        eng = _make(_jy("320", 2))
        assert "SET_320_HEAL" in _mods(eng, "1204_lord"), "忆灵侧已挂（未启用）"
        assert math.isclose(_eff(eng, "1204")["heal_bonus"], 0.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["heal_bonus"], 0.0, rel_tol=1e-9)
        eng._apply_modifier(eng.state.actors["1204"], Modifier(
            modifier_id="TEST_SPD_BUFF", name="测试速度", modifier_type="buff",
            duration=0, stat_effects={"spd": 40.0}))
        assert math.isclose(_eff(eng, "1204")["heal_bonus"], 0.12, rel_tol=1e-9), "装备者一档"
        assert math.isclose(_eff(eng, "1204_lord")["heal_bonus"], 0.12, rel_tol=1e-9), "忆灵一档"
        eng._apply_modifier(eng.state.actors["1204"], Modifier(
            modifier_id="TEST_SPD_BUFF2", name="测试速度2", modifier_type="buff",
            duration=0, stat_effects={"spd": 36.0}))
        assert math.isclose(_eff(eng, "1204")["heal_bonus"], 0.20, rel_tol=1e-9), "装备者二档"
        assert math.isclose(_eff(eng, "1204_lord")["heal_bonus"], 0.20, rel_tol=1e-9), "忆灵二档"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "320", 4, spd=170)]))
        assert math.isclose(_eff(eng, "w")["heal_bonus"], 0.20, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 321 妖精织梦的乐园（在场人数差值映射；景元+神君凑在场目标数）
# ---------------------------------------------------------------------------
class TestSet321:
    def test_2pc_four_targets_no_bonus(self):
        """2 件（景元+神君+2 队友=4 在场目标）：N=4 → 增伤 0."""
        eng = _make(_jy("321", 2, allies=[_inline_member("a"), _inline_member("b")]))
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.0, rel_tol=1e-9)

    def test_2pc_more_targets_tier(self):
        """2 件（景元+神君+3 队友=5 在场目标）：多 1 名 → +9%（0.09）；装备者/忆灵同值."""
        eng = _make(_jy("321", 2, allies=[_inline_member("a"), _inline_member("b"),
                                          _inline_member("c")]))
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.09, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["dmg_bonus"]["all"], 0.09, rel_tol=1e-9), (
            "忆灵同档（actor_enter 镜像挂 + 召唤者持件门控）")

    def test_2pc_fewer_targets_tier(self):
        """2 件（景元+神君=2 在场目标）：少 2 名 → 2×12%=0.24；神君离场（N=1）
        → 3×12%=0.36（actor_exit 事件窗重算，stack_mode replace 换烘焙值）."""
        eng = _make(_jy("321", 2))
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        eng.dismiss_summon_actor("1204_lord")
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.36, rel_tol=1e-9), "少 3 名封顶"

    def test_2pc_solo_cap(self):
        """2 件（inline 单飞 N=1）：少 3 名封顶 3 层 → 0.36（双向上限 36% 互证）."""
        eng = _make(_build([_inline_member("w", "321", 2)]))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.36, rel_tol=1e-9)

    def test_4pc_no_increment(self):
        """4 件：无 4pc（staging 臆造 4pc 已删——9%/12% 是多/少分档非 2pc/4pc 并置）——与 2 件全等."""
        eng = _make(_jy("321", 4))
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 322 沉欢醉饮的海隅
# ---------------------------------------------------------------------------
class TestSet322:
    def test_2pc_atk_only(self):
        """2 件：atk 1000×1.12=1120；DoT 阈值档待收（增伤乘区无消费端 B27#3 在案）——
        高攻装备员亦不挂任何 DoT 件."""
        eng = _make(_build([_inline_member("w", "322", 2, atk=4000)]))
        assert math.isclose(_eff(eng, "w")["atk"], 4000 * 1.12, rel_tol=1e-9)
        assert "SET_322_2PC_DOT_DMG_T1" not in _mods(eng, "w")
        assert "SET_322_2PC_DOT_DMG_T2" not in _mods(eng, "w")

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "322", 4)]))
        assert math.isclose(_eff(eng, "w")["atk"], 1120.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 323 永恒之地翁法罗斯（景元+神君承载忆灵；光环 effect_scope=team）
# ---------------------------------------------------------------------------
class TestSet323:
    def test_2pc_team_spd_with_memosprite(self):
        """2 件：暴击率 0.13 常驻；神君在场 → 我方全体 spd +8%（景元 99×1.08=106.92、
        神君 60×1.08=64.8、队友 100×1.08=108——effect_scope=team 条件按装备者语境）."""
        eng = _make(_jy("323", 2, allies=[_inline_member("a")]))
        assert math.isclose(_eff(eng, "1204")["crit_rate"], 0.13, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD * 1.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["spd"], 60 * 1.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["spd"], 108.0, rel_tol=1e-9), "我方全体含队友"

    def test_2pc_spd_falls_off_without_memosprite(self):
        """2 件：神君离场 → 全队速度回落（忆灵在场=持续条件，非触发型）."""
        eng = _make(_jy("323", 2, allies=[_inline_member("a")]))
        eng.dismiss_summon_actor("1204_lord")
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["spd"], 100.0, rel_tol=1e-9)

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等（单件光环天然单份=「无法叠加」单装备者口径）."""
        eng = _make(_jy("323", 4, allies=[_inline_member("a")]))
        assert math.isclose(_eff(eng, "1204")["spd"], JY_SPD * 1.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["spd"], 108.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 324 天国@直播间（SP 消耗窗口计数）
# ---------------------------------------------------------------------------
def _324_build(pieces):
    wearer = _inline_member("w", "324", pieces, actions=[
        _basic("w_basic"),
        {"action_id": "w_s1", "name": "战技1", "action_type": "skill",
         "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 1.0}],
         "skill_point_cost": 1},
        {"action_id": "w_s2", "name": "战技2", "action_type": "skill",
         "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 1.0}],
         "skill_point_cost": 2},
        {"action_id": "w_s3", "name": "战技3", "action_type": "skill",
         "target_type": "single", "damage_type": "fire", "scaling": [{"atk": 1.0}],
         "skill_point_cost": 3}])
    return _build([wearer, _inline_member("a")])


def _turn_end(eng, actor="a"):
    eng.bus.emit("on_turn_end", {"actor": actor}, eng.state)


class TestSet324:
    def test_2pc_single_skill_3sp(self):
        """2 件：一次消耗 3 点（战技3）→ 按点计数 3 层达标 → 暴伤 0.5+0.16+0.32=0.98、
        持续 3 回合；计数件触发后即摘."""
        eng = _make(_324_build(2))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.66, rel_tol=1e-9), "触发前只 2pc"
        _cast(eng, "w", "w_s3")
        assert "SET_324_SP_TRACK" not in _mods(eng, "w"), "达标后计数件摘除"
        assert math.isclose(_mods(eng, "w")["SET_324_CRITDMG"].duration, 3.0), "持续 3 回合"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.98, rel_tol=1e-9)

    def test_2pc_accumulate_2plus1(self):
        """2 件：同窗 2 点+1 点累计达标（战技2→战技1）→ 0.98."""
        eng = _make(_324_build(2))
        _cast(eng, "w", "w_s2")
        assert "SET_324_CRITDMG" not in _mods(eng, "w"), "2 点未达标"
        _cast(eng, "w", "w_s1")
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.98, rel_tol=1e-9), "同窗累计 3 点"

    def test_2pc_cross_turn_window_reset(self):
        """2 件：消耗 1 点 → 任意回合结束计数清零 → 再耗 1 点仍不达标（0.66 不变）——
        「同一回合内」窗口按任意回合末重置."""
        eng = _make(_324_build(2))
        _cast(eng, "w", "w_s1")
        assert math.isclose(_mods(eng, "w")["SET_324_SP_TRACK"].stacks, 1.0)
        _turn_end(eng, "a")
        assert "SET_324_SP_TRACK" not in _mods(eng, "w"), "回合窗关闭清零"
        _cast(eng, "w", "w_s1")
        assert "SET_324_CRITDMG" not in _mods(eng, "w"), "跨窗不累加"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.66, rel_tol=1e-9)

    def test_2pc_sp_gain_not_counted(self):
        """2 件：产点（普攻 +1）不计入消耗计数."""
        eng = _make(_324_build(2))
        _cast(eng, "w", "w_basic")
        assert "SET_324_SP_TRACK" not in _mods(eng, "w")

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_324_build(4))
        _cast(eng, "w", "w_s3")
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.98, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 325 零号关卡朋克洛德（欢愉度阈值分档）
# ---------------------------------------------------------------------------
class TestSet325:
    def test_2pc_base_elation_only(self):
        """2 件（欢愉度 0 起）：面板欢愉度 0+0.08=0.08 < 0.4 → 暴伤不加（0.5）——
        ElationDamageAddedRatioBase 映射 elation 面板（21_elation §21.1 终审，非 dmg_elation）."""
        eng = _make(_build([_inline_member("w", "325", 2)]))
        assert math.isclose(_eff(eng, "w")["elation"], 0.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)

    def test_2pc_tier1(self):
        """2 件（基础欢愉度 0.32）：0.32+0.08=0.40 ≥ 0.4 → 暴伤 +20%（0.7）——档位判定含 2pc."""
        eng = _make(_build([_inline_member("w", "325", 2, elation=0.32)]))
        assert math.isclose(_eff(eng, "w")["elation"], 0.40, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.70, rel_tol=1e-9)

    def test_2pc_tier2(self):
        """2 件（基础欢愉度 0.75）：0.75+0.08=0.83 ≥ 0.8 → 暴伤 +32%（0.82，取高不叠加）；
        阈值恰界（如 0.72+0.08）受浮点拼界影响不按恰界断言."""
        eng = _make(_build([_inline_member("w", "325", 2, elation=0.75)]))
        assert math.isclose(_eff(eng, "w")["elation"], 0.83, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.82, rel_tol=1e-9), "二档替换非 0.5+0.52"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "325", 4, elation=0.75)]))
        assert math.isclose(_eff(eng, "w")["elation"], 0.83, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.82, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 326 千星荟萃之城
# ---------------------------------------------------------------------------
_KILL_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "硬假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]},
    {"actor_id": "e2", "name": "纸假人", "hp": 100, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]},
    {"actor_id": "e3", "name": "纸假人2", "hp": 100, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _326_build(pieces):
    wearer = _inline_member("w", "326", pieces, actions=[_basic("w_basic"), _fua("w_fua")])
    ally = _inline_member("a", actions=[_basic("a_basic"), _fua("a_fua")])
    return _build([wearer, ally])


class TestSet326:
    def test_2pc_follow_up_atk_buff(self):
        """2 件：装备者施放追击 → atk +24%（1240）持续 2 回合；再放刷新不叠层；
        队友追击不触发（EN「the wearer uses Follow-Up ATK」——staging 漏收效果 A 已补）."""
        eng = _make(_326_build(2))
        _cast(eng, "a", "a_fua")
        assert "SET_326_2PC_ATK" not in _mods(eng, "w"), "队友追击不发"
        _cast(eng, "w", "w_fua")
        assert math.isclose(_mods(eng, "w")["SET_326_2PC_ATK"].duration, 2.0)
        assert math.isclose(_eff(eng, "w")["atk"], 1240.0, rel_tol=1e-9)
        _cast(eng, "w", "w_fua")
        assert math.isclose(_eff(eng, "w")["atk"], 1240.0, rel_tol=1e-9), "刷新不叠层"

    def test_2pc_kill_team_critdmg(self):
        """2 件：敌方被消灭 → 我方全体暴伤 +12%（0.62）战中常驻；再杀不叠加
        （「该效果无法叠加」——has_modifier 单判闸）."""
        eng = _make(_326_build(2), stage=_KILL_STAGE)
        _cast(eng, "w", "w_basic", target_id="e2")
        assert not eng.state.actors["e2"].alive, "纸假人被击杀"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.62, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["crit_dmg"], 0.62, rel_tol=1e-9), "我方全体"
        _cast(eng, "a", "a_basic", target_id="e3")
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.62, rel_tol=1e-9), "二次击杀不叠加"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_326_build(4))
        _cast(eng, "w", "w_fua")
        assert math.isclose(_eff(eng, "w")["atk"], 1240.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 327 坠星启航地（开拓同行分组）
# ---------------------------------------------------------------------------
class TestSet327:
    def test_2pc_both_companions(self):
        """2 件（装备者+另一队友均挂 trailblaze_companions 分组）：暴击率 0.13、
        暴伤 0.5+0.32=0.82."""
        eng = _make(_build([_inline_member("w", "327", 2, groups=["trailblaze_companions"]),
                            _inline_member("a", groups=["trailblaze_companions"])]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.13, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.82, rel_tol=1e-9)

    def test_2pc_only_wearer_companion(self):
        """2 件（仅装备者挂分组）：count_team(group) = 1 < 2 → 暴伤不加（0.5）."""
        eng = _make(_build([_inline_member("w", "327", 2, groups=["trailblaze_companions"]),
                            _inline_member("a")]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.13, rel_tol=1e-9), "暴击率无条件"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)
        assert "SET_327_TRAILBLAZE_CRIT_DMG" not in _mods(eng, "w")

    def test_2pc_wearer_not_companion(self):
        """2 件（装备者未挂分组、两名队友挂了）：in_group($self) 不成立 → 暴伤不加."""
        eng = _make(_build([_inline_member("w", "327", 2),
                            _inline_member("a", groups=["trailblaze_companions"]),
                            _inline_member("b", groups=["trailblaze_companions"])]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "装备者须同为同行"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "327", 4, groups=["trailblaze_companions"]),
                            _inline_member("a", groups=["trailblaze_companions"])]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.82, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 328 寰宇生研院（能量上限溢出映射）
# ---------------------------------------------------------------------------
class TestSet328:
    def test_2pc_below_threshold(self):
        """2 件（max_energy 100 < 200）：不挂增伤件（dmg_bonus.all 0）."""
        eng = _make(_build([_inline_member("w", "328", 2)]))
        assert "SET_328_2PC_DMG" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("all", 0.0), 0.0, rel_tol=1e-9)

    def test_2pc_linear_and_cap(self):
        """2 件：max_energy 260 → (260-200)×0.2%=0.12；400 → 钳 0.32（溢出 160 点封顶）."""
        eng = _make(_build([_inline_member("w", "328", 2, max_energy=260)]))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.12, rel_tol=1e-9)
        eng2 = _make(_build([_inline_member("w", "328", 2, max_energy=400)]))
        assert math.isclose(_eff(eng2, "w")["dmg_bonus"]["all"], 0.32, rel_tol=1e-9), "硬上限"

    def test_4pc_no_increment(self):
        """4 件：无 4pc——与 2 件全等."""
        eng = _make(_build([_inline_member("w", "328", 4, max_energy=260)]))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.12, rel_tol=1e-9)
