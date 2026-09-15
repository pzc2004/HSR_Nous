"""火花 1501 模板端到端对轴（验收型批·欢愉命途首模板）：真模板 YAML → 编译 →
直播态换技能/好活当赏天赋附伤（欢愉真路由）/笑点经济/欢愉技段链/行迹/星魂全链 → 手算全等.
过堂勘正十二件见 fixture 头注；B40 迁移记六件同注。

口径常数：火花 atk 640.332；行迹后 crit 0.17/0.633（池 0 期望暴击区 1+0.17×0.633=1.10761——
仅秘技进战前口径）；进战每欢愉命途成员笑点 +1（本编队单欢愉 N=1）→ palette 1501103 重烘
暴伤 0.633+0.08=0.713、战内期望暴击区 1+0.17×0.713=1.12121；假人 def 1000 → 防御区 0.5、
火弱点 → 抗性区 1.0、未击破 0.9 → Z0=0.45×1.10761（池 0）/ Z0P=0.45×1.12121（池 1）。
欢愉面板=行迹 +0.28（1501101 转化：实战 ATK 640<2000 → +0）→ elation_multi=1.28。
档位：普攻/强化普攻 lv6（E3→lv7），战技/终结技/天赋/欢愉技 lv10（E3 欢愉技→lv11；
E5 终结技/天赋/欢愉技→lv12）。削韧显示值=tbgd ShowStanceList÷3。

欢愉伤害真路由（B40 ⓵⓷——ATK×倍率占位退役）：纯倍率×等级系数 LV_COEF=7535.107
×(1+elation 面板)×(1+5·src/(src+240))×期望暴击区×0.5×0.9，见 `_el`。src=punchline_source
定槽（21_elation §21.2）：欢愉技 150120 全段=阿哈笑点池实时值（res_punchline；阿哈代放/
额外阿哈经 _aha_pool_override 覆写）；天赋附伤=持有者好活当赏合并值（缺省定槽——进战 20）。
好活当赏=引擎原生条目列表（st.banger_entries 逐条目独立 2 回合计时，eng._resource_value
读合并值——旧 modifier 层账/150102 直播态推定挂退役，B40 ⓶）；笑点=队伍账
eng.state.punchline；150120 action_type=elation_skill 正身（合法行动集引擎排除，B40 ⓵）。
终结技 #3=0.6×欢愉度段=普通火直伤动态项（官方 "Fire DMG" vs 天赋 "Fire Elation DMG"
措辞分野）：0.6×0.28=0.168×ATK，与 action 层 #2 段同面板口径（获得笑点前——钩序纪律）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import legal_action_set
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 640.332
CRIT_ZONE = 1 + (0.05 + 0.12) * (0.5 + 0.133)   # 1.10761（行迹后期望暴击区，池 0——仅秘技进战前用）
Z0 = 0.5 * 0.9 * CRIT_ZONE                       # 防御区×未击破×期望暴击（抗性区 1.0，池 0）
POOL0 = 1                                        # 进战发放：每欢愉命途成员笑点 +1（本编队 N=1）
CRIT_ZONE_P = 1 + 0.17 * (0.633 + 0.08 * POOL0)  # 1.12121（palette 按进战池重烘暴伤 0.713）
Z0P = 0.5 * 0.9 * CRIT_ZONE_P                    # 战内基准口径（进战池 1）
LV_COEF = 7535.107                               # 欢愉伤害等级系数 Lv.80（rulebook elation_level_multiplier）
ELATION = 0.28                                   # 行迹欢愉度 5 节点聚合（1501101 转化 ATK<2000 → +0）


def _el(mult: float, src: float, cz: float, *, el: float = ELATION) -> float:
    """欢愉伤害期望（expected 模式）：纯倍率×等级系数×(1+elation)×笑点乘区×期望暴击区×防御区 0.5×未击破 0.9.

    mult=纯倍率；src=punchline_source（欢愉技=笑点池实时值，天赋附伤=持有者好活当赏合并值 20）；
    cz=期望暴击区（palette 现场暴伤）；el=elation 面板（E4 后 0.64）。
    """
    return mult * LV_COEF * (1 + el) * (1 + 5 * src / (src + 240)) * cz * 0.45


def _build(*, eidolon: int = 0, pre_battle: bool = False, extra_elation: int = 0):
    member = {"character_template": "1501", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member]
    for i in range(extra_elation):
        team.append({"actor_id": f"ela{i}", "name": f"欢愉{i}", "inline": True,
                     "path": "elation",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": f"ela{i}_basic", "name": "普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "fire", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10}]})
    team.append({"actor_id": "ally", "name": "辅手", "inline": True,
                 "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
                 "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                              "target_type": "single", "damage_type": "fire",
                              "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
                              "skill_point_gain": 1}]})
    build = {"build": {"team": team,
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1501", "technique": "150107"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, extra_elation: int = 0):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle,
                                    extra_elation=extra_elation),
                             _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _spx(eng):
    return eng.state.actors["1501"]


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
    st = _spx(eng)
    st.current_energy = 160.0
    ult = next(a for a in eng.actions_by_actor["1501"] if a.action_id == "150103")
    assert eng._fire_ultimate(st, ult) is True


def _avail(eng, aid):
    st = _spx(eng)
    a = next(x for x in eng.actions_by_actor["1501"] if x.action_id == aid)
    return eng._available_if_ok(st, a)


class TestSparxieCompile:
    def test_actions_resources_level_key(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1501"]}
        assert set(acts) == {"150101", "150102", "150103", "150108",
                             "150109", "150110", "150120"}
        assert acts["150120"].action_type == "elation_skill", "欢愉技 action_type 正身（B40 ⓵）"
        assert acts["150120"].level_key == "elation_skill", "勘正⑨：欢愉技独立取档键"
        decls = compiled.resource_decls_by_actor["1501"]
        assert set(decls) == {"thrill", "_live", "_engagement", "banger_turns"}, (
            "笑点=队伍账/好活当赏=引擎原生条目列表——punchline 声明退役（B40 ⓶）")
        assert decls["thrill"]["max"] == 10
        assert decls["_live"]["max"] == 1
        assert decls["_engagement"]["max"] == 20, "互动陷阱本次技能内上限 param(150102,1)"
        assert decls["banger_turns"]["current"] == 2, "spec 固定 2 回合缺省档（8009 先例）"

    def test_elation_skill_not_in_legal_set(self, compiled):
        """欢愉技=体系触发行动（阿哈时刻/代放族）——合法行动集引擎排除，顶替旧「归 skill 类
        开放施放」占位（B40 ⓵）."""
        eng = _make(compiled)
        legal = legal_action_set(_spx(eng), eng.actions_by_actor["1501"], 5)
        assert "150120" not in {a.action_id for a in legal}


class TestTraces:
    def test_trace_crit_stats(self, compiled):
        """行迹数值节点：暴击率 0.05+0.12=0.17、暴伤 0.5+0.133=0.633、欢愉度 0.28（勘正③+
        B40 ⓹ trace_stat_effects 收）；进战池 1 → palette 1501103 重烘暴伤 +0.08."""
        eng = _make(compiled)
        es = eng.pipeline.effective_stats(_spx(eng))
        assert math.isclose(es["atk"], 640.332, rel_tol=1e-9)
        assert math.isclose(es["crit_rate"], 0.17, rel_tol=1e-9)
        assert math.isclose(es["crit_dmg"], 0.633 + 0.08 * POOL0, rel_tol=1e-9), (
            "进战池 1 → palette 重烘 0.633+0.08=0.713")
        assert math.isclose(es["elation"], 0.28, rel_tol=1e-9), (
            "行迹欢愉度 5 节点 0.04+0.04+0.06+0.06+0.08；1501101 转化 ATK 640<2000 → +0")


class TestBasic:
    def test_basic_damage_economy(self, compiled):
        """普攻 lv6=1.0 档：e1 伤 1.0×ATK×Z0P；产 1 点、回 20 能、削韧 10."""
        eng = _make(compiled)
        st, e1 = _spx(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp0 - e1.current_hp, 1.0 * ATK * Z0P, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点（3→4）"
        assert math.isclose(st.current_energy, 20.0), "回能 20"
        assert math.isclose(e1.toughness, 90.0), "削韧 10（tbgd 30÷3）"


class TestLivestream:
    def test_open_toggle_and_availability(self, compiled):
        """150102 开播：耗 1 点、_live 闩置 1、计数复位；换技能互斥生效；好活当赏=进战 §8.1
        统发 20（引擎原生条目——直播态推定挂退役，B40 ⓶）."""
        eng = _make(compiled)
        st = _spx(eng)
        assert _avail(eng, "150101") and not _avail(eng, "150108")
        assert not _avail(eng, "150110"), "150110 重名变体恒不可用（1 < 0 良构闸）"
        _cast(eng, "1501", "150102")
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点（3→2，tbgd 权威）"
        assert math.isclose(st.resources["_live"], 1.0)
        assert math.isclose(st.resources["_engagement"], 0.0)
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "进战 20 点好活当赏（引擎统发，合并值口径）")
        assert st.banger_entries == [{"value": 20.0, "turns": 2.0}], (
            "引擎原生条目列表——单条目 20 点/2 回合独立计时（B40 ⓶）")
        assert "CERTIFIED_BANGER" not in st.modifiers, "旧 modifier 层账推定挂摘除（防双发）"
        assert not _avail(eng, "150101") and _avail(eng, "150108")
        assert _avail(eng, "150109") and not _avail(eng, "150102"), "直播态内开播技互斥"

    def test_enhanced_basic_finalize(self, compiled):
        """强化普攻 lv6（主 1.0/邻 0.5）+ 天赋主段 0.4 欢愉真路由（好活当赏门内——src=进战
        20 合并值）：e1 吃 1.0×ATK×Z0P+_el(0.4,20,CZ_P)、e2 吃 0.5×ATK×Z0P；削韧主 10
        （天赋 5 随编译互斥闸摘除——欢愉段削韧无通道，引擎缺口在案）、邻 5；结算下播."""
        eng = _make(compiled)
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150108")
        assert math.isclose(hp1 - e1.current_hp,
                            1.0 * ATK * Z0P + _el(0.4, 20, CRIT_ZONE_P), rel_tol=1e-9), (
            "主 1.0 直伤 + 天赋 0.4 欢愉真路由（param(150104,3) lv10，缺省定槽=好活当赏 20）")
        assert math.isclose(hp2 - e2.current_hp, 0.5 * ATK * Z0P, rel_tol=1e-9), (
            "相邻 lv6=0.5；天赋相邻段 #4 待收不计")
        assert math.isclose(e1.toughness, 90.0), (
            "主 10；天赋附伤削韧 5 摘除（category elation × toughness_dmg 编译互斥——引擎缺口在案）")
        assert math.isclose(e2.toughness, 95.0), "邻 5（tbgd 15÷3）"
        assert math.isclose(st.resources["_live"], 0.0), "结算直播连线结果（官方 desc）"
        assert math.isclose(eng.state.skill_points, 3.0), "开播-1 强普+1"
        assert math.isclose(st.current_energy, 40.0), "强普回能 40（tbgd）"
        assert _avail(eng, "150101") and not _avail(eng, "150108")


class TestTalentGate:
    def test_no_banger_no_bonus(self, compiled):
        """好活当赏门：条目清空后打强化普攻/终结技 → 天赋附伤两子句都不发（勘正②终结技半）；
        终结技 #3=0.6×欢愉度段不闸（本体伤害动态项，与门无关——(0.5+0.168)×ATK×Z0P）."""
        eng = _make(compiled)
        st = _spx(eng)
        st.banger_entries.clear()           # 进战 20 清空=无好活当赏（门控 resource_of 快照域）
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "1501", "150108")   # 绕过 available_if 直施——无好活当赏
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK * Z0P, rel_tol=1e-9), (
            "无天赋主段 0.4（好活当赏条目空——resource_of 门未过）")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (0.5 + 0.6 * ELATION) * ATK * Z0P, rel_tol=1e-9), (
            "终结技 lv10：#2=0.5 ATK 段 + #3=0.6×0.28 欢愉度段——无天赋全体 0.48")
        assert math.isclose(hp2 - e2.current_hp, (0.5 + 0.6 * ELATION) * ATK * Z0P, rel_tol=1e-9)


class TestUltimate:
    def test_ult_damage_and_economy(self, compiled):
        """终结技（无好活当赏——条目清空口径）：全体 (0.5+0.168)×ATK×Z0P（#2 ATK 段 + #3
        欢愉度动态段，同面板口径）、削韧 20、返能 5；笑点 1（进战）+2（本体）+2（万花筒
        1 欢愉）=5、爆点 +1；palette 重烘暴伤 +0.40."""
        eng = _make(compiled)
        st = _spx(eng)
        st.banger_entries.clear()
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp, (0.5 + 0.6 * ELATION) * ATK * Z0P, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, (0.5 + 0.6 * ELATION) * ATK * Z0P, rel_tol=1e-9)
        assert math.isclose(e1.toughness, 80.0), "削韧 20（tbgd 60÷3；#3 段无追加削韧）"
        assert math.isclose(st.current_energy, 5.0), "满 160 开大返 5"
        assert math.isclose(eng.state.punchline, 5.0), "1+2+2（进战 1，单欢愉档）"
        assert math.isclose(st.resources["thrill"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.08 * 5, rel_tol=1e-9), "1501103：5 笑点×8% 重烘"
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"],
                            0.5 + 0.08 * 5, rel_tol=1e-9), "team scope 辅手同吃"

    def test_ult_with_banger_talent(self, compiled):
        """开播后开大（好活当赏=进战 20 门内）：全体 (0.5+0.168)×ATK×Z0P + 天赋 0.48 欢愉
        真路由（缺省定槽=持有者好活当赏合并值 20；palette 读获得笑点前面板 0.713）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (0.5 + 0.6 * ELATION) * ATK * Z0P + _el(0.48, 20, CRIT_ZONE_P),
                            rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp,
                            (0.5 + 0.6 * ELATION) * ATK * Z0P + _el(0.48, 20, CRIT_ZONE_P),
                            rel_tol=1e-9)
        assert math.isclose(e1.toughness, 80.0), (
            "终结技 20；天赋附伤削韧 5 摘除（编译互斥——引擎缺口在案）")
        assert math.isclose(eng.state.punchline, 5.0), "进战 1+2+2"


class TestKaleidoscope:
    def test_two_elation(self, compiled):
        """1501102 二欢愉档：开大额外 +4 笑点 +1 爆点（count_team('elation')==2）."""
        eng = _make(_compiled(extra_elation=1))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(eng.state.punchline, 8.0), "2+2+4（进战 2 欢愉各 +1）"
        assert math.isclose(st.resources["thrill"], 1.0), "爆点档 1/1/4——二欢愉 +1（终结技本体不产爆点）"

    def test_three_elation(self, compiled):
        """1501102 ≥3 欢愉档：开大额外 +8 笑点 +4 爆点（进战 +3 → 合计 13，队伍账实测无 10 钳）."""
        eng = _make(_compiled(extra_elation=2))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(eng.state.punchline, 13.0), "3+2+8=13（进战 3；旧 2+8=10 恰逢 max 10 未能证伪钳制）"
        assert math.isclose(st.resources["thrill"], 4.0), "≥3 档 +4"


class TestElationSkill:
    def test_signal_overflow_segments(self, compiled):
        """欢愉技 lv10（手动对轴——体系触发行动不走合法集，直施对轴）：全体 0.5 + 追加
        20 段×0.25 随机单体（expected 按序取首全落 e1），全段笑点池实时值（进战 1）欢愉
        真路由——e1 吃 _el(5.5,1,CZ_P)；e2 只吃全体 0.5（勘正①：hook 全体段已删，无双倍）."""
        eng = _make(compiled)
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2, sp0 = e1.current_hp, e2.current_hp, eng.state.skill_points
        _cast(eng, "1501", "150120")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(0.5 + 20 * 0.25, 1, CRIT_ZONE_P), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, _el(0.5, 1, CRIT_ZONE_P), rel_tol=1e-9), (
            "全体主段 action scaling elation 行键单承——无 hook 重复结算")
        assert math.isclose(st.resources["thrill"], 2.0), "#4=2 爆点"
        assert math.isclose(eng.state.skill_points, sp0), "不耗点（tbgd）"
        assert math.isclose(st.current_energy, 5.0), "回能 5（tbgd）"
        assert math.isclose(e1.toughness, 100.0), "削韧待实测保守 0"

    def test_e3_level_gear(self, compiled):
        """E3 联动：欢愉技 lv11（全体 0.525、追加 0.2625×20）+ 普攻 lv7=1.1 档."""
        eng = _make(_compiled(eidolon=3))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150120")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(0.525 + 20 * 0.2625, 1, CRIT_ZONE_P), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, _el(0.525, 1, CRIT_ZONE_P), rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp1 - e1.current_hp, 1.1 * ATK * Z0P, rel_tol=1e-9), (
            "普攻默认 lv6，E3+1 → lv7=index 6=1.1（勘正⑫）")

    def test_e5_level_gear(self, compiled):
        """E5 联动：终结技 lv12=index 11=0.54 + 天赋 lv12 #2=0.528 欢愉真路由；欢愉技 lv12
        （全体 0.55、追加 0.275×20——开大后池 10/E1 抗穿 0.15/E4 欢愉度 0.64 实时面板）."""
        eng = _make(_compiled(eidolon=5))
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _cast(eng, "1501", "150102")
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        assert math.isclose(hp1 - e1.current_hp,
                            (0.54 + 0.6 * ELATION) * ATK * Z0P + _el(0.528, 20, CRIT_ZONE_P),
                            rel_tol=1e-9), (
            "终结技 lv12 #2=0.54+#3=0.168 + 天赋 lv12 0.528 欢愉（E4 欢愉度件晚模板钩——本发不吃）")
        assert math.isclose(hp2 - e2.current_hp,
                            (0.54 + 0.6 * ELATION) * ATK * Z0P + _el(0.528, 20, CRIT_ZONE_P),
                            rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1501", "150120")
        # 开大后笑点 1+2+2+5(E4)=10：palette 暴伤 0.633+0.80=1.433、E1 抗穿 0.015×10=0.15、
        # E4 欢愉度 0.28+0.36=0.64——实时面板
        cz = 1 + 0.17 * (0.633 + 0.08 * 10)
        res = 1 + 0.015 * 10
        assert math.isclose(eng.state.punchline, 10.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.64, rel_tol=1e-9), (
            "E4 欢愉度 +36%（开大后挂——本发欢愉技起吃）")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(0.55 + 20 * 0.275, 10, cz, el=0.64) * res, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp,
                            _el(0.55, 10, cz, el=0.64) * res, rel_tol=1e-9)


class TestEidolons:
    def test_e1_res_pen_halo(self):
        """E1（勘正⑤收编）：每笑点全体抗穿 +1.5%——开大后 5 笑点（进战 1+2+2）→ 0.075；再开大 9 笑点 → 0.135."""
        eng = _make(_compiled(eidolon=1))
        st, ally = _spx(eng), eng.state.actors["ally"]
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.015 * 5, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.015 * 5, rel_tol=1e-9)
        _ult(eng)
        assert math.isclose(eng.state.punchline, 9.0)
        assert math.isclose(eng.pipeline.effective_stats(ally)["res_pen"], 0.015 * 9, rel_tol=1e-9), (
            "on_resource_gain 重挂 replace 重烘追层")

    def test_e4_extra_punchline(self):
        """E4：开大额外 +5 笑点 → 1+2+2+5=10；palette 重烘 0.08×10=0.80；欢愉度 +36%·3 回合
        （B40 ⓹——星魂钩晚模板钩，本发终结技各段不吃）."""
        eng = _make(_compiled(eidolon=4))
        st = _spx(eng)
        _ult(eng)
        assert math.isclose(eng.state.punchline, 10.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.08 * 10, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"],
                            0.28 + 0.36, rel_tol=1e-9), "E4 欢愉度件（B40 ⓹ stat_effects elation）"
        assert math.isclose(st.modifiers["SPARXIE_E4_ELATION"].duration, 3.0)

    def test_e6_res_pen_and_damage(self):
        """E6：全属性抗穿 +20%（stat_effects 直挂）——普攻抗性区 1.0→1.2."""
        eng = _make(_compiled(eidolon=6))
        st, e1 = _spx(eng), eng.state.actors["e1"]
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "1501", "150101")
        assert math.isclose(hp1 - e1.current_hp,
                            1.1 * ATK * 0.5 * 1.2 * 0.9 * CRIT_ZONE_P, rel_tol=1e-9), (
            "eidolon=6 含 E3 → 普攻 lv7=1.1 档联动；进战池 1 → palette 暴伤 0.713")
        _ult(eng)   # E1 联动：10 笑点（1 进战+2+2+5）→ 抗穿合计 0.2+0.15
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"],
                            0.2 + 0.015 * 10, rel_tol=1e-9)


class TestAhaInstantEnd:
    def test_e1_aha_end_punchline(self):
        """E1（B40 ⓸）：阿哈时刻结束 +5 笑点——池 7 消耗→清池→E1 +5 落清后池；授好活当赏
        =消耗池值 7（进战 20+7=27 合并）；代放 150120 全段读实时池 7（insert 闩已摘）；
        +5 同时重烘 palette 0.633+0.40 与 E1 抗穿 0.075."""
        eng = _make(_compiled(eidolon=1))
        st = _spx(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        eng.state.punchline = 7.0       # 直写不触发获得联动——palette 保持进战烘焙 0.713
        hp1, hp2 = e1.current_hp, e2.current_hp
        eng._run_aha_turn()
        assert math.isclose(hp1 - e1.current_hp,
                            _el(0.5 + 20 * 0.25, 7, CRIT_ZONE_P), rel_tol=1e-9), (
            "阿哈代放 150120：全体 0.5+20 段×0.25 全落 e1，src=实时池 7（20 段插闩摘除同发）")
        assert math.isclose(hp2 - e2.current_hp, _el(0.5, 7, CRIT_ZONE_P), rel_tol=1e-9)
        assert math.isclose(eng._resource_value(st, "certified_banger"), 27.0), (
            "进战 20+授予=消耗池 7（逐条目独立计时，合并加和）")
        assert math.isclose(eng.state.punchline, 5.0), "清池 7 → E1「阿哈时刻结束时」+5"
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.08 * 5, rel_tol=1e-9), "+5 经 on_resource_gain 重烘 palette"
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"],
                            0.015 * 5, rel_tol=1e-9), "E1 抗穿光环同钩重烘"

    def test_e2_aha_end_extra_turn_and_thrill(self):
        """E2（B40 ⓸）：阿哈时刻结束 → 火花额外回合入队 + 爆点 +2（代放 150120 自发 #4=2
        → 合计 4）；E1 随 eidolon=2 联动：清池 3 → +5."""
        eng = _make(_compiled(eidolon=2))
        st = _spx(eng)
        eng.state.punchline = 3.0
        eng._run_aha_turn()
        assert math.isclose(st.resources["thrill"], 4.0), (
            "代放 150120 #4=2（insert 闩摘除——代放同发）+ E2 阿哈结束 +2")
        assert len(eng.scheduler._extra_queue) == 1, "E2 额外回合入队（grant_extra_turn）"
        handle, _kind = eng.scheduler._extra_queue[0]
        assert eng.scheduler._actors[handle].actor_id == "1501"
        assert math.isclose(eng.state.punchline, 5.0), "E1 联动：清池 3 → +5"


class TestEngagementGate:
    def test_counter_cap_and_reset(self, compiled):
        """互动陷阱计数：手动施放 +1（≤20 闸）；打满 20 后不可用；再开播复位（勘正④）."""
        eng = _make(compiled)
        st = _spx(eng)
        _cast(eng, "1501", "150102")
        _cast(eng, "1501", "150109")
        assert math.isclose(st.resources["_engagement"], 1.0)
        st.resources["_engagement"] = 19.0
        assert _avail(eng, "150109"), "19<20 仍可用"
        eng.state.skill_points = 5.0
        _cast(eng, "1501", "150109")
        assert math.isclose(st.resources["_engagement"], 20.0)
        assert not _avail(eng, "150109"), "本次技能内最多发动 20 次（param(150102,1)）"
        _cast(eng, "1501", "150108")   # 结算下播
        _cast(eng, "1501", "150102")   # 再开播 → 计数复位
        assert math.isclose(st.resources["_engagement"], 0.0)
        assert _avail(eng, "150109")


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技流量变现：进战全体 0.5×ATK×Z0 火伤 + 回 2 战技点（勘正⑩ gain_skill_point 收编）."""
        eng = _make(_compiled(pre_battle=True), initial_sp=0)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(eng.state.skill_points, 2.0), "#1=2 战技点"
        assert math.isclose(1e9 - e1.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9), "#2=50% ATK"
        assert math.isclose(1e9 - e2.current_hp, 0.5 * ATK * Z0, rel_tol=1e-9)
