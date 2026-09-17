"""风堇全机制模板端到端对轴（记忆战舰 demo）：真模板 YAML → 编译 → 召唤/治疗/tally/雨过天晴全链 → 手算全等.

链：T1 战技（召唤小伊卡 = 风堇有效上限×50%、双段治疗"除小伊卡/小伊卡"分群、首召回能 45）
→ 开大（雨过天晴全队生命 + 忆灵自动施放乌云乌云快走开——tally×20%（lv6）直写基数区、放完清 50%）
→ 忆灵额外回合施放（非插入档，增伤随 tally 缩放）
→ 忆灵天赋累积窗（敌方伤人 → 行动后统一：自耗 4% + 治疗降血目标/额外全体各 2.8%+28）
→ 解散 → 风堇行动提前 30%。数值全按 expected 模式手算对轴
（默认档：basic 6 / skill 10 / ult 10 / 忆灵 10——数组 index = 等级-1）。

口径常数：风堇有效上限 = 1086.624×1.1 = 1195.2864（行迹 hp_pct 初始 modifier）；
假人 def 0 → 防御区 0.5、风弱点 → 抗性区 1.0、未击破 0.9；忆灵暴击 1.0/0.5 → 期望暴击区 1.5。
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

HYA_BASE_HP = 1086.624
HYA_EFF_HP = 1086.624 * 1.1          # 1195.2864（行迹生命节点 ×2）
IKA_HP = HYA_EFF_HP * 0.5            # 597.6432（140904：初始上限 = 风堇 ×50%）
DEF_RES = 0.5                        # 假人 def 0 口径（缺省防御 → def_multi 0.5）
UNBROKEN = 0.9
CRIT_EXP = 1 + 1.0 * 0.5             # 1.5（忆灵继承暴击 1.0/0.5，rulebook 封顶口径）
SKILL_ALLY_HEAL = 0.08 * HYA_EFF_HP + 160     # 255.622912（lv10 战技·除小伊卡）
SKILL_IKA_HEAL = 0.1 * HYA_EFF_HP + 200       # 319.52864（lv10 战技·小伊卡）
TALENT_HEAL = 0.02 * HYA_EFF_HP + 20          # 43.905728（忆灵天赋 lv6 #2-#5——E0 上限 lv6 勘正后，两笔同值）


def _build(*, pre_battle=None):
    b = {"build": {"team": [
        {"character_template": "1409", "level": 80},
        {"actor_id": "ally", "name": "火攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["wind"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled, *, initial_sp=10):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _cast(eng, aid):
    """手动施放风堇技能（_execute_action 不发 on_action——由调用方补发，同 _run_turn 口径）."""
    hya = eng.state.actors["1409"]
    a = next(x for x in eng.actions_by_actor["1409"] if x.action_id == aid)
    eng._execute_action(hya, a)
    eng.bus.emit("on_action", {
        "actor": "1409", "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": "1409", "actor_type": "character"}, eng.state)


def _ika(eng):
    return eng.state.actors["1409_ika"]


class TestHyacineCompile:
    def test_summon_def_and_resources_registered(self, compiled):
        sd = compiled.summon_defs["1409_ika"]
        assert sd.owner_id == "1409" and sd.inheritance == "full"
        assert math.isclose(sd.max_hp_ratio, 0.5), "140904：初始上限 = 风堇 ×50%"
        assert sd.actor.summon_flags == {"av": False}, "1140903：不上行动条"
        assert "hyacine_cumulative_heal" not in sd.resource_decls, (
            "tally 已迁出忆灵侧（曾=忆灵 custom_resources v1.2 首实例——布场重置清账偏离在案）")
        # tally 账挂风堇（官方"本场累计"跨重召保留）；资源并入全队 decl 并集（收尾交叉校验与引擎初始化同源）
        assert "hyacine_cumulative_heal" in compiled.resource_decls_by_actor["1409"]
        assert "_ika_first_summon" in compiled.resource_decls_by_actor["1409"]
        acts = {a.action_id for a in compiled.actions_by_actor["1409"]}
        assert {"140901", "140902", "140903"} <= acts
        ult = next(a for a in compiled.actions_by_actor["1409"] if a.action_id == "140903")
        assert ult.energy_cost == 140 and ult.apply_modifiers[0]["modifier_id"] == "AFTER_RAIN"


class TestSummonAndSkill:
    def test_ika_spawn_half_effective_hp_and_av_frozen(self, compiled):
        eng = _make(compiled)
        starts = []
        eng.bus.subscribe("on_turn_start", lambda et, p, ctx: starts.append(p["actor"]))
        rec = eng.step()                       # 风堇 T1（spd 124 最快——战技召唤）
        assert rec["actor_id"] == "1409" and rec["kind"] == "normal"
        ika = _ika(eng)
        assert ika.alive
        assert math.isclose(ika.actor.stats.hp, IKA_HP), (
            f"小伊卡上限 = 风堇有效上限 {HYA_EFF_HP:.4f} ×50%：{ika.actor.stats.hp}")
        assert math.isclose(ika.current_hp, IKA_HP)
        assert math.isclose(ika.actor.stats.atk, 388.08), "其余字段 full 继承忆师面板"
        assert math.isclose(ika.actor.stats.crit_rate, 1.0)
        assert eng.scheduler.handle_of("1409_ika") in eng.scheduler._frozen, (
            "av:false 布场即冻结（1140903：只靠额外回合行动）")
        assert math.isclose(eng.state.actors["1409"].current_energy, 75.0), (
            "T1 战技回能 30 + 首召 15+30 = 75")
        for _ in range(6):                     # 继续推进：正常条永不弹出小伊卡
            eng.step()
        assert "1409_ika" not in starts, "av:false（1140903）永不上行动条"

    def test_skill_heals_split_targets_and_tally(self, compiled):
        eng = _make(compiled)
        _cast(eng, "140902")                      # T1：召唤（全体满血，治疗多为 0）
        ika = _ika(eng)
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        hya.current_hp = 500.0
        ally.current_hp = 100.0
        ika.current_hp = 100.0                    # 留出治疗空间（×1.25 后 499.41 < 597.64 免封顶）
        # 三目标治疗前 HP 均 ≤50% 有效上限（597.64/1500/298.82）→ 阴云莞尔 ×1.25 全吃
        ally_heal = SKILL_ALLY_HEAL * 1.25
        ika_heal = SKILL_IKA_HEAL * 1.25
        tally0 = hya.resources["hyacine_cumulative_heal"]
        sp0, e0 = eng.state.skill_points, hya.current_energy
        _cast(eng, "140902")                      # T2：双段治疗对轴
        assert math.isclose(hya.current_hp, 500.0 + ally_heal), "除小伊卡口径 8%+160（≤50% 阴云莞尔 ×1.25）"
        assert math.isclose(ally.current_hp, 100.0 + ally_heal)
        assert math.isclose(ika.current_hp, 100.0 + ika_heal), "小伊卡口径 10%+200（×1.25）"
        assert math.isclose(
            hya.resources["hyacine_cumulative_heal"] - tally0,
            ally_heal * 2 + ika_heal), "tally = 风堇+小伊卡实际治疗量逐笔记账（账挂风堇）"
        assert eng.state.skill_points == sp0 - 1, "战技点 -1（米游社标签）"
        assert math.isclose(hya.current_energy, e0 + 30.0), "战技回能 30（米游社标签）"
        # 140904：3 次治疗实例 → 3 层（叠层计数 + 烘焙值双件；按实例触发口径，见模板注）
        stacks = ika.modifiers["IKA_HEAL_STACKS"]
        boost = ika.modifiers["IKA_DMG_BOOST"]
        assert stacks.stacks == 3 and math.isclose(boost.stat_effects["all_dmg"], 0.8 * 3)


class TestUltimateAndRainclouds:
    def _ult_with_tally(self, eng):
        """T1 战技召唤 → 满能开大：返回 (tally 治疗事件累计, 开大前伤害)."""
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        _cast(eng, "140902")
        hya = eng.state.actors["1409"]
        hya.current_energy = 140.0
        dmg0 = eng.state.total_damage
        _cast(eng, "140903")
        return gains, dmg0

    def test_after_rain_team_max_hp_and_tick(self, compiled):
        eng = _make(compiled)
        self._ult_with_tally(eng)
        hya = eng.state.actors["1409"]
        mod = hya.modifiers["AFTER_RAIN"]
        assert mod.duration == 3 and mod.tick_anchor == "owner_turn_start"
        # 雨过天晴 lv10：我方全体生命上限 +30%（白值口径）+600——挂风堇辐射全队（含小伊卡）
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"],
                            HYA_BASE_HP * (1 + 0.1 + 0.3) + 600)
        assert math.isclose(eng.pipeline.effective_stats(_ika(eng))["hp"],
                            IKA_HP * 1.3 + 600)
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["hp"],
                            3000 * 1.3 + 600)
        # 官方原文"风堇每回合开始时持续回合数减 1"
        eng._tick_modifiers(hya, "owner_turn_start")
        assert hya.modifiers["AFTER_RAIN"].duration == 2
        eng._tick_modifiers(hya, "owner_turn_start")
        assert hya.modifiers["AFTER_RAIN"].duration == 1

    def test_rainclouds_tally_scaling_and_clear(self, compiled):
        eng = _make(compiled)
        gains, dmg0 = self._ult_with_tally(eng)
        ika = _ika(eng)
        hya = eng.state.actors["1409"]
        e1 = eng.state.actors["e1"]
        assert math.isclose(e1.toughness, 9999.0 - 10.0), (
            "1140901 忆灵技削韧 10（米游社在案——hook toughness_dmg 回填，风弱点匹配）")
        tally_pre = sum(g["amount"] for g in gains)   # 战技+终结技全部实际治疗逐笔记账
        # 自动施放（雨过天晴·插入档）：伤害 = tally×20%（lv6 #1）× 全乘区（3 层增伤 2.4）
        auto_dmg = eng.state.total_damage - dmg0
        expected_auto = tally_pre * 0.20 * CRIT_EXP * DEF_RES * UNBROKEN * (1 + 0.8 * 3)
        assert math.isclose(auto_dmg, expected_auto, rel_tol=1e-6), (
            f"乌云乌云快走开 = tally {tally_pre:.2f}×20%×乘区：手算 {expected_auto:.2f} vs {auto_dmg:.2f}")
        assert math.isclose(hya.resources["hyacine_cumulative_heal"], tally_pre * 0.5), (
            "施放后清空 tally 的 50%（忆灵侧 set_resource 跨 actor 写风堇账）")
        # 额外回合施放（非插入档）：tally 减半后再缩放，本动增伤仍在（回合末才走字）
        dmg1 = eng.state.total_damage
        rec = eng.step()
        assert rec["actor_id"] == "1409_ika" and rec["kind"] == "normal_extra", (
            "1140903：雨过天晴进入档授 1 个额外回合")
        extra_dmg = eng.state.total_damage - dmg1
        expected_extra = tally_pre * 0.5 * 0.20 * CRIT_EXP * DEF_RES * UNBROKEN * (1 + 0.8 * 3)
        assert math.isclose(extra_dmg, expected_extra, rel_tol=1e-6)
        assert math.isclose(hya.resources["hyacine_cumulative_heal"], tally_pre * 0.25)
        assert math.isclose(e1.toughness, 9999.0 - 20.0), "额外回合档再削 10（每次施放各削）"

    def test_tally_survives_ika_dismiss_and_resummon(self, compiled):
        """tally 跨重召保留（官方"本场累计"——账挂风堇，忆灵离场布场重置不清账）."""
        eng = _make(compiled)
        gains, _ = self._ult_with_tally(eng)          # 战技+终结技治疗 → tally 有账 + 自动施放清 50%
        hya = eng.state.actors["1409"]
        tally_hold = hya.resources["hyacine_cumulative_heal"]
        assert tally_hold > 0.0
        assert eng.dismiss_summon_actor("1409_ika") is True
        assert math.isclose(hya.resources["hyacine_cumulative_heal"], tally_hold), (
            "小伊卡离场 tally 不随布场重置（迁入忆师前的偏离已收）")
        _cast(eng, "140902")                          # 重召：tally 续账不归零
        assert "1409_ika" in eng.state.actors
        assert hya.resources["hyacine_cumulative_heal"] >= tally_hold


class TestMemospriteTalent:
    def test_accumulated_heal_and_self_drain(self, compiled):
        eng = _make(compiled)
        _cast(eng, "140902")
        ika = _ika(eng)
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        # 敌方攻击注入（inline 敌人无行动表——手动给一刀，thanatoplum 同款直调）
        eng.actions_by_actor["e1"] = [Action(
            action_id="e_slash", name="挥砍", action_type="basic", target_type="single",
            damage_type="physical", scaling=[{"atk": 0.5}])]
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        ika.current_hp = 300.0
        ally.current_hp = 2000.0
        e1 = eng.state.actors["e1"]
        enemy_hp0 = e1.current_hp
        hya_hp0, ika_hp0, ally_hp0 = hya.current_hp, ika.current_hp, ally.current_hp
        tally0 = hya.resources["hyacine_cumulative_heal"]
        eng._enemy_turn(e1)
        hit = next(d["amount"] for d in drops if d["reason"] == "hit" and d["target"] == "1409")
        drain = IKA_HP * 0.04                        # 自耗 4%（lv10 #1；无雨过天晴，上限 597.6432）
        # 风堇承伤 → 行动后统一结算：降血目标 2.8%+28 + 额外全体 2.8%+28（两笔都中风堇）
        assert math.isclose(hya.current_hp, hya_hp0 - hit + TALENT_HEAL * 2), (
            "降血目标笔 + 全体笔")
        assert math.isclose(ika.current_hp, ika_hp0 - drain + TALENT_HEAL), (
            f"自耗 {drain:.4f} 后吃全体笔（风堇侧 2.8%+28）")
        assert math.isclose(ally.current_hp, ally_hp0 + TALENT_HEAL), "未降血队友只吃全体笔"
        assert e1.current_hp == enemy_hp0, "敌方不入治疗聚合（actor_type_of 闸）"
        # tally 逐笔记账：三笔实际治疗全入（源 = 风堇/小伊卡集合内；账挂风堇）
        healed = sum(g["amount"] for g in gains)
        assert math.isclose(hya.resources["hyacine_cumulative_heal"] - tally0, healed)
        assert healed > 0

    def test_drain_only_on_ally_decrease(self, compiled):
        """敌方掉血不触发自耗/治疗（忆灵技打敌方全程在发 on_hp_decrease——无闸即误触）."""
        eng = _make(compiled)
        _cast(eng, "140902")
        ika = _ika(eng)
        ika_hp0 = ika.current_hp
        # 忆灵技直接打（trigger_action 插入档——on_hp_decrease 只落在敌方）
        rain = next(a for a in eng.actions_by_actor["1409_ika"] if a.action_id == "1140901")
        eng.trigger_action(ika, rain)
        assert math.isclose(ika.current_hp, ika_hp0), "敌方 HP 降低不触发天赋自耗"


class TestDismissAndTechnique:
    def test_dismiss_advances_hyacine_and_resummon_energy(self, compiled):
        eng = _make(compiled)
        _cast(eng, "140902")
        hya = eng.state.actors["1409"]
        assert math.isclose(hya.current_energy, 75.0), "首召 15+30（每场一次标记已消费）"
        h = eng.scheduler.handle_of("1409")
        rem0 = eng.scheduler._remaining[h]
        assert eng.dismiss_summon_actor("1409_ika") is True
        rem1 = eng.scheduler._remaining[h]
        assert math.isclose(rem0 - rem1, 3000.0), "1140906：消失时风堇行动提前 30%（距离制 10000×30%）"
        e0 = hya.current_energy
        _cast(eng, "140902")                          # 重新召唤：非首召
        assert math.isclose(hya.current_energy, e0 + 30.0 + 15.0), "非首召只回 15"

    def test_technique_prebattle(self):
        build = _build(pre_battle=[{"actor_id": "1409", "technique": "140907"}])
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        eng.setup()                                    # on_battle_start 在此发射——先订阅再 setup
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        # 全体治疗 30%+600（施放者有效上限基数 0.3×1195.2864+600=958.59）：开局满血
        # 口径（B-TR① 引擎补口——hp% 初始件角色旧布场残血病已修）→ 双目标实回 0、
        # 拟回全转 excess（958.58592 双目标同值即证施放者比例）；队友满血同 0
        assert math.isclose(hya.current_hp, HYA_EFF_HP)
        healed = {g["target"]: g for g in gains}
        assert math.isclose(healed["1409"]["amount"], 0.0), "满血实回 0（开局满血口径）"
        assert math.isclose(healed["1409"]["excess"], 0.3 * HYA_EFF_HP + 600.0, rel_tol=1e-9), (
            "拟回 30%+600（施放者有效上限基数）全转 excess")
        assert math.isclose(healed["ally"]["excess"], 0.3 * HYA_EFF_HP + 600.0, rel_tol=1e-9)
        assert math.isclose(ally.current_hp, 3000.0)
        for st in (hya, ally):
            mod = st.modifiers.get("HYACINE_TECHNIQUE_HP")
            assert mod is not None and mod.duration == 2, "秘技生命上限 +20% 持续 2 回合"
        assert "1409_ika" not in eng.state.actors, "秘技不召唤"
        # 官方"本场累计"=实回口径——满血实回 0 不入 tally（拟回/excess 不计；账挂风堇
        # 后的 tally 归账行为在实回场景已由 1409 全链 e2e 覆盖，本例 excess 场景恒 0）
        assert eng.state.actors["1409"].resources["hyacine_cumulative_heal"] == 0.0


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        eng = _make(compiled)
        applied = []
        eng.bus.subscribe("after_apply_modifier", lambda et, p, ctx: applied.append(p))
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert state.actors["1409_ika"].alive
        assert any("飞入晨昏的我们" in l for l in log), "政策窗口自动开大"
        assert any(p["modifier_id"] == "AFTER_RAIN" for p in applied), "雨过天晴已施加"
        assert sum(1 for l in log if "插入发动 乌云乌云快走开" in l) >= 1, "雨过天晴自动施放（插入档）"
        # 额外回合施放（非插入档）：裸"使用"行 = _summon_turn 日志（插入档另有"插入发动"前缀行）
        solo = [l for l in log if "小伊卡 使用 乌云乌云快走开" in l]
        assert len(solo) >= 1, "1140903 额外回合档施放"
        assert state.actors["1409"].resources["hyacine_cumulative_heal"] >= 0.0


class TestStormCalm:
    """1409103 大行迹「暴风停歇」：spd>200 门控 + 超速度档治疗量（条件光环重估通道对轴）."""

    def test_gate_tier_and_reclaim(self, compiled):
        eng = _make(compiled)
        hya = eng.state.actors["1409"]
        assert "HYACINE_STORM_CALM" in hya.modifiers, "进战即挂（门控非挂摘）"
        # 124 < 200：不生效——生命仍 ×1.1（行迹节点），heal_bonus 0
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"], HYA_EFF_HP)
        assert math.isclose(eng.pipeline.effective_stats(hya)["heal_bonus"], 0.0)
        # +100 → 224 > 200：激活——hp_pct +0.2 → ×1.3；heal_bonus = min(24,200)×1% = 0.24
        eng._apply_modifier(hya, Modifier(
            modifier_id="SPD_TEST", name="测速", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0}))
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"], HYA_BASE_HP * 1.3)
        assert math.isclose(eng.pipeline.effective_stats(hya)["heal_bonus"], 0.24)
        # 再 +100 → 324：档 = min(124,200)×1% = 1.24（stat_exprs 现场变档）
        eng._apply_modifier(hya, Modifier(
            modifier_id="SPD_TEST2", name="测速二", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0}))
        assert math.isclose(eng.pipeline.effective_stats(hya)["heal_bonus"], 1.24)
        # 摘回 124：失效回收=数值不计，件仍在挂载
        eng._remove_modifier(hya, "SPD_TEST")
        eng._remove_modifier(hya, "SPD_TEST2")
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"], HYA_EFF_HP)
        assert math.isclose(eng.pipeline.effective_stats(hya)["heal_bonus"], 0.0)
        assert "HYACINE_STORM_CALM" in hya.modifiers

    def test_ika_side_reads_summoner_spd(self, compiled):
        eng = _make(compiled)
        hya = eng.state.actors["1409"]
        eng._apply_modifier(hya, Modifier(
            modifier_id="SPD_TEST", name="测速", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0}))   # 224 > 200
        _cast(eng, "140902")
        ika = _ika(eng)
        assert "HYACINE_STORM_CALM_IKA" in ika.modifiers, "小伊卡侧件随召唤挂上"
        assert math.isclose(eng.pipeline.effective_stats(ika)["heal_bonus"], 0.24), (
            "忆灵侧按忆师速度计档（stat_of($self.summoner_id, 'spd')）")
        eng._remove_modifier(hya, "SPD_TEST")
        assert math.isclose(eng.pipeline.effective_stats(ika)["heal_bonus"], 0.0), (
            "忆师跌下 200 → 忆灵侧同步关（live 重估）")


class TestGloomyGrin:
    """1409101 大行迹「阴云莞尔」治疗量段：受疗者当前 HP ≤50% 有效上限时治疗量 +25%
    （hit_condition 治疗命中域首实例——$event.target_hp_ratio 治疗前现场判定，面板不污染）."""

    def test_modifiers_hung_and_panel_clean(self, compiled):
        eng = _make(compiled)
        hya = eng.state.actors["1409"]
        assert "HYACINE_GLOOMY_GRIN" in hya.modifiers, "风堇侧件进战即挂"
        _cast(eng, "140902")
        ika = _ika(eng)
        assert "HYACINE_GLOOMY_GRIN_IKA" in ika.modifiers, "小伊卡侧件随召挂上（scoped 不辐射，双件各挂）"
        assert math.isclose(eng.pipeline.effective_stats(hya)["heal_bonus"], 0.0)
        assert math.isclose(eng.pipeline.effective_stats(ika)["heal_bonus"], 0.0), (
            "hit_condition 件一律不进面板（两域求值语义）")

    def test_boundary_and_ika_side(self, compiled):
        eng = _make(compiled)
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        _cast(eng, "140902")
        ika = _ika(eng)
        ally_max = eng.pipeline.effective_stats(ally)["hp"]     # 3000
        base = 0.08 * HYA_EFF_HP                                # hp_scaling 段（不吃加成前）
        # 贴线 = 0.5 按 ≤ 成立（官方 equal to or less than）：×1.25
        ally.current_hp = ally_max * 0.5
        r = eng.pipeline.heal(hya, ally, 0.0, hp_scaling=0.08)
        assert math.isclose(float(r.node["actualAmount"]), base * 1.25)
        # 刚过线 0.5+ε：不加成
        ally.current_hp = ally_max * 0.5 + 1
        r = eng.pipeline.heal(hya, ally, 0.0, hp_scaling=0.08)
        assert math.isclose(float(r.node["actualAmount"]), base)
        # 小伊卡侧同判定（官方"风堇和小伊卡的治疗量提高"——双件各挂）
        ally.current_hp = ally_max * 0.4
        ika_base = 0.05 * IKA_HP
        r = eng.pipeline.heal(ika, ally, 0.0, hp_scaling=0.05)
        assert math.isclose(float(r.node["actualAmount"]), ika_base * 1.25)

    def test_skill_heal_split_by_target_hp(self, compiled):
        """e2e：同一次战技双段治疗按受疗者 HP 分档——≤50% 的 ally ×1.25、>50% 的风堇原价."""
        eng = _make(compiled)
        _cast(eng, "140902")                      # T1 召唤
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        ika = _ika(eng)
        hya_max = eng.pipeline.effective_stats(hya)["hp"]
        ally_max = eng.pipeline.effective_stats(ally)["hp"]
        hya.current_hp = hya_max * 0.75           # >50%：原价（留足缺口免封顶）
        ally.current_hp = ally_max * 0.4          # ≤50%：×1.25
        ika.current_hp = eng.pipeline.effective_stats(ika)["hp"]   # 满血：治疗 0 不入账
        _cast(eng, "140902")
        assert math.isclose(hya.current_hp, hya_max * 0.75 + SKILL_ALLY_HEAL)
        assert math.isclose(ally.current_hp, ally_max * 0.4 + SKILL_ALLY_HEAL * 1.25)


class TestStormyCaress:
    """1409102 大行迹「雷雨轻柔」净化段：施放战技/终结技解除我方全体 1 个负面
    （remove_modifier filter+max_count 双通道——战技 on_action / 终结技 on_ultimate，B37 口径）."""

    def _apply_debuffs(self, eng):
        hya, ally = eng.state.actors["1409"], eng.state.actors["ally"]
        eng._apply_modifier(hya, Modifier(
            modifier_id="DEB_A", name="旧伤", modifier_type="debuff", duration=2))
        eng._apply_modifier(hya, Modifier(
            modifier_id="DEB_B", name="新咒", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="DEB_C", name="咒", modifier_type="debuff", duration=2))
        eng._apply_modifier(ally, Modifier(
            modifier_id="DEB_X", name="印记", modifier_type="debuff", duration=0, dispellable=False))

    def test_skill_purifies_one_per_ally_lifo(self, compiled):
        eng = _make(compiled)
        self._apply_debuffs(eng)
        _cast(eng, "140902")
        hya, ally = eng.state.actors["1409"], eng.state.actors["ally"]
        assert "DEB_B" not in hya.modifiers and "DEB_A" in hya.modifiers, (
            "逐目标只摘 1 个、LIFO 最新先摘")
        assert "DEB_C" not in ally.modifiers and "DEB_X" in ally.modifiers, (
            "队友同摘 1 个；不可驱散不占名额")

    def test_ult_purifies(self, compiled):
        eng = _make(compiled)
        self._apply_debuffs(eng)
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        hya.current_energy = 140.0
        ult = next(a for a in eng.actions_by_actor["1409"] if a.action_id == "140903")
        eng._fire_ultimate(hya, ult)          # 真实开大路径：on_action/on_ultimate 同发（B37 方案 A）
        assert "DEB_B" not in hya.modifiers and "DEB_A" in hya.modifiers
        assert "DEB_C" not in ally.modifiers and "DEB_X" in ally.modifiers


def _build_eidolon(n: int):
    """星魂档 build（member.eidolon: N → 模板 eidolons E1..EN 生效）."""
    b = _build()
    b["build"]["team"][0]["eidolon"] = n
    return b


def _compile_eidolon(n: int):
    return compile_encounter(_build_eidolon(n), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


class TestHyacineEidolons:
    """风堇 E1-E6 星魂（member.eidolon 激活——数值/机制照 ranks_detail 官方文本）."""

    def test_e3_e5_skill_level_overrides(self):
        c3 = _compile_eidolon(3)
        lv = next(a for a in c3.build_team if a.actor_id == "1409").skill_levels
        assert lv["ultimate"] == 12 and lv["basic"] == 7, "E3：终结技+2、普攻+1"
        c5 = _compile_eidolon(5)
        lv = next(a for a in c5.build_team if a.actor_id == "1409").skill_levels
        assert lv["skill"] == 12 and lv["talent"] == 12, "E5：战技+2、天赋+2"

    def test_e3_e5_hook_segments_follow_level(self):
        """param() 随档实证：E3 ult+2 → 雨过天晴 hp_pct 取 lv12=0.33（action apply_modifiers）；
        E5 skill+2 → 战技治疗 #1 取 lv12=0.088、天赋增伤 #3 取 lv12=0.88（编译期替换产物直读）."""
        c3 = _compile_eidolon(3)
        act = next(a for a in c3.actions_by_actor["1409"] if a.action_id == "140903")
        assert math.isclose(act.apply_modifiers[0]["stat_effects"]["hp_pct"], 0.33), (
            "雨过天晴生命档随 ult 等级跳档（旧烘焙扁平 0.3）")
        c5 = _compile_eidolon(5)
        ratios = [eff.get("ratio") for h in c5.hooks for eff in h.effects
                  if eff.get("effect_type") == "heal"]
        assert 0.088 in ratios, f"战技双段治疗随档 lv12=0.088：{ratios}"
        boost = [eff["modifier"]["stat_effects"]["all_dmg"] for h in c5.hooks
                 for eff in h.effects
                 if eff.get("effect_type") == "apply_modifier"
                 and (eff.get("modifier") or {}).get("modifier_id") == "IKA_DMG_BOOST"]
        assert boost and boost[0].startswith("0.88 *"), f"疗愈晨曦增伤/层随档 lv12=0.88：{boost}"

    def test_e1_after_rain_hp_and_attack_heal(self):
        eng = _make(_compile_eidolon(1))
        hya = eng.state.actors["1409"]
        ally = eng.state.actors["ally"]
        hya.current_energy = 140.0
        _cast(eng, "140903")
        mod = hya.modifiers["E1_AFTER_RAIN_HP"]
        assert mod.duration == 3 and mod.tick_anchor == "owner_turn_start"
        assert mod.effect_scope == "team" and math.isclose(mod.stat_effects["hp_pct"], 0.5)
        hya_eff = eng.pipeline.effective_stats(hya)["hp"]
        assert math.isclose(hya_eff, HYA_BASE_HP * (1 + 0.1 + 0.3 + 0.5) + 600), (
            "雨过天晴 30% + E1 额外 50%（白值口径叠算）+600")
        # ② 队友施放攻击 → 立即回复 = 风堇有效上限 ×8%（每次行动限 1 次）；
        # 受疗前 100 ≤ 50%×6000（雨过天晴+E1 后 ally 有效上限）→ 阴云莞尔 ×1.25
        ally.current_hp = 100.0
        atk = next(a for a in eng.actions_by_actor["ally"] if a.action_id == "ally_basic")
        eng._execute_action(ally, atk)
        assert math.isclose(ally.current_hp, 100.0 + 0.08 * hya_eff * 1.25), (
            "E1②：施放攻击后立即回复 8%×风堇生命上限（≤50% 阴云莞尔 ×1.25）")
        ally.current_hp = 100.0
        eng._remove_modifier(hya, "AFTER_RAIN")
        eng._execute_action(ally, atk)
        assert math.isclose(ally.current_hp, 100.0), "雨过天晴解除 → E1② 不再回复"

    def test_e2_spd_up_on_ally_hp_decrease(self):
        eng = _make(_compile_eidolon(2))
        ally = eng.state.actors["ally"]
        eng.bus.emit("on_hp_decrease", {
            "amount": 100.0, "source": "e1", "reason": "hit", "target": "ally"}, eng.state)
        mod = ally.modifiers["E2_COURTYARD_SPD"]
        assert mod.duration == 2 and math.isclose(mod.stat_effects["spd_pct"], 0.3)
        spd0 = eng.pipeline.effective_stats(ally)["spd"]
        assert math.isclose(spd0, 80.0 * 1.3), "E2：我方目标掉血 → 速度+30%（2 回合）"
        eng.bus.emit("on_hp_decrease", {
            "amount": 50.0, "source": "ally", "reason": "hit", "target": "e1"}, eng.state)
        assert math.isclose(eng.pipeline.effective_stats(ally)["spd"], spd0), (
            "敌方掉血不触发（actor_type_of 闸）")

    def test_e4_storm_calm_crit_dmg(self):
        eng = _make(_compile_eidolon(4))
        hya = eng.state.actors["1409"]
        # 124 < 200：E4 条件件在挂载但不生效
        assert "HYACINE_STORM_CALM_E4" in hya.modifiers
        assert math.isclose(eng.pipeline.effective_stats(hya)["crit_dmg"], 0.5)
        eng._apply_modifier(hya, Modifier(
            modifier_id="SPD_TEST", name="测速", modifier_type="buff", duration=0,
            stat_effects={"spd": 100.0}))   # 224 > 200
        assert math.isclose(eng.pipeline.effective_stats(hya)["crit_dmg"], 0.5 + 0.48), (
            "E4：超 200 每点速度暴伤 +2%（24×2%=0.48，至多计入 200 点同暴风停歇口径）")
        _cast(eng, "140902")
        ika = _ika(eng)
        assert "HYACINE_STORM_CALM_E4_IKA" in ika.modifiers
        assert math.isclose(eng.pipeline.effective_stats(ika)["crit_dmg"], 0.5 + 0.48), (
            "小伊卡侧按忆师速度计档（stat_of($self.summoner_id, 'spd')）")

    def test_e6_tally_clear_12pct_and_res_pen(self):
        eng = _make(_compile_eidolon(6))
        hya = eng.state.actors["1409"]
        gains = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: gains.append(p))
        _cast(eng, "140902")
        # ② 小伊卡在场 → 我方全体抗穿 +20%（挂风堇 team 光环）
        assert "E6_SKY_RES_PEN" in hya.modifiers
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"], 0.2)
        hya.current_energy = 140.0
        _cast(eng, "140903")                       # 雨过天晴自动施放 → 结算清 tally
        tally_pre = sum(g["amount"] for g in gains)
        assert math.isclose(hya.resources["hyacine_cumulative_heal"], tally_pre * 0.88,
                            rel_tol=1e-6), (
            "E6①：清 tally 改为 12%（基础 hook 清 50% 后重设 ×1.76 → 余 88%）")
        assert eng.dismiss_summon_actor("1409_ika") is True
        assert "E6_SKY_RES_PEN" not in hya.modifiers, "小伊卡离场 → 抗穿光环摘除"
        assert math.isclose(eng.pipeline.effective_stats(eng.state.actors["ally"])["res_pen"], 0.0)
