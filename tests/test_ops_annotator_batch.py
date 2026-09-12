"""批量打标驱动（ops/annotator/batch）——花名册/锚跳过/目标清单.

run_batch 的 LLM/闸链行为由 test_ops_annotator_dag.py 单角色端到端覆盖；
此处只钉批调度面（清单派生与锚纪律）。
"""

from __future__ import annotations

from hsr_nous.ops.annotator.batch import anchor_ids, collect_targets, roster


def test_anchor_ids_real_fixtures():
    """真实 fixtures 派生锚集（与目录内容同文件就近维护——加锚=放新 fixture）。"""
    assert anchor_ids() == frozenset({
        "1001", "1002", "1003", "1004", "1005", "1006", "1008", "1009", "1013", "1014", "1015", "1101", "1102", "1103", "1104", "1105", "1106", "1107", "1112", "1204", "1303", "1507", "1310", "1313", "1403", "1404", "1407", "1408", "1409", "1412",
        "1413", "1414", "1415",
        "999901", "999902", "999903", "999904", "999905", "999906", "999907", "999908"})


def test_roster_all_playable_with_skills():
    """花名册：全员有技能清单、cid 升序、规模>=90（版本追踪——新角色入库自动入册）。"""
    r = roster()
    assert len(r) >= 90 and r == sorted(r) and "1404" in r


def test_collect_targets_skips_anchors_by_default():
    t = collect_targets()
    assert not (set(t) & set(anchor_ids())), "默认跳锚（人工全机制版已在库）"
    assert "1107" not in t and "1108" in t, "1107 已转锚跳过；1108 仍在批"


def test_collect_targets_include_anchors_opt_in():
    t = collect_targets(include_anchors=True)
    assert "1404" in t, "--include-anchors：锚重打（对拍收益）放行"


def test_collect_targets_explicit_ids():
    assert collect_targets(ids=["1404", "1202"]) == ["1404", "1202"]
