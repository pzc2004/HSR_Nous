"""通用目标选择代数：pool → where → order_by → index → take → mode 一台求值器.

验证三层：存量选择器⇔代数等价（模板零改动的硬承诺）；代数直写（dict 全槽）；
random 的 zagreus/expected 双口径（roll 抽 N、expected 按序取前 N 不掷骰）；
taunt_or_random 的嘲讽覆盖、候选过滤与普通随机回退。
"""
from __future__ import annotations

import random as _random

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _mk_engine(mode=MODE_EXPECTED, seed=None):
    hero = Actor(actor_id="hero", name="hero", level=80,
                 stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100))
    allies = [Actor(actor_id=f"a{i}", name=f"队友{i}", level=80,
                    stats=StatBlock(atk=500 * i, spd=100, hp=1000 * i, max_energy=100))
              for i in (1, 2)]
    enemies = [Actor(actor_id=f"e{i}", name=f"敌{i}", actor_type="monster", level=80,
                     stats=StatBlock(atk=100 * i, spd=100, hp=2000 * i, max_toughness=100,
                                     weakness=["fire"]))
               for i in (1, 2, 3)]
    enc = Encounter(encounter_id="t", name="t", actors=[hero] + allies + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=mode, seed=seed, initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestHookSelectorEquivalence:
    """存量 hook 字符串选择器 ⇔ 目标代数：结果必须逐项一致（脱糖别名的等价电池）."""

    def test_self_and_allies(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        rt = eng._hooks._hook_target_states
        assert [s.actor.actor_id for s in rt("self", hero, {})] == ["hero"]
        assert [s.actor.actor_id for s in rt("all_allies", hero, {})] == ["hero", "a1", "a2"]
        assert [s.actor.actor_id for s in rt("other_allies", hero, {})] == ["a1", "a2"]
        assert [s.actor.actor_id for s in rt("all_enemies", hero, {})] == ["e1", "e2", "e3"]

    def test_enemy_first_and_highest_hp(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        rt = eng._hooks._hook_target_states
        assert rt("enemy_first", hero, {})[0].actor.actor_id == "e1"
        assert rt("highest_hp", hero, {})[0].actor.actor_id == "e3", "e3 hp 最大（2000×3）"

    def test_highest_hp_hit_pool(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            "highest_hp_hit", hero, {"hit_targets": ["e1", "e3"]})[0]
        assert picked.actor.actor_id == "e3"


class TestHookAlgebraDirect:
    def test_where_order_take(self):
        """代数直写：where $it 过滤 + order_by 降序 + take 2."""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "$it.hp > 2000", "order_by": "$it.hp", "take": 2},
            hero, {})
        assert [s.actor.actor_id for s in picked] == ["e2", "e3"], "过滤 e1 后按 hp 升序取前 2"

    def test_order_by_formation_and_reverse(self):
        """编队特殊键：formation 保持池序，-formation 反转，均可过编译闸."""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        for order, expected in (("formation", ["e1", "e2"]), ("-formation", ["e3", "e2"])):
            spec = {"pool": "enemies", "order_by": order, "take": 2}
            picked = eng._hooks._hook_target_states(spec, hero, {})
            assert [s.actor.actor_id for s in picked] == expected
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
            }], "模板 X")

    def test_index_selects_exact_position_after_filter_and_order(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        spec = {"pool": "enemies", "where": "$it.hp > 2000", "order_by": "$it.hp", "index": 1}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        picked = eng._hooks._hook_target_states(spec, hero, {})
        assert [state.actor.actor_id for state in picked] == ["e3"]
        assert eng._hooks._hook_target_states({"pool": "enemies", "index": 3}, hero, {}) == []
        with pytest.raises(ValueError, match="index 须为非负整数"):
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0,
                "target": {"pool": "enemies", "index": -1},
            }], "模板 X")

    def test_unselectable_pool_excludes_selectable_and_includes_battle_events(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        eng.state.actors["a1"].actor.summon_flags.update({
            "enemy_targetable": False, "ally_targetable": False})
        eng.state.actors["e1"].actor.summon_flags["enemy_targetable"] = False
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "create_battle_event", "event_id": 20001,
            "team": "TeamNeutral"}, {})
        spec = {"pool": "unselectable"}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        picked = eng._hooks._hook_target_states(spec, hero, {})
        assert [s.actor.actor_id for s in picked] == ["a1", "e1", "$battle_event:20001"]

    def test_unique_name_pool_passes_compiler_and_resolves_binding(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        spec = {"pool": "unique:Chosen"}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        assert eng._hooks._hook_target_states(spec, hero, {}) == []
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "set_dynamic_target", "dynamic_key": "Chosen",
            "target": "self", "scope": "unique_name"}, {})
        assert eng._hooks._hook_target_states(spec, hero, {}) == [hero]

    def test_private_dynamic_target_readable_by_owner(self):
        """actor 私有动态目标绑定（per-owner，非 unique_name）须被持有者读到——
        旧 unique_target_id 只读 $level，私有表只写不读静默空转（05_effects §actor
        私有动态目标绑定）；他人读同名不串，全局 unique_name 回落口径不变。"""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        spec = {"pool": "unique:Priv"}
        assert eng._hooks._hook_target_states(spec, hero, {}) == []
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "set_dynamic_target", "dynamic_key": "Priv",
            "target": {"pool": "enemies", "take": 1}, "owner": "self"}, {})
        resolved = eng._hooks._hook_target_states(spec, hero, {})
        assert [s.actor.actor_id for s in resolved] == ["e1"], "持有者读到私有绑定"
        other = eng.state.actors["e2"]
        assert eng._hooks._hook_target_states(spec, other, {}) == [], "私有绑定不串他人"

    def test_event_targets_includes_battle_event(self):
        """battle_event 实体不进 state.actors，$event.targets/hit_targets 须回落
        battle_event_actor（旧只查 state.actors 丢 $battle_event:* 目标）。"""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "create_battle_event", "event_id": 60001, "team": ""}, {})
        ev = eng.battle_events[60001]["actor_state"]
        for field in ("targets", "hit_targets"):
            resolved = eng._hooks._hook_target_states(
                f"$event.{field}", hero, {field: [ev.actor.actor_id]})
            assert [s.actor.actor_id for s in resolved] == [ev.actor.actor_id], field

    def test_modifier_namespace_battle_event_stacks(self):
        """$modifier 命名空间对 battle_event 目标须读其实例（旧查不到 → stacks 恒 0，
        与 stacks() 函数分叉）。"""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "create_battle_event", "event_id": 60001, "team": ""}, {})
        ev = eng.battle_events[60001]["actor_state"]
        eng._apply_modifier(ev, Modifier(
            modifier_id="m", name="m", modifier_type="debuff", duration=0, stacks=2))
        ctx = eng._hooks._hook_ctx(hero, {"modifier_id": "m", "target": ev.actor.actor_id})
        assert ctx["modifier"].stacks == 2, "battle_event 目标的 $modifier.stacks 须读实例"

    def test_target_predicates_accept_parsed_dict(self):
        """target_lists_intersect/target_in_selected 接受已解析 dict 规格——旧
        json.loads(str(dict)) 把 dict 转 Python repr（单引号/True）再解析必炸。"""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        funcs = eng._hooks._hook_functions(hero, {})
        spec = {"pool": "enemies"}
        assert funcs["target_in_selected"](spec, "e1") == 1.0
        assert funcs["target_in_selected"](spec, "hero") == 0.0
        assert funcs["target_lists_intersect"](spec, {"pool": "enemies", "take": 1}) == 1.0
        assert funcs["target_lists_intersect"]({"pool": "allies"}, {"pool": "enemies"}) == 0.0

    def test_target_unselectable_battle_event_matches_pool(self):
        """battle_event 实体：target_unselectable 谓词与 pool:'unselectable' 口径一致
        （旧谓词读 summon_flags 默认 True 返回 0，池按 actor_type 含它 → 矛盾）。"""
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        eng._hooks._run_hook_effect(hero, {
            "effect_type": "create_battle_event", "event_id": 60001, "team": ""}, {})
        ev = eng.battle_events[60001]["actor_state"]
        funcs = eng._hooks._hook_functions(hero, {})
        assert funcs["target_unselectable"](ev.actor.actor_id) == 1.0
        pool = eng._hooks._hook_target_states({"pool": "unselectable"}, hero, {})
        assert ev in pool, "池含 battle_event，谓词须同判不可选"

    def test_take_int_random_targets(self):
        """实例垫底（敌方 "Deals … to 3 random targets"）：take 3 + mode random——
        roll 同 seed 复现；expected 按序取前 N 不掷骰（确定化口径）."""
        spec = {"pool": "enemies", "take": 3, "mode": "random"}
        eng_r1 = _mk_engine(mode=MODE_ROLL, seed=42)
        eng_r2 = _mk_engine(mode=MODE_ROLL, seed=42)
        h1 = eng_r1.state.actors["hero"]
        h2 = eng_r2.state.actors["hero"]
        p1 = [s.actor.actor_id for s in eng_r1._hooks._hook_target_states(spec, h1, {})]
        p2 = [s.actor.actor_id for s in eng_r2._hooks._hook_target_states(spec, h2, {})]
        assert p1 == p2 and len(p1) == 3, "roll 同 seed 抽样逐项复现"
        eng_e = _mk_engine()
        he = eng_e.state.actors["hero"]
        pe = [s.actor.actor_id for s in eng_e._hooks._hook_target_states(spec, he, {})]
        assert pe == ["e1", "e2", "e3"], "expected 确定化：按序取前 N（不掷骰）"

    def test_taunt_or_random_respects_candidates_and_forced_taunt(self):
        spec = {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_random"}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        eng = _mk_engine(mode=MODE_ROLL, seed=42)
        attacker = eng.state.actors["e1"]
        candidates = [eng.state.actors[key] for key in ("hero", "a1", "a2")]
        eng.pipeline.rng = _random.Random(17)
        expected = _random.Random(17).choice(candidates)
        picked = eng._hooks._hook_target_states(spec, attacker, {})
        assert picked == [expected], "无嘲讽时按普通随机抽取，不按嘲讽值加权"

        eng._apply_modifier(attacker, Modifier(
            modifier_id="TAUNT", name="嘲讽", modifier_type="debuff",
            source_id="a2", forced_taunt=True, duration=2))
        assert eng._hooks._hook_target_states(spec, attacker, {}) == [candidates[2]]

        filtered = {**spec, "where": "$it.actor_id != 'a2'"}
        eng.pipeline.rng = _random.Random(17)
        expected = _random.Random(17).choice(candidates[:2])
        assert eng._hooks._hook_target_states(filtered, attacker, {}) == [expected], (
            "被过滤的嘲讽来源不能越过候选集")
        eng_expected = _mk_engine()
        assert eng_expected._hooks._hook_target_states(
            spec, eng_expected.state.actors["e1"], {}) == [eng_expected.state.actors["hero"]]
        with pytest.raises(ValueError, match="仅支持 take: 1"):
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0,
                "target": {**spec, "take": 2},
            }], "模板 X")

    def test_taunt_or_aggro_uses_weighted_fallback(self):
        spec = {"pool": "enemy_targets", "take": 1, "mode": "taunt_or_aggro"}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        eng = _mk_engine(mode=MODE_ROLL, seed=42)
        attacker = eng.state.actors["e1"]
        for actor_id, taunt in (("hero", 100.0), ("a1", 100.0), ("a2", 300.0)):
            eng.state.actors[actor_id].actor.stats.taunt = taunt
        calls = []
        original = eng._pick_ally_target

        def checked(owner, *, candidates=None, random_by_aggro=True):
            calls.append(random_by_aggro)
            return original(owner, candidates=candidates, random_by_aggro=random_by_aggro)

        eng._pick_ally_target = checked
        eng.pipeline.rng = _random.Random(17)
        assert eng._hooks._hook_target_states(spec, attacker, {}) == [eng.state.actors["a2"]]
        assert calls == [True]

        eng._apply_modifier(attacker, Modifier(
            modifier_id="TAUNT", name="嘲讽", modifier_type="debuff",
            source_id="hero", forced_taunt=True, duration=2))
        assert eng._hooks._hook_target_states(spec, attacker, {}) == [eng.state.actors["hero"]]
        with pytest.raises(ValueError, match="仅支持 take: 1"):
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0,
                "target": {**spec, "take": 2},
            }], "模板 X")

    def test_concat_preserves_order_and_duplicates(self):
        spec = {"concat": [
            {"pool": "enemies", "take": 1},
            {"pool": "enemies", "take": 2},
        ]}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        eng = _mk_engine()
        picked = eng._hooks._hook_target_states(spec, eng.state.actors["hero"], {})
        assert [state.actor.actor_id for state in picked] == ["e1", "e1", "e2"]
        outer = {**spec, "where": "$it.actor_id != 'e1'", "take": 1}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": outer,
        }], "模板 X")
        picked = eng._hooks._hook_target_states(outer, eng.state.actors["hero"], {})
        assert [state.actor.actor_id for state in picked] == ["e2"]
        with pytest.raises(ValueError, match="pool/include_"):
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0,
                "target": {**spec, "pool": "enemies"},
            }], "模板 X")

    def test_where_has_modifier_named(self):
        """实例垫底（按修饰符点名，1224 师父族）：where: has_modifier($it, 'M')."""
        eng = _mk_engine()
        eng._apply_modifier(eng.state.actors["e2"], Modifier(
            modifier_id="MARK", name="标记", modifier_type="debuff", duration=2))
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "has_modifier($it, 'MARK')", "take": 1}, hero, {})
        assert [s.actor.actor_id for s in picked] == ["e2"]

    def test_where_monster_rank_uses_enemy_policy(self):
        from types import SimpleNamespace
        eng = _mk_engine()
        eng._enemy_policies["e2"] = SimpleNamespace(monster_rank="Elite")
        eng._enemy_policies["e3"] = SimpleNamespace(monster_rank="LittleBoss")
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "monster_rank($it) >= 3"}, eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["e2", "e3"]
        eng._enemy_policies["e2"].monster_rank = "Minion"
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "monster_rank($it) < 4"}, eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["e1", "e2"]

    def test_where_monster_id_strips_stage_suffix(self):
        eng = _mk_engine()
        st = eng.state.actors.pop("e2")
        st.actor.actor_id = "2004023__stage_x"
        eng.state.actors[st.actor.actor_id] = st
        picked = eng._hooks._hook_target_states(
            {"pool": "enemies", "where": "monster_id($it) == '2004023'"},
            eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["2004023__stage_x"]

    def test_where_character_id_strips_stage_suffix(self):
        eng = _mk_engine()
        st = eng.state.actors.pop("hero")
        st.actor.actor_id = "1220__stage_x"
        eng.state.actors[st.actor.actor_id] = st
        picked = eng._hooks._hook_target_states(
            {"pool": "allies", "where": "character_id($it) == '1220'"}, st, {})
        assert [s.actor.actor_id for s in picked] == ["1220__stage_x"]

    def test_where_is_adjacent_excludes_primary_and_far_targets(self):
        eng = _mk_engine()
        picked = eng._hooks._hook_target_states({
            "pool": "allies", "where": "is_adjacent($it, $event.target)",
        }, eng.state.actors["hero"], {"target": "a1"})
        assert [s.actor.actor_id for s in picked] == ["hero", "a2"]

    def test_where_primary_and_caster_adjacent_targets(self):
        eng = _mk_engine()
        picked = eng._hooks._hook_target_states({
            "pool": "allies",
            "where": "($it.actor_id == $event.target or is_adjacent($it, $event.target))",
        }, eng.state.actors["hero"], {"target": "hero"})
        assert [s.actor.actor_id for s in picked] == ["hero", "a1"]
        picked = eng._hooks._hook_target_states({
            "pool": "enemies", "where": "is_adjacent($it, $self.actor_id)",
        }, eng.state.actors["e2"], {})
        assert [s.actor.actor_id for s in picked] == ["e1", "e3"]

    def test_where_action_disabled_reads_prevent_action_not_controlled(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        eng._apply_modifier(hero, Modifier(
            modifier_id="STOP", name="禁行", modifier_type="buff",
            prevent_action=True, duration=1))
        picked = eng._hooks._hook_target_states({
            "pool": "allies", "where": "action_disabled($it) and not controlled($it)",
        }, hero, {})
        assert [s.actor.actor_id for s in picked] == ["hero"]

    def test_where_actor_type_excludes_summons(self):
        eng = _mk_engine()
        eng.state.actors["a1"].actor.actor_type = "summon"
        picked = eng._hooks._hook_target_states({
            "pool": "allies", "where": "actor_type_of($it) != 'summon'",
        }, eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["hero", "a2"]

    def test_where_remove_servant_uses_summoner_id(self):
        eng = _mk_engine()
        eng.state.actors["a1"].actor.summoner_id = "hero"
        picked = eng._hooks._hook_target_states({
            "pool": "allies", "where": "not $it.summoner_id",
        }, eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["hero", "a2"]

    def test_order_by_shield_lowest(self):
        """$it.shield（当前护盾值=栈剩余合计——峥嵘"护盾值最低的我方目标"族，2026-09-08）：
        order_by 升序 + take 1 取最低；无盾=0 参与排序."""
        from hsr_nous.sim.state import ShieldInstance
        eng = _mk_engine()
        a1, a2 = eng.state.actors["a1"], eng.state.actors["a2"]
        a1.shields.append(ShieldInstance(
            shield_id="S1", name="盾1", remaining=500.0, source_id="hero"))
        a2.shields.append(ShieldInstance(
            shield_id="S2", name="盾2", remaining=100.0, source_id="hero"))
        a2.shields.append(ShieldInstance(
            shield_id="S3", name="盾3", remaining=50.0, source_id="hero"))
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states(
            {"pool": "allies", "order_by": "$it.shield", "take": 1}, hero, {})
        assert picked[0].actor.actor_id == "hero", "hero 无盾=0 最低"
        picked = eng._hooks._hook_target_states(
            {"pool": "allies", "where": "$it.shield > 0", "order_by": "$it.shield", "take": 2},
            hero, {})
        assert [s.actor.actor_id for s in picked] == ["a2", "a1"], (
            "有盾者按剩余合计升序（a2=150 < a1=500）")


class TestNestedCountAndDynamicTake:
    def test_nested_count_keeps_outer_owner_and_event(self):
        eng = _mk_engine()
        hero = eng.state.actors["hero"]
        picked = eng._hooks._hook_target_states({
            "pool": "allies",
            "where": ("count_selected('self', "
                      "'$it.actor_id == $self.actor_id and $it.actor_id == $event.target') == 1"),
        }, hero, {"target": "hero"})
        assert [s.actor.actor_id for s in picked] == ["hero", "a1", "a2"]

    def test_dynamic_take_evaluates_once_with_hook_owner(self):
        spec = {"pool": "allies", "take": "1 + count_selected('self', 'true')"}
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0, "target": spec,
        }], "模板 X")
        eng = _mk_engine()
        picked = eng._hooks._hook_target_states(spec, eng.state.actors["hero"], {})
        assert [s.actor.actor_id for s in picked] == ["hero", "a1"]

    @pytest.mark.parametrize(("take", "message"), [
        ("$it.hp", r"take.*\$it"),
        ("$self.atkk", "atkk"),
        ("$event.not_a_payload", "not_a_payload"),
    ])
    def test_dynamic_take_namespace_gates(self, take, message):
        with pytest.raises(ValueError, match=message):
            BuildCompiler()._validate_effects([{
                "effect_type": "deal_damage", "scaling_atk": 1.0,
                "target": {"pool": "allies", "take": take},
            }], "模板 X", event_ns="on_action")


class TestPolicyAlgebra:
    def _rt(self, eng):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        return eng.decision._apply_selector if isinstance(
            eng.decision, CompiledPolicyRuntime) else None

    def test_string_alias_equivalence(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        hero = eng.state.actors["hero"]
        assert rt._apply_selector("highest_hp", cands, hero, {}, eng).actor.actor_id == "e3"
        assert rt._apply_selector("lowest_hp_pct", cands, hero, {}, eng).actor.actor_id == "e1"
        assert rt._apply_selector("highest_atk", cands, hero, {}, eng).actor.actor_id == "e3"

    def test_legacy_dict_forms(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        cands[0].current_hp = 1000.0   # e1 残血（区分 hp_pct 档，防全员满血并列）
        cands[1].current_hp = 2500.0   # e2 半血+（>2000 档用）
        hero = eng.state.actors["hero"]
        assert rt._apply_selector({"type": "max", "key": "hp_pct"}, cands, hero, {}, eng).actor.actor_id == "e3"
        eng._apply_modifier(cands[0], Modifier(
            modifier_id="M2", name="标", modifier_type="debuff", duration=1))
        assert rt._apply_selector({"type": "has_modifier", "modifier_id": "M2"},
                                  cands, hero, {}, eng).actor.actor_id == "e1"
        assert rt._apply_selector({"type": "first", "condition": "target_hp > 2000"},
                                  cands, hero, {}, eng).actor.actor_id == "e2"

    def test_algebra_direct(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = _mk_engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        cands = [eng.state.actors[f"e{i}"] for i in (1, 2, 3)]
        hero = eng.state.actors["hero"]
        picked = rt._apply_selector({"order_by": "-$it.hp", "take": 1},
                                    cands, hero, {}, eng)
        assert picked.actor.actor_id == "e3"


class TestAlgebraCompileGates:
    def test_hook_dict_gates(self):
        bc = BuildCompiler()
        bad_pool = [{"effect_type": "deal_damage", "scaling_atk": 1.0,
                     "target": {"pool": "galaxy"}}]
        with pytest.raises(ValueError, match="非法 pool"):
            bc._validate_effects(bad_pool, "模板 X")
        with pytest.raises(ValueError, match="take 非法值"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"take": 0}}], "模板 X")
        with pytest.raises(ValueError, match="非法 mode"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"mode": "chaos"}}], "模板 X")
        with pytest.raises(ValueError, match="未知键"):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"pool": "enemies", "pooll": "x"}}], "模板 X")
        with pytest.raises(Exception):
            bc._validate_effects([{"effect_type": "deal_damage", "scaling_atk": 1.0,
                                   "target": {"where": "$it =!=> 1"}}], "模板 X")

    def test_hook_dict_valid_compiles(self):
        BuildCompiler()._validate_effects([{
            "effect_type": "deal_damage", "scaling_atk": 1.0,
            "target": {"pool": "enemies", "where": "$it.broken",
                       "order_by": "-$it.hp", "take": 2, "mode": "random"}}], "模板 X")

    def test_policy_dict_pool_rejected(self):
        with pytest.raises(ValueError, match="不允许 pool 键"):
            BuildCompiler()._compile_policy({
                "target_rules": [{"condition": "true",
                                  "selector": {"pool": "enemies", "take": 1}, "priority": 0}]})

    def test_policy_algebra_compiles(self):
        p = BuildCompiler()._compile_policy({
            "target_rules": [{"condition": "true",
                              "selector": {"order_by": "-$it.hp", "take": 1}, "priority": 0}]})
        assert p.target_rules


def test_it_ns_open_namespace_collision_explicit_wins():
    """$it NS 防撞：模板把 "max_hp" 当 stat_effects 自定义键（开放命名空间合法）时，
    显式面板键胜出且不 TypeError 炸（1208 打标实证——SimpleNamespace(**显式, **eff) 撞键）。"""
    from hsr_nous.sim.state import Modifier
    eng = _mk_engine()
    st = eng.state.actors["hero"]
    eng._apply_modifier(st, Modifier(
        modifier_id="X", name="x", modifier_type="buff", duration=0,
        stat_effects={"max_hp": 123.0}))
    from hsr_nous.sim.target_algebra import _it_namespace
    ns = _it_namespace(eng, st)["it"]
    assert ns.max_hp == float(eng.pipeline.effective_stats(st)["hp"]), "显式面板键胜"
    assert ns.actor_id == "hero"
