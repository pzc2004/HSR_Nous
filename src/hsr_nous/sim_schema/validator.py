"""模拟器输入验证器：检查 Encounter 配置的合法性."""

from dataclasses import dataclass, field
from typing import List, Optional

from hsr_nous.sim_schema.actor import Actor, StatBlock
from hsr_nous.sim_schema.encounter import Cycle, Encounter, TerminationConfig, Wave
from hsr_nous.sim_schema.modifiers import Modifier


@dataclass
class ValidationError:
    """验证错误."""

    path: str
    """出错的字段路径，如 "actors[0].stats.hp"."""

    message: str
    """错误描述."""

    severity: str = "error"
    """严重程度：error | warning."""


@dataclass
class ValidationResult:
    """验证结果."""

    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, path: str, message: str) -> None:
        self.errors.append(ValidationError(path, message, "error"))

    def add_warning(self, path: str, message: str) -> None:
        self.warnings.append(ValidationError(path, message, "warning"))

    def merge(self, other: "ValidationResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


# ---------------------------------------------------------------------------
# 常量限制
# ---------------------------------------------------------------------------

MAX_TEAM_SIZE = 4
"""队伍最大角色数."""

MAX_ENEMIES_PER_WAVE = 10
"""每波次最大敌人数."""

MAX_WAVES = 10
"""最大波次数."""

MAX_CYCLES = 99
"""最大轮次数上限."""

MAX_ACTIONS_PER_ACTOR = 20
"""每个角色最大技能数."""

MAX_MODIFIER_STACK = 99
"""buff 最大叠层数."""

VALID_ACTOR_TYPES = {"character", "monster", "summon"}
"""合法的 actor_type 值."""

VALID_ACTION_TYPES = {"basic", "skill", "ultimate", "talent", "follow_up", "elation_damage", "memosprite_skill", "memosprite_talent"}
"""合法的 action_type 值."""

VALID_TARGET_TYPES = {"single", "blast", "aoe", "bounce", "self", "ally_single", "ally_aoe", "enemy_single", "enemy_blast", "enemy_aoe", "all_enemies", "all_allies"}
"""合法的 target_type 值."""

VALID_ELEMENT_TYPES = {"physical", "fire", "ice", "thunder", "wind", "quantum", "imaginary", None}
"""合法的 damage_type 值."""

VALID_MODIFIER_TYPES = {"buff", "debuff", "dot", "shield", "heal", "control"}
"""合法的 modifier_type 值."""

VALID_TERMINATION_MODES = {"fixed_av", "kill_target", "survival", "wipe"}
"""合法的结束条件模式."""


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------


def validate_encounter(encounter: Encounter) -> ValidationResult:
    """验证完整 Encounter 配置."""
    result = ValidationResult()

    # 基础字段
    if not encounter.encounter_id:
        result.add_error("encounter_id", "不能为空")

    if not encounter.name:
        result.add_warning("name", "建议填写名称")

    # 验证各组件
    result.merge(validate_globals(encounter.globals))
    result.merge(validate_actors(encounter.actors))
    result.merge(validate_waves(encounter.waves))
    result.merge(validate_cycle(encounter.cycle))
    result.merge(validate_termination(encounter.termination))

    return result


def validate_globals(globals_dict: dict) -> ValidationResult:
    """验证全局状态."""
    result = ValidationResult()

    if "skill_points" in globals_dict:
        sp = globals_dict["skill_points"]
        if "max" in sp and sp["max"] < 0:
            result.add_error("globals.skill_points.max", "不能为负数")
        if "current" in sp and "max" in sp:
            if sp["current"] > sp["max"]:
                result.add_error("globals.skill_points.current", "不能超过 max")

    return result


def validate_actors(actors: list) -> ValidationResult:
    """验证参战单位列表."""
    result = ValidationResult()

    # 分离角色和敌人
    characters = [a for a in actors if isinstance(a, Actor) and a.actor_type == "character"]
    monsters = [a for a in actors if isinstance(a, Actor) and a.actor_type in ("monster", "summon")]

    # 角色数量限制
    if len(characters) > MAX_TEAM_SIZE:
        result.add_error("actors", f"角色数量 ({len(characters)}) 超过上限 ({MAX_TEAM_SIZE})")

    if len(characters) == 0:
        result.add_warning("actors", "没有角色单位")

    # 验证每个 Actor
    for i, actor in enumerate(actors):
        if not isinstance(actor, Actor):
            result.add_error(f"actors[{i}]", "必须是 Actor 实例")
            continue
        result.merge(validate_actor(actor, f"actors[{i}]"))

    return result


def validate_actor(actor: Actor, path: str) -> ValidationResult:
    """验证单个 Actor."""
    result = ValidationResult()

    # 基础字段
    if not actor.actor_id:
        result.add_error(f"{path}.actor_id", "不能为空")

    if not actor.name:
        result.add_warning(f"{path}.name", "建议填写名称")

    if actor.actor_type not in VALID_ACTOR_TYPES:
        result.add_error(f"{path}.actor_type", f"非法值 '{actor.actor_type}'，合法值: {VALID_ACTOR_TYPES}")

    if actor.level < 1 or actor.level > 90:
        result.add_error(f"{path}.level", f"等级 ({actor.level}) 必须在 1-90 之间")

    # 验证属性
    result.merge(validate_stats(actor.stats, f"{path}.stats"))

    # 验证技能
    if len(actor.actions) > MAX_ACTIONS_PER_ACTOR:
        result.add_error(f"{path}.actions", f"技能数量 ({len(actor.actions)}) 超过上限 ({MAX_ACTIONS_PER_ACTOR})")

    return result


def validate_stats(stats: StatBlock, path: str) -> ValidationResult:
    """验证属性块."""
    result = ValidationResult()

    # 非负检查
    if stats.hp < 0:
        result.add_error(f"{path}.hp", "不能为负数")
    if stats.atk < 0:
        result.add_error(f"{path}.atk", "不能为负数")
    if stats.def_ < 0:
        result.add_error(f"{path}.def_", "不能为负数")
    if stats.spd <= 0:
        result.add_error(f"{path}.spd", "速度必须大于 0")

    # 暴击率范围
    if stats.crit_rate < 0 or stats.crit_rate > 1:
        result.add_warning(f"{path}.crit_rate", f"暴击率 ({stats.crit_rate}) 通常在 0-1 之间")

    # 暴击伤害
    if stats.crit_dmg < 0:
        result.add_error(f"{path}.crit_dmg", "不能为负数")

    # 能量
    if stats.max_energy < 0:
        result.add_error(f"{path}.max_energy", "不能为负数")
    if stats.energy < 0:
        result.add_error(f"{path}.energy", "不能为负数")
    if stats.max_energy > 0 and stats.energy > stats.max_energy:
        result.add_error(f"{path}.energy", f"当前能量 ({stats.energy}) 不能超过上限 ({stats.max_energy})")

    # 能量恢复效率
    if stats.energy_regen < 0:
        result.add_error(f"{path}.energy_regen", "不能为负数")

    # 韧性
    if stats.max_toughness < 0:
        result.add_error(f"{path}.max_toughness", "不能为负数")
    if stats.toughness < 0:
        result.add_error(f"{path}.toughness", "不能为负数")
    if stats.max_toughness > 0 and stats.toughness > stats.max_toughness:
        result.add_error(f"{path}.toughness", f"当前韧性 ({stats.toughness}) 不能超过上限 ({stats.max_toughness})")

    # 嘲讽值
    if stats.taunt < 0:
        result.add_error(f"{path}.taunt", "不能为负数")

    return result


def validate_waves(waves: list) -> ValidationResult:
    """验证波次配置."""
    result = ValidationResult()

    if len(waves) > MAX_WAVES:
        result.add_error("waves", f"波次数 ({len(waves)}) 超过上限 ({MAX_WAVES})")

    for i, wave in enumerate(waves):
        if not isinstance(wave, Wave):
            result.add_error(f"waves[{i}]", "必须是 Wave 实例")
            continue
        result.merge(validate_wave(wave, f"waves[{i}]"))

    return result


def validate_wave(wave: Wave, path: str) -> ValidationResult:
    """验证单个波次."""
    result = ValidationResult()

    if wave.wave_index < 1:
        result.add_error(f"{path}.wave_index", "波次索引必须 >= 1")

    if len(wave.enemy_ids) > MAX_ENEMIES_PER_WAVE:
        result.add_error(f"{path}.enemy_ids", f"敌人数 ({len(wave.enemy_ids)}) 超过上限 ({MAX_ENEMIES_PER_WAVE})")

    if len(wave.enemy_ids) == 0:
        result.add_warning(f"{path}.enemy_ids", "波次没有敌人")

    if len(wave.enemy_ids) != len(wave.enemy_levels):
        result.add_error(f"{path}", "enemy_ids 和 enemy_levels 长度不一致")

    return result


def validate_cycle(cycle: Optional[Cycle]) -> ValidationResult:
    """验证轮次配置."""
    result = ValidationResult()

    if cycle is None:
        return result

    if not isinstance(cycle, Cycle):
        result.add_error("cycle", "必须是 Cycle 实例")
        return result

    if cycle.first_cycle_av < 1:
        result.add_error("cycle.first_cycle_av", "首轮 AV 必须 >= 1")

    if cycle.subsequent_cycle_av < 1:
        result.add_error("cycle.subsequent_cycle_av", "后续轮次 AV 必须 >= 1")

    if cycle.max_cycles < 0:
        result.add_error("cycle.max_cycles", "最大轮次数不能为负数")

    if cycle.max_cycles > MAX_CYCLES:
        result.add_error("cycle.max_cycles", f"最大轮次数 ({cycle.max_cycles}) 超过上限 ({MAX_CYCLES})")

    return result


def validate_termination(termination: TerminationConfig) -> ValidationResult:
    """验证结束条件."""
    result = ValidationResult()

    if termination.mode not in VALID_TERMINATION_MODES:
        result.add_error("termination.mode", f"非法模式 '{termination.mode}'，合法值: {VALID_TERMINATION_MODES}")

    if termination.max_turns < 1:
        result.add_error("termination.max_turns", "最大回合数必须 >= 1")

    if termination.max_action_value < 1:
        result.add_error("termination.max_action_value", "最大行动值必须 >= 1")

    if termination.mode == "kill_target" and not termination.target_ids:
        result.add_warning("termination.target_ids", "kill_target 模式下建议指定目标 ID")

    return result


def validate_modifier(modifier: Modifier, path: str) -> ValidationResult:
    """验证 Modifier."""
    result = ValidationResult()

    if not modifier.modifier_id:
        result.add_error(f"{path}.modifier_id", "不能为空")

    if modifier.modifier_type not in VALID_MODIFIER_TYPES:
        result.add_error(f"{path}.modifier_type", f"非法类型 '{modifier.modifier_type}'，合法值: {VALID_MODIFIER_TYPES}")

    if modifier.duration < 0:
        result.add_error(f"{path}.duration", "不能为负数")

    if modifier.max_stack < 1:
        result.add_error(f"{path}.max_stack", "必须 >= 1")

    if modifier.max_stack > MAX_MODIFIER_STACK:
        result.add_error(f"{path}.max_stack", f"叠层数 ({modifier.max_stack}) 超过上限 ({MAX_MODIFIER_STACK})")

    return result
