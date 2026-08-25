"""参战单位定义：仿真器内部使用的角色/敌人表示."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StatBlock:
    """基础属性块.

    与 game_rules.md 和 properties.json 对齐的完整属性列表。
    """

    # 基础属性
    hp: float = 0.0
    atk: float = 0.0
    def_: float = 0.0
    spd: float = 100.0  # 默认速度，避免验证报错

    # 暴击
    crit_rate: float = 0.05       # 基础 5%
    crit_dmg: float = 0.50        # 基础 50%

    # 击破
    break_effect: float = 0.0     # 击破特攻
    # 削韧效率双池（01_formula §1.5 toughness_damage 式：(1+池1)×(1+池2) 乘算——spec 双池，实测待确认 B19）
    break_efficiency_boost: float = 0.0  # 池 1：削韧值提高（角色行迹/光锥族）
    weakness_break_efficiency_boost: float = 0.0  # 池 2：弱点击破效率提高（阮梅弦外音/遗器套装族）

    # 效果
    effect_hit: float = 0.0       # 效果命中
    effect_res: float = 0.0       # 效果抵抗

    # 穿透 / 易伤（伤害公式用）
    def_pen: float = 0.0          # 防御穿透（攻击方：无视防御% + 对目标减防%）
    res_pen: float = 0.0          # 抗性穿透（攻击方：含抗性降低）
    vulnerability: float = 0.0    # 易伤（受击方承受伤害提高）

    # 能量
    max_energy: float = 0.0       # 能量上限（从 characters.json max_sp）
    energy_regen: float = 1.0     # 能量恢复效率（基础 100%）

    # 治疗/护盾
    heal_bonus: float = 0.0       # 治疗量加成
    shield_bonus: float = 0.0     # 护盾加成

    # 增伤（按属性分类）
    dmg_bonus: Dict[str, float] = field(default_factory=dict)
    # 示例：{"physical": 0.0, "fire": 0.1, "ice": 0.0, ...}
    # 通用增伤放在 "all" 键

    # 抗性（按属性分类）
    resistance: Dict[str, float] = field(default_factory=dict)
    # 示例：{"physical": 0.2, "fire": 0.0, ...}

    # 弱点属性
    weakness: List[str] = field(default_factory=list)
    # 示例：["fire", "ice"]

    # 嘲讽值（受击概率权重）；0=未显式设置 → 查 rulebook 命途/忆灵表，再兜底 100
    taunt: float = 0.0
    # 存护=150, 毁灭=125, 同协/丰饶/虚无/记忆/欢愉=100, 智识/巡猎=75（rulebook taunt.path_base）

    # 韧性（敌人用）
    max_toughness: float = 0.0    # 韧性上限


@dataclass
class Actor:
    """参战单位（角色或敌人）."""

    actor_id: str
    name: str
    actor_type: str = "character"  # "character" | "monster"
    level: int = 80
    stats: StatBlock = field(default_factory=StatBlock)
    actions: List[str] = field(default_factory=list)
    # 技能等级（basic/skill/ultimate/talent；满级为常态默认——build.yaml skill_levels / 星魂 E3/E5 覆盖）
    skill_levels: Dict[str, int] = field(default_factory=lambda: {
        "basic": 6, "skill": 10, "ultimate": 10, "talent": 10})
    # 召唤归属（忆灵/召唤物 → 忆师/召唤者 actor_id）：受击回能归召唤者（mechanics 05 §5.1 忆灵回能交互）
    summoner_id: str = ""
    # 命途（英文 canonical key：destruction/harmony/...）——基础嘲讽查 rulebook path_base 用（mechanics 10）
    path: str = ""
