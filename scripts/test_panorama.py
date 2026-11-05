"""Real-data panorama/drilldown and same-record legal filter acceptance."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'_site')));threading.Thread(target=server.serve_forever,daemon=True).start()
out=ROOT.parent/'panorama-preview';out.mkdir(exist_ok=True)
report={}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:'+str(server.server_port),wait_until='networkidle');page.wait_for_selector('.pm-canvas')
  assert page.locator('#current-product').input_value()==''
  assert page.locator('.pm-heading h2').inner_text()=='华测导航产品专利全景'
  assert page.locator('.pm-node.root').inner_text().startswith('华测导航产品专利全景')
  report['overview']=page.evaluate('''()=>{const m=panoramaData(currentFiltered()),ids=m.groups.flatMap(g=>g.children.map(n=>n.id));return {productIds:ids,unique:new Set(ids).size,documents:currentFiltered().length,applications:new Set(currentFiltered().map(d=>d.applicationNumber)).size};}''')
  assert report['overview']['unique']==16 and len(report['overview']['productIds'])==16
  page.locator('[data-pm-zoom="fit"]').click();page.locator('.panorama-workspace').screenshot(path=str(out/'all-products.png'))
  page.locator('#current-product').select_option('agriculture');assert page.locator('.pm-heading h2').inner_text()=='农机自动驾驶与作业系统'
  page.locator('#current-product').select_option('');assert page.locator('.pm-heading h2').inner_text()=='华测导航产品专利全景'
  report['levels']=page.evaluate('''()=>{const out=[];for(const p of primaryData.categories){currentFilter.product=p.id;panoramaReset(p.id);currentRender();const base=panoramaData(currentFiltered());if(base.title!==p.name)throw Error('product '+p.id);let paths=0,topics=0,leaves=0;for(const form of ['method','structure','design']){panorama={...panorama,level:'form',form,path:'',topic:''};const fm=panoramaData(currentFiltered());for(const path of fm.nodes){paths++;panorama={...panorama,...path.action};const pm=panoramaData(currentFiltered());for(const topic of pm.nodes){topics++;panorama={...panorama,...topic.action};const tm=panoramaData(currentFiltered());if(tm.scoped.length!==tm.nodes.length)throw Error('count mismatch');if(!tm.nodes.length)throw Error('empty '+p.id+topic.id);for(const n of tm.nodes)if(!currentById[n.patent])throw Error('unknown document');leaves+=tm.nodes.length;panorama.level='path';}panorama.level='form';}}out.push({product:p.id,paths,topics,leafOccurrences:leaves});}panoramaReset();currentFilter.product='';currentRender();return out;}''')
  # Navigate actual controls, then restore zoom when returning.
  page.locator('#current-product').select_option('gnss')
  page.locator('[data-pm-zoom="in"]').click();zoom=page.locator('.pm-viewport').get_attribute('data-zoom')
  page.locator('.pm-node.leaf button').first.click();assert page.evaluate('panorama.level')=='path'
  pathTitle=page.locator('.pm-heading h2').inner_text();page.locator('.pm-node.leaf button').first.click();assert page.evaluate('panorama.level')=='topic'
  assert page.locator('[data-pm-patent]').count()>1
  page.locator('[data-pm-zoom="fit"]').click();page.locator('.panorama-workspace').screenshot(path=str(out/'subpath-map.png'))
  total=page.evaluate('panoramaData(currentFiltered()).nodes.length');seen=set()
  while True:
   seen.update(page.locator('[data-pm-patent]').evaluate_all('(xs)=>xs.map(x=>x.dataset.pmPatent)'))
   nxt=page.locator('[data-pm-page="1"]')
   if not nxt.count() or nxt.is_disabled():break
   nxt.click()
  assert len(seen)==total
  page.locator('[data-pm-patent]').first.click();assert page.locator('#workspace-details').is_visible()
  assert page.locator('#workspace-details .law-panel').count()==1
  assert '尚未核验' in page.locator('#workspace-details .law-panel').inner_text()
  page.locator('#workspace-details .law-panel').screenshot(path=str(out/'legal-region-details.png'))
  page.locator('[data-detail-clear]').click();assert page.evaluate('panorama.level')=='topic'
  page.locator('[data-pm-back]').click();assert page.locator('.pm-heading h2').inner_text()==pathTitle
  page.locator('[data-pm-back]').click();assert page.evaluate('panorama.level')=='product';assert page.locator('.pm-viewport').get_attribute('data-zoom')==zoom
  page.locator('[data-pm-home]').click();assert page.locator('#current-product').input_value()==''
  page.locator('#law-stage').select_option('published');assert page.evaluate('currentFiltered().length')==463
  page.locator('#law-region').select_option('CN');assert page.evaluate('currentFiltered().length')==463
  page.locator('#law-status').select_option('unverified');assert page.evaluate('currentFiltered().length')==0
  page.locator('#current-clear').click();assert page.evaluate('currentFiltered().length')==938
  report['legal']=page.evaluate('''()=>{const wo=patentLaw({id:'WO2026000001A1',country:'中国'}),ep=patentLaw({id:'EP1234567B1'}),bad=patentLaw({id:'CN123A',country:'美国'}),missing=patentLaw({id:''});if(wo.verifiedActiveRegions.length||ep.verifiedActiveRegions.length||wo.verifiedAt||missing.verifiedAt)throw Error('false verification');if(bad.regionCode!=='unknown')throw Error('conflict');return {records:currentDocs.length,verified:currentDocs.filter(d=>patentLaw(d).verifiedAt).length,WO:wo.region,EP:ep.region,conflict:bad.region};}''')
  # Actual background drag and native fullscreen.
  page.locator('[data-pm-zoom="in"]').click()
  page.locator('[data-pm-zoom="in"]').click()
  page.locator('.pm-viewport').scroll_into_view_if_needed()
  page.locator('.pm-viewport').evaluate('(e)=>e.scrollLeft=0')
  box=page.locator('.pm-viewport').bounding_box()
  before=page.locator('.pm-viewport').evaluate('(e)=>e.scrollLeft')
  page.mouse.move(box['x']+box['width']/2,box['y']+12)
  page.mouse.down();page.mouse.move(box['x']+box['width']/2-80,box['y']+12,steps=8);page.mouse.up()
  assert page.locator('.pm-viewport').evaluate('(e)=>e.scrollLeft')>before
  page.locator('[data-pm-full]').click()
  page.wait_for_function('document.fullscreenElement || document.querySelector(".pm-expanded")')
  page.locator('[data-pm-full]').click()
  page.wait_for_function('!document.fullscreenElement && !document.querySelector(".pm-expanded")')
  report['dragAndFullscreen']=True
  # Search and mobile use on real dense map.
  page.locator('[data-pm-home]').click();page.locator('#pm-locate').fill('农机');page.locator('[data-pm-locate]').click();assert page.locator('.located').count()==1
  page.locator('#current-q').fill('CN104697526A');assert page.evaluate('currentFiltered().length')==1
  page.locator('#current-clear').click()
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  page.locator('#current-product').select_option('survey');page.locator('.pm-node.leaf button').first.click();page.locator('.pm-node.leaf button').first.click();assert page.evaluate('panorama.level')=='topic'
  page.locator('[data-pm-patent]').first.click();assert page.locator('#workspace-details .law-panel').is_visible();page.locator('[data-detail-clear]').click()
  page.locator('.panorama-workspace').screenshot(path=str(out/'mobile-subpath.png'))
  assert not errors,errors
  report.update(status='pass',nodePaginationComplete=True,returnZoomPreserved=True,productSelectorRootSynchronized=True,sameRecordFilters=True,mobileNoOverflow=True,pageErrors=errors)
  browser.close()
finally:server.shutdown()
(ROOT/'reports/panorama-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS: panorama, 16-product drilldown, pagination, legal filters, desktop/mobile')
