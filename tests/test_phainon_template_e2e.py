"""白厄全机制模板端到端对轴（刀 1 验收）：真模板 YAML → 编译 → 火种变身全链 → 手算全等.

链：预置火种 10 → T1 战技（+2=12）→ 变身（扣 12，毁伤+4，倒计时 8，初始行动值 expected=0.5）
→ cd1-7 血棘渡亡（各毁伤+2）→ cd8 强制最后一击（均分）→ 提前退出 → 退后政策再战技（火种+2、伤害再加一笔）。
注意：技能等级系统未接（deal_damage 恒 lv1），对轴按 lv1 倍率。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action
from tests.template_materialize import TEST_TEMPLATE_ROOTS

ATK = 582.12 * 1.5            # 含照见英雄本色 1 层（atk_pct 0.5，行迹 hook 进战即挂）
K_ATK = 582.12 * 2.3          # 倒计时：形态 0.8 + 行迹 1 层 0.5（Σpct 白值加算）
CRIT_EXP = 1 + 0.17 * 0.873  # 1.14841（含行迹面板：crit 0.17/0.873）
DEF_RES = 0.5              # 假人 def 0 口径
UNBROKEN = 0.9


@pytest.fixture(scope="module")
def compiled():
    build = {"build": {"team": [{"character_template": "1408", "level": 80}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "not in_state", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]} for i in (1, 2, 3)],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


def _compile_eidolon(n: int):
    """星魂档编译（member.eidolon: N——与模块 fixture 同 build/stage 口径）."""
    build = {"build": {"team": [{"character_template": "1408", "level": 80, "eidolon": n}],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "not in_state", "action": "skill", "priority": 50},
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": f"e{i}", "name": f"假人{i}", "hp": 1e9, "spd": 100,
         "max_toughness": 9999, "weakness": ["physical"]} for i in (1, 2, 3)],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}
    return compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS)


class TestPhainonEidolonParams:
    def test_e5_hook_segments_follow_level(self):
        """param() 随档实证：E5 skill+2/talent+2 → 形态攻击取 lv12=0.88（state_config 同通道）、
        此身为炬暴伤取 lv12=0.33（编译期替换产物直读；弑魂减伤 #2 全档 0.75 扁平不跳在案）."""
        c5 = _compile_eidolon(5)
        lv = next(a for a in c5.build_team if a.actor_id == "1408").skill_levels
        assert lv["skill"] == 12 and lv["talent"] == 12, "E5：战技+2、天赋+2"
        sc = c5.state_configs_by_actor["1408"][0]
        assert math.isclose(sc.stat_effects["atk_pct"], 0.88), (
            "形态攻击随 talent 等级跳档（旧烘焙扁平 0.8）")
        assert math.isclose(sc.stat_effects["hp_pct"], 2.97), (
            "形态生命随档 lv12=2.97（回填勘正：旧取 lv1 行 1.35）")
        cd = [eff["modifier"]["stat_effects"]["crit_dmg"] for h in c5.hooks
              for eff in h.effects
              if eff.get("effect_type") == "apply_modifier"
              and (eff.get("modifier") or {}).get("modifier_id") == "TALENT_140804_CD"]
        assert cd and all(math.isclose(v, 0.33) for v in cd), f"此身为炬暴伤随档 lv12=0.33：{cd}"


class TestPhainonTemplateE2E:
    def _run(self, compiled):
        eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        eng.state.actors["1408"].resources["fire_seed"] += 7.0  # 开局 hook 3 + 预置 7 + T1 战技 2 = 12
        return eng.run()

    def test_full_chain_hand_calc(self, compiled):
        state = self._run(compiled)
        log = state.log

        # 1. 变身与退出发生（日志用形态显示名"卡厄斯兰那"）
        assert any("进入形态 卡厄斯兰那" in l for l in log)
        assert any("退出形态 卡厄斯兰那" in l for l in log)
        # 2. 倒计时 8 动：7 血棘 + 1 最后一击
        assert sum(1 for l in log if "创生•血棘渡亡" in l and "白厄 对 假人1" in l) == 7
        assert sum(1 for l in log if "最后一击" in l) == 3  # aoe 3 怪各一条日志
        # 3. 资源轨迹：火种扣 12→0；倒计时初始行动值 expected=0.5（官方"0~100% 均匀"期望档）→
        #    提前退出 → 1408101 返还 1 → 退后政策再战技 +2（资源轨迹 0→1→3）；
        #    毁伤 4(变身)+2×7(血棘)——2026-09-06 值块 max 消费后 clamp 到官方上限 7（溢出作废，
        #    旧期望 18 是无 clamp 时的假性累计；段数不受 cap 影响（26 段封顶两态同））
        st = state.actors["1408"]
        assert math.isclose(st.resources["fire_seed"], 3.0), (
            f"退出返还 1 + 退后战技 2 = 3：{st.resources}")
        assert math.isclose(st.resources["ruin"], 7.0)
        # 4. 形态已退出
        assert st.state_config is None

        # 5. 伤害全链手算（满级档：战技 lv10 3.0/1.2、血棘 lv6 2.5/0.75（普攻系满级 6）、终结技 lv10 9.6；
        #    提前退出 → 退后二战技，战技×2）
        skill_main = ATK * 3.0 * CRIT_EXP * DEF_RES * UNBROKEN
        skill_sub = ATK * 1.2 * CRIT_EXP * DEF_RES * UNBROKEN
        k_atk = K_ATK
        k_main = k_atk * 2.5 * CRIT_EXP * DEF_RES * UNBROKEN
        k_sub = k_atk * 0.75 * CRIT_EXP * DEF_RES * UNBROKEN
        fin = k_atk * 3.2 * CRIT_EXP * DEF_RES * UNBROKEN  # 9.6/3 均分
        expected = 2 * (skill_main + skill_sub) + 7 * (k_main + k_sub) + 3 * fin
        assert math.isclose(state.total_damage, expected, rel_tol=1e-6), (
            f"手算 {expected:.2f} vs 实际 {state.total_damage:.2f}"
        )

    def test_state_config_registered_from_template(self, compiled):
        """模板 state_config 块经编译进引擎（非手动注册）."""
        assert "1408" in compiled.state_configs_by_actor
        cfg, entry = compiled.state_configs_by_actor["1408"]
        assert cfg.state == "khaslana" and entry == "140803"
        assert cfg.final_action_id == "final_strike"
        assert math.isclose(cfg.stat_effects["atk_pct"], 0.8)
        assert cfg.grants_immune == ["control"], "140805：卡厄斯兰那免疫控制类负面状态"


def _build_with_ally():
    """白厄+增益队友（ally_single 技）——队友技指白厄（编队首=缺省目标）."""
    return {"build": {"team": [
        {"character_template": "1408", "level": 80},
        {"actor_id": "ally", "name": "辅助手", "inline": True,
         "base_stats": {"atk": 1000, "spd": 80, "hp": 3000, "max_energy": 100},
         "actions": [{"action_id": "ally_skill", "name": "鼓舞", "action_type": "skill",
                      "target_type": "ally_single", "damage_type": None, "scaling": []}]},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "true", "action": "basic", "priority": 0}]}}}


_STAGE_FIRE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "火弱假人", "hp": 1e9, "spd": 100,
     "max_toughness": 9999, "weakness": ["fire"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 800}}}


def _monster_atk():
    return Action(action_id="e1_atk", name="撕咬", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 0.1}], toughness_dmg=10)


class TestTalentBecomeTarget:
    """140804 此身为炬：成为技能目标获火种（任意非自源）+ 队友施放暴伤（actor_type_of 队友闸）."""

    def test_seed_any_source_crit_teammate_only(self):
        eng = CombatEngine.from_compiled(
            compile_encounter(_build_with_ally(), _STAGE_FIRE, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        ph = eng.state.actors["1408"]
        seed0 = ph.resources["fire_seed"]              # 开局行迹 hook +3
        eng._execute_action(eng.state.actors["e1"], _monster_atk())
        assert math.isclose(ph.resources["fire_seed"], seed0 + 1), "敌源击中照喂火种"
        assert "TALENT_140804_CD" not in ph.modifiers, (
            "敌方施放不给暴伤——官方限定「若该技能由队友施放」（2026-09-08 补闸）")
        ally = eng.state.actors["ally"]
        a = next(x for x in eng.actions_by_actor["ally"] if x.action_id == "ally_skill")
        eng._execute_action(ally, a)
        assert math.isclose(ph.resources["fire_seed"], seed0 + 2), "队友技指白厄再喂 1 枚"
        mod = ph.modifiers["TALENT_140804_CD"]
        assert mod.duration == 3 and math.isclose(mod.stat_effects["crit_dmg"], 0.3), (
            "队友施放 → 暴伤+30% 3 回合（lv10 #1/#2）")


class TestKhaslanaImmuneAndZone:
    """140805 变身期免疫控制（grants_immune 形态标记件硬拒）+ 境界时墟铁墓
    （压缩口径：banish + ZONE_PHY_WEAK 植弱点 + exit_remove_modifiers——不走 Zone 系统）."""

    def _make(self):
        eng = CombatEngine.from_compiled(
            compile_encounter(_build_with_ally(), _STAGE_FIRE, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        eng.setup()
        return eng

    def _transform(self, eng):
        ph = eng.state.actors["1408"]
        ph.resources["fire_seed"] = 12.0
        ult = next(a for a in eng.actions_by_actor["1408"] if a.action_id == "140803")
        assert eng._fire_ultimate(ph, ult) is True
        return ph

    def test_control_immunity_in_state(self):
        eng = self._make()
        ph = eng.state.actors["1408"]
        ctrl = lambda mid: Modifier(modifier_id=mid, name="冻结",
                                    modifier_type="control", duration=2)
        assert eng._apply_modifier(ph, ctrl("CTRL_PRE")) is True, "变身前控制可上"
        ph = self._transform(eng)
        immunes = []
        eng.bus.subscribe("on_immune", lambda et, p, ctx: immunes.append(p))
        assert eng._apply_modifier(ph, ctrl("CTRL_IN")) is False, "形态内控制硬拒"
        assert "CTRL_IN" not in ph.modifiers
        assert immunes and immunes[0]["target"] == "1408", "on_immune 事件留痕"
        eng.exit_state(ph)
        assert eng._apply_modifier(ph, ctrl("CTRL_POST")) is True, "退出形态后恢复可上"

    def test_zone_physical_weakness_enables_toughness(self):
        eng = self._make()
        ph, e1 = eng.state.actors["1408"], eng.state.actors["e1"]
        basic = next(a for a in eng.actions_by_actor["1408"] if a.action_id == "140801")
        eng._execute_action(ph, basic)
        assert math.isclose(e1.toughness, 9999.0), "常态物理打火弱假人不削韧（own_element 闸）"
        self._transform(eng)
        assert "ZONE_PHY_WEAK" in e1.modifiers, "境界植入物理弱点（apply_modifiers 压缩口径）"
        kbasic = next(a for a in eng.actions_by_actor["1408"] if a.action_id == "140808")
        eng._execute_action(ph, kbasic)
        assert math.isclose(e1.toughness, 9999.0 - 20.0), "植弱点计入有效弱点 → 削韧 20"
        eng.exit_state(ph)
        assert "ZONE_PHY_WEAK" not in e1.modifiers, "exit_remove_modifiers：境界随形态解除"
        eng._execute_action(ph, basic)
        assert math.isclose(e1.toughness, 9999.0 - 20.0), "境界解除后物理不再削韧"
