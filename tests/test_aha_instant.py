"""阿哈时刻调度主体（B40 P2b）端到端：生成/速度公式/回合流程（解控→编号序代放→
授好活当赏→清池）/波次重置豁免/额外阿哈时刻（aha_instant effect）/事件词表。

模子同 P1a 批（tmp_path 微型模板）。口径：欢愉甲 spd 200 / 欢愉乙 spd 150 →
阿哈速度 = 80+200×0.2+150×0.1 = 135；参演编号 乙116 < 甲120（编号小先放）；
等级系数 7535.107、假人 def 1000 → 0.5、雷弱点 → 1.0、未击破 0.9、期望暴击 1.025、
面板 elation 0.5（×1.5）；pool=30 → multi=1+150/270≈1.5556；额外时刻=固定 20。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier

LV_COEF = 7535.107
DEF_ZONE = 0.5
CRIT_EXP = 1.025

_A = """\
actor_id: "900401"
name: "欢愉甲"
level: 80
elation_number: 120
path: "elation"
base_stats: {atk: 1000, spd: 200, hp: 3000, max_energy: 100, elation: 0.5,
             crit_rate: 0.05, crit_dmg: 0.5}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "thunder"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
  - action_id: "t_ea"
    name: "甲欢愉技"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "thunder"
    scaling: [{elation: 0.5}]
"""

_B = """\
actor_id: "900402"
name: "欢愉乙"
level: 80
elation_number: 116
path: "elation"
base_stats: {atk: 1000, spd: 150, hp: 3000, max_energy: 100, elation: 0.5,
             crit_rate: 0.05, crit_dmg: 0.5}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "thunder"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
  - action_id: "t_eb"
    name: "乙欢愉技"
    action_type: "elation_skill"
    target_type: "aoe"
    damage_type: "thunder"
    scaling: [{elation: 0.3}]
"""

_EXTRA = """\
actor_id: "900404"
name: "额外时刻测试员"
level: 80
path: "harmony"
base_stats: {atk: 1000, spd: 100, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_ult"
    name: "额外时刻号令"
    action_type: "ultimate"
    target_type: "self"
    scaling: []
    energy_cost: 100
hooks:
  - event: "on_ultimate"
    condition: "$event.source == '900404' && $event.action == 't_ult'"
    effects:
      - effect_type: "aha_instant"
"""

_PLAIN = """\
actor_id: "900405"
name: "凡人测试员"
level: 80
path: "destruction"
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
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture()
def roots(tmp_path):
    d = tmp_path / "characters"
    d.mkdir()
    for fname, body in {
        "900401_欢愉甲.yaml": _A, "900402_欢愉乙.yaml": _B,
        "900404_额外时刻.yaml": _EXTRA, "900405_凡人.yaml": _PLAIN,
    }.items():
        (d / fname).write_text(body, encoding="utf-8")
    return [str(tmp_path)]


def _make(roots, team=("900401", "900402")):
    c = compile_encounter({"build": {"team": [
        {"character_template": t, "level": 80} for t in team],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}},
        _STAGE, template_roots=roots)
    eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


class TestAhaSpawn:
    def test_spawn_speed_formula_and_battle_start_pool(self, roots):
        """进战在条：速度=80+200×0.2+150×0.1=135；进战每欢愉角色 +1 笑点（池=2）。"""
        eng = _make(roots)
        aha = eng.state.actors.get("aha_instant")
        assert aha is not None, "队伍有欢愉角色→阿哈在条"
        assert aha.actor.actor_type == "aha"
        assert math.isclose(aha.actor.stats.spd, 135.0), "速度公式 80+0.2V1+0.1V2"
        assert eng.state.punchline == 2.0, "进战每欢愉角色 +1（队伍账）"
        handle = eng.scheduler.handle_of("aha_instant")
        assert handle in eng.scheduler._wave_reset_exempt, "波次重置豁免注册（转面不重跑）"

    def test_no_elation_no_aha(self, roots):
        """无欢愉角色 → 无阿哈单位、笑点池静置 0。"""
        eng = _make(roots, team=("900405",))
        assert "aha_instant" not in eng.state.actors
        assert eng.state.punchline == 0.0

    def test_aha_not_ally(self, roots):
        """阿哈不算我方单位：选择器/全灭判定/光环辐射统一排除。"""
        eng = _make(roots)
        assert all(s.actor.actor_type != "aha" for s in eng._allies_alive())


class TestAhaTurn:
    def test_full_procedure_order_and_account(self, roots):
        """回合流程：编号序代放（乙116 先于 甲120）→ 授好活当赏（值=消耗池）→
        清池 → 事件词表 start/end（extra=0）。"""
        eng = _make(roots)
        eng.state.punchline = 30.0
        events = []
        eng.bus.subscribe("on_action", lambda et, p, s: events.append(("act", p)))
        eng.bus.subscribe("aha_instant_start", lambda et, p, s: events.append(("start", p)))
        eng.bus.subscribe("aha_instant_end", lambda et, p, s: events.append(("end", p)))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        eng._run_aha_turn()
        kinds = [k for k, _ in events]
        assert kinds.index("start") < kinds.index("act") < kinds.index("end"), "事件序"
        inserts = [p for k, p in events if k == "act" and p.get("insert")]
        assert [p["actor"] for p in inserts] == ["900402", "900401"], (
            "参演编号升序代放（乙 116 → 甲 120）")
        multi = 1 + 5 * 30 / (30 + 240)
        expect = (LV_COEF * (0.3 + 0.5) * 1.5 * multi * CRIT_EXP * DEF_ZONE * 0.9)
        assert math.isclose(hp - tgt.current_hp, expect, rel_tol=1e-9), (
            "双欢愉技共用实时池 30 结算（全体共享总值，非逐人扣减）")
        assert eng.state.punchline == 0.0, "清池"
        for aid in ("900401", "900402"):
            st = eng.state.actors[aid]
            assert eng._resource_value(st, "certified_banger") == 30.0, (
                "授好活当赏=消耗池值（逐角色账）")
        pl = [p for k, p in events if k == "end"][0]
        assert pl["consumed"] == 30.0 and pl["extra"] == 0
        assert pl["actors"] == ["900402", "900401"]

    def test_cleanse_control(self, roots):
        """解控：欢愉角色的控制类可驱散件在阿哈时刻摘除（非控制件不动）。"""
        eng = _make(roots)
        st = eng.state.actors["900401"]
        eng._modifiers._apply_modifier(st, Modifier(
            modifier_id="T_FREEZE", name="测试冻结", modifier_type="debuff",
            duration=2, dispellable=True, control_kind="freeze"))
        eng._modifiers._apply_modifier(st, Modifier(
            modifier_id="T_VULN", name="测试易伤", modifier_type="debuff",
            duration=2, dispellable=True))
        eng._run_aha_turn()
        assert "T_FREEZE" not in st.modifiers, "控制件解除"
        assert "T_VULN" in st.modifiers, "非控制件不摘"


class TestExtraAha:
    def test_extra_fixed_20_pool_untouched(self, roots):
        """额外阿哈时刻（aha_instant effect）：固定 20 结算——行动段按 20 不按实时池、
        池不清、授 20 好活当赏、extra=1。"""
        eng = _make(roots, team=("900401", "900404"))
        eng.state.punchline = 30.0
        events = []
        eng.bus.subscribe("aha_instant_end", lambda et, p, s: events.append(p))
        tgt = eng.state.actors["e1"]
        hp = tgt.current_hp
        st = eng.state.actors["900404"]
        st.current_energy = 100.0
        ult = eng.actions_by_actor["900404"][0]
        assert eng._fire_ultimate(st, ult) is True
        multi = 1 + 5 * 20 / (20 + 240)
        expect = LV_COEF * 0.5 * 1.5 * multi * CRIT_EXP * DEF_ZONE * 0.9
        assert math.isclose(hp - tgt.current_hp, expect, rel_tol=1e-9), (
            "欢愉技按固定 20 结算（_aha_pool_override 覆写锚——实时池 30 不误取）")
        assert eng.state.punchline == 30.0, "额外时刻不耗池"
        assert eng._resource_value(eng.state.actors["900401"], "certified_banger") == 20.0
        assert events and events[0]["extra"] == 1 and events[0]["consumed"] == 20.0


class TestWaveExempt:
    def test_wave_reset_skips_aha(self, roots):
        """转波次：全体剩余距离重置 10000，阿哈豁免续跑（「转面不重跑」）。"""
        stage2 = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人一", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100, "weakness": ["thunder"]}],
            "waves": [{"wave_index": 1, "enemies": [
                {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
                 "def": 1000, "max_toughness": 100, "weakness": ["thunder"]}]}],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
        c = compile_encounter({"build": {"team": [
            {"character_template": "900401", "level": 80},
            {"character_template": "900402", "level": 80}],
            "policy": {"name": "p", "action_rules": [
                {"condition": "true", "action": "basic", "priority": 0}]}}},
            stage2, template_roots=roots)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        handle = eng.scheduler.handle_of("aha_instant")
        eng.scheduler._remaining[handle] = 4321.0       # 跑了一半的阿哈
        h_mate = eng.scheduler.handle_of("900401")
        eng.scheduler.reset_action_gauge(except_countdown=True)
        assert eng.scheduler._remaining[handle] == 4321.0, "阿哈跨波按原行动值续跑"
        assert eng.scheduler._remaining[h_mate] == 10000.0, "其余单位照常重置"
