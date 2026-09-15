"""银狼LV.999 1506 模板端到端对轴（验收型批）：真模板 YAML → 编译 → Hidden MMR/笑点队伍账/
好活当赏条目账/Godmode 状态机/强化普攻欢愉化/盲盒概率闩/欢愉技正身/秘技/星魂全链 →
手算全等（过堂勘正十五件 + B40 迁移记六条 + 在案四件见 fixture 头注）。

口径常数：银狼LV.999 atk 388.08；行迹折入后面板（B40 在案㈣ 钓出回填——1506201-1506210
十节点旧 fixture 全漏）crit_rate 0.197（0.05+0.147）、crit_dmg 0.5、spd 119（110+9——
1506101 欢愉度仍 0 档）、elation 0.1（ElationDamageAddedRatioBase 0.04+0.06——B40 P1b
终审映射面板键）；max_energy 0（Hidden MMR 特殊充能——ult_cost_resource 门槛 60）。
实取档（默认 basic lv6 / 其余 lv10；欢愉技 level_key=elation_skill 缺省回退 10）：
战技 lv10=1.6（Punchline 5）；终结技 lv10：盲盒倍率 0.9/衰减 0.2；天赋 lv10：追加 0.4、
CR 0.004/点、CD 0.008/点、3 次退出；强化普攻 lv6：弹射 2.4/Final Hit 1.0/增伤档 0.15×
min(round(MMR/60),2)；欢愉技 150620 全档 +15 MMR；150621 lv10=0.9×6 段。
假人 def 1000 → 防御区 0.5；弱点 imaginary → 抗性区 1.0；未击破 0.9。
期望暴击区 = 1+实时CR×0.5（MMR 转模 stat_exprs 实时面板——断言按各时点 MMR 实算；
CR 封顶=100%−无条件件面板动态式，B40 在案㈣）。

欢愉伤害真路由（B40 迁移记⓷——ATK×倍率占位全退役）：纯倍率×等级系数 LV_COEF 7535.107
×(1+elation 面板)×(1+5·src/(src+240))×(1+merrymake)×期望暴击区×0.5×抗性×易伤×0.9
×(1+final_dmg_boost)，见 `_el`（乘区书写序与 rulebook elation_damage 链一致）。
src 定槽（21_elation §21.2）：150621=阿哈笑点池实时值×(1+E4 闩 5)、秘技豆=99 字面
（官方 #1 "fixed amount ... taken into account"）、其余（天赋追加/150608 本体+Final Hit/
盲盒主干）=持有者好活当赏合并值（进战 20 引擎统发起即持——旧 CERTIFIED_BANGER
modifier 布尔闩翻案，B40 ⓶）。好活当赏=引擎原生条目列表（st.banger_entries 逐条目
独立 2 回合计时，eng._resource_value 读合并值）；笑点=队伍账 eng.state.punchline
（custom_resource 声明退役）；欢愉技 action_type=elation_skill 正身（合法行动集引擎
排除——体系触发行动，B40 ⓵）；Final Hit/盲盒均分=amount/enemies_alive() 手算分母
（迁移钓出——官方 split/distributed evenly 明示，旧「全体各吃全额」与注释矛盾勘正）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import legal_action_set
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 388.08
LV_COEF = 7535.107                     # 欢愉伤害等级系数 Lv.80（rulebook elation_level_multiplier）
CR0 = 0.05 + 0.147                     # 暴击率面板（基础 + 行迹节点折入）= 0.197
ZONE = 0.5 * 1.0 * 0.9                 # 直伤链：防御区 × 抗性区 × 未击破


def _cz(mmr: float, *, cr_per: float = 0.004) -> float:
    """期望暴击区（MMR 转模实时面板，未触顶区间）：1 + (0.197 + MMR×cr_per) × 0.5."""
    return 1 + (CR0 + mmr * cr_per) * 0.5


def _pm(src: float) -> float:
    """笑点乘区（rulebook zones.punchline_multi 同式）."""
    return 1 + 5 * src / (src + 240)


def _el(mult: float, src: float, cz: float, *, mm: float = 0.0, fd: float = 0.0,
        vuln: float = 1.0, res: float = 1.0) -> float:
    """欢愉伤害期望（expected 模式；乘区书写序与 rulebook elation_damage 链一致）.

    mult=纯倍率；src=punchline_source（150621=笑点池×(1+E4 闩)、秘技豆=99、其余=好活当赏
    合并值）；cz=期望暴击区；mm=merrymake（E6）；fd=final_dmg_boost（150608 增伤档）；
    elation 面板恒 0.1（行迹节点；spd 119<160 → 1506101 给 0）→ elation_multi=1.1。
    """
    return (LV_COEF * mult * 1.0 * 1.0 * cz * (1 + 0.1) * _pm(src) * (1 + mm)
            * 0.5 * res * vuln * 1.0 * 0.9 * (1 + fd))


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1506", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "战技", "action_type": "skill",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 20, "skill_point_cost": 1},
                     {"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1506", "technique": "150607"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["imaginary"]}],
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


def _sw(eng):
    return eng.state.actors["1506"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


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
    st = _sw(eng)
    ult = next(a for a in eng.actions_by_actor["1506"] if a.action_id == "150603")
    assert eng._fire_ultimate(st, ult) is True


class TestSilverWolfCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1506"]}
        assert set(acts) == {"150601", "150602", "150603", "150608",
                             "150610", "150612", "150618", "150620", "150621"}
        assert acts["150620"].action_type == acts["150621"].action_type == "elation_skill", (
            "欢愉技 action_type 正身（B40 ⓵）")
        assert acts["150608"].scaling == [], (
            "强化普攻本体欢愉伤 hook 承载——action 层 elation 行键=笑点池错槽不用（B40 ⓷）")
        decls = compiled.resource_decls_by_actor["1506"]
        assert "punchline" not in decls, "笑点=队伍账引擎原生——声明退役（B40 ⓶）"
        assert decls["hidden_mmr"]["max"] == 300
        assert decls["_lootbox_p"]["current"] == 1.0
        assert decls["_e4_pl_mult"]["current"] == 0.0, "E4 计入倍加闩缺省 0（E0 不计）"
        assert decls["banger_turns"]["current"] == 2.0, "好活当赏缺省 2 回合档"
        ult = next(a for a in compiled.actions_by_actor["1506"] if a.action_id == "150603")
        assert ult.ult_cost_resource == "hidden_mmr" and ult.ult_cost_amount == 60
        # 欢愉技独立档轨（勘正⑨——E3/E5 欢愉技+1 不与战技+2 串档）
        lk = {a.action_id: a.level_key for a in compiled.actions_by_actor["1506"]}
        assert lk["150620"] == lk["150621"] == "elation_skill"

    def test_elation_skill_not_in_legal_set(self, compiled):
        """欢愉技=体系触发行动（阿哈时刻/代放族）——合法行动集引擎排除，顶替旧 follow_up
        占位（B40 ⓵，8009 同法）；available_if 形态互斥闩保留（非 res_aha_turn 类锚）."""
        eng = _make(compiled)
        legal = {a.action_id for a in legal_action_set(
            _sw(eng), eng.actions_by_actor["1506"], 5)}
        assert "150620" not in legal and "150621" not in legal
        assert "150601" in legal and "150602" in legal


class TestBattleStart:
    def test_loadout(self, compiled):
        """进战两件（B40 引擎 _init_aha 原生统发）：+1 笑点（欢愉角色×1）/ 好活当赏 20 点
        条目 2 回合；行迹折入面板（在案㈣——crit 0.197/spd 119/elation 0.1）."""
        eng = _make(compiled)
        st = _sw(eng)
        assert math.isclose(eng.state.punchline, 1.0), "§8.2 进战每欢愉角色 +1"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "§8.1 进战 20 点好活当赏（引擎统发，合并值口径）")
        assert st.banger_entries == [{"value": 20.0, "turns": 2.0}], (
            "引擎原生条目列表——单条目 20 点/2 回合独立计时（B40 ⓶）")
        assert "CERTIFIED_BANGER" not in st.modifiers, "旧 modifier 布尔闩翻案摘除"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.197, rel_tol=1e-9), "0.05+行迹 0.147（在案㈣）"
        assert math.isclose(eff["spd"], 119.0, rel_tol=1e-9), "110+行迹 9"
        assert math.isclose(eff["elation"], 0.1, rel_tol=1e-9), (
            "行迹 ElationDamageAddedRatioBase 0.04+0.06 → elation 面板（B40 P1b 映射终审）")


class TestSkillAndPunchline:
    def test_skill_dmg_and_resource_link(self, compiled):
        """战技 lv10=1.6 全体 + 天赋追加 0.4 欢愉（进战 20 好活门自动通过——B40 ⓶⓷）：
        本体 388.08×1.6×0.45×1.0985=306.9402336（MMR=0 → CR 0.197）；追加每敌
        _el(0.4,20,1.1085)≈2289.9155（钩序=官方「Gains Punchline ... and deals」获得在
        先——与 8009 先伤后得相反，按本角色文本序：追加吃发放后 MMR=5 面板 CR 0.217）；
        Punchline 1+5=6；天赋等量 MMR +5；SP 3→2."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150602")
        total = 306.9402336 + _el(0.4, 20, _cz(5))
        assert math.isclose(hp1 - e1.current_hp, total, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, total, rel_tol=1e-9)
        st = _sw(eng)
        assert math.isclose(eng.state.punchline, 6.0), "进战 1 + 战技 5"
        assert math.isclose(st.resources["hidden_mmr"], 5.0), "天赋等量联动（进战发放不触发）"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "好活当赏=进战 20（1506 自体无发放技能——供给引擎进战/阿哈结算）")
        assert math.isclose(eng.state.skill_points, 2.0)

    def test_basic_toughness_and_crit_convert(self, compiled):
        """普攻 lv6=1.0 + 天赋追加（pool $event.target 单体——勘正⑥）：战技后 MMR=5 →
        CR=0.197+5×0.004=0.217 → 暴击区 1.1085；本体 388.08×0.45×1.1085=193.584006；
        追加 _el(0.4,20,1.1085)；削韧 10（fandom 补写）."""
        eng = _make(compiled)
        _cast(eng, "1506", "150602")   # MMR → 5
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150601")
        assert math.isclose(hp - e1.current_hp,
                            193.584006 + _el(0.4, 20, _cz(5)), rel_tol=1e-9)
        assert math.isclose(e1.toughness, 80.0), "战技 10 + 普攻 10 各削韧"
        st = _sw(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.217, rel_tol=1e-9), "CR 转模 stat_exprs 现场追踪（勘正③）"

    def test_crit_convert_cap_and_overflow(self, compiled):
        """MMR 灌满 300：CR=0.197+min(1.2, 0.803)=1.0 封顶（动态封顶=100%−无条件件面板
        0.197——B40 在案㈣）；CD=0.5+(300−200.75)×0.008=1.294."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 300.0)
        assert math.isclose(st.resources["hidden_mmr"], 300.0), "max 300 clamp"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 1.0, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], 1.294, rel_tol=1e-9)


class TestElationSkills:
    def test_pro_gamer_move_and_trace_thresholds(self, compiled):
        """150620：MMR +15；1506102 两档——池=进战 1+45=46（≥40）→ 再 +20+20；合计 +55
        （150620 档读池快照——E4 仅及 150621，B40 ⓸ per-action 拆钩）."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "punchline", 45.0)   # 天赋联动 MMR +45
        assert math.isclose(st.resources["hidden_mmr"], 45.0)
        _cast(eng, "1506", "150620")
        assert math.isclose(st.resources["hidden_mmr"], 45 + 15 + 20 + 20), (
            "欢愉技 +15 + 行迹两档 +40")

    def test_honkai_dmg_demo_and_chance_reset(self, compiled):
        """150621 lv10=0.9×6 段欢愉伤（expected 按序取首=e1 独吃）：笑点池实时值=进战 1
        （E0 闩 0），每段 _el(0.9,1,1.0985)≈3764.0489，6 段≈22584.2935；盲盒概率闩重置 1.0."""
        eng = _make(compiled)
        st = _sw(eng)
        st.resources["_lootbox_p"] = 0.2
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150621")
        assert math.isclose(hp1 - e1.current_hp, _el(0.9, 1, _cz(0)) * 6, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0), "随机单体 6 段全落首敌（expected）"
        assert math.isclose(st.resources["_lootbox_p"], 1.0), "概率闩重置"


class TestUltimateGodmode:
    def test_enter_state_chain(self, compiled):
        """进状态：MMR 60 扣空 + 1506103 +20 → 20；_godmode 闩/免疫件挂；好活当赏=进战
        条目（B40 ⓶——官方「While holding」=持有前提非获得途径，挂载件退役）；行动提前
        100%（remaining → 0）；普攻/战技/150620 与强化普攻/150621 可用性互斥翻转."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        assert math.isclose(st.resources["hidden_mmr"], 20.0), "60 扣空 + 行迹 +20"
        assert math.isclose(st.resources["_godmode"], 1.0)
        assert "GODMODE_PLAYER" in st.modifiers
        assert "ENH_BASIC_DMG" in st.modifiers, "增伤档随状态挂载（勘正⑭/B40 ⓺）"
        assert "CERTIFIED_BANGER" not in st.modifiers, "布尔闩挂载件退役（B40 ⓶）"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "好活当赏=进战 20 条目（引擎原生）")
        assert math.isclose(_remaining(eng, "1506"), 0.0), "行动提前 100%"
        acts = {a.action_id: a for a in eng.actions_by_actor["1506"]}
        assert not eng._available_if_ok(st, acts["150601"])
        assert not eng._available_if_ok(st, acts["150602"])
        assert not eng._available_if_ok(st, acts["150620"])
        assert eng._available_if_ok(st, acts["150608"])
        assert eng._available_if_ok(st, acts["150621"])


class TestEnhancedBasic:
    def _enter_godmode(self, compiled, mmr_after: float):
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)                       # MMR → 20
        st.resources["hidden_mmr"] = mmr_after
        return eng

    def test_dmg_bonus_snapshot_low_mmr(self, compiled):
        """MMR=20：增伤档 0.15×min(round(1/3),2)=0（final_dmg_boost 槽动态追踪——B40 ⓺）；
        CR=0.197+20×0.004=0.277 → 暴击区 1.1385。本体欢愉化（B40 ⓷——好活当赏合并值 20
        定槽）：弹射（压缩单段 lv6=2.4）_el(2.4,20,1.1385)≈14111.3334 落 e1；
        Final Hit 全体均分 1.0/2=0.5（迁移钓出——官方 split evenly）每敌
        _el(0.5,20,1.1385)≈2939.8611."""
        eng = self._enter_godmode(compiled, 20.0)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150608")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(2.4, 20, _cz(20)) + _el(0.5, 20, _cz(20)), rel_tol=1e-9), (
            "e1 吃弹射 + Final Hit 均分")
        assert math.isclose(hp2 - e2.current_hp, _el(0.5, 20, _cz(20)), rel_tol=1e-9), (
            "e2 仅 Final Hit 均分")
        assert math.isclose(_sw(eng).resources["_godmode_uses"], 1.0)
        boost = eng.pipeline.effective_stats(_sw(eng))["dmg_bonus"].get("final_dmg_boost", 0.0)
        assert math.isclose(boost, 0.0, abs_tol=1e-12)

    def test_dmg_bonus_snapshot_high_mmr(self, compiled):
        """MMR=130：档 0.15×min(round(2.1667),2)=0.3；CR=0.717 → 暴击区 1.3585。
        弹射 _el(2.4,20,1.3585,fd=0.3)≈21889.6094；Final 均分 _el(0.5,20,1.3585,fd=0.3)
        ≈4560.3353（final_dmg_boost 独立乘区乘在期望暴击后——本体/Final 同吃勘正⑭，
        官方「强化普攻期间」域；150621/盲盒同吃偏差在案㈢）."""
        eng = self._enter_godmode(compiled, 130.0)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1506", "150608")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(2.4, 20, _cz(130), fd=0.3) + _el(0.5, 20, _cz(130), fd=0.3),
                            rel_tol=1e-9)
        boost = eng.pipeline.effective_stats(_sw(eng))["dmg_bonus"]["final_dmg_boost"]
        assert math.isclose(boost, 0.3, rel_tol=1e-9)

    def test_exit_after_three_uses(self, compiled):
        """3 次用尽退出：摘 Godmode/增伤档、清 MMR、闩归零（快照 +1 补偿口径）；好活当赏
        条目不动（B40 ⓶——官方退出只清 Hidden MMR，条目自然 2 回合计时）."""
        eng = self._enter_godmode(compiled, 20.0)
        st = _sw(eng)
        for _ in range(3):
            _cast(eng, "1506", "150608")
        assert math.isclose(st.resources["_godmode"], 0.0)
        assert math.isclose(st.resources["hidden_mmr"], 0.0)
        assert "GODMODE_PLAYER" not in st.modifiers
        assert "ENH_BASIC_DMG" not in st.modifiers
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "退出不清好活当赏（官方文本只清 Hidden MMR）")
        acts = {a.action_id: a for a in eng.actions_by_actor["1506"]}
        assert eng._available_if_ok(st, acts["150601"]), "退出后普通普攻恢复可用"


class TestTalentFollowUp:
    def test_skill_follow_up_all_enemies(self, compiled):
        """好活当赏追加·战技（lv10 #3=0.4）全体：门=进战 20 条目自动通过（B40 ⓶——旧
        _hang_banger 手动挂载件退役）；钩序在笑点发放钩后 → MMR=5 → CR 0.217 → 暴击区
        1.1085；每敌 _el(0.4,20,1.1085)≈2289.9155."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        dmg = hp - e1.current_hp
        skill = 306.9402336                     # 战技本体（MMR=0 时点）
        follow = _el(0.4, 20, _cz(5))           # 追加（MMR=5 时点）
        assert math.isclose(dmg, skill + follow, rel_tol=1e-9)
        assert math.isclose(follow, 2289.915539558308, rel_tol=1e-9)

    def test_follow_up_gate_snapshot(self, compiled):
        """追加门读好活当赏条目（B40 ⓶）：进战条目清空后施放战技 → 无追加（官方
        「While holding Certified Banger」=持有前提）；1506 自体无好活发放技能——
        供给仅引擎进战/阿哈结算."""
        eng = _make(compiled)
        st = _sw(eng)
        st.banger_entries.clear()
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1506", "150602")
        assert math.isclose(hp1 - e1.current_hp, 306.9402336, rel_tol=1e-9), (
            "无好活当赏 → 无追加，仅战技本体")
        assert math.isclose(eng._resource_value(st, "certified_banger"), 0.0)

    def test_basic_follow_up_event_target(self, compiled):
        """好活当赏追加·普攻（勘正⑥收录——pool $event.target 单体）：e1 独吃追加，
        e2 无伤。普攻 lv6=1.0（MMR=0）=191.837646；追加（MMR=0）_el(0.4,20,1.0985)
        ≈2269.2578."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150601", target=e1)
        assert math.isclose(hp1 - e1.current_hp,
                            191.837646 + _el(0.4, 20, _cz(0)), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0)


class TestLootBox:
    def _enter_godmode(self, compiled):
        eng = _make(compiled, initial_sp=5)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        st.resources["hidden_mmr"] = 0.0    # 清零 → CR 0.197 简化口径（增伤档 0）
        return eng

    def test_trigger_and_chance_decay(self, compiled):
        """消耗 SP（before>after）→ 盲盒触发：#3=0.9 全体均分 0.45/敌（迁移钓出——官方
        distributed evenly；好活当赏合并值 20 定槽）每敌 _el(0.45,20,1.0985)≈2552.9150；
        概率闩 1.0→0.2；再次消耗 p=0.2<0.5（expected 钉）不触发；SP 增加不触发（勘正⑬）."""
        eng = self._enter_godmode(compiled)
        st = _sw(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        eng.bus.emit("on_skill_point_change", {"before": 5, "after": 4, "reason": "skill"},
                     eng.state)
        assert math.isclose(hp - e1.current_hp, _el(0.45, 20, _cz(0)), rel_tol=1e-9)
        assert math.isclose(st.resources["_lootbox_p"], 0.2), "成功后概率 ×0.2"
        hp = e1.current_hp
        eng.bus.emit("on_skill_point_change", {"before": 4, "after": 3, "reason": "skill"},
                     eng.state)
        assert math.isclose(hp - e1.current_hp, 0.0), "p=0.2 expected 不触发"
        eng.bus.emit("on_skill_point_change", {"before": 3, "after": 4, "reason": "gain"},
                     eng.state)
        assert math.isclose(hp - e1.current_hp, 0.0), "SP 增加不触发（消耗判定）"


class TestTechnique:
    def test_munch_bean_wave_lootbox(self):
        """秘技 0 点 + 豆在场：on_wave_start 盲盒同基数均分 0.45/敌 + 99 点好活当赏计入
        （官方 #1 "fixed amount ... taken into account"——勘正⑫/B40 ⓷ 兑现）每敌
        _el(0.45,99,1.0985)≈4536.0053；秘技不发放好活当赏（保守承载退役——合并值仍
        进战 20）."""
        eng = _make(_compiled(pre_battle=True))
        st = _sw(eng)
        assert "TECH_MUNCH_BEAN" in st.modifiers
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(hp - e1.current_hp, _el(0.45, 99, _cz(0)), rel_tol=1e-9)
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "官方无发放——合并值=进战 20")


class TestEidolons:
    def test_e1_zone_vuln_and_exit_purge(self):
        """E1：进状态 all_enemies 易伤 0.2（勘正⑦——vulnerability 在案，欢愉/直伤两链
        同吃）；3 次用尽退出同步摘除."""
        eng = _make(_compiled(eidolon=1))
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["e1"])["vulnerability"],
                            0.2, rel_tol=1e-9)
        st.resources["hidden_mmr"] = 20.0
        for _ in range(3):
            _cast(eng, "1506", "150608")
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["e1"])["vulnerability"],
                            0.0, rel_tol=1e-9), "退出摘除结界易伤"

    def test_e2_extra_turn_and_use_refund(self):
        """E2：状态内 MMR 增量累计 120（含 1506103 进状态 +20——记账钩实证口径）
        → grant_extra_turn（勘正⑤）+ 强化普攻次数 -1 + 计数窗重置."""
        eng = _make(_compiled(eidolon=2))
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        assert math.isclose(st.resources["_e2_mmr_delta"], 20.0), "进状态 +20 计入增量"
        _cast(eng, "1506", "150608")   # uses 0→1
        assert math.isclose(st.resources["_godmode_uses"], 1.0)
        eng._gain_resource(st, "hidden_mmr", 100.0)   # delta 20+100=120 达档
        assert len(eng.scheduler._extra_queue) >= 1, "额外回合入队"
        assert math.isclose(st.resources["_godmode_uses"], 0.0), "恢复 1 次强化普攻"
        assert math.isclose(st.resources["_e2_mmr_delta"], 0.0), "每档重置"

    def test_e3_skill_lv12_and_elation_lv11(self):
        """E3：战技 lv12=1.76（本体 337.6342570 + 追加 lv10 档）+ 欢愉技+1 → 150621
        lv11=0.945——独立档轨不与战技+2 串档（勘正⑨）。eidolon=3 联动 E1：开大后结界
        易伤 0.2 → 150621 段伤 ×1.2（欢愉链吃易伤——vuln 乘区正常生效）；
        池=进战 1+战技 5=6 实时值."""
        eng = _make(_compiled(eidolon=3))
        st = _sw(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        assert math.isclose(hp - e1.current_hp,
                            337.6342569600001 + _el(0.4, 20, _cz(5)), rel_tol=1e-9)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        st.resources["hidden_mmr"] = 0.0
        hp = e1.current_hp
        _cast(eng, "1506", "150621")
        assert math.isclose(hp - e1.current_hp,
                            _el(0.945, 6, _cz(0), vuln=1.2) * 6, rel_tol=1e-9), (
            "E1 易伤联动（族谱 18——eidolon=N 全联动）")

    def test_e4_counted_punchline_sixfold(self):
        """E4（B40 ⓸ 收编）：150621 笑点计入=原量×(1+5)——闩 5 进战 set；池=1 → 计入 6，
        每段 _el(0.945,6,1.0985)≈4344.1065（E3 联动 lv11 档）；计入非发放——池仍 1."""
        eng = _make(_compiled(eidolon=4))
        st = _sw(eng)
        assert math.isclose(st.resources["_e4_pl_mult"], 5.0), "E4 闩进战 set（星魂无等级轨道）"
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150621")
        assert math.isclose(hp - e1.current_hp, _el(0.945, 6, _cz(0)) * 6, rel_tol=1e-9)
        assert math.isclose(eng.state.punchline, 1.0), "计入口径非发放——池不变"

    def test_e4_trace_threshold_reads_counted(self):
        """E4×1506102 联动（官方同词 "taken into account"）：池=1+3=4 → 150621 计入
        4×6=24 ∈[20,40) → 一档 +20 MMR（E0 同设计入 4 → 无档——拆钩口径 B40 ⓸）."""
        eng = _make(_compiled(eidolon=4))
        st = _sw(eng)
        eng._gain_resource(st, "punchline", 3.0)   # 天赋联动 MMR +3
        _cast(eng, "1506", "150621")
        assert math.isclose(st.resources["hidden_mmr"], 3.0 + 20.0), (
            "计入 24≥20 → 一档 +20（<40 无二档）")

    def test_e5_talent_lv12_follow_up(self):
        """E5：天赋 lv12——追加 0.44、CR 0.0044/点。战技后 MMR=5 → CR=0.219 → 暴击区
        1.1095；战技本体 lv12（E3 联动）337.6342570 + 追加每敌 _el(0.44,20,1.1095)
        ≈2521.1794."""
        eng = _make(_compiled(eidolon=5))
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        dmg = hp - e1.current_hp
        assert math.isclose(dmg, 337.6342569600001 + _el(0.44, 20, _cz(5, cr_per=0.0044)),
                            rel_tol=1e-9), "战技本体 lv12（E3 联动）+ 追加 lv12 档"

    def test_e6_res_pen_and_merrymake(self):
        """E6（全联动）：res_pen 1.0 常驻（禁限弱点保守读）→ 抗性区 2.0；merrymake 0.5
        常驻（B40 ⓺——增笑独立乘区真路由，旧 all_dmg 近似退役：普攻本体直伤不吃，
        域偏差在案㈢=追加同吃）。普攻 lv7（E3 联动）本体 388.08×1.1×0.5×2.0×0.9×1.0985
        =422.0428212；追加 lv12（E5 联动）_el(0.44,20,1.0985,mm=0.5,res=2.0)≈7488.5506."""
        eng = _make(_compiled(eidolon=6))
        st = _sw(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 1.0, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["merrymake"], 0.5, rel_tol=1e-9), (
            "增笑乘区面板键（B40 ⓺）")
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150601")
        assert math.isclose(hp - e1.current_hp,
                            422.0428212 + _el(0.44, 20, _cz(0), mm=0.5, res=2.0),
                            rel_tol=1e-9)


class TestTrace1506101:
    def test_elation_panel_speed_conversion(self, compiled):
        """大行迹 1506101（B40 ⓹ 收编——常驻件 stat_exprs 现场求值）：spd 119<160 →
        欢愉度 +0（面板仅行迹节点 0.1）；测试件 spd+60 → 179 → 0.5+0.02×19=0.88（面板
        0.98）；再 +100 → 279 → 超额 119 截 100 → 0.5+2.0=2.5（面板 2.6）."""
        eng = _make(compiled)
        st = _sw(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"], 0.1, rel_tol=1e-9)
        eng._apply_modifier(st, Modifier(
            modifier_id="TEST_SPD", name="测速", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"spd": 60.0}))
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"],
                            0.98, rel_tol=1e-9), "179 → 0.5+0.02×19=0.88 +节点 0.1"
        eng._apply_modifier(st, Modifier(
            modifier_id="TEST_SPD2", name="测速二", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"spd": 100.0}))
        assert math.isclose(eng.pipeline.effective_stats(st)["elation"],
                            2.6, rel_tol=1e-9), "279 → 超额 119 截 100：0.5+2.0=2.5 +节点 0.1"
