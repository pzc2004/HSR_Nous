"""数据查询工具：封装 pipeline/ 为 LangChain Tools."""

from langchain_core.tools import tool
from hsr_nous.pipeline import (
    get_character_full,
    get_character_by_name,
    calc_character_stats,
    load_relic_sets,
    get_enemy,
    list_characters,
    list_enemies,
    list_relic_sets,
)

_LANG = "cn"

# 元素英文 → 中文映射
_ELEMENT_CN = {
    "Fire": "火", "Ice": "冰", "Imaginary": "虚数",
    "Physical": "物理", "Quantum": "量子", "Thunder": "雷", "Wind": "风",
}

# 命途英文 → 中文映射
_PATH_CN = {
    "Knight": "存护", "Priest": "丰饶", "Warrior": "毁灭",
    "Rogue": "巡猎", "Mage": "智识", "Shaman": "同谐",
    "Warlock": "虚无", "Elation": "欢愉", "Memory": "记忆",
}


def _fmt_pct(val: float) -> str:
    """将小数格式化为百分比（如 0.05 → '5.0%'）."""
    return f"{val * 100:.1f}%"


def _fmt_stat(key: str, val) -> str:
    """根据属性类型格式化数值."""
    if key in ("crit_rate", "crit_dmg"):
        return _fmt_pct(val) if isinstance(val, (int, float)) else str(val)
    if isinstance(val, float):
        return f"{val:.1f}"
    return str(val)


@tool
def query_character(character_name: str) -> str:
    """查询角色的完整信息，包括属性、技能、行迹、星魂等。

    Args:
        character_name: 角色名称，支持中文，如 "黄泉"、"花火"、"阮梅"
    """
    char = get_character_by_name(character_name, lang=_LANG)
    if not char:
        all_chars = list_characters(lang=_LANG)
        matches = [(cid, name) for cid, name in all_chars if character_name in name]
        if matches:
            return f"未找到角色 '{character_name}'，你是否想找：{', '.join(name for _, name in matches[:5])}"
        return f"未找到角色: {character_name}"

    full = get_character_full(char["id"], lang=_LANG)
    if not full:
        return f"无法获取 {character_name} 的完整数据"

    try:
        stats = calc_character_stats(char["id"], level=80, lang=_LANG)
    except Exception:
        stats = {}

    skills = full.get("skills_detail", [])
    ranks = full.get("ranks_detail", [])

    element = _ELEMENT_CN.get(full.get("element", ""), full.get("element", "未知"))
    path = _PATH_CN.get(full.get("path", ""), full.get("path", "未知"))

    return f"""角色名称: {full.get('name', character_name)}
ID: {full.get('id', '未知')}
属性: {element}
命途: {path}
稀有度: {'★' * full.get('rarity', 0)}

Lv.80 基础属性:
  HP: {_fmt_stat('hp', stats.get('hp', '未知'))}
  攻击力: {_fmt_stat('atk', stats.get('atk', '未知'))}
  防御力: {_fmt_stat('def', stats.get('def', '未知'))}
  速度: {_fmt_stat('spd', stats.get('spd', '未知'))}
  暴击率: {_fmt_stat('crit_rate', stats.get('crit_rate', '未知'))}
  暴击伤害: {_fmt_stat('crit_dmg', stats.get('crit_dmg', '未知'))}

技能数量: {len(skills)}
星魂数量: {len(ranks)}
"""


@tool
def query_character_stats(character_name: str, level: int = 80) -> str:
    """计算角色在指定等级下的基础属性面板。

    Args:
        character_name: 角色名称
        level: 目标等级（1-80），默认 80
    """
    char = get_character_by_name(character_name, lang=_LANG)
    if not char:
        return f"未找到角色: {character_name}"

    try:
        stats = calc_character_stats(char["id"], level=level, lang=_LANG)
    except Exception as e:
        return f"计算属性失败: {e}"

    return f"""{character_name} Lv.{level} 基础属性:
  HP: {_fmt_stat('hp', stats.get('hp', '未知'))}
  攻击力: {_fmt_stat('atk', stats.get('atk', '未知'))}
  防御力: {_fmt_stat('def', stats.get('def', '未知'))}
  速度: {_fmt_stat('spd', stats.get('spd', '未知'))}
  暴击率: {_fmt_stat('crit_rate', stats.get('crit_rate', '未知'))}
  暴击伤害: {_fmt_stat('crit_dmg', stats.get('crit_dmg', '未知'))}
"""


@tool
def query_relic_sets() -> str:
    """查询所有遗器套装的效果。返回遗器套装列表，包括 2 件套和 4 件套效果。"""
    relic_sets = load_relic_sets(lang=_LANG)

    result = "遗器套装列表：\n\n"
    for set_id, set_data in relic_sets.items():
        name = set_data.get("name", "未知")
        desc_2 = set_data.get("desc", ["", ""])[0] if len(set_data.get("desc", [])) > 0 else ""
        desc_4 = set_data.get("desc", ["", ""])[1] if len(set_data.get("desc", [])) > 1 else ""

        result += f"【{name}】\n"
        if desc_2:
            result += f"  2件套: {desc_2}\n"
        if desc_4:
            result += f"  4件套: {desc_4}\n"
        result += "\n"

    return result


@tool
def query_enemy(enemy_name: str) -> str:
    """查询敌人的弱点、抗性、技能等信息。

    Args:
        enemy_name: 敌人名称，如 "冰锋"、"无尽寒冬之槊"
    """
    all_enemies = list_enemies()
    matches = [(eid, name) for eid, name in all_enemies if enemy_name in name]

    if not matches:
        return f"未找到敌人: {enemy_name}"

    enemy_id, enemy_display_name = matches[0]
    enemy = get_enemy(enemy_id)

    if not enemy:
        return f"无法获取敌人数据: {enemy_display_name}"

    weaknesses = enemy.get("ElementalWeaknesses", [])
    resistance = enemy.get("ElementalResistance", {})
    skills = enemy.get("SkillList", [])

    result = f"""敌人: {enemy_display_name}
ID: {enemy.get('Id', enemy_id)}

弱点: {', '.join(weaknesses) if weaknesses else '无'}

抗性:
"""
    for element, value in resistance.items():
        result += f"  {element}: {value:.0%}\n"

    if skills:
        result += f"\n技能: {len(skills)} 个\n"
        for skill in skills[:5]:
            result += f"  - {skill.get('Name', '未知')}\n"

    return result


@tool
def list_all_characters() -> str:
    """列出游戏中所有可用的角色。"""
    chars = list_characters(lang=_LANG)
    result = f"共有 {len(chars)} 个角色：\n"
    result += ", ".join(name for _, name in chars)
    return result


@tool
def list_all_enemies() -> str:
    """列出游戏中所有可用的敌人。"""
    enemies = list_enemies()
    result = f"共有 {len(enemies)} 个敌人：\n"
    unique_names = list(dict.fromkeys(name for _, name in enemies if name))
    result += ", ".join(unique_names[:50])
    if len(unique_names) > 50:
        result += f"... 等共 {len(unique_names)} 个"
    return result


@tool
def list_all_relic_sets() -> str:
    """列出游戏中所有可用的遗器套装。"""
    relic_sets = list_relic_sets(lang=_LANG)
    result = f"共有 {len(relic_sets)} 个遗器套装：\n"
    result += ", ".join(name for _, name in relic_sets)
    return result
