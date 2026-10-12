"""命途系统模块 + 模板 import 机制端到端（2026-10-12——阿哈时刻自引擎硬编码迁入
`data/library/system/paths/elation.yaml` 首租）：

- auto-import：编译 team 时按成员有效 path 注入 `system/paths/<path>.yaml`（存在即
  注入——非欢愉队无阿哈，与引擎旧行为一致；多欢愉角色去重单实例）
- 显式 imports 槽（member/角色模板级，备用）与词表闸全家（缺文件/形态/未知标记/
  名实不符/无单位挂钩/资源重名/单位撞 id/const 无名）
- 系统单位四语义标记行为钉（untargetable 目标池排除 / no_wipe 不计全灭 /
  no_aura 光环接收侧豁免 / wave_reset_exempt 波次豁免注册+续跑）
- 合并语义：模块钩先于角色钩订阅（体系先于个体——发放/结算在角色钩之前的现序保持）

模子同 test_aha_instant（tmp_path 微型模板 + canonical 模块根兜底）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier

#: canonical 命途模块根（`system/paths/elation.yaml` 真身——与 TEST_TEMPLATE_ROOTS 同构，
#: 人工 tmp 根优先、模块根兜底）
MODULE_ROOT = "data/library"

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000,
     "max_toughness": 100, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


def _member(aid, *, path=None, spd=200, imports=None, custom_resources=None):
    m = {"actor_id": aid, "name": f"测试员{aid}", "inline": True,
         "base_stats": {"atk": 1000, "spd": spd, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": f"{aid}_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "fire",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}
    if path:
        m["path"] = path
    if imports is not None:
        m["imports"] = imports
    if custom_resources is not None:
        m["custom_resources"] = custom_resources
    return m


def _make(members, *, roots_extra=()):
    roots = [*(roots_extra), MODULE_ROOT]
    c = compile_encounter({"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}},
        _STAGE, template_roots=roots)
    eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                     initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _compile(members, *, roots_extra=()):
    roots = [*(roots_extra), MODULE_ROOT]
    return compile_encounter({"build": {"team": members,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}},
        _STAGE, template_roots=roots)


class TestAutoImport:
    def test_elation_team_injects_aha(self):
        """欢愉队 auto-import：阿哈在条 + 进战发放（+1 笑点/+20 好活当赏）."""
        eng = _make([_member("h1", path="elation", spd=200)])
        aha = eng.state.actors.get("aha_instant")
        assert aha is not None, "欢愉队→模块注入→阿哈在条"
        assert aha.actor.actor_type == "aha"
        assert math.isclose(aha.actor.stats.spd, 80.0 + 0.2 * 200), "具名速度规则 aha 求值"
        assert math.isclose(eng.state.punchline, 1.0), "进战每欢愉角色 +1 笑点（模块钩）"
        st = eng.state.actors["h1"]
        assert st.banger_entries == [{"value": 20.0, "turns": 2.0}], "进战 20 好活当赏（模块钩）"

    def test_non_elation_team_no_injection(self):
        """非欢愉队：auto-import 静默跳过——无阿哈、笑点池静置 0（现行为一致）."""
        eng = _make([_member("h1", path="destruction")])
        assert "aha_instant" not in eng.state.actors
        assert eng.state.punchline == 0.0
        assert not any(h.owner_id == "aha_instant" for h in eng._compiled_hooks), (
            "非欢愉队不注入模块钩")

    def test_multi_elation_dedup_single_instance(self):
        """多欢愉角色去重单实例（encounter 级 Python 模块缓存语义）."""
        c = _compile([_member("h1", path="elation", spd=200),
                      _member("h2", path="elation", spd=150),
                      _member("h3", path="elation", spd=100)])
        system = [a for a in c.system_actors if a.actor_id == "aha_instant"]
        assert len(system) == 1, "三欢愉角色→单阿哈实例（auto-import 去重）"
        eng = CombatEngine.from_compiled(c, mode=MODE_EXPECTED,
                                         initial_energy_ratio=0.0, initial_sp=3)
        eng.setup()
        assert sum(1 for aid in eng.state.actors if aid == "aha_instant") == 1
        assert math.isclose(eng.state.punchline, 3.0), "进战 3 欢愉各 +1"
        assert math.isclose(eng.state.actors["aha_instant"].actor.stats.spd,
                            80.0 + 0.2 * 200 + 0.1 * 150 + 0.05 * 100), "速度公式前三权重"

    def test_module_hooks_before_character_hooks(self, tmp_path):
        """合并语义：模块钩先于角色钩订阅（体系先于个体——发放/结算现序保持）."""
        d = tmp_path / "characters"
        d.mkdir()
        (d / "900701_欢愉测试员.yaml").write_text("""\
actor_id: "900701"
name: "欢愉测试员"
level: 80
path: "elation"
base_stats: {atk: 1000, spd: 200, hp: 3000, max_energy: 100}
actions:
  - action_id: "t_basic"
    name: "普攻"
    action_type: "basic"
    target_type: "single"
    damage_type: "fire"
    scaling: [{atk: 1.0}]
    toughness_dmg: 10
hooks:
  - event: "on_action"
    condition: "$event.actor == '900701'"
    effects:
      - effect_type: "gain_resource"
        resource_id: "punchline"
        amount: 1
""", encoding="utf-8")
        c = _compile([{"character_template": "900701", "level": 80}],
                     roots_extra=[str(tmp_path)])
        owners = [h.owner_id for h in c.hooks]
        assert owners.index("aha_instant") < owners.index("900701"), (
            "模块钩订阅序先于角色钩（体系先于个体）")


class TestExplicitImports:
    def test_member_imports_injects_module(self):
        """显式 imports 备用槽：非欢愉成员显式引用 → 模块注入（阿哈在条、无欢愉角色不发放）."""
        eng = _make([_member("h1", path="destruction", imports=["paths/elation"])])
        aha = eng.state.actors.get("aha_instant")
        assert aha is not None, "显式 imports 强制注入"
        assert math.isclose(aha.actor.stats.spd, 80.0), "无欢愉角色→速度=基础值"
        assert eng.state.punchline == 0.0, "无欢愉角色→发放目标池空"
        assert not eng.state.actors["h1"].banger_entries

    def test_imports_missing_module_explodes(self):
        """显式引用悬空：FileNotFoundError（auto-import 才静默跳过）."""
        with pytest.raises(FileNotFoundError, match="paths/void"):
            _compile([_member("h1", imports=["paths/void"])])

    def test_imports_type_and_form_gates(self):
        """imports 词表闸：非列表 / 形态非法（缺 scope 段）编译期炸."""
        with pytest.raises(ValueError, match="imports 须为模块名字符串列表"):
            _compile([_member("h1", imports="paths/elation")])
        with pytest.raises(ValueError, match="形态非法"):
            _compile([_member("h1", imports=["elation"])])


class TestSystemUnitMarkers:
    def test_untargetable(self):
        """untargetable：目标池/我方命名空间排除（_allies_alive 单漏斗）."""
        eng = _make([_member("h1", path="elation")])
        assert all(s.actor.actor_type != "aha" for s in eng._allies_alive())
        from hsr_nous.sim.target_algebra import resolve_pool
        st = eng.state.actors["h1"]
        pool = resolve_pool("allies", engine=eng, st=st, payload={})
        assert all(s.actor.actor_type != "aha" for s in pool), "hook 目标代数池同排除"
        pool_all = resolve_pool("all", engine=eng, st=st, payload={})
        assert all(s.actor.actor_type != "aha" for s in pool_all), "all 池同排除"

    def test_no_wipe(self):
        """no_wipe：阿哈存活不算我方存活——全角色阵亡即判全灭."""
        eng = _make([_member("h1", path="elation")])
        assert "aha_instant" in eng.state.actors
        eng.state.actors["h1"].alive = False
        assert eng._should_terminate(), "唯一角色阵亡→全灭（阿哈不计入）"
        assert eng._termination_reason() == "all_allies_dead"

    def test_no_aura(self):
        """no_aura：team 光环辐射不到阿哈面板（接收侧豁免；我方单位照吃）."""
        eng = _make([_member("h1", path="elation")])
        st = eng.state.actors["h1"]
        eng._modifiers._apply_modifier(st, Modifier(
            modifier_id="T_TEAM_AURA", name="测试团队光环", modifier_type="buff",
            duration=0, dispellable=False, effect_scope="team",
            stat_effects={"atk": 100.0}))
        aha = eng.state.actors["aha_instant"]
        assert math.isclose(eng.pipeline.effective_stats(st)["atk"], 1100.0), "我方照吃光环"
        assert math.isclose(eng.pipeline.effective_stats(aha)["atk"], 0.0), (
            "阿哈不吃光环辐射（no_aura 接收侧豁免）")

    def test_wave_reset_exempt(self):
        """wave_reset_exempt：注册 scheduler 豁免集 + 转波次按原行动值续跑."""
        eng = _make([_member("h1", path="elation")])
        handle = eng.scheduler.handle_of("aha_instant")
        assert handle in eng.scheduler._wave_reset_exempt, "标记驱动豁免注册"
        eng.scheduler._remaining[handle] = 4321.0
        h_hero = eng.scheduler.handle_of("h1")
        eng.scheduler.reset_action_gauge(except_countdown=True)
        assert eng.scheduler._remaining[handle] == 4321.0, "阿哈跨波续跑（转面不重跑）"
        assert eng.scheduler._remaining[h_hero] == 10000.0, "其余单位照常重置"

    def test_turn_handler_dispatch(self):
        """turn_handler: aha_turn——调度弹出的阿哈回合走引擎结算原语（共读池→代放→授条目→清池）."""
        eng = _make([_member("h1", path="elation", spd=200)])
        rec1 = eng.step()   # h1 普攻（spd 200 先到）
        assert rec1["actor_id"] == "h1"
        rec2 = eng.step()   # 阿哈时刻（速度 120，eta 83.3 < 敌方 100）
        assert rec2["actor_id"] == "aha_instant" and not rec2["skipped"]
        assert eng.state.punchline == 0.0, "结算清池（进战 1 被本次消耗）"
        st = eng.state.actors["h1"]
        assert eng._resource_value(st, "certified_banger") == 21.0, (
            "进战 20 + 阿哈时刻授予=消耗池值 1（逐角色账合并）")


class TestModuleSchemaGates:
    """模块 schema 词表闸全家（tmp 合成模块——显式 imports 触发编译）."""

    def _write_module(self, tmp_path, name, body):
        d = tmp_path / "system" / "paths"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.yaml").write_text(body, encoding="utf-8")
        return str(tmp_path)

    def test_unknown_flag(self, tmp_path):
        root = self._write_module(tmp_path, "badflag", """\
module: "paths/badflag"
units:
  - actor_id: "sys_unit"
    name: "坏标记单位"
    actor_type: "system"
    flags: ["flying"]
""")
        with pytest.raises(ValueError, match="未知语义标记"):
            _compile([_member("h1", imports=["paths/badflag"])], roots_extra=[root])

    def test_top_level_unknown_key(self, tmp_path):
        root = self._write_module(tmp_path, "badkey", """\
module: "paths/badkey"
bogus: 1
""")
        with pytest.raises(ValueError, match="未知键"):
            _compile([_member("h1", imports=["paths/badkey"])], roots_extra=[root])

    def test_module_name_mismatch(self, tmp_path):
        root = self._write_module(tmp_path, "mismatch", """\
module: "paths/other"
""")
        with pytest.raises(ValueError, match="名实不符|与加载名不符"):
            _compile([_member("h1", imports=["paths/mismatch"])], roots_extra=[root])

    def test_hooks_without_units(self, tmp_path):
        root = self._write_module(tmp_path, "ownerless", """\
module: "paths/ownerless"
hooks:
  - event: "before_battle_start"
    effects:
      - effect_type: "gain_skill_point"
        amount: 1
""")
        with pytest.raises(ValueError, match="无系统单位"):
            _compile([_member("h1", imports=["paths/ownerless"])], roots_extra=[root])

    def test_resource_clash_with_character(self, tmp_path):
        root = self._write_module(tmp_path, "clash", """\
module: "paths/clash"
units:
  - actor_id: "sys_unit"
    name: "资源单位"
    actor_type: "system"
custom_resources:
  shared_pool: {max: 10}
""")
        with pytest.raises(ValueError, match="重名"):
            _compile([_member("h1", imports=["paths/clash"],
                              custom_resources={"shared_pool": {"max": 5}})],
                     roots_extra=[root])

    def test_const_unknown_name(self, tmp_path):
        root = self._write_module(tmp_path, "badconst", """\
module: "paths/badconst"
units:
  - actor_id: "sys_unit"
    name: "常量单位"
    actor_type: "system"
hooks:
  - event: "before_battle_start"
    effects:
      - effect_type: "gain_skill_point"
        amount: "const(does_not_exist)"
""")
        with pytest.raises(ValueError, match="无此数值体系常量"):
            _compile([_member("h1", imports=["paths/badconst"])], roots_extra=[root])

    def test_system_unit_id_clash(self, tmp_path):
        root = self._write_module(tmp_path, "idclash", """\
module: "paths/idclash"
units:
  - actor_id: "h1"
    name: "撞名单位"
    actor_type: "system"
""")
        with pytest.raises(ValueError, match="撞 id|重复 actor_id"):
            _compile([_member("h1", imports=["paths/idclash"])], roots_extra=[root])

    def test_unit_base_stats_unknown_key(self, tmp_path):
        root = self._write_module(tmp_path, "badstats", """\
module: "paths/badstats"
units:
  - actor_id: "sys_unit"
    name: "坏面板单位"
    actor_type: "system"
    base_stats: {weakness: ["fire"]}
""")
        with pytest.raises(ValueError, match="未知键"):
            _compile([_member("h1", imports=["paths/badstats"])], roots_extra=[root])

    def test_forbidden_actor_type(self, tmp_path):
        root = self._write_module(tmp_path, "badtype", """\
module: "paths/badtype"
units:
  - actor_id: "sys_unit"
    name: "伪装单位"
    actor_type: "monster"
""")
        with pytest.raises(ValueError, match="actor_type 非法值"):
            _compile([_member("h1", imports=["paths/badtype"])], roots_extra=[root])
