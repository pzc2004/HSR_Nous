"""海瑟音 1410 模板端到端对轴（验收型批）：真模板 YAML → 编译 →
行迹/天赋 4 色 DoT/Zone 追加 DOT/易伤/星魂全链 → 手算全等.

口径常数：海瑟音白值 atk 601.524（行迹 atk_pct +18% → 有效 709.79832）、
crit 0.05/0.5（期望暴击区 1.025）、EHR 0.1（行迹 +10%）；假人 def 1000 →
防御区 0.5（Zone DEF-25% 时 1000/1750；E3 lv12 DEF-27% 时 1000/1730）、
物理弱点 → 抗性区 1.0、未击破 0.9。
lv 档：普攻 lv6=1.0（E3→lv7=1.1）、战技 lv10=1.4/易伤 0.2（E5→lv12=1.54/0.22）、
终结技 lv10=2.0/追加 0.8/帽 8（E3→lv12=2.16/0.88）、天赋 lv10 DoT 0.25
（E5→lv12=0.275）、裂伤=min(20%maxHP, 25%ATK)——1e9 假人帽必生效=0.25×ATK。
每次命中 Zone 内敌人还追加 1 发 0.8×ATK 的 Zone DOT（trigs<cap），DoT 跳伤/
追加 DOT 走 deal_damage 含期望暴击区（全库触电同族口径，官方不暴击偏差在案）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 601.524 * 1.18                       # 有效攻击（行迹 atk_pct +18%）
DEFZ = 1000.0 / (1000.0 * 0.75 + 1000.0)   # Zone DEF-25%（lv10）→ 1000/1750
DEFZ12 = 1000.0 / (1000.0 * 0.73 + 1000.0)  # Zone DEF-27%（E3 lv12）→ 1000/1730
CRIT = 1 + 0.05 * 0.5                      # 期望暴击区 1.025
ZZ = DEFZ * 0.9 * CRIT                     # Zone 在场全乘区（lv10，抗性 1.0）
ZZ5 = DEFZ12 * 1.2 * 0.9 * CRIT            # eidolon≥4：lv12 减防 + E4 抗性区 1.2


def _build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1410", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1410", "technique": "141007"}]
    return build


# 四色弱点假人（物理/风/火/雷——天赋 4 色 DoT 全弱点匹配 → 抗性区一律 1.0）
_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical", "wind", "fire", "thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["physical", "wind", "fire", "thunder"]}],
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


def _hy(eng):
    return eng.state.actors["1410"]


def _dmg(eng, aid="1410"):
    return eng.state.damage_by_actor.get(aid, 0.0)


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
    st = _hy(eng)
    st.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1410"] if a.action_id == "141003")
    assert eng._fire_ultimate(st, ult) is True


class TestHysilensCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id for a in compiled.actions_by_actor["1410"]}
        assert acts == {"141001", "141002", "141003"}
        decls = compiled.resource_decls_by_actor["1410"]
        assert {"_dot_idx", "_zone_trigs", "_zone_cap", "_hy_guard"} <= set(decls)
        assert decls["_zone_cap"]["current"] == 8.0, "次数帽基准 8（141003 #5 全档常量）"
        assert decls["_zone_cap"]["max"] == 12

    def test_trace_panel(self, compiled):
        """小行迹 SPD+14 / ATK+18% / EHR+10%（勘正④——官方 skill_trees properties）."""
        eng = _make(compiled)
        eff = eng.pipeline.effective_stats(_hy(eng))
        assert math.isclose(eff["spd"], 102 + 14, rel_tol=1e-9)
        assert math.isclose(eff["atk"], ATK, rel_tol=1e-9)
        assert math.isclose(eff["effect_hit"], 0.1, rel_tol=1e-9)


class TestBattleStartZone:
    def test_trace_a_zone_and_sp(self, compiled):
        """行迹 A：开战双敌挂 Zone（DEF-25%/ATK-15%、source_turn_start 锚、不可驱散）
        + 部署回 1 战技点（勘正⑥ gain_skill_point 收录）."""
        eng = _make(compiled)
        for aid in ("e1", "e2"):
            tgt = eng.state.actors[aid]
            zone = tgt.modifiers["HYS_ZONE"]
            assert zone.tick_anchor == "source_turn_start", "官方「海瑟音回合开始时 -1」"
            assert zone.dispellable is False, "结界=领域不可驱散"
            assert zone.duration == 3
            eff = eng.pipeline.effective_stats(tgt)
            assert math.isclose(eff["def_"], 1000 * 0.75, rel_tol=1e-9)
            assert math.isclose(eff["atk"], 1000 * 0.85, rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 4.0), "3+1（部署回点）"
        assert math.isclose(_hy(eng).resources["_zone_trigs"], 0.0)

    def test_trace_c_pearl_fiddle_gate(self, compiled):
        """行迹 C：EHR 0.1<0.6 → 增伤门控关闭（且钳位不倒扣）；stat_exprs 现场通道."""
        eng = _make(compiled)
        hy = _hy(eng)
        assert "HYS_PEARL_FIDDLE" in hy.modifiers
        assert math.isclose(eng.pipeline.effective_stats(hy)["dmg_bonus"].get("all", 0.0),
                            0.0, abs_tol=1e-9)
        eng._apply_modifier(hy, Modifier(
            modifier_id="EHR_FIX", name="EHR", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"effect_hit": 1.0}))
        assert math.isclose(eng.pipeline.effective_stats(hy)["dmg_bonus"].get("all", 0.0),
                            0.15 * 5, rel_tol=1e-9), "EHR 1.1 → (1.1-0.6)/0.1=5 档 → 0.75"
        eng._apply_modifier(hy, Modifier(
            modifier_id="EHR_FIX2", name="EHR2", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"effect_hit": 0.2}))
        assert math.isclose(eng.pipeline.effective_stats(hy)["dmg_bonus"].get("all", 0.0),
                            0.9, rel_tol=1e-9), "EHR 1.3 → 7 档钳 6 → 封顶 0.9"


class TestBasicSkill:
    def test_basic_damage_sp_energy(self, compiled):
        """普攻 lv6=1.0×ATK×ZZ；命中再追加 1 发 Zone DOT 0.8×ATK×ZZ（合计 1.8）；
        SP +1（4→5）、回能 20."""
        eng = _make(compiled)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1410", "141001")
        assert math.isclose(hp1 - e1.current_hp, 1.8 * ATK * ZZ, rel_tol=1e-9), (
            "普攻 1.0 + Zone 追加 0.8")
        assert math.isclose(eng.state.skill_points, 5.0)
        assert math.isclose(_hy(eng).current_energy, 20.0)
        assert "HY_DOT_WIND" in e1.modifiers, "天赋：命中施加第 1 色（风化）"

    def test_skill_aoe_vuln(self, compiled):
        """战技 lv10=1.4×ATK×ZZ 全体（本击不吃自己易伤——on_action 后挂在案）；
        易伤 +20% 三回合；SP -1、回能 30；后续普攻吃 1.2 承伤区."""
        eng = _make(compiled)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "1410", "141002")
        for tgt, hp in ((e1, hp1), (e2, hp2)):
            assert math.isclose(hp - tgt.current_hp, 2.2 * ATK * ZZ, rel_tol=1e-9), (
                "战技 1.4 + Zone 追加 0.8（逐目标各 1 发）")
        assert math.isclose(eng.state.skill_points, 3.0), "4-1"
        assert math.isclose(_hy(eng).current_energy, 30.0)
        for aid in ("e1", "e2"):
            assert math.isclose(
                eng.pipeline.effective_stats(eng.state.actors[aid])["vulnerability"],
                0.2, rel_tol=1e-9), "易伤 +20%（vulnerability 在案键）"
        hp1 = e1.current_hp
        _cast(eng, "1410", "141001")
        assert math.isclose(hp1 - e1.current_hp, 1.8 * ATK * ZZ * 1.2, rel_tol=1e-9), (
            "易伤后普攻+追加同吃 1.2 承伤区")


class TestUltimate:
    def test_ult_damage_zone_refresh_reset(self, compiled):
        """终结技 lv10=2.0×ATK×ZZ 全体（行迹 A Zone 已在场→本击吃减防）+ 追加 0.8；
        计数归零、Zone 刷新 3 回合、部署再回 1 点、能量 110→5."""
        eng = _make(compiled)
        hy = _hy(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hy.resources["_zone_trigs"] = 5.0
        e1.modifiers["HYS_ZONE"].duration = 1
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng)
        for tgt, hp in ((e1, hp1), (e2, hp2)):
            assert math.isclose(hp - tgt.current_hp, 2.8 * ATK * ZZ, rel_tol=1e-9), (
                "终结技 2.0 + Zone 追加 0.8")
            assert tgt.modifiers["HYS_ZONE"].duration == 3, "重新部署刷新 3 回合"
        assert math.isclose(hy.resources["_zone_trigs"], 0.0), "部署计数归零"
        assert math.isclose(hy.current_energy, 5.0), "110-110+5"
        assert math.isclose(eng.state.skill_points, 5.0), "4+1（再次部署回点）"


class TestTalentRotation:
    def test_four_color_rotation(self, compiled):
        """天赋轮转（确定近似）：命中 1..5 依次 风/裂/灼/触/风；施加本身零伤害
        （damage_by_actor 只记 Zone 追加）；_dot_idx 1→2→3→0→1."""
        eng = _make(compiled)
        hy = _hy(eng)
        e1 = eng.state.actors["e1"]
        seq = ["HY_DOT_WIND", "HY_DOT_BLEED", "HY_DOT_BURN", "HY_DOT_SHOCK", "HY_DOT_WIND"]
        for i, mid in enumerate(seq):
            d0 = _dmg(eng)
            _cast(eng, "ally", "ally_basic")
            assert mid in e1.modifiers, f"第 {i + 1} 击施加 {mid}"
            assert math.isclose(_dmg(eng) - d0, 0.8 * ATK * ZZ, rel_tol=1e-9), (
                "每击 Zone 追加恰 1 发（递归闩——追加自身不再触天赋/自链）")
        assert math.isclose(hy.resources["_dot_idx"], 1.0), "轮转 1→2→3→0→1"
        assert math.isclose(hy.resources["_zone_trigs"], 5.0), "5 击 5 发"


class TestDotTicksAndZoneCap:
    def test_ticks_per_instance_and_cap(self, compiled):
        """4 色齐备后敌方回合开始：4 跳 DoT（各 0.25×ATK×ZZ，裂伤帽=0.25×ATK 同值）
        + Zone 追加按实例数 4 发（勘正⑪）= 合计 (1.0+3.2)×ATK×ZZ；计数 4→8 满帽后
        次回合只剩 4 跳 DoT（无追加）."""
        eng = _make(compiled)
        hy = _hy(eng)
        e1 = eng.state.actors["e1"]
        for _ in range(4):
            _cast(eng, "ally", "ally_basic")   # 4 色齐备；trigs=4
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 4.2 * ATK * ZZ, rel_tol=1e-9), (
            "4 跳 0.25 + 4 发 0.8（min(4, 8-4)）")
        assert math.isclose(hy.resources["_zone_trigs"], 8.0)
        assert math.isclose(hy.resources["_hy_guard"], 0.0), "闩归位"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, 1.0 * ATK * ZZ, rel_tol=1e-9), (
            "满帽 8：只剩 4 跳 DoT（4×0.25），无 Zone 追加")

    def test_cap_partial_batch(self, compiled):
        """残帽 1 时 2 实例只结 1 发（min(count, cap-trigs) 钳——勘正⑪）."""
        eng = _make(compiled)
        hy = _hy(eng)
        e1 = eng.state.actors["e1"]
        for _ in range(2):
            _cast(eng, "ally", "ally_basic")   # 风+裂；trigs=2
        hy.resources["_zone_trigs"] = 7.0
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, (0.5 + 0.8) * ATK * ZZ, rel_tol=1e-9), (
            "2 跳 0.25 + min(2, 8-7)=1 发 0.8")
        assert math.isclose(hy.resources["_zone_trigs"], 8.0)


class TestEidolons:
    def test_e1_extra_coexisting_instance(self):
        """E1：天赋施加时追加 1 色共存实例（快照配位：风化→裂伤_E1——勘正③非 4 色齐发）；
        回合开始 2 跳 + Zone 追加按 2 实例计."""
        eng = _make(_compiled(eidolon=1))
        e1 = eng.state.actors["e1"]
        _cast(eng, "ally", "ally_basic")
        assert set(e1.modifiers) >= {"HY_DOT_WIND", "HY_DOT_BLEED_E1"}
        assert "HY_DOT_BURN_E1" not in e1.modifiers, "一次命中只追加 1 色"
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        assert math.isclose(hp1 - e1.current_hp, (0.5 + 1.6) * ATK * ZZ, rel_tol=1e-9), (
            "风 1 跳 + 裂 1 跳（_E1 实例同倍率）+ 追加 2 发（min(2, 8-1)）")

    def test_e2_teamwide_pearl_bake(self):
        """E2：行迹增伤扩散全队——other_allies（自身不双份）；蒙福者烘焙=EHR 挂点快照
        （EHR 0.1 → 钳 0；EHR 1.1 → 0.75）；勘正⑧负值钳."""
        eng = _make(_compiled(eidolon=2))
        hy = _hy(eng)
        ally = eng.state.actors["ally"]
        assert "E2_PEARL_FIDDLE" in ally.modifiers, "开战 Zone 同触发（勘正⑦）"
        assert "E2_PEARL_FIDDLE" not in hy.modifiers, "自身已持行迹本体不双份（勘正⑨）"
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.0, abs_tol=1e-9), "EHR 0.1 → 钳 0（不倒扣）"
        eng._apply_modifier(hy, Modifier(
            modifier_id="EHR_FIX", name="EHR", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"effect_hit": 1.0}))
        _ult(eng)   # replace 重挂重烘
        assert math.isclose(eng.pipeline.effective_stats(ally)["dmg_bonus"].get("all", 0.0),
                            0.75, rel_tol=1e-9), "烘焙=施加者 EHR 1.1 → 0.75"
        assert math.isclose(eng.pipeline.effective_stats(hy)["dmg_bonus"].get("all", 0.0),
                            0.75, rel_tol=1e-9), "本体 stat_exprs 现场同值"

    def test_e4_all_res_pen(self):
        """E4：Zone 期间我方全体 res_pen +20%（敌方减抗等效承载）；开战即挂（勘正⑦）；
        战技本击抗性区 1.2（lv10 档；eidolon=4 含 E3 → Zone 减防 lv12 27%）."""
        eng = _make(_compiled(eidolon=4))
        hy = _hy(eng)
        ally = eng.state.actors["ally"]
        for st in (hy, ally):
            assert math.isclose(eng.pipeline.effective_stats(st)["res_pen"], 0.2,
                                rel_tol=1e-9)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1410", "141002")
        assert math.isclose(hp1 - e1.current_hp, (1.4 + 0.88) * ATK * DEFZ12 * 1.2 * 0.9 * CRIT,
                            rel_tol=1e-9), (
            "战技 lv10 1.4 + 追加 lv12 0.88（E3 联动），抗性区 1- (0-0.2)=1.2")

    def test_e3_e5_level_tiers(self):
        """E3/E5 联动（eidolon=5）：战技 lv12=1.54/易伤 0.22；普攻 lv7=1.1；
        天赋 lv12=0.275；终结技 lv12=2.16/追加 0.88/减防 27%；E4 抗性区 1.2 同吃."""
        eng = _make(_compiled(eidolon=5))
        hy = _hy(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1410", "141002")
        assert math.isclose(hp1 - e1.current_hp, (1.54 + 0.88) * ATK * ZZ5, rel_tol=1e-9), (
            "战技 lv12 1.54 + 追加 lv12 0.88（减防 27%+抗性 1.2）")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.22,
                            rel_tol=1e-9), "易伤 lv12 +22%"
        hp1 = e1.current_hp
        _cast(eng, "1410", "141001")
        assert math.isclose(hp1 - e1.current_hp, (1.1 + 0.88) * ATK * ZZ5 * 1.22,
                            rel_tol=1e-9), "普攻 lv7 1.1（易伤 1.22 同吃）"
        hy.resources["_zone_trigs"] = 0.0
        hp1 = e1.current_hp
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        # eidolon=5 含 E1：战技击→风+裂_E1、普攻击→裂+灼_E1 → 4 实例（跳 4×0.275、追加 4×0.88）
        assert math.isclose(hp1 - e1.current_hp, (1.1 + 3.52) * ATK * ZZ5 * 1.22,
                            rel_tol=1e-9), (
            "4 跳 lv12 0.275 + 追加 4 发 0.88（裂伤帽=0.275×ATK<20%×1e9）")
        _ult(eng)
        assert math.isclose(eng.pipeline.effective_stats(e1)["def_"], 730.0, rel_tol=1e-9), (
            "Zone 减防 lv12 27%")

    def test_e6_cap_12(self):
        """E6：开战次数帽 8→12（基准 8 见 decl——勘正①）；残帽 1 发后满帽止."""
        eng = _make(_compiled(eidolon=6))
        hy = _hy(eng)
        assert math.isclose(hy.resources["_zone_cap"], 12.0)
        e1 = eng.state.actors["e1"]
        hy.resources["_zone_trigs"] = 11.0
        d0 = _dmg(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(_dmg(eng) - d0, 0.88 * ATK * ZZ5, rel_tol=1e-9), (
            "11<12 恰 1 发（lv12 0.88）")
        assert math.isclose(hy.resources["_zone_trigs"], 12.0)
        d0 = _dmg(eng)
        _cast(eng, "ally", "ally_basic")
        assert math.isclose(_dmg(eng) - d0, 0.0, abs_tol=1e-9), "满帽 12 不再追加"
        _ult(eng)
        assert math.isclose(hy.resources["_zone_cap"], 12.0), "重新部署帽仍 12"
        assert math.isclose(hy.resources["_zone_trigs"], 0.0), "重新部署计数归零"


class TestTechnique:
    def test_pre_battle_two_dots(self):
        """秘技：进战双敌各挂 2 色天赋同款 DoT（风+灼确定化近似在案）；行迹 A Zone
        与部署回点同发（SP 3+1=4，秘技点池独立）."""
        eng = _make(_compiled(pre_battle=True))
        for aid in ("e1", "e2"):
            mods = eng.state.actors[aid].modifiers
            assert "HY_DOT_WIND" in mods and "HY_DOT_BURN" in mods
            assert "HYS_ZONE" in mods
        assert math.isclose(eng.state.skill_points, 4.0)
