"""B35② 段级变体 + 逐击选招 + 段间决策入簿：引擎/web/重放三路测试.

语义钉：index 对齐变体（黄泉混合段型）/ 逐击选招（飞霄，脚本恒取变体 0）/ 段间换目标入
决策簿 record 第四位，重放逐段复现。SP/能量仍行动级结算一次、月茧共享一次伤害事件（不动）。
"""
from __future__ import annotations

import math
import threading
import time

import yaml
from fastapi.testclient import TestClient

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.compile.build_compiler import BuildCompiler
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.policy_api import ScriptedPolicy
from hsr_nous.sim.web import create_app
from hsr_nous.sim_schema.action import Action
from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Encounter, TerminationConfig

from tests.template_materialize import TEST_TEMPLATE_ROOTS


# ---------------------------------------------------------------------------
# 引擎层：变体结算 + 编译闸 + 缺省口径
# ---------------------------------------------------------------------------

def _attacker():
    return Actor(actor_id="atk", name="攻手", level=80,
                 stats=StatBlock(atk=2000, spd=150, hp=3000, max_energy=100,
                                 crit_rate=0.0, crit_dmg=0.5))


def _dummy(eid, hp=1e9, res=None):
    a = Actor(actor_id=eid, name=f"假人{eid[1]}", actor_type="monster", level=80,
              stats=StatBlock(hp=hp, spd=100, max_toughness=9999, weakness=["physical", "thunder"]))
    if res:
        a.stats.resistance = dict(res)
    return a


def _engine(actions, enemies, policy=None, av=70.0):
    enc = Encounter(encounter_id="t", name="t", actors=[_attacker()] + enemies,
                    termination=TerminationConfig(mode="fixed_av", max_action_value=av))
    eng = CombatEngine(enc, actions_by_actor={"atk": actions},
                       policy=policy or ScriptedPolicy(rotation=["skill"]),
                       mode=MODE_EXPECTED, seed=None,
                       initial_sp=10, initial_energy_ratio=0.0)
    eng.setup()
    return eng


class TestInstanceVariants:
    def test_index_aligned_variant_applies(self):
        """index 对齐变体（黄泉族）：seg0 基础行动（单体物理），seg1 变体（群攻雷）."""
        hits = []
        action = Action(
            action_id="s", name="两段", action_type="skill", target_type="single",
            damage_type="physical", scaling=[{"atk": 1.0}], toughness_dmg=10,
            skill_point_cost=1, instances=2,
            instance_variants=[None, {"target_type": "aoe", "damage_type": "thunder",
                                      "scaling": [{"atk": 0.5}], "toughness_dmg": 5}])
        eng = _engine([action], [_dummy("e1"), _dummy("e2")])
        eng.bus.subscribe("after_being_hit", lambda et, p, ctx: hits.append(p))
        state = eng.run()
        seg0 = [h for h in hits if h["seg_index"] == 0]
        seg1 = [h for h in hits if h["seg_index"] == 1]
        assert len(seg0) == 1 and seg0[0]["damage_type"] == "physical", "seg0 基础行动单体物理"
        assert {h["target"] for h in seg1} == {"e1", "e2"}, "seg1 变体群攻打全体"
        assert all(h["damage_type"] == "thunder" for h in seg1)
        # 倍率口径：atk2000 无暴击期望——seg0 单体 1.0、seg1 群攻 0.5（抗性 0 白板）
        assert seg0[0]["amount"] > seg1[0]["amount"], "变体 scaling 覆写生效（1.0 > 0.5）"
        assert math.isclose(state.total_damage, sum(h["amount"] for h in hits), rel_tol=1e-9)

    def test_variant_gate_rejects_bad_key(self):
        with __import__("pytest").raises(ValueError, match="未知键 'label'"):
            BuildCompiler()._compile_action_list(
                [{"action_id": "s", "name": "x", "action_type": "skill", "target_type": "single",
                  "damage_type": "fire", "scaling": [{"atk": 1.0}], "instances": 2,
                  "instance_variants": [None, {"label": "大招"}]}], "t")

    def test_variant_gate_rejects_bad_target_type(self):
        with __import__("pytest").raises(ValueError):
            BuildCompiler()._compile_action_list(
                [{"action_id": "s", "name": "x", "action_type": "skill", "target_type": "single",
                  "damage_type": "fire", "scaling": [{"atk": 1.0}], "instances": 2,
                  "instance_variants": [None, {"target_type": "enemy_single"}]}], "t")

    def test_fixture_compiles_and_default_is_variant0(self):
        """999904 编译透传 + 脚本策略逐击选招恒取变体 0（确定性缺省口径）."""
        build = {"build": {"team": [{"character_template": "999904", "level": 80}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["physical", "thunder"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 400}}}
        eng = CombatEngine.from_compiled(
            compile_encounter(build, stage, template_roots=TEST_TEMPLATE_ROOTS),
            mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        ult = next(a for a in eng.actions_by_actor["999904"] if a.action_type == "ultimate")
        assert ult.segment_choice is True and len(ult.instance_variants) == 2
        hits = []
        eng.bus.subscribe("after_being_hit", lambda et, p, ctx: hits.append(p))
        eng.setup()
        eng.state.actors["999904"].current_energy = 20.0   # 直接满能放大
        eng.run()
        ult_hits = [h for h in hits if h["action_type"] == "ultimate"]
        assert len(ult_hits) >= 3 and len(ult_hits) % 3 == 0, "每次放大 3 段（多轮放大段数成倍）"
        assert all(h["damage_type"] == "physical" for h in ult_hits), (
            "脚本策略逐击选招恒取变体 0（单体物理）——变体 1（群攻雷）不得出现")


# ---------------------------------------------------------------------------
# web 层：手动选招 / 段间换目标 / 入簿重放
# ---------------------------------------------------------------------------

# inline build（web 会话生产根不含 fixtures——模板引用解析不到 999904， inline 自包含）：
# 1 角色（普攻 + 3 段逐击选招终结技：变体 0 单体物理 / 变体 1 群攻雷）对 2 木桩
_WEB_BUILD = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "选招手",
            "level": 80,
            "base_stats": {"atk": 1000, "spd": 134, "hp": 3000, "max_energy": 20},
            "actions": [
                {"action_id": "b", "name": "普攻", "action_type": "basic",
                 "target_type": "single", "damage_type": "physical",
                 "scaling": [{"atk": 1.0}]},
                {"action_id": "u", "name": "三段选斩", "action_type": "ultimate",
                 "target_type": "single", "damage_type": "physical",
                 "scaling": [{"atk": 0.8}], "energy_cost": 20,
                 "instances": 3, "segment_choice": True,
                 "instance_variants": [
                     {"target_type": "single", "damage_type": "physical",
                      "scaling": [{"atk": 0.8}], "toughness_dmg": 10},
                     {"target_type": "aoe", "damage_type": "thunder",
                      "scaling": [{"atk": 0.5}], "toughness_dmg": 10},
                 ]},
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
        "stage_id": "choice_duo",
        "enemies": [
            {"actor_id": "e1", "name": "假人壹", "level": 80, "hp": 1_000_000_000,
             "spd": 50, "weakness": ["physical", "thunder"], "max_toughness": 9999},
            {"actor_id": "e2", "name": "假人贰", "level": 80, "hp": 1_000_000_000,
             "spd": 40, "weakness": ["physical", "thunder"], "max_toughness": 9999},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 600},
    }
}


def _post_thread(client: TestClient, path: str, body: dict | None = None) -> tuple:
    """POST 放线程发（决策点/重放可能阻塞响应）。daemon=True：死锁时僵尸不拖住 pytest."""
    box: dict = {}

    def do_post():
        r = client.post(path, json=body or {})
        box["status"], box["body"] = r.status_code, r.json()

    t = threading.Thread(target=do_post, daemon=True)
    t.start()
    return t, box


class _EvtDrain:
    """事件箱增量收集器：/api/state 与 _op 响应共用单游标增量 events（谁先谁拿不重发）——
    测试要全量事件流必须在每次响应顺手收集，事后补读只剩尾巴."""
    def __init__(self):
        self.events: list = []

    def feed(self, payload: dict | None) -> None:
        self.events.extend((payload or {}).get("events") or [])


def _wait_pending(client: TestClient, phase: str, drain: _EvtDrain | None = None, **match) -> dict:
    """轮询等指定阶段的 pending 出现（10s 兜底；match 键值须同时命中——防陈旧 pending
    竞态：choose 放行后引擎尚未清旧 pending，下一轮轮询可能读到上一段次的残影）."""
    for _ in range(200):
        r = client.get("/api/state").json()
        if drain is not None:
            drain.feed(r)
        p = r.get("pending")
        if p and p["phase"] == phase and all(p.get(k) == v for k, v in match.items()):
            return p
        time.sleep(0.05)
    raise AssertionError(
        f"等不到 pending phase={phase} {match}（当前：{client.get('/api/state').json().get('pending')}）")


def _choose_basic_with_target(client: TestClient, drain: _EvtDrain | None = None) -> None:
    """普攻（单体、2 敌在场）：行动选择 + 目标选择两跳（缺省目标）."""
    client.post("/api/choose", json={"index": 0})
    p = _wait_pending(client, "target", drain)
    client.post("/api/choose", json={"actor_id": p["default"]})


def _drive_first_segmented_ult(client: TestClient, answers: list,
                               drain: _EvtDrain | None = None) -> None:
    """跑完第 1 回合（普攻 → 窗口放大 → 首段选目标 → 按 answers 逐段回答）."""
    _choose_basic_with_target(client, drain)
    _wait_pending(client, "ultimate", drain)
    client.post("/api/choose", json={"actor_id": "hero"})             # 窗口放大
    p = _wait_pending(client, "target", drain)                        # 单体终结技首段选目标
    client.post("/api/choose", json={"actor_id": p["default"]})
    for i, ans in enumerate(answers):                                   # 3 段 → 2 次段间决策
        _wait_pending(client, "segment", drain, seg=i + 2)
        client.post("/api/choose", json=ans)


def _load(client: TestClient) -> None:
    r = client.post("/api/load", json={
        "build_yaml": yaml.safe_dump(_WEB_BUILD, allow_unicode=True),
        "stage_yaml": yaml.safe_dump(_WEB_STAGE, allow_unicode=True),
        "mode": "expected", "seed": None})
    assert r.status_code == 200, r.text


class TestSegmentChoiceWeb:
    def test_manual_pick_variant_and_retarget(self):
        """手动：第 2 段选变体 1（群攻雷）+ 第 3 段换目标 e2——变体表/候选都进 pending."""
        client = TestClient(create_app())
        _load(client)
        drain = _EvtDrain()
        t, _box = _post_thread(client, "/api/step")
        _wait_pending(client, "action", drain)
        _choose_basic_with_target(client, drain)       # 普攻（行动+目标两跳）
        _wait_pending(client, "ultimate", drain)
        client.post("/api/choose", json={"actor_id": "hero"})
        p = _wait_pending(client, "target", drain)     # 单体终结技首段选目标（e1/e2，缺省 e1）
        client.post("/api/choose", json={"actor_id": p["default"]})
        # 第 2 段：pending 带变体表（2 项）与候选（2 敌）——选变体 1
        p = _wait_pending(client, "segment", drain, seg=2)
        assert p["total"] == 3
        assert len(p["variants"]) == 2 and len(p["candidates"]) == 2
        client.post("/api/choose", json={"segment": 1, "variant": 1})
        # 第 3 段：换目标 e2
        p = _wait_pending(client, "segment", drain, seg=3)
        client.post("/api/choose", json={"segment": 1, "actor_id": "e2"})
        t.join(timeout=10)
        assert not t.is_alive()
        drain.feed(_box["body"])
        assert client.get("/api/state").json()["turn_count"] == 1
        # 事件流验证（全量收集自 drain——/api/state 与 _op 响应共用单游标增量事件箱）：
        # seg1 群攻雷打全体、seg2 单体物理打 e2
        hits = [e for e in drain.events if e.get("kind") == "hit"]
        seg1 = [h for h in hits if h.get("seg") == 1]
        assert {h["target"] for h in seg1} == {"e1", "e2"}, "第 2 段选变体 1=群攻"
        seg2 = [h for h in hits if h.get("seg") == 2]
        assert len(seg2) == 1 and seg2[0]["target"] == "e2", "第 3 段换目标 e2"
        # 驱动到请求返回（不留悬挂请求——anyio worker 非 daemon 纪律）
        t, _box = _post_thread(client, "/api/step")
        _wait_pending(client, "action", drain)
        _choose_basic_with_target(client, drain)
        _wait_pending(client, "ultimate", drain)
        client.post("/api/choose", json={"actor_id": "skip"})
        t.join(timeout=10)
        assert not t.is_alive()

    def test_segment_answers_journaled_and_replayed(self):
        """段间决策入簿（record 第四位）：向后 goto 重放，选招/换目标逐段复现不卡死."""
        client = TestClient(create_app())
        _load(client)
        t, _box = _post_thread(client, "/api/step")
        _wait_pending(client, "action")
        # 第 1 回合：选变体 1 + 换目标 e2（与原局决策留痕不同也无妨——重放必须复现同一轨迹）
        _drive_first_segmented_ult(client, [
            {"segment": 1, "variant": 1},
            {"segment": 1, "actor_id": "e2"},
        ])
        t.join(timeout=10)
        assert not t.is_alive()
        # 第 2 回合攒第 2 动（普攻 + skip），决策簿 2 动
        t, _box = _post_thread(client, "/api/step")
        _wait_pending(client, "action")
        _choose_basic_with_target(client)
        _wait_pending(client, "ultimate")
        client.post("/api/choose", json={"actor_id": "skip"})
        t.join(timeout=10)
        assert client.get("/api/state").json()["turn_count"] == 2
        # 向后 goto 1：重放第 1 回合——段间回答（变体 1 / e2）由段间队列逐段供给；
        # 重放段事件重灌事件箱，goto 响应带全量（验证口径=直接对重放流形断言，
        # 不做原局/重放列表相等——原局事件已被轮询增量取走，列表本来就拼不齐）
        t, box = _post_thread(client, "/api/goto", {"n": 1})
        t.join(timeout=10)
        assert not t.is_alive(), "goto 重放卡死——段间队列未在重放段供给"
        assert box["status"] == 200
        assert client.get("/api/state").json()["turn_count"] == 1
        evts_after = (box["body"] or {}).get("events") or []
        seg_hits_after = [(h.get("seg"), h.get("target"))
                          for h in evts_after if h.get("kind") == "hit" and h.get("action_type") == "ultimate"]
        assert (1, "e1") in seg_hits_after and (1, "e2") in seg_hits_after, (
            "重放必须复现选招变体 1（群攻打 e1+e2）——段间回答（1, None）由段间队列供给")
        assert (2, "e2") in seg_hits_after, (
            "重放必须复现换目标 e2——段间回答（None, 'e2'）由段间队列供给")
        # 实时继续并驱动到请求返回（不留悬挂请求）
        t2, _box2 = _post_thread(client, "/api/step")
        _wait_pending(client, "action")
        _choose_basic_with_target(client)
        _wait_pending(client, "ultimate")
        client.post("/api/choose", json={"actor_id": "skip"})
        t2.join(timeout=10)
        assert not t2.is_alive()
