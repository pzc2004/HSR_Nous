# Docs 文档目录

存放项目参考文档，包括游戏规则、机制说明、设计决策记录等。

## 文件结构

```
docs/
├── README.md              # 本文档
├── game_rules.md          # 崩铁核心战斗规则总纲（公式、机制、触发时机）
└── mechanics/             # 各模块详细机制文档
    ├── 00_game_basics.md         # 游戏基础概念（命途/属性/光锥/遗器/养成/基础属性）
    ├── 01_base_stats.md          # 基础属性、治疗与护盾、技能与打击方式、记忆命途与忆灵
    ├── 02_damage_formula.md      # 伤害公式详解（含增伤、易伤、防御、抗性、暴击、真实伤害）
    ├── 03_action_sequence.md     # 行动序与速度机制（AV、拉条/推条、额外回合、冻结）
    ├── 04_break_system.md        # 击破/弱点击破机制（韧性削减、击破伤害、超击破）
    ├── 05_energy_system.md       # 能量与终结技机制
    ├── 06_skill_points.md        # 战技点机制
    ├── 07_buff_system.md         # Buff/Debuff 层数、持续时间、结算、驱散、属性二次转化
    ├── 08_elation_system.md      # 欢愉命途机制（欢愉伤害、阿哈时刻、笑点）
    ├── 09_follow_up_attacks.md   # 追加攻击触发规则
    ├── 10_taunt_system.md        # 嘲讽值与受击概率
    ├── 11_special_mechanics.md   # 特殊机制（专属效果、控制、HP 事件 vs 伤害事件、结界/境界/连携攻击）
    └── 12_technique_system.md    # 秘技系统（秘技点、分类、战前策略）
```

## 阅读指南

- **`game_rules.md`**：战斗规则总纲——索引 + 速查公式 + 待确认事项 + 修改记录（详细内容已拆分到 `mechanics/`）
- **`mechanics/`**：各专题的独立文档，方便单独查阅某一机制的细节

## 与代码的关系

- `docs/` 里的文档是**参考源**：描述游戏"应该是什么样"
- `src/hsr_nous/sim_schema/README.md` 是**实现层**：描述模拟器"怎么表达"
- 当游戏规则文档和代码实现有冲突时，以游戏规则文档为准，代码需要调整

## 参考来源

- **紫喵Azunya** 编写的[《星穹铁道入坑指南》系列攻略](https://www.miyoushe.com/sr/collection/1985001)（米游社）
- **[Honkai: Star Rail Wiki](https://honkai-star-rail.fandom.com/wiki/Honkai:_Star_Rail_Wiki)**（Fandom）——机制词条、技能数据、专属效果、嘲讽值/秘技系统等
- **[B 站 · 夜殇黑羽《论属性的二次转化》](https://www.bilibili.com/opus/1176311260863528979)**——属性二次转化全角色盘点（§7.7）
- **[StarRailRes](https://github.com/Mar-7th/StarRailRes)**（Dimbreath）——基础数值数据

## 写作建议

- 用中文写，方便沟通
- 公式用代码块表示
- 不确定的地方标注 `[待确认]`
- 版本变化时在 `game_rules.md` 保留历史记录
