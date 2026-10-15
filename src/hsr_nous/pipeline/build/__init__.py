"""build 域（配装域）：角色/光锥/遗器数据——build.yaml 输入数据.

- `loader.py`：StarRailRes JSON 加载 + 查询 + 计算辅助（P1 自 pipeline/loader.py 迁入，
  17 个 load_<entity> 样板压缩为表驱动 load_entity + 别名）
- `update.py`：StarRailRes 下载（P1 自 pipeline/update.py 切出）
- `semantic.py`：角色语义补充（Fandom 技能机制数值 + 专光映射 两件活脚本合并；
  米游社技能已归档停爬，归档件留 pipeline/ 原位）
"""
