#!/usr/bin/env python3
"""enemies 域下载：tbgd 五表 + 实际引用 CharacterConfig/Ability/ConfigAI.

ExcelOutput 表走 `/ExcelOutput/` raw 命名空间；Config 树走仓库根部 raw 命名空间。
CharacterConfig 来自 MonsterTemplateConfig.JsonConfig，同族 Ability 须经 GitLab 实际文件索引
确认后才下载；不扫全仓，也不对猜测文件名发起 404 重试。

五表（Dimbreath/turnbasedgamedata ExcelOutput，官方配置表镜像）：
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
_GITLAB_CONFIG_RAW = (
    "https://gitlab.com/Dimbreath/turnbasedgamedata/-/raw/main/{filename}"
)


def _download_url(filename: str) -> str:
    """ExcelOutput 表与仓库根部 Config 树分属两个 URL 命名空间."""
    template = _GITLAB_CONFIG_RAW if filename.startswith("Config/") else _GITLAB_RAW
    return template.format(filename=filename)

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


def _referenced_ai_paths(out_dir: Path) -> List[str]:
    """五表落盘后扫描实际引用的 ConfigAI 相对路径，避免全目录盲目下载."""
    paths = set()
    for filename, fields in (
        ("MonsterTemplateConfig.json", ("AIPath",)),
        ("MonsterConfig.json", ("AIPath", "OverrideAIPath")),
    ):
        path = out_dir / filename
        if not path.exists():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[warn] ConfigAI 引用扫描失败 {filename}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            for field in fields:
                value = row.get(field)
                if (isinstance(value, str) and value.startswith("Config/ConfigAI/")
                        and ".." not in Path(value).parts):
                    paths.add(value)
    return sorted(paths)


def _referenced_character_configs(out_dir: Path) -> List[str]:
    """MonsterTemplateConfig.JsonConfig 的实际 CharacterConfig 引用."""
    path = out_dir / "MonsterTemplateConfig.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sorted({
        str(row["JsonConfig"]) for row in rows
        if isinstance(row.get("JsonConfig"), str)
        and row["JsonConfig"].startswith("Config/ConfigCharacter/")
        and ".." not in Path(row["JsonConfig"]).parts
    })


def _ability_companions(configs: List[str], available: set[str]) -> List[str]:
    """CharacterConfig 本体 + 经远端文件索引证实存在的同族 Ability 文件."""
    targets = set(configs)
    for config in configs:
        path = Path(config)
        if "_Config" not in path.name:
            continue
        ability = (config.replace("Config/ConfigCharacter/", "Config/ConfigAbility/", 1)
                   .replace("_Config", "_Ability", 1))
        if ability in available:
            targets.add(ability)
    return sorted(targets)


def _remote_ability_file_index(timeout: float) -> set[str]:
    """GitLab 实际上游文件索引；只取清单，不下载整仓或盲试文件名."""
    import urllib.parse
    import urllib.request

    files: set[str] = set()
    base = "https://gitlab.com/api/v4/projects/Dimbreath%2Fturnbasedgamedata/repository/tree?"
    for page in range(1, 1000):
        query = urllib.parse.urlencode({
            "path": "Config/ConfigAbility/Monster", "per_page": 100, "page": page,
        })
        with urllib.request.urlopen(base + query, timeout=timeout) as response:
            rows = json.load(response)
        if not isinstance(rows, list):
            raise ValueError("GitLab Ability 文件索引返回非数组")
        for row in rows:
            path = str(row.get("path") or "")
            if (row.get("type") == "blob" and path.endswith(".json")
                    and not path.endswith(".layout.json")):
                files.add(path)
        if len(rows) < 100:
            break
    return files


def run_update(
    *,
    data_dir: str,
    files: List[str] | None = None,
    timeout: float = 30.0,
    dry_run: bool = False,
) -> int:
    """拉取五表与实际引用 ConfigAI（文件级断点；单件失败不阻塞他件）."""
    from hsr_nous.pipeline.build.update import download_with_etag

    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    targets = list(files) if files else list(TBGD_FILES)

    updated: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []
    etags: Dict[str, str] = {}

    def _download(filename: str) -> None:
        url = _download_url(filename)
        try:
            raw, etag = download_with_etag(url, timeout=timeout)
        except Exception as exc:
            print(f"[error] {filename}: {exc}", file=sys.stderr)
            failed.append(filename)
            return
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[error] {filename}: invalid JSON - {exc}", file=sys.stderr)
            failed.append(filename)
            return

        if etag:
            etags[filename] = etag

        local_path = root / filename
        if local_path.exists() and local_path.read_bytes() == raw:
            print(f"[skip] {filename}: identical to local")
            skipped.append(filename)
            return
        if dry_run:
            print(f"[would update] {filename}: {len(raw)} bytes")
            return
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(raw)
        print(f"[updated] {filename}: {len(raw)} bytes")
        updated.append(filename)

    for filename in targets:
        _download(filename)
    if not files:
        # 必须在五表之后：CharacterConfig/Ability 与 ConfigAI 都按实际引用顺序下载，避免 429。
        character_configs = _referenced_character_configs(root)
        available: set[str] = set()
        if character_configs:
            try:
                available = _remote_ability_file_index(timeout)
            except Exception as exc:
                print(f"[error] Config/ConfigAbility 文件索引: {exc}", file=sys.stderr)
                failed.append("Config/ConfigAbility index")
        for filename in _ability_companions(character_configs, available):
            targets.append(filename)
            _download(filename)
        for filename in _referenced_ai_paths(root):
            targets.append(filename)
            _download(filename)

    # 红线版本对齐校验（warn-only）：模板表在更新范围内且成功落盘（或本就在盘）才比对
    unreleased: List[str] = []
    if ("MonsterTemplateConfig.json" in targets
            and "MonsterTemplateConfig.json" not in failed and not dry_run):
        unreleased = _check_monster_alignment(root, timeout=timeout)
        for mid in unreleased:
            print(f"[warn] 疑似未发布内容: MonsterTemplateConfig id={mid} "
                  f"不在 Hakushin 已上线怪物花名册", file=sys.stderr)

    # ETag 表并入 manifest（--incr HEAD 快检用）：本跑新抓的覆盖，未抓的沿旧表
    manifest_path = root / "manifest.json"
    old_etags: Dict[str, str] = {}
    if manifest_path.exists():
        try:
            old_etags = dict(json.loads(manifest_path.read_text(encoding="utf-8")).get("etags") or {})
        except Exception:
            old_etags = {}
    old_etags.update(etags)
    manifest = {
        "source": "https://gitlab.com/Dimbreath/turnbasedgamedata",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "unreleased_warnings": unreleased,
        "etags": old_etags,
    }
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        from hsr_nous.pipeline.enemies.loader import clear_data_cache
        clear_data_cache()
    print(f"\n[summary] total={len(targets)}, updated={len(updated)}, "
          f"skipped={len(skipped)}, failed={len(failed)}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="turnbasedgamedata 敌人表与实际引用 Config 下载（GitLab raw）"
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
