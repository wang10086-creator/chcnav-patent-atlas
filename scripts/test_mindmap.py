from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
import threading,json
from playwright.sync_api import sync_playwright
r=Path.cwd();sv=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(r/'_site')));threading.Thread(target=sv.serve_forever,daemon=True).start()
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:'+str(sv.server_port),wait_until='networkidle');page.wait_for_selector('.mm-node')
 assert page.locator('.reader-directory').count()==0 and page.locator('.reader-detail').count()==0
 page.locator('.mindmap-workspace').screenshot(path=str(r.parent/'release-validation/mindmap-desktop.png'))
 count=page.locator('[data-mm-path]').count();assert count>0
 page.locator('[data-mm-path]').first.click();assert page.locator('#mindmap-detail').is_visible();page.locator('.mm-subpath summary').first.click();assert page.locator('.reader-reference').first.is_visible()
 page.locator('#mindmap-detail').screenshot(path=str(r.parent/'release-validation/mindmap-window.png'))
 page.keyboard.press('Escape');assert not page.locator('#mindmap-detail').is_visible()
 checks=page.evaluate('''()=>{const out=[];for(const p of primaryData.categories){currentFilter.product=p.id;resetReader(p.id);currentRender();const m=readerModel(currentFiltered());const expected=Object.keys(claimFormLabels).reduce((n,f)=>n+Math.min(6,readerRankedPaths(routeTopics(m.items,f)).length),0);if(document.querySelectorAll('[data-mm-path]').length!==expected)throw Error(p.id);out.push({product:p.id,paths:expected});}currentFilter.product='';resetReader();currentRender();return out;}''')
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.locator('[data-mm-path]').first.click();assert page.locator('#mindmap-detail').is_visible();page.keyboard.press('Escape')
 page.locator('.mindmap-workspace').screenshot(path=str(r.parent/'release-validation/mindmap-mobile.png'))
 assert not errors,errors
 (r/'reports/mindmap-validation.json').write_text(json.dumps({'products':checks,'desktop':True,'mobile':True,'secondaryWindow':True,'escapeCloses':True,'originalInlineDetailsRemoved':True,'pageErrors':errors},ensure_ascii=False,indent=2)+'\n')
 print('PASS',len(checks),'products; modal, desktop/mobile, no errors');b.close()
sv.shutdown()
