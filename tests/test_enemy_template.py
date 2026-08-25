"""敌人模板测试：calc_enemy_stats 公式链对轴 + 特殊怪容错 + 模板形状.

对轴方式：测试独立从 json 重算 base×HardLevel×Elite×Modify（测公式链装配，不依赖数据快照值）。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

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


class TestMonsterMetaQuery:
    """A2：monster.json 读取下沉 pipeline 查询函数（生成器不拼数据路径）."""

    def test_get_monster_meta_default(self):
        from hsr_nous.pipeline.stages_loader import get_monster_meta
        meta = get_monster_meta("1002011")
        assert meta and meta["en"] == "Ice Edge"
        assert get_monster_meta("9999999_不存在") is None


class TestEnemyDataDirInjection:
    """A2：data_dir 注入——生成器读注入根的 hakushin/fandom 数据（缺省走 pipeline 缺省根）."""

    @pytest.fixture()
    def mini_data(self, tmp_path):
        import json as j
        hak = tmp_path / "stages" / "hakushin"
        hak.mkdir(parents=True)
        (hak / "monstervalue.json").write_text(j.dumps({"9001": {
            "AttackBase": 100.0, "DefenceBase": 50.0, "HPBase": 1000.0,
            "SpeedBase": 100.0, "StanceBase": 30.0, "StatusResistanceBase": 0.1,
            "child": [{"Id": 9001, "HardLevelGroup": 1, "EliteGroup": 1,
                       "StanceWeakList": ["Fire"]}]}}), encoding="utf-8")
        (hak / "HardLevelGroup.json").write_text(j.dumps([{
            "HardLevelGroup": 1, "Level": 80, "HPRatio": 1.0, "AttackRatio": 1.0,
            "DefenceRatio": 1.0, "SpeedRatio": 1.0, "StanceRatio": 1.0}]), encoding="utf-8")
        (hak / "EliteGroup.json").write_text(j.dumps([{
            "EliteGroup": 1, "HPRatio": 1.0, "AttackRatio": 1.0, "DefenceRatio": 1.0,
            "SpeedRatio": 1.0, "StanceRatio": 1.0}]), encoding="utf-8")
        (hak / "monster.json").write_text(j.dumps({
            "9001": {"en": "Test Dummy"}}), encoding="utf-8")
        (tmp_path / "fandom_enemy_data.json").write_text(j.dumps({
            "Test Dummy": {"skills": [{"name": "Slap", "type": "Basic ATK",
                                       "desc": "Deals damage."}]}}), encoding="utf-8")
        return str(tmp_path)

    def test_generate_reads_injected_data_dir(self, mini_data):
        tpl = generate_enemy_template("9001", level=80, data_dir=mini_data)
        assert tpl["name"] == "Test Dummy"          # monster.json 来自注入根
        assert tpl["base_stats"]["hp"] == 1000.0    # monstervalue 公式链来自注入根
        assert tpl["weakness"] == ["fire"]
        assert any("Slap" in n for n in tpl["notes"])  # fandom 技能 notes 来自注入根

    def test_default_data_dir_unchanged(self):
        """缺省行为不变：生产根读真数据（命名两态——官方英文名）."""
        tpl = generate_enemy_template("1002011", level=80)
        assert tpl["name"] == "Ice Edge"
