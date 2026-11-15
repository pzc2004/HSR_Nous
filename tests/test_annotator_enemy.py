"""enemy 打标 DAG：机械直译零 LLM、未支持入人工队列、缓存重放."""
from __future__ import annotations

import json

import yaml

from hsr_nous.ops.annotator import FakeRunner, run_enemy
from hsr_nous.ops.annotator import enemy_nodes
from hsr_nous.ops.annotator.batch import KINDS, collect_targets


def _official():
    return {
        "kind": "enemy", "id": "fake_enemy", "name": "假人",
        "base_template": {
            "enemy_id": "fake_enemy", "name": "假人", "level": 80,
            "base_stats": {"hp": 10000, "atk": 100, "def": 100, "spd": 100,
                           "max_toughness": 30, "effect_res": 0},
            "weakness": ["physical"], "resistance": {}, "actions": [],
            "policy": {"sequence": ["s1"], "cooldown": {}, "initial_cooldown": {}},
            "notes": [],
        },
        "skills": [{
            "skill_id": "s1", "trigger_key": "Skill01", "damage_type": "Physical",
            "sp_hit_base": 10, "param_list": [2.5], "phase_list": [], "modifier_list": [],
        }],
        "sources": {
            "character_config": {
                "SkillList": [{
                    "Name": "Skill01", "SkillType": "Skill",
                    "TargetInfo": {"TargetType": "EnemySelect"}, "EntryAbility": "A",
                }],
                "AbilityList": [],
                "DynamicValues": {"Floats": {"10": {"ReadInfo": {
                    "Type": "SkillParam", "TriggerKey": "Skill01", "Index": 0,
                }}}},
            },
            "abilities": {"A": {"Name": "A", "OnStart": [{
                "$type": "RPG.GameCore.DamageByAttackProperty",
                "TargetType": {"$type": "RPG.GameCore.TargetAlias",
                               "Alias": "AbilityTargetEntity"},
                "AttackProperty": {
                    "$type": "RPG.GameCore.AttackData",
                    "DamageType": {"DamageType": "Physical"},
                    "DamagePercentage": {"IsDynamic": True, "PostfixExpr": {
                        "OpCodes": "AQAR", "FixedValues": [], "DynamicHashes": [10],
                    }},
                    "SPHitRatio": {"IsDynamic": False, "FixedValue": {"Value": 1}},
                },
            }]}},
            "modifiers": {}, "ability_sources": {"A": "fixture"},
            "source_files": ["fixture"], "missing_abilities": [], "missing_modifiers": [],
            "ambiguous": [], "invalid_files": [],
        },
        "semantics": {"Skill01": {"name": "测试攻击", "energy": 0}},
    }


def test_enemy_full_mechanical_chain_uses_zero_llm_and_replays(tmp_path, monkeypatch):
    monkeypatch.setattr(enemy_nodes, "_load_enemy", lambda _enemy_id: _official())
    llm = FakeRunner([])
    kwargs = {"llm": llm, "runs_root": tmp_path / "runs",
              "staging_root": tmp_path / "staging"}
    out = run_enemy("fake_enemy", **kwargs)
    assert "finalize" in out and "human_queue" not in out
    assert out["draft"]["ok"] and out["smoke"]["turns"] > 0
    assert llm.calls == []
    path = tmp_path / "staging" / "enemies" / "fake_enemy_假人.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["actions"][0]["scaling"] == [{"atk": 2.5}]
    evidence = json.loads((tmp_path / "staging" / "notes" / "fake_enemy.json")
                          .read_text(encoding="utf-8"))
    assert evidence["llm_calls"] == 0

    def forbidden(_enemy_id):
        raise AssertionError("缓存重放不应重新拉取数据")

    monkeypatch.setattr(enemy_nodes, "_load_enemy", forbidden)
    replayed = run_enemy("fake_enemy", **kwargs)
    assert replayed["finalize"] == out["finalize"]
    events = (tmp_path / "runs" / "enemies" / "fake_enemy" / "events.jsonl").read_text()
    assert '"event": "cached"' in events
    assert llm.calls == []


def test_enemy_unsupported_goes_human_queue_without_llm(tmp_path, monkeypatch):
    official = _official()
    official["sources"]["abilities"]["A"]["OnStart"].append({
        "$type": "RPG.GameCore.PredicateTaskList",
        "SuccessTaskList": [{"$type": "RPG.GameCore.DefineDynamicValue"}],
    })
    monkeypatch.setattr(enemy_nodes, "_load_enemy", lambda _enemy_id: official)
    llm = FakeRunner([])
    out = run_enemy("fake_enemy", llm=llm, runs_root=tmp_path / "runs",
                    staging_root=tmp_path / "staging")
    assert "human_queue" in out and "finalize" not in out
    assert "PredicateTaskList" in out["human_queue"]["trail"]
    assert llm.calls == []


def test_enemy_batch_kind_registration():
    assert "enemy" in KINDS
    assert collect_targets(kind="enemy", ids=["fake_enemy"]) == ["fake_enemy"]


def test_enemy_batch_does_not_initialize_llm(tmp_path, monkeypatch):
    from hsr_nous.ops.annotator import batch

    def forbidden_llm(**_kwargs):
        raise AssertionError("机械 enemy 批处理不应初始化 LLM")

    monkeypatch.setattr(batch, "make_tribios_runner", forbidden_llm)
    monkeypatch.setattr(batch, "_RUNNERS", {
        "enemy": lambda _cid, **_kwargs: {"finalize": {"staging": "candidate"}},
    })
    out = batch.run_batch(["fake_enemy"], kind="enemy", runs_root=tmp_path)
    assert out["results"]["fake_enemy"]["status"] == "finalized"
