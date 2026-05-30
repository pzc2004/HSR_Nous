"""角色技能原始数据模型."""

from typing import Any, Dict, List, Optional


class CharacterSkill:
    """角色技能.

    数据来源:
    - StarRailRes: id, name, element, type, effect, params 等
    - Fandom wiki: energy_cost, energy_gen, toughness_dmg, sp_cost, sp_gain, enhanced
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    @property
    def id(self) -> str:
        return self._data.get("id", "")

    @property
    def name(self) -> str:
        return self._data.get("name", "")

    @property
    def max_level(self) -> int:
        return self._data.get("max_level", 0)

    @property
    def element(self) -> str:
        return self._data.get("element", "")

    @property
    def type(self) -> str:
        return self._data.get("type", "")

    @property
    def type_text(self) -> str:
        return self._data.get("type_text", "")

    @property
    def effect(self) -> str:
        return self._data.get("effect", "")

    @property
    def effect_text(self) -> str:
        return self._data.get("effect_text", "")

    @property
    def simple_desc(self) -> str:
        return self._data.get("simple_desc", "")

    @property
    def desc(self) -> str:
        return self._data.get("desc", "")

    @property
    def params(self) -> List[List[float]]:
        return self._data.get("params", [])

    @property
    def icon(self) -> str:
        return self._data.get("icon", "")

    # ----- 以下字段来自 Fandom wiki（pipeline 合并时填入）-----

    @property
    def energy_cost(self) -> Optional[int]:
        """终结技能量消耗."""
        v = self._data.get("energy_cost")
        return int(v) if v else None

    @property
    def energy_gen(self) -> Optional[int]:
        """回能值."""
        v = self._data.get("energy_gen")
        return int(v) if v else None

    @property
    def toughness_dmg(self) -> Optional[int]:
        """削韧值."""
        v = self._data.get("toughness_dmg")
        return int(v) if v else None

    @property
    def sp_cost(self) -> int:
        """战技点消耗."""
        return self._data.get("sp_cost", 0)

    @property
    def sp_gain(self) -> int:
        """战技点回复."""
        return self._data.get("sp_gain", 0)

    @property
    def enhanced(self) -> bool:
        """是否为强化版本."""
        return self._data.get("enhanced", False)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)
