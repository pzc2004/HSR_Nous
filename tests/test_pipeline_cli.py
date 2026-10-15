"""hsr-data 统一 CLI 测试（P4）：域路由 / 增量 ETag 快检 / 人话报错 / check 状态报告.

离线构造：域更新函数 monkeypatch 替换、HEAD 快检桩化、manifest tmp 写入——不触真网。
"""
from __future__ import annotations

import json
from argparse import Namespace
from typing import Dict, List

import pytest

from hsr_nous.pipeline import cli


def _args(**kw) -> Namespace:
    base = dict(command="update", domain=None, incr=False, with_fandom=False,
                ssh=False, dry_run=False, data_dir="/tmp/x", timeout=1.0, lang=None)
    base.update(kw)
    return Namespace(**base)


class TestDomainRouting:
    def test_update_all_domains_default(self, monkeypatch, capsys):
        """缺省 = 三域全跑（零 flag 记忆——好用五条①）."""
        calls: List[str] = []
        for d in cli.DOMAINS:
            monkeypatch.setitem(cli._UPDATERS, d,
                                lambda args, _d=d: calls.append(_d) or {"src": "ok"})
        assert cli._cmd_update(_args()) == 0
        assert calls == ["build", "enemies", "stages"]

    def test_update_single_domain(self, monkeypatch, capsys):
        calls: List[str] = []
        monkeypatch.setitem(cli._UPDATERS, "build",
                            lambda args: calls.append("build") or {"src": "ok"})
        assert cli._cmd_update(_args(domain="build")) == 0
        assert calls == ["build"]

    def test_domain_failure_does_not_block_others(self, monkeypatch, capsys):
        """单源失败不阻塞其它源落盘 + 人话报错（好用五条④）."""
        monkeypatch.setitem(cli._UPDATERS, "build",
                            lambda args: (_ for _ in ()).throw(OSError("network down")))
        monkeypatch.setitem(cli._UPDATERS, "enemies", lambda args: {"tbgd": "ok"})
        monkeypatch.setitem(cli._UPDATERS, "stages", lambda args: {"hakushin+buh": "ok"})
        assert cli._cmd_update(_args()) == 1
        err = capsys.readouterr().err
        assert "[error] build:" in err and "重跑只补失败源" in err

    def test_source_level_failure_collected(self, monkeypatch, capsys):
        """域内某源 failed（非 ok/skipped）计入失败清单."""
        monkeypatch.setitem(cli._UPDATERS, "build",
                            lambda args: {"starrailres": "failed", "tbgd_skill": "ok"})
        assert cli._cmd_update(_args(domain="build")) == 1
        assert "build/starrailres" in capsys.readouterr().err


class TestIncrEtagCheck:
    def test_changed_files_etag_match(self, tmp_path, monkeypatch):
        """ETag 一致 → 免下载；不一致/缺表/快检失败 → 列入下载."""
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps({"etags": {"a.json": '"aaa"', "b.json": '"bbb"'}}),
                      encoding="utf-8")
        monkeypatch.setattr(cli, "_remote_etag",
                            lambda url, timeout: {"a.json": '"aaa"',
                                                  "b.json": '"XXX"'}.get(url))
        got = cli._changed_files(lambda f: f, ["a.json", "b.json", "c.json"], mf, 1.0)
        assert got == ["b.json", "c.json"]   # b=远端变了 / c=快检失败(None)保守列入

    def test_changed_files_no_manifest_full_download(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "_remote_etag", lambda url, timeout: '"x"')
        got = cli._changed_files(lambda f: f, ["a.json"], tmp_path / "nope.json", 1.0)
        assert got == ["a.json"]   # 无 manifest 保守全量

    def test_changed_files_head_failure_conservative(self, tmp_path, monkeypatch):
        mf = tmp_path / "manifest.json"
        mf.write_text(json.dumps({"etags": {"a.json": '"aaa"'}}), encoding="utf-8")
        monkeypatch.setattr(cli, "_remote_etag", lambda url, timeout: None)
        assert cli._changed_files(lambda f: f, ["a.json"], mf, 1.0) == ["a.json"]


class TestCheckCommand:
    def test_check_all_domains(self, monkeypatch, capsys):
        for d in cli.DOMAINS:
            monkeypatch.setitem(cli._CHECKERS, d, lambda args, _d=d: [f"[{_d}] ok"])
        assert cli._cmd_check(_args(command="check")) == 0
        out = capsys.readouterr().out
        assert "[build] ok" in out and "[enemies] ok" in out and "[stages] ok" in out

    def test_check_stages_reads_manifest(self, tmp_path, monkeypatch, capsys):
        """stages check：读 _update_manifest.json 输出 live 版本/期数/红线滤除."""
        hak = tmp_path / "hakushin"
        hak.mkdir(parents=True)
        (hak / "_update_manifest.json").write_text(json.dumps({
            "updated_at": "2026-10-15T00:00:00Z",
            "hakushin_live_version": "4.6",
            "period_counts": {"hakushin": {"maze": 90}, "buhflipexplode": {"fh": 98}},
            "redline_removed": {"fh-versions.json": ["x"]},
            "failures": [],
        }), encoding="utf-8")
        monkeypatch.setattr(cli, "_CHECKERS", {
            **cli._CHECKERS,
            "stages": lambda args: cli._check_stages(args),
        })
        from hsr_nous.pipeline import paths
        monkeypatch.setattr(paths, "stages_dir", lambda: tmp_path)
        # _check_stages 内部 from paths import stages_dir——monkeypatch 模块属性
        import hsr_nous.pipeline.cli as cli_mod
        monkeypatch.setitem(cli._CHECKERS, "stages", cli_mod._check_stages)
        monkeypatch.setattr("hsr_nous.pipeline.paths.stages_dir", lambda: tmp_path)
        assert cli._cmd_check(_args(command="check", domain="stages")) == 0
        out = capsys.readouterr().out
        assert "4.6" in out and "hakushin=90" in out and "buh=98" in out


class TestFandomGating:
    def test_incr_skips_fandom_by_default(self, monkeypatch):
        """--incr 默认跳过 Fandom 爬虫（真身门控：not incr or with_fandom）."""
        called: List[str] = []
        monkeypatch.setattr("hsr_nous.pipeline.enemies.semantic.main",
                            lambda: called.append("fandom") or 0)
        from hsr_nous.pipeline.enemies import update as enemies_update
        from hsr_nous.pipeline import update as router_update
        monkeypatch.setattr(enemies_update, "run_update", lambda **kw: 0)
        monkeypatch.setattr(router_update, "download_enemies", lambda **kw: 0)
        cli._UPDATERS["enemies"](_args(domain="enemies", incr=True))
        assert called == [], "--incr 默认不应触发 fandom 爬虫"

    def test_with_fandom_overrides_incr(self, monkeypatch):
        called: List[str] = []
        monkeypatch.setattr("hsr_nous.pipeline.enemies.semantic.main",
                            lambda: called.append("fandom") or 0)
        from hsr_nous.pipeline.enemies import update as enemies_update
        from hsr_nous.pipeline import update as router_update
        monkeypatch.setattr(enemies_update, "run_update", lambda **kw: 0)
        monkeypatch.setattr(router_update, "download_enemies", lambda **kw: 0)
        cli._UPDATERS["enemies"](_args(domain="enemies", incr=True, with_fandom=True))
        assert called == ["fandom"], "--with-fandom 应在 --incr 下也跑 fandom"
