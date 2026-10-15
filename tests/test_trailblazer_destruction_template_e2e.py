"""开拓者•毁灭 8001 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
普攻/战技扩散/双模式终结技/牵制盗垒叠层烘焙/蓄势/不灭三振/E1 闩链/E3/E5 实取档/
E6 击杀叠层全链 → 手算全等.

口径常数：开拓者•毁灭白值 atk 620.928、def 460.845、crit 0.05/0.5（期望暴击区 1.025）、
max_energy 120；行迹十节点聚合 atk×1.28 / hp×1.18 / def×1.125（pct 白值口径——8002 同案）；
假人 def 1000 → 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9
→ Z=0.46125。等级轨道：编译缺省 basic=6/skill=10/ultimate=10/talent=10
（E3 战技+2/天赋+2、E5 终结技+2/普攻+1——实取档随星魂联动，断言按实取档手算）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 620.928
DEF = 460.845
HP = 1203.048
ATK_EFF = ATK * 1.28          # 行迹攻击 28%（pct 白值口径——8002 同案）
DEF_EFF = DEF * 1.125         # 行迹防御 12.5%
HP_EFF = HP * 1.18            # 行迹生命 18%
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)   # 防御区 × 未击破 × 期望暴击区（抗性区 1.0）


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8001", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8001", "technique": "800107"}]
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


def _tb(eng):
    return eng.state.actors["8001"]


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


def _ult(eng, aid="800108", *, target=None):
    st = _tb(eng)
    st.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["8001"] if a.action_id == aid)
    if target is not None:
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
            target if target in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


def _emit_break(eng, target="e1"):
    eng.bus.emit("on_break", {"source": "8001", "target": target,
                              "element": "physical", "bar_index": 0}, eng.state)


class TestCompile:
    def test_actions_toughness_and_wrapper_removed(self, compiled):
        """action 集 = 普攻/战技/双模式终结技（800103 菜单包装件已摘除——零伤陷阱+
        双计费门）；削韧 tbgd 权威：10 / 主20邻10 / 30 / 主20邻20."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["8001"]}
        assert set(acts) == {"800101", "800102", "800108", "800109"}, (
            "800103 包装 action 已摘除（_ult_action_of 取首件——声明序首件 800108=确定性缺省单体模式）")
        assert acts["800101"].toughness_dmg == 10
        assert acts["800102"].toughness_dmg == 20 and acts["800102"].toughness_dmg_blast == 10
        assert acts["800108"].toughness_dmg == 30
        assert acts["800109"].toughness_dmg == 20 and acts["800109"].toughness_dmg_blast == 20
        assert acts["800108"].energy_cost == 120 and acts["800109"].energy_cost == 120, (
            "两模式各全价承载 energy_cost=120=max_sp（无免费后门）")
        assert acts["800108"].energy_gain == 5 and acts["800109"].energy_gain == 5
        assert compiled.resource_decls_by_actor["8001"]["_e1_once"]["max"] == 1


class TestTraces:
    def test_ready_for_battle_energy(self, compiled):
        """行迹蓄势（8001101）：战斗开始立即回复 15 能量（initial_energy_ratio=0 起手）."""
        eng = _make(compiled)
        assert math.isclose(_tb(eng).current_energy, 15.0)


class TestBasicAndSkill:
    def test_basic_lv6(self, compiled):
        """普攻：编译缺省 basic=6 档实取 1.0×ATK×Z；回能 20；产 1 点；削韧 10."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8001", "800101")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK_EFF * Z, rel_tol=1e-9), (
            "普攻 lv6=1.0（10 档表 index 5——编译缺省 6 档非 lv10）")
        assert math.isclose(_tb(eng).current_energy, 15.0 + 20.0), "蓄势 15 + 普攻 20"
        assert math.isclose(eng.state.skill_points, 4.0), "3+1 产点"
        assert e1.toughness == 90, "100-10"

    def test_skill_blast_same_multiplier(self, compiled):
        """战技：主/相邻同倍率 lv10=1.25（params 单列）；耗 1 点；回能 30；削韧 主20邻10."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8001", "800102")
        assert math.isclose(hp1 - e1.current_hp, 1.25 * ATK_EFF * Z, rel_tol=1e-9), "主 1.25"
        assert math.isclose(hp2 - e2.current_hp, 1.25 * ATK_EFF * Z, rel_tol=1e-9), (
            "相邻同倍率 1.25（params 单列口径）")
        assert math.isclose(eng.state.skill_points, 2.0), "3-1 耗点"
        assert math.isclose(_tb(eng).current_energy, 15.0 + 30.0)
        assert e1.toughness == 80 and e2.toughness == 90, "主 100-20、邻 100-10"


class TestTalent:
    def test_break_stacks_bake_and_cap(self, compiled):
        """牵制盗垒：两次真击破叠 2 层（atk ×1.48→×1.68、def ×1.225→×1.325——行迹坚韧
        0.1/层字面值不随档 + 行迹白值 0.28/0.125 同池加算）；第三击破除数钳 2 层；叠层面板
        吃进伤害（第二击 1.0×(620.928×1.48)×Z）."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.toughness = 10
        _cast(eng, "8001", "800101")   # 真击破 e1 → 1 层（破的一击仍按未击破 0.9）
        assert math.isclose(st.modifiers["TB_STEAL_STACKS"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.48, rel_tol=1e-9), (
            "1 层：行迹 0.28 + lv10 param(800104,1)=0.2 烘焙")
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.225, rel_tol=1e-9), (
            "行迹白值 0.125 + 行迹坚韧 1 层 ×10%")
        hp2 = e2.current_hp
        _cast(eng, "8001", "800101", target=e2)   # 不击破 e2：纯伤断言烘焙吃进伤害
        assert math.isclose(hp2 - e2.current_hp, 1.0 * (ATK * 1.48) * Z, rel_tol=1e-9), (
            "1 层面板吃进本次普攻伤害")
        e2.toughness = 10
        _cast(eng, "8001", "800101", target=e2)   # 真击破 e2 → 2 层
        # （击破伤害与本击同账落地——不断 HP，只看层数/面板）
        assert math.isclose(st.modifiers["TB_STEAL_STACKS"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.68, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.325, rel_tol=1e-9)
        _emit_break(eng)   # 第三击破：计数钳 2、面板维持 ×1.68
        assert math.isclose(st.modifiers["TB_STEAL_STACKS"].stacks, 2.0), "上限 2 层"
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.68, rel_tol=1e-9)


class TestUltimate:
    def test_single_mode_full_account(self, compiled):
        """800108 单体模式：4.5×ATK×Z（lv10）；能量 120 全扣 + 5 回 = 5；削韧 30."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng, "800108")
        assert math.isclose(hp1 - e1.current_hp, 4.5 * ATK_EFF * Z, rel_tol=1e-9), (
            "lv10=4.5（15 档表 index 9——末行 5.25 是 lv15）")
        assert math.isclose(_tb(eng).current_energy, 5.0), "120 全扣 + energy_gain 5"
        assert e1.toughness == 70, "100-30"

    def test_blast_mode_full_account(self, compiled):
        """800109 扩散模式：主 2.7 / 邻 1.62 ×ATK×Z（lv10）；能量 5；削韧 主20邻20."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "800109")
        assert math.isclose(hp1 - e1.current_hp, 2.7 * ATK_EFF * Z, rel_tol=1e-9), "主 2.7"
        assert math.isclose(hp2 - e2.current_hp, 1.62 * ATK_EFF * Z, rel_tol=1e-9), "邻 1.62"
        assert math.isclose(_tb(eng).current_energy, 5.0)
        assert e1.toughness == 80 and e2.toughness == 80, "主邻各 100-20"

    def test_auto_ult_deterministic_default(self, compiled):
        """自动路径确定性缺省 = 声明序首件 800108 单体模式（同 instance_variants
        恒取变体 0 口径；模式选择策略待实测在案）."""
        eng = _make(compiled)
        assert eng._ult_action_of(_tb(eng)).action_id == "800108"


class TestEidolons:
    def test_e1_ult_kill_refund_and_reset(self):
        """E1：终结技击杀 +10 能（120→5+10=15）；on_action（结算后）闩复位 0；
        非终结技击杀不回（basic 击杀只 +20 行动回能）."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 1.0
        _ult(eng, "800108")   # 击杀 e1 → +10；on_action 自动发射复位闩
        assert not e1.alive
        assert math.isclose(st.current_energy, 15.0), "120 全扣 +5 行动回能 +10 E1"
        assert math.isclose(st.resources["_e1_once"], 0.0), "终结技 on_action 复位闩"
        e2.current_hp = 1.0
        _cast(eng, "8001", "800101", target=e2)   # 普攻击杀非终结技域 → 不回
        assert math.isclose(st.current_energy, 15.0 + 20.0), "E1 域外只 +20 行动回能"

    def test_e1_once_per_attack(self):
        """E1 once-per-attack：扩散一大双杀只回 1 次（闩语义反转：首杀触发置 1、
        二杀被闩）——能量 5+10=15，非 25."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp, e2.current_hp = 1.0, 1.0
        _ult(eng, "800109")   # 主 e1 邻 e2 同攻击双杀
        assert not e1.alive and not e2.alive
        assert math.isclose(st.current_energy, 15.0), "同一次攻击只触发 1 次"

    def test_e3_skill_talent_lv12(self):
        """E3 联动：战技 lv12=1.375（E0 基础上 +2 档）；天赋 lv12 → 每层 0.22
        （param(800104,1) 随档）——1 层 atk ×1.50（行迹 0.28+0.22），def ×1.225
        （行迹 0.125 + 坚韧 0.1 字面值不随档）."""
        eng = _make(_compiled(eidolon=3))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8001", "800102")
        assert math.isclose(hp1 - e1.current_hp, 1.375 * ATK_EFF * Z, rel_tol=1e-9), "战技 lv12"
        assert math.isclose(hp2 - e2.current_hp, 1.375 * ATK_EFF * Z, rel_tol=1e-9), "相邻同档"
        _emit_break(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.50, rel_tol=1e-9), (
            "天赋 lv12：1 层 行迹 0.28+0.22")
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.225, rel_tol=1e-9), (
            "行迹坚韧 0.1 字面值不随档 + 行迹白值 0.125")

    def test_e5_ult_basic_level_chain(self):
        """E5 联动：普攻 lv7=1.1（缺省 6+1——draft「无档可取」勘正）；终结技
        lv12 → 800108=4.8."""
        eng = _make(_compiled(eidolon=5))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8001", "800101")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK_EFF * Z, rel_tol=1e-9), "普攻 lv7=1.1"
        hp1b = e1.current_hp
        _ult(eng, "800108")
        assert math.isclose(hp1b - e1.current_hp, 4.8 * ATK_EFF * Z, rel_tol=1e-9), "终结技 lv12=4.8"

    def test_e6_kill_triggers_talent(self):
        """E6：击杀也叠天赋层（含 E3 → 每层 0.22）；basic 击杀非 E1 域不回能."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 1.0
        _cast(eng, "8001", "800101")
        assert math.isclose(st.modifiers["TB_STEAL_STACKS"].stacks, 1.0), "击杀触发天赋 1 层"
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.50, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 15.0 + 20.0), "蓄势 15 + 普攻 20（E1 域外）"

    def test_e4_and_fighting_will_absent(self):
        """E4/斗志待收负向钉：击破后攻击已击破敌——暴击率恒 0.05（无错模件在场）；
        战技命中后目标无 FIGHTING_WILL 件（res_pen 挂敌死键已摘除）."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        e1.toughness = 10
        _cast(eng, "8001", "800101")   # 击破 e1
        assert e1.broken
        _cast(eng, "8001", "800102")   # 攻击已击破敌
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05, rel_tol=1e-9), (
            "E4 待收——目标条件暴击通道缺，不许错模近似")
        assert "E4_CRIT_BROKEN" not in st.modifiers
        assert "FIGHTING_WILL" not in e1.modifiers, "斗志待收——res_pen 挂敌死键已摘除"


class TestTechnique:
    def test_pre_battle_heal(self):
        """秘技不灭三振：进战全体各回自身 Max HP 15%（$target 逐目标）。
        开局满血口径（B-TR① 引擎补口——hp% 初始件角色旧布场残血病已修，起手
        current_hp=有效上限 1419.59664）→ 开拓者拟回 212.939496=0.15×1419.59664
        全转 excess（实回 0）；辅手满血拟回全转 excess=450——两目标 excess 不同
        基数即证非施放者比例."""
        c = _compiled(pre_battle=True)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        events = []
        eng.bus.subscribe("on_hp_increase",
                          lambda et, payload, state: events.append(payload))
        eng.setup()
        got = {e["target"]: e for e in events}
        assert math.isclose(got["8001"]["amount"], 0.0), "满血实回 0（开局满血口径）"
        assert math.isclose(got["8001"]["excess"], 0.15 * HP_EFF, rel_tol=1e-9), (
            "拟回 0.15×自身有效上限（含行迹 hp_pct 0.18）全转 excess")
        assert math.isclose(_tb(eng).current_hp, HP_EFF, rel_tol=1e-9)
        assert math.isclose(got["ally"]["amount"], 0.0)
        assert math.isclose(got["ally"]["excess"], 0.15 * 3000.0, rel_tol=1e-9)
