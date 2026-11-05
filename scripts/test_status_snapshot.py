"""Real-source state UI, same-record filters and failure/conflict regressions."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'_site')))
threading.Thread(target=server.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(server.server_port)
out=ROOT.parent/'status-preview';out.mkdir(exist_ok=True);report={};errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=browser.new_page(viewport={'width':1440,'height':1000});p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas');assert p.evaluate('statusRecords.size')==938
  report['validity']={}
  for key,n,apps in [('source-active',491,360),('source-inactive',340,340),('source-pending',107,107),('unverified',0,0)]:
   p.locator('#law-status').select_option(key)
   assert p.evaluate('currentFiltered().length')==n
   assert p.evaluate('new Set(currentFiltered().map(d=>d.applicationNumber)).size')==apps
   assert p.evaluate('panoramaData(currentFiltered()).scoped.length')==n
   report['validity'][key]={'documents':n,'applications':apps}
  p.locator('#current-clear').click()
  raw={'授权':491,'未缴年费':112,'驳回':213,'实质审查':104,'撤回':6,'全部无效':3,'期限届满':4,'公开':3,'避重放弃':2}
  for state,n in raw.items():
   p.locator('#law-raw').select_option(state);assert p.evaluate('currentFiltered().length')==n
  p.locator('#current-clear').click();p.locator('#law-status').select_option('source-active');p.locator('#law-region').select_option('CN');p.locator('#law-stage').select_option('published')
  assert p.evaluate('currentFiltered().every(d=>sourceStatus(d).validityRaw==="有效"&&patentLaw(d).stage==="published"&&patentLaw(d).regionCode==="CN")')
  combined=p.evaluate('currentFiltered().length');assert combined==137
  p.locator('a[href="#patents"]').first.click();p.wait_for_selector('.current-library');assert p.evaluate('currentFiltered().length')==137
  assert 'IncoPat 2026-11-03' in p.locator('.law-badge').first.inner_text()
  p.locator('.current-library article a').first.click();p.wait_for_selector('.law-panel')
  detail=p.locator('.law-panel').inner_text()
  assert all(x in detail for x in ['授权','有效','2026-11-03','尚未核验','原资料基线状态','当前法律状态未核验'])
  assert p.locator('.pdf-links').count()>0
  p.locator('.law-panel').screenshot(path=str(out/'status-detail.png'))
  # All members read their own matching record; official territory is never inferred.
  report['versions']=p.evaluate('''()=>{const apps=new Map();for(const d of currentDocs){const l=patentLaw(d);if(l.verifiedAt||l.verifiedActiveRegions.length||l.verifiedGrantRegions.length)throw Error('invented official status');if(l.observation.applicationNumber!==d.applicationNumber)throw Error('wrong association');const v=[l.observation.statusRaw,l.observation.validityRaw].join('/');if(apps.has(d.applicationNumber)&&apps.get(d.applicationNumber)!==v)throw Error('version conflict');apps.set(d.applicationNumber,v);}return {documents:currentDocs.length,applications:apps.size,officialVerified:0};}''')
  # History remains separate even when its status conflicts with source snapshot.
  assert p.evaluate('''()=>{const d=currentDocs.find(d=>sourceStatus(d).validityRaw==='失效');const old=byClaim[d.id];byClaim[d.id]={...(old||{}),statusSnapshot:{provider:'Google Patents',displayedStatus:'Active',checkedAt:'2026-11-01',sourceUrl:'https://patents.google.com/patent/'+d.id}};const html=lawDetails(d);byClaim[d.id]=old;return html.includes('Active')&&html.includes('独立保留')&&html.includes('失效')&&html.includes('不同来源');}''')
  # Reject unauthorized fields, duplicate IDs, application mismatch and version conflicts.
  assert p.evaluate('''()=>{let failures=0;for(const mutate of [s=>s.records[0].privatePath='test',s=>s.records.push(s.records[0]),s=>s.records[0].applicationNumber='wrong',s=>s.officialVerified=true,s=>{const r=s.records.find((r,i)=>s.records.some((x,j)=>i!==j&&x.applicationNumber===r.applicationNumber));r.statusRaw='不同状态';}]){const s=structuredClone(statusSnapshot);mutate(s);try{validateStatusSnapshot(s,currentDocs);}catch{failures++;}}return failures===5;}''')
  p.goto(url+'/#products',wait_until='networkidle');p.wait_for_selector('.pm-canvas');p.locator('#law-status').select_option('source-inactive');p.locator('a[href="#updates"]').first.click();p.wait_for_selector("#materials-notes");p.screenshot(path=str(out/'status-filters.png'),full_page=True)
  # Phone filters and detail.
  m=browser.new_page(viewport={'width':390,'height':844});m.goto(url,wait_until='networkidle');m.wait_for_selector('.pm-canvas');m.locator('[data-panel="filters"]').click();m.locator('#law-raw').select_option('期限届满');assert m.evaluate('currentFiltered().length')==4;m.locator('[data-panel="filters"]').click();assert m.evaluate('document.documentElement.scrollWidth<=innerWidth');m.screenshot(path=str(out/'status-mobile.png'),full_page=True)
  for kind in ['missing','conflict']:
   q=browser.new_page();payload=json.loads((ROOT/'_site/data/incopat-status-snapshot.json').read_text());payload['records'][0]['applicationNumber']='wrong'
   q.route('**/incopat-status-snapshot.json',lambda route:route.fulfill(status=404,body='missing') if kind=='missing' else route.fulfill(body=json.dumps(payload),content_type='application/json'))
   q.goto(url,wait_until='networkidle');q.wait_for_selector('.pm-canvas');assert q.evaluate('statusRecords.size')==0;assert q.evaluate('currentDocs.length')==938;assert '关联校验失败' in q.locator('.source-status-note').inner_text();q.close()
  assert not errors,errors
  report.update(status='pass',sourceStatus=raw,combinedPublishedActive=combined,missingAndConflictFailClosed=True,historicalSourcesSeparated=True,privacyWhitelistRejected=True,pageErrors=errors)
  browser.close()
finally:server.shutdown()
(ROOT/'reports/status-ui-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS: source status UI, counts, versions, raw filters, failure paths, desktop/mobile')
