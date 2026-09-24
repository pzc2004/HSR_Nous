"""打标 DAG 可视化（ops/annotator/web）——流水线形态实时渲染，零硬编码.

数据源唯一 = runs 目录状态流（events.jsonl + 节点缓存记录）：结构（declared 的 id/kind/service/deps）
与状态（running/cached/done/failed）全从事件重建，动态扇出节点与静态节点同权在册。
前端按图结构现场分层（最长路径）布局，任何 DAG 形状都能渲——打标 DAG 只是第一租户。

启动：`bash scripts/annotator.sh dag [--port 8010]`（runs_root 缺省 data/annotator/runs）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RUNS_ROOT = ROOT / "data/annotator/runs"


def _read_events(run_dir: Path) -> List[Dict[str, Any]]:
    p = run_dir / "events.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _graph_from_events(run_dir: Path) -> Dict[str, Any]:
    """事件流 → 图快照：declared 定结构，末次事件定状态；值预览从节点缓存记录补。"""
    nodes: Dict[str, Dict[str, Any]] = {}
    for e in _read_events(run_dir):
        nid = e.get("node", "")
        if not nid:
            continue
        if e["event"] == "declared":
            nodes[nid] = {"id": nid, "kind": e.get("kind", ""), "service": e.get("service", ""),
                          "deps": e.get("deps", []),
                          "status": "pending", "error": "", "value_preview": ""}
        if nid in nodes:
            nodes[nid]["status"] = e["event"]
            if e["event"] == "failed":
                nodes[nid]["error"] = e.get("error", "")
    for nid, n in nodes.items():
        rec = run_dir / f"{nid}.json"
        if rec.exists():
            try:
                n["value_preview"] = json.dumps(
                    json.loads(rec.read_text(encoding="utf-8")).get("value"),
                    ensure_ascii=False, default=str)[:200]
            except (json.JSONDecodeError, OSError):
                pass
    edges = [[d, nid] for nid, n in nodes.items() for d in n["deps"]]
    return {"nodes": list(nodes.values()), "edges": edges, "run": run_dir.name}


def create_app(runs_root: "str | Path" = DEFAULT_RUNS_ROOT) -> FastAPI:
    runs_root = Path(runs_root)
    app = FastAPI(title="打标 DAG 可视化")

    @app.get("/api/runs")
    def list_runs() -> Dict[str, Any]:
        if not runs_root.exists():
            return {"runs": []}
        runs = []
        for d in sorted(runs_root.iterdir()):
            if not d.is_dir():
                continue
            events = _read_events(d)
            statuses: Dict[str, int] = {}
            for e in events:
                statuses[e["event"]] = statuses.get(e["event"], 0) + 1
            runs.append({"cid": d.name, "events": len(events),
                         "last_t": events[-1]["t"] if events else 0, "statuses": statuses})
        return {"runs": runs}

    @app.get("/api/graph/{cid}")
    def graph(cid: str) -> Dict[str, Any]:
        run_dir = runs_root / cid
        if not run_dir.is_dir():
            return {"nodes": [], "edges": [], "run": cid, "error": "run 不存在"}
        return _graph_from_events(run_dir)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    return app


_INDEX_HTML = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<title>打标 DAG 可视化</title><style>
body{background:#0d1117;color:#c9d1d9;font:13px/1.5 ui-monospace,monospace;margin:0}
#top{padding:8px 12px;border-bottom:1px solid #30363d;display:flex;gap:12px;align-items:center}
select{background:#161b22;color:#c9d1d9;border:1px solid #30363d;padding:2px 8px}
#wrap{display:flex;height:calc(100vh - 42px)}#svg{flex:1;overflow:auto}
#detail{width:340px;border-left:1px solid #30363d;padding:10px;white-space:pre-wrap;
word-break:break-all;overflow:auto}
.node{cursor:pointer}.node rect{stroke-width:1.5;rx:6}
.pending{fill:#161b22;stroke:#8b949e}.running{fill:#0c2d6b;stroke:#58a6ff}
.cached{fill:#0d3d3d;stroke:#39c5cf}.done{fill:#0d3b1e;stroke:#3fb950}
.failed{fill:#4d1215;stroke:#f85149}.k-llm{stroke-dasharray:4 2}.k-gate{stroke-width:3}
text{fill:#c9d1d9;font-size:11px;pointer-events:none}.edge{stroke:#8b949e;stroke-width:1.2;
marker-end:url(#arr)}.muted{color:#8b949e}
</style></head><body>
<div id="top"><b>DAG 流水线</b><span class="muted">run:</span>
<select id="run"></select><span id="meta" class="muted"></span></div>
<div id="wrap"><div id="svg"></div><div id="detail">点节点看详情（状态/错误/值预览）</div></div>
<script>
const S={pending:'pending',running:'running',cached:'cached',done:'done',failed:'failed'};
let cur='';
async function j(u){return (await fetch(u)).json()}
function layout(g){ // 最长路径分层 + 层内居中横铺——纯结构，无硬编码
  const dep=new Map(g.nodes.map(n=>[n.id,n.deps])), depth={};
  const d=id=>depth[id]??(depth[id]=dep.get(id)?.length?1+Math.max(...dep.get(id).map(d)):0);
  g.nodes.forEach(n=>d(n.id));
  const layers={}; g.nodes.forEach(n=>{(layers[depth[n.id]]??=[]).push(n.id)});
  const W=170,H=70, maxCount=Math.max(...Object.values(layers).map(a=>a.length),1);
  const pos={};
  Object.entries(layers).forEach(([l,ids])=>ids.forEach((id,i)=>{
    pos[id]={x:80+(maxCount-ids.length)*W/2+i*W, y:36+l*H};   // 层内居中：主链竖、支链横
  }));
  return {pos, W:160+maxCount*W+220, H:80+Object.keys(layers).length*H};  // 右侧留弧线位
}
async function draw(){
  if(!cur)return; const g=await j('/api/graph/'+cur);
  document.getElementById('meta').textContent=
    `${g.nodes.length} 节点 ${g.edges.length} 边`;
  const L=layout(g), pos=L.pos, svg=document.getElementById('svg');
  let s=`<svg width="${L.W}" height="${L.H}" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3"
  orient="auto"><path d="M0,0 L7,3 L0,6 z" fill="#8b949e"/></marker></defs>`;
  const rowGap=70;
  for(const [a,b] of g.edges){const p1=pos[a],p2=pos[b];if(!p1||!p2)continue;
    const x1=p1.x+60,y1=p1.y+34,x2=p2.x+60,y2=p2.y;
    const dy=p2.y-p1.y;
    if(dy>0 && dy<=rowGap && p1.x===p2.x){   // 相邻同列：竖直线（无中间节点遮挡）
      s+=`<line class="edge" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    }else if(dy>0 && p1.x!==p2.x && dy<=rowGap){  // 相邻跨列：短斜线
      s+=`<line class="edge" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
    }else{          // 跨行快线/回边：右侧弧线，跨幅越大弧越外（快线可见不压节点）
      const bulge=44+Math.min(8,Math.abs(Math.round(dy/rowGap))-1)*24;
      const mx=Math.max(x1,x2)+bulge;
      s+=`<path class="edge" d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}" fill="none"/>`;
    }}
  for(const n of g.nodes){const p=pos[n.id];
    s+=`<g class="node" onclick="show('${n.id}')">
    <rect class="${n.status} k-${n.kind}" x="${p.x}" y="${p.y}" width="120" height="34" rx="6"/>
    <text x="${p.x+8}" y="${p.y+14}">${n.id}</text>
    <text x="${p.x+8}" y="${p.y+28}" class="muted">${n.kind||''} · ${n.status}</text></g>`}
  svg.innerHTML=s+'</svg>'; window._g=g;
}
window.show=id=>{const n=window._g.nodes.find(x=>x.id===id);
  document.getElementById('detail').textContent=
  `${n.id}\\nkind: ${n.kind||'-'}  service: ${n.service||'-'}\\nstatus: ${n.status}\\n`+
  (n.error?`error: ${n.error}\\n`:'')+(n.value_preview?`value: ${n.value_preview}`:'')};
async function runs(){const r=await j('/api/runs');const sel=document.getElementById('run');
  sel.innerHTML=r.runs.map(x=>`<option ${x.cid===cur?'selected':''}>${x.cid}</option>`).join('');
  if(!cur&&r.runs.length)cur=r.runs[r.runs.length-1].cid;
  sel.onchange=()=>{cur=sel.value;draw()};draw();}
runs(); setInterval(()=>{draw()},1500);
</script></body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="打标 DAG 可视化")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--runs-root", default=str(DEFAULT_RUNS_ROOT))
    args = parser.parse_args()
    import uvicorn

    print(f"打标 DAG 可视化：http://127.0.0.1:{args.port}（runs_root={args.runs_root}）")
    uvicorn.run(create_app(args.runs_root), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
