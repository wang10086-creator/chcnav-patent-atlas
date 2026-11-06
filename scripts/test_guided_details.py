"""Real-data descendant guidance, inline evidence and bounded desktop layout."""
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
import threading, json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent/'guided-map-preview';OUT.mkdir(exist_ok=True)
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'_site')))
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(server.server_port)
report={};errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  p=browser.new_page(viewport={'width':1440,'height':900});p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  assert p.locator('#workspace-notes').count()==0
  assert p.locator('.detail-empty').count()==1
  assert p.evaluate('currentDocs.length')==938
  p.locator('[data-pm-zoom="fit"]').click();p.screenshot(path=str(OUT/'desktop-overview.png'),full_page=True)
  # A publication absent from the overview must guide every step without filtering global data.
  target='CN104697526A';p.locator('#pm-locate').fill(target)
  assert p.evaluate('currentFiltered().length')==938
  assert p.evaluate('mapGuidance.matches.length')==2
  assert '2 项' in p.locator('.located').inner_text()
  assert p.evaluate('panorama.level')=='overview'
  p.screenshot(path=str(OUT/'desktop-guidance.png'),full_page=True)
  steps=[]
  for _ in range(8):
   steps.append(p.evaluate('panorama.level'))
   assert p.locator('#pm-locate').input_value()==target
   if p.locator('.guide-target').count():break
   p.locator('.located').click()
  assert steps==['overview','product','path','topic'],steps
  assert p.locator('.guide-target').get_attribute('data-pm-patent')==target
  p.wait_for_function('()=>{const e=document.querySelector(".guide-target"),r=e.getBoundingClientRect(),v=e.closest(".pm-viewport").getBoundingClientRect();return r.left>=v.left&&r.right<=v.right&&r.top>=v.top&&r.bottom<=v.bottom;}')
  p.locator('.guide-target').click()
  assert p.locator('#patent-drawer').count()==0
  detail=p.locator('#node-detail-content').text_content()
  assert all(x in detail for x in [target,'法律状态与地域','2026-11-03','非实时状态','未官方核验','申请／公布地域','原始摘要与元信息'])
  assert p.locator('#node-detail-content .pdf-links a').count()>=1
  assert p.locator('#node-detail-content').evaluate('(e)=>e.scrollHeight>e.clientHeight')
  p.screenshot(path=str(OUT/'desktop-guided-detail.png'),full_page=True)
  # Clicking a second document replaces the pane. Back clears it, retaining the query.
  second=p.locator('[data-pm-patent]').evaluate_all('(xs)=>xs.find(x=>x.dataset.pmPatent!=="CN104697526A").dataset.pmPatent')
  p.locator('[data-pm-patent="'+second+'"]').click()
  assert second in p.locator('#node-detail-content').inner_text()
  p.locator('[data-pm-back]').click();assert p.locator('.detail-empty').count()==1
  assert p.locator('#pm-locate').input_value()==target
  p.locator('[data-pm-locate]').click();assert '2 / 2' in p.locator('#pm-locate-result').inner_text()
  assert p.evaluate('panorama.level')!='topic' # No automatic jump to a leaf.
  for _ in range(6):
   if p.locator('.guide-target').count():break
   p.locator('.located').click()
  assert p.locator('.guide-target').get_attribute('data-pm-patent')==target
  report['deepGuidance']={'publication':target,'paths':2,'levels':steps,'nextReturnsToCommonAncestor':True}
  # No match and clearing must remove every annotation; empty/non-patent terminals show detail.
  p.locator('#pm-locate').fill('没有这个节点_938xyz');assert '无匹配' in p.locator('#pm-locate-result').inner_text();assert p.locator('.guide-match').count()==0
  p.locator('[data-pm-clear]').click();assert p.locator('#pm-locate').input_value()=='';assert p.locator('.located').count()==0
  p.locator('[data-pm-home]').click();p.locator('#law-status').select_option('unverified');p.locator('.pm-node.leaf button').first.click();assert p.locator('.detail-empty').count()==0
  assert '0 申请' in p.locator('#node-detail-content').inner_text()
  p.locator('#current-clear').click();assert p.locator('.detail-empty').count()==1
  # Later pagination: locate a real document at position >= 12 from its parent path.
  route=p.evaluate('''()=>{for(const product of primaryData.categories){const productState={level:'product',product:product.id,scene:'',form:'',path:'',topic:'',page:0};for(const form of panoramaData(currentFiltered(),productState).groups){const fs={...productState,...form.action};for(const path of panoramaData(currentFiltered(),fs).nodes){const ps={...fs,...path.action};for(const topic of panoramaData(currentFiltered(),ps).nodes){const ts={...ps,...topic.action},ns=panoramaData(currentFiltered(),ts).nodes;if(ns.length>24)return {path:ps,topic:ts,target:ns[20].patent};}}}}}''')
  assert route
  p.evaluate('(s)=>panoramaGo(s)',route['path']);p.locator('#pm-locate').fill(route['target']);p.locator('.located').click()
  assert p.evaluate('panorama.page')==1
  assert p.locator('.guide-target').get_attribute('data-pm-patent')==route['target']
  p.locator('[data-pm-page="1"]').click();assert p.evaluate('panorama.page')==2 # Pagination still usable with an active query.
  p.locator('#law-region').select_option('CN');assert p.locator('#pm-locate').input_value()=='';assert p.locator('.guide-match').count()==0;assert p.locator('.detail-empty').count()==1
  report['paginationTarget']=route['target']
  # Scope semantics: a search started in one product cannot find another product's documents.
  p.locator('#current-product').select_option('survey');p.locator('#pm-locate').fill(target);assert '无匹配' in p.locator('#pm-locate-result').inner_text()
  p.locator('#current-q').fill('CN104697526A');assert p.locator('#pm-locate').input_value()==''
  p.locator('#current-clear').click();p.locator('#current-q').fill(target);assert p.evaluate('currentFiltered().length')==1
  p.locator('#current-clear').click()
  # All moved explanations, sources and dates remain under updates.
  p.locator('[data-pm-info]').click();p.wait_for_selector('#materials-notes')
  p.locator('[data-open-key="current-coverage"]').evaluate('(e)=>e.open=true')
  notes=p.locator('#materials-notes').inner_text()
  assert all(t in notes for t in ['资料覆盖','938','807','IncoPat','2026-11-03','未官方核验','不等同于有效地域','不公开','导图操作','场景依据','常规方法载体'])
  assert p.locator('#materials-notes a[download]').count()>=7
  p.screenshot(path=str(OUT/'updates-notes.png'),full_page=True)
  p.locator('a[href="#products"]').first.click();p.wait_for_selector('.pm-canvas')
  # Bounded desktops; smaller/zoom-equivalent viewports permit needed scroll without clipping.
  report['layouts']=[]
  for width,height,name in [(1920,1080,'wide'),(1440,900,'desktop'),(1366,768,'laptop'),(1280,720,'small-desktop'),(820,1180,'tablet'),(390,844,'mobile'),(683,384,'zoom-equivalent')]:
   q=browser.new_page(viewport={'width':width,'height':height});q.on('pageerror',lambda e:errors.append(str(e)));q.goto(url,wait_until='networkidle');q.wait_for_selector('.pm-canvas')
   layout=q.evaluate('({width:innerWidth,height:innerHeight,scrollHeight:document.documentElement.scrollHeight,scrollWidth:document.documentElement.scrollWidth,map:document.querySelector(".pm-viewport").getBoundingClientRect().toJSON()})')
   assert layout['scrollWidth']<=width
   if width>=1200:
    assert layout['scrollHeight']<=height+1,layout
    assert layout['map']['height']>=330,layout
    q.locator('#current-product').select_option('gnss');q.locator('.pm-node.leaf button').first.click();q.locator('.pm-node.leaf button').first.click()
    q.locator('[data-pm-patent]').first.click()
    assert q.evaluate('document.documentElement.scrollHeight')<=height+1
    q.locator('[data-pm-zoom="in"]').click();before=q.evaluate('({state:JSON.stringify(panorama),zoom:document.querySelector(".pm-viewport").dataset.zoom})')
    q.locator('[data-panel="details"]').click();q.locator('[data-panel="filters"]').click();q.wait_for_timeout(150)
    assert q.evaluate('JSON.stringify(panorama)')==before['state'];assert q.locator('.pm-viewport').get_attribute('data-zoom')==before['zoom']
    q.locator('[data-panel="details"]').click();q.locator('[data-panel="filters"]').click()
   else:
    q.locator('#pm-locate').fill(target)
    for _ in range(6):
     if q.locator('.guide-target').count():break
     q.locator('.located').click()
    q.locator('.guide-target').click();q.wait_for_timeout(350)
    assert q.locator('#workspace-details').is_visible();assert target in q.locator('#node-detail-content').inner_text()
    assert q.evaluate('document.documentElement.scrollWidth')<=width
   q.screenshot(path=str(OUT/(name+'.png')),full_page=width>=1200)
   report['layouts'].append(layout);q.close()
  # Existing design evidence still opens, switches original pages and returns to this pane.
  p.locator('#pm-locate').fill('CN308935268S')
  for _ in range(6):
   if p.locator('.guide-target').count():break
   p.locator('.located').click()
  p.locator('.guide-target').click()
  assert '原页 4/4 页' in p.locator('#node-detail-content .design-views').inner_text()
  assert p.locator('#node-detail-content').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
  p.locator('[data-dv-mode="pages"]').click();p.locator('[data-dv-open]').first.click()
  p.wait_for_function('document.querySelector("#design-viewer img").complete && document.querySelector("#design-viewer img").naturalWidth>0')
  assert p.locator('#design-viewer').is_visible()
  p.locator('[data-dv-close]').click();assert 'CN308935268S' in p.locator('#node-detail-content').inner_text()
  report['designEvidence']={'publication':'CN308935268S','originalPages':4,'viewerImageLoaded':True}
  # Fullscreen retains the inline pane within the fullscreen subtree.
  p.locator('[data-pm-full]').click();p.wait_for_function('document.fullscreenElement || document.querySelector(".pm-expanded")')
  assert p.evaluate('(document.fullscreenElement||document.querySelector(".pm-expanded")).contains(document.querySelector("#workspace-details"))')
  p.locator('[data-pm-full]').click();p.wait_for_function('!document.fullscreenElement&&!document.querySelector(".pm-expanded")')
  assert not errors,errors
  report.update(status='pass',noPageErrors=True,sourceDatesUnchanged=True,inlineDetailSwitchAndClear=True,explanationsPreserved=True,fullscreenDetails=True)
  browser.close()
finally:server.shutdown()
(ROOT/'reports/guided-details-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS: deep guided search, inline details, pagination, notes and seven responsive sizes')
