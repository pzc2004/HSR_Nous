"""L3 装备级对拍·遗器词条波（2026-09-23，BACKLOG B22 扩展④）：driver 场景扩
equipment.relics 词条块（主词条满级值 + 副词条 roll 数 × 高档值，两侧同构——对方
c.a 直喂同值，镜像 calculateRelicStats；我方 build_compiler apply_relics 汇总词条池
→ RELIC_{actor} 初始 modifier 通道，与行迹/套装同通道）后，三个代表性 build 试点：

① 记忆 HP 队（昔涟 1415 带 HP% 遗器——「遗器 HP% 进忆灵生命」链路灯：德谬歌生命
   随遗器 HP% 涨，双方一致；遐蝶 1407 带 HP% 遗器——本人生命倍率段对拍 + 死龙
   34000 常量对照（遗器不动死龙，双方同））；
② 标准输出 build（真理医生 1305 双暴/攻击遗器——面板+伤害双方一致）；
③ 击破 build（流萤 1310 击破特攻遗器——BE 进击破/超击破链）。

统一口径（两侧一致，沿用前几波）：星魂钉死 E0、行迹满级、无光锥、假人 lvl80
def 1000（防御区 0.5）、匹配弱点（抗性区 1.0）、未击破（0.9）、期望暴击。
**词条口径**：attacker.* 钉死面板 = 白值+行迹——**不含套装件/词条**（套装走
relic_sets 原生通道、词条走 equipment.relics → c.a，与我方「词条池经 RELIC 初始
modifier 通道」同构）；面板断言 = 对方 stats/entity_stats 回显 vs 我方
effective_stats，伤害断言 = 逐段 rel_tol 1e-4（双锚=对方+手算）。

===========================================================================
遗器词条 harness 映射表（场景槽 ↔ 两侧通道）
===========================================================================
场景 equipment.relics   对方通道                                  我方通道
{slot}: {main, subs}    calculateRelicStats 镜像——c.a[BasicKey]  build_compiler.apply_relics
  main=词条 id（满级值）  直加（optimizerWorker.ts:251 原序：套装   汇总词条池（flat/pct/dmg_
  subs={id: roll 数}      基础件后、setBasic 前，同容器加算）；     全键）→ RELIC_{actor}
                        pct 键落 *_P 经 c→x 差额镜像按白值换算     初始 modifier（与行迹/套装
                        （差额捕获 caAtk/caHp/... 与 entity 0     同通道，引擎按白值口径
                        共用——忆灵/pet 镜像基数同读）             结算——不烘焙防双重计）
值表 RELIC_AFFIX_MAIN/SUB rulebook relic_affixes 同值镜像            rulebook relic_affixes
（driver 头注「遗器词条口径」） （5★ 满级主词条+高档副词条）        （pipeline StarRailRes 镜像，
                                                                    doc_lint 词条镜像闸看守）
忆灵生命链              忆灵白值 = scaling×(钉死+c.a 差额) + flat  德谬歌 = 白值×(1+HP_P 池)
                        （≡ c.a 终值——transferBaseStats 与         活同步（池 = 行迹+套装+词条
                        calculateMemospriteBaseStats 同读 c.a）     modifier 全源——B-RL① 修复）

===========================================================================
各 build 装备映射表（对方条件开关 ↔ 我方模板 hooks；词条两侧同槽同值）
===========================================================================
① 昔涟 1415（冰，记忆）5 件 pct-only（head flat HP 由 R-RL1 另钉）：
  113 莳者×2（hands+body）  2pc 生命+12%（双方 p2c/套装初始 modifier 同通道）；
                            4pc 受击叠 CR 不装（无受击场双方同 0——valueLongevousDisciple 钉 0）
  302 仙舟×2（sphere+rope） 2pc 生命+12% + spd≥120 全队攻+8%（双方 dyn 件同档——
                            词条 spd 110+25.032=135.032 过线，atk 面板回显互对）
  119 铁骑×1（feet）        单件无套（inert 对照——套装计数两侧各自通道）
  涟漪态（141503 首开）     双方 HP+24%/CR+50%/结界真伤 24%——对方 memoTalent/TRUE_DMG
                            乘区 vs 我方 modifier/追加段（总和比等，R-CY1 收口口径）
①b 遐蝶 1407（量子，记忆）：113×2 + 119/302/303 单件——2pc 生命+12% 唯一套效；
  spdBuff（倒置的火炬 HP≥50% → spd_pct 0.4，满血场双方同挂）对面板无伤害消费。
② 真理医生 1305（虚数，巡猎）：116×2 + 102×2 + 301×2——攻+36% 三 2pc
  （301 spd≥120 档双方同灭：spd 103）；116 4pc dot 穿透不装（valuePrisonerInDeepConfinement
  钉 0 无害——pieces=2 本就不调 p4x）。
③ 流萤 1310（火，毁灭）：119×2 + 118×2（BE+32%）+ 303/304 单件；
  完全燃烧（state_config：spd+60/α BE+0.25）双方同档；BE≥150% 转化 100% 双方同档。

===========================================================================
结构差清单（数值自证见各 divergence 测试——差值恰为标注值，任一侧改动触红）
===========================================================================
R-RL1 德谬歌 flat HP 词条——对方忆灵白值 = scaling×钉死面板（含 flat）vs 我方
   白值×(1+HP_P 池)（flat 无镜像通道——「忆灵白值=忆师白值」KQM 口径不含 flat，
   flat 是否随迁无实测/社区定论，待实测）→ 钉 head flat HP 705.6：
   对方/我方 恰为 1 + 705.6/DEM_HP（昔涟本人面板两侧同含 flat——只差忆灵）。
R-FF1（沿用 test_crosscheck_legacy_1300 在案）：流萤击破场超击破——对方击破易伤
   1.2（我方终结技易伤窗口待收）→ 对方/我方 恰为 1.2。

已修真病两件（本波钓出——单列）：
B-RL① 遗器词条烘焙污染 L1.5 白值基数 + pct 池不可见——apply_relics 旧把词条按
   白值×val/flat 直接烘焙进 stats：① flat 烘焙使引擎 Layer 1.5 的基数
   getattr(st, base_stat) 含 flat → flat × pct cross 项双重计（实证：真理医生
   hands flat 352.8 + atk_pct 池 1.6768——白值+flat 后 ×(1+池) 得 3022.0 vs
   正确 2430.4，虚高 24.4%）；② pct 烘焙同理，且 modifier 池是 pct 池暴露
   （stat_of 读口）唯一通道——烘焙使遗器 HP% 对德谬歌镜像不可见（HEAD 1a1fe5c
   声称已修的「遗器 HP% 进忆灵生命」实证从未真过：昔涟 +43.2% HP% → 德谬歌
   1872.10 纹丝不动）。修复：词条全键（flat/pct/dmg_）改 RELIC_{actor} 初始
   modifier 通道（与行迹/套装同通道，引擎按白值口径结算——单一 pct 源时与烘焙式
   等价，多源时唯一正确）；连带修复 _merge_relic_sets 的
   modifiers_by_actor[actor_id] = mods 赋值抹列（RELIC 词条件先于套装件入列被
   整体覆盖——成套时词条件静默消失，单件时幸存）。
B-RL② driver 忆灵/pet 面板镜像基数只读钉死面板——真实管线 scaling×c.a 终值
   （含套装件/词条），driver 忆灵扩拍时无装备先例写成 scaling×钉死值 → 遗器
   HP% 进忆灵生命对方侧断路（本波试点才会踩到）。修复：镜像挪 c→x 差额后，
   基数 = 钉死+c.a 差额（pet 同改——transferBaseStats SelfAndPet 段同读 c.a 终值）；
   无装备存量场景零行为差（c.a 全 0 时基数=钉死值，逐字节一致）。
B-RL③ 召唤继承读白值漏词条 + 面板视角双计——summon_actor 继承直读
   actor.stats 白值：词条 modifier 通道化后白值不含词条 → 德谬歌 crit 漏遗器
   副词条（0.55/0.873 vs 应 0.6148/1.0026）； naive 改 effective 又双计
   （昔涟天赋 all_dmg 0.2 天赋经 aura 辐射+继承双计成 0.4、长夜 E2 暴伤
   +0.4 经忆灵侧件+继承双计——行迹/星魂件在忆灵侧有专门通道，本就不走继承）。
   修复：_gear_panel = 白值 + 遗器归并件（source_kind="relic" 的 RELIC 词条件+
   套装初始件，剔除 team_scope 光环，_skip_aura），行迹/星魂件不进面板；
   无遗器件时回退白值直读（存量零行为差）。
"""
from __future__ import annotations

import pytest

from hsr_nous.sim.compile import compile_encounter
# 同前几波：driver fixture（缺 node/依赖整模块 skip）+ node 调用 + 引擎件复用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401
from tests.test_crosscheck_characters import (  # noqa: F401
    _POLICY, _cast, _dummy, _hit_amounts, _make_logged, _stage,
)
from tests.template_materialize import TEST_TEMPLATE_ROOTS

# ---------------------------------------------------------------------------
# 词条值（rulebook relic_affixes——driver RELIC_AFFIX_MAIN/SUB 同值镜像；对拍数值闸看守）
# ---------------------------------------------------------------------------

A_MAIN_HP, A_MAIN_ATK, A_MAIN_HP_PCT = 705.6, 352.8, 0.432
A_MAIN_CR, A_MAIN_CD, A_MAIN_BE = 0.324, 0.648, 0.648
A_MAIN_SPD, A_MAIN_ELE = 25.032, 0.388803
A_SUB_CR, A_SUB_CD, A_SUB_BE = 0.0324, 0.0648, 0.0648
A_SUB_HP_PCT = 0.0432


# ---------------------------------------------------------------------------
# 我方侧 build 模子 / 对方侧场景模子
# ---------------------------------------------------------------------------

def _member_build(template: str, relics: dict):
    return {"build": {"team": [
        {"character_template": template, "level": 80, "relics": relics},
    ], "policy": _POLICY}}


def _compiled(build, element: str, enemies=None):
    return compile_encounter(build, _stage(enemies or _dummy("e1", element)),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _fire_ult(eng, owner, aid, *, energy=None, resource=None):
    st = eng.state.actors[owner]
    if energy is not None:
        st.current_energy = energy
    if resource is not None:
        rid, val = resource
        st.resources[rid] = val
    ult = next(a for a in eng.actions_by_actor[owner] if a.action_id == aid)
    assert eng._fire_ultimate(st, ult) is True


def _opt(character_id: str, action: str, element: str, self_path: str, *,
         conditionals: dict, base: dict, attacker: dict,
         equipment: dict | None = None, enemy: dict | None = None):
    sc = {
        "kind": "character", "character_id": character_id, "eidolon": 0,
        "action": action, "element": element, "conditionals": conditionals,
        "base": base, "attacker": attacker, "self_path": self_path,
        "enemy": enemy or {"level": 80, "damage_resistance": 0.0,
                           "weakness_broken": False, "count": 1},
    }
    if equipment:
        sc["equipment"] = equipment
    return sc


def _equipment(relics: dict, sets: list) -> dict:
    """对方装备块：relic_sets 套装归属 + relics 词条（槽位键仅标签，set_id 剥离）."""
    return {
        "relic_sets": sets,
        "relics": {slot: {k: v for k, v in spec.items() if k != "set_id"}
                   for slot, spec in relics.items()},
    }


# ===========================================================================
# ① 记忆 HP 队——昔涟 1415（德谬歌生命随遗器 HP% 涨，双方一致）
# ===========================================================================

CY_W_HP, CY_W_ATK, CY_W_DEF, CY_W_SPD = 1397.088, 446.292, 582.12, 110.0
CY_CR0, CY_CD0 = 0.05, 0.873
CY_TALENT = 1.2                          # 141504 全队增伤 0.2（永续）

# 词条配装（5 件 pct-only——head flat HP 由 R-RL1 另钉）：
CY_RELICS = {
    "slot1": {"set_id": "113", "main": "atk", "subs": {"hp_pct": 2, "crit_rate": 2}},
    "slot2": {"set_id": "113", "main": "hp_pct", "subs": {"crit_dmg": 2}},
    "slot3": {"set_id": "119", "main": "spd"},
    "slot4": {"set_id": "302", "main": "hp_pct", "subs": {"hp_pct": 3}},
    "slot5": {"set_id": "302", "main": "hp_pct"},
}
CY_SETS = [{"id": "113", "pieces": 2, "conditionals": {"valueLongevousDisciple": 0}},
           {"id": "302", "pieces": 2}]
CY_RELIC_PCT = 3 * A_MAIN_HP_PCT + 5 * A_SUB_HP_PCT        # 1.512（三主五副）
CY_POOL_PRE = 0.1 + 0.12 + 0.12 + CY_RELIC_PCT             # 1.852（行迹+113+302+词条）
CY_HP_PRE = CY_W_HP * (1 + CY_POOL_PRE)                    # 涟漪前面板
CY_POOL_RIP = CY_POOL_PRE + 0.24                           # +等待过去双方 HP 24%
CY_HP_RIP = CY_W_HP * (1 + CY_POOL_RIP)                    # 涟漪后面板（德谬歌双方同值）
DEM_HP = CY_HP_RIP
CY_CR = CY_CR0 + 2 * A_SUB_CR                              # 0.1148
CY_CD = CY_CD0 + 2 * A_SUB_CD                              # 1.0026
CY_CR_RIP = CY_CR + 0.5                                    # 涟漪 CR+50%
CY_SPD = CY_W_SPD + A_MAIN_SPD                             # 135.032（302 spd≥120 档过线）
CY_ATK = CY_W_ATK * 1.08 + A_MAIN_ATK                      # 302 档 0.08×白值 + hands flat


def _opt_cyrene(action: str, *, cond: dict | None = None, relics: dict | None = None):
    c = {"buffPriority": 0, "memospriteActive": False, "zoneActive": False,
         "talentDmgBuff": True, "traceSpdBasedBuff": True, "odeToEgoExtraBounces": 0,
         "e1ExtraBounces": 12, "e2TrueDmgStacks": 2, "e4BounceStacks": 24,
         "e6DefPen": True}
    c.update(cond or {})
    return _opt("1415", action, "ice", "Remembrance", conditionals=c,
                base={"atk": CY_W_ATK, "hp": CY_W_HP, "def": CY_W_DEF, "spd": CY_W_SPD},
                attacker={"atk": CY_W_ATK, "hp": CY_W_HP * 1.1, "def": CY_W_DEF,
                          "spd": CY_W_SPD, "cr": CY_CR0, "cd": CY_CD0},
                equipment=_equipment(relics or CY_RELICS, CY_SETS))


def _cy_ripples(eng):
    """追忆钉 24 实打首开 → 涟漪态（德谬歌+双方 CR+50%+双方 HP+24%+结界永续）."""
    cyr = eng.state.actors["1415"]
    eng._gain_resource(cyr, "recollection", 23.0, source_id="ally")
    _cast(eng, "1415", "141501")             # +1 = 24（ally+1415 两源）
    _fire_ult(eng, "1415", "141503")
    assert "1415_dem" in eng.state.actors


class TestCyreneHpBuild:
    """昔涟 HP% 遗器：面板（涟漪前/后）双方互对 + 普攻 + 德谬歌生命链 + Minuet 逐段."""

    def test_panel_pre_ripples(self, optimizer_driver):
        """词条面板全键回显：HP（pct 池全源）/ATK（flat+302 档）/SPD/CR/CD."""
        eng, log = _make_logged(_compiled(_member_build("1415", CY_RELICS), "ice"))
        eff = eng.pipeline.effective_stats(eng.state.actors["1415"])
        assert eff["hp"] == pytest.approx(CY_HP_PRE, rel=REL_TOL)
        assert eff["atk"] == pytest.approx(CY_ATK, rel=REL_TOL)
        assert eff["spd"] == pytest.approx(CY_SPD, rel=REL_TOL)
        assert eff["crit_rate"] == pytest.approx(CY_CR, rel=REL_TOL)
        assert eff["crit_dmg"] == pytest.approx(CY_CD, rel=REL_TOL)

        theirs = run_optimizer(optimizer_driver, _opt_cyrene("basic"))
        st = theirs["stats"]
        assert st["hp"] == pytest.approx(CY_HP_PRE, rel=REL_TOL), "对方 c.a HP_P×白值通道"
        assert st["atk"] == pytest.approx(CY_ATK, rel=REL_TOL), "对方 flat+302 dyn 档"
        assert st["spd"] == pytest.approx(CY_SPD, rel=REL_TOL)
        assert st["cr"] == pytest.approx(CY_CR, rel=REL_TOL)
        assert st["cd"] == pytest.approx(CY_CD, rel=REL_TOL)

    def test_basic_pre_ripples(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1415", CY_RELICS), "ice"))
        _cast(eng, "1415", "141501")
        ours = _hit_amounts(log, source="1415")
        theirs = run_optimizer(optimizer_driver, _opt_cyrene("basic"))

        hand = 0.5 * CY_HP_PRE * 0.5 * 0.9 * (1 + CY_CR * CY_CD) * CY_TALENT
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻（遗器 HP% 进生命倍率）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_demiurge_hp_and_minuet(self, optimizer_driver):
        """涟漪态：德谬歌生命 = 白值×(1+HP_P 池+24%)——遗器 HP% 全进（B-RL① 修复链，
        对方 = scaling×(钉死+c.a 差额)+24%×白值 ≡ 同值）；Minuet 主段+追加段逐段 +
        结界真伤追加 vs 对方聚合 TRUE_DMG 乘区（总和比等，R-CY1 收口口径）."""
        eng, log = _make_logged(_compiled(_member_build("1415", CY_RELICS), "ice"))
        _cy_ripples(eng)
        dem = eng.state.actors["1415_dem"]
        assert eng.pipeline.effective_stats(dem)["hp"] == pytest.approx(DEM_HP, rel=REL_TOL), (
            "我方德谬歌生命（遗器 HP% 进忆灵生命——本波主链路灯）")
        assert eng.pipeline.effective_stats(eng.state.actors["1415"])["hp"] == pytest.approx(
            CY_HP_RIP, rel=REL_TOL)
        log.clear()
        _cast(eng, "1415_dem", "1141501")
        ice = [e["amount"] for e in log if e.get("reason") == "hit"
               and e.get("damage_type") == "ice"]
        true = [e["amount"] for e in log if e.get("reason") == "hit"
                and e.get("damage_type") == "true"]
        theirs = run_optimizer(optimizer_driver, _opt_cyrene(
            "memo_skill", cond={"memospriteActive": True, "zoneActive": True,
                                "odeToEgoExtraBounces": 1}))

        assert theirs["stats"]["hp"] == pytest.approx(CY_HP_RIP, rel=REL_TOL), (
            "对方双方 HP+24%（memoTalent HP_P——忆师白值加算口径）")
        assert theirs["entity_stats"][1]["hp"] == pytest.approx(DEM_HP, rel=REL_TOL), (
            "对方德谬歌生命（scaling×c.a 终值——B-RL② 镜像口径）")
        z = 0.5 * 0.9 * (1 + CY_CR_RIP * CY_CD) * CY_TALENT
        seg = 0.6 * DEM_HP * z
        assert ice == pytest.approx([seg, seg], rel=REL_TOL), (
            "我方主段+1 追加段（unique_sources−1）vs 手算")
        assert true == pytest.approx([0.24 * seg, 0.24 * seg], rel=REL_TOL), (
            "结界真伤追加段 ×0.24")
        assert theirs["hits"][0]["hp_scaling"] == pytest.approx(1.2, rel=REL_TOL), (
            "对方聚合 0.6×(1+1)（odeToEgoExtraBounces=1）")
        assert sum(ice) + sum(true) == pytest.approx(
            theirs["hits"][0]["damage"], rel=REL_TOL), "总和双方互对（段数差在案）"


class TestRelicFlatHpDivergence:
    """R-RL1：德谬歌 flat HP 词条——对方忆灵白值含 flat（scaling×钉死面板）vs 我方
    白值×(1+HP_P 池)（flat 无镜像通道，待实测）→ 恰为 1 + 705.6/DEM_HP."""

    def test_flat_hp_head(self, optimizer_driver):
        relics = dict(CY_RELICS)
        relics["slot0"] = {"set_id": "113", "main": "hp"}   # head flat HP 705.6（第 6 件，113 仍 2pc）
        eng, log = _make_logged(_compiled(_member_build("1415", relics), "ice"))
        _cy_ripples(eng)
        dem = eng.state.actors["1415_dem"]
        ours_dem = eng.pipeline.effective_stats(dem)["hp"]
        assert ours_dem == pytest.approx(DEM_HP, rel=REL_TOL), (
            "我方德谬歌生命不含 flat（白值×(1+HP_P 池)——flat 无镜像通道，待实测）")
        assert eng.pipeline.effective_stats(eng.state.actors["1415"])["hp"] == pytest.approx(
            CY_HP_RIP + A_MAIN_HP, rel=REL_TOL), "昔涟本人面板含 flat（烘焙，双方同）"

        theirs = run_optimizer(optimizer_driver, _opt_cyrene(
            "memo_skill", cond={"memospriteActive": True, "zoneActive": True,
                                "odeToEgoExtraBounces": 1},
            relics=relics))
        theirs_dem = theirs["entity_stats"][1]["hp"]
        assert theirs_dem == pytest.approx(DEM_HP + A_MAIN_HP, rel=REL_TOL), (
            "对方忆灵白值含 flat（scaling×钉死面板——flat 随迁）")
        assert theirs_dem / ours_dem == pytest.approx(
            1 + A_MAIN_HP / DEM_HP, rel=REL_TOL), "R-RL1 结构差恰为 1 + 705.6/DEM_HP"


# ===========================================================================
# ①b 遐蝶 1407（HP% 遗器——本人生命倍率段 + 死龙 34000 常量对照）
# ===========================================================================

CA_W_HP, CA_W_ATK, CA_W_DEF, CA_W_SPD = 1629.936, 523.908, 485.1, 95.0
CA_CR0, CA_CD0, CA_Q = 0.237, 0.633, 0.144
CA_RELICS = {
    "slot1": {"set_id": "113", "main": "atk", "subs": {"hp_pct": 2}},
    "slot2": {"set_id": "113", "main": "hp_pct", "subs": {"crit_rate": 2}},
    "slot3": {"set_id": "119", "main": "def_pct"},
    "slot4": {"set_id": "302", "main": "hp_pct"},
    "slot5": {"set_id": "303", "main": "hp_pct"},
}
CA_SETS = [{"id": "113", "pieces": 2, "conditionals": {"valueLongevousDisciple": 0}}]
CA_RELIC_PCT = 3 * A_MAIN_HP_PCT + 2 * A_SUB_HP_PCT           # 1.3824
CA_POOL = 0.12 + CA_RELIC_PCT                                 # 1.5024（113 2pc 唯一套效）
CA_HP = CA_W_HP * (1 + CA_POOL)
CA_CR = CA_CR0 + 2 * A_SUB_CR                                 # 0.3018
CA_ATK = CA_W_ATK + A_MAIN_ATK                                # 876.708


def _opt_castorice(action: str, *, cond: dict | None = None):
    c = {"buffPriority": 1, "memospriteActive": False, "spdBuff": True,
         "talentDmgStacks": 0, "memoSkillEnhances": 1, "memoTalentHits": 6,
         "teamDmgBoost": False, "memoDmgStacks": 0, "cyreneSpecialEffect": False,
         "e1EnemyHp50": True, "e6Buffs": True}
    c.update(cond or {})
    return _opt("1407", action, "quantum", "Remembrance", conditionals=c,
                base={"atk": CA_W_ATK, "hp": CA_W_HP, "def": CA_W_DEF, "spd": CA_W_SPD},
                attacker={"atk": CA_W_ATK, "hp": CA_W_HP, "def": CA_W_DEF,
                          "spd": CA_W_SPD, "cr": CA_CR0, "cd": CA_CD0,
                          "element_boost": CA_Q},
                equipment=_equipment(CA_RELICS, CA_SETS))


class TestCastoriceHpBuild:
    """遐蝶 HP% 遗器：生命倍率普攻对拍 + 死龙 34000 常量对照（遗器不动死龙）."""

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1407", CA_RELICS), "quantum"))
        _cast(eng, "1407", "140701")
        ours = _hit_amounts(log, source="1407")
        theirs = run_optimizer(optimizer_driver, _opt_castorice("basic"))

        hand = 0.5 * CA_HP * 0.5 * 0.9 * (1 + CA_CR * CA_CD0) * (1 + CA_Q)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻（遗器 HP% 进倍率）vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["stats"]["hp"] == pytest.approx(CA_HP, rel=REL_TOL), (
            "对方面板回显（c.a HP_P×白值通道）")
        assert theirs["stats"]["cr"] == pytest.approx(CA_CR, rel=REL_TOL)

    def test_dragon_hp_control(self, optimizer_driver):
        """死龙 34000 常量（memoBaseHpFlat）——遗器 HP% 不动死龙（对照组，双方同）."""
        eng, log = _make_logged(_compiled(_member_build("1407", CA_RELICS), "quantum"))
        _fire_ult(eng, "1407", "140703", resource=("newbud", 34000.0))
        assert "1407_netherwing" in eng.state.actors
        nw = eng.state.actors["1407_netherwing"]
        assert eng.pipeline.effective_stats(nw)["hp"] == pytest.approx(34000.0, rel=REL_TOL)

        theirs = run_optimizer(optimizer_driver, _opt_castorice("basic"))
        assert theirs["entity_stats"][1]["name"] == "Netherwing"
        assert theirs["entity_stats"][1]["hp"] == pytest.approx(34000.0, rel=REL_TOL), (
            "对方死龙 34000 常量面板（scaling 0×钉死 + flat——忆灵面板镜像闸）")


# ===========================================================================
# ② 标准输出 build——真理医生 1305（双暴/攻击遗器：面板+伤害双方一致）
# ===========================================================================

RT_W_ATK, RT_HP, RT_DEF, RT_SPD = 776.16, 1047.816, 460.845, 103.0
RT_CR0, RT_CD0 = 0.17, 0.5
RT_TRACE_ATK_PCT = 0.28
RT_RELICS = {
    "slot0": {"set_id": "116", "main": "hp"},
    "slot1": {"set_id": "116", "main": "atk", "subs": {"crit_dmg": 2, "atk_pct": 2}},
    "slot2": {"set_id": "102", "main": "crit_dmg", "subs": {"crit_rate": 3}},
    "slot3": {"set_id": "102", "main": "atk_pct", "subs": {"crit_rate": 2}},
    "slot4": {"set_id": "301", "main": "imaginary_dmg", "subs": {"atk_pct": 2}},
    "slot5": {"set_id": "301", "main": "atk_pct"},
}
RT_SETS = [{"id": "116", "pieces": 2, "conditionals": {"valuePrisonerInDeepConfinement": 0}},
           {"id": "102", "pieces": 2},
           {"id": "301", "pieces": 2}]
RT_RELIC_ATK_PCT = 2 * 0.432 + 4 * 0.0432                          # 1.0368（双主四副）
RT_ATK_PCT = RT_TRACE_ATK_PCT + 0.12 * 3 + RT_RELIC_ATK_PCT         # 1.6768（行迹+三 2pc+词条）
RT_ATK = RT_W_ATK * (1 + RT_ATK_PCT) + A_MAIN_ATK                   # 面板（pct×白值+flat）
RT_HP_PANEL = RT_HP + A_MAIN_HP
RT_CR = RT_CR0 + 5 * A_SUB_CR                                       # 0.332
RT_CD = RT_CD0 + A_MAIN_CD + 2 * A_SUB_CD                           # 1.2776
RT_ELE = A_MAIN_ELE


def _opt_ratio(action: str, *, cond: dict | None = None):
    c = {"enemyDebuffStacks": 0, "summationStacks": 0}
    c.update(cond or {})
    return _opt("1305", action, "imaginary", "Hunt", conditionals=c,
                base={"atk": RT_W_ATK, "hp": RT_HP, "def": RT_DEF, "spd": RT_SPD},
                attacker={"atk": RT_W_ATK * 1.28, "hp": RT_HP, "def": RT_DEF,
                          "spd": RT_SPD, "cr": RT_CR0, "cd": RT_CD0},
                equipment=_equipment(RT_RELICS, RT_SETS))


class TestRatioCritBuild:
    """真理医生双暴/攻击遗器：面板五键回显互对 + 普攻/战技/追击/大招逐段."""

    def test_panel_echo(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", RT_RELICS), "imaginary"))
        eff = eng.pipeline.effective_stats(eng.state.actors["1305"])
        assert eff["atk"] == pytest.approx(RT_ATK, rel=REL_TOL)
        assert eff["hp"] == pytest.approx(RT_HP_PANEL, rel=REL_TOL)
        assert eff["crit_rate"] == pytest.approx(RT_CR, rel=REL_TOL)
        assert eff["crit_dmg"] == pytest.approx(RT_CD, rel=REL_TOL)
        assert eff["dmg_bonus"]["imaginary"] == pytest.approx(RT_ELE, rel=REL_TOL)

        theirs = run_optimizer(optimizer_driver, _opt_ratio("basic"))
        st = theirs["stats"]
        assert st["atk"] == pytest.approx(RT_ATK, rel=REL_TOL), "对方 ATK_P×白值+flat 通道"
        assert st["hp"] == pytest.approx(RT_HP_PANEL, rel=REL_TOL)
        assert st["cr"] == pytest.approx(RT_CR, rel=REL_TOL)
        assert st["cd"] == pytest.approx(RT_CD, rel=REL_TOL)
        assert st["element_boost"] == pytest.approx(RT_ELE, rel=REL_TOL)

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", RT_RELICS), "imaginary"))
        _cast(eng, "1305", "130501")
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _opt_ratio("basic"))

        hand = 1.0 * RT_ATK * 0.5 * 0.9 * (1 + RT_CR * RT_CD) * (1 + RT_ELE)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_skill_and_fua(self, optimizer_driver):
        """战技 1.5（归纳 0 层）+ 天赋追击 2.7（归纳 1 层——hook 序⑬先挂后追）."""
        eng, log = _make_logged(_compiled(_member_build("1305", RT_RELICS), "imaginary"))
        _cast(eng, "1305", "130502")
        ours = _hit_amounts(log, source="1305")
        theirs_skill = run_optimizer(optimizer_driver, _opt_ratio("skill"))
        theirs_fua = run_optimizer(optimizer_driver, _opt_ratio(
            "fua", cond={"summationStacks": 1}))

        hand_skill = 1.5 * RT_ATK * 0.5 * 0.9 * (1 + RT_CR * RT_CD) * (1 + RT_ELE)
        crit1 = 1 + (RT_CR + 0.025) * (RT_CD + 0.05)   # 归纳 1 层现场面板
        hand_fua = 2.7 * RT_ATK * 0.5 * 0.9 * crit1 * (1 + RT_ELE)
        assert ours == pytest.approx([hand_skill, hand_fua], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs_skill["hits"][0]["damage"], rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_fua["hits"][0]["damage"], rel=REL_TOL), (
            "追击段双方互对（summationStacks 钉 1 = 战技后现场 1 层）")

    def test_ult(self, optimizer_driver):
        eng, log = _make_logged(_compiled(_member_build("1305", RT_RELICS), "imaginary"))
        _fire_ult(eng, "1305", "130503", energy=140.0)
        ours = _hit_amounts(log, source="1305")
        theirs = run_optimizer(optimizer_driver, _opt_ratio("ult"))

        hand = 2.4 * RT_ATK * 0.5 * 0.9 * (1 + RT_CR * RT_CD) * (1 + RT_ELE)
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


# ===========================================================================
# ③ 击破 build——流萤 1310（击破特攻遗器：BE 进击破/超击破链）
# ===========================================================================

FF_W_ATK, FF_HP, FF_DEF, FF_SPD = 523.908, 814.968, 776.16, 109.0
FF_BE0 = 0.373
FF_RELICS = {
    "slot0": {"set_id": "119", "main": "hp"},
    "slot1": {"set_id": "119", "main": "atk", "subs": {"break_effect": 2}},
    "slot2": {"set_id": "118", "main": "atk_pct", "subs": {"break_effect": 2}},
    "slot3": {"set_id": "118", "main": "def_pct", "subs": {"break_effect": 2}},
    "slot4": {"set_id": "303", "main": "fire_dmg"},
    "slot5": {"set_id": "304", "main": "break_effect", "subs": {"break_effect": 2}},
}
FF_SETS = [{"id": "119", "pieces": 2}, {"id": "118", "pieces": 2}]
FF_RELIC_BE = 2 * 0.16 + A_MAIN_BE + 8 * A_SUB_BE       # 1.4864（双 2pc+绳主+八副）
FF_BE = FF_BE0 + FF_RELIC_BE                            # 1.8594（基础面板）
FF_BE_COMB = FF_BE + 0.25                               # 2.1094（完全燃烧 α+25%）
FF_ATK = FF_W_ATK * (1 + 0.432) + A_MAIN_ATK            # 1103.036（body 主 atk_pct+hands flat）
FF_ELE = A_MAIN_ELE
FF_CZ = 1 + 0.05 * 0.5                                  # 1.025


def _opt_firefly(action: str, *, cond: dict | None = None, be: float = FF_BE0):
    c = {"enhancedStateActive": False, "enhancedStateSpdBuff": True,
         "superBreakDmg": False, "atkToBeConversion": True,
         "talentDmgReductionBuff": True, "e1DefShred": True, "e4ResBuff": True,
         "e6Buffs": True}
    c.update(cond or {})
    return _opt("1310b1", action, "fire", "Destruction", conditionals=c,
                base={"atk": FF_W_ATK, "hp": FF_HP, "def": FF_DEF, "spd": FF_SPD},
                attacker={"atk": FF_W_ATK, "hp": FF_HP, "def": FF_DEF, "spd": FF_SPD,
                          "cr": 0.05, "cd": 0.5, "be": be},
                equipment=_equipment(FF_RELICS, FF_SETS))


def _enter_combustion(eng):
    """终结技进完全燃烧（state_config：spd+60/效率+0.5/α BE+0.25/强化替换）."""
    st = eng.state.actors["1310"]
    _fire_ult(eng, "1310", "1131003", energy=240.0)
    assert st.state_config is not None, "进完全燃烧"


class TestFireflyBreakBuild:
    """流萤击破特攻遗器：BE 面板回显 + 强化战技 BE 转换段 + 击破/超击破链."""

    def test_basic_and_be_panel(self, optimizer_driver):
        """普攻 1.0 火（燃烧外）+ BE 面板 1.8594 双方同值（遗器 BE 全渠道：行迹+双 2pc+
        绳主+八副——flat 通道两侧各自 modifier/c.a）."""
        eng, log = _make_logged(_compiled(_member_build("1310", FF_RELICS), "fire"))
        _cast(eng, "1310", "1131001")
        ours = _hit_amounts(log, source="1310")
        theirs = run_optimizer(optimizer_driver, _opt_firefly("basic"))

        assert eng.pipeline.effective_stats(eng.state.actors["1310"])["break_effect"] == (
            pytest.approx(FF_BE, rel=REL_TOL))
        assert theirs["stats"]["be"] == pytest.approx(FF_BE, rel=REL_TOL), (
            "对方 BE 面板回显（c.a BE 直加通道）")
        hand = 1.0 * FF_ATK * 0.5 * 0.9 * FF_CZ * (1 + FF_ELE)
        assert ours == pytest.approx([hand], rel=REL_TOL), "我方普攻 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"

    def test_combustion_skill_be_conversion(self, optimizer_driver):
        """完全燃烧强化战技：主 2.0 + BE 转换段 0.2×min(BE,3.6)=0.39596 双段 vs 对方
        折叠 2.42188 单发（段数差在案总和互对）；BE 2.1094/spd 169 面板双方同值."""
        eng, log = _make_logged(_compiled(_member_build("1310", FF_RELICS), "fire"))
        _enter_combustion(eng)
        log.clear()
        _cast(eng, "1310", "1131009")
        ours = _hit_amounts(log, source="1310")
        theirs = run_optimizer(optimizer_driver, _opt_firefly(
            "skill", cond={"enhancedStateActive": True}))

        assert theirs["stats"]["be"] == pytest.approx(FF_BE_COMB, rel=REL_TOL), (
            "对方 α BE 面板回显")
        assert theirs["stats"]["spd"] == pytest.approx(169.0, rel=REL_TOL)
        z = 0.5 * 0.9 * FF_CZ * (1 + FF_ELE)
        assert ours == pytest.approx(
            [2.0 * FF_ATK * z, 0.2 * FF_BE_COMB * FF_ATK * z], rel=REL_TOL), (
            "我方主段+BE 转换段（对方折叠单发——段数差在案）vs 手算")
        assert sum(ours) == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "总和双方互对")

    def test_super_break_r_ff1(self, optimizer_driver):
        """击破场超击破（R-FF1 沿用）：舞台韧性 100 档，燃烧内首发即破（45 削韧）——
        火击破/超击破手算（BE 2.1094 双方同档）+ 对方超击破 ×1.2 结构差钉 R-FF1."""
        eng, log = _make_logged(_compiled(_member_build("1310", FF_RELICS), "fire",
                                          enemies=[{"actor_id": "e1", "name": "假人",
                                                    "hp": 1e9, "spd": 100, "atk": 1000,
                                                    "def": 1000, "max_toughness": 100,
                                                    "weakness": ["physical"]}]))
        _enter_combustion(eng)
        e1 = eng.state.actors["e1"]
        e1.toughness = 15.0
        log.clear()
        _cast(eng, "1310", "1131009")                # 植弱+45 削韧首发即破
        assert e1.broken, "强战 30×1.5=45 ≥15 首发即破（B-FF③ 削韧勘正）"
        _cast(eng, "1310", "1131009")                # 已击破 → 超击破
        hits = [e["amount"] for e in log
                if e.get("reason") == "hit" and e.get("source") == "1310"]
        breaks = [e["amount"] for e in log
                  if e.get("reason") == "break" and e.get("source") == "1310"]
        theirs = run_optimizer(optimizer_driver, _opt_firefly(
            "skill", cond={"enhancedStateActive": True, "superBreakDmg": True}))

        z1 = 0.5 * 1.0 * FF_CZ * (1 + FF_ELE)        # 已击破韧性区 1.0
        assert hits == pytest.approx(
            [2.0 * FF_ATK * 0.5 * 0.9 * FF_CZ * (1 + FF_ELE),
             0.2 * FF_BE_COMB * FF_ATK * z1,
             2.0 * FF_ATK * z1, 0.2 * FF_BE_COMB * FF_ATK * z1], rel=REL_TOL), (
            "两发四段（首发主段 0.9 当次击破、BE 转换段 hook 序在击破后读 1.0；"
            "二发全 1.0——legacy R-FF1 同序）vs 手算")
        brk_hand = 3767.5533 * 2.0 * (0.5 + 100 / 40) * (1 + FF_BE_COMB) * 0.5
        assert breaks[0] == pytest.approx(brk_hand, rel=REL_TOL), (
            "火击破（满韧 100 档——对方 BREAK 行动独立注册本场无落点）vs 手算")
        sb_hand = 376.75533 * (30 * 1.5) * (1 + FF_BE_COMB) * 0.5 * 1.0
        assert breaks[1] == pytest.approx(sb_hand, rel=REL_TOL), (
            "我方超击破段（有效削韧 45；转化 100%——BE 2.1094≥150% 双方同档）vs 手算")
        assert len(theirs["hits"]) == 2, "对方直伤+超击破双发"
        assert theirs["hits"][0]["damage"] == pytest.approx(
            (2.0 + 0.2 * FF_BE_COMB) * FF_ATK * z1, rel=REL_TOL), "对方折叠直伤 vs 手算"
        sb_theirs = theirs["hits"][1]
        assert sb_theirs["breakdown"]["vulnMulti"] == pytest.approx(1.2, rel=REL_TOL), (
            "对方击破易伤 1.2（我方终结技易伤窗口待收——R-FF1 在案）")
        assert sb_theirs["damage"] / breaks[1] == pytest.approx(1.2, rel=REL_TOL), (
            "R-FF1 结构差恰为 1.2")
