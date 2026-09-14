"""银狼LV.999 1506 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
Hidden MMR/Punchline 双资源/Godmode 状态机/强化普攻/盲盒概率闩/欢愉技/秘技/星魂全链 → 手算全等.

口径常数：银狼LV.999 atk 388.08、crit_rate 0.05、crit_dmg 0.5、spd 110、max_energy 0
（Hidden MMR 特殊充能——ult_cost_resource 门槛 60）。
实取档（默认 basic lv6 / 其余 lv10；欢愉技 level_key=elation_skill 缺省回退 ultimate=10）：
战技 lv10=1.6（Punchline 5）；终结技 lv10：盲盒倍率 0.9/衰减 0.2；天赋 lv10：追加 0.4、
CR 0.004/点、CD 0.008/点、3 次退出；强化普攻 lv6：弹射 2.4/Final Hit 1.0/增伤档 0.15×
min(round(MMR/60),2)；欢愉技 150620 全档 +15 MMR；150621 lv10=0.9×6 段。
假人 def 1000 → 防御区 (800+200)/(1000+1000)=0.5；弱点 imaginary → 抗性区 1.0；
未击破 0.9；期望暴击区 = 1+实时CR×0.5（MMR 转模实时面板——断言按各时点 MMR 实算）。
欢愉伤全部普通伤近似（21_elation 未实装——模板在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 388.08
ZONE = 0.5 * 1.0 * 0.9          # 防御区 × 抗性区 × 未击破
CRIT0 = 1 + 0.05 * 0.5          # 期望暴击区（MMR=0）= 1.025


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


def _hang_banger(eng):
    """好活当赏装填（官方获得途径未明示——模板保守读挂载件的等价物）."""
    eng._apply_modifier(_sw(eng), Modifier(
        modifier_id="CERTIFIED_BANGER", name="好活当赏", modifier_type="buff",
        duration=0, dispellable=False))


class TestSilverWolfCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1506"]}
        assert acts == {"150601", "150602", "150603", "150608",
                        "150610", "150612", "150618", "150620", "150621"}
        decls = compiled.resource_decls_by_actor["1506"]
        assert decls["hidden_mmr"]["max"] == 300
        assert decls["_lootbox_p"]["current"] == 1.0
        ult = next(a for a in compiled.actions_by_actor["1506"] if a.action_id == "150603")
        assert ult.ult_cost_resource == "hidden_mmr" and ult.ult_cost_amount == 60
        # 欢愉技独立档轨（勘正⑨——E3/E5 欢愉技+1 不与战技+2 串档）
        lk = {a.action_id: a.level_key for a in compiled.actions_by_actor["1506"]}
        assert lk["150620"] == lk["150621"] == "elation_skill"


class TestSkillAndPunchline:
    def test_skill_dmg_and_resource_link(self, compiled):
        """战技 lv10=1.6 全体：每敌 388.08×1.6×0.46125=286.40304（MMR=0 → 暴击区 1.025）；
        Punchline +5 → 天赋等量 MMR +5；SP 3→2."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150602")
        assert math.isclose(hp1 - e1.current_hp, 286.40304, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 286.40304, rel_tol=1e-9)
        st = _sw(eng)
        assert math.isclose(st.resources["punchline"], 5.0)
        assert math.isclose(st.resources["hidden_mmr"], 5.0), "天赋等量联动"
        assert math.isclose(eng.state.skill_points, 2.0)

    def test_basic_toughness_and_crit_convert(self, compiled):
        """普攻 lv6=1.0：MMR=5 → CR=0.05+5×0.004=0.07 → 暴击区 1.035；
        伤=388.08×0.5×0.9×1.035=180.74826；削韧 10（fandom 补写）."""
        eng = _make(compiled)
        _cast(eng, "1506", "150602")   # MMR → 5
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150601")
        assert math.isclose(hp - e1.current_hp, 180.74826, rel_tol=1e-9)
        assert math.isclose(e1.toughness, 80.0), "战技 10 + 普攻 10 各削韧"
        st = _sw(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_rate"],
                            0.07, rel_tol=1e-9), "CR 转模 stat_exprs 现场追踪（勘正③）"

    def test_crit_convert_cap_and_overflow(self, compiled):
        """MMR 灌满 300：CR=0.05+min(1.2,0.95)=1.0 封顶；CD=0.5+(300-237.5)×0.008=1.0."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 300.0)
        assert math.isclose(st.resources["hidden_mmr"], 300.0), "max 300 clamp"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 1.0, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], 1.0, rel_tol=1e-9)


class TestElationSkills:
    def test_pro_gamer_move_and_trace_thresholds(self, compiled):
        """150620：MMR +15；1506102 两档——punchline 45（≥40）→ 再 +20+20；合计 +55."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "punchline", 45.0)   # 天赋联动 MMR +45
        assert math.isclose(st.resources["hidden_mmr"], 45.0)
        _cast(eng, "1506", "150620")
        assert math.isclose(st.resources["hidden_mmr"], 45 + 15 + 20 + 20), (
            "欢愉技 +15 + 行迹两档 +40")

    def test_honkai_dmg_demo_and_chance_reset(self, compiled):
        """150621 lv10=0.9×6 段（expected 按序取首=e1 独吃）：每段 388.08×0.9×0.46125
        =161.10171，6 段 966.61026；盲盒概率闩重置 1.0."""
        eng = _make(compiled)
        st = _sw(eng)
        st.resources["_lootbox_p"] = 0.2
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150621")
        assert math.isclose(hp1 - e1.current_hp, 161.10171 * 6, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0), "随机单体 6 段全落首敌（expected）"
        assert math.isclose(st.resources["_lootbox_p"], 1.0), "概率闩重置"


class TestUltimateGodmode:
    def test_enter_state_chain(self, compiled):
        """进状态：MMR 60 扣空 + 1506103 +20 → 20；_godmode 闩/免疫件/好活当赏挂；
        行动提前 100%（remaining → 0）；普攻/战技与强化普攻/150621 可用性互斥翻转."""
        eng = _make(compiled)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        assert math.isclose(st.resources["hidden_mmr"], 20.0), "60 扣空 + 行迹 +20"
        assert math.isclose(st.resources["_godmode"], 1.0)
        assert "GODMODE_PLAYER" in st.modifiers
        assert "CERTIFIED_BANGER" in st.modifiers
        assert math.isclose(_remaining(eng, "1506"), 0.0), "行动提前 100%"
        acts = {a.action_id: a for a in eng.actions_by_actor["1506"]}
        assert not eng._available_if_ok(st, acts["150601"])
        assert not eng._available_if_ok(st, acts["150602"])
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
        """MMR=20：增伤档 0.15×min(round(1/3),2)=0（类型桶动态追踪）；CR=0.05+20×0.004
        =0.13 → 暴击区 1.065。弹射（action 层 lv6=2.4）=388.08×2.4×0.45×1.065
        =446.369616；Final Hit（全体各，lv6 #4=1.0）=388.08×0.45×1.065=185.98734."""
        eng = self._enter_godmode(compiled, 20.0)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150608")
        assert math.isclose(hp1 - e1.current_hp, 446.369616 + 185.98734, rel_tol=1e-9), (
            "e1 吃弹射 + Final Hit")
        assert math.isclose(hp2 - e2.current_hp, 185.98734, rel_tol=1e-9), "e2 仅 Final Hit"
        assert math.isclose(_sw(eng).resources["_godmode_uses"], 1.0)
        boost = eng.pipeline.effective_stats(_sw(eng))["dmg_bonus"].get("basic_dmg_boost", 0.0)
        assert math.isclose(boost, 0.0, abs_tol=1e-12)

    def test_dmg_bonus_snapshot_high_mmr(self, compiled):
        """MMR=130：档 0.15×min(round(2.1667),2)=0.3；CR=0.57 → 暴击区 1.285。
        弹射=388.08×2.4×0.45×1.285×1.3=700.1506512；Final=388.08×0.45×1.285×1.3
        =291.729438（增伤区 1.3 乘在期望暴击后——各区独立；本体/Final 同吃勘正⑭）."""
        eng = self._enter_godmode(compiled, 130.0)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1506", "150608")
        assert math.isclose(hp1 - e1.current_hp,
                            700.1506512 + 291.729438, rel_tol=1e-9)
        boost = eng.pipeline.effective_stats(_sw(eng))["dmg_bonus"]["basic_dmg_boost"]
        assert math.isclose(boost, 0.3, rel_tol=1e-9)

    def test_exit_after_three_uses(self, compiled):
        """3 次用尽退出：摘 Godmode/好活当赏、清 MMR、闩归零（快照 +1 补偿口径）."""
        eng = self._enter_godmode(compiled, 20.0)
        st = _sw(eng)
        for _ in range(3):
            _cast(eng, "1506", "150608")
        assert math.isclose(st.resources["_godmode"], 0.0)
        assert math.isclose(st.resources["hidden_mmr"], 0.0)
        assert "GODMODE_PLAYER" not in st.modifiers
        assert "CERTIFIED_BANGER" not in st.modifiers
        acts = {a.action_id: a for a in eng.actions_by_actor["1506"]}
        assert eng._available_if_ok(st, acts["150601"]), "退出后普通普攻恢复可用"


class TestTalentFollowUp:
    def test_skill_follow_up_all_enemies(self, compiled):
        """好活当赏追加·战技（lv10 #3=0.4）全体：MMR=5 → CR=0.07 → 暴击区 1.035；
        每敌 388.08×0.4×0.45×1.035=72.299304."""
        eng = _make(compiled)
        _hang_banger(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        dmg = hp - e1.current_hp
        skill = 286.40304                     # 战技本体（MMR=0 时点）
        follow = 388.08 * 0.4 * ZONE * 1.035  # 追加（MMR=5 时点）
        assert math.isclose(dmg, skill + follow, rel_tol=1e-9)
        assert math.isclose(follow, 72.299304, rel_tol=1e-9)

    def test_basic_follow_up_event_target(self, compiled):
        """好活当赏追加·普攻（勘正⑥收录——pool $event.target 单体）：e1 独吃追加，
        e2 无伤。普攻 lv6=1.0（MMR=0）=179.0019；追加（MMR=0）=388.08×0.4×0.46125
        =71.60076."""
        eng = _make(compiled)
        _hang_banger(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1506", "150601", target=e1)
        assert math.isclose(hp1 - e1.current_hp, 179.0019 + 71.60076, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0)


class TestLootBox:
    def _enter_godmode(self, compiled):
        eng = _make(compiled, initial_sp=5)
        st = _sw(eng)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        st.resources["hidden_mmr"] = 0.0    # 清零 → CR 0.05 简化口径
        return eng

    def test_trigger_and_chance_decay(self, compiled):
        """消耗 SP（before>after）→ 盲盒触发：每敌 388.08×0.9×0.46125=161.10171；
        概率闩 1.0→0.2；再次消耗 p=0.2<0.5（expected 钉）不触发；SP 增加不触发（勘正⑬）."""
        eng = self._enter_godmode(compiled)
        st = _sw(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        eng.bus.emit("on_skill_point_change", {"before": 5, "after": 4, "reason": "skill"},
                     eng.state)
        assert math.isclose(hp - e1.current_hp, 161.10171, rel_tol=1e-9)
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
        """秘技 0 点 + 豆在场：on_wave_start 盲盒同基数（勘正⑫）每敌 161.10171
        + 好活当赏刷新."""
        eng = _make(_compiled(pre_battle=True))
        st = _sw(eng)
        assert "TECH_MUNCH_BEAN" in st.modifiers
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        assert math.isclose(hp - e1.current_hp, 161.10171, rel_tol=1e-9)
        assert "CERTIFIED_BANGER" in st.modifiers


class TestEidolons:
    def test_e1_zone_vuln_and_exit_purge(self):
        """E1：进状态 all_enemies 易伤 0.2（勘正⑦——vulnerability 在案）；3 次用尽退出
        同步摘除."""
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
        """E3：战技 lv12=1.76（每敌 388.08×1.76×0.46125=315.043344）；
        欢愉技+1 → 150621 lv11=0.945（每段 388.08×0.945×0.46125=169.1567955）——
        独立档轨不与战技+2 串档（勘正⑨）。eidolon=3 联动 E1：开大后结界易伤 0.2
        → 150621 段伤 ×1.2=202.9881546."""
        eng = _make(_compiled(eidolon=3))
        st = _sw(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        assert math.isclose(hp - e1.current_hp, 315.043344, rel_tol=1e-9)
        eng._gain_resource(st, "hidden_mmr", 60.0)
        _ult(eng)
        st.resources["hidden_mmr"] = 0.0
        hp = e1.current_hp
        _cast(eng, "1506", "150621")
        assert math.isclose(hp - e1.current_hp, 202.9881546 * 6, rel_tol=1e-9), (
            "E1 易伤联动（族谱 18——eidolon=N 全联动）")

    def test_e5_talent_lv12_follow_up(self):
        """E5：天赋 lv12——追加 0.44、CR 0.0044/点。战技后 MMR=5 → CR=0.072 →
        暴击区 1.036；追加每敌 388.08×0.44×0.45×1.036=79.60607424."""
        eng = _make(_compiled(eidolon=5))
        _hang_banger(eng)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150602")
        dmg = hp - e1.current_hp
        assert math.isclose(dmg - 315.043344, 79.60607424, rel_tol=1e-9), (
            "战技本体 lv12（E3 联动）+ 追加 lv12 档")

    def test_e6_res_pen_and_merrymake(self):
        """E6（全联动）：res_pen 1.0 常驻（禁限弱点保守读）→ 抗性区 1-clamp(0-1,-1,0.9)
        =2.0；all_dmg 0.5 常驻（merrymakes 承载）。普攻 lv7（E3 联动）=1.1：
        388.08×1.1×0.5×2.0×0.9×1.025×1.5=590.70627."""
        eng = _make(_compiled(eidolon=6))
        st = _sw(eng)
        assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 1.0, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp = e1.current_hp
        _cast(eng, "1506", "150601")
        assert math.isclose(hp - e1.current_hp, 590.70627, rel_tol=1e-9)
