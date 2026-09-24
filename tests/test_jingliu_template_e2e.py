"""镜流 1212 双版本模板端到端对轴（版本化试点）：真模板 YAML × member.version
→ 编译双轨分流 → 加强后（1121xxx·Max HP 套）/加强前（121xxx·ATK 套）全链 → 手算全等.

版本双轨：加强前后机制互不兼容（技能/行迹/星魂 E1/E4/E6 三套全随版本拆），
`version: legacy` 选 1212_镜流_legacy.yaml，默认 enhanced——owner 裁定"加强
前后视为两个角色"。过堂勘正见两 fixture 头注（星魂幻名三件/月色 /10 幻视/
剑首技名错位/耗血自耗/朔望上限分版）。

口径常数：镜流白值 hp 1435.896、atk 679.14、crit 0.05/0.5+行迹暴伤 0.373（B-TR③
回填 character_skill_trees 十节点：暴伤 0.373/速度+9/生命+10%——HP 面板=白值×1.1）；
假人 def 0 → 防御区 0.5、冰弱点 → 抗性区 1.0、未击破 0.9。无 buff 期望区
Z0=0.5*0.9*(1+0.05*0.873)；转魄 crit_rate 0.05+0.5=0.55（天赋 lv10 #7=0.5——
params 15 档，lv10=index 9）。
技能/终结技/天赋 lv10、普攻 lv6 口径。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS

HP = 1435.896 * 1.1                          # 1579.4856（行迹生命+10%——B-TR③ 回填）
ATK = 679.14
CD = 0.5 + 0.373                             # 0.873（行迹暴伤——B-TR③ 回填）
Z0 = 0.5 * 0.9 * (1 + 0.05 * CD)             # 无转魄期望区 0.4696425
Z_TRANS = 0.5 * 0.9 * (1 + 0.55 * CD)        # 转魄期望区（月色 0 层）0.6660675
# legacy 汲血转攻 tally 实额制（lv10：min(5.4×drain 实额累计, 1.8×基础攻)）：
# 单队友 drain=0.04×3000=120 → 首段 648；第二段累计 240 → 1296 越 cap → 1222.452
LEGACY_BOOST_1 = min(5.4 * (0.04 * 3000), 1.8 * ATK)        # 648.0
LEGACY_BOOST_2 = min(5.4 * (0.04 * 3000) * 2, 1.8 * ATK)    # 1222.452（cap）


def _build(*, eidolon: int = 0, version: str | None = None, pre_battle: bool = False):
    member = {"character_template": "1212", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    if version:
        member["version"] = version
    build = {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "ice",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}
    if pre_battle:
        build["build"]["pre_battle"] = [{
            "actor_id": "1212",
            "technique": "121207" if version == "legacy" else "1121207"}]
    return build


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["ice"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0, version: str | None = None, pre_battle: bool = False):
    return compile_encounter(_build(eidolon=eidolon, version=version, pre_battle=pre_battle),
                             _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled_enh():
    return _compiled()


@pytest.fixture(scope="module")
def compiled_leg():
    return _compiled(version="legacy")


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=4)
    eng.setup()
    return eng


def _jl(eng):
    return eng.state.actors["1212"]


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


class TestVersionGate:
    """member.version 编译期分流 + 词表闸（错拼/inline 滥用/缺文件都炸，不静默吞）."""

    def test_default_is_enhanced(self, compiled_enh):
        acts = {a.action_id for a in compiled_enh.actions_by_actor["1212"]}
        assert acts == {"1121201", "1121202", "1121203", "1121209"}, "默认=加强后 1121xxx 套"
        decls = compiled_enh.resource_decls_by_actor["1212"]
        assert decls["syzygy"]["max"] == 4 and "_hit_count" in decls

    def test_legacy_track(self, compiled_leg):
        acts = {a.action_id for a in compiled_leg.actions_by_actor["1212"]}
        assert acts == {"121201", "121202", "121203", "121209"}, "legacy=加强前 121xxx 套"
        decls = compiled_leg.resource_decls_by_actor["1212"]
        assert decls["syzygy"]["max"] == 3 and "_hit_count" not in decls

    def test_bad_version_rejected(self):
        with pytest.raises(ValueError, match="version 非法值"):
            _compiled(version="legancy")

    def test_inline_version_rejected(self):
        build = {"build": {"team": [
            {"actor_id": "x", "name": "假", "inline": True, "version": "legacy",
             "base_stats": {"atk": 100}, "actions": []}],
            "policy": {"name": "p", "action_rules": []}}}
        with pytest.raises(ValueError, match="inline 角色无版本轨"):
            compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)

    def test_legacy_missing_file_rejected(self):
        build = _build(version="legacy")
        build["build"]["team"][0]["character_template"] = "1202"   # 停云无 legacy 文件
        with pytest.raises(FileNotFoundError, match="加强前"):
            compile_encounter(build, _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


class TestEnhanced:
    """加强后（1121xxx·Max HP 套）：朔望/转魄/月色/计次/剑首回能全链."""

    def test_skill_grants_syzygy_and_sword_champion_energy(self, compiled_enh):
        """无罅飞光 lv10：主 1.5×Max×Z0 + 朔望+1 + 回能 20+15（剑首 11212102）."""
        eng = _make(compiled_enh)
        s = _jl(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1212", "1121202")
        assert math.isclose(hp1 - e1.current_hp, 1.5 * HP * Z0, rel_tol=1e-9)
        assert math.isclose(s.resources["syzygy"], 1.0)
        assert math.isclose(s.current_energy, 35.0), "战技 20 + 剑首 15"
        assert math.isclose(s.resources.get("_transmigration", 0.0), 0.0)

    def test_transmigration_and_moonlight_chain(self, compiled_enh):
        """二战技进转魄（额外+1 朔望 → 3，暴击率 0.6）→ 寒川映月主 1.5/邻 0.75×Max
        ×转魄期望区 + 耗队友 5%Max（other_allies 不自耗）+ 月色 1 层 + 计次 1."""
        eng = _make(compiled_enh)
        s = _jl(eng)
        _cast(eng, "1212", "1121202")
        _cast(eng, "1212", "1121202")
        assert math.isclose(s.resources["_transmigration"], 1.0)
        assert math.isclose(s.resources["syzygy"], 3.0), "2 层进转魄额外+1"
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_rate"], 0.55, rel_tol=1e-9)
        ally = eng.state.actors["ally"]
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp_a, hp1, hp2, hp_s = ally.current_hp, e1.current_hp, e2.current_hp, s.current_hp
        _cast(eng, "1212", "1121209")
        assert math.isclose(hp1 - e1.current_hp, 1.5 * HP * Z_TRANS, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.75 * HP * Z_TRANS, rel_tol=1e-9)
        assert math.isclose(hp_a - ally.current_hp, 0.05 * 3000, rel_tol=1e-9), "耗队友 5%Max"
        assert math.isclose(s.current_hp, hp_s), "镜流不自耗"
        assert math.isclose(s.resources["syzygy"], 2.0)
        assert math.isclose(s.resources["_hit_count"], 1.0)
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"],
                            CD + 0.44, rel_tol=1e-9), "月色 1 层 lv10 暴伤+44%"
        assert math.isclose(s.current_energy, (20 + 15) * 2 + 30 + 8, rel_tol=1e-9), (
            "两战技（20+15 剑首）+ 寒川（30+8 剑首）=108")

    def test_ultimate_blast(self, compiled_enh):
        """终结技 lv10：主 1.8×Max / 邻 0.9×Max×Z0 + 朔望+1 + 回能 5."""
        eng = _make(compiled_enh)
        s = _jl(eng)
        s.current_energy = 140.0
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        ult = next(a for a in eng.actions_by_actor["1212"] if a.action_id == "1121203")
        assert eng._fire_ultimate(s, ult) is True
        assert math.isclose(hp1 - e1.current_hp, 1.8 * HP * Z0, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.9 * HP * Z0, rel_tol=1e-9)
        assert math.isclose(s.resources["syzygy"], 1.0)
        assert math.isclose(s.current_energy, 5.0)


class TestLegacy:
    """加强前（121xxx·ATK 套）：朔望/转魄/汲血转攻/剑首提前全链."""

    def test_skill_and_transmigration_no_bonus_syzygy(self, compiled_leg):
        """无罅飞光 lv10：主 2.0×ATK×Z0 + 朔望+1；二战技进转魄**无额外朔望**（=2）."""
        eng = _make(compiled_leg)
        s = _jl(eng)
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "1212", "121202")
        assert math.isclose(hp1 - e1.current_hp, 2.0 * ATK * Z0, rel_tol=1e-9)
        assert math.isclose(s.resources["syzygy"], 1.0)
        assert math.isclose(s.current_energy, 20.0), "旧版剑首是行动提前非回能"
        _cast(eng, "1212", "121202")
        assert math.isclose(s.resources["_transmigration"], 1.0)
        assert math.isclose(s.resources["syzygy"], 2.0), "旧版进转魄不额外获得"
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_rate"], 0.55, rel_tol=1e-9)

    def test_eskill_drain_and_atk_boost(self, compiled_leg):
        """寒川映月 lv10：主 2.5×ATK/邻 1.25×ATK×转魄区 + 耗队友 4%Max +
        汲血转攻 tally 实额（首发后 atk+648；次发吃 648、发后钉 cap 1222.452）."""
        eng = _make(compiled_leg)
        s = _jl(eng)
        _cast(eng, "1212", "121202")
        _cast(eng, "1212", "121202")
        ally = eng.state.actors["ally"]
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp_a, hp1, hp2 = ally.current_hp, e1.current_hp, e2.current_hp
        _cast(eng, "1212", "121209")
        assert math.isclose(hp1 - e1.current_hp, 2.5 * ATK * Z_TRANS, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 1.25 * ATK * Z_TRANS, rel_tol=1e-9)
        assert math.isclose(hp_a - ally.current_hp, 0.04 * 3000, rel_tol=1e-9), "耗队友 4%Max"
        assert math.isclose(eng.pipeline.effective_stats(s)["atk"],
                            ATK + LEGACY_BOOST_1, rel_tol=1e-9), "tally 120 → 转攻 648"
        hp1b = e1.current_hp
        _cast(eng, "1212", "121209")
        assert math.isclose(hp1b - e1.current_hp,
                            2.5 * (ATK + LEGACY_BOOST_1) * Z_TRANS, rel_tol=1e-9), (
            "第二发吃首发转攻 648")
        assert math.isclose(s.resources["syzygy"], 0.0)
        assert math.isclose(s.resources["_transmigration"], 0.0), "朔望归零退转魄"
        assert math.isclose(s.resources["_drain_tally"], 0.04 * 3000 * 2, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(s)["atk"], ATK, rel_tol=1e-9), (
            "退转魄后转攻 enable_if 关——tally 240 在账（cap 1222.452 待命）")


class TestTechnique:
    """秘技古镜照神：进战回能 15 + 朔望+1 + 冻结（官方 desc「regenerates #6[i] Energy」
    #6[i]=15 + 米游社秘技「回能 15」双证——曾误写 gain_resource energy 幻影写死效，
    gain_energy 通道钉）."""

    def test_technique_energy_and_syzygy_enhanced(self):
        eng = _make(_compiled(pre_battle=True))
        s = _jl(eng)
        assert math.isclose(s.current_energy, 15.0), "秘技进战回能 15"
        assert math.isclose(s.resources["syzygy"], 1.0), "朔望+1"
        assert "TECH_FROZEN" in eng.state.actors["e1"].modifiers, "全体冻结 1 回合"

    def test_technique_energy_and_syzygy_legacy(self):
        eng = _make(_compiled(version="legacy", pre_battle=True))
        s = _jl(eng)
        assert math.isclose(s.current_energy, 15.0), "秘技进战回能 15"
        assert math.isclose(s.resources["syzygy"], 1.0), "朔望+1"


class TestEidolons:
    def test_e1_enhanced(self):
        """E1 月犯天关（新）：开大 → 暴伤+36%（1 回合）+ 主目标追伤 0.8×Max
        （_fire_ultimate 自发 on_action 勿手动补发；追伤按结算时面板 crit
        0.05/0.86；目标近似 pool 首敌，挡因在案）."""
        compiled = _compiled(eidolon=1)
        eng = _make(compiled)
        s = _jl(eng)
        s.current_energy = 140.0
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        ult = next(a for a in eng.actions_by_actor["1212"] if a.action_id == "1121203")
        assert eng._fire_ultimate(s, ult) is True
        assert "E1_CRIT_DMG" in s.modifiers
        z_e1 = 0.5 * 0.9 * (1 + 0.05 * (CD + 0.36))
        assert math.isclose(hp1 - e1.current_hp, 1.8 * HP * Z0 + 0.8 * HP * z_e1, rel_tol=1e-9)

    def test_e4_enhanced_moonlight_crit(self):
        """E4 持秉玄烛（新）：转魄中月色每层额外暴伤+20%——eidolon=4 全联动口径：
        E3 天赋 lv12（月色 0.484/层）+ 寒川触发 E1（+0.36）同台，逐层对轴."""
        compiled = _compiled(eidolon=4)
        eng = _make(compiled)
        s = _jl(eng)
        _cast(eng, "1212", "1121202")
        _cast(eng, "1212", "1121202")
        _cast(eng, "1212", "1121209")   # 耗血 → 月色 1 层 + E4 挂；E1 同发
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"],
                            CD + 0.484 + 0.2 + 0.36, rel_tol=1e-9)

    def test_e6_enhanced(self):
        """E6 蚀变于娄（新）：进转魄额外朔望+2（max=4 截断——上限覆写通道缺在案）
        + 转魄中冰抗穿+30%（enable_if 门控）."""
        compiled = _compiled(eidolon=6)
        eng = _make(compiled)
        s = _jl(eng)
        assert math.isclose(eng.pipeline.effective_stats(s)["res_pen"], 0.0, abs_tol=1e-9)
        _cast(eng, "1212", "1121202")
        _cast(eng, "1212", "1121202")
        assert math.isclose(s.resources["syzygy"], 4.0), "2+1+2=5 → max 4 截断（E6 上限未覆写）"
        assert math.isclose(eng.pipeline.effective_stats(s)["res_pen"], 0.3, rel_tol=1e-9)

    def test_e6_legacy(self):
        """E6 蚀变于娄（旧）：进转魄额外朔望+1（2→3 满）+ 转魄中暴伤+50%."""
        compiled = _compiled(eidolon=6, version="legacy")
        eng = _make(compiled)
        s = _jl(eng)
        _cast(eng, "1212", "121202")
        _cast(eng, "1212", "121202")
        assert math.isclose(s.resources["syzygy"], 3.0), "2+1=3（旧版上限 3）"
        assert math.isclose(eng.pipeline.effective_stats(s)["crit_dmg"], CD + 0.5, rel_tol=1e-9)
