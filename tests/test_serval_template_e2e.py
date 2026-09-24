"""希露瓦 1103 模板端到端对轴（验收型批·组2）：真模板 YAML → 编译 → 触电两族/
天赋附加/延长语义/行迹/星魂全链 → 手算全等.

过堂两件（fixture 头注同录）：~~触电 modifier_type dot→debuff~~（native 通道
未接线）——**2026-09-22 双通道合并回迁**：触电两族（SHOCK_SKILL/SHOCK_TECH）
迁声明式 dot 通道（不暴击+施加时刻快照+EHR 命中区截 1.0 中性，R-SV1 暴击区差
消灭）/ 终结技延长 refresh→adjust_duration +2（≠refresh 重写实证）。

口径常数：希露瓦白值 atk 652.68、crit 0.237/0.5（0.05+行迹 crit_rate 0.187
B-TR① 回填——期望暴击区 1.1185）；假人 def 0 → 防御区 0.5、雷弱点 →
抗性区 1.0、未击破 0.9。普攻 lv6=1.0。触电跳伤 lv10 param(110302,5)=1.04；
天赋附加 lv10 param(110304,1)=0.72。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

SV_ATK = 652.68
Z = 0.5 * 0.9 * (1 + 0.237 * 0.5)   # 暴击区 1.1185（行迹 crit_rate 0.187 回填——B-TR①）
SHOCK = 1.04          # param(110302,5) lv10
CHORD = 0.72          # param(110304,1) lv10


def _build(*, eidolon: int = 0):
    member = {"character_template": "1103", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _sv(eng):
    return eng.state.actors["1103"]


def _cast(eng, owner, aid, *, target=None):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    m7 = _sv(eng)
    m7.current_energy = 100.0
    ult = next(a for a in eng.actions_by_actor["1103"] if a.action_id == "110303")
    assert eng._fire_ultimate(m7, ult) is True


class TestServalCompile:
    def test_battle_start_energy(self, compiled):
        eng = _make(compiled)
        assert math.isclose(_sv(eng).current_energy, 15.0), "String Vibration 开战 +15"


class TestSkillShock:
    def test_blast_shock_and_chord(self, compiled):
        """战技：主 1.4/邻 0.6 对轴 + 双目标触电挂载 + 天赋对全体触电者 0.72."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1103", "110302")
        assert math.isclose(hp1 - e1.current_hp, (1.4 + CHORD) * SV_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, (0.6 + CHORD) * SV_ATK * Z, rel_tol=1e-9)
        assert "SHOCK_SKILL" in e1.modifiers and "SHOCK_SKILL" in e2.modifiers
        assert e1.modifiers["SHOCK_SKILL"].modifier_type == "dot", (
            "声明式 DoT 通道承载（2026-09-22 双通道合并——native dot 接线回迁）")

    def test_shock_tick(self, compiled):
        """触电跳伤 = 1.04×ATK×0.45（声明式 dot 通道：不暴击；EHR 0.18 命中区
        min(1, 1.0×1.18) 截 1.0 权重中性）."""
        eng = _make(compiled)
        _cast(eng, "1103", "110302")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng._tick_dots(e1)   # 声明式跳伤走引擎 A 类结算（非 on_turn_start 事件）
        assert math.isclose(hp1 - e1.current_hp, SHOCK * SV_ATK * 0.45, rel_tol=1e-9)


class TestUltimate:
    def test_ult_extends_shock_by_two(self, compiled):
        """大招延长：adjust_duration +2（剩 1 → 3——refresh 重写 4 不等价勘正实证）."""
        eng = _make(compiled)
        _cast(eng, "1103", "110302")
        e1 = eng.state.actors["e1"]
        assert e1.modifiers["SHOCK_SKILL"].duration == 2
        eng._tick_modifiers(e1, "owner_turn_end")   # 走 1 字 → 剩 1
        assert e1.modifiers["SHOCK_SKILL"].duration == 1
        e2 = eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, (1.8 + CHORD) * SV_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, (1.8 + CHORD) * SV_ATK * Z, rel_tol=1e-9)
        assert e1.modifiers["SHOCK_SKILL"].duration == 3, "1+2 延长（≠refresh 重写 4）"
        assert math.isclose(_sv(eng).current_energy, 5.0)


class TestEidolons:
    def test_e1_splash_and_e2_energy(self):
        """E1 普攻溅射 0.6×普攻倍率 + E2 触电在场自身行动 +4 能（触电需先挂）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1103", "110302")   # 挂触电（E2 门控成立）
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1103", "110301")
        assert math.isclose(hp1 - e1.current_hp,
                            (1.0 + 0.6 * 1.0 + CHORD) * SV_ATK * Z, rel_tol=1e-9), (
            "普攻 + E1 溅射（0.6×普攻 lv6=1.0 倍率）+ 天赋附加")
        assert math.isclose(_sv(eng).current_energy, 15.0 + 30.0 + 20.0 + 4.0 + 4.0), (
            "开战 15 + 战技 30 + 普攻 20 + E2 两次 ×4")

    def test_e4_ult_shocks_unshocked(self):
        """E4：大招对未触电目标补挂触电（已触电者不动）."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        # 只手动挂 e1（模拟先验触电——战技会 e1/e2 同挂，故直挂单点），e2 未挂
        from hsr_nous.sim.state import Modifier
        eng._apply_modifier(eng.state.actors["e1"], Modifier(
            modifier_id="SHOCK_SKILL", name="触电", modifier_type="debuff", duration=1))
        _ult(eng)
        e2 = eng.state.actors["e2"]
        assert "SHOCK_SKILL" in e2.modifiers, "E4 补挂未触电目标"
        assert eng.state.actors["e1"].modifiers["SHOCK_SKILL"].duration == 3, (
            "e1 先验触电走延长 1+2=3（E4 不重挂）")

    def test_e6_true_bonus(self):
        """E6：雷伤命中触电目标 +30% 真伤段（E3 普攻 lv7=1.1、E5 天赋 lv12=0.792
        全联动在案；普攻/溅射/天赋三段雷伤各吃真伤——真伤段自身不递归）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1103", "110302")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1103", "110301")
        hits = (1.1 + 0.6 * 1.1 + 0.792) * SV_ATK * Z   # 普攻 lv7 + E1 溅射 + 天赋 lv12
        assert math.isclose(hp1 - e1.current_hp, hits * 1.3, rel_tol=1e-9)

    def test_mania_kill_atk(self, compiled):
        """Mania：击杀 ATK+20% 二回合."""
        eng = _make(compiled)
        e2 = eng.state.actors["e2"]
        e2.current_hp = 100.0
        _cast(eng, "1103", "110302", target=e2)   # 主目标 e2 击杀
        assert not e2.alive
        assert "MANIA_ATK" in _sv(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_sv(eng))["atk"],
                            SV_ATK * 1.2, rel_tol=1e-9)
