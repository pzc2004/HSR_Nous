#!/usr/bin/env python3
"""build 域下载：从 GitHub 更新 StarRailRes 数据文件到本地缓存.

P1 三域归置自 pipeline/update.py 切出（角色/光锥/遗器——build.yaml 输入数据）；
敌人（theBowja/turnbasedgamedata）与期数（Hakushin/buhflipexplode）分属 enemies/
stages 域，统一 CLI 见 pipeline/update.py 路由（P4 收编 hsr-data）。
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

_GITHUB_RAW_URL = (
    "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/{index}/{lang}/{filename}"
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
    from hsr_nous.pipeline.paths import starrailres_dir
    return starrailres_dir()


def download_file(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_with_etag(url: str, timeout: float = 30.0) -> "tuple[bytes, str | None]":
    """下载并返回 (内容, ETag)——ETag 入 manifest 供增量快检（--incr HEAD 比对）."""
    req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers.get("ETag")


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
    # 数据缓存失效钩子（函数内 import——保直接脚本执行零项目依赖，同 redline 先例）：
    # 写盘完成后清空 loader `_load_cached`，长驻/同进程调用方不再读旧数据
    from hsr_nous.pipeline.build.loader import clear_data_cache

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
        clear_data_cache()
        # 红线版本对齐校验（warn-only）：SSH 分支未实现，仅 HTTPS 分支执行
        return 0

    # HTTPS 逐文件下载模式
    failed: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    etags: Dict[str, str] = {}

    for filename in targets:
        url = _GITHUB_RAW_URL.format(index=index, lang=lang, filename=filename)

        try:
            raw, etag = download_with_etag(url, timeout=timeout)
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

        if etag:
            etags[filename] = etag

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
    # ETag 表并入 manifest（--incr HEAD 快检用）：本跑新抓的覆盖，未抓的沿旧表
    old_etags: Dict[str, str] = {}
    if manifest_path.exists():
        try:
            old_etags = dict(json.loads(manifest_path.read_text(encoding="utf-8")).get("etags") or {})
        except Exception:
            old_etags = {}
    old_etags.update(etags)
    manifest = {
        "source": "https://github.com/Mar-7th/StarRailRes",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unreleased_warnings": unreleased,
        "etags": old_etags,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total = len(targets)
    print(f"\n[summary] total={total}, updated={len(updated)}, skipped={len(skipped)}, failed={len(failed)}")
    clear_data_cache()
    return 1 if failed else 0
