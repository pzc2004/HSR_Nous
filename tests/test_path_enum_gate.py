"""命途 path 闭合枚举编译闸测试（03_actor §3.1 Actor.path——词表唯一源 sim_schema/actor.py PATHS）.

覆盖：
- 合法全枚举过编译（模板/member 共用 `_compile_inline_character` 单漏斗，inline 即全通道）
- 非法值编译期炸（报错带词表）
- 历史漂移拼写（'the_hunt'/'Rogue' 族）炸且报错信息指向正解 canonical（PATH_ALIASES 指路）
- 派生闸：PATHS == 官方数据派生全集（StarRailRes characters.json path 原值经 PATH_ALIASES
  映射的值集——新命途入库先同步 PATHS；数据缺失环境按 _data_env 纪律跳过）
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim_schema.actor import PATH_ALIASES, PATHS
from tests._data_env import data_available, data_skip_reason


def _build(path: str) -> dict:
    return {"build": {
        "team": [{
            "inline": True, "actor_id": "hero", "name": "测试员", "level": 80,
            "path": path,
            "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
            "actions": [{
                "action_id": "b", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "fire",
                "scaling": [{"atk": 1.0}], "toughness_dmg": 10,
            }],
        }],
        "policy": {"name": "p", "action_rules": [{"condition": "true", "action": "basic", "priority": 0}]},
    }}


def _stage() -> dict:
    return {"stage": {
        "stage_id": "s",
        "enemies": [{"actor_id": "e1", "name": "假人", "hp": 1e6, "spd": 100, "max_toughness": 30}],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }}


class TestPathEnumGate:
    @pytest.mark.parametrize("path", sorted(PATHS))
    def test_canonical_paths_compile(self, path: str):
        """闭合词表全枚举合法过编译，Actor.path 原样落地."""
        compiled = compile_encounter(_build(path), _stage())
        assert compiled.build_team[0].path == path

    def test_empty_path_default_ok(self):
        """缺省 ''（未声明）合法——闸只锁词表外值."""
        compiled = compile_encounter(_build(""), _stage())
        assert compiled.build_team[0].path == ""

    def test_illegal_path_rejected(self):
        """词表外值编译期炸，报错带闭合词表."""
        with pytest.raises(ValueError, match="path 非法值 'hunter'"):
            compile_encounter(_build("hunter"), _stage())

    def test_the_hunt_rejected_with_hint(self):
        """'the_hunt'（历史三分裂主病）炸，且报错信息指向正解 'hunt'."""
        with pytest.raises(ValueError, match=r"path 非法值 'the_hunt'，正解 'hunt'"):
            compile_encounter(_build("the_hunt"), _stage())

    def test_official_raw_name_rejected_with_hint(self):
        """官方内部类目原值（'Rogue'——绕过生成器的手写漂移）炸，正解 'hunt'（大小写不敏感指路）."""
        with pytest.raises(ValueError, match=r"path 非法值 'rogue'，正解 'hunt'"):
            compile_encounter(_build("Rogue"), _stage())


class TestPathEnumDerivation:
    def test_aliases_point_into_paths(self):
        """别名表自洽：值全 ∈ PATHS；键与 PATHS 不交（canonical 不是自己的别名）."""
        assert set(PATH_ALIASES.values()) <= set(PATHS)
        assert not (set(PATH_ALIASES) & set(PATHS))

    @pytest.mark.skipif(not data_available(), reason=data_skip_reason())
    def test_paths_derived_from_official_data(self):
        """PATHS == 官方数据派生全集（StarRailRes characters.json path 原值 → canonical 映射值集）.

        新命途随官方数据入库时本闸炸——先补 sim_schema/actor.py PATHS（+ PATH_ALIASES
        内部类目名映射），不许绕。
        """
        from hsr_nous.pipeline import load_characters

        chars = load_characters(lang="cn")
        official_raw = {str(c.get("path") or "") for c in chars.values()} - {""}
        assert official_raw, "官方 characters.json 无任何 path 值——数据源异常，勿放行"
        derived = {PATH_ALIASES.get(p.lower(), p.lower()) for p in official_raw}
        assert set(PATHS) == derived, (
            f"命途词表与官方数据漂移：only-PATHS={sorted(set(PATHS) - derived)} "
            f"only-official={sorted(derived - set(PATHS))}——新命途入库先同步 "
            "sim_schema/actor.py PATHS/PATH_ALIASES")
