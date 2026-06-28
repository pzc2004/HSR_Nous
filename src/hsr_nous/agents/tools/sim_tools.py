"""战斗模拟工具：封装 sim.engine.CombatEngine 为 LangChain Tools.

通过 adapters.encounter_adapter 组装 Encounter，调用真实 CombatEngine.run() 返回结果。

数据流：
    team_config + relic_set + enemy_name
        ↓ adapters.encounter_adapter.build_encounter
    Encounter + actions_by_actor
        ↓ sim.engine.CombatEngine.run
    BattleState → total_damage / action_history
"""
from __future__ import annotations

from langchain_core.tools import tool

from hsr_nous.adapters.encounter_adapter import build_encounter
from hsr_nous.sim.engine import CombatEngine


def _parse_team(team_config: str) -> list[str]:
    """解析 'A+B+C+D' 格式队伍，支持中文逗号."""
    s = team_config.replace("，", "+").replace(",", "+").replace("、", "+")
    return [t.strip() for t in s.split("+") if t.strip()]


def _run_simulation(
    team_config: str,
    relic_set: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
    level: int = 80,
    max_av: int = 1500,
    lang: str = "en",
) -> str:
    """真实仿真：组装 Encounter → 跑 CombatEngine → 输出报告."""
    team = _parse_team(team_config)
    if not team:
        return "错误：队伍为空，请提供 1-4 个角色名（用 + 分隔）"

    try:
        encounter, actions_by_actor = build_encounter(
            team=team,
            relic_set=relic_set,
            enemy_name=enemy_name,
            level=level,
            max_av=max_av,
            lang=lang,
        )
    except Exception as e:
        return (
            f"错误：无法组装战斗配置\n"
            f"队伍: {team_config}\n"
            f"原因: {type(e).__name__}: {e}\n"
            f"建议: 检查角色名是否正确（支持中文名，如'黄泉'）"
        )

    try:
        state = CombatEngine(encounter, actions_by_actor=actions_by_actor).run()
    except Exception as e:
        return (
            f"错误：战斗模拟失败\n"
            f"队伍: {'+'.join(team)}\n"
            f"原因: {type(e).__name__}: {e}\n"
            f"建议: 尝试减少队伍人数或更换敌人"
        )

    # 计算每角色输出
    lines = [
        f"战斗模拟结果（基于 sim.engine.CombatEngine Phase 1）：",
        f"队伍: {'+'.join(team)}",
        f"遗器: {relic_set}",
        f"敌人: {enemy_name}",
        f"等级: {level}",
        "",
        f"总伤害 (total_damage): {state.total_damage:,.0f}",
        f"回合数 (turn_count): {state.turn_count}",
        f"累计 AV (total_av): {state.total_av:.1f}",
        "",
        "每角色输出：",
    ]
    for actor_id, dmg in sorted(state.damage_by_actor.items(), key=lambda kv: -kv[1]):
        actor_name = next(
            (a.name for a in encounter.actors if a.actor_id == actor_id),
            actor_id,
        )
        lines.append(f"  - {actor_name}: {dmg:,.0f}")

    lines.append("")
    lines.append(f"行动历史（前 10 条）：")
    for entry in state.action_history[:10]:
        lines.append(f"  {entry}")
    if len(state.action_history) > 10:
        lines.append(f"  ... 等共 {len(state.action_history)} 条")

    return "\n".join(lines)


@tool
def simulate_battle(
    team_config: str,
    relic_set: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
    level: int = 80,
) -> str:
    """运行战斗模拟器，返回 DPS、回合数、每角色输出等指标。

    Args:
        team_config: 队伍配置，格式为"角色1+角色2+角色3+角色4"
        relic_set: 遗器套装，如"雷4"、"量子4"、"默认"
        enemy_name: 敌人名称，如"忘却之庭BOSS"、"末日幻影"、"虚构叙事"
        level: 队伍等级（1-80），默认 80
    """
    return _run_simulation(
        team_config=team_config,
        relic_set=relic_set,
        enemy_name=enemy_name,
        level=level,
    )


@tool
def compare_configs(
    team1: str,
    team2: str,
    relic1: str = "默认",
    relic2: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
    level: int = 80,
) -> str:
    """对比两种队伍配置的战斗效果。

    Args:
        team1: 第一种队伍配置
        team2: 第二种队伍配置
        relic1: 第一种遗器配置
        relic2: 第二种遗器配置
        enemy_name: 敌人名称
        level: 队伍等级
    """
    result1 = _run_simulation(
        team_config=team1,
        relic_set=relic1,
        enemy_name=enemy_name,
        level=level,
    )
    result2 = _run_simulation(
        team_config=team2,
        relic_set=relic2,
        enemy_name=enemy_name,
        level=level,
    )

    return f"""配置对比（基于 sim.engine.CombatEngine Phase 1）：

=== 配置 1：{team1} ({relic1}) ===
{result1}

=== 配置 2：{team2} ({relic2}) ===
{result2}"""
