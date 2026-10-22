"""交互式研究 Agent 原型：人在浏览器里与挂载 nous 工具的 DSH 对话。

启动 DSH web 面（叠加研究 profile）：

- ``research.cordis.yml``：禁用全部内置工具、只读沙箱（工作区=研究根）、
  挂载 ``nous`` MCP 网关（候选/claim 工具族）与工具白名单 guard；
- ``openai.cordis.yml``：``agent-default-model`` 指向仓库根 ``.env`` 的
  ``HSR_NOUS_LLM_AGENTS_*`` OpenAI 兼容端点。

信任边界与 headless 一致：Agent 只能调用 ``mcp__nous__*`` 白名单工具，可信结论
由研究后端（research/core）产出，Agent 自然语言文本不可信。启动后打印的
``dsh web:`` 令牌化 URL 即访问凭证，注意保密。

用法::

    hsr-research-chat                # 起服务（默认 8002 端口，仅回环绑定）
    hsr-research-chat --port 8080    # 换端口
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from hsr_nous.agents.dsh import _environment, _executable, _prepare_root
from hsr_nous.common import load_repo_env, repo_root

DEFAULT_PORT = 8002  # 研究台 web 已约定 8001，此处错开


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="监听端口（默认 8002）")
    parser.add_argument("--research-root", type=Path, help="研究根（默认 HSR_NOUS_RESEARCH_ROOT 或 ~/HSR_Nous）")
    parser.add_argument("--dsh-bin", type=Path, help="DSH 可执行文件（默认 external/dsh 或 PATH）")
    args = parser.parse_args(argv)

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
    argv_dsh = _build_argv(args.port, args.dsh_bin)
    print(f"研究根: {root}", file=sys.stderr)
    print("启动后请打开打印的 dsh web: 令牌化 URL（VS Code 端口转发场景把 host 换成本地 localhost）", file=sys.stderr)
    os.execvpe(argv_dsh[0], argv_dsh, env)
    return 0  # os.execvpe 成功则不返回


if __name__ == "__main__":
    raise SystemExit(main())
