"""批量打标驱动（ops/annotator/batch）——全花名册逐角色端到端，断点续跑.

外层顺序循环（单角色内 DAG 自带 max_workers 并发，llm_api 服务闸统一限速）；
runs_root/<cid>/ 即每角色的重放状态机（同输入哈希命中缓存零重跑——批量重跑=增量续跑）；
单角色异常不拖死全批（轨迹落汇总 JSON 等人工）。

用法：`uv run python -m hsr_nous.ops.annotator.batch [--ids 1404,1202] [--limit N]
      [--include-anchors] [--budget 3] [--use ANNOTATOR]`（生产走 `scripts/annotator.sh batch`）。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.ops.annotator.llm import make_tribios_runner
from hsr_nous.ops.annotator.pipeline import ROOT, run_character

FIXTURES_DIR = ROOT / "tests/fixtures/templates/characters"


def anchor_ids(fixtures_dir: Optional[Path] = None) -> frozenset:
    """手写锚集合 = fixtures 文件名派生（加锚=放新 fixture，代码不动——锚角色默认跳过：
    人工全机制版已在库，重打只有对拍收益，--include-anchors 才放行）。"""
    d = fixtures_dir or FIXTURES_DIR
    return frozenset(p.name.split("_", 1)[0] for p in d.glob("*.yaml"))


def roster(*, lang: str = "cn") -> List[str]:
    """全花名册（有技能清单的可玩角色，按 cid 升序——确定性批序）。"""
    from hsr_nous.pipeline import load_characters

    chars = load_characters(lang=lang)
    return sorted(str(cid) for cid, raw in chars.items()
                  if isinstance(raw, dict) and raw.get("skills"))


def collect_targets(*, ids: Optional[List[str]] = None, include_anchors: bool = False,
                    limit: Optional[int] = None) -> List[str]:
    """目标清单：显式 ids 直给；否则全花名册（默认跳锚）。"""
    if ids:
        return list(ids)
    anchors = anchor_ids()
    out = [c for c in roster() if include_anchors or c not in anchors]
    return out[:limit] if limit else out


def run_batch(cids: List[str], *, llm_use: str = "ANNOTATOR",
              runs_root: Path = ROOT / "data/annotator/runs",
              staging_root: Optional[Path] = None, budget: int = 3,
              workers: int = 1,
              summary_path: Optional[Path] = None) -> Dict[str, Any]:
    """逐角色打标：返回 {cid: {status, detail}}（status: finalized/human_queue/error）。

    断点续跑零专门代码——runs_root/<cid>/ 的节点缓存即状态机（重跑同批=全缓存命中）。
    workers>1 = 多角色外层并行（单角色 DAG 内部基本串行——evidence/draft/三闸一条链，
    并发宽度只能来自外层；共享 tribios 客户端按 key 并发闸统一限流，workers 别超客户端
    并发配额，超出=排队不增益）。
    """
    llm = make_tribios_runner(use=llm_use)
    results: Dict[str, Any] = {}
    t0 = time.time()

    def _one(pair: "tuple[int, str]") -> "tuple[int, str, Dict[str, Any]]":
        i, cid = pair
        try:
            out = run_character(cid, llm=llm, runs_root=runs_root,
                                staging_root=staging_root, budget=budget)
            if "finalize" in out:
                r = {"status": "finalized", "detail": out["finalize"].get("staging", "")}
            elif "human_queue" in out:
                r = {"status": "human_queue",
                     "detail": out["human_queue"].get("reason", "")}
            else:
                r = {"status": "error", "detail": f"运行图终点异常：{sorted(out)}"}
        except Exception as e:  # 单角色失败不拖死全批（轨迹落汇总等人工）
            r = {"status": "error", "detail": f"{type(e).__name__}: {e}"}
        return i, cid, r

    from concurrent.futures import ThreadPoolExecutor, as_completed
    pairs = list(enumerate(cids, 1))
    done = 0
    if workers <= 1:
        for i, cid, r in map(_one, pairs):
            results[cid] = r
            done += 1
            print(f"[{done}/{len(cids)}] {cid} → {r['status']}（累计 {time.time() - t0:.0f}s）",
                  flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, cid, r in (f.result() for f in as_completed(
                    [pool.submit(_one, p) for p in pairs])):
                results[cid] = r
                done += 1
                print(f"[{done}/{len(cids)}] {cid} → {r['status']}（累计 {time.time() - t0:.0f}s）",
                      flush=True)
    summary = {"results": results, "elapsed_s": round(time.time() - t0, 1),
               "counts": {s: sum(1 for r in results.values() if r["status"] == s)
                          for s in ("finalized", "human_queue", "error")}}
    path = summary_path or (Path(runs_root) / "_batch_summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"批量收官：{summary['counts']}（汇总 {path}）", flush=True)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="annotator.batch", description=__doc__.splitlines()[0])
    ap.add_argument("--ids", help="显式 cid 清单（逗号分隔；缺省=全花名册）")
    ap.add_argument("--limit", type=int, help="试点限量（全花名册前 N 个）")
    ap.add_argument("--include-anchors", action="store_true",
                    help="锚角色（fixtures 已有手写版）也重打——默认跳过")
    ap.add_argument("--budget", type=int, default=3, help="内环修订预算（默认 3）")
    ap.add_argument("--workers", type=int, default=1,
                    help="多角色外层并行数（默认 1=顺序；单角色 DAG 内部基本串行，"
                         "并发宽度只能来自外层——别超 LLM 客户端并发配额）")
    ap.add_argument("--use", default="ANNOTATOR", help="LLM 用途槽（默认 ANNOTATOR）")
    args = ap.parse_args(argv)

    cids = collect_targets(
        ids=[x.strip() for x in args.ids.split(",") if x.strip()] if args.ids else None,
        include_anchors=args.include_anchors, limit=args.limit)
    print(f"目标 {len(cids)} 个：{cids[:8]}{'…' if len(cids) > 8 else ''}"
          f"（外层并行 {args.workers}）", flush=True)
    summary = run_batch(cids, llm_use=args.use, budget=args.budget, workers=args.workers)
    return 0 if summary["counts"]["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
