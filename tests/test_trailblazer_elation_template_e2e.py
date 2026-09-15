"""开拓者•欢愉 8010 模板端到端对轴（验收型批）：真模板 YAML → 编译 → 好活当赏条目账/
笑点账/天赋追加/终结技双分支/欢愉技段链/行迹/星魂全链 → 手算全等（过堂勘正十六件
见 fixture 头注；B40 迁移记六件同注）。8009 双子同套件——结构与口径对齐；唯一原语
口径差异：801020 收尾均摊段=hook 手算分母 ÷enemies_alive()（8009 为 action split:even
单承——同数值解，差异在案待上游统一，8009 勘正⑦）。

口径常数：开拓者 atk 465.696、行迹 atk_pct 0.28 → 实战面板 596.09088；crit_rate 面板
0.32（0.05+小节点 0.12+大行迹 0.15——trace_stat_effects 折入）、crit_dmg 面板 0.633
（0.5+小节点 0.133）→ 期望暴击区 1+0.32×0.633=1.20256。假人 def 1000 → 防御区 0.5、
雷弱点 → 抗性区 1.0、未击破 0.9。直伤链 Z=0.5×0.9×期望暴击区。
终结技暴伤 +50%（lv10）后 crit_dmg 1.133 → CZ_ULT=1.36256；
E5 暴伤 +54%（lv12）后 crit_dmg 1.173 → CZ_E5ULT=1.37536；
E6 暴伤再 +100% 后 crit_dmg 1.633 → CZ_E6=1.52256。

欢愉伤害真路由（B40 ⓵——ATK×倍率占位退役）：纯倍率×等级系数 LV_COEF=7535.107
×elation_multi×punchline_multi×期望暴击区×0.5×0.9，见 `_el`。8010 实战 atk
596.09088<1000 → 行迹 8010101 欢愉度 +0 → elation_multi=1.0；punchline_multi=
1+5·src/(src+240)，src 定槽（21_elation §21.2）：欢愉技 801020 全段=阿哈笑点池实时值
（终结技代放=固定计入 20——pool_override 覆写锚）；天赋追加段=max($team.
certified_banger)（官方「按我方最高好活当赏值计算」）。好活当赏=引擎原生条目列表
（st.banger_entries 逐条目独立 2 回合计时，eng._resource_value 读合并值——旧 modifier
CERTIFIED_BANGER 层账翻案，B40 ⓶）；笑点=队伍账 eng.state.punchline；欢愉技
action_type=elation_skill 正身（合法行动集引擎排除——体系触发行动，旧 available_if
闩退役，B40 ⓵）。
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

TB_ATK = 465.696 * 1.28                    # 行迹 atk_pct 0.28 后实战面板 = 596.09088
Z = 0.5 * 0.9 * (1 + 0.32 * 0.633)         # 直伤链：防御区×未击破×期望暴击区（行迹后面板）
CZ = 1 + 0.32 * 0.633                      # 期望暴击区（行迹后面板）= 1.20256
CZ_ULT = 1 + 0.32 * 1.133                  # 终结技暴伤 +0.5（lv10）后 = 1.36256
CZ_E5ULT = 1 + 0.32 * 1.173                # E5 终结技暴伤 +0.54（lv12）后 = 1.37536
CZ_E6 = 1 + 0.32 * 1.633                   # E6 暴伤再 +1.0 后 = 1.52256
LV_COEF = 7535.107                         # 欢愉伤害等级系数 Lv.80（rulebook elation_level_multiplier）


def _el(mult: float, src: float, cz: float) -> float:
    """欢愉伤害期望（expected 模式）：纯倍率×等级系数×笑点乘区×期望暴击区×防御区 0.5×未击破 0.9.

    mult=纯倍率；src=punchline_source（欢愉技=笑点池/代放固定 20，天赋追加=最高好活当赏合并值）；
    cz=期望暴击区（CZ 族）。elation_multi=1.0——面板欢愉度 0（atk<1000 行迹 8010101 不给）。
    """
    return mult * LV_COEF * (1 + 5 * src / (src + 240)) * cz * 0.45


def _build(*, eidolon: int = 0):
    member = {"character_template": "8010", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member,
        {"actor_id": "ally", "name": "辅手", "inline": True, "element": "thunder",
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "skill_point_gain": 1},
                     {"action_id": "ally_fua", "name": "追加", "action_type": "follow_up",
                      "target_type": "single", "damage_type": "thunder",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["thunder"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _compiled(*, eidolon: int = 0):
    return compile_encounter(_build(eidolon=eidolon), _STAGE,
                             template_roots=TEST_TEMPLATE_ROOTS)


@pytest.fixture(scope="module")
def compiled():
    return _compiled()


def _make(compiled, *, initial_sp: int = 3):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=initial_sp)
    eng.setup()
    return eng


def _tb(eng):
    return eng.state.actors["8010"]


def _remaining(eng, aid):
    return eng.scheduler._remaining[eng.scheduler._handles[aid]]


def _cast(eng, owner, aid, target_id="e1"):
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


def _ult(eng, target_id="8010"):
    st = _tb(eng)
    tgt = eng.state.actors[target_id]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    st.current_energy = 160.0
    ult = next(a for a in eng.actions_by_actor["8010"] if a.action_id == "801003")
    assert eng._fire_ultimate(st, ult) is True


class TestTrailblazerCompile:
    def test_actions_resources(self, compiled):
        acts = {a.action_id: a for a in compiled.actions_by_actor["8010"]}
        assert set(acts) == {"801001", "801002", "801003", "801020"}
        assert acts["801020"].action_type == "elation_skill", "欢愉技 action_type 正身（B40 ⓵）"
        assert not acts["801020"].split, (
            "收尾均摊段=hook 手算分母 ÷enemies_alive()——8009 双子为 split:even 单承，"
            "原语口径差异在案待上游统一（8009 勘正⑦）")
        assert acts["801003"].target_type == "ally_single", "指定我方单体（勘正⑪）"
        decls = compiled.resource_decls_by_actor["8010"]
        assert set(decls) == {"_tech_laugh", "banger_turns"}, (
            "笑点=队伍账/好活当赏=引擎原生条目列表——punchline/aha_turn 声明退役（B40 ⓵⓶）")

    def test_elation_skill_not_in_legal_set(self, compiled):
        """欢愉技=体系触发行动（阿哈时刻/代放族）——合法行动集引擎排除，顶替旧 available_if 闩（B40 ⓵）."""
        eng = _make(compiled)
        legal = legal_action_set(_tb(eng), eng.actions_by_actor["8010"], 5)
        assert "801020" not in {a.action_id for a in legal}


class TestBattleStart:
    def test_loadout(self, compiled):
        """进战两件（勘正⑩/B40 ⓶）：+1 笑点（欢愉角色×1）/ 好活当赏 20 点条目 2 回合；行迹面板."""
        eng = _make(compiled)
        st = _tb(eng)
        assert math.isclose(eng.state.punchline, 1.0), "§8.2 进战每欢愉角色 +1"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), (
            "§8.1 进战 20 点好活当赏（引擎统发，合并值口径）")
        assert st.banger_entries == [{"value": 20.0, "turns": 2.0}], (
            "引擎原生条目列表——单条目 20 点/2 回合独立计时（B40 ⓶）")
        assert "CERTIFIED_BANGER" not in st.modifiers, "旧 modifier 层账翻案摘除"
        eff = eng.pipeline.effective_stats(st)
        assert math.isclose(eff["crit_rate"], 0.32, rel_tol=1e-9), "0.05+行迹 0.27（勘正②折入）"
        assert math.isclose(eff["crit_dmg"], 0.633, rel_tol=1e-9), "0.5+行迹 0.133"
        assert math.isclose(eff["atk"], 465.696 * 1.28, rel_tol=1e-9), "atk_pct 0.28"


class TestBasicAndSkill:
    def test_basic_lv6(self, compiled):
        """普攻 lv6=index5=1.0 单体；产 1 点；回能 20+天赋 10=30；笑点 1+3=4；削韧 10."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z, rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, 0.0)
        assert math.isclose(eng.state.skill_points, 4.0), "产 1 点"
        assert math.isclose(st.current_energy, 30.0), "普攻回 20 + 天赋攻击后回 10"
        assert math.isclose(eng.state.punchline, 4.0), "天赋攻击后 +3 笑点"
        assert math.isclose(e1.toughness, 90.0), "削韧 10（三源互证，勘正⑫）"

    def test_skill_lv10_with_cb_extra(self, compiled):
        """战技 lv10：0.6 全体直伤 + 天赋追加 0.3 欢愉伤害（持好活当赏门；追加源=max($team.
        certified_banger)=进战 20）；自体好活当赏 20+20=40；耗 1 点；回能 30+10；削韧 20."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * 0.6 * Z + _el(0.3, 20, CZ), rel_tol=1e-9), (
            "战技 0.6 直伤 + 天赋追加 0.3 欢愉真路由（追加源=进战 20 合并值）")
        assert math.isclose(hp2 - e2.current_hp,
                            TB_ATK * 0.6 * Z + _el(0.3, 20, CZ), rel_tol=1e-9)
        assert math.isclose(eng.state.skill_points, 2.0), "耗 1 点"
        assert math.isclose(st.current_energy, 40.0), "战技回 30 + 天赋 10"
        assert math.isclose(eng.state.punchline, 4.0)
        assert math.isclose(e1.toughness, 80.0) and math.isclose(e2.toughness, 80.0)
        assert math.isclose(eng._resource_value(st, "certified_banger"), 40.0), (
            "进战 20 + 战技 20（条目列表合并加和=官方「合并计算」，B40 ⓶）")

    def test_skill_extra_gate_snapshot(self, compiled):
        """天赋追加门读事件开始旧值（族谱#9——resource_of 快照域）：好活当赏条目清空后施放
        战技→本发无追加，但战技发放钩仍新发 20 点条目（文本序：伤害在先获得在后）."""
        eng = _make(compiled)
        st = _tb(eng)
        st.banger_entries.clear()
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 0.6 * Z, rel_tol=1e-9)
        assert math.isclose(eng._resource_value(st, "certified_banger"), 20.0), "战技新发 20 点条目"


class TestUltimate:
    def test_self_target_branch_a(self, compiled):
        """终结技指自己（欢愉目标）：暴伤 +50% → 面板 1.133；好活当赏 20+10=30；立即代放
        欢愉技 lv10（固定计入 20 笑点 pool_override；吃暴伤后 CZ_ULT）：e1=8×0.2+均摊 0.3、
        e2=0.3（hook 手算分母 ÷2——双子口径差异在案）；+5 笑点/回 1 点；代放的欢愉技回 5 能
        （tbgd）再计天赋 +10 能 +3 笑点；阿哈挂账."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "8010")
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.5, rel_tol=1e-9), "暴伤 +50%（lv10）"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 30.0), "分支 A +10"
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.2 + 0.6 / 2, 20, CZ_ULT), rel_tol=1e-9), (
            "代放欢愉技：8 段×0.2+均摊 0.3，固定 20 笑点（暴伤挂在触发前——文本序一致）")
        assert math.isclose(hp2 - e2.current_hp, _el(0.6 / 2, 20, CZ_ULT), rel_tol=1e-9)
        assert math.isclose(eng.state.punchline, 9.0), "进战 1+终结技 5+天赋 3"
        assert math.isclose(st.current_energy, 20.0), "160 全扣→回 5+欢愉技 5+天赋 10"
        assert math.isclose(eng.state.skill_points, 4.0), "行迹 8010102：放大回 1 点"
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0), (
            "代放的欢愉技=我方施放 elation_skill → 阿哈咬它挂账（含自身，勘正⑭/B40 ⓵ 精确域）")
        assert math.isclose(e1.toughness, 100.0), "欢愉技削韧保守 0（待实测在案）"

    def test_ally_target_branch_b_and_dispel(self, compiled):
        """终结技指非欢愉队友：暴伤 +50% 挂队友 + 净化控制类（普通 debuff 保留）+
        行动提前 50%（-5000）；分支 A 不发（队友非欢愉命途、无好活当赏发放）；敌方零伤害."""
        eng = _make(compiled)
        ally = eng.state.actors["ally"]
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_FREEZE", name="冻结", modifier_type="control",
            control_kind="freeze", duration=2, dispellable=True))
        eng._apply_modifier(ally, Modifier(
            modifier_id="TEST_DOT", name="裂伤", modifier_type="debuff",
            duration=2, dispellable=True))
        e1 = eng.state.actors["e1"]
        hp1 = e1.current_hp
        before = _remaining(eng, "ally")
        _ult(eng, "ally")
        assert math.isclose(eng.pipeline.effective_stats(ally)["crit_dmg"],
                            0.5 + 0.5, rel_tol=1e-9), "指定队友暴伤 +50%（ally_single 勘正⑪）"
        assert "TEST_FREEZE" not in ally.modifiers, "控制类被净化（勘正⑧）"
        assert "TEST_DOT" in ally.modifiers, "非控制类 debuff 保留（触发域限 CC 子类）"
        assert math.isclose(before - _remaining(eng, "ally"), 5000.0, rel_tol=1e-9), (
            "分支 B：行动提前 50%（path_of 代理）")
        assert math.isclose(eng._resource_value(ally, "certified_banger"), 0.0), (
            "非欢愉目标不发放好活当赏")
        assert math.isclose(hp1 - e1.current_hp, 0.0), "不触发欢愉技"
        assert math.isclose(eng.state.skill_points, 4.0), "放大回 1 点"
        assert math.isclose(_tb(eng).current_energy, 5.0), "无天赋回能（未触发欢愉技）"
        assert math.isclose(eng.state.punchline, 6.0), "1+5"


class TestElationSkillManual:
    def test_segments_manual_axis(self, compiled):
        """欢愉技 lv10（手动对轴——体系触发行动不走合法集，直施对轴，8009 同法）：8 段随机
        0.2（expected 确定化首敌）+ 均摊 0.6/2（hook 手算分母），全段笑点池实时值（进战 1）；
        回 5+天赋 10 能；天赋 +3 笑点；阿哈咬它挂账；不耗点；削韧 0."""
        eng = _make(compiled)
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.2 + 0.6 / 2, 1, CZ), rel_tol=1e-9)
        assert math.isclose(hp2 - e2.current_hp, _el(0.6 / 2, 1, CZ), rel_tol=1e-9), (
            "均摊段 hook 手算分母 ÷enemies_alive()——与 8009 split:even 同数值解（差异在案）")
        assert math.isclose(st.current_energy, 15.0), "欢愉技回 5（tbgd）+天赋 10"
        assert math.isclose(eng.state.punchline, 4.0), "进战 1+天赋 3"
        assert math.isclose(eng.state.skill_points, 3.0), "不耗不产（tbgd）"
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0)
        assert math.isclose(e1.toughness, 100.0), "削韧保守 0（待实测在案）"

    def test_aha_sic_em_bank_and_clear(self, compiled):
        """阿哈咬它（行迹 8010103）：普攻不挂账；辅手追加（follow_up）亦不挂账——旧
        follow_up 代理退役，官方「施放欢愉技后」elation_skill 精确域（B40 ⓵）；自身欢愉技
        挂 1 层（含自身勘正⑭）→ 战技兑现 2×1=2：好活当赏 20+20+2=42，账摘."""
        eng = _make(compiled)
        st = _tb(eng)
        _cast(eng, "ally", "ally_basic")
        assert "AHA_SIC_EM_ARMED" not in st.modifiers, "普攻非欢愉技不挂账"
        _cast(eng, "ally", "ally_fua")
        assert "AHA_SIC_EM_ARMED" not in st.modifiers, (
            "follow_up 不挂账——旧代理退役，elation_skill 精确域")
        _cast(eng, "8010", "801020")
        assert math.isclose(st.modifiers["AHA_SIC_EM_ARMED"].stacks, 1.0), "自身欢愉技挂账（含自身）"
        _cast(eng, "8010", "801002")
        assert math.isclose(eng._resource_value(st, "certified_banger"), 42.0), (
            "进战 20+战技 20+清账 2×1（清账=独立新条目，合并加和口径）")
        assert "AHA_SIC_EM_ARMED" not in st.modifiers, "清账摘除"


class TestEidolons:
    def test_e1_armed_bank(self):
        """E1：战技×4 挂账钳 3 层（好活当赏 100）→ 终结技指自己：分支 A 10+E1 兑现
        2×min(3,3)=6=116，账摘；再战技（阿哈 +2）1 层 → 二大 +10+2=150（条目合并值与旧
        stacks 全等——读取改 eng._resource_value）."""
        eng = _make(_compiled(eidolon=1))
        st = _tb(eng)
        for _ in range(4):
            _cast(eng, "8010", "801002")
        assert math.isclose(st.modifiers["E1_CB_ARMED"].stacks, 3.0), "至多叠 3 层"
        assert math.isclose(eng._resource_value(st, "certified_banger"), 100.0), "进战 20+战技 4×20"
        _ult(eng, "8010")   # 代放 801020 → 阿哈挂账 1
        assert math.isclose(eng._resource_value(st, "certified_banger"), 116.0), (
            "100+分支A 10+E1 2×3（加算读，待实测在案）")
        assert "E1_CB_ARMED" not in st.modifiers, "下次终结技后清账"
        _cast(eng, "8010", "801002")   # +20 +阿哈 2×1 → 138；E1 挂 1 层
        assert math.isclose(eng._resource_value(st, "certified_banger"), 138.0)
        _ult(eng, "8010")
        assert math.isclose(eng._resource_value(st, "certified_banger"), 150.0), "138+10+E1 2×1"

    def test_e3_level_tracks(self):
        """E3（勘正①/B40 ⓺）：战技 lv12=0.66/天赋 lv12=0.33/欢愉技 lv11（0.21·0.63）；普攻仍 lv6."""
        eng = _make(_compiled(eidolon=3))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.21 + 0.63 / 2, 1, CZ), rel_tol=1e-9), "lv11：8×0.21+0.315"
        assert math.isclose(hp2 - e2.current_hp, _el(0.63 / 2, 1, CZ), rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801002")
        assert math.isclose(hp1 - e1.current_hp,
                            TB_ATK * 0.66 * Z + _el(0.33, 20, CZ), rel_tol=1e-9), (
            "战技 lv12=0.66 直伤 + 天赋追加 lv12=0.33 欢愉真路由（幻视族谱#18 联动取档）")
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z, rel_tol=1e-9), (
            "E3 不加普攻——仍 lv6=1.0")

    def test_e5_level_tracks(self):
        """E5：普攻 lv7=1.1（勘正①——非钳表尾）；终结技 lv12 暴伤 +54% → 面板 1.173；
        代放欢愉技 lv12（0.22·0.66，E3+E5 联动轨；固定 20 笑点 pool_override）."""
        eng = _make(_compiled(eidolon=5))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.1 * Z, rel_tol=1e-9), "普攻 lv7=1.1"
        hp1, hp2 = e1.current_hp, e2.current_hp
        _ult(eng, "8010")
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 0.54, rel_tol=1e-9), "暴伤 +54%（lv12）"
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.22 + 0.66 / 2, 20, CZ_E5ULT), rel_tol=1e-9), (
            "lv12：8×0.22+0.33，固定 20 笑点，暴伤后 CZ_E5ULT")
        assert math.isclose(hp2 - e2.current_hp, _el(0.66 / 2, 20, CZ_E5ULT), rel_tol=1e-9)

    def test_e4_vulnerability(self):
        """E4：欢愉技后敌方全体易伤 10%·2 回合（当次不吃勘正⑬）→ 下次普攻 ×1.1."""
        eng = _make(_compiled(eidolon=4))
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.21 + 0.63 / 2, 1, CZ), rel_tol=1e-9), (
            "E4 挂在结算后——本发不吃（eidolon=4 联动 E3，lv11 档）")
        assert math.isclose(eng.pipeline.effective_stats(e1)["vulnerability"], 0.1, rel_tol=1e-9)
        assert math.isclose(eng.pipeline.effective_stats(e2)["vulnerability"], 0.1, rel_tol=1e-9)
        assert math.isclose(e1.modifiers["E4_VULNERABILITY"].duration, 2.0)
        hp1 = e1.current_hp
        _cast(eng, "8010", "801001")
        assert math.isclose(hp1 - e1.current_hp, TB_ATK * 1.0 * Z * 1.1, rel_tol=1e-9), (
            "下次攻击吃易伤 ×1.1")

    def test_e6_crit_dmg_next_cast(self):
        """E6：欢愉技后自身暴伤 +100%·3 回合（当次不吃）→ 第二次欢愉技 lv12 全链（二发
        笑点池=进战 1+首发天赋 3=4）：e1=(8×0.22+0.33)×CZ_E6 链×1.1（E4 易伤随 eidolon=6 联动）."""
        eng = _make(_compiled(eidolon=6))
        st = _tb(eng)
        e1, e2 = eng.state.actors["e1"], eng.state.actors["e2"]
        hp1 = e1.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.22 + 0.66 / 2, 1, CZ), rel_tol=1e-9), "首发不吃 E6/E4（池=1）"
        assert "E6_CRIT_DMG" in st.modifiers
        assert math.isclose(st.modifiers["E6_CRIT_DMG"].duration, 3.0)
        assert math.isclose(eng.pipeline.effective_stats(st)["crit_dmg"],
                            0.633 + 1.0, rel_tol=1e-9)
        hp1, hp2 = e1.current_hp, e2.current_hp
        _cast(eng, "8010", "801020")
        assert math.isclose(hp1 - e1.current_hp,
                            _el(8 * 0.22 + 0.66 / 2, 4, CZ_E6) * 1.1, rel_tol=1e-9), (
            "二发吃 E6 暴伤+E4 易伤（池=1+3=4）")
        assert math.isclose(hp2 - e2.current_hp,
                            _el(0.66 / 2, 4, CZ_E6) * 1.1, rel_tol=1e-9)
