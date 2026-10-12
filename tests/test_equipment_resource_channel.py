"""装备侧资源/计数通道闸钉（2026-10-12，B36 批 3）：

通道下发票三件，逐条生效钉+反例：
- 装备模板（光锥+遗器）开放 `custom_resources` 键——decl 注册进装备者资源表
  （与角色模板同一 `_parse_resource_decls` 闸：词表外子键照旧编译期炸）；
- 装备 hooks 开放 `trigger_limit` 糖（desugar 装备侧同构展开——计数器注册 +
  充满 hooks + 门控 + 消耗）；模板顶层词表外键照旧编译期炸；
- `on_skill_point_change` 载荷下发 `turn`（回合序号=state.turn_count+1）与
  `consumer`（耗点行动者 actor_id；增益/非行动路径恒 ""）——模板条件可读。

收编件的行为钉归各族 e2e（test_lc_knight/abundance/erudition/elation_e2e、
test_relic_cavern_121_131_e2e）。
"""
from __future__ import annotations

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

_MEMBER = {
    "actor_id": "w", "name": "装备员", "inline": True, "path": "preservation",
    "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
    "actions": [{"action_id": "t_basic", "name": "普攻", "action_type": "basic",
                 "target_type": "single", "damage_type": "fire",
                 "scaling": [{"atk": 1.0}], "toughness_dmg": 10}],
}
_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}

_LC_BASE = {
    "light_cone_id": "t930", "name": "测试光锥", "rarity": 4, "path": "Knight",
    "base_stats": {"hp": 100.0, "atk": 50.0, "def": 30.0},
}
_RELIC_BASE = {"relic_set_id": "t931", "name": "测试套装"}


def _write_tpl(tmp_path, kind, ref, tpl):
    d = tmp_path / kind
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ref}.yaml").write_text(yaml.safe_dump(tpl, allow_unicode=True), encoding="utf-8")


def _compile_with_lc(tmp_path, tpl, *, relic_tpl=None):
    _write_tpl(tmp_path, "light_cones", "t930", tpl)
    member = {**_MEMBER, "light_cone_template": "t930", "light_cone": {"superimposition": 1}}
    if relic_tpl is not None:
        _write_tpl(tmp_path, "relics", "t931", relic_tpl)
        member["relics"] = {f"slot{i}": {"set_id": "t931"} for i in range(4)}
    build = {"build": {"team": [member],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])


def _compile_with_relic(tmp_path, tpl, *, pieces=4):
    _write_tpl(tmp_path, "relics", "t931", tpl)
    member = {**_MEMBER, "relics": {f"slot{i}": {"set_id": "t931"} for i in range(pieces)}}
    build = {"build": {"team": [member],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])


# ---------------------------------------------------------------------------
# 通道一：装备模板 custom_resources（光锥 + 遗器）
# ---------------------------------------------------------------------------

class TestEquipmentCustomResources:
    def test_lc_custom_resources_registered_and_runtime_init(self, tmp_path):
        """光锥 custom_resources → decl 注册进装备者资源表 + 引擎 setup current 初始化."""
        compiled = _compile_with_lc(tmp_path, {
            **_LC_BASE,
            "custom_resources": {"lc_t930_pool": {"max": 5, "current": 2,
                                                  "owner": "light_cone"}},
            "hooks": [{"event": "on_battle_start",
                       "effects": [{"effect_type": "gain_resource",
                                    "resource_id": "lc_t930_pool", "amount": 1}]}]})
        decls = compiled.resource_decls_by_actor["w"]
        assert decls["lc_t930_pool"]["max"] == 5 and decls["lc_t930_pool"]["current"] == 2.0
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        st = eng.state.actors["w"]
        assert st.resources["lc_t930_pool"] == 3.0, "初始 2 + 进战钩 +1（运行期统一入口）"

    def test_lc_unknown_top_key_still_rejected(self, tmp_path):
        """词表外照旧炸（通道开放不松键闸）."""
        with pytest.raises(ValueError, match="未知键 'custom_resourcees'"):
            _compile_with_lc(tmp_path, {**_LC_BASE, "custom_resourcees": {}})

    def test_lc_resource_block_subkey_gate(self, tmp_path):
        """装备侧与角色模板同一 _parse_resource_decls 闸——值块词表外子键炸."""
        with pytest.raises(ValueError, match="未知键 'maxx'"):
            _compile_with_lc(tmp_path, {
                **_LC_BASE,
                "custom_resources": {"lc_t930_pool": {"max": 5, "maxx": 6}}})

    def test_relic_custom_resources_registered_when_piece_active(self, tmp_path):
        """遗器顶层 custom_resources → 任一件套激活（≥2pc）即解析注册."""
        compiled = _compile_with_relic(tmp_path, {
            **_RELIC_BASE,
            "custom_resources": {"rec_t931_tally": {"max": "inf", "owner": "relic"}},
            "set_2pc": {"desc": "二件", "stat_effects": {"crit_dmg": 0.16}},
            "set_4pc": {"desc": "四件", "hooks": [
                {"event": "on_resource_gain",
                 "condition": "$event.resource_id == 'punchline'",
                 "effects": [{"effect_type": "gain_resource",
                              "resource_id": "rec_t931_tally",
                              "amount": "$event.amount"}]}]}}, pieces=4)
        assert "rec_t931_tally" in compiled.resource_decls_by_actor["w"]

    def test_relic_unknown_top_key_still_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="未知键 'custom_resourcees'"):
            _compile_with_relic(tmp_path, {**_RELIC_BASE, "custom_resourcees": {}})


# ---------------------------------------------------------------------------
# 通道二：装备 hooks 的 trigger_limit 糖（desugar 装备侧同构展开）
# ---------------------------------------------------------------------------

class TestEquipmentTriggerLimit:
    _HOOK = {
        "event": "after_being_hit",
        "condition": "$event.amount > 0",
        "trigger_limit": {"per_turn": 1},
        "effects": [{"effect_type": "gain_skill_point", "amount": 1}],
    }

    def test_lc_hook_trigger_limit_expands(self, tmp_path):
        """光锥 hook 挂 trigger_limit → 计数器四联件展开（资源注册+充满钩+门控+消耗）."""
        compiled = _compile_with_lc(tmp_path, {**_LC_BASE, "hooks": [self._HOOK]})
        decls = compiled.resource_decls_by_actor["w"]
        counters = [r for r in decls if r.startswith("_tl_")]
        assert len(counters) == 1, "计数资源注册进装备者资源表"
        rid = counters[0]
        assert decls[rid]["max"] == 1.0
        owner = next(h for h in compiled.hooks if h.event == "after_being_hit")
        assert owner.condition_expr is not None
        assert owner.effects[-1]["effect_type"] == "gain_resource"
        assert owner.effects[-1]["resource_id"] == rid
        charges = [h for h in compiled.hooks if h.event in ("on_battle_start", "on_turn_start")]
        assert len(charges) == 2, "充满 hooks（开局 + per_turn 重置点）"

    def test_lc_hook_trigger_limit_runtime(self, tmp_path):
        """运行期限次：每回合 1 次，回合开始重置."""
        compiled = _compile_with_lc(tmp_path, {**_LC_BASE, "hooks": [self._HOOK]})
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        sp0 = eng.state.skill_points
        payload = {"amount": 100.0, "absorbed": 0.0, "damage_type": "fire",
                   "source": "e1", "target": "w", "is_critical": False,
                   "seg_index": 0, "actor_type": "monster", "action_type": "basic",
                   "hit_targets": ["w"]}
        for _ in range(3):
            eng.bus.emit("after_being_hit", payload, eng.state)
        assert eng.state.skill_points == sp0 + 1, "每回合限 1 次"
        eng.bus.emit("on_turn_start", {"actor": "w"}, eng.state)
        eng.bus.emit("after_being_hit", payload, eng.state)
        assert eng.state.skill_points == sp0 + 2, "回合开始重置后再触发"

    def test_relic_piece_hook_trigger_limit_expands(self, tmp_path):
        """遗器套装件 hook 挂 trigger_limit → 同构展开."""
        compiled = _compile_with_relic(tmp_path, {
            **_RELIC_BASE,
            "set_2pc": {"desc": "二件", "hooks": [self._HOOK]}}, pieces=2)
        decls = compiled.resource_decls_by_actor["w"]
        assert any(r.startswith("_tl_") for r in decls), "计数资源注册进装备者资源表"
        owner = next(h for h in compiled.hooks if h.event == "after_being_hit")
        assert owner.effects[-1]["effect_type"] == "gain_resource"


# ---------------------------------------------------------------------------
# 通道三：on_skill_point_change 载荷 turn/consumer（模板条件可读）
# ---------------------------------------------------------------------------

class TestSkillPointChangePayload:
    def _engine(self):
        build = {"build": {"team": [_MEMBER],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, _STAGE, template_roots=[]),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        return eng

    def test_payload_turn_and_consumer_readable(self):
        """载荷钉：行动耗点 → turn=当前回合序（turn_count+1）、consumer=行动者；
        钩产点 → consumer 恒 ""."""
        eng = self._engine()
        recs = []
        eng.bus.subscribe("on_skill_point_change", lambda et, p, ctx: recs.append(dict(p)))
        eng._adjust_skill_points(-2, reason="action:t_skill", consumer="w")
        eng._adjust_skill_points(1, reason="hook")
        consume, gain = recs
        assert consume["consumer"] == "w" and consume["before"] == 3 and consume["after"] == 1
        assert consume["turn"] == eng.state.turn_count + 1, "回合戳=已完成行动数+1"
        assert gain["consumer"] == "", "增益路径 consumer 恒空"
        assert gain["turn"] == consume["turn"]

    def test_turn_stamp_advances_with_turns(self):
        """回合戳随 _run_turn 推进（turn_count 递增 → 下一回合戳 +1）."""
        eng = self._engine()
        recs = []
        eng.bus.subscribe("on_skill_point_change", lambda et, p, ctx: recs.append(dict(p)))
        eng._adjust_skill_points(-1, reason="action:t_skill", consumer="w")
        eng.state.turn_count += 1   # 回合推进（_run_turn 唯一通道的等价态）
        eng._adjust_skill_points(-1, reason="action:t_skill", consumer="w")
        assert recs[1]["turn"] == recs[0]["turn"] + 1
