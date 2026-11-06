"""Compare actual filter result IDs with the prior release; exercise relocated controls."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import threading,json,hashlib
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT.parent/'top-filters-preview';OUT.mkdir(exist_ok=True)
class Q(SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
servers=[]
def serve(directory):
 s=ThreadingHTTPServer(('127.0.0.1',0),partial(Q,directory=str(directory)));threading.Thread(target=s.serve_forever,daemon=True).start();servers.append(s);return 'http://127.0.0.1:'+str(s.server_port)
url=serve(ROOT/'_site');baseline=serve(ROOT.parent/'pre-top-filters-build');errors=[];report={}
cases=[{}, {'product':'survey'}, {'status':'source-active'}, {'status':'source-pending','region':'CN'}, {'raw':'公开'}, {'raw':'未缴年费','stage':'grant-document'}, {'stage':'published','product':'gnss'}, {'since':'2026-11-01'}, {'type':'design'}, {'q':'CN110749912A'}, {'q':'不存在的专利_938xyz'}]
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':1440,'height':900});old=b.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
  old.goto(baseline,wait_until='networkidle');old.wait_for_selector('.pm-canvas');p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  assert not p.locator('.atlas-workspace #workspace-filters').count()
  assert p.locator('#enterprise-select').is_visible()
  for id in ['current-q','current-product','law-status','law-region','current-clear']:assert p.locator('#'+id).is_visible()
  assert p.locator('#workspace-filters').bounding_box()['y']<p.locator('.atlas-workspace').bounding_box()['y']
  counts=[]
  for c in cases:
   expected=old.evaluate("""c=>{currentQuery=c.q||'';currentFilter={product:c.product||'',status:c.type||'',form:''};lawFilter={status:c.status||'',region:c.region||'',raw:c.raw||'',stage:c.stage||'',since:c.since||''};return currentFiltered().map(d=>d.id).sort();}""",c)
   p.locator('#current-clear').click()
   for key,id in [('product','current-product'),('status','law-status'),('region','law-region'),('raw','law-raw'),('stage','law-stage'),('since','law-since'),('type','current-status'),('q','current-q')]:
    if key not in c:continue
    if key in ['raw','stage','since','type'] and not p.locator('.top-more').evaluate('(e)=>e.open'):p.locator('.top-more summary').click()
    if key in ['since','q']:p.locator('#'+id).fill(c[key])
    else:p.locator('#'+id).select_option(c[key])
   actual=p.evaluate('currentFiltered().map(d=>d.id).sort()');assert actual==expected,(c,len(expected),len(actual))
   counts.append({'filters':c,'documents':len(actual),'idsMatchPreviousRelease':True})
  p.locator('#current-clear').click();assert p.evaluate('currentFiltered().length')==938
  if p.locator('.top-more').evaluate('(e)=>e.open'):p.locator('.top-more summary').click()
  p.locator('.top-source-fold summary').click();assert all(x in p.locator('.top-filter-notes').inner_text() for x in ['2026-11-03','未官方核验','地域和状态按同一条文献组合筛选','不等同于有效地域'])
  p.locator('.top-source-fold summary').click()
  p.locator('#pm-locate').fill('CN110749912A');p.locator('[data-path-result]').first.click();assert p.evaluate('nodeDetail.patent')=='CN110749912A'
  state=p.evaluate('JSON.stringify(panorama)');p.locator('[data-pm-zoom="in"]').click();zoom=p.locator('.pm-viewport').get_attribute('data-zoom')
  for name in ['filters','details']:
   p.locator('[data-panel="'+name+'"]').click();p.locator('[data-panel="'+name+'"]').click();p.wait_for_timeout(100)
   assert p.evaluate('JSON.stringify(panorama)')==state;assert p.locator('.pm-viewport').get_attribute('data-zoom')==zoom
  p.locator('[data-path-current]').click();p.locator('[data-pm-zoom="fit"]').click()
  p.locator('[data-pm-full]').click();p.wait_for_function('document.fullscreenElement || document.querySelector(".pm-expanded")');assert p.locator('#node-detail-content').is_visible()
  p.locator('[data-pm-full]').click();p.wait_for_function('!document.fullscreenElement&&!document.querySelector(".pm-expanded")')
  p.locator('#current-product').select_option('survey');assert p.evaluate('nodeDetail') is None;assert p.evaluate('panorama.product')=='survey';assert 'CN110749912A' not in p.locator('.pm-breadcrumb').inner_text()
  # Small screens can open all controls and scroll the panel without overflowing the page.
  p.set_viewport_size({'width':390,'height':844});p.locator('[data-panel="filters"]').click();p.locator('[data-panel="filters"]').click()
  p.locator('.top-more summary').click();assert p.locator('#law-stage').is_visible();p.locator('#law-stage').select_option('published');assert p.locator('#law-stage').input_value()=='published'
  assert '已选' in p.locator('.top-more summary').inner_text();assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
  p.locator('#current-clear').click();assert p.evaluate('currentFiltered().length')==938
  p.screenshot(path=str(OUT/'mobile-expanded-filters.png'),full_page=True)
  assert not errors,errors
  report={'status':'pass','filterCases':counts,'sourceNoticePreserved':True,'enterpriseVisible':True,'directPatentAndDetail':True,'resizePreservesZoomAndPath':True,'fullscreenDetails':True,'mobileExpandedControls':True,'pageErrors':errors}
  b.close()
finally:
 for s in servers:s.shutdown()
(ROOT/'reports/top-filters-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
