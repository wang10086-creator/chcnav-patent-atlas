from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import threading,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];out=ROOT.parent/'technical-points-preview';out.mkdir(exist_ok=True)
class Q(SimpleHTTPRequestHandler):
 def log_message(self,*a):pass
s=ThreadingHTTPServer(('127.0.0.1',0),partial(Q,directory=str(ROOT/'_site')));threading.Thread(target=s.serve_forever,daemon=True).start()
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);p=b.new_page(viewport={'width':1440,'height':900});errors=[];p.on('pageerror',lambda e:errors.append(str(e)))
  p.goto('http://127.0.0.1:'+str(s.server_port),wait_until='networkidle');p.wait_for_selector('.pm-canvas')
  p.locator('#pm-locate').fill('CN104697526A')
  for _ in range(6):
   if p.locator('.guide-target').count():break
   p.locator('.located').click()
  assert p.locator('.guide-target').get_attribute('data-pm-patent')=='CN104697526A'
  assert '用于农业机械的捷联惯导系统以及控制方法' not in p.locator('.guide-target b').inner_text()
  p.locator('.guide-target').click()
  assert p.locator('#node-detail-content .current-form-block').count()>0
  assert not p.locator('#node-detail-content .legal-details-fold').evaluate('(e)=>e.open')
  assert p.locator('#node-detail-content').evaluate('(e)=>!!(e.querySelector(".current-form-block").compareDocumentPosition(e.querySelector(".legal-details-fold")) & Node.DOCUMENT_POSITION_FOLLOWING)')
  p.screenshot(path=str(out/'technical-first-desktop.png'),full_page=True)
  p.locator('.legal-details-fold>summary').click();assert p.locator('.legal-details-fold .law-panel').is_visible();assert '2026-11-03' in p.locator('.legal-details-fold').inner_text();assert '未官方核验' in p.locator('.legal-details-fold').inner_text()
  # Every summary is copied from the same publication's saved analysis; no cross-version inference.
  checks=p.evaluate("""()=>{let analyzed=0,extracted=0;for(const d of currentDocs){const v=patentNodePoint(d),a=currentAnalyses.find(a=>a.id===d.id);if(!v.title||!v.description||v.sourceId!==d.id||v.basis==='待核实')throw Error('missing '+d.id);if(v.basis.includes('权项摘录')){const c=currentTexts[d.id].claims.find(c=>Number(c.number)===1)||currentTexts[d.id].claims[0];if(v.description!==c.text.replace(/\\s+/g,' ').trim())throw Error('wrong text');extracted++;}else analyzed++;}return {analyzed,extracted,documents:currentDocs.length};}""")
  assert p.locator('.guide-target small').inner_text().startswith('CN104697526A · 用于农业机械')
  assert p.locator('#node-detail-content .technical-point-evidence').count()==1

  p.locator('[data-pm-home]').click();p.locator('[data-pm-clear]').click();p.locator('#pm-locate').fill('用于农业机械的捷联惯导系统');assert p.evaluate('mapGuidance.matches.length')>0
  p.set_viewport_size({'width':390,'height':844});assert p.evaluate('document.documentElement.scrollWidth<=innerWidth')
  p.evaluate("openCurrentPatent('CN107490368B')");assert p.locator('.current-form-block').count()>0;assert not p.locator('.legal-details-fold').evaluate('(e)=>e.open');p.screenshot(path=str(out/'technical-first-mobile.png'))
  assert not errors,errors
  (ROOT/'reports/technical-points-validation.json').write_text(json.dumps({'status':'pass',**checks,'originalTitleSearch':True,'lawCollapsedAndExpandable':True,'mobileNoOverflow':True,'pageErrors':errors},ensure_ascii=False,indent=2)+'\n')
  b.close()
finally:s.shutdown()
print('PASS: version-specific labels, original-title/ID search, technical-first details, expandable legal data, mobile')
