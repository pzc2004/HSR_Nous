"""期数编成查询层：对调用方屏蔽 Hakushin / buhflipexplode 双源差异.

- buhflipexplode（buh）：期数时间轴 + 紊流/天气 buff + 敌方编成与 HP/攻击系数，
  覆盖 aa（异相仲裁）/ fh（混沌回忆）/ pf（虚构叙事）/ as（末日幻影）四种玩法；
- Hakushin：每期每层详情（紊流 buff 文本、推荐属性、等级、怪物列表），无时间轴。

两源期号口径不同、映射关系弱（buh 用版本期号如 "4.3.1"，Hakushin 用自增 id 如
"1031"），因此 list_stages 把两源分别列出（各源各表），不强行按期号 join。

怪物本体查询已迁 enemies 域（`pipeline/enemies/loader.py`——P3 切源：tbgd 五表
为数值权威，theBowja 冻结保留回退）；本模块只管期数/编成。
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.pipeline import paths as _paths
from hsr_nous.pipeline.redline import _flatten_strs, parse_version_time

# 对外玩法名 -> buh versions 文件前缀
_MODE_TO_BUH = {"moc": "fh", "pf": "pf", "as": "as", "aa": "aa"}
# 对外玩法名 -> Hakushin 期数列表/详情目录名（aa 无 Hakushin 源）
_MODE_TO_HAKUSHIN = {"moc": "maze", "pf": "maze_extra", "as": "maze_boss"}

# 异相仲裁敌人等级假设：未经实测确认，结算条目统一附 _level_assumption 标记
_AA_LEVEL_ASSUMPTION = 95


def _resolve_stages_dir(stages_dir: Optional[str]) -> Path:
    return Path(stages_dir) if stages_dir is not None else _paths.stages_dir()


@lru_cache(maxsize=None)
def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _check_mode(mode: str) -> None:
    if mode not in _MODE_TO_BUH:
        raise ValueError(f"未知玩法: {mode!r}（可选: {list_modes()}）")


def _load_buh_versions(mode: str, stages_dir: Path) -> Dict[str, Any]:
    """加载 buh versions 并摊平为 {期号: 期数据}（fh 为 list of sections，逐节合并）."""
    path = stages_dir / "buhflipexplode" / f"{_MODE_TO_BUH[mode]}-versions.json"
    data = _load_json(str(path))
    if isinstance(data, dict):
        return data
    merged: Dict[str, Any] = {}
    for section in data:
        versions = section.get("versions")
        if isinstance(versions, dict):
            merged.update(versions)
    return merged


def _buff_text(buffs_table: Dict[str, Any], buff_id: str) -> Optional[str]:
    """查 buff 文本：去掉小数后缀（"41000002.1" -> "41000002"），list 值拼接为文本."""
    value = buffs_table.get(buff_id.split(".")[0])
    if isinstance(value, list):
        return "\n".join(str(v) for v in value)
    return value if isinstance(value, str) else None


def list_modes() -> List[str]:
    """支持的玩法列表：moc 混沌回忆 / pf 虚构叙事 / as 末日幻影 / aa 异相仲裁."""
    return ["moc", "pf", "as", "aa"]


def list_stages(mode: str, *, stages_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """列出某玩法的期数（期号 / 名称 / 起止时间），buh 与 Hakushin 两源分别列出.

    时间轴以 buh versions 为准（begin/end 为 date；Hakushin 时间为空，原样给出
    非空字符串或 None）。返回条目含 source 字段："buhflipexplode" / "hakushin"。
    """
    _check_mode(mode)
    root = _resolve_stages_dir(stages_dir)
    stages: List[Dict[str, Any]] = []

    buh_path = root / "buhflipexplode" / f"{_MODE_TO_BUH[mode]}-versions.json"
    if buh_path.exists():
        for key, entry in _load_buh_versions(mode, root).items():
            begin, end = parse_version_time(entry.get("versionTime", ""))
            stages.append({
                "source": "buhflipexplode",
                "id": key,
                "name": entry.get("versionName", ""),
                "begin": begin,
                "end": end,
            })

    hak_mode = _MODE_TO_HAKUSHIN.get(mode)
    if hak_mode:
        hak_path = root / "hakushin" / f"{hak_mode}.json"
        if hak_path.exists():
            for period_id, entry in _load_json(str(hak_path)).items():
                stages.append({
                    "source": "hakushin",
                    "id": period_id,
                    "name": entry.get("en", ""),
                    "begin": entry.get("live_begin") or entry.get("begin") or None,
                    "end": entry.get("live_end") or entry.get("end") or None,
                })
    return stages


def get_stage_hakushin(
    mode: str, period_id: str, *, stages_dir: Optional[str] = None
) -> Dict[str, Any]:
    """从 Hakushin 详情组装某期关卡结构，详情文件缺失抛 FileNotFoundError.

    返回 {period_id, mode, source, floors}；每层：
    {id, name, group_name, desc（紊流 buff 文本）, param, countdown,
     damage_type: [side1 推荐属性, side2 推荐属性],
     sides: [[{level, elite_group, hard_level_group, monster_list}, ...], [...]]}
    （sides[0] 对应 event_id_list1，sides[1] 对应 event_id_list2）
    """
    _check_mode(mode)
    hak_mode = _MODE_TO_HAKUSHIN.get(mode)
    if hak_mode is None:
        raise ValueError(f"玩法 {mode!r} 无 Hakushin 数据源")
    path = (
        _resolve_stages_dir(stages_dir) / "hakushin" / "details" / hak_mode / f"{period_id}.json"
    )
    floors_raw = _load_json(str(path))
    # Hakushin 详情有两种外层形态：maze 直接是 floor 数组，maze_extra/maze_boss
    # 则以 {"level": floor 数组} 包装；统一归一为 floor 数组再映射。
    if isinstance(floors_raw, dict):
        floors_raw = floors_raw.get("level") or []

    floors: List[Dict[str, Any]] = []
    for floor in floors_raw:
        sides: List[List[Dict[str, Any]]] = []
        for key in ("event_id_list1", "event_id_list2"):
            sides.append([
                {
                    "level": event.get("level"),
                    "elite_group": event.get("elite_group"),
                    "hard_level_group": event.get("hard_level_group"),
                    "monster_list": event.get("monster_list"),
                }
                for event in floor.get(key, [])
            ])
        floors.append({
            "id": floor.get("id"),
            "name": floor.get("name"),
            "group_name": floor.get("group_name"),
            "desc": floor.get("desc"),
            "param": floor.get("param"),
            "countdown": floor.get("countdown"),
            "damage_type": [floor.get("damage_type1"), floor.get("damage_type2")],
            "sides": sides,
        })
    return {
        "period_id": str(period_id),
        "mode": mode,
        "source": "hakushin",
        "floors": floors,
    }


def list_hakushin_monster_ids(mode: str, *, stages_dir: Optional[str] = None) -> List[str]:
    """列出某玩法全部 Hakushin 期数引用的敌人实例 ID（去重、排序）.

    与 MonsterTemplateConfig 的模板花名册不同：关卡可引用同模板的多阶段/多变体
    MonsterID。生成 stage 前必须让敌人模板覆盖本集合，否则引用侧无法编译。
    """
    monster_ids: set[str] = set()
    for period in list_stages(mode, stages_dir=stages_dir):
        if period["source"] != "hakushin":
            continue
        data = get_stage_hakushin(mode, period["id"], stages_dir=stages_dir)
        for floor in data["floors"]:
            for side in floor["sides"]:
                for event in side:
                    for monster in event.get("monster_list") or []:
                        monster_ids.update(str(v) for v in monster.values() if v)
    return sorted(monster_ids)


def get_stage_buh(
    mode: str, version_key: str, *, stages_dir: Optional[str] = None
) -> Dict[str, Any]:
    """从 buh versions 组装某期关卡：名称 / 时间 / buff / debuff / 敌方编成.

    sides 原样透传 versionEnemies.sides（sideElementMult / sideHPMult / waves）；
    buff/debuff 文本查 buffs.json，期号不存在抛 KeyError。
    """
    _check_mode(mode)
    root = _resolve_stages_dir(stages_dir)
    versions = _load_buh_versions(mode, root)
    if version_key not in versions:
        raise KeyError(f"{mode} 无期数 {version_key!r}（可选: {sorted(versions)}）")
    entry = versions[version_key]

    buffs_path = root / "buhflipexplode" / "buffs.json"
    buffs_table = _load_json(str(buffs_path)) if buffs_path.exists() else {}

    def _resolve_buffs(ids_node: Any) -> List[Dict[str, Any]]:
        seen: set = set()
        out: List[Dict[str, Any]] = []
        for raw_id in _flatten_strs(ids_node):
            buff_id = raw_id.split(".")[0]
            if buff_id in seen:
                continue
            seen.add(buff_id)
            out.append({"id": buff_id, "text": _buff_text(buffs_table, raw_id)})
        return out

    return {
        "version_key": version_key,
        "mode": mode,
        "source": "buhflipexplode",
        "versionName": entry.get("versionName"),
        "versionTime": entry.get("versionTime"),
        "buffs": _resolve_buffs(entry.get("versionBuffIDs")),
        "debuffs": _resolve_buffs(entry.get("versionDebuffIDs")),
        "sides": entry.get("versionEnemies", {}).get("sides", []),
    }


def compute_buh_enemies(
    version_key: str, *, mode: str = "aa", stages_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """对指定 buh 期数（默认异相仲裁 aa）逐敌结算数值.

    - HP = round(baseHP × sideHPMult)（baseHP 为 enemies.json 中的系数，
      sideHPMult 为该侧 HP 系数）；
    - speed = baseSPD，toughness 原样透传；
    - level 固定按 95 假设——异相仲裁敌人等级未经实测确认，
      每条结算附 ``_level_assumption: True`` 标记；
    - attack / defence 不猜测，输出 None：按 docs/mechanics/01_base_stats.md
      的等级公式待实现。

    红线过滤后引用应有本体；enemies.json 中缺失本体的 id 跳过不计。
    """
    _check_mode(mode)
    root = _resolve_stages_dir(stages_dir)
    versions = _load_buh_versions(mode, root)
    if version_key not in versions:
        raise KeyError(f"{mode} 无期数 {version_key!r}（可选: {sorted(versions)}）")
    entry = versions[version_key]
    enemies_table = _load_json(str(root / "buhflipexplode" / "enemies.json"))

    result: List[Dict[str, Any]] = []
    for side_idx, side in enumerate(entry.get("versionEnemies", {}).get("sides", [])):
        hp_mult = side.get("sideHPMult", 0)
        for wave_idx, wave in enumerate(side.get("waves", [])):
            for foe in wave.get("enemies", []):
                foe_id = foe.get("id")
                base = enemies_table.get(foe_id)
                if base is None:
                    continue
                result.append({
                    "id": foe_id,
                    "name": base.get("name"),
                    "side": side_idx,
                    "wave": wave_idx,
                    "count": foe.get("count", 1),
                    "phase": foe.get("phase"),
                    "hp": round(base.get("baseHP", 0) * hp_mult),
                    "speed": base.get("baseSPD"),
                    "toughness": base.get("toughness"),
                    "level": _AA_LEVEL_ASSUMPTION,
                    "_level_assumption": True,
                    "attack": None,
                    "defence": None,
                })
    return result


