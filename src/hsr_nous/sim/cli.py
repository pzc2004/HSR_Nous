"""`hsr-sim` 命令行入口（名册代号 aquila/天空泰坦——边界层：一切出入口归它；泰坦名只活文档，不进标识符）.

- `hsr-sim run <build.yaml> <stage.yaml>`：一把梭跑完整场，出战报
- `hsr-sim debug <build.yaml> <stage.yaml>`：交互调试（单步/断点/检视/回退/手动选行动）

本层是纯壳：解析命令 → 调 `DebugController`/引擎 → 打印，不含任何战斗逻辑。
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.sim import CombatEngine, DebugController, MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.compile import compile_encounter_yaml
from hsr_nous.sim.debug import DEFAULT_CHECKPOINT_INTERVAL

_PROMPT = "(oronyx) "

_HELP = """命令一览：
  step / s                推进一回合
  continue / c            连续跑到断点或终局
  break turn <n>          第 n 动断点
  break actor <名/id>     单位行动断点
  breaks / clear          查看断点 / 清空断点
  bar [n]                 行动条预览（默认前 10）
  field                   全场概览
  inspect <名/id>         检视单位（HP/能量/buff/资源/形态）
  log [n]                 最近 n 条日志（默认 20）
  trace [n]               轨迹表（最近 n 动，默认 20）
  snapshot [--out 文件]   当前局面快照（JSON）
  back [n]                回退 n 动（默认 1）
  goto <n>                跳到第 n 动
  manual / auto           手动接管决策 / 交还编译策略
  help / quit             帮助 / 退出
"""


def _load_compiled(build_path: str, stage_path: str):
    return compile_encounter_yaml(
        Path(build_path).read_text(encoding="utf-8"),
        Path(stage_path).read_text(encoding="utf-8"),
    )


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# run：一把梭
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace) -> int:
    compiled = _load_compiled(args.build, args.stage)
    engine = CombatEngine.from_compiled(compiled, mode=args.mode, seed=args.seed)
    state = engine.run()
    snap = state.snapshot()
    print(f"总伤害 {snap['total_damage']:,.0f}｜轮次 {snap['cycles_used']}｜行动数 {snap['turn_count']}"
          + ("｜⚠ 截断局" if snap["truncated"] else ""))
    for aid, dmg in sorted(snap["damage_by_actor"].items(), key=lambda kv: -kv[1]):
        name = state.actors[aid].actor.name if aid in state.actors else aid
        print(f"  {name}: {dmg:,.0f}")
    if args.log:
        print("---- 战斗日志 ----")
        for line in state.log:
            print(line)
    return 0


# ---------------------------------------------------------------------------
# debug：交互调试
# ---------------------------------------------------------------------------

class _Repl:
    def __init__(self, ctl: DebugController) -> None:
        self.ctl = ctl

    # -- 工具 --

    def _resolve(self, token: str) -> str:
        """单位名或 id → actor_id。"""
        actors = self.ctl.state.actors
        if token in actors:
            return token
        for aid, st in actors.items():
            if st.actor.name == token:
                return aid
        raise KeyError(f"找不到单位 {token!r}（field 可查在场单位）")

    def _choose_hook(self, legal: List[Any]) -> Any:
        """手动决策回调：列出合法行动，读编号。"""
        print("── 决策点，选择行动：")
        for i, a in enumerate(legal):
            print(f"  [{i}] {a.name}（{a.action_type}）")
        raw = input("编号（回车=0）：").strip()
        if not raw:
            return legal[0]
        try:
            return legal[int(raw)]
        except (ValueError, IndexError):
            print("无效编号，按 [0] 处理")
            return legal[0]

    # -- 命令 --

    def cmd_step(self, _a: List[str]) -> None:
        rec = self.ctl.step_turn()
        for line in rec["logs"]:
            print(line)
        if not rec["done"]:
            print(f"· turn_count={self.ctl.state.turn_count} clock={self.ctl.state.clock:.1f}")

    def cmd_continue(self, _a: List[str]) -> None:
        rec = self.ctl.continue_()
        for line in rec["logs"]:
            print(line)
        print("· 已到终局" if rec["done"] else f"· 断点停于 turn_count={self.ctl.state.turn_count}")

    def cmd_break(self, a: List[str]) -> None:
        if len(a) != 2 or a[0] not in ("turn", "actor"):
            print("用法：break turn <n> | break actor <名/id>")
            return
        if a[0] == "turn":
            self.ctl.break_on_turn(int(a[1]))
        else:
            self.ctl.break_on_actor(self._resolve(a[1]))
        print("· 断点已设")

    def cmd_breaks(self, _a: List[str]) -> None:
        print(f"turn 断点: {sorted(self.ctl._break_turns) or '无'}；actor 断点: {sorted(self.ctl._break_actors) or '无'}")

    def cmd_clear(self, _a: List[str]) -> None:
        self.ctl.clear_breaks()
        print("· 断点已清空")

    def cmd_bar(self, a: List[str]) -> None:
        _print_json(self.ctl.action_bar(int(a[0]) if a else 10))

    def cmd_field(self, _a: List[str]) -> None:
        _print_json(self.ctl.field())

    def cmd_inspect(self, a: List[str]) -> None:
        if not a:
            print("用法：inspect <名/id>")
            return
        _print_json(self.ctl.inspect(self._resolve(a[0])))

    def cmd_log(self, a: List[str]) -> None:
        n = int(a[0]) if a else 20
        for line in self.ctl.state.log[-n:]:
            print(line)

    def cmd_trace(self, a: List[str]) -> None:
        n = int(a[0]) if a else 20
        for e in self.ctl.trace[-n:]:
            skip = "（跳过）" if e["skipped"] else ""
            print(f"  动{e['turn_count']:<4} AV{e['clock']:<8.1f} {e['actor_id']:<10} {e['kind']}{skip}")

    def cmd_snapshot(self, a: List[str]) -> None:
        snap = self.ctl.snapshot()
        if "--out" in a:
            path = a[a.index("--out") + 1]
            Path(path).write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"· 快照已写入 {path}")
        else:
            _print_json(snap)

    def cmd_back(self, a: List[str]) -> None:
        self.ctl.back(int(a[0]) if a else 1)
        print(f"· 已回退到 turn_count={self.ctl.state.turn_count}")

    def cmd_goto(self, a: List[str]) -> None:
        if not a:
            print("用法：goto <n>")
            return
        self.ctl.goto_turn(int(a[0]))
        print(f"· 已跳到 turn_count={self.ctl.state.turn_count}")

    def cmd_manual(self, _a: List[str]) -> None:
        self.ctl.set_action_hook(self._choose_hook)
        print("· 手动模式：我方决策点将询问你")

    def cmd_auto(self, _a: List[str]) -> None:
        self.ctl.set_auto()
        print("· 自动模式：交还编译策略")

    def run(self) -> int:
        self.cmd_manual([])
        self.cmd_field([])
        print(_HELP)
        while True:
            try:
                raw = input(_PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not raw:
                continue
            parts = shlex.split(raw)
            cmd, a = parts[0], parts[1:]
            if cmd in ("quit", "q", "exit"):
                return 0
            if cmd in ("help", "h", "?"):
                print(_HELP)
                continue
            aliases = {"s": "step", "c": "continue", "i": "inspect", "f": "field"}
            cmd = aliases.get(cmd, cmd)
            handler = getattr(self, f"cmd_{cmd}", None)
            if handler is None:
                print(f"未知命令 {cmd!r}（help 查命令）")
                continue
            try:
                handler(a)
            except (ValueError, KeyError, RuntimeError) as e:
                print(f"✗ {e}")
            if self.ctl.done:
                print("· 战斗已结束（quit 退出）")


def _cmd_debug(args: argparse.Namespace) -> int:
    compiled = _load_compiled(args.build, args.stage)
    engine = CombatEngine.from_compiled(compiled, mode=args.mode, seed=args.seed)
    ctl = DebugController(
        engine,
        enable_rewind=not args.no_rewind,
        checkpoint_interval=args.checkpoint_interval,
    )
    return _Repl(ctl).run()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="hsr-sim", description="翁法罗斯战斗模拟器 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "debug"):
        p = sub.add_parser(name)
        p.add_argument("build", help="build.yaml（编队+配装+策略）")
        p.add_argument("stage", help="stage.yaml（敌人+关卡）")
        p.add_argument("--mode", default=MODE_EXPECTED, choices=[MODE_EXPECTED, MODE_ROLL])
        p.add_argument("--seed", type=int, default=None)
    sub.choices["run"].add_argument("--log", action="store_true", help="附全战斗日志")
    sub.choices["debug"].add_argument("--no-rewind", action="store_true", help="关闭回退（不存轨迹与检查点）")
    sub.choices["debug"].add_argument("--checkpoint-interval", type=int,
                                      default=DEFAULT_CHECKPOINT_INTERVAL, help="检查点间隔（每 N 动一档）")
    args = parser.parse_args(argv)
    return _cmd_run(args) if args.cmd == "run" else _cmd_debug(args)


if __name__ == "__main__":
    raise SystemExit(main())
