"""trigger_order.yaml 跨 actor hook 执行序 + $team 跨 actor 聚合命名空间.

语义钉：trigger_order 声明序 → 编译产物列表序兜底（未列事件/单位零影响）；
$team = 我方全员逐值列表（all_allies 同口径），外套白名单聚合函数
（max/sum/count——"全队攻击力最高者 >N"族策略可写）。
"""
from __future__ import annotations

import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED


def _tpl(tid, amount):
    return {
        "actor_id": tid, "name": tid, "level": 80,
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
        "custom_resources": {"r": {"max": 99}},
        "actions": [{"action_id": f"{tid}b", "name": "普攻", "action_type": "basic",
                     "target_type": "single", "damage_type": "physical",
                     "scaling": [{"atk": 1.0}]}],
        "hooks": [{"event": "on_battle_start",
                   "effects": [{"effect_type": "gain_resource",
                                "resource_id": "r", "amount": amount}]}],
    }


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 70}}}


def _run(tmp_path, with_order):
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ta_甲.yaml").write_text(yaml.safe_dump(_tpl("ta", 1), allow_unicode=True),
                                  encoding="utf-8")
    (d / "tb_乙.yaml").write_text(yaml.safe_dump(_tpl("tb", 2), allow_unicode=True),
                                  encoding="utf-8")
    if with_order:
        g = tmp_path / "global"
        g.mkdir(exist_ok=True)
        (g / "trigger_order.yaml").write_text(
            yaml.safe_dump({"order": {"on_battle_start": ["tb", "ta"]}}, allow_unicode=True),
            encoding="utf-8")
    build = {"build": {"team": [{"character_template": "ta", "level": 80},
                                {"character_template": "tb", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    eng = CombatEngine.from_compiled(
        compile_encounter(build, _STAGE, template_roots=[str(tmp_path)]),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    gains = []
    eng.bus.subscribe("on_resource_gain", lambda et, p, ctx: gains.append(
        (p["actor"], p["amount"])))
    eng.setup()   # on_battle_start 在此发射
    return gains


class TestTriggerOrder:
    def test_default_compile_order(self, tmp_path):
        gains = _run(tmp_path, with_order=False)
        assert gains == [("ta", 1.0), ("tb", 2.0)], "无文件=编译产物列表序（队伍声明序）"

    def test_file_order_overrides(self, tmp_path):
        gains = _run(tmp_path, with_order=True)
        assert gains == [("tb", 2.0), ("ta", 1.0)], (
            "trigger_order.yaml 声明序覆盖编译序（tb 先 ta 后）")

    def test_bad_shape_rejected(self, tmp_path):
        g = tmp_path / "global"
        g.mkdir(parents=True, exist_ok=True)
        (g / "trigger_order.yaml").write_text(
            yaml.safe_dump({"order": {"on_battle_start": "ta"}}, allow_unicode=True),
            encoding="utf-8")
        import pytest
        with pytest.raises(ValueError, match="须为 actor_id 列表"):
            _run(tmp_path, with_order=False)   # 不重写——坏文件应被加载闸拦下


class TestTeamNamespace:
    def _engine(self):
        from hsr_nous.sim_schema.actor import Actor, StatBlock
        from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig
        from hsr_nous.sim.policy_api import ScriptedPolicy
        actors = [Actor(actor_id=f"a{i}", name=f"队友{i}", level=80,
                        stats=StatBlock(atk=1000 * i, spd=100, hp=2000, max_energy=100))
                  for i in (1, 2, 3)]
        actors.append(Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                            stats=StatBlock(hp=1e9, spd=50, max_toughness=9999,
                                            weakness=["physical"])))
        enc = Encounter(encounter_id="t", name="t", actors=actors,
                        termination=TerminationConfig(mode="fixed_av", max_action_value=70))
        eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                           mode=MODE_EXPECTED, seed=None, initial_sp=10,
                           initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def test_aggregates(self):
        eng = self._engine()
        ns = eng.team_namespace()
        assert max(ns.atk) == 3000.0 and count_ok(ns) and sum(ns.broken) == 0
        st = eng.state.actors["a1"]
        fns = eng._hooks._hook_functions(st)
        ctx = eng._hooks._hook_ctx(st, {})
        assert eng._expr.evaluate(eng._expr.compile(
            "max($team.atk) > 1500", layer="effect"), ctx, functions=fns) is True
        assert eng._expr.evaluate(eng._expr.compile(
            "count($team.atk) == 3", layer="effect"), ctx, functions=fns) is True
        eng.state.actors["a2"].broken = True
        assert eng._expr.evaluate(eng._expr.compile(
            "sum($team.broken) == 1", layer="effect"),
            eng._hooks._hook_ctx(st, {}), functions=fns) is True

    def test_policy_ctx_has_team(self):
        from hsr_nous.sim.policy_api import CompiledPolicyRuntime
        from hsr_nous.sim.compile.compiled import CompiledPolicy
        eng = self._engine()
        rt = CompiledPolicyRuntime(CompiledPolicy(
            name="p", action_rules=(), target_rules=(), parameters={}))
        ctx = rt._context(eng.state.actors["a1"], eng)
        assert "team" in ctx and max(ctx["team"].atk) == 3000.0


def count_ok(ns) -> bool:
    return len(ns.atk) == 3 and len(ns.actor_id) == 3
