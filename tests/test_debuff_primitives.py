"""debuff 判定/计数原语（has_debuff/debuff_count/dot_count）+ 逐目标命中域通道单测与收编件族 e2e.

引擎通道（2026-09-16）：
- 三宿主函数（hooks._hook_functions——hook cond / 条件光环 / 目标代数 where 三域同槽，
  hit_condition 命中域经 engine 注入同集）：口径 = 游戏「负面状态」（new_kind 漏斗
  != 'buff'——debuff/dot/control 全计、stacks 不展开）；dot_count = modifier_type=='dot' 严口径
- hit_condition 命中域 `$event.target` 注入（结算点统一并入，payload dict 不含此键）——
  「攻击者对带 debuff 的目标增伤/穿透/暴击」= 命中域 scoped boost（承伤三区通用化同构）
- scoped def_pen（逐目标无视防御，_def_multi_eff 消费——直伤/击破/超击破/欢愉/DoT 跳伤
  全伤害路由）；scoped crit_rate/crit_dmg（目标条件暴击——仅直伤路由，DoT/击破不暴击）；
  DoT 跳伤攻击侧 scoped（增伤/def_pen 跳伤时刻现值——快照只含无条件面板）

口径常数（expected 模式）：attacker lv80 → 防御区 = 1000/(target_def×(1-def_pen)+1000)
（def 1000 → 0.5）；全弱点 → 抗性 1.0；未击破 0.9；期望暴击区 = 1 + min(1,cr)×cd
（cr 0.05 / cd 0.5 → 1.025）。白值：inline 装备员 atk 1000/spd 100/hp 3000/crit 0.05/0.5。
"""
from __future__ import annotations

import math
import types
from pathlib import Path

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim.target_algebra import eval_algebra
from tests.template_materialize import TEST_TEMPLATE_ROOTS

_LC_DIR = Path(__file__).parent / "fixtures" / "templates" / "light_cones"


def _lc_base(lc_id):
    """fixture 实载白值（机制断言手算基数）."""
    f = next(_LC_DIR.glob(f"{lc_id}_*.yaml"))
    return yaml.safe_load(f.read_text(encoding="utf-8"))["base_stats"]


# ---------------------------------------------------------------------------
# 模子（relic/lc e2e 族同形）
# ---------------------------------------------------------------------------

_BASIC = {"action_id": "t_basic", "name": "普攻", "action_type": "basic",
          "target_type": "single", "damage_type": "fire",
          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _member(actor_id="w", *, set_id=None, pieces=0, lc=None, sup=1, path=None,
            element=None, actions=(_BASIC,), spd=100):
    m = {"actor_id": actor_id, "name": f"装备员{actor_id}", "inline": True,
         "base_stats": {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100},
         "actions": list(actions)}
    if set_id is not None:
        m["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    if lc is not None:
        m["light_cone_template"] = lc
        m["light_cone"] = {"superimposition": sup}
    if path:
        m["path"] = path
    if element:
        m["element"] = element
    return m


def _build(member):
    return {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100,
     "weakness": ["fire", "ice", "thunder", "wind", "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

_STAGE2 = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100,
     "weakness": ["fire", "ice", "thunder", "wind", "quantum", "imaginary", "physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100,
     "weakness": ["fire", "ice", "thunder", "wind", "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(member, stage=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(_build(member), stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _cast(eng, owner, aid, target_id="e1"):
    """行动施放模子（_execute_action + on_action 广播，relic/lc e2e 族同形）."""
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


def _hp(eng, aid="e1"):
    return eng.state.actors[aid].current_hp


def _panel(eng, aid="w"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


#: 手挂件模子（debuff/dot/control/buff 四类——new_kind 漏斗全谱）
def _debuff(mid, **kw):
    return Modifier(modifier_id=mid, name=mid, modifier_type="debuff", duration=2, **kw)


def _dot(mid, **kw):
    return Modifier(modifier_id=mid, name=mid, modifier_type="dot", debuff_kind="dot",
                    duration=2, dot_element="fire", dot_ratio=0.5, **kw)


def _control(mid, **kw):
    return Modifier(modifier_id=mid, name=mid, modifier_type="control",
                    debuff_kind="control", duration=2, control_kind="freeze", **kw)


def _buff(mid, **kw):
    return Modifier(modifier_id=mid, name=mid, modifier_type="buff", duration=2, **kw)


# ---------------------------------------------------------------------------
# ① 三函数口径与目标解析通道（ActorState / actor_id / 查无安全缺省）
# ---------------------------------------------------------------------------
class TestPrimitiveFunctions:
    def test_has_debuff_umbrella(self):
        """has_debuff = 游戏「负面状态」伞：debuff/dot/control 全计；buff 不计."""
        eng = _make(_member("w"))
        e1 = eng.state.actors["e1"]
        fns = eng._hooks._hook_functions(eng.state.actors["w"])
        assert fns["has_debuff"](e1) == 0.0
        eng._apply_modifier(e1, _buff("B1"))
        assert fns["has_debuff"](e1) == 0.0, "纯 buff 不算负面"
        for m in (_debuff("D1"), _dot("DOT1"), _control("C1")):
            eng._apply_modifier(e1, m)
        assert fns["has_debuff"](e1) == 1.0

    def test_debuff_count_full_spectrum(self):
        """debuff_count：三类负面全计、buff 不计、stacks 不展开（按实例数）."""
        eng = _make(_member("w"))
        e1 = eng.state.actors["e1"]
        fns = eng._hooks._hook_functions(eng.state.actors["w"])
        eng._apply_modifier(e1, _debuff("D1", stacks=3))   # 3 层仍 1 件
        eng._apply_modifier(e1, _dot("DOT1"))
        eng._apply_modifier(e1, _control("C1"))
        eng._apply_modifier(e1, _buff("B1"))
        assert fns["debuff_count"](e1) == 3.0
        assert fns["dot_count"](e1) == 1.0, "dot_count 严口径——只数 modifier_type=='dot'"

    def test_target_resolution_and_safe_default(self):
        """目标解析与 has_modifier 同通道：ActorState / actor_id 字符串；查无 → 0.0."""
        eng = _make(_member("w"))
        e1 = eng.state.actors["e1"]
        fns = eng._hooks._hook_functions(eng.state.actors["w"])
        eng._apply_modifier(e1, _debuff("D1"))
        assert fns["debuff_count"]("e1") == 1.0
        assert fns["has_debuff"]("e1") == 1.0
        assert fns["dot_count"]("e1") == 0.0
        assert fns["debuff_count"]("nobody") == 0.0
        assert fns["has_debuff"]("nobody") == 0.0
        assert fns["dot_count"]("nobody") == 0.0


# ---------------------------------------------------------------------------
# ② 三语境求值（hook cond / hit_condition / 目标代数 where）
# ---------------------------------------------------------------------------
class TestThreeContexts:
    def test_hook_condition_context(self):
        """hook cond 语境：debuff_count($event.target) 经 _hook_condition_ok 真通道求值."""
        eng = _make(_member("w"))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        h = types.SimpleNamespace(
            condition_expr=eng._expr.compile(
                "debuff_count($event.target) >= 2", layer="effect"),
            owner_id="w", event="on_action")
        payload = {"actor": "w", "target": "e1"}
        eng._apply_modifier(e1, _debuff("D1"))
        assert eng._hooks._hook_condition_ok(h, w, payload) is False
        eng._apply_modifier(e1, _dot("DOT1"))
        assert eng._hooks._hook_condition_ok(h, w, payload) is True

    def test_hit_condition_context(self):
        """hit_condition 语境：scoped 件条件读 $event.target（ActorState 注入）——
        目标带 debuff 才计入增伤；面板域恒忽略 scoped 件."""
        eng = _make(_member("w"))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng._apply_modifier(w, Modifier(
            modifier_id="T_DMG", name="对负面增伤", modifier_type="buff", duration=0,
            stat_effects={"all_dmg": 0.5},
            hit_condition_expr=eng._expr.compile(
                "has_debuff($event.target) > 0", layer="effect")))
        assert math.isclose(_panel(eng)["dmg_bonus"].get("all", 0.0), 0.0), \
            "面板求值一律忽略带 hit_condition 的 modifier（spec 两域语义）"
        act = next(a for a in eng.actions_by_actor["w"] if a.action_id == "t_basic")
        r0 = eng.pipeline.deal_damage(act, w, e1)
        assert math.isclose(r0.node["dmgBoostMulti"], 1.0, rel_tol=1e-9)
        eng._apply_modifier(e1, _dot("DOT1"))
        r1 = eng.pipeline.deal_damage(act, w, e1)
        assert math.isclose(r1.node["dmgBoostMulti"], 1.5, rel_tol=1e-9)

    def test_algebra_where_context(self):
        """目标代数 where 语境：dot_count($it) 逐元素过滤——只命中带 DoT 的敌人."""
        eng = _make(_member("w"), stage=_STAGE2)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        eng._apply_modifier(e1, _dot("DOT1"))
        pool = [e1, e2]
        hit = eval_algebra({"where": "dot_count($it) >= 1"}, pool=pool,
                           engine=eng, expr=eng._expr)
        assert [s.actor.actor_id for s in hit] == ["e1"]
        hit2 = eval_algebra({"where": "debuff_count($it) >= 1"}, pool=pool,
                            engine=eng, expr=eng._expr)
        assert [s.actor.actor_id for s in hit2] == ["e1"]
        eng._apply_modifier(e2, _control("C1"))
        hit3 = eval_algebra({"where": "has_debuff($it) > 0"}, pool=pool,
                            engine=eng, expr=eng._expr)
        assert [s.actor.actor_id for s in hit3] == ["e1", "e2"]


# ---------------------------------------------------------------------------
# ③ scoped def_pen 逐目标（A 目标有 DoT 吃穿透、B 目标没有不吃）
# ---------------------------------------------------------------------------
class TestScopedDefPenPerTarget:
    def test_per_target_resolution(self):
        """同一攻击者同一面板：逐目标命中域判定——穿透只作用于满足条件的目标."""
        eng = _make(_member("w"), stage=_STAGE2)
        w, e1, e2 = (eng.state.actors[i] for i in ("w", "e1", "e2"))
        eng._apply_modifier(w, Modifier(
            modifier_id="T_PEN", name="对 DoT 目标无视防御", modifier_type="buff", duration=0,
            stat_effects={"def_pen": 0.24},
            hit_condition_expr=eng._expr.compile(
                "dot_count($event.target) >= 1", layer="effect")))
        assert math.isclose(_panel(eng)["def_pen"], 0.0), "scoped 件不进面板"
        eng._apply_modifier(e1, _dot("DOT1"))
        act = next(a for a in eng.actions_by_actor["w"] if a.action_id == "t_basic")
        r1 = eng.pipeline.deal_damage(act, w, e1)
        r2 = eng.pipeline.deal_damage(act, w, e2)
        assert math.isclose(r1.node["defMulti"], 1000 / (1000 * 0.76 + 1000), rel_tol=1e-9), \
            "e1 带 1 DoT → def_pen 0.24 生效"
        assert math.isclose(r2.node["defMulti"], 0.5, rel_tol=1e-9), \
            "e2 无 DoT → 穿透不生效（逐目标，不外溢）"

    def test_scoped_def_pen_in_break_route(self):
        """击破路由同通道（_def_multi_eff 消费）：目标带 DoT 时击破伤害吃 scoped 穿透."""
        eng = _make(_member("w"))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng._apply_modifier(w, Modifier(
            modifier_id="T_PEN", name="对 DoT 目标无视防御", modifier_type="buff", duration=0,
            stat_effects={"def_pen": 0.24},
            hit_condition_expr=eng._expr.compile(
                "dot_count($event.target) >= 1", layer="effect")))
        r0 = eng.pipeline.break_damage(w, e1, "fire")
        assert math.isclose(r0.node["defMulti"], 0.5, rel_tol=1e-9)
        eng._apply_modifier(e1, _dot("DOT1"))
        r1 = eng.pipeline.break_damage(w, e1, "fire")
        assert math.isclose(r1.node["defMulti"], 1000 / (1000 * 0.76 + 1000), rel_tol=1e-9)


# ---------------------------------------------------------------------------
# ④ scoped crit 目标条件暴击（仅直伤路由）
# ---------------------------------------------------------------------------
class TestScopedCrit:
    def test_scoped_crit_rate_and_dmg(self):
        """按目标 debuff 数的双暴：≥2 → crit_rate +0.5；≥3 → crit_dmg 再 +1.0（期望区对轴）."""
        eng = _make(_member("w"))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng._apply_modifier(w, Modifier(
            modifier_id="T_CR", name="对负面暴击率", modifier_type="buff", duration=0,
            stat_effects={"crit_rate": 0.5},
            hit_condition_expr=eng._expr.compile(
                "debuff_count($event.target) >= 2", layer="effect")))
        eng._apply_modifier(w, Modifier(
            modifier_id="T_CD", name="对多负面暴伤", modifier_type="buff", duration=0,
            stat_effects={"crit_dmg": 1.0},
            hit_condition_expr=eng._expr.compile(
                "debuff_count($event.target) >= 3", layer="effect")))
        assert math.isclose(_panel(eng)["crit_rate"], 0.05)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5)
        act = next(a for a in eng.actions_by_actor["w"] if a.action_id == "t_basic")
        r0 = eng.pipeline.deal_damage(act, w, e1)
        assert math.isclose(r0.node["critMulti"], 1.025, rel_tol=1e-9)
        eng._apply_modifier(e1, _debuff("D1"))
        eng._apply_modifier(e1, _debuff("D2"))
        r2 = eng.pipeline.deal_damage(act, w, e1)
        # cr 0.55 / cd 0.5 → 1 + 0.55×0.5 = 1.275
        assert math.isclose(r2.node["critMulti"], 1 + 0.55 * 0.5, rel_tol=1e-9)
        eng._apply_modifier(e1, _dot("DOT1"))
        r3 = eng.pipeline.deal_damage(act, w, e1)
        # cr 0.55 / cd 1.5 → 1 + 0.55×1.5 = 1.825
        assert math.isclose(r3.node["critMulti"], 1 + 0.55 * 1.5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# ⑤ 收编 e2e：116 幽锁深牢的系囚 4pc（按目标 DoT 数无视防御，6%/个上限 3）
# ---------------------------------------------------------------------------
class TestRelic116Collected:
    def test_4pc_def_pen_scales_with_dots(self):
        """0/1/3/4 DoT → def_pen 0/6%/18%/18%（上限 3 个）；atk 1120（2pc 攻击 +12%）."""
        eng = _make(_member("w", set_id="116", pieces=4))
        e1 = eng.state.actors["e1"]
        atk = 1120.0
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * 1.025), "无 DoT 不吃穿透"
        eng._apply_modifier(e1, _dot("DOT1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(
            atk * (1000 / (1000 * 0.94 + 1000)) * 0.9 * 1.025), "1 DoT → 无视 6%"
        for mid in ("DOT2", "DOT3"):
            eng._apply_modifier(e1, _dot(mid))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(
            atk * (1000 / (1000 * 0.82 + 1000)) * 0.9 * 1.025), "3 DoT → 无视 18%"
        eng._apply_modifier(e1, _dot("DOT4"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(
            atk * (1000 / (1000 * 0.82 + 1000)) * 0.9 * 1.025), "4 DoT → 封顶 3 个仍 18%"

    def test_4pc_per_target(self):
        """逐目标：e1 带 3 DoT 吃 18%，e2 无 DoT 不吃（同一攻击者不逐面板外溢）."""
        eng = _make(_member("w", set_id="116", pieces=4), stage=_STAGE2)
        e1 = eng.state.actors["e1"]
        for mid in ("DOT1", "DOT2", "DOT3"):
            eng._apply_modifier(e1, _dot(mid))
        atk = 1120.0
        before = _hp(eng)
        _cast(eng, "w", "t_basic", "e1")
        assert before - _hp(eng) == pytest.approx(
            atk * (1000 / (1000 * 0.82 + 1000)) * 0.9 * 1.025)
        before = _hp(eng, "e2")
        _cast(eng, "w", "t_basic", "e2")
        assert before - _hp(eng, "e2") == pytest.approx(atk * 0.5 * 0.9 * 1.025)

    def test_4pc_dot_tick_also_penetrates(self):
        """「对其造成伤害时」含 DoT 跳伤：装备者施加的 DoT 跳伤时刻按目标 DoT 数吃穿透."""
        eng = _make(_member("w", set_id="116", pieces=4))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        # 装备者施加 DoT（快照含有效攻击 1120 ×0.5）；再补 2 个 DoT → 共 3 个
        eng._apply_modifier_spec(e1, {
            "modifier_id": "DOT_W", "name": "触电", "modifier_type": "dot", "duration": 2,
            "dot_element": "thunder", "dot_ratio": 0.5}, w)
        eng._apply_modifier(e1, _dot("DOT2"))
        eng._apply_modifier(e1, _dot("DOT3"))
        before = _hp(eng)
        eng._tick_dots(e1)
        # 跳伤 = (1120×0.5) × 1.0(增伤快照) × (1000/1820) × 1.0(抗) × 0.9(未击破) × 1.0(ehr)
        assert before - _hp(eng) == pytest.approx(
            (1120.0 * 0.5) * (1000 / (1000 * 0.82 + 1000)) * 0.9)

    def test_2pc_no_pen(self):
        """2 件无 4pc——3 DoT 也不吃穿透."""
        eng = _make(_member("w", set_id="116", pieces=2))
        e1 = eng.state.actors["e1"]
        for mid in ("DOT1", "DOT2", "DOT3"):
            eng._apply_modifier(e1, _dot(mid))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(1120.0 * 0.5 * 0.9 * 1.025)


# ---------------------------------------------------------------------------
# ⑥ 收编 e2e：117 死水深潜的先驱 2pc（对负面目标增伤 12%）+ 4pc 暴伤半
# ---------------------------------------------------------------------------
class TestRelic117Collected:
    def test_2pc_dmg_vs_debuffed(self):
        """2pc：目标持任一 debuff → 增伤 +12%；干净目标不吃；面板增伤恒 0（scoped）."""
        eng = _make(_member("w", set_id="117", pieces=2))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["dmg_bonus"].get("all", 0.0), 0.0)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(1000 * 0.5 * 0.9 * 1.025), "干净目标不吃"
        eng._apply_modifier(e1, _dot("DOT1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * 1.025), \
            "DoT 亦属负面——吃 +12%"

    def test_4pc_crit_dmg_tiers(self):
        """4pc 暴伤半：≥2 负面 cd +8%、≥3 再 +4%（面板 cd 恒 0.5——scoped 不进面板）；
        2pc 同场生效（目标带负面 → 增伤 +12%）；暴击率面板 0.09."""
        eng = _make(_member("w", set_id="117", pieces=4))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["crit_rate"], 0.09)
        assert math.isclose(_panel(eng)["crit_dmg"], 0.5)
        eng._apply_modifier(e1, _debuff("D1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 1 负面：2pc +12% 生效；暴伤不加（<2）→ 期望暴击区 1+0.09×0.5
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * (1 + 0.09 * 0.5))
        eng._apply_modifier(e1, _debuff("D2"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 2 负面：cd 0.58 → 1+0.09×0.58
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * (1 + 0.09 * 0.58))
        eng._apply_modifier(e1, _dot("DOT1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 3 负面：cd 0.62 → 1+0.09×0.62
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * (1 + 0.09 * 0.62))

    def test_4pc_double_also_doubles_crit_dmg(self):
        """施减益翻倍：负面施加（装备者源——debuff 与 DoT 同伞口径）→ 翻倍三件套
        （暴击率 +4%、暴伤 ≥2 +8%/≥3 +4%），持续 1 回合."""
        eng = _make(_member("w", set_id="117", pieces=4))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng._apply_modifier(e1, _dot("DOT1", source_id="w"))
        mods = eng.state.actors["w"].modifiers
        assert "SET_117_4PC_DOUBLE" in mods, "DoT 施加同属「施加负面效果」——翻倍亦触发"
        assert "SET_117_4PC_DOUBLE_CD2" in mods and "SET_117_4PC_DOUBLE_CD3" in mods
        assert mods["SET_117_4PC_DOUBLE_CD2"].duration == 1
        eng._apply_modifier(e1, _debuff("D1", source_id="w"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 2 负面 + 翻倍：cr 0.13 / cd 0.5+0.08+0.08=0.66 → 1+0.13×0.66
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * (1 + 0.13 * 0.66))
        eng._apply_modifier(e1, _debuff("D2", source_id="w"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 3 负面 + 翻倍：cd 0.5+0.12+0.12=0.74 → 1+0.13×0.74
        assert before - _hp(eng) == pytest.approx(1000 * 1.12 * 0.5 * 0.9 * (1 + 0.13 * 0.74))


# ---------------------------------------------------------------------------
# ⑦ 收编 e2e：21001 晚安与睡颜（按目标负面数增伤，#1/个上限 3——含持续伤害）
# ---------------------------------------------------------------------------
class TestLC21001Collected:
    def test_dmg_scales_with_debuffs_s1(self):
        """S1（#1=0.12）：0/1/3/4 负面 → ×1.00/1.12/1.36/1.36（上限 3）；面板增伤恒 0."""
        atk = 1000 + _lc_base("21001")["atk"]      # 1476.28
        eng = _make(_member("w", lc="21001", sup=1, path="nihility"))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["dmg_bonus"].get("all", 0.0), 0.0)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * 1.025)
        eng._apply_modifier(e1, _debuff("D1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 1.12 * 0.5 * 0.9 * 1.025)
        for mid in ("DOT1", "C1"):
            eng._apply_modifier(e1, (_dot if mid == "DOT1" else _control)(mid))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 1.36 * 0.5 * 0.9 * 1.025), \
            "3 负面（debuff+dot+control 全计）→ 满层 36%"
        eng._apply_modifier(e1, _debuff("D2"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 1.36 * 0.5 * 0.9 * 1.025), "4 负面封顶"

    def test_dmg_s5(self):
        """S5（#1=0.24）：3 负面 → ×1.72."""
        atk = 1000 + _lc_base("21001")["atk"]
        eng = _make(_member("w", lc="21001", sup=5, path="nihility"))
        e1 = eng.state.actors["e1"]
        for m in (_debuff("D1"), _debuff("D2"), _dot("DOT1")):
            eng._apply_modifier(e1, m)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 1.72 * 0.5 * 0.9 * 1.025)

    def test_dot_tick_also_boosted(self):
        """「该效果对持续伤害也会生效」：装备者施加的 DoT 跳伤时刻按目标负面数吃增伤."""
        atk = 1000 + _lc_base("21001")["atk"]
        eng = _make(_member("w", lc="21001", sup=1, path="nihility"))
        w, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng._apply_modifier_spec(e1, {
            "modifier_id": "DOT_W", "name": "触电", "modifier_type": "dot", "duration": 2,
            "dot_element": "thunder", "dot_ratio": 0.5}, w)
        before = _hp(eng)
        eng._tick_dots(e1)
        # 1 负面（DoT 自身）→ ×1.12：跳伤 = (atk×0.5) × 1.12 × 0.5 × 0.9（快照增伤区 1.0）
        assert before - _hp(eng) == pytest.approx((atk * 0.5) * 1.12 * 0.5 * 0.9)
        eng._apply_modifier(e1, _debuff("D1"))
        eng._apply_modifier(e1, _debuff("D2"))
        before = _hp(eng)
        eng._tick_dots(e1)
        # 3 负面 → ×1.36（跳伤时刻现值——快照外的逐目标条件件）
        assert before - _hp(eng) == pytest.approx((atk * 0.5) * 1.36 * 0.5 * 0.9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_member("w", lc="21001", sup=1, path="destruction"))
        e1 = eng.state.actors["e1"]
        eng._apply_modifier(e1, _debuff("D1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        atk = 1000 + _lc_base("21001")["atk"]
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * 1.025)
        assert not [m for m in eng.state.actors["w"].modifiers if m.startswith("LC_21001")]


# ---------------------------------------------------------------------------
# ⑧ 收编 e2e：23007 雨一直下暴击半（对 ≥3 负面目标暴击率 +#5）
# ---------------------------------------------------------------------------
class TestLC23007Collected:
    def test_crit_rate_vs_3_debuffs_s1(self):
        """S1（#5=0.12，#4 恒 3）：<3 负面期望暴击区 1.025；≥3 → cr 0.17 → 1.085."""
        atk = 1000 + _lc_base("23007")["atk"]      # 1582.12
        eng = _make(_member("w", lc="23007", sup=1, path="nihility"))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["crit_rate"], 0.05), "scoped 件不进面板"
        eng._apply_modifier(e1, _debuff("D1"))
        eng._apply_modifier(e1, _dot("DOT1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * 1.025), "2 负面不加暴击率"
        eng._apply_modifier(e1, _control("C1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 3 负面 → 暴击率 +12%（cr 0.17）；首击已挂以太编码（亦计负面 + 易伤 +12%）→ ×1.12
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.17 * 0.5) * 1.12)

    def test_crit_rate_s5(self):
        """S5（#5=0.20）：3 负面 → cr 0.25 → 期望区 1.125；以太编码持有亦计负面."""
        atk = 1000 + _lc_base("23007")["atk"]
        eng = _make(_member("w", lc="23007", sup=5, path="nihility"))
        e1 = eng.state.actors["e1"]
        for m in (_debuff("D1"), _debuff("D2"), _dot("DOT1")):
            eng._apply_modifier(e1, m)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.25 * 0.5))


# ---------------------------------------------------------------------------
# ⑨ 收编 e2e：23020 纯粹思维的洗礼 #2/#3（按敌方负面数加暴伤，#2/个上限 #3=3）
# ---------------------------------------------------------------------------
class TestLC23020Collected:
    def test_crit_dmg_scales_with_debuffs_s1(self):
        """S1（#1=0.20、#2=0.08）：面板 cd 0.7；1/3 负面 → 命中 cd 0.78/0.94."""
        atk = 1000 + _lc_base("23020")["atk"]      # 1582.12
        eng = _make(_member("w", lc="23020", sup=1, path="hunt"))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["crit_dmg"], 0.7), "常驻暴伤 +20%（#1）；scoped 不进面板"
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.05 * 0.7))
        eng._apply_modifier(e1, _dot("DOT1"))
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.05 * 0.78))
        for m in (_debuff("D1"), _debuff("D2"), _debuff("D3")):
            eng._apply_modifier(e1, m)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        # 4 负面封顶 3 层 → cd 0.7+3×0.08=0.94
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.05 * 0.94))

    def test_crit_dmg_s5(self):
        """S5（#1=0.32、#2=0.12）：2 负面 → cd 0.82+2×0.12=1.06."""
        atk = 1000 + _lc_base("23020")["atk"]
        eng = _make(_member("w", lc="23020", sup=5, path="hunt"))
        e1 = eng.state.actors["e1"]
        assert math.isclose(_panel(eng)["crit_dmg"], 0.82)
        for m in (_debuff("D1"), _dot("DOT1")):
            eng._apply_modifier(e1, m)
        before = _hp(eng)
        _cast(eng, "w", "t_basic")
        assert before - _hp(eng) == pytest.approx(atk * 0.5 * 0.9 * (1 + 0.05 * 1.06))
