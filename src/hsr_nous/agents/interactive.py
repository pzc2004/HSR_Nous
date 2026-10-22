"""交互式研究 Agent 原型：人在浏览器里与挂载 nous 工具的 DSH 对话。

聊天主入口是研究台单页——``hsr-research-web``（默认 8001）启动时会代管聊天桥
子进程（``agents.chat_server``，回环随机端口 + ``/chat/*`` 反代）。本 CLI 保留
两种显式模式：

- 缺省（stock web）：启动 DSH web 面（叠加研究 profile），DSH 自带 UI::

    hsr-research-chat                # 起服务（默认 8002 端口，仅回环绑定）
    hsr-research-chat --port 8080    # 换端口

- ``--serve``（ACP 桥独立模式）：薄委托到 ``chat_server.main``，开发调试直起桥
  进程（不经研究台反代）::

    hsr-research-chat --serve                # 默认 8003 端口
    hsr-research-chat --serve --port 8080

两种模式叠加同一组 profile 补丁：

- ``research.cordis.yml``：禁用全部内置工具、只读沙箱（工作区=研究根）、
  挂载 ``nous`` MCP 网关（候选/claim 工具族）与工具白名单 guard；
- ``openai.cordis.yml``：``agent-default-model`` 指向仓库根 ``.env`` 的
  ``HSR_NOUS_LLM_AGENTS_*`` OpenAI 兼容端点。

信任边界与 headless 一致：Agent 只能调用 ``mcp__nous__*`` 白名单工具，可信结论
由研究后端（research/core）产出，Agent 自然语言文本不可信。stock web 启动后打印的
``dsh web:`` 令牌化 URL 即访问凭证，注意保密。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from hsr_nous.agents.dsh import _environment, _executable, _prepare_root
from hsr_nous.common import load_repo_env, repo_root

DEFAULT_PORT = 8002  # stock web：研究台 web 已约定 8001，此处错开
SERVE_PORT = 8003  # ACP 桥独立模式：8001=workbench、8002=stock chat，此处再错开


def _build_argv(port: int, dsh_bin: Path | None) -> list[str]:
    profile_dir = Path(__file__).parent / "dsh_profile"
    return [
        _executable(dsh_bin),
        "--profile", "web",
        "--patch", str(profile_dir / "research.cordis.yml"),
        "--patch", str(profile_dir / "openai.cordis.yml"),
        "--no-open",
        "--port", str(port),
    ]


def _serve(port: int, root: Path | None, dsh_bin: Path | None) -> int:
    """ACP 桥独立模式：薄委托 chat_server.main（前置校验/组装都在桥侧）。"""
    from hsr_nous.agents.chat_server import main as bridge_main

    argv = ["--port", str(port), "--host", "127.0.0.1"]
    if root is not None:
        argv += ["--research-root", str(root)]
    if dsh_bin is not None:
        argv += ["--dsh-bin", str(dsh_bin)]
    return bridge_main(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve", action="store_true",
        help="走 ACP 桥独立模式（chat_server 直起；日常聊天主入口是 hsr-research-web）",
    )
    parser.add_argument("--port", type=int, default=None, help="监听端口（缺省 8002；--serve 时 8003）")
    parser.add_argument("--research-root", type=Path, help="研究根（默认 HSR_NOUS_RESEARCH_ROOT 或 ~/HSR_Nous）")
    parser.add_argument("--dsh-bin", type=Path, help="DSH 可执行文件（默认 external/dsh 或 PATH）")
    args = parser.parse_args(argv)
    if args.serve:
        return _serve(
            args.port if args.port is not None else SERVE_PORT,
            args.research_root,
            args.dsh_bin,
        )

    load_repo_env()  # 仓库根 .env → 环境变量（不覆盖已有）；DSH 启动时也会自行读取
    missing = [name for name in (
        "HSR_NOUS_LLM_AGENTS_API_KEY",
        "HSR_NOUS_LLM_AGENTS_MODEL",
        "HSR_NOUS_LLM_AGENTS_API_BASE",
    ) if not os.environ.get(name)]
    if missing:
        parser.error(
            f"缺少模型配置 {missing}——先按 .env.example 填写 HSR_NOUS_LLM_AGENTS_* 三项"
        )

    root = _prepare_root(args.research_root)
    env = _environment(root, None)
    argv_dsh = _build_argv(args.port if args.port is not None else DEFAULT_PORT, args.dsh_bin)
    print(f"研究根: {root}", file=sys.stderr)
    print("启动后请打开打印的 dsh web: 令牌化 URL（VS Code 端口转发场景把 host 换成本地 localhost）", file=sys.stderr)
    os.execvpe(argv_dsh[0], argv_dsh, env)
    return 0  # os.execvpe 成功则不返回


if __name__ == "__main__":
    raise SystemExit(main())
