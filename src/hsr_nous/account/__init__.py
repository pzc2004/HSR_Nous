"""Mihoyo 账号集成：经 genshin.py 读取米游社账号数据（只读公开数据）.

⚠️ 合规警告 ⚠️
本模块使用**非官方协议**（经 genshin.py 封装的 HoYoLAB/米游社 API），存在账号风险。
- 仅读取公开可查数据：角色（含遗器/光锥/星魂/技能等级）、开拓力、忘却之庭战绩
- 不向米哈游服务器写入任何数据
- 强烈建议使用 keyring 保管 ltuid/ltoken，不要硬编码
- 默认行为：未配置或失败时静默返回 None，**绝不主动重试**

详见 docs/integrations.md。
"""
from __future__ import annotations

from hsr_nous.account.client import fetch_account_snapshot
from hsr_nous.account.models import (
    AccountCharacter,
    AccountLightCone,
    AccountRelic,
    AccountSnapshot,
    MoCRecord,
    RelicStat,
)
from hsr_nous.account.showcase import fetch_showcase_snapshot

__all__ = [
    "fetch_account_snapshot",
    "fetch_showcase_snapshot",
    "AccountCharacter",
    "AccountLightCone",
    "AccountRelic",
    "AccountSnapshot",
    "MoCRecord",
    "RelicStat",
]
