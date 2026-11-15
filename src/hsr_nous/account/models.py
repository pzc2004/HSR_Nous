"""米游社账号领域模型.

纯账号事实的冻结快照——不认识 sim_schema / build.yaml / canonical key,
schema 映射归 `adapters/account_adapter.py`（防腐层，依赖只指向稳定侧）。
API 原始词条名原样保留（如 "ATKAddedRatio"），canonical 化不在本层。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class RelicStat:
    """单条遗器词条快照（API 原始形态）."""

    name: str      # API 原始词条名（如 "ATKAddedRatio" / 中文显示名，随 lang）
    value: str     # API 原始值串（如 "43.0" / "10.4%"——解析归 adapter）
    times: int = 1 # 强化次数


@dataclass(frozen=True)
class AccountRelic:
    """单件遗器（位面饰品并入，pos 区分槽位）."""

    id: str
    name: str
    pos: int          # 槽位 1-6（1-4 遗器，5-6 位面饰品）
    level: int = 0
    rarity: int = 5
    set_id: str = ""
    main: Optional[RelicStat] = None
    subs: Tuple[RelicStat, ...] = ()


@dataclass(frozen=True)
class AccountLightCone:
    """装备中的光锥."""

    id: str
    name: str
    level: int = 1
    superimposition: int = 1   # 叠影
    rarity: int = 5


@dataclass(frozen=True)
class AccountCharacter:
    """账号拥有的角色（genshin 详情端点全粒度）."""

    id: str                 # 官方角色 ID（如 "1308"）
    name: str
    level: int = 1
    eidolon: int = 0        # 已解锁星魂数 0-6
    unlocked_eidolons: Tuple[str, ...] = ()   # 已解锁星魂名称明细
    path: str = ""          # 命途（API 原值）
    element: str = ""       # 元素（API 原值）
    skill_levels: Dict[str, int] = field(default_factory=dict)  # point_id → 等级
    light_cone: Optional[AccountLightCone] = None
    relics: Tuple[AccountRelic, ...] = ()
    panel: Dict[str, float] = field(default_factory=dict)  # 计算面板（属性名→final 值）
    has_memosprite: bool = False  # 忆灵


@dataclass(frozen=True)
class MoCRecord:
    """忘却之庭战绩."""

    season: int
    name: str = ""
    stars: int = 0          # 该期总星数
    max_floor: int = 0      # 通关最高层数
    total_battles: int = 0


@dataclass(frozen=True)
class AccountSnapshot:
    """账号完整快照（一次拉取）."""

    uid: str
    nickname: str = ""
    level: int = 0          # 开拓等级
    trailblaze_power: int = 0
    characters: Tuple[AccountCharacter, ...] = ()
    moc_records: Tuple[MoCRecord, ...] = ()
