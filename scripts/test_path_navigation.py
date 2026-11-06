"""Exercise actual paths, URL/history restoration and direct results on the full baseline."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];out=ROOT.parent/'path-navigation-preview';out.mkdir(exist_ok=True)
class Q(SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
s=ThreadingHTTPServer(('127.0.0.1',0),partial(Q,directory=str(ROOT/'_site')));threading.Thread(target=s.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(s.server_port);report={};errors=[]
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':1600,'height':1000});p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  target='CN110749912A';p.locator('#pm-locate').fill(target)
  matches=p.evaluate('mapGuidance.matches.map(x=>({key:x.key,patent:x.patent,path:x.trail.map(t=>t.title)}))');assert len(matches)>=1,matches
  assert '匹配文献 1 件' in p.locator('#pm-search-results summary').inner_text()
  assert all(m['patent']==target for m in matches)
  p.screenshot(path=str(out/'after-search-results.png'),full_page=True)
  p.locator('[data-path-result]').first.click();assert p.evaluate('panorama.level')=='topic'
  assert p.evaluate('nodeDetail.patent')==target
  assert target in p.locator('.pm-breadcrumb').inner_text()
  assert p.locator('#node-detail-content .technical-point-evidence').count()==1
  assert not p.locator('#node-detail-content .legal-details-fold').evaluate('(e)=>e.open')
  if not p.locator('#path-navigation').is_visible():p.locator('[data-path-toggle]').click()
  assert target in p.locator('#path-navigation [aria-current="location"]').inner_text()
  assert p.locator('#path-navigation li.on-path').count()==5 # product/form/path/topic/publication
  assert p.locator('.pm-node.patent .path-current').get_attribute('data-pm-patent')==target
  selected=p.evaluate('JSON.stringify(panorama)');hash1=p.url
  # A copied route also resolves without the original tab's session cache.
  shared=b.new_page(viewport={'width':1440,'height':900});shared.goto(hash1,wait_until='networkidle');shared.wait_for_selector('.pm-canvas')
  assert shared.evaluate('nodeDetail?.patent')==target
  assert shared.evaluate('JSON.stringify(panorama)')==selected
  shared.close()
  p.context.grant_permissions(['clipboard-read','clipboard-write'])
  p.locator('[data-path-copy]').click();p.wait_for_function('document.querySelector("[data-path-copy]").textContent==="已复制路径"')
  assert p.evaluate('navigator.clipboard.readText()')==p.url
  report['copiedLinkNewTab']=True
  p.locator('#pm-search-results summary').click()
  p.screenshot(path=str(out/'after-desktop.png'),full_page=True)
  # Manual pan and zoom remain until explicit recenter; no periodic forced recenter.
  p.locator('[data-pm-zoom="in"]').click();p.locator('.pm-viewport').evaluate('(e)=>{e.scrollLeft=0;e.scrollTop=0;}');p.wait_for_timeout(150)
  pos=p.locator('.pm-viewport').evaluate('(e)=>({left:e.scrollLeft,top:e.scrollTop,zoom:e.dataset.zoom})');p.wait_for_timeout(250)
  assert pos==p.locator('.pm-viewport').evaluate('(e)=>({left:e.scrollLeft,top:e.scrollTop,zoom:e.dataset.zoom})')
  p.locator('[data-path-current]').click();assert p.locator('.path-current').first.count()
  assert p.evaluate('JSON.stringify(panorama)')==selected
  before=p.locator('.pm-viewport').evaluate('(e)=>({left:e.scrollLeft,top:e.scrollTop,zoom:e.dataset.zoom})')
  p.reload(wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  assert p.evaluate('nodeDetail?.patent')==target
  assert p.evaluate('JSON.stringify(panorama)')==selected,(selected,p.evaluate('JSON.stringify(panorama)'))
  assert p.locator('.pm-viewport').get_attribute('data-zoom')==before['zoom']
  # Choose a different associated path if the actual publication has multiple paths.
  p.locator('[data-pm-home]').click();p.locator('#pm-locate').fill(target)
  if len(matches)>1:
   p.locator('[data-path-result]').nth(1).click();assert p.evaluate('JSON.stringify(panorama)')!=selected
   assert p.evaluate('nodeDetail.patent')==target
  # Back/forward restores the selected exact document, not stale details from a different branch.
  p.locator('[data-pm-home]').click();assert p.locator('.detail-empty').count()==1
  p.go_back(wait_until='networkidle');assert p.evaluate('nodeDetail?.patent')==target
  p.go_forward(wait_until='networkidle');assert p.evaluate('panorama.level')=='overview';assert p.locator('.detail-empty').count()==1
  # A real known multipath document: one document, two paths, both independently selectable.
  p.locator('#pm-locate').fill('CN104697526A');assert p.locator('[data-path-result]').count()==2
  assert '匹配文献 1 件 · 关联路径 2 条' in p.locator('#pm-search-results summary').inner_text()
  p.locator('[data-path-result]').nth(1).click();key=p.evaluate('panoramaStateKey(panorama)')
  p.locator('[data-path-result]').first.click();assert key!=p.evaluate('panoramaStateKey(panorama)')
  p.locator('[data-pm-back]').click();assert p.evaluate('panorama.level')=='path';assert p.locator('.detail-empty').count()==1
  p.locator('[data-pm-back]').click();assert p.evaluate('panorama.level')=='form'
  # No match must leave the current route untouched; clearing removes result list.
  key=p.evaluate('panoramaStateKey(panorama)');p.locator('#pm-locate').fill('不存在_938xyz')
  assert '无匹配' in p.locator('#pm-search-results').inner_text();assert key==p.evaluate('panoramaStateKey(panorama)')
  p.locator('[data-pm-clear]').click();assert not p.locator('#pm-search-results').is_visible()
  # Filters and product changes remove old selection/highlights.
  p.locator('#current-product').select_option('survey');assert p.evaluate('panorama.product')=='survey';assert p.locator('.detail-empty').count()==1
  assert 'CN104697526A' not in p.locator('.pm-breadcrumb').inner_text()
  p.locator('#law-region').select_option('CN');assert p.evaluate('nodeDetail') is None
  # Explicit layer/path names can be selected directly without a publication match.
  p.locator('[data-pm-home]').click();p.locator('#pm-locate').fill('参考站网络与差分分发');assert p.locator('[data-path-result]').count()>0
  p.locator('[data-path-result]').first.click();assert p.evaluate('panorama.level')=='topic'
  # Invalid ID cannot silently display a different document; friendly fallback is visible.
  p.goto(url+'/#products?map='+__import__('urllib.parse').parse.quote(json.dumps({'v':1,'company':'chcnav','state':{'level':'topic','product':'gnss','form':'method','path':'not-a-path','topic':'invalid'},'patent':'CN000000000A'})),wait_until='networkidle')
  assert p.locator('.path-notice').count()==1;assert p.evaluate('nodeDetail') is None
  assert p.evaluate('panorama.level') in ['product','form']
  # Audit the full real hierarchy and exercise all products/protection layers without mutating data.
  p.goto(url,wait_until='networkidle')
  audit=p.evaluate("""()=>{const index=guidanceIndex(pathRoot(),currentFiltered()),docs=new Set(index.filter(x=>x.patent).map(x=>x.patent)),forms=index.filter(x=>x.trail.at(-1).state?.level==='form');return {documents:docs.size,forms:forms.map(x=>x.trail.at(-1).state),hidden:forms.flatMap(x=>{const state=x.trail.at(-1).state,ns=panoramaData(currentFiltered(),state).nodes;return ns.slice(6).map(n=>({state,title:n.title,target:{...state,...n.action}}));})};}""")
  assert audit['documents']==938,audit['documents']
  for state in audit['forms']:
   p.evaluate('(s)=>jumpPath(s)',state)
   assert p.evaluate('panoramaStateKey(panorama)')==p.evaluate('(s)=>panoramaStateKey(s)',state)
   assert p.locator('.pm-breadcrumb [aria-current="page"]').count()==1
   assert p.locator('#path-navigation [aria-current="location"]').count()==1
  report['allProductsAndLayers']={'products':len(set(s['product'] for s in audit['forms'])),'layers':len(audit['forms']),'searchableDocuments':audit['documents'],'collapsedRouteCount':len(audit['hidden'])}
  if audit['hidden']:
   hidden=audit['hidden'][0]
   p.locator('[data-pm-home]').click();p.locator('[data-pm-clear]').click();p.locator('#pm-locate').fill(hidden['title']);p.locator('[data-path-result]').first.click()
   assert p.evaluate('panorama.level')=='path'
   report['collapsedRouteDirect']=hidden['title']
  # Collapsed navigation ancestors are recoverable using the explicit current-node operation.
  p.goto(url,wait_until='networkidle');p.locator('#pm-locate').fill(target);p.locator('[data-path-result]').first.click()
  if not p.locator('#path-navigation').is_visible():p.locator('[data-path-toggle]').click()
  p.locator('#path-navigation [data-path-expand]').first.click()
  assert p.locator('#path-navigation [aria-current="location"]').count()==0
  p.locator('[data-path-current]').click();assert p.locator('#path-navigation [aria-current="location"]').count()==1
  # Mobile: navigation is a closable in-flow panel with independent scroll, no horizontal overflow.
  p.goto(url,wait_until='networkidle');p.set_viewport_size({'width':390,'height':844});p.locator('#pm-locate').fill(target);p.locator('[data-path-result]').first.click()
  p.locator('[data-path-toggle]').click();assert p.locator('#path-navigation').is_visible()
  assert p.locator('#path-navigation').evaluate('(e)=>e.scrollHeight>e.clientHeight')
  assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
  p.locator('[data-path-current]').click();p.locator('#path-navigation').scroll_into_view_if_needed();p.screenshot(path=str(out/'after-mobile.png'))
  p.locator('[data-path-close]').click();assert not p.locator('#path-navigation').is_visible()
  report.update(status='pass',publication=target,actualPaths=len(matches),paths=matches,knownMultipath={'publication':'CN104697526A','documents':1,'paths':2},refreshAndHistory=True,panZoomAndRecenter=True,invalidPathFallback=True,mobileNoOverflow=True,baselineDocuments=p.evaluate('currentDocs.length'),pageErrors=errors)
  assert not errors,errors
  b.close()
finally:s.shutdown()
(ROOT/'reports/path-navigation-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
