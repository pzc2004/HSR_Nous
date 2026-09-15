"""批量打标驱动（ops/annotator/batch）——花名册/锚跳过/目标清单.

run_batch 的 LLM/闸链行为由 test_ops_annotator_dag.py 单角色端到端覆盖；
此处只钉批调度面（清单派生与锚纪律）。
"""

from __future__ import annotations

from hsr_nous.ops.annotator.batch import anchor_ids, collect_targets, roster


def test_anchor_ids_real_fixtures():
    """真实 fixtures 派生锚集（与目录内容同文件就近维护——加锚=放新 fixture）。"""
    assert anchor_ids() == frozenset({
        "1001", "1002", "1003", "1004", "1005", "1006", "1008", "1009", "1013", "1014", "1015", "1101", "1102", "1103", "1104", "1105", "1106", "1107", "1108", "1109", "1110", "1111", "1201", "1202", "1203", "1205", "1206", "1207", "1208", "1209", "1210", "1211", "1212", "1213", "1214", "1215", "1217", "1218", "1220", "1221", "1222", "1223", "1224", "1225", "1112", "1204", "1301", "1302", "1303", "1304", "1305", "1306", "1307", "1308", "1309", "1312", "1314", "1315", "1317", "1321", "1501", "1502", "1504", "1505", "1506", "1507", "1508", "1509", "1510", "1310", "1313", "1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1409", "1410", "1412",
        "1413", "1414", "1415",
        "8001", "8002", "8003", "8004", "8005", "8006", "8007", "8008", "8009", "8010",
        "999901", "999902", "999903", "999904", "999905", "999906", "999907", "999908"})


def test_roster_all_playable_with_skills():
    """花名册：全员有技能清单、cid 升序、规模>=90（版本追踪——新角色入库自动入册）。"""
    r = roster()
    assert len(r) >= 90 and r == sorted(r) and "1404" in r


def test_collect_targets_skips_anchors_by_default():
    t = collect_targets()
    assert not (set(t) & set(anchor_ids())), "默认跳锚（人工全机制版已在库）"
    assert "1224" not in t and "1225" not in t, "1224/1225 皆已转锚跳过（1225 随 B38 超击破体系收官入库）"


def test_collect_targets_include_anchors_opt_in():
    t = collect_targets(include_anchors=True)
    assert "1404" in t, "--include-anchors：锚重打（对拍收益）放行"


def test_collect_targets_explicit_ids():
    assert collect_targets(ids=["1404", "1202"]) == ["1404", "1202"]


def test_live_workers_hot_config(tmp_path, monkeypatch):
    """外层并行热更：live config batch_workers 键现场读（升档补位/降档排干）——
    文件缺失/非法值静默回落命令行缺省。"""
    import json

    from hsr_nous.ops.annotator import batch as batch_mod

    home = tmp_path / "home"
    cfg_dir = home / ".config" / "hsr_nous"
    cfg_dir.mkdir(parents=True)
    monkeypatch.setattr(batch_mod.Path, "home", classmethod(lambda cls: home))
    assert batch_mod._live_workers(2) == 2, "无文件回落命令行值"
    (cfg_dir / "annotator_live_config.json").write_text(
        json.dumps({"batch_workers": 6}), encoding="utf-8")
    assert batch_mod._live_workers(2) == 6, "live 键覆盖命令行值（升档）"
    (cfg_dir / "annotator_live_config.json").write_text(
        json.dumps({"batch_workers": 1}), encoding="utf-8")
    assert batch_mod._live_workers(4) == 1, "降档同步"
    (cfg_dir / "annotator_live_config.json").write_text(
        json.dumps({"batch_workers": -3}), encoding="utf-8")
    assert batch_mod._live_workers(4) == 1, "非法值钳 1"
    (cfg_dir / "annotator_live_config.json").write_text("{坏 json", encoding="utf-8")
    assert batch_mod._live_workers(4) == 4, "坏文件静默回落"
