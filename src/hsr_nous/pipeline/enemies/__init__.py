"""enemies 域（敌人域）：敌人本体数据——面板/弱点/抗性/技能/AI.

- `update.py`：turnbasedgamedata 五表拉取（GitLab raw 直下零爬虫）+ 红线对齐校验
- `loader.py`：tbgd 口径统一查询（calc_enemy_stats/get_enemy_detail/list_monster_ids/
  get_enemy_skills/get_enemy_ai——消费方切源前的对拍基准见 tests/test_enemy_source_parity.py）
- `semantic.py`：敌人语义补充（extract_fandom_enemies 迁入——敌人机制描述文本，语义补充非数值权威）
"""
