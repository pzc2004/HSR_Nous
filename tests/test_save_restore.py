"""真·全状态存档与恢复（`CombatEngine.save_state` / `load_state`，主体 sim/save_load.py）.

两层钉：

① 世界线一致（验收核心）——原局跑 N 步 → save_state →（可经 json.dumps/loads 往返）→
load_state → 续跑 M 步；对照组同种子一口气跑 N+M 步。断言四件：终态 snapshot() 投影
逐字段全等（round-4 比对口径）+ total_damage 一致 + 战斗日志流逐行一致 +
**续跑后再存档与对照组再存档逐比特全等**（全精度定点——比 round-4 投影更强的口径，
调度器树键/RNG 流位置/引擎运行期字段全在比对面内）。编队三路线：佩拉队（常规
RNG 面：暴击判定/随机目标/效果命中roll）+ 欢愉队（阿哈时刻重 RNG 通道——系统单位
在档）+ 累积/召唤队（999905 累积测试员——hooks 累积队列与召唤物在档，存档点挑
队列非空时刻）；expected 模式（无 RNG）同钉一组；多波次编队转波后存档同钉。

② 完备性闸（防漂移核心）——save_load.FIELD_CODECS 键集 vs `dataclasses.fields`
反射双向比对（新增字段未登记即炸——漏一个字段 = 世界线静默分叉）；引擎/调度器/
管线/hooks 运行期字段的「存档 ∪ 结构豁免」二分清单同钉（豁免件逐条注理由——
编译产物由 from_compiled 重带，不进存档）。
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.save_load import FIELD_CODECS, SAVE_VERSION
from hsr_nous.sim.state import ActorState, BattleState, Modifier, ShieldInstance, StateConfig
from hsr_nous.sim_schema.actor import Actor, StatBlock
from tests.template_materialize import TEST_TEMPLATE_ROOTS

N_STEPS = 30   # 存档点（原局先跑 N 步）
M_STEPS = 20   # 续跑段（读档后续 M 步；对照组一口气 N+M 步）
AV_BUDGET = 20000  # 步进式测试的终止预算（N+M 步内不触终止，约 100AV/步的 4 倍余量）


# ---------------------------------------------------------------------------
# 编队与关卡（惯例同 tests/test_caveats_channel.py / test_sparxie_template_e2e.py：
# 真模板经 character_template 引用 + inline 辅手，TEST_TEMPLATE_ROOTS 正典根注入）
# ---------------------------------------------------------------------------

def _pela_build(**over):
    """佩拉队（1106 真模板 + inline 辅手——常规 RNG 面：暴击/随机目标/效果命中）."""
    build = {
        "team": [
            {"character_template": "1106", "level": 80},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "ice",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        ],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]},
    }
    build.update(over)
    return {"build": build}


def _pela_stage(**over):
    stage = {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 800,
                     "max_toughness": 9999, "weakness": ["ice"]}],
        "termination": {"mode": "fixed_av", "max_action_value": AV_BUDGET},
    }
    stage.update(over)
    return {"stage": stage}


def _elation_build():
    """欢愉队（火花 1501 真模板 + inline 欢愉成员激活阿哈时刻系统单位 + 辅手——
    阿哈重 RNG 通道：阿哈速度规则覆写 spd 的系统单位在档，演员面板运行时 replace
    产物经全字段 actor 存档恢复）."""
    return {"build": {
        "team": [
            {"character_template": "1501", "level": 80},
            {"actor_id": "ela0", "name": "欢愉零", "inline": True, "path": "elation",
             "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ela0_basic", "name": "普攻",
                          "action_type": "basic", "target_type": "single",
                          "damage_type": "fire", "scaling": [{"atk": 1.0}],
                          "toughness_dmg": 10}]},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "fire",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
                          "skill_point_gain": 1}]},
        ],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _elation_stage():
    return {"stage": {
        "stage_id": "s",
        "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100, "weakness": ["fire"]},
            {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 100, "weakness": ["fire"]}],
        "termination": {"mode": "fixed_av", "max_action_value": AV_BUDGET}}}


def _acc_build():
    """累积/召唤队（999905 累积测试员真模板——hooks 累积队列 §23.9 + av:false 冻结
    召唤物在档；敌方假人攻击制造 on_hp_decrease 喂队列）."""
    return {"build": {
        "team": [
            {"character_template": "999905", "level": 80},
            {"actor_id": "ally", "name": "辅手", "inline": True,
             "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
             "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                          "target_type": "single", "damage_type": "physical",
                          "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]},
        ],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _acc_stage():
    return {"stage": {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "打手假人", "hp": 1e9, "spd": 130,
                     "atk": 800, "max_toughness": 9999, "weakness": ["physical"]}],
        "termination": {"mode": "fixed_av", "max_action_value": AV_BUDGET}}}


def _wave_stage():
    """多波次关卡（wave1 假人低 HP 早死触发转波，存档点落在 wave2 已登场之后）."""
    return {"stage": {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 3000, "spd": 100, "atk": 500,
                     "max_toughness": 60, "weakness": ["ice"]}],
        "waves": [{"wave_index": 1, "enemies": [
            {"actor_id": "e2", "name": "假人二", "hp": 1e9, "spd": 120, "atk": 800,
             "max_toughness": 120, "weakness": ["ice"]}]}],
        "termination": {"mode": "fixed_av", "max_action_value": AV_BUDGET}}}


# ---------------------------------------------------------------------------
# 世界线协议
# ---------------------------------------------------------------------------

def _steps(eng: CombatEngine, n: int) -> None:
    """推进 n 个调度回合（步内终局=编队/预算配置错误，测试直接炸）."""
    for i in range(n):
        assert eng.step() is not None, f"第 {i + 1} 步前战斗已终止（预算 {AV_BUDGET} 配置复查）"


def _assert_worldline(compiled, *, mode: str, seed: int, via_json: bool = False) -> None:
    """存档续跑 vs 一口气对照：投影全等 + 日志流一致 + 总伤一致 + 再存档逐比特全等."""
    eng = CombatEngine.from_compiled(compiled, mode=mode, seed=seed)
    _steps(eng, N_STEPS)
    save = eng.save_state()
    if via_json:
        save = json.loads(json.dumps(save, ensure_ascii=False))
    restored = CombatEngine.load_state(compiled, save)
    _steps(restored, M_STEPS)

    ctrl = CombatEngine.from_compiled(compiled, mode=mode, seed=seed)
    _steps(ctrl, N_STEPS + M_STEPS)

    assert restored.state.snapshot() == ctrl.state.snapshot(), "终态 snapshot() 投影分叉"
    assert restored.state.log == ctrl.state.log, "战斗日志流分叉"
    assert restored.state.total_damage == ctrl.state.total_damage, "总伤分叉"
    assert restored.save_state() == ctrl.save_state(), (
        "全精度再存档分叉（调度器树键/RNG 流位置/引擎运行期字段其一漂移）")


class TestWorldLineRoll:
    def test_pela_team_roll(self):
        """佩拉队 roll 模式（常规 RNG 面：暴击判定/随机目标/效果命中 roll）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        _assert_worldline(compiled, mode=MODE_ROLL, seed=42)

    def test_elation_team_roll(self):
        """欢愉队 roll 模式（阿哈时刻重 RNG 通道 + 系统单位在档）."""
        compiled = compile_encounter(_elation_build(), _elation_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, N_STEPS)
        assert "aha_instant" in eng.state.actors, "阿哈时刻系统单位应在场（存档覆盖对象）"
        save = eng.save_state()
        restored = CombatEngine.load_state(compiled, save)
        _steps(restored, M_STEPS)
        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(ctrl, N_STEPS + M_STEPS)
        assert restored.state.snapshot() == ctrl.state.snapshot(), "终态 snapshot() 投影分叉"
        assert restored.state.log == ctrl.state.log, "战斗日志流分叉"
        assert restored.state.total_damage == ctrl.state.total_damage, "总伤分叉"
        assert restored.save_state() == ctrl.save_state(), "全精度再存档分叉"

    def test_acc_queue_and_summon_roll(self):
        """累积/召唤队 roll 模式：存档点挑累积队列**非空**时刻（§23.9 队列在档恢复）."""
        compiled = compile_encounter(_acc_build(), _acc_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=11)
        _steps(eng, 6)   # 实证：第 6 步末队列挂 1 条未消费 payload（999905 记账灵）
        save = eng.save_state()
        assert save["acc_queues"] and save["acc_queues"][0]["queue"], (
            "存档点累积队列应非空（本钉的覆盖前提——队列空=机制没压到）")
        assert "999905_memo" in eng.state.actors, "av:false 冻结召唤物应在场（在档对象）"
        restored = CombatEngine.load_state(compiled, save)
        _steps(restored, M_STEPS)
        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=11)
        _steps(ctrl, 6 + M_STEPS)
        assert restored.state.snapshot() == ctrl.state.snapshot(), "终态 snapshot() 投影分叉"
        assert restored.state.log == ctrl.state.log, "战斗日志流分叉"
        assert restored.save_state() == ctrl.save_state(), "全精度再存档分叉"


class TestWorldLineExpected:
    def test_pela_team_expected(self):
        """expected 模式（无 RNG——期望值结算通道）同钉."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        _assert_worldline(compiled, mode=MODE_EXPECTED, seed=7)


class TestJsonRoundTrip:
    """JSON 落盘往返：save dict 经 json.dumps/loads 后再 load，世界线仍一致."""

    def test_pela_roll_via_json(self):
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        _assert_worldline(compiled, mode=MODE_ROLL, seed=42, via_json=True)

    def test_elation_roll_via_json(self):
        compiled = compile_encounter(_elation_build(), _elation_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        _assert_worldline(compiled, mode=MODE_ROLL, seed=42, via_json=True)


class TestWaveSave:
    def test_save_after_wave_transition(self):
        """转波后存档：wave2 敌人已在场（在档单位），恢复后不得重布场/重回波次计数."""
        compiled = compile_encounter(_pela_build(), _wave_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=3)
        _steps(eng, N_STEPS)
        assert eng.current_wave == 1, "存档点应已转波（wave2 在打的局——本钉覆盖前提）"
        assert "e2" in eng.state.actors and eng.state.actors["e2"].alive
        save = eng.save_state()
        restored = CombatEngine.load_state(compiled, json.loads(json.dumps(save)))
        assert restored.current_wave == 1, "恢复后波次计数不得回退"
        assert set(restored.state.actors) == set(eng.state.actors), (
            "wave2 敌人按存档在场，不得经 _advance_wave 重布场")
        _steps(restored, M_STEPS)
        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=3)
        _steps(ctrl, N_STEPS + M_STEPS)
        assert restored.state.snapshot() == ctrl.state.snapshot(), "终态 snapshot() 投影分叉"
        assert restored.state.log == ctrl.state.log, "战斗日志流分叉"
        assert restored.save_state() == ctrl.save_state(), "全精度再存档分叉"


class TestRunToEnd:
    def test_restored_run_completes_same_terminal_state(self):
        """读档后 run() 跑到终局：终态与对照组全等（battle_end 一次性旗标通道同验）."""
        stage = _pela_stage()
        # 预算须让 fixed_av 终止先于 MAX_TURNS_SAFETY=200 截断到来（佩拉队实测
        # 约 34AV/回合——含终结技插入零 AV 回合；4000AV ≈ 120 回合内终局）
        stage["stage"]["termination"] = {"mode": "fixed_av", "max_action_value": 4000}
        compiled = compile_encounter(_pela_build(), stage, template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, N_STEPS)
        restored = CombatEngine.load_state(compiled, eng.save_state())
        restored.run()
        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        ctrl.run()
        assert restored.state.snapshot() == ctrl.state.snapshot()
        assert restored.save_state() == ctrl.save_state()


# ---------------------------------------------------------------------------
# 完备性闸（防漂移核心）：字段策略表 ↔ dataclasses.fields 反射双向比对 +
# 引擎/调度器/管线/hooks 运行期字段「存档 ∪ 结构豁免」二分清单
# ---------------------------------------------------------------------------

class TestCompletenessGate:
    @pytest.mark.parametrize("cls", [Modifier, ActorState, BattleState, Actor, StatBlock,
                                     ShieldInstance, StateConfig])
    def test_field_codecs_cover_dataclass(self, cls):
        """存档字段策略表（save_load.FIELD_CODECS）与 dataclass 字段集机械一致.

        新增字段未进表（或删字段忘同步）即炸——存档漏一个字段 = 世界线静默分叉。
        本表无豁免件：连 Actor 本体都全字段嵌套存档（运行期 replace 产物无需求解重放）。
        """
        fields = {f.name for f in dataclasses.fields(cls)}
        codecs = FIELD_CODECS[cls]
        missing = fields - set(codecs)
        extra = set(codecs) - fields
        assert not missing, (
            f"{cls.__name__} 新字段未登记存档策略：{sorted(missing)}"
            "——在 sim/save_load.py FIELD_CODECS 补编解码方式")
        assert not extra, (
            f"{cls.__name__} 存档策略表残留已删字段：{sorted(extra)}——同步 FIELD_CODECS")

    def test_known_codec_vocabulary(self):
        """编解码词表闭合（表内只许出现已实现的编解码名——防笔坏死键）."""
        known = {"plain", "expr", "expr_dict", "tuple2_dict", "actor", "stat_block",
                 "frozenset", "modifiers", "shields", "state_config", "actor_states"}
        for cls, table in FIELD_CODECS.items():
            bad = set(table.values()) - known
            assert not bad, f"{cls.__name__} 存档策略表含未知编解码 {sorted(bad)}"

    # 引擎实例字段的结构豁免单（编译产物/注入件——from_compiled 重带，不进存档；
    # 逐条注理由。新字段未进「存档 ∪ 本单」即炸）
    _ENGINE_STRUCTURAL = {
        "encounter": "编译产物（from_compiled 重带）",
        "actions_by_actor": "编译产物",
        "summon_defs": "编译产物",
        "_binding_params": "编译产物",
        "decision": "编译策略运行时（无实例状态——select_* 全走 ctx/turn_count 现算）",
        "_expr": "表达式编译器（parse 缓存=派生物；恢复重 parse 经它兜底）",
        "pipeline": "结算管线（mode 走 save['mode']、rng 走 save['rng']，余为注入回调/缓存）",
        "bus": "事件总线（订阅恢复时重挂；_depth/_warned 是结算瞬时量，档间恒静息零值）",
        "_hooks": "HookRuntime（累积队列走 save['acc_queues']，余为引擎门面引用）",
        "_modifiers": "ModifierBook（无实例状态——仅引擎门面引用）",
        "initial_sp": "setup 注入件（_init_state 不重跑，恢复后无消费点）",
        "initial_energy_ratio": "setup 注入件（同上）",
        "wave_enemies": "编译产物（未来波次敌人——登场时刻才经 _advance_wave 布场）",
        "_enemy_policies": "编译产物（敌人序列/冷却规则；运行态在 _enemy_policy_state 存档）",
        "state_configs_by_actor": "编译产物（形态注册表；state_config 按名回挂同件）",
        "_initial_modifiers": "编译产物（初始挂载属历史，已在存档的 modifiers 里）",
        "_compiled_hooks": "编译产物（恢复时按列表序编号重挂订阅与累积队列）",
        "caveats": "编译产物（纯元数据，不进结算）",
        "_resource_decls": "编译产物",
        "state_entry_actions": "编译产物",
        "_trigger_order": "编译产物",
    }

    def test_engine_attrs_partitioned(self):
        """引擎实例字段二分闸：vars(engine) ⊆ 存档字段 ∪ 结构豁免单（反方向同查）."""
        compiled = compile_encounter(_elation_build(), _elation_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 10)
        save = eng.save_state()
        saved = set(save["engine"]) | {"state", "scheduler"}
        unknown = set(vars(eng)) - saved - set(self._ENGINE_STRUCTURAL)
        assert not unknown, (
            f"引擎新运行期字段未二分（存档 or 豁免注理由）：{sorted(unknown)}"
            "——漏存档 = 世界线静默分叉；在 sim/save_load.py _ENGINE_RUNTIME_FIELDS "
            "或本测试 _ENGINE_STRUCTURAL 登记")
        stale = (saved - {"state", "scheduler"}) - set(vars(eng)) - self._ENGINE_LAZY_SAVED
        assert not stale, f"存档字段在引擎上已不存在：{sorted(stale)}——同步存档清单"

    #: 惰性存档字段（结算期才落实例——中场引擎 vars 不含属预期；恢复侧恒写，
    #: 与原引擎 getattr 缺省语义逐比特对齐）
    _ENGINE_LAZY_SAVED = {"_battle_end_emitted"}

    def test_scheduler_attrs_partitioned(self):
        """调度器字段二分闸：存档（动态六件+clock+eta 树键）∪ 派生重建（树/句柄映射）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 5)
        saved = {"_tie_of", "_frozen", "_extra_queue", "_countdown",
                 "_wave_reset_exempt", "_remaining", "_spd_now", "clock"}
        derived = {"_tree", "_actors", "_handles"}  # 恢复时从存档逐句柄 insert 派生
        unknown = set(vars(eng.scheduler)) - saved - derived
        assert not unknown, (
            f"调度器新字段未二分：{sorted(unknown)}——在 sim/save_load.py "
            "_save_scheduler/_restore_scheduler 或本测试豁免集登记")

    def test_pipeline_attrs_partitioned(self):
        """管线字段二分闸：mode/rng 存档，余为注入回调与派生缓存（__init__ 重挂）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        saved = {"mode", "rng"}
        structural = {"_expr", "_aura_provider", "_cond_runtime", "_cond_warn",
                      "_hit_functions", "_hit_self_ns", "_actor_lookup",
                      "_rb", "_comp_cache"}
        unknown = set(vars(eng.pipeline)) - saved - structural
        assert not unknown, f"管线新字段未二分：{sorted(unknown)}"

    def test_hooks_attrs_partitioned(self):
        """HookRuntime 字段二分闸：累积队列存档（按编译钩编号），引擎门面豁免."""
        compiled = compile_encounter(_acc_build(), _acc_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=11)
        unknown = set(vars(eng._hooks)) - {"_engine", "_acc_queues"}
        assert not unknown, f"HookRuntime 新字段未二分：{sorted(unknown)}"

    def test_save_is_json_serializable(self):
        """存档纯数据闸：json.dumps 必须直接可序列化（真可落盘——含表达式槽/RNG 嵌套）."""
        compiled = compile_encounter(_elation_build(), _elation_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 10)
        blob = json.dumps(eng.save_state(), ensure_ascii=False)
        assert blob and json.loads(blob)["save_version"] == SAVE_VERSION

    def test_save_restore_fixed_point(self):
        """存档→恢复→再存档定点：恢复引擎立刻再存档与原存档逐比特全等.

        编解码不对称（tuple↔list/frozenset 序/表达式重 parse 源串漂移）在本钉下显形。
        """
        compiled = compile_encounter(_acc_build(), _acc_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=11)
        _steps(eng, 6)   # 累积队列非空时刻（覆盖 acc_queues 通道的对称性）
        save1 = eng.save_state()
        restored = CombatEngine.load_state(compiled, json.loads(json.dumps(save1)))
        assert restored.save_state() == json.loads(json.dumps(save1)), (
            "读档后再存档与原存档分叉——编码/解码不对称（定点未达）")


# ---------------------------------------------------------------------------
# 契约闸（误用防线）
# ---------------------------------------------------------------------------

class TestGuards:
    def test_save_before_setup_rejected(self):
        """战斗未开始无可存档（开局前的等价物是编译产物本身）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        with pytest.raises(ValueError, match="战斗未开始无可存档"):
            eng.save_state()

    def test_mode_mismatch_rejected(self):
        """roll/expected 混接即炸（结算语义不同，世界线必分叉）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 3)
        save = eng.save_state()
        with pytest.raises(ValueError, match="存档模式"):
            CombatEngine.load_state(compiled, save, mode=MODE_EXPECTED)

    def test_save_version_rejected(self):
        """格式版本闸（演进需配套迁移通道）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 3)
        save = eng.save_state()
        save["save_version"] = SAVE_VERSION + 1
        with pytest.raises(ValueError, match="存档格式版本不符"):
            CombatEngine.load_state(compiled, save)

    def test_seed_warns_and_is_ignored(self):
        """load_state 传 seed：忽略并告警（RNG 流位置由存档恢复）."""
        compiled = compile_encounter(_pela_build(), _pela_stage(),
                                     template_roots=TEST_TEMPLATE_ROOTS)
        eng = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(eng, 3)
        save = eng.save_state()
        with pytest.warns(RuntimeWarning, match="seed 被忽略"):
            restored = CombatEngine.load_state(compiled, save, seed=999)
        _steps(restored, 2)
        ctrl = CombatEngine.from_compiled(compiled, mode=MODE_ROLL, seed=42)
        _steps(ctrl, 5)
        assert restored.state.snapshot() == ctrl.state.snapshot(), (
            "seed 被忽略后世界线仍须与原线一致（RNG 流位置走存档）")
