"""流萤全机制模板端到端对轴（机制标注闭环试点验收）：真模板 YAML → 编译 → 完全燃烧全链.

链：天赋补能 50%（0→120）→ T1 战技 131002（耗血 40% 上限、回能 144=0.6×240、行动提前 25%）
→ 满大 → after 窗口终结技 131003（进【完全燃烧】、行动提前 100% 首动立即弹出、通用回能 5）
→ 倒计时 3 动（131009×2 耗点回血、131008×1 产点回血）→ 倒计时耗尽退出 → 技能组还原。
数值口径：战技回能 lv10 档（param(131002,3)=0.6×240=144，ERR 豁免清单具名——param() 回填勘正：旧取 lv15 行 0.65，fixture 约定档 = skill 10）；形态加成 lv10 档
（与 build 默认 skill_levels 对齐）。
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


@pytest.fixture(scope="module")
def compiled():
    build = {"build": {"team": [{"character_template": "1310", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "in_state", "action": "skill", "priority": 50},
                           {"condition": "not in_state", "action": "skill", "priority": 40},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        # 木桩（无行动表=占位不攻击）；弱点不含 fire——验证 131009 植火弱
        {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": 360}}}
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
        """形态加成与植弱：燃烧内面板速度恒 174（114+60）；131009 植火弱 2 回合."""
        eng, probe = _run(compiled)
        assert probe["spd_in_state"] and all(
            math.isclose(s, COMBAT_SPD) for s in probe["spd_in_state"]), (
            f"燃烧内速度 +60：{probe['spd_in_state']}")
        implants = [p for p in probe["apply_mod"] if p["modifier_id"] == "FF_FIRE_WEAK"]
        assert implants and all(p["target"] == "e1" for p in implants), (
            f"131009 植火弱（target 随回合走字 2 回合后过期，故探针取证）：{implants}")
        act = next(a for a in compiled.actions_by_actor["1310"] if a.action_id == "131009")
        spec = act.apply_modifiers[0]
        assert spec["weakness_add"] == ["fire"] and spec["duration"] == 2

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
