"""DoT 全乘区接链（B27#3 收官）：快照切分 / 目标侧链 / dot_dmg_boost 池 / 裂伤链 / scoped 承伤.

spec 锚：mechanics 02 §2.12（DOT 乘区表 + 快照切分落地口径）+ 01_formula §1.4（裂伤特例，
BE 在 cap 外乘区）。公式链 = rulebook `dot_damage`（route["dot"]）/ `bleed_dot_damage`
（route["bleed"]）表达式求值，此处只手算对轴。

口径常数（expected 模式）：假人 lv80、attacker lv80 → 防御区 = 1000/(def+1000)
（def 1000 → 0.5；def 500 → 2/3）；弱点匹配 → 抗性 1.0，非弱点默认抗 0.2 → 0.8；
未击破 0.9 / 已击破 1.0。旧 v0.2 简化口径（快照面板×倍率零乘区）已退役。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, SettlementPipeline
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.state import ActorState, Modifier
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _src_st(atk: float = 2000.0, **stats) -> ActorState:
    """施加者（攻击侧快照源）：默认裸板 atk 2000 / lv80."""
    base = {"atk": atk, "spd": 100, "hp": 5000, "max_energy": 100}
    base.update(stats)
    hero = Actor(actor_id="hero", name="测试员", level=80, stats=StatBlock(**base))
    return ActorState(actor=hero, current_hp=hero.stats.hp)


def _holder_st(*, def_: float = 1000.0, weakness=("fire",), hp: float = 1e9,
               broken: bool = False, max_toughness: float = 120.0,
               actor_type: str = "monster", resistance=None,
               vulnerability: float = 0.0) -> ActorState:
    """跳伤持有者（目标侧现值）：默认 def 1000 / 火弱点 / 未击破."""
    enemy = Actor(actor_id="e1", name="假人", actor_type=actor_type, level=80,
                  stats=StatBlock(hp=hp, spd=100, def_=def_, max_toughness=max_toughness,
                                  weakness=list(weakness), resistance=dict(resistance or {}),
                                  vulnerability=vulnerability))
    st = ActorState(actor=enemy, current_hp=hp)
    st.broken = broken
    return st


def _dot_mod(pipe: SettlementPipeline, src: ActorState, holder: ActorState, *,
             element: str = "fire", ratio: float = 1.0, legacy: bool = False) -> Modifier:
    """dot 件：默认走施加时刻快照包（dot_snapshot_context）；legacy=True 裸件兜底路径."""
    mod = Modifier(modifier_id="DOT_T", name="持续伤害", modifier_type="dot", debuff_kind="dot",
                   duration=2, source_id=src.actor.actor_id, dot_element=element, dot_ratio=ratio,
                   dot_source_atk=pipe.effective_stats(src)["atk"])
    if not legacy:
        mod.dot_snapshot_ctx = pipe.dot_snapshot_context(src, holder, element, ratio)
    return mod


def _neutralize_def(holder: ActorState) -> None:
    """防御区中性化（def_ 覆写 0 → def_multi=1.0）——「无乘区=旧值」锚的构造件."""
    holder.modifiers["DEF0"] = Modifier(
        modifier_id="DEF0", name="零防", modifier_type="debuff",
        override_effects={"def_": 0.0})


# ---------------------------------------------------------------------------
# ① 基础跳伤对轴：攻击侧无乘区 + 目标侧链全中性 → 与旧简化口径同值
# ---------------------------------------------------------------------------
class TestBaselineTick:
    def test_neutral_chain_matches_legacy_value(self):
        """中性链（def 覆写 0→1.0、火弱点 1.0、已击破 1.0）：跳伤 = atk 快照 × ratio 旧值."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(atk=5432.1 / 1.234)   # 有效 atk 使 ability = 5432.1×1.234/1.234…直取整
        holder = _holder_st(broken=True)
        _neutralize_def(holder)
        mod = _dot_mod(pipe, src, holder, ratio=1.234)
        ability = pipe.effective_stats(src)["atk"] * 1.234
        r = pipe.dot_tick(holder, mod)
        assert math.isclose(r.value, ability, rel_tol=1e-12), "中性链下 = 旧快照值"
        assert math.isclose(holder.current_hp, 1e9 - ability, rel_tol=1e-9)

    def test_legacy_bare_mod_fallback(self):
        """裸件兜底（无 dot_snapshot_ctx）：攻击侧全中性、基数走 dot_source_atk×dot_ratio."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st()
        holder = _holder_st(broken=True)
        _neutralize_def(holder)
        mod = _dot_mod(pipe, src, holder, ratio=1.234, legacy=True)
        mod.dot_source_atk = 5432.1
        r = pipe.dot_tick(holder, mod)
        assert r.value == 5432.1 * 1.234, "裸件中性链下 = 旧简化值（逐比特）"

    def test_unbroken_dummy_chain(self):
        """非中性假人（def 1000→0.5、弱点 1.0、未击破 0.9）：2000×1.0×0.45 = 900."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(atk=2000.0)
        holder = _holder_st()
        mod = _dot_mod(pipe, src, holder, ratio=1.0)
        r = pipe.dot_tick(holder, mod)
        assert math.isclose(r.value, 2000.0 * 0.5 * 0.9, rel_tol=1e-12)
        assert r.node["isCrit"] is False, "DoT 不暴击"


# ---------------------------------------------------------------------------
# ② dot_dmg_boost 面板池折入（「持续伤害提高」——增伤合成按施加时刻快照）
# ---------------------------------------------------------------------------
class TestDotDmgBoostPool:
    def test_boost_bucket_folded(self):
        """桶 0.24 → 增伤区 1.24：2000×1.24×0.5×0.9 = 1116."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(dmg_bonus={"dot_dmg_boost": 0.24})
        holder = _holder_st()
        mod = _dot_mod(pipe, src, holder, ratio=1.0)
        assert math.isclose(mod.dot_snapshot_ctx["dmg_boost_multi"], 1.24, rel_tol=1e-12)
        r = pipe.dot_tick(holder, mod)
        assert math.isclose(r.value, 2000.0 * 1.24 * 0.5 * 0.9, rel_tol=1e-12)

    def test_boost_stacks_with_all_and_element(self):
        """all 0.1 + fire 0.2 + dot 0.24 → 1.54；非同属性桶（ice 0.5）不计."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(dmg_bonus={"all": 0.1, "fire": 0.2, "dot_dmg_boost": 0.24, "ice": 0.5})
        holder = _holder_st()
        mod = _dot_mod(pipe, src, holder, element="fire", ratio=1.0)
        assert math.isclose(mod.dot_snapshot_ctx["dmg_boost_multi"], 1.54, rel_tol=1e-12)
        r = pipe.dot_tick(holder, mod)
        assert math.isclose(r.value, 2000.0 * 1.54 * 0.5 * 0.9, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# ③ 目标侧链逐区（防御/抗性/易伤/减伤/韧性减伤——跳伤时刻现值）
# ---------------------------------------------------------------------------
class TestTargetSideChain:
    def _tick(self, src: ActorState, holder: ActorState, ratio: float = 1.0) -> float:
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        return pipe.dot_tick(holder, _dot_mod(pipe, src, holder, ratio=ratio)).value

    def test_def_zone(self):
        """def 500 → 1000/(500+1000) = 2/3：2000×2/3×0.9 = 1200."""
        assert math.isclose(self._tick(_src_st(), _holder_st(def_=500.0)),
                            2000.0 * (2 / 3) * 0.9, rel_tol=1e-12)

    def test_def_pen_from_snapshot(self):
        """def_pen 0.5（攻击侧快照输入）→ 1000/(1000×0.5+1000) = 2/3."""
        assert math.isclose(self._tick(_src_st(def_pen=0.5), _holder_st()),
                            2000.0 * (2 / 3) * 0.9, rel_tol=1e-12)

    def test_res_zone_non_weakness(self):
        """非弱点（冰 DoT 打火弱假人）→ 0.8：2000×0.5×0.8×0.9 = 720."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st()
        holder = _holder_st(weakness=("fire",))
        mod = _dot_mod(pipe, src, holder, element="ice", ratio=1.0)
        assert math.isclose(pipe.dot_tick(holder, mod).value,
                            2000.0 * 0.5 * 0.8 * 0.9, rel_tol=1e-12)

    def test_res_zone_explicit_resistance(self):
        """面板火抗 0.5（非弱点覆盖默认 0.2）→ 0.5；res_pen 快照 0.2 → 有效 0.3 → 0.7."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(res_pen=0.2)
        holder = _holder_st(weakness=(), resistance={"fire": 0.5})
        mod = _dot_mod(pipe, src, holder, element="fire", ratio=1.0)
        assert math.isclose(pipe.dot_tick(holder, mod).value,
                            2000.0 * 0.5 * 0.7 * 0.9, rel_tol=1e-12)

    def test_vuln_zone(self):
        """面板易伤 0.3 → 1.3：2000×0.5×0.9×1.3 = 1170."""
        assert math.isclose(self._tick(_src_st(), _holder_st(vulnerability=0.3)),
                            2000.0 * 0.5 * 0.9 * 1.3, rel_tol=1e-12)

    def test_dmg_red_zone(self):
        """减伤件（dmg_dmg_reduction 0.2）→ 0.8：2000×0.5×0.9×0.8 = 720."""
        holder = _holder_st()
        holder.modifiers["DR"] = Modifier(
            modifier_id="DR", name="减伤", modifier_type="debuff",
            stat_effects={"dmg_dmg_reduction": 0.2})
        assert math.isclose(self._tick(_src_st(), holder),
                            2000.0 * 0.5 * 0.9 * 0.8, rel_tol=1e-12)

    def test_base_universal_zone(self):
        """已击破 1.0 vs 未击破 0.9：同一跳伤两态差分."""
        assert math.isclose(self._tick(_src_st(), _holder_st(broken=True)),
                            2000.0 * 0.5 * 1.0, rel_tol=1e-12)
        assert math.isclose(self._tick(_src_st(), _holder_st(broken=False)),
                            2000.0 * 0.5 * 0.9, rel_tol=1e-12)

    def test_ind_vuln_zone_current_value(self):
        """独立易伤（常规 DoT 生效列）：目标面板桶 0.4 → ×1.4（跳伤时刻现值）."""
        holder = _holder_st()
        holder.modifiers["IV"] = Modifier(
            modifier_id="IV", name="独立易伤", modifier_type="debuff",
            stat_effects={"dmg_ind_vulnerability": 0.4})
        assert math.isclose(self._tick(_src_st(), holder),
                            2000.0 * 0.5 * 0.9 * 1.4, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# ④ 快照语义（engine 级）：施加后攻击侧 buff 移除不影响跳伤；目标侧 debuff 后挂影响跳伤
# ---------------------------------------------------------------------------
def _engine() -> CombatEngine:
    hero = Actor(actor_id="hero", name="测试员", level=80,
                 stats=StatBlock(atk=2000, spd=200, hp=5000, max_energy=100,
                                 crit_rate=0.0, crit_dmg=0.5))
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=1e9, spd=50, def_=1000, max_toughness=100,
                                  weakness=["fire", "physical"]))
    enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                    termination=TerminationConfig(mode="fixed_av", max_action_value=300))
    eng = CombatEngine(enc, actions_by_actor={}, policy=ScriptedPolicy(),
                       mode=MODE_EXPECTED, initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


_DOT_SPEC = {"modifier_id": "DOT_FIRE", "name": "灼烧", "modifier_type": "dot",
             "duration": 2, "dot_element": "fire", "dot_ratio": 1.0}


class TestSnapshotSemantics:
    def test_attacker_side_frozen_target_side_live(self):
        eng = _engine()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        # 施加者带 atk+50% buff（有效 atk 3000）时施加 DoT → 快照 ability=3000
        eng._apply_modifier(hero_st, Modifier(
            modifier_id="ATKB", name="攻击提升", modifier_type="buff",
            stat_effects={"atk_pct": 0.5}))
        assert math.isclose(eng.pipeline.effective_stats(hero_st)["atk"], 3000.0, rel_tol=1e-12)
        eng._apply_modifier_spec(e1, dict(_DOT_SPEC), hero_st)
        mod = e1.modifiers["DOT_FIRE"]
        assert math.isclose(mod.dot_snapshot_ctx["ability_multiplier"], 3000.0, rel_tol=1e-12)
        assert math.isclose(mod.dot_source_atk, 3000.0, rel_tol=1e-12), "快照按施加时刻有效面板"
        hp0 = e1.current_hp
        eng._tick_dots(e1)
        tick1 = hp0 - e1.current_hp
        assert math.isclose(tick1, 3000.0 * 0.5 * 0.9, rel_tol=1e-12)
        # 攻击侧 buff 移除（有效 atk 回落 2000）→ 跳伤不变（快照）
        hero_st.modifiers.pop("ATKB")
        assert math.isclose(eng.pipeline.effective_stats(hero_st)["atk"], 2000.0, rel_tol=1e-12)
        hp1 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp1 - e1.current_hp, tick1, rel_tol=1e-12), "攻击侧快照不随面板回落"
        # 目标侧易伤后挂（0.5）→ 当次起跳伤 ×1.5（现值）
        eng._apply_modifier(e1, Modifier(
            modifier_id="VULN", name="易伤", modifier_type="debuff",
            stat_effects={"vulnerability": 0.5}))
        hp2 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp2 - e1.current_hp, 3000.0 * 0.5 * 0.9 * 1.5, rel_tol=1e-12)

    def test_dot_spec_rejects_missing_source(self):
        """编译期拒非法补位：dot 件无施加者 = 无快照源，报错指路."""
        eng = _engine()
        e1 = eng.state.actors["e1"]
        with pytest.raises(ValueError, match="快照源"):
            eng._apply_modifier_spec(e1, dict(_DOT_SPEC), None)

    def test_dot_spec_rejects_bad_ratio(self):
        """缺 dot_ratio/dot_element = 残件，报错指路."""
        eng = _engine()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        with pytest.raises(ValueError, match="dot_ratio"):
            eng._apply_modifier_spec(
                e1, {"modifier_id": "BAD", "name": "残件", "modifier_type": "dot",
                     "duration": 2, "dot_element": "fire"}, hero_st)


# ---------------------------------------------------------------------------
# ⑤ 裂伤目标侧链（bleed_dot_damage：BE/最终伤害快照，其余目标侧现值；独立易伤/虚弱不喂）
# ---------------------------------------------------------------------------
class TestBleedChain:
    def _bleed_mod(self, pipe, src, holder, ratio=1.0) -> Modifier:
        mod = Modifier(modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot",
                       debuff_kind="dot", duration=2, source_id=src.actor.actor_id,
                       dot_element="physical", dot_ratio=ratio)
        mod.dot_snapshot_ctx = pipe.dot_snapshot_context(src, holder, "physical", ratio)
        return mod

    def test_bleed_full_chain(self):
        """elite 7%×100000 = 7000（未触 cap）；BE 1.0→2.0、最终伤害 0.5→1.5（快照）；
        def 0.5 / 物理弱点 1.0 / 已击破 1.0（现值）→ 7000×2.0×1.5×0.5 = 10500."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(break_effect=1.0, dmg_bonus={"final_dmg_boost": 0.5})
        holder = _holder_st(hp=100000.0, weakness=("physical",), broken=True)
        holder.current_hp = 100000.0
        mod = self._bleed_mod(pipe, src, holder)
        r = pipe.bleed_tick(holder, mod)
        assert math.isclose(r.node["bleedBaseMulti"], 7000.0, rel_tol=1e-12)
        assert math.isclose(r.value, 7000.0 * 2.0 * 1.5 * 0.5 * 1.0 * 1.0, rel_tol=1e-12)

    def test_bleed_target_side_variations(self):
        """未击破 ×0.9 / 易伤 0.3 ×1.3 / 非弱点 ×0.8（现值逐区）."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(break_effect=1.0)
        # 未击破
        h1 = _holder_st(hp=100000.0, weakness=("physical",), broken=False)
        h1.current_hp = 100000.0
        r1 = pipe.bleed_tick(h1, self._bleed_mod(pipe, src, h1))
        assert math.isclose(r1.value, 7000.0 * 2.0 * 0.5 * 1.0 * 0.9, rel_tol=1e-12)
        # 易伤现值
        h2 = _holder_st(hp=100000.0, weakness=("physical",), broken=True, vulnerability=0.3)
        h2.current_hp = 100000.0
        r2 = pipe.bleed_tick(h2, self._bleed_mod(pipe, src, h2))
        assert math.isclose(r2.value, 7000.0 * 2.0 * 0.5 * 1.3 * 1.0, rel_tol=1e-12)
        # 非弱点抗性
        h3 = _holder_st(hp=100000.0, weakness=("fire",), broken=True)
        h3.current_hp = 100000.0
        r3 = pipe.bleed_tick(h3, self._bleed_mod(pipe, src, h3))
        assert math.isclose(r3.value, 7000.0 * 2.0 * 0.5 * 0.8 * 1.0, rel_tol=1e-12)

    def test_bleed_ignores_ind_vuln_and_weaken(self):
        """击破 DoT 列：独立易伤（目标 0.4）/ 虚弱（施加者 0.3）/ 增伤（施加者 0.5）均不喂."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(break_effect=1.0,
                      dmg_bonus={"weaken": 0.3, "all": 0.5, "dot_dmg_boost": 0.5})
        holder = _holder_st(hp=100000.0, weakness=("physical",), broken=True)
        holder.current_hp = 100000.0
        holder.modifiers["IV"] = Modifier(
            modifier_id="IV", name="独立易伤", modifier_type="debuff",
            stat_effects={"dmg_ind_vulnerability": 0.4})
        r = pipe.bleed_tick(holder, self._bleed_mod(pipe, src, holder))
        assert math.isclose(r.value, 7000.0 * 2.0 * 0.5 * 1.0 * 1.0, rel_tol=1e-12)

    def test_bleed_cap_binds_before_be(self):
        """cap 在基数层比较：HP 1e9 精英 → min 取 2×3767.5533×3.5，BE 在 cap 外乘."""
        pipe = SettlementPipeline(mode=MODE_EXPECTED)
        src = _src_st(break_effect=1.0)
        holder = _holder_st(hp=1e9, weakness=("physical",), broken=True)
        mod = self._bleed_mod(pipe, src, holder)
        cap = 2 * 3767.5533 * (0.5 + 120 / 40)
        r = pipe.bleed_tick(holder, mod)
        assert math.isclose(r.node["bleedBaseMulti"], cap, rel_tol=1e-12)
        assert math.isclose(r.value, cap * 2.0 * 0.5 * 1.0 * 1.0, rel_tol=1e-12)

    def test_bleed_engine_break_integration(self):
        """引擎链：物理击破 → BRK_DOT_physical 带快照（BE 2.0）→ 跳伤全链.

        cap = 2×3767.5533×(0.5+100/40) = 22605.3198；×2.0（BE）×0.5（def）×1.0（弱点）
        ×1.0（已击破）= 22605.3198。
        """
        hero = Actor(actor_id="hero", name="测试员", level=80,
                     stats=StatBlock(atk=2000, spd=200, hp=5000, max_energy=100,
                                     break_effect=1.0, crit_rate=0.0, crit_dmg=0.5))
        dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                      stats=StatBlock(hp=1e9, spd=50, def_=1000, max_toughness=100,
                                      weakness=["physical"]))
        enc = Encounter(encounter_id="t", name="t", actors=[hero, dummy],
                        termination=TerminationConfig(mode="fixed_av", max_action_value=300))
        eng = CombatEngine(enc, actions_by_actor={
            "hero": [Action(action_id="b", name="普攻", action_type="basic",
                            target_type="single", damage_type="physical",
                            scaling=[{"atk": 1.0}], toughness_dmg=100)]},
            policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
            initial_sp=10, initial_energy_ratio=0.0)
        eng.setup()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._execute_action(hero_st, eng.actions_by_actor["hero"][0])
        assert "BRK_DOT_physical" in e1.modifiers and e1.broken
        cap = 2 * 3767.5533 * (0.5 + 100 / 40)
        hp0 = e1.current_hp
        eng._tick_dots(e1)
        assert math.isclose(hp0 - e1.current_hp, cap * 2.0 * 0.5 * 1.0 * 1.0, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# ⑥ scoped vulnerability「受到的持续伤害提高」：命中 dot（含裂伤）不命中直伤
# ---------------------------------------------------------------------------
class TestScopedDotVulnerability:
    def _eng_with_scoped(self) -> CombatEngine:
        eng = _engine()
        e1 = eng.state.actors["e1"]
        # 类型限定承伤：vulnerability + hit_condition（椒丘 1218/灵砂 1222 同构——action_type 路由 id "dot"）
        eng._apply_modifier_spec(e1, {
            "modifier_id": "DOT_TAKEN", "name": "受到的持续伤害提高", "modifier_type": "debuff",
            "duration": 0, "stat_effects": {"vulnerability": 0.2},
            "hit_condition": "$event.action_type == 'dot'"}, None)
        return eng

    def test_scoped_hits_dot_tick(self):
        eng = self._eng_with_scoped()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        eng._apply_modifier_spec(e1, dict(_DOT_SPEC), hero_st)
        hp0 = e1.current_hp
        eng._tick_dots(e1)
        # 2000×0.5×0.9×(1+0.2 scoped) = 1080
        assert math.isclose(hp0 - e1.current_hp, 2000.0 * 0.5 * 0.9 * 1.2, rel_tol=1e-12)

    def test_scoped_misses_direct_damage(self):
        eng = self._eng_with_scoped()
        hero_st = eng.state.actors["hero"]
        e1 = eng.state.actors["e1"]
        action = Action(action_id="b", name="普攻", action_type="basic", target_type="single",
                        damage_type="fire", scaling=[{"atk": 1.0}])
        r = eng.pipeline.deal_damage(action, hero_st, e1)
        # 直伤命中域 action_type='basic' → scoped 不命中：2000×0.5×0.9（期望暴击 1.0——crit_rate 0）
        assert math.isclose(r.value, 2000.0 * 0.5 * 0.9, rel_tol=1e-12)

    def test_scoped_hits_bleed_tick(self):
        eng = self._eng_with_scoped()
        e1 = eng.state.actors["e1"]
        e1.actor.stats.hp = 100000.0
        e1.current_hp = 100000.0
        e1.broken = True
        mod = Modifier(modifier_id="BRK_DOT_physical", name="裂伤", modifier_type="dot",
                       debuff_kind="dot", duration=2, source_id="hero",
                       dot_element="physical", dot_ratio=1.0,
                       dot_snapshot_ctx=eng.pipeline.dot_snapshot_context(
                           eng.state.actors["hero"], e1, "physical", 1.0))
        e1.modifiers["BRK_DOT_physical"] = mod
        hp0 = e1.current_hp
        eng._tick_dots(e1)
        # 7000×1.0（BE 0）×0.5×1.0×1.0×1.2 scoped = 5040
        assert math.isclose(hp0 - e1.current_hp, 7000.0 * 0.5 * 1.2, rel_tol=1e-12)
