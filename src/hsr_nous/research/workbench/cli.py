"""Run the read-only research workbench locally."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Sequence

from hsr_nous.common import research_root


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, default=research_root())
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-orphan-guard", action="store_true")
    args = parser.parse_args(argv)
    try:
        from hsr_nous.research.workbench.web import create_app
        from hsr_nous.sim.web import run_server
    except ImportError:
        print("缺少网页端依赖：uv pip install -e \".[web]\"", file=sys.stderr)
        return 1
    app = create_app(args.research_root)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    guard = "" if args.no_orphan_guard else "，孤儿看护开"
    print(f"HSR_Nous 研究台：{url}（只读{guard}，Ctrl-C 停止）")
    run_server(app, args.port, orphan_guard=not args.no_orphan_guard)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
