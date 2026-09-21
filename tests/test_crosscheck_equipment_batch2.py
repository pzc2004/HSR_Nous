"""L3 装备级对拍·残部扫荡波（BACKLOG B22 扩展②续二）：首批 6+4（equipment.py）与批量波
25+14（equipment_batch.py）之后的专光扫荡——本批 22 光锥（全 5star 专光，按载体摊开：
毁灭·白厄 8 / 虚无·黄泉 5 / 巡猎·真理 4 / 智识·黑塔 3 / 丰饶·罗刹 1 / 存护·杰帕德 1），
每件等式场景三方比对（我方引擎 vs 对方 vs 手算，rel_tol 1e-4）+ 结构差钉倍数。

载体（映射表现成，见各源文件）：白厄 1408（毁灭）/黄泉 1308（虚无）/真理医生 1305（巡猎）
/黑塔 1013（智识）/罗刹 1203（丰饶——终结技 2.0 虚数，常量自 legacy_1300 复用）/杰帕德
1104（存护——Grit 防转攻，常量自 legacy_1000 复用）。裁判链路与统一口径同前两批
（driver 头注 + 首批 docstring）；本文件只增映射表与场景。对方侧光锥属性段（对方控制器
不承载的 properties）一律钉进 attacker.*

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
--- 毁灭（白厄 1408；面板 = 白值×1.5 行迹 atkBuffStacks=1 走对方角色条件件）---
23002 无可取代的东西 S1——属性段 ATK+24%（对方钉 atk 面板，ATK_P×白值口径）
（无开关）常驻 atk_pct 24%    on_battle_start 常驻 modifier               普攻比等
dmgBuff（true）             on_kill/受击 钩【增伤 24% 1回合+触发锁】+治疗   杀 1 后普攻比等；
                            （治疗=atk×8% 官方攻击口径——我方状态锚单钉）  当次击杀段钉 S1
23009 到不了的彼岸 S1——属性段 CR+18%/HP+18%（对方钉 cr/hp 面板）
dmgBuff（true）             受击/on_hp_decrease(drain/set_hp) 钩【增伤     手发耗血事件后
                            24%】+攻击后解除（on_action 段后摘=当次自吃）  普攻比等
23014 此身为剑 S1——属性段 CD+20%（对方钉 cd）
eclipseStacks 0-3（3）      队友受击/耗血叠层 stat_exprs all_dmg 14%×N     手发队友受击 @1/@3
maxStackDefPen（true）      满层 enable_if def_pen 12%（面板读取即重估）    层比等；@3 带穿透
23015 比阳光更明亮的 S1——属性段 CR+18%（对方钉 cr）
dragonsCallStacks 0-2（2）  on_action 普攻叠层 stat_exprs atk_pct 18%×N     第 2/3 发普攻 @1/@2
                            （+energy_regen 6%×N 无伤害读出随挂不测）    层比等
23025 梦应归于何处 S1——属性段 BE+60%（对方钉 be 面板）
routedVulnerability（true） on_break 钩目标【击破易伤 24%】hit_condition   当次击破段自吃
                            break（先于结算——当次自吃）+溃败减速 20%        vs 手算；击破后
                            （无伤害读出）                                 直伤钉 S3
23039 血火啊，燃烧前路 S1——属性段 HP+18%（对方钉 hp 面板）
skillUltDmgBoost（true）    常驻 scoped 件 all_dmg 30%（skill/ult）+      战技比等；耗血
                            on_action 耗血 6% 上限（floor 1）——阈值快照   6% 锚；额外 30%
                            >500 未达（白厄 HP 不够）DMG_BONUS 未挂        段双方同未挂列注
23044 黎明恰如此燃烧 S1——属性段 SPD+12（对方钉 spd 面板）
defPen（true）              常驻面板 def_pen 18%（=对方 DEF_PEN 开关）      普攻比等（穿透区）
dmgBuff（true）             on_ultimate 钩【烈阳 60% 1回合】               合成大招事件后
                            （tick owner_turn_start）                       普攻比等；当次前钉 S4
23045 没有回报的加冕 S1——属性段 CD+36%（对方钉 cd）
ultAtkBoost（true）         on_ultimate 钩【攻击 40% 2回合】               合成大招事件后
energyAtkBuff（true）       同钩第二件：max_energy≥300 闸——白厄 max_energy  普攻比等；能量闸
                            =0 两侧同灭（对方读 context.baseEnergy=0）     两侧同灭列注
--- 虚无（黄泉 1308）---
23022 重塑时光之忆 S1——属性段 EHR+40%（对方钉 effect_hit，无直伤消费=面板锚）
prophetStacks 0-4（4）      先知叠层——**整段待收**（fixture 仅挂 EHR 面板件，         基线比等；
                            ATK_P 5%/层+DoT 无视防御 7.2%/层未收编在案）  钉 4 层钉 S5
23024 行于流逝的岸 S1——属性段 CD+36%（对方钉 cd）
emptyBubblesDebuff（true）  after_being_hit 首段挂【泡影】→ on_hp_decrease   第 2 击直伤+
                            钩真伤段 24%×命中额（DoT 不暴击同族真伤直写）  真伤合计比等；
                            （对方=BOOST 24% 全局+ULT 24% 近似——合计等价）  首击钉 S6
23035 长路终有归途 S1——属性段 BE+60%（对方钉 be 面板）
breakVulnerabilityStacks    on_break 钩目标【焚灼】击破易伤 18%×N（钳 2；   BE 面板锚+击破段
0-2（2）                    hit_condition break，先于结算=当次自吃）——@2 层  vs 手算（当次自
                            不可达（二次击破韧性不回填）在案               吃 18%）；直伤钉
                                                            S7（对方 BREAK
                                                            scoped VULN 对直伤不可见两侧同）
23043 谎言在风中飘扬 S1——属性段 SPD+18%（对方钉 spd 面板=白值×1.18）
defPen（true）              after_being_hit 首段全体【茫然】def-16% 2回合   第 2 次命中比等；
additionalDefPen（true）    同钩 SPD≥170 追加【失窃】def-8%（$self.spd      首击钉 S8；高速
                            活读面板）                                   档注入比等 100/176
23050 勿忘她的火焰 S1——属性段 BE+60%（对方钉 be 面板）
breakDmgBuff（true）        常驻 dmg_break_dmg_boost 32%（击破池；自身+     击破段 vs 手算
                            最高 BE 队友——单人队幂等）——对方 BREAK 标签     ×1.32；直伤
                            BOOST 对直伤不可见（kind=character 无击破段）   比等列注
--- 巡猎（真理医生 1305；面板 = 白值×1.28 行迹）---
23012 如泥酣眠 S1——属性段 CD+30%（对方钉 cd）
missedCritCrBuff（false）   after_being_hit（非暴击，期望模式 is_critical    第 2 发普攻比等
                            恒 false——口径在案非病）钩【梦醒】CR+36%       （@梦醒）
23016 烦恼着，幸福着 S1——属性段 CR+18%（对方钉 cr）
（无开关）追击增伤 30%      常驻 dmg_follow_up_dmg_boost（=对方 FUA 标签     追击首段比等
                            BOOST 无条件件）                                （targetTameStacks=0）
targetTameStacks 0-2（2）   on_action 追击钩目标【温驯】叠层（hook 追击无     手发等价事件补发
                            on_action 事件——通道缺口在案，wave-1 合成先例）  on_action 后第 3 次
                            → after_being_hit 挂【温驯·暴伤】CD 12%×N        追击 @1 层比等
23031 我将，巡征追猎 S1——属性段 CR+15%（对方钉 cr）
luminfluxUltStacks 0-2（2） on_action 追击叠【流光】（on_turn_end -1）——     基线比等；
                            **增伤段待收**（流光件无 stat 承载——ULT 无视     钉 2 层大招钉 S9
                            防御 27%/层未收编在案）
23046 理想燃烧的地狱 S1——属性段 CR+16%（对方钉 cr）
spAtkBuff（true）           消耗战技点攻击 40%——**待收**（param_3 绑定未挂，  钉 true 钉 S10
                            fixture 注释在案）
atkBuffStacks 0-4（4）      on_action 战技叠层 stat_exprs atk_pct 10%×N      第 5 发战技 @4 层
                            （钳 4）                                      比等
--- 智识（黑塔 1013）---
23018 片刻，留在眼底 S1——属性段 CD+36%（对方钉 cd）
maxEnergyDmgBoost（true）   常驻 dmg_ultimate_dmg_boost=min(能量上限,180)×    大招比等
                            0.36%/点（黑塔上限 110 → 39.6%——对方 ULT BOOST
                            同式读 context.baseEnergy 场景槽）
23028 偏偏希望无价 S1——属性段 CR+16%（对方钉 cr）
fuaDmgBoost（true）         常驻 stat_exprs 追击增伤=min(max((CD-1.2)        自然 CD 双方 0 层
                            //0.2,0),4)×12%（面板读取即重估）——对方同式      ——对方 floor 未
                            但 **floor 未钳零下界（对方病 B-NEW1）**：CD<120%  钳零 -48%（病钉
                            时对方给负增伤（CD 0.5 → -48%），我方钳零正确    S11）；CD 2.0 档
                                                            双方 4 层 48% 比等
ultFuaDefShred（true）      追击/终结技无视防御 20%——**待收**（fixture 未挂  钉 true 钉 S12
                            在案；对方默认开——场景一律显式钉 false）
23041 生命当付之一炬 S1（properties 全空——无属性段）
（无开关）回合开始回能 10   on_turn_start 钩 gain_energy（装备者过滤）        我方状态锚单钉
defPen（true）              after_being_hit（source=装备者）目标降防 12%      第 2 次命中比等；
                            2回合（replace——官方「同类效果无法叠加」）       首击钉 S13
dmgBoost（true）            对「装备者添加的弱点」目标增伤 60%——**待收**       钉 true 钉 S14
                            （has_weakness 未实现+弱点来源归属通道缺，双缺口
                            fixture 注释在案；对方无条件 BOOST 近似）
--- 丰饶（罗刹 1203；面板 = 白值×1.28 行迹；终结技 2.0 虚数）---
23032 唯有香如故 S1——属性段 BE+60%（对方钉 be 面板）
woefreeState（true）        after_being_hit（终结技命中怪物）挂【忘忧】易伤     第 2 次命中比等
additionalVulnerability     param_2 10%；BE≥150% 追加 param_4 8%（$self.      （10% 档）；当次
（true）                    break_effect 活读面板——注入 0.9 上 1.5 档）        大招钉 S15；
                                                            高档 18% 分支比等
--- 存护（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）---
23005 制胜的瞬间 S1——属性段 DEF+24%/EHR+24%（对方钉 def/ehr 面板）
selfAttackedDefBuff         after_being_hit（自身）挂 DEF+24% 1回合             受击后普攻比等
（true）                    （Grit 放大进 ATK=白值+0.35×DEF——双方同链）；        （DEF 1.605 档）；
                            常驻 aggro_boost 嘲讽值（无伤害读出随挂不测）      受击前钉 S16

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）
===========================================================================
S1  23002 增伤窗口（我方 on_kill 结算后挂=击杀段不吃；对方开关恒开）→ 当次击杀段 1.24
S2  23025 击破易伤无窗口差——我方 on_break 先于击破结算（engine 主序 on_break→
    break_damage 在案），当次击破段自吃 24% 易伤 ≡ 对方恒开档语义；唯作用域差见 S3
S3  23025 易伤作用域（我方 hit_condition break 限定 vs 对方 VULNERABILITY 全局近似）
    → 击破后直伤 1.24
S4  23044 烈阳窗口（我方 on_ultimate 结算后挂=当次及之前不吃；对方恒开）→ 大招前普攻 1.6
S5  23022 先知叠层（我方整段待收在案）→ 钉 4 层：对方/我方 = 1.2（ATK_P 0.20 白值换算）
S6  23024 泡影窗口（我方首击挂标=首击无真伤段；对方恒开）→ 首击 1.24
S7  23035 焚灼无窗口差——同 S2（on_break 先于结算当次自吃 18% ≡ 对方 stacks=1 档）；
    对方 kind=character 不出击破段 → 击破段我方 vs 手算单钉（×1.18 自证）
S8  23043 茫然窗口（我方首段后挂=首击不吃；对方 DEF_PEN 恒开）→ 首击 (100/184)/0.5
    = 100/92 ≈ 1.086957
S9  23031 流光增伤段（我方待收——流光件无 stat 承载）→ 钉 2 层大招：
    对方/我方 = (100/146)/0.5 = 100/73 ≈ 1.369863
S10 23046 耗点增伤段（我方待收——param_3 绑定未挂）→ 对方/我方 = 1.68/1.28 = 1.3125
S11 23028 对方病（B-NEW1）：floorSafe((CD-1.2)/0.2) 未钳零下界——CD<120% 负增伤
    （自然 CD 0.5 → -48%），我方 min(max(..,0),4) 钳零正确 → 对方/我方 = 0.52
S12 23028 追击/终结技无视防御段（我方待收在案）→ 钉 true（CD 2.0 档）：
    对方/我方 = (100/180)/0.5 = 10/9 ≈ 1.111111
S13 23041 降防窗口（我方 after_being_hit 结算后挂=首击不吃；对方 DEF_PEN 恒开）
    → 首击 (100/188)/0.5 = 100/94 ≈ 1.063830
S14 23041 弱点增伤段（我方待收——has_weakness 双缺口在案）→ 对方/我方 = 1.6
S15 23032 忘忧窗口（我方 after_being_hit 结算后挂=当次大招不吃；对方 VULNERABILITY
    恒开）→ 当次大招 1.10
S16 23005 受击防御窗口（我方 after_being_hit 结算后挂=受击前不吃；对方 DEF_P 恒开）
    → 受击前普攻 (w_atk+0.35×1.605×w_def)/(w_atk+0.35×1.365×w_def) ≈ 1.064950
    （Grit 放大非整数倍——双方 ATK 面板回显自证）

真病清单（本波新发现，均对方侧/external 只读报回）：
- B-NEW1（23028）：见 S11——对方 YetHopeIsPriceless floor 未钳零下界，CD<120% 负增伤。

跳过清单（缺读出端/载体未立，不硬造）：
- 23030 落日时起舞（毁灭·追击叠层 36%/层）：需毁灭追击载体——白厄无追击读出（变身
  pyre_counter 链路重），云璃/克拉拉反击载体常量未立——未拍
- 23032 唯有香如故已拍（罗刹载体——见映射表丰饶节）；23008 棺的回响（丰饶·大招后
  速度/回能——无伤害读出）/23013 时节不居（治疗量转伤害——HealTally 寄存器链重）/
  23017 惊魂夜（妖火=受疗者外最高攻击——单人队无落点，对方滑条无条件=建模近似）/
  23029/23042（丰饶专光）：丰饶残部未拍（治疗/护盾读出 fua_heal 先例可接，下波续）
- 23023 命运从未公平（存护·追击挂惊惶——需砂金载体，常量未立+盲注链重）/24002 记忆的
  质料（存护·护盾量+减伤——无伤害读出）/24006（欢愉）：存护/欢愉残部未拍（23005 已拍
  ——见映射表存护节）
- 23003/23019/23021/23026/23038/23048/23051（同谐专光）：团队 buff 链需 teammates
  真队友镜像+我方队友在场——链路重，未拍
- 23040 让告别更美一些（记忆·遐蝶专光）：忆灵多实体链重（死龙 HP 缩放），未拍
- 遗器残部（101 过客/103 圣骑士/106 铁卫/107 火匠/118 钟表匠/119 铁骑/121 司铎/
  124 诗人/125 女武神/126 船长/128 隐士/129 魔法少女/130 卜者）：107 需火系智识载体
  （姬子常量未立）、119 击破族读出同 23050 受限、124/130 速度档 driver c.a 缺口在案、
  101/103/106/118 无伤害读出、125/126/128/129/121 双方机制核对未及——本波未拍
- 位面饰品 301-328：driver p2t 未接入（在案）——全部未拍
- 23024 终结技额外真伤段（param_3 24%）：黄泉大招多段+结链重，基本段已拍覆盖机制——
  列注未拍
"""
from __future__ import annotations

import pytest

# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    AC_ATK, HT_ATK, Z, _POLICY, _cast, _hit_amounts, _inject, _make_logged,
)
from tests.test_crosscheck_equipment import (  # noqa: F401
    RT_ATK, RT_CD, RT_CR, _acheron_opt, _compiled, _herta_opt, _member_build,
    _ratio_opt, _ult,
)
from tests.test_crosscheck_equipment_batch import (  # noqa: F401
    _eff, _eff_spd, _kill_enemies, _lc, _low_hp_enemy, _fragile_toughness, _pha_opt,
)
from tests.test_crosscheck_team_phainon import (  # noqa: F401
    PH_ATK, PH_CD, PH_CR, PH_SPD, Z_PH,
)
from tests.test_crosscheck_legacy_1300 import (  # noqa: F401
    LC_ATK_W, LC_CZ, _opt_luocha,
)
from tests.test_crosscheck_legacy_1000 import (  # noqa: F401
    GP_ATK_W, GP_CZ, GP_DEF_W, GP_ICE, _opt_gepard,
)

# ---------------------------------------------------------------------------
# 口径常数（本批新增；载体既有常数从各波文件复用）
# ---------------------------------------------------------------------------

# 光锥白值（fixture base_stats 终审值；仅 atk 进手算锚）
LC23002_ATK = 582.12
LC23009_ATK = 582.12
LC23014_ATK = 582.12
LC23015_ATK = 635.04
LC23025_ATK = 476.28
LC23039_ATK = 476.28
LC23044_ATK = 687.96
LC23045_ATK = 582.12
LC23022_ATK = 582.12
LC23024_ATK = 635.04
LC23035_ATK = 476.28
LC23043_ATK = 582.12
LC23050_ATK = 529.2
LC23012_ATK = 582.12
LC23016_ATK = 582.12
LC23031_ATK = 635.04
LC23046_ATK = 582.12
LC23018_ATK = 582.12
LC23028_ATK = 582.12
LC23041_ATK = 582.12
LC23032_ATK = 529.2
LC23005_ATK, LC23005_DEF = 476.28, 595.35

# 击破基准（我方口径：3767.5533×scaling×(0.5+maxToughness/40)×def0.5——
# 对方 kind=character 不出击破段，击破段一律我方 vs 手算单钉；物理 scaling=2.0）
BREAK_BASE_10 = 3767.5533 * (0.5 + 10 / 40) * 0.5          # 雷/冰 scaling=1.0，韧性 10
BREAK_BASE_10_PHY = BREAK_BASE_10 * 2.0                    # 物理 scaling=2.0


def _break_amounts(log, source):
    """击破段日志（reason='break' 域——_hit_amounts 只收 'hit' 域）."""
    return [e["amount"] for e in log
            if e.get("reason") == "break" and e.get("source") == source]


def _hits_of(log, *, source, action_type):
    """按 action_type 过滤的直伤段（'hit' 域——skill/follow_up/basic 分流）."""
    return [e["amount"] for e in log
            if e.get("reason") == "hit" and e.get("source") == source
            and e.get("action_type") == action_type]


def _emit(eng, event, payload):
    """合成事件补发（wave-1 先例——hook 通道缺口处的等价事件手发）."""
    eng.bus.emit(event, payload, eng.state)


def _member_build2(lc: str, teammate: str):
    """双成员 build（23014 月蚀需队友受击载体——队友只承事件不出手）."""
    return {"build": {"team": [
        {"character_template": "1408", "level": 80,
         "light_cone_template": lc, "light_cone": {"superimposition": 1}},
        {"character_template": teammate, "level": 80},
    ], "policy": _POLICY}}


# ===========================================================================
# 光锥对拍——毁灭载体（白厄 1408）
# ===========================================================================

class TestLC23002SomethingIrreplaceable:
    """无可取代的东西 S1（白厄）：常驻攻击 24%（属性段）+ 击杀/受击增伤 24%."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23002"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23002_ATK
        atk = white * 1.24                      # LC 属性段（对方钉面板）
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23002_ATK, extra_attacker={"atk": atk},
            equipment=_lc("23002", "Destruction", {"dmgBuff": False})))

        hand = 1.0 * white * 1.74 * Z_PH         # 面板 = 白值×(1.5 行迹+0.24 属性段)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 24% 钩 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.74, rel=REL_TOL), (
            "对方 ATK_P 0.5（行迹条件件）×白值 + 钉死面板属性段")

    def test_kill_dmg_buff(self, optimizer_driver):
        """击杀跨线：增伤在 on_kill 结算后挂（当次击杀段不吃——S1 钉）→ 随后普攻吃."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="23002"), "physical",
            enemies=_kill_enemies("physical")))
        eng.state.actors["1408"].current_hp = 1000.0
        _cast(eng, "1408", "140801", target="e2")   # 击杀 → 治疗 + 增伤 24% + 触发锁
        assert "LC_23002_DMG_BUFF" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801", target="e1")
        ours = _hit_amounts(log, source="1408", target="e1")
        white = PH_ATK + LC23002_ATK
        atk = white * 1.24
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23002_ATK, extra_attacker={"atk": atk},
            equipment=_lc("23002", "Destruction", {"dmgBuff": True})))

        hand = 1.0 * white * 1.74 * Z_PH * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方击杀后普攻（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        # 治疗锚：官方攻击口径——回复 = 面板 atk×8%（我方状态锚单钉）
        assert eng.state.actors["1408"].current_hp == pytest.approx(
            1000.0 + white * 1.74 * 0.08, rel=REL_TOL)

    def test_kill_window_divergence(self, optimizer_driver):
        """S1 结构差：对方 dmgBuff 恒开含当次击杀段（建模近似）；我方 on_kill 结算后挂
        → 当次击杀段 对方/我方 = 1.24."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="23002"), "physical",
            enemies=_kill_enemies("physical")))
        _cast(eng, "1408", "140801", target="e2")
        ours = _hit_amounts(log, source="1408", target="e2")[0]
        white = PH_ATK + LC23002_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23002_ATK, extra_attacker={"atk": white * 1.24},
            equipment=_lc("23002", "Destruction", {"dmgBuff": True})))

        assert ours == pytest.approx(1.0 * white * 1.74 * Z_PH, rel=REL_TOL), (
            "我方当次击杀段（无增伤）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.24, rel=REL_TOL)


class TestLC23009UnreachableSide:
    """到不了的彼岸 S1（白厄）：常驻 CR 18%/HP 18%（属性段）+ 耗血/受击增伤 24%."""

    def test_drain_dmg_buff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23009"), "physical"))
        _emit(eng, "on_hp_decrease", {"target": "1408", "reason": "drain"})
        assert "LC_23009_UNREACHABLE_DMG" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")               # 当次自吃（on_action 段后摘）
        assert "LC_23009_UNREACHABLE_DMG" not in eng.state.actors["1408"].modifiers
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23009_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23009_ATK, extra_attacker={"cr": PH_CR + 0.18},
            equipment=_lc("23009", "Destruction", {"dmgBuff": True})))

        hand = 1.0 * white * 1.5 * 0.5 * 0.9 * (1 + 0.35 * 0.873) * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方耗血后普攻（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert _eff(eng, "1408")["crit_rate"] == pytest.approx(0.35, rel=REL_TOL), (
            "我方常驻 CR 18% 面板")


class TestLC23014IShallBeMyOwnSword:
    """此身为剑 S1（白厄+黑塔队友）：CD 20%（属性段）+ 月蚀叠层 14%/层 + 满层穿透 12%."""

    def test_eclipse_one_stack(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build2("23014", "1013"), "physical"))
        _emit(eng, "after_being_hit", {"target": "1013", "source": "e1"})
        _cast(eng, "1408", "140801")
        assert "LC_23014_ECLIPSE" not in eng.state.actors["1408"].modifiers, "攻击后解除"
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23014_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23014_ATK, extra_attacker={"cd": PH_CD + 0.2},
            equipment=_lc("23014", "Destruction", {
                "eclipseStacks": 1, "maxStackDefPen": False})))

        hand = 1.0 * white * 1.5 * 0.5 * 0.9 * (1 + 0.17 * 1.073) * 1.14
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 @1 层月蚀 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_eclipse_full_def_pen(self, optimizer_driver):
        """满 3 层：增伤 42% + 无视防御 12%（enable_if 面板重估——攻击后摘层联动关闭）."""
        eng, log = _make_logged(_compiled(
            _member_build2("23014", "1013"), "physical"))
        for _ in range(3):
            _emit(eng, "after_being_hit", {"target": "1013", "source": "e1"})
        assert eng.state.actors["1408"].modifiers["LC_23014_ECLIPSE"].stacks == 3
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23014_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23014_ATK, extra_attacker={"cd": PH_CD + 0.2},
            equipment=_lc("23014", "Destruction", {
                "eclipseStacks": 3, "maxStackDefPen": True})))

        hand = 1.0 * white * 1.5 * (100 / 188) * 0.9 * (1 + 0.17 * 1.073) * 1.42
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方满层月蚀（42%+穿透）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 188, rel=REL_TOL), "对方满层 DEF_PEN 12% 穿透区"


class TestLC23015BrighterThanTheSun:
    """比阳光更明亮的 S1（白厄）：常驻 CR 18%（属性段）+ 普攻叠龙吟 18% 攻击/层."""

    def test_dragons_call_stacks(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23015"), "physical"))
        for _ in range(3):
            _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23015_ATK
        theirs2 = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23015_ATK, extra_attacker={"cr": PH_CR + 0.18},
            equipment=_lc("23015", "Destruction", {"dragonsCallStacks": 2})))
        theirs1 = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23015_ATK, extra_attacker={"cr": PH_CR + 0.18},
            equipment=_lc("23015", "Destruction", {"dragonsCallStacks": 1})))

        # 命中序 = [①@0, ②@1层, ③@2层]（层在行动后挂=当次不吃）
        hand2 = 1.0 * (white * 1.5 + white * 0.18) * 0.5 * 0.9 * (1 + 0.35 * 0.873)
        hand3 = 1.0 * (white * 1.5 + white * 0.36) * 0.5 * 0.9 * (1 + 0.35 * 0.873)
        assert ours == pytest.approx(
            [1.0 * white * 1.5 * 0.5 * 0.9 * (1 + 0.35 * 0.873), hand2, hand3],
            rel=REL_TOL), "我方叠层斜坡 vs 手算"
        assert ours[1] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL), (
            "第 2 发（@1 层）双方互对")
        assert ours[2] == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL), (
            "第 3 发（@2 层）双方互对")
        assert theirs2["stats"]["atk"] == pytest.approx(white * 1.86, rel=REL_TOL), (
            "对方 ATK_P 0.36 白值换算通道")


class TestLC23025WhereaboutsShouldDreamsRest:
    """梦应归于何处 S1（白厄）：常驻 BE 60%（属性段）+ 击破后目标击破易伤 24%."""

    def test_break_and_follow_up(self, optimizer_driver):
        """当次击破段：我方 on_break 先于击破结算（当次自吃 24% 易伤——engine 主序
        on_break→break_damage 在案）；对方钉 off + kind=character 不出击破段——
        击破段我方 vs 手算单钉；击破后直伤比等（韧性区 1.0 对齐，开关 off）."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="23025"), "physical",
            enemies=_fragile_toughness("physical")))
        _cast(eng, "1408", "140801")   # 削韧 10 → 当次击破
        assert "LC_23025_ROUTED_VULN" in eng.state.actors["e1"].modifiers
        _cast(eng, "1408", "140801")   # 击破后普攻
        ours = _hit_amounts(log, source="1408")
        breaks = _break_amounts(log, "1408")
        white = PH_ATK + LC23025_ATK

        assert breaks[0] == pytest.approx(
            BREAK_BASE_10_PHY * 1.6 * 1.24, rel=REL_TOL), (
            "我方当次击破段（BE 0.6+溃败易伤 24% 当次自吃）vs 手算")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23025_ATK, extra_attacker={"be": 0.6},
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": True,
                   "count": 1},
            equipment=_lc("23025", "Destruction", {"routedVulnerability": False})))
        hand2 = 1.0 * white * 1.5 * 0.5 * 1.0 * (1 + PH_CR * PH_CD)
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方击破后普攻 vs 手算"
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "击破后直伤双方比等（开关 off）")
        assert _eff(eng, "1408")["break_effect"] == pytest.approx(0.6, rel=REL_TOL)

    def test_scoped_vs_global_divergence(self, optimizer_driver):
        """S3 结构差：对方 VULNERABILITY 全局（直伤也吃）；我方 hit_condition break
        限定（直伤不吃）→ 击破后直伤 对方/我方 = 1.24."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="23025"), "physical",
            enemies=_fragile_toughness("physical")))
        _cast(eng, "1408", "140801")
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")[1]
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23025_ATK, extra_attacker={"be": 0.6},
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": True,
                   "count": 1},
            equipment=_lc("23025", "Destruction", {"routedVulnerability": True})))
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.24, rel=REL_TOL)


class TestLC23039FlameOfBlood:
    """血火啊，燃烧前路 S1（白厄）：HP 18%（属性段）+ 战技/终结技增伤 30% + 耗血 6%."""

    def test_skill_dmg_and_drain(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23039"), "physical"))
        st = eng.state.actors["1408"]
        hp0 = st.current_hp
        _cast(eng, "1408", "140802")   # 战技：30% 增伤 + 耗血 6% 上限
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23039_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "skill", lc_atk=LC23039_ATK,
            equipment=_lc("23039", "Destruction", {"skillUltDmgBoost": True})))

        hand = 3.0 * white * 1.5 * Z_PH * 1.3
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技（增伤 30%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        # 耗血锚：6%×现上限（上限含本锥 hp_pct 18%——额外增伤阈值 500 未达 DMG_BONUS
        # 未挂，双方同档列注）
        assert "LC_23039_DMG_BONUS" not in st.modifiers
        assert st.current_hp == pytest.approx(hp0 - hp0 * 1.18 * 0.06, rel=REL_TOL), (
            "我方耗血 6% 上限 vs 手算")


class TestLC23044ThusBurnsTheDawn:
    """黎明恰如此燃烧 S1（白厄）：常驻 SPD+12/DEF_PEN 18%（面板）+ 大招后烈阳 60%."""

    def test_permanent_def_pen(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23044"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23044_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23044_ATK, extra_attacker={"spd": PH_SPD + 12},
            equipment=_lc("23044", "Destruction", {"defPen": True, "dmgBuff": False})))

        hand = 1.0 * white * 1.5 * (100 / 182) * 0.9 * (1 + PH_CR * PH_CD)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻穿透 18% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 182, rel=REL_TOL)
        assert _eff_spd(eng, "1408") == pytest.approx(PH_SPD + 12, rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(PH_SPD + 12, rel=REL_TOL)

    def test_blazing_sun_after_ult(self, optimizer_driver):
        """合成 on_ultimate（白厄大招=变身技无伤害段——事件等价补发，wave-1 先例）
        → 烈阳 60% → 普攻比等（对方 dmgBoost 开关）."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23044"), "physical"))
        _emit(eng, "on_ultimate", {"source": "1408"})
        assert "LC_23044_BLAZING_SUN" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23044_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23044_ATK, extra_attacker={"spd": PH_SPD + 12},
            equipment=_lc("23044", "Destruction", {"defPen": True, "dmgBuff": True})))

        hand = 1.0 * white * 1.5 * (100 / 182) * 0.9 * (1 + PH_CR * PH_CD) * 1.6
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方烈阳后普攻（+60%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_pre_ult_window_divergence(self, optimizer_driver):
        """S4 结构差：对方 dmgBuff 恒开（烈阳前普攻也吃=建模近似）；我方 on_ultimate
        结算后挂 → 大招前普攻 对方/我方 = 1.6."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23044"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")[0]
        white = PH_ATK + LC23044_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23044_ATK, extra_attacker={"spd": PH_SPD + 12},
            equipment=_lc("23044", "Destruction", {"defPen": True, "dmgBuff": True})))

        assert ours == pytest.approx(
            1.0 * white * 1.5 * (100 / 182) * 0.9 * (1 + PH_CR * PH_CD), rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.6, rel=REL_TOL)


class TestLC23045AThanklessCoronation:
    """没有回报的加冕 S1（白厄）：常驻 CD 36%（属性段）+ 大招后攻击 40%（能量 300 闸两侧同灭）."""

    def test_ult_atk_buff(self, optimizer_driver):
        """合成 on_ultimate → 攻击 40% 2回合 → 普攻比等；第二件能量闸：白厄
        max_energy=0（火种槽）→ 我方 max_energy≥300 不达成 ≡ 对方 baseEnergy=0 闸灭."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="23045"), "physical"))
        _emit(eng, "on_ultimate", {"source": "1408"})
        assert "LC_23045_ATK_FIRST" in eng.state.actors["1408"].modifiers
        assert eng.state.actors["1408"].current_energy == 0.0, (
            "能量闸两侧同灭（我方 max_energy=0 锚）")
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC23045_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC23045_ATK, extra_attacker={"cd": PH_CD + 0.36},
            equipment=_lc("23045", "Destruction", {
                "ultAtkBoost": True, "energyAtkBuff": True})))

        hand = 1.0 * (white * 1.5 + white * 0.4) * 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.36))
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方大招后普攻（+40%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.9, rel=REL_TOL), (
            "对方 ATK_P 0.40 白值换算通道（能量闸灭——无第二件）")


# ===========================================================================
# 光锥对拍——虚无载体（黄泉 1308）
# ===========================================================================

class TestLC23022ReforgedRemembrance:
    """重塑时光之忆 S1（黄泉）：EHR 40%（属性段面板锚）+ 先知叠层整段待收（S5 钉）."""

    def test_ehr_panel_baseline(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23022"), "thunder"))
        assert _eff(eng, "1308")["effect_hit"] == pytest.approx(0.40, rel=REL_TOL), (
            "我方 EHR 属性段（面板锚——直伤无消费）")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23022_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"effect_hit": 0.4},
            equipment=_lc("23022", "Nihility", {"prophetStacks": 0})))

        hand = 1.0 * white * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_prophet_stacks_divergence(self, optimizer_driver):
        """S5 结构差：先知叠层（ATK_P 5%/层+DoT 无视防御 7.2%/层）我方整段待收
        （fixture 仅 EHR 面板件在案）→ 钉 4 层：对方/我方 = 1.2."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23022"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC23022_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"effect_hit": 0.4},
            equipment=_lc("23022", "Nihility", {"prophetStacks": 4})))

        assert theirs["stats"]["atk"] == pytest.approx(white * 1.2, rel=REL_TOL), (
            "对方 ATK_P 0.20 白值换算通道")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.2, rel=REL_TOL)


class TestLC23024AlongThePassingShore:
    """行于流逝的岸 S1（黄泉）：CD 36%（属性段）+ 泡影真伤段 24%（对方 BOOST 近似）."""

    def test_mirage_fizzle_proc(self, optimizer_driver):
        """第 2 击：直伤（无增伤池）+ 真伤段 24%×命中额——合计 ≡ 对方 BOOST 24%
        （1.24×基数双方同值）；真伤段不暴击不吃增伤池（deal_true_damage 直写槽）."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23024"), "thunder"))
        _cast(eng, "1308", "130801")   # 首击挂泡影（结算后——当次无真伤段，S6 钉）
        assert "LC_23024_MIRAGE_FIZZLE" in eng.state.actors["e1"].modifiers
        _cast(eng, "1308", "130801")   # 第 2 击：泡影跳真伤
        hits = _hits_of(log, source="1308", action_type="basic")
        trues = [e["amount"] for e in log
                 if e.get("reason") == "hit" and e.get("source") == "1308"
                 and e.get("damage_type") == "true"]
        white = AC_ATK + LC23024_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"cd": 0.5 + 0.36},
            equipment=_lc("23024", "Nihility", {"emptyBubblesDebuff": True})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.05 * 0.86)
        assert hits[1] == pytest.approx(hand, rel=REL_TOL), "我方第 2 击直伤 vs 手算"
        assert trues[0] == pytest.approx(0.24 * hand, rel=REL_TOL), (
            "我方泡影真伤段（24%×命中额）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand * 1.24, rel=REL_TOL)
        assert hits[1] + trues[0] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "合计双方比等（1.24 同值异构）"

    def test_first_hit_window_divergence(self, optimizer_driver):
        """S6 结构差：对方 BOOST 恒开（首击即 1.24）；我方首击挂标=首击无真伤段
        → 首击 对方/我方 = 1.24."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23024"), "thunder"))
        _cast(eng, "1308", "130801")
        hits = _hits_of(log, source="1308", action_type="basic")
        trues = [e for e in log if e.get("damage_type") == "true"]
        assert trues == [], "首击无真伤段（泡影未挂——窗口锚）"
        white = AC_ATK + LC23024_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"cd": 0.5 + 0.36},
            equipment=_lc("23024", "Nihility", {"emptyBubblesDebuff": True})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.05 * 0.86)
        assert hits[0] == pytest.approx(hand, rel=REL_TOL), "我方首击（无真伤段）vs 手算"
        assert theirs["hits"][0]["damage"] / hits[0] == pytest.approx(1.24, rel=REL_TOL)


class TestLC23035LongRoadLeadsHome:
    """长路终有归途 S1（黄泉）：常驻 BE 60%（属性段）+ 击破后焚灼（击破易伤 18%/层）."""

    def test_break_charring(self, optimizer_driver):
        """当次击破段：我方 on_break 先于击破结算（当次自吃焚灼 18%——与对方 stacks=1
        档语义同向同值）；对方 kind=character 不出击破段——击破段我方 vs 手算单钉.
        直伤段比等（对方 BREAK-scoped VULN 对直伤不可见——两侧同锚）."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="23035"), "thunder",
            enemies=_fragile_toughness("thunder")))
        _cast(eng, "1308", "130801")   # 削韧 10 → 当次击破
        assert "LC_23035_CHARRING" in eng.state.actors["e1"].modifiers
        breaks = _break_amounts(log, "1308")
        hits = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23035_ATK

        assert breaks[0] == pytest.approx(
            BREAK_BASE_10 * 1.6 * 1.18, rel=REL_TOL), (
            "我方当次击破段（BE 0.6+焚灼 18% 当次自吃）vs 手算")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"be": 0.6},
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 1},
            equipment=_lc("23035", "Nihility", {"breakVulnerabilityStacks": 1})))
        hand = 1.0 * white * Z
        assert hits[0] == pytest.approx(hand, rel=REL_TOL), "我方直伤段 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 BREAK-scoped VULN 对直伤不可见（双方互对）")
        assert _eff(eng, "1308")["break_effect"] == pytest.approx(0.6, rel=REL_TOL)


class TestLC23043LiesAflutterInTheWind:
    """谎言在风中飘扬 S1（黄泉）：常驻 SPD 18%（属性段）+ 茫然 def-16%（+失窃 def-8%）."""

    def test_bamboozle_second_hit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23043"), "thunder"))
        _cast(eng, "1308", "130801")
        assert "LC_23043_BAMBOOZLE" in eng.state.actors["e1"].modifiers
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23043_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"spd": 101 * 1.18},
            equipment=_lc("23043", "Nihility", {
                "defPen": True, "additionalDefPen": True})))

        hand2 = 1.0 * white * (100 / 184) * 0.9 * 1.025
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方第 2 次命中（茫然）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 184, rel=REL_TOL)
        assert _eff_spd(eng, "1308") == pytest.approx(101 * 1.18, rel=REL_TOL)

    def test_first_hit_window_divergence(self, optimizer_driver):
        """S8 结构差：对方 DEF_PEN 恒开；我方 after_being_hit 结算后挂（首击不吃）
        → 首击 对方/我方 = (100/184)/0.5 = 100/92."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23043"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC23043_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"spd": 101 * 1.18},
            equipment=_lc("23043", "Nihility", {
                "defPen": True, "additionalDefPen": True})))

        assert ours == pytest.approx(1.0 * white * Z, rel=REL_TOL), "我方首击（无穿透）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(100 / 92, rel=REL_TOL)

    def test_theft_high_spd(self, optimizer_driver):
        """高速档：注入 spd_pct 0.52（面板 101×1.70=171.7≥170）→ 失窃追加 def-8%
        → 第 2 次命中 100/176 比等（对方 SPD≥170 追加档同闸）."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23043"), "thunder"))
        _inject(eng, "1308", "XC_SPD", {"spd_pct": 0.52})
        assert _eff_spd(eng, "1308") == pytest.approx(101 * 1.70, rel=REL_TOL)
        _cast(eng, "1308", "130801")
        assert "LC_23043_THEFT" in eng.state.actors["e1"].modifiers
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23043_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"spd": 101 * 1.70},
            equipment=_lc("23043", "Nihility", {
                "defPen": True, "additionalDefPen": True})))

        hand2 = 1.0 * white * (100 / 176) * 0.9 * 1.025
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方高速档（16%+8%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 176, rel=REL_TOL)


class TestLC23050NeverForgetHerFlame:
    """勿忘她的火焰 S1（黄泉）：常驻 BE 60%（属性段）+ 击破伤害提高 32%（击破池）."""

    def test_break_dmg_boost(self, optimizer_driver):
        """击破段 vs 手算 ×1.32（dmg_break_dmg_boost 击破池——当次即吃，双方常驻件）；
        直伤段比等（对方 BREAK 标签 BOOST 对直伤不可见；我方 scoped 同）."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="23050"), "thunder",
            enemies=_fragile_toughness("thunder")))
        _cast(eng, "1308", "130801")   # 削韧 10 → 当次击破
        breaks = _break_amounts(log, "1308")
        hits = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23050_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"be": 0.6},
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 1},
            equipment=_lc("23050", "Nihility", {"breakDmgBuff": True})))

        assert breaks[0] == pytest.approx(
            BREAK_BASE_10 * 1.6 * 1.32, rel=REL_TOL), "我方击破段（×1.32 池）vs 手算"
        hand = 1.0 * white * Z
        assert hits[0] == pytest.approx(hand, rel=REL_TOL), "我方直伤段 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 BREAK 标签 BOOST 对直伤不可见（双方互对）")
        assert _eff(eng, "1308")["break_effect"] == pytest.approx(0.6, rel=REL_TOL)
        # 自身+最高 BE 队友同 id 重挂幂等（单人队只一件——锚）
        assert sum(1 for m in eng.state.actors["1308"].modifiers
                   if m == "LC_23050_BREAK_DMG") == 1


# ===========================================================================
# 光锥对拍——巡猎载体（真理医生 1305；面板 = 白值×1.28 行迹）
# ===========================================================================

class TestLC23012SleepLikeTheDead:
    """如泥酣眠 S1（真理医生）：常驻 CD 36%（属性段）+ 未暴击梦醒 CR 36%."""

    def test_missed_crit_cr(self, optimizer_driver):
        """期望模式 is_critical 恒 false（口径在案非病）→ 首击后梦醒挂上 → 第 2 发吃."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23012"), "imaginary"))
        _cast(eng, "1305", "130501")
        assert "LC_23012_CRIT_RATE_BUFF" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        white = RT_ATK + LC23012_ATK
        theirs1 = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23012_ATK, cd=RT_CD + 0.30,
            equipment=_lc("23012", "Hunt", {"missedCritCrBuff": False})))
        theirs2 = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23012_ATK, cd=RT_CD + 0.30,
            equipment=_lc("23012", "Hunt", {"missedCritCrBuff": True})))

        hand1 = 1.0 * (white * 1.28) * 0.5 * 0.9 * (1 + RT_CR * 0.80)
        hand2 = 1.0 * (white * 1.28) * 0.5 * 0.9 * (1 + (RT_CR + 0.36) * 0.80)
        assert ours[0] == pytest.approx(hand1, rel=REL_TOL), "我方首击（无梦醒）vs 手算"
        assert theirs1["hits"][0]["damage"] == pytest.approx(hand1, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方第 2 发（梦醒 36%）vs 手算"
        assert theirs2["hits"][0]["damage"] == pytest.approx(hand2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL)
        assert theirs2["hits"][0]["breakdown"]["critMulti"] == pytest.approx(
            1 + (RT_CR + 0.36) * 0.80, rel=REL_TOL)


class TestLC23016WorrisomeBlissful:
    """烦恼着，幸福着 S1（真理医生）：常驻 CR 18%+追击增伤 30% + 温驯叠暴伤 12%/层."""

    def test_fua_boost_and_tame(self, optimizer_driver):
        """追击①（温驯未挂）比等；手发 on_action(follow_up) 补温驯（hook 追击无
        on_action 事件——通道缺口在案）；追击③ @1 层温驯·暴伤比等.
        归纳层并行：追击①@1 层/追击③@3 层（战技后挂——对方 summationStacks 逐场钉）."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23016"), "imaginary"))
        _cast(eng, "1305", "130502")   # 战技① → 追击①（归纳 1）
        _emit(eng, "on_action", {"actor": "1305", "action_type": "follow_up",
                                 "action_id": "130504", "target": "e1",
                                 "actor_type": "character"})
        assert "LC_23016_TAME" in eng.state.actors["e1"].modifiers
        _cast(eng, "1305", "130502")   # 战技② → 追击②（温驯·暴伤结算后挂=当次不吃）
        _cast(eng, "1305", "130502")   # 战技③ → 追击③（吃温驯·暴伤 12%）
        fuas = _hits_of(log, source="1305", action_type="follow_up")
        white = RT_ATK + LC23016_ATK

        theirs0 = run_optimizer(optimizer_driver, _ratio_opt(
            "fua", lc_atk=LC23016_ATK, cr=RT_CR + 0.18,
            conditionals={"summationStacks": 1},
            equipment=_lc("23016", "Hunt", {"targetTameStacks": 0})))
        theirs1 = run_optimizer(optimizer_driver, _ratio_opt(
            "fua", lc_atk=LC23016_ATK, cr=RT_CR + 0.18,
            conditionals={"summationStacks": 3},
            equipment=_lc("23016", "Hunt", {"targetTameStacks": 1})))

        # 追击①：归纳 1（cr+2.5%/cd+5%）+ 追击增伤 30%，无温驯暴伤
        hand1 = 2.7 * (white * 1.28) * 0.5 * 0.9 \
            * (1 + (RT_CR + 0.18 + 0.025) * (0.5 + 0.05)) * 1.30
        # 追击③：归纳 3（cr+7.5%/cd+15%）+ 温驯·暴伤 12%（cd+12%）
        hand3 = 2.7 * (white * 1.28) * 0.5 * 0.9 \
            * (1 + (RT_CR + 0.18 + 0.075) * (0.5 + 0.15 + 0.12)) * 1.30
        assert fuas[0] == pytest.approx(hand1, rel=REL_TOL), "我方追击①（30% 常驻）vs 手算"
        assert theirs0["hits"][0]["damage"] == pytest.approx(hand1, rel=REL_TOL)
        assert fuas[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert fuas[2] == pytest.approx(hand3, rel=REL_TOL), "我方追击③（温驯 12%）vs 手算"
        assert theirs1["hits"][0]["damage"] == pytest.approx(hand3, rel=REL_TOL)
        assert fuas[2] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)


class TestLC23031IVentureForthToHunt:
    """我将，巡征追猎 S1（真理医生）：常驻 CR 15%（属性段）+ 流光增伤段待收（S9 钉）."""

    def test_panel_baseline(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23031"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        white = RT_ATK + LC23031_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23031_ATK, cr=RT_CR + 0.15,
            equipment=_lc("23031", "Hunt", {"luminfluxUltStacks": 0})))

        hand = 1.0 * (white * 1.28) * 0.5 * 0.9 * (1 + (RT_CR + 0.15) * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 15% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_def_pen_divergence(self, optimizer_driver):
        """S9 结构差：流光增伤段（ULT 无视防御 27%/层）我方待收（流光件无 stat
        承载在案）→ 钉 2 层大招：对方/我方 = (100/146)/0.5 = 100/73."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23031"), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        ours = _hit_amounts(log, source="1305")
        white = RT_ATK + LC23031_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "ult", lc_atk=LC23031_ATK, cr=RT_CR + 0.15,
            equipment=_lc("23031", "Hunt", {"luminfluxUltStacks": 2})))

        assert ours == pytest.approx(
            [2.4 * (white * 1.28) * 0.5 * 0.9 * (1 + (RT_CR + 0.15) * 0.5)],
            rel=REL_TOL), "我方大招（无穿透——待收）vs 手算"
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 146, rel=REL_TOL), "对方 DEF_PEN 54% 穿透区"
        assert theirs["hits"][0]["damage"] / ours[0] == pytest.approx(
            100 / 73, rel=REL_TOL)


class TestLC23046TheHellWhereIdealsBurn:
    """理想燃烧的地狱 S1（真理医生）：常驻 CR 16%（属性段）+ 战技叠攻 10%/层."""

    def test_skill_stacks(self, optimizer_driver):
        """战技×5：命中序=[@0..@4]（层在行动后挂）；归纳并行 ramp（对方逐场钉）."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23046"), "imaginary"))
        for _ in range(5):
            _cast(eng, "1305", "130502")
        skills = _hits_of(log, source="1305", action_type="skill")
        white = RT_ATK + LC23046_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", lc_atk=LC23046_ATK, cr=RT_CR + 0.16,
            conditionals={"summationStacks": 4},
            equipment=_lc("23046", "Hunt", {"spAtkBuff": False, "atkBuffStacks": 4})))

        # 第 5 发 @4 层、归纳 4：cr 0.33+0.10=0.43，cd 0.5+0.20=0.70
        hand5 = 1.5 * (white * 1.28 + white * 0.40) * 0.5 * 0.9 * (1 + 0.43 * 0.70)
        assert skills[4] == pytest.approx(hand5, rel=REL_TOL), "我方第 5 发（@4 层）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand5, rel=REL_TOL)
        assert skills[4] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.68, rel=REL_TOL), (
            "对方 ATK_P 0.40 白值换算通道")

    def test_sp_atk_divergence(self, optimizer_driver):
        """S10 结构差：消耗战技点攻击 40% 我方待收（param_3 绑定未挂在案）
        → 对方/我方 = 1.68/1.28 = 1.3125."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="23046"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        white = RT_ATK + LC23046_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23046_ATK, cr=RT_CR + 0.16,
            equipment=_lc("23046", "Hunt", {"spAtkBuff": True, "atkBuffStacks": 0})))

        assert ours == pytest.approx(
            1.0 * (white * 1.28) * 0.5 * 0.9 * (1 + (RT_CR + 0.16) * 0.5),
            rel=REL_TOL), "我方（无耗点段）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.3125, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——智识载体（黑塔 1013）
# ===========================================================================

class TestLC23018AnInstantBeforeAGaze:
    """片刻，留在眼底 S1（黑塔）：常驻 CD 36%（属性段）+ 终结技增伤按能量 0.36%/点."""

    def test_ult_energy_boost(self, optimizer_driver):
        """黑塔能量上限 110 → 增伤 39.6%（min(110,180)×0.36%——对方读 base_energy
        场景槽同式）."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23018"), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23018_ATK
        sc = _herta_opt(
            "ult", atk=white, extra_attacker={"cd": 0.5 + 0.36},
            equipment=_lc("23018", "Erudition", {"maxEnergyDmgBoost": True}))
        sc["base_energy"] = 110.0
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 2.0 * white * 0.5 * 0.9 * (1 + 0.05 * 0.86) * 1.396
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方大招（+39.6%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.396, rel=REL_TOL)


class TestLC23028YetHopeIsPriceless:
    """偏偏希望无价 S1（黑塔）：常驻 CR 16%（属性段）+ 追击增伤按暴伤 12%×层（≤4）."""

    def _fua_scene(self):
        """跨线追击模子（520/1000 半血上一刀跨线——21006 先例）."""
        return _make_logged(_compiled(
            _member_build("1013", lc="23028"), "ice", enemies=_low_hp_enemy("ice")))

    def test_fua_boost_cd_floor_theirs_bug(self, optimizer_driver):
        """S11 对方病（B-NEW1）：自然 CD 0.5——双方皆 0 层（官方口径）；对方
        floorSafe((CD-1.2)/0.2) 未钳零下界 → -48% 负增伤，我方 min(max(..,0),4)
        钳零正确 → 对方/我方 = 0.52."""
        eng, log = self._fua_scene()
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")   # 跨线 → 追击
        ours = _hit_amounts(log, source="1013", target="e1")
        white = HT_ATK + LC23028_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white, extra_attacker={"cr": 0.05 + 0.16},
            equipment=_lc("23028", "Erudition", {
                "fuaDmgBoost": True, "ultFuaDefShred": False})))

        hand = 0.4 * white * 0.5 * 0.9 * (1 + 0.21 * 0.5)
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), (
            "我方追击（CD 0.5 → 0 层钳零正确）vs 手算")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            0.52, rel=REL_TOL), "对方病数值自证（-48% 负增伤）"
        assert theirs["hits"][0]["damage"] / ours[1] == pytest.approx(0.52, rel=REL_TOL)

    def test_fua_boost_high_cd(self, optimizer_driver):
        """CD 2.0 档：双方 4 层 48% 比等（注入 CD+1.5——面板读取即重估；对方钉
        cd=2.0 floor((2.0-1.2)/0.2)=4 同档）."""
        eng, log = self._fua_scene()
        eng.state.actors["e1"].current_hp = 520.0
        _inject(eng, "1013", "XC_CD", {"crit_dmg": 1.5})
        _cast(eng, "1013", "101301")   # 跨线 → 追击
        ours = _hit_amounts(log, source="1013", target="e1")
        white = HT_ATK + LC23028_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white, extra_attacker={"cr": 0.05 + 0.16, "cd": 2.0},
            equipment=_lc("23028", "Erudition", {
                "fuaDmgBoost": True, "ultFuaDefShred": False})))

        hand = 0.4 * white * 0.5 * 0.9 * (1 + 0.21 * 2.0) * 1.48
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方追击（4 层 48%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_fua_def_shred_divergence(self, optimizer_driver):
        """S12 结构差：追击/终结技无视防御 20% 我方待收（fixture 未挂在案）
        → CD 2.0 档钉 true：对方/我方 = (100/180)/0.5 = 10/9."""
        eng, log = self._fua_scene()
        eng.state.actors["e1"].current_hp = 520.0
        _inject(eng, "1013", "XC_CD", {"crit_dmg": 1.5})
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013", target="e1")[1]
        white = HT_ATK + LC23028_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white, extra_attacker={"cr": 0.05 + 0.16, "cd": 2.0},
            equipment=_lc("23028", "Erudition", {
                "fuaDmgBoost": True, "ultFuaDefShred": True})))

        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 180, rel=REL_TOL), "对方无视防御 20% 穿透区"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(10 / 9, rel=REL_TOL)


class TestLC23041LifeShouldBeCastToFlames:
    """生命当付之一炬 S1（黑塔）：回合回能 10 + 命中降防 12% + 弱点增伤 60% 待收."""

    def test_turn_start_energy(self, optimizer_driver):
        """回合开始回能 10（我方状态锚单钉——对方控制器无能量承载）."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23041"), "ice"))
        assert eng.state.actors["1013"].current_energy == 0.0
        _emit(eng, "on_turn_start", {"actor": "1013"})
        assert eng.state.actors["1013"].current_energy == pytest.approx(10.0)

    def test_def_down_second_hit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23041"), "ice"))
        _cast(eng, "1013", "101301")
        assert "LC_23041_DEF_DOWN" in eng.state.actors["e1"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23041_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white,
            equipment=_lc("23041", "Erudition", {"dmgBoost": False, "defPen": True})))

        hand2 = 1.0 * white * (100 / 188) * 0.9 * 1.025
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方第 2 次命中（降防）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(
            100 / 188, rel=REL_TOL)

    def test_first_hit_window_divergence(self, optimizer_driver):
        """S13 结构差：对方 DEF_PEN 恒开；我方 after_being_hit 结算后挂（首击不吃）
        → 首击 对方/我方 = (100/188)/0.5 = 100/94."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23041"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC23041_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white,
            equipment=_lc("23041", "Erudition", {"dmgBoost": False, "defPen": True})))

        assert ours == pytest.approx(1.0 * white * Z, rel=REL_TOL), "我方首击（无降防）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(100 / 94, rel=REL_TOL)

    def test_dmg_boost_divergence(self, optimizer_driver):
        """S14 结构差：对「装备者添加的弱点」目标增伤 60% 我方待收（has_weakness
        未实现+弱点来源归属通道缺——双缺口 fixture 注释在案）→ 对方/我方 = 1.6."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23041"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC23041_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=white,
            equipment=_lc("23041", "Erudition", {"dmgBoost": True, "defPen": False})))

        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.6, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.6, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——丰饶载体（罗刹 1203；面板 = 白值×1.28 行迹）
# ===========================================================================

class TestLC23032ScentAloneStaysTrue:
    """唯有香如故 S1（罗刹）：常驻 BE 60%（属性段）+ 终结技命中挂【忘忧】易伤."""

    def test_woefree_second_hit(self, optimizer_driver):
        """终结技挂忘忧（after_being_hit 结算后——当次不吃，S15 钉）→ 下一次普攻
        比等（10% 档——BE 0.6<150%，双方同闸）."""
        eng, log = _make_logged(_compiled(_member_build("1203", lc="23032"), "imaginary"))
        _ult(eng, "1203", "120303", 100.0)
        assert "LC_23032_WOEFREE" in eng.state.actors["e1"].modifiers
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC23032_ATK
        atk = white * 1.28
        sc = _opt_luocha("basic")
        sc["base"]["atk"] = white
        sc["attacker"].update({"atk": atk, "be": 0.6})
        sc["equipment"] = _lc("23032", "Abundance", {
            "woefreeState": True, "additionalVulnerability": True})
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * atk * 0.5 * 0.9 * LC_CZ * 1.10
        assert ours[0] == pytest.approx(
            2.0 * atk * 0.5 * 0.9 * LC_CZ, rel=REL_TOL), "我方当次大招（忘忧未挂）vs 手算"
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方第 2 次命中（忘忧）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.10, rel=REL_TOL)
        assert _eff(eng, "1203")["break_effect"] == pytest.approx(0.6, rel=REL_TOL), (
            "我方 BE 属性段面板（0.6<1.5 低档闸）")
        assert theirs["stats"]["be"] == pytest.approx(0.6, rel=REL_TOL)

    def test_ult_window_divergence(self, optimizer_driver):
        """S15 结构差：对方 VULNERABILITY 恒开（当次大招即吃）；我方 after_being_hit
        结算后挂 → 当次大招 对方/我方 = 1.10."""
        eng, log = _make_logged(_compiled(_member_build("1203", lc="23032"), "imaginary"))
        _ult(eng, "1203", "120303", 100.0)
        ours = _hit_amounts(log, source="1203")[0]
        white = LC_ATK_W + LC23032_ATK
        atk = white * 1.28
        sc = _opt_luocha("ult")
        sc["base"]["atk"] = white
        sc["attacker"].update({"atk": atk, "be": 0.6})
        sc["equipment"] = _lc("23032", "Abundance", {
            "woefreeState": True, "additionalVulnerability": True})
        theirs = run_optimizer(optimizer_driver, sc)

        assert ours == pytest.approx(
            2.0 * atk * 0.5 * 0.9 * LC_CZ, rel=REL_TOL), "我方当次大招（无易伤）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.10, rel=REL_TOL)

    def test_woefree_high_be_branch(self, optimizer_driver):
        """BE≥150% 档：注入 break_effect 0.9（面板 0.6+0.9=1.5）→ 忘忧 18% 分支
        （param_2+param_4）→ 下一次普攻比等（对方 BE≥1.5 追加档同闸）."""
        eng, log = _make_logged(_compiled(_member_build("1203", lc="23032"), "imaginary"))
        _inject(eng, "1203", "XC_BE", {"break_effect": 0.9})
        _ult(eng, "1203", "120303", 100.0)
        _cast(eng, "1203", "120301")
        ours = _hit_amounts(log, source="1203")
        white = LC_ATK_W + LC23032_ATK
        atk = white * 1.28
        sc = _opt_luocha("basic")
        sc["base"]["atk"] = white
        sc["attacker"].update({"atk": atk, "be": 1.5})
        sc["equipment"] = _lc("23032", "Abundance", {
            "woefreeState": True, "additionalVulnerability": True})
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * atk * 0.5 * 0.9 * LC_CZ * 1.18
        assert ours[0] == pytest.approx(
            2.0 * atk * 0.5 * 0.9 * LC_CZ, rel=REL_TOL), "我方当次大招（忘忧未挂）vs 手算"
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方高档忘忧（18%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(
            1.18, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——存护载体（杰帕德 1104；Grit 防转攻 0.35×DEF 经 on_turn_start 活读）
# ===========================================================================

class TestLC23005MomentOfVictory:
    """制胜的瞬间 S1（杰帕德）：常驻 DEF 24%+EHR 24%（属性段）+ 受击 DEF 24%
    （Grit 放大进 ATK——防御面板的直伤消费通道）."""

    def test_self_attacked_def_buff(self, optimizer_driver):
        """受击 → DEF+24% → Grit 重算（stat_exprs 活读新 DEF）→ 普攻比等.
        对方 DEF_P 条件件 → DEF 终值 → dynamic conversion（ATK+=0.35×DEF）同链."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="23005"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})   # Grit 挂载（legacy_1000 先例）
        _emit(eng, "after_being_hit", {"target": "1104", "source": "e1"})
        assert "LC_23005_HIT_DEF" in eng.state.actors["1104"].modifiers
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")
        white_atk = GP_ATK_W + LC23005_ATK               # 1019.592
        white_def = GP_DEF_W + LC23005_DEF               # 1250.235
        atk = white_atk + 0.35 * white_def * 1.605       # Grit（DEF 1.605 档）
        sc = _opt_gepard("basic")
        sc["base"].update({"atk": white_atk, "def": white_def})
        sc["attacker"].update({"atk": white_atk, "def": white_def * 1.365})
        sc["equipment"] = _lc("23005", "Preservation", {"selfAttackedDefBuff": True})
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours[0] == pytest.approx(hand, rel=REL_TOL), "我方受击后普攻（Grit 放大）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(atk, rel=REL_TOL), (
            "对方 dynamic conversion 面板回显（DEF_P 条件件过 Grit）")
        assert _eff(eng, "1104")["atk"] == pytest.approx(atk, rel=REL_TOL), (
            "我方 Grit 活读新 DEF 面板")

    def test_pre_hit_baseline(self, optimizer_driver):
        """基线（未受击）：DEF 1.365 档双方比等（对方开关 off）."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="23005"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")
        white_atk = GP_ATK_W + LC23005_ATK
        white_def = GP_DEF_W + LC23005_DEF
        atk = white_atk + 0.35 * white_def * 1.365
        sc = _opt_gepard("basic")
        sc["base"].update({"atk": white_atk, "def": white_def})
        sc["attacker"].update({"atk": white_atk, "def": white_def * 1.365})
        sc["equipment"] = _lc("23005", "Preservation", {"selfAttackedDefBuff": False})
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * atk * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE)
        assert ours[0] == pytest.approx(hand, rel=REL_TOL), "我方基线普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_pre_hit_window_divergence(self, optimizer_driver):
        """S16 结构差：对方 DEF_P 恒开（未受击也吃=建模近似）；我方 after_being_hit
        结算后挂 → 受击前普攻 对方/我方 = (w_atk+0.35×1.605×w_def)/(w_atk+0.35×1.365×w_def)."""
        eng, log = _make_logged(_compiled(_member_build("1104", lc="23005"), "ice"))
        _emit(eng, "on_turn_start", {"actor": "1104"})
        _cast(eng, "1104", "110401")
        ours = _hit_amounts(log, source="1104")[0]
        white_atk = GP_ATK_W + LC23005_ATK
        white_def = GP_DEF_W + LC23005_DEF
        sc = _opt_gepard("basic")
        sc["base"].update({"atk": white_atk, "def": white_def})
        sc["attacker"].update({"atk": white_atk, "def": white_def * 1.365})
        sc["equipment"] = _lc("23005", "Preservation", {"selfAttackedDefBuff": True})
        theirs = run_optimizer(optimizer_driver, sc)

        assert ours == pytest.approx(
            1.0 * (white_atk + 0.35 * white_def * 1.365) * 0.5 * 0.9 * GP_CZ * (1 + GP_ICE),
            rel=REL_TOL), "我方受击前普攻（DEF 1.365 档）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            (white_atk + 0.35 * white_def * 1.605)
            / (white_atk + 0.35 * white_def * 1.365), rel=REL_TOL)
