"""v0.5 adapters 模板生成测试：真角色数据 → 模板 → 编译 → 引擎.

首个真角色：丹恒（1002，纯 atk 直伤，无机制依赖）。
"""
from __future__ import annotations

import math

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED

from tests._data_env import data_available, data_skip_reason

pytestmark = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

DAN_HENG_ID = "1002"


@pytest.fixture(scope="module")
def dan_heng_template(tmp_path_factory):
    """生成丹恒模板到**临时根**（module 级，只生成一次；曾写真实 data/，同团灭事故族）."""
    from hsr_nous.adapters.template_generator import write_character_template
    out = tmp_path_factory.mktemp("tpl_gen") / "characters"
    path = write_character_template(DAN_HENG_ID, out_dir=str(out), level=80, lang="cn")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestTemplateGeneration:
    def test_template_shape(self, dan_heng_template):
        tpl = dan_heng_template
        assert tpl["actor_id"] == DAN_HENG_ID and tpl["name"] == "丹恒"
        assert tpl["base_stats"]["atk"] > 0 and tpl["base_stats"]["hp"] > 0
        types = {a["action_type"] for a in tpl["actions"]}
        assert types == {"basic", "skill", "ultimate"}
        for a in tpl["actions"]:
            assert a["scaling"] and a["scaling"][0]["atk"] > 0
            assert a["damage_type"] == "wind"

    def test_scaling_values(self, dan_heng_template):
        """倍率对轴：普攻 lvl1=0.5、战技 lvl1=1.3、终结 lvl1=2.4（StarRailRes 参数）."""
        by_type = {a["action_type"]: a for a in dan_heng_template["actions"]}
        assert math.isclose(by_type["basic"]["scaling"][0]["atk"], 0.5)
        assert math.isclose(by_type["skill"]["scaling"][0]["atk"], 1.3)
        assert math.isclose(by_type["ultimate"]["scaling"][0]["atk"], 2.4)


class TestTemplateToEngine:
    def _build(self):
        return {
            "build": {
                "team": [{"character_template": DAN_HENG_ID, "level": 80,
                          "skill_levels": {"basic": 1, "skill": 1, "ultimate": 1, "talent": 1}}],
                "policy": {"name": "p", "action_rules": [
                    {"condition": "energy >= max_energy", "action": "ultimate", "priority": 90},
                    {"condition": "true", "action": "basic", "priority": 0},
                ]},
            }
        }

    def _stage(self):
        return {"stage": {"stage_id": "s", "enemies": [
            {"actor_id": "e", "name": "假人", "hp": 1e9, "spd": 100, "max_toughness": 9999, "weakness": ["wind"]},
        ], "termination": {"mode": "fixed_av", "max_action_value": 200}}}

    def test_template_ref_compiles(self, dan_heng_template):
        """character_template 引用路径打通."""
        compiled = compile_encounter(self._build(), self._stage())
        assert compiled.build_team[0].actor_id == DAN_HENG_ID
        assert len(compiled.actions_by_actor[DAN_HENG_ID]) == 3

    def test_real_character_damage_hand_calc(self, dan_heng_template):
        """真丹恒打风弱假人：伤害 = atk×0.5×0.5×0.9×crit期望（普攻 lvl1，期望模式）."""
        compiled = compile_encounter(self._build(), self._stage())
        engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
        state = engine.run()

        base = dan_heng_template["base_stats"]
        atk = base["atk"]
        crit_expected = base["crit_rate"] * (1 + base["crit_dmg"]) + (1 - base["crit_rate"])
        # def：假人无面板防御 → 200+10×80=1000；attacker_const = 80×10+200=1000 → 0.5
        # 行迹：dmg_bonus.wind 进面板（直加）；atk_pct 经 trace modifier 白值乘算（atk_eff = atk×(1+pct)）
        wind_boost = 1.0 + (base.get("dmg_bonus") or {}).get("wind", 0.0)
        atk_eff = atk * (1.0 + (dan_heng_template.get("trace_stat_effects") or {}).get("atk_pct", 0.0))
        expected = atk_eff * 0.5 * 1.0 * 0.5 * 1.0 * 0.9 * wind_boost * crit_expected
        hits = [l for l in state.log if "丹恒" in l and "伤害" in l]
        assert hits, f"丹恒应有伤害记录：{state.log[:5]}"
        # 丹恒 spd 高于假人，先手两动内敌人不反击；按实际动数×单动期望比对总量
        assert math.isclose(state.total_damage, expected * len(hits), rel_tol=1e-4), (
            f"期望每动 {expected:.1f} × {len(hits)} 动 = {expected * len(hits):.1f}，"
            f"实际 {state.total_damage:.1f}"
        )


class TestScalingNotes:
    def test_hp_scaling_characters_flagged(self):
        """HP/DEF 倍率角色会打 scaling_note 警示（不静默错生成）."""
        from hsr_nous.adapters.template_generator import generate_character_template
        tpl = generate_character_template("1205", level=80, lang="cn")  # 刃：生命倍率
        assert "scaling_notes" in tpl, "刃应有 HP 倍率警示"


@pytest.fixture(scope="module")
def phainon_actions():
    from hsr_nous.adapters.template_generator import generate_character_template
    tpl = generate_character_template("1408", level=80, lang="cn")  # 白厄
    return {a["action_id"]: a for a in tpl["actions"]}


class TestTargetTypeFromRawData:
    """v0.7 写法二（决策卡 #18 补注）：target_type / scaling_blast 忠于原始数据."""

    def test_blast_scaling_blast_from_params(self, phainon_actions):
        """血棘渡亡 140808：blast 形态，副倍率照抄 params（lvl1 主 1.25/副 0.375）."""
        a = phainon_actions["140808"]
        assert a["target_type"] == "blast"
        assert math.isclose(a["scaling"][0]["atk"], 1.25)
        assert math.isclose(a["scaling_blast"][0]["atk"], 0.375)
        # 按等级数组各自成长（lvl2 主 1.5/副 0.45——非固定比例）
        assert math.isclose(a["scaling"][1]["atk"], 1.5)
        assert math.isclose(a["scaling_blast"][1]["atk"], 0.45)

    def test_aoe_and_bounce_from_effect(self, phainon_actions):
        """终结技 140803=AoEAttack→aoe；死星天裁 140811=Bounce→bounce."""
        assert phainon_actions["140803"]["target_type"] == "aoe"
        assert phainon_actions["140811"]["target_type"] == "bounce"

    def test_enhance_has_no_damage_scaling(self, phainon_actions):
        """Enhance 类（140809）：params[0] 不是伤害倍率，清空防误进伤害结算."""
        a = phainon_actions["140809"]
        assert a["target_type"] == "self"
        assert a["scaling"] == [] and a["damage_type"] is None


class TestLightConeTemplate:
    """光锥模板：白值 + properties 语义命名列 + params 占位列."""

    def test_lc_23042_shape(self):
        from hsr_nous.adapters.template_generator import generate_light_cone_template
        tpl = generate_light_cone_template("23042")
        assert tpl["light_cone_id"] == "23042" and tpl["name"] == "愿虹光永驻天空"
        assert tpl["base_stats"]["atk"] > 0 and tpl["base_stats"]["hp"] > 0
        # properties（SpeedAddedRatio）同值对齐并成语义列，顶替 params 第 1 列
        assert math.isclose(tpl["lookup_tables"]["spd_pct"][0], 0.18)
        assert math.isclose(tpl["lookup_tables"]["spd_pct"][4], 0.30)
        assert "param_1" not in tpl["lookup_tables"]
        # 未命中列保留占位名；全 0 列（param_3）跳过
        assert "param_2" in tpl["lookup_tables"]
        assert "param_3" not in tpl["lookup_tables"]
        # bindings 与表一一对应
        assert len(tpl["variable_bindings"]) == len(tpl["lookup_tables"])
        assert tpl["notes"], "机制 desc 应留存 notes 待收编"


class TestRelicSetTemplate:
    def test_relic_102_stat_effects(self):
        from hsr_nous.adapters.template_generator import generate_relic_set_template
        tpl = generate_relic_set_template("102")
        assert tpl["relic_set_id"] == "102"
        # properties 结构化映射：2pc 攻击 12%、4pc 速度 6%
        assert math.isclose(tpl["set_2pc"]["stat_effects"]["atk_pct"], 0.12)
        assert math.isclose(tpl["set_4pc"]["stat_effects"]["spd_pct"], 0.06)
        # desc 未覆盖部分（普攻伤害 10%）不在 properties → notes 留存
        assert tpl["notes"]


class TestFullSmoke:
    """全量生成冒烟：光锥/遗器全量不炸（生成器铁律：不静默错生成）."""

    def test_all_light_cones_generate(self):
        from hsr_nous.pipeline.loader import list_light_cones
        from hsr_nous.adapters.template_generator import generate_light_cone_template
        for lc_id, _ in list_light_cones(lang="cn"):
            tpl = generate_light_cone_template(lc_id)
            assert tpl["base_stats"]["atk"] >= 0

    def test_all_relic_sets_generate(self):
        from hsr_nous.pipeline.loader import list_relic_sets
        from hsr_nous.adapters.template_generator import generate_relic_set_template
        for set_id, _ in list_relic_sets(lang="cn"):
            tpl = generate_relic_set_template(set_id)
            assert tpl["name"]


class TestOutDirDefaults:
    """A4：四个 write_* 缺省 out_dir 同出一处（模板根唯一事实源的子目录）."""

    def test_write_defaults_derive_from_template_root(self):
        import inspect

        from hsr_nous.adapters import template_generator as gen
        from hsr_nous.sim_schema.templates import DEFAULT_TEMPLATE_ROOTS

        root = DEFAULT_TEMPLATE_ROOTS[0]
        expected = {
            "write_character_template": f"{root}/characters",
            "write_light_cone_template": f"{root}/light_cones",
            "write_relic_set_template": f"{root}/relics",
            "write_enemy_template": f"{root}/enemies",
        }
        for name, want in expected.items():
            got = inspect.signature(getattr(gen, name)).parameters["out_dir"].default
            assert got == want, f"{name} 缺省 out_dir {got!r} != {want!r}"
            assert got == gen._OUT_DIRS[want.removeprefix(f"{root}/")]


class TestDescriptionSidecar:
    """呈现层旁车（descriptions/）：官方中文 desc/params + 能量槽显示名，web 调试台旁路消费."""

    def test_sidecar_shape_phainon(self):
        """1408 旁车（F3 扩员后）：技能条目全收（普攻/战技/终结技/天赋×2/秘技/MazeNormal +
        变身三组，共 10 条），大行迹 3 节点（1408101-103，属性小行迹/技能等级节点不收）；
        desc 原文带占位符、params 按档原样（lv10=末档 1.4），energy_name=火种（天赋文本已查证）."""
        from hsr_nous.adapters.template_generator import generate_description_sidecar
        sc = generate_description_sidecar("1408")
        assert sc["actor_id"] == "1408" and sc["energy_name"] == "火种"
        assert set(sc["actions"]) == {"140801", "140802", "140803", "140804", "140805",
                                      "140806", "140807", "140808", "140809", "140811"}
        basic = sc["actions"]["140801"]
        assert basic["name"] == "逐火救世，行则将至"
        assert "#1[i]" in basic["desc"] and basic["params"][-1] == [1.4]
        # 天赋/秘技条目（扩员点）：带官方 type_text 作来源展开卡类型标签
        assert sc["actions"]["140804"]["name"] == "此身为炬"
        assert sc["actions"]["140804"]["type_text"] == "天赋"
        assert sc["actions"]["140805"]["name"] == "命运•此躯即神"
        assert sc["actions"]["140807"]["type_text"] == "秘技"
        # 大行迹节点：name+desc+params（照见英雄本色 lv1：攻+50%、至多 2 层）
        assert set(sc["traces"]) == {"1408101", "1408102", "1408103"}
        t3 = sc["traces"]["1408103"]
        assert t3["name"] == "照见英雄本色" and "#1[i]" in t3["desc"]
        assert t3["params"][-1] == [0.5, 2]

    def test_sidecar_ranks_phainon(self):
        """ranks 段：1408 六魂全收（rank id 前缀 char_id），E2 官方描述含"抗性穿透"；
        rank/name/desc/params 原样抽（cn 全表 params 为 null → 空表回落）。"""
        from hsr_nous.adapters.template_generator import generate_description_sidecar
        ranks = generate_description_sidecar("1408")["ranks"]
        assert set(ranks) == {"140801", "140802", "140803", "140804", "140805", "140806"}
        e2 = ranks["140802"]
        assert e2["rank"] == 2 and e2["name"] == "天与地，世间的泡沫"
        assert "抗性穿透" in e2["desc"] and e2["params"] == []
        assert ranks["140806"]["name"] == "亘古长升，蚀火残阳"
        assert "神经仿绣图" == generate_description_sidecar("1303")["ranks"]["130301"]["name"]

    def test_energy_name_official_names_only(self):
        """能量名收录闸：表外角色 → None（前端回落"能量"）；
        表与 sim/battles 特殊充能硬表逐项一致（两处手工表的防漂移闸）."""
        import json
        from pathlib import Path

        from hsr_nous.adapters.template_generator import (
            _ENERGY_NAMES_JSON, generate_description_sidecar)
        from hsr_nous.sim import battles

        assert generate_description_sidecar("1001")["energy_name"] is None  # 三月七：普通能量
        table = json.loads(_ENERGY_NAMES_JSON.read_text(encoding="utf-8"))
        for cid, name in battles._SPECIAL_CHARGE_BY_ID.items():
            assert table.get(cid) == name, f"{cid}：旁车能量名表与 battles 硬表漂移（{name}）"

    def test_write_sidecar_roundtrip(self, tmp_path):
        """写盘回读：{char_id}.json 可解析、字段齐；无骨架角色 ValueError."""
        import json
        from pathlib import Path

        from hsr_nous.adapters.template_generator import write_description_sidecar
        p = write_description_sidecar("1408", out_dir=str(tmp_path))
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        assert doc["actor_id"] == "1408" and "140801" in doc["actions"]
        with pytest.raises(ValueError, match="无骨架"):
            write_description_sidecar("9999", out_dir=str(tmp_path))
