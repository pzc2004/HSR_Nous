"""流萤全机制模板端到端对轴（机制标注闭环试点验收 → 版本化拆分后=**legacy 轨**）：
真模板 YAML（version: legacy）→ 编译 → 完全燃烧全链.

链：天赋补能 50%（0→120）→ T1 战技 131002（耗血 40% 上限、回能 144=0.6×240、行动提前 25%）
→ 满大 → after 窗口终结技 131003（进【完全燃烧】、行动提前 100% 首动立即弹出、通用回能 5）
→ 倒计时 3 动（131009×2 耗点回血、131008×1 产点回血）→ 倒计时耗尽退出 → 技能组还原。
数值口径：战技回能 lv10 档（param(131002,3)=0.6×240=144，ERR 豁免清单具名——param() 回填勘正：旧取 lv15 行 0.65，fixture 约定档 = skill 10）；形态加成 lv10 档
（与 build 默认 skill_levels 对齐）。

版本双轨（2026-09-14 B39）：本文件钉 **legacy 轨**（1310xx——旧版：植弱单体 hook 通道 +
E2 旧版 CD）；enhanced 轨（11310xx——植弱主+相邻 apply_modifiers + E2 每回合重置）
见 TestFireflyEnhanced。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.scheduler import EXTRA_COUNTDOWN
from tests.template_materialize import TEST_TEMPLATE_ROOTS

MAX_HP = 814.968
MAX_ENERGY = 240.0
SKILL_ENERGY = 0.6 * MAX_ENERGY       # 144：131002 lv10 档回能（param 随档勘正——旧 lv15 行 0.65；ERR 豁免）
BASE_SPD = 114.0
COMBAT_SPD = BASE_SPD + 60.0          # 燃烧内面板速度 174（131003 lv10 #3）


def _build(*, eidolon: int = 0, version: str | None = "legacy", stage_enemies: list | None = None):
    member = {"character_template": "1310", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    if version:
        member["version"] = version
    enemies = stage_enemies or [
        # 木桩（无行动表=占位不攻击）；弱点不含 fire——验证 131009 植火弱
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}]
    build = {"build": {"team": [member],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "in_state", "action": "skill", "priority": 50},
                           {"condition": "not in_state", "action": "skill", "priority": 40},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": enemies,
        "termination": {"mode": "fixed_av", "max_action_value": 360}}}
    return build, stage


@pytest.fixture(scope="module")
def compiled():
    build, stage = _build()
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


def _run(compiled):
    """驱动一整场并采集探针.

    on_gain_energy 是 waterfall——订阅必须先于 setup()（on_battle_start 在 setup 内发射，
    天赋补能那笔晚了就漏记）。逐步 step 收集回合类型 / SP 轨迹 / 燃烧内面板速度快照。
    """
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    probe: dict = {"energy": [], "hp_down": [], "apply_mod": [],
                   "steps": [], "sp": [], "spd_in_state": []}
    eng.bus.subscribe_waterfall(
        "on_gain_energy", lambda et, p, ctx: probe["energy"].append(dict(p)) or None)
    eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: probe["hp_down"].append(dict(p)))
    eng.bus.subscribe("after_apply_modifier", lambda et, p, ctx: probe["apply_mod"].append(dict(p)))
    eng.setup()
    while True:
        r = eng.step()
        if r is None:
            break
        probe["steps"].append(r)
        probe["sp"].append(eng.state.skill_points)
        st = eng.state.actors["1310"]
        if st.state_config is not None:
            probe["spd_in_state"].append(eng.pipeline.effective_stats(st)["spd"])
    return eng, probe


class TestFireflyTemplateE2E:
    def test_state_config_registered_from_template(self, compiled):
        """模板 state_config 块经编译进引擎（非手动注册）."""
        assert "1310" in compiled.state_configs_by_actor
        cfg, entry = compiled.state_configs_by_actor["1310"]
        assert cfg.state == "complete_combustion" and entry == "131003"
        assert cfg.replaces_actions == {"basic": "131008", "skill": "131009"}
        assert cfg.locked_actions == ["ultimate"]
        assert math.isclose(cfg.stat_effects["spd"], 60.0)

    def test_skill_energy_gain_144(self, compiled):
        """验收①：战技回能 ≈ 0.6×240 = 144（不是固定 30；ERR 豁免，量精确）."""
        _, probe = _run(compiled)
        hits = [p for p in probe["energy"]
                if p.get("reason") == "effect" and math.isclose(p["amount"], SKILL_ENERGY)]
        assert len(hits) == 2, f"T1 + 退出燃烧后 T2 各一笔 144：{probe['energy']}"
        assert all(p["err_exempt"] for p in hits), "mechanics 05 §5.3 豁免清单具名流萤战技"

    def test_talent_battle_start_energy(self, compiled):
        """天赋：战斗开始能量不足 50% 补至 50%（0→120，ERR 豁免具名）."""
        _, probe = _run(compiled)
        hits = [p for p in probe["energy"] if math.isclose(p["amount"], 0.5 * MAX_ENERGY)]
        assert len(hits) == 1 and hits[0]["err_exempt"], f"天赋补能 120：{probe['energy']}"

    def test_combustion_enter_exit_and_countdown(self, compiled):
        """验收②：终结技后进【完全燃烧】+ 行动条 3 个倒计时回合 + 倒计时耗尽退出."""
        eng, probe = _run(compiled)
        log = eng.state.log
        assert any("进入形态 完全燃烧" in l for l in log)
        assert any("退出形态 完全燃烧" in l for l in log)
        cds = [s for s in probe["steps"] if s["kind"] == EXTRA_COUNTDOWN]
        assert len(cds) == 3 and all(s["actor_id"] == "1310" for s in cds), (
            f"倒计时 3 动（动数窗≈70 速倒计时）：{cds}")
        # 行动提前 100%：首个倒计时回合与 T1 战技同一时刻（immediate_action 立即弹出）
        assert math.isclose(cds[0]["clock"], probe["steps"][0]["clock"])
        assert eng.state.actors["1310"].state_config is None, "倒计时耗尽后形态已退出"

    def test_enhanced_actions_and_sp_ledger(self, compiled):
        """验收③⑤：燃烧内普攻变 131008（+1 点）、战技变 131009（-1 点不回能）；SP 账本全程."""
        eng, probe = _run(compiled)
        log = eng.state.log
        assert sum(1 for l in log if "火萤Ⅳ型-死星过载" in l) == 2, "131009×2（SP 2→1→0）"
        assert sum(1 for l in log if "火萤Ⅳ型-底火斩击" in l) == 1, "131008×1（SP 0→1）"
        bad = [p for p in probe["energy"] if str(p.get("action_id")) in ("131008", "131009")]
        assert not bad, f"强化普攻/战技不回能量（米游社回能0标签）：{bad}"
        # SP 账本：初始 3 起，流萤各行动后 = 战技2 → 强战1 → 强战0 → 强普1 → 战技0 → 普攻1
        ff_sp = [sp for s, sp in zip(probe["steps"], probe["sp"]) if s["actor_id"] == "1310"]
        assert ff_sp == [2, 1, 0, 1, 0, 1], f"SP 账本轨迹（初始 3）：{ff_sp}"

    def test_exit_restores_actions(self, compiled):
        """验收④：倒计时耗尽退出燃烧，技能组还原（退出日志后常态 131002/131001，强化件锁定）."""
        eng, _ = _run(compiled)
        log = eng.state.log
        exit_idx = next(i for i, l in enumerate(log) if "退出形态 完全燃烧" in l)
        after = log[exit_idx:]
        assert any("指令-天火轰击" in l for l in after), "131002 随退出还原可用"
        assert any("指令-闪燃推进" in l for l in after), "131001 随退出还原可用"
        assert not any("死星过载" in l or "底火斩击" in l for l in after), (
            "强化件仅在形态内合法（_legal_with_state 增强件过滤）")

    def test_skill_hp_cost_and_advance(self, compiled):
        """战技副效果：耗血 40% 上限（保底 1）；行动提前 25%（间隔 87.72×0.75=65.79 而非 87.72）."""
        _, probe = _run(compiled)
        drains = [p for p in probe["hp_down"]
                  if p["reason"] == "set_hp" and p["target"] == "1310"]
        assert len(drains) == 2 and all(
            math.isclose(p["amount"], 0.4 * MAX_HP, rel_tol=1e-6) for p in drains), (
            f"两次战技各耗 40% 生命上限：{drains}")
        ff_normal = [s for s in probe["steps"] if s["actor_id"] == "1310" and s["kind"] == "normal"]
        gap = ff_normal[-1]["clock"] - ff_normal[-2]["clock"]
        assert math.isclose(gap, 10000 / BASE_SPD * 0.75, abs_tol=0.01), (
            f"退出后 T2 战技行动提前 25%：间隔 {gap:.2f}（不提前应为 {10000 / BASE_SPD:.2f}）")

    def test_combustion_buffs_and_fire_weakness_implant(self, compiled):
        """形态加成与植弱：燃烧内面板速度恒 174（114+60）；131009 植火弱 2 回合
        （legacy=hook 通道单体——after_apply_modifier 探针取证）."""
        eng, probe = _run(compiled)
        assert probe["spd_in_state"] and all(
            math.isclose(s, COMBAT_SPD) for s in probe["spd_in_state"]), (
            f"燃烧内速度 +60：{probe['spd_in_state']}")
        implants = [p for p in probe["apply_mod"] if p["modifier_id"] == "FF_FIRE_WEAK"]
        assert implants and all(p["target"] == "e1" for p in implants), (
            f"131009 植火弱（legacy hook 单体；target 随回合走字 2 回合后过期）：{implants}")

    def test_enhanced_heal_and_post_exit_energy_rule(self, compiled):
        """强化技回血 + 退出燃烧后能量规则（官方：开大后余 5，后续按正常回能）."""
        eng, probe = _run(compiled)
        st = eng.state.actors["1310"]
        # 终态 hp = 0.6×上限：T1 耗 40% → 燃烧内强化技回血回满 → T2 再耗 40%；
        # 若强化技未回血，T2 后只剩 0.2×上限——0.6 与 0.2 之差即回血生效证据
        assert math.isclose(st.current_hp, 0.6 * MAX_HP, rel_tol=1e-6), (
            f"强化普攻 20% / 强化战技 25% 回血：hp={st.current_hp:.2f}")
        # 能量轨迹：开大消耗 240 → hook 补通用回能 5（吃 ERR）→ 战技 149 → 普攻 169
        assert math.isclose(st.current_energy, 169.0), (
            f"退出燃烧后能量 = 5 + 144 + 20：{st.current_energy}")
        assert any(math.isclose(p["amount"], 5.0) and not p["err_exempt"]
                   for p in probe["energy"]), "终结技通用回能 5（非豁免，吃 ERR）"


_TWO_ENEMIES = [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
     "max_toughness": 9999, "weakness": ["physical"]},
    {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100,
     "max_toughness": 9999, "weakness": ["physical"]}]


class TestFireflyEnhanced:
    """enhanced 轨（11310xx——默认 version 不落键）：植弱主+相邻 + E2 新版每回合重置."""

    def test_default_loads_enhanced_track(self):
        """默认（不写 version）= enhanced：11310xx 行动组 + state_config 换绑 + 植弱在 action."""
        build, stage = _build(version=None)
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        acts = {a.action_id for a in c.actions_by_actor["1310"]}
        assert acts == {"1131001", "1131002", "1131003", "1131008", "1131009"}
        cfg, entry = c.state_configs_by_actor["1310"]
        assert entry == "1131003"
        assert cfg.replaces_actions == {"basic": "1131008", "skill": "1131009"}
        spec = next(a for a in c.actions_by_actor["1310"]
                    if a.action_id == "1131009").apply_modifiers[0]
        assert spec["weakness_add"] == ["fire"] and spec["duration"] == 2

    def test_blast_weakness_implant_two_enemies(self):
        """新版植弱=主+相邻（apply_modifiers all_enemies 口径注在案）——双敌两只都中."""
        build, stage = _build(version=None, stage_enemies=_TWO_ENEMIES)
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        _, probe = _run(c)
        targets = {p["target"] for p in probe["apply_mod"]
                   if p["modifier_id"] == "FF_FIRE_WEAK"}
        assert targets == {"e1", "e2"}, f"新版植弱主+相邻（双敌=全场等价）：{targets}"

    def test_e2_extra_turn_reset_per_turn(self):
        """E2 新版：燃烧内击破→立即额外回合；闩同回合挡第二次；回合开始清零可再触发."""
        build, stage = _build(eidolon=2, version=None)
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1310"]
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "1131003")
        assert eng._fire_ultimate(st, ult) is True
        assert st.state_config is not None, "进完全燃烧（E2 触发域前提）"
        brk = {"source": "1310", "target": "e1", "element": "fire", "bar_index": 0}
        q0 = len(eng.scheduler._extra_queue)
        eng.bus.emit("on_break", dict(brk), eng.state)
        assert len(eng.scheduler._extra_queue) == q0 + 1, "首次击破→额外回合"
        assert math.isclose(st.resources["_e2_used"], 1.0)
        eng.bus.emit("on_break", dict(brk), eng.state)
        assert len(eng.scheduler._extra_queue) == q0 + 1, "同回合闩挡第二次"
        eng.bus.emit("on_turn_start", {"actor": "1310"}, eng.state)
        assert math.isclose(st.resources["_e2_used"], 0.0), "回合开始重置"
        eng.bus.emit("on_break", dict(brk), eng.state)
        assert len(eng.scheduler._extra_queue) == q0 + 2, "重置后可再触发"

    def test_e2_legacy_cooldown_semantics(self):
        """E2 旧版（legacy 轨）：CD「1 回合后可再次触发」——闩在回合**结束**清零
        （与新版回合**开始**清零分版，连动密度差异即加强点）."""
        build, stage = _build(eidolon=2, version="legacy")
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1310"]
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "131003")
        assert eng._fire_ultimate(st, ult) is True
        brk = {"source": "1310", "target": "e1", "element": "fire", "bar_index": 0}
        q0 = len(eng.scheduler._extra_queue)
        eng.bus.emit("on_break", dict(brk), eng.state)
        assert len(eng.scheduler._extra_queue) == q0 + 1
        assert math.isclose(st.resources["_e2_cd"], 1.0)
        eng.bus.emit("on_turn_start", {"actor": "1310"}, eng.state)
        assert math.isclose(st.resources["_e2_cd"], 1.0), "旧版回合开始**不**清零"
        eng.bus.emit("on_turn_end", {"actor": "1310"}, eng.state)
        assert math.isclose(st.resources["_e2_cd"], 0.0), "旧版回合结束清零 ≈ 隔一回合"
        eng.bus.emit("on_break", dict(brk), eng.state)
        assert len(eng.scheduler._extra_queue) == q0 + 2


class TestBetaModule:
    """β模组-自限装甲超击破转化（B38⑥）：enhanced 档 150%/300%→100%/150%，
    legacy 档 200%/360%→35%/50%；燃烧门控 + 阈值 stat_exprs 现场求值（含 α+25%/遗器动态）."""

    def test_enhanced_beta_tiers_and_gate(self):
        """enhanced：燃烧外 0；燃烧内基础 BE 0.996 不够档；抬到 1.696 → 1.0；抬到 3.196 → 1.5."""
        build, stage = _build(version=None)
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1310"]
        es = lambda: eng.pipeline.effective_stats(st).get("super_break_modifier", 0.0)
        assert es() == 0.0, "燃烧外 β 关（enable_if 门控）"
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "1131003")
        assert eng._fire_ultimate(st, ult) is True
        assert es() == 0.0, "燃烧内基础 BE 0.996（0.746+α 0.25）未达 150% 档"
        from hsr_nous.sim.state import Modifier
        eng._apply_modifier(st, Modifier(
            modifier_id="BE1", name="BE", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 0.7}))
        assert math.isclose(es(), 1.0, rel_tol=1e-9), "BE 1.696 ≥ 150% → 转化 100%"
        eng._apply_modifier(st, Modifier(
            modifier_id="BE2", name="BE2", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 1.5}))
        assert math.isclose(es(), 1.5, rel_tol=1e-9), "BE 3.196 ≥ 300% → 转化 150%"

    def test_enhanced_super_break_chain(self):
        """燃烧内 BE 1.696：强战首发破敌（直伤+击破）→ 二发超击破
        = 30（20×1.5 效率）×系数×2.696×0.5×转化 1.0（舞台韧性 100 档——击破基数按满韧读）."""
        build, stage = _build(version=None, stage_enemies=[
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
             "max_toughness": 100, "weakness": ["physical"]}])
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1310"]
        from hsr_nous.sim.state import Modifier
        eng._apply_modifier(st, Modifier(
            modifier_id="BE1", name="BE", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 0.7}))
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "1131003")
        assert eng._fire_ultimate(st, ult) is True
        tgt = eng.state.actors["e1"]
        tgt.toughness = 15.0   # 强战 20×1.5=30 首发即破（植火弱同动作生效——fire 削韧放行实证）
        eng.decision.select_target = lambda a, t, cands, e: (
            tgt if tgt in cands else (cands[0] if cands else None))
        eskill = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "1131009")
        hp = tgt.current_hp
        eng._execute_action(st, eskill)
        assert tgt.broken
        direct1 = 2.0 * 523.908 * 0.5 * 1.025 * 0.9
        brk = 3767.5533 * 2.0 * 3.0 * 2.696 * 0.5
        assert math.isclose(hp - tgt.current_hp, direct1 + brk, rel_tol=1e-6), (
            "首发：直伤（未击破 0.9）+ 击破伤害（be 2.696，满韧 100 档 (0.5+100/40)=3.0）")
        hp2 = tgt.current_hp
        eng._execute_action(st, eskill)
        direct2 = 2.0 * 523.908 * 0.5 * 1.025
        sb = 376.75533 * 30 * 2.696 * 0.5 * 1.0
        assert math.isclose(hp2 - tgt.current_hp, direct2 + sb, rel_tol=1e-6), (
            "二发：直伤（已击破）+ 超击破（有效削韧 30=20×1.5 效率）")

    def test_legacy_beta_tiers_and_alpha_correction(self):
        """legacy：燃烧内 BE 不得含 α+25%（行迹层版本勘正实证）；BE 2.046 → 0.35、
        3.646 → 0.5（旧版档显著低于加强版）."""
        build, stage = _build(version="legacy")
        c = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        st = eng.state.actors["1310"]
        st.current_energy = 240.0
        ult = next(a for a in eng.actions_by_actor["1310"] if a.action_id == "131003")
        assert eng._fire_ultimate(st, ult) is True
        assert math.isclose(eng.pipeline.effective_stats(st)["break_effect"],
                            0.746, rel_tol=1e-9), "旧版无 α+25%（勘正实证）"
        es = lambda: eng.pipeline.effective_stats(st).get("super_break_modifier", 0.0)
        from hsr_nous.sim.state import Modifier
        eng._apply_modifier(st, Modifier(
            modifier_id="BE1", name="BE", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 1.3}))
        assert math.isclose(es(), 0.35, rel_tol=1e-9), "BE 2.046 ≥ 200% → 转化 35%"
        eng._apply_modifier(st, Modifier(
            modifier_id="BE2", name="BE2", modifier_type="buff",
            duration=0, dispellable=False, stat_effects={"break_effect": 1.6}))
        assert math.isclose(es(), 0.5, rel_tol=1e-9), "BE 3.646 ≥ 360% → 转化 50%"
