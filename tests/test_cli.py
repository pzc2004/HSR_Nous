"""hsr-sim CLI 冒烟测试：run 出报 / debug REPL 命令调度."""

import yaml

from hsr_nous.sim.cli import main

HERO_YAML = {
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "黄泉",
            "level": 80,
            "base_stats": {
                "atk": 3000, "spd": 134, "hp": 1200, "max_energy": 110,
                "crit_rate": 0.5, "crit_dmg": 1.0,
            },
            "actions": [{
                "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "thunder",
                "scaling": [{"atk": 1.0}],
            }],
        }],
        "policy": {
            "name": "default",
            "action_rules": [
                {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                {"condition": "true", "action": "basic", "priority": 0},
            ],
            "target_rules": [],
            "parameters": {},
        },
    }
}

STAGE_YAML = {
    "stage": {
        "stage_id": "dummy_150",
        "enemies": [{
            "actor_id": "enemy", "name": "假人", "level": 80,
            "hp": 1_000_000_000, "spd": 100, "weakness": ["thunder"],
        }],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }
}


def _write_yamls(tmp_path):
    build = tmp_path / "build.yaml"
    stage = tmp_path / "stage.yaml"
    build.write_text(yaml.safe_dump(HERO_YAML, allow_unicode=True), encoding="utf-8")
    stage.write_text(yaml.safe_dump(STAGE_YAML, allow_unicode=True), encoding="utf-8")
    return str(build), str(stage)


def test_run_report(tmp_path, capsys):
    build, stage = _write_yamls(tmp_path)
    assert main(["run", build, stage, "--log"]) == 0
    out = capsys.readouterr().out
    assert "总伤害" in out and "黄泉" in out and "战斗日志" in out


def _feed_inputs(monkeypatch, inputs):
    it = iter(inputs)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError  # 输入耗尽 = Ctrl-D

    monkeypatch.setattr("builtins.input", fake_input)


def test_repl_auto_flow(tmp_path, capsys, monkeypatch):
    """auto 模式下的检视类命令全流程：step/bar/trace/back/goto/field/inspect/snapshot."""
    build, stage = _write_yamls(tmp_path)
    _feed_inputs(monkeypatch, [
        "auto",          # 交还编译策略（不再消耗决策输入）
        "step", "bar", "trace 5", "back", "goto 2",
        "field", "inspect 黄泉", "inspect hero", "snapshot", "break turn 2",
        "breaks", "clear", "continue", "quit",
    ])
    assert main(["debug", build, stage]) == 0
    out = capsys.readouterr().out
    assert '"eta"' in out  # bar 输出行动条 JSON
    assert '"actor_id": "hero"' in out  # inspect 命中（中文名与 id 两种寻址都过）


def test_repl_manual_decision(tmp_path, capsys, monkeypatch):
    """manual 默认：决策点停下来问编号，回车默认 [0]."""
    build, stage = _write_yamls(tmp_path)
    _feed_inputs(monkeypatch, ["step", "", "quit"])  # 首步即 hero 决策点，回车选 [0]
    assert main(["debug", build, stage]) == 0
    out = capsys.readouterr().out
    assert "决策点" in out and "[0] 普攻" in out


def test_repl_unknown_command_and_eof(tmp_path, capsys, monkeypatch):
    build, stage = _write_yamls(tmp_path)
    _feed_inputs(monkeypatch, ["foobar"])  # 随后输入耗尽 = Ctrl-D 退出
    assert main(["debug", build, stage]) == 0
    assert "未知命令" in capsys.readouterr().out
