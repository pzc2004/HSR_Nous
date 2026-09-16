"""参战单位定义：仿真器内部使用的角色/敌人表示."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

#: 命途 canonical key 闭合词表（03_actor §3.1 Actor.path）——词表唯一源。
#: 全集从官方数据派生（StarRailRes characters.json path 原值经 PATH_ALIASES 映射的
#: 值集；tests/test_path_enum_gate.py 派生闸双向对账，新命途入库先同步本表），
#: 词表外值编译期炸（build_compiler path 闸——'the_hunt'/'rogue' 类拼写分裂的正解指路）。
PATHS = frozenset({
    "destruction",  # 毁灭（官方内部类目 Warrior）
    "erudition",    # 智识（Mage）
    "hunt",         # 巡猎（Rogue——canonical 是 hunt 不是 the_hunt/rogue）
    "harmony",      # 同谐（Shaman）
    "nihility",     # 虚无（Warlock）
    "preservation",  # 存护（Knight）
    "abundance",    # 丰饶（Priest）
    "remembrance",  # 记忆（Memory）
    "elation",      # 欢愉（Elation——官方数据本名即 canonical）
})

#: 命途拼写别名 → canonical key（StarRailRes 内部类目名小写 + 历史打标漂移拼写）。
#: **别名不是合法值**——模板 `path:` 写别名照样编译期炸（合法态只有 PATHS 一种）；
#: 本表仅两消费口：① adapters 生成器 canonical 化（_internal_path——官方数据原值
#: 是内部类目名，入库前必须映射）；② build_compiler path 闸报错指路（非法值命中
#: 本表时给出正解）。官方内部类目名与漂移拼写同表——都是"非 canonical 但认得"
#: 的写法，新命途的内部类目名入库时补录。
PATH_ALIASES = {
    # StarRailRes characters.json path 原值（小写后）——生成器 canonical 化通道
    "warrior": "destruction",
    "mage": "erudition",
    "rogue": "hunt",
    "shaman": "harmony",
    "warlock": "nihility",
    "knight": "preservation",
    "priest": "abundance",
    "memory": "remembrance",
    # 历史打标漂移拼写（2026-09-17 三分裂病灶勘正——闸报错正解指路用）
    "the_hunt": "hunt",
    "nihilism": "nihility",
}


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
    # 欢愉（21_elation）：欢愉度面板属性（与击破特攻同族——数值即百分比池，flat 加算；
    # 行迹 ElationDamageAddedRatioBase〔CN「欢愉度强化」〕→ 本键，elation_multi = 1+elation）
    elation: float = 0.0
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
    # 追加韧性条（03_actor §3.10，虚韧性族）：主条归零后按加入序承接的追加条 max 列表；
    # 空 = 单条模型（缺省，与多条前行为一致）
    toughness_bars: List[float] = field(default_factory=list)


@dataclass
class Actor:
    """参战单位（角色或敌人）."""

    actor_id: str
    name: str
    actor_type: str = "character"  # "character" | "monster" | "summon"（忆灵/召唤物，12_summon）
    level: int = 80
    stats: StatBlock = field(default_factory=StatBlock)
    actions: List[str] = field(default_factory=list)
    # 技能等级（basic/skill/ultimate/talent；满级为常态默认——build.yaml skill_levels / 星魂 E3/E5 覆盖）
    skill_levels: Dict[str, int] = field(default_factory=lambda: {
        "basic": 6, "skill": 10, "ultimate": 10, "talent": 10})
    # 召唤归属（忆灵/召唤物 → 忆师/召唤者 actor_id）：受击回能归召唤者（mechanics 05 §5.1 忆灵回能交互）
    summoner_id: str = ""
    # 召唤物能力闸（12_summon §12.4 通用约定：能力集合**默认全开**，仅技能文本明确否认的
    # 逐实例显式 false——如小伊卡 {"av": false} 不上行动条、Netherwing {"enemy_targetable": false}）。
    # 键：av（上行动条）/ enemy_targetable / ally_targetable / taunt（参与嘲讽加权）；空 dict=全开
    summon_flags: Dict[str, bool] = field(default_factory=dict)
    # 命途（英文 canonical key——闭合词表 PATHS（本文件唯一源，官方数据派生全集），
    # 词表外编译期炸）——基础嘲讽查 rulebook path_base / count_team / path_of 消费（mechanics 10）
    path: str = ""
    # 分组标签（开放命名空间：`faction:xxx` 阵营/官方分组——黄金裔族；`path:<name>` 由
    # in_group 按 path 字段自动映射，不入本表）——in_group/count_team(group=...) 消费（03_actor §3.1）
    groups: List[str] = field(default_factory=list)
    # 元素（伤害属性，英文小写 canonical key——动态元素族取数源：element_of 宿主函数，
    # 丹恒•腾荒 1414 同袍"相应属性"附加伤害首实例）；"" = 未声明（element_of 缺省口径）
    element: str = ""
    # 参演编号（21_elation §21.1——阿哈时刻欢愉技触发序，越小越先；固定数值同能量上限
    # 性质，官方数据文本无字段=模板手填标源）；0 = 非欢愉角色/未声明
    elation_number: int = 0
