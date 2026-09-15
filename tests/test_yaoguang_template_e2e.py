"""爻光 1502 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 结界/笑点账/好活当赏/
大吉大利/欢愉技/行迹/星魂全链 → 手算全等（过堂勘正十四件见 fixture 头注）。

口径常数：爻光 atk 465.696；行迹后实战面板 crit_rate 0.237（0.05+0.187）、
crit_dmg 1.1（0.5+0.6）→ 期望暴击区 1+0.237×1.1=1.2607；spd 110（101+9）。
辅手 atk 1500、crit 0.05/0.5 → 期望暴击区 1.025。假人 def 1000 → 防御区 0.5、
物理弱点 → 抗性区 1.0、未击破 0.9。Z=0.5×0.9×1.2607=0.567315。
大吉大利/150220 伤害为 ATK 基数占位（欢愉管线待收②——只对轴 DSL 接线）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

YG_ATK = 465.696
Z = 0.5 * 0.9 * (1 + 0.237 * 1.1)          # 防御区×未击破×期望暴击区（行迹后面板）
Z_ALLY = 0.5 * 0.9 * 1.025
ALLY_BASIC = 1500 * 1.0 * Z_ALLY           # 辅手普攻期望 = 691.875


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1502", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True, "element": "physical",
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1502", "technique": "150207"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _yg(eng):
    return eng.state.actors["1502"]


def _cast(eng, owner, aid, target_id="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _yg(eng)
    st.current_energy = 180.0
    ult = next(a for a in eng.actions_by_actor["1502"] if a.action_id == "150203")
    assert eng._fire_ultimate(st, ult) is True


class TestYaoGuangCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1502"]}
        assert acts == {"150201", "150202", "150203", "150220"}
        decls = compiled.resource_decls_by_actor["1502"]
        assert set(decls) == {"punchline", "aha_turn"}

    def test_elation_skill_sealed(self, compiled):
        """欢愉技 available_if 封手动后门（勘正⑤）：res_aha_turn 恒 0 → 不可用."""
        eng = _make(compiled)
        a = next(x for x in eng.actions_by_actor["1502"] if x.action_id == "150220")
        assert eng._available_if_ok(_yg(eng), a) is False


class TestBattleStart:
    def test_loadout(self, compiled):
        """开局三件：进战 +1 笑点（欢愉角色×1）/ 好活当赏 20 层 3 回合 / 行迹面板."""
        eng = _make(compiled)
        st = _yg(eng)
        assert math.isclose(eng.state.punchline, 1.0), "§8.2 进战每欢愉角色 +1"
        cb = st.modifiers["CERTIFIED_BANGER"]
        assert math.isclose(cb.stacks, 20.0) and math.isclose(cb.duration, 3.0), (
            "§8.1 进战 20 点，2+行迹1=3 回合")
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.237, rel_tol=1e-9), "0.05+行迹0.187"
        assert math.isclose(eff["crit_dmg"], 1.1, rel_tol=1e-9), "0.5+神闲意满0.6"
        assert math.isclose(eff["spd"], 110.0, rel_tol=1e-9), "101+行迹9"


class TestBasicAndZone:
    def test_basic_blast_self_great_boon(self, compiled):
        """普攻 lv6：主 0.9/邻 0.30 + 大吉大利 0.2（我方目标含自身——勘正③）；结界未起笑点不涨."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150201")
        assert math.isclose(hp1 - e1.current_hp, YG_ATK * (0.9 + 0.2) * Z, rel_tol=1e-9), (
            "主目标 = 普攻 0.9 + 大吉大利 0.2")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * 0.30 * Z, rel_tol=1e-9), "相邻 0.30（lv6）"
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点"
        assert math.isclose(_yg(eng).current_energy, 30.0), "普攻回能 30（官方文本）"
        assert math.isclose(eng.state.punchline, 1.0), "结界未起 → +0"

    def test_skill_zone_punchline_snapshot(self, compiled):
        """战技：挂结界（3 回合自身回合开始走字）+ 首技即得 3 笑点（勘正②快照补偿）；
        结界持续期间普攻/战技各 +3."""
        eng = _make(compiled)
        st = _yg(eng)
        hp1 = eng.state.actors["e1"].current_hp
        _cast(eng, "1502", "150202", target_id="1502")
        assert "ELATION_ZONE" in st.modifiers
        assert math.isclose(st.modifiers["ELATION_ZONE"].duration, 3.0)
        assert math.isclose(eng.state.punchline, 4.0), "1+3（首技即得——快照补偿在案）"
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点"
        assert math.isclose(st.current_energy, 30.0), "战技回能 30（fandom）"
        assert math.isclose(hp1 - eng.state.actors["e1"].current_hp, 0.0), (
            "支援技主目标非敌 → 不触发大吉大利")
        _cast(eng, "1502", "150201")
        assert math.isclose(eng.state.punchline, 7.0), "结界期间普攻 +3"
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.state.punchline, 10.0), "结界期间战技 +3（refresh 不双挂）"
        assert math.isclose(st.modifiers["ELATION_ZONE"].duration, 3.0)


class TestUltimate:
    def test_res_pen_punchline_energy(self, compiled):
        """终结技 lv10：+5 笑点 / 全队全抗穿 +20%（每持有者 3 回合）/ 回 5 能——抗穿实伤链."""
        eng = _make(compiled)
        _ult(eng)
        st = _yg(eng)
        assert math.isclose(eng.state.punchline, 6.0), "1+5"
        assert math.isclose(st.current_energy, 5.0), "180 全扣后回 5"
        assert "ULT_RES_PEN" in st.modifiers and "ULT_RES_PEN" in eng.state.actors["ally"].modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"],
                            0.2, rel_tol=1e-9)
        # 抗穿入伤：敌方 0 抗 → 抗性区 1-(0-0.2)=1.2
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            (ALLY_BASIC + YG_ATK * 0.2 * Z) * 1.2, rel_tol=1e-9), (
            "辅手普攻+大吉大利，抗穿 0.2 → ×1.2")


class TestElationSkill:
    def test_full_chain(self, compiled):
        """欢愉技 lv10（手动对轴）：凶星低语 16% 先挂→AoE 1.0 全体 + 随机 5×0.2（expected
        确定化首敌）+ 大吉大利 0.2（施放攻击触发）+ 行迹回 1 点；不回能不涨笑点."""
        eng = _make(compiled)
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.16, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e2)["vulnerability"], 0.16, rel_tol=1e-9)
        assert math.isclose(hp1 - e1.current_hp,
                            YG_ATK * Z * 1.16 * (1.0 + 5 * 0.2 + 0.2), rel_tol=1e-9), (
            "AoE1.0+随机5×0.2+大吉大利0.2，易伤 ×1.16")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * Z * 1.16 * 1.0, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "行迹 1502102：欢愉技回 1 点（勘正⑨）"
        assert math.isclose(st.current_energy, 0.0), "回能保守 0（fandom 无条目待实测）"
        assert math.isclose(eng.state.punchline, 1.0), "欢愉技不产笑点"


class TestGreatBoonGate:
    def test_gate_and_attack_filter(self, compiled):
        """大吉大利门控：有好活当赏→辅手攻击附带 0.2；摘除→不触发；爻光支援技不打敌→不触发."""
        eng = _make(compiled)
        st = _yg(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, ALLY_BASIC + YG_ATK * 0.2 * Z, rel_tol=1e-9), (
            "辅手 691.875 + 大吉大利（占位 ATK 基数）")
        eng._remove_modifier(st, "CERTIFIED_BANGER", "test")
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, ALLY_BASIC, rel_tol=1e-9), "门摘 → 无附带"
        hp1 = e1.current_hp
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(hp1 - e1.current_hp, 0.0), "支援技（主目标非敌）不触发"


class TestEidolons:
    def test_e2_zone_spd_gate(self):
        """E2：结界持续期间我方 SPD +12%（enable_if 门控勘正⑭）——无结界 110/90，起界
        122.12/100.8（spd_pct 按白值 101 乘算，行迹 flat +9 另加——Layer 1.5 口径）."""
        eng = _make(_compiled(eidolon=2))
        st = _yg(eng)
        assert "E2_ZONE_SPD" in st.modifiers, "常驻件在（未启用）"
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 110.0, rel_tol=1e-9), (
            "结界未起 → 不启用")
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["spd"],
                            90.0, rel_tol=1e-9)
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 101 * 1.12 + 9, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["spd"],
                            90 * 1.12, rel_tol=1e-9), "team scope 同吃"

    def test_e2_technique_path(self):
        """E2 + 秘技开战：结界已在 → 速度件开局即启用（enable_if 双路径同真勘正⑭）."""
        eng = _make(_compiled(eidolon=2, pre_battle=True))
        assert "ELATION_ZONE" in _yg(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_yg(eng))["spd"],
                            101 * 1.12 + 9, rel_tol=1e-9)

    def test_e3_level_tracks(self):
        """E3（含 E2）：欢愉技 lv11（AoE 1.05/段 0.21）、普攻 lv7（0.99/0.33）、结界 SPD +12%."""
        eng = _make(_compiled(eidolon=3))
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")
        assert math.isclose(hp1 - e1.current_hp,
                            YG_ATK * Z * 1.16 * (1.05 + 5 * 0.21 + 0.2), rel_tol=1e-9), (
            "lv11 AoE1.05+5×0.21；天赋仍 lv10 → 大吉大利 0.2")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * Z * 1.16 * 1.05, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150201")   # 凶星低语 3 回合仍在 → 本次伤害同吃 1.16
        assert math.isclose(hp1 - e1.current_hp, YG_ATK * (0.99 + 0.2) * Z * 1.16, rel_tol=1e-9), (
            "普攻 lv7 主 0.99（易伤存续 ×1.16）")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * 0.33 * Z * 1.16, rel_tol=1e-9), (
            "lv7 邻 0.33（易伤存续 ×1.16）")
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 101 * 1.12 + 9, rel_tol=1e-9), (
            "E2 随 eidolon=3 联动")

    def test_e5_level_tracks(self):
        """E5：终结技 lv12 → 抗穿 0.22；天赋 lv12 → 大吉大利 0.22（抗穿后 ×1.22）."""
        eng = _make(_compiled(eidolon=5))
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(_yg(eng))["res_pen"], 0.22, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            (ALLY_BASIC + YG_ATK * 0.22 * Z) * 1.22, rel_tol=1e-9), (
            "天赋 lv12 大吉大利 0.22；抗穿 0.22 → 抗性区 1.22")

    def test_e5_elation_skill_lv12(self):
        """E5（含 E3）：欢愉技 lv12 → AoE 1.1/段 0.22；天赋 lv12 → 大吉大利 0.22."""
        eng = _make(_compiled(eidolon=5))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")
        assert math.isclose(hp1 - e1.current_hp,
                            YG_ATK * Z * 1.16 * (1.1 + 5 * 0.22 + 0.22), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * Z * 1.16 * 1.1, rel_tol=1e-9)

    def test_e6_compile_smoke(self):
        """E6  notes-only（待收⑤）：eidolon=6 编译+开局不炸，E2 速度链路仍真."""
        eng = _make(_compiled(eidolon=6))
        assert math.isclose(eng.state.punchline, 1.0)
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(_yg(eng))["spd"],
                            101 * 1.12 + 9, rel_tol=1e-9)


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技=开战自动触发 1 次战技（不耗点）：结界在 + 笑点 3+进战 1=4 + 回能 30（勘正⑩）."""
        eng = _make(_compiled(pre_battle=True))
        st = _yg(eng)
        assert "ELATION_ZONE" in st.modifiers
        assert math.isclose(eng.state.punchline, 4.0), "秘技触发战技 3 + 进战 1"
        assert math.isclose(st.current_energy, 30.0), "战技回能随本体（阮梅秘技同构）"
        assert math.isclose(eng.state.skill_points, 3.0), "不耗战技点"
        _cast(eng, "1502", "150201")
        assert math.isclose(eng.state.punchline, 7.0), "开局结界已在 → 普攻即 +3"
