"""敌人打标 DAG：TBGD Ability 机械编译，完整支持时零 LLM.

链：data_pull → crosscheck → draft → compile → smoke → golden_diff → finalize。
任一未知节点/缺引用/覆盖缺口直接 human_queue；不把未知语义交给 LLM 脑补。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from hsr_nous.adapters.enemy_ability import AbilityCompiler
from hsr_nous.ops.annotator.nodes import _human_queue_node
from hsr_nous.ops.dag import Node
from hsr_nous.pipeline.paths import annotator_dir, library_dir, sim_templates_dir


def _load_enemy(enemy_id: str) -> Dict[str, Any]:
    """独立取数口，测试可替换为小 fixture；生产全部来自 pipeline/旧模板回归锚."""
    from hsr_nous.adapters.template_generator import generate_enemy_template
    from hsr_nous.pipeline.enemies.loader import (
        get_enemy_ability_sources, get_enemy_mechanics, get_enemy_skills)

    template = generate_enemy_template(str(enemy_id))
    skills = get_enemy_skills(str(enemy_id))
    by_id = {str(skill["skill_id"]): skill for skill in skills}
    fdata = get_enemy_mechanics(template["name"], weakness=template.get("weakness")) or {}
    semantic_by_name = {s.get("name"): s for s in fdata.get("skills") or []}
    semantics = {}
    for action in template.get("actions") or []:
        raw = by_id.get(str(action.get("action_id")))
        if raw and raw.get("trigger_key"):
            semantics[str(raw["trigger_key"])] = {
                **(semantic_by_name.get(action.get("name")) or {}),
                "name": action.get("name"), "energy": action.get("energy_grant") or 0,
            }
    return {
        "kind": "enemy", "id": str(enemy_id), "name": template["name"],
        "base_template": template, "skills": skills,
        "sources": get_enemy_ability_sources(str(enemy_id)), "semantics": semantics,
    }


def data_pull_enemy_node(enemy_id: str) -> Node:
    def fn(_inputs: Dict[str, Any]) -> Dict[str, Any]:
        return _load_enemy(str(enemy_id))
    return Node("data_pull", fn, service="game_data")


def crosscheck_enemy_node(enemy_id: str) -> Node:
    """机械核对 trigger/EntryAbility/本地引用；冲突只报告，draft 给出最终覆盖判定."""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        official = inputs["data_pull"]
        config = official["sources"].get("character_config") or {}
        config_skills = {str(s.get("Name")): s for s in config.get("SkillList") or []}
        rows: List[Dict[str, Any]] = []
        conflicts: List[Dict[str, Any]] = []
        for skill in official["skills"]:
            trigger = str(skill.get("trigger_key") or "")
            entry = (config_skills.get(trigger) or {}).get("EntryAbility")
            ok = bool(trigger and entry)
            rows.append({"item": f"{skill['skill_id']}.EntryAbility", "draft": entry,
                         "anchor": trigger, "ok": ok})
            if not ok:
                conflicts.append({"item": skill["skill_id"],
                                  "why": f"trigger {trigger!r} 无 CharacterConfig.EntryAbility"})
        for kind in ("missing_abilities", "missing_modifiers", "ambiguous", "invalid_files"):
            values = official["sources"].get(kind) or []
            rows.append({"item": kind, "draft": values, "ok": not values})
            conflicts.extend({"item": kind, "why": str(value)} for value in values)
        return {"rows": rows, "conflicts": conflicts,
                "note": "conflict 是数据/覆盖审计；是否可定稿由 AbilityCompiler 逐技能判定"}
    return Node("crosscheck", fn, deps=("data_pull",), service="game_data")


def _compiler(official: Dict[str, Any]) -> AbilityCompiler:
    return AbilityCompiler(official["id"], official["skills"], official["sources"],
                           semantics=official.get("semantics") or {},
                           level=int(official["base_template"].get("level", 80)))


def draft_enemy_node(enemy_id: str, workdir: Path,
                     staging_root: Optional[Path] = None) -> Node:
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        official = inputs["data_pull"]
        converted = _compiler(official).compile_enemy()
        template = copy.deepcopy(official["base_template"])
        template["actions"] = converted["actions"]
        if converted["hooks"]:
            template["hooks"] = converted["hooks"]
        else:
            template.pop("hooks", None)
        if converted["summons"]:
            template["summons"] = converted["summons"]
        else:
            template.pop("summons", None)
        # 旧生成器的额外运行时区段若尚未由新编译器产出，不允许静默消失。
        if official["base_template"].get("summons") and not converted["summons"]:
            converted["unsupported"].append({
                "owner": "summons", "path": "summons", "node_type": "SummonCoverage",
                "reason": "旧模板召唤物尚未由通用编译器重建",
            })
        for section in ("capabilities", "custom_resources"):
            if template.get(section):
                converted["unsupported"].append({
                    "owner": section, "path": section, "node_type": "LegacySection",
                    "reason": f"旧模板 {section} 尚未由通用编译器重建",
                })
        converted["ok"] = converted["ok"] and not converted["unsupported"]
        template["notes"] = list(template.get("notes") or []) + [
            "机制由通用 AbilityCompiler 按上游节点生成；旧 per-skill 转换器仅作回归锚",
        ]
        err = "\n".join(
            f"{item.get('owner', '')}: {item['path']} {item['node_type']} — {item['reason']}"
            for item in converted["unsupported"])
        return {"ok": converted["ok"], "tpl": template, "err": err, "path": "",
                "unsupported": converted["unsupported"], "deferred": converted["deferred"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (compile_enemy_node(enemy_id, workdir, staging_root),)
        return (_human_queue_node(str(enemy_id), "Ability 节点/引用尚未完整支持", "draft"),)
    return Node("draft", fn, deps=("data_pull", "crosscheck"), service="game_data", shape=shape)


def _probe_build() -> Dict[str, Any]:
    return {"build": {
        "team": [{
            "actor_id": "annotator_hero", "name": "打标假人", "inline": True,
            "base_stats": {"hp": 1000000, "atk": 0, "def": 1000, "spd": 50,
                           "max_energy": 100},
            "actions": [{
                "action_id": "annotator_basic", "name": "打标普攻", "action_type": "basic",
                "target_type": "single", "damage_type": "physical",
                "scaling": [{"atk": 0}], "toughness_dmg": 0, "energy_gain": 0,
            }],
        }],
        "policy": {"name": "annotator_probe", "action_rules": [
            {"condition": "true", "action": "basic", "priority": 0}]},
    }}


def _probe_stage(enemy_id: str) -> Dict[str, Any]:
    return {"stage": {
        "enemies": [{"enemy_template": str(enemy_id), "level": 80}],
        "termination": {"mode": "fixed_av", "max_action_value": 500},
    }}


def _stage_candidate(enemy_id: str, tpl_text: str, workdir: Path) -> Path:
    directory = workdir / "enemies"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{enemy_id}_candidate.yaml"
    path.write_text(tpl_text, encoding="utf-8")
    return path


def _roots(workdir: Path) -> List[str]:
    return [str(workdir), str(library_dir()), str(sim_templates_dir())]


def compile_enemy_node(enemy_id: str, workdir: Path,
                       staging_root: Optional[Path] = None) -> Node:
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        previous = inputs["draft"]
        text = yaml.safe_dump(previous["tpl"], allow_unicode=True, sort_keys=False)
        path = _stage_candidate(str(enemy_id), text, workdir)
        try:
            from hsr_nous.sim.compile import compile_encounter
            compile_encounter(_probe_build(), _probe_stage(str(enemy_id)),
                              template_roots=_roots(workdir))
        except Exception as exc:  # noqa: BLE001 —— 闸门原样回报编译错误
            return {"ok": False, "tpl": previous["tpl"], "tpl_text": text,
                    "err": f"{type(exc).__name__}: {exc}", "path": str(path)}
        return {"ok": True, "tpl": previous["tpl"], "tpl_text": text,
                "err": "", "path": str(path)}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (smoke_enemy_node(enemy_id, staging_root),)
        return (_human_queue_node(str(enemy_id), "敌人候选编译失败", "compile"),)
    return Node("compile", fn, deps=("draft",), service="compile", kind="gate", shape=shape)


def smoke_enemy_node(enemy_id: str, staging_root: Optional[Path] = None) -> Node:
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        previous = inputs["compile"]
        try:
            from hsr_nous.sim import CombatEngine, MODE_EXPECTED
            from hsr_nous.sim.compile import compile_encounter
            workdir = Path(previous["path"]).parent.parent
            compiled = compile_encounter(_probe_build(), _probe_stage(str(enemy_id)),
                                         template_roots=_roots(workdir))
            engine = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, seed=1,
                                                initial_energy_ratio=0.0)
            state = engine.run()
            turns = state.snapshot()["turn_count"]
            if not turns:
                raise RuntimeError("冒烟零行动")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "tpl": previous["tpl"], "tpl_text": previous["tpl_text"],
                    "err": f"{type(exc).__name__}: {exc}", "path": previous["path"]}
        return {"ok": True, "tpl": previous["tpl"], "tpl_text": previous["tpl_text"],
                "err": "", "path": previous["path"], "turns": turns}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (golden_enemy_node(enemy_id, staging_root),)
        return (_human_queue_node(str(enemy_id), "敌人候选冒烟失败", "smoke"),)
    return Node("smoke", fn, deps=("compile",), service="compile", kind="gate", shape=shape)


def golden_enemy_node(enemy_id: str, staging_root: Optional[Path] = None) -> Node:
    """独立重算并与候选逐值对拍；这是结构 golden，不冒充真实客户端 trace."""
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        previous = inputs["smoke"]
        fresh = _compiler(inputs["data_pull"]).compile_enemy()
        mismatches = []
        if previous["tpl"].get("actions") != fresh["actions"]:
            mismatches.append("actions 与 AbilityCompiler 独立重算不一致")
        if (previous["tpl"].get("hooks") or []) != fresh["hooks"]:
            mismatches.append("hooks 与 AbilityCompiler 独立重算不一致")
        if (previous["tpl"].get("summons") or []) != fresh["summons"]:
            mismatches.append("summons 与 AbilityCompiler 独立重算不一致")
        if previous["tpl"].get("base_stats") != inputs["data_pull"]["base_template"].get("base_stats"):
            mismatches.append("base_stats 被转换层改动")
        err = "；".join(mismatches)
        return {"ok": not mismatches, "tpl": previous["tpl"], "tpl_text": previous["tpl_text"],
                "err": err, "path": previous["path"]}

    def shape(value: Dict[str, Any]):
        if value["ok"]:
            return (finalize_enemy_node(enemy_id, staging_root),)
        return (_human_queue_node(str(enemy_id), "敌人结构 golden 对拍失败", "golden"),)
    return Node("golden", fn, deps=("smoke", "data_pull"), service="compile",
                kind="gate", shape=shape)


def finalize_enemy_node(enemy_id: str, staging_root: Optional[Path] = None) -> Node:
    def fn(inputs: Dict[str, Any]) -> Dict[str, Any]:
        previous = inputs["golden"]
        official = inputs["data_pull"]
        root = Path(staging_root) if staging_root else annotator_dir() / "staging_root"
        staging = root / "enemies"
        notes = root / "notes"
        staging.mkdir(parents=True, exist_ok=True)
        notes.mkdir(parents=True, exist_ok=True)
        safe = str(official["name"]).replace("•", "_").replace("·", "_").replace("/", "_")
        path = staging / f"{enemy_id}_{safe}.yaml"
        path.write_text(previous["tpl_text"], encoding="utf-8")
        evidence = notes / f"{enemy_id}.json"
        evidence.write_text(json.dumps({
            "id": str(enemy_id), "mode": "mechanical_ability_compiler", "llm_calls": 0,
            "sources": official["sources"].get("source_files") or [],
            "golden": "结构对拍；真实客户端 golden 后置",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"staging": str(path), "notes": str(evidence), "review": "ready_for_human"}
    return Node("finalize", fn, deps=("golden", "data_pull"))
