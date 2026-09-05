"""`hsr-sim` 命令行入口（名册代号 aquila/天空泰坦——边界层：一切出入口归它；泰坦名只活文档，不进标识符）.

- `hsr-sim`：启动界面（终端配置选择器）——列配置库（`battles.py`）→ 选配置 → 选 run/debug 开始
- `hsr-sim run <build.yaml> <stage.yaml>`：一把梭跑完整场，出战报
- `hsr-sim debug <build.yaml> <stage.yaml>`：交互调试（单步/断点/检视/回退/手动选行动）
- `hsr-sim web <build.yaml> <stage.yaml>`：本地网页调试台（FastAPI 单页应用，复用同一台 DebugController）；
  无参 → 空会话落 `#/home` 大厅；`--templates DIR`（可重复）指定附加模板根，
  优先级高于默认 data/sim_templates（如人工全机制锚模板压生成骨架）
- run/debug/web 均可用 `--config <名字>` 直接选库内配置（与位置参数互斥）

本层是纯壳：解析命令 → 调 `DebugController`/引擎 → 打印，不含任何战斗逻辑。
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.sim import CombatEngine, DebugController, MODE_EXPECTED, MODE_ROLL
from hsr_nous.sim.battles import list_battles, load_battle
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


def _resolve_yamls(args: argparse.Namespace, parser: argparse.ArgumentParser):
    """--config / 位置参数 → (build_yaml, stage_yaml)；互斥同给报错退出；都不给 → (None, None)."""
    if args.config and (args.build or args.stage):
        parser.error("--config 与位置参数 build/stage 互斥，二选一")
    if args.config:
        try:
            return load_battle(args.config)
        except (KeyError, ValueError) as e:
            parser.error(str(e))
    if bool(args.build) != bool(args.stage):
        parser.error("build 与 stage 须成对给出")
    if args.build:
        return (Path(args.build).read_text(encoding="utf-8"),
                Path(args.stage).read_text(encoding="utf-8"))
    return None, None


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# run：一把梭
# ---------------------------------------------------------------------------

def _cmd_run(args: argparse.Namespace, build_yaml: str, stage_yaml: str) -> int:
    compiled = compile_encounter_yaml(build_yaml, stage_yaml)
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
        print("翁法罗斯 · 调试控制器（oronyx/岁月泰坦）——单步/断点/检视/回退，help 查命令，quit 退出")
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


def _cmd_debug(args: argparse.Namespace, build_yaml: str, stage_yaml: str) -> int:
    compiled = compile_encounter_yaml(build_yaml, stage_yaml)
    engine = CombatEngine.from_compiled(compiled, mode=args.mode, seed=args.seed)
    ctl = DebugController(
        engine,
        enable_rewind=not args.no_rewind,
        checkpoint_interval=args.checkpoint_interval,
    )
    return _Repl(ctl).run()


# ---------------------------------------------------------------------------
# web：本地网页调试台
# ---------------------------------------------------------------------------

def _cmd_web(args: argparse.Namespace, build_yaml: Optional[str], stage_yaml: Optional[str]) -> int:
    """起本地 FastAPI 网页端（延迟 import：fastapi/uvicorn 是 [web] 可选依赖）。"""
    try:
        from hsr_nous.sim.web import create_app, run_server
    except ImportError:
        print("缺少网页端依赖：uv pip install -e \".[web]\"", file=sys.stderr)
        return 1
    app = create_app(build_yaml, stage_yaml, mode=args.mode, seed=args.seed,
                     extra_template_roots=args.templates)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    landing = "直达战斗（已带局）" if build_yaml is not None else "大厅（空会话）"
    print(f"翁法罗斯网页调试台：{url}（{landing}，Ctrl-C 停止）")
    run_server(app, args.port)
    return 0


# ---------------------------------------------------------------------------
# 裸命令：终端配置选择器（启动界面）
# ---------------------------------------------------------------------------

def _read(prompt: str) -> Optional[str]:
    """读一行输入；EOF/Ctrl-C → None（退出选择器）。"""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _cmd_pick() -> int:
    """无子命令：列配置库 → 选配置（编号/名字）→ 选 run/debug → 开始；q 退出。"""
    entries = list_battles()
    print("翁法罗斯 · 战斗配置库（data/battles）")
    for i, e in enumerate(entries, 1):
        print(f"  [{i}] {e['name']}——{e['description']}")
        print(f"      队伍：{'、'.join(e['team_preview']) or '—'} ｜ 关卡：{'、'.join(e['stage_preview']) or '—'}")
    if not entries:
        print("  （库为空——可用 hsr-sim web 大厅保存自定义配置）")
    while True:
        raw = _read("选择编号或名字（q 退出）：")
        if raw is None or raw.lower() in ("", "q", "quit", "exit"):
            return 0
        entry = entries[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(entries) \
            else next((e for e in entries if e["name"] == raw), None)
        if entry is not None:
            break
        print(f"✗ 无此配置 {raw!r}")
    how = _read("run 还是 debug？[r/d]（回车=r）：")
    if how is None:
        return 0
    build_yaml, stage_yaml = load_battle(entry["name"])
    args = argparse.Namespace(mode=MODE_EXPECTED, seed=None, log=False,
                              no_rewind=False, checkpoint_interval=DEFAULT_CHECKPOINT_INTERVAL)
    print(f"· 开局：{entry['name']}")
    if how.lower() in ("d", "debug"):
        return _cmd_debug(args, build_yaml, stage_yaml)
    return _cmd_run(args, build_yaml, stage_yaml)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="hsr-sim", description="翁法罗斯战斗模拟器 CLI")
    sub = parser.add_subparsers(dest="cmd")  # 无子命令 → 终端配置选择器
    for name in ("run", "debug", "web"):
        p = sub.add_parser(name)
        p.add_argument("build", nargs="?", help="build.yaml（编队+配装+策略）")
        p.add_argument("stage", nargs="?", help="stage.yaml（敌人+关卡）")
        p.add_argument("--config", default=None,
                       help="配置库（data/battles）中的配置名，与位置参数互斥")
        p.add_argument("--mode", default=MODE_EXPECTED, choices=[MODE_EXPECTED, MODE_ROLL])
        p.add_argument("--seed", type=int, default=None)
    sub.choices["run"].add_argument("--log", action="store_true", help="附全战斗日志")
    sub.choices["debug"].add_argument("--no-rewind", action="store_true", help="关闭回退（不存轨迹与检查点）")
    sub.choices["debug"].add_argument("--checkpoint-interval", type=int,
                                      default=DEFAULT_CHECKPOINT_INTERVAL, help="检查点间隔（每 N 动一档）")
    sub.choices["web"].add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    sub.choices["web"].add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    sub.choices["web"].add_argument("--templates", action="append", default=[], metavar="DIR",
                                    help="额外模板根目录，优先于默认 data/sim_templates（可重复），"
                                         "例：--templates tests/fixtures/templates")
    args = parser.parse_args(argv)
    if args.cmd is None:
        return _cmd_pick()
    build_yaml, stage_yaml = _resolve_yamls(args, parser)
    if args.cmd in ("run", "debug") and build_yaml is None:
        parser.error(f"{args.cmd} 需要 <build> <stage> 或 --config <名字>")
    if args.cmd == "run":
        return _cmd_run(args, build_yaml, stage_yaml)
    if args.cmd == "debug":
        return _cmd_debug(args, build_yaml, stage_yaml)
    return _cmd_web(args, build_yaml, stage_yaml)  # web：两者皆可 None（空会话进大厅）


if __name__ == "__main__":
    raise SystemExit(main())
