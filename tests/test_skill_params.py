"""params 引用 `param(<skill_id>, <N>)`（05_effects §5.1）编译期取档闸.

语义钉：
- 取档等级 = 编译期最终 skill_levels[level_key]（默认档 + member 覆写 + 星魂
  skill_level_overrides 加算之后）；level_key 缺键回落 ultimate（引擎 _skill_level_of 同口径）；
- 越档钳表尾 + ⚠ 编译警告（忆灵族 10 档上限无第 11 档）；无表/序号越界/语法非法编译期炸；
- 一切过表达式预编译闸的字符串槽同通道（effects 数值槽/modifier stat_effects/stat_exprs/
  condition/action apply_modifiers/召唤物侧 hooks——读模板主角色等级）。
"""
from __future__ import annotations

import pytest
import yaml

from hsr_nous.sim.compile import compile_encounter

#: 15 档表——逐档可辨（lvN 第 1 项 = N，第 2 项 = N×10，第 3 项 = N×100）
_ROWS15 = [[float(n), float(n * 10), float(n * 100)] for n in range(1, 16)]
#: 10 档表（忆灵族上限）
_ROWS10 = [[float(n), float(n * 10)] for n in range(1, 11)]

_STAGE = {"stage": {"stage_id": "s", "enemies": [
    {"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 50,
     "max_toughness": 9999, "weakness": ["physical"]}],
    "termination": {"mode": "fixed_av", "max_action_value": 70}}}


def _tpl(*, eidolons=None, summons=None, hooks=None, apply_mods=None):
    """最小合法角色模板：skill_params 双表（9001=skill 15 档 / 19001=memosprite_skill 10 档）."""
    action = {"action_id": "pb", "name": "普攻", "action_type": "basic",
              "target_type": "single", "damage_type": "physical",
              "scaling": [{"atk": 1.0}]}
    if apply_mods is not None:
        action["apply_modifiers"] = apply_mods
    return {
        "actor_id": "p1", "name": "测试员", "level": 80,
        "base_stats": {"atk": 1000, "spd": 100, "hp": 3000, "max_energy": 100},
        "skill_params": {
            "9001": {"level_key": "skill", "rows": _ROWS15},
            "19001": {"level_key": "memosprite_skill", "rows": _ROWS10},
        },
        "actions": [action],
        "hooks": hooks if hooks is not None else [
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(9001, 1)"}]}],
        **({"eidolons": eidolons} if eidolons else {}),
        **({"summons": summons} if summons else {}),
    }


def _compile(tmp_path, tpl, *, eidolon=0, skill_levels=None):
    d = tmp_path / "characters"
    d.mkdir(parents=True, exist_ok=True)
    (d / "p1_测试员.yaml").write_text(yaml.safe_dump(tpl, allow_unicode=True),
                                     encoding="utf-8")
    member = {"character_template": "p1", "level": 80, "eidolon": eidolon}
    if skill_levels:
        member["skill_levels"] = skill_levels
    build = {"build": {"team": [member],
                       "policy": {"name": "p", "action_rules": [
                           {"condition": "true", "action": "basic", "priority": 0}]}}}
    return compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])


def _hook_amounts(compiled, owner="p1"):
    return [eff.get("amount") for h in compiled.hooks if h.owner_id == owner
            for eff in h.effects]


class TestSkillParams:
    def test_base_level_row(self, tmp_path):
        """基础取档：默认 skill 10 → 第 10 行第 1 项 = 10.0（编译期已替换为字面量）."""
        compiled = _compile(tmp_path, _tpl())
        assert 10.0 in _hook_amounts(compiled), (
            f"param(9001,1) 应按 lv10 取 10.0：{_hook_amounts(compiled)}")

    def test_member_skill_levels_override(self, tmp_path):
        """member skill_levels 覆写参与取档：skill=5 → 5.0."""
        compiled = _compile(tmp_path, _tpl(), skill_levels={"skill": 5})
        assert 5.0 in _hook_amounts(compiled)

    def test_eidolon_level_jump(self, tmp_path):
        """E3 跳档（10→12）：skill_level_overrides 加算后取第 12 行——星魂档在 hook 编译前定稿."""
        eidolons = {"E3": {"name": "等级魂", "skill_level_overrides": {"skill": 2}}}
        e0 = _compile(tmp_path / "e0", _tpl(eidolons=eidolons), eidolon=0)
        e3 = _compile(tmp_path / "e3", _tpl(eidolons=eidolons), eidolon=3)
        assert 10.0 in _hook_amounts(e0)
        assert 12.0 in _hook_amounts(e3), (
            f"E3 skill+2 后应取 lv12=12.0：{_hook_amounts(e3)}")
        lv = next(a for a in e3.build_team if a.actor_id == "p1").skill_levels
        assert lv["skill"] == 12

    def test_memosprite_cap_clamp_warns(self, tmp_path):
        """cap 钳位：忆灵槽 10 档表 + 星魂 +1 → lv11 越界 → 钳表尾 lv10 + ⚠ 编译警告."""
    def test_memosprite_eidolon_plus_one_to_lv7(self, tmp_path):
        """忆灵槽 E0 种子 lv6（三源互证见 build_compiler._SkillParams 类注）+ 星魂 +1
        → lv7 表内取档（不警告）——官方原文"Memosprite Skill Lv. +1, up to a maximum
        of Lv. 10"的实档."""
        eidolons = {"E3": {"name": "忆灵魂",
                           "skill_level_overrides": {"memosprite_skill": 1}}}
        tpl = _tpl(eidolons=eidolons, hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(19001, 2)"}]}])
        import warnings as _w
        with _w.catch_warnings():
            _w.simplefilter("error")   # lv7 在表内——任何钳位警告都视为失败
            compiled = _compile(tmp_path, tpl, eidolon=3)
        assert 70.0 in _hook_amounts(compiled), (
            f"E3 忆灵技+1 应取 lv7 第 2 项=70.0：{_hook_amounts(compiled)}")
        lv = next(a for a in compiled.build_team if a.actor_id == "p1").skill_levels
        assert lv["memosprite_skill"] == 7

    def test_memosprite_cap_clamp_warns(self, tmp_path):
        """cap 钳位：member skill_levels 忆灵槽 11（越官方 cap 10 的误写）→
        取档越出 10 档表尾 → 钳表尾 lv10 + ⚠（星魂 +1 走 levels 阶段 cap 10 正档，
        不经本钳位——见 test_memosprite_eidolon_plus_one_to_lv7）."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(19001, 2)"}]}])
        with pytest.warns(UserWarning, match="钳到表尾"):
            compiled = _compile(tmp_path, tpl,
                                skill_levels={"memosprite_skill": 11})
        assert 100.0 in _hook_amounts(compiled), (
            f"钳到表尾应取 lv10 第 2 项=100.0：{_hook_amounts(compiled)}")

    def test_memosprite_default_level_silent(self, tmp_path):
        """忆灵槽缺省 lv6 不警告（种子值——E0 游戏内上限，角色 skill_levels 无此键）."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(19001, 2)"}]}])
        compiled = _compile(tmp_path, tpl)
        assert 60.0 in _hook_amounts(compiled), (
            f"缺省应取 lv6 第 2 项=60.0：{_hook_amounts(compiled)}")

    def test_missing_table_rejected(self, tmp_path):
        """无表报错：param() 引用未声明的技能 id → 编译期炸."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(9999, 1)"}]}])
        with pytest.raises(ValueError, match="无表"):
            _compile(tmp_path, tpl)

    def test_index_out_of_range_rejected(self, tmp_path):
        """序号越界：N 越出该行长度 → 编译期炸（N 从 1 起）."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param(9001, 4)"}]}])
        with pytest.raises(ValueError, match="序号越界"):
            _compile(tmp_path, tpl)

    def test_bad_syntax_rejected(self, tmp_path):
        """语法非法：id 加引号 → 替换后残留 param( → 编译期炸并指路."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "gain_skill_point",
                          "amount": "param('9001', 1)"}]}])
        with pytest.raises(ValueError, match="param 引用语法非法"):
            _compile(tmp_path, tpl)

    def test_mixed_with_expression(self, tmp_path):
        """混写：param(...)*0.5 族——替换为字面量后过同一表达式预编译闸."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "deal_damage",
                          "scaling_atk": "param(9001, 1) * 0.5"}]}])
        compiled = _compile(tmp_path, tpl)
        vals = [eff.get("scaling_atk") for h in compiled.hooks for eff in h.effects]
        assert "10 * 0.5" in vals, f"混写应替换为字面量表达式：{vals}"

    def test_modifier_stat_effects_float_channel(self, tmp_path):
        """apply_modifier stat_effects：param() 纯字面量回 float 主通道（不留表达式串）."""
        tpl = _tpl(hooks=[
            {"event": "on_battle_start",
             "effects": [{"effect_type": "apply_modifier",
                          "modifier": {"modifier_id": "M", "modifier_type": "buff",
                                       "duration": 1,
                                       "stat_effects": {"all_dmg": "param(9001, 2)"}}}]}])
        compiled = _compile(tmp_path, tpl)
        se = [eff["modifier"]["stat_effects"] for h in compiled.hooks for eff in h.effects
              if eff.get("effect_type") == "apply_modifier"]
        assert se and se[0].get("all_dmg") == 100.0 and isinstance(se[0]["all_dmg"], float), (
            f"stat_effects 应回 float 通道 lv10 第 2 项=100.0：{se}")

    def test_action_apply_modifiers_channel(self, tmp_path):
        """action apply_modifiers 同通道（雨过天晴族正主槽位）."""
        apply_mods = [{"target": "self", "modifier_id": "M", "modifier_type": "buff",
                       "duration": 3, "stat_effects": {"hp_pct": "param(9001, 1)"}}]
        compiled = _compile(tmp_path, _tpl(apply_mods=apply_mods))
        act = next(a for a in compiled.actions_by_actor["p1"] if a.action_id == "pb")
        assert act.apply_modifiers[0]["stat_effects"]["hp_pct"] == 10.0

    def test_summon_hook_reads_owner_levels(self, tmp_path):
        """召唤物侧 hooks 引用角色模板表、取模板主角色等级（星魂覆写落在角色上）."""
        eidolons = {"E5": {"name": "等级魂", "skill_level_overrides": {"skill": 2}}}
        summons = {"p1_pet": {"name": "宠物", "inheritance": "full",
                              "hooks": [{"event": "on_battle_start",
                                         "effects": [{"effect_type": "gain_skill_point",
                                                      "amount": "param(9001, 3)"}]}]}}
        e5 = _compile(tmp_path, _tpl(eidolons=eidolons, summons=summons), eidolon=5)
        assert 1200.0 in _hook_amounts(e5, owner="p1_pet"), (
            f"召唤物 hook 应读角色 lv12 第 3 项=1200.0：{_hook_amounts(e5, 'p1_pet')}")

    def test_light_cone_context_no_table(self, tmp_path):
        """光锥 hooks 语境无角色等级轨道——param() 等同无表编译期炸."""
        d = tmp_path / "characters"
        d.mkdir(parents=True, exist_ok=True)
        (d / "p1_测试员.yaml").write_text(yaml.safe_dump(_tpl(), allow_unicode=True),
                                         encoding="utf-8")
        lc = tmp_path / "light_cones"
        lc.mkdir(exist_ok=True)
        (lc / "9001_测试锥.yaml").write_text(yaml.safe_dump({
            "light_cone_id": "9001", "name": "测试锥", "rarity": 5, "path": "remembrance",
            "base_stats": {"hp": 1000, "atk": 500, "def": 500},
            "hooks": [{"event": "on_battle_start",
                       "effects": [{"effect_type": "gain_skill_point",
                                    "amount": "param(9001, 1)"}]}],
        }, allow_unicode=True), encoding="utf-8")
        build = {"build": {"team": [{"character_template": "p1", "level": 80,
                                     "light_cone_template": "9001"}],
                           "policy": {"name": "p", "action_rules": [
                               {"condition": "true", "action": "basic", "priority": 0}]}}}
        with pytest.raises(ValueError, match="无表"):
            compile_encounter(build, _STAGE, template_roots=[str(tmp_path)])

    def test_skill_params_shape_gates(self, tmp_path):
        """skill_params 形状闸：level_key 缺失 / rows 空 / 行非数值列表均编译期炸."""
        bad = _tpl()
        bad["skill_params"]["9001"] = {"rows": _ROWS15}
        with pytest.raises(ValueError, match="level_key"):
            _compile(tmp_path / "a", bad)
        bad2 = _tpl()
        bad2["skill_params"]["9001"] = {"level_key": "skill", "rows": []}
        with pytest.raises(ValueError, match="rows"):
            _compile(tmp_path / "b", bad2)
        bad3 = _tpl()
        bad3["skill_params"]["9001"] = {"level_key": "skill", "rows": [["x"]]}
        with pytest.raises(ValueError, match="数值列表"):
            _compile(tmp_path / "c", bad3)
