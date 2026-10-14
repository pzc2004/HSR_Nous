"""数据根路径解析——全项目唯一事实源.

解析优先级（逐层覆盖）：
1. ``HSR_NOUS_DATA_DIR`` 环境变量（CI/多份数据并存/自定义位置）；
2. 仓库 ``./data``（开发兜底——clone 即跑；XDG 用户目录为后续"数据搬家"期的默认，
   届时在此插入第三层，调用方零改动）。

两类数据命运不同：
- **缓存级**（starrailres/stages/fandom/tbgd/sim_templates/提取产物……gitignored，
  可重新下载/生成）——随 ``data_root()`` 走，可搬；
- **仓库内容**（``data/library`` 手写正典 / ``data/battles`` 策展对局——git 追踪，
  是项目内容的一部分）——永远仓库相对，不随 ``data_root()`` 移动。

约定：本模块只出**函数**（调用时才解析），不出 import 期冻结的路径常量——
否则环境变量覆盖会被 import 顺序架空。调用方已有的 ``data_dir`` 注入参数全部保留，
缺省值统一改从本模块出。
"""
from __future__ import annotations

import os
from pathlib import Path

#: 仓库根（src/hsr_nous/pipeline/paths.py → 上三级）
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: 环境变量名（sim_schema 侧模板根解析如需同名变量，由 doc_lint 镜像闸强制一致）
DATA_DIR_ENV = "HSR_NOUS_DATA_DIR"


def repo_root() -> Path:
    """仓库根目录."""
    return _REPO_ROOT


def data_root() -> Path:
    """数据根目录：``HSR_NOUS_DATA_DIR`` 环境变量 > 仓库 ./data."""
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else _REPO_ROOT / "data"


# ---------------------------------------------------------------------------
# 缓存级（随 data_root 走）
# ---------------------------------------------------------------------------

def starrailres_dir() -> Path:
    """StarRailRes 主数据（角色/光锥/遗器 index_new/{lang}/）."""
    return data_root() / "starrailres"


def stages_dir() -> Path:
    """关卡编成域根（hakushin/ + buhflipexplode/）."""
    return data_root() / "stages"


def monstervalue_path() -> Path:
    """Hakushin 全怪 base 值 + 修正系数（生成器敌人花名册/数值链主源）."""
    return stages_dir() / "hakushin" / "monstervalue.json"


def monster_meta_path() -> Path:
    """Hakushin monster.json（怪物元信息：rank/camp/weak/英文名）."""
    return stages_dir() / "hakushin" / "monster.json"


def hard_level_groups_path() -> Path:
    """Hakushin HardLevelGroup.json（敌人等级修正组）."""
    return stages_dir() / "hakushin" / "HardLevelGroup.json"


def elite_groups_path() -> Path:
    """Hakushin EliteGroup.json（精英修正组）."""
    return stages_dir() / "hakushin" / "EliteGroup.json"


def enemies_dir() -> Path:
    """theBowja 遗留敌人数据目录（enemies.json 所在——断更冻结保留）."""
    return data_root() / "enemies"


def fandom_enemy_path() -> Path:
    """Fandom 敌人机制语义文件（enemies/semantic 产物——语义补充，数值权威为 tbgd 五表）."""
    return data_root() / "fandom_enemy_data.json"


def fandom_skill_path() -> Path:
    """Fandom 技能机制语义文件（extract_fandom_skills 产物）."""
    return data_root() / "fandom_skill_data.json"


def turnbasedgamedata_dir() -> Path:
    """turnbasedgamedata 可下载件目录（Monster/Template/Skill/EliteGroup/HardLevelGroup 五件）."""
    return data_root() / "turnbasedgamedata"


def tbgd_file(name: str) -> Path:
    """turnbasedgamedata 配置文件路径（name 如 "MonsterConfig.json"——调用方逐件指名）."""
    return turnbasedgamedata_dir() / name


def tbgd_skill_path() -> Path:
    """tbgd 技能机制提取产物（extract_tbgd_skills 产物）."""
    return data_root() / "tbgd_skill_data.json"


def miyoushe_skill_path() -> Path:
    """米游社技能五项存量文件（源已归档停爬，crosscheck 可选校验列）."""
    return data_root() / "miyoushe_skill_data.json"


def sim_templates_dir() -> Path:
    """生成器骨架根（gitignored 纯生成物——template_generator main() 全量产出）."""
    return data_root() / "sim_templates"


def annotator_dir() -> Path:
    """打标 DAG 产物总根（runs/staging/notes 等子目录的父目录，gitignored）."""
    return data_root() / "annotator"


def annotator_runs_dir() -> Path:
    """打标 DAG 运行产物根（断点续跑/汇总，gitignored）."""
    return annotator_dir() / "runs"


# ---------------------------------------------------------------------------
# 仓库内容（git 追踪，不随 data_root 移动）
# ---------------------------------------------------------------------------

def library_dir() -> Path:
    """机制正典库（手写/机标全机制 DSL 模板——git 追踪，仓库内容）."""
    return _REPO_ROOT / "data" / "library"


def battles_dir() -> Path:
    """策展对局配置库（git 追踪，仓库内容）."""
    return _REPO_ROOT / "data" / "battles"
