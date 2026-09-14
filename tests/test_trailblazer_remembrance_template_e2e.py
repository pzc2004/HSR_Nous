"""开拓者•记忆 8007（穹——与 8008 星 同人物另一实体，同套件双版本裁决回植版）模板
端到端对轴（验收型批）：真模板 YAML → 编译 →
双分支战技/终结技双档/充能循环/声援真伤/强化普攻连携/行迹/星魂全链 → 手算全等.

口径常数：本体 atk 543.312×1.14（行迹 atk 14%）=619.37568、暴伤 0.5+0.373=0.873
（期望暴击 1+0.05×0.873=1.04365）；迷迷继承白值 atk 543.312、crit 0.05/0.5（期望
1.025）、hp 烘焙 1478.2528（1047.816×0.8+640）、spd 130。暴伤光环 lv10 = 0.168×0.5
+0.336=0.42（迷迷暴伤 0.92→期望 1.046；本体 1.293→1.06465；辅手 0.92→1.046）。
假人 def 1000 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9。
默认档 basic 6 / skill 10 / ult 10 / talent 10 / 忆灵 10。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

TB_ATK = 543.312 * 1.14              # 619.37568（行迹 atk_pct 0.14 已入面板）
MEM_ATK = 543.312                    # 迷迷继承忆主白值（无行迹）
MEM_HP = 1047.816 * 0.8 + 640        # 1478.2528（800704 lv10 #2/#4 烘焙）
MEM_SPD = 130.0
AURA_CD = 0.168 * 0.5 + 0.336        # 0.42（1800703 lv10：迷迷暴伤 0.5 基线）
CRIT_TB = 1 + 0.05 * 0.873           # 1.04365（无光环——秘技开战口径）
CRIT_TB_A = 1 + 0.05 * (0.873 + AURA_CD)   # 1.06465
CRIT_MEM_A = 1 + 0.05 * (0.5 + AURA_CD)    # 1.046
DEF_ZONE = 0.5
UNBROKEN = 0.9


def _dmg(atk_eff, mult, crit):
    """直伤手算链：有效基数 × 倍率 × 增伤区 1.0 × 防御区 0.5 × 抗性区 1.0 ×
    未击破 0.9 × 期望暴击区——全参数按实取档显式给."""
    return atk_eff * mult * 1.0 * DEF_ZONE * 1.0 * UNBROKEN * crit


def _ally():
    return {"actor_id": "ally", "name": "辅手", "inline": True,
            "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
            "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "fire",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1}]}


def _ally_zero_energy():
    a = _ally()
    a["actor_id"] = "ally0"
    a["name"] = "零能辅手"
    a["base_stats"]["max_energy"] = 0
    return a


def _build(*, eidolon: int = 0, pre_battle: bool = False, ally=None, extra_template=None):
    member = {"character_template": "8007", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member]
    if extra_template:
        team.append({"character_template": extra_template, "level": 80})
    team.append(ally if ally is not None else _ally())
    build = {"build": {"team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "8007", "technique": "800707"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": a, "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["ice", "fire"]} for a in ("e1", "e2")],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False, ally=None, extra_template=None):
    return compile_encounter(
        _build(eidolon=eidolon, pre_battle=pre_battle, ally=ally, extra_template=extra_template),
        _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _tb(eng):
    return eng.state.actors["8007"]


def _mem(eng):
    return eng.state.actors["8007_mem"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _set_remaining(eng, aid, v):
    eng.scheduler._remaining[eng.scheduler._handles[aid]] = v


def _hits(eng):
    rec = []
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: rec.append(dict(p)))
    return rec


def _cast(eng, aid, *, target="e1"):
    """手动施放本体行动（_execute_action 不发 on_action——调用方补发，同 _run_turn 口径）."""
    st = _tb(eng)
    a = next(x for x in eng.actions_by_actor["8007"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "8007", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _mem_cast(eng, aid, *, target="e1"):
    """手动施放迷迷行动（同 _cast 口径——支援技可指我方目标）."""
    st = _mem(eng)
    a = next(x for x in eng.actions_by_actor["8007_mem"] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": "8007_mem", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ally_cast(eng, owner, aid, *, target="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _ult(eng):
    st = _tb(eng)
    st.current_energy = 160.0
    ult = next(a for a in eng.actions_by_actor["8007"] if a.action_id == "800703")
    assert eng._fire_ultimate(st, ult) is True


def _summon(eng):
    _cast(eng, "800702")


def _support(eng, target="ally"):
    _mem_cast(eng, "1800707", target=target)


def _legal(eng, owner="8007"):
    return {a.action_id for a in eng._legal_with_available_if(
        eng.state.actors[owner], list(eng.actions_by_actor[owner]))}


class TestTrailblazerCompile:
    def test_actions_summon_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["8007"]}
        assert acts == {"800701", "800702", "800709", "800703", "800708"}
        mem_acts = {a.action_id for a in compiled.actions_by_actor["8007_mem"]}
        assert mem_acts == {"1800701", "1800707"}
        decls = compiled.resource_decls_by_actor["8007"]
        assert decls["epic"]["max"] == 2
        assert compiled.resource_decls_by_actor["8007_mem"]["charge"]["max"] == 1, (
            "充能忆灵自持（12_summon v1.2——重召布场重置、不在场不累计）")
        sd = compiled.summon_defs["8007_mem"]
        assert "atk" in sd.inheritance and "crit_dmg" in sd.inheritance, "部分继承列表（1413/1415 先例）"
        assert math.isclose(sd.actor.stats.hp, MEM_HP), "迷迷 hp = 1047.816×0.8+640（烘焙精确值）"
        assert math.isclose(sd.actor.stats.spd, MEM_SPD), "迷迷初速 130（800704 #1）"


class TestTracesAndBattleStart:
    def test_trace_stats_and_advance30(self, compiled):
        """行迹属性节点入面板（暴伤 0.873/攻 1.14/生 1.14）；追念之权杖开战提前 30% →
        97.087-3000 钳 0."""
        eng = _make(compiled)
        st = _tb(eng)
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_dmg"], 0.873), "0.5+行迹 0.373"
        assert math.isclose(eff["atk"], TB_ATK), "543.312×1.14"
        assert math.isclose(eff["hp"], 1047.816 * 1.14), "行迹 hp_pct 0.14"
        assert math.isclose(_remaining(eng, "8007"), 7000.0), "10000-3000（距离制——拉条 30%）"


class TestSkillSummonAndRestore:
    def test_summon_branch_full_pack(self, compiled):
        """800702：耗 1 点回 30 能；召唤迷迷（继承白值+烘焙 hp/spd）；充能 0.5+0.4=0.9
        （Summon 版无充能段——#2 在「若迷迷已在场」分支内；召唤当次自身回能不计，
        社区首召 90% 互证）；暴伤光环全队；分支互斥翻转."""
        eng = _make(compiled)
        _summon(eng)
        st = _tb(eng)
        assert eng.state.skill_points == 2.0 and math.isclose(st.current_energy, 30.0)
        mem = _mem(eng)
        assert mem.alive
        assert math.isclose(mem.actor.stats.hp, MEM_HP) and math.isclose(mem.current_hp, MEM_HP)
        assert math.isclose(mem.actor.stats.atk, MEM_ATK), "atk 继承忆主白值（无行迹）"
        assert math.isclose(mem.actor.stats.max_energy, 0.0), "忆灵无能量经济定格"
        assert math.isclose(eng.pipeline.effective_stats(mem)["spd"], MEM_SPD)
        assert math.isclose(mem.resources["charge"], 0.9), "迷迷加油 0.5 + 首召 0.4（无双计）"
        assert _remaining(eng, "8007_mem") > 0.0, "90% 未满——不立即行动"
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"], 0.873 + AURA_CD), (
            "本体 0.873+光环 0.42=1.293")
        assert math.isclose(eng.pipeline.effective_stats(mem)["crit_dmg"], 0.5 + AURA_CD), (
            "迷迷自持光环（条件域读无条件件面板 0.5 基线）")
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"],
                            0.5 + AURA_CD), "辅手同吃光环"
        assert _legal(eng) == {"800701", "800709", "800703"}, "召唤后 800702 锁、800709 开"

    def test_restore_branch_heal_and_charge(self, compiled):
        """800709（迷迷在场）：治疗 0.6×迷迷上限 + 充能 +0.1（+天赋 0.03）——0.9+0.1+0.03
        触 100% 立即行动."""
        eng = _make(compiled)
        _summon(eng)
        mem = _mem(eng)
        mem.current_hp = 500.0
        _cast(eng, "800709")
        assert math.isclose(mem.current_hp, 500.0 + 0.6 * MEM_HP), "lv10 治疗 60%×1478.2528"
        assert math.isclose(mem.resources["charge"], 1.0), "0.9+0.1+0.03（30 能转化）→ 满档截断"
        assert math.isclose(_remaining(eng, "8007_mem"), 0.0), "1800703：充能达 100% 立即行动"


class TestUltimateDoubleBranch:
    def test_first_summon_e0u(self, compiled):
        """终结技首召档（E0u 嵌套 actor_enter）：充能 0.4+0.5+0.4 截 1.0 → 立即行动；
        AoE = 2.4×迷迷 atk×0.5×0.9×1.046（迷迷面板暴击——与 8007 本体钩 1.06465 分歧）；
        史诗 +1；削韧 20/敌."""
        eng = _make(compiled)
        rec = _hits(eng)
        _ult(eng)
        st = _tb(eng)
        mem = _mem(eng)
        assert mem.alive and math.isclose(mem.resources["charge"], 1.0)
        assert math.isclose(_remaining(eng, "8007_mem"), 0.0), "满充能立即行动"
        assert math.isclose(st.resources["epic"], 1.0), "8007501：终结技后 +1 层史诗"
        assert math.isclose(st.current_energy, 5.0), "160 全扣 + 施放回能 5"
        hits = [h for h in rec if h.get("action_type") == "ultimate"]
        assert len(hits) == 2 and all(
            math.isclose(h["amount"], _dmg(MEM_ATK, 2.4, CRIT_MEM_A), rel_tol=1e-9)
            for h in hits), "2.4×543.312×0.5×0.9×1.046（lv10，迷迷面板——暴伤 0.92 含光环）"
        assert all(math.isclose(eng.state.actors[a].toughness, 80.0) for a in ("e1", "e2")), (
            "终结技削韧 20/敌（钩侧承担）")

    def test_on_field_u1(self, compiled):
        """在场档（U1）：先战技召唤再开大——同倍率同面板；充能 0.9+0.4 截 1.0."""
        eng = _make(compiled)
        _summon(eng)
        rec = _hits(eng)
        _ult(eng)
        assert math.isclose(_mem(eng).resources["charge"], 1.0), "0.9+0.4 截 1.0"
        hits = [h for h in rec if h.get("action_type") == "ultimate"]
        assert len(hits) == 2 and all(
            math.isclose(h["amount"], _dmg(MEM_ATK, 2.4, CRIT_MEM_A), rel_tol=1e-9)
            for h in hits), "U1 档与 E0u 同值（迷迷面板统一通道）"


class TestTalentEnergyToCharge:
    def test_energy_waterfall(self, compiled):
        """800704：我方每回 10 能 → 迷迷 +1% 充能（// 池守恒）。本体普攻 1.0 档伤害对轴
        + 充能三步（辅手回能同计——全队累计口径）."""
        eng = _make(compiled)
        _summon(eng)
        rec = _hits(eng)
        _cast(eng, "800701")                    # 本体 +20 能 → +0.02
        assert math.isclose(_mem(eng).resources["charge"], 0.9 + 0.02)
        basic = [h for h in rec if h.get("action_type") == "basic"]
        assert len(basic) == 1 and math.isclose(
            basic[0]["amount"], _dmg(TB_ATK, 1.0, CRIT_TB_A), rel_tol=1e-9), (
            "普攻 lv6 1.0×619.37568×0.5×0.9×1.06465（光环面板）")
        _cast(eng, "800701", target="e2")
        assert math.isclose(_mem(eng).resources["charge"], 0.9 + 0.04), "两刀各 +20 能"
        _ally_cast(eng, "ally", "ally_basic")
        assert math.isclose(_mem(eng).resources["charge"], 0.9 + 0.06), "辅手 +20 能 → +0.02"


class TestEnhancedBasicJoint:
    def test_epic_consume_purify_and_joint(self, compiled):
        """800708：耗 1 史诗+净化迷迷控制件；连携双半=本体 1.2×619.38 / 迷迷 1.2×543.31
        （lv6 档，各自面板）；充能 +0.1（+天赋 0.03）；削韧 5+5；互斥翻转."""
        eng = _make(compiled)
        _summon(eng)
        _ult(eng)                               # 史诗 1、充能 1.0
        _support(eng, "ally")                   # 充能归零（声援落辅手——本例不再行动）
        assert _legal(eng) == {"800709", "800703", "800708"}, "史诗+在场 → 强化普攻开、普攻锁"
        mem = _mem(eng)
        eng._apply_modifier(mem, Modifier(
            modifier_id="TEST_FREEZE", name="测试冻结", modifier_type="control",
            debuff_kind="control", control_kind="freeze", duration=2, dispellable=True))
        sp0, e0 = eng.state.skill_points, _tb(eng).current_energy
        rec = _hits(eng)
        _cast(eng, "800708", target="e1")
        assert math.isclose(_tb(eng).resources["epic"], 0.0), "消耗 1 层史诗"
        assert "TEST_FREEZE" not in mem.modifiers, "净化迷迷全部控制类 debuff（$mod.kind 一把罩）"
        assert math.isclose(mem.resources["charge"], 0.1 + 0.03), (
            "支援归零后 +10% 充能 + 30 能转化 0.03（余量池 5+30→35 取 3）")
        tb_half = [h for h in rec if h.get("action_type") == "basic" and h["source"] == "8007"]
        mem_half = [h for h in rec if h.get("action_type") == "basic" and h["source"] == "8007_mem"]
        assert len(tb_half) == 2 and all(
            math.isclose(h["amount"], _dmg(TB_ATK, 1.2, CRIT_TB_A), rel_tol=1e-9)
            for h in tb_half), "本体半 lv6 1.2×619.37568×0.5×0.9×1.06465（全体）"
        assert len(mem_half) == 2 and all(
            math.isclose(h["amount"], _dmg(MEM_ATK, 1.2, CRIT_MEM_A), rel_tol=1e-9)
            for h in mem_half), "迷迷半 lv6 1.2×543.312×0.5×0.9×1.046（忆灵侧钩精确面板）"
        assert math.isclose(eng.state.skill_points, sp0 + 1.0), "强化普攻仍产 1 点（tbgd）"
        assert math.isclose(_tb(eng).current_energy, e0 + 30.0), "回能 30"
        assert all(math.isclose(eng.state.actors[a].toughness, 80.0 - 10.0) for a in ("e1", "e2")), (
            "终结技 20 后连携再削 5+5=10（80→70）")
        assert _legal(eng) == {"800701", "800709", "800703"}, "史诗耗尽 → 普攻回换 800701"


class TestMemospriteSkill:
    def test_baddies_bounce_and_aoe(self, compiled):
        """1800701：4 弹跳全中首敌（期望模式确定口径）0.504 档 + 末段全体 1.26 档（lv10，
        迷迷面板）；袖珍的事诗 +5% 充能；削韧 30/10."""
        eng = _make(compiled)
        _summon(eng)
        rec = _hits(eng)
        _mem_cast(eng, "1800701")
        hits = [h for h in rec if h.get("action_type") == "memosprite_skill"]
        e1_hits = [h for h in hits if h["target"] == "e1"]
        assert len(e1_hits) == 5, "4 弹跳 + 末段全体各中 e1"
        assert all(math.isclose(h["amount"], _dmg(MEM_ATK, 0.504, CRIT_MEM_A), rel_tol=1e-9)
                   for h in e1_hits[:4]), "弹跳 0.504×543.312×0.5×0.9×1.046 ×4"
        assert math.isclose(e1_hits[4]["amount"], _dmg(MEM_ATK, 1.26, CRIT_MEM_A), rel_tol=1e-9), (
            "末段全体 1.26 档")
        e2_hits = [h for h in hits if h["target"] == "e2"]
        assert len(e2_hits) == 1 and math.isclose(
            e2_hits[0]["amount"], _dmg(MEM_ATK, 1.26, CRIT_MEM_A), rel_tol=1e-9)
        assert math.isclose(_mem(eng).resources["charge"], 0.9 + 0.05), "8007102：施放 +5% 充能"
        assert math.isclose(eng.state.actors["e1"].toughness, 100.0 - 30.0), "10+5×4=30"
        assert math.isclose(eng.state.actors["e2"].toughness, 100.0 - 10.0), "末段 10"
        assert _legal(eng, "8007_mem") == {"1800701"}, "充能未满：支援锁"


class TestMemospriteSupport:
    def test_advance_support_charge_reset_and_true_dmg(self, compiled):
        """1800707：拉条 100%+附声援 3 回合+充能归零；辅手攻击追加真伤 0.36×原伤害
        （辅手能量上限 100 → 磁石记账 mem_boost 0）."""
        eng = _make(compiled)
        _summon(eng)
        mem = _mem(eng)
        mem.resources["charge"] = 1.0
        assert _legal(eng, "8007_mem") == {"1800707"}, "充能满：仅支援可点"
        _support(eng, "ally")
        ally = eng.state.actors["ally"]
        assert math.isclose(mem.resources["charge"], 0.0), "施放支援后充能归零"
        assert math.isclose(_remaining(eng, "ally"), 0.0), "拉条 100%（111.11-10000 钳 0）"
        assert "MEM_SUPPORT" in ally.modifiers
        assert math.isclose(ally.resources.get("mem_boost", 0.0), 0.0), "100 上限 → 磁石 0"
        rec = _hits(eng)
        _ally_cast(eng, "ally", "ally_basic")
        hit = [h for h in rec if h.get("damage_type") == "fire"]
        trues = [h for h in rec if h.get("damage_type") == "true"]
        assert len(hit) == 1 and math.isclose(hit[0]["amount"], _dmg(1500, 1.0, CRIT_MEM_A),
                                              rel_tol=1e-9)
        assert len(trues) == 1 and math.isclose(trues[0]["amount"], 0.36 * hit[0]["amount"],
                                                rel_tol=1e-9), (
            "声援真伤 = 0.36×原伤害（真伤不吃任何乘区）")

    def test_self_cast_no_advance(self, compiled):
        """对迷迷自身施放：仍附声援，但不触发行动提前（官方明文分支——8007 全目标拉条
        漏分支已正）."""
        eng = _make(compiled)
        _summon(eng)
        mem = _mem(eng)
        mem.resources["charge"] = 1.0
        _set_remaining(eng, "8007_mem", 4000.0)
        _support(eng, "8007_mem")
        assert "MEM_SUPPORT" in mem.modifiers
        assert math.isclose(_remaining(eng, "8007_mem"), 4000.0), "自身施放不拉条"

    def test_true_dmg_trace_scaling(self, compiled):
        """8007103 磁石与长链：本体（能量上限 160）持声援 → mem_boost 0.12 →
        真伤倍率 0.36+0.12=0.48."""
        eng = _make(compiled)
        _summon(eng)
        mem = _mem(eng)
        mem.resources["charge"] = 1.0
        _support(eng, "8007")
        st = _tb(eng)
        assert "MEM_SUPPORT" in st.modifiers
        assert math.isclose(st.resources.get("mem_boost", 0.0), 0.12), (
            "(160-100)//10×0.02=0.12（挂点记账——能量上限不变量快照）")
        rec = _hits(eng)
        _cast(eng, "800701")
        hit = [h for h in rec if h.get("damage_type") == "ice"]
        trues = [h for h in rec if h.get("damage_type") == "true"]
        assert len(hit) == 1 and len(trues) == 1
        assert math.isclose(trues[0]["amount"], 0.48 * hit[0]["amount"], rel_tol=1e-9), (
            "0.36+0.12 单段合并（官方「倍率提高」非追加段）")


class TestMemExit:
    def test_exit_pack(self, compiled):
        """迷迷消失：光环摘除（辅手暴伤回落 0.5）+ 遗憾…不留 拉忆主 25%（5000-2500）
        + 分支翻转回召唤版."""
        eng = _make(compiled)
        _summon(eng)
        _set_remaining(eng, "8007", 5000.0)
        assert eng.dismiss_summon_actor("8007_mem") is True
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["crit_dmg"],
                            0.5), "光环随灭摘除"
        assert math.isclose(_remaining(eng, "8007"), 2500.0), "1800706：行动提前 25%"
        assert _legal(eng) == {"800701", "800702", "800703"}, "迷迷离场 → 回复分支锁、召唤分支回"


class TestTechnique:
    def test_prebattle_delay_and_dmg(self):
        """秘技：全体敌人延后 50%（+5000）+ 全体冰伤 100%×本体 ATK（无光环口径 1.04365）."""
        eng = CombatEngine.from_compiled(_compiled(pre_battle=True), mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        rec = _hits(eng)
        eng.setup()
        tech = [h for h in rec if h.get("action_type") == "follow_up"]
        assert len(tech) == 2 and all(
            math.isclose(h["amount"], _dmg(TB_ATK, 1.0, CRIT_TB), rel_tol=1e-9)
            for h in tech), "1.0×619.37568×0.5×0.9×1.04365（开战无光环）"
        for a in ("e1", "e2"):
            assert math.isclose(_remaining(eng, a), 10000.0 + 5000.0), "延后 50%（距离制 +5000）"


class TestEidolons:
    def test_e1_propagation_and_crit(self):
        """E1：声援同播持有者忆灵（同 id 挂标）+ 双方暴击率 +10%（enable_if 随声援门控）
        ——迷迷弹跳 0.15 暴击率档期望 1.138 并逐击追加真伤 0.36×."""
        eng = _make(_compiled(eidolon=1))
        _summon(eng)
        mem = _mem(eng)
        mem.resources["charge"] = 1.0
        _support(eng, "8007")                   # 声援落本体 → E1 同播迷迷
        assert "MEM_SUPPORT" in mem.modifiers, "E1：声援效果对持有者的忆灵同播"
        assert math.isclose(eng.pipeline.effective_stats(_tb(eng))["crit_rate"], 0.05 + 0.1)
        assert math.isclose(eng.pipeline.effective_stats(mem)["crit_rate"], 0.05 + 0.1), (
            "忆灵同吃暴击 +10%（不可叠加=replace 同件）")
        rec = _hits(eng)
        _mem_cast(eng, "1800701")
        hits = [h for h in rec if h.get("action_type") == "memosprite_skill"]
        crit_e1 = 1 + 0.15 * (0.5 + AURA_CD)    # 1.138
        assert math.isclose(hits[0]["amount"], _dmg(MEM_ATK, 0.504, crit_e1), rel_tol=1e-9), (
            "E1 暴击率 0.15 档：期望暴击 1+0.15×0.92")
        trues = [h for h in rec if h.get("damage_type") == "true"]
        assert len(trues) == 6, "迷迷持声援：每次伤害（4 弹跳+2 末段）各追加真伤"
        got = sorted(h["amount"] for h in trues)
        want = sorted(0.36 * h["amount"] for h in hits)
        assert all(math.isclose(g, w, rel_tol=1e-9) for g, w in zip(got, want)), (
            "真伤 0.36×各原伤害（迷迷 mem_boost 0、E4 未激活）")

    def test_e2_other_memosprite_action_energy(self):
        """E2：长夜月忆灵长夜行动 → 本体 +8 能（每回合 1 次闸，本体回合开始重置）；
        本体行动不触发（域=summon 且非迷迷——勘正⑦）."""
        eng = _make(_compiled(eidolon=2, extra_template="1413"))
        st = _tb(eng)
        assert "1413_evey" in eng.state.actors, "长夜天赋进战召唤"
        evey = eng.state.actors["1413_evey"]
        a = next(x for x in eng.actions_by_actor["1413_evey"] if x.action_id == "1141301")

        def _evey_act():
            eng._execute_action(evey, a)
            eng.bus.emit("on_action", {"actor": "1413_evey", "action_type": "memosprite_skill",
                                       "action_id": "1141301", "target_type": "single",
                                       "target": "e1", "actor_type": "summon"}, eng.state)

        _evey_act()
        assert math.isclose(st.current_energy, 8.0), "E2：忆灵行动回能 8"
        _evey_act()
        assert math.isclose(st.current_energy, 8.0), "每回合至多 1 次（闸）"
        eng.bus.emit("on_turn_start", {"actor": "8007"}, eng.state)
        _evey_act()
        assert math.isclose(st.current_energy, 16.0), "本体回合开始重置可触发次数"
        _cast(eng, "800701")
        assert math.isclose(st.current_energy, 16.0 + 20.0), "本体行动不进 E2 域（仅 +普攻回能）"

    def test_e3_skill_lv12_heal(self):
        """E3：战技+2 → 800709 治疗实取 lv12=0.66×迷迷上限."""
        eng = _make(_compiled(eidolon=3))
        _summon(eng)
        mem = _mem(eng)
        mem.current_hp = 500.0
        _cast(eng, "800709")
        assert math.isclose(mem.current_hp, 500.0 + 0.66 * MEM_HP), "E3 战技 lv12=0.66"

    def test_e4_zero_energy_ally(self):
        """E4：零能量上限辅手放技 → 标记件 + 迷迷 +3% 充能；其声援真伤倍率 +6%
        （E1 联动暴击 0.15 档实算——标记 per-target，非全局旗）."""
        eng = _make(_compiled(eidolon=4, ally=_ally_zero_energy()))
        _summon(eng)
        mem = _mem(eng)
        _ally_cast(eng, "ally0", "ally_basic")
        ally0 = eng.state.actors["ally0"]
        assert "E4_SUPPORT_BONUS" in ally0.modifiers, "零能量上限放技 → E4 标记"
        assert math.isclose(mem.resources["charge"], 0.9 + 0.03 + 0.02), (
            "E4 +3%（零上限放技）+ 天赋 +2%（请求量 20 能——虚账口径在案）")
        assert "E4_SUPPORT_BONUS" not in _tb(eng).modifiers, "非零能量不挂标记"
        mem.resources["charge"] = 1.0
        _support(eng, "ally0")
        rec = _hits(eng)
        _ally_cast(eng, "ally0", "ally_basic")
        hit = [h for h in rec if h.get("damage_type") == "fire"]
        trues = [h for h in rec if h.get("damage_type") == "true"]
        crit_e1 = 1 + 0.15 * (0.5 + AURA_CD)    # 1.138（E1 联动：声援辅手暴击 +10%）
        assert len(hit) == 1 and math.isclose(hit[0]["amount"], _dmg(1500, 1.0, crit_e1),
                                              rel_tol=1e-9)
        assert len(trues) == 1 and math.isclose(trues[0]["amount"], 0.42 * hit[0]["amount"],
                                                rel_tol=1e-9), "0.36+E4 0.06=0.42 单段"

    def test_e5_ult_basic_lv_shift(self):
        """E5：普攻 lv7=1.1 档；终结技 lv12=2.64 档（E6 未激活——不固定暴击 1.046）."""
        eng = _make(_compiled(eidolon=5))
        _summon(eng)
        rec = _hits(eng)
        _cast(eng, "800701")
        basic = [h for h in rec if h.get("action_type") == "basic" and h["source"] == "8007"]
        assert len(basic) == 1 and math.isclose(
            basic[0]["amount"], _dmg(TB_ATK, 1.1, CRIT_TB_A), rel_tol=1e-9), "普攻 lv7 1.1 档"
        rec.clear()
        _ult(eng)
        hits = [h for h in rec if h.get("action_type") == "ultimate"]
        assert hits and all(math.isclose(h["amount"], _dmg(MEM_ATK, 2.64, CRIT_MEM_A),
                                         rel_tol=1e-9) for h in hits), (
            "终结技 lv12 2.64×543.312×0.5×0.9×1.046")

    def test_e6_fixed_crit_scoped(self):
        """E6：终结技暴击率固定 100%（期望暴击 1+1.0×0.92=1.92，E5 联动 lv12 2.64 档）
        ——夹心摘除作用域=终结技单段：随后 1800701 弹跳回 1.046 常态；E4 联动充能 +3%."""
        eng = _make(_compiled(eidolon=6))
        _summon(eng)
        rec = _hits(eng)
        _ult(eng)
        crit_fixed = 1 + 1.0 * (0.5 + AURA_CD)  # 1.92
        hits = [h for h in rec if h.get("action_type") == "ultimate"]
        assert hits and all(math.isclose(h["amount"], _dmg(MEM_ATK, 2.64, crit_fixed),
                                         rel_tol=1e-9) for h in hits), (
            "E6 固定暴击 × E5 lv12 2.64 档")
        assert "REVELATION_CRIT" not in _mem(eng).modifiers, "夹心摘除——暴击件不残留"
        _support(eng, "ally")                   # 充能归零
        rec.clear()
        _mem_cast(eng, "1800701")
        bounce = [h for h in rec if h.get("action_type") == "memosprite_skill" and h["target"] == "e1"]
        assert math.isclose(bounce[0]["amount"], _dmg(MEM_ATK, 0.504, CRIT_MEM_A), rel_tol=1e-9), (
            "作用域外不固定暴击（1.046 常态面板）")
        assert math.isclose(_mem(eng).resources["charge"], 0.03 + 0.05 + 0.03), (
            "E4 联动：支援施放（迷迷=零能量上限放技）+3% → 归零后入账；8007102 +5% + 本击再放技 +3%")


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        """政策全链冒烟：战技召唤 → 迷迷自动行动坏人！麻烦！ → 窗口开大."""
        eng = _make(compiled)
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert any("就决定是你了！" in l for l in log), "战技召唤"
        assert any("坏人！麻烦！" in l for l in log), "迷迷自动回合施放忆灵技"
        assert any("一起上吧，迷迷！" in l for l in log), "政策窗口开大"
        assert _mem(eng).alive or state.actors["8007"].resources.get("epic", 0.0) >= 0.0
