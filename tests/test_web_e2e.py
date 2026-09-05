"""E2E 冒烟：Playwright 驱动真实 Chromium 过 sim web 关键流程（DOM 类 bug 的唯一自动闸）.

覆盖（今天连环炸过的全部故障类）：
- 开局渲染（按钮行/行动条/战技点数字）
- 瞄准态（locked 高亮/候选 aimable/幽灵条落点）
- 白厄变身（放逐置灰+徽章/倒计时条目/形态三键 QWE/毁伤资源行）
- 连续模式（推进过敌方回合、自然停在决策点）

运行机制：独立端口（8139）起真实服务器 + Playwright 无头 Chromium（项目 B4 既有依赖，
Chromium 在 ~/Library/Caches/ms-playwright）；playwright/Chromium 不可用 → 整文件 skip
（同 node 闸惯例，CI 无此依赖不红）。
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
import urllib.request

import pytest

PORT = 8139
BASE = f"http://localhost:{PORT}"

_PAGE = None   # Playwright page（module fixture 注入；_js 的传输层）


def _js(code: str):
    """页面 JS 求值（Playwright page.evaluate；返回 JS 值直出，无信封）。"""
    v = _PAGE.evaluate(code)
    return json.loads(v) if isinstance(v, str) else v


def _api(path: str, body: dict | None = None, timeout: int = 25):
    if body is None:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return json.load(r)
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _state() -> dict:
    return _api("/api/state")


def _step_thread() -> tuple:
    box: dict = {}

    def go() -> None:
        try:
            box["r"] = _api("/api/step", {})
        except Exception as e:  # noqa: BLE001
            box["err"] = repr(e)

    t = threading.Thread(target=go, daemon=True)
    t.start()
    return t, box


def _wait_pending(phase: str, actor: str | None = None, timeout: float = 15.0) -> dict:
    """等指定阶段 pending（可选限定行动方）。"""
    for _ in range(int(timeout / 0.05)):
        p = _state().get("pending")
        if p and p["phase"] == phase and (actor is None or p.get("actor_id") == actor):
            return p
        time.sleep(0.05)
    raise AssertionError(f"pending 未出现：phase={phase} actor={actor}")


def _wait_dom(js_pred: str, desc: str, timeout: float = 8.0) -> None:
    """等页面 DOM 反映服务器状态（页面 600ms 轮询——服务器 pending ≠ 页面已渲染）。"""
    for _ in range(int(timeout / 0.1)):
        if _js(f"(() => !!({js_pred}))()"):
            return
        time.sleep(0.1)
    raise AssertionError(f"DOM 等待超时：{desc}")


def _choose(choice: dict) -> None:
    if "index" in choice:
        _api("/api/choose", {"index": choice["index"]})
    elif "actor_id" in choice:
        _api("/api/choose", {"actor_id": choice["actor_id"]})
    elif "ult_now" in choice:
        _api("/api/choose", {"ult_now": choice["ult_now"]})


def _answer(p: dict, sp: int) -> None:
    """回答一个 pending：窗口 skip、目标按 ally_order 区分敌我（**不能按 id 前缀猜**——
    1313 是'13'开头，曾把星期日误判成敌人，全队增益喂给他、他再拉自己形成死循环）、
    行动按 SP 经济选（白厄有点就战技攒火种；队友 SP≥2 才放技能留储备）。"""
    if p["phase"] == "ultimate":
        _choose({"actor_id": "skip"})
        return
    if p["phase"] == "target":
        ids = [c["actor_id"] for c in p["candidates"]]
        allies = set(_state().get("ally_order") or [])
        enemies = [i for i in ids if i not in allies]
        _choose({"actor_id": enemies[0] if enemies else ("1408" if "1408" in ids else ids[0])})
        return
    want_skill = sp > 0 if p["actor_id"] == "1408" else sp >= 2
    c = next((x for x in p["choices"] if x["action_type"] == ("skill" if want_skill else "basic")),
           p["choices"][0])
    _choose({"index": c["index"]})


def _advance_one(stop_at=None):
    """推进到下一个决策点（先把挂起的 pending 答完再 step；409=锁被前序 step 占着→等它出 pending）。

    stop_at：predicate——命中时不答、原样停在 pending 上返回之（留给调用方处理）。"""
    t, box = None, {}
    for _ in range(400):
        s = _state()
        p = s.get("pending")
        if p is not None:
            if stop_at is not None and stop_at(p):
                return p
            _answer(p, s.get("skill_points", 0))
            time.sleep(0.05)
            continue
        if t is None:
            t, box = _step_thread()
            time.sleep(0.05)
            continue
        if box.get("err"):
            if "409" in box["err"]:
                t, box = None, {}   # 锁被占——下轮再试（先把 pending 答掉锁自然放）
                time.sleep(0.3)
                continue
            raise AssertionError(f"step 出错：{box['err']}")
        if not t.is_alive():
            return None   # 无决策点的 turn 走完
        time.sleep(0.05)
    raise AssertionError("advance 未收尾")


def _drive_to_transform() -> None:
    """开车到窗口放变身（队友技指白厄攒火种）。"""
    for _ in range(120):
        p = _advance_one(stop_at=lambda p: p["phase"] == "ultimate"
                         and "1408" in [r["actor_id"] for r in p.get("ready", [])])
        if p is not None:
            _choose({"actor_id": "1408"})
            return
    raise AssertionError("120 动内没到变身窗口")


@pytest.fixture(scope="module")
def browser_page():
    global _PAGE
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("无 playwright（E2E 冒烟跳过；uv pip install playwright 后可用）")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            _PAGE = browser.new_page()
            yield _PAGE
            browser.close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chromium 不可用（E2E 冒烟跳过）：{e}")


@pytest.fixture(scope="module")
def server(browser_page):
    proc = subprocess.Popen(
        ["uv", "run", "hsr-sim", "web", "--port", str(PORT), "--no-open",
         "--templates", "tests/fixtures/templates"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)   # 独立进程组：teardown 整组杀（uv 壳会留下真 python 子进程）
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(BASE + "/", timeout=2):
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise AssertionError("服务器 8139 起不来")
        browser_page.goto(f"{BASE}/#/battle")
        yield BASE
    finally:
        try:
            import os, signal
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass


def test_phainon_team_key_flows(server: str) -> None:
    # ---- 1. 开局渲染：按钮行/行动条/战技点数字 ----
    _api("/api/load", {"config": "demo_白厄队"})
    _step_thread()   # 引擎载入后是闲的：先推进到首个决策点（线程挂在 pending 上无妨）
    _wait_pending("action")
    _wait_dom("document.querySelectorAll('#actionBtns .act-btn').length >= 2", "按钮行渲染")
    _wait_dom("document.querySelectorAll('#actionBar .bar-entry').length >= 3",
              "行动条渲染（renderBar 异步 fetch）")
    r = _js("""(() => ({
        btns: document.querySelectorAll('#actionBtns .act-btn').length,
        bar: document.querySelectorAll('#actionBar .bar-entry').length,
        sp: document.getElementById('spPips').textContent
    }))()""")
    assert r["btns"] >= 2, f"按钮行缺失：{r}"
    assert r["bar"] >= 3, f"行动条凭空消失类：{r}"
    assert "/5" in r["sp"], f"战技点数字缺失：{r}"

    # ---- 2. 瞄准态：locked 高亮 + 候选 aimable ----
    _js("(() => { startAiming(S.pending.choices.find(c=>c.action_type==='skill')); render(); })()")
    r = _js("""(() => ({
        locked: document.querySelectorAll('#actionBtns .act-btn.locked').length,
        aimable: document.querySelectorAll('.card.aimable').length
    }))()""")
    assert r["locked"] == 1, f"锁定技能未点亮：{r}"
    assert r["aimable"] >= 1, f"候选未高亮：{r}"
    _js("(() => { aiming = null; render(); })()")

    # ---- 3. 推进到星期日回合：幽灵条落点在白厄 ----
    for _ in range(20):
        p = _advance_one(stop_at=lambda p: p["phase"] == "action" and p["actor_id"] == "1313")
        if p:
            break
    else:
        raise AssertionError("20 动内没到星期日回合")
    _wait_dom("S.pending && S.pending.actor_id === '1313' && S.pending.phase === 'action'",
              "页面同步星期日决策点")
    _js("(() => { startAiming(S.pending.choices.find(c=>c.action_type==='skill'));"
        "render(); if (S.barCache) layoutBar(S.barCache); })()")
    _wait_dom("document.querySelectorAll('.bar-entry.ghost').length >= 1", "拉条幽灵条渲染")
    r = _js("""(() => ({
        ghosts: [...document.querySelectorAll('.bar-entry.ghost')].map(n => n.dataset.aid)
    }))()""")
    assert "1408" in r["ghosts"], f"拉条幽灵条未落在白厄：{r}"
    _js("(() => { aiming = null; render(); })()")

    # ---- 4. 变身：放逐置灰+徽章 / 倒计时条目 / 毁伤资源行 ----
    _drive_to_transform()
    _wait_dom("document.querySelectorAll('.card.banished').length >= 3", "放逐置灰渲染")
    r = _js("""(() => ({
        banished: document.querySelectorAll('.card.banished').length,
        badges: document.querySelectorAll('.badge.banished').length,
        cd: [...document.querySelectorAll('#actionBar .bar-entry')]
              .filter(n => n.textContent.includes('倒')).length
    }))()""")
    assert r["banished"] >= 3 and r["badges"] >= 3, f"放逐显示缺失：{r}"
    assert r["cd"] >= 1, f"倒计时条目缺失：{r}"
    # 终结技槽位口径：白厄形态锁定（140805"无法施放终结技"）、队友放逐离场——全灰带原因
    r2 = _js("""(() => [...document.querySelectorAll('#allyRow .ult-slot-btn')].map(b => ({
        aid: b.dataset.ultnow, dis: b.classList.contains('disabled'),
        reason: b.dataset.reason || null })))()""")
    by_aid = {x["aid"]: x for x in r2}
    assert by_aid.get("1408", {}).get("reason") == "形态锁定", f"白厄变身期终结技应形态锁定：{r2}"
    assert all(by_aid.get(a, {}).get("reason") == "离场" for a in ("1412", "1313", "1414")), \
        f"放逐队友终结技应离场灰显：{r2}"
    s = _state()
    res = (s["actors"]["1408"].get("resources") or [])
    assert any(x["label"] == "毁伤" for x in res), f"毁伤资源行缺失：{res}"

    # ---- 5. 倒计时回合：形态三键 Q/W/E ----
    for _ in range(10):
        p = _advance_one(stop_at=lambda p: p["phase"] == "action" and p["actor_id"] == "1408")
        if p is not None:
            break
    else:
        raise AssertionError("10 动内没到白厄倒计时行动决策点")
    _wait_dom("[...document.querySelectorAll('#actionBtns .act-btn .key')]"
              ".some(n => n.textContent === 'W')", "形态三键渲染")
    r = _js("""(() => ({
        keys: [...document.querySelectorAll('#actionBtns .act-btn .key')].map(n => n.textContent)
    }))()""")
    assert {"Q", "W", "E"} <= set(r["keys"]), f"形态三键缺失：{r}"

    # ---- 6. 连续模式：推进且自然停在决策点（先答掉当前倒计时决策——
    # autoToggle 对挂起决策点是拒启的；选 140808 扩散普攻
    # （三怪沙包局弹主目标决策段——旧单怪局直通无此段——顺答首怪）----
    c = next(x for x in p["choices"] if x["action_id"] == "140808")
    _choose({"index": c["index"]})
    clock0 = _state()["clock"]
    pt = _wait_pending("target", timeout=5)
    _choose({"actor_id": pt["candidates"][0]["actor_id"]})
    _wait_dom("!S.pending", "页面消化倒计时决策")
    _js("(() => { if (!AUTO.on) autoToggle(); })()")
    time.sleep(3.0)
    s2 = _state()
    assert s2["clock"] > clock0, f"连续模式未推进：{clock0} → {s2['clock']}"
    _js("(() => { autoStop(); })()")

    # ---- 7. 终结技确认态：作用范围标签（与行动瞄准态【群攻】同口径——曾只显示技能名）----
    # 纯渲染断言：confirmHint 只在有决策点的分支渲染——合成 action pending 进分支
    # （别靠推进/autoStop 后的现场：三怪局节奏下停在哪儿是运气，曾两次超时落空）
    _js("(() => { S.manual = true; S.pending = {phase: 'action', actor_id: '1408', choices: [], ready: []};"
        " ultAim = {actor_id: '1414', name: '丹恒•腾荒', ult_name: '亢龙无悔，移山辟世',"
        " target_type: 'aoe', via: 'window', key_hint: '4', immediate: false}; render(); })()")
    _wait_dom("document.querySelector('#actionZone .hint') && "
              "document.querySelector('#actionZone .hint').textContent.includes('【群攻】')",
              "终结技确认态群攻标签")
    _js("(() => { ultAim = {actor_id: '1408', name: '白厄', ult_name: '永劫燔世，其将背负',"
        " target_type: 'single', via: 'now', key_hint: '1', immediate: false}; render(); })()")
    _wait_dom("document.querySelector('#actionZone .hint').textContent.includes('【单体】')",
              "终结技确认态单体标签")
    _js("(() => { ultAim = null; render(); })()")
