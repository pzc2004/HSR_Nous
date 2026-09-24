"""位面饰品 301-313 族遗器 e2e：staging→fixtures 验收批（12 套——301/302/303/304/
305/306/307/308/309/310/311/313；位面饰品仅 2pc，无 4pc 段：2 件触发 2pc、4 件与
2 件全等、1 件不触发）。勘正条目逐套见 tests/fixtures/templates/relics/<id>_*.yaml
头注；官方依据 data/starrailres/index_new/cn/relic_sets.json desc+properties。

口径常数：假人 def 1000 → 防御区 0.5；火弱点 → 抗性区 1.0；未击破 0.9；期望暴击区
1+crit_rate×crit_dmg（装备员默认 0.05/0.5 → 1.025，阈值套按面板另算）。直伤链
Z0=0.5×0.9。阈值语义=动态门（enable_if 懒求值——官方"当前暴击率/速度大于等于"
文本+社区层：战斗中面板过线即生效，格拉默提速吃 18% 攻略实证）；305/308 触发域
=进战快照（官方"进入战斗后/时"）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

Z0 = 0.5 * 0.9  # 防御区×未击破


def _actions(*kinds):
    pool = {
        "basic": {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
                  "target_type": "single", "damage_type": "fire",
                  "scaling": [{"atk": 1.0}], "toughness_dmg": 10},
        "skill": {"action_id": "t_skill", "name": "战技", "action_type": "skill",
                  "target_type": "single", "damage_type": "fire",
                  "scaling": [{"atk": 2.0}], "toughness_dmg": 20},
        "ultimate": {"action_id": "t_ult", "name": "终结技", "action_type": "ultimate",
                     "target_type": "single", "damage_type": "fire",
                     "scaling": [{"atk": 2.0}], "toughness_dmg": 30},
        "follow_up": {"action_id": "t_fua", "name": "追加", "action_type": "follow_up",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.5}], "toughness_dmg": 10},
    }
    return [dict(pool[k]) for k in kinds]


def _build(set_id, pieces, *, stats=None, action_kinds=("basic",), with_ally=False):
    base = {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100, **(stats or {})}
    team = [{"actor_id": "w", "name": "装备员", "inline": True, "base_stats": base,
             "relics": {f"slot{i}": {"set_id": set_id} for i in range(pieces)},
             "actions": _actions(*action_kinds)}]
    if with_ally:
        team.append({"actor_id": "a2", "name": "队友", "inline": True,
                     "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
                     "actions": _actions("basic")})
    return {"build": {"team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage(squishy=0):
    enemies = [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 100,
                "weakness": ["fire", "ice", "thunder", "wind", "quantum",
                             "imaginary", "physical"]}]
    for i in range(squishy):
        enemies.append({"actor_id": f"s{i + 1}", "name": f"脆皮{i + 1}", "hp": 100,
                        "spd": 100, "atk": 1000, "def": 1000, "max_toughness": 100,
                        "weakness": ["fire"]})
    return {"stage": {"stage_id": "s", "enemies": enemies,
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(set_id, pieces, *, stats=None, action_kinds=("basic",), with_ally=False,
          squishy=0):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(set_id, pieces, stats=stats, action_kinds=action_kinds,
                                 with_ally=with_ally),
                          _stage(squishy), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _cast(eng, owner, aid, target_id="e1"):
    """直施对轴（钩子触发通道——照抄 trailblazer 模子）：_execute_action + on_action 补发."""
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "actor_type": st.actor.actor_type}, eng.state)


def _eff(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


class TestSet301SpaceSealing:
    """301 太空封印站：atk+12%（stat_effects 常驻）；spd≥120 动态门再 +12%."""

    @pytest.mark.parametrize("pieces,want100,want120",
                             [(1, 1000.0, 1000.0), (2, 1120.0, 1240.0), (4, 1120.0, 1240.0)])
    def test_atk_by_pieces(self, pieces, want100, want120):
        """1 件不触发；2/4 件同效（无 4pc 段）——1000×(1+0.12[+0.12])."""
        assert math.isclose(_eff(_make("301", pieces))["atk"], want100, rel_tol=1e-9)
        assert math.isclose(_eff(_make("301", pieces, stats={"spd": 120}))["atk"],
                            want120, rel_tol=1e-9)

    def test_threshold_boundary_119(self):
        eng = _make("301", 2, stats={"spd": 119})
        assert math.isclose(_eff(eng)["atk"], 1120.0, rel_tol=1e-9), "119 < 120 门槛不达"


class TestSet302FleetOfAgeless:
    """302 不老者的仙舟：hp+12%；spd≥120 → 我方全体 atk+8%（effect_scope: team 光环，
    条件读携带者面板）."""

    @pytest.mark.parametrize("pieces,hp,atk_w,atk_a",
                             [(1, 3000.0, 1000.0, 1000.0),
                              (2, 3360.0, 1080.0, 1080.0),
                              (4, 3360.0, 1080.0, 1080.0)])
    def test_team_aura_by_pieces(self, pieces, hp, atk_w, atk_a):
        eng = _make("302", pieces, stats={"spd": 120}, with_ally=True)
        assert math.isclose(_eff(eng)["hp"], hp, rel_tol=1e-9), "3000×1.12"
        assert math.isclose(_eff(eng)["atk"], atk_w, rel_tol=1e-9), "装备员自吃 1000×1.08"
        assert math.isclose(_eff(eng, "a2")["atk"], atk_a, rel_tol=1e-9), "队友辐射 1000×1.08"

    def test_below_threshold_no_aura(self):
        eng = _make("302", 2, with_ally=True)
        assert math.isclose(_eff(eng)["hp"], 3360.0, rel_tol=1e-9), "常驻段不受阈值影响"
        assert math.isclose(_eff(eng)["atk"], 1000.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a2")["atk"], 1000.0, rel_tol=1e-9), (
            "携带者 spd 100——staging 旧病（all_allies 各按自己速度判定）下队友会误吃")


class TestSet303PanGalactic:
    """303 泛银河商业公司：effect_hit+10%；atk_pct=clamp(当前效果命中×25%, 0, 25%)
    ——stat_exprs 现场求值（无条件件面板含本套 2pc 的 0.1）."""

    @pytest.mark.parametrize("pieces,ehr0,want_atk,want_ehr",
                             [(1, 0.0, 1000.0, 0.0), (2, 0.0, 1025.0, 0.1),
                              (4, 0.0, 1025.0, 0.1)])
    def test_conversion_by_pieces(self, pieces, ehr0, want_atk, want_ehr):
        eng = _make("303", pieces, stats={"effect_hit": ehr0})
        assert math.isclose(_eff(eng)["effect_hit"], want_ehr, rel_tol=1e-9)
        assert math.isclose(_eff(eng)["atk"], want_atk, rel_tol=1e-9), (
            "1000×(1+(0+ehr0+0.1)×0.25)")

    def test_conversion_curve(self):
        """ehr 0.5 → (0.6)×0.25=0.15 → 1150；ehr 1.0 → 1.1×0.25=0.275 钳 0.25 → 1250."""
        assert math.isclose(_eff(_make("303", 2, stats={"effect_hit": 0.5}))["atk"],
                            1150.0, rel_tol=1e-9)
        assert math.isclose(_eff(_make("303", 2, stats={"effect_hit": 1.0}))["atk"],
                            1250.0, rel_tol=1e-9), "最多提高 25% 封顶"


class TestSet304Belobog:
    """304 筑城者的贝洛伯格：def+15%；effect_hit≥50% 动态门再 +15%（死键
    'effect_hit_rate' 已正为 $self.effect_hit）."""

    @pytest.mark.parametrize("pieces,ehr0,want",
                             [(1, 0.0, 500.0), (2, 0.0, 575.0), (2, 0.5, 650.0),
                              (4, 0.5, 650.0)])
    def test_def_by_threshold(self, pieces, ehr0, want):
        eng = _make("304", pieces, stats={"def": 500, "effect_hit": ehr0})
        assert math.isclose(_eff(eng)["def_"], want, rel_tol=1e-9), (
            "500×(1+0.15[+0.15])——ehr0 0.5+2pc 0.1=0.6≥0.5")

    def test_below_threshold(self):
        eng = _make("304", 2, stats={"def": 500, "effect_hit": 0.39})
        assert math.isclose(_eff(eng)["def_"], 575.0, rel_tol=1e-9), "0.39+0.1=0.49 < 0.5"


class TestSet305CelestialDifferentiator:
    """305 星体差分机：crit_dmg+16%；进战 crit_dmg≥120% 快照 → crit_rate+60%，
    首次行动结算后摘除（本动仍吃）."""

    @pytest.mark.parametrize("pieces,cr,cd", [(1, 0.05, 1.1), (2, 0.65, 1.26), (4, 0.65, 1.26)])
    def test_buff_by_pieces(self, pieces, cr, cd):
        """crit_dmg 1.1+0.16=1.26≥1.2 → crit_rate 0.05+0.6=0.65（1 件=裸面板 1.1/0.05）."""
        eng = _make("305", pieces, stats={"crit_dmg": 1.1})
        assert math.isclose(_eff(eng)["crit_rate"], cr, rel_tol=1e-9)
        assert math.isclose(_eff(eng)["crit_dmg"], cd, rel_tol=1e-9)

    def test_first_action_consumes(self):
        """首次攻击吃 0.65 暴击（1+0.65×1.26=1.819 期望区）→ 战后增益摘除."""
        eng = _make("305", 2, stats={"crit_dmg": 1.1})
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp, 1000 * 1.0 * Z0 * 1.819, rel_tol=1e-9)
        assert "SET_305_CRIT_RATE" not in eng.state.actors["w"].modifiers, "首动后摘除"
        assert math.isclose(_eff(eng)["crit_rate"], 0.05, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            1000 * 1.0 * Z0 * (1 + 0.05 * 1.26), rel_tol=1e-9), "第二动回归基础暴击"

    def test_below_threshold_no_buff(self):
        eng = _make("305", 2, stats={"crit_dmg": 0.9})
        assert math.isclose(_eff(eng)["crit_rate"], 0.05, rel_tol=1e-9), "0.9+0.16=1.06 < 1.2"
        _cast(eng, "w", "t_basic")
        assert "SET_305_CRIT_RATE" not in eng.state.actors["w"].modifiers


class TestSet306InertSalsotto:
    """306 停转的萨尔索图：crit_rate+8%；当前暴击率≥50% 动态门 → 终结技/追加 +15%
    （原生类型增伤桶 dmg_ultimate_dmg_boost / dmg_follow_up_dmg_boost；普攻不吃）."""

    @pytest.mark.parametrize("pieces,cr", [(1, 0.45), (2, 0.53), (4, 0.53)])
    def test_crit_panel_by_pieces(self, pieces, cr):
        eng = _make("306", pieces, stats={"crit_rate": 0.45})
        assert math.isclose(_eff(eng)["crit_rate"], cr, rel_tol=1e-9), "0.45+0.08=0.53"

    def test_ult_fua_boost_basic_excluded(self):
        """CZ=1+0.53×0.5=1.265：ult 2.0×1.15=1309.275；fua 1.5×1.15=981.95625；
        basic 1.0 无桶=569.25."""
        eng = _make("306", 2, stats={"crit_rate": 0.45},
                    action_kinds=("basic", "ultimate", "follow_up"))
        e1 = eng.state.actors["e1"]
        cz = 1 + 0.53 * 0.5
        for aid, ratio, boost in (("t_ult", 2.0, 1.15), ("t_fua", 1.5, 1.15),
                                  ("t_basic", 1.0, 1.0)):
            hp1 = e1.current_hp
            _cast(eng, "w", aid)
            assert math.isclose(hp1 - e1.current_hp,
                                1000 * ratio * boost * Z0 * cz, rel_tol=1e-9), aid

    def test_below_threshold_no_boost(self):
        """0.3+0.08=0.38 < 0.5 → 终结技无增伤（快照式 hook 条件旧病同点位回归测试）."""
        eng = _make("306", 2, stats={"crit_rate": 0.3}, action_kinds=("ultimate",))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_ult")
        assert math.isclose(hp1 - e1.current_hp,
                            1000 * 2.0 * Z0 * (1 + 0.38 * 0.5), rel_tol=1e-9)


class TestSet307Talia:
    """307 盗贼公国塔利亚：break_effect+16%；spd≥145 动态门再 +20%."""

    @pytest.mark.parametrize("pieces,spd,want",
                             [(1, 145, 0.0), (2, 100, 0.16), (2, 144, 0.16),
                              (2, 145, 0.36), (4, 145, 0.36)])
    def test_break_effect(self, pieces, spd, want):
        eng = _make("307", pieces, stats={"spd": spd})
        assert math.isclose(_eff(eng)["break_effect"], want, rel_tol=1e-9)


class TestSet308Vonwacq:
    """308 生命的翁瓦克：energy_regen+5%；进战 spd≥120 快照 → 行动提前 40%
    （remaining 10000-4000=6000——advance_action amount 百分数口径，旧病 0.4→40）."""

    @pytest.mark.parametrize("pieces,er,rem120", [(1, 1.0, 10000.0), (2, 1.05, 6000.0),
                                                  (4, 1.05, 6000.0)])
    def test_energy_regen_and_advance(self, pieces, er, rem120):
        eng = _make("308", pieces, stats={"spd": 120})
        assert math.isclose(_eff(eng)["energy_regen"], er, rel_tol=1e-9)
        assert math.isclose(_remaining(eng, "w"), rem120, rel_tol=1e-9)

    def test_below_threshold_no_advance(self):
        eng = _make("308", 2, stats={"spd": 119})
        assert math.isclose(_eff(eng)["energy_regen"], 1.05, rel_tol=1e-9)
        assert math.isclose(_remaining(eng, "w"), 10000.0, rel_tol=1e-9)


class TestSet309RutilantArena:
    """309 繁星竞技场：crit_rate+8%；当前暴击率≥70% 动态门 → 普攻/战技 +20%
    （dmg_basic_dmg_boost / dmg_skill_dmg_boost 原生桶；终结技不吃）."""

    @pytest.mark.parametrize("pieces,cr", [(1, 0.62), (2, 0.7), (4, 0.7)])
    def test_crit_panel_by_pieces(self, pieces, cr):
        eng = _make("309", pieces, stats={"crit_rate": 0.62})
        assert math.isclose(_eff(eng)["crit_rate"], cr, rel_tol=1e-9), "0.62+0.08=0.70 恰好达阈"

    def test_basic_skill_boost_ult_excluded(self):
        """CZ=1+0.7×0.5=1.35：basic 1.0×1.2=729；skill 2.0×1.2=1458；ult 2.0 无桶=1215."""
        eng = _make("309", 2, stats={"crit_rate": 0.62},
                    action_kinds=("basic", "skill", "ultimate"))
        e1 = eng.state.actors["e1"]
        cz = 1 + 0.7 * 0.5
        for aid, ratio, boost in (("t_basic", 1.0, 1.2), ("t_skill", 2.0, 1.2),
                                  ("t_ult", 2.0, 1.0)):
            hp1 = e1.current_hp
            _cast(eng, "w", aid)
            assert math.isclose(hp1 - e1.current_hp,
                                1000 * ratio * boost * Z0 * cz, rel_tol=1e-9), aid

    def test_below_threshold_no_boost(self):
        """0.5+0.08=0.58 < 0.7 → 普攻无增伤."""
        eng = _make("309", 2, stats={"crit_rate": 0.5})
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            1000 * 1.0 * Z0 * (1 + 0.58 * 0.5), rel_tol=1e-9)


class TestSet310BrokenKeel:
    """310 折断的龙骨：effect_res+10%；effect_res≥30% 动态门 → 我方全体 crit_dmg+10%
    （effect_scope: team 光环，同 302 修法）."""

    @pytest.mark.parametrize("pieces,er,cd_w,cd_a",
                             [(1, 0.2, 0.5, 0.5), (2, 0.3, 0.6, 0.6), (4, 0.3, 0.6, 0.6)])
    def test_team_aura_by_pieces(self, pieces, er, cd_w, cd_a):
        """effect_res 0.2+2pc 0.1=0.3 恰好达阈 → 全队暴伤 0.5+0.1=0.6（1 件=裸面板）."""
        eng = _make("310", pieces, stats={"effect_res": 0.2}, with_ally=True)
        assert math.isclose(_eff(eng)["effect_res"], er, rel_tol=1e-9)
        assert math.isclose(_eff(eng)["crit_dmg"], cd_w, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a2")["crit_dmg"], cd_a, rel_tol=1e-9)

    def test_below_threshold_no_aura(self):
        """0.19+0.1=0.29 < 0.3 → 携带者/队友皆无（staging 旧病下队友按各自抵抗判定会分化）."""
        eng = _make("310", 2, stats={"effect_res": 0.19}, with_ally=True)
        assert math.isclose(_eff(eng)["crit_dmg"], 0.5, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "a2")["crit_dmg"], 0.5, rel_tol=1e-9)


class TestSet311Glamoth:
    """311 苍穹战线格拉默：atk+12%；spd≥135/160 动态门分档 all_dmg +12%/+18%
    （单 modifier stat_exprs 三元分档；战斗中提速变档懒求值）."""

    @pytest.mark.parametrize("pieces,spd,boost",
                             [(1, 160, 0.0), (2, 134, 0.0), (2, 135, 0.12),
                              (2, 160, 0.18), (4, 160, 0.18)])
    def test_spd_tiers(self, pieces, spd, boost):
        """atk 恒 1000×1.12=1120；CZ=1.025；basic = 1120×(1+boost)×Z0×1.025."""
        eng = _make("311", pieces, stats={"spd": spd})
        assert math.isclose(_eff(eng)["atk"], 1120.0 if pieces >= 2 else 1000.0, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        atk = 1120.0 if pieces >= 2 else 1000.0
        assert math.isclose(hp1 - e1.current_hp,
                            atk * (1 + boost) * Z0 * 1.025, rel_tol=1e-9)

    def test_mid_battle_spd_buff_retier(self):
        """动态门实证：spd 134 进战无档 → 外部 +30 速（164）后升 0.18 档（快照式
        旧病=战斗中变档永久丢失；格拉默提速吃 18% 的社区层玩法即此口径）."""
        eng = _make("311", 2, stats={"spd": 134})
        st = eng.state.actors["w"]
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp, 1120 * Z0 * 1.025, rel_tol=1e-9), "提速前无档"
        eng._apply_modifier(st, Modifier(
            modifier_id="EXT_SPD", name="外部加速", modifier_type="buff",
            duration=2, stat_effects={"spd": 30.0}))
        assert math.isclose(_eff(eng)["spd"], 164.0, rel_tol=1e-9)
        hp1 = e1.current_hp
        _cast(eng, "w", "t_basic")
        assert math.isclose(hp1 - e1.current_hp,
                            1120 * 1.18 * Z0 * 1.025, rel_tol=1e-9), "提速后升 160 档"


class TestSet313Sigonia:
    """313 无主荒星茨冈尼亚：crit_rate+4%；敌方目标被消灭 → crit_dmg+4%/层、
    至多 10 层（stat_exprs 0.04×stacks 现场求值——引擎 stat_effects 不随层乘算）."""

    @pytest.mark.parametrize("pieces,cr", [(1, 0.05), (2, 0.09), (4, 0.09)])
    def test_crit_panel_by_pieces(self, pieces, cr):
        eng = _make("313", pieces)
        assert math.isclose(_eff(eng)["crit_rate"], cr, rel_tol=1e-9), "0.05+0.04"

    def test_kill_stacks_and_cap(self):
        """击杀脆皮 → 每层 +0.04 暴伤（1 层 0.54 / 2 层 0.58）；再补 12 发 on_kill
        事件钳 10 层 → 0.5+0.40=0.90."""
        eng = _make("313", 2, squishy=2)
        st = eng.state.actors["w"]
        _cast(eng, "w", "t_basic", "s1")
        assert not eng.state.actors["s1"].alive, "脆皮被击杀"
        assert math.isclose(st.modifiers["SET_313_KILL_CRIT_DMG"].stacks, 1.0)
        assert math.isclose(_eff(eng)["crit_dmg"], 0.54, rel_tol=1e-9)
        _cast(eng, "w", "t_basic", "s2")
        assert math.isclose(st.modifiers["SET_313_KILL_CRIT_DMG"].stacks, 2.0)
        assert math.isclose(_eff(eng)["crit_dmg"], 0.58, rel_tol=1e-9)
        for _ in range(12):
            eng.bus.emit("on_kill", {"source": "w", "target": "e1",
                                     "action_id": "t_basic"}, eng.state)
        assert math.isclose(st.modifiers["SET_313_KILL_CRIT_DMG"].stacks, 10.0), (
            "max_stack 10 钳顶")
        assert math.isclose(_eff(eng)["crit_dmg"], 0.9, rel_tol=1e-9)

    def test_ally_death_no_stack(self):
        """队友阵亡（非敌方目标）不叠层——actor_type_of 过滤（staging 无过滤旧病回归）."""
        eng = _make("313", 2, with_ally=True)
        st = eng.state.actors["w"]
        a2 = eng.state.actors["a2"]
        a2.current_hp = 0.0
        eng._check_death(a2, "e1")
        assert not a2.alive
        assert "SET_313_KILL_CRIT_DMG" not in st.modifiers, "队友死不叠"

    def test_one_piece_no_stack(self):
        eng = _make("313", 1, squishy=1)
        _cast(eng, "w", "t_basic", "s1")
        assert "SET_313_KILL_CRIT_DMG" not in eng.state.actors["w"].modifiers


class TestSet312Dreamland:
    """312 梦想之地匹诺康尼：2pc 能量恢复效率 +5% + 同属性我方其他角色增伤 10%
    （代数 where 元素过滤；元素面板成员自建——family 模子无 element 槽）."""

    @staticmethod
    def _make312():
        def member(aid, element):
            return {"actor_id": aid, "name": f"装备员{aid}", "inline": True,
                    "element": element,
                    "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
                    "actions": [{"action_id": f"{aid}_basic", "name": "普攻",
                                 "action_type": "basic", "target_type": "single",
                                 "damage_type": element, "scaling": [{"atk": 1.0}],
                                 "toughness_dmg": 10}]}
        wearer = member("w", "fire")
        wearer["relics"] = {f"slot{i}": {"set_id": "312"} for i in range(2)}
        build = {"build": {"team": [wearer, member("a2", "fire"), member("a3", "ice")],
            "policy": {"name": "p", "action_rules": [
                {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100,
             "weakness": ["fire", "ice", "thunder", "wind", "quantum",
                          "imaginary", "physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        return eng

    def test_2pc_energy_regen(self):
        eng = self._make312()
        assert _eff(eng, "w")["energy_regen"] == pytest.approx(1.05)

    def test_same_element_ally_dmg(self):
        """同属性队友（火）+10% 增伤；异属性队友（冰）不挂；装备者自身不挂（其他角色）."""
        eng = self._make312()
        assert _eff(eng, "a2")["dmg_bonus"]["all"] == pytest.approx(0.1)
        # 异属性队友/装备者自身：持件但 enable_if 门死=零贡献（逐受益人判定通道）
        assert _eff(eng, "a3")["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0)
        assert _eff(eng, "w")["dmg_bonus"].get("all", 0.0) == pytest.approx(0.0)
