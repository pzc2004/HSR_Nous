"""战斗配置库（battles.py）测试：CRUD 往返 / 空目录自动物化 / preview 解析.

全部用 tmp_path 替换 BATTLES_DIR，不碰真实 data/battles。
"""

from pathlib import Path

import pytest
import yaml

from hsr_nous.sim import battles

BUILD_YAML = yaml.safe_dump({
    "build": {
        "team": [{
            "character_template": "inline",
            "actor_id": "hero",
            "name": "测试员",
            "level": 80,
            "base_stats": {"atk": 1000, "spd": 120, "hp": 3000, "max_energy": 100},
            "actions": [{
                "action_id": "hero_basic", "name": "普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 1.0}],
            }],
        }],
        "policy": {
            "name": "default",
            "action_rules": [{"condition": "true", "action": "basic", "priority": 0}],
            "target_rules": [],
            "parameters": {},
        },
    }
}, allow_unicode=True)

STAGE_YAML = yaml.safe_dump({
    "stage": {
        "stage_id": "t",
        "enemies": [
            {"actor_id": "e1", "name": "假人甲", "hp": 1e9, "spd": 100},
            {"actor_id": "e2", "name": "假人乙", "hp": 1e9, "spd": 90},
        ],
        "waves": [{"wave_index": 2, "enemies": [
            {"actor_id": "e3", "name": "假人丙", "hp": 1e9, "spd": 80},
        ]}],
        "termination": {"mode": "fixed_av", "max_action_value": 150},
    }
}, allow_unicode=True)


@pytest.fixture(autouse=True)
def tmp_battles_dir(tmp_path, monkeypatch):
    d = tmp_path / "battles"
    monkeypatch.setattr(battles, "BATTLES_DIR", d)
    return d


def test_crud_roundtrip(tmp_battles_dir):
    battles.save_battle("测试局", "一句话描述", BUILD_YAML, STAGE_YAML)
    build_yaml, stage_yaml = battles.load_battle("测试局")
    assert build_yaml == BUILD_YAML and stage_yaml == STAGE_YAML
    entries = battles.list_battles()
    hit = next(e for e in entries if e["name"] == "测试局")
    assert hit["description"] == "一句话描述"
    # 同名保存 = 覆盖
    battles.save_battle("测试局", "新描述", BUILD_YAML, STAGE_YAML)
    assert next(e for e in battles.list_battles() if e["name"] == "测试局")["description"] == "新描述"
    battles.delete_battle("测试局")
    with pytest.raises(KeyError):
        battles.load_battle("测试局")
    with pytest.raises(KeyError):
        battles.delete_battle("测试局")


def test_save_validates_yaml_and_name(tmp_battles_dir):
    with pytest.raises(ValueError):
        battles.save_battle("x", "", "不是 yaml: [", STAGE_YAML)
    with pytest.raises(ValueError):
        battles.save_battle("x", "", "foo: 1", STAGE_YAML)  # 顶层缺 build 键
    for bad in ("", "a/b", "a\\b", "a:b", 'a"b', ".."):
        with pytest.raises(ValueError):
            battles.save_battle(bad, "", BUILD_YAML, STAGE_YAML)
    assert not tmp_battles_dir.exists() or not list(tmp_battles_dir.glob("*.yaml"))


def test_empty_dir_auto_seeds_demos(tmp_battles_dir):
    entries = battles.list_battles()
    assert len(entries) == 4
    names = {e["name"] for e in entries}
    assert names == {"demo_黄泉队", "demo_停云白板", "demo_白厄", "demo_白厄队"}
    for e in entries:
        assert e["description"] and e["team_preview"] and e["stage_preview"]
    # 删掉一个不再复活；删光（目录空）= 恢复出厂，四个演示局重新物化
    battles.delete_battle("demo_停云白板")
    assert {e["name"] for e in battles.list_battles()} == {"demo_黄泉队", "demo_白厄", "demo_白厄队"}
    for name in ("demo_黄泉队", "demo_白厄", "demo_白厄队"):
        battles.delete_battle(name)
    assert len(battles.list_battles()) == 4


def test_preview_inline_names_and_waves(tmp_battles_dir):
    team, stage = battles.preview_names(BUILD_YAML, STAGE_YAML)
    assert team == ["测试员"]
    assert stage == ["假人甲", "假人乙", "假人丙"]  # 含 waves 里的敌人


def test_preview_template_ref_resolution(tmp_battles_dir, tmp_path, monkeypatch):
    """模板引用按 {root}/{kind}/<ref>_<名>.yaml 文件名解析显示名；找不到回退引用串。"""
    root = tmp_path / "templates"
    (root / "characters").mkdir(parents=True)
    (root / "enemies").mkdir(parents=True)
    (root / "characters" / "9999_开拓者•欢愉.yaml").write_text("x: 1", encoding="utf-8")
    monkeypatch.setattr(battles, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    build = yaml.safe_dump({"build": {"team": [
        {"character_template": "9999", "level": 80},
        {"character_template": "8888", "level": 80},  # 无对应文件 → 回退 "8888"
        {"actor_id": "anon"},                          # 既无名也无引用 → actor_id
    ]}}, allow_unicode=True)
    stage = yaml.safe_dump({"stage": {"enemies": [
        {"enemy_template": "1001", "actor_id": "e1"},  # enemies/ 下无文件 → 回退 "1001"
    ]}}, allow_unicode=True)
    team, enemy = battles.preview_names(build, stage)
    assert team == ["开拓者•欢愉", "8888", "anon"]
    assert enemy == ["1001"]


def test_preview_bad_yaml_gives_empty(tmp_battles_dir):
    assert battles.preview_names("[: 坏", "[: 也坏") == ([], [])


def _mk_char_template(root: Path, ref: str, name: str, **extra) -> None:
    (root / "characters").mkdir(parents=True, exist_ok=True)
    doc = {"actor_id": ref, "name": name, "level": 80, "base_stats": {"max_energy": 130.0}}
    doc.update(extra)
    (root / "characters" / f"{ref}_{name}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")


def test_preview_special_charge_annotation(tmp_battles_dir, tmp_path, monkeypatch):
    """④ 特殊充能标注三路径：DSL energy_name > 注释显式声明 > max_energy 阈值；正常人无标注。"""
    root = tmp_path / "templates"
    _mk_char_template(root, "1308", "黄泉", base_stats={"max_energy": 9.0},
                      energy_name="残梦")                                          # DSL 字段 → 残梦
    _mk_char_template(root, "1407", "遐蝶", base_stats={"max_energy": 0.0},
                      trace_notes=["max_sp 为 null：特殊充能角色（新蕊类），能量机制待人工"])  # 注释 → 新蕊
    _mk_char_template(root, "7777", "测试员甲", base_stats={"max_energy": 24.0})   # 阈值 → 通称
    _mk_char_template(root, "1202", "停云")                                        # 130 正常 → 无标注
    monkeypatch.setattr(battles, "DEFAULT_TEMPLATE_ROOTS", (str(root),))
    build = yaml.safe_dump({"build": {"team": [
        {"character_template": "1308", "level": 80},
        {"character_template": "1407", "level": 80},
        {"character_template": "7777", "level": 80},
        {"character_template": "1202", "level": 80},
    ]}}, allow_unicode=True)
    team, _ = battles.preview_names(build, "stage: {}")
    assert team == ["黄泉·残梦", "遐蝶·新蕊", "测试员甲·特殊充能", "停云"]


_DEMO_TEMPLATE_IDS = ("1202", "1304", "1308", "1403", "1408")
_DEMO_TEMPLATES_PRESENT = all(
    any(Path("data/sim_templates/characters").glob(f"{i}_*.yaml")) for i in _DEMO_TEMPLATE_IDS)


@pytest.mark.skipif(
    not _DEMO_TEMPLATES_PRESENT,
    reason="本地无 data/sim_templates 角色模板（gitignored），演示局编译冒烟跳过")
def test_seeded_demos_compile(tmp_battles_dir):
    """数据环境下三个演示局都能真实编译（演示配置不是摆设）。"""
    from hsr_nous.sim.compile import compile_encounter_yaml
    for e in battles.list_battles():
        compiled = compile_encounter_yaml(*battles.load_battle(e["name"]))
        assert compiled.build_team and compiled.stage.enemies


@pytest.mark.skipif(
    not _DEMO_TEMPLATES_PRESENT,
    reason="本地无 data/sim_templates 角色模板（gitignored），演示局标注冒烟跳过")
def test_demo_preview_special_charge_annotation(tmp_battles_dir):
    """数据环境下演示局预览标注：黄泉·残梦 / 白厄·火种；停云正常人无标注。"""
    entries = {e["name"]: e for e in battles.list_battles()}
    assert entries["demo_黄泉队"]["team_preview"][0] == "黄泉·残梦"
    assert entries["demo_白厄"]["team_preview"] == ["白厄·火种"]
    assert entries["demo_停云白板"]["team_preview"] == ["停云"]


# ---------------------------------------------------------------------------
# 附加模板根（EXTRA_TEMPLATE_ROOTS，web --templates 同款机制）
# ---------------------------------------------------------------------------

def test_extra_template_roots_priority_and_fallback(tmp_path, monkeypatch):
    """附加根优先：同 id 双根都有 → 解析自附加根；附加根缺失的 id → 回落默认根。"""
    extra, default = tmp_path / "extra", tmp_path / "default"
    _mk_char_template(extra, "1408", "白厄·人工版")      # 同 id 双根都有 → 附加根压制
    _mk_char_template(default, "1408", "白厄·生成版")
    _mk_char_template(default, "1308", "黄泉")           # 仅默认根有 → 回落
    monkeypatch.setattr(battles, "DEFAULT_TEMPLATE_ROOTS", (str(default),))
    monkeypatch.setattr(battles, "EXTRA_TEMPLATE_ROOTS", [str(extra)])
    assert battles.template_doc("characters", "1408")["name"] == "白厄·人工版"
    assert battles.template_doc("characters", "1308")["name"] == "黄泉"
    assert battles.template_roots() == (str(extra), str(default))
    # 清空附加根（set_extra_template_roots 覆盖式）→ 全部回默认根
    battles.set_extra_template_roots([])
    assert battles.template_doc("characters", "1408")["name"] == "白厄·生成版"


def test_battle_catalog_merges_extra_roots(tmp_path, monkeypatch):
    """catalog 跨根合并：同 id 附加根压制 + 默认根补全（不只列附加根那几份）。"""
    extra, default = tmp_path / "extra", tmp_path / "default"
    _mk_char_template(extra, "1408", "白厄·人工版")
    _mk_char_template(default, "1408", "白厄·生成版")
    _mk_char_template(default, "1308", "黄泉")
    monkeypatch.setattr(battles, "DEFAULT_TEMPLATE_ROOTS", (str(default),))
    monkeypatch.setattr(battles, "EXTRA_TEMPLATE_ROOTS", [str(extra)])
    chars = {c["id"]: c["name"] for c in battles.battle_catalog()["characters"]}
    assert chars == {"1408": "白厄·人工版", "1308": "黄泉"}


def test_template_hit_provenance(tmp_path, monkeypatch):
    """template_hit 带 provenance：附加根命中 "anchor" / 默认根命中 "generated" / 未命中 None；
    catalog 角色行同源标记。"""
    extra, default = tmp_path / "extra", tmp_path / "default"
    _mk_char_template(extra, "1408", "白厄·人工版")
    _mk_char_template(default, "1408", "白厄·生成版")
    _mk_char_template(default, "1308", "黄泉")
    monkeypatch.setattr(battles, "DEFAULT_TEMPLATE_ROOTS", (str(default),))
    monkeypatch.setattr(battles, "EXTRA_TEMPLATE_ROOTS", [str(extra)])
    path, source = battles.template_hit("characters", "1408")
    assert source == battles.TEMPLATE_SOURCE_ANCHOR and path.parent.parent == extra
    path2, source2 = battles.template_hit("characters", "1308")
    assert source2 == battles.TEMPLATE_SOURCE_GENERATED and path2.parent.parent == default
    assert battles.template_hit("characters", "9999") is None
    chars = {c["id"]: c["source"] for c in battles.battle_catalog()["characters"]}
    assert chars == {"1408": "anchor", "1308": "generated"}


_FIXTURES_TEMPLATES = Path(__file__).parent / "fixtures" / "templates"
_FIXTURE_PHAINON = _FIXTURES_TEMPLATES / "characters" / "1408_phainon.yaml"


@pytest.mark.skipif(
    not (_DEMO_TEMPLATES_PRESENT and _FIXTURE_PHAINON.is_file()),
    reason="本地无 data/sim_templates 角色模板（gitignored）或 fixtures 锚模板，真实根优先级冒烟跳过")
def test_extra_roots_real_fixtures_override(monkeypatch):
    """真实根：fixtures 人工锚模板压 data/ 生成骨架（1408 出形态机），其余角色照常 data/。"""
    monkeypatch.setattr(battles, "EXTRA_TEMPLATE_ROOTS", [str(_FIXTURES_TEMPLATES)])
    doc = battles.template_doc("characters", "1408")
    assert (doc.get("state_config") or {}).get("state") == "khaslana"  # fixtures 形态机件
    fallback = battles.template_doc("characters", "1308")              # fixtures 无 → 回落 data/
    assert fallback is not None and fallback.get("name") == "黄泉"
    battles.set_extra_template_roots([])
    plain = battles.template_doc("characters", "1408")                 # 缺省链：生成骨架无形态机
    assert plain is not None and not (plain.get("state_config") or {})
