"""Read-only, loopback-only live dashboard for the Veyro Mission Runner (stdlib)."""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import runner

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e9ef;--mute:#8b93a5;--ok:#3ecf8e;--warn:#f5b73d;--bad:#ef5b5b;--info:#6aa6ff;--sel:#243049}
:root[data-theme=light]{--bg:#f5f6f8;--card:#fff;--line:#e1e4ea;--fg:#171a21;--mute:#667085;--ok:#168a5a;--warn:#b7791f;--bad:#c53030;--info:#2563eb;--sel:#e4edff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{display:flex;align-items:center;flex-wrap:wrap;gap:10px 14px;padding:14px 24px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:2}
h1{font-size:17px;margin:0;font-weight:650;letter-spacing:.2px}.sp{flex:1}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);font-size:12px;font-weight:600;background:var(--card)}
.pill i{width:8px;height:8px;border-radius:50%;background:var(--mute)}
.ok i{background:var(--ok)}.warn i{background:var(--warn)}.bad i{background:var(--bad)}.info i{background:var(--info)}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.info{color:var(--info)}.mute{color:var(--mute)}
#status{display:flex;gap:8px;flex-wrap:wrap}
button,select{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:4px 10px;cursor:pointer}
main{padding:20px 24px;display:grid;gap:16px;grid-template-columns:repeat(12,1fr)}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0}
section h2{margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:.8px;color:var(--mute);font-weight:650}
.c12{grid-column:span 12}.c8{grid-column:span 8}.c6{grid-column:span 6}.c4{grid-column:span 4}
@media(max-width:1000px){.c8,.c6,.c4{grid-column:span 12}}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.tile{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.tile b{display:block;font-size:22px;font-weight:650}.tile small{color:var(--mute)}
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.filters label{color:var(--mute);font-size:12px;display:flex;gap:6px;align-items:center}
.board{display:grid;grid-template-columns:repeat(6,minmax(170px,1fr));gap:12px;overflow-x:auto}
.col{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:10px;min-height:110px}
.col h3{margin:0 0 8px;font-size:12px;color:var(--mute);display:flex;justify-content:space-between}
.card{border:1px solid var(--line);background:var(--card);border-radius:8px;padding:8px 10px;margin-bottom:8px;cursor:pointer}
.card.sel{border-color:var(--info);background:var(--sel)}
.card b{display:block;font-size:13px;overflow-wrap:anywhere}.card small{color:var(--mute);display:block;overflow-wrap:anywhere}
.card small.bad{color:var(--bad)}.card small.ok{color:var(--ok)}.card small.warn{color:var(--warn)}
.empty{color:var(--mute);font-style:italic;padding:6px 2px}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);font-size:13px;vertical-align:top;overflow-wrap:anywhere}
th{color:var(--mute);font-weight:600;font-size:12px}tr.click{cursor:pointer}tr.click:hover{background:var(--bg)}
.kv{display:grid;grid-template-columns:150px 1fr;gap:5px 12px}.kv div:nth-child(odd){color:var(--mute)}.kv div{overflow-wrap:anywhere}
code,pre{font-family:ui-monospace,Menlo,monospace;font-size:12px}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.log{max-height:300px;overflow:auto}
"""

JS = r"""
const $=id=>document.getElementById(id);
function el(t,c,x){const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e}
function pill(text,cls){const p=el('span','pill '+cls);p.append(el('i'),document.createTextNode(text));return p}
function clear(n){while(n.firstChild)n.removeChild(n.firstChild)}
function empty(n,msg){n.append(el('div','empty',msg))}
const NA='unavailable';
function kv(n,rows){clear(n);n.className='kv';rows.forEach(([k,v])=>n.append(el('div',0,k),el('div',0,v==null||v===''?NA:String(v))))}
function table(n,head,rows,msg,onrow){clear(n);if(!rows.length)return empty(n,msg);const t=el('table'),h=el('tr');head.forEach(x=>h.append(el('th',0,x)));t.append(h);
 rows.forEach(r=>{const tr=el('tr',onrow?'click':'');if(onrow)tr.onclick=()=>onrow(r);r.forEach(c=>tr.append(c instanceof Node?c:el('td',0,c==null?NA:String(c))));t.append(tr)});n.append(t)}
function td(node){const d=el('td');d.append(node);return d}
function fmtDur(sec){sec=Math.max(0,Math.round(sec));const h=Math.floor(sec/3600),m=Math.floor(sec%3600/60),s=sec%60;return h?h+'h '+m+'m':m?m+'m '+s+'s':s+'s'}

/* Kanban columns requested by the owner. Mapping from what the runner really records:
   QUEUED->READY (backoff shown as a note), RUNNING->IN PROGRESS, RUNNING in post-run verification->IN REVIEW,
   BLOCKED and FAILED->BLOCKED, DONE->DONE. NOT STARTED has no data source, so it is never populated. */
const COLS=['NOT STARTED','READY','IN PROGRESS','IN REVIEW','BLOCKED','DONE'];
function colOf(t){return t.status==='DONE'?'DONE':(t.status==='BLOCKED'||t.status==='FAILED')?'BLOCKED':
 t.status==='RUNNING'?(t.stage==='verifying'?'IN REVIEW':'IN PROGRESS'):'READY'}
const F={module:'',phase:'',status:'',agent:''};
let S=null,SEL=null,fetchedAt=0,theme=localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');
document.documentElement.dataset.theme=theme;
const agentOf=t=>t.role+(t.route&&t.route.primary?' ('+t.route.primary+')':'');
const phaseOf=t=>t.plan_phase||NA;
function visible(t){return(!F.module||t.module===F.module)&&(!F.phase||phaseOf(t)===F.phase)&&(!F.status||colOf(t)===F.status)&&(!F.agent||t.role===F.agent)}
function opts(sel,key,vals){const s=$(sel),cur=F[key];clear(s);s.append(new Option('all',''));vals.forEach(v=>s.append(new Option(v,v)));
 if(cur&&!vals.includes(cur)){F[key]=''}s.value=F[key]}

function baselinePill(s){
 const h=s.health||{},b=s.baseline,pin=s.baseline_pin;
 if(!pin)return pill('Baseline: NOT PINNED (owner step pending)','bad');
 if(pin.error)return pill('Baseline pin unreadable','bad');
 if(!b||h.status==='UNKNOWN')return pill('Baseline: not yet checked by a runner','warn');
 if(h.status==='BLOCKED')return pill('Blocked: '+(h.code||'baseline'),'bad');
 if(h.status==='OK')return s.runner_alive?pill('Baseline verified '+new Date(b.checked_at).toLocaleTimeString(),'ok'):pill('Baseline: last OK '+new Date(b.checked_at).toLocaleTimeString()+' (runner offline - stale)','warn');
 return pill('Baseline: '+(h.status||NA),'warn')}

function render(s){
 S=s;fetchedAt=Date.now();
 const hd=$('status');clear(hd);
 hd.append(pill(s.runner_alive?'Runner live':'Runner offline',s.runner_alive?'ok':'bad'));
 const c=s.control||NA;hd.append(pill('Control: '+c,c==='RUN'?'ok':c==='PAUSE'?'warn':'bad'));
 hd.append(baselinePill(s));
 if(s.state_error)hd.append(pill('State unreadable','bad'));
 $('stamp').textContent='Updated '+new Date().toLocaleTimeString();
 const T=s.tasks,by={};COLS.forEach(k=>by[k]=0);T.forEach(t=>by[colOf(t)]++);
 const r=s.runner||{};
 const tiles=$('tiles');clear(tiles);
 [['Tasks',T.length],['Ready',by['READY']],['In progress',by['IN PROGRESS']],['In review',by['IN REVIEW']],['Blocked',by['BLOCKED']],['Done',by['DONE']],
  ['Modules',new Set(T.map(t=>t.module)).size],['Recoveries',s.recoveries]].forEach(([k,v])=>{const d=el('div','tile');d.append(el('b',0,v),el('small',0,k));tiles.append(d)});
 const hb=el('div','tile');hb.append(el('b','','—'),el('small',0,'Heartbeat'));hb.firstChild.id='hbtile';tiles.append(hb);
 const up=el('div','tile');up.append(el('b','','—'),el('small',0,'Runner uptime'));up.firstChild.id='uptile';tiles.append(up);
 opts('f-module','module',[...new Set(T.map(t=>t.module))].sort());
 opts('f-phase','phase',[...new Set(T.map(phaseOf))].sort());
 opts('f-status','status',COLS);
 opts('f-agent','agent',[...new Set(T.map(t=>t.role))].sort());
 const vis=T.filter(visible);
 const b=$('board');clear(b);
 COLS.forEach(k=>{const col=el('div','col'),hh=el('h3'),items=vis.filter(t=>colOf(t)===k);hh.append(el('span',0,k),el('span',0,items.length));col.append(hh);
  if(k==='NOT STARTED')col.append(el('div','empty','No backlog source is connected: a task exists here only once enqueued, so nothing can be "not started".'));
  else if(!items.length)col.append(el('div','empty','Empty'));
  items.forEach(t=>{const cd=el('div','card'+(t.id===SEL?' sel':''));cd.onclick=()=>{SEL=t.id;render(S)};
   cd.append(el('b',0,t.title),el('small',0,t.module+' · '+phaseOf(t)+' · '+t.role+' · attempt '+t.attempts+'/'+t.max_attempts));
   if(t.status==='FAILED')cd.append(el('small','bad','FAILED (retries exhausted)'));
   if(t.retry_in)cd.append(el('small','warn','retry in '+t.retry_in+'s'));
   if(t.blocked_reason)cd.append(el('small','bad',t.blocked_reason));
   if(t.last_error&&k==='BLOCKED')cd.append(el('small',0,t.last_error.replace((t.blocked_reason||'')+': ','').slice(0,140)));
   if(t.status==='RUNNING'&&t.started_at){const e=el('small','info','');e.dataset.since=t.started_at;e.dataset.label=t.stage==='verifying'?'verifying ':'running ';cd.append(e)}
   if(t.route)cd.append(el('small',t.route.verdict==='VERIFIED'?'ok':'warn','route '+t.route.verdict+(t.route.primary?' · '+t.route.primary:'')));
   col.append(cd)});b.append(col)});
 detail(s);
 const mods={};T.forEach(t=>{const m=mods[t.module]=mods[t.module]||{n:0,up:''};COLS.forEach(k=>m[k]=m[k]||0);m[colOf(t)]++;m.n++;if(t.updated_at>m.up)m.up=t.updated_at});
 table($('modules'),['Module','Tasks','Ready','In progress','In review','Blocked','Done','Last activity'],
  Object.keys(mods).sort().map(m=>[m,mods[m].n,mods[m]['READY'],mods[m]['IN PROGRESS'],mods[m]['IN REVIEW'],mods[m]['BLOCKED'],mods[m]['DONE'],mods[m].up.slice(0,19).replace('T',' ')]),
  'No module has tasks. Modules appear only when tasks are enqueued; no module status is claimed.',row=>{F.module=row[0];render(S)});
 const run=T.filter(t=>t.status==='RUNNING');
 const ops=$('live');clear(ops);
 const wl=s.writer_lock||{};
 const lockTxt=wl.state==='held'?('HELD'+(wl.owner&&wl.owner.task_id?' by task '+wl.owner.task_id:'')+(wl.runner_alive===false?(wl.child_alive?' - runner dead, orphan child still alive':' - runner dead'):'')):wl.state==='free'?'free':NA;
 const k=el('div');ops.append(k);
 kv(k,[['Runner',s.runner?('pid '+r.pid+' @ '+(r.host||NA)):'never started'],['Started',r.started_at],['Writer lock',lockTxt],['Pending commands',s.pending_commands],['Block detail',(s.health||{}).detail]]);
 if(!run.length)ops.append(el('div','empty',s.runner_alive?'Idle: no task is running.':'No task running (runner offline).'));
 run.forEach(t=>{const d=el('div','card');d.onclick=()=>{SEL=t.id;render(S)};d.append(el('b',0,t.title),el('small',0,t.module+' · '+t.role+' · '+(t.stage==='verifying'?'verifying result':'child running')+(t.child_pid?' · child pid '+t.child_pid:'')));
  const e=el('small','info','');e.dataset.since=t.started_at;e.dataset.label='elapsed ';d.append(e);ops.append(d)});
 table($('events'),['Time','Event','Op','Detail'],s.events.slice(0,40).map(e=>{const{ts,kind,op_id,...rest}=e;return[ts.slice(11,19),kind,op_id,JSON.stringify(rest).slice(0,160)]}),'No operations recorded yet.');
 const pin=s.baseline_pin,bl=s.baseline||{};
 const bx=$('baseline');clear(bx);
 if(!pin)empty(bx,'Not pinned. Hashes are trusted only from an out-of-repo pin created by the owner step `runner.py pin-baseline`; until then no dispatch happens.');
 else if(pin.error)empty(bx,pin.error);
 else{const k2=el('div');bx.append(k2);kv(k2,[['Pinned at',pin.pinned_at],['Pinned index sha256',pin.index_sha256.slice(0,16)+'…'],['Pinned sources',pin.sources],['Last runner check',bl.checked_at],['Check result',bl.ok===undefined?null:bl.ok?'match':(bl.reason||'MISMATCH')]]);
  if((bl.sources||[]).length)bx.append(el('div','mute','Per-source: '+bl.sources.map(x=>x.name.slice(0,24)+(x.match?' ✓':' ✗')).join(' · ')))}
 const u=Object.entries(s.usage||{});
 table($('usage'),['Model (as reported)','Runs','Input','Output','Cache','Cost USD (reported)'],u.map(([m,x])=>[m,x.runs,x.input,x.output,x.cache,x.cost_usd.toFixed(4)]),
  'No model usage recorded. Nothing has been dispatched, so no model identity is claimed.');
 const ev=T.filter(t=>t.route).map(t=>[t.route.mr_id,t.module+'/'+t.role,t.route.intended,t.route.primary,td(pill(t.route.verdict,t.route.verdict==='VERIFIED'?'ok':'bad'))]);
 table($('routing'),['MR id','Task','Intended','Resolved primary','Verdict'],ev,'No routing evidence yet. A route is only marked VERIFIED from model identity the CLI reported.');
 ciView(s.ci);
 clock();
}
function link(url,text){if(!url)return el('span',0,text==null?NA:String(text));const a=el('a','',text==null?url:String(text));a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a}
function ciTone(v){return v==='SUCCESS'||v==='success'||v==='pass'||v==='APPROVED'||v==='MERGED'?'ok':v==='FAILURE'||v==='failure'||v==='fail'||v==='CHANGES_REQUESTED'||v==='cancelled'?'bad':'warn'}
function ciView(ci){
 const n=$('ci');clear(n);
 if(!ci){empty(n,'No CI observation yet. The runner has not recorded one (observer unavailable, rate limited, or runner not reloaded). Nothing is reported as passing.');return}
 const st=ci.state||'unavailable',obs=ci.observed_at?new Date(ci.observed_at).toLocaleString():null;
 const head=el('div');head.append(pill(st==='fresh'?'CI data fresh':st==='stale'?'CI data STALE':'CI data unavailable',st==='fresh'?'ok':st==='stale'?'warn':'bad'));n.append(head);
 if(ci.head_matches_local===false)n.append(el('div','empty','Observed remote head '+(ci.head_sha||'').slice(0,12)+' differs from local HEAD '+(ci.local_head||'').slice(0,12)+'. This CI state does not cover unpushed or local work.'));
 else if(ci.head_matches_local==null)n.append(el('div','empty','Local HEAD could not be compared with the observed remote head; do not read this as status of local work.'));
 const k=el('div');n.append(k);
 kv(k,[['Observed',obs?obs+(ci.age_s!=null?' ('+fmtDur(ci.age_s)+' ago)':''):'never'],['Source',ci.source],['Last fetch error',ci.error||(st==='fresh'?'none':null)],
  ['Repository',ci.repo],['Branch',ci.branch],['Observed remote head',ci.head_sha?ci.head_sha.slice(0,12):null],['Local HEAD',ci.local_head?ci.local_head.slice(0,12):null]]);
 const pr=ci.pr,p=el('div');n.append(el('div','mute','Pull request'),p);
 if(!pr)p.append(el('div','empty',ci.observed_at?'No pull request found for this branch.':NA));
 else{const r=el('div');p.append(r);kv(r,[['PR',pr.number!=null?'#'+pr.number:null],['State',pr.state+(pr.draft?' (draft)':'')],['Review',pr.review]]);
  if(pr.url)p.append(link(pr.url,pr.url))}
 n.append(el('div','mute',ci.source==='github-public-api'?'Observed checks (required status not verified)':'Required checks'));
 const cc=el('div');n.append(cc);
 table(cc,['Check','State'],(ci.checks||[]).map(c=>[td(link(c.url,c.name)),td(pill(c.state||NA,st==='fresh'?ciTone(c.state):'warn'))]),ci.source==='github-public-api'?(pr?'No check runs observed for the PR head.':'No check runs read: checks are only read when an open PR exists. Not a pass.'):'No required checks reported for this branch.');
 n.append(el('div','mute','Recent workflow runs'));
 const rr=el('div');n.append(rr);
 table(rr,['Workflow','Result','Commit','Run'],(ci.runs||[]).map(x=>[x.name,x.status==='completed'?x.conclusion:x.status,x.head_sha?x.head_sha.slice(0,8):null,td(link(x.url,'open'))]),'No workflow runs observed.');
 const dep=el('div');n.append(el('div','mute','Environments'),dep);
 kv(dep,[['Staging deployment',ci.staging||'not configured'],['Secrets',ci.secrets||'not configured'],['Rollback',ci.rollback||'not configured']]);
}
function detail(s){
 const n=$('detail');clear(n);
 const t=s.tasks.find(x=>x.id===SEL);
 if(!t){empty(n,SEL?'Selected task no longer exists.':'Select a card to see its full record and evidence.');return}
 const k=el('div');n.append(k);const ev=t.evidence||{},rt=t.route||{};
 kv(k,[['Task',t.id],['Title',t.title],['Module',t.module],['Plan phase',t.plan_phase],['Agent role',t.role],['Runner status',t.status+(t.stage?' / '+t.stage:'')],['Board column',colOf(t)],
  ['Attempts',t.attempts+'/'+t.max_attempts],['Blocked reason',t.blocked_reason],['Last error',t.last_error],['Created',t.created_at],['Started',t.started_at],['Finished',t.finished_at],
  ['Allowed paths',(t.allowed_paths||[]).join(', ')||'none (read-only)'],['Expected changes',(t.expected_changes||[]).join(', ')],['Verify command',t.verify_cmd&&t.verify_cmd.length?t.verify_cmd.join(' '):null],
  ['Route verdict',rt.verdict?rt.verdict+' - '+rt.basis:null],['Models used',(rt.models||[]).map(m=>m.model+' '+m.tokens+' tok').join(', ')],
  ['Files changed',(ev.changed||[]).map(c=>c.path+' ('+(c.sha256?c.sha256.slice(0,10):'deleted')+')').join(', ')||(t.evidence?'none':null)],
  ['Verification',ev.verify?('exit '+ev.verify.exit):null],['Review outcome',ev.review_outcome],['Violations',(ev.violations||[]).join(', ')],
  ['Isolation',ev.isolation?ev.isolation.sandbox+', '+ev.isolation.permission_mode:null]]);
 if(ev.verify&&ev.verify.tail){n.append(el('div','mute','Verification output (tail)'));n.append(el('pre',0,ev.verify.tail))}
 const mine=s.events.filter(e=>e.task_id===t.id||(e.op_id||'').startsWith(t.id+':')).slice(0,15);
 n.append(el('div','mute','Recent events for this task (window of last 200 events)'));
 if(mine.length)mine.forEach(e=>n.append(el('div',0,e.ts.slice(11,19)+'  '+e.kind+'  '+(e.op_id||''))));else n.append(el('div','empty','No events in the current window.'));
}
function clock(){
 if(!S)return;const now=Date.now();
 const age=S.heartbeat_age_s==null?null:S.heartbeat_age_s+(now-fetchedAt)/1000;
 const hb=$('hbtile');if(hb)hb.textContent=age==null?NA:fmtDur(age)+' ago';
 const hh=$('hbhead');hh.textContent=age==null?'No heartbeat recorded':'Heartbeat '+fmtDur(age)+' ago'+(S.runner_alive?'':' (runner offline)');
 const up=$('uptile');if(up)up.textContent=S.runner&&S.runner.started_at&&S.runner_alive?fmtDur((now-Date.parse(S.runner.started_at))/1000):NA;
 document.querySelectorAll('[data-since]').forEach(e=>{e.textContent=e.dataset.label+fmtDur((now-Date.parse(e.dataset.since))/1000)});
}
async function tick(){
 try{const r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)throw 0;render(await r.json());$('conn').className='pill ok';$('conn').lastChild.textContent='Live'}
 catch(e){$('conn').className='pill bad';$('conn').lastChild.textContent='Dashboard unreachable - data is stale'}
}
[['f-module','module'],['f-phase','phase'],['f-status','status'],['f-agent','agent']].forEach(([id,k])=>{$(id).onchange=e=>{F[k]=e.target.value;if(S)render(S)}});
$('f-reset').onclick=()=>{Object.keys(F).forEach(k=>F[k]='');if(S)render(S)};
$('theme').onclick=()=>{theme=theme==='dark'?'light':'dark';localStorage.setItem('theme',theme);document.documentElement.dataset.theme=theme};
tick();setInterval(tick,3000);setInterval(clock,1000);
"""

HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Veyro Mission Runner</title><link rel="stylesheet" href="/app.css"></head><body>
<header><h1>Veyro Mission Runner</h1><div id="status"></div><div class="sp"></div>
<small id="hbhead" class="mute"></small>
<span id="conn" class="pill"><i></i><span>Connecting…</span></span><small id="stamp" class="mute"></small>
<button id="theme" title="Toggle dark / light">Dark / Light</button></header>
<main>
<section class="c12"><h2>Overview</h2><div id="tiles" class="tiles"></div></section>
<section class="c12"><h2>Kanban</h2>
<div class="filters"><label>Module <select id="f-module"></select></label><label>Phase <select id="f-phase"></select></label>
<label>Status <select id="f-status"></select></label><label>Agent <select id="f-agent"></select></label><button id="f-reset">Reset filters</button></div>
<div id="board" class="board" style="margin-top:12px"></div></section>
<section class="c6"><h2>Task detail</h2><div id="detail"></div></section>
<section class="c6"><h2>Live operations</h2><div id="live"></div></section>
<section class="c12"><h2>Module details</h2><div id="modules"></div></section>
<section class="c6"><h2>Baseline (out-of-repo pin)</h2><div id="baseline"></div></section>
<section class="c6"><h2>CI</h2><div id="ci"></div></section>
<section class="c6"><h2>Usage</h2><div id="usage"></div></section>
<section class="c6"><h2>Model routing evidence</h2><div id="routing"></div></section>
<section class="c12"><h2>Recent events</h2><div id="events" class="log"></div></section>
</main><script src="/app.js"></script></body></html>"""

ASSETS = {"/": ("text/html; charset=utf-8", HTML), "/app.css": ("text/css; charset=utf-8", CSS),
          "/app.js": ("text/javascript; charset=utf-8", JS)}


def make_handler(cfg, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "VeyroDash"

        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body, extra=()):
            b = body.encode()
            self.send_response(code)
            for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("Cache-Control", "no-store"),
                         ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"),
                         ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'"),
                         *extra):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.headers.get("Host") not in allowed_hosts:  # DNS-rebinding guard
                return self._send(403, "text/plain", "forbidden host")
            path = self.path.split("?")[0]
            if path == "/api/state":
                return self._send(200, "application/json", json.dumps(runner.snapshot(cfg)))
            if path in ASSETS:
                return self._send(200, *ASSETS[path])
            self._send(404, "text/plain", "not found")

        def _no_write(self):
            self._send(405, "text/plain", "dashboard is read-only", [("Allow", "GET")])

        do_POST = do_PUT = do_DELETE = do_PATCH = _no_write

    return H


def make_server(cfg, port=8766):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(cfg, 0))  # bound first so port 0 resolves
    srv.RequestHandlerClass = make_handler(cfg, srv.server_address[1])
    srv.daemon_threads = True
    return srv


def serve(cfg, port):
    srv = make_server(cfg, port)
    print(f"dashboard on http://127.0.0.1:{srv.server_address[1]}/ (read-only, loopback only)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
