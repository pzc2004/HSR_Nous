"""打标 DAG 单角色端到端（FakeRunner 罐头 LLM）——内环三态 + 重放.

三态：打回→修订→过闸→finalize / 预算耗尽→human_queue / 重放零 LLM 调用。
万敌 1404 dogfood（drain_hp 现成原语；真实数据走 query-game-data 拉取）。
"""

from __future__ import annotations

from hsr_nous.ops.annotator import FakeRunner, run_character

_NOTES = "# 万敌 1404 证据笔记\n- 战技 140402：耗自身当前 HP 50%（官方文本，floor 1）→ blast 虚数\n"

_TPL_VALID = """actor_id: "1404"
name: "万敌"
level: 80
path: "destruction"
base_stats:
  hp: 1500.0
  atk: 600.0
  def: 500.0
  spd: 100.0
  crit_rate: 0.05
  crit_dmg: 0.5
  max_energy: 160
actions:
  - action_id: "140401"
    name: "踏平雄狮的震荡"
    action_type: "basic"
    target_type: "single"
    damage_type: "imaginary"
    scaling: [{"hp": 0.5}]
    toughness_dmg: 10
    skill_point_gain: 1
    energy_gain: 20
  - action_id: "140402"
    name: "万死无悔"
    action_type: "skill"
    target_type: "blast"
    damage_type: "imaginary"
    scaling: [{"hp": 0.5}]
    toughness_dmg: 20
    skill_point_cost: 1
    energy_gain: 30
hooks:
  - event: "on_action"
    condition: "$event.actor == '1404' && $event.action_id == '140402'"
    effects:
      - effect_type: "drain_hp"
        target: "self"
        amount: "0.5 * $self.hp"
        floor: 1
        drain_ratio: 0
"""

_TPL_INVALID = _TPL_VALID.replace(
    "    skill_point_cost: 1\n",
    "    skill_point_cost: 1\n    bogus_key: 1   # 词表闸必炸（内环打回测试件）\n",
)


def _fake(v_draft: str, v_revise: str) -> FakeRunner:
    return FakeRunner([
        ("被闸门打回", v_revise),      # revise 提示词命中词在前
        ("DSL YAML 模板", v_draft),    # draft
        ("证据笔记", _NOTES),          # evidence
    ])


def test_inner_loop_revise_then_finalize(tmp_path):
    llm = _fake(_TPL_INVALID, _TPL_VALID)
    out = run_character("1404", llm=llm, runs_root=tmp_path / "runs",
                        staging_root=tmp_path / "staging")
    assert "finalize" in out and "human_queue" not in out, "打回一次后过闸到 finalize"
    tpl = tmp_path / "staging" / "1404_万敌.yaml"
    assert tpl.is_file() and "bogus_key" not in tpl.read_text(encoding="utf-8"), "定稿=修订稿"
    assert (tmp_path / "staging" / "notes" / "1404.md").is_file(), "证据笔记随候选包"
    assert len(llm.calls) == 3, "evidence+draft+revise 各一次（内环打回触发修订）"


def test_budget_exhausted_goes_human_queue(tmp_path):
    llm = _fake(_TPL_INVALID, _TPL_INVALID)
    out = run_character("1404", llm=llm, runs_root=tmp_path / "runs",
                        staging_root=tmp_path / "staging", budget=2)
    assert "human_queue" in out and "finalize" not in out
    assert out["human_queue"]["review"] == "needs_human"
    assert out["human_queue"]["trail"], "失败轨迹随包（compile 错误输出）"


def test_replay_zero_llm_calls(tmp_path):
    out1 = run_character("1404", llm=_fake(_TPL_VALID, _TPL_VALID),
                         runs_root=tmp_path / "runs", staging_root=tmp_path / "staging")
    assert "finalize" in out1
    llm2 = _fake(_TPL_VALID, _TPL_VALID)
    out2 = run_character("1404", llm=llm2, runs_root=tmp_path / "runs",
                         staging_root=tmp_path / "staging")
    assert "finalize" in out2
    assert llm2.calls == [], "输入哈希不变 → 全链缓存命中，LLM 零调用"
