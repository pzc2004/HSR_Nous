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
  # 副词条初始值与每次强化增加值：各自独立从 Low/Med/High 三档随机一档（= base、base+step、base+2·step）
  # 数值来源：data/starrailres/index_new/cn/relic_sub_affixes.json（rarity "5"），与 fandom Relic/Stats 一致
  hp: {base: 33.87, step: 4.23376}          # 小生命 33.87 / 38.10 / 42.34
  atk: {base: 16.935, step: 2.11688}        # 小攻击 16.94 / 19.05 / 21.17
  def: {base: 16.935, step: 2.11688}        # 小防御 16.94 / 19.05 / 21.17
  hp_pct: {base: 0.03456, step: 0.00432}    # 3.456% / 3.888% / 4.32%
  atk_pct: {base: 0.03456, step: 0.00432}
  def_pct: {base: 0.0432, step: 0.0054}     # 4.32% / 4.86% / 5.4%
  spd: {base: 2.0, step: 0.3}               # 速度 2.0 / 2.3 / 2.6（唯一不满足 0.8/0.9/1.0 比例的词条）
  crit_rate: {base: 0.02592, step: 0.00324} # 2.592% / 2.916% / 3.24%
  crit_dmg: {base: 0.05184, step: 0.00648}  # 5.184% / 5.832% / 6.48%
  break_effect: {base: 0.05184, step: 0.00648}
  effect_hit: {base: 0.03456, step: 0.00432}
  effect_res: {base: 0.03456, step: 0.00432}
```

**编译期消费**：`build.yaml` 的 `main:`/`subs:` 词条 id → 数值查 `sim_schema/rulebook.yaml`
的 `relic_affixes` 段（上表数据的镜像，逐值一致由 doc_lint 遗器词条镜像闸重算保证）；
不在表的词条（错拼/编造/用错主副位置）编译期报错。

**adapter 职责**：根据遗器配置计算最终属性，合并到 `base_stats` 中。

**未来扩展**：部分 4 件套效果会触发“层数型资源”，可复用 `custom_resources`，`owner: "relic"`。当前 23 角色盘点未出现需建模的遗器层数资源，保持 forward-compatibility。详见 `16_custom_resources.md` §16.2。

---
