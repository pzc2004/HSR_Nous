"""打标 DAG dogfood 共享件——万敌 1404 金样净模板（过 compile/smoke/golden_diff 三闸）。

金样净=白值实值（calc_character_stats lv80）+ 官方五行动块 + scaling 全表照抄 params
（取档 index=等级-1）。test_ops_annotator_dag / test_ops_annotator_community 共用
（打回件由各测试自行 replace 派生）。
"""

from __future__ import annotations

TPL_1404_GOLDEN_CLEAN = """actor_id: "1404"
name: "万敌"
level: 80
path: "destruction"
base_stats:
  hp: 1552.32
  atk: 426.888
  def: 194.04
  spd: 100.0
  crit_rate: 0.05
  crit_dmg: 0.873
  max_energy: 160
actions:
  - action_id: "140401"
    name: "踏破征途的誓言"
    action_type: "basic"
    target_type: "single"
    damage_type: "imaginary"
    scaling: [{"hp": 0.25}, {"hp": 0.3}, {"hp": 0.35}, {"hp": 0.4}, {"hp": 0.45}, {"hp": 0.5}, {"hp": 0.55}, {"hp": 0.6}, {"hp": 0.65}, {"hp": 0.7}]
    toughness_dmg: 10
    skill_point_gain: 1
    energy_gain: 20
  - action_id: "140402"
    name: "万死无悔"
    action_type: "skill"
    target_type: "blast"
    damage_type: "imaginary"
    scaling: [{"hp": 0.45}, {"hp": 0.495}, {"hp": 0.54}, {"hp": 0.585}, {"hp": 0.63}, {"hp": 0.675}, {"hp": 0.7312}, {"hp": 0.7875}, {"hp": 0.8438}, {"hp": 0.9}, {"hp": 0.945}, {"hp": 0.99}, {"hp": 1.035}, {"hp": 1.08}, {"hp": 1.125}]
    scaling_blast: [{"hp": 0.25}, {"hp": 0.275}, {"hp": 0.3}, {"hp": 0.325}, {"hp": 0.35}, {"hp": 0.375}, {"hp": 0.4062}, {"hp": 0.4375}, {"hp": 0.4688}, {"hp": 0.5}, {"hp": 0.525}, {"hp": 0.55}, {"hp": 0.575}, {"hp": 0.6}, {"hp": 0.625}]
    toughness_dmg: 20
    skill_point_cost: 0
    energy_gain: 30
  - action_id: "140403"
    name: "诛天焚骨的王座"
    action_type: "ultimate"
    target_type: "blast"
    damage_type: "imaginary"
    energy_cost: 160
    scaling: [{"hp": 0.96}, {"hp": 1.024}, {"hp": 1.088}, {"hp": 1.152}, {"hp": 1.216}, {"hp": 1.28}, {"hp": 1.36}, {"hp": 1.44}, {"hp": 1.52}, {"hp": 1.6}, {"hp": 1.664}, {"hp": 1.728}, {"hp": 1.792}, {"hp": 1.856}, {"hp": 1.92}]
    scaling_blast: [{"hp": 0.6}, {"hp": 0.64}, {"hp": 0.68}, {"hp": 0.72}, {"hp": 0.76}, {"hp": 0.8}, {"hp": 0.85}, {"hp": 0.9}, {"hp": 0.95}, {"hp": 1.0}, {"hp": 1.04}, {"hp": 1.08}, {"hp": 1.12}, {"hp": 1.16}, {"hp": 1.2}]
    toughness_dmg: 20
    energy_gain: 5
  - action_id: "140409"
    name: "弑王成王"
    action_type: "skill"
    target_type: "blast"
    damage_type: "imaginary"
    scaling: [{"hp": 0.55}, {"hp": 0.605}, {"hp": 0.66}, {"hp": 0.715}, {"hp": 0.77}, {"hp": 0.825}, {"hp": 0.8938}, {"hp": 0.9625}, {"hp": 1.0312}, {"hp": 1.1}, {"hp": 1.155}, {"hp": 1.21}, {"hp": 1.265}, {"hp": 1.32}, {"hp": 1.375}]
    scaling_blast: [{"hp": 0.33}, {"hp": 0.363}, {"hp": 0.396}, {"hp": 0.429}, {"hp": 0.462}, {"hp": 0.495}, {"hp": 0.5363}, {"hp": 0.5775}, {"hp": 0.6188}, {"hp": 0.66}, {"hp": 0.693}, {"hp": 0.726}, {"hp": 0.759}, {"hp": 0.792}, {"hp": 0.825}]
    toughness_dmg: 20
    skill_point_cost: 0
    energy_gain: 30
  - action_id: "140411"
    name: "弑神登神"
    action_type: "skill"
    target_type: "blast"
    damage_type: "imaginary"
    scaling: [{"hp": 1.4}, {"hp": 1.54}, {"hp": 1.68}, {"hp": 1.82}, {"hp": 1.96}, {"hp": 2.1}, {"hp": 2.275}, {"hp": 2.45}, {"hp": 2.625}, {"hp": 2.8}, {"hp": 2.94}, {"hp": 3.08}, {"hp": 3.22}, {"hp": 3.36}, {"hp": 3.5}]
    scaling_blast: [{"hp": 0.84}, {"hp": 0.924}, {"hp": 1.008}, {"hp": 1.092}, {"hp": 1.176}, {"hp": 1.26}, {"hp": 1.365}, {"hp": 1.47}, {"hp": 1.575}, {"hp": 1.68}, {"hp": 1.764}, {"hp": 1.848}, {"hp": 1.932}, {"hp": 2.016}, {"hp": 2.1}]
    toughness_dmg: 30
    skill_point_cost: 0
    energy_gain: 10
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
