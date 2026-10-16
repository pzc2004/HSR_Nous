#!/usr/bin/env python3
"""数据快照镜像工具（CD `.github/workflows/data-cron.yml` + 本地人工通道共用）.

模型（owner 2026-10-16 定稿）：
- **hsr-data update 是唯一数据生产者**（内容不变）——快照 = 其产物原样打包，
  构造恒等，无第二套取数实现
- release 只是产物缓存：CD 每两周生产（cron）、本地人工随时可推（publish-local）
- buh 死源：以冻结快照（FROZEN_BUH_TAG）作覆盖层应急，上游 v4.0 落地后删除覆盖层即揭封
- pins.py 钉值唯一事实源；挪钉走 PR + auto-merge（CI 绿即合）；快照只留最新 2 个

子命令：build（CD 全量构建）/ publish-local（本地人工推送）/ publish（上传 release）/
bump（pins 挪钉开 PR）/ prune（留存清理）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

MIRROR_REPO = "pzc2004/HSR_Nous"
PINS_PATH = Path("src/hsr_nous/pipeline/pins.py")

#: buh 冻结快照（上游 2026-10-16 v4.0 改版下架前的最后形态；覆盖层应急用，上游恢复后删）
FROZEN_BUH_TAG = "data-buh-4.6-20261016"
FROZEN_BUH_ASSET = "buh-snapshot.tar.gz"

#: 快照清单（2026-10-16 数据资产审计：三域活数据 + 冻结活读件；排除缓存/生成件/tracked）
SNAPSHOT_PATHS = [
    "starrailres",
    "turnbasedgamedata",
    "stages",
    "enemies",
    "fandom_skill_data.json",
    "fandom_enemy_data.json",
    "miyoushe_skill_data.json",
    "tbgd_skill_data.json",
]


# ----------------------------------------------------------------- 通用工具


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(cmd)}", file=sys.stderr)
    return subprocess.run(cmd, check=True, **kw)


def _gh_api(path: str):
    out = _run(["gh", "api", path, "--jq", "."], capture_output=True, text=True)
    return json.loads(out.stdout)


def _download(url: str, timeout: float = 60.0, retries: int = 3) -> bytes:
    last: Exception = RuntimeError("unreachable")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HSR_Nous data-mirror"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def _release_url(tag: str, asset: str) -> str:
    return f"https://github.com/{MIRROR_REPO}/releases/download/{tag}/{asset}"


def _pack(data_dir: Path, out_file: Path) -> None:
    with tarfile.open(out_file, "w:gz") as tf:
        for rel in SNAPSHOT_PATHS:
            src = data_dir / rel
            if src.exists():
                tf.add(src, arcname=rel)
            else:
                print(f"[warn] 快照清单项缺失:{rel}", file=sys.stderr)


# ----------------------------------------------------------------- build（CD 全量构建）


def _overlay_frozen_buh(work: Path) -> None:
    """buh 死源覆盖层：冻结快照解出原始件 → 管道红线过滤（与 _update_buh 同一组函数）
    → 落 work/stages/buhflipexplode/。上游 v4.0 落地后删除本函数调用即揭封。"""
    from datetime import date

    from hsr_nous.pipeline.redline import collect_referenced_ids, filter_entities, filter_phases

    url = _release_url(FROZEN_BUH_TAG, FROZEN_BUH_ASSET)
    tmp = Path(tempfile.mkdtemp(prefix="buh_frozen_"))
    (tmp / "snap.tar.gz").write_bytes(_download(url))
    with tarfile.open(tmp / "snap.tar.gz") as tf:
        tf.extractall(tmp / "x")
    src, out = tmp / "x", work / "stages" / "buhflipexplode"
    out.mkdir(parents=True, exist_ok=True)

    today = date.today()
    filtered: dict = {}
    for mode in ("aa", "fh", "pf", "as"):
        data = json.loads((src / "hsr" / mode / f"{mode}-versions.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data, removed = filter_phases(data, today)
        else:
            removed = []
            for section in data:
                versions = section.get("versions")
                if isinstance(versions, dict):
                    kept, rm = filter_phases(versions, today)
                    section["versions"] = kept
                    removed.extend(rm)
        if removed:
            print(f"[redline] buh {mode}-versions.json: 移除未上线期 {removed}", file=sys.stderr)
        filtered[mode] = data
        (out / f"{mode}-versions.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
    enemy_ids, buff_ids = collect_referenced_ids(filtered)
    for name, keep in (("enemies", enemy_ids), ("buffs", buff_ids)):
        entities = json.loads((src / "assets" / "hsr" / f"{name}.json").read_text(encoding="utf-8"))
        kept, n_removed = filter_entities(entities, keep)
        if n_removed:
            print(f"[redline] buh {name}.json: 移除 {n_removed} 条未引用条目", file=sys.stderr)
        (out / f"{name}.json").write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    print(f"[overlay] buh 冻结覆盖层落盘（{FROZEN_BUH_TAG}）", file=sys.stderr)


def _validate_gates(work: Path) -> None:
    """验收闸：三域数据闸（tests._data_env）不过即炸——绝不发布坏快照."""
    os.environ["HSR_NOUS_DATA_DIR"] = str(work)
    from tests._data_env import data_available, stage_data_available, tbgd_data_available

    assert data_available(), "build 域闸未点亮（starrailres/tbgd_skill/fandom_skill 缺失）"
    assert stage_data_available(), "stages 域闸未点亮"
    assert tbgd_data_available(), "tbgd 域闸未点亮"
    print("[validate] 三域数据闸全亮", file=sys.stderr)


def cmd_build(args) -> None:
    """CD 全量构建：hsr-data update（唯一生产者）→ buh 冻结覆盖层 → 闸 → 打包."""
    work = Path(tempfile.mkdtemp(prefix="snap_")) / "data"
    work.mkdir(parents=True)
    env = dict(os.environ, HSR_NOUS_DATA_DIR=str(work))
    update_cmd = ["uv", "run", "hsr-data", "update"]
    if args.with_fandom:
        update_cmd.append("--with-fandom")
    # buh 死源失败容忍（"失败保旧版不半写"，此处全新目录即缺席，由覆盖层补）
    subprocess.run(update_cmd, env=env, check=False)

    _overlay_frozen_buh(work)
    _validate_gates(work)

    tag = args.tag or f"data-full-{time.strftime('%Y%m%d')}"
    out_file = Path(args.out_dir) / "data-snapshot.tar.gz"
    _pack(work, out_file)
    print(f"tag={tag}")
    print(f"[build] {out_file}（{out_file.stat().st_size}B）", file=sys.stderr)
    (Path(args.out_dir) / ".mirror_outputs.json").write_text(
        json.dumps({"tag": tag, "size": out_file.stat().st_size}))


# ----------------------------------------------------------------- publish-local（本地人工推送）


def cmd_publish_local(args) -> None:
    """本地人工推送：打包本地 data/ → 发 release → pins 挪钉（commit 留给 owner）."""
    data_dir = Path(args.data_dir)
    assert (data_dir / "starrailres").exists(), f"{data_dir} 不像数据目录（缺 starrailres/）"
    base = f"data-full-{time.strftime('%Y%m%d')}"
    tag, n = base, 1
    while subprocess.run(["gh", "release", "view", tag, "--repo", MIRROR_REPO],
                         capture_output=True).returncode == 0:
        n += 1
        tag = f"{base}-r{n}"
    tmp = Path(tempfile.mkdtemp(prefix="snap_local_"))
    out_file = tmp / "data-snapshot.tar.gz"
    _pack(data_dir, out_file)
    _run(["gh", "release", "create", tag, str(out_file), "--repo", MIRROR_REPO,
          "--title", f"HSR_Nous 数据快照 {tag}",
          "--notes", f"source: manual（本地人工推送）\nnote: {args.note}\n"
                     f"构建时间: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"])
    _bump_pins(tag)
    print(f"[publish-local] https://github.com/{MIRROR_REPO}/releases/tag/{tag}", file=sys.stderr)
    print("[publish-local] pins.py 已在工作区挪钉——commit 由 owner 过目后执行", file=sys.stderr)


# ----------------------------------------------------------------- publish / bump / prune


def cmd_publish(args) -> None:
    meta_path = Path(args.out_dir) / ".mirror_outputs.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    notes = (f"source: cron（CD 定期构建）\n"
             f"构建时间: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
             f"内容: hsr-data update 产物（构造恒等）+ buh 冻结覆盖层（{FROZEN_BUH_TAG}）\n"
             f"大小: {meta.get('size', '?')}B")
    exists = subprocess.run(["gh", "release", "view", args.tag, "--repo", MIRROR_REPO],
                            capture_output=True).returncode == 0
    if exists:
        _run(["gh", "release", "upload", args.tag, args.file, "--clobber", "--repo", MIRROR_REPO])
    else:
        _run(["gh", "release", "create", args.tag, args.file, "--repo", MIRROR_REPO,
              "--title", f"HSR_Nous 数据快照 {args.tag}", "--notes", notes])
    print(f"[publish] https://github.com/{MIRROR_REPO}/releases/tag/{args.tag}", file=sys.stderr)


def _bump_pins(tag: str) -> None:
    text = PINS_PATH.read_text(encoding="utf-8")
    marker = 'SNAPSHOT_TAG = "'
    old = text.split(marker)[1].split('"')[0]
    if old == tag:
        print(f"[bump] pins 已是 {tag}，无需挪动", file=sys.stderr)
        return
    PINS_PATH.write_text(text.replace(f'{marker}{old}"', f'{marker}{tag}"'), encoding="utf-8")
    print(f"[bump] pins.py: {old} → {tag}", file=sys.stderr)


def cmd_bump(args) -> None:
    text = PINS_PATH.read_text(encoding="utf-8")
    old = text.split('SNAPSHOT_TAG = "')[1].split('"')[0]
    if old == args.tag:
        print(f"[bump] pins 已是 {args.tag}，无需挪动", file=sys.stderr)
        return
    branch = f"data/snapshot-pin-{args.tag}"
    _run(["git", "config", "user.name", "hsr-nous-bot"])
    _run(["git", "config", "user.email", "hsr-nous-bot@users.noreply.github.com"])
    _run(["git", "checkout", "-b", branch, "origin/main"])
    _bump_pins(args.tag)
    _run(["git", "add", str(PINS_PATH)])
    _run(["git", "commit", "-m", f"chore(data): 快照 pin {old} → {args.tag}（CD 定期前移）"])
    _run(["git", "push", "-u", "origin", branch])
    out = _run(["gh", "pr", "create", "--repo", MIRROR_REPO, "--base", "main", "--head", branch,
                "--title", f"chore(data): 快照 pin {old} → {args.tag}",
                "--body", f"CD data-mirror 前移数据快照镜像：{old} → {args.tag}\n\n"
                          f"发布记录：https://github.com/{MIRROR_REPO}/releases/tag/{args.tag}\n\n"
                          f"auto-merge 已开启——CI 全绿后自动合并（想人工把关可点掉）"],
               capture_output=True, text=True)
    pr_url = out.stdout.strip()
    _run(["gh", "pr", "merge", pr_url, "--auto", "--squash"])
    print(f"[bump] PR 已创建并挂 auto-merge: {pr_url}", file=sys.stderr)


def cmd_prune(args) -> None:
    """留存上限：只保留最新 keep 个 data-full-* 快照 release，其余连 release 带 tag 删除."""
    releases = _gh_api(f"repos/{MIRROR_REPO}/releases?per_page=100")
    data_releases = sorted(
        (r for r in releases if r["tag_name"].startswith("data-full-")),
        key=lambda r: r["created_at"], reverse=True,
    )
    for rel in data_releases[args.keep:]:
        tag = rel["tag_name"]
        _run(["gh", "release", "delete", tag, "--repo", MIRROR_REPO, "--yes"])
        _run(["git", "push", "origin", "--delete", tag])
        print(f"[prune] 删除旧快照 {tag}", file=sys.stderr)
    print(f"[prune] 保留 {[r['tag_name'] for r in data_releases[:args.keep]]}", file=sys.stderr)


# ----------------------------------------------------------------- 入口


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="CD 全量构建（hsr-data update + buh 覆盖层 + 闸 + 打包）")
    p_build.add_argument("--tag", default="")
    p_build.add_argument("--out-dir", required=True)
    p_build.add_argument("--with-fandom", action="store_true")
    p_build.set_defaults(fn=cmd_build)

    p_pl = sub.add_parser("publish-local", help="本地人工推送（打包本地 data/ 发 release + 挪钉）")
    p_pl.add_argument("--data-dir", default="data")
    p_pl.add_argument("--note", default="")
    p_pl.set_defaults(fn=cmd_publish_local)

    p_pub = sub.add_parser("publish", help="上传 release 资产（CD 流程用）")
    p_pub.add_argument("--tag", required=True)
    p_pub.add_argument("--file", required=True)
    p_pub.add_argument("--out-dir", required=True)
    p_pub.set_defaults(fn=cmd_publish)

    p_bump = sub.add_parser("bump", help="pins 挪钉开 PR（auto-merge）")
    p_bump.add_argument("--tag", required=True)
    p_bump.set_defaults(fn=cmd_bump)

    p_prune = sub.add_parser("prune", help="留存清理（只留最新 keep 个快照）")
    p_prune.add_argument("--keep", type=int, default=2)
    p_prune.set_defaults(fn=cmd_prune)

    args = parser.parse_args()
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
