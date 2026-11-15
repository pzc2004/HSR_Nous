"""真实队伍全决策世界线构造件。"""
from __future__ import annotations

import yaml

from hsr_nous.common import repo_data_dir
from hsr_nous.research.core import WorldlineRunner, derive_child_spec
from hsr_nous.research.schema import WorldlineSpec


def make_acheron_worldline_parts():
    path = repo_data_dir() / "battles" / "demo_黄泉队.yaml"
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    build = yaml.safe_load(record["build_yaml"])
    stage = yaml.safe_load(record["stage_yaml"])
    build["build"]["policy"] = {
        "mode": "scripted",
        "ult_timing": "scripted",
        "script": [
            {"turn": 3, "actor": "1304", "action": "130402"},
            {"turn": 4, "actor": "1308", "action": "130801", "target": "enemy1"},
            {"turn": 5, "actor": "1403", "action": "140302"},
            {"turn": 9, "actor": "1304", "action": "130402"},
            {"turn": 10, "actor": "1308", "action": "130801", "target": "enemy1"},
            {"turn": 11, "actor": "1403", "action": "140302"},
            {"turn": 15, "actor": "1304", "action": "130402"},
            {"turn": 16, "actor": "1308", "action": "130801", "target": "enemy1"},
        ],
        "ultimate_script": [
            {"turn": 1, "window": "after_action", "actor": "1403", "action": "skip"},
            {"turn": 2, "window": "after_action", "actor": "1403", "action": "skip"},
            {"turn": 3, "window": "before_action", "actor": "1304", "action": "skip"},
            {"turn": 3, "window": "after_action", "actor": "1304", "action": "130403",
             "target": "enemy1"},
            {"turn": 3, "window": "after_action", "actor": "1403", "action": "skip"},
            {"turn": 4, "window": "before_action", "actor": "1403", "action": "skip"},
            {"turn": 4, "window": "after_action", "actor": "1403", "action": "skip"},
            {"turn": 5, "window": "before_action", "actor": "1403", "action": "skip"},
            {"turn": 5, "window": "after_action", "actor": "1403", "action": "140303"},
            {"turn": 5, "window": "after_action", "actor": "1308", "action": "skip"},
            {"turn": 6, "window": "after_action", "actor": "1308", "action": "skip"},
            {"turn": 7, "window": "after_action", "actor": "1308", "action": "skip"},
            {"turn": 8, "window": "after_action", "actor": "1308", "action": "skip"},
            {"turn": 9, "window": "before_action", "actor": "1308", "action": "skip"},
            {"turn": 9, "window": "after_action", "actor": "1308", "action": "skip"},
            {"turn": 10, "window": "before_action", "actor": "1308", "action": "skip"},
            {"turn": 10, "window": "after_action", "actor": "1308", "action": "130803"},
        ],
    }
    return build, stage, [0.99] * 92


def make_completed_and_failed_worldlines(store):
    build, stage, values = make_acheron_worldline_parts()
    runner = WorldlineRunner(store=store)
    parent = runner.run(WorldlineSpec(
        build, stage, tuple(values), initial_sp=5, initial_energy_ratio=1.0
    ))
    broken_script = [dict(entry) for entry in
                     parent.spec.build["build"]["policy"]["script"]]
    broken_script[0]["turn"] = 999
    child = runner.run(derive_child_spec(
        parent, script=broken_script, note="故意破坏普通行动脚本以验证失败展示"
    ))
    assert parent.status == "completed"
    assert child.status == "failed"
    return parent, child
