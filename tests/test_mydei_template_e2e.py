"""万敌全机制模板端到端对轴（打标 DAG 首个真跑产物 + 人工闸版 fixture）：真模板 YAML → 编译
→ 充能/血仇/双自动技/免死双分支/终结技/血祥罩衫条件光环全链 → 手算全等.

链：敌方损血 → Charge 按"每损 1% Max HP = 1 点"记账（血祥三元只乘敌源笔）→ Charge≥100 入血仇
（耗 100 + 回 30% Max HP + 行动提前 + VENDETTA：Max HP+50%/DEF 恒 0/免疫控制）→ 回合开始自动
「弑王成王」（drain 当前 HP 35%，floor 1——自耗也记账充能）→ Charge≥150 自动「弑神登神」
（耗 150，施放期间 _gsb_busy 禁充能）→ 致命伤走免死双分支（水与泥土前 3 次不清退 vs 第 4 次
起天赋清空退血仇回 50%）。数值全按 expected 模式手算对轴（默认档全 lv10——params 单行钳表尾）。

口径常数：万敌白值 hp 1552.32、行迹 hp_pct 0.18 → 有效上限 1831.7376；VENDETTA max_hp_pct
+0.5（param(140404,5)）→ 血仇有效上限 1552.32×1.68 = 2607.8976。假人 def 0 → 防御区 0.5、
虚数弱点 → 抗性区 1.0、未击破 0.9；万敌暴击 0.05/0.873（<4000 血祥不激活）→ 期望暴击区 1.04365。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

BASE_HP = 1552.32
EFF_HP = BASE_HP * 1.18               # 1831.7376（行迹生命节点 ×3）
VENDETTA_HP = BASE_HP * 1.68          # 2607.8976（血仇 max_hp_pct +0.5 同池加算）
DEF_RES = 0.5                         # 假人 def 0 口径
UNBROKEN = 0.9
CRIT_EXP = 1 + 0.05 * 0.873           # 1.04365
ZONES = DEF_RES * UNBROKEN * CRIT_EXP


def _build(*, eidolon: int = 0):
    member = {"character_template": "1404", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["imaginary"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=5)
    eng.setup()
    return eng


def _mydei(eng):
    return eng.state.actors["1404"]


def _arm_vendetta(eng, md):
    """直接武装血仇（闩 + VENDETTA 件——绕过充能入态链的测试快速路）."""
    md.resources["_vendetta"] = 1.0
    eng._apply_modifier(md, Modifier(
        modifier_id="VENDETTA", name="血仇", modifier_type="buff", duration=0,
        dispellable=False, stat_effects={"hp_pct": 0.5, "def_pct": -1.0}))


def _foe_hit(eng, *, scaling=1.0, instances=1):
    """敌方单体打万敌（目标钉死）；返回 on_hp_decrease payload 列表（记账自洽取数）."""
    drops = []
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
    eng.actions_by_actor = {**eng.actions_by_actor, "e1": [Action(
        action_id="e_hit", name="重击", action_type="basic", target_type="single",
        damage_type="physical", scaling=[{"atk": scaling}], instances=instances)]}
    eng._pick_ally_target = lambda attacker=None: _mydei(eng)
    eng._enemy_turn(eng.state.actors["e1"])
    return drops


class TestMydeiCompile:
    def test_resources_and_action_keys(self, compiled):
        decls = set(compiled.resource_decls_by_actor["1404"])
        assert {"charge", "_vendetta", "_gsb_busy", "_e6_gsb", "_e2_heal_accum",
                "mud_soil"} <= decls
        mud = compiled.resource_decls_by_actor["1404"]["mud_soil"]
        assert mud["max"] == 3 and mud["current"] == 3.0, "1404101 水与泥土：单场 3 次"
        acts = {a.action_id: a for a in compiled.actions_by_actor["1404"]}
        assert acts["140402"].skill_point_cost == 0, (
            "万死无悔不耗点（tbgd BPNeed 权威 + 米游社双源，常识冲突待实测不改）")
        assert acts["140402"].toughness_dmg == 20 and acts["140402"].toughness_dmg_blast == 10
        assert acts["140409"].toughness_dmg == 20 and acts["140409"].toughness_dmg_blast == 10
        assert acts["140411"].toughness_dmg == 30 and acts["140411"].toughness_dmg_blast == 20
        assert acts["140403"].energy_cost == 160 and acts["140403"].toughness_dmg == 20
        assert acts["140403"].toughness_dmg_blast == 20, "削韧全（tbgd stance÷3 显示口径）"

    def test_base_stats_real_values(self, compiled):
        a = compiled.build_team[0]
        assert a.actor_id == "1404" and a.path == "destruction" and a.element == "imaginary"
        assert (a.stats.hp, a.stats.atk, a.stats.def_, a.stats.spd) == \
            (1552.32, 426.888, 194.04, 100.0), "lv80 白值实值（calc_character_stats 官方管线）"
        assert a.stats.crit_dmg == 0.873 and a.stats.max_energy == 160.0
        assert a.skill_levels == {"basic": 6, "skill": 10, "ultimate": 10, "talent": 10,
                            "elation_skill": 10, "memosprite_skill": 6, "memosprite_talent": 6}


class TestChargeAndVendetta:
    def test_charge_bookkeeping_and_enter_vendetta(self, compiled):
        eng = _make(compiled)
        md = _mydei(eng)
        assert math.isclose(md.actor.stats.hp * 1.18, EFF_HP)
        # 损血充能：每损 1% 有效上限 = 1 点（E0 血祥不激活 → 敌源三元乘 = 1）
        drops = _foe_hit(eng, scaling=1.0)
        amt = drops[0]["amount"]
        assert math.isclose(md.resources["charge"], amt / EFF_HP * 100, rel_tol=1e-9), (
            "Charge = 损失量/有效上限×100（血祥 <4000 未激活，敌源乘 = 1）")
        # 入血仇：charge 置 100 后小 hit 触发——同事件先记账后判入（hook 注册序钉死）
        md.resources["charge"] = 100.0
        hp0 = md.current_hp
        drops = _foe_hit(eng, scaling=0.01)
        amt2 = drops[0]["amount"]
        assert "VENDETTA" in md.modifiers, "Charge≥100 → 入血仇"
        assert math.isclose(md.resources["_vendetta"], 1.0)
        assert math.isclose(md.resources["charge"], amt2 / EFF_HP * 100, rel_tol=1e-9), (
            "入血仇耗 100：残量 = 本次小 hit 新记账")
        # 回 25% 有效上限（param(140404,1) lv10 正档——apply 在 heal 后，按入血仇前上限计）
        assert math.isclose(md.current_hp, hp0 - amt2 + 0.25 * EFF_HP, rel_tol=1e-9)
        # VENDETTA 面板：Max HP +50%（同池加算 1.68）/ DEF 恒 0 / 免疫控制
        eff = eng.pipeline.effective_stats(md)
        assert math.isclose(eff["hp"], VENDETTA_HP, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 0.0, abs_tol=1e-9), "血仇 DEF 恒 0（def_pct -1.0）"
        assert "control" in md.modifiers["VENDETTA"].grants_immune, "1404102 三十僭主"
        # 入血仇行动提前 100%：AV0 未排程时 _remaining 无键（advance_action 机制族
        # 已由风堇 e2e 钉死），此处不重复铺战斗轴


class TestAutoSkills:
    def test_kingslayer_auto_cast_and_drain(self, compiled):
        """回合开始自动「弑王成王」：敌方吃 lv10 倍率手算全等；自耗 35% 当前 HP（floor 1）也记账."""
        eng = _make(compiled)
        md, e1 = _mydei(eng), eng.state.actors["e1"]
        _arm_vendetta(eng, md)
        md.current_hp = VENDETTA_HP
        hp_e, hp_m = e1.current_hp, md.current_hp
        eng.bus.emit("on_turn_start", {"actor": "1404"}, eng.state)
        assert math.isclose(hp_e - e1.current_hp, 1.1 * VENDETTA_HP * ZONES, rel_tol=1e-9), (
            "弑王成王主目标 = 110% 血仇上限（lv10=idx 9）× 防御 0.5 × 未击破 0.9 × 期望暴击 1.04365")
        assert math.isclose(md.current_hp, hp_m * 0.65, rel_tol=1e-9), (
            "自耗 = 当前 HP 35%（drain_hp floor 1）")
        assert math.isclose(md.resources["charge"],
                            (hp_m * 0.35) / VENDETTA_HP * 100, rel_tol=1e-6), (
            "自耗失血同样记账充能（源=自身 → 不吃敌源三元乘）")

    def test_godslayer_threshold_cast(self, compiled):
        """血仇中 Charge≥150 → 耗 150 自动「弑神登神」；_gsb_busy 施放后清零."""
        eng = _make(compiled)
        md, e1 = _mydei(eng), eng.state.actors["e1"]
        _arm_vendetta(eng, md)
        md.current_hp = VENDETTA_HP
        md.resources["charge"] = 150.0
        hp_e = e1.current_hp
        drops = _foe_hit(eng, scaling=0.01)
        amt = next(p["amount"] for p in drops if p.get("target") == "1404")
        assert math.isclose(hp_e - e1.current_hp, 2.8 * VENDETTA_HP * ZONES, rel_tol=1e-9), (
            "弑神登神主目标 = 280% 血仇上限（lv10=idx 9）× 乘区")
        assert math.isclose(md.resources["charge"], amt / VENDETTA_HP * 100, rel_tol=1e-6), (
            "耗 150：残量 = 触发 hit 新记账（禁充能闩不挡触发笔——闩在 trigger 前置位）")
        assert math.isclose(md.resources["_gsb_busy"], 0.0), "施放期间禁充能闩已清"


class TestUltimate:
    def test_ult_heal_charge_taunt_mark(self, compiled):
        eng = _make(compiled)
        md, e1 = _mydei(eng), eng.state.actors["e1"]
        _arm_vendetta(eng, md)
        md.current_hp = VENDETTA_HP * 0.5
        md.current_energy = 160.0
        ult = next(a for a in eng.actions_by_actor["1404"] if a.action_id == "140403")
        hp_e, hp_m = e1.current_hp, md.current_hp
        assert eng._fire_ultimate(md, ult) is True
        assert math.isclose(hp_e - e1.current_hp, 1.6 * VENDETTA_HP * ZONES, rel_tol=1e-9)
        assert math.isclose(md.current_hp, hp_m + 0.2 * VENDETTA_HP, rel_tol=1e-9), (
            "终结技回 20% Max HP（param(140403,3) lv10 正档，血仇上限口径）")
        assert math.isclose(md.resources["charge"], 20.0), "终结技充能 +20（param(140403,5)）"
        taunt = e1.modifiers["MYDEI_TAUNT_ULT"]
        assert math.isclose(taunt.duration, 2.0), "嘲讽 2 回合（param(140403,4)）"
        assert "MYDEI_GSB_MARK" in e1.modifiers, "登神打标（旧标 refresh 覆盖在案）"
        assert math.isclose(md.current_energy, 5.0), "开大耗 160 后释放回能 5（tbgd）"


class TestUndyingBranches:
    def test_mud_soil_first_three_no_exit(self, compiled):
        """分支 A：前 3 次致命 = cancel + mud_soil-1；不清充能/不退血仇/不回血."""
        eng = _make(compiled)
        md = _mydei(eng)
        _arm_vendetta(eng, md)
        md.current_hp = 100.0
        md.resources["charge"] = 50.0
        for expect in (2.0, 1.0, 0.0):
            _foe_hit(eng, scaling=1000.0)   # 致命（amount ≫ 当前 HP → waterfall cancel）
            assert math.isclose(md.current_hp, 100.0), "cancel：血不掉"
            assert math.isclose(md.resources["mud_soil"], expect)
            assert math.isclose(md.resources["charge"], 50.0), "水与泥土不清充能"
            assert "VENDETTA" in md.modifiers, "水与泥土不退血仇"

    def test_fourth_lethal_exits_and_heals(self, compiled):
        """分支 B：第 4 次（mud_soil 尽）= cancel + 清空充能 + 退血仇 + 回 50% 非血仇上限."""
        eng = _make(compiled)
        md = _mydei(eng)
        _arm_vendetta(eng, md)
        md.current_hp = 100.0
        md.resources["charge"] = 50.0
        md.resources["mud_soil"] = 0.0
        _foe_hit(eng, scaling=1000.0)
        assert math.isclose(md.resources["charge"], 0.0), "天赋免死清空充能"
        assert math.isclose(md.resources["_vendetta"], 0.0)
        assert "VENDETTA" not in md.modifiers, "退出血仇"
        assert math.isclose(md.current_hp, 100.0 + 0.5 * EFF_HP, rel_tol=1e-9), (
            "回 50% Max HP（param(140404,4)——remove 后按非血仇上限 1831.7376 计）")


class TestBloodSilkAura:
    def test_gated_below_4000_and_active_tier(self, compiled):
        """1404103 血祥罩衫：Max HP ≤4000 不计入；推过 4000 现场变档（超档三元对轴）."""
        eng = _make(compiled)
        md = _mydei(eng)
        eff0 = eng.pipeline.effective_stats(md)
        assert math.isclose(eff0["crit_rate"], 0.05), "1831.7376 < 4000 → 血祥不计入"
        # 外挂 hp_pct +2.0（无条件件）→ 条件域面板 1552.32×3.18 = 4936.3776
        eng._apply_modifier(md, Modifier(
            modifier_id="HP_BUFF", name="外源生命", modifier_type="buff", duration=0,
            stat_effects={"hp_pct": 2.0}))
        over = BASE_HP * 3.18 - 4000.0           # 936.3776（未触 4000 计入上限）
        eff1 = eng.pipeline.effective_stats(md)
        assert math.isclose(eff1["crit_rate"], 0.05 + over / 100 * 0.012, rel_tol=1e-9)
        # incoming_heal 档（×0.0075）：eff 不 echo 受疗池——同 stat_exprs 通道由 crit_rate
        # 档与下方敌源充能三元乘两钉覆盖，不另铺治疗轴
        # 敌源笔充能三元乘（+2.5%/超 100）——自耗笔不乘（源=自身）
        drops = _foe_hit(eng, scaling=0.01)
        amt = drops[0]["amount"]
        assert math.isclose(md.resources["charge"],
                            amt / (BASE_HP * 3.18) * 100 * (1 + over / 100 * 0.025),
                            rel_tol=1e-9), "敌源笔 × (1 + 超档×2.5%)；分母=当前有效上限"


class TestEidolon6:
    def test_enter_vendetta_at_start_and_lower_threshold(self):
        b = _build(eidolon=6)
        compiled = compile_encounter(b, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)
        eng = _make(compiled)
        md = _mydei(eng)
        assert "VENDETTA" in md.modifiers, "E6：入场直接血仇（不含入态治疗/提前——官方分开表述）"
        assert math.isclose(md.resources["_e6_gsb"], 1.0)
        # 阈值降档 150→100：charge 100 即触发弑神登神
        md.current_hp = VENDETTA_HP
        md.resources["charge"] = 100.0
        e1 = eng.state.actors["e1"]
        hp_e = e1.current_hp
        _foe_hit(eng, scaling=0.01)
        assert math.isclose(hp_e - e1.current_hp, 3.08 * VENDETTA_HP * ZONES, rel_tol=1e-9), (
            "E6 阈值 100 即登神（150-50×闩）；eidolon=6 含 E3 战技+2 → 弑神登神取 lv12=idx 11 "
            "（308%——scaling 全表随档实证，param()/表驱动链端到端对轴）")
