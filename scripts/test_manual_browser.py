from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Q(SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
s=ThreadingHTTPServer(('127.0.0.1',0),partial(Q,directory=str(ROOT/'_site')));threading.Thread(target=s.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(s.server_port)
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':1440,'height':1000});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
  r={'kind':'patent','company':'fixture','companyName':'隔离测试企业','publicationId':'US20240012345A1','applicationNumber':'US20240012345','jurisdiction':'US','title':'隔离测试文献','applicants':'测试','sourceUrl':'https://example.org/record','productId':'other'}
  event=lambda r:{'record':r,'fingerprint':'test-only','enteredAt':'2026-11-05T01:00:00Z'}
  ledger={'schemaVersion':1,'events':[event(r),event({**r,'publicationId':'US20240012345B1'}),event({'kind':'status','company':'fixture','publicationId':r['publicationId'],'applicationNumber':r['applicationNumber'],'jurisdiction':'US','statusRaw':'待核实测试','normalizedStatus':'unknown','asOf':'2026-11-05','verification':'manual','sourceUrl':'https://example.org/status'})]}
  p.route('**/manual-updates.json',lambda route:route.fulfill(body=json.dumps(ledger),content_type='application/json'))
  p.goto(url,wait_until='networkidle');p.wait_for_selector('.pm-canvas');assert p.evaluate('currentDocs.length')==938
  p.locator('#enterprise-select').select_option('fixture');assert p.evaluate('currentDocs.length')==2;assert p.evaluate('new Set(currentDocs.map(d=>d.applicationNumber)).size')==1
  assert '隔离测试企业' in p.locator('.pm-heading').inner_text();assert '待分析资料 2' in p.locator('.panorama-workspace').inner_text()
  p.locator('a[href="#patents"]').first.click();p.wait_for_selector('.current-library');assert p.locator('.current-library article').count()==2;p.locator('.current-library article a').first.click();p.wait_for_selector('.law-panel');assert '追加状态记录' in p.locator('#patent-drawer').inner_text()
  p.locator('#enterprise-select').select_option('chcnav');assert p.evaluate('currentDocs.length')==938
  p.goto(url+'/maintenance.html',wait_until='networkidle');p.locator('[name="publicationId"]').fill('CN123456789A');p.locator('[name="applicationNumber"]').fill('CN202010000001.1');p.locator('#add').click();assert '新增' in p.locator('#preview').inner_text();assert p.locator('#export').is_disabled();p.locator('#consent').check();assert not p.locator('#export').is_disabled()
  with p.expect_download() as download:p.locator('#export').click()
  assert download.value.suggested_filename=='manual-patent-draft.json';p.locator('#clear').click();assert p.locator('#preview').inner_text()=='尚无草稿'
  p.set_viewport_size({'width':390,'height':844});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors
  out=ROOT.parent/'manual-update-preview';out.mkdir(exist_ok=True);p.screenshot(path=str(out/'editor-mobile.png'),full_page=True);b.close()
finally:s.shutdown()
print('PASS: isolated new enterprise, A/B document counts, pending portrait, manual status, draft confirmation/cancel, mobile')
