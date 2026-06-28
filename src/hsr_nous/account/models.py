"""Mihoyo 账号数据模型.

所有 dataclass 都是只读快照——agent/builder 等模块使用，但不要原地修改。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Eidolon:
    """星魂（命座）信息."""

    eidolon_id: str
    name: str
    unlocked: bool = False


@dataclass
class OwnedCharacter:
    """用户拥有的角色（含命座、光锥、遗器主信息）.

    与 raw_schema.Character 的区别：包含账号特有字段（命座解锁数、等级、装备）。
    """

    character_id: str  # StarRailRes ID，如 "1308"（Acheron）
    name: str
    level: int = 1
    ascension: int = 0  # 突破阶段 0-6
    eidolon: int = 0  # 命座解锁数 0-6
    light_cone_id: Optional[str] = None
    light_cone_level: int = 1
    relic_set_ids: List[str] = field(default_factory=list)
    # 详细信息（API 返回的原始 avatar_info，可选）
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MoCRecord:
    """忘却之庭战绩."""

    season: int
    name: str = ""
    stars: int = 0  # 该期总星数
    max_floor: int = 0  # 通关最高层数
    total_battles: int = 0


@dataclass
class AccountSnapshot:
    """账号完整快照（一次拉取包含全部信息）."""

    uid: str
    nickname: str = ""
    level: int = 0  # 开拓等级
    trailblaze_power: int = 0  # 当前开拓力
    owned_characters: List[OwnedCharacter] = field(default_factory=list)
    moc_records: List[MoCRecord] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)