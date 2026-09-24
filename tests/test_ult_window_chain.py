"""终结技窗口连放环（游戏同款）：放一个 → 重查 ready → 再问，直到 skip/无人就绪.

覆盖（owner 实测报错的三案）：
A. 多人同窗口连大——放完一个窗口不关，ready 里还有人就能接着放；
B. 充能连锁——星期日族充能大充满队友后，同窗口接着放队友的大；
C. 全 skip 口径不回破——决策不放时窗口正常关闭、回合照走。
"""
from __future__ import annotations

from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ULT_AFTER_ACTION
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig


def _actor(aid, name, spd):
    return Actor(actor_id=aid, name=name, level=80,
                 stats=StatBlock(atk=2000, spd=spd, hp=3000, max_energy=100))


def _dummy():
    return Actor(actor_id="e1", name="假人", actor_type="monster", level=80,
                 stats=StatBlock(hp=1e9, spd=100, max_toughness=9999, weakness=["physical"]))


def _basic():
    return Action(action_id="basic", name="普攻", action_type="basic", target_type="single",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10)


def _ult(aid, name):
    return Action(action_id=aid, name=name, action_type="ultimate", target_type="aoe",
                  damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=20)


class _ChainFirst:
    """每次拿 ready 第一个（模拟手动"亮了就点"连放）。"""

    ult_timing = ULT_AFTER_ACTION

    def select_action(self, st, legal, eng=None):
        return legal[0]

    def select_target(self, *a, **k):
        return None

    def select_ultimate(self, st, ready, eng=None):
        return ready[0][1] if ready else None


class _NeverUlt(_ChainFirst):
    def select_ultimate(self, st, ready, eng=None):
        return None


def _engine(policy):
    actors = [_actor("a", "甲", 130), _actor("b", "乙", 120), _dummy()]
    enc = Encounter(encounter_id="t", name="t", actors=actors,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=300))
    eng = CombatEngine(enc, actions_by_actor={
        "a": [_basic(), _ult("ult_a", "甲大")],
        "b": [_basic(), _ult("ult_b", "乙大")],
        "e1": [_basic()]},
        policy=policy, mode=MODE_EXPECTED, initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _tap(eng):
    hits = []
    eng.bus.subscribe("on_ultimate",
                      lambda ev, p, ctx: hits.append((p.get("source"), round(ctx.clock, 1))))
    return hits


class TestUltWindowChain:
    def test_multi_ready_chain_same_window(self):
        """A：双人满能同窗口 → 连放且两发同一时钟刻（无 AV 流逝）。"""
        eng = _engine(_ChainFirst())
        eng.state.actors["a"].current_energy = 100
        eng.state.actors["b"].current_energy = 100
        hits = _tap(eng)
        eng.run()
        assert [h[0] for h in hits] == ["a", "b"], f"连放序列错：{hits}"
        assert hits[0][1] == hits[1][1], f"两发不在同窗口：{hits}"

    def test_recharge_chain_same_window(self):
        """B：甲大充满乙（星期日充能大族）→ 重查 ready 后乙同窗口接着放。"""
        eng = _engine(_ChainFirst())
        eng.state.actors["a"].current_energy = 100
        hits = _tap(eng)

        def _fill_b(ev, p, ctx):
            if p.get("source") == "a":
                eng._grant_energy(eng.state.actors["b"], 200,
                                  source="test", action_id=None, reason="test")

        eng.bus.subscribe("on_ultimate", _fill_b)
        eng.run()
        assert [h[0] for h in hits] == ["a", "b"], f"充能连锁序列错：{hits}"
        assert hits[0][1] == hits[1][1], f"连锁不在同窗口：{hits}"

    def test_all_skip_window_closes(self):
        """C：决策永不放 → 窗口正常关闭、回合照走、战斗按预算结束。"""
        eng = _engine(_NeverUlt())
        eng.state.actors["a"].current_energy = 100
        hits = _tap(eng)
        state = eng.run()
        assert hits == []
        assert state.turn_count > 0
