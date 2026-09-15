"""记忆（Memory）光锥族 e2e：staging→fixtures 验收批.

十四件验收 fixture（tests/fixtures/templates/light_cones/）→ 编译 → 白值三围 + 机制行为
断言（手算对轴）+ 叠影 S1/S5 差分；勘正条目见各 fixture 头注。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / def 0 / crit 0.05/0.5；
开拓者•记忆 8008 hp 1047.816 / atk 543.312 / def 630.63 / spd 103 / max_energy 160
（行迹 atk_pct 0.14 / hp_pct 0.14 / crit_dmg 0.373）；景元 1204 hp 1164.24 / atk 698.544 /
spd 99 / crit 0.05/0.5、神君 1204_lord 开战召唤在场（crit 0.05/0.5）。
假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、未击破 0.9。
忆灵承载：8008+迷迷（技能 800802 召唤；1800701 攻敌 / 1800707 支援我方）与
1204+神君（开战在场）双载体按件选用。命途门槛：本族 14 件官方文本均无「装备者命途为
记忆时」条件（ranks.json desc 终审）——不设 path_of 门，留档测试钉死该决策。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

#: 光锥白值三围（生成器数值区照抄——验收只读不手改；loader 白值病修复后官方正确值）
LC_BASE = {
    "20021": (846.72, 317.52, 264.6),
    "21050": (846.72, 476.28, 396.9),
    "21051": (952.56, 476.28, 330.75),
    "21054": (1058.4, 370.44000000000005, 396.9),
    "21057": (1058.4, 529.2, 330.75),
    "23040": (1270.08, 529.2, 396.9),
    "24005": (1058.4, 529.2, 396.9),
    "20022": (635.04, 423.36, 264.6),
    "21052": (1058.4, 529.2, 198.45),
    "22006": (846.72, 476.28, 396.9),
    "23036": (1058.4, 635.04, 396.9),
    "23042": (1164.24, 476.28, 529.2),
    "23049": (1164.24, 529.2, 463.05),
    "23052": (1270.08, 476.28, 463.05),
}


def _basic(aid="t_basic"):
    return {"action_id": aid, "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1,
            "energy_gain": 20}


def _inline(lc_id, *, sup=1, path=None, aid="w", actions=None, max_energy=100):
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": max_energy},
         "actions": actions if actions is not None else [_basic(f"{aid}_basic")]}
    if lc_id:
        m["light_cone_template"] = lc_id
        m["light_cone"] = {"superimposition": sup}
    if path:
        m["path"] = path
    return m


def _build(members):
    return {"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _tb(lc_id, *, sup=1, eidolon=0):
    """开拓者•记忆 8008（忆灵=迷迷，800802 召唤）+ 光锥."""
    m = {"character_template": "8008", "level": 80,
         "light_cone_template": lc_id, "light_cone": {"superimposition": sup}}
    if eidolon:
        m["eidolon"] = eidolon
    return _build([m])


def _jy(lc_id, *, sup=1):
    """景元 1204（神君开战在场）+ 光锥."""
    return _build([{"character_template": "1204", "level": 80,
                    "light_cone_template": lc_id, "light_cone": {"superimposition": sup}}])


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build, *, sp=3):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=sp)
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


def _ult(eng, owner, aid, energy, target_id="e1"):
    st = eng.state.actors[owner]
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = float(energy)
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    assert eng._fire_ultimate(st, a) is True


def _hp_dec(eng, target, *, amount=100.0, reason="drain", source=None):
    """掉血事件（blade 模子）：直改 HP + on_hp_decrease 发射（hook 触发域）."""
    st = eng.state.actors[target]
    st.current_hp = max(1.0, st.current_hp - amount)
    eng.bus.emit("on_hp_decrease", {
        "amount": amount, "reason": reason, "target": target,
        "source": source or target}, eng.state)


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _white(lc_id, *, hp_mult=1.0, atk_mult=1.0):
    """白值三围断言（inline 装备员 3000/1000/0 + 光锥白值；mult=该锥 S1 常驻 pct 件口径——
    白值百分比乘区与面板白值同基，21051 atk/21054 hp/23040 hp 三件套）."""
    hp, atk, dfn = LC_BASE[lc_id]
    eng = _make(_build([_inline(lc_id)]))
    eff = _eff(eng, "w")
    assert math.isclose(eff["hp"], (3000 + hp) * hp_mult, rel_tol=1e-9), f"{lc_id} hp 白值"
    assert math.isclose(eff["atk"], (1000 + atk) * atk_mult, rel_tol=1e-9), f"{lc_id} atk 白值"
    assert math.isclose(eff["def_"], dfn, rel_tol=1e-9), f"{lc_id} def 白值"


# ---------------------------------------------------------------------------
# 20021 焚影（3★）：首次召唤忆灵 → +1 战技点 +#2 能量
# ---------------------------------------------------------------------------
class TestLC20021:
    def test_white_stats(self):
        _white("20021")

    def test_first_summon_grants_sp_and_energy(self):
        """S1：800802 召唤迷迷（耗 1 点/回 30 能）→ 焚影 +1 点/+12 能（净 SP 不变、
        能量 +42）；锁挂上."""
        eng = _make(_tb("20021"))
        st = eng.state.actors["8008"]
        sp0, en0 = eng.state.skill_points, st.current_energy
        _cast(eng, "8008", "800802")
        assert math.isclose(eng.state.skill_points, sp0), "耗 1 + 焚影 1 = 净 0"
        assert math.isclose(st.current_energy, en0 + 42.0), "战技 30 + 焚影 12（S1）"
        assert "LC_20021_FIRST_SUMMON_LOCK" in _mods(eng, "8008"), "首次召唤锁"

    def test_second_summon_no_retrigger(self):
        """解散重召：锁阻断二发——SP 净耗 1（无焚影回点）、能量只 +30（无焚影回能）."""
        eng = _make(_tb("20021"))
        st = eng.state.actors["8008"]
        _cast(eng, "8008", "800802")
        eng.dismiss_summon_actor("8008_mem")
        sp0, en0 = eng.state.skill_points, st.current_energy
        _cast(eng, "8008", "800802")
        assert math.isclose(eng.state.skill_points, sp0 - 1), "锁在：焚影不再回点"
        assert math.isclose(st.current_energy, en0 + 30.0), "锁在：焚影不再回能"

    def test_s5_energy_diff(self):
        """S5（#2=20）：召唤后能量 +30+20=50."""
        eng = _make(_tb("20021", sup=5))
        st = eng.state.actors["8008"]
        en0 = st.current_energy
        _cast(eng, "8008", "800802")
        assert math.isclose(st.current_energy, en0 + 50.0), "S5 焚影 +20 能"


# ---------------------------------------------------------------------------
# 21050 胜利只在朝夕间（4★）：暴伤常驻 + 忆灵对我方施技 → 全队增伤
# ---------------------------------------------------------------------------
class TestLC21050:
    def test_white_stats(self):
        _white("21050")

    def test_crit_dmg_base(self):
        """S1：装备者暴伤 0.5+行迹 0.373+0.12=0.993（迷迷未召唤=无 1800703 光环干扰）."""
        eng = _make(_tb("21050"))
        assert math.isclose(_eff(eng, "8008")["crit_dmg"], 0.5 + 0.373 + 0.12, rel_tol=1e-9)

    def test_memosprite_ally_skill_team_dmg(self):
        """S1：迷迷声援（1800707 对我方）→ 我方全体增伤 +8%（装备者/迷迷/队友同吃）×3 回合."""
        eng = _make(_tb("21050"))
        _cast(eng, "8008", "800802")                      # 召唤迷迷
        _cast(eng, "8008_mem", "1800707", target_id="8008")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9), (
            "我方全体含忆灵")
        assert math.isclose(_mods(eng, "8008")["LC_21050_TEAM_DMG"].duration, 3.0)

    def test_memosprite_attack_no_trigger(self):
        """迷迷攻敌（1800701 主目标敌方）≠ 对我方施技——不触发."""
        eng = _make(_tb("21050"))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800701")
        assert "LC_21050_TEAM_DMG" not in _mods(eng, "8008")

    def test_s5_team_dmg_diff(self):
        """S5（#2=0.16）：全队增伤 +16%."""
        eng = _make(_tb("21050", sup=5))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800707", target_id="8008")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.16, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21051 天才们的问候（4★）：攻击常驻 + 终结技后普攻增伤（装备者与忆灵）
# ---------------------------------------------------------------------------
class TestLC21051:
    def test_white_stats(self):
        _white("21051", atk_mult=1.16)

    def test_atk_pct_base_and_ult_basic_boost(self):
        """S1：atk=(1000+476.28)×1.16=1712.4848；终结技 → 普攻增伤 +20%（hit_condition
        仅普攻）：普攻=1712.4848×0.46125×1.2；战技不吃（×1.0）."""
        actions = [_basic("w_basic"),
                   {"action_id": "w_skill", "name": "战技", "action_type": "skill",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
                    "skill_point_cost": 1, "energy_gain": 30},
                   {"action_id": "w_ult", "name": "终结技", "action_type": "ultimate",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "energy_cost": 100, "toughness_dmg": 30}]
        eng = _make(_build([_inline("21051", actions=actions)]))
        atk = (1000 + 476.28) * 1.16
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(_eff(eng, "w")["atk"], atk, rel_tol=1e-9), "攻击常驻 #1"
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "终结技前无增伤"
        _ult(eng, "w", "w_ult", 100)
        assert "LC_21051_BASIC_DMG" in _mods(eng, "w")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.2, rel_tol=1e-9), "普攻吃 +20%"
        hp1 = e1.current_hp
        _cast(eng, "w", "w_skill")
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "战技不吃（仅普攻）"

    def test_memosprite_dual_apply(self):
        """景元终结技 → 装备者/神君双挂（代数 $it.summoner_id == $event.source 寻址）."""
        eng = _make(_jy("21051"))
        _ult(eng, "1204", "120403", 130)
        assert "LC_21051_BASIC_DMG" in _mods(eng, "1204"), "装备者挂"
        assert "LC_21051_BASIC_DMG" in _mods(eng, "1204_lord"), "忆灵双挂"

    def test_other_actor_ult_no_trigger(self):
        """非装备者终结技不触发（装备者判定 $event.source == $self.actor_id）."""
        ally = _inline(None, aid="a", actions=[
            _basic("a_basic"),
            {"action_id": "a_ult", "name": "终结技", "action_type": "ultimate",
             "target_type": "single", "damage_type": "fire",
             "scaling": [{"atk": 1.0}], "energy_cost": 100, "toughness_dmg": 30}])
        eng = _make(_build([_inline("21051"), ally]))
        _ult(eng, "a", "a_ult", 100)
        assert "LC_21051_BASIC_DMG" not in _mods(eng, "w")

    def test_s5_basic_boost_diff(self):
        """S5（#2=0.4）：终结技后普攻 ×1.4."""
        actions = [_basic("w_basic"),
                   {"action_id": "w_ult", "name": "终结技", "action_type": "ultimate",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "energy_cost": 100, "toughness_dmg": 30}]
        eng = _make(_build([_inline("21051", sup=5, actions=actions)]))
        atk = (1000 + 476.28) * (1 + 0.32)
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        e1 = eng.state.actors["e1"]
        _ult(eng, "w", "w_ult", 100)
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.4, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21054 故事的下一页（4★）：生命常驻 + 忆灵攻击后治疗量（装备者与忆灵）
# ---------------------------------------------------------------------------
class TestLC21054:
    def test_white_stats(self):
        _white("21054", hp_mult=1.16)

    def test_hp_pct_base(self):
        """S1：hp=(1047.816+1058.4)×(1+0.14 行迹+0.16)=2106.216×1.3=2738.0808."""
        eng = _make(_tb("21054"))
        assert math.isclose(_eff(eng, "8008")["hp"],
                            (1047.816 + 1058.4) * 1.3, rel_tol=1e-9)

    def test_memosprite_attack_heal_bonus(self):
        """S1：迷迷攻敌（1800701）→ 装备者/忆灵治疗量各 +12%×1 回合."""
        eng = _make(_tb("21054"))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800701")
        assert math.isclose(_eff(eng, "8008")["heal_bonus"], 0.12, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["heal_bonus"], 0.12, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "8008")["LC_21054_HEAL"].duration, 1.0)

    def test_no_trigger_cases(self):
        """装备者普攻（非忆灵）/ 迷迷声援（对我方非攻击）均不触发."""
        eng = _make(_tb("21054"))
        _cast(eng, "8008", "800801")
        assert "LC_21054_HEAL" not in _mods(eng, "8008"), "装备者行动非忆灵攻击"
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800707", target_id="8008")
        assert "LC_21054_HEAL" not in _mods(eng, "8008"), "忆灵支援技非攻击"

    def test_s5_heal_diff(self):
        """S5（#2=0.24）：治疗量 +24%."""
        eng = _make(_tb("21054", sup=5))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800701")
        assert math.isclose(_eff(eng, "8008")["heal_bonus"], 0.24, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21057 花儿不会忘记（4★）：装备者暴伤常驻 + 忆灵暴伤常驻
# ---------------------------------------------------------------------------
class TestLC21057:
    def test_white_stats(self):
        _white("21057")

    def test_dual_crit_dmg(self):
        """S1（景元+神君开战在场）：装备者暴伤 0.5+0.24=0.74；神君暴伤 0.5+0.24=0.74
        （actor_enter 开战召唤钩挂忆灵本体）."""
        eng = _make(_jy("21057"))
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.74, rel_tol=1e-9), "装备者 #1"
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.74, rel_tol=1e-9), "忆灵 #2"

    def test_resummon_idempotent(self):
        """解散重召仍 0.74（max_stack 1 幂等重挂；重召=引擎 summon_actor 再入场）."""
        eng = _make(_jy("21057"))
        eng.dismiss_summon_actor("1204_lord")
        eng.summon_actor(eng.state.actors["1204"], "1204_lord")
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.74, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "1204_lord")["LC_21057_MEMO_CRIT_DMG"].stacks, 1.0)

    def test_s5_dual_diff(self):
        """S5（#1=0.4 / #2=0.48）：装备者 0.9、忆灵 0.98."""
        eng = _make(_jy("21057", sup=5))
        assert math.isclose(_eff(eng, "1204")["crit_dmg"], 0.9, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "1204_lord")["crit_dmg"], 0.98, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23040 让告别，更美一些（5★）：生命常驻 + 冥花无视防御 + 忆灵消失拉条
# ---------------------------------------------------------------------------
class TestLC23040:
    def test_white_stats(self):
        _white("23040", hp_mult=1.30)

    def test_hp_pct_base(self):
        """S1：hp=(1047.816+1270.08)×(1+0.14 行迹+0.30)=2317.896×1.44=3337.77024."""
        eng = _make(_tb("23040"))
        assert math.isclose(_eff(eng, "8008")["hp"],
                            (1047.816 + 1270.08) * 1.44, rel_tol=1e-9)

    def test_flower_on_wearer_hp_loss_dual(self):
        """S1：装备者掉血 → 冥花（无视防御 30%）装备者/迷迷双挂×2 回合；敌方掉血不触发."""
        eng = _make(_tb("23040"))
        _cast(eng, "8008", "800802")                      # 迷迷在场
        _hp_dec(eng, "e1", source="8008")
        assert "LC_23040_DEATH_FLOWER" not in _mods(eng, "8008"), "敌方掉血不触发"
        _hp_dec(eng, "8008")
        assert math.isclose(_eff(eng, "8008")["def_pen"], 0.3, rel_tol=1e-9), "装备者冥花"
        assert math.isclose(_eff(eng, "8008_mem")["def_pen"], 0.3, rel_tol=1e-9), (
            "忆灵双挂（代数 $it.summoner_id == $event.target 寻址）")
        assert math.isclose(_mods(eng, "8008")["LC_23040_DEATH_FLOWER"].duration, 2.0)

    def test_flower_on_memosprite_hp_loss(self):
        """忆灵掉血 → 冥花装备者/忆灵同挂（$event.target 直挂）."""
        eng = _make(_tb("23040"))
        _cast(eng, "8008", "800802")
        _hp_dec(eng, "8008_mem")
        assert math.isclose(_eff(eng, "8008")["def_pen"], 0.3, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["def_pen"], 0.3, rel_tol=1e-9)

    def test_farewell_advance_once_and_ult_reset(self):
        """忆灵消失 → 行动提前 12%（8008 天赋自带迷迷消失提前 25% 叠加=3700）限 1 次；
        再消失闩阻断（余 25% 天赋段）；终结技重置后再发."""
        eng = _make(_tb("23040"))
        _cast(eng, "8008", "800802")
        r0 = _remaining(eng, "8008")
        eng.dismiss_summon_actor("8008_mem")
        assert math.isclose(r0 - _remaining(eng, "8008"), 3700.0, rel_tol=1e-9), (
            "天赋 25%（800804，-2500）+ 光锥 12%（-1200）")
        assert "LC_23040_FAREWELL_USED" in _mods(eng, "8008"), "触发闩"
        _cast(eng, "8008", "800802")
        r1 = _remaining(eng, "8008")
        eng.dismiss_summon_actor("8008_mem")
        assert math.isclose(r1 - _remaining(eng, "8008"), 2500.0, rel_tol=1e-9), (
            "闩在：光锥不再提前（仅天赋 25% 段）")
        _ult(eng, "8008", "800803", 160)                # 终结技重置（本发顺带重召迷迷）
        assert "LC_23040_FAREWELL_USED" not in _mods(eng, "8008"), "终结技摘闩"
        eng.scheduler._remaining[eng.scheduler._handles["8008"]] = 10000.0   # 补足距离防触底钳零
        r2 = _remaining(eng, "8008")
        eng.dismiss_summon_actor("8008_mem")
        assert math.isclose(r2 - _remaining(eng, "8008"), 3700.0, rel_tol=1e-9), "重置后再发"

    def test_s5_flower_and_advance_diff(self):
        """S5（#2=0.5 / #4=0.24）：冥花无视防御 50%；消失提前 25%+24%（-4900）."""
        eng = _make(_tb("23040", sup=5))
        _hp_dec(eng, "8008")
        assert math.isclose(_eff(eng, "8008")["def_pen"], 0.5, rel_tol=1e-9)
        _cast(eng, "8008", "800802")
        r0 = _remaining(eng, "8008")
        eng.dismiss_summon_actor("8008_mem")
        assert math.isclose(r0 - _remaining(eng, "8008"), 4900.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 24005 记忆永不落幕（5★）：速度常驻 + 装备者战技 → 全队增伤
# ---------------------------------------------------------------------------
class TestLC24005:
    def test_white_stats(self):
        _white("24005")

    def test_spd_pct_base(self):
        """S1：spd 100×1.06=106."""
        eng = _make(_build([_inline("24005")]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)

    def test_skill_team_dmg(self):
        """S1：装备者战技 → 我方全体增伤 +8%×3 回合（队友同吃）；装备者普攻/队友战技不触发."""
        actions = [_basic("w_basic"),
                   {"action_id": "w_skill", "name": "战技", "action_type": "skill",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
                    "skill_point_cost": 1, "energy_gain": 30}]
        ally = _inline(None, aid="a")
        eng = _make(_build([_inline("24005", actions=actions), ally]))
        _cast(eng, "w", "w_basic")
        assert "LC_24005_TEAM_DMG" not in _mods(eng, "w"), "普攻非战技"
        _cast(eng, "a", "a_basic")
        _cast(eng, "w", "w_skill")
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9), "全队含队友"
        assert math.isclose(_mods(eng, "w")["LC_24005_TEAM_DMG"].duration, 3.0)

    def test_other_actor_skill_no_trigger(self):
        """队友战技 ≠ 装备者战技——不触发（装备者判定）."""
        ally = _inline(None, aid="a", actions=[
            _basic("a_basic"),
            {"action_id": "a_skill", "name": "战技", "action_type": "skill",
             "target_type": "single", "damage_type": "fire",
             "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
             "skill_point_cost": 1, "energy_gain": 30}])
        eng = _make(_build([_inline("24005"), ally]))
        _cast(eng, "a", "a_skill")
        assert "LC_24005_TEAM_DMG" not in _mods(eng, "w")

    def test_s5_team_dmg_diff(self):
        """S5（#2=0.16）：全队增伤 +16%."""
        actions = [_basic("w_basic"),
                   {"action_id": "w_skill", "name": "战技", "action_type": "skill",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
                    "skill_point_cost": 1, "energy_gain": 30}]
        eng = _make(_build([_inline("24005", sup=5, actions=actions)]))
        _cast(eng, "w", "w_skill")
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.16, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 族级留档：官方文本无命途门槛——path 不匹配照触发（12 件同决策，本族代表两件）
# ---------------------------------------------------------------------------
class TestMemoryNoPathGate:
    def test_24005_on_non_memory_path(self):
        """24005 挂 path='destruction' 装备员：速度常驻与战技增伤照触发——文本无
        「装备者命途为记忆时」条件（ranks.json desc 终审，验收决策在案）."""
        actions = [_basic("w_basic"),
                   {"action_id": "w_skill", "name": "战技", "action_type": "skill",
                    "target_type": "single", "damage_type": "fire",
                    "scaling": [{"atk": 1.0}], "toughness_dmg": 20,
                    "skill_point_cost": 1, "energy_gain": 30}]
        eng = _make(_build([_inline("24005", path="destruction", actions=actions)]))
        assert math.isclose(_eff(eng, "w")["spd"], 106.0, rel_tol=1e-9)
        _cast(eng, "w", "w_skill")
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)

    def test_21050_on_non_memory_path(self):
        """21050 挂 path='destruction'：暴伤常驻照发."""
        eng = _make(_build([_inline("21050", path="destruction")]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5 + 0.12, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 20022 溯忆（3★）：忆灵回合双挂【缅怀】+ 忆灵消失摘除
# ---------------------------------------------------------------------------
class TestLC20022:
    def test_white_stats(self):
        _white("20022")

    def test_memo_turn_stacks_both(self):
        """S1：神君回合开始 → 景元/神君各 1 层（每层 all_dmg +8%），两回合 2 层 +16%."""
        eng = _make(_jy("20022"))
        eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        assert _mods(eng, "1204")["LC_20022_REMEMBRANCE"].stacks == 1
        assert "LC_20022_REMEMBRANCE" not in _mods(eng, "1204_lord"), "忆灵侧镜像待收（不硬凑锚）"
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.16, rel_tol=1e-9)

    def test_stack_cap_and_memo_exit(self):
        """4 层钳顶（#2 恒 4）；神君离场 → 景元侧【缅怀】摘除."""
        eng = _make(_jy("20022"))
        for _ in range(5):
            eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        assert _mods(eng, "1204")["LC_20022_REMEMBRANCE"].stacks == 4
        eng.dismiss_summon_actor("1204_lord")
        assert "LC_20022_REMEMBRANCE" not in _mods(eng, "1204")

    def test_s5_per_stack_diff(self):
        """S5（#1=0.12）：1 层 +12%."""
        eng = _make(_jy("20022", sup=5))
        eng.bus.emit("on_turn_start", {"actor": "1204_lord"}, eng.state)
        assert math.isclose(_eff(eng, "1204")["dmg_bonus"]["all"], 0.12, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21052 多流汗，少流泪（4★）：暴击常驻 + 忆灵在场双增伤
# ---------------------------------------------------------------------------
class TestLC21052:
    def test_white_stats(self):
        _white("21052")

    def test_crit_rate_base(self):
        """S1：装备者暴击率 0.05+0.12=0.17（忆灵未召=无忆灵技叠层干扰）."""
        eng = _make(_tb("21052"))
        assert math.isclose(_eff(eng, "8008")["crit_rate"], 0.05 + 0.12, rel_tol=1e-9)

    def test_memo_on_field_dual_dmg(self):
        """S1：召唤迷迷 → 装备者 all_dmg +24%（enable_if 翻转）、迷迷同挂 +24%."""
        eng = _make(_tb("21052"))
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"].get("all", 0.0), 0.0,
                            abs_tol=1e-12), "忆灵未召=增伤不启用"
        _cast(eng, "8008", "800802")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)

    def test_s5_diff(self):
        """S5：暴击 +20%、增伤 +36%."""
        eng = _make(_tb("21052", sup=5))
        assert math.isclose(_eff(eng, "8008")["crit_rate"], 0.05 + 0.2, rel_tol=1e-9)
        _cast(eng, "8008", "800802")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.36, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 22006 飞向粉色的明天（4★）：暴伤常驻 + 开拓者•记忆装备时团队增伤/强化普攻增伤
# ---------------------------------------------------------------------------
class TestLC22006:
    def test_white_stats(self):
        _white("22006")

    def test_crit_dmg_base(self):
        """S1：8008 暴伤 0.5+行迹 0.373+0.12=0.993."""
        eng = _make(_tb("22006"))
        assert math.isclose(_eff(eng, "8008")["crit_dmg"], 0.5 + 0.373 + 0.12, rel_tol=1e-9)

    def test_team_dmg_on_tb(self):
        """S1：8008 装备 → 全队增伤 +8%（装备者/忆灵同吃）；非 8007/8008 装备员不挂."""
        eng = _make(_tb("22006"))
        _cast(eng, "8008", "800802")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        eng2 = _make(_build([_inline("22006")]))
        assert "LC_22006_TEAM_DMG" not in _mods(eng2, "w")

    def test_enhanced_basic_compression(self):
        """S1（#3=0.6）：强化普攻【明天，一同写下！】真伤追加 = 冰伤段 ×0.6（真伤压缩
        严格等价——on_hp_decrease 事件流逐段核：本体半/迷迷半双覆盖）."""
        eng = _make(_tb("22006", sup=1))
        _cast(eng, "8008", "800802")                       # 迷迷在场
        eng.state.actors["8008"].resources["epic"] = 1.0   # 史诗（强化门镜像）
        events = []
        eng.bus.subscribe("on_hp_decrease", lambda _et, p, _ctx: events.append(p))
        _cast(eng, "8008", "800808")
        basic_dmg = sum(p["amount"] for p in events
                        if p["reason"] == "hit" and p["damage_type"] == "ice"
                        and p["action_type"] == "basic" and p["target"] == "e1")
        true_dmg = sum(p["amount"] for p in events
                       if p["reason"] == "hit" and p["damage_type"] == "true"
                       and p["target"] == "e1")
        assert basic_dmg > 0, "强化普攻两段均命中"
        assert math.isclose(true_dmg, basic_dmg * 0.6, rel_tol=1e-9), "两段均 +60%（S1）"

    def test_normal_basic_no_compression(self):
        """普通普攻（800801，无史诗门）不触发真伤追加."""
        eng = _make(_tb("22006", sup=1))
        _cast(eng, "8008", "800802")
        events = []
        eng.bus.subscribe("on_hp_decrease", lambda _et, p, _ctx: events.append(p))
        _cast(eng, "8008", "800801")
        true_dmg = sum(p["amount"] for p in events
                       if p["reason"] == "hit" and p["damage_type"] == "true")
        assert true_dmg == 0.0


# ---------------------------------------------------------------------------
# 23036 将光阴织成黄金（5★）：基础速度 + 织锦叠层（忆灵侧镜像待收）
# ---------------------------------------------------------------------------
class TestLC23036:
    def test_white_stats(self):
        _white("23036")

    def test_base_spd_flat(self):
        """S1：基础速度 +12（flat——面板 112）；S5 +20."""
        eng = _make(_build([_inline("23036")]))
        assert math.isclose(_eff(eng, "w")["spd"], 112.0, rel_tol=1e-9)
        eng5 = _make(_build([_inline("23036", sup=5)]))
        assert math.isclose(_eff(eng5, "w")["spd"], 120.0, rel_tol=1e-9)

    def test_brocade_stacks_and_full_basic_boost(self):
        """S1：攻击 ×6 → 6 层（#2 恒 6 钳顶），暴伤 +0.09×6；满层普攻增伤 +0.09×6."""
        eng = _make(_build([_inline("23036")]))
        for _ in range(5):
            _cast(eng, "w", "w_basic")
        assert _mods(eng, "w")["LC_23036_BROCADE"].stacks == 5
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5 + 0.09 * 5, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("basic_dmg_boost", 0.0), 0.0,
                            abs_tol=1e-12), "未满层无普攻增伤"
        _cast(eng, "w", "w_basic")
        assert _mods(eng, "w")["LC_23036_BROCADE"].stacks == 6
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5 + 0.09 * 6, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["basic_dmg_boost"], 0.09 * 6,
                            rel_tol=1e-9), "满层普攻增伤随层"

    def test_memo_skill_also_stacks(self):
        """忆灵技（迷迷 1800701）→ 装备者 +1 层（21050 近似域）."""
        eng = _make(_tb("23036"))
        _cast(eng, "8008", "800802", target_id="8008")
        assert "LC_23036_BROCADE" not in _mods(eng, "8008"), "召唤技非攻击不叠层"
        _cast(eng, "8008_mem", "1800701")
        assert _mods(eng, "8008")["LC_23036_BROCADE"].stacks == 1

    def test_memo_mirror_pending(self):
        """忆灵侧暴伤镜像待收（fixture 头注挡因）——迷迷不挂镜像件（不硬凑锚）."""
        eng = _make(_tb("23036"))
        _cast(eng, "8008", "800802")
        assert "LC_23036_BROCADE_MEMO" not in _mods(eng, "8008_mem")


# ---------------------------------------------------------------------------
# 23042 愿虹光永驻天空（5★）：速度常驻 + 忆灵技承伤（耗血/tally/忆灵附加段待收）
# ---------------------------------------------------------------------------
class TestLC23042:
    def test_white_stats(self):
        _white("23042")

    def test_spd_pct(self):
        eng = _make(_build([_inline("23042")]))
        assert math.isclose(_eff(eng, "w")["spd"], 118.0, rel_tol=1e-9)

    def test_memo_skill_vuln(self):
        """S1：忆灵技 → 敌方全体承伤 +18%（2 回合，replace 同类不叠）；S5 +36%."""
        eng = _make(_tb("23042"))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800701")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.18, rel_tol=1e-9)
        assert _mods(eng, "e1")["LC_23042_VULN"].duration == 2
        eng5 = _make(_tb("23042", sup=5))
        _cast(eng5, "8008", "800802")
        _cast(eng5, "8008_mem", "1800701")
        assert math.isclose(_eff(eng5, "e1")["vulnerability"], 0.36, rel_tol=1e-9)

    def test_no_drain_placeholder(self):
        """耗血段待收——装备者行动不耗我方生命（不硬凑锚）."""
        eng = _make(_tb("23042"))
        hp0 = eng.state.actors["8008"].current_hp
        _cast(eng, "8008", "800801")
        assert math.isclose(eng.state.actors["8008"].current_hp, hp0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23049 致长夜的星光（5★）：生命常驻 + 夜色三件 + 忆灵消失回能
# ---------------------------------------------------------------------------
class TestLC23049:
    def test_white_stats(self):
        _white("23049", hp_mult=1.3)

    def test_night_pieces(self):
        """S1：忆灵技 → 装备者持【夜色】；装备者/忆灵增伤 +30%、忆灵无视防御 +20%."""
        eng = _make(_tb("23049"))
        _cast(eng, "8008", "800802")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"].get("all", 0.0), 0.0,
                            abs_tol=1e-12), "夜色未持=增伤不启用"
        _cast(eng, "8008_mem", "1800701")
        assert "LC_23049_NIGHT" in _mods(eng, "8008")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.3, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["dmg_bonus"]["all"], 0.3, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["def_pen"], 0.2, rel_tol=1e-9)

    def test_memo_exit_energy(self):
        """S1：忆灵消失 → 装备者回能 +8；S5 +16."""
        eng = _make(_tb("23049"))
        _cast(eng, "8008", "800802")
        st = eng.state.actors["8008"]
        st.current_energy = 0.0
        eng.dismiss_summon_actor("8008_mem")
        assert math.isclose(st.current_energy, 8.0, rel_tol=1e-9)
        eng5 = _make(_tb("23049", sup=5))
        _cast(eng5, "8008", "800802")
        st5 = eng5.state.actors["8008"]
        st5.current_energy = 0.0
        eng5.dismiss_summon_actor("8008_mem")
        assert math.isclose(st5.current_energy, 16.0, rel_tol=1e-9)

    def test_s5_night_values(self):
        """S5：增伤 +60%、忆灵无视防御 +30%."""
        eng = _make(_tb("23049", sup=5))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800701")
        assert math.isclose(_eff(eng, "8008")["dmg_bonus"]["all"], 0.6, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008_mem")["def_pen"], 0.3, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23052 爱如此刻永恒（5★）：速度常驻 + 空白/诗行 + 双持增强
# ---------------------------------------------------------------------------
class TestLC23052:
    def test_white_stats(self):
        _white("23052")

    def test_spd_pct(self):
        eng = _make(_build([_inline("23052")]))
        assert math.isclose(_eff(eng, "w")["spd"], 118.0, rel_tol=1e-9)

    def test_blank_ally_skill(self):
        """S1：忆灵对我方施技 → 装备者持【空白】+ 敌方承伤 +10%."""
        eng = _make(_tb("23052"))
        _cast(eng, "8008", "800802")
        _cast(eng, "8008_mem", "1800707", target_id="8008")
        assert "LC_23052_BLANK" in _mods(eng, "8008")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.1, rel_tol=1e-9)

    def test_poem_enemy_skill_team_crit(self):
        """S1：忆灵对敌施技 → 装备者持【诗行】→ 全队暴伤 +16%（8008：0.5+0.373+0.16）."""
        eng = _make(_tb("23052"))
        _cast(eng, "8008", "800802")
        cd0 = _eff(eng, "8008")["crit_dmg"]
        _cast(eng, "8008_mem", "1800701")
        assert "LC_23052_POEM" in _mods(eng, "8008")
        assert math.isclose(_eff(eng, "8008")["crit_dmg"] - cd0, 0.16, rel_tol=1e-9)

    def test_both_held_enhanced(self):
        """S1 双持：空白承伤 ×1.6=+16%、诗行暴伤 ×1.6=+25.6%（#4=0.6 效果提高）."""
        eng = _make(_tb("23052"))
        _cast(eng, "8008", "800802")
        cd0 = _eff(eng, "8008")["crit_dmg"]
        _cast(eng, "8008_mem", "1800707", target_id="8008")
        _cast(eng, "8008_mem", "1800701")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.16, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "8008")["crit_dmg"] - cd0, 0.256, rel_tol=1e-9)
