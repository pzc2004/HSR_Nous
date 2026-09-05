"""网页端 JS 纯函数逻辑闸（①②③ 前端增量）：node 执行页面 <script> 并断言纯函数输出.

页面脚本在 node 下只取纯函数（DOM 绑定/轮询由 `typeof document/window !== 'undefined'`
引导保护跳过）。覆盖：技能详情卡渲染、单位循环切换、徽章 chips 截断、状态/数值/星魂/
光锥/遗器 tab 渲染的空态与激活态。无 node 环境（CI）自动跳过。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).parent.parent / "src" / "hsr_nous" / "sim" / "web_static" / "index.html"

#: 追加在页面脚本后的断言台（任一断言失败即 throw → node 非零退出）
_HARNESS = r"""
function eq(cond, msg) { if (!cond) throw new Error(msg); }
// ① 技能详情卡：名称/作用域/分级倍率两行/耗点回能削韧/无描述
const sk = {name:'八雷飞渡', action_type:'skill', target_type:'blast', scaling:[{atk:0.8},{atk:2.0}],
  scaling_blast:[{atk:0.3},{atk:0.75}], energy_cost:0, energy_gain:30, energy_gain_default:false,
  toughness_dmg:20, skill_point_cost:1, skill_point_gain:0, instances:1, desc:null};
const cardHtml = skillCardHtml(sk);
eq(cardHtml.includes('八雷飞渡') && cardHtml.includes('战技') && cardHtml.includes('扩散'), 'skill head');
eq(cardHtml.includes('Lv1') && cardHtml.includes('80.0%') && cardHtml.includes('Lv2') && cardHtml.includes('200.0%'), 'scaling rows');
eq(cardHtml.includes('扩散 Lv2') && cardHtml.includes('75.0%'), 'blast row');
eq(cardHtml.includes('耗点 1') && cardHtml.includes('回能 30') && cardHtml.includes('削韧值 20'), 'meta');
eq(cardHtml.includes('无描述'), 'desc fallback');
const sk2 = {...sk, desc:'原文描述', energy_gain_default:true, instances:3};
eq(skillCardHtml(sk2).includes('原文描述') && skillCardHtml(sk2).includes('（缺省）') && skillCardHtml(sk2).includes('3 段'), 'desc/default/instances');
// ② 单位循环切换（C 面板 ←/→ 与下拉共用）
eq(cycleId(['a','b','c'], 'a', 1) === 'b' && cycleId(['a','b','c'], 'c', 1) === 'a', 'cycle fwd');
eq(cycleId(['a','b','c'], 'a', -1) === 'c' && cycleId([], 'x', 1) === 'x' && cycleId(['a'], 'z', 1) === 'a', 'cycle wrap/empty');
// ③ buff 小方块图标行（L1/L5 组件，旧具名 chip 组件的继任）：首字方块 + 右下角层数 + 超量 +N
const bics = [
  {name:'甲', stacks:1, type:'buff'}, {name:'乙', stacks:1, type:'buff'},
  {name:'丙', stacks:1, type:'buff'}, {name:'丁', stacks:1, type:'buff'},
  {name:'戊', stacks:1, type:'buff'}, {name:'己', stacks:1, type:'buff'},
  {name:'庚', stacks:1, type:'buff'}, {name:'辛', stacks:1, type:'buff'},
  {name:'壬', stacks:1, type:'buff'},
];
const bicHtml = buffIconsHtml(bics, 'hero');
eq(bicHtml.includes('>甲<') && bicHtml.includes('>辛<') && !bicHtml.includes('>壬<') && bicHtml.includes('+1'), 'buff icons cap 8');
eq(bicHtml.includes('showMods(&quot;hero&quot;)'), 'buff icons overflow modal');
eq(!buffIconsHtml([{name:'甲', stacks:1, type:'buff'}], 'hero').includes('+'), 'buff icons no-overflow');
eq(buffIconsHtml([], 'hero') === '' && buffIconsHtml(null, 'hero') === '', 'buff icons empty');
// 能量条标签：旁车 energy_name 下发值（缺省"能量"由调用方 || 回落）
eq(meter('energy', 5, 12, '火种', false).includes('火种'), 'meter sidecar label');
eq(meter('energy', 110, 110, '能量', true).includes('能量'), 'meter default label');
// 状态 tab：空态 + 明细行（层数/时长/来源/数值/可驱散）
eq(statusRowsHtml([]).includes('无 modifier'), 'status empty');
const row = statusRowsHtml([{name:'行迹', type:'buff', stacks:2, max_stack:5, duration:0,
  source_name:'黄泉', stat_effects:{atk_pct:0.28}, scaling_effects:{}, override_effects:{}, dispellable:false}]);
eq(row.includes('行迹') && row.includes('×2/5') && row.includes('永久') && row.includes('黄泉'), 'status row');
eq(row.includes('攻击力 +28.0%') && row.includes('不可驱散'), 'status detail F1 zh');
// 数值 tab：百分比口径
const eff = {hp:2910.8, atk:1585.2, def:1575.0, spd:108.8, crit_rate:0.05, crit_dmg:0.74,
  break_effect:0.6, effect_hit:0.4, effect_res:0.3, energy_regen:1.0, heal_bonus:0.0};
const st = statsTabHtml(eff);
eq(st.includes('2911') && st.includes('74.0%') && st.includes('60.0%') && st.includes('击破特攻'), 'stats');
eq(st.includes('108.8'), 'stats spd 一位小数');
eq(statsTabHtml(null).includes('无数据'), 'stats empty');
// 星魂 tab：激活态 + 空态
const eds = [{rank:'E1', name:'一魂', active:true, desc:'增伤'}, {rank:'E2', name:'二魂', active:false, desc:''}];
eq(eidolonsTabHtml(eds).includes('已激活') && eidolonsTabHtml(eds).includes('（无描述）'), 'eidolon rows');
eq(eidolonsTabHtml([]).includes('无数据'), 'eidolon empty');
// 星魂 tab：官方 desc 主文本在前、模板注记降灰次级行（有才显示）、双无才"（无描述）"
const e2h = eidolonsTabHtml([{rank:'E2', name:'天与地，世间的泡沫', active:false,
  desc:'抗性穿透提高20%。', note:'消耗≥4毁伤获得额外回合'}]);
eq(e2h.includes('抗性穿透提高20%。') && e2h.indexOf('抗性穿透') < e2h.indexOf('消耗≥4毁伤'), 'eidolon desc main first');
eq(e2h.includes('<div class="dim">消耗≥4毁伤获得额外回合</div>'), 'eidolon note dim line');
eq(!eidolonsTabHtml([{rank:'E1', name:'一魂', active:true, desc:'官方描述', note:''}]).includes('（无描述）'), 'eidolon desc-only no fallback');
// 光锥/遗器 tab：空态
eq(lightConeTabHtml(null).includes('无') && relicsTabHtml(null).includes('无数据'), 'lc/relic empty');
// 表单编辑器：datalist 值解析（"1308 黄泉·残梦" → "1308"）
eq(parsePickerId('1308 黄泉·残梦') === '1308' && parsePickerId(' 8001 冰锋 ') === '8001', 'picker id');
eq(parsePickerId('自定义怪') === '' && parsePickerId('') === '', 'picker non-id');
// 行动键位（崩铁本体）：单战技=E；双战技=W、E（卡厄斯兰那 Q/W/E）；普攻=Q
const ch = (i, t) => ({index: i, action_type: t});
const two = [ch(0,'basic'), ch(1,'skill'), ch(2,'skill')];
eq(keyOf(two[0], two) === 'q' && keyOf(two[1], two) === 'w' && keyOf(two[2], two) === 'e',
   'keyOf two-skill Q/W/E');
const one = [ch(0,'basic'), ch(1,'skill')];
eq(keyOf(one[0], one) === 'q' && keyOf(one[1], one) === 'e', 'keyOf single-skill Q/E');
eq(keyOf(ch(3,'ultimate'), one) === '1', 'keyOf ultimate 1');
// 模板来源徽章：锚版=金（tpl-anchor）/ 骨架=灰（默认 badge）/ 无模板（inline）=空串
eq(tplBadgeHtml('anchor').includes('锚版') && tplBadgeHtml('anchor').includes('tpl-anchor'), 'tpl badge anchor');
eq(tplBadgeHtml('generated').includes('骨架') && !tplBadgeHtml('generated').includes('tpl-anchor'), 'tpl badge generated');
eq(tplBadgeHtml(null) === '' && tplBadgeHtml('weird') === '', 'tpl badge empty');
// 单位卡：名字行带来源徽章（我方/敌方同一 card()；徽章在名字之后、其余徽章之前）
const bare = {hp:1, max_hp:1, alive:true, modifier_list:[]};
const cAnchor = card('hero', {...bare, name:'白厄', template_source:'anchor'}, 'ally');
eq(cAnchor.includes('tpl-anchor') && cAnchor.indexOf('锚版') > cAnchor.indexOf('白厄'), 'card anchor badge');
eq(card('e1', {...bare, name:'冰锋', template_source:'generated'}, 'enemy').includes('骨架'), 'card generated badge');
eq(!card('e2', {...bare, name:'假人', template_source:null}, 'enemy').includes('骨架'), 'card inline no badge');
// C 面板模板行：徽章 + 完整路径；无模板 → 空行
const tplLine = tplPathLineHtml({source:'anchor', path:'/x/fixtures/templates/characters/1408_phainon.yaml'});
eq(tplLine.includes('tpl-anchor') && tplLine.includes('1408_phainon.yaml'), 'tpl path line');
eq(tplPathLineHtml(null) === '', 'tpl path empty');
// 大厅角色选项：锚版后缀（generated 无后缀降噪）；parsePickerId 仍取首部 id
eq(charOptionLabel({id:'1408', name:'白厄', charge:'火种', source:'anchor'}) === '1408 白厄·火种·锚版', 'lobby anchor label');
eq(charOptionLabel({id:'1308', name:'黄泉', charge:'残梦', source:'generated'}) === '1308 黄泉·残梦', 'lobby generated label');
eq(parsePickerId('1408 白厄·火种·锚版') === '1408', 'picker id with badge suffix');
// F1 stat 中文化：映射表 / pct 族 ×100 / 元素动态族 / 未知键回落原文（不脑补）
eq(fmtStatKv('atk_pct', 0.5) === '攻击力 +50.0%', 'fmt atk_pct zh');
eq(fmtStatKv('hp', 800) === '生命上限 +800', 'fmt flat hp');
eq(fmtStatKv('dmg_physical', 0.2) === '物理伤害提高 +20.0%', 'fmt dmg elem');
eq(fmtStatKv('res_fire', -0.1) === '火抗性 -10.0%', 'fmt res elem');
eq(fmtStatKv('custom_x', 0.5) === 'custom_x +0.5', 'fmt unknown fallback raw');
eq(statZh('vulnerability') === '易伤' && statZh('weird_key') === 'weird_key', 'statZh table+fallback');
// F2 来源文案：action/trace/light_cone/state 组合 + 空 kind 回落现状
eq(sourceTextHtml({source_name:'白厄', source_kind:'action', source_ref:'140802',
  source_action_name:'黎明创世，地辟天开', source_action_type:'skill'})
  === '来自 白厄 · 战技『黎明创世，地辟天开』', 'source action');
eq(sourceTextHtml({source_name:'白厄', source_kind:'trace'}) === '来自 白厄 · 行迹', 'source trace');
eq(sourceTextHtml({source_name:'阮•梅', source_kind:'light_cone', source_ref:'镜中故我'})
  === '来自 阮•梅 · 光锥『镜中故我』', 'source lc');
eq(sourceTextHtml({source_name:'白厄', source_kind:'state', source_ref:'卡厄斯兰那'})
  === '来自 白厄 · 形态『卡厄斯兰那』', 'source state');
eq(sourceTextHtml({source_name:'黄泉', source_kind:''}) === '来自 黄泉', 'source empty fallback');
// F3 可展开行：expandable → src-link + toggleSrcDetail 调用；否则纯文本不可点
const rowExp = statusRowsHtml([{name:'时墟铁墓', type:'debuff', stacks:1, max_stack:1, duration:0,
  source_name:'白厄', source_id:'1408', source_kind:'action', source_ref:'140803',
  source_action_name:'永劫燔世，其将背负', source_action_type:'ultimate',
  stat_effects:{}, scaling_effects:{}, override_effects:{}, dispellable:false, expandable:true}]);
eq(rowExp.includes('src-link') && rowExp.includes('toggleSrcDetail(this,&quot;1408&quot;,&quot;140803&quot;)'), 'expandable row link');
eq(rowExp.includes('终结技『永劫燔世，其将背负』'), 'expandable label');
const rowNo = statusRowsHtml([{name:'照见英雄本色', type:'buff', stacks:1, max_stack:2, duration:0,
  source_name:'白厄', source_kind:'hook', source_ref:'照见英雄本色',
  stat_effects:{}, scaling_effects:{}, override_effects:{}, dispellable:false, expandable:false}]);
eq(!rowNo.includes('src-link') && rowNo.includes('来自 白厄 · 照见英雄本色'), 'non-expandable hook row');
// F3 来源详情卡（行迹等旁车件最小卡，sk-card 壳）
const sCard = srcCardHtml({name:'照见英雄本色', kind:'行迹', desc:'攻击力提高50%'});
eq(sCard.includes('sk-card') && sCard.includes('照见英雄本色') && sCard.includes('行迹')
   && sCard.includes('攻击力提高50%'), 'srcCard render');
eq(srcCardHtml({name:'x', kind:'', desc:''}).includes('无描述'), 'srcCard empty desc');
// follow_up 触发件过滤：不作玩家按钮（恒合法是引擎点火需要）；键位不受其影响
const chF = (i, t) => ({index: i, action_type: t});
S.pending = {choices: [chF(0,'basic'), chF(1,'skill'), {index:2, action_type:'follow_up'},
  {index:3, action_type:'follow_up'}, chF(4,'skill')]};
eq(visibleChoices().length === 3 && visibleChoices().every(c => c.action_type !== 'follow_up'),
   'visibleChoices filters follow_up');
eq(keyOf(visibleChoices()[1]) === 'w' && keyOf(visibleChoices()[2]) === 'e',
   'keyOf two-skill W/E after follow_up filter');
S.pending = null;
// 特殊充能槽：charge 优先渲染（label/值/激活线下发）；满线 full；无 charge 且 max_energy=0 → 无能量条
const cChg = card('hero', {...bare, name:'白厄', max_energy:0,
  charge:{resource_id:'fire_seed', value:3, cap:12, label:'火种'}}, 'ally');
eq(cChg.includes('火种') && cChg.includes('3 / 12'), 'charge meter render');
eq(!cChg.includes('meter energy full'), 'charge below cap not full');
eq(card('hero', {...bare, name:'白厄', max_energy:0,
  charge:{resource_id:'fire_seed', value:12, cap:12, label:'火种'}}, 'ally')
  .includes('meter energy full'), 'charge full at cap');
const cNorm = card('hero2', {...bare, name:'黄泉', max_energy:110, energy:60, charge:null}, 'ally');
eq(cNorm.includes('60 / 110') && cNorm.includes('能量'), 'normal energy meter untouched');
eq(!card('hero3', {...bare, name:'充能员', max_energy:0, charge:null}, 'ally')
  .includes('meter energy'), 'no bar when no charge and max_energy 0');
// X2 【机制名】链接化：旁车 xref_names / 场上 modifier 名命中 → x-link；不命中 → 纯文本
S.actors = {e1: {name:'假人', modifier_list:['时墟铁墓']}};
sheetDataCache['1408'] = {xref_names: ['照见英雄本色', '毁伤']};
const lw = descWithLinks('获得【毁伤】与【不存在的机制】。', '1408');
eq(lw.includes('x-link') && lw.includes('openXref(this,&quot;1408&quot;,&quot;毁伤&quot;)'), 'desc link hit');
eq(lw.includes('【不存在的机制】') && !lw.includes('不存在的机制&quot;'), 'desc miss plain');
eq(descWithLinks('触发【时墟铁墓】。', '1408').includes('x-link'), 'desc link via field modifier');
eq(descWithLinks('', '1408') === '', 'desc empty');
// X3 激活 modifier 详情卡：状态行 + 来源文案 + 数值中文化
const xm = xrefModifierCardHtml({name:'弑魂之炽', type:'buff', stacks:4, max_stack:99, duration:0,
  source_name:'白厄', source_kind:'action', source_ref:'140809',
  source_action_name:'灾厄•弑魂焚诏', source_action_type:'skill',
  stat_effects:{dmg_dmg_reduction:0.75}, scaling_effects:{}, override_effects:{}, dispellable:false});
eq(xm.includes('弑魂之炽') && xm.includes('×4/99') && xm.includes('永久'), 'xref mod card status');
eq(xm.includes('来自 白厄 · 战技『灾厄•弑魂焚诏』'), 'xref mod card source');
eq(xm.includes('减伤 +75.0%'), 'xref mod card stat zh');
// 返回栈：前推 capped 两层（一层返回），回弹一层到底不动
let stk = [];
stk = xrefStackPush(stk, {x:'a'}); stk = xrefStackPush(stk, {x:'b'}); stk = xrefStackPush(stk, {x:'c'});
eq(stk.length === 2 && stk[0].x === 'b' && stk[1].x === 'c', 'stack cap two layers');
stk = xrefStackPop(stk);
eq(stk.length === 1 && stk[0].x === 'b' && stk === xrefStackPop(stk), 'stack pop one layer');
// X3 徽章：具名方块 → openXref；+N 超量徽记 → 维持 showMods 全量弹层；层数 >1 才标角标
const bicX = buffIconsHtml([{name:'弑魂之炽', stacks:4, type:'buff'},
  {name:'照见英雄本色', stacks:1, type:'buff'}], '1408');
eq(bicX.includes('openXref(this,&quot;1408&quot;,&quot;弑魂之炽&quot;)'), 'buff icon named xref');
eq(bicX.includes('<i>4</i>') && !bicX.includes('照见英雄本色<i') && bicX.includes('title="照见英雄本色"'),
   'buff icon stacks badge only when >1');
eq(buffIconsHtml([{name:'时墟铁墓', stacks:2, type:'debuff'}], 'h').includes('buff-ic de'), 'buff icon debuff red');
eq(buffIconsHtml([{name:'甲', stacks:1, type:'buff'}], 'hero').includes('showMods(&quot;hero&quot;)') === false
   && bicHtml.includes('showMods(&quot;hero&quot;)'), 'buff icon overflow keeps modal');
// ---- 交互四件套（T1 演出 / T2 事件卡 / T3 节奏 / T4 浮现）----
// T1 跳字分类：暴击金大 / 普通白 / 治疗绿 / 全额盾吸收蓝灰 / 阵亡灰；无可视化 kind → null
eq(fxOf({kind:'hit', amount:1234, absorbed:0, crit:true}).cls === 'crit', 'fx crit gold');
const fxN = fxOf({kind:'hit', amount:1234, absorbed:0, crit:false});
eq(fxN.cls === 'normal' && String(fxN.text) === '1234', 'fx normal white');
eq(fxOf({kind:'hit', amount:500, absorbed:500, crit:false}).cls === 'shield', 'fx full-absorb shield');
eq(fxOf({kind:'hit', amount:500, absorbed:100, crit:false}).cls === 'normal', 'fx partial absorb stays normal');
const fxH = fxOf({kind:'heal', amount:800});
eq(fxH.cls === 'heal' && fxH.text === '+800', 'fx heal green');
eq(fxOf({kind:'death'}).text === '阵亡' && fxOf({kind:'dot', amount:60}).cls === 'normal', 'fx death/dot');
eq(fxOf({kind:'mod_add'}) === null && fxOf({kind:'wave'}) === null, 'fx non-visual kinds');
// T2 事件合并：同动同源同目标同行动类型多段并一条（数值累加、暴击并集、段数计数）
const mg = mergeHitEvents([
  {kind:'hit', turn:3, source:'h', target:'e', action_type:'skill', amount:100, absorbed:0, crit:false, seg:0},
  {kind:'hit', turn:3, source:'h', target:'e', action_type:'skill', amount:50, absorbed:10, crit:true, seg:1},
  {kind:'hit', turn:3, source:'h', target:'e2', action_type:'skill', amount:70, absorbed:0, crit:false, seg:0},
]);
eq(mg.length === 2 && mg[0].amount === 150 && mg[0].absorbed === 10 && mg[0].crit === true
   && mg[0].segs === 2 && mg[1].segs === undefined, 'mergeHitEvents segs');
// T2 事件卡渲染：伤害（徽标组）/ 治疗 / 击破 / 阵亡 / 波次 / buff 变化 / 终结技
const acts = {h:{name:'黄泉'}, e:{name:'冰锋'}, e2:{name:'炎华'}};
const dc = eventCardHtml(mg[0], acts);
eq(dc.includes('黄泉') && dc.includes('战技') && dc.includes('冰锋'), 'card actor·type→target');
eq(dc.includes('伤害 150') && dc.includes('暴击') && dc.includes('盾 10') && dc.includes('×2 段'), 'card badges');
eq(eventCardHtml({kind:'heal', source:'h', target:'h', amount:803}, acts).includes('+803'), 'card heal');
eq(eventCardHtml({kind:'break', source:'h', target:'e', amount:900}, acts).includes('击破 900'), 'card break');
const dth = eventCardHtml({kind:'death', target:'e'}, acts);
eq(dth.includes('冰锋') && dth.includes('阵亡'), 'card death');
eq(eventCardHtml({kind:'wave', wave:2}, acts).includes('第 2 波'), 'card wave');
eq(eventCardHtml({kind:'mod_add', target:'h', mod:'毁伤', mod_type:'buff'}, acts).includes('获得「毁伤」'), 'card mod_add');
eq(eventCardHtml({kind:'mod_del', target:'h', mod:'毁伤'}, acts).includes('的「毁伤」消失'), 'card mod_del');
const uc = eventCardHtml({kind:'ult', source:'h', name:'天降正义'}, acts);
eq(uc.includes('释放终结技「天降正义」'), 'card ult with name');
eq(eventCardHtml({kind:'hit', turn:1, source:'h', target:'e', action_type:'skill', amount:5}, acts)
  .includes('ev-detail'), 'card collapsible detail');
// T3 调速：tick 间隔按倍率缩放
eq(autoDelay(0.5) === 1400 && autoDelay(1) === 700 && autoDelay(2) === 350 && autoDelay(4) === 175,
   'autoDelay scale');
// T3 关键点检测：终结技窗口边沿 / 波次翻篇 / 活转死；同态不重触发
const kp0 = {loaded:true, wave:1, pending:null, actors:{e:{alive:true}}};
const kpUlt = {loaded:true, wave:1, pending:{phase:'ultimate'}, actors:{e:{alive:true}}};
eq(detectKeyPause(kp0, kpUlt) === 'ultimate', 'kp ultimate edge');
eq(detectKeyPause(kpUlt, kpUlt) === null, 'kp no retrigger');
eq(detectKeyPause(kp0, {...kp0, wave:2}) === 'wave', 'kp wave');
eq(detectKeyPause(kp0, {loaded:true, wave:1, pending:null, actors:{e:{alive:false}}}) === 'death', 'kp death');
eq(detectKeyPause(kp0, kp0) === null && detectKeyPause(null, kp0) === null
   && detectKeyPause(kp0, {loaded:false}) === null, 'kp none');
// T4 行动条终结技徽章：能量满 / 火种到线 → ready；敌方恒否；徽章上行动条条目
eq(barUltReady({actor_type:'character', max_energy:110, energy:110}) === true, 'bar ready energy full');
eq(barUltReady({actor_type:'character', max_energy:110, energy:60}) === false, 'bar not ready');
eq(barUltReady({actor_type:'character', charge:{value:12, cap:12}}) === true, 'bar ready charge cap');
eq(barUltReady({actor_type:'monster', max_energy:0, energy:0}) === false && barUltReady(null) === false,
   'bar monster/null never');
eq(barEntryHtml({name:'白厄', kind:'normal', eta:12.3}, true).includes('终结技'), 'bar entry ult badge');
eq(!barEntryHtml({name:'白厄', kind:'normal', eta:12.3}, false).includes('终结技'), 'bar entry no badge');
// T4 敌卡：意图行（无意图不显示）+ 非零抗性小徽标（弱点行原有）
eq(intentLineHtml({intent:'挥打'}).includes('下一步：挥打'), 'intent line');
eq(intentLineHtml({intent:null}) === '' && intentLineHtml({}) === '', 'intent empty hidden');
eq(resBadgesHtml({fire:0.2}).includes('火抗 20%'), 'res badge zh');
eq(resBadgesHtml({quantum:0.2, fire:0}).includes('量子抗 20%'), 'res zero filtered');
eq(resBadgesHtml({}) === '' && resBadgesHtml(null) === '', 'res empty');
const cInt = card('e9', {...bare, name:'测试怪', intent:'挥打', resistance:{fire:0.2}, weakness:['fire']}, 'enemy');
eq(cInt.includes('下一步：挥打') && cInt.includes('火抗 20%') && cInt.includes('data-aid="e9"'), 'card intent+res+aid');
// 终结技就绪徽章已上移行动条：单位卡不再渲染（T4 移动语义）
eq(!card('h9', {...bare, name:'黄泉', max_energy:110, energy:110}, 'ally').includes('终结技就绪'),
   'card ult badge moved to bar');
// ---- 布局五轨（L1 我方卡 / L2 圆钮 / L3 行动条 / L4 瞄准 / L5 敌卡 buff）----
// L1 站位数字：我方编队序 1-4（与 1234 键位同口径），敌方/不在册 → ''
const stanceActors = {a:{actor_type:'character'}, b:{actor_type:'character'},
  e:{actor_type:'monster'}, c:{actor_type:'character'}};
eq(allyStance('b', stanceActors) === '2' && allyStance('c', stanceActors) === '3', 'stance 1-4 ally order');
eq(allyStance('e', stanceActors) === '' && allyStance('zz', stanceActors) === '', 'stance enemy/none empty');
// L1 我方卡：站位徽标 + 立绘位 + buff 图标行（层数角标）齐备
S.actors = stanceActors;
const cAlly = card('b', {...bare, name:'白厄', modifier_icons:[{name:'毁伤', stacks:2, type:'buff'}]}, 'ally');
eq(cAlly.includes('class="stance">2<') && cAlly.includes('avatar') && cAlly.includes('buff-row')
   && cAlly.includes('<i>2</i>'), 'ally card stance/avatar/buff row');
// L4 目标圈统一语义（游戏同款）：主目标大圈（单体/扩散主/群攻/弹射同尺寸）；扩散副目标小圈；
// 群攻/弹射候选全大圈（无副目标）；单体仅箭头带圈
aiming = {candidates:['e1','e2','e3'], arrow:1, label:'剑阵', key:'e', phase2:false, actionIndex:1, target_type:'blast'};
S.actors = {e1:{actor_type:'monster'}, e2:{actor_type:'monster'}, e3:{actor_type:'monster'}};
const cArrow = card('e2', {...bare, name:'冰锋'}, 'enemy');
eq(cArrow.includes('reticle') && !cArrow.includes('reticle sm') && cArrow.includes('cross'),
   'aim reticle 大圈 on arrow card');
const cSplash = card('e1', {...bare, name:'炎华'}, 'enemy');
eq(cSplash.includes('splash') && cSplash.includes('reticle sm'), 'blast 副目标小圈');
// blast 边缘箭：箭头在 e1（边上）→ 仅 e2 小圈，e3 出范围不带圈（瞄准池 ≠ 命中集）
aiming = {candidates:['e1','e2','e3'], arrow:0, label:'剑阵', key:'e', phase2:false, actionIndex:1, target_type:'blast'};
const cEdge1 = card('e1', {...bare, name:'炎华'}, 'enemy');
eq(cEdge1.includes('reticle') && !cEdge1.includes('reticle sm'), 'blast 边缘箭主目标大圈');
const cEdge2 = card('e2', {...bare, name:'冰锋'}, 'enemy');
eq(cEdge2.includes('reticle sm'), 'blast 边缘箭相邻小圈');
const cEdge3 = card('e3', {...bare, name:'虚卒'}, 'enemy');
eq(!cEdge3.includes('reticle'), 'blast 范围外不带圈');
aiming = {candidates:['e1','e2','e3'], arrow:1, label:'赞颂', key:'e', phase2:false, actionIndex:1, target_type:'aoe'};
const cAoe = card('e1', {...bare, name:'炎华'}, 'enemy');
eq(cAoe.includes('reticle') && !cAoe.includes('reticle sm'), 'aoe 候选全大圈');
aiming = {candidates:['e2'], arrow:0, label:'破军', key:'q', phase2:false, actionIndex:0, target_type:'single'};
const cSingleOther = card('e1', {...bare, name:'炎华'}, 'enemy');
eq(!cSingleOther.includes('reticle'), '单体非候选不带圈');
aiming = null;
// L4 弱点元素图标：悬上缘小圆图标（元素首字+色板；词表外回落原文首字）
const wk = weakIconsHtml(['fire', 'ice', 'physical']);
eq(wk.includes('elem-ic') && wk.includes('>火<') && wk.includes('>冰<') && wk.includes('>物<'), 'weak elem icons');
eq(weakIconsHtml(['xelian']).includes('>x<'), 'weak icon unknown fallback raw char');
eq(weakIconsHtml([]) === '' && weakIconsHtml(null) === '', 'weak icons empty');
// L4 敌卡：弱点图标行悬上缘（weak-row），buff 图标行复用（L5）
const cEnemy = card('e1', {...bare, name:'测试怪', weakness:['fire'],
  modifier_icons:[{name:'时墟铁墓', stacks:1, type:'debuff'}]}, 'enemy');
eq(cEnemy.includes('weak-row') && cEnemy.includes('buff-ic de'), 'enemy card weak top row + L5 buff icons');
// L2 行动圆钮：data-act 键位/名称/类型·作用域·耗点标签；终结技圆钮 data-ult/键位/名
const ab = actBtnHtml({index:1, name:'黎明创世，地辟天开', action_type:'skill', target_type:'blast',
  skill_point_cost:1}, 'w');
eq(ab.includes('data-act="1"') && ab.includes('>W<') && ab.includes('黎明创世') && ab.includes('战技·扩散·耗点 1'),
   'act circle btn');
eq(actBtnHtml({index:0, name:'普攻', action_type:'basic', target_type:'single', skill_point_cost:0}, 'q')
  .includes('普攻·单体'), 'act btn basic tags no cost');
const ub = ultBtnHtml({actor_id:'1408', name:'白厄', ult_name:'永劫燔世，其将背负', key_hint:'1'});
eq(ub.includes('data-ult="1408"') && ub.includes('>1<') && ub.includes('白厄') && ub.includes('永劫燔世'),
   'ult circle btn');
// L2 瞄准目标计数：单体 1 / 扩散主目标±1（边缘收敛）/ 群攻全量
eq(aimCountText({target_type:'single', candidates:['e1','e2'], arrow:0}) === '目标 ×1', 'aim count single');
eq(aimCountText({target_type:'blast', candidates:['e1','e2','e3','e4','e5'], arrow:2}) === '目标 ×3', 'aim count blast mid');
eq(aimCountText({target_type:'blast', candidates:['e1','e2','e3'], arrow:0}) === '目标 ×2', 'aim count blast edge');
eq(aimCountText({target_type:'aoe', candidates:['e1','e2','e3','e4'], arrow:0}) === '目标 ×4', 'aim count aoe');
eq(aimCountText(null) === '', 'aim count null');
// L3 行动条条目：▶当前 + 首字头像 + 就绪徽章 + 类型小图标（追/倒）
const be = barEntryHtml({name:'白厄', kind:'normal', eta:12.3}, true, true);
eq(be.includes('bar-play') && be.includes('▶') && be.includes('bar-ava') && be.includes('终结技'), 'bar entry current+avatar+ult');
eq(!barEntryHtml({name:'白厄', kind:'normal', eta:12.3}, false, false).includes('bar-play'), 'bar entry not current');
eq(barEntryHtml({name:'缇宝', kind:'normal_extra', eta:5.0}, false).includes('bar-kind extra'), 'bar kind extra icon');
// owner 裁定：「倒」只给退大终点（state_exit）；countdown 本体的每一动是普通回合不戴标
eq(!barEntryHtml({name:'白厄', kind:'countdown', eta:5.0}, false).includes('bar-kind'), 'bar kind countdown no icon');
eq(barEntryHtml({name:'白厄', kind:'state_exit', eta:5.0}, false).includes('bar-kind cd'), 'bar kind state_exit 倒 icon');
// HP 条盾叠层：有盾=蓝段+盾值数字；无盾=纯血条
{
  const h1 = meterHpFull({hp: 800, max_hp: 1000, shield: 200});
  eq(h1.includes('b class="sh"') && h1.includes('盾 200') && h1.includes('width:20%'), 'meterHp shield overlay+num');
  const h2 = meterHpFull({hp: 800, max_hp: 1000, shield: 0});
  eq(!h2.includes('b class="sh"') && !h2.includes('盾 '), 'meterHp no shield = plain');
  const h3 = meterHpFull({hp: 1000, max_hp: 1000, shield: 300});
  eq(h3.includes('width:30%'), 'meterHp 满血盾段仍从左可见');
}
// ---- owner 终审四 bug（B1 编队序 / B2 倒计时 ▶ / B3 护盾·非数值效果 / B4 一键重开）----
// B1 根因实证：JS 对整数字符串键按数值升序重排（node 同 V8 口径）——
// 编队序（1408/1412/1313/1414）会被排成数值序（1313 星期日最左），ally_order 清单是唯一可信载体
const numActors = {1408:{actor_type:'character'}, 1412:{actor_type:'character'},
  1313:{actor_type:'character'}, 1414:{actor_type:'character'}, enemy:{actor_type:'monster'}};
eq(Object.keys(numActors).filter(k => numActors[k].actor_type !== 'monster').join(',') === '1313,1408,1412,1414',
   'B1 root cause: JS numeric keys reorder ascending');
const FORM = ['1408', '1412', '1313', '1414'];   // 服务端 ally_order（= build 编队序 = key_hint 口径）
eq(allyIdsOf(numActors, FORM).join(',') === '1408,1412,1313,1414', 'B1 ally ids by formation order');
eq(allyStance('1408', numActors, FORM) === '1' && allyStance('1313', numActors, FORM) === '3'
   && allyStance('1414', numActors, FORM) === '4', 'B1 stance matches key_hint caliber');
eq(allyStance('enemy', numActors, FORM) === '' && allyStance('zz', numActors, FORM) === '',
   'B1 stance enemy/unknown empty');
// B1 兜底：未下发 ally_order → 键序（怪物仍排除）；清单缺员 → 键序接尾
eq(allyIdsOf(numActors, null).join(',') === '1313,1408,1412,1414', 'B1 fallback key order w/o monster');
eq(allyIdsOf(numActors, ['1414', '1408']).join(',') === '1414,1408,1313,1412',
   'B1 partial order then leftover append');
// B2 ▶ 归属：倒计时回合决策点（pending 挂在 1408）→ ▶ 打给 countdown 条目而非纯首位
const barCd = [{actor_id:'1002011', kind:'normal', eta:500.0},
  {actor_id:'1408', kind:'countdown', eta:639.7}];
eq(barCurrentIndex(barCd, {phase:'action', actor_id:'1408'}) === 1, 'B2 countdown executing gets ▶');
eq(barCurrentIndex(barCd, null) === 0, 'B2 no pending → first (about to execute)');
eq(barCurrentIndex(barCd, {phase:'action', actor_id:'zzz'}) === 0, 'B2 pending actor off-bar → first');
eq(barCurrentIndex([], null) === -1 && barCurrentIndex(null, null) === -1, 'B2 empty bar');
// B2 倒计时条目在执行位渲染：▶ 同帧（倒标只属于退大终点 state_exit，倒计时动不戴标）
const beCd = barEntryHtml({name:'卡厄斯兰那', kind:'countdown', eta:639.7}, false, true);
eq(beCd.includes('bar-play') && beCd.includes('▶') && !beCd.includes('bar-kind'),
   'B2 countdown entry ▶ + no kind icon');
// B3 盾值行：公式原文 + 当前值；实例取不到（remaining null）→ 只显示公式
const shm = {name:'渊渟岳峙，地载八荒', type:'buff', stacks:1, max_stack:3, duration:3,
  source_name:'丹恒•腾荒', stat_effects:{}, scaling_effects:{}, override_effects:{},
  dispellable:false, shield:{formula:'$self.atk * 0.2 + 400', remaining:918.4}};
const shmDetail = modDetailHtml(shm);
eq(shmDetail.includes('护盾') && shmDetail.includes('$self.atk * 0.2 + 400') && shmDetail.includes('（当前 918）'),
   'B3 shield formula + current value');
const shmNoInst = modDetailHtml({...shm, shield:{formula:'$self.atk * 0.2 + 400', remaining:null}});
eq(shmNoInst.includes('$self.atk * 0.2 + 400') && !shmNoInst.includes('（当前'),
   'B3 shield formula only when instance missing');
// B3 shield 件不算"非数值效果"（效果已显示）→ 状态行无提示无链接
eq(!statusRowsHtml([shm], '1414').includes('效果见技能描述'), 'B3 shield mod no hint');
// B3 非数值连结/标记类：提示"效果见技能描述" + 名称 xref 链接（不脑补效果文本）；
// 无 aid（旧调用）→ 旧渲染不标
const marker = {name:'同袍', type:'buff', stacks:1, max_stack:1, duration:0,
  source_name:'丹恒•腾荒', stat_effects:{}, scaling_effects:{}, override_effects:{}, dispellable:false};
const rowMark = statusRowsHtml([marker], '1408');
eq(rowMark.includes('效果见技能描述') && rowMark.includes('x-link')
   && rowMark.includes('openXref(this,&quot;1408&quot;,&quot;同袍&quot;)'), 'B3 marker hint + name xref link');
const rowMarkLegacy = statusRowsHtml([marker]);
eq(!rowMarkLegacy.includes('效果见技能描述') && !rowMarkLegacy.includes('x-link')
   && rowMarkLegacy.includes('mod-name'), 'B3 no-aid legacy render unchanged');
// B3 有数值效果的旧件不受新逻辑影响（照旧无提示）
eq(!statusRowsHtml([{name:'行迹', type:'buff', stacks:2, max_stack:5, duration:0,
  source_name:'黄泉', stat_effects:{atk_pct:0.28}, scaling_effects:{}, override_effects:{},
  dispellable:false}], '1308').includes('效果见技能描述'), 'B3 numeric mod no hint');
// B4 一键重开：前端接线存在（restartBattle 走 /api/restart；端点行为由 tests/test_web.py 覆盖）
eq(typeof restartBattle === 'function', 'B4 restartBattle wired');
// 瞄准候选按 ally_order（S.actors 键序来自引擎 field()，不保证编队序——曾致左移 3→4→2→1 错位）
S.actors = {
  '1313': {actor_type:'character', alive:true, name:'星期日'},
  '1408': {actor_type:'character', alive:true, name:'白厄'},
  '1412': {actor_type:'character', alive:true, name:'刻律德菈'},
  '1414': {actor_type:'character', alive:true, name:'腾荒'},
  'e1': {actor_type:'monster', alive:true, name:'假人'},
};
S.ally_order = ['1408','1412','1313','1414'];
eq(JSON.stringify(predictTargets({target_type:'ally_single'})) === JSON.stringify(['1408','1412','1313','1414']),
   'predictTargets ally_order（编队序，非 S.actors 键序）');
eq(JSON.stringify(predictTargets({target_type:'single'})) === JSON.stringify(['e1']), 'predictTargets enemy');
// 敌方布场序（enemy_order）：库怪数字 id 会被 JS 整数键重排（同 B1 根因）——实锤案例：
// stage 列出序 1002030/1002011/1002020 被排成 1002011/1002020/1002030，扩散 ±1 高亮全错
S.actors = {
  '1408': {actor_type:'character', alive:true, name:'白厄'},
  '1002030': {actor_type:'monster', alive:true, name:'银鬃炮手'},
  '1002011': {actor_type:'monster', alive:true, name:'冰锋'},
  '1002020': {actor_type:'monster', alive:false, name:'流浪者'},
};
S.enemy_order = ['1002030', '1002011', '1002020'];
eq(enemyIdsOf(S.actors, S.enemy_order).join(',') === '1002030,1002011,1002020',
   'enemyIdsOf 布场序（非 JS 数值键序）');
eq(JSON.stringify(predictTargets({target_type:'blast'})) === JSON.stringify(['1002030','1002011']),
   'predictTargets enemy_order + 只留存活');
eq(enemyIdsOf(S.actors, null).join(',') === '1002011,1002020,1002030', 'enemyIdsOf 兜底键序');
eq(sheetUnitIds().join(',') === '1408,1002030,1002011,1002020', 'sheet 单位序 = 我方编队 + 敌方布场');
S.actors = undefined; S.ally_order = undefined; S.enemy_order = undefined; sheetDataCache = {};
// inline 事件参数引号加固：含撇号的名字不再崩 onclick（旧拼法静默失效）
const cQuote = card('e1', {...bare, name:"O'Brien 假人", modifier_list:[]}, 'enemy');
eq(cQuote.includes('onCardClick(&quot;e1&quot;, &quot;O\'Brien 假人&quot;)'), 'quote-safe onCardClick');
eq(buffIconsHtml([{name:"Knight's Vow", stacks:1, type:'buff'}], 'h')
  .includes('openXref(this,&quot;h&quot;,&quot;Knight\'s Vow&quot;)'), 'quote-safe buff xref');
// 瞄准态存活校验：phase1 只认同一决策方的 action；换阶段/换人/消失 → 退出（回退落点
// 是终结技窗口时瞄准压住 ult 按钮曾只能靠 Esc 手解）
eq(aimingAlive({phase2:false, actor:'1408'}, {phase:'action', actor_id:'1408'}) === true, 'aim alive same actor action');
eq(aimingAlive({phase2:false, actor:'1408'}, {phase:'action', actor_id:'1313'}) === false, 'aim dead other actor');
eq(aimingAlive({phase2:false, actor:'1408'}, {phase:'ultimate', actor_id:'1408'}) === false, 'aim dead ult window');
eq(aimingAlive({phase2:false, actor:'1408'}, null) === false, 'aim dead pending gone');
eq(aimingAlive({phase2:true, actor:'1408'}, {phase:'target', actor_id:'1408'}) === true, 'aim phase2 target alive');
eq(aimingAlive({phase2:true, actor:'1408'}, {phase:'action', actor_id:'1408'}) === false, 'aim phase2 wrong phase');
// 全体确认制（owner 裁决）：任何行动类型都给候选进瞄准（单体/扩散选一个、群攻全体、自身自己），无直通
S.actors = {'1408': {actor_type:'character', alive:true, name:'白厄'},
  'e1': {actor_type:'monster', alive:true, name:'假人1'}, 'e2': {actor_type:'monster', alive:true, name:'假人2'}};
S.ally_order = ['1408'];
S.pending = {actor_id: '1408', choices: []};
eq(JSON.stringify(predictTargets({target_type:'aoe'})) === JSON.stringify(['e1','e2']), 'aoe → 敌全体（进瞄准非直通）');
eq(JSON.stringify(predictTargets({target_type:'ally_aoe'})) === JSON.stringify(['1408']), 'ally_aoe → 我方全体（编队序）');
eq(JSON.stringify(predictTargets({target_type:'self'})) === JSON.stringify(['1408']), 'self → 自己');
eq(JSON.stringify(predictTargets({target_type:'ally_single'})) === JSON.stringify(['1408']), 'ally_single → 编队序');
// 行动条：相对/绝对 AV（rel=相对当前时钟游戏同款；abs=原值）+ 当前行动者置顶 ▶+「当前」标
eq(barDispVal(196.1, 98, 'rel') === 98.1, 'barDispVal rel = eta-clock');
eq(barDispVal(90, 98, 'rel') === 0, 'barDispVal rel 负值钳 0');
eq(barDispVal(196.1, 98, 'abs') === 196.1, 'barDispVal abs = 原值');
{
  const h = barEntryHtml({name:'丹恒', kind:'normal', eta:196.1}, false, true, '当前');
  eq(h.includes('▶') && h.includes('当前'), 'barEntry 当前者置顶 ▶+「当前」标');
  const h2 = barEntryHtml({name:'白厄', kind:'normal', eta:101}, false, false, 3);
  eq(!h2.includes('▶') && h2.includes('>3<'), 'barEntry 队列条目无 ▶、显示相对值');
}
S.actors = undefined; S.ally_order = undefined; S.pending = null; S.last_target = null; sheetDataCache = {};
// 行动条可见条目：行动中单位的"下一动"拷贝抑制（当前者与队列拷贝同键 → 滑动过渡）；
// 额外回合拷贝不抑制（再现族照显）
{
  const bar = [
    {actor_id:'1408', name:'白厄', kind:'normal', eta:198},
    {actor_id:'1408', name:'白厄', kind:'normal_extra', eta:98},
    {actor_id:'e1', name:'假人', kind:'normal', eta:200},
  ];
  const vis = barVisibleEntries(bar, '1408', 98, 'rel');
  eq(vis.length === 3 && vis[0].kind === 'current' && vis[1].kind === 'normal_extra' && vis[2].actor_id === 'e1',
     'barVisibleEntries：当前者置顶 + 下一动拷贝抑制 + 额外拷贝保留');
  eq(barVisibleEntries(bar, null, 98, 'rel').length === 3, 'barVisibleEntries：无 pending 全显');
  eq(barVisibleEntries([{actor_id:'1408', kind:'normal', eta:198}], '1408', 98, 'rel').length === 1,
     'barVisibleEntries：唯一拷贝被抑 → 只剩当前者');
}
// 幽灵条预览：星期日战技 immediate → 箭头目标落顶（eta=clock，Δ 负）；
// delay/advance 按 pct×10000÷spd 折 AV；变速 spd/spd_pct 按距离守恒重算；同 actor 效果链连施
{
  const barById = {'1408': {actor_id:'1408', name:'白厄', eta:196.1, spd:100}, 'e1': {actor_id:'e1', name:'假人', eta:150, spd:100}};
  const g1 = ghostEntries([{who:'target', kind:'immediate', pct:1}], '1408', ['1408'], ['e1'], '1313', barById, 98);
  eq(g1.length === 1 && g1[0].newEta === 98 && Math.abs(g1[0].delta + 98.1) < 1e-9 && g1[0].kind === 'immediate',
     'ghost immediate：目标落顶 Δ=-98.1');
  eq(g1[0].name === '白厄', 'ghost 带名字（曾丢 name 渲染 undefined）');
  const g2 = ghostEntries([{who:'target', kind:'delay', pct:0.3}], 'e1', ['1408'], ['e1'], '1313', barById, 98);
  eq(g2.length === 1 && g2[0].newEta === 180 && g2[0].delta === 30, 'ghost delay 30%：+30 AV');
  const g3 = ghostEntries([{who:'target', kind:'advance', pct:0.5}], '1408', ['1408'], ['e1'], '1313', barById, 98);
  eq(g3.length === 1 && g3[0].newEta === 146.1, 'ghost advance 50%：eta-50');
  // 变速 flat（征服者 spd+20 族）：eta 202/clock 104.2/spd 119 → 104.2+97.8×119/139 ≈ 187.92
  const g6 = ghostEntries([{who:'target', kind:'spd', delta:20}], '1408', ['1408'], ['e1'], '1313',
     {'1408': {actor_id:'1408', name:'白厄', eta:202, spd:119}}, 104.2);
  eq(g6.length === 1 && Math.abs(g6[0].newEta - (104.2 + 97.8*119/139)) < 1e-6 && g6[0].delta < 0 && g6[0].kind === 'spd',
     'ghost spd flat：距离守恒重算（202→187.9，Δ≈-14.1）');
  // 变速 pct：spd×1.2 → eta 减半方向
  const g7 = ghostEntries([{who:'target', kind:'spd_pct', pct:0.2}], '1408', ['1408'], ['e1'], '1313', barById, 98);
  eq(g7.length === 1 && Math.abs(g7[0].newEta - (98 + 98.1/1.2)) < 1e-6, 'ghost spd_pct：eta-clock 按 1/(1+pct) 折');
  // 同 actor 效果链：先 immediate 落顶，再 spd 变速（R=0 → 仍在顶）
  const g8 = ghostEntries([{who:'target', kind:'immediate', pct:1}, {who:'target', kind:'spd', delta:20}],
     '1408', ['1408'], ['e1'], '1313', barById, 98);
  eq(g8.length === 1 && g8[0].newEta === 98, 'ghost 效果链：immediate+spd 连施仍在顶');
  const g5 = ghostEntries([{who:'self', kind:'extra', pct:1}], null, ['1408'], ['e1'], '1313', barById, 98);
  eq(g5.length === 0, 'ghost self 不在条上（被抑拷贝）→ 跳过');
  const h = ghostEntryHtml({ghostKind:'immediate', delta:-98.1}, '白厄');
  eq(h.includes('白厄') && h.includes('即') && h.includes('-98.1'), 'ghostEntryHtml：名+即+ΔAV');
  // 行动后重跑条预览（owner 裁决）：无 self AV 效果也给本单位下一动落点（clock + 10000/spd）；
  // 有 self 效果时由 av_fx 幽灵承担不重复
  S.actors = {'1313': {actor_type:'character', alive: true}, '1408': {actor_type:'character', alive: true}};
  S.ally_order = ['1313', '1408']; S.enemy_order = [];
  S.pending = {actor_id: '1313', choices: [
    {index: 0, action_id: 's', action_type: 'skill', target_type: 'ally_single', av_fx: []}]};
  aiming = {candidates: ['1408'], arrow: 0, label: '战技', key: 'e', phase2: false, actionIndex: 0};
  const g9 = aimingGhostEntries([{actor_id: '1313', name: '星期日', eta: 98, spd: 120}], 98);
  eq(g9.length === 1 && g9[0].kind === 'rerun' && g9[0].name === '星期日'
     && Math.abs(g9[0].newEta - (98 + 10000/120)) < 1e-6,
     'rerun 幽灵：本单位行动后重跑落点（clock+10000/spd）');
  const h9 = ghostEntryHtml({ghostKind:'rerun', delta:83.3}, '星期日');
  eq(h9.includes('次'), 'ghostEntryHtml rerun 标「次」');
  aiming = null;
}
// 瞄准态按钮行 = visibleChoices 全体原位（follow_up 触发件不作按钮），当前锁定技能带 locked 高亮
S.pending = {choices: [
  {index: 0, action_id: 'b', action_type: 'basic', name: '普攻', target_type: 'single'},
  {index: 1, action_id: 's', action_type: 'skill', name: '战技', target_type: 'blast', skill_point_cost: 1},
  {index: 2, action_id: 'f1', action_type: 'follow_up', name: '触发件', target_type: 'single'},
  {index: 3, action_id: 'u', action_type: 'ultimate', name: '终结技', target_type: 'aoe'},
]};
{
  const btns = visibleChoices().map(c => actBtnHtml(c, keyOf(c), c.index === 1)).join('');
  eq(btns.includes('data-act="0"') && btns.includes('data-act="1"') && !btns.includes('data-act="2"'),
     '瞄准按钮行：Q+E 全体原位，触发件不漏回');
  eq(!btns.includes('data-act="3"'), '瞄准按钮行：ultimate 滤除（正道=金钮/窗口，choices 免费大 trap 埋掉）');
  eq(/act-btn locked" data-act="1"/.test(btns) && !/act-btn locked" data-act="0"/.test(btns),
     '瞄准按钮行：仅当前锁定技能带 locked 高亮');
}
S.pending = null;
// L6 终结技槽位钮（贴卡圆钮）：键位角标 + 终结技名首字 + data-ultnow 委托键；locked=确认态点亮；
// 未就绪=disabled 灰钮带 data-reason（点击/轻点只报原因，悬停/长按看描述）
{
  const h = ultSlotBtnHtml({actor_id:'1313', name:'星期日', ult_name:'轻与伤痕的赞颂', key_hint:'3'});
  eq(h.includes('data-ultnow="1313"') && h.includes('us-key') && h.includes('>3<')
     && h.includes('轻') && h.includes('ult-slot-btn') && !h.includes('disabled'),
     'ultSlotBtnHtml：键位/名首字/委托键');
  const h2 = ultSlotBtnHtml({actor_id:'1313', name:'星期日', ult_name:'轻与伤痕的赞颂', key_hint:'3'}, true);
  eq(h2.includes('ult-slot-btn locked') && !h.includes(' locked'), 'ultSlotBtnHtml locked：确认态点亮');
  const h4 = ultSlotBtnHtml({actor_id:'1408', name:'白厄', ult_name:'永劫燔世，其将背负', key_hint:'1', ready:false, reason:'火种不足'});
  eq(h4.includes('disabled') && h4.includes('data-reason="火种不足"') && h4.includes('data-ultnow="1408"'),
     'ultSlotBtnHtml 未就绪：灰钮带原因');
  const h3 = ultBtnHtml({actor_id:'1313', name:'星期日', ult_name:'轻与伤痕的赞颂', key_hint:'3'}, true);
  eq(h3.includes('ult-btn locked') && h3.includes('data-ult="1313"'), 'ultBtnHtml locked：窗口确认态点亮');
}
console.log('JS_LOGIC_OK');
"""


def test_web_js_pure_logic(tmp_path):
    """node 跑页面脚本 + 断言台（无 node → skip）。"""
    node = shutil.which("node")
    if node is None:
        pytest.skip("本机无 node（JS 逻辑闸跳过；CI 无此依赖）")
    html = INDEX.read_text(encoding="utf-8")
    m = re.search(r"<script>(.*?)</script>", html, re.S)
    assert m, "index.html 缺 <script> 块"
    script = tmp_path / "page.js"
    script.write_text(m.group(1) + "\n;" + _HARNESS, encoding="utf-8")
    r = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0 and "JS_LOGIC_OK" in r.stdout, (
        f"JS 逻辑闸失败：\n{r.stdout}\n{r.stderr}")
