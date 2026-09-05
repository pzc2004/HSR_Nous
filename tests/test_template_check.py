"""template_check CLI 测试：合法输入全过 / 编译炸 compile_ok=False / 引擎炸 smoke_ok=False.

判级入口 `hsr_nous.sim.template_check.main` 在进程内直调（快），另有一条 `uv run python -m`
子进程用例钉死 annotator 消费的真实入口形态（stdout 单行 JSON + 退出码）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from hsr_nous.sim import template_check as tc
from tests._data_env import data_available, data_skip_reason

TINGYUN_TEMPLATE = Path("data/sim_templates/characters/1202_停云.yaml")

# 停云模板在 data/（gitignored）——无数据环境整类跳过（inline build 用例不受影响）
_NEEDS_DATA = pytest.mark.skipif(not data_available(), reason=data_skip_reason())


def _run_main(argv, capsys) -> dict:
    rc = tc.main(argv)
    out = capsys.readouterr().out.strip()
    payload = json.loads(out.splitlines()[-1])
    return rc, payload


@pytest.fixture()
def tmp_char_root():
    root = Path(tempfile.mkdtemp(prefix="template_check_test_"))
    (root / "characters").mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@_NEEDS_DATA
class TestCharacterIdForm:
    def test_valid_template_all_pass(self, capsys):
        rc, payload = _run_main(["--character-id", "1202"], capsys)
        assert rc == 0
        assert payload["compile_ok"] is True and payload["compile_error"] is None
        assert payload["smoke_ok"] is True and payload["smoke_error"] is None
        assert payload["turns"] > 0 and payload["total_damage"] > 0

    def test_compile_error_verdict(self, tmp_char_root, capsys):
        """模板引用未登记事件 → 编译期炸：compile_ok=False，冒烟不执行."""
        # 坏 hook 追加进现有 hooks 列表（活模板已有 hooks 块——文本拼接第二个
        # 顶级 hooks: 会撞"YAML 重复键不许静默覆盖"闸，测不到目标错误）
        doc = yaml.safe_load(TINGYUN_TEMPLATE.read_text(encoding="utf-8"))
        doc.setdefault("hooks", []).append({"event": "on_skill_used"})
        (tmp_char_root / "characters" / TINGYUN_TEMPLATE.name).write_text(
            yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        rc, payload = _run_main(
            ["--character-id", "1202", "--template-roots", str(tmp_char_root)], capsys)
        assert rc == 1
        assert payload["compile_ok"] is False
        assert "on_skill_used" in payload["compile_error"]
        assert payload["smoke_ok"] is False and payload["smoke_error"] is None

    def test_engine_error_verdict(self, tmp_char_root, capsys):
        """hook 数值槽引用运行期未定义字段：过编译白名单、跑战斗才炸 → smoke_ok=False."""
        doc = yaml.safe_load(TINGYUN_TEMPLATE.read_text(encoding="utf-8"))
        doc.setdefault("hooks", []).append({
            "event": "on_turn_start",
            "effects": [{"effect_type": "gain_energy", "target": "self",
                         "amount": "$self.no_such_field"}]})
        (tmp_char_root / "characters" / TINGYUN_TEMPLATE.name).write_text(
            yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
        rc, payload = _run_main(
            ["--character-id", "1202", "--template-roots", str(tmp_char_root)], capsys)
        assert rc == 1
        assert payload["compile_ok"] is True
        assert payload["smoke_ok"] is False
        assert "no_such_field" in payload["smoke_error"]


class TestBuildStageForm:
    def test_inline_build_stage_all_pass(self, tmp_path, capsys):
        build = {"build": {"team": [{
            "inline": True, "actor_id": "c1", "name": "测试员",
            "base_stats": {"hp": 3000, "atk": 1000, "def": 500, "spd": 120,
                           "max_energy": 100},
            "actions": [{"action_id": "b1", "name": "普攻", "action_type": "basic",
                         "target_type": "single", "damage_type": "fire",
                         "scaling": [{"atk": 1.0}], "toughness_dmg": 10}]}]}}
        stage = {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
             "max_toughness": 9999, "weakness": ["fire"]}],
            "termination": {"mode": "fixed_av", "max_action_value": 300}}}
        bp = tmp_path / "b.yaml"
        sp = tmp_path / "s.yaml"
        bp.write_text(yaml.safe_dump(build, allow_unicode=True), encoding="utf-8")
        sp.write_text(yaml.safe_dump(stage, allow_unicode=True), encoding="utf-8")
        rc, payload = _run_main(["--build", str(bp), "--stage", str(sp)], capsys)
        assert rc == 0
        assert payload["compile_ok"] is True and payload["smoke_ok"] is True
        assert payload["turns"] > 0 and payload["total_damage"] > 0

    def test_missing_input_pair_errors(self):
        with pytest.raises(SystemExit):
            tc.main(["--build", "b.yaml"])  # 只有 --build 没有 --stage → argparse error


@_NEEDS_DATA
class TestSubprocessEntry:
    def test_uv_run_module_form(self):
        """annotator 消费的真实形态：uv run python -m，stdout 单行 JSON + 退出码."""
        proc = subprocess.run(
            ["uv", "run", "python", "-m", "hsr_nous.sim.template_check",
             "--character-id", "1202"],
            capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[:300]
        lines = proc.stdout.strip().splitlines()
        assert len(lines) == 1, f"stdout 必须单行 JSON：{lines!r}"
        payload = json.loads(lines[0])
        assert payload["compile_ok"] is True and payload["smoke_ok"] is True
