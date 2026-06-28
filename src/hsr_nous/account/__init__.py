"""Mihoyo 账号集成：通过 HoYoLAB / 米游社 API 读取用户公开账号数据.

⚠️ 合规警告 ⚠️
本模块使用的是**非官方协议**（HoYoLAB API），存在账号风险。
- 仅读取公开可查数据：角色、命座、光锥、忘却之庭战绩、开拓力等
- 不向米哈游服务器写入任何数据
- 强烈建议使用 keyring 保管 ltuid/ltoken，不要硬编码
- 默认行为：未检测到 token 时立即返回友好提示，**绝不主动重试**

详见 docs/INTEGRATIONS.md。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 公开 re-exports
from hsr_nous.account.client import (
    AccountClient,
    AccountError,
    is_configured,
    get_owned_characters,
    get_trailblaze_power,
    get_moc_records,
)
from hsr_nous.account.models import OwnedCharacter, Eidolon, MoCRecord, AccountSnapshot

__all__ = [
    "AccountClient",
    "AccountError",
    "OwnedCharacter",
    "Eidolon",
    "MoCRecord",
    "AccountSnapshot",
    "is_configured",
    "get_owned_characters",
    "get_trailblaze_power",
    "get_moc_records",
]