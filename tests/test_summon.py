"""12_summon 忆灵/召唤体系 v1：生命周期 / 行为模式 / 能力闸 / 继承 / heal / 编译闸.

压缩要点（实现注）：triggered 行为 = 召唤物自身 hooks + trigger_action（复用 hook 机制，
不立新描述层）；召唤物 hooks 编译期注册（owner_id=召唤物 id），未入场时 HookRuntime
按 state.actors 查无即跳过，入场自然生效——无需运行时订阅。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.compile.compiled import SummonDef
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 编译闸
# ---------------------------------------------------------------------------

def _valid_summon_block():
    return {
        "s1": {
            "name": "测试灵",
            "inheritance": "full",
            "actions": [{"action_id": "s1_hit", "name": "打", "action_type": "basic",
                         "target_type": "single", "damage_type": "physical",
                         "scaling": [{"atk": 1.0}]}],
        }
    }


def _template_with_summons(summons):
    return {
        "actor_id": "t900", "name": "模板主", "level": 80,
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
        "actions": [{"action_id": "t900b", "name": "普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 1.0}]}],
        "summons": summons,
    }


class TestSummonsCompileGates:
    def _compile(self, summons):
        tpl = _template_with_summons(summons)
        hooks: list = []
        actions_out: dict = {}
        owner = Actor(actor_id="t900", name="模板主")
        return BuildCompiler()._compile_summons(tpl["summons"], owner, "t900", hooks, actions_out)

    def test_valid_block_compiles(self):
        defs = self._compile(_valid_summon_block())
        d = defs["s1"]
        assert d.owner_id == "t900" and d.inheritance == "full"
        assert d.actor.actor_type == "summon" and d.actor.summoner_id == "t900"
        assert d.actor.summon_flags == {}          # 默认全开（空 dict）

    def test_unknown_summon_key_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["behaviour"] = {}                # 错拼（spec 键是 behavior 族——v1 不收）
        with pytest.raises(ValueError, match="未知键 'behaviour'"):
            self._compile(blk)

    def test_unknown_capability_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["capabilities"] = {"fly": False}
        with pytest.raises(ValueError, match="未知键 'fly'"):
            self._compile(blk)

    def test_capability_non_bool_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["capabilities"] = {"av": 0}
        with pytest.raises(ValueError, match="须为 bool"):
            self._compile(blk)

    def test_inheritance_illegal_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["inheritance"] = "partial"       # spec 词表是 full/none/字段列表
        with pytest.raises(ValueError, match="inheritance 非法值"):
            self._compile(blk)

    def test_inheritance_none_requires_hp(self):
        blk = _valid_summon_block()
        blk["s1"]["inheritance"] = "none"
        with pytest.raises(ValueError, match="base_stats 未给 hp"):
            self._compile(blk)

    def test_inheritance_unknown_stat_field_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["inheritance"] = ["atk", "luck"]
        with pytest.raises(ValueError, match="未知 stat 字段"):
            self._compile(blk)

    def test_summon_actions_pass_action_gate(self):
        blk = _valid_summon_block()
        blk["s1"]["actions"][0]["scalingg"] = [{"atk": 1.0}]   # 错拼（_ACTION_KEYS 闸）
        with pytest.raises(ValueError, match="未知键 'scalingg'"):
            self._compile(blk)

    def test_summon_hooks_pass_hook_gate(self):
        blk = _valid_summon_block()
        blk["s1"]["hooks"] = [{"event": "on_skill_used", "effects": []}]   # 未登记事件
        with pytest.raises(ValueError):
            self._compile(blk)

    def test_summon_effect_param_gate(self):
        with pytest.raises(ValueError, match="未知键 'summon_idd'"):
            BuildCompiler()._validate_effects(
                [{"effect_type": "summon", "summon_idd": "s1"}], "模板 X")

    def test_template_top_key_summons_accepted(self):
        """summons 是角色模板合法顶层键（未进词表时写了编译期炸——回归钉）."""
        BuildCompiler()._compile_summons(_valid_summon_block(), Actor(actor_id="t900", name="x"),
                                         "t900", [], {})

    def test_max_hp_ratio_accepted(self):
        blk = _valid_summon_block()
        blk["s1"]["max_hp_ratio"] = 0.5
        d = self._compile(blk)["s1"]
        assert d.max_hp_ratio == 0.5
        # 缺省 = 0（不覆写）
        assert self._compile(_valid_summon_block())["s1"].max_hp_ratio == 0.0

    def test_max_hp_ratio_illegal_rejected(self):
        for bad in (0, -0.5, "0.5", True):
            blk = _valid_summon_block()
            blk["s1"]["max_hp_ratio"] = bad
            with pytest.raises(ValueError, match="max_hp_ratio 须为正数"):
                self._compile(blk)


# ---------------------------------------------------------------------------
# 引擎线束（inline 直构 + fixture 双通道）
# ---------------------------------------------------------------------------

def _char(cid="hero", atk=1000.0, spd=100.0, hp=3000.0):
    return Actor(actor_id=cid, name=cid, level=80,
                 stats=StatBlock(atk=atk, spd=spd, hp=hp, max_energy=100))


def _dummy(eid="e1", hp=1e9, spd=100.0):
    return Actor(actor_id=eid, name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=hp, spd=spd, max_toughness=9999, weakness=["physical"]))


def _summon_def(sid, owner_id, *, flags=None, inheritance="none", atk=500.0, spd=100.0, hp=2000.0,
                max_hp_ratio=0.0):
    return SummonDef(
        owner_id=owner_id,
        actor=Actor(actor_id=sid, name=sid, actor_type="summon", level=80,
                    stats=StatBlock(atk=atk, spd=spd, hp=hp, max_energy=100),
                    summoner_id=owner_id, summon_flags=flags or {}),
        inheritance=inheritance,
        max_hp_ratio=max_hp_ratio,
    )


def _engine(summon_defs=None, av=400.0, allies=1):
    actors = [_char()] + ([_char("ally2")] if allies > 1 else []) + [_dummy()]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    actions = {
        "hero": [Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                        damage_type="physical", scaling=[{"atk": 1.0}])],
        "ally2": [Action(action_id="b2", name="普攻", action_type="basic", target_type="single",
                         damage_type="physical", scaling=[{"atk": 1.0}])],
        "s_inde": [Action(action_id="ih", name="自立一击", action_type="basic",
                          target_type="single", damage_type="physical", scaling=[{"atk": 1.0}])],
        "s_trig": [Action(action_id="th", name="触发一击", action_type="follow_up",
                          target_type="single", damage_type="physical", scaling=[{"atk": 1.0}])],
    }
    eng = CombatEngine(enc, actions_by_actor=actions, policy=ScriptedPolicy(rotation=["basic"]),
                       mode=MODE_EXPECTED, seed=None, initial_sp=10, initial_energy_ratio=0.0,
                       summon_defs=summon_defs or {})
    eng.setup()
    return eng


class TestSummonLifecycle:
    def test_spawn_inherit_and_actor_enter(self):
        eng = _engine({"s_inde": _summon_def("s_inde", "hero", inheritance="full")})
        enters = []
        eng.bus.subscribe("actor_enter", lambda et, p, ctx: enters.append(p))
        hero = eng.state.actors["hero"]
        st = eng.summon_actor(hero, "s_inde")
        assert st.alive and st.actor.actor_type == "summon" and st.actor.summoner_id == "hero"
        assert math.isclose(st.actor.stats.atk, 1000.0)      # full 继承召唤者 Layer-1
        assert math.isclose(st.current_hp, 3000.0)           # 含 hp
        assert enters and enters[0]["reason"] == "summon"
        # 未登记 id 大声炸（不许静默）
        with pytest.raises(ValueError, match="未登记召唤物"):
            eng.summon_actor(hero, "ghost")

    def test_partial_inheritance(self):
        eng = _engine({"s1": _summon_def("s1", "hero", inheritance=("atk",), atk=500.0, hp=2000.0)})
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        assert math.isclose(st.actor.stats.atk, 1000.0)      # 列出字段继承
        assert math.isclose(st.actor.stats.hp, 2000.0)       # 其余用自带 base_stats

    def test_partial_inheritance_def_key_maps_to_def_(self):
        """inheritance 列表项 "def"（base_stats YAML 键名）→ StatBlock.def_（长夜月忆灵首实例）."""
        eng = _engine({"s1": _summon_def("s1", "hero", inheritance=("def",), atk=500.0, hp=2000.0)})
        eng.state.actors["hero"].actor.stats.def_ = 654.0
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        assert math.isclose(st.actor.stats.def_, 654.0), '"def" 键继承到 def_ 字段'
        assert math.isclose(st.actor.stats.atk, 500.0), "未列出字段用自带 base_stats"

    def test_max_hp_ratio_overrides_inherited_hp(self):
        """max_hp_ratio：hp = 召唤时刻召唤者有效生命上限 × 比例，其余字段按 inheritance 照常."""
        eng = _engine({"s1": _summon_def("s1", "hero", inheritance="full", max_hp_ratio=0.5)})
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        assert math.isclose(st.actor.stats.hp, 1500.0)       # 3000 × 0.5（覆盖 full 继承的 hp）
        assert math.isclose(st.current_hp, 1500.0)           # 初始 HP 同步取覆写后上限
        assert math.isclose(st.actor.stats.atk, 1000.0)      # atk 仍走 full 继承

    def test_max_hp_ratio_reads_effective_hp_at_summon(self):
        """口径 = 召唤时刻**有效**上限：召唤者已挂 hp_pct buff 时按 buff 后值定格."""
        eng = _engine({"s1": _summon_def("s1", "hero", inheritance="full", max_hp_ratio=0.5)})
        hero = eng.state.actors["hero"]
        eng._apply_modifier_spec(
            hero,
            {"modifier_id": "HP_UP", "name": "加血", "modifier_type": "buff",
             "stat_effects": {"hp_pct": 0.5}},
            hero)
        st = eng.summon_actor(hero, "s1")
        assert math.isclose(st.actor.stats.hp, 3000.0 * 1.5 * 0.5), (
            f"应为有效上限 4500 × 0.5：{st.actor.stats.hp}")

    def test_max_hp_ratio_none_inheritance_no_asset_mutation(self):
        """inheritance none + ratio：覆写不污染编译资产（二次召唤按新时刻重算）."""
        sdef = _summon_def("s1", "hero", inheritance="none", hp=2000.0, max_hp_ratio=0.5)
        eng = _engine({"s1": sdef})
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        assert math.isclose(st.actor.stats.hp, 1500.0)
        assert math.isclose(sdef.actor.stats.hp, 2000.0), "SummonDef 编译资产本体不得被覆写"

    def test_resummon_after_dismiss(self):
        eng = _engine({"s1": _summon_def("s1", "hero")})
        hero = eng.state.actors["hero"]
        eng.summon_actor(hero, "s1")
        assert eng.dismiss_summon_actor("s1") is True
        assert not eng.state.actors["s1"].alive
        assert eng.dismiss_summon_actor("s1") is False        # 重复解散 no-op
        st = eng.summon_actor(hero, "s1")
        assert st.alive, "离场后可重新召唤（旧 handle 已冻结，调度映射换新）"
        assert eng.summon_actor(hero, "s1") is st             # 已在场重复召唤 = 不动

    def test_owner_death_dismisses_summons(self):
        eng = _engine({"s1": _summon_def("s1", "hero"), "s2": _summon_def("s2", "hero")})
        exits = []
        eng.bus.subscribe("actor_exit", lambda et, p, ctx: exits.append(p))
        hero = eng.state.actors["hero"]
        eng.summon_actor(hero, "s1")
        eng.summon_actor(hero, "s2")
        hero.current_hp = 0
        eng._check_death(hero)
        assert not hero.alive
        assert not eng.state.actors["s1"].alive and not eng.state.actors["s2"].alive
        assert sum(1 for p in exits if p["reason"] == "dismiss") == 2

    def test_independent_summon_takes_own_turns(self):
        eng = _engine({"s_inde": _summon_def("s_inde", "hero", spd=100.0)}, av=150.0)
        eng.summon_actor(eng.state.actors["hero"], "s_inde")
        state = eng.run()
        assert any("自立一击" in l for l in state.log), "independent 召唤物应上行动条自动行动"

    def test_triggered_summon_never_on_bar(self):
        eng = _engine({"s_trig": _summon_def("s_trig", "hero", flags={"av": False})}, av=150.0)
        eng.summon_actor(eng.state.actors["hero"], "s_trig")
        starts = []
        eng.bus.subscribe("on_turn_start", lambda et, p, ctx: starts.append(p["actor"]))
        state = eng.run()
        assert "s_trig" not in starts, "av:false（triggered 型）永不上行动条"
        assert state.actors["s_trig"].alive, "冻结≠离场——单位仍在场可被机制驱动"


class TestSummonCapabilities:
    def test_enemy_untargetable_excluded_from_enemy_pools(self):
        eng = _engine({"s1": _summon_def("s1", "hero", flags={"enemy_targetable": False})})
        eng.summon_actor(eng.state.actors["hero"], "s1")
        picked = {eng._pick_ally_target(eng.state.actors["e1"]).actor.actor_id
                  for _ in range(20)}
        assert picked == {"hero"}, "enemy_targetable:false 永不进敌方选目标池"
        # 敌方 AoE 目标集同口径剔除
        monster_st = eng.state.actors["e1"]
        aoe = Action(action_id="ma", name="横扫", action_type="basic", target_type="aoe",
                     damage_type="physical", scaling=[{"atk": 1.0}])
        _primary, targets = eng._resolve_targets(monster_st, aoe)
        assert [t.actor.actor_id for t in targets] == ["hero"]

    def test_ally_untargetable_excluded_from_ally_pools(self):
        eng = _engine({"s1": _summon_def("s1", "hero", flags={"ally_targetable": False})})
        eng.summon_actor(eng.state.actors["hero"], "s1")
        pool = eng._hooks._hook_target_states("all_allies", eng.state.actors["hero"], {})
        assert "s1" not in [s.actor.actor_id for s in pool]

    def test_taunt_false_zero_weight(self):
        eng = _engine({"s1": _summon_def("s1", "hero", flags={"taunt": False})})
        eng.summon_actor(eng.state.actors["hero"], "s1")
        # 期望模式取最高权重：taunt:false 置 0 → 恒选 hero（taunt 默认 100）
        assert eng._pick_ally_target(eng.state.actors["e1"]).actor.actor_id == "hero"


class TestHealEffect:
    def test_heal_all_allies(self):
        eng = _engine(allies=2)
        for aid in ("hero", "ally2"):
            eng.state.actors[aid].current_hp = 1000.0
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        eff = {"effect_type": "heal", "target": "all_allies", "ratio": 0.1}
        eng._hooks._run_hook_effect(eng.state.actors["hero"], eff, {})
        assert eng.state.actors["hero"].current_hp > 1000.0
        assert eng.state.actors["ally2"].current_hp > 1000.0
        assert {g["target"] for g in gains} == {"hero", "ally2"}


# ---------------------------------------------------------------------------
# fixture 999903 全链路（编译 → 双灵入场 → independent 自动动 / triggered 代打）
# ---------------------------------------------------------------------------

class TestSummonerFixture:
    def _run(self, av=400.0):
        build = {"build": {"team": [{"character_template": "999903", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": av}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        return eng, eng.run()

    def test_dual_summon_battle_start(self):
        eng, state = self._run()
        assert state.actors["999903_inde"].alive and state.actors["999903_trig"].alive
        assert math.isclose(state.actors["999903_inde"].actor.stats.atk, 1000.0), "full 继承"
        assert math.isclose(state.actors["999903_trig"].actor.stats.atk, 500.0), "none 用自带"
        assert any("自立一击" in l for l in state.log), "independent 灵上行动条自动行动"
        assert any("触发一击" in l for l in state.log), "triggered 灵由自身 hook 代打"

    def test_triggered_never_takes_normal_turn(self):
        eng, state = self._run()
        # 触发灵 av:false：战斗日志/行动记录中无其普通回合（代打是 insert，不占回合）
        assert not any(l.startswith("AV") and "触发测试灵 使用" in l and "触发一击" not in l
                       for l in state.log)


# ---------------------------------------------------------------------------
# prefer_target "owner_last_target"（03_actor §3.8.1——忆灵"优先忆师最后攻击的敌人"族）
# ---------------------------------------------------------------------------

class TestPreferTarget:
    def _engine2(self, summon_defs):
        """双敌线束（区分优先命中与缺省首个）."""
        actors = [_char(), _dummy("e1"), _dummy("e2")]
        enc = Encounter(encounter_id="t", name="t", actors=actors,
                        termination=TerminationConfig(mode="fixed_av", max_action_value=400.0))
        actions = {
            "hero": [Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                            damage_type="physical", scaling=[{"atk": 1.0}])],
            "s1": [Action(action_id="s1_hit", name="打", action_type="memosprite_skill",
                          target_type="single", damage_type="physical",
                          scaling=[{"atk": 1.0}], prefer_target="owner_last_target")],
        }
        eng = CombatEngine(enc, actions_by_actor=actions, policy=ScriptedPolicy(rotation=["basic"]),
                           mode=MODE_EXPECTED, seed=None, initial_sp=10, initial_energy_ratio=0.0,
                           summon_defs=summon_defs)
        eng.setup()
        return eng

    def test_prefers_owner_last_target(self):
        eng = self._engine2({"s1": _summon_def("s1", "hero")})
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        eng._last_target_by_actor["hero"] = "e2"
        act = eng.actions_by_actor["s1"][0]
        primary, targets = eng._resolve_targets(st, act)
        assert primary is eng.state.actors["e2"] and targets == [primary], (
            "优先忆师最后攻击的敌人（越过缺省首个 e1）")

    def test_fallback_when_no_record_or_target_gone(self):
        eng = self._engine2({"s1": _summon_def("s1", "hero")})
        st = eng.summon_actor(eng.state.actors["hero"], "s1")
        act = eng.actions_by_actor["s1"][0]
        primary, _ = eng._resolve_targets(st, act)
        assert primary.actor.actor_id == "e1", "召唤者无攻击记录 → 回落统一决策链（缺省首个存活）"
        eng._last_target_by_actor["hero"] = "e2"
        eng.state.actors["e2"].alive = False
        primary, _ = eng._resolve_targets(st, act)
        assert primary.actor.actor_id == "e1", "记录目标已离场 → 回落缺省首个存活"

    def test_non_summon_action_unaffected(self):
        eng = self._engine2({"s1": _summon_def("s1", "hero")})
        eng._last_target_by_actor["hero"] = "e2"
        hero = eng.state.actors["hero"]
        act = eng.actions_by_actor["hero"][0]      # 无 prefer_target 的普攻
        primary, _ = eng._resolve_targets(hero, act)
        assert primary.actor.actor_id == "e1", "无 prefer_target 字段的行动走原决策链"

    def test_prefer_target_vocab_rejected(self):
        blk = _valid_summon_block()
        blk["s1"]["actions"][0]["prefer_target"] = "nearest"
        with pytest.raises(ValueError, match="prefer_target"):
            BuildCompiler()._compile_summons(
                blk, Actor(actor_id="t900", name="模板主"), "t900", [], {})
