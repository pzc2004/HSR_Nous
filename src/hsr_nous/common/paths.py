"""公共路径解析：仓库根 / 数据根 / 研究产物根（全项目唯一事实源）.

数据根解析优先级（逐层覆盖）：
1. ``HSR_NOUS_DATA_DIR`` 环境变量（CI/多份数据并存/自定义位置）；
2. 仓库 ``./data``（开发兜底）。

研究产物根独立解析：``HSR_NOUS_RESEARCH_ROOT`` > ``Path.home()/HSR_Nous``；
绝不默认写仓库或 CWD。

两类数据命运不同：
- **缓存级**（starrailres/stages/fandom/tbgd/sim_templates/提取产物……gitignored，
  可重新下载/生成）——随 ``data_root()`` 走，可搬；
- **仓库内容**（``data/library`` 手写正典 / ``data/battles`` 策展对局——git 追踪，
  是项目内容的一部分）——永远仓库相对，不随 ``data_root()`` 移动。

约定：本模块只出**函数**（调用时才解析），不出 import 期冻结的路径常量——
否则环境变量覆盖会被 import 顺序架空。
"""
from __future__ import annotations

import os
from pathlib import Path

#: 仓库根（src/hsr_nous/common/paths.py → 上四级：common → hsr_nous → src → 仓库根）
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: 环境变量名（pipeline/sim_schema 曾各自镜像此名——已收敛到本层单一定义）
DATA_DIR_ENV = "HSR_NOUS_DATA_DIR"
RESEARCH_ROOT_ENV = "HSR_NOUS_RESEARCH_ROOT"


def repo_root() -> Path:
    """仓库根目录."""
    return _REPO_ROOT


def repo_data_dir() -> Path:
    """仓库内 ``data/`` 目录（仓库内容根——library/battles 恒挂其下，不随 env 移动）."""
    return _REPO_ROOT / "data"


def data_root() -> Path:
    """数据根目录：``HSR_NOUS_DATA_DIR`` 环境变量 > 仓库 ``./data``."""
    env = os.environ.get(DATA_DIR_ENV)
    return Path(env) if env else repo_data_dir()


def research_root() -> Path:
    """研究产物根：``HSR_NOUS_RESEARCH_ROOT`` > 用户 home 下的 ``HSR_Nous``."""
    env = os.environ.get(RESEARCH_ROOT_ENV)
    return Path(env) if env else Path.home() / "HSR_Nous"
