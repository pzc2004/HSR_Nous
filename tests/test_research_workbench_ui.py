from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).parent.parent / "src" / "hsr_nous" / "research" / "workbench" / "web_static" / "index.html"

_HARNESS = r"""
function eq(cond,msg){if(!cond)throw new Error(msg);}
eq(esc('<img src=x>')==='&lt;img src=x&gt;','html escape');
eq(esc('"\'')==='&quot;&#39;','quote escape');
eq(statusZh('running')==='运行中' && statusZh('other')==='other','status labels');
eq(fmt(12345.6)==='12,346' && fmt(1.234)=== '1.23' && fmt('bad')==='—','number formatting');
eq(pct(0.983)==='98.3%' && pct('bad')==='—','percent formatting');
const id='a'.repeat(64);
eq(taskFromHash('#/task/'+id)===id && taskHash(id)==='#/task/'+id,'task hash roundtrip');
eq(taskFromHash('#/task/xyz')===null && taskFromHash('#/other/'+id)===null,'invalid hash');
const rows=[
 {contract_id:'positive',dev_rank:1,selected:true,dev:{effect:12},holdout_adjusted:{effect:10,confidence_interval:{lower:5,upper:15}},
  selection_reason:'dev selected; holdout adjusted CI excludes 0',trial_id:'t1',report_id:'r1',status:'accepted'},
 {contract_id:'negative',dev_rank:2,selected:false,dev:{effect:-4},holdout_adjusted:{effect:-5,confidence_interval:{lower:-10,upper:0}},
  selection_reason:'not selected by dev',trial_id:'t2',report_id:'r2',status:'accepted'},
 {contract_id:'zero',dev_rank:3,selected:false,dev:{effect:0},holdout_adjusted:{effect:0,confidence_interval:{lower:-1,upper:1}},
  selection_reason:'holdout adjusted CI contains 0',trial_id:'t3',report_id:'r3',status:'inconclusive'},
];
const chart=effectChart(rows);
eq(chart.includes('class="axis"') && chart.includes('positive') && chart.includes('negative'),'chart labels and zero axis');
eq(chart.includes('selected-ci') && chart.includes('selected-effect'),'selected chart styling');
const centers=[...chart.matchAll(/cx="([0-9.\-]+)"/g)].map(m=>Number(m[1]));
const center=(155+610)/2;
eq(centers[0]>center && centers[1]<center && centers[2]===center,'positive negative zero scales');
eq(candidateRows({candidates:rows}).includes('dev selected') && candidateRows({candidates:rows}).includes('holdout effect')===false,'candidate table semantics');
eq(effectChart([]).includes('没有可绘制'),'chart empty state');
const dist={minimum:0,maximum:100,p5:10,p50:50,p95:90,mean:42,n:16};
const range=rangeChart(dist);
eq(range.includes('left:10%') && range.includes('width:80%') && range.includes('left:50%'),'distribution range scale');
eq(distributionBlock(dist).includes('mean <b>42.00</b>') && distributionBlock(dist).includes('n <b>16</b>'),'distribution block');
eq(distributionBlock(null).includes('无有效分布'),'distribution empty');
const same=rangeChart({minimum:5,maximum:5,p5:5,p50:5,p95:5});
eq(!same.includes('NaN'),'zero width distribution');
const actors=actorDamageRows({baseline:{holdout:{1308:{display_name:'黄泉',status:'present',n:16,distribution:{mean:100}}}},variant:{holdout:{1406:{display_name:'赛飞儿',status:'absent',n:0,distribution:null}}}});
eq(actors.includes('黄泉') && actors.includes('赛飞儿') && actors.includes('present') && actors.includes('absent'),'actor damage rows');
const detail=detailHtml({kind:'modifier',status:'resolved',evidence:{modifier_id:'m1',details:{name:'测试增益',stacks:2,duration:3,stat_effects:{atk_pct:0.5}}}});
eq(detail.includes('测试增益') && detail.includes('stacks') && detail.includes('atk_pct'),'modifier detail');
(async()=>{
  Object.assign(state,{task:{task_id:'t1'},trialReport:{keep:1},selectedCandidate:'c',currentDrilldown:{keep:1},run:{keep:1},detail:{keep:1},report:null});
  renderAll=()=>{};
  api=async path=>{
    if(path.endsWith('/events'))return {events:[]};
    const id=path.split('/').pop();
    return {task_id:id,candidate_set:{question:'q'},candidate_set_id:'s',status:'running',artifact_status:'partial',attempt:1,completed_runs:1,total_runs:10,report_id:null,candidates:[],error:null};
  };
  await selectTask('t1');
  eq(state.trialReport.keep===1 && state.run.keep===1 && state.detail.keep===1,'refresh preserves selection');
  await selectTask('t2');
  eq(state.trialReport===null && state.run===null && state.detail===null,'switch resets selection');
  console.log('WORKBENCH_JS_LOGIC_OK');
})().catch(error=>{throw error});
"""


def test_workbench_js_pure_logic(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("本机无 node（研究台 JS 逻辑闸跳过）")
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match, "研究台缺 script 块"
    script = tmp_path / "workbench.js"
    script.write_text(match.group(1) + "\n;" + _HARNESS, encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and "WORKBENCH_JS_LOGIC_OK" in result.stdout, (
        f"研究台 JS 逻辑闸失败：\n{result.stdout}\n{result.stderr}"
    )
