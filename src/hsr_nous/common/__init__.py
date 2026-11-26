"""公共基座（common）：零项目依赖、无业务语义的基建（路径 / 环境变量 / IO 基元）.

边界规则（AGENTS.md「模块边界」+「模块分类」）：

- 本层**不 import 任何其它 `hsr_nous.*`**（只标准库；第三方依赖由消费方自持）；
- 其它**所有模块都允许 import 本层**——公共基座是唯一"人人可依赖"的叶子层；
- 只放无业务语义的基建：路径解析 / `.env` 与环境变量 / IO 基元。
  业务语义（游戏数据形状、模板、LLM 配置）一律留在各自模块。
"""
from __future__ import annotations

from hsr_nous.common.env import load_dotenv, load_repo_env, parse_env_file
from hsr_nous.common.paths import (
    DATA_DIR_ENV,
    RESEARCH_ROOT_ENV,
    data_root,
    repo_data_dir,
    repo_root,
    research_root,
)

__all__ = [
    "DATA_DIR_ENV",
    "RESEARCH_ROOT_ENV",
    "data_root",
    "load_dotenv",
    "load_repo_env",
    "parse_env_file",
    "repo_data_dir",
    "repo_root",
    "research_root",
]
