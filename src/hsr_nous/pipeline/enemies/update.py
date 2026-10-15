#!/usr/bin/env python3
"""enemies 域下载：turnbasedgamedata 敌人配置表五件（GitLab raw 直下，零爬虫）.

五件（Dimbreath/turnbasedgamedata ExcelOutput，官方配置表镜像）：
- MonsterConfig.json（2722 实例：模板回挂/修正系数/弱点/抗性/技能表/AI 覆写/召唤链）
- MonsterTemplateConfig.json（632 模板：base 值/Rank/默认 AI——与 hakushin monstervalue
  顶层一一对应，632×6 字段全量对拍全等在案）
- MonsterSkillConfig.json（3566 技能：倍率 ParamList/削韧 SPHitBase/AI_CD/AI_ICD）
- EliteGroup.json / HardLevelGroup.json（公式链系数表——与 hakushin 同名列车）

红线（warn-only，三域共用口径）：以 Hakushin monster.json 已上线花名册对齐
MonsterTemplateConfig 模板 id——tbgd 是版本追踪仓（含未上线内容），花名册外的
模板 id 仅告警不剔除（神谕仅作绊线，官方公告为终审；剔除决策在消费侧红线，
见 pipeline/redline.py）。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

from hsr_nous.pipeline.build.update import download_file

_GITLAB_RAW = (
    "https://gitlab.com/Dimbreath/turnbasedgamedata/-/raw/main/ExcelOutput/{filename}"
)

#: 五件清单（文件名 = GitLab ExcelOutput 原文件名）
TBGD_FILES = [
    "MonsterConfig.json",
    "MonsterTemplateConfig.json",
    "MonsterSkillConfig.json",
    "EliteGroup.json",
    "HardLevelGroup.json",
]


def _default_data_dir() -> Path:
    from hsr_nous.pipeline.paths import turnbasedgamedata_dir
    return turnbasedgamedata_dir()


def _check_monster_alignment(out_dir: Path, timeout: float) -> List[str]:
    """红线版本对齐校验（warn-only）：tbgd 模板 id 比对 Hakushin 已上线怪物花名册.

    返回 MonsterTemplateConfig 中不在 monster.json 花名册里的 id（疑似未发布内容）。
    任何异常（网络失败、结构不符等）都捕获并返回空列表，绝不影响正常更新流程。
    """
    try:
        from hsr_nous.pipeline.paths import monster_meta_path

        roster = json.loads(monster_meta_path().read_text(encoding="utf-8"))
        templates = json.loads(
            (out_dir / "MonsterTemplateConfig.json").read_text(encoding="utf-8")
        )
        template_ids = {str(t.get("MonsterTemplateID")) for t in templates}
        from hsr_nous.pipeline.redline import check_release_alignment
        return check_release_alignment(template_ids, roster.keys())
    except Exception as exc:
        print(f"[warn] 怪物花名册对齐校验跳过: {exc}", file=sys.stderr)
        return []


def run_update(
    *,
    data_dir: str,
    files: List[str] | None = None,
    timeout: float = 30.0,
    dry_run: bool = False,
) -> int:
    """拉取五件（identical 一致跳过——文件级断点；单件失败不阻塞他件）."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    targets = files if files else TBGD_FILES

    updated: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []
    for filename in targets:
        url = _GITLAB_RAW.format(filename=filename)
        try:
            raw = download_file(url, timeout=timeout)
        except Exception as exc:
            print(f"[error] {filename}: {exc}", file=sys.stderr)
            failed.append(filename)
            continue
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[error] {filename}: invalid JSON - {exc}", file=sys.stderr)
            failed.append(filename)
            continue

        local_path = root / filename
        if local_path.exists() and local_path.read_bytes() == raw:
            print(f"[skip] {filename}: identical to local")
            skipped.append(filename)
            continue
        if dry_run:
            print(f"[would update] {filename}: {len(raw)} bytes")
            continue
        local_path.write_bytes(raw)
        print(f"[updated] {filename}: {len(raw)} bytes")
        updated.append(filename)

    # 红线版本对齐校验（warn-only）：模板表在更新范围内且成功落盘（或本就在盘）才比对
    unreleased: List[str] = []
    if ("MonsterTemplateConfig.json" in targets
            and "MonsterTemplateConfig.json" not in failed and not dry_run):
        unreleased = _check_monster_alignment(root, timeout=timeout)
        for mid in unreleased:
            print(f"[warn] 疑似未发布内容: MonsterTemplateConfig id={mid} "
                  f"不在 Hakushin 已上线怪物花名册", file=sys.stderr)

    manifest = {
        "source": "https://gitlab.com/Dimbreath/turnbasedgamedata",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unreleased_warnings": unreleased,
    }
    if not dry_run:
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"\n[summary] total={len(targets)}, updated={len(updated)}, "
          f"skipped={len(skipped)}, failed={len(failed)}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="turnbasedgamedata 敌人配置表五件下载（GitLab raw）"
    )
    parser.add_argument("--data-dir", default=str(_default_data_dir()),
                        help="落盘目录（缺省 = paths.turnbasedgamedata_dir()）")
    parser.add_argument("--files", default=None,
                        help="逗号分隔的文件清单（缺省 = 五件全量）")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="只检查不写入")
    args = parser.parse_args()

    files = [f.strip() for f in args.files.split(",") if f.strip()] if args.files else None
    return run_update(data_dir=args.data_dir, files=files,
                      timeout=args.timeout, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
