"""爻光 1502 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 结界/笑点队伍账/好活当赏
条目账/大吉大利/欢愉技/终结技额外阿哈时刻/行迹/星魂全链 → 手算全等（过堂勘正十五件
+ B40 迁移记六件见 fixture 头注）。

口径常数：爻光 atk 465.696；行迹后实战面板 crit_rate 0.237（0.05+0.187）、
crit_dmg 1.1（0.5+0.6）→ 期望暴击区 CZ=1+0.237×1.1=1.2607；spd 110（101+9）；
欢愉度面板 0.1（行迹小节点 1502204/08：0.04+0.06——1502101 SPD 转模读无条件件面板
110<120 → +0，结界共享/E2 为条件件不计入，04 §4.16 防环口径在案）。辅手 atk 1500、
crit 0.05/0.5 → 期望暴击区 1.025。假人 def 1000 → 防御区 0.5、物理弱点 → 抗性区 1.0、
未击破 0.9。直伤链 Z=0.5×0.9×CZ。

欢愉伤害真路由（B40——ATK×倍率占位退役）：纯倍率×等级系数 LV_COEF=7535.107
×(1+elation 面板)×punchline_multi×期望暴击区×0.5×0.9，见 `_el`。punchline_multi=
1+5·src/(src+240)，src 定槽（21_elation §21.2）：欢愉技 150220 全段=阿哈笑点池实时值
（终结技额外时刻=固定计入 20——_aha_pool_override 覆写锚）；大吉大利=触发角色好活
当赏合并值、无好活取爻光的（fixture 三元表达式——辅手无好活恒走兜底=爻光合并值）。
好活当赏=引擎原生条目列表（st.banger_entries 逐条目独立计时——banger_turns 档 3 回合，
行迹 1502103 兑现；eng._resource_value 读合并值）；笑点=队伍账 eng.state.punchline；
欢愉技 action_type=elation_skill 正身（合法行动集引擎排除——体系触发行动，旧
available_if 闩退役）；终结技额外阿哈时刻=aha_instant effect（固定 20 不耗池照授——
抗穿先挂、额外回合后发，当次欢愉伤害吃抗穿 ×1.2，时序待实测在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import legal_action_set
from tests.template_materialize import TEST_TEMPLATE_ROOTS

YG_ATK = 465.696
CZ = 1 + 0.237 * 1.1                      # 期望暴击区（行迹后面板）= 1.2607
Z = 0.5 * 0.9 * CZ                        # 直伤链：防御区×未击破×期望暴击区
Z_ALLY = 0.5 * 0.9 * 1.025
ALLY_BASIC = 1500 * 1.0 * Z_ALLY          # 辅手普攻期望 = 691.875
LV_COEF = 7535.107                        # 欢愉伤害等级系数 Lv.80（rulebook elation_level_multiplier）
EL_BASE = 0.1                             # 爻光欢愉度面板（行迹小节点；1502101 阈值未到 +0）


def _el(mult: float, src: float, *, el: float = EL_BASE, mm: float = 0.0) -> float:
    """欢愉伤害期望（expected 模式）：纯倍率×等级系数×(1+欢愉度)×笑点乘区×增笑乘区×
    期望暴击区×防御区 0.5×未击破 0.9（抗性/易伤/终伤另乘——按场景在断言语境标注）.

    mult=纯倍率；src=punchline_source（欢愉技=池实时值 1 / 额外时刻固定 20，大吉大利=
    触发角色好活当赏合并值兜底爻光）；el=爻光实时欢愉度面板；mm=merrymake 池（E6）。
    暴击区恒 CZ——欢愉伤害源恒爻光（「攻击者欢愉度低于爻光用爻光的算」——辅手 0<0.1
    恒成立；择优半件待收①）。
    """
    return mult * LV_COEF * (1 + el) * (1 + 5 * src / (src + 240)) * (1 + mm) * CZ * 0.45


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


def _banger(eng):
    return eng._resource_value(_yg(eng), "certified_banger")


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
        acts = {a.action_id: a for a in compiled.actions_by_actor["1502"]}
        assert set(acts) == {"150201", "150202", "150203", "150220"}
        assert acts["150220"].action_type == "elation_skill", "欢愉技 action_type 正身（B40 ⓵）"
        assert acts["150220"].scaling[9] == {"elation": 1.0}, "scaling elation 行键纯倍率（ATK 占位退役）"
        decls = compiled.resource_decls_by_actor["1502"]
        assert set(decls) == {"banger_turns"}, (
            "笑点=队伍账/好活当赏=引擎原生条目列表——punchline/aha_turn 声明退役（B40 ⓵⓶）")
        assert decls["banger_turns"]["current"] == 3.0, "行迹 1502103：好活当赏 2+1=3 回合档"

    def test_elation_skill_not_in_legal_set(self, compiled):
        """欢愉技=体系触发行动（阿哈时刻/额外时刻族）——合法行动集引擎排除，顶替旧 available_if 闩（B40 ⓵）."""
        eng = _make(compiled)
        legal = legal_action_set(_yg(eng), eng.actions_by_actor["1502"], 5)
        assert "150220" not in {a.action_id for a in legal}


class TestBattleStart:
    def test_loadout(self, compiled):
        """进战两件（引擎 _init_aha 统发）：+1 笑点 / 好活当赏 20 点条目 3 回合；行迹面板."""
        eng = _make(compiled)
        st = _yg(eng)
        assert math.isclose(eng.state.punchline, 1.0), "§8.2 进战每欢愉角色 +1（队伍账）"
        assert math.isclose(_banger(eng), 20.0), "§8.1 进战 20 点好活当赏（引擎统发，合并值口径）"
        assert st.banger_entries == [{"value": 20.0, "turns": 3.0}], (
            "引擎原生条目列表——单条目 20 点/3 回合独立计时（banger_turns 档覆写，B40 ⓶）")
        assert "CERTIFIED_BANGER" not in st.modifiers, "旧 modifier 层账翻案摘除"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.237, rel_tol=1e-9), "0.05+行迹0.187"
        assert math.isclose(eff["crit_dmg"], 1.1, rel_tol=1e-9), "0.5+神闲意满0.6"
        assert math.isclose(eff["spd"], 110.0, rel_tol=1e-9), "101+行迹9"
        assert math.isclose(eff["elation"], 0.1, rel_tol=1e-9), (
            "行迹小节点 0.04+0.06（1502101：无条件件面板 spd 110<120 → +0，防环口径在案）")


class TestBasicAndZone:
    def test_basic_blast_self_great_boon(self, compiled):
        """普攻 lv6：主 0.9/邻 0.30 直伤 + 大吉大利真路由 0.2（我方目标含自身——勘正③；
        源=自身好活当赏 20）；结界未起笑点不涨."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150201")
        assert math.isclose(hp1 - e1.current_hp, YG_ATK * 0.9 * Z + _el(0.2, 20), rel_tol=1e-9), (
            "主目标 = 普攻 0.9 直伤 + 大吉大利 0.2 欢愉真路由（src=进战 20 合并值）")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * 0.30 * Z, rel_tol=1e-9), "相邻 0.30（lv6）"
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点"
        assert math.isclose(_yg(eng).current_energy, 30.0), "普攻回能 30（官方文本）"
        assert math.isclose(eng.state.punchline, 1.0), "结界未起 → +0"

    def test_skill_zone_punchline_snapshot(self, compiled):
        """战技：挂结界（3 回合自身回合开始走字）+ 首技即得 3 笑点（勘正②快照补偿）；
        结界共享欢愉度=爻光无条件件面板 0.1×20%=0.02 辐射全队（B40 ⓹）；期间普攻/战技各 +3."""
        eng = _make(compiled)
        st = _yg(eng)
        hp1 = eng.state.actors["e1"].current_hp
        _cast(eng, "1502", "150202", target_id="1502")
        assert "ELATION_ZONE" in st.modifiers
        assert math.isclose(st.modifiers["ELATION_ZONE"].duration, 3.0)
        assert math.isclose(eng.state.punchline, 4.0), "1+3（首技即得——快照补偿在案）"
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点"
        assert math.isclose(st.current_energy, 30.0), "战技回能 30（fandom）"
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.12, rel_tol=1e-9), (
            "结界共享：0.1+0.2×0.1（lv10 #2=20%——共享基数=无条件件面板，防环口径在案）")
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["elation"],
                            0.02, rel_tol=1e-9), "team scope 同吃"
        assert math.isclose(hp1 - eng.state.actors["e1"].current_hp, 0.0), (
            "支援技主目标非敌 → 不触发大吉大利")
        _cast(eng, "1502", "150201")
        assert math.isclose(eng.state.punchline, 7.0), "结界期间普攻 +3"
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.state.punchline, 10.0), "结界期间战技 +3（refresh 不双挂）"
        assert math.isclose(st.modifiers["ELATION_ZONE"].duration, 3.0)


class TestUltimate:
    def test_res_pen_extra_aha_turn(self, compiled):
        """终结技 lv10：+5 笑点 / 全队全抗穿 +20%（每持有者 3 回合）/ 回 5 能 / 额外阿哈时刻
        （B40 ⓸ aha_instant——固定计入 20 不耗池：代放欢愉技 lv10 全链（凶星低语先挂本发即吃
        ×1.16、抗穿先挂 ×1.2）+ 照授 20 好活当赏=20+20）；行迹回 1 点."""
        eng = _make(compiled)
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(eng.state.punchline, 6.0), "1+5（额外时刻固定 20 结算——不耗池）"
        assert math.isclose(st.current_energy, 5.0), "180 全扣后回 5"
        assert "ULT_RES_PEN" in st.modifiers and "ULT_RES_PEN" in eng.state.actors["ally"].modifiers
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9)
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.0, 20) + 5 * _el(0.2, 20) + _el(0.2, 20)) * 1.16 * 1.2,
                            rel_tol=1e-9), (
            "额外时刻代放：AoE1.0+随机5×0.2+大吉大利0.2（段/大吉大利 src 同值 20=固定档/授前"
            "好活当赏），凶星低语 ×1.16、抗穿 ×1.2")
        assert math.isclose(hp2 - e2.current_hp, _el(1.0, 20) * 1.16 * 1.2, rel_tol=1e-9)
        assert math.isclose(_banger(eng), 40.0), "进战 20 + 额外时刻照授 20（不耗池照授在案）"
        assert math.isclose(eng.state.skill_points, 4.0), "行迹 1502102：代放欢愉技回 1 点"
        # 抗穿+易伤存续入伤：辅手普攻（自身抗穿 0.2 → ×1.2）+ 大吉大利（兜底=爻光 40）
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            (ALLY_BASIC + _el(0.2, 40)) * 1.2 * 1.16, rel_tol=1e-9), (
            "辅手无好活 → 大吉大利取爻光合并值 40（三元兜底）；抗穿 1.2、凶星低语 1.16 存续")


class TestElationSkill:
    def test_full_chain(self, compiled):
        """欢愉技 lv10（手动对轴——体系触发行动不走合法集，直施对轴）：凶星低语 16% 先挂
        →AoE 1.0 全体 + 随机 5×0.2（expected 确定化首敌）+ 大吉大利 0.2（施放攻击触发，
        待实测在案），全段池实时值 1（无覆写锚）；行迹回 1 点；不回能不涨笑点."""
        eng = _make(compiled)
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.16, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e2)["vulnerability"], 0.16, rel_tol=1e-9)
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.0, 1) + 5 * _el(0.2, 1) + _el(0.2, 20)) * 1.16,
                            rel_tol=1e-9), (
            "AoE1.0+随机5×0.2（池=1）+大吉大利0.2（src=好活当赏 20），易伤 ×1.16")
        assert math.isclose(hp2 - e2.current_hp, _el(1.0, 1) * 1.16, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "行迹 1502102：欢愉技回 1 点（勘正⑨）"
        assert math.isclose(st.current_energy, 0.0), "回能保守 0（fandom 无条目待实测）"
        assert math.isclose(eng.state.punchline, 1.0), "欢愉技不产笑点"


class TestGreatBoonGate:
    def test_gate_and_attack_filter(self, compiled):
        """大吉大利门控：有好活当赏→辅手攻击附带 0.2（辅手无好活→取爻光 20 兜底）；条目
        清空→不触发；爻光支援技不打敌→不触发."""
        eng = _make(compiled)
        st = _yg(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, ALLY_BASIC + _el(0.2, 20), rel_tol=1e-9), (
            "辅手 691.875 + 大吉大利真路由（punchline_source 三元兜底=爻光合并值 20）")
        st.banger_entries.clear()
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp, ALLY_BASIC, rel_tol=1e-9), "条目清 → 无附带"
        hp1 = e1.current_hp
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(hp1 - e1.current_hp, 0.0), "支援技（主目标非敌）不触发"


class TestEidolons:
    def test_e1_extra_pool_stays_20(self):
        """E1：额外时刻固定计入笑点仍 20（① 20→40 待收②——aha_instant 固定 20 无表达式槽，
        引擎缺口在案）→ 照授 20：好活当赏 20+20=40，代放链与 eidolon=0 同值."""
        eng = _make(_compiled(eidolon=1))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _ult(eng)
        assert math.isclose(_banger(eng), 40.0), (
            "进战 20+授 20——E1① 40 档兑现后应 60，现引擎固定 20（待收②，不报假数）")
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.0, 20) + 5 * _el(0.2, 20) + _el(0.2, 20)) * 1.16 * 1.2,
                            rel_tol=1e-9), "固定 20 档代放链（lv10）"

    def test_e2_zone_spd_gate(self):
        """E2：结界持续期间我方 SPD +12%·欢愉度 +16%（enable_if 门控勘正⑭/B40 ⓹）——无结界
        110/90、欢愉度 0.1/0；起界 122.12/100.8、欢愉度 0.28/0.18（0.1+共享 0.02+E2 0.16）."""
        eng = _make(_compiled(eidolon=2))
        st = _yg(eng)
        assert "E2_ZONE_AURA" in st.modifiers, "常驻件在（未启用）"
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 110.0, rel_tol=1e-9), (
            "结界未起 → 不启用")
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.1, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["spd"],
                            90.0, rel_tol=1e-9)
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 101 * 1.12 + 9, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["spd"],
                            90 * 1.12, rel_tol=1e-9), "team scope 同吃"
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.28, rel_tol=1e-9), (
            "0.1+共享 0.02+E2 0.16（共享基数=无条件件面板 0.1——条件件不计入，防环口径）")
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["elation"],
                            0.18, rel_tol=1e-9), "0.02+0.16"

    def test_e2_technique_path(self):
        """E2 + 秘技开战：结界已在 → 速度/欢愉度件开局即启用（enable_if 双路径同真勘正⑭）."""
        eng = _make(_compiled(eidolon=2, pre_battle=True))
        assert "ELATION_ZONE" in _yg(eng).modifiers
        assert math.isclose(eng.pipeline.effective_stats(_yg(eng))["spd"],
                            101 * 1.12 + 9, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(_yg(eng))["elation"],
                            0.28, rel_tol=1e-9)

    def test_e3_level_tracks(self):
        """E3（含 E2）：欢愉技 lv11（AoE 1.05/段 0.21）、普攻 lv7（0.99/0.33）、结界 lv12
        （共享 22%→0.022）+ E2 光环."""
        eng = _make(_compiled(eidolon=3))
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.05, 1) + 5 * _el(0.21, 1) + _el(0.2, 20)) * 1.16,
                            rel_tol=1e-9), "lv11 AoE1.05+5×0.21；天赋仍 lv10 → 大吉大利 0.2"
        assert math.isclose(hp2 - e2.current_hp, _el(1.05, 1) * 1.16, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150201")   # 凶星低语 3 回合仍在 → 本次伤害同吃 1.16
        assert math.isclose(hp1 - e1.current_hp,
                            (YG_ATK * 0.99 * Z + _el(0.2, 20)) * 1.16, rel_tol=1e-9), (
            "普攻 lv7 主 0.99+大吉大利 0.2（易伤存续 ×1.16）")
        assert math.isclose(hp2 - e2.current_hp, YG_ATK * 0.33 * Z * 1.16, rel_tol=1e-9), (
            "lv7 邻 0.33（易伤存续 ×1.16）")
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], 101 * 1.12 + 9, rel_tol=1e-9), (
            "E2 随 eidolon=3 联动")
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.282, rel_tol=1e-9), (
            "结界 lv12 共享 0.22×0.1=0.022：0.1+0.022+0.16")

    def test_e4_final_dmg_window(self):
        """E4（含 E3）：终结技额外时刻中我方欢愉技伤害为原伤害 150%（B40 ⓺——
        aha_instant_start/end 挂摘 final_dmg_boost 0.5；窗内大吉大利同吃 ×1.5 口径偏差
        在案）；窗后摘除——辅手攻击附带大吉大利不再 ×1.5."""
        eng = _make(_compiled(eidolon=4))
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.05, 20) + 5 * _el(0.21, 20) + _el(0.2, 20)) * 1.16 * 1.2 * 1.5,
                            rel_tol=1e-9), "lv11 代放链 ×1.5（E4 窗——凶星低语/抗穿同吃）"
        assert math.isclose(hp2 - e2.current_hp,
                            _el(1.05, 20) * 1.16 * 1.2 * 1.5, rel_tol=1e-9)
        assert "E4_FINAL_DMG" not in st.modifiers, "aha_instant_end 摘除——窗只罩额外时刻"
        assert math.isclose(eng.pipeline.effective_stats(st)["dmg_bonus"].get(
            "final_dmg_boost", 0.0), 0.0, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            (ALLY_BASIC + _el(0.2, 40)) * 1.2 * 1.16, rel_tol=1e-9), (
            "窗后大吉大利不 ×1.5（兜底=爻光 40）")

    def test_e5_level_tracks(self):
        """E5（含 E3/E4）：终结技 lv12 → 抗穿 0.22；欢愉技 lv12（AoE 1.1/段 0.22）；天赋 lv12
        → 大吉大利 0.22；额外时刻链抗穿 ×1.22、E4 窗 ×1.5."""
        eng = _make(_compiled(eidolon=5))
        st = _yg(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.22, rel_tol=1e-9)
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.1, 20) + 5 * _el(0.22, 20) + _el(0.22, 20)) * 1.16 * 1.22 * 1.5,
                            rel_tol=1e-9), "lv12 代放链（大吉大利 lv12=0.22 同窗；E4 随 eidolon=5 联动 ×1.5）"
        assert math.isclose(hp2 - e2.current_hp, _el(1.1, 20) * 1.16 * 1.22 * 1.5, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            (ALLY_BASIC + _el(0.22, 40)) * 1.22 * 1.16, rel_tol=1e-9), (
            "天赋 lv12 大吉大利 0.22（兜底=爻光 40）；抗穿 1.22、易伤 1.16 存续")

    def test_e6_merrymake(self):
        """E6①：我方全体欢愉伤害增笑 25%（B40 ⓺ merrymake 键——常驻 team 件）→ 欢愉技
        全链 ×1.25；E2 速度链路仍真."""
        eng = _make(_compiled(eidolon=6))
        st = _yg(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["merrymake"], 0.25, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["merrymake"],
                            0.25, rel_tol=1e-9), "team scope 同吃"
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1502", "150220")   # E3+E5 联动 → lv12；天赋 lv12 → 大吉大利 0.22
        assert math.isclose(hp1 - e1.current_hp,
                            (_el(1.1, 1, mm=0.25) + 5 * _el(0.22, 1, mm=0.25)
                             + _el(0.22, 20, mm=0.25)) * 1.16, rel_tol=1e-9), (
            "lv12 全链 ×1.25 增笑（E6② 倍率 +100% 待收③——无通道不硬凑）")
        assert math.isclose(hp2 - e2.current_hp, _el(1.1, 1, mm=0.25) * 1.16, rel_tol=1e-9)
        _cast(eng, "1502", "150202", target_id="1502")
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"],
                            101 * 1.12 + 9, rel_tol=1e-9), "E2 速度链路仍真"


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技=开战自动触发 1 次战技（不耗点）：结界在（共享欢愉度 0.02 同挂）+ 笑点
        3+进战 1=4 + 回能 30（勘正⑩）；开局普攻大吉大利按结界共享后面板 0.12 结算."""
        eng = _make(_compiled(pre_battle=True))
        st = _yg(eng)
        assert "ELATION_ZONE" in st.modifiers
        assert math.isclose(eng.state.punchline, 4.0), "秘技触发战技 3 + 进战 1"
        assert math.isclose(st.current_energy, 30.0), "战技回能随本体（阮梅秘技同构）"
        assert math.isclose(eng.state.skill_points, 3.0), "不耗战技点"
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.12, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1502", "150201")
        assert math.isclose(eng.state.punchline, 7.0), "开局结界已在 → 普攻即 +3"
        assert math.isclose(hp1 - e1.current_hp,
                            YG_ATK * 0.9 * Z + _el(0.2, 20, el=0.12), rel_tol=1e-9), (
            "大吉大利吃结界共享后欢愉度面板 0.12（无易伤/抗穿）")
