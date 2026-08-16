"""关卡编成（深渊）查询层：对调用方屏蔽 Hakushin / buhflipexplode 双源差异.

- buhflipexplode（buh）：期数时间轴 + 紊流/天气 buff + 敌方编成与 HP/攻击系数，
  覆盖 aa（异相仲裁）/ fh（混沌回忆）/ pf（虚构叙事）/ as（末日幻影）四种玩法；
- Hakushin：每期每层详情（紊流 buff 文本、推荐属性、等级、怪物列表），无时间轴。

两源期号口径不同、映射关系弱（buh 用版本期号如 "4.3.1"，Hakushin 用自增 id 如
"1031"），因此 list_stages 把两源分别列出（各源各表），不强行按期号 join。

怪物本体查询（get_enemy_detail）也是双源：基础数值主源 Hakushin monstervalue，
技能/抗性明细回退 theBowja 遗留快照（断更于游戏 3.2，返回带 _stale 标记）。
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from hsr_nous.pipeline.redline import parse_version_time

_DEFAULT_STAGES_DIR = Path(__file__).parent.parent.parent.parent / "data" / "stages"
_DEFAULT_ENEMIES_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "enemies" / "enemies.json"
)
_DEFAULT_MONSTERVALUE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "data" / "stages" / "hakushin" / "monstervalue.json"
)
_DEFAULT_FANDOM_ENEMY_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "fandom_enemy_data.json"
)

# 对外玩法名 -> buh versions 文件前缀
_MODE_TO_BUH = {"moc": "fh", "pf": "pf", "as": "as", "aa": "aa"}
# 对外玩法名 -> Hakushin 期数列表/详情目录名（aa 无 Hakushin 源）
_MODE_TO_HAKUSHIN = {"moc": "maze", "pf": "maze_extra", "as": "maze_boss"}

# 异相仲裁敌人等级假设：未经实测确认，结算条目统一附 _level_assumption 标记
_AA_LEVEL_ASSUMPTION = 95


def _resolve_stages_dir(stages_dir: Optional[str]) -> Path:
    return Path(stages_dir) if stages_dir is not None else _DEFAULT_STAGES_DIR


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


def _flatten_ids(node: Any) -> List[str]:
    """把（可能嵌套 list 的）buff id 容器展平成字符串列表."""
    out: List[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_flatten_ids(item))
    return out


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
        for raw_id in _flatten_ids(ids_node):
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


def _lookup_monstervalue(table: Dict[str, Any], enemy_id: str) -> Optional[Dict[str, Any]]:
    """在 monstervalue 里查怪物：顶层命中返回原条目；否则在 child 修正系数数组里找
    子实体 id，命中返回 父 base 值 + 子修正系数 的合并视图（含 parent_id）."""
    top = table.get(enemy_id)
    if isinstance(top, dict):
        return dict(top)
    for parent_id, entry in table.items():
        if not isinstance(entry, dict):
            continue
        for child in entry.get("child", []):
            if str(child.get("Id")) == enemy_id:
                merged = {k: v for k, v in entry.items() if k != "child"}
                merged.update(child)
                merged["parent_id"] = parent_id
                return merged
    return None


def get_enemy_detail(
    enemy_id: str,
    *,
    enemies_path: Optional[str] = None,
    monstervalue_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """按 ID 查询怪物本体，双源路由.

    - 主源 Hakushin ``monstervalue.json``（跟随 live 版本更新）：AttackBase /
      HPBase / SpeedBase / StanceBase / StatusResistanceBase 等 base 数值，
      子实体命中时附 EliteGroup / HPModifyRatio / HardLevelGroup 等修正系数，
      返回标 ``_source: "hakushin"``；
    - 回退 theBowja ``enemies.json`` 遗留快照（断更于游戏 3.2，上游 DimBreath
      2024-10 被 DMCA）：Id / ElementalResistance / SkillList 等技能与抗性表，
      返回标 ``_source: "bowja_legacy"`` + ``_stale: True``。

    两源均无该 id 返回 None。
    """
    key = str(enemy_id)
    mv_path = (
        Path(monstervalue_path) if monstervalue_path is not None
        else _DEFAULT_MONSTERVALUE_PATH
    )
    if mv_path.exists():
        detail = _lookup_monstervalue(_load_json(str(mv_path)), key)
        if detail is not None:
            return {"_source": "hakushin", **detail}

    bowja_path = (
        Path(enemies_path) if enemies_path is not None else _DEFAULT_ENEMIES_PATH
    )
    if bowja_path.exists():
        legacy = _load_json(str(bowja_path)).get(key)
        if legacy is not None:
            return {"_source": "bowja_legacy", "_stale": True, **legacy}
    return None


def get_enemy_mechanics(
    page_title: str, *, fandom_enemy_path: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """按 Fandom 页面名查询敌人机制数据（来源 data/fandom_enemy_data.json）.

    数据文件由 pipeline/extract_fandom_enemies.py 生成——文件不存在时返回 None，
    需先跑提取脚本（如 --limit 5 验证后全量）。
    """
    path = (
        Path(fandom_enemy_path) if fandom_enemy_path is not None
        else _DEFAULT_FANDOM_ENEMY_PATH
    )
    if not path.exists():
        return None
    return _load_json(str(path)).get(page_title)
