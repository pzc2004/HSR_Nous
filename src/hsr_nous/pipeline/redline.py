"""红线过滤：只保留已正式上线版本的数据.

纯函数模块，无 I/O。供 update_stages 在落盘前过滤未发布的期数与实体引用，
也可供 update 对版本追踪类数据源做版本对齐校验（warn-only）。
"""

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

_DATE_FMT = "%d/%m/%Y"


def parse_version_time(s: str) -> Tuple[Optional[date], Optional[date]]:
    """解析 "dd/mm/yyyy - dd/mm/yyyy" 格式的期数起止时间.

    两端都必须是合法日期才返回 (start, end)；占位符（"xx/xx/20xx - xx/xx/20xx"）、
    异常输入、或仅一端可解析（如 "26/04/2023 - PRESENT"）一律返回 (None, None)。
    """
    if not isinstance(s, str):
        return None, None
    parts = [p.strip() for p in s.split("-")]
    if len(parts) != 2:
        return None, None
    parsed: List[date] = []
    for part in parts:
        try:
            parsed.append(datetime.strptime(part, _DATE_FMT).date())
        except ValueError:
            return None, None
    return parsed[0], parsed[1]


def filter_phases(versions: Dict[str, Any], today: date) -> Tuple[Dict[str, Any], List[str]]:
    """按期数时间过滤 versions（期号 -> 期数据），剔除未正式上线的期.

    移除规则（红线：无法确认已上线的期一律按未发布处理）:

    1. 开始日期 > today 的未来期；
    2. 无完整可解析日期的期——包括名称为空且无日期的空占位期，
       也包括有名字但排期未定（"xx/xx/20xx"）或时间格式残缺的未发布期。

    返回 (保留的 versions, 移除的期号列表)。
    """
    kept: Dict[str, Any] = {}
    removed: List[str] = []
    for key, entry in versions.items():
        start, _end = parse_version_time(entry.get("versionTime", ""))
        if start is None or start > today:
            removed.append(key)
        else:
            kept[key] = entry
    return kept, removed


def _flatten_strs(node: Any) -> List[str]:
    """把（可能嵌套 list 的）id 容器展平成字符串列表."""
    out: List[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_flatten_strs(item))
    return out


def collect_referenced_ids(versions_data: Any) -> Tuple[Set[str], Set[str]]:
    """从（过滤后的）versions 数据递归收集引用的 enemy id 与 buff id.

    - enemy id：waves 子树内 dict 的 "id" 键，原样保留
      （"31100.1" 这类带小数后缀的 id 在 enemies.json 中是真实键，不去后缀）；
    - buff id：versionBuffIDs / versionDebuffIDs 的值（debuff 可能嵌套 list），
      去掉小数后缀（如 "41000002.1" -> "41000002"，buffs.json 只存主键）。
    """
    enemy_ids: Set[str] = set()
    buff_ids: Set[str] = set()

    def _walk(node: Any, in_waves: bool) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("versionBuffIDs", "versionDebuffIDs"):
                    for bid in _flatten_strs(value):
                        buff_ids.add(bid.split(".")[0])
                elif key == "id" and in_waves and isinstance(value, str):
                    enemy_ids.add(value)
                elif key == "waves":
                    _walk(value, True)
                else:
                    _walk(value, in_waves)
        elif isinstance(node, list):
            for item in node:
                _walk(item, in_waves)

    _walk(versions_data, False)
    return enemy_ids, buff_ids


def filter_entities(entities: Dict[str, Any], keep_ids: Set[str]) -> Tuple[Dict[str, Any], int]:
    """按 id 白名单过滤 enemies/buffs 字典，返回 (保留的字典, 移除条数)."""
    kept = {key: value for key, value in entities.items() if key in keep_ids}
    return kept, len(entities) - len(kept)


def check_release_alignment(ids: Iterable[str], live_ids: Iterable[str]) -> List[str]:
    """返回不在已上线花名册中的 id（疑似未发布内容，仅告警用）."""
    live = {str(i) for i in live_ids}
    return sorted({str(i) for i in ids} - live)
