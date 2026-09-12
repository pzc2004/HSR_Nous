"""tribios（llm/ 统一接入层）测试：config 多 key / client 轮转与重试 / scheduler 流式调度
/ live config 热更新（物化/轮询/并发动态调整/端点热替换）."""
from __future__ import annotations

import json
import re
import threading
import time

import httpx
import pytest

from hsr_nous.llm import (
    DeadTask, LLMClient, LLMConfigError, LLMError, LLMUseConfig, LiveConfig, Scheduler,
    load_dotenv, load_use_config,
)
from hsr_nous.llm.client import current_key_slot


def _cfg(**kw) -> LLMUseConfig:
    base = dict(use="T", api_keys=("k1",), model="m", api_base="http://stub")
    base.update(kw)
    return LLMUseConfig(**base)


class _Resp:
    def __init__(self, content="ok", status=200, text=""):
        self.status_code = status
        self.text = text
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_multi_key_parsing(self):
        cfg = load_use_config("annotator", env={
            "HSR_NOUS_LLM_ANNOTATOR_API_KEY": " k1 , k2 ,,k3 ",
            "HSR_NOUS_LLM_ANNOTATOR_MODEL": "m",
        })
        assert cfg.api_keys == ("k1", "k2", "k3") and cfg.key_count == 3
        assert cfg.concurrency == 4  # 缺省
        assert cfg.api_base == "https://api.openai.com/v1"  # 缺省

    def test_openai_fallback_and_no_effort_fallback(self):
        cfg = load_use_config("annotator", env={
            "OPENAI_API_KEY": "ok", "OPENAI_MODEL": "om", "OPENAI_API_BASE": "http://o"})
        assert cfg.api_keys == ("ok",) and cfg.model == "om" and cfg.api_base == "http://o"
        assert cfg.effort == ""
        with pytest.raises(LLMConfigError, match="API_KEY"):
            load_use_config("annotator", env={"OPENAI_EFFORT": "high"})  # EFFORT 无回落，且缺 key

    def test_concurrency_read_and_validate(self):
        env = {"HSR_NOUS_LLM_T_API_KEY": "k", "HSR_NOUS_LLM_T_MODEL": "m",
               "HSR_NOUS_LLM_T_CONCURRENCY": "7"}
        assert load_use_config("t", env=env).concurrency == 7
        with pytest.raises(LLMConfigError, match="整数"):
            load_use_config("t", env={**env, "HSR_NOUS_LLM_T_CONCURRENCY": "abc"})
        with pytest.raises(LLMConfigError, match="≥1"):
            load_use_config("t", env={**env, "HSR_NOUS_LLM_T_CONCURRENCY": "0"})

    def test_missing_model_raises(self):
        with pytest.raises(LLMConfigError, match="MODEL"):
            load_use_config("t", env={"HSR_NOUS_LLM_T_API_KEY": "k"})

    def test_load_dotenv(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text(
            "# c\nTRIB_T_A=bar\nTRIB_T_B=\"a b\"\nTRIB_T_C=x # tail\n", encoding="utf-8")
        for k in ("TRIB_T_A", "TRIB_T_B", "TRIB_T_C"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("TRIB_T_A", "pre")  # 外部环境优先
        assert load_dotenv(tmp_path / ".env") is not None
        import os
        assert os.environ["TRIB_T_A"] == "pre"
        assert os.environ["TRIB_T_B"] == "a b"
        assert os.environ["TRIB_T_C"] == "x"
        assert load_dotenv(tmp_path / "nonexistent.env") is None


# ---------------------------------------------------------------------------
# client
# ---------------------------------------------------------------------------

class TestClient:
    def test_chat_payload_and_effort_passthrough(self):
        seen = []

        def transport(url, payload, headers):
            seen.append((url, payload, headers))
            return _Resp("答案")

        client = LLMClient(_cfg(effort="max", max_tokens=12345), transport=transport)
        out = client.chat([{"role": "user", "content": "hi"}])
        assert out == "答案"
        url, payload, headers = seen[-1]
        assert url == "http://stub/chat/completions"
        assert payload["model"] == "m" and payload["max_tokens"] == 12345
        assert payload["reasoning_effort"] == "max"
        assert headers["Authorization"] == "Bearer k1"

    def test_effort_omitted_when_empty_and_overridable(self):
        seen = []

        def transport(url, payload, headers):
            seen.append(payload)
            return _Resp()

        LLMClient(_cfg(), transport=transport).chat([{"role": "user", "content": "x"}])
        assert "reasoning_effort" not in seen[-1]
        client = LLMClient(_cfg(effort="max"), transport=transport)
        client.chat([{"role": "user", "content": "x"}], effort="low")  # 调用级覆盖配置
        assert seen[-1]["reasoning_effort"] == "low"
        client.chat([{"role": "user", "content": "x"}], max_tokens=999)
        assert seen[-1]["max_tokens"] == 999

    def test_key_rotation_and_explicit_index(self):
        auths = []

        def transport(url, payload, headers):
            auths.append(headers["Authorization"])
            return _Resp()

        client = LLMClient(_cfg(api_keys=("k1", "k2")), transport=transport)
        for _ in range(4):
            client.chat([{"role": "user", "content": "x"}])
        assert auths == ["Bearer k1", "Bearer k2", "Bearer k1", "Bearer k2"]
        client.chat([{"role": "user", "content": "x"}], key_index=1)
        assert auths[-1] == "Bearer k2"
        with pytest.raises(LLMError, match="越界"):
            client.chat([{"role": "user", "content": "x"}], key_index=5)

    def test_transport_retry_then_success(self, monkeypatch):
        monkeypatch.setattr("hsr_nous.llm.client.time.sleep", lambda s: None)
        calls = []

        def flaky(url, payload, headers):
            calls.append(1)
            if len(calls) == 1:
                raise httpx.ReadTimeout("slow")
            return _Resp("恢复")

        client = LLMClient(_cfg(), transport=flaky)
        assert client.chat([{"role": "user", "content": "x"}]) == "恢复"
        assert len(calls) == 2

    def test_transport_retry_exhausted_raises(self, monkeypatch):
        monkeypatch.setattr("hsr_nous.llm.client.time.sleep", lambda s: None)

        def always_timeout(url, payload, headers):
            raise httpx.ReadTimeout("slow")

        client = LLMClient(_cfg(), transport=always_timeout)
        with pytest.raises(LLMError, match="传输层错误"):
            client.chat([{"role": "user", "content": "x"}])

    def test_http_429_retried_then_raises(self, monkeypatch):
        monkeypatch.setattr("hsr_nous.llm.client.time.sleep", lambda s: None)
        calls = []

        def bad_status(url, payload, headers):
            calls.append(1)
            return _Resp(status=429, text="rate limited")

        client = LLMClient(_cfg(), transport=bad_status)
        with pytest.raises(LLMError, match="HTTP 429"):
            client.chat([{"role": "user", "content": "x"}])
        assert len(calls) == 5  # 429=限流瞬断族：TRANSPORT_RETRIES(4)+1 次退避重试后抛

    def test_http_4xx_no_retry_and_empty_content(self):
        calls = []

        def bad_status(url, payload, headers):
            calls.append(1)
            return _Resp(status=400, text="bad request")

        client = LLMClient(_cfg(), transport=bad_status)
        with pytest.raises(LLMError, match="HTTP 400"):
            client.chat([{"role": "user", "content": "x"}])
        assert len(calls) == 1  # 其余 4xx=确定性错误不重试
        empty = LLMClient(_cfg(), transport=lambda u, p, h: _Resp(content=""))
        with pytest.raises(LLMError, match="空 content"):
            empty.chat([{"role": "user", "content": "x"}])

    def test_parts_list_content_joined(self):
        client = LLMClient(_cfg(), transport=lambda u, p, h: type("R", (), {
            "status_code": 200,
            "json": lambda self: {"choices": [{"message": {"content": [
                {"text": "a"}, {"text": "b"}]}}]},
        })())
        assert client.chat([{"role": "user", "content": "x"}]) == "ab"


# ---------------------------------------------------------------------------
# scheduler
# ---------------------------------------------------------------------------

class TestScheduler:
    def test_per_key_cap_and_completion(self):
        client = LLMClient(_cfg(api_keys=("k1", "k2"), concurrency=2))
        sch = Scheduler(client)
        lock = threading.Lock()
        inflight = {}
        max_seen = {}

        def make(i):
            def task():
                k = current_key_slot()
                with lock:
                    inflight[k] = inflight.get(k, 0) + 1
                    max_seen[k] = max(max_seen.get(k, 0), inflight[k])
                time.sleep(0.02)
                with lock:
                    inflight[k] -= 1
                return i
            return task

        futs = [sch.submit(make(i), label=f"t{i}") for i in range(8)]
        sch.run()
        assert [f.result() for f in futs] == list(range(8))
        assert all(v <= 2 for v in max_seen.values()), f"每 key 并发超帽：{max_seen}"
        assert set(max_seen) == {0, 1}, "两个 key 都应被用到"

    def test_streaming_replenish_not_batch_wait(self):
        """完成一个立刻补一个：快任务完成后慢任务未结束时，新任务已在快 key 上开跑."""
        client = LLMClient(_cfg(api_keys=("k1", "k2"), concurrency=1))
        sch = Scheduler(client, per_key_concurrency=1)
        marks = {}

        def timed(name, dur):
            def task():
                time.sleep(dur)
                marks[name] = time.monotonic()
                return name
            return task

        t0 = time.monotonic()
        marks["A_start"] = t0
        sch.submit(timed("A_slow", 0.20), label="A")   # key#1 慢任务
        sch.submit(timed("B_fast", 0.02), label="B")   # key#2 快任务
        sch.submit(timed("C_fast", 0.02), label="C")   # 排队——B 完成即补到 key#2
        sch.run()
        assert marks["C_fast"] < marks["A_slow"], (
            "C 应在 B 完成后立刻补位（≈0.04s），不等 A（≈0.20s）——若成立则非分批等待")

    def test_retry_then_success(self):
        client = LLMClient(_cfg())
        sch = Scheduler(client)
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise ValueError("首次失败")
            return "ok"

        fut = sch.submit(flaky, label="flaky", max_retries=2)
        lines = []
        sch.run(progress_fn=lines.append)
        assert fut.result() == "ok"
        assert sch.retries == 1 and not sch.dead
        assert len(attempts) == 2

    def test_dead_after_max_retries(self):
        client = LLMClient(_cfg())
        sch = Scheduler(client)
        attempts = []

        def always_fail():
            attempts.append(1)
            raise ValueError("永远失败")

        fut = sch.submit(always_fail, label="bad", max_retries=2)
        sch.run()
        with pytest.raises(ValueError, match="永远失败"):
            fut.result()
        assert len(attempts) == 3  # 1 + 2 重试
        assert sch.retries == 2
        assert len(sch.dead) == 1
        dead = sch.dead[0]
        assert isinstance(dead, DeadTask) and dead.label == "bad" and dead.attempts == 3

    def test_progress_format(self):
        client = LLMClient(_cfg(api_keys=("k1", "k2"), concurrency=3))
        sch = Scheduler(client)
        sch.submit(lambda: 1, label="a")
        sch.submit(lambda: 1 / 0, label="b", max_retries=0)
        lines = []
        sch.run(progress_fn=lines.append)
        assert lines, "progress_fn 应在任务终态回调"
        assert re.fullmatch(r"1/2 完成 · key#1 \d/3 · key#2 \d/3 · 重试 0 · 人工 1",
                            lines[-1]), f"progress 末行形态：{lines[-1]!r}"

    def test_submit_after_close_rejected(self):
        client = LLMClient(_cfg())
        sch = Scheduler(client)
        sch.submit(lambda: 1)
        sch.run()
        with pytest.raises(RuntimeError, match="shutdown"):
            sch.submit(lambda: 2)


# ---------------------------------------------------------------------------
# LiveConfig（热更新文件）
# ---------------------------------------------------------------------------

def _write_live(path, **over):
    """改热更文件并确保 mtime 变化（poll 的触发条件）。失败即测试环境不支持 ns mtime."""
    before = path.stat().st_mtime_ns if path.exists() else -1
    data = dict(over)
    if path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            base = {}
        base.update(over)
        data = base
    for _ in range(200):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if path.stat().st_mtime_ns != before:
            return
        time.sleep(0.005)
    raise AssertionError("live 文件 mtime 不变——无法触发热更")


class TestLiveConfig:
    def test_materialize_creates_file_from_env(self, tmp_path):
        cfg = _cfg(api_base="http://ep", model="m", effort="max", concurrency=3)
        live = LiveConfig.materialize(tmp_path / "live.json", cfg)
        data = json.loads((tmp_path / "live.json").read_text(encoding="utf-8"))
        assert data == {"api_base": "http://ep", "model": "m",
                        "effort": "max", "concurrency": 3}
        assert "api_key" not in data, "api_key 永不进热更文件"
        cur = live.current
        assert (cur.api_base, cur.model, cur.effort, cur.concurrency) == (
            "http://ep", "m", "max", 3)
        assert live.poll() is None, "物化后无变化不应触发 reload"

    def test_existing_file_loaded_and_partial_update(self, tmp_path):
        path = tmp_path / "live.json"
        _write_live(path, api_base="http://edited", model="m2", effort="", concurrency=7)
        live = LiveConfig.materialize(path, _cfg())
        assert live.current.api_base == "http://edited" and live.current.concurrency == 7
        _write_live(path, concurrency=9)  # 只改一个字段，其余保持
        ov = live.poll()
        assert ov is not None and ov.concurrency == 9
        assert ov.api_base == "http://edited" and ov.model == "m2"
        assert live.poll() is None  # mtime 未再变 → None

    def test_effort_can_be_cleared(self, tmp_path):
        live = LiveConfig.materialize(tmp_path / "live.json", _cfg(effort="max"))
        _write_live(live.path, effort="")
        ov = live.poll()
        assert ov is not None and ov.effort == ""

    def test_invalid_content_keeps_old_and_records_error(self, tmp_path):
        live = LiveConfig.materialize(tmp_path / "live.json", _cfg(concurrency=3))
        _write_live(live.path, concurrency=0)
        assert live.poll() is None and "≥1" in live.last_error
        assert live.current.concurrency == 3, "非法内容沿用旧值"
        _write_live(live.path, concurrency="abc")
        assert live.poll() is None and "整数" in live.last_error
        live.path.write_text("{oops", encoding="utf-8")
        live._mtime_ns = None  # 强制重读（绕过 mtime 书签）
        assert live.poll() is None and live.last_error
        _write_live(live.path, concurrency=8)  # 修好后恢复生效
        ov = live.poll()
        assert ov is not None and ov.concurrency == 8 and live.last_error == ""

    def test_api_key_in_file_ignored(self, tmp_path):
        live = LiveConfig.materialize(tmp_path / "live.json", _cfg())
        _write_live(live.path, api_key="leak-me-not", concurrency=5)
        ov = live.poll()
        assert ov is not None and ov.concurrency == 5
        assert not hasattr(ov, "api_key")

    def test_deleted_file_keeps_old(self, tmp_path):
        live = LiveConfig.materialize(tmp_path / "live.json", _cfg(concurrency=4))
        live.path.unlink()
        assert live.poll() is None and live.current.concurrency == 4


# ---------------------------------------------------------------------------
# client 热替换 + scheduler 热更新
# ---------------------------------------------------------------------------

class TestClientHotSwap:
    def test_apply_endpoint_affects_only_later_calls(self):
        seen = []

        def transport(url, payload, headers):
            seen.append((url, payload["model"], payload.get("reasoning_effort"),
                         headers["Authorization"]))
            return _Resp()

        client = LLMClient(_cfg(api_keys=("k1", "k2"), api_base="http://old",
                                model="m1", effort="low"), transport=transport)
        old_cfg = client.config
        client.chat([{"role": "user", "content": "x"}])
        client.apply_endpoint(api_base="http://new", model="m2", effort="max")
        assert client.config is not old_cfg, "重建实例（frozen replace）"
        assert client.config.api_keys == ("k1", "k2"), "保留 key 列表"
        client.chat([{"role": "user", "content": "x"}])
        assert seen[0] == ("http://old/chat/completions", "m1", "low", "Bearer k1")
        assert seen[1] == ("http://new/chat/completions", "m2", "max", "Bearer k2")
        # 在飞语义等价物：调用进入时取走的 cfg 快照不受后续热替换影响
        cfg_snapshot = client.config
        client.apply_endpoint(api_base="http://third")
        assert cfg_snapshot.api_base == "http://new"


class _Gate:
    """线程同步计数闸：等第 N 个任务起跑（超时即失败，不盲 sleep）."""

    def __init__(self):
        self.cond = threading.Condition()
        self.started = 0

    def tick(self):
        with self.cond:
            self.started += 1
            self.cond.notify_all()

    def wait_started(self, n, timeout=10.0):
        deadline = time.monotonic() + timeout
        with self.cond:
            while self.started < n:
                remaining = deadline - time.monotonic()
                assert remaining > 0, f"等第 {n} 个任务起跑超时（started={self.started}）"
                self.cond.wait(remaining)


class TestSchedulerLive:
    def test_live_file_applied_at_init(self, tmp_path):
        path = tmp_path / "live.json"
        _write_live(path, api_base="http://pre", model="mm", effort="", concurrency=7)
        client = LLMClient(_cfg(concurrency=2))
        sch = Scheduler(client, live=LiveConfig.materialize(path, client.config))
        assert sch.per_key == 7, "启动即以热更文件为准"
        assert client.config.api_base == "http://pre" and client.config.model == "mm"

    def test_concurrency_bump_mid_run_adds_slots(self, tmp_path):
        cfg = _cfg(concurrency=4)
        live = LiveConfig.materialize(tmp_path / "live.json", cfg)
        sch = Scheduler(LLMClient(cfg), live=live, live_poll_interval=0.02)
        gate, release = _Gate(), threading.Event()

        def make(i):
            def task():
                gate.tick()
                assert release.wait(timeout=15), "测试收尾异常：release 未置位"
                return i
            return task

        futs = [sch.submit(make(i), label=f"t{i}") for i in range(12)]
        runner = threading.Thread(target=sch.run)
        runner.start()
        try:
            gate.wait_started(4)
            time.sleep(0.1)
            assert gate.started == 4, "每 key 并发 4 封顶（热更前）"
            _write_live(live.path, concurrency=8)  # 4→8：慢任务在飞期间改并发
            gate.wait_started(8)
            time.sleep(0.1)
            assert gate.started == 8, "调大到 8 后在飞数立刻上升（不等在飞完成）"
        finally:
            release.set()
            runner.join(timeout=15)
        assert not runner.is_alive()
        assert [f.result() for f in futs] == list(range(12))

    def test_concurrency_shrink_does_not_kill_inflight(self, tmp_path):
        cfg = _cfg(concurrency=3)
        live = LiveConfig.materialize(tmp_path / "live.json", cfg)
        sch = Scheduler(LLMClient(cfg), live=live, live_poll_interval=0.02)
        gate, release = _Gate(), threading.Event()

        def make(i):
            def task():
                gate.tick()
                assert release.wait(timeout=15)
                return i
            return task

        futs = [sch.submit(make(i), label=f"t{i}") for i in range(5)]
        runner = threading.Thread(target=sch.run)
        runner.start()
        try:
            gate.wait_started(3)
            _write_live(live.path, concurrency=1)  # 调小：不杀在飞，自然回落
            time.sleep(0.3)
            assert gate.started == 3, "调小后不再派发，但在飞 3 个继续跑"
        finally:
            release.set()
            runner.join(timeout=15)
        assert not runner.is_alive()
        assert [f.result() for f in futs] == list(range(5))

    def test_endpoint_swap_affects_only_later_dispatches(self, tmp_path):
        cfg = _cfg(api_base="http://old", model="m1", concurrency=1)
        live = LiveConfig.materialize(tmp_path / "live.json", cfg)
        seen, first_called = [], threading.Event()
        first_may_finish = threading.Event()

        def transport(url, payload, headers):
            seen.append((url, payload["model"]))
            if len(seen) == 1:
                first_called.set()
                assert first_may_finish.wait(timeout=15), "首个在飞请求未被放行"
            return _Resp()

        client = LLMClient(cfg, transport=transport)
        sch = Scheduler(client, live=live, live_poll_interval=0.02)
        for i in range(3):
            sch.submit(lambda: client.chat([{"role": "user", "content": "x"}]),
                       label=f"t{i}")
        lines = []
        runner = threading.Thread(target=sch.run, args=(lines.append,))
        runner.start()
        try:
            assert first_called.wait(timeout=10), "首个任务未起跑"
            _write_live(live.path, api_base="http://new", model="m2")  # 在飞中改端点
        finally:
            first_may_finish.set()
            runner.join(timeout=15)
        assert not runner.is_alive()
        assert seen[0] == ("http://old/chat/completions", "m1"), "在飞在原端点跑完"
        assert seen[1:] == [("http://new/chat/completions", "m2")] * 2, (
            "之后派发的任务切到新端点/新模型")
        assert re.search(r"m2 @ http://new · 并发 1/key$", lines[-1]), (
            f"progress 行显示当前生效 endpoint/model/并发：{lines[-1]!r}")

    def test_progress_shows_live_error(self, tmp_path):
        cfg = _cfg(concurrency=2)
        live = LiveConfig.materialize(tmp_path / "live.json", cfg)
        sch = Scheduler(LLMClient(cfg), live=live, live_poll_interval=0.02)
        _write_live(live.path, concurrency=-1)
        sch._poll_live()
        assert "热更配置非法" in sch.progress() and sch.per_key == 2

    def test_no_live_keeps_plain_progress(self):
        client = LLMClient(_cfg())
        sch = Scheduler(client)
        sch.submit(lambda: 1, label="a")
        lines = []
        sch.run(progress_fn=lines.append)
        assert "@" not in lines[-1] and "并发" not in lines[-1], (
            "不挂 live 时 progress 行保持原形态")
