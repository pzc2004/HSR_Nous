"""引擎数值字面量闸（引擎零游戏数值铁律的执行层——`extra_pool=20.0` 字面量漏网案后立项）.

铁律：一切游戏数值（倍率/系数/固定发放值/规则阈值）只许住在数据层——rulebook
constants（体系常量）或模板 YAML（角色/装备数值）。本闸扫描 `src/hsr_nous/sim/**`
的数值字面量，命中白名单外即红：**新增任何数值字面量前先自问"这是游戏数值吗"**——
是则挪数据层；否则在下方白名单补一行并注明技术理由。

边界与挂账：
- 不扫 `web.py`（纯 UI 技术量）与 `battles.py`（demo 数据本体——配置即数据文件）。
- AV 距离模型 10000.0 系体系常量，按铁律亦应归 rulebook——牵动调度器全层，挂账另案；
  现经白名单放行（见 `_ALLOWED_FLOATS` 注）。
- 闸防大不防小：小整数（<65）结构/游戏两可，value 级无法区分（如 pre_battle 池默认 5
  疑为秘技点规则值——挂账待核出处后挪簿），靠 review 与本闸新增注释纪律兜底。
"""
from __future__ import annotations

import ast
from pathlib import Path

SIM_ROOT = Path(__file__).resolve().parents[1] / "src" / "hsr_nous" / "sim"
_SKIP_FILES = {"web.py", "battles.py"}   # 纯 UI 技术量 / demo 数据本体——非引擎逻辑面

# 浮点白名单（新增须一行一注技术理由；游戏浮点数值是历史违规主力——20.0/80.0/系数族）
_ALLOWED_FLOATS = {
    0.0, 1.0, -1.0, 2.0, 0.5,   # 结构量
    100.0,                      # 百分数换算基（hooks delay/advance 族 /100.0）
    1e-9, 1e-6, 1e-12,          # 浮点容差
    0.05, 0.50, 0.95,           # 统计分位（montecarlo 分布口径）
    0.1, 0.8, 0.2,              # 编译闸技术阈值（mechanic_chance 族/校验容差）
    10000.0,                    # AV 距离模型（scheduler DISTANCE——体系常量，挪簿挂账另案）
    9999.0,                     # AV999 显示钳（policy_api——体系常量，与距离模型同挂账）
    450.0,                      # demo 默认终止 AV（stage 未声明时的兜底配置——非规则值）
}

# 整数白名单（小整数结构量按段放行；段外须明确技术理由）
_ALLOWED_INTS = set(range(-3, 65)) | {
    80, 90, 99, 100, 110, 120, 128, 130, 150, 200, 240, 300,
    400, 404, 409, 500, 800, 1000, 1500, 8000, 9999, 10000,
    100000, 999999, 1000000,    # 演示上限/超时/缓存/重入帽/样本数/AV 距离等技术量
}


def _iter_numeric_literals():
    for path in sorted(SIM_ROOT.rglob("*.py")):
        if path.name in _SKIP_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, (int, float))
                    and not isinstance(node.value, bool)):
                yield path, node


def test_no_game_number_literals_in_engine():
    """sim/ 数值字面量全过白名单（游戏数值归 rulebook constants/模板 YAML）."""
    bad = []
    for path, node in _iter_numeric_literals():
        v = node.value
        allowed = (v in _ALLOWED_FLOATS) if isinstance(v, float) else (v in _ALLOWED_INTS)
        if not allowed:
            bad.append(f"  {path.relative_to(SIM_ROOT)}:{node.lineno}  {v!r}")
    assert not bad, (
        "引擎层新增数值字面量须先归 rulebook constants/模板 YAML（引擎零游戏数值）；\n"
        "确为技术常量 → tests/test_engine_literal_gate.py 白名单补行并注理由：\n"
        + "\n".join(bad))
