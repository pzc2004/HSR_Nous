"""数据域路径（pipeline 专用）——路径解析公共底盘在 ``hsr_nous/common/paths.py``.

两类数据命运不同：
- **缓存级**（starrailres/stages/fandom/tbgd/sim_templates/提取产物……gitignored，
  可重新下载/生成）——随 ``data_root()`` 走，可搬；
- **仓库内容**（``data/library`` 手写正典 / ``data/battles`` 策展对局——git 追踪，
  是项目内容的一部分）——永远仓库相对，不随 ``data_root()`` 移动。

本模块只保留**数据域专有**路径（starrailres/stages/... 与 library/battles 内容根）；
`repo_root()` / `repo_data_dir()` / `data_root()` / `DATA_DIR_ENV` 一律由
``hsr_nous.common.paths`` 转出（兼容壳：旧调用方 import 路径不变）。
约定：只出**函数**（调用时才解析），不出 import 期冻结的路径常量——否则环境变量
覆盖会被 import 顺序架空。调用方已有的 ``data_dir`` 注入参数全部保留。
"""
from __future__ import annotations

from pathlib import Path

from hsr_nous.common.paths import DATA_DIR_ENV, data_root, repo_data_dir, repo_root


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
    """Hakushin 全怪 base 值 + 修正系数（**冻结保留**：与 tbgd 五表全等已切源，
    停更留作回退/对拍参照——数值权威为 turnbasedgamedata，见 enemies/loader.py）."""
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
    """theBowja 遗留敌人数据目录（enemies.json 所在——断更 3.2，**冻结保留**：
    停更留作回退，数值权威为 turnbasedgamedata 五表）."""
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
    return repo_data_dir() / "library"


def battles_dir() -> Path:
    """策展对局配置库（git 追踪，仓库内容）."""
    return repo_data_dir() / "battles"
