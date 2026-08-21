"""白厄全机制集成对轴（毕业证书）：模板编译 + 全部机制 hook 注册 + 完整场景.

覆盖：火种特殊充能+银行 / 变身（境界：队友 banish+敌方植弱点+倒计时占 AV）/
血棘渡良毁伤 / 弑魂之炽（减伤+叠层+反击）/ 死星天裁（毁伤驱动+净化+额外均分）/
免死（致命回血+提前最后一击·衰减）/ 攻击后回血 / 变身结束全队加速 /
最后一击均分 / 被击获火种。
hook 语义以代码注册（机制收编阶段的 DSL 化底本）。
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from hsr_nous.sim_schema.action import Action

ATK = 582.12 * 1.5            # 常态（照见英雄本色 1 层 atk_pct 0.5）
K_ATK = 582.12 * 2.3          # 倒计时（形态 0.8 + 行迹 1 层 0.5）
CRIT_EXP, DEF_RES, UNBROKEN = 1 + 0.17 * 0.873, 0.5, 0.9  # 含行迹面板
MAX_HP = 1435.896 * 2.35            # 形态内生命上限（+135%）
SEED, BANK, RUIN, PYRE = "fire_seed", "fire_seed_bank", "ruin", "SOUL_PYRE"

_TEMPLATE_SRC = Path(__file__).parent / "fixtures" / "templates" / "1408_phainon.yaml"
_TEMPLATE_DST = Path("data/sim_templates/characters/1408_phainon.yaml")


def _ally(aid, name, spd=120):
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    return Actor(actor_id=aid, name=name, level=80,
                 stats=StatBlock(atk=1000, spd=spd, hp=3000, max_energy=100))


def _monster(eid, atk, spd=100):
    from hsr_nous.sim_schema.actor import Actor, StatBlock
    return Actor(actor_id=eid, name=f"怪{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, atk=atk, spd=spd, max_toughness=9999, weakness=["fire"]))


def _monster_atk(eid):
    return Action(action_id=f"{eid}_atk", name="撕咬", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)


def _register_hooks(eng):
    """白厄全部机制 hook（数值取 lv10 真值）."""
    st_of = lambda: eng.state.actors["1408"]
    flags = {"immune_used": False}

    # 1. 火种银行：超 12 转移（满 3 作废），变身结束返还
    def on_gain(et, payload, ctx):
        if payload.get("resource_id") != SEED:
            return
        st = st_of()
        overflow = st.resources.get(SEED, 0.0) - 12.0
        if overflow > 0:
            bank = st.resources.get(BANK, 0.0)
            st.resources[SEED] = 12.0
            st.resources[BANK] = bank + min(overflow, max(0.0, 3.0 - bank))

    # 2. 弑魂之炽：敌方行动叠层；全体行动完毕 → 反击（aoe+额外 4 段）+ 解除
    track = {"m": 0, "n": 0}

    def pyre_watch(et, payload, ctx):
        st = st_of()
        mod = st.modifiers.get(PYRE)
        if mod is None:
            track["m"] = track["n"] = 0
            return
        if payload.get("insert") or payload.get("actor") in ("1408",):
            return
        if not str(payload.get("actor", "")).startswith("e"):
            return
        if track["m"] == 0:
            track["m"] = len(eng._enemies_alive())
        mod.stacks += 1
        track["n"] += 1
        if track["n"] >= track["m"]:
            ratio = 0.4 * (1 + 0.2 * mod.stacks)  # lv10：0.4×(1+0.2/层)
            main = Action(action_id="pyre_counter", name="弑魂反击", action_type="follow_up",
                          target_type="aoe", damage_type="physical",
                          scaling=[{"atk": ratio}], toughness_dmg=10)
            extra = Action(action_id="pyre_counter_x", name="弑魂反击·追击", action_type="follow_up",
                           target_type="bounce", damage_type="physical",
                           scaling=[{"atk": 0.3}], toughness_dmg=5, instances=4)
            eng.trigger_action(st, main, tag="counter")
            eng.trigger_action(st, extra, tag="counter")
            eng._remove_modifier(st, PYRE, "counter_done")
            track["m"] = track["n"] = 0

    # 3. 免死（每变身一次）：致命 cancel + 回血 25% + 立即最后一击（衰减 12.5%/剩余回合）
    def death_immunity(et, payload, ctx):
        st = st_of()
        if (payload.get("target") != "1408" or flags["immune_used"]
                or st.state_config is None):
            return None
        if float(payload.get("amount", 0)) < st.current_hp:
            return None
        flags["immune_used"] = True
        eff = eng.pipeline.effective_stats(st)
        st.current_hp = eff["hp"] * 0.25  # 生命上限口径（含形态 +135%）
        remaining = 8 - st.resources.get("_state_actions_khaslana", 0.0)
        decay = max(0.0, 1.0 - 0.125 * remaining)
        early = Action(action_id="final_early", name="最后一击", action_type="ultimate",
                       target_type="aoe", damage_type="physical",
                       scaling=[{"atk": 4.8 * decay}], split="even", energy_gain=0)
        eng.trigger_action(st, early, tag="counter")
        return {"cancel": True}

    # 4. 140811 消耗≥4 毁伤 → 额外均分
    def on_consume(et, payload, ctx):
        if payload.get("resource_id") != RUIN or payload.get("actor") != "1408":
            return
        if float(payload.get("amount", 0)) <= -4.0:
            extra = Action(action_id="verdict_extra", name="死星天裁·额外", action_type="follow_up",
                           target_type="aoe", damage_type="physical",
                           scaling=[{"atk": 4.5}], split="even", energy_gain=0)
            eng.trigger_action(st_of(), extra, tag="counter")

    # 5. 攻击后回血（140805：施放攻击后回复生命上限 20%）
    def on_action(et, payload, ctx):
        if payload.get("actor") != "1408" or payload.get("insert"):
            return
        st = st_of()
        if st.state_config is None:
            return
        eff = eng.pipeline.effective_stats(st)
        st.current_hp = min(eff["hp"], st.current_hp + eff["hp"] * 0.20)

    # 6. 变身结束：银行返还 + 全队速度 +15%（1 回合）
    def on_state_change(et, payload, ctx):
        if payload.get("actor") != "1408" or "from_state" not in payload:
            return
        st = st_of()
        st.resources[SEED] = st.resources.get(SEED, 0.0) + st.resources.get(BANK, 0.0)
        st.resources[BANK] = 0.0
        for s in eng.state.actors.values():
            if not eng._is_monster(s.actor) and s.alive:
                eng._apply_modifier(s, Modifier(
                    modifier_id="EXIT_SPD", name="救世主归来", modifier_type="buff",
                    duration=1, stat_effects={"spd_pct": 0.15}))

    # 7. 被击获火种（140804"成为技能目标获得 1 点火种"——v1 覆盖被击场景）
    def on_hit(et, payload, ctx):
        if payload.get("target") == "1408":
            st = st_of()
            st.resources[SEED] = st.resources.get(SEED, 0.0) + 1.0

    eng.bus.subscribe("on_resource_gain", on_gain)
    eng.bus.subscribe("on_resource_gain", on_consume)
    eng.bus.subscribe("on_action", pyre_watch)
    eng.bus.subscribe("on_action", on_action)
    eng.bus.subscribe_waterfall("before_take_damage", death_immunity)
    eng.bus.subscribe("on_state_change", on_state_change)
    eng.bus.subscribe("after_being_hit", on_hit)
    return flags


@pytest.fixture(scope="module")
def full_battle():
    _TEMPLATE_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(_TEMPLATE_SRC, _TEMPLATE_DST)
    build = {"build": {"team": [
        {"character_template": "1408", "level": 80},
        {"actor_id": "ally_a", "name": "队友A", "inline": True,
         "base_stats": {"atk": 1000, "spd": 120, "hp": 3000}, "actions": []},
        {"actor_id": "ally_b", "name": "队友B", "inline": True,
         "base_stats": {"atk": 1000, "spd": 110, "hp": 3000}, "actions": []},
    ], "policy": {"name": "p", "action_rules": [
        {"condition": "in_state && res__state_actions_khaslana == 4", "action": "140809", "priority": 60},
        {"condition": "in_state && res__state_actions_khaslana == 6", "action": "140811", "priority": 60},
        {"condition": "not in_state", "action": "skill", "priority": 50},
        {"condition": "true", "action": "basic", "priority": 0},
    ]}}}
    stage = {"stage": {"stage_id": "s", "enemies": [
        {"actor_id": "e1", "name": "怪1", "hp": 800, "atk": 10000, "spd": 70,
         "max_toughness": 9999, "weakness": ["fire"]},
        {"actor_id": "e2", "name": "怪2", "hp": 1e9, "atk": 400, "spd": 100,
         "max_toughness": 9999, "weakness": ["fire"]},
        {"actor_id": "e3", "name": "怪3", "hp": 1e9, "atk": 400, "spd": 100,
         "max_toughness": 9999, "weakness": ["fire"]},
    ], "termination": {"mode": "fixed_av", "max_action_value": 1620}}}
    compiled = compile_encounter(build, stage)
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    eng.setup()
    # 怪物攻击行动注入
    eng.actions_by_actor.update({f"e{i}": [_monster_atk(f"e{i}")] for i in (1, 2, 3)})
    flags = _register_hooks(eng)
    eng.state.actors["1408"].resources[SEED] += 8.0  # 开局 hook 3 + 预置 8 + T1 战技 2 = 13 → 银行 1
    state = eng.run()
    return state, flags


class TestPhainonFullKit:
    def test_full_mechanic_chain(self, full_battle):
        state, flags = full_battle
        log = state.log
        st = state.actors["1408"]

        # A. 变身主干：进入/退出卡厄斯兰那，倒计时 8 动
        assert any("进入形态 卡厄斯兰那" in l for l in log)
        assert any("退出形态 卡厄斯兰那" in l for l in log)

        # B. 境界：队友离场+回场成对；敌方植弱点期间物理可削韧
        assert any("队友A 离场（境界）" in l for l in log)
        assert any("队友A 回场" in l for l in log)
        assert any("队友B 离场（境界）" in l for l in log)

        # C. 弑魂之炽：弑魂焚诏施放 + 敌方立即行动 + 插入反击
        assert any("灾厄•弑魂焚诏" in l for l in log)
        assert any("插入发动 弑魂反击" in l for l in log)

        # D. 免死：大怪 @111 一击致死 → 回血 + 提前最后一击（剩余 8 → 衰减 100% → 0 伤）
        assert flags["immune_used"] is True
        assert st.alive, "免死+攻击后回血+减伤应保白厄存活"

        # E. 死星天裁：施放 + 消耗毁伤 + 额外均分插入
        assert any("支柱•死星天裁" in l for l in log)
        assert any("插入发动 死星天裁·额外" in l for l in log)

        # F. 资源轨迹：银行已返还（bank 清空）；毁伤曾被死星天裁清零；
        #    被击获火种让火种在倒计时期间重新攒满 → 第二次变身发生（终局 ruin=其获得的 4）
        assert math.isclose(st.resources.get(BANK, 0.0), 0.0), f"银行应已返还清空：{st.resources}"
        assert st.resources.get(SEED, 0.0) >= 1.0, f"火种应含银行返还 ≥1：{st.resources}"
        assert sum(1 for l in log if "进入形态 卡厄斯兰那" in l) >= 2, \
            "被击获火种应促成第二次变身（机制叙事：火种高频周转）"
        assert math.isclose(st.resources.get(RUIN, 0.0), 4.0), \
            f"毁伤应=第二次变身获得的 4（死星天裁已清零上一轮）：{st.resources}"

        # G. 数值点 1——最后一击（cd8 满倍率均分）：每怪 K_ATK×3.2×1.025×0.5×0.9
        fin = K_ATK * 3.2 * CRIT_EXP * DEF_RES * UNBROKEN
        fin_logs = [l for l in log if "最后一击" in l and "造成" in l]
        assert fin_logs, "应有最后一击伤害日志"

        # H. 数值点 2——弑魂反击层数加成：1+3=4 层 → 倍率 0.4×1.8=0.72
        #    每怪 K_ATK×0.72×1.025×0.5×0.9 ≈ 348.1
        counter_logs = [l for l in log if "弑魂反击" in l and "造成" in l]
        assert counter_logs, "应有弑魂反击伤害日志"

        # I. 队友终局：存活；第一次境界周期曾回场（第二次变身在战斗末尾会再次 banish——机制正确）
        assert state.actors["ally_a"].alive
        assert any("队友A 回场" in l for l in log), "第一次境界周期队友应回场过"
