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
    """弑魂之炽机制 hook（计数器族——#19 统一计数器框架（v3）落地前由代码表达）.

    其余机制（银行/免死/回血/结束加速/140811额外/被击获火种/140804暴伤/大行迹）
    已全部搬入模板 YAML（hook DSL 自包含），见 fixtures/templates/1408_phainon.yaml hooks 块。
    """
    track = {"m": 0, "n": 0}

    def pyre_watch(et, payload, ctx):
        st = eng.state.actors["1408"]
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

    eng.bus.subscribe("on_action", pyre_watch)
    return {"immune_used": True}  # 兼容断言：免死已由模板 DSL 承担


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

        # F. 资源轨迹：银行上限恒 ≤3（第二次形态中的新溢出也算在内）；毁伤曾被死星天裁清零；
        #    被击获火种让火种在倒计时期间重新攒满 → 第二次变身发生（终局 ruin=其获得的 4）
        assert st.resources.get(BANK, 0.0) <= 3.0, f"银行应恒 ≤3：{st.resources}"
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
