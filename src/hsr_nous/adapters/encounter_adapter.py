"""关卡适配器：将原始敌人数据转换为 sim_schema.Encounter."""

from typing import Any, Dict

from hsr_nous.sim_schema.encounter import Cycle, Encounter, Wave


def adapt_encounter(monster_data: Dict[str, Any]) -> Encounter:
    """将原始敌人数据转换为仿真器 Encounter.

    TODO: 实现波次、敌人等级、环境条件映射
    """
    return Encounter(
        encounter_id=str(monster_data.get("_id", "")),
        name=monster_data.get("name", ""),
    )
