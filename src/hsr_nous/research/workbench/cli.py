"""Run the research workbench locally（唯一前端：研究视图 + ACP 聊天视图）。

聊天桥是 workbench 代管的第二个本地服务（spawn 子进程，同 sim.web 本地服务
先例；workbench 不 import agents 任何代码，只做回环反代）。缺模型配置或 DSH
时子进程自行非零退出，本侧探活失败后降级为无聊天。
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Sequence

import httpx

from hsr_nous.common import repo_root, research_root

_HEALTHZ_TIMEOUT_S = 30.0


def _free_loopback_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    """terminate → 5s 等待 → kill 兜底（uvicorn 自身处理 SIGTERM 优雅退出）。"""
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _spawn_chat_bridge(
    root: Path, dsh_bin: Path | None
) -> tuple[subprocess.Popen[bytes], str] | None:
    """spawn 回环聊天桥子进程（``agents.chat_server``）并等 ``/healthz`` 就绪。

    前置校验内聚在子进程（缺 ``HSR_NOUS_LLM_AGENTS_*``/DSH 即打印中文错误并非零
    退出）；本侧只管 spawn、探活与失败收尸。任何一步失败都 terminate 并返回
    None——降级为无聊天（页面标注「聊天桥未启用」）。
    """
    port = _free_loopback_port()
    argv = [
        sys.executable, "-m", "hsr_nous.agents.chat_server",
        "--port", str(port), "--host", "127.0.0.1",
        "--research-root", str(root),
    ]
    if dsh_bin is not None:
        argv += ["--dsh-bin", str(dsh_bin)]
    try:
        proc = subprocess.Popen(argv, cwd=repo_root())
    except OSError as error:
        print(f"聊天视图未启用：无法启动聊天桥子进程：{error}", file=sys.stderr)
        return None
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + _HEALTHZ_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            print(
                f"聊天视图未启用：聊天桥子进程提前退出（code={proc.returncode}）"
                "——检查 HSR_NOUS_LLM_AGENTS_* 模型配置与 DSH（scripts/setup_agent_env.sh）",
                file=sys.stderr,
            )
            return None
        try:
            if httpx.get(f"{base}/healthz", timeout=1.0).status_code == 200:
                return proc, base
        except httpx.HTTPError:
            time.sleep(0.2)
    print("聊天视图未启用：聊天桥 /healthz 等待超时（30s）", file=sys.stderr)
    _terminate(proc)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=research_root())
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--dsh-bin", type=Path, help="聊天桥 DSH 可执行文件（默认 external/dsh 或 PATH）")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-orphan-guard", action="store_true")
    args = parser.parse_args(argv)
    try:
        from hsr_nous.research.workbench.web import create_app
        from hsr_nous.sim.web import run_server
    except ImportError:
        print("缺少网页端依赖：uv pip install -e \".[web]\"", file=sys.stderr)
        return 1
    bridge = _spawn_chat_bridge(args.research_root, args.dsh_bin)
    app = create_app(args.research_root, chat_proxy=bridge[1] if bridge else None)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    guard = "" if args.no_orphan_guard else "，孤儿看护开"
    if bridge is not None:
        chat = f"聊天视图开（回环反代 → ACP 桥子进程 :{bridge[1].rsplit(':', 1)[1]}）"
    else:
        chat = "聊天视图未启用"
    print(f"HSR_Nous 研究台：{url}（研究数据只读，{chat}{guard}，Ctrl-C 停止）")
    try:
        run_server(app, args.port, orphan_guard=not args.no_orphan_guard)
    finally:
        if bridge is not None:
            _terminate(bridge[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
