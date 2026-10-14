"""数据环境探测：data/ 为 gitignored 本地数据，CI 无数据环境时数据依赖测试自动跳过.

workflow 注释（.github/workflows/test.yml）声明"数据依赖测试自带 skipif"——
本模块是该声明的实现：任何依赖 data/ 下游戏数据的测试，在数据缺失时跳过而不是 FileNotFoundError。

判定分级：四源各一判定 + 两个组合判定 + 两个生成件判定——测试按实际依赖挂对应判定，
不再一律捆绑三件套。tbgd 独立测试只查 turnbasedgamedata 落盘件（CI 可下载，不被 fandom
必需项误拦）；fandom 语义依赖测试只查 fandom_enemy_data.json（镜像/快照供给，未就位显式
标待补场景）；生成件（sim_templates 骨架 / tbgd_skill 提取产物）CI 由生成命令动态产出，
挂 sim_templates_available / tbgd_skill_available。
"""
from __future__ import annotations

from pathlib import Path

# 四源关键文件（各判定只查自己那组，互不绑架）
_STARRAILRES_REQUIRED = (
    "data/starrailres/index_new/cn/characters.json",   # pipeline.loader（角色/光锥/遗器——配装域）
)
_STAGE_REQUIRED = (
    "data/stages/hakushin/maze.json",                  # 期数编成域（hakushin 深渊期数主文件）
)
_TBGD_REQUIRED = (
    "data/turnbasedgamedata/MonsterTemplateConfig.json",  # turnbasedgamedata 可下载件（敌人机制域——CI 可拉）
)
_FANDOM_SEMANTIC_REQUIRED = (
    "data/fandom_enemy_data.json",                     # Fandom 语义文件（敌人机制描述文本——镜像/快照供给）
)


def _all_exist(paths: tuple[str, ...]) -> bool:
    return all(Path(p).exists() for p in paths)


def starrailres_available() -> bool:
    """配装域数据（StarRailRes）是否可用."""
    return _all_exist(_STARRAILRES_REQUIRED)


def stage_data_available() -> bool:
    """期数编成域数据（Hakushin/buhflipexplode）是否可用."""
    return _all_exist(_STAGE_REQUIRED)


def tbgd_data_available() -> bool:
    """turnbasedgamedata 可下载件是否可用——tbgd 独立测试挂本判定（CI 拉 tbgd 即可跑，不被 fandom 必需项误拦）."""
    return _all_exist(_TBGD_REQUIRED)


def fandom_semantic_available() -> bool:
    """Fandom 语义文件是否可用——fandom 语义依赖测试挂本判定（镜像/快照供给，未就位显式标待补场景）."""
    return _all_exist(_FANDOM_SEMANTIC_REQUIRED)


def enemy_data_available() -> bool:
    """敌人全量数据（= turnbasedgamedata + Fandom 语义两件）是否可用."""
    return tbgd_data_available() and fandom_semantic_available()


def sim_templates_available() -> bool:
    """生成器骨架（data/sim_templates——gitignored 纯生成物）是否已生成.

    CI 由 `python -m hsr_nous.adapters.template_generator` 动态全量生成（约 2 秒）；
    本地同命令跑一次即得。
    """
    d = Path("data/sim_templates/characters")
    return d.is_dir() and any(d.glob("*_*.yaml"))


def tbgd_skill_available() -> bool:
    """tbgd 技能机制提取产物（data/tbgd_skill_data.json——extract_tbgd_skills 产物）是否可用.

    CI 由 `python -m hsr_nous.pipeline.extract_tbgd_skills` 动态提取；本地同命令跑一次即得。
    """
    return Path("data/tbgd_skill_data.json").exists()


def generated_skip_reason() -> str:
    return "生成件缺失（data/sim_templates 或 data/tbgd_skill_data.json——跑 template_generator/extract_tbgd_skills 生成）"


def data_available() -> bool:
    """全量数据环境（原三件套语义）是否可用——全套依赖测试用."""
    return starrailres_available() and stage_data_available() and enemy_data_available()


def data_skip_reason() -> str:
    return "本地数据缺失（data/ 为 gitignored；CI 无数据环境，数据依赖测试按设计跳过）"


def fandom_pending_reason() -> str:
    return "Fandom 语义文件缺失（镜像/快照未就位——显式待补场景，不计入 CI 覆盖率）"
