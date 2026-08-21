"""敌人模板测试：calc_enemy_stats 公式链对轴 + 特殊怪容错 + 模板形状.

对轴方式：测试独立从 json 重算 base×HardLevel×Elite×Modify（测公式链装配，不依赖数据快照值）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from hsr_nous.adapters.template_generator import generate_enemy_template
from hsr_nous.pipeline.stages_loader import calc_enemy_stats

_ROOT = Path(__file__).parent.parent / "data" / "stages" / "hakushin"


def _independent_calc(enemy_id: str, level: int) -> dict:
    """独立重算（与实现不同路径：直接读三张表）."""
    mv = json.loads((_ROOT / "monstervalue.json").read_text(encoding="utf-8"))
    hard = json.loads((_ROOT / "HardLevelGroup.json").read_text(encoding="utf-8"))
    elite = json.loads((_ROOT / "EliteGroup.json").read_text(encoding="utf-8"))
    d = mv[enemy_id]
    child = next((c for c in d.get("child") or [] if str(c["Id"]) == enemy_id),
                 (d.get("child") or [{}])[0] if d.get("child") else {})
    g = {e["Level"]: e for e in hard if e["HardLevelGroup"] == child.get("HardLevelGroup", 1)}
    h = g[min(level, max(g))]
    e = next((x for x in elite if x["EliteGroup"] == child.get("EliteGroup", 1)), {})
    el = lambda k: float(e.get(k, 1) or 1)
    return {
        "hp": d["HPBase"] * h["HPRatio"] * el("HPRatio") * float(child.get("HPModifyRatio", 1) or 1),
        "atk": d["AttackBase"] * h["AttackRatio"] * el("AttackRatio") * float(child.get("AttackModifyRatio", 1) or 1),
        "spd": d["SpeedBase"] * h["SpeedRatio"] * el("SpeedRatio") * float(child.get("SpeedModifyRatio", 1) or 1)
        + float(child.get("SpeedModifyValue") or 0),
    }


class TestCalcEnemyStats:
    def test_formula_chain_matches_independent_calc(self):
        """公式链装配对轴：hp/atk/spd 与独立重算逐字段相等."""
        s = calc_enemy_stats("1002011", 80)
        ref = _independent_calc("1002011", 80)
        assert math.isclose(s["hp"], ref["hp"], rel_tol=1e-9)
        assert math.isclose(s["atk"], ref["atk"], rel_tol=1e-9)
        assert math.isclose(s["spd"], ref["spd"], rel_tol=1e-9)

    def test_effect_res_level_bonus(self):
        """效果抗性 = base + min((level-50)×0.4%, 10%)（Lv80 → +10% 上限）."""
        s = calc_enemy_stats("1002011", 80)  # base 0.2
        assert math.isclose(s["effect_res"], 0.2 + 0.10, rel_tol=1e-9)

    def test_level_clamped_beyond_table(self):
        """超出 HardLevelGroup 表级数 → 钳级并标记."""
        s = calc_enemy_stats("1002011", 999)
        assert s["_level_clamped"] is True

    def test_null_stance_base_tolerated(self):
        """StanceBase=null（无韧性条特殊怪）→ toughness 0 + 缺失名单."""
        s = calc_enemy_stats("2024020", 80)
        assert s["max_toughness"] == 0.0
        assert "StanceBase" in s["_missing_bases"]

    def test_empty_child_default_coefficients(self):
        """child=[]（无形态变体）→ 顶层 base + 默认系数，可正常生成."""
        s = calc_enemy_stats("4034020", 80)
        assert s is not None and s["hp"] > 0


class TestEnemyTemplate:
    def test_template_shape(self):
        tpl = generate_enemy_template("1002011", level=80)
        assert tpl["enemy_id"] == "1002011" and tpl["name"]  # 官方英文名（命名两态合法）
        assert tpl["weakness"] == ["fire", "thunder"]
        assert tpl["base_stats"]["hp"] > 0 and tpl["base_stats"]["spd"] > 0
        assert tpl["actions"][0]["action_type"] == "basic"  # 占位行动
        assert tpl["notes"], "攻击属性缺口等提示应入 notes"

    def test_full_smoke_all_monsters(self):
        """全量冒烟：monstervalue 全怪生成不炸."""
        mv = json.loads((_ROOT / "monstervalue.json").read_text(encoding="utf-8"))
        for eid in mv:
            tpl = generate_enemy_template(eid, level=80)
            assert tpl["base_stats"]["hp"] >= 0
