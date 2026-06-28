"""自动战斗 CLI 入口（dry-run 默认）.

用法：
    # DryRun 模式
    uv run python -m hsr_nous.pilot --max-cycles 5

    # 真机模式（确认风险后）
    HSR_NOUS_ALLOW_AUTOPILOT=1 uv run python -m hsr_nous.pilot --max-cycles 5 --live

启动时打印 ToS 警告；用户必须明确 --live 才尝试真机模式。
"""
from __future__ import annotations

import argparse
import sys

from hsr_nous.pilot import PilotConfig, PilotController


def _print_warning() -> None:
    print("=" * 60)
    print("⚠️  自动战斗模块（hsr_nous.pilot）")
    print("⚠️  本模块违反 HoYoverse ToS，存在账号封禁风险")
    print("⚠️  仅供学习研究，作者不承担责任")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HSR_Nous 自动战斗模块（默认 dry-run）",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=10,
        help="最大循环次数（默认 10）",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="检测置信度下限（默认 0.6）",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="真机模式（需 HSR_NOUS_ALLOW_AUTOPILOT=1 + I ACCEPT）",
    )
    args = parser.parse_args()

    _print_warning()

    if args.live:
        print("⚠️  启用真机模式 — 你需要显式接受风险")
        try:
            accept = input("键入 'I ACCEPT' 以确认: ").strip()
        except EOFError:
            accept = ""
        if accept != "I ACCEPT":
            print("❌ 未确认风险，退出")
            return 1
        print("✅ 已确认风险，启动真机模式")
    else:
        print("ℹ️  Dry-run 模式（不实际点击）")

    cfg = PilotConfig(
        dry_run=not args.live,
        max_cycles=args.max_cycles,
        min_confidence=args.min_confidence,
        accept_text="I ACCEPT" if args.live else "",
    )

    try:
        controller = PilotController(cfg)
    except RuntimeError as e:
        print(f"❌ 启动失败: {e}", file=sys.stderr)
        return 1

    results = controller.run()
    print(f"\n✅ 执行 {len(results)} 轮循环")
    for r in results:
        target_str = f"target={r.target}" if r.target else "no target"
        print(f"  cycle={r.cycle} action={r.action_taken} {target_str} confidence={r.confidence:.2f}")

    if isinstance(controller.actuator, DryRunActuator := __import__(
        "hsr_nous.pilot.actuator", fromlist=["DryRunActuator"]
    ).DryRunActuator):
        events = controller.actuator.events
        print(f"\n记录 {len(events)} 个事件（dry-run，未触发）")
    return 0


if __name__ == "__main__":
    sys.exit(main())