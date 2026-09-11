"""hsr-sim web 孤儿看护回归：一次性 bash 包装死后，服务器必须数秒内自动停服。

历史事故（2026-09-07）：一次性 `bash -c 'uv run hsr-sim web … &'` 起的 dev 服务器
全部孤儿化（ppid=1），单机攒出 159 个拖垮负载。本测试复现该形状：外层 bash 起完
即死 → 属主死亡 → 看护线程应自动停服（端口关闭、进程清场）。
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path

from hsr_nous.sim.web import _is_wrapper_cmd, _owner_pid

_ROOT = Path(__file__).parent.parent
_PORT = 8153
_BASE = f"http://127.0.0.1:{_PORT}"
_LOG = "/tmp/hsr-orphan-guard-test.log"
_PGREP_PAT = f"hsr-sim web --port {_PORT}"


def _port_open() -> bool:
    try:
        with urllib.request.urlopen(_BASE + "/", timeout=1):
            return True
    except Exception:  # noqa: BLE001 —— 拒连/超时都视为未开
        return False


def _leftover_pids() -> list[str]:
    r = subprocess.run(["pgrep", "-f", _PGREP_PAT], capture_output=True, text=True)
    return [p for p in r.stdout.split() if p != str(os.getpid())]


def test_wrapper_cmd_detection() -> None:
    assert _is_wrapper_cmd("uv run hsr-sim web --port 1")
    assert _is_wrapper_cmd("/Users/x/.venv/bin/python3 /Users/x/.venv/bin/hsr-sim web")
    assert _is_wrapper_cmd("hsr-sim web --port 1")
    # bash -c 里包着 hsr-sim 启动串的干等子壳也是包装（孤儿事故的真实形状）
    assert _is_wrapper_cmd("/bin/bash -c cd /x && uv run hsr-sim web --port 1 >log 2>&1 &")
    # 真属主：交互 shell / pytest / 监管进程
    assert not _is_wrapper_cmd("/bin/zsh")
    assert not _is_wrapper_cmd("/Users/x/.venv/bin/python3 /Users/x/.venv/bin/pytest tests/")
    assert not _is_wrapper_cmd("")


def test_owner_pid_is_alive() -> None:
    # 当前 pytest 进程链上总有一个活着的非包装属主（交互 shell / 任务壳 / 监管进程）
    owner = _owner_pid()
    assert owner is not None, "pytest 链上找不到非包装属主（起服即孤儿？）"
    os.kill(owner, 0)


def test_orphaned_server_self_terminates() -> None:
    assert not _port_open(), f"端口 {_PORT} 被占，换个端口再跑"
    try:
        # 形状复现：一次性 bash -c '… &' —— bash 秒死，uv/python 随即孤儿化
        subprocess.run(
            ["/bin/bash", "-c",
             f"cd '{_ROOT}' && uv run hsr-sim web --port {_PORT} --no-open "
             f"--templates tests/fixtures/templates >{_LOG} 2>&1 &"],
            check=True)
        deadline = time.time() + 60  # uv 冷启动 + 模板编译，宽松等
        while time.time() < deadline and not _port_open():
            time.sleep(0.3)
        assert _port_open(), f"服务器没起来（日志 {_LOG}）"
        # 属主（一次性 bash）已死 → 看护 interval+grace 量级内停服（宽限 30s）
        deadline = time.time() + 30
        while time.time() < deadline and _port_open():
            time.sleep(0.5)
        assert not _port_open(), "孤儿看护未生效：属主死后服务器仍存活"
        time.sleep(1)  # uv 壳察觉子进程死亡退出有一瞬间的先后
        assert _leftover_pids() == [], f"孤儿看护未生效：残留进程 {_leftover_pids()}"
    finally:
        subprocess.run(["pkill", "-f", _PGREP_PAT], capture_output=True)
