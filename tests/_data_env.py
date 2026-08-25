"""数据环境探测：data/ 为 gitignored 本地数据，CI 无数据环境时数据依赖测试自动跳过.

workflow 注释（.github/workflows/test.yml）声明"数据依赖测试自带 skipif"——
本模块是该声明的实现：任何依赖 data/ 下游戏数据的测试，在数据缺失时跳过而不是 FileNotFoundError。
"""
from __future__ import annotations

from pathlib import Path

# 关键数据文件：任缺其一即视为"无数据环境"
_REQUIRED = (
    "data/starrailres/index_new/cn/characters.json",   # pipeline.loader（角色/光锥/遗器）
    "data/stages/hakushin/monstervalue.json",          # 敌人 calc 公式链
    "data/fandom_enemy_data.json",                     # 敌人技能/抗性
)


def data_available() -> bool:
    """本地数据环境是否可用."""
    return all(Path(p).exists() for p in _REQUIRED)


def data_skip_reason() -> str:
    return "本地数据缺失（data/ 为 gitignored；CI 无数据环境，数据依赖测试按设计跳过）"
