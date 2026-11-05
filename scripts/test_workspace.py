"""Responsive real-data workbench and isolated enterprise navigation checks."""
from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT/'_site')))
threading.Thread(target=server.serve_forever,daemon=True).start()
url='http://127.0.0.1:'+str(server.server_port)+'/'
out=ROOT.parent/'workspace-preview';out.mkdir(exist_ok=True)
report={'screens':[]};errors=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for width,height,name in [(1920,1080,'wide'),(1440,900,'desktop'),(1366,768,'laptop'),(820,1180,'tablet'),(390,844,'mobile')]:
   p=browser.new_page(viewport={'width':width,'height':height});p.on('pageerror',lambda e:errors.append(str(e)))
   p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas')
   assert p.locator('#enterprise-select option').count()==1
   assert p.locator('#enterprise-select').input_value()=='chcnav'
   assert p.evaluate('currentDocs.length')==938
   assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
   assert p.locator('#workspace-filters').is_visible()==(width>=1200)
   assert p.locator('#workspace-notes').is_visible()==(width>=1700)
   box=p.locator('.pm-viewport').bounding_box();report['screens'].append({'name':name,'viewport':[width,height],'map':box})
   assert box['width']>width*(.65 if width>=1200 else .85)
   assert box['y']<height*.48
   p.screenshot(path=str(out/(name+'.png')),full_page=True)
   # Toggling does not reset map, filters or diagram-space position.
   if width>=1200:
    p.locator('#current-product').select_option('gnss');p.locator('.pm-node.leaf button').first.click();p.locator('.pm-node.leaf button').first.click()
    p.locator('[data-pm-zoom="in"]').click()
    prior=p.evaluate('({state:JSON.stringify(panorama),zoom:document.querySelector(".pm-viewport").dataset.zoom})')
    p.locator('[data-panel="filters"]').click();p.wait_for_timeout(100)
    assert p.evaluate('JSON.stringify(panorama)')==prior['state']
    assert p.locator('.pm-viewport').get_attribute('data-zoom')==prior['zoom']
    assert p.locator('#current-product').input_value()=='gnss'
    p.locator('[data-panel="filters"]').click()
    if width==1440:p.screenshot(path=str(out/'desktop-subpath.png'),full_page=True)
   else:p.locator('[data-panel="filters"]').click()
   p.locator('#current-clear').click()
   p.locator('#current-q').fill('CN104697526A');assert p.evaluate('currentFiltered().length')==1
   p.locator('#current-clear').click();assert p.evaluate('currentFiltered().length')==938
   p.locator('#law-stage').select_option('published');p.locator('#law-region').select_option('CN');assert p.evaluate('currentFiltered().length')==463
   p.locator('a[href="#patents"]').first.click();p.wait_for_selector('.current-library');assert p.locator('.current-library').count()==1;assert p.evaluate('currentFiltered().length')==463
   p.locator('#current-clear').click();p.locator('a[href="#updates"]').first.click();p.wait_for_function('lastView==="updates"');assert '本次资料与保留历史' in p.locator('.workspace-main').inner_text()
   p.locator('a[href="#products"]').first.click();p.wait_for_selector('.pm-canvas');p.locator('#pm-locate').fill('农机');p.locator('[data-pm-locate]').click();assert p.locator('.located').count()==1
   if width==390:
    p.locator('#current-product').select_option('survey');p.locator('[data-panel="filters"]').click();p.locator('.pm-node.leaf button').first.click();assert p.evaluate('panorama.level')=='path'
    p.screenshot(path=str(out/'mobile-path.png'),full_page=True)
   p.close()
  # Test-only second bundle: isolated page navigation, no production entry/data written.
  p=browser.new_page();requests=[];p.on('pageerror',lambda e:errors.append(str(e)))
  source=(ROOT/'_site/atlas.js').read_text().replace("const enterpriseConfig=[", "const enterpriseConfig=[{id:'fixture',name:'隔离测试企业',shortName:'隔离测试',entry:'fixture/',pdfRepository:'wang10086-creator/chcnav-patent-pdfs'},")
  # Keep current enterprise default first; exact matching determines selection.
  p.route('**/atlas.js',lambda route:route.fulfill(body=source,content_type='text/javascript'))
  def fixture(route):
   path=route.request.url.split('/fixture/',1)[1].split('?',1)[0] or 'index.html'
   f=ROOT/'_site'/path
   if path=='index.html':
    html=f.read_text().replace('src="atlas.js"','src="/atlas.js"')
    route.fulfill(body=html,content_type='text/html');return
   if path in ['data/portfolio-current.json','data/full-analysis.json','data/product-portraits.json']:
    data=json.loads(f.read_text());target=json.loads((ROOT/'_site/data/full-analysis.json').read_text())['records'][0]
    if isinstance(data,list):data=[d for d in data if d['id']==target['id']]
    elif path=='data/full-analysis.json':data['records']=[target]
    else:data['mappings']=[m for m in data['mappings'] if m['applicationNumber']==target['applicationNumber']]
    route.fulfill(body=json.dumps(data),content_type='application/json');return
   if f.exists():route.fulfill(path=str(f))
   else:route.fulfill(status=404,body='missing fixture')
  p.route('**/fixture/**',fixture)
  p.on('request',lambda r:requests.append(r.url))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas');p.locator('#current-q').fill('GNSS')
  p.locator('#enterprise-select').select_option('fixture');p.wait_for_url('**/fixture/#products');p.wait_for_load_state('networkidle');p.wait_for_selector('.pm-canvas')
  assert p.locator('#current-q').input_value()==''
  assert p.evaluate('panorama.level')=='overview'
  assert p.locator('.pm-heading h2').inner_text()=='隔离测试产品专利全景'
  assert p.evaluate('currentDocs.length')==1
  assert p.locator('#patent-drawer').count()==0
  assert any('/fixture/data/' in r for r in requests)
  assert p.evaluate('panoramaHistory.length')==0
  p.locator('#enterprise-select').select_option('chcnav');p.wait_for_url(url+'#products');p.wait_for_selector('.pm-canvas');assert p.evaluate('currentDocs.length')==938
  report['enterpriseIsolation']='test-only separate bundle: 1 record vs 938; full navigation resets search, nodes and details'
  browser.close()
 assert not errors,errors
 report.update(status='pass',pageErrors=errors)
finally:server.shutdown()
(ROOT/'reports/workspace-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('PASS: responsive layout, sidebars, navigation, filters and enterprise isolation')
