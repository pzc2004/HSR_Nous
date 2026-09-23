"""引擎小件簇一：trigger_dot（强制结算 DoT）/ adjust_duration（时长±N）/ toughness_scope（削韧作用域）.

语义钉：trigger_dot 与自然跳伤共用结算单漏斗但不消耗 duration；adjust_duration ±N
≠ refresh（调到 0 按到期移除）；toughness_scope "all" 无视弱点、元素列表部分无视、
缺省 own_element 闸不变（植入弱点计入）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _engine(enemy_weakness=("physical",)):
    hero = Actor(actor_id="hero", name="hero", level=80,
                 stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100,
                                 crit_rate=0.0, crit_dmg=0.5))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=100,
                                  weakness=list(enemy_weakness)))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestTriggerDot:
    def test_retrigger_without_duration_consume(self):
        """强制结算：DoT 立即跳一次但 duration 不动（额外触发非走字）；事件照发."""
        eng = _engine()
        st = eng.state.actors["e1"]
        eng._apply_modifier(st, Modifier(
            modifier_id="DOT_SHOCK", name="触电", modifier_type="dot", debuff_kind="dot",
            duration=2, source_id="hero", dot_element="thunder",
            dot_ratio=1.0, dot_source_atk=1000.0))
        retrig = []
        eng.bus.subscribe("on_dot_retrigger", lambda et, p, ctx: retrig.append(p))
        hp_before = st.current_hp
        eng._hooks._run_hook_effect(eng.state.actors["hero"],
                                    {"effect_type": "trigger_dot", "target": "enemy_first"}, {})
        assert st.current_hp < hp_before, "强制结算立即跳伤"
        assert st.modifiers["DOT_SHOCK"].duration == 2, "强制触发不消耗 duration"
        assert retrig and retrig[0]["modifier_id"] == "DOT_SHOCK", "on_dot_retrigger 照发"


class TestAdjustDuration:
    def _mod(self):
        return Modifier(modifier_id="BUFF_X", name="增益", modifier_type="buff", duration=1)

    def test_extend_is_not_refresh(self):
        """+N 是在剩余上累加（1+2=3），不是重置满值（≠ refresh）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, self._mod())
        eng._hooks._run_hook_effect(st, {"effect_type": "adjust_duration",
                                         "modifier_id": "BUFF_X", "delta": 2}, {})
        assert st.modifiers["BUFF_X"].duration == 3

    def test_shrink_to_zero_expires(self):
        """-N 调到 0 按到期移除（reason=expire 同走字口径）."""
        eng = _engine()
        st = eng.state.actors["hero"]
        eng._apply_modifier(st, self._mod())
        removed = []
        eng.bus.subscribe("after_remove_modifier", lambda et, p, ctx: removed.append(p))
        eng._hooks._run_hook_effect(st, {"effect_type": "adjust_duration",
                                         "modifier_id": "BUFF_X", "delta": -5}, {})
        assert "BUFF_X" not in st.modifiers
        assert removed and removed[0]["reason"] == "expire"


class TestToughnessScope:
    def _fire_action(self, **kw):
        base = dict(action_id="s", name="斩", action_type="skill", target_type="single",
                    damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)
        base.update(kw)
        return Action(**base)

    def test_default_gate_unchanged(self):
        """缺省闸：无弱点属性不可削（旧行为不变）."""
        eng = _engine(enemy_weakness=["physical"])
        st = eng.state.actors["e1"]
        eng._apply_toughness_damage(st.actor, self._fire_action(), st)
        assert st.toughness == 100.0, "火属性打物理弱点怪：缺省闸不可削"

    def test_scope_all_ignores_weakness(self):
        """'all'：无视弱点任意属性可削（乱破/波提欧族）."""
        eng = _engine(enemy_weakness=["physical"])
        st = eng.state.actors["e1"]
        eng._apply_toughness_damage(st.actor, self._fire_action(toughness_scope="all"), st)
        assert st.toughness < 100.0

    def test_scope_list_partial(self):
        """元素列表：表内元素无视弱点可削；表外仍走默认闸."""
        eng = _engine(enemy_weakness=["physical"])
        st = eng.state.actors["e1"]
        eng._apply_toughness_damage(st.actor, self._fire_action(toughness_scope=["fire"]), st)
        assert st.toughness < 100.0
        st.toughness = 100.0
        eng._apply_toughness_damage(st.actor, self._fire_action(toughness_scope=["ice"]), st)
        assert st.toughness == 100.0, "列表外元素（ice 攻击不在 [ice] 里？——在才削，不在不削）"

    def test_compiler_gate(self):
        with pytest.raises(ValueError, match="toughness_scope 非法值"):
            BuildCompiler()._compile_action_list(
                [{"action_id": "s", "name": "x", "action_type": "skill", "target_type": "single",
                  "damage_type": "fire", "scaling": [{"atk": 1.0}], "toughness_scope": "alll"}], "t")


# ---------------------------------------------------------------------------
# 小件簇二：续段执行（段间全灭转波续打）/ assist 助战技
# ---------------------------------------------------------------------------

class TestContinueOnWipe:
    def test_segments_continue_into_next_wave(self):
        """3 段技：seg0 灭波 1 → 转波 → seg1/2 打在波 2（黄泉族砍穿波次；不立检查点模型）."""
        hero = Actor(actor_id="hero", name="hero", level=80,
                     stats=StatBlock(atk=1000, spd=150, hp=3000, max_energy=100,
                                     crit_rate=0.0, crit_dmg=0.5))
        d1 = Actor(actor_id="e1", name="假人壹", actor_type="monster", level=80,
                   stats=StatBlock(hp=100.0, spd=100, max_toughness=9999, weakness=["fire"]))
        d2 = Actor(actor_id="e2", name="假人贰", actor_type="monster", level=80,
                   stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["fire"]))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, d1],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70))
        action = Action(action_id="s", name="三连", action_type="skill", target_type="single",
                        damage_type="fire", scaling=[{"atk": 0.5}], toughness_dmg=10,
                        instances=3)
        eng = CombatEngine(enc, actions_by_actor={"hero": [action]},
                           policy=ScriptedPolicy(rotation=["skill"]), mode=MODE_EXPECTED,
                           seed=None, initial_sp=10, initial_energy_ratio=0.0,
                           wave_enemies={1: [d2]})
        eng.setup()
        hits = []
        eng.bus.subscribe("after_being_hit", lambda et, p, ctx: hits.append(p))
        eng.run()
        segs = sorted(h["seg_index"] for h in hits)
        assert segs == [0, 1, 2], f"3 段全部结算（转波续段）：{segs}"
        assert hits[0]["target"] == "e1" and hits[1]["target"] == "e2" and hits[2]["target"] == "e2", (
            "seg0 打波 1、seg1/2 转波打波 2")
        assert eng.state.actors["e2"].alive, "波 2 承受后续段存活（伤害按段各自结算）"


class TestAssist:
    def _assist(self, **kw):
        base = dict(action_id="ast", name="助战", action_type="assist", target_type="single",
                    damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)
        base.update(kw)
        return Action(**base)

    def _engine_with_quota(self, quota):
        from hsr_nous.sim.policy_api import legal_action_set
        eng = _engine()
        st = eng.state.actors["hero"]
        if quota is not None:
            st.resources["assist_n"] = float(quota)
        return eng, st

    def test_excluded_from_turn_legal_set(self):
        from hsr_nous.sim.policy_api import legal_action_set
        eng, st = self._engine_with_quota(3)
        legal = legal_action_set(st, [self._assist()], eng.state.skill_points)
        assert legal == [], "assist 是插入式行动——不进回合合法行动集"

    def test_quota_gate_and_consume(self):
        eng, st = self._engine_with_quota(2)
        action = self._assist(assist_cost_resource="assist_n")
        hits = []
        eng.bus.subscribe("after_being_hit", lambda et, p, ctx: hits.append(p))
        assert eng.fire_assist(st, action) is True
        assert eng.fire_assist(st, action) is True
        assert eng.fire_assist(st, action) is False, "额度耗尽即不可发动"
        assert st.resources["assist_n"] == 0.0 and len(hits) == 2, "每次发动消耗 1 额度"
        assert eng.state.turn_count == 0, "插入执行不占回合（turn_count 不动）"

    def test_unlimited_without_resource(self):
        eng, st = self._engine_with_quota(None)
        action = self._assist()
        for _ in range(3):
            assert eng.fire_assist(st, action) is True

    def test_non_assist_rejected(self):
        eng, st = self._engine_with_quota(None)
        with pytest.raises(ValueError, match="非 assist 行动"):
            eng.fire_assist(st, Action(action_id="b", name="普攻", action_type="basic",
                                       target_type="single", damage_type="physical",
                                       scaling=[{"atk": 1.0}]))


# ---------------------------------------------------------------------------
# 小件簇三：多韧性条（03_actor §3.10，虚韧性族）
# ---------------------------------------------------------------------------

class TestToughnessBars:
    def _boss(self):
        return Actor(actor_id="boss", name="多血条", actor_type="monster", level=80,
                     stats=StatBlock(hp=1e9, spd=100, max_toughness=100.0,
                                     toughness_bars=[50.0, 30.0], weakness=["fire"]))

    def _engine_boss(self):
        hero = Actor(actor_id="hero", name="hero", level=80,
                     stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100,
                                     crit_rate=0.0, crit_dmg=0.5))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, self._boss()],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED, seed=None, initial_sp=10,
                           initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def _fire(self, dmg=60):
        return Action(action_id="s", name="斩", action_type="skill", target_type="single",
                      damage_type="fire", scaling=[{"atk": 0.0}], toughness_dmg=dmg)

    def test_bar_sequence_and_exhaustion(self):
        """主条→追加 1→追加 2 按序打穿：on_break 条序 0/1/2；弱点击破状态仅末条（§4.5）."""
        eng = self._engine_boss()
        st = eng.state.actors["boss"]
        breaks = []
        eng.bus.subscribe("on_break", lambda et, p, ctx: breaks.append(p))
        eng._apply_toughness_damage(st.actor, self._fire(60), st)
        assert st.toughness == 40.0 and not st.broken
        eng._apply_toughness_damage(st.actor, self._fire(60), st)
        assert st.bar_index == 1 and st.toughness == 50.0, "主条破→追加 1 满值承接"
        assert not st.broken, "主条破≠弱点击破状态（§4.5 多层规则：末条才进入）"
        eng._apply_toughness_damage(st.actor, self._fire(60), st)
        assert st.bar_index == 2 and st.toughness == 30.0 and not st.broken, "追加 1 破→追加 2 承接（削 60 溢出 10 作废）"
        eng._apply_toughness_damage(st.actor, self._fire(40), st)
        assert st.broken and st.bar_index == 3 and st.bars_exhausted, "末条破→弱点击破状态 + 条尽"
        toughness_before = st.toughness
        eng._apply_toughness_damage(st.actor, self._fire(10), st)
        assert st.toughness == toughness_before, "条尽削韧不再生效"
        assert [b["bar_index"] for b in breaks] == [0, 1, 2], "每条击破可观测（on_break 条序）"

    def test_effects_and_delay_only_main_bar(self):
        """属性击破效果/推条仅末条；击破伤害每条照走（虚击破）."""
        eng = self._engine_boss()
        st = eng.state.actors["boss"]
        dmg0 = eng.state.total_damage
        for dmg in (60, 60, 60, 40):
            eng._apply_toughness_damage(st.actor, self._fire(dmg), st)
        dots = [m for m in st.modifiers.values() if m.modifier_type == "dot"]
        assert len(dots) <= 1, "属性击破 DoT 只末条施加（中间条不挂）"
        assert eng.state.total_damage - dmg0 > 0, "三条各结算一次击破伤害（虚击破照走）"

    def test_recovery_resets_to_main_bar(self):
        """恢复回 bar 0 满主条（追加条随下次主条破再循环）."""
        eng = self._engine_boss()
        st = eng.state.actors["boss"]
        for dmg in (60, 60, 60, 40):
            eng._apply_toughness_damage(st.actor, self._fire(dmg), st)
        assert st.bars_exhausted
        st.broken = False
        st.bar_index = 0
        st.toughness = float(st.actor.stats.max_toughness)   # 与恢复点同口径复位
        assert not st.bars_exhausted and st.toughness == 100.0

    def test_add_toughness_bar_effect(self):
        """add_toughness_bar：机制赋予运行期追加条（恢复不消失）."""
        eng = self._engine_boss()
        st = eng.state.actors["boss"]
        st.actor.stats.toughness_bars = []   # 清成单条，验证机制赋予路径
        eng._hooks._run_hook_effect(eng.state.actors["hero"],
                                    {"effect_type": "add_toughness_bar", "target": "enemy_first",
                                     "amount": 20}, {})
        assert st.extra_bars == [20.0]
        eng._apply_toughness_damage(st.actor, self._fire(120), st)
        assert st.bar_index == 1 and st.toughness == 20.0, "机制赋予条承接（主条破后切入）"

    def test_single_bar_behavior_unchanged(self):
        """无追加条 = 旧单条行为（主条破→条尽，不再可削）."""
        eng = _engine(enemy_weakness=["fire"])   # 单条假人 max_toughness=100，火弱点
        st = eng.state.actors["e1"]
        eng._apply_toughness_damage(st.actor, self._fire(120), st)
        assert st.broken and st.bars_exhausted
        before = st.toughness
        eng._apply_toughness_damage(st.actor, self._fire(10), st)
        assert st.toughness == before


# ---------------------------------------------------------------------------
# 小件簇三：致命判定通道（on_kill action_id 归属 / on_hp_lock 锁血钳制发射点）
# ---------------------------------------------------------------------------

class TestKillAttribution:
    def test_on_kill_action_id_action_path(self):
        """action 伤害致死：on_kill payload 带致死行动 id（"指定技能击杀"族过滤锚）."""
        eng = _engine()
        e1 = eng.state.actors["e1"]
        e1.current_hp = 1.0
        kills = []
        eng.bus.subscribe("on_kill", lambda et, p, ctx: kills.append(p))
        act = Action(action_id="a1", name="斩", action_type="basic", target_type="single",
                     damage_type="physical", scaling=[{"atk": 1.0}])
        eng._execute_action(eng.state.actors["hero"], act)
        assert not e1.alive
        assert kills and kills[0]["source"] == "hero" and kills[0]["target"] == "e1"
        assert kills[0]["action_id"] == "a1"

    def test_on_kill_hook_damage_inherits_trigger_action(self):
        """hook 伤害致死：继承触发事件的行动 id（死龙焰息 hook 承载伤害——归属 1140702 族）；
        非行动触发（dot 等）为 ""."""
        eng = _engine()
        e1 = eng.state.actors["e1"]
        e1.current_hp = 1.0
        kills = []
        eng.bus.subscribe("on_kill", lambda et, p, ctx: kills.append(p))
        eng._hooks._run_hook_effect(
            eng.state.actors["hero"],
            {"effect_type": "deal_damage", "name": "焰息", "target": "enemy_first",
             "damage_type": "physical", "amount": 10.0},
            {"action_id": "1140702", "actor": "hero"})
        assert kills and kills[0]["action_id"] == "1140702", "触发事件 action_id 继承"
        e1.current_hp = 1.0
        e1.alive = True
        kills.clear()
        eng._hooks._run_hook_effect(
            eng.state.actors["hero"],
            {"effect_type": "deal_damage", "name": "dot", "target": "enemy_first",
             "damage_type": "physical", "amount": 10.0},
            {})
        assert kills and kills[0]["action_id"] == "", "无行动来源为 ''"

    def test_on_hp_lock_emitted_at_clamp(self):
        """锁血钳制：伤害使 HP 归零被 hp_lock 钳 1 血——on_hp_lock 发射（source/target/action_id）."""
        eng = _engine()
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        e1.current_hp = 50.0
        locks = []
        eng.bus.subscribe("on_hp_lock", lambda et, p, ctx: locks.append(p))
        e1.current_hp = -10.0   # 伤害落账后 HP 归零（直接置值模拟结算后状态）
        eng._check_death(e1, "hero", action_id="1140702")
        assert e1.alive and e1.current_hp == 1.0, "锁血钳 1 不死"
        assert locks and locks[0]["source"] == "hero" and locks[0]["target"] == "e1"
        assert locks[0]["action_id"] == "1140702"

    def test_on_hp_lock_in_bus_contract(self):
        """on_hp_lock 已登记总线契约（hook event 编译闸同表——写了不炸）."""
        from hsr_nous.sim.bus import DEFAULT_CONTRACT
        assert DEFAULT_CONTRACT.get("on_hp_lock") == "emit"


# ---------------------------------------------------------------------------
# 小件簇四：faction 通道（in_group / count_team group 析取——昔涟 1415102 族，03_actor §3.1）
# ---------------------------------------------------------------------------

def _engine_faction():
    heroes = [
        Actor(actor_id="a_rem", name="记忆人", level=80, path="remembrance",
              stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
        Actor(actor_id="a_heir", name="黄金裔", level=80,
              groups=["faction:chrysos_heir"],
              stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
        Actor(actor_id="a_both", name="记忆裔", level=80, path="remembrance",
              groups=["faction:chrysos_heir"],
              stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
        Actor(actor_id="a_plain", name="路人", level=80,
              stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
        Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
              stats=StatBlock(hp=1e9, spd=100, max_toughness=100, weakness=["physical"])),
    ]
    enc = Encounter(encounter_id="t", name="t", actors=heroes,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=70))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10,
                       initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestFactionChannel:
    def test_in_group_path_auto_mapping(self):
        """path:<name> 按 path 字段自动映射（无需 groups 声明）."""
        eng = _engine_faction()
        fn = eng._hooks._hook_functions(eng.state.actors["a_rem"])
        assert fn["in_group"]("a_rem", "path:remembrance") == 1.0
        assert fn["in_group"]("a_rem", "path:harmony") == 0.0
        assert fn["in_group"]("a_rem", "faction:chrysos_heir") == 0.0, "未声明 faction 不命中"

    def test_in_group_declared_faction_and_fallback(self):
        """faction:xxx 查 actor.groups 声明表；查无 actor 按 0.0（false-y 安全缺省）."""
        eng = _engine_faction()
        fn = eng._hooks._hook_functions(eng.state.actors["a_rem"])
        assert fn["in_group"]("a_heir", "faction:chrysos_heir") == 1.0
        assert fn["in_group"]("a_plain", "faction:chrysos_heir") == 0.0
        assert fn["in_group"]("ghost", "faction:chrysos_heir") == 0.0
        assert fn["in_group"]("e1", "faction:chrysos_heir") == 0.0

    def test_count_team_disjunct_dedup(self):
        """path+group 同给=析取（命途匹配或分组命中）；双命中只计 1 次（官方"黄金裔或记忆"读法）."""
        eng = _engine_faction()
        assert eng._count_team_group(path="remembrance") == 2.0, "单 path：a_rem + a_both"
        assert eng._count_team_group(group="faction:chrysos_heir") == 2.0, "单 group：a_heir + a_both"
        assert eng._count_team_group(path="remembrance", group="faction:chrysos_heir") == 3.0, (
            "析取：a_rem + a_heir + a_both（a_both 双命中不重复计）")
        assert eng._count_team_path("remembrance") == 2.0, "旧单漏斗回归不变"

    def test_count_team_includes_dead_roster(self):
        """含阵亡编成口径（"队伍中"与存活无关）."""
        eng = _engine_faction()
        eng.state.actors["a_heir"].alive = False
        assert eng._count_team_group(group="faction:chrysos_heir") == 2.0

    def test_groups_compile_gate_and_member_override(self):
        """groups 形状闸（非字符串列表编译期炸）+ member 级声明进 Actor（模板可被 member 覆盖）."""
        from hsr_nous.sim.compile import compile_encounter
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 70}}}

        def _build(groups):
            return {"build": {"team": [
                {"actor_id": "h", "name": "h", "inline": True, "groups": groups,
                 "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
                 "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "physical",
                              "scaling": [{"atk": 1.0}]}]}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "true", "action": "basic", "priority": 0}]}}}

        with pytest.raises(ValueError, match="groups 须为字符串列表"):
            compile_encounter(_build("chrysos_heir"), stage)
        compiled = compile_encounter(_build(["faction:chrysos_heir"]), stage)
        actor = next(a for a in compiled.to_encounter().actors if a.actor_id == "h")
        assert actor.groups == ["faction:chrysos_heir"], "member 级 groups 声明落到 Actor"


# ---------------------------------------------------------------------------
# 小件簇五：动态元素族（element_of / who_has / damage_type 表达式二态——丹恒•腾荒 1414 同袍族）
# ---------------------------------------------------------------------------

class TestDynamicElement:
    def _eng(self):
        hero = Actor(actor_id="dh", name="丹恒", level=80, element="physical",
                     stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100))
        ally = Actor(actor_id="ally", name="火攻手", level=80, element="fire",
                     stats=StatBlock(atk=2000, spd=90, hp=3000, max_energy=100))
        dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=100, max_toughness=9999,
                                      weakness=["physical"]))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, ally, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED, seed=None, initial_sp=10,
                           initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def test_element_of_and_who_has(self):
        eng = self._eng()
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="TONGPAO", name="同袍", modifier_type="buff", duration=0))
        fn = eng._hooks._hook_functions(eng.state.actors["dh"])
        assert fn["who_has"]("TONGPAO") == "ally", "反查持有者"
        assert fn["who_has"]("NOPE") == "", "无持有者返回 ''"
        assert fn["element_of"]("ally") == "fire"
        assert fn["element_of"](fn["who_has"]("TONGPAO")) == "fire", "复合：同袍元素"
        assert fn["element_of"]("ghost") == "", "查无返回 ''"

    def test_damage_type_expression_resolved(self):
        """damage_type 表达式：求值为持有者元素（fire）——on_hp_decrease 携带动态属性."""
        eng = self._eng()
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="TONGPAO", name="同袍", modifier_type="buff", duration=0))
        hits = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: hits.append(p))
        eng._hooks._run_hook_effect(
            eng.state.actors["dh"],
            {"effect_type": "deal_damage", "name": "同袍附加", "target": "enemy_first",
             "damage_type": "element_of(who_has('TONGPAO'))",
             "category": "additional", "amount": "0.8 * stat_of(who_has('TONGPAO'), 'atk')"},
            {})
        assert hits and hits[0]["damage_type"] == "fire", "动态属性随同袍"
        assert hits[0]["action_type"] == "additional", "附加伤害类别（不吃类型限定增伤）"
        # 火非弱点假人：0.8×2000×0.5(def)×0.8(res)×0.9(未击破)×1.025(期望暴击 0.05/0.5)
        assert math.isclose(hits[0]["amount"], 1600.0 * 0.5 * 0.8 * 0.9 * 1.025, rel_tol=1e-9)

    def test_damage_type_expression_invalid_result_raises(self):
        """求值结果非合法元素（目标未声明 element → ''）运行期炸——不静默吞."""
        eng = self._eng()
        eng.state.actors["ally"].actor.element = ""   # 未声明
        with pytest.raises(ValueError, match="非合法元素"):
            eng._hooks._run_hook_effect(
                eng.state.actors["dh"],
                {"effect_type": "deal_damage", "name": "x", "target": "enemy_first",
                 "damage_type": "element_of('ally')", "amount": 1.0},
                {})

    def test_damage_type_compile_gate(self):
        """编译闸：元素字面量直用；词表外按表达式预编译（错拼/非法即炸）."""
        from hsr_nous.sim.compile.build_compiler import BuildCompiler
        BuildCompiler()._validate_effects(
            [{"effect_type": "deal_damage", "target": "enemy_first",
              "damage_type": "element_of(who_has('TONGPAO'))", "amount": 1.0}], "模板 X")
        with pytest.raises(ValueError, match="damage_type 非法"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "deal_damage", "target": "enemy_first",
                  "damage_type": "quanttum", "amount": 1.0}], "模板 X")

    def test_element_member_gate(self):
        """element 顶层键：词表闸（错拼编译期炸）+ 落到 Actor."""
        from hsr_nous.sim.compile import compile_encounter
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 70}}}

        def _build(element):
            return {"build": {"team": [
                {"actor_id": "h", "name": "h", "inline": True, "element": element,
                 "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
                 "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "physical",
                              "scaling": [{"atk": 1.0}]}]}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "true", "action": "basic", "priority": 0}]}}}

        with pytest.raises(ValueError, match="element 非法值"):
            compile_encounter(_build("quanttum"), stage)
        compiled = compile_encounter(_build("Fire"), stage)
        actor = next(a for a in compiled.to_encounter().actors if a.actor_id == "h")
        assert actor.element == "fire", "element 落 Actor（大小写归一小写）"


# ---------------------------------------------------------------------------
# 小件簇五：exit_state hook effect（形态退出模板驱动通道，1510 拓星者首实例）
# + damageable_enemies（"敌方无法被继续削减生命值"判定源）
# ---------------------------------------------------------------------------

class TestExitStateEffect:
    def test_exit_state_hook_effect(self):
        """exit_state effect：退出当前形态（摘标记/state_config 清空/on_state_change
        广播，走 engine.exit_state 单漏斗）；无形态安全空转."""
        from hsr_nous.sim.state import StateConfig
        eng = _engine()
        cfg = StateConfig(state="starblazer", name="拓星者",
                          replaces_actions={"basic": ["b_enh"]}, locked_actions=["skill"])
        eng.register_state_config("hero", cfg, entry_action_id="ult_x")
        st = eng.state.actors["hero"]
        eng.enter_state(st, cfg)
        assert st.state_config is cfg and "STATE_starblazer" in st.modifiers
        events = []
        eng.bus.subscribe("on_state_change", lambda et, p, ctx: events.append(p))
        eng._hooks._run_hook_effect(st, {"effect_type": "exit_state"}, {})
        assert st.state_config is None and "STATE_starblazer" not in st.modifiers
        assert events and events[0]["from_state"] == "starblazer" and events[0]["to_state"] is None
        eng._hooks._run_hook_effect(st, {"effect_type": "exit_state"}, {})
        assert st.state_config is None, "无形态安全空转"

    def test_exit_state_compile_gate(self):
        """编译闸：exit_state 已登记 effect_types 白名单 + 参数键词表（reason）."""
        from hsr_nous.sim_schema.effect_types import ENGINE_EFFECT_TYPES
        assert "exit_state" in ENGINE_EFFECT_TYPES
        BuildCompiler()._validate_effects(
            [{"effect_type": "exit_state", "reason": "test"}], "模板 X")
        with pytest.raises(ValueError, match="未知 effect_type"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "exit_stat"}], "模板 X")
        with pytest.raises(ValueError, match="未知键"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "exit_state", "reason2": "x"}], "模板 X")


class TestDamageableEnemies:
    def test_damageable_enemies_excludes_hp_lock(self):
        """damageable_enemies：存活且无 hp_lock 件计数——锁血敌人不再可削减
        （与 enemies_alive 分工：存活计数 vs 可削减计数，1510 判定源）."""
        eng = _engine()
        e1 = eng.state.actors["e1"]
        fns = eng._hooks._hook_functions(eng.state.actors["hero"])
        assert fns["damageable_enemies"]() == 1.0
        eng._apply_modifier(e1, Modifier(
            modifier_id="LOCK", name="锁血", modifier_type="buff", duration=0, hp_lock=True))
        assert fns["damageable_enemies"]() == 0.0, "锁血敌人不可再削减"
        assert fns["enemies_alive"]() == 1.0, "enemies_alive 仍计存活"
        e1.alive = False
        assert fns["damageable_enemies"]() == 0.0 and fns["enemies_alive"]() == 0.0
