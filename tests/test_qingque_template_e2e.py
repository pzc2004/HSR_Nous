"""青雀 1201 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 抽牌循环/
暗杠状态机/强化普攻/终结技/行迹/星魂全链 → 手算全等.

过堂六件（fixture 头注同录）：牌战 SP 收编 / E1 类型桶 / E2 每张回能 /
E4 授予收编 / 战技不结束回合 / 终结技抽 4 张补钩。

口径常数：青雀白值 atk 652.68、crit 0.05/0.5（期望暴击区 1.025）；行迹 atk+28%/
量子+14.4%（B-TR② 已回填——面板 835.4304、增伤池 1.144；暗杠 ATK pct 池加算
×2.0=1305.36）；假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。
暗杠 ATK lv10 +72%；强化普攻 lv6 主 2.4/邻 1.0；终结技 lv10 2.0。普攻 lv6=1.0。
B-QQ①（对拍钓出）：听牌每层 +10%（社区层定谳——满层 152%）+replace 重烘。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

QQ_ATK = 652.68
QQ_EFF = QQ_ATK * 1.28                        # 835.4304（B-TR② 行迹 atk 0.28 回填后面板）
QQ_ANGANG = QQ_ATK * 2.0                      # 1305.36（pct 池 1+0.28+0.72）
QUANTUM = 0.144                               # 量子行迹增伤池（B-TR②）
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)


def _build(*, eidolon: int = 0):
    member = {"character_template": "1201", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _qq(eng):
    return eng.state.actors["1201"]


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


class TestQingqueCompile:
    def test_resources_available_if(self, compiled):
        decls = compiled.resource_decls_by_actor["1201"]
        assert decls["_tiles_hand"]["max"] == 4 and decls["_is_angang"]["max"] == 1
        assert "_tile_war_used" in decls, "牌战每场闩（收编件）"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1201"]}
        assert acts["120102"].available_if == "res__is_angang < 1"
        assert acts["120108"].available_if == "res__is_angang >= 1"


class TestTileDraw:
    def test_talent_draw_and_e2_energy(self, compiled):
        """天赋抽牌：任一友方回合开始 +1 张（E0 不回能——E2 未激活对照）."""
        eng = _make(compiled)
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        s = _qq(eng)
        assert math.isclose(s.resources["_tiles_hand"], 1.0)
        assert math.isclose(s.current_energy, 0.0), "E0 无 E2——抽牌不回能"

    def test_e2_energy_per_tile(self):
        """E2：每抽 1 张回 1 能（on_resource_gain 按量收编——战技抽 2 回 2）."""
        compiled = compile_encounter(_build(eidolon=2), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(_qq(eng).current_energy, 1.0), "天赋抽 1 回 1"
        _cast(eng, "1201", "120102")
        assert math.isclose(_qq(eng).current_energy, 3.0), "战技抽 2 回 2（每张计）"


class TestSkill:
    def test_skill_draw_sp_stack(self, compiled):
        """战技：抽 2 张 + 增伤叠层 1 层（0.28）+ 争番 0.1 + 牌战返 SP（净 0 耗首发）
        + 不结束回合（grant_extra_turn 收编在案）."""
        eng = _make(compiled)
        sp0 = eng.state.skill_points
        _cast(eng, "1201", "120102")
        s = _qq(eng)
        assert math.isclose(s.resources["_tiles_hand"], 2.0)
        assert math.isclose(eng.state.skill_points, sp0), "牌战 −1+1 净 0（gain_skill_point 收编）"
        assert math.isclose(s.resources["_tile_war_used"], 1.0), "每场闩"
        eff = eng.pipeline.effective_stats(s)
        assert math.isclose(eff["dmg_bonus"].get("all", 0.0), 0.28 + 0.1, rel_tol=1e-9), (
            "叠层 1 层 0.28 + 争番 0.1")
        _cast(eng, "1201", "120102")
        assert math.isclose(eng.state.skill_points, sp0 - 1), "二发不返（闩在场）"


class TestAngang:
    def test_angang_enter_attack_exit(self, compiled):
        """暗杠：4 张判满 → 消耗全部牌 + ATK+72% + 战技硬闸；强化普攻主 2.4/邻 1.0
        + 解闸摘件 + 抢杠 SPD+10%."""
        eng = _make(compiled)
        s = _qq(eng)
        s.resources["_tiles_hand"] = 4.0
        eng.bus.emit("on_turn_start", {"actor": "1201"}, eng.state)
        assert math.isclose(s.resources["_tiles_hand"], 0.0)
        assert math.isclose(s.resources["_is_angang"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(s)["atk"], QQ_ANGANG, rel_tol=1e-9), (
            "pct 池加算 ×2.0（B-TR② 行迹 0.28 入池）")
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1201", "120108")
        atk = QQ_ANGANG
        assert math.isclose(hp1 - e1.current_hp, 2.4 * atk * Z * (1 + QUANTUM), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.0 * atk * Z * (1 + QUANTUM), rel_tol=1e-9)
        assert math.isclose(s.resources["_is_angang"], 0.0), "施放后解闩"
        assert "ANGANG_ATK" not in s.modifiers, "摘 ATK 件"
        assert math.isclose(eng.pipeline.effective_stats(s)["spd"], 98 * 1.1, rel_tol=1e-9), (
            "抢杠 SPD+10%")


class TestUltimate:
    def test_ult_aoe_draw_energy(self, compiled):
        """大招：AoE 2.0 对轴 + 抽 4 张（set 补满——E2 set 语义不回能在案）+ 回能 5."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        m7 = _qq(eng)
        m7.current_energy = 140.0
        e0 = m7.current_energy
        ult = next(a for a in eng.actions_by_actor["1201"] if a.action_id == "120103")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.0 * QQ_EFF * Z * (1 + QUANTUM), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 2.0 * QQ_EFF * Z * (1 + QUANTUM), rel_tol=1e-9)
        assert math.isclose(m7.resources["_tiles_hand"], 4.0), "set 4 补满"
        assert math.isclose(m7.current_energy, 5.0), (
            "set 语义不发 on_resource_gain——E0/E2 均不因补牌回能（量差在案）")


class TestEidolons:
    def test_e1_ult_boost(self):
        """E1：终结技伤害 +10%（dmg_ultimate_dmg_boost 收编实证）."""
        compiled = compile_encounter(_build(eidolon=1), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        m7 = _qq(eng)
        m7.current_energy = 140.0
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1201"] if a.action_id == "120103")
        assert eng._fire_ultimate(m7, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 2.0 * QQ_EFF * Z * (1 + QUANTUM + 0.1),
                            rel_tol=1e-9), "E1 终结技增伤 0.1 与量子 0.144 同池加算"

    def test_e4_grant_expected_off_and_follow(self):
        """E4：expected 口径 24% 恒不授予（mechanic_chance 双态钉）；手动挂标记 →
        普攻追加 100% 原伤段."""
        compiled = compile_encounter(_build(eidolon=4), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        _cast(eng, "1201", "120102")
        assert "E4_SELF_SUFFICER" not in _qq(eng).modifiers, "expected 不授予（0.24<0.5）"
        eng._apply_modifier(_qq(eng), Modifier(
            modifier_id="E4_SELF_SUFFICER", name="Self-Sufficer",
            modifier_type="buff", duration=1, tick_anchor="owner_turn_end"))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1201", "120101")
        assert math.isclose(hp1 - e1.current_hp,
                            2 * (1.0 * QQ_EFF * Z * (1 + QUANTUM + 0.38)), rel_tol=1e-9), (
            "普攻（叠层 0.28+听牌 0.1=0.38/层×1 +量子 0.144=1.524 区——B-QQ① 每层读）"
            "+ 100% 原伤真伤段（category true 压缩实证）")

    def test_e6_sp_refund(self):
        """E6：强化普攻后返 1 SP（gain_skill_point 收编——净产 +1 在案）."""
        compiled = compile_encounter(_build(eidolon=6), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        s = _qq(eng)
        s.resources["_tiles_hand"] = 4.0
        eng.bus.emit("on_turn_start", {"actor": "1201"}, eng.state)
        sp0 = eng.state.skill_points
        _cast(eng, "1201", "120108")
        assert math.isclose(eng.state.skill_points, sp0 + 1.0)
