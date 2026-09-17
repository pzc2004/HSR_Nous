"""L3 装备级对拍·名册批量扫荡（BACKLOG B22 扩展②续）：首批 6 光锥+4 遗器（见
tests/test_crosscheck_equipment.py）之后的批量扩拍——本批 25 光锥 + 14 遗器，
按品类摊开（输出专光/条件增伤/叠层/对敌 debuff/能量/面板族/追击/击破/速度/治疗/记忆族），
每件等式场景三方比对（我方引擎 vs 对方 vs 手算，rel_tol 1e-4）+ 结构差钉倍数。

载体（映射表现成，见各源文件）：黑塔 1013（智识）/黄泉 1308（虚无）/真理医生 1305（巡猎）
/白厄 1408（毁灭）/遐蝶 1407（记忆）/刻律德菈 1412（同谐·风——110 风套 2pc 门控载体）。
裁判链路与统一口径同首批（driver 头注 + 首批 docstring）；本文件只增映射表与场景。

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
--- 智识（黑塔 1013）---
24004 不息的演算 S1——属性段 ATK+8%（对方钉 atk 面板，ATK_P×白值口径）
atkBuffStacks 0-5（5）       攻击命中计数叠层 atk_pct 4%×N——**待收**（攻击级     钉 0 比等；钉 5 钉 S1
                            命中计数通道缺，fixture 在案）
spdBuff（false）            击中≥3 敌速度 +8%——**待收**（同通道缺）              钉 false（无伤害读出）
23010 拂晓之前 S1——属性段 CD+36%（对方钉 cd）
（无开关）战技/终结技增伤18% 常驻 dmg_skill/dmg_ultimate 类型桶                    战技段比等
fuaDmgBoost（true）         【梦身】追加增伤 48%：常驻 dmg_follow_up +             战技后跨线追击比等
                            enable_if has_modifier(SOMNUS)；摘除钩=on_action
                            follow_up——黑塔追击走 hook deal_damage 无此事件
                            （通道缺口在案，单体追击首发自吃正确）
21020 天才们的休憩 S1——属性段 ATK+16%（对方钉 atk 面板）
defeatedEnemyCdBuff（true） on_kill 钩 crit_dmg +24% 3回合                        杀 1 后比等
21013 别让世界静下来 S1
ultDmgBuff（true）          常驻 dmg_ultimate_dmg_boost 32%                        大招比等
（无开关）进战回能 20        on_battle_start gain_energy（无伤害读出）             我方状态锚单钉
21006 「我」的诞生 S1
（无开关）追加增伤 24%       常驻 dmg_follow_up_dmg_boost                           跨线追击比等
enemyHp50FuaBuff（true）    ≤50%HP 追加额外 +24%——**待收**（命中域无目标 HP      钉 true 钉 S2
                            通道，fixture 在案）
20006 智库 S1（无开关）      常驻 dmg_ultimate 28%                                  大招比等
20020 睿见 S1
postUltAtkBuff（true）      on_ultimate 钩 atk_pct 24% 2回合                       大招后普攻比等；
                                                                                 当次大招钉 S3（窗口族）
--- 虚无（黄泉 1308）---
23006 只需等待 S1——属性段 增伤 24%（AllDamageTypeAddedRatio，对方钉 dmg_boost）
spdStacks 0-3（3）          on_action 叠层 stat_exprs spd_pct 4.8%×N（钳 3）       3 行动后速度面板比等
dotEffect（false）          游丝：after_being_hit 挂记 → on_turn_start 跳伤        我方 vs 手算单钉
                            0.6×ATK（对方控制器无伤害承载=未建模；现 hook           （结构注记，非 S 钉）
                            deal_damage 期望暴击照算——B27#3 迁移待过堂在案）
21015 决心如汗珠般闪耀 S1
targetEnsnared（true）      after_being_hit 钩【攻陷】def_pct -12% 1回合           第 2 次命中比等；
                            （对方=FullTeam DEF_PEN 恒穿透无首次概念）             首次命中钉 S4
23004 以世界之名 S1
skillAtkBoost（true）       on_become_target 战技钩 atk_pct 24%（伤害前挂          战技比等（当次即吃
                            →结算后摘，当次即吃；对方 actionKind(SKILL) 同窗）     两侧同）
skillEhrBoost（true）       同钩 effect_hit 18%（无伤害读出）                      随挂不测
enemyDebuffedDmgBoost（false）对负面敌增伤 24%——**待收**（任意 debuff 存在性      钉 true 钉 S5
                            查询通道缺，fixture 在案）
21022 延长记号 S1——属性段 BE+16%（对方钉 be 面板，无直伤消费=面板锚）
enemyShockWindShear（true） 对触电/风化增伤 16%——**待收**（debuff 种类查询       钉 true 钉 S6
                            通道缺，fixture 在案）
20011 渊环 S1               对减速增伤 24%——**整段待收**（减速为数值型非具名     钉 true 钉 S7
                            debuff，fixture 在案）
--- 巡猎（真理医生 1305）---
21010 论剑 S1
sameTargetHitStacks 0-5（5）after_being_hit 双支（挂标/叠层 stat_exprs 8%×N）——  连击同目标第 3/4 发
                            首击只挂标无加成（官方）；层在命中后挂=当次不吃        比等（@1/@2 层）
24001 星海巡航 S1——属性段 CR+8%（对方钉 cr）
enemyHp50CrBoost（false）   ≤50%HP 暴击 +8%——**待收**（scoped crit 无消费端，    钉 true 钉 S8
                            fixture 在案）
enemyDefeatedAtkBuff（true）on_kill 钩 atk_pct 20% 2回合                           杀 1 后比等
21003 唯有沉默 S1——属性段 ATK+16%（并入我方 fixture 常驻 atk_pct）
enemies2CrBuff（true）      enable_if enemies_alive()≤2 crit_rate 12%              1 敌/3 敌门控双向比等
                            （对方 context.enemyCount≤2 同闸）
21017 点个关注吧 S1
（无开关）普攻/战技增伤 24%  常驻 dmg_basic/dmg_skill 类型桶                       普攻比等
maxEnergyDmgBoost（true）   enable_if $self.energy≥max_energy 额外 24%             满能量比等；空能钉 false
20007 离弦 S1
defeatedEnemyAtkBuff（true）on_kill 钩 atk_pct 24% 3回合                           杀 1 后比等
21037 最后的赢家 S1——属性段 ATK+12%（对方钉 atk 面板）
goodFortuneStacks 0-4（4）  【好运】暴击命中叠层 CD 8%×N——期望模式                钉 0 比等；钉 4 钉 S9
                            is_critical=false 层不可达（口径在案非病）
--- 毁灭（白厄 1408；行迹 atk_pct 0.5 白值换算两侧同）---
24000 记一位星神的陨落 S1
atkBoostStacks 0-4（4）     on_action 攻击叠层 stat_exprs atk_pct 8%×N（钳 4）     第 5 发普攻（@4 层）比等
weaknessBreakDmgBuff（true）on_break 钩 all_dmg 12% 2回合（结算后挂=当次不吃）    击破后行动比等；
                                                                                 当次击破段钉 S10
21012 秘密誓心 S1——属性段 增伤 20%（对方钉 dmg_boost）
enemyHpHigherDmgBoost（true）目标 HP%≥自身 HP% 额外 20%——**待收**（命中域无      钉 true 钉 S11
                            目标 HP 通道，fixture 在案）
21033 无处可逃 S1——属性段 ATK+24%（对方控制器**空**——全走钉死面板）
（无开关）击杀回血           on_kill 钩 heal 12%×atk（对方无承载=未建模）          我方 vs 手算单钉
21019 在蓝天下 S1——属性段 ATK+16%（对方钉 atk 面板）
defeatedEnemyCrBuff（true） on_kill 钩 crit_rate 12% 3回合                         杀 1 后比等
20016 俱殁 S1
selfHp80CrBuff（true）      enable_if hp/max_hp<0.8 crit_rate 12%（条件光环        半血比等；满血门控
                            现场重估；对方开关=状态钉）                            灭件比等
21058 一行往日的血 S1——属性段 CR+12%（对方钉 cr）
skillUltDmgBoost（true）    常驻 dmg_skill/dmg_ultimate 24%                        战技比等
--- 记忆（遐蝶 1407）---
24005 记忆永不落幕 S1——属性段 SPD+6%（对方钉 spd 面板，SPD_P×白值口径）
teamDmgBoost（true）        on_action 战技后 all_allies all_dmg 8% 3回合           战技后普攻比等；
                            （对方 mutual FullTeam 恒开无窗口）                    当次战技钉 S12

===========================================================================
遗器 buff 状态映射表（基础件 p2c/p4c 两侧各自原生通道，不钉面板）
===========================================================================
102 快枪手（黑塔）  2pc atk_pct 12%（p2c）；4pc spd_pct 6%（p4c 面板回显互对）+
                   普攻增伤 10%（对方 BASIC 标签 BOOST——战技段两侧同无比等）
104 猎人（黑塔）    2pc dmg_ice 10%（p2c 元素门控）；4pc on_ultimate 钩 CD 25% 2回合
                   （对方 enabled 恒开=当次即吃——窗口族）→ 大招后普攻比等；当次大招钉 S14
105 拳王（白厄）    2pc dmg_physical 10%（p2c 元素门控）；4pc on_action/受击叠层
                   stat_exprs atk_pct 5%×N（钳 5；对方 value 钉层）→ 第 6 发普攻比等
108 天才（遐蝶）    2pc dmg_quantum 10%（p2c）；4pc def_pen 10% 常驻 + 量子弱点额外
                   10%——**待收**（scoped def_pen 通道缺，fixture 在案）→ 钉 false 比等；
                   钉 true（20% 档）钉 S13
110 翔鹰（刻律德菈）2pc dmg_wind 10%（p2c 元素门控——风载体唯一已注册）；4pc 施放
                   终结技后行动提前 25%——无伤害读出**未拍**（在案）
111 怪盗（黄泉）    2pc/4pc break_effect 16%×2（p2c+p4c 面板回显互对，直伤无消费）；
                   4pc 击破回能 3（对方无承载=未建模，状态锚在案）
112 废土客（真理）  2pc dmg_imaginary 10%（p2c）；4pc 对负面敌 CR+10%/禁锢 CD+20%
                   ——**待收**（scoped 双暴无消费端，fixture 在案）→ 钉 0 比等；钉 1 钉 S15
113 莳者（黄泉）    2pc hp_pct 12%（p2c 面板回显互对）；4pc 受击/耗血叠层
                   stat_exprs crit_rate 8%×N（钳 2；对方 value 钉层）→ 手发受击 2 次比等
114 信使（黄泉）    2pc spd_pct 6%（p2c 面板回显互对）；4pc 对我方目标施放终结技全队
                   速度 12%——载体终结技皆对敌（ AoE/单体攻击技）**未拍**（在案）
120 勇烈（黑塔）    2pc atk_pct 12% + 4pc 面板 crit_rate 6%（p4c）；4pc on_action
                   follow_up 钩 dmg_ultimate 36% 1回合——黑塔追击=hook deal_damage
                   无 on_action（通道缺口在案）→ 手发等价事件后大招比等
122 学者（真理）    2pc crit_rate 8%（p2c）；4pc 常驻战技/终结技 20% + on_ultimate
                   闩下次战技 scoped 25%（对方 enabled 开关=闩已立）→ 战技/大招后战技比等
123 英豪（遐蝶）    2pc atk_pct 12%（生命倍率载体=无伤害消费，面板锚）；4pc 忆灵在场
                   spd 6%（enable_if has_summon）+ 忆灵攻击后装备者/忆灵 CD 30%
                   （对方 enabled=SelfAndMemosprite 恒开）→ 召唤+忆灵攻击后普攻/
                   双实体面板回显比等
127 救世主（遐蝶）  2pc crit_rate 8%；4pc 普攻/战技后忆灵在场→HP 24%+全队增伤 15%
                   （A 钩摘+B 钩忆灵在场重挂=常驻刷新；对方 enabled 恒开无窗口）
                   → 战技后普攻比等；当次战技钉 S16
131 领航员（真理）  2pc atk_pct 12%；4pc 进战 1 层/战技叠层（钳 3）stat_exprs
                   战技/终结技增伤 18%×N（对方 value 钉层）→ 连放战技 @1/@2 层比等

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）
===========================================================================
S1  24004 攻击叠层/增速（我方待收——攻击级命中计数通道缺在案）→ 钉 5 层：
    对方/我方 = (1.08+0.20)/1.08 = 1.28/1.08 ≈ 1.185185
S2  21006 ≤50%HP 追加额外增伤（我方待收——命中域无目标 HP 通道在案）→
    对方/我方 = 1.48/1.24 = 37/31 ≈ 1.193548
S3  20020 睿见窗口（对方 postUltAtkBuff 恒开含当次大招=建模近似，我方
    on_ultimate 结算后挂）→ 当次大招 1.24
S4  21015 攻陷窗口（对方 DEF_PEN 恒穿透无首次概念，我方 after_being_hit
    结算后挂=首次不吃）→ 首次命中 (100/188)/0.5 = 100/94 ≈ 1.063830
S5  23004 对负面敌增伤（我方待收——任意 debuff 存在性查询缺在案）→ 1.24
S6  21022 触电/风化增伤（我方待收——debuff 种类查询缺在案）→ 1.16
S7  20011 减速增伤（我方整段待收在案）→ 1.24
S8  24001 ≤50%HP 暴击（我方待收——scoped crit 无消费端在案）→
    对方/我方 = 1.165/1.125 = 233/225 ≈ 1.035556
S9  21037 好运叠层（期望模式 is_critical 恒 false——口径在案非病）→
    对方钉 4 层/我方 = (1+0.17×0.82)/(1+0.17×0.5) = 1.1394/1.085 ≈ 1.050138
S10 24000 击破增伤窗口（E8 同族）→ 当次击破段 1.12
S11 21012 HP% 比较额外增伤（我方待收在案）→ 1.4/1.2 = 7/6 ≈ 1.166667
S12 24005 团队增伤窗口（对方 mutual 恒开）→ 当次战技 1.224/1.144 ≈ 1.069930
S13 108 量子弱点额外穿透（我方待收——scoped def_pen 通道缺在案）→
    (100/180)/(100/190) = 19/18 ≈ 1.055556
S14 104 暴伤窗口（对方 enabled 恒开）→ 当次大招 1.0375/1.025 = 83/82 ≈ 1.012195
S15 112 对负面敌 CR+10%（我方待收——scoped 双暴无消费端在案；禁锢 CD+20%
    同案）→ 钉 1 档：对方/我方 = 1.135/1.085 = 227/217 ≈ 1.046083
S16 127 忆灵在场件窗口（对方恒开）→ 当次战技
    1.24×(1+0.144+0.1+0.15)/(1+0.144+0.1) ≈ 1.389517

待查/未完清单（证据不足或通道缺口，不钉不改）：
- 23006 游丝 DoT：对方控制器无伤害承载（未建模）——我方 vs 手算单钉在案；
  现 hook deal_damage 期望暴击照算（DoT 不暴击的官方口径=B27#3 声明式 dot
  迁移待过堂在案，非本批新病）
- 21033 击杀治疗：对方控制器全空（properties 只经钉死面板）——治疗量我方
  vs 手算单钉；治疗/护盾类光锥对拍读出端缺（driver 无 heal 输出）在案
- 124 诗人/130 卜者：速度档读 x.c.a SPD——driver 镜像 c 只含套装件（钉死面板
  在 x.a）恒低档，非语义差是镜像 fidelity 缺口——driver 需补 c.a 白值速度
  再拍（报回 owner 定夺镜像改法）
- 110 4pc 推条/114 4pc 全队速度（对我方目标终结技）：无伤害读出/载体终结技
  皆对敌——未拍在案
- 23010 梦身摘除/120 4pc 追击触发：依赖 on_action(follow_up) 事件——黑塔/
  真理追击走 hook deal_damage 无此事件（引擎通道缺口在案）；本批以手发等价
  事件补发（wave-1 合成事件先例），首发自吃数值正确性不受影响
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter  # noqa: F401
# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    AC_ATK, HT_ATK, Z, _POLICY, _cast, _dummy, _hit_amounts, _make_logged, _stage,
)
from tests.test_crosscheck_equipment import (  # noqa: F401
    RT_ATK, RT_CD, RT_CR, RT_DEF, RT_HP, RT_SPD, ZR, _acheron_opt, _compiled,
    _herta_opt, _member_build, _ratio_opt, _rt_panel, _ult,
)
from tests.test_crosscheck_team_phainon import (  # noqa: F401
    CY_ATK, CY_WIND, PH_ATK, PH_CD, PH_CR, PH_DEF, PH_HP, PH_SPD, Z_CY, Z_PH,
    _opt_cerydra, _opt_phainon,
)
from tests.test_crosscheck_team_remembrance import (  # noqa: F401
    CA_ATK, CA_CD, CA_CR, CA_DEF, CA_HP, CA_Q, CA_SPD, Z_CA_CRIT, _fire_ult,
    _opt_castorice,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（本批新增；载体既有常数从各波文件复用）
# ---------------------------------------------------------------------------

# 光锥白值（fixture base_stats 终审值；仅 atk 进手算锚，hp/def 不进伤害式）
LC24004_ATK, LC23010_ATK = 529.2, 582.12
LC21020_ATK, LC21013_ATK, LC21006_ATK = 476.28, 476.28, 476.28
LC20006_ATK, LC20020_ATK = 370.44, 370.44
LC23006_ATK, LC21015_ATK, LC23004_ATK, LC21022_ATK = 582.12, 476.28, 582.12, 476.28
LC21010_ATK, LC24001_ATK, LC21003_ATK, LC21017_ATK = 476.28, 529.2, 476.28, 476.28
LC20007_ATK, LC21037_ATK = 370.44, 476.28
LC24000_ATK, LC21012_ATK, LC21033_ATK = 529.2, 476.28, 529.2
LC21019_ATK, LC20016_ATK, LC21058_ATK = 476.28, 370.44, 529.2
LC24005_ATK = 529.2

# 击杀测试双敌模子（e2 脆皮——21027 早餐先例）
def _kill_enemies(element: str):
    return _dummy("e1", element) + [
        {"actor_id": "e2", "name": "假人2", "hp": 100.0, "spd": 100, "atk": 1000,
         "def": 1000, "max_toughness": 9999, "weakness": [element]}]


def _low_hp_enemy(element: str):
    """跨线追击模子（520/1000 半血上一刀跨线——黑塔 115 先例）."""
    return [{"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 9999, "weakness": [element]}]


def _fragile_toughness(element: str):
    """当次击破模子（韧性 10——23000 E8 先例）."""
    return [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 10, "weakness": [element]}]


# ---------------------------------------------------------------------------
# 对方侧场景模子（本批新增载体：白厄/刻律/遐蝶——既有模子不含 equipment 槽）
# ---------------------------------------------------------------------------

def _pha_opt(action: str, *, lc_atk: float = 0.0, equipment=None, cond=None,
             extra_attacker=None, enemy=None):
    """对方白厄场景：E0 中性钉死（同 _opt_phainon）+ 装备块/光锥白值并入.

    行迹 atk_pct 0.5 走**对方角色条件件**（atkBuffStacks=1 → ATK_P×白值——
    与 wave-1 同口径，不钉面板；重复钉=双倍计入）；光锥属性段 ATK% 族
    （21019/21033 族）才钉 extra_attacker.atk = 白值×(1+属性段).
    """
    white = PH_ATK + lc_atk
    sc = _opt_phainon(action, cond=cond, enemy_count=(enemy or {}).get("count", 1))
    sc["base"] = {"atk": white, "hp": PH_HP, "def": PH_DEF, "spd": PH_SPD}
    sc["attacker"] = {**{"atk": white, "hp": PH_HP, "def": PH_DEF,
                         "spd": PH_SPD, "cr": PH_CR, "cd": PH_CD},
                      **(extra_attacker or {})}
    if enemy:
        sc["enemy"] = enemy
    if equipment:
        sc["equipment"] = equipment
    return sc


def _cas_opt(action: str, *, equipment=None, cond=None, extra_attacker=None):
    """对方遐蝶场景：_opt_castorice 铺底 + 装备块/面板覆写."""
    sc = _opt_castorice(action, cond=cond)
    sc["attacker"].update(extra_attacker or {})
    if equipment:
        sc["equipment"] = equipment
    return sc


def _cer_opt(action: str, *, equipment=None):
    """对方刻律德菈场景（110 风套门控载体）：_opt_cerydra 铺底 + 装备块."""
    sc = _opt_cerydra(action)
    if equipment:
        sc["equipment"] = equipment
    return sc


def _lc(lc_id: str, path: str, conditionals: dict, sup: int = 1):
    return {"light_cone": {"id": lc_id, "superimposition": sup, "path": path,
                           "conditionals": conditionals}}


def _relic(set_id: str, pieces: int, conditionals: dict):
    return {"relic_sets": [{"id": set_id, "pieces": pieces,
                            "conditionals": conditionals}]}


def _eff_spd(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])["spd"]


def _eff(eng, aid):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


# ===========================================================================
# 光锥对拍——智识载体（黑塔 1013）
# ===========================================================================

class TestLC24004EternalCalculus:
    """不息的演算 S1（黑塔）：常驻攻击 8%（属性段）+ 攻击叠层/增速待收（S1 钉）."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="24004"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC24004_ATK
        theirs_sc = _herta_opt(
            "basic", atk=white * 1.08,
            equipment=_lc("24004", "Erudition", {"atkBuffStacks": 0, "spdBuff": False}))
        theirs_sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, theirs_sc)

        hand = 1.0 * white * 1.08 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 8% 钩 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.08, rel=REL_TOL)

    def test_stacks_divergence(self, optimizer_driver):
        """S1 结构差：攻击叠层 4%×5（我方待收——攻击级命中计数通道缺在案）→
        对方钉 5 层 ATK_P 0.20：对方/我方 = 1.28/1.08."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="24004"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC24004_ATK
        sc = _herta_opt(
            "basic", atk=white * 1.08,
            equipment=_lc("24004", "Erudition", {"atkBuffStacks": 5, "spdBuff": False}))
        sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, sc)

        assert theirs["stats"]["atk"] == pytest.approx(white * 1.28, rel=REL_TOL), (
            "对方 ATK_P 0.20 白值换算通道")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.28 / 1.08, rel=REL_TOL)


class TestLC23010BeforeDawn:
    """拂晓之前 S1（黑塔）：CD 36%（属性段）+ 战技/终结技 18% + 梦身追加 48%."""

    def test_skill(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="23010"), "ice"))
        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC23010_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "skill", atk=white, extra_attacker={"cd": 0.5 + 0.36},
            equipment=_lc("23010", "Erudition", {"fuaDmgBoost": False})))

        hand = 1.0 * white * 0.5 * 0.9 * (1 + 0.05 * 0.86) * 1.18
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技（CD36%+增伤18%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_somnus_fua(self, optimizer_driver):
        """梦身追加增伤：战技（挂梦身）→ 基本击杀跨线追击吃 48%（黑塔追击=hook
        deal_damage——enable_if 现场读梦身仍挂，当次自吃正确；摘除钩通道缺口在案）。
        e2 血轴：2000——战技 AoE 后 67.8%>50% 不跨线（追击不在梦身挂载前误发），
        普攻后 40.5%≤50% 跨线（梦身已挂）."""
        enemies = _dummy("e1", "ice") + [
            {"actor_id": "e2", "name": "假人2", "hp": 2000.0, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="23010"), "ice", enemies=enemies))
        _cast(eng, "1013", "101302")                       # 战技 → SOMNUS 挂上（不跨线）
        assert "LC_23010_SOMNUS" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301", target="e2")          # 跨线 → 追击（梦身在）
        ours = _hit_amounts(log, source="1013", target="e1")   # [战技, 追击]
        white = HT_ATK + LC23010_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white, extra_attacker={"cd": 0.5 + 0.36},
            equipment=_lc("23010", "Erudition", {"fuaDmgBoost": True})))

        hand_fua = 0.4 * white * 0.5 * 0.9 * (1 + 0.05 * 0.86) * 1.48
        assert ours[1] == pytest.approx(hand_fua, rel=REL_TOL), "我方追击（梦身 48%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_fua, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21020GeniusesRepose:
    """天才们的休憩 S1（黑塔）：常驻攻击 16%（属性段）+ 击杀暴伤 24%."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21020"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21020_ATK
        sc = _herta_opt("basic", atk=white * 1.16,
                        equipment=_lc("21020", "Erudition", {"defeatedEnemyCdBuff": False}))
        sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * white * 1.16 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_kill_cd(self, optimizer_driver):
        """击杀跨线：追击在 on_kill 暴伤挂载**前**嵌发（on_hp_decrease→跨线→死亡
        →on_kill 序——无 CD 件）；随后普攻吃 CD+24%（21027 早餐双段先例同构）."""
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21020"), "ice", enemies=_kill_enemies("ice")))
        _cast(eng, "1013", "101301", target="e2")   # 击杀 → on_kill 暴伤 24% 3回合
        assert "LC_21020_CRIT_DMG" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301", target="e1")
        ours = _hit_amounts(log, source="1013", target="e1")
        white = HT_ATK + LC21020_ATK
        sc = _herta_opt("basic", atk=white * 1.16,
                        equipment=_lc("21020", "Erudition", {"defeatedEnemyCdBuff": True}))
        sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, sc)

        hand_fua = 0.4 * white * 1.16 * Z              # 追击（无 CD 件——挂载前嵌发）
        hand = 1.0 * white * 1.16 * 0.5 * 0.9 * (1 + 0.05 * 0.74)
        assert ours == pytest.approx([hand_fua, hand], rel=REL_TOL), (
            "我方两段：追击（无 CD 件）+ 击杀后普攻（CD+24%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21013MakeTheWorldClamor:
    """别让世界静下来 S1（黑塔）：终结技增伤 32% + 进战回能 20（状态锚）."""

    def test_ult_boost(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="21013"), "ice"))
        assert eng.state.actors["1013"].current_energy == pytest.approx(20.0), (
            "我方进战回能 20（状态锚——无伤害读出单钉）")
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21013_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", atk=white,
            equipment=_lc("21013", "Erudition", {"ultDmgBuff": True})))

        hand = 2.0 * white * Z * 1.32
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方大招（增伤 32%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21006BirthOfSelf:
    """「我」的诞生 S1（黑塔）：追加增伤 24% + ≤50%HP 额外 24% 待收（S2 钉）."""

    def test_fua_boost(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21006"), "ice", enemies=_low_hp_enemy("ice")))
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")   # 跨线 → 追击
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC21006_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white,
            equipment=_lc("21006", "Erudition", {"enemyHp50FuaBuff": False})))

        hand = 0.4 * white * Z * 1.24
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方追击（增伤 24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_low_hp_divergence(self, optimizer_driver):
        """S2 结构差：≤50%HP 追加额外 +24%（我方待收——命中域无目标 HP 通道在案）
        → 对方/我方 = 1.48/1.24."""
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21006"), "ice", enemies=_low_hp_enemy("ice")))
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")[1]
        white = HT_ATK + LC21006_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", atk=white,
            equipment=_lc("21006", "Erudition", {"enemyHp50FuaBuff": True})))

        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.48, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.48 / 1.24, rel=REL_TOL)


class TestLC20006DataBank:
    """智库 S1（黑塔）：终结技增伤 28% 常驻."""

    def test_ult_boost(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="20006"), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC20006_ATK
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", atk=white,
            equipment=_lc("20006", "Erudition", {"ultDmgBuff": True})))

        hand = 2.0 * white * Z * 1.28
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC20020Sagacity:
    """睿见 S1（黑塔）：终结技后攻击 24% 2回合（窗口族 S3 钉）."""

    def test_post_ult_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1013", lc="20020"), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        assert "LC_20020_SAGACITY_ATK" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        white = HT_ATK + LC20020_ATK
        sc = _herta_opt("basic", atk=white,
                        equipment=_lc("20020", "Erudition", {"postUltAtkBuff": True}))
        sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, sc)

        hand = 1.0 * white * 1.24 * Z
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方大招后普攻（+24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_window_divergence(self, optimizer_driver):
        """S3 结构差：对方 postUltAtkBuff 恒开含当次大招（建模近似）；我方
        on_ultimate 结算后挂（当次不吃）→ 当次大招 1.24."""
        eng, log = _make_logged(_compiled(_member_build("1013", lc="20020"), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")[0]
        white = HT_ATK + LC20020_ATK
        sc = _herta_opt("ult", atk=white,
                        equipment=_lc("20020", "Erudition", {"postUltAtkBuff": True}))
        sc["base"] = {"atk": white, "hp": 952.56, "def": 396.9, "spd": 100}
        theirs = run_optimizer(optimizer_driver, sc)

        assert ours == pytest.approx(2.0 * white * Z, rel=REL_TOL), "我方当次大招 vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.24, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——虚无载体（黄泉 1308）
# ===========================================================================

class TestLC23006Patience:
    """只需等待 S1（黄泉）：常驻增伤 24%（属性段）+ 速度叠层 + 游丝 DoT（对方未建模）."""

    def test_permanent_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23006"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23006_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"dmg_boost": 0.24},
            equipment=_lc("23006", "Nihility", {"spdStacks": 0, "dotEffect": False})))

        hand = 1.0 * white * Z * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 24% 钩 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_spd_stacks_panel(self, optimizer_driver):
        """速度叠层：3 行动后 spd = 101×(1+3×0.048)——双方面板回显 + 手算三锚
        （速度无伤害读出=面板比等）."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23006"), "thunder"))
        for _ in range(3):
            _cast(eng, "1308", "130801")
        ours_spd = _eff_spd(eng, "1308")
        white = AC_ATK + LC23006_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"dmg_boost": 0.24},
            equipment=_lc("23006", "Nihility", {"spdStacks": 3, "dotEffect": False})))

        hand_spd = 101 * (1 + 3 * 0.048)
        assert ours_spd == pytest.approx(hand_spd, rel=REL_TOL), "我方 3 层速度 vs 手算"
        assert theirs["stats"]["spd"] == pytest.approx(hand_spd, rel=REL_TOL), (
            "对方 SPD_P 0.144 白值换算通道")

    def test_erode_dot_vs_hand(self, optimizer_driver):
        """游丝 DoT（对方控制器无伤害承载=未建模——我方 vs 手算单钉）：
        挂码后手发 on_turn_start → 跳伤 0.6×atk×0.5×0.9×1.24×1.025（现 hook
        deal_damage 期望暴击照算——B27#3 声明式 dot 迁移待过堂在案，非本批新病）."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23006"), "thunder"))
        _cast(eng, "1308", "130801")
        assert "LC_23006_ERODE" in eng.state.actors["e1"].modifiers, "首施挂游丝"
        log.clear()
        eng.bus.emit("on_turn_start", {"actor": "e1"}, eng.state)
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23006_ATK

        hand = 0.6 * white * 0.5 * 0.9 * 1.24 * 1.025
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方游丝跳伤 vs 手算（对方未建模——结构注记）")


class TestLC21015Resolution:
    """决心如汗珠般闪耀 S1（黄泉）：攻陷 def -12%（对方 FullTeam DEF_PEN 建模）."""

    def test_ensnare_second_hit(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21015"), "thunder"))
        _cast(eng, "1308", "130801")
        assert "LC_21015_ENSNARE" in eng.state.actors["e1"].modifiers, "首次命中挂攻陷"
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC21015_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("21015", "Nihility", {"targetEnsnared": True})))

        hand2 = 1.0 * white * (100 / 188) * 0.9 * 1.025   # 穿透 12% → 100/188
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "我方第二次命中（攻陷已挂）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(100 / 188, rel=REL_TOL)

    def test_first_hit_window_divergence(self, optimizer_driver):
        """S4 结构差：对方 DEF_PEN 恒穿透无首次概念；我方 after_being_hit 结算后
        挂（首次不吃）→ 首次命中 对方/我方 = (100/188)/0.5 = 100/94."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21015"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC21015_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("21015", "Nihility", {"targetEnsnared": True})))

        assert ours == pytest.approx(1.0 * white * Z, rel=REL_TOL), "我方首次（无穿透）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(100 / 94, rel=REL_TOL)


class TestLC23004InTheNameOfTheWorld:
    """以世界之名 S1（黄泉）：战技攻击 24%（当次即吃两侧同窗）+ 负面增伤待收（S5 钉）."""

    def test_skill_atk_boost(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23004"), "thunder"))
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC23004_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "skill", atk=white,
            equipment=_lc("23004", "Nihility", {
                "enemyDebuffedDmgBoost": False, "skillAtkBoost": True,
                "skillEhrBoost": True})))

        hand = 1.6 * white * 1.24 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方战技（on_become_target 伤害前挂=当次即吃）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 actionKind(SKILL) ATK_P 0.24 同窗")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_debuffed_dmg_divergence(self, optimizer_driver):
        """S5 结构差：对负面敌增伤 24%（我方待收——任意 debuff 存在性查询缺在案）
        → 对方/我方 = 1.24."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="23004"), "thunder"))
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC23004_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "skill", atk=white,
            equipment=_lc("23004", "Nihility", {
                "enemyDebuffedDmgBoost": True, "skillAtkBoost": True,
                "skillEhrBoost": True})))

        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.24, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.24, rel=REL_TOL)


class TestLC21022Fermata:
    """延长记号 S1（黄泉）：BE 16% 面板锚 + 触电/风化增伤待收（S6 钉）."""

    def test_be_panel_and_neutral(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21022"), "thunder"))
        assert _eff(eng, "1308")["break_effect"] == pytest.approx(0.16), (
            "我方 BE 属性段（面板锚——直伤无消费）")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        white = AC_ATK + LC21022_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white, extra_attacker={"be": 0.16},
            equipment=_lc("21022", "Nihility", {"enemyShockWindShear": False})))

        hand = 1.0 * white * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.16, rel=REL_TOL), "对方 BE 面板回显"

    def test_shock_wind_divergence(self, optimizer_driver):
        """S6 结构差：对触电/风化增伤 16%（我方待收——debuff 种类查询缺在案）→ 1.16."""
        eng, log = _make_logged(_compiled(_member_build("1308", lc="21022"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        white = AC_ATK + LC21022_ATK
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=white,
            equipment=_lc("21022", "Nihility", {"enemyShockWindShear": True})))

        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.16, rel=REL_TOL)


class TestLC20011Loop:
    """渊环 S1（黄泉）：减速增伤整段待收（S7 钉——divergence 单件）."""

    def test_slowed_divergence(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1308", lc="20011"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")[0]
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + 317.52,
            equipment=_lc("20011", "Nihility", {"enemySlowedDmgBuff": True})))

        assert ours == pytest.approx(1.0 * (AC_ATK + 317.52) * Z, rel=REL_TOL), (
            "我方整段待收=无增伤 vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.24, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——巡猎载体（真理医生 1305）
# ===========================================================================

class TestLC21010Swordplay:
    """论剑 S1（真理医生）：同目标连击叠层 8%×N（首击只挂标无加成——官方口径）."""

    def test_ramp_same_target(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21010"), "imaginary"))
        for _ in range(4):
            _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        # 命中序 = [①@挂标(0), ②@0层, ③@1层, ④@2层]（层在命中后挂=当次不吃）
        base = 1.0 * _rt_panel(LC21010_ATK) * ZR
        assert ours == pytest.approx(
            [base, base, base * 1.08, base * 1.16], rel=REL_TOL), "我方叠层斜坡 vs 手算"
        theirs1 = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21010_ATK,
            equipment=_lc("21010", "Hunt", {"sameTargetHitStacks": 1})))
        theirs2 = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21010_ATK,
            equipment=_lc("21010", "Hunt", {"sameTargetHitStacks": 2})))
        assert ours[2] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL), (
            "第 3 发（@1 层）双方互对")
        assert ours[3] == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL), (
            "第 4 发（@2 层）双方互对")


class TestLC24001Cruising:
    """星海巡航 S1（真理医生）：CR 8%（属性段）+ 击杀攻击 20% + 低血暴击待收（S8 钉）."""

    def test_permanent_cr(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="24001"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC24001_ATK, cr=RT_CR + 0.08,
            equipment=_lc("24001", "Hunt", {
                "enemyHp50CrBoost": False, "enemyDefeatedAtkBuff": False})))

        hand = 1.0 * _rt_panel(LC24001_ATK) * 0.5 * 0.9 * (1 + 0.25 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 CR 8% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_kill_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="24001"), "imaginary",
            enemies=_kill_enemies("imaginary")))
        _cast(eng, "1305", "130501", target="e2")   # 击杀 → 攻击 20% 2回合
        assert "LC_24001_ATK_UP" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501", target="e1")
        ours = _hit_amounts(log, source="1305", target="e1")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC24001_ATK, cr=RT_CR + 0.08,
            equipment=_lc("24001", "Hunt", {
                "enemyHp50CrBoost": False, "enemyDefeatedAtkBuff": True})))

        # 击杀攻击 20% 与行迹 28% 同白值基数（分算叠加非乘算）
        hand = 1.0 * (_rt_panel(LC24001_ATK) + (RT_ATK + LC24001_ATK) * 0.2) \
            * 0.5 * 0.9 * 1.125
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方击杀后普攻（+20%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_low_hp_cr_divergence(self, optimizer_driver):
        """S8 结构差：≤50%HP 暴击 +8%（我方待收——scoped crit 无消费端在案）
        → 对方/我方 = 1.165/1.125."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="24001"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC24001_ATK, cr=RT_CR + 0.08,
            equipment=_lc("24001", "Hunt", {
                "enemyHp50CrBoost": True, "enemyDefeatedAtkBuff": False})))

        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.165, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.165 / 1.125, rel=REL_TOL)


class TestLC21003OnlySilenceRemains:
    """唯有沉默 S1（真理医生）：常驻攻击 16% + ≤2 敌暴击 12%（门控双向比等）."""

    def test_one_enemy(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21003"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21003_ATK,
            extra_attacker={"atk": _rt_panel(LC21003_ATK)
                            + (RT_ATK + LC21003_ATK) * 0.16},
            equipment=_lc("21003", "Hunt", {"enemies2CrBuff": True})))

        hand = 1.0 * (_rt_panel(LC21003_ATK) + (RT_ATK + LC21003_ATK) * 0.16) \
            * 0.5 * 0.9 * (1 + 0.29 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 1 敌（CR 档开）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_three_enemy_gate_off(self, optimizer_driver):
        """3 敌场：我方 enable_if enemies_alive()≤2 灭 ≡ 对方 context.enemyCount≤2 闸."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="21003"), "imaginary",
            enemies=_dummy("e1", "imaginary", n=3)))
        _cast(eng, "1305", "130501", target="e2")
        ours = _hit_amounts(log, source="1305", target="e2")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21003_ATK,
            extra_attacker={"atk": _rt_panel(LC21003_ATK)
                            + (RT_ATK + LC21003_ATK) * 0.16},
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 3},
            equipment=_lc("21003", "Hunt", {"enemies2CrBuff": True})))

        hand = 1.0 * (_rt_panel(LC21003_ATK) + (RT_ATK + LC21003_ATK) * 0.16) * ZR
        # CR 档灭——仅攻击 16%（与行迹同白值基数）
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 3 敌（CR 档灭）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 enemyCount=3 同闸灭")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21017SubscribeForMore:
    """点个关注吧 S1（真理医生）：普攻/战技增伤 24% + 满能量额外 24%（门控比等）."""

    def test_basic_not_full_energy(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21017"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21017_ATK,
            equipment=_lc("21017", "Hunt", {"maxEnergyDmgBoost": False})))

        hand = 1.0 * _rt_panel(LC21017_ATK) * ZR * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_basic_full_energy(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21017"), "imaginary"))
        st = eng.state.actors["1305"]
        st.current_energy = 140.0   # 满能（真理医生 max_energy 140）→ enable_if 现场重估开
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21017_ATK,
            equipment=_lc("21017", "Hunt", {"maxEnergyDmgBoost": True})))

        hand = 1.0 * _rt_panel(LC21017_ATK) * ZR * 1.48
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方满能量（1.24+0.24）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC20007DartingArrow:
    """离弦 S1（真理医生）：击杀攻击 24% 3回合."""

    def test_kill_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="20007"), "imaginary",
            enemies=_kill_enemies("imaginary")))
        _cast(eng, "1305", "130501", target="e2")
        assert "LC_20007_ATK_BUFF" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130501", target="e1")
        ours = _hit_amounts(log, source="1305", target="e1")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC20007_ATK,
            equipment=_lc("20007", "Hunt", {"defeatedEnemyAtkBuff": True})))

        hand = 1.0 * (_rt_panel(LC20007_ATK) + (RT_ATK + LC20007_ATK) * 0.24) * ZR
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方击杀后普攻（+24% 与行迹同白值基数）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21037FinalVictor:
    """最后的赢家 S1（真理医生）：常驻攻击 12%（属性段）+ 好运叠层口径差（S9 钉）."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21037"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        # 属性段 ATK+12% 走钉死面板：面板 = 白值×1.28(行迹) + 白值×0.12
        # （行迹与属性段同白值基数——分算叠加非乘算）
        white = RT_ATK + LC21037_ATK
        atk = white * 1.28 + white * 0.12
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21037_ATK,
            extra_attacker={"atk": atk},
            equipment=_lc("21037", "Hunt", {"goodFortuneStacks": 0})))

        hand = 1.0 * atk * ZR
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_stacks_mode_divergence(self, optimizer_driver):
        """S9 口径差（非病）：好运暴击叠层 CD 8%×4——期望模式 is_critical 恒 false
        层不可达（fixture 口径在案）；对方钉 4 层 CD 0.32 → 1.1394/1.085."""
        eng, log = _make_logged(_compiled(_member_build("1305", lc="21037"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        assert "LC_21037_GOOD_FORTUNE" not in eng.state.actors["1305"].modifiers, (
            "期望模式叠层不出（口径锚）")
        white = RT_ATK + LC21037_ATK
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC21037_ATK,
            extra_attacker={"atk": white * 1.28 + white * 0.12},
            equipment=_lc("21037", "Hunt", {"goodFortuneStacks": 4})))

        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.1394, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.1394 / 1.085, rel=REL_TOL)


# ===========================================================================
# 光锥对拍——毁灭载体（白厄 1408；面板 = 白值×1.5 行迹）
# ===========================================================================

class TestLC24000FallOfAeon:
    """记一位星神的陨落 S1（白厄）：攻击叠层 8%×4 + 击破增伤 12%（窗口族 S10 钉）."""

    def test_atk_stacks(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="24000"), "physical"))
        for _ in range(5):
            _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC24000_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC24000_ATK,
            equipment=_lc("24000", "Destruction", {
                "atkBoostStacks": 4, "weaknessBreakDmgBuff": False})))

        # 命中序 = [①@0 … ⑤@4层]（层在行动后挂=当次不吃；钳 4）
        hand5 = 1.0 * (white * 1.5 + white * 0.32) * Z_PH
        assert ours[4] == pytest.approx(hand5, rel=REL_TOL), "我方第 5 发（@4 层）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand5, rel=REL_TOL)
        assert ours[4] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.82, rel=REL_TOL), (
            "对方 ATK_P 0.32 白值换算通道")

    def test_break_buff_window(self, optimizer_driver):
        """击破增伤 12%：我方 on_break 结算后挂（当次击破段不吃）≡ 对方击破后
        行动恒开；当次击破段钉 S10（E8 同族）。叠层伴随：第 2 发 @1 层."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="24000"), "physical",
            enemies=_fragile_toughness("physical")))
        _cast(eng, "1408", "140801")   # 削韧 10 → 当次击破
        assert "LC_24000_DMG_BONUS" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801")   # 击破后：增伤 12% + 韧性区 1.0 + @1 层
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC24000_ATK

        assert ours[0] == pytest.approx(1.0 * white * 1.5 * Z_PH, rel=REL_TOL), (
            "当次击破段无增伤")
        hand2 = 1.0 * (white * 1.5 + white * 0.08) * 0.5 * 1.0 * (1 + PH_CR * PH_CD) * 1.12
        assert ours[1] == pytest.approx(hand2, rel=REL_TOL), "击破后普攻 vs 手算"
        # 击破后行动双方比等（对方钉已击破 + 增伤开关 + @1 层）
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC24000_ATK,
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": True,
                   "count": 1},
            equipment=_lc("24000", "Destruction", {
                "atkBoostStacks": 1, "weaknessBreakDmgBuff": True})))
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        # S10：当次击破段对方（未击破+开关）恰为 ×1.12
        theirs_first = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC24000_ATK,
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 1},
            equipment=_lc("24000", "Destruction", {
                "atkBoostStacks": 0, "weaknessBreakDmgBuff": True})))
        assert theirs_first["hits"][0]["damage"] / ours[0] == pytest.approx(1.12, rel=REL_TOL)


class TestLC21012SecretVow:
    """秘密誓心 S1（白厄）：常驻增伤 20%（属性段）+ HP% 比较额外 20% 待收（S11 钉）."""

    def test_permanent_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21012"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21012_ATK, extra_attacker={"dmg_boost": 0.2},
            equipment=_lc("21012", "Destruction", {"enemyHpHigherDmgBoost": False})))

        white = PH_ATK + LC21012_ATK
        hand = 1.0 * white * 1.5 * Z_PH * 1.2
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_hp_higher_divergence(self, optimizer_driver):
        """S11 结构差：目标 HP%≥自身 HP% 额外 +20%（我方待收——命中域无目标 HP
        通道在案）→ 对方/我方 = 1.4/1.2 = 7/6."""
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21012"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")[0]
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21012_ATK, extra_attacker={"dmg_boost": 0.2},
            equipment=_lc("21012", "Destruction", {"enemyHpHigherDmgBoost": True})))

        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.4, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.4 / 1.2, rel=REL_TOL)


class TestLC21033NowhereToRun:
    """无处可逃 S1（白厄）：常驻攻击 24%（对方控制器空=全走钉死面板）+ 击杀治疗单钉."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21033"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC21033_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21033_ATK,
            extra_attacker={"atk": white * 1.24},
            equipment=_lc("21033", "Destruction", {})))

        hand = 1.0 * (white * 1.74) * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_kill_heal_vs_hand(self, optimizer_driver):
        """击杀治疗（对方控制器空=未建模——我方 vs 手算单钉）：
        heal = 12%×击杀时刻面板 atk（白值×1.74）."""
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="21033"), "physical",
            enemies=_kill_enemies("physical")))
        heal_log = []
        eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: heal_log.append(dict(p)))
        st = eng.state.actors["1408"]
        st.current_hp = 100.0   # 压血防溢出封顶（缺口 ≫ 治疗量）
        _cast(eng, "1408", "140801", target="e2")   # 击杀 → on_kill 回血
        white = PH_ATK + LC21033_ATK
        hand_heal = 0.12 * (white * 1.74)
        assert len(heal_log) == 1 and heal_log[0]["target"] == "1408"
        assert heal_log[0]["amount"] == pytest.approx(hand_heal, rel=REL_TOL), (
            "我方击杀治疗 vs 手算（对方未建模——结构注记）")


class TestLC21019UnderTheBlueSky:
    """在蓝天下 S1（白厄）：常驻攻击 16% + 击杀暴击 12% 3回合."""

    def test_permanent_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21019"), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC21019_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21019_ATK,
            extra_attacker={"atk": white * 1.16},
            equipment=_lc("21019", "Destruction", {"defeatedEnemyCrBuff": False})))

        hand = 1.0 * (white * 1.66) * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_kill_cr(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1408", lc="21019"), "physical",
            enemies=_kill_enemies("physical")))
        _cast(eng, "1408", "140801", target="e2")
        assert "LC_21019_CRITRATE_ON_KILL" in eng.state.actors["1408"].modifiers
        _cast(eng, "1408", "140801", target="e1")
        ours = _hit_amounts(log, source="1408", target="e1")
        white = PH_ATK + LC21019_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=LC21019_ATK,
            extra_attacker={"atk": white * 1.16},
            equipment=_lc("21019", "Destruction", {"defeatedEnemyCrBuff": True})))

        hand = 1.0 * (white * 1.66) * 0.5 * 0.9 * (1 + 0.29 * PH_CD)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方击杀后普攻（CR+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC20016MutualDemise:
    """俱殁 S1（白厄）：HP<80% 暴击 12%（条件光环现场重估 vs 对方状态钉）."""

    def test_low_hp_cr(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="20016"), "physical"))
        st = eng.state.actors["1408"]
        st.current_hp = 0.5 * st.actor.stats.hp   # <80% → 光环开
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=370.44,
            equipment=_lc("20016", "Destruction", {"selfHp80CrBuff": True})))

        white = PH_ATK + 370.44
        hand = 1.0 * white * 1.5 * 0.5 * 0.9 * (1 + 0.29 * PH_CD)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方半血（CR+12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_full_hp_gate_off(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="20016"), "physical"))
        _cast(eng, "1408", "140801")   # 满血 → enable_if 灭
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", lc_atk=370.44,
            equipment=_lc("20016", "Destruction", {"selfHp80CrBuff": False})))

        white = PH_ATK + 370.44
        hand = 1.0 * white * 1.5 * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方满血（光环灭）vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC21058TrailOfBygoneBlood:
    """一行往日的血 S1（白厄）：CR 12%（属性段）+ 战技/终结技增伤 24% 常驻."""

    def test_skill(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1408", lc="21058"), "physical"))
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        white = PH_ATK + LC21058_ATK
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "skill", lc_atk=LC21058_ATK, extra_attacker={"cr": PH_CR + 0.12},
            equipment=_lc("21058", "Destruction", {"skillUltDmgBoost": True})))

        hand = 3.0 * white * 1.5 * 0.5 * 0.9 * (1 + 0.29 * PH_CD) * 1.24
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方战技（CR12%+增伤24%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# 光锥对拍——记忆载体（遐蝶 1407）
# ===========================================================================

class TestLC24005MemorysCurtain:
    """记忆永不落幕 S1（遐蝶）：SPD 6%（属性段）+ 战技后全队增伤 8%（窗口族 S12 钉）."""

    def test_spd_and_post_skill_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", lc="24005"), "quantum"))
        assert _eff_spd(eng, "1407") == pytest.approx(95 * (1 + 0.4 + 0.06), rel=REL_TOL), (
            "我方速度面板（行迹 40% + 属性段 6% 同白值基数）")
        _cast(eng, "1407", "140702")   # 战技 → 全队增伤挂上（结算后）
        assert "LC_24005_TEAM_DMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        # 生命倍率载体：光锥白值 HP 并入两侧（游戏公式白值口径——ATK 族先例同构）；
        # 战技耗血 → 天赋 1 层（+0.2），对方 talentDmgStacks 钉 1
        hp = CA_HP + 1058.4   # 24005 白值 HP
        theirs_sc = _cas_opt(
            "basic", cond={"talentDmgStacks": 1},
            extra_attacker={"hp": hp, "spd": 95 + 95 * 0.06},
            equipment=_lc("24005", "Remembrance", {"teamDmgBoost": True}))
        theirs_sc["base"] = {"atk": CA_ATK, "hp": hp, "def": CA_DEF, "spd": CA_SPD}
        theirs = run_optimizer(optimizer_driver, theirs_sc)

        hand = 0.5 * hp * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.08 + 0.2)
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), (
            "我方战技后普攻（+8%+天赋 1 层）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(95 * 1.46, rel=REL_TOL), (
            "对方速度面板回显（行迹 SPD_P 0.4 + 钉死 6%）")

    def test_skill_window_divergence(self, optimizer_driver):
        """S12 结构差：对方 mutual FullTeam 恒开含当次战技；我方 on_action 结算后
        挂（当次不吃）→ 当次战技 对方/我方 = 1.224/1.144."""
        eng, log = _make_logged(_compiled(_member_build("1407", lc="24005"), "quantum"))
        _cast(eng, "1407", "140702")
        ours = _hit_amounts(log, source="1407")[0]
        hp = CA_HP + 1058.4
        theirs_sc = _cas_opt(
            "skill", extra_attacker={"hp": hp},
            equipment=_lc("24005", "Remembrance", {"teamDmgBoost": True}))
        theirs_sc["base"] = {"atk": CA_ATK, "hp": hp, "def": CA_DEF, "spd": CA_SPD}
        theirs = run_optimizer(optimizer_driver, theirs_sc)

        hand_ours = 0.5 * hp * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q)
        assert ours == pytest.approx(hand_ours, rel=REL_TOL), "我方当次战技（无增伤）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            1.224 / 1.144, rel=REL_TOL)


# ===========================================================================
# 遗器对拍（基础件 p2c/p4c 两侧各自原生通道）
# ===========================================================================

class TestRelic102Musketeer:
    """快枪手（黑塔）：2pc 攻击 12% + 4pc 速度 6%/普攻增伤 10%（BASIC 标签门控）."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="102", pieces=4), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", equipment=_relic("102", 4, {"enabledMusketeerOfWildWheat": True})))

        hand = 1.0 * HT_ATK * 1.12 * Z * 1.1
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻（2pc+4pc）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(106.0, rel=REL_TOL), (
            "对方 p4c SPD_P 6% c→x 通道")
        assert _eff_spd(eng, "1013") == pytest.approx(106.0, rel=REL_TOL)

    def test_skill_no_boost(self, optimizer_driver):
        """战技不吃普攻增伤（对方 BASIC 标签闸 ≡ 我方 dmg_basic 类型桶）."""
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="102", pieces=4), "ice"))
        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "skill", equipment=_relic("102", 4, {"enabledMusketeerOfWildWheat": True})))

        hand = 1.0 * HT_ATK * 1.12 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic104Hunter:
    """密林卧雪的猎人（黑塔）：2pc 冰伤 + 4pc 终结技后暴伤 25%（窗口族 S14 钉）."""

    def test_2pc_ice(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="104", pieces=2), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", equipment=_relic("104", 2, {"enabledHunterOfGlacialForest": True})))

        hand = 1.0 * HT_ATK * Z * 1.1
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_post_ult_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="104", pieces=4), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        assert "SET_104_ULT_CRITDMG" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", equipment=_relic("104", 4, {"enabledHunterOfGlacialForest": True})))

        hand = 1.0 * HT_ATK * 0.5 * 0.9 * (1 + 0.05 * 0.75) * 1.1
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方大招后普攻（CD+25%）vs 手算"
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_window_divergence(self, optimizer_driver):
        """S14 结构差：对方 enabled 恒开含当次大招；我方 on_ultimate 结算后挂
        → 当次大招 对方/我方 = 1.0375/1.025 = 83/82."""
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="104", pieces=4), "ice"))
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")[0]
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", equipment=_relic("104", 4, {"enabledHunterOfGlacialForest": True})))

        assert ours == pytest.approx(2.0 * HT_ATK * Z * 1.1, rel=REL_TOL), (
            "我方当次大招（无 CD 件）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(83 / 82, rel=REL_TOL)


class TestRelic105Champion:
    """街头出身的拳王（白厄）：2pc 物伤 + 4pc 攻击叠层 5%×5（对方 value 钉层）."""

    def test_2pc_physical(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1408", set_id="105", pieces=2), "physical"))
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", equipment=_relic("105", 2, {"valueChampionOfStreetwiseBoxing": 0})))

        hand = 1.0 * PH_ATK * 1.5 * Z_PH * 1.1
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_4pc_five_stacks(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1408", set_id="105", pieces=4), "physical"))
        for _ in range(6):
            _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _pha_opt(
            "basic", equipment=_relic("105", 4, {"valueChampionOfStreetwiseBoxing": 5})))

        # 命中序 = [①@0 … ⑥@5层]（层在行动后挂=当次不吃；钳 5）
        hand6 = 1.0 * (PH_ATK * 1.5 + PH_ATK * 0.25) * Z_PH * 1.1
        assert ours[5] == pytest.approx(hand6, rel=REL_TOL), "我方第 6 发（@5 层）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand6, rel=REL_TOL)
        assert ours[5] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic108Genius:
    """繁星璀璨的天才（遐蝶）：2pc 量子伤 + 4pc 穿透 10%（量子弱点额外 10% 待收 S13 钉）."""

    def test_4pc_def_pen(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="108", pieces=4), "quantum"))
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _cas_opt(
            "basic", equipment=_relic("108", 4, {"enabledGeniusOfBrilliantStars": False})))

        hand = 0.5 * CA_HP * (100 / 190) * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1)
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方 2pc+4pc（穿透 10% → 100/190）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(100 / 190, rel=REL_TOL)

    def test_quantum_weakness_divergence(self, optimizer_driver):
        """S13 结构差：量子弱点额外穿透 10%（我方待收——scoped def_pen 通道缺在案；
        量子弱点假人在案=官方 20% 档）→ (100/180)/(100/190) = 19/18."""
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="108", pieces=4), "quantum"))
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")[0]
        theirs = run_optimizer(optimizer_driver, _cas_opt(
            "basic", equipment=_relic("108", 4, {"enabledGeniusOfBrilliantStars": True})))

        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(100 / 180, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(19 / 18, rel=REL_TOL)


class TestRelic110Eagle:
    """晨昏交界的翔鹰（刻律德菈——风载体唯一已注册）：2pc 风伤门控；4pc 推条未拍."""

    def test_2pc_wind(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1412", set_id="110", pieces=2), "wind"))
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _cer_opt(
            "basic", equipment=_relic("110", 2, {"enabledEagleOfTwilightLine": True})))

        hand = 1.0 * CY_ATK * (1 + CY_WIND + 0.1) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方风伤 2pc vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 p2c 元素门控（wind ✓）")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic111Thief:
    """流星追迹的怪盗（黄泉）：BE 16%×2 面板锚（直伤无消费）+ 击破回能注记."""

    def test_be_panel_and_neutral(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="111", pieces=4), "thunder"))
        assert _eff(eng, "1308")["break_effect"] == pytest.approx(0.32), (
            "我方 2pc+4pc BE 32%（面板锚——直伤无消费）")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment=_relic("111", 4, {"enabledThiefOfShootingMeteor": True})))

        hand = 1.0 * AC_ATK * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "直伤中性（BE 无消费）"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["be"] == pytest.approx(0.32, rel=REL_TOL), (
            "对方 p2c+p4c BE c→x 通道")


class TestRelic112Wastelander:
    """盗匪荒漠的废土客（真理医生）：2pc 虚数伤 + 4pc scoped 双暴待收（S15 钉）."""

    def test_2pc_imaginary(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="112", pieces=4), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", equipment=_relic("112", 4, {"valueWastelanderOfBanditryDesert": 0})))

        hand = 1.0 * _rt_panel() * ZR * 1.1
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_debuff_cr_divergence(self, optimizer_driver):
        """S15 结构差：对负面敌 CR+10%（我方待收——scoped 双暴无消费端在案；
        禁锢 CD+20% 同案）→ 钉 1 档：1.135/1.085."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="112", pieces=4), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", equipment=_relic("112", 4, {"valueWastelanderOfBanditryDesert": 1})))

        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.135, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.135 / 1.085, rel=REL_TOL)


class TestRelic113Longevous:
    """宝命长存的莳者（黄泉）：2pc 生命 12%（面板锚）+ 4pc 受击叠层 CR 8%×2."""

    def test_4pc_two_stacks(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="113", pieces=4), "thunder"))
        # 手发受击 2 次（reason=hit——官方文本两类之一；wave-1 合成事件先例）
        for _ in range(2):
            eng.bus.emit("on_hp_decrease", {
                "target": "1308", "reason": "hit", "source": "e1", "amount": 10.0},
                eng.state)
        assert eng.state.actors["1308"].modifiers["SET_113_4PC_CRITRATE"].stacks == 2
        assert _eff(eng, "1308")["hp"] == pytest.approx(1125.432 * 1.12), (
            "我方 2pc 生命（面板锚——不进伤害式）")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment=_relic("113", 4, {"valueLongevousDisciple": 2})))

        hand = 1.0 * AC_ATK * 0.5 * 0.9 * (1 + 0.21 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 2 层 CR vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["hp"] == pytest.approx(1125.432 * 1.12, rel=REL_TOL), (
            "对方 p2c HP_P c→x 通道")


class TestRelic114Messenger:
    """骇域漫游的信使（黄泉）：2pc 速度 6%（面板锚）；4pc 全队速度未拍（在案）."""

    def test_2pc_spd(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="114", pieces=2), "thunder"))
        assert _eff_spd(eng, "1308") == pytest.approx(101 * 1.06, rel=REL_TOL)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment=_relic("114", 2, {"enabledMessengerTraversingHackerspace": False})))

        hand = 1.0 * AC_ATK * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "直伤中性（速度无消费）"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(101 * 1.06, rel=REL_TOL), (
            "对方 p2c SPD_P c→x 通道")


class TestRelic120Valorous:
    """风举云飞的勇烈（黑塔）：2pc 攻击 + 4pc 暴击 6% + 追击后终结技增伤 36%."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="120", pieces=4), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", equipment=_relic("120", 4, {"enabledTheWindSoaringValorous": False})))

        hand = 1.0 * HT_ATK * 1.12 * 0.5 * 0.9 * (1 + 0.11 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 2pc+4pc 暴击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_post_fua_ult(self, optimizer_driver):
        """追击后终结技增伤 36%：黑塔追击=hook deal_damage 无 on_action(follow_up)
        （引擎通道缺口在案）——手发等价事件（wave-1 合成事件先例/120 e2e t_fua 同口径）."""
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="120", pieces=4), "ice"))
        eng.bus.emit("on_action", {
            "actor": "1013", "action_type": "follow_up", "action_id": "101304",
            "target_type": "single", "target": "e1", "actor_type": "character"},
            eng.state)
        assert "SET_120_ULT_DMG" in eng.state.actors["1013"].modifiers
        _ult(eng, "1013", "101303", 110.0)
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "ult", equipment=_relic("120", 4, {"enabledTheWindSoaringValorous": True})))

        hand = 2.0 * HT_ATK * 1.12 * 0.5 * 0.9 * (1 + 0.11 * 0.5) * 1.36
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方追击后大招（+36%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic122Scholar:
    """识海迷坠的学者（真理医生）：2pc 暴击 8% + 4pc 战技/终结技 20% + 闩下次战技 25%."""

    def test_skill(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="122", pieces=4), "imaginary"))
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", equipment=_relic("122", 4, {"enabledScholarLostInErudition": False})))

        hand = 1.5 * _rt_panel() * 0.5 * 0.9 * (1 + 0.25 * 0.5) * 1.2
        assert ours[0] == pytest.approx(hand, rel=REL_TOL), "我方战技（CR8%+增伤20%）vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_post_ult_skill(self, optimizer_driver):
        """闩下次战技 25%：我方 on_ultimate 闩（行动次数型时长——终结技 on_action
        不误吞）≡ 对方 enabled 开关."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="122", pieces=4), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        assert "SET_122_NEXT_SKILL_DMG_UP" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")   # [大招, 战技, 追击]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", equipment=_relic("122", 4, {"enabledScholarLostInErudition": True})))

        hand = 1.5 * _rt_panel() * 0.5 * 0.9 * (1 + 0.25 * 0.5) * 1.45
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), (
            "我方大招后战技（20%+闩 25%）vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic123HeroOfTriumphantSong:
    """凯歌祝捷的英豪（遐蝶）：2pc 攻击（生命倍率载体=面板锚）+ 4pc 忆灵在场速度
    6% + 忆灵攻击后双实体暴伤 30%（对方 enabled=SelfAndMemosprite 恒开）."""

    def test_memo_attack_then_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="123", pieces=4), "quantum"))
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 召唤死龙
        log.clear()
        _cast(eng, "1407_netherwing", "1140702")   # 忆灵攻击 → 4pc CD 双挂
        assert "SET_123_CRITDMG" in eng.state.actors["1407"].modifiers
        assert "SET_123_CRITDMG" in eng.state.actors["1407_netherwing"].modifiers, (
            "忆灵侧同挂（对方 SelfAndMemosprite 同构）")
        log.clear()
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _cas_opt(
            "basic", cond={"memospriteActive": True, "teamDmgBoost": True,
                           "talentDmgStacks": 1},
            equipment=_relic("123", 4, {"enabledHeroOfTriumphantSong": True})))

        # 暴伤 0.633+0.30；增伤 = 量子 0.144 + 怒啸 0.1 + 天赋 1 层 0.2（焰息耗血叠）
        hand = 0.5 * CA_HP * 0.5 * 0.9 * (1 + CA_CR * (CA_CD + 0.3)) \
            * (1 + CA_Q + 0.1 + 0.2) * 1.2
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方忆灵攻击后普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["spd"] == pytest.approx(95 * 1.46, rel=REL_TOL), (
            "对方 SPD_P 6%（忆灵在场档）白值换算")
        assert theirs["entity_stats"][1]["cd"] == pytest.approx(CA_CD + 0.3, rel=REL_TOL), (
            "对方忆灵实体暴伤回显（SelfAndMemosprite 落点）")


class TestRelic127WorldRemakingDeliverer:
    """再创天地的救世主（遐蝶）：2pc 暴击 8% + 4pc 忆灵在场生命 24%/全队增伤 15%
    （A 钩摘+B 钩重挂=常驻刷新；对方 enabled 恒开无窗口——S16 钉）."""

    def test_post_skill_basic_with_memo(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="127", pieces=4), "quantum"))
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))
        log.clear()
        _cast(eng, "1407", "140702")   # 战技（当次不吃）→ B 钩忆灵在场重挂
        assert "SET_127_TEAM_DMG" in eng.state.actors["1407"].modifiers
        _cast(eng, "1407", "140701")   # 普攻：生命 24% + 增伤 15% + 天赋 1 层
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _cas_opt(
            "basic", cond={"memospriteActive": True, "teamDmgBoost": True,
                           "talentDmgStacks": 2},
            equipment=_relic("127", 4, {"enabledWorldRemakingDeliverer": True})))

        crit = 1 + (CA_CR + 0.08) * CA_CD
        # 战技耗血 → 天赋实测 2 层（+0.4——140702 全队耗血 40% 跨两档，引擎实证）
        hand = 0.5 * (CA_HP * 1.24) * 0.5 * 0.9 * crit * (1 + CA_Q + 0.1 + 0.4 + 0.15) * 1.2
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), (
            "我方战技后普攻（HP24%+增伤15%+天赋2层）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_window_divergence(self, optimizer_driver):
        """S16 结构差：对方 enabled 恒开含当次战技（HP24%+增伤15%）；我方结算后挂
        → 当次战技 对方/我方 = 1.24×1.394/1.244."""
        eng, log = _make_logged(_compiled(
            _member_build("1407", set_id="127", pieces=4), "quantum"))
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))
        log.clear()
        _cast(eng, "1407", "140702")
        ours = _hit_amounts(log, source="1407")[0]
        # 对方 memospriteActive=True 时 skill 段=140709 强化连携（段形不可比）——
        # 钉常态战技 + res_pen/怒啸双钉（乘区两侧对消：我方境界原生 vs 对方钉死）
        theirs = run_optimizer(optimizer_driver, _cas_opt(
            "skill", cond={"memospriteActive": False, "teamDmgBoost": True,
                           "talentDmgStacks": 0},
            extra_attacker={"res_pen": 0.2},
            equipment=_relic("127", 4, {"enabledWorldRemakingDeliverer": True})))

        crit = 1 + (CA_CR + 0.08) * CA_CD
        hand_ours = 0.5 * CA_HP * 0.5 * 0.9 * crit * (1 + CA_Q + 0.1) * 1.2
        assert ours == pytest.approx(hand_ours, rel=REL_TOL), (
            "我方当次战技（无 4pc 件）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(
            1.24 * (1 + CA_Q + 0.1 + 0.15) / (1 + CA_Q + 0.1), rel=REL_TOL)


class TestRelic131Navigator:
    """星如我见的领航员（真理医生）：2pc 攻击 12% + 4pc 进战 1 层/战技叠层
    战技·终结技增伤 18%×N（钳 3；对方 value 钉层）."""

    def test_skill_ramp(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", set_id="131", pieces=4), "imaginary"))
        _cast(eng, "1305", "130502")
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")   # [战技①, 追击①, 战技②, 追击②]
        white_panel = RT_ATK * 1.28 + RT_ATK * 0.12   # 行迹 28% + 2pc 12%（同白值基数）
        z = 0.5 * 0.9 * (1 + RT_CR * RT_CD)
        # 层在行动后挂=当次不吃：战技①@进战 1 层（18%）→ 战技②@2 层（36%）
        assert ours[0] == pytest.approx(1.5 * white_panel * z * 1.18, rel=REL_TOL), (
            "我方战技①（@1 层）vs 手算")
        # 追击① → 归纳 1 层（CR+2.5%/CD+5%——真理行迹，L2 先例）推高战技②暴击区
        z2 = 0.5 * 0.9 * (1 + (RT_CR + 0.025) * (RT_CD + 0.05))
        assert ours[2] == pytest.approx(1.5 * white_panel * z2 * 1.36, rel=REL_TOL), (
            "我方战技②（@2 层+归纳 1 层）vs 手算")
        theirs1 = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", equipment=_relic("131", 4, {"valueAsNavigatorIseeSeesIt": 1})))
        theirs2 = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", conditionals={"summationStacks": 1},
            equipment=_relic("131", 4, {"valueAsNavigatorIseeSeesIt": 2})))
        assert ours[0] == pytest.approx(theirs1["hits"][0]["damage"], rel=REL_TOL)
        assert ours[2] == pytest.approx(theirs2["hits"][0]["damage"], rel=REL_TOL)
