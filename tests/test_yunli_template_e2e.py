"""云璃 1221 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 天赋反击/
Parry-Cull/兜底 Slash/真式/Demon Quell/星魂全链 → 手算全等.

过堂勘正七件+grants_immune 闸升级（fixture 头注同录）：回能 15 收录 /
Parry 任一回合结束 / action_type ultimate 声明 / crit_dmg+减伤补件 /
crowd_control 错拼+闸词表校验 / atk_pct 勘误 / 嘲讽挡因改写。

口径常数：云璃白值 atk 679.14 × 行迹攻 1.28（B-TR④ 回填——攻 0.28/生命 0.18/
暴击 0.067 官方十节点聚合）= 869.2992；crit 0.117/0.5（期望暴击区 1.0585；
Parry 件 crit_dmg+1.0 → 1.1755）；假人 def 0 → 防御区 0.5、物理弱点 →
抗性区 1.0、未击破 0.9。反击 lv10=1.2；Cull lv10 主 2.2 追加 6×0.72。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

YL_ATK = 679.14
YL_ATK_E = YL_ATK * 1.28                      # 869.2992（行迹 atk_pct 0.28——B-TR④）
Z = 0.5 * 0.9 * (1 + 0.117 * 0.5)             # CR 0.05+行迹 0.067=0.117 → 期望暴击区 1.0585
Z_PARRY = 0.5 * 0.9 * (1 + 0.117 * 1.5)       # Parry crit_dmg+1.0 期 → 1.1755


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1221", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    b = {"team": [member],
         "policy": {"name": "p", "action_rules": [
             {"condition": "true", "action": "skill", "priority": 50},
             {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _yl(eng):
    return eng.state.actors["1221"]


def _hit_yunli(eng, source="e1"):
    """敌方攻击云璃（on_hp_decrease 受击事件——反击触发点）."""
    eng.bus.emit("on_hp_decrease", {
        "amount": 100.0, "source": source, "reason": "hit", "target": "1221",
        "damage_type": "physical", "action_type": "basic",
        "is_critical": False}, eng.state)


def _ult(eng):
    yl = _yl(eng)
    yl.current_energy = 120.0
    ult = next(x for x in eng.actions_by_actor["1221"] if x.action_id == "122103")
    assert eng._fire_ultimate(yl, ult) is True


class TestTalentCounter:
    def test_counter_flash(self, compiled):
        """天赋反击（非 Parry）：受击 → 闪铄 1.2 + 回能 15 + True Sunder 挂上."""
        eng = _make(compiled)
        yl = _yl(eng)
        e1 = eng.state.actors["e1"]
        yl.current_energy = 50.0
        hp1 = e1.current_hp
        _hit_yunli(eng)
        assert math.isclose(hp1 - e1.current_hp, 1.2 * YL_ATK_E * Z, rel_tol=1e-9)
        assert math.isclose(yl.current_energy, 65.0), "官方 params #3=15"
        assert "TRUE_SUNDER_ATK" in yl.modifiers

    def test_sunder_carries_next_hit(self, compiled):
        """真式持续：第一发反击挂 ATK+30%（duration 1）——后续发吃到（联动钉）."""
        eng = _make(compiled)
        yl = _yl(eng)
        e1 = eng.state.actors["e1"]
        _hit_yunli(eng)   # 第一发挂真式
        hp1 = e1.current_hp
        _hit_yunli(eng)   # 第二发吃真式（atk ×1.3）
        assert math.isclose(hp1 - e1.current_hp,
                            1.2 * YL_ATK * (1.28 + 0.3) * Z, rel_tol=1e-9), (
            "真式 atk_pct 0.3 与行迹 0.28 同池加算 → ×1.58")


class TestParryCull:
    def test_ult_parry_modifiers(self, compiled):
        """大招：Parry 挂上——免疫控制+减伤 0.2+crit_dmg+1.0（下一次反击）."""
        eng = _make(compiled)
        yl = _yl(eng)
        _ult(eng)
        m = yl.modifiers["YUNLI_PARRY"]
        assert m.grants_immune == ["control"]
        assert math.isclose(m.stat_effects["dmg_dmg_reduction"], 0.2)
        assert math.isclose(m.stat_effects["crit_dmg"], 1.0)

    def test_parry_hit_cull(self, compiled):
        """Parry 中受击 → Cull 主 2.2+追加 6×0.72（确定化同序首）+ 摘 Parry."""
        eng = _make(compiled)
        yl = _yl(eng)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        hp1 = e1.current_hp
        _hit_yunli(eng)
        expect = (2.2 + 6 * 0.72) * YL_ATK_E * Z_PARRY
        assert math.isclose(hp1 - e1.current_hp, expect, rel_tol=1e-9)
        assert "YUNLI_PARRY" not in yl.modifiers, "Cull 后摘除 Parry"

    def test_parry_expire_any_turn_end(self, compiled):
        """兜底：未受击——**敌人**回合结束也兜底 Slash（官方「任一回合结束」）."""
        eng = _make(compiled)
        yl = _yl(eng)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 2.2 * YL_ATK_E * Z_PARRY, rel_tol=1e-9)
        assert "YUNLI_PARRY" not in yl.modifiers
        assert math.isclose(yl.resources["_slash_toggle"], 1.0), (
            "Fiery Wheel 交替闩：本次 Slash → 下次兜底回 Cull")

    def test_parry_immune_control(self, compiled):
        """Demon Quell：Parry 期免疫控制（grants_immune ["control"] 词表校验后）."""
        eng = _make(compiled)
        _ult(eng)
        yl = _yl(eng)
        applied = eng._apply_modifier(yl, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="debuff",
            debuff_kind="control", duration=2))
        assert applied is False, "Parry 期免疫控制"


class TestEidolons:
    def test_e4_ult_effect_res(self):
        """E4：施放终结技后效果抵抗 +50% 1 回合."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _ult(eng)
        assert math.isclose(
            eng.pipeline.effective_stats(_yl(eng))["effect_res"], 0.5, rel_tol=1e-9)

    def test_e6_enemy_action_triggers_cull(self):
        """E6：Parry 期敌方主动施放任意技能即触发 Cull（触发域扩至施放不限攻击）."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        yl = _yl(eng)
        e1 = eng.state.actors["e1"]
        _ult(eng)
        hp1 = e1.current_hp
        eng.bus.emit("on_action", {"actor": "e1", "action_type": "skill",
                                   "action_id": "e_skill", "target_type": "self",
                                   "target": "e1", "actor_type": "monster"}, eng.state)
        assert (hp1 - e1.current_hp) > 0, "E6：敌方施放即触发 Cull（无需受击）"
        assert "YUNLI_PARRY" not in yl.modifiers


class TestTechnique:
    def test_ward_cull_amplified(self):
        """秘技 Ward：进战 Cull×1.8（主+追加 6 段确定化同序首）."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1221", "technique": "122107"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        expect = 1.8 * (2.2 + 6 * 0.72) * YL_ATK_E * Z
        assert math.isclose(1e9 - e1.current_hp, expect, rel_tol=1e-9)
