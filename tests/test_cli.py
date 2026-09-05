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


# ---------------------------------------------------------------------------
# v3 启动界面：--config 与裸命令配置选择器
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from hsr_nous.sim import battles as _battles  # noqa: E402


@pytest.fixture
def battles_dir(tmp_path, monkeypatch):
    """配置库隔离到 tmp，并预存一个 inline 配置（ascii 名排头，选择器里编号恒为 1）。"""
    d = tmp_path / "battles"
    monkeypatch.setattr(_battles, "BATTLES_DIR", d)
    _battles.save_battle(
        "aaa_测试局", "CLI 测试配置",
        yaml.safe_dump(HERO_YAML, allow_unicode=True),
        yaml.safe_dump(STAGE_YAML, allow_unicode=True))
    return d


def test_config_mutex_with_positionals(battles_dir, tmp_path):
    """--config 与位置参数同给 → argparse 报错退出（SystemExit 2）。"""
    build, stage = _write_yamls(tmp_path)
    for cmd in ("run", "debug", "web"):
        with pytest.raises(SystemExit) as e:
            main([cmd, build, stage, "--config", "aaa_测试局"])
        assert e.value.code == 2
    # run/debug 两者皆无也报错；web 无参合法（空会话进大厅）
    for cmd in ("run", "debug"):
        with pytest.raises(SystemExit):
            main([cmd])


def test_config_unknown_name_errors(battles_dir):
    with pytest.raises(SystemExit) as e:
        main(["run", "--config", "不存在"])
    assert e.value.code == 2


def test_run_with_config(battles_dir, capsys):
    """--config 直达：从库取局跑完出战报（与位置参数路径等价）。"""
    assert main(["run", "--config", "aaa_测试局"]) == 0
    out = capsys.readouterr().out
    assert "总伤害" in out and "黄泉" in out


def test_bare_pick_selector_run(battles_dir, capsys, monkeypatch):
    """裸命令启动界面：列配置 → 选编号 1 → 回车默认 run → 出战报。"""
    _feed_inputs(monkeypatch, ["1", ""])
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "[1] aaa_测试局" in out and "队伍：黄泉" in out  # 选择器列出了库内配置（含预览）
    assert "总伤害" in out


def test_bare_pick_selector_by_name_and_debug(battles_dir, capsys, monkeypatch):
    """按名字选 + d 进 debug REPL。"""
    _feed_inputs(monkeypatch, ["aaa_测试局", "d", "auto", "bar", "quit"])
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "· 开局：aaa_测试局" in out and '"eta"' in out  # 进 REPL 且 bar 输出了行动条


def test_bare_pick_selector_quit_and_bad_input(battles_dir, capsys, monkeypatch):
    _feed_inputs(monkeypatch, ["99", "q"])  # 越界编号 → 重问 → q 退出
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "无此配置" in out and "总伤害" not in out


def test_web_config_direct_vs_empty(battles_dir, monkeypatch):
    """web --config 直达（会话已载局）vs web 无参空会话（大厅）；run_server 截获 app 不起服务。"""
    import hsr_nous.sim.web as web_mod
    from fastapi.testclient import TestClient
    captured = {}
    monkeypatch.setattr(web_mod, "run_server", lambda app, port: captured.setdefault("app", app))
    assert main(["web", "--config", "aaa_测试局", "--no-open"]) == 0
    s = TestClient(captured["app"]).get("/api/state").json()
    assert s["loaded"] and set(s["actors"]) == {"hero", "enemy"}
    captured.clear()
    assert main(["web", "--no-open"]) == 0
    assert TestClient(captured["app"]).get("/api/state").json() == {"loaded": False, "pending": None}


def test_web_templates_flag(monkeypatch):
    """web --templates（可重复）：附加模板根按序透传进 battles 查找链；不带则复位为空。"""
    import hsr_nous.sim.web as web_mod
    monkeypatch.setattr(_battles, "EXTRA_TEMPLATE_ROOTS", [])  # 隔离全局（create_app 会写入）
    monkeypatch.setattr(web_mod, "run_server", lambda app, port: None)
    assert main(["web", "--templates", "tests/fixtures/templates",
                 "--templates", "other/root", "--no-open"]) == 0
    assert _battles.EXTRA_TEMPLATE_ROOTS == ["tests/fixtures/templates", "other/root"]
    assert main(["web", "--no-open"]) == 0
    assert _battles.EXTRA_TEMPLATE_ROOTS == []
