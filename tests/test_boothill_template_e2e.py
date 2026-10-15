"""波提欧 1315 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 换技能互斥/
对峙双标记+额外回合/优势口袋击杀击破双链/天赋击破伤害按层/大招植弱点+推条/
秘技植入/三大行迹/E1/E2/E3/E5/E6 全链 → 手算全等。

口径常数：波提欧白值 atk 620.928（行迹 atk_pct 0.18 → 有效 732.69504）、
crit 0.05/0.5、行迹 break_effect 0.373（幽灵装填 stat_exprs 转化后
crit_rate 0.0873 / crit_dmg 0.6865 → 期望暴击区 1.05993145）、spd 107、
max_energy 115。假人 def 1000 → 防御区 0.5（E1 无视 16% → 1000/1840）；
e1/e2 物理弱点 → 抗性区 1.0、未击破 0.9、已击破 1.0；e3 无弱点（植入链专用）。
物理击破 scaling 2.0；击破基数 = 3767.5533×2.0×(0.5+100/40)×(1+BE)×防御区。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim import legal_action_set
from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---- 手算口径常数（全部可由上文推导链复算） --------------------------------
ATK = 620.928 * 1.18                      # 白值 × (1+行迹 atk_pct 0.18)
BE0, BE2 = 0.373, 0.673                   # 行迹击破 0.373；E2 触发后 +0.3
CR0 = 0.05 + min(0.1 * BE0, 0.3)          # 0.0873（幽灵装填）
CD0 = 0.5 + min(0.5 * BE0, 1.5)           # 0.6865
CE0 = CR0 * (1 + CD0) + (1 - CR0)         # 期望暴击区 1.05993145
CR2 = 0.05 + min(0.1 * BE2, 0.3)          # 0.1173（E2 触发后）
CD2 = 0.5 + min(0.5 * BE2, 1.5)           # 0.8365
CE2 = CR2 * (1 + CD2) + (1 - CR2)         # 1.09812145
D0 = 0.5                                  # 假人 def 1000 → 防御区
D1 = 1000 / (1000 * (1 - 0.16) + 1000)    # E1 无视 16% → 1000/1840
BB = 3767.5533 * 2.0 * (0.5 + 100 / 40)   # 击破基数（物理 scaling 2.0、假人韧性 100）
BRK0 = BB * (1 + BE0) * D0                # E0 击破一发（be 1.373、def 0.5、res/universal/vuln=1）
BRK1 = BB * (1 + BE0) * D1                # E1+（def_pen 0.16）
BRK1B = BB * (1 + BE2) * D1               # E2 BE buff 在挂后


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1315", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1315", "technique": "131507"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical"]},
    {"actor_id": "e3", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
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


def _bh(eng):
    return eng.state.actors["1315"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _cast(eng, aid, *, target="e1", owner="1315"):
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


def _ult(eng, *, target="e1", energy=115.0):
    st = _bh(eng)
    st.current_energy = energy
    ult = next(a for a in eng.actions_by_actor["1315"] if a.action_id == "131503")
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


def _standoff(eng, target="e1"):
    """进对峙（战技 + 手动 on_action 钩链）并返回战前 SP."""
    sp0 = eng.state.skill_points
    _cast(eng, "131502", target=target)
    return sp0


class TestBoothillCompile:
    def test_actions_available_if_and_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["1315"]}
        assert set(acts) == {"131501", "131502", "131503", "131508"}
        assert acts["131501"].available_if == "has_modifier($self, 'STANDOFF') < 1"
        assert acts["131502"].available_if == "has_modifier($self, 'STANDOFF') < 1"
        assert acts["131508"].available_if == "has_modifier($self, 'STANDOFF') >= 1"
        assert compiled.resource_decls_by_actor["1315"]["_e2_cd"]["max"] == 1
        assert any(m.modifier_id == "TRACE_1315"
                   for m in compiled.modifiers_by_actor["1315"]), "行迹小节点聚合件"
        assert math.isclose(acts["131501"].toughness_dmg, 10.0)
        assert math.isclose(acts["131508"].toughness_dmg, 20.0)
        assert math.isclose(acts["131503"].toughness_dmg, 30.0)


class TestPanels:
    def test_trace_and_ghost_load(self, compiled):
        """行迹（过堂②）：atk_pct 0.18/hp_pct 0.10/break_effect 0.373；
        幽灵装填 stat_exprs 活读 → crit 0.0873/0.6865."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_bh(eng))
        assert math.isclose(eff["atk"], ATK, rel_tol=1e-9)
        assert math.isclose(eff["hp"], 1203.048 * 1.10, rel_tol=1e-9)
        assert math.isclose(eff["break_effect"], BE0, rel_tol=1e-9)
        assert math.isclose(eff["crit_rate"], CR0, rel_tol=1e-9), "0.05+min(0.1×0.373, 0.3)"
        assert math.isclose(eff["crit_dmg"], CD0, rel_tol=1e-9), "0.5+min(0.5×0.373, 1.5)"
        assert math.isclose(eff["spd"], 107.0)


class TestBasic:
    def test_basic_damage_sp_energy_toughness(self, compiled):
        """普攻 lv6=1.0：ATK×1.0×0.5×0.9×CE0；产 1 点、回 20 能、削韧 10."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        sp0, hp0 = eng.state.skill_points, e1.current_hp
        _cast(eng, "131501")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.0 * D0 * 0.9 * CE0, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, sp0 + 1), "米游社/tbgd 双源产 1 点"
        assert math.isclose(_bh(eng).current_energy, 20.0)
        assert math.isclose(e1.toughness, 90.0), "tbgd 削韧 10"

    def test_legal_set_mutex(self, compiled):
        """换技能互斥（available_if 读 STANDOFF 件——过堂⑰）：对峙前 131501/131502、
        对峙后仅 131508."""
        eng = _make(compiled)
        st = _bh(eng)
        legal = eng._legal_with_available_if(
            st, legal_action_set(st, eng.actions_by_actor["1315"], eng.state.skill_points))
        assert {a.action_id for a in legal} == {"131501", "131502"}
        _standoff(eng)
        legal = eng._legal_with_available_if(
            st, legal_action_set(st, eng.actions_by_actor["1315"], eng.state.skill_points))
        assert {a.action_id for a in legal} == {"131508"}, "对峙中普攻强化 + 战技硬关"


class TestStandoff:
    def test_marks_extra_turn_and_expiry(self, compiled):
        """战技：耗 1 点无回能 → 自身 STANDOFF(dur 3 补偿) + 敌侧 STANDOFF_TARGET
        （forced_taunt）+ 额外回合；走字 3 次到期 → 统一链清敌侧标记."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        st = _bh(eng)
        sp0 = _standoff(eng)
        assert math.isclose(eng.state.skill_points, sp0 - 1), "tbgd BPNeed=1"
        assert math.isclose(st.current_energy, 0.0), "官方『该战技无法恢复能量』"
        assert st.modifiers["STANDOFF"].duration == 3, "官方 2 真实回合+额外回合走字补偿（过堂⑰）"
        assert e1.modifiers["STANDOFF_TARGET"].forced_taunt is True, "嘲讽（过堂⑪）"
        assert len(eng.scheduler._extra_queue) == 1, "本回合不会结束（grant_extra_turn 过堂⑦）"
        eng._tick_modifiers(st, "owner_turn_start")   # 额外回合走字
        eng._tick_modifiers(st, "owner_turn_start")   # 第 1 真实回合开始
        assert "STANDOFF" in st.modifiers and st.modifiers["STANDOFF"].duration == 1
        eng._tick_modifiers(st, "owner_turn_start")   # 第 2 真实回合开始 → 到期
        assert "STANDOFF" not in st.modifiers
        assert "STANDOFF_TARGET" not in e1.modifiers, "after_remove_modifier 统一清理链（过堂⑰）"

    def test_enhanced_basic_and_above_snakes(self, compiled):
        """强化普攻 lv6=2.2：ATK×2.2×0.5×0.9×CE0；产点 0、回 30 能、削韧 20（E0 无层不加持）；
        蛇之上行：非对峙目标（e2 源）×0.7、对峙目标（e1 源）×1.0、无对峙不减免."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": 1000.0, "damage_type": "physical", "source": "e2",
            "target": "1315", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(float(wp.get("amount", 1000.0)), 1000.0), "无对峙不减免"
        sp0 = _standoff(eng)
        hp0 = e1.current_hp
        _cast(eng, "131508")
        assert math.isclose(hp0 - e1.current_hp, ATK * 2.2 * D0 * 0.9 * CE0, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, sp0 - 1), "强化普攻无法恢复战技点"
        assert math.isclose(_bh(eng).current_energy, 30.0)
        assert math.isclose(e1.toughness, 80.0), "tbgd 削韧 20（天赋 +50%/层待收——E0 无层不变）"
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": 1000.0, "damage_type": "physical", "source": "e2",
            "target": "1315", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(float(wp.get("amount", 1000.0)), 700.0), "蛇之上行 ×0.7（非对峙目标）"
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": 1000.0, "damage_type": "physical", "source": "e1",
            "target": "1315", "action_type": "basic", "is_critical": False}, eng.state)
        assert math.isclose(float(wp.get("amount", 1000.0)), 1000.0), "对峙目标攻击不减免"


class TestUltimate:
    def test_implant_before_damage_and_delay(self, compiled):
        """大招 lv10=4.0 打 e3（无物理弱点）：on_become_target 先植弱点（过堂⑨）→
        本击即享抗性区 1.0 + 解锁削韧 30；推条 40% → 剩余 +4000；先扣 115 后返 5."""
        eng = _make(compiled)
        e3 = eng.state.actors["e3"]
        r0, hp0 = _remaining(eng, "e3"), e3.current_hp
        _ult(eng, target="e3")
        assert math.isclose(hp0 - e3.current_hp, ATK * 4.0 * D0 * 0.9 * CE0, rel_tol=1e-9), (
            "植入先于伤害结算——无弱点目标也按 0 抗性计")
        assert math.isclose(e3.toughness, 70.0), "植入解锁削韧 30（tbgd/米游社双源）"
        assert "BOOTHILL_ULT_WEAKNESS" in e3.modifiers
        assert e3.modifiers["BOOTHILL_ULT_WEAKNESS"].duration == 2
        assert math.isclose(_remaining(eng, "e3") - r0, 4000.0), "行动延后 40%（lv10 #2）"
        assert math.isclose(_bh(eng).current_energy, 5.0), "先扣 115 后返 5（tbgd/米游社双源）"


class TestPocketChains:
    def test_break_chain_then_talent(self, compiled):
        """击破链（E0）：强化普攻（削韧 20）破 e1 → 优势口袋 +1 + 解除对峙（统一链）
        + 抵近射击回 10 能；同击天赋随发 0.7×BRK0（on_break 先于 on_action——
        天赋钩读击破后新层数，与游戏"击破那一下吃新层"连发口径一致）；
        次击（目标已击破 + 1 层）天赋再追加 0.7×BRK0."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        st = _bh(eng)
        _standoff(eng)
        e1.toughness = 20.0
        hp0 = e1.current_hp
        _cast(eng, "131508")
        direct = ATK * 2.2 * D0 * 0.9 * CE0           # 伤害结算时未击破 → 0.9
        assert math.isclose(hp0 - e1.current_hp, direct + BRK0 + 0.7 * BRK0, rel_tol=1e-9), (
            "直伤 + 引擎物理击破 + 天赋 1 层（击破后新层随发）")
        assert e1.broken
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 1.0), "击破对峙目标 +1 层"
        assert "STANDOFF" not in st.modifiers and "STANDOFF_TARGET" not in e1.modifiers
        assert math.isclose(st.current_energy, 30.0 + 10.0), "强化普攻 30 + 抵近射击 10"
        hp1 = e1.current_hp
        _cast(eng, "131508")
        assert math.isclose(hp1 - e1.current_hp,
                            ATK * 2.2 * D0 * 1.0 * CE0 + 0.7 * BRK0, rel_tol=1e-9), (
            "已击破 1.0 + 天赋 1 层 0.7 倍（lv10 #1）")
        assert math.isclose(st.current_energy, 70.0)

    def test_kill_chain(self, compiled):
        """击杀链（E0）：对峙目标被消灭（任何来源——官方『均可获得』，过堂⑥）→
        +1 层 + 解除对峙 + 抵近射击回 10 能."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        st = _bh(eng)
        _standoff(eng)
        e1.current_hp = 100.0
        _cast(eng, "131508")   # 768 直伤致死 → 引擎自发 on_kill
        assert not e1.alive
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 1.0)
        assert "STANDOFF" not in st.modifiers, "随后解除【绝命对峙】"
        assert math.isclose(st.current_energy, 30.0 + 10.0)


class TestEidolons:
    def test_e1_def_pen_and_start_pocket(self):
        """E1：开战 1 层优势口袋 + 无视 16% 防御（def_pen 过堂⑭）——普攻按 1000/1840."""
        eng = _make(_compiled(eidolon=1))
        st = _bh(eng)
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 1.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["def_pen"], 0.16, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "131501")
        assert math.isclose(hp0 - e1.current_hp, ATK * 1.0 * D1 * 0.9 * CE0, rel_tol=1e-9)

    def test_e2_full_chain_and_turn_latch(self):
        """E2：对峙中获得优势口袋 → 回 1 点 + BE+30%（Ghost Load 活读随动）+ _e2_cd 闩；
        同回合第二次被闩挡（回点不发）、抵近射击无闩照发；回合开始清零.

        引擎结构序（_trigger_break：on_break emit → break_damage 结算）：E2 的 BE buff
        在击破事件中先生效 → 触发它的那一下击破本身即按 be 1.673 结算（BRK1B）；
        天赋钩挂 on_action（击破后）读新层数。游戏内同序真相待实测在案."""
        eng = _make(_compiled(eidolon=2))
        st = _bh(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 1.0), "E1 开战 1 层"
        sp0 = _standoff(eng)                       # 3 → 2
        e1.toughness = 20.0
        hp0 = e1.current_hp
        _cast(eng, "131508")                        # 破 e1：口袋 1→2 + E2 BE buff 即挂
        assert math.isclose(hp0 - e1.current_hp,
                            ATK * 2.2 * D1 * 0.9 * CE0 + BRK1B + 1.2 * BRK1B, rel_tol=1e-9), (
            "直伤（CE0）+ 引擎击破（be 1.673）+ 天赋新层 2 层 1.2 倍（E1 防御区）")
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 2.0)
        assert math.isclose(eng.state.skill_points, sp0), "E2 回 1 点（净耗 0）"
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"], BE2, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"], CR2, rel_tol=1e-9), (
            "Ghost Load 活读：0.05+0.0673")
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"], CD2, rel_tol=1e-9)
        assert math.isclose(st.resources["_e2_cd"], 1.0), "单回合闩"
        # 同回合第二循环：闩挡 E2（回点/BE 不重复）、抵近射击照发、天赋读新层 3 层 1.7 倍
        _standoff(eng, target="e2")                # 3 → 2
        e2.toughness = 20.0
        hp1 = e2.current_hp
        _cast(eng, "131508", target="e2")
        assert math.isclose(hp1 - e2.current_hp,
                            ATK * 2.2 * D1 * 0.9 * CE2 + BRK1B + 1.7 * BRK1B, rel_tol=1e-9), (
            "E2 BE buff 在挂：直伤 CE2 + 击破/天赋走 be 1.673；新层 3 层 → 1.7 倍")
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 3.0)
        assert math.isclose(eng.state.skill_points, 2.0), "同回合不重复触发（闩挡回点）"
        assert math.isclose(st.current_energy, (30 + 10) + (30 + 10)), (
            "抵近射击无闩：两次获得均回 10 能")
        eng.bus.emit("on_turn_start", {"actor": "1315"}, eng.state)
        assert math.isclose(st.resources["_e2_cd"], 0.0), "波提欧回合开始清零"

    def test_e3_ult_lv12_and_basic_lv7(self):
        """E3（含 E1）：终结技 lv12=4.32/推条 42%（+4200）；普攻 lv7=1.1、
        强化普攻 lv7=2.42（默认 lv6+1 不触钳——过堂⑱）."""
        eng = _make(_compiled(eidolon=3))
        st = _bh(eng)
        e1 = eng.state.actors["e1"]
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 1.0), "E1 开战 1 层"
        hp0, r0 = e1.current_hp, _remaining(eng, "e1")
        _ult(eng, target="e1")
        assert math.isclose(hp0 - e1.current_hp, ATK * 4.32 * D1 * 0.9 * CE0, rel_tol=1e-9), (
            "终结技 lv12 倍率 4.32（E1 防御区）")
        assert math.isclose(_remaining(eng, "e1") - r0, 4200.0), "推条 lv12=42%"
        hp1 = e1.current_hp
        _cast(eng, "131501")
        assert math.isclose(hp1 - e1.current_hp, ATK * 1.1 * D1 * 0.9 * CE0, rel_tol=1e-9), (
            "普攻 lv7=1.1")
        _standoff(eng)
        hp2 = e1.current_hp
        _cast(eng, "131508")
        assert math.isclose(hp2 - e1.current_hp, ATK * 2.42 * D1 * 0.9 * CE0, rel_tol=1e-9), (
            "强化普攻 lv7=2.42")

    def test_e6_talent_lv12_and_target_bonus(self):
        """E6（含 E1 防御区/E2 回点 BE/E3 档位/E5 天赋 lv12）：3 层强化普攻击破目标 →
        天赋 1.87 + E6 目标侧 0.748（=1.87×0.4）；E2 于溢出层照发（溢出亦触发——过堂⑮）；
        引擎结构序下同击击破即吃 E2 BE buff（be 1.673——on_break emit 先于击破结算，待实测）."""
        eng = _make(_compiled(eidolon=6))
        st = _bh(eng)
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(st, Modifier(
            modifier_id="POCKET_TRICKSHOT", name="优势口袋", modifier_type="buff",
            stacks=2, max_stack=3, stack_mode="refresh", duration=0, dispellable=False))
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 3.0), "E1 1 层+装填 2 层"
        sp0 = eng.state.skill_points
        _standoff(eng)
        e1.toughness = 20.0
        hp0 = e1.current_hp
        _cast(eng, "131508")
        assert math.isclose(hp0 - e1.current_hp,
                            ATK * 2.42 * D1 * 0.9 * CE0 + BRK1B + (1.87 + 0.748) * BRK1B,
                            rel_tol=1e-9), (
            "直伤 lv7（CE0）+ 引擎击破/天赋 lv12 1.87/E6 0.748 全走 be 1.673")
        assert math.isclose(st.modifiers["POCKET_TRICKSHOT"].stacks, 3.0), "溢出层钳顶"
        assert math.isclose(eng.state.skill_points, sp0), "溢出获得亦触发 E2 回点"
        hp1 = e1.current_hp
        _cast(eng, "131508")   # 已击破 + E2 BE buff 在挂（be 1.673、CE2）
        assert math.isclose(hp1 - e1.current_hp,
                            ATK * 2.42 * D1 * 1.0 * CE2 + (1.87 + 0.748) * BRK1B,
                            rel_tol=1e-9), "3 层：天赋 1.87 + E6 0.748（BE buff 随档）"


class TestTechnique:
    def test_first_skill_implants_weakness(self):
        """秘技：进战持 TECH_WEAKNESS_ARMED → 首次战技对目标植物理弱点 2 回合
        （与终结技同件——官方『相同的物理弱点』）+ 摘标记（首次限定）."""
        eng = _make(_compiled(pre_battle=True))
        st = _bh(eng)
        e3 = eng.state.actors["e3"]
        assert "TECH_WEAKNESS_ARMED" in st.modifiers
        _cast(eng, "131502", target="e3")
        assert "BOOTHILL_ULT_WEAKNESS" in e3.modifiers, "首次战技植弱点（过堂⑩）"
        assert "physical" in eng.pipeline.effective_weakness(e3)
        assert "TECH_WEAKNESS_ARMED" not in st.modifiers, "触发即摘 = 首次限定"
        assert "STANDOFF_TARGET" in e3.modifiers, "战技本件（对峙标记）不冲突"
