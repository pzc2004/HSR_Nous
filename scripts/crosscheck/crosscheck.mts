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
 *   },
 *   "teammates": [                                             // 可选——组队级对拍扩展（队友 buff 跨 actor 传导）
 *     { "character_id": "1403", "eidolon": 0,                  // 真队友：注册表查控制器
 *       "path": "Harmony", "element": "quantum",               //   countTeamPath/Element 元数据口径
 *       "conditionals": { ...覆盖 teammateDefaults()... } },   //   开关落点 = teammateContent
 *     { "path": "Nihility" }                                   // path-only 占位：无 buff 链，
 *   ]                                                          //   只进 countTeamPath 元数据
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
 * 队友链口径（teammates 块；无 teammates 时行为与 L2/装备级逐字节一致）：
 * - 镜像 comboStateTransform.precomputeConditionals → precomputeTeammates：队友
 *   initializeTeammateConfigurationsContainer（主 precompute 之前）→ 主 LC/角色
 *   effects → 主 LC/角色 mutual → 逐队友（槽位序）precomputeMutualEffectsContainer
 *   (x, teammateAction, context, 主 action) + precomputeTeammateEffectsContainer。
 *   队友 buff 落点 = 主角色容器 x（FullTeam targets 含实体 0——队友条件 buff 折叠
 *   进主 C 面板的对方原生口径）。
 * - teammateAction.characterConditionals = controller.teammateDefaults() 铺底 +
 *   场景覆盖（映射表的对方侧落点）；teammateContent 键集 ⊂ defaults() 键集
 *   （对方控制器 precomputeMutual 读的就是 teammateAction——本驱动按原样喂）。
 * - 队友 action 共享主 config（comboStateTransform.ts:180 原生口径）——
 *   initializeTeammateConfigurationsContainer 的写件（PermansorTerrae bondmate →
 *   hasSummons=true）与同队 mutual 的读件（Sunday 召唤物增伤档读 hasSummons）
 *   经同一对象传导；缺省按实体表推算（主 C 自带召唤物实体时为 true）。
 * - 队友星魂在控制器构造时钉死（conditionals(e, false)——E1/E4 族门控读闭包 e）。
 * - 队友光锥/遗器未接入（矩阵无实例垫底——需要时按 precomputeTeammates 内 LC
 *   mutual/teammateEffects 与 getTeammateOption 套装槽补镜像）。
 * - context.teammateNMetadata 由 teammates 块生成（path/element 进 countTeamPath/
 *   countTeamElement）；无 teammates 时回落旧 teammate_paths（path-only 占位等价）。
 * ---------------------------------------------------------------------------
 * 忆灵扩拍（2026-09-17 记忆战舰波）新增镜像：
 * - action："memo_skill"|"memo_talent"|"skill_heal"|"ult_heal"（对方 AbilityKind 同名键；
  *   忆灵技/忆灵天赋/治疗行动的 actionDefinition 取段同构）。
 * - hit 实体解析：sourceEntity/scalingEntity 名 → 索引（镜像 actionTransform Phase 3，
  *   scalingEntityIndex 缺省回落 sourceEntityIndex）——跨实体缩放段（死龙打遐蝶 HP 基数）
  *   不再恒 0；实体白值镜像 computeEntityBaseStats（memosprite = scaling×角色白值）。
 * - 忆灵面板镜像（calculateMemospriteBaseStats）：钉死面板写实体 0 后，忆灵实体
  *   ATK/DEF/HP/SPD = scaling×钉死值 + flat，CR/CD/BE/EHR/主元素增伤照钉死值继承
  *   （真实管线 transferBaseStats 只铺 SelfAndPet，Pet≠Memosprite）。
 * - applyPercentStats 忆灵分支：百分比件 × 忆灵自身白值（全队 HP_P 族落忆灵段用）。
 * - dynamic conditionals 镜像（evaluateDynamicConditionals：applyPercentStats 后、
  *   终端套装件前，角色→LC 序直调 condition+effect）——长夜月战技光环（忆灵暴伤
  *   换算）/风堇速度档（>200 生命+超档治疗量）等动态件通道。
 * - 命中寄存器回写：逐 hit 伤害后 setHitRegisterValue（镜像 optimizerWorker.ts:283）
  *   ——HealTally/引用段族（风堇 tally 直写基数）唯一读口。
 * - 输出增列：hits[].source_entity（段实体归属回显）、entity_stats（多实体场逐实体
  *   面板回显——忆灵面板归属/继承钉错的第一道闸）。
 * ---------------------------------------------------------------------------
 * 欢愉扩拍（2026-09-17 欢愉波）新增镜像：
 * - action："elation_skill"|"unique"（对方 AbilityKind 同名键——欢愉技/专属技
 *   （银狼999 Top Loot Box、绯英狐狸老师 FUA 住 UNIQUE）actionDefinition 取段同构）。
 * - 欢愉双键钉面板：ELATION（欢愉度——(1+elation) 乘区读口）/MERRYMAKING（增笑）
 *   写入钉死面板（formula 层 run() 早有槽位，L2 同槽补写），stats 回显同增两键。
 * - hits[] 回显增列：elation_scaling/punchline_stacks（全段型恒 0 占位），欢愉段
 *   breakdown 增 elationMulti（含 minElationOverride 择优槽——爻光大吉大利队友链
 *   "攻击者欢愉度低于爻光则用爻光的"）/merrymakeMulti/punchlineMulti。
 * - context.baseEnergy 场景槽（base_energy 键）：绯英天赋终结技笑点地板
 *   max(baseEnergy, CB) 读口（官方=能量上限 max_sp——480≠耗能 240 在案）。
 * - actionModifiers 镜像（actionTransform Phase 1 原位：actionDefinition 之后、索引
 *   注册之前；主角色件先行、队友件槽位序——ModifierContext 同 buildModifierContext
 *   口径）：爻光大吉大利（向 directHit 行动追加欢愉段，段元素=攻击者、笑点=触发者
 *   好活当赏择优）唯一挂点；其余在册角色 actionModifiers 全空（逐件核实——火花/
 *   绯英/银狼999/欢愉开拓者/记忆战舰 12 件皆 () => []），空挂零行为差。
 * ---------------------------------------------------------------------------
 * 老角色扫荡②扩拍（2026-09-18，tests/test_crosscheck_legacy_1200.py）新增镜像：
 * - enemy.elemental_weak 场景槽 → context.enemyElementalWeak（彦卿 Icing 追加段/
 *   托帕 A4 金融动荡 BOOST/饮月 CD 族的读口——driver 此前无槽恒 false 无落点）。
 * - 召唤物（pet，非忆灵）面板镜像：钉死面板 + applyPercentStats 双段补 SelfAndPet
 *   的 Pet 侧（镜像 calculateStats.transferBaseStats/applyPercentStats 的
 *   entityBaseOffsets[SelfAndPet] 循环——账账族召唤物继承主角色战斗面板含条件
 *   buff；忆灵走 memosprite 专用镜像不重复铺）。托帕 1112 为首实例（账账 pet）。
 * ---------------------------------------------------------------------------
 * 老角色扫荡③扩拍（2026-09-18，tests/test_crosscheck_legacy_1300.py）新增镜像：
 * - 主 LC/角色 initializeConfigurationsContainer（comboStateTransform.ts:126-127
 *   原位：队友 initialize 与主 effects 之前）——FireflyB1 超击破档（superBreakDmg
 *   → config.enemyWeaknessBroken=true，baseUniversal/击破易伤门控读口）首实例。
 * ---------------------------------------------------------------------------
 */

import { readFileSync } from 'node:fs'

import { Acheron } from 'lib/conditionals/character/1300/Acheron'
import { Aventurine } from 'lib/conditionals/character/1300/Aventurine'
import { DrRatio } from 'lib/conditionals/character/1300/DrRatio'
import { Sunday } from 'lib/conditionals/character/1300/Sunday'
import { Herta } from 'lib/conditionals/character/1000/Herta'
// --- 名册扩拍老角色批量扫荡① 1000-1100 号段（tests/test_crosscheck_legacy_1000.py） ---
import { Arlan } from 'lib/conditionals/character/1000/Arlan'
import { Asta } from 'lib/conditionals/character/1000/Asta'
import { Himeko } from 'lib/conditionals/character/1000/Himeko'
import { Bronya } from 'lib/conditionals/character/1100/Bronya'
import { Gepard } from 'lib/conditionals/character/1100/Gepard'
import { Hook } from 'lib/conditionals/character/1100/Hook'
import { Luka } from 'lib/conditionals/character/1100/Luka'
import { Natasha } from 'lib/conditionals/character/1100/Natasha'
import { Pela } from 'lib/conditionals/character/1100/Pela'
import { Sampo } from 'lib/conditionals/character/1100/Sampo'
import { Serval } from 'lib/conditionals/character/1100/Serval'
import { Bailu } from 'lib/conditionals/character/1200/Bailu'
// --- 老角色批量扫荡② 1100-1200 号段续波（tests/test_crosscheck_legacy_1200.py） ---
import { Qingque } from 'lib/conditionals/character/1200/Qingque'
import { Sushang } from 'lib/conditionals/character/1200/Sushang'
import { Tingyun } from 'lib/conditionals/character/1200/Tingyun'
import { Yanqing } from 'lib/conditionals/character/1200/Yanqing'
// --- 老角色扫荡① 续：加强版（B1）套件——现役版建模（1006 银狼 11006xx/1004 瓦尔特） ---
import { SilverWolfB1 } from 'lib/conditionals/character/1000/SilverWolfB1'
import { WeltB1 } from 'lib/conditionals/character/1000/WeltB1'
// --- 老角色扫荡② 续：1107 克拉拉/1112 托帕（召唤物双实体）/1005 卡芙卡 B1 ---
import { Clara } from 'lib/conditionals/character/1100/Clara'
import { Topaz } from 'lib/conditionals/character/1100/Topaz'
import { KafkaB1 } from 'lib/conditionals/character/1000/KafkaB1'
// --- 老角色批量扫荡③（tests/test_crosscheck_legacy_1300.py）：1212 镜流 B1/1213 饮月/
//     1205 刃 B1/1208 符玄/1203 罗刹/1217 藿藿 B1/1302 银枝/1303 阮•梅 ---
import { JingliuB1 } from 'lib/conditionals/character/1200/JingliuB1'
import { ImbibitorLunae } from 'lib/conditionals/character/1200/ImbibitorLunae'
import { BladeB1 } from 'lib/conditionals/character/1200/BladeB1'
import { FuXuan } from 'lib/conditionals/character/1200/FuXuan'
import { Luocha } from 'lib/conditionals/character/1200/Luocha'
import { HuohuoB1 } from 'lib/conditionals/character/1200/HuohuoB1'
import { Argenti } from 'lib/conditionals/character/1300/Argenti'
import { RuanMei } from 'lib/conditionals/character/1300/RuanMei'
import { SparkleB1 } from 'lib/conditionals/character/1300/SparkleB1'
import { FireflyB1 } from 'lib/conditionals/character/1300/FireflyB1'
import { Castorice } from 'lib/conditionals/character/1400/Castorice'
import { Cerydra } from 'lib/conditionals/character/1400/Cerydra'
import { Cyrene } from 'lib/conditionals/character/1400/Cyrene'
import { Evernight } from 'lib/conditionals/character/1400/Evernight'
import { Hyacine } from 'lib/conditionals/character/1400/Hyacine'
import { PermansorTerrae } from 'lib/conditionals/character/1400/PermansorTerrae'
import { Phainon } from 'lib/conditionals/character/1400/Phainon'
import { Tribbie } from 'lib/conditionals/character/1400/Tribbie'
// --- 名册扩拍欢愉波（tests/test_crosscheck_elation.py）：1500 号段欢愉族 + 欢愉开拓者 ---
import { Evanescia } from 'lib/conditionals/character/1500/Evanescia'
// --- 名册扩拍 1500 混编波（tests/test_crosscheck_1500.py）：1510/1507/1508/1509/1504 ---
import { Ashveil } from 'lib/conditionals/character/1500/Ashveil'
import { Gilgamesh } from 'lib/conditionals/character/1500/Gilgamesh'
import { HimekoNova } from 'lib/conditionals/character/1500/HimekoNova'
import { MortenaxBlade } from 'lib/conditionals/character/1500/MortenaxBlade'
import { RinTohsaka } from 'lib/conditionals/character/1500/RinTohsaka'
import { SilverWolfLv999 } from 'lib/conditionals/character/1500/SilverWolfLv999'
import { Sparxie } from 'lib/conditionals/character/1500/Sparxie'
import { Yaoguang } from 'lib/conditionals/character/1500/Yaoguang'
import {
  TrailblazerElationCaelus,
  TrailblazerElationStelle,
} from 'lib/conditionals/character/8000/TrailblazerElation'
import { BaptismOfPureThought } from 'lib/conditionals/lightcone/5star/BaptismOfPureThought'
import { IncessantRain } from 'lib/conditionals/lightcone/5star/IncessantRain'
import { InTheNight } from 'lib/conditionals/lightcone/5star/InTheNight'
import { NightOnTheMilkyWay } from 'lib/conditionals/lightcone/5star/NightOnTheMilkyWay'
import { GoodNightAndSleepWell } from 'lib/conditionals/lightcone/4star/GoodNightAndSleepWell'
import { TheSeriousnessOfBreakfast } from 'lib/conditionals/lightcone/4star/TheSeriousnessOfBreakfast'
// --- 名册批量扫荡波（tests/test_crosscheck_equipment_batch.py）：3star ---
import { DartingArrow } from 'lib/conditionals/lightcone/3star/DartingArrow'
import { DataBank } from 'lib/conditionals/lightcone/3star/DataBank'
import { Loop } from 'lib/conditionals/lightcone/3star/Loop'
import { MutualDemise } from 'lib/conditionals/lightcone/3star/MutualDemise'
import { Sagacity } from 'lib/conditionals/lightcone/3star/Sagacity'
// --- 名册批量扫荡波：4star ---
import { ASecretVow } from 'lib/conditionals/lightcone/4star/ASecretVow'
import { ATrailOfBygoneBlood } from 'lib/conditionals/lightcone/4star/ATrailOfBygoneBlood'
import { Fermata } from 'lib/conditionals/lightcone/4star/Fermata'
import { FinalVictor } from 'lib/conditionals/lightcone/4star/FinalVictor'
import { GeniusesRepose } from 'lib/conditionals/lightcone/4star/GeniusesRepose'
import { MakeTheWorldClamor } from 'lib/conditionals/lightcone/4star/MakeTheWorldClamor'
import { NowhereToRun } from 'lib/conditionals/lightcone/4star/NowhereToRun'
import { OnlySilenceRemains } from 'lib/conditionals/lightcone/4star/OnlySilenceRemains'
import { ResolutionShinesAsPearlsOfSweat } from 'lib/conditionals/lightcone/4star/ResolutionShinesAsPearlsOfSweat'
import { SubscribeForMore } from 'lib/conditionals/lightcone/4star/SubscribeForMore'
import { Swordplay } from 'lib/conditionals/lightcone/4star/Swordplay'
import { TheBirthOfTheSelf } from 'lib/conditionals/lightcone/4star/TheBirthOfTheSelf'
import { UnderTheBlueSky } from 'lib/conditionals/lightcone/4star/UnderTheBlueSky'
// --- 名册批量扫荡波：5star ---
import { BeforeDawn } from 'lib/conditionals/lightcone/5star/BeforeDawn'
import { CruisingInTheStellarSea } from 'lib/conditionals/lightcone/5star/CruisingInTheStellarSea'
import { EternalCalculus } from 'lib/conditionals/lightcone/5star/EternalCalculus'
import { InTheNameOfTheWorld } from 'lib/conditionals/lightcone/5star/InTheNameOfTheWorld'
import { MemorysCurtainNeverFalls } from 'lib/conditionals/lightcone/5star/MemorysCurtainNeverFalls'
import { OnTheFallOfAnAeon } from 'lib/conditionals/lightcone/5star/OnTheFallOfAnAeon'
import { PatienceIsAllYouNeed } from 'lib/conditionals/lightcone/5star/PatienceIsAllYouNeed'
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
  elemental_weak?: boolean     // kind=character：敌方对本行动元素弱（context.enemyElementalWeak——
                               //   彦卿 Icing 追加段/饮月 CD/托帕 A4 BOOST 的读口，默认 false）
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
    | 'memo_skill' | 'memo_talent' | 'skill_heal' | 'ult_heal'
    | 'elation_skill' | 'unique'
  conditionals?: Record<string, number | boolean>
  base?: { atk?: number, hp?: number, def?: number, spd?: number }
  base_energy?: number                     // context.baseEnergy（绯英天赋终结技笑点地板
                                           //   max(baseEnergy, CB) 读口——官方=max_sp）
  self_path?: string
  teammate_paths?: string[]
  elemental_break_scaling?: number
  equipment?: EquipmentSpec
  teammates?: TeammateSpec[]
}

// --- 队友块（kind=character 可选；链路口径见文件头注） ---
interface TeammateSpec {
  character_id?: string                           // 真队友（注册表查控制器）；缺省 = path-only 元数据占位
  eidolon?: number
  path: string                                    // countTeamPath 口径
  element?: ElementName                           // countTeamElement 口径（可缺省）
  conditionals?: Record<string, number | boolean> // 覆盖 teammateDefaults()
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
  memo_skill: AbilityKind.MEMO_SKILL,
  memo_talent: AbilityKind.MEMO_TALENT,
  skill_heal: AbilityKind.SKILL_HEAL,
  ult_heal: AbilityKind.ULT_HEAL,
  // --- 老角色扫荡波（2026-09-17）：DoT 技种（希露瓦/艾丝妲触电段——standardDot 取段同构） ---
  dot: AbilityKind.DOT,
  // --- 欢愉波（2026-09-17）：欢愉技/专属技（银狼999 Top Loot Box、绯英狐狸老师 FUA） ---
  elation_skill: AbilityKind.ELATION_SKILL,
  unique: AbilityKind.UNIQUE,
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
  [Tribbie.id]: Tribbie as never,
  [Aventurine.id]: Aventurine as never,
  [Phainon.id]: Phainon as never,
  [Cerydra.id]: Cerydra as never,
  [Sunday.id]: Sunday as never,
  [PermansorTerrae.id]: PermansorTerrae as never,
  [Castorice.id]: Castorice as never,
  [Evernight.id]: Evernight as never,
  [Hyacine.id]: Hyacine as never,
  [Cyrene.id]: Cyrene as never,
  // --- 名册扩拍欢愉波（1500 号段欢愉族 + 欢愉双子；1504/1507/1508/1509/1510 非欢愉不拍） ---
  [Sparxie.id]: Sparxie as never,
  [Yaoguang.id]: Yaoguang as never,
  [Evanescia.id]: Evanescia as never,
  [SilverWolfLv999.id]: SilverWolfLv999 as never,
  [TrailblazerElationCaelus.id]: TrailblazerElationCaelus as never,
  [TrailblazerElationStelle.id]: TrailblazerElationStelle as never,
  // --- 名册扩拍 1500 混编波（智识/虚无/毁灭/巡猎——上条注释「非欢愉不拍」本波收回） ---
  [HimekoNova.id]: HimekoNova as never,
  [MortenaxBlade.id]: MortenaxBlade as never,
  [RinTohsaka.id]: RinTohsaka as never,
  [Gilgamesh.id]: Gilgamesh as never,
  [Ashveil.id]: Ashveil as never,
  // --- 名册扩拍老角色批量扫荡①（1000-1100 号段——1102 希儿对方 stub 壳不拍） ---
  [Arlan.id]: Arlan as never,
  [Asta.id]: Asta as never,
  [Himeko.id]: Himeko as never,
  [Bronya.id]: Bronya as never,
  [Gepard.id]: Gepard as never,
  [Hook.id]: Hook as never,
  [Luka.id]: Luka as never,
  [Natasha.id]: Natasha as never,
  [Pela.id]: Pela as never,
  [Sampo.id]: Sampo as never,
  [Serval.id]: Serval as never,
  [Bailu.id]: Bailu as never,
  // --- 老角色扫荡① 续：B1 加强版套件（我方 fixture=现役加强版——1006 单轨 11006xx 先例） ---
  [SilverWolfB1.id]: SilverWolfB1 as never,
  [WeltB1.id]: WeltB1 as never,
  // --- 老角色批量扫荡②（1100-1200 号段续波——停云/素裳/彦卿/青雀/克拉拉/托帕/卡芙卡B1） ---
  [Tingyun.id]: Tingyun as never,
  [Sushang.id]: Sushang as never,
  [Yanqing.id]: Yanqing as never,
  [Qingque.id]: Qingque as never,
  [Clara.id]: Clara as never,
  [Topaz.id]: Topaz as never,
  [KafkaB1.id]: KafkaB1 as never,
  // --- 老角色批量扫荡③（1200-1300 号段——镜流/刃/藿藿按对方 B1 id 直呼，
  //     我方 fixture=现役加强版 1121xxx/1120xxx/11217xx 轨，1005b1/1004b1 先例） ---
  [JingliuB1.id]: JingliuB1 as never,
  [ImbibitorLunae.id]: ImbibitorLunae as never,
  [BladeB1.id]: BladeB1 as never,
  [FuXuan.id]: FuXuan as never,
  [Luocha.id]: Luocha as never,
  [HuohuoB1.id]: HuohuoB1 as never,
  [Argenti.id]: Argenti as never,
  [RuanMei.id]: RuanMei as never,
  [SparkleB1.id]: SparkleB1 as never,
  [FireflyB1.id]: FireflyB1 as never,
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
  // --- 名册批量扫荡波（25 件：输出专光/条件增伤/叠层/对敌 debuff/能量/面板族） ---
  [DartingArrow.id]: DartingArrow as never,
  [DataBank.id]: DataBank as never,
  [Loop.id]: Loop as never,
  [MutualDemise.id]: MutualDemise as never,
  [Sagacity.id]: Sagacity as never,
  [ASecretVow.id]: ASecretVow as never,
  [ATrailOfBygoneBlood.id]: ATrailOfBygoneBlood as never,
  [Fermata.id]: Fermata as never,
  [FinalVictor.id]: FinalVictor as never,
  [GeniusesRepose.id]: GeniusesRepose as never,
  [MakeTheWorldClamor.id]: MakeTheWorldClamor as never,
  [NowhereToRun.id]: NowhereToRun as never,
  [OnlySilenceRemains.id]: OnlySilenceRemains as never,
  [ResolutionShinesAsPearlsOfSweat.id]: ResolutionShinesAsPearlsOfSweat as never,
  [SubscribeForMore.id]: SubscribeForMore as never,
  [Swordplay.id]: Swordplay as never,
  [TheBirthOfTheSelf.id]: TheBirthOfTheSelf as never,
  [UnderTheBlueSky.id]: UnderTheBlueSky as never,
  [BeforeDawn.id]: BeforeDawn as never,
  [CruisingInTheStellarSea.id]: CruisingInTheStellarSea as never,
  [EternalCalculus.id]: EternalCalculus as never,
  [InTheNameOfTheWorld.id]: InTheNameOfTheWorld as never,
  [MemorysCurtainNeverFalls.id]: MemorysCurtainNeverFalls as never,
  [OnTheFallOfAnAeon.id]: OnTheFallOfAnAeon as never,
  [PatienceIsAllYouNeed.id]: PatienceIsAllYouNeed as never,
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

  // --- 队友：teammates 块（真队友查控制器 + path-only 占位）或旧 teammate_paths
  //     （path-only 等价）——teammateAction.characterConditionals = teammateDefaults()
  //     铺底 + 场景覆盖；队友星魂在控制器构造时钉死 ---
  type TeammateController = {
    teammateDefaults: () => Record<string, number | boolean>
    initializeTeammateConfigurationsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void
    precomputeMutualEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext, s: OptimizerAction) => void
    precomputeTeammateEffectsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext, s: OptimizerAction) => void
  }
  const rawTeammates: TeammateSpec[] = scenario.teammates
    ?? (scenario.teammate_paths ?? []).map((p) => ({ path: p }))
  const teammates = rawTeammates.slice(0, 3).map((spec) => {
    let tmController: TeammateController | undefined
    let tmConditionals: Record<string, number | boolean> = {}
    if (spec.character_id) {
      const tmConfig = CHARACTER_REGISTRY[spec.character_id]
      if (!tmConfig) throw new Error(`teammate not registered: ${spec.character_id}`)
      tmController = tmConfig.conditionals(spec.eidolon ?? 0, false) as TeammateController
      tmConditionals = { ...tmController.teammateDefaults(), ...(spec.conditionals ?? {}) }
    }
    const tmAction = {
      actorId: spec.character_id ?? '',
      actorEidolon: spec.eidolon ?? 0,
      characterConditionals: tmConditionals,
      lightConeConditionals: {},
    } as unknown as OptimizerAction
    return { spec, controller: tmController, action: tmAction, conditionals: tmConditionals }
  })

  // --- Action（只填角色链实际读的字段，其余 cast） ---
  const action = {
    actionType: actionKind,
    actionKind,
    actorId: scenario.character_id,
    actorEidolon: scenario.eidolon ?? 0,
    characterConditionals: conditionals,
    lightConeConditionals: lcConditionals,
    setConditionals,
    // 队友槽（镜像 defineAction——actorId/星魂/条件字典落位；无队友槽保持空壳）
    teammate0: teammates[0]
      ? { actorId: teammates[0].spec.character_id ?? '', actorEidolon: teammates[0].spec.eidolon ?? 0,
          characterConditionals: teammates[0].conditionals, lightConeConditionals: {} }
      : { characterConditionals: {}, lightConeConditionals: {} },
    teammate1: teammates[1]
      ? { actorId: teammates[1].spec.character_id ?? '', actorEidolon: teammates[1].spec.eidolon ?? 0,
          characterConditionals: teammates[1].conditionals, lightConeConditionals: {} }
      : { characterConditionals: {}, lightConeConditionals: {} },
    teammate2: teammates[2]
      ? { actorId: teammates[2].spec.character_id ?? '', actorEidolon: teammates[2].spec.eidolon ?? 0,
          characterConditionals: teammates[2].conditionals, lightConeConditionals: {} }
      : { characterConditionals: {}, lightConeConditionals: {} },
    teammateDynamicConditionals: [],
    conditionalRegistry: {},
    conditionalState: {},
  } as unknown as OptimizerAction

  // --- Context（countTeamPath / ashblazing 敌数 / 公式常量的读口全钉） ---
  const teammateMeta = (spec?: TeammateSpec) => spec
    ? {
      characterId: (spec.character_id ?? '') as never,
      characterEidolon: spec.eidolon ?? 0,
      lightCone: '', lightConeSuperimposition: 1,
      lightConePath: spec.path as never,
      path: spec.path as never,
      element: (spec.element ? ELEMENT_DISPLAY[spec.element] : '') as never,
    }
    : undefined
  const context = {
    characterId: scenario.character_id,
    characterEidolon: scenario.eidolon ?? 0,
    path: (scenario.self_path ?? '') as never,
    teammate0Metadata: teammateMeta(rawTeammates[0]),
    teammate1Metadata: teammateMeta(rawTeammates[1]),
    teammate2Metadata: teammateMeta(rawTeammates[2]),
    deprioritizeBuffs: false,
    enemyLevel: enemy.level ?? 80,
    enemyCount: enemy.count ?? 1,
    enemyMaxToughness: enemy.max_toughness ?? 0,
    enemyDamageResistance: enemy.damage_resistance ?? 0,
    enemyEffectResistance: enemy.effect_resistance ?? 0,
    enemyWeaknessBroken: enemy.weakness_broken ?? false,
    enemyElementalWeak: enemy.elemental_weak ?? false,   // 元素弱点槽（彦卿/托帕 A4 族读口）
    elementalBreakScaling: scenario.elemental_break_scaling ?? 1,
    baseATK: base.atk ?? 0,
    baseDEF: base.def ?? 0,
    baseHP: base.hp ?? 0,
    baseSPD: base.spd ?? 100,
    baseEnergy: scenario.base_energy ?? 0,   // 绯英天赋终结技笑点地板（max(baseEnergy,CB)）
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

  // --- actionModifiers 镜像（actionTransform Phase 1：actionDefinition 之后、索引注册
  //     之前——主角色件先行、队友件槽位序追加；爻光大吉大利（Great Boon 向 directHit
  //     行动附欢愉段）唯一挂点。ModifierContext 镜像 buildModifierContext：主 =
  //     action.characterConditionals；队友 = 槽位 characterConditionals） ---
  for (const modifier of controller.actionModifiers?.() ?? []) {
    modifier.modify(action, context, {
      characterId: scenario.character_id as never,
      eidolon: scenario.eidolon ?? 0,
      isTeammate: false,
      ownConditionals: conditionals,
      ownLightConeConditionals: lcConditionals,
    })
  }
  for (const tm of teammates) {
    if (!tm.controller) continue
    for (const modifier of (tm.controller as {
      actionModifiers?: () => { modify: (a: OptimizerAction, c: OptimizerContext, s: never) => void }[]
    }).actionModifiers?.() ?? []) {
      modifier.modify(action, context, {
        characterId: (tm.spec.character_id ?? '') as never,
        eidolon: tm.spec.eidolon ?? 0,
        isTeammate: true,
        ownConditionals: tm.conditionals,
        ownLightConeConditionals: {},
      } as never)
    }
  }
  ;(context as { allActions: OptimizerAction[] }).allActions = [action]
  ;(context as { outputRegistersLength: number }).outputRegistersLength = action.hits!.length

  // --- 实体注册表（单角色链：entityDeclaration/Definition + 白值） ---
  const entityNames: string[] = controller.entityDeclaration()
  const entityDefs = controller.entityDefinition!(action, context) as Record<string, Record<string, unknown>>
  const entities: OptimizerEntity[] = entityNames.map((name) => {
    const def2 = entityDefs[name]
    // 镜像 actionTransform.computeEntityBaseStats：memosprite 实体白值 = scaling×角色白值
    // （flat 件不进 base——calculateMemospriteBaseStats 的平值槽；applyPercentStats 的
    // memo 分支百分比换算基数读的就是本白值）
    const memo = def2.memosprite === true
    return {
      name,
      ...def2,
      targetMask: computeTargetMask(def2 as never),
      baseAtk: memo ? ((def2.memoBaseAtkScaling as number) ?? 0) * (base.atk ?? 0) : (base.atk ?? 0),
      baseDef: memo ? ((def2.memoBaseDefScaling as number) ?? 0) * (base.def ?? 0) : (base.def ?? 0),
      baseHp: memo ? ((def2.memoBaseHpScaling as number) ?? 0) * (base.hp ?? 0) : (base.hp ?? 0),
      baseSpd: memo ? ((def2.memoBaseSpdScaling as number) ?? 0) * (base.spd ?? 100) : (base.spd ?? 100),
    } as OptimizerEntity
  })
  const registry = new NamedArray(entities, (e) => e.name)

  // --- hit 实体解析（镜像 actionTransform Phase 3：sourceEntity/scalingEntity 名 → 索引；
  //     scalingEntityIndex 缺省回落 sourceEntityIndex——忆灵技跨实体缩放（死龙打遐蝶 HP
  //     基数族）的唯一通道，旧版恒 0 会把跨实体段读错人） ---
  for (let i = 0; i < action.hits!.length; i++) {
    const hit = action.hits![i] as Record<string, unknown>
    hit.localHitIndex = i
    hit.registerIndex = i
    hit.sourceEntityIndex = hit.sourceEntity
      ? registry.getIndex(hit.sourceEntity as string)
      : 0
    hit.scalingEntityIndex = hit.scalingEntity
      ? registry.getIndex(hit.scalingEntity as string)
      : hit.sourceEntityIndex
  }

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

  // --- 主 LC/角色 initializeConfigurationsContainer（镜像 comboStateTransform.ts:126-127：
  //     LC 先、角色后，位置在队友 initialize 与主 effects 之前——FireflyB1 超击破档
  //     （superBreakDmg → config.enemyWeaknessBroken=true，baseUniversal/击破易伤门控读口）
  //     首实例；其余在册主控制器此件全空/no-op（逐件核实：Luocha/HuohuoB1 空壳） ---
  ;(lcController as { initializeConfigurationsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void })
    .initializeConfigurationsContainer?.(x, action, context)
  ;(controller as { initializeConfigurationsContainer?: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void })
    .initializeConfigurationsContainer?.(x, action, context)

  // --- 队友 initializeTeammateConfigurationsContainer（镜像 precomputeConditionals
  //     序：主 initialize → 队友 initialize → 主 effects；试点队友均无此件，挂链备全） ---
  // 队友 action 共享主 config（镜像 comboStateTransform.ts:180 teammateAction.config =
  // action.config）——PermansorTerrae initialize 写 hasSummons（bondmate→召唤物在队）、
  // Sunday mutual 读 hasSummons（召唤物增伤档），两件的落点都是这一共享对象
  for (const tm of teammates) {
    ;(tm.action as { config?: ComputedStatsContainerConfig }).config = config
    tm.controller?.initializeTeammateConfigurationsContainer?.(x, tm.action, context)
  }

  // --- 条件 buff（镜像 precomputeConditionals：LC 先、角色后——
  //     comboStateTransform.ts:152-156 序） ---
  lcController.precomputeEffectsContainer?.(x, action, context)
  controller.precomputeEffectsContainer?.(x, action, context)
  lcController.precomputeMutualEffectsContainer?.(x, action, context, action)
  controller.precomputeMutualEffectsContainer?.(x, action, context, action)

  // --- 队友 mutual/teammateEffects（镜像 precomputeTeammates：槽位序，第 4 参 =
  //     主 action；队友 buff 落主角色容器 x——FullTeam 折叠进主 C 的原生口径） ---
  for (const tm of teammates) {
    tm.controller?.precomputeMutualEffectsContainer?.(x, tm.action, context, action)
    tm.controller?.precomputeTeammateEffectsContainer?.(x, tm.action, context, action)
  }

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
  // 欢愉双键（欢愉波——AttackerSpec 早有槽位，L2 钉死面板同槽补写；ELATION=欢愉度
  // 面板（等级系数路由的 (1+elation) 乘区读口）、MERRYMAKING=增笑面板）
  a[StatKey.ELATION] += atk.elation ?? 0
  a[StatKey.MERRYMAKING] += atk.merrymaking ?? 0

  // --- 召唤物（pet/summon，非忆灵）面板镜像（calculateStats.transferBaseStats 的
  //     SelfAndPet 段：真实管线把 c.a 基础面板铺满 Self|Pet 全体——账账族召唤物继承
  //     主角色战斗面板；忆灵走下方 calculateMemospriteBaseStats 专用镜像不重复铺） ---
  for (let ei = 1; ei < entities.length; ei++) {
    const ent = entities[ei] as Record<string, unknown>
    if (ent.pet !== true) continue
    const o = x.getActionIndex(ei, 0)
    a[o + StatKey.ATK] += atk.atk ?? 0
    a[o + StatKey.HP] += atk.hp ?? 0
    a[o + StatKey.DEF] += atk.def ?? 0
    a[o + StatKey.SPD] += atk.spd ?? 100
    a[o + StatKey.CR] += atk.cr ?? 0
    a[o + StatKey.CD] += atk.cd ?? 0
    a[o + StatKey.BE] += atk.be ?? 0
    a[o + StatKey.EHR] += atk.effect_hit ?? 0
    if (elem) a[o + elem.boostKey] += atk.element_boost ?? 0
  }

  // --- 忆灵面板镜像（calculateStats.calculateMemospriteBaseStats：真实管线里
  //     transferBaseStats 只铺 SelfAndPet（Pet≠Memosprite），忆灵实体走本函数——
  //     ATK/DEF/HP/SPD = scaling×主面板 + flat，CR/CD/BE/EHR/RES/ERR/OHB/元素增伤
  //     照主面板继承。钉死面板等价于 c.a 满配口径，故用钉死值做基数） ---
  for (let ei = 1; ei < entities.length; ei++) {
    const ent = entities[ei] as Record<string, unknown>
    if (ent.memosprite !== true) continue
    const o = x.getActionIndex(ei, 0)
    a[o + StatKey.ATK] += ((ent.memoBaseAtkScaling as number) ?? 0) * (atk.atk ?? 0) + ((ent.memoBaseAtkFlat as number) ?? 0)
    a[o + StatKey.DEF] += ((ent.memoBaseDefScaling as number) ?? 0) * (atk.def ?? 0) + ((ent.memoBaseDefFlat as number) ?? 0)
    a[o + StatKey.HP] += ((ent.memoBaseHpScaling as number) ?? 0) * (atk.hp ?? 0) + ((ent.memoBaseHpFlat as number) ?? 0)
    a[o + StatKey.SPD] += ((ent.memoBaseSpdScaling as number) ?? 0) * (atk.spd ?? 100) + ((ent.memoBaseSpdFlat as number) ?? 0)
    a[o + StatKey.CR] += atk.cr ?? 0
    a[o + StatKey.CD] += atk.cd ?? 0
    a[o + StatKey.BE] += atk.be ?? 0
    a[o + StatKey.EHR] += atk.effect_hit ?? 0
    // 元素增伤继承（对拍场景只有主元素一键——多元素件接入时按全键循环补）
    if (elem) a[o + elem.boostKey] += atk.element_boost ?? 0
  }

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
  // applyPercentStats 忆灵分支：百分比件 × 忆灵自身白值（scaling×角色白值——
  // 实体注册表已镜像；全队 HP_P 族（雨过天晴/德谬歌生命）落忆灵段的唯一通道）
  for (let ei = 1; ei < entities.length; ei++) {
    const ent = entities[ei]
    if (ent.memosprite !== true) continue
    const o = x.getActionIndex(ei, 0)
    a[o + StatKey.ATK] += a[o + StatKey.ATK_P] * ent.baseAtk
    a[o + StatKey.HP] += a[o + StatKey.HP_P] * ent.baseHp
    a[o + StatKey.DEF] += a[o + StatKey.DEF_P] * ent.baseDef
    a[o + StatKey.SPD] += a[o + StatKey.SPD_P] * ent.baseSpd
  }
  // applyPercentStats 的 SelfAndPet 段（calculateStats.ts:234-246）：百分比件读**实体 0**
  // 的 pct 槽 ×context.baseX 后铺全体 Self|Pet——实体 0 已在上方单行换算落账，此处补
  // pet 实体镜像（账账族吃主角色的 ATK_P/SPD_P 条件 buff——与主 C 同源同值）
  for (let ei = 1; ei < entities.length; ei++) {
    const ent = entities[ei] as Record<string, unknown>
    if (ent.pet !== true) continue
    const o = x.getActionIndex(ei, 0)
    a[o + StatKey.ATK] += a[StatKey.ATK_P] * (base.atk ?? 0)
    a[o + StatKey.HP] += a[StatKey.HP_P] * (base.hp ?? 0)
    a[o + StatKey.DEF] += a[StatKey.DEF_P] * (base.def ?? 0)
    a[o + StatKey.SPD] += a[StatKey.SPD_P] * (base.spd ?? 100)
  }

  // --- dynamic conditionals（镜像 calculateStats.evaluateDynamicConditionals：角色→LC
  //     ——真实管线位置在 applyPercentStats 之后、终端套装件之前；长夜月战技光环
  //     （忆灵暴伤=自身暴伤换算）/风堇速度档（>200 生命+超档治疗量）等动态件的唯一通道。
  //     真实管线 evaluateConditional 包 condition+effect，此处同构直调） ---
  for (const dc of (controller as { dynamicConditionals?: { condition: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => boolean, effect: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void }[] }).dynamicConditionals ?? []) {
    if (dc.condition(x, action, context)) dc.effect(x, action, context)
  }
  for (const dc of (lcController as { dynamicConditionals?: { condition: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => boolean, effect: (x: ComputedStatsContainer, a: OptimizerAction, c: OptimizerContext) => void }[] }).dynamicConditionals ?? []) {
    if (dc.condition(x, action, context)) dc.effect(x, action, context)
  }

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
    // 命中寄存器回写（镜像 optimizerWorker.ts:283——HealTally/引用段族（风堇 tally
    // 直写基数）的唯一读口；CPU .apply 路径不写寄存器，worker 在主循环逐 hit 写）
    x.setHitRegisterValue(hit.registerIndex as number, dmg)
    const defPen = x.getValue(StatKey.DEF_PEN, i)
    const resPen = x.getValue(StatKey.RES_PEN, i)
    const cr = Math.min(1, x.getValue(StatKey.CR, i) + x.getValue(StatKey.CR_BOOST, i))
    const cd = x.getValue(StatKey.CD, i) + x.getValue(StatKey.CD_BOOST, i)
    const elemBoostKey = ELEMENT_BOOST_BY_TAG[hit.damageElement as number]
    // 欢愉段回显（欢愉波——ElationDamageFunction 乘区读回：elation（含 minElationOverride
    // 择优槽——爻光大吉大利队友链）/merrymaking/punchline 三区；非欢愉段恒 0/不落键）
    const isEla = (hit.damageFunctionType as DamageFunctionType) === DamageFunctionType.Elation
    const punchline = (hit.punchlineStacks as number) ?? 0
    // 乘区读回的基数区按 scalingEntityIndex 取（忆灵技跨实体缩放——战斗面板读
    // sourceEntity（默认 getValue 解析），白值基数读 scalingEntity，两参不同才显形）
    const sei = (hit.scalingEntityIndex as number) ?? 0
    hits.push({
      damage: dmg,
      damage_function: DamageFunctionType[hit.damageFunctionType as DamageFunctionType],
      source_entity: entities[(hit.sourceEntityIndex as number) ?? 0]?.name ?? '',
      atk_scaling: (hit.atkScaling as number) ?? 0,
      hp_scaling: (hit.hpScaling as number) ?? 0,
      def_scaling: (hit.defScaling as number) ?? 0,
      elation_scaling: (hit.elationScaling as number) ?? 0,
      punchline_stacks: punchline,
      breakdown: {
        baseUniversalMulti: config.enemyWeaknessBroken ? 1 : 0.9,
        defMulti: 100 / ((context.enemyLevel + 20) * Math.max(0, 1 - defPen) + 100),
        resMulti: 1 - (context.enemyDamageResistance - resPen),
        vulnMulti: 1 + x.getValue(StatKey.VULNERABILITY, i),
        finalDmgMulti: 1 + x.getValue(StatKey.FINAL_DMG_BOOST, i),
        dmgBoostMulti: 1 + x.getValue(StatKey.BOOST, i)
          + (elemBoostKey ? x.getValue(elemBoostKey, i) : 0),
        abilityMulti: ((hit.atkScaling as number) ?? 0) * x.getValue(StatKey.ATK, i, sei)
          + ((hit.hpScaling as number) ?? 0) * x.getValue(StatKey.HP, i, sei)
          + ((hit.defScaling as number) ?? 0) * x.getValue(StatKey.DEF, i, sei),
        critMulti: cr * (1 + cd) + (1 - cr),
        ...(isEla ? {
          elationMulti: 1 + Math.max(x.getValue(StatKey.ELATION, i),
            (hit.minElationOverride as number) ?? 0),
          merrymakeMulti: 1 + x.getValue(StatKey.MERRYMAKING, i),
          punchlineMulti: 1 + (5 * punchline) / (punchline + 240),
        } : {}),
      },
    })
  }

  // --- 面板回显（钉错面板/行迹平铺的第一道闸） ---
  // 空 hits（白厄变身技/弑魂焚诏等无伤行动）时 getValue 的 hit 解析无落点——
  // 面板回显对无伤行动无意义，跳过半截（total/hits 照返，比零用）
  const stats = action.hits!.length > 0 ? {
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
    res_pen: x.getValue(StatKey.RES_PEN, 0),
    vulnerability: x.getValue(StatKey.VULNERABILITY, 0),
    final_dmg_boost: x.getValue(StatKey.FINAL_DMG_BOOST, 0),
    elation: x.getValue(StatKey.ELATION, 0),
    merrymaking: x.getValue(StatKey.MERRYMAKING, 0),
  } : {}

  // --- 忆灵实体回显（多实体场——忆灵面板归属/继承钉错的第一道闸；
  //     逐实体 action 层读回，hit 解析显式传实体索引） ---
  const entityStats = action.hits!.length > 0 && entities.length > 1
    ? entities.map((ent, ei) => ({
      name: ent.name,
      hp: x.getValue(StatKey.HP, 0, ei),
      atk: x.getValue(StatKey.ATK, 0, ei),
      def: x.getValue(StatKey.DEF, 0, ei),
      spd: x.getValue(StatKey.SPD, 0, ei),
      cr: x.getValue(StatKey.CR, 0, ei) + x.getValue(StatKey.CR_BOOST, 0, ei),
      cd: x.getValue(StatKey.CD, 0, ei) + x.getValue(StatKey.CD_BOOST, 0, ei),
      dmg_boost: x.getValue(StatKey.BOOST, 0, ei),
      element_boost: elem ? x.getValue(elem.boostKey, 0, ei) : 0,
    }))
    : undefined

  return { total, hits, stats, entity_stats: entityStats }
}

const scenario = JSON.parse(readFileSync(0, 'utf8')) as Scenario
process.stdout.write(JSON.stringify(
  scenario.kind === 'character' ? runCharacter(scenario) : run(scenario),
))
