"""B35① 逐段确认（segment_confirm）：instances 段间 checkpoint 协议测试.

三路语义：脚本/编译策略直通（expected/roll 确定性零影响）；手动（web）段间阻塞等确认；
重放段直通（确认不携带信息，决策簿不记账、重放天然安全）。
"""
from __future__ import annotations

import math
import threading
import time

import yaml
from fastapi.testclient import TestClient

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.web import create_app
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 引擎层：语义保持 + 协议钩子计数
# ---------------------------------------------------------------------------

def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.5, crit_dmg=1.0))


def _dummy(eid, hp=1e9):
    return Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
                 stats=StatBlock(hp=hp, spd=100, max_toughness=100, weakness=["fire"]))


def _engine(actions, enemies, policy=None, av=70.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"atk": actions},
                       policy=policy or ScriptedPolicy(rotation=["skill"]),
                       mode=MODE_EXPECTED, seed=None,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


def _seg_skill(**kw):
    base = dict(action_id="s", name="三连斩", action_type="skill", target_type="single",
                damage_type="fire", scaling=[{"atk": 0.5}], toughness_dmg=10,
                skill_point_cost=1, instances=3, segment_confirm=True)
    base.update(kw)
    return Action(**base)


class TestSegmentConfirmSemantics:
    def test_scripted_pass_through_identical(self):
        """脚本策略直通：带/不带 segment_confirm 的同一行动，终态逐字段一致（确定性零影响）."""
        flagged = _engine([_seg_skill()], [_dummy("e1")]).run()
        plain = _engine([_seg_skill(segment_confirm=False)], [_dummy("e1")]).run()
        assert math.isclose(flagged.total_damage, plain.total_damage, rel_tol=1e-9)
        assert flagged.log == plain.log
        assert flagged.skill_points == plain.skill_points
        assert math.isclose(flagged.actors["atk"].current_energy,
                            plain.actors["atk"].current_energy, rel_tol=1e-9)

    def test_checkpoint_count(self):
        """协议钩子第 2 段起每段一次：3 段 → seg 1,2 两次；instances=1 → 零次."""
        class _CountingPolicy(ScriptedPolicy):
            def __init__(self, **kw):
                super().__init__(**kw)
                self.segments: list[int] = []

            def wait_segment(self, actor_state, action, seg_index, engine=None):
                self.segments.append(seg_index)

        pol = _CountingPolicy(rotation=["skill"])
        _engine([_seg_skill()], [_dummy("e1")], policy=pol).run()
        assert pol.segments == [1, 2]

        pol1 = _CountingPolicy(rotation=["skill"])
        _engine([_seg_skill(instances=1)], [_dummy("e1")], policy=pol1).run()
        assert pol1.segments == []

    def test_fixture_compiles_with_flag(self):
        """fixture 999902 编译后 segment_confirm/instances 原样透传（编译器闸 + 词表同步）."""
        build = {"build": {"team": [{"character_template": "999902", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 70}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        ult = next(a for a in eng.actions_by_actor["999902"] if a.action_type == "ultimate")
        assert ult.instances == 3 and ult.segment_confirm is True


# ---------------------------------------------------------------------------
# web 层：手动段间阻塞 + 重放直通
# ---------------------------------------------------------------------------

# inline build：1 角色（普攻 single + 3 段 AoE 终结技 segment_confirm）对 1 木桩
# max_energy=20 + 普攻回 20：一动后终结技就绪（窗口弹出于行动后）
_WEB_BUILD = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "多段手",
            "level": 80,
            "base_stats": {"atk": 1000, "spd": 134, "hp": 3000, "max_energy": 20},
            "actions": [
                {"action_id": "b", "name": "普攻", "action_type": "basic",
                 "target_type": "single", "damage_type": "physical",
                 "scaling": [{"atk": 1.0}]},
                {"action_id": "u", "name": "三段连斩", "action_type": "ultimate",
                 "target_type": "aoe", "damage_type": "physical",
                 "scaling": [{"atk": 0.5}], "energy_cost": 20,
                 "instances": 3, "segment_confirm": True, "toughness_dmg": 10},
            ],
        }],
        "policy": {
            "name": "default",
            "action_rules": [{"condition": "true", "action": "basic", "priority": 0}],
            "target_rules": [],
            "parameters": {},
        },
    }
}

_WEB_STAGE = {
    "stage": {
        "stage_id": "seg_sandbag",
        "enemies": [
            {"actor_id": "e1", "name": "假人", "level": 80, "hp": 1_000_000_000,
             "spd": 50, "weakness": ["physical"], "max_toughness": 9999},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 300},
    }
}

_LOAD = {
    "build_yaml": yaml.safe_dump(_WEB_BUILD, allow_unicode=True),
    "stage_yaml": yaml.safe_dump(_WEB_STAGE, allow_unicode=True),
    "mode": "expected",
    "seed": None,
}


def _post_thread(client: TestClient, path: str, body: dict | None = None) -> tuple:
    """POST 放线程发（决策点/重放可能阻塞响应）。daemon=True：死锁时僵尸不拖住 pytest
    （test_web.py 同款纪律——曾有死锁线程非 daemon，整文件卡到 600s 超时）。"""
    box: dict = {}

    def do_post():
        r = client.post(path, json=body or {})
        box["status"], box["body"] = r.status_code, r.json()

    t = threading.Thread(target=do_post, daemon=True)
    t.start()
    return t, box


def _wait_pending(client: TestClient, phase: str, **match) -> dict:
    """轮询等指定阶段的 pending 出现（10s 兜底；match 键值须同时命中——防陈旧 pending
    竞态：choose 放行后引擎尚未清旧 pending，下一轮轮询可能读到上一段次的残影）."""
    for _ in range(200):
        p = client.get("/api/state").json().get("pending")
        if p and p["phase"] == phase and all(p.get(k) == v for k, v in match.items()):
            return p
        time.sleep(0.05)
    raise AssertionError(
        f"等不到 pending phase={phase} {match}（当前：{client.get('/api/state').json().get('pending')}）")


def _run_first_turn_with_segmented_ult(client: TestClient) -> list:
    """跑完第 1 回合（普攻 → 终结技窗口放大 → 2 次段间确认），返回段间 pending 快照列."""
    client.post("/api/load", json=_LOAD)
    t, _box = _post_thread(client, "/api/step")
    _wait_pending(client, "action")
    client.post("/api/choose", json={"index": 0})                       # 普攻
    _wait_pending(client, "ultimate")
    client.post("/api/choose", json={"actor_id": "hero"})               # 窗口放大
    seen = []
    for i in range(2):                                                  # 3 段 → 2 次段间挂起
        p = _wait_pending(client, "segment", seg=i + 2)
        seen.append((p["action_name"], p["seg"], p["total"]))
        client.post("/api/choose", json={"segment": 1})
    t.join(timeout=10)
    return seen


class TestSegmentConfirmWeb:
    def test_manual_blocks_per_segment(self):
        """手动模式：3 段终结技段间挂起恰 2 次（seg 2/3、3/3），确认后战斗继续推进."""
        client = TestClient(create_app())
        seen = _run_first_turn_with_segmented_ult(client)
        assert seen == [("三段连斩", 2, 3), ("三段连斩", 3, 3)]
        assert client.get("/api/state").json()["turn_count"] == 1
        # 战斗未卡死：下一步推进到第 2 回合行动决策点（敌木桩无行动直过）
        t, _box = _post_thread(client, "/api/step")
        p = _wait_pending(client, "action")
        assert p["actor_id"] == "hero"
        # 驱动到请求返回再收尾——把停在决策点的请求留给进程退出会让 anyio worker
        # （非 daemon）永久阻塞，pytest 退不出（曾因此撞 600s 后台超时）
        client.post("/api/choose", json={"index": 0})
        _wait_pending(client, "ultimate")
        client.post("/api/choose", json={"actor_id": "skip"})
        t.join(timeout=10)
        assert not t.is_alive()

    def test_replay_pass_through_no_hang(self):
        """重放安全：含逐段确认的回合向后 goto，段内重放时段间 hook 直通不卡死（确认不记账）.

        注意 goto 语义：向前 goto = 实时推进（与 step 同款会停在决策点等输入，本就不是
        重放路径）；向后 goto 才是"检查点恢复 + 决策簿重放填缝"——本测走后者。
        """
        client = TestClient(create_app())
        _run_first_turn_with_segmented_ult(client)
        # 再跑第 2 回合（普攻 + 窗口 skip），决策簿攒下 2 动
        t, _box = _post_thread(client, "/api/step")
        _wait_pending(client, "action")
        client.post("/api/choose", json={"index": 0})
        _wait_pending(client, "ultimate")
        client.post("/api/choose", json={"actor_id": "skip"})
        t.join(timeout=10)
        assert client.get("/api/state").json()["turn_count"] == 2
        # 向后 goto 1：恢复检查点 0 + 重放第 1 回合（含逐段确认终结技）——
        # 若段间 hook 在重放段阻塞，本请求死锁（线程 + join 兜底；anyio worker 非
        # daemon，永久阻塞会拖住整个 pytest 进程退不出）
        t, box = _post_thread(client, "/api/goto", {"n": 1})
        t.join(timeout=10)
        assert not t.is_alive(), "goto 重放卡死——段间 hook 未在重放段直通"
        assert box["status"] == 200
        assert client.get("/api/state").json()["turn_count"] == 1
        # 实时继续：下一回合行动决策点正常出现，并驱动到请求返回（同上：不留悬挂请求）
        t2, _box2 = _post_thread(client, "/api/step")
        _wait_pending(client, "action")
        client.post("/api/choose", json={"index": 0})
        _wait_pending(client, "ultimate")
        client.post("/api/choose", json={"actor_id": "skip"})
        t2.join(timeout=10)
        assert not t2.is_alive()
