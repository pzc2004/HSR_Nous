"""L2 角色级 + L4 组队级对拍（BACKLOG B22 名册扩拍第一波）：白厄队 4 角色——
白厄 1408（变身链全游最复杂机制）/ 刻律德菈 1412（军功指针=独特目标代数）/
星期日 1313 / 丹恒•腾荒 1414（护盾发射点）。逐段伤害 == hsr-optimizer 角色实现
整链伤害（rel_tol 1e-4；双锚=对方+手算，对不上的按惯例钉结构差数值自证）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（+teammates 块，
驱动头注有完整口径）。我方路径：真模板（tests/fixtures 人工根）→ 编译 →
CombatEngine 钉资源 → _cast/_fire_ultimate → bus on_hp_decrease 逐段记录仪
（setup 前订阅，L2 先例）。

统一口径（两侧一致，沿用 L2/装备级/黄泉队）：星魂钉死、行迹满级、无光锥无遗器、
假人 lvl80 def 1000（防御区 0.5）、匹配弱点（抗性区 1.0）、未击破（0.9）、期望暴击。
星魂覆盖：1408 fixture 有 eidolons 块（E2 场比等在案）；1412/1313/1414 fixture 无
eidolons 块 → E0 起步，星魂开关两侧门控同灭（e1DefPen/e2DmgBoost/e4/e6 族）。

===========================================================================
白厄 1408 buff 状态映射表（对方 content 开关 ↔ 我方模板触发）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
transformedState（true）       state_config khaslana（140803 变身）            非变身钉 false / 变身钉 true
                                                                            （变身经火种 12 实打进入）
enhancedSkillType（FOUNDATION）140811 死星天裁（弹射毁伤驱动）/140809 弑魂焚诏  FOUNDATION 对 140811 /
                               （CALAMITY=1）（无伤技）                        CALAMITY 对 140809（双无伤比零）
atkBuffStacks 1-2（2）         行迹 1408103 照见英雄本色 atk_pct 0.5×层        钉 1 = 开局至首变前口径
                               （进战 1 层 / 变身结束再 1 层）                （对方默认 2=首变退出后）
cdBuff（true）                 140804 队友技指白厄 → 暴伤 +30% 3 回合          单人钉 false；组队场实打喂出比等
sustainDmgBuff（true）         1408102 前半（受队友治疗/护盾增伤 45% 4 回合）   钉 false 比等；钉 true 钉 P5 结构差
                               ——**待收**（护盾获得无事件通道，fixture 头注在案）×1.45（空池）；注入 all_dmg 0.45 比等
spdBuff（false）               140805 变身结束全队 spd_pct +15%                对拍无伤害消费，两侧同钉
cyreneSpecialEffect（true）    昔涟联动（无昔涟场景恒 0）                      钉 false 明示
e1Buffs（true，E1）            E1 开大后暴伤 +50% 3 回合（on_ultimate 钩）      E2 场比等（对方常开 precompute
                                                                            件覆盖变身前=建模近似，E1 注在案）
e2ResPen（true，E2）           E2 变身期物理抗穿 +20%（EIDO stat_effects）     E2 变身场比等；变身前泄漏见 待查①
e6TrueDmg（true，E6）          E6 死星天裁后真伤 36%（fixture notes 待 v3）    E0 门控同灭
（无开关）Foundation 450% 额外  140811 消耗≥4 毁伤 → verdict_extra 均分 4.5     对方未建模——钉 P1 结构差 18/13
（无开关）弑魂反击叠层放大       每层 +20% 原始倍率（官方覆盖整个反击）          对方 1.60 平铺=0 层口径——
                                                                            钉 P2 结构差 ×(1+0.2n)
（无开关）境界植弱点/队友离场    ZONE_PHY_WEAK / banish_allies_on_enter        对方无此概念——行为锚单钉

===========================================================================
刻律德菈 1412 buff 状态映射表（teammate 链：对方 teammateContent ↔ 我方模板）
===========================================================================
对方 teammate content（默认）  我方模板对应                                   对拍处置
militaryMerit（true）          CYD_MERIT（141202 指目标挂，唯一通道）          施放 141202→1408 后比等
peerage（true）                爵位战技暴伤 +72% + 全属性抗穿 +10%——**待收**   钉 false 比等；钉 true + 注入
                               （爵位 buff/徽章待 B31 选择器，1412 hook 注在案）{crit_dmg .72, res_pen .1} 比等；
                                                                            不注入钉 P3 结构差 1.212255
teammateATKValue（4000）       天赋 141204 军功 ATK = 刻律 atk×24%——**待收**  钉 0 比等；钉 732.69504（我方刻律
                               （1412 fixture 未收，2026-09-17 对拍登记）      行迹后攻击）+ 注入 atk 175.8468 比等；
                                                                            不注入钉 P4 结构差（=攻击比 1.201387）
spdBuff（true）                1412103 征服者 spd+20（目标与刻律，3 回合）     实打喂出——面板/回显双闸比等
cyreneSpecialEffect（true）    昔涟联动（无昔涟恒 0）                          钉 true 无害
e1DefPen/e2DmgBoost/e6Buffs    星魂（1412 fixture 无 eidolons 块）             E0 门控同灭
（无开关）见者 CR +100%         CYD_VIDI_CRIT crit_rate 1.0                    已修真病 B-NEW⑥（0.01→1.0 笔误，
                                                                            官方 1412102 params [[1,1]]）
（无开关）天赋附伤 0.6×atk 风    after_being_hit 钩（军功持有者攻击 → 1 段）    对方未建模——单锚手算；
                                                                            多目标段数口径同 T2（攻击实例
                                                                            id 通道缺，1314/1403 在案）
（teammate 不建）奇袭           充能≥6 军功持有者放战技 → 复制再放一次          对方未建模——行为锚+手算（P6）

===========================================================================
星期日 1313 buff 状态映射表
===========================================================================
skillDmgBuff（true）           SUNDAY_SKILL_DMG all_dmg 0.3（目标有召唤物再    施放 131302→1408 比等（无召唤物
                               +0.5，施放时刻存在性烘焙）                     档）；召唤物档见 T-PH2
talentCrBuffStacks 0-1（1）    SUNDAY_TALENT_CR crit_rate +20% 3 回合         钉 1 实打比等
beatified（true）              BEATIFIED 暴伤 = 0.3×星期日暴伤 + 0.12（快照）  131303→1408 实打比等
teammateCDValue（2.50）        星期日自身 crit_dmg 0.873（快照源）             钉 0.873 = 快照同源
techniqueDmgBuff（false）      秘技荣光之秘 all_dmg 0.5                        钉 false（秘技族不进对拍）
e1DefPen/e2DmgBuff/e6 族       星魂（1313 fixture 无 eidolons 块）             E0 门控同灭
（无开关）终结技回能 → 火种      1408102 后半（队友回能效果 → 火种 +1）         火种计数锚（131303 指白厄
                                                                            =目标 1 + 回能 1 = +2）

===========================================================================
丹恒•腾荒 1414 buff 状态映射表
===========================================================================
bondmate（true）               TONGPAO（141402 指目标挂，唯一通道）           施放 141402→1408 比等
sourceAtk（3000）              神秀 1414101：同袍攻 = 腾荒 atk×15% 快照        钉 745.1136（我方行迹后攻击）
                                                                            → ATK +111.76704 比等
e1ResPen/e4DmgReduction/e6 族  星魂（1414 fixture 无 eidolons 块）             E0 门控同灭
cyreneSpecialEffect（true）    昔涟联动（无昔涟恒 0）                          钉 true 无害
（无开关）战技/终结技全队盾      TERRA_SHIELD 0.2×atk+400（PERMANSON_SHIELD 池）主 C 场盾段双锚比等（对方
                                                                            ShieldDamageFunction）；teammate
                                                                            链无盾件——组队场单锚手算
（无开关）龙灵强化追击附加两笔   同袍属性附加 0.8 + 峥嵘强化段 0.4（同袍 atk）  对方未建模——钉 T-TE1（段数+
                                                                            单段手算）；主段 0.8 物理比等
（无开关）bondmate→hasSummons  龙灵在队 → 星期日 +50% 召唤物档（对方全队级）  我方龙灵 summoner=丹恒 →
                                                                            has_summon(白厄)=0 不触发——
                                                                            钉 T-PH2 结构差 9/7（归属待实测）

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
P1 死星天裁 450% 额外段（对方未建模；对方固定 26 段×0.45=11.7 聚合）
   → 毁伤 7 场：我方 (26×0.45+4.5)/对方 11.7 = 16.2/11.7 = 18/13 ≈ 1.38462
P2 弑魂反击叠层放大（对方 1.60 平铺=0 层口径）→ 我方/对方 = 1+0.2n；2 层场 = 1.4
P3 爵位战技暴伤 72% + 抗穿 10%（我方待收）→ (1+0.17×1.893)/(1+0.17×1.173)×1.1
   = 1.32181/1.19941×1.1 ≈ 1.212255
P4 军功 ATK 24%×刻律攻击（我方待收）→ 比值 = 1049.0268/873.18 ≈ 1.201387
   （其余乘区全等，差值恰为攻击区比）
P5 1408102 前半 45% 增伤（我方待收，护盾获得事件通道缺）→ 空增伤池 ×1.45
P6 奇袭复制（对方未建模）→ 段数/充能行为锚+手算（对方无 oracle）
T-PH2 龙灵归属：对方全队级 hasSummons（Terra initialize 写共享 config → 星期日
   +50% 档触发）vs 我方龙灵 summoner=丹恒（has_summon(白厄)=0 不触发）
   → 组合场增伤池 2.25/1.75 = 9/7 ≈ 1.28571（归属官方"丹恒•腾荒召唤龙灵"主语
   =丹恒 vs "for them"——待实测 B19；对齐件注入 +0.5 后其余全链全等）
T-TE1 龙灵强化追击同袍附加两笔（对方未建模）→ 段数钉 2，单段手算

待查清单（证据不足，不钉不改）：
待查① 白厄 E2 物穿官方限定变身期（"Khaslana's Physical RES PEN"），我方 EIDO
   stat_effects 常驻 → 变身前泄漏 0.2（eidolon 块无 enable_if 通道，报回 owner）
待查② 弑魂反击官方"视为战技伤害"（DMG considered as Skill DMG），我方
   pyre_counter 两行动 action_type=follow_up——战技限定 buff 命中口径待查
   （对拍注入件为全局池不判别，爵位战技限定 buff 落地时复核）
待查③ 奇袭当发技充能口径：我方当发 +1 再消 6 = 余 1（hook 声明序）；官方
   "During Coup de Main, Cerydra cannot gain Charge" 或读作余 0——待实测
待查④ 爵位抗穿 +10% 是否限定战技：对方按战技限定建模（damageType SKILL tag），
   官方"increases their All-Type RES PEN"未限定——对拍场=战技场景等价，非战技
   段口径待实测

已修真病两件（本批钓出，模板笔误级——单列）：
B-NEW⑤ 1408 fixture 弑魂反击·追击段漏叠层放大：官方"每层使该反击倍率 +20%
   （原始倍率）"覆盖整个反击（AoE + 4 段追击），pyre_counter_x trigger 缺
   scaling_atk 覆写 → 旧值追击 0.3 平铺（2 层总倍率 1.76 vs 官方 2.24）。
   已修（scaling_atk 0.3×(1+0.2×stacks)，与 pyre_counter 同式）
B-NEW⑥ 1412 fixture 见者 crit_rate 0.01→1.0：官方 1412102 #1[i]% = 100%
   （StarRailRes params [[1,1]]，[i] 渲染=值×100）——% 换算笔误，旧值 1%。
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
# 同 L2/组队级：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    _POLICY, _cast, _dummy, _hit_amounts, _inject, _make_logged, _stage,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死；fixture 终审值，行迹平铺按模板 trace_stat_effects 并入）
# ---------------------------------------------------------------------------

PH_ATK, PH_HP, PH_DEF, PH_SPD = 582.12, 1435.896, 703.395, 99
PH_CR, PH_CD = 0.17, 0.873
Z_PH = 0.5 * 0.9 * (1 + PH_CR * PH_CD)          # 白厄基准区 = 0.5167845
PH_ATK_T1 = PH_ATK * 1.5                        # 行迹 1 层（开局）= 873.18
PH_K_ATK = PH_ATK * 2.3                         # 变身 0.8 + 行迹 1 层 = 1338.876

CY_ATK_W = 620.9280000000001                    # 刻律德菈白值
CY_ATK = CY_ATK_W * 1.18                        # 行迹 atk_pct 0.18 后 = 732.69504
CY_WIND = 0.224                                 # 行迹风伤
Z_CY = 0.5 * 0.9 * 1.5                          # 见者 CR 1.05 封顶 1.0 → 期望 1.5
CY_ATK_BUFF = 0.24 * CY_ATK                     # 军功 ATK 待收件 = 175.8468096

SU_ATK, SU_CD = 640.332, 0.873
Z_SU = 0.5 * 0.9 * (1 + 0.05 * SU_CD)           # 0.4696425
SU_BEATIFIED_CD = 0.3 * SU_CD + 0.12            # 蒙福者快照 = 0.3819

TE_ATK_W = 582.1199999999999                    # 腾荒白值
TE_ATK = TE_ATK_W * 1.28                        # 行迹 atk_pct 0.28 后 = 745.1136
Z_TE = 0.5 * 0.9 * 1.025                        # 0.46125
TE_SHIELD = 0.2 * TE_ATK + 400                  # 战技/终结技盾 = 549.02272
TE_SHIELD_DRAGON = 0.1 * TE_ATK + 200           # 龙灵行动盾 = 274.51136
TE_ATK_BUFF = 0.15 * TE_ATK                     # 神秀 = 111.76704

# 结构差比值（映射表 P1-P5 / T-PH2）
P1_RATIO = 16.2 / 11.7                          # 18/13 ≈ 1.384615
P2_RATIO_2STACKS = 1.4                          # 1+0.2×2
P3_RATIO = (1 + 0.17 * 1.893) / (1 + 0.17 * 1.173) * 1.1   # ≈ 1.212255
P4_RATIO = (PH_ATK_T1 + CY_ATK_BUFF) / PH_ATK_T1           # ≈ 1.201387
T_PH2_RATIO = 2.25 / 1.75                       # 9/7 ≈ 1.285714


# ---------------------------------------------------------------------------
# 我方侧引擎件（白厄单人 / 白厄队 demo 编成）
# ---------------------------------------------------------------------------

def _phainon_build(*, eidolon: int = 0):
    member = {"character_template": "1408", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    return {"build": {"team": [member], "policy": _POLICY}}


def _phainon_compiled(*, eidolon: int = 0, enemies=None):
    return compile_encounter(_phainon_build(eidolon=eidolon),
                             _stage(enemies or _dummy("e1", "physical")),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _team_build():
    """demo_白厄队编成：白厄+刻律德菈+星期日+丹恒•腾荒（白厄编队首=缺省友方目标）."""
    return {"build": {"team": [
        {"character_template": "1408", "level": 80},
        {"character_template": "1412", "level": 80},
        {"character_template": "1313", "level": 80},
        {"character_template": "1414", "level": 80},
    ], "policy": _POLICY}}


def _team_dummy(*, n=1):
    """双弱点假人：physical（白厄/腾荒）+ wind（刻律附伤）——抗性区 1.0 基准."""
    return [{"actor_id": f"e{i+1}" if n > 1 else "e1", "name": f"假人{i+1}",
             "hp": 1e9, "spd": 100, "atk": 1000, "def": 1000, "max_toughness": 9999,
             "weakness": ["physical", "wind"]} for i in range(n)]


def _team_compiled(*, enemies=None):
    return compile_encounter(_team_build(), _stage(enemies or _team_dummy()),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _transform(eng):
    """火种钉 12 实打变身（140803）→ 进入卡厄斯兰那（毁伤 +4 / 境界植弱点）."""
    st = eng.state.actors["1408"]
    st.resources["fire_seed"] = 12.0     # 开局 hook 3 → 覆写钉死（激活口径）
    ult = next(a for a in eng.actions_by_actor["1408"] if a.action_id == "140803")
    assert eng._fire_ultimate(st, ult) is True
    assert st.state_config is not None and st.state_config.state == "khaslana"


def _ult_at(eng, owner, aid, energy, target):
    """对友方终结技（131303 族）：钉能量 + select_target 覆写指目标后实打."""
    st = eng.state.actors[owner]
    st.current_energy = energy
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    assert eng._fire_ultimate(st, ult) is True


def _seeds(eng):
    return eng.state.actors["1408"].resources["fire_seed"]


def _eff(eng, aid="1408"):
    return eng.pipeline.effective_stats(eng.state.actors[aid])


def _shield_of(eng, aid, shield_id):
    """护盾实例剩余值（PERMANSON_SHIELD 池逐件 FIFO——按 shield_id 直读）."""
    for s in eng.state.actors[aid].shields:
        if s.shield_id == shield_id:
            return s.remaining
    return None


# ---------------------------------------------------------------------------
# 对方侧场景模子（映射表见模块 docstring）
# ---------------------------------------------------------------------------

def _opt_phainon(action: str, *, eidolon: int = 0, cond: dict | None = None,
                 teammates: list | None = None, enemy_count: int = 1):
    """对方白厄场景：E0 中性钉死（变身/行迹层数/cdBuff/sustain 按场配）."""
    c = {"transformedState": False, "enhancedSkillType": 0,   # 0=FOUNDATION
         "atkBuffStacks": 1, "cdBuff": False, "sustainDmgBuff": False,
         "spdBuff": False, "cyreneSpecialEffect": False,
         "e1Buffs": True, "e2ResPen": True, "e6TrueDmg": True}
    c.update(cond or {})
    sc = {"kind": "character", "character_id": "1408", "eidolon": eidolon,
          "action": action, "element": "physical", "conditionals": c,
          "base": {"atk": PH_ATK, "hp": PH_HP, "def": PH_DEF, "spd": PH_SPD},
          "attacker": {"atk": PH_ATK, "hp": PH_HP, "def": PH_DEF, "spd": PH_SPD,
                       "cr": PH_CR, "cd": PH_CD},
          "self_path": "Destruction",
          "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                    "count": enemy_count}}
    if teammates is not None:
        sc["teammates"] = teammates
    return sc


def _opt_cerydra(action: str):
    """对方刻律德菈本人场景：spdBuff/crBuff 默认开（见者 CR 100%+征服者 20 速——
    atkToCd 为 dynamic conditional 未挂驱动，攻击 732.7<2000 门控两侧同灭）."""
    base = {"atk": CY_ATK_W, "hp": 1358.2800000000002, "def": 485.1, "spd": 99}
    return {"kind": "character", "character_id": "1412", "eidolon": 0,
            "action": action, "element": "wind",
            "conditionals": {"spdBuff": True, "crBuff": True, "atkToCd": True,
                             "e2DmgBoost": True, "e4UltDmg": True, "e6Buffs": True},
            "base": base,
            "attacker": {**base, "atk": CY_ATK, "hp": 1358.2800000000002 * 1.1,
                         "cr": 0.05, "cd": 0.5, "element_boost": CY_WIND},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_sunday(action: str):
    """对方日本人场景：defaults 全中性（talentCrBuffStacks 0/skillDmgBuff false）."""
    base = {"atk": SU_ATK, "hp": 1241.8560000000002, "def": 533.61, "spd": 96}
    return {"kind": "character", "character_id": "1313", "eidolon": 0,
            "action": action, "element": "imaginary",
            "conditionals": {"skillDmgBuff": False, "talentCrBuffStacks": 0,
                             "techniqueDmgBuff": False, "e1DefPen": False,
                             "e2DmgBuff": False},
            "base": base,
            "attacker": {**base, "def": 533.61 * 1.125, "cr": 0.05, "cd": SU_CD},
            "self_path": "Harmony",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _opt_terra(action: str):
    """对方腾荒本人场景：shieldAbility 默认 ult（盾段随行动落地）."""
    base = {"atk": TE_ATK_W, "hp": 1047.816, "def": 776.1600000001, "spd": 102}
    return {"kind": "character", "character_id": "1414", "eidolon": 0,
            "action": action, "element": "physical",
            "conditionals": {"shieldAbility": "ult"},
            "base": base,
            "attacker": {**base, "atk": TE_ATK, "def": 776.1600000001 * 1.225,
                         "cr": 0.05, "cd": 0.5},
            "self_path": "Preservation",
            "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                      "count": 1}}


def _tm_cerydra(**cond):
    c = {"militaryMerit": True, "peerage": False, "teammateATKValue": 0,
         "spdBuff": True, "cyreneSpecialEffect": True,
         "e1DefPen": True, "e2DmgBoost": True, "e6Buffs": True}
    c.update(cond)
    return {"character_id": "1412", "eidolon": 0, "path": "Harmony",
            "element": "wind", "conditionals": c}


def _tm_sunday(**cond):
    c = {"skillDmgBuff": True, "talentCrBuffStacks": 1, "beatified": True,
         "teammateCDValue": SU_CD, "techniqueDmgBuff": False,
         "e1DefPen": True, "e2DmgBuff": True, "e6CrToCdConversion": True}
    c.update(cond)
    return {"character_id": "1313", "eidolon": 0, "path": "Harmony",
            "element": "imaginary", "conditionals": c}


def _tm_terra(**cond):
    c = {"bondmate": True, "sourceAtk": TE_ATK, "cyreneSpecialEffect": True,
         "e1ResPen": True, "e4DmgReduction": True, "e6Buffs": True}
    c.update(cond)
    return {"character_id": "1414", "eidolon": 0, "path": "Preservation",
            "element": "physical", "conditionals": c}


# ===========================================================================
# L2 白厄 1408（对方 1400/Phainon.ts 全实现）——非变身链
# ===========================================================================

class TestPhainonDuipai:
    """白厄 E0 非变身：普攻/战技全等（双锚+乘区读回）+ 变身本体双无伤."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_phainon("basic"))
        st = theirs["stats"]
        assert st["atk"] == pytest.approx(PH_ATK_T1, rel=REL_TOL), (
            "行迹 1 层 ATK_P 0.5 白值换算通道")
        assert st["cr"] == pytest.approx(PH_CR, rel=REL_TOL)
        assert st["cd"] == pytest.approx(PH_CD, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_phainon_compiled())
        assert math.isclose(_eff(eng)["atk"], PH_ATK_T1, rel_tol=1e-9), (
            "我方行迹 1 层面板（照见英雄本色 atk_pct 0.5）")
        _cast(eng, "1408", "140801")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon("basic"))

        hand = 1.0 * PH_ATK_T1 * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", 1 + PH_CR * PH_CD), ("abilityMulti", PH_ATK_T1)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill_single(self, optimizer_driver):
        """战技 lv10=3.0 单体场（1 敌 → blast 无相邻）：双方全等."""
        eng, log = _make_logged(_phainon_compiled())
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon("skill"))

        hand = 3.0 * PH_ATK_T1 * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_blast_three(self, optimizer_driver):
        """战技 blast（对方只建主目标单发=建模收敛，D6 同族）：3 敌场打中位 e2，
        主 3.0 == 对方，相邻 1.2×2 手算自证（140802 lv10 #2=1.2）."""
        eng, log = _make_logged(_phainon_compiled(enemies=_dummy("e1", "physical", n=3)))
        _cast(eng, "1408", "140802", target="e2")
        adj1 = _hit_amounts(log, source="1408", target="e1")
        main = _hit_amounts(log, source="1408", target="e2")
        adj3 = _hit_amounts(log, source="1408", target="e3")
        theirs = run_optimizer(optimizer_driver, _opt_phainon("skill", enemy_count=3))

        assert main == pytest.approx([3.0 * PH_ATK_T1 * Z_PH], rel=REL_TOL)
        assert main[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "主目标段双方互对（对方 enemyCount 不进战技倍率）")
        assert adj1 == pytest.approx([1.2 * PH_ATK_T1 * Z_PH], rel=REL_TOL), "相邻段① vs 手算"
        assert adj3 == pytest.approx([1.2 * PH_ATK_T1 * Z_PH], rel=REL_TOL), "相邻段② vs 手算"

    def test_ult_transform_entry_no_damage(self, optimizer_driver):
        """变身技本体无伤害（伤害在 final_strike）：我方实打变身零伤害事件 + 境界
        植弱点行为锚（对方无境界概念——单钉）；对方非变身 ULT 空 hits 比零."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon("ult"))

        assert ours == [], "变身入口无伤害段"
        assert theirs["total"] == 0.0 and theirs["hits"] == [], "对方非变身 ULT 无 hits"
        assert "ZONE_PHY_WEAK" in eng.state.actors["e1"].modifiers, (
            "境界时墟铁墓：敌方全体植物理弱点（140803 apply_modifiers——行为锚单钉）")


# ===========================================================================
# L2 白厄变身链（卡厄斯兰那——全游最复杂机制，对到哪算哪）
# ===========================================================================

class TestPhainonTransformed:
    """变身态：强化普攻全等 / 死星天裁 P1 钉差 / 弑魂反击 P2 钉差 / 最后一击全等."""

    def test_enhanced_basic(self, optimizer_driver):
        """创生•血棘渡亡 lv6=2.5（变身 0.8+行迹 1 层面板 1338.876）：单敌全等."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        assert math.isclose(_eff(eng)["atk"], PH_K_ATK, rel_tol=1e-9), (
            "我方变身面板（state_config atk_pct 0.8 + 行迹 0.5）")
        log.clear()
        _cast(eng, "1408", "140808")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "basic", cond={"transformedState": True}))

        hand = 2.5 * PH_K_ATK * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方强化普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(PH_K_ATK, rel=REL_TOL), (
            "对方变身 ATK_P（天赋 0.8 + 行迹 0.5×1）白值换算")

    def test_enhanced_basic_blast_three(self, optimizer_driver):
        """强化普攻 blast（对方收敛单发，D6 同族）：主 2.5 == 对方，相邻 0.75×2 手算."""
        eng, log = _make_logged(_phainon_compiled(enemies=_dummy("e1", "physical", n=3)))
        _transform(eng)
        log.clear()
        _cast(eng, "1408", "140808", target="e2")
        adj1 = _hit_amounts(log, source="1408", target="e1")
        main = _hit_amounts(log, source="1408", target="e2")
        adj3 = _hit_amounts(log, source="1408", target="e3")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "basic", cond={"transformedState": True}, enemy_count=3))

        assert main == pytest.approx([2.5 * PH_K_ATK * Z_PH], rel=REL_TOL)
        assert main[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert adj1 == pytest.approx([0.75 * PH_K_ATK * Z_PH], rel=REL_TOL), "相邻段① vs 手算"
        assert adj3 == pytest.approx([0.75 * PH_K_ATK * Z_PH], rel=REL_TOL), "相邻段② vs 手算"

    def test_foundation_ruin7_divergence(self, optimizer_driver):
        """P1：死星天裁毁伤 7（变身 4 + 血棘×2 → 8 截 7）→ 26 段×0.45（28 截 26）
        + 额外均分 4.5（消耗≥4）== 16.2 总倍率；对方固定 26×0.45=11.7 聚合、不建
        450% 额外 → 我方/对方 恰为 18/13（逐段手算 + 总和比值双钉）."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        _cast(eng, "1408", "140808")     # 毁伤 4+2=6
        _cast(eng, "1408", "140808")     # 毁伤 6+2=8 → 截 7
        st = eng.state.actors["1408"]
        assert math.isclose(st.resources["ruin"], 7.0), "毁伤上限 7（E0）"
        log.clear()
        _cast(eng, "1408", "140811")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"transformedState": True}))   # FOUNDATION 默认

        assert math.isclose(st.resources["ruin"], 0.0), "施放消耗全部毁伤"
        assert len(ours) == 27, f"1 段额外均分 + 26 段弹射（实收 {len(ours)} 段）"
        # 段序：consume_all_resource → on_resource_gain 钩嵌套发 verdict_extra（insert
        # 因果序）→ 本家 26 段弹射——额外段先落地（记录仪 setup 前订阅口径）
        assert ours[0] == pytest.approx(4.5 * PH_K_ATK * Z_PH, rel=REL_TOL), (
            "额外均分段（verdict_extra 消耗≥4 触发）vs 手算")
        for amt in ours[1:]:
            assert amt == pytest.approx(0.45 * PH_K_ATK * Z_PH, rel=REL_TOL), (
                "弹切段逐段 vs 手算")
        assert sum(ours) == pytest.approx(16.2 * PH_K_ATK * Z_PH, rel=REL_TOL)
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(11.7, rel=REL_TOL), (
            "对方聚合口径：26×0.45/敌数（450% 额外未建模）")
        assert theirs["total"] == pytest.approx(11.7 * PH_K_ATK * Z_PH, rel=REL_TOL)
        assert sum(ours) / theirs["total"] == pytest.approx(P1_RATIO, rel=REL_TOL), (
            "P1 结构差恰为 16.2/11.7 = 18/13")

    def test_calamity_no_damage(self, optimizer_driver):
        """弑魂焚诏双无伤：我方施放零伤害事件（buff+敌方立即行动，手动场无后续）；
        对方 CALAMITY 档 skill 空 hits 比零."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        log.clear()
        _cast(eng, "1408", "140809")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"transformedState": True, "enhancedSkillType": 1}))

        assert ours == [], "弑魂焚诏本体无伤害（反击在敌方行动后）"
        assert theirs["total"] == 0.0 and theirs["hits"] == []
        assert "SOUL_PYRE" in eng.state.actors["1408"].modifiers, "弑魂之炽 1 层已挂"
        assert math.isclose(eng.state.actors["1408"].resources["ruin"], 5.0), (
            "毁伤 4+1（敌方全体数量 1）")

    def test_counter_two_stacks_divergence(self, optimizer_driver):
        """P2：弑魂反击 2 层（施放 1 + 敌方行动 1）→ 官方倍率 (0.4+4×0.3)×1.4=2.24
        （每层 +20% 原始倍率覆盖整个反击——B-NEW⑤ 修复后我方同式）；对方 1.60 平铺
        =0 层口径（不建叠层放大）→ 我方/对方 恰为 1.4."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        _cast(eng, "1408", "140809")
        log.clear()
        # 敌方行动（手动补发——hook ① 叠层 + ② 阈值反击的触发口径）
        eng.bus.emit("on_action", {
            "actor": "e1", "action_type": "basic", "action_id": "e1_atk",
            "target_type": "single", "target": "1408",
            "actor_type": "monster"}, eng.state)
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "fua", cond={"transformedState": True}))

        assert "SOUL_PYRE" not in eng.state.actors["1408"].modifiers, "反击后解除"
        assert len(ours) == 5, f"AoE 1 段 + 追击 4 段（实收 {len(ours)} 段）"
        assert ours[0] == pytest.approx(0.4 * 1.4 * PH_K_ATK * Z_PH, rel=REL_TOL), (
            "AoE 段 0.4×(1+0.2×2) vs 手算")
        for amt in ours[1:]:
            assert amt == pytest.approx(0.3 * 1.4 * PH_K_ATK * Z_PH, rel=REL_TOL), (
                "追击段 0.3×(1+0.2×2) vs 手算（B-NEW⑤ 修复后同放大）")
        assert sum(ours) == pytest.approx(2.24 * PH_K_ATK * Z_PH, rel=REL_TOL)
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(1.6, rel=REL_TOL), (
            "对方聚合 0.40+4×0.30 平铺（叠层放大未建模）")
        assert theirs["total"] == pytest.approx(1.6 * PH_K_ATK * Z_PH, rel=REL_TOL)
        assert sum(ours) / theirs["total"] == pytest.approx(P2_RATIO_2STACKS, rel=REL_TOL), (
            "P2 结构差恰为 1+0.2×2 = 1.4")

    def test_final_strike(self, optimizer_driver):
        """最后一击 lv10=9.6 均分（单敌全吃）：我方 final_strike 实打 vs 对方变身
        ULT 9.60 单发——双锚全等（终结技类别归因两侧同）."""
        eng, log = _make_logged(_phainon_compiled())
        _transform(eng)
        log.clear()
        _cast(eng, "1408", "final_strike")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "ult", cond={"transformedState": True}))

        hand = 9.6 * PH_K_ATK * Z_PH
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方最后一击 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_e2_transformed_basic(self, optimizer_driver):
        """E2 链：E1 开大暴伤 +50%（我方 on_ultimate 钩 vs 对方常开 precompute 件）
        + E2 变身物穿 20%（双方各自通道）→ 强化普攻三方全等."""
        eng, log = _make_logged(_phainon_compiled(eidolon=2))
        _transform(eng)   # E1 钩随变身开大挂 E1_CRIT_DMG
        assert math.isclose(_eff(eng)["crit_dmg"], PH_CD + 0.5, rel_tol=1e-9)
        assert math.isclose(_eff(eng)["res_pen"], 0.2, rel_tol=1e-9)
        log.clear()
        _cast(eng, "1408", "140808")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "basic", eidolon=2, cond={"transformedState": True}))

        z_e2 = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.5)) * 1.2
        hand = 2.5 * PH_K_ATK * z_e2
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 E2 链 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.2, rel=REL_TOL)
        assert theirs["stats"]["cd"] == pytest.approx(PH_CD + 0.5, rel=REL_TOL)


# ===========================================================================
# L2 刻律德菈 1412 本人（basic/ult 双段全等——见者 CR 100% 修复后首验）
# ===========================================================================

class TestCerydraDuipai:
    """刻律德菈 E0：普攻/终结技三方全等（atkToCd dynamic 未挂驱动，732.7<2000
    门控两侧同灭；spdBuff +20 速度无伤害消费）."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(compile_encounter(
            {"build": {"team": [{"character_template": "1412", "level": 80}],
                       "policy": _POLICY}},
            _stage(_dummy("e1", "wind")), template_roots=TEST_TEMPLATE_ROOTS))
        assert math.isclose(_eff(eng, "1412")["crit_rate"], 1.05, rel_tol=1e-9), (
            "见者 CR +100%（B-NEW⑥ 修复后口径）")
        _cast(eng, "1412", "141201")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _opt_cerydra("basic"))

        hand = 1.0 * CY_ATK * (1 + CY_WIND) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(1 + CY_WIND, rel=REL_TOL)
        assert bd["critMulti"] == pytest.approx(1.5, rel=REL_TOL), "CR 1.05 封顶 1.0 两侧同"
        assert theirs["stats"]["cr"] == pytest.approx(1.05, rel=REL_TOL)

    def test_ult(self, optimizer_driver):
        eng, log = _make_logged(compile_encounter(
            {"build": {"team": [{"character_template": "1412", "level": 80}],
                       "policy": _POLICY}},
            _stage(_dummy("e1", "wind")), template_roots=TEST_TEMPLATE_ROOTS))
        _ult_at(eng, "1412", "141203", 130.0, "1412")
        ours = _hit_amounts(log, source="1412")
        theirs = run_optimizer(optimizer_driver, _opt_cerydra("ult"))

        hand = 2.4 * CY_ATK * (1 + CY_WIND) * Z_CY
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算（lv10 2.4 AoE）"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# L2 星期日 1313 本人（basic 单段全等——增益件均为队友链/非伤害）
# ===========================================================================

class TestSundayDuipai:
    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(compile_encounter(
            {"build": {"team": [{"character_template": "1313", "level": 80}],
                       "policy": _POLICY}},
            _stage(_dummy("e1", "imaginary")), template_roots=TEST_TEMPLATE_ROOTS))
        _cast(eng, "1313", "131301")
        ours = _hit_amounts(log, source="1313")
        theirs = run_optimizer(optimizer_driver, _opt_sunday("basic"))

        hand = 1.0 * SU_ATK * Z_SU
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# L2 丹恒•腾荒 1414 本人（basic/ult 全等 + 护盾段双锚 + 龙灵强化追击）
# ===========================================================================

class TestTerraDuipai:
    """腾荒 E0：普攻/终结技全等；终结技盾段与对方 ShieldDamageFunction 双锚；
    强化龙灵追击主段全等 + 同袍附加两笔 T-TE1 单锚."""

    def _terra_compiled(self):
        return compile_encounter(
            {"build": {"team": [{"character_template": "1414", "level": 80}],
                       "policy": _POLICY}},
            _stage(_dummy("e1", "physical")), template_roots=TEST_TEMPLATE_ROOTS)

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(self._terra_compiled())
        _cast(eng, "1414", "141401")
        ours = _hit_amounts(log, source="1414")
        theirs = run_optimizer(optimizer_driver, _opt_terra("basic"))

        hand = 1.0 * TE_ATK * Z_TE
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_ult_and_shield(self, optimizer_driver):
        """终结技 3.0 AoE 全等 + 全队盾 0.2×atk+400：我方 PERMANSON_SHIELD 池实例
        vs 对方 ultShield 段（ShieldDamageFunction）——护盾发射点双锚."""
        eng, log = _make_logged(self._terra_compiled())
        _ult_at(eng, "1414", "141403", 135.0, "1414")
        ours = _hit_amounts(log, source="1414")
        theirs = run_optimizer(optimizer_driver, _opt_terra("ult"))

        hand = 3.0 * TE_ATK * Z_TE
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方终结技 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        # 盾段双锚（0.2×745.1136+400 = 549.02272）
        assert _shield_of(eng, "1414", "TERRA_SHIELD") == pytest.approx(
            TE_SHIELD, rel=REL_TOL), "我方护盾实例 vs 手算"
        assert theirs["hits"][1]["damage"] == pytest.approx(TE_SHIELD, rel=REL_TOL), (
            "对方 ultShield 段 vs 手算")
        assert theirs["hits"][1]["damage_function"] == "Shield"

    def test_enhanced_souldragon_fua(self, optimizer_driver):
        """强化龙灵行动（白厄同袍场——真实编成口径）：主段 0.8×腾荒 atk 物理全等
        （神秀落白厄面板，腾荒自身攻击不带入）；同袍附加 0.8 + 峥嵘强化段 0.4
        （基数=同袍白厄神秀后攻击 984.947）对方未建模——T-TE1 单锚手算；
        龙灵行动盾 0.1×atk+200 与对方 fuaShield 段双锚."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1414", "141402", target="1408")   # 同袍=白厄 + 龙灵召唤
        assert "1414_souldragon" in eng.state.actors
        _ult_at(eng, "1414", "141403", 135.0, "1414")  # 强化计数 2 层
        log.clear()
        eng.bus.emit("on_action", {
            "actor": "1414_souldragon", "action_type": "memosprite_skill",
            "action_id": "souldragon_act", "target_type": "self",
            "target": "1414_souldragon", "actor_type": "summon"}, eng.state)
        main = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1414"
                and e.get("action_type") == "follow_up"]
        adds = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1414"
                and e.get("action_type") == "additional"]
        theirs = run_optimizer(optimizer_driver, _opt_terra("fua"))

        hand_main = 0.8 * TE_ATK * Z_TE
        assert main == pytest.approx([hand_main], rel=REL_TOL), (
            "我方龙灵追加主段（物理 AoE，单敌）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_main, rel=REL_TOL)
        assert main[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "主段双方互对"
        # T-TE1：同袍附加两笔（对方未建模——单锚手算；基数=白厄神秀后攻击）
        tongpao_atk = PH_ATK_T1 + TE_ATK_BUFF
        assert adds == pytest.approx([0.8 * tongpao_atk * Z_TE, 0.4 * tongpao_atk * Z_TE],
                                     rel=REL_TOL), (
            "同袍附加 0.8 + 峥嵘强化段 0.4（白厄物理附加——动态元素族）vs 手算")
        assert len(theirs["hits"]) == 2, "对方 FUA 只建主段+盾段（附加两笔未建模）"
        # 龙灵行动盾双锚（0.1×745.1136+200 = 274.51136）
        assert _shield_of(eng, "1408", "TERRA_SHIELD_DRAGON") == pytest.approx(
            TE_SHIELD_DRAGON, rel=REL_TOL), "我方龙灵行动盾（全队——读白厄侧实例）vs 手算"
        assert theirs["hits"][1]["damage"] == pytest.approx(TE_SHIELD_DRAGON, rel=REL_TOL), (
            "对方 fuaShield 段 vs 手算")


# ===========================================================================
# 组队矩阵① 刻律德菈 → 白厄（军功指针=独特目标代数；火种/速度/暴伤传导）
# ===========================================================================

class TestCerydraToPhainon:
    """141202 指白厄：火种 +1（140804 成为目标）+ 暴伤 +30%（队友施放）+ 军功 +
    征服者速度——传导链逐通道比等；军功 ATK/爵位 buff 待收钉 P4/P3."""

    def test_merit_seed_cd_spd_channels(self, optimizer_driver):
        """非伤害传导三通道：火种 3→4 / 暴伤 0.873→1.173 / 速度 99→119（双方回显互对）."""
        eng, log = _make_logged(_team_compiled())
        assert math.isclose(_seeds(eng), 3.0), "开局行迹 3 火种"
        _cast(eng, "1412", "141202", target="1408")
        assert math.isclose(_seeds(eng), 4.0), "成为技能目标 +1（140804——火种指针）"
        assert "CYD_MERIT" in eng.state.actors["1408"].modifiers, "军功唯一通道授予"
        assert math.isclose(_eff(eng)["crit_dmg"], PH_CD + 0.3, rel_tol=1e-9), (
            "队友施放 → 暴伤 +30%（140804 后半）")
        assert math.isclose(_eff(eng)["spd"], 119.0, rel_tol=1e-9), (
            "征服者 spd+20（1412103——目标与刻律）")
        assert math.isclose(_eff(eng, "1412")["spd"], 119.0, rel_tol=1e-9), "刻律自身同挂"
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_cerydra()]))
        assert theirs["stats"]["spd"] == pytest.approx(119.0, rel=REL_TOL), (
            "对方 SPD+20 落主 C 容器（SingleTarget 折叠口径）")
        assert theirs["stats"]["cd"] == pytest.approx(PH_CD + 0.3, rel=REL_TOL)

    def test_skill_merit_neutral(self, optimizer_driver):
        """军功态白厄战技：军功 ATK/爵位待收件中性化（atkValue 0/peerage false）
        → 传导链全等（暴伤 1.173 + 攻击 873.18 双方同）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_cerydra()]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        hand = 3.0 * PH_ATK_T1 * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_merit_atk_injected(self, optimizer_driver):
        """军功 ATK 待收（P4）→ 注入 atk 175.8468（=0.24×刻律行迹后攻击）等价件
        → 比等；对方 teammateATKValue 钉 732.69504 同源."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        _inject(eng, "1408", "XC_CY_ATK", {"atk": CY_ATK_BUFF})
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True},
            teammates=[_tm_cerydra(teammateATKValue=CY_ATK)]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        hand = 3.0 * (PH_ATK_T1 + CY_ATK_BUFF) * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方注入件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(PH_ATK_T1 + CY_ATK_BUFF, rel=REL_TOL)

    def test_skill_merit_atk_divergence(self, optimizer_driver):
        """P4：不注入 → 对方恰为我方 ×(1049.0268/873.18)（差值恰为攻击区比，
        其余乘区全等）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")[0]
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True},
            teammates=[_tm_cerydra(teammateATKValue=CY_ATK)]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        assert ours == pytest.approx(3.0 * PH_ATK_T1 * z, rel=REL_TOL), "我方无军功 ATK 基准链"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(P4_RATIO, rel=REL_TOL), (
            "P4 结构差恰为攻击区比 (873.18+175.8468)/873.18")

    def test_skill_peerage_injected(self, optimizer_driver):
        """爵位 buff 待收（P3）→ 注入 {crit_dmg .72, res_pen .1} 等价件（战技场景
        限定——对方 damageType SKILL tag 同口径）→ 比等."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        _inject(eng, "1408", "XC_PEERAGE", {"crit_dmg": 0.72, "res_pen": 0.1})
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_cerydra(peerage=True)]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3 + 0.72)) * 1.1
        hand = 3.0 * PH_ATK_T1 * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方注入件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        assert bd["resMulti"] == pytest.approx(1.1, rel=REL_TOL), (
            "对方爵位 RES_PEN 0.10（战技限定 tag 落 SKILL 段）")

    def test_skill_peerage_divergence(self, optimizer_driver):
        """P3：不注入 → 对方恰为我方 ×1.212255（暴伤承 1.893/1.173 × 抗穿 1.1）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")[0]
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_cerydra(peerage=True)]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        assert ours == pytest.approx(3.0 * PH_ATK_T1 * z, rel=REL_TOL), "我方无爵位基准链"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(P3_RATIO, rel=REL_TOL), (
            "P3 结构差恰为 (1+0.17×1.893)/(1+0.17×1.173)×1.1")

    def test_coup_de_main_copy(self, optimizer_driver):
        """P6 奇袭（对方未建模——行为锚+手算）：充能堆到 6 后军功持有者放战技 →
        复制再放一次（两段 140802 全值）+ 消耗 6 充能。充能口径：141202 挂军功 1
        → 白厄普攻×5（天赋各 +1）= 6 → 战技当发 +1=7（④先于⑤，待查③在案）
        → 奇袭消 6 = 余 1。暴伤件持续 3 回合（tick 锚=回合——手动 action 链不消费，
        全程 cd 1.173 口径）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        for _ in range(5):
            _cast(eng, "1408", "140801")
        assert math.isclose(eng.state.actors["1412"].resources["cerydra_charge"], 6.0), (
            "充能 1+5=6（爵位升级点）")
        log.clear()
        _cast(eng, "1408", "140802")
        skill_hits = [e["amount"] for e in log
                      if e.get("reason") == "hit" and e.get("source") == "1408"
                      and e.get("action_type") == "skill"]

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        assert len(skill_hits) == 2, "奇袭复制 → 战技两段（原发+复制）"
        for amt in skill_hits:
            assert amt == pytest.approx(3.0 * PH_ATK_T1 * z, rel=REL_TOL), (
                "复制段=原段全值（cd 1.173 手算）")
        assert math.isclose(eng.state.actors["1412"].resources["cerydra_charge"], 1.0), (
            "当发 +1（④）→ 奇袭消 6（⑤）= 余 1（待查③口径）")
        assert math.isclose(_seeds(eng), 4.0 + 4.0), (
            "战技自家 resource_gain +2×2（复制=真战技再放——火种指针同吃）")


# ===========================================================================
# 组队矩阵② 星期日 → 白厄（战技增伤/暴击率 + 蒙福者暴伤 + 回能火种）
# ===========================================================================

class TestSundayToPhainon:
    def test_skill_boost_cr(self, optimizer_driver):
        """131302 指白厄：增伤 0.3（无召唤物档）+ 暴击率 0.2 + 暴伤 0.3（140804）
        + 火种 +1——三 buff 跨 actor 传导三方全等."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1313", "131302", target="1408")
        assert math.isclose(_seeds(eng), 4.0), "成为技能目标 +1"
        assert math.isclose(_eff(eng)["dmg_bonus"].get("all", 0.0), 0.3, rel_tol=1e-9)
        assert math.isclose(_eff(eng)["crit_rate"], PH_CR + 0.2, rel_tol=1e-9)
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_sunday(beatified=False)]))

        z = 0.5 * 0.9 * (1 + (PH_CR + 0.2) * (PH_CD + 0.3)) * 1.3
        hand = 3.0 * PH_ATK_T1 * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.3, rel=REL_TOL), "对方战技增伤 0.3（无召唤物档——hasSummons=false）"

    def test_beatified_ult(self, optimizer_driver):
        """131303 指白厄：蒙福者暴伤 0.3819（0.3×星期日暴伤+0.12 快照）+ 回能 →
        火种 +2（目标 1 + 回能 1，140804/1408102 双通道）——三方全等."""
        eng, log = _make_logged(_team_compiled())
        _ult_at(eng, "1313", "131303", 130.0, "1408")
        assert math.isclose(_seeds(eng), 5.0), "目标 1 + 回能 1 = +2（火种指针双通道）"
        assert "BEATIFIED" in eng.state.actors["1408"].modifiers
        assert math.isclose(_eff(eng)["crit_dmg"], PH_CD + 0.3 + SU_BEATIFIED_CD,
                            rel_tol=1e-9), "140804 暴伤 + 蒙福者快照同挂"
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_sunday(
                skillDmgBuff=False, talentCrBuffStacks=0, beatified=True)]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3 + SU_BEATIFIED_CD))
        hand = 3.0 * PH_ATK_T1 * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["cd"] == pytest.approx(PH_CD + 0.3 + SU_BEATIFIED_CD,
                                                      rel=REL_TOL), (
            "对方蒙福者 CD = 0.3×0.873+0.12（teammateCDValue 钉快照同源）")


# ===========================================================================
# 组队矩阵③ 丹恒•腾荒 → 白厄（同袍攻/护盾发射点 + sustain P5 钉差）
# ===========================================================================

class TestTerraToPhainon:
    def test_bondmate_atk_and_shield(self, optimizer_driver):
        """141402 指白厄：同袍 + 神秀 ATK+111.767（快照 vs 滑块同源）+ 全队盾
        549.0227（teammate 链无盾件——单锚手算）+ 火种 +1 + 暴伤 0.3——
        sustainDmgBuff 钉 false 中性化 → 攻击/暴伤通道全等."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1414", "141402", target="1408")
        assert math.isclose(_seeds(eng), 4.0), "成为技能目标 +1"
        assert "TONGPAO" in eng.state.actors["1408"].modifiers, "同袍唯一通道授予"
        assert math.isclose(_eff(eng)["atk"], PH_ATK_T1 + TE_ATK_BUFF, rel_tol=1e-9), (
            "神秀快照（0.15×腾荒行迹后攻击）")
        assert _shield_of(eng, "1408", "TERRA_SHIELD") == pytest.approx(
            TE_SHIELD, rel=REL_TOL), "我方护盾发射点（0.2×745.1136+400）——单锚手算"
        assert "1414_souldragon" in eng.state.actors, "生生之德：龙灵召唤"
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True}, teammates=[_tm_terra()]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        hand = 3.0 * (PH_ATK_T1 + TE_ATK_BUFF) * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["atk"] == pytest.approx(PH_ATK_T1 + TE_ATK_BUFF, rel=REL_TOL)

    def test_sustain_divergence(self, optimizer_driver):
        """P5：1408102 前半（受队友盾 → 增伤 45%）我方待收（护盾获得事件通道缺，
        fixture 头注在案）；对方 sustainDmgBuff×teamHasSustain 常开 0.45 →
        对方恰为我方 ×1.45（空增伤池）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1414", "141402", target="1408")
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")[0]
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True, "sustainDmgBuff": True},
            teammates=[_tm_terra()]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3))
        assert ours == pytest.approx(3.0 * (PH_ATK_T1 + TE_ATK_BUFF) * z, rel=REL_TOL), (
            "我方无 sustain 增伤基准链（待收实证）")
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(
            1.45, rel=REL_TOL), "对方 Preservation 队友 → teamHasSustain 常开件"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.45, rel=REL_TOL), (
            "P5 结构差恰为 ×1.45")

    def test_sustain_injected(self, optimizer_driver):
        """注入 all_dmg 0.45 等价件 → 三方全等（隔离唯一差=待收的 1408102 前半）."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1414", "141402", target="1408")
        _inject(eng, "1408", "XC_SUSTAIN", {"all_dmg": 0.45})
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True, "sustainDmgBuff": True},
            teammates=[_tm_terra()]))

        z = 0.5 * 0.9 * (1 + PH_CR * (PH_CD + 0.3)) * 1.45
        hand = 3.0 * (PH_ATK_T1 + TE_ATK_BUFF) * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方注入件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# 组队矩阵④ 三队友全开（组合场——T-PH2 龙灵归属口径差钉 9/7 + 对齐件隔离）
# ===========================================================================

class TestCombinedPhainonTeam:
    def _full_prep(self, eng):
        """刻律 141202→白厄 → 星期日 131302→白厄 → 腾荒 141402→白厄（火种 3+3=6）."""
        _cast(eng, "1412", "141202", target="1408")
        _cast(eng, "1313", "131302", target="1408")
        _cast(eng, "1414", "141402", target="1408")

    def test_all_buffs_divergence(self, optimizer_driver):
        """T-PH2：三队友全开 + 注入待收两件（军功 ATK/sustain）→ 仍差星期日召唤物
        档：对方 Terra bondmate → 共享 config hasSummons=true → 战技增伤 0.3+0.5；
        我方龙灵 summoner=丹恒 → has_summon(白厄)=0 → 0.3 单档。增伤池 2.25/1.75
        = 9/7 恰为结构差（其余乘区——攻击/暴击/暴伤/速度全等）."""
        eng, log = _make_logged(_team_compiled())
        self._full_prep(eng)
        assert math.isclose(_seeds(eng), 6.0), "三队友技各喂 1（火种指针）"
        _inject(eng, "1408", "XC_CY_ATK", {"atk": CY_ATK_BUFF})
        _inject(eng, "1408", "XC_SUSTAIN", {"all_dmg": 0.45})
        assert math.isclose(_eff(eng)["dmg_bonus"].get("all", 0.0), 0.75, rel_tol=1e-9), (
            "我方增伤池 0.3（星期日无召唤物档）+0.45（注入）")
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")[0]
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True, "sustainDmgBuff": True},
            teammates=[_tm_cerydra(teammateATKValue=CY_ATK), _tm_sunday(beatified=False),
                       _tm_terra()]))

        atk_full = PH_ATK_T1 + CY_ATK_BUFF + TE_ATK_BUFF
        z = 0.5 * 0.9 * (1 + (PH_CR + 0.2) * (PH_CD + 0.3))
        assert ours == pytest.approx(3.0 * atk_full * z * 1.75, rel=REL_TOL), "我方 vs 手算"
        hand_theirs = 3.0 * atk_full * z * 2.25
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_theirs, rel=REL_TOL), (
            "对方 vs 手算")
        bd = theirs["hits"][0]["breakdown"]
        assert bd["dmgBoostMulti"] == pytest.approx(2.25, rel=REL_TOL), (
            "对方池 0.3+0.5（hasSummons 档）+0.45（sustain）")
        assert theirs["stats"]["atk"] == pytest.approx(atk_full, rel=REL_TOL)
        assert theirs["stats"]["cr"] == pytest.approx(PH_CR + 0.2, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(T_PH2_RATIO,
                                                                   rel=REL_TOL), (
            "T-PH2 结构差恰为 2.25/1.75 = 9/7（龙灵归属待实测）")

    def test_all_buffs_aligned_oracle(self, optimizer_driver):
        """T-PH2 隔离件：再注入 all_dmg 0.5（对方口径的召唤物档等价）→ 组合场
        全链全等——证明唯一差 = 龙灵归属读法，其余跨 actor 传导两侧同构."""
        eng, log = _make_logged(_team_compiled())
        self._full_prep(eng)
        _inject(eng, "1408", "XC_CY_ATK", {"atk": CY_ATK_BUFF})
        _inject(eng, "1408", "XC_SUSTAIN", {"all_dmg": 0.45})
        _inject(eng, "1408", "XC_SUMMON_TIER", {"all_dmg": 0.5})
        _cast(eng, "1408", "140802")
        ours = _hit_amounts(log, source="1408")
        theirs = run_optimizer(optimizer_driver, _opt_phainon(
            "skill", cond={"cdBuff": True, "sustainDmgBuff": True},
            teammates=[_tm_cerydra(teammateATKValue=CY_ATK), _tm_sunday(beatified=False),
                       _tm_terra()]))

        atk_full = PH_ATK_T1 + CY_ATK_BUFF + TE_ATK_BUFF
        z = 0.5 * 0.9 * (1 + (PH_CR + 0.2) * (PH_CD + 0.3)) * 2.25
        hand = 3.0 * atk_full * z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方对齐件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"


# ===========================================================================
# 组队矩阵⑤ 刻律德菈天赋附伤（军功持有者攻击 → 0.6 风附加——对方未建模）
# ===========================================================================

class TestCerydraAdditional:
    def test_additional_on_merit_attack(self, optimizer_driver):
        """军功持有者（白厄）攻击 → 刻律附加 1 段 0.6×atk 风（after_being_hit 钩，
        seg0 单敌 1 段——多目标段数口径同 T2 在案）。对方天赋附伤未建（其
        actionDefinition 无此段）——单锚手算；数值公式同构见 L2 刻律本人链."""
        eng, log = _make_logged(_team_compiled())
        _cast(eng, "1412", "141202", target="1408")
        log.clear()
        _cast(eng, "1408", "140801")
        adds = [e for e in log
                if e.get("reason") == "hit" and e.get("source") == "1412"
                and e.get("action_type") == "additional"]

        hand = 0.6 * CY_ATK * (1 + CY_WIND) * Z_CY
        assert len(adds) == 1, "单敌单段攻击 → 1 段附加（141204 #3，20 次计数内）"
        assert adds[0]["amount"] == pytest.approx(hand, rel=REL_TOL), (
            "附加段 vs 手算（刻律行迹后面板 + 风伤 0.224 + 见者 CR 封顶期望 1.5）")
        assert math.isclose(eng.state.actors["1412"].resources["cerydra_fua_count"], 1.0), (
            "触发计数 +1（终结技重置口径）")
