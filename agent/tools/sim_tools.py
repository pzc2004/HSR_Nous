"""战斗模拟工具：封装 sim/ 为 LangChain Tools.

当前为占位实现，返回简化的模拟数据。
等 sim/ 引擎完成后，替换为真实的战斗模拟。
"""

from langchain_core.tools import tool


@tool
def simulate_battle(
    team_config: str,
    relic_set: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
) -> str:
    """运行战斗模拟器，返回 DPS、生存率等指标。

    这个工具模拟不同队伍配置和遗器搭配的战斗效果。

    Args:
        team_config: 队伍配置，格式为"角色1+角色2+角色3+角色4"，如"黄泉+花火+阮梅+符玄"
        relic_set: 遗器套装，如"雷4"、"量子4"、"快枪手4"
        enemy_name: 敌人名称，默认"忘却之庭BOSS"
    """
    # 占位实现：基于角色组合的简化 DPS 计算
    # 等 sim/ 引擎完成后替换为真实模拟

    # 基础 DPS（假设 Lv.80 角色、遗器满级）
    base_dps = 120000

    # 角色加成（简化模型）
    character_bonuses = {
        "黄泉": 1.35,    # 主 C，高倍率
        "花火": 1.20,    # 同谐辅助，暴击增益
        "阮梅": 1.15,    # 同谐辅助，伤害增益
        "符玄": 1.05,    # 存护，生存保障
        "银狼": 1.18,    # 虚无，减防
        "佩拉": 1.12,    # 虚无，减防
        "停云": 1.10,    # 同谐，攻击力增益
        "布洛妮娅": 1.15,  # 同谐，拉条+增伤
        "罗刹": 1.05,    # 丰饶，治疗
        "白露": 1.05,    # 丰饶，治疗
        "杰帕德": 1.03,  # 存护，护盾
    }

    team_chars = [c.strip() for c in team_config.replace("，", "+").split("+")]
    for char in team_chars:
        if char in character_bonuses:
            base_dps *= character_bonuses[char]

    # 遗器加成
    relic_bonuses = {
        "雷4": 1.15,
        "雷2+2": 1.08,
        "量子4": 1.10,
        "量子2+2": 1.06,
        "快枪手4": 1.08,
        "快枪手2+2": 1.05,
        "默认": 1.0,
    }
    base_dps *= relic_bonuses.get(relic_set, 1.0)

    # 生存率（根据存护/丰饶角色数量）
    survival_chars = {"符玄", "罗刹", "白露", "杰帕德", "加拉赫", "藿藿"}
    survival_count = sum(1 for c in team_chars if c in survival_chars)
    survival_rate = min(0.99, 0.75 + survival_count * 0.08)

    # 能量效率（根据同谐角色数量）
    harmony_chars = {"花火", "阮梅", "停云", "布洛妮娅", "知更鸟"}
    harmony_count = sum(1 for c in team_chars if c in harmony_chars)
    energy_efficiency = min(0.95, 0.70 + harmony_count * 0.08)

    return f"""战斗模拟结果：
队伍: {team_config}
遗器: {relic_set}
敌人: {enemy_name}

DPS: {base_dps:,.0f}
生存率: {survival_rate:.0%}
能量效率: {energy_efficiency:.0%}

注：当前为占位模拟数据，等 sim/ 引擎完成后将替换为真实模拟。"""


@tool
def compare_configs(
    team1: str,
    team2: str,
    relic1: str = "默认",
    relic2: str = "默认",
) -> str:
    """对比两种队伍配置的战斗效果。

    Args:
        team1: 第一种队伍配置，如"黄泉+花火+阮梅+符玄"
        team2: 第二种队伍配置，如"黄泉+银狼+佩拉+符玄"
        relic1: 第一种遗器配置
        relic2: 第二种遗器配置
    """
    # 简化对比
    result1 = simulate_battle.invoke({"team_config": team1, "relic_set": relic1})
    result2 = simulate_battle.invoke({"team_config": team2, "relic_set": relic2})

    return f"""配置对比：

=== 配置 1 ===
{result1}

=== 配置 2 ===
{result2}

注：当前为占位模拟数据，等 sim/ 引擎完成后将替换为真实对比。"""
