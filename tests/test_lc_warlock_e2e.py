"""虚无（Warlock）光锥族 e2e：staging→fixtures 验收批.

24 件验收 fixture（tests/fixtures/templates/light_cones/）→ 编译 → 白值/机制/命途门控/
叠影差分手算对轴；勘正条目见各 fixture 头注。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / crit 0.05/0.5（期望暴击区
1+cr×cd）、level 80（默认）；假人 def 1000 → 防御区 0.5、全弱点 → 抗性区 1.0、
未击破 0.9。白值说明：fixture 白值区 = **官方正确值**（pipeline.calc_light_cone_stats
promo_levels 缺 (70,80) 段之病 2026-09-15 已修复——lv80 取 A6 base+step×79，23007
实证 1058.4/582.12/463.05 与官方全等；staging 生成器旧值（A5 基底）待重生成同步，
fixture 未采用病值——验收时已按官方源写入正确值）。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

_LC_DIR = Path(__file__).parent / "fixtures" / "templates" / "light_cones"

_IDS = ["20004", "20011", "20018", "21001", "21008", "21015", "21022", "21029",
        "21041", "21044", "21061", "22000", "23004", "23006", "23007", "23022",
        "23024", "23029", "23035", "23043", "23047", "23050", "23059", "24003"]

#: 官方 lv80 白值（light_cone_promotions A6 base + step×79 手算；fandom 23007 对轴）
_OFFICIAL = {
    "20004": (846.72, 317.52, 264.6),
    "20011": (846.72, 317.52, 264.6),
    "20018": (846.72, 317.52, 264.6),
    "21001": (952.56, 476.28, 330.75),
    "21008": (952.56, 476.28, 330.75),
    "21022": (952.56, 476.28, 330.75),
    "21015": (952.56, 476.28, 330.75),
    "21029": (846.72, 529.2, 330.75),
    "21041": (1058.4, 476.28, 264.6),
    "21044": (952.56, 476.28, 330.75),
    "21061": (1058.4, 529.2, 330.75),
    "22000": (952.56, 476.28, 330.75),
    "23004": (1058.4, 582.12, 463.05),
    "23006": (1058.4, 582.12, 463.05),
    "23007": (1058.4, 582.12, 463.05),
    "23022": (1058.4, 582.12, 463.05),
    "23024": (1058.4, 635.04, 396.9),
    "23029": (952.56, 582.12, 529.2),
    "23035": (952.56, 476.28, 661.5),
    "23043": (952.56, 582.12, 529.2),
    "23047": (952.56, 635.04, 463.05),
    "23050": (1164.24, 529.2, 463.05),
    "23059": (1375.92, 423.36, 463.05),
    "24003": (1058.4, 529.2, 396.9),
}


def _lc_base(lc_id):
    """fixture 实载白值（生成器值——机制断言手算基数）."""
    f = next(_LC_DIR.glob(f"{lc_id}_*.yaml"))
    return yaml.safe_load(f.read_text(encoding="utf-8"))["base_stats"]


def _basic(aid="t_basic", **kw):
    a = {"action_id": aid, "name": "普攻", "action_type": "basic",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}
    a.update(kw)
    return a


def _skill(aid="t_skill", **kw):
    a = {"action_id": aid, "name": "战技", "action_type": "skill",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 1.0}], "toughness_dmg": 20}
    a.update(kw)
    return a


def _ult(aid="t_ult", **kw):
    a = {"action_id": aid, "name": "终结技", "action_type": "ultimate",
         "target_type": "single", "damage_type": "fire",
         "scaling": [{"atk": 2.0}], "toughness_dmg": 30, "energy_cost": 100}
    a.update(kw)
    return a


def _member(lc_id, *, sup=1, path="nihility", spd=100, actions=None, aid="w",
            extra_stats=None, element="fire"):
    stats = {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100}
    stats.update(extra_stats or {})
    m = {"actor_id": aid, "name": f"装备员{aid}", "inline": True, "element": element,
         "base_stats": stats,
         "actions": actions if actions is not None else [_basic(f"{aid}_basic")]}
    if lc_id is not None:
        m["light_cone_template"] = lc_id
        m["light_cone"] = {"superimposition": sup}
    if path:
        m["path"] = path
    return m


def _build(members):
    return {"build": {"team": list(members),
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

_STAGE2 = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire", "ice", "thunder", "wind",
                                       "quantum", "imaginary", "physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _make(build, stage=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage or _STAGE, template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _cast(eng, owner, aid, target_id="e1"):
    """手动施放（8009 模子）：行动结算 + 补发 on_action（hook 触发域）."""
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


def _fire_ult(eng, owner, aid="t_ult"):
    st = eng.state.actors[owner]
    st.current_energy = float(st.actor.stats.max_energy)
    ult = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


# ---------------------------------------------------------------------------
# 白值三围：官方值锚（生成器病已修——见模块头注；原 xfail 锚验收合格转正）
# ---------------------------------------------------------------------------
class TestWhiteStatsOfficial:
    @pytest.mark.parametrize("lc_id", _IDS)
    def test_official_white_stats(self, lc_id):
        hp, atk, dfn = _OFFICIAL[lc_id]
        eng = _make(_build([_member(lc_id)]))
        eff = _eff(eng, "w")
        # 23059 机制含 hp_pct +30%（S1）——面板 = (角色+光锥白值)×1.3，基数同官方白值
        want_hp = (3000 + hp) * 1.3 if lc_id == "23059" else 3000 + hp
        assert math.isclose(eff["hp"], want_hp, rel_tol=1e-9), f"{lc_id} hp"
        assert math.isclose(eff["atk"], 1000 + atk, rel_tol=1e-9), f"{lc_id} atk"
        assert math.isclose(eff["def_"], dfn, rel_tol=1e-9), f"{lc_id} def"

    @pytest.mark.parametrize("lc_id", _IDS)
    def test_fixture_white_stats_pinned(self, lc_id):
        """fixture 白值区 = 官方正确值（与 _OFFICIAL 锚对偶——防手滑钉住）."""
        base = _lc_base(lc_id)
        hp, atk, dfn = _OFFICIAL[lc_id]
        assert math.isclose(base["hp"], hp, rel_tol=1e-9), f"{lc_id} fixture hp"
        assert math.isclose(base["atk"], atk, rel_tol=1e-9), f"{lc_id} fixture atk"
        assert math.isclose(base["def"], dfn, rel_tol=1e-9), f"{lc_id} fixture def"


# ---------------------------------------------------------------------------
# 20004 幽邃：战斗开始效果命中+3 回合
# ---------------------------------------------------------------------------
class TestLC20004:
    def test_ehr_s1_and_duration(self):
        eng = _make(_build([_member("20004", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.2, rel_tol=1e-9)
        assert _mods(eng, "w")["LC_20004_VOID_EHR"].duration == 3, "官方#2恒3回合"

    def test_ehr_s5(self):
        eng = _make(_build([_member("20004", sup=5)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.4, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("20004", path="destruction")]))
        assert "LC_20004_VOID_EHR" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 21008 猎物的视线：效果命中常驻（DoT 增伤半待收——dot 零乘区 B27#3）
# ---------------------------------------------------------------------------
class TestLC21008:
    def test_ehr_s1(self):
        eng = _make(_build([_member("21008", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.2, rel_tol=1e-9)

    def test_ehr_s5(self):
        eng = _make(_build([_member("21008", sup=5)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.4, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("21008", path="hunt")]))
        assert "LC_21008_PREY_SIGHT" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 21015 决心如汗珠般闪耀：击中挂【攻陷】减防
# ---------------------------------------------------------------------------
class TestLC21015:
    def test_ensnare_def_down_s1(self):
        """S1：基础概率 60%（expected ≥0.5 恒触发）→ 攻陷 def_pct −0.12 → 假人 880."""
        eng = _make(_build([_member("21015", sup=1)]))
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        assert "LC_21015_ENSNARE" in e1.modifiers
        assert math.isclose(_eff(eng, "e1")["def_"], 1000 * 0.88, rel_tol=1e-9)
        assert e1.modifiers["LC_21015_ENSNARE"].duration == 1, "官方#3恒1回合"

    def test_ensnare_no_reapply_while_present(self):
        """目标已持攻陷 → 判据断路（官方「如果该目标不处于【攻陷】状态」）."""
        eng = _make(_build([_member("21015", sup=1)]))
        _cast(eng, "w", "w_basic")
        mod = eng.state.actors["e1"].modifiers["LC_21015_ENSNARE"]
        _cast(eng, "w", "w_basic")
        assert eng.state.actors["e1"].modifiers["LC_21015_ENSNARE"] is mod, (
            "攻陷在场不重挂（同实例保持）")

    def test_ensnare_def_down_s5(self):
        eng = _make(_build([_member("21015", sup=5)]))
        _cast(eng, "w", "w_basic")
        assert math.isclose(_eff(eng, "e1")["def_"], 1000 * 0.84, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("21015", path="erudition")]))
        _cast(eng, "w", "w_basic")
        assert "LC_21015_ENSNARE" not in eng.state.actors["e1"].modifiers


# ---------------------------------------------------------------------------
# 21029 后会有期：普攻/战技后附加伤害
# ---------------------------------------------------------------------------
class TestLC21029:
    def test_additional_dmg_s1(self):
        """S1：普攻 1.0 + 附加 0.48（附加伤害=装备者火属性，假人全弱点抗性 1.0）."""
        atk = 1000 + _lc_base("21029")["atk"]     # 1490.8（生成器值）
        eng = _make(_build([_member("21029", sup=1)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * 1.48 * z, rel_tol=1e-9)

    def test_additional_dmg_s5(self):
        atk = 1000 + _lc_base("21029")["atk"]
        eng = _make(_build([_member("21029", sup=5)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * 1.96 * z, rel_tol=1e-9)

    def test_ultimate_not_triggered(self):
        """官方限定普攻/战技——终结技后无附加段."""
        atk = 1000 + _lc_base("21029")["atk"]
        eng = _make(_build([_member("21029", sup=1,
                                    actions=[_basic("w_basic"), _ult("w_ult")])]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _fire_ult(eng, "w", "w_ult")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, 2.0 * atk * z, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        atk = 1000 + _lc_base("21029")["atk"]
        eng = _make(_build([_member("21029", path="destruction")]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "无附加段"


# ---------------------------------------------------------------------------
# 21041 好戏开演：戏法叠层增伤 + EHR≥80% 增攻
# ---------------------------------------------------------------------------
def _debuff_skill(aid="w_skill"):
    """施加 debuff 的测试战技（戏法触发载体——通用 def_pct 减防件）."""
    return _skill(aid, apply_modifiers=[{
        "target": "all_enemies", "modifier_id": "TEST_DEBUFF", "name": "测试减益",
        "modifier_type": "debuff", "duration": 2, "stat_effects": {"def_pct": -0.1}}])


class TestLC21041:
    def test_trick_stacks_and_dmg(self):
        """戏法：每施加 1 个 debuff +1 层（cap 3），每层 all_dmg +6%（S1 stat_exprs 动态）."""
        eng = _make(_build([_member("21041", sup=1, actions=[_debuff_skill()])]))
        for want_stacks, want_dmg in ((1, 0.06), (2, 0.12), (3, 0.18), (3, 0.18)):
            _cast(eng, "w", "w_skill")
            mod = _mods(eng, "w")["LC_21041_TRICK"]
            assert mod.stacks == want_stacks, f"层数 {want_stacks}"
            assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], want_dmg,
                                rel_tol=1e-9)

    def test_ehr_gated_atk(self):
        """EHR ≥ 80%（S1 param_4 恒值）→ atk +20%：0.8 触发 / 0.7 不触发（enable_if 门控）."""
        atk_lc = _lc_base("21041")["atk"]          # 441.72（生成器值）
        eng_on = _make(_build([_member("21041", sup=1, extra_stats={"effect_hit": 0.8})]))
        assert math.isclose(_eff(eng_on, "w")["atk"], (1000 + atk_lc) * 1.2, rel_tol=1e-9)
        eng_off = _make(_build([_member("21041", sup=1, extra_stats={"effect_hit": 0.7})]))
        assert math.isclose(_eff(eng_off, "w")["atk"], 1000 + atk_lc, rel_tol=1e-9)

    def test_ehr_gated_atk_s5(self):
        atk_lc = _lc_base("21041")["atk"]
        eng = _make(_build([_member("21041", sup=5, extra_stats={"effect_hit": 0.9})]))
        assert math.isclose(_eff(eng, "w")["atk"], (1000 + atk_lc) * 1.36, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("21041", path="harmony",
                                    actions=[_debuff_skill()],
                                    extra_stats={"effect_hit": 0.9})]))
        _cast(eng, "w", "w_skill")
        assert "LC_21041_TRICK" not in _mods(eng, "w")
        assert "LC_21041_ATK_EHR" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 21044 无边曼舞：暴击率常驻（防御降低/减速目标暴伤半待收）
# ---------------------------------------------------------------------------
class TestLC21044:
    def test_crit_rate_s1(self):
        eng = _make(_build([_member("21044", sup=1)]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05 + 0.08, rel_tol=1e-9)

    def test_crit_rate_s5(self):
        eng = _make(_build([_member("21044", sup=5)]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05 + 0.16, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("21044", path="preservation")]))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21061 假日浴场大冒险：增伤常驻 + 攻击后易伤
# ---------------------------------------------------------------------------
class TestLC21061:
    def test_all_dmg_and_vulnerability_s1(self):
        """S1：all_dmg +16% 常驻；攻击后目标易伤 +10%（100% 基础概率恒挂）."""
        atk = 1000 + _lc_base("21061")["atk"]     # 1490.8（生成器值）
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("21061", sup=1)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.16, rel_tol=1e-9), (
            "首发：增伤区 1.16、目标尚无缝伤")
        assert "LC_21061_VULNERABILITY" in e1.modifiers
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.16 * 1.1, rel_tol=1e-9), (
            "次发：易伤区 1.1 同吃")

    def test_vulnerability_s5(self):
        atk = 1000 + _lc_base("21061")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("21061", sup=5)]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.32 * 1.16, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        atk = 1000 + _lc_base("21061")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("21061", path="abundance")]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9)
        assert "LC_21061_VULNERABILITY" not in e1.modifiers


# ---------------------------------------------------------------------------
# 22000 新手任务开始前：效果命中常驻（减防目标回能半待收）
# ---------------------------------------------------------------------------
class TestLC22000:
    def test_ehr_s1(self):
        eng = _make(_build([_member("22000", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.2, rel_tol=1e-9)

    def test_ehr_s5(self):
        eng = _make(_build([_member("22000", sup=5)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.4, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("22000", path="hunt")]))
        assert "LC_22000_EFFECT_HIT" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23004 以世界之名：战技此次攻击增益（负面目标增伤半待收）
# ---------------------------------------------------------------------------
class TestLC23004:
    def test_skill_window_buff_s1(self):
        """S1：战技伤害前挂 atk +24%（on_become_target）→ 结算后摘（on_action）."""
        atk_lc = _lc_base("23004")["atk"]         # 539.88（生成器值）
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23004", sup=1, actions=[_skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_skill")
        assert math.isclose(hp1 - e1.current_hp, (1000 + atk_lc) * 1.24 * z, rel_tol=1e-9), (
            "战技本发吃增益——伤害前挂实证")
        assert "LC_23004_SKILL_BUFF" not in _mods(eng, "w"), "结算后摘除"
        assert math.isclose(_eff(eng, "w")["atk"], 1000 + atk_lc, rel_tol=1e-9)

    def test_skill_window_buff_s5(self):
        atk_lc = _lc_base("23004")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23004", sup=5, actions=[_skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_skill")
        assert math.isclose(hp1 - e1.current_hp, (1000 + atk_lc) * 1.4 * z, rel_tol=1e-9)

    def test_basic_no_buff(self):
        """普攻非战技——不挂增益."""
        atk_lc = _lc_base("23004")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23004", sup=1)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, (1000 + atk_lc) * z, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        atk_lc = _lc_base("23004")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23004", path="hunt", actions=[_skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_skill")
        assert math.isclose(hp1 - e1.current_hp, (1000 + atk_lc) * z, rel_tol=1e-9)
        assert "LC_23004_SKILL_BUFF" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23007 雨一直下：效果命中常驻 + 以太编码（≥3debuff 暴击半待收）
# ---------------------------------------------------------------------------
class TestLC23007:
    def test_ehr_s1(self):
        eng = _make(_build([_member("23007", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.24, rel_tol=1e-9)

    def test_aether_code_and_vuln_s1(self):
        """S1：普攻后随机 1 个未持有受击目标挂【以太编码】→ 次击吃易伤 +12%."""
        atk = 1000 + _lc_base("23007")["atk"]     # 1539.88（生成器值）
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23007", sup=1)]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        assert "LC_23007_AETHER_CODE" in e1.modifiers
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.12, rel_tol=1e-9)

    def test_aether_code_count_per_action(self):
        """每次施放攻击挂 1 个（计数严格）：双假人 AoE 战技 → 全场恰 1 码；再放 → 第 2 个."""
        eng = _make(_build([_member("23007", sup=1,
                                    actions=[_skill("w_aoe", target_type="aoe")])]),
                    stage=_STAGE2)
        _cast(eng, "w", "w_aoe")
        coded = [t for t in ("e1", "e2") if "LC_23007_AETHER_CODE" in _mods(eng, t)]
        assert len(coded) == 1, "一次攻击恰挂 1 个以太编码"
        _cast(eng, "w", "w_aoe")
        coded2 = [t for t in ("e1", "e2") if "LC_23007_AETHER_CODE" in _mods(eng, t)]
        assert len(coded2) == 2, "未持有者补挂第 2 个（全场编满后空池不再挂）"

    def test_aether_code_vuln_s5(self):
        atk = 1000 + _lc_base("23007")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23007", sup=5)]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.2, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23007", path="destruction")]))
        _cast(eng, "w", "w_basic")
        assert "LC_23007_AETHER_CODE" not in eng.state.actors["e1"].modifiers
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 23022 重塑时光之忆：效果命中常驻（先知叠层整族待收）
# ---------------------------------------------------------------------------
class TestLC23022:
    def test_ehr_s1(self):
        eng = _make(_build([_member("23022", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.4, rel_tol=1e-9)

    def test_ehr_s5(self):
        eng = _make(_build([_member("23022", sup=5)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.6, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23022", path="remembrance")]))
        assert "LC_23022_EFFECT_HIT" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23024 行于流逝的岸：暴伤常驻 + 泡影 + 泡影增伤（真伤压缩）
# ---------------------------------------------------------------------------
class TestLC23024:
    def test_crit_dmg_s1(self):
        eng = _make(_build([_member("23024", sup=1)]))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5 + 0.36, rel_tol=1e-9)

    def test_mirage_and_dmg_boost_s1(self):
        """S1：首击挂【泡影】（本击不吃）；次击真伤压缩 +24%（暴伤 0.86 → 期望区 1.043）."""
        atk = 1000 + _lc_base("23024")["atk"]     # 1588.96（生成器值）
        z = 0.5 * 0.9 * (1 + 0.05 * 0.86)
        eng = _make(_build([_member("23024", sup=1)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "首击无增伤"
        assert "LC_23024_MIRAGE_FIZZLE" in e1.modifiers
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.24, rel_tol=1e-9), (
            "次击 = 原伤害 ×1.24（真伤压缩严格等价）")

    def test_ult_extra_boost_s1(self):
        """终结技对泡影目标额外 +24%（与通用 +24% 叠合 = ×1.48）."""
        atk = 1000 + _lc_base("23024")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.86)
        eng = _make(_build([_member("23024", sup=1,
                                    actions=[_basic("w_basic"), _ult("w_ult")])]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")   # 先挂泡影
        hp1 = e1.current_hp
        _fire_ult(eng, "w", "w_ult")
        assert math.isclose(hp1 - e1.current_hp, 2.0 * atk * z * 1.48, rel_tol=1e-9)

    def test_mirage_boost_s5(self):
        atk = 1000 + _lc_base("23024")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * (0.5 + 0.6))
        eng = _make(_build([_member("23024", sup=5)]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.4, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        atk = 1000 + _lc_base("23024")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23024", path="hunt")]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9)
        assert "LC_23024_MIRAGE_FIZZLE" not in e1.modifiers
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23029 那无数个春天：效果命中常驻 + 卸甲（穷寇升级半待收）
# ---------------------------------------------------------------------------
class TestLC23029:
    def test_ehr_and_unarmored_s1(self):
        """S1：EHR +60%；60% 基础概率（expected 恒触发）→ 卸甲易伤 +10%."""
        atk = 1000 + _lc_base("23029")["atk"]     # 1539.88（生成器值）
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23029", sup=1)]))
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.6, rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        assert "LC_23029_UNARMORED" in e1.modifiers
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.1, rel_tol=1e-9)

    def test_unarmored_s5(self):
        atk = 1000 + _lc_base("23029")["atk"]
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        eng = _make(_build([_member("23029", sup=5)]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_basic")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        assert math.isclose(hp1 - e1.current_hp, atk * z * 1.18, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23029", path="erudition")]))
        _cast(eng, "w", "w_basic")
        assert "LC_23029_UNARMORED" not in eng.state.actors["e1"].modifiers
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 23035 长路终有归途：击破特攻常驻 + 焚灼（击破承伤 scoped）
# ---------------------------------------------------------------------------
class TestLC23035:
    def test_break_effect_s1(self):
        eng = _make(_build([_member("23035", sup=1)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.6, rel_tol=1e-9)

    def test_charring_stacks_and_break_vuln(self):
        """焚灼：击破时挂（恒 100%）→ 击破承伤 +18%/层 cap 2（replace 自指重烘承载，
        scoped 域无 stat_exprs 通道——fixture 头注勘正②）."""
        eng = _make(_build([_member("23035", sup=1)]))
        src, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        base = float(eng.pipeline.break_damage(src, e1, "fire").value)
        ratios = []
        for _ in range(3):
            eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                      "source": "w", "target": "e1"}, eng.state)
            ratios.append(float(eng.pipeline.break_damage(src, e1, "fire").value) / base)
        assert math.isclose(ratios[0], 1.18, rel_tol=1e-9), "1 层 +18%"
        assert math.isclose(ratios[1], 1.36, rel_tol=1e-9), "2 层 +36%"
        assert math.isclose(ratios[2], 1.36, rel_tol=1e-9), "第 3 次钳 2 层（#5 恒 2）"
        assert _mods(eng, "e1")["LC_23035_CHARRING"].duration == 2

    def test_break_effect_s5(self):
        eng = _make(_build([_member("23035", sup=5)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 1.0, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23035", path="harmony")]))
        eng.bus.emit("on_break", {"bar_index": 0, "element": "fire",
                                  "source": "w", "target": "e1"}, eng.state)
        assert "LC_23035_CHARRING" not in _mods(eng, "e1")
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 23043 谎言在风中飘扬：速度常驻 + 茫然/失窃减防
# ---------------------------------------------------------------------------
class TestLC23043:
    def test_spd_and_bamboozle_s1(self):
        """S1：spd 100×1.18=118 <170 → 只挂茫然（def −16% → 840）."""
        eng = _make(_build([_member("23043", sup=1)]))
        assert math.isclose(_eff(eng, "w")["spd"], 100 * 1.18, rel_tol=1e-9)
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        assert "LC_23043_BAMBOOZLE" in e1.modifiers
        assert "LC_23043_THEFT" not in e1.modifiers
        assert math.isclose(_eff(eng, "e1")["def_"], 1000 * 0.84, rel_tol=1e-9)

    def test_theft_when_spd_170(self):
        """装备员 spd 150×1.18=177 ≥170 → 茫然+失窃双挂（def −16%−8% → 760）."""
        eng = _make(_build([_member("23043", sup=1, spd=150)]))
        assert math.isclose(_eff(eng, "w")["spd"], 150 * 1.18, rel_tol=1e-9)
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        assert "LC_23043_BAMBOOZLE" in e1.modifiers
        assert "LC_23043_THEFT" in e1.modifiers
        assert math.isclose(_eff(eng, "e1")["def_"], 1000 * 0.76, rel_tol=1e-9)

    def test_theft_s5(self):
        """S5：spd 140×1.30=182 ≥170 → def −24%−12% → 640."""
        eng = _make(_build([_member("23043", sup=5, spd=140)]))
        _cast(eng, "w", "w_basic")
        assert math.isclose(_eff(eng, "e1")["def_"], 1000 * 0.64, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23043", path="destruction")]))
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        assert "LC_23043_BAMBOOZLE" not in e1.modifiers
        assert "LC_23043_THEFT" not in e1.modifiers
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23050 勿忘她的火焰：击破特攻 + 击破伤害（添加弱点回 SP 半待收——判定通道缺，
# fixture 头注待收条在案）
# ---------------------------------------------------------------------------
class TestLC23050:
    def test_break_effect_and_break_dmg_s1(self):
        """S1：BE +60%；装备者击破伤害 +32%（break_dmg_boost 池）；单人队取序最高=自身."""
        eng = _make(_build([_member("23050", sup=1)]))
        eff = _eff(eng, "w")
        assert math.isclose(eff["break_effect"], 0.6, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["break_dmg_boost"], 0.32, rel_tol=1e-9)
        src, e1 = eng.state.actors["w"], eng.state.actors["e1"]
        eng2 = _make(_build([_member(None)]))
        base = float(eng2.pipeline.break_damage(
            eng2.state.actors["w"], eng2.state.actors["e1"], "fire").value)
        boosted = float(eng.pipeline.break_damage(src, e1, "fire").value)
        assert math.isclose(boosted / base, 1.6 * 1.32, rel_tol=1e-9), (
            "be_multi 1.6 × break_dmg_boost 1.32")

    def test_teammate_highest_be(self):
        """队友 BE 更高 → 击破伤害件落队友（fallback：击破特攻最高的队友）."""
        ally = _member(None, aid="ally", extra_stats={"break_effect": 1.0})
        eng = _make(_build([_member("23050", sup=1), ally]))
        assert "LC_23050_BREAK_DMG" in _mods(eng, "ally")
        assert math.isclose(_eff(eng, "ally")["dmg_bonus"]["break_dmg_boost"], 0.32,
                            rel_tol=1e-9)

    def test_teammate_not_buffed_when_self_highest(self):
        """装备者 BE 最高（0.6 > 队友 0.3）→ 取序命中自身（同 id 幂等=仅装备者）."""
        ally = _member(None, aid="ally", extra_stats={"break_effect": 0.3})
        eng = _make(_build([_member("23050", sup=1), ally]))
        assert "LC_23050_BREAK_DMG" in _mods(eng, "w")
        assert "LC_23050_BREAK_DMG" not in _mods(eng, "ally")

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23050", path="hunt")]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.0, abs_tol=1e-12)
        assert "LC_23050_BREAK_DMG" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23059 灼尽炼狱的新骸：生命上限 + 每波次回能 + 炼狱标记
# ---------------------------------------------------------------------------
class TestLC23059:
    def test_hp_pct_s1(self):
        """S1：hp 白值 (3000+1276.08)×1.3（hp_pct 基数=角色+光锥白值）."""
        hp_lc = _lc_base("23059")["hp"]
        eng = _make(_build([_member("23059", sup=1)]))
        assert math.isclose(_eff(eng, "w")["hp"], (3000 + hp_lc) * 1.3, rel_tol=1e-9)

    def test_hp_pct_s5(self):
        hp_lc = _lc_base("23059")["hp"]
        eng = _make(_build([_member("23059", sup=5)]))
        assert math.isclose(_eff(eng, "w")["hp"], (3000 + hp_lc) * 1.6, rel_tol=1e-9)

    def test_energy_once_per_wave(self):
        """首波有旗（on_battle_start 补）→ 回合开始 +20 能摘旗；再发无；转波次补旗再 +20."""
        eng = _make(_build([_member("23059", sup=1)]))
        w = eng.state.actors["w"]
        assert "LC_23059_ENERGY_READY" in w.modifiers, "首波旗在（battle_start 补挂）"
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert math.isclose(w.current_energy, 20.0, rel_tol=1e-9)
        assert "LC_23059_ENERGY_READY" not in w.modifiers, "触发即摘旗"
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert math.isclose(w.current_energy, 20.0, rel_tol=1e-9), "无旗不再回"
        eng.bus.emit("on_wave_start", {"wave_index": 1}, eng.state)
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert math.isclose(w.current_energy, 40.0, rel_tol=1e-9), "转波次补旗再触发"

    def test_energy_not_on_others_turn(self):
        """他人回合开始不触发（$event.actor 判据）."""
        ally = _member(None, aid="ally")
        eng = _make(_build([_member("23059", sup=1), ally]))
        eng.bus.emit("on_turn_start", {"actor": "ally"}, eng.state)
        assert math.isclose(eng.state.actors["w"].current_energy, 0.0, abs_tol=1e-12)
        assert "LC_23059_ENERGY_READY" in _mods(eng, "w"), "旗未误摘"

    def test_purgatory_on_skill(self):
        """战技攻击后目标挂【炼狱】（2 回合标记件；暴击承伤半待收）."""
        eng = _make(_build([_member("23059", sup=1, actions=[_skill("w_skill")])]))
        _cast(eng, "w", "w_skill")
        mod = eng.state.actors["e1"].modifiers["LC_23059_PURGATORY"]
        assert mod.duration == 2
        eng2 = _make(_build([_member("23059", sup=1)]))
        _cast(eng2, "w", "w_basic")
        assert "LC_23059_PURGATORY" not in eng2.state.actors["e1"].modifiers, "普攻不挂"

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23059", path="destruction",
                                    actions=[_skill("w_skill")])]))
        assert "LC_23059_ENERGY_READY" not in _mods(eng, "w")
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        assert math.isclose(eng.state.actors["w"].current_energy, 0.0, abs_tol=1e-12)
        _cast(eng, "w", "w_skill")
        assert "LC_23059_PURGATORY" not in eng.state.actors["e1"].modifiers


# ---------------------------------------------------------------------------
# 24003 孤独的疗愈：击破特攻常驻（DoT 增伤/击杀回能两半待收）
# ---------------------------------------------------------------------------
class TestLC24003:
    def test_break_effect_s1(self):
        eng = _make(_build([_member("24003", sup=1)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.2, rel_tol=1e-9)

    def test_break_effect_s5(self):
        eng = _make(_build([_member("24003", sup=5)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.4, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("24003", path="hunt")]))
        assert "LC_24003_BREAK_EFFECT" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 20011 渊环【待收】：减速条件增伤无通道——fixture 仅承载白值/叠影表（不硬凑）
# ---------------------------------------------------------------------------
class TestLC20011:
    def test_no_hook_no_dmg_boost(self):
        """无任何 LC_20011 modifier；普攻 = 无增伤裸伤（待收锚——机制落地后本测试改写）."""
        atk = 1000 + _lc_base("20011")["atk"]
        eng = _make(_build([_member("20011", sup=1)]))
        assert not [m for m in _mods(eng, "w") if m.startswith("LC_20011")]
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "无增伤段"


# ---------------------------------------------------------------------------
# 20018 匿影：战技闩 → 下一次普攻附加伤害
# ---------------------------------------------------------------------------
class TestLC20018:
    def test_additional_after_skill_s1(self):
        """S1：战技上闩 → 普攻 1.0 + 附加 0.6（装备者火属性，附加伤害同乘区口径）."""
        atk = 1000 + _lc_base("20018")["atk"]
        eng = _make(_build([_member("20018", sup=1,
                                    actions=[_basic("w_basic"), _skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_skill")
        assert "LC_20018_SKILL_LATCH" in _mods(eng, "w"), "战技后闩在"
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * 1.6 * z, rel_tol=1e-9)
        assert "LC_20018_SKILL_LATCH" not in _mods(eng, "w"), "首段消费闩"

    def test_no_latch_no_additional(self):
        """未施放战技：普攻无附加段."""
        atk = 1000 + _lc_base("20018")["atk"]
        eng = _make(_build([_member("20018", sup=1)]))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9)

    def test_additional_s5(self):
        """S5（#1=1.2）：普攻 1.0 + 附加 1.2."""
        atk = 1000 + _lc_base("20018")["atk"]
        eng = _make(_build([_member("20018", sup=5,
                                    actions=[_basic("w_basic"), _skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_skill")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * 2.2 * z, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        atk = 1000 + _lc_base("20018")["atk"]
        eng = _make(_build([_member("20018", path="destruction",
                                    actions=[_basic("w_basic"), _skill("w_skill")])]))
        e1 = eng.state.actors["e1"]
        _cast(eng, "w", "w_skill")
        assert "LC_20018_SKILL_LATCH" not in _mods(eng, "w")
        hp1 = e1.current_hp
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21001 晚安与睡颜【待收】：目标 debuff 计数原语缺——fixture 仅承载白值/叠影表
# ---------------------------------------------------------------------------
class TestLC21001:
    def test_no_hook_placeholder(self):
        """候选稿脑补钩（on_kill 加攻）已推倒——无任何 LC_21001 modifier（待收锚）."""
        eng = _make(_build([_member("21001", sup=1)]))
        assert not [m for m in _mods(eng, "w") if m.startswith("LC_21001")]
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        atk = 1000 + _lc_base("21001")["atk"]
        _cast(eng, "w", "w_basic")
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5)
        assert math.isclose(hp1 - e1.current_hp, atk * z, rel_tol=1e-9), "无增伤段"


# ---------------------------------------------------------------------------
# 21022 延长记号：击破特攻常驻（触电/风化增伤半待收）
# ---------------------------------------------------------------------------
class TestLC21022:
    def test_break_effect_s1(self):
        eng = _make(_build([_member("21022", sup=1)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.16, rel_tol=1e-9)

    def test_break_effect_s5(self):
        eng = _make(_build([_member("21022", sup=5)]))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.32, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("21022", path="hunt")]))
        assert "LC_21022_BREAK" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 23006 只需等待：增伤常驻 + 攻击速度叠层 + 游丝 DoT
# ---------------------------------------------------------------------------
class TestLC23006:
    def test_all_dmg_and_spd_stacks(self):
        """S1：all_dmg +24%；每次攻击 +4.8% 速度（cap 3 层=14.4%）."""
        eng = _make(_build([_member("23006", sup=1)]))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)
        _cast(eng, "w", "w_basic")
        assert math.isclose(_eff(eng, "w")["spd"], 100 * 1.048, rel_tol=1e-9)
        for _ in range(3):
            _cast(eng, "w", "w_basic")
        assert _mods(eng, "w")["LC_23006_SPD_STACK"].stacks == 3, "#4 恒 3 钳顶"
        assert math.isclose(_eff(eng, "w")["spd"], 100 * 1.144, rel_tol=1e-9)

    def test_erode_applied_and_dot_tick(self):
        """S1：击中挂游丝（100% 基础概率期望口径必中，持续 1 回合）；目标回合开始跳雷伤
        = 装备者有效攻击 ×0.6（吃装备者增伤区——DoT 全公式链口径待实测在案）."""
        atk = 1000 + _lc_base("23006")["atk"]
        eng = _make(_build([_member("23006", sup=1)]))
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        assert "LC_23006_ERODE" in e1.modifiers
        assert e1.modifiers["LC_23006_ERODE"].duration == 1, "#5 恒 1 回合"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5) * 1.24     # 防御×未击破×期望暴击×(1+all_dmg S1)
        assert math.isclose(hp1 - e1.current_hp, atk * 0.6 * z, rel_tol=1e-9)

    def test_erode_s5_tick(self):
        """S5（#1=1.0、#2=0.4）：跳雷伤 = atk ×1.0 ×区（增伤 1.40）."""
        atk = 1000 + _lc_base("23006")["atk"]
        eng = _make(_build([_member("23006", sup=5)]))
        _cast(eng, "w", "w_basic")
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        z = 0.5 * 0.9 * (1 + 0.05 * 0.5) * 1.40
        assert math.isclose(hp1 - e1.current_hp, atk * 1.0 * z, rel_tol=1e-9)

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23006", path="hunt")]))
        _cast(eng, "w", "w_basic")
        assert "LC_23006_ERODE" not in eng.state.actors["e1"].modifiers
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("all", 0.0), 0.0, abs_tol=1e-12)
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23047 海洋为何而歌：效果命中常驻 + 魂迷 + 受击加速（DoT 计数易伤半待收）
# ---------------------------------------------------------------------------
class TestLC23047:
    def test_ehr_s1_and_s5(self):
        eng1 = _make(_build([_member("23047", sup=1)]))
        assert math.isclose(_eff(eng1, "w")["effect_hit"], 0.4, rel_tol=1e-9)
        eng5 = _make(_build([_member("23047", sup=5)]))
        assert math.isclose(_eff(eng5, "w")["effect_hit"], 0.6, rel_tol=1e-9)

    def test_enthrall_applied_on_debuff(self):
        """S1：装备者施加 debuff → 80% 基础概率（expected 必中）挂魂迷 3 回合；同类不叠."""
        eng = _make(_build([_member("23047", sup=1, actions=[_debuff_skill()])]))
        _cast(eng, "w", "w_skill")
        e1 = eng.state.actors["e1"]
        assert "LC_23047_ENTHRALL" in e1.modifiers
        assert e1.modifiers["LC_23047_ENTHRALL"].duration == 3, "#3 恒 3 回合"
        mod = e1.modifiers["LC_23047_ENTHRALL"]
        _cast(eng, "w", "w_skill")
        assert e1.modifiers["LC_23047_ENTHRALL"] is mod, "同类效果无法叠加（在持不重挂）"

    def test_attacker_spd_buff(self):
        """攻击魂迷目标 → 攻击者速度 +10%（S1 #6）3 回合."""
        eng = _make(_build([_member("23047", sup=1, actions=[_basic("w_basic"), _debuff_skill()])]))
        _cast(eng, "w", "w_skill")          # 挂魂迷
        _cast(eng, "w", "w_basic")          # 攻击魂迷目标
        assert "LC_23047_SPD" in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["spd"], 100 * 1.1, rel_tol=1e-9)

    def test_enthrall_removed_on_wearer_death(self):
        """装备者无法战斗（on_kill 锚）→ 移除所有魂迷."""
        eng = _make(_build([_member("23047", sup=1, actions=[_debuff_skill()])]))
        _cast(eng, "w", "w_skill")
        eng.bus.emit("on_kill", {"action_id": "", "source": "e1", "target": "w"}, eng.state)
        assert "LC_23047_ENTHRALL" not in eng.state.actors["e1"].modifiers

    def test_path_mismatch_no_effect(self):
        eng = _make(_build([_member("23047", path="hunt", actions=[_debuff_skill()])]))
        _cast(eng, "w", "w_skill")
        assert "LC_23047_ENTHRALL" not in eng.state.actors["e1"].modifiers
        assert math.isclose(_eff(eng, "w")["effect_hit"], 0.0, abs_tol=1e-12)
