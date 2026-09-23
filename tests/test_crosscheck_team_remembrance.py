"""L2 角色级 + L4 组队级对拍（BACKLOG B22 名册扩拍第二波）：记忆战舰 4 角色——
遐蝶 1407（死龙：跨实体缩放/特殊充能/耗血产蕊）/ 长夜月 1413（长夜：忆质驱动变档倍率/
暴伤换算光环=dynamic conditional 首接）/ 风堇 1409（小伊卡：治疗 tally→伤害转换链=
HealTallyDamageFunction 首接）/ 昔涟 1415（德谬歌：结界真伤/追忆特殊充能/献予诗系）。
逐段伤害 == hsr-optimizer 角色实现整链伤害（rel_tol 1e-4；双锚=对方+手算，
对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（memo_skill/memo_talent/
skill_heal/ult_heal 新技种 + 忆灵面板镜像 + 寄存器回写 + dynamic conditionals 镜像——
驱动头注有完整口径）。我方路径：真模板（tests/fixtures 人工根）→ 编译 → CombatEngine
钉资源 → _cast/_fire_ultimate/dismiss_summon_actor → bus on_hp_decrease 逐段记录仪
（setup 前订阅，L2 先例）+ on_hp_increase 治疗记录仪（风堇组）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级、无光锥无遗器、假人 lvl80
def 1000（防御区 0.5）、匹配弱点（抗性区 1.0）、未击破（0.9）、期望暴击。
**忆灵槽等级口径**：E0 上限 lv6（本波勘正——三源互证：对方全角色忆灵技按 lv6 取值
（焰息 0.24/0.28/0.34=lv6 行）；fandom 忆灵技能表渲染封顶 lv7；星魂原文
"Memosprite Skill Lv. +1, up to a maximum of Lv. 10"与普攻（E0 上限 6）同构，
异于战技（E0 上限 10））。我方编译器种子 10→6 已修（B-NEW⑦，见下）。

===========================================================================
遐蝶 1407 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
buffPriority（MEMO）           面板优先级（无伤害语义）                        钉 MEMO 无害
memospriteActive（true）       死龙在场（140703 召唤 + 遗世冥域 res_pen 0.2）  按场钉——死龙链钉 true，
                                                                            单人链钉 false
spdBuff（true）                1407102 倒置的火炬：HP≥50% → spd_pct +40%       满血场钉 true（enable_if 自动挂）
                                                                            （速度无伤害消费——面板回显闸）
talentDmgStacks 0-3（3）       140704 荒芜增伤 0.2×层（失 HP 叠层，双方同挂）   按失 HP 事件数实打喂出后逐档钉
memoSkillEnhances 1-3（3）     焰息连发档（0.24/0.28/0.34 lv6）                连发第 N 发钉 N
memoTalentHits 0-6（6）        1140706 晦翼 6 段（对方聚合单发 6×0.40）        钉 6——段数差在案（对方聚合）
teamDmgBoost（true）           1140705 怒啸：被召唤全体增伤 10% 3 回合         死龙在场钉 true
memoDmgStacks 0-6（3）         1407103 西风驻足 0.3×层（焰息施放叠层，死龙侧）  按焰息计数实打喂出后逐档钉
cyreneSpecialEffect（true）    1141517 献予「生死」（无昔涟场景恒 0）           无昔涟钉 false；昔涟场见 T-CY3
e1EnemyHp50（true，E1）        E1 低血真伤追加段（E0 门控同灭）                 E0 钉 true 无害
e6Buffs（true，E6）            E6 量子抗穿+晦翼 +3 段（E0 门控同灭）            E0 钉 true 无害
（无开关）战技 blast 相邻段     140702 相邻 0.3×2                              对方收敛主目标单发（D6 同族）
                                                                            ——主段比等，相邻手算自证
（无开关）强化战技两段分账       140709 遐蝶半 0.3 + 死龙半 0.5（耗血天赋计入     对方双 hit 同场景共享钉死层数——
                               死龙半不含遐蝶半——on_action 序在案；死龙半源=   分两场各钉 0/1 层比对对应段
                               死龙，R-CY3 收官：死龙侧 hook+max_hp_of('1407')）

===========================================================================
长夜月 1413 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
buffPriority（MEMO）           无伤害语义                                     钉 MEMO 无害
memoTalentDmgBuff（true）      1141303 孤独：双方增伤 50%（lv6——开局召唤自动挂）钉 true（EVE_SOLITUDE 双件）
traceCritBuffs（true）         1413101 天黑黑：CR+35%（烘焙面板）/施放耗血 CD+15% 钉 true（CR 已烘焙；CD 经施放
                                                                            实打喂出——EVE_TRACE_CRIT）
skillMemoCdBuff（true）        141302 光环：忆灵 CD=长夜月 CD×24%+天亮了档      钉 true——对方 dynamic 件
                                                                            （EvernightCdConditional）driver 已镜像；
                                                                            我方快照口径=第二次施放战技后全等
talentMemoCdBuff（true）       141304 失 HP 双方 CD+60%（lv10）                钉 true（战技耗血实打喂出）
memoriaStacks 0-40（16）       忆质计数（追加段 0.10/4 点；≥16 如露档）         按场钉（我方 resource 直读+实打）
enhancedState（true）          至暗之谜：双方增伤 60%+敌方易伤 30%              终结技后钉 true；终结技当发
                                                                            钉 false（官方序 AoE 先于入状态——
                                                                            对方 pinned 覆盖当发=建模序差，钉 R-EV1）
cyreneSpecialEffect（true）    1141524 献予「岁月」（无昔涟恒 0）               无昔涟钉 false
e1FinalDmg/e2CdBuff/e4Buffs/e6ResPen  星魂（E0 门控同灭）                       E0 钉 true 无害
（无开关）141303 终结技 AoE     U1 忆灵侧 hook 2.0×长夜上限                     对方 ULT 段（长夜 source）比等
（无开关）1141307 主/余分裂     每点 0.12 主 / 0.06 余（我方 AoE+主补差两段化）   对方主目标收敛单发——主段比等，
                                                                            相邻手算自证（D6 同族）
（无开关）1141301 忆质追加段    主段 0.5 + 追加 (n//4)×0.10（我方两 hit 分账）    对方聚合单发 0.5+(n//4)×0.10——
                                                                            总和比等，段数差在案

===========================================================================
风堇 1409 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
healAbility（SKILL）           tally 引用治疗档（战技 0.08×HP+160）             钉 SKILL（ULT 档同构不接）
buffPriority（MEMO）           无伤害语义                                     钉 MEMO 无害
clearSkies（true）             雨过天晴：全队 HP+600+30%（140903 终结技挂）      终结技后钉 true
healTargetHp50（true）         1409101 阴云莞尔：受疗者 HP≤50% → 治疗量+25%     按受疗者血档两态各钉
resBuff（true）                1409102 效果抵抗+50%（烘焙 0.68）                无伤害消费——钉 true 无害
spd200HpBuff（true）           1409103 暴风停歇：spd>200 双方 HP+20%、超档       钉 true——对方 dynamic 件
                               治疗量+1%/点（≤200）                           （HyacineSpdActivation/Conversion）
                                                                            driver 已镜像；低速场两侧同灭
healingDmgStacks 0-3（3）      140904 疗愈晨曦：小伊卡增伤 0.8×层（治疗实例叠层）按治疗实例数实打喂出后逐档钉
healTallyMultiplier 1-100（20）tally 假定值=引用治疗×倍率（对方建模近似——       钉 = 我方实际 tally / 引用治疗值
                               真实 tally=本场累计治疗）                     （等价锚定——比值恰为 tally 比）
e1HpBuff/e2SpdBuff/e4CdBuff/e6ResPen  星魂（E0 门控同灭）                       E0 钉 true 无害
（无开关）小伊卡双段治疗         140902/140903 小伊卡段（0.10+200 / 0.12+240）   对方只建除小伊卡段——小伊卡段
                                                                            手算自证（D6 同族）

===========================================================================
昔涟 1415 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
buffPriority（SELF）           无伤害语义                                     钉 SELF 无害
memospriteActive（true）       涟漪态（141503 首开：德谬歌+双方 CR+50%+          涟漪场钉 true；涟漪前钉 false
                               双方 HP+24%（lv6）+强化普攻）                  （强化普攻换技两态对齐）
zoneActive（true）             141502 结界（我方真伤追加 24%；对方 TRUE_DMG     结界展开钉 true——对方乘区 vs
                               乘区——数值等价：Σ(段×1.24)≡Σ段×1.24）          我方追加段，总和比等
talentDmgBuff（true）          141504 全队增伤 20% 光环（开局自动挂）           钉 true
traceSpdBasedBuff（true）      1415103 三相：spd≥180 全队增伤 20%+双方冰抗穿     低速场两侧同灭；spd 190 场
                               min(超出,60)×2%（对方 finalize 档）             比等（我方 _inject 提速）
odeToEgoExtraBounces 0-6（3）  1141526 追加段=不同队友来源追忆−1（×0.60 lv6）   按 unique_sources−1 实打钉
e1ExtraBounces（12，E1）/e2TrueDmgStacks（2，E2）/e4BounceStacks（24，E4）/e6DefPen（E6）  E0 门控同灭
（无开关）德谬歌生命口径        白值 1397.088 烘焙 + 行迹 hp_pct 0.1    已收口（2026-09-23）——白值×(1+HP_P%)
                               镜像（DEM_TRACE_HP）+ DEM_MAXHP            活同步，与对方忆师白值加算
                               hp_pct 0.24（team 光环辐射天然活同步）     逐位一致（R-CY1 转三方相等）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-CY1 德谬歌生命口径——**已收口（2026-09-23）**：旧口径「召唤时刻昔涟有效上限定格
   （max_hp_ratio 1.0）×(1+24%)」快照且行迹 24% 双重计入（1.1×1.24 vs 1.34=恰差
   1.0179104）；owner 查证（百度百科/BWIKI「昔涟的生命值百分比变化时，德谬歌的生命值
   百分比也会相应变化」+ KQM「忆灵白值=忆师白值」）定论：德谬歌生命上限 = 昔涟**白值**
   ×(1+HP_P%) **活同步**。收口口径：白值 1397.088 烘焙（summons base_stats）+ HP_P 池 =
   行迹 0.1 镜像件（DEM_TRACE_HP）+ DEM_MAXHP 0.24（hp_pct 同池白值乘算不双重计），
   team 光环辐射天然活同步（界外同侧）——与对方忆师白值加算 1872.09792 逐位一致，
   Minuet 类（德谬歌基数段）三方相等转正式（test_minuet_demiurge_scaling；
   昔涟本人段两侧本就全等）
R-EV1 长夜月终结技当发的至暗件覆盖窗（官方序"召唤→AoE→进入至暗之谜"——我方
   AoE 不吃增伤 0.6/易伤 0.3；对方 pinned enhancedState 覆盖当发=建模近似）
   → 终结技当发 对方/我方 恰为 (2.1/1.5)×1.3 = 1.82
R-CY2 昔涟 teammate 链三相增伤（对方 precomputeTeammateEffects 的 cyreneSpdDmg
   无速度门控常开 0.2——主角色链 finalize 有门控；我方 1415103 enable_if
   spd≥180 两侧一致）→ 对方/我方 恰为 (1+0.144+0.2+0.2)/(1+0.144+0.2)
   = 1.544/1.344 ≈ 1.1488095（昔涟 spd 110 场）
R-CY3 140709 死龙半面板归属——**已收口（2026-09-17）**：旧压缩口径「忆灵继承忆师
   面板 ⇒ 挂哪边等价」仅在对称 buff 下成立；长夜月光环/天亮了（忆灵限定 CD，不落
   遐蝶）与长夜月 E1（忆灵限定 final 独立乘区）在场即破。收口口径：死龙半/爪痕 hook
   挪死龙侧（$self=死龙面板，忆灵限定 buff 自动全吃）+ 基数 max_hp_of('1407') 跨
   actor 读忆师——与对方 hit 双引用（sourceEntity=死龙 + scalingEntity=遐蝶）1:1
   同构；组合场三方相等（死龙 CD 1.61492 全链），E1 场四档（敌数 4+/3/2/1 →
   ×1.2/1.25/1.3/1.5）三方比对见 TestEvernightToCastorice::test_e1_final_dmg_
   on_netherwing_half。**晦翼+E6 追加段残留同日收口（时序扶正）**：引擎新发射点
   before_actor_exit（alive=False 之前——死龙在世，alive 闸不挡；dismiss/death
   双发射点盖倒计时/低血自爆/忆师牵连/被打死），晦翼 6 段+E6 追加 3 段挪死龙侧
   生前自爆（HP 基数 max_hp_of('1407') 同收官批先例）；忆灵限定 buff 对 9 段
   全通——光环/天亮了场（test_wings_under_halo_and_dawn，段值 820.7547）与
   E1 final 四档（test_e1_final_dmg_on_wings，984.9057/1025.9434/1066.9811/
   1231.1321）三方相等转正式；E0 对称场逐位不变（503.67506876238184，worktree
   对拍实证）；焰息本就走死龙侧 hook，无此差（活证据对拍零差）

已修真病一件（本波钓出——单列）：
B-NEW⑦ 编译器忆灵槽等级种子 10→6（build_compiler._SkillParams 种子 +
   _effective_skill_levels 默认档/cap + 召唤物 skill_levels 继承忆师定稿档）：
   E0 忆灵技/忆灵天赋游戏内上限 lv6（三源互证见上），旧种子 lv10 全线高估
   （焰息 0.336 vs 0.24 = 1.4×）；四 fixture E3/E5 补忆灵槽 +1 覆写（lv7 随档），
   四个 e2e 文件重基线（lv10→lv6 常量）。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    _POLICY, _cast, _dummy, _hit_amounts, _inject, _make_logged, _stage,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture 终审值，行迹平铺按模板 trace_stat_effects 并入）
# ---------------------------------------------------------------------------

# 遐蝶 1407（量子，生命倍率）
CA_HP, CA_ATK, CA_DEF, CA_SPD = 1629.936, 523.908, 485.1, 95
CA_CR, CA_CD, CA_Q = 0.237, 0.633, 0.144
Z_CA_CRIT = 1 + CA_CR * CA_CD                    # 1.150021
NW_HP = 34000.0                                  # 死龙 = 新蕊上限（ult lv10 #3）

# 长夜月 1413（冰，生命倍率）
EV_HP_W = 1319.472
EV_HP = EV_HP_W * 1.18                           # 1556.97696（行迹 hp_pct 0.18）
EVEY_HP = EV_HP * 0.5                            # 778.48848（141304 #5）
EV_CR, EV_CD = 0.587, 0.633                      # CR 含天黑黑 35% 烘焙
EVEY_CD_FULL = 0.633 + 0.6 + 0.15 + 0.05 + 0.24 * (0.633 + 0.6 + 0.15)   # 1.76492
Z_EV_CRIT = 1 + EV_CR * EV_CD                    # 1.371571
Z_EVEY_CRIT = 1 + EV_CR * EVEY_CD_FULL           # 2.035919…

# 风堇 1409（风，生命倍率/治疗）
HY_HP_W = 1086.624
HY_HP = HY_HP_W * 1.1                            # 1195.2864（行迹 hp_pct 0.1）
HY_SPD = 124
IKA_HP = HY_HP * 0.5                             # 597.6432（140904 #1）
HY_SKILL_HEAL = 0.08 * HY_HP + 160               # 255.622912（lv10 #1/#2 除小伊卡）
HY_ULT_HEAL = 0.10 * HY_HP + 200                 # 319.52864（lv10 #1/#2 除小伊卡）

# 昔涟 1415（冰，生命倍率）
CY_HP_W = 1397.088
CY_HP = CY_HP_W * 1.1                            # 1536.7968（行迹 hp_pct 0.1）
CY_HP_FULL = CY_HP_W * 1.34                      # 1872.09792（+德谬歌 24%——双方同值）
CY_CR, CY_CD = 0.05, 0.873
Z_CY_CRIT = 1 + CY_CR * CY_CD                    # 1.04365
Z_CY_RIP = 1 + (CY_CR + 0.5) * CY_CD             # 1.48015（涟漪双方 CR+50%）
DEM_HP_OURS = CY_HP_FULL                    # 1872.09792（R-CY1 收口 2026-09-23：白值×(1+HP_P%) 活同步——与对方同口径逐位一致）
DEM_HP_THEIRS = CY_HP + 0.24 * CY_HP_W      # 1872.09792（对方=忆师白值加算）
R_EV1 = (2.1 / 1.5) * 1.3                        # 1.82（结构差 R-EV1）
R_CY2 = 1.544 / 1.344                            # ≈ 1.1488095（结构差 R-CY2）


# ---------------------------------------------------------------------------
# 我方侧引擎件
# ---------------------------------------------------------------------------

def _solo_build(cid, *, eidolon: int = 0):
    member = {"character_template": cid, "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member], "policy": _POLICY}}


def _solo_compiled(cid, *, enemies):
    return compile_encounter(_solo_build(cid), _stage(enemies),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _fire_ult(eng, owner, aid, *, energy=None, resource=None):
    """钉资源开大（特殊充能族：能量槽无意义——ult_cost_resource 门槛走资源）."""
    st = eng.state.actors[owner]
    if energy is not None:
        st.current_energy = energy
    if resource is not None:
        rid, val = resource
        st.resources[rid] = val
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _inc_log(eng):
    """治疗记录仪：on_hp_increase 有序事件流（amount=实回值）."""
    log = []
    eng.bus.subscribe("on_hp_increase", lambda et, p, ctx: log.append(dict(p)))
    return log


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_castorice(action: str, *, cond: dict | None = None,
                   teammates: list | None = None, enemy_count: int = 1):
    c = {"buffPriority": 1, "memospriteActive": False, "spdBuff": True,
         "talentDmgStacks": 0, "memoSkillEnhances": 1, "memoTalentHits": 6,
         "teamDmgBoost": False, "memoDmgStacks": 0, "cyreneSpecialEffect": False,
         "e1EnemyHp50": True, "e6Buffs": True}
    c.update(cond or {})
    sc = {"kind": "character", "character_id": "1407", "eidolon": 0,
          "action": action, "element": "quantum", "conditionals": c,
          "base": {"atk": CA_ATK, "hp": CA_HP, "def": CA_DEF, "spd": CA_SPD},
          "attacker": {"atk": CA_ATK, "hp": CA_HP, "def": CA_DEF, "spd": CA_SPD,
                       "cr": CA_CR, "cd": CA_CD, "element_boost": CA_Q},
          "self_path": "Remembrance",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": enemy_count}}
    if teammates is not None:
        sc["teammates"] = teammates
    return sc


def _opt_evernight(action: str, *, cond: dict | None = None, enemy_count: int = 1):
    c = {"buffPriority": 1, "memoTalentDmgBuff": True, "traceCritBuffs": True,
         "skillMemoCdBuff": True, "talentMemoCdBuff": False, "memoriaStacks": 0,
         "enhancedState": False, "cyreneSpecialEffect": False,
         "e1FinalDmg": True, "e2CdBuff": True, "e4Buffs": True, "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1413", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": 543.312, "hp": EV_HP_W, "def": 582.12, "spd": 99},
            "attacker": {"atk": 543.312, "hp": EV_HP, "def": 582.12, "spd": 99,
                         "cr": 0.237, "cd": EV_CD},   # CR 0.237：天黑黑 35% 走对方 trace 件
            "self_path": "Remembrance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": enemy_count}}


def _opt_hyacine(action: str, *, cond: dict | None = None, spd: float = HY_SPD):
    c = {"healAbility": 2, "buffPriority": 1, "clearSkies": False,   # 2=DamageType.SKILL
         "healTargetHp50": False, "resBuff": True, "spd200HpBuff": True,
         "healingDmgStacks": 0, "healTallyMultiplier": 20,
         "e1HpBuff": True, "e2SpdBuff": True, "e4CdBuff": True, "e6ResPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1409", "eidolon": 0,
            "action": action, "element": "wind", "conditionals": c,
            "base": {"atk": 388.08, "hp": HY_HP_W, "def": 630.63, "spd": spd},
            "attacker": {"atk": 388.08, "hp": HY_HP, "def": 630.63, "spd": spd,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Remembrance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_cyrene(action: str, *, cond: dict | None = None, spd: float = 110):
    c = {"buffPriority": 0, "memospriteActive": False, "zoneActive": False,
         "talentDmgBuff": True, "traceSpdBasedBuff": True, "odeToEgoExtraBounces": 0,
         "e1ExtraBounces": 12, "e2TrueDmgStacks": 2, "e4BounceStacks": 24,
         "e6DefPen": True}
    c.update(cond or {})
    return {"kind": "character", "character_id": "1415", "eidolon": 0,
            "action": action, "element": "ice", "conditionals": c,
            "base": {"atk": 446.292, "hp": CY_HP_W, "def": 582.12, "spd": spd},
            "attacker": {"atk": 446.292, "hp": CY_HP, "def": 582.12, "spd": spd,
                         "cr": CY_CR, "cd": CY_CD},
            "self_path": "Remembrance",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _tm_cyrene(**cond):
    c = {"zoneActive": True, "cyreneSpdDmg": False, "specialEffect": True,
         "talentDmgBuff": True, "cyreneHp": 10000, "cyreneCr": 1.00,
         "e2TrueDmgStacks": 2, "e6DefPen": True}
    c.update(cond)
    return {"character_id": "1415", "eidolon": 0, "path": "Remembrance",
            "element": "ice", "conditionals": c}


def _tm_evernight(eidolon: int = 0, **cond):
    c = {"enhancedState": True, "cyreneSpecialEffect": False, "skillMemoCdBuff": True,
         "evernightCombatCD": 1.383, "e1FinalDmg": True, "e4Buffs": True,
         "e6ResPen": True}
    c.update(cond)
    return {"character_id": "1413", "eidolon": eidolon, "path": "Remembrance",
            "element": "ice", "conditionals": c}


def _tm_hyacine(**cond):
    c = {"clearSkies": True, "e1HpBuff": True, "e2SpdBuff": True, "e6ResPen": True}
    c.update(cond)
    return {"character_id": "1409", "eidolon": 0, "path": "Remembrance",
            "element": "wind", "conditionals": c}


# ===========================================================================
# L2 遐蝶 1407（对方 1400/Castorice.ts 全实现）——单人链 + 死龙链
# ===========================================================================

class TestCastoriceDuipai:
    """遐蝶 E0：普攻/战技/骸爪双段/焰息连发 ramp/晦翼聚合——双锚+乘区读回."""

    def _ult(self, eng):
        """新蕊钉满实打 140703 → 死龙在场 + 遗世冥域 res_pen 0.2 + 怒啸 0.1."""
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))
        assert "1407_netherwing" in eng.state.actors

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_castorice("basic"))
        st = theirs["stats"]
        assert st["spd"] == pytest.approx(133.0, rel=REL_TOL), (
            "spdBuff SPD_P 0.40 白值换算（倒置的火炬）")
        assert st["hp"] == pytest.approx(CA_HP, rel=REL_TOL)
        assert theirs["entity_stats"][1]["name"] == "Netherwing"
        assert theirs["entity_stats"][1]["hp"] == pytest.approx(NW_HP, rel=REL_TOL), (
            "死龙 34000 常量面板（memoBaseHpFlat——忆灵面板镜像闸）")

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_solo_compiled("1407", enemies=_dummy("e1", "quantum")))
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _opt_castorice("basic"))

        hand = 0.5 * CA_HP * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", Z_CA_CRIT), ("dmgBoostMulti", 1 + CA_Q),
                     ("abilityMulti", 0.5 * CA_HP)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_normal_single(self, optimizer_driver):
        """战技 lv10=0.5 单体场（无死龙——memospriteActive=false 档）：双方全等."""
        eng, log = _make_logged(_solo_compiled("1407", enemies=_dummy("e1", "quantum")))
        _cast(eng, "1407", "140702")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _opt_castorice("skill"))

        hand = 0.5 * CA_HP * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q)
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_blast_three(self, optimizer_driver):
        """战技 blast（对方只建主目标单发=建模收敛，D6 同族）：主 0.5 比等，
        相邻 0.3×2 手算自证（lv10 #2）."""
        eng, log = _make_logged(_solo_compiled(
            "1407", enemies=_dummy("e1", "quantum", n=3)))
        _cast(eng, "1407", "140702", target="e2")
        adj1 = _hit_amounts(log, source="1407", target="e1")
        main = _hit_amounts(log, source="1407", target="e2")
        adj3 = _hit_amounts(log, source="1407", target="e3")
        theirs = run_optimizer(optimizer_driver, _opt_castorice("skill", enemy_count=3))

        z = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q)
        assert main == pytest.approx([0.5 * CA_HP * z], rel=REL_TOL)
        assert main[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert adj1 == pytest.approx([0.3 * CA_HP * z], rel=REL_TOL), "相邻段① vs 手算"
        assert adj3 == pytest.approx([0.3 * CA_HP * z], rel=REL_TOL), "相邻段② vs 手算"

    def test_enhanced_skill_two_segments(self, optimizer_driver):
        """140709 骸爪连携（死龙在场）：遐蝶半 0.3（耗血前=天赋 0 层）+ 死龙半 0.5
        （on_action 耗血 40% 先叠 1 层天赋——死龙半吃 0.2）；境界 1.2+怒啸 0.1 双方同.
        R-CY3 收官后死龙半源=死龙（死龙侧 hook+max_hp_of('1407') 基数）——无忆灵限定
        buff 场与遐蝶面板逐位一致（CD 0.633/增伤池两侧同构），等价口径实证."""
        eng, log = _make_logged(_solo_compiled("1407", enemies=_dummy("e1", "quantum")))
        self._ult(eng)
        log.clear()
        _cast(eng, "1407", "140709")
        ours_cas = _hit_amounts(log, source="1407")
        ours_nw = _hit_amounts(log, source="1407_netherwing")
        theirs0 = run_optimizer(optimizer_driver, _opt_castorice(
            "skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                           "talentDmgStacks": 0}))
        theirs1 = run_optimizer(optimizer_driver, _opt_castorice(
            "skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                           "talentDmgStacks": 1}))

        z0 = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1) * 1.2
        hand_cas = 0.3 * CA_HP * z0
        hand_nw = 0.5 * CA_HP * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1 + 0.2) * 1.2
        assert ours_cas == pytest.approx([hand_cas], rel=REL_TOL), (
            "我方遐蝶半（0 层）vs 手算")
        assert ours_nw == pytest.approx([hand_nw], rel=REL_TOL), (
            "我方死龙半（1 层——源=死龙，对称 buff 场与遐蝶面板逐位一致）vs 手算")
        assert theirs0["hits"][0]["damage"] == pytest.approx(hand_cas, rel=REL_TOL), (
            "对方遐蝶半（talentDmgStacks=0 场）vs 手算")
        assert ours_cas[0] == pytest.approx(theirs0["hits"][0]["damage"], rel=REL_TOL)
        assert theirs1["hits"][1]["damage"] == pytest.approx(hand_nw, rel=REL_TOL), (
            "对方死龙半（talentDmgStacks=1 场——共享钉死层数故分场比对）vs 手算")
        assert ours_nw[0] == pytest.approx(theirs1["hits"][1]["damage"], rel=REL_TOL)
        assert theirs0["hits"][1]["source_entity"] == "Netherwing", (
            "对方死龙半实体归属回显（跨实体缩放段——scaling=遐蝶）")
        assert theirs0["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.2, rel=REL_TOL), (
            "遗世冥域 res_pen 0.2（对方 mutual 全队件）")

    def test_breath_ramp(self, optimizer_driver):
        """焰息三连 ramp（0.24/0.28/0.34 lv6）：耗血叠天赋（0.2/0.4/0.6）+ 西风
        （0/0.3/0.6）逐发实打喂出，对方按档钉死——三发全等."""
        eng, log = _make_logged(_solo_compiled("1407", enemies=_dummy("e1", "quantum")))
        self._ult(eng)
        log.clear()
        ours_chain = []
        for _ in range(3):
            log.clear()
            _cast(eng, "1407_netherwing", "1140702")
            # 每发首 hit=焰息（结算 hook 声明序先于消失钩）：第 3 发满 3 回合带出 1140706
            # 消逝 6 段（旧源=遐蝶被 source 过滤天然出集——时序扶正后同源死龙须按位排除，
            # 消逝段对轴归 test_wings_aggregate 族）
            ours_chain += _hit_amounts(log, source="1407_netherwing")[:1]

        z = 0.5 * 0.9 * Z_CA_CRIT * 1.2
        hands = [
            0.24 * CA_HP * z * (1 + CA_Q + 0.1 + 0.2),          # 第 1 发：天赋 1 层，西风 0
            0.28 * CA_HP * z * (1 + CA_Q + 0.1 + 0.4 + 0.3),    # 第 2 发：天赋 2 层，西风 1
            0.34 * CA_HP * z * (1 + CA_Q + 0.1 + 0.6 + 0.6),    # 第 3 发：天赋 3 层，西风 2
        ]
        assert ours_chain == pytest.approx(hands, rel=REL_TOL), "我方三连 ramp vs 手算"
        for i, (enh, talent, west) in enumerate(((1, 1, 0), (2, 2, 1), (3, 3, 2))):
            theirs = run_optimizer(optimizer_driver, _opt_castorice(
                "memo_skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                                    "memoSkillEnhances": enh, "talentDmgStacks": talent,
                                    "memoDmgStacks": west}))
            assert theirs["hits"][0]["damage"] == pytest.approx(hands[i], rel=REL_TOL), (
                f"对方第 {i + 1} 发（enhances={enh}/talent={talent}/westwind={west}）vs 手算")
            assert ours_chain[i] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
                f"第 {i + 1} 发双方互对")
            assert theirs["hits"][0]["source_entity"] == "Netherwing"

    def test_wings_aggregate(self, optimizer_driver):
        """晦翼 6 段×0.40（lv6）：我方 before_actor_exit 六段逐段（死龙侧生前自爆——
        2026-09-17 时序扶正；E0 对称 buff 场与旧遐蝶侧逐位全等=不变性实证）vs
        对方聚合单发 2.40——总和比等，段数差在案（对方 memoTalentHits 聚合同 D6 族）."""
        eng, log = _make_logged(_solo_compiled("1407", enemies=_dummy("e1", "quantum")))
        self._ult(eng)
        log.clear()
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        ours = _hit_amounts(log, source="1407_netherwing")
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "memo_talent", cond={"memospriteActive": True, "teamDmgBoost": True}))

        z = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1) * 1.2
        hand_seg = 0.40 * CA_HP * z
        assert ours == pytest.approx([hand_seg] * 6, rel=REL_TOL), "我方六段逐段 vs 手算"
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(2.40, rel=REL_TOL), (
            "对方聚合 6×0.40（memoTalentHits=6）")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（段数差在案）")
        assert theirs["hits"][0]["damage"] == pytest.approx(6 * hand_seg, rel=REL_TOL), (
            "对方 vs 手算")


# ===========================================================================
# L2 长夜月 1413（对方 1400/Evernight.ts 全实现）——稳态链（战技×2 后）
# ===========================================================================

class TestEvernightDuipai:
    """长夜月 E0：普攻/忆灵技（忆质变档）/终结技/如露——双锚+dynamic 光环互对."""

    def _prep(self, eng):
        """战技×2 稳态：天黑黑 CD 0.15 + 天赋 CD 0.6 双方 + 光环快照全值
        （0.24×1.383+0.05=0.38192——第一次施放快照不含天黑黑 0.15，第二次重挂追平
        对方 dynamic 连续口径）；忆质 1+7+7=15."""
        _cast(eng, "1413", "141302")
        _cast(eng, "1413", "141302")
        assert math.isclose(eng.state.actors["1413"].resources["memoria"], 15.0)

    def test_basic(self, optimizer_driver):
        """普攻 0.5×HP（天黑黑 0.15+天赋 0.6 已由前一发施放喂出——天黑黑自耗 5%
        连锁天赋耗血半；对方 traceCritBuffs+talentMemoCdBuff pinned 口径同值 1.383）."""
        eng, log = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice")))
        _cast(eng, "1413", "141301")             # 天黑黑+天赋 CD 喂出（2 回合内全盖）
        log.clear()
        _cast(eng, "1413", "141301")
        ours = _hit_amounts(log, source="1413")
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "basic", cond={"talentMemoCdBuff": True}))

        hand = 0.5 * EV_HP * 0.5 * 0.9 * (1 + EV_CR * (EV_CD + 0.15 + 0.6)) * 1.5
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_panel_evey(self, optimizer_driver):
        """长夜面板归属：Evey HP=忆师×0.5（memoBaseHpScaling）+ CD 全链（继承 0.633
        +天黑黑 0.15+天赋 0.6+光环 0.38192=1.76492）——dynamic 镜像互对."""
        eng, _ = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice")))
        self._prep(eng)
        eff = eng.pipeline.effective_stats(eng.state.actors["1413_evey"])
        assert math.isclose(eff["hp"], EVEY_HP, rel_tol=1e-9)
        assert math.isclose(eff["crit_dmg"], EVEY_CD_FULL, rel_tol=1e-9), (
            "我方长夜 CD 全链（天黑黑/天赋/光环快照）")
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "basic", cond={"talentMemoCdBuff": True}))
        es = theirs["entity_stats"]
        assert es[1]["name"] == "Evey"
        assert es[1]["hp"] == pytest.approx(EVEY_HP, rel=REL_TOL), "对方长夜 HP（0.5×忆师）"
        assert es[1]["cd"] == pytest.approx(EVEY_CD_FULL, rel=REL_TOL), (
            "对方长夜 CD（dynamic 光环换算 0.24×1.383+天亮了 0.05）")
        assert theirs["stats"]["cd"] == pytest.approx(0.633 + 0.6 + 0.15, rel=REL_TOL), (
            "对方长夜月本人 CD（无光环——光环只落忆灵）")

    def test_memo_skill_memoria_scaling(self, optimizer_driver):
        """1141301：主段 0.5 + 追加 (15//4)×0.10（忆质钉 12 → 施放链 +3=15；对方
        <16 分支聚合 0.5+3×0.10=0.8 单发——总和比等，段数差在案）。注：对方
        MEMO_SKILL 在 ≥16 切如露模型（0.12×stacks），1141301 对拍须在 <16 窗口."""
        eng, log = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice")))
        self._prep(eng)
        eng.state.actors["1413"].resources["memoria"] = 12.0
        log.clear()
        _cast(eng, "1413_evey", "1141301")
        ours = _hit_amounts(log, source="1413_evey")
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "memo_skill", cond={"talentMemoCdBuff": True, "memoriaStacks": 15}))

        z = 0.5 * 0.9 * Z_EVEY_CRIT * 1.5
        hand_main, hand_add = 0.5 * EVEY_HP * z, 0.3 * EVEY_HP * z
        assert ours == pytest.approx([hand_main, hand_add], rel=REL_TOL), (
            "我方主段+忆质追加段（15//4=3）vs 手算")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(0.8, rel=REL_TOL), (
            "对方聚合 0.5+floor(15/4)×0.10（<16 分支）")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对")
        assert theirs["hits"][0]["source_entity"] == "Evey"

    def test_ult_aoe_then_darkest_riddle(self, optimizer_driver):
        """141303：AoE 2.0×长夜上限（官方序先 AoE 后入至暗——当发不吃增伤/易伤，
        对方 enhancedState=false 场比等）；至暗态忆灵技（enhancedState=true 场
        双方增伤 0.6+易伤 0.3 同挂）比等."""
        eng, log = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice")))
        self._prep(eng)
        log.clear()
        _fire_ult(eng, "1413", "141303", energy=240.0)
        ours_ult = _hit_amounts(log, source="1413_evey")
        theirs_ult = run_optimizer(optimizer_driver, _opt_evernight(
            "ult", cond={"talentMemoCdBuff": True}))

        z = 0.5 * 0.9 * Z_EVEY_CRIT * 1.5
        hand_ult = 2.0 * EVEY_HP * z
        assert ours_ult == pytest.approx([hand_ult], rel=REL_TOL), (
            "我方终结技 AoE（先结后入状态——不吃至暗件）vs 手算")
        assert theirs_ult["hits"][0]["damage"] == pytest.approx(hand_ult, rel=REL_TOL)
        assert ours_ult[0] == pytest.approx(theirs_ult["hits"][0]["damage"], rel=REL_TOL)
        assert "DARKEST_RIDDLE" in eng.state.actors["1413"].modifiers, "至暗之谜已入"

        # 至暗态忆灵技：双方增伤 0.6（DR 双件）+ 易伤 0.3（DR_VULN）——对方 enhancedState 场
        # （忆质钉 12 → 施放链 15：<16 窗口保 1141301 模型，≥16 对方切如露）
        eng.state.actors["1413"].resources["memoria"] = 12.0
        log.clear()
        _cast(eng, "1413_evey", "1141301")
        ours = _hit_amounts(log, source="1413_evey")
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "memo_skill", cond={"talentMemoCdBuff": True, "memoriaStacks": 15,
                                "enhancedState": True}))
        z_dr = 0.5 * 0.9 * Z_EVEY_CRIT * (1 + 0.5 + 0.6) * 1.3
        assert sum(ours) == pytest.approx(0.8 * EVEY_HP * z_dr, rel=REL_TOL), (
            "我方至暗态忆灵技（15//4=3 追加 → 0.5+0.3=0.8 总倍率）vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.3, rel=REL_TOL)

    def test_ult_cast_divergence(self, optimizer_driver):
        """R-EV1：对方 enhancedState=true 覆盖终结技当发（pinned 建模近似）→
        对方恰为我方 ×(2.1/1.5×1.3) = 1.82."""
        eng, log = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice")))
        self._prep(eng)
        log.clear()
        _fire_ult(eng, "1413", "141303", energy=240.0)
        ours = _hit_amounts(log, source="1413_evey")[0]
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "ult", cond={"talentMemoCdBuff": True, "enhancedState": True}))

        z = 0.5 * 0.9 * Z_EVEY_CRIT * 1.5
        assert ours == pytest.approx(2.0 * EVEY_HP * z, rel=REL_TOL), "我方无至暗基准链"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(R_EV1, rel=REL_TOL), (
            "R-EV1 结构差恰为 1.82（增伤 2.1/1.5 × 易伤 1.3）")

    def test_dream_dissolving(self, optimizer_driver):
        """1141307 如露（忆质≥16）：主目标每点 0.12/其余 0.06（我方 AoE+主补差两段化，
        对方主目标收敛单发）——主段总和比等；自耗消失+忆质清零行为锚."""
        eng, log = _make_logged(_solo_compiled("1413", enemies=_dummy("e1", "ice", n=3)))
        self._prep(eng)
        eng.state.actors["1413"].resources["memoria"] = 20.0
        log.clear()
        _cast(eng, "1413_evey", "1141307", target="e2")
        main = _hit_amounts(log, source="1413_evey", target="e2")
        adj1 = _hit_amounts(log, source="1413_evey", target="e1")
        theirs = run_optimizer(optimizer_driver, _opt_evernight(
            "memo_skill", cond={"talentMemoCdBuff": True, "memoriaStacks": 23}))

        z = 0.5 * 0.9 * Z_EVEY_CRIT * 1.5
        hand_pt = 0.06 * EVEY_HP * z      # 每点余段
        assert adj1 == pytest.approx([23 * hand_pt], rel=REL_TOL), "相邻 AoE 段 vs 手算"
        assert main == pytest.approx([23 * hand_pt, 23 * hand_pt], rel=REL_TOL), (
            "主目标 AoE+补差两段 vs 手算")
        assert sum(main) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "主目标总和（23×0.12）双方互对")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(0.12 * 23, rel=REL_TOL)
        assert not eng.state.actors["1413_evey"].alive, "如露自耗消失（官方全耗 HP）"
        assert math.isclose(eng.state.actors["1413"].resources["memoria"], 0.0), "忆质全耗"


# ===========================================================================
# L2 风堇 1409（对方 1400/Hyacine.ts 全实现）——治疗 tally→伤害 转换链（新大陆）
# ===========================================================================

class TestHyacineDuipai:
    """风堇 E0：普攻/双段治疗（阴云莞尔两态）/雨过天晴/tally 直写基数/速度档."""

    def _skill(self, eng, cid="1409"):
        _cast(eng, cid, "140902")
        assert "1409_ika" in eng.state.actors

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        _cast(eng, "1409", "140901")
        ours = _hit_amounts(log, source="1409")
        theirs = run_optimizer(optimizer_driver, _opt_hyacine("basic"))

        hand = 0.5 * HY_HP * 0.5 * 0.9 * 1.5    # CR 1.0 封顶（阴云莞尔烘焙/对方 trace 件）
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cr"] == pytest.approx(1.05, rel=REL_TOL), (
            "对方 trace CR+100%（min(1,·) 封顶两侧同）")

    def test_skill_heal_full_hp(self, optimizer_driver):
        """战技双段治疗（受疗者满血→阴云莞尔不触发，对方 healTargetHp50=false 场）：
        除小伊卡 0.08×HP+160 比等；小伊卡段 0.10+200 手算自证（对方只建单段，D6 同族）."""
        eng, _ = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        inc = _inc_log(eng)
        hya = eng.state.actors["1409"]
        hya.current_hp = eng.pipeline.effective_stats(hya)["hp"] - 300.0
        self._skill(eng)
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        theirs = run_optimizer(optimizer_driver, _opt_hyacine("skill_heal"))

        assert heals[("1409", "1409")] == pytest.approx(HY_SKILL_HEAL, rel=REL_TOL), (
            "我方除小伊卡段 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(HY_SKILL_HEAL, rel=REL_TOL), (
            "对方 SKILL_HEAL 段 vs 手算（OHB 0）")
        assert heals[("1409", "1409")] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["damage_function"] == "Heal"
        assert heals[("1409", "1409_ika")] == pytest.approx(0.0), "小伊卡满血实回 0"
        assert math.isclose(
            eng.state.actors["1409"].resources["hyacine_cumulative_heal"],
            HY_SKILL_HEAL, rel_tol=1e-9), "tally 逐实例记账（满血小伊卡记 0）"

    def test_skill_heal_target_hp50(self, optimizer_driver):
        """阴云莞尔：受疗者 HP≤50% → 治疗量 +25%（hit_condition 现场判定）——
        对方 healTargetHp50=true（OHB 0.25）场比等."""
        eng, _ = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        inc = _inc_log(eng)
        hya = eng.state.actors["1409"]
        hya.current_hp = 500.0                    # 41.8% ≤ 50% → 触发
        self._skill(eng)
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        theirs = run_optimizer(optimizer_driver, _opt_hyacine(
            "skill_heal", cond={"healTargetHp50": True}))

        hand = HY_SKILL_HEAL * 1.25
        assert heals[("1409", "1409")] == pytest.approx(hand, rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert heals[("1409", "1409")] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_ult_heal_and_clear_skies(self, optimizer_driver):
        """终结技双段治疗（0.10×HP+200）+ 雨过天晴（全队 HP+600+30%）——
        治疗段比等；生命光环面板回显互对（小伊卡段/小伊卡生命口径手算自证）."""
        eng, _ = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        inc = _inc_log(eng)
        hya = eng.state.actors["1409"]
        hya.current_hp = 500.0                    # 触发阴云莞尔——两态之一（对方同钉）
        _fire_ult(eng, "1409", "140903", energy=140.0)
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        theirs = run_optimizer(optimizer_driver, _opt_hyacine(
            "ult_heal", cond={"healTargetHp50": True, "clearSkies": True}))

        hand = (0.10 * (HY_HP + 600 + 0.3 * HY_HP_W) + 200) * 1.25   # 雨过天晴先挂=生命随档
        assert heals[("1409", "1409")] == pytest.approx(hand, rel=REL_TOL), (
            "我方终结技治疗（阴云莞尔触发；雨过天晴生命 2121.27 基数）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 ULT_HEAL 段 vs 手算")
        assert heals[("1409", "1409")] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        hy_full = HY_HP + 600 + 0.3 * HY_HP_W
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"], hy_full,
                            rel_tol=1e-9), "我方雨过天晴后生命（600+30%白值）"
        assert theirs["stats"]["hp"] == pytest.approx(hy_full, rel=REL_TOL), (
            "对方雨过天晴后生命回显（HP 600 + HP_P 0.3 白值换算）")
        assert "AFTER_RAIN" in hya.modifiers

    def test_tally_damage(self, optimizer_driver):
        """1140901 tally→伤害：tally 钉 4000（=战技+终结技治疗实账口径）×20%（lv6）
        直写基数区 × 3 层晨曦增伤 2.4 × CR 1.0；对方 HealTallyDamageFunction
        （引用治疗寄存器×healTallyScaling=0.2×(4000/引用值)）——等价锚定比等."""
        eng, _ = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        inc = _inc_log(eng)
        hya = eng.state.actors["1409"]
        hya.current_hp = 100.0
        self._skill(eng)                          # 治疗实例 → 晨曦 2 层
        _fire_ult(eng, "1409", "140903", energy=140.0)   # 再 2 实例 → 封顶 3 层
        hya.resources["hyacine_cumulative_heal"] = 4000.0
        ika = eng.state.actors["1409_ika"]
        assert math.isclose(
            ika.modifiers["IKA_DMG_BOOST"].stat_effects["all_dmg"], 0.8 * 3,
            rel_tol=1e-9), "晨曦 3 层（治疗实例叠层）"
        tally_dmg = [e for e in eng.bus and []]   # 占位防误用（下行才是真记录仪）
        dmg_log = []
        eng.bus.subscribe("on_hp_decrease", lambda et, p, ctx: dmg_log.append(dict(p)))
        _cast(eng, "1409_ika", "1140901")
        ours = [e["amount"] for e in dmg_log
                if e.get("reason") == "hit" and e.get("source") == "1409_ika"]
        h_ref = HY_SKILL_HEAL                     # 对方引用治疗（fake heal 段）= 255.622912
        theirs = run_optimizer(optimizer_driver, _opt_hyacine(
            "memo_skill", cond={"healingDmgStacks": 3,
                                "healTallyMultiplier": 4000.0 / h_ref}))

        hand = 4000.0 * 0.2 * 0.5 * 0.9 * 1.5 * (1 + 0.8 * 3)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 tally 直写基数 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(h_ref, rel=REL_TOL), (
            "对方引用治疗段（fake heal——recorded=false 但仍求值）vs 手算")
        assert theirs["hits"][1]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 HealTally 段 vs 手算（引用值×0.2×(4000/引用值)≡4000×0.2）")
        assert ours[0] == pytest.approx(theirs["hits"][1]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][1]["damage_function"] == "HealTally"
        assert theirs["hits"][1]["source_entity"] == "Ica"
        assert math.isclose(hya.resources["hyacine_cumulative_heal"], 2000.0,
                            rel_tol=1e-9), "施放后清 50%（lv6 #2）"

    def test_spd200_storm_calm(self, optimizer_driver):
        """暴风停歇（spd>200 门控——对方 dynamic 两件 driver 镜像）：双方 HP+20% 白值
        + 超 1 点治疗量+1%——spd 201 场治疗/生命回显三锚互对；低速场两侧同灭."""
        eng, _ = _make_logged(_solo_compiled("1409", enemies=_dummy("e1", "wind")))
        inc = _inc_log(eng)
        hya = eng.state.actors["1409"]
        _inject(eng, "1409", "XC_SPD", {"spd": 77.0})   # 124+77=201
        assert math.isclose(eng.pipeline.effective_stats(hya)["spd"], 201.0, rel_tol=1e-9)
        hy_boosted = HY_HP + 0.2 * HY_HP_W              # 暴风停歇 +20% 白值 = 1412.6112
        assert math.isclose(eng.pipeline.effective_stats(hya)["hp"], hy_boosted,
                            rel_tol=1e-9), "我方暴风停歇生命档"
        hya.current_hp = eng.pipeline.effective_stats(hya)["hp"] - 300.0  # 满血档（阴云莞尔灭）
        self._skill(eng)
        heals = {(e["source"], e["target"]): e["amount"] for e in inc
                 if e.get("reason") == "heal"}
        theirs = run_optimizer(optimizer_driver, _opt_hyacine("skill_heal", spd=201.0))

        hand = (0.08 * hy_boosted + 160) * 1.01         # 超 1 点 → 治疗量 +1%
        assert heals[("1409", "1409")] == pytest.approx(hand, rel=REL_TOL), (
            "我方暴风停歇治疗档 vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方 dynamic 两件（HyacineSpdActivation/Conversion）vs 手算")
        assert heals[("1409", "1409")] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["hp"] == pytest.approx(hy_boosted, rel=REL_TOL), (
            "对方 dynamic 生命档回显")


# ===========================================================================
# L2 昔涟 1415（对方 1400/Cyrene.ts 全实现）——涟漪链 + 德谬歌
# ===========================================================================

class TestCyreneDuipai:
    """昔涟 E0：普攻/涟漪强化普攻/Minuet（德谬歌基数 R-CY1 已收口三方相等）/三相速度档."""

    def _ripples(self, eng):
        """追忆钉 24 实打首开 → 涟漪态（德谬歌+双方 CR+50%+双方 HP+24%+结界永续）."""
        cyr = eng.state.actors["1415"]
        eng._gain_resource(cyr, "recollection", 23.0, source_id="ally")
        _cast(eng, "1415", "141501")             # +1 = 24（provenance：ally+1415 两源）
        _fire_ult(eng, "1415", "141503")
        assert "1415_dem" in eng.state.actors
        assert eng.state.actors["1415"].state_config is not None

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_solo_compiled("1415", enemies=_dummy("e1", "ice")))
        _cast(eng, "1415", "141501")
        ours = _hit_amounts(log, source="1415")
        theirs = run_optimizer(optimizer_driver, _opt_cyrene("basic"))

        hand = 0.5 * CY_HP * 0.5 * 0.9 * Z_CY_CRIT * 1.2   # 天赋全队增伤 0.2
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_enhanced_basic_ripples(self, optimizer_driver):
        """涟漪态 141508：单体 0.3+全体 0.3（对方聚合 0.6 单发，段数差在案）+ 双方
        CR+50% + 双方 HP+24% + 结界真伤 24%（对方 TRUE_DMG 乘区 vs 我方追加段——
        Σ(段×1.24) 总和比等）."""
        eng, log = _make_logged(_solo_compiled("1415", enemies=_dummy("e1", "ice")))
        self._ripples(eng)
        log.clear()
        _cast(eng, "1415", "141508")
        ice = [e["amount"] for e in log
               if e.get("reason") == "hit" and e.get("damage_type") == "ice"]
        true = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("damage_type") == "true"]
        theirs = run_optimizer(optimizer_driver, _opt_cyrene(
            "basic", cond={"memospriteActive": True, "zoneActive": True}))

        z = 0.5 * 0.9 * Z_CY_RIP * 1.2
        hand_seg = 0.3 * CY_HP_FULL * z
        assert ice == pytest.approx([hand_seg, hand_seg], rel=REL_TOL), (
            "我方单体+全体两段（昔涟生命=1536.7968+335.30=1872.098 双方同）vs 手算")
        assert true == pytest.approx([0.24 * hand_seg, 0.24 * hand_seg], rel=REL_TOL), (
            "结界真伤追加段 ×0.24")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(0.6, rel=REL_TOL), (
            "对方强化普攻聚合 0.3×2")
        assert sum(ice) + sum(true) == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "总和双方互对（段数差在案）"
        assert theirs["stats"]["hp"] == pytest.approx(CY_HP_FULL, rel=REL_TOL), (
            "对方双方 HP+24%（memoTalent HP_P——忆师白值加算口径）")
        assert theirs["stats"]["cr"] == pytest.approx(0.55, rel=REL_TOL), "对方涟漪 CR+50%"

    def test_minuet_demiurge_scaling(self, optimizer_driver):
        """1141501 Minuet（德谬歌基数）：主段 AoE 0.6 + 追加段（unique_sources−1=1）
        ×0.6——R-CY1 **已收口（2026-09-23）**：德谬歌生命口径改白值×(1+HP_P%) 活同步
        （昔涟白值 1397.088×1.34=1872.098，与对方忆师白值加算逐位一致）→ 三方相等."""
        eng, log = _make_logged(_solo_compiled("1415", enemies=_dummy("e1", "ice")))
        self._ripples(eng)
        dem = eng.state.actors["1415_dem"]
        assert math.isclose(eng.pipeline.effective_stats(dem)["hp"], DEM_HP_OURS,
                            rel_tol=1e-9), (
            "我方德谬歌生命（白值 1397.088×1.34——R-CY1 收口，非定格×1.24）")
        log.clear()
        _cast(eng, "1415_dem", "1141501")
        ice = [e["amount"] for e in log if e.get("reason") == "hit"
               and e.get("damage_type") == "ice"]
        theirs = run_optimizer(optimizer_driver, _opt_cyrene(
            "memo_skill", cond={"memospriteActive": True, "zoneActive": True,
                                "odeToEgoExtraBounces": 1}))

        z = 0.5 * 0.9 * Z_CY_RIP * 1.2                       # 冰段乘区（真伤另段）
        hand_seg = 0.6 * DEM_HP_OURS * z
        assert ice == pytest.approx([hand_seg, hand_seg], rel=REL_TOL), (
            "我方主段+1 追加段（unique_sources 2−1）vs 手算")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(1.2, rel=REL_TOL), (
            "对方聚合 0.6×(1+1)（odeToEgoExtraBounces=1）")
        theirs_total = 2 * 0.6 * DEM_HP_THEIRS * z * 1.24    # 对方结界 TRUE_DMG 乘区
        assert theirs["hits"][0]["damage"] == pytest.approx(theirs_total, rel=REL_TOL), (
            "对方 vs 手算（德谬歌=1872.098 口径）")
        ours_total = sum(e["amount"] for e in log if e.get("reason") == "hit")
        assert ours_total == pytest.approx(sum(ice) * 1.24, rel=REL_TOL), (
            "我方真伤追加段 ×0.24 与冰段同比例")
        assert ours_total == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "R-CY1 收口：三方相等（我方=对方=手算——旧结构差 1.0179104 核销）")
        assert theirs["hits"][0]["source_entity"] == "Demiurge"

    def test_trace_spd180(self, optimizer_driver):
        """1415103 三相：spd≥180 全队增伤 20% + 冰抗穿 min(超出,60)×2%——spd 190 场
        （我方 _inject 提速 / 对方钉 spd=190，finalize 档）比等；110 场两侧同灭."""
        eng, log = _make_logged(_solo_compiled("1415", enemies=_dummy("e1", "ice")))
        _inject(eng, "1415", "XC_SPD", {"spd": 80.0})   # 110+80=190
        _cast(eng, "1415", "141501")
        ours = _hit_amounts(log, source="1415")
        theirs = run_optimizer(optimizer_driver, _opt_cyrene("basic", spd=190))

        z = 0.5 * 0.9 * Z_CY_CRIT * (1 + 0.2 + 0.2) * 1.2    # 天赋 0.2+三相 0.2，冰抗穿 0.2
        hand = 0.5 * CY_HP * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方三相档 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.2, rel=REL_TOL), (
            "对方 finalize 冰抗穿 (190-180)×2%")
        # 低速场两侧同灭（既有 test_basic 即 110 场——此处单钉门控负例回显）
        theirs110 = run_optimizer(optimizer_driver, _opt_cyrene("basic"))
        assert theirs110["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.2, rel=REL_TOL), "110 场：三相灭（只剩天赋 0.2）"


# ===========================================================================
# 组队矩阵① 昔涟 → 遐蝶（结界真伤/天赋增伤/献予「生死」晦翼烘焙）
# ===========================================================================

class TestCyreneToCastorice:
    """1415→1407：zone 真伤 + talent 0.2（单开）/ 献予诗晦翼烘焙（组合）——
    三相 teammate 链常开件钉 R-CY2."""

    def _team_build(self):
        return {"build": {"team": [
            {"character_template": "1407", "level": 80},
            {"character_template": "1415", "level": 80},
        ], "policy": _POLICY}}

    def _team_compiled(self):
        return compile_encounter(self._team_build(), _stage(_dummy("e1", "quantum")),
                                 template_roots=TEST_TEMPLATE_ROOTS)

    def test_zone_and_talent(self, optimizer_driver):
        """141502 结界 + 天赋 0.2：遐蝶普攻 → 主段×1.24 真伤回响——对方 zoneActive+
        talentDmgBuff 场比等（cyreneSpdDmg 钉 false 隔离常开件）."""
        eng, log = _make_logged(self._team_compiled())
        _cast(eng, "1415", "141502")
        log.clear()
        _cast(eng, "1407", "140701")
        q = [e["amount"] for e in log if e.get("reason") == "hit"
             and e.get("source") == "1407" and e.get("damage_type") == "quantum"]
        true = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("damage_type") == "true"]
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "basic", teammates=[_tm_cyrene()]))

        hand = 0.5 * CA_HP * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.2)
        assert q == pytest.approx([hand], rel=REL_TOL), "我方主段（天赋 0.2）vs 手算"
        assert true == pytest.approx([0.24 * hand], rel=REL_TOL), "结界真伤回响"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand * 1.24, rel=REL_TOL), (
            "对方 TRUE_DMG 乘区场 vs 手算")
        assert q[0] + true[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（乘区 vs 追加段——数值等价）")

    def test_cyrene_spd_dmg_divergence(self, optimizer_driver):
        """R-CY2：对方 teammate 链 cyreneSpdDmg 无速度门控常开 0.2（我方 1415103
        enable_if 与对方主角色链一致——昔涟 spd 110 不触发）→ 对方恰为我方
        ×(1.544/1.344)."""
        eng, log = _make_logged(self._team_compiled())
        _cast(eng, "1415", "141502")
        log.clear()
        _cast(eng, "1407", "140701")
        ours = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("source") == "1407" and e.get("damage_type") == "quantum"][0]
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "basic", teammates=[_tm_cyrene(cyreneSpdDmg=True)]))

        hand = 0.5 * CA_HP * 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.2)
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方无三相基准链（spd 110）"
        assert theirs["hits"][0]["damage"] / (ours * 1.24) == pytest.approx(
            R_CY2, rel=REL_TOL), "R-CY2 结构差恰为 1.544/1.344（对方常开件，结界 1.24 已约）"

    def test_ode_wings_bonus(self, optimizer_driver):
        """献予「生死」：新蕊上限 200% 覆写 + 溢出 30% 烘焙晦翼 +0.216/段（敌方 1 名
        ≤2 档）——对方 cyreneSpecialEffect 场（0.0024×30×3=0.216 同值）比等."""
        eng, log = _make_logged(self._team_compiled())
        cyr = eng.state.actors["1415"]
        cas = eng.state.actors["1407"]
        eng._gain_resource(cyr, "recollection", 24.0, source_id="ally")
        _fire_ult(eng, "1415", "141503")          # 德谬歌入场（激活免费大——无标记不烘焙）
        eng.dismiss_summon_actor("1407_netherwing")   # 送走到免大死龙（无烘焙基线）
        _cast(eng, "1415_dem", "1141502", target="1407")   # 献予「生死」：标记+上限覆写
        assert cas.modifiers["CYRENE_ODE_LIFE_DEATH"].max_override == 68000.0
        cas.resources["newbud"] = 44200.0          # 溢出 10200=30%
        _fire_ult(eng, "1407", "140703")
        assert math.isclose(cas.resources["_ode_wing_bonus"], 0.216, rel_tol=1e-9), (
            "烘焙 30×(0.0024+0.0048)=0.216（lv6 #2/#5）")
        log.clear()
        eng.dismiss_summon_actor("1407_netherwing")
        ours = _hit_amounts(log, source="1407_netherwing")   # 时序扶正后晦翼源=死龙
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "memo_talent", cond={"memospriteActive": True, "teamDmgBoost": True,
                                 "cyreneSpecialEffect": True},
            teammates=[_tm_cyrene()]))

        z = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1 + 0.2) * 1.2   # 量子段乘区（真伤另段）
        hand_seg = (0.40 + 0.216) * CA_HP * z
        assert ours == pytest.approx([hand_seg] * 6, rel=REL_TOL), (
            "我方晦翼含烘焙（0.40+0.216）×6 段（怒啸/天赋/境界同挂）vs 手算")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(
            6 * (0.40 + 0.216), rel=REL_TOL), (
            "对方聚合：6×(0.40+0.0024×30×3)——敌方 1 名 <3 档 ×3")
        true = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("damage_type") == "true"]
        assert sum(ours) + sum(true) == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对（对方 TRUE_DMG 乘区 vs 我方真伤追加段）")


# ===========================================================================
# 组队矩阵② 长夜月 → 遐蝶（易伤/忆灵暴伤光环跨 actor 传导）
# ===========================================================================

class TestEvernightToCastorice:
    """1413→1407（双人记忆子队——天亮了 2 记忆档 0.15）：DR 易伤 0.3 + 光环
    0.24×1.383+0.15 落死龙——对方 teammate 链（evernightCombatCD 钉 1.383 同源）比等."""

    def _team_compiled(self):
        return compile_encounter(
            {"build": {"team": [
                {"character_template": "1407", "level": 80},
                {"character_template": "1413", "level": 80},
            ], "policy": _POLICY}},
            _stage(_dummy("e1", "quantum")), template_roots=TEST_TEMPLATE_ROOTS)

    def test_dr_vuln_and_halo_on_netherwing(self, optimizer_driver):
        """1413 战技×2 稳态 + 终结技入至暗 → 死龙焰息：光环 CD 0.48192 + 孤独/天赋
        （死龙不吃——挂长夜双方）+ 易伤 0.3（DR_VULN 全场）——传导链全等."""
        eng, log = _make_logged(self._team_compiled())
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 先召死龙
        _cast(eng, "1413", "141302")     # 光环落在场忆灵（死龙+长夜）——官方"我方全体
        _cast(eng, "1413", "141302")     #   忆灵"为施放时点存续件，后召不补（在案）
        _fire_ult(eng, "1413", "141303", energy=240.0)
        nw = eng.state.actors["1407_netherwing"]
        halo_cd = 0.633 + 0.24 * (0.633 + 0.6 + 0.15) + 0.15   # 继承+光环+天亮了 2 记忆
        assert math.isclose(eng.pipeline.effective_stats(nw)["crit_dmg"], halo_cd,
                            rel_tol=1e-9), "我方光环 CD 落死龙（snapshot 全值口径）"
        log.clear()
        _cast(eng, "1407_netherwing", "1140702")
        ours = _hit_amounts(log, source="1407_netherwing")
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "memo_skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                                "talentDmgStacks": 3, "memoSkillEnhances": 1,
                                "memoDmgStacks": 0},
            teammates=[_tm_evernight()]))

        # 天赋 3 层（长夜月战技 4 次耗血+终结技 1 次预先叠满——140704 计数全队失 HP）
        z = 0.5 * 0.9 * (1 + CA_CR * halo_cd) * (1 + CA_Q + 0.1 + 0.6) * 1.2 * 1.3
        hand = 0.24 * CA_HP * z
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方焰息（天赋 3 层/西风 0/境界 1.2/易伤 1.3）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), (
            "对方（evernightCombatCD 钉 1.383 → 光环 0.33192+天亮了 0.15 同源）vs 手算")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["entity_stats"][1]["cd"] == pytest.approx(halo_cd, rel=REL_TOL), (
            "对方死龙 CD 回显（teammate 链忆灵暴伤落点）")
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.3, rel=REL_TOL)

    def _team_compiled_e1(self, n):
        return compile_encounter(
            {"build": {"team": [
                {"character_template": "1407", "level": 80},
                {"character_template": "1413", "level": 80, "eidolon": 1},
            ], "policy": _POLICY}},
            _stage(_dummy("e1", "quantum", n=n)), template_roots=TEST_TEMPLATE_ROOTS)

    def test_e1_final_dmg_on_netherwing_half(self, optimizer_driver):
        """长夜月 E1（teammates 块 eidolon 钉 1）：忆灵 final 独立乘区按敌数变档
        （4+/3/2/1 → ×1.2/1.25/1.3/1.5——e1FinalDmgMap/E1_MEMO_FINAL_DMG 同表）——
        R-CY3 收口验收件：死龙半挪死龙侧后忆灵限定 final 区全吃，四档三方比对；
        遐蝶半非忆灵 = final 区恒 1 对照（E1 忆灵限定命中域闸）."""
        nw_cd = 0.633 + 0.24 * (0.633 + 0.6 + 0.15) + 0.15   # 光环 0.33192+天亮了 2 记忆 0.15
        for n, gear in ((4, 0.2), (3, 0.25), (2, 0.3), (1, 0.5)):
            eng, log = _make_logged(self._team_compiled_e1(n))
            _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 先召死龙
            _cast(eng, "1413", "141302")
            _cast(eng, "1413", "141302")     # 光环+天亮了落在场忆灵（存续件口径同上传导链）
            nw = eng.state.actors["1407_netherwing"]
            assert "E1_MEMO_FINAL_DMG" in nw.modifiers, "E1 忆灵件落死龙（actor_enter 挂）"
            fdb = eng.pipeline.effective_stats(nw)["dmg_bonus"].get("final_dmg_boost", 0.0)
            assert fdb == pytest.approx(gear, rel=REL_TOL), (
                f"我方 final 区现场变档（敌数 {n} → +{gear}）")
            log.clear()
            _cast(eng, "1407", "140709")
            ours_cas = _hit_amounts(log, source="1407", target="e1")
            ours_nw_all = [e["amount"] for e in log
                           if e.get("reason") == "hit"
                           and e.get("source") == "1407_netherwing"
                           and e.get("damage_type") == "quantum"]
            theirs = run_optimizer(optimizer_driver, _opt_castorice(
                "skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                               "talentDmgStacks": 3},
                teammates=[_tm_evernight(eidolon=1, enhancedState=False)],
                enemy_count=n))

            # 天赋 3 层（长夜月战技 2×2 次耗血预叠满——140704 计数全队失 HP）
            z_cas = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1 + 0.6) * 1.2
            hand_cas = 0.3 * CA_HP * z_cas
            z_nw = 0.5 * 0.9 * (1 + CA_CR * nw_cd) * (1 + CA_Q + 0.1 + 0.6) * 1.2 * (1 + gear)
            hand_nw = 0.5 * CA_HP * z_nw
            assert ours_cas == pytest.approx([hand_cas], rel=REL_TOL), (
                f"遐蝶半（天赋 3 层；无 final 区对照）敌数 {n} vs 手算")
            assert ours_nw_all == pytest.approx([hand_nw] * n, rel=REL_TOL), (
                f"死龙半（死龙 CD 1.11492 全链 × final 区 {1 + gear}）敌数 {n} 逐目标 vs 手算")
            assert theirs["hits"][1]["damage"] == pytest.approx(hand_nw, rel=REL_TOL), (
                f"对方死龙半（e1FinalDmgMap[{n}]={gear}）vs 手算")
            assert ours_nw_all[0] == pytest.approx(
                theirs["hits"][1]["damage"], rel=REL_TOL), f"死龙半三方互对（敌数 {n}）"
            assert theirs["hits"][1]["breakdown"]["finalDmgMulti"] == pytest.approx(
                1 + gear, rel=REL_TOL), f"对方 final 区回显 ×{1 + gear}（敌数 {n}）"
            assert theirs["hits"][1]["breakdown"]["critMulti"] == pytest.approx(
                1 + CA_CR * nw_cd, rel=REL_TOL), "对方死龙半暴击区=死龙 CD 1.11492 全链"
            assert theirs["hits"][0]["breakdown"]["finalDmgMulti"] == pytest.approx(
                1.0, rel=REL_TOL), "遐蝶半非忆灵——final 区恒 1（E1 命中域对照）"
            assert ours_cas[0] == pytest.approx(
                theirs["hits"][0]["damage"], rel=REL_TOL), f"遐蝶半双方互对（敌数 {n}）"

    def test_wings_under_halo_and_dawn(self, optimizer_driver):
        """时序扶正验收件①（忆灵限定 buff 场：光环 CD+天亮了，无 E1）——晦翼 6 段
        从「残留漏算」转三方相等：死龙在世结算（before_actor_exit 生前自爆）⇒
        光环/天亮了落死龙面板全吃；对方聚合单发 sourceEntity=Netherwing 同口径."""
        eng, log = _make_logged(self._team_compiled())
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 先召死龙
        _cast(eng, "1413", "141302")
        _cast(eng, "1413", "141302")     # 光环+天亮了落在场忆灵（存续件口径同传导链）
        nw = eng.state.actors["1407_netherwing"]
        nw_cd = 0.633 + 0.24 * (0.633 + 0.6 + 0.15) + 0.15   # 1.11492（光环+天亮了 2 记忆）
        assert math.isclose(eng.pipeline.effective_stats(nw)["crit_dmg"], nw_cd,
                            rel_tol=1e-9), "我方光环 CD 落死龙（晦翼结算面板=本件）"
        log.clear()
        assert eng.dismiss_summon_actor("1407_netherwing") is True
        ours = _hit_amounts(log, source="1407_netherwing")
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "memo_talent", cond={"memospriteActive": True, "teamDmgBoost": True,
                                 "talentDmgStacks": 3},
            teammates=[_tm_evernight(enhancedState=False)]))

        # 天赋 3 层（长夜月战技 2×2 次耗血预叠满——140704 计数全队失 HP）；
        # 境界在场（生前自爆——摘除在死后清理钩）
        z = 0.5 * 0.9 * (1 + CA_CR * nw_cd) * (1 + CA_Q + 0.1 + 0.6) * 1.2
        hand_seg = 0.40 * CA_HP * z
        assert ours == pytest.approx([hand_seg] * 6, rel=REL_TOL), (
            "我方晦翼 6 段（死龙 CD 1.11492 全链——光环 0.33192+天亮了 0.15+继承 0.633）vs 手算")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(2.40, rel=REL_TOL), (
            "对方聚合 6×0.40（memoTalentHits=6）")
        assert theirs["hits"][0]["damage"] == pytest.approx(6 * hand_seg, rel=REL_TOL), (
            "对方聚合单发（Netherwing 容器——evernightCombatCD 钉 1.383 同源 CD 链）vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "晦翼三方互对（段数差在案——忆灵限定 buff 漏算正式收口）")
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(
            1 + CA_CR * nw_cd, rel=REL_TOL), "对方晦翼暴击区=死龙 CD 1.11492 全链回显"

    def test_e1_final_dmg_on_wings(self, optimizer_driver):
        """时序扶正验收件②（owner 硬指标——E1 final 档对晦翼）：长夜月 E1 忆灵 final
        独立乘区按敌数变档（4+/3/2/1 → ×1.2/1.25/1.3/1.5——e1FinalDmgMap 同表）对
        晦翼 6 段三方全等——旧「E1 场实证漏 final 区」（B27 候选）正式收口."""
        nw_cd = 0.633 + 0.24 * (0.633 + 0.6 + 0.15) + 0.15   # 光环 0.33192+天亮了 2 记忆 0.15
        for n, gear in ((4, 0.2), (3, 0.25), (2, 0.3), (1, 0.5)):
            eng, log = _make_logged(self._team_compiled_e1(n))
            _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 先召死龙
            _cast(eng, "1413", "141302")
            _cast(eng, "1413", "141302")     # 光环+天亮了落在场忆灵（存续件口径同上）
            nw = eng.state.actors["1407_netherwing"]
            assert "E1_MEMO_FINAL_DMG" in nw.modifiers, "E1 忆灵件落死龙（actor_enter 挂）"
            fdb = eng.pipeline.effective_stats(nw)["dmg_bonus"].get("final_dmg_boost", 0.0)
            assert fdb == pytest.approx(gear, rel=REL_TOL), (
                f"我方 final 区现场变档（敌数 {n} → +{gear}）——晦翼结算面板=本件")
            log.clear()
            assert eng.dismiss_summon_actor("1407_netherwing") is True
            ours = [e["amount"] for e in log
                    if e.get("reason") == "hit"
                    and e.get("source") == "1407_netherwing"
                    and e.get("damage_type") == "quantum"]
            theirs = run_optimizer(optimizer_driver, _opt_castorice(
                "memo_talent", cond={"memospriteActive": True, "teamDmgBoost": True,
                                     "talentDmgStacks": 3},
                teammates=[_tm_evernight(eidolon=1, enhancedState=False)],
                enemy_count=n))

            # 天赋 3 层（长夜月战技 2×2 次耗血预叠满）；境界在场（生前自爆）
            z = 0.5 * 0.9 * (1 + CA_CR * nw_cd) * (1 + CA_Q + 0.1 + 0.6) * 1.2 * (1 + gear)
            hand_seg = 0.40 * CA_HP * z
            assert ours == pytest.approx([hand_seg] * 6, rel=REL_TOL), (
                f"我方晦翼 6 段（死龙 CD 1.11492 全链 × final 区 {1 + gear}）敌数 {n} vs 手算")
            assert theirs["hits"][0]["damage"] == pytest.approx(6 * hand_seg, rel=REL_TOL), (
                f"对方聚合（e1FinalDmgMap[{n}]={gear}）vs 手算")
            assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
                f"晦翼三方互对（敌数 {n}——我方=对方=手算）")
            assert theirs["hits"][0]["breakdown"]["finalDmgMulti"] == pytest.approx(
                1 + gear, rel=REL_TOL), f"对方晦翼 final 区回显 ×{1 + gear}（敌数 {n}）"
            assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(
                1 + CA_CR * nw_cd, rel=REL_TOL), "对方晦翼暴击区=死龙 CD 1.11492 全链"


# ===========================================================================
# 组队矩阵③ 组合场（记忆战舰全家：昔涟+长夜月+风堇 → 遐蝶）
# ===========================================================================

class TestCombinedRemembranceTeam:
    """4 人编成（天亮了 3 记忆档 0.5）：雨过天晴生命 + 至暗易伤 + 结界真伤 +
    双光环落死龙——组合两态（全开/隔离 1141524 待收件）."""

    def _team_compiled(self):
        return compile_encounter(
            {"build": {"team": [
                {"character_template": "1407", "level": 80},
                {"character_template": "1409", "level": 80},
                {"character_template": "1413", "level": 80},
                {"character_template": "1415", "level": 80},
            ], "policy": _POLICY}},
            _stage(_dummy("e1", "quantum")), template_roots=TEST_TEMPLATE_ROOTS)

    def test_full_combo_enhanced_skill(self, optimizer_driver):
        """全开：风堇终结技（雨过天晴）→ 遐蝶终结技（先召死龙吃光环）→ 长夜月
        战技×2+终结技（至暗）→ 昔涟战技（结界）→ 遐蝶 140709 两段——生命/暴伤
        （天亮了 4 记忆档 0.65）/易伤/真伤全链互对；天赋 3 层（长夜月耗血预叠）."""
        eng, log = _make_logged(self._team_compiled())
        _fire_ult(eng, "1409", "140903", energy=140.0)        # 雨过天晴（含小伊卡召唤）
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))   # 先召死龙
        _cast(eng, "1413", "141302")     # 光环落在场忆灵（施放时点存续件——后召不补）
        _cast(eng, "1413", "141302")
        _fire_ult(eng, "1413", "141303", energy=240.0)        # 至暗之谜
        _cast(eng, "1415", "141502")                          # 结界
        cas_hp = CA_HP + 600 + 0.3 * CA_HP                    # 雨过天晴后遐蝶生命 2718.9168
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1407"])["hp"], cas_hp,
            rel_tol=1e-9)
        log.clear()
        _cast(eng, "1407", "140709")
        q_cas = [e["amount"] for e in log if e.get("reason") == "hit"
                 and e.get("source") == "1407" and e.get("damage_type") == "quantum"]
        q_nw = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("source") == "1407_netherwing" and e.get("damage_type") == "quantum"]
        true = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("damage_type") == "true"]
        theirs = run_optimizer(optimizer_driver, _opt_castorice(
            "skill", cond={"memospriteActive": True, "teamDmgBoost": True,
                           "talentDmgStacks": 3},
            teammates=[_tm_hyacine(), _tm_evernight(), _tm_cyrene()]))

        halo_cd = 0.633 + 0.24 * (0.633 + 0.6 + 0.15) + 0.65   # 天亮了 4 记忆档 0.65
        nw_cd = halo_cd
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1407_netherwing"])["crit_dmg"],
            nw_cd, rel_tol=1e-9), "我方光环 CD 落死龙（先召后挂——存续件口径）"
        z_cas = 0.5 * 0.9 * Z_CA_CRIT * (1 + CA_Q + 0.1 + 0.2 + 0.6) * 1.2 * 1.3
        hand_cas = 0.3 * cas_hp * z_cas
        assert q_cas == pytest.approx([hand_cas], rel=REL_TOL), (
            "遐蝶半（天赋 3 层预叠——长夜月 5 次耗血；雨过天晴生命随档）vs 手算")
        # R-CY3 已收口（2026-09-17）：死龙半挪死龙侧 hook（$self=死龙面板——忆灵限定
        # buff 全吃）+ 基数 max_hp_of('1407') 跨 actor 读忆师——与对方 hit 双引用
        #（sourceEntity=死龙/scalingEntity=遐蝶）同构；死龙 CD 1.61492 全链三方相等
        z_nw = 0.5 * 0.9 * (1 + CA_CR * nw_cd) * (1 + CA_Q + 0.1 + 0.2 + 0.6) * 1.2 * 1.3
        hand_nw = 0.5 * cas_hp * z_nw
        assert q_nw == pytest.approx([hand_nw], rel=REL_TOL), (
            "死龙半（我方=死龙面板——光环 CD 1.61492 全链；增伤同池 2.044；基数=遐蝶上限）vs 手算")
        assert true == pytest.approx([0.24 * hand_cas, 0.24 * hand_nw], rel=REL_TOL), (
            "结界真伤回响两段")
        assert q_cas[0] + true[0] == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "遐蝶半总和双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1 + CA_Q + 0.1 + 0.2 + 0.6, rel=REL_TOL)
        assert theirs["hits"][1]["damage"] == pytest.approx(hand_nw * 1.24, rel=REL_TOL), (
            "对方死龙半（死龙容器——光环全值 CD；结界 TRUE_DMG ×1.24）vs 手算")
        assert q_nw[0] + true[1] == pytest.approx(
            theirs["hits"][1]["damage"], rel=REL_TOL), (
            "死龙半三方互对（R-CY3 收口——我方=对方=手算）")
        assert theirs["hits"][1]["breakdown"]["critMulti"] == pytest.approx(
            1 + CA_CR * nw_cd, rel=REL_TOL), "对方死龙半暴击区=死龙 CD 1.61492 全链"
        assert theirs["entity_stats"][1]["cd"] == pytest.approx(nw_cd, rel=REL_TOL), (
            "对方死龙 CD（光环 0.33192+天亮了 0.65+继承）")
        assert theirs["stats"]["hp"] == pytest.approx(cas_hp, rel=REL_TOL), (
            "对方雨过天晴后遐蝶生命回显")
