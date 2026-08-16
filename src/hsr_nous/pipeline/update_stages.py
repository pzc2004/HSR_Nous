#!/usr/bin/env python3
"""下载深渊关卡编成数据（Hakushin + buhflipexplode 双源），落盘前过红线.

- Hakushin（hakush.in 数据后端）：期数列表 + 系数表 + 怪物基础数值（monstervalue，
  单文件含全部怪物 AttackBase/HPBase 等 base 值与 child 修正系数）+ 每期详情
  （详情仅 en 路径），未来占位期（名称为空且无排期）的详情不落盘；
- buhflipexplode-src：aa/fh/pf/as 四种玩法的 versions + enemies/buffs 系数表，
  先按红线过滤未上线期数，再按引用白名单过滤 enemies/buffs。

输出到 <data_dir>/stages/{hakushin,buhflipexplode}/，结构与数据快照一致。
"""

import json
import sys
import time
import urllib.error
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from hsr_nous.pipeline.redline import (
    collect_referenced_ids,
    filter_entities,
    filter_phases,
)
from hsr_nous.pipeline.update import download_file

_HAKUSHIN_BASE = "https://static.nanoka.cc"
_BUH_BASE = "https://raw.githubusercontent.com/spiritfxxxx/buhflipexplode-src/main"

# Hakushin 期数列表文件 -> 详情端点前缀（详情只有 en 路径）
_HAKUSHIN_DETAIL_EP = {"maze": "maze", "maze_extra": "story", "maze_boss": "boss"}
# Hakushin 顶层文件（列表 + 系数表 + 怪物基础数值 monstervalue）
_HAKUSHIN_TOP_FILES = [
    "maze", "maze_extra", "maze_boss", "EliteGroup", "HardLevelGroup", "monster",
    "monstervalue",
]
_BUH_MODES = ["aa", "fh", "pf", "as"]


def _fetch(url: str, timeout: float) -> Tuple[bytes, Any]:
    """下载并解析 JSON，失败抛异常（由调用方捕获记录）."""
    raw = download_file(url, timeout=timeout)
    return raw, json.loads(raw)


def _save(path: Path, content: bytes, *, dry_run: bool, label: str) -> None:
    """整体字节不变则跳过，否则落盘（dry_run 只打印）."""
    if path.exists() and path.read_bytes() == content:
        print(f"[skip] {label}: identical to local")
        return
    if dry_run:
        print(f"[would update] {label}: {len(content)} bytes")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    print(f"[updated] {label}: {len(content)} bytes")


def _dumps(data: Any) -> bytes:
    """buh 文件的序列化格式（与数据快照一致：indent=1，UTF-8 原文，无尾换行）."""
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def _is_placeholder_detail(detail: Any) -> bool:
    """未来占位期判定：名称为空字符串且 begin_time 为空（None/""）."""
    if isinstance(detail, list):
        head = detail[0] if detail else {}
    elif isinstance(detail, dict):
        head = detail
    else:
        return False
    if not isinstance(head, dict):
        return False
    return head.get("name") == "" and not head.get("begin_time")


def _update_hakushin(
    hak_dir: Path,
    *,
    timeout: float,
    dry_run: bool,
    failures: List[str],
    redline_removed: Dict[str, Any],
) -> Tuple[Dict[str, int], Optional[str]]:
    """下载 Hakushin 列表/系数表/详情，返回 (各模式详情期数, live 版本号)."""
    try:
        _raw, manifest = _fetch(f"{_HAKUSHIN_BASE}/manifest.json", timeout)
        live = manifest["hsr"]["live"]
    except Exception as exc:
        print(f"[error] hakushin manifest.json: {exc}", file=sys.stderr)
        failures.append(f"hakushin manifest.json: {exc}")
        return {}, None

    print(f"[hakushin] live version: {live}")

    # 顶层列表与系数表：原样落盘
    lists: Dict[str, Any] = {}
    for name in _HAKUSHIN_TOP_FILES:
        url = f"{_HAKUSHIN_BASE}/hsr/{live}/{name}.json"
        try:
            raw, data = _fetch(url, timeout)
        except Exception as exc:
            print(f"[error] hakushin {name}.json: {exc}", file=sys.stderr)
            failures.append(f"hakushin {name}.json: {exc}")
            continue
        _save(hak_dir / f"{name}.json", raw, dry_run=dry_run, label=f"hakushin/{name}.json")
        lists[name] = data

    # 每期详情：未来占位期不落盘
    detail_counts: Dict[str, int] = {}
    for mode, ep in _HAKUSHIN_DETAIL_EP.items():
        periods = lists.get(mode)
        if not isinstance(periods, dict):
            continue
        kept = 0
        placeholders: List[str] = []
        for period_id in periods:
            url = f"{_HAKUSHIN_BASE}/hsr/{live}/en/{ep}/{period_id}.json"
            try:
                raw, detail = _fetch(url, timeout)
            except urllib.error.HTTPError as exc:
                print(f"[error] hakushin {mode}/{period_id}: HTTP {exc.code}", file=sys.stderr)
                failures.append(f"hakushin {mode}/{period_id}: HTTP {exc.code}")
                continue
            except Exception as exc:
                print(f"[error] hakushin {mode}/{period_id}: {exc}", file=sys.stderr)
                failures.append(f"hakushin {mode}/{period_id}: {exc}")
                continue
            if _is_placeholder_detail(detail):
                print(f"[redline] hakushin {mode}/{period_id}: 未来占位期，不落盘")
                placeholders.append(period_id)
                continue
            _save(
                hak_dir / "details" / mode / f"{period_id}.json", raw,
                dry_run=dry_run, label=f"hakushin/details/{mode}/{period_id}.json",
            )
            kept += 1
        detail_counts[mode] = kept
        if placeholders:
            redline_removed[f"hakushin {mode} 占位期"] = placeholders
    return detail_counts, live


def _update_buh(
    buh_dir: Path,
    *,
    timeout: float,
    dry_run: bool,
    today: date,
    failures: List[str],
    redline_removed: Dict[str, Any],
) -> Dict[str, int]:
    """下载 buhflipexplode versions/enemies/buffs 并过红线，返回各模式期数."""
    # versions：按红线过滤未上线期数
    filtered_versions: Dict[str, Any] = {}
    phase_counts: Dict[str, int] = {}
    for mode in _BUH_MODES:
        url = f"{_BUH_BASE}/hsr/{mode}/{mode}-versions.json"
        try:
            _raw, data = _fetch(url, timeout)
        except Exception as exc:
            print(f"[error] buh {mode}-versions.json: {exc}", file=sys.stderr)
            failures.append(f"buh {mode}-versions.json: {exc}")
            continue
        removed: List[str] = []
        if isinstance(data, dict):
            # aa/pf/as：期号 -> 期数据
            data, removed = filter_phases(data, today)
        elif isinstance(data, list):
            # fh：list of sections，每节有 versions dict
            for section in data:
                versions = section.get("versions")
                if isinstance(versions, dict):
                    kept, rm = filter_phases(versions, today)
                    section["versions"] = kept
                    removed.extend(rm)
        filtered_versions[mode] = data
        if removed:
            redline_removed[f"{mode}-versions.json"] = removed
            print(f"[redline] buh {mode}-versions.json: 移除未上线期 {removed}")
        phase_counts[mode] = sum(
            len(s.get("versions", {})) for s in data
        ) if isinstance(data, list) else len(data)
        _save(
            buh_dir / f"{mode}-versions.json", _dumps(data),
            dry_run=dry_run, label=f"buhflipexplode/{mode}-versions.json",
        )

    if not filtered_versions:
        return phase_counts

    # enemies/buffs：按过滤后期数的引用白名单过滤
    enemy_ids, buff_ids = collect_referenced_ids(filtered_versions)
    for name, keep_ids in (("enemies", enemy_ids), ("buffs", buff_ids)):
        url = f"{_BUH_BASE}/assets/hsr/{name}.json"
        try:
            _raw, entities = _fetch(url, timeout)
        except Exception as exc:
            print(f"[error] buh {name}.json: {exc}", file=sys.stderr)
            failures.append(f"buh {name}.json: {exc}")
            continue
        kept, n_removed = filter_entities(entities, keep_ids)
        if n_removed:
            redline_removed[f"{name}.json"] = f"移除 {n_removed} 条未引用条目（保留 {len(kept)}/{len(entities)}）"
            print(f"[redline] buh {name}.json: 移除 {n_removed} 条未引用条目（保留 {len(kept)}/{len(entities)}）")
        _save(
            buh_dir / f"{name}.json", _dumps(kept),
            dry_run=dry_run, label=f"buhflipexplode/{name}.json",
        )
    return phase_counts


def run(
    *,
    data_dir: str,
    timeout: float = 30.0,
    dry_run: bool = False,
    today: Optional[date] = None,
) -> int:
    """下载两源关卡编成数据并过红线，返回 0（成功）或 1（有失败）."""
    root = Path(data_dir) / "stages"
    hak_dir = root / "hakushin"
    buh_dir = root / "buhflipexplode"
    today = today or date.today()

    failures: List[str] = []
    redline_removed: Dict[str, Any] = {}

    print(f"[stages] data dir: {root} (today={today.isoformat()})")
    hak_counts, live = _update_hakushin(
        hak_dir, timeout=timeout, dry_run=dry_run,
        failures=failures, redline_removed=redline_removed,
    )
    buh_counts = _update_buh(
        buh_dir, timeout=timeout, dry_run=dry_run, today=today,
        failures=failures, redline_removed=redline_removed,
    )

    manifest = {
        "sources": {"hakushin": _HAKUSHIN_BASE, "buhflipexplode": _BUH_BASE},
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hakushin_live_version": live,
        "period_counts": {"hakushin": hak_counts, "buhflipexplode": buh_counts},
        "redline_removed": redline_removed,
        "failures": failures,
    }
    if dry_run:
        print(f"[would update] hakushin/_update_manifest.json: {len(_dumps(manifest))} bytes")
    else:
        hak_dir.mkdir(parents=True, exist_ok=True)
        (hak_dir / "_update_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"\n[summary] hakushin={sum(hak_counts.values())} details, "
          f"buh={sum(buh_counts.values())} phases, "
          f"redline_removed={len(redline_removed)} kinds, failed={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run(data_dir=str(Path(__file__).parent.parent.parent.parent / "data")))
