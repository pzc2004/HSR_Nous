"""阿格莱雅 1402 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 召唤/至高之姿/
间隙织线/附加伤害/速度层/短视之惩/星魂全链 → 手算全等.

口径常数：阿格莱雅 atk 698.544、spd 102、crit 0.05+行迹 0.12=0.17/0.5 → 期望暴击
1+0.17×0.5=1.085；行迹雷伤 0.224 → 增伤区 1.224；max_energy 350。衣匠继承白值
（atk 698.544、crit 0.05/0.5 → 期望 1.025、无雷伤行迹 → 增伤区 1.0），hp 烘焙
1539.625（1241.856×0.66+720）、spd 35.7（102×0.35）。假人 def 1000 → 防御区 0.5、
雷弱点 → 抗性区 1.0、未击破 0.9。默认档 basic 6 / skill 10 / ult 10 / 忆灵 10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

AGL_ATK = 698.544
AGL_SPD = 102.0
GM_HP = 1539.625                    # 1241.856×0.66 + 720（140204 lv10 #5/#6 烘焙）
GM_SPD = 35.7                       # 102×0.35（140204 #4 烘焙）
DMG_ZONE = 1.224                    # 行迹雷伤 +22.4%
DEF_ZONE = 0.5                      # 假人 def 1000
UNBROKEN = 0.9
CRIT_AGL = 1 + 0.17 * 0.5           # 1.085（行迹暴击率 0.12 已入面板）
CRIT_GM = 1 + 0.05 * 0.5            # 1.025


def _dmg(atk_eff, mult, *, dmg_zone=DMG_ZONE, def_pen=0.0, res_pen=0.0, crit=CRIT_AGL):
    """直伤手算链：基数 × 增伤区 × 防御区(1000/(1000(1-pen)+1000)) × 抗性区(1+pen) ×
    未击破 0.9 × 期望暴击区——全参数按实取档显式给."""
    def_multi = 1000.0 / (1000.0 * max(0.0, 1.0 - def_pen) + 1000.0)
    return atk_eff * mult * dmg_zone * def_multi * (1.0 + res_pen) * UNBROKEN * crit


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1402", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1402", "technique": "140207"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": a, "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]} for a in ("e1", "e2", "e3")],
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


def _agl(eng):
    return eng.state.actors["1402"]


def _gm(eng):
    return eng.state.actors["1402_garmentmaker"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _hits(eng):
    rec = []
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: rec.append(dict(p)))
    return rec


def _cast(eng, aid, *, target="e2"):
    """手动施放阿格莱雅行动（_execute_action 不发 on_action——调用方补发，同 _run_turn 口径）."""
    st = _agl(eng)
    a = next(x for x in eng.actions_by_actor["1402"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "1402", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": target,
        "actor_type": st.actor.actor_type}, eng.state)


def _gm_cast(eng, *, target="e2"):
    """手动施放衣匠忆灵技（trigger_action 走自动目标不可控——直调+补发，同 _cast 口径）."""
    st = _gm(eng)
    a = next(x for x in eng.actions_by_actor["1402_garmentmaker"] if x.action_id == "1140201")
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "1402_garmentmaker", "action_type": a.action_type,
        "action_id": "1140201", "target_type": a.target_type, "target": target,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _agl(eng)
    st.current_energy = 350.0
    ult = next(a for a in eng.actions_by_actor["1402"] if a.action_id == "140203")
    assert eng._fire_ultimate(st, ult) is True


def _legal(eng):
    return {a.action_id for a in eng._legal_with_available_if(
        _agl(eng), list(eng.actions_by_actor["1402"]))}


class TestAglaeaCompile:
    def test_actions_summon_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1402"]}
        assert acts == {"140201", "140202", "140209", "140203", "140208"}
        sd = compiled.summon_defs["1402_garmentmaker"]
        assert "atk" in sd.inheritance and "crit_rate" in sd.inheritance, "部分继承列表（1413/1415 先例）"
        assert math.isclose(sd.actor.stats.spd, GM_SPD), "衣匠初速 = 阿格莱雅 ×35%（烘焙）"
        decls = compiled.resource_decls_by_actor["1402"]
        assert decls["_spd_stacks"]["max"] == 7 and decls["_e2_stacks"]["max"] == 3


class TestTracesAndBattleStart:
    def test_trace_stats_and_sol_energy(self, compiled):
        """行迹属性节点入面板（crit 0.17/def×1.125/雷伤 0.224）；飞驰之阳补能至 175."""
        eng = _make(compiled)
        st = _agl(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.17), "0.05+行迹 0.12"
        assert math.isclose(eff["def_"], 485.1 * 1.125), "行迹 def_pct 0.125"
        assert math.isclose(eff["dmg_bonus"]["thunder"], 0.224), "行迹雷伤 5 节点合计"
        assert math.isclose(st.current_energy, 175.0), "飞驰之阳：0 < 175 → 补至 175"

    def test_pre_stance_legality(self, compiled):
        """姿态外：140208 锁、140209 锁（衣匠未召）；140201/140202/140203 合法."""
        eng = _make(compiled)
        assert _legal(eng) == {"140201", "140202", "140203"}


class TestSkillSummon:
    def test_summon_inherit_and_immediate_action(self, compiled):
        """战技召唤：衣匠白值继承 + hp/spd 烘焙 + 置闩 + 阿格莱雅立即行动 + 战技点/回能."""
        eng = _make(compiled)
        st = _agl(eng)
        rem0 = _remaining(eng, "1402")
        _cast(eng, "140202")
        gm = _gm(eng)
        assert gm.alive and st.resources["_gm_on_field"] == 1.0
        assert math.isclose(gm.actor.stats.hp, GM_HP), "1241.856×0.66+720（lv10 烘焙）"
        assert math.isclose(gm.current_hp, GM_HP)
        assert math.isclose(gm.actor.stats.atk, AGL_ATK), "atk 继承忆师白值"
        assert math.isclose(eng.pipeline.effective_stats(gm)["spd"], GM_SPD), "0 层：35.7"
        assert math.isclose(rem0 - _remaining(eng, "1402"), 10000.0), "立即行动=拉条 100%（距离制）"
        assert math.isclose(st.current_energy, 175.0 + 20.0), "战技回能 20"
        assert eng.state.skill_points == 2.0, "战技耗 1 点"
        assert "GM_SPD_STACKS" in gm.modifiers, "召唤回挂速度层烘焙件（0 层）"

    def test_restore_branch_heal(self, compiled):
        """140209（衣匠在场）：治疗 = #1 × 衣匠上限（lv10 50%）；互斥分支切换."""
        eng = _make(compiled)
        _cast(eng, "140202")
        gm = _gm(eng)
        assert _legal(eng) == {"140201", "140209", "140203"}, "在场后 140202 锁、140209 开"
        gm.current_hp = 500.0
        _cast(eng, "140209")
        assert math.isclose(gm.current_hp, 500.0 + 0.5 * GM_HP), "lv10 治疗 50%×1539.625"


class TestStitchAndAdditional:
    def test_stitch_apply_and_single_target(self, compiled):
        """挂标走 on_action 主目标：首刀无附加段（快照读攻击前标态）；换目标旧标摘除."""
        eng = _make(compiled)
        rec = _hits(eng)
        _cast(eng, "140202")
        rec.clear()
        _cast(eng, "140201", target="e2")
        e2 = eng.state.actors["e2"]
        basic_hits = [h for h in rec if h.get("action_type") == "basic" and h["target"] == "e2"]
        assert len(basic_hits) == 1 and math.isclose(
            basic_hits[0]["amount"], _dmg(AGL_ATK, 1.0), rel_tol=1e-9), (
            "普攻 lv6 1.0×atk×1.224×0.5×0.9×1.085")
        assert not [h for h in rec if h.get("action_type") == "additional"], (
            "首刀目标无标——附加段不触发（快照语义）")
        assert "SEAM_STITCH" in e2.modifiers, "行动后挂标（on_action 主目标口径）"
        _cast(eng, "140201", target="e1")
        assert "SEAM_STITCH" not in e2.modifiers, "单目标覆盖：新标落 e1 旧标摘除"
        assert "SEAM_STITCH" in eng.state.actors["e1"].modifiers

    def test_additional_dmg_and_talent_energy(self, compiled):
        """二刀起：附加段 = 0.3×atk 全乘区（category additional）+ 附加段命中回能 10."""
        eng = _make(compiled)
        st = _agl(eng)
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")          # 挂标
        e0 = st.current_energy
        rec = _hits(eng)
        _cast(eng, "140201", target="e2")          # 二刀：主段+附加段
        add = [h for h in rec if h.get("action_type") == "additional"]
        assert len(add) == 1 and math.isclose(add[0]["amount"], _dmg(AGL_ATK, 0.3), rel_tol=1e-9), (
            "金玫之指 lv10：0.3×atk×1.224×0.5×0.9×1.085（附加伤害吃常规乘区）")
        assert math.isclose(st.current_energy, e0 + 20.0 + 10.0), (
            "普攻回能 20 + 天赋附加段回能 10（tbgd 140204）")
        assert eng.state.skill_points == 4.0, "初始 3 - 召唤 1 + 两刀普攻各产 1"


class TestUltimateStance:
    def test_stance_modifiers_myopic_and_lock(self, compiled):
        """终结技：至高之姿套件 + 短视之惩双件（0 层：0.072×102+0.036×35.7）+ 锁普攻/战技."""
        eng = _make(compiled)
        _cast(eng, "140202")
        _ult(eng)
        st = _agl(eng)
        assert st.resources["_stance"] == 1.0 and "SUPREME_STANCE" in st.modifiers
        assert "GM_CC_IMMUNE" in _gm(eng).modifiers, "衣匠免控（grants_immune control）"
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], AGL_SPD), "0 层 SPD% = 0"
        myopic = 0.072 * AGL_SPD + 0.036 * GM_SPD       # 8.6292
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"],
                            AGL_ATK + myopic, rel_tol=1e-9), "短视之惩·阿格莱亚索件"
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["atk"],
                            AGL_ATK + myopic, rel_tol=1e-9), "短视之惩·衣匠件（stat_of 忆师速度）"
        assert _legal(eng) == {"140208", "140203"}, "姿态内：普攻/战技全锁，仅孤锋千吻+终结技"
        assert math.isclose(_remaining(eng, "1402"), 0.0), "开大立即行动"
        assert math.isclose(st.current_energy, 5.0), "350 全扣 + 施放回能 5"

    def test_enhanced_basic_blast(self, compiled):
        """孤锋千吻 lv6：主 2.0/邻 0.9×短视面板；不产点；削韧 20/10；命中带标主目标起附加段."""
        eng = _make(compiled)
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")          # 挂标 e2
        _ult(eng)
        sp0 = eng.state.skill_points
        rec = _hits(eng)
        _cast(eng, "140208", target="e2")
        atk_eff = AGL_ATK + 0.072 * AGL_SPD + 0.036 * GM_SPD     # 707.1732（0 层）
        main = [h for h in rec if h.get("action_type") == "basic" and h["target"] == "e2"]
        adj = [h for h in rec if h.get("action_type") == "basic" and h["target"] in ("e1", "e3")]
        assert math.isclose(main[0]["amount"], _dmg(atk_eff, 2.0), rel_tol=1e-9), "主目标 2.0 档"
        assert len(adj) == 2 and all(math.isclose(h["amount"], _dmg(atk_eff, 0.9), rel_tol=1e-9)
                                     for h in adj), "相邻 0.9 档 ×2"
        add = [h for h in rec if h.get("action_type") == "additional"]
        assert len(add) == 1 and math.isclose(add[0]["amount"], _dmg(atk_eff, 0.3), rel_tol=1e-9), (
            "附加段随短视面板 0.3×atk_eff")
        assert eng.state.skill_points == sp0, "孤锋千吻不产点（官方明示）"
        e2 = eng.state.actors["e2"]
        assert math.isclose(e2.toughness, 100.0 - 10.0 - 20.0), "普攻 10 + 强化主段 20"
        assert math.isclose(eng.state.actors["e1"].toughness, 100.0 - 10.0), "强化相邻段 10"


class TestSpdStacks:
    def _six_stacks(self, eng):
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")          # 挂标
        for _ in range(6):
            _gm_cast(eng, target="e2")             # 衣匠攻击带标目标 → 每层 +1

    def test_gm_attack_stacks_and_gm_dmg(self, compiled):
        """基础轨仅衣匠攻击叠层：6 层衣匠速度 35.7+6×55（1140203 lv6——忆灵槽勘正）；
        姿态外阿格莱雅速度不变."""
        eng = _make(compiled)
        rec = _hits(eng)
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")
        _gm_cast(eng, target="e2")
        gm = _gm(eng)
        assert math.isclose(_agl(eng).resources["_spd_stacks"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(gm)["spd"], GM_SPD + 55.0), "1 层 +55（lv6）"
        gm_main = [h for h in rec if h.get("action_type") == "memosprite_skill" and h["target"] == "e2"]
        assert math.isclose(gm_main[0]["amount"],
                            _dmg(AGL_ATK, 1.1, dmg_zone=1.0, crit=CRIT_GM), rel_tol=1e-9), (
            "刺纹之陷 lv6 1.1（忆灵槽勘正——E0 上限 lv6；hsr-optimizer 同取 1.10 互证）"
            "×继承 atk×1.0×0.5×0.9×1.025（衣匠无雷伤行迹）")
        self._six_stacks(eng)                      # 已有 1 层 → 再补 5 刀到 6
        for _ in range(4):
            _gm_cast(eng, target="e2")
        assert math.isclose(_agl(eng).resources["_spd_stacks"], 6.0), "基础轨 6 层封顶"
        assert math.isclose(eng.pipeline.effective_stats(gm)["spd"], GM_SPD + 6 * 55.0), "365.7"
        assert math.isclose(eng.pipeline.effective_stats(_agl(eng))["spd"], AGL_SPD), (
            "姿态外阿格莱雅不吃速度层（官方：【至高之姿】下才获得）")

    def test_stance_spd_pct_and_myopic_scaling(self, compiled):
        """6 层开大：阿格莱雅速度 102×(1+0.15×6)=193.8；短视随速度层现场变档."""
        eng = _make(compiled)
        self._six_stacks(eng)
        _ult(eng)
        st = _agl(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], AGL_SPD * 1.9, rel_tol=1e-9)
        myopic = 0.072 * AGL_SPD * 1.9 + 0.036 * (GM_SPD + 6 * 55.0)   # lv6 层速 55
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], AGL_ATK + myopic, rel_tol=1e-9), (
            "短视之惩 = 7.2%×193.8 + 3.6%×418.5（stat_exprs 现场求值）")
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["atk"], AGL_ATK + myopic, rel_tol=1e-9)


class TestGarmentmakerExit:
    def test_exit_clamp_energy_and_stance_dispel(self, compiled):
        """衣匠消失：枯草之盈回能 20 + 织运之竭保 1 层 + 至高之姿解除 + 锁重开."""
        eng = _make(compiled)
        TestSpdStacks._six_stacks(self, eng)
        _ult(eng)
        e0 = _agl(eng).current_energy
        assert eng.dismiss_summon_actor("1402_garmentmaker") is True
        st = _agl(eng)
        assert math.isclose(st.current_energy, e0 + 20.0), "1140206：消失回能 20"
        assert math.isclose(st.resources["_spd_stacks"], 1.0), "1402102：最多保留 1 层（6→1）"
        assert st.resources["_stance"] == 0.0 and "SUPREME_STANCE" not in st.modifiers
        assert "SUPREME_SPD_PCT" not in st.modifiers and "MYOPIC_DOOM_ATK" not in st.modifiers
        assert _legal(eng) == {"140201", "140202", "140203"}, "姿态解除：锁重开"

    def test_resummon_restores_one_stack(self, compiled):
        """重召按保留层数恢复：衣匠速度 = 35.7 + 1×55（lv6 层速——忆灵槽勘正）."""
        eng = _make(compiled)
        TestSpdStacks._six_stacks(self, eng)
        eng.dismiss_summon_actor("1402_garmentmaker")
        _cast(eng, "140202")
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["spd"], GM_SPD + 55.0), (
            "织运之竭：重召获得对应层数（1 层）")


class TestTechnique:
    def test_prebattle_full_pack(self):
        """秘技四件：进战召唤 + 回能 30（后飞驰之阳钳补 175）+ 全体雷伤 + 随机挂标."""
        eng = CombatEngine.from_compiled(_compiled(pre_battle=True), mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        rec = _hits(eng)
        eng.setup()
        st = _agl(eng)
        assert _gm(eng).alive, "秘技进战即召唤"
        assert math.isclose(st.current_energy, 175.0), "秘技 +30 → 30 < 175 → 飞驰之阳补至 175"
        tech = [h for h in rec if h.get("action_type") == "follow_up"]
        assert len(tech) == 3 and all(math.isclose(h["amount"], _dmg(AGL_ATK, 1.0), rel_tol=1e-9)
                                      for h in tech), "全体 100% ATK 雷伤 ×3 敌"
        stitched = [a for a in ("e1", "e2", "e3")
                    if "SEAM_STITCH" in eng.state.actors[a].modifiers]
        assert len(stitched) == 1, "随机 1 敌挂标（expected 模式序取）"
        assert all(math.isclose(eng.state.actors[a].toughness, 80.0) for a in ("e1", "e2", "e3")), (
            "秘技进战削韧 20/目标（米游社）")


class TestEidolons:
    def test_e1_true_dmg_and_energy(self):
        """E1：织线目标受击追加真伤 0.15×原伤害（含附加段）+ 攻击回能 20/次."""
        eng = _make(_compiled(eidolon=1))
        st = _agl(eng)
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")
        e0 = st.current_energy
        rec = _hits(eng)
        _cast(eng, "140201", target="e2")
        basic = [h for h in rec if h.get("action_type") == "basic"]
        add = [h for h in rec if h.get("action_type") == "additional"]
        trues = [h for h in rec if h.get("damage_type") == "true"]
        assert len(trues) == 2, "主段+附加段各追加 1 段真伤"
        # 附加段在主段事件的钩级联内先发（模板钩先于星魂钩）→ 真伤落地序 = [附加段, 主段]——按集合对轴
        got = sorted(h["amount"] for h in trues)
        want = sorted([0.15 * basic[0]["amount"], 0.15 * add[0]["amount"]])
        assert all(math.isclose(g, w, rel_tol=1e-9) for g, w in zip(got, want)), (
            "附加伤害也吃织线易伤（真伤等值口径）")
        assert math.isclose(st.current_energy, e0 + 20.0 + 10.0 + 20.0), (
            "普攻 20 + 天赋 10 + E1 攻击带标回能 20")

    def test_e2_def_pen_stacks_and_clear(self):
        """E2：双方行动各叠 14% 无视防御（≤3 层）→ 防御区 1000/1580；他人施放技能清零."""
        eng = _make(_compiled(eidolon=2))
        st = _agl(eng)
        _cast(eng, "140202")                       # 阿格莱雅行动 → 1 层
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.14)
        _cast(eng, "140201", target="e2")          # 2 层
        _gm_cast(eng, target="e2")                 # 衣匠行动 → 3 层
        assert math.isclose(st.resources["_e2_stacks"], 3.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.42)
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["def_pen"], 0.42), "衣匠同吃"
        _gm_cast(eng, target="e2")                 # 第 4 次不叠（封顶 3）
        assert math.isclose(st.resources["_e2_stacks"], 3.0)
        rec = _hits(eng)
        _cast(eng, "140201", target="e2")
        basic = [h for h in rec if h.get("action_type") == "basic"]
        assert math.isclose(basic[0]["amount"], _dmg(AGL_ATK, 1.0, def_pen=0.42), rel_tol=1e-9), (
            "3 层防御区 = 1000/(1000×0.58+1000)")
        # 辅手施放技能（uses-ability 域）→ 清零
        ally = eng.state.actors["ally"]
        a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_basic")
        tgt = eng.state.actors["e1"]
        eng.decision.select_target = lambda actor_state, action_type, candidates, engine: tgt
        eng._execute_action(ally, a)
        eng.bus.emit("on_action", {"actor": "ally", "action_type": "basic",
                                   "action_id": "ally_basic", "target_type": "single",
                                   "target": "e1", "actor_type": "character"}, eng.state)
        assert math.isclose(st.resources["_e2_stacks"], 0.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.0), "清零后无视防御移除"

    def test_e3_level_overrides(self):
        """E3：普攻 lv7（1.1 档）+ 战技 lv12（治疗 0.55）——E1/E2 联动在案（本例只断档位）."""
        eng = _make(_compiled(eidolon=3))
        _cast(eng, "140202")
        rec = _hits(eng)
        _cast(eng, "140201", target="e2")
        basic = [h for h in rec if h.get("action_type") == "basic"]
        assert math.isclose(basic[0]["amount"], _dmg(AGL_ATK, 1.1, def_pen=0.14), rel_tol=1e-9), (
            "E3 普攻+1 → lv7=1.1（E2 联动：召唤+普攻=2 层 def_pen 0.14 → 防御区 1000/1860）")
        gm = _gm(eng)
        gm.current_hp = 500.0
        _cast(eng, "140209")
        assert math.isclose(gm.current_hp, 500.0 + 0.55 * GM_HP), "E3 战技+2 → lv12=0.55"

    def test_e4_seventh_stack(self):
        """E4：层上限 7——阿格莱雅攻击也可叠层（快照语义：首刀挂标不叠，二刀起叠）."""
        eng = _make(_compiled(eidolon=4))
        st = _agl(eng)
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")          # 挂标（事件开始时无标——不叠）
        assert math.isclose(st.resources["_spd_stacks"], 0.0), "快照语义：挂标刀不叠层"
        _cast(eng, "140201", target="e2")          # E4：阿格莱雅攻击带标目标 → 1 层
        assert math.isclose(st.resources["_spd_stacks"], 1.0), "E4：阿格莱雅攻击也叠层"
        for _ in range(5):
            _gm_cast(eng, target="e2")             # 基础轨 → 2..6
        _cast(eng, "140201", target="e2")          # E4 阿格莱雅侧放行第 7 层
        assert math.isclose(st.resources["_spd_stacks"], 7.0)
        _gm_cast(eng, target="e2")
        assert math.isclose(st.resources["_spd_stacks"], 7.0), "7 层封顶"
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["spd"], GM_SPD + 7 * 57.2), (
            "E3 忆灵天赋+1 → lv7 层速 57.2")
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["spd"], AGL_SPD * (1 + 0.15 * 7), rel_tol=1e-9), (
            "209.1（E4 第 7 层也计入姿态 SPD%）")

    def test_e5_ult_talent_lv12(self):
        """E5：终结技 lv12 → 0.16/层；天赋 lv12 → 附加段 0.336（E1-E4 联动在案）."""
        eng = _make(_compiled(eidolon=5))
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")          # 挂标（快照：不叠层）
        _gm_cast(eng, target="e2")                 # 基础轨 → 1 层（开大前实得 1 层）
        _ult(eng)
        mod = _agl(eng).modifiers["SUPREME_SPD_PCT"]
        assert math.isclose(mod.stat_effects["spd_pct"], 0.16 * 1), "lv12 每层 0.16×1 层"
        rec = _hits(eng)
        _cast(eng, "140208", target="e2")
        # 主段/附加段结算在钩级联（E4 叠层→2）之前：面板 = 1 层（姿态 SPD% 0.16、衣匠
        # +57.2——E3 忆灵天赋+1 → lv7）
        atk_eff = AGL_ATK + 0.072 * (AGL_SPD * (1 + 0.16 * 1)) + 0.036 * (GM_SPD + 1 * 57.2)
        add = [h for h in rec if h.get("action_type") == "additional"]
        assert math.isclose(add[0]["amount"], _dmg(atk_eff, 0.336, def_pen=0.42), rel_tol=1e-9), (
            "天赋 lv12 附加段 0.336（E2 联动：召唤+普攻+忆灵技=3 层 def_pen 0.42）")
        main = [h for h in rec if h.get("action_type") == "basic" and h["target"] == "e2"]
        assert math.isclose(main[0]["amount"], _dmg(atk_eff, 2.2, def_pen=0.42), rel_tol=1e-9), (
            "E3 联动：孤锋千吻 lv7 主 2.2 档")
        assert math.isclose(_agl(eng).resources["_spd_stacks"], 2.0), "E4：带标强化普攻后 1→2 层"

    def test_e6_thunder_res_pen(self):
        """E6：姿态内双方雷抗穿 +20% → 抗性区 1.2（E1-E5 联动：lv12 档+def_pen 0.42）."""
        eng = _make(_compiled(eidolon=6))
        _cast(eng, "140202")
        _cast(eng, "140201", target="e2")
        _ult(eng)
        st = _agl(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2)
        assert math.isclose(eng.pipeline.effective_stats(_gm(eng))["res_pen"], 0.2), "衣匠同档"
        rec = _hits(eng)
        _cast(eng, "140208", target="e2")
        # 开大时 0 层（首刀只挂标）——主段结算面板 = 0 层（短视 0.072×102+0.036×35.7）；
        # E2 联动：召唤+普攻=2 层 def_pen 0.28（强化普攻的 E2 叠层在 on_action 晚于伤害结算）
        atk_eff = AGL_ATK + 0.072 * AGL_SPD + 0.036 * GM_SPD
        main = [h for h in rec if h.get("action_type") == "basic" and h["target"] == "e2"]
        assert math.isclose(main[0]["amount"],
                            _dmg(atk_eff, 2.2, def_pen=0.28, res_pen=0.2), rel_tol=1e-9), (
            "抗性区 = 1-（0-0.2）= 1.2；E2 2 层 def_pen 0.28；E3 lv7 主 2.2")
        assert math.isclose(_agl(eng).resources["_spd_stacks"], 1.0), "E4：带标强化普攻后 0→1 层"
        eng.dismiss_summon_actor("1402_garmentmaker")
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.0), "衣匠消失姿态解除→穿透摘除"


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        """政策全链冒烟：战技召唤 → 衣匠自动行动刺纹之陷 → 开大进姿态 → 孤锋千吻."""
        eng = _make(compiled)
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert any("高举吧，升华的名讳" in l for l in log)
        assert any("衣匠 使用 刺纹之陷" in l or "刺纹之陷" in l for l in log), "衣匠自动回合施放忆灵技"
        assert any("共舞吧，命定的衣匠" in l for l in log), "政策窗口开大"
        assert any("孤锋千吻" in l for l in log), "姿态内强化普攻"
        assert _gm(eng).alive or state.actors["1402"].resources["_gm_on_field"] >= 0.0
