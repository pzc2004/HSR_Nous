"""L3 装备级对拍（BACKLOG B22 扩展②）：同角色、同面板、装备同一光锥/遗器（两侧都装上）、
装备条件开关逐个钉死——逐段伤害 == hsr-optimizer 装备条件控制器整链伤害（rel_tol 1e-4）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character" + equipment 块（驱动头注有
完整链路口径）——对方 LC 控制器（本地注册表 + 命途门控镜像 resolver）precompute/finalize
并入角色链；套装经 calculateBasicSetEffects 真调用 + p2x/p4x 按套分派镜像 + p4t 终端镜像。
我方路径：真模板 YAML（fixtures 人工根优先）→ build 装备 light_cone_template/relics →
编译（白值并入 + 叠影绑定 + hooks/套装初始 modifier）→ CombatEngine。

统一口径（两侧一致，沿用 L2）：星魂钉死、行迹满级、假人 lvl80 def 1000（防御区 0.5）、
匹配弱点（抗性区 1.0）、未击破（0.9）、期望暴击（1+cr·cd）；面板 = 角色+光锥白值 +
行迹/套装各自原生通道——**套装基础件（p2c/p4c）与 LC 机制件两侧都不钉面板，各自通道**；
**LC 属性段**（暴击/命中类 properties，对方控制器不承载）对方侧钉进 attacker.* 终值面板。
Ratio 行迹 atk_pct 0.28/def_pct 0.125（fixture trace_stat_effects）→ 面板 atk = 白值×1.28。

===========================================================================
载体③ 真理医生 1305 buff 状态映射表（E0 钉死）
===========================================================================
对方 content id（默认）      我方模板对应                                  对拍处置
enemyDebuffStacks 0-5（5）    行迹「推理」≥3 负面 +10%/层 至多 50%——**待收**  钉 0 比等；钉 5 钉 ×1.5
                            （fixture 在案：debuff 通道缺时按未收编）        结构差（对方通用 BOOST 池）
summationStacks 0-6（6）      大行迹「归纳」战技每层 CR+2.5%/CD+5%（1层/次    逐场钉层数=我方现场层数
                            基线，stat_exprs 活读层）                        （战技后 FUA 钉 1）
（无开关）天赋追击 2.7×ATK    on_action 战技钩 deal_damage（确定性全触发=    FUA 段比等（单发 1 敌）
                            概率上界收录，B19 在案）
（无开关）终结技 2.4 + 短见   on_ultimate 钩挂 WISEMANS_FOLLY（自身伤害无    大招比等；短见=敌方 1 件
                            贡献；队友触发愚行——单人队不出）               负面（计入 scoped 计数）

===========================================================================
光锥 buff 状态映射表（对方条件开关 ↔ 我方模板 hooks；属性段=对方钉面板）
===========================================================================
23007 雨一直下 S1（黄泉）——属性段 EHR+24%（对方钉 effect_hit，无伤害消费）
enemy3DebuffsCrBoost（true） LC_23007_CRIT_RATE：debuff_count($event.target)≥3  钉 true+3 负面比等
                            → scoped crit_rate +12%（④-2 通道）
targetCodeDebuff（true）    LC_23007_AETHER_CODE：on_action 随机 1 敌挂【以太    施放 1 次挂码后第 2 次比等
                            编码】vulnerability 12%（对方=FullTeam VULN 件）
21001 晚安与睡颜（黄泉）     三层 scoped all_dmg（debuff_count≥1/2/3 各 12%）   钉 0/3 层比等；S5 叠影抽查
                            （对方 debuffStacksDmgIncrease 全局 BOOST 近似）
23000 银河铁道之夜 S1（黑塔）敌数攻击 atk_pct 9%×min(enemies_alive(),5)        3 敌场钉 enemyCount=3 比等
（enemyCountAtkBuff true）  （对方 ATK_P×context.enemyCount）
击破增伤 30%/1回合          on_break 钩（当次击破段不吃=钩在结算后）          击破后行动比等；
（enemyWeaknessBreakDmgBuff）                                              当次击破段钉 ×1.3 结构差
21027 早餐的仪式感 S1（黑塔）常驻 all_dmg 12%（**对方控制器未承载**——        对方钉 dmg_boost 0.12 面板比等
                            对方侧走钉死面板）；击杀叠层 atk_pct 4%×层         杀 1 后钉 defeatedEnemyAtkStacks=1
（defeatedEnemyAtkStacks 0-3）on_kill 钩（stat_exprs 活读层）                比等
23020 纯粹思维的洗礼 S1（真理医生）——属性段 CD+20%（对方钉 cd）
debuffCdStacks 0-3（3）     三层 scoped crit_dmg（debuff_count≥1/2/3 各 8%）  钉 3+3 负面比等
postUltBuff（true）         论辩：on_ultimate 钩 all_dmg 36%/2回合            大招后行动比等（负面计数
                            （对方 BOOST 36% 全局+FUA 限定 DEF_PEN 24%）       按事件时刻：战技段=短见 1
                                                                            件/追击段=短见+演绎 2 件，
                                                                            两侧同钉）；当次大招钉
                                                                            ×1.36 结构差；FUA 段钉
                                                                            25/22 结构差（scoped def_pen
                                                                            待收②在案）
23001 于夜色中 S1（真理医生）——属性段 CR+18%（对方钉 cr）
spdScalingBuffs（true）     LC_23001_NIGHT_SPD_STACKS：stat_exprs 活读速度     SPD 钉 160 → 6 层比等；
                            min(max(spd-100,0)/10,6)×6% 普攻/战技类型桶        SPD 155 钉 1.30/1.33 结构差
                            （**连续档** vs 对方 floor 阶梯——口径差在案）；    （我方连续近似，fixture 待实测）；
                            终结技 CD 档 **待收**（类型限定 scoped crit_dmg    大招钉 1.427/1.175 结构差
                            通道缺，fixture 在案）

===========================================================================
遗器 buff 状态映射表（套装基础件 p2c/p4c 两侧各自原生通道，不钉面板）
===========================================================================
116 系囚（黄泉）  2pc atk_pct 12%（对方 p2c↔我方套装初始 modifier——同白值基数）；
                 4pc dot_count≥1/2/3 scoped def_pen 6%×3（对方 value 钉层）
117 先驱（黄泉）  2pc has_debuff scoped all_dmg 12%（对方 value≥0 全局 BOOST）；
                 4pc 面板 CR 4% + debuff_count≥2/3 scoped CD 8%+4%（对方 CD_BOOST 档表
                 +p4c CR）；翻倍=施减益钩 +CR4%/CD 8%+4% 1回合（对方 value 3/4 档）
115 大公（黑塔）  2pc dmg_follow_up_dmg_boost 20%（对方 FUA 标签 BOOST）；
                 4pc 追击命中逐段叠 atk_pct 6%/层（段后挂层，新追击首段先摘）——
                 对方=p4x ATK_P×钉层 + finalizer 期望叠层曲线（ashblazingCompute）
109 乐队（黄泉）  2pc dmg_thunder 10%（对方 p2c 元素门控 LIGHTNING_DMG_BOOST）；
                 4pc 战技后 atk_pct 20%（on_action 结算后挂=当次不吃）——
                 对方 enabled 开关=无条件 precompute（当次即吃）

结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）：
E1 真理医生行迹「推理」（我方待收在案）→ 钉 5 层：对方/我方 = 1.5
E2 23020 论辩覆盖窗口（对方 precompute 含当次大招=建模近似，我方 on_ultimate
   结算后挂）→ 当次大招 1.36
E3 23020 论辩 FUA 无视防御 24%（我方待收②在案——scoped def_pen 通道已在，
   本件未收编）→ FUA 段 25/22 ≈ 1.13636（防御区 0.5 → 100/176）
E4 23001 速度档连续 vs 阶梯（我方连续近似在案 vs 对方 floor）→ SPD 155：
   对方/我方 = 1.30/1.33
E5 23001 终结技 CD 档（我方待收——类型限定 scoped crit_dmg 通道缺）→
   SPD 160 大招：对方/我方 = 1.427/1.175
E6 大公 4pc 叠层模型差（对方期望曲线当段即吃 vs 我方段后挂层当段不吃）→
   单发追击（1 敌钉 0 层）：对方/我方 = 1.06
E7 109 乐队 4pc 覆盖窗口（对方开关无条件当次即吃 vs 我方结算后挂）→
   当次战技 1.2
E8 23000 击破增伤覆盖窗口（同 E2/E7 族）→ 当次击破段 1.3
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.state import Modifier
# 同 L2：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    AC_ATK, HT_ATK, Z, _POLICY, _cast, _dummy, _hit_amounts, _inject, _make_logged,
    _stage,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死）
# ---------------------------------------------------------------------------

RT_ATK = 776.16            # 真理医生白值（fixture 终审值）
RT_HP, RT_DEF, RT_SPD = 1047.816, 460.845, 103
RT_CR, RT_CD = 0.17, 0.5   # cr 含行迹 flat 0.12（勘正①）
RT_TRACE_ATK_PCT = 0.28    # 行迹攻击力节点（trace_stat_effects）
ZR = 0.5 * 0.9 * (1 + RT_CR * RT_CD)   # 真理医生基准防御×未击破×期望暴击

# 光锥白值（fixture base_stats 终审值；hp/def 本测试不进伤害式，仅 atk 进手算锚）
LC23007_ATK, LC21001_ATK = 582.12, 476.28
LC23000_ATK, LC21027_ATK = 582.12, 476.28
LC23001_ATK, LC23020_ATK = 582.12, 582.12


def _rt_panel(lc_atk: float = 0.0) -> float:
    """真理医生终值面板 atk = (角色+光锥白值) × (1 + 行迹 28%)."""
    return (RT_ATK + lc_atk) * (1 + RT_TRACE_ATK_PCT)


# ---------------------------------------------------------------------------
# 我方侧 build 模子（装备块并入 member；e2e 先例同形 test_debuff_primitives.py）
# ---------------------------------------------------------------------------

def _member_build(template: str, *, lc: str | None = None, sup: int = 1,
                  set_id: str | None = None, pieces: int = 0):
    member = {"character_template": template, "level": 80}
    if lc:
        member["light_cone_template"] = lc
        member["light_cone"] = {"superimposition": sup}
    if set_id:
        member["relics"] = {f"slot{i}": {"set_id": set_id} for i in range(pieces)}
    return {"build": {"team": [member], "policy": _POLICY}}


def _compiled(build, element: str, enemies=None):
    return compile_encounter(build, _stage(enemies or _dummy("e1", element)),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _inject_debuffs(eng, target: str, n: int, *, mtype: str = "debuff",
                    source: str = "", via_engine: bool = False):
    """对拍注入负面件：直写（不触发钩——隔离翻倍族对照）或经引擎（触发
    after_apply_modifier——117 翻倍钩的正规激发口，source_id 指装备者）."""
    for i in range(n):
        mod = Modifier(
            modifier_id=f"XC_{mtype.upper()}_{i}", name=f"对拍负面{i}",
            modifier_type=mtype, duration=0, dispellable=False, source_id=source)
        if via_engine:
            eng._apply_modifier(eng.state.actors[target], mod)
        else:
            eng.state.actors[target].modifiers[mod.modifier_id] = mod


def _clean_knots(eng, wearer: str | None = None):
    """黄泉行迹 1 开局结（+5 残梦 + 随机敌 5 结——官方机制）隔离：负面计数类装备
    对拍要求负面件数 = 注入数，开局结摘除（连带的 117 翻倍三件——开局结经引擎
    施加会正规触发翻倍钩——同步摘除回空白 slate；叠加/翻倍由测试自重演）."""
    for st in eng.state.actors.values():
        st.modifiers.pop("CRIMSON_KNOT", None)
    if wearer:
        for mid in [m for m in eng.state.actors[wearer].modifiers if "DOUBLE" in m]:
            eng.state.actors[wearer].modifiers.pop(mid)


def _ult(eng, owner: str, action_id: str, energy: float):
    st = eng.state.actors[owner]
    st.current_energy = energy
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == action_id)
    assert eng._fire_ultimate(st, ult) is True


# ---------------------------------------------------------------------------
# 对方侧场景模子（条件开关默认中性钉死；装备块按需并）
# ---------------------------------------------------------------------------

def _opt(character_id: str, action: str, element: str, self_path: str, *,
         eidolon: int = 0, conditionals: dict | None = None,
         base: dict, attacker: dict, equipment: dict | None = None,
         enemy: dict | None = None, teammate_paths: list | None = None):
    sc = {
        "kind": "character", "character_id": character_id, "eidolon": eidolon,
        "action": action, "element": element, "conditionals": conditionals or {},
        "base": base, "attacker": attacker, "self_path": self_path,
        "enemy": enemy or {"level": 80, "damage_resistance": 0.0,
                           "weakness_broken": False, "count": 1},
    }
    if teammate_paths:
        sc["teammate_paths"] = teammate_paths
    if equipment:
        sc["equipment"] = equipment
    return sc


def _acheron_opt(action: str, *, equipment=None, atk=AC_ATK, enemy=None,
                 conditionals=None, extra_attacker=None):
    cond = {"crimsonKnotStacks": 9, "nihilityTeammatesBuff": False,
            "e1EnemyDebuffed": False, "thunderCoreStacks": 0,
            "stygianResurgeHitsOnTarget": 6, "e4UltVulnerability": True,
            "e6UltBuffs": True}
    cond.update(conditionals or {})
    return _opt("1308", action, "thunder", "Nihility", conditionals=cond,
                base={"atk": atk, "hp": 1125.432, "def": 436.59, "spd": 101},
                attacker={**{"atk": atk, "hp": 1125.432, "def": 436.59, "spd": 101,
                             "cr": 0.05, "cd": 0.5}, **(extra_attacker or {})},
                equipment=equipment, enemy=enemy)


def _herta_opt(action: str, *, equipment=None, atk=HT_ATK, enemy=None,
               conditionals=None, extra_attacker=None):
    cond = {"fuaStacks": 1, "techniqueBuff": False, "targetFrozen": False,
            "enemyHpGte50": False, "enemyHpLte50": False,
            "e2TalentCritStacks": 0, "e6UltAtkBuff": True}
    cond.update(conditionals or {})
    return _opt("1013", action, "ice", "Erudition", conditionals=cond,
                base={"atk": atk, "hp": 952.56, "def": 396.9, "spd": 100},
                attacker={**{"atk": atk, "hp": 952.56, "def": 396.9, "spd": 100,
                             "cr": 0.05, "cd": 0.5}, **(extra_attacker or {})},
                equipment=equipment, enemy=enemy)


def _ratio_opt(action: str, *, equipment=None, lc_atk=0.0, cr=RT_CR, cd=RT_CD,
               spd=RT_SPD, enemy=None, conditionals=None, extra_attacker=None):
    """真理医生对方场景：E0 双开关钉 0（映射表见模块 docstring）；面板 atk 含行迹 28%."""
    cond = {"enemyDebuffStacks": 0, "summationStacks": 0}
    cond.update(conditionals or {})
    white = RT_ATK + lc_atk
    atk = {**{"atk": _rt_panel(lc_atk), "hp": RT_HP, "def": RT_DEF, "spd": spd,
              "cr": cr, "cd": cd}, **(extra_attacker or {})}
    return _opt("1305", action, "imaginary", "Hunt", conditionals=cond,
                base={"atk": white, "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD},
                attacker=atk, equipment=equipment, enemy=enemy)


# ===========================================================================
# 载体③ 真理医生 1305 基线（新载体链自证：无装备逐段全等 + 行迹双通道）
# ===========================================================================

class TestRatioBaseline:
    """真理医生 E0 无装备：普攻/战技/追击/大招全等（行迹 28% 攻击 + 归纳层双锚）."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305"), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt("basic"))

        assert ours == pytest.approx([1.0 * _rt_panel() * ZR], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(1.0 * _rt_panel() * ZR, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(_rt_panel(), rel=REL_TOL), (
            "对方钉死面板 = 白值×1.28（行迹 28% 攻击走钉死面板，我方 trace 通道）")

    def test_skill_and_fua(self, optimizer_driver):
        """战技 1.5（归纳 0 层）+ 天赋追击 2.7（归纳 1 层——hook 序⑬先挂后追）."""
        eng, log = _make_logged(_compiled(_member_build("1305"), "imaginary"))
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")
        theirs_skill = run_optimizer(optimizer_driver, _ratio_opt("skill"))
        theirs_fua = run_optimizer(optimizer_driver, _ratio_opt(
            "fua", conditionals={"summationStacks": 1}))

        crit1 = 1 + (RT_CR + 0.025) * (RT_CD + 0.05)   # 归纳 1 层现场面板
        assert ours == pytest.approx(
            [1.5 * _rt_panel() * ZR, 2.7 * _rt_panel() * 0.5 * 0.9 * crit1], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL), (
            "追击段双方互对（summationStacks 钉 1 = 战技后现场 1 层）")

    def test_ult(self, optimizer_driver):
        """大招 2.4：短见挂目标（自身伤害无贡献；单人队愚行不出）."""
        eng, log = _make_logged(_compiled(_member_build("1305"), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt("ult"))

        assert ours == pytest.approx([2.4 * _rt_panel() * ZR], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRatioKnownDivergence:
    """E1：行迹「推理」≥3 负面 +10%/层 至多 50%——我方待收（fixture 在案）."""

    def test_deduction_trace(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305"), "imaginary"))
        _inject_debuffs(eng, "e1", 5)
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", conditionals={"enemyDebuffStacks": 5}))

        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.5, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.5, rel=REL_TOL)


# ===========================================================================
# 光锥对拍
# ===========================================================================

class TestLC23007IncessantRain:
    """雨一直下 S1（黄泉）：scoped 暴击（④-2 新通道）+ 以太编码承伤."""

    def test_scoped_cr_three_debuffs(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="23007"), "thunder"))
        _clean_knots(eng)
        _inject_debuffs(eng, "e1", 3)
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1308"])["effect_hit"], 0.24,
            rel_tol=1e-9), "我方 EHR 属性段 24%（无伤害消费——面板手算锚）"
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC23007_ATK,
            equipment={"light_cone": {
                "id": "23007", "superimposition": 1, "path": "Nihility",
                "conditionals": {"enemy3DebuffsCrBoost": True, "targetCodeDebuff": False}}}))

        hand = 1.0 * (AC_ATK + LC23007_ATK) * 0.5 * 0.9 * (1 + 0.17 * 0.5)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 scoped CR（3 负面 +12%）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.085, rel=REL_TOL)

    def test_aether_code_vulnerability(self, optimizer_driver):
        """以太编码：施放 1 次后目标承伤 +12%（我方钩挂敌方 vs 对方 FullTeam VULN 件）."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="23007"), "thunder"))
        _cast(eng, "1308", "130801")
        assert "LC_23007_AETHER_CODE" in eng.state.actors["e1"].modifiers, "首施挂码"
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC23007_ATK,
            equipment={"light_cone": {
                "id": "23007", "superimposition": 1, "path": "Nihility",
                "conditionals": {"enemy3DebuffsCrBoost": False, "targetCodeDebuff": True}}}))

        base = 1.0 * (AC_ATK + LC23007_ATK) * Z
        assert ours == pytest.approx([base, base * 1.12], rel=REL_TOL), (
            "我方两段：挂码前 ×1.0 / 挂码后 ×1.12")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.12, rel=REL_TOL)


class TestLC21001GoodNight:
    """晚安与睡颜（黄泉）：按目标负面数增伤（我方三层 scoped vs 对方全局 BOOST 近似）."""

    def test_three_debuffs(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="21001"), "thunder"))
        _clean_knots(eng)
        _inject_debuffs(eng, "e1", 3)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC21001_ATK,
            equipment={"light_cone": {
                "id": "21001", "superimposition": 1, "path": "Nihility",
                "conditionals": {"debuffStacksDmgIncrease": 3}}}))

        hand = 1.0 * (AC_ATK + LC21001_ATK) * Z * 1.36
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_zero_debuff(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="21001"), "thunder"))
        _clean_knots(eng)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC21001_ATK,
            equipment={"light_cone": {
                "id": "21001", "superimposition": 1, "path": "Nihility",
                "conditionals": {"debuffStacksDmgIncrease": 0}}}))

        hand = 1.0 * (AC_ATK + LC21001_ATK) * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_superimposition5(self, optimizer_driver):
        """叠影管道抽查（S5：12%→24%/层，三层 72%）——两侧叠影索引同链."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="21001", sup=5), "thunder"))
        _clean_knots(eng)
        _inject_debuffs(eng, "e1", 3)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC21001_ATK,
            equipment={"light_cone": {
                "id": "21001", "superimposition": 5, "path": "Nihility",
                "conditionals": {"debuffStacksDmgIncrease": 3}}}))

        hand = 1.0 * (AC_ATK + LC21001_ATK) * Z * 1.72
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23000MilkyWay:
    """银河铁道之夜 S1（黑塔）：敌数档攻击 + 击破增伤窗口."""

    def test_enemy_count_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="23000"), "ice",
            enemies=_dummy("e1", "ice", n=3)))
        _cast(eng, "1013", "101301", target="e2")
        ours = _hit_amounts(log, source="1013", target="e2")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC23000_ATK,
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 3},
            equipment={"light_cone": {
                "id": "23000", "superimposition": 1, "path": "Erudition",
                "conditionals": {"enemyCountAtkBuff": True,
                                 "enemyWeaknessBreakDmgBuff": False}}}))

        atk3 = (HT_ATK + LC23000_ATK) * 1.27   # 9%×3 敌
        hand = 1.0 * atk3 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 enemies_alive() 活读 3 敌"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(atk3, rel=REL_TOL), (
            "对方 ATK_P 0.27 白值换算通道")

    def test_break_boost_window(self, optimizer_driver):
        """E8 结构差：击破增伤 30%——我方 on_break 钩在结算后（当次击破段不吃），
        对方开关无条件（当次即吃）→ 当次击破段对方恰为 ×1.3；击破后行动双方比等
        （我方假人已击破→韧性区 1.0，对方场景钉 weakness_broken=true 对齐）。
        敌数攻击档全程生效（1 敌 ×1.09——与增伤窗口独立乘区，锚内含）."""
        frag = [{"actor_id": "e1", "name": "假人", "hp": 1e9, "spd": 100, "atk": 1000,
                 "def": 1000, "max_toughness": 10, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="23000"), "ice", enemies=frag))
        _cast(eng, "1013", "101301")   # 削韧 10 → 当次击破
        assert "LC_23000_DMG_ON_BREAK" in eng.state.actors["1013"].modifiers
        _cast(eng, "1013", "101301")   # 击破后：增伤 30% + 韧性区 1.0
        ours = _hit_amounts(log, source="1013")
        atk1 = (HT_ATK + LC23000_ATK) * 1.09   # 敌数档 1 敌

        assert ours[0] == pytest.approx(1.0 * atk1 * Z, rel=REL_TOL), "当次击破段无增伤"
        assert ours[1] == pytest.approx(1.0 * atk1 * 0.5 * 1.0 * 1.025 * 1.3, rel=REL_TOL), (
            "击破后：增伤 30% + 击破态韧性区 1.0")
        # 击破后行动：双方比等（对方钉已击破 + 增伤开关 + 敌数档 1 敌）
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC23000_ATK,
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": True,
                   "count": 1},
            equipment={"light_cone": {
                "id": "23000", "superimposition": 1, "path": "Erudition",
                "conditionals": {"enemyCountAtkBuff": True,
                                 "enemyWeaknessBreakDmgBuff": True}}}))
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        # 当次击破段：对方（未击破+开关）恰为我方 ×1.3
        theirs_first = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC23000_ATK,
            enemy={"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                   "count": 1},
            equipment={"light_cone": {
                "id": "23000", "superimposition": 1, "path": "Erudition",
                "conditionals": {"enemyCountAtkBuff": True,
                                 "enemyWeaknessBreakDmgBuff": True}}}))
        assert theirs_first["hits"][0]["damage"] / ours[0] == pytest.approx(1.3, rel=REL_TOL)


class TestLC21027Breakfast:
    """早餐的仪式感 S1（黑塔）：常驻 12%（对方走钉死面板）+ 击杀叠层."""

    def test_always_on_dmg(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21027"), "ice"))
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        # 映射表：对方控制器只承载击杀叠层——常驻 12% 钉进 dmg_boost 面板
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC21027_ATK,
            extra_attacker={"dmg_boost": 0.12},
            equipment={"light_cone": {
                "id": "21027", "superimposition": 1, "path": "Erudition",
                "conditionals": {"defeatedEnemyAtkStacks": 0}}}))
        hand = 1.0 * (HT_ATK + LC21027_ATK) * Z * 1.12
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方常驻 12% 钩 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_kill_stacks(self, optimizer_driver):
        enemies = _dummy("e1", "ice") + [
            {"actor_id": "e2", "name": "假人2", "hp": 100.0, "spd": 100, "atk": 1000,
             "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", lc="21027"), "ice", enemies=enemies))
        _cast(eng, "1013", "101301", target="e2")   # 击杀 → on_kill 叠 1 层
        _cast(eng, "1013", "101301", target="e1")
        ours = _hit_amounts(log, source="1013", target="e1")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", atk=HT_ATK + LC21027_ATK,
            extra_attacker={"dmg_boost": 0.12},
            equipment={"light_cone": {
                "id": "21027", "superimposition": 1, "path": "Erudition",
                "conditionals": {"defeatedEnemyAtkStacks": 1}}}))
        white = HT_ATK + LC21027_ATK

        hand_fua = 0.4 * white * Z * 1.12          # 击杀跨线追击（无层）
        hand_basic2 = 1.0 * white * 1.04 * Z * 1.12  # 1 层攻击 4%
        assert ours == pytest.approx([hand_fua, hand_basic2], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand_basic2, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(white * 1.04, rel=REL_TOL), (
            "对方 ATK_P 0.04 白值换算通道")


class TestLC23020Baptism:
    """纯粹思维的洗礼 S1（真理医生专光）：scoped 暴伤 + 论辩（窗口/FUA 穿透双结构差）."""

    def test_scoped_cd_three_debuffs(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23020"), "imaginary"))
        _inject_debuffs(eng, "e1", 3)
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23020_ATK, cd=RT_CD + 0.2,
            equipment={"light_cone": {
                "id": "23020", "superimposition": 1, "path": "Hunt",
                "conditionals": {"debuffCdStacks": 3, "postUltBuff": False}}}))

        hand = 1.0 * _rt_panel(LC23020_ATK) * 0.5 * 0.9 * (1 + RT_CR * (RT_CD + 0.2 + 0.24))
        assert ours == pytest.approx([hand], rel=REL_TOL), (
            "我方三层 scoped CD（面板 20% + 3 负面 24%）vs 手算")
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_disputation_post_ult_skill(self, optimizer_driver):
        """论辩大招后战技：我方 36% 增伤（on_ultimate 钩）≡ 对方 postUltBuff 全局 BOOST；
        短见=目标 1 件负面 → 两侧各钉 1 层 scoped CD（我方 debuff_count 实数 vs 对方钉 1）."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23020"), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        assert "LC_23020_DISPUTATION" in eng.state.actors["1305"].modifiers
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")   # [大招, 战技, 追击]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "skill", lc_atk=LC23020_ATK, cd=RT_CD + 0.2,
            conditionals={"summationStacks": 0},
            equipment={"light_cone": {
                "id": "23020", "superimposition": 1, "path": "Hunt",
                "conditionals": {"debuffCdStacks": 1, "postUltBuff": True}}}))

        # 战技命中时归纳 0 层（on_action 结算后挂）；短见 1 负面 → scoped CD +8%
        crit = 1 + RT_CR * (RT_CD + 0.2 + 0.08)
        hand = 1.5 * _rt_panel(LC23020_ATK) * 0.5 * 0.9 * crit * 1.36
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方战技段（论辩+短见 1 层 CD）vs 手算"
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_disputation_ult_window(self, optimizer_driver):
        """E2 结构差：论辩覆盖窗口——对方 precompute 当次大招即吃 +36%；
        我方 on_ultimate 钩在伤害结算后（当次不吃）→ 对方恰为 ×1.36."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23020"), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "ult", lc_atk=LC23020_ATK, cd=RT_CD + 0.2,
            equipment={"light_cone": {
                "id": "23020", "superimposition": 1, "path": "Hunt",
                "conditionals": {"debuffCdStacks": 0, "postUltBuff": True}}}))

        hand_ours = 2.4 * _rt_panel(LC23020_ATK) * 0.5 * 0.9 * (1 + RT_CR * (RT_CD + 0.2))
        assert ours == pytest.approx(hand_ours, rel=REL_TOL), "我方当次大招（无论辩）vs 手算"
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.36, rel=REL_TOL)

    def test_disputation_fua_def_pen(self, optimizer_driver):
        """E3 结构差：论辩「追加攻击无视 24% 防御」——我方待收②（scoped def_pen
        通道已在，本件未收编在案）。大招后战技→追击段：双方其余乘区钉全等
        （追击时刻敌方 2 件负面=短见+演绎——hook 序⑬演绎先挂，两侧各钉 2 层
        scoped CD），对方防御区 100/176 vs 我方 0.5 → 恰为 25/22."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23020"), "imaginary"))
        _ult(eng, "1305", "130503", 140.0)
        _cast(eng, "1305", "130502")
        ours_fua = _hit_amounts(log, source="1305")[2]   # [大招, 战技, 追击]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "fua", lc_atk=LC23020_ATK, cd=RT_CD + 0.2,
            conditionals={"summationStacks": 1},
            equipment={"light_cone": {
                "id": "23020", "superimposition": 1, "path": "Hunt",
                "conditionals": {"debuffCdStacks": 2, "postUltBuff": True}}}))

        crit = 1 + (RT_CR + 0.025) * (RT_CD + 0.2 + 0.05 + 0.16)   # 归纳 1 层 + 2 负面 CD
        hand_ours = 2.7 * _rt_panel(LC23020_ATK) * 0.5 * 0.9 * crit * 1.36
        assert ours_fua == pytest.approx(hand_ours, rel=REL_TOL), "我方追击段（无穿透）vs 手算"
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(100 / 176, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours_fua == pytest.approx(25 / 22, rel=REL_TOL)

    def test_path_gate_parity(self, optimizer_driver):
        """命途门控 parity：23020 装黄泉（虚无≠巡猎）——对方 resolver 空控制器 ≡
        我方 hooks 命途门控全灭；白值三围两侧照并（门控只灭机制）."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", lc="23020"), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", atk=AC_ATK + LC23020_ATK,
            equipment={"light_cone": {
                "id": "23020", "superimposition": 1, "path": "Hunt",
                "conditionals": {"debuffCdStacks": 3, "postUltBuff": True}}}))

        hand = 1.0 * (AC_ATK + LC23020_ATK) * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方门控全灭=纯白值面板"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestLC23001InTheNight:
    """于夜色中 S1（真理医生）：速度档增伤（连续 vs 阶梯）+ 终结技 CD 档待收."""

    def test_spd160_full_stacks_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23001"), "imaginary"))
        _inject(eng, "1305", "XC_SPD", {"spd": 160.0 - RT_SPD})
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23001_ATK, cr=RT_CR + 0.18, spd=160.0,
            equipment={"light_cone": {
                "id": "23001", "superimposition": 1, "path": "Hunt",
                "conditionals": {"spdScalingBuffs": True}}}))

        hand = 1.0 * _rt_panel(LC23001_ATK) * 0.5 * 0.9 * (1 + (RT_CR + 0.18) * RT_CD) * 1.36
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 6 档（160 速度）+ CR18% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.36, rel=REL_TOL)

    def test_spd155_continuous_vs_floor(self, optimizer_driver):
        """E4 结构差：速度档——我方连续口径（(spd-100)/10 不去尾，fixture 待实测在案）
        vs 对方 floor 阶梯：SPD 155 → 我方 5.5 档 +33% / 对方 5 档 +30% → 1.30/1.33."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23001"), "imaginary"))
        _inject(eng, "1305", "XC_SPD", {"spd": 155.0 - RT_SPD})
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "basic", lc_atk=LC23001_ATK, cr=RT_CR + 0.18, spd=155.0,
            equipment={"light_cone": {
                "id": "23001", "superimposition": 1, "path": "Hunt",
                "conditionals": {"spdScalingBuffs": True}}}))

        z = 0.5 * 0.9 * (1 + (RT_CR + 0.18) * RT_CD)
        assert ours == pytest.approx(1.0 * _rt_panel(LC23001_ATK) * z * 1.33, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(
            1.0 * _rt_panel(LC23001_ATK) * z * 1.30, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.30 / 1.33, rel=REL_TOL)

    def test_ult_cd_tier(self, optimizer_driver):
        """E5 结构差：终结技 CD 档（6 层 +72%）——我方待收（类型限定 scoped crit_dmg
        通道缺，fixture 在案）→ SPD 160 大招：对方 critMulti 1.427 / 我方 1.175."""
        eng, log = _make_logged(_compiled(
            _member_build("1305", lc="23001"), "imaginary"))
        _inject(eng, "1305", "XC_SPD", {"spd": 160.0 - RT_SPD})
        _ult(eng, "1305", "130503", 140.0)
        ours = _hit_amounts(log, source="1305")[0]
        theirs = run_optimizer(optimizer_driver, _ratio_opt(
            "ult", lc_atk=LC23001_ATK, cr=RT_CR + 0.18, spd=160.0,
            equipment={"light_cone": {
                "id": "23001", "superimposition": 1, "path": "Hunt",
                "conditionals": {"spdScalingBuffs": True}}}))

        hand_ours = 2.4 * _rt_panel(LC23001_ATK) * 0.5 * 0.9 * (1 + (RT_CR + 0.18) * RT_CD)
        assert ours == pytest.approx(hand_ours, rel=REL_TOL), "我方大招（无 CD 档）vs 手算"
        assert theirs["hits"][0]["breakdown"]["critMulti"] == pytest.approx(1.427, rel=REL_TOL)
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.427 / 1.175, rel=REL_TOL)


# ===========================================================================
# 遗器对拍
# ===========================================================================

class TestRelic116Prisoner:
    """系囚 4pc（黄泉）：2pc 攻击面板 + 4pc dot_count scoped 无视防御（④-2 新通道）."""

    def test_2pc_atk(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="116", pieces=4), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "116", "pieces": 4,
                 "conditionals": {"valuePrisonerInDeepConfinement": 0}}]}))

        hand = 1.0 * AC_ATK * 1.12 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 2pc 攻击 12% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(AC_ATK * 1.12, rel=REL_TOL), (
            "对方 p2c ATK_P×白值通道（c→x 差额镜像）")

    def test_4pc_dot_count_def_pen(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="116", pieces=4), "thunder"))
        _inject_debuffs(eng, "e1", 3, mtype="dot")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "116", "pieces": 4,
                 "conditionals": {"valuePrisonerInDeepConfinement": 3}}]}))

        hand = 1.0 * AC_ATK * 1.12 * (100 / 182) * 0.9 * 1.025   # 无视防御 18% → 100/182
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 3 DoT scoped 穿透 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["defMulti"] == pytest.approx(100 / 182, rel=REL_TOL)


class TestRelic117Pioneer:
    """先驱 4pc（黄泉）：2pc 对负面增伤 + 4pc 负面暴伤/翻倍."""

    def test_2pc_boost_and_panel_cr(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="117", pieces=4), "thunder"))
        _clean_knots(eng, wearer="1308")
        _inject_debuffs(eng, "e1", 1)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "117", "pieces": 4,
                 "conditionals": {"valuePioneerDiverOfDeadWaters": 0}}]}))

        hand = 1.0 * AC_ATK * 0.5 * 0.9 * (1 + 0.09 * 0.5) * 1.12   # CR 4% + 增伤 12%
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["cr"] == pytest.approx(0.09, rel=REL_TOL), "对方 p4c CR 通道"

    def test_4pc_cd_ge3(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="117", pieces=4), "thunder"))
        _clean_knots(eng, wearer="1308")
        _inject_debuffs(eng, "e1", 3)
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "117", "pieces": 4,
                 "conditionals": {"valuePioneerDiverOfDeadWaters": 2}}]}))

        hand = 1.0 * AC_ATK * 0.5 * 0.9 * (1 + 0.09 * 0.62) * 1.12   # CD +12%
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方 ≥2/≥3 双件 scoped CD vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_4pc_doubled(self, optimizer_driver):
        """翻倍：我方经引擎施加 1 件负面（after_apply_modifier → 翻倍钩）+ 直写 2 件
        （不触发——隔离对照）；对方钉 value 4（CD 24% + CR 翻倍 4%）."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="117", pieces=4), "thunder"))
        _clean_knots(eng, wearer="1308")
        _inject_debuffs(eng, "e1", 1, source="1308", via_engine=True)
        _inject_debuffs(eng, "e1", 2)
        assert "SET_117_4PC_DOUBLE" in eng.state.actors["1308"].modifiers
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "117", "pieces": 4,
                 "conditionals": {"valuePioneerDiverOfDeadWaters": 4}}]}))

        hand = 1.0 * AC_ATK * 0.5 * 0.9 * (1 + 0.13 * 0.74) * 1.12   # CR 13% CD 74%
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方翻倍三件 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestRelic115Ashblazing:
    """大公（黑塔）：2pc 追击增伤 + 4pc 叠层（模型差钉 E6）."""

    def test_2pc_fua_boost(self, optimizer_driver):
        low = [{"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="115", pieces=2), "ice", enemies=low))
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", equipment={"relic_sets": [
                {"id": "115", "pieces": 2,
                 "conditionals": {"valueTheAshblazingGrandDuke": 0}}]}))

        assert ours == pytest.approx([1.0 * HT_ATK * Z, 0.4 * HT_ATK * Z * 1.2], rel=REL_TOL), (
            "我方普攻 + 追击（2pc +20%）")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.2, rel=REL_TOL)

    @pytest.mark.xfail(
        strict=True,
        reason="真 bug 报回（B-NEW）：引擎 hook 伤害链（hooks.py deal_damage——黑塔/真理医生"
               "天赋追击等全部钩源伤害）只发 on_hp_decrease，不发 after_being_hit（action 层"
               "engine.py:1594 独发）→ 大公 4pc 叠层钩（after_being_hit × follow_up）及一切"
               "follow_up 类 after_being_hit 消费对钩伤害全灭。爆炸半径：约 50 件模板消费"
               "该事件，补 emit 的事件契约（seg_index/hit_targets/链尾时点）需 owner 拍板——"
               "修复后本测试转 XPASS 即激活为正式对拍件")
    def test_4pc_post_fua_basic(self, optimizer_driver):
        """叠层后普攻：我方追击后 1 层（段后挂层）≡ 对方 p4x 钉 1 层 ATK_P 6%.
        【当前被引擎 bug 阻断——见 xfail 标记】"""
        low = [{"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="115", pieces=4), "ice", enemies=low))
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")   # 跨线追击 → 1 层
        assert eng.state.actors["1013"].modifiers["SET_115_ATK_STACK"].stacks == 1
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "basic", equipment={"relic_sets": [
                {"id": "115", "pieces": 4,
                 "conditionals": {"valueTheAshblazingGrandDuke": 1}}]}))

        assert ours[1] == pytest.approx(1.0 * HT_ATK * 1.06 * Z, rel=REL_TOL), (
            "我方 1 层后普攻 vs 手算")
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_4pc_fua_ramp_divergence(self, optimizer_driver):
        """E6 结构差：叠层模型——对方 ashblazingCompute 期望曲线当段即吃（单发 1 敌
        = 6% ATK），我方段后挂层当段不吃（0 层）→ 对方追击段恰为 ×1.06."""
        low = [{"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_compiled(
            _member_build("1013", set_id="115", pieces=4), "ice", enemies=low))
        eng.state.actors["e1"].current_hp = 520.0
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _herta_opt(
            "fua", equipment={"relic_sets": [
                {"id": "115", "pieces": 4,
                 "conditionals": {"valueTheAshblazingGrandDuke": 0}}]}))

        assert ours[1] == pytest.approx(0.4 * HT_ATK * Z * 1.2, rel=REL_TOL), (
            "我方追击段（0 层+2pc 20%）vs 手算")
        assert theirs["hits"][0]["damage"] / ours[1] == pytest.approx(1.06, rel=REL_TOL)


class TestRelic109Band:
    """乐队 4pc（黄泉）：2pc 雷伤面板（元素门控）+ 4pc 战技后攻击（窗口差钉 E7）."""

    def test_2pc_lightning_boost(self, optimizer_driver):
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="109", pieces=2), "thunder"))
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "109", "pieces": 2,
                 "conditionals": {"enabledBandOfSizzlingThunder": True}}]}))

        hand = 1.0 * AC_ATK * Z * 1.1
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方雷伤 10% vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["stats"]["element_boost"] == pytest.approx(0.1, rel=REL_TOL), (
            "对方 p2c 元素段 c→x 通道")

    def test_4pc_post_skill_basic(self, optimizer_driver):
        """战技后行动：我方 4pc 攻击 20% 已挂（on_action 结算后）≡ 对方开关件."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="109", pieces=4), "thunder"))
        _cast(eng, "1308", "130802")
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "basic", equipment={"relic_sets": [
                {"id": "109", "pieces": 4,
                 "conditionals": {"enabledBandOfSizzlingThunder": True}}]}))

        hand = 1.0 * AC_ATK * 1.2 * Z * 1.1
        assert ours[1] == pytest.approx(hand, rel=REL_TOL), "我方战技后普攻（4pc+2pc）vs 手算"
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_4pc_skill_window(self, optimizer_driver):
        """E7 结构差：4pc 覆盖窗口——对方开关无条件（当次战技即吃 +20%）；
        我方 on_action 结算后挂（当次不吃）→ 当次战技对方恰为 ×1.2."""
        eng, log = _make_logged(_compiled(
            _member_build("1308", set_id="109", pieces=4), "thunder"))
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")[0]
        theirs = run_optimizer(optimizer_driver, _acheron_opt(
            "skill", equipment={"relic_sets": [
                {"id": "109", "pieces": 4,
                 "conditionals": {"enabledBandOfSizzlingThunder": True}}]}))

        assert ours == pytest.approx(1.6 * AC_ATK * Z * 1.1, rel=REL_TOL), (
            "我方当次战技（无 4pc）vs 手算")
        assert theirs["hits"][0]["damage"] / ours == pytest.approx(1.2, rel=REL_TOL)
