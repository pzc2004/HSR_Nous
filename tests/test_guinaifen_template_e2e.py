"""桂乃芬 1210 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 灼烧链/
FIREKISS 层数驱动/爆燃/Walking on Knives 真伤/星魂全链 → 手算全等.

过堂勘正四件（fixture 头注同录）：FIREKISS vulnerability+stat_exprs 动态层数 /
E4 gain_energy 内建通道 / WoK 真伤 damage_type 留源元素 / High Poles
mechanic_chance(0.8) 概率通道——**2026-09-22 双通道合并**：灼烧 DoT 迁声明式
dot 通道（不暴击+施加时刻快照+dot_base_chance 期望权重），FIREKISS/E4 触发点
随迁 on_hp_decrease reason='dot'（跳伤后挂层/回能序保持）。

口径常数：桂乃芬白值 atk 582.12、spd 106、crit 0.05/0.5（期望暴击区 1.025）；
假人 def 0 → 防御区 0.5、火弱点 → 抗性区 1.0、未击破 0.9。
灼烧 lv10 #4=2.1821×atk；FIREKISS 每层 0.07 lv10（cap 3）；爆燃 lv10 #2=0.92。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

GNF_ATK = 582.12
Z = 0.5 * 0.9 * 1.025


def _build(*, eidolon: int = 0, pre_battle: list | None = None):
    member = {"character_template": "1210", "level": 80}
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
     "max_toughness": 9999, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _gnf(eng):
    return eng.state.actors["1210"]


def _cast(eng, aid, target_id="e1"):
    gnf = _gnf(eng)
    a = next(x for x in eng.actions_by_actor["1210"] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(gnf, a)
    eng.bus.emit("on_action", {
        "actor": "1210", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": gnf.actor.actor_type}, eng.state)


class TestGuinaifenCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1210"]
        assert {"_s2_burn", "_s6_fk"} <= set(decls)


class TestSkillBurn:
    def test_skill_blast_and_burn(self, compiled):
        """战技：主 1.2 邻 0.4 lv10 对轴 + 灼烧挂主目标（相邻灼烧待收在案）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "121002")
        assert math.isclose(hp1 - e1.current_hp, 1.2 * GNF_ATK * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.4 * GNF_ATK * Z, rel_tol=1e-9)
        assert "GUINAIFEN_BURN" in e1.modifiers
        assert "GUINAIFEN_BURN" not in e2.modifiers, "相邻灼烧通道缺在案"

    def test_burn_tick_and_firekiss(self, compiled):
        """灼烧 tick 2.1821×atk（lv10 #4，声明式 dot 通道：不暴击×0.45）+ WoK 真伤
        0.2（tick 经 on_hp_decrease damage_type='fire' 命中 WoK）+ FIREKISS 挂 1 层
        vuln 0.07（跳伤后挂层——当次跳不吃新层）."""
        eng = _make(compiled)
        _cast(eng, "121002")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng._tick_dots(e1)   # 声明式跳伤走引擎 A 类结算（非 on_turn_start 事件）
        burn = 2.1821 * GNF_ATK
        assert math.isclose(hp1 - e1.current_hp, burn * 0.45 * 1.2, rel_tol=1e-9), (
            "灼烧 ×0.45（不暴击）+ WoK 真伤 0.2（跳伤本体火伤同吃——官方未限定在案）")
        fk = e1.modifiers["FIREKISS"]
        assert fk.stacks == 1
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.07, rel_tol=1e-9), "stat_exprs 动态：1 层 0.07 lv10"
        # 第二跳：2 层 0.14（层数驱动实证）；tick 吃第一跳挂的 1 层 vuln ×1.07
        hp2 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp2 - e1.current_hp, burn * 0.45 * 1.07 * 1.2, rel_tol=1e-9), (
            "第二跳吃 1 层 FIREKISS vuln（跳伤时刻目标侧现值）")
        assert e1.modifiers["FIREKISS"].stacks == 2
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.14, rel_tol=1e-9)


class TestUltimate:
    def test_ult_detonate(self, compiled):
        """大招：全体 1.2 + 灼烧中目标爆燃 0.92×原灼烧（不清除）；无灼烧目标纯本体对照."""
        eng = _make(compiled)
        _cast(eng, "121002")   # e1 挂灼烧、e2 无
        gnf = _gnf(eng)
        gnf.current_energy = 120.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        # 清 FIREKISS 层数使时点干净（本例只对轴爆燃/本体构成）
        e1.modifiers.pop("FIREKISS", None)
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(x for x in eng.actions_by_actor["1210"] if x.action_id == "121003")
        assert eng._fire_ultimate(gnf, ult) is True
        # e1 = 大招 1.2 + 爆燃 0.92×2.1821 + WoK 两段 0.2×（大招额+爆燃额）——无 vuln（层已清）
        base_ult = 1.2 * GNF_ATK * Z
        base_det = 0.92 * 2.1821 * GNF_ATK * Z
        assert math.isclose(hp1 - e1.current_hp,
                            (base_ult + base_det) * 1.2, rel_tol=1e-9), (
            "本体+爆燃+WoK 双段（均 ×1.2 含真伤段）")
        assert math.isclose(hp2 - e2.current_hp, base_ult, rel_tol=1e-9), (
            "无灼烧：纯本体无爆燃无 WoK")
        assert "GUINAIFEN_BURN" in e1.modifiers, "爆燃不清除灼烧（官方无移除表述）"


class TestTraces:
    def test_high_poles_basic_burn(self, compiled):
        """High Poles：普攻挂灼烧（mechanic_chance(0.8)——expected 恒挂/roll 80%）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        _cast(eng, "121001")
        assert "GUINAIFEN_BURN" in e1.modifiers, "expected 口径 0.8≥0.5 恒挂"

    def test_walking_on_knives_direct_hit(self, compiled):
        """WoK：灼烧中目标的直击火伤追加真伤 0.2×原伤（category true 跳乘区等值口径）."""
        eng = _make(compiled)
        _cast(eng, "121002")   # 挂灼烧（此发无 WoK——伤害时目标尚无灼烧）
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "121001")   # 普攻 1.0 lv6——灼烧中 → +WoK 0.2
        basic = 1.0 * GNF_ATK * Z
        dealt = hp1 - e1.current_hp
        vuln = eng.pipeline.effective_stats(e1).get("vulnerability", 0.0)
        # 普攻吃 FIREKISS vuln（1 层 0.07，战技 tick 未发故仅灼烧挂时的 0 层？
        # ——灼烧挂在战技 on_action（伤害后），普攻时 0 层 vuln=0；WoK 真伤不吃 vuln）
        assert vuln == 0.0
        assert math.isclose(dealt, basic * 1.2, rel_tol=1e-9)


class TestEidolons:
    def test_e1_res_down(self):
        """E1：战技主目标效果抵抗 −10% 2 回合."""
        eng = _make(compile_encounter(_build(eidolon=1), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "121002")
        assert "E1_EFFECT_RES_DOWN" in e1.modifiers
        assert "E1_EFFECT_RES_DOWN" not in e2.modifiers, "限主目标（相邻受益待实测在案）"
        assert math.isclose(eng.pipeline.effective_stats(e1).get("effect_res", 0.0),
                            -0.1, rel_tol=1e-9)

    def test_s2_burn_multiplier(self):
        """S2：本体灼烧 ×1.4（dot_ratio 表达式烘焙——施加时刻读 res__s2_burn）."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast(eng, "121002")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng._tick_dots(e1)
        burn_s2 = 2.1821 * 1.4 * GNF_ATK
        assert math.isclose(hp1 - e1.current_hp, burn_s2 * 0.45 * 1.2, rel_tol=1e-9)

    def test_e4_tick_energy(self):
        """E4：本体灼烧每跳回 2 能（gain_energy 内建通道——跳伤 on_hp_decrease 触发）."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast(eng, "121002")
        gnf = _gnf(eng)
        gnf.current_energy = 50.0
        eng._tick_dots(eng.state.actors["e1"])
        assert math.isclose(gnf.current_energy, 52.0)


class TestTechnique:
    def test_tech_four_hits_firekiss(self):
        """秘技：4 击 ×0.5 确定化同目标 + FIREKISS cap 3 + vuln 逐击递增对轴."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1210", "technique": "121007"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        e1 = eng.state.actors["e1"]
        hit = 0.5 * GNF_ATK * Z
        expect = hit * (1 + 1.07 + 1.14 + 1.21)   # vuln 逐击 0/0.07/0.14/0.21
        assert math.isclose(1e9 - e1.current_hp, expect, rel_tol=1e-9)
        assert e1.modifiers["FIREKISS"].stacks == 3, "cap 3"
        assert math.isclose(eng.pipeline.effective_stats(e1).get("vulnerability", 0.0),
                            0.21, rel_tol=1e-9)
