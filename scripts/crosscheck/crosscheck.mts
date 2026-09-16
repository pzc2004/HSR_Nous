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
 *
 * L2 角色级对拍（kind: "character"）：对方角色实现（conditionals controller）
 * 整链求值——actionDefinition 取 hits → precomputeEffects/MutualEffects 条件
 * buff → 钉死面板写入 → ATK_P→白值换算（镜像 calculateStats.applyPercentStats）
 * → finalizeCalculations → 逐 hit getDamageFunction。不装遗器（x.c 空 sets →
 * ashblazing finalizer 自然 no-op）、不带光锥、星魂/条件开关由场景钉死。
 * 场景 JSON：
 * {
 *   "kind": "character",
 *   "character_id": "1013", "eidolon": 0,
 *   "action": "basic" | "skill" | "ult" | "fua",
 *   "conditionals": { ...覆盖 defaults() 的开关... },
 *   "base": { "atk", "hp", "def", "spd" },          // 白值（ATK_P 换算基数）
 *   "attacker": { 同 crit 场景键 },                    // 钉死面板（终值）
 *   "self_path": "Nihility", "teammate_paths": [...], // countTeamPath 计数口径
 *   "enemy": { "level", "damage_resistance", "weakness_broken",
 *              "count", "max_toughness" },
 *   "elemental_break_scaling": 1.0,
 *   "equipment": {                                            // 可选——装备对拍扩展
 *     "light_cone": { "id": "23007", "superimposition": 1,
 *                     "path": "Nihility",                      // 光锥命途（≠self_path → 空控制器，
 *                                                              //   镜像 LightConeConditionalsResolver.get 门控）
 *                     "conditionals": { ...覆盖 defaults()... } },
 *     "relic_sets": [ { "id": "116", "pieces": 4,              // ingameId + 件数（2|4）
 *                       "conditionals": { "valuePrisonerInDeepConfinement": 3 } } ]
 *   }
 * }
 * 输出 JSON：{ "total", "hits": [{ "damage", "atk_scaling", ..., "breakdown" }],
 *             "stats": { 面板回显——钉错面板/行迹平铺第一时间显形 } }
 *
 * ---------------------------------------------------------------------------
 * 装备链口径（equipment 块；无 equipment 时行为与 L2 逐字节一致）：
 * - attacker.* 仍是钉死**终值面板**——含光锥属性段（对方 LC properties 暴击/命中等
 *   无控制器承载，由场景钉进面板）；套装基础件（p2c/p4c）**不钉**——两侧各自原生
 *   通道（对方 calculateBasicSetEffects 真调用 / 我方遗器模板 stat_effects）。
 * - base.* = 白值（**角色+光锥**，ATK_P/SPD_P 换算基数；游戏公式白值口径，
 *   我方 _merge_light_cone 并入后同构）。
 * - 链路镜像（optimizerWorker.ts:274-277 + comboStateTransform.ts:152-156 +
 *   calculateStats.calculateComputedStats + calculateDamage.calculateBaseMultis）：
 *   LC precomputeEffects → 角色 precomputeEffects → LC precomputeMutual → 角色
 *   precomputeMutual → 钉死面板 → 套装基础件（真调用 calculateBasicSetEffects，
 *   c→x 差额镜像——c 只含套装件，差额 ≡ transferBaseStats+calculateBaseStats 对
 *   本场景的净效果）→ 套装条件件 p2x/p4x（executeNonDynamicCombatSets 的按套分派
 *   镜像——每套至多装一次、件数 2|4 的形态下与槽位派发逐件等价）→ ATK_P 白值换算
 *   → 终端套装件 p4t 镜像（evaluateTerminalSetConditionals：遗器只调 p4t、位面
 *   p2t——位面未接入）→ LC finalizeCalculations → 角色 finalizeCalculations。
 * - dynamic conditionals：试点全件（6 光锥/4 套装/3 角色）均无 dynamicConditionals
 *   （已逐件核实），evaluateDynamicConditionals/SetConditionals 未挂——接入带
 *   dynamic 件时按 calculateStats.ts:262-299 补镜像。
 * ---------------------------------------------------------------------------
 */

import { readFileSync } from 'node:fs'

import { Acheron } from 'lib/conditionals/character/1300/Acheron'
import { DrRatio } from 'lib/conditionals/character/1300/DrRatio'
import { Herta } from 'lib/conditionals/character/1000/Herta'
import { BaptismOfPureThought } from 'lib/conditionals/lightcone/5star/BaptismOfPureThought'
import { IncessantRain } from 'lib/conditionals/lightcone/5star/IncessantRain'
import { InTheNight } from 'lib/conditionals/lightcone/5star/InTheNight'
import { NightOnTheMilkyWay } from 'lib/conditionals/lightcone/5star/NightOnTheMilkyWay'
import { GoodNightAndSleepWell } from 'lib/conditionals/lightcone/4star/GoodNightAndSleepWell'
import { TheSeriousnessOfBreakfast } from 'lib/conditionals/lightcone/4star/TheSeriousnessOfBreakfast'
import {
  ConditionalDataType,
  ElementToDamage,
  type ElementName as OptimizerElementName,
} from 'lib/constants/constants'
import { BasicKey, BasicStatsArrayCore } from 'lib/optimization/basicStatsArray'
import { calculateBasicSetEffects, calculateSetCounts } from 'lib/optimization/calculateStats'
import { relicIndexToSetConfig } from 'lib/sets/setConfigRegistry'
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
  count?: number               // kind=character：敌数（ashblazing/敌数语义槽，默认 1）
}

interface BreakSpec {
  element_scaling?: number     // 属性击破倍率（火 1.0 / 物理 2.0 / 风 1.5 …）
  special_scaling?: number
}

type ScenarioKind = 'crit' | 'break' | 'super_break' | 'elation' | 'dot' | 'character'

interface Scenario {
  kind: ScenarioKind
  element: ElementName
  attacker?: AttackerSpec
  hit?: HitSpec
  enemy?: EnemySpec
  break?: BreakSpec
  // --- kind === 'character' 专槽 ---
  character_id?: string
  eidolon?: number
  action?: 'basic' | 'skill' | 'ult' | 'fua'
  conditionals?: Record<string, number | boolean>
  base?: { atk?: number, hp?: number, def?: number, spd?: number }
  self_path?: string
  teammate_paths?: string[]
  elemental_break_scaling?: number
  equipment?: EquipmentSpec
}

// --- 装备块（kind=character 可选；链路口径见文件头注） ---
interface LightConeEquipSpec {
  id: string
  superimposition?: number
  path: string                                  // 光锥命途（≠self_path → 空控制器）
  conditionals?: Record<string, number | boolean>
}

interface RelicSetEquipSpec {
  id: string                                    // ingameId（'116' 族）
  pieces: number                                // 件数（2 → p2 档；4 → p2+p4 档）
  conditionals?: Record<string, number | boolean>  // value{SetKey}/enabled{SetKey} 覆盖
}

interface EquipmentSpec {
  light_cone?: LightConeEquipSpec
  relic_sets?: RelicSetEquipSpec[]
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

// ---------------------------------------------------------------------------
// L2 角色级对拍：对方角色实现整链求值
// ---------------------------------------------------------------------------

const ACTION_KIND_MAP: Record<string, AbilityKind> = {
  basic: AbilityKind.BASIC,
  skill: AbilityKind.SKILL,
  ult: AbilityKind.ULT,
  fua: AbilityKind.FUA,
}

// 镜像 damageCalculator.elementTagToStatKeyBoost（逐 hit 增伤区读回用）
const ELEMENT_BOOST_BY_TAG: Record<number, AKeyValue> = {
  [ElementTag.Physical]: StatKey.PHYSICAL_DMG_BOOST,
  [ElementTag.Fire]: StatKey.FIRE_DMG_BOOST,
  [ElementTag.Ice]: StatKey.ICE_DMG_BOOST,
  [ElementTag.Lightning]: StatKey.LIGHTNING_DMG_BOOST,
  [ElementTag.Wind]: StatKey.WIND_DMG_BOOST,
  [ElementTag.Quantum]: StatKey.QUANTUM_DMG_BOOST,
  [ElementTag.Imaginary]: StatKey.IMAGINARY_DMG_BOOST,
}

// 角色注册表（本地显式登记——对方官方注册表走 import.meta.glob（Vite 特性），
// 打不进 node bundle；直引 config 等价：registry 本身也只是 id → config 的聚合。
// 接新角色 = 加一行 import + 一行登记）
const CHARACTER_REGISTRY: Record<string, { conditionals: (e: number, withContent: boolean) => never }> = {
  [Herta.id]: Herta as never,
  [Acheron.id]: Acheron as never,
  [DrRatio.id]: DrRatio as never,
}

// 光锥注册表（同角色注册表——lightConeConfigRegistry 同走 import.meta.glob）。
// 接新光锥 = 加一行 import + 一行登记；命途门控在 runCharacter 内镜像
// （LightConeConditionalsResolver.get：lightConePath ≠ path → 空控制器效果全灭）。
const LIGHTCONE_REGISTRY: Record<string, {
  conditionals: (s: number, withContent: boolean, wearer?: unknown) => never
}> = {
  [IncessantRain.id]: IncessantRain as never,
  [BaptismOfPureThought.id]: BaptismOfPureThought as never,
  [InTheNight.id]: InTheNight as never,
  [NightOnTheMilkyWay.id]: NightOnTheMilkyWay as never,
  [GoodNightAndSleepWell.id]: GoodNightAndSleepWell as never,
  [TheSeriousnessOfBreakfast.id]: TheSeriousnessOfBreakfast as never,
}

// 遗器套装：relicIndexToSetConfig 是静态显式表（无 glob），按 ingameId 现场查。
function relicConfigByIngameId(ingameId: string) {
  const cfg = relicIndexToSetConfig.find((c) => c.info.ingameId === ingameId)
  if (!cfg) throw new Error(`relic set not found: ${ingameId}`)
  return cfg
}

// 我方 canonical 元素名 → 对方 ElementName（LC wearer 元数据 / elementalDamageType 用）
const ELEMENT_DISPLAY: Record<ElementName, OptimizerElementName> = {
  physical: 'Physical', fire: 'Fire', ice: 'Ice', thunder: 'Lightning',
  wind: 'Wind', quantum: 'Quantum', imaginary: 'Imaginary',
}

function runCharacter(scenario: Scenario) {
  if (!scenario.character_id) throw new Error('character_id required')
  const actionKind = ACTION_KIND_MAP[scenario.action ?? '']
  if (!actionKind) throw new Error(`unknown action: ${scenario.action}`)
  const atk = scenario.attacker ?? {}
  const enemy = scenario.enemy ?? {}
  const base = scenario.base ?? {}

  // --- 角色 controller（星魂钉死；withContent=false → 空 i18n，文本不取） ---
  const config0 = CHARACTER_REGISTRY[scenario.character_id]
  if (!config0) throw new Error(`character not registered: ${scenario.character_id}`)
  const controller = config0.conditionals(scenario.eidolon ?? 0, false) as {
    defaults: () => Record<string, number | boolean>
    entityDeclaration: () => string[]
    entityDefinition?: (a: OptimizerAction, c: OptimizerContext) => Record<string, Record<string, unknown>>
    actionDefinition: (a: OptimizerAction, c: OptimizerContext) => Record<string, { hits: Hit[] }>
    precomputeEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void
    precomputeMutualEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext, s: OptimizerAction) => void
    finalizeCalculations?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void
  }

  // --- 条件开关：defaults() + 场景覆盖（buff 状态映射表的对方侧落点） ---
  const conditionals = { ...controller.defaults(), ...(scenario.conditionals ?? {}) }

  // --- 装备：LC controller + 套装 config（无 equipment → 全空，行为与 L2 一致） ---
  const equip = scenario.equipment ?? {}
  const lcSpec = equip.light_cone
  const setSpecs = equip.relic_sets ?? []
  type LcController = {
    defaults: () => Record<string, number | boolean>
    precomputeEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void
    precomputeMutualEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext, s: OptimizerAction) => void
    finalizeCalculations?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void
  }
  let lcController: LcController = { defaults: () => ({}) }
  if (lcSpec) {
    const lcConfig = LIGHTCONE_REGISTRY[lcSpec.id]
    if (!lcConfig) throw new Error(`light cone not registered: ${lcSpec.id}`)
    if (lcSpec.path === scenario.self_path) {
      lcController = lcConfig.conditionals((lcSpec.superimposition ?? 1) - 1, false, {
        element: ELEMENT_DISPLAY[scenario.element],
        characterId: scenario.character_id,
      }) as LcController
    }
    // 命途不匹配 → 空控制器（镜像 LightConeConditionalsResolver.get 门控——效果全灭）
  }
  const lcConditionals = { ...lcController.defaults(), ...(lcSpec?.conditionals ?? {}) }
  // 套装条件开关：display.defaultValue 铺底（镜像 buildDefaultSetConditionals）+ 场景覆盖
  const setConfigs = setSpecs.map((s) => relicConfigByIngameId(s.id))
  const setConditionals: Record<string, number | boolean> = {}
  for (const cfg of setConfigs) {
    const key = (cfg.display.conditionalType === ConditionalDataType.BOOLEAN ? 'enabled' : 'value')
      + cfg.setKey
    setConditionals[key] = cfg.display.defaultValue
  }
  for (const s of setSpecs) Object.assign(setConditionals, s.conditionals ?? {})

  // --- Action（只填角色链实际读的字段，其余 cast） ---
  const action = {
    actionType: actionKind,
    actionKind,
    actorId: scenario.character_id,
    actorEidolon: scenario.eidolon ?? 0,
    characterConditionals: conditionals,
    lightConeConditionals: lcConditionals,
    setConditionals,
    teammate0: { characterConditionals: {}, lightConeConditionals: {} },
    teammate1: { characterConditionals: {}, lightConeConditionals: {} },
    teammate2: { characterConditionals: {}, lightConeConditionals: {} },
    teammateDynamicConditionals: [],
    conditionalRegistry: {},
    conditionalState: {},
  } as unknown as OptimizerAction

  // --- Context（countTeamPath / ashblazing 敌数 / 公式常量的读口全钉） ---
  const teammateMeta = (path?: string) => path ? { path: path as never } : undefined
  const context = {
    characterId: scenario.character_id,
    characterEidolon: scenario.eidolon ?? 0,
    path: (scenario.self_path ?? '') as never,
    teammate0Metadata: teammateMeta(scenario.teammate_paths?.[0]),
    teammate1Metadata: teammateMeta(scenario.teammate_paths?.[1]),
    teammate2Metadata: teammateMeta(scenario.teammate_paths?.[2]),
    deprioritizeBuffs: false,
    enemyLevel: enemy.level ?? 80,
    enemyCount: enemy.count ?? 1,
    enemyMaxToughness: enemy.max_toughness ?? 0,
    enemyDamageResistance: enemy.damage_resistance ?? 0,
    enemyEffectResistance: enemy.effect_resistance ?? 0,
    enemyWeaknessBroken: enemy.weakness_broken ?? false,
    elementalBreakScaling: scenario.elemental_break_scaling ?? 1,
    baseATK: base.atk ?? 0,
    baseDEF: base.def ?? 0,
    baseHP: base.hp ?? 0,
    baseSPD: base.spd ?? 100,
    // 装备链读口：elementalDamageType（套装 p2c 元素门控——乐队 2pc 族）；
    // characterController/lightConeController（dynamic conditionals 读口——试点
    // 全件无 dynamic，挂上备链，不消费）
    elementalDamageType: ElementToDamage[ELEMENT_DISPLAY[scenario.element] as keyof typeof ElementToDamage],
    characterController: controller,
    lightConeController: lcController,
  } as unknown as OptimizerContext

  // --- hits：actionDefinition 取段 + Phase 2 注册（镜像 actionTransform） ---
  const defs = controller.actionDefinition(action, context) as Record<string, { hits: Hit[] }>
  const def = defs[actionKind]
  if (!def) throw new Error(`no actionDefinition for ${scenario.action}`)
  action.hits = def.hits
  for (let i = 0; i < action.hits!.length; i++) {
    const hit = action.hits![i] as Record<string, unknown>
    hit.localHitIndex = i
    hit.registerIndex = i
    hit.sourceEntityIndex = 0
    hit.scalingEntityIndex = 0
  }
  ;(context as { allActions: OptimizerAction[] }).allActions = [action]
  ;(context as { outputRegistersLength: number }).outputRegistersLength = action.hits!.length

  // --- 实体注册表（单角色链：entityDeclaration/Definition + 白值） ---
  const entityNames: string[] = controller.entityDeclaration()
  const entityDefs = controller.entityDefinition!(action, context) as Record<string, Record<string, unknown>>
  const entities: OptimizerEntity[] = entityNames.map((name) => {
    const def2 = entityDefs[name]
    return {
      name,
      ...def2,
      targetMask: computeTargetMask(def2 as never),
      baseAtk: base.atk ?? 0,
      baseDef: base.def ?? 0,
      baseHp: base.hp ?? 0,
      baseSpd: base.spd ?? 100,
    } as OptimizerEntity
  })
  const registry = new NamedArray(entities, (e) => e.name)

  // --- 容器（无装备 → x.c 空 sets，ashblazing finalizer 自然 no-op；
  //     有遗器 → setsArray/setCounts 按件数铺满，套装基础件真调用） ---
  const config = new ComputedStatsContainerConfig(action, context, registry)
  action.config = config
  const x = new ComputedStatsContainer()
  x.initializeArrays(config.arrayLength, context)
  x.setConfig(config)
  const c = new BasicStatsArrayCore(false)
  x.setBasic(c as never)
  if (setSpecs.length > 0) {
    // setsArray：4 遗器槽按件数铺（件数≤4），余槽填互异未用 index（不成对=不触发）；
    // 位面槽 2 个互异（无位面接入——ornamentMatch2=0）。镜像 calculateSetCounts 口径。
    const slots: number[] = []
    setConfigs.forEach((cfg, i) => {
      const n = Math.min(setSpecs[i].pieces, 4)
      for (let k = 0; k < n; k++) slots.push(cfg.info.index)
    })
    for (let filler = 0; slots.length < 4; filler++) {
      if (!slots.includes(filler)) slots.push(filler)
    }
    slots.push(0, 1)
    c.setsArray = slots
    c.sets = calculateSetCounts(slots)
    // 套装基础件 p2c/p4c（真调用 calculateBasicSetEffects——槽位去重/匹配内部处理）
    calculateBasicSetEffects(c as never, context, c.sets, c.setsArray)
  }

  // --- 条件 buff（镜像 precomputeConditionals：LC 先、角色后——
  //     comboStateTransform.ts:152-156 序） ---
  lcController.precomputeEffectsContainer?.(x, action, context)
  controller.precomputeEffectsContainer?.(x, action, context)
  lcController.precomputeMutualEffectsContainer?.(x, action, context, action)
  controller.precomputeMutualEffectsContainer?.(x, action, context, action)

  // --- 钉死面板写入（终值，action 层实体 0；镜像 transferBaseStats 读口） ---
  const a = x.a
  const elem = ELEMENT_MAP[scenario.element]
  a[StatKey.ATK] += atk.atk ?? 0
  a[StatKey.HP] += atk.hp ?? 0
  a[StatKey.DEF] += atk.def ?? 0
  a[StatKey.SPD] += atk.spd ?? 100
  a[StatKey.CR] += atk.cr ?? 0
  a[StatKey.CD] += atk.cd ?? 0
  a[StatKey.BE] += atk.be ?? 0
  a[StatKey.BOOST] += atk.dmg_boost ?? 0
  if (elem) a[elem.boostKey] += atk.element_boost ?? 0
  a[StatKey.DEF_PEN] += atk.def_pen ?? 0
  a[StatKey.RES_PEN] += atk.res_pen ?? 0
  a[StatKey.VULNERABILITY] += atk.vulnerability ?? 0
  a[StatKey.FINAL_DMG_BOOST] += atk.final_dmg_boost ?? 0
  a[StatKey.EHR] += atk.effect_hit ?? 0

  if (setSpecs.length > 0) {
    // --- 套装基础件 c→x 差额镜像（≡ calculateBaseStats+transferBaseStats 对本场景的
    //     净效果：c 只含套装件——pct 族乘白值、percent/元素直通；钉死面板不含套装件，
    //     差额=套装效果本身） ---
    const ca = c.a
    a[StatKey.ATK] += ca[BasicKey.ATK] + ca[BasicKey.ATK_P] * (base.atk ?? 0)
    a[StatKey.HP] += ca[BasicKey.HP] + ca[BasicKey.HP_P] * (base.hp ?? 0)
    a[StatKey.DEF] += ca[BasicKey.DEF] + ca[BasicKey.DEF_P] * (base.def ?? 0)
    a[StatKey.SPD] += ca[BasicKey.SPD] + ca[BasicKey.SPD_P] * (base.spd ?? 100)
    a[StatKey.CR] += ca[BasicKey.CR]
    a[StatKey.CD] += ca[BasicKey.CD]
    a[StatKey.BE] += ca[BasicKey.BE]
    a[StatKey.EHR] += ca[BasicKey.EHR]
    a[StatKey.RES] += ca[BasicKey.RES]
    a[StatKey.ERR] += ca[BasicKey.ERR]
    a[StatKey.OHB] += ca[BasicKey.OHB]
    a[StatKey.ELATION] += ca[BasicKey.ELATION]
    for (const name of ['PHYSICAL_DMG_BOOST', 'FIRE_DMG_BOOST', 'ICE_DMG_BOOST',
      'LIGHTNING_DMG_BOOST', 'WIND_DMG_BOOST', 'QUANTUM_DMG_BOOST',
      'IMAGINARY_DMG_BOOST'] as const) {
      a[StatKey[name]] += ca[BasicKey[name]]
    }

    // --- 套装条件件 p2x/p4x（executeNonDynamicCombatSets 按套分派镜像——每套至多
    //     装一次、件数 2|4 的形态下与槽位派发逐件等价：2pc 件调 p2x，4pc 追加 p4x） ---
    setConfigs.forEach((cfg, i) => {
      cfg.conditionals.p2x?.(x, context, setConditionals as never)
      if (setSpecs[i].pieces >= 4) cfg.conditionals.p4x?.(x, context, setConditionals as never)
    })
  }

  // --- ATK_P/HP_P/DEF_P/SPD_P → 白值换算（镜像 calculateStats.applyPercentStats；
  //     条件 buff 的百分比件（秘技/E6 族）与套装 p4x 百分比件（大公 4pc 族）在此落为平值） ---
  a[StatKey.ATK] += a[StatKey.ATK_P] * (base.atk ?? 0)
  a[StatKey.HP] += a[StatKey.HP_P] * (base.hp ?? 0)
  a[StatKey.DEF] += a[StatKey.DEF_P] * (base.def ?? 0)
  a[StatKey.SPD] += a[StatKey.SPD_P] * (base.spd ?? 100)

  if (setSpecs.length > 0) {
    // --- 终端套装件（evaluateTerminalSetConditionals 镜像：遗器只调 p4t、位面 p2t——
    //     位面未接入；试点 4 套均无 p4t，挂链备全） ---
    setConfigs.forEach((cfg, i) => {
      if (setSpecs[i].pieces >= 4) cfg.conditionals.p4t?.(x, context, setConditionals as never)
    })
  }

  // --- finalize（镜像 calculateBaseMultis：LC 先、角色后） ---
  lcController.finalizeCalculations?.(x, action, context)
  controller.finalizeCalculations?.(x, action, context)

  // --- 逐 hit 求值 + 乘区读回（对拍显微镜，节点级） ---
  const hits = []
  let total = 0
  for (let i = 0; i < action.hits!.length; i++) {
    const hit = action.hits![i] as Record<string, unknown>
    const dmg = getDamageFunction(hit.damageFunctionType as DamageFunctionType)
      .apply(x, action, i, context)
    total += dmg
    const defPen = x.getValue(StatKey.DEF_PEN, i)
    const resPen = x.getValue(StatKey.RES_PEN, i)
    const cr = Math.min(1, x.getValue(StatKey.CR, i) + x.getValue(StatKey.CR_BOOST, i))
    const cd = x.getValue(StatKey.CD, i) + x.getValue(StatKey.CD_BOOST, i)
    const elemBoostKey = ELEMENT_BOOST_BY_TAG[hit.damageElement as number]
    hits.push({
      damage: dmg,
      damage_function: DamageFunctionType[hit.damageFunctionType as DamageFunctionType],
      atk_scaling: (hit.atkScaling as number) ?? 0,
      hp_scaling: (hit.hpScaling as number) ?? 0,
      def_scaling: (hit.defScaling as number) ?? 0,
      breakdown: {
        baseUniversalMulti: config.enemyWeaknessBroken ? 1 : 0.9,
        defMulti: 100 / ((context.enemyLevel + 20) * Math.max(0, 1 - defPen) + 100),
        resMulti: 1 - (context.enemyDamageResistance - resPen),
        vulnMulti: 1 + x.getValue(StatKey.VULNERABILITY, i),
        finalDmgMulti: 1 + x.getValue(StatKey.FINAL_DMG_BOOST, i),
        dmgBoostMulti: 1 + x.getValue(StatKey.BOOST, i)
          + (elemBoostKey ? x.getValue(elemBoostKey, i) : 0),
        abilityMulti: ((hit.atkScaling as number) ?? 0) * x.getValue(StatKey.ATK, i)
          + ((hit.hpScaling as number) ?? 0) * x.getValue(StatKey.HP, i)
          + ((hit.defScaling as number) ?? 0) * x.getValue(StatKey.DEF, i),
        critMulti: cr * (1 + cd) + (1 - cr),
      },
    })
  }

  // --- 面板回显（钉错面板/行迹平铺的第一道闸） ---
  const stats = {
    atk: x.getValue(StatKey.ATK, 0),
    hp: x.getValue(StatKey.HP, 0),
    def: x.getValue(StatKey.DEF, 0),
    spd: x.getValue(StatKey.SPD, 0),
    cr: x.getValue(StatKey.CR, 0) + x.getValue(StatKey.CR_BOOST, 0),
    cd: x.getValue(StatKey.CD, 0) + x.getValue(StatKey.CD_BOOST, 0),
    be: x.getValue(StatKey.BE, 0),
    dmg_boost: x.getValue(StatKey.BOOST, 0),
    element_boost: elem ? x.getValue(elem.boostKey, 0) : 0,
    def_pen: x.getValue(StatKey.DEF_PEN, 0),
    vulnerability: x.getValue(StatKey.VULNERABILITY, 0),
    final_dmg_boost: x.getValue(StatKey.FINAL_DMG_BOOST, 0),
  }

  return { total, hits, stats }
}

const scenario = JSON.parse(readFileSync(0, 'utf8')) as Scenario
process.stdout.write(JSON.stringify(
  scenario.kind === 'character' ? runCharacter(scenario) : run(scenario),
))
