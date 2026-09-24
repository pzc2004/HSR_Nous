"""打标自检 harness（annotator.sh 的后端——审过的固定件，打标工只喂数据、本件不许 worker 改）.

用法：
  python3 scripts/annotator_check.py compile <template.yaml>
  python3 scripts/annotator_check.py smoke   <template.yaml> [max_av=300]

- compile：编译闸——单角色 build + 沙包 stage 全链编译（词表闸/静态校验/param()/资源闸全过一遍）
- smoke：编译 + 开战冒烟（fixed_av 截断局）：不炸、动数 >0、无异常退出
模板根查找链：模板所在目录 → tests/fixtures/templates → data/sim_templates（staging 直喂）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent

_STAGE_YAML = """stage:
  stage_id: annotator_probe
  enemies:
  - enemy_template: sandbag
    actor_id: enemy1
    name: 打标假人·壹
  - enemy_template: sandbag
    actor_id: enemy2
    name: 打标假人·贰
  termination:
    mode: fixed_av
    max_action_value: {max_av}
"""

_BUILD_YAML = """build:
  team:
    - character_template: '{cid}'
      level: 80
  policy:
    name: annotator_probe
    action_rules:
      - condition: energy >= max_energy
        action: ultimate
        priority: 90
      - condition: skill_points > 2
        action: skill
        priority: 50
      - condition: 'true'
        action: basic
        priority: 0
    parameters: {{}}
"""


def _load_template_id(template: Path) -> str:
    doc = yaml.safe_load(template.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not doc.get("actor_id"):
        raise SystemExit(f"模板缺 actor_id（或不是合法 YAML dict）：{template}")
    return str(doc["actor_id"])


def _compile(template: Path, max_av: float = 300.0):
    sys.path.insert(0, str(_ROOT / "src"))
    from hsr_nous.sim.compile import compile_encounter_yaml

    cid = _load_template_id(template)
    # 模板命中走 <root>/characters/<cid>_*.yaml 布局——给定文件先进临时 characters/ 布局，
    # 否则平铺路径会静默漏命中、被 data/sim_templates 生成骨架顶包（2026-09-09 dogfood 钓出）
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="annotator_check_"))
    (tmp / "characters").mkdir(parents=True, exist_ok=True)
    # 文件名强制 <cid>_ 前缀（命中 glob 是 <cid>_*——原名不带 cid 前缀会静默漏命中）
    shutil.copy(template, tmp / "characters" / f"{cid}_{template.name}")
    roots = [str(tmp), str(_ROOT / "tests/fixtures/templates"),
             str(_ROOT / "data/sim_templates")]
    return cid, compile_encounter_yaml(_BUILD_YAML.format(cid=cid),
                                       _STAGE_YAML.format(max_av=max_av), template_roots=roots)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    mode, template = argv[1], Path(argv[2]).resolve()
    if not template.is_file():
        print(f"模板不存在：{template}")
        return 2

    if mode == "compile":
        try:
            cid, compiled = _compile(template)
        except Exception as e:  # noqa: BLE001 —— 编译闸：炸什么报什么
            print(f"FAIL compile：{type(e).__name__}: {e}")
            return 1
        n_actions = sum(len(v) for v in compiled.actions_by_actor.items())
        n_hooks = len(compiled.hooks or [])
        print(f"PASS compile：{cid} 编译通过（行动块 {n_actions} 处，hook {n_hooks} 条）")
        return 0

    if mode == "smoke":
        max_av = float(argv[3]) if len(argv) > 3 else 300.0
        sys.path.insert(0, str(_ROOT / "src"))
        from hsr_nous.sim import CombatEngine, MODE_EXPECTED
        from hsr_nous.sim.compile import compile_encounter_yaml

        cid = _load_template_id(template)
        try:
            _, compiled = _compile(template, max_av=max_av)
            state = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=1).run()
        except Exception as e:  # noqa: BLE001
            print(f"FAIL smoke：{type(e).__name__}: {e}")
            return 1
        snap = state.snapshot()
        ok = snap["turn_count"] > 0
        print(("PASS" if ok else "FAIL") + " smoke：" + json.dumps({
            "char": cid, "turns": snap["turn_count"],
            "total_damage": round(snap["total_damage"], 1),
            "truncated": snap["truncated"]}, ensure_ascii=False))
        return 0 if ok else 1

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
