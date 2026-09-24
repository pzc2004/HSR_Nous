"""开拓者•毁灭 8002 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 天赋击破
叠层（stat_exprs 动态）/终结技双分支/蓄势/不灭三振/E1 闩链/E3/E5 实取档/E6 击杀
叠层全链 + 斗志/E2/E4 待收负向钉 → 手算全等.

口径常数：atk 620.928（行迹 atk_pct 0.28 → 有效 794.78784）、hp 1203.048（行迹
hp_pct 0.18 → 有效 1419.59664）、def 460.845（行迹 def_pct 0.125 → 有效
518.450625）、crit 0.05/0.5（期望暴击区 1.025）、max_energy 120；假人 def 1000
→ 防御区 0.5、物理弱点 → 抗性区 1.0、未击破 0.9 → Z=0.46125。等级轨道：编译
缺省 basic=6/skill=10/ultimate=10/talent=10（E3 战技+2/天赋+2、E5 终结技+2/
普攻+1——实取档随星魂联动，断言按实取档手算）。8001=同命途另一性体镜像
（机制同构、id 系不同），本件按 8002 官方数据独立对轴。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 620.928
HP = 1203.048
DEF = 460.845
ATK_EFF = ATK * 1.28          # 行迹攻击 28%（pct 白值口径）
HP_EFF = HP * 1.18            # 行迹生命 18%
DEF_EFF = DEF * 1.125         # 行迹防御 12.5%
Z = 0.5 * 0.9 * (1 + 0.05 * 0.5)   # 防御区 × 未击破 × 期望暴击区（抗性区 1.0）= 0.46125
CRIT = 1 + 0.05 * 0.5         # 期望暴击区 = 1.025


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "8002", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "8002", "technique": "800207"}]
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
    return eng.state.actors["8002"]


def _cast(eng, aid, *, target=None):
    st = _tb(eng)
    a = next(x for x in eng.actions_by_actor["8002"] if x.action_id == aid)
    tgt = target or eng.state.actors["e1"]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "8002", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng, aid="800208"):
    st = _tb(eng)
    st.current_energy = 120.0
    ult = next(a for a in eng.actions_by_actor["8002"] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _emit_break(eng, target="e1"):
    eng.bus.emit("on_break", {"source": "8002", "target": target,
                              "element": "physical", "bar_index": 0}, eng.state)


class TestCompile:
    def test_actions_toughness_and_wrapper_removed(self, compiled):
        """action 集 = 普攻/战技/双模式终结技（800203 菜单包装件已摘除——不存在的高伤
        混合体免费后门+零伤陷阱+双计费门）；削韧 tbgd 权威：10 / 主20邻10 / 30 / 主20邻20."""
        acts = {a.action_id: a for a in compiled.actions_by_actor["8002"]}
        assert set(acts) == {"800201", "800202", "800208", "800209"}, (
            "800203 包装 action 已摘除（_ult_action_of 取首件——声明序首件 800208=确定性缺省单体模式）")
        assert acts["800201"].toughness_dmg == 10
        assert acts["800202"].toughness_dmg == 20 and acts["800202"].toughness_dmg_blast == 10
        assert acts["800208"].toughness_dmg == 30
        assert acts["800209"].toughness_dmg == 20 and acts["800209"].toughness_dmg_blast == 20
        assert acts["800208"].energy_cost == 120 and acts["800209"].energy_cost == 120, (
            "两模式各全价承载 energy_cost=120=max_sp（无免费后门）")
        assert acts["800208"].energy_gain == 5 and acts["800209"].energy_gain == 5
        assert compiled.resource_decls_by_actor["8002"]["_e1_once"]["max"] == 1
        assert compiled.build_team[0].skill_levels == {
            "basic": 6, "skill": 10, "ultimate": 10, "talent": 10,
            "elation_skill": 10, "memosprite_skill": 6, "memosprite_talent": 6}
        trace = next(m for m in compiled.modifiers_by_actor["8002"]
                     if m.modifier_id == "TRACE_8002")
        assert math.isclose(trace.stat_effects["atk_pct"], 0.28)
        assert math.isclose(trace.stat_effects["hp_pct"], 0.18)
        assert math.isclose(trace.stat_effects["def_pct"], 0.125), "勘正①：行迹属性节点聚合"


class TestTraces:
    def test_ready_for_battle_and_panels(self, compiled):
        """蓄势（8002101）：进战回 15 能；行迹聚合面板：atk×1.28 / hp×1.18 / def×1.125."""
        eng = _make(compiled)
        st = _tb(eng)
        assert math.isclose(st.current_energy, 15.0)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["atk"], ATK_EFF, rel_tol=1e-9)
        assert math.isclose(eff["hp"], HP_EFF, rel_tol=1e-9)
        assert math.isclose(eff["def_"], DEF_EFF, rel_tol=1e-9)


class TestBasicAndSkill:
    def test_basic_lv6(self, compiled):
        """普攻 lv6=1.0：1.0×794.78784×0.46125=366.5958912；回能 15+20=35；产 1 点；削韧 10."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "800201")
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK_EFF * Z, rel_tol=1e-9), (
            "普攻 lv6=1.0（10 档表 index 5——编译缺省 6 档非 lv10）")
        assert math.isclose(_tb(eng).current_energy, 35.0), "蓄势 15 + 普攻 20"
        assert math.isclose(eng.state.skill_points, 4.0), "3+1 产点"
        assert e1.toughness == 90, "100-10"

    def test_skill_blast_same_multiplier(self, compiled):
        """战技 lv10 主/邻同 1.25（官方同一 #1 双目标）：1.25×794.78784×0.46125
        =458.244864；耗 1 点；回能 15+30=45；削韧 主20邻10."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "800202")
        assert math.isclose(hp1 - e1.current_hp, 1.25 * ATK_EFF * Z, rel_tol=1e-9), "主 1.25"
        assert math.isclose(hp2 - e2.current_hp, 1.25 * ATK_EFF * Z, rel_tol=1e-9), (
            "相邻同倍率 1.25（官方同一 #1——斗志已摘除待收，无 +25%）")
        assert math.isclose(eng.state.skill_points, 2.0), "3-1 耗点"
        assert math.isclose(_tb(eng).current_energy, 45.0)
        assert e1.toughness == 80 and e2.toughness == 90, "主 100-20、邻 100-10"


class TestTalent:
    def test_break_stacks_live_read_and_cap(self, compiled):
        """牵制盗垒：两次真击破叠 2 层（atk ×1.48→×1.68、def ×1.225→×1.325——stat_exprs
        现场读层含行迹 0.28/0.125）；第三次击破计数钳 2；叠层面板吃进伤害（第二击
        1.0×(620.928×1.48)×Z）."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.toughness = 10
        _cast(eng, "800201")   # 真击破 e1 → 1 层（破的一击仍按 0 层+未击破 0.9）
        assert math.isclose(st.modifiers["PERFECT_PICKOFF"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.48, rel_tol=1e-9), (
            "1 层：1+行迹 0.28+天赋 0.2（lv10 param(800204,1) 编译期取档）")
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.225, rel_tol=1e-9), (
            "1 层：1+行迹 0.125+坚韧 0.1")
        hp2 = e2.current_hp
        _cast(eng, "800201", target=e2)   # 不击破 e2：纯伤断言叠层吃进伤害
        assert math.isclose(hp2 - e2.current_hp, 1.0 * (ATK * 1.48) * Z, rel_tol=1e-9)
        e2.toughness = 10
        _cast(eng, "800201", target=e2)   # 真击破 e2 → 2 层
        assert math.isclose(st.modifiers["PERFECT_PICKOFF"].stacks, 2.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.68, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.325, rel_tol=1e-9)
        _emit_break(eng)   # 第三次击破：计数钳 2、面板维持（stat_exprs 读层恒新）
        assert math.isclose(st.modifiers["PERFECT_PICKOFF"].stacks, 2.0), "上限 2 层 clamp"
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.68, rel_tol=1e-9)

    def test_hit_on_broken_target(self, compiled):
        """已击破目标 base_universal=1.0：1 层后普攻 = (620.928×1.48)×0.5×1.0×1.025
        =470.973888（击破伤害与破的一击同账落地——不看 HP，只看层数/面板；
        破的一击伤害结算先于 on_break 故不吃当层叠层）."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        e1.toughness = 10
        _cast(eng, "800201")   # 真击破 e1（击破伤害同账——不断 HP）
        assert e1.broken
        assert math.isclose(_tb(eng).modifiers["PERFECT_PICKOFF"].stacks, 1.0)
        hp1b = e1.current_hp
        _cast(eng, "800201")   # 已破目标第二击：纯直伤（无新击破账）
        assert math.isclose(hp1b - e1.current_hp,
                            1.0 * (ATK * 1.48) * 0.5 * 1.0 * CRIT, rel_tol=1e-9), (
            "1 层 atk×1.48 + 已击破 1.0")


class TestUltimate:
    def test_single_mode_full_account(self, compiled):
        """800208 单体：4.5×794.78784×0.46125=1649.6815104（lv10=index 9——末行 5.25
        是 lv15）；能量 120 全扣 + 5 回 = 5；削韧 30."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng, "800208")
        assert math.isclose(hp1 - e1.current_hp, 4.5 * ATK_EFF * Z, rel_tol=1e-9)
        assert math.isclose(_tb(eng).current_energy, 5.0), "120 全扣 + energy_gain 5"
        assert e1.toughness == 70, "100-30"

    def test_blast_mode_full_account(self, compiled):
        """800209 扩散：主 2.7=989.80890624 / 邻 1.62=593.885343744（lv10）；
        能量 5；削韧 主20邻20（tbgd [60,0,60]÷3）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "800209")
        assert math.isclose(hp1 - e1.current_hp, 2.7 * ATK_EFF * Z, rel_tol=1e-9), "主 2.7"
        assert math.isclose(hp2 - e2.current_hp, 1.62 * ATK_EFF * Z, rel_tol=1e-9), "邻 1.62"
        assert math.isclose(_tb(eng).current_energy, 5.0)
        assert e1.toughness == 80 and e2.toughness == 80, "主邻各 100-20"

    def test_auto_ult_deterministic_default(self, compiled):
        """自动路径确定性缺省 = 声明序首件 800208 单体模式（同 instance_variants
        恒取变体 0 口径；模式选择策略待实测在案）."""
        eng = _make(compiled)
        assert eng._ult_action_of(_tb(eng)).action_id == "800208"


class TestEidolons:
    def test_e1_ult_kill_refund_and_reset(self):
        """E1：终结技击杀 +10 能（120→5+10=15）；终结技 on_action（结算后）闩复位 0；
        非终结技击杀不回（basic 击杀只 +20 行动回能）."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp = 1.0
        _ult(eng, "800208")   # 击杀 e1 → +10；on_action 自动发射复位闩
        assert not e1.alive
        assert math.isclose(st.current_energy, 15.0), "120 全扣 +5 行动回能 +10 E1"
        assert math.isclose(st.resources["_e1_once"], 0.0), "终结技 on_action 复位闩"
        e2.current_hp = 1.0
        _cast(eng, "800201", target=e2)   # 普攻击杀非终结技域 → 不回
        assert math.isclose(st.current_energy, 35.0), "E1 域外只 +20 行动回能"

    def test_e1_once_per_attack(self):
        """E1 once-per-attack：扩散一大双杀只回 1 次（首杀触发置 1、二杀被闩）——
        能量 5+10=15，非 25."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        e1.current_hp, e2.current_hp = 1.0, 1.0
        _ult(eng, "800209")   # 主 e1 邻 e2 同攻击双杀
        assert not e1.alive and not e2.alive
        assert math.isclose(st.current_energy, 15.0), "同一次攻击只触发 1 次"

    def test_e2_absent_no_heal(self):
        """E2 待收负向钉：战技命中后不回血（has_weakness 查询通道缺——全命中
        落地=对非物理弱点敌静默多回，宁缺勿假摘除）."""
        eng = _make(_compiled(eidolon=2))
        st = _tb(eng)
        st.current_hp = 100.0
        _cast(eng, "800202")
        assert math.isclose(st.current_hp, 100.0), "E2 待收——不许无过滤回血（勘正⑤）"

    def test_e3_skill_talent_lv12(self):
        """E3 联动：战技 lv12=1.375（1.375×794.78784×0.46125=504.0693504）；天赋
        lv12 → param(800204,1)=0.22：1 层 atk ×1.50（=931.392），def ×1.225 维持."""
        eng = _make(_compiled(eidolon=3))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "800202")
        assert math.isclose(hp1 - e1.current_hp, 1.375 * ATK_EFF * Z, rel_tol=1e-9), "战技 lv12"
        assert math.isclose(hp2 - e2.current_hp, 1.375 * ATK_EFF * Z, rel_tol=1e-9), "相邻同档"
        _emit_break(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.50, rel_tol=1e-9), (
            "天赋 lv12：1+行迹 0.28+层 0.22（stat_exprs 编译期取档）")
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.225, rel_tol=1e-9), (
            "行迹坚韧 0.1 字面值不随档")

    def test_e5_ult_basic_level_chain(self):
        """E5 联动（含 E3）：普攻 lv7=1.1（缺省 6+1——勘正⑨）；终结技 lv12 →
        800208=4.8（4.8×794.78784×0.46125=1759.66027776）."""
        eng = _make(_compiled(eidolon=5))
        assert _tb(eng).actor.skill_levels == {
            "basic": 7, "skill": 12, "ultimate": 12, "talent": 12,
            "elation_skill": 10, "memosprite_skill": 6, "memosprite_talent": 6}
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "800201")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK_EFF * Z, rel_tol=1e-9), "普攻 lv7=1.1"
        hp1b = e1.current_hp
        _ult(eng, "800208")
        assert math.isclose(hp1b - e1.current_hp, 4.8 * ATK_EFF * Z, rel_tol=1e-9), "终结技 lv12=4.8"

    def test_e6_kill_triggers_talent(self):
        """E6：击杀也叠天赋层（含 E3 → 每层 0.22：atk ×1.50、def ×1.225）；
        basic 击杀非 E1 域不回能（15+20=35）."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        e1.current_hp = 1.0
        _cast(eng, "800201")
        assert not e1.alive
        assert math.isclose(st.modifiers["PERFECT_PICKOFF"].stacks, 1.0), "击杀触发天赋 1 层"
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], ATK * 1.50, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_"], DEF * 1.225, rel_tol=1e-9)
        assert math.isclose(st.current_energy, 35.0), "蓄势 15 + 普攻 20（E1 域外）"

    def test_e4_and_fighting_will_absent(self):
        """E4/斗志待收负向钉：击破后攻击已击破敌——暴击率恒 0.05（scoped 暴击通道
        缺，不许错模件在场）；战技/终结技命中后无任何斗志件（指定目标限定不可
        表达整件摘除——dmg_skill_dmg_boost 桶恒 0）."""
        eng = _make(_compiled(eidolon=4))
        st = _tb(eng)
        e1 = eng.state.actors["e1"]
        e1.toughness = 10
        _cast(eng, "800201")   # 击破 e1
        assert e1.broken
        _cast(eng, "800202")   # 攻击已击破敌
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], 0.05, rel_tol=1e-9), (
            "E4 待收——目标条件暴击通道缺，不许错模近似")
        assert "E4_CRIT_BROKEN" not in st.modifiers
        assert "FIGHTING_WILL" not in st.modifiers, "斗志整件待收（勘正④）"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["dmg_bonus"].get("skill_dmg_boost", 0.0), 0.0), (
            "战技类型桶恒 0——语义改写法不许留")


class TestTechnique:
    def test_pre_battle_heal(self):
        """秘技不灭三振：进战全体各回自身 Max HP 15%（$target 逐目标——勘正⑥）。
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
        assert math.isclose(got["8002"]["amount"], 0.0), "满血实回 0（开局满血口径）"
        assert math.isclose(got["8002"]["excess"], 0.15 * HP_EFF, rel_tol=1e-9), (
            "拟回 0.15×自身有效上限全转 excess")
        assert math.isclose(_tb(eng).current_hp, HP_EFF, rel_tol=1e-9)
        assert math.isclose(got["ally"]["amount"], 0.0)
        assert math.isclose(got["ally"]["excess"], 0.15 * 3000.0, rel_tol=1e-9)
