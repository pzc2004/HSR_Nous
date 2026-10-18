#!/usr/bin/env python3
"""hsr-data 统一命令入口（P4）——三域数据更新与状态检查.

命令：
    hsr-data update [build|enemies|stages]   数据更新（缺省 = 三域全量）
    hsr-data check  [build|enemies|stages]   状态报告（不写入）

全局参数（对所有命令通用，无"仅此域有效"例外）：
    --incr        增量：远端快检只下变化文件；Fandom 爬虫默认跳过（--with-fandom 才跑）
    --ssh         git sparse-checkout 替代 HTTPS（国内直连慢时切换）
    --dry-run     只报告不写盘
    --data-dir    自定义数据目录（缺省 = paths.data_root()）
    --timeout     单文件下载超时（秒）
    --lang        StarRailRes 语言（缺省 = en+cn 双拉；指定则只拉该语言）

好用五条（设计验收）：零记忆全量一条 / check 状态可见 / 文件级断点能续 /
报错人话且单源失败不阻塞 / 通道 --ssh 可选。
旧命令 hsr-data-update 保留过渡（路由壳 pipeline/update.py，过渡一个版本）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

DOMAINS = ("build", "enemies", "stages")


# ---------------------------------------------------------------------------
# 远端快检（增量语义：HEAD 比对 ETag 与本地 manifest.etags——两源 CDN 均不给
# Last-Modified 但都给 ETag（内容哈希），实测钉死 2026-10-15）
# ---------------------------------------------------------------------------

def _remote_etag(url: str, timeout: float) -> Optional[str]:
    """HEAD 快检远端 ETag；不支持/失败 → None（保守列入下载）."""
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "HSR_Nous/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.headers.get("ETag")
    except Exception:
        return None


def _manifest_updated_at(manifest_path: Path) -> Optional[float]:
    """读本地 manifest 的 updated_at（ISO 字符串 → epoch 秒）."""
    try:
        text = json.loads(manifest_path.read_text(encoding="utf-8"))["updated_at"]
        from datetime import datetime, timezone
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _changed_files(url_of, files: List[str], manifest_path: Path,
                   timeout: float) -> List[str]:
    """增量快检：HEAD 比对各文件远端 ETag 与本地 manifest.etags，
    返回需下载的子集（manifest/etag 缺 → 保守列入下载——首跑后即有表）."""
    try:
        stored = dict(json.loads(manifest_path.read_text(encoding="utf-8")).get("etags") or {})
    except Exception:
        stored = {}
    changed: List[str] = []
    for f in files:
        remote_etag = _remote_etag(url_of(f), timeout)
        if remote_etag is None or stored.get(f) != remote_etag:
            changed.append(f)
    return changed


# ---------------------------------------------------------------------------
# 域更新实现（每域返回 {源: 状态行}；异常上抛给路由层统一人话化）
# ---------------------------------------------------------------------------

def _update_build(args) -> Dict[str, str]:
    """build 域：StarRailRes（en+cn 或指定 lang）+ 机制数值（tbgd 技能）+ Fandom 语义."""
    from hsr_nous.pipeline.build.update import CORE_FILES, _GITHUB_RAW_URL, run_update
    from hsr_nous.pipeline.paths import starrailres_dir

    out: Dict[str, str] = {}
    data_dir = args.data_dir
    langs = [args.lang] if args.lang else ["en", "cn"]
    rc = 0
    for lang in langs:
        files = None
        if args.incr:
            files = _changed_files(
                lambda f: _GITHUB_RAW_URL.format(index="index_new", lang=lang, filename=f),
                CORE_FILES,
                starrailres_dir() / "index_new" / lang / "manifest.json",
                args.timeout)
            print(f"  [incr] starrailres[{lang}]: {len(files)}/{len(CORE_FILES)} 件需更新")
            if not files:
                continue
        rc |= run_update(data_dir=data_dir, files=files, lang=lang,
                         timeout=args.timeout, dry_run=args.dry_run,
                         use_ssh=args.ssh)
    out["starrailres"] = "ok" if rc == 0 else "failed"

    from hsr_nous.pipeline import extract_tbgd_skills
    old_argv, rc2 = sys.argv, 0
    try:
        sys.argv = ["extract_tbgd_skills", "--data-dir", str(Path(data_dir).parent)]
        rc2 = extract_tbgd_skills.main()
    finally:
        sys.argv = old_argv
    out["tbgd_skill"] = "ok" if rc2 == 0 else "failed"

    if not args.incr or args.with_fandom:
        from hsr_nous.pipeline.build import semantic
        old_argv, rc3 = sys.argv, 0
        try:
            sys.argv = ["semantic", "--data-dir", str(Path(data_dir).parent)]
            rc3 = semantic.main()
        finally:
            sys.argv = old_argv
        out["fandom_semantic"] = "ok" if rc3 == 0 else "failed"
    else:
        out["fandom_semantic"] = "skipped(--incr)"
    return out


def _update_enemies(args) -> Dict[str, str]:
    """enemies 域：tbgd 五件 + theBowja 冻结源备料（一次性快照）+ Fandom 语义."""
    from hsr_nous.pipeline.enemies.update import TBGD_FILES, _GITLAB_RAW
    from hsr_nous.pipeline.enemies.update import run_update as tbgd_update
    from hsr_nous.pipeline.paths import turnbasedgamedata_dir

    out: Dict[str, str] = {}
    files = None
    if args.incr:
        files = _changed_files(
            lambda f: _GITLAB_RAW.format(filename=f),
            TBGD_FILES,
            turnbasedgamedata_dir() / "manifest.json",
            args.timeout)
        print(f"  [incr] tbgd: {len(files)}/{len(TBGD_FILES)} 件需更新")
        if not files:
            out["tbgd"] = "ok"
            files = None  # 标完成——跳过下载段
    if files is not None or not args.incr:
        rc = tbgd_update(data_dir=str(turnbasedgamedata_dir()), files=files,
                         timeout=args.timeout, dry_run=args.dry_run)
        out["tbgd"] = "ok" if rc == 0 else "failed"

    from hsr_nous.pipeline.update import download_enemies
    rc2 = download_enemies(data_dir=str(Path(args.data_dir).parent),
                           timeout=args.timeout, dry_run=args.dry_run,
                           use_ssh=args.ssh)
    out["theBowja(冻结备料)"] = "ok" if rc2 == 0 else "failed"

    if not args.incr or args.with_fandom:
        from hsr_nous.pipeline.enemies import semantic as enemies_semantic
        old_argv, rc3 = sys.argv, 0
        try:
            sys.argv = ["enemies_semantic", "--data-dir", str(Path(args.data_dir).parent)]
            rc3 = enemies_semantic.main()
        finally:
            sys.argv = old_argv
        out["fandom_semantic"] = "ok" if rc3 == 0 else "failed"
    else:
        out["fandom_semantic"] = "skipped(--incr)"
    return out


def _update_stages(args) -> Dict[str, str]:
    """stages 域：Hakushin + buhflipexplode 期数（红线过滤；断点=文件级 identical）."""
    from hsr_nous.pipeline.stages.update import run as stages_run

    rc = stages_run(data_dir=str(Path(args.data_dir).parent),
                    timeout=args.timeout, dry_run=args.dry_run)
    return {"hakushin+buh": "ok" if rc == 0 else "failed"}


# ---------------------------------------------------------------------------
# 状态检查（check——只读不写）
# ---------------------------------------------------------------------------

def _fmt_ts(epoch: Optional[float]) -> str:
    if epoch is None:
        return "未知"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(epoch)) + "Z"


def _check_build(args) -> List[str]:
    from hsr_nous.pipeline.paths import (
        fandom_skill_path, starrailres_dir, tbgd_skill_path,
    )
    from hsr_nous.pipeline.build.update import _GITHUB_RAW_URL

    lines = ["[build] 配装域（StarRailRes + 机制数值 + Fandom 语义）"]
    for lang in ("en", "cn"):
        mf = starrailres_dir() / "index_new" / lang / "manifest.json"
        local_ts = _manifest_updated_at(mf)
        lines.append(f"  starrailres[{lang}]: 本地下载于 "
                     f"{_fmt_ts(local_ts)}"
                     + ("" if mf.exists() else "（无 manifest——未下载或旧版）"))
        remote_etag = _remote_etag(
            _GITHUB_RAW_URL.format(index="index_new", lang=lang,
                                   filename="characters.json"), args.timeout)
        if remote_etag is None:
            lines.append("    远端快检不可达（或禁 HEAD）")
        else:
            try:
                stored = (json.loads(mf.read_text(encoding="utf-8")).get("etags") or {}) \
                    .get("characters.json") if mf.exists() else None
            except Exception:
                stored = None
            lines.append(f"    characters.json: {'远端无变化（ETag 一致）' if stored == remote_etag else '远端有更新可拉（ETag 不同或无本地表）'}")
    for label, p in (("fandom_skill_data", fandom_skill_path()),
                     ("tbgd_skill_data", tbgd_skill_path())):
        pp = p
        lines.append(f"  {label}: {'存在 ' + time.strftime('%Y-%m-%d', time.gmtime(pp.stat().st_mtime)) if pp.exists() else '缺失'}")
    return lines


def _check_enemies(args) -> List[str]:
    from hsr_nous.pipeline.paths import enemies_dir, turnbasedgamedata_dir

    lines = ["[enemies] 敌人域（turnbasedgamedata 五表 + 引用 ConfigAI + theBowja 冻结备料）"]
    mf = turnbasedgamedata_dir() / "manifest.json"
    lines.append(f"  tbgd 五表 + 引用 ConfigAI: 本地下载于 {_fmt_ts(_manifest_updated_at(mf))}"
                 + ("" if mf.exists() else "（无 manifest——未下载）"))
    bowja = enemies_dir() / "enemies.json"
    lines.append(f"  theBowja（冻结保留）: "
                 f"{'存在 ' + time.strftime('%Y-%m-%d', time.gmtime(bowja.stat().st_mtime)) if bowja.exists() else '缺失（回退测试将 skip）'}")
    return lines


def _check_stages(args) -> List[str]:
    from hsr_nous.pipeline.paths import stages_dir

    lines = ["[stages] 期数域（Hakushin + buhflipexplode，红线过滤）"]
    mf = stages_dir() / "hakushin" / "_update_manifest.json"
    if mf.exists():
        m = json.loads(mf.read_text(encoding="utf-8"))
        lines.append(f"  本地下载于 {m.get('updated_at', '?')}；"
                     f"hakushin live 版本 = {m.get('hakushin_live_version', '?')}")
        counts = m.get("period_counts", {})
        lines.append(f"  期数: hakushin={sum((counts.get('hakushin') or {}).values())} details / "
                     f"buh={sum((counts.get('buhflipexplode') or {}).values())} phases")
        removed = m.get("redline_removed") or {}
        if removed:
            lines.append(f"  上次红线滤除 {len(removed)} 类："
                         + ", ".join(f"{k}×{len(v) if isinstance(v, list) else v}"
                                     for k, v in list(removed.items())[:5]))
        failures = m.get("failures") or []
        if failures:
            lines.append(f"  ⚠ 上次更新失败项：{', '.join(failures[:5])}")
    else:
        lines.append("  未下载（无 _update_manifest.json）")
    return lines


# ---------------------------------------------------------------------------
# 路由与人话报错
# ---------------------------------------------------------------------------

_UPDATERS = {"build": _update_build, "enemies": _update_enemies, "stages": _update_stages}
_CHECKERS = {"build": _check_build, "enemies": _check_enemies, "stages": _check_stages}


def _cmd_update(args) -> int:
    domains = [args.domain] if args.domain else list(DOMAINS)
    failed: List[str] = []
    for d in domains:
        print(f"\n=== [{d}] ===", flush=True)
        try:
            results = _UPDATERS[d](args)
        except Exception as exc:  # noqa: BLE001 —— 人话化，不给 stack trace
            print(f"[error] {d}: {type(exc).__name__}: {exc}（建议: 检查网络/"
                  f"数据源可用性后重跑——文件级断点，已落盘不重下）", file=sys.stderr)
            failed.append(d)
            continue
        for src, status in results.items():
            if status != "ok" and not status.startswith("skipped"):
                failed.append(f"{d}/{src}")
        for src, status in results.items():
            print(f"  [{status}] {src}", flush=True)
    if failed:
        print(f"\n[error] 失败源（数据保持旧版不半写，重跑只补失败源）: "
              f"{', '.join(failed)}", file=sys.stderr)
        return 1
    print("\n[ok] 全部源更新完成")
    return 0


def _cmd_check(args) -> int:
    domains = [args.domain] if args.domain else list(DOMAINS)
    for d in domains:
        try:
            for line in _CHECKERS[d](args):
                print(line)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {d} 状态读取失败: {exc}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="hsr-data",
        description="HSR_Nous 数据统一入口——三域（build/enemies/stages）更新与状态检查",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_global(p: argparse.ArgumentParser) -> None:
        p.add_argument("domain", nargs="?", choices=DOMAINS,
                       help="单域限定（缺省 = 三域全跑）")
        p.add_argument("--incr", action="store_true",
                       help="增量：远端快检只下变化；Fandom 爬虫默认跳过")
        p.add_argument("--with-fandom", action="store_true",
                       help="增量模式下也跑 Fandom 语义提取（爬虫）")
        p.add_argument("--ssh", action="store_true",
                       help="git sparse-checkout 替代 HTTPS（国内直连慢时切换）")
        p.add_argument("--dry-run", action="store_true", help="只报告不写盘")
        p.add_argument("--data-dir", default=None,
                       help="数据目录（缺省 = paths.starrailres_dir()；域内自行取父目录）")
        p.add_argument("--timeout", type=float, default=30.0)
        p.add_argument("--lang", default=None,
                       help="StarRailRes 语言（缺省 = en+cn 双拉；指定 en/cn 只拉一种）")

    p_update = sub.add_parser("update", help="数据更新（缺省三域全量）")
    _add_global(p_update)
    p_check = sub.add_parser("check", help="状态报告（不写入）")
    _add_global(p_check)

    args = parser.parse_args()
    from hsr_nous.pipeline.paths import starrailres_dir
    if args.data_dir is None:
        args.data_dir = str(starrailres_dir())

    if args.command == "update":
        return _cmd_update(args)
    return _cmd_check(args)


if __name__ == "__main__":
    raise SystemExit(main())
