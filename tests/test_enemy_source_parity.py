"""敌人数据源替代对拍：tbgd 新 loader vs 现 hakushin 链（替代前置验证闸）.

设计文档 P2 验收：全量字段映射+对拍表全绿，**一切差异只能是有意接受的显式差异**。
本文件即该闸的固化——tbgd（turnbasedgamedata 五表）与 hakushin（monstervalue +
HardLevelGroup + EliteGroup 公式链）全量逐值对拍，差异白名单只有两类：

1. **Speed/StanceModifyValue 平加项**（迁移即修复）：hakushin monstervalue 无
   模板级 SpeedModifyValue（16 件）与实例+模板级 StanceModifyValue（472+12 件），
   现公式链漏算；tbgd 版计入——spd 差异必须恰等于模板级 SpeedModifyValue，
   max_toughness 差异必须恰等于实例+模板级 StanceModifyValue（其余情况零差异）。
2. **800205073 DefenceModifyRatio 缺键**（语义=默认 1，数值无差——含在全等断言内）。

数据依赖：tbgd 五件（tbgd_data_available）+ hakushin 公式链（stage_data_available）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.pipeline import paths as _paths
from hsr_nous.pipeline.enemies import loader as tbgd
from tests._data_env import (
    data_skip_reason,
    stage_data_available,
    tbgd_data_available,
)

pytestmark = pytest.mark.skipif(
    not (tbgd_data_available() and stage_data_available()),
    reason=data_skip_reason())

_LEVELS = (80,)          # 全量对拍等级
_CLAMP_SAMPLE_LEVELS = (65, 95, 120)   # 抽样等级（含钳级语义）
_CLAMP_SAMPLE_SIZE = 20


def _v(raw):
    """tbgd {Value} 包装/裸值统一解包（= enemies/loader._v，引用见函数体注释）."""
    return tbgd._v(raw)


# ---------------------------------------------------------------------------
# 冻结 hakushin 链独立重算（对拍参照——自含实现，不依赖已退役的旧 stages 敌人段）
# ---------------------------------------------------------------------------

import json as _json
from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _hakushin_tables():
    mv = _json.loads(_paths.monstervalue_path().read_text(encoding="utf-8"))
    hard_rows = _json.loads(_paths.hard_level_groups_path().read_text(encoding="utf-8"))
    elite_rows = _json.loads(_paths.elite_groups_path().read_text(encoding="utf-8"))
    hard_table: dict = {}
    for e in hard_rows:
        hard_table.setdefault(e["HardLevelGroup"], {})[e["Level"]] = e
    elite_table = {e["EliteGroup"]: e for e in elite_rows}
    return mv, hard_table, elite_table


def _hakushin_calc(enemy_id: str, level: int):
    """旧 stages/loader.calc_enemy_stats 语义的测试侧参照（公式链逐步对齐）.

    逐键语义：detail = monstervalue 顶层或 child 合并视图（变体走默认子实体——
    ModifyRatio 恒按 1 吞，见 test_variant_semantics）；面板 = base ×
    HardLevelGroup[clamped] × EliteGroup × child.ModifyRatio；spd 加
    child.SpeedModifyValue；effect_res = base + 等级加算；weakness = child 表小写。
    """
    mv, hard_table, elite_table = _hakushin_tables()
    detail = mv.get(enemy_id)
    if isinstance(detail, dict):
        detail = dict(detail)
    else:
        detail = None
        for pid, entry in mv.items():
            if not isinstance(entry, dict):
                continue
            for c in entry.get("child", []):
                if str(c.get("Id")) == enemy_id:
                    detail = {k: v for k, v in entry.items() if k != "child"}
                    detail.update(c)
                    detail["parent_id"] = pid
                    break
            if detail is not None:
                break
        if detail is None:
            return None

    children = detail.get("child") or []
    child = next((c for c in children if str(c.get("Id")) == enemy_id),
                 children[0] if children else None)
    if child is None:
        child = {"HardLevelGroup": 1, "EliteGroup": 1}

    group = hard_table.get(child.get("HardLevelGroup", 1))
    if not group:
        return None
    clamped = min(level, max(group))
    hard = group[clamped]
    elite = elite_table.get(child.get("EliteGroup", 1), {})

    def _ratio(t, k):
        return float(t.get(k, 1) or 1)

    def _chain(base, rk, mk):
        return (float(base or 0.0) * _ratio(hard, rk) * _ratio(elite, rk)
                * float(child.get(mk, 1) or 1))

    missing = [k for k in ("AttackBase", "DefenceBase", "HPBase", "SpeedBase", "StanceBase")
               if detail.get(k) is None]
    spd = _chain(detail["SpeedBase"], "SpeedRatio", "SpeedModifyRatio")
    spd += float(child.get("SpeedModifyValue") or 0)
    return {
        "level": level,
        "hp": _chain(detail["HPBase"], "HPRatio", "HPModifyRatio"),
        "atk": _chain(detail["AttackBase"], "AttackRatio", "AttackModifyRatio"),
        "def_": _chain(detail["DefenceBase"], "DefenceRatio", "DefenceModifyRatio"),
        "spd": spd,
        "max_toughness": _chain(detail["StanceBase"], "StanceRatio", "StanceModifyRatio"),
        "effect_res": float(detail.get("StatusResistanceBase", 0) or 0)
        + min(max(level - 50, 0) * 0.004, 0.10),
        "weakness": [w.lower() for w in child.get("StanceWeakList") or []],
        "_level_clamped": clamped != level,
        "_missing_bases": missing,
    }


def test_roster_parity():
    """模板花名册同集：tbgd MonsterTemplateConfig 顶层 == monstervalue 顶层 632 键."""
    import json
    mv = json.loads(_paths.monstervalue_path().read_text(encoding="utf-8"))
    assert set(tbgd.list_monster_ids()) == {str(k) for k in mv.keys()}


def test_template_base_parity():
    """模板 base 六值全等对拍（632×6，None 语义一致：tbgd 缺键 == mv null）."""
    import json
    mv = json.loads(_paths.monstervalue_path().read_text(encoding="utf-8"))
    bad = {}
    for tid, tpl in tbgd._template_map().items():
        top = mv.get(tid)
        assert top is not None, f"monstervalue 缺模板 {tid}"
        for key in ("HPBase", "AttackBase", "DefenceBase",
                    "SpeedBase", "StanceBase", "StatusResistanceBase"):
            tv, hv = _v(tpl.get(key)), top.get(key)
            if tv is None and hv is None:
                continue
            if tv is None or hv is None or not math.isclose(tv, float(hv), rel_tol=1e-4):
                bad.setdefault(tid, {})[key] = (tv, hv)
    assert not bad, f"模板 base 值差异：{dict(list(bad.items())[:5])}"


def test_coefficient_tables_parity():
    """公式链系数表逐值对拍：tbgd EliteGroup/HardLevelGroup == hakushin 同名两表."""
    import json
    hak_elite = json.loads(_paths.elite_groups_path().read_text(encoding="utf-8"))
    hak_hard = json.loads(_paths.hard_level_groups_path().read_text(encoding="utf-8"))

    def _rows_by(table, key):
        return {int(r[key]): r for r in table}

    for label, tbgd_rows, hak_rows in (
            ("EliteGroup", tbgd._load_table("EliteGroup.json"), hak_elite),
            ("HardLevelGroup", tbgd._load_table("HardLevelGroup.json"), hak_hard)):
        if label == "EliteGroup":
            t_map = {int(r["EliteGroup"]): r for r in tbgd_rows}
            h_map = {int(r["EliteGroup"]): r for r in hak_rows}
        else:
            # HardLevelGroup 行 = (group, level) 二元键——按组坍缩会漏等级维
            t_map = {(int(r["HardLevelGroup"]), int(r["Level"])): r for r in tbgd_rows}
            h_map = {(int(r["HardLevelGroup"]), int(r["Level"])): r for r in hak_rows}
        assert set(t_map) == set(h_map), (
            f"{label} 键集差异：仅 tbgd {sorted(set(t_map) - set(h_map))[:5]} / "
            f"仅 hakushin {sorted(set(h_map) - set(t_map))[:5]}")
        bad = {}
        for gid in t_map:
            for ratio_key in ("AttackRatio", "DefenceRatio", "HPRatio",
                              "SpeedRatio", "StanceRatio"):
                tv = _v(t_map[gid].get(ratio_key))
                hv = _v(h_map[gid].get(ratio_key))
                if tv is None and hv is None:
                    continue
                if tv is None or hv is None or not math.isclose(tv, hv, rel_tol=1e-6):
                    bad.setdefault(gid, {})[ratio_key] = (tv, hv)
        assert not bad, f"{label} 系数差异：{dict(list(bad.items())[:5])}"


def _assert_stats_equal(tid: str, level: int) -> None:
    """单 id 单等级对拍：五值/抗性/弱点——spd/toughness 仅允许平加项差异."""
    h = _hakushin_calc(tid, level)
    t = tbgd.calc_enemy_stats(tid, level)
    assert h is not None, f"hakushin 链查无 {tid}"
    assert t is not None, f"tbgd 链查无 {tid}"

    for key in ("hp", "atk", "def_", "effect_res"):
        assert math.isclose(h[key], t[key], rel_tol=1e-6), (
            f"{tid} lv{level} {key} 差异：hakushin={h[key]} vs tbgd={t[key]}")

    detail = tbgd.get_enemy_detail(tid)
    tpl = detail["_template"]
    # spd 差异必须恰等于模板级 SpeedModifyValue（实例级 hakushin 已算，见
    # stages/loader.py:432）；max_toughness 差异必须恰等于实例+模板级 StanceModifyValue
    spd_flat = _v(tpl.get("SpeedModifyValue")) or 0.0
    stance_flat = ((_v(detail.get("StanceModifyValue")) or 0.0)
                   + (_v(tpl.get("StanceModifyValue")) or 0.0))
    assert math.isclose(t["spd"] - h["spd"], spd_flat, rel_tol=1e-6, abs_tol=1e-6), (
        f"{tid} lv{level} spd 差异 {t['spd'] - h['spd']} ≠ 模板平加 {spd_flat}")
    assert math.isclose(
        t["max_toughness"] - h["max_toughness"], stance_flat,
        rel_tol=1e-6, abs_tol=1e-6), (
        f"{tid} lv{level} toughness 差异 {t['max_toughness'] - h['max_toughness']}"
        f" ≠ 平加 {stance_flat}")

    assert t["weakness"] == h["weakness"], (
        f"{tid} 弱点差异：hakushin={h['weakness']} vs tbgd={t['weakness']}")
    assert t["_level_clamped"] == h["_level_clamped"]
    assert t["_missing_bases"] == h["_missing_bases"]


def test_stats_parity_all_templates_lv80():
    """全量模板对拍（632 × lv80）：差异仅平加项显式接受（见模块 docstring）.

    对拍域 = 模板 id（自身子实体——生成器花名册口径）：hakushin 链走
    顶层 base × child[自身] 系数，tbgd 链走 模板 base × 自身实例行系数，
    两链良定义同构。变体实例（非自身子实体）见 test_variant_semantics。
    """
    for tid in tbgd.list_monster_ids():
        _assert_stats_equal(tid, 80)


def test_stats_parity_clamp_levels_sample():
    """抽样对拍钳级语义（lv65/95/120 × 20 模板 id——等级超表钳到组内最大级两链一致）."""
    for tid in tbgd.list_monster_ids()[:_CLAMP_SAMPLE_SIZE]:
        for lv in _CLAMP_SAMPLE_LEVELS:
            _assert_stats_equal(tid, lv)


def test_variant_semantics():
    """变体实例语义钉（2090 个非自身子实体）：hakushin 链对变体 id 走默认子实体
    （ModifyRatio 恒按 1 算——变体系数被吞， monstervalue child 合并视图只取 base），
    tbgd 链按实例行真实系数算——两者差异必须恰等于 ModifyRatio 族（tbgd 是游戏真值，
    hakushin 对变体的坏口径在案；生成器花名册只含模板 id，此差异不进现行生产面）。

    抽样断言：hp/atk/def_ 三值 tbgd == hakushin × 对应 ModifyRatio（rel_tol=1e-6）。
    """
    sample = [i for i in sorted(tbgd._instance_map().keys())
              if i not in set(tbgd.list_monster_ids())][:_CLAMP_SAMPLE_SIZE]
    assert sample, "变体实例集非空（2722 - 632 自身）"
    for vid in sample:
        h = _hakushin_calc(vid, 80)
        t = tbgd.calc_enemy_stats(vid, 80)
        if h is None or t is None:
            continue  # hakushin 查无的变体（tbgd 新增覆盖）跳过——不计差异
        detail = tbgd.get_enemy_detail(vid)
        for key, modify_key in (("hp", "HPModifyRatio"), ("atk", "AttackModifyRatio"),
                                ("def_", "DefenceModifyRatio")):
            ratio = _v(detail.get(modify_key)) or 1.0
            assert math.isclose(t[key], h[key] * ratio, rel_tol=1e-6), (
                f"变体 {vid} {key}：tbgd={t[key]} ≠ hakushin×ModifyRatio "
                f"{h[key]}×{ratio}")
