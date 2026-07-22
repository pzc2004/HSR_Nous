# 游戏基础概念

> **资料来源**：[Fandom - Path](https://honkai-star-rail.fandom.com/wiki/Path)、[Fandom - Light Cone](https://honkai-star-rail.fandom.com/wiki/Light_Cone)、[Fandom - Relic](https://honkai-star-rail.fandom.com/wiki/Relic)、StarRailRes 本地数据

### 0.1 命途 (Path)

角色的职业定位。每个角色属于一个命途，决定其战斗定位和可装备的光锥。

| 英文名 | 中文名 | 定位 | 对应星神 |
|-------|-------|------|---------|
| Destruction | 毁灭 | 前排输出，兼顾输出与自保，常以 HP 换伤害 | Nanook（纳努克） |
| The Hunt | 巡猎 | 单体爆发输出，擅长击杀 BOSS | Lan（岚） |
| Erudition | 智识 | 群体输出，擅长清理多目标 | Nous（博识尊） |
| Harmony | 同谐 | 增益辅助，强化队友属性和行动 | Xipe（希佩） |
| Nihility | 虚无 | 减益辅助，施加 DoT 和控制 | IX（伊克斯） |
| Preservation | 存护 | 坦克/护盾，吸收伤害保护队友 | Qlipoth（克里珀） |
| Abundance | 丰饶 | 治疗，回复 HP 和解除负面状态 | Yaoshi（药师） |
| Remembrance | 记忆 | 召唤系，通过忆灵/忆灵技造成伤害 | Fuli（浮黎） |
| Elation | 欢愉 | 欢愉伤害体系，笑点/阿哈时刻等机制 | Aha（阿哈） |

> StarRailRes 内部 ID 与英文显示名不同：Warrior=Destruction, Rogue=The Hunt, Mage=Erudition, Shaman=Harmony, Warlock=Nihility, Knight=Preservation, Priest=Abundance, Memory=Remembrance, Elation=Elation。

### 0.2 属性 (Combat Type / Element)

角色和敌人的攻击属性。共 7 种：

| 英文 | 中文 | 缩写 |
|------|------|------|
| Physical | 物理 | PHY |
| Fire | 火 | FIR |
| Ice | 冰 | ICE |
| Lightning | 雷 | THU |
| Wind | 风 | WND |
| Quantum | 量子 | QUA |
| Imaginary | 虚数 | IMA |

敌人对每种属性有**弱点**（Weakness）和**抗性**（Resistance）。通常只有击中弱点属性才能削减韧性（存在无视弱点削韧等例外，详见 [04_break_system.md](04_break_system.md)）。星铁**没有元素反应**（跟原神不同）。

### 0.3 光锥 (Light Cone)

角色装备的「武器」。提供基础属性加成和被动技能。

- **命途匹配**：角色命途必须跟光锥命途一致，**被动效果才生效**。命途不匹配时只给基础属性（HP/ATK/DEF），不给被动。
- **稀有度**：3★ ~ 5★，稀有度越高基础属性越高。
- **等级上限**：80 级，通过消耗其他光锥或经验材料升级。
- **叠影 (Superimposition)**：消耗**同名光锥**提升被动效果，S1 ~ S5（叠影 1~5 阶）。只提升被动数值，不影响基础属性。叠影等级相加合并（S2 + S2 → S4）。
- **属性预算公式**（Lv.1 时，`x = HP/4.8, y = ATK/2.4, z = DEF/3`）：
  - 3★：x + y + z = 18
  - 4★：x + y + z = 23
  - 5★（多数）：x + y + z = 28
  - 5★（黑塔商店兑换）：x + y + z = 26

### 0.4 遗器 (Relic)

角色装备的「防具」。分两类，共 6 个部位：

| 类型 | 中文俗称 | 部位数 | 部位 | 套装效果 | 获取途径 |
|------|---------|-------|------|---------|---------|
| **Cavern Relic** | 外圈 | 4 | 头部 / 手部 / 躯干 / 脚部 | 2 件套 + 4 件套 | 凝滞虚空（侵蚀隧廊） |
| **Planar Ornament** | 位面饰品 / 内圈 | 2 | 位面球 / 连结绳 | 仅 2 件套 | 模拟宇宙 / 差分宇宙 |

#### 主词条 (Main Stat)

每个部位有固定的主词条类型池：

| 部位 | 主词条选项 |
|------|----------|
| 头部 | 生命值（固定） |
| 手部 | 攻击力（固定） |
| 躯干 | 生命%/攻击%/防御%/效果命中/治疗加成/暴击率/暴击伤害 |
| 脚部 | 生命%/攻击%/防御%/速度 |
| 位面球 | 生命%/攻击%/防御%/7 种属性伤害提高 |
| 连结绳 | 生命%/攻击%/防御%/击破特攻/能量恢复效率 |

#### 副词条 (Sub Stats)

- 最多 4 条副词条
- **不能与主词条同类型**（头部主词条是生命值，副词条不会出生命值，但可以出生命%）
- 每强化 3 级：未满 4 条时新增一条；满 4 条后随机强化一条已有副词条
- 初始值和每次强化增量分 3 档（低/中/高），随机选取

#### 稀有度

| 稀有度 | 等级上限 | 初始副词条数 |
|-------|---------|------------|
| 5★ | +15 | 3 ~ 4 |
| 4★ | +12 | 2 ~ 3 |
| 3★ | +9 | 1 ~ 2 |

### 0.5 角色养成概览

| 系统 | 说明 |
|------|------|
| **等级** | 上限 80 级，升级提升基础属性（HP/ATK/DEF/SPD） |
| **行迹 (Trace)** | 技能升级树，消耗材料提升技能等级、解锁额外能力（3 个大节点）和属性加成 |
| **星魂 (Eidolon)** | 抽到重复角色解锁，共 6 层（E1~E6），每层强化一个技能或解锁新机制 |
| **光锥叠影** | 见 §0.3 |

### 0.6 战斗基础属性

| 属性 | 英文 | 说明 |
|------|------|------|
| 生命上限 | Max HP | 决定角色能承受的伤害量 |
| 攻击力 | ATK | 伤害公式的核心乘数 |
| 防御力 | DEF | 减少受到的伤害 |
| 速度 | SPD | 决定行动序中的行动频率（详见 [03_action_sequence.md](03_action_sequence.md)） |
| 暴击率 | CRIT Rate | 造成暴击的概率 |
| 暴击伤害 | CRIT DMG | 暴击时额外增加的伤害倍率 |
| 击破特攻 | Break Effect | 提升弱点击破后的击破伤害（详见 [04_break_system.md](04_break_system.md)） |
| 效果命中 | Effect Hit | 提升施加 debuff 的成功率 |
| 效果抵抗 | Effect RES | 降低被施加 debuff 的概率 |
| 能量恢复效率 | Energy Regen | 提升每次行为获得的能量 |
| 治疗加成 | Outgoing Healing Boost | 提升治疗量 |
| 嘲讽值 | Taunt | 决定被敌人选为目标概率（详见 [10_taunt_system.md](10_taunt_system.md)） |
| 欢愉度 | Elation | 欢愉命途专属面板属性，影响欢愉伤害（详见 [08_elation_system.md](08_elation_system.md)） |

---
