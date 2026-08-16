"""query-game-data skill CLI.

纯路由层: argv → loader API → 附加 signature_light_cone_id → JSON.

数据流:
    query → _resolve(by_id / by_name) → 业务函数 (调 loader 组装)
    → _attach_bilingual / _attach_signature_lc → json.dumps

详见 .agents/skills/query-game-data/SKILL.md.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from hsr_nous.pipeline.loader import (  # noqa: E402
    get_character,
    get_character_by_name,
    get_character_full,
    get_enemy,
    get_enemy_by_name,
    get_light_cone,
    get_light_cone_by_name,
    get_light_cone_ranks,
    get_relic_set,
    get_relic_set_by_name,
    list_characters,
    list_enemies,
    list_light_cones,
    list_relic_sets,
    load_signature_light_cones,
)


# ---------------------------------------------------------------------------
# 通用 helpers
# ---------------------------------------------------------------------------
def _resolve(
    query: str, get_by_id, get_by_name, *, lang_for_id: str = "cn"
) -> Optional[Dict[str, Any]]:
    """优先按 ID 查 lang_for_id, 否则按 CN 名, 再按 EN 名.

    lang_for_id: 传给 get_by_id 的 lang 参数 (例如 "cn" / "en" / None).
                 敌人数据不分语言, 传 None. 此时 by_name 也不传 lang.
    """
    if lang_for_id is None:
        if query.isdigit():
            item = get_by_id(query)
            if item is not None:
                return item
        return get_by_name(query)  # 敌人不分语言, 不带 lang
    if query.isdigit():
        item = get_by_id(query, lang=lang_for_id)
        if item is not None:
            return item
    return get_by_name(query, lang="cn") or get_by_name(query, lang="en")


def _attach_bilingual(item: Dict, get_by_id) -> Dict:
    """给 item 副本附加 name_cn / name_en."""
    out = dict(item)
    eid = item.get("id", "")
    if not eid:
        return out
    cn = get_by_id(eid, lang="cn")
    en = get_by_id(eid, lang="en")
    if cn:
        out["name_cn"] = cn.get("name", "")
    if en:
        out["name_en"] = en.get("name", "")
    return out


def _not_found(query: str, list_kind: str) -> Dict:
    return {"_error": f"{list_kind[:-1]} not found: {query}",
            "_hint": f"try `list {list_kind}` to see all"}


def _attach_signature_lc(char_id: str, full: Dict) -> None:
    """从 loader 加载 sig_lc 映射, 附加 sig_lc_id. 5★ 无映射时打 warning."""
    sig_map = load_signature_light_cones()
    if char_id in sig_map:
        full["signature_light_cone_id"] = sig_map[char_id]["sig_lc_id"]
        return
    full["signature_light_cone_id"] = None
    name_en = full.get("name_en", "")
    if not name_en.startswith("Trailblazer") and str(full.get("rarity", 0)) == "5":
        full["_warning"] = (
            f"5★ character {name_en or char_id} has no signature LC mapping. "
            "可能是本地 StarRailRes 缺数据或专光映射表过时。"
        )


# ---------------------------------------------------------------------------
# 角色
# ---------------------------------------------------------------------------
def query_character(query: str) -> Dict:
    char = _resolve(query, get_character, get_character_by_name)
    if char is None:
        return _not_found(query, "characters")
    full = get_character_full(char["id"])
    if full is None:
        return {"_error": f"character exists but get_character_full failed: {char['id']}"}
    _attach_bilingual(full, get_character)
    _attach_signature_lc(char["id"], full)
    return full


# ---------------------------------------------------------------------------
# 光锥
# ---------------------------------------------------------------------------
def query_light_cone(query: str) -> Dict:
    lc = _resolve(query, get_light_cone, get_light_cone_by_name)
    if lc is None:
        return _not_found(query, "light_cones")
    result = _attach_bilingual(lc, get_light_cone)
    ranks = get_light_cone_ranks(lc["id"], lang="cn")
    if ranks:
        result["skill_name"] = ranks.get("skill")
        # ranks.desc 是机制描述; light_cones.json 的 desc 是故事/世界观叙述, 用 ranks 覆盖
        ranks_desc = ranks.get("desc")
        if ranks_desc:
            result["desc"] = ranks_desc
        result["params_by_superimposition"] = ranks.get("params")
        result["properties_by_superimposition"] = ranks.get("properties")
    return result


# ---------------------------------------------------------------------------
# 遗器套装
# ---------------------------------------------------------------------------
def query_relic(query: str) -> Dict:
    s = _resolve(query, get_relic_set, get_relic_set_by_name)
    if s is None:
        return _not_found(query, "relic_sets")
    result = _attach_bilingual(s, get_relic_set)
    desc = s.get("desc", [])
    if len(desc) >= 1:
        result["set_2pc"] = desc[0]
    if len(desc) >= 2:
        result["set_4pc"] = desc[1]
    return result


# ---------------------------------------------------------------------------
# 敌人
# ---------------------------------------------------------------------------
def query_enemy(query: str) -> Dict:
    return _resolve(query, get_enemy, get_enemy_by_name, lang_for_id=None) or _not_found(query, "enemies")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
def list_entities(kind: str) -> List[Dict]:
    if kind == "characters":
        return [{"id": cid, "name_cn": n} for cid, n in list_characters(lang="cn")]
    if kind == "light_cones":
        return [{"id": lid, "name_cn": n} for lid, n in list_light_cones(lang="cn")]
    if kind == "relic_sets":
        return [{"id": sid, "name_cn": n} for sid, n in list_relic_sets(lang="cn")]
    if kind == "enemies":
        return [{"id": eid, "name": n} for eid, n in list_enemies()]
    return [{"_error": f"unknown list kind: {kind}",
             "_supported": ["characters", "light_cones", "relic_sets", "enemies"]}]


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    entity_type = sys.argv[1]
    handlers = {
        "character": query_character,
        "light_cone": query_light_cone,
        "relic": query_relic,
        "enemy": query_enemy,
    }

    if entity_type == "list":
        if len(sys.argv) < 3:
            print({"_error": "list needs subkind: characters | light_cones | relic_sets | enemies"},
                  file=sys.stderr)
            sys.exit(1)
        result = list_entities(sys.argv[2])
    elif entity_type in handlers:
        if len(sys.argv) < 3:
            print({"_error": f"{entity_type} needs query (id or name)"}, file=sys.stderr)
            sys.exit(1)
        result = handlers[entity_type](sys.argv[2])
    else:
        print({"_error": f"unknown entity_type: {entity_type}",
               "_supported": list(handlers) + ["list"]}, file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
