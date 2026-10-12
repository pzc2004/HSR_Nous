"""121-131 族遗器 e2e：staging→机制库验收批（human_queue 分诊落版）.

本批 5 套（121/122/128/129/131），每套 2 件/4 件分例——2 件只触发 2pc、4 件全触发。
fixture 勘正/挡因条目见各 fixture 头注。

口径常数（110-120 族同模子）：装备员 atk 1000 / spd 100 / hp 3000，inline scaling atk 1.0；
假人 def 1000 → 防御区 0.5；弱点全配 → 抗性 1.0；未击破 0.9；期望暴击区 1.025
（crit 0.05/0.5）。直伤基准（无增伤）= 1000×0.5×0.9×1.025 = 461.25。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 模子（110-120 族同构）
# ---------------------------------------------------------------------------

_BASIC_FIRE = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
               "target_type": "single", "damage_type": "fire",
               "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
_SKILL_FIRE = {"action_id": "t_skill", "name": "战技", "action_type": "skill",
               "target_type": "single", "damage_type": "fire", "energy_gain": 0,
               "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
_SKILL_ALLY = {"action_id": "t_skill_a", "name": "战技·辅", "action_type": "skill",
               "target_type": "ally_single", "skill_point_cost": 1, "energy_gain": 0}
_ULT_FIRE = {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
             "target_type": "single", "damage_type": "fire", "energy_cost": 100,
             "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
_ULT_ALLY = {"action_id": "t_ult_a", "name": "终结技·辅", "action_type": "ultimate",
             "target_type": "ally_single", "energy_cost": 100, "energy_gain": 0}

#: 直伤链：防御区×未击破×期望暴击区
Z = 0.5 * 0.9 * 1.025
#: 122 专用：2pc 暴击率 +8% → 期望暴击区 0.13×1.5+0.87=1.065
Z122 = 0.5 * 0.9 * 1.065


def _member(actor_id="w", *, set_id=None, pieces=0, actions=()):
    m = {"actor_id": actor_id, "name": f"装备员{actor_id}", "inline": True,
         "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
         "actions": list(actions)}
    if set_id is not None:
        m["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    return m


def _build(set_id, pieces=4, *, actions=(_BASIC_FIRE,), extra=()):
    member = _member("w", set_id=set_id, pieces=pieces, actions=actions)
    return {"build": {"team": [member, *extra],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(set_id, pieces=4, *, actions=(_BASIC_FIRE,), extra=()):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(set_id, pieces, actions=actions, extra=extra), _STAGE,
                          template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _cast(eng, owner, aid, target_id="e1"):
    """行动施放模子（8009 模子——_execute_action + on_action 广播）."""
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
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = 100.0
    assert eng._fire_ultimate(st, a) is True


def _hp(eng, aid="e1"):
    return eng.state.actors[aid].current_hp


def _dmg_of(eng, owner, aid, target_id="e1", *, ult=False):
    """单段伤害对轴取数（施放前后 HP 差）."""
    hp1 = _hp(eng, target_id)
    (_ult if ult else _cast)(eng, owner, aid, target_id)
    return hp1 - _hp(eng, target_id)


# ---------------------------------------------------------------------------
# 121 重循苦旅的司铎：2pc 速度 +6%；4pc 对我方单体放技挂目标暴伤叠层
# ---------------------------------------------------------------------------
class TestRelic121Sacerdos:
    def test_2pc_spd(self):
        eng = _make("121", 2)
        assert _panel(eng)["spd"] == pytest.approx(106.0)

    def test_4pc_crit_dmg_on_ally_skill(self):
        """4pc：对我方单体放战技 → 目标暴伤 +18%（2 回合）；再放叠 2 层 +36%（cap 2）."""
        ally = _member("a", actions=(_BASIC_FIRE,))
        eng = _make("121", 4, actions=(_BASIC_FIRE, _SKILL_ALLY), extra=(ally,))
        _cast(eng, "w", "t_skill_a", target_id="a")
        assert _panel(eng, "a")["crit_dmg"] == pytest.approx(0.5 + 0.18)
        assert eng.state.actors["a"].modifiers["SET_121_CRITDMG"].duration == 2
        _cast(eng, "w", "t_skill_a", target_id="a")
        assert _panel(eng, "a")["crit_dmg"] == pytest.approx(0.5 + 0.36)
        _cast(eng, "w", "t_skill_a", target_id="a")
        assert eng.state.actors["a"].modifiers["SET_121_CRITDMG"].stacks == 2, "cap 2"
        assert _panel(eng, "a")["crit_dmg"] == pytest.approx(0.5 + 0.36)

    def test_4pc_ally_ult_also_triggers(self):
        ally = _member("a", actions=(_BASIC_FIRE,))
        eng = _make("121", 4, actions=(_BASIC_FIRE, _ULT_ALLY), extra=(ally,))
        _ult(eng, "w", "t_ult_a", target_id="a")
        assert _panel(eng, "a")["crit_dmg"] == pytest.approx(0.5 + 0.18)

    def test_2pc_only_no_4pc(self):
        ally = _member("a", actions=(_BASIC_FIRE,))
        eng = _make("121", 2, actions=(_BASIC_FIRE, _SKILL_ALLY), extra=(ally,))
        _cast(eng, "w", "t_skill_a", target_id="a")
        assert _panel(eng, "a")["crit_dmg"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 122 识海迷坠的学者：2pc 暴击率 +8%；4pc 战技/终结技增伤 + 终结技后下次战技加增
# ---------------------------------------------------------------------------
class TestRelic122Scholar:
    def test_2pc_crit_rate(self):
        eng = _make("122", 2)
        assert _panel(eng)["crit_rate"] == pytest.approx(0.05 + 0.08)

    def test_4pc_skill_ult_dmg(self):
        """4pc：战技/终结技 +20%（类型桶常驻）；普攻不吃."""
        eng = _make("122", 4, actions=(_BASIC_FIRE, _SKILL_FIRE, _ULT_FIRE))
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.2)
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.2)
        assert _dmg_of(eng, "w", "t_skill") == pytest.approx(1000 * 1.2 * Z122)
        assert _dmg_of(eng, "w", "t_basic") == pytest.approx(1000 * 1.0 * Z122)
        assert _dmg_of(eng, "w", "t_ult", ult=True) == pytest.approx(1000 * 1.2 * Z122)

    def test_4pc_next_skill_after_ult(self):
        """终结技后下一次战技额外 +25%（hit_condition scoped）；再下次战技回落 +20%."""
        eng = _make("122", 4, actions=(_BASIC_FIRE, _SKILL_FIRE, _ULT_FIRE))
        _ult(eng, "w", "t_ult")
        assert _dmg_of(eng, "w", "t_skill") == pytest.approx(1000 * 1.45 * Z122)
        assert _dmg_of(eng, "w", "t_skill") == pytest.approx(1000 * 1.2 * Z122), "一次性消费"

    def test_2pc_only_no_4pc(self):
        eng = _make("122", 2, actions=(_BASIC_FIRE, _SKILL_FIRE, _ULT_FIRE))
        assert _dmg_of(eng, "w", "t_skill") == pytest.approx(1000 * 1.0 * Z122)


# ---------------------------------------------------------------------------
# 128 自匿星芒的隐士：2pc/4pc 护盾量（4pc 后半持盾暴伤【待收】）
# ---------------------------------------------------------------------------
class TestRelic128Hermit:
    def test_2pc_shield_bonus(self):
        eng = _make("128", 2)
        assert _panel(eng)["shield_bonus"] == pytest.approx(0.1)

    def test_4pc_shield_bonus(self):
        eng = _make("128", 4)
        assert _panel(eng)["shield_bonus"] == pytest.approx(0.1 + 0.12)

    def test_4pc_shielded_crit_pending(self):
        """后半「我方目标持有装备者提供的护盾时暴伤 +15%」待收（fixture 头注挡因——
        逐目标持盾判定无通道）."""
        eng = _make("128", 4)
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 129 闪耀功勋的魔法少女：2pc 暴伤 +16%；4pc 欢愉伤无视防御 10%（2026-09-23 收编）
# + 每累计 5 笑点额外无视 1%×N 钳 10（2026-10-12 B36 批 3 收编——装备侧
# custom_resources 通道 + hit_stat_exprs 命中域折算）
# ---------------------------------------------------------------------------
class TestRelic129MagicalGirl:
    @staticmethod
    def _elation_dmg(eng):
        """欢愉路由直测（settle elation——hit_condition 命中域 def_pen 消费端）."""
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        return eng.pipeline.settle_damage(
            "elation", w, e1, element="fire",
            params={"ability_multiplier": 1000.0, "punchline_source": 30.0}).value

    @staticmethod
    def _direct_dmg(eng):
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        return eng.pipeline.settle_damage(
            "direct", w, e1,
            action=next(iter(eng.actions_by_actor.get("w", [])), None),
            params={"base_override": 1000.0}).value

    def test_2pc_crit_dmg(self):
        eng = _make("129", 2)
        assert _panel(eng)["crit_dmg"] == pytest.approx(0.5 + 0.16)

    def test_4pc_base_def_pen(self):
        """4pc 基础半生效钉：欢愉路由 10% 穿透（defMulti 100/190）；直伤路由不吃（反例）."""
        eng = _make("129", 4)
        assert eng.state.actors["w"].resources.get("rec_129_punch_tally", 0.0) == 0.0, (
            "累计池初始化（装备侧 custom_resources 通道）")
        base = self._elation_dmg(eng)
        naked = base * 0.5 / (100 / 190)   # 折回零穿透基准（defMulti 100/190 → 0.5）
        eng2 = _make("129", 2)             # 2pc 无 4pc → 零穿透
        assert self._elation_dmg(eng2) == pytest.approx(naked, rel=1e-9), "2pc 无穿透（反例）"

    def test_4pc_stack_tally_and_fold(self):
        """叠层半生效钉：笑点获得累计 → min(//5,10)×1% 命中域折算——13 点=2 层
        （0.10+0.02 → defMulti 100/186）；负向清池不计；钳 10 层."""
        eng = _make("129", 4)
        w = eng.state.actors["w"]
        v0 = self._elation_dmg(eng)
        eng._gain_resource(w, "punchline", 13.0)
        assert w.resources["rec_129_punch_tally"] == 13.0, "正向获得累计"
        v2 = self._elation_dmg(eng)
        ratio = (100 / (100 * (1 - 0.12) + 100)) / (100 / (100 * (1 - 0.10) + 100))
        assert v2 / v0 == pytest.approx(ratio, rel=1e-9), "2 层穿透增量比"
        eng._gain_resource(w, "punchline", -13.0)   # 阿哈清池负向——不计入累计
        assert w.resources["rec_129_punch_tally"] == 13.0, "负向清池不计（反例）"
        eng._gain_resource(w, "punchline", 60.0)    # 累计 73 → 14 层 → 钳 10
        v10 = self._elation_dmg(eng)
        ratio_cap = (100 / (100 * (1 - 0.20) + 100)) / (100 / (100 * (1 - 0.10) + 100))
        assert v10 / v0 == pytest.approx(ratio_cap, rel=1e-9), "钳 10 层（0.10+0.10）"

    def test_direct_route_unaffected(self):
        """反例：直伤路由（非欢愉伤害）不吃本件穿透（hit_condition 路由标识闸）."""
        eng = _make("129", 4, actions=(_BASIC_FIRE,))
        eng._gain_resource(eng.state.actors["w"], "punchline", 30.0)
        v_129 = self._direct_dmg(eng)
        eng2 = _make("129", 2, actions=(_BASIC_FIRE,))
        assert v_129 == pytest.approx(self._direct_dmg(eng2), rel=1e-9), (
            "直伤路由 4pc 与 2pc 同值（穿透不命中）")


# ---------------------------------------------------------------------------
# 131 星如我见的领航员：4pc 进战/战技叠层（战技终结技增伤），回合开始/终结技后摘除
# ---------------------------------------------------------------------------
class TestRelic131Navigator:
    def test_4pc_battle_start_stack(self):
        eng = _make("131", 4, actions=(_BASIC_FIRE, _SKILL_FIRE, _ULT_FIRE))
        assert eng.state.actors["w"].modifiers["SET_131_NAV_STACK"].stacks == 1
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.18)
        assert _panel(eng)["dmg_bonus"]["ultimate_dmg_boost"] == pytest.approx(0.18)

    def test_4pc_skill_stacks_cap3(self):
        eng = _make("131", 4, actions=(_BASIC_FIRE, _SKILL_FIRE))
        _cast(eng, "w", "t_skill")
        assert eng.state.actors["w"].modifiers["SET_131_NAV_STACK"].stacks == 2
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.36)
        _cast(eng, "w", "t_skill")
        _cast(eng, "w", "t_skill")
        assert eng.state.actors["w"].modifiers["SET_131_NAV_STACK"].stacks == 3
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.54)

    def test_4pc_turn_start_and_ult_remove(self):
        """回合开始 -1 层；施放终结技后 -1 层（on_ultimate 在终结技结算后发射）."""
        eng = _make("131", 4, actions=(_BASIC_FIRE, _SKILL_FIRE, _ULT_FIRE))
        _cast(eng, "w", "t_skill")                       # 2 层
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert eng.state.actors["w"].modifiers["SET_131_NAV_STACK"].stacks == 1
        _ult(eng, "w", "t_ult")
        assert eng.state.actors["w"].modifiers["SET_131_NAV_STACK"].stacks == 0
        assert _panel(eng)["dmg_bonus"]["skill_dmg_boost"] == pytest.approx(0.0)

    def test_2pc_only_no_stacks(self):
        eng = _make("131", 2, actions=(_BASIC_FIRE, _SKILL_FIRE))
        assert "SET_131_NAV_STACK" not in eng.state.actors["w"].modifiers
        assert _panel(eng)["atk"] == pytest.approx(1000 * 1.12)
