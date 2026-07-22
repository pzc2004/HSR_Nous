"""原始数据模型（Schema）：对应外部数据源（StarRailRes）的数据结构定义.

纯类型层：只做 dict 的类型化视图，不做文件加载。
文件 I/O（下载/加载/查询）统一走 pipeline。
"""

from hsr_nous.raw_schema.character import Character
from hsr_nous.raw_schema.character_promotion import CharacterPromotion
from hsr_nous.raw_schema.character_rank import CharacterRank
from hsr_nous.raw_schema.character_skill import CharacterSkill
from hsr_nous.raw_schema.character_skill_tree import CharacterSkillTree
from hsr_nous.raw_schema.element import Element
from hsr_nous.raw_schema.enemy import Enemy
from hsr_nous.raw_schema.light_cone import LightCone
from hsr_nous.raw_schema.light_cone_promotion import LightConePromotion
from hsr_nous.raw_schema.light_cone_rank import LightConeRank
from hsr_nous.raw_schema.path import Path as HsrPath
from hsr_nous.raw_schema.property import Property
from hsr_nous.raw_schema.relic import Relic, RelicSet
from hsr_nous.raw_schema.relic_affix import RelicMainAffix, RelicSubAffix

__all__ = [
    "Character",
    "CharacterSkill",
    "CharacterPromotion",
    "CharacterRank",
    "CharacterSkillTree",
    "LightCone",
    "LightConePromotion",
    "LightConeRank",
    "RelicSet",
    "Relic",
    "RelicMainAffix",
    "RelicSubAffix",
    "Element",
    "Enemy",
    "HsrPath",
    "Property",
]
