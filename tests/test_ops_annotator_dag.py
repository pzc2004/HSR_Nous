"""打标 DAG 单角色端到端（FakeRunner 罐头 LLM）——内环三态 + 重放.

三态：打回→修订→过闸→finalize / 预算耗尽→human_queue / 重放零 LLM 调用。
万敌 1404 dogfood（drain_hp 现成原语；真实数据走 query-game-data 拉取）。
"""

from __future__ import annotations

from hsr_nous.ops.annotator import FakeRunner, run_character
from tests._annotator_dogfood import TPL_1404_GOLDEN_CLEAN

_NOTES = "# 万敌 1404 证据笔记\n- 战技 140402：耗自身当前 HP 50%（官方文本，floor 1）→ blast 虚数\n"

_TPL_VALID = TPL_1404_GOLDEN_CLEAN

_TPL_INVALID = _TPL_VALID.replace(
    "    toughness_dmg: 10\n",
    "    toughness_dmg: 10\n    bogus_key: 1   # 词表闸必炸（内环打回测试件）\n",
    1,
)


def _fake(v_draft: str, v_revise: str) -> FakeRunner:
    return FakeRunner([
        ("被闸门打回", v_revise),      # revise 提示词命中词在前
        ("DSL YAML 模板", v_draft),    # draft
        ("证据笔记", _NOTES),          # evidence
    ])


def _fake_search(query, max_results):
    return [{"title": f"{query} 结果", "url": f"https://example.com/{abs(hash(query)) % 1000}",
             "snippet": "社区摘要"}]


def _fake_fetch(url, cap):
    return f"正文:{url}"

def test_inner_loop_revise_then_finalize(tmp_path):
    llm = _fake(_TPL_INVALID, _TPL_VALID)
    out = run_character("1404", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                        runs_root=tmp_path / "runs",
                        staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out, "打回一次后过闸到 finalize"
    tpl = tmp_path / "staging" / "1404_万敌.yaml"
    assert tpl.is_file() and "bogus_key" not in tpl.read_text(encoding="utf-8"), "定稿=修订稿"
    assert (tmp_path / "staging" / "notes" / "1404.md").is_file(), "证据笔记随候选包"
    assert len(llm.calls) == 3, "evidence+draft+revise 各一次（内环打回触发修订）"


def test_budget_exhausted_goes_human_queue(tmp_path):
    llm = _fake(_TPL_INVALID, _TPL_INVALID)
    out = run_character("1404", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                        runs_root=tmp_path / "runs",
                        staging_root=tmp_path / "staging", budget=2)
    assert "human_queue" in out and "finalize" not in out
    assert out["human_queue"]["review"] == "needs_human"
    assert out["human_queue"]["trail"], "失败轨迹随包（compile 错误输出）"


def test_replay_zero_llm_calls(tmp_path):
    out1 = run_character("1404", llm=_fake(_TPL_VALID, _TPL_VALID),
                         search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out1
    llm2 = _fake(_TPL_VALID, _TPL_VALID)
    out2 = run_character("1404", llm=llm2, search_fn=_fake_search, fetch_fn=_fake_fetch,
                         runs_root=tmp_path / "runs",
                         staging_root=tmp_path / "staging")
    assert "finalize" in out2
    assert llm2.calls == [], "输入哈希不变 → 全链缓存命中，LLM 零调用"


# ---------------------------------------------------------------------------
# golden_diff 金样对拍（v2 机械闸）
# ---------------------------------------------------------------------------

def test_golden_reject_then_revise_finalize(tmp_path):
    """初稿金样不过（白值幻视）→ 打回 → 修订稿过闸到 finalize（内环第三闸实证）."""
    bad = _TPL_VALID.replace("  hp: 1552.32", "  hp: 1500.0   # 幻视白值（金样必炸）")
    llm = _fake(bad, _TPL_VALID)
    out = run_character("1404", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                        runs_root=tmp_path / "runs",
                        staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out
    assert "golden1" in out, "金样闸进运行图"
    assert len(llm.calls) == 3, "evidence+draft+revise 各一次（金样打回触发修订）"


def test_golden_mismatches_unit():
    """单元：四类幻视逐类命中（不依赖运行图，直接喂官方包）."""
    from hsr_nous.ops.annotator.nodes import _golden_mismatches
    official = {
        "skills": [
            {"id": "140401", "name_cn": "踏破征途的誓言", "type_text": "Basic ATK",
             "desc": "对指定敌方单体造成等同于万敌 #1[i]% 生命上限的虚数属性伤害。",
             "params": [[0.25], [0.3], [0.35], [0.4], [0.45], [0.5], [0.55], [0.6], [0.65], [0.7]]},
            {"id": "140402", "name_cn": "万死无悔", "type_text": "Skill",
             "desc": "对指定敌方单体造成 #1[i]，相邻目标 #2[i]，消耗当前生命值 #3[i]。",
             "params": [[0.45, 0.25, 0.5], [0.495, 0.275, 0.5]]},
            {"id": "140403", "name_cn": "诛天焚骨的王座", "type_text": "Ultimate",
             "desc": "对指定敌方单体造成 #1[i]，相邻目标 #2[i]。",
             "params": [[0.96, 0.6], [1.024, 0.64]]},
        ]}
    # 合格稿零 mismatch（base_stats 幻视也在内——calc 走真管线，下面逐类拆开验）
    good = _TPL_VALID.replace(
        '    scaling: [{"hp": 0.45}, {"hp": 0.495}, {"hp": 0.54}, {"hp": 0.585}, {"hp": 0.63}, {"hp": 0.675}, {"hp": 0.7312}, {"hp": 0.7875}, {"hp": 0.8438}, {"hp": 0.9}, {"hp": 0.945}, {"hp": 0.99}, {"hp": 1.035}, {"hp": 1.08}, {"hp": 1.125}]\n    scaling_blast: [{"hp": 0.25}, {"hp": 0.275}, {"hp": 0.3}, {"hp": 0.325}, {"hp": 0.35}, {"hp": 0.375}, {"hp": 0.4062}, {"hp": 0.4375}, {"hp": 0.4688}, {"hp": 0.5}, {"hp": 0.525}, {"hp": 0.55}, {"hp": 0.575}, {"hp": 0.6}, {"hp": 0.625}]',
        '    scaling: [{"hp": 0.45}, {"hp": 0.495}]\n    scaling_blast: [{"hp": 0.25}, {"hp": 0.275}]').replace(
        '    scaling: [{"hp": 0.96}, {"hp": 1.024}, {"hp": 1.088}, {"hp": 1.152}, {"hp": 1.216}, {"hp": 1.28}, {"hp": 1.36}, {"hp": 1.44}, {"hp": 1.52}, {"hp": 1.6}, {"hp": 1.664}, {"hp": 1.728}, {"hp": 1.792}, {"hp": 1.856}, {"hp": 1.92}]\n    scaling_blast: [{"hp": 0.6}, {"hp": 0.64}, {"hp": 0.68}, {"hp": 0.72}, {"hp": 0.76}, {"hp": 0.8}, {"hp": 0.85}, {"hp": 0.9}, {"hp": 0.95}, {"hp": 1.0}, {"hp": 1.04}, {"hp": 1.08}, {"hp": 1.12}, {"hp": 1.16}, {"hp": 1.2}]',
        '    scaling: [{"hp": 0.96}, {"hp": 1.024}]\n    scaling_blast: [{"hp": 0.6}, {"hp": 0.64}]').replace(
        '  - action_id: "140409"', '  - action_id: "140409"  # noqa').replace(
        '  - action_id: "140411"', '  - action_id: "140411"  # noqa')
    # 140409/140411 不在本 official 包——剪掉（脑补 id 闸会拦）
    import re as _re
    good = _re.sub(r"  - action_id: \"140409\".*?hooks:", "hooks:", good, flags=_re.S)
    assert _golden_mismatches("1404", good, official) == [], "合格稿零 mismatch"
    # ① 白值幻视
    bad = good.replace("  hp: 1552.32", "  hp: 1500.0")
    assert any("base_stats.hp" in m for m in _golden_mismatches("1404", bad, official))
    # ② 脑补 id
    bad = good.replace('action_id: "140401"', 'action_id: "140499"')
    assert any("140499 不在官方技能清单" in m for m in _golden_mismatches("1404", bad, official))
    # ② 缺核心
    bad = _re.sub(r"  - action_id: \"140403\".*?(?=  - action_id:|hooks:)", "", good, flags=_re.S)
    assert any("140403" in m and "缺行动块" in m for m in _golden_mismatches("1404", bad, official))
    # ③ 单行误取末行（万敌 lv15 误标 lv10 族）
    bad = good.replace('    scaling: [{"hp": 0.45}, {"hp": 0.495}]',
                       '    scaling: [{"hp": 0.495}]')
    assert any("行数 1 ≠ params 行数 2" in m for m in _golden_mismatches("1404", bad, official))
    # ③ 主倍率对不上（行内值集口径——0.51 不在 lv2 行 [0.495, 0.275, 0.5] 内；
    # 值撞同行其他列（0.5）机械闸放行，倍率列位置归人工闸判）
    bad = good.replace('    scaling: [{"hp": 0.45}, {"hp": 0.495}]',
                       '    scaling: [{"hp": 0.45}, {"hp": 0.51}]')
    assert any("scaling[1]" in m and "不在 params[1]" in m
               for m in _golden_mismatches("1404", bad, official))
    assert _golden_mismatches(
        "1404", good.replace('    scaling: [{"hp": 0.45}, {"hp": 0.495}]',
                             '    scaling: [{"hp": 0.45}, {"hp": 0.5}]'),
        official) == [], "0.5 撞 lv2 行第 3 列——行内值集放行（列位置归人工闸）"
    # ③ 相邻倍率对不上
    bad = good.replace('    scaling_blast: [{"hp": 0.25}, {"hp": 0.275}]',
                       '    scaling_blast: [{"hp": 0.25}, {"hp": 0.28}]')
    assert any("scaling_blast[1]" in m for m in _golden_mismatches("1404", bad, official))


def test_draft_prompt_carries_params_table_and_cheatsheet(tmp_path):
    """draft 提示词必带：官方 params 全表（唯一照抄源——禁内插）+ 结构块速查（shield 族）——
    试点实证：缺表 → LLM 线性内插补行被金样打回；缺速查 → shield 写成 str 三轮修不回。"""
    captured = {}

    class _Cap(FakeRunner):
        def __call__(self, *, system, prompt, max_tokens=8000):
            if "DSL YAML 模板" in prompt:
                captured["draft"] = prompt
                captured["system"] = system
            return super().__call__(system=system, prompt=prompt, max_tokens=max_tokens)

    llm = _Cap([("DSL YAML 模板", TPL_1404_GOLDEN_CLEAN), ("证据笔记", "# 笔记")])
    run_character("1404", llm=llm, search_fn=_fake_search, fetch_fn=_fake_fetch,
                        runs_root=tmp_path / "runs",
                  staging_root=tmp_path / "staging")
    assert "唯一照抄源" in captured["draft"] and "params" in captured["draft"]
    assert "140402" in captured["draft"], "params 全表按技能 id 下发"
    assert "shield:" in captured["system"] and "remove_modifier" in captured["system"], \
        "结构块速查在系统提示（draft/revise 同享）"
    assert "不许目测表尾当 lv10" in captured["system"], "全表照抄纪律（取档 index=等级-1）"
