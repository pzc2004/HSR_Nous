"""hsr-sim web 冒烟测试：空会话启动 → load 开局 → 两阶段手动决策 → 行动条/回退.

两阶段决策协议：行动 pending（phase=action，choose {index}）→ 目标 pending（phase=target，
choose {actor_id}）。手动决策的并发是核心：step 在后台线程里阻塞等 /api/choose——
TestClient 同步调用会跟着堵死，所以 step 请求本身也放线程里发，主线程轮询
/api/state 等 pending 出现。

行动序（本 fixture，fixed_av=150）：hero spd134(AV74.6) → enemy3 spd130(AV76.9)
→ enemy2 spd110(AV90.9) → enemy1 spd90(AV111.1) → hero(AV149.3) → 之后全部超线截断。
敌人无行动（空过，不触发决策点），所以 hero 的两动是第 1、5 步。
"""

import threading
import time

import yaml
from fastapi.testclient import TestClient

from hsr_nous.sim.web import create_app

# inline fixture：1 角色（普攻 single + 战技 aoe）对 3 怪（不同名/速度/韧性/弱点，供切目标）
HERO_YAML = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "黄泉",
            "level": 80,
            "base_stats": {
                "atk": 3000, "spd": 134, "hp": 1200, "max_energy": 110,
                "crit_rate": 0.5, "crit_dmg": 1.0,
            },
            "actions": [
                {
                    "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                    "target_type": "single", "damage_type": "thunder",
                    "scaling": [{"atk": 1.0}],
                },
                {
                    "action_id": "hero_skill", "name": "剑阵", "action_type": "skill",
                    "target_type": "aoe", "damage_type": "thunder",
                    "scaling": [{"atk": 1.2}], "skill_point_cost": 1,
                },
            ],
        }],
        "policy": {
            "name": "default",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        },
    }
}

STAGE_YAML = {
    "stage": {
        "stage_id": "trio_150",
        "enemies": [
            {"actor_id": "enemy1", "name": "炎华造物", "level": 80,
             "hp": 1_000_000_000, "spd": 90, "weakness": ["fire"], "max_toughness": 60},
            {"actor_id": "enemy2", "name": "霜晶造物", "level": 80,
             "hp": 1_000_000_000, "spd": 110, "weakness": ["thunder", "ice"], "max_toughness": 30},
            {"actor_id": "enemy3", "name": "虚数卒", "level": 80,
             "hp": 1_000_000_000, "spd": 130, "weakness": ["imaginary"], "max_toughness": 90},
        ],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }
}

_LOAD_BODY = {
    "build_yaml": yaml.safe_dump(HERO_YAML, allow_unicode=True),
    "stage_yaml": yaml.safe_dump(STAGE_YAML, allow_unicode=True),
    "mode": "expected",
    "seed": None,
}


def _load(client: TestClient) -> None:
    r = client.post("/api/load", json=_LOAD_BODY)
    assert r.status_code == 200, r.text


def _step_thread(client: TestClient) -> tuple:
    """step 放线程发（决策点会阻塞响应），返回 (线程, 结果箱)。

    daemon=True：死锁/测试中途失败时僵尸线程不拖住 pytest 进程
    （曾有死锁线程非 daemon，整文件卡到 600s 超时）。
    """
    box: dict = {}

    def do_step():
        r = client.post("/api/step")
        box["status"], box["body"] = r.status_code, r.json()

    t = threading.Thread(target=do_step, daemon=True)
    t.start()
    return t, box


def _wait_pending(client: TestClient, phase: str) -> dict:
    """轮询等指定阶段的 pending 出现（10s 兜底）。"""
    for _ in range(200):
        s = client.get("/api/state").json()
        p = s.get("pending")
        if p and p["phase"] == phase:
            return p
        time.sleep(0.05)
    raise AssertionError(f"{phase} 阶段决策点未出现")


def _choose_action_and_target(client: TestClient, action_index: int, target_id: str) -> None:
    """走完两阶段：行动 choose {index} → 等目标 pending → choose {actor_id}。"""
    assert client.post("/api/choose", json={"index": action_index}).status_code == 200
    _wait_pending(client, "target")
    assert client.post("/api/choose", json={"actor_id": target_id}).status_code == 200


def test_index_page():
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200 and "翁法罗斯" in r.text


def test_state_empty_then_load():
    """app 启动不强制 YAML：空会话 state 200（loaded=false），load 后 actors 就位。"""
    client = TestClient(create_app())
    s = client.get("/api/state").json()
    assert s == {"loaded": False, "pending": None}
    _load(client)
    s = client.get("/api/state").json()
    assert s["loaded"] and not s["done"] and s["manual"]  # load 默认手动（对齐 CLI debug）
    assert set(s["actors"]) == {"hero", "enemy1", "enemy2", "enemy3"}
    hero = s["actors"]["hero"]
    assert hero["name"] == "黄泉" and hero["max_hp"] == 1200 and hero["actor_type"] == "character"
    assert s["actors"]["enemy2"]["actor_type"] == "monster"
    assert s["actors"]["enemy2"]["weakness"] == ["thunder", "ice"]
    assert s["last_target"] == {}


def test_two_phase_action_then_target():
    """两阶段流：action pending → choose index → target pending（3 怪候选）→ choose actor_id。"""
    client = TestClient(create_app())
    _load(client)
    t, box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert p["actor_id"] == "hero"
    assert [c["name"] for c in p["choices"]] == ["普攻", "剑阵"]
    # 阶段不符：行动阶段喂 actor_id → 400
    assert client.post("/api/choose", json={"actor_id": "enemy2"}).status_code == 400
    assert client.post("/api/choose", json={"index": 0}).status_code == 200
    p = _wait_pending(client, "target")
    assert p["actor_id"] == "hero" and p["target_type"] == "single"
    assert len(p["candidates"]) == 3  # 3 怪全在候选
    assert {c["actor_id"] for c in p["candidates"]} == {"enemy1", "enemy2", "enemy3"}
    assert p["default"] == "enemy1"   # 无记忆时回首个（编队序）
    # 阶段不符：目标阶段喂 index → 400
    assert client.post("/api/choose", json={"index": 0}).status_code == 400
    assert client.post("/api/choose", json={"actor_id": "enemy2"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive(), "choose 后 step 未完成"
    assert box["status"] == 200, box
    rec = box["body"]["record"]
    assert rec["done"] is False and rec["actor_id"] == "hero"
    # 执行成功且日志含所选目标名
    assert any("霜晶造物" in line for line in box["body"]["logs"])
    assert client.get("/api/state").json()["turn_count"] == 1


def test_target_memory():
    """目标记忆：同一行动方第二次 target pending 的 default == 上次选的 actor_id。"""
    client = TestClient(create_app())
    _load(client)
    # hero 第 1 动：选 enemy2
    t, _box = _step_thread(client)
    _wait_pending(client, "action")
    _choose_action_and_target(client, 0, "enemy2")
    t.join(timeout=10)
    assert client.get("/api/state").json()["last_target"] == {"hero": "enemy2"}
    # 中间 3 步是敌人空过（无行动不触发决策点），同步推进
    for _ in range(3):
        assert client.post("/api/step").status_code == 200
    assert client.get("/api/state").json()["turn_count"] == 4
    # hero 第 2 动：target pending 的 default 应是记忆中的 enemy2
    t, _box = _step_thread(client)
    _wait_pending(client, "action")
    assert client.post("/api/choose", json={"index": 0}).status_code == 200
    p = _wait_pending(client, "target")
    assert p["default"] == "enemy2"
    assert client.post("/api/choose", json={"actor_id": p["default"]}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()


def test_aoe_passthrough_no_target_phase():
    """aoe 行动直通：choose 后 step 直接完成（若弹目标决策点，step 会卡住等 choose）。"""
    client = TestClient(create_app())
    _load(client)
    t, box = _step_thread(client)
    p = _wait_pending(client, "action")
    skill_idx = next(c["index"] for c in p["choices"] if c["name"] == "剑阵")
    assert client.post("/api/choose", json={"index": skill_idx}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive(), "aoe 不应触发目标决策点（step 应直接完成）"
    assert box["status"] == 200
    assert any("剑阵" in line for line in box["body"]["logs"])
    assert client.get("/api/state").json()["pending"] is None


def test_consecutive_decisions_both_pending():
    """回归（owner v1 补）：连续决策点都必须弹 pending（曾 bug：决策 Event 一次 set 不复位，
    第二个决策起 wait() 被陈旧 set 秒放，静默走默认、pending 不再出现）。v2 两阶段同测。"""
    client = TestClient(create_app())
    _load(client)
    # hero 两动（第 1、5 步），每动都是 action→target 两段——四个决策点逐一弹窗即复位正常
    for expected_turns in (1, 5):
        t, _box = _step_thread(client)
        p = _wait_pending(client, "action")
        assert p["actor_id"] == "hero", f"第 {expected_turns} 动行动决策点未出现（Event 未复位）"
        _choose_action_and_target(client, 0, "enemy1")
        t.join(timeout=10)
        assert not t.is_alive()
        assert client.get("/api/state").json()["turn_count"] == expected_turns
        if expected_turns == 1:
            for _ in range(3):  # 敌人 3 步空过
                assert client.post("/api/step").status_code == 200
    assert client.get("/api/state").json()["turn_count"] == 5


def test_unavailable_choices_surfaced():
    """不可用技能灰显下发：被战技点拦下的技能不进 legal，但要在 pending.unavailable 带原因
    （游戏同款灰按钮不是消失——"白厄变身三技能没了"误判之源：0 点时合法集只剩普攻）。"""
    build = yaml.safe_load(yaml.safe_dump(HERO_YAML))   # yaml 往返深拷贝
    build["build"]["team"][0]["actions"][1]["skill_point_cost"] = 9   # 永远不够 → 剑阵必被拦
    client = TestClient(create_app())
    r = client.post("/api/load", json={
        "build_yaml": yaml.safe_dump(build, allow_unicode=True),
        "stage_yaml": _LOAD_BODY["stage_yaml"], "mode": "expected", "seed": None})
    assert r.status_code == 200, r.text
    t, _box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert [c["name"] for c in p["choices"]] == ["普攻"]   # 剑阵不在 legal
    assert p["unavailable"] == [
        {"name": "剑阵", "action_id": "hero_skill", "action_type": "skill",
         "target_type": "aoe", "skill_point_cost": 9, "skill_point_gain": 0,
         "key_hint": "e", "reason": "战技点不足"}]   # 灰技仍占原键位+可预览（data 全带）
    _choose_action_and_target(client, 0, "enemy1")   # 放行收尸
    t.join(timeout=10)
    assert not t.is_alive()


# 终结技 fixture（v2b）：max_energy=20，初始 50%=10，普攻 +20 后必满 → after 窗口必弹 ult 决策
HERO_ULT_YAML = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "黄泉",
            "level": 80,
            "base_stats": {"atk": 3000, "spd": 134, "hp": 1200, "max_energy": 20},
            "actions": [
                {
                    "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                    "target_type": "single", "damage_type": "thunder",
                    "scaling": [{"atk": 1.0}],
                },
                {
                    "action_id": "hero_ult", "name": "终结技·残梦", "action_type": "ultimate",
                    "target_type": "aoe", "damage_type": "thunder",
                    "scaling": [{"atk": 2.4}], "energy_cost": 20,
                },
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

_ULT_LOAD_BODY = {
    "build_yaml": yaml.safe_dump(HERO_ULT_YAML, allow_unicode=True),
    "stage_yaml": _LOAD_BODY["stage_yaml"],
    "mode": "expected",
    "seed": None,
}


def _drive_to_ult_window(client: TestClient) -> tuple:
    """手动模式推进到终结技窗口：step → 行动(普攻) → 目标(enemy1) → ultimate pending。"""
    assert client.post("/api/load", json=_ULT_LOAD_BODY).status_code == 200
    t, box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert [c["name"] for c in p["choices"]] == ["普攻"]  # 能量 10/20 未满，终结技不在 legal
    _choose_action_and_target(client, 0, "enemy1")
    return t, box


def test_manual_ultimate_window_fire():
    """手动终结技：行动后能量满 → phase=ultimate pending（ready 含 key_hint）→ 放行 → 日志含终结技名。"""
    client = TestClient(create_app())
    t, box = _drive_to_ult_window(client)
    p = _wait_pending(client, "ultimate")
    assert p["actor_id"] == "hero"  # 窗口所属行动方
    assert [(r["actor_id"], r["ult_name"], r["key_hint"]) for r in p["ready"]] == [
        ("hero", "终结技·残梦", "1")]
    assert client.post("/api/choose", json={"index": 0}).status_code == 400  # 阶段不符
    assert client.post("/api/choose", json={"actor_id": "enemy1"}).status_code == 400  # 不在 ready
    assert client.post("/api/choose", json={"actor_id": "hero"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    assert any("终结技·残梦" in line for line in box["body"]["logs"])
    assert client.get("/api/state").json()["turn_count"] == 1


def test_manual_ultimate_window_skip():
    """skip 路径：本窗口不放——日志无终结技名、能量保留、回合照常完成。"""
    client = TestClient(create_app())
    t, box = _drive_to_ult_window(client)
    _wait_pending(client, "ultimate")
    assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    assert not any("终结技·残梦" in line for line in box["body"]["logs"])
    s = client.get("/api/state").json()
    assert s["turn_count"] == 1
    assert s["actors"]["hero"]["energy"] == 20  # 跳过不耗能量，下一窗口再问


def test_manual_ultimate_window_chain():
    """窗口连放（游戏同款）：放完一个重查 ready 再弹窗——能跨单位连放直到 skip/无人就绪.

    hero_b 终结技 energy_cost=10（初始 10 即就绪）；hero_a 普攻后满能 → after 窗口
    ready=[hero_a, hero_b]（编队序）。先跨单位放 hero_b → 再弹窗 ready=[hero_a] →
    放掉 → 窗口关闭；两发日志在案、回合只走 1 动。ready 行带 target_type（确认态范围标签）。
    """
    build = yaml.safe_load(yaml.safe_dump(HERO_ULT_YAML))   # yaml 往返深拷贝
    build["build"]["team"][0]["actor_id"] = "hero_a"
    build["build"]["team"][0]["name"] = "甲"
    hero_b = yaml.safe_load(yaml.safe_dump(build["build"]["team"][0]))
    hero_b["actor_id"] = "hero_b"
    hero_b["name"] = "乙"
    hero_b["base_stats"]["spd"] = 100   # 甲先动
    hero_b["actions"][0]["action_id"] = "hero_b_basic"
    hero_b["actions"][1]["action_id"] = "hero_b_ult"
    hero_b["actions"][1]["name"] = "终结技·断罪"
    hero_b["actions"][1]["energy_cost"] = 10   # 初始 10（50%）即就绪
    build["build"]["team"].append(hero_b)
    client = TestClient(create_app())
    r = client.post("/api/load", json={
        "build_yaml": yaml.safe_dump(build, allow_unicode=True),
        "stage_yaml": _LOAD_BODY["stage_yaml"], "mode": "expected", "seed": None})
    assert r.status_code == 200, r.text

    t, box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert p["actor_id"] == "hero_a"
    _choose_action_and_target(client, 0, "enemy1")   # 普攻 → 能量满 → after 窗口

    p = _wait_pending(client, "ultimate")
    assert [r["actor_id"] for r in p["ready"]] == ["hero_a", "hero_b"]
    assert all(r["target_type"] == "aoe" for r in p["ready"])   # 范围标签下发
    assert client.post("/api/choose", json={"actor_id": "hero_b"}).status_code == 200
    p = _wait_pending(client, "ultimate")   # 连放环：放完重查 ready 再弹窗
    assert [r["actor_id"] for r in p["ready"]] == ["hero_a"]
    assert client.post("/api/choose", json={"actor_id": "hero_a"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    logs = box["body"]["logs"]
    assert any("终结技·断罪" in line for line in logs)
    assert any("终结技·残梦" in line for line in logs)
    assert client.get("/api/state").json()["turn_count"] == 1


def test_ult_now_during_action_pending():
    """ult_now 决策点插队终结技（游戏同款随时可大）：行动 pending 中随时可开——
    引擎在决策点内施放（耗能量、日志在案）并重返同一行动决策点（pending 不断）。"""
    client = TestClient(create_app())
    t, _box = _drive_to_ult_window(client)   # 普攻后能量满 → 终结技窗口
    _wait_pending(client, "ultimate")
    assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    for _ in range(3):   # 敌人 3 步空过（角色满能：敌方行动后窗口每步都弹（游戏同款
        # 被击满能即弹）——逐窗 skip 掉，与"本回合窗口已问过、下窗口再问"口径一致）
        t2, _b2 = _step_thread(client)
        _wait_pending(client, "ultimate")
        assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
        t2.join(timeout=10)
        assert not t2.is_alive()
    t, box2 = _step_thread(client)
    p = _wait_pending(client, "action")
    assert p["actor_id"] == "hero"
    # 就绪终结技常态下发（ult_now 按钮取数）
    s = client.get("/api/state").json()
    assert [(u["actor_id"], u["key_hint"]) for u in s["ults"]] == [("hero", "1")]
    # 行动中开大：能量扣掉、日志在案、决策点重返（同 phase 同 actor）
    assert client.post("/api/choose", json={"ult_now": "hero"}).status_code == 200
    fired = False
    for _ in range(200):   # 等引擎线程在决策点内放完（能耗尽=已施放）
        s = client.get("/api/state").json()
        if s["actors"]["hero"]["energy"] < 20:
            fired = True
            break
        time.sleep(0.05)
    assert fired, "ult_now 未扣能量（未施放？）"
    # 全槽常显：放完能量空 → 槽位仍在但 ready=False 带原因（游戏同款灰槽，不是消失）
    assert [(u["actor_id"], u["ready"], u["reason"]) for u in s["ults"]] == [
        ("hero", False, "能量不足")]
    p2 = s["pending"]
    assert p2 and p2["phase"] == "action" and p2["actor_id"] == "hero", "决策点未重返"
    _choose_action_and_target(client, 0, "enemy1")   # 重返后照常下行动
    # 普攻回能又满 → after 窗口再弹（游戏逻辑正常路径，不是死循环）——skip 收尸
    _wait_pending(client, "ultimate")
    assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    assert box2["status"] == 200
    assert any("终结技·残梦" in line for line in box2["body"]["logs"]), "日志缺终结技"
    # 未就绪拒绝：能量已空再放 → 400
    assert client.post("/api/choose", json={"ult_now": "hero"}).status_code == 400


def test_ult_now_entry_ult_consumes_turn(monkeypatch):
    """ult_now 放变身入口技（白厄 140803，ult_quick_cast）：按下即变身、本回合行动被消耗——
    不退回默认放基础普攻（"结束本回合"协议 ult_now 路）；就绪行带 immediate 标记。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    stage = yaml.safe_dump({"stage": {
        "stage_id": "t",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 60}],
        "termination": {"mode": "fixed_av", "max_action_value": 3000}}}, allow_unicode=True)
    assert client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                          "stage_yaml": stage, "mode": "expected"}).status_code == 200
    skills = [0]

    def advance():
        """推进一 turn（step 放线程——决策点挂起会堵响应，主线程直发 = 死锁）并把挂起的
        决策点全部答完（action=战技/target=e1/ultimate=skip）。"""
        t, _box = _step_thread(client)
        for _ in range(400):
            s = client.get("/api/state").json()
            p = s.get("pending")
            if p is None and not t.is_alive():
                t.join(timeout=10)
                return   # 无决策点的 turn（敌方空过/战斗结束）
            if p is not None:
                if p["phase"] == "action":
                    # SP 经济：有点放战技（攒火种），没点普攻（回点）——恒选战技 3 动就断粮
                    want = "140802" if s.get("skill_points", 0) > 0 else "140801"
                    idx = next(c["index"] for c in p["choices"] if c["action_id"] == want)
                    if want == "140802":
                        skills[0] += 1
                    assert client.post("/api/choose", json={"index": idx}).status_code == 200
                elif p["phase"] == "target":
                    assert client.post("/api/choose", json={"actor_id": "e1"}).status_code == 200
                else:
                    assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
            time.sleep(0.05)
        raise AssertionError("advance 未收尾")

    def step_to_action():
        """逐 turn 推进直到我方行动决策点（敌方占位 turn 静默略过）；返回 (pending, box)。
        途中的终结技窗口（敌方行动后窗口——白厄就绪即弹）/目标段一律答掉放行。"""
        for _ in range(6):
            t, box = _step_thread(client)
            p = None
            for _ in range(200):
                s = client.get("/api/state").json()
                cand = s.get("pending")
                if cand and cand.get("phase") == "action":
                    p = cand
                    break
                if cand and cand.get("phase") == "ultimate":
                    assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
                elif cand and cand.get("phase") == "target":
                    assert client.post("/api/choose", json={"actor_id": "e1"}).status_code == 200
                if not t.is_alive() and cand is None:
                    break
                time.sleep(0.05)
            if p is not None:
                return p, t, box
            t.join(timeout=10)
        raise AssertionError("6 turn 内未到我方行动决策点")

    # 火种 3 起，战技 +2/动（SP 经济自平衡），5 动后 13 ≥ 12
    for _ in range(14):
        advance()
        if skills[0] >= 5:
            break
    assert skills[0] == 5, f"战技动数不足：{skills[0]}"

    # 白厄第 6 动决策点：就绪行应含 140803（entry 变身技，immediate=True）
    p, t, box = step_to_action()
    assert p["actor_id"] == "1408"
    s = client.get("/api/state").json()
    row = next((u for u in s["ults"] if u["actor_id"] == "1408"), None)
    assert row is not None, f"就绪行缺白厄变身技：{s['ults']}"
    assert row["immediate"] is True, f"变身技应免确认即放：{row}"

    # 按下即放：变身 + 本回合行动消耗（不许退回默认放 逐火救世）
    assert client.post("/api/choose", json={"ult_now": "1408"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive(), "ult_now 入口技后 step 未收尾"
    assert box["status"] == 200
    bl = box["body"]["logs"]
    assert any("卡厄斯兰那" in l for l in bl), "ult_now 未变身"
    assert not any("逐火救世，行则将至" in l for l in bl), (
        "回合消耗协议失效：ult_now 变身后仍执行了基础普攻")

    # 下一动 = 形态内行动（倒计时回合），形态普攻在合法集
    p2, _t2, _box2 = step_to_action()
    ids = {c["action_id"] for c in p2["choices"]}
    assert "140808" in ids, f"变身后应出形态内普攻：{ids}"
    # 收尾必须放行挂起的决策点（restart → _release_pending）——不然引擎线程堵在
    # _decision_hook 永不返回，线程池 worker 非 daemon，pytest 进程退不出（600s 超时案）
    assert client.post("/api/restart").status_code == 200


def test_auto_ultimate_still_fires():
    """auto 回归：编译策略照旧自动放（select_ultimate 旧口径——只放行动方自己的）。"""
    client = TestClient(create_app())
    assert client.post("/api/load", json=_ULT_LOAD_BODY).status_code == 200
    client.post("/api/mode", json={"mode": "auto"})
    r = client.post("/api/step")
    assert r.status_code == 200
    assert any("终结技·残梦" in line for line in r.json()["logs"])
    assert client.get("/api/state").json()["pending"] is None


def test_choose_without_pending_400():
    client = TestClient(create_app())
    _load(client)
    assert client.post("/api/choose", json={"index": 0}).status_code == 400
    assert client.post("/api/choose", json={"actor_id": "enemy1"}).status_code == 400
    assert client.post("/api/choose", json={}).status_code == 400


def test_bar_sorted_and_back():
    """auto 模式：行动条 eta 有序；step ×2 后 back 1，turn_count 回退。"""
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    assert client.post("/api/mode", json={"mode": "auto"}).json() == {"ok": True, "manual": False}
    assert client.post("/api/step").status_code == 200
    bar = client.get("/api/bar").json()
    assert bar and [e["eta"] for e in bar] == sorted(e["eta"] for e in bar)
    assert {"actor_id", "name", "kind", "eta"} <= set(bar[0])
    assert client.post("/api/step").status_code == 200
    assert client.get("/api/state").json()["turn_count"] == 2
    r = client.post("/api/back", json={"n": 1})
    assert r.status_code == 200 and r.json()["logs_reset"]
    assert client.get("/api/state").json()["turn_count"] == 1


def test_manual_back_no_hang():
    """manual 模式回退：重放段目标 hook 直通（replay 短路），back 不卡死。"""
    client = TestClient(create_app())
    _load(client)
    t, _box = _step_thread(client)
    _wait_pending(client, "action")
    _choose_action_and_target(client, 0, "enemy3")
    t.join(timeout=10)
    assert client.get("/api/state").json()["turn_count"] == 1
    r = client.post("/api/back", json={"n": 1})  # 重放段若弹目标决策点会堵死（busy 闸外无 choose）
    assert r.status_code == 200
    assert client.get("/api/state").json()["turn_count"] == 0


def test_inspect_and_snapshot():
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    d = client.get("/api/inspect/hero").json()
    assert d["actor_id"] == "hero" and d["current_hp"] == 1200
    assert client.get("/api/inspect/黄泉").status_code == 200  # 中文名寻址
    assert client.get("/api/inspect/nobody").status_code == 404
    snap = client.get("/api/snapshot").json()
    assert "actors" in snap and "turn_count" in snap


def test_break_turn_and_continue():
    """断点 + 连续推进：auto 模式下 continue 停在断点动。"""
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    client.post("/api/mode", json={"mode": "auto"})
    assert client.post("/api/break", json={"kind": "turn", "value": 3}).status_code == 200
    r = client.post("/api/continue", json={})
    assert r.status_code == 200
    assert client.get("/api/state").json()["turn_count"] == 3
    assert client.post("/api/clear_breaks").status_code == 200
    r = client.post("/api/continue", json={})  # 无断点跑到 fixed_av 截断终局
    assert r.json()["record"]["done"] is True
    assert client.get("/api/state").json()["done"]


# ---------------------------------------------------------------------------
# v3 启动界面：配置库 API（大厅）
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from hsr_nous.sim import battles as _battles  # noqa: E402

_SAVE_BODY = {
    "name": "网页测试局",
    "description": "大厅自定义配置",
    "build_yaml": _LOAD_BODY["build_yaml"],
    "stage_yaml": _LOAD_BODY["stage_yaml"],
}


@pytest.fixture
def battles_dir(tmp_path, monkeypatch):
    """配置库隔离到 tmp（不碰真实 data/battles）。"""
    d = tmp_path / "battles"
    monkeypatch.setattr(_battles, "BATTLES_DIR", d)
    return d


def test_battles_api_crud(battles_dir):
    """三端点往返：GET 自动物化 3 演示局 → save 自定义 → delete 删；未知名 404、坏名 400。"""
    client = TestClient(create_app())
    entries = client.get("/api/battles").json()
    assert len(entries) == 3  # 空目录自动物化三个内置演示配置
    demo = next(e for e in entries if e["name"] == "demo_黄泉队")
    assert demo["description"] and demo["team_preview"] and demo["stage_preview"]
    assert {"name", "description", "team_preview", "stage_preview"} == set(demo)
    # save：自定义配置入库并进列表（带 preview）
    assert client.post("/api/battles/save", json=_SAVE_BODY).json() == {"ok": True}
    entries = client.get("/api/battles").json()
    assert len(entries) == 4
    hit = next(e for e in entries if e["name"] == "网页测试局")
    assert hit["team_preview"] == ["黄泉"] and hit["stage_preview"] == ["炎华造物", "霜晶造物", "虚数卒"]
    # delete：删掉即消失；再删 404；坏名 400
    assert client.post("/api/battles/delete", json={"name": "网页测试局"}).json() == {"ok": True}
    assert len(client.get("/api/battles").json()) == 3
    assert client.post("/api/battles/delete", json={"name": "网页测试局"}).status_code == 404
    assert client.post("/api/battles/delete", json={"name": "a/b"}).status_code == 400
    assert client.post("/api/battles/save", json={**_SAVE_BODY, "build_yaml": "foo: 1"}).status_code == 400


def test_load_by_config_from_library(battles_dir):
    """大厅[开始] 路径：/api/load {config} 从库取局开局；未知配置 404。"""
    client = TestClient(create_app())
    assert client.post("/api/battles/save", json=_SAVE_BODY).status_code == 200
    assert client.post("/api/load", json={"config": "不存在"}).status_code == 404
    r = client.post("/api/load", json={"config": "网页测试局"})
    assert r.status_code == 200 and r.json()["logs_reset"]
    s = client.get("/api/state").json()
    assert s["loaded"] and set(s["actors"]) == {"hero", "enemy1", "enemy2", "enemy3"}


def test_custom_start_without_save_keeps_library(battles_dir):
    """自定义[仅开始]：直接 load 不存库——开局成功且配置库条目数不变。"""
    client = TestClient(create_app())
    before = len(client.get("/api/battles").json())
    r = client.post("/api/load", json=_LOAD_BODY)  # 大厅[仅开始] 走的就是 /api/load 原文 YAML
    assert r.status_code == 200
    assert client.get("/api/state").json()["loaded"]
    assert len(client.get("/api/battles").json()) == before


# ---------------------------------------------------------------------------
# v3 增量：技能详情 / C 面板聚合 / effective 数值块 / buff 徽章
# ---------------------------------------------------------------------------

def test_unit_skills_inline_and_state_badge_fields():
    """①③ inline 局：/api/unit_skills 返回全技能详情（lv 全表/耗点/回能/削韧，desc=None）；
    /api/state 单位卡带 modifier_list（徽章 chips 取数）。"""
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    skills = client.get("/api/unit_skills/hero").json()
    assert [s["name"] for s in skills] == ["普攻", "剑阵"]
    basic, skill = skills
    assert basic["scaling"] == [{"atk": 1.0}] and basic["toughness_dmg"] == 0  # fixture 未给削韧
    assert basic["energy_gain"] == 20 and basic["energy_gain_default"]  # None → 按类型缺省
    assert skill["skill_point_cost"] == 1 and skill["desc"] is None     # inline 无描述
    # 中文名寻址 + 404
    assert client.get("/api/unit_skills/黄泉").status_code == 200
    assert client.get("/api/unit_skills/nobody").status_code == 404
    assert client.get("/api/unit_sheet/nobody").status_code == 404
    s = client.get("/api/state").json()
    assert s["actors"]["hero"]["modifier_list"] == [] and s["actors"]["hero"]["modifiers"] == 0


def test_unit_sheet_inline_empty_blocks():
    """② inline 假人：unit_sheet 聚合端点——技能有，星魂/光锥/遗器各块为空（前端"无数据"）。"""
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    sheet = client.get("/api/unit_sheet/hero").json()
    assert sheet["actor_id"] == "hero" and sheet["name"] == "黄泉"
    assert [s["name"] for s in sheet["skills"]] == ["普攻", "剑阵"]
    assert sheet["eidolons"] == [] and sheet["light_cone"] is None and sheet["relics"] is None
    enemy = client.get("/api/unit_sheet/enemy1").json()  # 敌人也出面板（全空块）
    assert enemy["eidolons"] == [] and enemy["light_cone"] is None and enemy["relics"] is None


def test_inspect_effective_and_modifier_detail():
    """② /api/inspect 增强：effective 有效面板块（inline 无 modifier 时 == 裸面板）+
    modifier_detail 完整明细（名字/层数/时长/来源/数值）。"""
    client = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    d = client.get("/api/inspect/hero").json()
    eff = d["effective"]
    assert eff["atk"] == 3000 and eff["hp"] == 1200 and eff["spd"] == 134
    assert eff["crit_rate"] == 0.5 and eff["crit_dmg"] == 1.0
    assert {"def", "break_effect", "effect_hit", "effect_res", "energy_regen", "heal_bonus"} <= set(eff)
    assert d["modifier_detail"] == []


# ---- 真角色模板形态（hermetic：临时模板根造假角色/光锥/遗器模板）----

_FAKE_ROOT_DOCS = {
    "characters/9999_测试员.yaml": {
        "actor_id": "9999", "name": "测试员", "level": 80,
        "base_stats": {"hp": 3000, "atk": 1000, "def": 500, "spd": 120,
                       "crit_rate": 0.1, "crit_dmg": 0.5, "max_energy": 100},
        "actions": [{
            "action_id": "fake_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 1.0}, {"atk": 1.6}],
            "energy_gain": 20, "toughness_dmg": 10,
            "desc": "模板原文描述：一段测试用普攻。",
        }],
        "eidolons": {
            "E1": {"name": "一魂", "notes": ["一魂描述文本"]},
            "E2": {"name": "二魂"},
        },
    },
    "light_cones/23001_测试锥.yaml": {
        "light_cone_id": 23001, "name": "测试锥", "rarity": 5, "path": "Destruction",
        "base_stats": {"hp": 100, "atk": 50, "def": 30},
        "lookup_tables": {}, "variable_bindings": [],
        "notes": ["测试锥效果描述：攻击力提高。"],
    },
    "relics/199_测试套.yaml": {
        "relic_set_id": 199, "name": "测试套",
        "set_2pc": {"desc": "两件", "stat_effects": {"atk_pct": 0.1}},
        "set_4pc": {"desc": "四件"}, "notes": [],
    },
    "relics/399_测试位面.yaml": {
        "relic_set_id": 399, "name": "测试位面",
        "set_2pc": {"desc": "位面两件", "stat_effects": {"atk_pct": 0.1}},
        "notes": [],
    },
    "enemies/8001_测试怪.yaml": {
        "enemy_id": "8001", "name": "测试怪", "level": 80,
        "base_stats": {"hp": 500000, "atk": 500, "def": 100, "spd": 100,
                       "max_toughness": 60, "effect_res": 0},
        "weakness": ["fire", "thunder"],
        "actions": [],
    },
    # 表单测试专用干净角色（无 desc——desc 非编译合法键；9999 带 desc 仅供 unit_sheet 取数）
    "characters/8888_表单员.yaml": {
        "actor_id": "8888", "name": "表单员", "level": 80,
        "base_stats": {"hp": 3000, "atk": 1000, "def": 500, "spd": 120,
                       "crit_rate": 0.1, "crit_dmg": 0.5, "max_energy": 100},
        "actions": [{
            "action_id": "form_basic", "name": "表单普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "fire",
            "scaling": [{"atk": 1.0}], "energy_gain": 20, "toughness_dmg": 10,
        }],
    },
}


@pytest.fixture
def fake_template_root(tmp_path, monkeypatch):
    """临时模板根：编译（build/stage_compiler）与取数（battles.template_doc/catalog）三侧都指向它。"""
    root = tmp_path / "templates"
    for rel, doc in _FAKE_ROOT_DOCS.items():
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(_battles, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    from hsr_nous.sim.compile import build_compiler, stage_compiler
    monkeypatch.setattr(build_compiler, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    monkeypatch.setattr(stage_compiler, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    return root


_FAKE_BUILD = yaml.safe_dump({"build": {
    "team": [{   # inline 成员（编译自包含）；同名 actor_id 的假角色模板只供 unit_sheet 取
                 # desc/eidolons——desc 尚非 DSL 合法键，模板进编译会被 _ACTION_KEYS 拒
        "character_template": "inline", "actor_id": "9999", "name": "测试员", "level": 80,
        "eidolon": 1,
        "base_stats": {"hp": 3000, "atk": 1000, "def": 500, "spd": 120,
                       "crit_rate": 0.1, "crit_dmg": 0.5, "max_energy": 100},
        "actions": [{
            "action_id": "fake_basic", "name": "测试普攻", "action_type": "basic",
            "target_type": "single", "damage_type": "physical",
            "scaling": [{"atk": 1.0}, {"atk": 1.6}],
            "energy_gain": 20, "toughness_dmg": 10,
        }],
        "light_cone_template": "23001",
        "light_cone": {"level": 80, "superimposition": 2},
        "relics": {
            "head": {"set_id": "199", "main": "hp", "subs": {"spd": 1, "atk_pct": 2}},
            "body": {"set_id": "199", "main": "atk_pct", "subs": {"spd": 1}},
        },
    }],
    "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}],
               "target_rules": [], "parameters": {}},
}}, allow_unicode=True)


def test_unit_sheet_real_character_form(fake_template_root):
    """② 真角色形态：星魂（含激活位+描述）、光锥（名+叠影+描述）、遗器（套装+部位词条）一处取数。"""
    client = TestClient(create_app(_FAKE_BUILD, _LOAD_BODY["stage_yaml"], mode="expected"))
    sheet = client.get("/api/unit_sheet/9999").json()
    assert sheet["name"] == "测试员"
    # 技能：模板 desc 按 action_id 合入
    sk = sheet["skills"][0]
    assert sk["name"] == "测试普攻" and sk["desc"] == "模板原文描述：一段测试用普攻。"
    assert sk["scaling"] == [{"atk": 1.0}, {"atk": 1.6}]  # lv1/lv2 全表
    # 星魂：E1 激活（build eidolon:1），E2 未激活
    assert [(e["rank"], e["name"], e["active"]) for e in sheet["eidolons"]] == [
        ("E1", "一魂", True), ("E2", "二魂", False)]
    # 模板机制注记降 note 次级字段；旁车无 ranks 段 → 官方 desc 空（回落现状）
    assert sheet["eidolons"][0]["note"] == "一魂描述文本"
    assert sheet["eidolons"][0]["desc"] == ""
    # 光锥：模板名 + build 叠影 + notes 描述
    lc = sheet["light_cone"]
    assert lc["name"] == "测试锥" and lc["superimposition"] == 2 and lc["level"] == 80
    assert lc["desc"] == ["测试锥效果描述：攻击力提高。"]
    # 遗器：套装名 + 各部位主/副词条
    rel = sheet["relics"]
    assert rel["sets"] == [{"set_id": "199", "name": "测试套", "count": 2}]
    assert sorted((p["slot"], p["main"]) for p in rel["pieces"]) == [("body", "atk_pct"), ("head", "hp")]
    head = next(p for p in rel["pieces"] if p["slot"] == "head")
    assert head["subs"] == {"spd": 1, "atk_pct": 2} and head["set_name"] == "测试套"
    # 数值 tab 取数：遗器 2pc atk_pct 进 effective（1000×1.1 + 光锥 50 + 遗器主词条不计 = 1150 族）
    eff = client.get("/api/inspect/9999").json()["effective"]
    assert eff["atk"] > 1050  # 白值 1000 + 光锥 50，且 2pc atk_pct 0.1 生效（>1050 即含 pct）


# ---------------------------------------------------------------------------
# v3 增量：表单编辑器（catalog 四清单 + form 组装）
# ---------------------------------------------------------------------------

import json  # noqa: E402

_FORM_BASE = {
    "team": [{"character": "8888", "level": 80, "eidolon": 2,
              "light_cone": "23001", "relic_set": "199"}],
    "enemies_mode": "library",
    "library_enemies": [{"enemy": "8001", "wave": 1}],
    "termination": {"mode": "wipe"},
    "policy_rules": [{"condition": "energy >= max_energy", "action": "ultimate", "priority": 90}],
}


def test_catalog_endpoint_and_graceful_degradation(fake_template_root, tmp_path, monkeypatch):
    """catalog 四清单字段齐（角色标注/遗器 cavern/敌人弱点）；数据文件缺失 → 优雅降级空表。"""
    monster = tmp_path / "monster.json"
    monster.write_text(json.dumps(
        {"8001": {"zh": "测试怪", "weak": ["Fire", "Thunder"], "rank": "Minion"}}), encoding="utf-8")
    monkeypatch.setattr(_battles, "MONSTER_JSON", monster)
    monkeypatch.setattr(_battles, "ENEMIES_JSON", tmp_path / "不存在.json")
    cat = TestClient(create_app()).get("/api/catalog").json()
    assert set(cat) == {"characters", "light_cones", "relic_sets", "enemies"}
    assert cat["characters"] == [{"id": "8888", "name": "表单员", "charge": None, "source": "generated"},
                                 {"id": "9999", "name": "测试员", "charge": None, "source": "generated"}]
    assert cat["light_cones"] == [{"id": "23001", "name": "测试锥", "rarity": 5}]
    assert cat["relic_sets"] == [
        {"id": "199", "name": "测试套", "kind": "cavern", "desc_2pc": "两件", "desc_4pc": "四件"},
        {"id": "399", "name": "测试位面", "kind": "planar", "desc_2pc": "位面两件", "desc_4pc": ""}]
    assert cat["enemies"] == [{"id": "8001", "name": "测试怪",
                               "weakness": ["fire", "thunder"], "rank": "Minion"}]
    # 优雅降级：模板根空 + 数据文件缺 → 四张空表（不 500）
    monkeypatch.setattr(_battles, "DEFAULT_TEMPLATE_ROOTS", (str(tmp_path / "空目录"),))
    monkeypatch.setattr(_battles, "MONSTER_JSON", tmp_path / "也没有.json")
    empty = TestClient(create_app()).get("/api/catalog").json()
    assert empty == {"characters": [], "light_cones": [], "relic_sets": [], "enemies": []}


def test_form_assemble_and_compile(fake_template_root):
    """form 组装：build/stage 可编译；cavern 遗器默认四件；wipe → fixed_av 999999；
    policy 无兜底规则自动补 true→basic。"""
    from hsr_nous.sim.compile import compile_encounter_yaml
    client = TestClient(create_app())
    r = client.post("/api/battles/assemble", json={"form": _FORM_BASE})
    assert r.status_code == 200, r.text
    compiled = compile_encounter_yaml(r.json()["build_yaml"], r.json()["stage_yaml"])
    assert [a.name for a in compiled.build_team] == ["表单员"]
    assert compiled.stage.termination_mode == "fixed_av" and compiled.stage.max_action_value == 999999  # 杀光即停 = 大 AV 预算
    build_doc = yaml.safe_load(r.json()["build_yaml"])
    member = build_doc["build"]["team"][0]
    assert member["eidolon"] == 2 and member["light_cone_template"] == "23001"
    relics = member["relics"]
    assert set(relics) == {"head", "hand", "body", "feet"}  # cavern 四件
    assert (relics["head"]["main"], relics["hand"]["main"],
            relics["body"]["main"], relics["feet"]["main"]) == ("hp", "atk", "crit_rate", "spd")
    rules = build_doc["build"]["policy"]["action_rules"]
    assert rules[0]["action"] == "ultimate"
    assert rules[-1] == {"condition": "true", "action": "basic", "priority": 0}  # 自动兜底


def test_form_assemble_custom_enemies_and_planar(fake_template_root):
    """自定义怪 inline（弱点过滤/波次分组/e1..eN 发号）+ planar 遗器两件（球位跟角色属性）。"""
    from hsr_nous.sim.compile import compile_encounter_yaml
    client = TestClient(create_app())
    form = {**_FORM_BASE,
            "team": [{"character": "8888", "level": 70, "eidolon": 0,
                      "light_cone": "", "relic_set": "399"}],
            "enemies_mode": "custom",
            "custom_enemies": [
                {"name": "甲", "hp": 800000, "spd": 120, "toughness": 30, "level": 70,
                 "wave": 1, "weakness": ["fire", "非法属性", "ice"]},
                {"name": "乙", "hp": 500000, "spd": 90, "toughness": 60, "level": 70,
                 "wave": 2, "weakness": []}],
            "termination": {"mode": "fixed_av", "max_action_value": 800}}
    r = client.post("/api/battles/assemble", json={"form": form})
    assert r.status_code == 200, r.text
    stage_doc = yaml.safe_load(r.json()["stage_yaml"])["stage"]
    e1 = stage_doc["enemies"][0]
    assert e1["actor_id"] == "e1" and e1["name"] == "甲" and e1["weakness"] == ["fire", "ice"]
    assert len(stage_doc["waves"]) == 1 and stage_doc["waves"][0]["wave_index"] == 2
    assert stage_doc["waves"][0]["enemies"][0]["name"] == "乙"
    assert stage_doc["termination"]["max_action_value"] == 800
    relics = yaml.safe_load(r.json()["build_yaml"])["build"]["team"][0]["relics"]
    assert set(relics) == {"sphere", "rope"}  # planar 两件
    assert relics["sphere"]["main"] == "fire_dmg" and relics["rope"]["main"] == "atk_pct"
    compiled = compile_encounter_yaml(r.json()["build_yaml"], r.json()["stage_yaml"])
    assert [e.name for e in compiled.stage.enemies] == ["甲"]


def test_form_assemble_validation_errors(fake_template_root):
    """组装校验：空队 / 库怪复选 / 坏条件 / 无模板角色 / 自定义怪缺名 → 全 400 带中文原因。"""
    client = TestClient(create_app())
    bad = [
        {**_FORM_BASE, "team": []},                                                    # 空队
        {**_FORM_BASE, "library_enemies": [{"enemy": "8001"}, {"enemy": "8001"}]},     # 复选撞 id
        {**_FORM_BASE, "policy_rules": [{"condition": "energy >>> 1", "action": "basic"}]},  # 坏表达式
        {**_FORM_BASE, "team": [{"character": "7777"}]},                               # 无模板角色
        {**_FORM_BASE, "enemies_mode": "custom", "custom_enemies": [{"name": ""}]},    # 缺名
    ]
    for form in bad:
        r = client.post("/api/battles/assemble", json={"form": form})
        assert r.status_code == 400, (form, r.text)


def test_save_form_shape_roundtrip(battles_dir, fake_template_root):
    """save 的 form 形态：服务端组装后入库（preview 可解析），按 config 名直接开局。"""
    client = TestClient(create_app())
    r = client.post("/api/battles/save",
                    json={"name": "表单局", "description": "表单存库", "form": _FORM_BASE})
    assert r.json() == {"ok": True}, r.text
    hit = next(e for e in client.get("/api/battles").json() if e["name"] == "表单局")
    assert hit["team_preview"] == ["表单员"] and hit["stage_preview"] == ["测试怪"]
    assert client.post("/api/load", json={"config": "表单局"}).status_code == 200
    s = client.get("/api/state").json()
    assert s["loaded"] and set(s["actors"]) == {"8888", "8001"}


# ---------------------------------------------------------------------------
# 呈现层旁车（descriptions/）：官方 desc 服务端格式化 + 能量槽显示名下发
# ---------------------------------------------------------------------------

def test_format_desc_server_side():
    """_format_desc 纯函数：#N[i] 整数 / #N[fN] 浮点（N 位小数）按末档（模板等级）代入；
    紧跟 % ×100（0.5→50 / 0.23→23.0）；计数原值（2→2）；索引越界原样保留；空 desc → None。"""
    from hsr_nous.sim.web import _format_desc
    params = [[0.5], [0.6], [0.7], [0.8], [0.9], [1.0], [1.1], [1.2], [1.3], [1.4]]
    assert _format_desc("造成等同于白厄#1[i]%攻击力的伤害", params) == "造成等同于白厄140%攻击力的伤害"
    assert _format_desc("持续#2[i]回合", [[0.5, 2], [1.4, 3]]) == "持续3回合"   # 末档；计数不乘
    assert _format_desc("#1[f1]档", [[1.4]]) == "1.4档"   # [fN] 浮点档（丹恒大招 #4[f1]% 病例）
    assert _format_desc("护盾#1[f1]%攻击力", [[0.23]]) == "护盾23.0%攻击力"
    assert _format_desc("#9[i]越界保留", [[1.4]]) == "#9[i]越界保留"
    assert _format_desc("无占位符", []) == "无占位符"
    assert _format_desc(None, [[1]]) is None and _format_desc("", [[1]]) is None


_SIDECAR_9999 = {
    "actor_id": "9999",
    "energy_name": "火种",
    "actions": {
        "fake_basic": {
            "name": "测试普攻",
            "desc": "造成#1[i]%伤害，持续#2[i]回合",
            "params": [[0.5, 2], [1.4, 3]],
        },
    },
}


def _write_sidecar(root, actor_id: str, content: str) -> None:
    d = root / "descriptions"
    d.mkdir(exist_ok=True)
    (d / f"{actor_id}.json").write_text(content, encoding="utf-8")


def test_unit_skills_sidecar_desc_and_energy_name(fake_template_root):
    """旁车命中：desc 服务端格式化下发（优先于模板原文 desc）；state 单位卡带 energy_name。"""
    _write_sidecar(fake_template_root, "9999", json.dumps(_SIDECAR_9999, ensure_ascii=False))
    client = TestClient(create_app(_FAKE_BUILD, _LOAD_BODY["stage_yaml"], mode="expected"))
    sk = client.get("/api/unit_skills/9999").json()[0]
    assert sk["desc"] == "造成140%伤害，持续3回合"
    s = client.get("/api/state").json()
    assert s["actors"]["9999"]["energy_name"] == "火种"
    assert s["actors"]["enemy1"]["energy_name"] is None  # 敌人无旁车 → None（前端回落"能量"）


def test_sidecar_missing_and_corrupt_degrades(fake_template_root):
    """旁车降级：坏文件 → desc 回落模板原文、energy_name None；inline 局无旁车 → 全 None，不炸。"""
    _write_sidecar(fake_template_root, "9999", "{坏 json")
    client = TestClient(create_app(_FAKE_BUILD, _LOAD_BODY["stage_yaml"], mode="expected"))
    sk = client.get("/api/unit_skills/9999").json()[0]
    assert sk["desc"] == "模板原文描述：一段测试用普攻。"  # 旁车坏 → 模板原文回落
    s = client.get("/api/state").json()
    assert s["actors"]["9999"]["energy_name"] is None
    # inline 局（真模板根下也无 hero 旁车）：desc/energy_name 全 None
    client2 = TestClient(create_app(
        _LOAD_BODY["build_yaml"], _LOAD_BODY["stage_yaml"], mode="expected"))
    assert client2.get("/api/unit_skills/hero").json()[0]["desc"] is None
    assert client2.get("/api/state").json()["actors"]["hero"]["energy_name"] is None


# ---------------------------------------------------------------------------
# 附加模板根（create_app extra_template_roots ← CLI web --templates）
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

_FIXTURES_TEMPLATES = str(Path(__file__).parent / "fixtures" / "templates")

_PHAINON_BUILD = yaml.safe_dump({"build": {
    "team": [{"character_template": "1408", "level": 80}],
    "policy": {"name": "p",
               "action_rules": [{"condition": "true", "action": "basic", "priority": 0}],
               "target_rules": [], "parameters": {}}}}, allow_unicode=True)

_PHAINON_STAGE = yaml.safe_dump({"stage": {
    "stage_id": "t",
    "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 60}],
    "termination": {"mode": "fixed_av", "max_action_value": 300}}}, allow_unicode=True)


def _phainon_first_choices(client: TestClient) -> set:
    """推进到白厄首个行动决策点（敌人 spd100 先空过一步），返回 choices 的 action_id 集。

    choices 里另含 follow_up 触发件（pyre_counter 等恒在 legal 集，引擎既有口径）——
    断言一律用子集/不相交，不点名它们。
    """
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    assert client.post("/api/step").status_code == 200  # e1 空过（无行动不弹决策点）
    t, _box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert p["actor_id"] == "1408"
    ids = {c["action_id"] for c in p["choices"]}
    # 放行引擎线程：选 [0]（single 候选 1 个直通无 target 阶段）；若行动后窗口弹终结技决策
    # （对照组骨架 max_energy=12、普攻回能 20 → 行动后能量满必弹）则 skip 放行
    assert client.post("/api/choose", json={"index": 0}).status_code == 200
    for _ in range(200):
        s = client.get("/api/state").json()
        p2 = s.get("pending")
        if p2 and p2["phase"] == "ultimate":
            assert client.post("/api/choose", json={"actor_id": "skip"}).status_code == 200
            break
        if not t.is_alive():
            break
        time.sleep(0.05)
    t.join(timeout=10)
    assert not t.is_alive()
    return ids


def test_extra_template_roots_gate_state_actions(monkeypatch):
    """--templates 端到端：1408 编译自 fixtures 锚模板——常态 choices 只有普通形态行动
    （140808/140809/140811 随形态机解锁，常态不出现；火种 3<12 终结技也不在）。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])  # 隔离全局（create_app 会写入）
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    ids = _phainon_first_choices(client)
    assert {"140801", "140802"} <= ids
    assert ids.isdisjoint({"140803", "140808", "140809", "140811"})


@pytest.mark.skipif(
    not any(Path("data/sim_templates/characters").glob("1408_*.yaml")),
    reason="本地无 data/sim_templates 角色模板（gitignored），缺省根对照组跳过")
def test_default_roots_skeleton_ungated_control(monkeypatch):
    """对照组：无附加根 → 1408 编译自 data/ 生成骨架（无形态机），强化行动常态即可选。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app())
    assert "140808" in _phainon_first_choices(client)


# ---------------------------------------------------------------------------
# 模板来源 provenance（state 单位卡徽章 + C 面板路径行）
# ---------------------------------------------------------------------------

def test_template_source_in_state_and_sheet(monkeypatch):
    """provenance 下发：/api/state 单位卡 template_source（anchor/None）；/api/unit_sheet 带完整路径。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    s = client.get("/api/state").json()
    assert s["actors"]["1408"]["template_source"] == "anchor"   # fixtures 人工锚模板
    assert s["actors"]["e1"]["template_source"] is None         # inline 假人无模板 → 不标
    sh = client.get("/api/unit_sheet/1408").json()
    assert sh["template"]["source"] == "anchor"
    assert sh["template"]["path"].endswith("fixtures/templates/characters/1408_phainon.yaml")


@pytest.mark.skipif(
    not (any(Path("data/sim_templates/characters").glob("1408_*.yaml"))
         and any(Path("data/sim_templates/enemies").glob("1002011_*.yaml"))),
    reason="本地无 data/sim_templates 角色/敌人模板（gitignored），generated 对照组跳过")
def test_template_source_generated_control(monkeypatch):
    """对照（需 data/）：缺省根 → 角色 generated；enemy_template 库怪走同一解析链 → generated。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app())
    stage = yaml.safe_dump({"stage": {
        "stage_id": "t",
        "enemies": [{"enemy_template": "1002011", "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 150}}}, allow_unicode=True)
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": stage, "mode": "expected"})
    assert r.status_code == 200, r.text
    s = client.get("/api/state").json()
    assert s["actors"]["1408"]["template_source"] == "generated"
    assert s["actors"]["1002011"]["template_source"] == "generated"   # 敌方模板同样标注


# ---------------------------------------------------------------------------
# F2/F3 modifier 来源（payload 字段 + 旁车来源索引 + E2E 可展开）
# ---------------------------------------------------------------------------

def test_modifier_source_fields_and_sidecar_map(monkeypatch):
    """F2 payload：modifier 条目带 source_kind/source_ref/解析件（hook 件=可展示名记账）；
    F3 取数：unit_sheet.sidecar 全量索引（天赋/行迹 desc 已服务端格式化）。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    det = client.get("/api/inspect/1408").json()["modifier_detail"]
    assert det, "开局 hook 应已挂行迹件"
    for m in det:
        assert set(m) >= {"source_kind", "source_ref", "source_action_name",
                          "source_action_type", "expandable"}
    hook = next(m for m in det if m["modifier_id"] == "TRACE_1408103")
    assert hook["source_kind"] == "hook" and hook["source_ref"] == "照见英雄本色"
    assert hook["source_name"] == "白厄"
    # X1：显示名按本角色旁车 name 精确匹配 → 命中行迹节点（行迹 > 天赋 > 技能 优先级）
    assert hook["expandable"] is True and hook["source_ref_id"] == "1408103"
    sc = client.get("/api/unit_sheet/1408").json()["sidecar"]
    assert sc["140804"]["kind"] == "天赋" and "火种" in sc["140804"]["desc"]
    assert sc["1408103"]["kind"] == "行迹" and "50%" in sc["1408103"]["desc"]  # #1[i]% → 50%


def test_eidolons_official_desc_and_note(monkeypatch):
    """星魂段（模板段 ∪ 旁车 ranks）：E1-E6 全带官方 desc；模板机制注记降 note 次级字段；
    对照（缺省根骨架无 eidolons 段）：旁车 ranks 独立撑起六魂行。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    eds = client.get("/api/unit_sheet/1408").json()["eidolons"]
    assert [e["rank"] for e in eds] == ["E1", "E2", "E3", "E4", "E5", "E6"]
    e1, e2 = eds[0], eds[1]
    assert "额外回合的基础速度继承比例" in e1["desc"]   # 官方 desc（ranks 140801）
    assert e1["note"], "fixture E1 机制注记应保留在 note"
    assert "抗性穿透提高20%" in e2["desc"]              # E2 官方 desc（ranks 140802）
    assert e2["note"] == ""                             # fixture E2 无注记 → note 空
    assert all(not e["active"] for e in eds)            # build 未配星魂 → 全未激活


@pytest.mark.skipif(
    not any(Path("data/sim_templates/characters").glob("1408_*.yaml")),
    reason="本地无 data/sim_templates 角色模板（gitignored），骨架对照跳过")
def test_eidolons_from_sidecar_without_template_section(monkeypatch):
    """骨架对照：data/ 模板无 eidolons 段 → 旁车 ranks 独立产出 E1-E6（官方 desc 补空白）。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app())
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    eds = client.get("/api/unit_sheet/1408").json()["eidolons"]
    assert [e["rank"] for e in eds] == ["E1", "E2", "E3", "E4", "E5", "E6"]
    assert "抗性穿透提高20%" in eds[1]["desc"]
    assert all(e["note"] == "" for e in eds)


# ---------------------------------------------------------------------------
# 特殊充能槽（charge：max_energy=0 + ult_cost_resource 驱动的通用机制）
# ---------------------------------------------------------------------------

def _charge_template_root(root: Path, ult_cost_amount: float = 8) -> None:
    """tmp 模板根落一个特殊充能测试角色（zeal 资源 + ult_cost_resource 大招）。"""
    (root / "characters").mkdir(parents=True)
    doc = {
        "actor_id": "9001", "name": "充能员", "level": 80,
        "base_stats": {"atk": 1000, "spd": 120, "hp": 3000, "max_energy": 0},
        "custom_resources": {"zeal": {"max": 20}},
        "actions": [
            {"action_id": "z1", "name": "普攻", "action_type": "basic",
             "target_type": "single", "damage_type": "fire",
             "scaling": [{"atk": 1.0}], "resource_gain": {"zeal": 3}},
            {"action_id": "z_ult", "name": "大招", "action_type": "ultimate",
             "target_type": "single", "damage_type": "fire",
             "scaling": [{"atk": 2.0}],
             "ult_cost_resource": "zeal", "ult_cost_amount": ult_cost_amount},
        ],
    }
    (root / "characters" / "9001_充能员.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


def _load_charge_client(root: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    monkeypatch.setattr(_battles, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    client = TestClient(create_app())
    build = yaml.safe_dump({"build": {
        "team": [{"character_template": "9001", "level": 80}],
        "policy": {"name": "p", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}],
            "target_rules": [], "parameters": {}}}}, allow_unicode=True)
    stage = yaml.safe_dump({"stage": {
        "stage_id": "t",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 60}],
        "termination": {"mode": "fixed_av", "max_action_value": 300}}}, allow_unicode=True)
    r = client.post("/api/load", json={"build_yaml": build, "stage_yaml": stage, "mode": "expected"})
    assert r.status_code == 200, r.text
    return client


def test_charge_payload_generic_mechanism(tmp_path, monkeypatch):
    """charge 下发（通用机制，ult_cost_resource 驱动）：激活线=ult_cost_amount；
    值随资源结算；无旁车 label 回落资源 id 原文。"""
    root = tmp_path / "templates"
    _charge_template_root(root, ult_cost_amount=8)
    client = _load_charge_client(root, monkeypatch)
    ch = client.get("/api/state").json()["actors"]["9001"]["charge"]
    assert ch == {"resource_id": "zeal", "value": 0.0, "cap": 8.0, "label": "zeal"}
    # 普攻（+3 zeal，spd120 先手）后 value 跟上；常规能量字段不受影响
    t, _box = _step_thread(client)
    p = _wait_pending(client, "action")
    assert p["actor_id"] == "9001"
    assert client.post("/api/choose", json={"index": 0}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive()
    a = client.get("/api/state").json()["actors"]["9001"]
    assert a["charge"]["value"] == 3.0 and a["max_energy"] == 0.0


def test_charge_cap_fallback_to_resource_max(tmp_path, monkeypatch):
    """cap 回落：ult_cost_amount=0 → custom_resources[res].max。"""
    root = tmp_path / "templates"
    _charge_template_root(root, ult_cost_amount=0)
    client = _load_charge_client(root, monkeypatch)
    ch = client.get("/api/state").json()["actors"]["9001"]["charge"]
    assert ch["cap"] == 20.0


def test_charge_phainon_and_regular_untouched(monkeypatch):
    """fixtures 白厄：charge={fire_seed, 3, 12, 火种}（label=旁车 energy_name）；
    敌木桩与 inline 常规能量角色 → charge None、原能量条字段不变。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    s = client.get("/api/state").json()
    assert s["actors"]["1408"]["charge"] == {
        "resource_id": "fire_seed", "value": 3.0, "cap": 12.0, "label": "火种"}
    assert s["actors"]["e1"]["charge"] is None
    client2 = TestClient(create_app())
    _load(client2)  # inline hero（max_energy=110，无 ult_cost_resource）
    hero = client2.get("/api/state").json()["actors"]["hero"]
    assert hero["charge"] is None and hero["max_energy"] == 110.0


def test_action_source_expandable_end_to_end(monkeypatch):
    """E2E：自动局白厄攒火种开大 → 敌方 ZONE_PHY_WEAK 条目 kind=action、ref=140803、
    解析名/类型齐全、expandable=True（ref 命中施加者旁车）。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    build = yaml.safe_dump({"build": {
        "team": [{"character_template": "1408", "level": 80},
                 # 产点工具人：fixtures 普攻未声明 skill_point_gain（DSL 需显式），
                 # 白厄独自放战技点会耗尽永远攒不满火种——inline 普攻 +2 点保战技循环
                 {"actor_id": "sp_pump", "name": "产点员", "inline": True,
                  "base_stats": {"atk": 1000, "spd": 120, "hp": 3000},
                  "actions": [{"action_id": "pump_basic", "name": "普攻",
                               "action_type": "basic", "target_type": "single",
                               "damage_type": "physical", "scaling": [{"atk": 1.0}],
                               "skill_point_gain": 2}]}],
        "policy": {"name": "p", "action_rules": [   # 常态攒战技充火种（不带 energy 规则——
            {"condition": "not in_state", "action": "skill", "priority": 50},
            # 1408 max_energy=0 时 energy>=max_energy 恒真，会抢 90 优先级回落 basic 永远攒不出火种；
            # 工具人无战技行动，自然回落 basic 产点）
            {"condition": "true", "action": "basic", "priority": 0}],
            "target_rules": [], "parameters": {}}}}, allow_unicode=True)
    stage = yaml.safe_dump({"stage": {
        "stage_id": "t",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 60}],
        "termination": {"mode": "fixed_av", "max_action_value": 1500}}}, allow_unicode=True)
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": build, "stage_yaml": stage, "mode": "expected"})
    assert r.status_code == 200, r.text
    assert client.post("/api/mode", json={"mode": "auto"}).status_code == 200
    r = client.post("/api/continue", json={"max_steps": 400})
    assert r.status_code == 200, r.text
    det = client.get("/api/inspect/e1").json()["modifier_detail"]
    zone = next((m for m in det if m["modifier_id"] == "ZONE_PHY_WEAK"), None)
    assert zone is not None, f"变身应已植入境界件（AV 预算内未开大？）：{det}"
    assert zone["source_kind"] == "action" and zone["source_ref"] == "140803"
    assert zone["source_action_name"] == "永劫燔世，其将背负"
    assert zone["source_action_type"] == "ultimate"
    assert zone["source_name"] == "白厄"
    assert zone["expandable"] is True
    assert zone["source_ref_id"] == "140803"
    # X2 端点：场上激活 modifier 优先于旁车（① 命中）
    xr = client.get("/api/xref/e1/时墟铁墓").json()
    assert xr["found"] and xr["via"] == "active_modifier"
    assert xr["modifier"]["modifier_id"] == "ZONE_PHY_WEAK"


# ---------------------------------------------------------------------------
# X1/X2 交叉引用（name 匹配三态 + 端点解析顺序）
# ---------------------------------------------------------------------------

def test_xref_name_lookup_priority_and_ambiguity():
    """X1 name 匹配三态：kind 优先级（行迹 > 天赋 > 技能 > 星魂）；同层多命中=歧义 None；零命中 None。"""
    from hsr_nous.sim.web import WebSession
    sess = WebSession()
    sess._sidecars["x"] = {
        "actions": {
            "1001": {"name": "同名技", "desc": "", "params": [], "type_text": "战技"},
            "1002": {"name": "独有技", "desc": "", "params": [], "type_text": "天赋"},
        },
        "traces": {"1003": {"name": "同名技", "desc": "", "params": []}},
        "ranks": {"1004": {"rank": 1, "name": "同名技", "desc": "", "params": []}},
    }
    hit = sess._xref_sidecar_lookup("x", "同名技")
    assert hit["ref"] == "1003" and hit["kind"] == "行迹"          # 行迹 > 天赋 > 技能 > 星魂
    assert sess._xref_sidecar_lookup("x", "独有技")["ref"] == "1002"  # 天赋层单命中
    sess._sidecars["x"]["traces"]["1005"] = {"name": "同名技", "desc": "", "params": []}
    assert sess._xref_sidecar_lookup("x", "同名技") is None          # 行迹层双命中 = 歧义不收
    assert sess._xref_sidecar_lookup("x", "不存在") is None          # 零命中
    # 只查本角色旁车（SP 同名事故预防）：别单位同名不可见
    assert WebSession()._xref_sidecar_lookup("y", "同名技") is None


def test_xref_resolve_endpoint(monkeypatch):
    """X2 端点解析顺序：① 场上激活 modifier 优先于 ② 旁车 name 命中 优先于 ③ desc 首个含【】；
    全 miss → found=False。"""
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])
    client = TestClient(create_app(extra_template_roots=[_FIXTURES_TEMPLATES]))
    r = client.post("/api/load", json={"build_yaml": _PHAINON_BUILD,
                                       "stage_yaml": _PHAINON_STAGE, "mode": "expected"})
    assert r.status_code == 200, r.text
    # ① 激活 modifier 优先：照见英雄本色既是开局 modifier 又是行迹条目 → active_modifier 胜
    xr = client.get("/api/xref/1408/照见英雄本色").json()
    assert xr["found"] and xr["via"] == "active_modifier"
    assert xr["modifier"]["modifier_id"] == "TRACE_1408103"
    # ② 旁车 name 精确命中：此身为炬 → 天赋 140804
    xr = client.get("/api/xref/1408/此身为炬").json()
    assert xr["found"] and xr["via"] == "sidecar_name"
    assert xr["entry"]["ref"] == "140804" and xr["entry"]["kind"] == "天赋"
    # ③ desc 首个含【】：毁伤 → 140805（actions 段 id 升序首中）
    xr = client.get("/api/xref/1408/毁伤").json()
    assert xr["found"] and xr["via"] == "sidecar_desc"
    assert xr["entry"]["ref"] == "140805"
    # 全 miss → 不可点回落
    assert client.get("/api/xref/1408/不存在的机制").json() == {"found": False}
    # unit_sheet 带 xref_names（前端链接化预判集合：含条目名与 desc 内【】名）
    names = client.get("/api/unit_sheet/1408").json()["xref_names"]
    assert "此身为炬" in names and "毁伤" in names and "照见英雄本色" in names



# ---------------------------------------------------------------------------
# 交互四件套服务端骨架：bus 事件旁听流 + state 纯展示字段（wave/intent/resistance/events）
# ---------------------------------------------------------------------------

# 带一个行动的敌人模板（inline 敌人无 actions——_enemy_turn 直选 actions[0] 的意图取数
# 只有模板通道能给）；hp 拉满防被流弹打死，事件断言集中在脆壳 e2 上
_EV_ENEMY_TPL = {
    "enemy_id": "8002", "name": "意图怪", "level": 80,
    "base_stats": {"hp": 1e9, "atk": 100, "def": 100, "spd": 50,
                   "max_toughness": 30, "effect_res": 0},
    "weakness": ["physical"],
    "actions": [{
        "action_id": "e_atk", "name": "挥打", "action_type": "basic",
        "target_type": "single", "damage_type": "physical", "scaling": [{"atk": 0.5}],
    }],
}

_EV_BUILD = yaml.safe_dump({"build": {
    "team": [{
        "character_template": "inline", "actor_id": "hero", "name": "测试员", "level": 80,
        # max_energy 20 + 普攻回能 20 → 首动后必浮终结技窗口（ult 事件链路顺带覆盖）
        "base_stats": {"atk": 9000, "spd": 200, "hp": 3000, "max_energy": 20},
        "actions": [
            {"action_id": "h_basic", "name": "普攻", "action_type": "basic",
             "target_type": "single", "damage_type": "physical",
             "scaling": [{"atk": 1.0}], "energy_gain": 20, "toughness_dmg": 10},
            {"action_id": "h_ult", "name": "天降正义", "action_type": "ultimate",
             "target_type": "aoe", "damage_type": "physical",
             "scaling": [{"atk": 2.0}], "energy_cost": 20},
        ],
    }],
    "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}],
               "target_rules": [], "parameters": {}}}}, allow_unicode=True)

_EV_STAGE = yaml.safe_dump({"stage": {
    "stage_id": "ev_tap",
    "enemies": [
        {"enemy_template": "8002"},
        {"actor_id": "e2", "name": "脆壳", "level": 80, "hp": 100, "spd": 60,
         "weakness": ["physical"], "max_toughness": 30, "resistance": {"fire": 0.2}},
    ],
    "termination": {"mode": "fixed_av", "max_action_value": 500}}}, allow_unicode=True)


def test_battle_events_stream_and_display_fields(tmp_path, monkeypatch):
    """事件旁听：普攻 hit→脆壳 death→行动后终结技 ult（服务端反查补行动名）全链落箱；
    state 展示字段：wave / 敌人 intent（模板 actions[0] 名）/ 非零 resistance 下发；
    事件单游标——推进响应与 state 轮询谁先谁拿、不重复（排空后为 []）。"""
    root = tmp_path / "templates"
    f = root / "enemies" / "8002_意图怪.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(_EV_ENEMY_TPL, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(_battles, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    from hsr_nous.sim.compile import build_compiler, stage_compiler
    monkeypatch.setattr(build_compiler, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    monkeypatch.setattr(stage_compiler, "DEFAULT_TEMPLATE_ROOTS", (str(root),))

    client = TestClient(create_app())
    r = client.post("/api/load", json={"build_yaml": _EV_BUILD, "stage_yaml": _EV_STAGE,
                                       "mode": "expected", "seed": None})
    assert r.status_code == 200, r.text
    assert r.json()["events_reset"] is True      # 开局即声明 reset（前端清卡重建）

    collected: list = []

    def poll() -> dict:
        s = client.get("/api/state").json()
        collected.extend(s.get("events") or [])
        return s

    def wait_phase(phase: str) -> dict:
        for _ in range(200):
            p = poll().get("pending")
            if p and p["phase"] == phase:
                return p
            time.sleep(0.05)
        raise AssertionError(f"{phase} 阶段决策点未出现")

    # 纯展示字段：wave=1；8002 意图=模板 actions[0] 名；e2 抗性下发、inline 无行动 → intent=None
    s = poll()
    assert s["wave"] == 1
    assert s["actors"]["8002"]["intent"] == "挥打"
    assert s["actors"]["e2"]["intent"] is None and s["actors"]["hero"]["intent"] is None
    assert s["actors"]["e2"]["resistance"] == {"fire": 0.2}
    # L1/L5 buff 图标行三件套（name/stacks/type；无 modifier 时为空数组不下发 None）
    assert s["actors"]["hero"]["modifier_icons"] == []

    # hero 首动（spd200 先行动）：普攻 → 选脆壳 e2（一击致死）→ 行动后终结技窗口放 ult
    t, box = _step_thread(client)
    wait_phase("action")
    assert client.post("/api/choose", json={"index": 0}).status_code == 200
    wait_phase("target")
    assert client.post("/api/choose", json={"actor_id": "e2"}).status_code == 200
    p = wait_phase("ultimate")
    assert [r["actor_id"] for r in p["ready"]] == ["hero"]
    assert client.post("/api/choose", json={"actor_id": "hero"}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive() and box["status"] == 200, box
    collected.extend(box["body"]["events"])

    kinds = [e["kind"] for e in collected]
    assert "hit" in kinds and "death" in kinds and "ult" in kinds
    hit = next(e for e in collected if e["kind"] == "hit" and e["target"] == "e2")
    assert hit["source"] == "hero" and hit["amount"] > 0 and hit["action_type"] == "basic"
    assert next(e for e in collected if e["kind"] == "death")["target"] == "e2"
    ult = next(e for e in collected if e["kind"] == "ult")
    assert ult["source"] == "hero" and ult["name"] == "天降正义"   # 行动名服务端反查补
    # 单游标：响应与轮询排完后，再拿为空（不重复投递）
    assert poll()["events"] == []

    # 回退重灌：reset_events 清箱后重放段事件自动回填（响应一次排清，不得二次排空袭空）
    def drive_one_step() -> None:   # 推一步到底（沿途出现的决策点一律取缺省放行）
        t2, b2 = _step_thread(client)
        while t2.is_alive():
            p = poll().get("pending")
            if p is None:
                time.sleep(0.05)
                continue
            if p["phase"] == "action":
                client.post("/api/choose", json={"index": 0})
            elif p["phase"] == "target":
                client.post("/api/choose", json={"actor_id": p["default"]})
            else:
                client.post("/api/choose", json={"actor_id": "skip"})
        t2.join(timeout=10)
        assert b2["status"] == 200, b2
        collected.extend(b2["body"]["events"])

    drive_one_step()
    drive_one_step()
    r = client.post("/api/back", json={"n": 1})
    assert r.status_code == 200 and r.json()["events_reset"] is True
    assert any(e["kind"] == "hit" for e in r.json()["events"])  # hero 首动普攻在重放段重灌



# ---------------------------------------------------------------------------
# owner 终审四 bug（B1 编队序 / B3 护盾·非数值效果显示 / B4 一键重开）服务端覆盖
# （B2 倒计时 ▶ 是纯前端归属逻辑——tests/test_web_ui_logic.py 的 node 闸直测）
# ---------------------------------------------------------------------------

# B1 fixture：两名纯数字 actor_id 成员按 1408 → 1313 编队（数值序与编队序刻意相反）
_NUM_ID_BUILD = yaml.safe_dump({
    "build": {
        "team": [
            {**HERO_YAML["build"]["team"][0], "actor_id": "1408", "name": "白厄"},
            {**HERO_YAML["build"]["team"][0], "actor_id": "1313", "name": "星期日"},
        ],
        "policy": HERO_YAML["build"]["policy"],
    }
}, allow_unicode=True)


def test_ally_order_payload_formation():
    """B1：/api/state 显式下发 ally_order（= build 编队序，与终结技 key_hint 同源）。

    actor_id 是纯数字字符串时 JS 会把对象键按数值升序重排（1313 先于 1408）——
    编队序必须由显式清单承载，不能信 actors 键序。
    """
    client = TestClient(create_app())
    r = client.post("/api/load", json={**_LOAD_BODY, "build_yaml": _NUM_ID_BUILD})
    assert r.status_code == 200, r.text
    s = client.get("/api/state").json()
    assert s["ally_order"] == ["1408", "1313"]        # 编队序，非数值升序 ["1313", "1408"]
    # 单 hero fixture 同口径；未开局无 ally_order（loaded=false 裸状态）
    client2 = TestClient(create_app())
    assert "ally_order" not in client2.get("/api/state").json()
    _load(client2)
    assert client2.get("/api/state").json()["ally_order"] == ["hero"]


def test_enemy_order_payload_placement():
    """/api/state 显式下发 enemy_order（= stage 布场序，引擎 _enemies_alive / blast 邻接同源）。

    库怪/深渊怪 actor_id 是纯数字模板 id，JS 整数键按数值升序重排——敌卡排列/瞄准候选/
    扩散高亮都不能信 actors 键序（实锤：列出序 1002030/1002011/1002020 被排成数值序后
    扩散高亮错邻）。本 fixture 敌列速度与列出序故意不一致（enemy1 最慢列最前），
    enemy_order 必须是列出序而非速度序/其他推导序。
    """
    client = TestClient(create_app())
    _load(client)
    s = client.get("/api/state").json()
    assert s["enemy_order"] == ["enemy1", "enemy2", "enemy3"]
    client2 = TestClient(create_app())
    assert "enemy_order" not in client2.get("/api/state").json()


# B3 fixture：战技给自身挂盾（scaling/flat 声明块——公式槽与 rulebook shield 式对齐）
_SHIELD_SPEC = {"scaling": {"def": 0.48}, "flat": 640}
HERO_SHIELD_YAML = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "存护",
            "level": 80,
            "base_stats": {"atk": 2000, "spd": 200, "hp": 3000, "def": 800},   # spd200 必先动
            "actions": [
                {
                    "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                    "target_type": "single", "damage_type": "physical",
                    "scaling": [{"atk": 0.5}],
                },
                {
                    "action_id": "hero_shield", "name": "渊渟岳峙，地载八荒",
                    "action_type": "skill", "target_type": "self",
                    "scaling": [], "skill_point_cost": 1,
                    "apply_modifiers": [{
                        "modifier_id": "HERO_SHIELD",
                        "name": "渊渟岳峙，地载八荒",
                        "modifier_type": "buff",
                        "duration": 3,
                        "dispellable": False,
                        "shield": _SHIELD_SPEC,
                    }],
                },
            ],
        }],
        "policy": {
            "name": "default",
            "action_rules": [
                {"condition": "skill_points > 0", "action": "skill", "priority": 50},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        },
    }
}

_SHIELD_LOAD_BODY = {
    "build_yaml": yaml.safe_dump(HERO_SHIELD_YAML, allow_unicode=True),
    "stage_yaml": _LOAD_BODY["stage_yaml"],
    "mode": "expected",
    "seed": None,
}


def test_shield_modifier_detail_payload():
    """B3：shield 类 modifier 的状态明细带盾值行取数（公式原文 + 当前盾值）。"""
    from hsr_nous.sim.web import _shield_formula_text
    # 公式原文口径：amount 表达式族直出原文；scaling/flat 族出声明块紧凑 JSON
    assert _shield_formula_text({"amount": "$self.atk * 0.2 + 400"}) == "$self.atk * 0.2 + 400"
    assert _shield_formula_text(None) == "" and _shield_formula_text({}) == ""

    client = TestClient(create_app())
    assert client.post("/api/load", json=_SHIELD_LOAD_BODY).status_code == 200
    t, box = _step_thread(client)
    p = _wait_pending(client, "action")
    idx = next(c["index"] for c in p["choices"] if c["name"] == "渊渟岳峙，地载八荒")
    assert client.post("/api/choose", json={"index": idx}).status_code == 200
    t.join(timeout=10)
    assert not t.is_alive() and box["status"] == 200, box  # self 直通，无目标阶段

    d = client.get("/api/inspect/hero").json()
    row = next(m for m in d["modifier_detail"] if m["modifier_id"] == "HERO_SHIELD")
    assert "shield" in row, "shield 类 modifier 明细缺盾值行"
    assert "0.48" in row["shield"]["formula"] and "640" in row["shield"]["formula"]
    # 当前盾值与引擎护盾实例同口径（snapshot.shields 交叉核对；0.48×800 + 640 = 1024）
    inst = next(s for s in d["shields"] if s["modifier_id"] == "HERO_SHIELD")
    assert row["shield"]["remaining"] == inst["remaining"] == 1024.0


def test_restart_same_config():
    """B4：/api/restart 同配置一键重开——当局 build/stage/mode/seed 原样重载，不进编辑器。"""
    client = TestClient(create_app())
    assert client.post("/api/restart").status_code == 400          # 未开局不可重开
    assert client.post("/api/load", json=_LOAD_BODY).status_code == 200
    t, _box = _step_thread(client)                                  # 推 1 动（两阶段走完）
    _wait_pending(client, "action")
    _choose_action_and_target(client, 0, "enemy1")
    t.join(timeout=10)
    assert client.get("/api/state").json()["turn_count"] == 1

    r = client.post("/api/restart")
    assert r.status_code == 200 and r.json()["logs_reset"] is True  # 与 /api/load 同帧语义
    s = client.get("/api/state").json()
    assert s["loaded"] and not s["done"] and s["turn_count"] == 0
    assert s["mode"] == "expected" and s["seed"] is None and s["manual"]  # 配置原样保留
    assert s["pending"] is None and s["ally_order"] == ["hero"]
    # 重开后可正常推进（决策点照常出现）
    t2, _b2 = _step_thread(client)
    assert _wait_pending(client, "action")["actor_id"] == "hero"
    client.post("/api/choose", json={"index": 0})
    p = _wait_pending(client, "target")
    client.post("/api/choose", json={"actor_id": p["default"]})
    t2.join(timeout=10)

    # mode/seed 保留：roll + seed=7 装局 → 重开后口径不变
    client2 = TestClient(create_app())
    assert client2.post("/api/load", json={**_LOAD_BODY, "mode": "roll", "seed": 7}).status_code == 200
    assert client2.post("/api/restart").status_code == 200
    s2 = client2.get("/api/state").json()
    assert s2["mode"] == "roll" and s2["seed"] == 7 and s2["turn_count"] == 0


def test_load_and_restart_during_pending():
    """回归（web 审计）：决策点挂起期间 /api/load 与 /api/restart 必须能换局——曾是死锁：
    step 引擎线程持锁等 choose → 换局端点非阻塞抢锁必 409（load 里的 _release_pending
    永远够不到）；前端 busy 闸再把请求静默吞掉（0 请求 0 提示），只能手动 choose 解套。
    现口径：换局端点先排干旧局（交还编译策略 + 放行挂起点）再等锁收尾。
    """
    client = TestClient(create_app())
    _load(client)
    t, box = _step_thread(client)
    _wait_pending(client, "action")
    # 决策点挂起中：restart 不再 409，且挂起的 step 被放行收尾（默认缺省打完这动）
    r = client.post("/api/restart")
    assert r.status_code == 200, r.text
    t.join(timeout=15)
    assert not t.is_alive(), "restart 排干后旧 step 应收尾（不再永久挂起）"
    assert box["status"] == 200, box
    s = client.get("/api/state").json()
    assert s["loaded"] and s["turn_count"] == 0 and s["pending"] is None
    # 重开后再推进到决策点，load 换局同样放行
    t2, box2 = _step_thread(client)
    _wait_pending(client, "action")
    r2 = client.post("/api/load", json=_LOAD_BODY)
    assert r2.status_code == 200, r2.text
    t2.join(timeout=15)
    assert not t2.is_alive() and box2["status"] == 200, box2
    s2 = client.get("/api/state").json()
    assert s2["loaded"] and s2["turn_count"] == 0 and s2["pending"] is None
    # 换局后决策点照常出现（新局健康）
    t3, _b3 = _step_thread(client)
    assert _wait_pending(client, "action")["actor_id"] == "hero"
    client.post("/api/choose", json={"index": 0})
    p = _wait_pending(client, "target")
    client.post("/api/choose", json={"actor_id": p["default"]})
    t3.join(timeout=10)
