"""hsr-nous 项目级 CLI：config 子命令（热更配置查看，api 层真 import 路径常量）."""

import json

from hsr_nous.api.cli import main


class TestConfigCmd:
    def test_config_prints_live_file(self, tmp_path, monkeypatch, capsys):
        import hsr_nous.api.cli as cli
        f = tmp_path / "annotator_live_config.json"
        f.write_text(json.dumps(
            {"api_base": "http://ep", "model": "m", "effort": "max", "concurrency": 7}),
            encoding="utf-8")
        monkeypatch.setattr(cli, "DEFAULT_LIVE_CONFIG_PATH", f)
        assert main(["config"]) == 0
        out = capsys.readouterr().out
        assert str(f) in out and "http://ep" in out and "concurrency: 7" in out

    def test_config_missing_file(self, tmp_path, monkeypatch, capsys):
        import hsr_nous.api.cli as cli
        monkeypatch.setattr(cli, "DEFAULT_LIVE_CONFIG_PATH", tmp_path / "nope.json")
        assert main(["config"]) == 0
        assert "不存在" in capsys.readouterr().out
