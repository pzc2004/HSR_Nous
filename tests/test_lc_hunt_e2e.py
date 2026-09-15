"""巡猎（Rogue/The Hunt）光锥族 e2e：staging→fixtures 验收批.

20 件验收 fixture（tests/fixtures/templates/light_cones/）→ 编译 → 白值三围/机制行为
断言（手算对轴）；勘正条目见各 fixture 头注。覆盖：白值三围（角色 1000/3000/100
+ 光锥白值）、机制面板与行为、命途限制分例（hunt 触发 / 非 hunt 只出白值）、
叠影 S1 起（S5 差分抽查）。

口径常数：inline 装备员 atk 1000 / spd 100 / hp 3000 / max_energy 100 / crit 0.05/0.5；
假人 def 1000 → 防御区 0.5、全弱点 → 抗性 1.0、未击破 0.9、期望暴击区 1+cr×cd。
面板直读 eng.pipeline.effective_stats（条件光环面板读取即重估——enable_if/stat_exprs
现场生效）。期望模式 is_critical 恒 false（暴击折进期望区）——暴击触发链用手发
after_being_hit（is_critical: True）驱动；mechanic_chance(p<0.5) 期望模式恒不触发
（21031 解除链只断负例，正例归 roll 模式实测）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from tests.template_materialize import TEST_TEMPLATE_ROOTS


def _basic(aid="t_basic"):
    return {"action_id": aid, "name": "普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _skill(aid="t_skill"):
    return {"action_id": aid, "name": "战技", "action_type": "skill",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 20}


def _fua(aid="t_fua"):
    return {"action_id": aid, "name": "追加攻击", "action_type": "follow_up",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "toughness_dmg": 10}


def _build(lc_id, *, superimposition=1, path="hunt", actions=None, base=None):
    stats = {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100}
    if base:
        stats.update(base)
    member = {"actor_id": "w", "name": "装备员", "inline": True,
              "base_stats": stats,
              "light_cone_template": lc_id,
              "light_cone": {"superimposition": superimposition},
              "actions": actions if actions is not None else [_basic()]}
    if path:
        member["path"] = path
    return {"build": {"team": [member],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]}}}


def _stage(*extra_enemies):
    enemies = [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 100,
                "weakness": ["fire", "ice", "thunder", "wind",
                             "quantum", "imaginary", "physical"]}]
    enemies += list(extra_enemies)
    return {"stage": {"stage_id": "s", "enemies": enemies,
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


#: 1 血脆皮（击杀链）/ 10 韧脆皮（击破链）
_E2_FRAGILE = {"actor_id": "e2", "name": "脆皮", "hp": 1, "spd": 100, "atk": 1000,
               "def": 1000, "max_toughness": 100,
               "weakness": ["fire", "ice", "thunder", "wind",
                            "quantum", "imaginary", "physical"]}
_E2_TENDER = {"actor_id": "e2", "name": "薄韧", "hp": 1e9, "spd": 100, "atk": 1000,
              "def": 1000, "max_toughness": 10,
              "weakness": ["fire", "ice", "thunder", "wind",
                           "quantum", "imaginary", "physical"]}
_E3 = {"actor_id": "e3", "name": "假人3", "hp": 1e9, "spd": 100, "atk": 1000,
       "def": 1000, "max_toughness": 100,
       "weakness": ["fire", "ice", "thunder", "wind",
                    "quantum", "imaginary", "physical"]}


def _make(build, stage=None):
    eng = CombatEngine.from_compiled(
        compile_encounter(build, stage or _stage(), template_roots=TEST_TEMPLATE_ROOTS),
        mode=MODE_EXPECTED, initial_energy_ratio=0.0, initial_sp=3)
    eng.setup()
    return eng


def _cast(eng, owner, aid, target_id="e1"):
    """手动施放（8009 模子）：行动结算 + 补发 on_action（hook 触发域）."""
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


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _mods(eng, aid):
    return eng.state.actors[aid].modifiers


def _hit(eng, source="w", target="e1", crit=True, action_type="basic"):
    """手发受击事件（暴击触发链——期望模式 is_critical 恒 false 的旁路）."""
    eng.bus.emit("after_being_hit", {
        "amount": 100.0, "absorbed": 0.0, "damage_type": "fire", "source": source,
        "target": target, "is_critical": crit, "seg_index": 0,
        "actor_type": "character", "action_type": action_type,
        "hit_targets": [target]}, eng.state)


# ---------------------------------------------------------------------------
# 20000 锋镝（战斗开始暴击率 +#1，3 回合）
# ---------------------------------------------------------------------------
class TestLC20000:
    LC_ATK, LC_DEF, LC_HP = 317.52, 264.6, 846.72

    def test_base_stats(self):
        eng = _make(_build("20000"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3000 + self.LC_HP, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1000 + self.LC_ATK, rel_tol=1e-9)
        assert math.isclose(eff["def_"], self.LC_DEF, rel_tol=1e-9)

    def test_crit_buff_s1(self):
        """S1：暴击率 0.05+0.12=0.17，modifier duration 3."""
        eng = _make(_build("20000"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "w")["LC_20000_CRIT_RATE_BUFF"].duration, 3)

    def test_crit_buff_s5(self):
        eng = _make(_build("20000", superimposition=5))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.29, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("20000", path="destruction"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)
        assert "LC_20000_CRIT_RATE_BUFF" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 20007 离弦（击杀后攻击 +#1，3 回合）
# ---------------------------------------------------------------------------
class TestLC20007:
    def test_base_stats(self):
        eng = _make(_build("20007"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3740.88, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1370.44, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 264.6, rel_tol=1e-9)

    def test_kill_atk_s1(self):
        """S1：装备者击杀脆皮 → atk 白值1370.44×1.24=1666.0144（白值=角色+光锥）."""
        eng = _make(_build("20007"), _stage(_E2_FRAGILE))
        assert math.isclose(_eff(eng, "w")["atk"], 1370.44, rel_tol=1e-9), "未击杀无件"
        _cast(eng, "w", "t_basic", "e2")
        assert "LC_20007_ATK_BUFF" in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["atk"], 1370.44 * 1.24, rel_tol=1e-9)

    def test_kill_atk_s5(self):
        eng = _make(_build("20007", superimposition=5), _stage(_E2_FRAGILE))
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["atk"], 1370.44 * 1.48, rel_tol=1e-9)

    def test_other_kill_no_buff(self):
        """敌方互杀/非装备者击杀不触发（source 过滤）."""
        eng = _make(_build("20007"), _stage(_E2_FRAGILE))
        eng.bus.emit("on_kill", {"source": "e1", "target": "e2", "action_id": ""}, eng.state)
        assert "LC_20007_ATK_BUFF" not in _mods(eng, "w")

    def test_path_gated(self):
        eng = _make(_build("20007", path="destruction"), _stage(_E2_FRAGILE))
        _cast(eng, "w", "t_basic", "e2")
        assert "LC_20007_ATK_BUFF" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 20014 相抗（击杀后速度 +#1，2 回合）
# ---------------------------------------------------------------------------
class TestLC20014:
    def test_base_stats(self):
        eng = _make(_build("20014"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3740.88, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1370.44, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 264.6, rel_tol=1e-9)

    def test_kill_spd_s1(self):
        """S1：击杀 → spd 白值100×1.10=110."""
        eng = _make(_build("20014"), _stage(_E2_FRAGILE))
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["spd"], 110.0, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "w")["LC_20014_ADVERSARIAL_SPD"].duration, 2)

    def test_kill_spd_s5(self):
        eng = _make(_build("20014", superimposition=5), _stage(_E2_FRAGILE))
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["spd"], 118.0, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("20014", path="destruction"), _stage(_E2_FRAGILE))
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21003 唯有沉默（攻击 +#1 常驻；敌数 ≤2 暴击率 +#2）
# ---------------------------------------------------------------------------
class TestLC21003:
    def test_base_stats(self):
        """白值三围（非巡猎位只出白值——机制件不挂，面板=角色+光锥白值）."""
        eng = _make(_build("21003", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1476.28, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 330.75, rel_tol=1e-9)

    def test_atk_and_crit_s1(self):
        """S1：atk 1476.28×1.16=1672.3952（常驻）；单敌 → crit 0.05+0.12=0.17."""
        eng = _make(_build("21003"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["atk"], 1476.28 * 1.16, rel_tol=1e-9)
        assert math.isclose(eff["crit_rate"], 0.17, rel_tol=1e-9), "1 敌 ≤2 → 暴击件生效"

    def test_crit_gate_dynamic(self):
        """3 敌 → 暴击件关（0.05）；2 敌 → 开（0.17）——enable_if 动态门."""
        eng = _make(_build("21003"), _stage(_E2_TENDER, _E3))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9), "3 敌 >2 → 关"
        eng2 = _make(_build("21003"), _stage(_E2_TENDER))
        assert math.isclose(_eff(eng2, "w")["crit_rate"], 0.17, rel_tol=1e-9), "2 敌 ≤2 → 开"

    def test_atk_s5(self):
        eng = _make(_build("21003", superimposition=5))
        assert math.isclose(_eff(eng, "w")["atk"], 1476.28 * 1.32, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.29, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("21003", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["atk"], 1476.28, rel_tol=1e-9), "非巡猎只出白值"
        assert math.isclose(eff["crit_rate"], 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21010 论剑（同目标连击每层 +#1 增伤，换目标解除；max #2=5）
# ---------------------------------------------------------------------------
class TestLC21010:
    def test_base_stats(self):
        eng = _make(_build("21010"))
        assert math.isclose(_eff(eng, "w")["atk"], 1476.28, rel_tol=1e-9)

    def test_stacking_axis_s1(self):
        """S1：首击挂标无层；第 2..6 击叠 1..5 层（每层 all_dmg 0.08），5 层封顶."""
        eng = _make(_build("21010"))
        _cast(eng, "w", "t_basic")
        assert "LC_21010_MARK" in _mods(eng, "e1"), "首击挂标"
        assert "LC_21010_SWORDPLAY_DMG" not in _mods(eng, "w"), "首击无层"
        _cast(eng, "w", "t_basic")
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 1.0)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.08, rel_tol=1e-9)
        for _ in range(4):
            _cast(eng, "w", "t_basic")
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 5.0)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.4, rel_tol=1e-9)
        _cast(eng, "w", "t_basic")
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 5.0), "5 层封顶"

    def test_damage_axis(self):
        """满层伤害手算：1476.28×1.0×1.4（增伤）×0.5（防）×0.9（未破）×1.025（期望暴击）."""
        eng = _make(_build("21010"))
        for _ in range(6):
            _cast(eng, "w", "t_basic")
        a = next(x for x in eng.actions_by_actor["w"] if x.action_id == "t_basic")
        dmg = eng.pipeline.deal_damage(a, eng.state.actors["w"], eng.state.actors["e1"])
        assert math.isclose(dmg.value, 1476.28 * 1.4 * 0.5 * 0.9 * 1.025, rel_tol=1e-9)

    def test_target_change_resets(self):
        """换目标：增益解除 + 标记迁移."""
        eng = _make(_build("21010"), _stage(_E2_TENDER))
        _cast(eng, "w", "t_basic")
        _cast(eng, "w", "t_basic")
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 1.0)
        _cast(eng, "w", "t_basic", "e2")
        assert "LC_21010_SWORDPLAY_DMG" not in _mods(eng, "w"), "换目标立即解除"
        assert "LC_21010_MARK" not in _mods(eng, "e1")
        assert "LC_21010_MARK" in _mods(eng, "e2")

    def test_other_attacker_no_interference(self):
        """队友击中带标/无标目标都不影响装备者的层（source 过滤）."""
        eng = _make(_build("21010"))
        _cast(eng, "w", "t_basic")
        _cast(eng, "w", "t_basic")
        _hit(eng, source="a", target="e1", crit=False)
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 1.0), "队友击中不叠"
        _hit(eng, source="a", target="e2", crit=False)
        assert math.isclose(_mods(eng, "w")["LC_21010_SWORDPLAY_DMG"].stacks, 1.0), "队友击他目标不清"

    def test_path_gated(self):
        eng = _make(_build("21010", path="destruction"))
        _cast(eng, "w", "t_basic")
        _cast(eng, "w", "t_basic")
        assert "LC_21010_MARK" not in _mods(eng, "e1")
        assert "LC_21010_SWORDPLAY_DMG" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 21017 点个关注吧！（普攻/战技增伤 +#1；满能量额外 +#2）
# ---------------------------------------------------------------------------
class TestLC21017:
    def test_base_stats(self):
        eng = _make(_build("21017"))
        assert math.isclose(_eff(eng, "w")["atk"], 1476.28, rel_tol=1e-9)

    def test_dmg_boost_s1(self):
        """S1：basic/skill 类型桶 0.24；终结技桶 0；满能量 → 0.48."""
        eng = _make(_build("21017"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["dmg_bonus"]["basic_dmg_boost"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["skill_dmg_boost"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("ultimate_dmg_boost", 0.0), 0.0, rel_tol=1e-9)
        eng.state.actors["w"].current_energy = 100.0
        eff2 = _eff(eng, "w")
        assert math.isclose(eff2["dmg_bonus"]["basic_dmg_boost"], 0.48, rel_tol=1e-9), "满能量翻倍"
        eng.state.actors["w"].current_energy = 50.0
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["basic_dmg_boost"], 0.24,
                            rel_tol=1e-9), "回落即失——enable_if 现场重估"

    def test_damage_axis(self):
        """普攻手算：1476.28×1.24×0.5×0.9×1.025."""
        eng = _make(_build("21017"))
        a = next(x for x in eng.actions_by_actor["w"] if x.action_id == "t_basic")
        dmg = eng.pipeline.deal_damage(a, eng.state.actors["w"], eng.state.actors["e1"])
        assert math.isclose(dmg.value, 1476.28 * 1.24 * 0.5 * 0.9 * 1.025, rel_tol=1e-9)

    def test_dmg_boost_s5(self):
        eng = _make(_build("21017", superimposition=5))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["basic_dmg_boost"], 0.48, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("21017", path="destruction"))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("basic_dmg_boost", 0.0), 0.0,
                            rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21024 春水初生（速度 +#1 / 增伤 +#2；受伤失效；自身回合结束恢复）
# ---------------------------------------------------------------------------
class TestLC21024:
    def test_base_stats(self):
        eng = _make(_build("21024"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3846.72, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1476.28, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 396.9, rel_tol=1e-9)

    def test_buff_cycle_s1(self):
        """S1：进战 spd 108 + all_dmg 0.12；HP 降低 → 失效；自身回合结束 → 恢复."""
        eng = _make(_build("21024"))
        assert math.isclose(_eff(eng, "w")["spd"], 108.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.12, rel_tol=1e-9)
        eng.bus.emit("on_hp_decrease", {"target": "w", "amount": 10.0, "source": "e1",
                                        "reason": "hit"}, eng.state)
        assert "LC_21024_SPRING_WATER" not in _mods(eng, "w"), "受伤失效"
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        assert "LC_21024_SPRING_WATER" not in _mods(eng, "w"), "他人回合结束不恢复"
        eng.bus.emit("on_turn_end", {"actor": "w"}, eng.state)
        assert "LC_21024_SPRING_WATER" in _mods(eng, "w"), "自身回合结束恢复"
        assert math.isclose(_eff(eng, "w")["spd"], 108.0, rel_tol=1e-9)

    def test_other_hp_decrease_noop(self):
        """队友/敌人 HP 降低不失效（target 过滤）."""
        eng = _make(_build("21024"))
        eng.bus.emit("on_hp_decrease", {"target": "e1", "amount": 10.0, "source": "w",
                                        "reason": "hit"}, eng.state)
        assert "LC_21024_SPRING_WATER" in _mods(eng, "w")

    def test_buff_s5(self):
        eng = _make(_build("21024", superimposition=5))
        assert math.isclose(_eff(eng, "w")["spd"], 112.0, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.24, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("21024", path="destruction"))
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21031 重返幽冥（暴击率 +#1；暴击后固定概率解 1 增益）
# ---------------------------------------------------------------------------
class TestLC21031:
    def test_base_stats(self):
        eng = _make(_build("21031"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3846.72, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1529.2, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 330.75, rel_tol=1e-9)

    def test_crit_rate_s1(self):
        """S1：0.05+0.12=0.17（撞名修复——读绑定参数而非面板）."""
        eng = _make(_build("21031"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.17, rel_tol=1e-9)

    def test_crit_rate_s5(self):
        eng = _make(_build("21031", superimposition=5))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.29, rel_tol=1e-9)

    def test_dispel_expected_mode_negative(self):
        """期望模式 mechanic_chance(0.16)<0.5 恒不触发（口径钉）——敌方增益保留."""
        eng = _make(_build("21031"))
        e1 = eng.state.actors["e1"]
        eng._apply_modifier_spec(e1, {
            "modifier_id": "TEST_BUFF", "name": "测试增益", "modifier_type": "buff",
            "duration": 0, "stat_effects": {"atk_pct": 0.5}}, None)
        assert "TEST_BUFF" in _mods(eng, "e1")
        _hit(eng, source="w", target="e1", crit=True)
        assert "TEST_BUFF" in _mods(eng, "e1"), "期望模式 16% 固定概率恒不生效"

    def test_path_gated(self):
        eng = _make(_build("21031", path="destruction"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21037 最后的赢家（攻击 +#1；暴击叠【好运】max #3=4，每层暴伤 +#2，自身回合结束移除）
# ---------------------------------------------------------------------------
class TestLC21037:
    def test_base_stats(self):
        """白值三围（非巡猎位只出白值）."""
        eng = _make(_build("21037", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1476.28, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 330.75, rel_tol=1e-9)

    def test_atk_s1(self):
        eng = _make(_build("21037"))
        assert math.isclose(_eff(eng, "w")["atk"], 1476.28 * 1.12, rel_tol=1e-9)

    def test_fortune_stacking(self):
        """S1：暴击 1 次 1 层（首击=1 层——修复 staging 双写首击 2 层病）；4 层封顶；
        每层 crit_dmg +0.08."""
        eng = _make(_build("21037"))
        _hit(eng, crit=True)
        assert math.isclose(_mods(eng, "w")["LC_21037_GOOD_FORTUNE"].stacks, 1.0)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.58, rel_tol=1e-9)
        for _ in range(3):
            _hit(eng, crit=True)
        assert math.isclose(_mods(eng, "w")["LC_21037_GOOD_FORTUNE"].stacks, 4.0)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.82, rel_tol=1e-9)
        _hit(eng, crit=True)
        assert math.isclose(_mods(eng, "w")["LC_21037_GOOD_FORTUNE"].stacks, 4.0), "4 层封顶"

    def test_fortune_removed_at_own_turn_end(self):
        eng = _make(_build("21037"))
        _hit(eng, crit=True)
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        assert "LC_21037_GOOD_FORTUNE" in _mods(eng, "w"), "他人回合结束不移除"
        eng.bus.emit("on_turn_end", {"actor": "w"}, eng.state)
        assert "LC_21037_GOOD_FORTUNE" not in _mods(eng, "w"), "自身回合结束移除"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)

    def test_non_crit_no_stack(self):
        eng = _make(_build("21037"))
        _hit(eng, crit=False)
        assert "LC_21037_GOOD_FORTUNE" not in _mods(eng, "w")

    def test_path_gated(self):
        eng = _make(_build("21037", path="destruction"))
        assert math.isclose(_eff(eng, "w")["atk"], 1476.28, rel_tol=1e-9)
        _hit(eng, crit=True)
        assert "LC_21037_GOOD_FORTUNE" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 21047 黑夜如影随行（击破特攻 +#1；进战/击破后速度 +#2 持续 2 回合，每回合限 1 次）
# ---------------------------------------------------------------------------
class TestLC21047:
    def test_base_stats(self):
        eng = _make(_build("21047"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3846.72, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1476.28, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 396.9, rel_tol=1e-9)

    def test_break_effect_and_spd_s1(self):
        """S1：break_effect 0.28（撞名修复——读绑定参数）；进战 spd 108 + 限流闩."""
        eng = _make(_build("21047"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["break_effect"], 0.28, rel_tol=1e-9)
        assert math.isclose(eff["spd"], 108.0, rel_tol=1e-9)
        assert "LC_21047_SPD_GATE" in _mods(eng, "w"), "进战触发后限流闩在场"

    def test_break_retrigger_gated(self):
        """闩在场时击破不重复触发；闩摘除后击破 → 重挂疾影 + 补闩（裸 self 死钩修复）."""
        eng = _make(_build("21047"), _stage(_E2_TENDER))
        del eng.state.actors["w"].modifiers["LC_21047_SPD"]
        del eng.state.actors["w"].modifiers["LC_21047_SPD_GATE"]
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)
        _cast(eng, "w", "t_basic", "e2")   # 10 韧一击击破
        assert eng.state.actors["e2"].broken, "击破事实"
        assert "LC_21047_SPD" in _mods(eng, "w"), "击破后重挂疾影"
        assert math.isclose(_eff(eng, "w")["spd"], 108.0, rel_tol=1e-9)
        assert "LC_21047_SPD_GATE" in _mods(eng, "w"), "每回合限流闩补挂"

    def test_spd_s5(self):
        eng = _make(_build("21047", superimposition=5))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.56, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["spd"], 112.0, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("21047", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["break_effect"], 0.0, rel_tol=1e-9)
        assert math.isclose(eff["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 21062 于那终点再见（暴伤 +#1；战技/追击增伤 +#2）
# ---------------------------------------------------------------------------
class TestLC21062:
    def test_base_stats(self):
        eng = _make(_build("21062"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1529.2, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 396.9, rel_tol=1e-9)

    def test_passive_s1(self):
        """S1：crit_dmg 0.5+0.24=0.74（撞名修复）；skill/fua 类型桶 0.24、basic 桶 0."""
        eng = _make(_build("21062"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_dmg"], 0.74, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["skill_dmg_boost"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["follow_up_dmg_boost"], 0.24, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("basic_dmg_boost", 0.0), 0.0, rel_tol=1e-9)

    def test_passive_s5(self):
        eng = _make(_build("21062", superimposition=5))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_dmg"], 0.9, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["skill_dmg_boost"], 0.4, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("21062", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_dmg"], 0.5, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("skill_dmg_boost", 0.0), 0.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23001 于夜色中（暴击率 +#1；速度 >100 每 10 点档普攻/战技增伤 +#3，max #5=6）
# ---------------------------------------------------------------------------
class TestLC23001:
    def test_base_stats(self):
        eng = _make(_build("23001"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 4058.4, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1582.12, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 463.05, rel_tol=1e-9)

    def test_crit_rate_s1(self):
        """S1：0.05+0.18=0.23（补收 staging 缺失的暴击常驻件）."""
        eng = _make(_build("23001"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.23, rel_tol=1e-9)

    def test_spd_stacks(self):
        """S1：spd 100 → 0 档；130 → 3 档=0.18；160 → 6 档=0.36；170 → 6 档封顶."""
        eng = _make(_build("23001"))
        assert math.isclose(_eff(eng, "w")["dmg_bonus"].get("basic_dmg_boost", 0.0), 0.0,
                            rel_tol=1e-9), "spd 100 无档"
        eng130 = _make(_build("23001", base={"spd": 130}))
        assert math.isclose(_eff(eng130, "w")["dmg_bonus"]["basic_dmg_boost"], 0.18, rel_tol=1e-9)
        assert math.isclose(_eff(eng130, "w")["dmg_bonus"]["skill_dmg_boost"], 0.18, rel_tol=1e-9)
        eng160 = _make(_build("23001", base={"spd": 160}))
        assert math.isclose(_eff(eng160, "w")["dmg_bonus"]["basic_dmg_boost"], 0.36, rel_tol=1e-9)
        eng170 = _make(_build("23001", base={"spd": 170}))
        assert math.isclose(_eff(eng170, "w")["dmg_bonus"]["basic_dmg_boost"], 0.36,
                            rel_tol=1e-9), "6 层封顶"

    def test_damage_axis(self):
        """spd 130 普攻手算：1582.12×1.18×0.5×0.9×(1+0.23×0.5)."""
        eng = _make(_build("23001", base={"spd": 130}))
        a = next(x for x in eng.actions_by_actor["w"] if x.action_id == "t_basic")
        dmg = eng.pipeline.deal_damage(a, eng.state.actors["w"], eng.state.actors["e1"])
        assert math.isclose(dmg.value, 1582.12 * 1.18 * 0.5 * 0.9 * 1.115, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("23001", path="destruction", base={"spd": 160}))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_rate"], 0.05, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"].get("basic_dmg_boost", 0.0), 0.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23012 如泥酣眠（暴伤 +#1；普攻/战技未暴击 → 暴击率 +#2 持续 1 回合，每 3 回合 1 次）
# ---------------------------------------------------------------------------
class TestLC23012:
    def test_base_stats(self):
        eng = _make(_build("23012"))
        assert math.isclose(_eff(eng, "w")["atk"], 1582.12, rel_tol=1e-9)

    def test_crit_dmg_s1(self):
        """S1：0.5+0.30=0.80（撞名修复）."""
        eng = _make(_build("23012"))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.8, rel_tol=1e-9)

    def test_non_crit_buff_and_cooldown(self):
        """期望模式未暴击恒真：普攻命中 → 暴击率 0.05+0.36=0.41 + 冷却闩；闩期内不再触发."""
        eng = _make(_build("23012"))
        _cast(eng, "w", "t_basic")
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.41, rel_tol=1e-9)
        assert "LC_23012_COOLDOWN" in _mods(eng, "w")
        _cast(eng, "w", "t_basic")
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.41, rel_tol=1e-9), "闩期内不重复触发"

    def test_crit_dmg_s5(self):
        eng = _make(_build("23012", superimposition=5))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 1.0, rel_tol=1e-9)
        _cast(eng, "w", "t_basic")
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.65, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("23012", path="destruction"))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9)
        _cast(eng, "w", "t_basic")
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23016 烦恼着，幸福着（暴击率 +#1 / 追击增伤 +#2；追击挂【温驯】max #4=2；
# 击中温驯目标按层加暴伤 +#3——近似建模，偏差见 fixture 头注）
# ---------------------------------------------------------------------------
class TestLC23016:
    ACTIONS = [_basic(), _fua()]

    def test_base_stats(self):
        eng = _make(_build("23016"))
        assert math.isclose(_eff(eng, "w")["atk"], 1582.12, rel_tol=1e-9)

    def test_passive_s1(self):
        eng = _make(_build("23016"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_rate"], 0.23, rel_tol=1e-9)
        assert math.isclose(eff["dmg_bonus"]["follow_up_dmg_boost"], 0.3, rel_tol=1e-9)

    def test_tame_stacking_and_critdmg(self):
        """装备者追击 → 温驯 1..2 层封顶；击中后暴伤 buff=0.12×层（replace 重烘：
        1 层 0.62 → 2 层 0.74 覆盖旧值）."""
        eng = _make(_build("23016", actions=self.ACTIONS))
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "e1")["LC_23016_TAME"].stacks, 1.0)
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.5, rel_tol=1e-9), "首挂当次无暴伤"
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "e1")["LC_23016_TAME"].stacks, 2.0)
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "e1")["LC_23016_TAME"].stacks, 2.0), "2 层封顶"
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.74, rel_tol=1e-9), "0.5+0.12×2"

    def test_other_follow_up_no_tame(self):
        """队友追击不挂温驯（actor 过滤）."""
        eng = _make(_build("23016", actions=self.ACTIONS))
        eng.bus.emit("on_action", {
            "actor": "a", "action_type": "follow_up", "action_id": "a_fua",
            "target_type": "single", "target": "e1", "actor_type": "character"}, eng.state)
        assert "LC_23016_TAME" not in _mods(eng, "e1")

    def test_path_gated(self):
        eng = _make(_build("23016", path="destruction", actions=self.ACTIONS))
        eff = _eff(eng, "w")
        assert math.isclose(eff["crit_rate"], 0.05, rel_tol=1e-9)
        _cast(eng, "w", "t_fua")
        assert "LC_23016_TAME" not in _mods(eng, "e1")


# ---------------------------------------------------------------------------
# 23020 纯粹思维的洗礼（暴伤 +#1；终结技攻击 → 【论辩】增伤 +#4 持续 2 回合）
# ---------------------------------------------------------------------------
class TestLC23020:
    def test_base_stats(self):
        eng = _make(_build("23020"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1582.12, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 529.2, rel_tol=1e-9)

    def test_crit_dmg_s1(self):
        eng = _make(_build("23020"))
        assert math.isclose(_eff(eng, "w")["crit_dmg"], 0.7, rel_tol=1e-9)

    def test_disputation_on_ultimate(self):
        """装备者终结技攻击敌方 → 论辩 all_dmg 0.36、duration 2；队友/非攻击目标不触发."""
        eng = _make(_build("23020"))
        eng.bus.emit("on_ultimate", {"source": "a", "action": "a_ult", "target": "e1"}, eng.state)
        assert "LC_23020_DISPUTATION" not in _mods(eng, "w"), "队友终结技不触发"
        eng.bus.emit("on_ultimate", {"source": "w", "action": "t_ult", "target": "a"}, eng.state)
        assert "LC_23020_DISPUTATION" not in _mods(eng, "w"), "非敌方目标（辅助型）不触发"
        eng.bus.emit("on_ultimate", {"source": "w", "action": "t_ult", "target": "e1"}, eng.state)
        assert "LC_23020_DISPUTATION" in _mods(eng, "w")
        assert math.isclose(_mods(eng, "w")["LC_23020_DISPUTATION"].duration, 2)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.36, rel_tol=1e-9)

    def test_disputation_s5(self):
        eng = _make(_build("23020", superimposition=5))
        eng.bus.emit("on_ultimate", {"source": "w", "action": "t_ult", "target": "e1"}, eng.state)
        assert math.isclose(_eff(eng, "w")["dmg_bonus"]["all"], 0.6, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("23020", path="destruction"))
        eng.bus.emit("on_ultimate", {"source": "w", "action": "t_ult", "target": "e1"}, eng.state)
        assert "LC_23020_DISPUTATION" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23027 驶向第二次生命（击破特攻 +#1；BE ≥ #2=1.5 → 速度 +#4——enable_if 动态门）
# ---------------------------------------------------------------------------
class TestLC23027:
    def test_base_stats(self):
        eng = _make(_build("23027"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 4058.4, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1582.12, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 463.05, rel_tol=1e-9)

    def test_break_effect_s1(self):
        """S1：break_effect 0.6（撞名修复——staging 进战读面板挂 0 值死件）."""
        eng = _make(_build("23027"))
        assert math.isclose(_eff(eng, "w")["break_effect"], 0.6, rel_tol=1e-9)

    def test_spd_gate(self):
        """S1：BE 0.6 < 1.5 → 无加速；基础 BE 1.0（总 1.6 ≥ 1.5）→ spd 112."""
        eng = _make(_build("23027"))
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9), "未过线"
        eng2 = _make(_build("23027", base={"break_effect": 1.0}))
        assert math.isclose(_eff(eng2, "w")["break_effect"], 1.6, rel_tol=1e-9)
        assert math.isclose(_eff(eng2, "w")["spd"], 112.0, rel_tol=1e-9), "过线即生效（动态门）"

    def test_spd_gate_s5(self):
        """S5：BE 1.0 < 1.5 仍不过线；基础 BE 0.6 → 1.6 过线，spd 120."""
        eng = _make(_build("23027", superimposition=5))
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)
        eng2 = _make(_build("23027", superimposition=5, base={"break_effect": 0.6}))
        assert math.isclose(_eff(eng2, "w")["spd"], 120.0, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("23027", path="destruction", base={"break_effect": 1.0}))
        assert math.isclose(_eff(eng, "w")["break_effect"], 1.0, rel_tol=1e-9), "非巡猎无光锥 BE"
        assert math.isclose(_eff(eng, "w")["spd"], 100.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23031 我将，巡征追猎（暴击率 +#1；追击叠【流光】max #3=2；自身回合结束 -1 层）
# ---------------------------------------------------------------------------
class TestLC23031:
    ACTIONS = [_basic(), _fua()]

    def test_base_stats(self):
        eng = _make(_build("23031"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1635.04, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 463.05, rel_tol=1e-9)

    def test_crit_rate_s1(self):
        """S1：0.05+0.15=0.20（补收 staging 缺失的暴击常驻件）."""
        eng = _make(_build("23031"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.2, rel_tol=1e-9)

    def test_luminflux_cycle(self):
        """装备者追击 → 流光 1..2 层封顶；自身回合结束 -1 层；他人追击/回合不干扰."""
        eng = _make(_build("23031", actions=self.ACTIONS))
        eng.bus.emit("on_action", {
            "actor": "a", "action_type": "follow_up", "action_id": "a_fua",
            "target_type": "single", "target": "e1", "actor_type": "character"}, eng.state)
        assert "LC_23031_LUMINFLUX" not in _mods(eng, "w"), "队友追击不叠"
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "w")["LC_23031_LUMINFLUX"].stacks, 1.0)
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "w")["LC_23031_LUMINFLUX"].stacks, 2.0)
        _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "w")["LC_23031_LUMINFLUX"].stacks, 2.0), "2 层封顶"
        eng.bus.emit("on_turn_end", {"actor": "e1"}, eng.state)
        assert math.isclose(_mods(eng, "w")["LC_23031_LUMINFLUX"].stacks, 2.0), "他人回合不扣"
        eng.bus.emit("on_turn_end", {"actor": "w"}, eng.state)
        assert math.isclose(_mods(eng, "w")["LC_23031_LUMINFLUX"].stacks, 1.0), "自身回合结束 -1"

    def test_path_gated(self):
        eng = _make(_build("23031", path="destruction", actions=self.ACTIONS))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)
        _cast(eng, "w", "t_fua")
        assert "LC_23031_LUMINFLUX" not in _mods(eng, "w")


# ---------------------------------------------------------------------------
# 23046 理想燃烧的地狱（暴击率 +#1；施放战技叠攻 +#4 max #5=4；SP 上限支待收）
# ---------------------------------------------------------------------------
class TestLC23046:
    ACTIONS = [_basic(), _skill()]

    def test_base_stats(self):
        eng = _make(_build("23046"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1582.12, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 529.2, rel_tol=1e-9)

    def test_crit_rate_s1(self):
        eng = _make(_build("23046"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.21, rel_tol=1e-9)

    def test_skill_stacking(self):
        """S1：每次战技 atk_pct +0.10×层（白值 1582.12）；4 层封顶 ×1.40."""
        eng = _make(_build("23046", actions=self.ACTIONS))
        _cast(eng, "w", "t_skill")
        assert math.isclose(_mods(eng, "w")["LC_23046_ATK_SKILL_STACK"].stacks, 1.0)
        assert math.isclose(_eff(eng, "w")["atk"], 1582.12 * 1.1, rel_tol=1e-9)
        for _ in range(3):
            _cast(eng, "w", "t_skill")
        assert math.isclose(_mods(eng, "w")["LC_23046_ATK_SKILL_STACK"].stacks, 4.0)
        assert math.isclose(_eff(eng, "w")["atk"], 1582.12 * 1.4, rel_tol=1e-9)
        _cast(eng, "w", "t_skill")
        assert math.isclose(_mods(eng, "w")["LC_23046_ATK_SKILL_STACK"].stacks, 4.0), "4 层封顶"

    def test_basic_no_stack(self):
        eng = _make(_build("23046", actions=self.ACTIONS))
        _cast(eng, "w", "t_basic")
        assert "LC_23046_ATK_SKILL_STACK" not in _mods(eng, "w")

    def test_path_gated(self):
        eng = _make(_build("23046", path="destruction", actions=self.ACTIONS))
        _cast(eng, "w", "t_skill")
        assert "LC_23046_ATK_SKILL_STACK" not in _mods(eng, "w")
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 23056 一场谎言的终幕（暴击率 +#1；进战/每 4 次追击 → 【影噬】3 回合：
# 攻击 +#4 + 敌方全体易伤 +#5——enable_if 跨 actor 门）
# ---------------------------------------------------------------------------
class TestLC23056:
    ACTIONS = [_basic(), _fua()]

    def test_base_stats(self):
        """白值三围（非巡猎位只出白值）."""
        eng = _make(_build("23056", path="destruction"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3846.72, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1635.04, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 529.2, rel_tol=1e-9)

    def test_battle_start_umbra(self):
        """S1：进战影噬——atk 1635.04×1.40=2224.544；e1/e2 易伤 0.20."""
        eng = _make(_build("23056"), _stage(_E2_TENDER))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.23, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "w")["atk"], 1635.04 * 1.4, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "w")["LC_23056_UMBRA_DEVOURER"].duration, 3)
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.2, rel_tol=1e-9)
        assert math.isclose(_eff(eng, "e2")["vulnerability"], 0.2, rel_tol=1e-9)

    def test_fua_regain_and_vuln_gate(self):
        """每 4 次追击重获影噬（计数件满 4 摘除）；影噬失效 → 易伤自动关（跨 actor 门）."""
        eng = _make(_build("23056", actions=self.ACTIONS))
        for _ in range(3):
            _cast(eng, "w", "t_fua")
        assert math.isclose(_mods(eng, "w")["LC_23056_FUA_COUNT"].stacks, 3.0)
        _cast(eng, "w", "t_fua")
        assert "LC_23056_FUA_COUNT" not in _mods(eng, "w"), "满 4 次摘计数件"
        assert "LC_23056_UMBRA_DEVOURER" in _mods(eng, "w"), "重获影噬"
        eng._remove_modifier(eng.state.actors["w"], "LC_23056_UMBRA_DEVOURER", "test")
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.0, rel_tol=1e-9), "影噬失效易伤关"
        for _ in range(4):
            _cast(eng, "w", "t_fua")
        assert "LC_23056_UMBRA_DEVOURER" in _mods(eng, "w"), "再 4 次追击重获"
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.2, rel_tol=1e-9), "重获易伤复效"

    def test_damage_axis(self):
        """进战手算：(1635.04×1.4)×1.0×0.5（防）×0.9（未破）×(1+0.23×0.5)×1.2（易伤）."""
        eng = _make(_build("23056"))
        a = next(x for x in eng.actions_by_actor["w"] if x.action_id == "t_basic")
        dmg = eng.pipeline.deal_damage(a, eng.state.actors["w"], eng.state.actors["e1"])
        assert math.isclose(dmg.value, 1635.04 * 1.4 * 0.5 * 0.9 * 1.115 * 1.2, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("23056", path="destruction"))
        assert math.isclose(_eff(eng, "w")["atk"], 1635.04, rel_tol=1e-9), "非巡猎只出白值"
        assert math.isclose(_eff(eng, "e1")["vulnerability"], 0.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 24001 星海巡航（暴击率 +#1；击杀后攻击 +#4 持续 2 回合；低血暴击支待收）
# ---------------------------------------------------------------------------
class TestLC24001:
    def test_base_stats(self):
        eng = _make(_build("24001"))
        eff = _eff(eng, "w")
        assert math.isclose(eff["hp"], 3952.56, rel_tol=1e-9)
        assert math.isclose(eff["atk"], 1529.2, rel_tol=1e-9)
        assert math.isclose(eff["def_"], 463.05, rel_tol=1e-9)

    def test_crit_rate_s1(self):
        """S1：0.05+0.08=0.13（补收 staging 缺失的暴击常驻件）."""
        eng = _make(_build("24001"))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.13, rel_tol=1e-9)

    def test_kill_atk(self):
        """S1：装备者击杀 → atk 1490.8×1.20=1788.96、duration 2；敌方互杀不触发."""
        eng = _make(_build("24001"), _stage(_E2_FRAGILE))
        eng.bus.emit("on_kill", {"source": "e1", "target": "e2", "action_id": ""}, eng.state)
        assert "LC_24001_ATK_UP" not in _mods(eng, "w")
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["atk"], 1529.2 * 1.2, rel_tol=1e-9)
        assert math.isclose(_mods(eng, "w")["LC_24001_ATK_UP"].duration, 2)

    def test_kill_atk_s5(self):
        eng = _make(_build("24001", superimposition=5), _stage(_E2_FRAGILE))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.21, rel_tol=1e-9)
        _cast(eng, "w", "t_basic", "e2")
        assert math.isclose(_eff(eng, "w")["atk"], 1529.2 * 1.4, rel_tol=1e-9)

    def test_path_gated(self):
        eng = _make(_build("24001", path="destruction"), _stage(_E2_FRAGILE))
        assert math.isclose(_eff(eng, "w")["crit_rate"], 0.05, rel_tol=1e-9)
        _cast(eng, "w", "t_basic", "e2")
        assert "LC_24001_ATK_UP" not in _mods(eng, "w")
