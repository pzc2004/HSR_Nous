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

### 6.1 真实词条值覆盖（账号导入）

账号导入等场景需要保留当前等级下的真实词条值，而不是按满级主词条和高档副词条重算。`build.yaml` 的每个 relic 槽位可选补充：

```yaml
relics:
  head:
    set_id: "127"
    main: "hp"
    main_value: 705.6
    subs:
      hp_pct: 2
      spd: 1
    sub_values:
      hp_pct: 0.094
      spd: 2.6
```

- `main_value`：当前等级下主词条的实际值；`main` 存在时必须有对应 `main_value`。
- `sub_values`：每个有效副词条的**实际累计值**（含初始值和强化值），比例统一用小数。`subs` 的整数次数保留作审计和旧路径回退。
- 有 `main_value` / `sub_values` 时优先使用实际值；旧手写 build 没有这些字段时，继续走原有满级主词条、roll 数 × 高档副词条路径。词条 ID、主/副位置校验和 modifier 聚合方式不变。
- 账号导入采用每件全量实际值约束：主词条缺 `main_value` 或有效副词条缺 `sub_values` 时记为数据缺失，不得在同一件遗器内静默混用真实值与高档近似。
- `set_id` 仍按原方式决定 2/4 件套激活，与是否使用实际词条值无关。

**adapter 职责**：根据遗器配置计算最终属性，合并到 `base_stats` 中。

**未来扩展**：部分 4 件套效果会触发“层数型资源”，可复用 `custom_resources`，`owner: "relic"`。当前 23 角色盘点未出现需建模的遗器层数资源，保持 forward-compatibility。详见 `16_custom_resources.md` §16.2。

---
