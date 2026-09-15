"""欢愉体系 schema 层（B40 P1b）端到端：elation 面板/elation_number/笑点队伍账/好活当赏条目列表。

模子同 trigger_action 批（tmp_path 微型模板，template_roots 注入，零锚集污染）。
口径：面板链 = base 0.1 + 行迹 0.28 + modifier 0.05 = 0.43；笑点=队伍账全局池；
好活当赏=条目列表（spec 固定 2 回合，持有者 owner_turn_end -1）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

_PANEL = """\
actor_id: "900201"
name: "欢愉面板测试员"
level: 80
elation_number: 144
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100, elation: 0.1}
trace_stat_effects: {"elation": 0.28}
custom_resources:
  _elation_seen:
    max: 1
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "fire"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
hooks:
  - event: "on_action"
    condition: "$event.actor == '900201' && $event.action_id == 't_basic'"
    effects:
      - effect_type: "gain_resource"
        resource_id: "punchline"
        amount: 5
  - event: "on_action"
    condition: "$event.actor == '900201' && $event.action_id == 't_basic' && $self.elation >= 0.4"
    effects:
      - effect_type: "set_resource"
        resource_id: "_elation_seen"
        amount: 1
"""

_MATE = """\
actor_id: "900202"
name: "队友测试员"
level: 80
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "physical"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
"""

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture()
def roots(tmp_path):
    d = tmp_path / "characters"
    d.mkdir()
    (d / "900201_欢愉面板.yaml").write_text(_PANEL, encoding="utf-8")
    (d / "900202_队友.yaml").write_text(_MATE, encoding="utf-8")
    return [str(tmp_path)]


def _make(roots, *, hooks_extra: str = ""):
    tpl = _PANEL
    if hooks_extra:
        d = roots[0]
        import pathlib
        tpl_path = pathlib.Path(d) / "characters" / "900201_欢愉面板.yaml"
        tpl_path.write_text(_PANEL + hooks_extra, encoding="utf-8")
    c = compile_encounter({"build": {"team": [
        {"character_template": "900201", "level": 80},
        {"character_template": "900202", "level": 80}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}},
        _STAGE, template_roots=roots)
    eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _cast_basic(eng, aid="900201"):
    st = eng.state.actors[aid]
    a = next(x for x in eng.actions_by_actor[aid] if x.action_id == "t_basic")
    tgt = eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": aid, "action_type": a.action_type, "action_id": a.action_id,
        "target_type": a.target_type, "target": "e1",
        "actor_type": st.actor.actor_type}, eng.state)


class TestElationPanel:
    def test_base_trace_modifier_chain(self, roots):
        """elation 面板链：base 0.1 + 行迹 0.28（trace_stat_effects 通道）= 0.38；
        $self.elation 表达式域可读（>=0.4 门=0.38+modifier 0.05 后开）。"""
        eng = _make(roots, hooks_extra="""
  - event: "on_battle_start"
    effects:
      - effect_type: "apply_modifier"
        target: "self"
        modifier:
          modifier_id: "E_BOOST"
          name: "欢愉度测试件"
          modifier_type: "buff"
          duration: 0
          stat_effects: {"elation": 0.05}
""")
        st = eng.state.actors["900201"]
        eff = eng.pipeline.effective_stats(st)
        assert eff["elation"] == pytest.approx(0.1 + 0.28 + 0.05), (
            "base+行迹+modifier 三层同池 flat 加算")
        assert eng.state.actors["900201"].actor.elation_number == 144, (
            "参演编号模板顶层键入 Actor 字段")

    def test_self_ns_gate_fires(self, roots):
        """$self.elation 条件域（无 modifier 时 0.38 < 0.4）不开；挂 0.05 件后开。"""
        eng = _make(roots)
        st = eng.state.actors["900201"]
        assert eng.pipeline.effective_stats(st)["elation"] == pytest.approx(0.38)
        _cast_basic(eng)
        assert st.resources.get("_elation_seen", 0.0) == 0.0, "0.38<0.4 门不开"
        eng._modifiers._apply_modifier_spec(st, {
            "modifier_id": "E_BOOST", "name": "欢愉度测试件", "modifier_type": "buff",
            "duration": 0, "stat_effects": {"elation": 0.05}}, st)
        _cast_basic(eng)
        assert st.resources.get("_elation_seen", 0.0) == 1.0, "0.43>=0.4 门开（$self.elation 现场值）"


class TestPunchlineTeamPool:
    def test_team_shared_pool_and_read_channels(self, roots):
        """笑点队伍账：A 获得 5 → 全局池 5；B 的 res_/resource_of 读通道同值；
        on_resource_gain 事件 actor 仍记持有者。"""
        eng = _make(roots)
        events = []
        eng.bus.subscribe("on_resource_gain",
                          lambda et, payload, state: events.append(payload))
        _cast_basic(eng, "900201")
        assert eng.state.punchline == 5.0, "A 获得写全局池"
        st_b = eng.state.actors["900202"]
        assert eng._resource_value(st_b, "punchline") == 5.0, "B 读同一池（队伍账）"
        assert eng._res_ns(st_b)["res_punchline"] == 5.0, "表达式 res_ 命名空间覆写"
        _cast_basic(eng, "900202")
        assert eng.state.punchline == 5.0, "B 无笑点产出钩——池不变（读不写）"
        pl = [p for p in events if p.get("resource_id") == "punchline"]
        assert len(pl) == 1 and pl[0]["actor"] == "900201" and pl[0]["current"] == 5.0, (
            "事件 actor 记持有者（模板 $event.actor 口径不变）")
        snap = eng.state.snapshot()
        assert snap["punchline"] == 5.0, "B16：队伍池进快照"


class TestCertifiedBanger:
    def _grant(self, eng, aid, amount):
        eng._gain_resource(eng.state.actors[aid], "certified_banger", float(amount))

    def test_entries_merge_read_and_expiry(self, roots):
        """条目列表：两次获得合并读（20+30=50）；res_/resource_of 同值；
        持有者 owner_turn_end 两拍后到期除名（spec 固定 2 回合）。"""
        eng = _make(roots)
        st = eng.state.actors["900201"]
        self._grant(eng, "900201", 20)
        self._grant(eng, "900201", 30)
        assert len(st.banger_entries) == 2
        assert eng._resource_value(st, "certified_banger") == 50.0, "合并值=条目加和"
        assert eng._res_ns(st)["res_certified_banger"] == 50.0
        snap = st.snapshot()
        assert snap["banger_entries"] == [{"value": 20.0, "turns": 2.0},
                                          {"value": 30.0, "turns": 2.0}], "B16：条目进快照"
        eng._tick_modifiers(st, "owner_turn_end")
        assert eng._resource_value(st, "certified_banger") == 50.0, "第一拍后仍在（turns 2→1）"
        assert [e["turns"] for e in st.banger_entries] == [1.0, 1.0]
        eng._tick_modifiers(st, "owner_turn_end")
        assert eng._resource_value(st, "certified_banger") == 0.0, "第二拍后到期除名"
        assert st.banger_entries == []
        assert any("好活当赏" in line and "到期" in line for line in eng.state.log)

    def test_other_anchor_untouched(self, roots):
        """计时锚隔离：非 owner_turn_end 拍不扣（与 modifier tick_anchor 同语义）。"""
        eng = _make(roots)
        st = eng.state.actors["900201"]
        self._grant(eng, "900201", 20)
        eng._tick_modifiers(st, "owner_turn_start")
        assert [e["turns"] for e in st.banger_entries] == [2.0], "异锚不扣"
