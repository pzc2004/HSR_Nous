"""行动级可用条件 available_if（03_actor §3.8.1 / 14_policy 合法性契约③）.

语义钉：条件不满足 = 不进合法行动集（政策/手动/召唤自动/终结技窗口同一漏斗，只读过滤）；
在场换技能 = 同槽双技互斥声明（纯合法性替换，非形态机）；运行期求值失败按不可用 + ⚠（B8
同口径）；编译期预编译 + $self 字段闸（hit_condition 同口径）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier


def _member(actions, resources=None):
    m = {"character_template": "inline", "actor_id": "hero", "name": "英雄", "level": 80,
         "base_stats": {"atk": 1000, "spd": 134, "hp": 3000, "max_energy": 100},
         "actions": actions}
    if resources:
        m["custom_resources"] = resources
    return m


_BASIC = {"action_id": "b", "name": "普攻", "action_type": "basic", "target_type": "single",
          "damage_type": "physical", "scaling": [{"atk": 1.0}]}
_SKILL_A = {"action_id": "s_a", "name": "常态战技", "action_type": "skill",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 1.5}], "skill_point_cost": 1,
            "available_if": "res__latch < 1"}
_SKILL_B = {"action_id": "s_b", "name": "强化战技", "action_type": "skill",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 2.0}], "skill_point_cost": 1,
            "available_if": "res__latch >= 1"}
_SKILL_TIER = {"action_id": "s_t", "name": "档位战技", "action_type": "skill",
               "target_type": "single", "damage_type": "physical",
               "scaling": [{"atk": 1.5}], "skill_point_cost": 1,
               "available_if": "res_charge >= 3"}
_ULT_GATED = {"action_id": "u", "name": "终结技", "action_type": "ultimate",
              "target_type": "single", "damage_type": "physical",
              "scaling": [{"atk": 3.0}], "energy_cost": 100,
              "available_if": "res__latch >= 1"}

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 20,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 400}}}


def _make(actions, *, resources=None, policy=None):
    build = {"build": {"team": [_member(actions, resources)],
                       "policy": policy or {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    eng = CombatEngine.from_compiled(compile_encounter(build, _STAGE),
                                     mode=MODE_EXPECTED, initial_sp=5,
                                     initial_energy_ratio=0.0)
    eng.setup()
    return eng


class _CapturePolicy:
    """手动路替身：逐决策点记录呈上的合法集（web 决策点/手动钩同源——
    引擎过滤后的 legal 即 choices），恒回首个合法."""

    ult_timing = "after_action"

    def __init__(self):
        self.seen: list[list[str]] = []

    def select_action(self, actor_state, legal, engine=None):
        self.seen.append([a.action_id for a in legal])
        return legal[0]

    def select_target(self, actor_state, action_type, candidates, engine=None):
        return None

    def select_ultimate(self, actor_state, ready, engine=None):
        return None

    def wait_segment(self, actor_state, action, seg_index, engine=None):
        return None


class TestSwapPairMutex:
    """在场换技能互斥：s_a（闩<1）↔ s_b（闩≥1）同槽双技声明."""

    def test_policy_picks_available_side(self):
        """政策路：闩 0 → 常态技在集；闩翻 1 → 强化技进集、常态技出集."""
        eng = _make([_BASIC, _SKILL_A, _SKILL_B],
                    resources={"_latch": {"max": 1}})
        state = eng.run()
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert uses and all("常态战技" in l for l in uses), f"闩 0 恒用常态技：{uses[:3]}"

        eng = _make([_BASIC, _SKILL_A, _SKILL_B],
                    resources={"_latch": {"max": 1}})
        eng.state.actors["hero"].resources["_latch"] = 1.0
        state = eng.run()
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert uses and all("强化战技" in l for l in uses), f"闩 1 恒用强化技：{uses[:3]}"

    def test_manual_choices_flip(self):
        """手动路：决策点呈上的 choices 随闩翻转进出（同槽另一侧恒不在集）."""
        eng = _make([_BASIC, _SKILL_A, _SKILL_B],
                    resources={"_latch": {"max": 1}})
        cap = _CapturePolicy()
        eng.decision = cap
        eng.step()                                # hero 首动决策（闩 0）
        assert cap.seen and "s_a" in cap.seen[0] and "s_b" not in cap.seen[0]
        eng.state.actors["hero"].resources["_latch"] = 1.0
        for _ in range(20):                       # 推进到 hero 下一决策点
            if eng.step() is None or len(cap.seen) >= 2:
                break
        assert len(cap.seen) >= 2 and "s_b" in cap.seen[-1] and "s_a" not in cap.seen[-1], (
            f"翻转后 choices 换技：{cap.seen}")

    def test_all_gated_falls_back_basic(self):
        """双技同闩外（不可达态）→ 合法集只剩普攻——条件闸不产空集崩溃."""
        eng = _make([_BASIC,
                     {**_SKILL_A, "available_if": "res__latch >= 2"},
                     {**_SKILL_B, "available_if": "res__latch >= 2"}],
                    resources={"_latch": {"max": 1}})
        state = eng.run()
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert uses and all("普攻" in l for l in uses)


class TestResourceTier:
    """资源档位判：res_charge >= 3."""

    def test_tier_boundary(self):
        eng = _make([_BASIC, _SKILL_TIER], resources={"charge": {"max": 9}})
        hero = eng.state.actors["hero"]
        legal_of = lambda: [a.action_id for a in eng._legal_with_available_if(
            hero, eng.actions_by_actor["hero"])]
        hero.resources["charge"] = 2.0
        assert legal_of() == ["b"], "2 < 3：档位技不在集"
        hero.resources["charge"] = 3.0
        assert legal_of() == ["b", "s_t"], "3 ≥ 3：档位技进集"


class TestUltimateWindow:
    def test_gated_ult_not_ready(self):
        """终结技窗口同闸：闩 0 → ready 空；闩 1 → ready 含终结技."""
        eng = _make([_BASIC, _ULT_GATED], resources={"_latch": {"max": 1}})
        hero = eng.state.actors["hero"]
        hero.current_energy = 100.0
        assert eng._ready_ultimates() == []
        hero.resources["_latch"] = 1.0
        assert [a.action_id for _st, a in eng._ready_ultimates()] == ["u"]


class TestSummonTurn:
    """召唤自动回合同闸：首行动被闸 → 自动退次合法（长夜月 1141307 族通道）."""

    def test_gated_first_action_skipped(self):
        from hsr_nous.sim.compile.compiled import SummonDef
        from hsr_nous.sim_schema.action import Action
        from hsr_nous.sim_schema.actor import Actor, StatBlock
        from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
        from hsr_nous.sim.policy_api import ScriptedPolicy

        hero = Actor(actor_id="hero", name="英雄", level=80,
                     stats=StatBlock(atk=1000, spd=134, hp=3000, max_energy=100))
        dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=20, max_toughness=9999, weakness=["physical"]))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=400))
        # 手工构造的 Action（无预编译产物）——引擎侧懒解析通道同测
        pet_actions = [
            Action(action_id="sp", name="条件技", action_type="memosprite_skill",
                   target_type="single", damage_type="physical",
                   scaling=[{"atk": 1.0}], available_if="res_charge >= 3"),
            Action(action_id="norm", name="常驻技", action_type="memosprite_skill",
                   target_type="single", damage_type="physical",
                   scaling=[{"atk": 0.5}])]
        actions = {"hero": [Action(action_id="b", name="普攻", action_type="basic",
                                   target_type="single", damage_type="physical",
                                   scaling=[{"atk": 1.0}])],
                   "hero_pet": pet_actions}
        sd = SummonDef(owner_id="hero",
                       actor=Actor(actor_id="hero_pet", name="宠物", actor_type="summon",
                                   level=80, stats=StatBlock(atk=500, spd=200, hp=2000,
                                                             max_energy=100),
                                   summoner_id="hero"),
                       inheritance="none")
        eng = CombatEngine(enc, actions_by_actor=actions,
                           policy=ScriptedPolicy(rotation=["basic"]),
                           mode=MODE_EXPECTED, initial_sp=5, initial_energy_ratio=0.0,
                           summon_defs={"hero_pet": sd})
        eng.setup()
        hero_st = eng.state.actors["hero"]
        pet = eng.summon_actor(hero_st, "hero_pet")
        # `res_charge` 读行动方自身资源（$self=宠物）——跨 actor 读忆师族走 resource_of，
        # 组合实例在模板回填（1413 忆灵技读忆师忆质）
        pet.resources["charge"] = 2.0
        eng._summon_turn(pet)
        assert any("常驻技" in l for l in eng.state.log[-3:]), "2 < 3：自动回合退常驻技"
        pet.resources["charge"] = 3.0
        eng._summon_turn(pet)
        assert any("条件技" in l for l in eng.state.log[-3:]), "3 ≥ 3：自动回合用条件技"


class TestScriptedGate:
    def test_scripted_cannot_bypass(self):
        """scripted 严格模式：脚本指定的行动被 available_if 闸 → 报"不在合法集"（与被锁同口径）."""
        eng = _make([_BASIC, _SKILL_A], resources={"_latch": {"max": 1}},
                    policy={"name": "p", "mode": "scripted",
                            "script": [{"turn": 1, "actor": "hero", "action": "s_a"},
                                       {"turn": 3, "actor": "hero", "action": "b"}]})
        eng.state.actors["hero"].resources["_latch"] = 1.0
        with pytest.raises(RuntimeError, match="不在合法集"):
            eng.run()


class TestEvalFailureB8:
    def test_undefined_name_unavailable_with_warn(self):
        """求值失败按不可用 + ⚠ 战斗日志（B8 同口径）——编译期放行裸 Name，运行期炸."""
        eng = _make([_BASIC,
                     {**_SKILL_A, "available_if": "res_undefined_var >= 1"}],
                    resources={"_latch": {"max": 1}})
        state = eng.run()
        uses = [l for l in state.log if "英雄 对 假人 使用" in l]
        assert uses and all("普攻" in l for l in uses), "求值失败=恒不可用 → 恒普攻"
        assert any("⚠" in l and "available_if" in l and "s_a" in l for l in state.log), (
            "⚠ 日志留痕（按不可用处理）")


class TestControlledFunction:
    """controlled(target)（§22.4）：合成 kind==control 口径（免疫判定同漏斗）."""

    def _controlled(self, eng, target):
        st = eng.state.actors["hero"]
        return eng._hooks._hook_functions(st)["controlled"](target)

    def test_control_kinds(self):
        eng = _make([_BASIC])
        hero = eng.state.actors["hero"]
        assert self._controlled(eng, "hero") == 0.0
        eng._apply_modifier(hero, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        assert self._controlled(eng, "hero") == 1.0, "control_kind 非空 → 受控"
        hero.modifiers.clear()
        eng._apply_modifier(hero, Modifier(
            modifier_id="DOM", name="支配", modifier_type="debuff",
            debuff_kind="control", duration=2))
        assert self._controlled(eng, "hero") == 1.0, "debuff_kind=control → 受控"
        hero.modifiers.clear()
        eng._apply_modifier(hero, Modifier(
            modifier_id="SHRED", name="减防", modifier_type="debuff", duration=2,
            stat_effects={"def_shred": 0.1}))
        assert self._controlled(eng, "hero") == 0.0, "普通 debuff → 不受控"
        assert self._controlled(eng, "nobody") == 0.0, "查无此人 → 0.0（缺省同口径）"

    def test_controlled_in_available_if(self):
        """组合实例：不受控才可用（长夜月 1141307 族表达式形态）."""
        act = {**_SKILL_A, "available_if": "!controlled('hero')"}
        eng = _make([_BASIC, act], resources={"_latch": {"max": 1}})
        hero = eng.state.actors["hero"]
        legal_of = lambda: [a.action_id for a in eng._legal_with_available_if(
            hero, eng.actions_by_actor["hero"])]
        assert "s_a" in legal_of()
        eng._apply_modifier(hero, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        assert "s_a" not in legal_of(), "受控 → 技能出集"


class TestCompileGates:
    def _compile(self, actions):
        build = {"build": {"team": [_member(actions)], "policy": {
            "name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]}}}
        return compile_encounter(build, _STAGE)

    def test_syntax_error_rejected(self):
        with pytest.raises(ValueError, match="available_if 表达式非法"):
            self._compile([{**_SKILL_A, "available_if": "res__latch >="}])

    def test_non_whitelist_function_rejected(self):
        with pytest.raises(ValueError, match="available_if 表达式非法"):
            self._compile([{**_SKILL_A, "available_if": "eval('1') >= 1"}])

    def test_self_ns_field_gate(self):
        with pytest.raises(ValueError, match="atkk"):
            self._compile([{**_SKILL_A, "available_if": "$self.atkk >= 1"}])

    def test_unknown_key_rejected(self):
        with pytest.raises(ValueError, match="未知键 'available_iff'"):
            self._compile([{**_SKILL_A, "available_iff": "true"}])

    def test_expr_precompiled_on_action(self):
        cp = self._compile([_BASIC, _SKILL_A])
        act = next(a for a in cp.actions_by_actor["hero"] if a.action_id == "s_a")
        assert act.available_if == "res__latch < 1"
        assert act.available_if_expr is not None, "编译期预编译产物随 Action 携带"
