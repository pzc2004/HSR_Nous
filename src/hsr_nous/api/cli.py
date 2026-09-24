"""`hsr-nous` 项目级 CLI（博识尊统一入口——各域命令的薄壳调度；名册：出入口归 aquila/边界层）.

- `hsr-nous config`：查看标注器 LLM 热更配置（仓库树外 `~/.config/hsr_nous/`；密钥只在 env 不展示）

分工：模拟器自有 `hsr-sim`（sim/cli.py，战斗相关）；本命令面只装项目级/infra 级入口。
api 层允许 import adapters/llm（AGENTS.md 边界表），infra 知识真引用、不做镜像常量。
"""

from __future__ import annotations

import argparse
import json
import time

from hsr_nous.llm.config import DEFAULT_LIVE_CONFIG_PATH


def _cmd_config() -> int:
    """`hsr-nous config`：打印标注器 LLM 热更配置（仓库树外文件；密钥只在 env，本命令不展示）."""
    path = DEFAULT_LIVE_CONFIG_PATH
    print(f"热更文件：{path}")
    if not path.exists():
        print("（不存在——首次跑标注器时以 env 值物化；env 引导配置见项目根 .env）")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"✗ 读取失败：{e}")
        return 1
    for key in ("api_base", "model", "effort", "concurrency"):
        if key in data:
            print(f"  {key}: {data[key]}")
    mtime = time.strftime("%F %T", time.localtime(path.stat().st_mtime))
    print(f"（修改于 {mtime}；运行中的标注器按 mtime 热载，文件值优先于 env 引导值）")
    print("⚠ 输出含内部端点，勿截图外发；API key 只在 env，本命令永不展示")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hsr-nous", description="博识尊项目级 CLI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("config", help="查看标注器 LLM 热更配置（仓库树外文件）")
    args = parser.parse_args(argv)
    if args.cmd == "config":
        return _cmd_config()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
