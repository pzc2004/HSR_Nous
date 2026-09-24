"""装备打标 DAG（光锥/遗器分支）——FakeRunner 罐头 LLM 全链 + 闸打回 + batch kind 分流.

全链：run_light_cone(20000 锋镝)/run_relic(101 云无留迹的过客) 到 finalize（staging 落盘
形状断言：数值区=生成器草稿原样 + hooks 机械合并）；闸打回：坏 hooks（词表外 effect_type）
与越权输出（draft 重写数值区）走内环 revise；golden 对拍单测（白值/叠影行/2pc 属性/hooks 空缺）；
batch：collect_targets kind 分流 + 花名册数量现场算（不写死）。
真实数据走 pipeline（光锥 20000/遗器 101 的 desc/params/白值锚——与生成器草稿同源）。
"""

from __future__ import annotations

import pytest
import yaml

from hsr_nous.ops.annotator import FakeRunner, run_light_cone, run_relic
from hsr_nous.ops.annotator.batch import (
    anchor_ids,
    collect_targets,
    roster_light_cones,
    roster_relics,
)
from hsr_nous.ops.annotator.equipment_nodes import (
    ROOT,
    _golden_mismatches_lc,
    _golden_mismatches_relic,
    _merge_lc_hooks,
    _merge_relic_hooks,
    data_pull_lc_node,
    data_pull_relic_node,
)
from tests._data_env import data_available, data_skip_reason

_need_data = pytest.mark.skipif(not data_available(), reason=data_skip_reason())

# ---------------------------------------------------------------------------
# 罐头件（锋镝 20000：开战暴击 buff，$self.param_1=叠影暴击列、param_2=持续 3 回合；
#           过客 101：2pc 治疗量已收 stat_effects，4pc 开战 +1 战技点）
# ---------------------------------------------------------------------------

_LC_HOOKS_OK = """hooks:
  - event: "on_battle_start"
    effects:
      - effect_type: "apply_modifier"
        modifier:
          modifier_id: "LC_20000_CRIT"
          name: "锋镝暴击"
          modifier_type: "buff"
          duration: 3
          dispellable: false
          stack_mode: "replace"
          stat_effects:
            crit_rate: "$self.param_1"
"""

_LC_HOOKS_BAD_EFFECT = """hooks:
  - event: "on_battle_start"
    effects:
      - effect_type: "brew_coffee"
        modifier: {}
"""

_LC_HOOKS_OVERREACH = """base_stats:
  hp: 1
hooks: []
"""

_RELIC_HOOKS_OK = """set_4pc:
  hooks:
    - event: "on_battle_start"
      effects:
        - effect_type: "gain_skill_point"
          amount: 1
"""

_RELIC_HOOKS_BAD_EFFECT = """set_4pc:
  hooks:
    - event: "on_battle_start"
      effects:
        - effect_type: "brew_coffee"
"""

_RELIC_HOOKS_OVERREACH = """set_2pc:
  stat_effects:
    atk_pct: 0.5
  hooks: []
"""

_NOTES = "# 证据笔记\n- 锋镝：开战暴击率提高 #1[i]%（官方文本，S1..S5 全档照抄）\n"


def _fake(v_draft: str, v_revise: str) -> FakeRunner:
    return FakeRunner([
        ("的 hooks 块被闸门打回", v_revise),   # revise 提示词命中词在前（draft 提示词
                                               # 含"必被闸门打回"——键必须带前缀消歧）
        ("DSL hooks 块", v_draft),             # draft
        ("输出证据笔记", _NOTES),               # evidence
    ])


def _fake_search(query, max_results):
    return [{"title": f"{query} 结果", "url": f"https://example.com/{abs(hash(query)) % 1000}",
             "snippet": "社区摘要"}]


def _fake_fetch(url, cap):
    return f"正文:{url}"


# ---------------------------------------------------------------------------
# 光锥全链
# ---------------------------------------------------------------------------

@_need_data
def test_lc_full_chain_finalize(tmp_path):
    """锋镝 20000 全链到 finalize：staging 落盘=草稿数值区原样 + hooks 机械合并."""
    llm = _fake(_LC_HOOKS_OK, _LC_HOOKS_OK)
    out = run_light_cone("20000", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out
    assert "golden1" in out and out["golden1"]["ok"], "金样闸过（数值区对数据锚零 mismatch）"
    tpl = tmp_path / "staging" / "light_cones" / "20000_锋镝.yaml"
    assert tpl.is_file(), "staging 落盘 <staging_root>/light_cones/<id>_<名>.yaml（与模板根同构）"
    doc = yaml.safe_load(tpl.read_text(encoding="utf-8"))
    official = data_pull_lc_node("20000").fn({})
    expect_base = yaml.safe_load(official["draft_text"])["base_stats"]
    assert doc["base_stats"] == expect_base, (
        "白值=生成器草稿原样（机械合并——LLM 没碰数值区；取值现场读防生成器迭代漂移）")
    assert doc["lookup_tables"]["param_1"] == [0.12, 0.15, 0.18, 0.21, 0.24], "叠影表原样"
    assert doc["variable_bindings"], "绑定层原样"
    assert doc["hooks"][0]["effects"][0]["modifier"]["modifier_id"] == "LC_20000_CRIT", (
        "LLM hooks 块并入")
    assert (tmp_path / "staging" / "notes" / "20000.md").is_file(), "证据笔记随候选包"
    assert (tmp_path / "runs" / "light_cones" / "20000").is_dir(), (
        "断点续跑状态机在 runs_root/light_cones/<id>/（与角色 runs_root/<cid>/ 隔离）")
    assert len(llm.calls) == 2, "evidence+draft 各一次（无打回）"


@_need_data
def test_lc_compile_gate_reject_then_revise(tmp_path):
    """词表外 effect_type → 编译闸打回 → revise 修好 → finalize（内环打回路径）."""
    llm = _fake(_LC_HOOKS_BAD_EFFECT, _LC_HOOKS_OK)
    out = run_light_cone("20000", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out
    assert out["compile1"]["ok"] is False and "brew_coffee" in out["compile1"]["err"], (
        "坏 hooks 被编译闸拒（错误输出回喂 revise）")
    assert "compile2" in out and out["compile2"]["ok"], "修订稿过闸"
    tpl = (tmp_path / "staging" / "light_cones" / "20000_锋镝.yaml").read_text(encoding="utf-8")
    assert "brew_coffee" not in tpl, "定稿=修订稿"
    assert len(llm.calls) == 3, "evidence+draft+revise 各一次"


@_need_data
def test_lc_merge_overreach_rejected(tmp_path):
    """draft 越权重写数值区（多顶层键）→ 机械合并处即拒 → revise 收敛 → finalize."""
    llm = _fake(_LC_HOOKS_OVERREACH, _LC_HOOKS_OK)
    out = run_light_cone("20000", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out
    assert out["compile1"]["ok"] is False
    assert "只许输出顶层 hooks" in out["compile1"]["err"], "越权输出在合并处被拒（不进编译）"
    doc = yaml.safe_load((tmp_path / "staging" / "light_cones" / "20000_锋镝.yaml")
                         .read_text(encoding="utf-8"))
    official = data_pull_lc_node("20000").fn({})
    expect_hp = yaml.safe_load(official["draft_text"])["base_stats"]["hp"]
    assert doc["base_stats"]["hp"] == expect_hp, "越权白值没漏进定稿（hp 取值现场读）"


@_need_data
def test_lc_budget_exhausted_goes_human_queue(tmp_path):
    llm = _fake(_LC_HOOKS_BAD_EFFECT, _LC_HOOKS_BAD_EFFECT)
    out = run_light_cone("20000", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging",
                         budget=2)
    assert "human_queue" in out and "finalize" not in out
    assert out["human_queue"]["review"] == "needs_human"
    assert out["human_queue"]["trail"], "失败轨迹随包"


@_need_data
def test_lc_replay_zero_llm_calls(tmp_path):
    out1 = run_light_cone("20000", llm=_fake(_LC_HOOKS_OK, _LC_HOOKS_OK),
                          search_fn=_fake_search, fetch_fn=_fake_fetch,
                          runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out1
    llm2 = _fake(_LC_HOOKS_OK, _LC_HOOKS_OK)
    out2 = run_light_cone("20000", llm=llm2, search_fn=_fake_search, fetch_fn=_fake_fetch,
                          runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out2
    assert llm2.calls == [], "输入哈希不变 → 全链缓存命中，LLM 零调用（断点续跑）"


@_need_data
def test_lc_draft_prompt_discipline(tmp_path):
    """draft 提示词必带：不脑补纪律 / 编译闸 effect_type 词表 / 锚范例 / 可用叠影参数 /
    生成器草稿全文（只读）——缺一类 LLM 就敢造词表外键或重写数值区."""
    captured = {}

    class _Cap(FakeRunner):
        def __call__(self, *, system, prompt, max_tokens=8000):
            if "DSL hooks 块" in prompt:
                captured["draft"] = prompt
                captured["system"] = system
            return super().__call__(system=system, prompt=prompt, max_tokens=max_tokens)

    llm = _Cap([("DSL hooks 块", _LC_HOOKS_OK), ("输出证据笔记", "# 笔记")])
    run_light_cone("20000", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                   runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    p, s = captured["draft"], captured["system"]
    assert "不脑补——官方 desc 没写的效果不许造" in p, "不脑补纪律（draft 提示词）"
    assert "只输出顶层 hooks" in p, "只产 hooks 块纪律"
    assert "apply_modifier" in p and "gain_skill_point" in p, "编译闸能过的 effect_type 词表随稿下发"
    assert "99001_测试光锥.yaml" in p and "1303_ruan_mei.yaml" in p, "dogfood + 真实验收风格锚双锚"
    assert "param_1" in p, "可用叠影参数（绑定层 $self 命名空间）下发"
    assert "light_cone_id" in p, "生成器草稿全文随稿（只读数值区）"
    assert "不脑补" in s and "叠加" in s, "装备交互语义纪律在系统提示"


# ---------------------------------------------------------------------------
# 遗器全链
# ---------------------------------------------------------------------------

@_need_data
def test_relic_full_chain_finalize(tmp_path):
    """过客 101 全链到 finalize：2pc stat_effects 原样保留 + 4pc hooks 机械合并."""
    llm = _fake(_RELIC_HOOKS_OK, _RELIC_HOOKS_OK)
    out = run_relic("101", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                    runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out
    assert out["golden1"]["ok"]
    tpl = tmp_path / "staging" / "relics" / "101_云无留迹的过客.yaml"
    assert tpl.is_file()
    doc = yaml.safe_load(tpl.read_text(encoding="utf-8"))
    assert doc["set_2pc"]["stat_effects"] == {"dmg_heal_bonus": 0.1}, "2pc 数值件原样"
    assert doc["set_2pc"]["desc"] == "治疗量提高10%。", "desc 原样"
    assert doc["set_4pc"]["hooks"][0]["effects"][0]["effect_type"] == "gain_skill_point", (
        "4pc hooks 并入")
    assert (tmp_path / "runs" / "relics" / "101").is_dir()
    assert len(llm.calls) == 2


@_need_data
def test_relic_gate_reject_then_revise(tmp_path):
    """遗器坏 hooks（词表外 effect_type）→ 打回 → 修好 → finalize."""
    llm = _fake(_RELIC_HOOKS_BAD_EFFECT, _RELIC_HOOKS_OK)
    out = run_relic("101", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                    runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out
    assert out["compile1"]["ok"] is False and "brew_coffee" in out["compile1"]["err"]
    assert len(llm.calls) == 3


@_need_data
def test_relic_merge_overreach_rejected(tmp_path):
    """遗器 draft 越权重写 stat_effects → 合并处即拒 → revise 收敛 → finalize."""
    llm = _fake(_RELIC_HOOKS_OVERREACH, _RELIC_HOOKS_OK)
    out = run_relic("101", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                    runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out
    assert "只许含 hooks" in out["compile1"]["err"]
    doc = yaml.safe_load((tmp_path / "staging" / "relics" / "101_云无留迹的过客.yaml")
                         .read_text(encoding="utf-8"))
    assert doc["set_2pc"]["stat_effects"] == {"dmg_heal_bonus": 0.1}, "越权数值没漏进定稿"


# ---------------------------------------------------------------------------
# golden_diff 单测（不依赖运行图，直接喂数据锚包）
# ---------------------------------------------------------------------------

def _lc_official():
    return data_pull_lc_node("20000").fn({})


def _relic_official():
    return data_pull_relic_node("101").fn({})


@_need_data
def test_golden_mismatches_lc_unit():
    official = _lc_official()
    good, err = _merge_lc_hooks(official["draft_text"], _LC_HOOKS_OK)
    assert not err and _golden_mismatches_lc(good, official) == [], "合格稿零 mismatch"
    # ① 白值 drift（生成器草稿过时族——打回措辞指路重跑生成器）
    #（篡改值动态取稿面实值——白值随生成器/loader 修复变动，不写死字面量）
    import re as _re
    cur_hp = _re.search(r"hp: ([\d.]+)", good).group(1)
    bad = good.replace(f"hp: {cur_hp}", "hp: 700.0", 1)
    assert any("base_stats.hp" in m and "drift" in m
               for m in _golden_mismatches_lc(bad, official))
    # ② 叠影表行数 ≠ 档数（整行剔除——safe_dump 两格缩进，replace 须带缩进防串行）
    bad = good.replace("  - 0.12\n", "", 1)
    assert any("行数 4 ≠ 叠影档数 5" in m for m in _golden_mismatches_lc(bad, official))
    # ② 行值不在 params 行内
    bad = good.replace("  - 0.15\n", "  - 0.151\n", 1)
    assert any("不在叠影 S2 参数行" in m for m in _golden_mismatches_lc(bad, official))
    # ③ hooks 空缺（desc 非空但 hooks 空=机制未收编）
    empty, err = _merge_lc_hooks(official["draft_text"], "hooks: []")
    assert not err
    assert any("机制未收编" in m for m in _golden_mismatches_lc(empty, official))


@_need_data
def test_golden_mismatches_relic_unit():
    official = _relic_official()
    good, err = _merge_relic_hooks(official["draft_text"], _RELIC_HOOKS_OK)
    assert not err and _golden_mismatches_relic(good, official) == [], "合格稿零 mismatch"
    # ① 2pc 属性 drift
    bad = good.replace("dmg_heal_bonus: 0.1", "dmg_heal_bonus: 0.5")
    assert any("set_2pc.stat_effects.dmg_heal_bonus" in m
               for m in _golden_mismatches_relic(bad, official))
    # ② 4pc hooks 空缺
    nohooks, err = _merge_relic_hooks(official["draft_text"], "set_2pc:\n  hooks: []\n")
    assert not err
    assert any("4pc 机制未收编" in m for m in _golden_mismatches_relic(nohooks, official))


# ---------------------------------------------------------------------------
# batch kind 分流 + 花名册（数量现场算，不写死）
# ---------------------------------------------------------------------------

def test_anchor_ids_per_kind():
    # 光锥锚 = dogfood 99001 + 验收批（加锚=放新 fixture——现场对账不写死清单）
    lc_fixture_dir = ROOT / "tests/fixtures/templates/light_cones"
    assert anchor_ids("light_cone") == frozenset(
        p.name.split("_", 1)[0] for p in lc_fixture_dir.glob("*.yaml")), (
        "光锥锚集=fixtures 目录文件名派生（验收批已入库）")
    # 遗器锚 = dogfood 990 + 验收批（加锚=放新 fixture——现场对账不写死清单）
    relic_anchors = anchor_ids("relic")
    fixture_dir = ROOT / "tests/fixtures/templates/relics"
    assert relic_anchors == frozenset(
        p.name.split("_", 1)[0] for p in fixture_dir.glob("*.yaml")), (
        "遗器锚集=fixtures 目录文件名派生（验收批已入库）")
    assert "990" in relic_anchors and "101" in relic_anchors
    assert anchor_ids() == anchor_ids("character"), "缺省 kind=character（角色锚不变）"


@_need_data
def test_roster_counts_live_glob():
    """花名册=生成器草稿全量 id——数量与目录现场对账（版本追踪，不写死计数）."""
    lc_dir = ROOT / "data/sim_templates/light_cones"
    relic_dir = ROOT / "data/sim_templates/relics"
    assert len(roster_light_cones()) == len(list(lc_dir.glob("*.yaml"))) > 0
    assert len(roster_relics()) == len(list(relic_dir.glob("*.yaml"))) > 0
    assert roster_light_cones() == sorted(roster_light_cones()), "确定性批序"
    assert "20000" in roster_light_cones() and "101" in roster_relics()


def test_collect_targets_kind_dispatch():
    lc = collect_targets(kind="light_cone")
    # 验收批已转锚（默认跳过；未验收的仍在册；99001 dogfood 不在生成器花名册）
    assert lc == [c for c in roster_light_cones() if c not in anchor_ids("light_cone")]
    assert "99001" not in lc and "20000" not in lc
    relic = collect_targets(kind="relic")
    # 验收批已转锚（101 等 51 套入库——默认跳过；未验收的仍在册）
    assert "990" not in relic and "101" not in relic
    assert relic == [c for c in roster_relics() if c not in anchor_ids("relic")]
    assert not (set(lc) & set(relic)), "kind 分流不串名册"
    assert collect_targets(kind="light_cone", ids=["20000"]) == ["20000"], "显式 ids 直给"
    assert collect_targets(kind="light_cone", include_anchors=True) == roster_light_cones(), (
        "include_anchors=全名册原样（锚过滤只在默认路径生效）")


@_need_data
def test_collect_targets_kind_skips_anchors(monkeypatch, tmp_path):
    """锚过滤真路径：手写真实装备模板进 fixtures → 默认跳过、--include-anchors 放行."""
    from hsr_nous.ops.annotator import batch as batch_mod

    d = tmp_path / "lc_fixtures"
    d.mkdir()
    (d / "20000_手写锋镝.yaml").write_text("# 手写锚", encoding="utf-8")
    monkeypatch.setitem(batch_mod.FIXTURES_DIRS, "light_cone", d)
    assert "20000" not in collect_targets(kind="light_cone"), "锚实体默认跳过"
    assert "20000" in collect_targets(kind="light_cone", include_anchors=True), "放行锚重打"
