"""§23.9 hook 累积模式：事件 → 入队 → flush 时机聚合执行一次（风堇小伊卡治疗 tally 族）.

语义钉：主事件只入队（condition 同普通 hook 快照口径）；flush 时聚合 $event=末事件包 +
targets（首现序去重 + target_filter 过滤）执行一次 effects → 队列清空；
target_filter 无 accumulated 编译期炸（静默忽略=幻觉温床）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 编译闸
# ---------------------------------------------------------------------------

class TestAccumulatedCompileGates:
    def _compile(self, hook):
        out: list = []
        BuildCompiler()._compile_hooks([hook], "模板 X", "t900", out)
        return out[0]

    _BASE = {"event": "on_hp_decrease", "effects": [
        {"effect_type": "heal", "target": "$event.targets", "ratio": 0.05}]}

    def test_accumulated_requires_flush_triggers(self):
        with pytest.raises(ValueError, match="无 flush_triggers"):
            self._compile({**self._BASE, "accumulated": True})

    def test_flush_triggers_contract_gate(self):
        with pytest.raises(ValueError, match="flush_triggers 引用未登记事件"):
            self._compile({**self._BASE, "accumulated": True,
                           "flush_triggers": ["on_skill_used"]})

    def test_target_filter_without_accumulated_rejected(self):
        with pytest.raises(ValueError, match="未声明 accumulated"):
            self._compile({**self._BASE, "target_filter": "$it != 'x'"})

    def test_target_filter_illegal_expr_rejected(self):
        with pytest.raises(ValueError):
            self._compile({**self._BASE, "accumulated": True,
                           "flush_triggers": ["on_turn_start"],
                           "target_filter": "$it =!=> 'x'"})

    def test_valid_accumulated_compiles(self):
        h = self._compile({**self._BASE, "accumulated": True,
                           "flush_triggers": ["on_turn_start"],
                           "target_filter": "$it != 'e9'"})
        assert h.accumulated is True and h.flush_triggers == ("on_turn_start",)
        assert h.target_filter_expr is not None


# ---------------------------------------------------------------------------
# 引擎：fixture 999905 全链路
# ---------------------------------------------------------------------------

def _engine():
    build = {"build": {"team": [{"character_template": "999905", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 70}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _hp_down(eng, target_id, amount, source="e1"):
    st = eng.state.actors[target_id]
    st.current_hp -= amount
    eng.bus.emit("on_hp_decrease", {
        "amount": amount, "source": source, "reason": "hit", "target": target_id}, eng.state)


class TestAccumulatedRuntime:
    def test_tally_then_flush_once(self):
        """三次掉血入队（忆灵自身除外）→ 无 flush 不治疗 → 回合开始聚合治疗一次 → 队列清空."""
        eng = _engine()
        hero = eng.state.actors["999905"]
        memo = eng.state.actors["999905_memo"]
        assert memo.alive, "开局记账灵入场"
        _hp_down(eng, "999905", 500.0)
        _hp_down(eng, "999905_memo", 300.0)   # 忆灵自身掉血——condition 排除，不入队
        _hp_down(eng, "999905", 200.0)
        hp_hero_before = hero.current_hp
        hp_memo_before = memo.current_hp
        # 无 flush：不结算（忆灵不抢跑）
        eng._hooks._flush_accumulated  # noqa: B018（存在性钉；不得提前结算）
        assert hero.current_hp == hp_hero_before and memo.current_hp == hp_memo_before
        # flush：聚合治疗一次——targets 首现序去重且不含忆灵自身
        healed = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: healed.append(p))
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert len(healed) == 1 and healed[0]["target"] == "999905", (
            "聚合治疗一次且仅作用聚合目标（忆灵自身被 condition 排除）")
        assert healed[0]["source"] == "999905_memo", "治疗来源是记账灵（hook owner）"
        assert hero.current_hp > hp_hero_before
        assert memo.current_hp == hp_memo_before, "记账灵不在聚合 targets 里"
        # 队列已清空：再 flush 无事发生
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert len(healed) == 1, "队列消费后即清——重复 flush 不得再结算"

    def test_target_filter_drops_candidates(self):
        """target_filter 逐候选过滤（$it）：hero 被滤出、ally2 通过——双向钉."""
        out: list = []
        BuildCompiler()._compile_hooks([{
            "event": "on_hp_decrease", "accumulated": True,
            "flush_triggers": ["on_turn_start"], "target_filter": "$it != 'hero'",
            "effects": [{"effect_type": "heal", "target": "$event.targets", "ratio": 0.05}],
        }], "测试", "hero", out)
        # setup 前注入编译产物（订阅随 setup 成形——setup 后替换只会新旧订阅并存）
        from hsr_nous.sim_schema.actor import Actor, StatBlock
        from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
        from hsr_nous.sim.policy_api import ScriptedPolicy
        actors = [
            Actor(actor_id="hero", name="hero", level=80,
                  stats=StatBlock(atk=1000, spd=100, hp=3000, max_energy=100)),
            Actor(actor_id="ally2", name="ally2", level=80,
                  stats=StatBlock(atk=1000, spd=90, hp=3000, max_energy=100)),
            Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=50, max_toughness=9999, weakness=["physical"])),
        ]
        enc = Encounter(encounter_id="t", name="t", actors=actors,
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED, seed=None, initial_sp=10,
                           initial_energy_ratio=0.0)
        eng._compiled_hooks = out
        eng.setup()
        _hp_down(eng, "hero", 400.0)
        _hp_down(eng, "ally2", 400.0)
        healed = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: healed.append(p))
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert [h["target"] for h in healed] == ["ally2"], (
            "target_filter 把 hero 滤出聚合 targets，ally2 通过——双向钉")
