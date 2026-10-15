#!/usr/bin/env python3
"""hsr-data-update 统一入口（路由壳）——P1 三域归置后按域分发.

- 默认/--lang/--files：build 域（StarRailRes 角色/光锥/遗器，真身 build/update.py）
- --enemies：敌人数据（theBowja 遗留源——P2 迁 enemies 域）
- --stages：期数编成（Hakushin + buhflipexplode，真身 stages/update.py）
- --mechanics：技能机制数值提取（extract_tbgd_skills——P2 迁 enemies 域）

P4 收编为 hsr-data 统一命令（全量/增量/单域/check），本壳保留旧命令形态过渡。
"""

import argparse
import json
import shutil
import sys
import urllib.error
from pathlib import Path
from typing import List, Optional

from hsr_nous.pipeline.build.update import (
    CORE_FILES,
    _HAKUSHIN_BASE_URL,
    _check_release_alignment,
    _git_sparse_clone,
    download_file,
    run_update,
)

__all__ = ["run_update", "download_enemies", "main"]

# theBowja/starrail-data 仓库的敌人数据
_ENEMY_DATA_URL = (
    "https://raw.githubusercontent.com/theBowja/starrail-data/main/data/CHS/enemies.json"
)


def _default_data_dir() -> Path:
    from hsr_nous.pipeline.paths import starrailres_dir
    return starrailres_dir()


def download_enemies(
    *,
    data_dir: str,
    timeout: float = 30.0,
    dry_run: bool = False,
    use_ssh: bool = False,
) -> int:
    """从 theBowja/starrail-data 下载敌人数据."""
    root = Path(data_dir)
    out_dir = root / "enemies"
    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / "enemies.json"

    if use_ssh:
        print("[ssh] cloning enemies data via SSH ...")
        repo_url = "git@github.com:theBowja/starrail-data.git"
        sparse_paths = ["data/CHS/enemies.json"]
        if not _git_sparse_clone(repo_url, sparse_paths, root, branch="main"):
            return 1
        # git sparse-clone 会放到 root/data/CHS/enemies.json，移到目标位置
        cloned = root / "data" / "CHS" / "enemies.json"
        if cloned.exists():
            shutil.move(str(cloned), str(local_path))
            shutil.rmtree(root / "data", ignore_errors=True)
            print(f"[updated] enemies.json: {local_path.stat().st_size} bytes")
        else:
            print("[error] enemies.json: not found after clone", file=sys.stderr)
            return 1
        return 0

    try:
        raw = download_file(_ENEMY_DATA_URL, timeout=timeout)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"[error] enemies.json: {exc}", file=sys.stderr)
        return 1

    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[error] enemies.json: invalid JSON - {exc}", file=sys.stderr)
        return 1

    if local_path.exists() and local_path.read_bytes() == raw:
        print("[skip] enemies.json: identical to local")
        return 0

    if dry_run:
        print(f"[would update] enemies.json: {len(raw)} bytes")
        return 0

    local_path.write_bytes(raw)
    print(f"[updated] enemies.json: {len(raw)} bytes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update StarRailRes data from Mar-7th/StarRailRes GitHub repository."
    )
    parser.add_argument(
        "--data-dir",
        default=str(_default_data_dir()),
        help="Local directory to store data files (default: pipeline/paths.starrailres_dir())",
    )
    parser.add_argument(
        "--files",
        default=None,
        help="Comma-separated list of files to update (default: all core files)",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="Language code (default: en; use 'cn' for 简体中文)",
    )
    parser.add_argument(
        "--index",
        default="index_new",
        help="Index directory (default: index_new)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Download timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be updated, don't write files",
    )
    parser.add_argument(
        "--enemies", action="store_true",
        help="Download enemy data from theBowja/starrail-data（遗留源——断更 3.2 冻结保留，"
             "现行权威为 --enemies-tbgd 的 turnbasedgamedata 五件）"
    )
    parser.add_argument(
        "--enemies-tbgd", action="store_true",
        help="Download enemy data from turnbasedgamedata (GitLab 五件——enemies 域新源)"
    )
    parser.add_argument(
        "--stages", action="store_true",
        help="Download stage lineup data (Hakushin + buhflipexplode) with red-line filtering"
    )
    parser.add_argument(
        "--mechanics", action="store_true",
        help="Download skill mechanics data (战技点耗产复核 extract_tbgd_skills)"
    )
    parser.add_argument(
        "--ssh", action="store_true",
        help="Use git SSH (sparse-checkout) instead of HTTPS for faster downloads in China"
    )
    args = parser.parse_args()

    # 如果指定了 --enemies-tbgd，下载 enemies 域 tbgd 五件（落盘 data/turnbasedgamedata/，
    # 与 --data-dir 无关；含红线 warn-only 对齐校验——需 Hakushin monster.json 在场，
    # 版本更新时请先跑 --stages 再跑本项）
    if args.enemies_tbgd:
        from hsr_nous.pipeline.enemies import update as enemies_update
        from hsr_nous.pipeline.paths import turnbasedgamedata_dir
        return enemies_update.run_update(
            data_dir=str(turnbasedgamedata_dir()),
            timeout=args.timeout,
            dry_run=args.dry_run,
        )

    # 如果指定了 --enemies，只下载敌人数据（--data-dir 默认指向 data/starrailres，
    # 未显式覆盖时取其父目录——落盘 data/enemies/，同 --stages 口径）
    if args.enemies:
        default_dir = str(_default_data_dir())
        data_dir = (
            str(_default_data_dir().parent)
            if args.data_dir == default_dir
            else args.data_dir
        )
        return download_enemies(
            data_dir=data_dir,
            timeout=args.timeout,
            dry_run=args.dry_run,
            use_ssh=args.ssh,
        )

    # 如果指定了 --stages，只下载关卡编成数据（stages/update.py 内部自拼 stages/ 子目录，
    # 需要 data/ 根目录；--data-dir 默认指向 data/starrailres，未显式覆盖时取其父目录）
    if args.stages:
        from hsr_nous.pipeline.stages import update as update_stages

        default_dir = str(_default_data_dir())
        data_dir = (
            str(_default_data_dir().parent)
            if args.data_dir == default_dir
            else args.data_dir
        )
        return update_stages.run(
            data_dir=data_dir,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )

    # 如果指定了 --mechanics，下载技能机制数据（提取器读 data/ 根 + StarRailRes 在册
    # 花名册做红线——红线依赖主数据，版本更新时请先跑默认更新再跑本项；--data-dir 默认
    # 指向 data/starrailres，未显式覆盖时取其父目录，同 --stages 口径。
    # 米游社提取器已归档停爬，不再纳入本流程）
    if args.mechanics:
        from hsr_nous.pipeline import extract_tbgd_skills

        default_dir = str(_default_data_dir())
        data_dir = (
            str(_default_data_dir().parent)
            if args.data_dir == default_dir
            else args.data_dir
        )
        old_argv, rc = sys.argv, 0
        try:
            sys.argv = ["extract_tbgd_skills", "--data-dir", data_dir]
            rc |= extract_tbgd_skills.main()
        finally:
            sys.argv = old_argv
        return rc

    files: Optional[List[str]] = None
    if args.files:
        files = [f.strip() for f in args.files.split(",") if f.strip()]

    return run_update(
        data_dir=args.data_dir,
        files=files,
        lang=args.lang,
        index=args.index,
        timeout=args.timeout,
        dry_run=args.dry_run,
        use_ssh=args.ssh,
    )


if __name__ == "__main__":
    raise SystemExit(main())
