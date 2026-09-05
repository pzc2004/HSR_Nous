"""hook DSL 化 v1：模板 hooks 块 → 编译 → 引擎订阅执行（四执行体）.

dogfood：白厄大行迹 1408101（战斗开始/变身结束获火种）+ 1408103（攻击叠层）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


@pytest.fixture(scope="module")
def engine_factory():
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1600}}}

    def make(seed_offset=0.0, policy_action="skill"):
        eng = CombatEngine.from_compiled(
            compile_encounter(
                {"build": {"team": [{"character_template": "1408", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": policy_action, "priority": 0}]}}},
                stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        if seed_offset:
            eng.state.actors["1408"].resources["fire_seed"] += seed_offset
        return eng
    return make


class TestHookDsl:
    def test_battle_start_seed_gain(self, engine_factory):
        """1408101：战斗开始经模板 hook 获得 3 火种（无 Python 注册）."""
        eng = engine_factory()
        st = eng.state.actors["1408"]
        assert math.isclose(st.resources["fire_seed"], 3.0), (
            f"开局火种应=模板 hook 给的 3：{st.resources}"
        )

    def test_heroism_stacks_on_enter_and_exit(self, engine_factory):
        """1408103：进战叠 1 层照见英雄本色（atk_pct 0.5）；变身结束再叠（cap 2）."""
        eng = engine_factory(seed_offset=9.0)  # 开局 3(钩)+预置 9=12 → T1 战技即可变身
        state = eng.run()
        st = state.actors["1408"]
        mod = st.modifiers.get("TRACE_1408103")
        assert mod is not None, "照见英雄本色应挂上"
        assert mod.stacks >= 1
        assert math.isclose(mod.stat_effects.get("atk_pct", 0.0), 0.5)

    def test_exit_seed_refund_via_hook(self, engine_factory):
        """1408101 变身结束返还 1 火种（模板 hook，与 Python 银行 hook 独立共存）."""
        eng = engine_factory(seed_offset=9.0)  # 开局 3(钩)+预置 9=12 → T1 战技即可变身
        gains = []
        eng.bus.subscribe("on_resource_gain", lambda et, p, ctx: gains.append(p))
        state = eng.run()
        assert any("退出形态 卡厄斯兰那" in l for l in state.log)
        # 断言返还事件本身（+1 火种唯一来源），不盯终局余额——修正战技点经济后
        # （基础普攻官方 +1 点）战技可持续，可能二次变身把返还+积蓄一并吃掉，余额断言假红
        assert any(p.get("resource_id") == "fire_seed" and p.get("amount") == 1
                   for p in gains), f"退出返还未发射：{gains}"

    def test_hook_condition_false_no_effect(self, engine_factory):
        """条件不满足不触发：未变身时 on_state_change 的 from_state 过滤."""
        # 只普攻策略：火种恒 3（开局钩给的）永远不够 12 → on_state_change 永不发 → 无返还。
        # 修正战技点经济后原"全程战技"场景靠普攻回点可持续放战技会真变身——
        # "不变身"前提必须靠策略钉死，不能靠 SP 枯竭
        eng = engine_factory(policy_action="basic")
        gains = []
        eng.bus.subscribe("on_resource_gain", lambda et, p, ctx: gains.append(p))
        state = eng.run()
        assert not any("进入形态" in l for l in state.log)
        assert not any(p.get("resource_id") == "fire_seed" and p.get("amount") == 1
                       for p in gains)

    def test_entry_ult_consumes_turn_via_before_window(self, engine_factory):
        """入口技"结束本回合"协议：before 窗口放变身 → 本回合行动阶段整体跳过——
        变身那一动不得再执行基础形态行动（曾 bug：窗口放完变身还退回默认放技能）."""
        eng = engine_factory(seed_offset=9.0)   # 3+9=12 火种 → T1 即可变身
        eng.decision.ult_timing = "before_action"   # 窗口前移：变身发生在行动决策前
        state = eng.run()
        log = state.log
        assert any("进入形态 卡厄斯兰那" in l for l in log), "应已变身"
        # 变身那一动（同 AV）不得再执行基础形态行动（曾 bug：窗口放完变身还退回默认放技能）；
        # 退形态后回到基础形态用基础技能是合法的——只钉变身当动
        transform_av = next(l.split(":")[0] for l in log if "进入形态 卡厄斯兰那" in l)
        assert not any(l.startswith(transform_av) and "黎明创世，地辟天开" in l for l in log), (
            f"回合消耗协议失效：变身当动（{transform_av}）仍执行了基础战技")
        # 战斗照常走完（倒计时回合/最后一击在案）
        assert any("最后一击" in l or "退出形态" in l for l in log)


def test_after_apply_modifier_payload_carries_type_and_stat():
    """23 章 §23.4 死示例修复钉死：after_apply_modifier payload 必须带 modifier_type/stat——
    示例 condition `$event.modifier_type == 'debuff' && $event.target != $self`
    修复前 payload 只发 {modifier_id,target,source}，条件恒不触发."""
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=2000, hp=2000, spd=200, crit_rate=0.5,
                                 crit_dmg=1.0, max_energy=100))
    enemy = Actor(actor_id="e1", name="精英", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=100, max_toughness=120.0, weakness=["fire"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={}, mode=MODE_EXPECTED,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    seen = []
    eng.bus.subscribe("after_apply_modifier", lambda et, p, ctx: seen.append(p))
    eng._apply_modifier(eng.state.actors["hero"], Modifier(
        modifier_id="VULN", name="易伤", modifier_type="debuff", duration=2,
        stat_effects={"vulnerability": 0.1}, source_id="e1"))
    assert seen, "after_apply_modifier 应发射"
    payload = seen[-1]
    assert payload["modifier_type"] == "debuff", f"payload 缺 modifier_type：{payload}"
    assert "vulnerability" in payload["stat"], f"payload stat 应为受影响属性键列表：{payload}"
    # 23 章 §23.4 示例 condition 全文必须能命中（$self = 被挂者 hook 主）
    cond = eng._expr.compile("$event.modifier_type == 'debuff' && $event.target != $self")
    assert bool(eng._expr.evaluate(cond, eng._hook_ctx(eng.state.actors["hero"], payload))) is True
    # 反例：buff 不命中 debuff 过滤
    eng._apply_modifier(eng.state.actors["hero"], Modifier(
        modifier_id="ATK_UP", name="攻击提升", modifier_type="buff", duration=2,
        stat_effects={"atk": 100.0}, source_id="e1"))
    payload_buff = seen[-1]
    assert bool(eng._expr.evaluate(cond, eng._hook_ctx(eng.state.actors["hero"], payload_buff))) is False


def test_immediate_action_and_grant_extra_turn_resolve_event_target():
    """1313 拉条 bug 钉死：grant_extra_turn/immediate_action 的 target 必须走统一解析
    （曾恒授 hook 携带者——星期日战技拉白厄变拉自己）。

    immediate_action = 立即行动原语（剩余距离置 0 到顶、无视推条，普通回合口径——
    星期日/布洛妮娅战技族），与 grant_extra_turn（插入式额外回合）语义不同。
    """
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    sunday = Actor(actor_id="1313", name="星期日", level=80,
                   stats=StatBlock(atk=500, hp=2000, spd=120, crit_rate=0.05,
                                   crit_dmg=0.5, max_energy=100))
    phainon = Actor(actor_id="1408", name="白厄", level=80,
                    stats=StatBlock(atk=500, hp=2000, spd=100, crit_rate=0.05,
                                    crit_dmg=0.5, max_energy=100))
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=80, max_toughness=120.0, weakness=["physical"]))
    enc = Encounter(encounter_id="t", name="t", actors=[sunday, phainon, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=500))
    eng = CombatEngine(enc, actions_by_actor={}, mode=MODE_EXPECTED,
                       initial_sp=3, initial_energy_ratio=0.0)
    eng.setup()
    st = eng.state.actors["1313"]
    payload = {"target": "1408", "source": "1313", "action_id": "131302"}

    # immediate_action → 目标剩余距离置 0（正常队首），不是 hook 携带者
    eng._run_hook_effect(st, {"effect_type": "immediate_action", "target": "$event.target"},
                         payload, {})
    first_normal = next(a for a, kind, _ in eng.scheduler.preview(3) if kind == "normal")
    assert first_normal.actor_id == "1408", (
        f"立即行动应把 1408 拉到正常队首，实际={first_normal.actor_id}")

    # grant_extra_turn target=$event.target → 额外回合授目标（插队首），不授携带者
    eng._run_hook_effect(st, {"effect_type": "grant_extra_turn", "target": "$event.target"},
                         payload, {})
    top = eng.scheduler.preview(5)[0]
    assert top[0].actor_id == "1408" and top[1] == "normal_extra", (
        f"额外回合应授 1408（normal_extra 插队首），实际={top[0].actor_id}/{top[1]}")

    # 缺省 target=self：再现/青雀族原行为不变（授 hook 携带者）
    eng._run_hook_effect(st, {"effect_type": "grant_extra_turn"}, payload, {})
    queued = [(a.actor_id, k) for a, k, _ in eng.scheduler.preview(6)]
    assert ("1313", "normal_extra") in queued, f"缺省 self 应授携带者 1313：{queued}"


def test_banished_units_frozen_no_hooks_no_ult():
    """放逐边界（owner 裁决钉死）：全局机制（军功充能/奇袭族）放逐照跑，
    个人能量冻结不涨，终结技禁放（无法行动）。
    案例：白厄变身放逐刻律德菈——充能 hook 照跑（游戏里充能挂在军功体系/白厄底下），
    但她的能量不再涨、就绪清单没有她。"""
    import types

    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.action import Action
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    hero = Actor(actor_id="hero", name="测试员甲", level=80,
                 stats=StatBlock(atk=500, hp=2000, spd=120, crit_rate=0.05,
                                 crit_dmg=0.5, max_energy=100))
    ally = Actor(actor_id="ally", name="测试员乙", level=80,
                 stats=StatBlock(atk=500, hp=2000, spd=100, crit_rate=0.05,
                                 crit_dmg=0.5, max_energy=50))
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=80, max_toughness=120.0, weakness=["fire"]))
    ult = Action(action_id="ally_ult", name="测试大", action_type="ultimate",
                 target_type="aoe", damage_type="fire", scaling=[{"atk": 1.0}], energy_cost=50)
    enc = Encounter(encounter_id="t", name="t", actors=[hero, ally, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=500))
    eng = CombatEngine(enc, actions_by_actor={"ally": [ult]}, mode=MODE_EXPECTED,
                       initial_sp=3, initial_energy_ratio=0.0)
    eng.setup()
    st = eng.state.actors["ally"]
    # 双 hook：能量 hook（放逐应冻结）+ 资源 hook（军功充能族，放逐照跑）
    eng._compiled_hooks = [types.SimpleNamespace(
        event="on_action", owner_id="ally", condition_expr=None,
        effects=[{"effect_type": "gain_energy", "target": "self", "amount": 5},
                 {"effect_type": "gain_resource", "resource_id": "test_charge", "amount": 1}])]
    eng._hooks._subscribe_compiled_hooks()

    st.banished = True
    st.current_energy = 50.0   # 满能放逐：就绪清单必须空（无法行动，禁开大）
    assert eng._ready_ultimates() == [], "放逐单位不应进终结技就绪清单"
    st.current_energy = 30.0
    eng.bus.emit("on_action", {"actor": "hero", "action_type": "basic",
                               "actor_type": "character"}, eng.state)
    assert st.current_energy == 30.0, "放逐后个人能量应冻结不涨"
    assert st.resources.get("test_charge", 0.0) == 1.0, (
        "放逐后全局机制（军功充能族 hook）应照跑——刻律德菈被放逐充能照生效（owner 实战口径）")

    st.banished = False   # 回场恢复：就绪照列、能量照涨
    st.current_energy = 50.0
    assert len(eng._ready_ultimates()) == 1
    st.current_energy = 30.0
    eng.bus.emit("on_action", {"actor": "hero", "action_type": "basic",
                               "actor_type": "character"}, eng.state)
    assert st.current_energy > 30.0, "回场后能量 hook 应恢复"


def test_emit_hooks_condition_snapshot_no_chain_trigger():
    """emit 类 hook 条件快照求值：同一事件的互斥分支不得连环触发——
    分支1挂上 X 后，分支2 的 has_modifier(X) 仍按**事件发生前**判定
    （1412 征服者病例：分支双跑 → 速度 buff 重复刷、充能 +2 而非 +1）。"""
    import types

    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=500, hp=2000, spd=120, crit_rate=0.05,
                                 crit_dmg=0.5, max_energy=100))
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=80, max_toughness=120.0, weakness=["fire"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={}, mode=MODE_EXPECTED,
                       initial_sp=3, initial_energy_ratio=0.0)
    eng.setup()
    eng._compiled_hooks = [
        types.SimpleNamespace(   # 分支1：给目标挂 X（无条件的先行分支）
            event="on_action", owner_id="hero", condition_expr=None,
            effects=[{"effect_type": "apply_modifier", "target": "self",
                      "modifier": {"modifier_id": "X", "name": "X", "modifier_type": "buff",
                                   "duration": 1}}]),
        types.SimpleNamespace(   # 分支2：has X 才跑——快照下不得触发（X 是分支1刚挂的）
            event="on_action", owner_id="hero",
            condition_expr=eng._expr.compile("has_modifier($event.target, 'X')"),
            effects=[{"effect_type": "gain_resource", "resource_id": "r2", "amount": 1}]),
        types.SimpleNamespace(   # 分支3：!has X 才跑——快照下应触发
            event="on_action", owner_id="hero",
            condition_expr=eng._expr.compile("!has_modifier($event.target, 'X')"),
            effects=[{"effect_type": "gain_resource", "resource_id": "r3", "amount": 1}]),
    ]
    eng._hooks._subscribe_compiled_hooks()
    st = eng.state.actors["hero"]
    eng.bus.emit("on_action", {"actor": "hero", "action_type": "basic",
                               "actor_type": "character", "target": "hero"}, eng.state)
    assert "X" in st.modifiers, "分支1应挂上 X"
    assert st.resources.get("r2", 0.0) == 0.0, (
        "分支2在快照下不得触发（连环触发=条件求值没快照）")
    assert st.resources.get("r3", 0.0) == 1.0, "分支3在快照下应触发"


def test_has_modifier_self_namespace_resolves_to_owner():
    """has_modifier($self, ...) 按 hook 持有者解析（_HookSelfNS 面板命名空间包装）——
    曾落 str($self) 查无此人恒 0，"单场一次"闸集体失效（1412 见者每次终结技都触发）。"""
    from hsr_nous.sim.state import Modifier
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=500, hp=2000, spd=120, crit_rate=0.05,
                                 crit_dmg=0.5, max_energy=100))
    enemy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=80, max_toughness=120.0, weakness=["fire"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, enemy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=50))
    eng = CombatEngine(enc, actions_by_actor={}, mode=MODE_EXPECTED,
                       initial_sp=3, initial_energy_ratio=0.0)
    eng.setup()
    st = eng.state.actors["hero"]
    ctx = eng._hook_ctx(st, {})
    fns = eng._hooks._hook_functions(st)
    cond = eng._expr.compile("has_modifier($self, 'X')")
    assert bool(eng._expr.evaluate(cond, ctx, functions=fns)) is False   # 未挂 X
    eng._apply_modifier(st, Modifier(
        modifier_id="X", name="X", modifier_type="buff", duration=1,
        stat_effects={}, source_id="e1"))
    assert bool(eng._expr.evaluate(cond, ctx, functions=fns)) is True, (
        "has_modifier($self,'X') 挂上后应命中（恒 0 = $self 解析坏了）")
    # 字面 id 通道不受影响（既有口径）
    cond2 = eng._expr.compile("has_modifier('hero', 'X')")
    assert bool(eng._expr.evaluate(cond2, ctx, functions=fns)) is True


def test_kill_target_enemy_wipe_and_party_wipe_universal():
    """kill_target 实装：终止=对面全灭（无 AV 预算，不再撞 fixed_av 的线）；
    我方全灭为模式无关通则（任何模式下我方死光即终局）。"""
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    from hsr_nous.sim_schema.action import Action
    from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

    basic = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                   damage_type="physical", scaling=[{"atk": 9.9}])
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=3000, hp=2000, spd=120, crit_rate=0.05,
                                 crit_dmg=0.5, max_energy=100))
    weak_enemy = Actor(actor_id="e1", name="脆皮", actor_type="monster", level=80,
                       stats=StatBlock(hp=100, spd=80, max_toughness=120.0, weakness=["physical"]))

    # 对面全灭判停：kill_target 无 AV 预算——杀完即终局（fixed_av 800 曾把变身局掐死在半路）
    enc = Encounter(encounter_id="t", name="t", actors=[hero, weak_enemy],
                    termination=TerminationConfig(mode="kill_target"))
    eng = CombatEngine(enc, actions_by_actor={"hero": [basic]}, mode=MODE_EXPECTED,
                       initial_sp=3, initial_energy_ratio=0.0)
    state = eng.run()
    assert state.actors["e1"].alive is False
    assert eng._should_terminate() is True

    # 无预算也照跑：敌人活着时 AV 随便超 800（kill_target 没有 fixed_av 的截断线）
    tank = Actor(actor_id="e1", name="木桩", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e12, spd=80, max_toughness=120.0, weakness=["physical"]))
    enc2 = Encounter(encounter_id="t2", name="t2", actors=[hero, tank],
                     termination=TerminationConfig(mode="kill_target"))
    eng2 = CombatEngine(enc2, actions_by_actor={"hero": [basic]}, mode=MODE_EXPECTED,
                        initial_sp=3, initial_energy_ratio=0.0)
    eng2.setup()
    eng2.state.clock = 100000.0   # 远超任何 AV 预算
    assert eng2._should_terminate() is False

    # 我方全灭通则：角色阵亡（任何模式）→ 终局（放逐不算死——白厄 solo 期不误判）
    enc3 = Encounter(encounter_id="t3", name="t3", actors=[hero, tank],
                     termination=TerminationConfig(mode="kill_target"))
    eng3 = CombatEngine(enc3, actions_by_actor={"hero": [basic]}, mode=MODE_EXPECTED,
                        initial_sp=3, initial_energy_ratio=0.0)
    eng3.setup()
    st = eng3.state.actors["hero"]
    st.current_hp = 0.0
    st.alive = False
    assert eng3._should_terminate() is True


def test_cerydra_surprise_skill_duplication():
    """奇袭战技复制（刻律德菈爵位机制核心，owner 实锤）：
    军功充能≥6 + 军功持有者放战技 → $event.action_id 动态复刻（持有者再放一次），
    随后消耗 6 充能；insert 闸防奇袭套娃；普攻/战技充能恢复（141204 天赋在案）。"""
    import yaml

    from tests._data_env import data_available, data_skip_reason
    if not data_available():
        pytest.skip(data_skip_reason())  # 依赖 data/ 下 1412 模板（gitignored）

    from hsr_nous.sim.compile import compile_encounter
    from hsr_nous.sim.state import Modifier

    build = {"build": {"team": [{"character_template": "1412", "level": 80},
                                {"character_template": "1408", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 400}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    st_cyd = eng.state.actors["1412"]
    st_p = eng.state.actors["1408"]
    # 军功 + 充能 6 就位（实战=刻律德菈战技施加；此处直接置状态）
    eng._apply_modifier(st_p, Modifier(
        modifier_id="CYD_MERIT", name="军功", modifier_type="buff", duration=0,
        dispellable=False, source_id="1412"))
    st_cyd.resources["cerydra_charge"] = 6.0
    actions = []
    eng.bus.subscribe("on_action", lambda et, p, ctx: actions.append(p))

    skill = next(a for a in eng.actions_by_actor["1408"] if a.action_id == "140802")
    hp_before = eng.state.actors["e1"].current_hp
    eng._execute_action(st_p, skill)
    # 回合流的 on_action 广播（直调 _execute_action 不含，奇袭 hook 挂在它上面——镜像 _run_turn）
    eng.bus.emit("on_action", {"actor": "1408", "action_type": skill.action_type,
                               "action_id": skill.action_id, "target_type": skill.target_type,
                               "actor_type": "character"}, eng.state)

    # 复刻：同一战技结算两次（原技能 + insert 复制）
    skill_acts = [p for p in actions if p.get("action_type") == "skill"]
    assert len(skill_acts) == 2, f"战技应结算两次（奇袭复制）：{skill_acts}"
    assert any(p.get("insert") for p in skill_acts), "应有一次 insert 复制"
    dmg = hp_before - eng.state.actors["e1"].current_hp
    assert dmg > 0
    # 充能：6 + 本动天赋 +1 - 奇袭耗 6 = 1
    assert st_cyd.resources["cerydra_charge"] == 1.0, (
        f"充能结算不符（6+1-6=1）：{st_cyd.resources['cerydra_charge']}")

    # 奇袭条件求值级负例（官方 141202"using their Skill on enemy targets"）：
    # self/ally 目标战技不命中（140809 自身强化战技不触发——owner 实战同口径），敌方目标命中
    st_cyd.resources["cerydra_charge"] = 6.0   # 复位充能（前面已被奇袭耗成 1——门 >= 6 要过）
    cond = next(h.condition_expr for h in eng._compiled_hooks
                if h.owner_id == "1412" and any(e.get("effect_type") == "trigger_action"
                                               for e in h.effects))
    for tt, want in (("self", False), ("ally_single", False), ("ally_aoe", False),
                     ("single", True), ("blast", True), ("bounce", True), ("aoe", True)):
        payload = {"actor": "1408", "action_type": "skill", "action_id": "x",
                   "target_type": tt, "insert": False}
        assert bool(eng._expr.evaluate(cond, eng._hook_ctx(st_cyd, payload),
                                       functions=eng._hooks._hook_functions(st_cyd))) is want, (
            f"target_type={tt} 奇袭条件应为 {want}")
    # insert 闸：复制的那次不得再触发奇袭（恰好两次，不是三次/无限）


def test_gain_energy_event_channel_and_target_namespace():
    """gain_energy '$event.<字段>' 通道 + $target 命名空间（停云/星期日单充族实例）：

    - 对 130 上限队友充 = 26（0.2×130，按目标面板逐目标求值）；
    - 对白厄充：能量被 0 上限截断，但回能事件触发 140804 特殊充能 hook → 火种 +1，
      叠上 140804"成为目标"+1 → 一次充能大 = 2 火种（owner 实战口径）。
    """
    from hsr_nous.sim.policy_api import ULT_AFTER_ACTION

    class _PickTarget:
        ult_timing = ULT_AFTER_ACTION

        def __init__(self, target_id):
            self.target_id = target_id

        def select_action(self, st, legal, eng=None):
            return legal[0]

        def select_target(self, st, action_type, candidates, eng=None):
            return next((c for c in candidates if c.actor.actor_id == self.target_id), None)

        def select_ultimate(self, st, ready, eng=None):
            return next((a for s, a in ready if s.actor.actor_id == "999901"), None)

    stage = {"stage": {"stage_id": "s", "enemies": [
        # 木桩（无行动表=占位不攻击）——排除"敌方攻击指白厄喂火种"的干扰源
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 400}}}

    def _make(target_id):
        build = {"build": {"team": [
            {"character_template": "1408", "level": 80},
            {"character_template": "999901", "level": 80},
            {"actor_id": "ally", "name": "队友A", "inline": True,
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 130},
             "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "physical",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        ], "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        eng.state.actors["999901"].current_energy = 100.0   # 满能即放
        eng.decision = _PickTarget(target_id)
        return eng

    # —— A：对 130 上限队友充 → 0.2×130 = 26（$target.max_energy 按目标求值）——
    # 按事件断言（不吃队友自动作回能的干扰：86=60 自动 + 26 本效果）；
    # on_gain_energy 是 waterfall 事件——必须 subscribe_waterfall 才挂得上（subscribe 只收 emit 类）
    eng = _make("ally")
    evts = []
    eng.bus.subscribe_waterfall("on_gain_energy", lambda et, p, ctx: evts.append(p) or None)
    eng.run()
    hit = [p for p in evts if p.get("actor") == "ally" and p.get("source") == "999901"]
    assert len(hit) == 1 and math.isclose(hit[0]["amount"], 26.0, abs_tol=1e-6), (
        f"应按目标上限 20% 充 26：{hit}")

    # —— B：对白厄充 → 能量截断为 0、火种 +2（目标 1 + 回能 1）——
    eng = _make("1408")
    gains = []
    eng.bus.subscribe("on_resource_gain", lambda et, p, ctx: gains.append(p))
    eng.run()
    st = eng.state.actors["1408"]
    assert math.isclose(st.current_energy, 0.0), f"白厄能量应恒 0（特殊充能）：{st.current_energy}"
    seed_gains = [p for p in gains if p.get("resource_id") == "fire_seed" and p.get("amount") == 1]
    # 火种 +1×2：140804 成为目标（140804）+ 特殊充能回能转换（on_gain_energy hook）
    assert len(seed_gains) == 2, f"充能大应直接回 2 枚火种：{seed_gains}"
    assert math.isclose(st.resources["fire_seed"], 3.0 + 2.0), (
        f"开局 3 + 充能大 2 = 5：{st.resources}")
