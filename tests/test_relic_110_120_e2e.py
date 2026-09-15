"""110-120 族遗器 e2e：staging→fixtures 验收批.

本族 11 套（110/111/112/113/114/115/116/117/118/119/120），每套 2 件/4 件分例：
2 件只触发 2pc、4 件全触发（4pc 行为断言分两例——2 件不触发 + 4 件触发）。
面板/行为断言手算对轴：假人 def 1000 → 防御区 0.5；弱点全配 → 抗性 1.0；
未击破 0.9；期望暴击 1.025（crit 0.05/0.5，每 +0.01 暴击率期望区 +0.005）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 模子（验收手册 e2e 模子 + 本族扩展件）
# ---------------------------------------------------------------------------

_BASIC_FIRE = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
               "target_type": "single", "damage_type": "fire",
               "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_BASIC_WIND = {**_BASIC_FIRE, "action_id": "t_basic_w", "name": "普攻·风",
               "damage_type": "wind"}
_BASIC_ZERO_E = {**_BASIC_FIRE, "energy_gain": 0}  # 显式不回能——111 能量断言隔离行动回能
_ULT_FIRE = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
             "target_type": "single", "damage_type": "fire", "energy_cost": 100,
             "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
_ULT_ALLY = {"action_id": "t_ult_a", "name": "终结技·辅", "action_type": "ultimate",
             "target_type": "ally_single", "energy_cost": 100}
_FUA = {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
        "target_type": "single", "damage_type": "fire",
        "scaling": [{"atk": 1.0}], "toughness_dmg": 0}
_DEBUFF_SKILL = {"action_id": "t_debuff", "name": "减益技", "action_type": "skill",
                 "target_type": "aoe",  # 对敌全体减益技（黑天鹅终结技同族）——无伤害段
                 "apply_modifiers": [
                     {"target": "all_enemies", "modifier_id": "TEST_DEBUFF",
                      "name": "测试减益", "modifier_type": "debuff", "duration": 2,
                      "stat_effects": {"vulnerability": 0.1}}]}


def _member(actor_id="w", *, set_id=None, pieces=0, actions=(), spd=100):
    m = {"actor_id": actor_id, "name": f"装备员{actor_id}", "inline": True,
         "base_stats": {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100},
         "actions": list(actions)}
    if set_id is not None:
        m["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    return m


def _build(set_id, pieces=4, *, actions=(_BASIC_FIRE,), extra=()):
    member = _member("w", set_id=set_id, pieces=pieces, actions=actions)
    return {"build": {"team": [member, *extra],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage(max_toughness=100):
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
         "max_toughness": max_toughness,
         "weakness": ["fire", "ice", "thunder", "wind",
                      "quantum", "imaginary", "physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(set_id, pieces=4, *, actions=(_BASIC_FIRE,), extra=(), max_toughness=100):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(set_id, pieces, actions=actions, extra=extra),
                          _stage(max_toughness), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _cast(eng, owner, aid, target_id="e1"):
    """行动施放模子（照抄 8009 e2e——_execute_action + on_action 广播）."""
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


#: 113 用敌方打击（inline 构造——单成员队伍下 _pick_ally_target 恒命中装备者）
_ENEMY_HIT = Action(action_id="e_hit", name="敌击", action_type="basic",
                    target_type="single", damage_type="physical",
                    scaling=[{"atk": 1.0}], toughness_dmg=0)


def _enemy_hit(eng, times=1):
    for _ in range(times):
        eng._execute_action(eng.state.actors["e1"], _ENEMY_HIT)


# ---------------------------------------------------------------------------
# 110 晨昏交界的翔鹰：2pc 风伤 +10% / 4pc 自开大后行动提前 25%
# ---------------------------------------------------------------------------

class TestRelic110:
    def test_2pc_wind_dmg(self):
        eng = _make("110", 2, actions=(_BASIC_WIND,))
        assert _panel(eng)["dmg_bonus"]["wind"] == pytest.approx(0.1)
        # 风普攻期望 = 1000 × 1.1(风伤) × 0.5 × 1.0 × 0.9 × 1.025 = 507.375
        before = _hp(eng)
        _cast(eng, "w", "t_basic_w")
        assert before - _hp(eng) == pytest.approx(1000 * 1.1 * 0.5 * 0.9 * 1.025)

    def test_4pc_advance_after_ult(self):
        eng = _make("110", 4, actions=(_ULT_FIRE,))
        assert _remaining(eng) == pytest.approx(10000.0)
        _ult(eng)
        assert _remaining(eng) == pytest.approx(7500.0)   # 提前 25% = 剩余距离 -2500

    def test_2pc_no_advance(self):
        eng = _make("110", 2, actions=(_ULT_FIRE,))
        _ult(eng)
        assert _remaining(eng) == pytest.approx(10000.0)   # 2 件无 4pc 钩——不拉条


# ---------------------------------------------------------------------------
# 111 流星追迹的怪盗：2pc 击破 +16% / 4pc 击破 +16% + 击破弱点回 3 能
# ---------------------------------------------------------------------------

class TestRelic111:
    def test_2pc_break_effect(self):
        eng = _make("111", 2)
        assert _panel(eng)["break_effect"] == pytest.approx(0.16)

    def test_4pc_break_effect(self):
        eng = _make("111", 4)
        assert _panel(eng)["break_effect"] == pytest.approx(0.32)

    def test_4pc_energy_on_break(self):
        # 假人韧性 10、普攻削韧 10 → 一击即破；energy_gain 0 隔离行动回能
        eng = _make("111", 4, actions=(_BASIC_ZERO_E,), max_toughness=10)
        _cast(eng, "w", "t_basic")
        assert eng.state.actors["e1"].broken, "削韧 10 对韧性 10 应已击破"
        assert eng.state.actors["w"].current_energy == pytest.approx(3.0)

    def test_2pc_no_energy_on_break(self):
        eng = _make("111", 2, actions=(_BASIC_ZERO_E,), max_toughness=10)
        _cast(eng, "w", "t_basic")
        assert eng.state.actors["e1"].broken
        assert eng.state.actors["w"].current_energy == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 113 宝命长存的莳者：2pc 生命 +12% / 4pc 受击/耗血后暴击 +8%×至多 2 层
# ---------------------------------------------------------------------------

class TestRelic113:
    def test_2pc_hp(self):
        eng = _make("113", 2)
        assert _panel(eng)["hp"] == pytest.approx(3000 * 1.12)

    def test_4pc_crit_stacks(self):
        eng = _make("113", 4)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)
        _enemy_hit(eng, 1)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.08)    # 1 层
        _enemy_hit(eng, 1)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.16)    # 2 层
        m = eng.state.actors["w"].modifiers["SET_113_4PC_CRITRATE"]
        assert m.stacks == 2 and m.duration == 2
        _enemy_hit(eng, 1)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.16)    # 上限 2 层

    def test_2pc_no_crit_on_hit(self):
        eng = _make("113", 2)
        _enemy_hit(eng, 1)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)

    def test_4pc_drain_branch(self):
        """我方消耗生命（drain）支路：drain_hp 真路径（刃/镜流耗血族同漏斗）触发叠层."""
        eng = _make("113", 4)
        st = eng.state.actors["w"]
        eng._run_hook_effect(st, {"effect_type": "drain_hp", "target": "self",
                                  "amount": 100, "drain_ratio": 0}, {})
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.08)    # drain 亦叠 1 层

    def test_4pc_dot_excluded_pending_probe(self):
        """DoT 跳伤不计入"受到攻击"（官方文本保守口径，待实测——翻案则改钉）."""
        eng = _make("113", 4)
        eng.bus.emit("on_hp_decrease", {"amount": 50.0, "source": "e1",
                                        "reason": "dot", "target": "w"}, eng.state)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 114 骇域漫游的信使：2pc 速度 +6% / 4pc 对我方开大后全队速度 +12%（1 回合）
# ---------------------------------------------------------------------------

def _ally():
    return _member("a2", actions=(_BASIC_FIRE,))


class TestRelic114:
    def test_2pc_spd(self):
        eng = _make("114", 2, extra=(_ally(),))
        assert _panel(eng)["spd"] == pytest.approx(106.0)
        assert _panel(eng, "a2")["spd"] == pytest.approx(100.0)

    def test_4pc_team_spd_after_ally_ult(self):
        eng = _make("114", 4, actions=(_ULT_ALLY,), extra=(_ally(),))
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert _panel(eng)["spd"] == pytest.approx(100 + 100 * 0.18)     # 2pc 6% + 4pc 12%
        assert _panel(eng, "a2")["spd"] == pytest.approx(100 + 100 * 0.12)
        m = eng.state.actors["w"].modifiers["SET_114_SPD"]
        assert m.duration == 1

    def test_2pc_no_team_spd(self):
        eng = _make("114", 2, actions=(_ULT_ALLY,), extra=(_ally(),))
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert _panel(eng)["spd"] == pytest.approx(106.0)
        assert _panel(eng, "a2")["spd"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# 116 幽锁深牢的系囚：2pc 攻击 +12% / 4pc 逐目标按 DoT 数无视防御【待收编】
# ---------------------------------------------------------------------------

class TestRelic116:
    def test_2pc_atk(self):
        eng = _make("116", 2)
        assert _panel(eng)["atk"] == pytest.approx(1120.0)

    def test_4pc_pending_no_extra(self):
        # 4pc 机制待收编（逐目标动态 def_pen + 目标 DoT 计数通道双缺）——4 件与 2 件
        # 行为一致：面板只多 0、无 4pc modifier、无 hook 注册
        eng = _make("116", 4)
        assert _panel(eng)["atk"] == pytest.approx(1120.0)
        assert set(eng.state.actors["w"].modifiers) == {"RELIC_116_2PC"}
        assert not eng._compiled_hooks


# ---------------------------------------------------------------------------
# 117 死水深潜的先驱：2pc 对负面目标增伤【待收编】 / 4pc 暴击 4% + 施减益后翻倍
# ---------------------------------------------------------------------------

class TestRelic117:
    def test_2pc_pending_no_stat(self):
        # 2pc 机制待收编（目标"持有任一 debuff"判定缺）——2 件无任何面板/钩
        eng = _make("117", 2)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)
        assert not eng.state.actors["w"].modifiers

    def test_4pc_crit_and_double(self):
        eng = _make("117", 4, actions=(_DEBUFF_SKILL,))
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.04)
        _cast(eng, "w", "t_debuff")
        # 装备者对敌方施加 debuff → 翻倍件：暴击率再 +4%（4%→8%），持续 1 回合
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.08)
        m = eng.state.actors["w"].modifiers["SET_117_4PC_DOUBLE"]
        assert m.duration == 1

    def test_2pc_no_double(self):
        eng = _make("117", 2, actions=(_DEBUFF_SKILL,))
        _cast(eng, "w", "t_debuff")
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# 118 机心戏梦的钟表匠：2pc 击破 +16% / 4pc 对我方开大后全队击破 +30%（2 回合）
# ---------------------------------------------------------------------------

class TestRelic118:
    def test_2pc_break_effect(self):
        eng = _make("118", 2, extra=(_ally(),))
        assert _panel(eng)["break_effect"] == pytest.approx(0.16)

    def test_4pc_team_be_after_ally_ult(self):
        eng = _make("118", 4, actions=(_ULT_ALLY,), extra=(_ally(),))
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert _panel(eng)["break_effect"] == pytest.approx(0.16 + 0.30)
        assert _panel(eng, "a2")["break_effect"] == pytest.approx(0.30)
        m = eng.state.actors["w"].modifiers["SET_118_WATCHMAKER_BE"]
        assert m.duration == 2

    def test_2pc_no_team_be(self):
        eng = _make("118", 2, actions=(_ULT_ALLY,), extra=(_ally(),))
        _ult(eng, aid="t_ult_a", target_id="a2")
        assert _panel(eng)["break_effect"] == pytest.approx(0.16)
        assert _panel(eng, "a2")["break_effect"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 119 荡除蠹灾的铁骑：2pc 击破 +16% / 4pc 击破·超击破无视防御【待收编】
# ---------------------------------------------------------------------------

class TestRelic119:
    def test_2pc_break_effect(self):
        eng = _make("119", 2)
        assert _panel(eng)["break_effect"] == pytest.approx(0.16)

    def test_4pc_pending_no_extra(self):
        # 4pc 机制待收编（击破/超击破限定 def_pen 消费端缺——全局 def_pen 外溢直伤
        # 不可代写）：4 件只多 0、无 4pc modifier、无 hook 注册
        eng = _make("119", 4)
        assert _panel(eng)["break_effect"] == pytest.approx(0.16)
        assert set(eng.state.actors["w"].modifiers) == {"RELIC_119_2PC"}
        assert not eng._compiled_hooks


# ---------------------------------------------------------------------------
# 120 风举云飞的勇烈：2pc 攻击 +12% / 4pc 暴击 6% + 追加后终结技伤害 +36%
# ---------------------------------------------------------------------------

class TestRelic120:
    #: 4 件期望暴击区 = 1 + (0.05+0.06)×0.5 = 1.055
    _CZ = 1 + 0.11 * 0.5

    def test_2pc_atk(self):
        eng = _make("120", 2)
        assert _panel(eng)["atk"] == pytest.approx(1120.0)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)

    def test_4pc_crit(self):
        eng = _make("120", 4)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.11)

    def test_4pc_ult_dmg_after_fua(self):
        eng = _make("120", 4, actions=(_FUA, _ULT_FIRE))
        _cast(eng, "w", "t_fua")
        m = eng.state.actors["w"].modifiers["SET_120_ULT_DMG"]
        assert m.stat_effects["dmg_ultimate_dmg_boost"] == pytest.approx(0.36)
        assert m.duration == 1
        # 追加后终结技期望 = 1120 × 1.36(终伤) × 0.5 × 1.0 × 0.9 × 1.055 = 723.1392
        before = _hp(eng)
        _ult(eng)
        assert before - _hp(eng) == pytest.approx(1120 * 1.36 * 0.5 * 0.9 * self._CZ)

    def test_4pc_ult_dmg_without_fua(self):
        # 未发动追加 → 无终伤件：终结技期望 = 1120 × 1.0 × 0.5 × 0.9 × 1.055 = 531.72
        eng = _make("120", 4, actions=(_FUA, _ULT_FIRE))
        before = _hp(eng)
        _ult(eng)
        assert before - _hp(eng) == pytest.approx(1120 * 1.0 * 0.5 * 0.9 * self._CZ)

    def test_2pc_no_ult_dmg(self):
        # 2 件：追加不触发终伤件；终结技期望 = 1120 × 0.5 × 0.9 × 1.025 = 516.6
        eng = _make("120", 2, actions=(_FUA, _ULT_FIRE))
        _cast(eng, "w", "t_fua")
        assert "SET_120_ULT_DMG" not in eng.state.actors["w"].modifiers
        before = _hp(eng)
        _ult(eng)
        assert before - _hp(eng) == pytest.approx(1120 * 0.5 * 0.9 * 1.025)


# ---------------------------------------------------------------------------
# 112 盗匪荒漠的废土客：2pc 虚数伤 +10%；4pc scoped 双暴【待收】
# ---------------------------------------------------------------------------
class TestRelic112Wastelander:
    def test_2pc_imaginary_dmg(self):
        """2pc 虚数伤 +10%（面板常驻；火伤普攻不吃——元素桶）."""
        eng = _make("112", 2, actions=(_BASIC_FIRE, {**_BASIC_FIRE, "action_id": "t_basic_i",
                                                    "name": "普攻·虚数", "damage_type": "imaginary"}))
        assert _panel(eng)["dmg_bonus"]["imaginary"] == pytest.approx(0.1)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic_i")
        assert _hp(eng) == pytest.approx(hp1 - 1000 * 1.1 * 0.5 * 0.9 * 1.025)
        hp2 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert _hp(eng) == pytest.approx(hp2 - 1000 * 1.0 * 0.5 * 0.9 * 1.025)

    def test_4pc_scoped_crit_pending(self):
        """4pc 待收（fixture 头注挡因——scoped 双暴无消费端）：减益目标前/后暴击面板
        与伤害均无变化（不硬凑锚）."""
        eng = _make("112", 4, actions=(_BASIC_FIRE, _DEBUFF_SKILL))
        _cast(eng, "w", "t_debuff")
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05)
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 115 毁烬焚骨的大公：2pc 追击增伤 +20%；4pc 追击逐段叠攻（cap 8，再追击移除）
# ---------------------------------------------------------------------------
def _fua_segs(eng, n, *, start=0):
    """追击多段命中事件（每次造成伤害 1 层——段序 start 起）."""
    for seg in range(start, start + n):
        eng.bus.emit("after_being_hit", {
            "source": "w", "target": "e1", "action_type": "follow_up",
            "damage_type": "fire", "amount": 100.0, "seg_index": seg}, eng.state)


class TestRelic115Ashblazing:
    def test_2pc_fua_dmg_boost(self):
        """2pc：追加攻击 +20%（类型桶）——追击伤害对轴；普攻不吃."""
        eng = _make("115", 2, actions=(_BASIC_FIRE, _FUA))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_fua")
        assert _hp(eng) == pytest.approx(hp1 - 1000 * 1.2 * 0.5 * 0.9 * 1.025)

    def test_4pc_stacks_per_hit(self):
        """4pc：追击每次造成伤害 +6% 攻击（3 段=3 层=+18%）；普攻不叠."""
        eng = _make("115", 4, actions=(_BASIC_FIRE, _FUA))
        _cast(eng, "w", "t_basic")
        assert "SET_115_ATK_STACK" not in eng.state.actors["w"].modifiers
        _fua_segs(eng, 3)
        assert eng.state.actors["w"].modifiers["SET_115_ATK_STACK"].stacks == 3
        assert _panel(eng)["atk"] == pytest.approx(1000 * 1.18)
        assert eng.state.actors["w"].modifiers["SET_115_ATK_STACK"].duration == 3

    def test_4pc_cap_8(self):
        eng = _make("115", 4, actions=(_BASIC_FIRE, _FUA))
        _fua_segs(eng, 9)
        assert eng.state.actors["w"].modifiers["SET_115_ATK_STACK"].stacks == 8
        assert _panel(eng)["atk"] == pytest.approx(1000 * 1.48)

    def test_4pc_reset_on_next_fua(self):
        """下一次施放追加攻击时移除旧叠层——新追击首段后从 1 层重计."""
        eng = _make("115", 4, actions=(_BASIC_FIRE, _FUA))
        _fua_segs(eng, 3)
        assert eng.state.actors["w"].modifiers["SET_115_ATK_STACK"].stacks == 3
        _cast(eng, "w", "t_fua")     # 新追击首段：先摘 3 层再计本次
        assert eng.state.actors["w"].modifiers["SET_115_ATK_STACK"].stacks == 1

    def test_2pc_only_no_stacks(self):
        eng = _make("115", 2, actions=(_BASIC_FIRE, _FUA))
        _fua_segs(eng, 2)
        assert "SET_115_ATK_STACK" not in eng.state.actors["w"].modifiers
