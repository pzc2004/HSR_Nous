"""符玄 1208 模板端到端对轴（验收型批·组3）：真模板 YAML → 编译 → 穷观阵/
慧明辐射/免控链/天赋回血/E2 免死/E6 损失池全链 → 手算全等.

过堂勘正六件（fixture 头注同录）：慧明 stat_exprs 重设计（max_hp 死键→hp flat
+stat_of 跨人）/ 天赋减伤 waterfall→慧明并入 / 免控链重构（grants_immune+
enable_if resource_of 跨人+on_immune 清槽）/ E2 致死 -1 偏移勘正 /
E6 cap 硬编→$self.max_hp / 天律回血 take 3 漏网修复。
2026-09-24 审查勘正：E2 回血时序（瀑内回血→after_being_hit 受击链收尾——
先扣血至 1 后治疗；旧案高血量队友终值低于官方，低血量两序同值未暴露）；
E2 同行动连坐（_e2_window 行动窗标：触发放宽「未用过 || 窗已开」，非插入
on_action 清窗、插入不清——官方 "all ally targets ... during this action" 全救）。

口径常数：符玄白值 hp 1474.704、spd 100、crit 0.05+行迹暴击 0.187=0.237/0.5
（B-TR③ 回填 character_skill_trees 十节点——暴击 0.187/生命+18%/效果抵抗 0.10，
慧明 hp flat 的 stat_of 基数=白值×1.18）；辅手 hp 3000。
慧明 lv10：HP 6% / 暴击 12% / 减伤 18%（E3 联动 lv12=6.6%/13.2%/19.6%）。
假人 def 0 → 防御区 0.5、量子弱点 → 抗性区 1.0、未击破 0.9。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS

FX_HP = 1474.704 * 1.18   # 1740.15072（行迹生命+18%——B-TR③ 回填；慧明 stat_of 基数）


def _build(*, eidolon: int = 0, pre_battle: list | None = None, extra_ally: bool = False):
    member = {"character_template": "1208", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member,
        {"actor_id": "ally", "name": "辅手", "inline": True,
         "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_basic", "name": "普攻", "action_type": "basic",
                      "target_type": "single", "damage_type": "quantum",
                      "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}]
    if extra_ally:
        team.append({"actor_id": "ally2", "name": "辅手二", "inline": True,
                     "base_stats": {"atk": 1500, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": "ally2_basic", "name": "普攻", "action_type": "basic",
                                  "target_type": "single", "damage_type": "quantum",
                                  "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]})
    b = {"team": team,
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "skill", "priority": 50},
            {"condition": "true", "action": "basic", "priority": 0}]}}
    if pre_battle:
        b["pre_battle"] = pre_battle
    return {"build": b}


_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
     "max_toughness": 9999, "weakness": ["quantum"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


@pytest.fixture(scope="module")
def compiled():
    return compile_encounter(_build(), _STAGE, template_roots=TEST_TEMPLATE_ROOTS)


def _make(compiled):
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _fx(eng):
    return eng.state.actors["1208"]


def _cast_skill(eng):
    """战技 120802（self 目标）+ 手动 on_action emit（on_become_target 引擎自发）."""
    fx = _fx(eng)
    a = next(x for x in eng.actions_by_actor["1208"] if x.action_id == "120802")
    eng._execute_action(fx, a)
    eng.bus.emit("on_action", {
        "actor": "1208", "action_type": "skill", "action_id": "120802",
        "target_type": "self", "target": "1208",
        "actor_type": fx.actor.actor_type}, eng.state)


class TestFuXuanCompile:
    def test_resources(self, compiled):
        decls = compiled.resource_decls_by_actor["1208"]
        assert {"_fx_restore", "_fx_cc_block", "_e2_used", "_e2_window", "_e2_pending", "_e6_pool"} <= set(decls)
        assert decls["_fx_restore"]["max"] == 2


class TestMatrixKnowledge:
    def test_skill_matrix_and_aura(self, compiled):
        """战技：矩阵+慧明挂上——全队 HP+6%×符玄 HP / 暴击 +12% / 减伤 +18%（lv10）."""
        eng = _make(compiled)
        _cast_skill(eng)
        fx = _fx(eng)
        assert "FU_XUAN_MATRIX" in fx.modifiers
        assert "FU_XUAN_KNOWLEDGE" in fx.modifiers
        ally_es = eng.pipeline.effective_stats(eng.state.actors["ally"])
        assert math.isclose(ally_es["hp"], 3000 + 0.06 * FX_HP, rel_tol=1e-9), "hp flat 跨人动态"
        assert math.isclose(ally_es["crit_rate"], 0.05 + 0.12, rel_tol=1e-9)
        assert math.isclose(ally_es["dmg_bonus"].get("dmg_reduction", 0.0), 0.18, rel_tol=1e-9), (
            "天赋减伤并入慧明辐射")
        fx_es = eng.pipeline.effective_stats(fx)
        assert math.isclose(fx_es["hp"], FX_HP * 1.06, rel_tol=1e-9), "慧明含符玄自己"
        assert math.isclose(fx.current_energy, 50.0), "阵下战技回能 30+20"

    def test_cc_immune_chain(self, compiled):
        """六壬太岁：免控 1 次全队共享——触发清槽、耗尽后控制正常挂上."""
        eng = _make(compiled)
        _cast_skill(eng)
        fx = _fx(eng)
        ally = eng.state.actors["ally"]
        assert math.isclose(fx.resources["_fx_cc_block"], 1.0)
        assert "FU_XUAN_CC_IMMUNE" in ally.modifiers
        m1 = Modifier(modifier_id="C1", name="冻结", modifier_type="debuff",
                      debuff_kind="control", duration=2)
        assert eng._apply_modifier(ally, m1) is False, "次数在：控制被硬拒（on_immune）"
        assert math.isclose(fx.resources["_fx_cc_block"], 0.0), "触发即清槽"
        m2 = Modifier(modifier_id="C2", name="冻结二", modifier_type="debuff",
                      debuff_kind="control", duration=2)
        assert eng._apply_modifier(ally, m2) is True, "次数耗尽：条件件未启用=免疫不在场"
        # 续战技重置次数（重激活在案）
        _cast_skill(eng)
        assert math.isclose(fx.resources["_fx_cc_block"], 1.0)
        m3 = Modifier(modifier_id="C3", name="冻结三", modifier_type="debuff",
                      debuff_kind="control", duration=2)
        assert eng._apply_modifier(ally, m3) is False, "重置后再免 1 次"


class TestTalent:
    def test_self_heal_below_half(self, compiled):
        """天赋：血线 ≤50% 回已损 90%（lv10）——开战 1 次，用完不触发."""
        eng = _make(compiled)
        _cast_skill(eng)
        fx = _fx(eng)
        max_hp = eng.pipeline.effective_stats(fx)["hp"]  # 慧明后 1.06×行迹后基数
        assert math.isclose(fx.resources["_fx_restore"], 1.0)
        fx.current_hp = max_hp * 0.4
        eng.bus.emit("on_hp_decrease", {"amount": 100.0, "source": "e1",
                                        "reason": "hit", "target": "1208"}, eng.state)
        assert math.isclose(fx.current_hp, max_hp * 0.4 + 0.9 * max_hp * 0.6, rel_tol=1e-9)
        assert math.isclose(fx.resources["_fx_restore"], 0.0)
        fx.current_hp = max_hp * 0.3
        eng.bus.emit("on_hp_decrease", {"amount": 50.0, "source": "e1",
                                        "reason": "hit", "target": "1208"}, eng.state)
        assert math.isclose(fx.current_hp, max_hp * 0.3), "次数耗尽不触发"
        # 大招补 1 次（cap 2）
        fx.current_energy = 135.0
        ult = next(x for x in eng.actions_by_actor["1208"] if x.action_id == "120803")
        assert eng._fire_ultimate(fx, ult) is True
        assert math.isclose(fx.resources["_fx_restore"], 1.0), "终结技补 1 次"

    def test_ult_heal_others(self, compiled):
        """遁甲幽隐：大招治疗其他角色 5%×符玄 MaxHP+133——不含自己."""
        eng = _make(compiled)
        _cast_skill(eng)
        fx = _fx(eng)
        ally = eng.state.actors["ally"]
        max_hp = eng.pipeline.effective_stats(fx)["hp"]
        ally.current_hp = 1000.0
        fx.current_hp = max_hp * 0.5
        fx.current_energy = 135.0
        ult = next(x for x in eng.actions_by_actor["1208"] if x.action_id == "120803")
        assert eng._fire_ultimate(fx, ult) is True
        assert math.isclose(ally.current_hp, 1000 + 0.05 * max_hp + 133, rel_tol=1e-9)
        assert math.isclose(fx.current_hp, max_hp * 0.5), "符玄自己不吃天律回血"


class TestEidolons:
    def _hit_ally(self, eng, target_id, amount):
        """手动镜像引擎受击链（_execute_action 同序）：before_take_damage 瀑布 →
        扣血 → on_hp_decrease → after_being_hit（受击链收尾——E2 回血落地点）."""
        wp = eng.bus.waterfall("before_take_damage", {
            "amount": amount, "damage_type": "quantum", "source": "e1",
            "target": target_id, "action_type": "basic", "is_critical": False}, eng.state)
        ally = eng.state.actors[target_id]
        ally.current_hp -= wp["amount"]
        eng.bus.emit("on_hp_decrease", {"amount": wp["amount"], "source": "e1",
                                        "reason": "hit", "target": target_id}, eng.state)
        eng.bus.emit("after_being_hit", {
            "amount": wp["amount"], "absorbed": 0.0, "damage_type": "quantum",
            "source": "e1", "target": target_id, "is_critical": False, "seg_index": 0,
            "actor_type": "monster", "action_type": "basic", "hit_targets": [target_id]},
            eng.state)
        return wp

    def _end_action(self, eng, actor="e1", insert=False):
        """行动收尾广播（引擎 on_action 在 _execute_action 后发射；insert=插入行动）."""
        eng.bus.emit("on_action", {"actor": actor, "action_type": "basic",
                                   "action_id": "e_atk", "target_type": "aoe",
                                   "target": "ally", "insert": insert,
                                   "actor_type": "monster" if actor == "e1" else "character"},
                    eng.state)

    def test_e2_death_save(self):
        """E2：阵下全队免死 1 次——伤害改写至 1 血 + 回 70% 有效上限 + 闩."""
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        fx = _fx(eng)
        ally = eng.state.actors["ally"]
        ally.current_hp = 500.0
        wp = self._hit_ally(eng, "ally", 1000.0)
        assert math.isclose(wp["amount"], 499.0), "改写为 hp-1（恰好降至 1 血）"
        ally_max = eng.pipeline.effective_stats(ally)["hp"]
        assert math.isclose(ally.current_hp, 1 + 0.7 * ally_max, rel_tol=1e-9)
        assert math.isclose(fx.resources["_e2_used"], 1.0)
        # 行动收尾清窗（两次行动之间必有 on_action）→ 次行动致命不再救（每场一次闩）
        self._end_action(eng)
        assert math.isclose(fx.resources["_e2_window"], 0.0), "行动收尾清窗"
        ally.current_hp = 100.0
        wp2 = self._hit_ally(eng, "ally", 9999.0)
        assert math.isclose(wp2["amount"], 9999.0), "闩+窗尽后原量通过"
        assert math.isclose(ally.current_hp, 100.0 - 9999.0), "不再救：不回血、原量扣血"

    def test_e2_death_save_high_hp(self):
        """E2 时序回归钉：高血量队友（90%）受致命伤——先扣血至 1 再回 70%，终值=1+0.7×max.

        2026-09-24 审查实证：旧案回血挂 before_take_damage 瀑内（扣血前落地），90% 血
        队友 70% 回血被上限钳制后再扣 (hp−1)，终值 311 远低于官方 2174；低血量队友
        （回血不触钳）两序同值，故旧 e2e 未暴露。
        """
        eng = _make(compile_encounter(_build(eidolon=2), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        ally = eng.state.actors["ally"]
        ally_max = eng.pipeline.effective_stats(ally)["hp"]
        ally.current_hp = ally_max * 0.9
        wp = self._hit_ally(eng, "ally", ally_max)
        assert math.isclose(wp["amount"], ally_max * 0.9 - 1, rel_tol=1e-9), (
            "改写为 hp-1（高血量队友同样恰好降至 1 血）")
        assert math.isclose(ally.current_hp, 1 + 0.7 * ally_max, rel_tol=1e-9), (
            "先扣血后治疗：终值=1+0.7×max（旧案瀑内回血被上限钳制只得 0.1×max+1）")

    def test_e2_aoe_multi_save(self):
        """E2 连坐：同一行动（AoE）双队友致死全救（官方 EN "all ally targets who
        were struck by a killing blow during this action"）；插入行动不清窗（队友反击
        不打断连坐）；非插入行动 on_action 清窗；每场一次闩仍生效（次行动不再救）."""
        eng = _make(compile_encounter(_build(eidolon=2, extra_ally=True), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        fx = _fx(eng)
        a1 = eng.state.actors["ally"]
        a2 = eng.state.actors["ally2"]
        a1.current_hp = 500.0
        a2.current_hp = 600.0
        # 同一敌方行动（AoE）先后命中 ally / ally2——行动未收尾（无 on_action），窗保持开
        wp1 = self._hit_ally(eng, "ally", 1000.0)
        assert math.isclose(wp1["amount"], 499.0)
        # 伤害链中插入队友反击（insert on_action）——不清窗，同行动连坐不被打断
        self._end_action(eng, actor="ally", insert=True)
        wp2 = self._hit_ally(eng, "ally2", 1000.0)
        assert math.isclose(wp2["amount"], 599.0), "窗内第二队友同样改写至 hp-1（连坐全救）"
        a1_max = eng.pipeline.effective_stats(a1)["hp"]
        a2_max = eng.pipeline.effective_stats(a2)["hp"]
        assert math.isclose(a1.current_hp, 1 + 0.7 * a1_max, rel_tol=1e-9)
        assert math.isclose(a2.current_hp, 1 + 0.7 * a2_max, rel_tol=1e-9)
        assert math.isclose(fx.resources["_e2_used"], 1.0), "每场一次：首场触发即耗"
        # 行动收尾（非插入 on_action）→ 窗清；次行动致命不再救
        self._end_action(eng)
        assert math.isclose(fx.resources["_e2_window"], 0.0), "行动收尾清窗"
        a1.current_hp = 100.0
        wp3 = self._hit_ally(eng, "ally", 9999.0)
        assert math.isclose(wp3["amount"], 9999.0), "次行动原量通过（每场一次闩生效）"
        assert math.isclose(a1.current_hp, 100.0 - 9999.0)

    def test_e4_ally_hit_energy(self):
        """E4：阵下队友成为攻击目标 → 符玄 +5 能（逐目标结算在案）."""
        eng = _make(compile_encounter(_build(eidolon=4), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        fx = _fx(eng)
        e0 = fx.current_energy
        eng.bus.emit("on_become_target", {
            "target": "ally", "source": "e1", "action_id": "e_atk",
            "action_type": "basic", "insert": False}, eng.state)
        assert math.isclose(fx.current_energy, e0 + 5.0)

    def test_e6_pool_and_ult_bonus(self):
        """E6：阵下全队损血入池 ×2 追加大招（cap 2.4×MaxHP）放后清池——E1/E3/E5 全联动对轴."""
        eng = _make(compile_encounter(_build(eidolon=6), _STAGE,
                                      template_roots=TEST_TEMPLATE_ROOTS))
        _cast_skill(eng)
        fx = _fx(eng)
        e1 = eng.state.actors["e1"]
        eng.bus.emit("on_hp_decrease", {"amount": 777.0, "source": "e1",
                                        "reason": "hit", "target": "ally"}, eng.state)
        assert math.isclose(fx.resources["_e6_pool"], 777.0)
        fx.current_energy = 135.0
        hp1 = e1.current_hp
        ult = next(x for x in eng.actions_by_actor["1208"] if x.action_id == "120803")
        assert eng._fire_ultimate(fx, ult) is True
        # 全联动：E3 战技 lv12 慧明 HP 6.6%/暴击 13.2%、E5 大招 lv12=1.08、E1 暴伤 +30%
        fx_hp = eng.pipeline.effective_stats(fx)["hp"]   # 1740.15072×1.066
        assert math.isclose(fx_hp, FX_HP * 1.066, rel_tol=1e-9)
        crit_zone = 1 + (0.05 + 0.187 + 0.132) * (0.5 + 0.30)
        base = 1.08 * fx_hp + 2 * 777.0   # 大招基数 + E6 追加（cap 1.2×1572 未触）
        assert math.isclose(hp1 - e1.current_hp, base * 0.5 * 0.9 * crit_zone, rel_tol=1e-9)
        assert math.isclose(fx.resources["_e6_pool"], 0.0), "放后清池"


class TestTechnique:
    def test_pre_battle_matrix(self):
        """秘技：进战矩阵 2 回合+慧明+免控次数 1（推定同战技在案）+免疫件全队."""
        eng = _make(compile_encounter(
            _build(pre_battle=[{"actor_id": "1208", "technique": "120807"}]),
            _STAGE, template_roots=TEST_TEMPLATE_ROOTS))
        fx = _fx(eng)
        ally = eng.state.actors["ally"]
        assert "FU_XUAN_MATRIX" in fx.modifiers
        assert "FU_XUAN_KNOWLEDGE" in fx.modifiers
        assert math.isclose(fx.resources["_fx_cc_block"], 1.0), (
            "秘技钩置 1 不被主干初始化覆盖")
        assert "FU_XUAN_CC_IMMUNE" in ally.modifiers
        ally_es = eng.pipeline.effective_stats(ally)
        assert math.isclose(ally_es["hp"], 3000 + 0.06 * FX_HP, rel_tol=1e-9)
        assert math.isclose(ally_es["crit_rate"], 0.17, rel_tol=1e-9)
