"""蒙特卡洛实验层 e2e 钉：终止模式 survival/wipe、结果分类器、指标族、CSV、版本指纹.

四件交付（sim/montecarlo.py 模块 docstring 为口径唯一来源，本文件逐件钉死）：
- ① survival/wipe 终止：通则双分支 + AV 预算外框（各两钉——测量/达成终点与预算外框）；
- ② 结果分类器五态：win（zero_cycle/stable 双旗标）/ loss / timeout / truncated / 无轮次注明；
- ③ 指标族手算对轴：CVaR 纯函数、expected 模式全键、能量循环（ult 计数 + 平均每动回能）、
  混合 factory 比率、truncated 局只计数不进分母；
- ④ CSV 行格式 + 版本指纹五键与文件内容逐位一致（测试独立重算——共享源必验）。
"""
from __future__ import annotations

import csv
import hashlib
import math
import subprocess
from pathlib import Path

import pytest

from hsr_nous.sim import montecarlo as mc
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim_schema import rulebook as _rulebook_mod
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Cycle, Encounter, TerminationConfig
from hsr_nous.sim_schema.templates import RUNTIME_TEMPLATE_ROOTS

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 构建件（全手算对轴场景：速度/预算/血量全部摆得明明白白）
# ---------------------------------------------------------------------------

def _basic() -> Action:
    return Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                  damage_type="fire", scaling=[{"atk": 1.0}], toughness_dmg=10)


def _enemy_basic() -> Action:
    return Action(action_id="eatk", name="敌普攻", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=0)


def _eng(seed: int = 0, *, hero_atk: float = 2000, hero_hp: float = 3000,
         hero_spd: float = 150, enemy_hp: float = 1e9, enemy_atk: float = 0.0,
         enemy_spd: float = 100, mode: str = "fixed_av", mav: float = 70.0,
         cycle: "Cycle | None" = None, max_energy: int = 100, ier: float = 0.0,
         with_ult: bool = False, enemy_fights: bool = False,
         extra_heroes: "list[Actor] | None" = None) -> CombatEngine:
    """单攻手 + 单假人的最小战斗（enemy_fights=True 时假人持普攻行动会打人）."""
    hero = Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=hero_atk, spd=hero_spd, hp=hero_hp, max_energy=max_energy,
                                 crit_rate=0.5, crit_dmg=1.0))  # 期望模式 ×1.5——v08 1350 钉同口径
    dummy = Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                  stats=StatBlock(hp=enemy_hp, spd=enemy_spd, atk=enemy_atk,
                                  max_toughness=9999, weakness=["fire"]))
    actions = {"atk": [_basic()]}
    if with_ult:
        actions["atk"].append(
            Action(action_id="ult", name="终结技", action_type="ultimate", target_type="single",
                   damage_type="fire", scaling=[{"atk": 3.0}], energy_cost=max_energy))
    if enemy_fights:
        actions["e1"] = [_enemy_basic()]
    actors = [hero] + list(extra_heroes or []) + [dummy]
    enc = Encounter(encounter_id="t", name="t", actors=actors, cycle=cycle,
                    termination=TerminationConfig(mode=mode, max_action_value=mav))
    eng = CombatEngine(enc, actions_by_actor=actions,
                       policy=ScriptedPolicy(rotation=["basic"]), mode=MODE_EXPECTED,
                       seed=seed, initial_sp=3, initial_energy_ratio=ier)
    eng.setup()
    return eng


def _battle_end_reasons(eng: CombatEngine) -> "list[str]":
    reasons: "list[str]" = []
    eng.bus.subscribe("battle_end", lambda et, p, ctx: reasons.append(p["reason"]))
    return reasons


# ---------------------------------------------------------------------------
# ① survival / wipe 终止模式（通则双分支 + AV 预算外框，10_termination.md）
# ---------------------------------------------------------------------------

class TestSurvivalWipeTermination:
    def test_survival_ends_at_party_wipe(self):
        """survival 生效钉①：我方团灭 = 生存测量终点——预算远未耗尽即停（不停到预算）."""
        eng = _eng(hero_hp=50, enemy_atk=99999, enemy_spd=200, enemy_hp=1e18,
                   mode="survival", mav=10000, enemy_fights=True)
        reasons = _battle_end_reasons(eng)
        state = eng.run()
        assert reasons == ["all_allies_dead"]
        assert not state.actors["atk"].alive
        assert state.clock < 10000, "团灭即终局，不得拖到预算线"
        assert not state.truncated

    def test_survival_budget_frame_when_team_unkillable(self):
        """survival 生效钉②：我方打不死、敌方打不动 → 满预算截断（存活通过窗口）."""
        eng = _eng(hero_atk=1, hero_hp=1e9, enemy_atk=1, enemy_hp=1e18,
                   mode="survival", mav=300, enemy_fights=True)
        reasons = _battle_end_reasons(eng)
        state = eng.run()
        assert reasons == ["max_action_value_reached"]
        assert state.actors["atk"].alive and state.clock >= 300
        assert not state.truncated

    def test_wipe_ends_at_kill_moment(self):
        """wipe 生效钉①：对面全灭 = 全灭达成——终止于击杀时点（不停到预算）."""
        eng = _eng(enemy_hp=500, mode="wipe", mav=10000)
        reasons = _battle_end_reasons(eng)
        state = eng.run()
        assert reasons == ["target_killed"]
        assert not state.actors["e1"].alive
        assert state.clock < 10000, "杀光即终局，不得拖到预算线"

    def test_wipe_budget_exhausted_reports_remaining(self):
        """wipe 生效钉②：预算耗尽未全灭 → AV 外框截断，残余敌方存活进结果记录."""
        eng = _eng(hero_atk=1, hero_hp=1e9, enemy_atk=1, enemy_hp=1e18,
                   mode="wipe", mav=300, enemy_fights=True)
        reasons = _battle_end_reasons(eng)
        eng.run()
        rec = mc.classify_outcome(eng)
        assert reasons == ["max_action_value_reached"]
        assert rec.outcome == "timeout" and rec.enemies_alive == 1


# ---------------------------------------------------------------------------
# ② 结果分类器五态
# ---------------------------------------------------------------------------

class TestOutcomeClassifier:
    def test_win_zero_cycle_and_stable_clear(self):
        """win + 0T + 稳通：轮次配置下首动（AV≈66.7 < 首轮预算 150）一击杀."""
        eng = _eng(enemy_hp=500, cycle=Cycle(first_cycle_av=150, subsequent_cycle_av=100),
                   mav=1e9)
        eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.outcome == "win"
        assert rec.cycle_enabled and rec.cycles_used == 1, "首轮内终结 = 0T 评分基础"
        assert rec.zero_cycle_kill and rec.stable_clear
        assert rec.allies_alive == 1 and rec.enemies_alive == 0

    def test_win_without_cycle_config_zero_cycle_false(self):
        """无轮次配置：zero_cycle_kill 恒 False 且 cycle_enabled=False 注明（0T 无定义不脑补）."""
        eng = _eng(enemy_hp=500, mav=1e9)
        eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.outcome == "win"
        assert rec.cycle_enabled is False and rec.zero_cycle_kill is False

    def test_win_with_ally_death_not_stable(self):
        """win 但减员 → stable_clear=False：敌方先手秒杀脆皮队友，攻手随后首轮内反杀."""
        fragile = Actor(actor_id="fr", name="脆皮", level=80,
                        stats=StatBlock(atk=1, spd=100, hp=50, max_energy=100, taunt=1000))
        eng = _eng(enemy_hp=500, enemy_atk=99999, enemy_spd=200, mav=1e9,
                   cycle=Cycle(first_cycle_av=150, subsequent_cycle_av=100),
                   enemy_fights=True, extra_heroes=[fragile])
        eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.outcome == "win"
        assert rec.allies_alive == 1, "脆皮阵亡、攻手存活"
        assert rec.stable_clear is False and rec.zero_cycle_kill is True

    def test_loss_party_wipe(self):
        """loss：敌方团灭我方（存活在场口径）."""
        eng = _eng(hero_hp=50, enemy_atk=99999, enemy_spd=200, enemy_hp=1e18,
                   mav=1e9, enemy_fights=True)
        eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.outcome == "loss"
        assert rec.allies_alive == 0 and rec.enemies_alive == 1
        assert not rec.zero_cycle_kill and not rec.stable_clear

    def test_timeout_fixed_av_sandbag(self):
        """timeout：fixed_av 打木桩预算耗尽，双方均存活."""
        eng = _eng()
        eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.outcome == "timeout"
        assert rec.allies_alive == 1 and rec.enemies_alive == 1

    def test_truncated_record_is_timeout(self):
        """截断局：outcome=timeout 且 truncated=True（毒数据标记，聚合层只计数）."""
        eng = _eng(hero_atk=1, hero_hp=1e9, enemy_hp=1e18, mav=1e15)
        with pytest.warns(RuntimeWarning, match="截断"):
            eng.run()
        rec = mc.classify_outcome(eng)
        assert rec.truncated and rec.outcome == "timeout"


# ---------------------------------------------------------------------------
# ③ 指标族手算对轴
# ---------------------------------------------------------------------------

class TestCvarHandCalc:
    def test_two_point_distribution(self):
        """[900×50, 1800×50]：p=0.05 → k=5 全 900；p=0.5 → k=50 全 900；p=1.0 → 全体均值 1350."""
        vals = [900.0] * 50 + [1800.0] * 50
        assert math.isclose(mc.cvar(vals, 0.05), 900.0)
        assert math.isclose(mc.cvar(vals, 0.5), 900.0)
        assert math.isclose(mc.cvar(vals, 1.0), 1350.0)

    def test_arithmetic_sequence(self):
        """1..20 升序：p=0.1 → k=floor(2)=2 → (1+2)/2=1.5；k 下限 1（p→0 取最差单样本）."""
        vals = [float(i) for i in range(1, 21)]
        assert math.isclose(mc.cvar(vals, 0.1), 1.5)
        assert math.isclose(mc.cvar(vals, 1e-9), 1.0)

    def test_invalid_p_raises(self):
        with pytest.raises(ValueError, match="∈"):
            mc.cvar([1.0], 0.0)
        with pytest.raises(ValueError, match="∈"):
            mc.run(_eng, n=1, cvar_p=1.5)


class TestRunMetricsHandCalc:
    def test_expected_mode_full_summary(self):
        """expected 模式 n=5（v08 同工厂：单动打木桩 fixed_av 70）全键对轴.

        手算：单发普攻期望 1350（不暴 900/暴 1800 两点，crit 0.5×1.0）；basic 默认回能
        20（rulebook energy 节）×1 动 = energy_gained 20、每动 20.0；无终结技。
        """
        res = mc.run(_eng, n=5, seed0=0, policy_source="rotation=[basic]")
        assert len(res.outcomes) == 5
        assert all(r.outcome == "timeout" for r in res.outcomes)
        s = res.summary
        assert s["n"] == 5 and s["n_truncated"] == 0
        assert s["win_rate"] == 0.0 and s["wipe_rate"] == 0.0
        assert s["zero_cycle_kill_rate"] == 0.0 and s["stable_clear_rate"] == 0.0
        assert math.isclose(s["total_damage"].mean, 1350.0, rel_tol=1e-9)
        assert math.isclose(s["cvar"], 1350.0, rel_tol=1e-9)  # 常数样本任意 p 同值
        assert s["cvar_p"] == 0.05
        assert math.isclose(s["ult_casts_mean"], 0.0)
        assert math.isclose(s["energy_gain_per_action_mean"], 20.0, rel_tol=1e-9)

    def test_ult_and_energy_cycle_hand_calc(self):
        """能量循环钉：max_energy 40 + 开局半能 20，fixed_av 150 / spd 150（66.7/133.3 两动）.

        手算：动1 普攻 +20 → 满 40 → 行动后窗口开大（耗 40 → 0，终结技默认回能 +5）；
        动2 普攻 +20 → 25。ult_casts=1；on_action 三发（普攻×2 + 终结技——双发机制）；
        energy_gained=20+5+20=45；每动 45/3=15.0。
        """
        factory = lambda seed: _eng(seed=seed, max_energy=40, ier=0.5, mav=150.0, with_ult=True)
        res = mc.run(factory, n=3, seed0=0)
        r = res.outcomes[0]
        assert r.ult_casts == 1
        assert math.isclose(r.energy_gained, 45.0, rel_tol=1e-9)
        assert math.isclose(r.energy_gain_per_action, 15.0, rel_tol=1e-9)
        assert math.isclose(res.summary["ult_casts_mean"], 1.0)
        assert math.isclose(res.summary["energy_gain_per_action_mean"], 15.0, rel_tol=1e-9)

    def test_mixed_factory_rates(self):
        """混合 factory：seed<2 一击杀（有轮次配置），其余打木桩——win/zck/stable 各 0.5."""

        def mixed(seed: int) -> CombatEngine:
            if seed < 2:
                return _eng(seed=seed, enemy_hp=500,
                            cycle=Cycle(first_cycle_av=150, subsequent_cycle_av=100), mav=1e9)
            return _eng(seed=seed)

        res = mc.run(mixed, n=4, seed0=0)
        s = res.summary
        assert s["n"] == 4
        assert math.isclose(s["win_rate"], 0.5)
        assert math.isclose(s["zero_cycle_kill_rate"], 0.5)
        assert math.isclose(s["stable_clear_rate"], 0.5)
        assert math.isclose(s["wipe_rate"], 0.0)
        assert [r.cycles_used for r in res.outcomes[:2]] == [1, 1]

    def test_truncated_excluded_from_rates(self):
        """truncated 局只计 n_truncated、不进比率分母（毒数据防线与 run_distribution 同口径）."""

        def mixed(seed: int) -> CombatEngine:
            if seed < 2:
                return _eng(seed=seed, hero_atk=1, hero_hp=1e9, enemy_hp=1e18, mav=1e15)
            return _eng(seed=seed)

        with pytest.warns(RuntimeWarning, match="截断"):
            res = mc.run(mixed, n=6, seed0=0)
        s = res.summary
        assert s["n"] == 4 and s["n_truncated"] == 2
        assert math.isclose(s["total_damage"].mean, 1350.0, rel_tol=1e-9)
        assert all(r.truncated for r in res.outcomes[:2])

    def test_all_truncated_raises(self):
        factory = lambda seed: _eng(seed=seed, hero_atk=1, hero_hp=1e9, enemy_hp=1e18, mav=1e15)
        with pytest.warns(RuntimeWarning), \
                pytest.raises(ValueError, match="全部 truncated"):
            mc.run(factory, n=2, seed0=0)

    def test_reproducible_same_seed0(self):
        """同 seed0 两趟实验：trial_id / outcomes / summary 逐字段全等（B16 聚合层）."""
        r1 = mc.run(_eng, n=5, seed0=7)
        r2 = mc.run(_eng, n=5, seed0=7)
        assert r1.trial_id == r2.trial_id
        assert r1.outcomes == r2.outcomes
        assert r1.summary == r2.summary


# ---------------------------------------------------------------------------
# ④ 事件级 CSV + 版本绑定指纹
# ---------------------------------------------------------------------------

class TestCsvExport:
    @staticmethod
    def _read(csv_path: str):
        text = Path(csv_path).read_text(encoding="utf-8")
        comments = [ln for ln in text.splitlines() if ln.startswith("#")]
        rows = [r for r in csv.reader(text.splitlines()) if r and not r[0].startswith("#")]
        return comments, rows

    def test_csv_rows_format(self, tmp_path):
        """CSV：头注（trial_id/版本/口径）+ 列头 + 每事件一行 9 字段，行内容抽查对轴."""
        path = str(tmp_path / "ev.csv")
        res = mc.run(_eng, n=2, seed0=0, csv_path=path)
        assert res.csv_path == path
        comments, rows = self._read(path)
        assert any("trial_id: " + res.trial_id in c for c in comments)
        assert any(c.startswith("# version: {") and "rulebook_hash" in c for c in comments)
        assert any("event_type 词表" in c for c in comments), "口径头注必须在场"
        assert rows[0] == ["trial_id", "run_id", "clock", "actor", "action_id",
                           "action_type", "target", "value", "event_type"]
        data = rows[1:]
        assert data and all(len(r) == 9 for r in data), "每事件一行 9 字段"
        assert {r[0] for r in data} == {res.trial_id}, "trial_id 列恒为本次实验 id"
        assert {r[1] for r in data} == {"0", "1"}, "run_id = 世界线种子"
        types = {r[8] for r in data}
        assert {"action", "energy_gain", "damage", "battle_end"} <= types
        # 抽查：普攻行动行（actor/action_id/action_type 对轴；value=实际耗点 0）
        act = next(r for r in data if r[8] == "action" and r[4] == "basic")
        assert act[3] == "atk" and act[5] == "basic" and act[6] == "e1" and act[7] == "0"
        # 抽查：回能行 value=20（basic 默认回能）；终局行 value=fixed_av 截断原因
        eg = next(r for r in data if r[8] == "energy_gain")
        assert eg[3] == "atk" and float(eg[7]) == 20.0
        assert {r[7] for r in data if r[8] == "battle_end"} == {"max_action_value_reached"}

    def test_csv_env_var_switch(self, tmp_path, monkeypatch):
        """环境变量开关：HSR_NOUS_MC_CSV 给路径即写（csv_path 参数缺省时）."""
        path = str(tmp_path / "env.csv")
        monkeypatch.setenv("HSR_NOUS_MC_CSV", path)
        res = mc.run(_eng, n=1, seed0=0)
        assert res.csv_path == path and Path(path).is_file()

    def test_csv_disabled_by_default(self):
        assert mc.run(_eng, n=1, seed0=0).csv_path is None


class TestVersionFingerprint:
    def test_five_keys_present(self):
        v = mc.collect_version_fingerprint(policy_source="abc")
        assert set(v) == {"git_commit", "rulebook_hash", "fixtures_hash",
                          "data_hash", "policy_hash"}

    def test_hashes_match_file_contents(self):
        """五键与文件内容逐位一致（测试独立重算——共享源必验，不抄实现件）."""
        v = mc.collect_version_fingerprint(policy_source="策略原文")
        # git_commit：subprocess 同法现算（非 git 环境容忍 None）
        try:
            r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT,
                               capture_output=True, text=True, timeout=10)
            expect_commit = r.stdout.strip() if r.returncode == 0 else None
        except OSError:
            expect_commit = None
        assert v["git_commit"] == expect_commit
        # rulebook_hash：rulebook.yaml 字节 sha256
        rulebook = Path(_rulebook_mod.__file__).resolve().parent / "rulebook.yaml"
        assert v["rulebook_hash"] == hashlib.sha256(rulebook.read_bytes()).hexdigest()
        # fixtures_hash：RUNTIME_TEMPLATE_ROOTS 全量 YAML 独立重算（根名/相对路径+字节链入）
        h = hashlib.sha256()
        n = 0
        for name in RUNTIME_TEMPLATE_ROOTS:
            root = _REPO_ROOT / name
            if not root.is_dir():
                continue
            for p in sorted(q for q in root.rglob("*")
                            if q.is_file() and q.suffix in (".yaml", ".yml")):
                h.update(f"{name}/{p.relative_to(root)}".encode("utf-8"))
                h.update(p.read_bytes())
                n += 1
        assert n > 0, "data/library 正典根为 tracked 必在场"
        assert v["fixtures_hash"] == h.hexdigest()
        # data_hash：starrailres 核心实体表独立重算；未下载（gitignored）→ 期望 None
        data_base = _REPO_ROOT / "data" / "starrailres" / "index_new" / "cn"
        h2 = hashlib.sha256()
        n2 = 0
        for fname in ("characters.json", "light_cones.json", "relics.json"):
            p = data_base / fname
            if p.is_file():
                h2.update(fname.encode("utf-8"))
                h2.update(p.read_bytes())
                n2 += 1
        assert v["data_hash"] == (h2.hexdigest() if n2 else None)
        # policy_hash：调用方文本 sha256
        assert v["policy_hash"] == hashlib.sha256("策略原文".encode("utf-8")).hexdigest()

    def test_policy_hash_none_when_unset(self):
        assert mc.collect_version_fingerprint()["policy_hash"] is None

    def test_run_binds_version_and_trial(self):
        """实验记录与 summary 同带指纹五键；trial_id 同输入同值（指纹派生），显式传入优先."""
        res = mc.run(_eng, n=2, seed0=0, policy_source="rotation=[basic]")
        assert set(res.version) == {"git_commit", "rulebook_hash", "fixtures_hash",
                                    "data_hash", "policy_hash"}
        assert res.summary["version"] == res.version, "summary 同携版本指纹（三载体之一）"
        again = mc.run(_eng, n=2, seed0=0, policy_source="rotation=[basic]")
        assert res.trial_id == again.trial_id
        explicit = mc.run(_eng, n=2, seed0=0, trial_id="my-trial")
        assert explicit.trial_id == "my-trial"
