"""scheduler 快照辅助测试：_countdown（倒计时状态）+ _spd_now（调度口径速度）进快照.

两字段曾是 B16 比对盲区——倒计时剩余动数/倒计时速度、on_speed_change 后的调度口径
速度不进快照，同种子两局全等校验盖不住它们。句柄是 int，序列化转 str 键保持风格一致。
（快照函数原在 sim/scheduler.py 上，生产零调用，已挪 tests/scheduler_debug.py）
"""
from __future__ import annotations

from hsr_nous.sim.scheduler import Scheduler
from hsr_nous.sim_schema.actor import Actor, StatBlock
from tests.scheduler_debug import snapshot


def _actor(aid, spd, atype="ally"):
    return Actor(actor_id=aid, name=aid, actor_type=atype, level=80,
                 stats=StatBlock(atk=1000, spd=spd, hp=3000, max_energy=100))


def _build() -> Scheduler:
    """确定性操作序列：倒计时授予 + 变速 + 三次弹出（时钟/余距/倒计时均推进）."""
    sch = Scheduler([_actor("a", 100), _actor("b", 80), _actor("e", 50, "monster")])
    sch.grant_countdown("a", 3, 120.0)
    sch.on_speed_change(_actor("b", 80), 80.0, 90.0)
    for _ in range(3):
        sch.next_actor()
    return sch


class TestSchedulerSnapshot:
    def test_snapshot_contains_countdown_and_spd_now(self):
        snap = snapshot(_build())
        assert "countdown" in snap and "spd_now" in snap
        # 句柄 int → str 键（序列化风格一致）
        assert all(isinstance(k, str) for k in snap["countdown"])
        assert all(isinstance(k, str) for k in snap["spd_now"])
        # 全体实体都有调度口径速度
        assert len(snap["spd_now"]) == 3

    def test_countdown_state_visible(self):
        sch = Scheduler([_actor("a", 100)])
        sch.grant_countdown("a", 2, 150.0)
        snap = snapshot(sch)
        h = str(sch.handle_of("a"))
        assert snap["countdown"][h]["left"] == 2
        assert snap["countdown"][h]["spd"] == 150.0

    def test_b16_identical_ops_equal_snapshot(self):
        """B16：同构调度器 + 同操作序列 → snapshot 逐字段全等（含两新字段）."""
        s1, s2 = snapshot(_build()), snapshot(_build())
        assert s1 == s2
        assert s1["countdown"], "倒计时状态必须非空——比对才真盖住盲区"
