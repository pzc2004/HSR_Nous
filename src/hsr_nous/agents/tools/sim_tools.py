"""战斗模拟工具（LangChain Tools 壳）.

**状态：已退役（2026-10-12）**——原经 `adapters.encounter_adapter.build_encounter`
组装 Encounter 跑 `CombatEngine.run()`；encounter_adapter 是旧 demo 通道
（`_ENEMY_PRESETS`/`_RELIC_BONUS` 启发式编造数值、找不到角色/技能插占位件，
命名两态下属非法中间态），随 2026-10-12 整改整文件删除。两个工具壳保留
（agents 层 SIM_TOOLS 注册不断链），调用恒返回退役说明——prompts 已约定
「模拟器返回错误 → 降级纯数据查询」路径（`agents/prompts.py`）。

正规通道：per-entity DSL 模板（`data/library/**`，template_generator / 打标 DAG 产出）
→ `sim.compile.compile_encounter` → `CombatEngine.from_compiled`。
"""
from __future__ import annotations

from langchain_core.tools import tool

_RETIRED_MESSAGE = (
    "错误：战斗模拟工具已退役（2026-10-12）\n"
    "原因：旧 demo 通道 encounter_adapter 使用启发式编造数值（非游戏数据），已删除\n"
    "替代：正规仿真走 data/library/** DSL 模板 → sim.compile → CombatEngine；"
    "本工具调用方请降级为纯数据查询方案（prompt 约定路径）"
)


@tool
def simulate_battle(
    team_config: str,
    relic_set: str = "默认",
    enemy_name: str = "忘却之庭BOSS",
    level: int = 80,
) -> str:
    """运行战斗模拟器，返回 DPS、回合数、每角色输出等指标。

    **已退役（2026-10-12）**：恒返回退役说明；正规仿真通道见模块 docstring。

    Args:
        team_config: 队伍配置，格式为"角色1+角色2+角色3+角色4"
        relic_set: 遗器套装，如"雷4"、"量子4"、"默认"
        enemy_name: 敌人名称，如"忘却之庭BOSS"、"末日幻影"、"虚构叙事"
        level: 队伍等级（1-80），默认 80
    """
    return _RETIRED_MESSAGE


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

    **已退役（2026-10-12）**：恒返回退役说明；正规仿真通道见模块 docstring。

    Args:
        team1: 第一种队伍配置
        team2: 第二种队伍配置
        relic1: 第一种遗器配置
        relic2: 第二种遗器配置
        enemy_name: 敌人名称
        level: 队伍等级
    """
    return _RETIRED_MESSAGE
