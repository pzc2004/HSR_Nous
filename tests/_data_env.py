"""数据环境探测：数据缺失时数据依赖测试自动跳过而不是 FileNotFoundError.

workflow 注释（.github/workflows/test.yml）声明"数据依赖测试自带 skipif"——
本模块是该声明的实现：任何依赖游戏数据的测试，在数据缺失时跳过而不是 FileNotFoundError。

判定分级：四源各一判定 + Ability 真实样例判定 + 两个组合判定 + 两个生成件判定——
测试按实际依赖挂对应判定，不再一律捆绑三件套。tbgd 独立测试只查 turnbasedgamedata
落盘件（CI 可下载，不被 fandom 必需项误拦）；fandom 语义依赖测试只查
fandom_enemy_data.json；Ability 真实样例另查 CharacterConfig/Ability 本地件（快照未含
新配置时显式待补）；生成件 CI 由生成命令动态产出，挂 sim_templates/tbgd_skill 判定。

路径一律走 pipeline/paths（HSR_NOUS_DATA_DIR 覆盖同步生效），不再按 CWD 相对拼。
"""
from __future__ import annotations

from hsr_nous.pipeline.paths import (
    fandom_enemy_path,
    sim_templates_dir,
    stages_dir,
    starrailres_dir,
    tbgd_skill_path,
    turnbasedgamedata_dir,
)


def starrailres_available() -> bool:
    """配装域数据（StarRailRes）是否可用."""
    return (starrailres_dir() / "index_new" / "cn" / "characters.json").exists()


def stage_data_available() -> bool:
    """期数编成域数据（Hakushin/buhflipexplode）是否可用."""
    return (stages_dir() / "hakushin" / "maze.json").exists()


def tbgd_data_available() -> bool:
    """turnbasedgamedata 可下载件是否可用——tbgd 独立测试挂本判定（CI 拉 tbgd 即可跑，不被 fandom 必需项误拦）."""
    return (turnbasedgamedata_dir() / "MonsterTemplateConfig.json").exists()


def enemy_ability_available() -> bool:
    """通用 Ability 编译器真实样例所需的 CharacterConfig/Ability 本地件."""
    root = turnbasedgamedata_dir()
    required = (
        "Config/ConfigCharacter/Monster/Monster_W1_Mecha04_00_Config.json",
        "Config/ConfigCharacter/Monster/Monster_W1_Mecha04_00_Config_A.json",
        "Config/ConfigAbility/Monster/Monster_W1_Mecha04_00_Ability.json",
        "Config/ConfigCharacter/Monster/Monster_W1_Bronya_00_Config_RL.json",
        "Config/ConfigAbility/Monster/Monster_W1_Bronya_00_Ability_RL.json",
        "Config/ConfigCharacter/Monster/Monster_W2_Mecha03_00_Config.json",
        "Config/ConfigAbility/Monster/Monster_W2_Mecha03_00_Ability.json",
        "Config/ConfigCharacter/Monster/Monster_W2_Fuyan_00_Config_RLBoss.json",
        "Config/ConfigAbility/Monster/Monster_W2_Fuyan_00_Ability_RLBoss.json",
        "Config/ConfigCharacter/Monster/Monster_W3_Clock_00_Config.json",
        "Config/ConfigAbility/Monster/Monster_W3_Clock_00_Ability.json",
        "Config/ConfigCharacter/Monster/Monster_W4_Harpy_00_Config.json",
        "Config/ConfigAbility/Monster/Monster_W4_Harpy_00_Ability.json",
        "Config/ConfigCharacter/Monster/Monster_SW_Minion01_01_Config.json",
        "Config/ConfigCharacter/Monster/Monster_SW_Minion01_01_Config_IF.json",
        "Config/ConfigAbility/Monster/Monster_SW_Minion01_01_Ability.json",
        "Config/ConfigAbility/Monster/Monster_SW_Boss_00_Ability.json",
    )
    return all((root / relative).is_file() for relative in required)


def fandom_semantic_available() -> bool:
    """Fandom 语义文件是否可用——fandom 语义依赖测试挂本判定（镜像/快照供给，未就位显式标待补场景）."""
    return fandom_enemy_path().exists()


def enemy_data_available() -> bool:
    """敌人全量数据（= turnbasedgamedata + Fandom 语义两件）是否可用."""
    return tbgd_data_available() and fandom_semantic_available()


def sim_templates_available() -> bool:
    """生成器骨架（data/sim_templates——gitignored 纯生成物）是否已生成.

    CI 由 `python -m hsr_nous.adapters.template_generator` 动态全量生成（约 2 秒）；
    本地同命令跑一次即得。
    """
    d = sim_templates_dir() / "characters"
    return d.is_dir() and any(d.glob("*_*.yaml"))


def tbgd_skill_available() -> bool:
    """tbgd 技能机制提取产物（extract_tbgd_skills 产物）是否可用.

    CI 由 `python -m hsr_nous.pipeline.extract_tbgd_skills` 动态提取；本地同命令跑一次即得。
    """
    return tbgd_skill_path().exists()


def generated_skip_reason() -> str:
    return "生成件缺失（data/sim_templates 或 data/tbgd_skill_data.json——跑 template_generator/extract_tbgd_skills 生成）"


def data_available() -> bool:
    """全量数据环境（原三件套语义）是否可用——全套依赖测试用."""
    return starrailres_available() and stage_data_available() and enemy_data_available()


def data_skip_reason() -> str:
    return "本地数据缺失（data/ 为 gitignored；CI 无数据环境，数据依赖测试按设计跳过）"


def fandom_pending_reason() -> str:
    return "Fandom 语义文件缺失（镜像/快照未就位——显式待补场景，不计入 CI 覆盖率）"
