"""模板校验 CLI：编译 + 行为冒烟（sim 域内校验入口，供外层子进程调用）.

定位：adapters 域的机制标注流水线（`adapters/mechanism_annotator.py`）等**开发期数据生产
工具**需要"模板可编译 + 组假人队跑战斗不炸"的判级能力，但模块边界禁止它们 import sim——
本 CLI 把该能力收敛在 sim 域内，调用方以子进程方式消费：

    python -m hsr_nous.sim.template_check --build build.yaml --stage stage.yaml
    python -m hsr_nous.sim.template_check --character-id 1202 [--template-roots 根 [根...]] \
        [--mode expected] [--seed 42]

stdout 单行 JSON（唯一结果通道）：

    {"compile_ok": bool, "compile_error": str|null,
     "smoke_ok": bool, "smoke_error": str|null,
     "turns": int, "total_damage": float}

退出码：compile_ok 且 smoke_ok → 0，否则 1（JSON 照常打印，调用方解析 stdout 判级）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED, MODE_ROLL

__all__ = ["check", "smoke_build_stage", "main"]

_MODES = {"expected": MODE_EXPECTED, "roll": MODE_ROLL}

#: 冒烟战斗长度（AV）——假人队冒烟只要求机制全链跑通，不需要长盘
SMOKE_MAX_AV = 750


def smoke_build_stage(char_id: str, *, max_av: int = SMOKE_MAX_AV) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """最小冒烟配置：该角色（模板引用）+ inline 假人队友 vs inline 全弱点假人.

    inline 敌人不带 actions——引擎按"行动（占位）"空过；敌人全弱点让击破链可触发；
    策略有战技点放战技否则普攻，终结技按缺省 after_action 自动开。
    """
    build = {
        "build": {
            "team": [
                {"character_template": str(char_id), "level": 80},
                {
                    "inline": True,
                    "actor_id": "dummy_ally",
                    "name": "假人队友",
                    "actor_type": "character",
                    "base_stats": {"hp": 3000, "atk": 1000, "def": 800, "spd": 95,
                                   "max_energy": 100},
                    "actions": [{
                        "action_id": "dummy_basic", "name": "普攻", "action_type": "basic",
                        "target_type": "single", "damage_type": "physical",
                        "scaling": [{"atk": 1.0}], "toughness_dmg": 10, "energy_gain": 20,
                    }],
                },
            ],
            "policy": {"name": "smoke", "action_rules": [
                {"condition": "skill_points > 0", "action": "skill", "priority": 1},
                {"condition": "true", "action": "basic", "priority": 0},
            ]},
        },
    }
    stage = {
        "stage": {
            "stage_id": "smoke",
            "enemies": [{
                "actor_id": "dummy_enemy", "name": "假人", "hp": 1e9, "atk": 100, "def": 500,
                "spd": 50, "max_toughness": 99999,
                "weakness": ["physical", "fire", "ice", "thunder", "wind", "quantum",
                             "imaginary"],
            }],
            "termination": {"mode": "fixed_av", "max_action_value": max_av},
        },
    }
    return build, stage


def check(
    build: Dict[str, Any],
    stage: Dict[str, Any],
    *,
    mode: str = MODE_EXPECTED,
    seed: Optional[int] = 42,
    template_roots: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """编译 + 冒烟判级。任何异常都吞进结果 JSON（调用方靠 ok 字段判级，不靠异常）."""
    result: Dict[str, Any] = {
        "compile_ok": False, "compile_error": None,
        "smoke_ok": False, "smoke_error": None,
        "turns": 0, "total_damage": 0.0,
    }
    try:
        compiled = compile_encounter(build, stage, template_roots=template_roots)
    except Exception as e:  # 编译异常文本 = 调用方自愈重试的反馈素材
        result["compile_error"] = f"{type(e).__name__}: {e}"
        return result
    result["compile_ok"] = True
    try:
        eng = CombatEngine.from_compiled(compiled, mode=mode, seed=seed,
                                         initial_energy_ratio=0.0)
        eng.setup()
        state = eng.run()
    except Exception as e:
        result["smoke_error"] = f"{type(e).__name__}: {e}"
        return result
    result["smoke_ok"] = True
    result["turns"] = state.turn_count
    result["total_damage"] = state.total_damage
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="template_check",
        description="模板校验：编译 + 假人队行为冒烟，stdout 单行 JSON 判级")
    p.add_argument("--build", metavar="PATH", help="build.yaml 路径（与 --stage 成对）")
    p.add_argument("--stage", metavar="PATH", help="stage.yaml 路径（与 --build 成对）")
    p.add_argument("--character-id", metavar="ID",
                   help="角色模板 id：包进最小 build（它+inline 假人队友）+ inline 全弱点假人")
    p.add_argument("--template-roots", nargs="+", default=None, metavar="ROOT",
                   help="模板根（有序，先命中生效；缺省 = 生产缺省 data/sim_templates）")
    p.add_argument("--mode", choices=sorted(_MODES), default="expected",
                   help="结算模式（默认 %(default)s，期望模式确定性）")
    p.add_argument("--seed", type=int, default=42, help="随机种子（默认 %(default)s）")
    args = p.parse_args(argv)

    roots = [str(r) for r in args.template_roots] if args.template_roots else None
    if args.character_id:
        build, stage = smoke_build_stage(str(args.character_id))
    elif args.build and args.stage:
        build = yaml.safe_load(Path(args.build).read_text(encoding="utf-8"))
        stage = yaml.safe_load(Path(args.stage).read_text(encoding="utf-8"))
    else:
        p.error("--build + --stage 成对，或 --character-id，必给其一")
    result = check(build, stage, mode=_MODES[args.mode], seed=args.seed, template_roots=roots)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["compile_ok"] and result["smoke_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
