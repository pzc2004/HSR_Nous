"""昔涟全机制模板端到端对轴（记忆战舰 demo）：真模板 YAML → 编译 → 追忆/德谬歌全链 → 手算全等.

链：进战（未来授予 + 岁月的旅人 +6 追忆烘焙 + 全队增伤 20% 光环）→ 战技（结界 2 回合
owner_turn_start 走字 + 追忆 +3）→ 我方受击 → 结界真伤（原伤害 ×24%，category:"true"
防递归闸）→ 消耗未来产点（来源=行动队友，unique_sources 计数前提）→ 首开 141503
（门槛 24 实扣 12 → 驱散自身 → 召唤德谬歌（界外三关/SPD 0/Max HP×100%+双方+33.6%/
召唤驱散全队控制/Story+1/立即额外回合）→ activate_ultimate 全队免费开大 → 涟漪态
（锁战技 + 强化普攻 141508 两段 + 双方暴击 50% + 结界转永续））→ 141514 再开
（门槛/扣量 12 → 德谬歌额外回合 + Story+1）→ Story 3 自动 Minuet + unique_sources
追加段。数值全按 expected 模式手算对轴（默认档：basic 6 / skill 10 / ult 10 / talent 10 /
忆灵 10——数组 index = 等级-1）。

口径常数：昔涟有效上限 = 1397.088×1.1 = 1536.7968（行迹 hp_pct 0.1 引擎结算）；
德谬歌 = 召唤时 ×1.0 = 1536.7968 → 双方 +33.6% 后 ×1.336 = 2053.1605248，
昔涟 1397.088×1.436 = 2006.218368；假人 def 兜底 1000 → 防御区 0.5、冰弱点 → 抗性区 1.0、
火非弱点 → 0.8、未击破 0.9；暴击 0.05/0.873（涟漪 +0.5 → 0.55——德谬歌经继承快照同值）。
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

CYRENE_HP = 1397.088 * 1.1              # 1536.7968（行迹 hp_pct 0.1）
CYRENE_HP_FULL = 1397.088 * 1.436       # 2006.218368（+德谬歌 33.6%）
DEM_HP_SUMMON = CYRENE_HP               # 1536.7968（141503 #1 max_hp_ratio 1.0 定格）
DEM_HP = DEM_HP_SUMMON * 1.336          # 2053.1605248（1141503 #1 双方 +33.6%）
DEF_RES = 0.5                           # 假人 def 兜底 1000 口径
UNBROKEN = 0.9
FIRE_RES = 0.8                          # 非弱点抗性 0.2
CRIT_OUT = 1 + 0.05 * 0.873             # 1.04365（无形态期望暴击区）
CRIT_RIP = 1 + 0.55 * 0.873             # 1.48015（涟漪 #3 +50%——双方同值）
TEAM = 1.2                              # 141504 #2 全队增伤 20%（effect_scope team）


def _build(*, pre_battle=None):
    allies = [
        {"actor_id": "ally", "name": "火攻手", "inline": True,
         "base_stats": {"atk": 2000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10},
                     {"action_id": "ally_ult", "name": "烈焰冲击", "action_type": "ultimate",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 3.0}], "energy_cost": 100}]},
    ]
    b = {"build": {"team": [{"character_template": "1415", "level": 80}] + allies,
                   "policy": {"name": "p", "action_rules": [
                       {"condition": "true", "action": "skill", "priority": 50},
                       {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        b["build"]["pre_battle"] = pre_battle
    return b


def _stage():
    return {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
         "max_toughness": 9999, "weakness": ["ice"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _stage(), template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled, *, initial_sp=10):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _cast(eng, owner, aid, *, target=None):
    """手动施放（_execute_action 不发 on_action——由调用方补发，同 _run_turn 口径）."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": target or owner,
        "actor_type": st.actor.actor_type}, eng.state)


def _cyr(eng):
    return eng.state.actors["1415"]


def _dem(eng):
    return eng.state.actors["1415_dem"]


def _ult(eng, aid="141503"):
    cyr = _cyr(eng)
    ult = next(a for a in eng.actions_by_actor["1415"] if a.action_id == aid)
    assert eng._fire_ultimate(cyr, ult) is True


class TestCyreneCompile:
    def test_summon_def_resources_and_state_registered(self, compiled):
        sd = compiled.summon_defs["1415_dem"]
        assert sd.actor.summon_flags == {
            "av": False, "enemy_targetable": False, "ally_targetable": False}, (
            "1141503：SPD 0 不上条 + 界外（双方皆不可选）")
        assert isinstance(sd.inheritance, tuple) and "spd" not in sd.inheritance
        assert math.isclose(sd.actor.stats.spd, 0.0), "1141503：速度保持为 0"
        assert math.isclose(sd.max_hp_ratio, 1.0), "141503 #1：初始生命上限 = 昔涟 ×100%"
        decl = compiled.resource_decls_by_actor["1415"]["recollection"]
        assert decl["max"] == 27.0 and decl["ult_threshold"] == 24.0 and decl["provenance"]
        assert compiled.resource_decls_by_actor["1415_dem"]["story"]["max"] == 3.0
        cfg, entry = compiled.state_configs_by_actor["1415"]
        assert cfg.state == "ripples" and entry == "141503"
        assert cfg.replaces_actions == {"basic": "141508", "ultimate": "141514"}
        assert cfg.locked_actions == ["skill"] and cfg.entry_end_turn is False
        assert math.isclose(cfg.stat_effects["crit_rate"], 0.5)
        acts = {a.action_id: a for a in compiled.actions_by_actor["1415"]}
        assert acts["141503"].ult_cost_amount == 24.0, "首开门槛 24（141504 #4）"
        assert acts["141503"].ult_consume_amount == 12.0, "实扣 12（fandom/params 双源）"
        assert acts["141514"].ult_cost_amount == 12.0, "涟漪态再开门槛 12（141504 #5）"
        assert acts["141501"].resource_gain == {"recollection": 1.0}
        assert acts["141502"].resource_gain == {"recollection": 3.0}
        assert acts["141508"].resource_gain == {"recollection": 3.0}
        assert acts["141508"].skill_point_gain == 0, "强化普攻不能恢复战技点（官方文本）"
        dacts = {a.action_id: a for a in compiled.actions_by_actor["1415_dem"]}
        assert {"1141501", "1141502"} <= set(dacts)


class TestBattleStart:
    def test_future_aura_and_baked_recollection(self, compiled):
        eng = _make(compiled)
        cyr, ally = _cyr(eng), eng.state.actors["ally"]
        assert "CYRENE_FUTURE" in ally.modifiers, "进战：队友获【未来】"
        assert "CYRENE_FUTURE" not in cyr.modifiers, "其他角色才获——昔涟自身无"
        aura = cyr.modifiers["CYRENE_TEAM_DMG"]
        assert aura.effect_scope == "team" and math.isclose(aura.stat_effects["all_dmg"], 0.2)
        assert math.isclose(cyr.resources["recollection"], 6.0), (
            "岁月的旅人 demo 烘焙档：3 记忆 → +6（1/2/3 名 → 2/3/6）")
        assert eng._resource_provenance[("1415", "recollection")] == {"1415"}, (
            "烘焙产点来源=自身——不计 Ode 队友数")


class TestFutureProduce:
    def test_consume_grants_point_with_actor_source(self, compiled):
        eng = _make(compiled)
        cyr, ally = _cyr(eng), eng.state.actors["ally"]
        r0 = cyr.resources["recollection"]
        _cast(eng, "ally", "ally_basic")
        assert "CYRENE_FUTURE" not in ally.modifiers, "持有【未来】行动时消耗"
        assert math.isclose(cyr.resources["recollection"], r0 + 1.0)
        assert eng._resource_provenance[("1415", "recollection")] == {"1415", "ally"}, (
            "消耗未来产点：来源=行动队友（1141526 多段计数前提）")
        # 昔涟行动后重授（replace 幂等）
        _cast(eng, "1415", "141501")
        assert "CYRENE_FUTURE" in ally.modifiers, "昔涟行动后：其他角色重新获【未来】"

    def test_memosprite_future_not_consumed(self, compiled):
        """1415101：忆灵持有【未来】不会被消耗（consume 限 character）."""
        eng = _make(compiled)
        cyr = _cyr(eng)
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")   # 凑 24 首开
        _ult(eng)
        dem = _dem(eng)
        eng._apply_modifier(dem, Modifier(
            modifier_id="CYRENE_FUTURE", name="未来", modifier_type="buff",
            duration=0, dispellable=False))
        r0 = cyr.resources["recollection"]
        eng.trigger_action(dem, next(a for a in eng.actions_by_actor["1415_dem"]
                                     if a.action_id == "1141501"), tag="test")
        assert "CYRENE_FUTURE" in dem.modifiers, "忆灵持有不消耗"
        assert math.isclose(cyr.resources["recollection"], r0), "忆灵行动不产点"


class TestZoneTrueDamage:
    def test_skill_zone_and_true_damage_no_recursion(self, compiled):
        eng = _make(compiled, initial_sp=5)
        cyr = _cyr(eng)
        drops = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: drops.append(p))
        r0, sp0 = cyr.resources["recollection"], eng.state.skill_points
        _cast(eng, "1415", "141502")
        zone = cyr.modifiers["CYRENE_ZONE"]
        assert zone.duration == 2 and zone.tick_anchor == "owner_turn_start"
        assert math.isclose(cyr.resources["recollection"], r0 + 3.0), "战技 +3 追忆"
        assert eng.state.skill_points == sp0 - 1
        # 队友火普攻 → 结界真伤 0.24×原伤害（火非弱点 res 0.8）
        e1 = eng.state.actors["e1"]
        hp0 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        ally_dmg = 2000 * TEAM * 1.025 * DEF_RES * FIRE_RES * UNBROKEN   # 885.6
        true_dmg = 0.24 * ally_dmg                                        # 212.544
        assert math.isclose(hp0 - e1.current_hp, ally_dmg + true_dmg, rel_tol=1e-6), (
            "受击一段 + 真伤一段（原伤害 ×24%）")
        true_hits = [p for p in drops if p.get("damage_type") == "true"]
        assert len(true_hits) == 1, "真伤自身不再触发结界（damage_type 防递归闸）"
        assert math.isclose(true_hits[0]["amount"], true_dmg, rel_tol=1e-6)
        assert true_hits[0]["source"] == "1415", "结界真伤归属昔涟"
        # 昔涟冰普攻（冰弱点 res 1.0）也触发
        hp1 = e1.current_hp
        _cast(eng, "1415", "141501")
        cyr_basic = 0.5 * CYRENE_HP * TEAM * CRIT_OUT * DEF_RES * 1.0 * UNBROKEN
        assert math.isclose(hp1 - e1.current_hp, cyr_basic * 1.24, rel_tol=1e-6)
        # 走字：昔涟回合开始 ×2 → 结界到期
        eng._tick_modifiers(cyr, "owner_turn_start")
        assert cyr.modifiers["CYRENE_ZONE"].duration == 1
        eng._tick_modifiers(cyr, "owner_turn_start")
        assert "CYRENE_ZONE" not in cyr.modifiers
        # 到期后不触发
        hp2 = e1.current_hp
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(hp2 - e1.current_hp, ally_dmg, rel_tol=1e-6), "结界到期无真伤"


class TestUltimateChain:
    def test_first_ult_full_chain_and_once_per_battle(self, compiled):
        eng = _make(compiled)
        cyr, ally, e1 = _cyr(eng), eng.state.actors["ally"], eng.state.actors["e1"]
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")   # 6+18=24 首开
        ults = []
        eng.bus.subscribe("on_ultimate", lambda et, p, ctx: ults.append(p))
        # 布场：队友控制 + 昔涟 debuff（召唤驱散全队控制 / 开大驱散自身非 buff 件）
        eng._apply_modifier(ally, Modifier(
            modifier_id="FRZ", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2))
        eng._apply_modifier(cyr, Modifier(
            modifier_id="SHRED", name="减防", modifier_type="debuff", duration=2))
        ally_hp0, e1_hp0 = ally.current_hp, e1.current_hp
        ally.current_energy = 0.0
        _ult(eng)
        # 追忆：门槛 24 激活、实扣 12（非遐蝶全扣族）
        assert math.isclose(cyr.resources["recollection"], 12.0)
        # 德谬歌布场：Max HP=召唤时昔涟有效上限×1.0 → 双方 +33.6%
        dem = _dem(eng)
        assert dem.alive
        assert math.isclose(eng.pipeline.effective_stats(dem)["hp"], DEM_HP, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(cyr)["hp"], CYRENE_HP_FULL, rel_tol=1e-9)
        # 召唤驱散全队控制 + 昔涟驱散自身非 buff 件（施放瞬间读法在案）
        assert "FRZ" not in ally.modifiers, "1141505：被召唤时驱散全队控制类"
        assert "SHRED" not in cyr.modifiers, "141504：开大驱散自身全部负面"
        # activate_ultimate：0 能队友终结技照放（不耗能量）、编入 on_ultimate 广播
        assert any(p["source"] == "ally" and p["action"] == "ally_ult" for p in ults), (
            "activate_ultimate：队友终结技作为插入行动发动")
        ally_ult_dmg = 2000 * 3.0 * TEAM * 1.025 * DEF_RES * FIRE_RES * UNBROKEN
        assert math.isclose(e1_hp0 - e1.current_hp, ally_ult_dmg, rel_tol=1e-6), (
            "首开无结界——队友大只结算自身伤害（真伤后续才挂）")
        assert math.isclose(ally.current_energy, 5.0), (
            "不扣开大成本——只有终结技自身回能 5（v1 白嫖口径 B19 在案）")
        # 涟漪态：标记 + 双方暴击 50%（德谬歌经继承快照）+ 结界转永续
        assert cyr.state_config is not None and cyr.state_config.state == "ripples"
        assert math.isclose(eng.pipeline.effective_stats(cyr)["crit_rate"], 0.55)
        assert math.isclose(eng.pipeline.effective_stats(dem)["crit_rate"], 0.55), (
            "德谬歌暴击 +50% 由忆灵侧永续件承载（继承快照=编译期面板不含形态件）")
        assert "DEM_RIPPLES_CRIT" in dem.modifiers
        assert cyr.modifiers["CYRENE_ZONE"].duration == 0, "涟漪态结界没有持续时间"
        # 德谬歌：Story+1（被召唤）+ 立即额外回合入队
        assert math.isclose(dem.resources["story"], 1.0)
        dem_h = eng.scheduler.handle_of("1415_dem")
        assert any(h == dem_h for h, _k in eng.scheduler._extra_queue), "召唤即授额外回合"
        # 界外三关：av 冻结不上条 / 敌方池剔除 / 我方池剔除
        assert dem_h in eng.scheduler._frozen, "av:false 布场即冻结"
        allies_for_enemy = [s for s in eng._allies_alive()
                            if s.actor.summon_flags.get("enemy_targetable", True)]
        assert all(s.actor.actor_id != "1415_dem" for s in allies_for_enemy), (
            "enemy_targetable:false——敌方一切目标池剔除")
        hook_allies = eng._hook_target_states("all_allies", cyr, {})
        assert all(s.actor.actor_id != "1415_dem" for s in hook_allies), (
            "ally_targetable:false——我方选择器池剔除（单体奶/盾指不到）")
        # 涟漪态再开 141514（门槛=扣量 12——首开余 12 恰可再开）
        assert eng._ult_action_of(cyr).action_id == "141514", (
            "形态替换 ult 按当前形态解析（141503 已被替换下场）")
        _ult(eng, "141514")
        assert math.isclose(cyr.resources["recollection"], 0.0), "141514 扣 12"
        assert math.isclose(dem.resources["story"], 2.0), "1141526：昔涟开大 Story +1"
        # 每场 1 次闸：涟漪永续 → 141503 永不可用（替换 + 入口拒重入双闸）
        ult503 = next(a for a in eng.actions_by_actor["1415"] if a.action_id == "141503")
        assert eng._fire_ultimate(cyr, ult503) is False, "单场战斗只能施放 1 次（结构性）"


class TestRipplesEnhancedBasic:
    def test_legality_and_two_stage_damage(self, compiled):
        eng = _make(compiled)
        cyr, e1 = _cyr(eng), eng.state.actors["e1"]
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")
        _ult(eng)
        # 合法性：basic→141508（原型 141501 被替换下场）、skill 锁、ult→141514
        legal = eng._legal_with_state(
            cyr, legal_action_set(cyr, eng.actions_by_actor["1415"], eng.state.skill_points))
        ids = {a.action_id for a in legal}
        assert "141508" in ids and "141501" not in ids, "仅能使用强化普攻"
        assert "141502" not in ids, "涟漪态锁战技"
        # 强化普攻两段：单体 #3 + 全体 #1（lv6 同档 0.3）+ 追忆 +3 + 不产战技点
        r0, sp0 = cyr.resources["recollection"], eng.state.skill_points
        hp0 = e1.current_hp
        _cast(eng, "1415", "141508")
        one_stage = 0.3 * CYRENE_HP_FULL * TEAM * CRIT_RIP * DEF_RES * 1.0 * UNBROKEN
        assert math.isclose(hp0 - e1.current_hp, one_stage * 2 * 1.24, rel_tol=1e-6), (
            "单体+全体两段（结界永续 → 每段各追加真伤 ×0.24）")
        assert math.isclose(cyr.resources["recollection"], r0 + 3.0)
        assert eng.state.skill_points == sp0, "强化普攻不能恢复战技点"


class TestHPSync:
    def test_bidirectional_percent_sync(self, compiled):
        eng = _make(compiled)
        cyr = _cyr(eng)
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")
        _ult(eng)
        dem = _dem(eng)
        # 降：昔涟被打到 50% → 德谬歌同步 50%（on_hp_decrease 通道）
        cyr.current_hp = 0.5 * CYRENE_HP_FULL
        eng.bus.emit("on_hp_decrease", {
            "amount": 1.0, "source": "e1", "reason": "hit", "target": "1415",
            "damage_type": "ice"}, eng.state)
        assert math.isclose(dem.current_hp, 0.5 * DEM_HP, rel_tol=1e-9), (
            "昔涟 HP% 下降 → 德谬歌同步（1141503）")
        # 升：昔涟被奶到 80% → 德谬歌同步 80%（on_hp_increase 通道——双向）
        cyr.current_hp = 0.8 * CYRENE_HP_FULL
        eng.bus.emit("on_hp_increase", {
            "amount": 1.0, "source": "ally", "reason": "heal", "target": "1415"}, eng.state)
        assert math.isclose(dem.current_hp, 0.8 * DEM_HP, rel_tol=1e-9)


class TestUniqueSourcesMinuet:
    def test_minuet_main_and_extra_instances(self, compiled):
        eng = _make(compiled)
        cyr, e1 = _cyr(eng), eng.state.actors["e1"]
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")   # 来源 {1415, ally}
        _ult(eng)
        dem = _dem(eng)
        hp0 = e1.current_hp
        eng.trigger_action(dem, next(a for a in eng.actions_by_actor["1415_dem"]
                                     if a.action_id == "1141501"), tag="test")
        main = 0.84 * DEM_HP * TEAM * CRIT_RIP * DEF_RES * 1.0 * UNBROKEN
        assert math.isclose(hp0 - e1.current_hp, main * 2 * 1.24, rel_tol=1e-6), (
            "Minuet 主段 0.84 + 1 个不同队友来源追加 1 段 ×0.84（unique_sources 2−1；"
            "单敌随机段同落 e1；结界永续 → 每段各追加真伤）")


class TestStoryAutoMinuet:
    def test_story_three_consumed_auto_minuet(self, compiled):
        eng = _make(compiled)
        cyr, e1 = _cyr(eng), eng.state.actors["e1"]
        eng._gain_resource(cyr, "recollection", 18.0, source_id="ally")
        _ult(eng)
        dem = _dem(eng)
        assert math.isclose(dem.resources["story"], 1.0)
        eng._gain_resource(dem, "story", 1.0, source_id="1415")           # 补到 2
        hp0 = e1.current_hp
        eng._gain_resource(dem, "story", 1.0, source_id="1415")           # 满 3 → 全耗自动放
        assert math.isclose(dem.resources["story"], 0.0), "Story 满 3 全耗"
        main = 0.84 * DEM_HP * TEAM * CRIT_RIP * DEF_RES * 1.0 * UNBROKEN
        assert math.isclose(hp0 - e1.current_hp, main * 2 * 1.24, rel_tol=1e-6), (
            "自动施放 Minuet（额外回合+自动施放压缩为插入施放，在案）——主段+追加段全量")


class TestOdePartial:
    """Ode 系列本队三件 + 泛用（能做的部分——跨 actor 资源/层写通道缺的半件待收在案）."""

    def _ode_build_eng(self):
        """昔涟 + 三黄金裔 stub（队伍上限 4——泛用档的非黄金裔目标走基础 build 的 ally）."""
        allies = [
            {"actor_id": aid, "name": nm, "inline": True,
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": f"{aid}_b", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "ice",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}
            for aid, nm in (("1407", "遐蝶 stub"), ("1409", "风堇 stub"), ("1413", "长夜月 stub"))]
        build = {"build": {"team": [{"character_template": "1415", "level": 80}] + allies,
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=10)
        eng.setup()
        eng._gain_resource(eng.state.actors["1415"], "recollection", 18.0, source_id="ally")
        _ult(eng)
        return eng

    def test_generic_ode_on_non_heir(self, compiled):
        eng = _make(compiled)
        eng._gain_resource(_cyr(eng), "recollection", 18.0, source_id="ally")
        _ult(eng)
        ally = eng.state.actors["ally"]
        _cast(eng, "1415_dem", "1141502", target="ally")
        mod = ally.modifiers["CYRENE_ODE_GENERIC"]
        assert math.isclose(mod.stat_effects["all_dmg"], 0.56) and mod.duration == 2, (
            "泛用档：非黄金裔 +56% 增伤 2 回合（lv10 #2/#3）")

    def test_ode_to_sky_cast_level(self):
        eng = self._ode_build_eng()
        hya = eng.state.actors["1409"]
        hya.current_energy = 10.0
        _cast(eng, "1415_dem", "1141502", target="1409")
        assert math.isclose(hya.current_energy, 10.0 + 33.6), "1141519：充能 33.6（lv10 #2）"
        ode = hya.modifiers["CYRENE_ODE_SKY"]
        assert ode.stacks == 2, "1141519：获 2 层「天空」（tally/消耗半件待收在案）"

    def test_ode_to_time_and_life_death_markers(self):
        eng = self._ode_build_eng()
        _cast(eng, "1415_dem", "1141502", target="1413")
        assert "CYRENE_ODE_TIME" in eng.state.actors["1413"].modifiers, (
            "1141524：整战斗标记（忆质+1/光环暴伤半件待收在案；长夜不在场增伤件 no-op）")
        _cast(eng, "1415_dem", "1141502", target="1407")
        assert "CYRENE_ODE_LIFE_DEATH" in eng.state.actors["1407"].modifiers, (
            "1141517：整件待收仅挂标记（新蕊溢出/消耗/倍率烘焙通道缺）")


class TestTechnique:
    def test_technique_prebattle_zone(self):
        build = _build(pre_battle=[{"actor_id": "1415", "technique": "141507"}])
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _stage(), template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        zone = _cyr(eng).modifiers.get("CYRENE_ZONE")
        assert zone is not None and zone.duration == 2, (
            "秘技：进战展开战技结界（2 回合档——异空间地图件不收）")
        assert zone.tick_anchor == "owner_turn_start"


class TestFullRunSmoke:
    def test_rule_policy_full_chain(self, compiled):
        eng = _make(compiled)
        _cyr(eng).resources["recollection"] = 20.0     # 政策窗口 2 动内满 24 自动开大
        state = eng.run()
        log = state.log
        assert not state.truncated
        assert "1415_dem" in state.actors, "德谬歌已入场"
        assert any("进入形态 往昔的涟漪" in l for l in log), (
            "政策窗口满追忆自动首开（入口技不走 _execute_action——无'使用'日志，"
            "白厄变身同型；进入形态即首开铁证）")
        assert any("向着爱与明天♪" in l for l in log), "涟漪态政策选招=强化普攻"
        assert any("花与箭的舞曲" in l for l in log), "德谬歌额外回合施放 Minuet"
        assert any("真实伤害" in l for l in log), "结界真伤追加留痕"
        assert state.actors["1415"].state_config.state == "ripples"
        assert state.actors["1415"].resources["recollection"] >= 0.0
