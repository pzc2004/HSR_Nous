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
from hsr_nous.account import is_configured, get_owned_characters, get_trailblaze_power, get_moc_records

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


@tool
def query_my_account(filter_role: str = "all") -> str:
    """查询玩家自己的米游社账号拥有的角色。

    **需要配置 HSR_NOUS_HOYO_LTUID 和 HSR_NOUS_HOYO_LTOKEN**（详见 .env.example）。
    配置保存方式：可用 keyring（推荐）或 .env 文件。
    未配置时返回友好提示，不会抛出异常。

    Args:
        filter_role: 角色类型过滤 "all" / "dps" / "support" / "sustain"
                     仅作为输出分组提示，不实际过滤（账号数据不含 path 字段时按名字启发式判断）

    Returns:
        玩家角色列表的中文报告（含命座、等级、光锥ID、开拓力、忘却之庭战绩）。
    """
    if not is_configured():
        return (
            "未配置米游社账号。请在 .env 设置 HSR_NOUS_HOYO_LTUID 和 HSR_NOUS_HOYO_LTOKEN，"
            "或用 `python -c \"import keyring; keyring.set_password('hsr_nous', "
            "'HSR_NOUS_HOYO_LTOKEN', '你的ltoken')\"` 保存到 keyring。"
            "详见 docs/INTEGRATIONS.md。"
        )

    chars = get_owned_characters()
    power = get_trailblaze_power()
    moc = get_moc_records()

    lines = ["玩家账号概览：", ""]
    lines.append(f"开拓力: {power}")
    lines.append(f"角色总数: {len(chars)}")

    # 按命座降序，分组
    by_eidolon = sorted(chars, key=lambda c: -c.eidolon)
    lines.append("\n角色列表（按命座排序）：")
    for c in by_eidolon[:30]:
        lc_str = f"光锥 {c.light_cone_id} Lv.{c.light_cone_level}" if c.light_cone_id else "无光锥"
        lines.append(
            f"  - {c.name} (E{c.eidolon}, Lv.{c.level}, {lc_str})"
        )
    if len(by_eidolon) > 30:
        lines.append(f"  ... 等共 {len(by_eidolon)} 个")

    if moc:
        lines.append("\n忘却之庭战绩（最近 5 期）：")
        for r in moc[:5]:
            lines.append(
                f"  - 第{r.season}期 {r.name}: {r.stars}★ 最高 {r.max_floor}层 共{r.total_battles}战"
            )

    return "\n".join(lines)


# ----------------------------------------------------------------- 养成建议


# 高价值 DPS 角色（用于启发式推荐）
_HIGH_VALUE_DPS = {"Acheron", "Dan Heng • Imbibitor Lunae", "Firefly", "Jing Yuan", "Seele", "Argenti"}
_HIGH_VALUE_SUPPORT = {"Sparkle", "Ruan Mei", "Pela", "Bronya", "Silver Wolf"}
_HIGH_VALUE_SUSTAIN = {"Fu Xuan", "Luocha", "Huohuo", "Bailu", "Gepard"}


def _classify_char(name: str) -> str:
    if name in _HIGH_VALUE_DPS:
        return "dps"
    if name in _HIGH_VALUE_SUPPORT:
        return "support"
    if name in _HIGH_VALUE_SUSTAIN:
        return "sustain"
    return "unknown"


@tool
def recommend_investment(
    target_team: str = "",
    *,
    owned_chars: str = "",
) -> str:
    """基于玩家已有角色 + 目标配队，给出资源优先级建议。

    启发式评分（不依赖 LLM，可解释）：
    - 角色权重：DPS > Support > Sustain（影响配队核心度）
    - 命座缺口：E0→E2（高价值），E2→E4（中等），E4→E6（边际）
    - 已有高命座 DPS > 未拥有的辅助

    Args:
        target_team: 目标配队的 4 个角色名（用 + 分隔），如 "黄泉+花火+阮梅+符玄"
                     （中文名亦可，工具会做模糊匹配）
        owned_chars: 玩家已有角色摘要（用 `query_my_account` 的输出格式或
                     "name:E{n}" 列表，用 + 分隔），
                     如 "Acheron:E2+Sparkle:E1+Fu Xuan:E0"

    Returns:
        资源优先级的中文报告。
    """
    from hsr_nous.account import get_owned_characters

    # 1. 获取 owned chars（优先用真实账号，回退到传入字符串）
    owned: list = []
    if is_configured():
        owned = get_owned_characters()
    elif owned_chars:
        for token in owned_chars.replace("，", "+").split("+"):
            token = token.strip()
            if not token:
                continue
            if ":" in token:
                name, eid_str = token.split(":", 1)
                try:
                    eid = int(eid_str.replace("E", "").replace("e", ""))
                except ValueError:
                    eid = 0
                from hsr_nous.account.models import OwnedCharacter
                owned.append(OwnedCharacter(character_id="?", name=name.strip(), eidolon=eid))

    # 2. 解析 target_team
    target: list[str] = []
    if target_team:
        target = [t.strip() for t in target_team.replace("，", "+").split("+") if t.strip()]

    if not owned and not target:
        return (
            "无法生成建议：请提供 target_team 或配置米游社账号（HSR_NOUS_HOYO_*）。\n"
            "示例：recommend_investment('黄泉+花火+阮梅+符玄', 'Acheron:E2+Sparkle:E1+Fu Xuan:E0')"
        )

    # 3. 评分：每个目标角色给一个 investment_score
    lines = ["资源优先级建议：\n"]
    total_budget = 100.0  # 相对预算

    rows = []
    for char_name in target if target else [c.name for c in owned[:8]]:
        owned_match = next((c for c in owned if c.name == char_name), None)
        eid = owned_match.eidolon if owned_match else -1  # -1 表示未拥有
        category = _classify_char(char_name)

        # 类别权重：DPS=1.0, Support=0.7, Sustain=0.5
        cat_weight = {"dps": 1.0, "support": 0.7, "sustain": 0.5}.get(category, 0.3)

        # 命座缺口权重：当前越高优先级越低
        if eid == -1:
            gap_weight = 1.0  # 未拥有：最高优先级（先抽到）
            state = "未拥有"
        elif eid == 0:
            gap_weight = 0.85
            state = f"E{eid}"
        elif eid <= 2:
            gap_weight = 0.65
            state = f"E{eid}"
        elif eid <= 4:
            gap_weight = 0.35
            state = f"E{eid}"
        else:
            gap_weight = 0.15
            state = f"E{eid}（高命座）"

        score = cat_weight * gap_weight
        rows.append((score, char_name, state, category))

    # 4. 按分数降序
    rows.sort(key=lambda r: -r[0])
    raw_sum = sum(r[0] for r in rows) or 1.0
    for score, char_name, state, category in rows:
        budget_pct = score / raw_sum * 100
        lines.append(
            f"  - {char_name} ({category}, {state}): 投入 {budget_pct:.0f}% 资源"
        )

    lines.append("\n优先级说明：")
    lines.append("  1. 未拥有的高价值 DPS / Support 最优先（抽到或兑换）")
    lines.append("  2. 已拥有 E0-E2：拉光锥 + 遗器刷取优先")
    lines.append("  3. 已拥有 E4+：仅刷遗器毕业")

    return "\n".join(lines)
