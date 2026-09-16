/**
 * 对拍驱动（BACKLOG B22）：JSON 场景 → hsr-optimizer 伤害计算器 → JSON 结果。
 *
 * 职责只有"翻译 + 调用"：把 stdin 的场景 JSON 翻译成 optimizer 的
 * ComputedStatsContainer / OptimizerAction / OptimizerContext，调用
 * CritDamageFunction / BreakDamageFunction / SuperBreakDamageFunction /
 * ElationDamageFunction / DotDamageFunction，把数值从 stdout 吐出。
 * 不修改 external/hsr-optimizer 的任何文件。
 *
 * 跑法（仓库根目录）：
 *   external/hsr-optimizer/node_modules/.bin/rolldown -c scripts/crosscheck/rolldown.config.mjs
 *   echo '{"kind":"crit", ...}' | node scripts/crosscheck/dist/crosscheck.mjs
 * （pytest 的 tests/test_crosscheck_optimizer.py 会自动完成上述两步）
 *
 * 场景 JSON：
 * {
 *   "kind": "crit" | "break" | "super_break" | "elation" | "dot",
 *   "element": "physical|fire|ice|thunder|wind|quantum|imaginary",
 *   "attacker": { "level", "atk", "hp", "def", "spd",
 *                 "cr", "cd", "be", "dmg_boost", "element_boost",
 *                 "def_pen", "res_pen", "vulnerability", "final_dmg_boost",
 *                 "super_break_modifier", "break_boost",          // super_break
 *                 "break_efficiency_boost",                        // super_break
 *                 "elation", "merrymaking",                        // elation
 *                 "effect_hit", "effect_res_pen", "dot_boost" },   // dot
 *   "hit":   { "atk_scaling", "hp_scaling", "def_scaling",         // crit/dot
 *              "toughness_dmg", "fixed_toughness_dmg",             // super_break
 *              "elation_scaling", "punchline_stacks",              // elation
 *              "dot_base_chance", "dot_split", "dot_stacks",
 *              "tick_coefficient" },                               // dot
 *   "enemy": { "level", "max_toughness", "damage_resistance",
 *              "effect_resistance", "weakness_broken" },
 *   "break": { "element_scaling", "special_scaling" }               // break
 * }
 *
 * 键位映射口径（按对方函数实际读的键）：
 * - super_break 的 dmgBoostMulti 只读 **hit 层** HKey.BOOST（同 break）——
 *   "break_boost" 写在 hit 层（getHitIndex），对应我方击破增伤池 break_dmg_boost；
 *   action 层 "dmg_boost" 对 break/super_break 不可见（getHitValue 不读 action 层）。
 * - 对方无独立「超击破增伤池」键（我方 super_break_dmg_boost 池在对方无落点）；
 *   对方无独立「DoT 增伤」键——"dot_boost" 与 "dmg_boost" 合写 action 层 BOOST
 *   （双方均为增伤池内加算，数值等价；我方 dot_dmg_boost 桶语义 = 对方按 hit
 *   标签过滤的 BOOST）。
 *
 * 输出 JSON：{ "damage": number, "breakdown": { 各乘区 } }
 *
 * ---------------------------------------------------------------------------
 * 已核实的公式差（击破韧性除数，/40 vs /120）：
 *   我方 pipeline.break_damage:  base = 3767.5533 × scaling × (0.5 + maxToughness/40)
 *   optimizer BreakDamageFunction: base = 3767.5533 × scaling × (0.5 + maxToughness/120)
 *     （见 external/hsr-optimizer/src/lib/optimization/engine/damage/damageCalculator.ts
 *       BreakDamageFunction.apply）
 *   实测（BE=1.0 火，精英 maxToughness=120，lvl80 vs lvl80，已击破，0 抗性）：
 *     我方 13186.4366（0.5+120/40 = 3.5），optimizer 5651.3300（0.5+120/120 = 1.5），
 *     比值恰为 3.5/1.5 = 7/3 ≈ 2.3333。
 *   结论：fandom 的 toughness/40 与 optimizer 的 toughness/120 差 3 倍——
 *   已查明为**单位差**（客户端原始韧性点 = 3×显示点，raw/120 ≡ display/40 恒等，
 *   B19 已标"基本解决"）。本驱动不做对齐，如实暴露差值。
 *
 * 已核实的结构差（2026-09-16 三路对拍扩展钉住，详见 tests/test_crosscheck_optimizer.py）：
 * - 超击破增伤池：我方有独立乘区 super_break_dmg_boost（忘归人 E4/乱破族，
 *   (1+池) 与击破增伤池乘算）；对方 SuperBreakDamageFunction 无此键（增伤只有
 *   hit 层 HKey.BOOST 一个池）。该池非零时两侧差值恰为 ×(1+池)。
 * - 欢愉增伤池/减伤区：我方 elation_damage 有 elation_dmg_boost 乘区（爻光族槽位）
 *   与 dmg_red 乘区（读目标减伤桶）；对方 ElationDamageFunction 两者皆无
 *   （乘区表：baseUniversal/def/res/vuln/finalDmg/crit/trueDmg + elation/
 *   merrymaking/punchline）。池非零时差值恰为 ×(1+池)。
 * - DoT：我方有独立易伤区 ind_vuln（常规 DoT 生效列）；对方 DotDamageFunction
 *   无此键。对方有 tickCoefficient / dotSplit / dotStacks 槽（默认 1/0/1），
 *   我方无对应槽。各槽非中性时差值恰为对应倍数。
 * ---------------------------------------------------------------------------
 */

import { readFileSync } from 'node:fs'

import { HKey, StatKey, type AKeyValue } from 'lib/optimization/engine/config/keys'
import {
  computeTargetMask,
  DamageTag,
  ElementTag,
  OutputTag,
} from 'lib/optimization/engine/config/tag'
import {
  ComputedStatsContainer,
  ComputedStatsContainerConfig,
  type OptimizerEntity,
} from 'lib/optimization/engine/container/computedStatsContainer'
import {
  DamageFunctionType,
  getDamageFunction,
} from 'lib/optimization/engine/damage/damageCalculator'
import { NamedArray } from 'lib/optimization/engine/util/namedArray'
import { AbilityKind } from 'lib/optimization/rotation/turnAbilityConfig'
import type { Hit } from 'types/hitConditionalTypes'
import type { OptimizerAction, OptimizerContext } from 'types/optimizer'

// ---------------------------------------------------------------------------
// 场景类型
// ---------------------------------------------------------------------------

type ElementName =
  | 'physical' | 'fire' | 'ice' | 'thunder' | 'wind' | 'quantum' | 'imaginary'

interface AttackerSpec {
  level?: number
  atk?: number
  hp?: number
  def?: number
  spd?: number
  cr?: number
  cd?: number
  be?: number
  dmg_boost?: number      // 通用增伤（StatKey.BOOST，action 层）
  element_boost?: number  // 属性增伤（如 LIGHTNING_DMG_BOOST）
  def_pen?: number
  res_pen?: number
  vulnerability?: number
  final_dmg_boost?: number
  super_break_modifier?: number      // 超击破转换倍率池（StatKey.SUPER_BREAK_MODIFIER）
  break_boost?: number               // 击破增伤池（hit 层 HKey.BOOST——break/super_break 唯一增伤读口）
  break_efficiency_boost?: number    // 削韧效率（StatKey.BREAK_EFFICIENCY_BOOST）
  elation?: number                   // 欢愉度（StatKey.ELATION）
  merrymaking?: number               // 好活当赏合并值（StatKey.MERRYMAKING）
  effect_hit?: number                // 效果命中（StatKey.EHR）
  effect_res_pen?: number            // 效果抵抗穿透（StatKey.EFFECT_RES_PEN）
  dot_boost?: number                 // DoT 增伤（对方无独立键，并入 action 层 BOOST——加算等价）
}

interface HitSpec {
  atk_scaling?: number
  hp_scaling?: number
  def_scaling?: number
  toughness_dmg?: number         // super_break：名义削韧（进 referenceHit.toughnessDmg）
  fixed_toughness_dmg?: number   // super_break：固定削韧（进 referenceHit.fixedToughnessDmg）
  elation_scaling?: number       // elation：纯倍率（hit.elationScaling）
  punchline_stacks?: number      // elation：阿哈笑点（hit.punchlineStacks）
  dot_base_chance?: number       // dot：基础命中概率（hit.dotBaseChance，默认 1）
  dot_split?: number             // dot：hit.dotSplit（对方专槽，默认 0）
  dot_stacks?: number            // dot：hit.dotStacks（对方专槽，默认 1）
  tick_coefficient?: number      // dot：hit.tickCoefficient（对方专槽，默认 1）
}

interface EnemySpec {
  level?: number
  max_toughness?: number
  damage_resistance?: number   // 已结算的属性抗性（弱点 0 / 非弱点 0.2 / 额外抗性）
  effect_resistance?: number
  weakness_broken?: boolean
}

interface BreakSpec {
  element_scaling?: number     // 属性击破倍率（火 1.0 / 物理 2.0 / 风 1.5 …）
  special_scaling?: number
}

type ScenarioKind = 'crit' | 'break' | 'super_break' | 'elation' | 'dot'

interface Scenario {
  kind: ScenarioKind
  element: ElementName
  attacker?: AttackerSpec
  hit?: HitSpec
  enemy?: EnemySpec
  break?: BreakSpec
}

// kind → 对方 hit 三要素（damageFunctionType / damageTag / directHit）
const KIND_MAP: Record<ScenarioKind, {
  fnType: DamageFunctionType, damageTag: DamageTag, directHit: boolean
}> = {
  crit: { fnType: DamageFunctionType.Crit, damageTag: DamageTag.BASIC, directHit: true },
  break: { fnType: DamageFunctionType.Break, damageTag: DamageTag.BREAK, directHit: false },
  super_break: { fnType: DamageFunctionType.SuperBreak, damageTag: DamageTag.SUPER_BREAK, directHit: false },
  elation: { fnType: DamageFunctionType.Elation, damageTag: DamageTag.ELATION, directHit: false },
  dot: { fnType: DamageFunctionType.Dot, damageTag: DamageTag.DOT, directHit: false },
}

// ---------------------------------------------------------------------------
// 元素映射（我方 canonical key → optimizer ElementTag + 属性增伤 StatKey）
// ---------------------------------------------------------------------------

const ELEMENT_MAP: Record<ElementName, { tag: ElementTag, boostKey: AKeyValue }> = {
  physical: { tag: ElementTag.Physical, boostKey: StatKey.PHYSICAL_DMG_BOOST },
  fire: { tag: ElementTag.Fire, boostKey: StatKey.FIRE_DMG_BOOST },
  ice: { tag: ElementTag.Ice, boostKey: StatKey.ICE_DMG_BOOST },
  thunder: { tag: ElementTag.Lightning, boostKey: StatKey.LIGHTNING_DMG_BOOST },
  wind: { tag: ElementTag.Wind, boostKey: StatKey.WIND_DMG_BOOST },
  quantum: { tag: ElementTag.Quantum, boostKey: StatKey.QUANTUM_DMG_BOOST },
  imaginary: { tag: ElementTag.Imaginary, boostKey: StatKey.IMAGINARY_DMG_BOOST },
}

// ---------------------------------------------------------------------------
// 主流程
// ---------------------------------------------------------------------------

function run(scenario: Scenario) {
  const atk = scenario.attacker ?? {}
  const hitSpec = scenario.hit ?? {}
  const enemy = scenario.enemy ?? {}
  const breakSpec = scenario.break ?? {}
  const elem = ELEMENT_MAP[scenario.element]
  if (!elem) throw new Error(`unknown element: ${scenario.element}`)
  const kindSpec = KIND_MAP[scenario.kind]
  if (!kindSpec) throw new Error(`unknown kind: ${scenario.kind}`)

  const isCrit = scenario.kind === 'crit'
  const isBreak = scenario.kind === 'break'
  const isSuperBreak = scenario.kind === 'super_break'
  const isElation = scenario.kind === 'elation'
  const isDot = scenario.kind === 'dot'

  // --- Hit（definition + runtime 字段；kind 专槽按对方函数实际读的键填） ---
  const hit = {
    damageFunctionType: kindSpec.fnType,
    damageType: kindSpec.damageTag,
    damageElement: elem.tag,
    outputTag: OutputTag.DAMAGE,
    directHit: kindSpec.directHit,
    atkScaling: hitSpec.atk_scaling ?? 0,
    hpScaling: hitSpec.hp_scaling ?? 0,
    defScaling: hitSpec.def_scaling ?? 0,
    skillPointsUsed: 0,                      // CritHit 必填
    specialScaling: breakSpec.special_scaling ?? 1, // BreakHit 用
    localHitIndex: 0,
    registerIndex: 0,
    sourceEntityIndex: 0,
    scalingEntityIndex: 0,
  } as Record<string, unknown>
  if (isSuperBreak) {
    // SuperBreakDamageFunction 经 hit.referenceHit 读削韧（toughnessDmg/fixedToughnessDmg）
    // 与 BREAK_EFFICIENCY_BOOST 的 hitIndex（referenceHit.localHitIndex ?? 本 hit）
    hit.referenceHit = {
      toughnessDmg: hitSpec.toughness_dmg ?? 0,
      fixedToughnessDmg: hitSpec.fixed_toughness_dmg ?? 0,
      localHitIndex: 0,
    }
  }
  if (isElation) {
    hit.elationScaling = hitSpec.elation_scaling ?? 0
    hit.punchlineStacks = hitSpec.punchline_stacks ?? 0
  }
  if (isDot) {
    hit.dotBaseChance = hitSpec.dot_base_chance ?? 1
    if (hitSpec.dot_split != null) hit.dotSplit = hitSpec.dot_split
    if (hitSpec.dot_stacks != null) hit.dotStacks = hitSpec.dot_stacks
    if (hitSpec.tick_coefficient != null) hit.tickCoefficient = hitSpec.tick_coefficient
  }

  // --- 单实体注册表 ---
  const entityDef = { primary: true, summon: false, memosprite: false, pet: false }
  const entity: OptimizerEntity = {
    ...entityDef,
    name: 'crosscheck',
    targetMask: computeTargetMask(entityDef),
    baseAtk: atk.atk ?? 0,
    baseDef: atk.def ?? 0,
    baseHp: atk.hp ?? 0,
    baseSpd: atk.spd ?? 100,
  }
  const registry = new NamedArray([entity], (e) => e.name)

  // --- Action / Context（只填计算器实际读的字段，其余 cast） ---
  const action = {
    actionType: AbilityKind.BASIC,
    hits: [hit as unknown as Hit],
    conditionalRegistry: {},
    conditionalState: {},
  } as unknown as OptimizerAction

  const context = {
    allActions: [action],
    outputRegistersLength: 1,
    deprioritizeBuffs: false,
    enemyLevel: enemy.level ?? 80,
    enemyMaxToughness: enemy.max_toughness ?? 0,
    enemyDamageResistance: enemy.damage_resistance ?? 0,
    enemyEffectResistance: enemy.effect_resistance ?? 0,
    enemyWeaknessBroken: enemy.weakness_broken ?? false,
    elementalBreakScaling: breakSpec.element_scaling ?? 1,
  } as unknown as OptimizerContext

  // --- 容器 ---
  const config = new ComputedStatsContainerConfig(action, context, registry)
  action.config = config
  const x = new ComputedStatsContainer()
  x.initializeArrays(config.arrayLength, context)
  x.setConfig(config)

  // --- 面板写入（实体 0 action 层；getValue = action 值 + hit 值，hit 层除
  //     break/super_break 的 HKey.BOOST 读口外保持 0） ---
  const a = x.a
  a[StatKey.ATK] = atk.atk ?? 0
  a[StatKey.HP] = atk.hp ?? 0
  a[StatKey.DEF] = atk.def ?? 0
  a[StatKey.SPD] = atk.spd ?? 100
  a[StatKey.CR] = atk.cr ?? 0
  a[StatKey.CD] = atk.cd ?? 0
  a[StatKey.BE] = atk.be ?? 0
  a[StatKey.BOOST] = (atk.dmg_boost ?? 0) + (atk.dot_boost ?? 0)
  a[elem.boostKey] = atk.element_boost ?? 0
  a[StatKey.DEF_PEN] = atk.def_pen ?? 0
  a[StatKey.RES_PEN] = atk.res_pen ?? 0
  a[StatKey.VULNERABILITY] = atk.vulnerability ?? 0
  a[StatKey.FINAL_DMG_BOOST] = atk.final_dmg_boost ?? 0
  a[StatKey.SUPER_BREAK_MODIFIER] = atk.super_break_modifier ?? 0
  a[StatKey.BREAK_EFFICIENCY_BOOST] = atk.break_efficiency_boost ?? 0
  a[StatKey.ELATION] = atk.elation ?? 0
  a[StatKey.MERRYMAKING] = atk.merrymaking ?? 0
  a[StatKey.EHR] = atk.effect_hit ?? 0
  a[StatKey.EFFECT_RES_PEN] = atk.effect_res_pen ?? 0
  // break/super_break 的 dmgBoostMulti = 1 + getHitValue(HKey.BOOST)——只读 hit 层
  a[x.getHitIndex(0, 0, HKey.BOOST)] = atk.break_boost ?? 0

  // --- 调用伤害函数 ---
  const damage = getDamageFunction(kindSpec.fnType).apply(x, action, 0, context)

  // --- breakdown：按 optimizer 公式从容器读回各乘区（对拍显微镜） ---
  const defPen = x.getValue(StatKey.DEF_PEN, 0)
  const resPen = x.getValue(StatKey.RES_PEN, 0)
  const cr = Math.min(1, x.getValue(StatKey.CR, 0) + x.getValue(StatKey.CR_BOOST, 0))
  const cd = x.getValue(StatKey.CD, 0) + x.getValue(StatKey.CD_BOOST, 0)
  const abilityMulti = (hitSpec.atk_scaling ?? 0) * x.getValue(StatKey.ATK, 0)
    + (hitSpec.hp_scaling ?? 0) * x.getValue(StatKey.HP, 0)
    + (hitSpec.def_scaling ?? 0) * x.getValue(StatKey.DEF, 0)

  const breakdown: Record<string, number> = {
    baseUniversalMulti: config.enemyWeaknessBroken ? 1 : 0.9,
    defMulti: 100 / ((context.enemyLevel + 20) * Math.max(0, 1 - defPen) + 100),
    resMulti: 1 - (context.enemyDamageResistance - resPen),
    vulnMulti: 1 + x.getValue(StatKey.VULNERABILITY, 0),
    finalDmgMulti: 1 + x.getValue(StatKey.FINAL_DMG_BOOST, 0),
  }
  if (isCrit) {
    breakdown.dmgBoostMulti = 1 + x.getValue(StatKey.BOOST, 0) + x.getValue(elem.boostKey, 0)
    breakdown.abilityMulti = abilityMulti
    breakdown.critMulti = cr * (1 + cd) + (1 - cr)
  } else if (isBreak) {
    breakdown.breakBaseMulti = 3767.5533 * context.elementalBreakScaling
      * (0.5 + context.enemyMaxToughness / 120) * (breakSpec.special_scaling ?? 1)
    breakdown.beMulti = 1 + x.getValue(StatKey.BE, 0)
  } else if (isSuperBreak) {
    const breakEfficiencyMulti = 1 + x.getValue(StatKey.BREAK_EFFICIENCY_BOOST, 0)
    const effectiveToughness = breakEfficiencyMulti * (hitSpec.toughness_dmg ?? 0)
      + (hitSpec.fixed_toughness_dmg ?? 0)
    breakdown.breakEfficiencyMulti = breakEfficiencyMulti
    breakdown.effectiveToughness = effectiveToughness
    breakdown.superBreakBaseMulti = (3767.5533 / 10) * effectiveToughness
    breakdown.beMulti = 1 + x.getValue(StatKey.BE, 0)
    breakdown.superBreakModMulti = x.getValue(StatKey.SUPER_BREAK_MODIFIER, 0)
    breakdown.dmgBoostMulti = 1 + x.getHitValue(HKey.BOOST, 0)
  } else if (isElation) {
    const punchline = hitSpec.punchline_stacks ?? 0
    breakdown.abilityMulti = hitSpec.elation_scaling ?? 0
    breakdown.elationLevelMultiplier = 7535.107
    breakdown.elationMulti = 1 + Math.max(x.getValue(StatKey.ELATION, 0), 0)
    breakdown.merrymakeMulti = 1 + x.getValue(StatKey.MERRYMAKING, 0)
    breakdown.punchlineMulti = 1 + (5 * punchline) / (punchline + 240)
    breakdown.critMulti = cr * (1 + cd) + (1 - cr)
  } else if (isDot) {
    const dotBaseChance = hitSpec.dot_base_chance ?? 1
    const dotSplit = hitSpec.dot_split ?? 0
    const dotStacks = hitSpec.dot_stacks ?? 1
    const effectiveDotChance = Math.min(1,
      dotBaseChance
      * (1 + x.getValue(StatKey.EHR, 0))
      * (1 - context.enemyEffectResistance + x.getValue(StatKey.EFFECT_RES_PEN, 0)))
    breakdown.dmgBoostMulti = 1 + x.getValue(StatKey.BOOST, 0) + x.getValue(elem.boostKey, 0)
    breakdown.abilityMulti = abilityMulti
    breakdown.ehrMulti = dotSplit
      ? (1 + dotSplit * effectiveDotChance * (dotStacks - 1)) / (1 + dotSplit * (dotStacks - 1))
      : effectiveDotChance
    breakdown.tickCoefficientMulti = hitSpec.tick_coefficient ?? 1
  }

  return { damage, breakdown }
}

const scenario = JSON.parse(readFileSync(0, 'utf8')) as Scenario
process.stdout.write(JSON.stringify(run(scenario)))
