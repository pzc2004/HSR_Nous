""".env 解析与仓库根环境加载（手写解析，零依赖）.

支持面 = 项目 `.env` 实际使用形态：`KEY=VALUE`、`#` 注释、值可带引号、行内 ` #`
注释、`export KEY=VALUE` 前缀。**不支持**多行值 / `${VAR}` 插值 / 裸键——
需要时先补测试再改实现（单一来源闸：`tests/test_doc_lint.py` 闸18）。

纪律：不覆盖已存在的环境变量（外部环境优先）；失败不抛（缺文件 → 空表/None）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from hsr_nous.common.paths import repo_root


def parse_env_file(path: Path) -> dict:
    """解析 .env → dict（纯函数，不写环境变量；文件缺失 → 空表）."""
    path = Path(path)
    if not path.exists():
        return {}
    parsed: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        key, value = key.strip(), value.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if not key:
            continue
        # 先剥行内注释（整值成对引号时 `#` 不算注释），再剥成对引号
        if " #" in value and not (len(value) >= 2 and value[0] == value[-1]
                                  and value[0] in ("'", '"')):
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        parsed[key] = value
    return parsed


def load_dotenv(path: Path) -> Optional[Path]:
    """解析 .env 并写入 ``os.environ``（``setdefault``——不覆盖已有变量）；文件缺失返回 None."""
    path = Path(path)
    parsed = parse_env_file(path)
    if not path.exists():
        return None
    for key, value in parsed.items():
        os.environ.setdefault(key, value)
    return path


def load_repo_env() -> Optional[Path]:
    """加载仓库根 ``.env``（仓库路径唯一事实源见 common.paths.repo_root）."""
    return load_dotenv(repo_root() / ".env")
