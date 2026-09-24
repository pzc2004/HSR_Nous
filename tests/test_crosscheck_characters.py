"""L2 角色级对拍（BACKLOG B22 扩展）：同角色、同面板、同钉死 buff 状态、同假人下，
我方引擎逐技能逐段伤害 == hsr-optimizer 角色实现整链伤害（rel_tol 1e-4）。

裁判路径：`scripts/crosscheck/crosscheck.mts` kind="character"（驱动头注有完整口径）——
对方 actionDefinition 取 hits → precomputeEffects/MutualEffects 条件 buff → 钉死面板
→ ATK_P 白值换算（镜像 applyPercentStats）→ finalizeCalculations → 逐 hit 伤害函数。
我方路径：真模板 YAML（tests/fixtures 人工根优先于 data/ 生成根）→ 编译 → CombatEngine
钉资源/血量 → _cast/_fire_ultimate → bus.subscribe("on_hp_decrease") 收逐段事件
（amount = 乘区结算后扣血值，源/目标/类别齐全）。

统一口径（两侧一致）：星魂按需钉死、无光锥、双方均不装遗器（对方 x.c 空 sets →
ashblazing finalizer 自然 no-op）、行迹满级（普攻 lv6 / 战技·终结技·天赋 lv10，
E3/E5 场随档）；假人 lvl80、def 1000（防御区 0.5 ≡ 对方 100/((80+20)+100)）、
匹配弱点（抗性区 1.0）、未击破（韧性减伤区 0.9）、期望暴击（1+cr·cd = 1.025）。

===========================================================================
黑塔 1013 buff 状态映射表（对方条件开关 ↔ 我方模板触发条件）
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
fuaStacks 1-5（5）             天赋跨线触发次数（单发 0.4×ATK 全体）          钉 1 = 单次触发比等
techniqueBuff（false）         秘技 TECH_ATK_BUFF（战前装填 ATK+40% 3回合）   各走通道后 basic 比等
targetFrozen（true）           行迹 Icing 终结技对冻结 +20%——**已收编（2026-09-23，
                               命中域 target_control_kinds）**                 钉 false/true 均三方比等
enemyHpGte50（true）           战技 HP≥50% +20% + 行迹 Efficiency +25%——**已收编
                               （2026-09-23，命中域 target_hp_ratio）**         钉 false/true 均三方比等
enemyHpLte50（false，E1）      E1 普攻对 ≤50% 目标追加 0.4×ATK                E0 关闭不出
e2TalentCritStacks 0-5（5，E2）E2 跨线计数层 ×3% CR                          E6 场钉 0（不触发 FUA）
e6UltAtkBuff（true，E6）       E6 大招后 ATK+25% 1 回合                       大招后普攻比等；
                                                                            当次大招钉 ×1.25 结构差
                                                                            （对方窗口覆盖当次=建模近似）

===========================================================================
黄泉 1308 buff 状态映射表
===========================================================================
对方 content id（默认）        我方模板对应                                   对拍处置
crimsonKnotStacks 0-9（9）     目标 CRIMSON_KNOT 层数（结爆 min(0.15(1+n),0.6)
                               /雨斩段，n=min(3,现场层数)）                   钉 9——消耗粒度对齐点
                                                                            （3 段各摘 3，双方 1.8 全等；
                                                                            非 3 倍数层双方摘法不同=已知建模差）
thunderCoreStacks 0-3（3）     行迹 3 前半（雨斩命中带结敌 +30%/层）——**已收编    预钉 3 层（上一大招遗留态）比等；
                               （2026-09-23，TRACE_TC/TRACE_TC_DMG 双件）    0 层实打渐进段我方 vs 手算单钉
stygianResurgeHitsOnTarget（6）Thunder Core 6 段（on_ultimate 钩 0.25×6）    钉 6 比等
nihilityTeammatesBuff（true）  行迹 2 The Abyss：我方 dmg_final_dmg_boost        3 虚无队双方同池比等
                               0.15/0.6（D7 已转正 2026-09-23）
                               vs 对方 FINAL_DMG ×1.15/×1.6 乘算
e1EnemyDebuffed（true，E1）    E1 对 debuff 敌 CR+18%——**待收**               钉 false
e4UltVulnerability（true，E4） E4_ULT_VULN（actor_enter 挂件 + ult 限定）    E4 场比等（含 lv12 随档）
（无开关）天赋大招期间 RES_PEN 20%  大招期间敌方抗性 -20%——**已收编（2026-09-23， 不再注入，大招 13 段总和比等；
                               ULT_RES_SHRED 常驻件 hit_condition ultimate）

结构差清单（数值自证见各 divergence 测试——差值恰为标注倍数，任一侧改动触红）：
~~D1 黑塔战技 HP≥50% 增伤 20%+行迹 25%~~ **已收官（2026-09-23，命中域
   target_hp_ratio——满血场三方全等 1.45）**
~~D2 黑塔行迹 Icing 冻结增伤 20%~~ **已收官（2026-09-23，命中域
   target_control_kinds——冻结场三方全等 1.2）**
D3 黑塔 E6 ATK+25% 覆盖窗口（对方含当次大招=建模近似）→ 当次大招 1.25
~~D4 黄泉天赋大招 RES_PEN 20%~~ **已收官（2026-09-23，ULT_RES_SHRED 常驻件
   hit_condition ultimate——大招 13 段总和三方全等 1.2×1.6×1.9）**
~~D5 黄泉行迹 3 前半雨斩增伤 30%×3~~ **已收官（2026-09-23，TRACE_TC 双件——
   预钉 3 层三方全等 1.9；0 层实打渐进段 ×1.0/1.3/1.6/1.9 我方 vs 手算单钉）**
D6 黄泉战技 blast 相邻段（对方只建主目标单发=建模收敛）→ 主线全等，相邻 0.6×2 手算自证
~~D7 黄泉 The Abyss 加算 vs 乘算~~ **已收官（2026-09-23——「提高至原伤害」=
   终伤乘算，归 dmg_final_dmg_boost 桶 ≡ 对方 FINAL_DMG_BOOST；行迹 3 增伤
   入池后仍全等，原「空池等价非空池分叉」注消解）**
"""
from __future__ import annotations

import math

import pytest

from hsr_nous.sim.compile import compile_encounter
from hsr_nous.sim.engine import CombatEngine
from hsr_nous.sim.pipeline import MODE_EXPECTED
from hsr_nous.sim.state import Modifier
from tests.template_materialize import TEST_TEMPLATE_ROOTS
# B22 公式层对拍件的复用：同一 driver fixture（缺 node/依赖整模块 skip）+ 同一 node 调用
from tests.test_crosscheck_optimizer import REL_TOL, optimizer_driver, run_optimizer  # noqa: F401

# ---------------------------------------------------------------------------
# 口径常数（两侧钉死）
# ---------------------------------------------------------------------------

HT_ATK = 582.12           # 黑塔白值（人工 fixture 模板终审值）
AC_ATK = 698.544          # 黄泉白值
Z = 0.5 * 0.9 * 1.025     # 防御区 0.5 × 未击破 0.9 × 期望暴击 1.025（抗性区 1.0）


def _assert_panel(theirs, *, atk, cr=0.05, cd=0.5, element_boost=0.0):
    """面板回显闸：对方容器读回值 == 钉死值（钉错面板/行迹平铺第一现场）."""
    st = theirs["stats"]
    assert math.isclose(st["atk"], atk, rel_tol=REL_TOL), f"面板 atk {st['atk']} != {atk}"
    assert math.isclose(st["cr"], cr, rel_tol=REL_TOL), f"面板 cr {st['cr']} != {cr}"
    assert math.isclose(st["cd"], cd, rel_tol=REL_TOL), f"面板 cd {st['cd']} != {cd}"
    assert math.isclose(st["element_boost"], element_boost, rel_tol=REL_TOL), \
        f"面板属性增伤 {st['element_boost']} != {element_boost}"


# ---------------------------------------------------------------------------
# 我方侧引擎件（e2e 先例同形：tests/test_herta_template_e2e.py /
# tests/test_accheron_template_e2e.py 的 _cast/_ult 模式）
# ---------------------------------------------------------------------------

def _cast(eng, owner, aid, *, target="e1"):
    st = eng.state.actors[owner]
    a = next(x for x in eng.actions_by_actor[owner] if x.action_id == aid)
    tgt = eng.state.actors[target]
    eng.decision.select_target = lambda actor_state, action_type, candidates, engine: (
        tgt if tgt in candidates else (candidates[0] if candidates else None))
    eng._execute_action(st, a)
    eng.bus.emit("on_action", {
        "actor": owner, "action_type": a.action_type, "action_id": aid,
        "target_type": a.target_type, "target": tgt.actor.actor_id,
        "sp_consumed": eng._last_sp_consumed,
        "actor_type": st.actor.actor_type}, eng.state)


def _events(eng):
    """逐段伤害记录仪：on_hp_decrease 有序事件流（amount=结算后扣血值）."""
    log = []
    eng.bus.subscribe("on_hp_decrease", lambda et, payload, ctx: log.append(dict(payload)))
    return log


def _make_logged(compiled):
    """引擎 + 时间序伤害日志：setup **前**订阅（登记序先于 hook 引擎——嵌套伤害
    （结爆/追击族由 hook 在外层命中事件内联发）按"因先于果"落地；setup 后订阅会
    因果倒序（hook 先跑、记录仪后收外层事件），逐段比对必须用本件）."""
    eng = CombatEngine.from_compiled(compiled, mode=MODE_EXPECTED, initial_energy_ratio=0.0)
    log = _events(eng)
    eng.setup()
    return eng, log


def _hit_amounts(log, *, source, target="e1"):
    return [e["amount"] for e in log
            if e.get("reason") == "hit" and e.get("source") == source
            and e.get("target") == target]


def _dummy(aid, element, *, hp=1e9, n=1):
    return [{"actor_id": f"e{i+1}" if n > 1 else aid, "name": f"假人{i+1}", "hp": hp,
             "spd": 100, "atk": 1000, "def": 1000, "max_toughness": 9999,
             "weakness": [element]} for i in range(n)]


def _stage(enemies):
    return {"stage": {"stage_id": "s", "enemies": enemies,
                      "termination": {"mode": "fixed_av", "max_action_value": 1500}}}


_POLICY = {"name": "p", "action_rules": [
    {"condition": "true", "action": "skill", "priority": 50},
    {"condition": "true", "action": "basic", "priority": 0}]}


# ---------------------------------------------------------------------------
# 黑塔 1013（对方 1000/Herta.ts 441 行全实现）
# ---------------------------------------------------------------------------

def _herta_build(*, eidolon: int = 0, pre_battle: bool = False):
    member = {"character_template": "1013", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    build = {"build": {"team": [member], "policy": _POLICY}}
    if pre_battle:
        build["build"]["pre_battle"] = [{"actor_id": "1013", "technique": "101307"}]
    return build


def _herta_compiled(*, eidolon: int = 0, pre_battle: bool = False, enemies=None):
    return compile_encounter(_herta_build(eidolon=eidolon, pre_battle=pre_battle),
                             _stage(enemies or _dummy("e1", "ice")),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _herta_ult(eng):
    st = eng.state.actors["1013"]
    st.current_energy = 110.0
    ult = next(a for a in eng.actions_by_actor["1013"] if a.action_id == "101303")
    assert eng._fire_ultimate(st, ult) is True


def _opt_herta(action: str, *, eidolon: int = 0, conditionals: dict | None = None):
    """对方黑塔场景：E0 全开关中性钉死（映射表见模块 docstring），按需覆盖."""
    cond = {"fuaStacks": 1, "techniqueBuff": False, "targetFrozen": False,
            "enemyHpGte50": False, "enemyHpLte50": False,
            "e2TalentCritStacks": 0, "e6UltAtkBuff": True}
    cond.update(conditionals or {})
    return {
        "kind": "character", "character_id": "1013", "eidolon": eidolon,
        "action": action, "element": "ice", "conditionals": cond,
        "base": {"atk": HT_ATK, "hp": 952.56, "def": 396.9, "spd": 100},
        "attacker": {"atk": HT_ATK, "hp": 952.56, "def": 396.9, "spd": 100,
                     "cr": 0.05, "cd": 0.5},
        "self_path": "Erudition",
        "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                  "count": 1},
    }


class TestHertaDuipai:
    """黑塔 E0 全技能逐段对拍：basic/skill/ult/FUA/秘技 五路全等（双锚：对方 + 手算）."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_herta("basic"))
        _assert_panel(theirs, atk=HT_ATK)

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_herta_compiled())
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _opt_herta("basic"))

        assert ours == pytest.approx([1.0 * HT_ATK * Z], rel=REL_TOL), "我方普攻单段 vs 手算"
        assert theirs["hits"][0]["damage"] == pytest.approx(1.0 * HT_ATK * Z, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("resMulti", 1.0), ("baseUniversalMulti", 0.9),
                     ("critMulti", 1.025), ("abilityMulti", HT_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"

    def test_skill(self, optimizer_driver):
        """战技 AoE 1.0（lv10）：enemyHpGte50 钉 false——假人打残（≤50%）使我方
        HP 条件增伤件不触发（D1 收编后本件由条件承载，不再是无条件缺失）."""
        eng, log = _make_logged(_herta_compiled())
        eng.state.actors["e1"].current_hp = 0.4 * eng.pipeline.effective_stats(
            eng.state.actors["e1"])["hp"]
        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _opt_herta("skill"))

        assert ours == pytest.approx([1.0 * HT_ATK * Z], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(1.0 * HT_ATK * Z, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.0, rel=REL_TOL), (
            "中性开关下增伤池空——双方同构")

    def test_ult(self, optimizer_driver):
        """终结技 AoE 2.0（lv10）：targetFrozen 钉 false（Icing 待收——divergence 另测）."""
        eng, log = _make_logged(_herta_compiled())
        _herta_ult(eng)
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _opt_herta("ult"))

        assert ours == pytest.approx([2.0 * HT_ATK * Z], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(2.0 * HT_ATK * Z, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_fua_cross_line(self, optimizer_driver):
        """天赋跨线追击：命中前 >50% → 命中后 ≤50% → 全体 0.4×ATK（lv10）——
        对方 fuaStacks 钉 1 = 单次触发单敌命中."""
        low = [{"actor_id": "e1", "name": "假人", "hp": 1000.0, "spd": 100, "atk": 1000,
                "def": 1000, "max_toughness": 9999, "weakness": ["ice"]}]
        eng, log = _make_logged(_herta_compiled(enemies=low))
        eng.state.actors["e1"].current_hp = 520.0   # >50%×1000；吃 268.5 后 ≤50% 跨线
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver, _opt_herta("fua"))

        assert ours == pytest.approx([1.0 * HT_ATK * Z, 0.4 * HT_ATK * Z], rel=REL_TOL), (
            "我方两段：普攻 + 天赋追加（跨线触发）")
        assert theirs["hits"][0]["damage"] == pytest.approx(0.4 * HT_ATK * Z, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "追加段双方互对（fuaStacks=1 ≡ 单次触发）")

    def test_technique_atk_buff(self, optimizer_driver):
        """秘技战前装填 ATK+40%：我方 TECH_ATK_BUFF（atk_pct 0.4）vs 对方 ATK_P 0.4
        ×白值换算——两条 ATK 通道的交叉验证."""
        eng, log = _make_logged(_herta_compiled(pre_battle=True))
        assert math.isclose(
            eng.pipeline.effective_stats(eng.state.actors["1013"])["atk"], HT_ATK * 1.4,
            rel_tol=1e-9), "我方秘技通道面板"
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs = run_optimizer(optimizer_driver,
                               _opt_herta("basic", conditionals={"techniqueBuff": True}))

        hand = 1.0 * HT_ATK * 1.4 * Z
        assert ours == pytest.approx([hand], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL)
        assert theirs["stats"]["atk"] == pytest.approx(HT_ATK * 1.4, rel=REL_TOL), (
            "对方 ATK_P 0.4 白值换算通道")
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)


class TestHertaKnownDivergence:
    """黑塔结构差三件（映射表 D1/D2/D3）：D1/D2 已收官转三方比等（2026-09-23），
    D3 维持差值钉（对方建模近似）."""

    def test_skill_hp_gte50_boost(self, optimizer_driver):
        """D1 已收官（2026-09-23）：战技 HP≥50% 增伤 20% + 行迹 Efficiency +25%——
        命中域 target_hp_ratio 键落地，常驻 hit_condition 件承载——满血假人双方
        增伤池同 1.45，三方全等."""
        eng, log = _make_logged(_herta_compiled())
        _cast(eng, "1013", "101302")
        ours = _hit_amounts(log, source="1013")[0]
        theirs = run_optimizer(optimizer_driver,
                               _opt_herta("skill", conditionals={"enemyHpGte50": True}))

        hand = 1.0 * HT_ATK * Z * 1.45
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方满血场 vs 手算（1.45 池）"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.45, rel=REL_TOL)

    def test_ult_frozen_boost(self, optimizer_driver):
        """D2 已收官（2026-09-23）：行迹 Icing 终结技对冻结 +20%——命中域
        target_control_kinds 列表落地（可分冻结/禁锢/纠缠），冻结假人双方增伤池
        同 1.2，三方全等."""
        eng, log = _make_logged(_herta_compiled())
        eng._apply_modifier(eng.state.actors["e1"], Modifier(
            modifier_id="TEST_FREEZE", name="对拍冻结", modifier_type="debuff",
            duration=0, dispellable=False, control_kind="freeze"))
        _herta_ult(eng)
        ours = _hit_amounts(log, source="1013")[0]
        theirs = run_optimizer(optimizer_driver,
                               _opt_herta("ult", conditionals={"targetFrozen": True}))

        hand = 2.0 * HT_ATK * Z * 1.2
        assert ours == pytest.approx(hand, rel=REL_TOL), "我方冻结场 vs 手算（1.2 池）"
        assert theirs["hits"][0]["damage"] == pytest.approx(hand, rel=REL_TOL), "对方 vs 手算"
        assert ours == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.2, rel=REL_TOL)

    def test_e6_window(self, optimizer_driver):
        """D3：E6 大招后 ATK+25% 1 回合——我方 on_ultimate 钩不覆盖当次大招；
        对方 e6UltAtkBuff 是无条件 precompute 件（含当次大招=建模近似）。
        大招后普攻（E3 lv7=1.1）：双方全等；当次大招（E5 lv12=2.16）：对方恰为 ×1.25."""
        eng, log = _make_logged(_herta_compiled(eidolon=6))
        _herta_ult(eng)
        _cast(eng, "1013", "101301")
        ours = _hit_amounts(log, source="1013")
        theirs_ult = run_optimizer(optimizer_driver, _opt_herta("ult", eidolon=6))
        theirs_basic = run_optimizer(optimizer_driver, _opt_herta("basic", eidolon=6))

        # 大招后普攻：我方 E6_ATK_UP 生效 ≡ 对方常开件——全等（含 E3 随档 1.1）
        hand_basic = 1.1 * HT_ATK * 1.25 * Z
        assert ours[1] == pytest.approx(hand_basic, rel=REL_TOL), "我方大招后普攻 vs 手算"
        assert theirs_basic["hits"][0]["damage"] == pytest.approx(hand_basic, rel=REL_TOL)
        assert ours[1] == pytest.approx(theirs_basic["hits"][0]["damage"], rel=REL_TOL)
        assert theirs_basic["stats"]["atk"] == pytest.approx(HT_ATK * 1.25, rel=REL_TOL)
        # 当次大招：我方无 E6 覆盖（2.16 lv12），对方含 25% → 恰为 ×1.25
        assert ours[0] == pytest.approx(2.16 * HT_ATK * Z, rel=REL_TOL), "我方当次大招 vs 手算"
        assert theirs_ult["hits"][0]["damage"] / ours[0] == pytest.approx(1.25, rel=REL_TOL)


# ---------------------------------------------------------------------------
# 黄泉 1308（对方 1300/Acheron.ts 452 行全实现）
# ---------------------------------------------------------------------------

def _acheron_build(*, eidolon: int = 0, extra_nihility: int = 0):
    member = {"character_template": "1308", "level": 80}
    if eidolon:
        member["eidolon"] = eidolon
    team = [member]
    for i in range(extra_nihility):
        team.append({"actor_id": f"nih{i}", "name": f"虚无{i}", "inline": True,
                     "path": "nihility",
                     "base_stats": {"atk": 1000, "spd": 90, "hp": 3000, "max_energy": 100},
                     "actions": [{"action_id": f"nih{i}_basic", "name": "普攻",
                                  "action_type": "basic", "target_type": "single",
                                  "damage_type": "ice", "scaling": [{"atk": 1.0}],
                                  "toughness_dmg": 10}]})
    return {"build": {"team": team, "policy": _POLICY}}


def _acheron_compiled(*, eidolon: int = 0, extra_nihility: int = 0, enemies=None):
    return compile_encounter(_acheron_build(eidolon=eidolon, extra_nihility=extra_nihility),
                             _stage(enemies or _dummy("e1", "thunder")),
                             template_roots=TEST_TEMPLATE_ROOTS)


def _acheron_ult(eng):
    st = eng.state.actors["1308"]
    st.resources["slashed_dream"] = 9.0
    ult = next(a for a in eng.actions_by_actor["1308"] if a.action_id == "130803")
    assert eng._fire_ultimate(st, ult) is True


def _knots(eng, aid, stacks):
    eng._apply_modifier(eng.state.actors[aid], Modifier(
        modifier_id="CRIMSON_KNOT", name="绯红结", modifier_type="debuff",
        stacks=stacks, max_stack=9, duration=0, dispellable=False))


def _pin_trace_tc(eng, stacks):
    """行迹 3 雨斩增伤双件钉层（真实 modifier 件——TRACE_TC 计数 + TRACE_TC_DMG
    烘焙值件 0.3×min(stacks,3)；模拟「上一大招遗留 3 层」在局态，对方
    thunderCoreStacks=N  slider 同义）."""
    st = eng.state.actors["1308"]
    eng._apply_modifier(st, Modifier(
        modifier_id="TRACE_TC", name="Thunder Core·计数", modifier_type="buff",
        stacks=stacks, max_stack=3, duration=3, dispellable=False))
    eng._apply_modifier(st, Modifier(
        modifier_id="TRACE_TC_DMG", name="Thunder Core", modifier_type="buff",
        duration=3, dispellable=False,
        stat_effects={"all_dmg": 0.3 * min(stacks, 3)}))


def _inject(eng, actor_id, modifier_id, stat_effects):
    """对拍注入件：把双方都已知的我方待收项以 modifier 等价挂上（隔离其余全链——
    注入后全等 ⇒ 差值恰来自该待收项；不注入 ⇒ 钉 divergence 倍数）."""
    st = eng.state.actors[actor_id]
    st.modifiers[modifier_id] = Modifier(
        modifier_id=modifier_id, name=f"对拍注入·{modifier_id}", modifier_type="buff",
        duration=0, dispellable=False, stat_effects=stat_effects)


def _opt_acheron(action: str, *, eidolon: int = 0, conditionals: dict | None = None,
                 nihility_teammates: int = 0):
    """对方黄泉场景：E1 钉 false（我方待收）、thunderCoreStacks 钉 0（行迹 3 前半
    我方待收——divergence 另测）、结 9 / Core 6 / The Abyss 按场配."""
    cond = {"crimsonKnotStacks": 9, "nihilityTeammatesBuff": True,
            "e1EnemyDebuffed": False, "thunderCoreStacks": 0,
            "stygianResurgeHitsOnTarget": 6, "e4UltVulnerability": True,
            "e6UltBuffs": True}
    cond.update(conditionals or {})
    paths = ["Nihility"] * nihility_teammates
    return {
        "kind": "character", "character_id": "1308", "eidolon": eidolon,
        "action": action, "element": "thunder", "conditionals": cond,
        "base": {"atk": AC_ATK, "hp": 1125.432, "def": 436.59, "spd": 101},
        "attacker": {"atk": AC_ATK, "hp": 1125.432, "def": 436.59, "spd": 101,
                     "cr": 0.05, "cd": 0.5},
        "self_path": "Nihility", "teammate_paths": paths,
        "enemy": {"level": 80, "damage_resistance": 0.0, "weakness_broken": False,
                  "count": 1},
    }


class TestAcheronDuipai:
    """黄泉 E0：普攻/战技全等 + 大招 13 段全链全等（双锚 + 乘区读回）."""

    def test_panel_echo(self, optimizer_driver):
        theirs = run_optimizer(optimizer_driver, _opt_acheron("basic"))
        _assert_panel(theirs, atk=AC_ATK)

    def test_basic(self, optimizer_driver):
        eng, log = _make_logged(_acheron_compiled())
        _cast(eng, "1308", "130801")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_acheron("basic"))

        assert ours == pytest.approx([1.0 * AC_ATK * Z], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(1.0 * AC_ATK * Z, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_single(self, optimizer_driver):
        """战技 lv10=1.6 单体场（1 敌 → blast 无相邻）：双方全等."""
        eng, log = _make_logged(_acheron_compiled())
        _cast(eng, "1308", "130802")
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver, _opt_acheron("skill"))

        assert ours == pytest.approx([1.6 * AC_ATK * Z], rel=REL_TOL)
        assert theirs["hits"][0]["damage"] == pytest.approx(1.6 * AC_ATK * Z, rel=REL_TOL)
        assert ours[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL)

    def test_skill_blast_three(self, optimizer_driver):
        """D6 结构差：对方战技只建主目标单发（1.6），不建模 blast 相邻段；
        我方 3 敌场打中位 e2（blast = 主 + 左右相邻）逐段：主 1.6 == 对方，
        相邻 0.6×2 手算自证（lv10 同档表）."""
        eng, log = _make_logged(_acheron_compiled(enemies=_dummy("e1", "thunder", n=3)))
        _cast(eng, "1308", "130802", target="e2")
        adj1 = _hit_amounts(log, source="1308", target="e1")
        main = _hit_amounts(log, source="1308", target="e2")
        adj3 = _hit_amounts(log, source="1308", target="e3")
        theirs = run_optimizer(optimizer_driver, _opt_acheron("skill"))

        assert main == pytest.approx([1.6 * AC_ATK * Z], rel=REL_TOL)
        assert main[0] == pytest.approx(theirs["hits"][0]["damage"], rel=REL_TOL), (
            "主目标段双方互对")
        assert adj1 == pytest.approx([0.6 * AC_ATK * Z], rel=REL_TOL), "相邻段① vs 手算"
        assert adj3 == pytest.approx([0.6 * AC_ATK * Z], rel=REL_TOL), "相邻段② vs 手算"

    def test_ult_full_chain(self, optimizer_driver):
        """大招 13 段全链（结 9 起手 + 行迹 3 双件钉 3 层）：3×雨斩 0.24 + 3×结爆 0.6
        + 返渡 1.2 + Core 0.25×6 == 对方聚合单发 5.22×1.9。对齐条件：天赋 RES_PEN
        已收编（ULT_RES_SHRED 常驻件，D4 收官）+ 3 虚无队（The Abyss 1.6 双方同池：
        dmg_final_dmg_boost ≡ 对方 FINAL_DMG_BOOST 乘算——D7 已转正，行迹 3 增伤
        入池后仍数值全等）+
        行迹 3 双件预钉 3 层（D5 收官——大招全程 1.9 池 ≡ 对方 thunderCoreStacks=3
        slider，「上一大招遗留 3 层」在局态双方同义）."""
        eng, log = _make_logged(_acheron_compiled(extra_nihility=2))
        st = eng.state.actors["1308"]
        assert math.isclose(
            eng.pipeline.effective_stats(st)["dmg_bonus"].get("final_dmg_boost", 0.0), 0.6,
            rel_tol=1e-9), "我方 The Abyss 3 虚无成立（final_dmg_boost 桶 0.6——D7 已转正）"
        _pin_trace_tc(eng, 3)
        _knots(eng, "e1", 9)
        _acheron_ult(eng)
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver,
                               _opt_acheron("ult", nihility_teammates=2,
                                            conditionals={"thunderCoreStacks": 3}))

        # 逐段手算（段序：雨斩/结爆 ×3 → 返渡 → Core×6）
        z_ult = Z * 1.2 * 1.6 * 1.9   # 防御 0.5 × 未击破 0.9 × 暴击 1.025 × 抗性 1.2 × 增伤 1.6 × 行迹3 1.9
        scalings = [0.24, 0.6, 0.24, 0.6, 0.24, 0.6, 1.2] + [0.25] * 6
        assert len(ours) == 13, f"13 段齐发（实收 {len(ours)} 段）"
        for i, (amt, sc) in enumerate(zip(ours, scalings)):
            assert amt == pytest.approx(sc * AC_ATK * z_ult, rel=REL_TOL), f"段 {i}（{sc}）vs 手算"
        # 总和双方互对 + 对方聚合倍率/乘区读回
        assert sum(ours) == pytest.approx(theirs["total"], rel=REL_TOL), "13 段总和 vs 对方聚合单发"
        assert sum(scalings) * 1.9 == pytest.approx(9.918, rel=REL_TOL)
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(5.22, rel=REL_TOL)
        bd = theirs["hits"][0]["breakdown"]
        for k, v in (("defMulti", 0.5), ("baseUniversalMulti", 0.9), ("critMulti", 1.025),
                     ("resMulti", 1.2), ("dmgBoostMulti", 1.9), ("finalDmgMulti", 1.6),
                     ("abilityMulti", 5.22 * AC_ATK)):
            assert bd[k] == pytest.approx(v, rel=REL_TOL), f"乘区 {k}"
        assert theirs["stats"]["final_dmg_boost"] == pytest.approx(0.6, rel=REL_TOL), (
            "对方 The Abyss 乘算件（×1.6 = 1+0.6 读回）")


class TestAcheronKnownDivergence:
    """黄泉结构差两件（映射表 D4/D5）——均已收官转三方比等（2026-09-23）."""

    def test_ult_talent_res_pen(self, optimizer_driver):
        """D4 已收官：天赋大招期间敌方抗性 -20%——ULT_RES_SHRED 常驻件
        （hit_condition ultimate）承载，不再注入等价件。对方 talentResPen 常开
        ULT 域——大招 13 段总和双方全等（行迹 3 双件钉 3 层隔离 D5）."""
        eng, log = _make_logged(_acheron_compiled(extra_nihility=2))
        _pin_trace_tc(eng, 3)
        _knots(eng, "e1", 9)
        _acheron_ult(eng)
        ours = sum(_hit_amounts(log, source="1308"))
        theirs = run_optimizer(optimizer_driver,
                               _opt_acheron("ult", nihility_teammates=2,
                                            conditionals={"thunderCoreStacks": 3}))

        assert ours == pytest.approx(5.22 * AC_ATK * Z * 1.2 * 1.6 * 1.9, rel=REL_TOL), (
            "我方全链（RES_PEN 1.2 × The Abyss 1.6 × 行迹3 1.9）vs 手算")
        assert theirs["total"] == pytest.approx(ours, rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["resMulti"] == pytest.approx(1.2, rel=REL_TOL)

    def test_ult_thunder_core_trace(self, optimizer_driver):
        """D5 已收官①：行迹 3 前半（雨斩命中带结敌增伤 30%/层×3、3 回合）——
        TRACE_TC/TRACE_TC_DMG 双件收编。预钉 3 层（上一大招遗留态）→ 大招全程
        1.9 增伤池 ≡ 对方 thunderCoreStacks=3，三方全等（D4 已收编无需注入）."""
        eng, log = _make_logged(_acheron_compiled(extra_nihility=2))
        _pin_trace_tc(eng, 3)
        _knots(eng, "e1", 9)
        _acheron_ult(eng)
        ours = sum(_hit_amounts(log, source="1308"))
        theirs = run_optimizer(optimizer_driver, _opt_acheron(
            "ult", nihility_teammates=2, conditionals={"thunderCoreStacks": 3}))

        assert ours == pytest.approx(5.22 * AC_ATK * Z * 1.2 * 1.6 * 1.9, rel=REL_TOL), (
            "我方全链 vs 手算（1.9 池全程）")
        assert theirs["total"] == pytest.approx(ours, rel=REL_TOL), "双方互对"
        assert theirs["hits"][0]["breakdown"]["dmgBoostMulti"] == pytest.approx(1.9, rel=REL_TOL)

    def test_ult_thunder_core_gain_mechanic(self, optimizer_driver):
        """D5 已收官②：叠层机制实打（0 层起手）——雨斩逐段命中带结敌目标 +1 层
        （30%/层），增伤件当段命中后生效（on-hit buff 不回溯触发段=通用口径）：
        雨斩段 ×1.0/1.3/1.6，结爆段 ×1.3/1.6/1.9（增伤钩在摘结钩前=「击中即生效」
        读法，段内结爆已吃当层——对方 slider 无渐进模型，本测试我方 vs 手算单钉）."""
        eng, log = _make_logged(_acheron_compiled(extra_nihility=2))
        _knots(eng, "e1", 9)
        _acheron_ult(eng)
        ours = _hit_amounts(log, source="1308")
        st = eng.state.actors["1308"]

        z = Z * 1.2 * 1.6   # 抗性 1.2（D4 收编）× The Abyss 1.6
        boosts = [1.0, 1.3, 1.3, 1.6, 1.6, 1.9, 1.9] + [1.9] * 6
        scalings = [0.24, 0.6, 0.24, 0.6, 0.24, 0.6, 1.2] + [0.25] * 6
        assert len(ours) == 13
        for i, (amt, sc, b) in enumerate(zip(ours, scalings, boosts)):
            assert amt == pytest.approx(sc * b * AC_ATK * z, rel=REL_TOL), (
                f"段 {i}（{sc}×{b}）vs 手算")
        assert st.modifiers["TRACE_TC"].stacks == 3, "三段雨斩各 +1 层（满 3）"
        assert st.modifiers["TRACE_TC_DMG"].stat_effects["all_dmg"] == pytest.approx(0.9), (
            "值件重烘 0.3×3=0.9")


class TestAcheronE4Duipai:
    """黄泉 E4 星魂链对拍（E1 钉 false 隔离待收项）：E3 大招随档 lv12 +
    E4 大招易伤 8% 双方各自通道全等."""

    def test_e4_ult_vuln_chain(self, optimizer_driver):
        eng, log = _make_logged(_acheron_compiled(eidolon=4, extra_nihility=2))
        _pin_trace_tc(eng, 3)
        _knots(eng, "e1", 9)
        # E4：敌人入场挂大招易伤（初始敌人不自动发 actor_enter——e2e 同口径手动补）
        eng.bus.emit("actor_enter", {"actor": "e1", "actor_type": "monster"}, eng.state)
        assert "E4_ULT_VULN" in eng.state.actors["e1"].modifiers
        _acheron_ult(eng)
        ours = _hit_amounts(log, source="1308")
        theirs = run_optimizer(optimizer_driver,
                               _opt_acheron("ult", eidolon=4, nihility_teammates=2,
                                            conditionals={"thunderCoreStacks": 3}))

        # E3 随档 lv12：雨斩 0.2592 / 结爆 min(0.162×4, 0.648)=0.648 / 返渡 1.296；Core 无档 0.25
        z_e4 = Z * 1.2 * 1.6 * 1.08 * 1.9   # ×行迹3 1.9（预钉 3 层——D4/D5 收编后）
        scalings = [0.2592, 0.648, 0.2592, 0.648, 0.2592, 0.648, 1.296] + [0.25] * 6
        assert len(ours) == 13
        for i, (amt, sc) in enumerate(zip(ours, scalings)):
            assert amt == pytest.approx(sc * AC_ATK * z_e4, rel=REL_TOL), f"段 {i}（{sc}）vs 手算"
        assert sum(scalings) == pytest.approx(5.5176, rel=REL_TOL)
        assert theirs["hits"][0]["atk_scaling"] == pytest.approx(5.5176, rel=REL_TOL)
        assert sum(ours) == pytest.approx(theirs["total"], rel=REL_TOL), (
            "E4 链 13 段总和双方互对（易伤 1.08 两侧各自通道）")
        assert theirs["hits"][0]["breakdown"]["vulnMulti"] == pytest.approx(1.08, rel=REL_TOL)
