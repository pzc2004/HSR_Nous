"""记忆战舰星魂全档位对照验收（demo_记忆战舰 队 E0→E6 ladder）.

同口径：`data/battles/demo_记忆战舰.yaml` 编译链 + `tests/fixtures/templates` 人工根
（= CLI `hsr-sim run --config demo_记忆战舰 --templates tests/fixtures/templates`）；
每档把四个 member.eidolon 同置 N → compile → 固定 50 行动截断局（沙包血池打不完，
步数预算各档一致=对照公平；MAX_TURNS_SAFETY 全量 200 档十倍耗时无增量信息）。
MODE_EXPECTED 确定化求期望（对照可复现；CLI 默认 roll 口径仅掷骰/期望之差）。

断言（任务两道）：
① 每档总伤 ≥ 前一档（星魂单调不减——纯数值魂也有正贡献）；
② 机制魂档位有差异化事件（新增触发在事件流/修饰件清单可观察；等级族档 E3/E5
   以编译层 skill_levels 跳档 + ladder 总伤差为差异化）。
ladder 表打印在测试日志（pytest -s 可见）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests._data_env import data_available, data_skip_reason
from tests.template_materialize import TEST_TEMPLATE_ROOTS

pytestmark = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

_BATTLE = Path("data/battles/demo_记忆战舰.yaml")
_STEP_BUDGET = 50          # 每档行动预算（截断局——七档同预算对照）

#: 机制魂档位 → 差异化信号（after_apply_modifier 的 modifier_id / 战斗日志子串）：
#: 每档四角色该级星魂的可观察新增件（至少一条命中即差异化成立）
_MECH_MARKERS = {
    1: ["E1_MEMO_FINAL_DMG", "E1_AFTER_RAIN_HP", "献予「真我」之诗·E1"],
    2: ["E2_ARDENT_WILL", "E2_COURTYARD_SPD", "E2_EVEY_CRIT_DMG"],
    4: ["E4_INCOMING_HEAL", "E4_MEMO_BREAK_EFF", "HYACINE_STORM_CALM_E4", "E4_MINUET_N"],
    6: ["E6_SKY_RES_PEN", "E6_TEAM_RES_PEN", "E6_NW_RES_PEN", "E6_ODE_DEF_SHRED"],
}
#: 等级族档位 → 编译层差异化（逐角色 skill_levels 跳档——四角色 E3/E5 键位各异照官方文本）
_LEVEL_RUNGS = {
    3: {"1407": {"ultimate": 12, "basic": 7}, "1409": {"ultimate": 12, "basic": 7},
        "1413": {"skill": 12, "basic": 7}, "1415": {"ultimate": 12, "talent": 12}},
    5: {"1407": {"skill": 12, "talent": 12}, "1409": {"skill": 12, "talent": 12},
        "1413": {"ultimate": 12, "talent": 12}, "1415": {"skill": 12, "basic": 7}},
}


def _demo_build_stage(eidolon: int):
    raw = yaml.safe_load(_BATTLE.read_text(encoding="utf-8"))
    build = yaml.safe_load(raw["build_yaml"])
    stage = yaml.safe_load(raw["stage_yaml"])
    for m in build["build"]["team"]:
        m["eidolon"] = eidolon
    return build, stage


def _rung(n: int):
    """单档：编译 + 固定预算截断 run → (state, 触发件集, 日志文本, 四角色 skill_levels)."""
    build, stage = _demo_build_stage(n)
    compiled = compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED)
    applied: list[str] = []
    eng.bus.subscribe("after_apply_modifier",
                      lambda et, p, ctx: applied.append(str(p.get("modifier_id", ""))))
    eng.setup()
    for _ in range(_STEP_BUDGET):
        if eng.step() is None:
            break
    levels = {a.actor_id: dict(a.skill_levels) for a in compiled.build_team}
    return eng.state, set(applied), "\n".join(eng.state.log), levels


@pytest.fixture(scope="module")
def ladder():
    """E0→E6 七档全跑（模块级一次——ladder 表与逐档断言共用）."""
    return {n: _rung(n) for n in range(7)}


class TestRemembranceEidolonLadder:
    def test_damage_monotonic_non_decreasing(self, ladder, capsys):
        rows = []
        for n in range(7):
            state = ladder[n][0]
            rows.append((n, state.total_damage, state.turn_count, state.truncated))
        with capsys.disabled():
            print("\n===== 记忆战舰星魂 ladder（demo_记忆战舰 full run 截断局，EXPECTED）=====")
            print(f"{'档位':<4}{'总伤':>18}{'行动数':>8}{'截断':>6}")
            for n, dmg, turns, trunc in rows:
                print(f"E{n:<3}{dmg:>18,.0f}{turns:>8}{'⚠' if trunc else '':>6}")
        for n in range(1, 7):
            assert rows[n][1] >= rows[n - 1][1] - 1e-6, (
                f"星魂单调性：E{n} 总伤 {rows[n][1]:,.0f} < E{n - 1} {rows[n - 1][1]:,.0f}")

    def test_mechanism_rungs_have_differential_signals(self, ladder):
        for n, markers in _MECH_MARKERS.items():
            _state, applied, log, _lv = ladder[n]
            hits = [m for m in markers if m in applied or m in log]
            assert hits, f"E{n} 机制魂无差异化信号（候选 {markers} 均未在事件流/修饰件出现）"

    def test_level_rungs_bump_skill_levels(self, ladder):
        for n, per_char in _LEVEL_RUNGS.items():
            levels = ladder[n][3]
            prev = ladder[n - 1][3]
            for aid, expect in per_char.items():
                for key, want in expect.items():
                    assert levels[aid].get(key) == want, (
                        f"E{n}：{aid} {key} 应为 {want}，实得 {levels[aid].get(key)}")
                    assert levels[aid].get(key, 0) > prev[aid].get(key, 0), (
                        f"E{n} vs E{n - 1}：{aid} {key} 无跳档")
