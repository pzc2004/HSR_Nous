## 6. 遗器数值设计

遗器数值分两部分：**主词条**（固定值，由部位决定）和**副词条**（随机数值，由强化次数决定）。

```yaml
relic_main_stats:
  head: {stat: "hp", base: 705.0}           # 固定
  hand: {stat: "atk", base: 352.0}          # 固定
  body:                                         # 可选
    candidates: ["hp_pct", "atk_pct", "def_pct", "crit_rate", "crit_dmg", "heal_bonus", "effect_hit"]
  feet:
    candidates: ["hp_pct", "atk_pct", "def_pct", "spd"]
  sphere:
    candidates: ["hp_pct", "atk_pct", "def_pct", "physical_dmg", "fire_dmg", "ice_dmg", ...]
  rope:
    candidates: ["hp_pct", "atk_pct", "def_pct", "break_effect", "energy_regen"]

relic_sub_stats:
  # 副词条每次强化增加的数值（崩铁标准）
  hp: {base: 33.87, step: 33.87}           # 小生命
  atk: {base: 16.93, step: 16.93}          # 小攻击
  def: {base: 16.93, step: 16.93}          # 小防御
  hp_pct: {base: 0.034, step: 0.034}
  atk_pct: {base: 0.034, step: 0.034}
  def_pct: {base: 0.043, step: 0.043}
  spd: {base: 2.0, step: 2.3}              # 速度有 2.0 / 2.3 两档
  crit_rate: {base: 0.026, step: 0.032}    # 2.6% / 3.2%
  crit_dmg: {base: 0.052, step: 0.064}     # 5.2% / 6.4%
  break_effect: {base: 0.052, step: 0.064}
  effect_hit: {base: 0.034, step: 0.043}
  effect_res: {base: 0.034, step: 0.043}
```

**adapter 职责**：根据遗器配置计算最终属性，合并到 `base_stats` 中。

---
