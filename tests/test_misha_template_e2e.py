"""米沙 1312 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 天赋 SP 计数/动态段数
终结技/逐段冻结/星魂全链 → 手算全等.

口径常数：米沙 atk 599.76（无 ATK 增益件）；行迹白值已收 → crit_rate 0.05+0.067=0.117、
冰伤区 1+0.224=1.224；期望暴击区 = 1+0.117×0.5 = 1.0585。
假人 def 1000 → 防御区 0.5；双假人均冰弱点 → 抗性区 1.0；未击破 0.9。
默认档 basic lv6 / skill·ultimate·talent lv10；eidolon=N 联动 E1..EN（E3 大招+2 → lv12、
E5 战技/天赋+2 → lv12）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 599.76
CRIT_ZONE = 1 + 0.117 * 0.5          # 1.0585（行迹 crit_rate +0.067 已并入面板）
DMG_ZONE = 1 + 0.224                 # 行迹冰伤 +22.4%
E6_ZONE = DMG_ZONE + 0.3             # E6 增伤 +30%（加算同区）
DEF_ZONE = 0.5                       # 假人 def 1000
UNBROKEN = 0.9


def _dmg(mult: float, zone: float = DMG_ZONE) -> float:
    """期望冰伤 = atk×倍率×防御区 0.5×抗性 1.0×未击破 0.9×增伤区×期望暴击区."""
    return ATK * mult * DEF_ZONE * UNBROKEN * zone * CRIT_ZONE


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1312", "level": 80}
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
        build["build"]["pre_battle"] = [{"actor_id": "1312", "technique": "131207"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, pre_battle=pre_battle), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, mode=MODE_EXPECTED, seed=None, initial_sp: int = 3):
    kw = {"seed": seed} if seed is not None else {}
    eng = CombatEngine.from_compiled(compiled, mode=mode, initial_energy_ratio=0.0,
                                     initial_sp=initial_sp, **kw)
    eng.setup()
    return eng


def _misha(eng):
    return eng.state.actors["1312"]


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
    st = _misha(eng)
    st.current_energy = 100.0
    ult = next(a for a in eng.actions_by_actor["1312"] if a.action_id == "131203")
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        candidates[0] if candidates else None)
    assert eng._fire_ultimate(st, ult) is True


class TestMishaCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1312"]}
        assert set(acts) == {"131201", "131202", "131203"}
        # 终结技载体：single（保首段指定目标语义）+ 无 scaling 不跳伤，段族全走 hooks
        assert acts["131203"].target_type == "single" and not acts["131203"].scaling
        decls = compiled.resource_decls_by_actor["1312"]
        assert set(decls) == {"_ult_bonus", "_ult_hit_dmg_bonus", "_e6_sp_armed"}
        assert "_ult_hits" not in decls, "同事件 set→读快照死链资源已整只摘除（勘正①）"


class TestTraces:
    def test_trace_stat_nodes(self, compiled):
        """行迹白值三项已收：crit_rate 0.117 / 冰伤 0.224 / def 396.9×1.225."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_misha(eng))
        assert math.isclose(eff["crit_rate"], 0.117, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["ice"], 0.224, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 396.9 * 1.225, rel_tol=1e-9)


class TestBasicSkill:
    def test_basic_damage_sp_energy(self, compiled):
        """普攻 lv6=1.0 档：dmg=atk×1.0×0.5×0.9×1.224×1.0585；SP+1、回能 20、削韧 10."""
        eng = _make(compiled)
        st, e1 = _misha(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "1312", "131201")
        assert math.isclose(hp0 - e1.current_hp, _dmg(1.0), rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0)
        assert math.isclose(st.current_energy, 20.0)
        assert math.isclose(e1.toughness, 90.0)

    def test_skill_blast_and_talent_self_count(self, compiled):
        """战技 lv10：主 2.0/邻 0.8；天赋计自耗（CN 我方全体）→ +1 段 +2 能，
        合计 +2 段、+32 能（30+2）；SP 4→3；削韧主 20/邻 10."""
        eng = _make(compiled, initial_sp=4)
        st = _misha(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp0, hp0b = e1.current_hp, e2.current_hp
        _cast(eng, "1312", "131202")
        assert math.isclose(hp0 - e1.current_hp, _dmg(2.0), rel_tol=1e-9)
        assert math.isclose(hp0b - e2.current_hp, _dmg(0.8), rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 3.0)
        assert math.isclose(st.current_energy, 32.0), "战技固有 30 + 天赋 2（自耗计入）"
        assert math.isclose(st.resources["_ult_bonus"], 2.0), "战技 +1 段 + 天赋 +1 段"
        assert math.isclose(e1.toughness, 80.0) and math.isclose(e2.toughness, 90.0)


class TestTalentTeamSP:
    def test_ally_consume_counts_gain_does_not(self, compiled):
        """天赋：队友耗点 → +1 段 +2 能（lv10 #2/#1）；产点（after>before）不触发."""
        eng = _make(compiled)
        st = _misha(eng)
        _cast(eng, "ally", "ally_skill")     # 辅手耗 1 点
        assert math.isclose(st.current_energy, 2.0)
        assert math.isclose(st.resources["_ult_bonus"], 1.0)
        _cast(eng, "ally", "ally_basic")     # 辅手产 1 点——不触发
        assert math.isclose(st.current_energy, 2.0)
        assert math.isclose(st.resources["_ult_bonus"], 1.0)


class TestUltimate:
    def test_default_3_hits_reset_energy(self, compiled):
        """E0 无累计：3 段全落 e1（首段指定 + 余段随机确定化取首）；段后 _ult_bonus 归零、
        回能 5（满 100 消耗后）."""
        eng = _make(compiled)
        st, e1 = _misha(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 3 * _dmg(0.6), rel_tol=1e-9)
        assert math.isclose(st.resources["_ult_bonus"], 0.0), "施放后段数恢复初始（官方原文）"
        assert math.isclose(st.current_energy, 5.0)

    def test_accumulated_hits_via_skill(self, compiled):
        """1 发战技（+2 段）→ 5 段."""
        eng = _make(compiled, initial_sp=4)
        e1 = eng.state.actors["e1"]
        _cast(eng, "1312", "131202")
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.6), rel_tol=1e-9)

    def test_cap_10(self, compiled):
        """秘技 +2 加 3 发战技（+6）→ 3+2+6=11 钳 10 段（min 钳制=溢出弃置在案）."""
        eng = _make(_compiled(pre_battle=True), initial_sp=5)
        st, e1 = _misha(eng), eng.state.actors["e1"]
        assert math.isclose(st.resources["_ult_bonus"], 2.0), "秘技进战 +2 段"
        for _ in range(3):
            eng.state.skill_points = 5.0
            _cast(eng, "1312", "131202")
        assert math.isclose(st.resources["_ult_bonus"], 8.0), "秘技 2 + 战技 3×(1+1)"
        e1.toughness = 100.0   # 测试布场：3 发战技已削 60——补满韧性隔离击破干扰，专验段数帽
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 10 * _dmg(0.6), rel_tol=1e-9), (
            "硬顶 10 段（param(131203,5) 全档恒定）")

    def test_first_hit_freeze_and_add_damage(self, compiled):
        """首段冻结 (0.2+0.8)×1.6=1.6 ≥0.5 expected 恒中；余段 0.32<0.5 不触发（e2 无件）；
        冻结目标回合开始附伤 0.3×atk×乘区（lv10 #4）."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _ult(eng)
        assert "MISHA_FREEZE" in e1.modifiers, "A2 首段 100% 基础概率 ×1.6"
        assert "MISHA_FREEZE" not in e2.modifiers, "余段 20%×1.6 expected 不触发"
        hp0 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp0 - e1.current_hp, _dmg(0.3), rel_tol=1e-9)

    def test_e2_never_procs_expected(self):
        """E2 0.24×1.6=0.384 < 0.5：expected 口径恒不触发（mechanic_chance 期望语义）."""
        eng = _make(_compiled(eidolon=2))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _ult(eng)
        assert "S2_DEF_DOWN" not in e1.modifiers and "S2_DEF_DOWN" not in e2.modifiers


class TestEidolons:
    def test_e1_enemy_count_hits(self):
        """E1（联动仅 E1）：2 敌在场 → +2 段 = 5 段（enemies_alive 正解——draft
        count('enemies')=len(字符串)=7→恒 +5 病已勘）；armed marker 在场."""
        eng = _make(_compiled(eidolon=1))
        st, e1 = _misha(eng), eng.state.actors["e1"]
        assert "E1_EXTRA_HITS" in st.modifiers
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.6), rel_tol=1e-9)
        eng0 = _make(_compiled(eidolon=0))
        assert "E1_EXTRA_HITS" not in _misha(eng0).modifiers

    def test_e2_roll_seed11(self):
        """E2 roll 档（seed=11 决定论）：仅首段门控掷中 → e1 独挂 S2（def 1000×0.84），
        e2 无件；冻结同种子仅 e1（首段 1.6 恒中 + 余段 0.32 未中）。逐段独立掷：
        快照相先 5 掷冻结（1.6/0.32×4）后 5 掷 E2（0.384），效果相按种子落定."""
        eng = _make(_compiled(eidolon=2), mode=MODE_ROLL, seed=11)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        _ult(eng)
        assert "S2_DEF_DOWN" in e1.modifiers and "S2_DEF_DOWN" not in e2.modifiers
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 1000 * 0.84, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e2)["def_"], 1000.0, rel_tol=1e-9)
        assert "MISHA_FREEZE" in e1.modifiers and "MISHA_FREEZE" not in e2.modifiers

    def test_e3_level_link(self):
        """E3 联动（E1+E3）：大招 lv12 → 段倍率 0.648（5 段）；普攻 lv7 → 1.1；
        冻结附伤 lv12 #4=0.324."""
        eng = _make(_compiled(eidolon=3))
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.648), rel_tol=1e-9)
        hp0 = e1.current_hp
        _cast(eng, "1312", "131201")
        assert math.isclose(hp0 - e1.current_hp, _dmg(1.1), rel_tol=1e-9)
        assert "MISHA_FREEZE" in e1.modifiers
        hp0 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp0 - e1.current_hp, _dmg(0.324), rel_tol=1e-9)

    def test_e4_multiplier_link(self):
        """E4 联动（E1+E3+E4）：段倍率 = lv12 0.648 + E4 0.06 = 0.708（加法门径），5 段."""
        eng = _make(_compiled(eidolon=4))
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.708), rel_tol=1e-9)

    def test_e5_skill_talent_levels(self):
        """E5 联动：战技 lv12 → 主 2.2/邻 0.88；天赋 lv12 → 每耗 1 点回 2.2 能."""
        eng = _make(_compiled(eidolon=5), initial_sp=4)
        st = _misha(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp0, hp0b = e1.current_hp, e2.current_hp
        _cast(eng, "1312", "131202")
        assert math.isclose(hp0 - e1.current_hp, _dmg(2.2), rel_tol=1e-9)
        assert math.isclose(hp0b - e2.current_hp, _dmg(0.88), rel_tol=1e-9)
        assert math.isclose(st.current_energy, 32.2, rel_tol=1e-9), "30 + 天赋 lv12 2.2"

    def test_e6_buff_covers_ult_and_sp_latch(self):
        """E6 联动（E1+E3+E4+E5+E6）：增伤挂 on_action 先于段族 on_ultimate → 本次大招
        5 段全吃 1.524 区（0.708 档）；后续战技（lv12 2.2）同吃；战技后 SP 净 0 变动
        （-1 耗 +1 回）、闩落；owner_turn_end 计时后增伤到期."""
        eng = _make(_compiled(eidolon=6), initial_sp=4)
        st, e1 = _misha(eng), eng.state.actors["e1"]
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.708, E6_ZONE), rel_tol=1e-9), (
            "E6 +30% 覆盖本次大招（on_action→on_ultimate 发射序——勘正④）")
        assert "S6_DMG_BOOST" in st.modifiers
        assert math.isclose(st.resources["_e6_sp_armed"], 1.0)
        sp_before = eng.state.skill_points
        hp0 = e1.current_hp
        _cast(eng, "1312", "131202")
        assert math.isclose(hp0 - e1.current_hp, _dmg(2.2, E6_ZONE), rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, sp_before), "战技 -1 + E6 回 1 = 净 0"
        assert math.isclose(st.resources["_e6_sp_armed"], 0.0), "闩落一次"
        eng._tick_modifiers(st)
        assert "S6_DMG_BOOST" not in st.modifiers, "持续至自身回合结束（duration 1）"


class TestTechnique:
    def test_pre_battle_loadout(self):
        """秘技进战 +2 段（梦中牢笼进战半）；空间捕获/互斥半待收（头注挡因）."""
        eng = _make(_compiled(pre_battle=True))
        st, e1 = _misha(eng), eng.state.actors["e1"]
        assert math.isclose(st.resources["_ult_bonus"], 2.0)
        hp0 = e1.current_hp
        _ult(eng)
        assert math.isclose(hp0 - e1.current_hp, 5 * _dmg(0.6), rel_tol=1e-9)
