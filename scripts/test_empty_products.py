"""Actual 3-document filter reproduction, zero-category explanations, recovery and isolation."""
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import json,threading
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT.parent/'empty-products-preview';OUT.mkdir(exist_ok=True)
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'_site')));threading.Thread(target=server.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(server.server_port)
errors=[];report={}
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':1440,'height':900});p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  assert p.evaluate('currentDocs.length')==938
  assert p.locator('.empty-filtered-empty,.empty-unpopulated').count()==0
  assert p.evaluate('panoramaData(currentFiltered()).groups.flatMap(g=>g.children).length')==16
  full=p.evaluate('primaryData.categories.map(c=>productCoverage(c.id))')
  assert sum(c['documents'] for c in full)==938 and sum(c['applications'] for c in full)==807
  # Exact source-status filter yields the screenshot's 3/3; full data remain unchanged.
  p.locator('#law-raw').select_option('公开')
  assert p.evaluate('currentFiltered().length')==3
  assert p.evaluate('new Set(currentFiltered().map(d=>d.applicationNumber)).size')==3
  assert p.locator('.empty-filtered-empty').count()==15
  assert p.locator('.empty-unpopulated').count()==0
  assert '来源法律状态：公开' in p.locator('.pm-filter-summary').inner_text()
  assert '807 申请 / 938 文献' in p.locator('.pm-filter-summary').inner_text()
  assert '筛选匹配' in p.locator('.pm-node.root').inner_text()
  survey=p.locator('[data-guide-key="product||survey"]')
  assert '0 申请 · 0 文献' in survey.inner_text()
  assert '全库 90 申请 / 102 文献' in survey.inner_text()
  p.locator('[data-pm-zoom="fit"]').click();p.screenshot(path=str(OUT/'filtered-overview.png'),full_page=True)
  survey.click();detail=p.locator('#node-detail-content').inner_text()
  assert all(x in detail for x in ['当前匹配 0','90 申请 · 102 文献','不是分类关联缺失','来源法律状态：公开'])
  p.screenshot(path=str(OUT/'empty-category-detail.png'),full_page=True)
  p.locator('[data-open-product-all="survey"]').click()
  assert p.locator('#current-product').input_value()=='survey'
  assert p.locator('#law-raw').input_value()==''
  assert p.evaluate('currentFiltered().length')==102
  assert p.evaluate('new Set(currentFiltered().map(d=>d.applicationNumber)).size')==90
  assert p.evaluate('panorama.level')=='product'
  assert p.locator('.detail-empty').count()==1
  assert p.locator('.pm-filter-summary').count()==0
  p.locator('[data-pm-home]').click();assert p.evaluate('currentFiltered().length')==938
  p.locator('#law-raw').select_option('公开');p.locator('[data-pm-reset-results]').click()
  assert p.evaluate('currentFiltered().length')==938
  assert p.locator('.empty-filtered-empty').count()==0
  # Complete no-match search and combined legal filters are explicitly labeled.
  p.locator('#current-q').fill('不存在的编号000000xyz')
  assert p.evaluate('currentFiltered().length')==0
  assert p.locator('.empty-filtered-empty').count()==16
  assert '搜索：不存在' in p.locator('.pm-filter-summary').inner_text()
  p.locator('[data-pm-reset-results]').click()
  p.locator('#law-raw').select_option('公开');p.locator('#law-stage').select_option('grant-document')
  assert p.evaluate('currentFiltered().length')==0
  assert all(t in p.locator('.pm-filter-summary').inner_text() for t in ['来源法律状态：公开','文献阶段：授权公告文献'])
  p.locator('[data-pm-reset-results]').click()
  # A truly empty preset is tested only in memory, and gets no misleading filter-recovery action.
  p.evaluate("primaryData.categories.push({id:'fixture-empty',name:'隔离空分类',include:'测试用途'});primaryById['fixture-empty']=primaryData.categories.at(-1);currentRender()")
  assert p.locator('.empty-unpopulated').count()==1
  p.locator('[data-guide-key="product||fixture-empty"]').click()
  assert '本企业尚无归入此分类的资料' in p.locator('#node-detail-content').inner_text()
  assert p.locator('[data-open-product-all]').count()==0
  assert p.evaluate('currentDocs.length')==938
  p.close()
  report['layouts']=[]
  for width,height in [(1920,1080),(1440,900),(1366,768),(1280,720),(390,844)]:
   q=b.new_page(viewport={'width':width,'height':height});q.on('pageerror',lambda e:errors.append(str(e)));q.goto(url,wait_until='networkidle');q.wait_for_selector('.pm-canvas')
   if width<1200:q.locator('[data-panel="filters"]').click()
   q.locator('#law-raw').select_option('公开')
   if width<1200:q.locator('[data-panel="filters"]').click()
   layout=q.evaluate('({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,mapHeight:document.querySelector(".pm-viewport").clientHeight})')
   assert layout['scrollWidth']<=width,layout
   if width>=1200:assert layout['scrollHeight']<=height+1,layout
   assert q.locator('.empty-filtered-empty').count()==15
   # All node rectangles remain disjoint after count annotations increase product-node height.
   assert q.evaluate('''()=>{const rr=[...document.querySelectorAll('.pm-canvas foreignObject')].map(x=>({x:+x.getAttribute('x'),y:+x.getAttribute('y'),w:+x.getAttribute('width'),h:+x.getAttribute('height')}));return rr.every((r,i)=>rr.every((s,j)=>i===j||r.x+r.w<=s.x||s.x+s.w<=r.x||r.y+r.h<=s.y||s.y+s.h<=r.y));}''')
   if width==390:q.screenshot(path=str(OUT/'mobile-filter-context.png'),full_page=True)
   report['layouts'].append(layout);q.close()
  assert not errors,errors
  report.update(status='pass',fullLibraryCategories=full,filterExample={'sourceStatusRaw':'公开','documents':3,'applications':3,'filteredEmptyCategories':15},filterResetRecovery=True,unpopulatedPresetDistinguished=True,zeroSearchAndCombination=True,originalDocumentsUnchanged=938,pageErrors=errors)
  b.close()
finally:server.shutdown()
(ROOT/'reports/empty-products-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS: 3/3 reproduction, full category counts, zero explanations/recovery, presets and responsive layout')
