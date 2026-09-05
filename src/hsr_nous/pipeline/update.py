#!/usr/bin/env python3
"""从 GitHub 更新 StarRailRes 数据文件到本地缓存."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

_GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/{index}/{lang}/{filename}"
)

# theBowja/starrail-data 仓库的敌人数据
_ENEMY_DATA_URL = (
    "https://raw.githubusercontent.com/theBowja/starrail-data/main/data/CHS/enemies.json"
)

# Hakushin（hakush.in 数据后端）：已上线花名册神谕，用于红线版本对齐校验
_HAKUSHIN_BASE_URL = "https://static.nanoka.cc"

CORE_FILES = [
    "characters.json",
    "character_skills.json",
    "character_skill_trees.json",
    "character_promotions.json",
    "character_ranks.json",
    "light_cones.json",
    "light_cone_promotions.json",
    "light_cone_ranks.json",
    "relic_sets.json",
    "relics.json",
    "relic_main_affixes.json",
    "relic_sub_affixes.json",
    "properties.json",
    "paths.json",
    "elements.json",
]


def _default_data_dir() -> Path:
    return Path(__file__).parent.parent.parent.parent / "data" / "starrailres"


def download_file(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _git_sparse_clone(
    repo_url: str,
    sparse_paths: List[str],
    dest_dir: Path,
    *,
    branch: str = "master",
) -> bool:
    """通过 SSH sparse-checkout 克隆仓库中指定路径的文件."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="hsr_nous_"))
    try:
        subprocess.run(
            ["git", "init"], cwd=tmp_dir, check=True,
            capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "remote", "add", "origin", repo_url], cwd=tmp_dir,
            check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "config", "core.sparseCheckout", "true"], cwd=tmp_dir,
            check=True, capture_output=True, text=True,
        )
        (tmp_dir / ".git" / "info" / "sparse-checkout").write_text(
            "\n".join(sparse_paths) + "\n", encoding="utf-8",
        )
        result = subprocess.run(
            ["git", "pull", "--depth=1", "origin", branch], cwd=tmp_dir,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"[error] git pull failed: {result.stderr}", file=sys.stderr)
            return False
        # 将克隆的文件复制到目标目录
        for sparse_path in sparse_paths:
            src = tmp_dir / sparse_path
            if src.is_dir():
                dst = dest_dir / sparse_path
                dst.mkdir(parents=True, exist_ok=True)
                for f in src.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dst / f.name)
            elif src.is_file():
                dst = dest_dir / sparse_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        return True
    except subprocess.TimeoutExpired:
        print("[error] git clone timed out", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _check_release_alignment(out_dir: Path, timeout: float) -> List[str]:
    """红线版本对齐校验（warn-only）：比对 Hakushin 已上线角色花名册.

    返回 characters.json 中不在已上线花名册里的 id（疑似未发布内容）。
    任何异常（网络失败、结构不符等）都捕获并返回空列表，绝不影响正常更新流程。
    """
    try:
        from hsr_nous.pipeline.redline import check_release_alignment

        live = json.loads(
            download_file(f"{_HAKUSHIN_BASE_URL}/manifest.json", timeout=timeout)
        )["hsr"]["live"]
        roster = json.loads(
            download_file(
                f"{_HAKUSHIN_BASE_URL}/hsr/{live}/character.json", timeout=timeout
            )
        )
        characters = json.loads(
            (out_dir / "characters.json").read_text(encoding="utf-8")
        )
        return check_release_alignment(characters.keys(), roster.keys())
    except Exception as exc:
        print(f"[warn] 版本对齐校验跳过: {exc}", file=sys.stderr)
        return []


def run_update(
    *,
    data_dir: str,
    files: Optional[List[str]] = None,
    lang: str = "en",
    index: str = "index_new",
    timeout: float = 30.0,
    dry_run: bool = False,
    use_ssh: bool = False,
) -> int:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)

    targets = files if files else CORE_FILES
    out_dir = root / index / lang
    out_dir.mkdir(parents=True, exist_ok=True)

    if use_ssh:
        # SSH sparse-checkout 模式：一次性克隆整个目录
        print(f"[ssh] cloning {index}/{lang}/ via SSH ...")
        repo_url = "git@github.com:Mar-7th/StarRailRes.git"
        sparse_paths = [f"{index}/{lang}/"]
        if not _git_sparse_clone(repo_url, sparse_paths, root, branch="master"):
            return 1
        # 统计结果
        updated: List[str] = []
        skipped: List[str] = []
        for filename in targets:
            local_path = out_dir / filename
            if local_path.exists():
                print(f"[updated] {filename}: {local_path.stat().st_size} bytes")
                updated.append(filename)
            else:
                print(f"[missing] {filename}", file=sys.stderr)
        manifest_path = out_dir / "manifest.json"
        manifest = {
            "source": "https://github.com/Mar-7th/StarRailRes",
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "updated": updated,
            "skipped": skipped,
            "failed": [],
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[summary] total={len(targets)}, updated={len(updated)}, skipped={len(skipped)}, failed=0")
        # 红线版本对齐校验（warn-only）：SSH 分支未实现，仅 HTTPS 分支执行
        return 0

    # HTTPS 逐文件下载模式
    failed: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []

    for filename in targets:
        url = _GITHUB_RAW_URL.format(index=index, lang=lang, filename=filename)

        try:
            raw = download_file(url, timeout=timeout)
        except urllib.error.HTTPError as exc:
            print(f"[error] {filename}: HTTP {exc.code}", file=sys.stderr)
            failed.append(filename)
            continue
        except urllib.error.URLError as exc:
            print(f"[error] {filename}: {exc.reason}", file=sys.stderr)
            failed.append(filename)
            continue

        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[error] {filename}: invalid JSON - {exc}", file=sys.stderr)
            failed.append(filename)
            continue

        local_path = out_dir / filename
        if local_path.exists():
            local_bytes = local_path.read_bytes()
            if local_bytes == raw:
                print(f"[skip] {filename}: identical to local")
                skipped.append(filename)
                continue

        if dry_run:
            print(f"[would update] {filename}: {len(raw)} bytes")
            continue

        local_path.write_bytes(raw)
        print(f"[updated] {filename}: {len(raw)} bytes")
        updated.append(filename)

    # 红线版本对齐校验（warn-only，不阻断）：characters.json 在更新范围内时才比对
    unreleased: List[str] = []
    if "characters.json" in targets:
        unreleased = _check_release_alignment(out_dir, timeout=timeout)
        for cid in unreleased:
            print(f"[warn] 疑似未发布内容: characters.json id={cid} 不在 Hakushin 已上线花名册", file=sys.stderr)

    manifest_path = out_dir / "manifest.json"
    manifest = {
        "source": "https://github.com/Mar-7th/StarRailRes",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unreleased_warnings": unreleased,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = len(targets)
    print(f"\n[summary] total={total}, updated={len(updated)}, skipped={len(skipped)}, failed={len(failed)}")
    return 1 if failed else 0


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
        help="Local directory to store data files",
    )
    parser.add_argument(
        "--lang", default="en", help="Language code (default: en)"
    )
    parser.add_argument(
        "--index", default="index_new", help="Index type: index_new or index_min (default: index_new)"
    )
    parser.add_argument(
        "--files",
        default="",
        help="Comma-separated file names to update (default: all core files)",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="Network timeout in seconds"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check remote files without writing"
    )
    parser.add_argument(
        "--enemies", action="store_true", help="Download enemy data from theBowja/starrail-data"
    )
    parser.add_argument(
        "--stages", action="store_true",
        help="Download stage lineup data (Hakushin + buhflipexplode) with red-line filtering"
    )
    parser.add_argument(
        "--mechanics", action="store_true",
        help="Download skill mechanics data (战技点耗产复核 extract_tbgd_skills + 米游社五项标签 extract_miyoushe_skills)"
    )
    parser.add_argument(
        "--ssh", action="store_true",
        help="Use git SSH (sparse-checkout) instead of HTTPS for faster downloads in China"
    )
    args = parser.parse_args()

    # 如果指定了 --enemies，只下载敌人数据
    if args.enemies:
        return download_enemies(
            data_dir=args.data_dir,
            timeout=args.timeout,
            dry_run=args.dry_run,
            use_ssh=args.ssh,
        )

    # 如果指定了 --stages，只下载关卡编成数据（update_stages 内部自拼 stages/ 子目录，
    # 需要 data/ 根目录；--data-dir 默认指向 data/starrailres，未显式覆盖时取其父目录）
    if args.stages:
        from hsr_nous.pipeline import update_stages

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

    # 如果指定了 --mechanics，下载技能机制数据（两提取器均读 data/ 根 + StarRailRes 在册
    # 花名册做红线——红线依赖主数据，版本更新时请先跑默认更新再跑本项；--data-dir 默认
    # 指向 data/starrailres，未显式覆盖时取其父目录，同 --stages 口径）
    if args.mechanics:
        from hsr_nous.pipeline import extract_miyoushe_skills, extract_tbgd_skills

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
            sys.argv = ["extract_miyoushe_skills", "--data-dir", data_dir]
            rc |= extract_miyoushe_skills.main()
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
