"""执行帧（ExecutionFrame，裁决卡 #26）语义钉：写后读可见性 + 执行级随机绑定.

验收清单逐条钉（designs/DECISIONS.md ## #26）：
    同学执行写后读（快照层 condition 读己之写）/ 跨事件链（modifier 回调写→同窗后续读）/
    提交后跨执行可见 / 回滚丢弃 / 嵌套隔离+提交合并 / roll 首采后续零消耗（RNG 流位置断言）/
    condition 读未绑定拒绝 / 同 seed 回放逐字段全等（#25 save_load harness 写法）.
"""
from __future__ import annotations

import json
import random

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.compiled import CompiledHook
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.enemy_ai import config_ai_dynamic_value
from hsr_nous.sim.pipeline import MODE_ROLL
from hsr_nous.sim_schema.expression import parse
from tests._builders import basic_action, engine_vs_dummy
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SEED = 42
# 绑定点的期望采样值：MODE_ROLL 下首段直伤暴击判定先消耗主流一次，after_being_hit
# hook 的 roll 首采 = Random(SEED) 的第二抽（流位置钉死在此——消费序漂移本测试即红）。
_SEQ_RNG = random.Random(SEED)
_BIND_DRAW = (_SEQ_RNG.random(), _SEQ_RNG.random())[1]


def _hook(event: str, owner: str, effects: list, condition: str | None = None) -> CompiledHook:
    """CompiledHook 手工件（effects 为 dict 清单；condition 过白名单编译）."""
    return CompiledHook(
        owner_id=owner, event=event,
        condition_expr=parse(condition, layer="effect") if condition else None,
        effects=tuple(dict(e) for e in effects))


def _install(eng: CombatEngine, *hooks: CompiledHook) -> None:
    eng._compiled_hooks = list(hooks)
    eng._hooks._subscribe_compiled_hooks()


def _committed(eng: CombatEngine, actor_id: str = "e1") -> dict:
    return dict(eng._enemy_policy_state.get(actor_id, {}).get("dynamic_values", {}))


def _attack(eng: CombatEngine, actor_id: str = "hero", action_id: str = "b") -> None:
    eng._execute_action(eng.state.actors[actor_id], eng.actions_by_actor[actor_id][0]
                        if action_id == "b" else
                        next(a for a in eng.actions_by_actor[actor_id] if a.action_id == action_id))


# ---------------------------------------------------------------------------
# 写后读（覆盖层读己之写）
# ---------------------------------------------------------------------------

class TestWriteRead:
    def test_same_action_write_then_read_snapshot_condition(self):
        """同学执行写后读：on_become_target 写入（覆盖层）→ 同窗 after_being_hit 的
        hook 级 condition（快照层）经 dynamic_of 读己之写；同一事件的快照不得穿透."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng,
                 _hook("on_become_target", "e1",
                       [{"effect_type": "set_dynamic_value", "target": "self",
                         "dynamic_key": "X", "amount": 1}]),
                 _hook("on_become_target", "e1",
                       [{"effect_type": "gain_resource", "resource_id": "leak", "amount": 1}],
                       condition="dynamic_of($self.actor_id, 'X') == 1"),
                 _hook("after_being_hit", "e1",
                       [{"effect_type": "gain_resource", "resource_id": "seen", "amount": 1}],
                       condition="dynamic_of($self.actor_id, 'X') == 1"))
        mid_action: list[tuple[float, dict]] = []
        eng.bus.subscribe("after_being_hit", lambda et, p, ctx: mid_action.append(
            (config_ai_dynamic_value(eng, "e1", "X"), _committed(eng))))

        _attack(eng)

        st_e = eng.state.actors["e1"]
        assert st_e.resources.get("seen", 0.0) == 1.0, "快照层 condition 应经覆盖层读己之写"
        assert st_e.resources.get("leak", 0.0) == 0.0, (
            "同一事件的快照 pass 不得看到本事件效果写入（事件间快照语义一字未改）")
        assert mid_action and mid_action[0][0] == 1.0, "行动中途覆盖层读数应为 1"
        assert "X" not in mid_action[0][1], "行动中途已提交态不得有 X（写未提交）"
        assert _committed(eng).get("X") == 1.0, "行动提交后 X 落已提交态"
        assert eng._frame_stack == [], "行动结束帧栈必须清空"

    def test_write_visible_across_event_chain_modifier_on_remove(self):
        """跨事件链：modifier on_remove 回调（摘件效果）写覆盖层 → 同窗后续事件读.

        链路：on_become_target 挂 M → on_hp_decrease 摘 M（OnDestroy 回调写 X）
        → after_being_hit 的 condition 读 X."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng,
                 _hook("on_become_target", "hero",
                       [{"effect_type": "apply_modifier", "target": "$event.target",
                         "modifier": {"modifier_id": "M", "name": "M", "modifier_type": "buff",
                                      "duration": 3,
                                      "on_remove": [
                                          {"effect_type": "set_dynamic_value", "target": "self",
                                           "dynamic_key": "X", "amount": 1}]}}]),
                 _hook("on_hp_decrease", "hero",
                       [{"effect_type": "remove_modifier", "target": "$event.target",
                         "modifier_id": "M"}]),
                 _hook("after_being_hit", "hero",
                       [{"effect_type": "gain_resource", "resource_id": "seen", "amount": 1}],
                       condition="dynamic_of($event.target, 'X') == 1"))
        _attack(eng)
        assert eng.state.actors["hero"].resources.get("seen", 0.0) == 1.0, (
            "modifier 回调写→同窗后续事件读：跨事件链覆盖层可见性")
        assert "M" not in eng.state.actors["e1"].modifiers, "M 应已被摘除"
        assert _committed(eng).get("X") == 1.0

    def test_commit_visible_across_executions(self):
        """提交后跨执行可见：第一次行动的写入提交后，第二次行动的 condition 读已提交态."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng,
                 _hook("on_become_target", "e1",
                       [{"effect_type": "set_dynamic_value", "target": "self",
                         "dynamic_key": "X", "amount": 1}],
                       condition="dynamic_of($self.actor_id, 'X') == 0"),
                 _hook("after_being_hit", "e1",
                       [{"effect_type": "gain_resource", "resource_id": "seen", "amount": 1}],
                       condition="dynamic_of($self.actor_id, 'X') >= 1"))
        _attack(eng)
        assert _committed(eng).get("X") == 1.0, "第一动提交 X"
        _attack(eng)
        st_e = eng.state.actors["e1"]
        assert st_e.resources.get("seen", 0.0) == 2.0, (
            "第二动的 condition 应读已提交态 X==1（跨执行可见）")
        assert _committed(eng).get("X") == 1.0, "第二动写入条件不满足，X 不变"


# ---------------------------------------------------------------------------
# 回滚 / 嵌套
# ---------------------------------------------------------------------------

class TestRollbackAndNesting:
    def test_exception_rolls_back_frame(self):
        """异常回滚整帧丢弃：写入后同 hook 后续 effect 抛错 → 覆盖层不得落已提交态."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng,
                 _hook("on_become_target", "hero",
                       [{"effect_type": "set_dynamic_value", "target": "$event.target",
                         "dynamic_key": "X", "amount": 1},
                        {"effect_type": "deal_damage", "target": "$event.target",
                         "amount": 1, "damage_type": "element_of('no_such_actor')"}]))
        with pytest.raises(ValueError, match="非合法元素"):
            _attack(eng)
        assert "X" not in _committed(eng), "回滚帧丢弃：已提交态不得残留 X"
        assert config_ai_dynamic_value(eng, "e1", "X") == 0.0, "帧外读回落缺省"
        assert eng._frame_stack == [], "异常后帧栈必须清空"

    def test_nested_frame_isolated_and_merged(self):
        """嵌套隔离+提交合并：子执行（trigger_action）写只进子帧；子帧提交并入父帧
        覆盖层（父帧后续读者可见）；最外层提交才落已提交态."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED,
                              actions={"hero": [basic_action("parent"), basic_action("child")]})
        _install(eng,
                 # 子行动的写者（子帧内自读自写）
                 _hook("on_become_target", "e1",
                       [{"effect_type": "set_dynamic_value", "target": "self",
                         "dynamic_key": "Y", "amount": "dynamic_of($self.actor_id, 'Y') + 7"}],
                       condition="$event.action_id == 'child'"),
                 # 父帧链：子执行之后立刻经覆盖层读 Y（子帧已提交并入父帧）
                 _hook("on_become_target", "hero",
                       [{"effect_type": "trigger_action", "caster": "self",
                         "action_id": "child"},
                        {"effect_type": "gain_resource", "resource_id": "post",
                         "amount": "dynamic_of('e1', 'Y')"}],
                       condition="$event.action_id == 'parent'"))
        child_saw: list[tuple[float, dict]] = []
        eng.bus.subscribe("on_become_target", lambda et, p, ctx: child_saw.append(
            (config_ai_dynamic_value(eng, "e1", "Y"), _committed(eng)))
            if p.get("action_id") == "child" else None)

        _attack(eng, action_id="parent")

        assert child_saw and child_saw[0][0] == 7.0, "子帧内读己之写（初值 0 + 7）"
        assert "Y" not in child_saw[0][1], "子执行中途已提交态不得有 Y（隔离单元）"
        assert eng.state.actors["hero"].resources.get("post", 0.0) == 7.0, (
            "子帧提交并入父帧覆盖层——父帧后续 effect 可见")
        assert _committed(eng).get("Y") == 7.0, "最外层提交落已提交态"
        assert eng._frame_stack == []


# ---------------------------------------------------------------------------
# roll：执行级随机绑定
# ---------------------------------------------------------------------------

class TestRoll:
    def test_roll_first_sample_then_free_rng_position(self):
        """roll 首采后续零消耗：两个引擎同 seed，双读表达式与单读表达式消耗同一主流位."""
        def build(amount: str):
            eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
            _install(eng, _hook("after_being_hit", "e1",
                                [{"effect_type": "gain_resource", "resource_id": "dice",
                                  "amount": amount}]))
            _attack(eng)
            return eng

        single = build("roll('d')")
        double = build("roll('d') + roll('d')")
        assert single.state.actors["e1"].resources["dice"] == pytest.approx(_BIND_DRAW)
        assert double.state.actors["e1"].resources["dice"] == pytest.approx(2 * _BIND_DRAW), (
            "同键二次读取零消耗返回绑定值")
        assert single.pipeline.rng.getstate() == double.pipeline.rng.getstate(), (
            "两引擎各消耗主流恰好一次——RNG 流位置断言")

    def test_roll_unbound_in_snapshot_condition_rejected(self):
        """condition（快照层）读未绑定 roll 显式拒绝：按 condition 求值失败口径
        （⚠ 日志 + 不触发），绝不静默采样."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng, _hook("after_being_hit", "e1",
                            [{"effect_type": "gain_resource", "resource_id": "seen",
                              "amount": 1}],
                            condition="roll('d') > 0"))
        _attack(eng)
        assert eng.state.actors["e1"].resources.get("seen", 0.0) == 0.0, (
            "读未绑定 roll 的 condition 不得触发")
        assert any("roll" in line and "⚠" in line for line in eng.state.log), (
            "未绑定拒绝必须显式留痕（⚠ 日志）")

    def test_condition_reads_bound_roll_same_frame(self):
        """condition 读已绑定 roll（同窗早前 effect 绑定）：共享掷骰跨求值点一致."""
        eng = engine_vs_dummy(mode=MODE_ROLL, seed=SEED)
        _install(eng,
                 _hook("on_hp_decrease", "e1",
                       [{"effect_type": "gain_resource", "resource_id": "bound",
                         "amount": "roll('d')"}]),
                 _hook("after_being_hit", "e1",
                       [{"effect_type": "gain_resource", "resource_id": "gated", "amount": 1}],
                       condition="roll('d') >= 0.5"))
        _attack(eng)
        st_e = eng.state.actors["e1"]
        assert st_e.resources.get("bound", 0.0) == pytest.approx(_BIND_DRAW), (
            "effect 域首采绑定值")
        expected_gate = 1.0 if _BIND_DRAW >= 0.5 else 0.0
        assert st_e.resources.get("gated", 0.0) == expected_gate, (
            "condition 读已绑定 roll：同帧共享同一骰子（零消耗、值一致）")


# ---------------------------------------------------------------------------
# 同 seed 回放逐字段全等（#25 harness 写法）
# ---------------------------------------------------------------------------

def _replay_build() -> dict:
    """回放编队：inline 英雄 + 带执行帧机制 hook（dynamic 写读链 + roll 绑定/读绑定）."""
    return {"build": {
        "team": [{"actor_id": "hero", "name": "测试员", "inline": True,
                  "base_stats": {"atk": 2000, "spd": 200, "hp": 5000, "max_energy": 100},
                  "actions": [{"action_id": "b", "name": "普攻", "action_type": "basic",
                               "target_type": "single", "damage_type": "fire",
                               "scaling": [{"atk": 1.0}], "toughness_dmg": 0}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "b", "priority": 0}]}}}


def _replay_stage() -> dict:
    return {"stage": {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
                     "max_toughness": 9999, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 800}}}


def _frame_hooks() -> list:
    return [
        _hook("on_become_target", "e1",
              [{"effect_type": "set_dynamic_value", "target": "self",
                "dynamic_key": "X",
                "amount": "dynamic_of($self.actor_id, 'X') + 1"}]),
        _hook("on_hp_decrease", "e1",
              [{"effect_type": "gain_resource", "resource_id": "dice", "amount": "roll('d')"}]),
        _hook("after_being_hit", "e1",
              [{"effect_type": "gain_resource", "resource_id": "hit_mark", "amount": 1}],
              condition="roll('d') >= 0.3 && dynamic_of($self.actor_id, 'X') >= 1"),
    ]


def _compiled_with_frame_hooks():
    compiled = compile_encounter(_replay_build(), _replay_stage(),
                                 template_roots=TEST_TEMPLATE_ROOTS)
    from dataclasses import replace as _dc_replace
    return _dc_replace(compiled, hooks=list(compiled.hooks) + _frame_hooks())


def _steps(eng: CombatEngine, n: int) -> None:
    for i in range(n):
        assert eng.step() is not None, f"第 {i + 1} 步前战斗已终止（预算配置复查）"


class TestReplayWorldLine:
    def test_same_seed_save_load_field_equal(self):
        """同 seed 回放逐字段全等：存档（JSON 往返）续跑 vs 一口气对照——
        snapshot 投影 / 日志流 / 总伤 / 再存档逐比特全等（#25 harness 同四件断言）."""
        compiled = _compiled_with_frame_hooks()
        n_steps, m_steps = 3, 4

        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=SEED)
        eng.setup()
        _steps(eng, n_steps)
        save = json.loads(json.dumps(eng.save_state(), ensure_ascii=False))
        restored = CombatEngine.load_state(compiled, save)
        _steps(restored, m_steps)

        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=SEED)
        ctrl.setup()
        _steps(ctrl, n_steps + m_steps)

        assert restored.state.snapshot() == ctrl.state.snapshot(), "终态 snapshot() 投影分叉"
        assert restored.state.log == ctrl.state.log, "战斗日志流分叉"
        assert restored.state.total_damage == ctrl.state.total_damage, "总伤分叉"
        assert restored.save_state() == ctrl.save_state(), (
            "全精度再存档分叉（含 RNG 流位置/已提交 dynamic_values 其一漂移）")
        # 帧机制痕迹断言：dynamic 写读链与 roll 绑定确实在回放局内发生
        # （步内混有敌方占位回合，on_become_target 次数 = 我方行动数 < 总步数）。
        assert _committed(restored).get("X", 0) >= 4, "回放局每动一次的 X 累写应已提交"
        assert restored.state.actors["e1"].resources.get("dice", 0.0) > 0.0

    def test_frame_never_leaks_into_save(self):
        """帧瞬态性钉：存档键集不含任何帧字段（覆盖层/绑定表零新增存储）."""
        compiled = _compiled_with_frame_hooks()
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=SEED)
        eng.setup()
        _steps(eng, 2)
        blob = json.dumps(eng.save_state(), ensure_ascii=False)
        assert "writes" not in blob and "rolls" not in blob and "_frame_stack" not in blob
        # 决策簿不记骰子（roll 不进决策簿）；帧栈档间恒空
        assert eng._frame_stack == []
